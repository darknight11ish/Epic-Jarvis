"""test_forecast.py - "about N to M weeks" (build queue item 3, 2026-09-30;
docs/GOALS-PROGRESS-DESIGN.md part B and section 7; JARVIS-API section 101).

    python3 backend/test_forecast.py

The edge-case table of the design, with expectations worked out BY HAND
(the arithmetic is in each comment), plus:
  - the six answers are separate, and "never" is never a number of weeks
    (the argmax pitfall: numpy's argmax over "did it cross?" answers 0 when
    nothing did, which reads as "reached on day 0");
  - the fitted line agrees with the standard library's own
    statistics.linear_regression (an independent check, not a copy);
  - the same numbers give byte-identical answers; the file imports no numpy
    and calls no argmax;
  - two different clocks and zones (a DST weekend) count "different days"
    by the owner's local dates.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_forecast.py")

import jarvis_forecast as F  # noqa: E402

PASSED, FAILED = [], []
UTC = timezone.utc
DAY = 86400.0
NOW = 1790000000.0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def weekly(vals, step_days=7.0, end=NOW - 3600):
    """One number per `step_days`, the last one an hour before NOW."""
    n = len(vals)
    return [(end - (n - 1 - i) * step_days * DAY, v) for i, v in enumerate(vals)]


def fc(points, target=70, better="lower", now=NOW, tz=UTC):
    return F.forecast(points, target, better, now, tz=tz)


def t_zero_and_three_points_are_not_enough():
    r = fc([])
    check("0 points: not_enough, 5 more needed",
          r["state"] == "not_enough" and r["needed"] == 5
          and r["words"] == "Not enough numbers yet - 5 more needed.", r)
    r = fc(weekly([80, 79, 78]))
    check("3 points (80, 79, 78): not_enough, 2 more needed",
          r["state"] == "not_enough" and r["needed"] == 2 and r["used"] == 3
          and r["words"] == "Not enough numbers yet - 2 more needed.", r)
    check("not enough draws nothing", r["line"] is None and r["band"] is None
          and r["low_weeks"] is None)


def t_five_numbers_need_three_days_over_a_week():
    same_day = [(NOW - 7200 + i * 600, 80 - i) for i in range(5)]
    r = fc(same_day)
    check("5 numbers on one day: not_enough (days), nobody is 'missing' a count",
          r["state"] == "not_enough" and r["needed"] == 0 and r["words"] == F.WORDS["not_enough_days"], r)
    # 5 numbers on 2 days (an 8-day gap): 3 on day A, 2 on day B.
    a = NOW - 9 * DAY
    two_days = [(a, 80), (a + 600, 79.5), (a + 1200, 79), (a + 8 * DAY, 77), (a + 8 * DAY + 60, 76.5)]
    r = fc(two_days)
    check("exactly 5 numbers on 2 days: not_enough (days)",
          r["state"] == "not_enough" and r["words"] == F.WORDS["not_enough_days"], r)
    # 5 numbers on 3 days, but the whole thing only 6 days long: still not enough.
    b = NOW - 7 * DAY
    short = [(b, 80), (b + 600, 79.9), (b + 2 * DAY, 79), (b + 4 * DAY, 78), (b + 6 * DAY, 77)]
    r = fc(short)
    check("5 numbers on 5 days spanning only 6 days: not_enough (a week is needed)",
          r["state"] == "not_enough", r["state"])
    # 5 numbers on exactly 3 days spanning exactly 7 days: allowed.
    # x (days) = 0, 0.25, 0.5 (day 1), 3, 7 with y = 80 - x: a perfect line, slope -1/day.
    c = NOW - 7 * DAY
    ok = [(c, 80.0), (c + 0.25 * DAY, 79.75), (c + 0.5 * DAY, 79.5), (c + 3 * DAY, 77.0),
          (c + 7 * DAY, 73.0)]
    r = fc(ok, now=c + 7 * DAY)
    # last fitted value 73, target 70, 1 point/day -> 3 days -> under a week.
    check("exactly 5 numbers, 3 days, 7 days long: a real answer (less than a week)",
          r["state"] == "range" and r["words"] == "Less than a week at this pace."
          and r["low_weeks"] == 1 and r["high_weeks"] == 1, r)
    check("...and the line meets the target 3 days after the last number",
          abs(r["cross_at"] - (c + 10 * DAY)) < 0.01, r["cross_at"])


def t_steady_fall_is_a_narrow_range():
    # 80, 79, 78, 77, 76 a week apart: slope -1 per week exactly, no scatter (se = 0).
    # From 76 to 70 is 6 weeks: low = high = 6.
    r = fc(weekly([80, 79, 78, 77, 76]))
    check("steady fall: 'About 6 weeks'",
          r["state"] == "range" and r["low_weeks"] == 6 and r["high_weeks"] == 6
          and r["words"] == "About 6 weeks at this pace.", r)
    check("the centre crossing is 42 days after the last number",
          abs(r["cross_at"] - (r["last_at"] + 42 * DAY)) < 0.01
          and abs(r["cross_low_at"] - r["cross_at"]) < 0.01)
    check("the basis sentence names how many numbers were used",
          r["basis"] == "A straight line through your last 5 numbers. It is a rough guess, not a promise.")
    check("the line starts at the first used number's fitted value (80)",
          abs(r["line"]["from"]["value"] - 80.0) < 1e-6 and r["line"]["to"]["value"] == 70.0)


def t_scattered_fall_is_a_wide_range_never_a_narrow_one():
    # weeks 0..5, y = 80, 76, 79, 75, 78, 74 (lower is better, target 70).
    # xbar 2.5, ybar 77; Sxx 17.5; Sxy -14 -> slope -0.8/wk; Syy 28;
    # SSE = 28 - 0.8*14 = 16.8; df 4 -> s^2 4.2 -> se = sqrt(4.2/17.5) = 0.4899/wk;
    # t(4) = 1.533 -> +-0.7510: fast 1.5510/wk, slow 0.0490/wk.
    # Line at week 5 = 79 - 0.8*5 = 75 -> 5 to go: fast 3.22 wk -> 3, slow 102.1 wk -> 103.
    r = fc(weekly([80, 76, 79, 75, 78, 74]))
    check("scattered fall: 'About 3 to 103 weeks'",
          r["state"] == "range" and (r["low_weeks"], r["high_weeks"]) == (3, 103)
          and r["words"] == "About 3 to 103 weeks at this pace.", r)
    # 80, 84, 79, 83, 77: slope -0.7/wk; SSE 28.3, df 3, se 0.9713, t 1.638 -> slow end
    # -0.89/wk: the slow end does not improve at all -> open ended.
    # line at week 4 = 79.2, 9.2 to go; fast 2.2909/wk -> 4.016 wk -> 4.
    r = fc(weekly([80, 84, 79, 83, 77]))
    check("very scattered fall: open ended, 'About 4 weeks or more'",
          r["state"] == "open_ended" and r["low_weeks"] == 4 and r["high_weeks"] is None
          and r["why"] == "scattered"
          and r["words"] == "About 4 weeks or more - your numbers are too scattered to say how much more.", r)
    check("open ended: no upper crossing, the slow edge stops at the drawing's edge",
          r["cross_high_at"] is None and r["band"]["slow"]["clipped"] and r["band"]["slow"]["open"])
    # 80, 79, 80, 79, 78: slope -0.4/wk; SSE 1.2; se 0.2; t 1.638 -> slow end 0.0724/wk:
    # line at week 4 = 78.4, 8.4 to go: fast 11.5 wk -> 11; slow 116 wk (> 104).
    r = fc(weekly([80, 79, 80, 79, 78]))
    check("slow end past 2 years: open ended 'or more ... more than 2 years'",
          r["state"] == "open_ended" and r["low_weeks"] == 11 and r["why"] == "long"
          and r["words"] == "About 11 weeks or more - it could take more than 2 years.", r)


def t_flat_and_wrong_way_are_never_not_a_number():
    for name, vals, better, target in (
            ("flat", [75, 75, 75, 75, 75], "lower", 70),
            ("rising when lower is better", [72, 73, 74, 75, 76], "lower", 70),
            ("falling when higher is better", [76, 75, 74, 73, 72], "higher", 90)):
        r = fc(weekly(vals), target=target, better=better)
        check(f"{name}: 'never' - its own answer, no weeks",
              r["state"] == "never" and r["low_weeks"] is None and r["high_weeks"] is None
              and r["words"] == "Not reached at this pace."
              and r["cross_at"] is None and r["line"] is None and r["band"] is None, r)
        check(f"{name}: not 'reached on day 0' (the argmax pitfall)",
              "0 weeks" not in r["words"] and r["state"] != "reached" and not r["over_two_years"])


def t_target_reached_and_no_target():
    r = fc(weekly([75, 74, 72, 71, 69]))
    check("last number 69 (target 70, lower better): 'reached', nothing drawn",
          r["state"] == "reached" and r["words"] == "You have reached your target."
          and r["line"] is None and r["band"] is None, r)
    r = fc([(NOW - 60, 69.0)])
    check("reached needs no minimum of numbers", r["state"] == "reached")
    r = fc(weekly([70, 71, 72, 73, 70]))
    check("exactly at the target counts as reached", r["state"] == "reached")
    r = fc(weekly([70, 75, 80, 85, 90]), target=90, better="higher")
    check("higher is better: at the target is reached", r["state"] == "reached")
    for target, better in ((None, "lower"), (70, None), (70, ""), (None, None)):
        r = fc(weekly([80, 79, 78, 77, 76]), target=target, better=better)
        check(f"target={target!r} better={better!r}: no_target",
              r["state"] == "no_target" and r["words"] == "Set a target to see a pace.", r)


def t_very_slow_and_huge_values():
    # 0.01 a week from 79.96 with 9.96 to go: 996 weeks -> more than 2 years.
    r = fc(weekly([80, 79.99, 79.98, 79.97, 79.96]))
    check("very slow: 'More than 2 years at this pace.'",
          r["state"] == "open_ended" and r["over_two_years"] and r["low_weeks"] == 105
          and r["high_weeks"] is None and r["words"] == "More than 2 years at this pace.", r)
    check("more than 2 years: the drawing stops at the edge, arrow on",
          r["line"]["clipped"] and r["cross_at"] is None)
    # 1e12 falling 1e10 a week: from 9.6e11 to 0 is 96 weeks. (floats: rounding guard)
    r = fc(weekly([1e12 - i * 1e10 for i in range(5)]), target=0)
    check("huge values: 'About 96 weeks' (no off-by-one from float noise)",
          r["state"] == "range" and r["low_weeks"] == 96 and r["high_weeks"] == 96, r)
    # A tiny slope and tiny values.
    r = fc(weekly([1e-9 * i for i in (5, 4, 3, 2, 1)]), target=0, better="lower")
    check("tiny values (5e-9 falling 1e-9 a week to 0): a real answer of about a week",
          r["state"] == "range" and r["low_weeks"] >= 1, r)


def t_absurd_numbers_never_raise():
    good = weekly([80, 79, 78, 77, 76])
    inf, nan = float("inf"), float("nan")
    cases = {
        "1e300 values": [(a, v * 1e300) for a, v in good],
        "1e300 timestamps": [(a * 1e300, v) for a, v in good],
        "inf value": good[:-1] + [(good[-1][0], inf)],
        "nan value": good[:-1] + [(good[-1][0], nan)],
        "nan timestamp": good[:-1] + [(nan, 76.0)],
        "inf timestamp": good[:-1] + [(inf, 76.0)],
    }
    for name, pts in cases.items():
        try:
            r = fc(pts)
        except Exception as exc:
            check(f"{name}: does not raise", False, repr(exc))
            continue
        check(f"{name}: the not_enough state, nothing drawn",
              r["state"] == "not_enough" and r["line"] is None and r["band"] is None, r)
    for name, target in (("1e300 target", 1e300), ("inf target", inf), ("nan target", nan)):
        try:
            r = fc(good, target=target)
        except Exception as exc:
            check(f"{name}: does not raise", False, repr(exc))
            continue
        check(f"{name}: a real state, never 'reached' by accident from a bad number",
              r["state"] in F.STATES and (target == 1e300 or r["state"] == "not_enough"), r)
    r = fc(good, target=1e300, better="higher")
    check("1e300 target, higher is better: no crash, a real state", r["state"] in F.STATES, r)
    r = fc(good, now=nan)
    check("nan clock: not_enough", r["state"] == "not_enough", r)
    r = fc(weekly([80, 79, 78, 77, 76]))
    check("a normal answer is unchanged by the guard", r["state"] == "range", r)


def t_duplicate_timestamps():
    pts = weekly([80, 79, 78, 77, 76])
    dup = pts + [pts[-1]]                       # the same number logged twice at the same instant
    r = fc(dup)
    check("a duplicated number changes nothing on a perfect line (6 used)",
          r["state"] == "range" and r["used"] == 6 and r["low_weeks"] == 6, r)
    every_twice = [p for p in pts for _ in (0, 1)]
    r = fc(every_twice)
    check("every number logged twice: still 'About 6 weeks'", r["low_weeks"] == 6 == r["high_weeks"], r)
    # Two different numbers at the same instant: still a line, wider spread.
    noisy = pts[:4] + [(pts[4][0], 76.0), (pts[4][0], 77.5)]
    r = fc(noisy)
    check("two different numbers at one instant: an answer, never a crash",
          r["state"] in ("range", "open_ended"), r["state"])


def t_the_window_is_the_last_12_of_90_days():
    old = [(NOW - 100 * DAY - i * DAY, 80.0 - i) for i in range(6)]
    r = fc(old)
    check("numbers older than 90 days are ignored: 0 used, 5 more needed",
          r["state"] == "not_enough" and r["used"] == 0 and r["needed"] == 5, r)
    fifteen = weekly([100 - i for i in range(15)], step_days=5)       # 70 days long
    r = fc(fifteen, target=50)
    check("15 numbers: only the last 12 are used", r["used"] == 12, r["used"])
    r = fc(fifteen, target=50)
    check("...and 'reached' looks at the very latest number even before the window",
          fc([(NOW - 200 * DAY, 60.0)], target=70)["state"] == "reached")


def t_days_are_the_owners_local_days_across_a_dst_weekend():
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        ny.utcoffset(datetime(2026, 3, 8, 12))
    except Exception:
        check("(zoneinfo has no America/New_York here - DST check skipped)", True)
        return
    # US clocks jumped forward at 2:00 on 8 March 2026. Local times:
    def loc(m, d, h, mi=0):
        return datetime(2026, m, d, h, mi, tzinfo=ny).timestamp()
    pts = [(loc(3, 7, 22, 0), 80.0), (loc(3, 7, 23, 30), 79.6), (loc(3, 8, 0, 30), 79.2),
           (loc(3, 8, 12, 0), 78.6), (loc(3, 15, 12, 0), 75.0)]
    now = loc(3, 16, 9)
    r_ny = F.forecast(pts, 70, "lower", now, tz=ny)
    r_utc = F.forecast(pts, 70, "lower", now, tz=UTC)
    # Local days: 7, 8, 15 = 3 days over 7 days 13 hours -> counted.
    # In UTC every one of the first four is on 8 March -> only 2 days -> not enough.
    check("in New York: 3 different local days over a week - enough",
          r_ny["state"] != "not_enough", r_ny["state"])
    check("in UTC the same numbers fall on 2 days - not enough",
          r_utc["state"] == "not_enough" and r_utc["words"] == F.WORDS["not_enough_days"], r_utc)
    # The line uses real elapsed time, not calendar days: the 23-hour local day
    # of 8 March does not stretch or shrink the slope.
    xs = [(a - pts[0][0]) / DAY for a, _ in pts]
    reg = statistics.linear_regression(xs, [v for _, v in pts])
    check("the fitted start value equals the standard library's regression intercept",
          abs(r_ny["line"]["from"]["value"] - round(reg.intercept, 6)) < 1e-5,
          (r_ny["line"]["from"], reg.intercept))


def t_the_line_agrees_with_the_standard_library():
    vals = [80, 76, 79, 75, 78, 74]
    pts = weekly(vals)
    r = fc(pts)
    xs = [(a - pts[0][0]) / DAY for a, _ in pts]
    reg = statistics.linear_regression(xs, vals)
    check("scattered example: fitted first value = statistics.linear_regression's intercept",
          abs(r["line"]["from"]["value"] - reg.intercept) < 1e-5, (r["line"]["from"], reg.intercept))
    y0 = reg.intercept + reg.slope * xs[-1]
    check("the band starts at the line's own value at the last date (75)",
          abs(r["band"]["from"]["value"] - y0) < 1e-5 and abs(y0 - 75.0) < 1e-9, r["band"]["from"])
    check("the centre crossing = (value - target) / slope: 6.25 weeks after the last number",
          abs((r["cross_at"] - r["last_at"]) / DAY - (y0 - 70) / -reg.slope) < 1e-4
          and abs((r["cross_at"] - r["last_at"]) / DAY / 7 - 6.25) < 1e-6)


def t_the_drawing_stops_at_the_edge():
    r = fc(weekly([80, 79.5, 79, 78.5, 78]), target=60)      # 4 weeks of data, 36 weeks to go
    check("a crossing beyond 3 data-lengths is clipped, not drawn off the chart",
          r["line"]["clipped"] and r["line"]["to"]["at"] == r["horizon_at"]
          and r["cross_at"] is None, r)
    check("the horizon is 3 data-lengths past the last number",
          abs((r["horizon_at"] - r["last_at"]) - 3 * (r["last_at"] - r["first_at"])) < 0.01)


def t_determinism_and_source_hygiene():
    pts = weekly([80, 76, 79, 75, 78, 74])
    a, b = json.dumps(fc(pts), sort_keys=True), json.dumps(fc(list(reversed(pts))), sort_keys=True)
    check("the same numbers give byte-identical answers (input order does not matter)", a == b)
    src = (HERE / "jarvis_forecast.py").read_text(encoding="utf-8")
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    check("no numpy import", not re.search(r"^\s*(import|from)\s+numpy", src, re.M))
    check("no argmax call anywhere in the code", "argmax(" not in code and "argmin(" not in code)
    check("no random numbers", "import random" not in src and "random." not in code)
    check("no network, file or process import",
          not re.search(r"^\s*(import|from)\s+(socket|urllib|http|requests|subprocess|sqlite3|os)\b",
                        src, re.M))
    check("the six states are exactly the documented ones",
          F.STATES == ("no_target", "reached", "not_enough", "range", "open_ended", "never"))
    seen = {fc(weekly(v), target=t, better=bt)["state"]
            for v, t, bt in (([], 70, "lower"), ([69], 70, "lower"), ([80, 79, 78], 70, "lower"),
                             ([80, 79, 78, 77, 76], 70, "lower"), ([80, 84, 79, 83, 77], 70, "lower"),
                             ([75] * 5, 70, "lower"), ([75] * 5, None, "lower"))}
    check("every one of the six states is reachable", seen == set(F.STATES), seen)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                import traceback
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
