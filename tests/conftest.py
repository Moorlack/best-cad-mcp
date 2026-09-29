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
