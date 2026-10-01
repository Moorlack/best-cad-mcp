"""Entities on frozen or off layers: marked by the scan (layer_state), skipped by analyses by default.

Pure Python (no SQLite/AutoCAD) so geometry analysis stays importable on its own.
"""

import json
from typing import Any, Dict, List, Tuple


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
