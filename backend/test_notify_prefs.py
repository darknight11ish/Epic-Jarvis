"""test_notify_prefs.py - this PC's own notification choices, in the owner's
settings file.

    python3 backend/test_notify_prefs.py

Runs anywhere; no model, no network, no gate.

WHAT THIS PROVES, and why each one is here. The owner's decision of 2026-10-08
moved the PC's notification choices (which of ITS toasts fire, and the quiet
hours around them) out of the desktop app's own `localStorage` and into
`[notifications]` in the owner's `jarvis-framework.toml`, so that the phone can
change them too. Four things have to hold for that to be worth anything:

1. **The defaults are the ones the desktop already used** - the four toggles
   ON, quiet hours OFF, 22:00 to 07:00 - and a settings file with no
   `[notifications]` table at all reads exactly as those defaults. An owner who
   never touches a switch must see no change at all.
2. **Nonsense is refused in plain words and nothing is written.** A time of day
   is the new shape: "7:05" is accepted and normalised, while 1320, "25:00",
   "7:5" and "" are refused with the shape that IS wanted. The rule the brief
   states - never render a time as a bare number of minutes with no
   explanation - starts here, because a bare 1320 is exactly what a looser
   check would have stored.
3. **A round trip through the real file.** One change moves ONE line, comments
   and CRLF endings survive, and what `read()` reports afterwards is what both
   apps will draw. A key the file lacks is added inside the section; a section
   the file lacks is created.
4. **Nothing is logged.** Not a value, not a path, not a refusal. Two of the
   seven are a window around the owner's own day, and one of them beside a
   toast time says when the owner is asleep, so the module writes no log line
   of any kind - proved by capturing stdout AND stderr AND the module's own
   logger for a whole successful write and a whole refusal.
"""
from __future__ import annotations

import contextlib
import io
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notify_prefs.py", "jarvis_framework.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-notify-prefs-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)

SHIPPED = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"

import jarvis_notify_prefs as N  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh(text: str = None) -> Path:
    p = TMP / "jarvis-framework.toml"
    if text is None:
        shutil.copyfile(SHIPPED, p)
    else:
        # write_bytes, not write_text: on Windows write_text turns the "\n" in a
        # CRLF sample into another CRLF, and the test would be measuring its own
        # translation rather than the writer's.
        p.write_bytes(text.encode("utf-8"))
    import jarvis_framework as fw
    fw.reload_framework()
    return p


# --------------------------------------------------------------------------
#   1. The defaults
# --------------------------------------------------------------------------
def t_defaults_are_what_the_desktop_already_did():
    """The desktop's own `notifications-prefs.js` defaults, matched one by one.
    Nothing here may change behaviour for an owner who never opens the card."""
    check("the four switches default ON",
          [N.DEFAULTS[k] for k in ("alarms", "reminders", "briefing", "handoff")]
          == [True, True, True, True], N.DEFAULTS)
    check("quiet hours default OFF", N.DEFAULTS["quiet_enabled"] is False)
    check("the window defaults to 22:00 to 07:00",
          N.DEFAULTS["quiet_start"] == "22:00" and N.DEFAULTS["quiet_end"] == "07:00",
          N.DEFAULTS)
    check("the shipped settings file carries every one of the seven, with the "
          "defaults",
          _shipped_section() == N.DEFAULTS, _shipped_section())
    check("the seven keys are the five switches and the two times, in that order",
          N.KEYS == ("alarms", "reminders", "briefing", "handoff",
                     "quiet_enabled", "quiet_start", "quiet_end"), N.KEYS)


def _shipped_section() -> dict:
    import tomllib
    return tomllib.loads(SHIPPED.read_text(encoding="utf-8"))["notifications"]


def t_a_file_with_no_section_reads_as_the_defaults():
    """The case that matters most: an owner whose settings file was written
    before this module existed. A missing table must be the defaults, never
    "no choices" - which would be quiet hours off and every switch read as
    whatever a client guessed."""
    fresh("# nothing but a comment\n[undo]\nttl_hours = 24\n")
    check("a file with no [notifications] table reads as the defaults",
          N.read() == N.DEFAULTS, N.read())
    fresh("[notifications]\nalarms = false\n")
    got = N.read()
    check("a partial table keeps what it says and defaults the rest",
          got["alarms"] is False and got["reminders"] is True
          and got["quiet_start"] == "22:00", got)
    fresh("[notifications]\nalarms = maybe\nquiet_start = \"half past ten\"\n")
    got = N.read()
    check("a nonsense value in a hand-edited file reads as its default rather "
          "than as something no screen can draw",
          got["alarms"] is True and got["quiet_start"] == "22:00", got)
    check("and a nonsense value never means 'go quiet by accident'",
          got["briefing"] is True and got["handoff"] is True, got)


# --------------------------------------------------------------------------
#   2. Nonsense refused, in plain words, writing nothing
# --------------------------------------------------------------------------
def t_a_time_of_day_is_checked_and_never_a_bare_number():
    """The one shape a number cannot express. 1320 must be REFUSED, not stored:
    rendering it as "1320" with no explanation is the outcome the brief names
    as worse than leaving the row out."""
    for good, want in (("22:00", "22:00"), ("07:00", "07:00"), ("00:00", "00:00"),
                       ("23:59", "23:59"), ("7:05", "07:05"), ("7:5", None),
                       ("22:0", None)):
        try:
            got = N.check_time(good)
        except N.PrefsError:
            got = None
        check(f"a time {good!r} is read as {want!r}", got == want, got)
    for bad in (1320, "1320", "25:00", "24:00", "22:60", "-1:00", "", "  ",
                "10 PM", "22.00", None, True):
        try:
            N.check_time(bad)
            check(f"a time {bad!r} is refused", False, "it was accepted")
        except N.PrefsError as exc:
            check(f"a time {bad!r} is refused in plain words",
                  bool(str(exc)) and "22:00" in str(exc) and "_" not in str(exc),
                  str(exc))


def t_nonsense_is_refused_and_writes_nothing():
    p = fresh()
    before = p.read_bytes()
    cases = [("alarms", "perhaps", "not on or off"),
             ("quiet_start", 1320, "a bare number of minutes"),
             ("quiet_start", "25:00", "an hour that does not exist"),
             ("quiet_end", "7", "not a time at all"),
             ("ttl_hours", 5, "not one of the seven"),
             ("", True, "no key at all")]
    for key, value, why in cases:
        try:
            N.write({key: value})
            check(f"{key} = {value!r} ({why}) is refused", False, "no error")
        except N.PrefsError as exc:
            check(f"{key} = {value!r} ({why}) is refused in plain words",
                  bool(str(exc)) and "_" not in str(exc), str(exc))
    check("not one byte was written", p.read_bytes() == before)
    try:
        N.write({})
        check("an empty change is refused", False, "no error")
    except N.PrefsError as exc:
        check("an empty change is refused in plain words", bool(str(exc)), str(exc))
    try:
        N.write({"alarms": False, "quiet_start": "nope"})
        check("a bad value in a set of changes refuses the WHOLE set", False,
              "it was accepted")
    except N.PrefsError:
        check("a bad value in a set of changes refuses the WHOLE set",
              p.read_bytes() == before, "part of the set was written")


# --------------------------------------------------------------------------
#   3. A round trip through the real file
# --------------------------------------------------------------------------
def t_a_round_trip_through_the_owners_file():
    p = fresh()
    before = p.read_text(encoding="utf-8")
    out = N.write({"alarms": False, "quiet_enabled": True,
                   "quiet_start": "23:15"})
    after = p.read_text(encoding="utf-8")
    check("the answer reports what it was and what it is",
          out["ok"] and out["changed"] and out["from"]["alarms"] is True
          and out["to"]["alarms"] is False and out["to"]["quiet_start"] == "23:15",
          out)
    check("what the module reads back is what both apps will be shown",
          N.read() == {"alarms": False, "reminders": True, "briefing": True,
                       "handoff": True, "quiet_enabled": True,
                       "quiet_start": "23:15", "quiet_end": "07:00"}, N.read())
    check("the switches are written as true/false, never as 1/0",
          "alarms = false" in after and "quiet_enabled = true" in after, after[-300:])
    check("a time is written as a QUOTED string, so the file holds what the "
          "owner reads",
          'quiet_start = "23:15"' in after, after[-300:])
    changed = [i for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines()), 1)
               if a != b]
    check("exactly the lines that changed moved", len(changed) == 3, changed)
    check("every comment survives", before.count("#") == after.count("#"))


def t_one_line_moves_and_the_rest_of_the_file_does_not():
    """The same discipline `jarvis_limits.py` follows: this is the owner's own
    file, full of their own notes, and a switch must not reformat it."""
    p = fresh("# a comment\r\n[notifications]\r\n"
              "quiet_start = \"22:00\"        # keep this\r\n[other]\r\nx = 1\r\n")
    N.write({"quiet_start": "06:30"}, path=p)
    raw = p.read_bytes()
    check("CRLF endings survive (no bare LF was introduced)",
          raw.count(b"\r\n") == raw.count(b"\n") and b"\r\n" in raw,
          (raw.count(b"\r\n"), raw.count(b"\n")))
    check("the line's own trailing comment survives",
          b'quiet_start = "06:30"        # keep this\r\n' in raw, raw.decode("utf-8"))
    check("and the other table is untouched", b"[other]\r\nx = 1\r\n" in raw,
          raw.decode("utf-8"))


def t_a_missing_key_and_a_missing_section_are_both_created():
    p = fresh("[undo]\nttl_hours = 24\n")
    N.write({"quiet_end": "08:00"}, path=p)
    text = p.read_text(encoding="utf-8")
    check("a file with no [notifications] table gets one",
          "[notifications]" in text and 'quiet_end = "08:00"' in text, text[-200:])
    check("... and the table it already had is left alone",
          "[undo]\nttl_hours = 24\n" in text, text)
    p2 = fresh("[notifications]\nalarms = true\n")
    N.write({"quiet_start": "05:00"}, path=p2)
    text2 = p2.read_text(encoding="utf-8")
    check("a section that exists but lacks a key has it added inside",
          text2.index("[notifications]") < text2.index('quiet_start = "05:00"'),
          text2)
    check("... and the key already there is untouched",
          "alarms = true" in text2, text2)


def t_a_byte_order_mark_is_kept():
    """The owner's real file may carry one. This module's writer must not strip
    it (jarvis_limits.py's writer does not either).

    NOTED, not fixed, and NOT asserted as a round trip: `jarvis_framework`'s
    own reader hands the file to `tomllib` in binary mode, and tomllib REFUSES a
    byte-order mark - `load_framework` catches that and falls back to "every
    setting is its default". So a settings file saved with a BOM reads as
    defaults TODAY, before this module existed. That belongs to
    `jarvis_framework.py` and is out of this change's scope; what is asserted
    here is only what this module is responsible for, that the bytes it does
    not own are left alone."""
    p = TMP / "jarvis-framework.toml"
    body = SHIPPED.read_text(encoding="utf-8")
    p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    N.write({"reminders": False}, path=p)
    raw = p.read_bytes()
    check("a file that had a byte-order mark still has one",
          raw.startswith(b"\xef\xbb\xbf"), raw[:6])
    check("... and the change is really in the bytes, on the right line",
          b"reminders = false" in raw and raw.count(b"\xef\xbb\xbf") == 1,
          raw.count(b"\xef\xbb\xbf"))
    check("... and the rest of the file is still there",
          b"[notifications]" in raw and b"quiet_end = \"07:00\"" in raw, raw[-160:])
    fresh()


# --------------------------------------------------------------------------
#   4. Nothing is logged
# --------------------------------------------------------------------------
def t_nothing_is_ever_logged():
    """A whole successful write and a whole refusal, with stdout, stderr and
    every logger captured. A settings path, a value or a refusal's words would
    all be something the owner never asked Jarvis to write down."""
    p = fresh()
    caught = io.StringIO()
    records = []

    class Grab(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    root = logging.getLogger()
    handler = Grab()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        with contextlib.redirect_stdout(caught), contextlib.redirect_stderr(caught):
            try:
                N.write({"quiet_start": "03:00", "alarms": False}, path=p)
            except Exception as exc:              # pragma: no cover - the point
                caught.write(str(exc))
            try:
                N.write({"quiet_start": "nonsense"}, path=p)
            except N.PrefsError:
                pass
            try:
                N.read()
            except Exception as exc:              # pragma: no cover - the point
                caught.write(str(exc))
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    said = caught.getvalue()
    check("a successful write and a refusal print nothing at all",
          said == "", repr(said))
    check("and nothing reaches any logger", records == [], records)


# --------------------------------------------------------------------------
if __name__ == "__main__":
    for fn in (t_defaults_are_what_the_desktop_already_did,
               t_a_file_with_no_section_reads_as_the_defaults,
               t_a_time_of_day_is_checked_and_never_a_bare_number,
               t_nonsense_is_refused_and_writes_nothing,
               t_a_round_trip_through_the_owners_file,
               t_one_line_moves_and_the_rest_of_the_file_does_not,
               t_a_missing_key_and_a_missing_section_are_both_created,
               t_a_byte_order_mark_is_kept,
               t_nothing_is_ever_logged):
        print(f"\n--- {fn.__name__} ---")
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
