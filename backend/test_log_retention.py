"""test_log_retention.py - the 90-day log promise finally has code behind it.

    py -3 backend/test_log_retention.py

THE GAP THIS PROVES CLOSED

`jarvis_framework.prune_logs()` existed and its own docstring said
"INFERRED - nothing surviving calls this". It was the only occurrence of the
name in the whole live backend, so `[logging].retention_days = 90` in
jarvis-framework.toml was a setting with nothing behind it: the audit log grew
at about 0.4 MB a day (~130 MB a year) for ever. Measured, not guessed -
~/.openjarvis/logs/jarvis-<date>.jsonl was 364 KB (2,888 lines) for one day.

WHAT IS CHECKED HERE

  * something in the live backend really calls it - a scan of the shipped
    modules, not just this suite, because a pruner called only by its own test
    is the same gap with a green tick on it;
  * it is wired the way this codebase runs periodic work: a poller in
    jarvis_events.POLLERS, which the pump drives every second, with a
    once-a-day gate on the tick. The test drives `Pump.tick()` by hand, the
    same way test_events_pump.py does, so no thread and no waiting;
  * an old log file in a scratch log directory is GONE after the tick, and the
    fresh one is untouched;
  * today's file survives even when it looks old (its own timestamp is
    ancient), because the writer and the pruner compare names, not dates;
  * files that are not `jarvis-*.jsonl`, and files in a directory next door,
    are never touched;
  * a second tick the same day deletes nothing at all (the once-a-day gate),
    and the sweep itself is idempotent;
  * retention_days = 0 means keep everything, and a value that is not a number
    keeps everything too - being unable to parse the setting must not delete
    the owner's audit trail.

Everything is driven into a temporary folder. No thread, no network, no
model, and nothing at all under the real ~/.openjarvis/logs.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-logret-"))
# Before anything imports jarvis_framework: CONFIG_DIR is read once, at import.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, explain, missing, require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_framework.py", "rebuilt/jarvis_events.py")

# The rebuilt modules are the ones under test, so they come FIRST on the path -
# ahead of any older copy that may be sitting in the backend folder.
REBUILT = HERE / "rebuilt"
if str(REBUILT) not in sys.path:
    sys.path.insert(0, str(REBUILT))

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (The old shape, check("SKIP - ...", True), is a condition
    of the constant True: it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The modules
# --------------------------------------------------------------------------

_absent = missing("jarvis_framework.py", "jarvis_events.py")
if _absent and os.environ.get("JARVIS_BACKEND"):
    print("FAIL  " + ", ".join(_absent) + " not found. " + explain())
    sys.exit(1)

try:
    import jarvis_framework as FW
    import jarvis_events as EV
except Exception as exc:  # pragma: no cover - a broken install, not a bug here
    skip(f"jarvis_framework/jarvis_events do not import here "
         f"({type(exc).__name__}: {exc}). {explain()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    sys.exit(1 if FAILED else 0)


#: A scratch log directory, and a neighbour holding a file that must survive.
LOG = _TMP / "logs"
SIDE = _TMP / "not-logs"
LOG.mkdir(parents=True, exist_ok=True)
SIDE.mkdir(parents=True, exist_ok=True)

_ORIG_LOAD = FW.load_framework


def config(retention=90):
    """Redirect this module's logging section at the scratch folder.

    A wrapper around the real loader, which is the shape the surviving suites
    already use (test_rebuilt.py records it). load_framework is called fresh
    by log_dir() and section() on every use, so patching it here reaches
    prune_logs without a restart.
    """
    def fake(*a, **k):
        d = _ORIG_LOAD(*a, **k)
        if not isinstance(d, dict):
            d = {}
        d.setdefault("logging", {})["log_directory"] = str(LOG)
        d["logging"]["retention_days"] = retention
        return d
    return fake


def day_name(offset_days=0, when=None):
    """The file name the writer itself would use, one place only."""
    return FW.log_name((time.time() if when is None else when)
                       + offset_days * 86400)


def add(name, age_days, body="{}\n"):
    """A log file with a chosen age. Returns its path."""
    p = LOG / name
    p.write_text(body, encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(p, (stamp, stamp))
    return p


def day_gate_reset():
    """Forget that retention ran today, so a later tick sweeps again."""
    EV._RETENTION_SEEN.clear()


def clear_logs():
    """Empty the scratch log folder. Files only: one test makes a subfolder to
    prove the sweep does not reach into it, and unlinking a directory is a
    Windows access error, not a tidier test."""
    for p in LOG.glob("*"):
        if p.is_file():
            p.unlink()


# --------------------------------------------------------------------------
#   Something in the live backend really calls it
# --------------------------------------------------------------------------

def t_a_shipped_module_calls_the_pruner():
    """CONTROL. Fails if the call site is ever removed again.

    This is the check that matters most, because it is the exact shape of the
    bug: the function was correct, tested by nothing, and called by nobody.
    It reads the modules the backend actually loads, not this suite.
    """
    callers = []
    for path in sorted(REBUILT.glob("jarvis_*.py")):
        src = path.read_text(encoding="utf-8", errors="replace")
        for line in src.splitlines():
            code = line.split("#", 1)[0]
            # A call, not the definition and not a mention in a docstring:
            # "def prune_logs(" and "the pruner prune_logs()" are both fine.
            if ".prune_logs(" in code and not code.strip().startswith("def "):
                callers.append(f"{path.name}:{line.strip()}")
    check("a shipped backend module calls prune_logs()",
          bool(callers),
          "nothing calls it - the 90-day setting is decoration again. "
          "Looked in " + str(REBUILT))
    check("...and it is jarvis_events.py doing it, from the pump's pollers",
          any(c.startswith("jarvis_events.py:") for c in callers),
          f"callers: {callers}")


def t_the_pump_runs_it():
    """It rides the periodic hook this codebase already has.

    The pump is the process's own every-second thread (events-pump.patch
    starts it in jarvis_hud.py), and a poller is how periodic work joins it.
    """
    check("_poll_log_retention is a poller on the pump",
          any(getattr(f, "__name__", "") == "_poll_log_retention"
              for f in EV.POLLERS),
          f"POLLERS = {[getattr(f, '__name__', f) for f in EV.POLLERS]}")
    pump = EV.Pump(bus=EV.Bus(), engine=None)
    try:
        pump.tick()
        drove = True
        why = ""
    except Exception as exc:
        drove = False
        why = f"{type(exc).__name__}: {exc}"
    check("a plain tick does not raise", drove, why)
    check("the pump still counts pollers the way status() reports them",
          isinstance(EV.status().get("pollers"), int), repr(EV.status()))


# --------------------------------------------------------------------------
#   The sweep itself
# --------------------------------------------------------------------------

def t_old_is_deleted_fresh_is_kept():
    """The headline behaviour, on this machine, in a scratch folder."""
    FW.load_framework = config(90)
    clear_logs()
    day_gate_reset()

    old = add(day_name(-200), 200)          # well past the window
    fresh = add(day_name(-3), 3)            # inside it
    today = add(day_name(0), 0)             # being written right now

    pump = EV.Pump(bus=EV.Bus(), engine=None)
    pump.tick()

    check("the file from 200 days ago is gone", not old.exists(),
          f"{old.name} is still in {LOG}")
    check("the file from 3 days ago is untouched", fresh.exists(),
          f"{fresh.name} was deleted inside the 90-day window")
    check("today's file is untouched", today.exists(),
          f"{today.name} was deleted - that is the file being written")
    check("the count of what went is reported",
          EV._RETENTION_SEEN.get("removed") == 1,
          repr(EV._RETENTION_SEEN))
    check("the day is marked, so the next tick this second does nothing",
          EV._RETENTION_SEEN.get("day") == time.strftime("%Y-%m-%d"),
          repr(EV._RETENTION_SEEN))
    FW.load_framework = _ORIG_LOAD


def t_todays_file_survives_even_when_it_looks_old():
    """A quiet day, a restored backup, a clock that moved: today's file can
    carry an old timestamp. It is still the file being appended to, so the
    skip is by NAME - that is why log_name() exists."""
    FW.load_framework = config(90)
    clear_logs()
    day_gate_reset()

    today = add(day_name(0), 400)           # named today, stamped last year
    EV.Pump(bus=EV.Bus(), engine=None).tick()

    check("today's file survives an old timestamp on it", today.exists(),
          "the pruner compared a date instead of the name and deleted the "
          "file the backend is appending to")
    FW.load_framework = _ORIG_LOAD


def t_the_setting_is_what_decides():
    """retention_days is the whole control, and it is read on every sweep."""
    day_gate_reset()
    clear_logs()
    borderline = add(day_name(-100), 100)   # older than 90 days, newer than 365

    FW.load_framework = config(365)
    EV.Pump(bus=EV.Bus(), engine=None).tick()
    check("with a 365-day window a 100-day-old file is kept", borderline.exists(),
          f"{borderline.name} was deleted under a 365-day window")

    day_gate_reset()
    FW.load_framework = config(90)
    EV.Pump(bus=EV.Bus(), engine=None).tick()
    check("changing the window to 90 days deletes it on the next sweep",
          not borderline.exists(),
          f"{borderline.name} survived the 90-day window")
    FW.load_framework = _ORIG_LOAD


def t_keep_everything_means_keep_everything():
    """"Keep till deleted" is the safe reading of an unusable setting."""
    day_gate_reset()
    clear_logs()
    ancient = add(day_name(-4000), 4000)

    FW.load_framework = config(0)
    EV.Pump(bus=EV.Bus(), engine=None).tick()
    check("retention_days = 0 keeps even a 10-year-old file", ancient.exists(),
          f"{ancient.name} was deleted by a 0-day window")

    FW.load_framework = config("ninety")
    EV.Pump(bus=EV.Bus(), engine=None).tick()
    check("a setting that is not a number keeps it too", ancient.exists(),
          "an unreadable retention_days deleted the owner's audit log")

    FW.load_framework = config(-5)
    EV.Pump(bus=EV.Bus(), engine=None).tick()
    check("a negative window keeps it as well", ancient.exists(),
          "a negative retention_days was read as 'delete everything'")
    FW.load_framework = _ORIG_LOAD


def t_nothing_outside_the_log_folder_is_reached():
    """Never anything but `jarvis-*.jsonl` directly inside log_directory."""
    FW.load_framework = config(90)
    clear_logs()
    day_gate_reset()

    good = add(day_name(-200), 200)
    other = add("jarvis-framework.toml", 200)         # not a .jsonl log
    plain = add("notes.txt", 200)                     # not a log at all
    nested = LOG / "old" / "jarvis-2000-01-01.jsonl"  # not directly inside
    nested.parent.mkdir(exist_ok=True)
    nested.write_text("{}\n", encoding="utf-8")
    os.utime(nested, (time.time() - 900 * 86400,) * 2)
    neighbour = SIDE / day_name(-200)
    neighbour.write_text("{}\n", encoding="utf-8")
    os.utime(neighbour, (time.time() - 900 * 86400,) * 2)

    EV.Pump(bus=EV.Bus(), engine=None).tick()

    check("the old jarvis log is gone", not good.exists(), f"{good} still there")
    check("a non-.jsonl file in the log folder is untouched", other.exists(),
          f"{other.name} was deleted")
    check("an ordinary file in the log folder is untouched", plain.exists(),
          f"{plain.name} was deleted")
    check("a log file in a SUBfolder is untouched", nested.exists(),
          "the sweep reached below the log directory")
    check("a same-named file in the folder next door is untouched",
          neighbour.exists(), "the sweep reached outside the log directory")
    FW.load_framework = _ORIG_LOAD


def t_it_is_idempotent_and_once_a_day():
    """Running it again cannot make anything worse, and the gate is real."""
    FW.load_framework = config(90)
    clear_logs()
    day_gate_reset()

    old = add(day_name(-200), 200)
    fresh = add(day_name(-3), 3)
    pump = EV.Pump(bus=EV.Bus(), engine=None)

    pump.tick()
    check("the first tick of the day removes the old file", not old.exists())
    before = sorted(p.name for p in LOG.glob("*"))

    # The same day, many ticks later: the gate means the sweep does not even
    # run, so nothing can be removed and no directory listing is paid for.
    for _ in range(5):
        pump.tick()
    check("later ticks the same day leave the folder exactly as it was",
          sorted(p.name for p in LOG.glob("*")) == before,
          f"{before} -> {sorted(p.name for p in LOG.glob('*'))}")

    # And the sweep itself is idempotent: no gate, run twice, same result.
    first = FW.prune_logs()
    second = FW.prune_logs()
    check("the sweep returns 0 when there is nothing old left",
          first == 0 and second == 0, f"{first}, {second}")
    check("the fresh file is still there after all of that", fresh.exists())

    day_gate_reset()
    EV.Pump(bus=EV.Bus(), engine=None).tick()
    check("with the day gate cleared it sweeps again and removes nothing",
          sorted(p.name for p in LOG.glob("*")) == before,
          f"{before} -> {sorted(p.name for p in LOG.glob('*'))}")
    FW.load_framework = _ORIG_LOAD


def t_a_failure_does_not_stop_the_other_pollers():
    """A poller that throws must not take the pump down with it. This one
    swallows its own errors, and Pump.tick counts the rest."""
    saved = FW.load_framework
    FW.load_framework = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("config on fire"))
    day_gate_reset()
    pump = EV.Pump(bus=EV.Bus(), engine=None)
    try:
        pump.tick()
        survived = True
        why = ""
    except Exception as exc:
        survived = False
        why = f"{type(exc).__name__}: {exc}"
    check("a config that throws every call does not kill the tick", survived, why)
    check("it still ticks, and says nothing was removed",
          pump.ticks == 1 and EV._RETENTION_SEEN.get("removed") is None,
          repr(EV._RETENTION_SEEN))
    FW.load_framework = saved


def t_it_writes_nothing_and_says_nothing():
    """No event, no new file: a tidy-up is not news for a lock screen."""
    FW.load_framework = config(90)
    clear_logs()
    day_gate_reset()
    add(day_name(-200), 200)
    bus = EV.Bus()
    EV.Pump(bus=bus, engine=None).tick()
    got = bus.since(0)
    events = got[0] if isinstance(got, tuple) else got
    check("no event is published by the sweep",
          not [e for e in events if getattr(e, "kind", "") == "log_retention"],
          f"kinds: {[getattr(e, 'kind', '') for e in events]}")
    # Nothing named it into existence: the sweep deletes and creates nothing,
    # so a folder holding one old log holds no logs at all afterwards.
    check("the sweep created no log file of its own",
          sorted(p.name for p in LOG.glob("jarvis-*.jsonl")) == [],
          f"{sorted(p.name for p in LOG.glob('jarvis-*.jsonl'))}")
    FW.load_framework = _ORIG_LOAD


def t_the_config_ships_with_the_setting_it_needs():
    """retention_days must still be in the file the backend reads, or the
    pruner silently falls back to its own default of 90."""
    toml = None
    for c in (REBUILT / "jarvis-framework.toml", BACKEND / "jarvis-framework.toml",
              REPO / "backend" / "jarvis-framework.toml"):
        if c.is_file():
            toml = c
            break
    if toml is None:
        skip("jarvis-framework.toml is not on this machine; "
             "cannot check the shipped window")
        return
    src = toml.read_text(encoding="utf-8", errors="replace")
    check("the shipped config still states retention_days",
          "retention_days" in src, f"looked in {toml}")
    check("...and its logging section is the one that owns it",
          "[logging]" in src, f"looked in {toml}")


if __name__ == "__main__":
    for fn in (t_a_shipped_module_calls_the_pruner, t_the_pump_runs_it,
               t_old_is_deleted_fresh_is_kept,
               t_todays_file_survives_even_when_it_looks_old,
               t_the_setting_is_what_decides,
               t_keep_everything_means_keep_everything,
               t_nothing_outside_the_log_folder_is_reached,
               t_it_is_idempotent_and_once_a_day,
               t_a_failure_does_not_stop_the_other_pollers,
               t_it_writes_nothing_and_says_nothing,
               t_the_config_ships_with_the_setting_it_needs):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if SKIPPED:
        print("skipped: " + "; ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
