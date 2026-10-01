import pytest


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
