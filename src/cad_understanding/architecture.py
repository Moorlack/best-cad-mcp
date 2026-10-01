"""Read-only architectural candidate inventory over an existing CAD-IR snapshot.

Names are evidence, never proof of a building element or structural function.
No scan, CAD mutation, structural calculation, or semantic-cache write occurs here.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.cad_database import CADDatabase

from .ir_builder import build_drawing_ir
from .block_attributes import summarize_block_attributes
from . import boundaries as boundary_limits
from .boundaries import check_boundary
from .boundary_relations import check_boundary_relations
from .project_card import get_project_card
from .project_context import build_project_context
from .scale_references import check_scale_references, validate_references
from .wall_lines import diagnose_wall_lines, validate_gap_tolerance
from .wall_networks import build_wall_networks
from .axis_junctions import validate_junction_tolerance
from .dimension_scale import check_dimension_scale
from .report_limits import (
    ARCHITECTURE_LIST_PATHS, DEFAULT_MAX_LIST_ITEMS, DEFAULT_MAX_RESPONSE_CHARS, fit_report,
    validate_max_list_items, validate_max_response_chars)
from .block_contents import expand_block_lines
from .plan_clusters import find_plan_clusters
from .layer_visibility import split_hidden
from .plan_summary import build_plan_summary
from .quantities import build_quantity_summary
from .thickness_estimate import estimate_wall_thickness
from .name_profiles import build_rules, tokens as name_tokens, validate_name_aliases
from .opening_swings import arc_from_geometry
from .room_loops import find_room_loops
from .wall_runs import build_wall_runs
from .wall_openings import relate_openings, validate_opening_max_width
from .wall_pairs import build_wall_segment_candidates, validate_wall_thickness_range
from .result import error_result, ok_result


# Whole tokens avoid matching WALL in WALLPAPER or COL in COLOR; see name_profiles for the vocabularies.
NAME_RULES = build_rules()


def _tokens(value: Any) -> set[str]:
    return name_tokens(value)


def _point(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple)) and len(value) in (2, 3)
        and all(isinstance(n, (int, float)) and not isinstance(n, bool)
                and math.isfinite(n) for n in value)
    )


def _shape(entity: dict) -> tuple[str, list[str]]:
    """Recognize only supported geometry; preserve curves without flattening them."""
    geometry = entity.get("geometry") or {}
    kinds = {str(entity.get(key) or "").lower().removeprefix("acdb")
             for key in ("object_name", "entity_type")}
    if "line" in kinds:
        start = geometry.get("start", geometry.get("start_point"))
        end = geometry.get("end", geometry.get("end_point"))
        if _point(start) and _point(end) and list(start) != list(end):
            return "line", []
    if kinds & {"polyline", "2dpolyline", "lwpolyline"}:
        vertices = geometry.get("vertices", geometry.get("points", []))
        if isinstance(vertices, list) and len(vertices) >= 2 and all(_point(p) for p in vertices):
            closed = geometry.get("closed") is True or vertices[0] == vertices[-1]
            if closed and len({tuple(p) for p in vertices}) >= 3:
                return "closed_polyline", ["boundary_topology_not_verified"]
            return "open_polyline", []
    if "mline" in kinds:
        vertices = geometry.get("vertices", [])
        if isinstance(vertices, list) and len(vertices) >= 2 and all(_point(p) for p in vertices):
            return "mline", []
    if any(kind.startswith("blockref") for kind in kinds):
        if _point(geometry.get("insertion_point")):
            return "block_reference", ["block_contents_not_interpreted"]
    if "circle" in kinds:
        radius = geometry.get("radius")
        if (_point(geometry.get("center")) and isinstance(radius, (int, float))
                and not isinstance(radius, bool) and math.isfinite(radius) and radius > 0):
            return "circle", []
    return "unsupported", ["unsupported_or_missing_geometry"]


def _compatible(category: str, shape: str) -> bool:
    if category in {"slab_boundary", "room_boundary"}:
        return shape == "closed_polyline"
    if category == "grid":
        return shape == "line"
    if shape == "mline":
        return category == "wall"
    if category == "column":
        return shape in {"closed_polyline", "circle", "block_reference"}
    return shape in {"line", "open_polyline", "closed_polyline", "block_reference"}


def _validate_wall_parameters(thickness_range, junction_tolerance, max_width):
    """Validate wall options; "auto" thickness/opening width are estimated from the drawing later."""
    if thickness_range != "auto":
        validate_wall_thickness_range(thickness_range)
    validate_junction_tolerance(junction_tolerance, "wall_junction_tolerance")
    if max_width == "auto":
        if thickness_range is None:
            raise ValueError("wall_opening_max_width requires wall_thickness_range to pair wall faces first.")
        return
    _validate_opening_request(thickness_range, max_width)


def _validate_opening_request(thickness_range, max_width):
    validate_opening_max_width(max_width)
    if max_width is not None and thickness_range is None:
        raise ValueError("wall_opening_max_width requires wall_thickness_range to pair wall faces first.")


def build_architectural_report(drawing_ir: dict, wall_gap_tolerance=None,
                               wall_thickness_range=None, wall_junction_tolerance=None,
                               wall_opening_max_width=None, name_aliases=None,
                               include_hidden_layers=False) -> dict:
    """Convert CAD-IR v2 to a deterministic, drawing-scoped candidate report.

Confidence is an ordinal rule label, not a calibrated probability. Even MEDIUM
requires human review. Candidate counts are not counts of physical elements.
"""
    validate_gap_tolerance(wall_gap_tolerance)
    _validate_wall_parameters(wall_thickness_range, wall_junction_tolerance, wall_opening_max_width)
    rules = build_rules(name_aliases)
    if drawing_ir.get("schema_version") != "cad-ir/v2":
        raise ValueError("Architectural analysis requires cad-ir/v2.")
    section = drawing_ir.get("sections", {}).get("entities")
    if not isinstance(section, dict) or not isinstance(section.get("items"), list):
        raise ValueError("CAD-IR must include the entities section with raw geometry.")
    entities = section["items"]
    hidden_layers = {}
    if not include_hidden_layers:
        # Frozen/off layers are not part of the displayed plan (other storeys, ceiling plans, ...).
        entities, hidden_layers = split_hidden(entities)
    virtual_lines, expanded_refs = expand_block_lines(entities, set().union(*rules.values()))
    if virtual_lines:
        entities = entities + virtual_lines
    drawing = deepcopy(drawing_ir.get("drawing", {}))
    identity = str(drawing.get("path") or drawing.get("name") or "unknown")
    candidates, unclassified, issues = [], [], []
    if hidden_layers:
        issues.append({"code": "hidden_layer_entities_skipped", "handles": [],
                       "message": f"{sum(hidden_layers.values())} entities on frozen or off layers were skipped "
                       f"({', '.join(sorted(hidden_layers)[:10])}{' ...' if len(hidden_layers) > 10 else ''}); "
                       "pass include_hidden_layers=true to analyse them."})
    boundary_checks = []
    valid_boundaries = {}
    boundary_budget = boundary_limits.MAX_BOUNDARY_CHECKS

    def issue(code: str, handles: list[str], message: str) -> None:
        issues.append({"code": code, "handles": handles, "message": message})

    issue("snapshot_freshness_unverified", [],
          "Analyze a fresh full scan of the intended drawing/space; this tool reads the cache only.")
    if str(drawing.get("units", "unknown")).lower() in {"", "unknown", "unitless", "0"}:
        issue("units_unverified", [], "Confirm drawing units against dimensions before using coordinates.")
    elif not drawing.get("units_metadata", {}).get("geometry_scale_verified"):
        issue("geometry_scale_unverified", [],
              "INSUNITS declares insertion units only; verify geometry scale against dimensions before calculations.")
    total = section.get("total", len(section["items"]))
    truncated = bool(section.get("truncated") or total != len(section["items"]))
    if truncated:
        issue("incomplete_entity_coverage", [], "The report does not include every scanned entity.")
    if not entities:
        issue("empty_snapshot", [], "No entities available; this does not prove the drawing is empty.")
    blocks = drawing_ir.get("sections", {}).get("blocks", {}).get("items", [])
    expanded_xrefs = Counter(str((e.get("geometry") or {}).get("xref_insert_handle") or "") for e in entities
                             if (e.get("geometry") or {}).get("xref_insert_handle"))
    if expanded_xrefs:
        issue("xref_contents_expanded", sorted(expanded_xrefs),
              f"{sum(expanded_xrefs.values())} entities from {len(expanded_xrefs)} xref references were read from the "
              "referenced files and placed in host coordinates (layers 'Xref|Layer', handles '<insert>/<handle>'); "
              "nested xrefs inside them are not followed.")
    if any(block.get("is_xref") for block in blocks):
        xref_names = {str(block.get("name") or "") for block in blocks if block.get("is_xref")}
        xref_references = sorted(str(e.get("handle") or "") for e in entities
                                 if str((e.get("geometry") or {}).get("block_name") or "") in xref_names
                                 and str(e.get("handle") or "") not in expanded_xrefs)
        if xref_references or not expanded_xrefs:
            issue("xref_contents_unverified", [], "Referenced drawings may contain additional architecture.")
        if xref_references:
            issue("xref_reference_not_expanded", xref_references,
                  "These references insert external drawings; their content is not read or classified "
                  "(scan with include_xrefs=true to read them).")

    if expanded_refs:
        issue("block_contents_expanded", sorted(expanded_refs),
              f"{sum(expanded_refs.values())} lines inside {len(expanded_refs)} block references were placed in "
              "WCS and classified by their own layer names (virtual handles '<block handle>/L<n>'); "
              "nested blocks and other entity types inside blocks are not read.")
    handle_counts = Counter(str(e.get("handle") or "") for e in entities)
    for entity in sorted(entities, key=lambda e: str(e.get("handle") or "")):
        handle = str(entity.get("handle") or "")
        if not handle or handle_counts[handle] != 1:
            issue("invalid_entity_identity", [handle] if handle else [],
                  "Missing or duplicate handle; entity excluded from classification.")
            continue
        geometry = entity.get("geometry") or {}
        properties = entity.get("properties") or {}
        shape, limitations = _shape(entity)
        kinds = {str(entity.get(key) or "").lower().removeprefix("acdb")
                 for key in ("object_name", "entity_type")}
        boundary_check = None
        if kinds & {"polyline", "2dpolyline", "lwpolyline"} and (
                geometry.get("closed") is True or shape == "closed_polyline"):
            if boundary_budget:
                boundary_check = check_boundary(geometry)
                boundary_budget -= 1
            else:
                boundary_check = {"status": "not_verified", "reason": "report_boundary_limit_exceeded",
                                  "geometric_area_drawing_units_squared": None,
                                  "floor_area_verified": False, "holes_checked": False}
            boundary_checks.append({"handle": handle, **boundary_check})
            if boundary_check["status"] == "valid_curved_contour":
                limitations = [w for w in limitations if w != "boundary_topology_not_verified"]
                limitations.append("floor_area_and_holes_not_verified")
                issue("boundary_valid_curved_contour", [handle],
                      "Bulged contour: area is exact, self-intersection was tested on a chord approximation; "
                      "it is excluded from containment relations and its floor area and holes are unverified.")
            elif boundary_check["status"] != "valid_simple_polygon":
                issue("boundary_" + boundary_check["status"], [handle], boundary_check["reason"])
            else:
                limitations = [w for w in limitations if w != "boundary_topology_not_verified"]
                limitations.append("floor_area_and_holes_not_verified")
                valid_boundaries[handle] = geometry
        block_name = geometry.get("block_name") or properties.get("block_name") or ""
        names = {"layer": str(entity.get("layer") or "0")}
        if shape == "block_reference" and block_name:
            names["block_name"] = str(block_name)
        effective_name = geometry.get("effective_name")
        if shape == "block_reference" and effective_name and effective_name != block_name:
            names["effective_name"] = str(effective_name)
        evidence_by_type = {}
        for category, aliases in rules.items():
            evidence = [
                {"source": source, "value": value, "matched_tokens": sorted(_tokens(value) & aliases)}
                for source, value in names.items() if _tokens(value) & aliases
            ]
            if evidence:
                evidence_by_type[category] = evidence
        compatible = [category for category in evidence_by_type if _compatible(category, shape)]
        if len(evidence_by_type) > 1:
            issue("conflicting_semantic_hints", [handle],
                  "Multiple architectural categories occur in names; no category is confirmed.")
        for category in evidence_by_type.keys() - set(compatible):
            issue("name_geometry_mismatch", [handle],
                  f"Name suggests {category}, but supported geometry does not establish a candidate.")
        # A closed outline alone never establishes a room or a slab.
        if not compatible and shape == "closed_polyline" and not evidence_by_type:
            compatible = ["closed_boundary"]
        if not compatible:
            unclassified.append({"handle": handle, "layer": names["layer"],
                                 "entity_type": entity.get("entity_type"),
                                 "reason": limitations or ["no_supported_architectural_evidence"]})
        for category in sorted(compatible):
            evidence = evidence_by_type.get(category, [])
            confidence = "MEDIUM" if evidence and len(evidence_by_type) == 1 else "LOW"
            hidden = entity.get("visible") is False or geometry.get("visible") is False
            if shape == "block_reference" or hidden:
                confidence = "LOW"
            key = "\0".join([identity, handle, category])
            warnings = ["requires_architectural_review", *limitations]
            if len(evidence_by_type) > 1:
                warnings.append("conflicting_semantic_hints")
            if hidden:
                warnings.append("entity_not_visible")
            candidates.append({
                "id": "arch_" + hashlib.sha256(key.encode()).hexdigest()[:20],
                "category": category, "status": "candidate", "confidence": confidence,
                "handles": [handle], "layer": names["layer"], "shape": shape,
                "geometry": deepcopy(geometry), "bbox": deepcopy(entity.get("bbox", {})),
                "evidence": evidence + [{"source": "geometry", "value": shape}],
                "warnings": warnings, "structural_role": "unknown",
                "boundary_check": deepcopy(boundary_check),
            })

    dimension_scale = check_dimension_scale(entities)
    if dimension_scale["checked"]:
        if dimension_scale["status"] == "agrees":
            issue("dimension_scale_consistent", [],
                  f"{dimension_scale['checked']} linear dimensions agree with the drawn geometry; "
                  "units and real-world scale are still only declared.")
        else:
            issue("dimension_scale_mismatch", [i["handle"] for i in dimension_scale["items"] if i["status"] == "differs"],
                  "Some linear dimension values differ from the distance between their extension-line points; "
                  "the drawing may not be drawn to scale or uses a dimension factor.")
    wall_lines = diagnose_wall_lines(candidates, truncated, wall_gap_tolerance, drawing.get("units", "unknown"))
    for gap in wall_lines["gap_search"]["candidates"]:
        issue("wall_endpoint_gap_candidate", gap["handles"],
              "Endpoints lie within the supplied tolerance; review whether the separation is intentional.")
    if wall_lines["excluded"] or wall_lines["unverified_pairs"] or truncated:
        issue("wall_line_diagnostics_incomplete", [],
              "Only eligible named wall LINE candidates were checked; inspect exclusions and coverage.")
    for relation in wall_lines["items"]:
        if relation["relation"] in {"duplicate", "overlap", "intersection"}:
            issue("wall_line_" + relation["relation"], relation["handles"],
                  "Review the relationship of these wall candidates; no physical wall or repair is inferred.")
    thickness_estimate = None
    if wall_thickness_range == "auto" or wall_opening_max_width == "auto":
        thickness_estimate = estimate_wall_thickness(candidates)
        if thickness_estimate is None:
            issue("wall_thickness_not_estimated", [],
                  "No plausible parallel wall-face pairs were found to estimate the wall thickness; walls were not paired.")
            wall_thickness_range = None if wall_thickness_range == "auto" else wall_thickness_range
            wall_opening_max_width = None
        else:
            if wall_thickness_range == "auto":
                wall_thickness_range = thickness_estimate["range_drawing_units"]
            if wall_opening_max_width == "auto":
                wall_opening_max_width = thickness_estimate["suggested_opening_max_width_drawing_units"]
            issue("wall_parameters_estimated", [],
                  f"Wall thickness ~{thickness_estimate['peak_drawing_units']:.6g} drawing units estimated from "
                  f"{thickness_estimate['pairs_considered']} face pairs; review wall_thickness_estimate before relying on it.")
    wall_segments = build_wall_segment_candidates(candidates, wall_thickness_range, truncated,
                                                  wall_junction_tolerance)
    if wall_segments["requested"]:
        swing_arcs = []
        for entity in entities:
            if "arc" in {str(entity.get(k) or "").lower().removeprefix("acdb") for k in ("object_name", "entity_type")}:
                arc = arc_from_geometry(entity.get("geometry") or {})
                if arc is not None and entity.get("handle"):
                    swing_arcs.append((str(entity["handle"]), arc))
        openings = relate_openings(candidates, wall_segments["segments"], wall_opening_max_width, identity,
                                   arcs=swing_arcs)
        wall_segments["openings"] = openings
        # Opening-gap search links collinear segments beyond the (width-based) junction tolerance.
        wall_segments["runs"] = build_wall_runs(wall_segments["segments"], wall_segments["junctions"]["junctions"],
                                                gaps=openings["gaps"])
        wall_segments["run_count"] = len(wall_segments["runs"])
        wall_segments["plan_clusters"] = find_plan_clusters(wall_segments["segments"])
        if wall_segments["plan_clusters"]["multiple_plan_clusters"]:
            issue("multiple_plan_clusters", [],
                  f"Wall segments form {wall_segments['plan_clusters']['cluster_count']} spatially separate groups; "
                  "the model space may hold several plans or details (not inferred as storeys).")
        wall_segments["room_loops"] = find_room_loops(
            wall_segments["segments"], wall_segments["junctions"]["junctions"],
            gaps=openings["gaps"], tolerance=wall_junction_tolerance,
            columns=[c for c in candidates if c["category"] == "column"])
        for segment in wall_segments["segments"]:
            # Geometric relation checked; the opening itself stays unverified.
            segment["openings_checked"] = True
        for gap_id in openings["gaps_without_opening_candidate"]:
            gap = next(g for g in openings["gaps"] if g["id"] == gap_id)
            if gap.get("swing_arcs"):
                issue("wall_gap_swing_arc_without_door_candidate", [str(s["source"]) for s in gap["swing_arcs"]],
                      f"Gap {gap_id} has a door-swing-like arc but no door/window/opening candidate; "
                      "the door symbol may sit on an unrecognised layer.")
                continue
            issue("wall_gap_without_opening_candidate", [],
                  f"Gap {gap_id} between wall segments has no door/window/opening candidate; "
                  "check for an unnamed opening or a drawing break.")
        for item in openings["openings"]:
            if item["status"] == "not_on_wall_segment":
                issue("opening_not_on_wall_segment", item["handles"],
                      "Door/window/opening candidate does not overlap any paired wall segment.")
    for segment in wall_segments["segments"]:
        if segment["ambiguous"]:
            issue("wall_segment_ambiguous_face", segment["shared_line_handles"],
                  "A wall face pairs with several parallel lines; review which pairing is intended.")
    relations = check_boundary_relations(valid_boundaries)
    relations["excluded_contour_handles"] = [c["handle"] for c in boundary_checks
                                              if c["status"] != "valid_simple_polygon"]
    relations["entity_coverage_truncated"] = truncated
    if relations["unverified_pairs"] or relations["excluded_contour_handles"] or truncated:
        issue("boundary_relations_incomplete", [],
              "Relations cover only eligible contours; inspect exclusions, pair limits and entity coverage.")
    for relation in relations["items"]:
        if relation["relation"] == "contains":
            issue("nested_boundary_requires_review", [relation["outer_handle"], relation["inner_handle"]],
                  "Nested contours may represent holes or unrelated objects; no area is subtracted.")
        else:
            issue("boundary_intersection_or_touch", relation["handles"],
                  "Contour edges intersect or touch within tolerance; review their intended relationship.")
    annotations = summarize_block_attributes(entities)
    if annotations["partial_block_handles"] or annotations["not_captured_block_handles"]:
        issue("block_attributes_incomplete",
              annotations["partial_block_handles"] + annotations["not_captured_block_handles"],
              "Some block attributes were not captured completely; inspect the cached per-block read status.")
    if annotations["truncated"]:
        issue("block_attribute_report_truncated", [],
              "Only the first 200 cached attributes are included; inspect individual blocks in CAD-IR.")
    return {
        "schema_version": "architectural-analysis/v1",
        "block_annotations": annotations,
        "boundary_checks": boundary_checks,
        "boundary_relations": relations,
        "dimension_scale_check": dimension_scale,
        "wall_thickness_estimate": thickness_estimate,
        "quantity_summary": build_quantity_summary(wall_segments, candidates),
        "wall_line_diagnostics": wall_lines,
        "wall_networks": build_wall_networks(candidates, wall_lines),
        "wall_segment_candidates": wall_segments,
        "drawing": drawing,
        "source": {"kind": "cached_cad_ir", "ir_generated_at": drawing_ir.get("generated_at"),
                   "freshness": "unverified", "quality": deepcopy(drawing_ir.get("quality", {})),
                   "warnings": deepcopy(drawing_ir.get("manifest", {}).get("warnings", []))},
        "coverage": {"scanned_entities": total, "examined_entities": len(entities),
                     "hidden_layer_entities_skipped": sum(hidden_layers.values()),
                     "hidden_layers_skipped": dict(sorted(hidden_layers.items())),
                     "truncated": truncated, "unclassified_entities": len(unclassified)},
        "summary": {"candidate_count": len(candidates),
                    "by_category": dict(sorted(Counter(c["category"] for c in candidates).items()))},
        "candidates": candidates, "unclassified": unclassified, "issues": issues,
        "structural_design_ready": False,
        "missing_for_structural_design": [
            "confirmed_units_and_levels", "reviewed_architectural_geometry",
            "confirmed_supports_and_load_paths", "materials_and_loads", "project_code_basis",
        ],
        "limitations": [
            "Rule-based naming and primitive geometry only; confidence is not a probability.",
            "Candidates represent source entities, not grouped physical walls or complete building elements.",
            "Wall faces are paired and openings related to them only when wall_thickness_range is supplied; opening sizes/types, floor assignment and block/xref traversal are not determined.",
            "Single horizontal contours (straight or bulged) can have geometric area; bulged contours are flagged valid_curved_contour (exact area, approximate self-intersection test) and are not used for containment relations; floor areas and holes remain unverified.",
            "Only model space is scanned; paper-space layouts and xref contents are not read, and stories/levels are not inferred.",
            "No exterior/interior or load-bearing classification, code checks, or member sizing.",
        ],
    }


def analyze_architectural_drawing(entity_limit: int = 10000,
                                  database: Optional[CADDatabase] = None,
                                  project_id: Optional[str] = None,
                                  reference_lengths: Optional[List[Dict[str, Any]]] = None,
                                  wall_gap_tolerance: Optional[float] = None,
                                  wall_thickness_range: Optional[List[float]] = None,
                                  wall_junction_tolerance: Optional[float] = None,
                                  wall_opening_max_width: Optional[float] = None,
                                  name_aliases: Optional[Dict[str, List[str]]] = None,
                                  include_hidden_layers: bool = False,
                                  max_list_items: Optional[int] = DEFAULT_MAX_LIST_ITEMS,
                                  max_response_chars: Optional[int] = DEFAULT_MAX_RESPONSE_CHARS) -> Dict[str, Any]:
    """Read scanned metadata without rescanning or altering the DWG."""
    if isinstance(entity_limit, bool) or not isinstance(entity_limit, int) or not 1 <= entity_limit <= 100000:
        return error_result("entity_limit must be an integer between 1 and 100000.")
    project = None
    try:
        validate_gap_tolerance(wall_gap_tolerance)
        _validate_wall_parameters(wall_thickness_range, wall_junction_tolerance, wall_opening_max_width)
        validate_name_aliases(name_aliases)
        validate_max_list_items(max_list_items)
        validate_max_response_chars(max_response_chars)
    except ValueError as exc:
        return error_result(str(exc))
    if reference_lengths is not None:
        try:
            validate_references(reference_lengths)
        except ValueError as exc:
            return error_result(str(exc))
    if project_id is not None:
        project = get_project_card(project_id, database=database)
        if not project["ok"]:
            return project
    drawing_ir = build_drawing_ir(
        database=database, rescan=False, sections=["entities", "blocks", "quality"],
        entity_limit=entity_limit, include_raw=True,
    )
    report = build_architectural_report(drawing_ir, wall_gap_tolerance=wall_gap_tolerance,
                                        wall_thickness_range=wall_thickness_range,
                                        wall_junction_tolerance=wall_junction_tolerance,
                                        wall_opening_max_width=wall_opening_max_width,
                                        name_aliases=name_aliases,
                                        include_hidden_layers=include_hidden_layers)
    from .snapshot_freshness import MESSAGES, apply_to_report, check_snapshot_freshness
    freshness = check_snapshot_freshness(database)
    code = apply_to_report(report, freshness)
    for item in report["issues"]:
        if item["code"] == "snapshot_freshness_unverified":
            item.update(code=code, message=MESSAGES[freshness["status"]])
    if reference_lengths is not None:
        report["scale_reference_check"] = check_scale_references(drawing_ir, reference_lengths)
        for check in report["scale_reference_check"]["checks"]:
            if check["status"] != "agrees":
                report["issues"].append({"code": "scale_reference_" + check["status"],
                                         "handles": [check["reference"]["handle"]],
                                         "message": check["reason"] or "Measured LINE length differs from the supplied reference."})
    if project is not None:
        context = build_project_context(report["drawing"], project["data"]["card"],
                                        project["data"]["readiness"])
        report["project_context"] = context
        for warning in context["warnings"]:
            report["issues"].append({"code": warning, "handles": [],
                                     "message": "Review project_context unit declarations; no conversion or scale confirmation was performed."})
    report["plan_summary"] = build_plan_summary(report)
    handles = sorted({handle for c in report["candidates"] for handle in c["handles"]})
    warnings = sorted({issue["code"] for issue in report["issues"]})
    trimmed = fit_report(report, ARCHITECTURE_LIST_PATHS, max_list_items, max_response_chars)
    if trimmed:
        warnings = sorted({*warnings, "report_lists_truncated"})
        returned = (trimmed.get("candidates") or {}).get("returned")
        handles = handles[:returned if returned is not None else min(max_list_items or 200, 200)]
    return ok_result(
        "Built architectural candidate inventory; engineering interpretation remains unverified.",
        data={"report": report},
        handles=handles,
        warnings=warnings,
        next_tools=["explain_entity", "validate_geometry", "export_view_image_with_mapping"],
    )


def plan_summary_result(result: Dict[str, Any], scan_message: Optional[str] = None) -> Dict[str, Any]:
    """Reduce an analyze_architectural_drawing result to its plan_summary."""
    if not result.get("ok"):
        if scan_message is not None:
            result.setdefault("data", {})["scan_message"] = scan_message
        return result
    summary = result["data"]["report"]["plan_summary"]
    warnings = [w for w in result.get("warnings", []) if w != "report_lists_truncated"]
    return ok_result(summary["text"].splitlines()[0],
                     data={"plan_summary": summary, "scan_message": scan_message},
                     warnings=warnings, next_tools=["analyze_architectural_drawing", "render_drawing_view"])
