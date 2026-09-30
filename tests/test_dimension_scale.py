import math

import pytest

from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.dimension_scale import check_dimension_scale


def dim(handle, measurement, p1, p2, rotation=0.0, kind="AcDbRotatedDimension", **extra):
    geometry = {"measurement": measurement, "xline1_point": list(p1), "xline2_point": list(p2),
                "text_override": "", "dimension_linear_factor": 1.0}
    if kind == "AcDbRotatedDimension":
        geometry["dimension_rotation"] = rotation
    geometry.update(extra)
    return {"handle": handle, "entity_type": kind, "layer": "DIM", "geometry": geometry}


def test_rotated_and_aligned_dimensions_agree_with_their_points():
    entities = [dim("A", 1424, (0, 0, 0), (1424, 0, 0)),
                dim("B", 500, (0, 0, 0), (0, 500, 0), rotation=math.pi / 2),
                dim("C", 5, (0, 0, 0), (3, 4, 0), kind="AcDbAlignedDimension"),
                dim("D", 100, (0, 0, 0), (100, 50, 0), rotation=0.0)]  # measured along X only
    result = check_dimension_scale(entities)
    assert result["status"] == "agrees" and result["checked"] == 4 and result["differ"] == 0
    assert result["median_ratio_measured_to_drawn"] == pytest.approx(1.0) and result["units_verified"] is False


def test_mismatch_overrides_factors_and_missing_data_are_reported():
    entities = [dim("A", 1000, (0, 0, 0), (100, 0, 0)),
                dim("B", 100, (0, 0, 0), (100, 0, 0)),
                dim("C", 100, (0, 0, 0), (100, 0, 0), text_override="~100"),
                dim("D", 100, (0, 0, 0), (100, 0, 0), dimension_linear_factor=25.4),
                {"handle": "E", "entity_type": "AcDbRotatedDimension", "geometry": {}},
                {"handle": "L", "entity_type": "AcDbLine", "geometry": {"start": [0, 0], "end": [1, 0]}}]
    result = check_dimension_scale(entities)
    assert result["status"] == "mixed" and result["checked"] == 2 and result["differ"] == 1
    assert result["skipped"] == {"dimension_data_not_captured": 1, "linear_scale_factor_not_one": 1,
                                 "text_overridden": 1}
    assert result["items"][0]["handle"] == "A" and result["items"][0]["ratio"] == pytest.approx(10.0)
    assert check_dimension_scale([])["status"] == "no_linear_dimensions_checked"


def _ir(entities):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg", "units": "mm"},
            "sections": {"entities": {"total": len(entities), "items": entities}}}


def test_architectural_report_carries_dimension_scale_issue_and_result():
    good = build_architectural_report(_ir([dim("A", 100, (0, 0, 0), (100, 0, 0))]))
    assert good["dimension_scale_check"]["status"] == "agrees"
    assert "dimension_scale_consistent" in {i["code"] for i in good["issues"]}
    bad = build_architectural_report(_ir([dim("A", 100, (0, 0, 0), (200, 0, 0))]))
    codes = {i["code"]: i for i in bad["issues"]}
    assert codes["dimension_scale_mismatch"]["handles"] == ["A"]
    assert build_architectural_report(_ir([]))["dimension_scale_check"]["checked"] == 0


def test_stored_rotation_that_does_not_match_the_measured_direction_is_tolerated():
    # Vertical distance measured, stored rotation 0: seen on an imported drawing.
    result = check_dimension_scale([dim("V", 1130, (0, 8033, 0), (0, 9163, 0), rotation=0.0)])
    assert result["status"] == "agrees"
    assert result["items"][0]["axis"] == "perpendicular_to_stored_rotation"
    # Neither direction matches: a real difference.
    wrong = check_dimension_scale([dim("W", 500, (0, 0, 0), (0, 1130, 0), rotation=0.0)])
    assert wrong["status"] == "differs"
