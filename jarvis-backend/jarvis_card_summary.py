"""jarvis_card_summary.py - how much of an approval card is shown at first,
and the setting that decides it, kept where BOTH apps can read it.

THE OWNER'S REQUEST (their own words, 2026-10-09): "for approval cards, there
should be a more simple summary, with an explain more button that expands the
approval card total word length and explains the details more. and approval
card preferences such as this should be changeable in the settings"

WHAT A CARD SHOWS, AND WHERE THOSE WORDS COME FROM

    collapsed   the SHORT summary, from `jarvis_card_words.summary_for` -
                "Jarvis wants to restore from a backup."
    expanded    the card's whole existing text, which is `notice["full"]` on
                the row (`approval-notice.patch`): the exact line or value
                being changed, why it matters, whether Windows Hello is asked
                for, and what saying no does.

Nothing here writes a word the owner reads: the summary is `jarvis_card_words`'
and the full text is the card's own. This module owns only the PREFERENCE, so
the phone and the desktop cannot drift apart on it - the same shape as
`jarvis_animal.py`'s shared switches, which both apps read from one file on the
PC.

WHY A FILE OF ITS OWN, BESIDE appearance.json AND animal.json. This is a
preference about how Jarvis talks to the owner, not about the animal's face, so
it must not be saved inside `animal.json` where the next change to that feature
could carry it away. It lives in the Jarvis settings folder beside them, is
written by `_save` the same way (a temporary file, then `os.replace`, so a
machine that dies mid-write leaves the old value rather than half a file), and
is read by both apps over one route.

COSMETIC, SO NO CARD - EITHER WAY (CLAUDE.md's standing rule: "cosmetic options
change at once"). Changing this changes which words are drawn on a card. It
approves nothing, runs nothing, reads nothing and reaches nothing, so turning
it on and turning it off are both instant, from either app or by asking Jarvis.
It is never decided by the AI model and it never changes a decision the owner
makes - the same card, the same buttons, the same words underneath.

NO SILENT FALLBACK (CLAUDE.md). A missing file, a damaged file, an unknown
value or a value of the wrong type is the DEFAULT ("start short"), said in
words by `view()["stored"]` so a screen can tell "you chose this" from "nothing
was saved" - never a guess at what the owner meant.

    python3 test_card_short_words.py
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

#: The one route both apps call: GET for the setting and its words, POST to
#: change it. Wrapped round the HUD's own Handler by `card-prefs.patch`, the
#: same way animal.patch wraps /api/animal.
PATH = "/api/card-prefs"

#: The two choices. `start_short` is the default the owner asked for; the
#: other shows everything at once, which is what a card did before this.
START_SHORT = "start_short"
ALWAYS_FULL = "always_full"
MODES = (START_SHORT, ALWAYS_FULL)
DEFAULT = START_SHORT

TITLE = "Approval cards"
LEAD = ("Cards that ask for your OK. This only changes how much of a card is shown at first - "
        "the same card, the same words underneath, the same buttons.")

#: What each choice is called, and what it does, in the owner's own terms.
#: Both apps show these words (GET /api/card-prefs hands them over), so there
#: is one wording rather than two that can drift.
CHOICES = (
    {
        "id": START_SHORT,
        "label": "Start short (default)",
        "detail": ("A card shows one line saying what Jarvis wants to do, and an \"Explain more\" "
                   "button opens the whole card: exactly what changes, why it matters, and what "
                   "happens if you say no. Nothing is hidden from you - it is one tap away."),
        "default": True,
    },
    {
        "id": ALWAYS_FULL,
        "label": "Always show everything",
        "detail": ("Every card is drawn open, with its whole text, as cards were before. No "
                   "\"Explain more\" button is needed because there is nothing folded away."),
        "default": False,
    },
)

#: The control's own words, from the one place that names them.
MORE_LABEL = "Explain more"
LESS_LABEL = "Show less"

#: What both apps say when an answer's shape is not one this module knows.
MISSING = ("Your PC's Jarvis cannot keep this card setting yet - run apply-patches.ps1 on "
           "the PC.")

_LOCK = threading.RLock()


def _config_dir() -> Path:
    """The Jarvis settings folder - the same one appearance.json, animal.json,
    sky.json and every other shared switch is written to."""
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "card-prefs.json"


def card_mode() -> str:
    """The stored display mode, or the default.

    Anything that is not one of `MODES` - a missing file, a damaged one, a
    number, a list, a name from a newer version - is the default, and
    `view()["stored"]` says so rather than pretending a choice was made.
    """
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT
    if not isinstance(doc, dict):
        return DEFAULT
    value = doc.get("mode")
    return value if value in MODES else DEFAULT


def _stored() -> bool:
    """Whether a real choice is saved (never whether the file exists)."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(doc, dict) and doc.get("mode") in MODES


def set_mode(mode: str) -> tuple:
    """Save one of the two choices. Returns (http code, body).

    Cosmetic either way, so there is no card and no direction that asks: this
    is the function POST /api/card-prefs and the spoken "always show the whole
    card" both call. An unknown mode is refused (400) rather than quietly
    saved as something else - a screen that offered a third choice would be a
    bug, and a silent default would hide it.
    """
    mode = str(mode or "").strip()
    if mode not in MODES:
        return 400, {"ok": False, "error": f"{mode!r} is not one of {', '.join(MODES)}."}
    before = card_mode()
    if before == mode:
        return 200, {"ok": True, "changed": False, "said": f"Already set: {label_of(mode)}.",
                     "view": view()}
    try:
        _write(mode)
    except Exception as exc:
        return 500, {"ok": False, "error": f"could not save ({type(exc).__name__})"}
    return 200, {"ok": True, "changed": True,
                 "said": ("Done - every card starts short, and \"Explain more\" opens the whole "
                          "one." if mode == START_SHORT else
                          "Done - every card is shown open, with its whole text."),
                 "view": view()}


def _write(mode: str) -> None:
    with _LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"mode": mode, "changed": time.time()}, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)


def label_of(mode: str) -> str:
    """The chosen choice's own label, or the default's when the mode is
    unknown - never an empty line on a screen."""
    for c in CHOICES:
        if c["id"] == mode:
            return str(c["label"])
    return str(CHOICES[0]["label"])


def view() -> dict:
    """GET /api/card-prefs: the setting, its choices and the words both apps
    show. `stored` is False when nothing is saved or the file cannot be read,
    so a screen can say "default" rather than claiming the owner chose it."""
    mode = card_mode()
    return {
        "available": True,
        "title": TITLE,
        "lead": LEAD,
        "mode": mode,
        "default": DEFAULT,
        "stored": _stored(),
        "choices": [dict(c) for c in CHOICES],
        "more_label": MORE_LABEL,
        "less_label": LESS_LABEL,
        "missing": MISSING,
    }


def handle_get() -> tuple:
    return 200, view()


def handle_post(body) -> tuple:
    """POST /api/card-prefs with {"mode": "start_short"|"always_full"}."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send {\"mode\": ...}."}
    mode = body.get("mode")
    if mode is None:
        return 400, {"ok": False, "error": "Send {\"mode\": ...}."}
    return set_mode(mode)


#: Words that carry no meaning here and are dropped before a spoken phrase is
#: read: the polite ones, the verb of asking, and the filler people put round a
#: noun. "show me the whole approval card again please" and "the whole card"
#: are the same request, and both have to name it.
#:
#: EVERY word here is one that changes nothing about which mode is meant. A
#: word that could carry meaning is deliberately NOT here, so that a sentence
#: this function does not understand answers None rather than falling back to
#: an empty list: "everything about the second card" keeps "about" and "second",
#: and is refused (see `spoken`).
_SPOKEN_NOISE = frozenset((
    "always", "just", "please", "now", "again", "me", "my", "the", "a", "an", "it",
    "show", "showing", "display", "give", "make", "set", "switch", "change", "keep",
    "use", "start", "starting", "with", "to", "on", "of", "for", "every", "each",
    "cards", "card", "approval", "approvals", "and",
))

#: The words a person actually uses for each mode. Deliberately disjoint, and
#: deliberately SHORT: only words that cannot mean anything else in this
#: grammar. "Brief" is NOT here, and neither is a bare "short", "summary",
#: "everything" or "all" - those are ordinary words this feature has no right
#: to, and the first version of this function took "the brief" (the morning
#: brief) and "show everything" (unhide every menu) away from the phrases that
#: already owned them. `backend/test_attention_phrases.py` and
#: `test_card_short_words.py` are the two checks that caught it.
_SPOKEN_FULL = frozenset(("everything", "whole", "full", "complete", "entire", "thing"))
_SPOKEN_SHORT = frozenset(("short", "summary", "compact", "glanceable", "first",
                           "version", "one"))

#: What may be LEFT after the noise comes out, for each mode - the forms a
#: person really says, and the only ones accepted. A closed list on purpose: a
#: bag of words ("the sentence contains `everything`, so show everything")
#: would answer "everything about the second card" with a change to every card
#: on the screen, and the whole point of this function is that a sentence it
#: does not recognise is None and the caller says so.
_SPOKEN_FORMS = {
    ALWAYS_FULL: (
        # "show the whole card" and "the whole card" both land here: "card" and
        # "approval" are noise, so what is left is the bare adjective, and the
        # adjective is the whole message.
        ("whole",), ("full",), ("everything",), ("everything", "it"),
        ("whole", "thing"), ("whole", "card"), ("full", "card"),
        ("complete", "card"), ("entire", "card"),
    ),
    START_SHORT: (
        ("short",), ("short", "version"), ("short", "summary"), ("short", "one"),
        ("summary",), ("summary", "first"), ("summary", "only"), ("compact",),
        ("short", "summary", "first"),
    ),
}


def spoken(words: str) -> Optional[str]:
    """The mode a spoken phrase names, or None - never a guess.

    "always show everything", "show me the whole approval card", "start short",
    "the short summary" - the whole sentence as the owner says it, not a
    canonical form they would have to know. Used by
    `jarvis_settings_registry.set_card_mode`, which jarvis_quick.py's grammar
    calls for "always show me the whole approval card", and which the app's own
    switch reaches through POST /api/card-prefs - one function, so asking and
    tapping cannot take two different paths.

    HOW IT READS, in three steps and no more:
      1. the noise words come out (`_SPOKEN_NOISE`: the polite lead-in, the
         verb of asking, "the"/"my", "approval", "card");
      2. every word left has to belong to ONE of the two modes' own short
         vocabulary (`_SPOKEN_FULL` / `_SPOKEN_SHORT`) - a sentence carrying
         words from both, or a word from neither, answers None;
      3. what is left has to BE one of that mode's written forms
         (`_SPOKEN_FORMS`), not merely contain one.
    Step 2 is what stops "everything about the second card" from silently
    changing every card on the screen; step 3 is what stops a bare word from
    being read as an instruction. `spoken("")` is None.
    """
    tokens = [w.strip(".,!?;:'\"") for w in str(words or "").lower().split()]
    meaning = [w for w in tokens if w and w not in _SPOKEN_NOISE]
    if not meaning:
        return None
    full = all(w in _SPOKEN_FULL for w in meaning)
    short = all(w in _SPOKEN_SHORT for w in meaning)
    if full == short:            # neither vocabulary, or one word from each
        return None
    mode = ALWAYS_FULL if full else START_SHORT
    return mode if tuple(meaning) in _SPOKEN_FORMS[mode] else None


def decide(notice: dict, mode: str = None, action: str = "") -> dict:
    """What one card shows, given the row's own `notice` and the preference.

    Returns {"summary", "full", "expanded", "control"}:

        summary   the short line (the notice's own `summary`, or - for a row
                  from an older backend that sent none - `jarvis_card_words`
                  building one from the action: never blank)
        full      the whole card, which is what "Explain more" reveals
        expanded  whether it starts open (the preference, and nothing else)
        control   whether an "Explain more" control is needed at all - False
                  under "always show everything" (nothing is folded away), and
                  False when the full text IS the summary (opening it would
                  show nothing more)

    BOTH APPS READ THIS ONE FUNCTION'S RULE, so "start short" cannot mean two
    things. The pure-Python half is here; the phone's copy is
    `net/CardSummary.kt`, and `tools/gen_card_summary_cases.py` writes the
    fixture that holds the two together.
    """
    import jarvis_card_words as W

    notice = notice if isinstance(notice, dict) else {}
    action = str(action or notice.get("action") or "").strip()
    full = str(notice.get("full") or notice.get("body") or "").strip()
    summary = str(notice.get("summary") or "").strip() or W.summary_for(action, full)
    mode = mode if mode in MODES else card_mode()
    # Under "always show everything" there is nothing folded away, so there is
    # no control to draw; folded, one is needed only when opening the card
    # would actually show more than the summary already does.
    return {
        "summary": summary,
        "full": full,
        "expanded": mode == ALWAYS_FULL,
        "control": mode != ALWAYS_FULL and bool(full) and full.strip() != summary.strip(),
    }


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so /api/card-prefs is answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original - the same shape jarvis_animal.install uses."""
    from urllib.parse import urlsplit

    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_card_summary", False):
        return "  cards      Approval cards (already on)"

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
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_card_summary = True
    do_POST._jarvis_card_summary = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return f"  cards      Approval cards: {label_of(card_mode())}"
