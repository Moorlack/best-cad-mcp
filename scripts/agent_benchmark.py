"""Freeze CAD agent experiments and summarize evidence-backed run records.

This is an offline experiment ledger, not a model runner or an AutoCAD driver.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "cad-agent-benchmark/v1"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def local_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or Path(name).is_absolute():
        raise ValueError(f"Path must stay inside {root}: {name}")
    return path


def receipt(path, root):
    path = Path(path).resolve()
    return {"path": path.relative_to(root.resolve()).as_posix(), "sha256": digest(path.read_bytes())}


def evidence(root, ref):
    if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
        raise ValueError("Evidence requires path and sha256")
    path = local_path(root, ref["path"])
    if digest(path.read_bytes()) != ref["sha256"]:
        raise ValueError(f"Evidence hash mismatch: {ref['path']}")
    return path


def number(value, label, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def validate_suite(suite):
    if suite.get("schema_version") != SCHEMA or not suite.get("cases"):
        raise ValueError("Expected a nonempty cad-agent-benchmark/v1 suite")
    ids = set()
    for case in suite["cases"]:
        if not case.get("case_id") or case["case_id"] in ids:
            raise ValueError("Case IDs must be nonempty and unique")
        ids.add(case["case_id"])
        if not case.get("prompt") or not isinstance(case.get("acceptance"), dict) or not case["acceptance"]:
            raise ValueError("Each case needs a prompt and acceptance criteria")
        if case.get("mode") not in {"inspect", "edit"}:
            raise ValueError("Case mode must be inspect or edit")
    for key in ("max_repair_rounds", "max_tool_calls", "max_elapsed_seconds"):
        number(suite["budget"][key], key, integer=True)


def prepare(suite_path, output, root=ROOT):
    suite = read_json(suite_path)
    validate_suite(suite)
    # Freeze the entire guidance tree, including referenced standards, and
    # source bytes rather than relying on a git SHA that misses local edits.
    paths = {local_path(root, case["drawing"]) for case in suite["cases"]}
    paths.update(local_path(root, name) for name in suite.get("judge_assets", []))
    for folder, pattern in (("src", "*.py"), ("prompts", "*.md"), (".agents/skills", "*.md")):
        paths.update((root / folder).rglob(pattern))
    paths.update(root / name for name in ("pyproject.toml", "server.json", "scripts/agent_benchmark.py"))
    frozen = {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(paths)}
    contract = {"suite": suite, "files": {name: digest(data) for name, data in frozen.items()}}
    baseline_id = identity(contract)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in frozen.items():
        target = local_path(output / "frozen", name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    manifest = {"schema_version": SCHEMA, "baseline_id": baseline_id,
                "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
                "contract": contract}
    write_json(output / "manifest.json", manifest)
    versions = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}
    write_json(output / "preparation-environment.json", {"python": sys.version, "packages": versions})
    template = {
        "schema_version": SCHEMA, "baseline_id": baseline_id, "run_id": "",
        "execution_kind": "live", "model": "", "vision_model": "",
        "runtime": {}, "model_settings": {}, "cases": [],
    }
    for case in suite["cases"]:
        template["cases"].append({
            "case_id": case["case_id"], "status": "pending", "reason": "",
            "repair_rounds": None, "tool_calls": None, "elapsed_seconds": None,
            "input_tokens": None, "output_tokens": None, "human_interventions": None,
            "evidence": {key: None for key in ("transcript", "before", "after", "grounding", "review")},
        })
    write_json(output / "run-template.json", template)
    return {"baseline_id": baseline_id, "output": str(output.resolve()), "case_count": len(suite["cases"])}


def load_manifest(bundle):
    manifest = read_json(bundle / "manifest.json")
    if manifest.get("schema_version") != SCHEMA or identity(manifest["contract"]) != manifest["baseline_id"]:
        raise ValueError("Invalid baseline manifest")
    validate_suite(manifest["contract"]["suite"])
    for name, expected in manifest["contract"]["files"].items():
        if digest(local_path(bundle / "frozen", name).read_bytes()) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    return manifest


def summarize_case(case, record, root, budget):
    status = record.get("status")
    if status not in {"pending", "blocked", "failed", "completed"}:
        raise ValueError("Unknown case status")
    result = {"case_id": case["case_id"], "status": status, "accepted": None,
              "grounding_exact_group_accuracy": None, "reason": record.get("reason", "")}
    for key in ("repair_rounds", "tool_calls", "elapsed_seconds", "human_interventions", "input_tokens", "output_tokens"):
        value = record.get(key)
        result[key] = None if value is None else number(value, key, integer=key != "elapsed_seconds")
    if status != "completed":
        if status != "pending" and not record.get("reason"):
            raise ValueError("Blocked/failed cases require a reason")
        if status == "failed":
            result["accepted"] = False
        return result
    for key in ("repair_rounds", "tool_calls", "elapsed_seconds", "human_interventions"):
        result[key] = number(record.get(key), key, integer=key != "elapsed_seconds")
    refs = record["evidence"]
    evidence(root, refs["transcript"])
    before = read_json(evidence(root, refs["before"]))
    after = read_json(evidence(root, refs["after"]))
    for snapshot in (before, after):
        if not snapshot.get("snapshot_id") or not snapshot.get("drawing_id"):
            raise ValueError("Snapshot receipts need snapshot_id and drawing_id")
        evidence(root, snapshot["image"])
        evidence(root, snapshot["scan"])
    if before["drawing_id"] != after["drawing_id"]:
        raise ValueError("Before/after drawing IDs differ")
    if case["mode"] == "edit" and before["snapshot_id"] == after["snapshot_id"]:
        raise ValueError("Edited drawings require a fresh final snapshot")
    review = read_json(evidence(root, refs["review"]))
    if not review.get("reviewer") or review.get("case_id") != case["case_id"]:
        raise ValueError("Review requires reviewer and matching case_id")
    if review.get("snapshot_id") != after["snapshot_id"]:
        raise ValueError("Review must reference the final snapshot")
    checks = review.get("checks", {})
    if set(checks) != set(case["acceptance"]) or any(v is not None and type(v) is not bool for v in checks.values()):
        raise ValueError("Review must score every frozen acceptance criterion as true, false, or null")
    attempts = number(review.get("edit_attempt_count"), "edit_attempt_count", integer=True)
    wrong = number(review.get("unintended_edit_count"), "unintended_edit_count", integer=True)
    if wrong > attempts:
        raise ValueError("Unintended edit count exceeds edit attempts")
    result.update(edit_attempt_count=attempts, unintended_edit_count=wrong,
                  unintended_edit_rate=wrong / attempts if attempts else None)
    if refs.get("grounding") is not None:
        grounding = read_json(evidence(root, refs["grounding"]))
        if grounding.get("ok") is not True:
            raise ValueError("Grounding evaluation did not succeed")
        metrics = grounding["data"]["metrics"]
        support = number(metrics["exact_group_case_count"], "exact_group_case_count", integer=True)
        accuracy = number(metrics["top1_exact_group_accuracy"], "top1_exact_group_accuracy")
        if accuracy > 1:
            raise ValueError("Grounding accuracy exceeds 1")
        result["grounding_exact_group_accuracy"] = accuracy if support else None
        result["grounding_exact_group_support"] = support
    violations = [key for key in ("repair_rounds", "tool_calls", "elapsed_seconds")
                  if result[key] > budget["max_" + key]]
    if record["human_interventions"]:
        violations.append("human_interventions")
    if case["mode"] == "inspect" and attempts:
        violations.append("read_only_case_modified")
    result["protocol_violations"] = violations
    result["accepted"] = (False if violations or wrong or False in checks.values()
                          else None if None in checks.values() else True)
    return result


def report(bundle, runs):
    manifest = load_manifest(Path(bundle))
    suite = manifest["contract"]["suite"]
    results = []
    comparison_keys = set()
    run_ids = set()
    for path in runs:
        path = Path(path)
        run = read_json(path)
        if run.get("schema_version") != SCHEMA or run.get("baseline_id") != manifest["baseline_id"]:
            raise ValueError("Run baseline does not match the frozen experiment")
        for key in ("run_id", "model", "vision_model"):
            if not isinstance(run.get(key), str) or not run[key].strip():
                raise ValueError(f"Run requires {key}")
        if run["run_id"] in run_ids:
            raise ValueError("Duplicate run_id")
        run_ids.add(run["run_id"])
        if run.get("execution_kind") not in {"live", "synthetic"}:
            raise ValueError("execution_kind must be live or synthetic")
        runtime_keys = ("autocad", "python", "mcp", "renderer", "host", "tool_profile", "dependencies_sha256")
        if not isinstance(run.get("runtime"), dict) or any(not run["runtime"].get(k) for k in runtime_keys):
            raise ValueError("Record actual execution runtime (AutoCAD, Python, MCP, renderer, host)")
        if run["runtime"]["tool_profile"] != suite["tool_profile"]:
            raise ValueError("Runtime tool profile differs from the frozen suite")
        if not isinstance(run.get("model_settings"), dict):
            raise ValueError("model_settings must be an object")
        comparison_keys.add(identity({k: run[k] for k in ("execution_kind", "runtime", "model_settings")}))
        records = run.get("cases", [])
        expected_ids = {c["case_id"] for c in suite["cases"]}
        if len(records) != len(expected_ids) or {c["case_id"] for c in records} != expected_ids:
            raise ValueError("Run must contain each frozen case exactly once")
        by_id = {c["case_id"]: c for c in records}
        cases = [summarize_case(c, by_id[c["case_id"]], path.parent, suite["budget"]) for c in suite["cases"]]
        accepted = sum(c["accepted"] is True for c in cases)
        assessed = sum(c["accepted"] is not None for c in cases)
        results.append({
            "run_id": run["run_id"], "model": run["model"], "vision_model": run["vision_model"],
            "execution_kind": run["execution_kind"], "cases": cases,
            "accepted_case_count": accepted, "assessed_case_count": assessed,
            "scheduled_case_count": len(cases),
            "completion_rate": sum(c["status"] == "completed" for c in cases) / len(cases),
            "acceptance_rate": accepted / len(cases) if assessed == len(cases) else None,
        })
    if len(comparison_keys) > 1:
        raise ValueError("Runtime, execution kind, or model settings differ; report these experiments separately")
    return {"schema_version": SCHEMA, "baseline_id": manifest["baseline_id"],
            "has_frozen_judge_assets": bool(suite.get("judge_assets")), "runs": results,
            "limitations": ["Evidence hashes check integrity, not the truth of a model or reviewer claim.",
                            "Acceptance and unintended edits depend on independent review of scans and images.",
                            "No model or AutoCAD execution is performed by this reporter."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("prepare")
    freeze.add_argument("--suite", type=Path, default=ROOT / "benchmarks/agent-loop/suite.json")
    freeze.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("report")
    score.add_argument("--bundle", type=Path, required=True)
    score.add_argument("--run", type=Path, action="append", required=True)
    ref = commands.add_parser("receipt")
    ref.add_argument("path", type=Path)
    ref.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.suite, args.output)
        elif args.command == "report":
            result = report(args.bundle, args.run)
        else:
            result = receipt(args.path, args.root)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Benchmark error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
