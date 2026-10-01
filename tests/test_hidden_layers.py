from types import SimpleNamespace

from src.cad_controller import CADController
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.geometry_analysis import build_geometry_report
from src.cad_understanding.layer_visibility import on_hidden_layer, split_hidden
from src.cad_understanding.plan_summary import build_plan_summary
from src.cad_understanding.view_grounding import COMPACT_MAX_OVERLAY_ITEMS, compact_export_for_model
from tests.test_thickness_estimate import line, plan


def with_hidden_storey():
    ir = plan()
    # A second storey drawn over the first on a frozen layer: same walls, shifted a little.
    extra = [dict(line(f"H{e['handle']}", [x + 37 for x in e["geometry"]["start"]],
                       [x + 37 for x in e["geometry"]["end"]], layer="1_A-WALL"),
                  geometry={"start": [x + 37 for x in e["geometry"]["start"]],
                            "end": [x + 37 for x in e["geometry"]["end"]], "layer_state": "frozen"})
             for e in ir["sections"]["entities"]["items"]]
    ir["sections"]["entities"]["items"] += extra
    ir["sections"]["entities"]["total"] += len(extra)
    return ir, len(extra)


def test_helpers_read_dict_and_json_geometry():
    assert on_hidden_layer({"geometry": {"layer_state": "off"}})
    assert on_hidden_layer({"geometry": '{"layer_state": "frozen"}'})
    assert not on_hidden_layer({"geometry": "not json"}) and not on_hidden_layer({})
    shown, hidden = split_hidden([{"layer": "A", "geometry": {"layer_state": "off"}}, {"layer": "B", "geometry": {}}])
    assert [e["layer"] for e in shown] == ["B"] and hidden == {"A": 1}


def test_architecture_skips_hidden_storeys_unless_asked():
    ir, extra = with_hidden_storey()
    report = build_architectural_report(ir, wall_thickness_range="auto", wall_opening_max_width="auto")
    assert report["wall_segment_candidates"]["segment_count"] == 6
    assert report["coverage"]["hidden_layer_entities_skipped"] == extra
    assert report["coverage"]["hidden_layers_skipped"] == {"1_A-WALL": extra}
    assert report["coverage"]["truncated"] is False
    issue = next(i for i in report["issues"] if i["code"] == "hidden_layer_entities_skipped")
    assert "1_A-WALL" in issue["message"]
    assert f"{extra} entities on frozen/off layers skipped" in build_plan_summary(report)["text"]
    mixed = build_architectural_report(ir, wall_thickness_range="auto", wall_opening_max_width="auto",
                                       include_hidden_layers=True)
    assert mixed["wall_segment_candidates"]["segment_count"] > 6
    assert mixed["coverage"]["hidden_layer_entities_skipped"] == 0


def test_geometry_report_skips_hidden_entities():
    ir, extra = with_hidden_storey()
    report = build_geometry_report(ir)
    assert report["coverage"]["hidden_layer_entities_skipped"] == extra
    assert report["coverage"]["selected_entities"] == len(ir["sections"]["entities"]["items"]) - extra
    assert build_geometry_report(ir, include_hidden_layers=True)["coverage"]["hidden_layer_entities_skipped"] == 0


def test_scan_reads_frozen_and_off_layers():
    layers = [SimpleNamespace(Name="0", Freeze=False, LayerOn=True),
              SimpleNamespace(Name="1_Wall", Freeze=True, LayerOn=True),
              SimpleNamespace(Name="Notes", Freeze=False, LayerOn=False)]
    document = SimpleNamespace(Layers=SimpleNamespace(Count=3, Item=lambda i: layers[i]))
    states = object.__new__(CADController)._hidden_layer_states(document)
    assert states == {"1_WALL": "frozen", "NOTES": "off"}


def test_compact_render_caps_overlay_lists_keeping_the_largest_items():
    items = [{"overlay_id": f"E{i}", "pixel_bbox": [0, 0, i, i]} for i in range(300)]
    export = {"ok": True, "data": {"snapshot": {"overlay_items": items, "context_json_path": "x.json"}}}
    slim = compact_export_for_model(export)["data"]["snapshot"]
    assert len(slim["overlay_items"]) == COMPACT_MAX_OVERLAY_ITEMS
    assert slim["overlay_items"][-1]["overlay_id"] == "E299" and slim["overlay_items"][0]["overlay_id"] == "E180"
    assert slim["compact"]["truncated_overlay_lists"] == {"overlay_items": {"total": 300, "returned": 120}}
    assert len(export["data"]["snapshot"]["overlay_items"]) == 300  # the stored snapshot is untouched


def test_compact_render_drops_long_paths_and_respects_a_text_budget():
    path = [[float(i), 0.0] for i in range(500)]
    items = [{"overlay_id": f"H{i}", "pixel_bbox": [0, 0, 10, 10], "world_path": path, "pixel_path": path}
             for i in range(60)]
    slim = compact_export_for_model({"ok": True, "data": {"snapshot": {"overlay_items": items}}})["data"]["snapshot"]
    first = slim["overlay_items"][0]
    assert "world_path" not in first and first["world_path_points"] == 500 and first["pixel_path_points"] == 500
    big = [{"overlay_id": f"T{i}", "pixel_bbox": [0, 0, i + 1, i + 1], "note": "x" * 900} for i in range(100)]
    slim = compact_export_for_model({"ok": True, "data": {"snapshot": {"overlay_items": big}}})["data"]["snapshot"]
    import json
    assert len(json.dumps(slim["overlay_items"])) <= 30000
    assert slim["compact"]["truncated_overlay_lists"]["overlay_items"]["total"] == 100
