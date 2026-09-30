"""Keep report lists within a size an MCP client can read.

A plan scan can yield thousands of candidates, segments and pairs; clients cut responses around
25k tokens, which hides everything after the cut. Long lists are trimmed to their first items
(they are already sorted deterministically), and `truncated_lists` records each total, so counts
are never lost. Nothing is recomputed: the full data is the cached snapshot, queryable by handle.
"""

DEFAULT_MAX_LIST_ITEMS = 200

ARCHITECTURE_LIST_PATHS = (
    "candidates", "unclassified", "boundary_checks", "block_annotations.items",
    "wall_line_diagnostics.items", "wall_line_diagnostics.excluded", "wall_networks.groups",
    "wall_segment_candidates.segments", "wall_segment_candidates.junctions.junctions",
    "wall_segment_candidates.runs", "wall_segment_candidates.openings.gaps",
    "wall_segment_candidates.openings.openings", "wall_segment_candidates.room_loops.loops",
    "boundary_relations.items", "issues", "dimension_scale_check.items",
)

GEOMETRY_LIST_PATHS = (
    "line_diagnostics.items", "line_diagnostics.excluded", "line_networks.groups", "line_networks.excluded",
    "parallel_line_pairs.pairs", "parallel_line_pairs.pair_junctions.junctions", "boundary_checks",
    "boundary_relations.items", "block_annotations.items", "coverage.unsupported_entities",
)


def validate_max_list_items(value):
    if value is None:
        return
    if type(value) is not int or not 1 <= value <= 100000:
        raise ValueError("max_list_items must be an integer between 1 and 100000, or null for no limit.")


def limit_lists(report, paths, limit):
    """Trim the lists at the dotted paths in place; returns {path: {"total": n, "returned": limit}}."""
    if limit is None:
        return {}
    trimmed = {}
    for path in paths:
        node = report
        *parents, leaf = path.split(".")
        for key in parents:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict) and isinstance(node.get(leaf), list) and len(node[leaf]) > limit:
            trimmed[path] = {"total": len(node[leaf]), "returned": limit}
            node[leaf] = node[leaf][:limit]
    if trimmed:
        report["truncated_lists"] = trimmed
    return trimmed
