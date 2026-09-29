from pathlib import Path

import pytest

from src import workspace_paths
from src.cad_tools import file_tools
from src.cad_understanding import view_grounding


def test_output_dir_uses_workspace_root_not_cwd(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    unrelated_cwd = tmp_path / "client_cwd"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.setenv("CAD_MCP_WORKSPACE_ROOT", str(workspace))

    out = workspace_paths.default_output_dir("cad_visual_exports")

    assert out == (workspace / ".cad_mcp" / "cad_visual_exports").resolve()
    assert out.is_dir()
    assert not (unrelated_cwd / "cad_visual_exports").exists()
    assert list(out.iterdir()) == []


def test_output_dir_falls_back_to_local_app_data(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file, not a directory")
    local = tmp_path / "local"
    monkeypatch.setenv("CAD_MCP_WORKSPACE_ROOT", str(blocked))
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    out = workspace_paths.default_output_dir("cad_image_traces")

    assert out == local / "best-cad-mcp" / "cad_image_traces"
    assert out.is_dir()


def test_output_dir_reports_all_failed_candidates(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("x")
    monkeypatch.setenv("CAD_MCP_WORKSPACE_ROOT", str(blocked))
    monkeypatch.setenv("LOCALAPPDATA", str(blocked))
    monkeypatch.setattr(workspace_paths.tempfile, "gettempdir", lambda: str(blocked))

    with pytest.raises(OSError, match="cad_visual_exports"):
        workspace_paths.default_output_dir("cad_visual_exports")


def test_database_workspace_root_matches_output_root(tmp_path, monkeypatch):
    from src import cad_database

    monkeypatch.setenv("CAD_MCP_WORKSPACE_ROOT", str(tmp_path))
    assert Path(cad_database._get_default_workspace_root()) == tmp_path.resolve()


def test_export_view_image_default_path_is_under_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    client_cwd = tmp_path / "client_cwd"
    client_cwd.mkdir()
    monkeypatch.chdir(client_cwd)
    monkeypatch.setenv("CAD_MCP_WORKSPACE_ROOT", str(workspace))
    paths = []
    monkeypatch.setattr(file_tools, "export_image", lambda filepath: paths.append(filepath) or "OK")

    file_tools.export_view_image()

    assert len(paths) == 1
    exported = Path(paths[0])
    assert exported.parent == (workspace / ".cad_mcp" / "cad_visual_exports").resolve()
    assert exported.suffix == ".wmf"
    assert not (client_cwd / "cad_visual_exports").exists()


def test_mapped_export_default_path_is_under_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    client_cwd = tmp_path / "client_cwd"
    client_cwd.mkdir()
    monkeypatch.chdir(client_cwd)
    monkeypatch.setenv("CAD_MCP_WORKSPACE_ROOT", str(workspace))
    seen = []

    def fake_export(filepath=None, zoom_extents_first=False):
        seen.append(filepath)
        return "ERROR: no document"

    monkeypatch.setattr(file_tools, "export_view_image", fake_export)
    monkeypatch.setattr(file_tools, "ctrl", type("Ctrl", (), {"has_document": True})())

    view_grounding.export_view_image_with_mapping(include_overlay=False)

    assert seen, "export was not attempted"
    assert Path(seen[0]).parent == (workspace / ".cad_mcp" / "cad_visual_exports").resolve()
    assert not (client_cwd / "cad_visual_exports").exists()
