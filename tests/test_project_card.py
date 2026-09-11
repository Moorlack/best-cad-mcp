import pytest

from src.cad_database import CADDatabase
from src.cad_understanding.project_card import get_project_card, get_project_card_history, update_project_card


@pytest.fixture
def db(tmp_path):
    result = CADDatabase(str(tmp_path / 'card.db'))
    result.configure_context(workspace_root=str(tmp_path), drawing_name='a.dwg')
    return result


def field(value, status='confirmed'):
    return {'value': value, 'status': status, 'source': 'Engineer supplied project brief'}


def test_persistence_merge_history_conflict_and_drawing_independence(db):
    assert not get_project_card('p1', db)['ok']
    result = update_project_card('p1', {'city': field('New York')}, 0, 'initial brief', db)
    assert result['ok']
    assert not result['data']['readiness']['engineering_design_ready']
    assert 'address' in result['data']['readiness']['gates']['code_selection']['missing']
    assert update_project_card('p1', {'state': field('NY')}, 1, 'state added', db)['ok']
    assert not update_project_card('p1', {'city': field('Other')}, 1, 'stale edit', db)['ok']
    db.configure_context(drawing_name='b.dwg', thread_id='other-thread')
    card = get_project_card('p1', db)['data']['card']
    assert card['revision'] == 2 and card['fields']['city']['value'] == 'New York'
    history = get_project_card_history('p1', database=db)['data']['revisions']
    assert len(history) == 2
    assert 'state' not in history[1]['fields']
    assert history[0]['change_reason'] == 'state added'
    reopened = CADDatabase(db.db_path)
    reopened.configure_context(workspace_root=db.get_context().workspace_root)
    assert get_project_card('p1', reopened)['data']['card'] == card


def test_workspace_and_project_isolation(db, tmp_path):
    update_project_card('p1', {'city': field('A')}, 0, 'create', db)
    assert not get_project_card('p2', db)['ok']
    db.configure_context(workspace_root=str(tmp_path / 'other'))
    assert not get_project_card('p1', db)['ok']
    assert get_project_card_history('p1', database=db)['data']['revisions'] == []


@pytest.mark.parametrize('fields', [
    {'unknown_field': field('x')}, {'city': {'value': 'NY', 'status': 'confirmed'}},
    {'story_count': field(True)}, {'story_heights': field([float('nan')])},
    {'units': field('feet')}, {'city': field('NY', 'missing')},
    {'risk_category': field('V')}, {'code_basis': field([{'document': 'IBC'}])},
    {'city': field('   ')}, {'city': field('NY', 'guessed')},
])
def test_invalid_inputs_do_not_create_revision(db, fields):
    assert not update_project_card('p1', fields, 0, 'invalid', db)['ok']
    assert not get_project_card('p1', db)['ok']


def test_assumptions_conflicts_and_units_change(db):
    inputs = {'story_count': field(2), 'story_heights': field([3]),
              'units': field('m'), 'coordinate_system': field('WCS', 'assumed')}
    result = update_project_card('p1', inputs, 0, 'initial', db)
    gates = result['data']['readiness']['gates']
    assert gates['geometry_review']['conflicts'] == ['story_count_and_heights_disagree']
    assert gates['geometry_review']['assumed'] == ['coordinate_system']
    assert gates['code_selection']['conflicts'] == []
    assert not update_project_card('p1', {'units': field('ft')}, 1, 'change units', db)['ok']
    result = update_project_card('p1', {'story_heights': field([3, 3]),
                                      'coordinate_system': field('WCS')}, 1, 'confirmed', db)
    assert result['data']['readiness']['gates']['geometry_review']['inputs_confirmed']
    result = update_project_card('p1', {'units': {'value': None, 'status': 'missing'},
                                      'story_heights': {'value': None, 'status': 'missing'}},
                                 2, 'withdraw incorrect information', db)
    assert 'units' in result['data']['readiness']['gates']['geometry_review']['missing']


def test_code_basis_retains_exact_applicability_and_source(db):
    basis = [{'document': 'Example standard', 'edition': 'test-only', 'jurisdiction': 'Example city',
              'applicability': 'Synthetic fixture; not governing law', 'reference': 'Engineer test brief section 1'}]
    assert update_project_card('p1', {'code_basis': field(basis)}, 0, 'test basis', db)['ok']
    assert get_project_card('p1', db)['data']['card']['fields']['code_basis']['value'] == basis


def test_mcp_card_tools_roundtrip_and_annotations(db):
    import asyncio
    from unittest.mock import patch
    from mcp import Client
    from src import server

    async def run():
        async with Client(server.mcp, raise_exceptions=True) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert not tools['update_project_card'].annotations.read_only_hint
            assert tools['get_project_card'].annotations.read_only_hint
            result = await client.call_tool('update_project_card', {
                'project_id': 'test', 'fields': {'city': field('Test city')},
                'expected_revision': 0, 'change_reason': 'MCP test'})
            assert not result.is_error
            result = await client.call_tool('get_project_card', {'project_id': 'test'})
            assert result.structured_content['result']['data']['card']['fields']['city']['value'] == 'Test city'
    with patch('src.cad_understanding.project_card.get_db', return_value=db):
        asyncio.run(run())
