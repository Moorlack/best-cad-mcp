"""Compare linear dimension values with the geometry they measure.

A rotated/aligned dimension stores the measured value and its two extension-line points. When the
value equals the distance between those points (along the dimension direction), the drawn geometry
agrees with its own dimensions. This supports, but never proves, a drawing scale: the drawing units
stay declared, and dimensions with overridden text or a linear scale factor other than 1 are skipped.
"""

import math
from statistics import median

DEFAULT_TOLERANCE = 0.01
MAX_ITEMS = 20


def _xy(value):
    if (isinstance(value, (list, tuple)) and len(value) >= 2
            and all(type(v) in (int, float) and math.isfinite(v) for v in value[:2])):
        return float(value[0]), float(value[1])
    return None


def check_dimension_scale(entities, tolerance=DEFAULT_TOLERANCE):
    """Summary of measured-versus-drawn agreement over scanned linear dimensions."""
    items, skipped = [], {}
    for entity in sorted(entities, key=lambda e: str(e.get("handle") or "")):
        geometry = entity.get("geometry") or {}
        kind = str(entity.get("entity_type") or entity.get("object_name") or "").lower().removeprefix("acdb")
        if kind not in {"rotateddimension", "aligneddimension"}:
            continue
        handle = str(entity.get("handle") or "")
        measured = geometry.get("measurement")
        p1, p2 = _xy(geometry.get("xline1_point")), _xy(geometry.get("xline2_point"))
        factor = geometry.get("dimension_linear_factor")
        reason = None
        if not (type(measured) in (int, float) and math.isfinite(measured) and measured > 0 and p1 and p2):
            reason = "dimension_data_not_captured"
        elif str(geometry.get("text_override") or "").strip():
            reason = "text_overridden"
        elif factor is not None and (type(factor) not in (int, float) or abs(factor - 1.0) > 1e-9):
            reason = "linear_scale_factor_not_one"
        elif kind == "rotateddimension" and not isinstance(geometry.get("dimension_rotation"), (int, float)):
            reason = "rotation_not_captured"
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        if kind == "rotateddimension":
            angle = geometry["dimension_rotation"]
            drawn = abs((p2[0] - p1[0]) * math.cos(angle) + (p2[1] - p1[1]) * math.sin(angle))
        else:
            drawn = math.dist(p1, p2)
        if drawn <= 0:
            skipped["zero_drawn_length"] = skipped.get("zero_drawn_length", 0) + 1
            continue
        ratio = measured / drawn
        items.append({"handle": handle, "measured": measured, "drawn": drawn, "ratio": ratio,
                      "status": "agrees" if abs(ratio - 1.0) <= tolerance else "differs"})
    agree = sum(1 for i in items if i["status"] == "agrees")
    result = {"checked": len(items), "agree": agree, "differ": len(items) - agree,
              "skipped": dict(sorted(skipped.items())), "tolerance_relative": tolerance,
              "median_ratio_measured_to_drawn": median(i["ratio"] for i in items) if items else None,
              "items": [i for i in items if i["status"] == "differs"][:MAX_ITEMS]
              + [i for i in items if i["status"] == "agrees"][:max(0, MAX_ITEMS - (len(items) - agree))],
              "units_verified": False,
              "interpretation": ("Dimension values compared with the distance between their extension-line points. "
                                 "Agreement shows the geometry is drawn consistently with its dimensions; it does "
                                 "not verify the unit or the real-world scale.")}
    result["status"] = ("no_linear_dimensions_checked" if not items
                        else "agrees" if not result["differ"] else "mixed" if agree else "differs")
    return result
