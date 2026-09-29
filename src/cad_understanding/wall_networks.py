"""Compatibility adapter retaining architectural group IDs and response fields."""
from .line_networks import build_line_networks


def build_wall_networks(candidates, diagnostics):
    result = build_line_networks([c for c in candidates if c['category'] == 'wall'], diagnostics,
                                id_prefix="wall_network_", review_key="requires_architectural_review")
    result['interpretation'] = (
        'Connected source LINE groups under diagnostic tolerance; not physical walls, rooms or load paths.')
    result["physical_walls_assembled"] = False
    for group in result["groups"]:
        group["structural_role"] = "unknown"
    return result
