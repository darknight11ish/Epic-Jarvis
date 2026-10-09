"""
jarvis_arbiter.py - the one place that decides whether to interrupt you.

Every feature in this project spends the owner's attention and, until this
module existed, every feature decided for itself how much. The initiative
engine speaks a finding. A Long Fuse job finishes and announces it. The model
steward finds a newer model. The gate raises a card. Each of those is
reasonable on its own; together they are a machine for interrupting somebody
all day, and the usual outcome is that the owner turns the lot off - which
costs them the one notification that mattered along with the forty that did
not.

So: nothing unsolicited reaches a client directly any more. It is handed to
this module, which holds a budget, and what does not fit the budget drains
into one daily digest.

Three things it is NOT, each for a reason:

  * It is not in the event bus. The bus fans out to three clients with three
    different ideas of what an interruption is - a tray balloon, a phone
    notification, a spoken sentence. The decision has to be made once, before
    that, or each client re-decides it differently.

  * It is not in the initiative engine. That engine is one producer among
    several, and a budget that only one producer respects is not a budget.

  * It does not touch anything you ASKED for. A gate card for an action you
    just requested is foreground: you are already here, waiting, and making
    that wait on a token bucket would be absurd. `solicited=True` bypasses
    everything. The budget governs things that arrive when nobody asked.

The digest deliberately has no bulk action and no way to approve anything.
A ranked list of pending approvals with one tap each was the first design and
it is exactly the "just approve these" pattern that jarvis_content_risk exists
to flag when an attacker uses it; building it in-house does not make it
better. The digest LISTS an approval and says which card to open. Approving
still happens one card at a time, in the gate, where the consequence and the
reason are shown.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

DB_PATH = Path(os.environ.get("JARVIS_ARBITER_DB", str(_CFG_DIR / "arbiter.db")))

_LOCK = threading.RLock()
_inited = False


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("arbiter", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Channels, priorities, and what they actually mean
# --------------------------------------------------------------------------
# SPEAK is the expensive one: audio, unprompted, in the room. It is what the
# budget counts. NOTIFY is a badge or a tray count - visible when the owner
# next looks, costing nothing until then. DIGEST is the overflow: it waits for
# the once-a-day brief.
SPEAK, NOTIFY, DIGEST, DROPPED = "speak", "notify", "digest", "dropped"

# Priority decides ORDER inside the digest and nothing else. It deliberately
# does not buy a bigger budget: a producer that wants to be heard more would
# simply always say "high", and a scale everyone tops out on is not a scale.
# The one exception is `critical`, which is for a fact about the machine the
# owner cannot act on later - the disk is full, the model will not load - and
# which the config can cap.
PRIORITIES = ("critical", "high", "normal", "low")
_PRI_RANK = {p: i for i, p in enumerate(PRIORITIES)}

# What kind of thing it is. Used for ranking the digest by CONSEQUENCE rather
# than by how loudly the item asks. See _rank().
KINDS = ("approval", "job", "finding", "steward", "reminder", "other")
_KIND_RANK = {"approval": 0, "job": 1, "steward": 2, "finding": 3,
              "reminder": 4, "other": 5}


def _connect() -> sqlite3.Connection:
    """Always inside `with closing(_connect()) as c:`.

    `isolation_level=None` for the same reason jarvis_gate.py uses it: without
    it, sqlite3 opens an implicit transaction on the first INSERT and nothing
    is written until somebody calls commit(). Every write in this module is a
    single statement, so autocommit is both correct and one fewer thing to get
    wrong on a path that decides whether the owner is interrupted.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10.0, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _inited
    with _LOCK:
        if _inited:
            return
        with closing(_connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS intents (
                    id        TEXT PRIMARY KEY,
                    source    TEXT NOT NULL,
                    kind      TEXT NOT NULL,
                    title     TEXT NOT NULL,
                    body      TEXT,
                    priority  TEXT NOT NULL,
                    ref       TEXT,           -- an id in another module
                    created   REAL NOT NULL,
                    expires   REAL,
                    channel   TEXT NOT NULL,  -- speak|notify|digest|dropped
                    state     TEXT NOT NULL,  -- queued|delivered|expired
                    delivered REAL
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_intent_state"
                      " ON intents(state, created)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS spend (
                    day   TEXT PRIMARY KEY,
                    spent INTEGER NOT NULL,
                    muted INTEGER NOT NULL DEFAULT 0
                )""")
        _inited = True


def _today(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now or time.time()))


# --------------------------------------------------------------------------
#   The budget
# --------------------------------------------------------------------------

def _limit() -> int:
    try:
        return max(0, int(_cfg("spoken_per_day", 3)))
    except (TypeError, ValueError):
        return 3


def _blocked_reason() -> Optional[str]:
    """Why the budget is zero right now regardless of what is left in it.

    Quiet and Standby are the owner saying "not now" in the plainest terms
    this system has, and a session lock says they are not at the desk. Speaking
    into an empty room is not free: it is either heard by somebody else or not
    heard at all, and both are worse than waiting.
    """
    try:
        import jarvis_power
        mode = jarvis_power.current()
        if mode in ("quiet", "standby"):
            return f"power mode is {mode}"
    except Exception:
        pass
    if _session_locked():
        return "the session is locked"
    return None


def _session_locked() -> bool:
    """Is the owner away from the machine?

    This replaces a webcam. An earlier design used face detection to decide
    whether to speak; it was killed because the operating system already knows
    the answer, and asking it costs no camera handle for a compromise to
    inherit and creates no record of who else was in the room.

    On Windows the real implementation is GetLastInputInfo plus the session
    lock/unlock notifications. There is no portable stdlib call for either, so
    this reads a small file that the desktop shell writes and returns False
    when it is absent - an unknown answer must not silence Jarvis, because a
    rule that fails to "never speak" is a rule that looks broken.
    """
    try:
        p = Path(os.environ.get("JARVIS_PRESENCE_FILE",
                                str(_CFG_DIR / "presence.json")))
        d = json.loads(p.read_text("utf-8"))
        if bool(d.get("locked")):
            return True
        idle = float(d.get("idle_seconds", 0) or 0)
        away_after = float(_cfg("away_after_idle_minutes", 15) or 15) * 60.0
        return away_after > 0 and idle >= away_after
    except Exception:
        return False


def budget(now: Optional[float] = None) -> dict:
    """What is left today, and why it might be zero anyway."""
    _init()
    day = _today(now)
    with closing(_connect()) as c:
        row = c.execute("SELECT spent, muted FROM spend WHERE day=?", (day,)).fetchone()
    spent = int(row["spent"]) if row else 0
    muted = bool(row["muted"]) if row else False
    limit = _limit()
    blocked = "muted until tomorrow" if muted else _blocked_reason()
    remaining = 0 if blocked else max(0, limit - spent)
    return {"limit": limit, "spent": spent, "remaining": remaining,
            "muted": muted, "blocked_by": blocked,
            "resets": "the start of tomorrow", "day": day}


def mute_until_tomorrow(now: Optional[float] = None) -> dict:
    """The owner's "not now" for the rest of the day. Deliberately not
    "mute forever": a mute with no end is how a feature gets switched off
    once and never reconsidered, and this one has a natural end."""
    _init()
    day = _today(now)
    with closing(_connect()) as c:
        c.execute("INSERT INTO spend (day, spent, muted) VALUES (?,0,1) "
                  "ON CONFLICT(day) DO UPDATE SET muted=1", (day,))
    _audit("arbiter.muted", {"day": day})
    return budget(now)


def unmute(now: Optional[float] = None) -> dict:
    _init()
    with closing(_connect()) as c:
        c.execute("UPDATE spend SET muted=0 WHERE day=?", (_today(now),))
    return budget(now)


# --------------------------------------------------------------------------
#   The two numbers the Brain shows - changeable since 2026-10-08
# --------------------------------------------------------------------------
# "How much Jarvis may interrupt you" is a card in the Brain on the PC. Until
# 2026-10-08 it was readable and nothing else: an audit of every feature
# against the real settings surface found the owner could see the budget and
# change it nowhere - the worst gap it found. The numbers live in
# jarvis-framework.toml's [arbiter] table, so changing one is a one-line edit
# of the owner's own settings file, with every other byte of it left alone:
# comments, spacing, CRLF endings and a byte-order mark included, the same
# promise jarvis_asks_first.set_tier makes for the tier lines.
#
# The range each number may take is the one the file's own comment already
# gives it. Nothing here is invented.
SPOKEN_PER_DAY_MIN, SPOKEN_PER_DAY_MAX = 0, 24
DIGEST_HOUR_MIN, DIGEST_HOUR_MAX = 0, 23

_SECTION_LINE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_NUMBER_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
                          r"(?P<eq>\s*=\s*)(?P<value>[^#\r\n]*?)(?P<rest>\s*(?:#.*)?)$")


class SettingsFileError(Exception):
    """The owner's settings file could not be read or written, so nothing was
    changed. The message is shown to the owner as it is, in plain words."""


def _as_int(raw: str) -> Optional[int]:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


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


def _rewrite_number(text: str, key: str, value: int,
                    *, section: str = "arbiter") -> tuple:
    """(new text, the old value or None). Only that one line moves.

    The line keeps its own indentation and its own trailing comment; when the
    owner has deleted the line, it is added back at the end of the table (or,
    with no table at all, under a new one)."""
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
        lines.append(f"{tail}[{section}]{ending}{key} = {value}{ending}")
        return "".join(lines), None
    last = start
    for i in range(start + 1, len(lines)):
        bare = lines[i].rstrip("\r\n")
        if _SECTION_LINE.match(bare):
            break                       # the next table starts here
        if not bare.strip():
            continue
        m = _NUMBER_LINE.match(bare)
        if m and m.group("key") == key:
            old = _as_int(m.group("value"))
            lines[i] = (f"{m.group('indent')}{key} = {value}"
                        f"{m.group('rest')}{ending}")
            return "".join(lines), old
        last = i
    lines.insert(last + 1, f"{key} = {value}{ending}")
    return "".join(lines), None


def _set_number(key: str, value, *, low: int, high: int,
                path: Optional[Path] = None) -> dict:
    """Change ONE number under [arbiter], atomically. Raises SettingsFileError."""
    n = _as_int(value)
    if n is None:
        raise SettingsFileError(f"\"{value}\" is not a whole number")
    if not low <= n <= high:
        raise SettingsFileError(f"That has to be a whole number between "
                                f"{low} and {high}")
    p = path or _toml_path()
    if p is None or not Path(p).is_file():
        raise SettingsFileError("Jarvis could not find your settings file "
                                "(jarvis-framework.toml), so nothing was changed")
    p = Path(p)
    with _LOCK:
        try:
            raw = p.read_bytes()
        except OSError as exc:
            raise SettingsFileError(f"Your settings file could not be read "
                                    f"({type(exc).__name__}), so nothing was changed")
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
        except UnicodeDecodeError:
            raise SettingsFileError("Your settings file is not plain text, so "
                                    "nothing was changed")
        new, old = _rewrite_number(text, key, n)
        if new == text:
            return {"ok": True, "from": old, "to": n, "changed": False}
        data = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp",
                                   dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            try:
                # The file's own permissions, not the temporary file's.
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
    return {"ok": True, "from": old, "to": n, "changed": True}


def set_spoken_per_day(count, *, path: Optional[Path] = None) -> dict:
    """How many times a day Jarvis may speak up unasked. 0 leaves the digest.

    {"ok", "from", "to", "changed", "loosening"} - and RAISING this is a
    loosening: the owner is interrupted more often. The answer says so rather
    than deciding: the route, and the two apps' own screens, are where a card
    is raised (an approval card for a loosening, nothing at all for a
    tightening - the same rule every other setting follows)."""
    before = _limit()
    out = _set_number("spoken_per_day", count,
                      low=SPOKEN_PER_DAY_MIN, high=SPOKEN_PER_DAY_MAX, path=path)
    out["loosening"] = int(out["to"]) > int(before)
    if out.get("changed"):
        _audit("arbiter.budget_changed", {"from": before, "to": out["to"]})
    return out


def set_digest_hour(hour, *, path: Optional[Path] = None) -> dict:
    """When the once-a-day brief arrives, as an hour 0-23.

    Never a loosening: it changes when the owner reads the overflow, not how
    much noise Jarvis makes in the room."""
    out = _set_number("digest_hour", hour,
                      low=DIGEST_HOUR_MIN, high=DIGEST_HOUR_MAX, path=path)
    out["loosening"] = False
    if out.get("changed"):
        _audit("arbiter.digest_hour_changed", {"to": out["to"]})
    return out


# --------------------------------------------------------------------------
#   The route: POST /api/attention/settings
# --------------------------------------------------------------------------
# The shape is jarvis_chatbot_limits.py's, deliberately: a numeric setting with
# a direction that matters. Turning the budget DOWN (or moving the digest) is
# applied at once, with no card - it only ever makes Jarvis quieter. Turning it
# UP is a loosening: the owner is interrupted more often, so it goes through
# ONE approval card first, and nothing is written until that card is approved.
#
# WHICH WAY IT IS comes from the NUMBER against the budget already in force,
# never from anything the caller sends. A page (or anything else that can reach
# the route) does not get to call a raise a lowering and skip the card; that
# exact hole was found and fixed in the money limits on 2026-10-07 (bug audit
# finding E2), so this module is written without it rather than after it.
#
# The gate action's name carries the meaning: `raise_attention_budget`. It is
# deliberately NOT in an owner's tier table, so it resolves to the file's
# unknown-action tier - "ask" in the shipped config - and a PC whose Jarvis
# cannot ask refuses the raise (503) instead of applying it.
RAISE_ACTION = "raise_attention_budget"

_STATE: dict = {"gate": None, "tier_of": None}


def configure(*, gate=None, tier_of=None) -> None:
    """Tests only: stand in for the approval gate and the tier table."""
    _STATE.update(gate=gate, tier_of=tier_of)


def _dep(name: str, default):
    return _STATE.get(name) or default


def _person_said_yes(v) -> bool:
    """The same reading jarvis_chatbot_limits.py uses: the tier must really be
    "ask" and the outcome must really be an approval on this PC."""
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


def _raise_budget_card(old: int, new: int) -> tuple:
    """The card for raising the budget, and the yes. (None, said) when it went
    through; ((status, body), "") when it did not."""
    prompt = (f"Let Jarvis speak up to {new} times a day, instead of {old}? "
              f"That is more interruptions, not fewer.")
    detail = {"text": prompt,
              "what": "let Jarvis interrupt you more often",
              "was": old, "now": new,
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
        words = {"denied": "You said no, so Jarvis still speaks up to "
                           f"{old} times a day.",
                 "timed_out": "The card was not answered in time, so Jarvis still "
                              f"speaks up to {old} times a day."}
        return (409, {"ok": False, "error": words.get(
            outcome, "That was not approved, so Jarvis still speaks up to "
                     f"{old} times a day.")}), ""
    return None, f"Jarvis may now speak up to {new} times a day."


def change(body, *, peer=None, local=None) -> tuple:
    """POST /api/attention/settings - the two numbers the Brain shows.

    {"spoken_per_day": 6} or {"digest_hour": 9}. One number at a time: the two
    are different kinds of thing, and a card that asked about both at once
    would be a card nobody could answer well."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send the number you want to change."}
    keys = [k for k in ("spoken_per_day", "digest_hour") if k in body]
    if len(keys) != 1:
        return 400, {"ok": False,
                     "error": "Send one of these: spoken_per_day, digest_hour."}
    key = keys[0]
    if key == "digest_hour":
        try:
            out = set_digest_hour(body[key])
        except SettingsFileError as exc:
            return 400, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "changed": out.get("changed", True),
                     "loosening": False, "from": out.get("from"),
                     "to": out.get("to"),
                     "said": f"The morning brief arrives at {int(out['to']):02d}:00 now."}

    # spoken_per_day. The NUMBER decides the direction, not the caller.
    raw = _as_int(body[key])
    if raw is None:
        return 400, {"ok": False, "error": f"\"{body[key]}\" is not a whole number."}
    if not SPOKEN_PER_DAY_MIN <= raw <= SPOKEN_PER_DAY_MAX:
        return 400, {"ok": False, "error": "That has to be a whole number between "
                                           f"{SPOKEN_PER_DAY_MIN} and "
                                           f"{SPOKEN_PER_DAY_MAX}."}
    old = _limit()
    raised = raw > old
    said = ""
    if raised:
        refused, said = _raise_budget_card(old, raw)
        if refused is not None:
            _audit("arbiter.budget_card", {"from": old, "to": raw, "outcome": "not_approved"})
            return refused
    try:
        out = set_spoken_per_day(raw)
    except SettingsFileError as exc:
        return 400, {"ok": False, "error": str(exc)}
    if not said:
        said = ("Jarvis will not speak up on its own today."
                if int(out["to"]) == 0 else
                f"Jarvis may speak up to {int(out['to'])} times a day.")
    return 200, {"ok": True, "changed": out.get("changed", True),
                 "loosening": raised, "approved": raised,
                 "from": out.get("from"), "to": out.get("to"), "said": said}


def handle_post(route: str, body, *, peer=None, local=None) -> tuple:
    """POST /api/attention/settings (the HUD's own route calls this)."""
    if route != "/api/attention/settings":
        return 404, {"error": "no such route"}
    return change(body, peer=peer, local=local)


def _spend(now: Optional[float] = None) -> bool:
    """Take one token. Returns False if there was none, without spending.

    The read and the write are one statement guarded on the count, so two
    producers firing at the same moment cannot both be told yes when only one
    token was left.

    The blocked check has to be HERE and not only in budget(): budget() is a
    report and this is the decision, and an earlier version had the reason
    computed in the report while the decision consulted nothing but the
    counter - so Quiet, Standby and a locked session all read as "blocked" on
    every screen while Jarvis carried on speaking. A number shown to the owner
    and a number the code acts on have to be the same number.
    """
    _init()
    if _blocked_reason():
        return False
    day = _today(now)
    limit = _limit()
    with closing(_connect()) as c:
        c.execute("INSERT OR IGNORE INTO spend (day, spent, muted) VALUES (?,0,0)", (day,))
        cur = c.execute("UPDATE spend SET spent = spent + 1 "
                        "WHERE day=? AND muted=0 AND spent < ?", (day, limit))
        return cur.rowcount > 0


# --------------------------------------------------------------------------
#   Delivering
# --------------------------------------------------------------------------

@dataclass
class Decision:
    id: str
    channel: str
    reason: str
    spoken: bool
    budget: dict

    def as_dict(self) -> dict:
        return asdict(self)


def deliver(source: str, title: str, body: str = "", *,
            kind: str = "finding", priority: str = "normal",
            can_defer: bool = True, expires: Optional[float] = None,
            ref: str = "", solicited: bool = False,
            want: str = SPEAK, now: Optional[float] = None) -> Decision:
    """Ask to reach the owner. The answer is one of four channels.

    `solicited=True` is for anything the owner is currently waiting on - a
    gate card for the action they just requested, an answer to a question they
    just asked. It skips the budget entirely, is never queued, and is never
    counted. Producers must not set it to get around the budget; there is a
    test asserting the initiative engine's own findings never do.

    `can_defer=False` says this stops being useful if it waits. It does NOT
    buy a token - it means that when there is no token, the item is dropped
    rather than put in a digest that will show it tomorrow when it is no
    longer true. A stale "your build is failing" from yesterday is worse than
    nothing, because acting on it wastes a real minute.
    """
    _init()
    now = time.time() if now is None else now
    kind = kind if kind in KINDS else "other"
    priority = priority if priority in PRIORITIES else "normal"
    iid = "i-" + uuid.uuid4().hex[:12]

    if solicited:
        # Not recorded, not counted, not queueable. The owner is here.
        _audit("arbiter.foreground", {"source": source, "kind": kind})
        return Decision(iid, want, "you asked for this", want == SPEAK,
                        budget(now))

    row = (iid, str(source)[:120], kind, str(title)[:300], str(body)[:4000],
           priority, str(ref)[:120], now, expires)

    def record(channel: str, state: str) -> None:
        with closing(_connect()) as c:
            c.execute("INSERT INTO intents (id,source,kind,title,body,priority,"
                      "ref,created,expires,channel,state,delivered)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      row + (channel, state, now if state != "queued" else None))

    if want != SPEAK:
        record(NOTIFY, "delivered")
        return Decision(iid, NOTIFY, "a badge costs nothing until you look",
                        False, budget(now))

    if _spend(now):
        record(SPEAK, "delivered")
        b = budget(now)
        _audit("arbiter.spoke", {"source": source, "kind": kind,
                                 "remaining": b["remaining"]})
        _publish_state(b)
        return Decision(iid, SPEAK, "within today's budget", True, b)

    b = budget(now)
    if not can_defer:
        record(DROPPED, "expired")
        _audit("arbiter.dropped", {"source": source, "kind": kind,
                                   "why": b["blocked_by"] or "budget spent"})
        return Decision(iid, DROPPED,
                        "this stops being true if it waits, and there was no "
                        "interruption left to spend on it", False, b)

    record(DIGEST, "queued")
    _publish_state(b)
    return Decision(iid, DIGEST,
                    (b["blocked_by"] or "today's interruptions are spent")
                    + "; it is in the digest", False, b)


# --------------------------------------------------------------------------
#   The digest
# --------------------------------------------------------------------------

def _rank(row: dict) -> tuple:
    """Order by CONSEQUENCE, never by urgency.

    An item does not move up the list because its own text says it is urgent.
    That is the whole attack jarvis_content_risk watches for, and a ranking
    function that rewards urgency would implement it for the attacker. So the
    key is: what kind of thing it is, then the priority a PRODUCER set (which
    is code, not content), then age.
    """
    return (_KIND_RANK.get(row["kind"], 9),
            _PRI_RANK.get(row["priority"], 9),
            row["created"])


def digest(limit: int = 50, now: Optional[float] = None) -> dict:
    """Everything waiting, ranked, with nothing resolvable from here.

    Note what this returns for an approval: an id, a title, and
    `opens_card: True`. It does not return the approval's detail and there is
    no function in this module that decides one. If a decision is worth a
    gate, it is worth one tap each - batching is how a gesture stops being a
    decision.
    """
    _init()
    now = time.time() if now is None else now
    expire(now)
    with closing(_connect()) as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM intents WHERE state='queued' ORDER BY created").fetchall()]
    rows.sort(key=_rank)
    items = []
    for r in rows[:limit]:
        item = {"id": r["id"], "kind": r["kind"], "source": r["source"],
                "title": r["title"], "priority": r["priority"],
                "created": r["created"], "ref": r["ref"] or ""}
        if r["kind"] == "approval":
            item["opens_card"] = True
            item["body"] = ""            # the card shows it, in the gate
        else:
            item["opens_card"] = False
            item["body"] = r["body"] or ""
        items.append(item)
    return {"items": items, "count": len(rows), "shown": len(items),
            "budget": budget(now), "hour": _digest_hour(),
            "note": ("Approvals open their own card. There is no approve-all, "
                     "here or anywhere else.")}


def _digest_hour() -> int:
    try:
        return max(0, min(23, int(_cfg("digest_hour", 18))))
    except (TypeError, ValueError):
        return 18


def digest_due(now: Optional[float] = None) -> bool:
    """True once a day, at the chosen hour, and only if there is something in
    it. A digest that arrives empty teaches the owner it is not worth opening.
    """
    _init()
    now = time.time() if now is None else now
    lt = time.localtime(now)
    if lt.tm_hour < _digest_hour():
        return False
    with closing(_connect()) as c:
        row = c.execute("SELECT COUNT(*) n FROM intents WHERE state='queued'").fetchone()
        if not row or not row["n"]:
            return False
        last = c.execute("SELECT MAX(delivered) d FROM intents "
                         "WHERE state='delivered' AND channel=?", (DIGEST,)).fetchone()
    if last and last["d"] and _today(last["d"]) == _today(now):
        return False
    return True


def mark_digest_delivered(ids: Optional[list] = None,
                          now: Optional[float] = None) -> int:
    """The owner has seen these. Called after the digest is actually shown,
    not when it is generated - a digest generated and never displayed (the
    phone was off, the tray never opened) must show up again."""
    _init()
    now = time.time() if now is None else now
    with closing(_connect()) as c:
        if ids is None:
            cur = c.execute("UPDATE intents SET state='delivered', channel=?, "
                            "delivered=? WHERE state='queued'", (DIGEST, now))
        else:
            qs = ",".join("?" * len(ids))
            cur = c.execute(f"UPDATE intents SET state='delivered', channel=?, "
                            f"delivered=? WHERE state='queued' AND id IN ({qs})",
                            [DIGEST, now, *ids])
        return cur.rowcount


def expire(now: Optional[float] = None) -> int:
    """Drop queued items whose moment has passed. Called on every read, so a
    digest never shows something that stopped being true while it waited."""
    _init()
    now = time.time() if now is None else now
    with closing(_connect()) as c:
        cur = c.execute("UPDATE intents SET state='expired' "
                        "WHERE state='queued' AND expires IS NOT NULL AND expires < ?",
                        (now,))
        keep = float(_cfg("keep_delivered_days", 14) or 14) * 86400.0
        c.execute("DELETE FROM intents WHERE state<>'queued' AND created < ?",
                  (now - keep,))
        return cur.rowcount


def pending_count(now: Optional[float] = None) -> int:
    """How many notches the reactor's rim ring draws."""
    _init()
    expire(now)
    with closing(_connect()) as c:
        row = c.execute("SELECT COUNT(*) n FROM intents WHERE state='queued'").fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------
#   What the reactor shows
# --------------------------------------------------------------------------
# BANKED is a new face state and it is not a mood, it is a fact: there are
# things waiting and Jarvis is not going to say them out loud. Dimmed idle, no
# animation, the rim ring fully drawn, silent until tapped.
#
# The important half is the rule underneath it: a job finishing while banked
# does NOT move the face to "speaking" and does not make a sound. It adds a
# notch. Getting this wrong - letting a completion produce audio because the
# code path that finishes a job is not the code path that checks the budget -
# is exactly how an interruption budget becomes decorative.

def banked(now: Optional[float] = None) -> bool:
    b = budget(now)
    return bool(b["remaining"] == 0 and pending_count(now) > 0)


def face_state(activity: str = "idle", now: Optional[float] = None) -> str:
    """What the reactor should show, given what Jarvis is doing.

    Banked only replaces a resting face. If Jarvis is mid-sentence to somebody
    who asked it something, that is foreground and it keeps its own state -
    the budget governs what Jarvis STARTS, not what it is in the middle of.
    """
    if activity in ("idle",) and banked(now):
        return "banked"
    return activity


_last_published: dict = {}


def _publish_state(b: Optional[dict] = None, now: Optional[float] = None) -> None:
    """Tell the clients, but only when something actually changed. A budget
    event per finding would be its own kind of noise."""
    try:
        import jarvis_events
    except Exception:
        return
    b = b or budget(now)
    state = {"remaining": b["remaining"], "limit": b["limit"],
             "blocked_by": b["blocked_by"], "pending": pending_count(now),
             "banked": banked(now)}
    if state == _last_published:
        return
    _last_published.update(state)
    try:
        jarvis_events.BUS.publish("attention", state)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The tick
# --------------------------------------------------------------------------

def tick(now: Optional[float] = None) -> dict:
    """One pass, for whatever loop is already running.

    Pulls finished Long Fuse jobs in here rather than letting them announce
    themselves. That is the contract jarvis_jobs.collect() was written for:
    "tell me tomorrow" has no tomorrow if the answer arrives as a voice
    interruption at two in the afternoon.
    """
    now = time.time() if now is None else now
    out = {"expired": expire(now), "jobs": 0, "digest_due": False}
    try:
        import jarvis_jobs
        for job in jarvis_jobs.collect(limit=20):
            state = job.get("state", "done")
            deliver(source="long-fuse",
                    title=(job.get("label") or job.get("handler") or "job")
                          + (" finished" if state == "done" else f" {state}"),
                    body=str(job.get("result_summary") or job.get("error") or "")[:1000],
                    kind="job",
                    priority="normal" if state == "done" else "high",
                    ref=str(job.get("id", "")), now=now)
            out["jobs"] += 1
    except Exception:
        pass
    out["digest_due"] = digest_due(now)
    out["pending"] = pending_count(now)
    _publish_state(now=now)
    return out


def status(now: Optional[float] = None) -> dict:
    return {"available": True, "budget": budget(now),
            "pending": pending_count(now), "banked": banked(now),
            "digest_hour": _digest_hour(), "digest_due": digest_due(now)}


if __name__ == "__main__":                                # pragma: no cover
    import pprint
    pprint.pprint(status())
