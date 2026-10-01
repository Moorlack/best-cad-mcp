import asyncio
from unittest.mock import patch

import pytest
from mcp import Client

from src import server
from src.cad_understanding.architecture import build_architectural_report, plan_summary_result
from src.cad_understanding.plan_summary import build_plan_summary
from tests.test_thickness_estimate import plan


def test_summary_digests_walls_gaps_and_loops():
    report = build_architectural_report(plan(), wall_thickness_range="auto", wall_opening_max_width="auto")
    summary = build_plan_summary(report)
    assert summary["walls"]["segments"] == 6 and summary["walls"]["thickness_estimated"] is True
    assert summary["openings"]["wall_gaps"] == 1 and summary["openings"]["gaps_without_symbol"] == 1
    assert summary["enclosed_areas"]["count"] == 2
    largest = summary["enclosed_areas"]["largest"]
    assert largest[0]["net_area"] >= largest[1]["net_area"] and largest[0]["through_opening"] is True
    assert summary["main_issues"]["wall_gap_without_opening_candidate"] == 1
    assert summary["verified"] is False
    text = summary["text"]
    assert "6 paired segments" in text and "typical thickness 200 (estimated)" in text
    assert "2 loops" in text and "not verified" in text


def test_summary_without_walls_and_collapsed_issue_counts():
    report = {"drawing": {"name": "a.dwg", "units": "mm"}, "issues": [
        {"code": "x", "handles": []}, {"code": "x", "handles": [], "omitted_count": 4}]}
    summary = build_plan_summary(report)
    assert summary["main_issues"] == {"x": 5}
    assert summary["walls"]["segments"] == 0 and summary["enclosed_areas"]["largest"] == []
    assert "walls not paired" in summary["text"]


def test_plan_summary_result_keeps_only_the_summary():
    result = {"ok": True, "warnings": ["a", "report_lists_truncated"],
              "data": {"report": {"plan_summary": {"text": "first\nsecond"}, "candidates": [1]}}}
    out = plan_summary_result(result, "scanned")
    assert out["ok"] and out["message"] == "first" and out["warnings"] == ["a"]
    assert out["data"] == {"plan_summary": {"text": "first\nsecond"}, "scan_message": "scanned"}
    failed = plan_summary_result({"ok": False, "message": "bad"}, "scanned")
    assert failed["ok"] is False and failed["data"]["scan_message"] == "scanned"


@pytest.mark.parametrize("scan", [True, False])
def test_native_mcp_summarize_plan_scans_then_analyzes(scan):
    async def exercise():
        async with Client(server.mcp, raise_exceptions=True, mode="2026-07-28") as client:
            return await client.call_tool("summarize_architectural_plan",
                                          {"scan": scan, "architectural_layers_only": True, "max_entities": 800})

    analysis = {"ok": True, "warnings": [], "data": {"report": {"plan_summary": {"text": "digest"}}}}
    with patch.object(server.query_tools, "scan_all_entities", return_value="scanned") as scan_fn, \
         patch.object(server.understanding_architecture, "analyze_architectural_drawing",
                      return_value=analysis) as analyze:
        result = asyncio.run(exercise()).model_dump(by_alias=True, mode="json")
    assert not result.get("isError")
    if scan:
        scan_fn.assert_called_once_with(max_entities=800, layers=None, architectural_layers_only=True,
                                        max_seconds=30.0, fast=True)
    else:
        scan_fn.assert_not_called()
    analyze.assert_called_once_with(entity_limit=800, wall_thickness_range="auto", wall_opening_max_width="auto",
                                    name_aliases=None, max_list_items=1, max_response_chars=None)
    data = result["structuredContent"]["result"]["data"]
    assert data["plan_summary"]["text"] == "digest" and data["scan_message"] == ("scanned" if scan else None)
