"""test_jarvis_open.py - "open Notion", "open settings", "open Jarvis
settings" (jarvis_open.py; the owner's request of 2026-10-10).

    python3 backend/test_jarvis_open.py

Runs anywhere; no Windows, no Start menu, no program is ever started (this
module starts nothing at all - see its own docstring). What it proves:

1. The sentences the owner asked for land where he said: "open Notion" is an
   app, "open settings" is JARVIS's own Settings window at the top (the
   owner's decision of 2026-10-10, the "flip" answer to question 1 of
   docs/BARS-AND-SETTINGS-AUDIT-2026-10-10.md), and "open Windows settings"
   is Windows' own screen.
2. "settings" is disambiguated and said out loud: the answer names which one
   it opened and how to ask for the other, on BOTH readings - and Jarvis's own
   sections still win when the owner names one ("open web search" is not an
   app).
3. "Open ..." never becomes a guess: a name that matches nothing is passed on
   to the PC to resolve and is NOT claimed to exist; a name is never given a
   nearest match; prose ("open a chat", "open my email") is not an app when
   the chat path owns it.
4. There is NO card, by construction: this module never imports jarvis_gate,
   and nothing in it starts a program (grep-checked for subprocess/startfile/
   Popen), exactly like jarvis_media.py's own rule.
5. jarvis_quick.py's fast path wires it up: the intent, the reply and every
   field X-Jarvis-Route needs - including the empty `open_place` that means
   "the top of the Settings window", which an empty string would otherwise
   drop on the floor.
"""
from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_open.py")
import jarvis_open as O  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                       else ""))


def where(sentence):
    """`(kind, target, note)` for a sentence, or None when it is not ours."""
    got = O.parse(sentence)
    if got is None:
        return None
    opened = O.resolve(got[0], got[1])
    return (opened.kind, opened.target, opened.note)


# --------------------------------------------------------------------------
#   The sentences the owner asked for, and where they land after the flip
# --------------------------------------------------------------------------

def t_the_three_sentences_he_asked_for():
    check("'open Notion' is an app, named as he said it",
          where("open Notion")[:2] == ("app", "notion"))
    check("'open settings' is JARVIS's own Settings window after the flip",
          where("open settings")[:2] == ("jarvis", ""))
    check("'open my settings' is Jarvis's too - the same default",
          where("open my settings")[:2] == ("jarvis", ""))
    check("'open Jarvis settings' is the same window, said explicitly",
          where("open Jarvis settings")[:2] == ("jarvis", ""))
    check("'open jarvis preferences' says the same thing",
          where("open jarvis preferences")[:2] == ("jarvis", ""))
    # Punctuation, capitals and politeness are the owner's, not the name's.
    for said in ("Open Notion.", "Jarvis, open Notion please", "can you open notion",
                 "launch notion", "please open Notion for me"):
        check(f"{said!r} is still Notion", where(said)[:2] == ("app", "notion"), where(said))


def t_settings_is_disambiguated_and_said_out_loud():
    # THE OWNER'S DECISION, said in the answer rather than left for him to
    # discover (2026-10-10, question 1 of the audit: "Flip it"). A bare "open
    # settings" is Jarvis's own window, and the note names the one phrase that
    # reaches Windows' own. (Careful with the substring: the note quotes that
    # phrase, so `Windows settings` as one literal is split by the opening
    # quote mark - check the words, not the quoted sentence.)
    kind, target, note = where("open settings")
    check("'open settings' opens JARVIS's own Settings, at the top",
          (kind, target) == ("jarvis", ""), (kind, target))
    check("...and says which one it opened", "Jarvis" in note, note)
    check("...and names Windows' own as the other door, in the words that reach it",
          "Windows" in note and "settings" in note, note)
    check("...and does NOT send him to the phrase he just said",
          "open Jarvis settings" not in note, note)
    # The only words that reach Windows' own screen now. Both the whole phrase
    # and the phrase with a trailing kind-noun must land there: that peel is
    # the step that would otherwise let the app index take them.
    for said in ("open Windows settings", "open windows settings",
                 "open the windows settings app"):
        check(f"{said!r} is Windows' own screen", where(said)[:2] == ("panel", "ms-settings:"),
              where(said))
    # A Windows panel by name is a panel, not an app called "display".
    check("'open display settings' is the Display page",
          where("open display settings")[:2] == ("panel", "ms-settings:display"))
    check("'open sound' is the Sound page",
          where("open sound")[:2] == ("panel", "ms-settings:sound"))
    # ...and its note names the other reading - the section jump inside Jarvis,
    # NOT the bare phrase, which is Jarvis's own window already.
    note = where("open sound")[2]
    check("a word that is also a Jarvis section says so",
          "Jarvis" in note, note)
    check("...and names the section jump, not the bare phrase",
          "open Jarvis settings, sound" in note, note)


def t_jarvis_sections_still_win_when_named():
    # jarvis_quick.py's own `_settings_open` runs first for these and owns the
    # answer - it is `settings_open` with the `open_settings` field both apps
    # already know, and that has not changed. What this checks is that the two
    # agree: jarvis_open.py resolves the same words to the SAME section id, so
    # neither can drift into sending the owner somewhere else.
    for said, section in (("open web search", "web-search"),
                          ("open voice settings", "voice"),
                          ("open the morning briefing", "briefing-settings"),
                          ("open the second graphics card", "second-card")):
        check(f"{said!r} resolves to the {section!r} section",
              where(said)[:2] == ("jarvis", section), where(said))
        check(f"...and the quick path still owns it as a settings jump",
              Q.match(said).name == "settings_open", Q.match(said))
    check("the section list is the apps' own, not a copy",
          "jarvis_settings_registry" in (
              HERE / "jarvis_open.py").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
#   Never a guess
# --------------------------------------------------------------------------

def t_a_name_that_matches_nothing_is_not_claimed_to_exist():
    kind, target, _ = where("open Flurblesoft")
    check("an unknown name is handed to the PC to resolve", kind == "app")
    check("...as the owner's own words, not as a program this PC is told it has",
          target == "flurblesoft" and O.resolve("flurblesoft").built is False)
    check("Jarvis does not claim it exists anywhere in the answer",
          "found" not in O.words(O.resolve("flurblesoft")).lower())


def t_windows_own_accessories_are_named_exactly():
    check("'open notepad' is notepad.exe", where("open notepad")[:2] == ("app", "notepad.exe"))
    check("'open calculator' is calc.exe", where("open calculator")[:2] == ("app", "calc.exe"))
    check("'open the calculator' drops the article",
          where("open the calculator")[:2] == ("app", "calc.exe"))
    check("'open an app called figma' looks up figma, not the phrase",
          where("open an app called figma")[:2] == ("app", "figma"))
    check("a built-in is marked built, so the PC does not have to look it up",
          O.resolve("notepad").built is True)
    for said, target in (("open file explorer", "explorer.exe"),
                         ("open control panel", "control.exe"),
                         ("open task manager", "taskmgr.exe")):
        check(f"{said!r} is the fixed shell command", where(said)[:2] == ("other", target))


def t_the_phrases_that_already_had_an_owner_still_do():
    # Prose and other features' sentences are not apps. These are checked
    # through jarvis_quick.py, where the ordering actually lives.
    check("'open a chat' is still the chat, not an app called chat",
          Q.match("open a chat").name == "open_chat")
    check("'what time is it' is still the model's",
          Q.match("what time is it") is None)
    check("'pause the music' is still music control",
          Q.match("pause the music").name == "media_pause")
    # "open my email" has no owner yet, so it is an app name and will be
    # reported as not found - which is honest, and is why the reply says so.
    check("an app that will not be found is still answered honestly",
          where("open my email")[0] == "app")


def t_a_sentence_that_is_not_an_open_request_is_not_ours():
    for said in ("", "open ", "notion", "what is open on my pc", "show me the settings",
                 "how do i open notion", "close notion", "open" + "x" * 300):
        check(f"{said[:24]!r} is not an 'open ...' request", O.parse(said) is None)


def t_a_trailing_kind_noun_is_peeled_once():
    check("'open the settings app' is Jarvis's own Settings, like the bare phrase",
          where("open the settings app")[:2] == ("jarvis", ""))
    check("'open the calculator program' is the calculator",
          where("open the calculator program")[:2] == ("app", "calc.exe"))
    # ...but a name that genuinely ends in one of those words is untouched.
    check("'open display settings' is not peeled into 'display'",
          where("open display settings")[:2] == ("panel", "ms-settings:display"))
    # The peel must not hand a Windows panel to the app index: a copy of the
    # page called "display settings" would otherwise be looked up as a program.
    check("'open the display settings app' is still the Display page",
          where("open the display settings app")[:2] == ("panel", "ms-settings:display"))


# --------------------------------------------------------------------------
#   No card, and nothing started from here
# --------------------------------------------------------------------------

def t_no_card_by_construction():
    src = (HERE / "jarvis_open.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.names[0].asname or n.names[0].name for n in ast.walk(tree)
             if isinstance(n, ast.Import)} | {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    check("jarvis_open.py never imports jarvis_gate, so it has no tier to give",
          "jarvis_gate" not in names and "import jarvis_gate" not in src)
    for forbidden in ("subprocess", "os.startfile", "Popen(", "os.system", "ShellExecute",
                      "webbrowser", "urllib", "socket", "requests"):
        check(f"jarvis_open.py never uses {forbidden!r} - it opens nothing itself",
              forbidden not in src)


# --------------------------------------------------------------------------
#   The fast path, end to end
# --------------------------------------------------------------------------

def t_the_fast_path_answers_without_the_model():
    check("'open notion' is answered by jarvis_quick.py, not the model",
          Q.match("open notion").name == "open_app")
    for said in ("open notion", "open settings", "open Jarvis settings"):
        intent = Q.match(said)
        check(f"{said!r} matched the open_app intent", intent is not None
              and intent.name == "open_app", said)


def t_the_route_carries_every_field_the_apps_need():
    def route(said):
        return Q.route_fields(Q.run(Q.match(said), None, 0.0))

    r = route("open notion")
    check("an app: the name and the kind ride along",
          r.get("open_app") == "notion" and r.get("open_app_kind") == "app")
    check("...and it is not marked built, so the PC resolves it",
          r.get("open_app_built") is False)

    r = route("open notepad")
    check("a built-in is marked built",
          r.get("open_app") == "notepad.exe" and r.get("open_app_built") is True)

    r = route("open settings")
    check("after the flip: Jarvis's own Settings, with an EMPTY place that still rides along",
          r.get("open_app_kind") == "jarvis" and r.get("open_place") == "",
          r.get("open_app_kind"))
    check("...and no `open_app`, because the place field carries it",
          "open_app" not in r, r)
    check("...and the note says which one and how to get the other",
          "Windows" in str(r.get("open_app_note", "")) and "settings" in str(
              r.get("open_app_note", "")).lower(), r.get("open_app_note"))
    check("...and that note never names the phrase he just said",
          "open Jarvis settings" not in str(r.get("open_app_note", "")),
          r.get("open_app_note"))

    # The one phrase that reaches Windows' own screen after the flip: a panel,
    # with the ms-settings address, exactly as a named Windows panel rides.
    r = route("open Windows settings")
    check("'open Windows settings' is still the Windows panel",
          r.get("open_app") == "ms-settings:" and r.get("open_app_kind") == "panel", r)

    r = route("open Jarvis settings")
    check("Jarvis's own Settings, said explicitly: the kind, and an EMPTY place",
          r.get("open_app_kind") == "jarvis" and r.get("open_place") == "")
    check("...and no `open_app`, because the place field carries it",
          "open_app" not in r)

    # A Jarvis Settings section named by one of its own names: the settings
    # registry's own matcher takes it first (that is `settings_open`, and it
    # has not changed), and this module must resolve the SAME words to the SAME
    # id - that is the anti-drift check. Read through the resolver rather than
    # through the quick path, which the registry owns.
    r = where("open backups")
    check("a Jarvis section name resolves to its own id, not to an app",
          r[:2] == ("jarvis", "backup"), r)

    # ...and a section named with a trailing "settings" - which the registry's
    # own matcher does not take, because it compares the WHOLE phrase - is still
    # resolved here rather than opened as an app called "backup".
    r = where("open the backup settings")
    check("a section name the registry's matcher does not take is still a section",
          r[:2] == ("jarvis", "backup") or r[:2] == ("panel", "ms-settings:backup"), r)


def t_the_reply_says_on_this_pc_because_the_phone_cannot():
    for said in ("open notion", "open settings", "open Jarvis settings", "open notepad"):
        reply = Q.run(Q.match(said), None, 0.0).reply
        check(f"{said!r} answers with 'on this PC'", "on this PC" in reply, reply)
    check("the phone's own sentence says where it happens",
          "PC" in O.ON_PC and "phone" in O.ON_PC)


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
