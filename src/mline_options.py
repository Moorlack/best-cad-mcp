"""Validate explicit multiline options before CAD mutations."""
import math

JUSTIFICATIONS = {"top": 0, "zero": 1, "bottom": 2}


def validate_mline_options(points, scale=None, justification=None):
    try:
        valid = (len(points) >= 2 and all(len(p) == 2 for p in points)
                 and all(type(v) in (int, float) and math.isfinite(v) for p in points for v in p)
                 and all(tuple(a) != tuple(b) for a, b in zip(points, points[1:])))
        valid_scale = scale is None or (type(scale) in (int, float) and math.isfinite(scale) and scale > 0)
    except (TypeError, OverflowError):
        valid = valid_scale = False
    if not valid:
        raise ValueError("MLINE requires at least two finite XY points without consecutive duplicates.")
    if not valid_scale:
        raise ValueError("scale must be a finite positive number.")
    if justification is not None and (not isinstance(justification, str) or justification not in JUSTIFICATIONS):
        raise ValueError("justification must be top, zero or bottom.")
