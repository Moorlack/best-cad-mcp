"""Drawing-scoped contact components, never confirmed physical walls."""

import hashlib
from collections import Counter
from copy import deepcopy


def build_wall_networks(candidates, diagnostics):
    excluded = {item['handle'] for item in diagnostics['excluded']}
    nodes = {c['handles'][0]: c for c in candidates
             if c['category'] == 'wall' and c['handles'][0] not in excluded}
    adjacency = {h: set() for h in nodes}
    for edge in diagnostics['items']:
        a, b = edge['handles']
        adjacency[a].add(b)
        adjacency[b].add(a)
    remaining = set(nodes)
    groups, membership = [], {}
    complete = not (excluded or diagnostics['unverified_pairs']
                    or diagnostics['entity_coverage_truncated'])
    while remaining:
        pending, members = [min(remaining)], set()
        while pending:
            handle = pending.pop()
            if handle in members:
                continue
            members.add(handle)
            pending.extend(adjacency[handle] - members)
        remaining -= members
        handles = sorted(members)
        key = '\0'.join(sorted(nodes[h]['id'] for h in handles))
        group_id = 'wall_network_' + hashlib.sha256(key.encode()).hexdigest()[:20]
        membership.update({h: group_id for h in handles})
        edges = [deepcopy(e) for e in diagnostics['items'] if e['handles'][0] in members]
        points = []
        for h in handles:
            g = nodes[h]['geometry']
            for p in (g.get('start', g.get('start_point')), g.get('end', g.get('end_point'))):
                points.append(list(p) + ([0.0] if len(p) == 2 else []))
        groups.append({'id': group_id, 'handles': handles, 'source_candidate_ids': [nodes[h]['id'] for h in handles],
                       'status': 'candidate', 'kind': 'contact_network' if edges else 'isolated_line',
                       'layers': sorted({nodes[h]['layer'] for h in handles}),
                       'bbox_wcs': {'min': [min(p[k] for p in points) for k in range(3)],
                                    'max': [max(p[k] for p in points) for k in range(3)]},
                       'relations': edges, 'relation_counts': dict(sorted(Counter(e['relation'] for e in edges).items())),
                       'coverage_complete': complete, 'requires_architectural_review': True,
                       'structural_role': 'unknown'})
    links = []
    for gap in diagnostics['gap_search']['candidates']:
        a, b = gap['handles']
        links.append({**deepcopy(gap), 'network_ids': [membership[a], membership[b]],
                      'within_same_network': membership[a] == membership[b]})
    return {'scope': diagnostics['scope'], 'groups': groups, 'group_count': len(groups),
            'included_lines': len(nodes), 'coverage_complete': complete,
            'excluded': deepcopy(diagnostics['excluded']),
            'unverified_pairs': deepcopy(diagnostics['unverified_pairs']),
            'entity_coverage_truncated': diagnostics['entity_coverage_truncated'],
            'gap_links': links, 'gaps_joined': False, 'physical_walls_assembled': False,
            'interpretation': 'Connected source LINE groups under diagnostic tolerance; not physical walls, rooms or load paths.'}
