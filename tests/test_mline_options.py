from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import cad_controller
from src.cad_controller import CADController
from src.cad_tools import drawing_tools


@pytest.fixture
def setup(monkeypatch):
    entity = SimpleNamespace(Handle='ABC', Layer='TEST', MLineScale=1., Justification=1,
                             StyleName='STANDARD', Delete=Mock())
    add = Mock(return_value=entity)
    doc = SimpleNamespace(ModelSpace=SimpleNamespace(AddMLine=add))
    ctrl = object.__new__(CADController)
    ctrl.acad = SimpleNamespace(Documents=SimpleNamespace(Count=1), ActiveDocument=doc)
    ctrl.doc = doc
    monkeypatch.setattr(CADController, '_ensure_connected', lambda self: None)
    monkeypatch.setattr(cad_controller, 'to_variant_array', lambda x: x)
    monkeypatch.setattr(cad_controller, 'com_set', setattr)
    return ctrl, entity, add


@pytest.mark.parametrize('just,value', [('top', 0), ('zero', 1), ('bottom', 2)])
def test_explicit_properties(setup, just, value):
    ctrl, entity, add = setup
    assert ctrl.add_mline([(0, 0), (10, 0)], scale=8, justification=just) is entity
    assert entity.MLineScale == 8 and entity.Justification == value
    add.assert_called_once_with([0., 0., 0., 10., 0., 0.])
    entity.Delete.assert_not_called()


def test_omitted_options_preserve_com_defaults(setup):
    ctrl, entity, _ = setup
    ctrl.add_mline([(0, 0), (10, 0)])
    assert entity.MLineScale == 1 and entity.Justification == 1


@pytest.mark.parametrize('kwargs', [{'scale': 0}, {'scale': -1}, {'scale': float('nan')},
                                   {'scale': True}, {'justification': 'center'}])
def test_reject_before_creation(setup, kwargs):
    ctrl, _, add = setup
    with pytest.raises(ValueError):
        ctrl.add_mline([(0, 0), (10, 0)], **kwargs)
    add.assert_not_called()


@pytest.mark.parametrize('cleanup_failure', [False, True])
def test_com_failure_cleanup_is_explicit(setup, monkeypatch, cleanup_failure):
    ctrl, entity, _ = setup
    monkeypatch.setattr(cad_controller, 'com_set', Mock(side_effect=RuntimeError('COM rejected')))
    if cleanup_failure:
        entity.Delete.side_effect = RuntimeError('busy')
    with pytest.raises(RuntimeError, match='ABC remains' if cleanup_failure else 'new entity removed'):
        ctrl.add_mline([(0, 0), (10, 0)], scale=8)
    entity.Delete.assert_called_once()


def test_silently_ignored_setting_is_not_success(setup, monkeypatch):
    ctrl, entity, _ = setup
    monkeypatch.setattr(cad_controller, 'com_set', lambda *args: None)
    with pytest.raises(RuntimeError, match='new entity removed'):
        ctrl.add_mline([(0, 0), (10, 0)], scale=8)
    entity.Delete.assert_called_once()


@pytest.mark.parametrize('points', [[0, 0, 10, 0, 1], [0, 0, 0, 0], [0, 0, float('inf'), 0]])
def test_invalid_points_do_not_change_layer(monkeypatch, points):
    ctrl = Mock()
    monkeypatch.setattr(drawing_tools, 'ctrl', ctrl)
    assert drawing_tools.draw_mline(points, layer='NEW').startswith('Error:')
    assert not ctrl.mock_calls


def test_tool_forwards_and_caches_actual_properties(setup, monkeypatch):
    ctrl, _, _ = setup
    database = Mock()
    monkeypatch.setattr(drawing_tools, 'ctrl', ctrl)
    monkeypatch.setattr(drawing_tools, 'db', database)
    drawing_tools.draw_mline([0, 0, 10, 0], scale=8, justification='top')
    geometry = database.upsert_entity.call_args.kwargs['geometry']
    assert geometry['mline_scale'] == 8 and geometry['mline_justification'] == 0
