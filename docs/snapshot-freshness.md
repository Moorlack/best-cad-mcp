# Свежесть снимка после scan

`analyze_geometry` и `analyze_architectural_drawing` читают кэш последнего scan.
Раньше `source.freshness` всегда был `unverified`. Теперь полный scan запоминает
слепок документа, а оба инструмента сравнивают его с живым AutoCAD:

| Поле слепка | Что ловит |
| --- | --- |
| путь документа (`FullName`) | активен другой DWG |
| число объектов ModelSpace | объекты добавлены или удалены |
| handle последнего объекта ModelSpace | удаление одного и создание другого при том же числе объектов |
| `HANDSEED` (необязательно) | созданы любые объекты базы; AutoCAD 2025 отказывает в `GetVariable("HANDSEED")`, тогда поле пустое и не сравнивается |

Статусы в `source.freshness` (подробности — `source.freshness_check`):

- `consistent_with_scan` — всё совпало. Перемещения и правки свойств
  существующих объектов этот слепок **не** меняют, поэтому это не доказательство
  актуальности; предупреждение `snapshot_existing_object_edits_not_detected`.
- `stale` — причина `active_document_differs`, `model_space_object_count_changed`,
  `model_space_last_entity_changed` или `database_objects_created_since_scan`; предупреждение/issue `snapshot_stale`.
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

Живая проверка 2026-09-29 (установленный `3083eb3`, AutoCAD 2025, TEST2.dwg): слепок
сохраняется и читается, путь и число объектов совпали, но `GetVariable("HANDSEED")`
вернул ошибку, и из-за обязательного HANDSEED статус был `unverified`
(`fingerprint_incomplete`). Исправлено: HANDSEED необязателен, добавлен handle
последнего объекта. Сценарий следующей проверки: после scan анализ →
`consistent_with_scan`; LINE без rescan → `stale` (`model_space_object_count_changed`);
новый слой без rescan при недоступном HANDSEED не обнаруживается (ограничение).
