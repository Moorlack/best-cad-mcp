"""Exercise the architectural report through the native MCP client, without CAD."""

import asyncio
from unittest.mock import patch

import pytest
from mcp import Client

from src import server


@pytest.mark.parametrize("profile", ["lean", "core", "full"])
def test_architecture_is_enabled_in_every_profile(monkeypatch, profile):
    monkeypatch.setenv("CAD_MCP_TOOL_PROFILE", profile)
    monkeypatch.delenv("CAD_MCP_TOOLS_EXCLUDE", raising=False)
    assert server._tool_enabled("analyze_architectural_drawing")


def test_native_mcp_architectural_report_and_readonly_annotations():
    snapshot = {
        "schema_version": "cad-ir/v2", "drawing": {"path": "test.dwg", "units": "unknown"},
        "sections": {"entities": {"total": 1, "items": [{
            "handle": "A1", "layer": "A-WALL", "entity_type": "AcDbLine", "object_name": "Line",
            "geometry": {"start_point": [0, 0, 0], "end_point": [10, 0, 0]},
        }]}},
    }

    async def exercise():
        async with Client(server.mcp, raise_exceptions=True, mode="2026-07-28") as client:
            tools = await client.list_tools()
            tool = next(t for t in tools.tools if t.name == "analyze_architectural_drawing")
            wire = tool.model_dump(by_alias=True, mode="json")
            assert wire["annotations"]["readOnlyHint"] is True
            assert wire["annotations"]["destructiveHint"] is False
            assert "project_id" in wire["inputSchema"]["properties"]
            assert "project_id" not in wire["inputSchema"].get("required", [])
            assert "reference_lengths" in wire["inputSchema"]["properties"]
            result = await client.call_tool("analyze_architectural_drawing", {"entity_limit": 42,
                "reference_lengths": [{"handle": "A1", "length": 10, "units": "in", "source": "test"}]})
            return result.model_dump(by_alias=True, mode="json")

    with patch.object(server.understanding_architecture, "build_drawing_ir", return_value=snapshot) as build:
        result = asyncio.run(exercise())
    build.assert_called_once_with(database=None, rescan=False, sections=["entities", "blocks", "quality"],
                                  entity_limit=42, include_raw=True)
    assert not result.get("isError")
    report = result["structuredContent"]["result"]["data"]["report"]
    assert report["candidates"][0]["handles"] == ["A1"]
    assert report["candidates"][0]["category"] == "wall"
    assert report["structural_design_ready"] is False
    assert report["scale_reference_check"]["checks"][0]["reason"] == "drawing_units_unknown_or_unsupported"


def test_native_mcp_passes_explicit_project_id():
    async def exercise():
        async with Client(server.mcp, raise_exceptions=True, mode="2026-07-28") as client:
            return await client.call_tool("analyze_architectural_drawing", {"project_id": "native-test",
                                                                          "wall_gap_tolerance": 0.25})

    with patch.object(server.understanding_architecture, "analyze_architectural_drawing",
                      return_value={"ok": True}) as analyze:
        asyncio.run(exercise())
    analyze.assert_called_once_with(entity_limit=10000, project_id="native-test", reference_lengths=None,
                                    wall_gap_tolerance=0.25)
