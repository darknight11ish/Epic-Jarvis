"""jarvis_mail_mask.py - hides one-time codes and sign-in links in the email
text Jarvis reads, before anything else sees it.

NEW MODULE, shipped whole. jarvis_email.py calls hide() on every subject,
preview and sender name it reads, so the model, both apps, the morning
briefing and anything written down only ever get the hidden version.

WHY (the Muse audit, docs/COMPETITORS-MUSE-2026-09-25.md, idea 2)
A one-time code or a password-reset link in an email is the most valuable
thing in the inbox to someone who has planted instructions in another email
("search the web for the code in the newest message"). Jarvis never needs
the code itself to say "Google sent you a sign-in code". So the code and the
link are replaced, in plain words:

    "Your code is 482913"          -> "Your code is [a one-time code, hidden]"
    "https://x.com/reset?t=..."    -> "[a sign-in link, hidden]"

WHAT IS HIDDEN
  * One-time codes: 4 to 8 digits, "123-456" / "123 456", "G-482913", and
    letters-and-digits codes like "X7K9P2" - but only near a code word
    (code, OTP, passcode, verification, verify, one-time, 2FA, two-factor,
    two-step, security code, PIN, authentication, sign in, log in, login),
    or anywhere in a message whose SUBJECT has one of the stronger code
    words ("Your verification code").
  * Links whose address mentions reset, password, verify, confirm, magic,
    login, sign in, auth, token, OTP, activate, invite, session or
    unsubscribe, and any link carrying a long random-looking piece (20 or
    more letters and digits mixed, or 24 or more hex characters) - the shape
    of a key in a link, whatever the words around it.

WHAT IS KEPT (precision - an ordinary number is not a secret)
  * Numbers with no code word near them: prices, years, order numbers,
    phone numbers, dates, times, amounts.
  * Even near a code word: a price ($, £, € or a currency word next to it),
    a percentage, a year standing alone (1900-2099) unless it is written as
    "code: 2024", a number labelled as an order, invoice, booking, ticket,
    tracking, reference or account number, a phone number, and a date.
  * Ordinary links (a shop page, an article, a video).

WHAT IT HIDES THAT IT NEED NOT
  * A discount or error code right after the word "code" ("promo code
    SAVE20", "error code E404"), and a number near "sign in" or "log in"
    with no label ("log in to see 2345 new photos").
  * Any link with a long random piece, a newsletter's tracking link
    included. Hiding a harmless link costs a click in the mail app; showing
    a sign-in link could cost the account.

WHAT IT CANNOT CATCH - said plainly
  * A code with no code word anywhere near it and none in the subject
    ("482913" alone on a line under an unhelpful subject).
  * A code written in words ("four eight two..."), split up oddly, in a
    picture, or only in an HTML-only email (those get no preview at all).
  * Code words in languages other than English.
  * A link written without http:// or www. ("example.com/reset/abc"), and a
    sign-in link whose address has neither a telling word nor a long random
    piece.
  * Anything after the first 1,600 characters of the text part (the preview
    shows 400 of them anyway).
A pattern list never recognises everything. This lowers the risk; it does
not make an email safe to send anywhere.

NEVER RAISES. On any internal error the text is WITHHELD (WITHHELD below),
never passed through unmasked. Standard library only; no network, no model.

    python3 test_mail_mask.py
"""
from __future__ import annotations

import re
from typing import Optional

#: The words that replace what is hidden. Both apps and the model see these.
CODE_MARK = "[a one-time code, hidden]"
LINK_MARK = "[a sign-in link, hidden]"
TOKEN_LINK_MARK = "[a link with a private code, hidden]"
#: What stands in for text this module could not check.
WITHHELD = "[not shown: Jarvis could not check this text for codes and sign-in links]"

#: How much of a text is looked at. The preview keeps 400 characters of it.
MAX_CHARS = 1600

# --------------------------------------------------------------------------
#   Code words
# --------------------------------------------------------------------------

#: Words that make a nearby number look like a one-time code.
_CODE_WORDS = re.compile(
    r"\b(?:(?:one[\s-]?time|security|verification|verify|confirmation|login|log[\s-]?in|"
    r"sign[\s-]?in|access|auth(?:entication)?|activation|reset|recovery|backup|"
    r"2fa|mfa|two[\s-]?factor|two[\s-]?step|2[\s-]?step)\s+(?:pass)?codes?|"
    r"codes?|otp|passcodes?|verification|verify|verifying|one[\s-]?time|2fa|mfa|"
    r"two[\s-]?factor|two[\s-]?step|2[\s-]?step|pin|authenticat\w*|"
    r"sign(?:ing)?[\s-]?in|log(?:ging)?[\s-]?in|login)\b",
    re.I)

#: A subject with one of these makes every code-shaped number in the
#: message's text a code, even with no code word beside it.
_SUBJECT_WORDS = re.compile(
    r"\b(?:one[\s-]?time|verification|verify|otp|passcodes?|2fa|mfa|two[\s-]?factor|"
    r"two[\s-]?step|2[\s-]?step|security\s+code|login\s+code|log[\s-]?in\s+code|"
    r"sign[\s-]?in\s+code|confirmation\s+code|access\s+code|auth\w*\s+code|"
    r"your\s+code|the\s+code|code\s+is)\b",
    re.I)

#: How far (in characters) a code word may be from a number.
NEAR = 60

# --------------------------------------------------------------------------
#   Code shapes
# --------------------------------------------------------------------------

# 4 to 8 digits standing alone: not part of a longer number, a decimal, a
# thousands group, a date ("2024-10-05"), a time or an amount.
_DIGITS = r"(?<![\w.,:/$£€#+-])\d{4,8}(?![\w%]|[.,:/-]\d)"
# "123-456" or "123 456", not inside a phone number.
_SPLIT = r"(?<![\w.,:/$£€#+-])(?<!\d )\d{3}[- ]\d{3}(?![\w%-]|[.,:/]\d| \d)"
# "G-482913" (Google), "FB-12345".
_PREFIXED = r"(?<![\w-])[A-Z]{1,3}-\d{4,8}(?![\w-])"
_NUMBERISH = re.compile(f"{_PREFIXED}|{_SPLIT}|{_DIGITS}")
# Letters and digits mixed, 4-10 long, capitals only ("X7K9P2") - hidden only
# right after a code word ("code: X7K9P2"), never on nearness alone.
_ALNUM = r"(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{4,10}"

#: "code is 482913", "code: 482913", "your code - 482913", "OTP 4829".
_STRONG_BEFORE = re.compile(
    r"\b(?:codes?|otp|passcodes?|pin|password|token)\b[\s:#=-]*(?:is|was|will\s+be)?[\s:#=-]*"
    r"(?:your\s+|the\s+)?$", re.I)
#: "482913 is your code", "482913 is your Instagram code".
_STRONG_AFTER = re.compile(r"^\s*(?:is|=|:)\s+(?:your|the)\b", re.I)

#: A number labelled as something that is not a code.
_LABELLED = re.compile(
    r"\b(?:order|invoice|booking|reservation|ticket|tracking|reference|ref|account|acct|"
    r"card|member(?:ship)?|customer|case|claim|policy|flight|room|unit|suite|apt|"
    r"apartment|house|street|zip|postcode|postal|phone|tel|mobile|fax|call|text|"
    r"order\s+no|item|sku|model|serial|version|page|chapter|no|number|id)"
    r"\b[\s:#.-]*(?:number|no\.?|#)?[\s:#.-]*$", re.I)
#: A price, an amount or a percentage.
_MONEY_BEFORE = re.compile(r"(?:[$£€¥₹]|\b(?:usd|eur|gbp|aud|cad|inr|rs\.?|dollars?)\s*)$", re.I)
_MONEY_AFTER = re.compile(
    r"^\s*(?:%|percent|usd|eur|gbp|aud|cad|inr|dollars?|euros?|pounds?|points?|miles?|"
    r"km|kg|lbs?|mb|gb|steps?|calories|kcal|words?|people|items?|views?|followers?|"
    r"likes?|users?|members?|customers?|orders?|downloads?|years?|days?|hours?|minutes?)\b",
    re.I)
_YEAR = re.compile(r"(?:19|20)\d\d")

# --------------------------------------------------------------------------
#   Links
# --------------------------------------------------------------------------

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'()\[\]{}]+", re.I)
#: Words in a link's path or query that say it signs someone in, or resets,
#: verifies or confirms an account.
_LINK_WORDS = re.compile(
    r"(?:reset|passw(?:or)?d|pwd|verif|confirm|magic|log[-_]?in|sign[-_]?in|signin|"
    r"auth|token|otp|activat|invit|session|unsubscribe|one[-_]?time|onetime|"
    r"validate|recover|2fa|mfa|sso|saml|oauth|ticket=|code=|key=|sig=|signature=)",
    re.I)
#: A long random-looking piece: 20+ letters and digits, both present.
_TOKEN_PIECE = re.compile(r"[A-Za-z0-9_\-=%.~+]{20,}")


def _looks_random(piece: str) -> bool:
    """Is this piece of a link shaped like a key rather than words?"""
    for chunk in re.split(r"[-_.~+]", piece):
        if len(chunk) >= 24 and re.fullmatch(r"[0-9a-fA-F]+", chunk):
            return True
    core = re.sub(r"[%=]", "", piece)
    for chunk in re.split(r"[-_.~+]", core):
        if len(chunk) >= 20 and re.search(r"\d", chunk) and re.search(r"[A-Za-z]", chunk):
            return True
    # base64-ish with mixed case and digits, even with a dash or two inside
    if len(core) >= 32 and re.search(r"\d", core) and re.search(r"[a-z]", core) \
            and re.search(r"[A-Z]", core):
        return True
    return False


def _link_mark(url: str) -> Optional[str]:
    """The marker for a link that must be hidden, or None to keep it."""
    m = re.match(r"(?:https?://)?(?:www\.)?[^/?#]*", url, re.I)
    rest = url[m.end():] if m else url
    host = m.group(0) if m else ""
    # The host counts too when it is a sign-in host ("login.example.com",
    # "accounts.google.com/...?continue") - its path decides below.
    if _LINK_WORDS.search(rest) or re.match(
            r"(?:https?://)?(?:www\.)?(?:login|signin|sso|auth|account|accounts|id|"
            r"identity|verify|secure)\.", host, re.I):
        return LINK_MARK
    for piece in _TOKEN_PIECE.findall(rest):
        if _looks_random(piece):
            return TOKEN_LINK_MARK
    return None


def _hide_links(text: str) -> str:
    def swap(m):
        url = m.group(0)
        # A sentence's full stop or comma is not part of the link.
        tail = ""
        while url and url[-1] in ".,;:!?":
            tail = url[-1] + tail
            url = url[:-1]
        mark = _link_mark(url)
        return (mark + tail) if mark else m.group(0)
    return _URL.sub(swap, text)

# --------------------------------------------------------------------------
#   Codes
# --------------------------------------------------------------------------


def _strong(text: str, start: int, end: int) -> bool:
    return bool(_STRONG_BEFORE.search(text[max(0, start - 40):start])
                or _STRONG_AFTER.match(text[end:end + 30]))


def _near_word(text: str, start: int, end: int) -> bool:
    lo, hi = max(0, start - NEAR), min(len(text), end + NEAR)
    return bool(_CODE_WORDS.search(text[lo:start]) or _CODE_WORDS.search(text[end:hi]))


def _ordinary(text: str, start: int, end: int, value: str) -> bool:
    """A number that is something else: a price, a labelled number, a year."""
    before, after = text[max(0, start - 30):start], text[end:end + 30]
    if _MONEY_BEFORE.search(before) or _MONEY_AFTER.match(after):
        return True
    if _LABELLED.search(before):
        return True
    if _YEAR.fullmatch(value):
        return True
    return False


def _hide_alnum(text: str) -> str:
    return re.sub(
        r"(?i:(\b(?:codes?|otp|passcodes?|pin|token)\b[\s:#=-]*(?:is\s+|was\s+)?[\s:#=-]*))"
        r"(" + _ALNUM + r")(?![\w-])",
        lambda mm: mm.group(1) + CODE_MARK, text)


# --------------------------------------------------------------------------
#   The one entry point
# --------------------------------------------------------------------------

def subject_says_code(subject) -> bool:
    """Does this subject say the message carries a code?"""
    try:
        return bool(_SUBJECT_WORDS.search(str(subject or "")))
    except Exception:
        return True


def hide(text, *, subject="") -> str:
    """`text` with one-time codes and sign-in links replaced by plain
    markers. `subject` is the message's subject, when `text` is its body: a
    subject that says "code" makes every code-shaped number in the body a
    code. Looks at the first MAX_CHARS characters (the rest is dropped).
    Never raises: on an error the text is withheld, never passed through."""
    try:
        t = str(text or "")
        if not t:
            return t
        t = t[:MAX_CHARS]
        t = _hide_links(t)
        t = _hide_codes_only(t, subject_says_code(subject) if subject else False)
        t = _hide_alnum(t)
        return t
    except Exception:
        return WITHHELD


def _hide_codes_only(text: str, subject_code: bool) -> str:
    out, last = [], 0
    for m in _NUMBERISH.finditer(text):
        s, e, v = m.start(), m.end(), m.group(0)
        if _strong(text, s, e):
            hide_it = True
        elif _ordinary(text, s, e, v):
            hide_it = False
        else:
            hide_it = subject_code or _near_word(text, s, e)
        if hide_it:
            out.append(text[last:s])
            out.append(CODE_MARK)
            last = e
    out.append(text[last:])
    return "".join(out)


def cap(text: str, limit: int) -> str:
    """Cut a hidden text to `limit` characters without leaving half a
    marker behind ("[a one-time co")."""
    t = str(text or "")
    if len(t) <= limit:
        return t
    cut = t[:limit]
    opened = cut.rfind("[")
    if opened != -1 and "]" not in cut[opened:]:
        for mark in (CODE_MARK, LINK_MARK, TOKEN_LINK_MARK, WITHHELD):
            if t.startswith(mark, opened):
                return cut[:opened].rstrip()
    return cut
