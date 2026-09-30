"""Find and choose among several running AutoCAD instances.

AutoCAD verticals (e.g. Civil 3D 2025) register the same COM ProgID as plain
AutoCAD 2025, and GetActiveObject returns whichever registered first. Picking
that one silently can write into an unrelated drawing, so with several
instances the choice must be explicit: a pinned process id, a drawing path, or
the only instance running. Otherwise selection fails closed.
"""

import time
import os


class AmbiguousAutoCADInstances(RuntimeError):
    """Several AutoCAD instances are running and nothing identifies the target."""


def _norm(path):
    return os.path.normcase(os.path.normpath(str(path))) if path else ""


def choose_instance(instances, pinned_pid=None, document_path=None, process_pids=None):
    """Pure selection over [{pid, documents, ...}]; returns one instance or None when none run.

    process_pids: AutoCAD process ids seen by the OS. Processes that COM enumeration
    missed (observed live for Civil 3D) still count, so a single reachable instance is
    not mistaken for the only one.
    """
    if pinned_pid is not None:
        for inst in instances:
            if inst.get("pid") == pinned_pid:
                return inst
        if process_pids and pinned_pid in process_pids:
            raise RuntimeError(f"AutoCAD process {pinned_pid} is running but not reachable through COM "
                               "(busy, a modal dialog, or not registered); retry later or choose another.")
        raise RuntimeError(f"The selected AutoCAD process {pinned_pid} is no longer running; "
                           "call select_autocad_instance again.")
    if document_path:
        target = _norm(document_path)
        matches = [i for i in instances if target in {_norm(d) for d in i.get("documents", [])}]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise RuntimeError(f"No running AutoCAD instance has {document_path} open.")
    unreachable = sorted(set(process_pids or ()) - {i.get("pid") for i in instances})
    if len(instances) + len(unreachable) <= 1:
        return instances[0] if instances else None
    listing = "; ".join(
        [f"pid {i.get('pid')}: {', '.join(os.path.basename(d) for d in i.get('documents', [])) or 'no documents'}"
         for i in instances]
        + [f"pid {pid}: not reachable through COM right now" for pid in unreachable])
    raise AmbiguousAutoCADInstances(
        f"{len(instances) + len(unreachable)} AutoCAD instances are running ({listing}). Call "
        "select_autocad_instance with a pid or document_path, or set CAD_MCP_AUTOCAD_DOCUMENT, before working.")


def acad_process_pids():
    """acad.exe process ids from the OS (independent of COM registration); None if unknown."""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq acad.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return None
    return parse_tasklist_csv(out)


def parse_tasklist_csv(out):
    pids = set()
    for line in out.splitlines():
        cells = [c.strip('"') for c in line.strip().split('","')]
        if len(cells) > 1 and cells[0].lower() == "acad.exe" and cells[1].isdigit():
            pids.add(int(cells[1]))
    return pids


def _pid_of(app):
    try:
        import win32process
        return win32process.GetWindowThreadProcessId(int(app.HWND))[1]
    except Exception:
        return None


def _documents_of(app):
    try:
        docs = app.Documents
        return [str(docs.Item(i).FullName or docs.Item(i).Name) for i in range(int(docs.Count))], None
    except Exception as exc:  # a busy instance rejects calls; keep it listed
        return [], f"{type(exc).__name__}: {exc}"


def _safe(app, attribute, default):
    try:
        return str(getattr(app, attribute))
    except Exception:
        return default


def list_instances(prog_ids):
    """Running AutoCAD applications from the Running Object Table, deduplicated by process."""
    import pythoncom
    import pywintypes
    import win32com.client

    clsids = set()
    for prog_id in prog_ids:
        try:
            clsids.add(str(pywintypes.IID(prog_id)).lower())
        except Exception:
            continue
    rot = pythoncom.GetRunningObjectTable()
    ctx = pythoncom.CreateBindCtx(0)
    found = {}
    for moniker in rot.EnumRunning():
        try:
            name = str(moniker.GetDisplayName(ctx, None))
        except Exception:
            continue
        key = name.strip("!").lower()
        is_app = key in clsids
        is_dwg = name.lower().endswith((".dwg", ".dwt"))
        if not (is_app or is_dwg):
            continue
        try:
            obj = win32com.client.Dispatch(rot.GetObject(moniker).QueryInterface(pythoncom.IID_IDispatch))
            app = obj if is_app else obj.Application
        except Exception:
            continue
        pid = _pid_of(app)
        key = pid if pid is not None else f"unknown-{len(found)}"
        if key in found:
            continue
        documents, error = _documents_of(app)
        found[key] = {"pid": pid, "app": app, "documents": documents, "error": error,
                      "name": _safe(app, "Name", "AutoCAD"), "version": _safe(app, "Version", "")}
    return list(found.values())


def describe(instances):
    return [{k: v for k, v in inst.items() if k != "app"} for inst in instances]


def activate_document(app, document_path, attempts=10):
    """Make the open drawing whose FullName (or, when unsaved, Name) matches the active one.

    Selecting an instance by document path must also select that drawing, otherwise later
    tools act on whichever drawing happens to be active. Returns True when it is active.
    """
    if not document_path:
        return False
    target = _norm(document_path)
    try:
        documents = app.Documents
        for index in range(int(documents.Count)):
            document = documents.Item(index)
            names = {_norm(getattr(document, "FullName", "") or ""), _norm(getattr(document, "Name", "") or "")}
            if target in names:
                document.Activate()
                for _ in range(attempts):
                    active = app.ActiveDocument
                    if _norm(getattr(active, "FullName", "") or getattr(active, "Name", "")) in names:
                        return True
                    time.sleep(0.1)
                return False
    except Exception:
        return False
    return False
