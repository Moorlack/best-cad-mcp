"""Architectural adapter: relate door/window/opening candidates to wall segments and gaps."""

import hashlib
import math

from .axis_junctions import find_axis_gaps, validate_junction_tolerance
from .region_overlap import band_polygon, box_band_overlap

OPENING_CATEGORIES = {"door", "window", "opening"}


def validate_opening_max_width(value):
    validate_junction_tolerance(value, "wall_opening_max_width")


def _bbox(candidate):
    box = candidate.get("bbox") or {}
    try:
        lo, hi = [float(v) for v in box["min"][:2]], [float(v) for v in box["max"][:2]]
    except (KeyError, TypeError, ValueError):
        return None
    return {"min": lo, "max": hi} if lo[0] <= hi[0] and lo[1] <= hi[1] else None


def _block_placement(geometry, start, end, width):
    """Insertion point and rotation of a block reference relative to one wall axis."""
    point = geometry.get("insertion_point")
    if not (isinstance(point, (list, tuple)) and len(point) >= 2):
        return None
    (x0, y0), (x1, y1) = start[:2], end[:2]
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    along = (point[0] - x0) * ux + (point[1] - y0) * uy
    placement = {"insertion_point_wcs": list(point[:2]),
                 "offset_from_axis": (point[0] - x0) * -uy + (point[1] - y0) * ux,
                 "position_along_axis": along, "axis_length": length,
                 "within_axis_span": -width / 2 <= along <= length + width / 2,
                 "mirrored": any(isinstance(geometry.get(k), (int, float)) and geometry[k] < 0
                                 for k in ("x_scale", "y_scale"))}
    normal = geometry.get("normal") or [0, 0, 1]
    rotation = geometry.get("rotation")
    if isinstance(rotation, (int, float)) and len(normal) == 3 and normal[2] > 0.999999:
        relative = (math.degrees(rotation) - math.degrees(math.atan2(uy, ux))) % 180.0
        placement["rotation_relative_to_wall_degrees"] = relative
        deviation = min(relative, 180.0 - relative)
        placement["orientation"] = ("along_wall" if deviation <= 1.0
                                    else "across_wall" if abs(deviation - 90.0) <= 1.0 else "oblique")
    else:
        placement["orientation"] = "not_evaluated_non_plan_normal_or_missing_rotation"
    return placement


def relate_openings(candidates, segments, max_width=None, identity="unknown"):
    """Geometric relations only: a symbol in a face gap supports, but does not prove, a real opening."""
    validate_opening_max_width(max_width)
    axes = [{"id": s["id"], "start": s["axis_wcs"][0], "end": s["axis_wcs"][1],
             "width": s["thickness_drawing_units"]["max"]} for s in segments]
    gap_result = find_axis_gaps(axes, max_width) if max_width is not None else None
    gaps = []
    for gap in (gap_result or {}).get("gaps", []):
        key = "\0".join([identity, *sorted(gap["ids"])])
        gaps.append({"id": "wall_gap_" + hashlib.sha256(key.encode()).hexdigest()[:20],
                     "segment_ids": gap["ids"], "gap_length": gap["gap_length"],
                     "thickness_drawing_units": gap["width"], "start_wcs": gap["start_wcs"],
                     "end_wcs": gap["end_wcs"], "status": "candidate"})
    gap_bands = [(g, band_polygon(g["start_wcs"], g["end_wcs"], g["thickness_drawing_units"])) for g in gaps]
    seg_bands = [(s, band_polygon(s["axis_wcs"][0], s["axis_wcs"][1], s["thickness_drawing_units"]["max"]))
                 for s in segments]
    items, used_gaps, unmeasured = [], set(), []
    for c in sorted((c for c in candidates if c["category"] in OPENING_CATEGORIES), key=lambda c: c["id"]):
        box = _bbox(c)
        if box is None:
            unmeasured.append(c["id"])
            continue
        in_gaps = [{"gap_id": g["id"], **box_band_overlap(box, band)} for g, band in gap_bands]
        on_segments = [{"segment_id": s["id"], **box_band_overlap(box, band)} for s, band in seg_bands]
        in_gaps = [m for m in in_gaps if m["ratio"] > 0]
        on_segments = [m for m in on_segments if m["ratio"] > 0]
        used_gaps.update(m["gap_id"] for m in in_gaps)
        status = "in_wall_gap" if in_gaps else "on_wall_segment" if on_segments else "not_on_wall_segment"
        item = {"candidate_id": c["id"], "category": c["category"], "handles": c["handles"],
                "status": status, "gap_matches": in_gaps, "segment_matches": on_segments,
                "opening_verified": False, "requires_architectural_review": True}
        # Reference axis: the best-overlapping gap, else the best-overlapping segment.
        if in_gaps:
            best = max(in_gaps, key=lambda m: m["ratio"])
            gap = next(g for g in gaps if g["id"] == best["gap_id"])
            item["opening_width_candidate_drawing_units"] = gap["gap_length"]
            item["width_source"] = "distance_between_face_ends"
            axis = (gap["start_wcs"], gap["end_wcs"], gap["thickness_drawing_units"], "gap", gap["id"])
        elif on_segments:
            best = max(on_segments, key=lambda m: m["ratio"])
            seg = next(s for s in segments if s["id"] == best["segment_id"])
            axis = (seg["axis_wcs"][0], seg["axis_wcs"][1], seg["thickness_drawing_units"]["max"],
                    "segment", seg["id"])
        else:
            axis = None
        if axis and c["shape"] == "block_reference":
            placement = _block_placement(c.get("geometry") or {}, axis[0], axis[1], axis[2])
            if placement:
                item["block_placement"] = {"reference": axis[3], "reference_id": axis[4], **placement}
        items.append(item)
    return {"requested": True, "gap_search": gap_result is not None,
            "max_width_drawing_units": max_width, "gaps": gaps,
            "gaps_without_opening_candidate": [g["id"] for g in gaps if g["id"] not in used_gaps],
            "openings": items, "unmeasured_candidate_ids": unmeasured,
            "coverage_complete": bool(gap_result is None or gap_result["coverage_complete"]) and not unmeasured,
            "interpretation": ("in_wall_gap: the candidate's box overlaps a gap between collinear wall faces; "
                               "on_wall_segment: it overlaps drawn wall faces only (a symbol over a continuous "
                               "wall); not_on_wall_segment: no paired wall nearby. Boxes include swings and "
                               "annotations; no opening size, type or structural effect is confirmed.")}
