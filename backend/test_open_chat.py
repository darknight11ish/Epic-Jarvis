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


# --- a typed decision word ("approve", 2026-10-11) ---------------------------
#
# The owner typed "approve" into the Jarvis bar and the app answered him with
# silence. The half that is right: a typed word can never approve anything
# (rule 4 - cards are decided by tapping the card's own button, and a risky one
# adds Windows Hello on this PC). The half that was wrong: the silence. A person
# who types "approve" is saying they cannot find the control, so the answer says
# WHERE it is.
#
# These travel the same path as "open a chat" above: jarvis_quick.py's own
# grammar, no model, the intent's name in X-Jarvis-Route's "quick" field.

#: Whole messages that are a decision and nothing else.
DECISIONS = (
    "approve",
    "Approve.",
    "approve it",
    "approve it please",
    "deny",
    "deny it",
    "reject",
    "reject it",
    "decline",
    "yes",
    "no",
    "yes please",
    # "no thanks" is here, not among the near misses: normalise() strips a
    # polite tail, so the grammar is handed exactly "no" - which IS the whole
    # message. Measured 2026-10-11 (the first version of this test guessed the
    # opposite and the app was right).
    "no thanks",
)

#: Sentences that merely CONTAIN such a word, which must stay ordinary chat.
DECISION_NEAR_MISSES = (
    "I approved the plans yesterday",
    "approve the invoice tomorrow",
    "yes but later",
    "reject the draft and rewrite it",
    "not yet",
)


def t_a_typed_decision_answers_where_the_card_is():
    now = time.time()
    sched = _Sched()
    try:
        for text in DECISIONS:
            intent = Q.match(text, now=now)
            check(f"a typed decision is answered without the model: {text!r}",
                  intent is not None and intent.name == "approval_where", intent)
            if intent is None or intent.name != "approval_where":
                continue
            result = Q.run(intent, sched, now)
            check(f"and really answers, no model: {text!r}",
                  result is not None and isinstance(result.reply, str)
                  and bool(result.reply.strip()), result)
            if result is None:
                continue
            reply = result.reply.lower()
            check(f"the answer names the card: {text!r}", "card" in reply, result.reply)
            check(f"and says where it is: {text!r}",
                  "approval window" in reply and "on this pc" in reply, result.reply)
            check(f"and says typing here cannot do it: {text!r}",
                  "cannot approve" in reply, result.reply)
            fields = Q.route_fields(result)
            check(f"the route carries the intent, unchanged: {text!r}",
                  fields.get("quick") == "approval_where", fields)
            check(f"and raises no gate: {text!r}", "gate" not in fields, fields)
        for text in DECISION_NEAR_MISSES:
            intent = Q.match(text, now=now)
            check(f"a sentence that merely contains one goes to the model: {text!r}",
                  intent is None or intent.name != "approval_where", intent)
    finally:
        sched.close()


def t_a_typed_decision_can_never_approve():
    """The reply offers no control, and no code path here can decide a card.

    Rule 4's whole point is that a typed word is not a decision, so the answer
    must carry nothing a client could action: no approve/deny field, no id, and
    no call into the gate from the intent's own branch.
    """
    sched = _Sched()
    try:
        intent = Q.match("approve")
        result = Q.run(intent, sched, time.time())
        fields = Q.route_fields(result)
        for forbidden in ("approved", "approve", "deny", "denied", "decision",
                          "option_id", "always"):
            check(f"the route carries no {forbidden!r} field",
                  forbidden not in fields, sorted(fields))
        # No interactive control in the words themselves.
        check("the answer offers no button or link",
              "[" not in result.reply and "http" not in result.reply, result.reply)
        # The intent's branch calls nothing that could decide anything.
        src = (Path(__file__).resolve().parent / "jarvis_quick.py").read_text(encoding="utf-8")
        start = src.index('if n == "approval_where":')
        branch = src[start:src.index('if n == "open_app":', start)]
        for call in ("gate(", "check(", "decide(", "approve(", "deny(", "_run_gate"):
            check(f"the approval_where branch never calls {call}", call not in branch)
        # And nothing else in the backend answers this intent.
        others = []
        for path in sorted((Path(__file__).resolve().parent).glob("*.py")):
            if path.name in ("jarvis_quick.py", "test_open_chat.py"):
                continue
            if "approval_where" in path.read_text(encoding="utf-8", errors="replace"):
                others.append(path.name)
        check("no other backend module knows this intent", not others, others)
    finally:
        sched.close()



if __name__ == "__main__":
    for fn in (t_every_phrasing_is_answered_with_no_model, t_answer_turn_end_to_end,
               t_route_carries_the_intent_name, t_fixed_line_style,
               t_the_phones_own_list_is_current,
               t_a_typed_decision_answers_where_the_card_is,
               t_a_typed_decision_can_never_approve):
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
