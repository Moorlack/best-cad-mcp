# Architectural DWG analysis — first increment

The Moorlack fork adds `analyze_architectural_drawing(entity_limit=10000)`.
It inventories architectural **candidates** from the existing CAD-IR snapshot,
without modifying or saving AutoCAD drawings. Available in `core`, `lean`, and
`full`; no additional dependency or structural code library is required.

## Workflow in Claude

1. Check the AutoCAD connection and confirm the intended drawing and model/paper space.
2. Run `scan_all_entities(topology_detail="full")` and check its result for errors.
3. Call `analyze_architectural_drawing`. The tool itself never triggers a live scan.
4. Review `coverage`, `issues`, `unclassified`, and candidate `warnings` before
   interpreting `candidates`. A successful tool call does not certify scan coverage.
5. Verify important handles with `explain_entity` and a mapped visual export.
   Confirm units against dimensions. Present unresolved questions to the engineer.

Example user prompt:

> Analyze the current architectural DWG without changing or saving it. Confirm the
> drawing/space and connection, perform a full topology scan, then call
> analyze_architectural_drawing. Present wall, opening, grid, column and boundary
> candidates with handles, layer, evidence and confidence. Report incomplete
> coverage, unknown units, unsupported objects and ambiguities. Verify important
> candidates against structured geometry and a mapped view. Do not infer structural
> function, calculate loads, or select members.

## Report contract

`data.report` uses `architectural-analysis/v1`:

- `drawing` and `source`: original drawing identity, IR generation time, source
  quality/warnings. Generation time is **not** evidence of a fresh AutoCAD scan.
- `coverage`: scanned/examined counts and explicit truncation. Raise `entity_limit`
  up to 100000 when necessary; this does not repair omissions in the original scan.
- `candidates`: drawing-scoped stable IDs, original native handles, layer, exact
  copied geometry/bbox, naming and geometry evidence, ordinal confidence, warnings.
- `unclassified`: entities without supported classification evidence.
- `issues`: missing units, unverified freshness, conflicting names, incompatible
  geometry, duplicate/missing handles, unverified Xrefs and incomplete coverage.
- `structural_design_ready`: always false in this increment.

Whole English tokens in layer names (e.g. `A-WALL`, `A-DOOR`, `S-GRID`, `S-COLS`,
`S-SLAB`) and block names provide naming evidence. Supported primitive geometry
must also agree. Labels alone are insufficient: text on `A-WALL` is not a wall.
Slab/room boundary candidates require a closed polyline; an unnamed closed
polyline remains only a `closed_boundary`. A closed flag is not proof of a valid,
simple polygon. No area is calculated and curved segments are not flattened.

`MEDIUM` means one naming category plus compatible primitive geometry. `LOW`
marks generic outlines, conflicting names, invisible entities or uninterpreted
block references. Neither label is a probability or engineering acceptance.
Every structural role remains `unknown`. Counts are source-entity candidates,
not counts of physical walls, doors or other building elements.

## Deliberate limits and next validation

This is a baseline inventory, not a complete architectural reconstruction.
It does not pair wall lines, associate openings with walls, assign floors,
interpret arbitrary naming standards, traverse block/Xref contents, distinguish
exterior/interior walls or identify bearing members. Native AEC/proxy objects
without supported geometry remain unclassified. Upstream CAD-IR currently reports
units as `unknown`; the report preserves that limitation instead of guessing.

No project codes, load calculations or sizing are included. Synthetic tests cover
the report contract, ambiguous/unsupported inputs and the real SQLite-to-IR path.
Validation on an engineer's DWG and reviewed interpretation is still required.

Run isolated tests: `python -m pytest tests/test_architecture.py -q`.
The AutoCAD installer and installed MCP source are unchanged by this branch.
