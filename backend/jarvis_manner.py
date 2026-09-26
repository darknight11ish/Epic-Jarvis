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
"""
from __future__ import annotations

import json
import os
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

# The line the local model gets. Wording only; each ends by saying every
# rule still applies (test_manner.py holds both to that).
NOTE = {
    WARM: ("Manner, for wording only: be warm, friendly and brief, and sound natural, "
           "like a helpful person. Do not gush, do not use filler such as \"Great "
           "question!\", and do not use emoji unless the owner does. All of Jarvis's "
           "rules still apply in full: still say what is a guess, and never claim an "
           "action was taken when it was not."),
    PLAIN: ("Manner, for wording only: be neutral and businesslike. Answer directly, "
            "with no small talk, praise or emoji. All of Jarvis's rules still apply in "
            "full: still say what is a guess, and never claim an action was taken when "
            "it was not."),
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


def current() -> str:
    """"warm" or "plain". The default for a missing or damaged file. Never raises."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
        m = doc.get("manner") if isinstance(doc, dict) else None
        return m if m in MANNERS else DEFAULT
    except Exception:
        return DEFAULT


def note(manner: str | None = None) -> str:
    """The line for the local model's request, for `manner` (or the setting)."""
    m = manner if manner in MANNERS else current()
    return NOTE[m]


def view() -> dict:
    m = current()
    return {
        "available": True,
        "manner": m,
        "default": DEFAULT,
        "title": TITLE,
        "detail": DETAIL,
        "spoken": SPOKEN,
        "choices": [{"id": k, "label": LABEL[k], "why": WHY[k]} for k in MANNERS],
    }


def handle_get() -> tuple:
    """GET /api/manner."""
    return 200, view()


def handle_set(body) -> tuple:
    """POST /api/manner {"manner": "warm" | "plain"} - at once, no card
    either way (see the module docstring)."""
    if not isinstance(body, dict) or set(body) != {"manner"}:
        return 400, {"ok": False, "error": 'send exactly {"manner": "warm"} or {"manner": "plain"}'}
    m = body["manner"]
    if m not in MANNERS:
        return 400, {"ok": False, "error": 'manner must be "warm" or "plain"'}
    p = settings_path()
    try:
        with _LOCK:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps({"manner": m}), encoding="utf-8")
            os.replace(tmp, p)
    except OSError as exc:
        # The exception's NAME only: its message names a folder.
        return 500, {"ok": False, "error": f"could not save the setting ({type(exc).__name__})"}
    return 200, {"ok": True, "said": SAID[m], **view()}
