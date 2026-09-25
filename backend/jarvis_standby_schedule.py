"""jarvis_standby_schedule.py - the standby schedule: "on standby from 01:00
to 07:00, every day".

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
No patch and no route of its own: it is a KIND of job on the one scheduler
(jarvis_schedule.register_kind), and it goes through the scheduler's own
routes. ARCHITECTURE section 12: anything that happens at a time is a kind
of job on the scheduler, not a timer thread of its own.

WHAT THE OWNER ASKED FOR (task #55): "Sleep feature - schedule + manual
sleep/wake, unload ALL models on both GPUs, warm-up on wake." With the
decision of 2026-09-25: ONE scheduler, reused for briefings, sleep mode and
the overnight tidy.

WHY IT IS CALLED "STANDBY SCHEDULE", NOT "SLEEP MODE"
Jarvis already has the thing that sleeps: Standby (jarvis_power_switch.py,
power-mode.patch). Both apps call it "Standby" (the desktop's tray: Change
power mode > Standby; the phone's Mind: the Standby button), and it already
frees the graphics cards. So "sleep mode" is not a second mode; it is
Standby, on a timetable. One word for one thing. And "sleep" is already
taken twice: [memory.sleep_time] / jarvis_sleep.py is the overnight memory
tidy (the toml warns that it does the OPPOSITE - uses the idle card to do
more), and jarvis_second_card.sleep() and friends are how standby frees
each engine.

WHAT IS REUSED, AND WHAT IS NEW
  * Going on standby and waking are jarvis_power_switch.set_mode() - the
    same call a tap in either app makes, through the same gate action
    (power_manage, "auto" in the shipped toml), the same "not while a task
    runs" refusal, the same unloading. Nothing here unloads anything itself.
  * Manual standby and waking: nothing new. They are the Standby and Active
    buttons that already exist in both apps.
  * New in jarvis_power_switch (the same change): standby also asks the
    everyday Ollama for EVERY model it still holds and unloads each; and
    leaving standby loads the chat model again at once (the warm-up).
  * New here: the timetable. One job of kind "standby" whose rule is a
    window, {"every": "day", "at": "01:00", "until": "07:00"}. It goes off
    at both ends.

SETTING IT UP IS ONE APPROVAL CARD; TURNING IT OFF IS IMMEDIATE
It repeats, so it is the scheduler's own `schedule_repeat` card, listing the
next three nights in full (the owner's rule: anything that repeats asks
once, with a card listing the next run times). Nothing happens until that
card is approved. Deleting it (either app's Coming up, Delete) is immediate
and needs no card - it only makes Jarvis do less. Pause skips it until
Resume. There is only ever one standby schedule; to change the times,
delete it and set up a new one (a new card).

Deleting or pausing it does NOT wake Jarvis if it is on standby now: that
is what Active is for. It only stops the next start and end.

WHAT HAPPENS AT EACH END
Which end it is comes from the clock (jarvis_schedule.in_window), not from
which job went off, so two ends found overdue together - the PC was off all
night, and 01:00 and 07:00 both went by - agree: it is after 07:00, so
Jarvis is awake.
  * The start (01:00): if Jarvis is not already on standby, set_mode
    ("standby"). Refused while a task is running (unloading the model under
    it would break it): that night is skipped, and the schedule's line in
    Coming up says so.
  * The end (07:00): if Jarvis is on standby - whoever put it there - set_mode
    ("active"), which loads the chat model again. If it is already awake
    (the owner woke it by hand), nothing is done.
  * A start found late, inside the window (the PC came on at 03:00): standby
    then, once. The same missed-while-off rule as every other job.

WHILE ON STANDBY (the same as standby by hand - nothing new here):
  * Timers, alarms and reminders still go off, on the PC and both apps. The
    scheduler does not look at the power mode, and "set a timer" is
    answered without the AI model (jarvis_quick.py).
  * A question is answered: Ollama loads the chat model for it, so the
    first answer takes 5-15 seconds. Jarvis stays on standby (nothing in
    this repository changes the mode on a question) until the end of the
    window or a tap on Active.
  * The going-off itself notifies nobody: kind "standby" has notify=False,
    so the `schedule` event says "notify": false and neither app shows a
    toast or a notification at 01:00. The `power` event still updates the
    Power line in both apps.

The last thing each end did is kept in memory (lost on a restart) and shown
under the job in both apps' Coming up as its `note`.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import jarvis_schedule as S

KIND = "standby"

#: Who changed the mode, as jarvis_power records it. Not "the owner, from
#: ..." - the desktop's tray reads that as "set by hand".
WHY = "the standby schedule"

#: How long an end waits for set_mode's answer. Freeing the cards can take
#: a few seconds; this runs on the scheduler's own thread for one job, so
#: waiting holds nothing else up.
WAIT_S = 30.0

ABOUT = (
    "At the start, Jarvis goes on standby - the same as choosing Standby: it "
    "unloads its models and frees the graphics card(s).",
    "At the end, it wakes (Active) and loads the chat model again, so the first "
    "answer is not slow.",
    "Timers, alarms and reminders still go off while it is on standby. A question "
    "asked then is answered, but the first answer takes 5-15 seconds.",
    "Turning it off does not wake Jarvis if it is on standby at that moment - "
    "choose Active for that.",
)

_LOCK = threading.Lock()
#: job id -> {"at": epoch, "sentence": str}: how its last end went.
_LAST: dict = {}


def _say(job_id: str, sentence: str, now: float) -> None:
    with _LOCK:
        if len(_LAST) > 20:
            _LAST.clear()
        _LAST[job_id] = {"at": now, "sentence": sentence}


def note(job_id: str) -> str:
    """The line under the job in Coming up: how its last end went."""
    with _LOCK:
        last = _LAST.get(job_id)
    return last["sentence"] if last else ""


def _power():
    import jarvis_power
    return jarvis_power


def _switch():
    import jarvis_power_switch
    return jarvis_power_switch


def _audit(event: str, detail: dict) -> None:
    S._audit(event, detail)


#: The clock the ends are judged by. The scheduler's own clock is the PC's;
#: the tests put theirs here.
CLOCK: Callable[[], float] = time.time


def run_end(job_id: str, *, sched=None, clock: Optional[Callable[[], float]] = None,
            power=None, switch=None) -> str:
    """One end of the window went off: go on standby or wake, by the clock.
    Returns the sentence it noted. Never raises (the scheduler's _safe
    catches anyway)."""
    s = sched if sched is not None else S.get()
    job = s.job(job_id)
    if not job or not isinstance(job.get("rule"), dict):
        return ""
    now = (clock or CLOCK)()
    at = S.clock(now)
    try:
        power = power if power is not None else _power()
        switch = switch if switch is not None else _switch()
        mode = str(power.current())
    except Exception as exc:
        said = f"Nothing changed at {at}: the power module is not available ({type(exc).__name__})."
        _say(job_id, said, now)
        return said
    want = "standby" if S.in_window(job["rule"], now) else "active"
    code = None
    if want == "standby" and mode == "standby":
        said = f"Already on standby at {at}."
    elif want == "active" and mode != "standby":
        said = f"Already awake at {at}."
    else:
        code, out = switch.set_mode(want, by=WHY, why=WHY, wait_s=WAIT_S)
        said = _outcome(want, code, out, at)
    _say(job_id, said, now)
    _audit("standby_schedule.end", {"id": job_id, "mode_was": mode, "wanted": want,
                                    "answer": code})
    return said


def _outcome(mode: str, code: int, out: dict, at: str) -> str:
    """One sentence for Coming up, from set_mode's own answer."""
    out = out if isinstance(out, dict) else {}
    if code == 200 and out.get("changed"):
        if mode == "standby":
            still = out.get("still_loaded") or []
            tail = (" Still loaded: " + ", ".join(still) + ".") if still else ""
            return f"Went on standby at {at}.{tail}"
        warm = out.get("warm_up")
        return (f"Woke at {at} and loaded the chat model ({warm}) again." if warm
                else f"Woke at {at}.")
    if code == 202:
        return (f"At {at} a card asked to switch to {mode} (your power setting asks "
                f"first); it changes only if it is approved.")
    if code == 409 and mode == "standby" and not out.get("waiting"):
        return (f"Skipped standby at {at}: a task was running, and standby would "
                f"unload the model it uses.")
    words = str(out.get("message") or out.get("error") or f"answer {code}")
    return f"Did not switch to {mode} at {at}: {words}"


def on_fire(job_id: str) -> None:
    run_end(job_id)


S.register_kind(
    KIND, "standby schedule", "Jarvis: standby schedule.",
    has_text=False, on_fire=on_fire, owner_listed=True,
    notify=False, window=True, single=True,
    edges=("on standby", "awake"), about=ABOUT, note=note,
)


def status(sched=None) -> Optional[dict]:
    """The standby schedule on the list now, or None."""
    s = sched if sched is not None else S.get()
    for j in s.listed():
        if j.get("kind") == KIND:
            return j
    return None
