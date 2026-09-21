import asyncio
import json
from pathlib import Path

import pytest

from src import visual_selftest


def test_missing_pillow_is_reported(monkeypatch):
    monkeypatch.setattr(visual_selftest.vision, "_pillow", lambda: None)
    result = visual_selftest.check_visual_pipeline()
    assert not result["ok"]
    assert result["data"]["checks"][-1]["name"] == "pillow"


def test_missing_fixture_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(visual_selftest.vision, "_pillow", lambda: object())
    monkeypatch.setattr(visual_selftest, "FIXTURE", tmp_path / "missing.wmf")
    assert visual_selftest.check_visual_pipeline()["data"]["checks"][-1]["name"] == "fixture"


@pytest.mark.parametrize("failure", ["missing", "blank", "corrupt", "exception", "none"])
def test_actual_image_validation_and_cleanup(monkeypatch, failure):
    pil = pytest.importorskip("PIL.Image")
    used_paths = []

    def convert(source):
        used_paths.append(Path(source))
        if failure == "exception":
            raise RuntimeError("renderer failed")
        if failure == "missing":
            return None
        output = Path(source).with_suffix(".png")
        if failure == "corrupt":
            output.write_bytes(b"not an image")
        else:
            with pil.new("RGB", (1024, 512), "white") as image:
                if failure != "blank":
                    image.paste("black", (100, 100, 300, 300))
                image.save(output)
        return output

    monkeypatch.setattr(visual_selftest.vision, "_try_convert_wmf_to_raster", convert)
    result = visual_selftest.check_visual_pipeline()
    assert result["ok"] == (failure == "none")
    assert used_paths and all(not path.parent.exists() for path in used_paths)
    if result["ok"]:
        assert len(result["data"]["checks"]) == 3
        assert not result["data"]["live_autocad_export_tested"]
        assert not result["data"]["client_image_display_tested"]


def test_cli_returns_failure_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(visual_selftest.vision, "_pillow", lambda: None)
    assert visual_selftest.main(["--json"]) == 1
    assert not json.loads(capsys.readouterr().out)["ok"]


def test_native_mcp_exposes_check(monkeypatch):
    from mcp import Client
    from src import server
    expected = {"ok": True, "message": "test", "data": {"checks": []}}
    monkeypatch.setattr(server, "run_visual_pipeline_check", lambda: expected)

    async def run():
        async with Client(server.mcp, raise_exceptions=True) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert tools["check_visual_pipeline"].annotations.read_only_hint
            result = await client.call_tool("check_visual_pipeline", {})
            assert result.structured_content["result"] == expected
    asyncio.run(run())
