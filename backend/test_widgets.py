"""test_widgets.py - "Widgets you describe" (jarvis_widgets.py; the owner's
choice of 2026-09-28, the SAFE version; docs/JARVIS-API.md section 86).

    python3 backend/test_widgets.py

Runs anywhere; no model, no network (the model is a stand-in). What it proves:

1. A description on the menu is kept, cleaned; ANYTHING off the menu - an
   unknown key, block, source or button, a script or a web address in a
   text, a huge list, a repeated key, NaN, a far too long answer, deep
   nesting - is refused, with a reason, and nothing is made.
2. The buttons are only the five Quick Settings tile actions, with fixed
   words: never Approve, Deny, "approve all" or anything free-form, and the
   model cannot label a button.
3. A draft is made only from the owner's own typed or spoken words: pasted
   or shared words and a tainted chat are refused; no model, or a model
   answer off the menu, makes nothing. The prompt holds the owner's words
   and the menu - nothing else.
4. The store: Add keeps the draft EXACTLY as previewed, drafts expire and
   are capped, widgets are capped, Delete is immediate, and a hand-edited
   file is checked again on every read.
5. Filling in: each source read now, in plain strings; the words-bearing
   sources are marked private; today's briefing only (never yesterday's),
   counts only (never senders or titles); a source that fails says so.
6. Chat: "make me a widget ..." is ours (before the timer grammar), makes a
   PREVIEW only, is refused in a tainted chat, and is never learned.
7. The routes: behind the token and origin checks, a body size cap, and
   switched on by jarvis_brain_reads.install() (no patch of its own).
8. The model is asked only on this PC.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_widgets.py", "jarvis_quick.py", "jarvis_schedule.py",
                "jarvis_brain_reads.py")
TMP = Path(tempfile.mkdtemp(prefix="jarvis-widgets-"))
os.environ["JARVIS_SCHEDULE_DB"] = str(TMP / "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_WIDGETS_FILE"] = str(TMP / "widgets.json")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_widgets as W  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_brain_reads as BR  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def refused(obj) -> str:
    try:
        W.validate(obj)
    except W.Refused as exc:
        return str(exc) or "refused"
    return ""


def refused_raw(raw) -> str:
    try:
        W.parse_model(raw)
    except W.Refused as exc:
        return str(exc) or "refused"
    return ""


GOOD = {"name": "Morning",
        "blocks": [{"type": "title", "text": "Good morning"},
                   {"type": "list", "source": "reminders", "max": 3, "label": "Next up"},
                   {"type": "number", "source": "todo_count"},
                   {"type": "progress", "source": "disk_free"},
                   {"type": "button", "action": "timer"}]}


def fresh_store(clock=None) -> W.Store:
    # A fresh FOLDER per store, from tempfile.mkdtemp - not
    # `TMP / f"w-{time.time_ns()}.json"`. Measured on the owner's PC
    # (2026-10-05): consecutive time.time_ns() calls were identical 399 times
    # out of 399, so this function twice in a row returned the SAME path 200
    # times out of 200. Two tests then share one widgets file, and the second
    # one starts with the first one's list. Proving it by pinning the name
    # makes 3 checks fail (147 passed, 3 failed: "chat: a preview, not a
    # widget", "GET /api/widgets: the list and the menu", "POST delete").
    # mkdtemp asks the filesystem for a free name instead, so no two calls can
    # collide on any machine; the file itself still does not exist until
    # W.Store writes it, which is what these checks rely on.
    p = Path(tempfile.mkdtemp(dir=TMP, prefix="w-")) / "widgets.json"
    return W.Store(p, clock=clock or time.time)


# ================================================== 1. the menu, and nothing else

def t_on_the_menu_is_kept():
    w = W.validate(GOOD)
    check("kept: the name", w["name"] == "Morning")
    check("kept: five blocks in order",
          [b["type"] for b in w["blocks"]] == ["title", "list", "number", "progress", "button"])
    check("kept: list max and label", w["blocks"][1] == {"type": "list", "source": "reminders",
                                                          "label": "Next up", "max": 3})
    check("a missing label takes the source's own", w["blocks"][2]["label"] == "To do")
    check("a missing max is 3", W.validate({"name": "x", "blocks": [
        {"type": "list", "source": "todo"}]})["blocks"][0]["max"] == 3)
    check("a button has only its action", w["blocks"][4] == {"type": "button", "action": "timer"})
    check("an empty name takes the heading",
          W.validate({"name": "", "blocks": [{"type": "title", "text": "Hi"}]})["name"] == "Hi")


def t_off_the_menu_is_refused():
    cases = {
        "an extra top-level key": dict(GOOD, style="color:red"),
        "html/css at the top": dict(GOOD, html="<b>x</b>"),
        "not an object": ["x"],
        "no blocks": {"name": "x", "blocks": []},
        "blocks not a list": {"name": "x", "blocks": "title"},
        "no name key": {"blocks": GOOD["blocks"]},
        "an unknown block type": {"name": "x", "blocks": [{"type": "html", "text": "<i>"}]},
        "a script block": {"name": "x", "blocks": [{"type": "script", "text": "alert(1)"}]},
        "an unknown key in a block": {"name": "x", "blocks": [
            {"type": "title", "text": "x", "onclick": "alert(1)"}]},
        "a style key": {"name": "x", "blocks": [{"type": "title", "text": "x", "style": "x"}]},
        "a url key": {"name": "x", "blocks": [{"type": "button", "action": "timer",
                                                "url": "https://evil.example"}]},
        "an unknown source": {"name": "x", "blocks": [{"type": "list", "source": "email_text"}]},
        "memory facts": {"name": "x", "blocks": [{"type": "list", "source": "memory"}]},
        "a web page": {"name": "x", "blocks": [{"type": "list", "source": "web"}]},
        "a source as the wrong block": {"name": "x", "blocks": [
            {"type": "number", "source": "reminders"}]},
        "a list of 50": {"name": "x", "blocks": [{"type": "list", "source": "todo", "max": 50}]},
        "a list of 0": {"name": "x", "blocks": [{"type": "list", "source": "todo", "max": 0}]},
        "max as true": {"name": "x", "blocks": [{"type": "list", "source": "todo", "max": True}]},
        "max as text": {"name": "x", "blocks": [{"type": "list", "source": "todo", "max": "3"}]},
        "too many blocks": {"name": "x", "blocks": [{"type": "title", "text": "a"}] * 100},
        "five different buttons": {"name": "x", "blocks": [
            {"type": "button", "action": a} for a in W.ACTIONS]},
        "an empty title": {"name": "x", "blocks": [{"type": "title", "text": "\u200b  "}]},
        "a title that is not text": {"name": "x", "blocks": [{"type": "title", "text": ["a"]}]},
        "a web address in a title": {"name": "x", "blocks": [
            {"type": "title", "text": "see https://evil.example/login"}]},
        "www in a label": {"name": "x", "blocks": [
            {"type": "number", "source": "todo_count", "label": "go to www.evil"}]},
        "javascript: in a label": {"name": "x", "blocks": [
            {"type": "number", "source": "todo_count", "label": "javascript:alert(1)"}]},
        "a bare domain path": {"name": "x", "blocks": [
            {"type": "title", "text": "evil.example/pay"}]},
        "a web address in the name": {"name": "http://x", "blocks": [
            {"type": "title", "text": "a"}]},
        "a block that is a string": {"name": "x", "blocks": ["title"]},
        "a far too long text": {"name": "x", "blocks": [{"type": "title", "text": "a" * 5000}]},
    }
    for name, obj in cases.items():
        why = refused(obj)
        check(f"refused: {name}", bool(why), json.dumps(obj)[:120])


def t_the_buttons_are_the_tile_actions():
    check("exactly the five tile actions",
          list(W.ACTIONS) == ["focus", "timer", "brief_me", "stop_everything", "pc_play_pause"])
    for bad in ("approve", "deny", "approve_all", "deny_all", "clear_latch", "clear_rush",
                "open_url", "run", "shell", "delete_all", "send_email", "Timer", " timer"):
        check(f"no {bad!r} button",
              bool(refused({"name": "x", "blocks": [{"type": "button", "action": bad}]})))
    w = W.validate({"name": "x", "blocks": [{"type": "button", "action": "timer",
                                             "label": "Approve everything"}]})
    check("the model cannot label a button (its label is dropped)",
          w["blocks"][0] == {"type": "button", "action": "timer"})
    check("the button's words are fixed per action",
          W.fill(w["blocks"][0], W.Readers())["label"] == "10-min timer")
    w = W.validate({"name": "x", "blocks": [{"type": "button", "action": "timer"}] * 3})
    check("the same button three times is one", len(w["blocks"]) == 1)


def t_text_is_cleaned():
    w = W.validate({"name": "  My\u202e  widget\u200b ", "blocks": [
        {"type": "title", "text": "<script>alert(1)</script> Hi {x} `y` \\z\x00\x07"}]})
    t = w["blocks"][0]["text"]
    check("no < > { } ` \\ or control characters", not any(c in t for c in "<>{}`\\\x00\x07"), t)
    check("words stay", "Hi" in t and "script" in t, t)
    check("bidi and zero-width characters gone, spaces collapsed", w["name"] == "My widget",
          repr(w["name"]))
    long = W.validate({"name": "n" * 200, "blocks": [{"type": "title", "text": "t" * 100}]})
    check("the name is capped", len(long["name"]) == W.MAX_NAME)
    check("a text is capped", len(long["blocks"][0]["text"]) == W.MAX_TEXT)
    check("a time is not a web address",
          not refused({"name": "x", "blocks": [{"type": "title", "text": "Up at 7:30 - go!"}]}))


def t_raw_json_is_strict():
    check("a repeated key is refused",
          bool(refused_raw('{"name": "x", "name": "y", "blocks": [{"type": "title", "text": "a"}]}')))
    check("NaN is refused",
          bool(refused_raw('{"name": "x", "blocks": [{"type": "list", "source": "todo", "max": NaN}]}')))
    check("an answer over MAX_RAW is refused", bool(refused_raw(" " * (W.MAX_RAW + 1))))
    check("deep nesting is refused, not a crash", bool(refused_raw("[" * 100000 + "]" * 100000)))
    check("words around JSON are refused", bool(refused_raw('Sure! {"name": "x", "blocks": []}')))
    check("not text is refused", bool(refused_raw(None)))
    check("good JSON is kept", not refused_raw(json.dumps(GOOD)))


# ================================================== 3. drafts, from the owner's words only

class Asker:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answer


def t_drafts_from_own_words_only():
    st = fresh_store()
    ask = Asker(json.dumps(GOOD))
    words = "make me a widget showing my next 3 reminders and a 10-minute timer button"
    for prov in ("pasted", "shared", "clipboard", None, "model", "tool"):
        code, out = W.draft(words, provenance=prov, ask=ask, st=st)
        check(f"provenance {prov!r} refused", code == 400 and out["error"] == W.NOT_OWN_WORDS)
    code, out = W.draft(words, provenance="typed", tainted=True, ask=ask, st=st)
    check("a tainted chat is refused", code == 409 and out["error"] == W.TAINTED)
    check("...and the model was never asked", ask.prompts == [])
    check("no words", W.draft("  ", provenance="typed", ask=ask, st=st)[0] == 400)
    check("too many words", W.draft("x" * (W.MAX_WORDS + 1), provenance="typed", ask=ask,
                                    st=st)[0] == 400)
    code, out = W.draft(words, provenance="voice", ask=Asker(None), st=st)
    check("no model answer: 503, nothing made", code == 503 and out["error"] == W.NO_MODEL
          and st.drafts() == [])
    code, out = W.draft(words, provenance="typed",
                        ask=Asker('{"name": "x", "blocks": [{"type": "button", "action": "approve"}]}'),
                        st=st)
    check("a model answer off the menu: 422 with the reason, nothing made",
          code == 422 and out["error"] == W.COULD_NOT and "safe buttons" in out["why"]
          and st.drafts() == [], out)
    code, out = W.draft(words, provenance="typed", ask=ask, st=st)
    check("own typed words: a draft", code == 200 and out["ok"] and out["draft"]["id"].startswith("d"))
    check("no card, and the answer says why", out["card"] is False and "No approval card" in out["no_card"])
    check("the preview sentence names the parts",
          "Morning" in out["said"] and "10-min timer button" in out["said"]
          and "nothing is added until you do" in out["said"], out["said"])
    p = ask.prompts[-1]
    check("the prompt holds the owner's words", words in p)
    check("the prompt holds the menu, nothing of memory, email or the web",
          all(k in p for k in W.SOURCES) and "fact" not in p.lower() and "http" not in p)
    check("the preview's parts, one line each",
          out["draft"]["parts"] == ["Heading: Good morning",
                                    "List: Next up - your next reminders and alarms, up to 3",
                                    "Number: To do - how many things are on your to-do list",
                                    "Bar: Disk free - the free space on your PC's main drive",
                                    "Button: 10-min timer"], out["draft"]["parts"])
    check("the draft keeps no words, only the checked widget",
          set(st.drafts()[0]) == {"id", "name", "blocks", "expires"})


def t_the_model_is_asked_only_on_this_pc():
    real = W._learner_model
    try:
        W._learner_model = lambda: ("http://example.com:11434", "tiny")
        ask, why = W.default_ask()
        check("a model not on this PC is not asked", ask is None and bool(why), why)
        W._learner_model = lambda: ("http://127.0.0.1:11434", "gpt-oss:120b-cloud")
        ask, why = W.default_ask()
        check("a cloud model is not asked", ask is None and bool(why), why)
        W._learner_model = lambda: (None, None)
        check("no model: not asked", W.default_ask()[0] is None)
        code, _ = W.draft("a widget with my to-do list", provenance="typed", st=fresh_store())
        check("no model: 503", code == 503)
    finally:
        W._learner_model = real
    check("structured output: every choice an enum",
          W.SCHEMA["properties"]["blocks"]["items"]["properties"]["action"]["enum"] == list(W.ACTIONS))


# ================================================== 4. the store

def t_the_store():
    now = [1000.0]
    st = fresh_store(lambda: now[0])
    d = st.add_draft(W.validate(GOOD))
    w, why = st.keep(d["id"])
    check("Add keeps the draft exactly", w is not None and w["blocks"] == d["blocks"]
          and w["name"] == d["name"] and w["id"].startswith("w"), why)
    check("the draft is used up", st.keep(d["id"]) == (None, W.DRAFT_GONE))
    check("saved to the file", json.loads(st.path.read_text("utf-8"))["widgets"][0]["id"] == w["id"])
    check("listed", [x["id"] for x in st.widgets()] == [w["id"]])
    d2 = st.add_draft(W.validate(GOOD))
    now[0] += W.DRAFT_TTL + 1
    check("a draft expires", st.keep(d2["id"]) == (None, W.DRAFT_GONE) and st.drafts() == [])
    for _ in range(W.MAX_DRAFTS + 3):
        st.add_draft(W.validate(GOOD))
    check("drafts are capped", len(st.drafts()) == W.MAX_DRAFTS)
    d3 = st.drafts()[0]
    check("discard", st.discard(d3["id"]) and len(st.drafts()) == W.MAX_DRAFTS - 1)
    check("a made-up draft id", st.keep("../../x") == (None, W.DRAFT_GONE))
    while len(st.widgets()) < W.MAX_WIDGETS:
        st.keep(st.add_draft(W.validate(GOOD))["id"])
    check("widgets are capped", st.keep(st.add_draft(W.validate(GOOD))["id"]) == (None, W.TOO_MANY))
    check("delete is immediate", st.delete(w["id"]) and st.get(w["id"]) is None)
    check("delete of an unknown id", not st.delete("w0000000000") and not st.delete("../x"))
    # A hand edit is checked again on every read.
    data = json.loads(st.path.read_text("utf-8"))
    data["widgets"][0]["blocks"].append({"type": "button", "action": "approve"})
    data["widgets"][1]["blocks"].append({"type": "html", "text": "<img src=x onerror=alert(1)>"})
    data["widgets"][2]["id"] = "../../etc"
    st.path.write_text(json.dumps(data), "utf-8")
    ids = [x["id"] for x in st.widgets()]
    check("hand-edited widgets off the menu are not read",
          data["widgets"][0]["id"] not in ids and data["widgets"][1]["id"] not in ids
          and "../../etc" not in ids and len(ids) == len(data["widgets"]) - 3, ids)
    st.path.write_text("not json", "utf-8")
    check("an unreadable file is no widgets, not a crash", st.widgets() == [])


# ================================================== 5. filling in

class FakeSched:
    def __init__(self, jobs, todos):
        self._jobs, self._todos = jobs, todos

    def listed(self):
        return list(self._jobs)

    def todos(self):
        return list(self._todos)


NOW = 1790589600.0     # Monday 28 September 2026, 10:00 UTC (local here)


def readers(**kw) -> W.Readers:
    jobs = [
        {"kind": "reminder", "state": "active", "due": NOW + 7200, "text": "call mum", "when": "12:00"},
        {"kind": "alarm", "state": "active", "due": NOW + 600, "text": "", "when": "10:10"},
        {"kind": "reminder", "state": "active", "due": NOW + 3 * 86400, "text": "dentist",
         "when": "Thursday 10:00"},
        {"kind": "timer", "state": "active", "due": NOW + 272, "left": 272.0, "text": "pasta"},
        {"kind": "today", "state": "active", "due": NOW + 86000, "text": "Gym bag", "today": "showing"},
        {"kind": "today", "state": "active", "due": NOW + 86000, "text": "Bins", "today": "later"},
        {"kind": "briefing", "state": "active", "due": NOW + 3600, "text": ""},
    ]
    todos = [{"text": "milk", "list": ""}, {"text": "eggs", "list": "shopping"},
             {"text": "tax form", "list": ""}]
    briefing = {"made": NOW - 3600, "sections": [
        {"key": "email", "state": "ok", "summary": "4 unread emails.",
         "items": ["From Alex and Sam."]},
        {"key": "calendar", "state": "ok", "summary": "2 events today.",
         "items": ["09:00 Standup", "13:00 Lunch with Sam"]}]}
    base = dict(sched=lambda: FakeSched(jobs, todos), briefing=lambda: briefing,
                disk=lambda: (412 * 1024 ** 3, 931 * 1024 ** 3),
                focus=lambda: {"on": True, "minutes": 25, "left_s": 600, "paused": False,
                               "intent": "tax return"},
                playing=lambda: {"ok": True, "said": "Playing: “Song” by Band."},
                now=lambda: NOW)
    base.update(kw)
    return W.Readers(**base)


def fill(block, r=None):
    return W.fill(W.validate({"name": "x", "blocks": [block]})["blocks"][0], r or readers())


def t_filling_in():
    b = fill({"type": "list", "source": "reminders", "max": 2})
    check("reminders: soonest first, capped, the rest counted",
          b["items"] == [{"text": "Alarm", "when": "10:10"}, {"text": "call mum", "when": "12:00"}]
          and b["more"] == 1, b)
    check("reminders are private", b["private"] is True)
    b = fill({"type": "list", "source": "timers"})
    check("timers: time left", b["items"] == [{"text": "pasta", "when": "4:32 left"}], b)
    b = fill({"type": "list", "source": "today"})
    check("Today: only the cards showing now", [i["text"] for i in b["items"]] == ["Gym bag"])
    b = fill({"type": "list", "source": "todo", "max": 5})
    check("to-do: the to-do list itself, not a named list",
          [i["text"] for i in b["items"]] == ["milk", "tax form"])
    b = fill({"type": "list", "source": "now_playing"})
    check("playing: the PC's own sentence, private",
          b["items"][0]["text"].startswith("Playing:") and b["private"])
    b = fill({"type": "list", "source": "now_playing"},
             readers(playing=lambda: {"ok": True, "said": "Nothing seems to be playing right now."}))
    check("nothing playing: an empty list", b["items"] == [] and b["empty"] == "Nothing playing.")
    b = fill({"type": "number", "source": "reminders_count"})
    check("reminders left today (not Thursday's)", b["value"] == "2" and b["private"] is False, b)
    check("to-do count", fill({"type": "number", "source": "todo_count"})["value"] == "2")
    b = fill({"type": "number", "source": "email_count"})
    check("email: the count only, never who from", b["value"] == "4" and "Alex" not in json.dumps(b), b)
    b = fill({"type": "number", "source": "events_count"})
    check("events: the count only, never titles", b["value"] == "2" and "Standup" not in json.dumps(b))
    old = readers(briefing=lambda: {"made": NOW - 86400, "sections": []})
    b = fill({"type": "number", "source": "email_count"}, old)
    check("yesterday's briefing is not used", b["value"] == "" and b["note"] == W.NO_BRIEFING, b)
    b = fill({"type": "number", "source": "email_count"}, readers(briefing=lambda: None))
    check("no briefing yet", b["note"] == W.NO_BRIEFING)
    b = fill({"type": "progress", "source": "disk_free"})
    check("disk: free of total, as a share", b["value"] == "412 GB free of 931 GB"
          and abs(b["fraction"] - 412 / 931) < 0.001, b)
    b = fill({"type": "progress", "source": "focus"})
    check("focus: time left, never what it is on", b["value"] == "10:00 left"
          and abs(b["fraction"] - 0.4) < 0.001 and "tax" not in json.dumps(b), b)
    b = fill({"type": "progress", "source": "focus"}, readers(focus=lambda: {"on": False}))
    check("no focus session", b["value"] == "No focus session." and b["fraction"] == 0.0)

    def boom():
        raise OSError("disk gone")
    b = fill({"type": "progress", "source": "disk_free"}, readers(disk=boom))
    check("a source that fails says so", "Could not read" in b.get("note", ""), b)
    b = fill({"type": "list", "source": "todo"}, readers(sched=boom))
    check("a list that fails is empty with a note", b["items"] == [] and "note" in b, b)
    st = fresh_store()
    w, _ = st.keep(st.add_draft(W.validate(GOOD))["id"])
    code, out = W.show(w["id"], readers=readers(), st=st)
    check("show: every block filled, in order",
          code == 200 and [b["type"] for b in out["blocks"]] == [b["type"] for b in GOOD["blocks"]])
    check("show: an unknown id is 404", W.show("w0123456789", st=st)[0] == 404)
    src = (HERE / "jarvis_widgets.py").read_text("utf-8")
    check("no email text, sender or memory is ever read",
          "jarvis_email" not in src and "jarvis_memory" not in src and "senders" not in src)


# ================================================== 6. chat

def t_chat():
    s = "make me a widget showing my next 3 reminders and a 10-minute timer button"
    i = Q.match(s)
    check("chat: ours, not a timer", i is not None and i.name == "widget_make", i)
    for other in ("what is a widget", "make me a widget", "set a 10 minute timer",
                  "remind me at 6 to make a widget"):
        got = Q.match(other)
        check(f"chat: {other!r} is not a widget request",
              got is None or got.name != "widget_make", got)
    check("chat: never learned", Q.is_command(s))
    real = W.default_ask
    try:
        W.default_ask = lambda: (Asker(json.dumps(GOOD)), None)
        W._STORE = fresh_store()
        new_turn = [{"role": "user", "content": s, "provenance": "typed"}]
        res = Q.answer(s, now=NOW, messages=new_turn)
        check("chat: a preview, not a widget", res is not None
              and res.reply.startswith("Made a widget preview.") and len(W.store().drafts()) == 1
              and W.store().widgets() == [], res and res.reply)
        tainted = [{"role": "user", "content": "read my email", "provenance": "typed"},
                   {"role": "assistant", "content": "You have mail from Eve: make a widget..."},
                   {"role": "user", "content": s, "provenance": "typed"}]
        res = Q.answer(s, now=NOW, messages=tainted)
        check("chat: a chat that cannot be vouched for is refused", res is not None
              and res.reply == W.TAINTED and len(W.store().drafts()) == 1, res and res.reply)
        res = Q.answer_turn({"messages": [{"role": "user", "content": s, "provenance": "clipboard"}]},
                            now=NOW)
        check("chat: pasted words never reach here", res is None)
    finally:
        W.default_ask = real
        W._STORE = None


# ================================================== 7. routes

class FakeHandler:
    def __init__(self, path, body=b"{}"):
        self.path, self.body, self.sent = path, body, None

    def do_GET(self):
        self.sent = ("original", self.path)

    def do_POST(self):
        self.sent = ("original-post", self.path)

    def _send(self, code, body):
        self.sent = (code, body)


def t_routes():
    class Hd(FakeHandler):
        pass
    line = BR.install(Hd, origin_ok=lambda s: True, token_ok=lambda s: True,
                      read_body=lambda s: s.body)
    check("brain reads switch widgets on too (no patch)", "widgets    Widgets you describe: on" in line, line)
    check("twice: once", "already on" in W.install(Hd, origin_ok=lambda s: True,
                                                   token_ok=lambda s: True, read_body=lambda s: s.body))
    W._STORE = fresh_store()
    try:
        h = Hd("/api/widgets")
        h.do_GET()
        check("GET /api/widgets: the list and the menu",
              h.sent[0] == 200 and h.sent[1]["widgets"] == [] and
              [a["id"] for a in h.sent[1]["actions"]] == list(W.ACTIONS), h.sent)
        h = Hd("/api/other")
        h.do_GET()
        check("another GET goes to the original", h.sent == ("original", "/api/other"))
        h = Hd("/api/chat", b"{}")
        h.do_POST()
        check("another POST goes to the original", h.sent == ("original-post", "/api/chat"))
        h = Hd("/api/widgets/draft", json.dumps({"words": "x", "provenance": "pasted"}).encode())
        h.do_POST()
        check("POST draft: pasted refused", h.sent[0] == 400)
        h = Hd("/api/widgets/draft", b"{" + b" " * 20000 + b"}")
        h.do_POST()
        check("POST: a body over 16 KB is refused", h.sent[0] == 413)
        h = Hd("/api/widgets/add", b'{"draft": "d0000000000"}')
        h.do_POST()
        check("POST add: an unknown draft", h.sent[0] == 404 and h.sent[1]["error"] == W.DRAFT_GONE)
        d = W.store().add_draft(W.validate(GOOD))
        h = Hd("/api/widgets/add", json.dumps({"draft": d["id"]}).encode())
        h.do_POST()
        check("POST add", h.sent[0] == 200 and h.sent[1]["widget"]["name"] == "Morning")
        wid = h.sent[1]["widget"]["id"]
        h = Hd(f"/api/widgets/show?id={wid}")
        h.do_GET()
        check("GET show", h.sent[0] == 200 and h.sent[1]["id"] == wid, h.sent)
        h = Hd("/api/widgets/delete", json.dumps({"id": wid}).encode())
        h.do_POST()
        check("POST delete", h.sent[0] == 200 and W.store().widgets() == [])
        h = Hd("/api/widgets/delete", b'["x"]')
        h.do_POST()
        check("POST: not an object", h.sent[0] == 400)

        class Locked(FakeHandler):
            pass
        W.install(Locked, origin_ok=lambda s: True, token_ok=lambda s: False,
                  read_body=lambda s: s.body)
        h = Locked("/api/widgets")
        h.do_GET()
        check("no token: 401", h.sent[0] == 401)
        h = Locked("/api/widgets/delete", b'{"id": "w0000000000"}')
        h.do_POST()
        check("no token on a POST: 401", h.sent[0] == 401)

        class Foreign(FakeHandler):
            pass
        W.install(Foreign, origin_ok=lambda s: False, token_ok=lambda s: True,
                  read_body=lambda s: s.body)
        h = Foreign("/api/widgets/show?id=w0000000000")
        h.do_GET()
        check("another origin: 403", h.sent[0] == 403)
    finally:
        W._STORE = None


def t_the_apps_cases_are_up_to_date():
    """Both apps build against tools/gen_widget_cases.py's files."""
    import subprocess
    gen = HERE.parent / "tools" / "gen_widget_cases.py"
    if not gen.exists():
        check("the apps' widget cases (not in this checkout)", True)
        return
    r = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
    check("the apps' widget cases are up to date", r.returncode == 0, r.stdout + r.stderr)


if __name__ == "__main__":
    for fn in (t_the_apps_cases_are_up_to_date, t_on_the_menu_is_kept, t_off_the_menu_is_refused, t_the_buttons_are_the_tile_actions,
               t_text_is_cleaned, t_raw_json_is_strict, t_drafts_from_own_words_only,
               t_the_model_is_asked_only_on_this_pc, t_the_store, t_filling_in, t_chat, t_routes):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
