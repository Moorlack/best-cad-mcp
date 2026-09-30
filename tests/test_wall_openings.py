import asyncio
import math
from unittest.mock import patch

import pytest
from mcp import Client

from src import server
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.axis_junctions import find_axis_gaps
from src.cad_understanding.region_overlap import band_polygon, box_band_overlap


def test_band_overlap_area_length_and_rotation():
    band = band_polygon([0, 0], [10, 0], 2)                      # y in [-1, 1]
    assert box_band_overlap({"min": [2, 0], "max": [4, 2]}, band) == {"measure": "area", "ratio": pytest.approx(0.5)}
    assert box_band_overlap({"min": [2, 5], "max": [4, 6]}, band)["ratio"] == 0
    assert box_band_overlap({"min": [-5, 0], "max": [5, 0]}, band) == {"measure": "length", "ratio": pytest.approx(0.5)}
    assert box_band_overlap({"min": [3, 0], "max": [3, 0]}, band) == {"measure": "point", "ratio": 1.0}
    diagonal = band_polygon([0, 0], [10, 10], 2 * math.sqrt(2))  # 45 degrees
    assert box_band_overlap({"min": [4, 4], "max": [6, 6]}, diagonal)["ratio"] == pytest.approx(1.0)
    assert box_band_overlap({"min": [8, 0], "max": [9, 1]}, diagonal)["ratio"] == 0


def test_axis_gaps_on_same_line_only():
    axes = [{"id": "A", "start": [0, 4], "end": [100, 4], "width": 8},
            {"id": "B", "start": [300, 4], "end": [136, 4], "width": 8},   # reversed direction
            {"id": "C", "start": [100, 40], "end": [200, 40], "width": 8},  # parallel, other line
            {"id": "D", "start": [50, 4], "end": [80, 4], "width": 8}]      # overlaps A
    r = find_axis_gaps(axes, 48)
    assert [(g["ids"], g["gap_length"]) for g in r["gaps"]] == [(["A", "B"], pytest.approx(36))]
    assert r["gaps"][0]["start_wcs"] == [pytest.approx(100), pytest.approx(4)]
    assert r["gaps"][0]["end_wcs"] == [pytest.approx(136), pytest.approx(4)]
    assert find_axis_gaps(axes, 30)["gap_count"] == 0
    with pytest.raises(ValueError, match="max_gap"):
        find_axis_gaps(axes, 0)


def line(h, a, b, layer="A-WALL"):
    lo, hi = [min(a[k], b[k]) for k in (0, 1)], [max(a[k], b[k]) for k in (0, 1)]
    return {"handle": h, "entity_type": "AcDbLine", "layer": layer, "geometry": {"start": a, "end": b},
            "bbox": {"min": lo, "max": hi}}


def block(h, name, point, lo, hi):
    return {"handle": h, "entity_type": "AcDbBlockReference", "layer": "0",
            "geometry": {"insertion_point": point, "block_name": name}, "bbox": {"min": lo, "max": hi}}


ITEMS = [
    line("W1", [0, 0], [100, 0]), line("W2", [0, 8], [100, 8]),          # wall piece 1
    line("W3", [136, 0], [300, 0]), line("W4", [136, 8], [300, 8]),      # after a 36 door gap
    line("W5", [340, 0], [400, 0]), line("W6", [340, 8], [400, 8]),      # after a 40 gap, no symbol
    block("D1", "DOOR-36", [100, 0, 0], [100, -30], [136, 8]),           # door in the gap
    line("N1", [200, 4], [240, 4], "A-WINDOW"),                          # window over continuous faces
    block("D2", "DOOR-36", [1000, 1000, 0], [1000, 1000], [1036, 1036]),  # far from walls
]


def snapshot(items):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "plan.dwg", "units": "in"},
            "sections": {"entities": {"items": items, "total": len(items)}}}


def report(**kw):
    return build_architectural_report(snapshot(ITEMS), wall_thickness_range=[4, 12], **kw)


def test_openings_related_to_gaps_and_segments():
    r = report(wall_opening_max_width=48)
    openings = r["wall_segment_candidates"]["openings"]
    assert openings["gap_search"] and len(openings["gaps"]) == 2
    status = {tuple(o["handles"]): o["status"] for o in openings["openings"]}
    assert status == {("D1",): "in_wall_gap", ("N1",): "on_wall_segment", ("D2",): "not_on_wall_segment"}
    door = next(o for o in openings["openings"] if o["handles"] == ["D1"])
    assert door["gap_matches"][0]["measure"] == "area" and 0 < door["gap_matches"][0]["ratio"] < 1
    assert not door["opening_verified"]
    assert all(seg["openings_checked"] for seg in r["wall_segment_candidates"]["segments"])
    empty = openings["gaps_without_opening_candidate"]
    assert len(empty) == 1
    gap = next(g for g in openings["gaps"] if g["id"] == empty[0])
    assert gap["gap_length"] == pytest.approx(40)
    codes = [i["code"] for i in r["issues"]]
    assert codes.count("wall_gap_without_opening_candidate") == 1
    assert ("opening_not_on_wall_segment", ["D2"]) in [(i["code"], i["handles"]) for i in r["issues"]]
    assert report(wall_opening_max_width=48)["wall_segment_candidates"]["openings"] == openings


def test_without_gap_search_door_in_gap_is_not_on_segments():
    openings = report()["wall_segment_candidates"]["openings"]
    assert not openings["gap_search"] and openings["gaps"] == []
    status = {tuple(o["handles"]): o["status"] for o in openings["openings"]}
    # The door box only touches the face ends; without a gap search it is not on any wall.
    assert status[("D1",)] == "not_on_wall_segment" and status[("N1",)] == "on_wall_segment"
    assert "openings" not in build_architectural_report(snapshot(ITEMS))["wall_segment_candidates"]


def test_opening_width_requires_segments_and_is_positive():
    with pytest.raises(ValueError, match="requires wall_thickness_range"):
        build_architectural_report(snapshot(ITEMS), wall_opening_max_width=48)
    with pytest.raises(ValueError, match="wall_opening_max_width"):
        report(wall_opening_max_width=-1)


def test_native_mcp_passes_opening_width():
    async def exercise():
        async with Client(server.mcp) as client:
            await client.call_tool("analyze_architectural_drawing", {"wall_thickness_range": [4, 12],
                                                                     "wall_opening_max_width": 48})

    with patch.object(server.understanding_architecture, "analyze_architectural_drawing",
                      return_value={"ok": True}) as arch:
        asyncio.run(exercise())
    assert arch.call_args.kwargs["wall_opening_max_width"] == 48


def _door(h, rotation=0.0, x_scale=1.0, normal=(0, 0, 1)):
    d = block(h, "DOOR-36", [100, 0, 0], [100, -30], [136, 8])
    d["geometry"].update({"rotation": rotation, "x_scale": x_scale, "y_scale": 1.0, "normal": list(normal)})
    return d


def _door_items(door):
    items = [e for e in ITEMS if e["handle"] not in {"D1", "D2", "N1"}] + [door]
    r = build_architectural_report(snapshot(items), wall_thickness_range=[4, 12], wall_opening_max_width=48)
    return next(o for o in r["wall_segment_candidates"]["openings"]["openings"] if o["handles"] == [door["handle"]])


def test_gap_width_and_block_placement_along_wall():
    item = _door_items(_door("D1"))
    assert item["opening_width_candidate_drawing_units"] == pytest.approx(36)
    assert item["width_source"] == "distance_between_face_ends"
    p = item["block_placement"]
    assert p["reference"] == "gap" and p["axis_length"] == pytest.approx(36)
    assert p["offset_from_axis"] == pytest.approx(-4) and p["position_along_axis"] == pytest.approx(0)
    assert p["within_axis_span"] and not p["mirrored"]
    assert p["orientation"] == "along_wall" and p["rotation_relative_to_wall_degrees"] == pytest.approx(0)


@pytest.mark.parametrize("rotation,x_scale,normal,orientation,mirrored", [
    (math.pi / 2, 1.0, (0, 0, 1), "across_wall", False),
    (math.pi, -1.0, (0, 0, 1), "along_wall", True),
    (math.radians(30), 1.0, (0, 0, 1), "oblique", False),
    (0.0, 1.0, (0, 0, -1), "not_evaluated_non_plan_normal_or_missing_rotation", False),
])
def test_block_orientation_and_mirroring(rotation, x_scale, normal, orientation, mirrored):
    p = _door_items(_door("D1", rotation, x_scale, normal))["block_placement"]
    assert p["orientation"] == orientation and p["mirrored"] is mirrored


def test_non_block_openings_have_no_placement():
    r = report(wall_opening_max_width=48)
    window = next(o for o in r["wall_segment_candidates"]["openings"]["openings"] if o["handles"] == ["N1"])
    assert "block_placement" not in window and "opening_width_candidate_drawing_units" not in window


def _swing_arc(center, start, end, normal=(0, 0, 1)):
    return {"center": list(center), "start": list(start), "end": list(end), "normal": list(normal)}


def test_arc_from_geometry_and_swing_match_for_a_quarter_circle():
    import math

    from src.cad_understanding.opening_swings import arc_from_geometry, find_swings

    arc = arc_from_geometry(_swing_arc((0, 0, 0), (36, 0, 0), (0, 36, 0)))
    assert arc["radius"] == pytest.approx(36) and math.degrees(arc["sweep"]) == pytest.approx(90)
    swings = find_swings([("A1", arc)], (0, 0), (36, 0))
    assert len(swings) == 1 and swings[0]["hinge_end"] == "start" and swings[0]["swing_side"] == "left"
    assert swings[0]["radius_to_opening_width_ratio"] == pytest.approx(1.0)
    # Mirrored plane normal flips the plan direction: same points now sweep clockwise (270 degrees).
    flipped = arc_from_geometry(_swing_arc((0, 0, 0), (36, 0, 0), (0, 36, 0), normal=(0, 0, -1)))
    assert math.degrees(flipped["sweep"]) == pytest.approx(270)
    assert find_swings([("A2", flipped)], (0, 0), (36, 0)) == []  # sweep outside the door range
    # Wrong radius or hinge far from both ends: no swing.
    assert find_swings([("A1", arc)], (0, 0), (90, 0)) == []
    assert find_swings([("A1", arc)], (100, 100), (136, 100)) == []
    assert arc_from_geometry({"center": [0, 0], "start": [1, 0], "end": [0, 5]}) is None


def test_block_definition_arcs_are_placed_with_rotation_scale_and_mirror():
    import math

    from src.cad_understanding.opening_swings import block_arcs_wcs

    definition = {"arcs": [_swing_arc((0, 0, 0), (36, 0, 0), (0, 36, 0))], "origin": [0, 0, 0]}
    reference = {"block_definition": definition, "insertion_point": [100, 50, 0], "rotation": math.pi / 2,
                 "x_scale": 1.0, "y_scale": 1.0, "normal": [0, 0, 1]}
    (arc,) = block_arcs_wcs(reference)
    assert arc["center"] == pytest.approx((100, 50)) and arc["radius"] == pytest.approx(36)
    # Rotated by 90 degrees the quarter circle runs from +Y to -X.
    assert math.degrees(arc["start_angle"]) == pytest.approx(90)
    assert math.degrees(arc["sweep"]) == pytest.approx(90)
    scaled = block_arcs_wcs({**reference, "rotation": 0.0, "x_scale": 2.0, "y_scale": 2.0})
    assert scaled[0]["radius"] == pytest.approx(72)
    mirrored = block_arcs_wcs({**reference, "rotation": 0.0, "x_scale": -1.0, "y_scale": 1.0})
    assert mirrored[0]["center"] == pytest.approx((100, 50))
    assert math.degrees(mirrored[0]["sweep"]) == pytest.approx(90)
    assert block_arcs_wcs({**reference, "x_scale": 2.0, "y_scale": 1.0}) == []  # non-uniform scale
    assert block_arcs_wcs({**reference, "normal": [0, 0, -1]}) == []
    assert block_arcs_wcs({"insertion_point": [0, 0, 0]}) == []


def test_relate_openings_reports_swing_arc_candidates():
    from src.cad_understanding.opening_swings import arc_from_geometry
    from src.cad_understanding.wall_openings import relate_openings

    def seg(i, a, b):
        return {"id": i, "axis_wcs": [a, b], "thickness_drawing_units": {"min": 8, "max": 8}}

    segments = [seg("S1", [0, 0, 0], [100, 0, 0]), seg("S2", [136, 0, 0], [236, 0, 0])]
    door = {"id": "door1", "category": "door", "handles": ["D"], "shape": "closed_polyline",
            "bbox": {"min": [100, -4], "max": [136, 4]}}
    arc = arc_from_geometry(_swing_arc((100, 0, 0), (136, 0, 0), (100, 36, 0)))
    report = relate_openings([door], segments, 50, "x", arcs=[("ARC1", arc)])
    item = report["openings"][0]
    assert item["status"] == "in_wall_gap" and item["swing_status"] == "swing_arc_candidate"
    assert item["swing_arcs"][0]["source"] == "ARC1" and item["swing_arcs"][0]["hinge_end"] == "start"
    none = relate_openings([door], segments, 50, "x", arcs=[])["openings"][0]
    assert none["swing_status"] == "none_found" and none["swing_arcs"] == []
    no_gap = relate_openings([door], segments, None, "x", arcs=[("ARC1", arc)])["openings"][0]
    assert no_gap["swing_status"] == "not_evaluated_no_gap_width" and "swing_arcs" not in no_gap


def test_xref_references_are_reported_without_expansion():
    ir = {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg", "units": "mm"},
          "sections": {"entities": {"items": [
              {"handle": "X1", "entity_type": "AcDbBlockReference", "layer": "A-WALL",
               "geometry": {"block_name": "SITE_XREF", "insertion_point": [0, 0, 0]}},
              {"handle": "B1", "entity_type": "AcDbBlockReference", "layer": "A-DOOR",
               "geometry": {"block_name": "DOOR", "insertion_point": [1, 1, 0]}}], "total": 2},
              "blocks": {"items": [{"name": "SITE_XREF", "is_xref": True}, {"name": "DOOR", "is_xref": False}]}}}
    report = build_architectural_report(ir)
    codes = {i["code"]: i for i in report["issues"]}
    assert codes["xref_reference_not_expanded"]["handles"] == ["X1"]
    assert "xref_contents_unverified" in codes
    assert any("model space is scanned" in text.lower() or "Only model space" in text for text in report["limitations"])


def _segment(seg_id, a, b, thickness=8.0):
    return {"id": seg_id, "axis_wcs": [list(a), list(b)],
            "thickness_drawing_units": {"min": thickness, "max": thickness, "mean": thickness}}


def test_wall_runs_chain_collinear_segments_across_gaps_but_not_corners():
    from src.cad_understanding.axis_junctions import find_axis_junctions
    from src.cad_understanding.wall_runs import build_wall_runs

    segments = [_segment("A", (0, 0, 0), (100, 0, 0)), _segment("B", (136, 0, 0), (236, 0, 0)),
                _segment("C", (300, 0, 0), (400, 0, 0)), _segment("V", (236, 4, 0), (236, 104, 0))]
    junctions = find_axis_junctions(
        [{"id": s["id"], "start": s["axis_wcs"][0], "end": s["axis_wcs"][1], "width": 8.0} for s in segments],
        tolerance=70)["junctions"]
    for junction in junctions:
        junction["segment_ids"] = junction.pop("ids")
    runs = build_wall_runs(segments, junctions)
    assert len(runs) == 1  # A-B-C chained by gaps; the perpendicular V joins only by a corner/T
    run = runs[0]
    assert run["segment_ids"] == ["A", "B", "C"] and run["gap_count"] == 2
    assert run["span_length"] == pytest.approx(400) and run["drawn_length"] == pytest.approx(300)
    assert run["gap_length_total"] == pytest.approx(100)
    assert run["axis_wcs"][0] == pytest.approx([0, 0]) and run["axis_wcs"][1] == pytest.approx([400, 0])
    assert run["physical_wall_verified"] is False and run["thickness_varies"] is False
    assert build_wall_runs(segments[:1], []) == []


def test_wall_runs_count_overlaps_without_double_counting_length():
    from src.cad_understanding.wall_runs import build_wall_runs

    segments = [_segment("A", (0, 0, 0), (100, 0, 0)), _segment("B", (60, 0, 0), (160, 0, 0), 12.0)]
    junctions = [{"kind": "parallel_overlap", "segment_ids": ["A", "B"], "overlap_length": 40}]
    (run,) = build_wall_runs(segments, junctions)
    assert run["drawn_length"] == pytest.approx(160) and run["overlap_count"] == 1
    assert run["thickness_varies"] is True


def test_segment_candidates_expose_runs_field():
    from src.cad_understanding.wall_pairs import build_wall_segment_candidates

    assert build_wall_segment_candidates([], None).get("runs") is None  # not requested


def test_wall_runs_can_be_linked_by_opening_gaps_beyond_junction_tolerance():
    from src.cad_understanding.wall_runs import build_wall_runs

    segments = [_segment("A", (0, 0, 0), (100, 0, 0)), _segment("B", (136, 0, 0), (236, 0, 0)),
                _segment("C", (300, 0, 0), (400, 0, 0))]
    assert build_wall_runs(segments, []) == []
    gaps = [{"segment_ids": ["A", "B"], "gap_length": 36}, {"segment_ids": ["B", "C"], "gap_length": 64}]
    (run,) = build_wall_runs(segments, [], gaps=gaps)
    assert run["segment_ids"] == ["A", "B", "C"] and run["gap_count"] == 2
    assert run["gap_length_total"] == pytest.approx(100)
    # A gap already reported as a junction is not double counted.
    known = [{"kind": "collinear_gap", "segment_ids": ["A", "B"], "gap_length": 36}]
    (again,) = build_wall_runs(segments, known, gaps=gaps)
    assert again["gap_count"] == 2
