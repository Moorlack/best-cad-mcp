"""Relations between already validated simple horizontal WCS polygons.

Containment is geometric evidence only: a nested outline is not a proven hole.
"""

import math
from itertools import combinations

from .boundaries import EPS

MAX_EDGE_COMPARISONS = 500000


def _points(geometry):
    points = [tuple(p) if len(p) == 3 else (*p, 0.0)
              for p in geometry.get("vertices", geometry.get("points", []))]
    if points[0] == points[-1]:
        points.pop()
    return points


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _contact(a, b, c, d):
    if any(max(a[k], b[k]) < min(c[k], d[k]) - EPS
           or max(c[k], d[k]) < min(a[k], b[k]) - EPS for k in (0, 1)):
        return False
    values = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    signs = [1 if v > EPS else -1 if v < -EPS else 0 for v in values]
    return signs[0] * signs[1] <= 0 and signs[2] * signs[3] <= 0


def _inside(point, polygon):
    x, y = point
    inside = False
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        if (a[1] > y) != (b[1] > y):
            at_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < at_x:
                inside = not inside
    return inside


def _relation(a, b):
    span_a, span_b = [max(max(p[k] for p in poly) - min(p[k] for p in poly)
                          for k in (0, 1)) for poly in (a, b)]
    # Require the entire pair to share a horizontal plane within the smaller
    # contour's tolerance; don't identify a floor above as a hole below.
    tolerance = EPS * min(span_a, span_b)
    heights = [p[2] for p in a + b]
    if max(heights) - min(heights) > tolerance:
        return "different_planes"
    span = max(max(p[k] for p in a + b) - min(p[k] for p in a + b) for k in (0, 1))
    if not math.isfinite(span) or span == 0:
        return "numeric_range_exceeded"
    x, y, _ = a[0]
    a, b = [[((p[0] - x) / span, (p[1] - y) / span) for p in poly] for poly in (a, b)]
    if any(max(p[k] for p in a) < min(p[k] for p in b) - EPS
           or max(p[k] for p in b) < min(p[k] for p in a) - EPS for k in (0, 1)):
        return "disjoint"
    if min(span_a, span_b) / span < 1e-6:
        return "scale_disparity_unverified"
    for i, start in enumerate(a):
        for j, other in enumerate(b):
            if _contact(start, a[(i + 1) % len(a)], other, b[(j + 1) % len(b)]):
                return "intersection_or_touch"
    if _inside(b[0], a):
        return "a_contains_b"
    if _inside(a[0], b):
        return "b_contains_a"
    return "disjoint"


def check_boundary_relations(valid_geometries):
    """Input contains only unique handles with valid_simple_polygon checks."""
    polygons = {h: _points(g) for h, g in sorted(valid_geometries.items())}
    budget = MAX_EDGE_COMPARISONS
    result = {"items": [], "eligible_contours": len(polygons),
              "total_pairs": len(polygons) * (len(polygons) - 1) // 2,
              "checked_pairs": 0, "different_plane_pairs": 0,
              "unverified_pairs": 0, "unverified_pair_samples": [],
              "holes_confirmed": False, "net_area_calculated": False,
              "relative_tolerance": EPS}
    for ha, hb in combinations(polygons, 2):
        a, b = polygons[ha], polygons[hb]
        cost = len(a) * len(b)
        if cost > budget:
            relation = "comparison_budget_exceeded"
        else:
            budget -= cost
            relation = _relation(a, b)
        if relation in {"comparison_budget_exceeded", "numeric_range_exceeded", "scale_disparity_unverified"}:
            result["unverified_pairs"] += 1
            if len(result["unverified_pair_samples"]) < 20:
                result["unverified_pair_samples"].append({"handles": [ha, hb], "reason": relation})
            continue
        result["checked_pairs"] += 1
        if relation == "different_planes":
            result["different_plane_pairs"] += 1
        elif relation in {"a_contains_b", "b_contains_a"}:
            outer, inner = (ha, hb) if relation == "a_contains_b" else (hb, ha)
            result["items"].append({"relation": "contains", "outer_handle": outer,
                                    "inner_handle": inner, "hole_status": "unverified"})
        elif relation == "intersection_or_touch":
            result["items"].append({"relation": relation, "handles": [ha, hb]})
    return result
