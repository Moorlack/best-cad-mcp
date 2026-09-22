"""Conservative checks for single horizontal, straight-edged closed polylines."""

import math

MAX_VERTICES = 256
EPS = 1e-9  # Relative to the largest XY extent; coordinates are normalized first.


def check_boundary(geometry):
    result = {"status": "not_verified", "reason": "missing_geometry",
              "geometric_area_drawing_units_squared": None,
              "floor_area_verified": False, "holes_checked": False,
              "relative_tolerance": EPS}

    def stop(reason, status="not_verified"):
        result.update(status=status, reason=reason)
        return result

    vertices = geometry.get("vertices", geometry.get("points"))
    if not isinstance(vertices, list) or len(vertices) < 3:
        return stop("too_few_vertices", "invalid")
    if len(vertices) > MAX_VERTICES:
        return stop("vertex_limit_exceeded")
    if not all(isinstance(p, (list, tuple)) and len(p) in (2, 3)
               and all(type(v) in (int, float) and math.isfinite(v) for v in p)
               for p in vertices):
        return stop("invalid_coordinates", "invalid")
    points = [tuple(float(v) for v in p) + ((0.0,) if len(p) == 2 else ()) for p in vertices]
    repeated_end = points[0] == points[-1]
    if geometry.get("closed") is not True and not repeated_end:
        return stop("open_contour", "invalid")
    bulges = geometry.get("bulges")
    if (geometry.get("bulges_complete") is not True
            or not isinstance(bulges, list) or len(bulges) != len(points)):
        return stop("curve_data_incomplete")
    if not all(type(v) in (int, float) and math.isfinite(v) for v in bulges):
        return stop("curve_data_incomplete")
    if any(v != 0 for v in bulges):
        return stop("curved_segments_unsupported")
    if repeated_end:
        points.pop()
    if len(points) < 3:
        return stop("too_few_vertices", "invalid")
    # Only horizontal WCS contours are supported. Unknown/non-WCS coordinates
    # with a tilted normal must not be projected to XY and reported as an area.
    normal = geometry.get("normal")
    if (not isinstance(normal, (list, tuple)) or len(normal) != 3
                              or not all(type(v) in (int, float) and math.isfinite(v) for v in normal)
                              or abs(normal[0]) > EPS or abs(normal[1]) > EPS
                              or abs(abs(normal[2]) - 1) > EPS):
        return stop("non_horizontal_plane")
    if geometry.get("vertices_coordinate_system") != "WCS":
        return stop("coordinate_system_unsupported")
    span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in (0, 1))
    if not math.isfinite(span):
        return stop("numeric_range_exceeded")
    if span == 0:
        return stop("zero_extent", "invalid")
    if max(p[2] for p in points) - min(p[2] for p in points) > EPS * span:
        return stop("non_horizontal_plane")
    x, y, _ = points[0]
    pts = [((p[0] - x) / span, (p[1] - y) / span) for p in points]
    n = len(pts)
    for i in range(n):
        for j in range(i + 1, n):
            if max(abs(pts[i][k] - pts[j][k]) for k in (0, 1)) <= EPS:
                return stop("repeated_or_near_coincident_vertex", "invalid")

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def intersects(a, b, c, d):
        if any(max(a[k], b[k]) < min(c[k], d[k]) - EPS
               or max(c[k], d[k]) < min(a[k], b[k]) - EPS for k in (0, 1)):
            return False
        values = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
        signs = [1 if v > EPS else -1 if v < -EPS else 0 for v in values]
        return signs[0] * signs[1] <= 0 and signs[2] * signs[3] <= 0

    for i, a in enumerate(pts):
        b, previous = pts[(i + 1) % n], pts[i - 1]
        if abs(cross(previous, a, b)) <= EPS and sum(
                (previous[k] - a[k]) * (b[k] - a[k]) for k in (0, 1)) > EPS:
            return stop("overlapping_adjacent_edges", "invalid")
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if intersects(a, b, pts[j], pts[(j + 1) % n]):
                return stop("self_intersection_or_touch", "invalid")
    area_normalized = abs(math.fsum(pts[i][0] * pts[(i + 1) % n][1]
                                   - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    if area_normalized <= EPS:
        return stop("degenerate_area", "invalid")
    area = area_normalized * span * span
    if not math.isfinite(area) or area == 0:
        return stop("numeric_range_exceeded")
    result.update(status="valid_simple_polygon", reason=None,
                  geometric_area_drawing_units_squared=area)
    return result
