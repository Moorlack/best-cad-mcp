import math
from types import SimpleNamespace

import pytest

from src.cad_controller import CADController
from src.xref_transform import InsertTransform, place_xref_records


def test_identity_and_rotated_scaled_placement():
    assert InsertTransform([0, 0, 0]).identity
    t = InsertTransform([100, 50, 0], rotation=math.pi / 2, x_scale=2, y_scale=2)
    line = {"handle": "A1", "type": "AcDbLine", "layer": "Wall", "start": [0, 0, 0], "end": [10, 0, 0],
            "length": 10.0, "bbox": [0, 0, 10, 0]}
    out = t.record(line)
    assert out["start"] == [100.0, 50.0, 0.0] and out["end"] == pytest.approx([100.0, 70.0, 0.0])
    assert out["length"] == 20.0 and out["bbox"] == pytest.approx([100.0, 50.0, 100.0, 70.0])
    arc = {"center": [0, 0, 0], "radius": 5.0, "start_angle": 0.0, "end_angle": 1.0, "angle_unit": "radian",
           "start_parameter": 0.0, "end_parameter": 1.0, "parameter_unit": "radian"}
    out = t.record(arc)
    assert out["radius"] == 10.0 and out["start_angle"] == pytest.approx(math.pi / 2)
    assert out["end_parameter"] == pytest.approx(1.0 + math.pi / 2)
    ellipse = {"major_axis": [1, 0, 0], "start_angle": 0.0, "angle_unit": "degree",
               "start_parameter": 0.5, "parameter_unit": "radian"}
    out = t.record(ellipse)
    assert out["major_axis"] == pytest.approx([0.0, 2.0, 0.0]) and out["start_angle"] == pytest.approx(90.0)
    assert out["start_parameter"] == 0.5  # relative to the major axis
    block = {"insertion_point": [1, 0, 0], "rotation": 0.25, "x_scale": 1.5, "y_scale": 1.5, "z_scale": 1.0}
    out = t.record(block)
    assert out["insertion_point"] == pytest.approx([100.0, 52.0, 0.0]) and out["rotation"] == pytest.approx(0.25 + math.pi / 2)
    assert out["x_scale"] == 3.0 and out["z_scale"] == 1.0
    poly = {"vertices": [[0, 0, 3], [1, 0, 3]], "elevation": 3.0, "bulges": [1.0], "visual_path": [[0, 0, 3]]}
    out = t.record(poly)
    assert out["vertices"][1] == pytest.approx([100.0, 52.0, 3.0]) and out["bulges"] == [1.0] and out["elevation"] == 3.0


@pytest.mark.parametrize("kwargs", [{"x_scale": -1}, {"x_scale": 1, "y_scale": 2}, {"normal": [0, 0, -1]}])
def test_mirrored_non_uniform_or_tilted_inserts_are_refused(kwargs):
    with pytest.raises(ValueError):
        InsertTransform([0, 0, 0], **kwargs)


def test_placed_records_get_host_names_and_virtual_handles():
    records = [{"handle": "2A", "type": "AcDbBlockReference", "layer": "Door", "block_name": "D36",
                "insertion_point": [0, 0, 0], "layer_state": "frozen"}, {"error": "x"}]
    placed = place_xref_records(records, "Wall Base", "1F0", InsertTransform([10, 0, 0]))
    assert len(placed) == 1
    item = placed[0]
    assert item["handle"] == "1F0/2A" and item["layer"] == "Wall Base|Door" and item["block_name"] == "Wall Base|D36"
    assert item["xref"] == "Wall Base" and item["source_handle"] == "2A" and "layer_state" not in item
    assert item["insertion_point"] == [10.0, 0.0, 0.0]


def test_controller_scans_each_xref_file_once_and_reactivates_the_host(monkeypatch, tmp_path):
    xref_file = tmp_path / "Base.dwg"
    xref_file.write_bytes(b"")
    host = SimpleNamespace(FullName=str(tmp_path / "Sheet.dwg"), Name="Sheet.dwg")
    inserts = {"I1": SimpleNamespace(Name="Base", InsertionPoint=(0, 0, 0), Rotation=0.0, XScaleFactor=1.0,
                                     YScaleFactor=1.0, ZScaleFactor=1.0, Normal=(0, 0, 1)),
               "I2": SimpleNamespace(Name="Base", InsertionPoint=(1000, 0, 0), Rotation=0.0, XScaleFactor=1.0,
                                     YScaleFactor=1.0, ZScaleFactor=1.0, Normal=(0, 0, 1)),
               "B1": SimpleNamespace(Name="Chair", InsertionPoint=(0, 0, 0))}
    blocks = {"Base": SimpleNamespace(IsXRef=True, Path="Base.dwg"), "Chair": SimpleNamespace(IsXRef=False)}
    host.HandleToObject = inserts.__getitem__
    host.Blocks = SimpleNamespace(Item=blocks.__getitem__)
    ctrl = object.__new__(CADController)
    ctrl.acad = SimpleNamespace()
    calls, activated = [], []
    monkeypatch.setattr(ctrl, "_scan_xref_file", lambda path, limit, deadline, options: calls.append(path) or {
        "entities": [{"handle": "L1", "type": "AcDbLine", "layer": "Wall", "start": [0, 0, 0], "end": [5, 0, 0]}]})
    monkeypatch.setattr("src.autocad_instances.activate_document", lambda app, path: activated.append(path) or True)
    entities = [{"handle": h, "type": "AcDbBlockReference"} for h in ("I1", "I2", "B1")]
    records, report = ctrl._scan_xref_contents(host, entities, 100, None, {})
    assert calls == [str(xref_file)] and activated == [host.FullName] and ctrl.doc is host
    assert [r["handle"] for r in records] == ["I1/L1", "I2/L1"] and records[1]["end"] == [1005.0, 0.0, 0.0]
    assert report["files_scanned"] == 1 and report["entities_added"] == 2
    assert [i["status"] for i in report["inserts"]] == ["expanded", "expanded"]


def test_architecture_reports_expanded_and_unexpanded_xrefs():
    from src.cad_understanding.architecture import build_architectural_report

    def ref(handle):
        return {"handle": handle, "entity_type": "AcDbBlockReference", "layer": "0",
                "geometry": {"block_name": "Base", "insertion_point": [0, 0, 0]}}
    xline = {"handle": "I1/L1", "entity_type": "AcDbLine", "layer": "Base|A-WALL",
             "geometry": {"start": [0, 0, 0], "end": [5, 0, 0], "xref_insert_handle": "I1"}}
    ir = {"schema_version": "cad-ir/v2", "drawing": {"path": "s.dwg"},
          "sections": {"entities": {"total": 3, "items": [ref("I1"), ref("I2"), xline]},
                       "blocks": {"items": [{"name": "Base", "is_xref": True}]}}}
    issues = {i["code"]: i for i in build_architectural_report(ir)["issues"]}
    assert issues["xref_contents_expanded"]["handles"] == ["I1"]
    assert issues["xref_reference_not_expanded"]["handles"] == ["I2"]
    ir["sections"]["entities"]["items"] = [ref("I1"), xline]
    codes = {i["code"] for i in build_architectural_report(ir)["issues"]}
    assert "xref_reference_not_expanded" not in codes and "xref_contents_unverified" not in codes
