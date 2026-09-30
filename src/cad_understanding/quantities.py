"""Geometric quantity summary of an architectural report (no verified takeoff).

Sums what the candidate pipeline already measured: wall axis length and thickness groups, opening
counts and widths, enclosed-loop areas. Every number is a geometric candidate in drawing units.
"""

import math
from collections import defaultdict


def build_quantity_summary(wall_segment_candidates, candidates):
    segments = (wall_segment_candidates or {}).get("segments") or []
    by_thickness = defaultdict(lambda: {"segments": 0, "axis_length": 0.0})
    total = 0.0
    for s in segments:
        (x0, y0), (x1, y1) = s["axis_wcs"][0][:2], s["axis_wcs"][1][:2]
        length = math.hypot(x1 - x0, y1 - y0)
        total += length
        key = round(float(s["thickness_drawing_units"]["mean"]), 3)
        by_thickness[key]["segments"] += 1
        by_thickness[key]["axis_length"] += length
    openings = ((wall_segment_candidates or {}).get("openings") or {}).get("openings") or []
    widths = defaultdict(list)
    for item in openings:
        width = item.get("opening_width_candidate_drawing_units")
        if isinstance(width, (int, float)):
            widths[item["category"]].append(width)
    loops = ((wall_segment_candidates or {}).get("room_loops") or {}).get("loops") or []
    net = [loop["net_area_drawing_units_squared"] for loop in loops if loop.get("net_area_drawing_units_squared") is not None]
    by_category = defaultdict(int)
    for c in candidates:
        by_category[c["category"]] += 1
    return {
        "walls": {"segment_count": len(segments), "total_axis_length": total,
                  "by_thickness": [{"thickness": k, **v} for k, v in sorted(by_thickness.items())]},
        "openings": {"count": len(openings),
                     "by_category": {cat: {"count": len(ws), "min_width": min(ws), "max_width": max(ws)}
                                     for cat, ws in sorted(widths.items())}},
        "enclosed_loops": {"count": len(loops), "total_net_area": math.fsum(net) if net else None,
                           "total_axis_area": math.fsum(loop["area_drawing_units_squared"] for loop in loops) if loops else None},
        "candidates_by_category": dict(sorted(by_category.items())),
        "status": "geometric_candidates_not_a_verified_takeoff", "units": "drawing units (lengths, squared for areas)",
    }
