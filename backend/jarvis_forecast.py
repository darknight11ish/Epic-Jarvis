"""jarvis_forecast.py - "about N to M weeks": a finish-time range for a
benchmark (build queue item 3, 2026-09-30; docs/GOALS-PROGRESS-DESIGN.md
part B; JARVIS-API section 101).

NEW MODULE, shipped whole. PURE: no file, no network, no model, no
random numbers, no third-party library (no numpy). The same numbers in give
the same words out, which is what the tests - and the two apps' shared
contract file - rely on. jarvis_projects.py calls forecast() when a
benchmark is read for a chart; jarvis_goals.py reads the same answer for
its optional pace line.

THE METHOD, IN PLAIN WORDS
A straight line (least squares) through the last up to 12 numbers logged in
the last 90 days. The spread comes from how sure the line's slope is (its
standard error, times a small fixed t-value for the number of numbers): the
faster end of the slope range gives the early finish, the slower end the
late one. Scattered numbers give a wide range on their own. A bootstrap was
refused in the design: with 5 to 12 numbers there are few different
resamples, it needs random numbers, and it looks more precise than it is.

SIX ANSWERS, NEVER BLENDED
    no_target    the benchmark has no target, or does not say better is
                 higher or lower
    reached      the latest number is already at or past the target
    not_enough   fewer than 5 numbers, or not on at least 3 different days
                 spread over at least a week
    range        the line improves and both ends are finite: "about 6 to 9
                 weeks"
    open_ended   the line improves but the slow end of the slope is flat or
                 backwards (or more than 2 years): only a lower end
    never        the line is flat or moves away from the target

"NEVER REACHED" IS ITS OWN ANSWER - THE ARGMAX PITFALL. numpy's argmax over
a yes/no array returns 0 when nothing is true, which reads as "reached on
day 0". This file finds no "first true" by searching: the answer is a closed
form (distance / slope), and a flat or wrong-way line is `never` before any
division happens. test_forecast.py checks the file has no argmax and no
numpy, and that the never-reached case stays `never`.

WHAT THE ANSWER CARRIES (all numbers from code; the words are here too, so
both apps say them word for word - tools/gen_projects_cases.py writes them
into the contract file):
    {"state", "words", "basis", "low_weeks", "high_weeks", "over_two_years",
     "why", "used", "needed", "first_at", "last_at", "horizon_at",
     "cross_low_at", "cross_at", "cross_high_at", "line", "band"}
`line` and `band` are the drawing: a dashed straight line from the first
used point to where it meets the target (or the edge), and a translucent
triangle from the last point out to the fast and slow crossings. They stop
at the edge - 3 times the length of the data past the last point - with
`clipped: true`, and the words carry the rest.
"""
from __future__ import annotations

import math
from datetime import datetime

DAY = 86400.0
WINDOW_DAYS = 90            # only numbers from the last 90 days
MAX_USED = 12               # ...and only the last 12 of those
MIN_USED = 5                # at least 5 numbers...
MIN_DAYS = 3                # ...on at least 3 different days...
MIN_SPAN_DAYS = 7           # ...spread over at least a week
MAX_WEEKS = 104             # "more than 2 years"
EDGE_SPANS = 3              # the drawing stops 3 data-lengths past the last point

#: Two-sided Student t, about the middle 80% (the 0.90 quantile), for 3 to
#: 10 degrees of freedom (5 to 12 numbers). The rules above keep n between
#: 5 and 12, so no lookup falls outside it.
T80 = {3: 1.638, 4: 1.533, 5: 1.476, 6: 1.440, 7: 1.415, 8: 1.397, 9: 1.383, 10: 1.372}

STATES = ("no_target", "reached", "not_enough", "range", "open_ended", "never")

#: The sentences, the same in both apps. `{low}` `{high}` `{weeks}` `{more}`
#: `{n}` are filled in here; the apps show `words` as sent and never
#: rebuild them.
WORDS = {
    "no_target": "Set a target to see a pace.",
    "reached": "You have reached your target.",
    "not_enough_count": "Not enough numbers yet - {more} more needed.",
    "not_enough_days": ("Not enough numbers yet - they need to be on at least 3 different "
                        "days, spread over a week or more."),
    "range": "About {low} to {high} weeks at this pace.",
    "range_same": "About {low} weeks at this pace.",
    "less_than_a_week": "Less than a week at this pace.",
    "open_scattered": ("About {low} {weeks} or more - your numbers are too scattered to say "
                       "how much more."),
    "open_long": "About {low} {weeks} or more - it could take more than 2 years.",
    "over_two_years": "More than 2 years at this pace.",
    "never": "Not reached at this pace.",
    "basis": "A straight line through your last {n} numbers. It is a rough guess, not a promise.",
}


def better_reached(latest: float, target: float, better: str) -> bool:
    """The one place "reached" is decided (a goal step's measure uses it
    too): higher is better means latest >= target, lower means <=."""
    if better == "higher":
        return latest >= target
    if better == "lower":
        return latest <= target
    return False


def _r(v: float) -> float:
    return round(float(v), 6)


def _blank(state: str, words: str, **more) -> dict:
    out = {"state": state, "words": words, "basis": "", "low_weeks": None,
           "high_weeks": None, "over_two_years": False, "why": "", "used": 0, "needed": 0,
           "first_at": None, "last_at": None, "horizon_at": None, "cross_low_at": None,
           "cross_at": None, "cross_high_at": None, "line": None, "band": None}
    out.update(more)
    return out


def _weeks(days: float) -> float:
    return round(days / 7.0, 6)


def _local_day(at: float, tz) -> tuple:
    d = datetime.fromtimestamp(at, tz)
    return (d.year, d.month, d.day)


def forecast(points, target, better, now: float, *, tz=None) -> dict:
    """`points` is a list of (at_seconds, value), any order - the caller may
    pass all of a benchmark's recent numbers; this picks the last up to 12
    from the last 90 days. `tz` decides what "a different day" means
    (None = this PC's own clock; the tests pass a fixed zone)."""
    if target is None or better not in ("higher", "lower"):
        return _blank("no_target", WORDS["no_target"])
    target = float(target)
    rows = sorted(((float(a), float(v)) for a, v in points), key=lambda p: p[0])
    if rows and better_reached(rows[-1][1], target, better):
        return _blank("reached", WORDS["reached"])

    recent = [p for p in rows if p[0] >= now - WINDOW_DAYS * DAY][-MAX_USED:]
    n = len(recent)
    if n < MIN_USED:
        more = MIN_USED - n
        return _blank("not_enough", WORDS["not_enough_count"].format(more=more),
                      used=n, needed=more)
    days = {_local_day(a, tz) for a, _ in recent}
    if len(days) < MIN_DAYS or recent[-1][0] - recent[0][0] < MIN_SPAN_DAYS * DAY:
        return _blank("not_enough", WORDS["not_enough_days"], used=n, needed=0)

    # ---- the straight line: x in days from the first used point -------------
    at0 = recent[0][0]
    xs = [(a - at0) / DAY for a, _ in recent]
    ys = [v for _, v in recent]
    xbar, ybar = sum(xs) / n, sum(ys) / n
    sxx = sum((x - xbar) ** 2 for x in xs)                  # > 0: the span is a week
    sxy = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    syy = sum((y - ybar) ** 2 for y in ys)
    b = sxy / sxx                                           # value change per day
    a0 = ybar - b * xbar
    sse = max(0.0, syy - b * sxy)
    se = math.sqrt(sse / (n - 2)) / math.sqrt(sxx)
    t = T80[n - 2]

    sign = 1.0 if better == "higher" else -1.0              # +1: bigger numbers are better
    g = sign * b                                            # improvement per day
    if not g > 0:                                           # flat, wrong way, or not a number
        return _blank("never", WORDS["never"], used=n)

    last_at = recent[-1][0]
    y0 = a0 + b * xs[-1]                                    # the line's own value at the last date
    dist = max(0.0, sign * (target - y0))                   # still to go, by the line
    g_hi, g_lo = g + t * se, g - t * se
    low_days = dist / g_hi
    central_days = dist / g
    span = last_at - at0
    horizon = last_at + EDGE_SPANS * span

    out = _blank("range", "", used=n, first_at=_r(at0), last_at=_r(last_at),
                 horizon_at=_r(horizon), basis=WORDS["basis"].format(n=n))

    slow_open = not g_lo > 0
    high_days = None if slow_open else dist / g_lo

    def edge(g_edge: float, days) -> dict:
        """Where an edge line ends: on the target, or at the drawing's edge."""
        if days is not None:
            cross = last_at + days * DAY
            if cross <= horizon:
                return {"at": _r(cross), "value": _r(target), "clipped": False}
        reach = (horizon - last_at) / DAY
        return {"at": _r(horizon), "value": _r(y0 + sign * g_edge * reach), "clipped": True}

    if low_days > MAX_WEEKS * 7:
        # even the fast end is more than 2 years away: only a lower end.
        out.update(state="open_ended", over_two_years=True, why="long",
                   low_weeks=MAX_WEEKS + 1, words=WORDS["over_two_years"])
    elif slow_open or high_days > MAX_WEEKS * 7:
        low = max(1, math.floor(_weeks(low_days)))
        out.update(state="open_ended", low_weeks=low,
                   why="scattered" if slow_open else "long",
                   words=WORDS["open_scattered" if slow_open else "open_long"].format(
                       low=low, weeks="week" if low == 1 else "weeks"))
    else:
        low = max(1, math.floor(_weeks(low_days)))
        high = max(low, math.ceil(_weeks(high_days)))
        if high_days <= 7:
            words = WORDS["less_than_a_week"]
            low = high = 1
        elif low == high:
            words = WORDS["range_same"].format(low=low)
        else:
            words = WORDS["range"].format(low=low, high=high)
        out.update(state="range", low_weeks=low, high_weeks=high, words=words)

    # ---- the drawing (dashed line and band), stopped at the edge ------------
    fast = edge(g_hi, low_days)
    slow = edge(max(g_lo, 0.0), high_days)
    centre = edge(g, central_days)
    out["cross_low_at"] = None if fast["clipped"] else fast["at"]
    out["cross_at"] = None if centre["clipped"] else centre["at"]
    out["cross_high_at"] = None if slow["clipped"] else slow["at"]
    out["line"] = {"from": {"at": _r(at0), "value": _r(a0)},
                   "to": {"at": centre["at"], "value": centre["value"]},
                   "clipped": centre["clipped"]}
    out["band"] = {"from": {"at": _r(last_at), "value": _r(y0)},
                   "fast": fast, "slow": dict(slow, open=slow_open)}
    return out
