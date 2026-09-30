"""jarvis_secrets.py - finding anything that looks like a key, a token, a
password or a card number in the words read from a picture of the screen, and
working out what to black out.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
no patch). "Screen safety", the owner's "all three" of 2026-09-29
(CLAUDE.md), part 1: before a model, or a text reader's output, is used,
secrets in a screenshot are blacked out. jarvis_picture.py paints the boxes;
jarvis_screen.clean_picture is the one door a screen picture goes through.

HOW IT WORKS, IN PLAIN WORDS
  1. Windows' text reader (jarvis_ocr.py) finds the words in the picture and
     WHERE each one is.
  2. The words are put back in reading order as text, and patterns look for
     secrets in that text:
       * gitleaks's rules (backend/jarvis_secret_rules.py, generated; MIT) -
         what an AWS key, a GitHub token, a private key, a database password
         in an address and about two hundred other things look like;
       * Presidio's patterns (MIT; the regular expressions only, not the
         package) for a card number (and it must pass the card check digit -
         a made-up number that fails it is left alone), a crypto wallet (its
         own check digits too), an IBAN (mod-97), an email address and an
         IP address;
       * two small patterns of Jarvis's own, because the two above miss
         them: a value written next to the word "password", "PIN" or
         "secret" (gitleaks's broad rule wants 10 characters or more), and a
         private key that is cut off before its end line.
  3. Every word that overlaps a secret, even by one letter, is covered whole
     - a half-hidden secret is worse than none. A secret that runs over
     several lines (a wrapped token, a card number, a key) is covered on
     EVERY line: a second pass joins the lines end to end and any match that
     crosses a line is kept.
  4. The boxes are SOLID BLACK. Never blurred (a blur can be undone).
  5. The text handed on has each hidden run replaced by "[hidden]".

ONE MORE DESTINATION, ON PURPOSE (docs/ARCHITECTURE.md section 3, "redaction is
per-destination"): jarvis_router._SECRET_PATTERNS is a small table that only
decides whether a TYPED question may go to a cloud lane, and jarvis_scrub.py
cleans the log. Words read from a picture are free-form and can hold anything,
so this is a much larger table, for this one destination.

FAIL CLOSED. A pattern that cannot be run, a screen with so much small text
that it cannot be checked in time, a hidden word the reader gave no position
for: every one of these means the picture is NOT handed on
(Redaction.boxless / Unchecked), never "carry on unchecked".

WHAT IT CANNOT DO, SAID PLAINLY (the apps' help and docs/JARVIS-API.md 62.13
say the same):
  * A pattern is a guess from the SHAPE of the words. A password shown with a
    show-password eye, or typed into a box with nothing written beside it,
    has no shape a pattern can tell from any other word - and a password that
    is shown as dots is not readable at all (which is also why it is safe).
    The text-box check (jarvis_ui_control / jarvis_screen_win: a box that
    says IsPassword is skipped) and the Never look at list are the other two
    locks; none of the three is perfect alone.
  * Text the reader cannot read (very small, stylised, or in a picture)
    cannot be checked. A QR code, a photo of a card, a handwritten note.
  * It will sometimes black out something harmless (a long product code that
    looks like a key, a version number that looks like an IP address).
    That is the safe way round.

Tested on any machine: backend/test_secrets.py (true and false positives, a
card that fails the check digit, secrets over several lines, the fail-closed
cases) and backend/test_secret_rules.py (every generated rule compiles and
finds its own sample).
"""
from __future__ import annotations

import hashlib
import ipaddress
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

#: What a hidden run of words is replaced by in the text handed on.
HIDDEN = "[hidden]"

#: The Presidio-style kinds, all on. (Email addresses and IP addresses are
#: personal details rather than secrets; they are hidden too because the
#: owner asked for "anything that looks like a key, card number or password"
#: and a screen full of them is rarely what a question is about. To leave
#: them visible, take "email" and "ip" out of this tuple.)
PII_KINDS = ("card", "crypto", "iban", "email", "ip", "ssn")

#: The most text that is checked in one go. More than this cannot be checked
#: in reasonable time, so it is refused (fail closed), not skipped.
#: Was 80,000: on 70,000 characters of dense text (hex, base58, digits) the
#: check took 8-13 seconds, and a regular expression holds Python's lock while
#: it runs, so the event stream and the approval queue froze and the phone saw a
#: stale link. 25,000 keeps a dense screen to about three seconds.
MAX_SCAN_CHARS = 25_000
#: Seconds the whole check may take before it gives up (fail closed). The clock
#: is looked at between every rule AND every so many matches inside a rule.
BUDGET_S = 6.0
#: How far a box is grown past the reader's tight word rectangle, in pixels
#: (plus a tenth of its height), so an edge of a letter is never left out.
PAD_PX = 3

NOT_CHECKED = ("Jarvis could not check this picture for keys, passwords and card numbers, so it "
               "is not using it.")


class Unchecked(Exception):
    """The picture or its words could not be checked. The caller hands nothing
    on (the reason is a plain sentence)."""


# --------------------------------------------------------------------------
#   gitleaks rules
# --------------------------------------------------------------------------

_GENERIC = "generic-api-key"
_COMPILED: dict = {}


def _load_rules() -> list:
    """[(rule dict, compiled regex, [(target, [compiled], [stopwords])])],
    compiled once. Raises Unchecked when the rule data is missing or a rule
    does not compile - never carries on with fewer rules."""
    if "rules" in _COMPILED:
        return _COMPILED["rules"]
    try:
        import jarvis_secret_rules as R
        out = []
        for r in R.RULES:
            rx = re.compile(r["regex"], re.ASCII)
            allow = [(a["target"], [re.compile(x, re.ASCII) for x in a["regexes"]],
                      list(a["stopwords"])) for a in r["allow"]]
            out.append((r, rx, allow))
        glob = ([re.compile(x, re.ASCII) for x in R.GLOBAL_ALLOW["regexes"]],
                list(R.GLOBAL_ALLOW["stopwords"]))
    except Exception as exc:
        raise Unchecked("the secret patterns could not be loaded (%s)" % type(exc).__name__)
    _COMPILED["rules"] = out
    _COMPILED["global"] = glob
    return out


def shannon(s: str) -> float:
    """Bits of entropy per character, as gitleaks measures it."""
    if not s:
        return 0.0
    n = len(s)
    counts: dict = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _secret_group(m: "re.Match", group: int) -> int:
    if group > 0:
        return group if group <= (m.re.groups or 0) else 0
    for i in range(1, (m.re.groups or 0) + 1):
        if m.group(i):
            return i
    return 0


def _line_of(text: str, pos: int) -> str:
    a = text.rfind("\n", 0, pos) + 1
    b = text.find("\n", pos)
    return text[a:b if b >= 0 else len(text)]


def _allowed(rule: dict, allow: list, glob, text: str, m, secret: str) -> bool:
    low = secret.lower()
    sets = list(allow)
    if rule["id"] == _GENERIC:
        # gitleaks's global allowlist applies to every rule; here it is used
        # for the one broad rule only (see jarvis_secret_rules.GLOBAL_ALLOW).
        sets.append(("secret", glob[0], glob[1]))
    for target, regexes, stops in sets:
        if any(s and s in low for s in stops):
            return True
        if regexes:
            hay = {"secret": secret, "match": m.group(0), "line": _line_of(text, m.start())}.get(
                target, secret)
            if any(x.search(hay) for x in regexes):
                return True
    return False


def _tick(deadline: float) -> None:
    """Give up (fail closed) when the time limit has passed."""
    if time.monotonic() > deadline:
        raise Unchecked("checking took too long")


def _gitleaks_spans(text: str, deadline: float) -> list:
    """[(start, end, rule id)] for every gitleaks rule match in `text`."""
    out = []
    # gitleaks only tries a rule when one of its `keywords` is in the text,
    # to save time. That is NOT done here: at the size of a screen it saves
    # almost nothing (every rule over 60,000 characters takes well under a
    # second), and it would let a token through whose vendor's name is not
    # on the screen.
    for rule, rx, allow in _load_rules():
        _tick(deadline)
        time.sleep(0)                       # let the event stream's threads run
        for i, m in enumerate(rx.finditer(text)):
            if i % 32 == 0:
                _tick(deadline)
            g = _secret_group(m, rule["group"])
            s, e = m.span(g)
            if e <= s:
                continue
            secret = text[s:e]
            if rule["entropy"] and shannon(secret) <= rule["entropy"]:
                continue
            if _allowed(rule, allow, _COMPILED["global"], text, m, secret):
                continue
            out.append((s, e, rule["id"]))
    return out


# --------------------------------------------------------------------------
#   Presidio-style patterns (regular expressions from Presidio, MIT) and their
#   check digits, written here
# --------------------------------------------------------------------------

_CARD = re.compile(
    # 2221-2720 are Mastercard's 2-series; 56-58 are Maestro.
    r"\b(?!1\d{12}(?!\d))((4\d{3})|(5[0-8]\d{2})|(2(?:2[2-9]\d|[3-6]\d\d|7[01]\d|720))"
    r"|(6\d{3})|(1\d{3})|(3\d{3}))"
    r"[- ]?(\d{3,4})[- ]?(\d{3,4})[- ]?(\d{3,5})\b")
_CRYPTO = re.compile(r"(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,59}")
_IBAN = re.compile(r"(?<![A-Z0-9])([A-Z]{2}[0-9]{2}(?:[ -]?[A-Z0-9]{4}){2,6})"
                   r"((?:[ -]?[A-Z0-9]{4})?)((?:[ -]?[A-Z0-9]{1,3})?)(?![A-Z0-9])")
_EMAIL = re.compile(
    r"\b((([!#$%&'*+\-/=?^_`{|}~\w])|([!#$%&'*+\-/=?^_`{|}~\w][!#$%&'*+\-/=?^_`{|}~\.\w]{0,}"
    r"[!#$%&'*+\-/=?^_`{|}~\w]))[@]\w+(?:-+\w+)*(?:\.\w+(?:-+\w+)*)+)\b")
_OCTET = r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
_IPV4 = re.compile(r"\b" + _OCTET + r"\." + _OCTET + r"\." + _OCTET + r"\." + _OCTET
                   + r"(?:/(?:[0-2]?\d|3[0-2]))?\b")
_H = r"[0-9A-Fa-f]{1,4}"
_IPV6 = re.compile(
    r"(?<![\w:])(?:(?:" + _H + r":){7}" + _H + r"|(?:" + _H + r":){1,7}:|:(?::" + _H
    + r"){1,7}|(?:" + _H + r":){1,6}:" + _H + r"|(?:" + _H + r":){1,5}(?::" + _H
    + r"){1,2}|(?:" + _H + r":){1,4}(?::" + _H + r"){1,3}|(?:" + _H + r":){1,3}(?::" + _H
    + r"){1,4}|(?:" + _H + r":){1,2}(?::" + _H + r"){1,5}|" + _H + r":(?::" + _H
    + r"){1,6})(?:%[0-9a-zA-Z]+)?(?![\w:]|\.\d)")


def luhn_ok(digits: str) -> bool:
    """The card check digit. `digits` is only digits, 13 to 19 of them."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_ok(value: str) -> bool:
    """The IBAN check: the first four characters go to the end, letters become
    10..35, and the number leaves a remainder of 1 when divided by 97."""
    v = re.sub(r"[ -]", "", value).upper()
    if not 15 <= len(v) <= 34 or not v.isalnum():
        return False
    moved = v[4:] + v[:4]
    num = "".join(str(int(c, 36)) for c in moved)
    return int(num) % 97 == 1


_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _base58check_ok(addr: str) -> bool:
    try:
        n = 0
        for ch in addr:
            n = n * 58 + _B58.index(ch)
        pad = len(addr) - len(addr.lstrip("1"))
        raw = b"\x00" * pad + n.to_bytes((n.bit_length() + 7) // 8, "big")
        if len(raw) < 5:
            return False
        return hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] == raw[-4:]
    except ValueError:
        return False


def _bech32_ok(addr: str) -> bool:
    if addr.lower() != addr and addr.upper() != addr:
        return False
    a = addr.lower()
    pos = a.rfind("1")
    if pos < 1 or pos + 7 > len(a) or len(a) > 90 or any(c not in _BECH for c in a[pos + 1:]):
        return False
    hrp, data = a[:pos], [_BECH.index(c) for c in a[pos + 1:]]
    values = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp] + data
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i, g in enumerate((0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)):
            if (top >> i) & 1:
                chk ^= g
    return chk in (1, 0x2BC830A3)


def crypto_ok(addr: str) -> bool:
    if addr.startswith(("1", "3")):
        return _base58check_ok(addr)
    if addr.lower().startswith("bc1"):
        return _bech32_ok(addr)
    return False


def _email_ok(addr: str) -> bool:
    domain = addr.rsplit("@", 1)[-1]
    tld = domain.rsplit(".", 1)[-1]
    return len(tld) >= 2 and tld.isalpha() and "." in domain


def _ip_ok(v: str) -> bool:
    try:
        ipaddress.ip_interface(v)
        return True
    except ValueError:
        return False


#: A US social security number, 123-45-6789. Area 000, 666 and 9xx and group 00
#: or serial 0000 are never issued, so they are left alone; a date (2026-09-29),
#: a phone number (555-123-4567) and a longer digit run do not fit the shape.
_SSN = re.compile(r"(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])")


def _pii_spans(text: str, kinds: Iterable[str], deadline: float = float("inf")) -> list:
    out = []
    kinds = set(kinds)
    _tick(deadline)
    if "ssn" in kinds:
        for m in _SSN.finditer(text):
            out.append((m.start(), m.end(), "ssn"))
    if "card" in kinds:
        for m in _CARD.finditer(text):
            if luhn_ok(re.sub(r"[- ]", "", m.group(0))):
                out.append((m.start(), m.end(), "card"))
    if "crypto" in kinds:
        _tick(deadline)
        for m in _CRYPTO.finditer(text):
            if crypto_ok(m.group(0)):
                out.append((m.start(), m.end(), "crypto"))
    if "iban" in kinds:
        _tick(deadline)
        for m in _IBAN.finditer(text):
            g1, g2, g3 = m.group(1), m.group(2), m.group(3)
            # Longest first, then shorter, as Presidio does.
            for cand in (g1 + g2 + g3, g1 + g2, g1):
                if iban_ok(cand):
                    out.append((m.start(), m.start() + len(cand), "iban"))
                    break
    if "email" in kinds:
        _tick(deadline)
        for m in _EMAIL.finditer(text):
            if _email_ok(m.group(0)):
                out.append((m.start(), m.end(), "email"))
    if "ip" in kinds:
        for rx in (_IPV4, _IPV6):
            _tick(deadline)
            for m in rx.finditer(text):
                if _ip_ok(m.group(0)):
                    out.append((m.start(), m.end(), "ip"))
    return out


# --------------------------------------------------------------------------
#   Jarvis's own three small patterns
# --------------------------------------------------------------------------

#: A value written right after the word password / passcode / PIN / secret and
#: a colon or equals sign: "Password: hunter2", "PIN = 4821". gitleaks's broad
#: rule needs 10 characters or more; a real password is often shorter.
_LABELS = (r"(?:pass(?:word|wd|code|phrase)?|pwd|pin|secret|passwort|kennwort|"
           r"mot[ \t]+de[ \t]+passe|contrase[nñ]a)")
#: Before the label there must be no letter or digit (so "spin" is not "pin"),
#: but an underscore is fine: DB_PASSWORD=..., API_SECRET_KEY=... After it a
#: "_SUFFIX" is allowed for the same reason.
_LABELLED = re.compile(
    # The value may sit on the next line (a form's label above its box), after
    # "is" ("your password is ..."), and a passphrase runs on for a few words.
    r"(?<![A-Za-z0-9])" + _LABELS + r"(?:_[A-Za-z0-9_]{0,40})?(?![A-Za-z0-9])[ \t]*"
    r"(?:[:=]|\bis\b|\bist\b)\s{0,3}"
    r"([^\s]{3,64}(?:[ \t]+[^\s]{1,64}){0,5})", re.I)
#: "password hunter2" with no colon, or a label alone on its line with the value
#: on the next. Only the password words (not "pin", "secret" or a bare "pass"),
#: and only a value with a digit in it, so "password reset", "password manager"
#: and "Forgot password?" are left alone.
_BARE_LABEL = r"(?:pass(?:word|wd|code|phrase)|pwd|passwort|kennwort|contrase[nñ]a)"
_LABELLED_BARE = re.compile(
    r"(?<![A-Za-z0-9])" + _BARE_LABEL + r"(?![A-Za-z0-9_])[ \t]*(?:[ \t]|\n[ \t]*)"
    r"((?=[^\s]*\d)[^\s:]{5,64})(?![\w])", re.I)
#: Codes: "PIN 4821", "CVV: 123", "Your verification code is 482913", a code
#: on the line under its label. Digits only, so ordinary words are not caught.
_CODE = re.compile(
    r"\b(?:cvv2?|cvc2?|otp|pin|(?:verification|security|confirmation|one[- ]time|login|"
    r"auth(?:entication)?|access)[ \t]+(?:code|pin)|(?:your|the)[ \t]+(?:code|passcode))\b"
    r"[ \t]*(?:[:=]|\bis\b)?\s{0,3}"
    r"(\d(?:[ -]?\d){2,7})(?!\d)", re.I)
#: The code BEFORE its label: "482913 is your verification code", "G-482913 is
#: your Google verification code", "123456 is your PIN".
_CODE_FIRST = re.compile(
    r"(?<!\d)(\d(?:[ -]?\d){3,7})(?!\d)[ \t]+(?:is|=)[ \t]+(?:your|the|my)\b[^\n.]{0,40}?"
    r"\b(?:code|pin|otp|passcode|password)\b", re.I)
#: A login header: "Authorization: Bearer eyJ...", "Authorization: Basic dXNl...",
#: or a bare "Bearer <token>". At least 20 characters, and (bare) a digit in them.
_TOKEN_CHARS = r"[A-Za-z0-9._~+/=-]"
_AUTH_HEADER = re.compile(
    r"authorization[ \t]*[:=][ \t]*(?:(?:bearer|basic|token|digest)[ \t]+)?(" + _TOKEN_CHARS
    + r"{20,})", re.I)
_BEARER = re.compile(r"\bbearer[ \t]+((?=" + _TOKEN_CHARS + r"*\d)" + _TOKEN_CHARS + r"{20,})", re.I)
#: What is not a password after such a label: dots or stars (the box shows
#: nothing readable), or the plain words a form puts there.
_MASK = re.compile(r"^[●•·*xX.\-_]+$")
_NOT_A_VALUE = frozenset((
    "required", "optional", "hidden", "none", "n/a", "null", "true", "false", "yes", "no",
    "enter", "empty", "unknown", "reset", "strong", "weak", "changed", "saved",
    "must", "cannot", "can't", "invalid", "incorrect", "expired"))
#: A private key that is cut off before its end line (the screen ends, or the
#: text reader missed a line): hides everything from its first line on.
_PEM_OPEN = re.compile(
    r"-----BEGIN[ A-Z]{0,30}PRIVATE KEY(?: BLOCK)?-----[\s\S]*?"
    r"(?:-----END[ A-Z]{0,30}PRIVATE KEY(?: BLOCK)?-----|\Z)")


def _own_spans(text: str, deadline: float = float("inf")) -> list:
    out = []
    _tick(deadline)
    for m in _LABELLED.finditer(text):
        v = m.group(1)
        first = v.split()[0]
        if _MASK.match(first) or first.lower().strip(".,;") in _NOT_A_VALUE:
            continue
        out.append((m.start(1), m.end(1), "labelled-password"))
    for m in _LABELLED_BARE.finditer(text):
        v = m.group(1)
        if _MASK.match(v) or v.lower().strip(".,;") in _NOT_A_VALUE:
            continue
        out.append((m.start(1), m.end(1), "labelled-password"))
    _tick(deadline)
    for m in _CODE.finditer(text):
        out.append((m.start(1), m.end(1), "labelled-code"))
    for m in _CODE_FIRST.finditer(text):
        out.append((m.start(1), m.end(1), "labelled-code"))
    for rx in (_AUTH_HEADER, _BEARER):
        for m in rx.finditer(text):
            out.append((m.start(1), m.end(1), "login-header"))
    _tick(deadline)
    for m in _PEM_OPEN.finditer(text):
        out.append((m.start(), m.end(), "private-key-open"))
    return out


# --------------------------------------------------------------------------
#   Words, lines and boxes
# --------------------------------------------------------------------------

@dataclass
class Word:
    text: str
    box: Optional[tuple] = None        # (left, top, right, bottom) in pixels, or None


@dataclass
class Redaction:
    """What checking one picture's words found."""
    text: str = ""                     # the words, hidden runs replaced, lines joined by \n
    boxes: list = field(default_factory=list)   # padded solid-black boxes (l, t, r, b)
    hidden: int = 0                    # runs of words that were hidden
    boxless: bool = False              # a hidden word had no position: the picture cannot be cleaned
    kinds: list = field(default_factory=list)   # which patterns fired (fixed ids, never the secret)


def to_lines(lines) -> list:
    """The reader's lines (or plain text) as [[Word, ...], ...]. Accepts a
    string; a list of strings; a list of {"text", "words": [{"text", "left",
    "top", "width", "height"}]}. A line with no words of its own is split on
    spaces and its words have no position."""
    if isinstance(lines, str):
        lines = lines.split("\n")
    out = []
    for ln in lines or []:
        words = []
        if isinstance(ln, dict):
            for w in ln.get("words") or []:
                if not isinstance(w, dict):
                    continue
                t = " ".join(str(w.get("text") or "").split())
                if not t:
                    continue
                try:
                    l, tp = float(w["left"]), float(w["top"])
                    box = (l, tp, l + float(w["width"]), tp + float(w["height"]))
                except (KeyError, TypeError, ValueError):
                    box = None
                words.append(Word(t, box))
            if not words:
                ln = ln.get("text")
        if not words and isinstance(ln, str):
            words = [Word(t) for t in ln.split()]
        if words:
            out.append(words)
    return out


def _layout(lines: list, joiner: str) -> tuple:
    """(text, [(start, end, line index, word index)]) with words joined by a
    space and lines by `joiner`."""
    parts, spans, pos = [], [], 0
    for li, words in enumerate(lines):
        if li:
            parts.append(joiner)
            pos += len(joiner)
        for wi, w in enumerate(words):
            if wi:
                parts.append(" ")
                pos += 1
            parts.append(w.text)
            spans.append((pos, pos + len(w.text), li, wi))
            pos += len(w.text)
    return "".join(parts), spans


_LONG_RUN = re.compile(r"\S{8000,}")


def _find(text: str, kinds: Iterable[str], deadline: float) -> list:
    if len(text) > MAX_SCAN_CHARS:
        raise Unchecked("there is too much small text in the picture to check")
    if _LONG_RUN.search(text):
        # A blob with no spaces (a base64 or hex dump, a minified line): the
        # secret patterns take seconds on it, so it is "cannot check" at once.
        raise Unchecked("there is a very long run of characters with no spaces in it, "
                        "which cannot be checked quickly")
    return (_gitleaks_spans(text, deadline) + _pii_spans(text, kinds, deadline)
            + _own_spans(text, deadline))


def _overlapping(spans: list, s: int, e: int) -> list:
    """(line, word) of every word that overlaps [s, e). `spans` are in
    reading order, so both their starts and their ends only grow: the first
    candidate and the last are found by bisection, not by walking them all."""
    import bisect
    ends = [b for (_a, b, _li, _wi) in spans]
    lo = bisect.bisect_right(ends, s)
    out = []
    for a, b, li, wi in spans[lo:]:
        if a >= e:
            break
        if b > s:
            out.append((li, wi))
    return out


def redact(lines, *, kinds: Iterable[str] = PII_KINDS, clock=time.monotonic) -> Redaction:
    """Check the words for secrets. `lines` as `to_lines` takes. Raises
    Unchecked when it cannot be done (fail closed); otherwise a Redaction."""
    ls = to_lines(lines)
    if not ls:
        return Redaction()
    deadline = clock() + BUDGET_S
    hit: set = set()                      # (line index, word index) to hide
    ids: set = set()
    text_a, spans_a = _layout(ls, "\n")
    for s, e, rid in _find(text_a, kinds, deadline):
        for k in _overlapping(spans_a, s, e):
            hit.add(k)
            ids.add(rid)
    # Second pass: the lines end to end, so a token the screen wrapped is one
    # word again. Only a match that crosses a line is kept (the rest was
    # found above), and every line it touches is hidden.
    if len(ls) > 1:
        text_b, spans_b = _layout(ls, "")
        for s, e, rid in _find(text_b, kinds, deadline):
            touched = _overlapping(spans_b, s, e)
            if len({li for li, _wi in touched}) > 1:
                for k in touched:
                    hit.add(k)
                    ids.add(rid)
    return _build(ls, hit, sorted(ids))


def _build(ls: list, hit: set, ids: list) -> Redaction:
    out_lines, boxes, runs, boxless = [], [], 0, False
    for li, words in enumerate(ls):
        parts, run_words = [], []

        def close_run() -> None:
            nonlocal runs, boxless
            if not run_words:
                return
            runs += 1
            parts.append(HIDDEN)
            have = [w.box for w in run_words if w.box]
            if len(have) != len(run_words):
                boxless = True
            if have:
                l = min(b[0] for b in have)
                t = min(b[1] for b in have)
                r = max(b[2] for b in have)
                bt = max(b[3] for b in have)
                pad = PAD_PX + 0.1 * (bt - t)
                boxes.append((l - pad, t - pad, r + pad, bt + pad))
            run_words.clear()

        for wi, w in enumerate(words):
            if (li, wi) in hit:
                run_words.append(w)
            else:
                close_run()
                parts.append(w.text)
        close_run()
        out_lines.append(" ".join(parts))
    return Redaction(text="\n".join(out_lines), boxes=boxes, hidden=runs, boxless=boxless,
                     kinds=ids)


def check(lines, *, timeout: float = BUDGET_S + 5.0) -> Redaction:
    """`redact`, but run on its own thread and given up on after `timeout`
    seconds: an unlucky pattern that never comes back must not hold a look
    up for ever. Raises Unchecked (the caller hands on nothing) when it
    cannot be done or takes too long - never returns a half answer."""
    box: dict = {}

    def run() -> None:
        try:
            box["r"] = redact(lines)
        except BaseException as exc:          # noqa: BLE001 - reported below
            box["e"] = exc

    t = threading.Thread(target=run, name="jarvis-secret-check", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise Unchecked("checking took too long")
    if "e" in box:
        exc = box["e"]
        raise exc if isinstance(exc, Unchecked) else Unchecked(type(exc).__name__)
    return box["r"]


def redact_text(text: str) -> tuple:
    """(text with every hidden run replaced by "[hidden]", how many runs).
    For words that never had a picture (the window's own text, the phone's
    screen text). Raises Unchecked when it cannot be checked - the caller
    hands on NOTHING then. Text with nothing to hide comes back exactly as
    it was."""
    t = str(text or "")
    r = check(t)
    if not r.hidden:
        return t, 0
    return r.text, r.hidden
