# Метаданные блоков в архитектурном анализе

Обычный `scan_all_entities` (minimal, capture_visual_geometry=true) теперь
сохраняет для AcDbBlockReference доступные свойства: block_name, effective_name,
insertion_point (WCS), normal, rotation (радианы), x_scale/y_scale/z_scale,
visible и is_dynamic_block. Режимы standard/full также читают эти поля.
Отрицательный масштаб сохраняется; отсутствующие свойства не заменяются догадками.

Архитектурный анализ учитывает EffectiveName динамического блока, даже если
его внутреннее имя анонимное, например *U42. Различие Name/EffectiveName описано
в [Autodesk ActiveX](https://help.autodesk.com/cloudhelp/2024/KOR/AutoCAD-ActiveX-Reference/files/GUID-A87607A4-D7F9-40B3-94B5-B9D88011DEB5.htm).

Это метаданные ссылки, а не восстановленная геометрия содержимого. Блоки не
взрываются, вложенные объекты и Xrefs не обходятся. Имена SG-1/VG-2 сами по себе
не дают архитектурной категории. Кандидаты по осмысленным именам вроде A-DOOR
имеют LOW confidence, block_contents_not_interpreted и требуют проверки.
Готовность к конструктивному расчёту остаётся false.

Обновление: существующий установщик → Repair / Extend → перезапуск клиента.
После обновления нужен новый scan. Старый кэш автоматически не дополняется.

## Проверка через клиент

Прочитай get_document_info, затем выполни scan_all_entities с
clear_annotations=false, clear_understanding=false. Через build_drawing_ir
с include_raw=true проверь метаданные нескольких блоков и вызови
analyze_architectural_drawing. Не создавай и не редактируй объекты, не сохраняй
DWG. Если блоков нет, отметь проверку метаданных блоков как SKIP.
Не требуй появления кандидатов, если названия не содержат архитектурных подсказок.
В конце сравни имя документа, units, entity_count и saved с исходными значениями.

Синтетические тесты пройдены; проверка реальных блоков после установки остаётся
отдельным шагом. Этот документ не подтверждает распознавание инженерного DWG.
