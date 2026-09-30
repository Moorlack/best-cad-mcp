from unittest.mock import MagicMock, patch

import pytest

from src.cad_controller import CADController


@pytest.fixture
def controller():
    # Bypass the shared singleton so these tests cannot change other tests' controllers.
    instance = object.__new__(CADController)
    instance.doc = MagicMock()
    instance.doc.Name = "Drawing1.dwg"
    instance.doc.ModelSpace.Count = 0
    instance.create_drawing = MagicMock(return_value={"success": True})
    instance._set_file_dialog_vars = MagicMock(return_value={"FILEDIA": 1})
    instance._prepare_application_for_file_operation = MagicMock()
    instance._restore_vars = MagicMock()
    instance._refresh_active_document = MagicMock()
    return instance


def test_dxf_open_fails_before_touching_autocad(controller):
    with patch.object(controller, "_ensure_connected") as connect:
        result = controller.open_drawing("fixture.DXF")
    assert not result["success"]
    assert "import_dxf" in result["message"]
    connect.assert_not_called()


def test_import_permission_and_file_checks_precede_new_document(controller, tmp_path):
    source = tmp_path / "source.dxf"
    source.write_text("fixture")
    assert not controller.import_dxf(str(source))["success"]
    assert not controller.import_dxf(str(source), allow_modify=1)["success"]
    assert not controller.import_dxf(str(tmp_path / "missing.dxf"), True)["success"]
    controller.create_drawing.assert_not_called()


def test_native_import_null_return_is_success(controller, tmp_path):
    source = tmp_path / "source.DXF"
    source.write_text("fixture")
    document = controller.doc

    def do_import(*_args):
        document.ModelSpace.Count = 91
        return None

    document.Import.side_effect = do_import
    with patch("src.cad_controller.to_variant_point", return_value=(0, 0, 0)):
        result = controller.import_dxf(str(source), True)
    assert result["success"]
    assert result["entity_count"] == 91
    document.Import.assert_called_once_with(str(source), (0, 0, 0), 1.0)
    document.Save.assert_not_called()
    document.Close.assert_not_called()
    controller._restore_vars.assert_called_once_with({"FILEDIA": 1})
    assert source.read_text() == "fixture"


def test_creation_failure_does_not_import(controller, tmp_path):
    source = tmp_path / "source.dxf"
    source.write_text("fixture")
    controller.create_drawing.return_value = {"success": False, "message": "No connection"}
    assert not controller.import_dxf(str(source), True)["success"]
    controller.doc.Import.assert_not_called()


def test_nonempty_template_is_not_modified(controller, tmp_path):
    source = tmp_path / "source.dxf"
    source.write_text("fixture")
    controller.doc.ModelSpace.Count = 2
    assert not controller.import_dxf(str(source), True)["success"]
    controller.doc.Import.assert_not_called()


def test_import_failure_preserves_document_and_restores_settings(controller, tmp_path):
    source = tmp_path / "source.dxf"
    source.write_text("fixture")
    controller.doc.Import.side_effect = RuntimeError("bad DXF")
    with patch("src.cad_controller.to_variant_point", return_value=(0, 0, 0)):
        result = controller.import_dxf(str(source), True)
    assert not result["success"]
    assert "partial" in result["warning"]
    controller._restore_vars.assert_called_once_with({"FILEDIA": 1})
    controller.doc.Close.assert_not_called()


def test_tool_does_not_sync_database_after_failed_import(monkeypatch):
    from src.cad_tools import file_tools

    ctrl = MagicMock()
    ctrl.import_dxf.return_value = {"success": False, "message": "import failed"}
    monkeypatch.setattr(file_tools, "ctrl", ctrl)
    with patch.object(file_tools, "_sync_db_drawing_from_info") as sync:
        assert file_tools.import_dxf("example.dxf", True)["ok"] is False
    sync.assert_not_called()
