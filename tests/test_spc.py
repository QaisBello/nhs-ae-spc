"""The SPC rules, checked on small series where the right answer can be worked out by hand."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from spc import assurance, limits, spc  # noqa: E402

NOISE = [10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 9]          # stable: mean 10, every moving range 1


def run(y, **kw):
    return spc([f"m{i:02d}" for i in range(len(y))], y, **kw)


def test_limits_are_mean_plus_minus_2_66_average_moving_range():
    mean, amr = limits(NOISE)
    assert mean == 10 and amr == 1
    p = run(NOISE)[0]
    assert p.upl == pytest.approx(12.66) and p.lpl == pytest.approx(7.34)
    assert p.near_upl == pytest.approx(10 + 2.66 * 2 / 3)


def test_screening_drops_huge_moving_ranges_from_the_average():
    y = NOISE + [40] + NOISE
    _, raw = limits(y, screen=False)
    _, screened = limits(y, screen=True)
    assert screened < raw and screened == pytest.approx(1.0)


def test_stable_process_is_common_cause_throughout():
    assert {p.variation for p in run(NOISE)} == {"common_cause"}


def test_point_outside_limits_is_special_cause_in_the_right_direction():
    y = NOISE + [20] + NOISE
    up = run(y, improvement="increase")
    assert up[12].rule == "outside" and up[12].variation == "improvement"
    down = run(y, improvement="decrease")
    assert down[12].variation == "concern"
    assert run(y, improvement="neutral")[12].variation == "neutral_high"


def test_seven_point_trend_flags_all_seven_points():
    y = NOISE + [9, 9.3, 9.6, 9.9, 10.2, 10.5, 10.8] + NOISE
    pts = run(y, improvement="increase")
    flagged = [i for i, p in enumerate(pts) if p.rule == "trend"]
    assert flagged == list(range(12, 19))       # the 7 rising points, nothing either side
    assert {pts[i].variation for i in flagged} == {"improvement"}


def test_six_rising_points_are_not_a_trend():
    y = NOISE[:-1] + [9.3, 9.6, 9.9, 10.2, 10.5, 10.8] + NOISE     # 10 before 9.3, so only six rise
    assert not any(p.rule == "trend" for p in run(y))


def test_seven_points_one_side_of_the_mean_is_a_shift():
    low, high = [9.0, 9.8, 9.1, 9.7, 9.0, 9.8, 9.2], [10.8, 10.2, 10.9, 10.1, 10.8, 10.2, 10.9]
    pts = run(low + high, improvement="decrease")
    assert [p.rule for p in pts] == ["shift"] * 14
    assert [p.variation for p in pts] == ["improvement"] * 7 + ["concern"] * 7


def test_two_of_three_near_the_upper_limit():
    # with these points added the near limit is 12.40 and the limit 13.50: 12.5 and 12.6 sit between them
    y = NOISE + [12.5, 10.5, 12.6] + NOISE
    pts = run(y, improvement="decrease")
    assert pts[12].near_upl < 12.5 and 12.6 < pts[12].upl
    assert [pts[i].rule for i in (12, 13, 14)] == ["two_of_three", "", "two_of_three"]
    assert pts[12].variation == "concern"


def test_rebase_gives_each_segment_its_own_limits():
    y = NOISE + [v + 5 for v in NOISE]
    pts = run(y, rebase=["m12"])
    assert pts[0].mean == 10 and pts[-1].mean == 15
    assert {p.variation for p in pts} == {"common_cause"}
    assert any(p.variation != "common_cause" for p in run(y))      # without the rebase it looks like a shift


@pytest.mark.parametrize("target,direction,expected", [
    (13, "increase", "fail"), (7, "increase", "pass"), (10, "increase", "inconsistent"),
    (13, "decrease", "pass"), (7, "decrease", "fail"), (10, "neutral", None), (None, "increase", None)])
def test_assurance_compares_target_with_process_limits(target, direction, expected):
    assert assurance(run(NOISE), target, direction) == expected
