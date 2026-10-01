#!/usr/bin/env python3
"""Writes the "Activity heatmap and balance chart" contract file for both
apps, and checks it.

    python3 tools/gen_progress_cases.py            # write both copies
    python3 tools/gen_progress_cases.py --check    # compare only

What the backend really answers (backend/jarvis_progress.py, progress.patch;
JARVIS-API section 105; docs/GOALS-PROGRESS-DESIGN.md "Progress contract
(frozen)"), in named situations, made by the real code - nothing written by
hand:

    jarvis-desktop/tests/fixtures/progress-cases.json
    jarvis-client/app/src/test/resources/contract/progress-cases.json

(byte-identical). It also carries what BOTH apps must draw the same way and
the backend does not send - the reference geometry below:

  * `heat_rects` - each day's square (x, y, size, level) for the grid;
  * `radar` - for a list of fractions: the rings, the spokes, the polygon,
    the value-label positions (numbers rounded to 2 places; the apps'
    tests allow a difference of 0.01);
  * `shading` - the five heatmap fills as a share of the accent colour laid
    over the surface, and the neutral empty cell.

The ids are counted and the clock is fixed, so the file only changes when the
backend's answer does. Times are worked out in New York (a real daylight
saving zone) so the sample days do not depend on the machine running this.
"""
import datetime as dt
import json
import math
import os
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from dateutil.tz import gettz as ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_CONF = Path(tempfile.mkdtemp(prefix="jarvis-progress-cases-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CONF)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _CONF
fw.LOG_DIR = _CONF
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: None
fw.action_tier = lambda action: "ask"
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_goals as G  # noqa: E402
import jarvis_progress as PR  # noqa: E402
import jarvis_projects as P  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "progress-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "progress-cases.json")
COPIES = (DESKTOP, PHONE)

NY = ZoneInfo("America/New_York")

#: The heatmap grid: one cell is CELL px square, STEP px from the next.
CELL = 14
GAP = 3
STEP = CELL + GAP
#: The share of the accent colour laid over the surface for level 0..4. Level
#: 0 is no fill at all: the surface with a thin outline (neutral, never red).
#: The ladder is held to MEASURED contrast (see `ladder_report`): level 1 at
#: least 1.5:1 over the surface, every neighbouring pair at least 1.25:1, the
#: top level at least 4.5:1 - for each desktop theme in theme.css. The phone's
#: accent is the owner's choice, so ProgressTest measures the worst case over
#: the whole accent palette instead (the top level clears 3.9:1 there, because
#: the accent is only guaranteed 4.5:1 against the card, not against the
#: slightly darker surface the grid sits on).
SHADING = {"alpha": [0.0, 0.40, 0.58, 0.79, 1.0], "empty_outline": True,
           "min_step": 0.18,
           "require": {"first_over_surface": 1.5, "neighbour": 1.25, "top": 4.5,
                       "phone_top": 3.9}}
#: The radar: a square canvas, its middle, the outer ring's radius, and how
#: far past the ring a label sits.
RADAR_SIZE = 260
RADAR_R = 80.0
RADAR_LABEL = 14.0
RINGS = (0.25, 0.5, 0.75, 1.0)


assert all(b - a >= SHADING["min_step"] - 1e-9
           for a, b in zip(SHADING["alpha"], SHADING["alpha"][1:])), "shading steps too close"


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(a, b) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _mix(under, over, alpha):
    return [round(o * alpha + u * (1 - alpha)) for u, o in zip(under, over)]


def _theme_tokens() -> dict:
    """--surface-2 and --accent-rgb of every desktop theme, read from theme.css
    (a translucent surface is laid over black, the usual dark desktop)."""
    css = (ROOT / "jarvis-desktop" / "src" / "theme.css").read_text(encoding="utf-8")
    blocks = {"deep-space": css[css.index(":root {"):css.index("\n}\n", css.index(":root {"))]}
    for name in ("paper", "high-contrast"):
        i = css.index(f'[data-theme="{name}"] {{')
        blocks[name] = css[i:css.index("\n}\n", i)]
    out = {}
    for name, text in blocks.items():
        m = re.search(r"--surface-2:\s*rgba?\(([^)]*)\)", text)
        a = re.search(r"--accent-rgb:\s*(\d+)\s+(\d+)\s+(\d+)", text)
        if name != "deep-space":
            assert m and a, name
        if name == "deep-space":
            base = css[:css.index('[data-theme="deep-space"]')]
            m = re.search(r"--surface-2:\s*rgba?\(([^)]*)\)", base)
            a = re.search(r"--accent-rgb:\s*(\d+)\s+(\d+)\s+(\d+)", base)
        parts = [float(x) for x in re.split(r"[ ,/]+", m.group(1).strip()) if x]
        alpha = parts[3] if len(parts) > 3 else 1.0
        surface = _mix([0, 0, 0], parts[:3], alpha)
        out[name] = {"surface": surface, "accent": [int(x) for x in a.groups()]}
    return out


def ladder_report() -> dict:
    """The measured contrast of the five levels in every desktop theme; raises
    when the ladder is not distinguishable (the owner's rule, 2026-09-30)."""
    need = SHADING["require"]
    out = {}
    for name, t in _theme_tokens().items():
        levels = [_mix(t["surface"], t["accent"], a) for a in SHADING["alpha"][1:]]
        over = [round(_ratio(c, t["surface"]), 2) for c in levels]
        near = [round(_ratio(levels[i], levels[i - 1]), 2) for i in range(1, 4)]
        assert over[0] >= need["first_over_surface"], f"{name}: level 1 is only {over[0]}:1"
        assert min(near) >= need["neighbour"], f"{name}: neighbouring levels {near}"
        assert over[-1] >= need["top"], f"{name}: the top level is only {over[-1]}:1"
        out[name] = {"surface": t["surface"], "accent": t["accent"],
                     "over_surface": over, "neighbours": near}
    return out


def ts(y, m, d, hh=12, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=NY).timestamp()


def r2(x: float) -> float:
    v = round(x, 2)
    return 0.0 if v == 0 else v


def heat_rects(days: list) -> list:
    """The reference for the heatmap grid: x = col * 17, y = row * 17."""
    return [{"date": d["date"], "x": d["col"] * STEP, "y": d["row"] * STEP, "size": CELL,
             "level": d["level"]} for d in days]


def heat_size(weeks: int) -> dict:
    return {"cell": CELL, "gap": GAP, "width": weeks * STEP - GAP, "height": 7 * STEP - GAP}


def radar(fractions: list) -> dict:
    """The reference for the balance chart. `fractions` are the axes in order
    (a number 0..1, or None = "no numbers yet", drawn as a dot in the middle).
    Spoke i points at angle -90 degrees + i * 360 / n (the first spoke is
    straight up, then clockwise)."""
    n = len(fractions)
    c = RADAR_SIZE / 2
    spokes, verts, labels = [], [], []
    for i, f in enumerate(fractions):
        a = -math.pi / 2 + 2 * math.pi * i / n
        cs, sn = math.cos(a), math.sin(a)
        spokes.append({"x": r2(c + RADAR_R * cs), "y": r2(c + RADAR_R * sn)})
        fr = 0.0 if f is None else float(f)
        verts.append({"x": r2(c + RADAR_R * fr * cs), "y": r2(c + RADAR_R * fr * sn),
                      "dot": f is None})
        anchor = "middle" if abs(cs) < 0.2 else ("start" if cs > 0 else "end")
        dy = 10 if sn > 0.3 else (0 if sn < -0.3 else 4)
        labels.append({"x": r2(c + (RADAR_R + RADAR_LABEL) * cs),
                       "y": r2(c + (RADAR_R + RADAR_LABEL) * sn + dy), "anchor": anchor})
    return {"size": RADAR_SIZE, "center": {"x": c, "y": c}, "radius": RADAR_R,
            "rings": [r2(RADAR_R * k) for k in RINGS], "fractions": fractions,
            "spokes": spokes, "polygon": verts, "labels": labels}


class _Counted:
    def __init__(self):
        self.n = 0

    def uuid4(self):
        self.n += 1
        return types.SimpleNamespace(hex=f"{self.n:010x}" + "0" * 22)   # a goal id keeps the first 10


class _NoSched:
    def add_repeat(self, kind, rule, text="", source="app"):
        return {"id": "job1", "state": "active"}


class _Ids:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"{self.n:032x}"


NOW = ts(2026, 10, 14, 18)


def _world(tag: str):
    P._reset_for_tests()
    P._new_id = _Ids()
    clock = [NOW]
    path = _CONF / f"projects-{tag}.db"
    gpath = _CONF / f"goals-{tag}.db"
    for f in (path, gpath):
        if f.exists():
            f.unlink()
    p = P.Projects(path, clock=lambda: clock[0])
    g = G.Goals(gpath, clock=lambda: clock[0], scheduler=_NoSched(),
                bench_reader=lambda pr, b: p.results(pr, b, 1))
    return p, g, clock


def _bench(p, pid, name, unit="", better=None, target=None):
    return p.add_benchmark(pid, {"name": name, "kind": "number", "unit": unit,
                                 "better": better, "target": target}, here=False)["id"]


def heat_cases() -> dict:
    out = {}
    p, g, clock = _world("heat-empty")
    out["empty"] = PR.activity(12, now=NOW, tz=NY, projects=p, goals=g)

    p, g, clock = _world("heat-one")
    pid = p.create({"name": "Running", "kind": "life"}, here=False)["id"]
    b = _bench(p, pid, "5k time", "min", "lower", 25)
    p.log(pid, b, 30, at=ts(2026, 10, 12))
    out["one_day"] = PR.activity(12, now=NOW, tz=NY, projects=p, goals=g)

    p, g, clock = _world("heat-mixed")
    pid = p.create({"name": "Garage", "kind": "life"}, here=False)["id"]
    b = _bench(p, pid, "Boxes cleared", "", "higher", 20)
    plan = [{"step": s, "by": "", "done": False} for s in ("Get quotes", "Pick one", "Book it",
                                                          "Do it", "Tidy up", "Celebrate")]
    gid = g.accept(g.create("Insulate the garage", plan)["id"])["id"]
    for i, day in enumerate((5, 5, 5, 6, 6, 7)):
        clock[0] = ts(2026, 10, day, 9 + i)
        g.mark_step(gid, i, True)
    clock[0] = NOW
    for day, n in ((5, 2), (6, 1), (8, 1), (9, 3)):
        for k in range(n):
            p.log(pid, b, k + 1, at=ts(2026, 10, day, 20))
    clock[0] = NOW
    out["mixed_levels"] = PR.activity(12, now=NOW, tz=NY, projects=p, goals=g)

    p, g, clock = _world("heat-dst")
    pid = p.create({"name": "Writing", "kind": "life"}, here=False)["id"]
    b = _bench(p, pid, "Pages", "", "higher", 100)
    for when in (ts(2026, 3, 7, 23, 30), ts(2026, 3, 8, 1, 30), ts(2026, 3, 8, 3, 30),
                 ts(2026, 3, 8, 23, 30), ts(2026, 3, 9, 0, 30)):
        p.log(pid, b, 1, at=when)
    out["dst_weekend"] = PR.activity(4, now=ts(2026, 3, 12), tz=NY, projects=p, goals=g)

    p, g, clock = _world("heat-private")
    pid = p.create({"name": "Health", "kind": "life"}, here=False)["id"]
    b = _bench(p, pid, "Body weight", "kg", "lower", 70)
    p.log(pid, b, 82, at=ts(2026, 10, 12))
    out["private_number"] = PR.activity(12, now=NOW, tz=NY, projects=p, goals=g)
    for c in out.values():
        c["rects"] = heat_rects(c["days"])
        c["size"] = heat_size(c["weeks"])
    return out


def balance_cases() -> dict:
    out = {}
    p, g, clock = _world("bal-empty")
    out["nothing_picked"] = PR.balance(projects=p, goals=g)

    p, g, clock = _world("bal")
    pid = p.create({"name": "Life", "kind": "life"}, here=False)["id"]
    weight = _bench(p, pid, "Body weight", "kg", "lower", 70)
    run = _bench(p, pid, "Weekly distance", "km", "higher", 20)
    saved = _bench(p, pid, "Emergency fund", "$", "higher", 1000)
    read = _bench(p, pid, "Books read", "", "higher", 12)
    fresh = _bench(p, pid, "Sleep target", "h", "higher", 8)
    for at, v in ((ts(2026, 9, 1), 80), (ts(2026, 10, 1), 75), (ts(2026, 10, 10), 72.5)):
        p.log(pid, weight, v, at=at)
    p.log(pid, run, 5, at=ts(2026, 9, 1))
    p.log(pid, run, 12.5, at=ts(2026, 10, 1))
    p.log(pid, saved, 200, at=ts(2026, 9, 1))
    p.log(pid, saved, 400, at=ts(2026, 10, 1))
    p.log(pid, read, 1, at=ts(2026, 9, 1))
    p.log(pid, read, 12, at=ts(2026, 10, 1))
    gid = g.accept(g.create("Insulate the garage", [{"step": s, "by": "", "done": False}
                                                    for s in ("a", "b", "c", "d", "e")])["id"])["id"]
    for i in range(3):
        g.mark_step(gid, i, True)

    def pick(*items):
        return PR.set_balance({"axes": [dict(kind=k, ref=r, **({"label": lb} if lb else {}))
                                        for k, r, lb in items]}, projects=p, goals=g)

    out["three_areas"] = pick(("bench", run, "Running"), ("bench", saved, ""), ("goal", gid, "Garage"))
    out["five_areas_mixed"] = pick(("bench", weight, ""), ("bench", run, ""), ("bench", saved, ""),
                                   ("bench", read, ""), ("bench", fresh, ""))
    p.log(pid, weight, 68, at=ts(2026, 10, 12))
    out["target_reached_private"] = pick(("bench", weight, ""), ("bench", run, ""),
                                         ("bench", read, ""))
    p.delete_benchmark(pid, run)
    out["after_a_benchmark_is_deleted"] = PR.balance(projects=p, goals=g)
    # A stopped goal leaves the chart like a draft (owner, 2026-09-30).
    p, g, clock = _world("bal-stopped")
    pid = p.create({"name": "Life", "kind": "life"}, here=False)["id"]
    a1 = _bench(p, pid, "Weekly distance", "km", "higher", 20)
    a2 = _bench(p, pid, "Books read", "", "higher", 12)
    p.log(pid, a1, 5, at=ts(2026, 9, 1))
    p.log(pid, a1, 12.5, at=ts(2026, 10, 1))
    p.log(pid, a2, 1, at=ts(2026, 9, 1))
    p.log(pid, a2, 6, at=ts(2026, 10, 1))
    live = g.accept(g.create("Insulate the garage", [{"step": s, "by": "", "done": False}
                                                    for s in ("a", "b")])["id"])["id"]
    gone = g.accept(g.create("Paint the fence", [{"step": s, "by": "", "done": False}
                                                for s in ("a", "b")])["id"])["id"]
    PR.set_balance({"axes": [{"kind": "bench", "ref": a1}, {"kind": "bench", "ref": a2},
                             {"kind": "goal", "ref": live}, {"kind": "goal", "ref": gone}]},
                   projects=p, goals=g)
    g.stop(gone)
    out["after_a_goal_is_stopped"] = PR.balance(projects=p, goals=g)
    for c in out.values():
        c["radar"] = radar([a["fraction"] for a in c["axes"]])
    return out


def refusals() -> dict:
    p, g, clock = _world("refuse")
    pid = p.create({"name": "Life", "kind": "life"}, here=False)["id"]
    a = _bench(p, pid, "A", "u", "higher", 10)
    b = _bench(p, pid, "B", "u", "higher", 10)
    nt = _bench(p, pid, "No finish line", "u")
    out = {}

    def sentence(body):
        code, ans = PR.handle_post("/api/progress/balance", body, projects=p, goals=g)
        return {"status": code, "error": ans.get("error")}
    out["two_areas"] = sentence({"axes": [{"kind": "bench", "ref": a}, {"kind": "bench", "ref": b}]})
    out["nine_areas"] = sentence({"axes": [{"kind": "bench", "ref": a}] * 9})
    out["same_twice"] = sentence({"axes": [{"kind": "bench", "ref": a}, {"kind": "bench", "ref": a},
                                           {"kind": "bench", "ref": b}]})
    out["gone"] = sentence({"axes": [{"kind": "bench", "ref": a}, {"kind": "bench", "ref": b},
                                     {"kind": "bench", "ref": "f" * 32}]})
    out["no_target"] = sentence({"axes": [{"kind": "bench", "ref": a}, {"kind": "bench", "ref": b},
                                          {"kind": "bench", "ref": nt}]})
    out["long_name"] = sentence({"axes": [{"kind": "bench", "ref": a, "label": "x" * 25},
                                          {"kind": "bench", "ref": b}, {"kind": "bench", "ref": a}]})
    return out


def cases() -> dict:
    real_uuid = G.uuid
    G.uuid = _Counted()
    try:
        heat = heat_cases()
        bal = balance_cases()
        refused = refusals()
    finally:
        G.uuid = real_uuid
        P._reset_for_tests()
    worked = {name: radar(f) for name, f in {
        "three_full": [1.0, 1.0, 1.0],
        "four_half": [0.5, 0.5, 0.5, 0.5],
        "five_mixed": [0.0, 0.25, 0.5, 0.75, 1.0],
        "three_with_a_dot": [None, 0.5, 0.5],
        "eight_ramp": [0.125 * i for i in range(1, 9)],
    }.items()}
    return {
        "words": dict(PR.WORDS),
        "levels": [dict(x) for x in PR.LEVELS],
        "shading": dict(SHADING, themes=ladder_report()),
        "limits": {"weeks_default": PR.WEEKS_DEFAULT, "weeks_min": PR.WEEKS_MIN,
                   "weeks_max": PR.WEEKS_MAX, "axes_min": PR.MIN_AXES, "axes_max": PR.MAX_AXES,
                   "label_max": PR.MAX_LABEL, "label_short": PR.MAX_SHORT},
        "heat_grid": {"cell": CELL, "gap": GAP, "step": STEP,
                      "sizes": {str(w): heat_size(w) for w in (4, 12, 26)}},
        "radar_constants": {"size": RADAR_SIZE, "radius": RADAR_R, "label_offset": RADAR_LABEL,
                            "rings": list(RINGS)},
        "radar_worked": worked,
        "heat": heat,
        "balance": bal,
        "refusals": refused,
    }


def render() -> str:
    text = json.dumps(cases(), ensure_ascii=False, indent=1, allow_nan=False) + "\n"
    return text


def main(argv) -> int:
    text = render()
    shutil.rmtree(_CONF, ignore_errors=True)
    if "--check" in argv:
        stale = [str(c.relative_to(ROOT)) for c in COPIES
                 if not c.exists() or c.read_text(encoding="utf-8") != text]
        if stale:
            print("STALE " + ", ".join(stale) + " - run python3 tools/gen_progress_cases.py")
            return 1
        print("progress-cases.json: both copies match")
        return 0
    for c in COPIES:
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", c.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
