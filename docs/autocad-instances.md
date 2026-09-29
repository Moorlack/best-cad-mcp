# Несколько запущенных AutoCAD

AutoCAD и его вертикали (Civil 3D 2025 и др.) регистрируют один COM ProgID, и
`GetActiveObject` отдаёт первый запущенный экземпляр. MCP мог молча работать не в
том DWG. С 2026-09-29 подключение выбирает экземпляр явно (`src/autocad_instances.py`):

1. закреплённый процесс (`select_autocad_instance(pid=...)` или `document_path=...`);
2. переменная окружения `CAD_MCP_AUTOCAD_DOCUMENT` — полный путь открытого DWG;
3. единственный запущенный экземпляр;
4. иначе — отказ `AmbiguousAutoCADInstances` со списком pid и открытых чертежей.
   Инструменты возвращают это сообщение (`Unable to connect to AutoCAD. …`),
   preflight показывает его в `autocad_com_live`; ожидание 6 с не выполняется.

Живой тест показал, что ROT может перестать показывать работающий Civil 3D, поэтому
выбор дополнительно сверяется с процессами ОС (`tasklist`, `acad.exe`): процесс без
COM-записи считается отдельным экземпляром, и без явного выбора подключение
отклоняется («not reachable through COM right now»).

Экземпляры находятся в Running Object Table: объекты приложений по CLSID всех
AutoCAD ProgID и открытые DWG по file moniker (`doc.Application`), дедупликация по
pid (`HWND` → процесс). Если перечисление ROT недоступно, остаётся прежний
`GetActiveObject` (записывается в лог). Занятый экземпляр (открытый диалог) остаётся
в списке с `error`, без документов.

Инструменты: `list_autocad_instances` (только чтение) и
`select_autocad_instance(pid | document_path | clear)` — закрепление на сессию MCP,
чертежи не меняются. Закреплённый pid после закрытия процесса даёт явную ошибку.

Живая проверка (обязательно в таком порядке, без записи до подтверждения): Civil 3D с
рабочим DWG и AutoCAD с TEST2 → `check_runtime_environment(check_autocad=True)`
должен сообщить о двух экземплярах; `list_autocad_instances` — оба pid и чертежи;
`select_autocad_instance(document_path=<TEST2>)`; `get_document_info` → TEST2.dwg;
только после этого тестовые изменения в TEST2.
