import pytest


@pytest.fixture(autouse=True)
def _no_live_autocad_freshness(monkeypatch):
    # Reports compare the cache with the live drawing; tests must not read a
    # running AutoCAD. Tests that need a live fingerprint patch this again.
    from src.cad_understanding import snapshot_freshness

    monkeypatch.setattr(snapshot_freshness, "live_document_fingerprint", lambda: None)
