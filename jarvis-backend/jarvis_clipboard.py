"""jarvis_clipboard.py - an opt-in, RAM-only clipboard time machine.

WHY THIS EXISTS

The owner copies things all day: a link to clean up, a small table to turn
into Markdown, a JSON blob to read, a sentence to keep for a minute. A
clipboard history is useful for exactly that. But a clipboard is also the
surface a password manager's "copy password" button writes to, where a
one-time code from a phone lands, and where a private key or a card number
can pass by on its way somewhere else. So this module is built the other way
round from an ordinary clipboard manager: it keeps NOTHING until it is turned
on, it would rather refuse something useful than keep one secret, and it
forgets the lot on the next lock.

This is Pillar 14, slice 14A: the module and its suite only. NOTHING CALLS IT
YET. There is no route, no desktop command, no chat tool and no clipboard
hook in this slice - the desktop wiring (`commands.rs` and the Quickbar
transform drawer) is slice 14B, held until the `commands.rs` hand-off lands.
A future caller must still put the owner's one permission model
(`jarvis_gate`) in front of turning capture on; `enabled=False` is the floor
underneath that, not a replacement for it.

WHAT IT IS

    ring = ClipboardRing()           # OFF: every offer() stores nothing
    ring.enabled = True              # the owner's switch (see above)
    ring.offer("copied words", foreground_app="Code",
               foreground_title="notes.py")   # -> {"kept": True, "reason": ""}
    ring.items                       # newest first, each {"text","app","title"}
    ring.lock()                      # the machine locked: wiped AND captured off
    ring.clear()                     # wiped, still on if it was on

  * THE RING. One in-memory `collections.deque`, `max_items` (25) long and
    `max_item_chars` (32768) per item; `max_items` is an N_placeholder, not a
    measurement. The newest item is first in `items`. A text already in the
    ring is never stored twice: re-copying it moves that one entry to the top
    (so a run of copies of the same thing is one entry, not a pile).
  * offer() REFUSES, STORING NOTHING, for every one of these, with the reason
    in `reason`:
      - "disabled"                  the switch is off;
      - "not_text"                  the argument is not a str;
      - "empty"                     empty or only whitespace;
      - "too_large"                 longer than max_item_chars;
      - "excluded_app"              a password manager, a credential dialog or
                                    an owner-configured excluded app is named
                                    by foreground_app or foreground_title;
      - "scrubber_unavailable"      `jarvis_scrub` is missing or raised (fail
                                    closed: an unscrubbed clipboard is not
                                    kept);
      - "secret_detected"           the real `jarvis_scrub` flags or redacts
                                    something in the text, or the text holds a
                                    card number that passes the card check
                                    digit (the scrubber's own shapes want a
                                    label: a bare card number has none);
      - "secret_or_otp_detected"    a "-----BEGIN" block; a 4-8 digit code
                                    within 80 characters of PIN / code / OTP /
                                    verification / passcode / 2FA / login /
                                    sign-in wording, or a G-123456 style code;
                                    a single 12-128 character token mixing at
                                    least three of lower case, upper case,
                                    digits and symbols (a lone http(s) link is
                                    a link, not a password).
  * THE TRANSFORMS. `transform(text, kind)` is a pure function - it keeps
    nothing - for exactly three kinds, and always returns the same four keys
    `{"ok", "kind", "text", "reason"}`:
      - "markdown_table"       CSV or TSV (a tab on the first non-empty line
                               selects TSV) -> a pipe table with a `| --- |`
                               separator row. Refused in plain words under two
                               rows, under two columns, or when the rows are
                               ragged.
      - "pretty_json"          `json.loads` then `json.dumps(..., indent=2,
                               ensure_ascii=False)`; invalid JSON is refused,
                               never half-pretty-printed.
      - "strip_tracking_params" every http(s) URL in the text has the
                               tracking parameters (`utm_*`, `fbclid`,
                               `gclid`, `msclkid`, `mc_eid`, `igshid`,
                               `_hsenc`, `vero_id`, `mkt_tok`) removed through
                               `urllib.parse`, and every other parameter kept
                               in its order (`?id=42&page=2`). Text that is
                               not a URL is returned exactly as it was.

THE ONE PROMISE THIS MODULE MAKES ABOUT THE DISK

  Nothing here touches the disk. There is no file, no database, no journal,
  no cache and no second process: the ring is plain Python objects in this
  process's memory and dies with it. `backend/test_clipboard.py` proves that
  by watching the operating system's own file-access event while the module
  is driven in a fresh folder, and by checking that no file appeared there -
  it never reads this text. Clearing drops the last reference to each string,
  which is the most Python can honestly promise: CPython may not have zeroed
  the freed bytes yet, and this module does not claim otherwise. What it does
  promise is that a cleared ring is empty and that nothing was ever written
  anywhere to recover.

WHAT THIS MODULE DOES NOT DO, SAID PLAINLY

  * It does not capture anything itself. It is asked (offer) and that is all;
    a caller must decide when to ask.
  * It does not decide whether the clipboard may be watched. That is the
    owner's switch and, later, the one approval card.
  * It cannot recognise every secret. It uses the project's real scrubber
    (`jarvis_scrub.find_secret` / `scrub_text`, the same one the logs use)
    and adds three narrow shapes of its own - a PEM header, a contextual
    one-time code / lone high-entropy token, and a card number that passes the
    check digit. A brand-new key format, a screenshot of a password, or a
    secret split across two copies can still get through; privacy here comes
    from being OFF by default and from wiping on lock, not from a perfect
    classifier.
  * It does not try to scrub what it stores. Anything it keeps was already
    judged not to be a credential; it is kept verbatim so a transform can
    work on it.

Two files, one rule: `backend/jarvis_clipboard.py` and
`jarvis-backend/jarvis_clipboard.py` are kept byte-identical, like every
shipped module. It is registered at the END of `SHIPPED` in
`backend/_where.py` and of `$SHIPPED` in `scripts/apply-patches.ps1`, and the
base's `_where.py` is re-taken from it, never edited by hand.

TESTS: `backend/test_clipboard.py` proves every refusal branch, the dedup and
the ring's bounds, the instant wipe, all three transforms, that the real
scrubber is the judge, and - with an audit hook on the operating system's own
events - that driving this module opens and writes nothing at all.
"""
from __future__ import annotations

import collections
import csv
import io
import json
import re
import urllib.parse

try:  # the project's one scrubber; a backend without it must fail CLOSED
    import jarvis_scrub as _scrub
except Exception:                                              # noqa: BLE001
    _scrub = None

__all__ = ["ClipboardRing", "transform", "DEFAULT_MAX_ITEMS",
           "DEFAULT_MAX_ITEM_CHARS", "EXCLUDED_APPS", "TRACKING_PARAMS",
           "TRANSFORMS"]

#: How many copies the ring keeps. N_placeholder: not measured on real use.
DEFAULT_MAX_ITEMS = 25

#: The longest single item kept, in characters. 32768 is 32 KiB of plain text.
DEFAULT_MAX_ITEM_CHARS = 32768

#: A window title or process name holding any of these is refused: a password
#: manager's "copy password" and a credential dialog are the two cases the
#: ring exists to survive. Matched case-insensitively as a substring, because
#: a window's title reads "Sign in - Bitwarden" and not just "Bitwarden".
EXCLUDED_APPS = (
    "1password",
    "bitwarden",
    "keepass",
    "keepassxc",
    "dashlane",
    "lastpass",
    "proton pass",
    "windows security",
    "credential manager",
)

#: Query parameters that identify who clicked a link. A parameter that starts
#: with `utm_` (lower case) is treated the same way. Everything else is kept.
TRACKING_PARAMS = frozenset((
    "fbclid", "gclid", "msclkid", "mc_eid", "igshid", "_hsenc", "vero_id",
    "mkt_tok",
))

#: The only three transforms there are. A caller asking for a fourth gets a
#: plain refusal, not a guess at what they meant.
TRANSFORMS = ("markdown_table", "pretty_json", "strip_tracking_params")

#: Wording that signals a one-time code is about to appear (or has just
#: appeared). The 4-8 digit code must be within OTP_WINDOW characters of one
#: of these words, so "the login page loaded" is not a code.
_OTP_WORDS = re.compile(
    r"(?i)\b(code|otp|verification|verify|passcode|2fa|two-factor|one-time"
    r"|login|sign-in|security\s+code|pin)\b")
_OTP_CODE = re.compile(r"(?<!\d)\d{4,8}(?!\d)")
_OTP_AUTHENTICATOR = re.compile(r"(?i)\bG-\d{6}\b")
OTP_WINDOW = 80

#: A card number, written with or without spaces or dashes. The digits alone
#: are checked by the Luhn check digit; the scrubber has no shape for a bare
#: card number (its own rules want a label to go on), so the ring checks it.
#: A run whose separators MIX (a copied date and time, "2026-10-17 192216")
#: is not read as a card: a card's groups are separated one way, not two.
_CARD_RUN = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")

#: http(s) links, for the tracking-parameter transform.
_URL = re.compile(r"(?i)\bhttps?://[^\s<>\"']+")

#: Trailing punctuation that belongs to the sentence, not to the address.
_URL_TAIL = ".,;:!?"


# ---------------------------------------------------------------------------
#   The walk-through helpers the offers use
# ---------------------------------------------------------------------------

def _normalised(names) -> tuple:
    """The app names as lower-case, whitespace-stripped substrings."""
    out = []
    for name in names:
        text = str(name or "").strip().lower()
        if text:
            out.append(text)
    return tuple(out)


def _excluded(foreground_app: str, foreground_title: str, extra: tuple) -> bool:
    """Whether a window title or process name names a refused app."""
    haystack = f"{foreground_app}\n{foreground_title}".lower()
    if not haystack.strip():
        return False
    return any(name in haystack for name in EXCLUDED_APPS + extra)


def _luhn_ok(digits: str) -> bool:
    """The card check digit: 13 to 19 digits, correct check digit."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, char in enumerate(reversed(digits)):
        value = int(char)
        if i % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _card_number(text: str) -> bool:
    """Whether the text holds a card number that passes the check digit."""
    for match in _CARD_RUN.finditer(text):
        raw = match.group(0)
        separators = {char for char in raw if not char.isdigit()}
        if len(separators) > 1:
            continue
        digits = re.sub(r"\D", "", raw)
        if _luhn_ok(digits):
            return True
    return False


def _secret_reason(text: str) -> str:
    """The refusal the scrubber gives this text, or "" when it gives none.

    The real `jarvis_scrub` is the judge. It is asked twice on purpose:
    `find_secret` answers with the KIND of credential it saw (never a value),
    and `scrub_text(identifiers=False)` catches a shape the finding table does
    not name but the redacter does. Identifiers are deliberately left in: an
    e-mail address is not a credential, and the ring is for the owner's own
    words, not a log line.
    """
    if _scrub is None:
        return "scrubber_unavailable"
    try:
        if _scrub.find_secret(text):
            return "secret_detected"
        if _scrub.scrub_text(text, identifiers=False) != text:
            return "secret_detected"
    except Exception:                                          # noqa: BLE001
        return "scrubber_unavailable"
    if _card_number(text):
        return "secret_detected"
    return ""


def _one_time_code(text: str) -> bool:
    """Whether the text holds a one-time code with the wording that frames one."""
    for match in _OTP_WORDS.finditer(text):
        start = max(0, match.start() - OTP_WINDOW)
        end = min(len(text), match.end() + OTP_WINDOW)
        if _OTP_CODE.search(text, start, end):
            return True
    return bool(_OTP_AUTHENTICATOR.search(text))


def _password_like(text: str) -> bool:
    """Whether the text is ONE token shaped like a generated password.

    "One word, 12-128 characters, mixing at least three of lower case, upper
    case, digits and symbols." A lone http(s) link mixes those classes too,
    and is a link, not a password: it is what the tracking transform is for.
    """
    words = text.split()
    if len(words) != 1:
        return False
    token = words[0]
    if not 12 <= len(token) <= 128:
        return False
    if "://" in token:
        return False
    classes = (
        any(char.islower() for char in token),
        any(char.isupper() for char in token),
        any(char.isdigit() for char in token),
        any(not char.isalnum() for char in token),
    )
    return sum(classes) >= 3


# ---------------------------------------------------------------------------
#   The transforms (pure functions, keeping nothing)
# ---------------------------------------------------------------------------

def _result(ok: bool, kind, text: str, reason: str) -> dict:
    """The one shape every transform answer has."""
    return {"ok": bool(ok), "kind": str(kind), "text": text, "reason": reason}


def _cell(value: str) -> str:
    """One table cell: no raw pipe (it would end the cell) and no newline."""
    return value.strip().replace("\r\n", "\n").replace("\n", " ").replace("|", "\\|")


def _markdown_table(text: str) -> dict:
    """CSV or TSV -> a pipe table with a `| --- |` separator row."""
    first = ""
    for line in text.splitlines():
        if line.strip():
            first = line
            break
    delimiter = "\t" if "\t" in first else ","
    try:
        rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)
                if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        return _result(False, "markdown_table", "",
                       "that is not a table I can read: " + str(exc))
    if len(rows) < 2:
        return _result(False, "markdown_table", "",
                       "a table needs at least 2 rows")
    columns = len(rows[0])
    if columns < 2:
        return _result(False, "markdown_table", "",
                       "a table needs at least 2 columns")
    if any(len(row) != columns for row in rows):
        return _result(False, "markdown_table", "",
                       "every row needs the same number of columns")
    lines = ["| " + " | ".join(_cell(value) for value in rows[0]) + " |",
             "| " + " | ".join("---" for _ in range(columns)) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return _result(True, "markdown_table", "\n".join(lines) + "\n", "")


def _pretty_json(text: str) -> dict:
    """Valid JSON -> the same value indented two spaces; invalid -> refusal."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _result(False, "pretty_json", "", "that is not valid JSON")
    return _result(True, "pretty_json",
                   json.dumps(parsed, indent=2, ensure_ascii=False), "")


def _is_tracking(name: str) -> bool:
    """Whether one query parameter name is a click identifier."""
    lowered = name.lower()
    return lowered.startswith("utm_") or lowered in TRACKING_PARAMS


def _clean_url(match: "re.Match") -> str:
    """One URL with its tracking parameters removed and nothing else moved."""
    raw = match.group(0)
    tail = ""
    while raw and raw[-1] in _URL_TAIL:
        tail = raw[-1] + tail
        raw = raw[:-1]
    parts = urllib.parse.urlsplit(raw)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    kept = [(name, value) for name, value in pairs if not _is_tracking(name)]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path,
         urllib.parse.urlencode(kept), parts.fragment)) + tail


def _strip_tracking(text: str) -> dict:
    """Every http(s) URL's tracking parameters gone; all other text untouched."""
    return _result(True, "strip_tracking_params", _URL.sub(_clean_url, text), "")


def transform(text: str, kind: str) -> dict:
    """One of the three deterministic transforms, or a plain refusal.

    Always returns exactly `{"ok", "kind", "text", "reason"}`. `reason` is ""
    on success and a short plain-English sentence on refusal; nothing is ever
    half-transformed. The function keeps nothing and touches no other state.
    """
    if not isinstance(text, str):
        return _result(False, kind, "", "that is not text")
    if kind == "markdown_table":
        return _markdown_table(text)
    if kind == "pretty_json":
        return _pretty_json(text)
    if kind == "strip_tracking_params":
        return _strip_tracking(text)
    return _result(False, kind, "", "that is not a transform I know")


# ---------------------------------------------------------------------------
#   The ring
# ---------------------------------------------------------------------------

class ClipboardRing:
    """The opt-in, RAM-only ring buffer. See the module docstring for the lot."""

    def __init__(self, enabled: bool = False, *,
                 max_items: int = DEFAULT_MAX_ITEMS,
                 max_item_chars: int = DEFAULT_MAX_ITEM_CHARS,
                 excluded_apps=()):
        self.enabled = bool(enabled)
        self.max_items = max(1, int(max_items))
        self.max_item_chars = max(1, int(max_item_chars))
        self.excluded_apps = _normalised(excluded_apps)
        self._items = collections.deque(maxlen=self.max_items)

    @property
    def items(self) -> tuple:
        """The ring, newest first, as copies: a caller cannot edit the ring."""
        return tuple({"text": item["text"], "app": item["app"],
                      "title": item["title"]} for item in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def offer(self, text: str, *, foreground_app: str = "",
              foreground_title: str = "") -> dict:
        """Offer one copied text to the ring; store it or refuse it plainly.

        Returns `{"kept": bool, "reason": str}` and nothing else. A refusal
        stores nothing and leaves the ring exactly as it was.
        """
        if not isinstance(text, str):
            return {"kept": False, "reason": "not_text"}
        if not self.enabled:
            return {"kept": False, "reason": "disabled"}
        if not text.strip():
            return {"kept": False, "reason": "empty"}
        if len(text) > self.max_item_chars:
            return {"kept": False, "reason": "too_large"}
        if _excluded(foreground_app, foreground_title, self.excluded_apps):
            return {"kept": False, "reason": "excluded_app"}
        reason = _secret_reason(text)
        if reason:
            return {"kept": False, "reason": reason}
        if "-----BEGIN" in text.upper():
            return {"kept": False, "reason": "secret_or_otp_detected"}
        if _one_time_code(text):
            return {"kept": False, "reason": "secret_or_otp_detected"}
        if _password_like(text):
            return {"kept": False, "reason": "secret_or_otp_detected"}
        self._store(text, foreground_app, foreground_title)
        return {"kept": True, "reason": ""}

    def _store(self, text: str, app: str, title: str) -> None:
        """Put one accepted text at the top, moving an earlier copy there too."""
        for index, item in enumerate(self._items):
            if item["text"] == text:
                del self._items[index]
                break
        self._items.appendleft({"text": text, "app": str(app or ""),
                                "title": str(title or "")})

    def lock(self) -> None:
        """The machine locked: wipe the ring at once and stop capturing.

        Turning capture back on is the owner's switch, not something a lock
        event may do by itself.
        """
        self._items.clear()
        self.enabled = False

    def clear(self) -> None:
        """Wipe the ring at once, leaving the capture switch as it was."""
        self._items.clear()
