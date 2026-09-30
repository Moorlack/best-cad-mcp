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

## Live test plan (выполнен 2026-09-30)

List processes, list instances, select TEST2 by full path, confirm get_document_info
before any write. Never modify the working Civil 3D drawings.
On a dedicated test layer create horizontal STANDARD MLINEs of length 100:
scale=8, one each with top/zero/bottom, separated spatially.
Fresh scan must report scale 8, justification 0/1/2 and two faces separated by 8.
Compare native AutoCAD bounding boxes to predicted faces; confirm CMLSCALE and
CMLJUST remain unchanged. Keep the test DWG unsaved and record actual handles.

## Результат live-теста 2026-09-30 (установленный a1f567f, TEST2.dwg)

- 8B0 top (y=2000), 8B1 zero (y=2200), 8B2 bottom (y=2400), scale=8, длина 100, слой A-WALL-TEST.
- Scan: две грани на расстоянии 8; top → 2000/1992, zero → 2204/2196, bottom → 2408/2400.
- После `regen` native-рамки: 1992–2000, 2196–2204, 2400–2408 (высота 8). До `regen` AutoCAD отдавал рамку
  прежней геометрии (высота 1.0): после установки свойств через COM отображаемая геометрия MLINE не обновляется
  сама. Данные scan и анализ корректны; для сверки с AutoCAD нужна регенерация (кандидат: Update() после свойств).
- CMLSCALE=1 и CMLJUST=0 до и после не менялись. Неверные scale/justification отклоняются до создания объекта.
- Клиентское описание инструмента может быть устаревшим (без новых параметров); вызов с параметрами работает.

## Обновление отображаемой геометрии (live PASS 2026-09-30, установленный 5f621eb)

После установки `MLineScale`/`Justification` через COM `add_mline` вызывает `Update()` у объекта (только когда заданы
scale или justification). Ошибка обновления только пишется в лог, корректный объект не удаляется. Подтверждение
после Repair: нарисовать MLINE scale=8 и сразу, без `regen`, прочитать GetBoundingBox — высота должна быть 8.
Если высота остаётся 1.0, `Update()` недостаточно; тогда нужен `Regen`/переустановка геометрии.

Результат: 8B0/8B1/8B2 (scale 8, top/zero/bottom) — GetBoundingBox без `regen` сразу даёт высоту 8 (1992–2000, 2196–2204, 2400–2408); CMLSCALE/CMLJUST не менялись.

