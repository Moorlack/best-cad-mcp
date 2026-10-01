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
    result = architecture.analyze_architectural_drawing(wall_thickness_range=[4, 12], max_list_items=50,
                                                      max_response_chars=None)
    assert result["ok"]
    report = result["data"]["report"]
    assert len(report["candidates"]) == 50 and report["summary"]["candidate_count"] == 1000
    assert report["truncated_lists"]["candidates"] == {"total": 1000, "returned": 50}
    assert report["wall_segment_candidates"]["segment_count"] == 500 and len(report["wall_segment_candidates"]["segments"]) == 50
    assert "report_lists_truncated" in result["warnings"] and len(result["handles"]) == 50
    full = architecture.analyze_architectural_drawing(wall_thickness_range=[4, 12], max_list_items=None,
                                                   max_response_chars=None)
    assert len(full["data"]["report"]["candidates"]) == 1000 and "truncated_lists" not in full["data"]["report"]
    assert architecture.analyze_architectural_drawing(max_list_items=0)["ok"] is False


def test_fit_report_halves_the_list_limit_until_the_response_fits_and_collapses_issues():
    import json

    from src.cad_understanding.report_limits import fit_report

    report = {"candidates": [{"id": i, "pad": "x" * 200} for i in range(400)],
              "issues": [{"code": "wall_gap", "handles": [], "message": "gap"} for _ in range(300)]
                        + [{"code": "units", "handles": [], "message": "u"}]}
    paths = ("candidates",)
    trimmed = fit_report(report, paths, 200, 20000)
    assert len(json.dumps(report)) <= 20000 + 200  # response_chars is added after measuring
    assert 3 <= len(report["candidates"]) < 200
    assert trimmed["candidates"]["total"] == 400
    assert trimmed["issues.wall_gap"] == {"total": 300, "returned": 5}
    codes = [i["code"] for i in report["issues"]]
    assert codes.count("wall_gap") == 6 and codes.count("units") == 1  # 5 kept + one omitted-count entry
    assert [i for i in report["issues"] if i.get("omitted_count")][0]["omitted_count"] == 295
    assert report["truncated_lists"]["response_chars"] <= 20000
    small = {"candidates": [1, 2, 3], "issues": []}
    assert fit_report(small, paths, 200, 60000) == {} and "truncated_lists" not in small
    unlimited = {"candidates": list(range(500)), "issues": []}
    assert fit_report(unlimited, paths, None, None) == {} and len(unlimited["candidates"]) == 500


def test_validate_max_response_chars():
    from src.cad_understanding.report_limits import validate_max_response_chars

    validate_max_response_chars(None)
    validate_max_response_chars(60000)
    for bad in (0, 1999, True, "60000", 10_000_001):
        with pytest.raises(ValueError):
            validate_max_response_chars(bad)


def test_fit_report_also_trims_long_nested_id_lists_when_still_too_big():
    import json

    from src.cad_understanding.report_limits import fit_report

    report = {"wall_segment_candidates": {"runs": [{"id": "r1", "segment_ids": [f"s{i:05d}" for i in range(5000)]}],
                                          "openings": {"gaps_without_opening_candidate": [f"g{i:05d}" for i in range(5000)]}},
              "issues": []}
    trimmed = fit_report(report, ("wall_segment_candidates.runs",), 200, 20000)
    assert len(json.dumps(report)) < 21000
    assert len(report["wall_segment_candidates"]["runs"][0]["segment_ids"]) <= 200
    assert trimmed["wall_segment_candidates.runs[].segment_ids"]["total"] == 5000
    assert trimmed["wall_segment_candidates.openings.gaps_without_opening_candidate"]["nested"] is True


def test_nested_trimming_keeps_polygons_issues_and_limitations():
    from src.cad_understanding.report_limits import fit_report

    polygon = [[float(i), float(i * 2)] for i in range(400)]
    report = {"wall_segment_candidates": {"room_loops": {"loops": [
        {"polygon_wcs": polygon, "segment_ids": [f"s{i}" for i in range(400)]}]}},
        "issues": [{"code": f"c{i}", "handles": []} for i in range(40)],
        "limitations": [f"limit {i}" for i in range(40)]}
    fit_report(report, (), 200, 4000)
    loop = report["wall_segment_candidates"]["room_loops"]["loops"][0]
    assert loop["polygon_wcs"] == polygon and len(loop["segment_ids"]) < 400
    assert len(report["limitations"]) == 40 and len(report["issues"]) == 40
