"""jarvis_voiceprint.py - "Write Like Me": sound like the owner, on his own PC.

WHAT THIS IS

Jarvis writes a lot of prose *as* the owner: email drafts, notes, messages.
This module is the engine that makes those drafts sound like him. It does that
in three steps, all of them local, all of them plain code:

  1. FIND how he has written about something similar before (an exemplar);
  2. STRIP the names, addresses and numbers out of that exemplar, so the shape
     of the sentences survives but nothing private does;
  3. MEASURE the result against a voiceprint - a small set of numbers worked
     out from his own writing - and score how closely a draft matches.

Nothing is sent anywhere. No weights are changed. The model is shown examples
at generation time, which is the one approach that both fits on this PC and can
be undone.

WHERE THIS MODULE CAME FROM, AND WHY IT IS NOT jarvis_style.py

`jarvis-backend/jarvis_style.py` already contains an earlier version of steps
1 and 2 - its `strip_entities`, `exemplars` and `prompt_block`. It is NOT
delivered to the owner's PC: it is in no patch the installer applies and in no
`$SHIPPED` entry, so `scripts/apply-patches.ps1` never writes it. Measured, the
repository holds exactly ONE copy of it:

    backend/jarvis_style.py          absent
    backend/rebuilt/jarvis_style.py  absent
    jarvis-backend/jarvis_style.py   present     <- the only copy

An edit there reaches nobody, and - measured - it has no call site at all: only
`rebuilt/jarvis_events.py` probes it by name for the "persona" capability and
`selftest.py` names it in a list. Nothing runs it.

The owner's decision (2026-10-15, from the review of the original plan) is the
one recorded in `docs/ARCHITECTURE.md` section 8: leave `jarvis_style.py`
exactly as it is - editing it would reach nobody, and promoting it into
`$SHIPPED` would make the installer start overwriting a file it has never
managed - and build the engine here, where it ships.

So this module is deliberately SELF-CONTAINED and does NOT import
`jarvis_style`. That is a rule, not an accident: on the owner's PC
`jarvis_style.py` IS present, so a `try: import jarvis_style` fallback would
silently run the OLD code on the one machine that matters. The stripping below
is this module's own, and its coverage is stated in the table further down.

WHAT IT STRIPS, MEASURED (2026-10-15, the system Python 3.12, no network)

The earlier engine carried eight regular expressions and a proper-noun walk,
and this one keeps all eight, byte for byte. It also closes the gaps that a
read-only probe of the earlier engine measured - cases where a number survived
into the text that is handed to a model. Every line below is a measured output
of `strip_entities` in THIS module, and the invariant is absolute: **no digit
survives**.

    input                                  output
    -------------------------------------- -----------------------------------
    'due 14/03/2026 today'                 'due [date] today'
    'due 03/14/2026 today'                 'due [date] today'
    'due 1/2/26 today'                     'due [date] today'
    'due 14-03-2026 today'                 'due [date] today'
    'due 2026-03-14 today'                 'due [number] today'
    'Meeting moved to 9:30 on Friday.'     'Meeting moved to [time] on Friday.'
    'the file is /home/user/notes.txt'     'the file is [path]'
    'Send it to john.smith@example.com'    'Send it to [email]'
    'ping me @mario on https://x.example'  'ping me [handle] on [link]'
    'The budget is $12,500.'               'The budget is [amount].'
    'The invoice for Acme Ltd is 89.99.'   'The invoice for [name] [name] is [amount].'
    'I paid 1,200 for the boiler.'         'I paid [amount] for the boiler.'
    'I paid 4500 for the boiler.'          'I paid [number] for the boiler.'
    'The PIN is 4821.'                     'The PIN is [number].'
    'Order 55123 arrived.'                 'Order [number] arrived.'
    'My postcode is CB1 2AB.'              'My postcode is [postcode].'
    'Ring the dentist on 01223 456789.'    'Ring the dentist on [number].'
    "Priya's number is 07700 900123."      "[name] number is [number]."
    'Account 44332211 with Barclays.'      'Account [number] with [name].'
    'Send it to 12 Oak Street, Cambridge.'  'Send it to [number] [name] [name], [name].'

Two of those were real leaks in the earlier engine and are worth naming, because
both are the same mistake - a pattern eating part of a value and leaving the
front of it behind:

  * `_PATH` ran BEFORE `_DATE`, and `_PATH` matches a sub-span INSIDE a
    slash-date: for 'due 14/03/2026 today' it matched '/03/2026' at (6,14)
    while `_DATE` would have matched (4,14), so the day survived as
    'due 14[path] today'. `_DATE` now runs first.
  * `_PHONE` required a 3-4 digit group first, so for '01223 456789' it matched
    only '456789' and the area code survived. It now accepts a leading 0.

The last line of defence, after every pattern above and the proper-noun walk,
replaces any remaining run of digits with `[number]`. That is what makes "no
digit survives" a property of the code rather than a hope, and
`backend/test_voiceprint.py` asserts it for every row of the table and then for
every line of this module's own docstring.

SENTENCE-OPENING NAMES (fixed 2026-10-20, Area 5 audit). The proper-noun walk
used to skip every capitalised word that OPENS a sentence, so "Priya's number
is ..." kept the name. Four rules now replace an opening name while leaving
ordinary openers alone: a possessive whose base is not a grammar contraction
("Priya's" -> "[name]"), a direct-address vocative such as "Sam," or "Hi Sam,"
("[name],"), an honorific ("Dr. Patel" -> "[name]"), and a name repeated at the
start of two sentences. Closed sets keep "It's ready.", "Thanks, I'll check."
and the usual conversational openers intact, and the no-digit guarantee is
unchanged.

WHAT IT IS NOT

- It is not a fine-tune. A LoRA adapter for an 8B model needs 7.5-9 GB and this
  card has 8 GB with a desktop compositor on it; more importantly, rolling back
  a retrieval index is free and rolling back weights is not.
- It does not learn from anything but the owner's own words. Nothing is read
  from a web page, an email, a document or a tool result.
- It does not weaken the memory store. Retrieval goes THROUGH
  `jarvis_memory`, so it trips the same taint latch every other memory read
  trips, and the turn stays on the local model.

THE PERMISSION MODEL, SAID PLAINLY

`POST /api/voiceprint/sample` and `POST /api/voiceprint/learn_edit` write the
owner's OWN words into a store on his OWN PC. They raise NO approval card, and
that matches the owner's decision of 2026-09-24 ("Jarvis learns automatically
by default ... facts ... learned from the owner's own words only ... are saved
without a per-fact yes"). Nothing leaves the PC: this is a memory write, not an
action on the world.

`POST /api/voiceprint/forget` is different, and it is deliberately harder. The
owner kept the question - 2026-09-24: every learned thing "is listed in both
apps with a Forget (it asks 'are you sure?' first ... because forgetting cannot
be undone)". So the route REFUSES a forget that does not carry
`"confirm": true`, and says so in plain words. That is the question, enforced
in the place that cannot be skipped by a different client.

Every write is guarded by `jarvis_scrub` and FAILS CLOSED - with no scrubber
nothing is written at all. The pattern is `jarvis_receipts.py`'s, copied
deliberately: its `_scrubber()` at `jarvis_receipts.py:289-295` and its refusal
at `:443-449`.

ROUTES

    GET  /api/voiceprint            the list of learned samples, the voiceprint
                                    numbers, and what the engine is doing
    POST /api/voiceprint/sample     one piece of the owner's own writing
    POST /api/voiceprint/learn_edit his final version of a draft, as a gold sample
    POST /api/voiceprint/forget     delete one sample; needs "confirm": true

They arrive with no patch at all: `plugins/ready/voiceprint/plugin.json` names
this module and `backend/jarvis_plugins.py` makes the call the patch would have
made. Standard library only - no network, no subprocess, no third-party package.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import time
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import jarvis_framework as fw
except Exception:                                    # pragma: no cover
    fw = None


ENABLED_PATH = "/api/voiceprint/enabled"
ENABLED_FILE = "voiceprint.json"


def _enabled_file() -> Path:
    return _config_dir() / ENABLED_FILE


def _enabled_override() -> Optional[bool]:
    """The owner's ON/OFF switch, when this module's own file has it. Never raises."""
    try:
        doc = json.loads(_enabled_file().read_text(encoding="utf-8"))
        value = doc.get("enabled") if isinstance(doc, dict) else None
        return value if isinstance(value, bool) else None
    except Exception:
        return None


def set_enabled(on: bool) -> dict:
    """Write the ON/OFF switch. No card, no network, this PC only.

    One small JSON file beside the settings (the same pattern receipts use);
    written to a .tmp then os.replace so a crash cannot leave half a file."""
    if not isinstance(on, bool):
        return {"ok": False, "error": "bad_body",
                "message": "enabled must be true or false"}
    path = _enabled_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"enabled": on}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "error": "not_written",
                "message": f"could not save the switch ({type(exc).__name__})"}
    _audit("voiceprint.enabled", {"on": on})
    return {"ok": True, "enabled": on}


def _cfg(key: str, default):
    """This module's settings, from `[voiceprint]` in jarvis-framework.toml.

    The three keys the earlier engine had (`enabled`, `exemplars`,
    `min_words`) also fall back to `[style]`, so a setting the owner already
    has keeps meaning what it meant.
    """
    if key == "enabled":
        own = _enabled_override()
        if own is not None:
            return own
    try:
        got = fw.load_framework()
    except Exception:
        return default
    for table in ("voiceprint", "style"):
        try:
            value = (got.get(table) or {}).get(key)
        except Exception:
            continue
        if value is not None:
            return value
    return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Stripping
# --------------------------------------------------------------------------
# Deliberately blunt. A clever entity recogniser would miss a different set of
# things and would be a dependency and a model; these patterns are the ones
# whose presence in a colleague-facing note would actually matter, and a false
# positive costs a placeholder in a sample nobody reads directly.
#
# The first eight are the earlier engine's, carried unchanged
# (jarvis-backend/jarvis_style.py:76-84). The rest close gaps that a probe
# measured, and the LAST one is the guarantee.

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_URL = re.compile(r"\bhttps?://\S+", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?"
                    r"(?:0\d{2,4}|\d{3,4})[\s-]?\d{3,4}(?:[\s-]?\d{2,4})?(?!\w)")
_MONEY = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?(?:\s?[kKmMbB])?")
_LONGNUM = re.compile(r"(?<!\w)\d[\d\s-]{5,}\d(?!\w)")
_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+|(?:/[\w.-]+){2,})")
_DATE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_HANDLE = re.compile(r"(?<![\w/])@[A-Za-z][\w.-]{2,}")

# Added 2026-10-15 (the owner's decision, from the review of the first plan).
_TIME = re.compile(r"(?<!\w)\d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]\.?m\.?)?(?!\w)", re.I)
_POSTCODE = re.compile(r"(?<!\w)[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}(?!\w)")
_DECIMAL = re.compile(r"(?<!\w)\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\w)"
                      r"|(?<!\w)\d+\.\d+(?!\w)")
# The guarantee. After every pattern above has had its turn, any run of digits
# that is still here becomes [number]. Without this, "no digit survives" is a
# claim about the patterns; with it, it is a property of the function.
_ANY_DIGITS = re.compile(r"\d+")

# A capitalised word that is not at the start of a sentence and is not one of
# the ordinary ones. Crude, and that is the point: it over-strips rather than
# leaving a surname in. (Unchanged from jarvis_style.py:89-95.)
_COMMON = frozenset("""
i a an the and or but if then so because while when where what who why how
monday tuesday wednesday thursday friday saturday sunday january february
march april may june july august september october november december
i'm i'll i've it's that's there's here's we're they're you're don't can't
ok okay yes no thanks hi hello dear regards best cheers
""".split())

#: Every substitution, in order, as (pattern, label). Exposed as data rather
#: than buried in the function so a test can assert the order is what it says
#: - the date-before-path bug was an ORDER bug, and order is the thing that
#: must not silently change.
#: Sentence-openers whose possessive form is grammar, not a person.
_KEEP_CONTRACTIONS = frozenset({
    "it", "that", "what", "there", "here", "let", "who", "how", "where", "when",
    "why", "today", "tomorrow", "yesterday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday",
})

#: Openers that are not vocatives even when followed by a comma.
_VOCATIVE_OPENERS = frozenset({
    "hi", "hey", "hello", "dear", "thanks", "thank", "yes", "no", "sure", "well",
    "ok", "okay", "first", "second", "third", "finally", "also", "however",
    "meanwhile", "honestly", "frankly", "basically", "personally", "fortunately",
    "unfortunately", "actually", "overall", "anyway", "besides", "still", "plus",
})

SUBSTITUTIONS = (
    (_URL, "[link]"),
    (_EMAIL, "[email]"),
    (_DATE, "[date]"),        # BEFORE _PATH: _PATH matches inside a slash-date
    (_TIME, "[time]"),
    (_POSTCODE, "[postcode]"),
    (_PATH, "[path]"),
    (_HANDLE, "[handle]"),
    (_MONEY, "[amount]"),
    (_DECIMAL, "[amount]"),
    (_PHONE, "[number]"),
    (_LONGNUM, "[number]"),
)


@dataclass
class Exemplar:
    """One piece of the owner's own writing, with its private parts removed."""
    text: str
    source: str
    when: Optional[float] = None
    stripped: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def strip_entities(text: str) -> tuple:
    """Return (text, count): the text with names and numbers taken out.

    Every replacement keeps its shape as a lowercase label, so a sentence reads
    as a sentence rather than collapsing. The count is how many substitutions
    were made, which the audit line records.

    The invariant, asserted for every row of this module's docstring table by
    backend/test_voiceprint.py: **the returned text contains no digit.**
    """
    n = 0

    def sub(rx, label, s):
        nonlocal n
        out, k = rx.subn(label, s)
        n += k
        return out

    s = text or ""
    for rx, label in SUBSTITUTIONS:
        s = sub(rx, label, s)

    # Area 5/Write-Like-Me audit (2026-10-20): names OPEN a sentence all the time,
    # and the old rule skipped every sentence-opening token. Four conditions now
    # replace one, while the closed sets keep "It's", "Thanks," and ordinary
    # conversational openers intact.
    first = r"(^|(?<=[.!?]\s)|\n)"

    def possessive(m):
        nonlocal n
        if m.group(2).lower() in _KEEP_CONTRACTIONS:
            return m.group(0)
        n += 1
        return m.group(1) + "[name]"

    s = re.sub(first + r"([A-Z][a-z]{1,20})['\u2019]s\b", possessive, s)

    def vocative(m):
        nonlocal n
        if m.group(3).lower() in _VOCATIVE_OPENERS:
            return m.group(0)
        n += 1
        greeting = (m.group(2) or "")
        return m.group(1) + greeting + "[name], "

    s = re.sub(first + r"((?:Hi|Hey|Hello|Dear)[ ,]+)?([A-Z][a-z]{1,20}),\s",
               vocative, s)

    def honorific(m):
        nonlocal n
        n += 1
        return m.group(1) + "[name]"

    s = re.sub(first + r"((?:Dr|Mr|Mrs|Ms|Prof)\.\s+[A-Z][a-z]+(?: [A-Z][a-z]+)?)",
               honorific, s)

    # A name repeated at the start of two sentences is certainly a name, not a
    # one-off opener; replace every such start before the mid-sentence check.
    starts = re.findall(r"(?:^|(?<=[.!?]\s)|\n)([A-Z][a-z]{1,20})\b", s)
    repeated_starts = {w for w in starts if starts.count(w) >= 2}

    def repeated_start(m):
        nonlocal n
        if m.group(2) in repeated_starts:
            n += 1
            return m.group(1) + "[name]"
        return m.group(0)

    s = re.sub(r"(^|(?<=[.!?]\s)|\n)([A-Z][a-z]{1,20})\b", repeated_start, s)

    # A capitalized word that also appears capitalized mid-sentence is a person
    # (or a brand) the writing keeps naming; replace it where it opens a sentence.
    mid_names = set(re.findall(r"(?<=[a-z0-9,;]\s)([A-Z][a-z]{1,20})\b", s))

    def repeated(m):
        nonlocal n
        if m.group(2) in mid_names:
            n += 1
            return m.group(1) + "[name]"
        return m.group(0)

    s = re.sub(first + r"([A-Z][a-z]{1,20})\b", repeated, s)

    # Proper nouns last, so the patterns above have already taken their pieces.
    # A token that is already a placeholder ("[name]") is skipped.
    out, start = [], True
    for token in re.split(r"(\s+)", s):
        if not token.strip():
            out.append(token)
            continue
        bare = token.strip(".,;:!?()[]\"'")
        if (not start and bare and bare[0].isupper() and bare.lower() not in _COMMON
                and not re.match(r"(?i)^i['\u2019]", bare)
                and not bare.isupper() and "[" not in token):
            out.append(token.replace(bare, "[name]"))
            n += 1
        else:
            out.append(token)
        start = token.rstrip().endswith((".", "!", "?", ":"))
    s = "".join(out)

    # The guarantee, last of all.
    s = sub(_ANY_DIGITS, "[number]", s)
    return s, n


def has_digits(text: str) -> bool:
    """True when a stripped text still has a digit in it. Used by the suite as
    the spine assertion, and cheap enough to leave in the module."""
    return any(ch.isdigit() for ch in (text or ""))


# --------------------------------------------------------------------------
#   Retrieval
# --------------------------------------------------------------------------

def _stored_exemplars(about: str) -> list:
    """The owner's OWN saved samples, most relevant first, from voiceprint.db.

    Scored by plain word overlap with `about` - no embeddings, no network - and
    read from the same `voiceprint_samples` table `add()`, `samples()` and
    `profile()` write. This is the 2026-10-20 audit's catch: exemplars() used
    to consult only the memory store and never read a single stored sample.
    Each row is (sort key, text, kind, when); strip_entities runs at return.
    """
    wanted = {w for w in re.findall(r"[a-z0-9']+", str(about or "").lower())
              if len(w) > 2}
    try:
        with closing(_connect()) as c:
            rows = [dict(r) for r in c.execute(
                "SELECT created_at, kind, text FROM voiceprint_samples"
                " ORDER BY created_at DESC LIMIT ?", (MAX_SAMPLES,)).fetchall()]
    except Exception:
        return []
    scored = []
    for order, row in enumerate(rows):
        text = str(row.get("text") or "")
        words = {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2}
        score = len(wanted & words)
        scored.append(((-score, -float(row.get("created_at") or 0.0), order),
                       text, str(row.get("kind") or KIND_SAMPLE),
                       row.get("created_at")))
    scored.sort(key=lambda item: item[0])
    return scored


def exemplars(about: str, k: Optional[int] = None,
              store: Any = None, latch: bool = True) -> list:
    """Find how the owner has written about something like this before.

    Reads the owner's stored samples from `voiceprint.db` FIRST (the row
    `add()` writes), scored by lexical overlap with `about`, and supplements
    with the memory store's own search when the private store has fewer than
    `k` matches or a store was supplied. Every text is passed through
    `strip_entities` before it is handed back, so no digit or name survives -
    the same guarantee the memory rows already had.

    `latch` trips the taint latch, so the turn that asked for a style sample
    stays on the local model - the same rule that applies to reading their
    mail, for the same reason.
    """
    if not _cfg("enabled", True):
        return []
    k = int(k if k is not None else _cfg("exemplars", 3) or 3)
    if k <= 0:
        return []
    min_words = int(_cfg("min_words", 6) or 6)
    found = []
    seen = set()
    for _sort, text, kind, when in _stored_exemplars(about):
        if len(text.split()) < min_words or text in seen:
            continue
        seen.add(text)
        found.append((text, kind, when, False))
        if len(found) >= k:
            break
    if len(found) < k:
        try:
            if store is None:
                import jarvis_memory
                store = jarvis_memory.store()
            rows = store.search(about or "", k=max(1, (k - len(found)) * 3))
        except Exception:
            rows = []
        for r in rows:
            text = str(r.get("text") or "")
            if len(text.split()) < min_words or text in seen:
                continue
            seen.add(text)
            found.append((text, str(r.get("source") or "memory"),
                          r.get("at") or r.get("ts"), True))
            if len(found) >= k:
                break

    if latch:
        # Before returning anything, not after. A latch set after the text has
        # been handed back is a latch that did not apply to the turn that used
        # it.
        try:
            import jarvis_gate
            jarvis_gate.latch_taint(why="voiceprint_exemplars")
        except Exception:
            pass

    out = []
    for text, kind, when, _from_memory in found:
        clean, n = strip_entities(text)
        out.append(Exemplar(clean, kind, when, n))
    _audit("voiceprint.exemplars", {"asked": k, "returned": len(out),
                                    "stripped": sum(e.stripped for e in out)})
    return out


def rules_block() -> str:
    """The instructions that go WITH exemplars. Never on its own.

    Returned separately so `prompt_block` can refuse to emit it when there is
    nothing under it: a heading with no examples teaches the model that this
    section is sometimes noise, and it discounts the section when there IS
    something in it.
    """
    return "\n".join([
        "Here is how the owner has written about similar things before.",
        "Match the rhythm, the sentence length and the level of formality.",
        "Names and numbers have been removed; do not copy the placeholders.",
    ])


#: A drafting request, in the owner's own words. Narrow on purpose: a chat
#: question is not a drafting turn, and injecting style there would taint every
#: conversation the moment one sample exists.
_DRAFT_REQUEST = re.compile(
    r"\b(?:draft|rewrite|compose|write (?:me |this |that |up )?(?:a |an )?(?:message|email|note|reply|letter|post)|"
    r"reply (?:to |with )|in my (?:own )?voice|write (?:it |this )?in my voice|"
    r"sound(?:s)? like me|my writing style)\b", re.I)

#: Register inference, in the order the audit names them. Defaults to general.
_REGISTER_WORDS = (
    ("work_email", ("email", "subject", "regards", "dear", "meeting", "deadline",
                    "report", "invoice", "colleague", "boss", "client")),
    ("firm_pushback", ("no", "decline", "push back", "refuse", "complain",
                       "not acceptable", "escalate", "cancel")),
    ("technical_doc", ("spec", "document", "readme", "api", "bug", "test",
                       "implementation", "technical")),
    ("casual_text", ("text", "message", "chat", "friend", "mum", "dad", "lol",
                     "thanks", "hey")),
)

#: The closed-world registers the UI and the audit name.
REGISTERS = ("general", "casual_text", "work_email", "technical_doc", "firm_pushback")


def drafting_request(text: str) -> bool:
    """True when this turn asks Jarvis to COMPOSE something, not to answer."""
    return bool(_DRAFT_REQUEST.search(str(text or "")))


def infer_register(text: str) -> str:
    """The register a drafting request is written in - a hint, never a mode."""
    low = str(text or "").lower()
    for name, words in _REGISTER_WORDS:
        if any(w in low for w in words):
            return name
    return "general"


def drafting_block(about: str, *, temporary: bool = False, external: bool = False,
                   store: Any = None) -> str:
    """The style block for ONE local drafting turn, or "" and no latch.

    Empty when the turn is Temporary, when it is an external-chatbot path, when
    the feature is off, or when there is no sample to draw on. A non-empty block
    latches the conversation local (the exemplars are the owner's private words);
    "" never latches, so an ordinary chat is not made private by an empty block.
    """
    if temporary or external:
        return ""
    if not _cfg("enabled", True):
        return ""
    try:
        if count() <= 0:
            return ""
    except Exception:
        return ""
    block = prompt_block(about, store=store, register=infer_register(about))
    if not block:
        return ""
    _latch("voiceprint_exemplars")
    return block


def _latch(why: str = "voiceprint_exemplars") -> None:
    """Latch the conversation local. One seam, so the suite can see it happen."""
    try:
        import jarvis_gate
        jarvis_gate.latch_taint(why=why)
    except Exception:
        pass


def prompt_block(about: str, k: Optional[int] = None, store: Any = None,
                 register: str = "") -> str:
    """The exemplars as a block to put in front of a draft.

    Empty when there is nothing to show, and that is on purpose - see
    `rules_block`. The early return is the FIRST statement, so no future edit
    can put a rules header above an empty list.
    """
    found = exemplars(about, k=k, store=store)
    if not found:
        return ""
    _ = register        # accepted for the call shape; exemplars have no register yet
    lines = [rules_block(), ""]
    lines += [f"- {e.text}" for e in found]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   The voiceprint itself: pure numbers, no model
# --------------------------------------------------------------------------

#: Ten things to ask the owner to write, in his own voice, so there is
#: something to measure. Each one is a register the drafts actually use; none
#: of them asks him to describe his own style, which nobody can do.
CALIBRATION_PROMPTS = (
    "A short message to a colleague asking them to do something by a date.",
    "A note to yourself about something you must not forget tomorrow.",
    "A reply turning something down, without sounding rude about it.",
    "A two-line summary of a long document for someone who is busy.",
    "A message explaining that something has gone wrong and what you will do.",
    "A message thanking someone for something specific.",
    "A message asking a company to fix a problem with an order.",
    "A plan for a day, written as if you were telling a friend about it.",
    "A description of something you saw or did, in a few sentences.",
    "An apology for being late, in your own words.",
)

_CONTRACTION = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.I)
# A sentence INCLUDING its own full stop, question mark or exclamation mark.
# The first version of this split on [.!?]+ and threw the mark away, so
# `endswith("?")` was never true and every text measured as having no
# questions at all. backend/test_voiceprint.py caught it; the mark is kept.
_SENTENCE = re.compile(r"[^.!?]*[.!?]+|[^.!?]+")


def _sentences(text: str) -> list:
    return [m.group(0).strip() for m in _SENTENCE.finditer(text or "")
            if m.group(0).strip()]


def _words(text: str) -> list:
    return [w for w in re.findall(r"[A-Za-z']+", text or "") if w]


def compute_voiceprint(texts) -> dict:
    """The numbers that ARE the voiceprint, worked out from his own writing.

    Pure standard library, no model and no network, so the answer is the same
    on every machine and can be read and argued with. Every number is a plain
    statistic over sentences and words; nothing here is a guess about meaning.

    Returns a dict of numbers (and always the same keys, so a caller can rely
    on them). An empty input gives zeroed numbers rather than an exception.
    """
    if isinstance(texts, str):
        texts = [texts]
    docs = [str(t or "") for t in (texts or []) if str(t or "").strip()]
    joined = "\n".join(docs)
    sents = _sentences(joined)
    words = _words(joined)
    per_sent = [len(_words(s)) for s in sents] or [0]
    word_lens = [len(w) for w in words] or [0]
    n_words = max(1, len(words))

    def per_100(count: int) -> float:
        return round(100.0 * count / n_words, 2)

    return {
        "documents": len(docs),
        "sentences": len(sents),
        "words": len(words),
        "mean_words_per_sentence": round(statistics.fmean(per_sent), 2),
        "median_words_per_sentence": round(float(statistics.median(per_sent)), 2),
        "longest_sentence_words": max(per_sent),
        "shortest_sentence_words": min(per_sent),
        "mean_word_length": round(statistics.fmean(word_lens), 2),
        "contractions_per_100_words": per_100(len(_CONTRACTION.findall(joined))),
        "questions_per_100_sentences": round(
            100.0 * sum(1 for s in sents if s.endswith("?")) / max(1, len(sents)), 2),
        "exclamations_per_100_sentences": round(
            100.0 * sum(1 for s in sents if s.endswith("!")) / max(1, len(sents)), 2),
        "commas_per_100_words": per_100(joined.count(",")),
        "semicolons_per_100_words": per_100(joined.count(";")),
        "dashes_per_100_words": per_100(joined.count(" - ") + joined.count(" -- ")),
        "list_markers_per_100_words": per_100(
            len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s", joined))),
        "short_words_pct": round(
            100.0 * sum(1 for w in words if len(w) <= 4) / n_words, 2),
        "one_sentence_documents_pct": round(
            100.0 * sum(1 for d in docs if len(_sentences(d)) == 1) / max(1, len(docs)), 2),
    }


#: How far a measure may sit from the voiceprint before it is called "off".
#: Chosen to be generous: this is a nudge for a draft, not a grade.
_TOLERANCE = {
    "mean_words_per_sentence": 6.0,
    "mean_word_length": 0.5,
    "contractions_per_100_words": 2.5,
    "commas_per_100_words": 2.5,
    "short_words_pct": 12.0,
}


#: Tokens only the stripping step may produce. If one reaches a draft the model
#: copied a placeholder the owner's real words never contained.
_PLACEHOLDER_RX = re.compile(
    r"\[(?:name|number|amount|date|link|email|path|handle|postcode|time)\]", re.I)


def leaked_placeholders(text: str) -> list:
    """The placeholder tokens in a draft, lowercased and unique. Never guesses."""
    return sorted({m.group(0).lower() for m in _PLACEHOLDER_RX.finditer(str(text or ""))})


def score_style_compliance(text: str, profile: Optional[dict] = None) -> dict:
    """How closely `text` reads like the voiceprint. 0 (nothing alike) to 1.

    Only the measures with a stated tolerance count, so the score is not
    diluted by the many numbers that describe length rather than voice. Returns
    the score, the measures that are close, and the measures that are off with
    both numbers, so a caller can say WHAT is off rather than only that
    something is.
    """
    profile = dict(profile or {})
    leaked = leaked_placeholders(text)
    if not profile:
        return {"score": None, "close": [], "off": [],
                "leaked_placeholder": bool(leaked), "leaked": leaked,
                "note": "no voiceprint yet - write a few samples first"}
    mine = compute_voiceprint(text)
    close, off = [], []
    for key, tol in _TOLERANCE.items():
        want = profile.get(key)
        got = mine.get(key)
        if want is None or got is None:
            continue
        if abs(float(got) - float(want)) <= tol:
            close.append(key)
        else:
            off.append({"measure": key, "voiceprint": want, "this_text": got})
    total = len(close) + len(off)
    out = {"score": round(len(close) / total, 3) if total else None,
           "close": close, "off": off, "measured": mine,
           "leaked_placeholder": bool(leaked), "leaked": leaked}
    if leaked:
        # A draft that says "Hi [name]" is broken whatever else it reads like.
        out["score"] = 0.0
        out["off"] = off + [{"measure": "leaked_placeholder", "leaked": leaked}]
    return out


# --------------------------------------------------------------------------
#   Where the store lives
# --------------------------------------------------------------------------

#: The settings folder, and its own file. `JARVIS_VOICEPRINT_DB` overrides the
#: file (the tests use a scratch one; the same shape as JARVIS_RECEIPTS_DB).
DB_ENV = "JARVIS_VOICEPRINT_DB"
DB_NAME = "voiceprint.db"

#: A sample may be this long. Longer is REFUSED rather than truncated: half a
#: sentence is a false example of how he writes, and a store is not the place
#: to keep a document by accident.
MAX_TEXT = 4000
MAX_SAMPLES = 500
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

#: The ways a sample can arrive. Named so the list can say which is which.
KIND_CALIBRATION = "calibration"
KIND_EDIT = "edit"
KIND_SAMPLE = "sample"
KINDS = (KIND_CALIBRATION, KIND_EDIT, KIND_SAMPLE)

LIST_PATH = "/api/voiceprint"
SAMPLE_PATH = "/api/voiceprint/sample"
EDIT_PATH = "/api/voiceprint/learn_edit"
FORGET_PATH = "/api/voiceprint/forget"
PATHS = (LIST_PATH,)

WORDS = {
    "no_confirm": ("Forgetting cannot be undone, so it asks first. Send "
                   "\"confirm\": true to mean yes."),
    "unknown": "no sample with that id",
    "no_scrubber": ("The scrubber is not available, so nothing was written. "
                    "Jarvis would rather keep no sample than keep one it could "
                    "not check for passwords and keys."),
    "forgotten": "That sample is gone. It cannot be brought back.",
    "too_long": f"A sample may be at most {MAX_TEXT} characters.",
    "empty": "There was nothing to learn from that.",
    "secret": ("That looks like it has a password, key or one-time code in it, "
               "so nothing was written. Write the sentence without it and try "
               "again."),
    "no_voiceprint": "No samples yet, so there is no voiceprint to measure against.",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS voiceprint_samples (
    id          TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    kind        TEXT NOT NULL,
    prompt      TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL,
    numbers     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_voiceprint_created
    ON voiceprint_samples (created_at DESC);
"""


def _config_dir() -> Path:
    """The owner's settings folder. The same four places jarvis_framework
    looks, so the store sits beside `goals.db` and `schedule.db`."""
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def db_path() -> Path:
    env = os.environ.get(DB_ENV)
    return Path(env) if env else _config_dir() / DB_NAME


def _connect() -> sqlite3.Connection:
    """Always `with closing(_connect()) as c:` - never `with _connect() as c:`.

    `with sqlite3.connect(...)` commits, it does not close, and on Windows the
    unclosed handles hold locks on the -wal file. Copied from
    jarvis_receipts.py:264-281, whose docstring records what that cost there.
    """
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # WAL so a read (the apps' list) never blocks a write (a sample), and the
    # busy timeout so two writes finishing together wait rather than fail.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(SCHEMA)
    return conn


# --------------------------------------------------------------------------
#   Never write a secret
# --------------------------------------------------------------------------


def _scrubber():
    """jarvis_scrub, or None. Fails CLOSED: no scrubber, nothing recorded.

    Copied from jarvis_receipts.py:289-295, on purpose and word for word.
    """
    try:
        import jarvis_scrub
        return jarvis_scrub
    except Exception:
        return None


def _secret_in(text: str) -> bool:
    """True when the text holds something that looks like a key or a password.

    `jarvis_scrub.find_secret` is the project's own reader for this, and it
    already knows the token file, the known values and the shapes. A sample of
    the owner's prose has no business carrying one, and a store is a bad place
    to discover it later.
    """
    try:
        import jarvis_scrub
        return bool(jarvis_scrub.find_secret(text))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Writing
# --------------------------------------------------------------------------


#: Chat-control markers no sample may carry into the store or a later prompt.
_CONTROL_MARKERS = re.compile(
    r"<\|(?:im_start|im_end|endoftext)\|>|</?tool_call>|</?think>", re.I)


def strip_control_markers(text: str) -> str:
    """SecAlign: control markers removed before a sample is stored. Pure."""
    return _CONTROL_MARKERS.sub("", str(text or ""))


def _new_id() -> str:
    # uuid4, like every other id in this backend, so a fixture built by driving
    # the real module is reproducible.
    return "vp" + uuid.uuid4().hex[:12]


def add(kind: str, text: str, *, prompt: str = "") -> str:
    """Learn one piece of the owner's own writing. Returns its id, "" if not.

    Never raises, never writes an unscrubbed word, and never writes anything at
    all without the project's scrubber. The text is scrubbed BEFORE it is
    stored, so nothing unscrubbed is ever on disk to be listed later.
    """
    try:
        if kind not in KINDS:
            kind = KIND_SAMPLE
        raw = strip_control_markers(str(text or "")).strip()
        if not raw:
            _audit("voiceprint.withheld", {"kind": kind, "why": "empty"})
            return ""
        if len(raw) > MAX_TEXT:
            _audit("voiceprint.withheld", {"kind": kind, "why": "too long"})
            return ""
        if _secret_in(raw):
            # The ROUTE checks this too, but a direct Python caller must not be
            # able to store a password the scrubber would only partly redact
            # (2026-10-20 audit, Part I catch 2B).
            _audit("voiceprint.withheld", {"kind": kind, "why": "secret"})
            return ""
        scrub = _scrubber()
        if scrub is None:
            # The same rule chat history uses ("no key, nothing is recorded"),
            # applied to words rather than to a database: better no sample than
            # one holding a key it could not check.
            _audit("voiceprint.withheld", {"kind": kind, "why": "no scrubber"})
            return ""
        clean = scrub.scrub_text(raw)
        if not str(clean or "").strip():
            _audit("voiceprint.withheld", {"kind": kind, "why": "scrubbed away"})
            return ""
        sample_id = _new_id()
        numbers = json.dumps(compute_voiceprint(clean))
        with closing(_connect()) as c:
            c.execute(
                "INSERT INTO voiceprint_samples (id, created_at, kind, prompt, text, numbers)"
                " VALUES (?,?,?,?,?,?)",
                (sample_id, time.time(), kind, str(prompt or "")[:MAX_TEXT],
                 clean[:MAX_TEXT], numbers))
            # Keep the store bounded: the oldest go first, and the list still
            # says how many there were.
            c.execute(
                "DELETE FROM voiceprint_samples WHERE id NOT IN"
                " (SELECT id FROM voiceprint_samples ORDER BY created_at DESC LIMIT ?)",
                (MAX_SAMPLES,))
        _audit("voiceprint.learned", {"kind": kind, "chars": len(clean)})
        return sample_id
    except Exception as exc:
        # A sample that cannot be written must never fail the thing it was
        # recording. Named, never quoted.
        _audit("voiceprint.write_failed", {"kind": str(kind), "error": type(exc).__name__})
        return ""


def add_owner_edit(before: str, after: str, *, prompt: str = "") -> str:
    """Learn from the owner changing a draft: HIS final words are the sample.

    The draft itself is kept only as a length, never as text - what teaches the
    style is the version he chose, not the one Jarvis proposed. An edit that
    changed nothing is not a sample.
    """
    if str(before or "").strip() == str(after or "").strip():
        return ""
    sample_id = add(KIND_EDIT, after, prompt=prompt)
    if sample_id:
        _audit("voiceprint.edit_learned", {"before_chars": len(str(before or "")),
                                          "after_chars": len(str(after or ""))})
    return sample_id


# --------------------------------------------------------------------------
#   Reading
# --------------------------------------------------------------------------

def samples(limit: int = DEFAULT_LIMIT) -> list:
    """The most recent samples, newest first. A read; nothing is written."""
    try:
        limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        with closing(_connect()) as c:
            rows = c.execute(
                "SELECT id, created_at, kind, prompt, text FROM voiceprint_samples"
                " ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    except Exception:
        return []
    return [{"id": r["id"], "created_at": r["created_at"], "kind": r["kind"],
             "prompt": r["prompt"], "text": r["text"]} for r in rows]


def count() -> int:
    try:
        with closing(_connect()) as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM voiceprint_samples").fetchone()["n"])
    except Exception:
        return 0


def profile(k: Optional[int] = None) -> dict:
    """The voiceprint: the numbers, worked out from every sample there is.

    Empty when there are no samples, so a caller can say "nothing to measure
    against yet" rather than printing zeros as though they meant something.
    """
    rows = samples(limit=MAX_LIMIT)
    if not rows:
        return {}
    return compute_voiceprint([r["text"] for r in rows])


def forget(sample_id: str, confirm: bool = False) -> dict:
    """Delete one sample. Refuses without `confirm`.

    The owner kept the question (2026-09-24: forgetting "asks 'are you sure?'
    first ... because forgetting cannot be undone"), so this is where the
    question is enforced - in the one place a client cannot skip.
    """
    sample_id = str(sample_id or "").strip()
    if not confirm:
        return {"ok": False, "needs": "confirm", "error": "not_confirmed",
                "message": WORDS["no_confirm"]}
    if not sample_id:
        return {"ok": False, "error": "unknown", "message": WORDS["unknown"]}
    try:
        with closing(_connect()) as c:
            cur = c.execute("DELETE FROM voiceprint_samples WHERE id = ?", (sample_id,))
            gone = cur.rowcount
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__,
                "message": "the store could not be opened, so nothing was forgotten"}
    if not gone:
        return {"ok": False, "error": "unknown", "message": WORDS["unknown"]}
    _audit("voiceprint.forgotten", {"id": sample_id})
    return {"ok": True, "forgotten": sample_id, "message": WORDS["forgotten"]}


# --------------------------------------------------------------------------
#   Routes
# --------------------------------------------------------------------------


def _status() -> dict:
    """What the engine is doing, in words a client can print."""
    n = count()
    return {
        "available": True,
        "enabled": bool(_cfg("enabled", True)),
        "samples": n,
        "scrubber": _scrubber() is not None,
        "store": str(db_path()),
        "note": ("Retrieved at generation time through the memory store, so it "
                 "taints the turn local. No weights are changed and nothing is "
                 "learned in the background."),
        "calibration_prompts": list(CALIBRATION_PROMPTS),
    }


def handle_get(route: str, query: str = "") -> tuple:
    """GET /api/voiceprint -> (200, {...}). A read; nothing is written."""
    if route == LIST_PATH:
        rows = samples()
        prof = profile()
        out = {"ok": True, "samples": rows, "count": len(rows),
               "voiceprint": prof, "status": _status()}
        if not prof:
            out["message"] = WORDS["no_voiceprint"]
        return 200, out
    return 404, {"ok": False, "error": "not_found"}


def handle_post(route: str, body: Optional[dict]) -> tuple:
    """The three mutating routes -> (status, {...}).

    A body that is not an object is refused rather than guessed at, and a
    denied forget changes nothing.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "bad_body",
                     "message": "the request body must be a JSON object"}
    if route == SAMPLE_PATH:
        text = str(body.get("text") or "")
        if not text.strip():
            return 400, {"ok": False, "error": "empty", "message": WORDS["empty"]}
        if len(text) > MAX_TEXT:
            return 400, {"ok": False, "error": "too_long", "message": WORDS["too_long"]}
        if _secret_in(text):
            return 400, {"ok": False, "error": "secret", "message": WORDS["secret"]}
        if _scrubber() is None:
            return 503, {"ok": False, "error": "no_scrubber", "message": WORDS["no_scrubber"]}
        sample_id = add(KIND_SAMPLE, text, prompt=str(body.get("prompt") or ""))
        if not sample_id:
            return 503, {"ok": False, "error": "not_written", "message": WORDS["no_scrubber"]}
        return 200, {"ok": True, "id": sample_id, "count": count()}
    if route == EDIT_PATH:
        before, after = str(body.get("before") or ""), str(body.get("after") or "")
        if not after.strip() or before.strip() == after.strip():
            return 200, {"ok": True, "id": "", "learned": False,
                         "message": "nothing changed, so there was nothing to learn"}
        if _secret_in(after):
            return 400, {"ok": False, "error": "secret", "message": WORDS["secret"]}
        if _scrubber() is None:
            return 503, {"ok": False, "error": "no_scrubber", "message": WORDS["no_scrubber"]}
        sample_id = add_owner_edit(before, after, prompt=str(body.get("prompt") or ""))
        return 200, {"ok": True, "id": sample_id, "learned": bool(sample_id)}
    if route == ENABLED_PATH:
        # The ruling's field name is "enabled"; "on" stays as an alias so a
        # client written against the earlier draft keeps working.
        value = body["enabled"] if "enabled" in body else body.get("on")
        return 200, set_enabled(value)
    if route == FORGET_PATH:
        return 200, forget(str(body.get("id") or ""), bool(body.get("confirm")))
    return 404, {"ok": False, "error": "not_found"}


NOT_THIS_PC = ("Adding or forgetting your own writing samples is for this PC "
               "only, so nothing was changed.")


def _peer_local(handler) -> tuple:
    """(peer, local) for one request, best effort; a missing pair fails closed."""
    peer = local = None
    try:
        peer = handler.client_address[0]
    except Exception:
        pass
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        pass
    return peer, local


def _from_this_pc(peer, local) -> bool:
    """Is this request from this PC? Fails CLOSED.

    2026-10-20 audit, Part I catch 2C: a phone on the same private network
    could add or forget the owner's writing samples with its bearer token.
    `jarvis_owner_check` is the project's one answer; when it is not beside
    this module, loopback (and ONLY loopback) is still accepted, so a suite or
    a checkout without the helper keeps working while a remote peer does not.
    """
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        if peer is None:
            return False
        try:
            host = str(peer).strip("[]").lower()
        except Exception:
            return False
        return host in ("127.0.0.1", "::1", "localhost")


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the four routes above are
    answered here, after the server's own origin and token checks.

    Every other request goes straight to the original, untouched - the same
    shape `jarvis_receipts.install()` uses (its :858-915), and the reason this
    feature needs no patch: `plugins/ready/voiceprint/plugin.json` names this
    module and `jarvis_plugins.py` makes the call the patch would have made.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_voiceprint", False):
        return "  voiceprint Write Like Me (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        from urllib.parse import urlsplit
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        from urllib.parse import urlsplit
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in (SAMPLE_PATH, EDIT_PATH, FORGET_PATH, ENABLED_PATH):
            return post0(self)
        if not _allowed(self):
            return None
        # 2026-10-20 audit, Part I catch 2C: adding, learning an edit or
        # forgetting the owner's OWN WRITING SAMPLES is for this PC only, so
        # another device is refused BEFORE the body is read. Reads (GET) stay a
        # token-guarded read, as before.
        #
        # The local ON/OFF switch is EXEMPT on the owner's decision of
        # 2026-10-20: it carries none of the owner's words, it is an ordinary
        # client setting like "How Jarvis talks" (which the paired phone may
        # also change), and the phone plate's switch has to keep working -
        # turning it off is instant, and neither direction raises a card.
        if route != ENABLED_PATH:
            peer, local = _peer_local(self)
            if not _from_this_pc(peer, local):
                return self._send(403, {"ok": False, "error": "not_this_pc",
                                        "message": NOT_THIS_PC})
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_voiceprint = True
    do_POST._jarvis_voiceprint = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  voiceprint Write Like Me: on"


def status() -> dict:
    """What the engine is doing. The shape the apps read."""
    return {"available": True, "enabled": bool(_cfg("enabled", True)), "samples": count(),
            "scrubber": _scrubber() is not None,
            "exemplars": int(_cfg("exemplars", 3) or 3),
            "note": ("Retrieved at generation time through the memory store, so "
                     "it taints the turn local. No weights are changed and "
                     "nothing is learned in the background.")}


# --------------------------------------------------------------------------
#   For the suites
# --------------------------------------------------------------------------


def _reset_for_tests() -> None:
    """Forget nothing on disk: only the module-level caches a RESTART would
    clear. There are none today, and this exists so a suite can call it
    unconditionally, the way the other modules' suites do."""
    return None
