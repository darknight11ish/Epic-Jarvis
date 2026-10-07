"""jarvis_referee.py - "Referee suggestions": Jarvis asks "This looks done - tick
it?" when a goal step's number reaches its target (the owner's decision of
2026-09-30; JARVIS-API section 108, docs/STUDY-FROM-TEXT-DESIGN.md section 13).

NEW MODULE, shipped whole (referee.patch adds the gate line and the startup block).

WHAT IT IS, IN PLAIN WORDS
A goal step can follow a number (a benchmark in Projects: "5k time", "savings").
When the newest number reaches the target the owner set, the step is only ever
TICKED by the owner's own tap (JARVIS-API section 101). This switch adds one
thing: a quiet look every hour, and - if a step's number has reached its
target and the step is still open - ONE card asking "This looks done - tick
it?", with the numbers on it. Yes ticks the step, exactly as the owner's own
tick would (Goals.mark_step: the PC sets done_at). No changes nothing, and the
same step is not asked about again for a day, then a week, then a month.

IT IS A SECOND-CARD SWITCH THAT LOADS NO MODEL (today)
It is the seventh switch in jarvis_second_card.FEATURES, id "referee", built
switched off like the rest and only switchable on with a capable second card.
The evidence on the card is worked out by CODE from the numbers
(jarvis_forecast.better_reached, the one place "reached" is decided) - no model
words it, so no model can misstate it. That is why the switch is marked
model_free: it starts no second Ollama and uses none of the card's memory. The
later step (reading a project task's change summary, where a small model's
opinion WOULD be used) is a follow-up; its card would say "a guess by the small
model, not a check" instead of the wording below.

WHAT IT MUST NEVER DO (each has a test in test_referee.py)
  * Write a tick itself. The ONLY call that changes a goal is
    Goals.mark_step, made in _decide after a person answered the card "yes" -
    never from a pass, a route or a tool. No model is called here at all.
  * Write a VERIFIED flag or a benchmark result, or run a test or a command.
    Test runs stay on the projects module's own path, with its own card.
  * Act on outside text. There is no route, no tool and no argument that takes
    words: the only trigger is the scheduler's hourly step, and the only input
    is the owner's own goals and logged numbers.
  * Nag. At most MAX_PER_DAY cards in any 24 hours; never while a card of its
    own is waiting; never while a focus session runs; never in Quiet or
    Standby, while the owner is mid-chat, or for a step the owner said no to
    recently (jarvis_backoff: 1 day, 7, then 30); the same step at most once a
    day even if nobody answered.
  * Say a private number aloud or send it anywhere. A health or money benchmark
    (jarvis_projects' own flags) gets a card marked keep_on_screen with a line
    saying so; nothing here is logged beyond ids and counts, and the words of
    the gate's `what` never hold a number or a name.

THE ONE SCHEDULER. KIND "referee" is a quiet, single, hourly job on
jarvis_schedule.py (owner_listed=False, notify=False, silent=True), added and
removed by ensure_job() as the switch goes on and off, like the overnight tidy
and topic sorting. No timer of its own.

Standard library only; other modules are imported when a function needs them.
Never logs a number, a goal or a step's words.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid as _uuid
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers and words (the words are the contract: docs section 13)
# --------------------------------------------------------------------------

KIND = "referee"
ACTION = "referee_tick"
FEATURE = "referee"
#: The offer kind jarvis_backoff.OFFERS declares for this card.
OFFER = "referee_tick_offer"

#: At most this many cards in any 24 hours.
MAX_PER_DAY = 3
DAY = 24 * 3600.0
#: The same step is not asked about twice inside this, answered or not.
SAME_STEP_SECONDS = 24 * 3600.0
#: The hourly look.
EVERY_HOURS = 1
MAX_KEPT = 40

TITLE = "This looks done - tick it?"
LABEL_NUMBER = ("This is a suggestion from a number, not a check. Jarvis only compared the "
                "latest number you logged with your target. It did not run a test, and it "
                "cannot tell whether the work is really finished - only you can say that.")
PRIVATE_LINE = ("This number is private (health or money): it is shown on this screen only "
                "and is never read aloud or sent anywhere.")
YES_LINE = ("If you say yes: this step is ticked, the same as if you had ticked it yourself. "
            "You can untick it at once in Goals.")
NO_LINE = ("If you say no: nothing changes, and Jarvis will not ask about this step again "
           "for a day, then a week, then a month.")
#: The `what` the gate keeps: no number, no name - it can be shown anywhere.
WHAT = "tick one step of one of your goals"

LAST_WORDS = {
    "ticked": "The step was ticked. You can untick it in Goals.",
    "denied": "You said no, so the step stays open. Jarvis will wait before asking again.",
    "timed_out": "Nobody answered the card in time, so the step stays open.",
    "stale": ("The card was about a step that changed while it waited - it is ticked, gone or "
              "no longer at its target - so nothing was ticked."),
    "withdrawn": "You turned Referee suggestions off while the card waited, so nothing was ticked.",
    "refused": "Nothing was ticked.",
    "failed": "The step could not be ticked.",
}


# --------------------------------------------------------------------------
#   Where the small ledger lives
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


def state_path() -> Path:
    env = os.environ.get("JARVIS_REFEREE_FILE")
    return Path(env) if env else _config_dir() / "referee.json"


_LOCK = threading.RLock()
#: The one card that may wait: {"id", "goal", "step", "since"}; {} = none.
_PENDING: dict = {}
_WITHDRAWN: set = set()
_LAST: dict = {}
_LATEST: dict = {}


def _now() -> float:
    return time.time()


def _read_ledger() -> dict:
    """{"offers": [epoch, ...], "asked": {fingerprint: epoch}}. A missing or
    unreadable file is an empty ledger - but see _may_ask: an unreadable one
    makes no card (fails quiet), an absent one simply starts fresh."""
    p = state_path()
    if not p.is_file():
        return {"offers": [], "asked": {}, "ok": True}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        offers = [float(x) for x in d.get("offers", []) if isinstance(x, (int, float))
                  and not isinstance(x, bool)]
        asked = {str(k): float(v) for k, v in (d.get("asked") or {}).items()
                 if isinstance(v, (int, float)) and not isinstance(v, bool)}
        return {"offers": offers, "asked": asked, "ok": True}
    except Exception:
        return {"offers": [], "asked": {}, "ok": False}


def _write_ledger(led: dict) -> bool:
    p = state_path()
    try:
        offers = sorted(led["offers"])[-MAX_KEPT:]
        asked = dict(sorted(led["asked"].items(), key=lambda kv: kv[1])[-MAX_KEPT:])
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"offers": offers, "asked": asked}, indent=1),
                       encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------
#   The pure part: which steps look done, and the card's words
# --------------------------------------------------------------------------

def _short(text, n: int = 80) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _number(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _fmt(value, unit: str) -> str:
    """The number the way jarvis_projects writes it (72.5 kg, $200, 5)."""
    try:
        import jarvis_goals
        return jarvis_goals._with_unit(value, unit or "")
    except Exception:
        return f"{value} {unit or ''}".strip()


def fingerprint(goal_id: str, step_id: str) -> str:
    import jarvis_backoff
    return jarvis_backoff.fingerprint(OFFER, f"{goal_id}|{step_id}")


def candidates(goals: list, read_bench: Callable, fmt: Callable = _fmt) -> list:
    """Every open step, of an ACTIVE goal, that follows a number which has
    reached its target - oldest goal first. Plain code, no model.

    `goals` is what Goals.list() answers; `read_bench(project, bench)` returns
    a benchmark as jarvis_projects answers it (or raises). A step is a
    candidate only if it is not ticked, not waiting on another step, and the
    latest number reaches the target by jarvis_forecast.better_reached - the
    one place "reached" is decided. Nothing else counts: no model, no words,
    no test result. (Where a step follows a project TASK's change summary, not a
    number, is a follow-up - see the module docstring.)"""
    import jarvis_forecast
    out = []
    for goal in reversed(list(goals or [])):
        if not isinstance(goal, dict) or goal.get("status") != "active":
            continue
        for step in goal.get("plan") or []:
            if not isinstance(step, dict) or step.get("done") or step.get("waiting_on"):
                continue
            m = step.get("measure")
            if not isinstance(m, dict):
                continue
            try:
                b = read_bench(m.get("project"), m.get("bench"))
            except Exception:
                continue
            if not isinstance(b, dict):
                continue
            latest = _number((b.get("latest") or {}).get("value")
                             if isinstance(b.get("latest"), dict) else None)
            target = _number(b.get("target"))
            better = b.get("better")
            if latest is None or target is None or better not in ("higher", "lower"):
                continue
            if not jarvis_forecast.better_reached(latest, target, better):
                continue
            unit = str(b.get("unit") or "")
            out.append({
                "goal": str(goal.get("id")), "step": str(step.get("id")),
                "goal_text": _short(goal.get("text")), "step_text": _short(step.get("step")),
                "bench_name": _short(b.get("name"), 60), "better": better,
                "latest": fmt(latest, unit), "target": fmt(target, unit),
                # jarvis_projects' own flags: a health or money number.
                "sensitive": bool(b.get("sensitive") or b.get("keep_on_screen")
                                  or step.get("measure_sensitive")),
                "kind": "number",
            })
    return out


def card_text(c: dict) -> str:
    """The card, word for word. Every number on it is worked out by code."""
    lines = [
        TITLE, "",
        f"Goal: \"{c['goal_text']}\"",
        f"Step: \"{c['step_text']}\"",
        (f"Evidence: \"{c['bench_name']}\" is now {c['latest']}, and your target is "
         f"{c['target']} ({c['better']} is better)."),
        "", LABEL_NUMBER,
    ]
    if c.get("sensitive"):
        lines += ["", PRIVATE_LINE]
    lines += ["", YES_LINE, NO_LINE]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   The gates on a card: what may be asked, and when
# --------------------------------------------------------------------------

def enabled() -> bool:
    """Is "Referee suggestions" genuinely on: the second-card switches, a capable
    second card here. False when in doubt."""
    try:
        import jarvis_second_card
        return bool(jarvis_second_card.feature_active(FEATURE))
    except Exception:
        return False


def _focus_running() -> bool:
    try:
        import jarvis_focus
        return bool(jarvis_focus.is_on())
    except Exception:
        return False


def waiting() -> bool:
    with _LOCK:
        return bool(_PENDING)


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "unknown"
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-referee-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    """Ids and counts only - never a goal's words, a step's, a number."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=_now(), message=LAST_WORDS.get(outcome, ""))
    _audit("referee.card", {"outcome": outcome})


def withdraw() -> None:
    """The switch was turned off (or the goal changed by hand): a card that
    waits is withdrawn, so approving it later ticks nothing."""
    with _LOCK:
        if _PENDING:
            _WITHDRAWN.add(_PENDING["id"])
            _PENDING.clear()


def _still_reached(goals_obj, goal_id: str, step_id: str, read_bench: Callable) -> bool:
    """Right now, the way the card said: the goal is active, the step is open
    and unlocked, its number is at its target."""
    g = goals_obj.get(goal_id)
    if not g or g.get("status") != "active":
        return False
    return any(c["goal"] == goal_id and c["step"] == step_id
               for c in candidates([g], read_bench))


def _decide(pid: str, cand: dict, fp: str, deps: dict) -> None:
    gate, tier_of = deps["gate"], deps["tier_of"]
    text = card_text(cand)
    detail = {"text": text, "what": WHAT, "leaves_this_pc": False,
              "keep_on_screen": bool(cand.get("sensitive")), "goal": cand["goal"],
              "step": cand["step"]}
    bo = deps["backoff"]
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        bo.closed(fp)
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(ACTION) != "ask":
        bo.closed(fp)
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome == "denied":
            bo.declined(fp)
            return _finish(pid, "denied")
        bo.closed(fp)
        if outcome == "timed_out":
            return _finish(pid, "timed_out")
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    # A person said yes. Check it is still true, then tick exactly as they would.
    with _LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn or not deps["enabled"]():
        bo.closed(fp)
        return _finish(pid, "withdrawn")
    goals_obj = deps["goals"]()
    if not _still_reached(goals_obj, cand["goal"], cand["step"], deps["read_bench"]):
        bo.closed(fp)
        return _finish(pid, "stale")
    try:
        goals_obj.mark_step(cand["goal"], None, True, step_id=cand["step"])
    except Exception as exc:
        bo.closed(fp)
        return _finish(pid, "failed", type(exc).__name__)
    bo.accepted(fp)
    _finish(pid, "ticked")


def _read_bench_default(project, bench):
    import jarvis_goals
    return jarvis_goals._read_bench(project, bench)


def _deps(**over) -> dict:
    import jarvis_backoff
    d = {"gate": _gate, "tier_of": _tier, "spawn": _spawn, "enabled": enabled,
         "focus": _focus_running, "backoff": None, "read_bench": _read_bench_default,
         "goals": None, "clock": _now}
    d.update({k: v for k, v in over.items() if v is not None})
    if d["backoff"] is None:
        d["backoff"] = jarvis_backoff.get()
    if d["goals"] is None:
        import jarvis_goals
        d["goals"] = jarvis_goals.get
    return d


def run_pass(**over) -> dict:
    """One quiet look. Raises at most ONE card and says why not otherwise:
    {"asked": 0|1, "why": <code>}. Counts and codes only - no words. Callers:
    the scheduler's hourly step (_on_fire) and the tests; nothing else.

    why codes: off, waiting, focus, daily_limit, unreadable, nothing, held (a
    candidate exists but jarvis_backoff or the same-step rule holds it back),
    tier (the gate line is not "ask"), asked."""
    deps = _deps(**over)
    now = deps["clock"]()
    if not deps["enabled"]():
        return {"asked": 0, "why": "off"}
    with _LOCK:
        if _PENDING:
            return {"asked": 0, "why": "waiting"}
    if deps["focus"]():
        return {"asked": 0, "why": "focus"}
    led = _read_ledger()
    if not led["ok"]:
        return {"asked": 0, "why": "unreadable"}
    if sum(1 for t in led["offers"] if now - t < DAY) >= MAX_PER_DAY:
        return {"asked": 0, "why": "daily_limit"}
    goals_obj = deps["goals"]()
    cands = candidates(goals_obj.list(), deps["read_bench"])
    if not cands:
        return {"asked": 0, "why": "nothing"}
    bo = deps["backoff"]
    for cand in cands:
        fp = fingerprint(cand["goal"], cand["step"])
        if now - led["asked"].get(fp, -1e18) < SAME_STEP_SECONDS:
            continue
        may, _why = bo.may_offer(fp, now, kind=OFFER)
        if not may:
            continue
        if deps["tier_of"](ACTION) != "ask":
            return {"asked": 0, "why": "tier"}
        pid = _uuid.uuid4().hex
        with _LOCK:
            if _PENDING:
                return {"asked": 0, "why": "waiting"}
            _PENDING.clear()
            _PENDING.update(id=pid, goal=cand["goal"], step=cand["step"], since=now)
            _LATEST["id"] = pid
        led["offers"].append(now)
        led["asked"][fp] = now
        _write_ledger(led)
        bo.opened(fp, now)
        _audit("referee.asked", {"sensitive": bool(cand["sensitive"])})
        try:
            deps["spawn"](lambda: _decide(pid, cand, fp, deps))
        except Exception:
            bo.closed(fp)
            with _LOCK:
                _PENDING.clear()
            return {"asked": 0, "why": "failed"}
        return {"asked": 1, "why": "asked"}
    return {"asked": 0, "why": "held"}


def status() -> dict:
    """What the apps could show: whether a card waits and how the last one ended.
    Counts and codes only. (No route serves it today - the card itself is the
    interface; this is for tests and for a later Settings line.)"""
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


# --------------------------------------------------------------------------
#   The one scheduler
# --------------------------------------------------------------------------

def ensure_job(sched=None) -> str:
    """Keep the scheduler in step with the switch: ON, one quiet hourly look;
    OFF, none (and a card that waits is withdrawn). "added", "kept", "removed"
    or "" (nothing to do, or no scheduler). Never raises."""
    try:
        if sched is None:
            import jarvis_schedule
            sched = jarvis_schedule.get()
        have = sched.jobs_of(KIND)
        if not enabled():
            withdraw()
            for jid in have:
                sched.act(jid, "delete")
            return "removed" if have else ""
        if have:
            for jid in have[1:]:
                sched.act(jid, "delete")
            return "kept"
        sched.add_repeat(KIND, {"every": "hours", "hours": EVERY_HOURS,
                                "start": _now() + 600.0}, source="referee")
        return "added"
    except Exception:
        return ""


def _on_fire(job_id: str) -> None:
    try:
        run_pass()
    except Exception:
        pass
    ensure_job()


try:
    import jarvis_schedule as _S
    _S.register_kind(KIND, "referee look", "Jarvis: a goal step may be done.", has_text=False,
                     on_fire=_on_fire, owner_listed=False, notify=False, silent=True,
                     single=True, repeatable=True, plain_repeat=True)
    _S.after_start(lambda: ensure_job())
except Exception:  # pragma: no cover - the scheduler ships beside it
    _S = None


def install() -> str:
    """referee.patch's startup line: keeps the hourly step in step with the
    switch. One banner line; never raises. Adds no route and no tool."""
    try:
        ensure_job()
        return "  referee    Referee suggestions (propose-only; off until the switch is on)"
    except Exception as exc:
        return f"  referee    NOT ON ({type(exc).__name__}) - Referee suggestions are off"


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _LATEST.clear()
