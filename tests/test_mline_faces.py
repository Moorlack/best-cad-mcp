from types import SimpleNamespace

import pytest

from src.cad_controller import CADController
from src.cad_database import CADDatabase
from src.cad_tools import query_tools
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.geometry_analysis import build_geometry_report
from src.cad_understanding.polyline_parts import source_of, split_mline


def geom(vertices, just=1, scale=8, style="STANDARD"):
    return {"vertices": vertices, "mline_style": style, "mline_scale": scale, "mline_justification": just}


def faces(parts):
    return {p["handles"][0]: (p["geometry"]["start"][:2], p["geometry"]["end"][:2]) for p in parts}


@pytest.mark.parametrize("just,ys", [(0, (0, -8)), (1, (4, -4)), (2, (8, 0))])
def test_justification_places_faces_left_positive(just, ys):
    parts, excluded = split_mline("M", geom([[0, 0, 0], [100, 0, 0]], just), "id")
    assert excluded == []
    got = faces(parts)
    assert got["M#e0s0"] == ([0, ys[0]], [100, ys[0]]) and got["M#e1s0"] == ([0, ys[1]], [100, ys[1]])
    assert source_of("M#e1s0") == {"handle": "M", "element": 1, "segment_index": 0}


def test_corner_faces_are_mitered():
    parts, _ = split_mline("M", geom([[0, 0, 0], [100, 0, 0], [100, 100, 0]]), "id")
    got = faces(parts)
    # left (+4) face turns inside the corner, right (-4) face outside.
    assert got["M#e0s0"][1] == [pytest.approx(96), pytest.approx(4)]
    assert got["M#e0s1"][0] == [pytest.approx(96), pytest.approx(4)]
    assert got["M#e1s0"][1] == [pytest.approx(104), pytest.approx(-4)]


def test_unknown_style_and_missing_data_are_explicit():
    assert split_mline("M", geom([[0, 0], [1, 0]], style="WALL200"), "id")[1][0]["reason"] == \
        "mline_style_offsets_unknown"
    assert split_mline("M", geom([[0, 0], [1, 0]], just=None), "id")[1][0]["reason"] == \
        "mline_scale_or_justification_missing"
    assert split_mline("M", geom([[0, 0]]), "id")[1][0]["reason"] == "invalid_mline_vertices"


def mline(h, vertices, layer="A-WALL", **kw):
    return {"handle": h, "entity_type": "AcDbMline", "layer": layer, "geometry": geom(vertices, **kw)}


def snapshot(items):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "plan.dwg", "units": "in"},
            "sections": {"entities": {"items": items, "total": len(items)}}}


def test_mline_wall_segments_corner_and_diagnostics():
    r = build_architectural_report(snapshot([mline("M", [[0, 300, 0], [0, 0, 0], [500, 0, 0]], just=1)]),
                                   wall_thickness_range=[4, 12])
    assert [c["shape"] for c in r["candidates"]] == ["mline"]
    seg = r["wall_segment_candidates"]
    assert seg["segment_count"] == 2
    assert [j["kind"] for j in seg["junctions"]["junctions"]] == ["corner"]
    assert seg["junctions"]["junctions"][0]["point_wcs"] == [pytest.approx(0), pytest.approx(0)]
    diag = r["wall_line_diagnostics"]
    assert diag["items"] == [] and diag["same_polyline_adjacent_pairs"] == 2
    groups = sorted(g["handles"] for g in r["wall_networks"]["groups"])
    assert groups == [["M#e0s0", "M#e0s1"], ["M#e1s0", "M#e1s1"]]  # the two faces are separate lines


def test_non_wall_mline_and_generic_pairs():
    r = build_architectural_report(snapshot([mline("R", [[0, 0], [100, 0]], layer="ROAD")]))
    assert r["candidates"] == []
    pairs = build_geometry_report(snapshot([mline("R", [[0, 0], [100, 0]], layer="ROAD")]),
                                  parallel_separation_range=[4, 12])["parallel_line_pairs"]
    assert pairs["pair_count"] == 1 and pairs["pairs"][0]["separation_mean"] == pytest.approx(8)
    other = build_geometry_report(snapshot([mline("R", [[0, 0], [100, 0]], style="ROAD2")]),
                                  parallel_separation_range=[4, 12])["parallel_line_pairs"]
    assert other["excluded"] == [{"handle": "R", "reason": "mline_style_offsets_unknown"}]


class _Mline:
    ObjectName, Handle, Layer = "AcDbMline", "M1", "A-WALL"
    Coordinates = (0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
    StyleName, MLineScale, Justification = "STANDARD", 8.0, 0


def test_scan_captures_mline_data(tmp_path, monkeypatch):
    mline_entity = _Mline()
    doc = SimpleNamespace(Name="a.dwg", FullName="C:/a.dwg",
                          ModelSpace=SimpleNamespace(Count=1, Item=lambda i: mline_entity),
                          GetVariable=lambda name: 1)
    db = CADDatabase(str(tmp_path / "cad.db"))
    ctrl = object.__new__(CADController)
    ctrl.doc = doc
    ctrl.acad = SimpleNamespace(Documents=SimpleNamespace(Count=1), ActiveDocument=doc)
    monkeypatch.setattr(query_tools, "db", db)
    monkeypatch.setattr(query_tools, "ctrl", ctrl)
    monkeypatch.setattr("src.cad_controller.win32com.client.Dispatch", lambda e: e)
    query_tools.scan_all_entities()
    stored = db.get_entity("M1")["geometry"]
    assert stored["vertices"] == [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]]
    assert (stored["mline_style"], stored["mline_scale"], stored["mline_justification"]) == ("STANDARD", 8.0, 0)


DXF_STYLES = """  0
SECTION
  2
OBJECTS
  0
MLINESTYLE
  5
1A
100
AcDbMlineStyle
  2
STANDARD
 70
     0
 71
     2
 49
0.5
 62
   256
  6
BYLAYER
 49
-0.5
 62
   256
  6
BYLAYER
  0
MLINESTYLE
  5
1B
100
AcDbMlineStyle
  2
WALL3
 71
     3
 49
1.0
 49
0.0
 49
-2.0
  0
ENDSEC
  0
EOF
"""


def test_parse_mline_styles_and_face_offsets():
    from src.mline_styles import face_offsets, parse_mline_styles

    styles = parse_mline_styles(DXF_STYLES)
    assert styles == {"STANDARD": [0.5, -0.5], "WALL3": [1.0, 0.0, -2.0]}
    assert face_offsets(styles["STANDARD"], 0) == (0.0, -1.0)
    assert face_offsets(styles["STANDARD"], 2) == (1.0, 0.0)
    assert face_offsets(styles["WALL3"], 1) == (1.0, -2.0)
    assert face_offsets(styles["WALL3"], 0) == (0.0, -3.0)
    assert face_offsets([1.0], 0) is None and face_offsets([1.0, 1.0], 0) is None
    assert face_offsets([1.0, 0.0], 5) is None
    assert parse_mline_styles("") == {}


def test_custom_style_uses_scanned_offsets_for_faces():
    geometry = {"vertices": [[0, 0, 0], [100, 0, 0]], "mline_style": "WALL3", "mline_scale": 2.0,
                "mline_justification": 1, "mline_style_offsets": [1.0, 0.0, -2.0]}
    parts, excluded = split_mline("H", geometry, "g")
    assert not excluded and len(parts) == 2
    ys = sorted(round(p["geometry"]["start"][1], 6) for p in parts)
    assert ys == [-4.0, 2.0]  # outer elements +1 and -2, scaled by 2
    missing = dict(geometry)
    del missing["mline_style_offsets"]
    assert split_mline("H", missing, "g")[1][0]["reason"] == "mline_style_offsets_unknown"
    bad = dict(geometry, mline_style_offsets=[1.0, 1.0])
    assert split_mline("H", bad, "g")[1][0]["reason"] == "mline_style_offsets_invalid"


class _FakeSelectionSet:
    def __init__(self, sets):
        self.sets, self.items = sets, []

    def AddItems(self, items):
        self.items = list(items)

    def Delete(self):
        self.sets.clear()


class _FakeSelectionSets:
    def __init__(self):
        self.sets = {}

    def Item(self, name):
        raise KeyError(name)

    def Add(self, name):
        self.sets[name] = _FakeSelectionSet(self.sets)
        return self.sets[name]


class _FakeExportDocument:
    def __init__(self, dxf_text, fail=False):
        self.SelectionSets, self.dxf_text, self.fail, self.exported = _FakeSelectionSets(), dxf_text, fail, []

    def HandleToObject(self, handle):
        return handle

    def Export(self, path, fmt, selection_set):
        if self.fail:
            raise RuntimeError("export failed")
        self.exported.append(list(selection_set.items))
        open(path + ".dxf", "w", encoding="utf-8").write(self.dxf_text)


def _controller_for_attach(monkeypatch):
    from src import cad_controller

    monkeypatch.setattr(cad_controller.win32com.client, "VARIANT", lambda kind, value: value)
    return cad_controller.CADController.__new__(cad_controller.CADController)


def test_scan_attaches_style_offsets_with_one_export_per_style(monkeypatch):
    controller = _controller_for_attach(monkeypatch)
    entities = [
        {"type": "AcDbMline", "handle": "A", "mline_style": "Wall3"},
        {"type": "AcDbMline", "handle": "B", "mline_style": "WALL3"},
        {"type": "AcDbMline", "handle": "C", "mline_style": "STANDARD"},
        {"type": "AcDbLine", "handle": "D"},
    ]
    document = _FakeExportDocument(DXF_STYLES)
    controller._attach_mline_style_offsets(document, entities)
    assert document.exported == [["A"]]  # one sample per non-STANDARD style; STANDARD needs none
    assert entities[0]["mline_style_offsets"] == [1.0, 0.0, -2.0] == entities[1]["mline_style_offsets"]
    assert "mline_style_offsets" not in entities[2] and "mline_style_offsets" not in entities[3]
    assert not document.SelectionSets.sets  # temporary selection set removed


def test_scan_style_offsets_are_skipped_safely(monkeypatch):
    controller = _controller_for_attach(monkeypatch)
    entities = [{"type": "AcDbMline", "handle": "A", "mline_style": "WALL3"}]
    controller._attach_mline_style_offsets(_FakeExportDocument(DXF_STYLES, fail=True), entities)
    assert "mline_style_offsets" not in entities[0]
    only_standard = [{"type": "AcDbMline", "handle": "A", "mline_style": "STANDARD"}]
    document = _FakeExportDocument(DXF_STYLES)
    controller._attach_mline_style_offsets(document, only_standard)
    assert document.exported == []
