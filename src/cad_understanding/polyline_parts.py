"""Domain-neutral split of straight polyline segments into LINE-like records.

Each part keeps the source handle and segment index; its internal key is
"<handle>#<index>" so several parts of one polyline can be compared with each
other (e.g. the two long sides of a wall drawn as one closed outline). Arc
segments (non-zero bulge) are reported, not flattened.
"""

import math

EPS = 1e-12
POLYLINE_KINDS = {"polyline", "2dpolyline", "lwpolyline"}


def _point(p):
    try:
        return (isinstance(p, (list, tuple)) and len(p) in (2, 3)
                and all(type(v) in (int, float) and math.isfinite(v) for v in p))
    except OverflowError:
        return False


def part_key(handle, index):
    return f"{handle}#{index}"


def split_polyline(handle, geometry, base_id, layer="0"):
    """Returns (parts, excluded) for one polyline's geometry dict."""
    vertices = geometry.get("vertices", geometry.get("points", []))
    if not isinstance(vertices, list) or len(vertices) < 2 or not all(_point(v) for v in vertices):
        return [], [{"handle": handle, "reason": "invalid_polyline_vertices"}]
    points = [tuple(v) + ((0.0,) if len(v) == 2 else ()) for v in vertices]
    closed = geometry.get("closed") is True
    if closed and points[0][:2] == points[-1][:2]:
        points = points[:-1]
    bulges = geometry.get("bulges")
    if not isinstance(bulges, list) or geometry.get("bulges_complete") is False:
        return [], [{"handle": handle, "reason": "polyline_bulges_not_captured"}]
    count = len(points) if closed else len(points) - 1
    parts, excluded = [], []
    for i in range(count):
        a, b = points[i], points[(i + 1) % len(points)]
        bulge = bulges[i] if i < len(bulges) else 0.0
        key = part_key(handle, i)
        if type(bulge) not in (int, float) or not math.isfinite(bulge) or abs(bulge) > EPS:
            excluded.append({"handle": key, "reason": "arc_segment_not_supported"})
            continue
        if math.dist(a[:2], b[:2]) <= EPS:
            excluded.append({"handle": key, "reason": "degenerate_segment"})
            continue
        parts.append({"id": f"{base_id}#{i}", "handles": [key], "shape": "line", "excluded_reason": None,
                      "geometry": {"start": list(a), "end": list(b)}, "layer": layer,
                      "source": {"handle": handle, "segment_index": i,
                                 "segment_count": count, "closed": closed}})
    return parts, excluded


def adjacent_parts(a, b):
    """True for consecutive segments of one polyline, which touch by construction."""
    sa, sb = a.get("source") or {}, b.get("source") or {}
    if not sa or sa.get("handle") != sb.get("handle") or sa.get("segment_index") is None:
        return False
    i, j, n = sa["segment_index"], sb["segment_index"], sa.get("segment_count") or 0
    return abs(i - j) == 1 or (bool(sa.get("closed")) and n > 2 and {i, j} == {0, n - 1})


def source_of(key):
    """Native handle and segment index for a part key (None index for a plain LINE)."""
    handle, sep, index = str(key).rpartition("#")
    if sep and index.isdigit():
        return {"handle": handle, "segment_index": int(index)}
    return {"handle": str(key), "segment_index": None}
