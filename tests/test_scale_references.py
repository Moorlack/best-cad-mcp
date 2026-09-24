from copy import deepcopy

import pytest

from src.cad_understanding.scale_references import check_scale_references, validate_references
from src.cad_understanding.architecture import analyze_architectural_drawing
from src.cad_understanding.drawing_units import unit_metadata
from src.cad_database import CADDatabase


def reference(length=1, units="ft", handle="A1"):
    return {"handle": handle, "length": length, "units": units, "source": "synthetic independent control"}


def snapshot():
    return {"drawing": {"units": "in", "units_metadata": unit_metadata(1, captured=True)},
            "sections": {"entities": {"items": [{"handle": "A1", "entity_type": "AcDbLine",
                                                   "geometry": {"start": [0, 0, 0], "end": [12, 0, 0],
                                                                "length": 999}}]}}}


@pytest.mark.parametrize("length,units,status", [
    (1, "ft", "agrees"), (12, "in", "agrees"), (304.8, "mm", "agrees"),
    (30.48, "cm", "agrees"), (0.3048, "m", "agrees"), (12, "m", "mismatch"),
])
def test_compare_from_endpoints_not_cached_length(length, units, status):
    original = snapshot()
    before = deepcopy(original)
    result = check_scale_references(original, [reference(length, units)])
    assert result["checks"][0]["status"] == status
    assert result["checks"][0]["measured_length_drawing_units"] == 12
    assert result["geometry_scale_verified"] is False
    assert original == before


@pytest.mark.parametrize("value", [0, -1, True, "12", float("nan"), float("inf"), 10**1000])
def test_invalid_reference_length_rejected(value):
    with pytest.raises(ValueError):
        validate_references([reference(value)])


def test_invalid_reference_metadata_and_limits():
    for refs in ([], [reference()] * 2, [reference(handle=str(i)) for i in range(21)],
                 [dict(reference(), source="")], [reference(units="yard")], [dict(reference(), extra=1)]):
        with pytest.raises(ValueError):
            validate_references(refs)


@pytest.mark.parametrize("case,reason", [
    ("missing", "handle_missing_from_snapshot"), ("duplicate", "ambiguous_handle"),
    ("dimension", "unsupported_entity_use_line"), ("unknown_units", "drawing_units_unknown_or_unsupported"),
    ("bad_endpoint", "missing_or_invalid_endpoints"), ("zero", "degenerate_or_out_of_range_length"),
])
def test_unverifiable_reference_is_not_mismatch_or_success(case, reason):
    ir = snapshot()
    items = ir["sections"]["entities"]["items"]
    if case == "missing":
        items.clear()
    elif case == "duplicate":
        items.append(deepcopy(items[0]))
    elif case == "dimension":
        items[0]["entity_type"] = "AcDbRotatedDimension"
    elif case == "unknown_units":
        ir["drawing"]["units_metadata"] = unit_metadata()
    elif case == "bad_endpoint":
        items[0]["geometry"]["end"] = [float("nan"), 0]
    else:
        items[0]["geometry"]["end"] = [0, 0, 0]
    r = check_scale_references(ir, [reference()])
    assert r["checks"][0]["status"] == "not_verified"
    assert r["checks"][0]["reason"] == reason
    assert r["all_references_agree"] is False


def test_sqlite_report_pipeline_with_3d_line_and_scope(tmp_path):
    db = CADDatabase(str(tmp_path / "cad.db"))
    db.activate_drawing(name="scale.dwg")
    db.set_drawing_units(unit_metadata(6, captured=True))
    db.upsert_entity("A1", "Line", "AcDbLine", geometry={"start": [0, 0, 0], "end": [0, 3, 4]})
    result = analyze_architectural_drawing(database=db, reference_lengths=[reference(500, "cm")])
    r = result["data"]["report"]
    assert r["scale_reference_check"]["all_references_agree"]
    assert r["scale_reference_check"]["checks"][0]["measured_length_drawing_units"] == 5
    assert r["structural_design_ready"] is False
    assert db.get_drawing_units()["geometry_scale_verified"] is False
    db.activate_drawing(name="other.dwg")
    result = analyze_architectural_drawing(database=db, reference_lengths=[reference()])
    assert "scale_reference_not_verified" in result["warnings"]
    assert not analyze_architectural_drawing(database=db, reference_lengths=[])["ok"]
