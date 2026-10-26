"""jarvis_private_chat.py - the fail-closed read-only gate for a private chat.

THE RULING. Gemini, principal architect, 2026-10-25 (H10, design (A)): a
PRIVATE chat - `"private": true` on POST /api/chat - is strictly reads-only.
It recalls no memory and learns nothing (that is the temporary chat this flag
implies), and it writes NOTHING to disk: not the chat history, not a learned
fact, not the feedback row, not the speed record, not the route audit line,
not an approval, not a receipt, not a device's last_seen. The one sentence it
gets back when it asks for a change is REFUSAL below.

WHY FAIL-CLOSED. The private flag can only ever make a turn stricter, so every
doubt is answered "no". `persist()` refuses a write for a private turn, and it
refuses a write whose kind is not in KINDS: an unknown writer is a bug here,
not a writer that gets a pass. `is_private()` reads only JSON `true` -
"yes", 1 and "true" are ordinary chats, exactly the rule the temporary flag
has always had.

WHAT ASKS THIS MODULE. jarvis_quick.py refuses a mutating fast-path intent
before it runs (so no reminder, receipt, setting or file is touched), and the
jarvis_hud.py patch (private-chat.patch) asks `persist()` at every disk write
its chat turn makes and `is_private()` for X-Jarvis-Route, the tools switch
and the device last_seen hold.

NOT IN HERE. The word hash the live-turn registry keeps in RAM (the temporary
chat's own behaviour - it is never the words, and never on disk). A backend
without this module is exactly the backend before private-chat.patch: the
flag is ignored, the fast path behaves as always, and nothing errors.
"""
from __future__ import annotations

#: The one sentence a private chat answers with when it asks for a change.
#: Agreed with the architect on 2026-10-25 (H10, ruling point 3).
REFUSAL = ("A private chat can read, search, and answer, but it doesn't change "
           "settings, save items, or run actions — switch back to a normal chat "
           "to do that.")

#: Every disk write a chat turn can make. `persist()` refuses all of them for
#: a private turn. This tuple IS the contract: a new writer must add its kind
#: here, and the suite walks it and proves each one is refused.
KINDS = ("chat_history", "memory", "learner", "feedback_turn", "speed",
         "route_audit", "approvals", "receipts", "device_last_seen", "sources",
         "budget")


def is_private(body) -> bool:
    """Is this /api/chat request a private chat? Only JSON `true` - the same
    strict reading `temporary` gets in jarvis_hud._temporary_chat."""
    return isinstance(body, dict) and body.get("private") is True


def persist(kind: str, body=None) -> bool:
    """The single fail-closed write gate: may this turn write `kind` to disk?

    False for every kind in a private chat (zero exceptions); False for a
    kind not in KINDS (fail closed - an unknown writer is refused rather than
    let through); True otherwise, so an ordinary chat is exactly what it was.
    """
    if kind not in KINDS:
        return False
    return not is_private(body)
