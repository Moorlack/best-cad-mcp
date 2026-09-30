"""Door-swing evidence: ARC geometry near an opening (standalone arcs or arcs inside the block).

Geometric evidence only. A quarter-circle next to a wall gap supports, but does not prove,
a swinging leaf; nothing here names a door type, leaf width or hinge hardware.
"""

import math

MAX_SWINGS_PER_OPENING = 4
HINGE_TOLERANCE_RATIO = 0.15     # hinge (arc centre) distance from a gap end, as a share of the gap length
RADIUS_TOLERANCE_RATIO = 0.20    # arc radius versus the opening width
MIN_SWEEP_DEGREES = 30.0
MAX_SWEEP_DEGREES = 180.5


def _xy(value):
    if (isinstance(value, (list, tuple)) and len(value) >= 2
            and all(type(v) in (int, float) and math.isfinite(v) for v in value[:2])):
        return float(value[0]), float(value[1])
    return None


def arc_from_geometry(geometry):
    """Plan-view arc {center, radius, start_angle, sweep} (radians, counter-clockwise) or None.

    AutoCAD arcs run counter-clockwise about their normal; a normal of -Z reverses the plan direction.
    """
    center, start, end = (_xy((geometry or {}).get(k)) for k in ("center", "start", "end"))
    if not (center and start and end):
        return None
    normal = (geometry or {}).get("normal") or [0, 0, 1]
    try:
        nz = float(normal[2])
    except (TypeError, ValueError, IndexError):
        return None
    if abs(nz) < 0.999999:
        return None
    radius = math.dist(center, start)
    if radius <= 0 or abs(math.dist(center, end) - radius) > 1e-6 * max(1.0, radius):
        return None
    if nz < 0:
        start, end = end, start
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0) % (2 * math.pi)
    if sweep <= 1e-9:
        sweep = 2 * math.pi
    return {"center": center, "radius": radius, "start_angle": a0, "sweep": sweep}


def block_transform(reference_geometry, uniform_only=True):
    """(place, sx, sy): maps block-local XY to WCS for a plan-view block reference, or None.

    Needs an insertion point, a +Z normal and finite non-zero scales; arcs additionally need uniform
    scale (uniform_only) so they stay arcs, while straight lines survive any scale.
    """
    definition = (reference_geometry or {}).get("block_definition") or {}
    point = _xy((reference_geometry or {}).get("insertion_point"))
    rotation = (reference_geometry or {}).get("rotation", 0.0)
    if point is None or type(rotation) not in (int, float) or not math.isfinite(rotation):
        return None
    normal = reference_geometry.get("normal") or [0, 0, 1]
    if len(normal) < 3 or normal[2] < 0.999999:
        return None
    sx, sy = reference_geometry.get("x_scale", 1.0), reference_geometry.get("y_scale", 1.0)
    if not all(type(v) in (int, float) and math.isfinite(v) and v != 0 for v in (sx, sy)):
        return None
    if uniform_only and abs(abs(sx) - abs(sy)) > 1e-9 * max(abs(sx), abs(sy)):
        return None
    origin = _xy(definition.get("origin")) or (0.0, 0.0)
    cos_r, sin_r = math.cos(rotation), math.sin(rotation)

    def place(local):
        x, y = (local[0] - origin[0]) * sx, (local[1] - origin[1]) * sy
        return (point[0] + cos_r * x - sin_r * y, point[1] + sin_r * x + cos_r * y)

    return place, sx, sy


def block_arcs_wcs(reference_geometry):
    """Arcs stored in the block definition, placed in WCS by the reference's insertion transform.

    Skips (returns []) for non-plan normals and non-uniform scale, where an arc would not stay an arc.
    """
    definition = (reference_geometry or {}).get("block_definition") or {}
    source_arcs = definition.get("arcs") or []
    transform = block_transform(reference_geometry) if source_arcs else None
    if transform is None:
        return []
    place, sx, sy = transform
    placed = []
    for entry in source_arcs:
        arc = arc_from_geometry(entry)
        if arc is None:
            continue
        center = place(arc["center"])
        a0, sweep = arc["start_angle"], arc["sweep"]
        start_local = (arc["center"][0] + arc["radius"] * math.cos(a0), arc["center"][1] + arc["radius"] * math.sin(a0))
        end_local = (arc["center"][0] + arc["radius"] * math.cos(a0 + sweep),
                     arc["center"][1] + arc["radius"] * math.sin(a0 + sweep))
        start, end = place(start_local), place(end_local)
        if sx * sy < 0:  # mirrored: counter-clockwise becomes clockwise, so swap the ends
            start, end = end, start
        a_start = math.atan2(start[1] - center[1], start[0] - center[0])
        a_end = math.atan2(end[1] - center[1], end[0] - center[0])
        swept = (a_end - a_start) % (2 * math.pi) or 2 * math.pi
        placed.append({"center": center, "radius": arc["radius"] * abs(sx), "start_angle": a_start, "sweep": swept})
    return placed


def _swing_entry(arc, source, hinge_end, hinge_distance, width, axis):
    (x0, y0), (x1, y1) = axis
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    mid = arc["start_angle"] + arc["sweep"] / 2.0
    mx, my = math.cos(mid), math.sin(mid)
    side = ux * my - uy * mx  # positive: the swing lies to the left of the axis direction
    return {"source": source, "hinge_end": hinge_end, "hinge_distance": hinge_distance,
            "radius": arc["radius"], "radius_to_opening_width_ratio": arc["radius"] / width,
            "sweep_degrees": math.degrees(arc["sweep"]), "swing_side": "left" if side > 0 else "right",
            "center_wcs": list(arc["center"]), "status": "candidate"}


def find_swings(arcs, start, end):
    """Arc candidates whose centre sits at one end of the opening and whose radius matches its width.

    arcs: [(source_label, arc_dict)]; start/end: opening end points (drawing units).
    """
    (x0, y0), (x1, y1) = start[:2], end[:2]
    width = math.hypot(x1 - x0, y1 - y0)
    if width <= 0:
        return []
    found = []
    for label, arc in arcs:
        if not (MIN_SWEEP_DEGREES <= math.degrees(arc["sweep"]) <= MAX_SWEEP_DEGREES):
            continue
        if abs(arc["radius"] - width) > RADIUS_TOLERANCE_RATIO * width:
            continue
        distances = {"start": math.dist(arc["center"], (x0, y0)), "end": math.dist(arc["center"], (x1, y1))}
        hinge_end = min(distances, key=distances.get)
        if distances[hinge_end] > HINGE_TOLERANCE_RATIO * width:
            continue
        found.append(_swing_entry(arc, label, hinge_end, distances[hinge_end], width, ((x0, y0), (x1, y1))))
    found.sort(key=lambda item: (item["hinge_distance"], str(item["source"])))
    return found[:MAX_SWINGS_PER_OPENING]
