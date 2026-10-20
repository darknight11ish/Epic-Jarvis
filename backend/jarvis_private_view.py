"""jarvis_private_view.py - the one read-only App lock / hidden-lists hook for server reads.

Q1 ruling (Gemini final audit, 2026-10-20, Section 13.8), Option (a): approve a
SINGLE read-only live-state hook, and keep the apps' own hiding as
belt-and-braces. The exact rules this module implements:

1. **A request can only add withholding, never remove it.** `effective()` ORs
   every source it is given (the trusted live state, the caller's two flags,
   and a supplied state mapping). `app_locked=False` on a request is not an
   unlock key; it means "this caller is not adding a reason to hide". Only
   `note_state()`, the trusted in-process hook, can clear a lock.
2. **The hook is absent -> unlocked.** The first time any of these routes runs
   in a standalone checkout/test there is no desktop state to read, so
   `state()` starts False. Behaviour is then exactly what it was before this
   module existed, and an older backend cannot lock itself out.
3. **The live HUD must eventually pass the state.** The desktop shell knows App
   lock and "Hide memory lists and chat history"; this backend process does
   not, yet. Until the live wiring lands, the routes accept
   `?app_locked=1` / `?hide_memory_lists=1` from the desktop (they can only
   withhold) and the apps keep hiding in their own drawers. ARCHITECTURE.md
   carries that note; JARVIS-API's three route sections say what a locked
   answer looks like.

NOT IN THIS MODULE, DELIBERATELY: Q2's `traces.db` retention cap. That database
is written only by the live HUD and has no shipped module here, so the F10 work
is **BLOCKED / live-only** for this wave. Nothing in this file invents a writer,
opens a database, or stores anything.
"""
from __future__ import annotations

import threading

#: The same two sentences the rest of the backend already uses for a withheld
#: private view (jarvis_people_crm's own WITHHELD_* constants - the tests pin
#: that they are byte-identical, so the apps show one wording, not three).
WITHHELD_LOCKED = "Hidden while App lock is on."
WITHHELD_HIDDEN = 'Hidden while "Hide memory lists and chat history" is on.'

#: The only spellings a query parameter may use to mean "yes". Anything else -
#: including "0", "false", "no" and a missing key - is False. Because the
#: values are ORed by effective(), that is a refusal to add a reason, never an
#: instruction to unlock.
_TRUE_WORDS = ("1", "true", "yes", "on")

_STATE = {"app_locked": False, "hide_memory_lists": False}
_STATE_LOCK = threading.Lock()


def flag(value) -> bool:
    """True only for the documented "yes" spellings; everything else False.

    Strings are matched case-insensitively after trimming, so `"1"`, `"true"`,
    `"Yes"` and `"ON"` count, and `"0"`, `"false"`, an empty string and `None`
    do not. A value that cannot even be stringified is False: a caller cannot
    make this raise, and cannot use it to unlock something."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    try:
        return str(value).strip().lower() in _TRUE_WORDS
    except Exception:
        return False


def note_state(*, app_locked=None, hide_memory_lists=None) -> dict:
    """The TRUSTED hook: the live HUD/desktop shell reports the real state here.

    A value of None leaves that half unchanged; True/False sets it exactly, so
    this is the ONE place a lock can be cleared. No HTTP handler calls it: a
    request carrying `app_locked=0` goes through `effective()`, which cannot
    clear anything. Returns the state after the change, so the caller can log
    what it set (this module logs nothing itself).
    """
    with _STATE_LOCK:
        if app_locked is not None:
            _STATE["app_locked"] = bool(app_locked)
        if hide_memory_lists is not None:
            _STATE["hide_memory_lists"] = bool(hide_memory_lists)
        return dict(_STATE)


def state() -> dict:
    """The trusted state as it stands: `{"app_locked", "hide_memory_lists"}`."""
    with _STATE_LOCK:
        return dict(_STATE)


def effective(*, app_locked=None, hide_memory_lists=None, lock_state=None) -> dict:
    """The merged answer every route uses: what to withhold, and its sentence.

    Sources, ORed together (never subtracted):
    * the trusted `state()` (False until `note_state()` is called, so an
      absent hook means unlocked);
    * `lock_state`, when a caller already has the state: a mapping may carry
      either key; any other truthy value locks both halves (the fail-safe
      reading of "the caller says the app is locked");
    * the two request flags - the only part a query string can reach.

    Returns `{"app_locked", "hide_memory_lists", "locked", "why"}`. `why` is ""
    when nothing is withheld, and the App-lock sentence wins over the hidden
    lists sentence when both are on - the same order jarvis_people_crm and the
    apps use.
    """
    trusted = state()
    want_app = flag(trusted.get("app_locked"))
    want_hide = flag(trusted.get("hide_memory_lists"))

    if isinstance(lock_state, dict):
        want_app = want_app or flag(lock_state.get("app_locked"))
        want_hide = want_hide or flag(lock_state.get("hide_memory_lists"))
    elif lock_state:
        want_app = True

    want_app = want_app or flag(app_locked)
    want_hide = want_hide or flag(hide_memory_lists)

    if want_app:
        why = WITHHELD_LOCKED
    elif want_hide:
        why = WITHHELD_HIDDEN
    else:
        why = ""
    return {"app_locked": want_app, "hide_memory_lists": want_hide,
            "locked": want_app or want_hide, "why": why}


def withhold(kind) -> str:
    """The honest marker for a withheld view of one kind.

    `"app_locked"` / `"locked"` / `"lock"` answer the App-lock sentence; every
    other kind (including "hidden", the default a caller gets for a missing
    argument) answers the hidden-lists sentence. This is a pure lookup: it
    never decides whether anything IS locked (effective() does that)."""
    try:
        cleaned = str(kind or "").strip().lower()
    except Exception:
        cleaned = ""
    return WITHHELD_LOCKED if cleaned in ("app_locked", "locked", "lock") else WITHHELD_HIDDEN


def withheld_words(*, app_locked=None, hide_memory_lists=None, lock_state=None) -> str:
    """The sentence for this request, or "" when nothing is withheld."""
    return effective(app_locked=app_locked, hide_memory_lists=hide_memory_lists,
                     lock_state=lock_state)["why"]


def _reset_for_tests() -> dict:
    """Back to the absent-hook state: unlocked in-process. Never called by a route."""
    return note_state(app_locked=False, hide_memory_lists=False)
