import pytest

from src.cad_understanding.architecture import build_architectural_report


def line(h, a, b, layer="A-WALL"):
    return {"handle": h, "entity_type": "AcDbLine", "layer": layer, "geometry": {"start": a, "end": b}}


def plan(thickness=200.0, gap=900.0):
    """Two rooms 5000 wide with walls `thickness` thick and one door gap in the bottom wall."""
    t = thickness / 2
    items = []
    # bottom wall with a door gap between x=1000 and 1000+gap
    for i, (x0, x1) in enumerate(((t, 1000.0), (1000.0 + gap, 10000.0 - t))):
        items += [line(f"B{i}a", [x0, -t, 0], [x1, -t, 0]), line(f"B{i}b", [x0, t, 0], [x1, t, 0])]
    items += [line("Ta", [t, 5000 - t, 0], [10000 - t, 5000 - t, 0]), line("Tb", [t, 5000 + t, 0], [10000 - t, 5000 + t, 0]),
              line("La", [-t, t, 0], [-t, 5000 - t, 0]), line("Lb", [t, t, 0], [t, 5000 - t, 0]),
              line("Ra", [10000 - t, t, 0], [10000 - t, 5000 - t, 0]), line("Rb", [10000 + t, t, 0], [10000 + t, 5000 - t, 0]),
              line("Pa", [5000 - t, t, 0], [5000 - t, 5000 - t, 0]), line("Pb", [5000 + t, t, 0], [5000 + t, 5000 - t, 0])]
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg", "units": "mm"},
            "sections": {"entities": {"total": len(items), "items": items}}}


def test_auto_thickness_and_opening_width_pair_the_walls_and_find_the_gap():
    report = build_architectural_report(plan(), wall_thickness_range="auto", wall_opening_max_width="auto")
    estimate = report["wall_thickness_estimate"]
    assert estimate["peak_drawing_units"] == pytest.approx(200.0)
    assert estimate["range_drawing_units"] == pytest.approx([160.0, 250.0])
    walls = report["wall_segment_candidates"]
    assert walls["segment_count"] == 6
    assert [g["gap_length"] for g in walls["openings"]["gaps"]] == [pytest.approx(900.0)]
    assert walls["room_loops"]["loop_count"] == 2
    assert "wall_parameters_estimated" in {i["code"] for i in report["issues"]}


def test_auto_without_wall_pairs_reports_and_skips_pairing():
    ir = {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg"}, "sections": {"entities": {"total": 1, "items": [
        line("A", [0, 0, 0], [100, 0, 0])]}}}
    report = build_architectural_report(ir, wall_thickness_range="auto")
    assert report["wall_thickness_estimate"] is None
    assert report["wall_segment_candidates"]["requested"] is False
    assert "wall_thickness_not_estimated" in {i["code"] for i in report["issues"]}


def test_invalid_auto_combinations_are_rejected():
    with pytest.raises(ValueError):
        build_architectural_report(plan(), wall_opening_max_width="auto")
    with pytest.raises(ValueError):
        build_architectural_report(plan(), wall_thickness_range="automatic")


def test_periodic_parallel_lines_do_not_win_over_wall_faces():
    ir = plan()
    stack = [line(f"H{i}", [20000, i * 60.0, 0], [21000, i * 60.0, 0]) for i in range(40)]  # hatch-like stack
    ir["sections"]["entities"]["items"] += stack
    ir["sections"]["entities"]["total"] += len(stack)
    report = build_architectural_report(ir, wall_thickness_range="auto")
    assert report["wall_thickness_estimate"]["peak_drawing_units"] == pytest.approx(200.0)


def test_several_wall_types_give_several_peaks_and_a_range_covering_them():
    thin, thick = plan(200.0), plan(400.0)
    shifted = []
    for e in thick["sections"]["entities"]["items"]:
        g = e["geometry"]
        shifted.append(line("X" + e["handle"], [g["start"][0], g["start"][1] + 20000, 0],
                            [g["end"][0], g["end"][1] + 20000, 0]))
    thin["sections"]["entities"]["items"] += shifted
    thin["sections"]["entities"]["total"] += len(shifted)
    report = build_architectural_report(thin, wall_thickness_range="auto", wall_opening_max_width="auto")
    estimate = report["wall_thickness_estimate"]
    assert sorted(p["thickness_drawing_units"] for p in estimate["peaks"]) == [pytest.approx(200.0), pytest.approx(400.0)]
    assert estimate["range_drawing_units"] == pytest.approx([160.0, 500.0])
    assert estimate["suggested_opening_max_width_drawing_units"] == pytest.approx(4800.0)
    assert report["wall_segment_candidates"]["segment_count"] == 12
    assert report["wall_segment_candidates"]["room_loops"]["loop_count"] == 4


def test_a_minor_separation_is_not_a_wall_type():
    ir = plan(200.0)
    # one short pair of faces 50 apart: far below the 15% length share
    ir["sections"]["entities"]["items"] += [line("Sa", [20000, 0, 0], [20100, 0, 0]), line("Sb", [20000, 50, 0], [20100, 50, 0])]
    estimate = build_architectural_report(ir, wall_thickness_range="auto")["wall_thickness_estimate"]
    assert [p["thickness_drawing_units"] for p in estimate["peaks"]] == [pytest.approx(200.0)]
