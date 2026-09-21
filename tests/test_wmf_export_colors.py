from unittest.mock import MagicMock, call, patch

import pytest

from src.cad_controller import CADController


def controller():
    # Bypass the singleton constructor so the test cannot replace the live controller.
    result = object.__new__(CADController)
    result.doc = MagicMock()
    result.doc.GetVariable.return_value = 0
    result.doc.ModelSpace.Count = 0
    return result


@pytest.mark.parametrize('previous', [0, 1])
@pytest.mark.parametrize('failure', [None, 'export', 'wait', 'set'])
def test_export_preserves_colors_and_restores_on_failure(previous, failure, tmp_path):
    ctrl = controller()
    doc = ctrl.doc
    doc.GetVariable.return_value = previous
    state = {'background': previous}

    def set_variable(name, value):
        state['background'] = value
        if failure == 'set' and doc.SetVariable.call_count == 1:
            raise RuntimeError('setter failed after applying value')

    def export(*args):
        assert state['background'] == 1
        if failure == 'export':
            raise RuntimeError('export failed')

    doc.SetVariable.side_effect = set_variable
    doc.Export.side_effect = export
    with patch.object(ctrl, '_wait_for_export_file', side_effect=RuntimeError('wait failed') if failure == 'wait' else None):
        if failure:
            with pytest.raises(RuntimeError):
                ctrl._export_with_selection_set(str(tmp_path / 'sample.wmf'), 'WMF')
        else:
            ctrl._export_with_selection_set(str(tmp_path / 'sample.wmf'), 'WMF')
    assert state['background'] == previous
    assert doc.SetVariable.call_args_list == [call('WMFBKGND', 1), call('WMFBKGND', previous)]
    doc.SelectionSets.Add.return_value.Delete.assert_called_once()
    doc.Save.assert_not_called()


def test_restore_failure_is_visible_and_selection_is_cleaned(tmp_path):
    ctrl = controller()
    ctrl.doc.SetVariable.side_effect = [None, RuntimeError('disconnected')]
    with patch.object(ctrl, '_wait_for_export_file'):
        with pytest.raises(RuntimeError, match='could not restore WMFBKGND'):
            ctrl._export_with_selection_set(str(tmp_path / 'sample.wmf'), 'WMF')
    ctrl.doc.SelectionSets.Add.return_value.Delete.assert_called_once()


def test_unreadable_setting_stops_export(tmp_path):
    ctrl = controller()
    ctrl.doc.GetVariable.side_effect = RuntimeError('cannot read original setting')
    with pytest.raises(RuntimeError):
        ctrl._export_with_selection_set(str(tmp_path / 'sample.wmf'), 'WMF')
    ctrl.doc.Export.assert_not_called()
    ctrl.doc.SetVariable.assert_not_called()


def test_non_wmf_export_does_not_touch_wmf_settings(tmp_path):
    ctrl = controller()
    with patch.object(ctrl, '_wait_for_export_file'):
        ctrl._export_with_selection_set(str(tmp_path / 'sample.dxf'), 'DXF')
    ctrl.doc.GetVariable.assert_not_called()
    ctrl.doc.SetVariable.assert_not_called()
    ctrl.doc.Export.assert_called_once()
