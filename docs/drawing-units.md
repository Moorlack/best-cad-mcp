# Единицы снимка DWG

`scan_all_entities` читает INSUNITS из того же COM-документа, что ModelSpace.
Значение хранится в SQLite по workspace_id/drawing_id, отдельно от карточки проекта.
`build_drawing_ir` и `analyze_architectural_drawing` возвращают `drawing.units`
и `drawing.units_metadata`: исходный `insunits`, `source`, `status`,
`captured_at` и `geometry_scale_verified=false`.

Примеры: 1 → in, 2 → ft, 4 → mm, 6 → m, 21 → us_survey_ft.
Ноль означает unitless, неизвестные коды и ошибки чтения — unknown.
US Survey Feet не объединяются с обычными футами. Полная таблица кодов и
ограничения платформ: [Autodesk INSUNITS](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Core/files/GUID-A58A87BB-482B-4042-A00A-EEF55A2B4FD8.htm).

INSUNITS управляет единицами вставки и не подтверждает масштаб существующих
объектов. Архитектурный отчёт сохраняет предупреждение `geometry_scale_unverified`
для объявленных единиц, `units_unverified` — для неизвестных/безразмерных.
Координаты не пересчитываются, карточка проекта не обновляется.

До первого сканирования после обновления прежние кэши возвращают unknown.
Повторный успешный скан заменяет метаданные, даже если новое чтение INSUNITS
не удалось. Ошибка всего скана оставляет прежний кэш и его время без изменений.
Кэш не является атомарным снимком редактируемого DWG: свежесть и полноту
геометрии по-прежнему нужно проверять, особенно при clear_db=false.

Обновление: существующий установщик → Repair / Extend, затем перезапуск клиента.
Новые зависимости, настройки и новый CMD не нужны.

## Промпт проверки для Codex или Claude

```text
Проверь обновление единиц AutoCAD MCP в текущем пустом DWG.
Ничего не создавай, не меняй системные переменные, не сохраняй и не закрывай DWG.
1. get_document_info: запиши имя, units и entity_count. Если DWG не пуст — останови тест.
2. scan_all_entities с clear_annotations=false, clear_understanding=false.
3. analyze_architectural_drawing: покажи drawing.units и units_metadata.
Проверь соответствие исходному INSUNITS: 1=in, 2=ft, 4=mm, 6=m,
0=unitless со status=unknown. Для остальных кодов не угадывай соответствие.
4. Проверь source=AutoCAD.INSUNITS, непустое captured_at,
geometry_scale_verified=false и предупреждение geometry_scale_unverified
(для unknown/unitless — units_unverified). Кандидатов должно быть 0.
5. Повтори get_document_info: имя, units, число объектов не изменились.
Выдай PASS/FAIL по шагам. Карточку проекта не изменяй.
Сканирование обновляет только локальный кэш MCP.
```

Код проверен синтетическими тестами контроллера, SQLite, CAD-IR и MCP;
установка через Repair и живая проверка этого обновления остаются отдельным шагом.
