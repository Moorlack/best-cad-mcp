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
