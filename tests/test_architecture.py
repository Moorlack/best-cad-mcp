"""Synthetic architectural fixtures; no AutoCAD session is required."""

import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from src.cad_database import CADDatabase
from src.cad_understanding.architecture import analyze_architectural_drawing, build_architectural_report


def entity(handle, layer, kind="Line", geometry=None):
    return {"handle": handle, "layer": layer, "entity_type": kind,
            "object_name": "AcDb" + kind, "geometry": geometry or {"start": [0, 0], "end": [10, 0]}}


def outline():
    return {"vertices": [[0, 0], [10, 0], [10, 8], [0, 8]], "closed": True}


def ir(entities, path="plan.dwg"):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": path, "units": "unknown"},
            "sections": {"entities": {"items": entities, "total": len(entities), "truncated": False}}}


def codes(report):
    return {i["code"] for i in report["issues"]}


def test_unclassified_block_annotations_do_not_become_semantic_evidence():
    captured = {"status": "partial", "items": [
        {"handle": "AT1", "tag": "TYPE", "text": "WALL", "invisible": True,
         "kind": "reference"}]}
    drawing = ir([entity("B1", "0", "BlockReference", {
        "insertion_point": [0, 0, 0], "block_attributes": captured})])
    report = build_architectural_report(drawing)
    assert report["candidates"] == []
    assert report["block_annotations"]["items"][0]["text"] == "WALL"
    assert "block_attributes_incomplete" in codes(report)
    assert report["structural_design_ready"] is False


def test_synthetic_architectural_plan_preserves_evidence_without_engineering_claims():
    drawing = ir([
        entity("A1", "A-WALL"), entity("A2", "A-DOOR"), entity("A3", "S-GRID"),
        entity("A4", "S-SLAB", "Polyline", outline()),
        entity("A5", "A-ROOM", "Polyline", outline()),
        entity("A6", "S-COLS", "Circle", {"center": [4, 4], "radius": 0.2}),
        entity("A7", "A-GLAZ"), entity("A8", "A-OPNG"),
    ])
    original = deepcopy(drawing)
    report = build_architectural_report(drawing)
    assert {c["category"] for c in report["candidates"]} == {
        "wall", "door", "grid", "slab_boundary", "room_boundary", "column", "window", "opening"}
    assert all(c["status"] == "candidate" and c["structural_role"] == "unknown"
               for c in report["candidates"])
    assert all(c["confidence"] == "MEDIUM" for c in report["candidates"])
    assert report["candidates"][0]["handles"] == ["A1"]
    assert report["candidates"][0]["evidence"][0]["value"] == "A-WALL"
    assert not report["structural_design_ready"]
    assert "units_unverified" in codes(report)
    assert drawing == original
    json.dumps(report, allow_nan=False)
    report["candidates"][0]["geometry"]["start"][0] = 99
    assert drawing == original


def test_conflicting_layer_and_block_name_remain_low_confidence():
    report = build_architectural_report(ir([entity(
        "B1", "A-WALL", "BlockReference",
        {"block_name": "DOOR-36", "insertion_point": [0, 0, 0]},
    )]))
    assert len(report["candidates"]) == 2
    assert {c["confidence"] for c in report["candidates"]} == {"LOW"}
    assert "conflicting_semantic_hints" in codes(report)
    assert all("block_contents_not_interpreted" in c["warnings"] for c in report["candidates"])


def test_annotation_on_wall_layer_and_substring_names_are_not_walls():
    report = build_architectural_report(ir([
        entity("T1", "A-WALL", "Text", {"text": "WALL", "insertion_point": [0, 0]}),
        entity("T2", "A-WALLPAPER"), entity("T3", "COLOR"),
        entity("T4", "A-SLAB"),
    ]))
    assert report["candidates"] == []
    assert report["coverage"]["unclassified_entities"] == 4
    assert "name_geometry_mismatch" in codes(report)


def test_unlabelled_boundary_is_not_promoted_to_slab_or_room():
    geometry = outline()
    geometry["bulges"] = [0, 1, 0, 0]
    report = build_architectural_report(ir([entity("P1", "0", "Polyline", geometry)]))
    candidate = report["candidates"][0]
    assert candidate["category"] == "closed_boundary"
    assert candidate["confidence"] == "LOW"
    assert candidate["geometry"]["bulges"] == [0, 1, 0, 0]
    assert "area" not in candidate
    assert "boundary_topology_not_verified" in candidate["warnings"]


@pytest.mark.parametrize("geometry", [
    {}, {"start": [0, 0], "end": [0, 0]},
    {"start": [float("nan"), 0], "end": [1, 0]},
    {"start": [0, 0], "end": [float("inf"), 0]},
    {"start": [True, 0], "end": [2, 0]},
])
def test_invalid_line_geometry_is_never_classified(geometry):
    item = entity("L1", "A-WALL")
    item["geometry"] = geometry
    report = build_architectural_report(ir([item]))
    assert report["candidates"] == []
    assert "name_geometry_mismatch" in codes(report)
    json.dumps(report, allow_nan=False)


def test_missing_duplicate_handles_and_partial_scan_are_explicit():
    drawing = ir([entity("", "A-WALL"), entity("D1", "A-WALL"), entity("D1", "A-WALL")])
    drawing["sections"]["entities"].update(total=20, truncated=True)
    drawing["sections"]["blocks"] = {"items": [{"name": "architecture", "is_xref": True}]}
    report = build_architectural_report(drawing)
    assert report["candidates"] == []
    assert {"invalid_entity_identity", "incomplete_entity_coverage", "xref_contents_unverified"} <= codes(report)


def test_ids_are_stable_across_order_and_unique_across_drawings():
    items = [entity("F1", "A-WALL"), entity("F2", "A-DOOR")]
    first = build_architectural_report(ir(items))["candidates"]
    assert first == build_architectural_report(ir(list(reversed(items))))["candidates"]
    other = build_architectural_report(ir(items, "other.dwg"))["candidates"]
    assert {c["id"] for c in first}.isdisjoint(c["id"] for c in other)


def test_empty_snapshot_does_not_claim_empty_dwg_or_design_readiness():
    report = build_architectural_report(ir([]))
    assert {"empty_snapshot", "snapshot_freshness_unverified"} <= codes(report)
    assert report["structural_design_ready"] is False


def test_real_sqlite_ir_adapter_preserves_native_handles_and_scopes_drawings(tmp_path):
    db = CADDatabase(str(tmp_path / "cad.db"))
    db.configure_context(workspace_root=str(tmp_path), conversation_id="c", thread_id="t",
                         drawing_name="first.dwg", drawing_path=str(tmp_path / "first.dwg"))
    db.upsert_entity("A1", "Line", "AcDbLine", layer="A-WALL",
                     geometry={"start_point": [0, 0, 0], "end_point": [10, 0, 0]},
                     bbox=(0, 0, 10, 0), topology_detail="full")
    db.upsert_entity("A2", "Line", "AcDbLine", layer="S-GRID",
                     geometry={"start": [0, 0], "end": [0, 5]}, bbox=(0, 0, 0, 5))
    with patch("src.cad_understanding.ir_builder._maybe_rescan", return_value=None) as rescan:
        result = analyze_architectural_drawing(database=db)
        rescan.assert_called_once_with(False)
    assert result["ok"]
    assert result["handles"] == ["A1", "A2"]
    assert "units_unverified" in result["warnings"]
    assert "incomplete_entity_coverage" in analyze_architectural_drawing(1, db)["warnings"]
    db.configure_context(drawing_name="second.dwg", drawing_path=str(tmp_path / "second.dwg"))
    assert analyze_architectural_drawing(database=db)["handles"] == []


@pytest.mark.parametrize("limit", [0, -1, 100001, True, 1.5])
def test_invalid_limits_do_not_touch_database(limit):
    with patch("src.cad_understanding.architecture.build_drawing_ir") as build:
        assert not analyze_architectural_drawing(limit)["ok"]
        build.assert_not_called()


def test_wrong_ir_contract_rejected():
    with pytest.raises(ValueError, match="cad-ir/v2"):
        build_architectural_report({})
    with pytest.raises(ValueError, match="entities"):
        build_architectural_report({"schema_version": "cad-ir/v2"})
