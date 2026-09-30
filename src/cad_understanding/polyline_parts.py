"""Domain-neutral split of straight polyline segments into LINE-like records.

Each part keeps the source handle and segment index; its internal key is
"<handle>#<index>" so several parts of one polyline can be compared with each
other (e.g. the two long sides of a wall drawn as one closed outline). Arc
segments (non-zero bulge) are reported, not flattened.
"""

import math

from src.mline_styles import face_offsets

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


# STANDARD MLINE style: two elements at +0.5 and -0.5 (positive = left of the
# drawing direction). Justification moves the vertices onto the top (0), the
# centre (1) or the bottom (2) element. Other styles' offsets are not exposed by COM;
# they arrive as geometry['mline_style_offsets'] (see src/mline_styles.py).
STANDARD_MLINE_OFFSETS = {0: (0.0, -1.0), 1: (0.5, -0.5), 2: (1.0, 0.0)}


def _offset_chain(points, offset):
    """Mitered offset of an open chain; parallel neighbours fall back to a plain offset."""
    normals = []
    for a, b in zip(points, points[1:]):
        length = math.dist(a[:2], b[:2])
        normals.append((-(b[1] - a[1]) / length, (b[0] - a[0]) / length))
    out = []
    for j, p in enumerate(points):
        if j == 0 or j == len(points) - 1:
            n = normals[0] if j == 0 else normals[-1]
            out.append((p[0] + n[0] * offset, p[1] + n[1] * offset, p[2]))
            continue
        n1, n2 = normals[j - 1], normals[j]
        denom = 1 + n1[0] * n2[0] + n1[1] * n2[1]
        if denom < 1e-9:  # reversal; keep the incoming offset
            out.append((p[0] + n1[0] * offset, p[1] + n1[1] * offset, p[2]))
            continue
        # Miter point: offset along the bisector, scaled by 1/cos(half angle).
        mx, my = (n1[0] + n2[0]) / denom, (n1[1] + n2[1]) / denom
        out.append((p[0] + mx * offset, p[1] + my * offset, p[2]))
    return out


def split_mline(handle, geometry, base_id, layer="0"):
    """Face segments of an MLINE (STANDARD, or a style with scanned offsets); returns (parts, excluded)."""
    vertices = geometry.get("vertices", [])
    style = str(geometry.get("mline_style") or "")
    scale, just = geometry.get("mline_scale"), geometry.get("mline_justification")
    if "vertices" not in geometry:
        return [], [{"handle": handle, "reason": "geometry_not_captured"}]
    if not isinstance(vertices, list) or len(vertices) < 2 or not all(_point(v) for v in vertices):
        return [], [{"handle": handle, "reason": "invalid_mline_vertices"}]
    if type(scale) not in (int, float) or not math.isfinite(scale) or just not in STANDARD_MLINE_OFFSETS:
        return [], [{"handle": handle, "reason": "mline_scale_or_justification_missing"}]
    if style.upper() == "STANDARD":
        element_offsets = STANDARD_MLINE_OFFSETS[just]
    else:
        # Other styles: the two outermost elements are the wall faces; offsets come from
        # the style read at scan time (DXF export), never guessed.
        style_offsets = geometry.get("mline_style_offsets")
        if not style_offsets:
            return [], [{"handle": handle, "reason": "mline_style_offsets_unknown"}]
        element_offsets = face_offsets(style_offsets, just)
        if element_offsets is None:
            return [], [{"handle": handle, "reason": "mline_style_offsets_invalid"}]
    points = [tuple(v) + ((0.0,) if len(v) == 2 else ()) for v in vertices]
    points = [p for i, p in enumerate(points) if i == 0 or math.dist(p[:2], points[i - 1][:2]) > EPS]
    if len(points) < 2:
        return [], [{"handle": handle, "reason": "degenerate_segment"}]
    parts = []
    count = len(points) - 1
    for k, offset in enumerate(element_offsets):
        chain = _offset_chain(points, offset * scale)
        for i in range(count):
            key = f"{handle}#e{k}s{i}"
            parts.append({"id": f"{base_id}#e{k}s{i}", "handles": [key], "shape": "line", "excluded_reason": None,
                          "geometry": {"start": list(chain[i]), "end": list(chain[i + 1])}, "layer": layer,
                          "source": {"handle": handle, "element": k, "segment_index": i,
                                     "segment_count": count, "closed": False}})
    return parts, []


def adjacent_parts(a, b):
    """True for consecutive segments of one polyline (or MLINE element), which touch by construction."""
    sa, sb = a.get("source") or {}, b.get("source") or {}
    if not sa or sa.get("handle") != sb.get("handle") or sa.get("segment_index") is None:
        return False
    if sa.get("element") != sb.get("element"):
        return False
    i, j, n = sa["segment_index"], sb["segment_index"], sa.get("segment_count") or 0
    return abs(i - j) == 1 or (bool(sa.get("closed")) and n > 2 and {i, j} == {0, n - 1})


def source_of(key):
    """Native handle and segment index for a part key (None index for a plain LINE)."""
    handle, sep, index = str(key).rpartition("#")
    if sep and index.isdigit():
        return {"handle": handle, "segment_index": int(index)}
    if sep and index.startswith("e") and "s" in index:
        element, _, segment = index[1:].partition("s")
        if element.isdigit() and segment.isdigit():
            return {"handle": handle, "element": int(element), "segment_index": int(segment)}
    return {"handle": str(key), "segment_index": None}
