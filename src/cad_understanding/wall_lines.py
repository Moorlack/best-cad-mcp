"""Compatibility adapter: architectural selection over shared geometry kernels."""
from .line_geometry import diagnose_lines, validate_gap_tolerance as _validate


def validate_gap_tolerance(value):
    return _validate(value, "wall_gap_tolerance")


def diagnose_wall_lines(candidates, entity_coverage_truncated=False, gap_tolerance=None,
                        drawing_units="unknown"):
    validate_gap_tolerance(gap_tolerance)
    selected = [{**c, "excluded_reason": "unsupported_shape_or_conflicting_names"}
                if c["shape"] != "line" or "conflicting_semantic_hints" in c["warnings"] else c
                for c in candidates if c["category"] == "wall"]
    result = diagnose_lines(selected, entity_coverage_truncated, gap_tolerance, drawing_units,
                            scope="named_wall_LINE_candidates_only",
                            review_key="requires_architectural_review")
    result["gap_search"]["interpretation"] = (
        "Nearby endpoints only; openings and intended separations are not defects.")
    result["physical_walls_assembled"] = False
    return result
