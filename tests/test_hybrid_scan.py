from types import SimpleNamespace

from src import cad_controller
from src.cad_controller import CADController


def controller():
    return object.__new__(CADController)


def entity(**extra):
    return SimpleNamespace(GetBoundingBox=lambda: ((1.0, 2.0, 0.0), (3.0, 4.0, 0.0)), **extra)


BLOCK = {"handle": "3A", "type": "AcDbBlockReference", "name": "BlockReference", "layer": "A-DOOR", "color": 3,
         "linetype": "ByLayer", "attributes": [{"Handle": "3B", "TagString": "NUM", "TextString": "D7", "Invisible": False}],
         "geometry": {"block_name": "DOOR", "insertion_point": [200.0, 0.0, 0.0],
                      "insertion_point_coordinate_system": "WCS", "normal": [0.0, 0.0, 1.0], "rotation": 0.5,
                      "rotation_unit": "radian", "x_scale": 1.0, "y_scale": 1.0, "z_scale": 1.0, "visible": True}}


def test_block_record_takes_dxf_fields_and_only_bbox_names_and_constants_from_com(monkeypatch):
    monkeypatch.setattr(cad_controller.win32com.client, "Dispatch", lambda obj: obj)  # other tests may stub win32com
    const = SimpleNamespace(Handle="C1", TagString="CONST", TextString="C", Invisible=False)
    ent = entity(EffectiveName="DOOR_DYN", IsDynamicBlock=True, GetConstantAttributes=lambda: (const,))
    document = SimpleNamespace(Blocks=SimpleNamespace(Item=lambda name: (_ for _ in ()).throw(KeyError(name))))
    info = controller()._hybrid_scan_record(document, ent, 4, BLOCK, False, False, True, True, {})
    assert info["index"] == 4 and info["handle"] == "3A" and info["color"] == 3 and info["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert info["effective_name"] == "DOOR_DYN" and info["is_dynamic_block"] is True and info["block_name"] == "DOOR"
    assert info["insertion_point"] == [200.0, 0.0, 0.0] and info["rotation"] == 0.5 and info["visible"] is True
    items = info["block_attributes"]["items"]
    assert [(i["kind"], i["tag"], i["text"]) for i in items] == [("reference", "NUM", "D7"), ("constant_definition", "CONST", "C")]
    assert info["block_attributes"]["status"] == "complete"


def test_minimal_records_skip_geometry_and_missing_geometry_falls_back_to_com():
    hatch = {"handle": "43", "type": "AcDbHatch", "name": "Hatch", "layer": "H", "color": 256, "linetype": "ByLayer",
             "geometry": None}
    info = controller()._hybrid_scan_record(None, entity(), 0, hatch, False, False, True, True, {})
    assert info == {"index": 0, "handle": "43", "type": "AcDbHatch", "name": "Hatch", "layer": "H",
                    "bbox": [1.0, 2.0, 3.0, 4.0]}
    no_geometry = {**BLOCK, "geometry": None}
    assert controller()._hybrid_scan_record(None, entity(), 0, no_geometry, False, False, True, True, {}) is None
    # Without geometry capture a block needs no geometry, so DXF still covers it.
    plain = controller()._hybrid_scan_record(None, entity(), 0, no_geometry, False, False, False, False, {})
    assert plain == {"index": 0, "handle": "3A", "type": "AcDbBlockReference", "name": "BlockReference", "layer": "A-DOOR"}
    text = {"handle": "40", "type": "AcDbText", "name": "Text", "layer": "0", "color": 1, "linetype": "ByLayer",
            "geometry": {"text": "Room"}}
    info = controller()._hybrid_scan_record(None, entity(), 0, text, True, True, False, False, {})
    assert info["text"] == "Room" and info["color"] == 1 and "bbox" not in info
