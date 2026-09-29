import asyncio
from unittest.mock import patch

import pytest
from mcp import Client

from src import server
from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.axis_junctions import find_axis_junctions
from src.cad_understanding.geometry_analysis import build_geometry_report


def axis(i, a, b, w=8):
    return {"id": i, "start": a, "end": b, "width": w}


def kinds(result):
    return sorted((tuple(j["ids"]), j["kind"]) for j in result["junctions"])


def test_corner_t_crossing_and_far_axes():
    r = find_axis_junctions([
        axis("H", [0, 4], [500, 4]),          # horizontal wall, faces y=0/8
        axis("V", [4, 8], [4, 300]),          # L corner at the left end, axis stops t/2 short
        axis("T", [204, 8], [204, 300]),      # butts into H's face -> T
        axis("X", [300, -100], [300, 100]),   # crosses H in the middle
        axis("F", [700, 0], [700, 300]),      # far away
    ])
    assert kinds(r) == [(("H", "T"), "t_junction"), (("H", "V"), "corner"), (("H", "X"), "crossing")]
    corner = next(j for j in r["junctions"] if j["kind"] == "corner")
    assert corner["point_wcs"] == [pytest.approx(4), pytest.approx(4)]
    assert corner["angle_degrees"] == pytest.approx(90)
    assert corner["positions"] == ["end", "end"] and corner["axis_overshoot"][1] == pytest.approx(4)
    assert r["tolerance_rule"] == "larger_width" and r["coverage_complete"]


def test_collinear_gap_and_parallel_overlap():
    r = find_axis_junctions([
        axis("A", [0, 4], [100, 4]),
        axis("B", [106, 4], [200, 4]),        # 6 gap on the same axis
        axis("C", [300, 4], [400, 4]),        # gap 100 > tolerance
        axis("D", [0, 7.5], [100, 7.5]),      # overlapping parallel axis 3.5 away (shared face)
    ])
    got = {tuple(j["ids"]): j for j in r["junctions"]}
    assert got[("A", "B")]["kind"] == "collinear_gap" and got[("A", "B")]["gap_length"] == pytest.approx(6)
    assert got[("A", "D")]["kind"] == "parallel_overlap"
    assert got[("A", "D")]["lateral_offset"] == pytest.approx(3.5)
    assert ("A", "C") not in got and ("B", "C") not in got


def test_explicit_tolerance_and_validation():
    items = [axis("H", [0, 4], [500, 4]), axis("V", [20, 8], [20, 300])]
    assert kinds(find_axis_junctions(items)) == [(("H", "V"), "t_junction")]
    assert kinds(find_axis_junctions(items, tolerance=30)) == [(("H", "V"), "corner")]
    far = [axis("H", [0, 4], [500, 4]), axis("V", [4, 30], [4, 300])]
    assert find_axis_junctions(far)["junction_count"] == 0
    assert find_axis_junctions(far, tolerance=40)["junction_count"] == 1
    for bad in (0, -1, float("nan"), "5", True):
        with pytest.raises(ValueError, match="junction_tolerance"):
            find_axis_junctions(items, tolerance=bad)
    r = find_axis_junctions(items + [axis("Z", [1, 1], [1, 1])])
    assert r["skipped_axes"] == ["Z"] and not r["coverage_complete"]


def line(h, a, b, layer="A-WALL"):
    return {"handle": h, "entity_type": "AcDbLine", "layer": layer, "geometry": {"start": a, "end": b}}


def snapshot(items):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg", "units": "mm"},
            "sections": {"entities": {"items": items, "total": len(items)}}}


# L-shaped wall 8 thick: outer faces y=0 / x=0, inner faces y=8 / x=8.
L_WALL = [line("H0", [0, 0], [500, 0]), line("H1", [8, 8], [500, 8]),
          line("V0", [0, 0], [0, 300]), line("V1", [8, 8], [8, 300])]


def test_wall_segments_report_corner():
    seg = build_architectural_report(snapshot(L_WALL), wall_thickness_range=[4, 12])["wall_segment_candidates"]
    assert seg["segment_count"] == 2
    j = seg["junctions"]
    assert j["junction_count"] == 1
    corner = j["junctions"][0]
    assert corner["kind"] == "corner" and sorted(corner["segment_ids"]) == sorted(s["id"] for s in seg["segments"])
    assert corner["point_wcs"] == [pytest.approx(4), pytest.approx(4)]
    with pytest.raises(ValueError, match="wall_junction_tolerance"):
        build_architectural_report(snapshot(L_WALL), wall_thickness_range=[4, 12], wall_junction_tolerance=0)


def test_generic_pairs_report_same_junction_without_wall_names():
    items = [dict(e, layer="PART") for e in L_WALL]
    pairs = build_geometry_report(snapshot(items), parallel_separation_range=[4, 12])["parallel_line_pairs"]
    assert pairs["pair_junctions"]["junction_count"] == 1
    assert pairs["pair_junctions"]["junctions"][0]["kind"] == "corner"
    assert "wall" not in str(pairs["pair_junctions"]).lower()


def test_native_mcp_passes_junction_tolerances():
    async def exercise():
        async with Client(server.mcp) as client:
            await client.call_tool("analyze_geometry", {"parallel_separation_range": [1, 2], "junction_tolerance": 3})
            await client.call_tool("analyze_architectural_drawing", {"wall_thickness_range": [4, 12],
                                                                     "wall_junction_tolerance": 20})

    with patch.object(server.understanding_geometry, "analyze_geometry", return_value={"ok": True}) as geo, \
            patch.object(server.understanding_architecture, "analyze_architectural_drawing",
                         return_value={"ok": True}) as arch:
        asyncio.run(exercise())
    assert geo.call_args.kwargs["junction_tolerance"] == 3
    assert arch.call_args.kwargs["wall_junction_tolerance"] == 20
