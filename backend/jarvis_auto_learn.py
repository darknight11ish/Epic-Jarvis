"""jarvis_auto_learn.py - Jarvis learns automatically, from the owner's own words only.

NEW MODULE, shipped whole. auto-learn.patch (last in the patch order) calls
it from the learner in jarvis_hud.py, and adds GET /api/memory/learning,
GET /api/memory/auto and POST /api/memory/learning/auto|sensitive.
docs/JARVIS-API.md section 19.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-24)
"Jarvis learns automatically by default. Facts about the owner and their
projects, learned from the owner's own words only (never from web pages,
emails, documents, notes or tool output), are saved without a per-fact yes,
and every one is listed in both apps with a one-tap Forget. Sensitive topics
(health, money, passwords and account details, private details about other
people) still wait for the owner's yes, unless the owner turns on 'Also
remember sensitive topics automatically', which is off by default. Turning
either setting on raises an approval card; turning it off is immediate."
And, decided later that day after the safety research: "Passwords, PINs,
account numbers and ID numbers always wait for the owner's yes, even with
'Also remember sensitive topics automatically' on. That setting covers
health, money and the other sensitive topics only."

WHAT THIS DOES
The learner still PROPOSES every fact into the review queue, exactly as
before. After each learning pass (and after each "Remember: ..."), this file
looks at what was just proposed and saves a proposal WITHOUT a card only when
every check below passes. Anything that fails any check stays an ordinary
card, and the card says which check stopped it, in plain words
(`auto_reason` on its /api/memory/pending row).

Saving goes through jarvis_extract.accept_auto() (auto-learn.patch), which
claims the proposal exactly as decide() does and writes it through the same
_accept(), so the fact's words, meaning search and dates are kept the same
way as a card you accepted - with source "auto" and where it came from in
its meta.

THE CHECKS (each a small function below, returning a reason in words or "")
  Settings    "Learn automatically" on (default ON), background learning on,
              jarvis_intake.py installed.
  The model   the learner's model is on this PC: OLLAMA_URL is loopback AND
              the model is not an Ollama cloud model (jarvis_router.
              is_remote_model) - nor is the second card's (GUARDS L11).
  Source      "conversation", or "remember" from a typed or voice turn.
              Never gate_denial, import:*, feedback_retire or anything else.
  Seen live   EVERY owner turn the learner read was seen arriving by this PC
              (jarvis_chat_log's live-turn registry, which is kept whether or
              not chat history is on), in the same conversation, typed or a
              verified voice transcript, and the conversation had not read
              outside text by then. One turn that fails makes every proposal
              from that pass a card: the model read it, and nothing says
              which turn a fact came from (GUARDS L1, L2, L4, H1, H5).
  Voice       a voice turn counts only when the check that let it in was
              very strict, decided by the stronger model, in mode "owner" (L8)
              - and, when the owner chose "only trust the talk button" for
              hands-free voice, only when it was started with the talk button.
  Outside     no sign of pasted text in any turn: a link or web-page code,
              hidden characters, a long encoded block, email headers, more
              than TURN_MAX_CHARS, or an injection_flags() hit - on the turns
              AND on the proposal (L4).
  Grounded    every content word and number in the fact is in the owner's
              own turns (L5).
  Correction  a proposal that would replace a stored fact is always a card
              (L6).
  Sensitive   jarvis_sensitive.py on the fact and on the turns it came from:
              word lists in eight languages, number and token shapes, the
              other-person rule, then the learner's own local model. Unless
              "Also remember sensitive topics automatically" is on, a hit is a
              card (L7). When unsure - or when the model does not answer: a hit.
              With it on, passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses are still a
              card (jarvis_sensitive.always_asks - the patterns only, no
              model; the owner's decision of 2026-09-24, after the safety
              research).

NOTHING LEAVES THIS PC. There is no network code here; the sensitive-topic
check asks the learner's own model, on this PC only. The event it raises,
`memory_saved`, carries fact ids only - never the words (L10).
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import threading
import time
import unicodedata
import uuid as _uuid
from contextlib import closing
from pathlib import Path
from typing import Callable, Optional

AUTO_ACTION = "learning_auto_enable"
SENSITIVE_ACTION = "learning_sensitive_enable"

#: A typed message longer than this reads as pasted, so it is never learned
#: from automatically (it still makes cards).
TURN_MAX_CHARS = 600

#: The one "Remember" shape learned automatically: a colon, one line.
_REMEMBER_AUTO = re.compile(r"^\s*remember\s*:\s*\S[^\n\r]*$", re.IGNORECASE)

#: How the approval gate names the stronger speaker model (jarvis_voice.
#: MODEL_BARS), and its file's short hash.
STRONG_MODEL_LABEL = "the stronger voice-ID model"
STRONG_MODEL_HASH = "d51abcf31717"

LIST_DEFAULT, LIST_MAX = 30, 100
_CID = re.compile(r"[A-Za-z0-9_-]{8,64}")

AUTO_CARD = "\n".join([
    "Turn on automatic learning.",
    "",
    "Jarvis will save facts about you and your projects from what you type or "
    "say to it - never from web pages, emails, documents or notes - without "
    "asking about each one. Every fact it saves is listed under \"Saved "
    "automatically\" in both apps, where you can forget it.",
    "",
    "Nothing leaves this PC. You can turn it off at any time from either app, "
    "and that is instant.",
    "",
    "If you say no: every fact still waits for your yes.",
])

SENSITIVE_CARD = "\n".join([
    "Also remember sensitive topics automatically.",
    "",
    "Health, money, and private details about other people, from what you type "
    "or say to Jarvis, will be saved without asking you first, and listed under "
    "\"Saved automatically\" with Forget.",
    "",
    "Passwords, PINs, account and ID numbers, birthdays, phone numbers and "
    "email addresses always wait for your yes, even with this on.",
    "",
    "Nothing leaves this PC. You can turn it off at any time from either app, "
    "and that is instant.",
    "",
    "If you say no: Jarvis keeps asking you first about these.",
])

AUTO_TEXT = ("Jarvis saves facts about you and your projects from what you type "
             "or say to it - never from web pages, emails, documents or notes. "
             "You can forget any of them here.")
SENSITIVE_TEXT = ("Health, money, and private details about other people. When this "
                  "is off, Jarvis asks you first. Passwords, PINs, account and ID "
                  "numbers, birthdays, phone numbers and email addresses always wait "
                  "for your yes.")
#: The note under "Learn automatically" while background learning is off -
#: the desktop's sentence, which both apps now show (fit audit item 10).
NEEDS_LEARNING = ("Background learning is off, so nothing is saved automatically. "
                  "Start background learning above to use this.")


# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The same folder jarvis_memory and jarvis_intake use, found the same way."""
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
    return _config_dir() / "auto-learning.json"


# --------------------------------------------------------------------------
#   1. The two settings
# --------------------------------------------------------------------------

_SETTINGS_LOCK = threading.Lock()

#: A damaged settings file reads as OFF. The switch then shows off, so the
#: one thing to do is turn it on: that card, approved, rewrites the file
#: (fit audit item 1 - it used to say "off and on again", but it already
#: shows off).
_DAMAGED = ("the automatic learning settings file is damaged, so nothing is saved "
            "automatically. Turn \"Learn automatically\" on again to rewrite it")


def settings() -> dict:
    """{"auto", "auto_sensitive", "why"}.

    No file at all, or a file that never had "auto": Learn automatically is
    ON - the owner's default. A file that cannot be read, is not JSON, or
    holds anything but true/false: OFF, and `why` says so (fail closed).
    "Also remember sensitive topics automatically": off unless the file says
    exactly true."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"auto": True, "auto_sensitive": False, "why": ""}
    except OSError as exc:
        return {"auto": False, "auto_sensitive": False,
                "why": f"the automatic learning settings file could not be read "
                       f"({type(exc).__name__}), so nothing is saved automatically"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"auto": False, "auto_sensitive": False,
                "why": _DAMAGED}
    auto = doc.get("auto", True)
    sens = doc.get("auto_sensitive", False)
    why = ""
    if not isinstance(auto, bool):
        auto, why = False, _DAMAGED
    if not isinstance(sens, bool):
        sens = False
    return {"auto": auto, "auto_sensitive": sens, "why": why}


def _save(**changes) -> dict:
    with _SETTINGS_LOCK:
        cur = settings()
        new = {"auto": cur["auto"], "auto_sensitive": cur["auto_sensitive"]}
        new.update(changes)
        new["changed"] = time.time()
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(new), encoding="utf-8")
        os.replace(tmp, p)
    return settings()


def set_auto(on: bool) -> dict:
    return dict(_save(auto=bool(on)), ok=True)


def set_sensitive(on: bool) -> dict:
    return dict(_save(auto_sensitive=bool(on)), ok=True)


# --------------------------------------------------------------------------
#   The approval cards (the shape of jarvis_learning_switch.py)
# --------------------------------------------------------------------------
#
# ON: one approval card and 202 {"waiting": true} at once. Only tier "ask"
# with outcome "approved" turns it on; denied, timed out, refused or turned
# off while the card waited changes nothing. OFF: immediate, never a card,
# and it withdraws a waiting ON card. Only the NEWEST card may set `last`
# (an older withdrawn card answering later must not be shown as the newer
# one's outcome) - the lessons of commit 260ddc5.

KINDS = ("auto", "sensitive")


def action_for(kind: str) -> str:
    """The approval action for one of the two switches."""
    return AUTO_ACTION if kind == "auto" else SENSITIVE_ACTION


_LOCK = threading.Lock()
_STATE = {k: {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}} for k in KINDS}
#: One lock per switch, held from an approved card's "was it withdrawn?"
#: check through writing the setting, and from OFF's withdrawing through
#: writing "off". Without it an OFF landing between the check and the write
#: was answered "off" and then overwritten by the card's "on" (red team R5,
#: reproduced before the fix). Always taken BEFORE _LOCK, never inside it.
_SWITCH = {k: threading.Lock() for k in KINDS}

#: What each way a card can end means, in plain words for the apps - the
#: `message` beside the technical `why` in auto_last / sensitive_last (fit
#: audit item 28).
LAST_WORDS = {
    "enabled": "You approved the card, so it is on.",
    "denied": "The card was turned down, so it stayed off.",
    "timed_out": "Nobody answered the card in time, so it stayed off.",
    "refused": "Your PC's settings do not let this be approved, so it stayed off.",
    "withdrawn": "You turned it off while the card waited, so approving it changed nothing.",
    "failed": "It was approved, but the setting could not be saved, so it stayed off.",
}
GATE_FAILED_WORDS = "The approval card could not be raised, so it stayed off."


def _card_text(kind: str) -> str:
    return AUTO_CARD if kind == "auto" else SENSITIVE_CARD


def _what(kind: str) -> str:
    return ("turn on automatic learning" if kind == "auto"
            else "also remember sensitive topics automatically")


def _setting_on(kind: str) -> bool:
    st = settings()
    return st["auto"] if kind == "auto" else st["auto_sensitive"]


def _apply_for(kind: str) -> Callable[[bool], dict]:
    return set_auto if kind == "auto" else set_sensitive


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-auto-learn-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def _finish(kind: str, pid: str, outcome: str, why: str = "",
            message: Optional[str] = None) -> None:
    s = _STATE[kind]
    with _LOCK:
        if s["pending"].get("id") == pid:
            s["pending"].clear()
        s["withdrawn"].discard(pid)
        if s["latest"].get("id") not in (None, pid):
            return
        s["last"].clear()
        s["last"].update(outcome=outcome, why=why, at=time.time(),
                         message=message or LAST_WORDS.get(outcome, ""))
    _audit(f"learning.{kind}.card", {"outcome": outcome})


def _decide(kind: str, pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    action = action_for(kind)
    text = _card_text(kind)
    try:
        v = gate(action, {"text": text, "what": _what(kind), "leaves_this_pc": False}, text)
    except Exception as exc:
        return _finish(kind, pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})", GATE_FAILED_WORDS)
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(action) != "ask":
        return _finish(kind, pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(kind, pid, outcome)
        return _finish(kind, pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH[kind]:
        # Held until the setting is written and `last` says so: an OFF
        # pressed meanwhile waits, then turns it off (red team R5).
        with _LOCK:
            withdrawn = pid in _STATE[kind]["withdrawn"]
        if withdrawn:
            return _finish(kind, pid, "withdrawn",
                           "you turned it off while the card was waiting")
        try:
            out = apply(True) or {}
        except Exception as exc:
            return _finish(kind, pid, "failed", type(exc).__name__)
        if out.get("ok") is False:
            return _finish(kind, pid, "failed", str(out.get("error", "")))
        _finish(kind, pid, "enabled")


def request(kind: str, enabled, *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None,
            apply: Optional[Callable[[bool], dict]] = None) -> tuple:
    """POST /api/memory/learning/auto (kind "auto") and /sensitive. Returns
    (http code, body)."""
    if kind not in KINDS:
        return 404, {"error": "no such setting"}
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    apply = apply or _apply_for(kind)
    s = _STATE[kind]
    if not isinstance(enabled, bool):
        return 400, {"error": 'need {"enabled": true|false}'}
    if not enabled:
        with _SWITCH[kind]:
            # The same lock an approved card holds from its withdrawn check
            # to its write: OFF is never overwritten by that card (R5).
            with _LOCK:
                if s["pending"]:
                    # Withdrawn AND no longer the waiting card: approving it
                    # does nothing, and a later ON raises a fresh card.
                    s["withdrawn"].add(s["pending"]["id"])
                    s["pending"].clear()
            try:
                apply(False)
            except Exception as exc:
                return 500, {"ok": False,
                             "error": f"could not save the setting ({type(exc).__name__})"}
        _audit(f"learning.{kind}.off", {})
        out = learning_status()
        out.update(ok=True, waiting=False, message=(
            "Learn automatically is off. Every fact waits for your yes." if kind == "auto"
            else "Sensitive topics wait for your yes."))
        return 200, out
    with _LOCK:
        waiting = bool(s["pending"])
    if _setting_on(kind) and not waiting:
        out = learning_status()
        out.update(ok=True, waiting=False, message="It is already on.")
        return 200, out
    action = action_for(kind)
    tier = tier_of(action)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{action} is tier {tier!r} in jarvis-framework.toml; turning this on needs a "
            f"person to say yes, so it must be 'ask'")}
    with _LOCK:
        pid = None if s["pending"] else _uuid.uuid4().hex
        if pid is not None:
            s["pending"].update(id=pid, since=time.time())
            s["latest"]["id"] = pid
    if pid is None:
        out = learning_status()
        out.update(ok=True, waiting=True, message="A card to turn this on is already "
                                                  "waiting for your approval.")
        return 202, out
    try:
        spawn(lambda: _decide(kind, pid, apply, gate, tier_of))
    except Exception:
        with _LOCK:
            s["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    out = learning_status()
    out.update(ok=True, waiting=True,
               message="Waiting for your approval. It turns on only if you approve the "
                       "card, on your PC or phone.")
    return 202, out


def state(kind: str) -> dict:
    s = _STATE[kind]
    with _LOCK:
        return {"waiting": bool(s["pending"]), "last": dict(s["last"]) or None}


def _reset_for_tests() -> None:
    with _LOCK:
        for s in _STATE.values():
            for v in s.values():
                v.clear()


def learning_status(learning_on: Optional[bool] = None, floor: Optional[bool] = None) -> dict:
    """GET /api/memory/learning's body. `learning_on` is the backend's own
    learning_enabled(); None when the caller does not know it."""
    st = settings()
    a, s = state("auto"), state("sensitive")
    out = {"auto": st["auto"], "auto_sensitive": st["auto_sensitive"],
           "auto_waiting": a["waiting"], "sensitive_waiting": s["waiting"],
           "auto_last": a["last"], "sensitive_last": s["last"],
           "why": st["why"]}
    if learning_on is not None:
        out["enabled"] = bool(learning_on)
        out["auto_active"] = bool(learning_on) and st["auto"]
        out["note"] = "" if learning_on else NEEDS_LEARNING
    if floor is not None:
        out["floor"] = bool(floor)
    try:
        import jarvis_learning_switch as LS
        ls = LS.state()
        # Background learning's own card - named apart from `waiting`, which
        # a POST reply uses for the card of the switch it changed.
        out["learning_waiting"], out["learning_last"] = ls["waiting"], ls["last"]
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
#   2. The checks - each returns "" when it passes, else a reason in words
# --------------------------------------------------------------------------

def check_settings(learning_on: bool) -> str:
    st = settings()
    if not st["auto"]:
        return st["why"] or "automatic learning is off"
    if not learning_on:
        return "background learning is off"
    return ""


def check_intake() -> str:
    try:
        import jarvis_intake  # noqa: F401
    except Exception:
        return "part of Jarvis's learning is not installed (jarvis_intake.py)"
    return ""


def _is_loopback(url) -> bool:
    try:
        import urllib.parse
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def _remote(name) -> bool:
    """Is this model answered off this machine? Fails closed: a router that
    cannot be read says yes."""
    try:
        import jarvis_router
        return bool(jarvis_router.is_remote_model(str(name or "")))
    except Exception:
        return True


def check_local_model(ollama_url, model) -> str:
    """GUARDS L11: the learner's model is on this PC, by address AND by name."""
    if not _is_loopback(ollama_url):
        return "the learning model is not on this PC"
    if not model or _remote(model):
        return "the learning model is a cloud model, not one on this PC"
    try:
        import jarvis_second_card
        lane = jarvis_second_card._learning_lane()
    except Exception:
        lane = None
    if lane is not None:
        if not _is_loopback(getattr(lane, "url", "")) or _remote(getattr(lane, "model", "")):
            return "the second card's learning model is not on this PC"
    return ""


def check_source(source) -> str:
    if source in ("conversation", "remember"):
        return ""
    if source == "gate_denial":
        return "made from an action you turned down, not from something you said"
    if isinstance(source, str) and source.startswith("import"):
        return "from an imported chat history"
    return "not from something you said"


_PROVENANCE_WHY = {
    "shared": "from shared text",
    "clipboard": "from the clipboard",
    "pasted": "from pasted text",
    "picture_caption": "from words sent with a picture",
    "voice_unverified": "said aloud, but this PC could not check it was your voice",
    # temporary-chat.patch (2026-09-25): a turn of a temporary chat is noted
    # in the live-turn registry (a hash, never the words, so the
    # conversation's "read outside text" mark still works) under this
    # provenance, so nothing re-sent from it is ever saved without a card.
    "temporary": "said in a temporary chat, which Jarvis never learns from",
    "unknown": "not marked as typed or said by you",
}


def check_provenance(entry: Optional[dict]) -> str:
    if entry is None:
        return "from a message this PC did not see arrive (re-sent or older history)"
    prov = entry.get("provenance")
    if prov in ("typed", "voice"):
        return ""
    return _PROVENANCE_WHY.get(prov, _PROVENANCE_WHY["unknown"])


def _strong(model) -> bool:
    m = str(model or "")
    label = STRONG_MODEL_LABEL
    try:
        import jarvis_voice
        label = jarvis_voice.MODEL_BARS[STRONG_MODEL_HASH]["label"]
    except Exception:
        pass
    return m == label or STRONG_MODEL_HASH in m


def check_voice(entry: dict) -> str:
    """GUARDS L8: a voice turn counts only when the voice check was very
    strict, decided by the stronger model, in mode "owner"."""
    if entry.get("provenance") != "voice":
        return ""
    vc = entry.get("voice_check") if isinstance(entry.get("voice_check"), dict) else {}
    if (vc.get("strictness") != "very_strict" or vc.get("mode") != "owner"
            or not _strong(vc.get("model"))):
        return ("said aloud, but the voice check was not at its strictest "
                "(very strict, the stronger voice model)")
    if not _source_trusted(vc.get("source")):
        return HANDS_FREE_WHY
    return ""


#: The card's reason when the owner's "hands-free" voice setting is "only
#: trust the talk button" and the turn was not started with the button.
HANDS_FREE_WHY = "said hands-free - your setting only trusts the talk button"


def _source_trusted(source) -> bool:
    """The owner's "hands-free" voice setting (jarvis_voice.
    hands_free_trusted, the owner's decision of 2026-09-24): is a voice turn
    that started this way - "push_to_talk", "wake_word", or "" when the
    speech route did not say - trusted like the talk button? A jarvis_voice
    without that setting: yes, as before. One that cannot answer: no (a
    card)."""
    try:
        import jarvis_voice
    except Exception:
        return True
    fn = getattr(jarvis_voice, "hands_free_trusted", None)
    if fn is None:
        return True
    try:
        return bool(fn(source))
    except Exception:
        return False


def check_taint(entry: dict) -> str:
    if entry.get("tainted") or entry.get("read_outside"):
        return "the conversation read outside text (a tool ran)"
    return ""


_LINK = re.compile(r"https?://|\bwww\.|\]\([^)]*\)|\[[^\]]*\]\s*\[[^\]]*\]"
                   r"|<\s*/?\s*[a-z][a-z0-9-]*(?:\s[^>]*)?>|<!--|&[a-z]+;|&#\d+;", re.I)
#: Characters that show as nothing, or as a blank, and are not in the
#: Unicode "format" / "private use" / "unassigned" groups _hidden() reads by
#: category: variation selectors (both blocks - enough to smuggle whole
#: sentences, one byte per selector), the combining grapheme joiner, the
#: Hangul and half-width fillers, the Braille blank, Khmer and Mongolian
#: invisibles, and the line and paragraph separators (red team R4).
_HIDDEN = re.compile("[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f"
                     "\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u206f"
                     "\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff9-\ufffb]"
                     "|[\U000e0000-\U000e01ef]")
#: Cf format, Co private use, Cn unassigned, Cs lone surrogates.
_HIDDEN_CATEGORIES = ("Cf", "Co", "Cn", "Cs")


def _hidden(text: str) -> bool:
    """Is any character in it invisible, or not a character at all? Control
    characters count too, except tab and the two line ends."""
    if _HIDDEN.search(text):
        return True
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in _HIDDEN_CATEGORIES or (cat == "Cc" and ch not in "\t\n\r"):
            return True
    return False


_ENCODED = re.compile(r"[A-Za-z0-9+/=_-]{48,}")
#: One piece of an encoded block split up to hide it: 8+ characters of the
#: base64 / hex alphabet that mix digits with letters, or have a capital
#: after the first letter ("SWdub3Jl", "aGVsbG8K"). Ordinary words do not.
_CHUNK = re.compile(r"[A-Za-z0-9+/=_-]+")
_ENCODED_JOINED = 48


def _chunky(tok: str) -> bool:
    if len(tok) < 8:
        return False
    digit = any(c.isdigit() for c in tok)
    letter = any(c.isalpha() for c in tok)
    inner_cap = any(c.isupper() for c in tok[1:]) and any(c.islower() for c in tok)
    return (digit and letter) or inner_cap or any(c in "+/=" for c in tok[1:-1])


def _encoded(text: str) -> bool:
    """A long encoded block, whole or cut into pieces with spaces or
    punctuation between them (red team R4: 40-character pieces got
    through): pieces next to each other, 48 characters or more in all."""
    if _ENCODED.search(text):
        return True
    run, end = 0, -10
    for m in _CHUNK.finditer(text):
        tok = m.group(0)
        if not _chunky(tok):
            run = 0
            continue
        gap = text[end:m.start()] if end >= 0 else ""
        run = run + len(tok) if (run and len(gap) <= 3 and not gap.strip(" \t\r\n.,;:-_|")) \
            else len(tok)
        end = m.end()
        if run >= _ENCODED_JOINED:
            return True
    return False


#: A web address without http:// or www.: "evil.example/owner-facts", or a
#: name ending in a well-known top-level domain (red team R4).
_DOMAIN = re.compile(
    r"\b[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
    r"\.[a-z]{2,24}/[^\s]*"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:com|net|org|io|co|uk|de|fr|ru|cn|info"
    r"|biz|app|dev|ai|xyz|top|site|online|gov|edu|example|test|ly|gg|tv|eu|link|click"
    r"|sh|gl|page|cloud|tech|store|shop|zip|mov|onion)\b", re.I)
_EMAIL_HEAD = re.compile(r"(?im)^\s*(?:from|to|subject|cc|bcc|date|sent|reply-to|"
                         r"return-path|received|message-id)\s*:"
                         r"|-{2,}\s*(?:original|forwarded)\s+message"
                         r"|^\s*on\b.{3,120}\bwrote:\s*$|^\s*>")


def outside_signs(text: str) -> str:
    """Signs that a message holds text the owner did not type: "" or the
    first sign found, in words."""
    if not isinstance(text, str):
        return "not text"
    if len(text) > TURN_MAX_CHARS:
        return f"longer than {TURN_MAX_CHARS} characters, which reads as pasted text"
    if _LINK.search(text) or _DOMAIN.search(text):
        return "it has a link or web-page code in it"
    if _hidden(text):
        return "it has hidden characters in it"
    if _encoded(text):
        return "it has a long encoded block in it"
    if _EMAIL_HEAD.search(text):
        return "it looks like an email"
    return ""


def check_outside(text: str) -> str:
    sign = outside_signs(text)
    if sign:
        return "looks like pasted text: " + sign
    if _injection(text):
        return "reads like an instruction to Jarvis"
    return ""


#: Cyrillic and Greek letters that look like Latin ones. "іgnore previous
#: instructions" with a Cyrillic і read as nothing to injection_flags() (red
#: team R4), so it also reads the text with these swapped for the Latin
#: letter, after NFKC (which already folds full-width and styled letters).
_LOOKALIKE = str.maketrans({
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "з": "3", "к": "k", "м": "m", "н": "h",
    "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s", "і": "i",
    "ї": "i", "ј": "j", "ԁ": "d", "ԛ": "q", "ԝ": "w", "һ": "h", "ӏ": "l", "ɡ": "g",
    "А": "A", "В": "B", "Е": "E", "Ё": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X", "Ѕ": "S", "І": "I", "Ї": "I",
    "Ј": "J", "Ԛ": "Q", "Ԝ": "W", "Һ": "H", "Ӏ": "I",
    # Greek
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k", "τ": "t", "υ": "u",
    "χ": "x", "ε": "e", "ς": "c", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H",
    "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y",
    "Χ": "X",
})


def plain_letters(text: str) -> str:
    """The text as injection_flags() should read it: NFKC, look-alike
    letters swapped for Latin ones, invisible characters taken out."""
    t = unicodedata.normalize("NFKC", str(text or "")).translate(_LOOKALIKE)
    return "".join(ch for ch in _HIDDEN.sub("", t)
                   if unicodedata.category(ch) not in _HIDDEN_CATEGORIES)


def _injection(text: str) -> bool:
    try:
        import jarvis_intake
        if jarvis_intake.injection_flags(text):
            return True
        plain = plain_letters(text)
        return plain != text and bool(jarvis_intake.injection_flags(plain))
    except Exception:
        return True                  # cannot check: not saved automatically


def check_instruction(fact: str) -> str:
    if _injection(fact):
        return "reads like an instruction to Jarvis"
    sign = outside_signs(fact)
    if sign:
        return "looks like pasted text: " + sign
    return ""


def check_not_correction(row: dict) -> str:
    """GUARDS L6: an automatic fact never retires or replaces another."""
    if row.get("replaces_id") or row.get("replaces"):
        return "it would replace a fact you already have"
    return ""


# ---- a fact that contradicts one already saved (the memory review, B5) ----
#
# GUARDS L6 above only sees a correction the learner's MODEL marked ("replaces").
# A model that leaves it out - "I live in York now" when Jarvis knows "Owner
# lives in Leeds" - used to be saved automatically, and both stayed true. So
# before an automatic save the stored facts are read too. A clash makes the
# proposal a card that names the fact it would replace (replaces_id, as the
# model's own correction would); it never retires anything by itself -
# only the owner accepting the card does, as for every correction.

#: Things a person has ONE of at a time: where they live, where and as what
#: they work, what they drive, what someone or something is called, and
#: "Owner's phone/car/manager... is". Each pattern gives the slot (who, and
#: which of these) and the value; two facts with the same slot and different
#: values contradict each other. "likes", "has", "plays" are not here:
#: "Owner likes folk" does not replace "Owner likes jazz".
_SUBJ = r"(?P<who>owner(?:'s(?: [a-z][\w-]*){1,3}?)?)"
_ONE_VALUE = [
    ("lives", re.compile(_SUBJ + r" (?:now )?(?:lives|live|is living|is based) (?:in|at|on) "
                         r"(?P<value>.+)$")),
    ("works", re.compile(_SUBJ + r" (?:now )?(?:works|work|is working) "
                         r"(?P<prep>at|for|as) (?P<value>.+)$")),
    ("drives", re.compile(_SUBJ + r" (?:now )?drives (?P<value>.+)$")),
    ("called", re.compile(_SUBJ + r" (?:is|are) (?:called|named) (?P<value>.+)$")),
    ("is", re.compile(r"(?P<who>owner's (?:(?:new|current|favourite|favorite) )?"
                      r"(?:phone|car|bike|laptop|manager|boss|doctor|gp|dentist|landlord"
                      r"|landlady|address|postcode|job|employer|team|school|university"
                      r"|favourite \w+|favorite \w+)) (?:is|are) (?P<value>.+)$")),
]
#: Words that say something CHANGED or ended.
_CHANGE = re.compile(r"\b(?:now|no longer|not any ?more|any ?more|moved|quit|stopped"
                     r"|switched|left|gave up|no more|used to)\b")
_FILLER_END = re.compile(r"\s*\b(?:now|currently|these days|any ?more|at the moment)\s*$")


def _plain(text: str) -> str:
    """Lower case, our date brackets off, "the owner" as "owner", one space."""
    t = str(text or "").lower().replace("’", "'")
    try:
        import jarvis_intake
        t = jarvis_intake._ADDED.sub(" ", t)
    except Exception:
        pass
    t = re.sub(r"\bthe (owner|user)\b", "owner", t)
    t = re.sub(r"\buser('s)?\b", r"owner\1", t)
    return " ".join(re.sub(r"[.!?]+$", "", t).split())


def _slot(text: str):
    """(slot, value) for a fact about one of the things a person has one of
    at a time, else None."""
    t = _plain(text)
    for name, rx in _ONE_VALUE:
        m = rx.match(t)
        if m:
            value = _FILLER_END.sub("", m.group("value")).strip(" ,")
            prep = m.groupdict().get("prep") or ""
            return (m.group("who"), name, prep), value
    return None


def _shared(a: str, b: str) -> int:
    """How many content words two facts share, the owner left out."""
    try:
        M = sys.modules.get("jarvis_memory")
        words = M._words if M is not None else None
    except Exception:
        words = None
    if words is None:
        words = lambda s: set(_words(s)) - _GROUND_STOP     # noqa: E731
    return len((words(a) - {"owner", "now"}) & (words(b) - {"owner", "now"}))


def find_contradiction(fact: str, store) -> Optional[dict]:
    """The stored CURRENT fact this one would change, or None: the same slot
    (_ONE_VALUE) with a different value, or a change word ("now", "no
    longer", "moved", "quit" ...) and two or more content words in common.
    Never raises: anything that fails is None (and the other checks still
    run)."""
    try:
        mine = _slot(fact)
        changes = bool(_CHANGE.search(_plain(fact)))
        if mine is None and not changes:
            return None
        try:
            hits = store.search(fact, k=8, word_floor=0.0)
        except TypeError:
            hits = store.search(fact, k=8)
        low = _plain(fact)
        for h in hits:
            if h.get("current") is False:
                continue
            other = str(h.get("text") or "")
            if _plain(other) == low:
                continue
            theirs = _slot(other)
            if mine is not None and theirs is not None and theirs[0] == mine[0] \
                    and theirs[1] != mine[1]:
                return h
            if changes and _shared(fact, other) >= 2:
                return h
    except Exception:
        return None
    return None


#: The card's reason for a contradiction (the fact's words are not in it:
#: the card itself shows the fact it would replace).
CHANGES_A_FACT = ("it would change a fact you already have - accepting it replaces "
                  "that one")


# ---- grounding ------------------------------------------------------------

#: Words that carry no fact of their own, plus the ways a fact names the
#: owner ("I" -> "the owner", "my" -> "the owner's").
_GROUND_STOP = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "by", "from", "as", "into", "onto", "about", "than", "that", "this",
    "these", "those", "it", "its", "is", "are", "was", "were", "be", "been",
    "being", "am", "has", "have", "had", "having", "do", "does", "did", "i", "me",
    "my", "mine", "myself", "im", "ive", "id", "ill", "owner", "owners", "user",
    "users", "he", "she", "they", "them", "their", "theirs", "him", "her", "his",
    "hers", "we", "our", "ours", "us", "you", "your", "yours", "who", "whom",
    "whose", "which", "what", "s", "also", "currently", "now", "very", "really",
    "just", "so", "there", "here",
}
#: Never stemmed and never satisfied by a look-alike: "notes" must not ground
#: "not".
_NEGATION = {"not", "no", "never", "nor", "none", "nobody", "nothing", "neither",
             "without", "cannot", "longer", "anymore", "former", "formerly", "ex",
             "used", "stopped", "quit"}


def _words(text: str) -> list:
    t = str(text or "").lower().replace("\u2019", "'")
    t = re.sub(r"\bcan't\b", "can not", t)
    t = re.sub(r"\bwon't\b", "will not", t)
    t = re.sub(r"n't\b", " not", t)
    t = t.replace("cannot", "can not")
    t = re.sub(r"'(?:s|re|m|ve|d|ll)\b", " ", t)
    return re.findall(r"[a-z0-9]+", t)


_IRREGULAR = {"goes": "go", "does": "do", "children": "child", "people": "person",
              "men": "man", "women": "woman", "wives": "wife", "lives": "live"}


def _stem(w: str) -> str:
    w = _IRREGULAR.get(w, w)
    for suffix, keep in (("ies", 3), ("ing", 3), ("ed", 3), ("es", 3), ("s", 3)):
        if w.endswith(suffix) and len(w) - len(suffix) >= keep:
            if suffix == "s" and w.endswith("ss"):
                break
            w = w[:-len(suffix)] + ("y" if suffix == "ies" else "")
            break
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def _pool(turns: list) -> tuple:
    """(stems, exact words) of the owner's turns, with the real dates
    jarvis_intake.anchor_dates() works out from their relative dates."""
    words = []
    try:
        import jarvis_intake
        anchored = [jarvis_intake.anchor_dates(t) for t in turns]
    except Exception:
        anchored = []
    for t in list(turns) + anchored:
        words += _words(t)
    return {_stem(w) for w in words}, set(words)


def _fact_words(fact: str) -> list:
    try:
        import jarvis_intake
        fact = jarvis_intake._ADDED.sub(" ", fact)     # our own date brackets
    except Exception:
        pass
    return [w for w in _words(fact) if w not in _GROUND_STOP]


#: Number words and their digits, one to twenty (the memory review, I3):
#: "I have three cats" grounds "Owner has 3 cats", and "2 dogs" grounds
#: "two dogs". Speech-to-text writes either, and so does the model. Only
#: the SAME number: "three" never grounds "4".
_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}


def _as_number(w: str) -> str:
    """The digits a number word means ("three" -> "3"), else the word."""
    return _NUMBER_WORDS.get(w, w)


def ungrounded(fact: str, turns: list) -> list:
    """The fact's words that are NOT in the owner's turns."""
    stems, exact = _pool(turns)
    numbers = {_as_number(x) for x in exact}
    out = []
    for w in _fact_words(fact):
        if any(ch.isdigit() for ch in w) or w in _NUMBER_WORDS:
            if w not in exact and _as_number(w) not in numbers:
                out.append(w)
        elif w in _NEGATION:
            if w not in exact:
                out.append(w)
        elif _stem(w) not in stems and w not in exact:
            out.append(w)
        elif w not in exact and _bare(w) and all(
                x.endswith(("ed", "ing")) for x in exact if _stem(x) == _stem(w)):
            # A plain word matched only by a past or -ing form: "hated"
            # does not ground "hat" (red team R2, "stem clash").
            out.append(w)
    return out


def _bare(w: str) -> bool:
    """A word with no ending _stem() takes off (bar a final e)."""
    s = _stem(w)
    return s == w or (w.endswith("e") and s == w[:-1])


def check_grounded(fact: str, turns: list) -> str:
    """GUARDS L5: every content word and every number of the fact is in
    what the owner said - and the fact leaves out nothing that changed what
    it meant (check_meaning, red team R2)."""
    if not _fact_words(fact):
        return "not in your own words"
    if ungrounded(fact, turns):
        return "not in your own words"
    return check_meaning(fact, turns)


# ---- what a fact leaves out (red team R2) ----------------------------------
#
# Grounding asks only whether each of the fact's words was said. It cannot
# see a word the fact LEFT OUT: "I don't drink coffee any more" grounds
# "Owner drinks coffee" word for word, and "My sister works at Google"
# grounds "Owner works at Google". So each sentence the fact came from is
# also read for the words that change what it means - a "not", a "used to",
# an "if", a "sister", a "she" - and a fact that drops one is a card.

#: (the word as the card says it, the pattern on _meaning_text()).
_QUALIFIERS = (
    ("not", r"\bnot\b"),
    ("no", r"\b(?:no|none|nobody|nothing|neither|nor|without)\b"),
    ("never", r"\bnever\b"),
    ("no longer", r"\bno longer\b"),
    ("any more", r"\bany ?more\b"),
    ("used to", r"\bused to\b"),
    ("quit", r"\bquit(?:s|ting)?\b"),
    ("stopped", r"\bstop(?:s|ped|ping)?\b"),
    ("gave up", r"\b(?:give|gives|gave|given|giving) up\b"),
    ("former", r"\b(?:former|formerly|ex)\b"),
    ("if", r"\b(?:if|unless|whether)\b"),
    ("would", r"\b(?:would|could|should)\b"),
    ("might", r"\bmight\b"),
    ("maybe", r"\b(?:maybe|perhaps|probably)\b"),
    ("planning", r"\bplan(?:s|ned|ning)?\b"),
    ("thinking of", r"\bthink(?:s|ing)? (?:of|about)\b|\bconsider(?:s|ed|ing)?\b"),
    ("hope to", r"\bhop(?:e|es|ed|ing) to\b|\bwish(?:es|ed|ing)?\b"),
    ("want to", r"\bwant(?:s|ed|ing)? to\b"),
)
_QUALIFIER_RX = [(label, re.compile(rx)) for label, rx in _QUALIFIERS]

#: Other people. A fact that drops one ("my sister works at Google" ->
#: "the owner works at Google") has moved between people.
_RELATIONS = {
    "sister", "brother", "sibling", "wife", "husband", "spouse", "partner",
    "girlfriend", "boyfriend", "fiance", "fiancee", "boss", "manager", "friend",
    "mum", "mom", "mother", "dad", "father", "parent", "son", "daughter", "kid",
    "child", "baby", "colleague", "coworker", "cousin", "aunt", "uncle", "niece",
    "nephew", "grandma", "grandmother", "grandad", "granddad", "grandpa",
    "grandfather", "grandson", "granddaughter", "grandchild", "neighbour",
    "neighbor", "flatmate", "roommate", "housemate", "stepmum", "stepmom",
    "stepdad", "stepson", "stepdaughter", "law",       # "in-law"
}
_RELATION_FORMS = {"children": "child", "wives": "wife", "sisters": "sister"}
#: Someone else, by a pronoun: the fact does not get to say who it was.
_THIRD_PERSON = {"he", "she", "him", "her", "his", "hers", "himself", "herself",
                 "they", "them", "their", "theirs", "themselves"}
#: The owner, in the owner's own words.
_FIRST_PERSON = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours",
                 "im", "ive", "id", "ill"}
_NAMES_OWNER = {"owner", "owners", "user", "users"}


def _meaning_text(text: str) -> str:
    t = str(text or "").lower().replace("’", "'")
    t = re.sub(r"'d\b", " would", t)           # "I'd like to" keeps its "would"
    t = re.sub(r"^\s*(?:no|nope|nah)\s*[,!.:;-]+", " ", t)   # "No, I live in Leeds"
    return " ".join(_words(t))


def _relations(words) -> set:
    out = set()
    for w in words:
        w = _RELATION_FORMS.get(w, w)
        if w not in _RELATIONS and w.endswith("s") and w[:-1] in _RELATIONS:
            w = w[:-1]
        if w in _RELATIONS:
            out.add(w)
    return out


def _sentences(turns: list) -> list:
    out = []
    for t in turns:
        out += [s for s in re.split(r"(?<=[.!?;])\s+|[\r\n]+", str(t or "")) if s.strip()]
    return out


def source_sentences(fact: str, turns: list) -> list:
    """The sentences of the owner's turns that share a content word or a
    number with the fact - all of them when none does (fail closed)."""
    want = {_stem(w) for w in _fact_words(fact)
            if not any(ch.isdigit() for ch in w) and w not in _NEGATION}
    nums = {w for w in _fact_words(fact) if any(ch.isdigit() for ch in w)}
    every = _sentences(turns)
    out = []
    for s in every:
        ws = _words(s)
        if want & {_stem(w) for w in ws} or nums & set(ws):
            out.append(s)
    return out or every


#: Past forms that do not end in "ed", and the present they belong to.
_PAST_IRREGULAR = {
    "went": "go", "drove": "drive", "taught": "teach", "ran": "run", "sang": "sing",
    "wore": "wear", "ate": "eat", "knew": "know", "grew": "grow", "wrote": "write",
    "swam": "swim", "spoke": "speak", "rode": "ride", "flew": "fly", "kept": "keep",
    "slept": "sleep", "built": "build", "bought": "buy", "brought": "bring",
    "thought": "think", "made": "make", "took": "take", "gave": "give", "held": "hold",
    "led": "lead", "met": "meet", "paid": "pay", "sold": "sell", "told": "tell",
    "understood": "understand", "won": "win",
}
#: "I've lived here for years" is still true now: a past form after these
#: is the present perfect, not the past.
_PERFECT = re.compile(r"\b(?:have|has|'ve|ve|'s|having)\s+(?:\w+\s+){0,2}$")


def _past_forms(w: str, turns: list) -> list:
    """The forms of `w` the owner used, when every one of them is the plain
    past ("lived", "worked", "went") and none is a present perfect ("I've
    lived") - else []."""
    stem = _stem(w)
    seen = []
    for t in turns:
        low = str(t or "").lower().replace("’", "'")
        for m in re.finditer(r"[a-z]+", low):
            x = m.group(0)
            base = _PAST_IRREGULAR.get(x)
            if _stem(x) != stem and not (base and _stem(base) == stem):
                continue
            if x == w:
                return []                          # the owner said this very form
            past = x.endswith("ed") or base is not None
            if not past or _PERFECT.search(low[:m.start()]):
                return []
            seen.append(x)
    return seen


def check_tense(fact: str, turns: list) -> str:
    """"" unless the fact says something is true NOW that the owner only
    said in the past tense - "I lived in Paris for two years in my
    twenties" is not "Owner lives in Paris" (the memory review, B7). A fact
    that keeps the past ("Owner lived in Paris", "Owner moved to York in
    2024") is fine, and so is the present perfect ("I've lived here since
    2019")."""
    for w in _fact_words(fact):
        if any(ch.isdigit() for ch in w) or w in _NEGATION or w.endswith(("ed", "ing")):
            continue
        if w in _PAST_IRREGULAR or len(w) < 3:
            continue
        if _past_forms(w, turns):
            return ("what you said was in the past tense, and the fact says it is true "
                    "now")
    return ""


#: Capitalised words that open a clause without naming anyone.
_NOT_A_NAME = {
    "i", "i'm", "im", "i've", "ive", "i'd", "i'll", "the", "a", "an", "my", "our", "your",
    "his", "her", "their", "its", "this", "that", "these", "those", "it", "we", "you",
    "he", "she", "they", "yes", "no", "ok", "okay", "so", "well", "anyway", "honestly",
    "also", "and", "but", "or", "oh", "hey", "hi", "hello", "today", "tomorrow",
    "yesterday", "tonight", "now", "then", "actually", "basically", "remember", "note",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "owner", "jarvis", "work", "home",
    "there", "here", "what", "when", "where", "who", "why", "how", "if", "as", "at", "in",
    "on", "for", "with", "not", "never", "just", "still", "all", "some", "every", "each",
}
_CLAUSE_SPLIT = re.compile(r"\s*[,;:]\s*|\s+(?:and|but|while|whereas|whilst)\s+", re.I)


def _other_clause(fact: str, sentences: list) -> str:
    """The name of someone else when the part of a sentence a fact about the
    owner came from is about THEM (the memory review, B6): "Dana works at
    Google and I work at Apple" is split into its clauses, the clause that
    shares the most of the fact's words is the one it came from, and when
    that clause names a person the fact leaves out and has no "I" or "my",
    the fact moved between people. "" otherwise - including when a clause
    that fits as well is the owner's own."""
    want = {_stem(w) for w in _fact_words(fact)
            if not any(ch.isdigit() for ch in w) and w not in _NEGATION}
    if not want:
        return ""
    best, top = [], 0
    for s in sentences:
        for c in _CLAUSE_SPLIT.split(str(s or "")):
            if not c.strip():
                continue
            n = len(want & {_stem(w) for w in _words(c)})
            if n > top:
                best, top = [c], n
            elif n == top and n:
                best.append(c)
    if not best:
        return ""
    if any(set(_meaning_text(c).split()) & _FIRST_PERSON for c in best):
        return ""
    in_fact = {w.lower() for w in re.findall(r"[\w'’-]+", str(fact))}
    for c in best:
        for m in re.finditer(r"(?<![\w'’])([A-Z][a-z][\w'’-]*)", c):
            name = re.sub(r"['’]s$", "", m.group(1))
            if name.lower() in _NOT_A_NAME or name.lower() in in_fact:
                continue
            return name
    return ""


def check_meaning(fact: str, turns: list) -> str:
    """"" when the fact keeps every word of its source sentences that
    changes what they mean; else which one it left out, in words."""
    tense = check_tense(fact, turns)
    if tense:
        return tense
    fact_text = _meaning_text(fact)
    fact_words = set(fact_text.split())
    fact_rel = _relations(fact_words)
    about_owner = bool(fact_words & _NAMES_OWNER)
    sentences = source_sentences(fact, turns)
    for s in sentences:
        said = _meaning_text(s)
        if s.rstrip().endswith("?") and not fact.rstrip().endswith("?"):
            return "what you said was a question, and the fact states it as true"
        for label, rx in _QUALIFIER_RX:
            if rx.search(said) and not rx.search(fact_text):
                return f"what you said had \"{label}\" in it, and the fact leaves it out"
        said_words = said.split()
        missing = sorted(_relations(said_words) - fact_rel)
        if missing:
            return (f"what you said was about your {missing[0]}, and the fact leaves "
                    f"that out - it may be about someone else")
        other = sorted((set(said_words) & _THIRD_PERSON) - fact_words)
        if other:
            return (f"what you said was about \"{other[0]}\" - someone else - and the "
                    f"fact does not say who")
    if about_owner and not any(set(_meaning_text(s).split()) & _FIRST_PERSON
                               for s in sentences):
        return "what you said was not about you, but the fact says it is"
    if about_owner and _other_clause(fact, sentences):
        # Not the name itself: this reason is kept beside the card, and a
        # name is the owner's words about someone else.
        return ("that part of what you said was about someone else, and the fact "
                "says it is about you")
    return ""


def source_turns(fact: str, turns: list) -> list:
    """The owner turns a fact shares a content word with."""
    want = {_stem(w) for w in _fact_words(fact)
            if not any(ch.isdigit() for ch in w) and w not in _NEGATION}
    nums = {w for w in _fact_words(fact) if any(ch.isdigit() for ch in w)}
    out = []
    for t in turns:
        ws = _words(t)
        if want & {_stem(w) for w in ws} or nums & set(ws):
            out.append(t)
    return out or list(turns)


# ---- sensitivity (GUARDS L7) ---------------------------------------------
#
# The check itself is jarvis_sensitive.py (shipped whole, backend/README.md
# "The sensitive-topic check"): word lists in eight languages, the shapes of
# codes, card and ID numbers, money and addresses, the other-person rule, and
# a question to the learner's own local model. A pattern hit, a "yes" or an
# "unsure" from the model, or no usable answer from it: a card. If that
# module is missing or fails, every fact is a card (fail closed).

def sensitivity(text: str) -> str:
    """"" or the topic in plain words ("health", "religion", "someone else's
    money"). The patterns only - no model - so it is cheap enough to run on
    every recalled fact. jarvis_sensitive.topic(); when that module cannot
    be loaded, any non-empty text counts as sensitive."""
    if not isinstance(text, str) or not text.strip():
        return ""
    try:
        import jarvis_sensitive
        # fact_topic: the patterns, and - when they find nothing - the topic
        # the fact was SAVED with (the memory review, B13).
        return getattr(jarvis_sensitive, "fact_topic", jarvis_sensitive.topic)(text)
    except Exception:
        return "a topic that could not be checked (jarvis_sensitive.py is missing)"


#: The card's reason when a fact holds something that always waits for a
#: yes (the owner's decision of 2026-09-24, after the safety research) -
#: given while "Also remember sensitive topics automatically" is on; with it
#: off, the ordinary sensitive-topic reason is given, as before.
ALWAYS_ASKS = {
    "credentials": "a password, PIN or account number - these always wait for your yes",
    "identity": "an ID number, birth date or contact details - these always wait for your yes",
}


def sensitive_key(fact: str, turns: list) -> str:
    """The sensitive topic of a fact as a label to keep WITH it - "health",
    "other_people", "unsure" when the check could not say - or "" (the
    memory review, B13). Kept so read-aloud and web search still know, once
    it is saved, what the local model said when it was saved: its words
    alone can look everyday ("Owner's best mate Liam tried to kill himself
    in May" names only a person).

    The same check as the card (jarvis_sensitive.classify - the local model
    included, and its answers are cached, so a card that was just checked
    is not asked twice). A fact whose words and source turns the patterns
    find nothing in is "" without asking the model: with "Also remember
    sensitive topics automatically" on, only those facts cost a model call.
    Fails closed: a check that cannot run is "unsure"."""
    try:
        import jarvis_sensitive as S
        texts = [fact] + [t for t in turns or [] if isinstance(t, str)]
        if not any(S.patterns(t)["sensitive"] for t in texts):
            return ""
        v = S.classify(fact, context=[t for t in turns or [] if isinstance(t, str)])
        if not v.get("reason"):
            return ""
        cats = [c for c in v.get("categories") or [] if c in S.CATEGORIES]
        return cats[0] if cats else "unsure"
    except Exception:
        return "unsure"


def check_sensitive(fact: str, turns: list, allowed: bool) -> str:
    """"" when the fact may be saved without a card, else the card's reason:
    "about health, a sensitive topic". `allowed` is the owner's "Also
    remember sensitive topics automatically".

    On, health, money, other people and the rest are saved - but passwords,
    PINs, account and ID numbers, birthdays, phone numbers and email addresses still are not (jarvis_sensitive.
    always_asks, on the fact AND the words it came from). That check is the
    patterns alone: the model is not asked, so the switch adds no wait."""
    try:
        import jarvis_sensitive
    except Exception:
        return "the check for sensitive topics is not installed (jarvis_sensitive.py)"
    if not allowed:
        return jarvis_sensitive.card_reason(fact, turns)
    always = getattr(jarvis_sensitive, "always_asks", None)
    if always is None:
        return ("the check for passwords, PINs and ID numbers is not installed "
                "(jarvis_sensitive.py is too old)")
    for text in [fact] + [t for t in turns or [] if isinstance(t, str)]:
        try:
            cat = always(text)
        except Exception as exc:
            return f"the check for passwords, PINs and ID numbers failed ({type(exc).__name__})"
        if cat:
            return ALWAYS_ASKS.get(cat, ALWAYS_ASKS["credentials"])
    return ""


# --------------------------------------------------------------------------
#   The turns, looked up in the live-turn registry
# --------------------------------------------------------------------------

def _live(conversation_id, text) -> Optional[dict]:
    try:
        import jarvis_chat_log
        return jarvis_chat_log.live_turn(conversation_id, text)
    except Exception:
        return None


def check_turns(turns: list, conversation_id) -> tuple:
    """("" or the first reason, [registry entries]) for the owner turns a
    pass read. Every turn must pass."""
    if not (isinstance(conversation_id, str) and _CID.fullmatch(conversation_id)):
        return "the app did not say which conversation this was", []
    entries = []
    if not turns:
        return "no words of yours to learn from", []
    for text in turns:
        entry = _live(conversation_id, text)
        why = (check_provenance(entry) or check_voice(entry) or check_taint(entry)
               or check_outside(text))
        if why:
            return why, entries
        entries.append(entry)
    return "", entries


# --------------------------------------------------------------------------
#   Where a card's reason is kept
# --------------------------------------------------------------------------
#
# A small table in the memory database, beside `proposals`: the reason a
# proposal stayed a card, and the provenance of a "Remember:" card's words.
# annotate() in jarvis_intake.py adds `auto_reason` to each /api/memory/pending
# row from it.

def _store():
    M = sys.modules.get("jarvis_memory")
    if M is None:
        import jarvis_memory as M  # type: ignore
    return M.store()


def _init_notes(c) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS auto_learn_notes ("
              " proposal_id INTEGER PRIMARY KEY, reason TEXT, provenance TEXT, at REAL,"
              " sensitive TEXT)")
    # `sensitive` (the memory review, B13): the topic a card was held back
    # for - a label ("health"), never words. A table from before it gets
    # the column.
    cols = [r[1] for r in c.execute("PRAGMA table_info(auto_learn_notes)")]
    if "sensitive" not in cols:
        c.execute("ALTER TABLE auto_learn_notes ADD COLUMN sensitive TEXT")


def _note_card(c, pid: int, reason: str, provenance: Optional[str] = None,
               sensitive: Optional[str] = None) -> None:
    _init_notes(c)
    c.execute("INSERT OR REPLACE INTO auto_learn_notes (proposal_id, reason, provenance, at,"
              " sensitive) VALUES (?,?,?,?,?)",
              (int(pid), reason, provenance, time.time(), sensitive or None))


def card_notes(ids) -> dict:
    """{proposal id: {"auto_reason", "provenance"}} for these proposals."""
    ids = [int(i) for i in ids or [] if isinstance(i, int) and not isinstance(i, bool)]
    if not ids:
        return {}
    M = sys.modules.get("jarvis_memory")
    if M is None or getattr(M, "_store", None) is None:
        return {}        # no store open: nothing to read, and none is made here
    try:
        st = M.store()
        with closing(st._connect()) as c:
            _init_notes(c)
            rows = c.execute(
                "SELECT proposal_id, reason, provenance FROM auto_learn_notes WHERE proposal_id IN (%s)"
                % ",".join("?" * len(ids)), ids).fetchall()
    except Exception:
        return {}
    return {int(r[0]): {"auto_reason": r[1] or "", "provenance": r[2]} for r in rows}


def annotate(rows: list) -> list:
    """Called by jarvis_intake.annotate() for /api/memory/pending: each row
    gets `auto_reason` - why it stayed a card, in words, or "" when automatic
    learning did not look at it (or was off) - and a "Remember:" card keeps
    its "in your own words" label only when its words were typed or said to
    this PC (GUARDS L3)."""
    notes = card_notes([r.get("id") for r in rows if isinstance(r, dict)])
    for r in rows:
        if not isinstance(r, dict):
            continue
        n = notes.get(r.get("id")) or {}
        r["auto_reason"] = n.get("auto_reason") or ""
        if r.get("source") == "remember" and n:
            r["verbatim"] = n.get("provenance") in ("typed", "voice")
    return rows


def _rows(c, ids) -> dict:
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    got = c.execute("SELECT * FROM proposals WHERE id IN (%s)" % ",".join("?" * len(ids)),
                    ids).fetchall()
    out = {}
    for r in got:
        d = dict(r) if not isinstance(r, tuple) else None
        if d is None:
            names = [x[0] for x in c.execute("SELECT * FROM proposals LIMIT 0").description]
            d = dict(zip(names, r))
        out[int(d["id"])] = d
    return out


# --------------------------------------------------------------------------
#   Saving
# --------------------------------------------------------------------------

def _extract():
    return sys.modules.get("jarvis_extract") or __import__("jarvis_extract")


def _publish(ids: list) -> None:
    """The `memory_saved` event: fact ids only, never the words (L10)."""
    if not ids:
        return
    try:
        import jarvis_events
        jarvis_events.BUS.publish("memory_saved", {"ids": [int(i) for i in ids]})
    except Exception:
        pass


def _save_fact(pid: int, meta: dict, extract=None) -> Optional[int]:
    x = extract or _extract()
    fn = getattr(x, "accept_auto", None)
    if fn is None:
        return None          # jarvis_extract.py without auto-learn.patch: cards only
    fid = fn(int(pid), dict(meta))
    return int(fid) if isinstance(fid, int) and not isinstance(fid, bool) and fid > 0 else None


def _provenance_of(entries: list) -> str:
    return "voice" if any(e.get("provenance") == "voice" for e in entries) else "typed"


def _meta(source: str, entries: list, conversation_id: str) -> dict:
    newest = max(entries, key=lambda e: e.get("seq", 0)) if entries else {}
    return {"auto": True, "proposal_source": source,
            "device": newest.get("device") or "unknown",
            "provenance": _provenance_of(entries),
            "conversation_id": conversation_id,
            "message_hash": newest.get("message_hash"),
            "tainted": False, "saved_at": time.time()}


def after_pass(out, turns, *, conversation_id=None, model=None, ollama=None,
               learning_on: bool = True, extract=None, publish: Callable = _publish) -> dict:
    """Called by the learner after one pass, with what propose() just queued
    (`out`) and the owner turns it read (`turns`, [{"role", "content"}]).
    Saves the proposals that pass every check; the rest stay cards, with
    their reason noted. Returns {"saved": [fact ids], "cards": {pid: reason}}.
    Never raises."""
    result = {"saved": [], "cards": {}}
    try:
        pids = [int(r["id"]) for r in out or []
                if isinstance(r, dict) and isinstance(r.get("id"), int)]
        if not pids:
            return result
        texts = [t.get("content") if isinstance(t, dict) else t for t in turns or []]
        texts = [t for t in texts if isinstance(t, str) and t.strip()]
        off = check_settings(learning_on)
        batch = off or check_intake() or check_local_model(ollama, model)
        entries = []
        if not batch:
            batch, entries = check_turns(texts, conversation_id)
        allowed = settings()["auto_sensitive"]
        st = _store()
        with closing(st._connect()) as c:
            rows = _rows(c, pids)
            decisions = {}
            topics = {}
            for pid in pids:
                row = rows.get(pid)
                if row is None or row.get("state") != "pending":
                    continue
                fact = str(row.get("text") or "")
                why = batch or check_source(row.get("source"))
                if not why and row.get("source") != "conversation":
                    why = "not from something you said"
                src = source_turns(fact, texts) if not why else []
                why = why or check_not_correction(row) or check_instruction(fact)
                sens = ""
                if not why:
                    why = check_sensitive(fact, src, allowed)
                    if why or allowed:
                        # B13: the topic goes with the card (accepting it
                        # saves the fact with it) or, under "Also remember
                        # sensitive topics automatically", with the fact.
                        sens = sensitive_key(fact, src)
                why = why or check_grounded(fact, texts)
                if not why:
                    # B5: a clash with a stored fact the model did not mark.
                    # The card then names that fact, as a correction would.
                    old = find_contradiction(fact, st)
                    if old is not None:
                        why = CHANGES_A_FACT
                        c.execute("UPDATE proposals SET replaces_id=?, replaces_text=?"
                                  " WHERE id=? AND state='pending' AND replaces_id IS NULL",
                                  (int(old["id"]), str(old.get("text") or ""), pid))
                        c.commit()
                decisions[pid] = why
                topics[pid] = sens
                if why and not off:
                    # No reason is noted while automatic learning is off:
                    # then every proposal is a card, as it always was.
                    _note_card(c, pid, why, sensitive=sens)
        for pid, why in decisions.items():
            if why:
                result["cards"][pid] = why
                continue
            meta = _meta("conversation", entries, conversation_id)
            if topics.get(pid):
                meta["sensitive"] = topics[pid]
            try:
                fid = _save_fact(pid, meta, extract)
            except Exception:
                fid = None
            if fid is None:
                result["cards"][pid] = "could not be saved automatically"
                with closing(st._connect()) as c:
                    _note_card(c, pid, result["cards"][pid])
            else:
                result["saved"].append(fid)
        if result["saved"]:
            publish(result["saved"])
            _entity_model_pass(result["saved"], ollama, model)
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


def _entity_model_pass(ids: list, ollama, model) -> None:
    """The entity layer's OPTIONAL model pass (jarvis_entities.py): off by
    default, and then this does nothing at all. On, it starts ONE local
    call over the facts this pass saved, on its own background thread, to
    link the people and things they name - links only, grounded in each
    fact's own words. The facts were linked by fixed rules when they were
    saved either way."""
    try:
        import jarvis_entities
        jarvis_entities.after_learner_pass(list(ids), ollama=ollama, model=model)
    except Exception:
        pass


def after_remember(res, messages, *, conversation_id=None, learning_on: bool = True,
                   extract=None, publish: Callable = _publish) -> dict:
    """Called by the learner right after "Remember: ..." was queued word for
    word (jarvis_intake.remember_from_turn's result is `res`). Saves it
    without a card when the newest turn passes every check. The model is not
    involved, so there is no model to check. Never raises."""
    result = {"saved": [], "cards": {}}
    try:
        if not isinstance(res, dict) or not res.get("queued") \
                or not isinstance(res.get("proposal_id"), int):
            return result
        pid = int(res["proposal_id"])
        last = messages[-1] if isinstance(messages, list) and messages else None
        content = last.get("content") if isinstance(last, dict) else None
        entry = _live(conversation_id, content) if isinstance(content, str) else None
        prov = entry.get("provenance") if entry else None
        off = check_settings(learning_on)
        why = off or check_intake()
        if not why:
            if not (isinstance(conversation_id, str) and _CID.fullmatch(conversation_id)):
                why = "the app did not say which conversation this was"
            else:
                why = (check_provenance(entry) or check_voice(entry) or check_taint(entry))
        if not why and not (isinstance(content, str) and _REMEMBER_AUTO.match(content.strip())):
            why = "\"Remember\" with a colon, on one line, is saved automatically - this was not"
        if not why:
            why = check_outside(content)
        st = _store()
        with closing(st._connect()) as c:
            row = _rows(c, [pid]).get(pid)
            if row is None or row.get("state") != "pending":
                return result
            fact = str(row.get("text") or "")
            if not why:
                why = (check_source(row.get("source"))
                       or ("" if row.get("source") == "remember" else "not from something you said")
                       or check_not_correction(row) or check_instruction(fact)
                       or check_sensitive(fact, [content], settings()["auto_sensitive"]))
            # The provenance goes with the card either way: annotate() shows
            # "in your own words" only for words typed or said to this PC
            # (GUARDS L3). No reason is noted while automatic learning is off.
            _note_card(c, pid, "" if off else why, prov)
        if why:
            result["cards"][pid] = why
            return result
        try:
            fid = _save_fact(pid, _meta("remember", [entry], conversation_id), extract)
        except Exception:
            fid = None
        if fid is None:
            result["cards"][pid] = "could not be saved automatically"
            with closing(st._connect()) as c:
                _note_card(c, pid, result["cards"][pid], prov)
            return result
        result["saved"].append(fid)
        try:
            import jarvis_intake
            if isinstance(jarvis_intake._remember_last, dict):
                jarvis_intake._remember_last.update(
                    auto_saved=True, note="Saved automatically. You can forget it under "
                                          "\"Saved automatically\".")
        except Exception:
            pass
        publish(result["saved"])
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


# --------------------------------------------------------------------------
#   GET /api/memory/auto - the "Saved automatically" list
# --------------------------------------------------------------------------

def list_auto(limit=LIST_DEFAULT, before=None, *, store=None, now=None) -> dict:
    """Auto-saved facts still current, newest first. Paged by whole seconds
    like the chat history list: a page never splits a second, so `before`
    means strictly older seconds and nothing is skipped or repeated."""
    st = settings()
    out = {"facts": [], "auto": st["auto"], "auto_sensitive": st["auto_sensitive"]}
    try:
        limit = max(1, min(LIST_MAX, int(limit)))
    except (TypeError, ValueError):
        limit = LIST_DEFAULT
    now = time.time() if now is None else now
    store = store or _store()
    sql = ("SELECT id, text, created, meta, valid_from FROM facts WHERE source='auto'"
           " AND (valid_to IS NULL OR valid_to > ?)")
    args = [now]
    where = ""
    if isinstance(before, (int, float)) and not isinstance(before, bool) and math.isfinite(before):
        where = " AND created < ?"
        args.append(float(math.floor(before)))
    with closing(store._connect()) as c:
        rows = c.execute(sql + where + " ORDER BY created DESC, id DESC LIMIT ?",
                         args + [limit]).fetchall()
        rows = [tuple(r) for r in rows]
        if len(rows) == limit:
            sec = math.floor(rows[-1][2] or 0)
            have = {r[0] for r in rows}
            rest = c.execute(sql + " AND created >= ? AND created < ?"
                             " ORDER BY created DESC, id DESC",
                             [now, float(sec), float(sec + 1)]).fetchall()
            rows += [tuple(r) for r in rest if r[0] not in have]
    # "Said again" (memory idea 3): how often the owner has said a fact
    # again since it was saved, and when last. Only for those said again.
    try:
        again = store.said_again_counts([int(r[0]) for r in rows])
    except Exception:
        again = {}
    for fid, text, created, meta, valid_from in rows:
        try:
            m = json.loads(meta or "{}")
            m = m if isinstance(m, dict) else {}
        except Exception:
            m = {}
        prov = m.get("provenance") if m.get("provenance") in ("typed", "voice") else "typed"
        row = {"id": int(fid), "text": text, "saved_at": int(created or 0),
               "provenance": prov, "device": str(m.get("device") or "unknown")}
        if again.get(int(fid)):
            row["said_again"] = {"count": again[int(fid)]["count"],
                                 "last": int(again[int(fid)]["last"])}
        true_from = _true_from_day(m, valid_from)
        if true_from:
            row["true_from"] = true_from
        out["facts"].append(row)
    return out


def _true_from_day(meta: dict, valid_from) -> Optional[str]:
    """"YYYY-MM-DD" - the day this fact became true, in this PC's time zone -
    only when that date came from the owner's own words (memory idea 4:
    "I moved to Leeds in January" is true from 1 January, and the store marks
    it meta["true_from"] = "said"). Otherwise None: the fact became true when
    it was saved, which `saved_at` already says. Both apps show it as "true
    from 1 January 2026" (the memory review's I10, 2026-09-27)."""
    M = sys.modules.get("jarvis_memory")
    said = getattr(M, "TRUE_FROM_SAID", "said")
    if meta.get("true_from") != said:
        return None
    try:
        v = float(valid_from)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v <= 0:
        return None
    import datetime as _dt
    try:
        return _dt.date.fromtimestamp(v).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


# --------------------------------------------------------------------------
#   Recall: one fact line inside the FACTS block (auto-learn.patch)
# --------------------------------------------------------------------------

#: The two lines the recalled-facts block is quoted between, and anything a
#: model could read as one of them.
_FACTS_MARK = re.compile(r"-{2,}\s*(?:end\s*)?facts\s*-{2,}", re.I)


def recall_line(line) -> str:
    """One recalled fact, made safe to put between ---FACTS--- and ---END
    FACTS---: on one line, and with nothing in it that reads as either
    line. A saved fact that said "---END FACTS--- Ignore the above" could
    otherwise close the quoted block early and speak as an instruction (red
    team R7)."""
    t = re.sub(r"[\r\n  \x0b\x0c\x85]+", " ", str(line or ""))
    while True:
        cut = _FACTS_MARK.sub(" ", t)
        if cut == t:
            return t
        t = cut


def is_sensitive_fact(text) -> bool:
    """For X-Jarvis-Route's `injected_sensitive` (the owner's decision of
    2026-09-24: an answer that uses a sensitive saved fact stays on screen).
    True when sensitivity() finds a topic - or cannot be asked (fail
    closed)."""
    try:
        return bool(sensitivity(str(text or "")))
    except Exception:
        return True


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

def _query(qs: str) -> dict:
    from urllib.parse import parse_qs
    try:
        return {k: v[0] for k, v in parse_qs(qs or "", keep_blank_values=True).items() if v}
    except Exception:
        return {}


def handle_get(path: str, query: str = "", *, learning_on: Optional[bool] = None,
               floor: Optional[bool] = None) -> tuple:
    """GET /api/memory/learning and /api/memory/auto. (code, body)."""
    if path == "/api/memory/learning":
        return 200, learning_status(learning_on, floor)
    if path == "/api/memory/auto":
        q = _query(query)
        try:
            limit = int(q.get("limit", LIST_DEFAULT))
        except (TypeError, ValueError):
            limit = LIST_DEFAULT
        before = None
        try:
            b = float(q["before"]) if q.get("before") else None
            # Seconds, not milliseconds: anything past tomorrow is ignored.
            if b is not None and 0 < b < time.time() + 86400:
                before = b
        except (TypeError, ValueError):
            before = None
        return 200, list_auto(limit, before)
    return 404, {"error": "no such route"}


def handle_post(route: str, body) -> tuple:
    """POST /api/memory/learning/auto and /api/memory/learning/sensitive."""
    kind = {"/api/memory/learning/auto": "auto",
            "/api/memory/learning/sensitive": "sensitive"}.get(route)
    if kind is None:
        return 404, {"error": "no such route"}
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        return 400, {"error": 'need {"enabled": true|false}'}
    return request(kind, body["enabled"])
