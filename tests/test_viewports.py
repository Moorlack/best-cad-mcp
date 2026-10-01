import asyncio
import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from mcp import Client

from src import server
from src.cad_controller import CADController
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.layer_visibility import parse_mview_xdata, split_by_view, viewport_window
from tests.test_thickness_estimate import plan

XDATA = ([1001, 1000, 1002, 1070, 1010, 1010, 1040, 1040, 1040, 1040, 1040, 1040, 1040, 1070, 1002, 1003, 1003, 1002, 1002],
         ["ACAD", "MVIEW", "{", 16, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.0, 1800.0, 440.0, -640.0, 50.0, 0.0, 0.0, 0,
          "{", "Base|1_Wall", "PS_Annot", "}", "}"])


def test_mview_xdata_gives_the_view_and_frozen_layers():
    view = parse_mview_xdata(*XDATA)
    assert view["view_height"] == 1800.0 and view["view_center"] == [440.0, -640.0]
    assert view["frozen_layers"] == ["Base|1_Wall", "PS_Annot"]
    assert viewport_window(view, 15.0, 18.0) == pytest.approx([440 - 750, -640 - 900, 440 + 750, -640 + 900])
    assert parse_mview_xdata([1001], ["ACAD"]) is None
    twisted = dict(view, twist=math.pi / 2)
    assert viewport_window(twisted, 15.0, 18.0) == pytest.approx([440 - 900, -640 - 750, 440 + 900, -640 + 750])
    assert viewport_window(dict(view, direction=[1.0, 0.0, 0.0]), 15.0, 18.0) is None


def test_split_by_view_drops_frozen_layers_and_entities_outside_the_window():
    entities = [{"layer": "base|1_wall", "bbox": {"min": [0, 0], "max": [1, 1]}},
                {"layer": "A", "bbox": {"min": [500, 500], "max": [600, 600]}},
                {"layer": "A", "bbox": {"min": [5, 5], "max": [6, 6]}}, {"layer": "A"}]
    shown, stats = split_by_view(entities, {"frozen_layers": ["Base|1_Wall"], "window": [0, 0, 100, 100]})
    assert len(shown) == 2 and stats == {"frozen_in_viewport": 1, "outside_viewport": 1}


def test_architecture_reports_the_viewport_scope():
    ir = plan()
    ir["sections"]["entities"]["items"].append(
        {"handle": "Z", "entity_type": "AcDbLine", "layer": "A-WALL", "bbox": {"min": [90000, 0], "max": [90100, 0]},
         "geometry": {"start": [90000, 0, 0], "end": [90100, 0, 0]}})
    vf = {"handle": "27128", "layout": "Sheet", "window": [-1000, -1000, 11000, 6000], "frozen_layers": []}
    report = build_architectural_report(ir, wall_thickness_range="auto", view_filter=vf)
    scope = report["coverage"]["viewport_scope"]
    assert scope["handle"] == "27128" and scope["outside_viewport"] == 1
    assert any(i["code"] == "viewport_scope_applied" for i in report["issues"])
    assert build_architectural_report(ir)["coverage"]["viewport_scope"] is None


def test_controller_lists_viewports_skipping_the_paper_space_one():
    def vp(handle, xdata):
        return SimpleNamespace(ObjectName="AcDbViewport", Handle=handle, Layer="VP", Center=(7, 9, 0), Width=15.0,
                               Height=18.0, CustomScale=1 / 96, ViewportOn=True, Clipped=False,
                               GetXData=lambda app: xdata)
    entities = [vp("1", XDATA), SimpleNamespace(ObjectName="AcDbLine"), vp("2710A", XDATA), vp("BAD", (None, None))]
    block = SimpleNamespace(Count=len(entities), Item=entities.__getitem__)
    layouts = [SimpleNamespace(ModelType=True, Name="Model"), SimpleNamespace(ModelType=False, Name="Sheet", Block=block)]
    ctrl = object.__new__(CADController)
    ctrl.doc = SimpleNamespace(Layouts=SimpleNamespace(Count=2, Item=layouts.__getitem__))
    with patch.object(CADController, "_ensure_connected"), patch("src.cad_controller.win32com.client.Dispatch", lambda e: e):
        ctrl.acad = SimpleNamespace(Documents=SimpleNamespace(Count=1), ActiveDocument=ctrl.doc)
        result = ctrl.layout_viewports()
    sheet = result["layouts"][0]
    assert sheet["name"] == "Sheet" and [v["handle"] for v in sheet["viewports"]] == ["2710A", "BAD"]
    assert sheet["viewports"][0]["status"] == "ok" and sheet["viewports"][0]["frozen_layers"] == ["Base|1_Wall", "PS_Annot"]
    assert sheet["viewports"][1]["status"] == "view_data_not_available"


def test_native_mcp_passes_the_viewport_filter():
    listing = {"success": True, "layouts": [{"name": "Sheet", "viewports": [
        {"handle": "2710A", "status": "ok", "model_window": [0, 0, 10, 10], "frozen_layers": ["X"]}]}]}

    async def exercise(handle):
        async with Client(server.mcp, raise_exceptions=True, mode="2026-07-28") as client:
            return (await client.call_tool("analyze_architectural_drawing", {"viewport_handle": handle})).model_dump(
                by_alias=True, mode="json")

    with patch.object(server.query_tools.ctrl, "layout_viewports", return_value=listing), \
         patch.object(server.understanding_architecture, "analyze_architectural_drawing",
                      return_value={"ok": True}) as analyze:
        asyncio.run(exercise("2710a"))
        missing = asyncio.run(exercise("FFFF"))
    assert analyze.call_args.kwargs["view_filter"] == {"handle": "2710A", "layout": "Sheet", "window": [0, 0, 10, 10],
                                                       "frozen_layers": ["X"]}
    assert "No layout viewport" in str(missing["structuredContent"])


def test_wmf_export_switches_to_the_model_tab_and_back():
    model, sheet = SimpleNamespace(Name="Model"), SimpleNamespace(Name="Sheet")
    doc = SimpleNamespace(ActiveSpace=0, ActiveLayout=sheet, Layouts=SimpleNamespace(Item=lambda name: model))
    ctrl = object.__new__(CADController)
    ctrl.doc = doc
    seen = []
    with ctrl._model_tab_for_export("WMF"):
        seen.append(doc.ActiveLayout)
    assert seen == [model] and doc.ActiveLayout is sheet and "Model tab" in ctrl.last_export_notes[0]
    doc.ActiveSpace = 1
    ctrl.last_export_notes = []
    with ctrl._model_tab_for_export("WMF"):
        assert doc.ActiveLayout is sheet
    with ctrl._model_tab_for_export("PDF"):
        pass
    assert ctrl.last_export_notes == []
