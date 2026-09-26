"""jarvis_manner.py - how Jarvis words things: warm and brief (the default),
or plain.

NEW MODULE, shipped whole. manner.patch adds GET and POST /api/manner to
jarvis_hud.py; jarvis_agent.py reads current() for the local model's
instructions, and jarvis_quick.py for its fixed answers.

THE OWNER'S DECISION (2026-09-25, after the creativity audit): "Jarvis's
manner: warm and brief by default, with a 'Plain' option in both apps'
settings (plain, businesslike answers). Manner never changes what Jarvis
does, asks or remembers - only how it phrases things."

WHAT IT CHANGES, AND ONLY THIS
  * One short system line (NOTE below) in the request THIS PC's model gets,
    placed just before the newest question - never first, so the Jarvis
    rules block stays first (jarvis_agent.keep_rules_first), and worded so
    it cannot loosen a rule: it names itself "wording only" and repeats that
    every rule still applies. It is added in jarvis_agent.run_local_turn,
    to the request for this PC's model and nowhere else - never to the
    conversation an app sent, so the relay (the only path to a cloud model,
    which gets the newest user turn and nothing else, cloud-one-turn.patch)
    never sees it.
  * The wording of jarvis_quick.py's fixed answers (timers, reminders, the
    to-do list): two phrasings of each, the same facts in both.
Nothing else reads it. It never changes a card, a tier, what is learned or
kept, or what is sent anywhere. Spoken answers keep the spoken-style rules
(jarvis_agent.SPOKEN_NOTE goes after this line, nearer the question).

NO CARD EITHER WAY. The setting does not trust anything more, show anything
more or send anything anywhere, so neither direction raises an approval
card (the rule for cards is about loosening; this loosens nothing).

WHERE IT IS KEPT: `manner.json` in the backend's config folder, beside
web-search.json. A missing or damaged file is the default, warm.

"FROM NOW ON ..." (the owner's decision, 2026-09-27). jarvis_quick.py
detects the phrase in the owner's own live words and calls set_temporary()
or handle_set() here - this module only holds the ONE extra idea that
needed: a manner that applies for ONE conversation only, in memory, never
written to `manner.json`, because a temporary chat makes no memory
(ARCHITECTURE section 5). `current()` takes an optional `conversation_id`
and checks that map first. Gone when the process restarts; bounded the same
way every other per-conversation map in this project is
(jarvis_agent.py's `_OPENED`).
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

WARM = "warm"
PLAIN = "plain"
MANNERS = (WARM, PLAIN)
DEFAULT = WARM

# The words both apps show (the desktop's Settings, the phone's Mind). The
# apps show the PC's own words from GET /api/manner; their copies are the
# same words, checked by tools/gen_plain_error_cases.py's contract file.
TITLE = "How Jarvis talks"
DETAIL = ("Changes only how Jarvis words its answers. It never changes what Jarvis "
          "does, what it asks you, or what it remembers.")
LABEL = {
    WARM: "Warm and brief (default)",
    PLAIN: "Plain",
}
WHY = {
    WARM: ("Friendly and short, like a helpful person. No gushing, no filler and "
           "no emoji unless you use them."),
    PLAIN: "Neutral and businesslike: just the answer, with no small talk.",
}
SPOKEN = "Spoken answers stay short and easy to listen to either way."
SAID = {
    WARM: "Jarvis will now answer warmly and briefly.",
    PLAIN: "Jarvis will now answer plainly.",
}

# Humour (the owner's decision, 2026-09-27: "a switch in 'How Jarvis
# talks', off to start; never on cards, errors or serious topics"). A
# second, independent switch beside manner - it can be on with either
# manner. Kept in the SAME file as manner (below), because it is the same
# settings screen; handle_set (below) reads-merges-writes so a POST for
# one setting never resets the other.
HUMOR_DEFAULT = False
HUMOR_TITLE = "Humour"
HUMOR_DETAIL = ("Occasional light humour in answers, when it fits. Off by default. Never as "
                "part of an approval, an error message, or a serious or sensitive topic.")
HUMOR_SAID = {
    True: "Jarvis may now use a little humour, when it fits.",
    False: "Jarvis will not use humour.",
}

#: Appended to the manner NOTE (below) only when the humour switch is on.
#: Wording only, like the rest of the note - and it says the same limits
#: the switch's own detail line does, so the model is told the same rule
#: the owner was.
HUMOR_NOTE = (
    " You may add a little light, gentle humour when it naturally fits - never about a "
    "serious or sensitive topic (health, money, safety, grief, crisis, or anything that "
    "sounds upsetting), never inside an approval card or an error message, and never forced.")

# The line the local model gets. Wording only; each ends by saying every
# rule still applies (test_manner.py holds both to that).
NOTE = {
    WARM: ("Manner, for wording only: be warm, friendly and brief, and sound natural, "
           "like a helpful person. Do not gush, do not use filler such as \"Great "
           "question!\", and do not use emoji unless the owner does. All of Jarvis's "
           "rules still apply in full: still say what is a guess, and never claim an "
           "action was taken when it was not."),
    PLAIN: ("Manner, for wording only: be neutral and businesslike. Answer directly, "
            "with no small talk, praise or emoji, and do not bring up shared jokes or "
            "nicknames unless the owner raises them first. All of Jarvis's rules still "
            "apply in full: still say what is a guess, and never claim an action was "
            "taken when it was not."),
}

_LOCK = threading.Lock()


def _config_dir() -> Path:
    """The same folder the rest of the backend uses, found the same way
    (jarvis_search._config_dir)."""
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw  # type: ignore
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "manner.json"


#: A conversation_id, the same shape every other per-conversation map in
#: this project checks (jarvis_agent._CID_OK, jarvis_quick._CONVERSATION).
_CID_OK = re.compile(r"[A-Za-z0-9_-]{8,64}")

#: "from now on ..." in a TEMPORARY chat (2026-09-27): conversation_id ->
#: manner, in memory only - never written to manner.json. Bounded like
#: jarvis_agent.py's `_OPENED`, so an owner who starts many temporary
#: chats cannot grow this without limit.
_TEMP_LOCK = threading.Lock()
_TEMPORARY: dict[str, str] = {}
_TEMPORARY_MAX = 200


def set_temporary(conversation_id: str, manner: str) -> bool:
    """"From now on, be more plain" (etc.), said in a TEMPORARY chat: the
    manner for THIS conversation only, for the rest of it - never persisted,
    because a temporary chat makes no memory (ARCHITECTURE section 5; the
    owner's decision, 2026-09-27). False (and nothing changed) for a bad
    conversation_id or a manner this module does not know."""
    if not (isinstance(conversation_id, str) and _CID_OK.fullmatch(conversation_id)):
        return False
    if manner not in MANNERS:
        return False
    with _TEMP_LOCK:
        _TEMPORARY.pop(conversation_id, None)
        _TEMPORARY[conversation_id] = manner
        while len(_TEMPORARY) > _TEMPORARY_MAX:
            _TEMPORARY.pop(next(iter(_TEMPORARY)))
    return True


def _read_settings() -> dict:
    """`manner.json`, as a plain dict - `{}` for a missing or damaged file.
    Never raises. The one place both `current()` and `humor_enabled()` read
    the file, and what `handle_set()` merges its one changed key into."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def current(conversation_id: str | None = None) -> str:
    """"warm" or "plain". `conversation_id`, when it has a temporary-chat
    override of its own (set_temporary), wins; otherwise the PC's saved
    setting - the default for a missing or damaged file. Never raises."""
    if isinstance(conversation_id, str) and conversation_id:
        with _TEMP_LOCK:
            m = _TEMPORARY.get(conversation_id)
        if m in MANNERS:
            return m
    m = _read_settings().get("manner")
    return m if m in MANNERS else DEFAULT


def humor_enabled() -> bool:
    """Whether the humour switch (the owner's decision, 2026-09-27) is on -
    off by default, and off for a missing or damaged file. Independent of
    manner: it can be on with either warm or plain. Never raises."""
    h = _read_settings().get("humor")
    return h if isinstance(h, bool) else HUMOR_DEFAULT


def note(manner: str | None = None, humor: bool | None = None) -> str:
    """The line for the local model's request, for `manner` (or the
    setting) - with the humour clause appended when `humor` (or the
    setting) is on."""
    m = manner if manner in MANNERS else current()
    h = humor if isinstance(humor, bool) else humor_enabled()
    return NOTE[m] + (HUMOR_NOTE if h else "")


def view() -> dict:
    m = current()
    h = humor_enabled()
    return {
        "available": True,
        "manner": m,
        "default": DEFAULT,
        "title": TITLE,
        "detail": DETAIL,
        "spoken": SPOKEN,
        "choices": [{"id": k, "label": LABEL[k], "why": WHY[k]} for k in MANNERS],
        # Humour (the owner's decision, 2026-09-27): a second, independent
        # switch on the same "How Jarvis talks" screen - off to start.
        "humor": h,
        "humor_default": HUMOR_DEFAULT,
        "humor_title": HUMOR_TITLE,
        "humor_detail": HUMOR_DETAIL,
    }


def handle_get() -> tuple:
    """GET /api/manner."""
    return 200, view()


def handle_set(body) -> tuple:
    """POST /api/manner {"manner": "warm" | "plain"} and/or {"humor": true |
    false} - at once, no card either way (see the module docstring). Either
    key alone, or both together, in one request; a POST that changes only
    one setting never resets the other, because this reads the file,
    changes just the key(s) sent, and writes it back."""
    if (not isinstance(body, dict) or not body
            or (set(body) - {"manner", "humor"})):
        return 400, {"ok": False, "error": 'send {"manner": "warm"|"plain"} and/or '
                                           '{"humor": true|false}, and nothing else'}
    changed_manner = "manner" in body
    changed_humor = "humor" in body
    m = body.get("manner")
    if changed_manner and m not in MANNERS:
        return 400, {"ok": False, "error": 'manner must be "warm" or "plain"'}
    h = body.get("humor")
    if changed_humor and not isinstance(h, bool):
        return 400, {"ok": False, "error": "humor must be true or false"}
    p = settings_path()
    try:
        with _LOCK:
            doc = _read_settings()
            if changed_manner:
                doc["manner"] = m
            if changed_humor:
                doc["humor"] = h
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, p)
    except OSError as exc:
        # The exception's NAME only: its message names a folder.
        return 500, {"ok": False, "error": f"could not save the setting ({type(exc).__name__})"}
    said = " ".join(s for s in (SAID[m] if changed_manner else None,
                                HUMOR_SAID[h] if changed_humor else None) if s)
    return 200, {"ok": True, "said": said, **view()}
