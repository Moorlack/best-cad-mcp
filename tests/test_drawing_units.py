from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.cad_controller import CADController
from src.cad_database import CADDatabase
from src.cad_tools import query_tools
from src.cad_understanding.drawing_units import unit_metadata
from src.cad_understanding.ir_builder import build_drawing_ir
from src.cad_understanding.architecture import build_architectural_report


@pytest.mark.parametrize("value,units", [(1, "in"), (2, "ft"), (4, "mm"),
                                        (6, "m"), (21, "us_survey_ft"),
                                        (0, "unitless"), (-1, "unknown"),
                                        (25, "unknown"), (True, "unknown"),
                                        (1.5, "unknown"), ("1", "unknown")])
def test_declared_units_are_never_verified(value, units):
    result = unit_metadata(value, captured=True)
    assert result["units"] == units
    assert result["geometry_scale_verified"] is False
    assert result["source"] == "AutoCAD.INSUNITS"


def test_persisted_units_scoped_and_cleared(tmp_path):
    path = str(tmp_path / "cad.db")
    db = CADDatabase(path)
    db.configure_context(workspace_id="one", drawing_id="a")
    db.set_drawing_units(unit_metadata(1, captured=True))
    db.configure_context(drawing_id="b")
    assert db.get_drawing_units()["units"] == "unknown"
    db.set_drawing_units(unit_metadata(6, captured=True))
    db.configure_context(workspace_id="two", drawing_id="a")
    assert db.get_drawing_units()["units"] == "unknown"
    reopened = CADDatabase(path)
    reopened.configure_context(workspace_id="one", drawing_id="a")
    assert build_drawing_ir(database=reopened)["drawing"]["units"] == "in"
    reopened.clear_entities()
    assert reopened.get_drawing_units()["units"] == "unknown"


def test_scan_reads_units_from_same_document_and_refreshes_cache(tmp_path, monkeypatch):
    db = CADDatabase(str(tmp_path / "cad.db"))
    doc = SimpleNamespace(Name="a.dwg", FullName="C:/a.dwg",
                          ModelSpace=SimpleNamespace(Count=0),
                          GetVariable=MagicMock(return_value=1))
    ctrl = object.__new__(CADController)
    ctrl.doc = doc
    ctrl.acad = SimpleNamespace(Documents=SimpleNamespace(Count=1), ActiveDocument=doc)
    monkeypatch.setattr(query_tools, "db", db)
    monkeypatch.setattr(query_tools, "ctrl", ctrl)
    query_tools.scan_all_entities()
    drawing = build_drawing_ir(database=db)["drawing"]
    assert drawing["units"] == "in"
    assert drawing["name"] == "a.dwg"
    assert drawing["units_metadata"]["captured_at"]
    report = build_architectural_report(build_drawing_ir(database=db))
    assert "geometry_scale_unverified" in {i["code"] for i in report["issues"]}
    doc.GetVariable.side_effect = RuntimeError("unavailable")
    query_tools.scan_all_entities(clear_db=False)
    assert db.get_drawing_units()["units"] == "unknown"
    assert db.get_drawing_units()["geometry_scale_verified"] is False

    other = SimpleNamespace(Name="b.dwg", FullName="C:/b.dwg")

    def switch_active_document(_):
        ctrl.acad.ActiveDocument = other
        return 6

    doc.GetVariable.side_effect = switch_active_document
    query_tools.scan_all_entities()
    assert db.get_context().drawing_name == "a.dwg"
    assert db.get_drawing_units()["units"] == "m"


def test_failed_scan_does_not_clear_previous_snapshot(tmp_path, monkeypatch):
    db = CADDatabase(str(tmp_path / "cad.db"))
    db.set_drawing_units(unit_metadata(4, captured=True))
    db.upsert_entity("A", "Line", "AcDbLine")
    monkeypatch.setattr(query_tools, "db", db)
    monkeypatch.setattr(query_tools, "ctrl", SimpleNamespace(
        scan_model_space=lambda *a, **kw: {"error": "disconnected"}))
    with pytest.raises(RuntimeError, match="disconnected"):
        query_tools.scan_all_entities()
    assert db.get_entity("A")
    assert db.get_drawing_units()["units"] == "mm"
