"""Domain-neutral parallel offset pairs over normalized LINE records."""

import hashlib
import math
from collections import Counter
from itertools import combinations

from .axis_junctions import find_axis_junctions
from .line_geometry import EPS, eligible_lines

DEFAULT_ANGLE_TOLERANCE_DEGREES = 0.01
MAX_ANGLE_TOLERANCE_DEGREES = 5.0


def _finite_positive(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def validate_separation_range(value, parameter_name="parallel_separation_range"):
    if value is None:
        return
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(_finite_positive(v) for v in value) or value[0] > value[1]):
        raise ValueError(f"{parameter_name} must be [min, max]: finite positive distances "
                         "in drawing coordinate units with min <= max.")


def validate_angle_tolerance(value, parameter_name="parallel_angle_tolerance_degrees"):
    if value is None:
        return
    try:
        valid = (type(value) in (int, float) and math.isfinite(value)
                 and 0 <= value <= MAX_ANGLE_TOLERANCE_DEGREES)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{parameter_name} must be between 0 and {MAX_ANGLE_TOLERANCE_DEGREES} degrees.")


def _measure(first, second, angle_tolerance):
    """Return pair geometry for parallel, overlapping, same-plane lines, else a reason."""
    a0, a1 = first
    b0, b1 = second
    if max(p[2] for p in (a0, a1, b0, b1)) - min(p[2] for p in (a0, a1, b0, b1)) > EPS * max(
            math.dist(a0[:2], a1[:2]), math.dist(b0[:2], b1[:2])):
        return None, "different_planes"
    length_a = math.dist(a0[:2], a1[:2])
    ux, uy = (a1[0] - a0[0]) / length_a, (a1[1] - a0[1]) / length_a
    length_b = math.dist(b0[:2], b1[:2])
    vx, vy = (b1[0] - b0[0]) / length_b, (b1[1] - b0[1]) / length_b
    # Direction-insensitive angle between the two infinite lines.
    angle = math.degrees(math.acos(min(1.0, abs(ux * vx + uy * vy))))
    if angle > angle_tolerance + 1e-12:
        return None, "not_parallel"

    def along(p):
        return (p[0] - a0[0]) * ux + (p[1] - a0[1]) * uy

    def across(p):
        return (p[0] - a0[0]) * -uy + (p[1] - a0[1]) * ux

    tb = sorted((along(b0), along(b1)))
    start, end = max(0.0, tb[0]), min(length_a, tb[1])
    overlap = end - start
    if overlap <= EPS * max(length_a, length_b):
        return None, "no_projected_overlap"
    # Offsets of B over the shared interval; B is straight, so interpolation is exact.
    span = along(b1) - along(b0)

    def b_at(t):
        r = (t - along(b0)) / span
        return (b0[0] + r * (b1[0] - b0[0]), b0[1] + r * (b1[1] - b0[1]))

    offsets = [across(b_at(t)) for t in (start, end)]
    if offsets[0] * offsets[1] < 0 or min(abs(o) for o in offsets) <= EPS * max(length_a, length_b):
        return None, "touching_or_crossing"
    distances = [abs(o) for o in offsets]
    side = 1 if offsets[0] > 0 else -1

    def axis_point(t, offset):
        return [a0[0] + t * ux - uy * offset / 2, a0[1] + t * uy + ux * offset / 2, a0[2]]

    return {
        "separation_min": min(distances), "separation_max": max(distances),
        "separation_mean": sum(distances) / 2, "angle_deviation_degrees": angle,
        "overlap_length": overlap,
        "overlap_ratios": [overlap / length_a, overlap / length_b],
        "offset_side": side,
        "midline_wcs": [axis_point(start, offsets[0]), axis_point(end, offsets[1])],
    }, None


def find_parallel_pairs(candidates, separation_range, angle_tolerance_degrees=None,
                        entity_coverage_truncated=False, id_prefix="line_pair_",
                        review_key="requires_review", scope="selected_LINE_entities",
                        junction_tolerance=None, include_junctions=False):
    """Pairs of parallel LINEs whose offset lies in an explicit distance range.

    The result is geometric evidence only: the same line may pair with several
    partners, and nothing is merged, trimmed or classified.
    """
    validate_separation_range(separation_range)
    validate_angle_tolerance(angle_tolerance_degrees)
    tolerance = (DEFAULT_ANGLE_TOLERANCE_DEGREES if angle_tolerance_degrees is None
                 else angle_tolerance_degrees)
    eligible, excluded = eligible_lines(candidates)
    ids = {c["handles"][0]: c.get("id", c["handles"][0]) for c in candidates}
    low, high = separation_range
    pairs, reasons = [], Counter()
    for ha, hb in combinations(eligible, 2):
        measured, reason = _measure(eligible[ha], eligible[hb], tolerance)
        if reason:
            reasons[reason] += 1
            continue
        if measured["separation_min"] < low * (1 - 1e-9) or measured["separation_max"] > high * (1 + 1e-9):
            reasons["separation_out_of_range"] += 1
            continue
        key = "\0".join(sorted((ids[ha], ids[hb])))
        pairs.append({"id": id_prefix + hashlib.sha256(key.encode()).hexdigest()[:20],
                      "handles": [ha, hb], "source_ids": [ids[ha], ids[hb]],
                      "status": "candidate", **measured, review_key: True})
    usage = Counter(h for pair in pairs for h in pair["handles"])
    for pair in pairs:
        pair["shared_line_handles"] = sorted(h for h in pair["handles"] if usage[h] > 1)
        pair["ambiguous"] = bool(pair["shared_line_handles"])
    complete = not (excluded or entity_coverage_truncated)
    extra = {}
    if include_junctions:
        extra["pair_junctions"] = find_axis_junctions(
            [{"id": p["id"], "start": p["midline_wcs"][0], "end": p["midline_wcs"][1],
              "width": p["separation_max"]} for p in pairs], junction_tolerance)
    return {**extra,"scope": scope, "requested": True,
            "separation_range_drawing_units": [low, high],
            "angle_tolerance_degrees": tolerance,
            "eligible_lines": len(eligible), "excluded": excluded,
            "checked_pairs": len(eligible) * (len(eligible) - 1) // 2,
            "rejected_pair_counts": dict(sorted(reasons.items())),
            "pairs": pairs, "pair_count": len(pairs),
            "unpaired_handles": sorted(set(eligible) - set(usage)),
            "ambiguous_handles": sorted(h for h, n in usage.items() if n > 1),
            "coverage_complete": complete,
            "entity_coverage_truncated": entity_coverage_truncated,
            "interpretation": ("Parallel offset LINE pairs in the requested range; nothing is "
                               "merged or classified, and a line may belong to several pairs.")}
