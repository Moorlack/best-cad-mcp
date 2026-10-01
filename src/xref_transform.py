"""Place scan records of an external reference into the host drawing.

An xref's own model space is scanned in its own coordinates; the host sees it through the xref
INSERT (insertion point, rotation, scale). Records are moved into host WCS so host analyses can use
them, with host-style layer names ("Xref|Layer") and virtual handles ("<insert handle>/<handle>").
Only plan-view inserts with a uniform positive scale are supported: mirrored or non-uniform inserts
would also change arc directions and bulges, so they are reported instead of approximated.
"""

import math

POINT_KEYS = ("start", "end", "center", "insertion_point", "xline1_point", "xline2_point")
POINT_LIST_KEYS = ("vertices", "visual_path", "fit_points", "control_points")
VECTOR_KEYS = ("major_axis", "minor_axis")
LENGTH_KEYS = ("radius", "length", "mline_scale", "x_scale", "y_scale", "z_scale")
RADIAN_KEYS = ("rotation", "dimension_rotation")


def _r(value):
    return round(float(value), 9)


class InsertTransform:
    """Host WCS = insertion + scale * R(rotation) * xref WCS (plan view only)."""

    def __init__(self, insertion_point, rotation=0.0, x_scale=1.0, y_scale=1.0, z_scale=1.0, normal=None):
        normal = normal or [0.0, 0.0, 1.0]
        if not (abs(normal[0]) < 1e-9 and abs(normal[1]) < 1e-9 and normal[2] > 0):
            raise ValueError("xref insert is not in the plan view")
        if not (x_scale > 0 and y_scale > 0 and math.isclose(x_scale, y_scale, rel_tol=1e-9)):
            raise ValueError("xref insert is mirrored or not uniformly scaled")
        self.origin = [float(v) for v in (list(insertion_point) + [0.0, 0.0, 0.0])[:3]]
        self.rotation = float(rotation or 0.0)
        self.scale = float(x_scale)
        self.z_scale = float(z_scale or 1.0)
        self.cos, self.sin = math.cos(self.rotation), math.sin(self.rotation)

    @property
    def identity(self):
        return self.origin == [0.0, 0.0, 0.0] and self.rotation == 0.0 and self.scale == 1.0

    def point(self, p):
        x, y = float(p[0]), float(p[1])
        z = float(p[2]) if len(p) > 2 else 0.0
        out = [_r(self.origin[0] + self.scale * (self.cos * x - self.sin * y)),
               _r(self.origin[1] + self.scale * (self.sin * x + self.cos * y))]
        return out + [_r(self.origin[2] + self.z_scale * z)] if len(p) > 2 else out

    def vector(self, v):
        x, y = float(v[0]), float(v[1])
        out = [_r(self.scale * (self.cos * x - self.sin * y)), _r(self.scale * (self.sin * x + self.cos * y))]
        return out + [_r(float(v[2]) * self.z_scale)] if len(v) > 2 else out

    def bbox(self, box):
        corners = [self.point([box[0], box[1]]), self.point([box[2], box[1]]),
                   self.point([box[0], box[3]]), self.point([box[2], box[3]])]
        return [min(c[0] for c in corners), min(c[1] for c in corners),
                max(c[0] for c in corners), max(c[1] for c in corners)]

    def record(self, record):
        """A transformed copy of one scan record (geometry fields only; identity fields untouched)."""
        out = dict(record)
        for key in POINT_KEYS:
            if isinstance(out.get(key), (list, tuple)) and len(out[key]) >= 2:
                out[key] = self.point(out[key])
        for key in POINT_LIST_KEYS:
            if isinstance(out.get(key), list):
                out[key] = [self.point(p) for p in out[key] if isinstance(p, (list, tuple)) and len(p) >= 2]
        for key in VECTOR_KEYS:
            if isinstance(out.get(key), (list, tuple)) and len(out[key]) >= 2:
                out[key] = self.vector(out[key])
        for key in LENGTH_KEYS:
            if isinstance(out.get(key), (int, float)) and not isinstance(out.get(key), bool):
                out[key] = _r(out[key] * (self.z_scale if key == "z_scale" else self.scale))
        for key in RADIAN_KEYS:
            if isinstance(out.get(key), (int, float)) and not isinstance(out.get(key), bool):
                out[key] = out[key] + self.rotation
        if isinstance(out.get("elevation"), (int, float)):
            out["elevation"] = _r(self.origin[2] + self.z_scale * out["elevation"])
        unit = out.get("angle_unit")
        for key in ("start_angle", "end_angle"):
            if isinstance(out.get(key), (int, float)):
                out[key] = _r(out[key] + (math.degrees(self.rotation) if unit == "degree" else self.rotation))
        if out.get("parameter_unit") == "radian" and out.get("angle_unit") == "radian":
            # Arc parameters are angles from the X axis; ellipse parameters are relative to the major axis.
            for key in ("start_parameter", "end_parameter"):
                if isinstance(out.get(key), (int, float)):
                    out[key] = out[key] + self.rotation
        if isinstance(out.get("bbox"), (list, tuple)) and len(out["bbox"]) >= 4:
            out["bbox"] = self.bbox(out["bbox"])
        return out


def place_xref_records(records, xref_name, insert_handle, transform):
    """Host-side copies of an xref's scan records seen through one INSERT."""
    placed = []
    for record in records:
        if not record.get("handle") or "error" in record:
            continue
        out = transform.record(record)
        out.pop("layer_state", None)  # the host's state of "Xref|Layer" applies, set by the host scan
        out["handle"] = f"{insert_handle}/{record['handle']}"
        out["layer"] = f"{xref_name}|{record.get('layer') or '0'}"
        if out.get("block_name"):
            out["block_name"] = f"{xref_name}|{out['block_name']}"
        out["xref"] = xref_name
        out["xref_insert_handle"] = insert_handle
        out["source_handle"] = record["handle"]
        placed.append(out)
    return placed
