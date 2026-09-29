import asyncio
import math
from copy import deepcopy
from unittest.mock import patch

import pytest
from mcp import Client

from src import server
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.geometry_analysis import build_geometry_report


def line(h, a, b, layer='A-WALL'):
    return {'handle': h, 'entity_type': 'AcDbLine', 'layer': layer,
            'geometry': {'start': a, 'end': b}}


def snapshot(items, path='a.dwg', truncated=False):
    return {'schema_version': 'cad-ir/v2', 'drawing': {'path': path, 'units': 'mm'},
            'sections': {'entities': {'items': items, 'total': len(items), 'truncated': truncated}}}


def pairs(items, rng=(100, 300), tol=None, **kw):
    return build_geometry_report(snapshot(items, **kw), parallel_separation_range=list(rng),
                                 parallel_angle_tolerance_degrees=tol)['parallel_line_pairs']


def walls(items, rng=(100, 300), **kw):
    return build_architectural_report(snapshot(items, **kw), wall_thickness_range=list(rng))


def test_offset_pair_measures_separation_overlap_and_midline():
    r = pairs([line('A', [0, 0], [1000, 0]), line('B', [1200, 200], [200, 200])])
    assert r['pair_count'] == 1 and r['coverage_complete']
    p = r['pairs'][0]
    assert p['handles'] == ['A', 'B']
    assert p['separation_min'] == pytest.approx(200) and p['separation_max'] == pytest.approx(200)
    assert p['overlap_length'] == pytest.approx(800)
    assert p['overlap_ratios'] == [pytest.approx(0.8), pytest.approx(0.8)]
    assert p['midline_wcs'] == [[pytest.approx(200), pytest.approx(100), 0.0],
                                [pytest.approx(1000), pytest.approx(100), 0.0]]
    assert not p['ambiguous'] and r['unpaired_handles'] == []


def test_rejections_are_counted_not_reported_as_pairs():
    r = pairs([line('A', [0, 0], [1000, 0]),
               line('far', [0, 500], [1000, 500]),          # out of range
               line('shifted', [2000, 200], [3000, 200]),    # no projected overlap
               line('skew', [0, 1000], [1000, 1100]),        # not parallel
               line('cross', [500, -50], [500, 50]),         # perpendicular
               line('high', [0, 200, 30], [1000, 200, 30])])  # different plane
    assert r['pair_count'] == 0
    counts = r['rejected_pair_counts']
    assert counts['separation_out_of_range'] >= 1
    assert counts['no_projected_overlap'] >= 1
    assert counts['not_parallel'] >= 1
    assert counts['different_planes'] >= 1
    assert set(r['unpaired_handles']) == {'A', 'far', 'shifted', 'skew', 'cross', 'high'}


def test_angle_tolerance_is_explicit_and_bounded():
    items = [line('A', [0, 0], [1000, 0]), line('B', [0, 200], [1000, 201])]  # ~0.057 degrees
    assert pairs(items)['pair_count'] == 0
    tapered = pairs(items, tol=0.1)['pairs'][0]
    assert tapered['separation_min'] == pytest.approx(200)
    assert tapered['separation_max'] == pytest.approx(201)
    assert tapered['angle_deviation_degrees'] == pytest.approx(math.degrees(math.atan(1 / 1000)))
    with pytest.raises(ValueError, match='between 0 and 5'):
        pairs(items, tol=6)


@pytest.mark.parametrize('rng', [None, [], [100], [0, 10], [10, 5], [1, float('inf')], ['1', 2], [True, 2]])
def test_invalid_ranges_are_rejected(rng):
    if rng is None:
        assert 'parallel_line_pairs' not in build_geometry_report(snapshot([]))
        return
    with pytest.raises(ValueError, match='parallel_separation_range'):
        build_geometry_report(snapshot([]), parallel_separation_range=rng)


def test_shared_face_is_ambiguous_and_ids_are_stable():
    items = [line('A', [0, 0], [1000, 0]), line('B', [0, 200], [1000, 200]),
             line('C', [0, -200], [1000, -200])]
    before = deepcopy(items)
    r = pairs(items)
    assert [p['handles'] for p in r['pairs']] == [['A', 'B'], ['A', 'C']]
    assert r['ambiguous_handles'] == ['A']
    assert all(p['ambiguous'] and p['shared_line_handles'] == ['A'] for p in r['pairs'])
    assert items == before
    assert pairs(list(reversed(items)))['pairs'] == r['pairs']
    assert pairs(items, path='b.dwg')['pairs'][0]['id'] != r['pairs'][0]['id']


def test_incomplete_selection_marks_coverage():
    items = [line('A', [0, 0], [1000, 0]), line('B', [0, 200], [1000, 200])]
    assert not pairs(items, truncated=True)['coverage_complete']
    r = build_geometry_report(snapshot(items), handles=['A', 'B', 'MISSING'],
                              parallel_separation_range=[100, 300])['parallel_line_pairs']
    assert r['pair_count'] == 1 and not r['coverage_complete']


def test_wall_segments_from_named_wall_faces_only():
    items = [line('A', [0, 0], [5000, 0]), line('B', [0, 200], [5000, 200]),
             line('P1', [0, 1000], [5000, 1000], 'PART'), line('P2', [0, 1200], [5000, 1200], 'PART')]
    report = walls(items)
    seg = report['wall_segment_candidates']
    assert seg['segment_count'] == 1 and seg['requested']
    s = seg['segments'][0]
    assert s['handles'] == ['A', 'B'] and s['id'].startswith('wall_segment_')
    assert s['thickness_drawing_units'] == {'min': pytest.approx(200), 'max': pytest.approx(200),
                                            'mean': pytest.approx(200)}
    assert s['axis_wcs'] == [[0, pytest.approx(100), 0.0], [pytest.approx(5000), pytest.approx(100), 0.0]]
    assert s['structural_role'] == 'unknown'
    assert not s['physical_wall_verified'] and s['openings_checked']
    assert s['source_candidate_ids'] == [c['id'] for c in report['candidates'] if c['handles'][0] in ('A', 'B')]
    assert not seg['physical_walls_assembled'] and not report['structural_design_ready']
    generic = pairs(items)
    assert generic['pair_count'] == 2  # the kernel itself has no naming rules


def test_wall_segments_not_requested_keeps_previous_report():
    items = [line('A', [0, 0], [5000, 0]), line('B', [0, 200], [5000, 200])]
    plain = build_architectural_report(snapshot(items))
    assert plain['wall_segment_candidates'] == {
        'requested': False, 'segments': [], 'segment_count': 0, 'physical_walls_assembled': False,
        'interpretation': 'Not requested; pass wall_thickness_range to pair wall faces.'}
    paired = walls(items)
    for key in ('candidates', 'wall_line_diagnostics', 'wall_networks', 'boundary_checks'):
        assert paired[key] == plain[key]
    with pytest.raises(ValueError, match='wall_thickness_range'):
        build_architectural_report(snapshot(items), wall_thickness_range=[300, 100])


def test_ambiguous_wall_face_raises_issue():
    items = [line('A', [0, 0], [5000, 0]), line('B', [0, 200], [5000, 200]),
             line('C', [0, -150], [5000, -150])]
    issues = [i for i in walls(items)['issues'] if i['code'] == 'wall_segment_ambiguous_face']
    assert len(issues) == 2 and all(i['handles'] == ['A'] for i in issues)


def test_native_mcp_passes_pairing_parameters():
    async def exercise():
        async with Client(server.mcp) as client:
            await client.call_tool('analyze_geometry', {'parallel_separation_range': [1, 2],
                                                        'parallel_angle_tolerance_degrees': 0.5})
            await client.call_tool('analyze_architectural_drawing', {'wall_thickness_range': [100, 300]})

    with patch.object(server.understanding_geometry, 'analyze_geometry', return_value={'ok': True}) as geo, \
            patch.object(server.understanding_architecture, 'analyze_architectural_drawing',
                         return_value={'ok': True}) as arch:
        asyncio.run(exercise())
    assert geo.call_args.kwargs['parallel_separation_range'] == [1, 2]
    assert geo.call_args.kwargs['parallel_angle_tolerance_degrees'] == 0.5
    assert arch.call_args.kwargs['wall_thickness_range'] == [100, 300]
