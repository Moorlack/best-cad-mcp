"""Let the unit suite import the COM bridge on hosts without pywin32."""

from __future__ import annotations

import sys
import types


def _ensure_windows_com_stubs() -> None:
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        win32com = types.ModuleType("win32com")
        client = types.ModuleType("win32com.client")
        pythoncom = types.ModuleType("pythoncom")
        pythoncom.VT_ARRAY = 0x2000
        pythoncom.VT_R8 = 5
        pythoncom.VT_I2 = 2
        pythoncom.VT_I4 = 3
        pythoncom.VT_BSTR = 8
        pythoncom.VT_VARIANT = 12
        pythoncom.VT_DISPATCH = 9
        client.VARIANT = lambda vt, value: value
        client.Dispatch = lambda obj: obj
        client.GetActiveObject = lambda prog_id: None
        win32com.client = client
        sys.modules["win32com"] = win32com
        sys.modules["win32com.client"] = client
        sys.modules["pythoncom"] = pythoncom


_ensure_windows_com_stubs()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_autocad_freshness(monkeypatch):
    # Reports compare the cache with the live drawing; tests must not read a
    # running AutoCAD. Tests that need a live fingerprint patch this again.
    from src.cad_understanding import snapshot_freshness

    monkeypatch.setattr(snapshot_freshness, "live_document_fingerprint", lambda: None)


@pytest.fixture(autouse=True)
def _no_live_acad_processes(monkeypatch):
    # Instance selection cross-checks OS processes; tests must not see a running AutoCAD.
    from src import autocad_instances

    monkeypatch.setattr(autocad_instances, "acad_process_pids", lambda: None)


@pytest.fixture(autouse=True)
def _no_live_autocad_connection(monkeypatch):
    # Some modules stub win32com at import time, but src.cad_controller may already hold the real
    # module (imported by another test file); a reconnect would then attach to a running AutoCAD.
    # Tests that exercise these paths patch them again with their own fakes.
    import sys

    from src import autocad_instances

    monkeypatch.setattr(autocad_instances, "list_instances", lambda prog_ids: [])
    client = sys.modules.get("win32com.client")
    if client is not None and getattr(client, "__file__", None):  # the real module, not a stub

        def refuse(*_args, **_kwargs):
            raise RuntimeError("Unit tests must not attach to a running AutoCAD.")

        monkeypatch.setattr(client, "GetActiveObject", refuse)
