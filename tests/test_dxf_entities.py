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
