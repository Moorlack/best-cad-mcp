import asyncio
from unittest.mock import patch

from mcp import Client

from src import server


def call(tool, arguments):
    async def exercise():
        async with Client(server.mcp, raise_exceptions=True, mode="2026-07-28") as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            result = await client.call_tool(tool, arguments)
            return tools[tool].model_dump(by_alias=True, mode="json"), result.model_dump(by_alias=True, mode="json")
    return asyncio.run(exercise())


def test_all_digit_handles_sent_as_numbers_reach_string_parameters():
    with patch.object(server.query_tools, "viewport_filter", return_value=(None, None)) as vf, \
         patch.object(server.understanding_architecture, "analyze_architectural_drawing", return_value={"ok": True}):
        tool, result = call("analyze_architectural_drawing", {"viewport_handle": 27128})
    assert not result.get("isError")
    vf.assert_called_once_with("27128")
    schema = tool["inputSchema"]["properties"]["viewport_handle"]
    assert "integer" not in str(schema) and "string" in str(schema)


def test_string_lists_and_plain_strings_accept_numbers_too():
    with patch.object(server.query_tools, "scan_all_entities", return_value="ok") as scan:
        _, result = call("scan_all_entities", {"layers": [101, "A-WALL"]})
    assert not result.get("isError")
    assert scan.call_args.kwargs["layers"] == ["101", "A-WALL"]
    assert server._lenient_annotation(bool) is bool
    assert server._lenient_annotation(server.Union[float, str]) == server.Union[float, str]
