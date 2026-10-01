"""Fast scan source: read simple model-space entities from an exported DXF instead of COM.

Reading each entity over COM costs 15-40 ms; a DXF export is written by AutoCAD in one call and
parsed here in Python. Only entity kinds whose scan record can be reproduced exactly from DXF are
taken (LINE, CIRCLE, ARC and plan-view LWPOLYLINE); everything else is returned as a handle for the
regular COM reader, so the cache content is the same either way.

Other kinds can still skip most COM calls: `partial_record` gives their handle, type, layer, colour and,
for blocks, MLINEs and texts, the scanned geometry fields; COM then only adds what DXF cannot reproduce
exactly (bounding boxes, effective block names, constant attributes, block definitions).
"""

import math
import re

DXF_TO_COM = {"LINE": "AcDbLine", "CIRCLE": "AcDbCircle", "ARC": "AcDbArc", "LWPOLYLINE": "AcDbPolyline"}
_UNICODE_ESCAPE = re.compile(r"\\U\+([0-9A-Fa-f]{4})")
# Entities that follow their owner in the ENTITIES section and are not separate model-space objects.
_SUBENTITIES = {"ATTRIB", "VERTEX", "SEQEND"}
_TEXT_CODES = {"1", "2", "3", "6", "8"}
# Last DXF subclass marker -> COM ObjectName, only where both are known to agree.
PARTIAL_TYPES = {"AcDbText", "AcDbMText", "AcDbHatch", "AcDbPoint", "AcDbBlockReference", "AcDbMline",
                 "AcDbLeader", "AcDbMLeader", "AcDbEllipse", "AcDbSpline", "AcDb2dPolyline", "AcDb3dPolyline",
                 "AcDbRotatedDimension", "AcDbAlignedDimension", "AcDbRadialDimension", "AcDbDiametricDimension",
                 "AcDb3PointAngularDimension", "AcDb2LineAngularDimension", "AcDbOrdinateDimension"}


def _r(value):
    return round(float(value), 9)


def _text(value):
    return _UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), value)


def iter_entities(dxf_text):
    """Yield (type, [(code, value), ...]) for top-level entities of the ENTITIES section.

    ATTRIB entities after an INSERT are kept in the owner's pairs as ("ATTRIB", [(code, value), ...]);
    VERTEX and SEQEND data are skipped.
    """
    lines = dxf_text.splitlines()
    i, in_entities, current, target = 0, False, None, None
    while i + 1 < len(lines):
        code, value = lines[i].strip(), lines[i + 1].rstrip("\r\n")
        i += 2
        if code == "0":
            if in_entities and value in _SUBENTITIES and current is not None:
                target = None
                if value == "ATTRIB":
                    target = []
                    current[1].append(("ATTRIB", target))
                continue
            if current is not None:
                yield current
                current = target = None
            if value == "SECTION" and i + 1 < len(lines) and lines[i].strip() == "2":
                in_entities = lines[i + 1].strip() == "ENTITIES"
                continue
            if value == "ENDSEC":
                in_entities = False
                continue
            if in_entities and value not in _SUBENTITIES:
                current = (value, [])
                target = current[1]
            continue
        if target is not None:
            target.append((code, _text(value) if code in _TEXT_CODES else value.strip()))
    if current is not None:
        yield current


def _first(pairs, code, default=None):
    for c, v in pairs:
        if c == code:
            return v
    return default


def _float(pairs, code, default=0.0):
    value = _first(pairs, code)
    return float(value) if value is not None else default


def _common(pairs):
    color = _first(pairs, "62")
    linetype = _first(pairs, "6")
    if linetype is not None:
        linetype = {"BYLAYER": "ByLayer", "BYBLOCK": "ByBlock"}.get(linetype.upper(), linetype)
    return {"layer": _first(pairs, "8", "0"), "color": int(color) if color is not None else 256,
            "linetype": linetype or "ByLayer"}


def _plan_normal(pairs):
    normal = (_float(pairs, "210", 0.0), _float(pairs, "220", 0.0), _float(pairs, "230", 1.0))
    return abs(normal[0]) < 1e-12 and abs(normal[1]) < 1e-12 and abs(normal[2] - 1.0) < 1e-12


def _arc_extent(cx, cy, r, a0, a1):
    """Bounding box of a counter-clockwise arc from a0 to a1 (radians)."""
    sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
    xs = [cx + r * math.cos(a0), cx + r * math.cos(a0 + sweep)]
    ys = [cy + r * math.sin(a0), cy + r * math.sin(a0 + sweep)]
    for k in range(-4, 9):
        angle = k * math.pi / 2
        if a0 <= angle <= a0 + sweep or a0 <= angle + 2 * math.pi <= a0 + sweep:
            xs.append(cx + r * math.cos(angle))
            ys.append(cy + r * math.sin(angle))
    return min(xs), min(ys), max(xs), max(ys)


def _bulge_segment(start, end, bulge):
    """(length, bbox) of one polyline segment with a bulge."""
    chord = math.hypot(end[0] - start[0], end[1] - start[1])
    if abs(bulge) <= 1e-12 or chord <= 1e-12:
        return chord, (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
    sweep = 4.0 * math.atan(bulge)
    radius = chord / (2.0 * abs(math.sin(sweep / 2.0)))
    dx, dy = end[0] - start[0], end[1] - start[1]
    offset = chord * (1.0 - bulge * bulge) / (4.0 * bulge)
    cx = start[0] + dx / 2.0 - dy / chord * offset
    cy = start[1] + dy / 2.0 + dx / chord * offset
    a_start = math.atan2(start[1] - cy, start[0] - cx)
    a_end = math.atan2(end[1] - cy, end[0] - cx)
    box = _arc_extent(cx, cy, radius, a_start, a_end) if bulge > 0 else _arc_extent(cx, cy, radius, a_end, a_start)
    return radius * abs(sweep), box


def _merge(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def entity_record(kind, pairs, read_common, read_geometry, include_bbox, visual_path=None):
    """Scan record for a supported entity, or None when COM must read it."""
    com_name = DXF_TO_COM.get(kind)
    handle = _first(pairs, "5")
    if com_name is None or not handle:
        return None
    if kind != "LINE" and not _plan_normal(pairs):
        return None  # OCS geometry: leave the transform to COM
    common = _common(pairs)
    info = {"handle": handle, "type": com_name, "name": com_name.replace("AcDb", ""), "layer": common["layer"]}
    if read_common:
        info["color"], info["linetype"] = common["color"], common["linetype"]
    box = None
    if kind == "LINE":
        start = [_r(_float(pairs, "10")), _r(_float(pairs, "20")), _r(_float(pairs, "30"))]
        end = [_r(_float(pairs, "11")), _r(_float(pairs, "21")), _r(_float(pairs, "31"))]
        box = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
        if read_geometry:
            info.update(start=start, end=end, length=_r(math.dist(start, end)))
    elif kind == "CIRCLE":
        cx, cy, cz, r = _float(pairs, "10"), _float(pairs, "20"), _float(pairs, "30"), _float(pairs, "40")
        box = (cx - r, cy - r, cx + r, cy + r)
        if read_geometry:
            info.update(center=[_r(cx), _r(cy), _r(cz)], radius=_r(r))
    elif kind == "ARC":
        cx, cy, cz, r = _float(pairs, "10"), _float(pairs, "20"), _float(pairs, "30"), _float(pairs, "40")
        a0, a1 = math.radians(_float(pairs, "50")), math.radians(_float(pairs, "51"))
        box = _arc_extent(cx, cy, r, a0, a1)
        if read_geometry:
            info.update(center=[_r(cx), _r(cy), _r(cz)], normal=[0.0, 0.0, 1.0],
                        start=[_r(cx + r * math.cos(a0)), _r(cy + r * math.sin(a0)), _r(cz)],
                        end=[_r(cx + r * math.cos(a1)), _r(cy + r * math.sin(a1)), _r(cz)],
                        radius=_r(r), start_angle=_r(a0), end_angle=_r(a1), angle_unit="radian",
                        start_parameter=a0, end_parameter=a1, parameter_unit="radian")
    else:  # LWPOLYLINE
        flags = int(_first(pairs, "70", "0"))
        closed = bool(flags & 1)
        elevation = _float(pairs, "38", 0.0)
        vertices, bulges = [], []
        for code, value in pairs:
            if code == "10":
                vertices.append([float(value), None])
                bulges.append(0.0)
            elif code == "20" and vertices and vertices[-1][1] is None:
                vertices[-1][1] = float(value)
            elif code == "42" and bulges:
                bulges[-1] = float(value)
        if len(vertices) < 1 or any(v[1] is None for v in vertices):
            return None
        segments = len(vertices) if closed else max(0, len(vertices) - 1)
        length, box = 0.0, None
        for index in range(segments):
            seg_length, seg_box = _bulge_segment(vertices[index], vertices[(index + 1) % len(vertices)], bulges[index])
            length += seg_length
            box = seg_box if box is None else _merge(box, seg_box)
        if box is None:
            box = (vertices[0][0], vertices[0][1], vertices[0][0], vertices[0][1])
        if read_geometry:
            ocs = [[_r(x), _r(y), 0.0] for x, y in vertices]
            info.update(length=_r(length), closed=closed,
                        vertices=[[_r(x), _r(y), _r(elevation)] for x, y in vertices],
                        vertices_coordinate_system="WCS", normal=[0.0, 0.0, 1.0], elevation=_r(elevation))
            segment_bulges = bulges[:segments]
            info["bulges_complete"] = True
            if segment_bulges:
                info["bulges"] = segment_bulges
                path = visual_path(ocs, segment_bulges, closed, elevation) if visual_path else []
                if path:
                    info["visual_path"] = path
    if include_bbox and box is not None:
        info["bbox"] = [_r(box[0]), _r(box[1]), _r(box[2]), _r(box[3])]
    return info


def _last_marker(pairs):
    marker = None
    for code, value in pairs:
        if code == "100":
            marker = value
    return marker


def _point(pairs, x, y, z):
    return [_r(_float(pairs, x)), _r(_float(pairs, y)), _r(_float(pairs, z))]


def _insert_geometry(pairs):
    if any(code == "101" for code, _ in pairs):
        return None
    attributes = []
    for code, value in pairs:
        if code != "ATTRIB":
            continue
        if any(c in {"101", "3"} for c, _ in value) or _first(value, "5") is None:
            return None  # multiline or long attribute text: COM reads it
        attributes.append({"Handle": _first(value, "5"), "TagString": _first(value, "2", ""),
                           "TextString": _first(value, "1", ""),
                           "Invisible": bool(int(_first(value, "70", "0")) & 1)})
    geometry = {"block_name": _first(pairs, "2"), "insertion_point": _point(pairs, "10", "20", "30"),
                "insertion_point_coordinate_system": "WCS", "normal": [0.0, 0.0, 1.0],
                "rotation": math.radians(_float(pairs, "50")), "rotation_unit": "radian",
                "x_scale": _float(pairs, "41", 1.0), "y_scale": _float(pairs, "42", 1.0),
                "z_scale": _float(pairs, "43", 1.0), "visible": _first(pairs, "60", "0") != "1"}
    return geometry, attributes


def _mline_geometry(pairs):
    vertices = []
    for code, value in pairs:
        if code == "11":
            vertices.append([float(value), None, 0.0])
        elif code == "21" and vertices:
            vertices[-1][1] = float(value)
        elif code == "31" and vertices:
            vertices[-1][2] = float(value)
    if not vertices or any(v[1] is None for v in vertices):
        return None
    return {"vertices": [[_r(x), _r(y), _r(z)] for x, y, z in vertices], "mline_style": _first(pairs, "2"),
            "mline_scale": _float(pairs, "40", 1.0), "mline_justification": int(_first(pairs, "70", "0"))}


def _text_geometry(kind, pairs):
    if any(code == "101" for code, _ in pairs):
        return None
    if kind == "MTEXT":
        return {"text": "".join(v for c, v in pairs if c == "3") + (_first(pairs, "1", "") or "")}
    return {"text": _first(pairs, "1", "")}


def partial_record(kind, pairs):
    """Fields DXF reproduces for kinds COM must still complete, or None to read them fully over COM.

    {"handle", "type", "name", "layer", "color", "linetype", "geometry"}; geometry is None when the
    kind's scanned geometry cannot be taken from DXF; blocks also carry "attributes" (reference group).
    """
    com_name = _last_marker(pairs)
    handle = _first(pairs, "5")
    if com_name not in PARTIAL_TYPES or not handle:
        return None
    if com_name == "AcDbBlockReference" and any(c in {"70", "71"} and int(v) > 1 for c, v in pairs
                                                if c in {"70", "71"}):
        return None  # MINSERT arrays
    record = {"handle": handle, "type": com_name, "name": com_name.replace("AcDb", ""), **_common(pairs),
              "geometry": None}
    if not _plan_normal(pairs):
        return record
    if com_name == "AcDbBlockReference":
        found = _insert_geometry(pairs)
        if found is not None:
            record["geometry"], record["attributes"] = found
    elif com_name == "AcDbMline":
        record["geometry"] = _mline_geometry(pairs)
    elif com_name in {"AcDbText", "AcDbMText"}:
        record["geometry"] = _text_geometry(kind, pairs)
    return record


def read_dxf_entities(dxf_text, read_common=True, read_geometry=True, include_bbox=True, visual_path=None,
                      partials=None):
    """(records, com_handles, order): fast records, handles COM must read, and every handle in file order.

    When a dict is passed as `partials`, it receives partial_record() results for the COM handles.
    """
    records, com_handles, order = {}, [], []
    for kind, pairs in iter_entities(dxf_text):
        handle = _first(pairs, "5")
        if not handle:
            continue
        order.append(handle)
        record = entity_record(kind, pairs, read_common, read_geometry, include_bbox, visual_path)
        if record is None:
            com_handles.append(handle)
            if partials is not None:
                partial = partial_record(kind, pairs)
                if partial is not None:
                    partials[handle] = partial
        else:
            records[handle] = record
    return records, com_handles, order
