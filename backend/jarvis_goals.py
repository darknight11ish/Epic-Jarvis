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

THE WEEKLY CHECK-IN
`on_checkin(goal_id)` is the scheduler's on_fire for kind "goal_checkin". It
looks at the goal's own already-stored plan and picks the first step not
yet marked done, so the nudge is entirely deterministic and cheap - no
model call, no tool call, nothing that could reach outside this file. The
nudge line is kept as the job's `note()` (shown under it in both apps'
Coming up) - never learned as a fact, never counted as an offer
(jarvis_backoff is not involved: this is the owner's own already-accepted
repeat firing on schedule, not something asked for the first time).
"""
from __future__ import annotations

import json
import os
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


def clean_plan(plan) -> list:
    """A plan as the owner may set it: a list of {"step", "by", "done"},
    1-MAX_STEPS long, each step non-empty and short. ValueError, with a
    plain sentence, for anything else - never a stack trace reaching an app."""
    if not isinstance(plan, list) or not plan:
        raise ValueError("a plan needs at least one step")
    if len(plan) > MAX_STEPS:
        raise ValueError(f"a plan can have at most {MAX_STEPS} steps - "
                         "keep the big ones and drop the rest")
    out = []
    for item in plan:
        if not isinstance(item, dict):
            raise ValueError("each step is its own step, with its own words")
        step = _clean_text(item.get("step"), MAX_TEXT, "a step")
        by = " ".join(str(item.get("by") or "").split())
        if len(by) > MAX_BY:
            raise ValueError(f"a step's rough date is longer than {MAX_BY} characters")
        done = bool(item.get("done"))
        out.append({"step": step, "by": by, "done": done})
    return out


def _default_plan(text: str) -> list:
    """No plan given yet: the goal's own words are step one, so a goal can
    always be created with zero extra effort and refined into real steps
    later, in the same edit the owner would use to accept it."""
    return [{"step": text, "by": "", "done": False}]


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

class Goals:
    """CRUD for goals, plus the weekly check-in's on_fire. `path`, `clock`
    and `scheduler` are replaceable for the tests - no test needs a real
    scheduler or a real model."""

    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time,
                 scheduler=None):
        self.path = Path(path) if path else db_path()
        self.now = clock
        self._scheduler = scheduler
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

    @staticmethod
    def _view(row) -> dict:
        return {
            "id": row["id"], "text": row["text"], "plan": json.loads(row["plan"]),
            "status": row["status"], "created": row["created"], "changed": row["changed"],
        }

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
        clean = clean_plan(plan) if plan is not None else _default_plan(text)
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
            current_plan = json.loads(row["plan"])
            goal_text = row["text"]
        clean = clean_plan(plan) if plan is not None else current_plan
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

    def mark_step(self, goal_id: str, index: int, done: bool) -> dict:
        with self._lock, self._db() as c:
            row = self._row(c, goal_id)
            if row is None:
                raise KeyError("no such goal")
            plan = json.loads(row["plan"])
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(plan):
                raise ValueError("that is not one of this goal's steps")
            plan[index]["done"] = bool(done)
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
        row = self.get(goal_id)
        if row is None:
            return None
        for i, step in enumerate(row["plan"]):
            if not step.get("done"):
                return {"index": i, **step}
        return None

    def checkin_note(self, goal_id: str) -> str:
        """The scheduler's `note(job_id)` hook reads this by the goal id the
        job's own `text` field carries. Deterministic - no model, no tool -
        so a check-in is cheap and never wrong about what it read."""
        row = self.get(goal_id)
        if row is None or row["status"] != "active":
            return ""
        nxt = self.next_open_step(goal_id)
        if nxt is None:
            return f'"{row["text"]}" - every step is marked done.'
        by = f" ({nxt['by']})" if nxt["by"] else ""
        return f'"{row["text"]}": still on track for "{nxt["step"]}"{by}?'

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
                               "by": MAX_BY}}
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
            goal = get().mark_step(goal_id, index, done)
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
