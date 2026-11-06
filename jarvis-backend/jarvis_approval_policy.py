"""jarvis_approval_policy.py - what needs an approval card, how many yeses it
takes, and whether Windows Hello stands in front of it - changed by talking to
Jarvis, one named action at a time.

THE OWNER'S ASK (2026-11-05, in their own words): "i would also like the
ability to change what gets an approval card through chat, including if
something gets a double confirmation, or a fingerprint/windows hello".

THREE INDEPENDENT THINGS, FOR ONE ACTION AT A TIME

  card           Whether the action raises an approval card at all. This is
                 the action's own line in [autonomy.tiers] of the owner's
                 settings file - the one table every part of Jarvis already
                 reads (jarvis_framework.action_tier, the gate). This module
                 writes it through jarvis_asks_first.set_tier, so there is one
                 writer and one rule, not a second table that could disagree.
  confirmations  One yes, or two. Kept in [autonomy.confirmations] as
                 `<action> = 2`; one yes is the default and is stored by
                 having no line at all.
  windows_hello  Whether a yes must also meet Windows Hello on the PC. Kept
                 in [autonomy.windows_hello] as `<action> = true`; no line
                 means no extra check.

WHY THE TWO NEW TABLES, AND NOT A SECOND FILE. The owner's settings file
(jarvis-framework.toml) is already where an action's tier lives, is already
watched for changes while Jarvis runs, and is already the one file an
approval card over a loosening rewrites. A second file would be a second
place for the same question, and the two could disagree - so the two extra
dimensions live beside the tier, in the same file, written with the same
discipline (see jarvis_asks_first.set_tier: read the bytes, change exactly
one line, parse it again, and write to a temporary file moved into place).

THE DIRECTION RULES - the whole safety core, and not negotiable

  * TIGHTENING (add a card where there was none, add a second yes, add
    Windows Hello) is INSTANT and raises NO card. It only ever makes Jarvis
    ask more, like every "turn it off" switch in both apps. It also
    withdraws a waiting card that would loosen the same thing.
  * LOOSENING (remove a card, remove the second yes, remove Windows Hello)
    raises ONE approval card, on the PC only, that needs Windows Hello to
    approve. The request itself is refused from any other device, and the
    backend refuses to approve it from any other device too
    (jarvis_owner_check.PC_ONLY_ACTIONS holds this module's card action).
    The card's words say exactly what stops being asked and name the action
    in the owner's own words; nothing is written until a person approves.
  * NOTHING IN BULK. One action, one dimension, one call. A body naming two
    dimensions is refused before any card, so there is no control that
    changes several things at once.
  * AN UNKNOWN ACTION IS REFUSED BEFORE ANY CARD, in one plain sentence that
    names the nearest actions this PC really has.

WHAT A CARD BEING TURNED OFF STILL DOES NOT DO. It never auto-approves
anything: it only decides whether a card is RAISED. A card that is raised
still needs the owner's yes, the event-stream-stale rule is untouched, and
the actions whose own module refuses anything but a card (jarvis_asks_first.
MUST_ASK, the gate's hard limits) can never lose their card - this module
delegates the card dimension to jarvis_asks_first.request_tier, which applies
that list itself.

WHAT A SECOND CONFIRMATION AND WINDOWS HELLO ARE ENFORCED BY. Not the gate
and not a new patch on the owner's file: the one place every real approval
already passes through is jarvis_owner_check.approve_check, which wraps POST
/api/approve (owner-check.patch installs it). It is a shipped module, so it
can carry this rule without editing the owner's jarvis_gate.py at all. There
the extra rules are applied:

  * `approval_needs(action)` (below) is read on every approval, from the same
    settings file the page reads.
  * Windows Hello: an action with `windows_hello = true` is refused from any
    other device and asks Windows Hello on the PC on EVERY yes, whether or not
    the card is otherwise risky - exactly the shape PC_ONLY_ACTIONS already
    has.
  * Two confirmations: the first yes runs every check (including Windows
    Hello), and is then told to say yes once more; it approves NOTHING. The
    second yes runs the same checks again and only then is the approval
    stamped, which is the only thing the gate believes. A card that needs two
    yeses is approved on the PC only, said plainly: the phone's one-tap
    approval cannot carry a second yes, so it is refused with the same
    "answer it on the PC" words every PC-only card already gets.
  * The counter lives in this process's memory, never on disk, and is dropped
    when Jarvis restarts: a restart makes the owner say yes twice again. That
    is the safe direction - more asking, never less.

FAIL CLOSED ON A DAMAGED LINE. A line this module cannot read (a typo, a
value of the wrong kind) is read as the STRICTER answer: two yeses, and
Windows Hello required. The page says so under that row rather than showing
a default.

NO SECOND WAY IN. There is deliberately no model-free fast-path grammar for
this feature (unlike "connect my calendar"): a regex over "stop asking" is
exactly how a sentence gets misread into a loosening, and every loosening
already needs the owner's own card plus Windows Hello on the PC. The model's
tool call is only a PREPARATION - `request_change` below decides the
direction and, for a loosening, raises the card; nothing is written by the
model. docs/ARCHITECTURE.md section 8 records this choice, and the fact that
neither app gets a write control for these three dimensions: both apps draw
the read-only note under a row of "What asks first" instead.

TRIVIA. No sockets, no threads but the one card thread, standard library
only. `_reset_for_tests` exists for the suites, as in jarvis_asks_first.py.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import stat
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - Python before 3.11
    try:
        import tomli as _toml  # type: ignore
    except ModuleNotFoundError:
        _toml = None  # type: ignore

#: The approval card this module raises for a loosening. jarvis_owner_check.
#: PC_ONLY_ACTIONS holds the same name, so its approval is PC-only and always
#: asks Windows Hello. jarvis_asks_first.HARD_LIMITS and MUST_ASK hold it too,
#: so no app switch and no settings line may ever make it cardless.
ACTION = "change_approval_policy"

CARD = "card"
CONFIRMATIONS = "confirmations"
WINDOWS_HELLO = "windows_hello"
FIELDS = (CARD, CONFIRMATIONS, WINDOWS_HELLO)

#: The two tables this module writes. The card dimension is NOT here: it is
#: [autonomy.tiers], read and written by jarvis_asks_first.
TABLES = {CONFIRMATIONS: "confirmations", WINDOWS_HELLO: "windows_hello"}
_HEADER = re.compile(r"^[ \t]*\[[ \t]*autonomy[ \t]*\.[ \t]*(?P<table>[A-Za-z0-9_-]+)"
                     r"[ \t]*\][ \t]*(?:#.*)?$")
_ANY_HEADER = re.compile(r"^[ \t]*\[")
_KEY_LINE = re.compile(r"^[ \t]*(?:[A-Za-z0-9_-]+|\"[^\"]*\"|'[^']*')[ \t]*=")
_INSERTED_NOTE = "  # set by talking to Jarvis; one action at a time"

# ---------------------------------------------------------------------------
# What is read, replaceable for the tests (the same shape jarvis_asks_first
# uses, so a suite can run with no settings file and no card)
# ---------------------------------------------------------------------------


def _framework():
    return fw


def _config_path() -> Optional[Path]:
    try:
        p = fw.config_path() if fw is not None else None
    except Exception:
        p = None
    return Path(p) if p else None


def _section(name: str) -> dict:
    try:
        sec = fw.section("autonomy") if fw is not None else {}
    except Exception:
        return {}
    got = sec.get(name) if isinstance(sec, dict) else None
    return got if isinstance(got, dict) else {}


def _reload() -> None:
    try:
        if fw is not None:
            fw.reload_framework()
    except Exception:
        pass


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _title(action: str) -> str:
    """The action in the owner's words, from the approval cards' own table."""
    try:
        import jarvis_card_words as W
        phrase = W.TITLES.get(action)
    except Exception:
        phrase = None
    if not phrase:
        phrase = action.replace("_", " ")
    return phrase[:1].upper() + phrase[1:]


def _lower_title(action: str) -> str:
    phrase = _title(action)
    return phrase[:1].lower() + phrase[1:]


def has_written_title(action: str) -> bool:
    try:
        import jarvis_card_words as W
        return bool(W.has_written_title(action))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The universe of actions this PC really has
# ---------------------------------------------------------------------------


def known_actions() -> set:
    """Every action an approval card can name on this PC, minus the page's
    fixed rows (they are decided in code and have no tier or card)."""
    found: set = set()
    try:
        import jarvis_asks_first as AF
        for _title_text, ids in AF.GROUPS:
            found.update(a for a in ids if not str(a).startswith("fixed:"))
    except Exception:
        pass
    try:
        found.update(str(a) for a in _all_tiers())
    except Exception:
        pass
    try:
        import jarvis_card_words as W
        found.update(str(a) for a in W.TITLES)
    except Exception:
        pass
    found.discard("lockdown")
    found.discard(ACTION)
    return {a for a in found if re.fullmatch(r"[a-z][a-z0-9_]{1,60}", a or "")}


def _all_tiers() -> dict:
    try:
        return dict(fw.all_tiers()) if fw is not None else {}
    except Exception:
        return {}


#: The everyday words an owner uses for an action whose own name does not say
#: it. ONLY a hint for the refusal sentence that names the nearest actions -
#: never a way to find or change anything, so a wrong hint costs one sentence,
#: not a card. "the door" and "my lights" are the owner's words, not action
#: names, and this is what makes the sentence name home_control instead of
#: guessing.
WORDS_ALSO = {
    "home_control": ("door", "doors", "lock", "locks", "alarm", "light", "lights",
                     "plug", "fan", "heating", "garage", "cover", "covers"),
    "send_email": ("email", "mail"),
    "email_read": ("email", "mail"),
    "draft_email": ("email", "mail"),
    "tidy_inbox": ("email", "inbox"),
    "calendar_read": ("calendar", "diary"),
    "set_reminder": ("reminder", "reminders", "alarm"),
    "set_timer": ("timer",),
    "shell_exec": ("shell", "command", "terminal"),
    "browser_control": ("browser", "web"),
    "control_phone": ("phone",),
    "control_computer": ("computer", "window"),
    "spend_money": ("money", "spend", "spending"),
    "delete_file": ("delete", "remove", "file", "files"),
    "read_files_readonly": ("read", "file", "files"),
    "notes_search": ("note", "notes"),
    "screen_picture": ("screen", "picture", "screenshot"),
}
_STOPWORDS = frozenset({"the", "a", "an", "to", "of", "for", "my", "your", "it",
                        "and", "or", "that", "this", "on", "in", "with", "before",
                        "me", "jarvis", "one", "something", "anything"})


def nearest(name: str, limit: int = 3) -> list:
    """The nearest real action names to `name`, for one plain sentence.

    Two kinds of near, because a person (and a model repeating their words)
    says "sending email", not "send email": the action's own name and the
    words of its approval card, plus the few everyday nouns in WORDS_ALSO.
    The overlap wins over letter-distance when there is one, so a real subject
    is never hidden behind a lookalike."""
    pool = sorted(known_actions())
    raw = str(name or "").strip()
    words = set(re.findall(r"[a-z]+", raw.lower())) - _STOPWORDS
    scored = []
    for action in pool:
        title_words = set(re.findall(r"[a-z]+", _title(action).lower()))
        action_words = set(re.findall(r"[a-z]+", action.replace("_", " ")))
        hints = set(WORDS_ALSO.get(action, ()))
        overlap = len(words & (title_words | action_words | hints))
        if overlap:
            scored.append((overlap, action))
    if scored:
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [action for _n, action in scored[:limit]]
    got = difflib.get_close_matches(raw, pool, n=limit, cutoff=0.55)
    if not got:
        got = difflib.get_close_matches(raw.replace(" ", "_"), pool, n=limit,
                                        cutoff=0.4)
    return got


class PolicyError(Exception):
    """The change could not be made. The message is a sentence for the owner."""


HAND_EDIT = ("Your settings file is written in a way this page cannot change safely, "
             "so nothing was changed. Edit the line by hand in Notepad, then restart "
             "Jarvis")
#: Refusals that are the same words the rest of the page already uses.
NOT_ON_LIST = ("That is not one of the actions this PC can be asked about, so nothing "
               "was changed.")


def refusal_for_unknown(name: str) -> str:
    near = nearest(name)
    if near:
        titles = [f'"{_title(a)}"' for a in near]
        return (f"This PC does not know an action called \"{name}\", so nothing was "
                f"changed. The nearest ones are {', '.join(titles)}.")
    return (f"This PC does not know an action called \"{name}\", so nothing was "
            f"changed. Ask what needs a card to hear the ones it does know.")


def _stem(word: str) -> str:
    """Just enough of a stem to read "sending an email" as "send an email".
    Only for resolving a name to ONE card's exact words - never for guessing."""
    w = word.lower()
    for suffix in ("ing", "es", "s"):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def resolve(name: str):
    """(the real action, whether it came from its card's words) for a name the
    owner or the model used. None when this PC cannot tell what is meant.

    An exact action name wins. Otherwise the words of ONE card may be used
    ("send an email" or "sending an email" for send_email) - never an
    approximate match, and never when two actions share the same words: a
    change is only ever made for something this PC can name exactly."""
    raw = str(name or "").strip()
    if not raw:
        return None
    known = known_actions()
    if raw in known:
        return raw, False
    wanted = {_stem(w) for w in re.findall(r"[a-z0-9]+", raw.lower())
              if w not in _STOPWORDS}
    hits = [a for a in known
            if wanted and wanted == {_stem(w) for w
                                     in re.findall(r"[a-z0-9]+", _title(a).lower())
                                     if w not in _STOPWORDS}]
    if len(hits) == 1:
        return hits[0], True
    return None


# ---------------------------------------------------------------------------
# Reading the policy
# ---------------------------------------------------------------------------


def approval_needs(action: str) -> dict:
    """{"confirmations": 1|2, "windows_hello": bool} for one action.

    FAIL CLOSED: a line that exists but cannot be read as what this module
    writes (a typo, a value of the wrong kind) counts as the STRICTER answer -
    two yeses, and Windows Hello required - so a damaged file can only add
    asking, never remove it. A missing module or file is the shipped default
    (one yes, no extra check), because then no line this module wrote can be
    read at all; the page says so when the file has a line it cannot read.

    No cache: jarvis_framework re-reads the file when it changes on disk
    (that is why an approved change takes effect without a restart), and an
    approval is not a hot path."""
    out = {"confirmations": 1, "windows_hello": False}
    try:
        table = _section(TABLES[CONFIRMATIONS])
    except Exception:
        table = {}
    if action in table:
        raw = table.get(action)
        try:
            out["confirmations"] = 2 if int(raw) >= 2 else 1
        except Exception:
            out["confirmations"] = 2           # cannot read it: stricter
    try:
        hello = _section(TABLES[WINDOWS_HELLO])
    except Exception:
        hello = {}
    if action in hello:
        raw = hello.get(action)
        if isinstance(raw, bool):
            out["windows_hello"] = raw
        else:
            out["windows_hello"] = True        # cannot read it: stricter
    return out


def card_line(action: str) -> bool:
    """Whether the action asks first, from its own line in the settings file."""
    try:
        import jarvis_asks_first as AF
        return AF._tier(action) == "ask"
    except Exception:
        return True


def policy_for(action: str) -> dict:
    """The whole current policy for one action, in plain words and as data."""
    asks = card_line(action)
    needs = approval_needs(action)
    try:
        stamp = jarvis_tier(action)
    except Exception:
        stamp = "ask"
    return {"action": action, "title": _title(action), "tier": stamp,
            "asks": asks, "confirmations": needs["confirmations"],
            "windows_hello": needs["windows_hello"],
            "said": said_for(action)}


def jarvis_tier(action: str) -> str:
    try:
        import jarvis_asks_first as AF
        return AF._tier(action)
    except Exception:
        return "ask"


def said_for(action: str) -> str:
    """One plain sentence: what this action does now, all three dimensions."""
    asks = card_line(action)
    needs = approval_needs(action)
    bits = []
    bits.append("asks you first every time" if asks else "runs without asking you")
    if needs["confirmations"] >= 2:
        bits.append("and takes two yeses")
    if needs["windows_hello"]:
        bits.append("and needs Windows Hello on this PC")
    return "It " + " ".join(bits) + "."


def row_note(action: str) -> str:
    """The extra sentence under a row of "What asks first" - empty when the
    action is at its shipped policy. Both apps draw this note without a
    change: it is the row's existing note field."""
    needs = approval_needs(action)
    bits = []
    if needs["confirmations"] >= 2:
        bits.append("It asks you twice: approve it, then approve it again.")
    if needs["windows_hello"]:
        bits.append("It also needs Windows Hello on this PC for every yes.")
    return " ".join(bits)


def decorate(row: dict) -> dict:
    """Add the policy to one page row (in place), for both apps' read-only
    page. Never a write control: the apps only draw what is already there."""
    action = row.get("action")
    if not action:
        return row
    needs = approval_needs(action)
    row["confirmations"] = needs["confirmations"]
    row["windows_hello"] = needs["windows_hello"]
    note = row_note(action)
    if note:
        row["note"] = ((row.get("note") or "") + " " + note).strip()
    return row


# ---------------------------------------------------------------------------
# Reading it for chat ("what needs a card?", "does X ask twice?")
# ---------------------------------------------------------------------------


def read_request(body, *, known: Optional[Callable[[], set]] = None) -> tuple:
    """The model's read: one action's policy, or the short list worth naming.

    (code, body). Never changes anything, never raises a card."""
    body = body if isinstance(body, dict) else {}
    action = body.get("action")
    known = known or known_actions
    if isinstance(action, str) and action.strip():
        action = action.strip()
        if action not in known():
            resolved = resolve(action)
            if resolved is None:
                return 200, {"ok": True, "known": False,
                             "said": refusal_for_unknown(action),
                             "nearest": nearest(action)}
            action = resolved[0]
        return 200, {"ok": True, "known": True, "policy": policy_for(action)}
    twice, hello, no_card = [], [], []
    try:
        import jarvis_asks_first as AF
        loose = dict(getattr(AF, "LOOSE", {}) or {})
    except Exception:
        loose = {}
    for name in sorted(known()):
        needs = approval_needs(name)
        if needs["confirmations"] >= 2:
            twice.append({"action": name, "title": _title(name)})
        if needs["windows_hello"]:
            hello.append({"action": name, "title": _title(name)})
    for name in sorted(loose):
        try:
            if not card_line(name):
                no_card.append({"action": name, "title": _title(name)})
        except Exception:
            continue
    said = ("Everything else asks you first. "
            if twice or hello or no_card else
            "Every action asks you first; none is set to ask twice or to need "
            "Windows Hello. ")
    return 200, {"ok": True, "known": True, "asks_twice": twice,
                 "needs_windows_hello": hello, "runs_without_a_card": no_card,
                 "said": said}


# ---------------------------------------------------------------------------
# Writing one line of the two extra tables (the jarvis_asks_first.set_tier
# discipline: exactly one line, parsed again before it is written)
# ---------------------------------------------------------------------------


def _parse(text: str) -> dict:
    if _toml is None:
        raise PolicyError("This PC's Python cannot read the settings file (it needs "
                          "Python 3.11 or newer), so nothing was changed")
    try:
        return _toml.loads(text)
    except Exception:
        raise PolicyError("Your settings file has a mistake in it, so nothing was "
                          "changed. Open it in Notepad and fix it first")


def _table_of(doc: dict, table: str) -> dict:
    a = doc.get("autonomy")
    t = a.get(table) if isinstance(a, dict) else None
    return t if isinstance(t, dict) else {}


def _toml_value(field: str, value):
    if field == CONFIRMATIONS:
        return str(int(value))
    return "true" if bool(value) else "false"


def rewrite_policy(text: str, field: str, action: str, value) -> str:
    """`text` with ONE line under the field's table changed, added, or
    removed (value None). Pure: no file is read or written here."""
    if field not in TABLES:
        raise PolicyError("That is not one of the three things this can change")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,60}", action or ""):
        raise PolicyError("That is not an action name")
    if value is not None:
        if field == CONFIRMATIONS and int(value) not in (1, 2):
            raise PolicyError("A second confirmation is either there or it is not")
        if field == WINDOWS_HELLO and not isinstance(value, bool):
            raise PolicyError("Windows Hello is either required or it is not")
    table = TABLES[field]
    before = _parse(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    heads = []
    for i, line in enumerate(lines):
        m = _HEADER.match(line)
        if m is not None and m.group("table") == table:
            heads.append(i)
    if len(heads) > 1:
        raise PolicyError(HAND_EDIT)
    key = re.compile(r"^(?P<lead>[ \t]*(?:" + re.escape(action) + r"|\""
                     + re.escape(action) + r"\"|'" + re.escape(action)
                     + r"')[ \t]*=[ \t]*)(?P<val>[^#\r\n]+?)(?P<rest>[ \t]*(?:#.*)?)$")
    if not heads:
        if value is None:
            return text                       # nothing to remove
        lines.extend(["", f"[autonomy.{table}]",
                      f"{action} = {_toml_value(field, value)}{_INSERTED_NOTE}"])
    else:
        start = heads[0] + 1
        end = next((i for i in range(start, len(lines)) if _ANY_HEADER.match(lines[i])),
                   len(lines))
        hits = [i for i in range(start, end) if key.match(lines[i])]
        if len(hits) > 1:
            raise PolicyError(HAND_EDIT)
        if hits:
            i = hits[0]
            if value is None:
                del lines[i]
            else:
                m = key.match(lines[i])
                lines[i] = f"{m.group('lead')}{_toml_value(field, value)}{m.group('rest')}"
        else:
            if value is None:
                return text                    # already absent: nothing to remove
            keys = [i for i in range(start, end) if _KEY_LINE.match(lines[i])]
            at = (keys[-1] + 1) if keys else start
            lines.insert(at, f"{action} = {_toml_value(field, value)}{_INSERTED_NOTE}")
    out = nl.join(lines)
    after = _parse(out)
    want = json.loads(json.dumps(before, default=str))
    got = json.loads(json.dumps(after, default=str))
    section = want.setdefault("autonomy", {})
    if not isinstance(section, dict):
        raise PolicyError(HAND_EDIT)
    table_before = section.setdefault(table, {})
    if not isinstance(table_before, dict):
        raise PolicyError(HAND_EDIT)
    table_after = got.get("autonomy", {}).get(table, {}) if isinstance(
        got.get("autonomy"), dict) else {}
    if value is None:
        table_before.pop(action, None)
    else:
        table_before[action] = int(value) if field == CONFIRMATIONS else bool(value)
    # An empty table may be written as {} or left out; both are the same
    # settings, so normalise that one case on both sides.
    if not table_before:
        section.pop(table, None)
    if isinstance(got.get("autonomy"), dict) and not table_after:
        got["autonomy"].pop(table, None)
    if got != want:
        raise PolicyError(HAND_EDIT)
    return out


def set_policy(action: str, field: str, value, *, path: Optional[Path] = None) -> dict:
    """Change ONE line of the two extra tables, atomically. value None removes
    it. {"ok": True, "from": ..., "to": ...}. Raises PolicyError."""
    p = path or _config_path()
    if p is None or not Path(p).is_file():
        raise PolicyError("Jarvis could not find your settings file, so nothing was "
                          "changed")
    p = Path(p)
    with _FILE_LOCK:
        try:
            raw = p.read_bytes()
        except OSError as exc:
            raise PolicyError(f"Your settings file could not be read "
                              f"({type(exc).__name__}), so nothing was changed")
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
        except UnicodeDecodeError:
            raise PolicyError(HAND_EDIT)
        old = _table_of(_parse(text), TABLES[field]).get(action)
        new = rewrite_policy(text, field, action, value)
        data = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
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
            raise PolicyError(f"Your settings file could not be written "
                              f"({type(exc).__name__}), so nothing was changed")
    _reload()
    return {"ok": True, "from": old, "to": value}


_FILE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# The card - loosening only, the PC only, one card plus Windows Hello
# ---------------------------------------------------------------------------

PENDING_WORDS = {
    "loosened": "You approved the card, so that is changed.",
    "denied": "The card was turned down, so nothing changed.",
    "timed_out": "Nobody answered the card in time, so nothing changed.",
    "refused": "Your PC's settings do not let this be approved, so nothing changed.",
    "withdrawn": "You made it ask more while the card waited, so approving it "
                 "changed nothing.",
    "failed": "It was approved, but the settings file could not be changed, so "
              "nothing changed.",
}
PC_ONLY = ("Letting Jarvis ask less can only be done on the PC, with an approval "
           "card and Windows Hello.")
NO_OWNER_CHECK = ("Your PC's Jarvis cannot ask Windows Hello itself yet, so nothing "
                  "can be loosened from the app - run apply-patches.ps1 on the PC.")
ONE_AT_A_TIME = "A card that would ask less is already waiting - answer it first."


def _keeps(action: str, field: str) -> str:
    """What still happens after a loosening, said in one sentence."""
    needs = approval_needs(action)
    bits = []
    if field != CARD and card_line(action):
        bits.append("It still asks you first every time.")
    if field != CONFIRMATIONS and needs["confirmations"] >= 2:
        bits.append("It still takes two yeses.")
    if field != WINDOWS_HELLO and needs["windows_hello"]:
        bits.append("It still needs Windows Hello on this PC.")
    return " ".join(bits)


def loosen_card(action: str, field: str) -> str:
    """ONE card's words: exactly what stops being asked, for one action.

    IT MUST NOT NAME A FILE THE GATE PROTECTS. This text is handed to
    jarvis_gate.check() as the card's prompt, and the gate reads that prompt
    for its own protected names before it looks at the tier table - a prompt
    that names one is refused at "never", so no card is raised at all (the
    bug jarvis_asks_first.loosen_card records). It names no file.
    """
    title = _title(action)
    low = _lower_title(action)
    if field == CARD:
        first = f"Let Jarvis {low} without asking you first?"
        stops = (f"From now on Jarvis will {low} without an approval card. Nothing "
                 f"else in your settings file changes.")
        keep = ("It still only runs when you ask it to, and Jarvis never does "
                "anything by itself.")
    elif field == CONFIRMATIONS:
        first = f"Stop asking you twice when you ask Jarvis to {low}?"
        stops = (f"From now on one yes is enough when you ask Jarvis to {low}. The "
                 f"second confirmation goes.")
        keep = ""
    else:
        first = f"Stop needing Windows Hello when you ask Jarvis to {low}?"
        stops = (f"From now on you approve \"{title}\" with the card alone, on this "
                 f"PC or your phone.")
        keep = ""
    keeps = " ".join(x for x in (keep, _keeps(action, field)) if x).strip()
    return "\n".join([
        first,
        "",
        stops + " This changes one line of your settings file on this PC; nothing "
        "else in it changes.",
        "",
        keeps,
        "",
        "Approving it needs Windows Hello on this PC. If you did not just do this, "
        "say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-approval-policy-card", daemon=True).start()


def _owner_check_armed() -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.armed())
    except Exception:
        return False


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


_L_LOCK = threading.Lock()
#: The one waiting card, if any: {"id", "action", "field", "since"}. There is
#: never more than one, so no press can stack two loosening cards up.
_L_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}
#: Held from an approved card's "was it withdrawn?" check through writing the
#: line, and from a tightening press's withdraw through ITS write - so a
#: tightening press in between is never overwritten by the card. Always taken
#: BEFORE _L_LOCK.
_L_SWITCH = threading.Lock()


def _finish(pid: str, action: str, field: str, outcome: str, why: str = "") -> None:
    with _L_LOCK:
        if _L_STATE["pending"].get("id") == pid:
            _L_STATE["pending"].clear()
        _L_STATE["withdrawn"].discard(pid)
        _L_STATE["last"].clear()
        _L_STATE["last"].update(outcome=outcome, action=action, field=field,
                                why=why, at=time.time(),
                                message=PENDING_WORDS.get(outcome, ""))
    _audit("approval_policy.card", {"action": action, "field": field,
                                    "outcome": outcome})


def _decide(pid: str, action: str, field: str, gate: Callable, tier_of: Callable,
            write: Callable) -> None:
    prompt = loosen_card(action, field)
    detail = {"text": prompt,
              "what": f"{_lower_title(action)} stopping: {field}",
              "setting": action, "field": field, "leaves_this_pc": False}
    try:
        v = gate(ACTION, detail, prompt)
    except Exception as exc:
        return _finish(pid, action, field, "refused",
                       f"the approval card failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(pid, action, field, "refused",
                       f"the card answered at tier {vtier!r}, which is not a "
                       f"person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, action, field, outcome)
        return _finish(pid, action, field, "refused",
                       str(getattr(v, "reason", "refused"))[:200])
    with _L_SWITCH:
        with _L_LOCK:
            withdrawn = pid in _L_STATE["withdrawn"]
        if withdrawn:
            return _finish(pid, action, field, "withdrawn")
        try:
            write(action, field, None)
        except PolicyError as exc:
            return _finish(pid, action, field, "failed", str(exc))
        except Exception as exc:
            return _finish(pid, action, field, "failed", type(exc).__name__)
    _audit("approval_policy.changed", {"action": action, "field": field,
                                       "to": None, "how": "loosened"})
    _finish(pid, action, field, "loosened")


def _here(here: Optional[bool], peer, local) -> bool:
    return bool(here) if here is not None else _from_this_pc(peer, local)


def _withdraw(action: str, field: str) -> None:
    """A tightening press withdraws a waiting card for the same one thing, so
    an approval that arrives afterwards changes nothing."""
    with _L_LOCK:
        p = _L_STATE["pending"]
        if p and p.get("action") == action and p.get("field") == field:
            _L_STATE["withdrawn"].add(p["id"])
            p.clear()


def _tighten(action: str, field: str, value, write: Callable,
             here: bool) -> tuple:
    """Instant, cardless: it only makes Jarvis ask more."""
    with _L_SWITCH:
        _withdraw(action, field)
        try:
            out = write(action, field, value)
        except PolicyError as exc:
            return 409, {"ok": False, "error": str(exc) + "."}
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not change it "
                                               f"({type(exc).__name__})"}
    _audit("approval_policy.changed", {"action": action, "field": field,
                                       "to": value, "how": "stricter"})
    return 200, {"ok": True, "changed": bool(out.get("changed", True)),
                 "field": field, "action": action,
                 "message": "Done. " + said_for(action)}


def request_change(body, *, peer=None, local=None, gate: Optional[Callable] = None,
                   tier_of: Optional[Callable[[str], str]] = None,
                   spawn: Optional[Callable] = None, write: Optional[Callable] = None,
                   armed: Optional[Callable[[], bool]] = None,
                   here: Optional[bool] = None,
                   known: Optional[Callable[[], set]] = None) -> tuple:
    """The whole change path for one action and one dimension. (code, body).

    `card` delegates to jarvis_asks_first.request_tier, so the existing rules
    for what may be loosened, and the card's own words, are the same ones the
    page already uses. `confirmations` and `windows_hello` follow the same
    direction rule here: more is instant, less is one card plus Windows Hello
    on the PC, and never anything in bulk."""
    gate = gate or _gate
    AF = None
    try:
        import jarvis_asks_first as AF          # noqa: F811 - the name is used below
        tier_of = tier_of or AF._tier
    except Exception:
        tier_of = tier_of or (lambda a: "ask")
    spawn = spawn or _spawn
    armed = armed or _owner_check_armed
    known = known or known_actions
    if write is None:
        def write(action, field, value):
            if field == CARD:
                ask = value != "auto"
                return AF.set_tier(action, "ask" if ask else AF.LOOSE[action])
            return set_policy(action, field, value)
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Say which action, and what to change."}
    unexpected = sorted(str(k) for k in body if str(k) not in ("action", "field", "value"))
    if unexpected:
        # ONE THING AT A TIME, enforced rather than promised: a second
        # dimension in the same body is refused before anything is read or
        # raised, so no control can change several things around one yes.
        return 400, {"ok": False, "error": (
            "One action and one thing at a time, so nothing was changed. Ask "
            "again for each one separately."), "one_at_a_time": True}
    action = body.get("action")
    field = body.get("field")
    value = body.get("value")
    if not isinstance(action, str) or not action.strip():
        return 400, {"ok": False, "error": "Say which action, one at a time."}
    action = action.strip()
    if field not in FIELDS:
        return 400, {"ok": False, "error": (
            "Say which of the three to change: whether it gets a card, how many "
            "yeses it takes, or whether it needs Windows Hello.")}
    # The value, in the shape the field uses. Strings because that is what a
    # model writes in a tool call; a person's sentence is turned into these by
    # the model, never by this module.
    if field == CARD:
        if value not in ("ask", "auto", True, False):
            return 400, {"ok": False, "error": "Whether to ask, answer ask or auto."}
        value = "ask" if value in ("ask", True) else "auto"
    elif field == CONFIRMATIONS:
        if value in (1, 2):
            value = int(value)
        elif str(value).strip() in ("1", "2"):
            value = int(str(value).strip())
        else:
            return 400, {"ok": False, "error": "One yes or two, answer 1 or 2."}
    else:
        if isinstance(value, bool):
            pass
        elif str(value).strip().lower() in ("true", "yes", "1", "on"):
            value = True
        elif str(value).strip().lower() in ("false", "no", "0", "off"):
            value = False
        else:
            return 400, {"ok": False, "error": "Windows Hello is yes or no."}
    if action not in known():
        resolved = resolve(action)
        if resolved is None:
            return 409, {"ok": False, "error": refusal_for_unknown(action),
                         "unknown_action": True, "nearest": nearest(action)}
        action = resolved[0]
    here = _here(here, peer, local)
    # ---- the card dimension: the existing rule, not a second one ----------
    if field == CARD:
        try:
            code, out = AF.request_tier({"action": action,
                                         "ask": value == "ask"},
                                        peer=peer, local=local, gate=gate,
                                        tier_of=tier_of, spawn=spawn,
                                        armed=armed, here=here)
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not change it "
                                               f"({type(exc).__name__})"}
        out = dict(out or {})
        out.setdefault("field", CARD)
        return code, out
    now = approval_needs(action)
    if field == CONFIRMATIONS:
        wanted = 2 if value == 2 else 1
        tighter = wanted == 2
        if wanted == 2 and not has_written_title(action):
            # The second yes is a card the owner must be able to read. An
            # action with no written title can only ask once, normally.
            return 409, {"ok": False, "error": (
                f"Jarvis has no written words for \"{action}\", so it cannot put a "
                f"second confirmation on it. Nothing was changed.")}
    else:
        wanted = bool(value)
        tighter = wanted is True
        if wanted and not has_written_title(action):
            return 409, {"ok": False, "error": (
                f"Jarvis has no written words for \"{action}\", so it cannot ask "
                f"Windows Hello for it. Nothing was changed.")}
        if wanted and not here:
            return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if now[field] == wanted:
        return 200, {"ok": True, "changed": False, "field": field,
                     "action": action, "message": said_for(action)}
    if tighter:
        # Instant and cardless: it only makes Jarvis ask more.
        return _tighten(action, field, wanted, write, here)
    # ---- loosening: the PC only, ONE card plus Windows Hello --------------
    if not here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not armed():
        return 503, {"ok": False, "error": NO_OWNER_CHECK}
    t = tier_of(ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"The card that would ask less is set to {t!r} in the settings file; it "
            f"must ask, so nothing was changed")}
    with _L_LOCK:
        if _L_STATE["pending"]:
            return 409, {"ok": False, "error": ONE_AT_A_TIME}
        pid = uuid.uuid4().hex
        _L_STATE["pending"].update(id=pid, action=action, field=field,
                                   since=time.time())
    try:
        spawn(lambda: _decide(pid, action, field, gate, tier_of, write))
    except Exception:
        with _L_LOCK:
            _L_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "field": field, "action": action,
                 "message": "Waiting for your approval. Approve the card on this PC - "
                            "it asks Windows Hello - and that is changed."}


def last() -> Optional[dict]:
    with _L_LOCK:
        got = dict(_L_STATE["last"]) or None
    return got


def waiting() -> Optional[dict]:
    with _L_LOCK:
        p = dict(_L_STATE["pending"])
    if not p:
        return None
    return {"action": p.get("action"), "field": p.get("field"),
            "title": _title(str(p.get("action") or ""))}


def _reset_for_tests() -> None:
    with _L_LOCK:
        _L_STATE["pending"].clear()
        _L_STATE["withdrawn"].clear()
        _L_STATE["last"].clear()
