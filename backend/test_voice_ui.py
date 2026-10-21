"""jarvis_voice_ui.py: what a spoken Live question may READ off this PC.

    python -B backend/run_suites.py test_voice_ui.py

THE SLICE (task-39, the audit's V7): a Live question may ask to read the
screen ("what's on my screen?") or the highlighted text ("read this
selection", "summarise what I selected"). Both are the EXISTING primitives -
jarvis_screen's "Look at this" and jarvis_ui_control.read_selection() - and
nothing new: no capture code, no new permission, no gate row, no tool, no
switch. The words are added to that one request as OUTSIDE TEXT and nowhere
else.

WHAT THIS SUITE PROVES: the intent words are narrow (an ordinary question
with "screen" in it is not hijacked); each read returns the expected shaped
answer from a STUBBED primitive and never writes, logs or stores a word; a
phone Live session reads nothing and says so in a fixed line; a paused look
passes the screen module's own words; the read never asks the gate and never
clicks; and - the hard rule - an action that CHANGES things still raises the
existing ONE card through control_computer, whose own contract runs nothing
until a person answers, by tap/click, never by voice.

Real screen/UIA reads are NOT driven here (no desktop in CI): the read seams
are, plus the existing tool contract. A real Live sentence with a real look is
owner-tested and reads NOT-TESTABLE until then.
"""
import json
import os
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_voice_ui.py", "jarvis_agent.py", "jarvis_screen.py",
                "jarvis_ui_control.py")

TMP = Path(tempfile.mkdtemp(prefix=".jarvis-voice-ui-tests-", dir=str(Path.home())))
CONF = TMP / "config"
LOGS = TMP / "logs"
CONF.mkdir()
LOGS.mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["OPENJARVIS_HOME"] = str(TMP / "home")
(TMP / "home").mkdir()
os.environ["JARVIS_LOG_DIR"] = str(LOGS)
os.environ.pop("JARVIS_CONFIG_DIR", None)
os.environ.pop("JARVIS_BACKEND", None)

import jarvis_voice_ui as V  # noqa: E402
import jarvis_agent as A  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []
CANARY = "CANARY-VOICE-UI-WORDS-42"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    shutil.rmtree(CONF, ignore_errors=True)
    shutil.rmtree(LOGS, ignore_errors=True)
    shutil.rmtree(TMP / "home", ignore_errors=True)
    CONF.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    (TMP / "home").mkdir(parents=True, exist_ok=True)


def files_under(root: Path) -> list:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file())


def canary_anywhere() -> list:
    hits = []
    for root in (CONF, LOGS, TMP / "home"):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            try:
                if CANARY.lower() in p.read_bytes().lower():
                    hits.append(str(p.relative_to(TMP)))
            except OSError:
                pass
    return hits


class Screen:
    """jarvis_screen's ENGINE, stood in for: `look_at_this` answers the same
    shape the real one answers, and records the call."""

    def __init__(self, ok=True, part=None, said="", note="I looked."):
        self.ok, self.calls = ok, []
        self.part = part if part is not None else (
            "[OUTSIDE TEXT - what is on your screen right now]\n" + CANARY)
        self.said, self.note = said, note

    def look_at_this(self, wait=True):
        self.calls.append(bool(wait))
        if not self.ok:
            return {"ok": False, "paused": "a_password_box", "said": self.said}
        return {"ok": True, "part": self.part, "note": self.note}


class Reader:
    """jarvis_ui_control.read_selection, stood in for."""

    def __init__(self, result=None):
        self.result, self.calls = result, []

    def __call__(self):
        self.calls.append(True)
        if self.result is not None:
            return self.result
        return {"ok": True, "refused": False, "why": "", "text": CANARY,
                "app": "Notepad", "chars": len(CANARY), "truncated": False,
                "scrubbed": False, "words": "Read the highlighted text."}


class GateSpy:
    """jarvis_gate stood in for: the READ path must never call check(); it
    may latch the taint, and the reason it gives must be a plain one."""

    def __init__(self):
        self.checks, self.latches = [], []
        self.module = types.ModuleType("jarvis_gate")
        self.module.check = lambda *a, **k: (
            self.checks.append(a), (_ for _ in ()).throw(
                AssertionError("a read must never ask the gate")))[1]
        self.module.latch_taint = lambda why="": (self.latches.append(why), True)[1]
        self.saved = None

    def __enter__(self):
        self.saved = sys.modules.get("jarvis_gate")
        sys.modules["jarvis_gate"] = self.module
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = self.saved


def msgs(words: str) -> list:
    return [{"role": "user", "content": words, "provenance": "voice", "live": True}]


# --------------------------------------------------------------------------
#   The words that count as asking (narrow on purpose)
# --------------------------------------------------------------------------

def t_the_intent_words_are_narrow():
    check("'what's on my screen?' asks for the screen",
          V.asked("what's on my screen?") == "screen")
    check("'what is on the screen' asks for the screen",
          V.asked("What is on the screen right now") == "screen")
    check("'read my screen' asks for the screen",
          V.asked("read my screen") == "screen")
    check("'read this selection' asks for the selection",
          V.asked("read this selection") == "selection")
    check("'what did I highlight?' asks for the selection",
          V.asked("what did i highlight") == "selection")
    check("'summarise what I selected' asks for the selection",
          V.asked("summarise what I selected") == "selection")
    check("an ordinary sentence with 'screen' is NOT the ask",
          V.asked("the cinema screen was huge in that film") == "")
    check("'selected' in another sense is NOT the ask",
          V.asked("i selected the blue paint for the kitchen") == "")
    check("an ordinary question asks nothing",
          V.asked("what's the weather tomorrow") == "")
    check("an empty question asks nothing", V.asked("") == "")


# --------------------------------------------------------------------------
#   The reads: shaped answers from the existing primitives, nothing else
# --------------------------------------------------------------------------

def t_a_screen_question_reads_once_and_adds_outside_text():
    fresh()
    eng = Screen()
    out, info = V.with_voice_read(msgs("what's on my screen?"),
                                  "what's on my screen?", engine=eng,
                                  session="desktop")
    check("the screen was looked at exactly once, and waited for",
          eng.calls == [True], eng.calls)
    check("the answer says a read happened, under the existing name",
          info.get("read") is True and info.get("tool") == V.SCREEN_TOOL
          and info.get("tool") == "read_screen", info)
    check("the words are the existing model part, unchanged",
          info.get("text") == eng.part, info.get("text"))
    check("the words were added as a part of the OWNER's message",
          isinstance(out[0]["content"], list) and len(out[0]["content"]) == 2,
          out[0]["content"])
    check("... the owner's own words stay a separate part, first",
          out[0]["content"][0] == {"type": "text", "text": "what's on my screen?"})
    check("... and the read words are the second part, labelled outside text",
          out[0]["content"][1]["text"] == eng.part
          and "OUTSIDE TEXT" in out[0]["content"][1]["text"])


def t_a_selection_question_reads_the_highlighted_text():
    fresh()
    reader = Reader()
    out, info = V.with_voice_read(msgs("read this selection"),
                                  "read this selection", reader=reader,
                                  session="desktop")
    check("the existing selection reader was called exactly once",
          reader.calls == [True], reader.calls)
    check("the answer reports the read under the existing name",
          info.get("read") is True and info.get("tool") == "read_screen", info)
    check("... the text is the reader's own text",
          info.get("text") == CANARY and info.get("app") == "Notepad", info)
    body = out[0]["content"][-1]["text"]
    check("... and it is handed on as OUTSIDE TEXT of its own",
          "OUTSIDE TEXT" in body and "HIGHLIGHTED" in body and CANARY in body, body)


def t_a_summary_question_uses_the_same_read():
    fresh()
    reader = Reader()
    _out, info = V.with_voice_read(msgs("summarise what I selected"),
                                   "summarise what I selected", reader=reader,
                                   session="desktop")
    check("asking for a summary reads the same selection (the model writes the summary)",
          reader.calls == [True] and info.get("read") is True
          and info.get("mode") == "selection", info)


def t_a_paused_screen_says_the_fixed_line():
    fresh()
    eng = Screen(ok=False, said="There's a password box in front, so no look.")
    out, info = V.with_voice_read(msgs("what's on my screen?"),
                                  "what's on my screen?", engine=eng,
                                  session="desktop")
    check("a refused look reads nothing and adds no words",
          info.get("read") is False and out[0]["content"] == "what's on my screen?",
          (info, out))
    check("... and it says the screen module's own fixed line, by code",
          "password box" in str(info.get("said")) and not info.get("text"), info)


def t_a_selection_refusal_passes_the_readers_words():
    fresh()
    reader = Reader({"ok": False, "refused": True, "why": "no_selection",
                     "words": "There is no highlighted text in the window in front."})
    out, info = V.with_voice_read(msgs("read this selection"),
                                  "read this selection", reader=reader,
                                  session="desktop")
    check("a selection refusal reads nothing and adds no words",
          info.get("read") is False and out[0]["content"] == "read this selection",
          (info, out))
    check("... and it hands on the reader's own plain words",
          "no highlighted text" in str(info.get("said")), info.get("said"))


def t_a_phone_live_session_reads_nothing():
    fresh()
    eng, reader = Screen(), Reader()
    for words in ("what's on my screen?", "read this selection"):
        out, info = V.with_voice_read(msgs(words), words,
                                      engine=eng, reader=reader, session="phone")
        check(f"a phone session asking '{words}' reads NOTHING",
              info.get("read") is False and eng.calls == [] and reader.calls == [],
              (info, eng.calls, reader.calls))
        check("... and the fixed phone line says why (the PC's screen is the PC's)",
              info.get("said") == V.PHONE_WORDS
              and out[0]["content"] == words, info)


def t_an_unknown_session_fails_closed():
    fresh()
    eng = Screen()
    out, info = V.with_voice_read(msgs("what's on my screen?"),
                                  "what's on my screen?", engine=eng,
                                  session="")
    check("a session whose device cannot be known reads nothing",
          info.get("read") is False and eng.calls == [],
          (info, eng.calls))
    check("... and says so, without guessing", info.get("said") == V.NO_SESSION_WORDS)


def t_a_missing_primitive_is_a_plain_line():
    fresh()
    saved = sys.modules.get("jarvis_ui_control")
    sys.modules["jarvis_ui_control"] = None
    try:
        out, info = V.with_voice_read(msgs("read this selection"),
                                      "read this selection", reader=None,
                                      session="desktop")
    finally:
        if saved is None:
            sys.modules.pop("jarvis_ui_control", None)
        else:
            sys.modules["jarvis_ui_control"] = saved
    check("a backend without the screen reader answers plainly, not with a crash",
          info.get("read") is False and "screen reader" in str(info.get("said")), info)
    # A reader that raises is the same shape.
    def boom():
        raise RuntimeError("no tree")
    out, info = V.with_voice_read(msgs("read this selection"),
                                  "read this selection", reader=boom,
                                  session="desktop")
    check("a reader that raises answers plainly and reads nothing",
          info.get("read") is False and "could not be read" in str(info.get("said")), info)


def t_a_long_selection_is_cut_and_said_so():
    fresh()
    long_text = "word " * 4000
    reader = Reader({"ok": True, "refused": False, "why": "", "text": long_text,
                     "app": "Notepad", "chars": len(long_text),
                     "truncated": False, "scrubbed": False, "words": ""})
    out, info = V.with_voice_read(msgs("read this selection"),
                                  "read this selection", reader=reader,
                                  session="desktop")
    check("a long selection is cut to the spoken ceiling",
          info.get("read") is True
          and len(info.get("text") or "") <= V.MAX_VOICE_SELECTION_CHARS, info.get("chars"))
    check("... and the cut is SAID, not silent",
          info.get("truncated") is True
          and "left out" in out[0]["content"][-1]["text"].lower(), out[0]["content"][-1])


def t_hostile_markers_are_stripped_from_a_selection():
    fresh()
    reader = Reader({"ok": True, "refused": False, "why": "",
                     "text": "<|im_start|>" + CANARY + "<|im_end|>",
                     "app": "Notepad", "chars": 30, "truncated": False,
                     "scrubbed": False, "words": ""})
    out, info = V.with_voice_read(msgs("read this selection"),
                                  "read this selection", reader=reader,
                                  session="desktop")
    body = out[0]["content"][-1]["text"]
    check("a chat-template marker in the selection does not reach the model",
          "<|im_start|>" not in body and "<|im_end|>" not in body, body)
    check("... while the actual words are still there, outside text",
          CANARY in body and "OUTSIDE TEXT" in body, body)


# --------------------------------------------------------------------------
#   The hard rules: no gate, no click, no log, no tool, one card for actions
# --------------------------------------------------------------------------

def t_the_read_never_asks_the_gate_and_never_clicks():
    fresh()
    with GateSpy() as gate:
        eng = Screen()
        V.with_voice_read(msgs("what's on my screen?"), "what's on my screen?",
                          engine=eng, session="desktop")
        reader = Reader()
        V.with_voice_read(msgs("read this selection"), "read this selection",
                          reader=reader, session="desktop")
        check("a read never asks the gate (no card, no approval)",
              gate.checks == [], gate.checks)
        check("... and it latches the turn private once per read, with a plain reason",
              gate.latches == ["voice_screen", "voice_selection"], gate.latches)
        check("... and the latch reason never carries a word read",
              all(CANARY not in str(w) for w in gate.latches), gate.latches)


def t_the_words_are_not_written_anywhere():
    fresh()
    before = (files_under(CONF), files_under(LOGS), files_under(TMP / "home"))
    eng = Screen()
    reader = Reader()
    V.with_voice_read(msgs("what's on my screen?"), "what's on my screen?",
                      engine=eng, session="desktop")
    V.with_voice_read(msgs("read this selection"), "read this selection",
                      reader=reader, session="desktop")
    after = (files_under(CONF), files_under(LOGS), files_under(TMP / "home"))
    check("a read writes no file at all (settings, logs or home unchanged)",
          before == after, {"before": before, "after": after})
    check("... and not one word the read returned appears in any file",
          canary_anywhere() == [], canary_anywhere())
    check("... no memory.db is created by a read",
          not any("memory.db" in name for name in files_under(CONF)), files_under(CONF))


def t_typed_chat_has_no_screen_query_of_its_own():
    fresh()
    names = set(A.TOOLS)
    check("no new tool was added to the model's tool list by this slice",
          not any(n in names for n in ("look_at_screen", "read_selection",
                                       "voice_screen_query", "screen_query")),
          sorted(n for n in names if "screen" in n or "select" in n))
    check("... and the voice read names are not offered to typed chat",
          not (set(V.READS) & set(A.offered_tools(None))))
    check("... the existing UI action stays the only way to change a program",
          "control_computer" in names)


def t_the_live_hook_does_nothing_without_live_words():
    fresh()
    watch = A._TurnWatch()
    out, info = A._live_voice_read(msgs("hello"), watch)
    check("a Live turn whose words ask nothing is left alone",
          info.get("read") is False and out[0]["content"] == "hello", (info, out))
    check("... and no screen engine is touched when nothing asks",
          info.get("said") == "", info)


class _Out:
    """The one writer to the app, stood in for (the methods a tool call
    reaches are all this)."""

    gone = False

    def set_status(self, _status):
        pass

    def card_answered(self, _verdict):
        pass


class _Verdict:
    def __init__(self, allowed, outcome=None, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


def t_a_carded_action_raises_one_card_and_runs_nothing_first():
    fresh()
    calls, ran = [], []
    tool = A.Tool(
        "control_computer",
        "click a named control (stub)",
        {"type": "object", "properties": {"goal": {"type": "string"}},
         "required": ["goal"]},
        prepare=lambda args: (None, "Plan: click \"Export\" in Notepad."),
        execute=lambda args, state, **kw: (ran.append(True), {"ok": True})[1],
        gate_lookup_name=lambda args: "jarvis_ui_control_run")
    tools = {"control_computer": tool}
    denied = _Verdict(False, outcome="denied")

    def checker_denied(action, detail, prompt):
        calls.append((action, detail, prompt))
        return denied
    convo, steps = [], []
    A._one_call({"id": "1", "function": {"name": "control_computer",
                                         "arguments": json.dumps(
                                             {"goal": "click Export"})}},
                ["control_computer"], convo, steps, checker_denied, None,
                _Out(), lambda *a, **k: None, watch=A._TurnWatch(),
                tools=tools)
    check("a spoken screen ACTION raises exactly ONE card",
          len(calls) == 1, calls)
    check("... under the EXISTING UI-control action, not a new one",
          calls and calls[0][0] in ("control_computer", "jarvis_ui_control_run"),
          calls[0][0] if calls else None)
    check("... and NOTHING ran before a person answered",
          ran == [] and not any(s.get("ran") for s in steps),
          (ran, steps))
    check("... the model is told the decision was no, and that nothing ran",
          convo and ("denied" in str(convo[-1].get("content")).lower()
                     or "not" in str(convo[-1].get("content")).lower()), convo)

    approved = _Verdict(True, outcome="approved")

    def checker_yes(action, detail, prompt):
        calls.append((action, detail, prompt))
        return approved
    ran.clear(); convo.clear(); steps.clear(); calls.clear()
    A._one_call({"id": "2", "function": {"name": "control_computer",
                                         "arguments": json.dumps(
                                             {"goal": "click Export"})}},
                ["control_computer"], convo, steps, checker_yes, None,
                _Out(), lambda *a, **k: None, watch=A._TurnWatch(),
                tools=tools)
    check("with a person's yes the SAME one-card path runs the plan once",
          len(calls) == 1 and ran == [True], (calls, ran))


def t_the_live_diet_still_shows_the_existing_ui_tool_for_a_screen_action():
    fresh()
    real_short, real_diet = A.short_list_on, A.tool_diet_on
    A.short_list_on = lambda: False
    A.tool_diet_on = lambda: True
    try:
        names = A.offered_tools(["calculator", "web_search", "control_computer"])
        offer = A._new_offer(names, limit=A.jarvis_live.live_tool_limit()
                             if hasattr(A, "jarvis_live") else 6)
        A._fill_offer(offer, names, question="click the Export button in Notepad",
                      conversation_id="voice-ui-test")
        check("a spoken 'click Export' Live turn is shown the existing control tool",
              "control_computer" in offer["shown"], offer["shown"])
        check("... so any change goes through its ONE existing card, never a new path",
              A.TOOLS["control_computer"].gate_lookup_name({})
              == "jarvis_ui_control_run")
    finally:
        A.short_list_on, A.tool_diet_on = real_short, real_diet


def t_the_screen_read_is_recorded_under_the_existing_read_name():
    fresh()
    check("the module records a screen look under jarvis_screen's own name",
          V.SCREEN_TOOL == "read_screen" == A.SCREEN_TOOL)
    check("... which is on the project's own step-event allowlist",
          "read_screen" in A.STEP_READS)


# --------------------------------------------------------------------------
#   Runner
# --------------------------------------------------------------------------

def main() -> int:
    print(f"tree: {HERE}")
    for fn in (t_the_intent_words_are_narrow,
               t_a_screen_question_reads_once_and_adds_outside_text,
               t_a_selection_question_reads_the_highlighted_text,
               t_a_summary_question_uses_the_same_read,
               t_a_paused_screen_says_the_fixed_line,
               t_a_selection_refusal_passes_the_readers_words,
               t_a_phone_live_session_reads_nothing,
               t_an_unknown_session_fails_closed,
               t_a_missing_primitive_is_a_plain_line,
               t_a_long_selection_is_cut_and_said_so,
               t_hostile_markers_are_stripped_from_a_selection,
               t_the_read_never_asks_the_gate_and_never_clicks,
               t_the_words_are_not_written_anywhere,
               t_typed_chat_has_no_screen_query_of_its_own,
               t_the_live_hook_does_nothing_without_live_words,
               t_a_carded_action_raises_one_card_and_runs_nothing_first,
               t_the_live_diet_still_shows_the_existing_ui_tool_for_a_screen_action,
               t_the_screen_read_is_recorded_under_the_existing_read_name):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:                                 # noqa: BLE001
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
