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
    assert loop["area_drawing_units_squared"] == pytest.approx(1000 * 1000, rel=0.001)
    assert loop["segment_ids"] == ["E", "N", "S", "W"] and loop["closed_through_opening_gap"] is False
    assert loop["room_confirmed"] is False and result["area_basis"] == "wall_axis_polygon"
    assert loop["perimeter_drawing_units"] == pytest.approx(4000, rel=0.001)


def test_partition_wall_splits_the_loop_into_two_with_t_junctions():
    segments = square() + [seg("P", (500, 4, 0), (500, 996, 0))]
    result = find_room_loops(segments, junctions_for(segments))
    assert result["loop_count"] == 2
    areas = sorted(loop["area_drawing_units_squared"] for loop in result["loops"])
    assert areas[0] == pytest.approx(500 * 1000, rel=0.001) and areas[1] == pytest.approx(500 * 1000, rel=0.001)
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
    assert loop["area_drawing_units_squared"] == pytest.approx(1000 * 1000, rel=0.001)


def test_too_few_axes_and_dangling_walls_give_no_loops():
    few = [seg("A", (0, 0, 0), (100, 0, 0)), seg("B", (100, 4, 0), (100, 100, 0))]
    assert find_room_loops(few, junctions_for(few))["loop_count"] == 0
    segments = square()[:3] + [seg("D", (0, 500, 0), (200, 500, 0))]
    assert find_room_loops(segments, junctions_for(segments))["loop_count"] == 0
    assert find_room_loops([], [])["loop_count"] == 0


def test_net_area_insets_each_edge_by_half_the_wall_thickness():
    segments = square()
    (loop,) = find_room_loops(segments, junctions_for(segments))["loops"]
    assert loop["area_drawing_units_squared"] == pytest.approx(1000 * 1000, rel=0.001)
    assert loop["net_area_drawing_units_squared"] == pytest.approx(992 * 992, rel=0.001)
    xs = sorted({round(p[0]) for p in loop["net_polygon_wcs"]})
    assert xs == [4, 996]
    assert loop["net_area_basis"].startswith("axis polygon moved inward")
    assert loop["columns_inside"] == []


def test_net_area_handles_partition_walls_and_different_thicknesses():
    segments = square() + [seg("P", (500, 4, 0), (500, 996, 0), thickness=20.0)]
    result = find_room_loops(segments, junctions_for(segments))
    areas = sorted(loop["net_area_drawing_units_squared"] for loop in result["loops"])
    # Left room: 1000 wide axis box inset 4 on the outer walls and 10 at the partition -> 486 x 992.
    assert areas[0] == pytest.approx(486 * 992, rel=0.002) and areas[1] == pytest.approx(486 * 992, rel=0.002)


def test_columns_inside_a_loop_are_subtracted_from_the_net_area():
    import math

    segments = square()
    columns = [
        {"handles": ["C1"], "shape": "circle", "geometry": {"radius": 10.0},
         "bbox": {"center": [250.0, 500.0], "width": 20.0, "height": 20.0}},
        {"handles": ["C2"], "shape": "closed_polyline", "boundary_check": {
            "status": "valid_simple_polygon", "geometric_area_drawing_units_squared": 400.0},
         "bbox": {"center": [700.0, 300.0], "width": 20.0, "height": 20.0}},
        {"handles": ["OUT"], "shape": "circle", "geometry": {"radius": 5.0},
         "bbox": {"center": [5000.0, 5000.0], "width": 10.0, "height": 10.0}},
        {"handles": ["BAD"], "shape": "block_reference", "bbox": {}},
    ]
    (loop,) = find_room_loops(segments, junctions_for(segments), columns=columns)["loops"]
    assert [c["handle"] for c in loop["columns_inside"]] == ["C1", "C2"]
    assert loop["columns_inside"][0]["area_basis"] == "circle"
    net = loop["net_area_drawing_units_squared"]
    assert loop["net_area_minus_columns_drawing_units_squared"] == pytest.approx(net - math.pi * 100 - 400)


def test_loop_inside_another_loop_is_reported_as_an_enclosed_void():
    outer = square(2000)
    inner = [seg("IS", (904, 1000, 0), (1096, 1000, 0)), seg("IE", (1100, 1004, 0), (1100, 1196, 0)),
             seg("IN", (1096, 1200, 0), (904, 1200, 0)), seg("IW", (900, 1196, 0), (900, 1004, 0))]
    segments = outer + inner
    loops = find_room_loops(segments, junctions_for(segments))["loops"]
    big = max(loops, key=lambda loop: loop["area_drawing_units_squared"])
    small = min(loops, key=lambda loop: loop["area_drawing_units_squared"])
    assert len(loops) == 2 and big["enclosed_loop_ids"] == [small["id"]] and small["enclosed_loop_ids"] == []
    assert big["net_area_minus_enclosed_loops_drawing_units_squared"] == pytest.approx(
        big["net_area_drawing_units_squared"] - small["area_drawing_units_squared"])
