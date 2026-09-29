import pytest

from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.geometry_analysis import build_geometry_report
from src.cad_understanding.polyline_parts import source_of, split_polyline


def pline(h, vertices, closed=False, bulges=None, layer="A-WALL"):
    bulges = bulges if bulges is not None else [0] * len(vertices)
    xs, ys = [v[0] for v in vertices], [v[1] for v in vertices]
    return {"handle": h, "entity_type": "AcDbPolyline", "layer": layer,
            "geometry": {"vertices": vertices, "closed": closed, "bulges": bulges, "bulges_complete": True},
            "bbox": {"min": [min(xs), min(ys)], "max": [max(xs), max(ys)]}}


def line(h, a, b, layer="A-WALL"):
    return {"handle": h, "entity_type": "AcDbLine", "layer": layer, "geometry": {"start": a, "end": b}}


def snapshot(items):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "plan.dwg", "units": "in"},
            "sections": {"entities": {"items": items, "total": len(items)}}}


def walls(items, **kw):
    return build_architectural_report(snapshot(items), wall_thickness_range=[4, 12], **kw)["wall_segment_candidates"]


def test_split_keeps_sources_and_reports_arcs():
    parts, excluded = split_polyline("P", {"vertices": [[0, 0], [10, 0], [10, 5], [0, 5]], "closed": True,
                                           "bulges": [0, 0.5, 0, 0], "bulges_complete": True}, "id")
    assert [p["handles"] for p in parts] == [["P#0"], ["P#2"], ["P#3"]]
    assert parts[2]["geometry"] == {"start": [0, 5, 0.0], "end": [0, 0, 0.0]}  # closing segment
    assert excluded == [{"handle": "P#1", "reason": "arc_segment_not_supported"}]
    assert split_polyline("P", {"vertices": [[0, 0], [1, 0]], "bulges": None}, "id")[1][0]["reason"] == \
        "polyline_bulges_not_captured"
    assert source_of("P#2") == {"handle": "P", "segment_index": 2}
    assert source_of("8B0") == {"handle": "8B0", "segment_index": None}


def test_closed_outline_wall_pairs_its_long_sides():
    seg = walls([pline("P", [[0, 0], [200, 0], [200, 8], [0, 8]], closed=True)])
    assert seg["segment_count"] == 1
    s = seg["segments"][0]
    assert s["handles"] == ["P#0", "P#2"]
    assert s["sources"] == [{"handle": "P", "segment_index": 0}, {"handle": "P", "segment_index": 2}]
    assert s["thickness_drawing_units"]["mean"] == pytest.approx(8)
    assert s["axis_wcs"] == [[0, pytest.approx(4), 0.0], [pytest.approx(200), pytest.approx(4), 0.0]]


def test_polyline_l_wall_corner_and_mixed_line_face():
    outer = pline("O", [[0, 300], [0, 0], [500, 0]])
    inner = pline("I", [[8, 300], [8, 8], [500, 8]])
    seg = walls([outer, inner])
    assert seg["segment_count"] == 2
    assert [j["kind"] for j in seg["junctions"]["junctions"]] == ["corner"]
    assert seg["junctions"]["junctions"][0]["point_wcs"] == [pytest.approx(4), pytest.approx(4)]
    mixed = walls([pline("O", [[0, 0], [500, 0]]), line("L", [0, 8], [500, 8])])
    assert mixed["segments"][0]["sources"] == [{"handle": "L", "segment_index": None},
                                               {"handle": "O", "segment_index": 0}]


def test_arc_faces_are_excluded_explicitly_and_limit_coverage():
    seg = walls([pline("A", [[0, 0], [100, 0], [100, 50]], bulges=[0, 1, 0]), line("L", [0, 8], [100, 8])])
    assert seg["segment_count"] == 1
    assert {"handle": "A#1", "reason": "arc_segment_not_supported"} in seg["excluded"]
    assert not seg["coverage_complete"]


def test_generic_pairs_use_polyline_segments_without_wall_names():
    items = [pline("P", [[0, 0], [200, 0], [200, 8], [0, 8]], closed=True, layer="PART")]
    pairs = build_geometry_report(snapshot(items), parallel_separation_range=[4, 12])["parallel_line_pairs"]
    assert pairs["pair_count"] == 1 and pairs["pairs"][0]["handles"] == ["P#0", "P#2"]
    assert pairs["scope"] == "selected_LINE_and_straight_polyline_segments"
    # Legacy LINE diagnostics are unchanged: polylines are not LINE candidates there.
    report = build_geometry_report(snapshot(items))
    assert report["line_diagnostics"]["candidate_count"] == 0
