"""Architectural adapter: spatially separate groups of wall segments (possible separate plans).

Model space often holds several floor plans, sections or details side by side. Grouping wall
segments by bounding-box proximity shows when one drawing contains several plan-like clusters.
This is a hint only: a cluster is not a storey, and no level or elevation is inferred.
"""

import hashlib
import math

from .spatial_pairs import pruned_pairs

MIN_SEGMENTS_PER_CLUSTER = 3
GAP_DIAGONAL_RATIO = 0.15
GAP_THICKNESS_MULTIPLE = 20.0


def find_plan_clusters(segments):
    """{clusters, cluster_count, gap_threshold_drawing_units, multiple_plan_clusters} over wall segments."""
    boxes = {}
    thickness = 0.0
    for s in segments:
        (x0, y0), (x1, y1) = s["axis_wcs"][0][:2], s["axis_wcs"][1][:2]
        boxes[s["id"]] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        thickness = max(thickness, float(s["thickness_drawing_units"]["max"]))
    result = {"clusters": [], "cluster_count": 0, "gap_threshold_drawing_units": None,
              "multiple_plan_clusters": False,
              "interpretation": ("Groups of wall segments separated by more than the gap threshold; possibly separate plans or "
                                 "details in one model space. A cluster is not a storey and no level is inferred.")}
    if len(boxes) < MIN_SEGMENTS_PER_CLUSTER:
        return result
    min_x = min(b[0] for b in boxes.values())
    min_y = min(b[1] for b in boxes.values())
    max_x = max(b[2] for b in boxes.values())
    max_y = max(b[3] for b in boxes.values())
    threshold = max(GAP_THICKNESS_MULTIPLE * thickness, GAP_DIAGONAL_RATIO * math.hypot(max_x - min_x, max_y - min_y))
    parent = {key: key for key in boxes}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    margin = threshold / 2.0
    for a, b in pruned_pairs(boxes, margin):
        ba, bb = boxes[a], boxes[b]
        # pruned_pairs may return every pair for small inputs, so test the proximity here too
        if not (ba[0] - margin <= bb[2] + margin and bb[0] - margin <= ba[2] + margin
                and ba[1] - margin <= bb[3] + margin and bb[1] - margin <= ba[3] + margin):
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for key in boxes:
        groups.setdefault(find(key), []).append(key)
    clusters = []
    for members in groups.values():
        members.sort()
        bx = [boxes[m] for m in members]
        clusters.append({"id": "plan_cluster_" + hashlib.sha256("\0".join(members).encode()).hexdigest()[:20],
                         "segment_count": len(members), "segment_ids": members[:50],
                         "segment_ids_truncated": len(members) > 50,
                         "bbox_wcs": {"min": [min(b[0] for b in bx), min(b[1] for b in bx)],
                                      "max": [max(b[2] for b in bx), max(b[3] for b in bx)]}})
    clusters.sort(key=lambda c: (-c["segment_count"], c["id"]))
    result.update(clusters=clusters, cluster_count=len(clusters), gap_threshold_drawing_units=threshold,
                  multiple_plan_clusters=sum(1 for c in clusters if c["segment_count"] >= MIN_SEGMENTS_PER_CLUSTER) >= 2)
    return result
