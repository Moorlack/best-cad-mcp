import time
from types import SimpleNamespace

import pytest

from src import cad_controller
from src.autocad_instances import AmbiguousAutoCADInstances, choose_instance, describe
from src.cad_controller import CADController
from src.cad_tools import utility_tools

CIVIL = {"pid": 101, "app": SimpleNamespace(tag="civil"), "documents": [r"C:\Work\SHG-MT-PR.dwg"], "error": None}
ACAD = {"pid": 202, "app": SimpleNamespace(tag="acad"), "documents": [r"C:\Tests\TEST2.dwg"], "error": None}


def test_choose_single_pinned_and_document():
    assert choose_instance([]) is None
    assert choose_instance([ACAD]) is ACAD
    assert choose_instance([CIVIL, ACAD], pinned_pid=202) is ACAD
    assert choose_instance([CIVIL, ACAD], document_path=r"c:\tests\test2.DWG") is ACAD
    with pytest.raises(RuntimeError, match="no longer running"):
        choose_instance([CIVIL], pinned_pid=202)
    with pytest.raises(RuntimeError, match="No running AutoCAD instance has"):
        choose_instance([CIVIL, ACAD], document_path=r"C:\Other.dwg")


def test_several_instances_fail_closed_with_listing():
    with pytest.raises(AmbiguousAutoCADInstances) as err:
        choose_instance([CIVIL, ACAD])
    message = str(err.value)
    assert "pid 101: SHG-MT-PR.dwg" in message and "pid 202: TEST2.dwg" in message
    assert "select_autocad_instance" in message
    assert describe([ACAD]) == [{"pid": 202, "documents": [r"C:\Tests\TEST2.dwg"], "error": None}]


@pytest.fixture
def ctrl(monkeypatch):
    c = object.__new__(CADController)
    c.acad = c.doc = None
    c._pinned_pid = None
    c._last_connect_error = None
    monkeypatch.delenv("CAD_MCP_AUTOCAD_DOCUMENT", raising=False)
    return c


def test_controller_refuses_to_guess_and_explains(ctrl, monkeypatch):
    monkeypatch.setattr(CADController, "running_instances", lambda self: [CIVIL, ACAD])
    started = time.time()
    assert ctrl.connect() is False
    assert time.time() - started < 2  # no 6 s retry loop for an ambiguous choice
    assert "2 AutoCAD instances are running" in ctrl._last_connect_error
    monkeypatch.setattr(CADController, "_ensure_connected", lambda self: None)
    blocked = ctrl.get_document_info()
    assert blocked["success"] is False and "select_autocad_instance" in blocked["message"]


def test_controller_uses_pin_env_or_single(ctrl, monkeypatch):
    monkeypatch.setattr(CADController, "running_instances", lambda self: [CIVIL, ACAD])
    monkeypatch.setenv("CAD_MCP_AUTOCAD_DOCUMENT", r"C:\Tests\TEST2.dwg")
    assert ctrl._get_active_autocad().tag == "acad"
    monkeypatch.delenv("CAD_MCP_AUTOCAD_DOCUMENT")
    result = ctrl.select_instance(pid=101)
    assert result["pinned_pid"] == 101 and ctrl._get_active_autocad().tag == "civil"
    assert ctrl.select_instance(clear=True)["pinned_pid"] is None
    monkeypatch.setattr(CADController, "running_instances", lambda self: [ACAD])
    assert ctrl._get_active_autocad().tag == "acad"


def test_enumeration_failure_falls_back_to_get_active_object(ctrl, monkeypatch):
    def broken(self):
        raise OSError("ROT unavailable")
    monkeypatch.setattr(CADController, "running_instances", broken)
    monkeypatch.setattr(cad_controller.win32com.client, "GetActiveObject", lambda prog_id: SimpleNamespace(tag="rot"),
                        raising=False)
    assert ctrl._get_active_autocad().tag == "rot"


def test_tools_report_and_select(ctrl, monkeypatch):
    monkeypatch.setattr(utility_tools, "ctrl", ctrl)
    monkeypatch.setattr(CADController, "running_instances", lambda self: [CIVIL, ACAD])
    listed = utility_tools.list_autocad_instances()
    assert listed["count"] == 2 and "select_autocad_instance" in listed["message"]
    assert all("app" not in i for i in listed["instances"])
    assert utility_tools.select_autocad_instance()["ok"] is False
    chosen = utility_tools.select_autocad_instance(document_path=r"C:\Tests\TEST2.dwg")
    assert chosen["ok"] and chosen["pinned_pid"] == 202
    assert utility_tools.select_autocad_instance(pid=999)["ok"] is False


def test_process_invisible_to_com_still_makes_choice_ambiguous():
    with pytest.raises(AmbiguousAutoCADInstances, match="pid 101: not reachable through COM"):
        choose_instance([ACAD], process_pids={101, 202})
    assert choose_instance([ACAD], process_pids={202}) is ACAD
    assert choose_instance([ACAD], pinned_pid=202, process_pids={101, 202}) is ACAD
    assert choose_instance([ACAD], document_path=r"C:\Tests\TEST2.dwg", process_pids={101, 202}) is ACAD


def test_controller_uses_os_process_list(ctrl, monkeypatch):
    from src import autocad_instances
    monkeypatch.setattr(CADController, "running_instances", lambda self: [ACAD])
    monkeypatch.setattr(autocad_instances, "acad_process_pids", lambda: {101, 202})
    assert ctrl.connect() is False and "not reachable through COM" in ctrl._last_connect_error
    monkeypatch.setattr(utility_tools, "ctrl", ctrl)
    listed = utility_tools.list_autocad_instances()
    assert listed["count"] == 2 and listed["unreachable_process_pids"] == [101]
    assert utility_tools.select_autocad_instance(pid=202)["ok"]
    assert ctrl._get_active_autocad().tag == "acad"


def test_tasklist_parsing():
    from src.autocad_instances import parse_tasklist_csv
    out = ('"acad.exe","21924","Console","1","2,048,000 K"\r\n'
           '"acad.exe","104420","Console","1","1,024 K"\r\n'
           'INFO: No tasks are running which match the specified criteria.\r\n')
    assert parse_tasklist_csv(out) == {21924, 104420}
    assert parse_tasklist_csv("") == set()


def test_pinned_process_running_but_unreachable_is_explained():
    with pytest.raises(RuntimeError, match="running but not reachable through COM"):
        choose_instance([ACAD], pinned_pid=101, process_pids={101, 202})


def test_remembered_instances_survive_rot_changes(ctrl, monkeypatch):
    from src import autocad_instances
    ctrl._known_instances = {}
    live_docs = SimpleNamespace(Count=1, Item=lambda i: SimpleNamespace(FullName=r"C:\Tests\TEST2.dwg", Name="TEST2.dwg"))
    acad = {**ACAD, "app": SimpleNamespace(tag="acad", Documents=live_docs)}
    rot = [[CIVIL, acad], [CIVIL]]  # second enumeration: AutoCAD vanished from the ROT
    monkeypatch.setattr(autocad_instances, "list_instances", lambda prog_ids: rot.pop(0) if rot else [CIVIL])
    monkeypatch.setattr(CADController, "_autocad_prog_id_candidates", staticmethod(lambda: []))
    monkeypatch.setattr(autocad_instances, "acad_process_pids", lambda: {101, 202})
    assert {i["pid"] for i in ctrl.running_instances()} == {101, 202}
    again = {i["pid"]: i for i in ctrl.running_instances()}
    assert again[202]["source"] == "remembered_reference" and again[202]["documents"] == [r"C:\Tests\TEST2.dwg"]
    assert ctrl.select_instance(document_path=r"C:\Tests\TEST2.dwg")["pinned_pid"] == 202
    monkeypatch.setattr(autocad_instances, "acad_process_pids", lambda: {101})  # AutoCAD closed
    assert {i["pid"] for i in ctrl.running_instances()} == {101}
