"""Statistical process control (XmR charts), following NHS England's Making Data Count method.

The rules match the NHSRplotthedots R package, the NHS-R Community's implementation of Making Data Count:

  centre line      mean of the baseline points
  process limits   mean +/- 2.66 x average moving range (AMR)
  screening        moving ranges >= 3.267 x AMR are left out and the AMR recalculated (on by default)
  near limits      mean +/- (2/3 x 2.66) x AMR, i.e. two sigma

Special cause variation is flagged when any of these occur:
  1. a single point outside the process limits
  2. a run of 7 points all increasing or all decreasing (a trend)
  3. two out of three consecutive points between the near limits and the process limits, all three on the
     same side of the mean
  4. a run of 7 points all above or all below the mean (a shift)
Where several apply, a point is labelled by the first in that order.

Each flag is then called improvement or concern from the measure's improvement direction.
Assurance compares a target with the process limits: if the target sits outside them, the process will
consistently hit (or consistently miss) it; if inside, hitting it is down to chance.

`rebase` starts a new segment with its own limits, e.g. once the process has changed for good.
"""
from dataclasses import dataclass

LIMIT, SCREEN, NEAR, RUN = 2.66, 3.267, 2.66 * 2 / 3, 7


@dataclass
class Point:
    x: str
    y: float
    segment: int
    mean: float
    lpl: float
    upl: float
    near_lpl: float
    near_upl: float
    rule: str = ""                       # outside | trend | two_of_three | shift
    variation: str = "common_cause"     # common_cause | improvement | concern | neutral_high | neutral_low


def limits(values, screen=True):
    """Mean and average moving range for one segment."""
    mean = sum(values) / len(values)
    mr = [abs(b - a) for a, b in zip(values, values[1:])]
    if not mr:
        return mean, 0.0
    amr = sum(mr) / len(mr)
    if screen:
        kept = [m for m in mr if m < SCREEN * amr]
        amr = sum(kept) / len(kept) if kept else amr
    return mean, amr


def _sign(v):
    return (v > 0) - (v < 0)


def _part_of_seven(v):
    """A point is part of a 7-point pattern if it, or one of the next 6 points, completes one."""
    vp = list(v) + [0] * 6
    return [any(vp[i + k] != 0 for k in range(7)) for i in range(len(v))]


def _seven_trend(y):
    """+1 / -1 at a point that ends 7 strictly increasing / decreasing points."""
    out = [0] * len(y)
    for i in range(6, len(y)):
        d = {_sign(y[j] - y[j - 1]) for j in range(i - 5, i + 1)}
        out[i] = d.pop() if len(d) == 1 and 0 not in d else 0
    return out


def _seven_one_side(rtm):
    vp = [0] * 6 + list(rtm)
    return [int(vp[i] != 0 and all(vp[i] == vp[i - k] for k in range(1, 7))) for i in range(6, len(vp))]


def _two_in_three(close, rtm):
    """A point close to a limit, in a window of 3 with 2+ close points all on one side of the mean."""
    vp, rp = [0, 0] + close + [0, 0], [0, 0] + rtm + [0, 0]
    hit = [any(sum(vp[i + k:i + k + 3]) >= 2 and abs(sum(rp[i + k:i + k + 3])) == 3 for k in range(3))
           for i in range(len(close))]
    return [h and c for h, c in zip(hit, close)]


def _segment_rules(pts):
    """Special cause type per point, ported from NHSRplotthedots ptd_special_cause_type().
    Returns (rule, side) or None. Priority: outside limits > trend > two in three > shift."""
    y = [p.y for p in pts]
    rtm = [_sign(p.y - p.mean) for p in pts]
    outside = [p.y > p.upl or p.y < p.lpl for p in pts]
    close = [int(not o and (p.y < p.near_lpl or p.y > p.near_upl)) for p, o in zip(pts, outside)]
    trend = _part_of_seven(_seven_trend(y))
    two3 = _two_in_three(close, rtm)
    shift = _part_of_seven(_seven_one_side(rtm))
    sdy = [_sign(b - a) for a, b in zip(y, y[1:])]
    out = []
    for i in range(len(y)):
        side = "high" if rtm[i] > 0 else "low"
        if outside[i]:
            out.append(("outside", side))
        elif trend[i]:
            # within a trend use the step to the next point, at its last point the step from the previous
            nxt = i + 1 < len(y) and trend[i + 1]
            step = (sdy[i] if i < len(sdy) else sdy[-1]) if nxt else (sdy[i - 1] if i else 0)
            out.append(("trend", "high" if step == 1 else "low"))
        elif two3[i]:
            out.append(("two_of_three", side))
        elif shift[i]:
            out.append(("shift", side))
        else:
            out.append(None)
    return out


def spc(x, y, improvement="increase", rebase=(), screen=True):
    """XmR chart for series y (labels x). improvement: 'increase', 'decrease' or 'neutral'.
    rebase: labels in x at which a new segment (with fresh limits) starts."""
    assert len(x) == len(y) and len(y) >= 2
    starts = sorted({0} | {x.index(r) for r in rebase if r in x})
    bounds = list(zip(starts, starts[1:] + [len(y)]))
    out = []
    for seg, (a, b) in enumerate(bounds):
        mean, amr = limits(y[a:b], screen)
        pts = [Point(x[i], y[i], seg, mean, mean - LIMIT * amr, mean + LIMIT * amr,
                     mean - NEAR * amr, mean + NEAR * amr) for i in range(a, b)]
        for p, r in zip(pts, _segment_rules(pts)):
            if r:
                p.rule, side = r
                if improvement == "neutral":
                    p.variation = f"neutral_{side}"
                else:
                    good = (side == "high") == (improvement == "increase")
                    p.variation = "improvement" if good else "concern"
        out.extend(pts)
    return out


def assurance(points, target, improvement="increase"):
    """Assurance from the latest segment's limits: pass | fail | inconsistent | None (no target/direction)."""
    if target is None or improvement == "neutral":
        return None
    last = points[-1]
    if target > last.upl:
        return "fail" if improvement == "increase" else "pass"
    if target < last.lpl:
        return "pass" if improvement == "increase" else "fail"
    return "inconsistent"
