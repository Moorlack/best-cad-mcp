"""Compare the scan-time drawing fingerprint with the live AutoCAD document.

The fingerprint (document path, model-space object count, last model-space
entity handle and, where AutoCAD exposes it, HANDSEED) changes when entities are
created or deleted, or another drawing is active. Moving or editing
existing objects does not change it, so a match is reported as consistent, never
as proof that the cache is current.
"""

from datetime import datetime, timezone

LIMITATION = "Edits to existing objects (moves, property changes) do not change this fingerprint."


def _norm_path(value):
    return str(value or "").replace("/", "\\").casefold()


def _summary(fingerprint):
    if not fingerprint:
        return None
    return {k: fingerprint.get(k) for k in ("name", "path", "model_space_count", "last_entity_handle",
                                           "handseed", "captured_at") if k in fingerprint}


def compare_fingerprints(scanned, live):
    result = {"status": "unverified", "reason": None, "scan": _summary(scanned), "live": _summary(live),
              "checked_at": datetime.now(timezone.utc).isoformat(), "limitations": [LIMITATION]}
    if not scanned:
        result["reason"] = "no_scan_fingerprint"
    elif live is None:
        result["reason"] = "autocad_document_unavailable"
    elif _norm_path(scanned.get("path")) != _norm_path(live.get("path")):
        result.update(status="stale", reason="active_document_differs")
    elif _differs(scanned, live, "model_space_count"):
        result.update(status="stale", reason="model_space_object_count_changed")
    elif _differs(scanned, live, "last_entity_handle"):
        result.update(status="stale", reason="model_space_last_entity_changed")
    elif _differs(scanned, live, "handseed"):
        result.update(status="stale", reason="database_objects_created_since_scan")
    elif any(fp.get(k) is None for fp in (scanned, live) for k in ("model_space_count", "last_entity_handle")):
        result["reason"] = "fingerprint_incomplete"
    else:
        result["status"] = "consistent_with_scan"
    return result


def _differs(scanned, live, key):
    # Optional fields (HANDSEED is unavailable in some AutoCAD versions) only
    # count when both sides report them.
    a, b = scanned.get(key), live.get(key)
    return a is not None and b is not None and str(a) != str(b)


def live_document_fingerprint():
    """Runtime adapter; returns None when AutoCAD or a document is not available."""
    try:
        from src.cad_controller import get_controller
        return get_controller().active_document_fingerprint()
    except Exception:
        return None


def check_snapshot_freshness(database=None):
    from src.cad_database import get_database

    db = database or get_database()
    return compare_fingerprints(db.get_scan_fingerprint(), live_document_fingerprint())


WARNINGS = {"unverified": "snapshot_freshness_unverified", "stale": "snapshot_stale",
            "consistent_with_scan": "snapshot_existing_object_edits_not_detected"}
MESSAGES = {
    "unverified": "Freshness could not be checked against the live drawing; rescan the intended drawing/space first.",
    "stale": "The drawing changed after the scan (see source.freshness_check); rescan before relying on this report.",
    "consistent_with_scan": "Document, object count and last entity match the scan; edits to existing objects are not detected.",
}


def apply_to_report(report, freshness):
    """Record the check in report.source; returns the warning code to use."""
    report.setdefault("source", {})["freshness"] = freshness["status"]
    report["source"]["freshness_check"] = freshness
    return WARNINGS[freshness["status"]]
