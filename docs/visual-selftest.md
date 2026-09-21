# Visual pipeline verification

Run `check_visual_pipeline` through MCP or `python -m src.visual_selftest`
(`--json` for machine-readable output). No active drawing or running AutoCAD is
required. The check does not create, edit, save or close DWG documents.

The test copies a bundled AutoCAD WMF into a temporary directory and uses the
same image preparation path as model vision. It decodes the resulting PNG/JPEG
with Pillow, checks for nonuniform image content and bounded dimensions. A
separate BMP tests PNG conversion and resizing from 1024×512 to 256×128. Temporary
outputs are removed after success/failure.

Missing dependencies, converter failures, corrupt output and blank rendering
produce `ok=false`; the CLI also exits with code 1. Finding an executable alone
does not count as success. Existing per-converter timeouts apply. Background
conversion processes are hidden on Windows.

The fixture `src/assets/visual-selftest.wmf` is a copy of this repository's
`docs/images/readme-cad-real.WMF` under the existing project license. It is included
in built packages so the check also works outside a source checkout.

## Windows installer

The independent AutoCAD installer, version 2026.09.21.01, installs the maintained
checkout with `pip install --upgrade -e ".[visual]"`, including Pillow and CairoSVG
in the dedicated environment. It runs this visual test before the MCP startup
test and client registration. A failed test stops setup with diagnostic output.

Use the updated standalone installer → Repair / Extend → desired client, then
fully restart the client. Older installers using requirements.txt do not guarantee
installation of the visual extra.

## Limits and Claude check

PASS verifies local WMF conversion and raster preparation, not live DWG export,
pixel/handle mapping accuracy, or client image display. SVG/Cairo native-library
availability is not certified by this WMF test. No engineering inference occurs.

After updating, ask Claude:

> Call check_visual_pipeline and report PASS/FAIL for each check. Do not modify
> or save AutoCAD drawings. Confirm that live_autocad_export_tested and
> client_image_display_tested are false; do not claim those were verified.
