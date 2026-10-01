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
