"""Default locations for files the MCP server writes on its own.

MCP clients often start the server with an unrelated working directory (for
example C:\\Windows), so defaults are resolved from CAD_MCP_WORKSPACE_ROOT and
fall back to per-user locations instead of the process working directory.
"""
import os
import tempfile
from pathlib import Path


def workspace_root() -> Path:
    configured = os.environ.get("CAD_MCP_WORKSPACE_ROOT") or os.getcwd()
    return Path(configured).resolve()


def _candidate_dirs(name: str):
    yield workspace_root() / ".cad_mcp" / name
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        yield Path(local_app_data) / "best-cad-mcp" / name
    yield Path(tempfile.gettempdir()) / "best-cad-mcp" / name


def default_output_dir(name: str) -> Path:
    """Return a created, writable directory for server-generated artifacts."""
    errors = []
    for candidate in _candidate_dirs(name):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".write_probe_{os.getpid()}"
            probe.write_bytes(b"")
            probe.unlink()
            return candidate
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
    raise OSError("No writable output directory for " + repr(name) + ": " + "; ".join(errors))
