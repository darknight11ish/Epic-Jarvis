"""jarvis_initiative.py - Jarvis noticing things without being asked.

REBUILT. One call site, and it is the whole contract:

    jarvis_hud.py:2240   _ENGINE = jarvis_initiative.build_from_config()
    jarvis_hud.py:2241   _ENGINE.start()

guarded by `if _fw2.load_framework().get("initiative", {}).get("enabled", True)`.
`_ENGINE` is also handed to the event pump as `Pump(engine=_ENGINE)`.

The config says what it is for:

    [initiative]
    enabled = true
    heartbeat_minutes = 30
    # Every finding or event that turns into an ACTION still goes through the
    # autonomy gate. A proactive Jarvis is not a Jarvis with fewer rules.

THE ORIGINAL CHECKS ARE NOT REBUILT, AND THAT IS DELIBERATE - BUT ONE IS.

This engine's job is to run checks on a timer and file what they find. WHICH
checks the original had is not recoverable - the config points at a
`HEARTBEAT.md` in the config directory that "lists the checks in plain
words", and that file is not on the machine either. Inventing a set of
background checks would mean a rebuilt Jarvis doing unattended things nobody
chose, which is the opposite of what this project is about.

So the list is not invented; it is ONE. `build_from_config()` registers the
events-pump watch (`pump_watch`), the one observation this module can make on
its own and the one failure that leaves everything else looking healthy:

    WHAT IT READS   threading.enumerate(), looking for the thread name that
                    jarvis_events.Pump.start() gives its poller thread
                    ("jarvis-events", rebuilt/jarvis_events.py:657). Nothing
                    else: no file, no database, no network, no fact, no model.
    WHAT IT DOES    returns one finding when that thread is not there, and
                    None when it is: {"level": "alert", "check": "event
                    stream", "message": "..."}. file() puts it in the queue
                    `/api/initiative` serves (jarvis_hud.py:3210-3211), and it
                    never acts: anything that turns into an ACTION still goes
                    through the autonomy gate.
    WHAT IT COSTS   nothing on a healthy machine. One `threading.enumerate()`
                    per heartbeat, and nothing at all inside the boot grace
                    window (PUMP_GRACE_SECONDS).

TWO CONSUMERS THAT COULD NOT SEE IT - BOTH FIXED 2026-10-15

  * the HUD's card for a heartbeat finding reads `level`, `check` and
    `message` off the QUEUE ROW (jarvis_hud.html:2591-2595), while file()
    nests the finding one level down under "finding" - so a finding filed
    here was served and never drawn. `drain()` now mirrors those three keys
    onto the row it hands out and keeps the nested dict exactly as it was, so
    nothing that read it there noticed. Fixed HERE rather than in the page
    because `jarvis_hud.html` is vendored (a copy of the desktop app's own
    file) and the row's shape is the backend's to decide.
  * the phone's "Findings" note (BrainScreen.kt:2503-2509) reads a `checks`
    count - top-level, or under a `status` object - out of the
    /api/initiative body, which the route never sent, so it went on saying
    "no background checks have been built" whether one was registered or
    none was. The route now sends it: `backend/initiative-payload.patch`,
    which is a patch rather than an edit to this module because the body is
    built in jarvis_hud.py and that file is NOT shipped whole - it is one of
    the files the patch stack delivers, so an edit to the copy in this
    repository would never reach the owner's PC.

AND IT TICKS THE JOB QUEUE (2026-10-15)

`Engine.start()` registers a second entry, `JOBS_TICK` (`jobs_tick`), which
calls `jarvis_jobs.tick()`. That is `jarvis_jobs.run_due()` - the job queue
that "Jobs that keep going after the chat ends" promises - and until this
landed it had NO production caller at all: the suites called the function
directly, so every check passed and no queued job ever ran on the owner's PC.
The queue rides this heartbeat rather than growing a clock of its own, which
is also why it is registered in `start()` and not in `build_from_config()`:
the built engine's own check list stays what `test_rebuilt.py` pins it to
(the one observation above), and a heartbeat that is actually running is what
a job needs. The owner's decision on who may run unattended, and who parks,
is in `jarvis_jobs.py`'s docstring and in ARCHITECTURE.md section 10.

WHY THAT ONE AND NOT A HUNDRED (2026-10-14, task-8). Nothing in production
had ever called `register()`. The audit measured `status()["checks"]` as 0 on
every boot: the engine started, ticked, and could not have filed anything,
for ever. The pump is the check because a dead pump is invisible every other
way - jarvis_hud.py prints "PUMP DID NOT START" to a console nobody reads and
nothing else ever mentions it - and the cost was recorded when it was fixed:
a gate raised while the desktop sat idle produced no toast and no tray badge
for up to an hour. This engine can see that, and only that, without inventing
a single thing.

`status()["note"]` still says the ORIGINAL check list is not recoverable, at
every count: one honest check is not the list that was lost.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get("initiative", {}).get(key, default)
    except Exception:
        return default


#: The thread name jarvis_events.Pump.start() gives its poller thread:
#:     threading.Thread(target=self._run, name="jarvis-events", daemon=True)
#: (rebuilt/jarvis_events.py:657). A rename there needs this line updated -
#: nothing else in the two modules is shared, and the check below is the one
#: thing in the backend that notices the pump is not running.
PUMP_THREAD = "jarvis-events"

#: The name the one built-in check registers under, and what status() reports
#: a count of. Short, lower-case, no spaces - the same shape a caller's own
#: registered name has.
BUILTIN_CHECK = "event_pump"

#: The name the background job queue's ticker registers under. Registered in
#: `Engine.start()`, not in `build_from_config()` - see the module docstring,
#: "AND IT TICKS THE JOB QUEUE". It is not one of this engine's CHECKS (it
#: notices nothing and files nothing); it is work the heartbeat does.
JOBS_TICK = "jobs"

#: How long after build_from_config() the pump may still be missing. The HUD
#: builds and starts this engine at jarvis_hud.py:6027-6028 and constructs the
#: pump around thirty lines later (:6064), and `Engine.start()` beats once
#: immediately - so a beat inside this window says nothing about the pump at
#: all. Two minutes is many times the gap between those two lines.
PUMP_GRACE_SECONDS = 120.0


def pump_running() -> bool:
    """Is the events pump's poller thread alive? READ-ONLY: it asks Python for
    the thread list and looks for PUMP_THREAD. It opens nothing, reads no
    file, touches no database and imports nothing that could have a side
    effect on first import."""
    return any(t.name == PUMP_THREAD for t in threading.enumerate())


def pump_finding(now: Optional[float] = None, built_at: Optional[float] = None,
                 alive: Optional[bool] = None) -> Optional[dict]:
    """The pump is not running -> one finding; it is -> None. The whole check,
    as a function of its inputs, so a test can drive it without a clock, a
    thread or a running Jarvis.

    `built_at` is when the engine was built (0.0 or None means "no grace
    window", which is what tests want). `alive` is the probe; left out, it is
    `pump_running()`.
    """
    now = time.time() if now is None else float(now)
    if built_at and now - float(built_at) < PUMP_GRACE_SECONDS:
        return None
    if alive is None:
        alive = pump_running()
    if alive:
        return None
    return {"level": "alert", "check": "event stream",
            "message": ("The event stream is not running, so approvals, power "
                        "changes and persona changes will not reach your apps "
                        "until Jarvis is restarted.")}


def pump_watch(built_at: Optional[float] = None) -> Callable[[], Optional[dict]]:
    """The check `build_from_config()` registers: `pump_finding` with the
    grace window measured from when the engine was built, and said ONCE per
    death - a heartbeat every 30 minutes would otherwise file the same broken
    pump into the inbox all day. If the pump comes back and dies again, it
    says so again.
    """
    t0 = time.time() if built_at is None else float(built_at)
    said = {"dead": False}

    def check() -> Optional[dict]:
        if pump_running():
            said["dead"] = False
            return None
        if said["dead"]:
            return None
        said["dead"] = True
        return pump_finding(built_at=t0, alive=False)

    return check


def jobs_tick() -> None:
    """The heartbeat's other job: run whatever the background queue has due.

    One line, because the work and every rule about it live in the module that
    owns the queue - `jarvis_jobs.tick()`. It is imported HERE rather than at
    the top of this file on purpose: this module is imported by the HUD's boot
    even when there is no jobs module to find, and a missing one must show up
    as a counted error on the beat (Engine.beat does that) rather than as an
    ImportError that stops the backend starting. It returns None, which is
    what `jarvis_jobs.tick()` returns: a truthy return would be filed as a
    FINDING and published to the apps, and job ids and labels are the owner's
    own material that never goes out that way.
    """
    import jarvis_jobs
    jarvis_jobs.tick()


#: What `drain()` mirrors onto a row, from a finding a check filed. `level` is
#: the one the HUD styles on; a finding that names none is a note, so it is
#: still drawn rather than dropped.
DEFAULT_LEVEL = "note"


def _mirrored(row: dict) -> dict:
    """`row` with `level`, `check` and `message` FLAT on it, for the HUD card.

    WHY THIS EXISTS, in one line: the page reads those three off the row
    (jarvis_hud.html:2591-2595), `file()` nests the finding one level down
    under "finding", and a finding that is served and never drawn looks
    exactly like a Jarvis that noticed nothing. Both shapes are kept: the
    nested `finding` is untouched, so every reader that already used it is
    unaffected, and `_ENGINE.drain()` rows simply carry the same thing twice.

    WHAT IS MIRRORED, AND WHAT IS FILLED IN (there is a difference):
      * `level` and `message` are the finding's own, when it is a dict and
        has them. `message` also accepts `text`, which is the key the
        existing tests file findings under. A finding with no level is
        `note`; a finding with no words at all gets "" and is still drawn,
        which is more honest than vanishing.
      * `check` falls back to the row's own `source` - the name the check
        registered under (`file(source, finding)`), which is precisely what
        the page prints in that slot. Nothing is invented for it.
      * a finding that is not a dict (a check may file a plain string, and
        this module's own suite does) reads as its own message.

    NO NEW EXPOSURE: the words were already on the row under `finding`, and
    /api/initiative already served that. This only stops the page having to
    guess where to look.
    """
    out = dict(row)
    finding = out.get("finding")
    if isinstance(finding, dict):
        level = finding.get("level")
        check = finding.get("check")
        message = finding.get("message")
        if message is None:
            message = finding.get("text")
    else:
        level = check = None
        message = finding if isinstance(finding, str) else None
    out["level"] = str(level) if level else DEFAULT_LEVEL
    out["check"] = str(check) if check else str(out.get("source") or "")
    out["message"] = "" if message is None else str(message)
    return out


class Engine:
    """Runs registered checks on a heartbeat and collects what they find."""

    def __init__(self, heartbeat_minutes: float = 30.0, enabled: bool = True) -> None:
        self.heartbeat = max(1.0, float(heartbeat_minutes)) * 60.0
        self.enabled = bool(enabled)
        self.checks: list = []
        self.findings: list = []
        # A running total, never decremented. The doorbell announces this,
        # not the unseen COUNT - see file()'s comment for why the count is
        # the wrong thing to key a change-feed on.
        self._filed_total = 0
        self.beats = 0
        self.errors = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    # ---- registration ------------------------------------------------------

    def register(self, name: str, fn: Callable) -> "Engine":
        with self._lock:
            self.checks.append((str(name), fn))
        return self

    # ---- running -----------------------------------------------------------

    def start(self) -> "Engine":
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return self
        self._attach_jobs_ticker()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jarvis-initiative",
                                        daemon=True)
        self._thread.start()
        return self

    def _attach_jobs_ticker(self) -> None:
        """Make the heartbeat also run the background job queue. Once.

        THE DEFECT THIS CLOSES (2026-10-15): `jarvis_jobs.run_due()` - the
        function that runs every due job, and so the whole of "Jobs that keep
        going after the chat ends" - had ZERO production call sites. The
        suites called it directly, which is the right way to test the function
        and exactly why the missing caller was invisible: every check passed
        and no queued job ever ran on the owner's PC.

        WHY register() AND NOT A THREAD OR A TIMER OF ITS OWN. This engine's
        heartbeat is the clock the HUD already starts; a second one would be a
        second source of "when". `register()` is the engine's own plug-in
        point, and a tick that returns None is exactly a check that finds
        nothing - it cannot file an inbox row.

        WHY HERE AND NOT IN build_from_config(). Two reasons, both about not
        breaking something that is pinned:
          * `build_from_config()`'s check list is the engine's own
            observations, and `test_rebuilt.py`'s
            `test_the_factory_arms_exactly_one_check_and_it_is_the_pump_watch`
            pins it to exactly [BUILTIN_CHECK]. Running the queue is not an
            observation; it is work.
          * a queue only needs a clock once the clock is RUNNING, so the
            honest place to attach it is the call that starts the heartbeat.
        The price, said plainly: `status()["checks"]` reads 1 on a built
        engine and 2 once it is started, and the phone's Findings note counts
        what the heartbeat actually runs.
        """
        with self._lock:
            if any(name == JOBS_TICK for name, _ in self.checks):
                return
        self.register(JOBS_TICK, jobs_tick)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def beat(self) -> list:
        """One pass over the checks. Returns what was newly found.

        Separate from the thread so a test can drive it without waiting half
        an hour, and so a check can be exercised on demand.
        """
        new = []
        with self._lock:
            checks = list(self.checks)
        for name, fn in checks:
            try:
                got = fn()
            except Exception:
                # A check that throws must not stop the others or kill the
                # heartbeat. Counted so a permanently broken check is visible
                # in status() rather than merely silent.
                self.errors += 1
                continue
            if not got:
                continue
            for item in (got if isinstance(got, list) else [got]):
                new.append(self.file(name, item))
        self.beats += 1
        return new

    @property
    def heartbeat_minutes(self) -> float:
        """jarvis_hud.py:2242 prints `{_ENGINE.heartbeat_minutes:g}`."""
        return self.heartbeat / 60.0

    @property
    def watchers(self) -> list:
        """jarvis_hud.py:2243 prints `len(_ENGINE.watchers)`. Same list as
        `checks`; the HUD's name for it, kept so the banner works."""
        return self.checks

    def drain(self) -> list:
        """Unseen findings, marked seen. jarvis_hud.py:3211 is the caller.

        Read-and-clear in one call, under one lock, because two calls would
        let a finding filed between them be marked seen without being
        returned - lost silently, which for an inbox is the worst failure.

        EVERY ROW CARRIES THE FINDING BOTH WAYS (2026-10-15). `finding` stays
        exactly what the check filed, one level down, unchanged - every
        existing reader reads it there - and the same row also carries
        `level`, `check` and `message` FLAT, which is where the HUD's card
        reads them (jarvis_hud.html:2591-2595). See `_mirrored` for what is
        mirrored and what is filled in, and the module docstring for why the
        fix is here rather than in the vendored page.
        """
        with self._lock:
            out = [_mirrored(f) for f in self.findings if not f["seen"]]
            for f in self.findings:
                f["seen"] = True
        return out

    def file(self, source: str, finding) -> dict:
        """Record something noticed. Announces a COUNT, never the content.

        The finding's text came from reading something - a mailbox, a page, a
        file - and `[privacy] never_leaves_device` covers all three. The event
        bus reaches a lock screen, so the doorbell carries how many, not what.

        TWO BUGS, both in how this told jarvis_events about itself, neither
        in what it stored - self.findings and drain() were never wrong.

        ONE: `note()` was called with no `announce_first`. It is a REPORT,
        not a poller's observation - something just happened - and
        jarvis_events.Bus.note()'s own docstring names this exact call as the
        example: without the flag, the first finding filed after every
        restart raised no event at all, because the bus had never seen the
        key "findings" and treated the sighting as a baseline. The row was
        still stored and still in drain()'s output - only the doorbell was
        silent, for the one finding a restarted Jarvis most needs to surface.

        TWO: the value announced was the UNSEEN count, and that count is not
        monotonic - mark_seen() lowers it without calling note(), so nothing
        re-baselines when it does. A fresh finding that happens to bring the
        unseen count back to a number already announced compares equal under
        note()'s dedupe and is swallowed: file A (2 unseen, announced) ->
        owner reads A (1 unseen, no event, nothing to re-baseline against) ->
        file B, a finding nobody has heard of (2 unseen again) -> dropped,
        because 2 == the last value note() saw for this key. `_filed_total`
        fixes it by never going backwards; the unseen COUNT for a human to
        read is still carried in `extra`, unchanged.
        """
        with self._lock:
            # The id is built INSIDE the lock. Outside it, len(self.findings)
            # was read before the append, so eight threads filing at once
            # produced duplicate ids - and mark_seen(one id) then marked two
            # rows, one of which nobody had read.
            row = {"id": f"f{int(time.time()*1000)}{len(self.findings)}",
                   "source": str(source), "at": time.time(),
                   "finding": finding, "seen": False}
            self.findings.append(row)
            self._filed_total += 1
            total = self._filed_total
            n = len([f for f in self.findings if not f["seen"]])
        try:
            import jarvis_events
            jarvis_events.BUS.note("findings", total, "finding",
                                   extra={"count": n}, announce_first=True)
        except Exception:
            pass
        return row

    def inbox(self, unseen_only: bool = False) -> list:
        with self._lock:
            return [dict(f) for f in self.findings
                    if not (unseen_only and f["seen"])]

    def mark_seen(self, ids: Optional[list] = None) -> int:
        """Mark findings read. Reading is not approving - nothing here acts."""
        with self._lock:
            n = 0
            for f in self.findings:
                if ids is None or f["id"] in ids:
                    if not f["seen"]:
                        f["seen"] = True
                        n += 1
            return n

    def _run(self) -> None:
        while not self._stop.is_set():
            self.beat()
            self._stop.wait(self.heartbeat)

    def status(self) -> dict:
        with self._lock:
            # The caveat is carried at EVERY count, not only at zero: the one
            # check above is not the list that was lost, and a reader who sees
            # `checks: 1` must not think the original list was recovered.
            note = ("the original check list is not recoverable, see the "
                    "module docstring")
            return {"enabled": self.enabled, "running": self.running,
                    "heartbeat_minutes": round(self.heartbeat / 60, 1),
                    "checks": len(self.checks), "beats": self.beats,
                    "errors": self.errors, "findings": len(self.findings),
                    "unseen": len([f for f in self.findings if not f["seen"]]),
                    "note": ("no checks are registered - " + note)
                            if not self.checks else note}


def build_from_config() -> Engine:
    """The engine the HUD starts. Never raises: a bad config must not stop
    the backend booting, and `enabled=false` is a legitimate answer.

    It also registers this module's ONE check - the events-pump watch
    (`pump_watch`), explained in the module docstring. Registered HERE rather
    than in the HUD because this is the call the HUD makes
    (jarvis_hud.py:6027) and the write scope of the change that wired it, and
    because nothing had ever registered anything: the audit measured
    `status()["checks"]` as 0 on every boot.
    """
    try:
        beats = float(_cfg("heartbeat_minutes", 30) or 30)
    except (TypeError, ValueError):
        beats = 30.0
    eng = Engine(heartbeat_minutes=beats, enabled=bool(_cfg("enabled", True)))
    eng.register(BUILTIN_CHECK, pump_watch())
    return eng
