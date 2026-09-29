"""CAD Understanding Layer.

Pure-Python analysis, grounding, validation, and plan helpers that operate on
the scanned CAD metadata database. These modules intentionally avoid direct
AutoCAD COM access; any live drawing interaction goes through existing tools.
"""

__all__ = ["ok_result", "error_result"]


def __getattr__(name):
    # Pure geometry consumers do not need the MCP result typing dependency.
    if name in __all__:
        from . import result
        return getattr(result, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
