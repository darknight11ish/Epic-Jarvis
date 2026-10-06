"""test_open_chat.py - "open a chat" and close phrasings, answered without
the AI model (the floating face, 2026-09-27: the desktop's small
always-on-top window with just Jarvis's animated face - no text box, voice
only - expands into the real Jarvis bar on this phrase).

    python3 backend/test_open_chat.py

What it proves:
  - a real spread of phrasings - "open a chat", "open the chat window",
    "show me the chat", "bring up the chat", "open the Jarvis bar" and
    close variants - are answered by jarvis_quick.py's own grammar with no
    model, end to end (Q.answer_turn), and a near miss ("open a chat about
    my day") is not;
  - the reply is fixed, non-empty text - no gate, no card, nothing written;
  - `route_fields()` carries the intent's own name, unchanged, in
    `X-Jarvis-Route`'s "quick" field - the one thing a client reads to know
    to bring its own window forward (jarvis-desktop/src-tauri/src/
    commands.rs, `stream_chat`);
  - it passes the same style rules test_manner.py holds every fixed line in
    this repo to (I135): no emoji, no "!", at most one "sorry", no film
    phrases.
No network, no model.
"""
from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py")

import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as SCHED  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class _Sched:
    def __init__(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.inner = SCHED.Scheduler(Path(self.tmp.name) / "schedule.json")

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def close(self):
        # Stop the loop first, then let the database handle be collected: a
        # live scheduler can still hold schedule.json open, and Windows refuses
        # to delete a file another handle holds (POSIX does not care, which is
        # why this only ever bit on the owner's PC - 2026-10-03). What is left
        # is a disposable temp folder.
        try:
            self.inner.stop()
        except Exception:
            pass
        gc.collect()
        try:
            self.tmp.cleanup()
        except OSError:
            pass


PHRASINGS = (
    "open a chat",
    "open the chat",
    "open a chat window",
    "open the chat window",
    "show me a chat",
    "show me the chat",
    "show me the chat window",
    "show the chat",
    "show chat",
    "bring up a chat",
    "bring up the chat",
    "bring up the chat window",
    "open the Jarvis bar",
    "open Jarvis bar",
    "show me the Jarvis bar",
    "show the Jarvis bar",
    "bring up the Jarvis bar",
    "hey Jarvis, open a chat",
)

NEAR_MISSES = (
    "open a chat about my day",
    "open the door",
    "show me the calendar",
    "open a chat with Alex",
)


def t_every_phrasing_is_answered_with_no_model():
    now = time.time()
    sched = _Sched()
    try:
        for text in PHRASINGS:
            intent = Q.match(text, now=now)
            check(f"matches the no-model grammar: {text!r}",
                  intent is not None and intent.name == "open_chat", intent)
            result = Q.run(intent, sched, now) if intent is not None else None
            check(f"and really answers, no model: {text!r}",
                  result is not None and isinstance(result.reply, str) and result.reply.strip(),
                  result)
        for text in NEAR_MISSES:
            intent = Q.match(text, now=now)
            check(f"a near miss goes to the model: {text!r}",
                  intent is None or intent.name != "open_chat", intent)
    finally:
        sched.close()


def t_answer_turn_end_to_end():
    sched = _Sched()
    try:
        for prov in ("typed", "voice"):
            body = {"messages": [{"role": "user", "content": "open a chat",
                                  "provenance": prov}], "stream": True}
            res = Q.answer_turn(body, sched=sched, now=time.time())
            check(f"answers end to end ({prov})",
                  res is not None and res.intent == "open_chat", res)
        body = {"messages": [{"role": "user", "content": "open a chat",
                              "provenance": "pasted"}]}
        check("pasted text goes to the model instead",
              Q.answer_turn(body, sched=sched) is None)
    finally:
        sched.close()


def t_route_carries_the_intent_name():
    sched = _Sched()
    try:
        intent = Q.match("open a chat")
        result = Q.run(intent, sched, time.time())
        fields = Q.route_fields(result)
        check("X-Jarvis-Route's quick field says open_chat",
              fields.get("quick") == "open_chat", fields)
        check("no gate is raised (not marked private)",
              "gate" not in fields, fields)
    finally:
        sched.close()


def t_fixed_line_style():
    sched = _Sched()
    try:
        intent = Q.match("open a chat")
        reply = Q.run(intent, sched, time.time()).reply
        check("no emoji, no exclamation mark, no film phrases",
              "!" not in reply
              and not any(w in reply.lower() for w in ("sir", "at your service", "j.a.r.v.i.s")))
    finally:
        sched.close()


def t_the_phones_own_list_is_current():
    # Cross-cutting audit finding #7, 2026-09-27: the phone's local
    # net/OpenChatPhrase.kt used to be a separately hand-maintained list
    # that had already drifted from this grammar. Generated now, and
    # checked here the same way test_card_words.py holds card-words-cases.json
    # to its own producer.
    sys.path.insert(0, str(HERE.parent / "tools"))
    import gen_open_chat_cases as G
    doc = G.document()
    have = G.PHONE.read_text(encoding="utf-8") if G.PHONE.exists() else ""
    check(f"{G.PHONE.relative_to(G.ROOT)} matches (python3 tools/gen_open_chat_cases.py)",
          have == doc)


if __name__ == "__main__":
    for fn in (t_every_phrasing_is_answered_with_no_model, t_answer_turn_end_to_end,
               t_route_carries_the_intent_name, t_fixed_line_style,
               t_the_phones_own_list_is_current):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            import traceback
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
