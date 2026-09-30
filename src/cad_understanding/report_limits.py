"""Keep report lists within a size an MCP client can read.

A plan scan can yield thousands of candidates, segments and pairs; clients cut responses around
25k tokens, which hides everything after the cut. Long lists are trimmed to their first items
(they are already sorted deterministically), and `truncated_lists` records each total, so counts
are never lost. Nothing is recomputed: the full data is the cached snapshot, queryable by handle.
"""

import copy
import json

DEFAULT_MAX_LIST_ITEMS = 200
DEFAULT_MAX_RESPONSE_CHARS = 60000
ISSUES_PER_CODE = 5

ARCHITECTURE_LIST_PATHS = (
    "candidates", "unclassified", "boundary_checks", "block_annotations.items",
    "wall_line_diagnostics.items", "wall_line_diagnostics.excluded", "wall_networks.groups",
    "wall_segment_candidates.segments", "wall_segment_candidates.junctions.junctions",
    "wall_segment_candidates.runs", "wall_segment_candidates.openings.gaps",
    "wall_segment_candidates.openings.openings", "wall_segment_candidates.room_loops.loops",
    "boundary_relations.items", "dimension_scale_check.items",
    "wall_segment_candidates.unpaired_handles", "wall_segment_candidates.ambiguous_handles",
    "wall_segment_candidates.excluded", "wall_networks.excluded", "wall_networks.unverified_pairs",
    "wall_line_diagnostics.unverified_pairs",
)

GEOMETRY_LIST_PATHS = (
    "line_diagnostics.items", "line_diagnostics.excluded", "line_networks.groups", "line_networks.excluded",
    "parallel_line_pairs.pairs", "parallel_line_pairs.pair_junctions.junctions", "boundary_checks",
    "boundary_relations.items", "block_annotations.items", "coverage.unsupported_entities",
)


def validate_max_response_chars(value):
    if value is None:
        return
    if type(value) is not int or not 2000 <= value <= 10_000_000:
        raise ValueError("max_response_chars must be an integer between 2000 and 10000000, or null for no limit.")


def _collapse_issues(report, limit):
    """Keep the first few issues per code; the rest are counted (hundreds of identical gap notes)."""
    issues = report.get("issues")
    if not isinstance(issues, list):
        return {}
    per_code = min(ISSUES_PER_CODE, limit)
    kept, seen, omitted = [], {}, {}
    for issue in issues:
        code = issue.get("code")
        seen[code] = seen.get(code, 0) + 1
        if seen[code] <= per_code:
            kept.append(issue)
        else:
            omitted[code] = omitted.get(code, 0) + 1
    if not omitted:
        return {}
    for code, count in sorted(omitted.items()):
        kept.append({"code": code, "handles": [], "omitted_count": count,
                     "message": f"{count} more issues with this code are not listed."})
    report["issues"] = kept
    return {"issues." + code: {"total": seen[code], "returned": per_code} for code in omitted}


def fit_report(report, paths, max_items=DEFAULT_MAX_LIST_ITEMS, max_chars=DEFAULT_MAX_RESPONSE_CHARS):
    """Trim long lists (and repeated issue codes) until the report fits both limits; in place.

    max_items caps each list; max_chars caps the serialized report, halving the list limit until it
    fits (down to 3 items per list). Returns the truncation record, which is also stored under
    report["truncated_lists"].
    """
    if max_items is None and max_chars is None:
        return {}
    limit = min(max_items or 200, 100000) if max_items is not None else 200
    source = copy.deepcopy(report)
    while True:
        work = copy.deepcopy(source)
        trimmed = limit_lists(work, paths, limit)
        trimmed.update(_collapse_issues(work, limit))
        if trimmed:
            work["truncated_lists"] = trimmed
        size = len(json.dumps(work, default=str))
        if max_chars is None or size <= max_chars or limit <= 3:
            break
        limit = max(3, limit // 2)
    if trimmed:
        work["truncated_lists"]["response_chars"] = size
    report.clear()
    report.update(work)
    return trimmed


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
