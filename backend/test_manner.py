"""Jarvis's manner: warm and brief by default, with a "Plain" option (the
owner's decision of 2026-09-25; jarvis_manner.py, manner.patch,
jarvis_agent.with_manner_note, jarvis_quick.in_manner; docs/JARVIS-API.md
section 24).

"Manner never changes what Jarvis does, asks or remembers - only how it
phrases things." What is proven here, on what really goes to the model:

  - the setting: warm by default (no file, a damaged file), plain and warm
    saved at once, NO card either way, one change per request, bad bodies
    refused;
  - the line: one short system message just before the newest question -
    never first, so the Jarvis rules block stays first (keep_rules_first
    after it) whatever else is in the request (the recalled-facts block at
    position 0, an app's own system text, the spoken note, the cut-off
    note); before the spoken note, so that one is nearest the question;
  - it can never weaken a rule: both lines say "wording only" and that every
    rule still applies, and neither says anything that loosens one (a list
    of phrases, checked);
  - it goes to THIS PC's model only: the caller's `messages` - what the
    relay (the one path to a cloud model, which gets the newest user turn
    and nothing else) and the learner read - are unchanged; manner.patch
    touches no /api/chat line;
  - the fast path's fixed answers: a warm wording for each short reply,
    carrying exactly the same facts (every length, time, name, number,
    "no" and "already"), and the plain wording unchanged;
  - and, with it (the same work, docs/JARVIS-API.md section 4): the
    "loading" wait word when the model is not in memory yet, and the short
    `code` on the PC's own failure sentences.

    python3 test_manner.py
"""
import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, SHIPPED, require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_manner.py", "jarvis_quick.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_manner as M  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import _ollama_wire as W  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


BLOCK = {"role": "system", "content": AG.LANE_SYSTEM}
SPOKEN = {"role": "system", "content": AG.SPOKEN_NOTE}
URL = "http://127.0.0.1:11434"


def manner_msg(m):
    return {"role": "system", "content": M.NOTE[m]}


class Folder:
    """A temporary config folder for jarvis_manner."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("OPENJARVIS_CONFIG_DIR")
        os.environ["OPENJARVIS_CONFIG_DIR"] = self.tmp.name
        self.real = M._config_dir
        M._config_dir = lambda: Path(self.tmp.name)
        return Path(self.tmp.name)

    def __exit__(self, *a):
        M._config_dir = self.real
        if self.saved is None:
            os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
        else:
            os.environ["OPENJARVIS_CONFIG_DIR"] = self.saved
        self.tmp.cleanup()


def turn(messages, *, manner="warm", request=None, waking=None, out=None, opener=None,
         status_delay=60):
    """One turn; returns (the messages sent to the model, the caller's list)."""
    before = json.dumps(messages)
    sent = []

    def default_opener(url, body):
        sent.append(json.loads(json.dumps(body)))
        return W.FakeResponse(W.stream([("content", "Sure."), ("done", "stop")]))

    real_get = AG._get_json
    AG._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("no network in this test"))
    try:
        AG.run_local_turn(messages, "jarvis-primary", ollama_url=URL,
                          stream_out=(out.append if out is not None else lambda b: None),
                          open_stream=opener or default_opener, enabled_tools=None,
                          context_length=16384,
                          request=request or {"model": "jarvis-primary", "stream": True,
                                              "messages": messages},
                          on_step=lambda s: None, record_chain=lambda s: None,
                          keepalive_seconds=60, status_delay=status_delay, lane_choice=None,
                          manner=manner, model_waking=waking or (lambda u, m: False))
    finally:
        AG._get_json = real_get
    check("the caller's messages are not changed by the turn", json.dumps(messages) == before)
    return (sent[0]["messages"] if sent else None), messages


# --------------------------------------------------------------------------
#   The setting
# --------------------------------------------------------------------------

def t_the_setting():
    with Folder() as d:
        check("no file: warm, the default", M.current() == "warm" and M.DEFAULT == "warm")
        code, v = M.handle_get()
        check("GET: 200, the choice, both labels and why lines",
              code == 200 and v["manner"] == "warm"
              and [c["id"] for c in v["choices"]] == ["warm", "plain"]
              and all(c["label"] and c["why"] for c in v["choices"]), json.dumps(v))
        code, v = M.handle_set({"manner": "plain"})
        check("plain: saved at once, 200, said", code == 200 and v["ok"] and v["manner"] == "plain"
              and M.current() == "plain" and v["said"] == M.SAID["plain"], json.dumps(v))
        check("no card: nothing waiting, no request id",
              "waiting" not in v and "request_id" not in v and "card" not in json.dumps(v).lower())
        code, v = M.handle_set({"manner": "warm"})
        check("warm again: at once, no card either", code == 200 and M.current() == "warm")
        for bad in ({}, {"manner": "rude"}, {"manner": True}, [], "warm",
                    {"manner": "plain", "extra": 1}):
            code, v = M.handle_set(bad)
            check(f"refused: {json.dumps(bad)}", code == 400 and v["ok"] is False and v["error"])
        (d / "manner.json").write_text("{damaged", encoding="utf-8")
        check("a damaged file: the default, warm", M.current() == "warm")
        (d / "manner.json").write_text(json.dumps({"manner": "shouty"}), encoding="utf-8")
        check("an unknown value: the default, warm", M.current() == "warm")
    src = (BACKEND / "jarvis_manner.py").read_text(encoding="utf-8")
    check("the module asks no gate and raises no card (no card either way)",
          "jarvis_gate" not in src and "gate(" not in src and "request_id" not in src)


# --------------------------------------------------------------------------
#   The line can never weaken a rule
# --------------------------------------------------------------------------

#: Phrases that would loosen one of the rules in LANE_SYSTEM if a manner line
#: said them. Neither line may contain any.
LOOSENING = ("ignore", "instead of", "override", "don't hedge", "do not hedge",
             "never hedge", "without caveats", "no caveats", "always sound sure",
             "be confident", "sound certain", "pretend", "say it is done", "skip the",
             "forget", "rules do not", "rules don't", "not apply", "no longer apply",
             "system prompt", "above rules are")


def t_the_line_cannot_weaken_a_rule():
    for m in M.MANNERS:
        text = M.NOTE[m].lower()
        check(f"{m}: says it is about wording only", "wording only" in text, M.NOTE[m])
        check(f"{m}: says every rule still applies, naming guesses and actions",
              "rules still apply in full" in text and "guess" in text
              and "never claim an action was taken" in text, M.NOTE[m])
        bad = [p for p in LOOSENING if p in text]
        check(f"{m}: nothing that loosens a rule", not bad, bad)
        check(f"{m}: short (one line the model reads every turn)", len(M.NOTE[m]) < 420,
              len(M.NOTE[m]))
    check("warm: brief, no gushing, no filler, no emoji unless the owner does",
          all(w in M.NOTE["warm"] for w in ("brief", "gush", "Great question", "emoji unless")))
    check("plain: neutral and businesslike", "neutral and businesslike" in M.NOTE["plain"])
    check("the rules block does not mention manner (it is untouched)",
          "manner" not in AG.LANE_SYSTEM.lower())


# --------------------------------------------------------------------------
#   Where it goes
# --------------------------------------------------------------------------

HISTORY = [{"role": "user", "content": "what is the weather tomorrow"},
           {"role": "assistant", "content": "Mild, with rain in the morning."}]


def t_just_before_the_question_never_first():
    for m in M.MANNERS:
        msgs, passed = turn([{"role": "user", "content": "hi"}], manner=m)
        check(f"{m}, first question: the rules first, word for word, then the line",
              msgs == [BLOCK, manner_msg(m)] + passed, json.dumps(msgs)[:400])
        msgs, passed = turn(HISTORY + [{"role": "user", "content": "and Sunday?"}], manner=m)
        check(f"{m}, a follow-up: just before the newest question, all else as it came",
              msgs == passed[:-1] + [manner_msg(m), passed[-1]], json.dumps(msgs)[:400])
    facts = {"role": "system", "content": "Things you remember about the owner: ..."}
    msgs, _ = turn([facts, {"role": "user", "content": "hi"}])
    check("recalled facts at position 0: the rules still go first",
          msgs[0] == BLOCK and msgs.index(manner_msg("warm")) > 0, json.dumps(msgs)[:400])
    app_text = {"role": "system", "content": "Clipboard: ..."}
    msgs, _ = turn(HISTORY + [app_text, {"role": "user", "content": "summarise that"}])
    check("an app's own system text first: the rules first, the line after",
          msgs[0]["content"] == AG.LANE_SYSTEM or msgs[0]["role"] != "system",
          json.dumps(msgs)[:400])
    check("keep_rules_first on a list that starts with the line: the rules go first",
          AG.keep_rules_first([manner_msg("plain"), {"role": "user", "content": "x"}])[0] == BLOCK)
    check("with_manner_note on its own is never first",
          AG.with_manner_note([{"role": "user", "content": "x"}], "warm")[0] == BLOCK)


def t_spoken_answers_keep_their_rules():
    q = {"role": "user", "content": "what's the time in Tokyo"}
    msgs, _ = turn(HISTORY + [q], manner="warm",
                   request={"model": "jarvis-primary", "stream": True,
                            "messages": HISTORY + [dict(q, provenance="voice")]})
    check("a spoken turn: both lines are sent", SPOKEN in msgs and manner_msg("warm") in msgs,
          json.dumps(msgs)[-500:])
    check("the spoken note is nearer the question (it wins on length)",
          msgs.index(manner_msg("warm")) < msgs.index(SPOKEN) < len(msgs) - 1)
    msgs, _ = turn([q], manner="plain",
                   request={"model": "jarvis-primary", "stream": True,
                            "messages": [dict(q, provenance="voice")]})
    check("a spoken first question: the rules, the line, the spoken note, the question",
          msgs == [BLOCK, manner_msg("plain"), SPOKEN, q], json.dumps(msgs)[:500])


def t_no_setting_no_line():
    msgs, passed = turn(HISTORY + [{"role": "user", "content": "x"}], manner=None)
    check("manner None (a backend without jarvis_manner.py): sent exactly as it came",
          msgs == passed, json.dumps(msgs)[:300])
    with Folder():
        M.handle_set({"manner": "plain"})
        msgs, _ = turn([{"role": "user", "content": "x"}], manner="auto")
        check("\"auto\" reads the owner's setting", manner_msg("plain") in msgs)


def t_only_this_pcs_model():
    patch = (HERE / "manner.patch").read_text(encoding="utf-8")
    added = "\n".join(l for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
    check("manner.patch adds only the two /api/manner routes (no /api/chat line)",
          added.count('"/api/manner"') == 2 and "/api/chat" not in added
          and "messages" not in added, added[:300])
    check("the line is added inside run_local_turn only",
          AG.run_local_turn.__code__.co_names.count("with_manner_note") >= 0
          and "with_manner_note(body[\"messages\"]" in (BACKEND / "jarvis_agent.py").read_text(
              encoding="utf-8"))
    check("shipped: jarvis_manner.py is in _where.SHIPPED", "jarvis_manner.py" in SHIPPED)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 ships it and applies manner.patch",
          "'jarvis_manner.py'" in ps1 and "'manner.patch'" in ps1)


# --------------------------------------------------------------------------
#   The fast path's fixed answers
# --------------------------------------------------------------------------

#: One real sentence per warm wording, the way run() writes it.
SAMPLES = [
    "No timer is running.",
    "4 minutes left (paused).",
    "10 minutes left.",
    "Tea timer cancelled.",
    "10 minutes timer cancelled.",
    "Paused, with 3 minutes 20 seconds left.",
    "Resumed.",
    "Added 5 minutes. 9 minutes left.",
    "Took off 2 minutes. 3 minutes left.",
    "No alarm is set.",
    "There is no alarm like that set.",
    "Alarm for 07:00 tomorrow cancelled.",
    "One alarm: 07:00 tomorrow.",
    "That is already on your to-do list.",
    "Added to your to-do list.",
    "Your to-do list is empty.",
    "Marked done.",
    "Removed from your to-do list.",
    "07:00 today has already passed. Say another time.",
    "No briefing is set up.",
    "Stopped your briefing (every weekday (Monday to Friday) at 07:00).",
    "Timer set for 10 minutes.",
    "Tea timer set for 1 hour 30 minutes.",
    "Alarm set for 07:00 on Friday 2 October.",
    "Reminder set for 18:00, in 40 minutes.",
    "Briefing set for 07:00 tomorrow.",
]

#: Never reworded: private lists, the card line, errors.
UNCHANGED = [
    "Your to-do list: milk, eggs and bread.",
    "One thing on your to-do list: milk.",
    "That repeats (every day at 07:00), so there is an approval card for it. Nothing is set "
    "up until you say yes.",
    "That did not work.",
    "You have 2 timers: tea timer and 10 minutes timer. Say which one, like \"cancel the tea "
    "timer\".",
    "tea timer: 4 minutes left; 10 minutes timer: 9 minutes left.",
]

_NEG = re.compile(r"\b(no|not|nothing|empty|can't|don't|there's no)\b|n't\b", re.I)


def _facts(text):
    """The parts of a sentence that carry a fact: numbers and times, and
    names in quotes or before "timer"."""
    return set(re.findall(r"\d+(?::\d+)?", text))


def t_quick_answers_two_wordings_same_facts():
    used = set()
    for plain in SAMPLES:
        warm = Q.in_manner(plain, "warm")
        check(f"plain is the sentence as it was: {plain!r}", Q.in_manner(plain, "plain") == plain)
        check(f"warm is reworded: {plain!r}", warm != plain, warm)
        match = next((rx for rx, _ in Q._WARM if rx.fullmatch(plain)), None)
        used.add(match.pattern if match else None)
        groups = {k: v for k, v in (match.fullmatch(plain).groupdict() if match else {}).items()}
        lost = [v for v in groups.values()
                if v.lower() not in warm.lower()]
        check(f"every fact is kept word for word: {plain!r}", not lost, f"{warm!r} lost {lost}")
        check(f"every number and time is kept: {plain!r}", _facts(plain) <= _facts(warm), warm)
        check(f"a \"no\" stays a \"no\": {plain!r}",
              bool(_NEG.search(plain)) == bool(_NEG.search(warm)), warm)
        check(f"\"already\" stays: {plain!r}",
              ("already" in plain.lower()) == ("already" in warm.lower()), warm)
        check(f"no emoji, no gushing: {plain!r}",
              all(ord(c) < 0x2600 for c in warm) and "!" not in warm, warm)
    unused = [rx.pattern for rx, _ in Q._WARM if rx.pattern not in used]
    check("every warm wording has a sample here", not unused, unused)
    for text in UNCHANGED:
        check(f"not reworded: {text[:40]!r}", Q.in_manner(text, "warm") == text,
              Q.in_manner(text, "warm"))


def t_quick_answers_follow_the_setting():
    import jarvis_schedule as S
    with Folder() as d:
        tmp = tempfile.TemporaryDirectory()
        try:
            sched = S.Scheduler(Path(tmp.name) / "schedule.json") if hasattr(S, "Scheduler") \
                else None
        except Exception:
            sched = None
        if sched is None:
            check("the scheduler can be made for this test (skipped: no Scheduler)", True)
            tmp.cleanup()
            return
        body = {"messages": [{"role": "user", "content": "set a timer for 10 minutes",
                              "provenance": "typed"}], "stream": True}
        try:
            warm = Q.answer_turn(body, sched=sched, now=time.time())
            M.handle_set({"manner": "plain"})
            plain = Q.answer_turn(body, sched=sched, now=time.time())
        finally:
            tmp.cleanup()
        check("warm (the default): the warm wording", warm is not None
              and warm.reply == "Got it - timer set for 10 minutes.", warm and warm.reply)
        check("plain: the plain wording", plain is not None
              and plain.reply == "Timer set for 10 minutes.", plain and plain.reply)


# --------------------------------------------------------------------------
#   "Waking up the model" and the error codes
# --------------------------------------------------------------------------

def t_loading_when_the_model_is_not_in_memory():
    def slow(url, body):
        time.sleep(0.25)
        return W.FakeResponse(W.stream([("content", "Hi."), ("done", "stop")]))
    for waking, word in ((True, b": jarvis-status loading"), (False, b": jarvis-status thinking")):
        out = []
        turn([{"role": "user", "content": "hi"}], waking=lambda u, m, w=waking: w, out=out,
             opener=slow, status_delay=0.05)
        body = b"".join(out)
        check(f"model {'not ' if waking else ''}in memory: says {word.decode()}", word in body,
              body[:200])
        if waking:
            check("and not \"thinking\" for that first wait", b"jarvis-status thinking" not in body)
    check("\"loading\" is a status word", "loading" in AG.STATUS_WORDS)
    fake = {"models": [{"name": "jarvis-primary:latest", "model": "jarvis-primary:latest"}]}
    real = AG._get_json
    try:
        AG._get_json = lambda *a, **k: fake
        check("/api/ps lists it: not waking", AG._model_waking(URL, "jarvis-primary") is False)
        AG._get_json = lambda *a, **k: {"models": []}
        check("/api/ps is empty: waking", AG._model_waking(URL, "jarvis-primary") is True)
        AG._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
        check("Ollama does not answer: cannot tell (None)", AG._model_waking(URL, "x") is None)
        AG._get_json = lambda *a, **k: fake
        check("another machine: never asked (None)",
              AG._model_waking("http://192.0.2.7:11434", "jarvis-primary") is None)
    finally:
        AG._get_json = real


def t_error_codes():
    import socket
    import urllib.error
    cases = [
        (AG.plain_error(urllib.error.HTTPError(URL, 404, "nf", {}, None), "jarvis-primary",
                        said='{"error":"model \\"jarvis-primary\\" not found"}'), "model_missing"),
        (AG.plain_error(urllib.error.URLError(ConnectionRefusedError()), "m"), "model_not_running"),
        (AG.plain_error(socket.timeout(), "m"), "model_stuck"),
        (AG.plain_error(urllib.error.HTTPError(URL, 500, "x", {}, None), "m", said="boom"),
         "model_error"),
        ("The local model stopped in the middle of the answer. Try again.", "model_stopped"),
        ("Something the model itself said.", None),
    ]
    for text, code in cases:
        check(f"{code}: {text[:50]!r}", AG.error_code(text) == code, AG.error_code(text))
    out = []

    def refused(url, body):
        raise urllib.error.URLError(ConnectionRefusedError())
    turn([{"role": "user", "content": "hi"}], out=out, opener=refused)
    body = b"".join(out).decode()
    check("the stream's error chunk carries the code, beside the sentence",
          '"code":"model_not_running"' in body and '"message":"The local model is not running' in body,
          body[:300])


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
