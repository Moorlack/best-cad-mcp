"""Compare cached LINE geometry with explicit external reference lengths."""

import math
from collections import Counter
from copy import deepcopy

METERS_PER_UNIT = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}
REL_TOL = 1e-6
ABS_TOL_METERS = 1e-9


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_references(references):
    if not isinstance(references, list) or not 1 <= len(references) <= 20:
        raise ValueError("reference_lengths must contain 1–20 reference objects.")
    handles = set()
    for ref in references:
        if not isinstance(ref, dict) or set(ref) != {"handle", "length", "units", "source"}:
            raise ValueError("Each reference requires exactly handle, length, units and source.")
        for field in ("handle", "source"):
            if not isinstance(ref[field], str) or not ref[field].strip() or len(ref[field]) > 1024:
                raise ValueError(f"Reference {field} must be nonempty text, at most 1024 characters.")
        if ref["handle"] in handles:
            raise ValueError("Each reference handle must be unique.")
        handles.add(ref["handle"])
        if not _finite_number(ref["length"]) or ref["length"] <= 0:
            raise ValueError("Reference length must be a finite positive number.")
        if not isinstance(ref["units"], str) or ref["units"] not in METERS_PER_UNIT:
            raise ValueError("Reference units must be mm, cm, m, in or ft.")


def check_scale_references(drawing_ir, references):
    validate_references(references)
    drawing = drawing_ir.get("drawing", {})
    units = drawing.get("units")
    metadata = drawing.get("units_metadata", {})
    unit_known = (units in METERS_PER_UNIT and metadata.get("status") == "declared"
                  and metadata.get("units") == units)
    section = drawing_ir.get("sections", {}).get("entities", {})
    entities = section.get("items", [])
    counts = Counter(str(e.get("handle") or "") for e in entities)
    by_handle = {str(e.get("handle") or ""): e for e in entities}
    checks = []
    for ref in references:
        item = {"reference": deepcopy(ref), "status": "not_verified", "reason": None,
                "measured_length_drawing_units": None, "measured_length_meters": None,
                "reference_length_meters": None, "reference_to_measured_ratio": None}
        checks.append(item)
        handle = ref["handle"]
        if counts[handle] != 1:
            item["reason"] = "handle_missing_from_snapshot" if not counts[handle] else "ambiguous_handle"
            continue
        ent = by_handle[handle]
        if str(ent.get("entity_type", "")).lower().removeprefix("acdb") != "line":
            item["reason"] = "unsupported_entity_use_line"
            continue
        geometry = ent.get("geometry") or {}
        points = [geometry.get("start", geometry.get("start_point")),
                  geometry.get("end", geometry.get("end_point"))]
        if not all(isinstance(p, (list, tuple)) and len(p) in (2, 3)
                   and all(_finite_number(v) for v in p) for p in points):
            item["reason"] = "missing_or_invalid_endpoints"
            continue
        points = [list(p) + ([0.0] if len(p) == 2 else []) for p in points]
        length = math.dist(*points)
        if not math.isfinite(length) or length <= 0:
            item["reason"] = "degenerate_or_out_of_range_length"
            continue
        item["measured_length_drawing_units"] = length
        if not unit_known:
            item["reason"] = "drawing_units_unknown_or_unsupported"
            continue
        measured = length * METERS_PER_UNIT[units]
        expected = ref["length"] * METERS_PER_UNIT[ref["units"]]
        if not all(math.isfinite(v) and v > 0 for v in (measured, expected)):
            item["reason"] = "numeric_range_exceeded"
            continue
        ratio = expected / measured
        item.update(measured_length_meters=measured, reference_length_meters=expected,
                    reference_to_measured_ratio=ratio if math.isfinite(ratio) else None,
                    status="agrees" if math.isclose(measured, expected, rel_tol=REL_TOL,
                                                   abs_tol=ABS_TOL_METERS) else "mismatch")
    return {"checks": checks, "all_references_agree": all(c["status"] == "agrees" for c in checks),
            "drawing_units": units, "geometry_scale_verified": False,
            "relative_tolerance": REL_TOL, "absolute_tolerance_meters": ABS_TOL_METERS,
            "entity_coverage_truncated": bool(section.get("truncated")),
            "limitations": ["Reference values and sources are user-supplied, not independently verified.",
                            "Only the specified LINE objects are compared; this does not verify the whole drawing.",
                            "No DWG edits, unit changes, project confirmations or dimension-text interpretation."]}
