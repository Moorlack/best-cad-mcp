import pytest

from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.quantities import build_quantity_summary


def test_quantity_summary_sums_segments_openings_and_loops():
    walls = {"segments": [
        {"axis_wcs": [[0, 0, 0], [100, 0, 0]], "thickness_drawing_units": {"mean": 8.0}},
        {"axis_wcs": [[0, 10, 0], [0, 60, 0]], "thickness_drawing_units": {"mean": 8.0}},
        {"axis_wcs": [[0, 0, 0], [0, 30, 0]], "thickness_drawing_units": {"mean": 12.0}}],
        "openings": {"openings": [{"category": "door", "opening_width_candidate_drawing_units": 36.0},
                                  {"category": "door", "opening_width_candidate_drawing_units": 40.0},
                                  {"category": "window"}]},
        "room_loops": {"loops": [{"area_drawing_units_squared": 100.0, "net_area_drawing_units_squared": 80.0},
                                 {"area_drawing_units_squared": 50.0, "net_area_drawing_units_squared": None}]}}
    summary = build_quantity_summary(walls, [{"category": "wall"}, {"category": "door"}, {"category": "wall"}])
    assert summary["walls"]["total_axis_length"] == pytest.approx(180.0)
    assert summary["walls"]["by_thickness"][0] == {"thickness": 8.0, "segments": 2, "axis_length": pytest.approx(150.0)}
    assert summary["openings"]["count"] == 3 and summary["openings"]["by_category"]["door"] == {
        "count": 2, "min_width": 36.0, "max_width": 40.0}
    assert summary["enclosed_loops"] == {"count": 2, "total_net_area": 80.0, "total_axis_area": 150.0}
    assert summary["candidates_by_category"] == {"door": 1, "wall": 2}
    assert summary["status"] == "geometric_candidates_not_a_verified_takeoff"


def test_quantity_summary_is_present_even_without_wall_pairing():
    empty = build_quantity_summary({}, [])
    assert empty["walls"]["segment_count"] == 0 and empty["enclosed_loops"]["total_net_area"] is None
    ir = {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg", "units": "mm"},
          "sections": {"entities": {"total": 0, "items": []}}}
    assert build_architectural_report(ir)["quantity_summary"]["walls"]["segment_count"] == 0
