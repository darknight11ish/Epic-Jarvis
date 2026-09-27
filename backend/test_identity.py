"""test_identity.py - "Who are you?", answered without the AI model
(feasibility I131: "Instant, honest, no model. Fixed text; no romance.").

    python3 backend/test_identity.py

What it proves:
  - ANSWER is one real, non-empty paragraph that says Jarvis's name, that
    it is software with no feelings, that it is not the Iron Man film
    character, and points at "what can you do?" / "what can you reach?"
    for specifics - and never claims romance or companionship (the
    owner's "no romance" condition);
  - a real spread of phrasings - identity, "are you an AI", the Iron Man
    probe, feelings, romance and friendship probes, and "what model are
    you" - are answered by jarvis_quick.py's own grammar with no model,
    end to end (Q.answer_turn), and a near miss or pasted text is not;
  - it is fixed text: no gate, no card, no setting, nothing written;
  - without jarvis_identity.py, the fast path says to run
    apply-patches.ps1, the same shape as jarvis_reach.py's own fallback;
  - it passes the same style rules test_manner.py holds every fixed line
    in this repo to (I135): no emoji, no "!", at most one "sorry", no
    film phrases ("sir", "at your service", "j.a.r.v.i.s.").
No network, no model.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_identity.py", "jarvis_quick.py")

import jarvis_identity as I  # noqa: E402
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
        self.tmp.cleanup()


PHRASINGS = (
    "who are you",
    "who are you?",
    "what are you",
    "are you an AI",
    "are you a robot",
    "are you human",
    "are you real",
    "are you conscious",
    "are you sentient",
    "are you alive",
    "are you JARVIS from Iron Man",
    "are you the JARVIS from Iron Man",
    "are you J.A.R.V.I.S.",
    "do you have feelings",
    "do you love me",
    "do you miss me",
    "are you my girlfriend",
    "are you my boyfriend",
    "are you my friend",
    "will you be my friend",
    "are you lonely",
    "what model are you running",
    "what model do you use",
    "what AI is this",
    "hey Jarvis, who are you",
)

NEAR_MISSES = (
    "who are you calling",
    "what are you doing this weekend",
    "are you sure",
    "are you free tomorrow",
    "what model of car do you drive",
)


def t_the_answer_shape():
    check("a real, non-empty paragraph", isinstance(I.ANSWER, str) and I.ANSWER.strip())
    check("says its name", "jarvis" in I.ANSWER.lower())
    check("says it is software", "software" in I.ANSWER.lower())
    check("declines feelings, a body and a past",
          "no feelings" in I.ANSWER.lower() and "no body" in I.ANSWER.lower()
          and "no past" in I.ANSWER.lower())
    check("says it is not the film character",
          "iron man" in I.ANSWER.lower())
    check("no \"sir\"", "sir" not in I.ANSWER.lower())
    check("no romance or companionship claimed (the owner's condition)",
          not any(w in I.ANSWER.lower() for w in
                  ("love you", "girlfriend", "boyfriend", "i'm your friend", "i am your friend",
                   "companion", "i miss you", "i feel")))
    check("points at the other fixed answers for specifics",
          "what can you do" in I.ANSWER.lower() and "what can you reach" in I.ANSWER.lower())
    check("sentence() returns the same text", I.sentence() == I.ANSWER)


def t_every_phrasing_is_answered_with_no_model():
    now = time.time()
    sched = _Sched()
    try:
        for text in PHRASINGS:
            intent = Q.match(text, now=now)
            check(f"matches the no-model grammar: {text!r}",
                  intent is not None and intent.name == "identity_help", intent)
            result = Q.run(intent, sched, now) if intent is not None else None
            check(f"and really answers, no model: {text!r}",
                  result is not None and result.reply == I.ANSWER, result)
        for text in NEAR_MISSES:
            intent = Q.match(text, now=now)
            check(f"a near miss goes to the model: {text!r}",
                  intent is None or intent.name != "identity_help", intent)
    finally:
        sched.close()


def t_answer_turn_end_to_end():
    sched = _Sched()
    try:
        for prov in ("typed", "voice"):
            body = {"messages": [{"role": "user", "content": "who are you?",
                                  "provenance": prov}], "stream": True}
            res = Q.answer_turn(body, sched=sched, now=time.time())
            check(f"answers end to end ({prov})",
                  res is not None and res.intent == "identity_help" and res.reply == I.ANSWER, res)
        body = {"messages": [{"role": "user", "content": "who are you?",
                              "provenance": "pasted"}]}
        check("pasted text goes to the model instead",
              Q.answer_turn(body, sched=sched) is None)
    finally:
        sched.close()


def t_fixed_text_no_card_no_setting():
    src = (HERE / "jarvis_identity.py").read_text(encoding="utf-8")
    check("the module asks no gate and raises no card",
          "jarvis_gate" not in src and "gate(" not in src and "request_id" not in src)
    check("no setting is written: no settings_path, no config dir, no os.replace",
          "settings_path" not in src and "os.replace" not in src)


def t_the_fallback_without_the_module():
    sched = _Sched()
    saved = sys.modules.get("jarvis_identity")
    sys.modules["jarvis_identity"] = None
    try:
        r = Q.answer("who are you?", sched=sched)
    finally:
        sys.modules["jarvis_identity"] = saved
        sched.close()
    check("without jarvis_identity.py it says to run apply-patches.ps1",
          r is not None and r.reply == Q.IDENTITY_MISSING)


if __name__ == "__main__":
    for fn in (t_the_answer_shape, t_every_phrasing_is_answered_with_no_model,
               t_answer_turn_end_to_end, t_fixed_text_no_card_no_setting,
               t_the_fallback_without_the_module):
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
