"""jarvis_tellme.py - "Tell me when ...": Jarvis looks every few minutes for
an email from a named sender, or a Home Assistant device reaching a state,
and ONLY tells the owner when it happens - urgently, if they asked.

NEW MODULE, shipped whole. No patch: it is a KIND of job on the one
scheduler (jarvis_schedule.register_kind), set up through the scheduler's
existing POST /api/schedule/add and its ONE schedule_repeat card, listed in
Coming up in both apps like any repeating job, and set up by voice or text
through jarvis_quick.py ("tell me when an email from Alex arrives").

THE OWNER'S DECISION (CLAUDE.md, 2026-09-25, after the prompt pack):
"Urgent alerts without phone calls: 'tell me when ...' (a named sender's
email, a device change) set up with one card; a match only notifies -
urgent ones as a phone notification that keeps ringing until seen. No
telephony service: a call would send private text to an outside voice
company (rule 1)."

WHAT IT MAY DO, AND WHAT IT NEVER DOES
  * Setting one up is ONE approval card (schedule_repeat, tier "ask" - the
    scheduler refuses any other tier). The card says exactly what is
    watched, which server is asked, how often, until when, whether it tells
    once or every time, and whether it is urgent.
  * A match ONLY notifies. Never an action, never a reply, never a card,
    never a message to anyone. Nothing read here goes to the AI model.
  * The notification's words are built from the OWNER'S words, never from
    the email or the device: "An email from Alex arrived." - where "Alex" is
    what the owner asked to watch for, not the From line. No subject, no
    sender address, no text of the email is ever shown, kept or logged.
    The device's own state value is not shown either: "The washing machine
    finished." A locked phone, and both apps while App lock or "Hide memory
    lists and chat history" is on, show only LOCK_SCREEN.
  * The model has no tool for this: a watch is set up only by the owner's
    own typed or said words (the fast path) or from an app. A web page or
    an email cannot set one up.

HOW OFTEN IT LOOKS, AND WHY THOSE NUMBERS
  * Email: every 5 minutes at most often (EMAIL_MINUTES). Each look is one
    sign-in to the owner's mail server; most mail apps check every 5 to 15
    minutes, and some providers slow down or block accounts that sign in
    much more often. Five minutes late is fine for "tell me when Alex
    writes".
  * Home Assistant: every minute at most often (HOME_MINUTES). One small
    request to a server on the owner's own network; "the washing machine
    finished" is worth knowing within a minute, and a door opening sooner
    than that is a job for Home Assistant's own automations, not this.
  * These floors are for this kind only. Every other repeat keeps the
    scheduler's hourly floor (jarvis_schedule.MIN_EVERY_HOURS): the generic
    rule check still refuses "every N minutes"; only this kind's own check
    (register_kind(check=...)) accepts it.
  * It ends: DEFAULT_DAYS (30) unless the owner says otherwise ("for the
    next 2 hours", "today"), at most MAX_DAYS (90) - a forgotten watch must
    not sign in to the inbox for ever. By default it tells ONCE and then
    ends; "tell me every time ..." keeps going until the end date.

EMAIL - READ-ONLY, THE FROM LINE ONLY, NOTHING MARKED AS READ
One connection per look to the server jarvis_email.plan() names (the same
JARVIS_IMAP_* settings, read fresh each time), and only these commands:
    LOGIN, EXAMINE (read-only select), UID SEARCH UID <n>:*,
    UID FETCH <uids> (BODY.PEEK[HEADER.FIELDS (FROM)]), CLOSE, LOGOUT
PEEK, so the server sets no \\Seen flag. No STORE, COPY, MOVE or EXPUNGE,
no subject, no body. The first look only notes where the mailbox is
(UIDNEXT); every later look reads the From line of mail that arrived since
the look before, at most MAX_NEW messages. The sender's name is matched on
this PC and never sent to the server. A mailbox whose UIDVALIDITY changes
(rebuilt by the provider) starts again from there, telling nothing.

HOME ASSISTANT - ONE DEVICE, READ ONLY
jarvis_home.plan_states([entity]) - one GET of one named entity, the same
read the model's home_read tool makes, through the same gate action. It
tells when the state CHANGES to one the owner asked for (off, open, ...):
a washing machine already off when the watch starts is not "finished".
"unavailable" and "unknown" (Home Assistant restarting) are skipped.

THE GATE, EVERY LOOK
Each look asks jarvis_gate first, like the morning briefing's reads:
email_read or home_read, and it runs only when that says yes without a
person at tier "auto" (the shipped tier). A read set to "ask" cannot be
asked every few minutes, and one set to "notify" would send a "Jarvis read
your email" message every few minutes - so with either, setting one up is
refused with the reason, and a look that meets it later is skipped and says
so under Coming up. (The morning briefing, which reads once a day, accepts
"notify" too.) So the audit log gets one line per look - the price of every
read leaving this PC going through the same gate.

THE EVENT
The scheduler rings no doorbell for a look (the kind is `silent`). On a
match this publishes `schedule` {"id", "kind": "tellme", "state":
"matched", "urgent": bool} - ids, the kind and a flag, never words. The
apps then read the job by id (GET /api/schedule?id=), whose `alert` is the
sentence above. Urgent: the phone rings and vibrates until the owner looks
(an alarm-style notification); the PC shows an alarm toast whose sound
loops until it is dismissed.

WHAT IS KEPT
The watch (the owner's words: a sender's name or a device) is in the job's
rule in schedule.db, like a reminder's words. This module's own table,
`tellme` in the same file, keeps per job only: the mailbox position (a
number), the device's last state (a short word), when it last looked and
how that went (a fixed sentence), and when it last matched. No sender, no
subject, no email text, ever.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import jarvis_schedule as S

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Words - both apps say the same (jarvis-desktop/src/coming-up.js,
#   jarvis-client net/Schedule.kt; tests/coming-up.mjs checks)
# --------------------------------------------------------------------------

KIND = "tellme"
TITLE = "Tell me when"
NOUN = "\"tell me when\""

#: All a lock screen shows - and all either app shows while App lock or
#: "Hide memory lists and chat history" is on.
LOCK_SCREEN = "Jarvis: something you asked to be told about happened."

EMAIL_MINUTES = 5
HOME_MINUTES = 1
MAX_MINUTES = 60
DEFAULT_DAYS = 30
MAX_DAYS = 90
#: At most this many at once, and this many that read email (each is one
#: sign-in to the mail server every EMAIL_MINUTES).
MAX_WATCHES = 10
MAX_EMAIL_WATCHES = 5
#: New messages whose From line one look reads, at most.
MAX_NEW = 50
MAX_NAME = 60

EMAIL_ACTION = "email_read"
EMAIL_TOOL = "email_check"
HOME_ACTION = "home_read"
HOME_TOOL = "home_read"

#: The one FETCH item a look asks for (jarvis_email.SENDER_FETCH's shape).
SENDER_FETCH = "(BODY.PEEK[HEADER.FIELDS (FROM)])"

#: What the owner may say a device does, and the Home Assistant states that
#: count as it. The card lists the states in full.
STATE_WORDS = {
    "finishes": ("off", "idle", "finished", "complete", "completed", "done", "stopped",
                 "standby"),
    "opens": ("on", "open", "opening", "unlocked"),
    "closes": ("off", "closed", "closing", "locked"),
    "turns on": ("on",),
    "turns off": ("off",),
}
#: The same, said after it happened.
PAST = {"finishes": "finished", "opens": "opened", "closes": "closed",
        "turns on": "turned on", "turns off": "turned off"}
#: States that say "Home Assistant cannot see it right now", not a change.
_NOT_A_STATE = ("unavailable", "unknown", "")

_TOKEN = re.compile(r"[a-z0-9_]{1,30}")
_ENTITY = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")
_NAME_OK = re.compile(r"[\w .@'&+-]{1,60}", re.UNICODE)

# --------------------------------------------------------------------------
#   Settings, the gate and the bus - replaceable, so the tests open no socket
# --------------------------------------------------------------------------


def _tier_of(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tools_enabled() -> set:
    try:
        cfg = fw.load_framework() if fw is not None else {}
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _audit(event: str, detail: dict) -> None:
    # Ids, the source and outcomes. Never a name, a device or a state.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


@dataclass
class Deps:
    tier_of: Callable[[str], str] = _tier_of
    gate: Callable = _gate
    tools_enabled: Callable[[], set] = _tools_enabled
    publish: Callable[[str, dict], None] = _publish
    #: (plan, base_uid, uidvalidity) -> {"uidvalidity", "base", "new": [raw From]}
    email_look: Optional[Callable] = None
    #: jarvis_home.run's `fetch`
    home_fetch: Optional[Callable] = None
    sched: Optional[Callable[[], object]] = None


DEPS = Deps()


def _sched():
    if DEPS.sched is not None:
        return DEPS.sched()
    return S._SCHED if S._SCHED is not None else S.get()


def _env(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


# --------------------------------------------------------------------------
#   Is a source set up? (settings only - no socket)
# --------------------------------------------------------------------------

def readiness(source: str, deps: Optional[Deps] = None) -> str:
    """"" when a watch on `source` could look, else the sentence why not."""
    deps = deps or DEPS
    enabled = deps.tools_enabled()
    if source == "email":
        if not _env("JARVIS_IMAP_HOST") or EMAIL_TOOL not in enabled:
            return ("Email is not set up for Jarvis on this PC, so there is no inbox to "
                    "watch.")
        return _tier_words(deps.tier_of(EMAIL_ACTION), "email", "every 5 minutes", "email")
    if source == "home":
        url = _env("JARVIS_HOME_URL")
        if not url or HOME_TOOL not in enabled:
            return ("Home Assistant is not set up for Jarvis on this PC, so there is no "
                    "device to watch.")
        try:
            import jarvis_local_http
            bad = jarvis_local_http.plain_http_problem(url, "JARVIS_HOME_URL",
                                                       "the Home Assistant token")
        except Exception:
            bad = ""
        if bad:
            return bad
        return _tier_words(deps.tier_of(HOME_ACTION), "Home Assistant", "every minute",
                           "a device")
    return "Jarvis can watch for an email from someone, or a Home Assistant device."


def _tier_words(tier: str, what: str, often: str, watched: str) -> str:
    """Only tier "auto" lets a watch look: "ask" would mean a card every few
    minutes, and "notify" a "Jarvis read your email" message every few
    minutes - so both are refused, with the reason, rather than obeyed badly."""
    if tier == "auto":
        return ""
    if tier == "notify":
        return (f"Your settings tell you each time Jarvis reads {what}, and a \"tell me "
                f"when\" would then tell you {often} - so it cannot watch {watched}.")
    return (f"Your settings ask for a yes each time Jarvis reads {what}, and a \"tell me "
            f"when\" cannot ask you {often} - so it cannot watch {watched}.")


# --------------------------------------------------------------------------
#   The watch, and its rule
# --------------------------------------------------------------------------

def _clean_name(v) -> str:
    t = " ".join(str(v or "").split()).strip(" \"'.,;:!?")
    if not t or len(t) > MAX_NAME or not _NAME_OK.fullmatch(t):
        raise ValueError("say the sender's name or address in a few plain words, like Alex "
                         "or alex@example.com")
    return t


def check_watch(w) -> dict:
    """The watch, tidied, or ValueError with a sentence."""
    if not isinstance(w, dict):
        raise ValueError("a \"tell me when\" needs what to watch")
    source = str(w.get("source") or "").strip().lower()
    urgent = w.get("urgent") is True
    once = w.get("once") is not False
    if source == "email":
        sender = _clean_name(w.get("sender"))
        if sender.casefold() in ("anyone", "anybody", "someone", "somebody", "everyone"):
            raise ValueError("say who the email is from, like \"tell me when an email from "
                             "Alex arrives\"")
        return {"source": "email", "sender": sender, "urgent": urgent, "once": once}
    if source == "home":
        entity = str(w.get("entity") or "").strip().lower()
        if not _ENTITY.fullmatch(entity) or len(entity) > 120:
            raise ValueError("a device is its Home Assistant name, like "
                             "switch.washing_machine")
        say = str(w.get("say") or "").strip().lower()
        states = w.get("states")
        if say in STATE_WORDS:
            want = list(STATE_WORDS[say])
        else:
            if isinstance(states, str):
                states = [states]
            if not isinstance(states, list) or not states or len(states) > 10:
                raise ValueError("say what the device should do: finish, open, close, turn "
                                 "on or off - or which state, like off")
            want = []
            for x in states:
                x = str(x or "").strip().lower()
                if not _TOKEN.fullmatch(x) or x in _NOT_A_STATE:
                    raise ValueError("a state is one short word, like off or open")
                if x not in want:
                    want.append(x)
            say = "is " + want[0] if len(want) == 1 else "is " + " or ".join(want)
        name = " ".join(str(w.get("name") or "").split()).lower()
        if name and (len(name) > 40 or not re.fullmatch(r"[a-z0-9' -]+", name)):
            name = ""
        return {"source": "home", "entity": entity, "name": name, "say": say,
                "states": want, "urgent": urgent, "once": once}
    raise ValueError("Jarvis can watch for an email from someone, or a Home Assistant device")


def check_rule(rule, now: float) -> dict:
    """This kind's own rule check (register_kind(check=...)): every N minutes
    from a start, with an end and the watch. The generic check_rule refuses
    minutes, so no other kind can look this often."""
    if not isinstance(rule, dict):
        raise ValueError("a \"tell me when\" needs what to watch")
    watch = check_watch(rule.get("watch"))
    floor = EMAIL_MINUTES if watch["source"] == "email" else HOME_MINUTES
    n = rule.get("minutes", floor)
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("how often is a whole number of minutes")
    if n < floor:
        raise ValueError(f"the most often it can look is every {floor} minute"
                         + ("s" if floor != 1 else ""))
    if n > MAX_MINUTES:
        raise ValueError(f"the least often it can look is every {MAX_MINUTES} minutes")
    start = rule.get("start")
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        start = now
    ends = rule.get("ends")
    if ends is None:
        ends = days_later(now, DEFAULT_DAYS)
    if not isinstance(ends, (int, float)) or isinstance(ends, bool):
        raise ValueError("the end is a time")
    ends = float(ends)
    if ends <= now + n * 60:
        raise ValueError("that ends before it could look even once")
    if ends > days_later(now, MAX_DAYS) + 60:
        raise ValueError(f"a \"tell me when\" can run for up to {MAX_DAYS} days")
    return {"every": "minutes", "minutes": n, "start": float(start), "ends": ends,
            "watch": watch}


def days_later(now: float, days: int) -> float:
    """The same time on this PC's clock `days` days on - across a clock
    change, 12:00 stays 12:00."""
    lt = time.localtime(now)
    y, mo, d = S._add_days(lt.tm_year, lt.tm_mon, lt.tm_mday, int(days))
    return S.wall_to_epoch(y, mo, d, lt.tm_hour, lt.tm_min)


def what_words(watch: dict) -> str:
    """The job's words, in Coming up: "an email from Alex arrives", "the
    washing machine finishes", "sensor.washer is idle"."""
    if watch.get("source") == "email":
        return f"an email from {watch['sender']} arrives"
    subject = f"the {watch['name']}" if watch.get("name") else watch.get("entity", "")
    return f"{subject} {watch.get('say') or 'changes'}"


def alert_words(watch: dict, count: int = 1) -> str:
    """What the notification says - from the owner's words only."""
    if watch.get("source") == "email":
        if count > 1:
            return f"{count} emails from {watch['sender']} arrived."
        return f"An email from {watch['sender']} arrived."
    subject = f"The {watch['name']}" if watch.get("name") else watch.get("entity", "")
    say = watch.get("say") or ""
    if say in PAST:
        return f"{subject} {PAST[say]}."
    if say.startswith("is "):
        return f"{subject} is now {say[3:]}."
    return f"{subject} changed."


def _end_words(ends: float, now: float) -> str:
    return f"{S.long_date(ends)} ({_left_words(ends - now)})"


def _left_words(seconds: float) -> str:
    days = seconds / 86400.0
    if days >= 1.5:
        return f"{int(round(days))} days"
    hours = seconds / 3600.0
    if hours >= 1.5:
        return f"{int(round(hours))} hours"
    return S.length_words(max(60.0, round(seconds / 60.0) * 60.0))


# --------------------------------------------------------------------------
#   The card - ONE, listing exactly what is watched
# --------------------------------------------------------------------------

def card(rule: dict, text: str, now: float) -> str:
    w = rule["watch"]
    n = rule["minutes"]
    every = S.rule_words(rule)
    lines = [f"Set up \"{TITLE}\".", ""]
    if w["source"] == "email":
        try:
            import jarvis_email as MAIL
            p = MAIL.plan(1, unread_only=False)
            where = f"{p.host}:{p.port}, mailbox \"{p.mailbox}\"" if p.configured \
                else "(no mail server is set up)"
        except Exception:
            where = "your mail server"
        lines += [
            f"Watching for: an email from {w['sender']}.",
            f"How: {every}, Jarvis signs in to your mail server ({where}) and reads only "
            "the From line of mail that arrived since it last looked - with PEEK, so nothing "
            "is marked as read. No subject, no text and no attachment is read, and nothing "
            "goes to the AI model.",
            f"It matches when the sender's name or address has \"{w['sender']}\" in it, as "
            "whole words. Your words stay on this PC: they are not sent to the mail server.",
        ]
    else:
        try:
            import jarvis_home as HOME
            p = HOME.plan_states([w["entity"]])
            url = p.queries[0].url if p.queries else "(Home Assistant is not set up)"
        except Exception:
            url = "your Home Assistant"
        named = f"the {w['name']} ({w['entity']})" if w.get("name") else w["entity"]
        lines += [
            f"Watching for: {named} - when it {w['say']}.",
            f"How: {every}, Jarvis reads that one device's state from your Home Assistant: "
            f"GET {url}. Nothing in your home is changed.",
            "It matches when the state CHANGES to: " + ", ".join(w["states"]) + ".",
        ]
    lines += [
        "Until: " + _end_words(float(rule["ends"]), now)
        + (", or the first time it happens - whichever comes first." if w["once"]
           else ". It tells you every time it happens until then."),
        ("Urgent: yes. Your phone rings and vibrates until you look, and the PC plays an "
         "alarm sound until you dismiss it." if w["urgent"] else
         "Urgent: no. An ordinary notification on both apps."),
        "",
        f"When it happens, Jarvis only tells you: \"{alert_words(w)}\" It never replies, never "
        "acts, and never opens or reads out the email or anything else.",
        f"A locked phone shows only: \"{LOCK_SCREEN}\"",
        "",
        "It runs on this PC, by this PC's clock. Each look is a request to your own "
        + ("mail server" if w["source"] == "email" else "Home Assistant")
        + ", under the same settings as asking Jarvis to read it; the notification goes only "
          "to your own apps. Nothing else is sent anywhere.",
        "Stopping or deleting it is immediate, from either app.",
        "",
        "If you say no: nothing is set up, and nothing is watched.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   What this module keeps: where each watch has got to
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tellme (
    id          TEXT PRIMARY KEY,
    base_uid    INTEGER,
    uidvalidity INTEGER,
    last_state  TEXT,
    looked_at   REAL,
    look_said   TEXT NOT NULL DEFAULT '',
    matched_at  REAL,
    matched_n   INTEGER NOT NULL DEFAULT 0,
    alert_count INTEGER NOT NULL DEFAULT 0
);
"""
_LOCK = threading.RLock()


def _db(sched=None):
    import sqlite3
    path = (sched or _sched()).path
    c = sqlite3.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def _state(job_id: str, sched=None) -> dict:
    with _LOCK:
        c = _db(sched)
        try:
            r = c.execute("SELECT * FROM tellme WHERE id = ?", (job_id,)).fetchone()
            return dict(r) if r is not None else {}
        finally:
            c.close()


def _save(job_id: str, sched=None, **fields) -> None:
    with _LOCK:
        c = _db(sched)
        try:
            c.execute("INSERT OR IGNORE INTO tellme (id) VALUES (?)", (job_id,))
            for key, value in fields.items():
                if key not in ("base_uid", "uidvalidity", "last_state", "looked_at",
                               "look_said", "matched_at", "matched_n", "alert_count"):
                    raise KeyError(key)
                c.execute(f"UPDATE tellme SET {key} = ? WHERE id = ?", (value, job_id))
            c.commit()
        finally:
            c.close()


def _tidy(sched) -> None:
    """Forget where watches that are gone had got to (deleted, or over for
    more than a day - the scheduler removes those)."""
    with _LOCK:
        c = _db(sched)
        try:
            c.execute("DELETE FROM tellme WHERE id NOT IN (SELECT id FROM jobs)")
            c.commit()
        except Exception:
            pass
        finally:
            c.close()


def _watch_of(job_id: str, sched) -> tuple:
    """(row, rule, watch) of a tellme job, straight from schedule.db."""
    with sched._lock, sched._db() as c:
        row = sched._row(c, job_id)
    if row is None or row["kind"] != KIND or not row["rule"]:
        return None, None, None
    rule = json.loads(row["rule"])
    return row, rule, rule.get("watch") or {}


# --------------------------------------------------------------------------
#   Looking
# --------------------------------------------------------------------------

def _ok_to_read(action: str, what: str, text: str, deps: Deps) -> bool:
    """The same gate every read of the owner's accounts goes through - and
    only a yes without a person counts here (nobody is asked every minute)."""
    if deps.tier_of(action) != "auto":
        return False
    try:
        v = deps.gate(action, {"text": text, "for": "tell me when", "what": what}, text)
    except Exception:
        return False
    return getattr(v, "allowed", False) is True and getattr(v, "tier", "auto") == "auto"


def _words(s: str) -> list:
    return [w for w in re.split(r"[^\w]+", s.casefold()) if w]


def sender_matches(watched: str, raw_from) -> bool:
    """Does one From header name the sender the owner asked about? An
    address is compared whole; a name matches when every one of its words
    is a whole word of the sender's display name or address - "Alex" finds
    "Alex Smith <a.smith@x.com>" and "alex@x.com", never "alexandra@x.com".
    Read on this PC only; never shown."""
    from email.utils import getaddresses
    import email as _email
    try:
        import jarvis_email as MAIL
        decode = MAIL._decode
    except Exception:
        def decode(v):
            return str(v or "")
    if isinstance(raw_from, bytes):
        try:
            value = _email.message_from_bytes(raw_from).get("From") or ""
        except Exception:
            return False
    else:
        value = str(raw_from or "")
    try:
        pairs = getaddresses([str(value)[:2000]])
    except Exception:
        return False
    want = watched.strip().casefold()
    want_words = [w for w in _words(want) if w not in ("the", "my")]
    for name, addr in pairs:
        addr = decode(addr).strip().casefold()
        if "@" in want:
            if addr == want:
                return True
            continue
        have = set(_words(decode(name))) | set(_words(addr))
        if want_words and all(w in have for w in want_words):
            return True
    return False


def _resp(conn, code: str) -> Optional[int]:
    try:
        _typ, data = conn.response(code)
        v = data[-1] if data else None
        if isinstance(v, bytes):
            v = v.decode("ascii", "replace")
        return int(str(v).strip()) if v not in (None, "") else None
    except Exception:
        return None


def _default_email_look(p, base_uid: Optional[int], uidvalidity: Optional[int]) -> dict:
    """ONE connection, read-only. The first look (no base) only notes where
    the mailbox is; later looks read the From line of mail that arrived
    since. Credentials read fresh from the environment, never kept."""
    import imaplib
    user = os.environ.get("JARVIS_IMAP_USER", "")
    password = os.environ.get("JARVIS_IMAP_PASSWORD", "")
    conn = imaplib.IMAP4_SSL(p.host, p.port, timeout=20.0)
    try:
        conn.login(user, password)
        typ, _ = conn.select(p.mailbox, readonly=True)
        if typ != "OK":
            raise RuntimeError("EXAMINE failed")
        uv = _resp(conn, "UIDVALIDITY")
        nxt = _resp(conn, "UIDNEXT")
        if base_uid is None or uv != uidvalidity:
            if nxt is None:
                typ, data = conn.uid("SEARCH", "ALL")
                ids = [int(x) for x in (data[0] or b"").split() if x.isdigit()] \
                    if typ == "OK" and data else []
                nxt = (max(ids) + 1) if ids else 1
            return {"uidvalidity": uv, "base": int(nxt) - 1, "new": [], "fresh": True}
        typ, data = conn.uid("SEARCH", "UID", f"{int(base_uid) + 1}:*")
        if typ != "OK":
            raise RuntimeError("SEARCH failed")
        # "n:*" always answers the newest message, even an older one:
        # only UIDs above the base are new.
        uids = sorted(int(x) for x in (data[0] or b"").split()
                      if x.isdigit() and int(x) > int(base_uid))
        heads = []
        take = uids[-MAX_NEW:]
        if take:
            typ, got = conn.uid("FETCH", ",".join(str(u) for u in take), SENDER_FETCH)
            if typ == "OK":
                for part in got or []:
                    if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes):
                        heads.append(part[1])
        return {"uidvalidity": uv, "base": uids[-1] if uids else int(base_uid), "new": heads}
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def _look_email(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    """(how many matched, the sentence for Coming up)."""
    import jarvis_email as MAIL
    p = MAIL.plan(1, unread_only=False)
    if not p.configured:
        return 0, "Could not look: email's settings on this PC need a look."
    text = (f"Jarvis would like to look for new mail in the \"{p.mailbox}\" mailbox on "
            f"{p.host}:{p.port} for a \"tell me when\": one connection, the From line only of "
            "mail that arrived since the last look, with PEEK - no subject or text is read.")
    if not _ok_to_read(EMAIL_ACTION, "look for an email from a named sender", text, deps):
        return 0, ("Could not look: your settings ask for a yes each time Jarvis reads "
                   "email.")
    look = deps.email_look or _default_email_look
    try:
        out = look(p, st.get("base_uid"), st.get("uidvalidity"))
    except Exception as exc:
        return 0, f"Could not look: the mail server did not answer ({type(exc).__name__})."
    base = out.get("base")
    _save(job_id, sched, base_uid=int(base) if base is not None else None,
          uidvalidity=out.get("uidvalidity"))
    n = sum(1 for h in (out.get("new") or []) if sender_matches(watch["sender"], h))
    return n, ""


def _look_home(job_id: str, watch: dict, st: dict, deps: Deps, sched) -> tuple:
    import jarvis_home as HOME
    p = HOME.plan_states([watch["entity"]])
    if p.reason_empty:
        return 0, "Could not look: Home Assistant's settings on this PC need a look."
    text = HOME.describe(p)
    if not _ok_to_read(HOME_ACTION, "look at one device for a \"tell me when\"", text, deps):
        return 0, ("Could not look: your settings ask for a yes each time Jarvis reads "
                   "Home Assistant.")
    out = HOME.run(p, fetch=deps.home_fetch, approved=True)
    if not out.get("ok"):
        if _not_found(out):
            return 0, "Could not look: Home Assistant says there is no such device."
        return 0, "Could not look: Home Assistant did not answer."
    raw = str((out.get("states") or [{}])[0].get("state") or "").strip().lower()
    if not _TOKEN.fullmatch(raw) or raw in _NOT_A_STATE:
        # Home Assistant cannot see it right now (restarting): not a change,
        # and not the new "before".
        return 0, ""
    before = st.get("last_state")
    _save(job_id, sched, last_state=raw)
    if before is None:
        return 0, ""
    wanted = set(watch.get("states") or [])
    return (1 if (raw in wanted and before not in wanted) else 0), ""


def look(job_id: str, *, deps: Optional[Deps] = None, sched=None) -> dict:
    """One look for one watch (the scheduler calls this on its own thread
    when the job goes off). Only ever notifies: a match rings the doorbell
    with the kind and a flag, and - if it was to tell once - ends the job.
    Nothing else happens, whatever was read."""
    deps = deps or DEPS
    sched = sched or _sched()
    row, rule, watch = _watch_of(job_id, sched)
    if row is None or row["state"] not in ("active", "fired"):
        return {"ok": False, "why": "not on the list"}
    st = _state(job_id, sched)
    now = sched.now()
    _tidy(sched)
    try:
        watch = check_watch(watch)
    except ValueError:
        return {"ok": False, "why": "not a watch"}
    ready = readiness(watch["source"], deps)
    if ready:
        n, said = 0, "Could not look: " + ready[0].lower() + ready[1:]
    elif watch["source"] == "email":
        n, said = _look_email(job_id, watch, st, deps, sched)
    else:
        n, said = _look_home(job_id, watch, st, deps, sched)
    _save(job_id, sched, looked_at=now, look_said=said)
    if n <= 0:
        return {"ok": True, "matched": 0}
    _save(job_id, sched, matched_at=now, matched_n=int(st.get("matched_n") or 0) + 1,
          alert_count=int(n))
    _audit("tellme.matched", {"id": job_id, "source": watch["source"]})
    if watch["once"]:
        sched.end(job_id)
    deps.publish("schedule", {"id": job_id, "kind": KIND, "state": "matched",
                              "urgent": bool(watch["urgent"])})
    return {"ok": True, "matched": n}


def _on_fire(job_id: str) -> None:
    look(job_id)


# --------------------------------------------------------------------------
#   The view: a line under the row, and the alert by id
# --------------------------------------------------------------------------

def note(job_id: str) -> str:
    sched = _sched()
    row, rule, watch = _watch_of(job_id, sched)
    if row is None:
        return ""
    st = _state(job_id, sched)
    now = sched.now()
    parts = []
    if row["state"] in ("active", "paused", "waiting"):
        ends = float(rule.get("ends") or now)
        parts.append(f"Until {S.long_date(ends)}"
                     + (", or the first time it happens." if watch.get("once", True) else "."))
    if watch.get("urgent"):
        parts.append("Urgent: rings until you look.")
    if st.get("matched_at"):
        parts.append(f"Happened at {S.when_words(float(st['matched_at']), now)}.")
    elif st.get("look_said"):
        parts.append(st["look_said"])
    elif st.get("looked_at"):
        parts.append(f"Last looked at {S.clock(float(st['looked_at']))} - nothing yet.")
    return " ".join(parts)


def fields(job_id: str) -> dict:
    """`alert` (the notification's sentence) once it has happened."""
    sched = _sched()
    row, rule, watch = _watch_of(job_id, sched)
    if row is None:
        return {}
    st = _state(job_id, sched)
    out = {"watches": watch.get("source", "")}
    if st.get("matched_at"):
        try:
            out["alert"] = alert_words(check_watch(watch), int(st.get("alert_count") or 1))
        except ValueError:
            pass
        out["alert_at"] = float(st["matched_at"])
    return out


# --------------------------------------------------------------------------
#   Setting one up - from an app (the route) or the fast path
# --------------------------------------------------------------------------

def add(watch: dict, *, ends: Optional[float] = None, minutes: Optional[int] = None,
        source: str = "app", sched=None, deps: Optional[Deps] = None) -> dict:
    """ONE card; nothing looks before it is approved. ValueError or
    OverflowError with a sentence."""
    deps = deps or DEPS
    sched = sched or _sched()
    w = check_watch(watch)
    why = readiness(w["source"], deps)
    if why:
        raise OverflowError(why[0].lower() + why[1:].rstrip("."))
    listed = [j for j in sched.listed() if j.get("kind") == KIND]
    if len(listed) >= MAX_WATCHES:
        raise OverflowError(f"there are already {MAX_WATCHES} \"tell me when\"s - delete one "
                            "first")
    if w["source"] == "email":
        mail = 0
        for j in listed:
            _r, _rule, jw = _watch_of(j["id"], sched)
            if jw and jw.get("source") == "email":
                mail += 1
        if mail >= MAX_EMAIL_WATCHES:
            raise OverflowError(f"there are already {MAX_EMAIL_WATCHES} watching email - each "
                                "signs in to your mail server every few minutes; delete one "
                                "first")
    rule = {"every": "minutes", "watch": w}
    if minutes is not None:
        rule["minutes"] = minutes
    if ends is not None:
        rule["ends"] = ends
    return sched.add_repeat(KIND, rule, what_words(w), source=source)


def add_route(body: dict) -> tuple:
    """POST /api/schedule/add {"kind": "tellme", "source": "email", "sender"}
    or {"kind": "tellme", "source": "home", "entity", "say" | "states",
    "name"?}, with "urgent"?, "once"?, "days"? (up to 90), "minutes"?.
    202 and ONE card, like any repeat."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Need a JSON object."}
    watch = {k: body.get(k) for k in ("source", "sender", "entity", "say", "states", "name",
                                      "urgent", "once")}
    ends = None
    days = body.get("days")
    if days is not None:
        if not isinstance(days, (int, float)) or isinstance(days, bool) or days <= 0:
            return 400, {"ok": False, "error": "Days is a number, like 7."}
        now = _sched().now()
        ends = (days_later(now, int(days)) if float(days).is_integer()
                else now + float(days) * 86400.0)
    minutes = body.get("minutes")
    if minutes is not None and (not isinstance(minutes, int) or isinstance(minutes, bool)):
        return 400, {"ok": False, "error": "How often is a whole number of minutes."}
    try:
        job = add(watch, ends=ends, minutes=minutes, source="app")
    except OverflowError as exc:
        return 409, {"ok": False, "error": S._sentence(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {"ok": False, "error": S._sentence(exc)}
    return 202, {"ok": True, "waiting": True, "job": job,
                 "said": "It looks again and again, so it waits for your yes on the card."}


# --------------------------------------------------------------------------
#   Finding a device by the name the owner said ("the washing machine")
# --------------------------------------------------------------------------

#: The Home Assistant kinds of device tried for a name, by what it should do.
_TRY = {
    "opens": ("binary_sensor", "cover", "lock"),
    "closes": ("binary_sensor", "cover", "lock"),
}
_TRY_ANY = ("switch", "binary_sensor", "sensor")


def slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def candidates(name: str, say: str) -> list:
    s = slug(name)
    if not s:
        return []
    return [f"{d}.{s}" for d in _TRY.get(say, _TRY_ANY)]


def find_device(name: str, say: str, *, deps: Optional[Deps] = None) -> dict:
    """Which of a few likely Home Assistant names exists for `name` - each
    read is ONE GET of ONE named entity through the gate (home_read), like
    the model's own reads; the whole house is never listed. {"found": [ids],
    "tried": [ids], "why": sentence or ""}."""
    deps = deps or DEPS
    tried = candidates(name, say)
    if not tried:
        return {"found": [], "tried": [], "why": ""}
    why = readiness("home", deps)
    if why:
        return {"found": [], "tried": tried, "why": why}
    import jarvis_home as HOME
    found = []
    for eid in tried:
        p = HOME.plan_states([eid])
        if p.reason_empty:
            continue
        text = HOME.describe(p)
        if not _ok_to_read(HOME_ACTION, "find a device for a \"tell me when\"", text, deps):
            return {"found": [], "tried": tried,
                    "why": readiness("home", deps) or "The approval gate did not let Jarvis "
                                                      "read Home Assistant."}
        out = HOME.run(p, fetch=deps.home_fetch, approved=True)
        if out.get("ok"):
            found.append(eid)
        elif not _not_found(out):
            return {"found": [], "tried": tried,
                    "why": "Home Assistant did not answer, so Jarvis could not look for it."}
    return {"found": found, "tried": tried, "why": ""}


def _not_found(out: dict) -> bool:
    why = str(out.get("reason") or "")
    return "404" in why or "Not Found" in why


S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=True, owner_listed=True,
                repeatable=True, silent=True, first_now=True, leaves=True,
                what="set up a \"tell me when\" (it looks every few minutes and only "
                     "notifies)",
                check=check_rule, card=card, add=add_route, note=note, fields=fields,
                on_fire=lambda job_id: _on_fire(job_id))
