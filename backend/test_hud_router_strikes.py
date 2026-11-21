"""test_hud_router_strikes.py - the HUD half of the 2-strike coding fallback.

    py -3 -B backend/test_hud_router_strikes.py

THE RULING THIS PROVES (external review, 2026-11-19, 6.1). Keep the
deterministic `complexity >= 0.40` pre-gate as Stage 1, and PAIR it with a
2-strike / local-failure fallback for coding tasks. #1408 shipped the router
half - `jarvis_router.note_local_failure()`, `local_failure_strikes()`,
`reset_local_failures()`, and `choose(..., conversation=, coding=)` - and
NOTHING CALLED ANY OF IT. So two local failures could not let a coding turn's
third attempt escalate, because the count could never leave zero.

WHAT THIS SUITE RUNS, AND WHY IT IS NOT A SOURCE READ. It builds the text the
WHOLE patch stack leaves (`backend/_stack.stand_in("jarvis_hud.py")`), lifts
the shipping `router-strikes.patch` blocks out of it - the two recorder
helpers, and the three failure points and two success points they are called
from - and EXECUTES them against the real `jarvis_router`. The failure blocks
are driven with a raised exception (the shape the relay really gets) and the
success blocks with the summaries the local answering loop really returns.
Every check reads what the router recorded, or what the lifted block did; none
of them greps the HUD's text.

WHAT THE ROUTE MUST STILL BE. The patch only records and clears a count; the
router's own `choose()` does the deciding. Its gates are unchanged: two
failures still cannot lift taint, private content, a picture, a file, the
budget or Lockdown, a cloud turn is never recorded, a NON-coding turn never
gets the fallback, and the cloud still needs the owner's yes / this PC's
standing switch (gate 6). `backend/test_router_strikes.py` proves the router's
own half; this suite proves the HUD really feeds it.

A SCRATCH HOME IS MADE BEFORE ANY IMPORT (the router reads settings through
jarvis_presets), and no socket, model or live settings file is used.
Standard library only.
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import traceback
import types
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REBUILT = HERE / "rebuilt"

#: A scratch home BEFORE anything reads a settings file.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-hud-strikes-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import _stack  # noqa: E402
import jarvis_router as RT  # noqa: E402

FAILED, PASSED = [], []
LOCAL = "qwen3.5:9b"
CLOUD = RT.CLOUD_LANE
#: A short coding request: the router's own score is under 0.40, which is the
#: whole point of the fallback.
CODING = "fix this bug in my app"
#: An ordinary short question: never coding, so it must not get the fallback.
ORDINARY = "What is a semicolon?"
#: Private content: two failures must still not take it out of this PC.
PRIVATE = "What is my password for the bank?"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ==========================================================================
#  the shipping text, lifted out of the patch stack
# ==========================================================================

def _stack_text():
    """(the whole stacked HUD text, why it could not be built or "")."""
    src, log = _stack.stand_in("jarvis_hud.py")
    if not src:
        return None, "; ".join((log or [])[-3:]) or "empty stand-in"
    return src, ""


SRC, SRC_WHY = _stack_text()


def _slice(start: str, end: str) -> str:
    """One block of the shipping HUD text, from `start` up to `end`."""
    if SRC is None:
        raise AssertionError(SRC_WHY)
    a = SRC.find(start)
    if a < 0:
        raise AssertionError(f"the patch stack does not carry {start[:60]!r}")
    b = SRC.find(end, a)
    if b < 0:
        raise AssertionError(f"the block after {start[:60]!r} has no {end[:40]!r}")
    return SRC[a:b]


def _exec(code: str, ns: dict) -> dict:
    exec(compile(code, "<lifted from the patch stack>", "exec"), ns)
    return ns


def _body(block: str, indent: int) -> str:
    """One lifted block, dedented and re-indented to sit in a wrapper."""
    return "".join(" " * indent + line + "\n"
                   for line in textwrap.dedent(block).splitlines())


def _helpers():
    """The two recorder helpers, lifted as they ship."""
    block = _slice("def _note_local_failure(lane: str, local_model: str, conversation) -> None:",
                   "def _temporary_chat(body) -> bool:")
    ns = _exec(block, {})
    return ns["_note_local_failure"], ns["_clear_local_failures"]


def _fresh(conv):
    RT.reset_local_failures(conv)
    return conv


def _clean():
    RT._LOCAL_FAILURES.clear()


class _Self:
    """The bits of the request handler the lifted blocks touch."""

    def __init__(self):
        self.sent = []

    def _send(self, code, body):
        self.sent.append((code, body))
        return code


def _drive_failure(lane_value, conv):
    """Run the shipping generic failure handler with one raised exception."""
    body = _slice("                _note_local_failure(lane, local_model, _conversation)\n"
                  "                # chat-stream.patch: what to DO, first. The cloud line used",
                  "\n            except (BrokenPipeError, ConnectionResetError, TimeoutError")
    code = ("def _drive(self, route_header, lane, local_model, _conversation,\n"
            "           active_ollama_url, JARVIS_URL, _note_local_failure):\n"
            "    try:\n"
            "        raise RuntimeError('the local lane produced no answer')\n"
            "    except Exception as exc:\n"
            "        try:\n"
            + _body(body, 12)
            + "        except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout):\n"
            + "            pass\n")
    ns = {"socket": __import__("socket")}
    _exec(code, ns)
    self_ = _Self()
    ns["_drive"](self_, {}, lane_value, LOCAL, conv, lambda: "http://127.0.0.1:11434",
                 "http://127.0.0.1:8000", _helpers()[0])
    return self_


def _drive_http_failure(lane_value, conv):
    """Run the shipping HTTP-refusal handler with one raised HTTPError."""
    block = _slice("        except urllib.error.HTTPError as exc:\n            _note_local_failure(",
                   "\n            self._send(exc.code, {")
    code = ("def _drive(lane, local_model, _conversation, _note_local_failure):\n"
            "    try:\n"
            "        raise urllib.error.HTTPError('jarvis://local', 503, 'unavailable',\n"
            "                                     None, None)\n"
            + _body(block, 4)
            + "        pass\n")
    ns = {"urllib": urllib}
    _exec(code, ns)
    ns["_drive"](lane_value, LOCAL, conv, _helpers()[0])


def _drive_success(lane_value, conv):
    """Run the shipping plain-relay SUCCESS point."""
    block = _slice("                        if _speed is not None:\n"
                   "                            _speed.finish(lane)\n"
                   "                        _clear_local_failures(",
                   "\n                    except (BrokenPipeError")
    code = ("def _drive(_speed, lane, local_model, _conversation, _clear_local_failures):\n"
            + _body(block, 4))
    ns = {}
    _exec(code, ns)
    ns["_drive"](_Speed(), lane_value, LOCAL, conv, _helpers()[1])


class _Speed:
    def finish(self, *a, **k):
        return None


def _drive_turn_summary(turn, lane_value, conv):
    """Run the shipping local answering loop's returned-summary point."""
    block = _slice("                    _turn = _turn or {}\n"
                   "                    # router-strikes.patch (2026-11-20): the local answering",
                   "\n                    # chat-history.patch: the answer and the tools that ran,")
    code = ("_turn = None\n"
            "def _drive(turn, lane, local_model, _conversation,\n"
            "           _note_local_failure, _clear_local_failures):\n"
            "    global _turn\n"
            "    _turn = turn\n"
            + _body(block, 4))
    ns = {"_note_local_failure": _helpers()[0],
          "_clear_local_failures": _helpers()[1]}
    _exec(code, ns)
    ns["_drive"](turn, lane_value, LOCAL, conv,
                 ns["_note_local_failure"], ns["_clear_local_failures"])


def _choose(conv, *, coding=True, query=CODING, **kw):
    args = dict(local_model=LOCAL, lanes=[CLOUD], owner_said_yes=True,
                conversation=conv, coding=coding)
    args.update(kw)
    return RT.choose(query, **args)


# ==========================================================================
#  1. the stack really carries the writers, and they compile
# ==========================================================================

def t_the_patch_stack_carries_the_recorder():
    check("the whole patch stack can be built", SRC is not None, SRC_WHY)
    if SRC is None:
        return
    note, clear = _helpers()
    check("the two recorder helpers ship and compile in the HUD text",
          callable(note) and callable(clear), (note, clear))


# ==========================================================================
#  2. the recorder: a local failure counts one, a cloud lane none
# ==========================================================================

def t_a_local_failure_records_one_strike():
    conv = _fresh("hud-failure")
    _drive_failure(LOCAL, conv)
    check("the relay's generic failure handler records ONE local failure",
          RT.local_failure_strikes(conv) == 1, RT.local_failure_strikes(conv))
    _drive_http_failure(LOCAL, conv)
    check("... and so does the HTTP-refusal handler (a local 429/500/503)",
          RT.local_failure_strikes(conv) == 2, RT.local_failure_strikes(conv))
    _drive_turn_summary({"finish_reason": None, "client_gone": False}, LOCAL, conv)
    check("... the local answering loop's error summary records one too",
          RT.local_failure_strikes(conv) == 3, RT.local_failure_strikes(conv))
    _clean()


def t_a_cloud_turn_is_never_recorded():
    conv = _fresh("hud-cloud")
    note, _clear = _helpers()
    _drive_failure(CLOUD, conv)
    _drive_http_failure(CLOUD, conv)
    _drive_turn_summary({"finish_reason": None, "client_gone": False}, CLOUD, conv)
    check("a cloud lane's failure is NOT recorded - it is not evidence about the "
          "local model", RT.local_failure_strikes(conv) == 0,
          RT.local_failure_strikes(conv))
    note(CLOUD, LOCAL, conv)
    check("... the recorder helper itself is a no-op for a cloud lane",
          RT.local_failure_strikes(conv) == 0, RT.local_failure_strikes(conv))
    _clean()


def t_a_successful_local_turn_clears_the_count():
    conv = _fresh("hud-success")
    note, _clear = _helpers()
    note(LOCAL, LOCAL, conv)
    note(LOCAL, LOCAL, conv)
    check("two failures are on the counter", RT.local_failure_strikes(conv) == 2,
          RT.local_failure_strikes(conv))
    _drive_success(LOCAL, conv)
    check("the plain relay finishing a local stream CLEARS the count",
          RT.local_failure_strikes(conv) == 0, RT.local_failure_strikes(conv))
    note(LOCAL, LOCAL, conv)
    _drive_turn_summary({"finish_reason": "stop", "client_gone": False}, LOCAL, conv)
    check("... and a local answer with a finish_reason clears it too",
          RT.local_failure_strikes(conv) == 0, RT.local_failure_strikes(conv))
    note(LOCAL, LOCAL, conv)
    _drive_success(CLOUD, conv)
    check("a cloud success clears nothing: only a LOCAL answer is evidence",
          RT.local_failure_strikes(conv) == 1, RT.local_failure_strikes(conv))
    _clean()


def t_a_client_gone_turn_is_neither():
    conv = _fresh("hud-gone")
    _drive_turn_summary({"finish_reason": None, "client_gone": True}, LOCAL, conv)
    check("a turn the client walked away from is not a local failure",
          RT.local_failure_strikes(conv) == 0, RT.local_failure_strikes(conv))
    _clean()


# ==========================================================================
#  3. two HUD-recorded failures + a third attempt = the router escalates
# ==========================================================================

def t_two_failures_let_the_third_attempt_escalate():
    conv = _fresh("hud-escalate")
    first = _choose(conv)
    check("with no failures a short coding turn stays local",
          first.gate == "complexity" and first.lane == LOCAL, (first.gate, first.lane))
    _drive_failure(LOCAL, conv)
    second = _choose(conv)
    check("ONE recorded failure does not escalate",
          second.gate == "complexity" and second.lane == LOCAL,
          (second.gate, second.lane))
    _drive_failure(LOCAL, conv)
    third = _choose(conv)
    check("TWO recorded failures let the third attempt reach the cloud even "
          "under 0.40", third.gate == "escalate" and third.lane == CLOUD,
          (third.gate, third.lane))
    check("... and the router's reason says why", "failed on this PC 2 times" in third.reason,
          third.reason)
    check("... its complexity is still reported honestly, under the threshold",
          third.complexity < 0.40, third.complexity)
    _clean()


def t_a_new_conversation_starts_at_zero():
    a = _fresh("hud-conv-a")
    b = _fresh("hud-conv-b")
    _drive_failure(LOCAL, a)
    _drive_failure(LOCAL, a)
    check("the count is kept for the conversation the HUD recorded against",
          RT.local_failure_strikes(a) == 2, RT.local_failure_strikes(a))
    check("a NEW conversation starts at zero", RT.local_failure_strikes(b) == 0,
          RT.local_failure_strikes(b))
    check("... so its coding turn stays local", _choose(b).gate == "complexity",
          _choose(b).gate)
    _clean()


def t_a_private_turn_stays_local_after_the_huds_two_failures():
    conv = _fresh("hud-private")
    _drive_failure(LOCAL, conv)
    _drive_failure(LOCAL, conv)
    d = _choose(conv, query=PRIVATE)
    check("a private turn with two HUD-recorded failures STILL stays on this PC",
          d.gate == "private" and d.lane == LOCAL, (d.gate, d.lane))
    _clean()


def t_a_non_coding_turn_does_not_get_the_fallback():
    conv = _fresh("hud-noncoding")
    _drive_failure(LOCAL, conv)
    _drive_failure(LOCAL, conv)
    d = _choose(conv, coding=False, query=ORDINARY)
    check("two failures on a NON-coding turn do not escalate it",
          d.gate == "complexity" and d.lane == LOCAL, (d.gate, d.lane))
    _clean()


# ==========================================================================
#  4. the recorders never break a turn, and hold counts only
# ==========================================================================

def t_a_broken_router_never_breaks_the_relay():
    conv = _fresh("hud-broken-router")
    note, clear = _helpers()
    broken = types.ModuleType("jarvis_router")

    def _boom(*_a, **_k):
        raise RuntimeError("the router is broken")

    broken.note_local_failure = _boom
    broken.reset_local_failures = _boom
    saved = sys.modules.get("jarvis_router")
    sys.modules["jarvis_router"] = broken
    try:
        try:
            note(LOCAL, LOCAL, conv)
            clear(LOCAL, LOCAL, conv)
            raised = None
        except Exception as exc:            # noqa: BLE001 - the point is that it does not
            raised = exc
    finally:
        if saved is not None:
            sys.modules["jarvis_router"] = saved
        else:
            sys.modules.pop("jarvis_router", None)
    check("a router that raises is swallowed: bookkeeping is never the reason a "
          "turn fails", raised is None, raised)


def t_the_counter_holds_counts_and_no_words():
    conv = _fresh("hud-words")
    _drive_failure(LOCAL, conv)
    _drive_failure(LOCAL, conv)
    check("the HUD keeps no words - the router's store holds a count",
          RT._LOCAL_FAILURES.get(conv) == 2, RT._LOCAL_FAILURES.get(conv))
    _clean()


# ==========================================================================

TESTS = [
    t_the_patch_stack_carries_the_recorder,
    t_a_local_failure_records_one_strike,
    t_a_cloud_turn_is_never_recorded,
    t_a_successful_local_turn_clears_the_count,
    t_a_client_gone_turn_is_neither,
    t_two_failures_let_the_third_attempt_escalate,
    t_a_new_conversation_starts_at_zero,
    t_a_private_turn_stays_local_after_the_huds_two_failures,
    t_a_non_coding_turn_does_not_get_the_fallback,
    t_a_broken_router_never_breaks_the_relay,
    t_the_counter_holds_counts_and_no_words,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
