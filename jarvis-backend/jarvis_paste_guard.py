"""jarvis_paste_guard.py - "Paste guard" (feasibility idea I115,
docs/FEASIBILITY-AUDIT-2026-09-26.md: "Keeps pasted passwords out of stored
history." / "Reuse jarvis_sensitive/jarvis_mail_mask patterns.").

NEW MODULE, shipped whole. No patch of its own - jarvis_chat_log.py calls
guard() on a user message's words, right before they are written to the
encrypted chat-history database, never before. THE MODEL ALREADY SAW THE
UNMASKED WORDS: jarvis_chat_log.record_turn() is called with `turn`, what
jarvis_agent.run_local_turn() already returned, so the turn this guards has
already been answered on the local model, with the real password, PIN or
code, exactly as the idea asks ("the model still sees it for this turn, on
the local model"). This module only decides what is worth KEEPING, forever,
encrypted, in a database the owner might one day export, back up, or search.

WHY A THIRD MASKER, NOT A CALL INTO jarvis_sensitive.py OR jarvis_mail_mask.py

Both already exist, and neither is the right shape to import from here:

  * jarvis_sensitive.py classifies a whole FACT ("is this worth asking
    about before saving?") - it is not spans, does not import cleanly
    without pulling in its model-calling machinery (ask_model,
    ollama_caller), and every pattern it owns is an underscore-prefixed
    module detail, not a published contract this module should depend on.
  * jarvis_mail_mask.py masks EMAIL text - untrusted, outside text, where a
    whole message is fair game to withhold on any doubt. A pasted password
    in the owner's own chat is the opposite: the point is to keep the rest
    of the message, in the owner's own words, and remove only the secret
    itself.

So this module is a third, deliberately small variant, in the spirit
crash_notes.rs's own `scrub()` already set for exactly this shape of
decision (its own doc comment: "not the same code as jarvis_scrub.py, on
purpose ... deliberately lighter"): the SAME PATTERN FAMILY as the other
two - a code word or label, a value near it, a handful of code shapes - reimplemented
against this module's one job, with no import between any of the three.

WHAT IS MASKED (a value, never the label around it)
  * "password is X", "pw: X", "PIN = X", "passcode - X", "my wifi password
    is X" - a credential word, then a value, in either order
    ("X is my password").
  * A one-time code, bare, near a code word ("here's the code: 482913",
    "OTP 738291") - the same shapes jarvis_mail_mask.py hides (4-8 digits,
    "123-456"/"123 456", "ABC-123456", a short letters-and-digits mix).

WHAT IS KEPT
  * Everything else in the message, word for word.
  * A credential WORD with no value near it ("I changed my password
    today", "two-factor is on for everything") - nothing to mask.
  * "password is fine/safe/wrong/expired/..." and the like - a small
    stoplist of the words that follow "is/are/was/were" without being a
    secret, the same shape jarvis_sensitive.py's own _NOT_A_VALUE guards.

THE MARKER IS THE "ONE FIXED LINE SAYING SO"

The idea's own words: "masked ... with one fixed line saying so". Rather
than a masked value AND a separate note, the marker itself says so, in
place, so the sentence still reads: "My wifi password is
[a password, PIN or code - kept out of the saved history]." - never a
half-redacted value, never a second banner elsewhere.

WHAT IT CANNOT CATCH - said plainly, the same as jarvis_mail_mask.py does
  * A bare "code" with no kind named ("the code is 482913") - see _LABEL's
    own comment for why: too many ordinary sentences in a developer's own
    chat name "the code" without meaning a secret.
  * A secret with no label word anywhere near it and no separator at all
    ("482913" alone on its own line, or "my new one is Sunshine123" with
    no "password"/"pin"/etc in the same message).
  * A secret split across two separate messages, or written in words
    ("four eight two one"), or inside a picture.
A pattern list never catches everything. This lowers what a stolen or
exported chat-history file can carry; it does not make pasting a real
password into chat a safe habit.

NEVER RAISES. On any internal error the text is returned UNCHANGED, masked
nothing: unlike jarvis_mail_mask.py's WITHHELD (email is untrusted input a
whole message may safely disappear from; the owner's own chat message is
not), a masking bug here would make an entire chat entry unreadable for no
security gain the encryption at rest was not already providing - see
jarvis_chat_log.py's own CredentialKey. Standard library only; no network,
no model.

    python3 test_paste_guard.py
"""
from __future__ import annotations

import re

#: The one fixed line that stands in for a masked value. Both apps' History
#: screens show this exactly as written - never a half-redacted value.
MASK = "[a password, PIN or code - kept out of the saved history]"

# --------------------------------------------------------------------------
#   Labels - the credential words a value is masked next to
# --------------------------------------------------------------------------

#: Mirrors jarvis_sensitive.py's own _CREDENTIALS_WEAK/_CREDENTIALS_STRONG
#: word choice (password, PIN, passcode, OTP, 2FA, a lock's own "...code",
#: the named "...code" phrases) - a smaller list, because this module only
#: ever masks a VALUE next to one of these, never classifies the sentence
#: as a topic. Deliberately NOT included: bare "code" alone - in a chat
#: with an app whose own owner writes software, "the code has a bug" is far
#: more common than a secret, and every real case this module needs to
#: catch already names what KIND of code it is (see the module docstring's
#: "WHAT IT CANNOT CATCH", further down, for this said plainly).
_LABEL = (
    r"pass(?:word|wd|code|phrase)s?|pw|pin(?:\s*codes?|\s*numbers?)?|otp|2fa|mfa|"
    r"two[- ]factor|two[- ]step|"
    r"(?:one[- ]time|verification|security|access|login|log[- ]in|sign[- ]in|"
    r"confirmation|auth(?:entication)?|recovery|door|alarm|gate|safe|garage|entry|"
    r"wi-?fi|wlan|unlock|keypad|building|sim|voicemail|screen[- ]?lock)\s+codes?"
)
_LABEL_WORD = re.compile(r"\b(?:" + _LABEL + r")\b", re.I)

#: Between a label and its value: EITHER a punctuation separator (: = - #,
#: any amount of it, with optional surrounding spaces) OR one of "is/are/
#: was/were/will be" between spaces. Proximity alone ("password today") is
#: never enough - see t_no_separator_no_match, which is exactly the bug an
#: earlier draft of this module had ("I changed my password today" got
#: "today" masked, because a `*`-only separator can match zero characters).
_SEP = r"(?:\s*[:#=\-]+\s*|\s+(?:is|are|was|were|will\s+be)\s+)"

#: A value token: no whitespace, sentence punctuation, or square bracket -
#: brackets are excluded so a value can never partially match INTO an
#: already-written MASK marker (which is itself bracketed), the same "a
#: marker is never matched again" rule jarvis_scrub.py and crash_notes.rs's
#: own MARK document. At least 2 characters: a single one is never a real
#: secret worth masking.
_VALUE = r"[^\s\"'.,;:!?\[\]]{2,}"

#: "password is X", "pw: X", "PIN = X" - label, then value.
_LABEL_THEN_VALUE = re.compile(
    r"\b(?P<label>" + _LABEL + r")\b" + _SEP + r"(?P<value>" + _VALUE + r")", re.I)

#: "X is my password", "X is the PIN" - value, then label.
_VALUE_THEN_LABEL = re.compile(
    r"(?P<value>" + _VALUE + r")\s+(?:is|are|was|were)\s+"
    r"(?:my|the|your|our|his|her|their)?\s*(?P<label>" + _LABEL + r")\b", re.I)

#: What follows "is/are/was/were" without being a secret: mirrors
#: jarvis_sensitive.py's own _NOT_A_VALUE, cut down to the words most likely
#: to actually follow a credential word in a sentence. Checked lower-cased,
#: with trailing punctuation already stripped by the caller.
_NOT_A_VALUE = frozenset("""
fine safe secure weak strong wrong correct changed reset required needed
enabled disabled on off here there gone lost forgotten saved stored
encrypted hashed expired temporary generated random set unique different
missing invalid valid not never also still just only same working broken
hidden masked shown blank empty done sorted fixed ignored good bad ok okay
it this that what nothing something everything anything
the a an my our his her their your same its
""".split())

# --------------------------------------------------------------------------
#   Bare codes - a code-shaped value with no separator at all, only near a
#   label word ("here's the code 482913", "OTP 738291")
# --------------------------------------------------------------------------

#: The same three shapes jarvis_mail_mask.py's own _NUMBERISH hides: 4-8
#: bare digits, "123-456"/"123 456", "ABC-123456" - plus a short
#: letters-and-digits mix (jarvis_mail_mask.py's own _ALNUM), because here
#: it is masked only near a label word, never on shape alone, so it needs
#: no code word restricted to just after it.
_DIGITS = r"(?<![\w.,:/$£€#+-])\d{4,8}(?![\w%]|[.,:/-]\d)"
_SPLIT = r"(?<![\w.,:/$£€#+-])(?<!\d )\d{3}[- ]\d{3}(?![\w%-]|[.,:/]\d| \d)"
_PREFIXED = r"(?<![\w-])[A-Za-z]{1,3}-\d{4,8}(?![\w-])"
_ALNUM = r"(?<![\w-])(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{5,10}(?![\w-])"
_CODEY = re.compile(f"{_PREFIXED}|{_SPLIT}|{_DIGITS}|{_ALNUM}")

#: How far (in characters) a bare code may be from a label word and still
#: count as belonging to it - the same idea as jarvis_mail_mask.py's NEAR.
NEAR = 40


def _strip_trailing_punct(value: str) -> tuple:
    """(value, trailing) - a sentence's own closing punctuation is not part
    of the masked value."""
    tail = ""
    while value and value[-1] in ".,;:!?\"'":
        tail = value[-1] + tail
        value = value[:-1]
    return value, tail


def _mask_labelled(text: str) -> tuple:
    """One pass over `text` masking every LABEL-THEN-VALUE and
    VALUE-THEN-LABEL pair. Returns (text, changed)."""
    changed = [False]

    def swap_after(m):
        value, tail = _strip_trailing_punct(m.group("value"))
        if not value or value.lower() in _NOT_A_VALUE:
            return m.group(0)
        changed[0] = True
        # Everything up to where "value" starts (the label and the
        # separator between it and the value) is kept verbatim; only the
        # value itself, plus the sentence punctuation _strip_trailing_punct
        # peeled off it, is replaced.
        prefix_len = m.start("value") - m.start(0)
        return m.group(0)[:prefix_len] + MASK + tail

    def swap_before(m):
        value = m.group("value")
        if not value or value.lower() in _NOT_A_VALUE:
            return m.group(0)
        changed[0] = True
        # Everything from where "value" ends (the rest of the match: "is
        # my password", etc.) is kept verbatim; only the value is replaced.
        suffix_start = m.end("value") - m.start(0)
        return MASK + m.group(0)[suffix_start:]

    out = _LABEL_THEN_VALUE.sub(swap_after, text)
    out = _VALUE_THEN_LABEL.sub(swap_before, out)
    return out, changed[0]


def _mask_bare_codes(text: str) -> tuple:
    """A code-shaped token within NEAR characters of a label word, with no
    separator at all. Only runs on text _mask_labelled has already left
    alone in that neighbourhood - see guard()'s docstring for why the two
    passes are separate rather than one shared scan."""
    labels = [m.span() for m in _LABEL_WORD.finditer(text)]
    if not labels:
        return text, False
    changed = False
    out, last = [], 0
    for m in _CODEY.finditer(text):
        s, e = m.start(), m.end()
        near = any(s - hi <= NEAR and lo - e <= NEAR for lo, hi in labels)
        if not near:
            continue
        # Already inside a MASK marker this same call already wrote - never
        # mask a mask (the same "a marker can never be matched again" rule
        # jarvis_scrub.py and crash_notes.rs's own MARK document).
        if MASK in text[max(0, s - len(MASK)):e + len(MASK)]:
            continue
        out.append(text[last:s])
        out.append(MASK)
        last = e
        changed = True
    out.append(text[last:])
    return ("".join(out) if changed else text), changed


def guard(text) -> tuple:
    """(masked_text, changed: bool). `text` is one user message's words,
    about to be written to the encrypted chat-history database (never
    before the model has already answered this turn - see the module
    docstring). Never raises: on any internal error, returns `(text,
    False)` unchanged."""
    try:
        t = str(text or "")
        if not t or not _LABEL_WORD.search(t):
            return t, False
        out, changed1 = _mask_labelled(t)
        out, changed2 = _mask_bare_codes(out)
        return out, (changed1 or changed2)
    except Exception:
        return text if isinstance(text, str) else str(text or ""), False
