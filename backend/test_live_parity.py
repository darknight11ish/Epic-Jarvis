"""test_live_parity.py - a Live turn can do what a typed chat turn can.

    python -B backend/run_suites.py test_live_parity.py

THE OWNER'S REQUEST (2026-11-01, verbatim): "also, id like javis live to be
able to reasonably do anything that jarvis can do through chat."

WHAT WAS WRONG, measured on 1861485da before this branch (the numbers are in
docs/LIVE-DESIGN.md 4.1 and in the pull request): a Live turn was shown at most
six tools, and the cap even cut the diet's FULL-LIST fallback. A typed question
the tool diet did not recognise was shown all 32 tools; the same words said in
Live were shown 6 - `notes_search`, `append_obsidian_daily`, `set_timer`,
`set_reminder`, `todo_add`, `change_setting`, `send_email` and 19 more were
never in front of the model. The model cannot call a tool it is not shown, so a
spoken request could not reach most of what Jarvis can do. The per-conversation
carried tool list was capped one smaller than typed chat's for the same reason.

WHAT IS TRUE NOW: a Live turn is shown exactly the tools a typed turn is shown
for the same words - same diet, same full-list fallback, same carried list -
because jarvis_live.LIVE_TOOL_FLOOR is typed chat's own TOOL_DIET_LIMIT and the
Live-only trim is gone from jarvis_agent._fill_offer. Live keeps its DELIBERATE
differences: its own `[live]` model/lane and 16K context (speed), the Live note
(short spoken answers, side talk), a card that pauses the session, and no way
to approve anything by voice. Cards are raised by the same gate, through the
same one action, and nothing runs before a person answers.

WHAT THIS SUITE PROVES, headless (fake model, stub tool, stub gate):

  1. THE TOOL LIST: for six kinds of question - unrecognised, recognised,
     many-matched and multi-step - Live is shown the SAME names as typed chat,
     including the two cases that used to lose 26 and 23 tools.
  2. THE FLOOR: a configured `[live] tool_limit` below typed chat's size cannot
     lower it; one above may raise it.
  3. THE CARRIED LIST: two turns of one Live conversation carry the same names
     as the same two typed turns.
  4. THE TURN: a Live turn whose question asks for a real action reaches the
     tool path, raises ONE card under the tool's own action, and nothing runs
     before the answer; with a person's yes the same path runs it once.
  5. THE PROMPT: the Live note is the only difference in what the model is
     sent - the tool array is identical.
  6. THE MARKS: the server reads the shape both apps send (`live: true` AND
     `provenance: "voice"`), and a live mark without the spoken provenance is
     not a Live turn.
  7. SAME PC-STATE ANSWER: the deterministic fast path (jarvis_quick) answers a
     PC question identically with and without the Live marks.
  8. THE DELIBERATE RULES: no voice-approval surface in jarvis_live, the card
     pause is still the card pause, and the Live note still carries the
     side-talk marker.

WHAT IT DOES NOT PROVE: a real model choosing a tool, a real phone, a real Live
session, or the audio path. Those are owner-tested and stay NOT-TESTABLE here.
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_live.py", "jarvis_live_turn.py",
                "jarvis_quick.py")

TMP = Path(tempfile.mkdtemp(prefix=".jarvis-live-parity-", dir=str(Path.home())))
for _d in ("config", "logs", "home"):
    (TMP / _d).mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")
os.environ.pop("JARVIS_CONFIG_DIR", None)
os.environ.pop("JARVIS_BACKEND", None)

import jarvis_agent as A  # noqa: E402
import jarvis_live as L  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"SKIP {why}")


def fresh():
    import shutil
    for d in ("config", "logs", "home"):
        shutil.rmtree(TMP / d, ignore_errors=True)
        (TMP / d).mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ helpers --

def shown(limit, question, conversation_id=None):
    """The tool names one turn would show, for these words and this limit."""
    names = A.offered_tools(list(A.TOOLS))
    offer = A._new_offer(names, limit=limit)
    A._fill_offer(offer, names, question=question, conversation_id=conversation_id)
    return list(offer["shown"])


QUESTIONS = (
    ("unrecognised", "book a table for two at the italian place"),
    ("recognised: email", "email Sam that I am running late"),
    ("recognised: note", "add this to my obsidian daily note: buy milk"),
    ("recognised: reminder", "remind me to call the dentist tomorrow at nine"),
    ("many matches", "email my notes calendar and reminder about the timer, "
                     "search the web, read the file, switch the light, "
                     "check my spending, connect the account"),
    ("multi-step", "check my email and calendar, then remind me and add a note"),
)


class Verdict:
    def __init__(self, allowed, outcome):
        self.allowed, self.outcome, self.tier = allowed, outcome, "ask"
        self.reason, self.action, self.request_id = "", "", None


def _one_turn(*, live: bool, approve: bool = False):
    """One whole turn whose fake model asks to click Export, then answers.

    The tool is `control_computer` with a stub body, so the turn takes the
    real check/prepare/gate path and the real ONE-card route, and the only
    thing replaced is the click itself. Returns what the gate was asked, what
    ran, the payloads the model was sent, and the turn summary.
    """
    calls, ran, steps, sent, made = [], [], [], [], {}

    def prepare(args):
        return None, 'Plan: click "Export" in Notepad.'

    def execute(args, state, **kw):
        ran.append(True)
        return {"ok": True}

    stub = A.Tool(
        "control_computer", "click a named control (stub)",
        {"type": "object", "properties": {
            "goal": {"type": "string"}, "window": {"type": "string"},
            "requests": {"type": "array", "items": {"type": "object"}}},
         "required": ["goal", "window", "requests"]},
        prepare=prepare, execute=execute,
        gate_lookup_name=lambda args: "jarvis_ui_control_run")
    real_tool = A.TOOLS.get("control_computer")
    A.TOOLS["control_computer"] = stub

    def checking(action, detail, prompt):
        calls.append((action, detail, prompt))
        return Verdict(bool(approve), "approved" if approve else "denied")

    tc = [{"id": "c0", "function": {"name": "control_computer", "arguments": json.dumps({
        "goal": "click Export", "window": "Notepad",
        "requests": [{"control": "Export", "action": "click",
                      "why": "the owner asked"}]})}}]
    replies = iter([{"choices": [{"message": {"role": "assistant", "tool_calls": tc}}]},
                    {"choices": [{"message": {"role": "assistant", "content": "done"}}]}])

    def post(url, payload):
        sent.append(payload)
        made.setdefault("tools", [t["function"]["name"] for t in (payload.get("tools") or [])])
        made.setdefault("system", [m.get("content", "") for m in (payload.get("messages") or [])
                                   if m.get("role") == "system"])
        return next(replies)

    msg = {"role": "user", "content": "click Export in Notepad", "provenance": "voice"}
    if live:
        msg["live"] = True
    request = {"messages": [msg],
               "conversation_id": "live-parity-live" if live else "live-parity-typed"}
    saved = (A._conversation_tainted, A._tier_of)
    A._conversation_tainted = lambda cid, messages=None: False
    A._tier_of = lambda a: "ask"
    try:
        summary = A.run_local_turn(
            [{"role": "user", "content": "click Export in Notepad"}], "m",
            ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None, post=post,
            gate_check=checking, enabled_tools={"control_computer"},
            record_chain=lambda s: None, on_step=steps.append, context_length=16384,
            request=request)
    finally:
        A._conversation_tainted, A._tier_of = saved
        if real_tool is not None:
            A.TOOLS["control_computer"] = real_tool
    return {"calls": calls, "ran": ran, "steps": steps, "summary": summary,
            "tools": made.get("tools") or [], "system": made.get("system") or []}


# ------------------------------------------------------------- 1. the tools --

def t_live_is_shown_exactly_what_typed_chat_is_shown():
    """The measured defect: 32 -> 6 tools for words the diet did not recognise.

    Every pair here must be the SAME list, not merely an overlapping one: a
    tool the model is not shown is a tool it does not call.
    """
    for label, question in QUESTIONS:
        typed = shown(None, question)
        live = shown(L.live_tool_limit(), question)
        check(f"a Live turn is shown the same tools as typed chat: {label}",
              live == typed, {"typed": typed, "live": live})
    typed = shown(None, "book a table for two at the italian place")
    floor = getattr(L, "LIVE_TOOL_FLOOR", 0)
    check("...and that is more than six: the fallback is no longer cut",
          len(typed) > floor and
          len(shown(L.live_tool_limit(),
                    "book a table for two at the italian place")) == len(typed),
          (len(typed), floor))


def t_the_live_tool_limit_is_a_floor_not_a_cut():
    check("Live's floor is typed chat's own diet size",
          getattr(L, "LIVE_TOOL_FLOOR", 0) == A.TOOL_DIET_LIMIT,
          (getattr(L, "LIVE_TOOL_FLOOR", None), A.TOOL_DIET_LIMIT))
    saved = L._live_int
    try:
        L._live_int = lambda key, default, lo, hi: 3
        check("a configured 3 cannot make Live show fewer tools than typed chat",
              L.live_tool_limit() == A.TOOL_DIET_LIMIT, L.live_tool_limit())
        L._live_int = lambda key, default, lo, hi: 12
        check("a configured 12 may show more than typed chat",
              L.live_tool_limit() == 12, L.live_tool_limit())
    finally:
        L._live_int = saved
    ov = L.turn_overrides("typed:8b", "http://127.0.0.1:11434", 196608)
    check("a Live turn still caps the context at [live] context_tokens",
          ov["context_length"] == 16384, ov)
    check("...and reports a tool limit no smaller than typed chat's",
          ov["tool_limit"] >= A.TOOL_DIET_LIMIT, ov)


def t_the_carried_tool_list_is_the_same_size():
    """The KV-prefix carried list: a Live chat must not carry one fewer."""
    def two_turns(limit, conv):
        A.reset_sticky_tools()
        first = shown(limit, "email Sam that I am late", conv)
        second = shown(limit, "what is the weather like", conv)
        A.reset_sticky_tools()
        return first, second
    typed = two_turns(None, "carry-typed")
    live = two_turns(L.live_tool_limit(), "carry-live")
    check("two turns of a Live conversation carry the same tools as two typed turns",
          live == typed, {"typed": typed, "live": live})


# -------------------------------------------------------------- 2. the turn --

def t_a_live_turn_raises_the_same_card_and_runs_nothing_first():
    fresh()
    typed = _one_turn(live=False)
    live = _one_turn(live=True)
    for label, out in (("typed", typed), ("Live", live)):
        check(f"a {label} turn that asks to click Export raises exactly ONE card",
              len(out["calls"]) == 1, out["calls"])
        check(f"...under the tool's own existing action, not a new one: {label}",
              out["calls"] and out["calls"][0][0] in
              ("control_computer", "jarvis_ui_control_run"),
              out["calls"][0][0] if out["calls"] else None)
        check(f"...and NOTHING ran before a person answered: {label}",
              out["ran"] == [], (out["ran"], out["steps"]))
        check(f"...the model is told it was refused, in words: {label}",
              "refused" in (out["summary"].get("answer") or "").lower()
              or "nothing was actually done" in (out["summary"].get("answer") or "").lower(),
              out["summary"].get("answer"))
    check("the Live turn takes the same card route as the typed one",
          [c[0] for c in live["calls"]] == [c[0] for c in typed["calls"]],
          ([c[0] for c in live["calls"]], [c[0] for c in typed["calls"]]))


def t_with_a_persons_yes_the_same_path_runs_it_once():
    fresh()
    live = _one_turn(live=True, approve=True)
    check("with a person's yes a Live turn runs the approved action once",
          live["calls"] and live["ran"] == [True] and len(live["calls"]) == 1,
          (live["calls"], live["ran"]))
    check("...and it still raised the card first (one card, never zero)",
          len(live["calls"]) == 1, live["calls"])


def t_the_live_note_is_the_only_difference_in_the_prompt():
    fresh()
    typed = _one_turn(live=False)
    live = _one_turn(live=True)
    check("the Live turn is sent the Live note",
          any(L.MODEL_NOTE in s for s in live["system"]), live["system"])
    check("...and the typed turn is not",
          not any(L.MODEL_NOTE in s for s in typed["system"]), typed["system"])
    check("...the tool array the model reads is identical",
          live["tools"] == typed["tools"], (live["tools"], typed["tools"]))


def t_the_server_reads_the_marks_both_apps_send():
    """The phone sends live+voice on the newest spoken message
    (ChatHistoryTest: "a question said in Jarvis Live is marked live - the
    newest spoken one only"); the desktop does the same (main.js liveTag)."""
    def watch_for(msg):
        return A._TurnWatch([msg], {"messages": [msg]})
    check("live + provenance voice is a Live turn",
          watch_for({"role": "user", "content": "hi", "provenance": "voice",
                     "live": True}).live is True)
    check("live on a TYPED message is not a Live turn",
          watch_for({"role": "user", "content": "hi", "provenance": "typed",
                     "live": True}).live is False)
    check("provenance voice without the live mark is not a Live turn",
          watch_for({"role": "user", "content": "hi", "provenance": "voice"}).live is False)


# ------------------------------------------------------------- 3. PC state ---

def t_a_pc_state_question_gets_the_same_answer_in_live():
    def body(text, live):
        msg = {"role": "user", "content": text, "provenance": "voice"}
        if live:
            msg["live"] = True
        return {"messages": [msg], "model": "m", "stream": False}
    for question in ("how do I change the theme", "what can you do"):
        typed = Q.answer_turn(body(question, False))
        live = Q.answer_turn(body(question, True))
        check(f"the fast path answers a PC-state question in Live: {question!r}",
              typed is not None and live is not None
              and typed.reply == live.reply and bool(typed.reply.strip()),
              (None if typed is None else typed.reply[:80],
               None if live is None else live.reply[:80]))


# -------------------------------------------------------- 4. what stays put -

def t_no_voice_approval_surface_and_the_card_pause_is_kept():
    check("jarvis_live has no way to approve or deny a card",
          not any(hasattr(L, n) for n in
                  ("approve", "deny", "decide_card", "answer_card", "approve_card")),
          [n for n in dir(L) if "approv" in n.lower() or "deny" in n.lower()])
    check("...and it never imports the gate itself",
          "jarvis_gate" not in getattr(L, "__dict__", {}),
          [k for k in getattr(L, "__dict__", {}) if "gate" in k])
    check("a card still PAUSES Live (the pause reason is unchanged)",
          L.CARD_PAUSES == ("card", "cards_unknown"), L.CARD_PAUSES)
    check("...and the pause says a spoken yes is not heard",
          "approve or deny" in L.PAUSE_WORDS["card"], L.PAUSE_WORDS["card"])
    check("the Live note still tells the model to avoid yes-or-no endings",
          "yes-or-no question" in L.MODEL_NOTE, L.MODEL_NOTE)
    check("...and still marks side talk with the fixed marker",
          L.SIDE_TALK_MARK in L.MODEL_NOTE and L.is_side_talk(L.SIDE_TALK_MARK))


def t_the_repository_holds_the_shipped_twin():
    for name in ("jarvis_agent.py", "jarvis_live.py"):
        check(f"the published base carries {name}",
              (REPO / "jarvis-backend" / name).is_file(), name)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
