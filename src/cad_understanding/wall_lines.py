"""Bounded diagnostics for named wall LINE candidates, not physical walls."""

import math
from itertools import combinations

EPS = 1e-9
MAX_LINES = 100


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _near(a, b):
    return max(abs(a[k] - b[k]) for k in (0, 1)) <= EPS


def _pair(first, second):
    points = first + second
    lengths = [math.dist(segment[0][:2], segment[1][:2]) for segment in (first, second)]
    if not all(math.isfinite(length) and length > 0 for length in lengths):
        return "not_verified"
    if max(p[2] for p in points) - min(p[2] for p in points) > EPS * min(lengths):
        return "different_planes"
    span = max(max(p[k] for p in points) - min(p[k] for p in points) for k in (0, 1))
    if not math.isfinite(span) or span <= 0:
        return "not_verified"
    origin = points[0]
    a, b, c, d = [tuple((p[k] - origin[k]) / span for k in (0, 1)) for p in points]
    if any(max(a[k], b[k]) < min(c[k], d[k]) - EPS
           or max(c[k], d[k]) < min(a[k], b[k]) - EPS for k in (0, 1)):
        return "disjoint"
    if min(lengths) / span < 1e-6:
        return "not_verified"
    if (_near(a, c) and _near(b, d)) or (_near(a, d) and _near(b, c)):
        return "duplicate"
    values = [_cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)]
    signs = [1 if v > EPS else -1 if v < -EPS else 0 for v in values]
    if all(s == 0 for s in signs):
        axis = 0 if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else 1
        overlap = min(max(a[axis], b[axis]), max(c[axis], d[axis])) - max(
            min(a[axis], b[axis]), min(c[axis], d[axis]))
        return "overlap" if overlap > EPS else "endpoint_joint"
    if signs[0] * signs[1] < 0 and signs[2] * signs[3] < 0:
        return "intersection"
    if signs[0] * signs[1] <= 0 and signs[2] * signs[3] <= 0:
        return "endpoint_joint" if any(_near(p, q) for p in (a, b) for q in (c, d)) else "t_junction"
    return "disjoint"


def diagnose_wall_lines(candidates, entity_coverage_truncated=False):
    eligible, excluded = {}, []
    wall_candidates = [c for c in candidates if c["category"] == "wall"]
    for candidate in sorted(wall_candidates, key=lambda c: c["handles"][0]):
        handle = candidate["handles"][0]
        if candidate["shape"] != "line" or "conflicting_semantic_hints" in candidate["warnings"]:
            excluded.append({"handle": handle, "reason": "unsupported_shape_or_conflicting_names"})
            continue
        g = candidate["geometry"]
        points = [g.get("start", g.get("start_point")), g.get("end", g.get("end_point"))]
        points = [tuple(p) + ((0.0,) if len(p) == 2 else ()) for p in points]
        length = math.dist(points[0][:2], points[1][:2])
        if not math.isfinite(length) or length <= 0 or abs(points[0][2] - points[1][2]) > EPS * length:
            excluded.append({"handle": handle, "reason": "non_horizontal_or_degenerate_line"})
        elif len(eligible) >= MAX_LINES:
            excluded.append({"handle": handle, "reason": "line_limit_exceeded"})
        else:
            eligible[handle] = points
    result = {"scope": "named_wall_LINE_candidates_only", "candidate_count": len(wall_candidates),
              "eligible_lines": len(eligible), "excluded": excluded,
              "total_pairs": len(eligible) * (len(eligible) - 1) // 2,
              "checked_pairs": 0, "different_plane_pairs": 0, "unverified_pairs": [],
              "items": [], "entity_coverage_truncated": entity_coverage_truncated,
              "relative_tolerance": EPS, "physical_walls_assembled": False,
              "gaps_checked": False}
    for ha, hb in combinations(eligible, 2):
        relation = _pair(eligible[ha], eligible[hb])
        if relation == "not_verified":
            result["unverified_pairs"].append([ha, hb])
            continue
        result["checked_pairs"] += 1
        if relation == "different_planes":
            result["different_plane_pairs"] += 1
        elif relation != "disjoint":
            result["items"].append({"relation": relation, "handles": [ha, hb],
                                    "requires_architectural_review": True})
    return result
