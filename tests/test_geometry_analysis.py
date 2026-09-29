import asyncio
import subprocess
import sys
from copy import deepcopy
from unittest.mock import patch

import pytest
from mcp import Client

from src import server
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.geometry_analysis import build_geometry_report


def line(h, a, b, layer='PART-OUTLINE'):
    return {'handle': h, 'entity_type': 'AcDbLine', 'layer': layer,
            'geometry': {'start': a, 'end': b}}


def snapshot(items):
    return {'schema_version': 'cad-ir/v2', 'drawing': {'path': 'part.dwg', 'units': 'mm',
            'units_metadata': {'status': 'declared', 'units': 'mm'}},
            'sections': {'entities': {'items': items, 'total': len(items)}}}


def test_non_architectural_geometry_selection_groups_and_reference():
    ir = snapshot([line('A', [0, 0], [10, 0]), line('B', [10, 0], [20, 0]),
                   line('C', [20.25, 0], [30, 0]), line('D', [0, 0], [10, 0], 'OTHER')])
    before = deepcopy(ir)
    r = build_geometry_report(ir, layers=['PART-OUTLINE'], gap_tolerance=.5,
                              reference_lengths=[{'handle': 'A', 'length': 1, 'units': 'cm', 'source': 'fixture'}])
    assert r['line_networks']['group_count'] == 2
    assert r['line_networks']['groups'][0]['handles'] == ['A', 'B']
    assert r['line_networks']['gap_links'][0]['handles'] == ['B', 'C']
    assert r['scale_reference_check']['checks'][0]['status'] == 'agrees'
    assert build_architectural_report(ir)['wall_networks']['group_count'] == 0
    assert 'wall' not in str(r['line_networks']).lower()
    assert 'architectural' not in str(r).lower()
    assert ir == before
    assert build_geometry_report(ir, handles=['D'], layers=['PART-OUTLINE'])['selection']['missing_or_filtered_handles'] == ['D']


def test_architecture_and_general_kernel_have_identical_relations():
    ir = snapshot([line('A', [0, 0], [10, 0], 'A-WALL'), line('B', [5, 0], [15, 0], 'A-WALL')])
    generic = build_geometry_report(ir)['line_networks']['groups'][0]
    old = build_architectural_report(ir)['wall_networks']['groups'][0]
    assert generic['handles'] == old['handles']
    assert generic['relation_counts'] == old['relation_counts']
    assert generic['bbox_wcs'] == old['bbox_wcs']
    assert old['id'].startswith('wall_network_')


def test_bad_identity_geometry_and_missing_selection_report_incompleteness():
    ir = snapshot([line('A', [0, 0], [1, 0]), line('A', [1, 0], [2, 0]),
                   line('B', [0, 0], [float('inf'), 0])])
    r = build_geometry_report(ir, handles=['A', 'B', 'MISSING'])
    assert r['coverage']['invalid_identity_handles'] == ['A']
    assert r['selection']['missing_or_filtered_handles'] == ['MISSING']
    assert not r['line_networks']['coverage_complete']
    assert r['line_diagnostics']['excluded'] == [{'handle': 'B', 'reason': 'invalid_coordinates'}]


@pytest.mark.parametrize('kwargs', [{'handles': []}, {'layers': ['']}, {'handles': ['A', 'A']},
                                   {'gap_tolerance': 0}, {'gap_tolerance': True}])
def test_invalid_request(kwargs):
    with pytest.raises(ValueError):
        build_geometry_report(snapshot([]), **kwargs)


def test_generic_contours_without_architectural_names():
    ir = snapshot([{'handle': 'P', 'entity_type': 'AcDbPolyline', 'layer': 'PART',
                    'geometry': {'vertices': [[0, 0], [10, 0], [10, 8], [0, 8]],
                                 'closed': True, 'bulges': [0]*4, 'bulges_complete': True,
                                 'normal': [0, 0, 1], 'vertices_coordinate_system': 'WCS'}}])
    r = build_geometry_report(ir)
    assert r['boundary_checks'][0]['geometric_area_drawing_units_squared'] == 80
    assert 'floor_area_verified' not in r['boundary_checks'][0]


@pytest.mark.parametrize('profile', ['lean', 'core', 'full'])
def test_generic_mcp_enabled(profile, monkeypatch):
    monkeypatch.setenv('CAD_MCP_TOOL_PROFILE', profile)
    assert server._tool_enabled('analyze_geometry')


def test_native_mcp_generic_report_and_readonly_contract():
    async def exercise():
        async with Client(server.mcp, raise_exceptions=True, mode='2026-07-28') as client:
            catalog = await client.list_tools()
            tool = next(t for t in catalog.tools if t.name == 'analyze_geometry')
            annotations = tool.model_dump(by_alias=True, mode='json')['annotations']
            assert annotations['readOnlyHint'] and not annotations['destructiveHint']
            return await client.call_tool('analyze_geometry', {'layers': ['PART-OUTLINE'], 'gap_tolerance': .5})
    with patch('src.cad_understanding.ir_builder.build_drawing_ir',
               return_value=snapshot([line('A', [0, 0], [1, 0])])):
        r = asyncio.run(exercise()).model_dump(by_alias=True, mode='json')
    assert r['structuredContent']['result']['data']['report']['line_networks']['included_lines'] == 1


def test_pure_entrypoint_without_site_packages_or_cad_runtime():
    code = """
from src.cad_understanding.geometry_analysis import build_geometry_report
r = build_geometry_report({'schema_version': 'cad-ir/v2', 'sections': {'entities': {'items': []}}})
assert r['schema_version'] == 'geometry-analysis/v1'
import sys
assert not any(k in sys.modules for k in ('mcp', 'win32com', 'src.cad_database', 'src.server'))
"""
    subprocess.run([sys.executable, '-S', '-c', code], check=True, capture_output=True, text=True)


def test_limits_and_truncated_snapshot_expose_partial_results():
    ir = snapshot([line(str(i), [i, 0], [i+1, 0]) for i in range(101)])
    r = build_geometry_report(ir)
    assert r['line_networks']['included_lines'] == 100
    assert not r['line_networks']['coverage_complete']
    ir = snapshot([line('A', [0, 0], [1, 0])])
    ir['sections']['entities']['truncated'] = True
    assert not build_geometry_report(ir)['line_networks']['coverage_complete']
