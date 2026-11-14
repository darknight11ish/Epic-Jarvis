"""test_widgets.py - "Widgets you describe" (jarvis_widgets.py; the owner's
choice of 2026-09-28, the SAFE version; docs/JARVIS-API.md section 86).

    python3 backend/test_widgets.py

Runs anywhere; no model, no network (the model is a stand-in). What it proves:

1. A description on the menu is kept, cleaned; ANYTHING off the menu - an
   unknown key, block, source or button, a script or a web address in a
   text, a huge list, a repeated key, NaN, a far too long answer, deep
   nesting, or an arrangement that is not one of the four - is refused, with
   a reason, and nothing is made.
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
9. The look (2026-11-14): accent, shade and contrast are closed lists of their
   own; absent means today's look so every older widget is unchanged, off the
   list is refused rather than defaulted, the preview's pickers may change it
   before Add, a draft is readable so the phone can draw a live preview, and
   every colour on the three lists is READABLE (WCAG AA, 4.5:1) on both
   backgrounds in both contrasts - measured, not eyeballed.
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
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("the apps' widget cases (not in this
    checkout)", True) - a condition of the constant True, so it printed as a
    pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


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


# ================================================== 2b. the arrangement (2026-10-30)

def t_the_arrangement_is_a_closed_list():
    """The four layouts: a closed list, default "stack", refused off the list,
    and shown to the owner in the preview. The one arrangement rule itself is
    proved by tools/gen_widget_cases.py and by both apps' own tests against
    its `boards`; this proves the PC's half - that a layout it hands out is
    one the apps can draw, and that it never invents one."""
    check("exactly the four arrangements",
          list(W.LAYOUTS) == ["stack", "big", "list", "compact"], list(W.LAYOUTS))
    check("the default is stack",
          W.validate({"name": "x", "blocks": [{"type": "title", "text": "a"}]})["layout"] == "stack")
    for layout in W.LAYOUTS:
        w = W.validate({"name": "x", "layout": layout,
                        "blocks": [{"type": "title", "text": "a"}]})
        check(f"kept: the {layout!r} arrangement", w["layout"] == layout)
    for bad in ("BIG", "Grid", "grid", "", " stack", "stack ", "tiles", "<script>",
                "stack\n", None, True, False, 0, 3, ["stack"], {"kind": "big"}):
        why = refused({"name": "x", "layout": bad,
                       "blocks": [{"type": "title", "text": "a"}]})
        check(f"refused: the arrangement {bad!r}", bool(why), json.dumps(bad, default=str))
    # An arrangement is not a place to put styling or code. `accent` left this
    # list on 2026-11-14, when it became a real key with a closed list of its
    # own (t_the_look_is_a_closed_list); every name still here is still refused.
    for key in ("colour", "color", "style", "columns", "grid", "font", "hex"):
        why = refused({"name": "x", key: "x", "blocks": [{"type": "title", "text": "a"}]})
        check(f"refused: a {key!r} key", bool(why))
    # The preview shows what was asked for, and "stack" adds no new words.
    plain = W.validate({"name": "x", "blocks": [{"type": "title", "text": "A"}]})
    big = W.validate({"name": "x", "layout": "big", "blocks": [
        {"type": "number", "source": "todo_count"}, {"type": "title", "text": "A"}]})
    check("the default sentence is unchanged",
          W.describe(plain) == "A widget called “x” showing the heading “A”.", W.describe(plain))
    check("a chosen arrangement is said in the sentence", "drawn large" in W.describe(big),
          W.describe(big))
    check("the preview's first line is the arrangement",
          W.parts(big)[0].startswith("Arranged:") and "large" in W.parts(big)[0], W.parts(big))
    check("every arrangement has preview words", set(W.LAYOUT_PARTS) == set(W.LAYOUTS))
    check("every arrangement has sentence words", set(W.LAYOUT_WORDS) == set(W.LAYOUTS))
    check("only the default adds nothing to the sentence",
          W.LAYOUT_WORDS[W.DEFAULT_LAYOUT] == ""
          and all(w for k, w in W.LAYOUT_WORDS.items() if k != W.DEFAULT_LAYOUT))
    # The model is told the list, and asked to choose from it.
    check("the schema offers exactly the four arrangements",
          W.SCHEMA["properties"]["layout"]["enum"] == list(W.LAYOUTS))
    check("the schema requires an arrangement", "layout" in W.SCHEMA["required"])
    check("the prompt offers each arrangement", all(k in W.prompt("x") for k in W.LAYOUTS))
    check("the prompt's answer shape carries a layout", '"layout": "..."' in W.prompt("x"))
    # It survives Add and a re-read of the file, and show() answers it.
    st = fresh_store()
    d = st.add_draft(W.validate({"name": "Desk", "layout": "list", "blocks": [
        {"type": "title", "text": "Hi"}]}))
    w, _ = st.keep(d["id"])
    check("a saved widget keeps its arrangement", w is not None and w["layout"] == "list", w)
    code, out = W.show(w["id"], st=st, readers=readers())
    check("show answers the arrangement", code == 200 and out["layout"] == "list",
          out.get("layout"))
    # A file written before 2026-10-30 has no key and must still read.
    old = json.loads(st.path.read_text("utf-8"))
    for row in old["widgets"]:
        row.pop("layout", None)
    st.path.write_text(json.dumps(old), "utf-8")
    check("a widget saved before 2026-10-30 reads as stack",
          [x["layout"] for x in st.widgets()] == ["stack"] * len(old["widgets"]))
    # A hand-edited one is checked again on read, like every other value.
    bad = json.loads(st.path.read_text("utf-8"))
    bad["widgets"][0]["layout"] = "grid"
    st.path.write_text(json.dumps(bad), "utf-8")
    check("a hand-edited arrangement off the list is not read",
          st.get(bad["widgets"][0]["id"]) is None)


def t_the_look_is_a_closed_list():
    """The look (2026-11-14): accent, shade and contrast are three CLOSED LISTS -
    absent means today's look, off the list is refused, and each one survives Add,
    the file and show(). Plus the rule that makes a list of colours safe to offer
    at all: every colour on it is LEGIBLE on both backgrounds, in both contrasts,
    measured here as WCAG AA (4.5:1) rather than eyeballed."""
    check("exactly the eight accents",
          list(W.ACCENTS) == ["cyan", "sky", "violet", "pink", "amber", "lime",
                              "orange", "mono"], list(W.ACCENTS))
    check("exactly the three shades", list(W.SHADES) == ["solid", "half", "clear"],
          list(W.SHADES))
    check("exactly the two contrasts", list(W.CONTRASTS) == ["normal", "high"],
          list(W.CONTRASTS))
    check("every accent carries a name and a hex",
          all(isinstance(v[0], str) and v[0] and len(v[1]) == 7 and v[1][0] == "#"
              for v in W.ACCENTS.values()), str(list(W.ACCENTS.values())[:2]))
    check("every shade carries a name and two alphas",
          all(isinstance(v[0], str) and v[0] and 0 <= v[2] <= v[1] <= 255
              for v in W.SHADES.values()), str(list(W.SHADES.values())))
    check("solid is the only wholly opaque shade and it is the default",
          [k for k, v in W.SHADES.items() if v[1] == 255] == ["solid"]
          and W.DEFAULT_SHADE == "solid")
    check("every contrast carries the four colours",
          all(set(v[1]) == {"bg", "surface", "text_hi", "text_muted"}
              for v in W.CONTRASTS.values()))

    # Absent = today's look, so every widget saved before today is unchanged.
    plain = W.validate({"name": "x", "blocks": [{"type": "title", "text": "a"}]})
    check("no look key means today's look",
          (plain["accent"], plain["shade"], plain["contrast"])
          == ("cyan", "solid", "normal"), str(plain))

    # Every value on every list is kept.
    for key, table in (("accent", W.ACCENTS), ("shade", W.SHADES),
                       ("contrast", W.CONTRASTS)):
        for value in table:
            got = W.validate({"name": "x", key: value,
                              "blocks": [{"type": "title", "text": "a"}]})[key]
            check(f"kept: the {key} {value!r}", got == value, got)

    # Off the list is refused, and a refusal names the reason - it is never a
    # quiet fall back to some other colour.
    for key in ("accent", "shade", "contrast"):
        for bad in ("Chartreuse", "chartreuse", "#BFA6FF", "", " ", "violet ",
                    " violet", "Violet", "grid", "<script>", None, True, False, 0, 3,
                    ["violet"], {"accent": "violet"}):
            why = refused({"name": "x", key: bad, "blocks": [{"type": "title", "text": "a"}]})
            check(f"refused: the {key} {bad!r}", bool(why), json.dumps(bad, default=str))
    # A look is not a place to smuggle styling, code or a second colour axis.
    for key in ("colour", "color", "colors", "hex", "alpha", "opacity", "transparency",
                "font", "fontsize", "size", "style", "grid", "theme", "image"):
        why = refused({**GOOD, key: "x"})
        check(f"refused: a {key!r} key", bool(why))

    # The preview sentence and its lines only mention what differs from today.
    looked = W.validate({"name": "x", "accent": "violet", "shade": "clear",
                         "contrast": "high",
                         "blocks": [{"type": "title", "text": "A"}]})
    check("the default sentence says nothing about a look",
          "cyan" not in W.describe(plain) and "solid" not in W.describe(plain)
          and "contrast" not in W.describe(plain), W.describe(plain))
    check("a chosen look is said in the sentence",
          "in violet" in W.describe(looked) and "See-through".lower() in W.describe(looked)
          and "high contrast" in W.describe(looked), W.describe(looked))
    check("the default preview has no look line",
          not any(p.startswith(("Colour:", "Background:", "Contrast:")) for p in W.parts(plain)))
    check("a chosen look has its own lines",
          W.parts(looked)[1].startswith("Colour: Violet")
          and W.parts(looked)[2].startswith("Background: See-through")
          and W.parts(looked)[3].startswith("Contrast: High contrast"), str(W.parts(looked)))
    # The look line comes FIRST among the look, right after the arrangement,
    # because both apps show at most MAX_BLOCKS lines and one added at the end
    # is the one that gets cut.
    check("the look lines sit directly after the arrangement",
          W.parts(looked)[0].startswith("Arranged:")
          and all(not p.startswith("Arranged:") for p in W.parts(looked)[1:]))

    # The model is offered the lists and is told to leave them alone otherwise.
    check("the schema offers exactly the eight accents",
          W.SCHEMA["properties"]["accent"]["enum"] == list(W.ACCENTS))
    check("the schema offers exactly the three shades",
          W.SCHEMA["properties"]["shade"]["enum"] == list(W.SHADES))
    check("the schema offers exactly the two contrasts",
          W.SCHEMA["properties"]["contrast"]["enum"] == list(W.CONTRASTS))
    check("the schema does not require a look, so a plain request gets none",
          not ({"accent", "shade", "contrast"} & set(W.SCHEMA["required"])))
    prompt = W.prompt("x")
    check("the prompt offers each accent", all(k in prompt for k in W.ACCENTS))
    check("the prompt says to leave the look out when none was asked for",
          "Leave all three out" in prompt)

    # It survives Add, the file, and a re-read of the file.
    st = fresh_store()
    d = st.add_draft(W.validate(dict(GOOD, accent="violet", shade="half", contrast="high")))
    w, _ = st.keep(d["id"])
    check("a saved widget keeps its look",
          w is not None and (w["accent"], w["shade"], w["contrast"]) == ("violet", "half", "high"),
          str(w and {k: w.get(k) for k in ("accent", "shade", "contrast")}))
    code, out = W.show(w["id"], st=st, readers=readers())
    check("show answers the look",
          code == 200 and (out["accent"], out["shade"], out["contrast"])
          == ("violet", "half", "high"), str(out.get("accent")))
    again = fresh_store()
    d2 = again.add_draft(W.validate(dict(GOOD, accent="amber")))
    w2, _ = again.keep(d2["id"])
    check("the look is on disk, not only in memory",
          [x["accent"] for x in W.Store(again.path).widgets()] == ["amber"],
          str([x["accent"] for x in W.Store(again.path).widgets()]))

    # A file written before 2026-11-14 has no keys and must still read.
    old = json.loads(again.path.read_text("utf-8"))
    for row in old["widgets"]:
        for key in ("accent", "shade", "contrast"):
            row.pop(key, None)
    again.path.write_text(json.dumps(old), "utf-8")
    read_back = again.widgets()
    check("a widget saved before 2026-11-14 reads in today's colours",
          [(x["accent"], x["shade"], x["contrast"]) for x in read_back]
          == [("cyan", "solid", "normal")] * len(old["widgets"]),
          str([(x["accent"], x["shade"], x["contrast"]) for x in read_back]))
    # A hand-edited one is checked again on read, like every other value.
    bad = json.loads(again.path.read_text("utf-8"))
    bad["widgets"][0]["accent"] = "chartreuse"
    again.path.write_text(json.dumps(bad), "utf-8")
    check("a hand-edited colour off the list is not read",
          again.get(bad["widgets"][0]["id"]) is None)

    # A DRAFT is readable through show too (2026-11-14): this is what lets the
    # phone's preview draw the real thing with real numbers, without a new route.
    st3 = fresh_store()
    d3 = st3.add_draft(W.validate(dict(GOOD, accent="pink", shade="clear")))
    code, preview = W.show(d3["id"], st=st3, readers=readers())
    check("show answers a draft id, for the live preview",
          code == 200 and preview["ok"] and preview["id"] == d3["id"], str(code))
    check("the draft preview carries its look and its blocks",
          (preview["accent"], preview["shade"]) == ("pink", "clear") and preview["blocks"],
          str(preview.get("accent")))
    check("reading a draft saves nothing", st3.widgets() == [])
    check("a widget id that does not exist is still 404",
          W.show("w0000000000", st=st3, readers=readers())[0] == 404)

    # The preview's own pickers may change the look before Add - and only to a
    # value on the list, or it is refused instead of quietly ignored.
    st4 = fresh_store()
    d4 = st4.add_draft(W.validate(dict(GOOD, accent="violet")))
    code, out = W.handle_post(W.ADD_PATH, {"draft": d4["id"], "accent": "amber",
                                           "contrast": "high"}, st=st4)
    check("Add takes the look the owner last chose", code == 200, str(code))
    saved = st4.widgets()
    check("the chosen look is what was saved",
          saved and (saved[0]["accent"], saved[0]["contrast"]) == ("amber", "high"),
          str(saved and {k: saved[0].get(k) for k in ("accent", "contrast")}))
    d5 = st4.add_draft(W.validate(GOOD))
    code, out = W.handle_post(W.ADD_PATH, {"draft": d5["id"], "shade": "frosted"}, st=st4)
    check("an off-list override is a 400 with a reason",
          code == 400 and out.get("ok") is False and out.get("error") == W.LOOK_REFUSED["shade"],
          f"{code} {out}")
    check("a refused override adds nothing", len(st4.widgets()) == 1)

    # The apps can build their pickers from the menu instead of hardcoding.
    menu = W.menu()
    check("the menu carries the eight accents with their names",
          [a["id"] for a in menu["look"]["accents"]] == list(W.ACCENTS)
          and menu["look"]["accents"][2]["label"] == "Violet", str(menu["look"]["accents"][:1]))
    check("the menu carries the shades and contrasts",
          [s["id"] for s in menu["look"]["shades"]] == list(W.SHADES)
          and [c["id"] for c in menu["look"]["contrasts"]] == list(W.CONTRASTS))
    check("the menu names today's look as the default",
          menu["look"]["default"] == {"accent": "cyan", "shade": "solid",
                                      "contrast": "normal"})

    # ---- and the one that makes a colour list safe: nothing is unreadable ----
    def _channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def _luminance(hexes):
        h = hexes.lstrip("#")
        return (0.2126 * _channel(int(h[0:2], 16)) + 0.7152 * _channel(int(h[2:4], 16))
                + 0.0722 * _channel(int(h[4:6], 16)))

    def _ratio(a, b):
        hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    worst = (99.0, "")
    for name, (_label, palette) in W.CONTRASTS.items():
        for colour in ("text_hi", "text_muted"):
            for ground in ("bg", "surface"):
                r = _ratio(palette[colour], palette[ground])
                worst = min(worst, (r, f"{name} {colour} on {ground}"))
                check(f"readable: {name} {colour} on {ground} (>= 4.5)",
                      r >= 4.5, f"{r:.2f}:1")
        for accent, (_alabel, ahex) in W.ACCENTS.items():
            for ground in ("bg", "surface"):
                r = _ratio(ahex, palette[ground])
                worst = min(worst, (r, f"{name} accent {accent} on {ground}"))
                check(f"readable: {name} accent {accent} on {ground} (>= 4.5)",
                      r >= 4.5, f"{r:.2f}:1")
    print(f"        (the least readable pair on the whole look: {worst[1]} at "
          f"{worst[0]:.2f}:1)")
    check("high contrast is not a paler version of normal",
          _ratio(W.CONTRASTS["high"][1]["text_hi"], W.CONTRASTS["high"][1]["bg"])
          >= _ratio(W.CONTRASTS["normal"][1]["text_hi"], W.CONTRASTS["normal"][1]["bg"]))


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
          out["draft"]["parts"] == ["Arranged: everything stacked, in the order given",
                                    "Heading: Good morning",
                                    "List: Next up - your next reminders and alarms, up to 3",
                                    "Number: To do - how many things are on your to-do list",
                                    "Bar: Disk free - the free space on your PC's main drive",
                                    "Button: 10-min timer"], out["draft"]["parts"])
    check("the draft keeps no words, only the checked widget",
          set(st.drafts()[0]) == {"id", "name", "layout", "accent", "shade", "contrast",
                                  "blocks", "expires"},
          str(set(st.drafts()[0])))
    # ... and "no words" is the point, not the key count: the owner's sentence
    # itself is in none of them, whatever keys the look added on 2026-11-14.
    check("the draft keeps none of the owner's own words",
          words not in json.dumps(st.drafts()[0]), words)


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
        skip("the apps' widget cases: tools/gen_widget_cases.py is not in this checkout, "
             "so the two apps' copies cannot be compared with what the backend makes today")
        return
    r = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
    check("the apps' widget cases are up to date", r.returncode == 0, r.stdout + r.stderr)


if __name__ == "__main__":
    for fn in (t_the_apps_cases_are_up_to_date, t_on_the_menu_is_kept, t_off_the_menu_is_refused, t_the_buttons_are_the_tile_actions,
               t_text_is_cleaned, t_raw_json_is_strict, t_the_arrangement_is_a_closed_list,
               t_the_look_is_a_closed_list,
               t_drafts_from_own_words_only,
               t_the_model_is_asked_only_on_this_pc, t_the_store, t_filling_in, t_chat, t_routes):
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
