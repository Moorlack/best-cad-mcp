"""Short, human-readable digest of an architectural report.

The full report is large and mostly evidence. This keeps the numbers a person (or an agent
answering one) asks first: what was scanned, how sure it is, walls, openings, enclosed areas and
the main warnings. Everything stays a geometric candidate in drawing units.
"""

from collections import Counter

MAX_LOOPS = 20
MAX_ISSUE_CODES = 12


def _fmt(value, digits=6):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def build_plan_summary(report):
    drawing = report.get("drawing") or {}
    source = report.get("source") or {}
    walls = report.get("wall_segment_candidates") or {}
    quantities = report.get("quantity_summary") or {}
    estimate = report.get("wall_thickness_estimate") or None
    loops = sorted(((walls.get("room_loops") or {}).get("loops") or []),
                   key=lambda loop: -(loop.get("net_area_drawing_units_squared") or loop["area_drawing_units_squared"]))
    openings = walls.get("openings") or {}
    issue_counts = Counter()
    for item in report.get("issues", []):
        issue_counts[item["code"]] += item.get("omitted_count") or 1
    units = drawing.get("units", "unknown")
    summary = {
        "drawing": {"name": drawing.get("name"), "path": drawing.get("path"), "declared_units": units,
                    "entities_scanned": (report.get("coverage") or {}).get("scanned_entities"),
                    "freshness": source.get("freshness"),
                    "scan_layer_filter": (source.get("scan_scope") or {}).get("layer_filter"),
                    "hidden_layer_entities_skipped": (report.get("coverage") or {}).get("hidden_layer_entities_skipped", 0),
                    "viewport_scope": (report.get("coverage") or {}).get("viewport_scope")},
        "walls": {"segments": (quantities.get("walls") or {}).get("segment_count", 0),
                  "total_axis_length": (quantities.get("walls") or {}).get("total_axis_length"),
                  "thickness_groups": (quantities.get("walls") or {}).get("by_thickness", [])[:8],
                  "thickness_range_used": walls.get("thickness_range_drawing_units"),
                  "thickness_estimated": estimate is not None,
                  "runs": walls.get("run_count", 0)},
        "openings": {"symbols_in_or_on_walls": len(openings.get("openings") or []),
                     "by_category": (quantities.get("openings") or {}).get("by_category", {}),
                     "wall_gaps": len(openings.get("gaps") or []),
                     "gaps_without_symbol": len(openings.get("gaps_without_opening_candidate") or []),
                     "gaps_with_swing_arc_only": len(openings.get("gaps_with_swing_arc_only") or [])},
        "enclosed_areas": {"count": len(loops),
                           "total_net_area": (quantities.get("enclosed_loops") or {}).get("total_net_area"),
                           "largest": [{"id": loop["id"], "net_area": loop.get("net_area_drawing_units_squared"),
                                        "axis_area": loop["area_drawing_units_squared"],
                                        "through_opening": loop.get("closed_through_opening_gap", False),
                                        "columns_inside": len(loop.get("columns_inside") or [])}
                                       for loop in loops[:MAX_LOOPS]]},
        "candidates_by_category": quantities.get("candidates_by_category", {}),
        "main_issues": dict(issue_counts.most_common(MAX_ISSUE_CODES)),
        "verified": False,
    }
    w, o, e = summary["walls"], summary["openings"], summary["enclosed_areas"]
    lines = [
        f"Drawing {_fmt(summary['drawing']['name'])}: {_fmt(summary['drawing']['entities_scanned'])} entities scanned, "
        f"units declared as {units} (scale not verified), freshness {_fmt(summary['drawing']['freshness'])}"
        + (f", scan limited to layers {', '.join(summary['drawing']['scan_layer_filter'][:5])}" if summary["drawing"]["scan_layer_filter"] else "")
        + (f", {summary['drawing']['hidden_layer_entities_skipped']} entities on frozen/off layers skipped"
           if summary["drawing"]["hidden_layer_entities_skipped"] else "")
        + (f", as shown in viewport {summary['drawing']['viewport_scope']['handle']} of layout "
           f"{summary['drawing']['viewport_scope']['layout']}" if summary["drawing"]["viewport_scope"] else "")
        + ".",
        f"Walls: {w['segments']} paired segments, axis length {_fmt(w['total_axis_length'])}"
        + (f", typical thickness {_fmt(estimate['peak_drawing_units'])} (estimated)" if estimate else
           (f", thickness range {w['thickness_range_used']}" if w["thickness_range_used"] else ", walls not paired (no thickness range)"))
        + f", {w['runs']} collinear runs.",
        f"Openings: {o['symbols_in_or_on_walls']} door/window/opening symbols related to walls, {o['wall_gaps']} wall gaps "
        f"({o['gaps_without_symbol']} without a symbol, of which {o['gaps_with_swing_arc_only']} have a door-swing arc).",
        f"Enclosed areas: {e['count']} loops, total net area {_fmt(e['total_net_area'])} (drawing units squared)"
        + (f"; largest {_fmt(e['largest'][0]['net_area'])}" if e["largest"] else "") + ".",
        "Main issues: " + (", ".join(f"{code} x{count}" for code, count in summary["main_issues"].items()) or "none") + ".",
        "All results are geometric candidates for review; nothing is a verified wall, room, area or structural element.",
    ]
    summary["text"] = "\n".join(lines)
    return summary
