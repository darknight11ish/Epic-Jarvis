"""jarvis_notify_prefs.py - which of this PC's own toasts fire, and the quiet
hours around them, in the OWNER'S SETTINGS FILE instead of one webview's
`localStorage`.

    check()      - refuse a value this module would not take, in plain words
    check_time() - refuse a time of day that is not "HH:MM"
    read()       - the seven values as they stand, each defaulted
    write()      - move the keys this module is handed; nothing else changes

WHY THIS EXISTS (the owner's decision, 2026-10-08). The desktop's Settings ->
Notifications card offered four switches (alarms, reminders, the morning
briefing, "Solve it here") and a quiet-hours window. `notifications-prefs.js`
kept them in the desktop app's own `localStorage` and pushed a copy to Rust
(`set_notification_prefs`, `jarvis-desktop/src-tauri/src/notifications.rs`),
which is what actually raises a toast. There was **no backend route and no
key in `jarvis-framework.toml` for any of the seven** - checked, and this
module is the answer to it. A phone can never reach another app's
`localStorage`, so a control on the phone needs the value to live somewhere
the phone can reach, and the one place both apps already read is the owner's
settings file.

THE FILE IS THE ONE HOME. This module owns `[notifications]` in the owner's
`jarvis-framework.toml` and nothing else. It keeps no second copy, no cache
and no database: `read()` asks the file every time (through
`jarvis_framework.load_framework`, the same reader every other module uses),
so what the owner reads on the phone IS what is in force. Where a key is
missing, the default below is what the module reports - the same defaults the
desktop's card has always used (the four toggles on, quiet hours off, 22:00
to 07:00), so a settings file written before this module existed behaves
exactly as it did.

THE SEVEN VALUES:

    [notifications]
    alarms = true          # alarms and urgent "tell me when" alerts
    reminders = true       # reminders, timers and to-do items
    briefing = true        # the morning briefing is ready
    handoff = true         # a website needs the owner ("Solve it here")
    quiet_enabled = false  # quiet hours on or off
    quiet_start = "22:00"  # the window's two ends, local time
    quiet_end = "07:00"

THE ROWS THE OWNER SEEES. The limits table (`jarvis_limits.py`) rides this
section: one row per value, `kind="bool"` for the five switches and
`kind="time"` for the two ends, each marked `app="both"` so BOTH apps draw
them. That is deliberate - a new patch would cost this repository its place in
`scripts/apply-patches.ps1`, three ordering invariants and the stand-in
ratchet, while a row in the one limits table costs a line. This module is the
thing those rows write; the rows are not a second table of their own.

WHAT IT NEVER DOES. It never logs: not a value, not a path, not a refusal.
Two of the seven are a window around the owner's own day, and one of them
combined with a toast time says when the owner is asleep. Nothing here is
worth a log line. It also never raises an approval card and never decides
anything: the limits table decides whether a change is put to the owner
first, and this module only reads, checks and writes the file.
"""
from __future__ import annotations

import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Optional, Tuple

try:
    import jarvis_framework as fw
except Exception:                                    # pragma: no cover
    fw = None

#: The one table in the owner's settings file this module owns.
SECTION = "notifications"

#: The five switches, in the order the desktop's card draws them, and the one
#: field name each has in `jarvis-framework.toml`.
SWITCHES: Tuple[str, ...] = ("alarms", "reminders", "briefing", "handoff",
                             "quiet_enabled")

#: The two ends of the quiet-hours window, "HH:MM" on the owner's own clock.
TIMES: Tuple[str, ...] = ("quiet_start", "quiet_end")

#: Every key this module owns, switches first.
KEYS: Tuple[str, ...] = SWITCHES + TIMES

#: What each key is when the owner's file does not say. The four toggles ON,
#: quiet hours OFF, 22:00 to 07:00 - byte for byte the defaults the desktop's
#: `notifications-prefs.js` and Rust's `NotificationPrefs::default()` already
#: use, so nothing changes behaviour for anyone who never touches a switch.
DEFAULTS: dict = {
    "alarms": True,
    "reminders": True,
    "briefing": True,
    "handoff": True,
    "quiet_enabled": False,
    "quiet_start": "22:00",
    "quiet_end": "07:00",
}

#: A time of day: one or two digits, a colon, exactly two digits. Deliberately
#: NOT tolerant of "7:5" or "7" - a bare number of minutes with no explanation
#: is worse than a refusal, and this is the one place that decides.
_TIME = re.compile(r"^(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)$")

_SECTION_LINE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_SCALAR_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
                          r"(?P<eq>\s*=\s*)(?P<value>[^#\r\n]*?)(?P<rest>\s*(?:#.*)?)$")

_TRUE = ("true", "1", "on", "yes")
_FALSE = ("false", "0", "off", "no")


class PrefsError(Exception):
    """The value was refused, or the owner's settings file could not be read or
    written, so nothing changed. The message is shown to the owner as it is,
    in plain words."""


# ---------------------------------------------------------------------------
#   Checking a value - the two functions the limits table calls
# ---------------------------------------------------------------------------
def check_time(value) -> str:
    """`value` as a time of day this module will store, or a `PrefsError`.

    The owner reads and types a clock time, so that is what is stored: a
    quoted "HH:MM". Anything else - a number of minutes, "7", "25:00",
    "7:5", an empty box - is refused with the shape that IS wanted, rather
    than quietly turned into some other number the owner never chose."""
    text = str(value).strip().strip('"').strip("'")
    if not _TIME.match(text):
        raise PrefsError("A time has to look like 22:00 (hours and minutes, "
                         "00 to 23 and 00 to 59).")
    # Normalise "7:05" to "07:05" so the file and both apps agree on one shape.
    hours, minutes = text.split(":")
    return f"{int(hours):02d}:{minutes}"


def check_bool(value) -> bool:
    """`value` as a switch, or a `PrefsError`. Accepts what the settings file
    and both apps' screens send (a real bool, or "on"/"off" and friends) and
    refuses the rest - including the string "perhaps", which must never be
    read as "off"."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise PrefsError("That is not on or off.")


def check(key: str, value):
    """One value for one key, checked, or a `PrefsError`. The key must be one
    of the seven; nothing else in the settings file is this module's to move."""
    if key not in KEYS:
        raise PrefsError("That is not a notification setting Jarvis knows.")
    return check_bool(value) if key in SWITCHES else check_time(value)


def is_time_key(key: str) -> bool:
    return key in TIMES


# ---------------------------------------------------------------------------
#   Reading the owner's file
# ---------------------------------------------------------------------------
def _config() -> dict:
    try:
        return dict(fw.load_framework() or {}) if fw is not None else {}
    except Exception:
        return {}


def _section(cfg: Optional[dict] = None) -> dict:
    node = (_config() if cfg is None else cfg) or {}
    got = node.get(SECTION)
    return got if isinstance(got, dict) else {}


def read() -> dict:
    """All seven values as they stand, each defaulted.

    A key the owner's file does not carry reads as its default; a key that is
    there but nonsense (a hand-edited "quiet_start = maybe", an "alarms = 3")
    reads as its default TOO, so a broken line can never leave a switch in a
    state neither app can draw. The one house rule the toasts already follow:
    a value nobody can read must never mean "go quiet by accident"."""
    got = _section()
    out: dict = {}
    for key in SWITCHES:
        if key not in got:
            out[key] = DEFAULTS[key]
            continue
        try:
            out[key] = check_bool(got[key])
        except PrefsError:
            out[key] = DEFAULTS[key]
    for key in TIMES:
        if key not in got:
            out[key] = DEFAULTS[key]
            continue
        try:
            out[key] = check_time(got[key])
        except PrefsError:
            out[key] = DEFAULTS[key]
    return out


def value_of(key: str):
    """One value, as `read()` would report it."""
    if key not in KEYS:
        raise PrefsError("That is not a notification setting Jarvis knows.")
    return read()[key]


# ---------------------------------------------------------------------------
#   Writing the owner's file - one line at a time, atomically
# ---------------------------------------------------------------------------
def _literal(key: str, value) -> str:
    if key in SWITCHES:
        return "true" if value else "false"
    return '"{}"'.format(value)


def _toml_path() -> Optional[Path]:
    try:
        p = fw.config_path() if fw is not None else None
    except Exception:
        p = None
    return Path(p) if p else None


def _reload() -> None:
    try:
        if fw is not None:
            fw.reload_framework()
    except Exception:
        pass


def _rewrite(text: str, key: str, literal: str) -> Tuple[str, Optional[str]]:
    """(new text, the old line's value or None). Only that one line moves.

    The section is created if the owner's file has none, and a key is added
    inside it if the section is there without that key. Every other line,
    every comment and the file's own line endings are left exactly as they
    were - the same discipline `jarvis_limits.py` follows, for the same
    reason: this is the owner's file and it is full of their own notes."""
    lines = text.splitlines(keepends=True)
    ending = "\r\n" if "\r\n" in text else "\n"
    start = None
    for i, line in enumerate(lines):
        m = _SECTION_LINE.match(line.rstrip("\r\n"))
        if m and m.group("name").strip() == SECTION:
            start = i
            break
    if start is None:
        tail = "" if (not lines or lines[-1].endswith(("\n", "\r"))) else ending
        lines.append(f"{tail}[{SECTION}]{ending}{key} = {literal}{ending}")
        return "".join(lines), None
    last = start
    for i in range(start + 1, len(lines)):
        bare = lines[i].rstrip("\r\n")
        if _SECTION_LINE.match(bare):
            break                       # the next table starts here
        if not bare.strip():
            continue
        m = _SCALAR_LINE.match(bare)
        if m and m.group("key") == key:
            old = m.group("value").strip().strip('"').strip("'")
            lines[i] = (f"{m.group('indent')}{key} = {literal}"
                        f"{m.group('rest')}{ending}")
            return "".join(lines), old
        last = i
    lines.insert(last + 1, f"{key} = {literal}{ending}")
    return "".join(lines), None


_LOCK = threading.RLock()


def write(changes: dict, *, path: Optional[Path] = None) -> dict:
    """Move the keys in `changes`, atomically, and nothing else.

    `{"ok", "changed", "from", "to"}` - `from` and `to` are whole seven-value
    readings, so the caller can show the owner what actually moved. An unknown
    key, or a value that is not on/off or a time, raises `PrefsError` BEFORE
    anything is written: a bad value in the middle of a set of changes must
    not leave half of them applied."""
    if not isinstance(changes, dict) or not changes:
        raise PrefsError("Send the notification settings you want to change.")
    wanted = {}
    for key, value in changes.items():
        wanted[key] = check(key, value)
    if not wanted:
        raise PrefsError("Send the notification settings you want to change.")
    before = read()
    p = path or _toml_path()
    if p is None or not Path(p).is_file():
        raise PrefsError("Jarvis could not find your settings file "
                         "(jarvis-framework.toml), so nothing was changed")
    p = Path(p)
    with _LOCK:
        try:
            raw_bytes = p.read_bytes()
        except OSError as exc:
            raise PrefsError("Your settings file could not be read "
                             f"({type(exc).__name__}), so nothing was changed")
        bom = raw_bytes.startswith(b"\xef\xbb\xbf")
        try:
            text = raw_bytes[3:].decode("utf-8") if bom else raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise PrefsError("Your settings file is not plain text, so "
                             "nothing was changed")
        new = text
        for key, value in wanted.items():
            new, _old = _rewrite(new, key, _literal(key, value))
        if new == text:
            return {"ok": True, "changed": False, "from": before, "to": before}
        data = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp",
                                   dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            try:
                os.chmod(tmp, stat.S_IMODE(os.stat(p).st_mode))
            except OSError:
                pass
            os.replace(tmp, p)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise PrefsError("Your settings file could not be written "
                             f"({type(exc).__name__}), so nothing was changed")
    _reload()
    after = read()
    return {"ok": True, "changed": after != before, "from": before, "to": after}
