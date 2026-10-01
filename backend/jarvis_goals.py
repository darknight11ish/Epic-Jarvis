"""jarvis_goals.py - "Goals with one card per step" (the owner's "build it
now", 2026-09-27, after the Jarvis evaluation; the design is
docs/creativity-2026-09-25/future.md idea 3 and the feasibility audit's I63/
I64, docs/FEASIBILITY-AUDIT-2026-09-26.md).

NEW MODULE, shipped whole (goals.patch adds the routes).

WHAT IT IS FOR, IN PLAIN WORDS
The owner says "I want to get the garage insulated before winter." and
writes (or asks Jarvis, in an ordinary chat message, to suggest) a short
plan: a handful of named steps, each with a rough date. That draft is
edited and accepted here. From then on the goal sits on Coming up, and once
a week Jarvis quietly checks whether the next step is still on track and
says so. Nothing here ever acts. When a step needs real action (search for
installers, draft an email, add a calendar entry), the owner asks Jarvis
for that in an ordinary chat message, and THAT tool use goes through the
exact same per-action approval card any chat turn already goes through -
this module adds no new way to act, and no new gate logic.

WHY THIS MODULE CALLS NO MODEL ITSELF
The creativity doc's own framing has Jarvis draft the first plan. This
module deliberately does not do that call itself: `jarvis_agent.py`'s own
`run_local_turn` is the real, tested way this backend talks to a local
model, and it takes its network calls (`open_stream`/`post`) as callables
supplied by `jarvis_hud.py` - a file that is not in this repository
(docs/ARCHITECTURE.md section 9), so there is no way to verify from here
exactly how it builds those calls. Rather than guess at unverified
internals (the exact mistake CLAUDE.md's "do not claim more than the
evidence supports" section exists to prevent), the drafting step is left to
ordinary chat, which already does this safely and is already shipped: the
owner can simply ask Jarvis to suggest a short plan for a goal, in a normal
message, and paste the result in when creating the goal here (or type their
own). What this module owns is the genuinely new part - keeping a goal, its
plan, and a weekly check-in - not text generation, which chat already does.

NOT THE SAME THING AS "THE PLAN CARD" (docs/FEASIBILITY-AUDIT-2026-09-26.md
I61, CLAUDE.md's "the plan card is allowed later, only after the multi-step
safety tests pass"). That is a BATCHING mechanism: one yes that would run
several safe steps at once, gated behind the multi-step tool-calling safety
tests (I95/tools/tool_eval) because batching approvals is close to
"approves in bulk". Goals never batches anything - every acting step is its
own separate card, exactly like ordinary chat tool use today - so it does
not touch that gate and was not waiting on it. (An earlier evaluation this
session briefly conflated the two before re-checking the source tables;
this docstring exists partly so nobody makes that same mistake twice.)

RULES IT TOUCHES
  * Rule 4 (no auto-approve, no approve-all): accepting a goal approves
    NOTHING that acts - it only starts a repeating check-in, which is data,
    not action. Every acting step still needs its own separate card, raised
    by the ordinary chat/tool path, never by this module.
  * Rule 1 (local-first): this module makes no network call of any kind -
    no model, no cloud, nothing. A goal's words never leave this PC through
    anything in this file.
  * "Before you add anything" (docs/ARCHITECTURE.md section 12): this is a
    KIND on the one scheduler (jarvis_schedule.py), not a timer of its own.
    The weekly check-in needs NO card (the owner's decision of 2026-09-28,
    after the post-change audits): like a plain repeating reminder
    (Kind.plain_repeat, decided 2026-09-26), only the owner's own taps can
    set one up - accepting their own goal - it reads nothing new and acts
    on nothing, and Stop tracking takes it down at once. Every acting step
    still needs its own card, as before; the check-in never covered any.

WHAT IS KEPT, AND WHERE
`goals.db` in the Jarvis settings folder, beside schedule.db and memory.db
(JARVIS_GOALS_DB overrides it, for the tests). One row per goal: the
owner's own words for the goal, its plan (a short JSON list of steps), and
which state it is in. Never written to a log beyond its id, never put on
the event bus beyond ids, never sent anywhere - this file opens no socket.

THE PLAN, KEPT SHORT ON PURPOSE
At most MAX_STEPS steps. The biggest named risk (creativity doc, idea 3) is
nagging and an 8B model being weak at long plans - kept short and editable
answers both. A step is free text plus a free-text rough date/label ("before
winter", "by Friday", or "") - never a strict calendar date, since the goal
is a nudge, not a scheduler entry of its own.

STEP LOCKS, DONE DATES AND THE PACE LINE (2026-09-30, JARVIS-API section 101,
docs/GOALS-PROGRESS-DESIGN.md parts A and B). A step also has a stable `id`
("s1".."s9", given by the PC, so reordering the steps never re-points a
lock), `done_at` (when the owner ticked it; null = unknown, for a step
ticked before this existed), `needs` (up to 3 step ids that must be met
first) and `measure` ({"project", "bench"}: the step is met when that
benchmark's latest number reaches its target). Met = ticked by hand OR its
number reached the target; reaching a target NEVER ticks the step - only the
owner's tap writes a tick. Locked = not met while a `needs` step is not met.
A hand tick on a locked step is refused (Locked, HTTP 409); an untick
clears `done_at` and never cascades. Cycles, unknown ids, a step waiting on
itself and more than 3 `needs` are refused on save by plain code (a
depth-first walk); nothing is stored as SQL. Old plans load with defaults
and get their ids the next time they are saved.

THE WEEKLY CHECK-IN
`on_checkin(goal_id)` is the scheduler's on_fire for kind "goal_checkin". It
looks at the goal's own already-stored plan and picks the first step that
is not met and not locked ("Waiting on X" when every open step is locked), so the nudge is entirely deterministic and cheap - no
model call, no tool call, nothing that could reach outside this file. The
nudge line is kept as the job's `note()` (shown under it in both apps'
Coming up) - never learned as a fact, never counted as an offer
(jarvis_backoff is not involved: this is the owner's own already-accepted
repeat firing on schedule, not something asked for the first time).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

MAX_TEXT = 300           # a goal's own words, and a step's
MAX_STEPS = 7            # "keep plans short" (idea 3's own risk mitigation)
MAX_GOALS = 20           # active + draft goals together
MAX_BY = 40              # a step's rough date/label ("before winter")
MAX_NEEDS = 3            # a step may wait on at most 3 other steps
STEP_IDS = tuple(f"s{i}" for i in range(1, 10))     # "s1".."s9"
_BENCH_ID = re.compile(r"[0-9a-f]{32}")

#: The scheduler kind this module registers on jarvis_schedule.py.
KIND = "goal_checkin"

#: Weekly, Monday morning - a plain default; the owner is not asked to pick
#: a time for this (it is not a repeat they typed, like a reminder).
DEFAULT_RULE = {"every": "week", "at": "09:00", "days": [0]}

STATES = ("draft", "active", "done", "stopped")

# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def db_path() -> Path:
    env = os.environ.get("JARVIS_GOALS_DB")
    return Path(env) if env else _config_dir() / "goals.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id           TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    plan         TEXT NOT NULL,
    status       TEXT NOT NULL,
    created      REAL NOT NULL,
    changed      REAL NOT NULL,
    checkin_job  TEXT
);
"""


# --------------------------------------------------------------------------
#   The plan: validating
# --------------------------------------------------------------------------

def _clean_text(text, limit: int, what: str) -> str:
    t = " ".join(str(text or "").split())
    if not t:
        raise ValueError(f"{what} needs some words")
    if len(t) > limit:
        raise ValueError(f"{what} is longer than {limit} characters - say it more briefly")
    return t


#: The sentences both apps show for a step's lock, word for word
#: (tools/gen_projects_cases.py carries them in the contract file). `{step}`
#: and `{steps}` are step words the PC fills in (shortened to 40 characters).
WORDS = {
    "locked": "locked",
    "after": "after: {steps}",
    "after_open_again": "after: {steps} (open again)",
    "reached": "The number reached its target: {latest} (target {target}).",
    "reached_tick": "{step}: the number reached its target - tick it when you are ready.",
    "waiting_on": "Waiting on \"{step}\".",
    "measure_gone": "The number this step follows is gone - tick it by hand.",
    "locked_refusal": "Do \"{step}\" first, or tick it if it is already done.",
    "self_wait": "\"{step}\" cannot wait on itself.",
    "unknown_wait": "\"{step}\" waits on a step that is not in this plan.",
    "too_many_needs": "\"{step}\" can wait on at most 3 other steps.",
    "circle": "These steps wait on each other in a circle: {steps}.",
    "no_such_benchmark": "\"{step}\" follows a number that does not exist any more.",
    "no_target": "\"{step}\" follows \"{name}\", which has no target yet - set one first.",
}


def _short(text, n: int = 40) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


class Locked(Exception):
    """A tick on a step that is still waiting for another. `waiting_on` are
    the step ids it waits on (HTTP 409, with the sentence)."""

    def __init__(self, message: str, waiting_on=()):
        super().__init__(message)
        self.waiting_on = list(waiting_on)


def _free_id(taken: set, prefer: str) -> str:
    if prefer in STEP_IDS and prefer not in taken:
        return prefer
    for sid in STEP_IDS:
        if sid not in taken:
            return sid
    raise ValueError(f"a plan can have at most {MAX_STEPS} steps")     # unreachable: 9 ids > 7


def load_plan(raw) -> list:
    """A stored plan (JSON text or list) with every field present: an old
    plan without ids gets s1, s2 ... by position, done_at null, needs [],
    measure null. Nothing is written - ids are kept the next time the plan
    is saved."""
    plan = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    taken = set()
    ids = []
    for st in plan:
        sid = st.get("id") if isinstance(st, dict) else None
        if sid in STEP_IDS and sid not in taken:
            taken.add(sid)
            ids.append(sid)
        else:
            ids.append(None)
    out = []
    for i, st in enumerate(plan):
        sid = ids[i] or _free_id(taken, f"s{i + 1}")
        taken.add(sid)
        needs = [n for n in (st.get("needs") or []) if isinstance(n, str)]
        m = st.get("measure")
        measure = ({"project": str(m.get("project")), "bench": str(m.get("bench"))}
                   if isinstance(m, dict) and m.get("project") and m.get("bench") else None)
        done_at = st.get("done_at")
        out.append({"id": sid, "step": st.get("step", ""), "by": st.get("by", ""),
                    "done": bool(st.get("done")),
                    "done_at": (float(done_at) if isinstance(done_at, (int, float))
                                and not isinstance(done_at, bool) and st.get("done") else None),
                    "needs": needs, "measure": measure})
    return out


def check_cycles(steps: list) -> None:
    """ValueError, in a plain sentence naming the steps, for a step that
    waits on itself, on a step that is not in the plan, on more than
    MAX_NEEDS steps, or a loop (s1 waits on s2, s2 waits on s1). Plain
    depth-first walk over at most 7 steps - no stored query, nothing run."""
    by_id = {st["id"]: st for st in steps}
    for st in steps:
        needs = st.get("needs") or []
        if len(needs) > MAX_NEEDS:
            raise ValueError(WORDS["too_many_needs"].format(step=_short(st["step"])))
        for n in needs:
            if n == st["id"]:
                raise ValueError(WORDS["self_wait"].format(step=_short(st["step"])))
            if n not in by_id:
                raise ValueError(WORDS["unknown_wait"].format(step=_short(st["step"])))
    state = {}                                  # id -> 1 (on the path now) or 2 (finished)
    path = []

    def walk(sid):
        state[sid] = 1
        path.append(sid)
        for n in by_id[sid]["needs"]:
            if state.get(n) == 1:
                loop = path[path.index(n):] + [n]
                names = " -> ".join('"' + _short(by_id[x]["step"], 24) + '"' for x in loop)
                raise ValueError(WORDS["circle"].format(steps=names))
            if n not in state:
                walk(n)
        path.pop()
        state[sid] = 2

    for st in steps:
        if st["id"] not in state:
            walk(st["id"])


def clean_plan(plan, previous=None, now: float = 0.0, check_measure=None) -> list:
    """A plan as the owner may set it: a list of {"step", "by", "done"} and,
    optionally, "id", "needs" (step ids) and "measure" ({"project",
    "bench"}); 1-MAX_STEPS long, each step non-empty and short. `previous`
    is the plan as stored (so a step keeps its `done_at`, and a measure
    that did not change is not re-checked); `check_measure(project, bench)`
    returns a sentence, or "" when the benchmark exists and has a target.
    ValueError, with a plain sentence, for anything else - never a stack
    trace reaching an app. `done_at` is never taken from the caller."""
    if not isinstance(plan, list) or not plan:
        raise ValueError("a plan needs at least one step")
    if len(plan) > MAX_STEPS:
        raise ValueError(f"a plan can have at most {MAX_STEPS} steps - "
                         "keep the big ones and drop the rest")
    before = {st["id"]: st for st in (previous or [])}
    taken, given = set(), []
    for item in plan:
        sid = item.get("id") if isinstance(item, dict) else None
        if sid in STEP_IDS and sid not in taken:
            taken.add(sid)
            given.append(sid)
        else:
            given.append(None)
    out = []
    for i, item in enumerate(plan):
        if not isinstance(item, dict):
            raise ValueError("each step is its own step, with its own words")
        step = _clean_text(item.get("step"), MAX_TEXT, "a step")
        by = " ".join(str(item.get("by") or "").split())
        if len(by) > MAX_BY:
            raise ValueError(f"a step's rough date is longer than {MAX_BY} characters")
        done = bool(item.get("done"))
        sid = given[i] or _free_id(taken, f"s{i + 1}")
        taken.add(sid)
        old = before.get(sid)
        if not done:
            done_at = None
        elif old is not None and old["done"]:
            done_at = old["done_at"]          # ticked before: keep when (or that it is unknown)
        else:
            done_at = float(now)
        needs = item.get("needs") or []
        if not isinstance(needs, list) or any(not isinstance(n, str) for n in needs):
            raise ValueError("what a step waits on is a list of step ids")
        needs = list(dict.fromkeys(needs))            # repeats first, then the limit
        if len(needs) > MAX_NEEDS:
            raise ValueError(WORDS["too_many_needs"].format(step=_short(step)))
        measure = item.get("measure")
        if measure is not None:
            if (not isinstance(measure, dict) or not isinstance(measure.get("project"), str)
                    or not isinstance(measure.get("bench"), str)
                    or not _BENCH_ID.fullmatch(measure["project"])
                    or not _BENCH_ID.fullmatch(measure["bench"])):
                raise ValueError(WORDS["no_such_benchmark"].format(step=_short(step)))
            measure = {"project": measure["project"], "bench": measure["bench"]}
            if check_measure is not None and (old is None or old["measure"] != measure):
                why = check_measure(measure["project"], measure["bench"], _short(step))
                if why:
                    raise ValueError(why)
        out.append({"id": sid, "step": step, "by": by, "done": done, "done_at": done_at,
                    "needs": needs, "measure": measure})
    check_cycles(out)
    return out


def bench_reached(view) -> bool:
    """Has this benchmark's latest number reached its own target? `view` is
    what jarvis_projects answers for a benchmark (or None: gone). The
    comparison itself is jarvis_forecast.better_reached - the one place
    "reached" is decided."""
    if not isinstance(view, dict):
        return False
    latest, target, better = view.get("latest"), view.get("target"), view.get("better")
    if not isinstance(latest, dict) or target is None or better not in ("higher", "lower"):
        return False
    v = latest.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    import jarvis_forecast
    return jarvis_forecast.better_reached(v, target, better)


def step_states(plan: list, read_bench=None) -> list:
    """One dict per step, in order - plain code, no model, no stored query:
        state       "done" (ticked), "met_by_number" (not ticked, but its
                    benchmark reached its target), "locked" (not met while
                    a step it needs is not met), or "open"
        waiting_on  ids of the needs that are not met (also on a done step:
                    it then reads "after X (open again)")
        reached     the benchmark reached its target (ticked or not)
        bench       the benchmark view read for it (None: none, or gone)
        unknown     the reader failed for some reason other than "not found":
                    the step is neither gone nor reached, and counts as met
                    for the steps that wait on it (never re-locks them)
    `read_bench(project, bench)` returns a benchmark view, or raises
    KeyError (LookupError) when the benchmark is really gone."""
    cache = {}
    unknown = set()

    def bench_of(m):
        key = (m["project"], m["bench"])
        if key not in cache:
            try:
                cache[key] = read_bench(*key) if read_bench is not None else None
            except LookupError:               # KeyError: the benchmark is really gone
                cache[key] = None
            except Exception:                 # the reader broke: we do not know
                cache[key] = None
                unknown.add(key)
        return cache[key]

    info = []
    for st in plan:
        m = st.get("measure")
        b = bench_of(m) if m else None
        info.append({"bench": b, "reached": bench_reached(b),
                     "unknown": bool(m) and (m["project"], m["bench"]) in unknown})
    # A step whose number could not be read is not "gone" and never locks
    # anyone: for a step that waits on it, it counts as met (the owner can
    # always tick by hand; a broken reader must not re-lock a whole plan).
    met = {st["id"]: bool(st["done"]) or info[i]["reached"] or info[i]["unknown"]
           for i, st in enumerate(plan)}
    out = []
    for i, st in enumerate(plan):
        waiting = [n for n in st.get("needs", []) if not met.get(n, False)]
        if st["done"]:
            state = "done"
        elif info[i]["reached"]:
            state = "met_by_number"
        elif waiting:
            state = "locked"
        else:
            state = "open"
        out.append({"state": state, "waiting_on": waiting, "reached": info[i]["reached"],
                    "bench": info[i]["bench"], "unknown": info[i]["unknown"]})
    return out


def _default_plan(text: str) -> list:
    """No plan given yet: the goal's own words are step one, so a goal can
    always be created with zero extra effort and refined into real steps
    later, in the same edit the owner would use to accept it."""
    return [{"id": "s1", "step": text, "by": "", "done": False, "done_at": None,
             "needs": [], "measure": None}]


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

def _with_unit(v, unit: str) -> str:
    """The number the way jarvis_projects writes it (72.5 kg, $200, 5)."""
    try:
        import jarvis_projects
        return jarvis_projects._with_unit(float(v), unit or "")
    except Exception:
        return f"{v} {unit}".strip()


def _read_bench(project: str, bench: str):
    """The default reader: the benchmark as jarvis_projects answers it
    (a chart-less read, one point). Raises when it does not exist."""
    import jarvis_projects
    return jarvis_projects.get().results(project, bench, 1)


def _leave_balance_chart(goal_id: str) -> None:
    """A stopped goal leaves the owner's balance chart (JARVIS-API section
    105.2). Best effort: the chart also drops it the next time it is read, so
    a failure here loses nothing."""
    try:
        import jarvis_projects
        jarvis_projects.get().axes_drop_goal(goal_id)
    except Exception:
        pass


class Goals:
    """CRUD for goals, plus the weekly check-in's on_fire. `path`, `clock`
    and `scheduler` are replaceable for the tests - no test needs a real
    scheduler or a real model."""

    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time,
                 scheduler=None, bench_reader=None):
        self.path = Path(path) if path else db_path()
        self.now = clock
        self._scheduler = scheduler
        # (project id, benchmark id) -> the benchmark as jarvis_projects
        # answers it (latest, target, better, forecast ...), or raises.
        self._bench_reader = bench_reader or _read_bench
        self._lock = threading.RLock()
        with self._db() as c:
            c.executescript(_SCHEMA)

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def _count_open(self, c) -> int:
        return int(c.execute(
            "SELECT COUNT(*) FROM goals WHERE status IN ('draft','active')").fetchone()[0])

    def _row(self, c, goal_id: str):
        return c.execute("SELECT * FROM goals WHERE id = ?", (str(goal_id),)).fetchone()

    def _view(self, row) -> dict:
        plan = load_plan(row["plan"])
        states = step_states(plan, self._bench_reader)
        names = {st["id"]: st["step"] for st in plan}
        steps = []
        for st, info in zip(plan, states):
            b = info["bench"]
            v = dict(st, state=info["state"], waiting_on=info["waiting_on"], reached=info["reached"])
            after = ", ".join('"' + _short(names.get(n, n)) + '"' for n in info["waiting_on"])
            if not info["waiting_on"]:
                v["lock_words"] = ""
            elif info["state"] == "done":
                v["lock_words"] = WORDS["after_open_again"].format(steps=after)
            else:
                v["lock_words"] = WORDS["after"].format(steps=after)
            v["measure_name"] = b.get("name", "") if b else ""
            v["measure_gone"] = bool(st["measure"]) and b is None and not info["unknown"]
            v["measure_sensitive"] = bool(b and b.get("sensitive"))
            v["reached_words"] = ""
            if info["reached"]:
                unit = b.get("unit", "")
                v["reached_words"] = WORDS["reached"].format(
                    latest=_with_unit(b["latest"]["value"], unit),
                    target=_with_unit(b["target"], unit))
            steps.append(v)
        return {
            "id": row["id"], "text": row["text"], "plan": steps,
            "status": row["status"], "created": row["created"], "changed": row["changed"],
        }

    def _check_measure(self, project: str, bench: str, step: str) -> str:
        """"" when the benchmark exists and has a target and a direction
        (a step cannot follow a number that has no finish line)."""
        try:
            b = self._bench_reader(project, bench)
        except Exception:
            b = None
        if not isinstance(b, dict):
            return WORDS["no_such_benchmark"].format(step=step)
        if b.get("target") is None or b.get("better") not in ("higher", "lower"):
            return WORDS["no_target"].format(step=step, name=_short(b.get("name", "")))
        return ""

    # ---- reading ------------------------------------------------------------

    def get(self, goal_id: str) -> Optional[dict]:
        with self._lock, self._db() as c:
            row = self._row(c, goal_id)
        return self._view(row) if row is not None else None

    def list(self) -> list:
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM goals ORDER BY created DESC").fetchall()
        return [self._view(r) for r in rows]

    # ---- creating a draft ---------------------------------------------------

    def create(self, text: str, plan=None) -> dict:
        """A new goal, in the owner's own words, with a plan - either given
        (the owner's own edit, or something they asked Jarvis to suggest in
        an ordinary chat message first and pasted in here) or, if none was
        given yet, a single-step placeholder made of the goal's own words.
        Calls no gate and raises no card: a draft is content, not action,
        exactly like an email draft (JARVIS-API.md section 40)."""
        text = _clean_text(text, MAX_TEXT, "a goal")
        clean = (clean_plan(plan, None, self.now(), self._check_measure) if plan is not None
                 else _default_plan(text))
        with self._lock, self._db() as c:
            if self._count_open(c) >= MAX_GOALS:
                raise OverflowError(f"there are already {MAX_GOALS} goals - "
                                    "stop tracking one before adding another")
            gid = "g" + uuid.uuid4().hex[:10]
            now = self.now()
            c.execute("INSERT INTO goals (id, text, plan, status, created, changed, "
                      "checkin_job) VALUES (?,?,?,?,?,?,NULL)",
                      (gid, text, json.dumps(clean), "draft", now, now))
        self._audit("goals.draft", {"id": gid})
        return self.get(gid)

    # ---- accepting: the one line that touches the gate ----------------------

    def accept(self, goal_id: str, plan=None) -> dict:
        """The owner's own edit of the draft (or the draft as it stood) is
        kept, and the weekly check-in is set up on jarvis_schedule's own
        repeating jobs - at once, with no card (KIND_OPTIONS' plain_repeat,
        the same as a plain repeating reminder), never a mechanism of its
        own. Approves nothing that acts."""
        with self._lock, self._db() as c:
            row = self._row(c, goal_id)
            if row is None:
                raise KeyError("no such goal")
            if row["status"] != "draft":
                raise ValueError("that goal is not waiting to be accepted")
            current_plan = load_plan(row["plan"])
            goal_text = row["text"]
        clean = (clean_plan(plan, current_plan, self.now(), self._check_measure)
                 if plan is not None else current_plan)
        # A step saved already done in the draft was "done" when the draft was
        # made, not when the owner accepted it. It is dated at accept time - the
        # moment the owner took the plan on (design "Audit amendments") - so a
        # pasted or suggested draft never carries a creation-day date onto the
        # activity heatmap (which counts only accepted goals).
        stamp = self.now()
        clean = [dict(st, done_at=(stamp if st.get("done") else None)) for st in clean]
        if self._scheduler is None:
            raise RuntimeError("the scheduler is not available")
        # has_text=True: the job's own text is the goal's own words (never a
        # raw internal id), so any generic rendering of an unfamiliar kind's
        # text still shows something sensible. It also exempts a repeating
        # job with no text of its own from jarvis_schedule's duplicate-rule
        # check (add_repeat), which would otherwise refuse a SECOND goal
        # whose check-in happens to share the same weekly rule as a first
        # one - every goal here uses the same DEFAULT_RULE on purpose, so
        # that check must not apply. Lookup stays by id (goal_id_for_job),
        # never by parsing this text back.
        job = self._scheduler.add_repeat(KIND, dict(DEFAULT_RULE), text=goal_text, source="app")
        now = self.now()
        with self._lock, self._db() as c:
            c.execute("UPDATE goals SET plan = ?, status = 'active', changed = ?, "
                      "checkin_job = ? WHERE id = ?",
                      (json.dumps(clean), now, job.get("id"), goal_id))
        self._audit("goals.accept", {"id": goal_id, "job": job.get("id")})
        return dict(self.get(goal_id), checkin=job)

    # ---- everyday changes: no card, like ticking off a to-do ----------------

    def mark_step(self, goal_id: str, index, done: bool, *, step_id=None) -> dict:
        """Tick or untick one step (by position, or by `step_id`). No card,
        immediate. Ticking a step that is still locked is refused (Locked);
        unticking clears `done_at` and touches no other step."""
        with self._lock, self._db() as c:
            row = self._row(c, goal_id)
            if row is None:
                raise KeyError("no such goal")
            plan = load_plan(row["plan"])
            if step_id is not None and index is None:
                hits = [i for i, st in enumerate(plan) if st["id"] == step_id]
                if not hits:
                    raise ValueError("that is not one of this goal's steps")
                index = hits[0]
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(plan):
                raise ValueError("that is not one of this goal's steps")
            step = plan[index]
            if bool(done) and not step["done"]:
                info = step_states(plan, self._bench_reader)[index]
                if info["state"] == "locked":
                    names = {st["id"]: st["step"] for st in plan}
                    raise Locked(WORDS["locked_refusal"].format(
                        step=_short(names.get(info["waiting_on"][0], ""))), info["waiting_on"])
            if bool(done):
                if not step["done"]:
                    step["done"], step["done_at"] = True, self.now()
            else:
                step["done"], step["done_at"] = False, None
            now = self.now()
            c.execute("UPDATE goals SET plan = ?, changed = ? WHERE id = ?",
                      (json.dumps(plan), now, goal_id))
        return self.get(goal_id)

    def stop(self, goal_id: str) -> dict:
        """Immediate, one tap - the same rule every "stop tracking this"
        control in this project follows. Deletes the check-in job too, so it
        never fires again for a goal nobody is tracking any more."""
        with self._lock, self._db() as c:
            row = self._row(c, goal_id)
            if row is None:
                raise KeyError("no such goal")
            job = row["checkin_job"]
            now = self.now()
            c.execute("UPDATE goals SET status = 'stopped', changed = ? WHERE id = ?",
                      (now, goal_id))
        if job and self._scheduler is not None:
            try:
                self._scheduler.act(job, "delete")
            except Exception:
                pass
        self._audit("goals.stop", {"id": goal_id})
        _leave_balance_chart(goal_id)
        return self.get(goal_id)

    # ---- the weekly check-in -------------------------------------------------

    def goal_id_for_job(self, job_id: str) -> str:
        """The reverse of `checkin_job` - looked up FROM the goal, never by
        parsing the job's own text (which is the goal's own words, for
        display only - see accept())."""
        with self._lock, self._db() as c:
            row = c.execute("SELECT id FROM goals WHERE checkin_job = ?",
                            (str(job_id),)).fetchone()
        return str(row["id"]) if row is not None else ""

    def next_open_step(self, goal_id: str) -> Optional[dict]:
        """The first step, in the owner's order, that is not met and not
        locked (or met by its number but not ticked yet). None when every
        step is done or every open one is locked."""
        row = self.get(goal_id)
        if row is None:
            return None
        for i, step in enumerate(row["plan"]):
            if step["state"] in ("open", "met_by_number"):
                return {"index": i, **step}
        return None

    def _waiting_on(self, plan: list) -> Optional[dict]:
        """When every unmet step is locked: the first prerequisite that is
        itself open (following the chain), else the first locked step."""
        by_id = {st["id"]: st for st in plan}
        seen = set()
        cur = next((st for st in plan if st["state"] == "locked"), None)
        while cur is not None and cur["id"] not in seen:
            seen.add(cur["id"])
            nxt = next((by_id[n] for n in cur["waiting_on"] if n in by_id
                        and by_id[n]["state"] in ("open", "locked")), None)
            if nxt is None:
                break
            if nxt["state"] == "open":
                return nxt
            cur = nxt
        return cur

    def checkin_note(self, goal_id: str) -> str:
        """The scheduler's `note(job_id)` hook reads this by the goal id the
        job's own `text` field carries. Deterministic - no model, no tool -
        so a check-in is cheap and never wrong about what it read. One
        neutral pace line ("About 6 to 9 weeks at this pace.") may follow
        for a step that follows a NON-private benchmark; a health or money
        benchmark's range stays on its screen (the note shows in Coming up)."""
        row = self.get(goal_id)
        if row is None or row["status"] != "active":
            return ""
        nxt = self.next_open_step(goal_id)
        if nxt is None:
            if any(st["state"] == "locked" for st in row["plan"]):
                wait = self._waiting_on(row["plan"])
                return f'"{row["text"]}": ' + WORDS["waiting_on"].format(step=_short(wait["step"]))
            return f'"{row["text"]}" - every step is marked done.'
        if nxt["state"] == "met_by_number":
            return f'"{row["text"]}": ' + WORDS["reached_tick"].format(step=_short(nxt["step"]))
        by = f" ({nxt['by']})" if nxt["by"] else ""
        note = f'"{row["text"]}": still on track for "{nxt["step"]}"{by}?'
        pace = self._pace_line(nxt)
        return f"{note} {pace}" if pace else note

    def _pace_line(self, step: dict) -> str:
        """The forecast's own words, or "" - only for a step that follows a
        benchmark that is not health or money, and only for a real range."""
        m = step.get("measure")
        if not m:
            return ""
        try:
            b = self._bench_reader(m["project"], m["bench"])
        except Exception:
            return ""
        if not isinstance(b, dict) or b.get("sensitive") or b.get("keep_on_screen"):
            return ""
        f = b.get("forecast")
        if isinstance(f, dict) and f.get("state") == "range":
            return str(f.get("words") or "")
        return ""

    def on_checkin(self, goal_id: str) -> None:
        """register_kind's on_fire for KIND. Calls no model, no tool, and
        raises no card: it only ever re-reads a goal this module already
        owns, and its whole output is a nudge line the apps show under the
        job - never an action, never learned, never sent anywhere."""
        try:
            self.checkin_note(goal_id)
        except Exception:
            pass  # a bad read here must never take the scheduler's loop down

    def _audit(self, event: str, detail: dict) -> None:
        try:
            if fw is not None:
                fw.audit_log(event, detail)
        except Exception:
            pass


# --------------------------------------------------------------------------
#   The one this backend uses, and its scheduler wiring
# --------------------------------------------------------------------------

_ONE: Optional[Goals] = None
_ONE_LOCK = threading.Lock()


def get() -> Goals:
    global _ONE
    with _ONE_LOCK:
        if _ONE is None:
            import jarvis_schedule
            _ONE = Goals(scheduler=jarvis_schedule.get())
        return _ONE


#: How KIND is registered on the one scheduler (register() below; the tests
#: use the same). plain_repeat=True: the weekly check-in is set up at once,
#: with NO card (the owner, 2026-09-28) - only the owner's own tap on Accept
#: sets one, it reads nothing new and acts on nothing, and Stop tracking
#: deletes it at once; the rule plain repeating reminders already follow
#: (decided 2026-09-26).
KIND_OPTIONS = dict(has_text=True, repeatable=True, plain_repeat=True,
                    what="set up a weekly check-in for a goal")


def register() -> None:
    """Called once, at import, by jarvis_hud.py's own startup block
    (goals.patch) - registers KIND on the one scheduler with this module's
    own on_checkin as its on_fire, and a `note` hook so both apps' Coming up
    can show the nudge without a second read."""
    import jarvis_schedule
    g = get()
    jarvis_schedule.register_kind(
        KIND, "goal check-in", "Jarvis: a goal check-in is due.",
        on_fire=lambda job_id: g.on_checkin(g.goal_id_for_job(job_id)),
        note=lambda job_id: g.checkin_note(g.goal_id_for_job(job_id)),
        **KIND_OPTIONS)


# --------------------------------------------------------------------------
#   The routes both apps call
# --------------------------------------------------------------------------

PATH = "/api/goals"
_TAILS = ("accept", "step", "stop")


def _goal_route(route: str):
    """None, or (goal_id, tail) for PATH itself (tail ""), PATH/<id>
    (tail ""), or PATH/<id>/(accept|step|stop)."""
    if not isinstance(route, str) or route == PATH:
        return None
    if not route.startswith(PATH + "/"):
        return None
    parts = route[len(PATH) + 1:].split("/")
    if len(parts) == 1 and parts[0]:
        return parts[0], ""
    if len(parts) == 2 and parts[0] and parts[1] in _TAILS:
        return parts[0], parts[1]
    return None


def _err(exc) -> tuple:
    """(http_status, body) for one of the plain exceptions the store raises
    - never a stack trace reaching an app."""
    if isinstance(exc, Locked):
        return 409, {"ok": False, "error": str(exc), "locked": True,
                     "waiting_on": exc.waiting_on}
    if isinstance(exc, KeyError):
        return 404, {"ok": False, "error": "no such goal"}
    if isinstance(exc, ValueError):
        return 400, {"ok": False, "error": str(exc)}
    if isinstance(exc, OverflowError):
        return 409, {"ok": False, "error": str(exc)}
    if isinstance(exc, RuntimeError):
        return 503, {"ok": False, "error": str(exc)}
    return 503, {"ok": False, "error": type(exc).__name__}


def handle_get(route: str) -> tuple:
    if route == PATH:
        return 200, {"ok": True, "goals": get().list(),
                     "limits": {"text": MAX_TEXT, "steps": MAX_STEPS, "goals": MAX_GOALS,
                               "by": MAX_BY, "needs": MAX_NEEDS},
                     "words": dict(WORDS)}
    hit = _goal_route(route)
    if hit is None or hit[1] != "":
        return 404, {"ok": False, "error": "no such goal"}
    goal = get().get(hit[0])
    if goal is None:
        return 404, {"ok": False, "error": "no such goal"}
    return 200, {"ok": True, "goal": goal}


def handle_post(route: str, body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    if route == PATH:
        try:
            goal = get().create(body.get("text"), body.get("plan"))
        except Exception as exc:
            return _err(exc)
        return 200, {"ok": True, "goal": goal}
    hit = _goal_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "no such goal"}
    goal_id, tail = hit
    try:
        if tail == "accept":
            goal = get().accept(goal_id, body.get("plan"))
        elif tail == "step":
            index, done = body.get("index"), body.get("done")
            sid = body.get("id")
            if sid is not None and not isinstance(sid, str):
                raise ValueError("that is not one of this goal's steps")
            goal = get().mark_step(goal_id, index, done, step_id=sid)
        elif tail == "stop":
            goal = get().stop(goal_id)
        else:
            return 404, {"ok": False, "error": "no such goal"}
    except Exception as exc:
        return _err(exc)
    return 200, {"ok": True, "goal": goal}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the goals routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original - the same shape every
    optional, whole-module feature in this backend uses (jarvis_news.py,
    jarvis_tool_updates.py, ...)."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_goals", False):
        _ARMED = True
        return "  goals      Goals (already on)"

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

    def _path(self) -> str:
        from urllib.parse import urlsplit
        return urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")

    def do_GET(self):
        route = _path(self)
        if route != PATH and _goal_route(route) is None:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = _path(self)
        if route != PATH and _goal_route(route) is None:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_goals = True
    do_POST._jarvis_goals = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        register()
    except Exception as exc:
        _ARMED = True
        return f"  goals      NOT ON ({type(exc).__name__}) - Goals is off"
    _ARMED = True
    return f"  goals      Goals: {len(get().list())} tracked"


_ARMED = False


def _reset_for_tests() -> None:
    global _ONE, _ARMED
    with _ONE_LOCK:
        _ONE = None
    _ARMED = False
