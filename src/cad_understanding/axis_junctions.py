"""Domain-neutral junctions between axis segments that carry a width.

Axes of paired offset lines usually stop half a width short of each other at a
corner, so junctions are found from the infinite axis lines: their crossing
point may lie beyond a segment end by at most the tolerance. Nothing is
trimmed, extended or merged; every junction is geometric evidence only.
"""

import math
from itertools import combinations

EPS = 1e-9
MAX_AXES = 500
PARALLEL_SIN = math.sin(math.radians(0.5))
COLLINEAR_FRACTION = 0.1


def validate_junction_tolerance(value, parameter_name="junction_tolerance"):
    if value is None:
        return
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{parameter_name} must be a finite positive distance in drawing coordinate units.")


def _vec(axis):
    (x0, y0), (x1, y1) = axis["start"][:2], axis["end"][:2]
    length = math.hypot(x1 - x0, y1 - y0)
    return (x0, y0), ((x1 - x0) / length, (y1 - y0) / length), length


def _position(t, length, tol):
    """Where parameter t falls on [0, length]: end, interior or outside."""
    overshoot = max(-t, t - length, 0.0)
    if overshoot > tol:
        return None, overshoot
    near_end = min(abs(t), abs(t - length)) <= tol
    return ("end" if near_end else "interior"), overshoot


def _parallel(a, b, pa, da, la, pb, db, lb, tol):
    offset = abs((pb[0] - pa[0]) * -da[1] + (pb[1] - pa[1]) * da[0])
    if offset > tol:
        return None
    tb = sorted(((pb[0] - pa[0]) * da[0] + (pb[1] - pa[1]) * da[1],
                 (pb[0] + db[0] * lb - pa[0]) * da[0] + (pb[1] + db[1] * lb - pa[1]) * da[1]))
    overlap = min(la, tb[1]) - max(0.0, tb[0])
    if overlap > EPS * max(la, lb):
        return {"kind": "parallel_overlap", "lateral_offset": offset, "overlap_length": overlap}
    gap = -overlap
    # Collinear continuation: nearly the same axis line, ends at most tol apart.
    if gap <= tol and offset <= COLLINEAR_FRACTION * tol:
        return {"kind": "collinear_gap", "lateral_offset": offset, "gap_length": gap}
    return None


def find_axis_junctions(axes, tolerance=None, id_key="id"):
    """axes: [{id, start, end, width}] in one horizontal plane (z ignored).

    Default tolerance per pair is the larger width, since a corner leaves the
    axes up to half a width apart and drawing noise should stay below that.
    """
    validate_junction_tolerance(tolerance)
    usable, skipped = [], []
    for axis in axes:
        try:
            _, _, length = _vec(axis)
            ok = math.isfinite(length) and length > 0 and math.isfinite(float(axis["width"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            ok = False
        (usable if ok and len(usable) < MAX_AXES else skipped).append(axis)
    junctions = []
    for a, b in combinations(usable, 2):
        pa, da, la = _vec(a)
        pb, db, lb = _vec(b)
        tol = tolerance if tolerance is not None else max(float(a["width"]), float(b["width"]))
        cross = da[0] * db[1] - da[1] * db[0]
        base = {"ids": [a[id_key], b[id_key]], "tolerance_drawing_units": tol, "status": "candidate"}
        if abs(cross) < PARALLEL_SIN:
            found = _parallel(a, b, pa, da, la, pb, db, lb, tol)
            if found:
                junctions.append({**base, **found, "angle_degrees": 0.0})
            continue
        wx, wy = pb[0] - pa[0], pb[1] - pa[1]
        ta = (wx * db[1] - wy * db[0]) / cross
        tb = (wx * da[1] - wy * da[0]) / cross
        pos_a, over_a = _position(ta, la, tol)
        pos_b, over_b = _position(tb, lb, tol)
        if pos_a is None or pos_b is None:
            continue
        kind = {("end", "end"): "corner", ("interior", "interior"): "crossing"}.get(
            (pos_a, pos_b), "t_junction")
        angle = math.degrees(math.asin(min(1.0, abs(cross))))
        junctions.append({**base, "kind": kind, "angle_degrees": angle,
                          "point_wcs": [pa[0] + da[0] * ta, pa[1] + da[1] * ta],
                          "positions": [pos_a, pos_b], "axis_overshoot": [over_a, over_b]})
    return {"requested": True, "tolerance_rule": "explicit" if tolerance is not None else "larger_width",
            "checked_axes": len(usable), "skipped_axes": [a.get(id_key) for a in skipped],
            "junctions": junctions, "junction_count": len(junctions),
            "coverage_complete": not skipped,
            "interpretation": ("Axis junction candidates from geometry only; axes are not trimmed or merged, "
                               "and a gap is not confirmed as an opening.")}


def find_axis_gaps(axes, max_gap, id_key="id"):
    """Gaps between collinear axes whose facing ends are 0 < gap <= max_gap apart.

    Each gap is returned with its start/end on the axis so callers can test what
    lies in it; a gap is geometric evidence, not an opening or a drawing error.
    """
    validate_junction_tolerance(max_gap, "max_gap")
    usable = []
    for axis in axes:
        try:
            _, _, length = _vec(axis)
            if math.isfinite(length) and length > 0:
                usable.append(axis)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    gaps = []
    for a, b in combinations(usable[:MAX_AXES], 2):
        pa, da, la = _vec(a)
        pb, db, lb = _vec(b)
        if abs(da[0] * db[1] - da[1] * db[0]) >= PARALLEL_SIN:
            continue
        width = max(float(a["width"]), float(b["width"]))
        offset = abs((pb[0] - pa[0]) * -da[1] + (pb[1] - pa[1]) * da[0])
        if offset > COLLINEAR_FRACTION * width:
            continue
        ends = sorted(((pb[0] - pa[0]) * da[0] + (pb[1] - pa[1]) * da[1],
                       (pb[0] + db[0] * lb - pa[0]) * da[0] + (pb[1] + db[1] * lb - pa[1]) * da[1]))
        if ends[0] >= la:
            first, second, lo, hi = a, b, la, ends[0]
        elif ends[1] <= 0:
            first, second, lo, hi = b, a, ends[1], 0.0
        else:
            continue  # overlapping axes are not a gap
        gap = hi - lo
        if not EPS < gap <= max_gap:
            continue
        gaps.append({"ids": [first[id_key], second[id_key]], "gap_length": gap, "width": width,
                     "lateral_offset": offset,
                     "start_wcs": [pa[0] + da[0] * lo, pa[1] + da[1] * lo],
                     "end_wcs": [pa[0] + da[0] * hi, pa[1] + da[1] * hi],
                     "status": "candidate"})
    return {"requested": True, "max_gap_drawing_units": max_gap, "gaps": gaps, "gap_count": len(gaps),
            "coverage_complete": len(usable) <= MAX_AXES}
