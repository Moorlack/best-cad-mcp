import pytest

from src.cad_understanding.boundaries import check_boundary
from src.cad_understanding.architecture import build_architectural_report


def contour(points, **kwargs):
    return dict(vertices=points, closed=True, bulges=[0] * len(points),
                bulges_complete=True, normal=[0, 0, 1], vertices_coordinate_system="WCS", **kwargs)


@pytest.mark.parametrize("points,area", [
    ([[0, 0], [10, 0], [10, 8], [0, 8]], 80),
    ([[0, 8], [10, 8], [10, 0], [0, 0]], 80),
    ([[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]], 7),
    ([[1e9, 1e9], [1e9 + 10, 1e9], [1e9 + 10, 1e9 + 8], [1e9, 1e9 + 8]], 80),
    ([[0, 0, 3], [10, 0, 3], [10, 8, 3], [0, 8, 3], [0, 0, 3]], 80),
])
def test_valid_simple_polygons(points, area):
    result = check_boundary(contour(points))
    assert result["status"] == "valid_simple_polygon"
    assert result["geometric_area_drawing_units_squared"] == pytest.approx(area)
    assert not result["floor_area_verified"]
    assert not result["holes_checked"]


@pytest.mark.parametrize("points", [
    [[0, 0], [10, 8], [0, 8], [10, 0]],
    [[0, 0], [10, 0], [10, 8], [10, 0], [0, 8]],
    [[0, 0], [10, 0], [5, 0], [5, 8], [0, 8]],
    [[0, 0], [1, 0], [2, 0]],
    [[0, 0], [0, 0], [0, 0]],
    [[0, 0], [10, 0], [5, 0], [10, 8], [0, 8]],
])
def test_invalid_contours_have_no_area(points):
    result = check_boundary(contour(points))
    assert result["status"] == "invalid"
    assert result["geometric_area_drawing_units_squared"] is None


@pytest.mark.parametrize("field,value", [
    ("bulges", [0, 0.01, 0, 0]), ("bulges", [0, None, 0, 0]),
    ("bulges_complete", False), ("bulges_complete", None),
    ("normal", [0, 1, 0]), ("normal", None),
    ("vertices_coordinate_system", "OCS"),
])
def test_unsupported_or_uncertain_geometry_has_no_area(field, value):
    geometry = contour([[0, 0], [10, 0], [10, 8], [0, 8]])
    geometry[field] = value
    result = check_boundary(geometry)
    assert result["status"] == "not_verified"
    assert result["geometric_area_drawing_units_squared"] is None


def test_vertex_limit():
    assert check_boundary(contour([[i, 0] for i in range(257)]))["reason"] == "vertex_limit_exceeded"


def test_report_work_limit_never_approves_unchecked_boundaries():
    entities = [{"handle": f"P{i:03}", "entity_type": "AcDbPolyline", "geometry": contour(
        [[0, 0], [10, 0], [10, 8], [0, 8]])} for i in range(101)]
    result = build_architectural_report({"schema_version": "cad-ir/v2", "sections": {
        "entities": {"items": entities}}})
    last = result["boundary_checks"][-1]
    assert last["status"] == "not_verified"
    assert last["reason"] == "report_boundary_limit_exceeded"
    assert last["geometric_area_drawing_units_squared"] is None


def test_report_preserves_invalid_boundary_and_exposes_handle():
    result = build_architectural_report({"schema_version": "cad-ir/v2", "sections": {
        "entities": {"items": [{"handle": "P1", "entity_type": "AcDbPolyline",
                                  "layer": "A-SLAB", "geometry": contour(
                                      [[0, 0], [10, 8], [0, 8], [10, 0]])}]}}})
    assert result["boundary_checks"][0]["handle"] == "P1"
    assert result["boundary_checks"][0]["status"] == "invalid"
    assert result["candidates"][0]["boundary_check"]["status"] == "invalid"
    assert not result["structural_design_ready"]
