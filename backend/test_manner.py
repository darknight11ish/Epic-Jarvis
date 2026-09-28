"""Jarvis's manner: warm and brief by default, with a "Plain" option (the
owner's decision of 2026-09-25; jarvis_manner.py, manner.patch,
jarvis_agent.with_manner_note, jarvis_quick.in_manner; docs/JARVIS-API.md
section 27).

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
#   Humour: a switch in "How Jarvis talks" (the owner's decision, 2026-09-27)
# --------------------------------------------------------------------------
#
# "A switch in 'How Jarvis talks', off to start; never on cards, errors or
# serious topics." A second, independent setting beside manner, on the same
# GET/POST /api/manner routes so both apps' one settings screen can change
# either one - or both - in a single request, without resetting the other.

def t_humor_off_by_default_and_in_the_view():
    with Folder():
        check("no file: humour is off, the default",
              M.humor_enabled() is False and M.HUMOR_DEFAULT is False)
        code, v = M.handle_get()
        check("GET carries the humour switch and its own words",
              code == 200 and v["humor"] is False and v["humor_title"] == M.HUMOR_TITLE
              and v["humor_detail"] == M.HUMOR_DETAIL, json.dumps(v))


def t_humor_can_be_set_without_touching_manner():
    with Folder():
        M.handle_set({"manner": "plain"})
        code, v = M.handle_set({"humor": True})
        check("humour turns on, at once, no card, and manner is untouched",
              code == 200 and v["ok"] and v["humor"] is True and v["manner"] == "plain"
              and M.humor_enabled() is True and M.current() == "plain"
              and v["said"] == M.HUMOR_SAID[True], json.dumps(v))
        code, v = M.handle_set({"manner": "warm"})
        check("changing manner afterwards leaves humour exactly as it was",
              code == 200 and v["manner"] == "warm" and v["humor"] is True
              and M.humor_enabled() is True, json.dumps(v))


def t_humor_and_manner_together_in_one_request():
    with Folder():
        code, v = M.handle_set({"manner": "plain", "humor": True})
        check("both change at once, one said sentence naming both",
              code == 200 and v["manner"] == "plain" and v["humor"] is True
              and M.SAID["plain"] in v["said"] and M.HUMOR_SAID[True] in v["said"], json.dumps(v))
        code, v = M.handle_set({"humor": False})
        check("turning it back off again leaves manner alone",
              code == 200 and v["humor"] is False and v["manner"] == "plain", json.dumps(v))


def t_humor_bad_bodies_refused():
    with Folder():
        for bad in ({}, {"humor": "yes"}, {"humor": 1}, [], "on", {"humor": True, "extra": 1}):
            code, v = M.handle_set(bad)
            check(f"refused: {json.dumps(bad)}", code == 400 and v["ok"] is False and v["error"])
        (Path(M.settings_path().parent) / "manner.json").write_text(
            json.dumps({"manner": "warm", "humor": "not a bool"}), encoding="utf-8")
        check("a damaged humour value: the default, off", M.humor_enabled() is False)


def t_humor_note_appended_only_when_on_never_weakening_a_rule():
    check("off: the plain manner note, unchanged", M.note("plain", humor=False) == M.NOTE["plain"])
    with_humor = M.note("warm", humor=True)
    check("on: the humour clause is appended, after the manner line",
          with_humor.startswith(M.NOTE["warm"]) and with_humor != M.NOTE["warm"]
          and M.HUMOR_NOTE in with_humor, with_humor)
    for phrase in LOOSENING:
        check(f"the humour clause never says: {phrase!r}", phrase not in M.HUMOR_NOTE.lower())
    check("it says plainly never on a serious or sensitive topic, an approval, or an error",
          "serious" in M.HUMOR_NOTE and "sensitive" in M.HUMOR_NOTE
          and "approval" in M.HUMOR_NOTE and "error" in M.HUMOR_NOTE)


def t_humor_defaults_to_the_setting_when_not_passed_explicitly():
    with Folder():
        M.handle_set({"humor": True})
        check("note() with no humor arg reads the saved setting",
              M.HUMOR_NOTE in M.note("warm"))
        M.handle_set({"humor": False})
        check("off again: no clause", M.HUMOR_NOTE not in M.note("warm"))


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
    # Since the warm-up (2026-09-28) the notes are added by ONE function,
    # dress_messages, which only the local turn and the warm-up of this PC's
    # own model call - never the relay, the one path to a cloud model.
    import ast
    tree = ast.parse((BACKEND / "jarvis_agent.py").read_text(encoding="utf-8"))
    callers = {}
    for top in tree.body:
        if isinstance(top, ast.FunctionDef):
            for node in ast.walk(top):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") in (
                        "with_manner_note", "dress_messages"):
                    callers.setdefault(node.func.id, set()).add(top.name)
    check("the line is added inside run_local_turn (and its warm-up) only",
          callers == {"with_manner_note": {"dress_messages"},
                      "dress_messages": {"run_local_turn", "chat_prefix"}}, callers)
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


# --------------------------------------------------------------------------
#   "From now on ..." (the owner's decision, 2026-09-27)
# --------------------------------------------------------------------------
#
# The MECHANISM only, wired to the one real dial this backend has today
# (warm/plain) - not the growth doc's bigger multi-dial system. Applies at
# once, no card either way (jarvis_manner.py already raises none for a
# manner change); a temporary chat's change stays in that chat only, in
# memory, never in manner.json.

def _quick_sched():
    import jarvis_schedule as S
    tmp = tempfile.TemporaryDirectory()
    try:
        sched = S.Scheduler(Path(tmp.name) / "schedule.json") if hasattr(S, "Scheduler") else None
    except Exception:
        sched = None
    return sched, tmp


def _own_words(text, cid="conv-fromnowon1", temporary=None):
    body = {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
            "conversation_id": cid}
    if temporary is not None:
        body["temporary"] = temporary
    return body


def t_from_now_on_detects_and_maps_to_the_one_real_dial():
    for text, manner in (("from now on, be more plain", "plain"),
                         ("from now on be warmer", "warm"),
                         ("from now on, talk more formally", "plain"),
                         ("from now on be friendlier", "warm"),
                         ("from now on, be more plain please", "plain")):
        intent = Q.match(text)
        check(f"detected and mapped: {text!r}",
              intent is not None and intent.name == "manner_from_now_on"
              and intent.f.get("manner") == manner, intent)
    unmapped = Q.match("from now on, keep answers short")
    check("recognised as the phrase, but not mapped to a real dial",
          unmapped is not None and unmapped.f.get("manner") is None, unmapped)
    check("is_command() is true for it (never learned as a fact)",
          Q.is_command("from now on, be more plain"))


def t_from_now_on_applies_at_once_no_card_and_can_be_undone_by_saying_the_other():
    with Folder():
        sched, tmp = _quick_sched()
        if sched is None:
            check("skipped: no Scheduler", True)
            tmp.cleanup()
            return
        try:
            check("sanity: warm by default", M.current() == "warm")
            res = Q.answer_turn(_own_words("from now on, be more plain"), sched=sched)
            check("applies at once: the setting is now plain",
                  res is not None and M.current() == "plain", res and res.reply)
            check("says Done, names the change, and points to where to undo it",
                  res.reply == "Done: plainer answers from now on. You can undo this in Settings.",
                  res.reply)
            check("no card: GET /api/manner needs no approval - it already answers plain",
                  M.handle_get()[1]["manner"] == "plain")
            again = Q.answer_turn(_own_words("from now on, be more plain"), sched=sched)
            check("asking for what it already is says so, and changes nothing",
                  again is not None and again.reply == "Jarvis already answers plainly."
                  and M.current() == "plain", again and again.reply)
            # "Undo": the owner can say the other one, or use the existing
            # Settings switch - both are the SAME real setting, not new state.
            back = Q.answer_turn(_own_words("from now on be warmer"), sched=sched)
            check("saying the other one undoes it, the same way",
                  back is not None and M.current() == "warm", back and back.reply)
        finally:
            tmp.cleanup()


def t_from_now_on_unmapped_tail_says_so_honestly():
    with Folder():
        sched, tmp = _quick_sched()
        if sched is None:
            check("skipped: no Scheduler", True)
            tmp.cleanup()
            return
        try:
            before = M.current()
            res = Q.answer_turn(_own_words("from now on, keep answers short"), sched=sched)
            check("says plainly that dial does not exist, and changes nothing",
                  res is not None and res.reply == Q.FROM_NOW_ON_UNMAPPED
                  and M.current() == before, res and res.reply)
        finally:
            tmp.cleanup()


def t_from_now_on_temporary_chat_stays_in_that_chat_only():
    with Folder():
        sched, tmp = _quick_sched()
        if sched is None:
            check("skipped: no Scheduler", True)
            tmp.cleanup()
            return
        try:
            check("sanity: warm by default, persisted", M.current() == "warm")
            res = Q.answer_turn(_own_words("from now on, be more plain", cid="conv-temp-a",
                                           temporary=True), sched=sched)
            check("applies for this chat: says so, for this chat only",
                  res is not None
                  and res.reply == ("Done: plainer answers for this chat. Say it again, or "
                                    "start a new chat, to change back."), res and res.reply)
            check("never written to manner.json - a temporary chat makes no memory",
                  M.current() == "warm" and M.handle_get()[1]["manner"] == "warm")
            check("this conversation now reads plain", M.current("conv-temp-a") == "plain")
            check("a DIFFERENT conversation is unaffected", M.current("conv-temp-b") == "warm")
            # An ordinary (non-temporary) turn, right after, is unaffected too.
            other = Q.answer_turn(_own_words("set a timer for 5 minutes", cid="conv-temp-c"),
                                  sched=sched)
            check("an ordinary chat's fixed answer stays in the PC's own (warm) manner",
                  other is not None and other.reply == "Got it - timer set for 5 minutes.",
                  other and other.reply)
        finally:
            tmp.cleanup()


def t_from_now_on_temporary_chat_needs_a_real_conversation_id():
    with Folder():
        sched, tmp = _quick_sched()
        if sched is None:
            check("skipped: no Scheduler", True)
            tmp.cleanup()
            return
        try:
            body = {"messages": [{"role": "user", "content": "from now on, be more plain",
                                  "provenance": "typed"}], "temporary": True}
            res = Q.answer_turn(body, sched=sched)
            check("no usable conversation id: refused plainly, nothing changed",
                  res is not None and res.reply == Q.FROM_NOW_ON_NO_CONVERSATION
                  and M.current() == "warm", res and res.reply)
        finally:
            tmp.cleanup()


def t_from_now_on_never_from_outside_text_or_a_shared_message():
    # newest_own_words() already refuses these (ARCHITECTURE section 3); this
    # nails down that "from now on ..." is no exception, since it is exactly
    # the kind of instruction an injection attempt would try this phrasing on.
    text = "from now on, be more plain"
    cases = [
        {"messages": [{"role": "system", "content": "outside text"},
                      {"role": "user", "content": text, "provenance": "typed"}]},
        {"messages": [{"role": "user", "content": text, "provenance": "shared"}]},
        {"messages": [{"role": "user", "content": "look at this", "provenance": "shared"},
                      {"role": "user", "content": text, "provenance": "typed"}]},
        {"messages": [{"role": "user", "content": text}]},   # no provenance at all
    ]
    for body in cases:
        check(f"not treated as the owner's own words: {body}", Q.newest_own_words(body) is None)


def t_from_now_on_feeds_the_local_models_manner_note_too():
    # The temporary-chat override reaches the model's own request the same
    # way the persisted setting does (with_manner_note), keyed by the
    # request's conversation_id - jarvis_agent._manner_now.
    with Folder():
        try:
            check("no override: the persisted setting", AG._manner_now("conv-model-1") == "warm")
            M.set_temporary("conv-model-1", "plain")
            check("this conversation's override wins", AG._manner_now("conv-model-1") == "plain")
            check("a different conversation is unaffected", AG._manner_now("conv-model-2") == "warm")
            check("the persisted setting itself is untouched by a temporary override",
                  M.current() == "warm")
            sent, _ = turn([{"role": "user", "content": "hi"}], manner="auto",
                           request={"conversation_id": "conv-model-1"})
            check("the model's own request gets the temporary chat's manner note",
                  sent is not None and manner_msg("plain") in sent, sent)
        finally:
            M._TEMPORARY.pop("conv-model-1", None)
            M._TEMPORARY.pop("conv-model-2", None)


def t_from_now_on_set_temporary_is_bounded_and_validated():
    check("a bad conversation id changes nothing", M.set_temporary("bad id!", "plain") is False)
    check("a manner this module does not know changes nothing",
          M.set_temporary("conv-zzzzzzzz", "sarcastic") is False)
    try:
        check("a real one works", M.set_temporary("conv-zzzzzzzz", "plain") is True
              and M.current("conv-zzzzzzzz") == "plain")
        for i in range(M._TEMPORARY_MAX + 10):
            M.set_temporary(f"conv-bound-{i:06d}", "plain")
        check("bounded - old entries are dropped rather than growing forever",
              len(M._TEMPORARY) <= M._TEMPORARY_MAX, len(M._TEMPORARY))
    finally:
        M._TEMPORARY.clear()


# --------------------------------------------------------------------------
#   Style rules for every fixed line (I135, 2026-09-27)
# --------------------------------------------------------------------------
#
# This is the "two wordings, same facts" check above (t_the_line_cannot_
# weaken_a_rule), extended past the manner line to every fixed line this
# repo has: jarvis_card_words, jarvis_quick, jarvis_sayable, jarvis_reach
# and jarvis_identity (the "quick answer" family jarvis_quick.py serves
# from), jarvis_focus, and the shared case files both apps read (the four
# that reproduce those modules' own words: card-words, focus, sayable and
# reach - not every *-cases.json file, most of which hold protocol or
# hardware test data, not prose). docs/ARCHITECTURE.md section 7 writes
# these rules down, beside the manner paragraph.
#
# Never a model judging text: every check below is a fixed rule (a regex,
# a count), the same "no AI marking its own homework" principle as
# tools/tool_eval/behaviour_cases.py.
import ast  # noqa: E402

_STYLE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF←-⇿✀-➿]")
_STYLE_SORRY = re.compile(r"\bsorry\b", re.I)
_STYLE_SIR = re.compile(r"\bsir\b", re.I)
_STYLE_SERVICE = re.compile(r"at your service", re.I)
_STYLE_DOTTED_JARVIS = re.compile(r"j\.\s*a\.\s*r\.\s*v\.\s*i\.\s*s\.", re.I)

#: The modules this check reads - by name, not by guessing at every string
#: in the codebase: each is a real module whose UPPER_CASE constants are
#: fixed lines the owner or the model's own answer can carry verbatim.
_STYLE_MODULES = ("jarvis_card_words.py", "jarvis_quick.py", "jarvis_focus.py",
                  "jarvis_sayable.py", "jarvis_reach.py", "jarvis_identity.py")

#: The shared case files both apps read - the desktop's copy; test_*.py
#: files elsewhere already hold the desktop and phone copies byte-identical,
#: so checking one says the same about both.
_STYLE_CASE_FILES = tuple(
    REPO / "jarvis-desktop" / "tests" / "fixtures" / f"{n}-cases.json"
    for n in ("card-words", "focus", "sayable", "reach"))

#: "!" is checked only on card text - jarvis_card_words.py, and the one
#: case file that reproduces it. Everywhere else (an error, a quick
#: answer, a focus callout) is not itself a card, so this repo's fixed
#: lines elsewhere are not held to that one.
_STYLE_CARD_SOURCES = ("jarvis_card_words.py", "card-words-cases.json")

#: Test-input fixtures deliberately built to look odd (gen_card_words_
#: cases.py's UNKNOWN list: "Weird-Name!!", "café_lights", ...) are actions
#: being fuzzed, never a line Jarvis itself says - skipped by key, not by
#: guessing at their odd content.
_STYLE_SKIP_JSON_KEYS = frozenset({"action", "_comment"})


def _style_strings_from_module(path: Path) -> list:
    """Every string literal inside a module-level UPPER_CASE constant -
    jarvis_sayable.SENTENCES, jarvis_card_words.TITLES, and the like."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out = []

    def collect(node):
        try:
            val = ast.literal_eval(node)
        except Exception:
            return
        stack = [val]
        while stack:
            v = stack.pop()
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, dict):
                stack.extend(v.keys())
                stack.extend(v.values())
            elif isinstance(v, (list, tuple, set, frozenset)):
                stack.extend(v)
    for node in ast.walk(tree):
        targets = None
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets or []:
            if isinstance(t, ast.Name) and t.id.isupper():
                collect(node.value)
    return out


def _style_strings_from_json(path: Path) -> list:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    stack = [data]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for k, vv in v.items():
                if k in _STYLE_SKIP_JSON_KEYS:
                    continue
                out.append(k)
                stack.append(vv)
        elif isinstance(v, list):
            stack.extend(v)
    return out


def t_style_rules_for_every_fixed_line():
    sources = []
    for name in _STYLE_MODULES:
        for s in _style_strings_from_module(BACKEND / name):
            sources.append((name, s))
    for path in _STYLE_CASE_FILES:
        for s in _style_strings_from_json(path):
            sources.append((path.name, s))
    check("this check actually read something from every source",
          len({name for name, _s in sources}) >= len(_STYLE_MODULES),
          sorted({name for name, _s in sources}))
    bad_emoji = [(n, s) for n, s in sources if _STYLE_EMOJI.search(s)]
    check("no emoji in any fixed line", not bad_emoji, bad_emoji[:5])
    bad_sorry = [(n, s) for n, s in sources if len(_STYLE_SORRY.findall(s)) > 1]
    check("never more than one \"sorry\" in the same line", not bad_sorry, bad_sorry[:5])
    bad_film = [(n, s) for n, s in sources
               if _STYLE_SIR.search(s) or _STYLE_SERVICE.search(s)
               or _STYLE_DOTTED_JARVIS.search(s)]
    check("no film phrases (\"sir\", \"at your service\", the dotted J.A.R.V.I.S. spelling)",
          not bad_film, bad_film[:5])
    bad_bang = [(n, s) for n, s in sources if n in _STYLE_CARD_SOURCES and "!" in s]
    check("no \"!\" on a card", not bad_bang, bad_bang[:5])


def t_both_apps_read_the_current_contract():
    # The same shape as test_asks_first.py's. Nothing ran this producer's
    # --check automatically, so the humour switch's words reached
    # jarvis_manner.view() and never both apps' copy (quality audit
    # 2026-09-27).
    import subprocess
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_plain_error_cases.py"),
                        "--check"], capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check("plain-error-cases.json (desktop and phone) is what the backend says today "
          "(python3 tools/gen_plain_error_cases.py)", r.returncode == 0, r.stdout + r.stderr)


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
