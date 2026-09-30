"""Experiment integrity and conservative grading; no live model/AutoCAD claims."""

import copy
import json

import pytest

from scripts import agent_benchmark as benchmark


@pytest.fixture
def experiment(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name in ("pyproject.toml", "server.json", "scripts/agent_benchmark.py", "fixture.dxf",
                 "src/tool.py", "prompts/review.md", ".agents/skills/cad/SKILL.md"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("frozen fixture", encoding="utf-8")
    suite = {
        "schema_version": benchmark.SCHEMA, "tool_profile": "core",
        "budget": {"max_repair_rounds": 2, "max_tool_calls": 100, "max_elapsed_seconds": 1200},
        "cases": [{"case_id": "move", "mode": "edit", "drawing": "fixture.dxf",
                   "prompt": "Move the complete component", "acceptance": {"translation": "Correct move"}}],
    }
    benchmark.write_json(root / "suite.json", suite)
    bundle = tmp_path / "bundle"
    benchmark.prepare(root / "suite.json", bundle, root=root)
    run = benchmark.read_json(bundle / "run-template.json")
    run.update(run_id="synthetic-test", model="test-model", vision_model="test-vision",
               execution_kind="synthetic", runtime={k: "fixture" for k in
               ("autocad", "python", "mcp", "renderer", "host", "dependencies_sha256")})
    run["runtime"]["tool_profile"] = "core"
    run_path = tmp_path / "run.json"
    benchmark.write_json(run_path, run)
    return root, bundle, run_path, run


def attach(root, name, data):
    path = root / name
    benchmark.write_json(path, data)
    return benchmark.receipt(path, root)


def complete(run_path, run):
    root = run_path.parent
    image = attach(root, "image.json", {"synthetic_image": True})
    scan = attach(root, "scan.json", {"synthetic_scan": True})
    # The ledger verifies integrity, not image encoding or claim truth.
    record = run["cases"][0]
    record.update(status="completed", repair_rounds=1, tool_calls=10, elapsed_seconds=50,
                  human_interventions=0)
    review = {"reviewer": "independent-fixture", "case_id": "move", "snapshot_id": "after",
              "checks": {"translation": True}, "edit_attempt_count": 1, "unintended_edit_count": 0}
    record["evidence"] = {
        "transcript": attach(root, "transcript.json", [{"synthetic_tool_call": True}]),
        "before": attach(root, "before.json", {"snapshot_id": "before", "drawing_id": "drawing",
                                                "image": image, "scan": scan}),
        "after": attach(root, "after.json", {"snapshot_id": "after", "drawing_id": "drawing",
                                              "image": image, "scan": scan}),
        "review": attach(root, "review.json", review),
        "grounding": attach(root, "grounding.json", {"ok": True, "data": {"metrics": {
            "exact_group_case_count": 1, "top1_exact_group_accuracy": 1.0}}}),
    }
    benchmark.write_json(run_path, run)
    return record, review


def summary(bundle, path):
    return benchmark.report(bundle, [path])["runs"][0]


def test_pending_is_unknown_not_perfect_or_failed(experiment):
    _, bundle, path, _ = experiment
    result = summary(bundle, path)
    assert result["acceptance_rate"] is None
    assert result["assessed_case_count"] == 0
    assert result["completion_rate"] == 0


def test_frozen_bytes_and_manifest_detect_tampering(experiment):
    _, bundle, path, _ = experiment
    (bundle / "frozen/fixture.dxf").write_text("changed")
    with pytest.raises(ValueError, match="Frozen input changed"):
        summary(bundle, path)


def test_matching_evidence_reports_success_and_missing_tokens(experiment):
    _, bundle, path, run = experiment
    complete(path, run)
    result = summary(bundle, path)
    assert result["acceptance_rate"] == 1
    assert result["cases"][0]["input_tokens"] is None
    assert result["cases"][0]["grounding_exact_group_accuracy"] == 1


@pytest.mark.parametrize("value,expected", [(None, None), (False, 0)])
def test_unknown_and_failed_review_never_pass(experiment, value, expected):
    _, bundle, path, run = experiment
    record, review = complete(path, run)
    review["checks"]["translation"] = value
    record["evidence"]["review"] = attach(path.parent, "review.json", review)
    benchmark.write_json(path, run)
    assert summary(bundle, path)["acceptance_rate"] == expected


@pytest.mark.parametrize("field,value", [("repair_rounds", 3), ("tool_calls", 101),
                                        ("elapsed_seconds", 1201), ("human_interventions", 1)])
def test_budget_and_intervention_fail_autonomous_acceptance(experiment, field, value):
    _, bundle, path, run = experiment
    record, _ = complete(path, run)
    record[field] = value
    benchmark.write_json(path, run)
    assert summary(bundle, path)["acceptance_rate"] == 0


def test_unintended_edit_remains_failure_after_repair(experiment):
    _, bundle, path, run = experiment
    record, review = complete(path, run)
    review["unintended_edit_count"] = 1
    record["evidence"]["review"] = attach(path.parent, "review.json", review)
    benchmark.write_json(path, run)
    assert summary(bundle, path)["acceptance_rate"] == 0


def test_stale_snapshot_cannot_pass(experiment):
    _, bundle, path, run = experiment
    record, _ = complete(path, run)
    record["evidence"]["after"] = record["evidence"]["before"]
    benchmark.write_json(path, run)
    with pytest.raises(ValueError, match="fresh final snapshot"):
        summary(bundle, path)


def test_evidence_mutation_rejected(experiment):
    _, bundle, path, run = experiment
    complete(path, run)
    (path.parent / "scan.json").write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        summary(bundle, path)


def test_different_runtime_and_duplicate_runs_rejected(experiment):
    _, bundle, path, run = experiment
    with pytest.raises(ValueError, match="Duplicate run_id"):
        benchmark.report(bundle, [path, path])
    other = copy.deepcopy(run)
    other["run_id"] = "other"
    other["runtime"]["renderer"] = "different"
    second = path.parent / "second.json"
    benchmark.write_json(second, other)
    with pytest.raises(ValueError, match="differ"):
        benchmark.report(bundle, [path, second])


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), 1.5])
def test_invalid_counts_rejected(experiment, value):
    _, bundle, path, run = experiment
    complete(path, run)
    run["cases"][0]["tool_calls"] = value
    path.write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(ValueError, match="tool_calls"):
        summary(bundle, path)


def test_omitted_case_rejected(experiment):
    _, bundle, path, run = experiment
    run["cases"] = []
    benchmark.write_json(path, run)
    with pytest.raises(ValueError, match="exactly once"):
        summary(bundle, path)


def test_path_escape_rejected(tmp_path):
    with pytest.raises(ValueError, match="stay inside"):
        benchmark.local_path(tmp_path, "../outside.json")


def test_prepare_refuses_to_overwrite_baseline(experiment):
    root, bundle, _, _ = experiment
    with pytest.raises(FileExistsError):
        benchmark.prepare(root / "suite.json", bundle, root=root)


def test_zero_ground_truth_support_is_unknown(experiment):
    _, bundle, path, run = experiment
    record, _ = complete(path, run)
    record["evidence"]["grounding"] = attach(path.parent, "grounding.json", {"ok": True, "data": {
        "metrics": {"exact_group_case_count": 0, "top1_exact_group_accuracy": 0}}})
    benchmark.write_json(path, run)
    assert summary(bundle, path)["cases"][0]["grounding_exact_group_accuracy"] is None


def test_failure_preserves_partial_costs(experiment):
    _, bundle, path, run = experiment
    run["cases"][0].update(status="failed", reason="Tool budget exhausted", tool_calls=100, elapsed_seconds=900)
    benchmark.write_json(path, run)
    result = summary(bundle, path)
    assert result["acceptance_rate"] == 0
    assert result["cases"][0]["tool_calls"] == 100


def test_different_baseline_rejected(experiment):
    _, bundle, path, run = experiment
    run["baseline_id"] = "another experiment"
    benchmark.write_json(path, run)
    with pytest.raises(ValueError, match="baseline"):
        summary(bundle, path)


def test_inspection_edits_and_wrong_drawing_fail(experiment):
    _, bundle, path, run = experiment
    record, _ = complete(path, run)
    case = benchmark.load_manifest(bundle)["contract"]["suite"]["cases"][0]
    case["mode"] = "inspect"
    budget = benchmark.load_manifest(bundle)["contract"]["suite"]["budget"]
    result = benchmark.summarize_case(case, record, path.parent, budget)
    assert result["accepted"] is False
    assert "read_only_case_modified" in result["protocol_violations"]
    after = benchmark.read_json(path.parent / "after.json")
    after["drawing_id"] = "another drawing"
    record["evidence"]["after"] = attach(path.parent, "after.json", after)
    benchmark.write_json(path, run)
    with pytest.raises(ValueError, match="drawing IDs"):
        summary(bundle, path)


def test_judge_assets_are_frozen(experiment):
    root, bundle, _, _ = experiment
    suite = benchmark.read_json(root / "suite.json")
    suite["judge_assets"] = ["judge.json"]
    benchmark.write_json(root / "judge.json", {"ground_truth": "reviewer annotated"})
    benchmark.write_json(root / "suite.json", suite)
    new_bundle = bundle.parent / "calibrated"
    benchmark.prepare(root / "suite.json", new_bundle, root=root)
    assert "judge.json" in benchmark.load_manifest(new_bundle)["contract"]["files"]
