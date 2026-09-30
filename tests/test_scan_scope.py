from unittest.mock import patch

from src import cad_controller
from src.cad_tools import query_tools


class _Layer:
    def __init__(self, name):
        self.Name = name


class _Layers:
    def __init__(self, names):
        self.items, self.Count = [_Layer(n) for n in names], len(names)

    def Item(self, index):
        return self.items[index]


class _Entity:
    def __init__(self, layer):
        self.Layer = layer


class _Space:
    def __init__(self, layers):
        self.items, self.Count = [_Entity(layer) for layer in layers], len(layers)

    def Item(self, index):
        return self.items[index]


class _Doc:
    def __init__(self, layer_names, entity_layers, active_space=2):
        self.Layers, self.ModelSpace, self.ActiveSpace = _Layers(layer_names), _Space(entity_layers), active_space


def _controller():
    return cad_controller.CADController.__new__(cad_controller.CADController)


def test_architectural_layers_use_the_multilingual_vocabulary():
    doc = _Doc(["0", "Defpoints", "АР_Стены", "A-DOOR", "S-COLS", "Text", "Wallpaper", "Окна"], [])
    assert _controller()._architectural_layer_names(doc) == ["АР_Стены", "A-DOOR", "S-COLS", "Окна"]


def test_layer_selection_falls_back_to_matching_names_when_not_in_model_space():
    doc = _Doc([], ["A-WALL", "a-wall-ext", "TEXT", "A-DOOR", "Стены"], active_space=2)
    items, count = _controller()._select_layer_entities(doc, ["A-WALL*", "стены"])
    assert count == 3 and [item.Layer for item in items] == ["A-WALL", "a-wall-ext", "Стены"]


def test_scan_messages_report_layer_limit_and_time_budget():
    with patch.object(query_tools, "ctrl") as ctrl, patch.object(query_tools, "db") as db:
        ctrl.get_document_info.return_value = {"name": "a.dwg", "full_name": r"C:\a.dwg"}
        ctrl.scan_model_space.return_value = {
            "entities": [{"handle": "H1", "type": "AcDbLine", "name": "Line", "layer": "A-WALL"}],
            "type_stats": {"AcDbLine": 1}, "total_available": 40, "scanned": 1, "truncated": True,
            "time_budget_exceeded": True, "layer_filter": ["A-WALL*"], "detail_level": "minimal"}
        db.upsert_entities_batch.return_value = 1
        text = query_tools.scan_all_entities(layers=["A-WALL*"], max_seconds=5)
    assert "Scan limited to layers: A-WALL*" in text
    assert "Stopped after 5 s with 1 of 40 entities" in text
    db.set_scan_fingerprint.assert_called_with(None)  # a partial read never becomes a freshness baseline
