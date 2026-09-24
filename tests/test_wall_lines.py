from copy import deepcopy

import pytest

from src.cad_database import CADDatabase
from src.cad_understanding.architecture import build_architectural_report, analyze_architectural_drawing


def line(handle, start, end, layer="A-WALL"):
    return {"handle": handle, "entity_type": "AcDbLine", "layer": layer,
            "geometry": {"start": start, "end": end}}


def report(items):
    return build_architectural_report({"schema_version": "cad-ir/v2", "sections": {
        "entities": {"items": items}}})


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
