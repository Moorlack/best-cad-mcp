from src.cad_understanding.plan_clusters import find_plan_clusters


def seg(i, x, y, length=100.0):
    return {"id": f"s{i}", "axis_wcs": [[x, y, 0], [x + length, y, 0]],
            "thickness_drawing_units": {"min": 8, "max": 8, "mean": 8}}


def test_two_separate_plans_form_two_clusters():
    left = [seg(i, 0, i * 60) for i in range(6)]
    right = [seg(10 + i, 50000, i * 60) for i in range(5)]
    result = find_plan_clusters(left + right)
    assert result["cluster_count"] == 2 and result["multiple_plan_clusters"] is True
    assert [c["segment_count"] for c in result["clusters"]] == [6, 5]
    assert result["clusters"][0]["bbox_wcs"]["min"] == [0, 0]


def test_one_connected_plan_and_tiny_inputs_are_single_or_empty():
    plan = [seg(i, (i % 5) * 120, (i // 5) * 60) for i in range(20)]
    single = find_plan_clusters(plan)
    assert single["cluster_count"] == 1 and single["multiple_plan_clusters"] is False
    few = find_plan_clusters(plan[:2])
    assert few["clusters"] == [] and few["multiple_plan_clusters"] is False


def test_a_stray_segment_does_not_count_as_a_second_plan():
    plan = [seg(i, 0, i * 60) for i in range(6)] + [seg(99, 50000, 0)]
    result = find_plan_clusters(plan)
    assert result["cluster_count"] == 2 and result["multiple_plan_clusters"] is False
