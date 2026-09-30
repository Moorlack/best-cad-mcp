from types import SimpleNamespace

import pytest

from src.cad_controller import CADController
from src.cad_database import CADDatabase
from src.cad_tools import query_tools
from src.cad_understanding import snapshot_freshness
from src.cad_understanding.architecture import analyze_architectural_drawing
from src.cad_understanding.geometry_analysis import analyze_geometry


def fp(path="C:/a.dwg", count=2, last="8AF", handseed="8B0"):
    return {"name": "a.dwg", "path": path, "model_space_count": count, "last_entity_handle": last,
            "handseed": handseed}


@pytest.mark.parametrize("scanned,live,status,reason", [
    (None, fp(), "unverified", "no_scan_fingerprint"),
    (fp(), None, "unverified", "autocad_document_unavailable"),
    (fp(), fp(path="C:/b.dwg"), "stale", "active_document_differs"),
    (fp(), fp(count=3), "stale", "model_space_object_count_changed"),
    (fp(), fp(last="8B4"), "stale", "model_space_last_entity_changed"),
    (fp(), fp(handseed="8B5"), "stale", "database_objects_created_since_scan"),
    # AutoCAD 2025 refuses HANDSEED; the remaining fields still decide.
    (fp(handseed=None), fp(handseed=None), "consistent_with_scan", None),
    (fp(handseed=None), fp(handseed=None, count=3), "stale", "model_space_object_count_changed"),
    (fp(last=None), fp(), "unverified", "fingerprint_incomplete"),
    (fp(count=None), fp(count=None), "unverified", "fingerprint_incomplete"),
    (fp(path="C:/A.DWG"), fp(path="c:\\a.dwg"), "consistent_with_scan", None),
])
def test_compare_fingerprints(scanned, live, status, reason):
    result = snapshot_freshness.compare_fingerprints(scanned, live)
    assert (result["status"], result["reason"]) == (status, reason)
    assert result["limitations"] == [snapshot_freshness.LIMITATION]


class _Doc:
    def __init__(self, count, handseed):
        self.Name, self.FullName = "a.dwg", "C:/a.dwg"
        self.ModelSpace = SimpleNamespace(Count=count, Item=lambda i: SimpleNamespace(
            ObjectName="AcDbLine", Handle=f"L{i}", Layer="PART"))
        self.handseed = handseed

    def GetVariable(self, name):
        return {"INSUNITS": 4, "HANDSEED": self.handseed}[name]


def _scanned(tmp_path, monkeypatch, doc):
    db = CADDatabase(str(tmp_path / "cad.db"))
    ctrl = object.__new__(CADController)
    ctrl.doc = doc
    ctrl.acad = SimpleNamespace(Documents=SimpleNamespace(Count=1), ActiveDocument=doc)
    monkeypatch.setattr(query_tools, "db", db)
    monkeypatch.setattr(query_tools, "ctrl", ctrl)
    query_tools.scan_all_entities()
    return db, ctrl


def test_scan_records_fingerprint_and_clearing_removes_it(tmp_path, monkeypatch):
    db, ctrl = _scanned(tmp_path, monkeypatch, _Doc(2, "8B0"))
    stored = db.get_scan_fingerprint()
    assert stored["path"] == "C:/a.dwg" and stored["model_space_count"] == 2
    assert stored["handseed"] == "8B0" and stored["last_entity_handle"] == "L1" and stored["captured_at"]
    assert ctrl.active_document_fingerprint() == {
        k: stored[k] for k in ("name", "path", "model_space_count", "last_entity_handle", "handseed")}


def test_fingerprint_without_handseed_uses_last_entity(tmp_path, monkeypatch):
    doc = _Doc(3, None)
    doc.GetVariable = lambda name: 4 if name == "INSUNITS" else (_ for _ in ()).throw(RuntimeError("no HANDSEED"))
    db, ctrl = _scanned(tmp_path, monkeypatch, doc)
    stored = db.get_scan_fingerprint()
    assert stored["handseed"] is None and stored["last_entity_handle"] == "L2"
    assert snapshot_freshness.compare_fingerprints(stored, ctrl.active_document_fingerprint())["status"] == \
        "consistent_with_scan"
    db.clear_entities()
    assert db.get_scan_fingerprint() is None


def test_truncated_scan_does_not_record_fingerprint(tmp_path, monkeypatch):
    db, _ = _scanned(tmp_path, monkeypatch, _Doc(2, "8B0"))
    query_tools.scan_all_entities(max_entities=1)
    assert db.get_scan_fingerprint() is None


@pytest.mark.parametrize("live_change,status,warning,issue", [
    ({}, "consistent_with_scan", "snapshot_existing_object_edits_not_detected",
     "snapshot_existing_object_edits_not_detected"),
    ({"handseed": "8B9"}, "stale", "snapshot_stale", "snapshot_stale"),
    (None, "unverified", "snapshot_freshness_unverified", "snapshot_freshness_unverified"),
])
def test_runtime_tools_report_live_freshness(tmp_path, monkeypatch, live_change, status, warning, issue):
    db, ctrl = _scanned(tmp_path, monkeypatch, _Doc(2, "8B0"))
    live = None if live_change is None else {**ctrl.active_document_fingerprint(), **live_change}
    monkeypatch.setattr(snapshot_freshness, "live_document_fingerprint", lambda: live)

    geometry = analyze_geometry(database=db)
    assert geometry["data"]["report"]["source"]["freshness"] == status
    assert geometry["data"]["report"]["source"]["freshness_check"]["status"] == status
    assert warning in geometry["warnings"]

    architecture = analyze_architectural_drawing(database=db)
    report = architecture["data"]["report"]
    assert report["source"]["freshness"] == status
    codes = {i["code"] for i in report["issues"]}
    assert issue in codes and (issue == "snapshot_freshness_unverified" or "snapshot_freshness_unverified" not in codes)
    assert warning in architecture["warnings"]


def test_scan_without_autocad_keeps_previous_cache(tmp_path, monkeypatch):
    db, ctrl = _scanned(tmp_path, monkeypatch, _Doc(2, "8B0"))
    before = (db.get_scan_fingerprint(), db.get_drawing_units(), sum(db.get_entity(h) is not None for h in ("L0", "L1")))
    ctrl.acad = None
    monkeypatch.setattr(CADController, "_ensure_connected", lambda self: None)
    with pytest.raises(RuntimeError, match="Unable to connect to AutoCAD"):
        query_tools.scan_all_entities()
    assert (db.get_scan_fingerprint(), db.get_drawing_units(), sum(db.get_entity(h) is not None for h in ("L0", "L1"))) == before
    assert before[2] == 2


def test_drawing_identity_path_uses_full_name_even_when_empty():
    from src.cad_tools.file_tools import _drawing_identity_path

    assert _drawing_identity_path({"full_name": "C:\\a\\b.dwg", "path": "C:\\a"}) == "C:\\a\\b.dwg"
    # Unsaved drawing: COM reports the default folder as Path but no FullName.
    assert _drawing_identity_path({"full_name": "", "path": "C:\\Users\\x\\Documents"}) == ""
    assert _drawing_identity_path({"path": "legacy.dwg"}) == "legacy.dwg"
