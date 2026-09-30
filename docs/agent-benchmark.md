# CAD agent loop experiments

The existing synthetic grounding tests and deterministic CADPlan demo test the
tools. To measure a model's ability to identify complete components, edit them,
and recover from mistakes, run the same tasks against independent copies of the
same drawing with fixed guidance and budgets.

`scripts/agent_benchmark.py` is an **offline experiment ledger** for a source
checkout. It freezes inputs, creates an empty run template, verifies evidence
hashes, and summarizes reviewed results. It does not call a model provider,
drive AutoCAD, enforce budgets during execution, or automatically judge images.
No GPT-6 improvement or live benchmark result is claimed by this addition.

## Pilot tasks

The initial [suite](../benchmarks/agent-loop/suite.json) uses the checked-in
flange coupling DXF:

1. Identify the full left-shaft outline in the longitudinal half-section without
   changing anything. A single correct edge is not a complete component.
2. Move the leftmost component in the exploded schematic 5 mm left, preserving
   all unrelated entities. Verify the result and repair mistakes within budget.

These are pilot tasks, not a calibrated benchmark dataset. A reviewer must first
inspect the imported DXF, establish complete target groups, and check that the
edit task is unambiguous and feasible. If it is not, revise the suite and freeze
a new baseline **before** testing either model. Do not invent ground truth from
the model's own findings. Keep judge annotations out of the model's context.
Import can change handles: annotate the baseline in the actual run drawing or
verify a mapping to it; do not copy handle IDs from historical demo artifacts.
Use `import_dxf(filepath, allow_modify=True)` for DXF input. It creates a
separate unsaved drawing; `open_drawing` is reserved for DWG. Inspect units,
scan the imported entities, and inspect the actual raster before accepting a
visual baseline. A readable image file alone does not prove a useful export.
After restarting an MCP server, call `get_document_info` to activate the current
drawing's metadata scope before reading cached scans or snapshots.
To freeze an independent answer key or reviewer protocol, add repository-relative
file paths to a top-level `judge_assets` array in a custom suite before preparing
it. Those bytes become part of the baseline. Keep these files with the reviewer,
not in the agent's supplied context. The default pilot has no calibrated answer
key; its report explicitly says `has_frozen_judge_assets=false`.

Follow the pilot with shared-edge, overlapping-contour, and repeated-component
fixtures, then a previously unseen maintenance drawing. Existing synthetic
stress tests are useful fixture ideas, but their canned observations are not
live model outputs.

## Freeze a baseline

From the repository root, after installing the project test/visual dependencies:

```powershell
.\.venv\Scripts\python.exe scripts\agent_benchmark.py prepare --output .cad_mcp\benchmarks\pilot-v1
```

This creates:

- `manifest.json`: suite, task text, acceptance criteria, budgets, file hashes,
  git revision, and a content-derived baseline ID;
- `frozen/`: exact drawing, source, benchmark script, prompt and skill/reference
  bytes, including uncommitted changes;
- `preparation-environment.json`: preparation Python and package versions;
- `run-template.json`: pending cases, with unknown measurements left as `null`.

An existing output directory is never overwritten. Run records use the same
baseline ID for both models. Use the frozen source and guidance with the
prepared Python environment; the MCP process can run `python -m src.server`
with `frozen/` as its working directory and `CAD_MCP_WORKSPACE_ROOT` pointing to
the separate case workspace. Configure the Python executable by absolute path.
The preparation environment is provenance, not proof of the later runtime.

## Run each model

Copy `run-template.json` into a separate run directory and fill in:

```json
{
  "run_id": "model-a-repetition-1",
  "execution_kind": "live",
  "model": "exact language/agent model identifier",
  "vision_model": "exact vision model identifier, even if the same model",
  "runtime": {
    "autocad": "installed version and build",
    "python": "actual server Python version",
    "mcp": "actual MCP SDK version",
    "renderer": "actual renderer and version",
    "host": "stable anonymized machine ID",
    "tool_profile": "core",
    "dependencies_sha256": "hash of the actual dependency version record"
  },
  "model_settings": {
    "reasoning_effort": "actual setting or unavailable",
    "temperature": "actual setting or unavailable",
    "client": "agent client and version"
  }
}
```

Preserve the template's other fields. Record the actual model identities; a
run label such as `model-a` is not sufficient provenance. `synthetic` is only for
harness tests, and cannot be compared in one report with `live` runs.

For each case:

1. Start a fresh model context and a separate workspace with a new copy of the
   frozen DXF. Use the same import procedure, units, view and image resolution.
   Do not hand one model a drawing already repaired by another model.
2. Open AutoCAD under the same Windows account and pass the skill's live runtime
   preflight. Do not start another AutoCAD process from this script. No live
   session means `blocked`, not a successful simulated run.
3. Give the model the frozen skill, relevant prompt, case task and its budget.
   It must choose the actual handles and plans. Do not replay `generate_demo.py`
   or reveal historical plans, answers or judge annotations.
4. Save the raw model responses and every MCP call/result, including rejected
   JSON, failures, dry-runs and retries. Record wall time, total tool calls,
   repair rounds, and human interventions. A repair round is one
   verify → revise → execute → verify cycle after the initial attempted edit;
   splitting a plan into phases does not reset the budget. Count failed edit
   attempts and rolled-back wrong edits too. Stop at the frozen budget.
5. Rescan after edits and export a fresh mapped image. Never reuse the old
   snapshot's pixel mapping. Keep original clean images, overlays and scans.
6. Have a reviewer independently check every frozen acceptance criterion,
   including intermediate wrong edits. `validate_geometry` returning `ok=true`
   only means the validation tool ran; inspect its report and compare baseline
   issues. A geometry pass alone cannot prove the user's requested edit occurred.
7. Set status to `completed`, `failed`, or `blocked`; give failed/blocked cases a
   reason. `completed` means the run and its review finished, not that it passed.

Run at least three repetitions per model and alternate execution order. Compare
the agent model with vision fixed, then vision with the agent fixed, if those
roles are separable. A joint-model comparison measures their combined effect.
Only after that should you revise the skill and run a new baseline. The reporter
intentionally refuses to combine different baselines, runtimes, execution kinds
or model settings. Separate reports can describe such experiments explicitly.

## Record evidence

Every evidence reference is `{ "path": "relative/path", "sha256": "..." }`.
All paths, including nested snapshot references, are relative to the **run JSON
directory**, not the file containing the reference. Generate a reference with:

```powershell
.\.venv\Scripts\python.exe scripts\agent_benchmark.py receipt .cad_mcp\runs\a\trace.jsonl --root .cad_mcp\runs\a
```

For a completed case, `evidence` requires:

- `transcript`: the complete raw trace;
- `before` and `after`: JSON snapshot receipts shaped as below;
- `review`: an independent review JSON;
- `grounding`: optionally, the unmodified structured ToolResult from
  `evaluate_vlm_grounding`, using independent complete handle groups.

Snapshot receipt example (receipt hashes omitted here for readability):

```json
{
  "snapshot_id": "actual-mapped-snapshot-id",
  "drawing_id": "actual-run-drawing-id",
  "image": {"path": "after/clean.png", "sha256": "..."},
  "scan": {"path": "after/scan.json", "sha256": "..."}
}
```

The two receipts must identify the same run drawing; edited cases require
different snapshot IDs. They are lightweight references to actual MCP evidence,
not replacements for the exported snapshot sidecars and scans in the trace.

Review example for the inspection case:

```json
{
  "reviewer": "independent reviewer identifier",
  "case_id": "shaft-outline",
  "snapshot_id": "actual-final-snapshot-id",
  "checks": {
    "complete_group_or_justified_abstention": null,
    "evidence_agreement": null,
    "drawing_unchanged": null
  },
  "edit_attempt_count": 0,
  "unintended_edit_count": 0,
  "notes": "Explain judgments and point to trace entries or artifacts."
}
```

Use `true`, `false`, or `null` for each criterion. `null` means unreviewed or
unresolved. An edit attempt is one mutating tool call (including mutating steps
inside a CADPlan); an unintended edit is an attempt that actually changed a
non-target entity or applied an incorrect change to the target, even if later
rolled back. Counts are reviewer measurements, not inferred from plan success.
Keep raw token usage when available; leave unavailable token counts `null`.

## Summarize and compare

```powershell
.\.venv\Scripts\python.exe scripts\agent_benchmark.py report --bundle .cad_mcp\benchmarks\pilot-v1 --run .cad_mcp\runs\a\run.json --run .cad_mcp\runs\b\run.json
```

The JSON report retains individual repetitions and per-case measurements:

- exact-group grounding accuracy and its support, when an evaluator result is
  supplied; zero labeled groups produces `null`, not perfect accuracy;
- reviewer-counted unintended edits / edit attempts;
- repair rounds, tool calls, elapsed seconds, tokens and interventions;
- completion coverage and final acceptance.

Acceptance requires every criterion to pass, no unintended edit, and no budget
violation or human intervention. Inspection cases must have no edit attempts.
Failed cases count as failures; pending/blocked/unresolved cases leave overall
acceptance `null` until the entire frozen suite is assessed. Missing cases,
duplicate runs, stale edit snapshots, changed files and invalid counts are
rejected. This avoids silently dropping hard cases or treating unknown as pass.

Hashes establish artifact integrity, not honest provenance or correct review.
The ledger does not parse the transcript to independently prove edits, tool-call
counts, budget compliance, or image content. Review the raw trace, scans and
images before trusting the report. A prepared bundle with pending cases is not
a completed live evaluation.
