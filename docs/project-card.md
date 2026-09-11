# Project card

The tools `update_project_card`, `get_project_card`, and `get_project_card_history`
store engineering inputs in the existing workspace SQLite database. They never
modify a DWG. Cards are keyed by **workspace + explicit project_id**, shared across
drawings and conversations in that workspace. Use a different project_id for each
real project, particularly when the installer workspace is an entire drive.

Read an existing card before updating. Supply its current `expected_revision`;
use 0 for a new card. An update merges only supplied fields and stores an immutable
revision with timestamp and `change_reason`. Conflicting revisions are rejected.
History returns full snapshots newest first, up to 100 per call (default 20).
Changing workspace/database does not automatically migrate cards. Keep the
workspace database backed up with project data; cards are not embedded in DWG.

Each field is an object with `value`, `status`, `source`, and optional `note`.
Status is `confirmed`, `assumed`, or `missing`. Confirmed/assumed values require a
nonempty source describing the evidence or basis. Missing values must be null.
The software records user-supplied confirmation, not independent verification.

| Field | Value |
| --- | --- |
| address, city, state, jurisdiction, work_type, occupancy | Nonempty text |
| materials, coordinate_system, architectural_constraints | Nonempty text |
| geotechnical_information, supports_and_load_paths | Nonempty text |
| risk_category | I, II, III, IV |
| story_count | Positive integer |
| story_heights | Positive finite numbers, one per story, in `units` |
| units | mm, cm, m, in, ft |
| code_basis | Nonempty list of objects with document, edition, jurisdiction, applicability, reference; every value is nonempty text |

Example tool arguments (synthetic project, not engineering criteria):

```json
{
  "project_id": "sample-project",
  "expected_revision": 0,
  "change_reason": "Record supplied units; location is still unavailable",
  "fields": {
    "units": {"value": "m", "status": "confirmed", "source": "User confirmed drawing units"},
    "address": {"value": null, "status": "missing"}
  }
}
```

Every read/update includes readiness gates for geometry_review, code_selection,
structural_model and foundation_review. They list missing inputs, assumptions and
story-count/height conflicts. Only affected gates are blocked. Even all confirmed
fields never imply code compliance or structural design readiness: geometry,
loads and calculations are outside this increment. There is no solver to enforce
these gates yet; future calculation tools must check their own input contracts.

Changing units while heights exist requires resupplying or explicitly clearing
heights. No conversion or reinterpretation is performed silently. Unspecified
fields are preserved. Withdraw a value with status missing and value null.
Code references are recorded exactly as supplied; no automatic adoption lookup,
edition selection, document retrieval or normative validation is implemented.

Verification: `python -m pytest tests/test_project_card.py -q` covers persistence,
partial updates, history, revision conflicts, project/workspace isolation,
invalid inputs, assumptions, units changes and a native MCP client round trip.
