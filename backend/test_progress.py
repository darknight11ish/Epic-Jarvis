"""test_progress.py - the activity heatmap and the balance chart
(jarvis_progress.py, progress.patch, docs/JARVIS-API.md section 105,
docs/GOALS-PROGRESS-DESIGN.md part C).

    python3 backend/test_progress.py

Real SQLite files in a temporary folder, the real jarvis_projects.py and
jarvis_goals.py (a fake scheduler, a fake clock), the real
jarvis_sensitive.py. No network, no model. What this proves:

  - the heatmap: empty data, one day, the level steps, Monday-first grid,
    future days never sent, weeks bounded, steps (done_at) plus logged
    numbers (by the date they are for), an untick takes a step off;
  - days are the owner's LOCAL days, across a daylight-saving weekend (spring
    forward and fall back), by a real time zone;
  - a health or money number shades its day and is never named: the answer
    holds dates and counts only, and says keep_on_screen;
  - no streak, no percentage, nothing red or "missed" in any word it sends;
  - the balance chart: 3 to 8 areas (or none), one owner's pick replaced whole,
    each area against its own target (higher and lower), a target already
    reached, a benchmark that is gone, no numbers yet, NaN and huge numbers,
    goal areas, the owner's own names, no overall score;
  - the routes and install();
  - jarvis_progress is NOT reachable from jarvis_agent.py or any model path.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from dateutil.tz import gettz as ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_progress.py", "jarvis_projects.py", "jarvis_goals.py",
                "jarvis_sensitive.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-progress-"))
_AUDIT = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: _AUDIT.append((event, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

_real_connect = socket.socket.connect
_NET = []


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_progress.py: no network")


socket.socket.connect = _no_connect

import jarvis_goals as G  # noqa: E402
import jarvis_progress as PR  # noqa: E402
import jarvis_projects as P  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def raises(fn, exc=Exception) -> str:
    try:
        fn()
    except exc as e:
        return str(e) or type(e).__name__
    return ""


NY = ZoneInfo("America/New_York")
_N = [0]


def ts(y, m, d, hh=12, mm=0, tz=NY, fold=0) -> float:
    return dt.datetime(y, m, d, hh, mm, tzinfo=tz, fold=fold).timestamp()


class Sched:
    def add_repeat(self, kind, rule, text="", source="app"):
        return {"id": "job1"}


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class World:
    """A projects store and a goals store side by side, on their own files."""

    def __init__(self, t=None):
        _N[0] += 1
        self.clock = Clock(t or ts(2026, 10, 14))
        self.p = P.Projects(_TMP / f"projects-{_N[0]}.db", clock=self.clock)
        self.g = G.Goals(_TMP / f"goals-{_N[0]}.db", clock=self.clock, scheduler=Sched(),
                         bench_reader=self.read_bench)
        self.pid = None

    def read_bench(self, project, bench):
        return self.p.results(project, bench, 1)

    def project(self, name="Fitness"):
        self.pid = self.p.create({"name": name, "kind": "life"}, here=False)["id"]
        return self.pid

    def bench(self, name, unit="", better=None, target=None, sensitive=False):
        if self.pid is None:
            self.project()
        body = {"name": name, "kind": "number", "unit": unit, "better": better,
                "target": target}
        if sensitive:
            body["sensitive"] = True
        return self.p.add_benchmark(self.pid, body, here=False)["id"]

    def log(self, bid, value, at=None):
        return self.p.log(self.pid, bid, value, at=at)

    def goal(self, text="Insulate the garage", steps=("Get quotes", "Pick one", "Book it"),
             accept=True):
        plan = [{"step": s, "by": "", "done": False} for s in steps]
        g = self.g.create(text, plan)
        if accept:
            g = self.g.accept(g["id"])
        return g["id"]

    def act(self, weeks=12, tz=NY):
        return PR.activity(weeks, now=self.clock.t, tz=tz, projects=self.p, goals=self.g)

    def bal(self):
        return PR.balance(projects=self.p, goals=self.g)

    def set(self, axes):
        return PR.set_balance({"axes": axes}, projects=self.p, goals=self.g)


def day(a, iso):
    return next(d for d in a["days"] if d["date"] == iso)


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from strings(v)


# --------------------------------------------------------------------------
#   Heatmap
# --------------------------------------------------------------------------

def t_empty():
    w = World()
    a = w.act()
    check("empty: nothing created, all days zero, empty flag, kind words",
          not w.p.exists() and a["total"] == 0 and a["days_active"] == 0 and a["empty"]
          and all(d["count"] == 0 and d["level"] == 0 for d in a["days"])
          and a["words"] == PR.WORDS["heat_empty"] and a["keep_on_screen"] is False)
    check("empty: the balance chart is empty too and creates nothing",
          w.bal()["axes"] == [] and w.bal()["choices"] == [] and not w.p.exists())
    check("empty: the total line has no '0 things on 0 days'", "0 things" not in json.dumps(a))


def t_one_day():
    w = World()
    b = w.bench("5k time", "min", "lower", 25)
    w.log(b, 30, at=ts(2026, 10, 12))
    a = w.act()
    d = day(a, "2026-10-12")
    check("one day: that day counts 1, level 1, words say so",
          d["count"] == 1 and d["level"] == 1 and d["words"] == "1 thing on 12 Oct", d)
    check("one day: the line is 'Last 12 weeks: 1 thing on 1 day.'",
          a["words"] == "Last 12 weeks: 1 thing on 1 day." and a["total"] == 1
          and a["days_active"] == 1 and not a["empty"], a["words"])
    check("one day: another day is neutral, worded without blame",
          day(a, "2026-10-11")["words"] == "Nothing on 11 Oct")


def t_levels_and_grid():
    check("levels: 0,1,2,3-4,5+", [PR.level_of(n) for n in (0, 1, 2, 3, 4, 5, 9)]
          == [0, 1, 2, 3, 3, 4, 4])
    w = World()   # Wednesday 14 Oct 2026
    a = w.act()
    ds = a["days"]
    check("grid: 11 full weeks plus Monday to Wednesday (Monday first)",
          len(ds) == 11 * 7 + 3 and ds[0]["date"] == "2026-07-27" and ds[0]["row"] == 0
          and ds[0]["col"] == 0 and ds[-1]["date"] == "2026-10-14"
          and ds[-1]["row"] == 2 and ds[-1]["col"] == 11, (len(ds), ds[0], ds[-1]))
    check("grid: dates run one day at a time, cols/rows follow",
          all((dt.date.fromisoformat(d["date"]) - dt.date(2026, 7, 27)).days == i
              and d["col"] == i // 7 and d["row"] == i % 7 for i, d in enumerate(ds)))
    check("grid: week labels", a["columns"][0]["label"] == "Week of 27 Jul"
          and a["columns"][11]["label"] == "Week of 12 Oct" and len(a["columns"]) == 12)
    check("grid: no future day", all(d["date"] <= "2026-10-14" for d in ds))
    check("weeks are bounded 4..26 and junk means 12",
          [PR.clamp_weeks(x) for x in (1, 4, 12, 26, 99, "8", "x", None, True, -3, float("nan"))]
          == [4, 4, 12, 26, 26, 8, 12, 12, 12, 4, 12])
    check("weeks=26 gives 25 full weeks of columns", w.act(26)["weeks"] == 26
          and len(w.act(26)["columns"]) == 26)
    on_monday = PR.activity(12, now=ts(2026, 10, 12, 9), tz=NY, projects=w.p, goals=w.g)
    check("a Monday today: the last column has one day", on_monday["days"][-1]["row"] == 0
          and on_monday["days"][-1]["date"] == "2026-10-12")
    on_sunday = PR.activity(12, now=ts(2026, 10, 18, 23, 59), tz=NY, projects=w.p, goals=w.g)
    check("a Sunday today: the last column is a whole week", len(on_sunday["days"]) == 12 * 7
          and on_sunday["days"][-1]["row"] == 6)


def t_steps_and_numbers():
    w = World(ts(2026, 10, 14, 18))
    gid = w.goal()
    w.clock.t = ts(2026, 10, 13, 9)
    w.g.mark_step(gid, 0, True)
    w.clock.t = ts(2026, 10, 13, 10)
    w.g.mark_step(gid, 1, True)
    b = w.bench("Garage boxes cleared", "", "higher", 20)
    w.log(b, 3, at=ts(2026, 10, 13, 20))
    w.clock.t = ts(2026, 10, 14, 18)
    a = w.act()
    check("steps and numbers share a day: 2 steps + 1 number = 3, level 3",
          day(a, "2026-10-13")["count"] == 3 and day(a, "2026-10-13")["level"] == 3
          and day(a, "2026-10-13")["words"] == "3 things on 13 Oct")
    w.g.mark_step(gid, 1, False)
    check("unticking takes that step off the day again",
          w.act()["days"][-2]["count"] == 2)
    w.log(b, 4, at=ts(2026, 9, 1))
    check("a backfilled number appears on its own date",
          day(w.act(), "2026-09-01")["count"] == 1)
    check("a number older than the window is not shown",
          w.act(4)["total"] == 2, w.act(4)["total"])


def t_future_and_bad_dates():
    w = World()
    b = w.bench("Books read", "", "higher", 12)
    w.log(b, 1, at=w.clock.t + 3600 * 20)          # tomorrow (allowed by the store)
    a = w.act()
    check("a number dated in the future is not counted or sent",
          a["total"] == 0 and a["days"][-1]["date"] == "2026-10-14")
    gid = w.goal()
    w.g.mark_step(gid, 0, True)
    # a step whose done_at is later than 'now' (a clock that moved back)
    with w.g._db() as c:
        row = c.execute("SELECT plan FROM goals WHERE id = ?", (gid,)).fetchone()
        plan = json.loads(row["plan"])
        plan[0]["done_at"] = w.clock.t + 5 * 86400
        c.execute("UPDATE goals SET plan = ? WHERE id = ?", (json.dumps(plan), gid))
    check("a step done 'in the future' is not counted", w.act()["total"] == 0)
    check("junk times are skipped, not crashed on",
          PR.local_date(float("nan")) is None and PR.local_date(1e30) is None
          and PR.local_date("x") is None and PR.local_date(True) is None
          and PR.local_date(None) is None)


def t_dst():
    # Spring forward: Sunday 8 March 2026, 02:00 -> 03:00 in New York.
    w = World(ts(2026, 3, 12))
    b = w.bench("Pages written", "", "higher", 100)
    for when in (ts(2026, 3, 7, 23, 30),           # 04:30 UTC on the 8th
                 ts(2026, 3, 8, 1, 30),            # EST
                 ts(2026, 3, 8, 3, 30),            # EDT, an hour "later"
                 ts(2026, 3, 8, 23, 30),           # 03:30 UTC on the 9th
                 ts(2026, 3, 9, 0, 30)):
        w.log(b, 1, at=when)
    a = w.act()
    got = {d: day(a, d)["count"] for d in ("2026-03-07", "2026-03-08", "2026-03-09")}
    check("DST spring forward: local days, not UTC days",
          got == {"2026-03-07": 1, "2026-03-08": 3, "2026-03-09": 1}, got)
    utc_days = {}
    for when in (ts(2026, 3, 7, 23, 30), ts(2026, 3, 8, 1, 30)):
        d = dt.datetime.fromtimestamp(when, dt.timezone.utc).date().isoformat()
        utc_days[d] = utc_days.get(d, 0) + 1
    check("DST: (the test would notice UTC bucketing)", utc_days.get("2026-03-08") == 2)
    check("DST weekend has exactly one cell per date, in order",
          [d["date"] for d in a["days"]] == sorted({d["date"] for d in a["days"]}))
    # Fall back: Sunday 1 November 2026, 02:00 -> 01:00; 01:30 happens twice.
    w2 = World(ts(2026, 11, 5))
    b2 = w2.bench("Pages written", "", "higher", 100)
    w2.log(b2, 1, at=ts(2026, 11, 1, 1, 30, fold=0))
    w2.log(b2, 1, at=ts(2026, 11, 1, 1, 30, fold=1))
    w2.log(b2, 1, at=ts(2026, 10, 31, 23, 45))
    w2.log(b2, 1, at=ts(2026, 11, 2, 0, 15))
    a2 = w2.act()
    check("DST fall back: the repeated hour stays on the one day",
          day(a2, "2026-11-01")["count"] == 2 and day(a2, "2026-10-31")["count"] == 1
          and day(a2, "2026-11-02")["count"] == 1)
    ahead = PR.activity(12, now=ts(2026, 3, 12), tz=dt.timezone(dt.timedelta(hours=13)),
                        projects=w.p, goals=w.g)
    check("another zone gives its own days (UTC+13)", ahead["today"] == "2026-03-13")
    default = PR.activity(12, now=time.time(), projects=w.p, goals=w.g)
    check("no tz means this PC's own local time", default["today"] == dt.date.today().isoformat()
          or abs(dt.datetime.now().hour - 12) > 10)


def t_sensitive_heatmap():
    w = World()
    b = w.bench("Body weight", "kg", "lower", 70)
    w.log(b, 82.4, at=ts(2026, 10, 12))
    w.log(b, 82.0, at=ts(2026, 10, 13))
    a = w.act()
    text = json.dumps(a)
    check("a health number shades its day", day(a, "2026-10-12")["count"] == 1
          and day(a, "2026-10-13")["level"] == 1)
    check("... is never named or shown", "weight" not in text.lower() and "82" not in text
          and "kg" not in text)
    check("... and the answer says keep_on_screen", a["keep_on_screen"] is True
          and a["hidden_words"] == PR.WORDS["hidden"])
    w2 = World()
    b2 = w2.bench("Spending on coffee", "$", "lower", 40)
    w2.log(b2, 9, at=ts(2026, 10, 12))
    check("a money number does the same", w2.act()["keep_on_screen"] is True
          and "coffee" not in json.dumps(w2.act()).lower())
    w3 = World()
    b3 = w3.bench("Chapters", "", "higher", 20)
    w3.log(b3, 1, at=ts(2026, 10, 12))
    check("an ordinary number does not set the flag", w3.act()["keep_on_screen"] is False)
    w4 = World()
    b4 = w4.bench("Chapters", "", "higher", 20, sensitive=True)
    w4.log(b4, 1, at=ts(2026, 10, 12))
    check("a number the owner marked private counts as private", w4.act()["keep_on_screen"] is True)
    w5 = World()
    gid = w5.goal("Get fitter", ("Take my medication daily",))
    w5.g.mark_step(gid, 0, True)
    a5 = w5.act()
    check("a private step shades and is never named",
          a5["keep_on_screen"] is True and a5["total"] == 1 and "medication" not in json.dumps(a5))
    w6 = World()
    b6 = w6.bench("Body weight", "kg", "lower", 70)
    w6.log(b6, 80, at=ts(2025, 1, 1))
    check("a private number outside the window does not set the flag",
          w6.act()["keep_on_screen"] is False)


def t_no_streak_words():
    w = World()
    b = w.bench("Chapters", "", "higher", 20)
    for i in range(1, 10):
        w.log(b, i, at=ts(2026, 10, i))
    a = w.act()
    bad = [(s, f) for s in strings([a, w.bal(), PR.WORDS]) for f in PR.FORBIDDEN_WORDS
           if f in s.lower()]
    check("no streak, run, percentage, average or 'missed' in anything sent", not bad, bad[:3])
    check("no streak-like key either", not [k for k in a if "streak" in k or "run" in k
                                            or "percent" in k or "rate" in k])
    check("nine days in a row are just nine counted days", a["days_active"] == 9
          and a["words"] == "Last 12 weeks: 9 things on 9 days.")


def t_speed():
    w = World()
    bs = [w.bench(f"Number {i}", "", "higher", 100) for i in range(12)]
    t0 = time.time()
    with w.p._db() as c:
        for i, b in enumerate(bs):
            c.executemany("INSERT INTO results (id, bench, value, at, source, logged) "
                          "VALUES (?,?,?,?,?,?)",
                          [(f"{i:04x}{j:028x}", b, float(j), w.clock.t - j * 3600, "app", 0.0)
                           for j in range(4000)])
    seed = time.time() - t0
    t1 = time.time()
    a = w.act(26)
    dur = time.time() - t1
    check("48,000 numbers: the 26-week heatmap is fast", dur < 1.5 and a["total"] > 0,
          f"{dur:.2f}s (seeding {seed:.1f}s)")


# --------------------------------------------------------------------------
#   Balance
# --------------------------------------------------------------------------

def t_fraction():
    f = PR.fraction
    check("lower is better: 80 -> 75 toward 70 is half", f(80, 75, 70, "lower") == 0.5)
    check("higher is better: 10 -> 15 toward 20 is half", f(10, 15, 20, "higher") == 0.5)
    check("a target already reached is a full ring (passed it too)",
          f(80, 70, 70, "lower") == 1.0 and f(80, 65, 70, "lower") == 1.0
          and f(10, 25, 20, "higher") == 1.0)
    check("moving away from the target is 0, never negative",
          f(80, 85, 70, "lower") == 0.0 and f(10, 5, 20, "higher") == 0.0)
    check("a first number already past the target that slid back is 0",
          f(65, 72, 70, "lower") == 0.0)
    check("first = target and not met is 0 (no divide by zero)",
          f(70, 71, 70, "lower") == 0.0)
    check("no direction, or a missing number, is None",
          f(1, 2, 3, None) is None and f(None, 2, 3, "higher") is None
          and f(1, None, 3, "higher") is None and f(1, 2, None, "higher") is None)
    check("NaN and infinity are None, never NaN",
          f(float("nan"), 1, 2, "higher") is None and f(1, float("inf"), 2, "higher") is None
          and f(1, 2, float("-inf"), "higher") is None)
    check("huge numbers stay finite and between 0 and 1",
          f(-1e300, 1e300, 1e308, "higher") is not None
          and 0.0 <= f(-1e300, 1e300, 1e308, "higher") <= 1.0)
    o = f(-1.7e308, 0, 1.7e308, "higher")
    check("an overflow in the subtraction is None or still between 0 and 1",
          o is None or 0.0 <= o <= 1.0, o)
    check("bool is not a number", f(True, 2, 3, "higher") is None)


def t_axes_limits():
    w = World()
    bs = [w.bench(f"Thing {i}", "u", "higher", 10) for i in range(9)]
    for b in bs:
        w.log(b, 1)
    ax = lambda n: [{"kind": "bench", "ref": bs[i]} for i in range(n)]      # noqa: E731
    check("2 areas are refused with a sentence", "3 to 8" in raises(lambda: w.set(ax(2))))
    check("9 areas are refused", "3 to 8" in raises(lambda: w.set(ax(9))))
    check("nothing was stored by a refusal", w.p.axes_read() == [])
    r3 = w.set(ax(3))
    check("3 areas are kept, drawable", len(r3["axes"]) == 3 and r3["drawable"] is True)
    r8 = w.set(ax(8))
    check("8 areas are kept, in the given order",
          [a["ref"] for a in r8["axes"]] == bs[:8] and len(w.p.axes_read()) == 8)
    check("a refusal leaves the earlier chart alone",
          raises(lambda: w.set(ax(2))) != "" and len(w.p.axes_read()) == 8)
    r0 = w.set([])
    check("an empty list clears the chart", r0["axes"] == [] and w.p.axes_read() == []
          and r0["words"] == PR.WORDS["balance_none"] and r0["drawable"] is False)
    check("the same area twice is refused",
          "once" in raises(lambda: w.set([ax(3)[0], ax(3)[0], ax(3)[1]])))
    check("an unknown number is refused",
          "gone" in raises(lambda: w.set(ax(2) + [{"kind": "bench", "ref": "0" * 32}])))
    check("junk shapes are refused",
          all(raises(lambda b=b: PR.set_balance(b, projects=w.p, goals=w.g))
              for b in (None, [], {}, {"axes": "x"}, {"axes": [1, 2, 3]},
                        {"axes": [{"kind": "x", "ref": "y"}] * 3})))
    nt = w.bench("No finish line", "u")
    w.log(nt, 1)
    check("a number without a target cannot be an axis",
          "target" in raises(lambda: w.set(ax(2) + [{"kind": "bench", "ref": nt}])))
    check("a name over 24 characters is refused",
          "24" in raises(lambda: w.set([dict(a, label="x" * 25) for a in ax(3)])))
    custom = w.set([dict(ax(3)[0], label="  Fit\nness  "), ax(3)[1], ax(3)[2]])
    check("the owner's own name is kept, tidied to one line",
          custom["axes"][0]["label"] == "Fit ness" and custom["axes"][1]["label"] == "Thing 1")
    check("the picker lists what can be picked, with picked marks",
          sum(1 for c in custom["choices"] if c["picked"]) == 3
          and all(c["kind"] in ("bench", "goal") for c in custom["choices"])
          and nt not in [c["ref"] for c in custom["choices"]])
    draft = w.goal("Draft only", accept=False)
    check("a draft goal cannot be an axis",
          "not accepted" in raises(lambda: w.set(ax(2) + [{"kind": "goal", "ref": draft}])))


def t_axis_values():
    w = World()
    lo = w.bench("Weight goal", "kg", "lower", 70)
    hi = w.bench("Distance", "km", "higher", 20)
    cash = w.bench("Saved", "$", "higher", 1000)
    nothing = w.bench("Fresh", "km", "higher", 5)
    for at, v in ((ts(2026, 9, 1), 80), (ts(2026, 10, 1), 75), (ts(2026, 10, 10), 72.5)):
        w.log(lo, v, at=at)
    w.log(hi, 5, at=ts(2026, 9, 1))
    w.log(hi, 12.5, at=ts(2026, 10, 1))
    w.log(cash, 200, at=ts(2026, 9, 1))
    w.log(cash, 400, at=ts(2026, 10, 1))
    r = w.set([{"kind": "bench", "ref": x} for x in (lo, hi, cash, nothing)])
    a = {x["ref"]: x for x in r["axes"]}
    check("lower is better: '72.5 of 70 kg', fraction 0.75",
          a[lo]["value_words"] == "72.5 of 70 kg" and a[lo]["fraction"] == 0.75, a[lo])
    check("higher: '12.5 of 20 km', 0.5", a[hi]["value_words"] == "12.5 of 20 km"
          and a[hi]["fraction"] == 0.5)
    check("money keeps its sign: '$400 of $1000', 0.25", a[cash]["value_words"] == "$400 of $1000"
          and a[cash]["fraction"] == 0.25)
    check("no numbers yet is a dot, not a zero: fraction null, words",
          a[nothing]["fraction"] is None and a[nothing]["state"] == "no_numbers"
          and a[nothing]["value_words"] == "no numbers yet")
    w.log(lo, 68, at=ts(2026, 10, 12))
    a2 = {x["ref"]: x for x in w.bal()["axes"]}
    check("target already reached: full ring, state reached, real value printed",
          a2[lo]["fraction"] == 1.0 and a2[lo]["state"] == "reached"
          and a2[lo]["value_words"] == "68 of 70 kg")
    check("no overall score, total or average anywhere in the answer",
          not [k for k in w.bal() if k in ("score", "total", "average", "overall")]
          and "No overall score" in w.bal()["summary"])
    check("the summary lists every area with its value", "Weight goal: 68 of 70 kg." in w.bal()["summary"]
          and "Fresh: no numbers yet." in w.bal()["summary"])
    check("the answer is plain JSON (no NaN)", json.dumps(w.bal(), allow_nan=False))
    long = w.bench("A very long benchmark name indeed", "u", "higher", 3)
    w.log(long, 1)
    lab = w.set([{"kind": "bench", "ref": x} for x in (lo, hi, long)])["axes"][2]["label"]
    check("a long default name is shortened for the spoke", len(lab) <= PR.MAX_LABEL
          and lab.endswith("…"))
    ax = w.set([{"kind": "bench", "ref": x} for x in (lo, hi, long)])["axes"]
    check("each area also carries a 12-character name for beside the spoke",
          all(len(a["short"]) <= PR.MAX_SHORT for a in ax) and ax[0]["short"] == "Weight goal"
          and ax[2]["short"].endswith("…"), [a["short"] for a in ax])


def t_bad_numbers_in_db():
    w = World()
    x = [w.bench(f"Big {i}", "u", "higher", 10) for i in range(3)]
    for b in x:
        w.log(b, 1)
    w.set([{"kind": "bench", "ref": b} for b in x])
    with w.p._db() as c:
        c.execute("UPDATE results SET value = ? WHERE bench = ?", (1e308, x[0]))
        c.execute("UPDATE benchmarks SET target = ? WHERE id = ?", (-1e308, x[0]))
        c.execute("UPDATE results SET value = ? WHERE bench = ?", (float("inf"), x[1]))
    r = w.bal()
    ok = True
    try:
        json.dumps(r, allow_nan=False)
    except ValueError:
        ok = False
    check("huge or infinite stored numbers never make NaN or a crash",
          ok and len(r["axes"]) == 3 and all(a["fraction"] is None or 0 <= a["fraction"] <= 1
                                             for a in r["axes"]), r["axes"])


def t_deleted_benchmark():
    w = World()
    bs = [w.bench(f"Thing {i}", "u", "higher", 10) for i in range(4)]
    for b in bs:
        w.log(b, 2)
    w.set([{"kind": "bench", "ref": b} for b in bs])
    w.p.delete_benchmark(w.pid, bs[1])
    r = w.bal()
    check("a deleted benchmark leaves the chart at once, order closed up",
          [a["ref"] for a in r["axes"]] == [bs[0], bs[2], bs[3]]
          and [a["position"] if "position" in a else 0 for a in r["axes"]] == [0, 0, 0]
          and [x["ref"] for x in w.p.axes_read()] == [bs[0], bs[2], bs[3]])
    w.p.delete_benchmark(w.pid, bs[2])
    r2 = w.bal()
    check("under 3 left: kept, not drawable, says so kindly",
          len(r2["axes"]) == 2 and r2["drawable"] is False and r2["words"] == PR.WORDS["balance_few"])
    with w.p._db() as c:       # a stray row (an older file): healed on the next read
        c.execute("INSERT INTO balance_axes (position, kind, project, ref, label) "
                  "VALUES (9, 'bench', ?, ?, '')", (w.pid, "f" * 32))
    r3 = w.bal()
    check("an axis whose benchmark is gone is dropped from the file too",
          len(r3["axes"]) == 2 and len(w.p.axes_read()) == 2)
    w.set([])
    b2 = w.bench("Another", "u", "higher", 5)
    w.log(b2, 1)
    w.set([{"kind": "bench", "ref": b} for b in (bs[0], bs[3], b2)])
    w.p.delete(w.pid)
    check("deleting the whole project clears its axes", w.p.axes_read() == [])


def t_goal_axes():
    w = World()
    g = w.goal("Insulate the garage", ("a", "b", "c", "d", "e"))
    one = w.goal("One step goal", ("only",))
    b1, b2 = w.bench("X", "u", "higher", 10), w.bench("Y", "u", "higher", 10)
    w.log(b1, 1)
    w.log(b2, 1)
    for i in range(3):
        w.g.mark_step(g, i, True)
    r = w.set([{"kind": "goal", "ref": g}, {"kind": "goal", "ref": one},
               {"kind": "bench", "ref": b1}])
    a = {x["ref"]: x for x in r["axes"]}
    check("a goal axis is steps done out of steps: '3 of 5 steps', 0.6",
          a[g]["value_words"] == "3 of 5 steps" and a[g]["fraction"] == 0.6, a[g])
    check("one step reads '0 of 1 step'", a[one]["value_words"] == "0 of 1 step"
          and a[one]["fraction"] == 0.0)
    w.g.mark_step(one, 0, True)
    check("all done is a full ring", {x["ref"]: x for x in w.bal()["axes"]}[one]["fraction"] == 1.0)
    check("goal choices are listed when accepted", any(c["kind"] == "goal" and c["ref"] == g
                                                       for c in r["choices"]))
    w.g.stop(one)
    r_stop = w.bal()
    check("a stopped goal leaves the chart, like a draft (owner, 2026-09-30)",
          not any(x["ref"] == one for x in r_stop["axes"])
          and not any(c["ref"] == one for c in r_stop["choices"])
          and all(a["ref"] != one for a in w.p.axes_read()))
    check("...and a save naming it is refused in a sentence",
          "stopped" in raises(lambda: w.set([{"kind": "goal", "ref": one}, {"kind": "goal", "ref": g},
                                             {"kind": "bench", "ref": b1}]), PR.Refused))
    # goals unreadable: nothing is forgotten
    class Broken:
        def list(self):
            raise RuntimeError("goals.db locked")
    r2 = PR.balance(projects=w.p, goals=Broken())
    check("goals.db unreadable: goal axes are not drawn but NOT forgotten",
          len(r2["axes"]) == 1 and len(w.p.axes_read()) == 2)
    a3 = PR.activity(12, now=w.clock.t, tz=NY, projects=w.p, goals=Broken())
    check("goals.db unreadable: the heatmap still draws the numbers", a3["total"] == 2)


def t_stopping_a_goal_takes_it_off_the_chart_at_once():
    w = World()
    g1, g2 = w.goal("First"), w.goal("Second")
    b = w.bench("X", "u", "higher", 10)
    w.log(b, 1)
    w.set([{"kind": "goal", "ref": g1}, {"kind": "goal", "ref": g2}, {"kind": "bench", "ref": b}])
    real = P._ONE
    P._ONE = w.p                      # the store Goals.stop() reaches for
    try:
        w.g.stop(g1)
    finally:
        P._ONE = real
    check("Goals.stop() calls the cleanup: gone from the file before any read",
          [a["ref"] for a in w.p.axes_read()] == [g2, b])


def t_stopped_and_draft_activity():
    w = World(ts(2026, 10, 14, 18))
    live = w.goal("Live goal")
    gone = w.goal("Stopped goal")
    draft = w.goal("Pasted draft", accept=False)
    w.clock.t = ts(2026, 10, 13, 9)
    w.g.mark_step(live, 0, True)
    w.g.mark_step(gone, 0, True)
    w.g.mark_step(draft, 0, True)          # ticked while still a draft
    w.clock.t = ts(2026, 10, 14, 18)
    check("a draft's ticked step is not on the heatmap; an accepted one is",
          day(w.act(), "2026-10-13")["count"] == 2)
    w.g.stop(gone)
    check("a stopped goal's ticked steps leave the heatmap too",
          day(w.act(), "2026-10-13")["count"] == 1)
    a = w.act()
    check("nothing else on the map", a["total"] == 1, a["total"])


def t_draft_done_step_is_dated_at_accept():
    w = World(ts(2026, 10, 1, 9))
    plan = [{"step": "Old habit", "by": "", "done": True}, {"step": "Next", "by": "", "done": False}]
    g = w.g.create("Pasted plan", plan)
    check("while a draft, the map does not shade its creation day",
          w.act()["total"] == 0 and w.g.get(g["id"])["plan"][0]["done"] is True)
    w.clock.t = ts(2026, 10, 14, 10)
    w.g.accept(g["id"])
    st = w.g.get(g["id"])["plan"]
    check("accepting dates a step saved done at ACCEPT time, not creation time",
          st[0]["done_at"] == w.clock.t and st[1]["done_at"] is None, st)
    check("...so it shades the accept day and not the creation day",
          day(w.act(), "2026-10-14")["count"] == 1 and day(w.act(), "2026-10-01")["count"] == 0)
    g2 = w.g.create("Second plan", plan)
    w.clock.t = ts(2026, 10, 15, 10)
    w.g.accept(g2["id"], [{"step": "Old habit", "by": "", "done": True, "id": "s1"},
                          {"step": "Next", "by": "", "done": True, "id": "s2"}])
    st2 = w.g.get(g2["id"])["plan"]
    check("an edit at accept time that has steps done also dates them at accept",
          st2[0]["done_at"] == w.clock.t and st2[1]["done_at"] == w.clock.t)


def t_picked_areas_survive_the_choice_cut():
    w = World()
    bs = []
    for i in range(PR.MAX_CHOICES + 6):
        if i % 10 == 0:
            w.project(f"Project {i // 10}")
        bs.append(w.bench(f"Thing {i:02d}", "u", "higher", 10))
    pick = [bs[-1], bs[-2], bs[-3]]        # the last ones: past the cut
    r = w.set([{"kind": "bench", "ref": b} for b in pick])
    refs = [c["ref"] for c in r["choices"]]
    check("more than 60 things: the picker is cut to 60 ...", len(refs) == PR.MAX_CHOICES, len(refs))
    check("... but every picked area is still offered, and ticked",
          all(b in refs for b in pick) and all(c["picked"] for c in r["choices"] if c["ref"] in pick))
    check("... in the original order", refs == [b["id"] for b in w.p.progress_benchmarks() if b["id"] in set(refs)])
    # a picked number whose target was taken away is still offered
    w2 = World()
    a, b2, c2 = (w2.bench(f"T{i}", "u", "higher", 10) for i in range(3))
    for x in (a, b2, c2):
        w2.log(x, 1)
    w2.set([{"kind": "bench", "ref": x} for x in (a, b2, c2)])
    with w2.p._db() as conn:
        conn.execute("UPDATE benchmarks SET target = NULL WHERE id = ?", (a,))
    r2 = w2.bal()
    check("a picked number that lost its target is still in the picker (so it can be unticked)",
          any(c["ref"] == a and c["picked"] for c in r2["choices"]))


def t_save_and_read_do_not_undo_each_other():
    """The read cleans up the stored chart; a save at the same moment must not be
    overwritten by a stale copy of the old chart."""
    import threading
    w = World()
    bs = [w.bench(f"Thing {i}", "u", "higher", 10) for i in range(6)]
    for b in bs:
        w.log(b, 1)
    w.set([{"kind": "bench", "ref": b} for b in bs[:3]])
    errors = []

    def reader():
        try:
            for _ in range(60):
                w.bal()
        except Exception as e:                 # pragma: no cover
            errors.append(e)

    t = threading.Thread(target=reader)
    t.start()
    for i in range(20):
        w.set([{"kind": "bench", "ref": b} for b in (bs[3:] if i % 2 == 0 else bs[:3])])
    t.join()
    last = bs[:3]
    check("a save is the last word: the chart is exactly what the last save said",
          not errors and [a["ref"] for a in w.p.axes_read()] == last, errors)
    # the clean-up itself runs under the store's lock
    seen = []
    real = w.p.axes_write

    def spy(axes):
        seen.append(w.p._lock._is_owned())
        return real(axes)

    w.p.axes_write = spy
    with w.p._db() as conn:       # a stray row: the read heals it, under the lock
        conn.execute("INSERT INTO balance_axes (position, kind, project, ref, label) "
                     "VALUES (9, 'bench', ?, ?, '')", (w.pid, "f" * 32))
    w.bal()
    check("the clean-up write is made while holding the store's lock", seen == [True], seen)


def t_sensitive_axes():
    w = World()
    s = w.bench("Body weight", "kg", "lower", 70)
    o = [w.bench(f"Thing {i}", "u", "higher", 10) for i in range(2)]
    w.log(s, 80, at=ts(2026, 9, 1))
    w.log(s, 78, at=ts(2026, 10, 1))
    for b in o:
        w.log(b, 1)
    r = w.set([{"kind": "bench", "ref": x} for x in [s] + o])
    check("a private axis is allowed and flagged, and so is the whole chart",
          r["axes"][0]["keep_on_screen"] is True and r["axes"][1]["keep_on_screen"] is False
          and r["keep_on_screen"] is True)
    check("the picker flags private choices too", any(c["keep_on_screen"] for c in r["choices"]))
    check("its value is exact and only on this answer: '78 of 70 kg'",
          r["axes"][0]["value_words"] == "78 of 70 kg")
    w2 = World()
    plain = [w2.bench(f"Thing {i}", "u", "higher", 10) for i in range(3)]
    for b in plain:
        w2.log(b, 1)
    check("an ordinary chart is not flagged",
          w2.set([{"kind": "bench", "ref": x} for x in plain])["keep_on_screen"] is False)


def t_audit():
    w = World()
    bs = [w.bench(f"Secret name {i}", "kg", "higher", 10) for i in range(3)]
    for b in bs:
        w.log(b, 7.77)
    _AUDIT.clear()
    w.set([{"kind": "bench", "ref": b, "label": "Private label"} for b in bs])
    blob = json.dumps(_AUDIT)
    check("the audit log has counts only", "Secret" not in blob and "7.77" not in blob
          and "Private label" not in blob and "projects.balance.set" in blob, blob)


# --------------------------------------------------------------------------
#   Routes
# --------------------------------------------------------------------------

def t_routes():
    w = World()
    bs = [w.bench(f"Thing {i}", "u", "higher", 10) for i in range(3)]
    for b in bs:
        w.log(b, 1)
    kw = dict(projects=w.p, goals=w.g)
    code, out = PR.handle_get("/api/progress/activity", "weeks=8", now=w.clock.t, tz=NY, **kw)
    check("GET activity?weeks=8", code == 200 and out["weeks"] == 8 and out["ok"])
    code, out = PR.handle_get("/api/progress/activity", "weeks=oops", now=w.clock.t, tz=NY, **kw)
    check("GET activity with junk weeks means 12", code == 200 and out["weeks"] == 12)
    code, out = PR.handle_post("/api/progress/balance", {"axes": [{"kind": "bench", "ref": b}
                                                                for b in bs]}, **kw)
    check("POST balance", code == 200 and len(out["axes"]) == 3)
    code, out = PR.handle_get("/api/progress/balance", **kw)
    check("GET balance", code == 200 and len(out["axes"]) == 3 and out["max"] == 8)
    code, out = PR.handle_post("/api/progress/balance", {"axes": [{"kind": "bench", "ref": bs[0]}]}, **kw)
    check("a refused POST is a 400 with a sentence and stores nothing",
          code == 400 and out["ok"] is False and out["error"].endswith(".")
          and len(w.p.axes_read()) == 3)
    check("unknown routes are 404",
          PR.handle_get("/api/progress/x", **kw)[0] == 404
          and PR.handle_post("/api/progress/activity", {}, **kw)[0] == 404)
    check("a broken store is a 503, not a stack trace",
          PR.handle_get("/api/progress/balance", projects=object(), goals=w.g)[0] == 503)


class FakeHandler:
    sent = []
    posted = []

    def __init__(self, path, body=b"{}", ok=True):
        self.path, self.body, self.ok = path, body, ok
        self.out = None

    def _send(self, code, obj):
        self.out = (code, obj)

    def do_GET(self):
        FakeHandler.sent.append(self.path)
        self.out = (200, {"orig": True})

    def do_POST(self):
        FakeHandler.posted.append(self.path)
        self.out = (200, {"orig": True})


def t_install():
    PR._reset_for_tests()
    cls = type("H", (FakeHandler,), {})
    cls.sent, cls.posted = [], []
    line = PR.install(cls, origin_ok=lambda h: h.ok, token_ok=lambda h: h.ok,
                      read_body=lambda h: h.body)
    check("install returns a banner line", "progress" in line.lower())
    check("install twice does not wrap twice",
          "already on" in PR.install(cls, origin_ok=lambda h: True, token_ok=lambda h: True,
                                     read_body=lambda h: b""))
    h = cls("/api/chat")
    h.do_GET()
    check("another route goes to the original", h.out == (200, {"orig": True}))
    h = cls("/api/progress/balance", ok=False)
    h.do_GET()
    check("a bad token or origin is refused before anything is read", h.out[0] in (401, 403))
    h = cls("/api/progress/balance", body=b"not json")
    h.do_POST()
    check("bad JSON is a 400", h.out[0] == 400)
    h = cls("/api/other")
    h.do_POST()
    check("another POST goes to the original", h.out == (200, {"orig": True}))
    PR._reset_for_tests()


# --------------------------------------------------------------------------
#   Not reachable from a model
# --------------------------------------------------------------------------

def t_not_reachable():
    allowed = {"jarvis_progress.py", "test_progress.py", "_where.py"}
    hits = []
    for f in sorted(HERE.rglob("*.py")):
        if f.name in allowed or "__pycache__" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if re.search(r"jarvis_progress|\bprogress\.py", text) and "test_" not in f.name:
            hits.append(f.name)
    check("no module in backend/ (jarvis_agent.py, quick, chat, search, speech ...) mentions "
          "jarvis_progress", not hits, hits)
    agent = HERE / "jarvis_agent.py"
    if agent.is_file():
        text = agent.read_text(encoding="utf-8")
        check("jarvis_agent.py neither imports it nor lists a progress tool",
              "jarvis_progress" not in text and not re.search(
                  r"Tool\(\s*['\"](?:my_)?(?:progress|activity|balance)", text)
              and not re.search(r"['\"](?:my_)?(?:progress|heatmap|balance_chart)['\"]\s*:", text))
        # The tool table's names, read for real.
        import importlib
        try:
            A = importlib.import_module("jarvis_agent")
            names = [str(getattr(t, "name", t)) for t in
                     (A.TOOLS.values() if isinstance(A.TOOLS, dict) else A.TOOLS)]
            check("the real tool table has no progress, heatmap or balance tool",
                  not [n for n in names if re.search(r"progress|heatmap|balance|activity", n)],
                  names)
        except Exception as exc:
            print(f"note  jarvis_agent could not be imported here ({type(exc).__name__}); "
                  "the text check above stands")
    else:
        print("note  jarvis_agent.py is not in this folder; the module scan above stands")
    src = (HERE / "jarvis_progress.py").read_text(encoding="utf-8")
    imports = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", src, re.M))
    bad = imports & {"jarvis_agent", "jarvis_search", "jarvis_chatbot", "jarvis_speech",
                     "jarvis_tts", "jarvis_quick", "jarvis_notify", "requests", "socket",
                     "urllib.request", "http.client", "jarvis_hud", "jarvis_web_search"}
    check("jarvis_progress imports nothing that reaches a model, a speaker or the network",
          not bad, bad)
    check("it calls no model and opens no file", "ollama" not in src.lower()
          and "open(" not in src and "urlopen" not in src)
    check("the words it sends contain no forbidden word",
          not [(s, f) for s in strings(PR.WORDS) for f in PR.FORBIDDEN_WORDS if f in s.lower()])


def t_patch_and_lists():
    sys.path.insert(0, str(HERE))
    import _stack
    order = _stack.order()
    check("progress.patch is in apply-patches.ps1's list, after retirement.patch",
          "progress.patch" in order and "retirement.patch" in order
          and order.index("progress.patch") > order.index("retirement.patch"))
    if "progress.patch" not in order:
        return
    text, log = _stack.stand_in("jarvis_hud.py", order[:order.index("progress.patch")])
    check("the stack before it builds a stand-in", text is not None, log)
    if text is None:
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-progress-patch-"))
    (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
    (d / "p.patch").write_bytes((HERE / "progress.patch").read_bytes())
    r = subprocess.run(["git", "apply", "--check", "p.patch"], cwd=d, capture_output=True, text=True)
    check("progress.patch applies to what the earlier patches wrote (no fuzz)",
          r.returncode == 0, r.stderr[-400:])
    full, _log = _stack.stand_in("jarvis_hud.py")
    check("and the whole stack still builds with it", full is not None
          and "jarvis_progress.install(Handler" in full)
    if full:
        i = full.index("import jarvis_progress")
        check("its block is inside the startup try/except and before the socket",
              full.index("# Before the main socket") > i
              and "jarvis_retirement.install" in full[:i])
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_progress.py is a shipped module", "'jarvis_progress.py'" in ps1)


def t_fixture():
    tool = REPO / "tools" / "gen_progress_cases.py"
    if not tool.is_file():
        check("tools/gen_progress_cases.py exists", False)
        return
    r = subprocess.run([sys.executable, str(tool), "--check"], capture_output=True, text=True)
    check("progress-cases.json (desktop and phone) is what the backend says today "
          "(python3 tools/gen_progress_cases.py)", r.returncode == 0, r.stdout + r.stderr)


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    check("no network was touched", not _NET, _NET)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
