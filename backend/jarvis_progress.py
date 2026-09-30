"""jarvis_progress.py - the activity heatmap and the owner's balance chart
(the owner's decision of 2026-09-30, docs/BUILD-QUEUE-2026-09-30.md item 7;
docs/GOALS-PROGRESS-DESIGN.md part C and its "Progress contract (frozen)";
docs/JARVIS-API.md section 105).

NEW MODULE, shipped whole (progress.patch adds the routes).

WHAT IT IS FOR, IN PLAIN WORDS
Two small pictures for Brain -> Projects, both drawn on the owner's own
screen from the owner's own ticks and numbers:

  * the ACTIVITY HEATMAP: about 12 weeks of days, each shaded by how many
    things were done that day - goal steps ticked (their `done_at`) plus
    numbers logged in benchmarks (by the date the number is for). An empty
    day is simply neutral. There is NO streak, no "longest run", no
    percentage of days and nothing red for a quiet day.
  * the BALANCE CHART (a radar): 3 to 8 areas the OWNER picks from their own
    benchmarks and goals. Each spoke is "how far from your first number to
    your target"; the real value is printed at each spoke. There is NO
    overall score, no average and no area - only the list of areas.

EVERY NUMBER AND SENTENCE COMES FROM CODE. No model writes a shade, a
fraction or a word here, and this module calls none.

HEALTH AND MONEY (CLAUDE.md, the owner's answer of 2026-09-30: "the heatmap
shades a day for a sensitive number WITHOUT naming it")
  * The heatmap sends dates and counts only - never a benchmark's name or a
    step's words - so a private number shades its day and nothing more.
  * `keep_on_screen` says a private item is in the picture; the apps then
    hide the picture under "Hide memory lists and chat history".
  * The balance chart may hold a private axis (the owner picked it): its
    words are the owner's own screen only - flagged `keep_on_screen` too.
  * NOTHING HERE REACHES A MODEL. It is not a tool in jarvis_agent.py, is
    not imported by it, and is not in any prompt, quick command, web search,
    chatbot text, notification or spoken answer. test_progress.py fails if
    any other module starts importing it.

WHAT IS KEPT: one small table, `balance_axes`, in projects.db (kind, ids and
the owner's label - no numbers). Choosing the axes is the owner's own display
choice, like sorting a list: no approval card. The audit log gets counts only.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
from typing import Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Limits and words
# --------------------------------------------------------------------------

WEEKS_DEFAULT = 12
WEEKS_MIN = 4
WEEKS_MAX = 26
MIN_AXES = 3
MAX_AXES = 8
MAX_LABEL = 24
MAX_CHOICES = 60

#: count -> level: 0, 1, 2, 3-4, 5 or more.
LEVELS = (
    {"level": 0, "min": 0, "max": 0},
    {"level": 1, "min": 1, "max": 1},
    {"level": 2, "min": 2, "max": 2},
    {"level": 3, "min": 3, "max": 4},
    {"level": 4, "min": 5, "max": None},
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: The sentences both apps show or build from. `{...}` is filled by the PC
#: (the answers carry finished sentences); the apps need only the fixed
#: labels. Nothing here is a streak, a score or a scolding.
WORDS = {
    "title": "Progress",
    "heat_title": "Activity",
    "heat_under": "Steps you tick and numbers you log, day by day. A quiet day is just a quiet day.",
    "heat_total": "Last {weeks} weeks: {things} on {days}.",
    "heat_empty": "Nothing here yet. A step you tick or a number you log will show on its day.",
    "heat_undated": "Steps ticked before this was added have no date, so they are not shown.",
    "day_some": "{things} on {date}",
    "day_none": "Nothing on {date}",
    "week_of": "Week of {date}",
    "balance_title": "Balance",
    "balance_under": ("Pick 3 to 8 of your numbers or goals. Each spoke shows how far you are "
                      "from your first number to your target. There is no total."),
    "balance_none": "Nothing picked yet.",
    "balance_few": "Pick at least 3 to see the chart.",
    "balance_edit": "Choose what to show",
    "balance_save": "Save the chart",
    "balance_clear": "Clear the chart",
    "balance_rename": "Name on the chart",
    "balance_limit": "Pick 3 to 8 areas, or none to clear the chart.",
    "no_numbers": "no numbers yet",
    "no_target": "no target yet",
    "no_steps": "no steps yet",
    "gone": "gone",
    "no_choices": "Nothing to pick from yet. Give a number a target, or accept a goal.",
    "hidden": "Hidden while memory lists and chat history are hidden.",
    "private": "Health or money: kept on screen, never read aloud or sent anywhere.",
    "summary_heat": "Activity, last {weeks} weeks. {total}",
    "summary_balance": "Balance chart, {n} areas. {items} No overall score.",
}

# The words the module must never send (test_progress.py checks every string).
FORBIDDEN_WORDS = ("streak", "in a row", "longest", "missed", "keep it up", "don't break",
                   "percent", "average", "points")

_ID = re.compile(r"[0-9a-f]{32}")
_GOAL = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class Refused(ValueError):
    """A refusal with a plain sentence the app shows as sent (a 400)."""


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Days (local time, DST-safe)
# --------------------------------------------------------------------------


def local_date(ts, tz=None) -> Optional[_dt.date]:
    """The calendar day of `ts` (seconds) in the owner's own time zone. `tz`
    None = this PC's local zone, which knows daylight saving for THAT date
    (datetime.fromtimestamp; a fixed offset taken today would be wrong for
    days on the other side of a clock change). None for a value that is not
    a sane time."""
    try:
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
            return None
        return _dt.datetime.fromtimestamp(float(ts), tz).date()
    except (OverflowError, OSError, ValueError):
        return None


def _stamp(d: _dt.date, tz=None) -> float:
    """A moment on day `d` (local midnight) as seconds - used only to bound a
    database read, so a clock change moving it an hour is harmless."""
    dt = _dt.datetime.combine(d, _dt.time.min)
    if tz is not None:
        dt = dt.replace(tzinfo=tz)
    return dt.timestamp()


def date_label(d: _dt.date) -> str:
    """"12 Oct" - English, the same in both apps (never the phone's locale)."""
    return f"{d.day} {_MONTHS[d.month - 1]}"


def level_of(count: int) -> int:
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count == 2:
        return 2
    return 3 if count <= 4 else 4


def _things(n: int) -> str:
    return f"{n} thing" if n == 1 else f"{n} things"


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def clamp_weeks(weeks) -> int:
    try:
        if isinstance(weeks, bool):
            raise TypeError
        w = int(float(weeks))
    except (TypeError, ValueError, OverflowError):
        return WEEKS_DEFAULT
    return max(WEEKS_MIN, min(WEEKS_MAX, w))


# --------------------------------------------------------------------------
#   The stores (replaceable for the tests)
# --------------------------------------------------------------------------


def _projects():
    import jarvis_projects
    return jarvis_projects.get()


def _goals():
    import jarvis_goals
    return jarvis_goals.get()


def _goal_state(goals) -> tuple:
    """(every goal, could goals be read). Unreadable goals give ([], False):
    the heatmap still draws from the numbers, and the balance chart never
    forgets a goal axis just because goals.db was briefly unavailable."""
    try:
        g = goals if goals is not None else _goals()
        return list(g.list()), True
    except Exception:
        return [], False


def _goal_list(goals) -> list:
    return _goal_state(goals)[0]


def _sensitive_text(text: str) -> bool:
    try:
        import jarvis_projects
        return bool(jarvis_projects.auto_sensitive(text or ""))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   The activity heatmap
# --------------------------------------------------------------------------


def activity(weeks=WEEKS_DEFAULT, *, now: float, tz=None, projects=None, goals=None) -> dict:
    """The answer of GET /api/progress/activity. Weeks start on Monday; the
    grid runs from the Monday `weeks - 1` weeks before this week's Monday to
    TODAY - future days are not sent. Dates and counts only."""
    weeks = clamp_weeks(weeks)
    today = local_date(now, tz)
    if today is None:
        raise Refused("the clock is not set to a sensible time")
    monday = today - _dt.timedelta(days=today.weekday())
    start = monday - _dt.timedelta(days=7 * (weeks - 1))
    counts: dict = {}
    private = False

    p = projects if projects is not None else _projects()
    lo = _stamp(start - _dt.timedelta(days=2), tz)
    hi = _stamp(today + _dt.timedelta(days=3), tz)
    for at, sensitive in p.activity_results(lo, hi):
        d = local_date(at, tz)
        if d is None or d < start or d > today:
            continue
        counts[d] = counts.get(d, 0) + 1
        private = private or bool(sensitive)

    for goal in _goal_list(goals):
        for st in goal.get("plan") or []:
            if not st.get("done"):
                continue
            d = local_date(st.get("done_at"), tz)
            if d is None or d < start or d > today:
                continue
            counts[d] = counts.get(d, 0) + 1
            if st.get("measure_sensitive") or _sensitive_text(st.get("step", "")):
                private = True

    days = []
    total = 0
    active = 0
    d = start
    while d <= today:
        n = counts.get(d, 0)
        off = (d - start).days
        label = date_label(d)
        days.append({
            "date": d.isoformat(), "col": off // 7, "row": off % 7, "count": n,
            "level": level_of(n),
            "words": (WORDS["day_some"].format(things=_things(n), date=label) if n
                      else WORDS["day_none"].format(date=label)),
        })
        total += n
        active += 1 if n else 0
        d += _dt.timedelta(days=1)
    columns = [{"col": i, "label": WORDS["week_of"].format(
        date=date_label(start + _dt.timedelta(days=7 * i)))} for i in range(weeks)]
    line = (WORDS["heat_total"].format(weeks=weeks, things=_things(total), days=_days(active))
            if total else WORDS["heat_empty"])
    return {
        "ok": True, "available": True, "title": WORDS["heat_title"], "weeks": weeks,
        "from": start.isoformat(), "to": today.isoformat(), "today": today.isoformat(),
        "columns": columns, "days": days, "total": total, "days_active": active,
        "empty": total == 0, "words": line, "note": WORDS["heat_undated"],
        "summary": WORDS["summary_heat"].format(weeks=weeks, total=line),
        "levels": [dict(x) for x in LEVELS],
        "keep_on_screen": private,
        "hidden_words": WORDS["hidden"],
    }


# --------------------------------------------------------------------------
#   The balance chart
# --------------------------------------------------------------------------


def _num(v: float) -> str:
    if float(v).is_integer() and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _with_unit(v: float, unit: str) -> str:
    n = _num(v)
    if not unit:
        return n
    if unit in ("$", "£", "€"):
        return f"{unit}{n}"
    if unit == "%":
        return f"{n}%"
    return f"{n} {unit}"


def _finite(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))


def fraction(first, latest, target, better) -> Optional[float]:
    """How far the latest number is from the first number to the target:
    0.0 (no closer, or further away) to 1.0 (the target reached or passed).
    None when there is nothing to measure (a missing or non-finite number,
    no direction). Works for "higher is better" and "lower is better".
    A first number that already sat at or past the target has no distance
    to cover: it reads 0.0 until the target is met. Never NaN, never > 1."""
    if better not in ("higher", "lower"):
        return None
    if not (_finite(first) and _finite(latest) and _finite(target)):
        return None
    met = latest >= target if better == "higher" else latest <= target
    if met:
        return 1.0
    gap = target - first
    if (better == "higher" and gap <= 0) or (better == "lower" and gap >= 0):
        return 0.0
    try:
        f = (latest - first) / gap
    except (OverflowError, ZeroDivisionError):
        return None
    if not math.isfinite(f):
        return None
    return round(max(0.0, min(1.0, f)), 4)


def _short(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _bench_axis(b: dict) -> dict:
    """The axis fields for one benchmark (see progress_bench)."""
    unit = b["unit"] or ""
    frac = None
    if not b["count"] or not _finite(b["latest"]):
        state, words = "no_numbers", WORDS["no_numbers"]
    elif not (_finite(b["target"]) and b["better"] in ("higher", "lower")):
        state, words = "no_target", WORDS["no_target"]
    else:
        frac = fraction(b["first"], b["latest"], b["target"], b["better"])
        met = (b["latest"] >= b["target"] if b["better"] == "higher"
               else b["latest"] <= b["target"])
        state = "reached" if met else "progress"
        lead = (_with_unit(b["latest"], unit) if unit in ("$", "£", "€", "%")
                else _num(b["latest"]))
        words = f"{lead} of {_with_unit(b['target'], unit)}"
    return {"state": state, "value_words": words, "fraction": frac,
            "keep_on_screen": bool(b["sensitive"]), "default_name": b["name"],
            "project": b["project"]}


def _goal_axis(g: dict) -> dict:
    plan = g.get("plan") or []
    total = len(plan)
    done = sum(1 for st in plan if st.get("done"))
    private = _sensitive_text(g.get("text", "")) or any(
        st.get("measure_sensitive") for st in plan)
    if not total:
        return {"state": "no_steps", "value_words": WORDS["no_steps"], "fraction": None,
                "keep_on_screen": private, "default_name": g.get("text", ""), "project": ""}
    return {"state": "reached" if done == total else "progress",
            "value_words": f"{done} of {total} step" + ("" if total == 1 else "s"),
            "fraction": round(done / total, 4), "keep_on_screen": private,
            "default_name": g.get("text", ""), "project": ""}


def _resolve(a: dict, p, goals_by_id: dict) -> Optional[dict]:
    """One stored axis -> its finished answer, or None when the thing is gone."""
    if a["kind"] == "bench":
        b = p.progress_bench(a["ref"])
        if b is None:
            return None
        core = _bench_axis(b)
    else:
        g = goals_by_id.get(a["ref"])
        if g is None or g.get("status") == "draft":
            return None
        core = _goal_axis(g)
    label = _short(a.get("label") or core["default_name"], MAX_LABEL)
    return {"label": label, "name": _short(core["default_name"], 60), "kind": a["kind"],
            "ref": a["ref"], "project": core["project"], "state": core["state"],
            "value_words": core["value_words"], "fraction": core["fraction"],
            "keep_on_screen": core["keep_on_screen"]}


def choices(p, goals_list: list, picked: set) -> list:
    out = []
    for b in p.progress_benchmarks():
        out.append({"kind": "bench", "ref": b["id"], "project": b["project"],
                    "project_name": b["project_name"], "name": _short(b["name"], 60),
                    "picked": ("bench", b["id"]) in picked,
                    "keep_on_screen": bool(b["sensitive"])})
    for g in goals_list:
        if g.get("status") != "active" or not g.get("plan"):
            continue
        out.append({"kind": "goal", "ref": g["id"], "project": "", "project_name": "",
                    "name": _short(g.get("text", ""), 60),
                    "picked": ("goal", g["id"]) in picked,
                    "keep_on_screen": _goal_axis(g)["keep_on_screen"]})
    return out[:MAX_CHOICES]


def balance(*, projects=None, goals=None) -> dict:
    """The answer of GET /api/progress/balance. Axes whose benchmark or goal
    is gone are dropped from the stored chart here (and there), so a
    deleted thing never leaves a hollow spoke."""
    p = projects if projects is not None else _projects()
    goals_list, goals_ok = _goal_state(goals)
    by_id = {g["id"]: g for g in goals_list}
    stored = p.axes_read()
    axes, keep = [], []
    for a in stored:
        if a["kind"] == "goal" and not goals_ok:
            continue          # cannot tell: leave it stored, do not draw it
        r = _resolve(a, p, by_id)
        if r is None:
            continue
        axes.append(r)
        keep.append(a)
    if goals_ok and len(keep) != len(stored):
        p.axes_write(keep)
    picked = {(a["kind"], a["ref"]) for a in axes}
    drawable = len(axes) >= MIN_AXES
    items = " ".join(f"{a['label']}: {a['value_words']}." for a in axes)
    if not axes:
        line = WORDS["balance_none"]
    elif not drawable:
        line = WORDS["balance_few"]
    else:
        line = ""
    return {
        "ok": True, "available": True, "title": WORDS["balance_title"],
        "axes": axes, "drawable": drawable, "min": MIN_AXES, "max": MAX_AXES,
        "max_label": MAX_LABEL, "words": line,
        "summary": (WORDS["summary_balance"].format(n=len(axes), items=items) if axes else line),
        "choices": choices(p, goals_list, picked),
        "keep_on_screen": any(a["keep_on_screen"] for a in axes),
        "hidden_words": WORDS["hidden"],
    }


def _label(v) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise Refused("a name on the chart is words")
    v = " ".join(_CTRL.sub(" ", v).split())
    if len(v) > MAX_LABEL:
        raise Refused(f"a name on the chart is at most {MAX_LABEL} characters")
    return v


def set_balance(body, *, projects=None, goals=None) -> dict:
    """POST /api/progress/balance {"axes": [{"kind", "ref", "label"?}]}. 3 to
    8 areas, or none to clear. Replaces the whole chart; nothing changes if
    anything is refused. No card: the owner's own display choice."""
    if not isinstance(body, dict) or not isinstance(body.get("axes"), list):
        raise Refused('send {"axes": [{"kind": "bench" or "goal", "ref": "..."}]}')
    raw = body["axes"]
    if len(raw) and not MIN_AXES <= len(raw) <= MAX_AXES:
        raise Refused(WORDS["balance_limit"])
    p = projects if projects is not None else _projects()
    by_id = {g["id"]: g for g in _goal_list(goals)}
    seen, keep = set(), []
    for item in raw:
        if not isinstance(item, dict):
            raise Refused("each area is an object with a kind and a ref")
        kind, ref = item.get("kind"), item.get("ref")
        if kind not in ("bench", "goal") or not isinstance(ref, str):
            raise Refused('each area is {"kind": "bench" or "goal", "ref": its id}')
        if (kind, ref) in seen:
            raise Refused("Each area can be on the chart once.")
        seen.add((kind, ref))
        label = _label(item.get("label"))
        if kind == "bench":
            b = p.progress_bench(ref) if _ID.fullmatch(ref) else None
            if b is None:
                raise Refused("One of those numbers is gone.")
            if not (_finite(b["target"]) and b["better"] in ("higher", "lower")):
                raise Refused(f'Give "{_short(b["name"], 40)}" a target and say which way is '
                              "better first - the chart measures each area against its target.")
            keep.append({"kind": "bench", "project": b["project"], "ref": ref, "label": label})
        else:
            g = by_id.get(ref) if _GOAL.fullmatch(ref) else None
            if g is None or g.get("status") != "active":
                raise Refused("One of those goals is gone or not accepted yet.")
            keep.append({"kind": "goal", "project": "", "ref": ref, "label": label})
    p.axes_write(keep)
    return balance(projects=p, goals=goals)


# --------------------------------------------------------------------------
#   The routes (docs/JARVIS-API.md section 105)
# --------------------------------------------------------------------------

PATH = "/api/progress"
_GET_ROUTES = (PATH + "/activity", PATH + "/balance")
_POST_ROUTES = (PATH + "/balance",)


def handle_get(route: str, query: str = "", *, now: Optional[float] = None, tz=None,
               projects=None, goals=None) -> tuple:
    import time as _time
    try:
        if route == PATH + "/activity":
            q = parse_qs(query or "")
            w = (q.get("weeks") or [WEEKS_DEFAULT])[0]
            return 200, activity(w, now=_time.time() if now is None else now, tz=tz,
                                 projects=projects, goals=goals)
        if route == PATH + "/balance":
            return 200, balance(projects=projects, goals=goals)
    except Refused as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    except Exception as exc:
        return 503, {"ok": False, "available": False, "error": type(exc).__name__}
    return 404, {"ok": False, "error": "no such route"}


def handle_post(route: str, body, *, projects=None, goals=None) -> tuple:
    if route != PATH + "/balance":
        return 404, {"ok": False, "error": "no such route"}
    try:
        return 200, set_balance(body, projects=projects, goals=goals)
    except Refused as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    except Exception as exc:
        return 503, {"ok": False, "available": False, "error": type(exc).__name__}


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap do_GET and do_POST so the progress routes are answered here,
    after the server's own origin and token checks. Every other request
    goes straight to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_progress", False):
        _ARMED = True
        return "  progress   Activity heatmap and balance chart (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in _GET_ROUTES:
            return get0(self)
        if not _allowed(self):
            return None
        code, out = handle_get(route, parts.query)
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in _POST_ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        code, out = handle_post(route, body)
        return self._send(code, out)

    do_GET._jarvis_progress = True
    do_POST._jarvis_progress = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  progress   Activity heatmap and balance chart: on"


_ARMED = False


def _reset_for_tests() -> None:
    global _ARMED
    _ARMED = False
