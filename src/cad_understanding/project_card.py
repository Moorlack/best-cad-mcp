"""Versioned project inputs; no inferred code adoption or engineering approval."""

from __future__ import annotations

import json
import math
import re

from .common import current_scope, get_db, now_iso
from .result import error_result, ok_result

TEXT_FIELDS = {
    "address", "city", "state", "jurisdiction", "work_type", "occupancy",
    "materials", "coordinate_system", "architectural_constraints",
    "geotechnical_information", "supports_and_load_paths",
}
FIELDS = TEXT_FIELDS | {"risk_category", "story_count", "story_heights", "units", "code_basis"}
# These are input gates, not a declaration that a structural calculation can run.
REQUIREMENTS = {
    "geometry_review": {"units", "coordinate_system", "story_count", "story_heights"},
    "code_selection": {"address", "city", "state", "jurisdiction", "work_type", "occupancy", "risk_category"},
    "structural_model": FIELDS - {"geotechnical_information"},
    "foundation_review": FIELDS,
}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _validate(fields):
    if not isinstance(fields, dict) or not fields or set(fields) - FIELDS:
        raise ValueError("Provide a nonempty fields object using the documented field names.")
    for name, entry in fields.items():
        if not isinstance(entry, dict) or set(entry) - {"value", "status", "source", "note"}:
            raise ValueError(f"{name}: expected value/status/source and optional note.")
        status = entry.get("status")
        if status not in {"confirmed", "assumed", "missing"}:
            raise ValueError(f"{name}: status must be confirmed, assumed or missing.")
        if "note" in entry and not isinstance(entry["note"], str):
            raise ValueError(f"{name}: note must be text.")
        if "source" in entry and not isinstance(entry["source"], str):
            raise ValueError(f"{name}: source must be text.")
        value = entry.get("value")
        if status == "missing":
            if value is not None:
                raise ValueError(f"{name}: missing input must have a null value.")
            continue
        if not _text(entry.get("source")):
            raise ValueError(f"{name}: record the source or explicit basis of the assumption.")
        valid = False
        if name in TEXT_FIELDS:
            valid = _text(value)
        elif name == "units":
            valid = isinstance(value, str) and value in {"mm", "cm", "m", "in", "ft"}
        elif name == "risk_category":
            valid = isinstance(value, str) and value in {"I", "II", "III", "IV"}
        elif name == "story_count":
            valid = type(value) is int and value > 0
        elif name == "story_heights":
            valid = (isinstance(value, list) and bool(value)
                     and all(type(v) in {int, float} and math.isfinite(v) and v > 0 for v in value))
        elif name == "code_basis":
            required = {"document", "edition", "jurisdiction", "applicability", "reference"}
            valid = (isinstance(value, list) and bool(value)
                     and all(isinstance(v, dict) and set(v) == required
                             and all(_text(v[k]) for k in required) for v in value))
        if not valid:
            raise ValueError(f"{name}: invalid value; see the project-card field schema.")
    json.dumps(fields, allow_nan=False)


def _identity(project_id):
    if not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", project_id):
        raise ValueError("project_id must be 1–80 ASCII letters/digits, dots, underscores or hyphens.")


def _schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS engineering_project_cards (
        workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
        revision INTEGER NOT NULL, card_json TEXT NOT NULL,
        PRIMARY KEY(workspace_id, project_id, revision))""")


def _read(conn, workspace, project_id):
    row = conn.execute("""SELECT card_json FROM engineering_project_cards
        WHERE workspace_id=? AND project_id=? ORDER BY revision DESC LIMIT 1""",
        (workspace, project_id)).fetchone()
    return json.loads(row[0]) if row else None


def _readiness(fields):
    conflicts = []
    count = fields.get("story_count", {}).get("value")
    heights = fields.get("story_heights", {}).get("value")
    if count is not None and heights is not None and count != len(heights):
        conflicts.append("story_count_and_heights_disagree")
    gates = {}
    for operation, names in REQUIREMENTS.items():
        missing = sorted(n for n in names if fields.get(n, {}).get("status", "missing") == "missing")
        assumed = sorted(n for n in names if fields.get(n, {}).get("status") == "assumed")
        relevant_conflicts = conflicts if "story_heights" in names else []
        gates[operation] = {"inputs_confirmed": not (missing or assumed or relevant_conflicts),
                            "missing": missing, "assumed": assumed, "conflicts": relevant_conflicts}
    return {"gates": gates, "engineering_design_ready": False,
            "warning": "Input status is user-supplied, not independently verified. Loads, geometry and calculations require separate validation."}


def get_project_card(project_id, database=None):
    try:
        _identity(project_id)
    except ValueError as exc:
        return error_result(str(exc))
    db = get_db(database)
    workspace = current_scope(db)["workspace_id"]
    with db._conn() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_project_cards'").fetchone()
        card = _read(conn, workspace, project_id) if exists else None
    if card is None:
        return error_result("Project card not found in the current workspace.")
    return ok_result("Read project card.", data={"card": card, "readiness": _readiness(card["fields"])})


def update_project_card(project_id, fields, expected_revision, change_reason, database=None):
    """Merge supplied fields into an immutable new revision with optimistic locking."""
    try:
        _identity(project_id)
        _validate(fields)
        if type(expected_revision) is not int or expected_revision < 0 or not _text(change_reason):
            raise ValueError("Provide expected_revision >= 0 and a nonempty change_reason.")
    except (ValueError, TypeError) as exc:
        return error_result(str(exc))
    db = get_db(database)
    workspace = current_scope(db)["workspace_id"]
    with db._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _schema(conn)
        previous = _read(conn, workspace, project_id)
        revision = previous["revision"] if previous else 0
        if revision != expected_revision:
            return error_result("Revision conflict: read the latest card before updating.",
                                data={"current_revision": revision})
        merged = dict(previous["fields"]) if previous else {}
        if ("units" in fields and merged.get("story_heights", {}).get("value") is not None
                and fields["units"].get("value") != merged.get("units", {}).get("value")
                and "story_heights" not in fields):
            return error_result("Changing units requires resupplying or clearing story_heights; no implicit conversion.")
        merged.update(fields)
        card = {"schema_version": "engineering-project/v1", "project_id": project_id,
                "revision": revision + 1, "updated_at": now_iso(), "change_reason": change_reason,
                "fields": merged}
        conn.execute("INSERT INTO engineering_project_cards VALUES (?, ?, ?, ?)",
                     (workspace, project_id, revision + 1, json.dumps(card, ensure_ascii=False, allow_nan=False)))
    return ok_result("Saved project card revision; DWG unchanged.",
                     data={"card": card, "readiness": _readiness(merged)})


def get_project_card_history(project_id, limit=20, database=None):
    try:
        _identity(project_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100.")
    except ValueError as exc:
        return error_result(str(exc))
    db = get_db(database)
    with db._conn() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engineering_project_cards'").fetchone()
        rows = conn.execute("""SELECT card_json FROM engineering_project_cards
            WHERE workspace_id=? AND project_id=? ORDER BY revision DESC LIMIT ?""",
            (current_scope(db)["workspace_id"], project_id, limit)).fetchall() if exists else []
    return ok_result("Read project card history (newest first).",
                     data={"revisions": [json.loads(row[0]) for row in rows], "limit": limit})
