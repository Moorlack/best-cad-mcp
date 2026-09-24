from copy import deepcopy

from src.cad_understanding.architecture import build_architectural_report


def line(h, a, b, layer='A-WALL'):
    return {'handle': h, 'entity_type': 'AcDbLine', 'layer': layer,
            'geometry': {'start': a, 'end': b}}


def report(items, path='a.dwg', truncated=False, tolerance=None):
    return build_architectural_report({'schema_version': 'cad-ir/v2', 'drawing': {'path': path},
                                      'sections': {'entities': {'items': items, 'truncated': truncated}}},
                                     wall_gap_tolerance=tolerance)['wall_networks']


def test_transitive_groups_gap_links_and_isolated_lines():
    items = [line('A', [0, 0], [10, 0]), line('B', [10, 0], [20, 0]),
             line('C', [15, -5], [15, 5]), line('D', [20.25, 0], [30, 0]),
             line('E', [0, 0, 5], [10, 0, 5])]
    before = deepcopy(items)
    r = report(items, tolerance=.5)
    assert [g['handles'] for g in r['groups']] == [['A', 'B', 'C'], ['D'], ['E']]
    assert r['groups'][0]['relation_counts'] == {'endpoint_joint': 1, 'intersection': 1}
    assert r['groups'][0]['bbox_wcs'] == {'min': [0, -5, 0], 'max': [20, 5, 0]}
    assert r['groups'][1]['kind'] == 'isolated_line'
    assert r['coverage_complete'] and r['included_lines'] == 5
    assert len(r['gap_links']) == 1
    assert r['gap_links'][0]['network_ids'] == [r['groups'][0]['id'], r['groups'][1]['id']]
    assert not r['gap_links'][0]['within_same_network']
    assert not r['gaps_joined'] and not r['physical_walls_assembled']
    assert items == before
    assert report(list(reversed(items)), tolerance=.5) == r
    assert report(items)['groups'] == r['groups']
    assert report(items, path='b.dwg')['groups'][0]['id'] != r['groups'][0]['id']


def test_duplicates_overlap_t_junction_and_cross_layer_evidence():
    r = report([line('A', [0, 0], [10, 0]), line('B', [10, 0], [0, 0]),
                line('C', [5, 0], [15, 0]), line('D', [7, 0], [7, 5], 'OTHER-WALL')])
    assert r['group_count'] == 1
    g = r['groups'][0]
    assert g['handles'] == ['A', 'B', 'C', 'D']
    assert g['layers'] == ['A-WALL', 'OTHER-WALL']
    assert g['relation_counts'] == {'duplicate': 1, 'overlap': 2, 't_junction': 3}
    assert g['structural_role'] == 'unknown' and g['requires_architectural_review']


def test_exclusions_truncation_and_limits_are_not_complete_networks():
    items = [line('A', [0, 0], [10, 0]), line('B', [10, 0], [20, 0], 'WALL-DOOR')]
    r = report(items)
    assert r['included_lines'] == 1 and not r['coverage_complete']
    assert not r['groups'][0]['coverage_complete']
    assert r['excluded'][0]['handle'] == 'B'
    assert not report(items[:1], truncated=True)['coverage_complete']
    r = report([line(str(i), [i, 0], [i+1, 0]) for i in range(101)])
    assert r['included_lines'] == 100 and not r['coverage_complete']
    assert len(r['excluded']) == 1


def test_unverified_pairs_preserved_without_joining():
    r = report([line('A', [0, 0], [1e9, 0]), line('B', [1, 0], [2, 0])])
    assert r['unverified_pairs'] == [['A', 'B']]
    assert r['group_count'] == 2 and not r['coverage_complete']


def test_empty_and_unlabelled_do_not_invent_walls():
    assert report([])['groups'] == []
    assert report([line('A', [0, 0], [10, 0], '0')])['groups'] == []
