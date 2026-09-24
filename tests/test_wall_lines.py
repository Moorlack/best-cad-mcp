from copy import deepcopy

import pytest

from src.cad_database import CADDatabase
from src.cad_understanding.architecture import build_architectural_report, analyze_architectural_drawing


def line(handle, start, end, layer="A-WALL"):
    return {"handle": handle, "entity_type": "AcDbLine", "layer": layer,
            "geometry": {"start": start, "end": end}}


def report(items, tolerance=None):
    return build_architectural_report({"schema_version": "cad-ir/v2", "sections": {
        "entities": {"items": items}}}, wall_gap_tolerance=tolerance)


@pytest.mark.parametrize("start,end,relation", [
    ([0, 0], [10, 0], "duplicate"), ([10, 0], [0, 0], "duplicate"),
    ([5, 0], [15, 0], "overlap"), ([2, 0], [8, 0], "overlap"),
    ([5, -5], [5, 5], "intersection"), ([5, 0], [5, 5], "t_junction"),
    ([10, 0], [15, 0], "endpoint_joint"), ([10, 0], [10, 5], "endpoint_joint"),
    ([11, 0], [15, 0], None), ([0, 1], [10, 1], None),
    ([0, 0, 3], [10, 0, 3], None),
])
def test_wall_line_relationships(start, end, relation):
    r = report([line("A", [0, 0], [10, 0]), line("B", start, end)])
    d = r["wall_line_diagnostics"]
    assert d["eligible_lines"] == 2
    assert d["checked_pairs"] == 1
    assert d["unverified_pairs"] == []
    assert not d["physical_walls_assembled"] and not d["gaps_checked"]
    assert not r["structural_design_ready"]
    if relation:
        assert d["items"][0]["relation"] == relation
        assert d["items"][0]["handles"] == ["A", "B"]
    else:
        assert d["items"] == []


def test_unlabelled_and_conflicting_lines_do_not_become_confirmed_wall_edges():
    r = report([line("A", [0, 0], [10, 0], "0"),
                line("B", [0, 0], [10, 0], "A-WALL-DOOR"),
                line("C", [0, 0, 0], [10, 0, 3])])
    d = r["wall_line_diagnostics"]
    assert d["candidate_count"] == 2
    assert d["eligible_lines"] == 0
    assert {e["handle"] for e in d["excluded"]} == {"B", "C"}


def test_wall_polylines_excluded_without_crashing():
    item = {"handle": "P", "entity_type": "AcDbPolyline", "layer": "A-WALL",
            "geometry": {"vertices": [[0, 0], [1, 0], [1, 1]], "closed": False}}
    assert report([item])["wall_line_diagnostics"]["excluded"][0]["handle"] == "P"


def test_translation_rotation_and_input_order():
    items = [line("B", [1e9, 1e9 + 5], [1e9, 1e9 + 15]),
             line("A", [1e9, 1e9], [1e9, 1e9 + 10])]
    original = deepcopy(items)
    d = report(items)["wall_line_diagnostics"]
    assert d["items"][0]["relation"] == "overlap"
    assert report(list(reversed(items)))["wall_line_diagnostics"] == d
    assert items == original


def test_line_limit_and_extreme_numeric_ranges_are_explicit():
    items = [line(f"L{i:03}", [0, i], [10, i]) for i in range(101)]
    d = report(items)["wall_line_diagnostics"]
    assert d["eligible_lines"] == 100
    assert d["excluded"] == [{"handle": "L100", "reason": "line_limit_exceeded"}]
    d = report([line("A", [-1e308, 0], [1e308, 0])])["wall_line_diagnostics"]
    assert d["excluded"][0]["reason"] == "non_horizontal_or_degenerate_line"


def test_sqlite_ir_roundtrip_preserves_native_handles(tmp_path):
    db = CADDatabase(str(tmp_path / "cad.db"))
    db.configure_context(workspace_root=str(tmp_path), drawing_name="wall-test.dwg")
    for handle in ("A1", "B1"):
        db.upsert_entity(handle, "Line", "AcDbLine", layer="A-WALL",
                         geometry={"start": [0, 0, 0], "end": [10, 0, 0]})
    result = analyze_architectural_drawing(database=db)
    assert "wall_line_duplicate" in result["warnings"]
    assert result["data"]["report"]["wall_line_diagnostics"]["items"][0]["handles"] == ["A1", "B1"]


@pytest.mark.parametrize("start,end,tolerance,count", [
    ([10.25, 0], [20, 0], 0.25, 1),
    ([10.25, 0], [20, 0], 0.2, 0),
    ([10.25, 0], [20, 0], None, 0),
    ([10, 0], [20, 0], 0.25, 0),
    ([5, -2], [5, 2], 10, 0),
    ([10.125, 0.125], [20, 5], 0.25, 1),
    ([10.25, 0, 3], [20, 0, 3], 5, 0),
    ([5, 0.125], [5, 5], 0.25, 0),
])
def test_gap_search_requires_explicit_tolerance_and_disjoint_same_plane(start, end, tolerance, count):
    r = report([line("A", [0, 0], [10, 0]), line("B", start, end)], tolerance)
    d = r["wall_line_diagnostics"]
    assert len(d["gap_search"]["candidates"]) == count
    assert d["gap_search"]["requested"] is (tolerance is not None)
    if count:
        gap = d["gap_search"]["candidates"][0]
        assert gap["handles"] == ["A", "B"]
        assert gap["endpoints"][0] == {"handle": "A", "endpoint": "end", "point": [10, 0, 0]}
        assert gap["distance_drawing_units"] <= tolerance
        assert gap["requires_architectural_review"]
    assert not r["structural_design_ready"]


@pytest.mark.parametrize("value", [0, -1, True, "0.25", float("inf"), float("nan"), 10**1000])
def test_invalid_gap_tolerance_returns_error_without_scanning(value):
    result = analyze_architectural_drawing(wall_gap_tolerance=value)
    assert result["ok"] is False


def test_gap_search_limit_does_not_claim_complete_coverage():
    items = [line(f"L{i:03}", [0, i], [10, i]) for i in range(101)]
    d = report(items, 0.25)["wall_line_diagnostics"]
    assert d["gap_search"]["requested"]
    assert d["gaps_checked"] is False
    assert len(d["excluded"]) == 1


def test_gap_sqlite_pipeline_reports_distance_and_preserves_geometry(tmp_path):
    db = CADDatabase(str(tmp_path / "gap.db"))
    for h, start, end in [("A", [0, 0, 0], [10, 0, 0]), ("B", [10.25, 0, 0], [20, 0, 0])]:
        db.upsert_entity(h, "Line", "AcDbLine", layer="A-WALL", geometry={"start": start, "end": end})
    before = deepcopy(db.get_entity("B"))
    r = analyze_architectural_drawing(database=db, wall_gap_tolerance=0.5)
    assert "wall_endpoint_gap_candidate" in r["warnings"]
    gap = r["data"]["report"]["wall_line_diagnostics"]["gap_search"]["candidates"][0]
    assert gap["distance_drawing_units"] == 0.25
    assert db.get_entity("B") == before
