"""test_active_selection.py - Pillar 24-A: reading the owner's highlighted text

    python -B backend/test_active_selection.py

What this proves, with NO desktop, NO owner's window and NO real UI Automation
call: `jarvis_ui_control.read_selection()` returns the selected text, the
program's name and whether the project's scrubber changed anything - and it
refuses in plain words when there is no selection, the program is one Jarvis
never reads (the owner's Never look at list, a private browser window, a
password box, the lock screen, Jarvis's own windows, capture protection), the
scrubber is not available, or the platform cannot read the selection.

The privacy rules are the EXISTING ones, not a second copy: these checks run
the REAL `jarvis_screen.pause_reason()`/`NeverLook` and (for the secret check)
the REAL `jarvis_scrub.scrub_text`, and only the window in front and the text
itself are injected. A refused window's selection is never even read: the
reader spy proves zero calls.

Everything here is a seam test: the module is driven, the injected fakes record
what they were asked, and no production source text is pinned (the pin ratchets
stay at zero).

A note that is honest rather than a promise: whether a given program exposes
its selection through Windows UI Automation, and how fast, is measured on the
owner's PC. This suite proves the Python contract, not the desktop.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_ui_control.py", "jarvis_screen.py", "jarvis_scrub.py")

#: A scratch settings folder, so the REAL "Never look at" list is the built-in
#: one (password managers, private banks, streaming sites) and not the owner's.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-selection-suite-"))
CONFIG = TMP / "config"
CONFIG.mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["JARVIS_CONFIG_DIR"] = str(CONFIG)

import jarvis_scrub as SCRUB  # noqa: E402
import jarvis_screen as S  # noqa: E402
import jarvis_ui_control as U  # noqa: E402

PASSED, SKIPPED, FAILED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: its own line, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The three fakes and the one real snapshot
# --------------------------------------------------------------------------

def front(**over):
    """A `jarvis_screen.pause_reason` snapshot of an ordinary, allowed window."""
    snap = {"exe": "notepad.exe", "title": "notes.txt - Notepad", "cls": "Notepad",
            "host": "", "hwnd": 1, "locked": False,
            "capture_protected": False, "password_focused": False}
    snap.update(over)
    return snap


class Reader:
    """The injected text reader: records every call, returns or raises."""

    def __init__(self, value="", exc=None):
        self.value, self.exc, self.calls = value, exc, []

    def __call__(self):
        self.calls.append(1)
        if self.exc is not None:
            raise self.exc
        return self.value


class Scrubber:
    def __init__(self, value=None, exc=None):
        self.value, self.exc, self.calls = value, exc, []

    def __call__(self, text):
        self.calls.append(text)
        if self.exc is not None:
            raise self.exc
        return text if self.value is None else self.value


class Never:
    """A stand-in for jarvis_screen.NeverLook: same three questions."""

    def __init__(self, broken=False, programs=(), sites=()):
        self.broken = broken
        self.programs = {str(p).lower() for p in programs}
        self.sites = {str(s).lower() for s in sites}

    def has_program(self, exe):
        return str(exe or "").rsplit("\\", 1)[-1].lower() in self.programs

    def has_site(self, site):
        site = str(site or "").lower()
        return any(site == s or site.endswith("." + s) for s in self.sites)

    def holds_sites(self):
        return bool(self.sites)


def identity(text):
    return text


def never_list(name="never.json"):
    """A REAL jarvis_screen.NeverLook over a scratch file (built-in entries only)."""
    return S.NeverLook(path=CONFIG / name)


def refuse(result, why):
    return (isinstance(result, dict) and result.get("ok") is False
            and result.get("refused") is True and result.get("why") == why
            and result.get("text") == "" and result.get("chars") == 0)


# --------------------------------------------------------------------------
#   1. The allowed path
# --------------------------------------------------------------------------

def t_the_selected_text_is_returned():
    reader = Reader("the selected words")
    result = U.read_selection(front=front(), selection=reader, never=never_list(),
                              scrubber=identity)
    check("an ordinary window returns its selected text", result.get("ok") is True, result)
    check("the text is exactly what the reader returned",
          result.get("text") == "the selected words", result.get("text"))
    check("the program is named, and it is not the window's title",
          result.get("app") == "notepad", result.get("app"))
    check("nothing was scrubbed, and the marker says so", result.get("scrubbed") is False)
    check("the text was not cut, and the marker says so", result.get("truncated") is False)
    check("the character count is the returned text's own",
          result.get("chars") == len("the selected words"), result.get("chars"))
    check("the reader was asked exactly once", reader.calls == [1], reader.calls)
    check("the answer has the documented keys",
          set(result) == {"ok", "refused", "why", "text", "app", "chars",
                          "truncated", "scrubbed", "words"}, sorted(result))
    check("the words say what was read, in plain English",
          "Read the highlighted text" in str(result.get("words")), result.get("words"))

    snap = front(exe=r"C:\Apps\Excel.exe", title="Secret budget.xlsx - Excel")
    result = U.read_selection(front=lambda: snap, selection=Reader("42"),
                              never=never_list(), scrubber=identity)
    check("the app is the program's name, not its path",
          result.get("app") == "Excel", result.get("app"))
    check("the window's TITLE never reaches the answer (it can hold private words)",
          "Secret budget.xlsx" not in json.dumps(result), json.dumps(result))


def t_no_selection_is_a_plain_refusal():
    for value in ("", "   ", "\n\t "):
        result = U.read_selection(front=front(), selection=Reader(value),
                                  never=never_list(), scrubber=identity)
        check(f"a selection of {value!r} is refused as no selection",
              refuse(result, "no_selection") and "no highlighted text" in
              str(result.get("words")).lower(), result)


def t_long_selection_is_cut_and_said_so():
    reader = Reader("a" * (U.MAX_SELECTION_CHARS + 2000))
    result = U.read_selection(front=front(), selection=reader, never=never_list(),
                              scrubber=identity)
    check("a very long selection is cut to MAX_SELECTION_CHARS",
          result.get("ok") is True and len(result.get("text", "")) == U.MAX_SELECTION_CHARS,
          len(result.get("text", "")))
    check("the answer marks the cut", result.get("truncated") is True, result.get("truncated"))
    check("... and says so out loud", "Only the first part" in str(result.get("words")),
          result.get("words"))


# --------------------------------------------------------------------------
#   2. The excluded windows: nothing is read, and the reader is never called
# --------------------------------------------------------------------------

def t_excluded_windows_are_refused_before_anything_is_read():
    cases = [
        ("a password manager (the built-in list)",
         front(exe="KeePass.exe", title="KeePass"), "never_look", never_list()),
        ("a bank program the owner added",
         front(exe="MyBank.exe"), "never_look",
         Never(programs=("mybank.exe",))),
        ("a bank site the owner added",
         front(exe="chrome.exe", title="Bank - Google Chrome",
               host="https://www.mybank.com/login"), "never_look",
         Never(sites=("mybank.com",))),
        ("a private browser window",
         front(exe="chrome.exe", title="Shopping - Incognito",
               host="https://example.com/"), "private_window", never_list()),
        ("a password box in front",
         front(password_focused=True), "password_box", never_list()),
        ("the lock screen", front(locked=True), "lock_screen", never_list()),
        ("one of Jarvis's own windows",
         front(title="Jarvis", cls="WebView2"), "jarvis", never_list()),
        ("a window that asks not to be captured",
         front(capture_protected=True), "protected", never_list()),
        ("a Never look at list that cannot be read",
         front(), "list_unreadable", Never(broken=True)),
    ]
    for label, snap, why, never in cases:
        reader = Reader("THE OWNER'S PRIVATE WORDS")
        result = U.read_selection(front=snap, selection=reader, never=never,
                                  scrubber=identity)
        check(f"{label}: refused as {why}", refuse(result, why), result)
        check(f"{label}: the selection reader was NEVER called",
              reader.calls == [], reader.calls)
        check(f"{label}: not one word of the selection is in the answer",
              "PRIVATE WORDS" not in json.dumps(result), json.dumps(result)[:200])
        check(f"{label}: the words are a full plain sentence",
              isinstance(result.get("words"), str) and len(result["words"]) > 20
              and result["words"].endswith("."), result.get("words"))


def t_no_window_at_all_is_a_plain_refusal():
    result = U.read_selection(front=lambda: None, selection=Reader("x"),
                              never=never_list(), scrubber=identity)
    check("no readable window in front is a plain refusal, not a crash",
          refuse(result, "cannot_read") and "could not be read" in result.get("words", ""),
          result)


# --------------------------------------------------------------------------
#   3. The scrubber: the project's own, and it fails closed
# --------------------------------------------------------------------------

def t_the_default_scrubber_is_the_project_s_own():
    check("the default scrubber IS jarvis_scrub.scrub_text - not a copy",
          U._default_scrubber() is SCRUB.scrub_text)


def t_a_secret_is_scrubbed_by_the_real_scrubber():
    text = ("before the key\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu\n"
            "-----END RSA PRIVATE KEY-----\n"
            "after the key this sentence stays.\n")
    result = U.read_selection(front=front(), selection=Reader(text),
                              never=never_list())  # the REAL scrubber
    check("a selection with a key in it succeeds", result.get("ok") is True, result)
    check("the answer marks that it was scrubbed", result.get("scrubbed") is True,
          result.get("scrubbed"))
    check("the key's body is NOT in the returned text",
          "MIIBOgIBAAJBAK" not in result.get("text", ""), result.get("text", "")[:120])
    check("the harmless words around it are still there",
          "before the key" in result.get("text", "")
          and "after the key this sentence stays." in result.get("text", ""),
          result.get("text", "")[:200])


def t_a_selection_that_is_all_secret_is_refused():
    result = U.read_selection(front=front(), selection=Reader("sk-live-ABCDEF123456"),
                              never=never_list(), scrubber=Scrubber(value=""))
    check("a selection that is nothing but a secret is refused as a secret",
          refuse(result, "secret") and "secret" in result.get("words", "").lower(), result)


def t_a_missing_or_broken_scrubber_fails_closed():
    real = U._default_scrubber
    U._default_scrubber = lambda: None
    try:
        result = U.read_selection(front=front(), selection=Reader("some words"),
                                  never=never_list())
    finally:
        U._default_scrubber = real
    check("no scrubber at all: refused, nothing returned (fail closed)",
          refuse(result, "scrubber"), result)

    result = U.read_selection(front=front(), selection=Reader("some words"),
                              never=never_list(), scrubber=Scrubber(exc=RuntimeError("x")))
    check("a scrubber that raises: refused, nothing returned", refuse(result, "scrubber"), result)


def t_a_reader_failure_is_plain():
    result = U.read_selection(front=front(), selection=Reader(exc=RuntimeError("no tree")),
                              never=never_list(), scrubber=identity)
    check("a reader that raises is a plain refusal, not a traceback",
          refuse(result, "cannot_read") and "RuntimeError" in result.get("words", ""), result)


# --------------------------------------------------------------------------
#   4. Nothing is persisted, and the real UIA path still loads
# --------------------------------------------------------------------------

def t_nothing_is_persisted():
    before = sorted(str(p.relative_to(TMP)) for p in TMP.rglob("*") if p.is_file())
    result = U.read_selection(front=front(), selection=Reader("CANARY-24-A-WORDS"),
                              never=never_list("persist.json"), scrubber=identity)
    after = sorted(str(p.relative_to(TMP)) for p in TMP.rglob("*") if p.is_file())
    check("the allowed read succeeds", result.get("ok") is True, result)
    check("no file was created or changed by the read", before == after,
          (before, after))
    hit = [p for p in TMP.rglob("*") if p.is_file()
           and "CANARY-24-A-WORDS" in p.read_text(encoding="utf-8", errors="replace")]
    check("the selected text was not written into any file under the settings folder",
          hit == [], hit)
    check("the answer carries no path or saved marker", not any(
        k in result for k in ("path", "file", "saved_path")), sorted(result))


def t_the_real_uia_library_has_the_selection_api():
    try:
        auto = U._uia_lib()
    except Exception as exc:
        skip(f"the real uiautomation package is not installed here "
             f"({type(exc).__name__}), so the real reader's API cannot be checked")
        return
    check("the real UIA library is importable on this machine",
          auto is not None)
    check("it has the two calls the reader uses (GetFocusedControl, TextPattern)",
          callable(getattr(auto, "GetFocusedControl", None))
          and getattr(getattr(auto, "PatternId", None), "TextPattern", None) is not None)
    check("the default selection reader is a real callable, never run by this suite",
          callable(U._default_selection_text) and callable(U._default_front_snapshot))
    check("the focused control's top-level window can be walked (the identity proof)",
          hasattr(auto.Control, "GetTopLevelControl")
          and callable(U._default_focused_window))


# --------------------------------------------------------------------------
#   4. The text must come from the window whose pause rules passed (S-2)
# --------------------------------------------------------------------------


def t_a_control_from_another_window_returns_no_text():
    snap = {"exe": "notepad.exe", "title": "notes", "cls": "Notepad", "host": "",
            "hwnd": 4321, "locked": False, "password_focused": False,
            "capture_protected": False}
    reader = Reader("words from somewhere else")
    result = U.read_selection(front=snap, selection=reader, never=never_list(),
                              scrubber=identity, window=lambda: {"hwnd": 9999})
    check("a focused control in ANOTHER top-level window is refused",
          result.get("ok") is False and result.get("refused") is True
          and result.get("why") == "window_changed", result)
    check("... and not one character of that other window's text is returned",
          result.get("text") == "" and "words from somewhere else" not in result.get("words", ""),
          result)
    check("... the read happened (the refusal is the PROOF, not a skipped read)",
          reader.calls == [1], reader.calls)


def t_a_matching_focused_window_still_returns_text():
    snap = {"exe": "notepad.exe", "title": "notes", "cls": "Notepad", "host": "",
            "hwnd": 7, "locked": False, "password_focused": False,
            "capture_protected": False}
    result = U.read_selection(front=snap, selection=Reader("same window words"),
                              never=never_list(), scrubber=identity,
                              window=lambda: {"hwnd": 7})
    check("the same window passes the identity proof and returns its text",
          result.get("ok") is True and result.get("text") == "same window words", result)


def t_a_window_that_changes_during_the_read_returns_nothing():
    first = {"exe": "notepad.exe", "title": "notes", "cls": "Notepad", "host": "",
             "hwnd": 11, "locked": False, "password_focused": False,
             "capture_protected": False}
    second = {"exe": "chrome.exe", "title": "Bank - Chrome", "cls": "Chrome_WidgetWin_1",
              "host": "mybank.example", "hwnd": 22, "locked": False,
              "password_focused": False, "capture_protected": False}
    seen = []

    def changing_front():
        seen.append(1)
        return first if len(seen) == 1 else second

    result = U.read_selection(front=changing_front, selection=Reader("bank words"),
                              never=never_list(), scrubber=identity)
    check("the front window changing between the check and the read is refused",
          result.get("ok") is False and result.get("why") == "window_changed", result)
    check("... with no text from the second window",
          result.get("text") == "" and "bank words" not in json.dumps(result), result)
    check("... and the front was really read twice (once before, once after)",
          len(seen) == 2, seen)


def t_reading_the_selection_is_not_writing_anything_else():
    # Defence in depth: a selection read must not be a way to change a setting,
    # hold a card or change the taint latch. The injected fakes make any call
    # to such a helper impossible; this pins the module surface instead.
    check("read_selection takes only the five injectable seams",
          list(U.read_selection.__kwdefaults__ or {})
          == ["front", "selection", "never", "scrubber", "window"],
          U.read_selection.__kwdefaults__)
    check("... and is keyword-only (no accidental positional bypass)",
          all(p.kind is p.KEYWORD_ONLY for p in
              __import__("inspect").signature(U.read_selection).parameters.values()),
          [(p.name, str(p.kind)) for p in
           __import__("inspect").signature(U.read_selection).parameters.values()])


if __name__ == "__main__":
    TESTS = (t_the_selected_text_is_returned, t_no_selection_is_a_plain_refusal,
             t_long_selection_is_cut_and_said_so,
             t_excluded_windows_are_refused_before_anything_is_read,
             t_no_window_at_all_is_a_plain_refusal,
             t_the_default_scrubber_is_the_project_s_own,
             t_a_secret_is_scrubbed_by_the_real_scrubber,
             t_a_selection_that_is_all_secret_is_refused,
             t_a_missing_or_broken_scrubber_fails_closed, t_a_reader_failure_is_plain,
             t_nothing_is_persisted, t_the_real_uia_library_has_the_selection_api,
             t_reading_the_selection_is_not_writing_anything_else,
             t_a_control_from_another_window_returns_no_text,
             t_a_matching_focused_window_still_returns_text,
             t_a_window_that_changes_during_the_read_returns_nothing)
    try:
        for fn in TESTS:
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
