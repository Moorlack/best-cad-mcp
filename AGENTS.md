# Project development rules

Maintain two user-approved objectives: the architectural/structural workflow
in BACKLOG.md and reuse of general CAD capabilities in other workflows/plugins.

- Put domain-independent geometry, unit, identity and data-processing algorithms
  in reusable modules. Keep architectural naming, structural roles, code rules
  and domain-specific readiness in adapters. Do not duplicate kernels per tool.
- Prefer a pure CAD-IR/data entry point for general algorithms; avoid importing
  AutoCAD COM, MCP or persistence into that entry point. Runtime adapters own I/O.
- Preserve existing MCP contracts and stable IDs when refactoring. Test both
  legacy behavior and a non-architectural use case for shared capabilities.
- Report limits, missing data and unsupported geometry explicitly. Do not infer
  engineering validity from geometric evidence or rename a specialized schema
  to claim universal support.
- Document reusable APIs and remaining domain dependencies in
  docs/reusable-cad-core.md. Record releases and live evidence in BACKLOG.md.
- Preserve delivery through the existing AutoCAD CMD Repair / Extend when
  feasible. Keep Revit and AutoCAD installers/runtimes independent.
- Follow the agreed live-test workflow: release, user Repair/restart, then test
  the installed MCP. Clearly distinguish checkout tests from installed tests.
