import math

import pytest

from src.dxf_entities import entity_record, iter_entities, read_dxf_entities


def dxf(*entities):
    body = []
    for kind, pairs in entities:
        body += ["0", kind] + [str(x) for pair in pairs for x in pair]
    return "\n".join(["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1032", "0", "ENDSEC",
                      "0", "SECTION", "2", "ENTITIES", *body, "0", "ENDSEC", "0", "EOF"]) + "\n"


LINE = ("LINE", [(5, "2C1"), (8, "A-WALL"), (10, 0), (20, 0), (30, 0), (11, 100), (21, 0), (31, 0)])
CIRCLE = ("CIRCLE", [(5, "2C2"), (8, "A-COL"), (62, 1), (10, 250), (20, 500), (30, 0), (40, 10)])
ARC = ("ARC", [(5, "2C3"), (8, "0"), (6, "DASHED"), (10, 400), (20, 0), (30, 0), (40, 36), (50, 0), (51, 90)])
POLY = ("LWPOLYLINE", [(5, "2C4"), (8, "\\U+0421\\U+0442\\U+0435\\U+043D\\U+044B"), (90, 4), (70, 1),
                       (10, 0), (20, 200), (42, 1), (10, 200), (20, 200), (10, 200), (20, 400), (10, 0), (20, 400)])
INSERT = ("INSERT", [(5, "2C5"), (8, "A-DOOR"), (66, 1), (2, "DOOR"), (10, 1), (20, 2), (30, 0)])
ATTRIB = ("ATTRIB", [(5, "2C6"), (8, "A-DOOR"), (1, "D1")])
SEQEND = ("SEQEND", [(5, "2C7"), (8, "A-DOOR")])
TILTED = ("CIRCLE", [(5, "2C8"), (8, "0"), (10, 0), (20, 0), (30, 0), (40, 5), (210, 0), (220, 0), (230, -1)])


def test_entities_section_is_split_into_top_level_entities():
    kinds = [kind for kind, _ in iter_entities(dxf(LINE, INSERT, ATTRIB, SEQEND, CIRCLE))]
    assert kinds == ["LINE", "INSERT", "CIRCLE"]  # attributes belong to their insert


def test_records_match_the_com_scan_shape():
    records, com_handles, order = read_dxf_entities(dxf(LINE, CIRCLE, ARC, POLY, INSERT, ATTRIB, SEQEND, TILTED))
    assert order == ["2C1", "2C2", "2C3", "2C4", "2C5", "2C8"]
    assert com_handles == ["2C5", "2C8"]  # insert and non-plan circle go to COM
    line = records["2C1"]
    assert line == {"handle": "2C1", "type": "AcDbLine", "name": "Line", "layer": "A-WALL", "color": 256,
                    "linetype": "ByLayer", "start": [0.0, 0.0, 0.0], "end": [100.0, 0.0, 0.0], "length": 100.0,
                    "bbox": [0.0, 0.0, 100.0, 0.0]}
    circle = records["2C2"]
    assert circle["color"] == 1 and circle["center"] == [250.0, 500.0, 0.0] and circle["radius"] == 10.0
    assert circle["bbox"] == [240.0, 490.0, 260.0, 510.0]
    arc = records["2C3"]
    assert arc["linetype"] == "DASHED" and arc["start"] == [436.0, 0.0, 0.0] and arc["end"] == [400.0, 36.0, 0.0]
    assert arc["start_angle"] == 0.0 and arc["end_angle"] == pytest.approx(math.pi / 2)
    assert arc["bbox"] == [400.0, 0.0, 436.0, 36.0]
    poly = records["2C4"]
    assert poly["layer"] == "Стены" and poly["closed"] is True and poly["bulges"] == [1.0, 0.0, 0.0, 0.0]
    assert poly["length"] == pytest.approx(600 + math.pi * 100)
    assert poly["bbox"] == pytest.approx([0.0, 100.0, 200.0, 400.0])  # bulge below the first edge
    assert poly["vertices"][0] == [0.0, 200.0, 0.0] and poly["vertices_coordinate_system"] == "WCS"


def test_reading_flags_and_visual_path_callback():
    calls = []
    records, _, _ = read_dxf_entities(dxf(LINE, POLY), read_common=False, read_geometry=False, include_bbox=False,
                                      visual_path=lambda *a: calls.append(a) or [[0, 0, 0]])
    assert records["2C1"] == {"handle": "2C1", "type": "AcDbLine", "name": "Line", "layer": "A-WALL"}
    assert calls == []  # no geometry requested
    records, _, _ = read_dxf_entities(dxf(POLY), visual_path=lambda *a: calls.append(a) or [[0, 0, 0]])
    assert records["2C4"]["visual_path"] == [[0, 0, 0]] and calls[0][2] is True
    assert entity_record("SPLINE", [("5", "1")], True, True, True) is None


INSERT_ATTRS = ("INSERT", [(5, "3A"), (100, "AcDbEntity"), (8, "A-DOOR"), (62, 3), (100, "AcDbBlockReference"),
                           (66, 1), (2, "DOOR"), (10, 200), (20, 0), (30, 0), (41, 2), (42, -1), (50, 30)])
ATTRIB_NUM = ("ATTRIB", [(5, "3B"), (100, "AcDbText"), (1, r"\U+0414\U+0432\U+0435\U+0440\U+044C 7"),
                         (100, "AcDbAttribute"), (2, "NUM"), (70, 0)])
ATTRIB_HID = ("ATTRIB", [(5, "3C"), (100, "AcDbText"), (1, "secret"), (100, "AcDbAttribute"), (2, "HID"), (70, 1)])
SEQ = ("SEQEND", [(5, "3D"), (8, "A-DOOR")])
TEXT = ("TEXT", [(5, "40"), (100, "AcDbEntity"), (8, "A-ANNO"), (100, "AcDbText"), (10, 0), (20, 0), (30, 0),
                 (40, 2.5), (1, "Room %%c"), (100, "AcDbText")])
MTEXT = ("MTEXT", [(5, "41"), (100, "AcDbEntity"), (8, "0"), (100, "AcDbMText"), (3, "first part "), (1, r"end\P")])
MLINE = ("MLINE", [(5, "42"), (100, "AcDbEntity"), (8, "A-WALL"), (100, "AcDbMline"), (2, "WALL3"), (40, 2.5),
                   (70, 1), (10, 0), (20, 0), (30, 0), (11, 0), (21, 0), (31, 0), (11, 100), (21, 0), (31, 0)])
HATCH = ("HATCH", [(5, "43"), (100, "AcDbEntity"), (8, "A-HATCH"), (100, "AcDbHatch"), (2, "SOLID")])
SOLID = ("SOLID", [(5, "44"), (100, "AcDbEntity"), (8, "0"), (100, "AcDbTrace")])
MINSERT = ("INSERT", [(5, "45"), (100, "AcDbEntity"), (8, "0"), (100, "AcDbMInsertBlock"), (2, "X"), (70, 3)])


def test_attributes_stay_with_their_insert_and_partial_records_cover_blocks_texts_mlines():
    entities = list(iter_entities(dxf(INSERT_ATTRS, ATTRIB_NUM, ATTRIB_HID, SEQ, TEXT)))
    assert [kind for kind, _ in entities] == ["INSERT", "TEXT"]
    partials = {}
    records, com_handles, order = read_dxf_entities(dxf(INSERT_ATTRS, ATTRIB_NUM, ATTRIB_HID, SEQ, TEXT, MTEXT,
                                                        MLINE, HATCH, SOLID, MINSERT), partials=partials)
    assert records == {} and com_handles == order == ["3A", "40", "41", "42", "43", "44", "45"]
    assert set(partials) == {"3A", "40", "41", "42", "43"}  # SOLID marker differs from COM, MINSERT is an array
    block = partials["3A"]
    assert block["type"] == "AcDbBlockReference" and block["color"] == 3 and block["layer"] == "A-DOOR"
    geometry = block["geometry"]
    assert geometry["block_name"] == "DOOR" and geometry["insertion_point"] == [200.0, 0.0, 0.0]
    assert geometry["rotation"] == pytest.approx(math.pi / 6) and geometry["x_scale"] == 2.0
    assert geometry["y_scale"] == -1.0 and geometry["z_scale"] == 1.0 and geometry["visible"] is True
    assert block["attributes"] == [
        {"Handle": "3B", "TagString": "NUM", "TextString": "Дверь 7", "Invisible": False},
        {"Handle": "3C", "TagString": "HID", "TextString": "secret", "Invisible": True}]
    assert partials["40"]["geometry"] == {"text": "Room %%c"}
    assert partials["41"]["geometry"] == {"text": r"first part end\P"}
    assert partials["42"]["geometry"] == {"vertices": [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]], "mline_style": "WALL3",
                                          "mline_scale": 2.5, "mline_justification": 1}
    assert partials["43"]["geometry"] is None and partials["43"]["type"] == "AcDbHatch"


def test_partial_geometry_is_left_to_com_when_dxf_cannot_reproduce_it():
    from src.dxf_entities import partial_record
    tilted = ("INSERT", INSERT_ATTRS[1] + [(210, 0), (220, 0), (230, -1)])
    long_attr = ("ATTRIB", ATTRIB_NUM[1] + [(3, "more text")])
    partials = {}
    read_dxf_entities(dxf(tilted), partials=partials)
    assert partials["3A"]["geometry"] is None
    kinds = list(iter_entities(dxf(INSERT_ATTRS, long_attr, SEQ)))
    assert partial_record(*kinds[0])["geometry"] is None



def dxf_with_blocks(blocks, entities=(), ltypes=("ByBlock", "ByLayer", "Continuous")):
    tables = ["0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LTYPE"]
    for name in ltypes:
        tables += ["0", "LTYPE", "2", name, "70", "0"]
    tables += ["0", "ENDTAB", "0", "ENDSEC"]
    body = ["0", "SECTION", "2", "BLOCKS"]
    for name, flags, base, items in blocks:
        body += ["0", "BLOCK", "2", name, "70", str(flags), "10", str(base[0]), "20", str(base[1]), "30", "0"]
        for kind, pairs in items:
            body += ["0", kind] + [str(x) for pair in pairs for x in pair]
        body += ["0", "ENDBLK"]
    body += ["0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for kind, pairs in entities:
        body += ["0", kind] + [str(x) for pair in pairs for x in pair]
    body += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(tables + body) + "\n"


def test_block_definitions_match_the_com_reader_format():
    from src.dxf_entities import block_definitions
    door = [("LINE", [(8, "A-DOOR"), (10, 0), (20, 0), (30, 0), (11, 36), (21, 0), (31, 0)]),
            ("ARC", [(8, "A-DOOR"), (10, 0), (20, 0), (30, 0), (40, 36), (50, 0), (51, 90)]),
            ("ATTDEF", [(8, "0"), (2, "TAG")])]
    tilted = [("ARC", [(10, 0), (20, 0), (30, 0), (40, 5), (50, 0), (51, 90), (210, 1), (220, 0), (230, 0)])]
    text = dxf_with_blocks([("DOOR", 0, (5, 6), door), ("BASE", 4, (0, 0), []), ("ROT", 0, (0, 0), tilted),
                            ("*Model_Space", 0, (0, 0), [])])
    found = block_definitions(text, 500, 300, 16)
    assert found["DOOR"] == {"arcs": [{"center": [0.0, 0.0, 0.0], "start": [36.0, 0.0, 0.0], "end": [0.0, 36.0, 0.0],
                                       "normal": [0.0, 0.0, 1.0]}],
                             "lines": [{"start": [0.0, 0.0, 0.0], "end": [36.0, 0.0, 0.0], "layer": "A-DOOR"}],
                             "entity_count": 3, "truncated": False, "origin": [5.0, 6.0, 0.0]}
    assert found["BASE"] is None and found["*Model_Space"] is None and "ROT" not in found  # xref / layout / COM


def test_linetype_spelling_follows_the_drawing_and_dimensions_come_from_dxf():
    from src.dxf_entities import read_dxf_entities
    dim = ("DIMENSION", [(5, "D1"), (100, "AcDbEntity"), (8, "DIM"), (100, "AcDbDimension"), (1, ""), (42, 120.5),
                         (100, "AcDbAlignedDimension"), (13, 0), (23, 0), (33, 0), (14, 0), (24, 120.5), (34, 0),
                         (50, 90), (100, "AcDbRotatedDimension")])
    old = dxf_with_blocks([], [LINE, dim], ltypes=("BYBLOCK", "BYLAYER", "CONTINUOUS"))
    partials = {}
    records, _, _ = read_dxf_entities(old, partials=partials)
    assert records["2C1"]["linetype"] == "BYLAYER" and partials["D1"]["linetype"] == "BYLAYER"
    assert partials["D1"]["geometry"] == {"measurement": 120.5, "xline1_point": [0.0, 0.0, 0.0],
                                          "xline2_point": [0.0, 120.5, 0.0], "text_override": "",
                                          "dimension_rotation": pytest.approx(math.pi / 2)}
    new = dxf_with_blocks([], [LINE])
    assert read_dxf_entities(new)[0]["2C1"]["linetype"] == "ByLayer"
