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

### Live WMF text contrast

WMF exports now temporarily set `WMFBKGND=1` and restore its previous value in a
finally block, including export failure. This preserves the AutoCAD background
and original foreground colors. Previously, transparent export could make ByLayer
block attributes dark against dark MTEXT background masks. The image pipeline
then received an already unreadable WMF; resizing was not the cause.

The fix was verified on a live drawing with Glass/Vent attributes: all ten Glass
and five Vent labels became visible. No entity/font/color was edited. The session
setting, Saved flag and DBMOD were unchanged after export. Failure to restore the
setting is reported explicitly, not silently ignored. Non-WMF exports are unchanged.

This is a source-only update delivered by Repair / Extend using the existing
installer. The resulting image may have a dark background matching AutoCAD.
No automatic cropping or pixel mapping changes are included.

Autodesk references: [WMFBKGND](https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-LT/files/GUID-51DB9284-EAF6-478E-8A3F-2A18E7A9263B.htm)
and [WMFFOREGND](https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-Core/files/GUID-485219AF-71F4-4E7A-B5FD-BE53E358AC54.htm).

PASS verifies local WMF conversion and raster preparation, not live DWG export,
pixel/handle mapping accuracy, or client image display. SVG/Cairo native-library
availability is not certified by this WMF test. No engineering inference occurs.

After updating, ask Claude:

> Call check_visual_pipeline and report PASS/FAIL for each check. Do not modify
> or save AutoCAD drawings. Confirm that live_autocad_export_tested and
> client_image_display_tested are false; do not claim those were verified.
