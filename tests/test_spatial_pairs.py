import random
from itertools import combinations

from src.cad_understanding.spatial_pairs import PRUNE_THRESHOLD, pruned_pairs


def brute(boxes, margin):
    keys = list(boxes)
    out = []
    for a, b in combinations(keys, 2):
        ba, bb = boxes[a], boxes[b]
        if (ba[0] - margin <= bb[2] + margin and bb[0] - margin <= ba[2] + margin
                and ba[1] - margin <= bb[3] + margin and bb[1] - margin <= ba[3] + margin):
            out.append((a, b))
    return out


def test_small_inputs_return_all_pairs_in_combination_order():
    boxes = {f"k{i}": (i * 1000.0, 0.0, i * 1000.0 + 1, 1.0) for i in range(10)}
    assert pruned_pairs(boxes, 1.0) == list(combinations(boxes, 2))


def test_large_inputs_match_bruteforce_overlap_in_the_same_order():
    rng = random.Random(7)
    boxes = {}
    for i in range(400):
        x, y = rng.uniform(0, 5000), rng.uniform(0, 5000)
        w, h = rng.choice([0, 0, 5, 60, 900]), rng.choice([0, 5, 60])
        boxes[f"L{i:03d}"] = (x, y, x + w, y + h)
    boxes["BIG"] = (0.0, 0.0, 5000.0, 5000.0)  # spans many cells: handled as oversized
    for margin in (0.0, 12.0, 80.0):
        assert len(boxes) > PRUNE_THRESHOLD
        assert pruned_pairs(boxes, margin) == brute(boxes, margin)


def test_pruning_drops_far_pairs_and_scales():
    boxes = {f"w{i}": (i * 100.0, 0.0, i * 100.0 + 90.0, 8.0) for i in range(2000)}
    pairs = pruned_pairs(boxes, 5.0)
    assert len(pairs) < 2000  # each wall meets only its neighbour, not 2 million pairs
    assert ("w0", "w1") in pairs and ("w0", "w5") not in pairs


def _wall_pair_segments(count):
    items = []
    for i in range(count):
        x = (i % 50) * 120.0
        y = (i // 50) * 60.0
        items.append({"id": f"c{i}a", "handles": [f"{i}a"], "shape": "line", "category": "wall",
                      "geometry": {"start": [x, y, 0], "end": [x + 100, y, 0]}})
        items.append({"id": f"c{i}b", "handles": [f"{i}b"], "shape": "line", "category": "wall",
                      "geometry": {"start": [x, y + 8, 0], "end": [x + 100, y + 8, 0]}})
    return items


def test_production_caps_allow_plan_sized_drawings_and_pairing_stays_exact():
    from src.cad_understanding import axis_junctions, line_geometry, room_loops
    from src.cad_understanding.line_pairs import find_parallel_pairs

    assert line_geometry.MAX_LINES >= 5000 and axis_junctions.MAX_AXES >= 5000 and room_loops.MAX_LOOP_AXES >= 5000
    items = _wall_pair_segments(600)  # 1200 wall faces: far above the former 100-line cap
    result = find_parallel_pairs(items, [4, 12])
    assert result["eligible_lines"] == 1200 and result["coverage_complete"]
    assert result["pair_count"] == 600 and not result["ambiguous_handles"]
    assert result["rejected_pair_counts"].get("far_apart_pruned", 0) > 700000
