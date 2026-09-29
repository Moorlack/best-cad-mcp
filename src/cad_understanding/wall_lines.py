"""Compatibility adapter: architectural selection over shared geometry kernels."""
from .line_geometry import diagnose_lines, validate_gap_tolerance as _validate
from .polyline_parts import split_mline, split_polyline


def select_wall_faces(candidates):
    """Wall LINE candidates plus straight segments of wall polylines, with explicit exclusions."""
    selected, extra_excluded = [], []
    for c in candidates:
        if c["category"] != "wall":
            continue
        if "conflicting_semantic_hints" in c["warnings"] or c["shape"] not in {
                "line", "open_polyline", "closed_polyline", "mline"}:
            selected.append({**c, "excluded_reason": "unsupported_shape_or_conflicting_names"})
        elif c["shape"] == "line":
            selected.append(c)
        else:
            split = split_mline if c["shape"] == "mline" else split_polyline
            parts, excluded = split(c["handles"][0], c["geometry"], c["id"], c["layer"])
            selected.extend({**p, "category": "wall", "warnings": list(c["warnings"])} for p in parts)
            extra_excluded.extend(excluded)
    return selected, extra_excluded


def validate_gap_tolerance(value):
    return _validate(value, "wall_gap_tolerance")


def diagnose_wall_lines(candidates, entity_coverage_truncated=False, gap_tolerance=None,
                        drawing_units="unknown"):
    validate_gap_tolerance(gap_tolerance)
    selected, extra_excluded = select_wall_faces(candidates)
    result = diagnose_lines(selected, entity_coverage_truncated, gap_tolerance, drawing_units,
                            scope="named_wall_LINE_candidates_only",
                            review_key="requires_architectural_review", extra_excluded=extra_excluded)
    result["gap_search"]["interpretation"] = (
        "Nearby endpoints only; openings and intended separations are not defects.")
    result["physical_walls_assembled"] = False
    return result
