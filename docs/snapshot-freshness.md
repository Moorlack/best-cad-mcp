# Свежесть снимка после scan

`analyze_geometry` и `analyze_architectural_drawing` читают кэш последнего scan.
Раньше `source.freshness` всегда был `unverified`. Теперь полный scan запоминает
слепок документа, а оба инструмента сравнивают его с живым AutoCAD:

| Поле слепка | Что ловит |
| --- | --- |
| путь документа (`FullName`) | активен другой DWG |
| число объектов ModelSpace | объекты добавлены или удалены |
| `HANDSEED` | созданы любые объекты базы (линии, слои, стили…) |

Статусы в `source.freshness` (подробности — `source.freshness_check`):

- `consistent_with_scan` — всё совпало. Перемещения и правки свойств
  существующих объектов этот слепок **не** меняют, поэтому это не доказательство
  актуальности; предупреждение `snapshot_existing_object_edits_not_detected`.
- `stale` — причина `active_document_differs`, `model_space_object_count_changed`
  или `database_objects_created_since_scan`; предупреждение/issue `snapshot_stale`.
- `unverified` — нет слепка (старый, усечённый или неполный scan), AutoCAD
  недоступен или слепок неполон; прежнее предупреждение `snapshot_freshness_unverified`.

Слепок сохраняется только для полного scan без усечения и ошибок чтения
объектов; очистка кэша удаляет его. Проверка только подключается к уже
запущенному AutoCAD (GetActiveObject) и никогда его не запускает. Чистые
функции `build_geometry_report`/`build_architectural_report` живой документ не
читают и остаются `unverified`.

Попутное исправление: если AutoCAD или документ недоступен, `scan_all_entities`
теперь возвращает ошибку и сохраняет прежний кэш. Раньше ответ был
«OK: 0 объектов», а кэш очищался.

Живая проверка: после scan вызвать анализ → `consistent_with_scan`; создать
LINE или слой без rescan → `stale` (`database_objects_created_since_scan`);
переключиться на другой DWG → `stale` (`active_document_differs`). Отдельно
подтвердить, что scan, рендер и анализ сами не меняют HANDSEED.
