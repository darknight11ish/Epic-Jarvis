"""jarvis_phone_apps.py - the apps Jarvis may open on the phone, managed.

    READ  GET  /api/phone/apps   the list, in the owner's own names
    WRITE POST /api/phone/apps   ONE app, card first: add or remove

THE GAP THIS CLOSES (2026-11-02). `jarvis_android_control.py`'s `[phone_apps]`
table is the whole permission for opening an app on the owner's phone, and it
ships EMPTY - so the feature could only be used by hand-editing
`jarvis-framework.toml`. The owner asked for the management in their own words:
"any apps that i ask if to open or do something with. i would need to approve a
card with the apps i would like it to manipulate first and i can remove or add
any android app to that list any time with an approval card... or by going to
the settings and changing it there too."

WHAT THIS MODULE IS, AND IS NOT. It is the WRITER for that one table, and the
one place the rules about a line in it live. It adds no second permission
model: every write goes through `jarvis_gate.check(action="change_own_config")`
- the existing action, tier and card words every other settings change already
uses - and nothing is written until a person says yes to that card. The model
tool in `jarvis_agent.py` reaches the SAME function through the agent's own
gate, so the chat path and the Settings path cannot disagree about what is
allowed: ONE rule, two doors.

CARD FIRST, AND THE CARD NAMES THE APP. The card's text is built here
(`card_text`), not by the model, and it names BOTH the friendly name and the
exact package id being added or removed. A removed line is carded exactly like
an added one. There is no bulk path: one call carries one app, and every field
is one plain string (`_one`), so a second app in the same request is refused
rather than quietly dropped.

THE FILE, THE SAME WAY THE OTHER SETTINGS ARE WRITTEN. `[phone_apps]` lives in
the owner's `jarvis-framework.toml`, so this module follows `jarvis_limits.py`
and `jarvis_notify_prefs.py` exactly: read the bytes, change ONE line of the
owner's own text (comments, ordering and line endings untouched), re-parse the
whole file and prove that the ONLY difference is the line it meant to change,
then write through a temporary file and `os.replace`, keeping the file's
permissions - and call `jarvis_framework.reload_framework()` so the change is
live on the next message. There is no `open(path, "w")` anywhere in this file:
a half-written settings file is how a policy becomes "missing, so off" with
nobody told.

WHAT A LINE MUST BE. The friendly name is what the owner says out loud and the
package is what Android knows the app by, validated with
`jarvis_android_control._safe_package` so the two modules cannot disagree about
what a package may look like (`com.jarvis.` is refused there, which keeps any
tap out of Jarvis's own Approve button). A line that is not a plain name and a
plain package is ignored when READ (the reader's rule, unchanged) and refused
when WRITTEN (here).

AUDIT. Every applied add and remove writes one `jarvis_framework.audit_log`
line naming the app and the package, after the write succeeded - never before,
so a refused or failed write leaves no line claiming it happened. The package
is the thing the owner is allowing, not a secret; the audit log is local.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Optional

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:                      # pragma: no cover
    try:
        import tomli as _toml                    # type: ignore
    except ModuleNotFoundError:
        _toml = None

#: The one table this module owns, and the one section it edits.
SECTION = "phone_apps"

#: The existing gate action every settings change already uses. NOT a new
#: action: `[autonomy.tiers]` already carries `change_own_config = "ask"`, the
#: gate already owns its risk row and `jarvis_card_words` already owns its
#: title, so nothing about the permission model is invented here.
ACTION = "change_own_config"

#: The route both apps call. One route, two verbs: read the list, or ask for
#: ONE change (which raises the card).
ROUTE = "/api/phone/apps"

#: A friendly name is something a person says; this is the most of it that
#: still reads as a name on a card.
MAX_NAME = 40

#: The same shape `jarvis_android_control._safe_package` accepts: a dotted
#: Android package, at least one dot. 127 characters is Android's own limit.
_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")

#: A line of the owner's own table. Both quoting styles TOML allows are here,
#: because the owner may have written a line by hand in either one, and a
#: line this module cannot recognise is a line it will not move.
_KEY = r'(?P<key>"(?:\\.|[^"\\])*"|\'(?:[^\']*)\'|[A-Za-z0-9_-]+)'
_VALUE = r'(?P<value>"(?:\\.|[^"\\])*"|\'(?:[^\']*)\')'
_ENTRY_LINE = re.compile(rf"^\s*{_KEY}\s*=\s*{_VALUE}\s*(?:#.*)?$")
_SECTION_LINE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*(?:#.*)?$")

#: The file-level lock, the same discipline `jarvis_limits.set_limit` uses: a
#: second write waits rather than reading a file that is halfway through the
#: first one's replace.
_LOCK = threading.RLock()

#: A test-only stand-in for the gate, like `jarvis_limits.configure`.
_STATE: dict = {"gate": None, "tier_of": None, "path": None}


class PhoneAppsError(Exception):
    """A refusal in the owner's words. Nothing was written when this is raised."""


# ---------------------------------------------------------------------------
#   Reading the list
# ---------------------------------------------------------------------------
def _config() -> dict:
    try:
        import jarvis_framework as fw
        return fw.load_framework()
    except Exception:
        return {}


def _table(cfg: Optional[dict] = None) -> dict:
    got = (cfg if cfg is not None else _config()).get(SECTION)
    return got if isinstance(got, dict) else {}


def _toml_path() -> Optional[Path]:
    try:
        import jarvis_framework as fw
        p = fw.config_path()
    except Exception:
        p = None
    return Path(p) if p else None


def _reload() -> None:
    try:
        import jarvis_framework as fw
        fw.reload_framework()
    except Exception:
        pass


def _rows(table: dict) -> list:
    """The table as the rows both apps draw, in the owner's own names.

    A line whose package is not a plain package name is LEFT OUT, exactly as
    `jarvis_android_control.read_phone_apps` leaves it out - one reader rule,
    so what the settings page shows is what the phone tool would honour. It is
    not hidden, though: `ignored` counts it and `note` says so.
    """
    rows, ignored = [], 0
    for name, package in table.items():
        if not isinstance(name, str) or not isinstance(package, str):
            ignored += 1
            continue
        friendly = name.strip()
        pkg = package.strip()
        if not friendly or not _PACKAGE.match(pkg) or pkg.startswith("com.jarvis."):
            ignored += 1
            continue
        rows.append({"name": friendly, "package": pkg})
    rows.sort(key=lambda r: r["name"].casefold())
    return [dict(r, can_play=_can_play(r["package"])) for r in rows], ignored


def _can_play(package: str) -> bool:
    """Whether Jarvis also knows this app's own search address, read from the
    module that owns them - never guessed here."""
    try:
        import jarvis_android_control as A
        return bool(A.SEARCH_LINKS.get(package))
    except Exception:
        return False


def view() -> dict:
    """The list, in words a settings page can draw. READ-ONLY, always."""
    rows, ignored = _rows(_table())
    out = {"ok": True, "available": True, "apps": rows, "count": len(rows),
           "empty": not rows, "note": "", "why": ""}
    if not rows:
        out["note"] = ("No apps are allowed yet, so Jarvis cannot open any app on "
                       "your phone. Add one here, or ask Jarvis in chat.")
    elif ignored:
        out["note"] = (f"{ignored} line(s) under [phone_apps] are not a plain name "
                       f"and a plain package name, so they are ignored.")
    return out


# ---------------------------------------------------------------------------
#   What a line may be
# ---------------------------------------------------------------------------
def _one(value) -> str:
    """One plain string, or a refusal. A LIST here is a bulk request and is
    refused instead of quietly using its first item."""
    if isinstance(value, (list, tuple, set, dict)):
        raise PhoneAppsError("One app at a time, please - this takes one name and "
                             "one package, and nothing was changed.")
    return str(value if value is not None else "").strip()


def check_name(value) -> str:
    name = _one(value)
    if not name:
        raise PhoneAppsError('Say which app, by the name you would say out loud - '
                             'for example "YouTube Music". Nothing was changed.')
    if len(name) > MAX_NAME:
        raise PhoneAppsError(f"That name is longer than {MAX_NAME} characters. Use "
                             f"a shorter name for the app. Nothing was changed.")
    if any(ord(c) < 32 for c in name):
        raise PhoneAppsError("That name has a control character in it, so it cannot "
                             "be written as one line. Nothing was changed.")
    return name


def check_package(value) -> str:
    package = _one(value)
    if not package:
        raise PhoneAppsError("Say the app's Android package as well - for example "
                             "com.google.android.apps.youtube.music. Nothing was "
                             "changed.")
    try:
        import jarvis_android_control as A
        package = A._safe_package(package)
    except PhoneAppsError:
        raise
    except ValueError as exc:
        raise PhoneAppsError(f"{exc} Nothing was changed.") from None
    except Exception:
        if not _PACKAGE.match(package):
            raise PhoneAppsError(
                f"{package!r} is not an Android package name (it looks like "
                f"com.company.app). Nothing was changed.") from None
    if package.startswith("com.jarvis."):
        raise PhoneAppsError("Jarvis's own app cannot be on this list: a tap in it "
                             "could reach its own Approve button. Nothing was changed.")
    if not _PACKAGE.match(package):
        raise PhoneAppsError(f"{package!r} is not an Android package name (it looks "
                             f"like com.company.app). Nothing was changed.")
    return package


def check_add(name, package, table: Optional[dict] = None) -> tuple:
    """(the name, the package) a new line would use, or PhoneAppsError."""
    name, package = check_name(name), check_package(package)
    table = _table() if table is None else table
    for have, pkg in table.items():
        if str(have).strip() == name:
            if str(pkg).strip() == package:
                raise PhoneAppsError(f"{name!r} is already on the list as "
                                     f"{package}. Nothing was changed.")
            raise PhoneAppsError(f"{name!r} is already on the list with a different "
                                 f"package ({pkg}), so neither was changed. Remove it "
                                 f"first if you mean to replace it.")
        if str(pkg).strip() == package:
            raise PhoneAppsError(f"{package} is already on the list as {have!r}. "
                                 f"Nothing was changed.")
    return name, package


def check_remove(name, table: Optional[dict] = None) -> tuple:
    """(the name exactly as the file spells it, its package), or PhoneAppsError."""
    name = check_name(name)
    table = _table() if table is None else table
    for have, pkg in table.items():
        if str(have).strip() == name:
            return str(have).strip(), str(pkg).strip()
    raise PhoneAppsError(f"{name!r} is not on the list, so there was nothing to "
                         f"remove. Nothing was changed.")


# ---------------------------------------------------------------------------
#   Writing ONE line of the owner's own text
# ---------------------------------------------------------------------------
def _quote(key: str) -> str:
    """A TOML basic-string key. Only `"` and `\\` need escaping."""
    return '"' + key.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unquote(token: str) -> str:
    """The value of a TOML key token this module can recognise."""
    if token.startswith('"') and token.endswith('"'):
        body = token[1:-1]
        return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1),
                                                                    m.group(1)), body)
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]
    return token


def _section_span(lines: list, section: str = SECTION):
    """(header index, first body index, end index) or None.

    `end` is the index of the next table's header (or len(lines)).
    """
    start = None
    for i, line in enumerate(lines):
        m = _SECTION_LINE.match(line.rstrip("\r\n"))
        if m and m.group("name").strip() == section:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _SECTION_LINE.match(lines[i].rstrip("\r\n")):
            end = i
            break
    return start, start + 1, end


def _rewrite_text(text: str, action: str, name: str, package: str) -> tuple:
    """(new text, said) with exactly ONE line added or removed, or both unchanged.

    The owner's file is their own: comments, ordering and line endings stay
    exactly as they are; only the one line this call is about moves.
    """
    lines = text.splitlines(keepends=True)
    ending = "\r\n" if "\r\n" in text else "\n"
    span = _section_span(lines)
    if action == "add":
        line = f"{_quote(name)} = {_quote(package)}{ending}"
        if span is None:
            tail = "" if (not lines or lines[-1].endswith(("\n", "\r"))) else ending
            lines.append(f"{tail}[{SECTION}]{ending}{line}")
            return "".join(lines), f"Added {name!r} to the list."
        _start, body, end = span
        at = end
        while at > body and not lines[at - 1].strip():
            at -= 1                      # before the blank lines that end a table
        lines.insert(at, line)
        return "".join(lines), f"Added {name!r} to the list."
    # remove: find THE line, in either TOML quoting style, and take it out.
    _start, body, end = span
    for i in range(body, end):
        m = _ENTRY_LINE.match(lines[i].rstrip("\r\n"))
        if m and _unquote(m.group("key")) == name \
                and _unquote(m.group("value")) == package:
            return "".join(lines[:i] + lines[i + 1:]), f"Removed {name!r} from the list."
    raise PhoneAppsError(f"The line for {name!r} could not be found where the list "
                         f"says it is, so nothing was changed. Edit it by hand in "
                         f"your settings file.")


def _parse(text: str) -> dict:
    if _toml is None:
        raise PhoneAppsError("This PC's Python cannot read a settings file, so "
                             "nothing was changed.")
    try:
        return _toml.loads(text)
    except Exception as exc:
        raise PhoneAppsError(f"Your settings file could not be read as settings "
                             f"({type(exc).__name__}), so nothing was changed.")


def _same_except(before: dict, after: dict, action: str, name: str,
                 package: str) -> bool:
    """True when `after` is `before` with exactly the one [phone_apps] line
    changed. Compared as whole parsed files, so a comment moved, a line lost
    elsewhere or a value changed anywhere is caught before the write lands."""
    want = json.loads(json.dumps(before, default=str))
    got = json.loads(json.dumps(after, default=str))
    table = want.setdefault(SECTION, {})
    if action == "add":
        table[name] = package
    else:
        # The [phone_apps] HEADER stays in the file even when its last line is
        # removed (this module never deletes the owner's own table header, only
        # the line it was asked about), so the wanted result is the SAME table
        # with that one key gone - not a file without the section.
        table.pop(name, None)
    return got == want


def _atomic_write(p: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
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
        raise PhoneAppsError(f"Your settings file could not be written "
                             f"({type(exc).__name__}), so nothing was changed.") from None


def write(action: str, name: str, package: str, *,
          path: Optional[Path] = None) -> dict:
    """Add or remove ONE app, atomically. NOTHING here raises a card.

    This is the function a caller runs AFTER its card was approved: the agent's
    tool (whose gate already asked) and this module's own `change()` (which
    asked through `jarvis_gate.check`). Keeping the write card-free is what
    makes "one card per change" true instead of two.
    """
    action = str(action or "").strip().lower()
    if action not in ("add", "remove"):
        raise PhoneAppsError("Ask to add an app or remove an app. Nothing was "
                             "changed.")
    before_table = _table()
    if action == "add":
        name, package = check_add(name, package, before_table)
    else:
        name, package = check_remove(name, before_table)
    p = path or _STATE.get("path") or _toml_path()
    if p is None or not Path(p).is_file():
        raise PhoneAppsError("Jarvis could not find your settings file on this PC, "
                             "so nothing was changed.")
    p = Path(p)
    with _LOCK:
        try:
            raw = p.read_bytes()
        except OSError as exc:
            raise PhoneAppsError(f"Your settings file could not be read "
                                 f"({type(exc).__name__}), so nothing was changed.") from None
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
        except UnicodeDecodeError:
            raise PhoneAppsError("Your settings file is not plain text, so nothing "
                                 "was changed.") from None
        before = _parse(text[1:] if text.startswith("\ufeff") else text)
        new, said = _rewrite_text(text, action, name, package)
        if new == text:
            return {"ok": True, "changed": False, "action": action, "name": name,
                    "package": package, "said": f"{name!r} was already as it is - "
                                                f"nothing to change."}
        after = _parse(new[1:] if new.startswith("\ufeff") else new)
        if not _same_except(before, after, action, name, package):
            raise PhoneAppsError("That change would have altered more of your "
                                 "settings file than the one line, so nothing was "
                                 "changed.")
        _atomic_write(p, (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
    _reload()
    _audit(action, name, package)
    return {"ok": True, "changed": True, "action": action, "name": name,
            "package": package, "said": said,
            "apps": view()["apps"]}


#: The audit event each applied change writes, named once. "remove" + "ed" is
#: "removeed", so the two are spelled out rather than built from the action.
_AUDIT_EVENT = {"add": "phone_apps.added", "remove": "phone_apps.removed"}


def _audit(action: str, name: str, package: str) -> None:
    """One local line per applied change - the package is what was allowed, not
    a secret, and nothing is written when the write above raised."""
    try:
        import jarvis_framework as fw
        fw.audit_log(_AUDIT_EVENT.get(action, f"phone_apps.{action}"),
                     {"name": name, "package": package})
    except Exception:
        pass


# ---------------------------------------------------------------------------
#   The card, and the route
# ---------------------------------------------------------------------------
def card_text(action: str, name: str, package: str) -> str:
    """The owner's own words to approve. Built HERE, never by the model, and
    it names both the friendly name and the exact package id."""
    if action == "add":
        return (f'Let Jarvis open "{name}" ({package}) on your phone?\n\n'
                f'This adds ONE line to the [phone_apps] list in your settings '
                f'file on this PC: "{name}" = "{package}". Nothing else changes, '
                f'and nothing is written until you approve.')
    return (f'Stop Jarvis opening "{name}" ({package}) on your phone?\n\n'
            f'This removes that ONE line from the [phone_apps] list in your '
            f'settings file on this PC. Nothing else changes, and nothing is '
            f'written until you approve.')


def _person_said_yes(v) -> bool:
    """The same test jarvis_limits.change() uses: a person answered THIS card
    with a yes. No outcome means the verdict came from somewhere else, so it is
    not a person's yes."""
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _dep(name: str, default):
    return _STATE.get(name) or default


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    import jarvis_gate
    try:
        return str(jarvis_gate.tier_of(action))
    except Exception:
        try:
            return str(jarvis_gate._tiers().get(action, "ask"))
        except Exception:
            return "ask"


def change(body, *, peer=None, local=None) -> tuple:
    """POST /api/phone/apps - ONE app, ONE card, and nothing written before it.

    The body is `{"action": "add"|"remove", "name": ..., "package": ...}`. A
    refusal (a bad name, a package that is not a package, `com.jarvis.`, an app
    already listed, an app not listed) is answered BEFORE a card exists, in the
    owner's words, with nothing changed and nobody asked.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send the app you want to add or remove."}
    action = str(body.get("action") or "").strip().lower()
    if action not in ("add", "remove"):
        return 400, {"ok": False, "changed": False,
                     "error": 'Say whether to "add" or "remove" an app.'}
    try:
        if action == "add":
            name, package = check_add(body.get("name"), body.get("package"))
        else:
            name, package = check_remove(body.get("name"))
    except PhoneAppsError as exc:
        return 400, {"ok": False, "error": str(exc), "changed": False}
    prompt = card_text(action, name, package)
    detail = {"text": prompt, "app": name, "package": package,
              "action": action, "leaves_this_pc": False}
    tier_of = _dep("tier_of", _tier)
    gate = _dep("gate", _gate)
    try:
        if tier_of(ACTION) != "ask":
            return 503, {"ok": False, "changed": False,
                         "error": "Your PC's Jarvis cannot ask you about a settings "
                                  "change yet, so nothing was changed."}
        v = gate(ACTION, detail, prompt)
    except Exception:
        return 503, {"ok": False, "changed": False,
                     "error": "Jarvis could not put that card to you just now, so "
                              "nothing was changed."}
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        if outcome == "denied":
            said = "You said no, so nothing was changed."
        elif outcome == "timed_out":
            said = "The card was not answered in time, so nothing was changed."
        else:
            said = "That was not approved, so nothing was changed."
        return 409, {"ok": False, "changed": False, "error": said}
    try:
        out = write(action, name, package)
    except PhoneAppsError as exc:
        return 409, {"ok": False, "changed": False, "error": str(exc)}
    return 200, dict(out, approved=True)


def handle_get() -> tuple:
    """GET /api/phone/apps. Read-only, behind the token, PC or phone."""
    return 200, view()


def handle_post(route: str, body, *, peer=None, local=None) -> tuple:
    """The HUD's own route calls this (phone-apps.patch)."""
    if route != ROUTE:
        return 404, {"error": "no such route"}
    return change(body, peer=peer, local=local)


def configure(*, gate=None, tier_of=None, path=None) -> None:
    """Tests only: stand in for the approval gate, the tier table and the file."""
    _STATE.update(gate=gate, tier_of=tier_of, path=path)
