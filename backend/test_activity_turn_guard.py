"""A finished chat turn cannot leave the benchmark refusing for hours.

    python3 backend/test_activity_turn_guard.py

WHY THIS SUITE EXISTS. Measured 2026-11-06: `/api/bench/run` refused with
`409 {"error": "Jarvis is answering. Measuring now would time the queue, not
the model."}` for over four hours, while `/api/bench` said `running: null`,
`/api/status` said no latch, `/api/voice/status` said not live and
`/api/pending` was empty. The reason was the HUD's in-memory activity mark:
`jarvis_bench.answer_streaming()` -> `jarvis_power_switch._busy_reason()` ->
`jarvis_power.in_flight()` -> `jarvis_events.activity()` still said
"thinking". `/api/chat` writes "thinking" at the top of the turn, but its
only "idle" write is in a `finally` several hundred lines lower - a turn
answered by the jarvis_quick fast path RETURNS before that block, and a raise
while the lane, the memory and the payload are chosen never reaches it. The
only cure was restarting the backend, which cleared the in-memory dict.

The owner's ruling of 2026-11-06 is what this file proves, in three parts:
  (a) a try/finally on every turn path - driven here through the REAL wrapper
      lifted out of the installed file (or the patch stack's own text for it),
      with the real jarvis_events bus and the real jarvis_bench module;
  (b) an explicit startup reset of the activity mark;
  (c) a five-minute stale lease: a busy mark that shows no progress is
      auto-cleared with ONE structured warning, the benchmark proceeds, and
      the 409 body / /api/status name the reason and the age.
A real turn is still protected: the mark is refreshed by every streamed chunk
(`_activity_touch`), by every tool step (announce), and by the exact
in-process answer count the wrapper sets and clears.

What this suite cannot prove: that the owner's installed jarvis_hud.py has the
patch applied - only scripts/apply-patches.ps1 there can do that. It drives the
patch's own added code, which is what `_where.hud_block` is for.
"""
from __future__ import annotations

import contextlib
import io
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import hud_block                      # noqa: E402

import jarvis_bench as B                          # noqa: E402
import jarvis_events                              # noqa: E402
import jarvis_power                               # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIP {name} - {why}")


def _reset():
    jarvis_bench_bus = jarvis_events
    jarvis_bench_bus.reset_activity()
    B._reset_for_tests()


def _stale(seconds_ago=305.0):
    """Make the mark claim a busy state with no progress for `seconds_ago`."""
    jarvis_events._ACTIVITY["updated_at_mono"] = time.monotonic() - float(seconds_ago)


# --------------------------------------------------------------------------
#   (c) the five-minute stale lease, and the bench guard it frees
# --------------------------------------------------------------------------

def t_a_fresh_busy_mark_still_refuses():
    _reset()
    jarvis_events.set_activity("thinking")
    check("a fresh 'thinking' mark is still a refusal",
          B.answer_streaming() == B.ANSWER_STREAMING, B.answer_streaming())
    try:
        B.check_job({"confirm": {"may_evict": True}}, model="qwen3.5:9b",
                    lane="everyday", get=_fake_get(),
                    standby=lambda: False, tasks=lambda: [],
                    running=lambda: None)
        refused = False
    except B.Refusal:
        refused = True
    check("... and check_job refuses with it", refused)
    _reset()


def t_a_stale_mark_is_cleared_and_the_benchmark_proceeds():
    _reset()
    jarvis_events.set_activity("thinking")
    _stale()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        sentence = B.answer_streaming()
    check("a busy mark with no progress for 305 s is NOT a refusal",
          sentence is None, sentence)
    check("... it is auto-cleared to idle",
          jarvis_events.activity().get("state") == "idle",
          jarvis_events.activity())
    warning = err.getvalue()
    check("... and ONE structured warning names the state and the age",
          "STALE" in warning and "'thinking'" in warning and "305" in warning,
          warning)
    err2 = io.StringIO()
    with contextlib.redirect_stderr(err2):
        B.answer_streaming()
    check("... the warning is not repeated on the next look",
          "STALE" not in err2.getvalue(), err2.getvalue())

    # And the guard itself - the row that refused the owner - passes now.
    try:
        B.check_job({"confirm": {"may_evict": True}}, model="qwen3.5:9b",
                    lane="everyday", get=_fake_get(),
                    standby=lambda: False, tasks=lambda: [],
                    running=lambda: None, base="http://127.0.0.1:11436")
        cleared = True
    except B.Refusal as exc:
        cleared = exc.code != 409 or "answering" not in str(exc.body.get("error"))
    check("... so /api/bench/run's own check_job no longer refuses it", cleared)
    _reset()


def t_progress_keeps_a_real_turn_fresh():
    _reset()
    jarvis_events.set_activity("speaking")
    _stale(3600.0)
    jarvis_events.touch_activity()
    check("one heartbeat (a streamed chunk) makes an hour-old mark fresh again",
          B.answer_streaming() == B.ANSWER_STREAMING, B.answer_streaming())
    _reset()


def t_the_exact_flag_still_refuses_when_the_mark_is_fresh():
    _reset()
    B.note_answer_start()
    B.note_answer_start()
    B.note_answer_end()
    check("two answers in flight, one done: still refused",
          B.answer_streaming() == B.ANSWER_STREAMING, B.answer_streaming())
    B.note_answer_end()
    check("... both done: allowed", B.answer_streaming() is None)
    _reset()


def t_a_stale_mark_frees_standby_too():
    _reset()
    jarvis_events.set_activity("working")
    _stale()
    check("in_flight() clears the same leftover",
          jarvis_power.in_flight() is None, jarvis_power.in_flight())
    check("... and the mark it read is idle now",
          jarvis_events.activity().get("state") == "idle")
    _reset()


def t_the_409_body_names_the_held_state_and_its_age():
    _reset()
    jarvis_events.set_activity("speaking")
    try:
        B.check_job({"confirm": {"may_evict": True}}, model="qwen3.5:9b",
                    lane="everyday", get=_fake_get(),
                    standby=lambda: False, tasks=lambda: [],
                    running=lambda: None)
        body = {}
    except B.Refusal as exc:
        body = exc.body
    check("the refusal carries the reason that held the model",
          "speaking" in str(body.get("busy_reason") or ""), body)
    check("... and the age of that claim, as a number",
          isinstance(body.get("activity_age_s"), (int, float))
          and body["activity_age_s"] < 5.0, body)
    _reset()


# --------------------------------------------------------------------------
#   (b) the startup reset
# --------------------------------------------------------------------------

def t_the_startup_reset_is_explicit_and_real():
    _reset()
    jarvis_events.set_activity("thinking")
    _stale()
    check("before the boot reset the mark is a leftover", B.answer_streaming() is None)
    jarvis_events._ACTIVITY.update(state="thinking", detail="")
    jarvis_events.reset_activity()
    check("reset_activity() clears it", jarvis_events.activity().get("state") == "idle",
          jarvis_events.activity())
    text = _patch_text()
    check("... and the boot sequence calls it explicitly",
          '+            _ev.reset_activity()' in text,
          "the patch has no reset_activity() line in the boot block")
    _reset()


# --------------------------------------------------------------------------
#   (a) the wrapper: every exit from a /api/chat turn clears the mark
# --------------------------------------------------------------------------

def _patch_text() -> str:
    path = HERE / "activity-turn-guard.patch"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _added_block(start, stop=""):
    """Contiguous ADDED lines of the patch, from `start` until `stop`."""
    out, inside = [], False
    for line in _patch_text().splitlines():
        if not inside:
            if line.startswith("+" + start):
                inside = True
            else:
                continue
        if not line.startswith("+"):
            break
        body = line[1:]
        if stop and body.startswith(stop):
            break
        out.append(body)
    return "\n".join(out) + ("\n" if out else "")


def _wrapper():
    """The patch's own do_POST wrapper, exec'd with the real bus and bench.

    The wrapper sits on `def do_POST(self):`, which is a CONTEXT line of the
    patch (the original method line is kept); its added lines start at the
    docstring. So the def is put back by hand and the body dedented one class
    level, which is the same text the owner's installed file holds.
    """
    source = _added_block(
        '        """Run one POST. A /api/chat turn cannot leave "thinking" behind.',
        "    def _do_post(self):")
    if not source:
        return None, "no do_POST wrapper in activity-turn-guard.patch"
    body = "\n".join(line[4:] if line.startswith("    ") else line
                     for line in source.splitlines())
    source = "def do_POST(self):\n" + body + "\n"
    ns = {"_activity": jarvis_events.set_activity, "jarvis_bench": B}
    exec(compile(source, "<activity-turn-guard wrapper>", "exec"), ns)
    return ns, "activity-turn-guard.patch"


def _handler(ns, path, behaviour):
    class Fake:
        def __init__(self):
            self.path = path

        def _do_post(self):
            return behaviour()

    Fake.do_POST = ns["do_POST"]
    return Fake()


def t_a_quick_answer_cannot_leave_thinking():
    _reset()
    ns, where = _wrapper()
    if ns is None:
        skip("the wrapper is in the patch stack", where)
        return
    seen = {}

    def quick():
        jarvis_events.set_activity("thinking")
        seen["during"] = B.answer_streaming()
        return "answered without the model"

    out = _handler(ns, "/api/chat", quick).do_POST()
    check("a fast-path turn still returns its answer", out == "answered without the model")
    check("... while it was running the benchmark WAS refused",
          seen.get("during") == B.ANSWER_STREAMING, seen)
    check("... and the mark it left is idle, not 'thinking'",
          jarvis_events.activity().get("state") == "idle",
          jarvis_events.activity())
    check("... so the benchmark is not refused afterwards",
          B.answer_streaming() is None, B.answer_streaming())
    _reset()


def t_a_raise_while_choosing_the_lane_cannot_leave_thinking():
    _reset()
    ns, where = _wrapper()
    if ns is None:
        skip("the wrapper is in the patch stack", where)
        return

    def explode():
        jarvis_events.set_activity("thinking")
        raise RuntimeError("the lane choice blew up")

    try:
        _handler(ns, "/api/chat", explode).do_POST()
        raised = False
    except RuntimeError:
        raised = True
    check("the error still reaches the server, as it did before", raised)
    check("... but the activity mark is cleared on the way out",
          jarvis_events.activity().get("state") == "idle",
          jarvis_events.activity())
    check("... so the benchmark is not refused afterwards",
          B.answer_streaming() is None, B.answer_streaming())
    _reset()


def t_another_route_is_not_touched():
    _reset()
    ns, where = _wrapper()
    if ns is None:
        skip("the wrapper is in the patch stack", where)
        return

    def other():
        jarvis_events.set_activity("thinking")
        return "not a chat route"

    out = _handler(ns, "/api/other", other).do_POST()
    check("a non-chat POST is not changed", out == "not a chat route")
    check("... and its own activity mark is left exactly as it was",
          jarvis_events.activity().get("state") == "thinking",
          jarvis_events.activity())
    _reset()


# --------------------------------------------------------------------------
#   (c) the /api/status half: state, age and the hold reason
# --------------------------------------------------------------------------

def t_status_exposes_the_mark_state_age_and_reason():
    text, where = hud_block("def _activity_status()", "def _abort(resp)")
    if text is None:
        skip("the status helper is in the patch stack", where)
        return
    ns = {}
    exec(compile(text, "<activity-turn-guard status>", "exec"), ns)
    _reset()
    jarvis_events.set_activity("speaking")
    view = ns["_activity_status"]()
    check("/api/status's first key is the state word",
          view.get("state") == "speaking", view)
    check("... with its age in seconds, a number",
          isinstance(view.get("age_s"), (int, float)) and view["age_s"] < 5.0, view)
    reason = ns["_busy_reason_for_status"]()
    check("... and the hold reason is the same sentence the 409 carries",
          "speaking" in str(reason or ""), reason)

    patch_text = _patch_text()
    check("... and the /api/status payload really carries all three keys",
          'str(_activity_status().get("state") or "")' in patch_text
          and '"activity_age_s": _activity_status().get("age_s")' in patch_text
          and '"busy_reason": _busy_reason_for_status(),' in patch_text,
          "the status payload hunk is missing one of the three keys")
    _reset()


def t_the_streams_refresh_the_mark():
    """Every streamed chunk and tool step stamps the mark (the ruling's (c))."""
    patch = (HERE / "activity-turn-guard.patch")
    text = patch.read_text(encoding="utf-8") if patch.is_file() else ""
    check("the turn guard patch ships", bool(text), patch)
    if not text:
        return
    added = [line[1:] for line in text.splitlines() if line.startswith("+")]
    calls = [line for line in added
             if line.strip() in ("_activity_touch()", "_activity_touch(),")]
    check("... it refreshes the mark from BOTH streaming loops", len(calls) == 2, calls)
    _reset()
    jarvis_events.set_activity("working")
    _stale(120.0)
    before = jarvis_events.activity_age()
    jarvis_events.touch_activity()
    after = jarvis_events.activity_age()
    check("touch_activity() makes the age young again",
          before is not None and before > 100 and after is not None and after < 2,
          (before, after))
    check("... and it does not change the state word",
          jarvis_events.activity().get("state") == "working")
    _reset()


def _fake_get(models=("qwen3.5:9b",), version="0.40.12"):
    def get(url):
        if url.endswith("/api/tags"):
            return {"models": [{"name": n} for n in models]}
        if url.endswith("/api/ps"):
            return {"models": []}
        if url.endswith("/api/version"):
            return {"version": version}
        raise AssertionError(f"unexpected GET {url}")
    return get


if __name__ == "__main__":
    for fn in (t_a_fresh_busy_mark_still_refuses,
               t_a_stale_mark_is_cleared_and_the_benchmark_proceeds,
               t_progress_keeps_a_real_turn_fresh,
               t_the_exact_flag_still_refuses_when_the_mark_is_fresh,
               t_a_stale_mark_frees_standby_too,
               t_the_409_body_names_the_held_state_and_its_age,
               t_the_startup_reset_is_explicit_and_real,
               t_a_quick_answer_cannot_leave_thinking,
               t_a_raise_while_choosing_the_lane_cannot_leave_thinking,
               t_another_route_is_not_touched,
               t_status_exposes_the_mark_state_age_and_reason,
               t_the_streams_refresh_the_mark):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)


