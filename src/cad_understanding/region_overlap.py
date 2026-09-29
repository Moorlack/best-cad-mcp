"""Domain-neutral overlap of axis-aligned boxes with oriented bands (axis +/- half width)."""

import math

EPS = 1e-12


def band_polygon(start, end, width):
    """Counter-clockwise rectangle around the segment start-end, `width` wide."""
    (x0, y0), (x1, y1) = start[:2], end[:2]
    length = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / length * width / 2, (x1 - x0) / length * width / 2
    return [(x0 - nx, y0 - ny), (x1 - nx, y1 - ny), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)]


def _area(poly):
    return abs(sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))) / 2


def _side(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _clip(subject, clipper):
    """Sutherland-Hodgman clip of a polygon by a counter-clockwise convex polygon."""
    output = list(subject)
    for i in range(len(clipper)):
        a, b = clipper[i - 1], clipper[i]
        points, output = output, []
        for j in range(len(points)):
            p, q = points[j - 1], points[j]
            p_in, q_in = _side(a, b, p) >= -EPS, _side(a, b, q) >= -EPS
            if q_in != p_in:
                dp, dq = _side(a, b, p), _side(a, b, q)
                t = dp / (dp - dq)
                output.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
            if q_in:
                output.append(q)
        if not output:
            break
    return output


def _segment_inside_fraction(p, q, clipper):
    """Cyrus-Beck: fraction of segment p-q inside a counter-clockwise convex polygon."""
    t0, t1 = 0.0, 1.0
    for i in range(len(clipper)):
        a, b = clipper[i - 1], clipper[i]
        dp, dq = _side(a, b, p), _side(a, b, q)
        if dp < -EPS and dq < -EPS:
            return 0.0
        if dp < -EPS or dq < -EPS:
            t = dp / (dp - dq)
            if dp < -EPS:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return max(0.0, t1 - t0)


def box_band_overlap(bbox, band):
    """Share of the box that lies inside the band: by area, or by length for a flat box."""
    (x0, y0), (x1, y1) = bbox["min"][:2], bbox["max"][:2]
    span = max(x1 - x0, y1 - y0)
    if span <= 0:
        inside = all(_side(band[i - 1], band[i], (x0, y0)) >= -EPS for i in range(len(band)))
        return {"measure": "point", "ratio": 1.0 if inside else 0.0}
    if min(x1 - x0, y1 - y0) <= 1e-9 * span:
        return {"measure": "length", "ratio": _segment_inside_fraction((x0, y0), (x1, y1), band)}
    box = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    clipped = _clip(box, band)
    area = _area(clipped) if len(clipped) >= 3 else 0.0
    return {"measure": "area", "ratio": area / ((x1 - x0) * (y1 - y0))}
