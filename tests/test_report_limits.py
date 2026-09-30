import pytest

from src.cad_understanding.report_limits import (
    ARCHITECTURE_LIST_PATHS, limit_lists, validate_max_list_items)


def test_limit_lists_trims_nested_lists_and_records_totals():
    report = {"candidates": list(range(500)), "wall_segment_candidates": {"junctions": {"junctions": list(range(30))}},
              "issues": [1, 2]}
    trimmed = limit_lists(report, ARCHITECTURE_LIST_PATHS, 100)
    assert len(report["candidates"]) == 100 and report["candidates"][-1] == 99
    assert len(report["wall_segment_candidates"]["junctions"]["junctions"]) == 30  # under the limit
    assert trimmed == {"candidates": {"total": 500, "returned": 100}}
    assert report["truncated_lists"] == trimmed
    assert limit_lists({"candidates": list(range(500))}, ARCHITECTURE_LIST_PATHS, None) == {}


def test_validate_max_list_items():
    validate_max_list_items(None)
    validate_max_list_items(1)
    for bad in (0, -5, True, "200", 2.5, 100001):
        with pytest.raises(ValueError):
            validate_max_list_items(bad)


def test_plan_sized_report_is_trimmed_by_the_tool_and_keeps_counts(monkeypatch):
    from src.cad_understanding import architecture

    items = []
    for i in range(500):
        x, y = (i % 25) * 120.0, (i // 25) * 60.0
        for k, yy in enumerate((y, y + 8)):
            items.append({"handle": f"{i:04d}{k}", "entity_type": "AcDbLine", "layer": "A-WALL",
                          "geometry": {"start": [x, yy, 0], "end": [x + 100, yy, 0]}})
    ir = {"schema_version": "cad-ir/v2", "drawing": {"path": "big.dwg", "units": "mm"},
          "sections": {"entities": {"total": len(items), "items": items}}}
    monkeypatch.setattr("src.cad_understanding.architecture.build_drawing_ir", lambda **kwargs: ir)
    monkeypatch.setattr("src.cad_understanding.architecture.check_snapshot_freshness",
                        lambda database=None: {"status": "unverified", "reason": None, "scan": None, "live": None,
                                               "checked_at": "", "limitations": []}, raising=False)
    result = architecture.analyze_architectural_drawing(wall_thickness_range=[4, 12], max_list_items=50)
    assert result["ok"]
    report = result["data"]["report"]
    assert len(report["candidates"]) == 50 and report["summary"]["candidate_count"] == 1000
    assert report["truncated_lists"]["candidates"] == {"total": 1000, "returned": 50}
    assert report["wall_segment_candidates"]["segment_count"] == 500 and len(report["wall_segment_candidates"]["segments"]) == 50
    assert "report_lists_truncated" in result["warnings"] and len(result["handles"]) == 50
    full = architecture.analyze_architectural_drawing(wall_thickness_range=[4, 12], max_list_items=None)
    assert len(full["data"]["report"]["candidates"]) == 1000 and "truncated_lists" not in full["data"]["report"]
    assert architecture.analyze_architectural_drawing(max_list_items=0)["ok"] is False
