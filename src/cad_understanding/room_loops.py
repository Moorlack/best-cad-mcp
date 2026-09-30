"""Architectural adapter: enclosed loops of wall-segment axes as room-area candidates.

The axes of paired wall faces are joined at the junction points already found (corners,
T-junctions, crossings) and, optionally, across opening gaps; the bounded faces of that planar
graph are candidate enclosed regions. Areas are measured on the wall AXES (wall thickness is not
subtracted) and a loop closed only through an opening gap is marked. Nothing here names a room,
confirms a floor area or assigns use; a region without a matching room symbol is only a loop.
"""

import hashlib
import math

MAX_LOOP_AXES = 5000
MIN_AREA_RATIO = 1e-9  # share of the squared drawing extent below which a face is ignored


def _param(point, origin, unit):
    return (point[0] - origin[0]) * unit[0] + (point[1] - origin[1]) * unit[1]


def _cluster(points, tolerance, anchors=()):
    """Union points closer than tolerance; returns (labels, cluster centres).

    A cluster containing anchor points (junction points, where axes meet exactly) is centred on
    their mean; otherwise on the mean of all its points.
    """
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = max(tolerance, 1e-9)
    grid = {}
    for i, p in enumerate(points):
        grid.setdefault((math.floor(p[0] / cell), math.floor(p[1] / cell)), []).append(i)
    for i, p in enumerate(points):
        cx, cy = math.floor(p[0] / cell), math.floor(p[1] / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((cx + dx, cy + dy), ()):
                    if j > i and math.dist(p, points[j]) <= tolerance:
                        parent[find(j)] = find(i)
    roots = {}
    labels = []
    for i in range(len(points)):
        labels.append(roots.setdefault(find(i), len(roots)))
    sums = {}
    for i, label in enumerate(labels):
        entry = sums.setdefault(label, {"all": [0.0, 0.0, 0], "anchor": [0.0, 0.0, 0]})
        for key in ("all", "anchor") if i in anchors else ("all",):
            entry[key][0] += points[i][0]
            entry[key][1] += points[i][1]
            entry[key][2] += 1
    centres = []
    for label in range(len(roots)):
        entry = sums[label]
        total = entry["anchor"] if entry["anchor"][2] else entry["all"]
        centres.append((total[0] / total[2], total[1] / total[2]))
    return labels, centres


def find_room_loops(segments, junctions, gaps=None, tolerance=None):
    """Bounded faces of the wall-axis graph; segments need id, axis_wcs and thickness_drawing_units."""
    usable = [s for s in segments if len(s.get("axis_wcs", [])) == 2
              and math.dist(s["axis_wcs"][0][:2], s["axis_wcs"][1][:2]) > 0][:MAX_LOOP_AXES]
    result = {"requested": True, "loops": [], "loop_count": 0, "area_basis": "wall_axis_polygon",
              "coverage_complete": len(usable) == len(segments),
              "interpretation": ("Enclosed regions of the wall-axis graph, areas on axes (thickness not subtracted); "
                                 "not confirmed rooms or floor areas. Loops closed across an opening gap are marked.")}
    if len(usable) < 3:
        return result
    axes = {s["id"]: (tuple(s["axis_wcs"][0][:2]), tuple(s["axis_wcs"][1][:2])) for s in usable}
    widths = [s["thickness_drawing_units"]["max"] for s in usable]
    tol = tolerance if tolerance is not None else max(widths)

    # Points on each axis: its ends, plus every junction point that falls on it.
    on_axis = {sid: [a, b] for sid, (a, b) in axes.items()}
    for junction in junctions:
        point = junction.get("point_wcs")
        if junction.get("kind") in {"corner", "t_junction", "crossing"} and point:
            for sid in junction.get("segment_ids", []):
                if sid in on_axis:
                    on_axis[sid].append((point[0], point[1]))
    junction_points = {(j["point_wcs"][0], j["point_wcs"][1]) for j in junctions
                       if j.get("kind") in {"corner", "t_junction", "crossing"} and j.get("point_wcs")}
    gap_edges = []
    for gap in gaps or []:
        ends = (tuple(gap["start_wcs"][:2]), tuple(gap["end_wcs"][:2]))
        gap_edges.append((gap["id"], ends))
        for sid in gap.get("segment_ids", []):
            if sid in on_axis:
                on_axis[sid].extend(ends)

    all_points, anchors = [], set()
    for sid, points in on_axis.items():
        for index, p in enumerate(points):
            if index >= 2 and (p[0], p[1]) in junction_points:
                anchors.add(len(all_points))
            all_points.append(p)
    for gap_id, ends in gap_edges:
        for p in ends:
            all_points.append(p)
    labels, centres = _cluster(all_points, tol, anchors)

    edges = {}  # frozenset({u, v}) -> {"segments": set, "gaps": set}

    def add_edge(u, v, kind, ident):
        if u == v:
            return
        entry = edges.setdefault(frozenset((u, v)), {"segments": set(), "gaps": set()})
        entry["segments" if kind == "axis" else "gaps"].add(ident)

    cursor = 0
    for sid, points in on_axis.items():
        count = len(points)
        a, b = axes[sid]
        length = math.dist(a, b)
        unit = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        chain = sorted(set(labels[cursor:cursor + count]), key=lambda lab: _param(centres[lab], a, unit))
        cursor += count
        for u, v in zip(chain, chain[1:]):
            add_edge(u, v, "axis", sid)
    for gap_id, ends in gap_edges:
        first, second = labels[cursor], labels[cursor + 1]
        cursor += 2
        add_edge(first, second, "gap", gap_id)

    # Drop dangling edges until every vertex has at least two neighbours.
    adjacency = {}
    for key in edges:
        u, v = tuple(key)
        adjacency.setdefault(u, set()).add(v)
        adjacency.setdefault(v, set()).add(u)
    changed = True
    while changed:
        changed = False
        for vertex in [v for v, n in adjacency.items() if len(n) < 2]:
            for other in adjacency.pop(vertex, set()):
                adjacency[other].discard(vertex)
            changed = True
    if not adjacency:
        return result

    def angle(u, v):
        return math.atan2(centres[v][1] - centres[u][1], centres[v][0] - centres[u][0])

    ordered = {u: sorted(n, key=lambda w, u=u: angle(u, w)) for u, n in adjacency.items()}
    visited, faces = set(), []
    for u in ordered:
        for v in ordered[u]:
            if (u, v) in visited:
                continue
            face, current = [], (u, v)
            while current not in visited:
                visited.add(current)
                face.append(current[0])
                a, b = current
                around = ordered[b]
                current = (b, around[(around.index(a) - 1) % len(around)])
            faces.append(face)

    extent = max(max(abs(c[0]) + abs(c[1]) for c in centres), 1.0)
    loops = []
    for face in faces:
        if len(face) < 3:
            continue
        area = math.fsum(centres[face[i]][0] * centres[face[(i + 1) % len(face)]][1]
                         - centres[face[(i + 1) % len(face)]][0] * centres[face[i]][1]
                         for i in range(len(face))) / 2
        if area <= MIN_AREA_RATIO * extent * extent:
            continue  # the outer face is clockwise/negative here; slivers are ignored
        used_segments, used_gaps = set(), set()
        perimeter = 0.0
        for i, vertex in enumerate(face):
            nxt = face[(i + 1) % len(face)]
            entry = edges[frozenset((vertex, nxt))]
            used_segments |= entry["segments"]
            used_gaps |= entry["gaps"]
            perimeter += math.dist(centres[vertex], centres[nxt])
        polygon = [[centres[v][0], centres[v][1]] for v in face]
        key = "\0".join(sorted(used_segments) + ["|"] + sorted(used_gaps))
        loops.append({"id": "room_loop_" + hashlib.sha256(key.encode()).hexdigest()[:20],
                      "polygon_wcs": polygon, "vertex_count": len(polygon),
                      "area_drawing_units_squared": area, "perimeter_drawing_units": perimeter,
                      "segment_ids": sorted(used_segments), "opening_gap_ids": sorted(used_gaps),
                      "closed_through_opening_gap": bool(used_gaps), "status": "candidate",
                      "room_confirmed": False, "requires_architectural_review": True})
    loops.sort(key=lambda loop: (loop["id"]))
    result.update(loops=loops, loop_count=len(loops))
    return result
