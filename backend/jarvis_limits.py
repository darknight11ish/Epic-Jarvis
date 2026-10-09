"""jarvis_limits.py - the limits and frequencies the owner can change.

    POST /api/limits/settings   {"key": "jobs_per_tick", "value": 8}

WHY ONE MODULE AND ONE ROUTE. An audit of all 117 features against the real
settings surface (2026-10-08) listed the frequencies and limits the owner could
see and change nowhere. Every one of them is the same shape - a number (or one
on/off) in the owner's own `jarvis-framework.toml`, read by a module that
already knows how to use it - so they share ONE table here and ONE route in
`jarvis_hud.py` (`limits-settings.patch`), rather than one route each. A new
patch costs this repository real work (its place in `apply-patches.ps1`, three
ordering invariants, the stand-in ratchet), so the next limit is a line in
`LIMITS` and nothing else.

WHAT THIS MODULE DOES NOT DO: it does not decide what a limit means, and it does
not change how any module uses its number. Every entry names the table and key
its owning module ALREADY reads, with the same default that module uses, so the
number written here is the number that module acts on. Where a module reads the
key itself (`jarvis_jobs.py`, `jarvis_watch.py`, `jarvis_undo.py`,
`jarvis_entities.py`), nothing in that module changes.

THE RULE, the same one every setting follows:

  * TURNING SOMETHING DOWN is applied at once, with no card - it can only make
    Jarvis do less;
  * TURNING IT UP is a loosening ONLY where the entry says so (`loosen_up=True`:
    keeping undo history longer, or letting a model read the owner's saved
    facts). Those go through ONE approval card first, and nothing is written
    until a person approves. Which way a request is comes from the value
    against the number in force - never from anything the caller sends.
"""
from __future__ import annotations

import os
import re
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:                                    # pragma: no cover
    fw = None

#: The gate action a raise is asked under. ONE name for every limit: the card's
#: own words (below) carry which limit and how far, and a name per limit would
#: mean a name per limit in the card-words table, on the "What asks first" page
#: and in the tier file - three places to keep in step for no gain the owner can
#: see. The value decides the direction, this name only says "this is a raise".
RAISE_ACTION = "raise_a_limit"

ROUTE = "/api/limits/settings"

_SECTION_LINE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_SCALAR_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
                          r"(?P<eq>\s*=\s*)(?P<value>[^#\r\n]*?)(?P<rest>\s*(?:#.*)?)$")


class SettingsFileError(Exception):
    """The owner's settings file could not be read or written, so nothing was
    changed. The message is shown to the owner as it is, in plain words."""


def _words(n) -> str:
    return f"{n:g}"


# ---------------------------------------------------------------------------
#   The table
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Limit:
    key: str                     # the name the route, the screens and a voice
                                 # sentence use
    section: str                 # the table in jarvis-framework.toml
    name: str                    # the key inside it
    title: str                   # the row's words, in the owner's language
    kind: str                    # "int" | "float" | "bool"
    default: object
    low: float = 0
    high: float = 0
    choices: tuple = ()          # when set, the value must be one of these
    loosen_up: bool = False      # is a BIGGER value (or bool ON) a loosening?
    pc_only: bool = False        # may only be changed from this PC
    app: str = "both"            # "both" | "desktop" | "phone"
    unit: str = ""               # what one step of the number means
    note: str = ""               # the row's second line, plain words
    says: Optional[Callable[[object], str]] = None

    def words(self, value) -> str:
        if self.says is not None:
            return self.says(value)
        if self.kind == "bool":
            return self.title if value else f"no: {self.title}"
        return f"{_words(value)}{(' ' + self.unit) if self.unit else ''}"


def _ttl_says(v) -> str:
    return {1: "keep undo for an hour",
            24: "keep undo for a day",
            168: "keep undo for a week"}.get(int(v), f"keep undo for {int(v)} hours")






LIMITS: tuple = (
    # `[undo].ttl_hours` - how long an Undo stays possible. LONGER keeps more
    # of the owner's own files recoverable on disk, so it is the one direction
    # that asks (jarvis_undo.py reads this key already).
    Limit("undo_window", "undo", "ttl_hours", "How long you can undo",
          "int", 24, low=1, high=720, choices=(1, 24, 168), loosen_up=True,
          app="both", unit="hours",
          note="A longer window keeps older copies of your files on this PC.",
          says=_ttl_says),
    # `[jobs].max_jobs_per_tick` - how much Jarvis gets on with at once.
    # Nothing leaves the PC and nothing is spent, so neither direction asks.
    Limit("jobs_per_tick", "jobs", "max_jobs_per_tick", "Jobs at once",
          "int", 4, low=1, high=16, pc_only=True, app="desktop", unit="jobs",
          note="How many jobs one tick may start. More at once is faster and "
               "busier."),
    # `[watch].star_jump` / `star_floor` - what counts as news from a project.
    Limit("watch_star_jump", "watch", "star_jump", "What counts as news: the jump",
          "float", 0.5, low=0.05, high=0.9, app="desktop", unit="of the count",
          note="A repository counts as news when its stars move by this "
               "fraction."),
    Limit("watch_star_floor", "watch", "star_floor", "What counts as news: the floor",
          "int", 25, low=1, high=500, app="desktop", unit="stars",
          note="...but never for a repository with fewer stars than this."),
    # `[decks].run_limit` (2026-10-08): how many cards one review run shows
    # before "Do 10 more" adds ten. The study module reads it now, with the 20
    # it always had as the default and 1..MAX_CARDS as the range. (Named in
    # words, not by module name, on purpose: that module's own suite checks
    # that no other module reaches it, and this table only writes its number.)
    Limit("study_run_cards", "decks", "run_limit", "Cards in a study run",
          "int", 20, low=1, high=1000, app="both", unit="cards",
          note="What one run shows before you can ask for ten more."),
    # `[chat].tag_suggest_quiet_minutes`: how long a chat must sit untouched
    # before the OVERNIGHT TAG SUGGESTER may read it for tags. NOT the
    # new-conversation window - the two are different features, and the file's
    # own comment says so. 0 means no waiting at all.
    Limit("tag_suggest_age", "chat", "tag_suggest_quiet_minutes",
          "Suggest tags for chats older than",
          "int", 30, low=0, high=1440, app="desktop", unit="minutes",
          note="The overnight job may read a chat this old to suggest a tag. "
               "0 means no waiting."),
    # NOT HERE, and said plainly rather than half-done: the "new conversation
    # after 30 quiet minutes" window is CLIENT-SIDE (`chat-history.js`'s
    # `IDLE_NEW_MS`, `ChatSession.kt`) - nothing in the backend reads or serves
    # it, so a key here could not change it. That one needs the two apps' own
    # settings, not a line in this table.
    # `[memory.entities].model_pass` - whether a model reads what the owner
    # saves, looking for people and things. Turning it ON is the loosening: a
    # model reads stored facts (the owner's decision of 2026-09-24 makes every
    # reading of memory a card). OFF is instant.
    Limit("memory_people", "memory.entities", "model_pass",
          "Look for people and things in what you save",
          "bool", False, loosen_up=True, app="phone",
          note="A model reads what you save to find the people and things in "
               "it. Off, only the plain words you used are kept."),
)


def find(key: str) -> Optional[Limit]:
    return next((x for x in LIMITS if x.key == key), None)


def limits_for(app: str) -> tuple:
    """Every limit this app may change. `app` is "desktop" or "phone"."""
    return tuple(x for x in LIMITS if x.app in ("both", app))


# ---------------------------------------------------------------------------
#   Reading and writing the owner's file
# ---------------------------------------------------------------------------
def _config() -> dict:
    try:
        return dict(fw.load_framework() or {}) if fw is not None else {}
    except Exception:
        return {}


def _table(cfg: dict, section: str) -> dict:
    node = cfg
    for part in section.split("."):
        node = (node or {}).get(part)
        if not isinstance(node, dict):
            return {}
    return node


def value_of(limit: Limit):
    """What the owner's file says now, or the default the owning module uses."""
    raw = _table(_config(), limit.section).get(limit.name, limit.default)
    try:
        if limit.kind == "bool":
            return raw is True or str(raw).strip().lower() in ("true", "1", "on", "yes")
        if limit.kind == "int":
            return int(float(str(raw).strip()))
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return limit.default


def _coerced(limit: Limit, value):
    """The value as the file would hold it, or a SettingsFileError to show."""
    if limit.kind == "bool":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "1", "on", "yes"):
            return True
        if str(value).strip().lower() in ("false", "0", "off", "no"):
            return False
        raise SettingsFileError("That is not on or off.")
    try:
        number = int(float(str(value).strip())) if limit.kind == "int" else float(str(value).strip())
    except (TypeError, ValueError):
        raise SettingsFileError(f"\"{value}\" is not a number.")
    if limit.choices:
        if number not in limit.choices:
            raise SettingsFileError("Choose one of: " + ", ".join(
                _words(c) for c in limit.choices) + ".")
    elif not (limit.low <= number <= limit.high):
        raise SettingsFileError("That has to be between "
                                f"{_words(limit.low)} and {_words(limit.high)}.")
    return int(number) if limit.kind == "int" else number


def _literal(limit: Limit, value) -> str:
    if limit.kind == "bool":
        return "true" if value else "false"
    return _words(value)


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


def _rewrite(text: str, section: str, key: str, literal: str) -> tuple:
    """(new text, the old line's value or None). Only that one line moves."""
    lines = text.splitlines(keepends=True)
    ending = "\r\n" if "\r\n" in text else "\n"
    start = None
    for i, line in enumerate(lines):
        m = _SECTION_LINE.match(line.rstrip("\r\n"))
        if m and m.group("name").strip() == section:
            start = i
            break
    if start is None:
        tail = "" if (not lines or lines[-1].endswith(("\n", "\r"))) else ending
        lines.append(f"{tail}[{section}]{ending}{key} = {literal}{ending}")
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
            old = m.group("value").strip()
            lines[i] = (f"{m.group('indent')}{key} = {literal}"
                        f"{m.group('rest')}{ending}")
            return "".join(lines), old
        last = i
    lines.insert(last + 1, f"{key} = {literal}{ending}")
    return "".join(lines), None


_LOCK = threading.RLock()


def set_limit(key: str, value, *, path: Optional[Path] = None) -> dict:
    """Change ONE limit in the owner's settings file, atomically.

    {"ok", "key", "from", "to", "changed", "loosening"} - and `loosening` says
    whether this direction is the one that needs a card, so the caller (the
    route, and the two apps' own screens) can put it to the owner. Nothing here
    raises a card or pretends to."""
    limit = find(key)
    if limit is None:
        raise SettingsFileError("That is not a limit Jarvis knows.")
    want = _coerced(limit, value)
    now = value_of(limit)
    raised = (want > now) if limit.kind != "bool" else (want and not now)
    p = path or _toml_path()
    if p is None or not Path(p).is_file():
        raise SettingsFileError("Jarvis could not find your settings file "
                                "(jarvis-framework.toml), so nothing was changed")
    p = Path(p)
    with _LOCK:
        try:
            raw_bytes = p.read_bytes()
        except OSError as exc:
            raise SettingsFileError(f"Your settings file could not be read "
                                    f"({type(exc).__name__}), so nothing was changed")
        bom = raw_bytes.startswith(b"\xef\xbb\xbf")
        try:
            text = raw_bytes[3:].decode("utf-8") if bom else raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise SettingsFileError("Your settings file is not plain text, so "
                                    "nothing was changed")
        new, old_raw = _rewrite(text, limit.section, limit.name, _literal(limit, want))
        if new == text:
            return {"ok": True, "key": key, "from": now, "to": want,
                    "changed": False, "loosening": False}
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
            raise SettingsFileError(f"Your settings file could not be written "
                                    f"({type(exc).__name__}), so nothing was changed")
    _reload()
    return {"ok": True, "key": key, "from": now, "to": want, "changed": True,
            "loosening": bool(raised)}


# ---------------------------------------------------------------------------
#   The card a loosening needs, and the route
# ---------------------------------------------------------------------------
_STATE: dict = {"gate": None, "tier_of": None}


def configure(*, gate=None, tier_of=None) -> None:
    """Tests only: stand in for the approval gate and the tier table."""
    _STATE.update(gate=gate, tier_of=tier_of)


def _dep(name: str, default):
    return _STATE.get(name) or default


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


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


def _raise_card(limit: Limit, old, new) -> tuple:
    """The card for a raise, and the yes. (None, said) when it went through;
    ((status, body), "") when it did not."""
    prompt = (f"{limit.title}: change it from {_words(old)} to {_words(new)} "
              f"({limit.words(new)})? That lets Jarvis do more.")
    detail = {"text": prompt, "what": limit.title.lower(),
              "was": old, "now": new, "limit": limit.key,
              "leaves_this_pc": False}
    gate = _dep("gate", _gate)
    tier_of = _dep("tier_of", _tier)
    try:
        if tier_of(RAISE_ACTION) != "ask":
            return (503, {"ok": False, "error": "Your PC's Jarvis cannot ask you about "
                                                "that yet, so nothing was changed."}), ""
        v = gate(RAISE_ACTION, detail, prompt)
    except Exception:
        return (503, {"ok": False, "error": "Jarvis could not put that to you just now, "
                                            "so nothing was changed."}), ""
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        words = {"denied": "You said no, so nothing was changed.",
                 "timed_out": "The card was not answered in time, so nothing was "
                              "changed."}
        return (409, {"ok": False, "error": words.get(
            outcome, "That was not approved, so nothing was changed.")}), ""
    return None, f"{limit.title} is now {limit.words(new)}."


def view(*, app: Optional[str] = None) -> dict:
    """Every limit, with what the owner's file says now and the owner's words.

    `app=None` - what the route asks for - returns EVERY row, each carrying its
    own `app`, so each screen filters on what a row says rather than on a
    filter guessed here. (Both call the same route: the PC's card must see the
    PC-only limits and the phone must not, and neither can be told apart at the
    route without the caller saying so.) `app="desktop"` / `"phone"` narrows it
    here, which is what the tests and the voice lane ask for."""
    rows = []
    for limit in (LIMITS if app is None else limits_for(app)):
        now = value_of(limit)
        rows.append({"key": limit.key, "title": limit.title, "kind": limit.kind,
                     "value": now, "words": limit.words(now),
                     "choices": list(limit.choices), "low": limit.low,
                     "high": limit.high, "unit": limit.unit, "note": limit.note,
                     "loosen_up": limit.loosen_up, "pc_only": limit.pc_only,
                     "app": limit.app})
    return {"ok": True, "available": True, "limits": rows}


def change(body, *, peer=None, local=None) -> tuple:
    """POST /api/limits/settings - {"key": ..., "value": ...}."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send the limit you want to change."}
    key = body.get("key")
    if not isinstance(key, str) or "value" not in body:
        return 400, {"ok": False, "error": "Send a limit and the number you want."}
    limit = find(key)
    if limit is None:
        return 400, {"ok": False, "error": "That is not a limit Jarvis knows."}
    if limit.pc_only:
        from_here = True
        try:
            import jarvis_owner_check as OC
            if peer is not None:
                from_here = bool(OC.from_this_pc(peer, local))
        except Exception:
            from_here = peer is None
        if not from_here:
            return 403, {"ok": False, "pc_only": True,
                         "error": "That can only be changed on the PC."}
    try:
        want = _coerced(limit, body["value"])
    except SettingsFileError as exc:
        return 400, {"ok": False, "error": str(exc)}
    now = value_of(limit)
    raised = (want > now) if limit.kind != "bool" else (want and not now)
    said = ""
    if raised and limit.loosen_up:
        refused, said = _raise_card(limit, now, want)
        if refused is not None:
            return refused
    try:
        out = set_limit(key, want)
    except SettingsFileError as exc:
        return 400, {"ok": False, "error": str(exc)}
    if not said:
        said = f"{limit.title} is now {limit.words(out['to'])}."
    return 200, {"ok": True, "key": key, "changed": out.get("changed", True),
                 "loosening": bool(raised and limit.loosen_up),
                 "approved": bool(raised and limit.loosen_up),
                 "from": out.get("from"), "to": out.get("to"), "said": said}


def handle_post(route: str, body, *, peer=None, local=None) -> tuple:
    """The HUD's own route calls this (limits-settings.patch)."""
    if route != ROUTE:
        return 404, {"error": "no such route"}
    return change(body, peer=peer, local=local)
