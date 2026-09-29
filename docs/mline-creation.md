# Explicit MLINE scale and justification

`draw_mline(points, layer=None, color="bylayer", scale=None, justification=None)`
now accepts a finite positive scale and `top`, `zero`, or `bottom` justification.
These are object properties. CMLSCALE/CMLJUST are not changed. Omitted options
retain the existing COM defaults, rather than promising to use current sysvars.
For STANDARD (offsets ±0.5), scale 8 yields separation 8 drawing units; custom
styles have their own offsets, so scale is not universally a wall thickness.

Coordinates must be complete finite XY pairs, with at least two vertices and
no consecutive duplicates. Validation runs before changing layers or creating
geometry. Requested properties are read back after setting. On failure, the new
entity is deleted; if deletion also fails, the error includes its handle.
Layer creation/activation is not rolled back. No drawing save occurs.
Run a fresh scan before analysis; draw operations do not refresh the scan fingerprint.

Autodesk references: [MLineScale](https://help.autodesk.com/cloudhelp/2025/ITA/AutoCAD-LT-ActiveX-Reference/files/GUID-6CFD9F11-2CE2-4011-BF88-E264AAE9D2A1.htm),
[Justification](https://help.autodesk.com/cloudhelp/2026/ESP/AutoCAD-ActiveX-Reference/files/GUID-7D9F7368-0B08-41FD-B7B3-8B800574FAC1.htm).

## Installed live test pending Repair

List processes, list instances, select TEST2 by full path, confirm get_document_info
before any write. Never modify the working Civil 3D drawings.
On a dedicated test layer create horizontal STANDARD MLINEs of length 100:
scale=8, one each with top/zero/bottom, separated spatially.
Fresh scan must report scale 8, justification 0/1/2 and two faces separated by 8.
Compare native AutoCAD bounding boxes to predicted faces; confirm CMLSCALE and
CMLJUST remain unchanged. Keep the test DWG unsaved and record actual handles.
