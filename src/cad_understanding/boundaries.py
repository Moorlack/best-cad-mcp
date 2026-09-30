"""Conservative checks for single horizontal closed polylines (straight or bulged edges)."""

import math

MAX_VERTICES = 256
MAX_BOUNDARY_CHECKS = 500  # contours checked per report; the rest are listed as not verified
MAX_FLATTENED_VERTICES = 1024
MAX_BULGE = 1e6
ARC_STEP = math.pi / 18  # 10 degrees per chord when an arc is flattened for the intersection test
EPS = 1e-9  # Relative to the largest XY extent; coordinates are normalized first.


def _arc_points(start, end, bulge):
    """Interior points of a bulged segment plus its exact signed area against the chord.

    Positive bulge is counter-clockwise from start to end and bulges to the right of the
    chord direction; replacing a chord by such an arc adds the segment area to a
    counter-clockwise signed area.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = math.hypot(dx, dy)
    sign = 1.0 if bulge > 0 else -1.0
    sweep = 4.0 * math.atan(abs(bulge))
    sagitta = abs(bulge) * chord / 2.0
    radius = (chord * chord / 4.0 + sagitta * sagitta) / (2.0 * sagitta)
    normal = (dy / chord, -dx / chord)  # right of the chord direction
    mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    arc_mid = (mid[0] + normal[0] * sign * sagitta, mid[1] + normal[1] * sign * sagitta)
    center = (arc_mid[0] - sign * radius * normal[0], arc_mid[1] - sign * radius * normal[1])
    first = math.atan2(start[1] - center[1], start[0] - center[0])
    steps = max(4, math.ceil(sweep / ARC_STEP))
    points = [(center[0] + radius * math.cos(first + sign * sweep * k / steps),
               center[1] + radius * math.sin(first + sign * sweep * k / steps)) for k in range(1, steps)]
    return points, sign * radius * radius / 2.0 * (sweep - math.sin(sweep))


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
    curved = sum(1 for v in bulges if v != 0)
    if curved and any(abs(v) > MAX_BULGE for v in bulges):
        return stop("curve_data_incomplete")
    if repeated_end:
        points.pop()
        bulges = list(bulges[:-1])
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
    if curved and normal[2] < 0:
        return stop("curved_segments_unsupported")
    span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in (0, 1))
    if not math.isfinite(span):
        return stop("numeric_range_exceeded")
    if span == 0:
        return stop("zero_extent", "invalid")
    if max(p[2] for p in points) - min(p[2] for p in points) > EPS * span:
        return stop("non_horizontal_plane")
    x, y, _ = points[0]
    pts = [((p[0] - x) / span, (p[1] - y) / span) for p in points]
    arc_area = 0.0
    original = list(pts)
    if curved:
        flat = []
        for i, vertex in enumerate(pts):
            flat.append(vertex)
            if bulges[i] != 0:
                inner, segment = _arc_points(vertex, pts[(i + 1) % len(pts)], float(bulges[i]))
                flat.extend(inner)
                arc_area += segment
        if len(flat) > MAX_FLATTENED_VERTICES:
            return stop("vertex_limit_exceeded")
        pts = flat
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
    if curved:
        # Exact area: chord polygon plus signed circular segments (flattened points only test simplicity).
        m = len(original)
        chord_area = math.fsum(original[i][0] * original[(i + 1) % m][1]
                               - original[(i + 1) % m][0] * original[i][1] for i in range(m)) / 2
        area_normalized = abs(chord_area + arc_area)
    else:
        area_normalized = abs(math.fsum(pts[i][0] * pts[(i + 1) % n][1]
                                       - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    if area_normalized <= EPS:
        return stop("degenerate_area", "invalid")
    area = area_normalized * span * span
    if not math.isfinite(area) or area == 0:
        return stop("numeric_range_exceeded")
    if curved:
        result.update(status="valid_curved_contour", reason=None, curved_segments=curved,
                      geometric_area_drawing_units_squared=area,
                      curve_check="self-intersection tested on a 10-degree chord approximation; area is exact")
    else:
        result.update(status="valid_simple_polygon", reason=None,
                      geometric_area_drawing_units_squared=area)
    return result
