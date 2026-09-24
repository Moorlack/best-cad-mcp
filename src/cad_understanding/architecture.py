"""Read-only architectural candidate inventory over an existing CAD-IR snapshot.

Names are evidence, never proof of a building element or structural function.
No scan, CAD mutation, structural calculation, or semantic-cache write occurs here.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from copy import deepcopy
from typing import Any, Dict, Optional

from src.cad_database import CADDatabase

from .ir_builder import build_drawing_ir
from .block_attributes import summarize_block_attributes
from .boundaries import check_boundary
from .boundary_relations import check_boundary_relations
from .project_card import get_project_card
from .project_context import build_project_context
from .result import error_result, ok_result


# Whole tokens avoid matching WALL in WALLPAPER or COL in COLOR.
NAME_RULES = {
    "wall": {"wall", "walls"},
    "door": {"door", "doors"},
    "window": {"window", "windows", "glaz"},
    "opening": {"opening", "openings", "opng"},
    "grid": {"grid", "grids", "axis", "axes"},
    "column": {"column", "columns", "cols", "col"},
    "slab_boundary": {"slab", "slabs", "deck"},
    "room_boundary": {"room", "rooms"},
}


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z]+", str(value).lower()))


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
    if category == "column":
        return shape in {"closed_polyline", "circle", "block_reference"}
    return shape in {"line", "open_polyline", "closed_polyline", "block_reference"}


def build_architectural_report(drawing_ir: dict) -> dict:
    """Convert CAD-IR v2 to a deterministic, drawing-scoped candidate report.

Confidence is an ordinal rule label, not a calibrated probability. Even MEDIUM
requires human review. Candidate counts are not counts of physical elements.
"""
    if drawing_ir.get("schema_version") != "cad-ir/v2":
        raise ValueError("Architectural analysis requires cad-ir/v2.")
    section = drawing_ir.get("sections", {}).get("entities")
    if not isinstance(section, dict) or not isinstance(section.get("items"), list):
        raise ValueError("CAD-IR must include the entities section with raw geometry.")
    entities = section["items"]
    drawing = deepcopy(drawing_ir.get("drawing", {}))
    identity = str(drawing.get("path") or drawing.get("name") or "unknown")
    candidates, unclassified, issues = [], [], []
    boundary_checks = []
    valid_boundaries = {}
    boundary_budget = 100

    def issue(code: str, handles: list[str], message: str) -> None:
        issues.append({"code": code, "handles": handles, "message": message})

    issue("snapshot_freshness_unverified", [],
          "Analyze a fresh full scan of the intended drawing/space; this tool reads the cache only.")
    if str(drawing.get("units", "unknown")).lower() in {"", "unknown", "unitless", "0"}:
        issue("units_unverified", [], "Confirm drawing units against dimensions before using coordinates.")
    elif not drawing.get("units_metadata", {}).get("geometry_scale_verified"):
        issue("geometry_scale_unverified", [],
              "INSUNITS declares insertion units only; verify geometry scale against dimensions before calculations.")
    total = section.get("total", len(entities))
    truncated = bool(section.get("truncated") or total != len(entities))
    if truncated:
        issue("incomplete_entity_coverage", [], "The report does not include every scanned entity.")
    if not entities:
        issue("empty_snapshot", [], "No entities available; this does not prove the drawing is empty.")
    blocks = drawing_ir.get("sections", {}).get("blocks", {}).get("items", [])
    if any(block.get("is_xref") for block in blocks):
        issue("xref_contents_unverified", [], "Referenced drawings may contain additional architecture.")

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
            if boundary_check["status"] != "valid_simple_polygon":
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
        for category, aliases in NAME_RULES.items():
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
        "drawing": drawing,
        "source": {"kind": "cached_cad_ir", "ir_generated_at": drawing_ir.get("generated_at"),
                   "freshness": "unverified", "quality": deepcopy(drawing_ir.get("quality", {})),
                   "warnings": deepcopy(drawing_ir.get("manifest", {}).get("warnings", []))},
        "coverage": {"scanned_entities": total, "examined_entities": len(entities),
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
            "No wall pairing, opening-to-wall association, floor assignment, or block/xref traversal.",
            "Single straight horizontal contours can have geometric area; floor areas, holes and curved contours remain unverified.",
            "No exterior/interior or load-bearing classification, code checks, or member sizing.",
        ],
    }


def analyze_architectural_drawing(entity_limit: int = 10000,
                                  database: Optional[CADDatabase] = None,
                                  project_id: Optional[str] = None) -> Dict[str, Any]:
    """Read scanned metadata without rescanning or altering the DWG."""
    if isinstance(entity_limit, bool) or not isinstance(entity_limit, int) or not 1 <= entity_limit <= 100000:
        return error_result("entity_limit must be an integer between 1 and 100000.")
    project = None
    if project_id is not None:
        project = get_project_card(project_id, database=database)
        if not project["ok"]:
            return project
    drawing_ir = build_drawing_ir(
        database=database, rescan=False, sections=["entities", "blocks", "quality"],
        entity_limit=entity_limit, include_raw=True,
    )
    report = build_architectural_report(drawing_ir)
    if project is not None:
        context = build_project_context(report["drawing"], project["data"]["card"],
                                        project["data"]["readiness"])
        report["project_context"] = context
        for warning in context["warnings"]:
            report["issues"].append({"code": warning, "handles": [],
                                     "message": "Review project_context unit declarations; no conversion or scale confirmation was performed."})
    return ok_result(
        "Built architectural candidate inventory; engineering interpretation remains unverified.",
        data={"report": report},
        handles=sorted({handle for c in report["candidates"] for handle in c["handles"]}),
        warnings=sorted({issue["code"] for issue in report["issues"]}),
        next_tools=["explain_entity", "validate_geometry", "export_view_image_with_mapping"],
    )
