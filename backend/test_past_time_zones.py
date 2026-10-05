"""test_past_time_zones.py - "last week" (jarvis_past.when) across a clock change.

    python3 backend/test_past_time_zones.py

The bug (time audit, 2026-09-30): "last week" found this week's Monday with
"today's midnight minus weekday x 86,400 seconds". A day is not always 86,400
seconds, so on the Sunday after the clocks changed in a zone like
Asia/Jerusalem (they went forward on Friday 27 March 2026) that came out as
Sunday 22 March at 23:00 - an hour before the Monday it meant - and "last
week" started an hour early, at the wrong time on the wrong day.

Runs anywhere that has time.tzset (Linux, macOS). Where it is missing the
checks are skipped by name, never faked. No network, no model.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_past.py")
import jarvis_past as P  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def use_tz(name) -> bool:
    if not hasattr(time, "tzset"):
        return False
    os.environ["TZ"] = name
    time.tzset()
    return True


def at(y, mo, d, h=12, mi=0) -> float:
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


def wall(t) -> tuple:
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)


def t_last_week_after_a_clock_change():
    for zone, now_at, want_start, want_end in (
            # The clocks went forward on Friday 27 March: Sunday 29 March is the
            # day the old arithmetic got wrong.
            ("Asia/Jerusalem", at(2026, 3, 29), (2026, 3, 16, 0, 0), (2026, 3, 23, 0, 0)),
            ("Asia/Jerusalem", at(2026, 3, 30), (2026, 3, 23, 0, 0), (2026, 3, 30, 0, 0)),
            # And back again in October (Sunday 25 October 2026).
            ("Asia/Jerusalem", at(2026, 10, 25), (2026, 10, 12, 0, 0), (2026, 10, 19, 0, 0)),
            ("America/New_York", at(2026, 3, 8), (2026, 2, 23, 0, 0), (2026, 3, 2, 0, 0)),
            ("America/New_York", at(2026, 11, 1), (2026, 10, 19, 0, 0), (2026, 10, 26, 0, 0)),
            ("Europe/London", at(2026, 3, 29), (2026, 3, 16, 0, 0), (2026, 3, 23, 0, 0)),
            ("UTC", at(2026, 9, 27), (2026, 9, 14, 0, 0), (2026, 9, 21, 0, 0))):
        if not use_tz(zone):
            skip(f"{zone}: this system has no time.tzset")
            continue
        got = P.when("what did we do last week", now_at)
        check(f"{zone} {wall(now_at)[:3]}: 'last week' is Monday 00:00 to Monday 00:00",
              got is not None and (wall(got[0]), wall(got[1])) == (want_start, want_end),
              got and (wall(got[0]), wall(got[1])))


def main() -> int:
    orig = os.environ.get("TZ")
    try:
        t_last_week_after_a_clock_change()
    finally:
        if orig is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig
        if hasattr(time, "tzset"):
            time.tzset()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
