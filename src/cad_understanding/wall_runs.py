"""Architectural adapter: chain collinear wall segments (across gaps) into candidate wall runs.

A run is a review aid: segments on one axis line, linked by collinear gaps or axis overlaps.
Corners and T-junctions never merge segments, nothing is trimmed, and a gap inside a run is
not confirmed as an opening.
"""

import hashlib
import math

LINK_KINDS = {"collinear_gap", "parallel_overlap"}


def _components(ids, links):
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return [sorted(members) for members in groups.values()]


def build_wall_runs(segments, junctions):
    """Runs of two or more collinear segments; single segments are not repeated as runs."""
    by_id = {s["id"]: s for s in segments}
    links, link_junctions = [], []
    for junction in junctions:
        if junction.get("kind") in LINK_KINDS and all(i in by_id for i in junction.get("segment_ids", [])):
            links.append(tuple(junction["segment_ids"]))
            link_junctions.append(junction)
    runs = []
    for members in sorted(_components(sorted(by_id), links)):
        if len(members) < 2:
            continue
        first = by_id[members[0]]["axis_wcs"]
        ox, oy = first[0][0], first[0][1]
        dx, dy = first[1][0] - ox, first[1][1] - oy
        norm = math.hypot(dx, dy)
        ux, uy = dx / norm, dy / norm
        intervals = []
        for segment_id in members:
            (x0, y0), (x1, y1) = by_id[segment_id]["axis_wcs"][0][:2], by_id[segment_id]["axis_wcs"][1][:2]
            t0, t1 = sorted(((x0 - ox) * ux + (y0 - oy) * uy, (x1 - ox) * ux + (y1 - oy) * uy))
            intervals.append((t0, t1))
        lo, hi = min(i[0] for i in intervals), max(i[1] for i in intervals)
        drawn, cursor = 0.0, None
        for t0, t1 in sorted(intervals):
            start = t0 if cursor is None else max(t0, cursor)
            if t1 > start:
                drawn += t1 - start
            cursor = t1 if cursor is None else max(cursor, t1)
        thicknesses = [by_id[i]["thickness_drawing_units"] for i in members]
        gaps = [j for j in link_junctions if set(j["segment_ids"]) <= set(members) and j["kind"] == "collinear_gap"]
        overlaps = [j for j in link_junctions if set(j["segment_ids"]) <= set(members) and j["kind"] == "parallel_overlap"]
        thin, thick = min(t["min"] for t in thicknesses), max(t["max"] for t in thicknesses)
        runs.append({"id": "wall_run_" + hashlib.sha256("\0".join(members).encode()).hexdigest()[:20],
                     "segment_ids": members,
                     "axis_wcs": [[ox + ux * lo, oy + uy * lo], [ox + ux * hi, oy + uy * hi]],
                     "span_length": hi - lo, "drawn_length": drawn, "gap_length_total": max(0.0, hi - lo - drawn),
                     "gap_count": len(gaps), "overlap_count": len(overlaps),
                     "thickness_drawing_units": {"min": thin, "max": thick},
                     "thickness_varies": thick - thin > 0.25 * thick,
                     "status": "candidate", "physical_wall_verified": False,
                     "requires_architectural_review": True})
    return runs
