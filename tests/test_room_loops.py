import pytest

from src.cad_understanding.axis_junctions import find_axis_junctions
from src.cad_understanding.room_loops import find_room_loops


def seg(seg_id, a, b, thickness=8.0):
    return {"id": seg_id, "axis_wcs": [list(a), list(b)],
            "thickness_drawing_units": {"min": thickness, "max": thickness, "mean": thickness}}


def junctions_for(segments, tolerance=None):
    found = find_axis_junctions(
        [{"id": s["id"], "start": s["axis_wcs"][0], "end": s["axis_wcs"][1],
          "width": s["thickness_drawing_units"]["max"]} for s in segments], tolerance)["junctions"]
    for junction in found:
        junction["segment_ids"] = junction.pop("ids")
    return found


def square(size=1000, gap_side=None):
    # Axes stop half a wall thickness short of the corners, like paired wall faces do.
    h = 4
    sides = [seg("S", (h, 0, 0), (size - h, 0, 0)), seg("E", (size, h, 0), (size, size - h, 0)),
             seg("N", (size - h, size, 0), (h, size, 0)), seg("W", (0, size - h, 0), (0, h, 0))]
    if gap_side == "S":  # a 36-unit door gap in the bottom wall
        sides[0:1] = [seg("S1", (h, 0, 0), (400, 0, 0)), seg("S2", (436, 0, 0), (size - h, 0, 0))]
    return sides


def test_four_walls_enclose_one_loop_with_axis_area():
    segments = square()
    result = find_room_loops(segments, junctions_for(segments))
    assert result["loop_count"] == 1
    loop = result["loops"][0]
    assert loop["area_drawing_units_squared"] == pytest.approx(1000 * 1000, rel=0.02)
    assert loop["segment_ids"] == ["E", "N", "S", "W"] and loop["closed_through_opening_gap"] is False
    assert loop["room_confirmed"] is False and result["area_basis"] == "wall_axis_polygon"
    assert loop["perimeter_drawing_units"] == pytest.approx(4000, rel=0.02)


def test_partition_wall_splits_the_loop_into_two_with_t_junctions():
    segments = square() + [seg("P", (500, 4, 0), (500, 996, 0))]
    result = find_room_loops(segments, junctions_for(segments))
    assert result["loop_count"] == 2
    areas = sorted(loop["area_drawing_units_squared"] for loop in result["loops"])
    assert areas[0] == pytest.approx(500 * 1000, rel=0.03) and areas[1] == pytest.approx(500 * 1000, rel=0.03)
    assert all("P" in loop["segment_ids"] for loop in result["loops"])


def test_open_layout_needs_the_opening_gap_to_close_a_loop():
    segments = square(gap_side="S")
    junctions = junctions_for(segments, tolerance=8)
    assert find_room_loops(segments, junctions)["loop_count"] == 0
    gap = {"id": "gap1", "segment_ids": ["S1", "S2"], "start_wcs": [400, 0], "end_wcs": [436, 0], "gap_length": 36}
    result = find_room_loops(segments, junctions, gaps=[gap])
    assert result["loop_count"] == 1
    loop = result["loops"][0]
    assert loop["closed_through_opening_gap"] is True and loop["opening_gap_ids"] == ["gap1"]
    assert loop["area_drawing_units_squared"] == pytest.approx(1000 * 1000, rel=0.02)


def test_too_few_axes_and_dangling_walls_give_no_loops():
    few = [seg("A", (0, 0, 0), (100, 0, 0)), seg("B", (100, 4, 0), (100, 100, 0))]
    assert find_room_loops(few, junctions_for(few))["loop_count"] == 0
    segments = square()[:3] + [seg("D", (0, 500, 0), (200, 500, 0))]
    assert find_room_loops(segments, junctions_for(segments))["loop_count"] == 0
    assert find_room_loops([], [])["loop_count"] == 0
