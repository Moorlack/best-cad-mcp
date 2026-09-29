"""Architectural adapter: wall-face LINE pairs as wall segment candidates."""
from .axis_junctions import find_axis_junctions, validate_junction_tolerance
from .line_pairs import find_parallel_pairs, validate_separation_range


def validate_wall_thickness_range(value):
    validate_separation_range(value, "wall_thickness_range")


def build_wall_segment_candidates(candidates, thickness_range, entity_coverage_truncated=False,
                                  junction_tolerance=None):
    """Pair named wall LINE candidates; thickness is geometric offset, not a verified wall type."""
    if thickness_range is None:
        return {"requested": False, "segments": [], "segment_count": 0,
                "physical_walls_assembled": False,
                "interpretation": "Not requested; pass wall_thickness_range to pair wall faces."}
    validate_wall_thickness_range(thickness_range)
    validate_junction_tolerance(junction_tolerance, "wall_junction_tolerance")
    selected = [{**c, "excluded_reason": "unsupported_shape_or_conflicting_names"}
                if c["shape"] != "line" or "conflicting_semantic_hints" in c["warnings"] else c
                for c in candidates if c["category"] == "wall"]
    result = find_parallel_pairs(selected, thickness_range,
                                 entity_coverage_truncated=entity_coverage_truncated,
                                 id_prefix="wall_segment_", review_key="requires_architectural_review",
                                 scope="named_wall_LINE_candidates_only")
    segments = []
    for pair in result.pop("pairs"):
        pair["thickness_drawing_units"] = {k: pair.pop("separation_" + k) for k in ("min", "max", "mean")}
        pair["source_candidate_ids"] = pair.pop("source_ids")
        pair["axis_wcs"] = pair.pop("midline_wcs")
        pair.update({"openings_checked": False, "physical_wall_verified": False,
                     "structural_role": "unknown"})
        segments.append(pair)
    result.pop("pair_count")
    result["thickness_range_drawing_units"] = result.pop("separation_range_drawing_units")
    junctions = find_axis_junctions(
        [{"id": s["id"], "start": s["axis_wcs"][0], "end": s["axis_wcs"][1],
          "width": s["thickness_drawing_units"]["max"]} for s in segments], junction_tolerance)
    for junction in junctions["junctions"]:
        junction["segment_ids"] = junction.pop("ids")
    junctions["interpretation"] = ("Corners, T-junctions, crossings and collinear gaps between wall segment axes; "
                                   "a gap is not confirmed as an opening and no segment is trimmed or merged.")
    result.update({"segments": segments, "segment_count": len(segments), "junctions": junctions,
                   "physical_walls_assembled": False,
                   "interpretation": ("Parallel wall-face LINE pairs within the requested thickness range. "
                                      "Segments overlap only where both faces are drawn; junctions are candidates only; openings, "
                                      "layers of construction and structural role are not "
                                      "determined, and ambiguous faces are not resolved.")})
    return result
