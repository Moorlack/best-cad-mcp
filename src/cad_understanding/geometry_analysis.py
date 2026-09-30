"""Reusable, read-only geometry report over CAD-IR; no architectural classification."""

import hashlib
import math
from collections import Counter
from copy import deepcopy

from .block_attributes import summarize_block_attributes
from . import boundaries as boundary_limits
from .boundaries import check_boundary
from .report_limits import GEOMETRY_LIST_PATHS, limit_lists, validate_max_list_items
from .boundary_relations import check_boundary_relations
from .line_geometry import diagnose_lines, validate_gap_tolerance
from .line_networks import build_line_networks
from .polyline_parts import split_mline, split_polyline
from .axis_junctions import validate_junction_tolerance
from .line_pairs import find_parallel_pairs, validate_angle_tolerance, validate_separation_range
from .scale_references import check_scale_references, validate_references


def _point(p):
    try:
        return (isinstance(p, (list, tuple)) and len(p) in (2, 3)
                and all(type(v) in (int, float) and math.isfinite(v) for v in p))
    except OverflowError:
        return False


def _selection(values, name):
    if values is not None and (not isinstance(values, list) or not values
                              or len(values) > 1000
                              or any(not isinstance(v, str) or not v.strip() for v in values)
                              or len(set(values)) != len(values)):
        raise ValueError(f"{name} must be a nonempty list of up to 1000 unique nonblank strings.")


def _line_exclusion_reason(geometry):
    """No endpoint keys at all means the scan did not store geometry; otherwise the values are bad."""
    keys = ('start', 'start_point', 'end', 'end_point')
    return 'invalid_coordinates' if any(k in geometry for k in keys) else 'geometry_not_captured'


def build_geometry_report(drawing_ir, handles=None, layers=None, gap_tolerance=None,
                          reference_lengths=None, parallel_separation_range=None,
                          parallel_angle_tolerance_degrees=None, junction_tolerance=None):
    """Pure Python entry point. Filters intersect; names are exact and never semantic."""
    _selection(handles, 'handles')
    _selection(layers, 'layers')
    validate_gap_tolerance(gap_tolerance)
    validate_separation_range(parallel_separation_range)
    validate_angle_tolerance(parallel_angle_tolerance_degrees)
    validate_junction_tolerance(junction_tolerance)
    if reference_lengths is not None:
        validate_references(reference_lengths)
    if drawing_ir.get('schema_version') != 'cad-ir/v2':
        raise ValueError('Geometry analysis requires cad-ir/v2.')
    section = drawing_ir.get('sections', {}).get('entities', {})
    if not isinstance(section.get('items'), list):
        raise ValueError('CAD-IR must include entities with raw geometry.')
    entities = section['items']
    selected = [e for e in entities if (handles is None or e.get('handle') in handles)
                and (layers is None or e.get('layer') in layers)]
    counts = Counter(str(e.get('handle') or '') for e in entities)
    drawing = deepcopy(drawing_ir.get('drawing', {}))
    identity = str(drawing.get('path') or drawing.get('name') or 'unknown')
    truncated = bool(section.get('truncated') or section.get('total', len(entities)) != len(entities))
    lines, boundaries, valid, unsupported, identity_errors = [], [], {}, [], []
    polyline_parts, polyline_excluded = [], []
    for entity in sorted(selected, key=lambda e: str(e.get('handle') or '')):
        h = str(entity.get('handle') or '')
        if not h or counts[h] != 1:
            identity_errors.append(h)
            continue
        g = entity.get('geometry') or {}
        kinds = {str(entity.get(k) or '').lower().removeprefix('acdb')
                 for k in ('entity_type', 'object_name')}
        if 'line' in kinds:
            good = _point(g.get('start', g.get('start_point'))) and _point(g.get('end', g.get('end_point')))
            lines.append({'id': 'geom_' + hashlib.sha256((identity+'\0'+h).encode()).hexdigest()[:20],
                          'handles': [h], 'shape': 'line' if good else 'unsupported',
                          'excluded_reason': None if good else _line_exclusion_reason(g),
                          'geometry': deepcopy(g), 'layer': entity.get('layer', '0')})
        elif kinds & {'polyline', '2dpolyline', 'lwpolyline'}:
            parts, skipped = split_polyline(
                h, g, 'geom_' + hashlib.sha256((identity+'\0'+h).encode()).hexdigest()[:20],
                entity.get('layer', '0'))
            polyline_parts.extend(parts)
            polyline_excluded.extend(skipped)
            check = check_boundary(g) if len(boundaries) < boundary_limits.MAX_BOUNDARY_CHECKS else {
                'status': 'not_verified', 'reason': 'report_boundary_limit_exceeded',
                'geometric_area_drawing_units_squared': None}
            boundaries.append({'handle': h, **check})
            if check['status'] == 'valid_simple_polygon':
                valid[h] = g
        elif 'mline' in kinds:
            parts, skipped = split_mline(
                h, g, 'geom_' + hashlib.sha256((identity+'\0'+h).encode()).hexdigest()[:20],
                entity.get('layer', '0'))
            polyline_parts.extend(parts)
            polyline_excluded.extend(skipped)
        else:
            unsupported.append({'handle': h, 'reason': 'entity_type_not_supported_for_geometry_checks'})
    missing = sorted(set(handles or []) - {e.get('handle') for e in selected})
    missing_layers = sorted(set(layers or []) - {e.get('layer') for e in selected})
    incomplete = truncated or bool(identity_errors or missing or missing_layers)
    diagnostics = diagnose_lines(lines + polyline_parts, incomplete, gap_tolerance, drawing.get('units', 'unknown'),
                                 extra_excluded=polyline_excluded)
    networks = build_line_networks(lines + polyline_parts, diagnostics)
    # Domain-neutral schema; the architectural adapter retains its legacy fields.
    for group in networks['groups']:
        group['source_geometry_ids'] = group.pop('source_candidate_ids')
    relations = check_boundary_relations(valid)
    relations['excluded_contour_handles'] = [b['handle'] for b in boundaries if b['status'] != 'valid_simple_polygon']
    relations['entity_coverage_truncated'] = incomplete
    for boundary in boundaries:
        boundary.pop('floor_area_verified', None)
    result = {'schema_version': 'geometry-analysis/v1', 'drawing': drawing,
              'source': {'kind': 'cached_cad_ir', 'freshness': 'unverified'},
              'selection': {'handles': handles, 'layers': layers, 'combination': 'intersection',
                            'missing_or_filtered_handles': missing, 'missing_or_filtered_layers': missing_layers},
              'coverage': {'snapshot_entities': len(entities), 'selected_entities': len(selected),
                           'snapshot_truncated': truncated, 'invalid_identity_handles': sorted(set(identity_errors)),
                           'unsupported_entities': unsupported},
              'line_diagnostics': diagnostics, 'line_networks': networks,
              'boundary_checks': boundaries, 'boundary_relations': relations,
              'block_annotations': summarize_block_attributes(selected),
              'limitations': ['Geometry evidence only; no domain classification or automatic repair.',
                              'Horizontal LINE and horizontal WCS contours (straight or bulged) only; inspect exclusions.',
                              'Declared units do not verify scale. Snapshot freshness must be established by a scan.']}
    if parallel_separation_range is not None:
        result['parallel_line_pairs'] = find_parallel_pairs(
            lines + polyline_parts, parallel_separation_range, parallel_angle_tolerance_degrees, incomplete,
            junction_tolerance=junction_tolerance, include_junctions=True, extra_excluded=polyline_excluded)
    if reference_lengths is not None:
        scoped = deepcopy(drawing_ir)
        scoped['sections']['entities']['items'] = selected
        result['scale_reference_check'] = check_scale_references(scoped, reference_lengths)
    return result


def analyze_geometry(entity_limit=10000, handles=None, layers=None, gap_tolerance=None,
                     reference_lengths=None, parallel_separation_range=None,
                     parallel_angle_tolerance_degrees=None, junction_tolerance=None, database=None,
                     max_list_items=200):
    # Lazy imports keep the pure entry point independent of SQLite/AutoCAD/MCP runtime.
    from .ir_builder import build_drawing_ir
    from .result import error_result, ok_result

    try:
        if type(entity_limit) is not int or not 1 <= entity_limit <= 100000:
            raise ValueError('entity_limit must be an integer between 1 and 100000.')
        _selection(handles, 'handles')
        _selection(layers, 'layers')
        validate_gap_tolerance(gap_tolerance)
        validate_separation_range(parallel_separation_range)
        validate_angle_tolerance(parallel_angle_tolerance_degrees)
        validate_junction_tolerance(junction_tolerance)
        validate_max_list_items(max_list_items)
        if reference_lengths is not None:
            validate_references(reference_lengths)
        snapshot = build_drawing_ir(database=database, rescan=False, sections=['entities'],
                                    entity_limit=entity_limit, include_raw=True)
        report = build_geometry_report(snapshot, handles, layers, gap_tolerance, reference_lengths,
                                       parallel_separation_range, parallel_angle_tolerance_degrees,
                                       junction_tolerance)
    except ValueError as exc:
        return error_result(str(exc))
    from .snapshot_freshness import apply_to_report, check_snapshot_freshness
    freshness_warning = apply_to_report(report, check_snapshot_freshness(database))
    warnings = [freshness_warning, 'geometry_scale_unverified']
    if limit_lists(report, GEOMETRY_LIST_PATHS, max_list_items):
        warnings.append('report_lists_truncated')
    return ok_result('Built domain-neutral geometry report; inspect coverage and limitations.',
                     data={'report': report}, warnings=warnings)
