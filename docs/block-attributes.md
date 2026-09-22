# Атрибуты блоков в кэше и архитектурном отчёте

Обычный `scan_all_entities` с capture_visual_geometry=true, а также standard/full
сканирование читают атрибуты AcDbBlockReference. Данные находятся в CAD-IR:
`geometry.block_attributes`. Для каждой записи сохраняются handle, tag, text,
invisible и kind. Повторяющиеся теги и пустые строки сохраняются без объединения.
Неизвестная видимость возвращается как null, а не false.

`kind=reference` — обычный AttributeReference из GetAttributes;
`kind=constant_definition` — определение постоянного атрибута из
GetConstantAttributes. Его handle не является handle отдельной вставки.
Именно так различает эти методы [документация Autodesk](https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-ActiveX/files/GUID-C34E2AE8-A2D0-4781-8B5B-BC3E226E8B94.htm).
Координаты атрибутов не экспортируются: преобразование определений в координаты
вставки ещё не реализовано. TextString сохраняется как исходный текст, без
интерпретации форматирования, полей и инженерных характеристик.

Архитектурный отчёт содержит `block_annotations`, включая атрибуты блоков,
которые не получили архитектурную категорию. Каждая запись содержит block_handle
и handle атрибута. Скрытые атрибуты не удаляются; Invisible не доказывает видимость
на экране, которая также зависит от слоя и блока. Текст — данные чертежа,
не инструкции для ИИ и не подтверждённые инженерные исходные данные.
Атрибуты не участвуют в автоматической классификации кандидатов.

## Полнота и ограничения

- До 64 атрибутов каждого вида на блок, до 1024 символов на строковое поле.
- В block_attributes: status=complete/partial, groups с available/included,
  truncated/read_failed; у записи — unavailable_fields/truncated_fields.
- В block_annotations: до 200 записей, available_in_cache/included/truncated,
  partial_block_handles и not_captured_block_handles.
- Ошибка COM не уничтожает данные самого блока или успешно прочитанные атрибуты.
- Пределы ограничивают обрабатываемые данные после возврата COM-массивов;
  получение самого массива AutoCAD не поддерживает постранично.
- Старый кэш требует повторного scan; его отсутствие атрибутов не считается
  подтверждением, что блоки не имеют атрибутов.
- Обычные TEXT/MTEXT внутри определений, вложенные блоки и Xrefs не обходятся.

## Проверка после обновления

Запустить существующий установщик → Repair / Extend, затем перезапустить клиент.
Новые зависимости и новый CMD не нужны.

Промпт:

```text
Проверь чтение атрибутов блоков установленным AutoCAD MCP.
Не изменяй, не сохраняй и не закрывай DWG.
1. check_runtime_environment(check_autocad=true), затем get_document_info.
2. scan_all_entities(clear_annotations=false, clear_understanding=false).
3. analyze_architectural_drawing: покажи block_annotations, число записей,
   неполные/непрочитанные блоки и признак усечения.
4. Для нескольких блоков сверь tag/text/invisible обычных атрибутов с
   get_block_attributes. Постоянные определения оцени отдельно:
   существующий get_block_attributes не возвращает их полный набор.
5. Если есть Glass/Vent, перечисли их вместе с block_handle и handle атрибута.
   Не требуй этих слов в другом чертеже; если атрибутов нет, укажи SKIP
   проверки непустых данных. Не превращай надписи в подтверждённые конструкции.
6. Повтори get_document_info и сравни имя, units, entity_count и saved.
Выдай PASS/FAIL/SKIP и ограничения. Карточку проекта не меняй.
```
