from unittest.mock import MagicMock

from src.cad_tools import edit_tools
from src.cad_understanding.plan import parse_tool_result_handles


def test_move_returns_handle_for_plan_postconditions(monkeypatch):
    ctrl = MagicMock()
    ctrl.move_entity.return_value = {"success": True}
    db = MagicMock()
    db.get_entity.return_value = None
    monkeypatch.setattr(edit_tools, "ctrl", ctrl)
    monkeypatch.setattr(edit_tools, "db", db)

    result = edit_tools.move_entity("16E", [0, 0, 0], [-5, 0, 0])

    assert parse_tool_result_handles(result) == ["16E"]
    ctrl.move_entity.assert_called_once_with("16E", [0, 0, 0], [-5, 0, 0])


def test_failed_move_does_not_advertise_a_captured_handle(monkeypatch):
    ctrl = MagicMock()
    ctrl.move_entity.return_value = {"success": False, "message": "busy"}
    db = MagicMock()
    monkeypatch.setattr(edit_tools, "ctrl", ctrl)
    monkeypatch.setattr(edit_tools, "db", db)

    result = edit_tools.move_entity("16E", [0, 0, 0], [-5, 0, 0])

    assert parse_tool_result_handles(result) == []
    db.upsert_entity.assert_not_called()
