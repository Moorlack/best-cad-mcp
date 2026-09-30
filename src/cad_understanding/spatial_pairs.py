"""Candidate pairs of items whose bounding boxes come within a margin of each other.

Plan drawings hold thousands of wall faces but each only interacts with neighbours. Checking
every pair is quadratic, so large inputs first keep only pairs whose boxes (grown by the margin
the caller needs) overlap. The pairs come back in the same order as itertools.combinations over
the keys, so results stay deterministic, and small inputs can skip pruning entirely.
"""

import math
from collections import defaultdict
from itertools import combinations

PRUNE_THRESHOLD = 150   # below this many items all pairs are checked, exactly as before
MAX_CELLS_PER_BOX = 400


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def pruned_pairs(boxes, margin):
    """boxes: {key: (minx, miny, maxx, maxy)} in insertion order.

    Returns [(key_a, key_b)] in combinations order, limited to pairs whose boxes grown by
    `margin` on each side overlap. Falls back to all pairs for small inputs.
    """
    keys = list(boxes)
    if len(keys) <= PRUNE_THRESHOLD:
        return list(combinations(keys, 2))
    margin = max(float(margin), 0.0)
    index = {key: i for i, key in enumerate(keys)}
    grown = {key: (b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin) for key, b in boxes.items()}
    extents = sorted(max(b[2] - b[0], b[3] - b[1]) for b in grown.values())
    cell = max(extents[len(extents) // 2], 1e-9)
    cells = defaultdict(list)
    oversized = []
    for key, (x0, y0, x1, y1) in grown.items():
        cx0, cx1 = math.floor(x0 / cell), math.floor(x1 / cell)
        cy0, cy1 = math.floor(y0 / cell), math.floor(y1 / cell)
        if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) > MAX_CELLS_PER_BOX:
            oversized.append(key)
            continue
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                cells[(cx, cy)].append(key)
    found = set()

    def overlaps(a, b):
        ba, bb = grown[a], grown[b]
        return ba[0] <= bb[2] and bb[0] <= ba[2] and ba[1] <= bb[3] and bb[1] <= ba[3]

    for members in cells.values():
        for a, b in combinations(members, 2):
            if overlaps(a, b):
                found.add((a, b) if index[a] < index[b] else (b, a))
    for big in oversized:
        for other in keys:
            if other != big and overlaps(big, other):
                found.add((big, other) if index[big] < index[other] else (other, big))
    return sorted(found, key=lambda pair: (index[pair[0]], index[pair[1]]))


def line_boxes(lines):
    """{key: bbox} from {key: [point, point, ...]}."""
    return {key: _bbox(points) for key, points in lines.items()}
