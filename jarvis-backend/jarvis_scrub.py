"""jarvis_scrub.py - takes passwords, keys and the pairing token out of what
the backend writes to its log.

WHAT THIS IS FOR, IN ONE SENTENCE
The desktop app writes everything the backend prints into `backend.log`
(jarvis-desktop/src-tauri/src/logfile.rs), a plain-text file the owner will
paste into a bug report - so no working key, token or password may reach it,
and ideally not the owner's e-mail address or Windows user name either.

HOW IT IS SWITCHED ON
`log-scrub.patch` calls `install(HUD_TOKEN)` in jarvis_hud.py, right after the
pairing token is resolved and before the startup banner. From then on:
  - everything printed to stdout or stderr goes through `scrub_text` a line at
    a time, which covers every `print`, every uncaught traceback (Python
    writes those to whatever sys.stderr is at the time), and the web server's
    request lines;
  - every `logging` record is scrubbed when it is made, whichever logger made
    it and wherever its handler writes - a file included;
  - a logging handler set up BEFORE install() that writes to the old stdout
    or stderr is re-pointed at the scrubbed one. (Found by the extraction
    research: a logger made before the scrubber started still wrote an
    OpenAI key in clear text. test_scrub.py makes one early to prove it.)

WHAT THIS IS NOT FOR - READ BEFORE ADDING A CALL SITE
docs/ARCHITECTURE.md section 3: "Redaction is per-destination." This module
has ONE destination: text written down on this machine.
  * NOT the ntfy push: that text is generated from our own tables
    (`jarvis_gate.notice_for`) and never reads the payload.
  * NOT the event bus: that is an allowlist (event-allowlist.patch).
  * NOT the cloud lane: a message holding a secret is sent LOCAL by
    `jarvis_router` gate 3, never "cleaned and sent anyway". A scrubbed string
    is NOT safe to send anywhere: a pattern list never recognises everything.
  * NOT the audit log. `jarvis_gate._redact` owns that, and putting a second
    redactor there is the owner's call (the extraction research, Module 1).

NO OFF SWITCH, ON PURPOSE
`jarvis_gate._redact` obeys `[logging].redact_private_content_in_logs`, and
test_gate_push.py exists because a switch named for one destination once
turned off protection on another. This module reads no setting at all.

TWO LAYERS, BECAUSE NEITHER IS ENOUGH ALONE
1. KNOWN VALUES. The exact secrets this process holds: the pairing token
   (handed to install()), every environment variable whose NAME says it is a
   secret - the same rule jarvis_child_env uses to keep secrets out of child
   programs (HUD_TOKEN, JARVIS_GITHUB_TOKEN, JARVIS_IMAP_PASSWORD,
   OPENAI_API_KEY ...) - and anything handed to register_secret(). Replaced
   wherever they appear, whatever they look like. This is the only layer that
   can catch the pairing token: it is 43 random characters with no prefix.
2. SHAPES. jarvis_router's own table (`_SECRET_PATTERNS`, the one gate 3 uses
   to keep a pasted key off the cloud lane - one table, so the two never
   drift), plus shapes that only matter in a log: a whole private-key block,
   the X-Jarvis-Token and Authorization headers, cookies, a password inside a
   URL (`https://user:pw@host`), a secret in a URL's query (`?token=...`), and
   `password = ...` style lines.
And a third, for the log only: E-MAIL ADDRESSES, the user-name part of a home
folder (C:\\Users\\<name>), and phone numbers written with a leading "+".

WHAT IT DELIBERATELY LEAVES ALONE
Bare numbers (every timestamp would look like a phone number), IP addresses
(the first thing a connection bug report needs), file names after the user
folder, and anything that merely "looks random" (hashes and ids would all go).

IT NEVER SAYS WHAT IT REMOVED
A replacement is `[redacted: <kind>]` - "a GitHub token", "HUD_TOKEN value" -
never the value, never a piece of it. Nothing in this module prints or logs.
It never raises: on any internal error the text is WITHHELD, with a marker,
rather than written out unscrubbed.

NOT COVERED, AND CANNOT BE FROM INSIDE PYTHON
Anything written to the file descriptor directly: a child program that
inherited it (the second Ollama, colibri, a shell command), faulthandler, or
`sys.stdout.buffer.write`.

References (read, not copied): OpenJarvis (Apache-2.0)
security/credential_stripper.py and security/scanner.py. The designs and
their tests: docs/EXTRACTION-RESEARCH-2026-09-23.md, Module 1.

    python3 test_scrub.py
"""
from __future__ import annotations

import base64
import os
import re
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

__all__ = ["scrub_text", "find_secret", "register_secret", "install", "MARK"]

#: Wave D-2: the tiers `classify_outbound_sensitivity` answers with. 0 is
#: "nothing sensitive in this text"; Tier 1 is never allowed out; Tier 2 is
#: health/personal-finance and needs an untrusted-free turn plus the owner's
#: own explicit instruction.
OUTBOUND_TIERS = {0: "none", 1: "tier1_always_refused", 2: "tier2_explicit_owner_only"}

#: Every replacement starts with this. No pattern below can match a marker,
#: so scrubbing twice gives the same text as scrubbing once.
MARK = "[redacted"


# --------------------------------------------------------------------------
#   Wave D-2: what may be staged on an outbound card, and what never may
#   (Ruling: two tiers; the classifier is a pure function of the text plus the
#   owner's own words, so every decision is testable without a network)
# --------------------------------------------------------------------------

#: A Luhn-valid card number, 13-19 digits with optional single spaces or
#: hyphens between them. The candidate is only a card if Luhn passes, so an
#: ordinary long number is not refused as one.
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
#: A US Social Security number, dashed (the shape the government issues and
#: the one a person types on a form).
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
#: A `vault://` handle - a pointer the owner stores instead of a value.
_VAULT_RE = re.compile(r"vault://[^\s<>\"']+", re.IGNORECASE)
#: A pairing token, exactly jarvis_devices.KEY_PATTERN's shape
#: (`jdk1.d<8 hex>.<43>`), so the two modules cannot disagree about it.
_PAIRING_RE = re.compile(r"\bjdk1\.d[0-9a-f]{8}\.[A-Za-z0-9_-]{43}\b")
#: API-key shapes a `gitleaks` scan knows by prefix. Deliberately a list of
#: PREFIXES rather than one clever regex: a new provider is one line.
_API_KEY_SHAPES = (
    re.compile(r"\bsk-(?:proj|ant|svcacct|admin)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
)
#: Health and personal-finance WORDS: Tier 2's detection. A money figure on
#: its own is a price; a figure beside one of these words is the owner's
#: position, which is what the second tier is about.
_HEALTH_RE = re.compile(
    r"\b(?:diagnos(?:is|ed|es)?|medications?|prescriptions?|dosage|blood pressure|"
    r"cholesterol|diabet(?:es|ic)|symptoms?|therapy|therapist|depress(?:ion|ed)?|"
    r"anxiety|hospital|medical record|health insurance|cancer|pregnan(?:cy|t))\b",
    re.IGNORECASE)
_FINANCE_RE = re.compile(
    r"\b(?:tax(?:es)?(?: balance)?|salary|income|net worth|mortgage|loan|debt|401\(?k\)?|"
    r"\bira\b|investment(?:s)?|portfolio|bank balance|account balance|account number|"
    r"routing number|sort code|credit score|budget|pension)\b",
    re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?:[$£€]\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:dollars|usd|eur|gbp)\b)", re.IGNORECASE)
#: The owner's OWN explicit authorisation, in his words, for this category.
#: "Email my accountant my Q3 tax balance" matches; "Reply to Sam about
#: Tuesday" does not, and neither does a bare "send it".
_EXPLICIT_HEALTH_SHARE_RE = re.compile(
    r"\b(?:send|email|e-mail|share|forward|tell|give|include|show|attach)\b.{0,80}"
    r"\b(?:health|medical|doctor|medication|prescription|symptoms?|diagnos(?:is|ed)?)\b",
    re.IGNORECASE | re.DOTALL)
_EXPLICIT_FINANCE_SHARE_RE = re.compile(
    r"\b(?:send|email|e-mail|share|forward|tell|give|include|show|attach)\b.{0,80}"
    r"\b(?:tax(?:es)?|salary|income|financ(?:e|es|ial)|balance|account|budget|"
    r"net worth|mortgage|loan|pension|investment)\b",
    re.IGNORECASE | re.DOTALL)


def _luhn_ok(digits: str) -> bool:
    """The card-number checksum. A 16-digit number that is not a card must not
    be refused as one, so the shape alone is never enough."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _tier1_categories(text: str) -> list:
    """Which Tier-1 shapes are in this text - never the values themselves, so
    a reason can be shown on a card without echoing the secret."""
    found = []
    for m in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found.append("card_number")
            break
    if _SSN_RE.search(text):
        found.append("government_id")
    if _VAULT_RE.search(text):
        found.append("vault_handle")
    if _PAIRING_RE.search(text):
        found.append("pairing_token")
    if any(p.search(text) for p in _API_KEY_SHAPES):
        found.append("api_key")
    return found


def _tier2_categories(text: str) -> list:
    found = []
    if _HEALTH_RE.search(text):
        found.append("health")
    if _FINANCE_RE.search(text) and _MONEY_RE.search(text):
        found.append("personal_finance")
    return found


def _redact_tier1(text: str) -> str:
    """The Tier-1 shapes replaced with the module's own marker style. The
    marker is stable, so scrubbing twice gives the same text."""
    out = scrub_text(text)
    out = _SSN_RE.sub(f"{MARK} government id]", out)
    out = _VAULT_RE.sub(f"{MARK} vault handle]", out)
    out = _PAIRING_RE.sub(f"{MARK} pairing token]", out)

    def card(m):
        digits = re.sub(r"[ -]", "", m.group(0))
        return f"{MARK} card number]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) \
            else m.group(0)
    out = _CARD_CANDIDATE.sub(card, out)
    for pattern in _API_KEY_SHAPES:
        out = pattern.sub(f"{MARK} api key]", out)
    return out


def classify_outbound_sensitivity(outbound_text, *, user_prompt: str = "",
                                  tainted: bool = False) -> dict:
    """What a draft may say before it is staged on an outbound card.

    Returns {allowed, tier, reasons, redacted_text, categories, tainted}.
    `tier` is 0 (nothing sensitive), 1 (never out, even if asked) or 2
    (health / personal finance: only when the turn has NOT read untrusted
    outside text AND the owner's own prompt explicitly authorises sharing
    that category). `redacted_text` masks the Tier-1 shapes, so a refusal can
    show the card a scrubbed version and the value never travels.

    Pure: no clock, no network, no file, no model. Two calls with the same
    arguments answer the same thing.
    """
    text = str(outbound_text or "")
    prompt = str(user_prompt or "")
    redacted = _redact_tier1(text)
    tier1 = _tier1_categories(text)
    if tier1:
        return {"allowed": False, "tier": 1,
                "reasons": [f"tier1_{c}" for c in tier1],
                "categories": tier1, "redacted_text": redacted,
                "tainted": bool(tainted)}
    tier2 = _tier2_categories(text)
    if tier2:
        explicit = {"health": bool(_EXPLICIT_HEALTH_SHARE_RE.search(prompt)),
                    "personal_finance": bool(_EXPLICIT_FINANCE_SHARE_RE.search(prompt))}
        blocked = [c for c in tier2 if tainted or not explicit.get(c)]
        if blocked:
            reasons = ["tier2_unrequested_or_tainted"]
            if tainted:
                reasons.append("turn_read_outside_text")
            return {"allowed": False, "tier": 2, "reasons": reasons,
                    "categories": blocked, "redacted_text": redacted,
                    "tainted": bool(tainted),
                    "why": ("This draft mentions health or money figures, and either the "
                            "turn has read outside text or you did not ask for that "
                            "category to be shared. Nothing is staged.")}
        return {"allowed": True, "tier": 2, "reasons": [], "categories": [],
                "redacted_text": text, "tainted": bool(tainted)}
    return {"allowed": True, "tier": 0, "reasons": [], "categories": [],
            "redacted_text": text, "tainted": bool(tainted)}


def _mark(kind: str) -> str:
    return f"{MARK}: {kind}]"


# ---------------------------------------------------------------------------
#   Layer 1: the values this process holds
# ---------------------------------------------------------------------------

#: A value shorter than this is not replaced by exact match: replacing "1" or
#: "yes" everywhere would wreck the log and protect nothing.
_MIN_KNOWN = 8

#: The floor for a secret whose NAME says it is one (`HUD_TOKEN`,
#: `JARVIS_IMAP_PASSWORD`). Four, not eight: the eight-character rule exists
#: to stop a short *unlabelled* value from being replaced everywhere, and a
#: name-marked secret is not that - the name is the evidence. Before this,
#: a genuinely short token or password (measured: `HUD_TOKEN=abc1234`) was
#: passed through to the log in clear by every one of the checks below, which
#: is exactly what rule 3 forbids. Four rather than one still keeps a
#: one-character value (or an empty one) out of the replacement table.
_MIN_NAMED = 4

_REGISTERED: set = set()
_REG_LOCK = threading.Lock()
_TOKEN_FILE_CACHE: Tuple[Optional[Tuple[str, float]], str] = (None, "")

#: Used only when jarvis_child_env.py cannot be imported; the same words.
_SECRET_WORDS = ("TOKEN", "KEY", "PASSWORD", "PASSWD", "SECRET", "CREDENTIAL", "AUTH")


def _own_rule(name: str) -> bool:
    up = str(name).upper()
    return any(w in up for w in _SECRET_WORDS)


_NAME_RULE = None


def _secret_name(name: str) -> bool:
    """Whether an environment variable's NAME says it holds a secret - the
    same rule that keeps secrets out of child programs (jarvis_child_env)."""
    global _NAME_RULE
    if _NAME_RULE is None:
        try:
            import jarvis_child_env
            _NAME_RULE = jarvis_child_env._looks_secret
        except Exception:
            _NAME_RULE = _own_rule
    try:
        return bool(_NAME_RULE(name))
    except Exception:
        return _own_rule(name)


def register_secret(value: Any) -> None:
    """Tell the scrubber about a secret this process holds.

    Kept in memory only. Never written, never logged, never returned by any
    function here. A value under eight characters is ignored (see _MIN_KNOWN).
    """
    try:
        v = str(value or "").strip()
    except Exception:
        return
    if len(v) >= _MIN_KNOWN:
        with _REG_LOCK:
            _REGISTERED.add(v)


def _token_file_value() -> str:
    """The pairing token in the OLD plain-text file token-file.patch wrote
    (`<config dir>/token`). token-store.patch moves it into Credential Manager
    and deletes the file, but a file the move could not delete is still the
    token the phone was paired with. Never raises."""
    global _TOKEN_FILE_CACHE
    try:
        import jarvis_framework as fw
        path = Path(fw.CONFIG_DIR) / "token"
        st = path.stat()
        key = (str(path), st.st_mtime)
        if _TOKEN_FILE_CACHE[0] == key:
            return _TOKEN_FILE_CACHE[1]
        value = path.read_text(encoding="utf-8").strip()
        _TOKEN_FILE_CACHE = (key, value)
        return value
    except Exception:
        return ""


def _known_values() -> List[Tuple[str, str]]:
    """(value, label) for every secret this process can see, in every form it
    is sent in, longest first."""
    raw: dict = {}
    try:
        env = dict(os.environ)
    except Exception:
        env = {}
    for name, value in env.items():
        if _secret_name(name):
            v = (value or "").strip()
            if len(v) >= _MIN_NAMED:
                raw.setdefault(v, name)
    tok = _token_file_value()
    if len(tok) >= _MIN_NAMED:
        raw.setdefault(tok, "HUD_TOKEN")
    with _REG_LOCK:
        for v in _REGISTERED:
            raw.setdefault(v, "a registered secret")

    out = {}
    for v, name in raw.items():
        label = f"{name} value"
        out.setdefault(v, label)
        # jarvis_notes.py puts the Joplin token in a URL through
        # urllib.parse.quote(token, safe=''), and urllib quotes the whole URL
        # in some of its errors.
        q = urllib.parse.quote(v, safe="")
        if q != v:
            out.setdefault(q, label)
    # jarvis_calendar.py sends base64("user:password") as Basic auth. The
    # header shape catches "Basic <blob>"; this catches the bare blob.
    user = (env.get("JARVIS_CALDAV_USER") or "").strip()
    pw = (env.get("JARVIS_CALDAV_PASSWORD") or "").strip()
    if user and len(pw) >= _MIN_NAMED:
        try:
            b = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("ascii")
            out.setdefault(b, "JARVIS_CALDAV_PASSWORD value")
        except Exception:
            pass
    return sorted(out.items(), key=lambda kv: -len(kv[0]))


def _replace_known(text: str) -> Tuple[str, Optional[str]]:
    first = None
    for value, label in _known_values():
        if value in text:
            text = text.replace(value, _mark(label))
            first = first or label
    return text, first


# ---------------------------------------------------------------------------
#   Private-key blocks
# ---------------------------------------------------------------------------
#
# The whole block, not only its header line. And never more than a key's
# worth: a BEGIN line with no END after it used to silence every later line
# of the log (the extraction research printed one and watched the log go
# quiet). Now, without an END, only the lines that look like key material
# are hidden - base64, a "Proc-Type:" style header, or blank - and at most
# _KEY_MAX_LINES of them.

_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_PEM_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----")
#: A 16384-bit RSA key is about 210 lines of 64 characters.
_KEY_MAX_LINES = 240
_KEY_MAX_CHARS = _KEY_MAX_LINES * 80
#: A line break, real or written out inside a JSON string.
_LINE_BREAK = re.compile(r"(\r?\n|\\r\\n|\\n)")
_B64 = re.compile(r"[A-Za-z0-9+/=]+")
_KEY_HEADER = re.compile(r"[A-Za-z][A-Za-z-]*: [^\r\n]*")


def _key_line(seg: str) -> bool:
    """Whether one line after a BEGIN line looks like part of the key. A long
    base64 line, or a short one with a digit or a base64 symbol in it (so a
    plain word like "Traceback" on the next line is NOT taken for a key and
    hidden), a header line, or a blank one."""
    s = seg.strip()
    if not s:
        return True
    if _KEY_HEADER.fullmatch(s):
        return True
    if _B64.fullmatch(s):
        return len(s) >= 40 or bool(re.search(r"[0-9+/=]", s))
    return False


def _cut_keys(text: str) -> str:
    out = []
    pos = 0
    while True:
        m = _PEM_BEGIN.search(text, pos)
        if not m:
            out.append(text[pos:])
            return "".join(out)
        out.append(text[pos:m.start()])
        out.append(_mark("private key"))
        e = _PEM_END.search(text, m.end(), m.end() + _KEY_MAX_CHARS)
        if e:
            pos = e.end()
            continue
        parts = _LINE_BREAK.split(text[m.end():])
        # parts = [rest of the BEGIN line, break, line, break, line, ...]
        used = 0
        if _key_line(parts[0]):
            used = len(parts[0])
            i, lines = 1, 0
            while i + 1 < len(parts) and lines < _KEY_MAX_LINES and _key_line(parts[i + 1]):
                if i + 2 >= len(parts) and not parts[i + 1].strip():
                    break           # keep the text's own final line break
                used += len(parts[i]) + len(parts[i + 1])
                i += 2
                lines += 1
        pos = m.end() + used


# ---------------------------------------------------------------------------
#   Layer 2: shapes
# ---------------------------------------------------------------------------

def _keep1(kind: str) -> str:
    return r"\1" + _mark(kind).replace("\\", "\\\\")


#: The value part of a labelled secret. `(?!\[redacted)` keeps a second pass
#: from redacting a marker.
_VAL = r"(?!\[redacted)[^\s\"'`,;&}\]\)<>]{4,}"

#: Shapes that keep the NAME of the thing ("Authorization: Bearer ",
#: "?token=") so the log still says what was there. Run before the router's
#: table.
_CONTEXT_SHAPES: List[Tuple[str, "re.Pattern[str]", str]] = [
    # A device's own key (jarvis_devices.py, docs/PAIRING-DESIGN.md 5.1):
    # jdk1.<device id>.<43 characters>. Found even out of context - that is
    # what its prefix is for. Replaced whole, first, so the header and
    # labelled shapes after it see only the marker.
    ("Jarvis device key",
     re.compile(r"(?<![A-Za-z0-9_-])jdk1\.d[0-9a-f]{8}\.[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
     _mark("Jarvis device key")),
    # This project's own header. The Android crash log already strips it
    # (CrashLog.kt).
    ("Jarvis pairing token",
     re.compile(r"(?i)(x-jarvis-token[\"']?\s*[:=]\s*[\"']?)" + _VAL),
     _keep1("Jarvis pairing token")),
    # Authorization: Bearer/Basic/Token <value>. Sixteen characters or more,
    # so "Basic authentication failed" survives.
    ("authorization header",
     re.compile(r"(?i)\b((?:bearer|basic|token)\s+)(?!\[redacted)"
                r"[A-Za-z0-9._~+/-]{16,}=*"),
     _keep1("credential")),
    ("cookie",
     re.compile(r"(?im)\b((?:set-)?cookie\s*:\s*)(?!\[redacted)[^\r\n]+"),
     _keep1("cookie")),
    # scheme://user:password@host - the scheme, user and host stay.
    ("password in a URL",
     re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)(?!\[redacted)[^/\s@]+(?=@)"),
     _keep1("password")),
    # A private calendar link - Google Calendar's "Secret address in iCal
    # format", https://calendar.google.com/calendar/ical/<calendar>/private-
    # <hex>/basic.ics - or any address with a /private-<hex> part: whoever
    # has it can read the calendar (jarvis_calendar.py). The scheme and host
    # stay; the path, which holds both the secret and the calendar's name
    # (often the owner's e-mail address, URL-quoted), goes.
    ("private calendar link",
     re.compile(r"(?i)\b((?:https?|webcal)://[^/\s\"'<>]+)(?!/\[redacted)"
                r"/[^\s\"'<>]*?(?:/calendar/ical/|/private-[0-9a-f]{8,})[^\s\"'<>]*"),
     r"\1/" + _mark("private calendar link")),
    ("private calendar link",
     re.compile(r"(?i)(/calendar/ical/)(?!\[redacted)[^\s\"'<>]+"),
     _keep1("private calendar link")),
    ("private calendar link",
     re.compile(r"(?i)(?<![\w-])private-[0-9a-f]{16,}(?![0-9a-f])"),
     _mark("private calendar link")),
    # ?token=... &api_key=... - jarvis_notes.py builds exactly this for Joplin.
    ("secret in a URL",
     re.compile(r"(?i)([?&](?:access_|refresh_|id_|auth_)?(?:token|api[_-]?key|key"
                r"|password|passwd|pwd|secret|client_secret|sig|signature)=)"
                r"(?!\[redacted)[^&#\s\"'<>]+"),
     _keep1("secret")),
]

#: After the router's table: `password = hunter22`, `"api_key": "abc..."`,
#: PASSWORD="x". Looser than the router's own labelled rule (which wants 16
#: characters), because a log line is not a question someone is asking.
#: `token` must be the whole word, so max_tokens=4096 and token_count=12 stay.
_LABELLED = ("labelled secret",
             re.compile(r"(?i)\b((?:[a-z0-9]+[_-])*(?:password|passwd|pwd|passphrase"
                        r"|secret|client_secret|api[_-]?key|apikey|access[_-]?key"
                        r"|private[_-]?key|token|auth[_-]?token|access[_-]?token"
                        r"|refresh[_-]?token)[\"']?\s*[:=]\s*[\"']?)" + _VAL),
             _keep1("secret"))

_ROUTER_TABLE: Optional[list] = None


def _router_shapes() -> list:
    """(kind, pattern) from jarvis_router._SECRET_PATTERNS - the table gate 3
    uses to keep a pasted key off the cloud lane. Read once. Empty when the
    router cannot be imported; the shapes above and the known values still
    apply then."""
    global _ROUTER_TABLE
    if _ROUTER_TABLE is None:
        try:
            import jarvis_router
            _ROUTER_TABLE = [(str(k), p) for k, p in jarvis_router._SECRET_PATTERNS]
        except Exception:
            _ROUTER_TABLE = []
    return _ROUTER_TABLE


def _sub_router(pattern, kind: str, text: str) -> str:
    """Replace a router match. A pattern with a group (the router's labelled
    rule) loses only the group - the value - so the label stays."""
    def repl(m):
        if pattern.groups and m.group(1) is not None:
            a, b = m.span(1)
            s = m.start()
            whole = m.group(0)
            return whole[:a - s] + _mark(kind) + whole[b - s:]
        return _mark(kind)
    return pattern.sub(repl, text)


def _apply_shapes(text: str) -> Tuple[str, Optional[str]]:
    first = None
    for kind, pattern, repl in _CONTEXT_SHAPES:
        new = pattern.sub(repl, text)
        if new != text:
            first, text = first or kind, new
    for kind, pattern in _router_shapes():
        new = _sub_router(pattern, kind, text)
        if new != text:
            first, text = first or kind, new
    kind, pattern, repl = _LABELLED
    new = pattern.sub(repl, text)
    if new != text:
        first, text = first or kind, new
    return text, first


_IDENTIFIER_SHAPES: List[Tuple[str, "re.Pattern[str]", str]] = [
    ("e-mail address",
     re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                r"\.[A-Za-z]{2,}\b"),
     _mark("e-mail")),
    # The user-name part of a home folder: C:\Users\pcadmin\... ->
    # C:\Users\[redacted: user]\... Public, Default and All Users are not people.
    ("home folder user name",
     re.compile(r"(?i)(\b[a-z]:[\\/]+users[\\/]+|(?<![\w.])/home/|(?<![\w.])/Users/)"
                r"(?!\[redacted)(?!(?:public|default|all users)(?:[\\/\s]|$))"
                # A folder name can hold spaces ("Mario Rossi"): up to 40
                # characters when a separator follows, else up to a space.
                r"(?:[^\\/\"'\r\n:,;<>|]{1,40}(?=[\\/])|[^\\/\s\"']+)"),
     _keep1("user")),
    ("phone number",
     re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?(?:\(\d{1,4}\)[\s.-]?)?\d{2,4}"
                r"(?:[\s.-]?\d{2,4}){1,4}\b"),
     _mark("phone")),
]


def _apply_identifiers(text: str) -> str:
    for _kind, pattern, repl in _IDENTIFIER_SHAPES:
        text = pattern.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
#   The public functions
# ---------------------------------------------------------------------------

def scrub_text(text: Any, *, identifiers: bool = True) -> str:
    """`text` with every recognised credential (and, by default, e-mail
    address, home-folder user name and +phone number) replaced by a
    `[redacted: <kind>]` marker.

    Always returns a str. Never raises: if anything inside fails, the whole
    text is withheld rather than passed through unscrubbed.
    """
    try:
        if text is None:
            return ""
        s = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
        if not s:
            return s
        s, _ = _replace_known(s)
        s = _cut_keys(s)
        s, _ = _apply_shapes(s)
        if identifiers:
            s = _apply_identifiers(s)
        return s
    except Exception:
        return _mark("text withheld - the scrubber failed on it")


def find_secret(text: Any) -> Optional[str]:
    """The KIND of the first credential found, or None. Never the value.

    For a caller that needs to know THAT a secret is in some text - the tool
    loop, which says so on the next approval card (jarvis_agent,
    SECRET_READ_LINE). E-mail addresses and the other identifiers are not
    secrets and are not checked.
    """
    try:
        s = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text or "")
        if not s:
            return None
        _, kind = _replace_known(s)
        if kind:
            return f"a credential this machine holds ({kind.replace(' value', '')})"
        if _PEM_BEGIN.search(s):
            return "a private key"
        for kind, pattern, _repl in _CONTEXT_SHAPES:
            if pattern.search(s):
                return f"a {kind}"
        for kind, pattern in _router_shapes():
            if pattern.search(s):
                return kind
        if _LABELLED[1].search(s):
            return "a labelled secret"
        return None
    except Exception:
        return "text that could not be checked (treated as a secret)"


# ---------------------------------------------------------------------------
#   stdout and stderr (backend.log)
# ---------------------------------------------------------------------------

class _ScrubbingStream:
    """Wraps sys.stdout or sys.stderr so every line is scrubbed before it
    reaches the real stream.

    LINE-BUFFERED ON PURPOSE. `print("Bearer", tok)` arrives as several
    write() calls, and a secret can straddle two of them. So text is held
    until a newline or a flush(). A key block spanning many lines is tracked
    across them - and let go of after _KEY_MAX_LINES, or at the first line
    that does not look like key material.
    """

    _FLUSH_AT = 64 * 1024

    def __init__(self, inner, *, identifiers: bool = True):
        self._inner = inner
        self._identifiers = identifiers
        self._buf = ""
        self._in_pem = False
        self._pem_lines = 0
        self._lock = threading.RLock()
        self._jarvis_scrub = True

    def _line(self, line: str) -> str:
        if self._in_pem:
            end = _PEM_END.search(line)
            if end:
                self._in_pem = False
                rest = line[end.end():]
                return scrub_text(rest, identifiers=self._identifiers) if rest.strip() else ""
            if self._pem_lines < _KEY_MAX_LINES and _key_line(line):
                self._pem_lines += 1
                return ""
            self._in_pem = False
        begin = _PEM_BEGIN.search(line)
        if (begin and not _PEM_END.search(line, begin.end())
                and not line[begin.end():].strip()):
            # A key block starts here and goes on over the next lines.
            self._in_pem = True
            self._pem_lines = 0
            nl = "\n" if line.endswith("\n") else ""
            return (scrub_text(line[:begin.start()], identifiers=self._identifiers)
                    + _mark("private key") + nl)
        return scrub_text(line, identifiers=self._identifiers)

    def _emit(self, chunk: str) -> None:
        if not chunk:
            return
        out = []
        for line in chunk.splitlines(keepends=True):
            try:
                out.append(self._line(line))
            except Exception:
                out.append(_mark("line withheld - the scrubber failed on it") + "\n")
        try:
            self._inner.write("".join(out))
        except Exception:
            pass

    def write(self, s) -> int:
        try:
            text = s if isinstance(s, str) else str(s)
        except Exception:
            return 0
        with self._lock:
            self._buf += text
            if "\n" in self._buf:
                cut = self._buf.rfind("\n") + 1
                ready, self._buf = self._buf[:cut], self._buf[cut:]
                self._emit(ready)
            if len(self._buf) >= self._FLUSH_AT:
                ready, self._buf = self._buf, ""
                self._emit(ready)
        return len(text)

    def writelines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        with self._lock:
            ready, self._buf = self._buf, ""
            self._emit(ready)
        try:
            self._inner.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        # encoding, isatty, fileno ... - everything else is the real stream's.
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
#   logging
# ---------------------------------------------------------------------------

_LOGGING_DONE = False


def _scrub_record(record) -> None:
    """Scrub one logging record in place: its message with the arguments put
    in, its traceback, its stack. Fails closed: a record that cannot be
    scrubbed carries a marker instead of its text."""
    import logging
    try:
        record.msg = scrub_text(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = scrub_text(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = scrub_text(record.exc_text)
        if record.stack_info:
            record.stack_info = scrub_text(record.stack_info)
    except Exception:
        record.msg = _mark("log message withheld - the scrubber failed on it")
        record.args = None
        record.exc_text = None
        record.exc_info = None
        record.stack_info = None


def _all_handlers() -> list:
    import logging
    loggers = [logging.getLogger()]
    try:
        loggers += [lg for lg in list(logging.Logger.manager.loggerDict.values())
                    if isinstance(lg, logging.Logger)]
    except Exception:
        pass
    seen, out = set(), []
    for lg in loggers:
        for h in list(getattr(lg, "handlers", []) or []):
            if id(h) not in seen:
                seen.add(id(h))
                out.append(h)
    return out


def _install_logging(old_streams: dict) -> None:
    """Every logging record, from any logger, scrubbed when it is made; and
    every handler already writing to the old stdout or stderr re-pointed at
    the scrubbed one."""
    global _LOGGING_DONE
    import logging
    if not _LOGGING_DONE:
        make = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            record = make(*args, **kwargs)
            _scrub_record(record)
            return record

        factory._jarvis_scrub = True
        logging.setLogRecordFactory(factory)
        _LOGGING_DONE = True
    for h in _all_handlers():
        stream = getattr(h, "stream", None)
        if stream is None or getattr(stream, "_jarvis_scrub", False):
            continue
        for old, new in old_streams.items():
            if stream is old:
                try:
                    h.setStream(new)
                except Exception:
                    try:
                        h.stream = new
                    except Exception:
                        pass
                break


def install(token: Any = None, *, identifiers: bool = True) -> bool:
    """Scrub everything this process prints and logs from now on. Idempotent.

    `token` is the pairing token (jarvis_hud passes HUD_TOKEN): it has no
    shape a pattern could find, so it is registered by value. Returns True
    when at least one stream is scrubbed.
    """
    import atexit
    register_secret(token)
    done = False
    old_streams: dict = {}
    for name in ("stdout", "stderr"):
        cur = getattr(sys, name, None)
        if cur is None:
            # pythonw, or a windowless build: there is no stream to wrap.
            continue
        if getattr(cur, "_jarvis_scrub", False):
            old_streams[cur._inner] = cur
            done = True
            continue
        wrapped = _ScrubbingStream(cur, identifiers=identifiers)
        setattr(sys, name, wrapped)
        atexit.register(wrapped.flush)
        old_streams[cur] = wrapped
        done = True
    # The streams Python started with, too: a handler made with
    # StreamHandler(sys.__stderr__) holds that object, not sys.stderr. It
    # keeps writing where it did, through a wrapper of its own.
    for name in ("stdout", "stderr"):
        orig = getattr(sys, f"__{name}__", None)
        if orig is not None and orig not in old_streams:
            old_streams[orig] = _ScrubbingStream(orig, identifiers=identifiers)
            atexit.register(old_streams[orig].flush)
    try:
        _install_logging(old_streams)
    except Exception:
        pass
    return done
