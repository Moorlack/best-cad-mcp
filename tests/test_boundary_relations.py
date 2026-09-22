from copy import deepcopy

import pytest

from src.cad_understanding import boundary_relations
from src.cad_understanding.architecture import build_architectural_report, analyze_architectural_drawing
from src.cad_database import CADDatabase


def polygon(points, z=0):
    return {"vertices": [[x, y, z] for x, y in points], "closed": True,
            "bulges": [0] * len(points), "bulges_complete": True,
            "vertices_coordinate_system": "WCS", "normal": [0, 0, 1]}


def rectangle(x, y, width, height, z=0):
    return polygon([(x, y), (x + width, y), (x + width, y + height), (x, y + height)], z)


def report(geometries):
    return build_architectural_report({"schema_version": "cad-ir/v2", "sections": {
        "entities": {"items": [{"handle": h, "entity_type": "AcDbPolyline",
                                  "layer": "A-SLAB", "geometry": g}
                                 for h, g in geometries.items()]}}})


@pytest.mark.parametrize("inner,relation", [
    (rectangle(2, 2, 2, 2), "contains"),
    (rectangle(9, 2, 2, 2), "intersection_or_touch"),
    (rectangle(10, 2, 2, 2), "intersection_or_touch"),
    (rectangle(10, 10, 2, 2), "intersection_or_touch"),
    (rectangle(0, 0, 10, 10), "intersection_or_touch"),
    (rectangle(12, 12, 2, 2), None),
    (rectangle(2, 2, 2, 2, z=3), None),
])
def test_pair_relations(inner, relation):
    r = report({"OUTER": rectangle(0, 0, 10, 10), "INNER": inner})
    relations = r["boundary_relations"]
    assert relations["checked_pairs"] == 1
    assert relations["unverified_pairs"] == 0
    assert not relations["holes_confirmed"]
    assert not relations["net_area_calculated"]
    assert not r["structural_design_ready"]
    if relation:
        assert relations["items"][0]["relation"] == relation
    else:
        assert relations["items"] == []
    if relation == "contains":
        assert relations["items"][0]["outer_handle"] == "OUTER"
        assert relations["items"][0]["inner_handle"] == "INNER"
        assert r["boundary_checks"][1]["geometric_area_drawing_units_squared"] == 100


def test_concave_outline_bbox_does_not_imply_containment():
    r = report({"L": polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]),
                "IN_BBOX": rectangle(2, 2, 1, 1)})
    assert r["boundary_relations"]["items"] == []


def test_translation_winding_and_input_order_do_not_change_relations():
    geometries = {"OUTER": rectangle(1e9, 1e9, 10, 10),
                  "INNER": rectangle(1e9 + 2, 1e9 + 2, 2, 2)}
    expected = report(geometries)["boundary_relations"]
    original = deepcopy(geometries)
    report(geometries)
    assert geometries == original
    geometries["INNER"]["vertices"].reverse()
    assert report(dict(reversed(list(geometries.items()))))["boundary_relations"] == expected


def test_bad_and_curved_contours_excluded_not_treated_as_disjoint():
    curved = rectangle(2, 2, 2, 2)
    curved["bulges"][0] = 0.5
    r = report({"OUTER": rectangle(0, 0, 10, 10), "CURVE": curved,
                "BAD": polygon([(0, 0), (2, 2), (0, 2), (2, 0)])})
    assert r["boundary_relations"]["eligible_contours"] == 1
    assert r["boundary_relations"]["excluded_contour_handles"] == ["BAD", "CURVE"]
    assert "boundary_relations_incomplete" in {i["code"] for i in r["issues"]}


def test_budget_exhaustion_is_explicit(monkeypatch):
    monkeypatch.setattr(boundary_relations, "MAX_EDGE_COMPARISONS", 0)
    r = report({"A": rectangle(0, 0, 10, 10), "B": rectangle(2, 2, 2, 2)})
    assert r["boundary_relations"]["checked_pairs"] == 0
    assert r["boundary_relations"]["unverified_pairs"] == 1
    assert r["boundary_relations"]["items"] == []


def test_extreme_scale_difference_not_silently_classified():
    r = report({"A": rectangle(0, 0, 1e9, 1e9), "B": rectangle(100, 100, 1, 1)})
    assert r["boundary_relations"]["unverified_pairs"] == 1


def test_sqlite_ir_pipeline_keeps_native_handles_and_gross_area(tmp_path):
    db = CADDatabase(str(tmp_path / "cad.db"))
    db.configure_context(workspace_root=str(tmp_path), drawing_name="relations.dwg")
    for handle, geometry in {"A1": rectangle(0, 0, 10, 10), "A2": rectangle(2, 2, 2, 2)}.items():
        db.upsert_entity(handle, "Polyline", "AcDbPolyline", geometry=geometry, layer="A-SLAB")
    r = analyze_architectural_drawing(database=db)["data"]["report"]
    assert r["boundary_relations"]["items"] == [
        {"relation": "contains", "outer_handle": "A1", "inner_handle": "A2", "hole_status": "unverified"}]
    assert r["boundary_checks"][0]["geometric_area_drawing_units_squared"] == 100
