"""Entities on frozen or off layers: marked by the scan (layer_state), skipped by analyses by default.

Pure Python (no SQLite/AutoCAD) so geometry analysis stays importable on its own.
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple


def on_hidden_layer(entity: Dict[str, Any]) -> bool:
    """True when the scan marked the entity's layer as frozen or off (not displayed)."""
    geometry = entity.get("geometry")
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except ValueError:
            return False
    return isinstance(geometry, dict) and bool(geometry.get("layer_state"))


def split_hidden(entities: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """(displayed entities, {layer: count} of skipped hidden-layer entities)."""
    shown, hidden = [], {}
    for entity in entities:
        if on_hidden_layer(entity):
            layer = str(entity.get("layer") or "0")
            hidden[layer] = hidden.get(layer, 0) + 1
        else:
            shown.append(entity)
    return shown, hidden



def parse_mview_xdata(codes, values) -> Optional[Dict[str, Any]]:
    """View data of a paper-space viewport from its legacy "ACAD"/"MVIEW" XData.

    Returns {target, direction, twist, view_height, view_center, frozen_layers} or None.
    The view centre is in display coordinates; for a plan view it is target + centre in WCS.
    """
    pairs = list(zip(codes or (), values or ()))
    if not any(c == 1000 and v == "MVIEW" for c, v in pairs):
        return None
    points = [v for c, v in pairs if c == 1010]
    reals = []
    for c, v in pairs:
        if c == 1002 and v == "{" and reals:
            break  # the nested group holds the frozen layers
        if c == 1040:
            reals.append(float(v))
    if len(points) < 2 or len(reals) < 4:
        return None
    return {"target": [float(x) for x in points[0]], "direction": [float(x) for x in points[1]],
            "twist": reals[0], "view_height": reals[1], "view_center": [reals[2], reals[3]],
            "frozen_layers": [str(v) for c, v in pairs if c == 1003]}


def viewport_window(view, paper_width, paper_height):
    """Model-space [min_x, min_y, max_x, max_y] a plan viewport shows (a superset when twisted)."""
    direction = view["direction"]
    if not (abs(direction[0]) < 1e-9 and abs(direction[1]) < 1e-9 and direction[2] > 0):
        return None
    height = float(view["view_height"])
    width = height * float(paper_width) / float(paper_height) if paper_height else height
    cx = view["target"][0] + view["view_center"][0]
    cy = view["target"][1] + view["view_center"][1]
    twist = float(view.get("twist") or 0.0)
    hw, hh = width / 2.0, height / 2.0
    if abs(math.sin(twist)) > 1e-12:
        c, s = abs(math.cos(twist)), abs(math.sin(twist))
        hw, hh = hw * c + hh * s, hw * s + hh * c
    return [cx - hw, cy - hh, cx + hw, cy + hh]


def _entity_box(entity):
    box = entity.get("bbox")
    if isinstance(box, dict) and box.get("min") and box.get("max"):
        return box["min"][0], box["min"][1], box["max"][0], box["max"][1]
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        return tuple(box[:4])
    return None


def split_by_view(entities, view_filter):
    """(entities shown in the viewport, {"frozen_in_viewport": n, "outside_viewport": n}).

    view_filter: {"frozen_layers": [...], "window": [min_x, min_y, max_x, max_y] or None}.
    Entities without a bounding box are kept when their layer is shown.
    """
    frozen = {str(name).upper() for name in view_filter.get("frozen_layers") or ()}
    window = view_filter.get("window")
    shown, stats = [], {"frozen_in_viewport": 0, "outside_viewport": 0}
    for entity in entities:
        if str(entity.get("layer") or "0").upper() in frozen:
            stats["frozen_in_viewport"] += 1
            continue
        box = _entity_box(entity) if window else None
        if box is not None and (box[2] < window[0] or box[0] > window[2] or box[3] < window[1] or box[1] > window[3]):
            stats["outside_viewport"] += 1
            continue
        shown.append(entity)
    return shown, stats
