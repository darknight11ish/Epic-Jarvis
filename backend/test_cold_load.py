"""test_cold_load.py - Spotlight 4: the cold-load progress line, and the
wake-from-sleep pre-warm (2026-10-18).

    python -B backend/test_cold_load.py

Runs anywhere: no model, no socket, no real Ollama. Everything here is driven
by injected answers and a fake warm-up; the ONE thing that is real is each
module's own function.

What it proves:

 1. THE COLD-LOAD NOTE. When the bounded /api/ps probe says the everyday model
    is not in memory, ONE plain sentence reaches the progress line through the
    existing activity doorbell the HUD passes into a turn (`announce`): it
    says the model is loading and the answer waits, names no ETA it cannot
    stand behind (no digit, no "seconds", no measured claim), and is said ONCE
    per cold start, not once per check.
 2. IT IS CLEARED WHEN WARM. A warm probe clears the sentence only when the
    line is still showing OUR sentence; another step's detail is never wiped.
 3. UNKNOWN IS NOT COLD AND NOT WARM. A probe that cannot tell (no /api/ps
    answer, another machine) says nothing and clears nothing; a probe that
    raises is the same.
 4. THE CHECK IS BOUNDED, NOT A TIMER. The helper calls the probe once per
    check and never sleeps: a hundred checks finish at once, so a fake timer
    delay or a retry loop would fail these checks.
 5. THE WAKE PRE-WARM. A clock jump of more than 300 s between two heartbeat
    clock reads calls the injected warm-up ONCE; a small gap, or no gap, calls
    it never; a later (second) wake warms once more; two ticks at once cannot
    load twice; and a warm-up that fails comes back as a plain sentence, never
    a traceback that could kill the heartbeat.
 6. THE SWITCHES: `[initiative] warm_on_wake = false` (or an explicit
    enabled=False) means NO load; the default is on, the same shape as
    `[power] warm_prefix`; Standby means no load.
 7. THE REAL LOOP STARTS, BEATS ONCE AND STOPS. The clock-sliced `_run` keeps
    the old "first beat is immediate" behaviour and stops promptly.

No pytest, no network, no model. Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_TMP = tempfile.mkdtemp(prefix="jarvis-cold-load-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
os.environ["JARVIS_CONFIG_DIR"] = _TMP
os.environ["JARVIS_FRAMEWORK_TOML"] = os.path.join(_TMP, "none.toml")

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "rebuilt/jarvis_initiative.py")

import jarvis_agent as A  # noqa: E402
import jarvis_initiative as IN  # noqa: E402

PASSED, SKIPPED, FAILED = [], [], []
SENTENCE = A.COLD_LOAD_NOTE


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-1200:])


def fresh():
    """Every note starts with the progress-line state cleared."""
    A._COLD_NOTE_SHOWN = False


class Recorder:
    def __init__(self):
        self.said = []

    def __call__(self, text):
        self.said.append(text)


# --------------------------------------------------------------------------
#   1-4: the cold-load progress line
# --------------------------------------------------------------------------


def t_the_sentence_is_plain_and_claims_no_eta():
    check("COLD_LOAD_NOTE is one non-empty sentence",
          isinstance(SENTENCE, str) and len(SENTENCE) > 40
          and SENTENCE.endswith("."), repr(SENTENCE))
    check("it says the local model is loading, in plain words",
          "Loading the local model" in SENTENCE and "GPU memory" in SENTENCE,
          SENTENCE)
    check("it says the first answer waits for it, which is the whole truth",
          "first answer waits" in SENTENCE, SENTENCE)
    check("it claims NO measured ETA - no digit, no seconds, no tilde",
          not any(ch.isdigit() for ch in SENTENCE)
          and "second" not in SENTENCE.lower()
          and "~" not in SENTENCE, SENTENCE)
    check("the sentence is ASCII (it crosses a console that is not always UTF-8)",
          all(ord(ch) < 128 for ch in SENTENCE), SENTENCE)


def t_a_cold_model_puts_the_sentence_on_the_progress_line():
    fresh()
    rec = Recorder()
    got = A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                            model_waking=lambda url, model: True, announce=rec)
    check("a COLD probe answers cold=True and says the sentence",
          got.get("cold") is True and got.get("said") == SENTENCE, got)
    check("... and the doorbell was rung exactly once with it",
          rec.said == [SENTENCE], rec.said)


def t_one_cold_start_is_said_once_not_once_per_check():
    fresh()
    rec = Recorder()
    first = A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                              model_waking=lambda url, model: True, announce=rec)
    second = A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                               model_waking=lambda url, model: True, announce=rec)
    check("the first cold check says the sentence", first.get("said") == SENTENCE, first)
    check("a second cold check in the same cold start does NOT say it again",
          second.get("cold") is True and second.get("said") == ""
          and rec.said == [SENTENCE], (second, rec.said))


def t_warm_clears_our_sentence_from_the_line():
    fresh()
    rec = Recorder()
    A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                      model_waking=lambda url, model: True, announce=rec)
    warm = A.cold_load_check(
        "http://127.0.0.1:11434", "qwen3.5:9b",
        model_waking=lambda url, model: False, announce=rec,
        activity=lambda: {"state": "working", "detail": SENTENCE})
    check("a WARM probe clears the sentence from the progress line",
          warm.get("cold") is False and warm.get("cleared") is True
          and rec.said[-1] == "", (warm, rec.said))
    again = A.cold_load_check(
        "http://127.0.0.1:11434", "qwen3.5:9b",
        model_waking=lambda url, model: False, announce=rec,
        activity=lambda: {"state": "working", "detail": SENTENCE})
    check("... and a second warm check clears nothing further",
          again.get("cleared") is False and rec.said[-1] == "", (again, rec.said))


def t_a_warm_probe_never_wipes_another_steps_detail():
    fresh()
    rec = Recorder()
    A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                      model_waking=lambda url, model: True, announce=rec)
    warm = A.cold_load_check(
        "http://127.0.0.1:11434", "qwen3.5:9b",
        model_waking=lambda url, model: False, announce=rec,
        activity=lambda: {"state": "working", "detail": "Step 2/3: reading the inbox"})
    check("a warm probe leaves ANOTHER step's detail alone (never a blanket clear)",
          warm.get("cleared") is False and rec.said == [SENTENCE], (warm, rec.said))
    after = A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                              model_waking=lambda url, model: True, announce=rec)
    check("... and the next cold start can still say the sentence once",
          after.get("said") == SENTENCE and rec.said[-1] == SENTENCE, rec.said)


def t_unknown_or_raising_probes_claim_nothing():
    fresh()
    rec = Recorder()
    unknown = A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                                model_waking=lambda url, model: None, announce=rec)
    check("a probe that cannot tell answers cold=None and says nothing",
          unknown.get("cold") is None and unknown.get("said") == ""
          and rec.said == [], (unknown, rec.said))
    check("... and the reason says plainly that the state could not be read",
          "could not be read" in str(unknown.get("reason")), unknown.get("reason"))

    def boom(url, model):
        raise OSError("no answer")
    raised = A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                               model_waking=boom, announce=rec)
    check("a probe that raises is the same refusal, never a traceback",
          raised.get("cold") is None and rec.said == [], raised)


def t_the_check_is_bounded_and_is_not_a_timer():
    fresh()
    calls = []

    def probe(url, model):
        calls.append(1)
        return False
    rec = Recorder()
    started = time.monotonic()
    for _ in range(100):
        A.cold_load_check("http://127.0.0.1:11434", "qwen3.5:9b",
                          model_waking=probe, announce=rec)
    took = time.monotonic() - started
    check("100 warm checks call the probe exactly 100 times - one bounded answer each",
          len(calls) == 100, len(calls))
    check("... and they take no measurable time: there is no sleep, retry or fake timer",
          took < 1.0, took)
    check("... and no sentence is said on a warm model", rec.said == [], rec.said)


# --------------------------------------------------------------------------
#   5-6: the wake-from-sleep pre-warm
# --------------------------------------------------------------------------


class Warmer:
    def __init__(self, answer=True):
        self.answer = answer
        self.calls = []

    def __call__(self):
        self.calls.append(time.time())
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def t_a_wake_jump_warms_once_and_no_jump_warms_never():
    e = IN.Engine(heartbeat_minutes=30)
    warm = Warmer()
    first = e.clock_tick(now=1000.0)
    check("the first clock read is only a baseline - no wake, no load",
          first.get("warmed") is False and warm.calls == [], first)
    small = e.clock_tick(now=1100.0)
    check("a 100-second gap is not a wake: no load",
          small.get("warmed") is False and warm.calls == []
          and "no wake" in str(small.get("reason")), small)
    direct = IN.Engine(heartbeat_minutes=30)
    direct_warm = Warmer()
    below = direct.warm_on_wake(now=1100.0, last=1000.0, warm=direct_warm)
    check("a gap under 300 s passed straight to the warm path is not a wake either",
          below.get("warmed") is False and direct_warm.calls == [], below)
    jumped = e.warm_on_wake(now=1500.0, last=1100.0, warm=warm)
    check("a gap over 300 s warms the everyday model once",
          jumped.get("warmed") is True and len(warm.calls) == 1, (jumped, warm.calls))
    check("... and the answer says the model is loading now, in plain words",
          "loading now" in str(jumped.get("reason")), jumped.get("reason"))


def t_one_warm_per_wake_and_a_later_wake_warms_again():
    e = IN.Engine(heartbeat_minutes=30)
    warm = Warmer()
    first = e.warm_on_wake(now=1000.0, last=100.0, warm=warm)
    second = e.warm_on_wake(now=1000.0, last=100.0, warm=warm)
    check("a second tick of the SAME wake never loads a second time",
          first.get("warmed") is True and second.get("warmed") is False
          and len(warm.calls) == 1
          and "already warmed" in str(second.get("reason")), (second, warm.calls))
    later = e.warm_on_wake(now=2000.0, last=1500.0, warm=warm)
    check("a LATER wake (another sleep) warms once more, still one call",
          later.get("warmed") is True and len(warm.calls) == 2,
          (later, warm.calls))


def t_the_setting_off_means_no_load_and_the_default_is_on():
    e = IN.Engine(heartbeat_minutes=30)
    warm = Warmer()
    off = e.warm_on_wake(now=1000.0, last=100.0, warm=warm, enabled=False)
    check("enabled=False loads nothing", off.get("warmed") is False
          and warm.calls == [] and "off" in str(off.get("reason")), off)
    keep = IN._cfg
    try:
        IN._cfg = lambda key, default=None: False if key == "warm_on_wake" else default
        check("[initiative] warm_on_wake = false is read as OFF", IN.warm_on_wake_on() is False,
              IN.warm_on_wake_on())
        IN._cfg = lambda key, default=None: default
        check("... and a missing key defaults to ON, the same shape as [power] warm_prefix",
              IN.warm_on_wake_on() is True, IN.warm_on_wake_on())
    finally:
        IN._cfg = keep


def t_standby_means_no_load():
    e = IN.Engine(heartbeat_minutes=30)
    warm = Warmer()
    got = e.warm_on_wake(now=1000.0, last=100.0, warm=warm, standby=lambda: True)
    check("a promised-free card is not warmed: Standby loads nothing",
          got.get("warmed") is False and warm.calls == []
          and "Standby" in str(got.get("reason")), got)


def t_a_failure_is_one_plain_sentence_and_never_kills_the_heartbeat():
    e = IN.Engine(heartbeat_minutes=30)
    warm = Warmer(RuntimeError("no GPU"))
    got = e.warm_on_wake(now=1000.0, last=100.0, warm=warm)
    check("a warm-up that raises comes back as warmed=False, never a traceback",
          got.get("warmed") is False, got)
    check("... and the reason names the failure plainly",
          "warm-up failed (RuntimeError)" in str(got.get("reason")), got.get("reason"))


def t_two_ticking_threads_cannot_load_twice():
    e = IN.Engine(heartbeat_minutes=30)
    warm = Warmer()
    e._warm_lock.acquire()
    try:
        got = e.warm_on_wake(now=1000.0, last=100.0, warm=warm)
    finally:
        e._warm_lock.release()
    check("while another warm-up holds the lock, nothing is loaded and the reason says so",
          got.get("warmed") is False and warm.calls == []
          and "already loading" in str(got.get("reason")), got)


def t_the_real_loop_beats_once_and_stops():
    e = IN.Engine(heartbeat_minutes=30)
    e.start()
    deadline = time.monotonic() + 5.0
    while e.beats < 1 and time.monotonic() < deadline:
        time.sleep(0.02)
    started = e.beats
    e.stop()
    check("Engine.start() still beats once immediately, as it always did",
          started >= 1, started)
    check("... and the sliced loop stops promptly", not e.running, e.running)


# --------------------------------------------------------------------------

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    try:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    except Exception:
        pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
