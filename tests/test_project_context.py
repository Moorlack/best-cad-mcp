import pytest

from src.cad_database import CADDatabase
from src.cad_understanding.architecture import analyze_architectural_drawing
from src.cad_understanding.drawing_units import unit_metadata
from src.cad_understanding.project_card import update_project_card, get_project_card_history


def setup(tmp_path, units="in", status="confirmed", insunits=1):
    db = CADDatabase(str(tmp_path / "cad.db"))
    db.configure_context(workspace_id="workspace-a", drawing_name="a.dwg")
    db.set_drawing_units(unit_metadata(insunits, captured=True))
    field = {"value": units if status != "missing" else None, "status": status, "source": "synthetic test"}
    assert update_project_card("project-a", {"units": field}, 0, "test", database=db)["ok"]
    return db


@pytest.mark.parametrize("unit,status,insunits,match,warnings", [
    ("in", "confirmed", 1, True, []),
    ("m", "confirmed", 1, False, ["project_units_mismatch"]),
    ("in", "assumed", 1, True, ["project_units_unconfirmed"]),
    ("m", "assumed", 1, False, ["project_units_unconfirmed", "project_units_mismatch"]),
    (None, "missing", 1, None, ["project_units_missing"]),
    ("in", "confirmed", 0, None, ["drawing_units_unavailable_for_project_check"]),
    ("ft", "confirmed", 21, False, ["project_units_mismatch"]),
])
def test_unit_comparison_never_confirms_scale_or_mutates_card(tmp_path, unit, status, insunits, match, warnings):
    db = setup(tmp_path, unit, status, insunits)
    history_before = get_project_card_history("project-a", database=db)
    report = analyze_architectural_drawing(database=db, project_id="project-a")["data"]["report"]
    ctx = report["project_context"]
    assert ctx["declared_units_match"] is match
    assert ctx["warnings"] == warnings
    assert not ctx["geometry_scale_verified"]
    assert not ctx["engineering_design_ready"]
    assert not report["structural_design_ready"]
    assert ctx["revision"] == 1
    assert ctx["readiness"]["gates"]["geometry_review"]["missing"]
    assert get_project_card_history("project-a", database=db) == history_before
    assert all(w in {i["code"] for i in report["issues"]} for w in warnings)


def test_explicit_project_selection_required_and_workspace_isolated(tmp_path):
    db = setup(tmp_path)
    assert "project_context" not in analyze_architectural_drawing(database=db)["data"]["report"]
    assert not analyze_architectural_drawing(database=db, project_id="missing")["ok"]
    assert not analyze_architectural_drawing(database=db, project_id="")["ok"]
    db.configure_context(workspace_id="workspace-b")
    assert not analyze_architectural_drawing(database=db, project_id="project-a")["ok"]


def test_reads_latest_revision_and_current_drawing_cache(tmp_path):
    db = setup(tmp_path)
    assert update_project_card("project-a", {"units": {"value": "m", "status": "confirmed", "source": "test"}},
                               1, "new units", database=db)["ok"]
    ctx = analyze_architectural_drawing(database=db, project_id="project-a")["data"]["report"]["project_context"]
    assert ctx["revision"] == 2 and ctx["declared_units_match"] is False
    db.activate_drawing(name="other.dwg")
    ctx = analyze_architectural_drawing(database=db, project_id="project-a")["data"]["report"]["project_context"]
    assert ctx["declared_units_match"] is None
    assert ctx["drawing_units"] == "unknown"
