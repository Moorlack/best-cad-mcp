"""Read-only comparison of declared drawing units and explicit project inputs."""

from copy import deepcopy


def build_project_context(drawing, card, readiness):
    project_units = deepcopy(card["fields"].get("units", {"value": None, "status": "missing"}))
    declared = deepcopy(drawing.get("units_metadata", {}))
    drawing_units = drawing.get("units", "unknown")
    warnings = []
    comparison = None
    if project_units["status"] == "missing":
        warnings.append("project_units_missing")
    elif project_units["status"] != "confirmed":
        warnings.append("project_units_unconfirmed")
    drawing_known = (declared.get("status") == "declared"
                     and declared.get("units") == drawing_units
                     and drawing_units not in (None, "", "unknown", "unitless"))
    if not drawing_known:
        warnings.append("drawing_units_unavailable_for_project_check")
    if drawing_known and project_units["status"] != "missing":
        comparison = drawing_units == project_units["value"]
        if not comparison:
            warnings.append("project_units_mismatch")
    return {
        "project_id": card["project_id"], "revision": card["revision"],
        "binding": "explicit_request_only",
        "project_units": project_units, "drawing_units": drawing_units,
        "drawing_units_metadata": declared, "declared_units_match": comparison,
        "geometry_scale_verified": False, "engineering_design_ready": False,
        "readiness": deepcopy(readiness), "warnings": warnings,
        "limitations": ["Matching unit declarations do not verify geometry scale.",
                        "Project input confirmation is user-supplied, not independently verified.",
                        "No persistent DWG/project binding or coordinate conversion is performed."],
    }
