"""Architectural adapter: estimate the usual wall thickness from the drawn wall faces.

Callers rarely know the wall thickness range in drawing units. Each wall face is paired with its
nearest parallel overlapping wall face; the most common separation (log-scale histogram) is taken
as the typical thickness and a range around it is suggested. The estimate is a starting point for
pairing, never a verified wall type.
"""

import math
from collections import defaultdict

from .line_pairs import find_parallel_pairs
from .wall_lines import select_wall_faces

BIN_RATIO = 1.05
RANGE_LOW, RANGE_HIGH = 0.8, 1.25
MAX_SEPARATION_SHARE = 0.05  # of the wall-face extent diagonal
OPENING_WIDTH_FACTOR = 12.0


def estimate_wall_thickness(candidates):
    """{peak, range, pairs_considered, peak_share} or None when no plausible pairs exist."""
    selected, _ = select_wall_faces(candidates)
    points = []
    for face in selected:
        if face.get("excluded_reason") or face.get("shape") != "line":
            continue
        g = face.get("geometry") or {}
        for key in ("start", "end"):
            p = g.get(key)
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                points.append((float(p[0]), float(p[1])))
    if len(points) < 4:
        return None
    diag = math.hypot(max(p[0] for p in points) - min(p[0] for p in points),
                      max(p[1] for p in points) - min(p[1] for p in points))
    if diag <= 0:
        return None
    pairs = find_parallel_pairs(selected, [diag * 1e-6, diag * MAX_SEPARATION_SHARE])["pairs"]
    # Canonical direction per face so "which side" is comparable between a face and its partners.
    flip = {}
    for face in selected:
        g = face.get("geometry") or {}
        a, b = g.get("start"), g.get("end")
        if face.get("handles") and isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            dx, dy = b[0] - a[0], b[1] - a[1]
            flip[face["handles"][0]] = 1 if (dx > 1e-12 or (abs(dx) <= 1e-12 and dy > 0)) else -1
    neighbours = defaultdict(list)  # handle -> [(separation, side of the partner)]
    for pair in pairs:
        first, second = pair["handles"]
        side = pair["offset_side"] * flip.get(first, 1)
        neighbours[first].append((pair["separation_mean"], side))
        neighbours[second].append((pair["separation_mean"], -side))

    def stacked(handle, separation, side):
        # A face with parallel neighbours at similar distance on BOTH sides belongs to a periodic
        # stack (hatching, arrays, stairs), not to a wall with two faces.
        return any(s <= 1.5 * separation and other == -side for s, other in neighbours[handle])

    nearest = {}
    for pair in pairs:
        for handle in pair["handles"]:
            if handle not in nearest or pair["separation_mean"] < nearest[handle]["separation_mean"]:
                nearest[handle] = pair
    unique = []
    for pair in {pair["id"]: pair for pair in nearest.values()}.values():
        first, second = pair["handles"]
        side = pair["offset_side"] * flip.get(first, 1)
        if not (stacked(first, pair["separation_mean"], side) or stacked(second, pair["separation_mean"], -side)):
            unique.append(pair)
    bins = defaultdict(list)
    for pair in unique:
        value = pair["separation_mean"]
        if value > 0:
            bins[round(math.log(value) / math.log(BIN_RATIO))].append(value)
    if not bins:
        return None
    best = max(bins, key=lambda key: (len(bins[key]) + 0.5 * (len(bins.get(key - 1, ())) + len(bins.get(key + 1, ()))), -key))
    values = bins[best] + bins.get(best - 1, []) + bins.get(best + 1, [])
    peak = sorted(values)[len(values) // 2]
    total = sum(len(v) for v in bins.values())
    return {"peak_drawing_units": peak, "range_drawing_units": [peak * RANGE_LOW, peak * RANGE_HIGH],
            "pairs_considered": total, "peak_share": len(values) / total,
            "suggested_opening_max_width_drawing_units": peak * OPENING_WIDTH_FACTOR,
            "method": "most common nearest parallel wall-face separation (log histogram, 5% bins)",
            "verified": False}
