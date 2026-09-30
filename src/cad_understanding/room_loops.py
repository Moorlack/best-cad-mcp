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


def _inset_polygon(points, distances):
    """Polygon moved inward (left of each counter-clockwise edge) by a distance per edge; None if unusable.

    Consecutive edges are intersected (mitre); collinear neighbours with different distances keep a small
    step. The result must stay a smaller, positive-area polygon or it is rejected.
    """
    n = len(points)
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = points[i], points[(i + 1) % n]
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 0:
            return None
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        d = distances[i]
        lines.append(((x0 + nx * d, y0 + ny * d), (ux, uy), (nx, ny), d))
    out = []
    for i in range(n):
        (p1, u1, n1, d1), (p2, u2, n2, d2) = lines[i - 1], lines[i]
        cross = u1[0] * u2[1] - u1[1] * u2[0]
        vertex = points[i]
        if abs(cross) < 1e-9:
            out.append((vertex[0] + n1[0] * d1, vertex[1] + n1[1] * d1))
            if abs(d1 - d2) > 1e-12:
                out.append((vertex[0] + n2[0] * d2, vertex[1] + n2[1] * d2))
            continue
        t = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / cross
        out.append((p1[0] + u1[0] * t, p1[1] + u1[1] * t))
    area = math.fsum(out[i][0] * out[(i + 1) % len(out)][1] - out[(i + 1) % len(out)][0] * out[i][1]
                     for i in range(len(out))) / 2
    return out, area


def _inside(point, polygon):
    x, y = point
    inside = False
    for i in range(len(polygon)):
        (x0, y0), (x1, y1) = polygon[i], polygon[(i + 1) % len(polygon)]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def _column_footprints(columns):
    """[{handle, center, area, area_basis}] from column candidates; unusable ones are skipped."""
    found = []
    for candidate in columns or []:
        box = candidate.get("bbox") or {}
        try:
            center = [float(v) for v in box["center"][:2]]
            width, height = float(box["width"]), float(box["height"])
        except (KeyError, TypeError, ValueError):
            continue
        geometry = candidate.get("geometry") or {}
        check = candidate.get("boundary_check") or {}
        if candidate.get("shape") == "circle" and isinstance(geometry.get("radius"), (int, float)):
            area, basis = math.pi * geometry["radius"] ** 2, "circle"
        elif check.get("status") == "valid_simple_polygon":
            area, basis = check["geometric_area_drawing_units_squared"], "closed_contour"
        else:
            area, basis = width * height, "bounding_box"
        if area > 0 and candidate.get("handles"):
            found.append({"handle": candidate["handles"][0], "center": center, "area": area, "area_basis": basis})
    return found


def find_room_loops(segments, junctions, gaps=None, tolerance=None, columns=None):
    """Bounded faces of the wall-axis graph; segments need id, axis_wcs and thickness_drawing_units.

    Each loop also gets a net area (axis polygon moved inward by half of each bounding wall's thickness) and
    the column candidates whose centre lies inside it (footprints subtracted from the net area).
    """
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
    width_of = {s["id"]: float(s["thickness_drawing_units"]["max"]) for s in usable}
    gap_width = {g["id"]: float(g.get("thickness_drawing_units") or 0.0) for g in (gaps or [])}
    footprints = _column_footprints(columns)
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
        half_widths = []
        for i, vertex in enumerate(face):
            nxt = face[(i + 1) % len(face)]
            entry = edges[frozenset((vertex, nxt))]
            used_segments |= entry["segments"]
            used_gaps |= entry["gaps"]
            perimeter += math.dist(centres[vertex], centres[nxt])
            widths = [width_of[s] for s in entry["segments"]] + [gap_width[g] for g in entry["gaps"]]
            half_widths.append(max(widths) / 2.0 if widths else 0.0)
        polygon = [[centres[v][0], centres[v][1]] for v in face]
        key = "\0".join(sorted(used_segments) + ["|"] + sorted(used_gaps))
        loops.append({"id": "room_loop_" + hashlib.sha256(key.encode()).hexdigest()[:20],
                      "polygon_wcs": polygon, "vertex_count": len(polygon),
                      "area_drawing_units_squared": area, "perimeter_drawing_units": perimeter,
                      "segment_ids": sorted(used_segments), "opening_gap_ids": sorted(used_gaps),
                      "closed_through_opening_gap": bool(used_gaps), "status": "candidate",
                      "room_confirmed": False, "requires_architectural_review": True})
        inset = _inset_polygon([tuple(p) for p in polygon], half_widths)
        if inset and 0 < inset[1] < area:
            loops[-1]["net_area_drawing_units_squared"] = inset[1]
            loops[-1]["net_polygon_wcs"] = [list(p) for p in inset[0]]
            loops[-1]["net_area_basis"] = "axis polygon moved inward by half of each bounding wall thickness"
        else:
            loops[-1]["net_area_drawing_units_squared"] = None
            loops[-1]["net_area_basis"] = "not_computed"
        inside = [f for f in footprints if _inside(f["center"], [tuple(p) for p in polygon])]
        loops[-1]["columns_inside"] = [{"handle": f["handle"], "area": f["area"], "area_basis": f["area_basis"]}
                                       for f in inside]
        net = loops[-1]["net_area_drawing_units_squared"]
        loops[-1]["net_area_minus_columns_drawing_units_squared"] = (
            max(0.0, net - math.fsum(f["area"] for f in inside)) if net is not None else None)
    # A loop that lies entirely inside another (sharing no wall) is a void of the outer one, e.g. a shaft.
    for outer in loops:
        outer_polygon = [tuple(p) for p in outer["polygon_wcs"]]
        enclosed = [inner for inner in loops if inner is not outer
                    and not set(inner["segment_ids"]) & set(outer["segment_ids"])
                    and inner["area_drawing_units_squared"] < outer["area_drawing_units_squared"]
                    and all(_inside(tuple(p), outer_polygon) for p in inner["polygon_wcs"])]
        outer["enclosed_loop_ids"] = sorted(inner["id"] for inner in enclosed)
        if enclosed and outer["net_area_drawing_units_squared"] is not None:
            outer["net_area_minus_enclosed_loops_drawing_units_squared"] = max(
                0.0, outer["net_area_drawing_units_squared"]
                - math.fsum(inner["area_drawing_units_squared"] for inner in enclosed))
    loops.sort(key=lambda loop: (loop["id"]))
    result.update(loops=loops, loop_count=len(loops))
    return result
