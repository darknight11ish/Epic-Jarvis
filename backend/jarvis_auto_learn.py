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
              very strict, decided by the stronger model, in mode "owner" (L8).
  Outside     no sign of pasted text in any turn: a link or web-page code,
              hidden characters, a long encoded block, email headers, more
              than TURN_MAX_CHARS, or an injection_flags() hit - on the turns
              AND on the proposal (L4).
  Grounded    every content word and number in the fact is in the owner's
              own turns (L5).
  Correction  a proposal that would replace a stored fact is always a card
              (L6).
  Sensitive   a word-list check (sensitivity()) on the fact and on the turns
              it came from: unless "Also remember sensitive topics
              automatically" is on, a hit is a card (L7). When unsure: a hit.

NOTHING LEAVES THIS PC. There is no network code here. The event it raises,
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
    "Health, money, passwords and account details, and private details about "
    "other people, from what you type or say to Jarvis, will be saved without "
    "asking you first, and listed under \"Saved automatically\" with Forget.",
    "",
    "Nothing leaves this PC. You can turn it off at any time from either app, "
    "and that is instant.",
    "",
    "If you say no: Jarvis keeps asking you first about these.",
])

AUTO_TEXT = ("Jarvis saves facts about you and your projects from what you type "
             "or say to it - never from web pages, emails, documents or notes. "
             "You can forget any of them here.")
SENSITIVE_TEXT = ("Health, money, passwords and account details, and private "
                  "details about other people. When this is off, Jarvis asks you first.")
#: The note under "Learn automatically" while background learning is off -
#: the desktop's sentence, which both apps now show (fit audit item 10).
NEEDS_LEARNING = ("Background learning is off, so nothing is saved automatically. "
                  "Start learning above to use this.")


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
    return ""


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


def ungrounded(fact: str, turns: list) -> list:
    """The fact's words that are NOT in the owner's turns."""
    stems, exact = _pool(turns)
    out = []
    for w in _fact_words(fact):
        if any(ch.isdigit() for ch in w) or w in _NEGATION:
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


def check_meaning(fact: str, turns: list) -> str:
    """"" when the fact keeps every word of its source sentences that
    changes what they mean; else which one it left out, in words."""
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
# Words and shapes, no model. Deliberately broad: a false hit costs one card
# the owner answers; a miss saves a sensitive fact without asking. Every one
# of the 42 phrasings in the memory audit's attack_sensitive.py is caught
# (test_auto_learn.py runs them all).

_OTHER_LANG_PASSWORD = (
    r"mot\s+de\s+passe|passwort|kennwort|contrase[nñ]a|\bclave\b|\bsenha\b|wachtwoord"
    r"|has[lł]o|\bheslo\b|jelsz[oó]|l[oö]senord|adgangskode|passord|salasana"
    r"|\bparola\b|\b[sş]ifre\b|парол|пароль|κωδικ|パスワード|暗証|密码|密碼|비밀번호"
    r"|\u0643\u0644\u0645\u0629\s*(?:\u0627\u0644)?\u0633\u0631|\u05e1\u05d9\u05e1\u05de")   # Arabic "kalimat al-sirr", Hebrew "sisma"

_SENSITIVE = [
    ("passwords and account details", re.compile("|".join([
        r"\bpass\s*(?:word|wd|wrd|code|phrase)s?\b", r"\bpassw\w*", r"\bpas+wo?r?d\b",
        r"\bp[a@4][s$5]{1,2}\w*", r"\bpwd?\b", r"\bpins?\b", r"\bpin\s*(?:number|code)\b",
        r"\b(?:door|alarm|gate|safe|garage|lock|entry|access|security|wi-?fi|verification"
        r"|recovery|backup|unlock|sort|zip)\s*codes?\b",
        r"\bcodes?\b[^.\n]{0,24}\d{3,}", r"\d{3,}[^.\n]{0,24}\bcodes?\b",
        r"\blog-?ins?\b", r"\busernames?\b", r"\bcredentials?\b", r"\blogin\b",
        r"\b2fa\b", r"\bmfa\b", r"\btwo[- ]factor\b", r"\botp\b", r"\bauthenticator\b",
        r"\bone[- ]time\s+(?:code|password|pin)\b",
        r"\bsecurity\s+(?:question|answer)s?\b", r"\bmaiden\s+name\b",
        r"\bcards?\b[^.\n]{0,30}\b(?:ends?|ending|expir\w*|numbers?|cvv|cvc)\b",
        r"\bexpir\w*\b[^.\n]{0,12}\d{1,2}\s*/\s*\d{2,4}", r"\bcvv\b|\bcvc\b",
        r"\b(?:\d{4}[ -]?){3}\d{1,4}\b",
        r"\b(?:ni|national\s+insurance|nhs|social\s+security|ssn|sin|tax|passport"
        r"|driver'?s\s+licen[cs]e|licen[cs]e|account|routing|sort|member(?:ship)?|policy"
        r"|customer|reference|iban|bank)\s*(?:number|no\.?|#|details?)\b",
        r"\b[a-z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[a-d]\b",
        r"\biban\b", r"\bswift\b", r"\bbic\b", r"\bsort\s+code\b",
        r"\bapi[ _-]?keys?\b", r"\btokens?\b", r"\bprivate\s+key\b",
        r"\b(?:seed|recovery)\s+phrase\b", _OTHER_LANG_PASSWORD,
    ]), re.I)),
    ("health", re.compile("|".join([
        r"\bdiagnos\w*", r"\bdiabet\w*", r"\binsulin\b", r"\bglucose\b",
        r"\bblood\s+(?:sugar|pressure|test|tests|work|type|count)\b",
        r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|ug|ml|iu)\b", r"\bdos(?:e|es|age|ing)\b",
        r"\b(?:sertraline|prozac|fluoxetine|zoloft|lexapro|escitalopram|citalopram"
        r"|xanax|valium|diazepam|adderall|ritalin|methylphenidate|lithium|metformin"
        r"|ozempic|wegovy|semaglutide|ibuprofen|paracetamol|codeine|morphine|oxycodone"
        r"|methadone|tramadol|warfarin|statins?|antidepressants?|antibiotics?"
        r"|antipsychotics?|steroids?|inhaler|epipen|chemo\w*|radiotherapy|dialysis"
        r"|hrt|prep)\b",
        r"\b\w+(?:pril|sartan|olol|statin|prazole|oxetine|azepam|zolam|cillin|mycin"
        r"|cycline|floxacin|triptan)\b",
        r"\bmedica\w*", r"\bmeds\b", r"\bmedicine\w*", r"\bpills?\b", r"\bprescri\w*",
        r"\bhiv\b", r"\baids\b", r"\bcancer\w*", r"\btumou?rs?\b", r"\basthma\w*",
        r"\bepilep\w*", r"\bseizures?\b", r"\bdepress(?:ion|ed|ive)\b", r"\banxi\w*",
        r"\bpanic\s+attacks?\b", r"\bbipolar\b", r"\bschizo\w*", r"\badhd\b", r"\badd\b",
        r"\bautis\w*", r"\bocd\b", r"\bptsd\b", r"\beating\s+disorders?\b",
        r"\banorexi\w*", r"\bbulimi\w*", r"\btherap\w*", r"\bpsychiatr\w*",
        r"\bpsycholog\w*", r"\bcounsell?\w*", r"\bmental\s+health\b", r"\bpregnan\w*",
        r"\bmiscarr\w*", r"\babortion\w*", r"\bivf\b", r"\bfertil\w*", r"\binfertil\w*",
        r"\bstds?\b", r"\bstis?\b", r"\bherpes\b", r"\bhepatitis\b", r"\bsurger\w*",
        r"\bsurgeon\w*", r"\bhospital\w*", r"\bclinic\w*", r"\bdoctors?\b", r"\bgp\b",
        r"\bnurse\w*", r"\bsymptoms?\b", r"\billness\w*", r"\bdiseases?\b",
        r"\bdisorders?\b", r"\bsyndromes?\b", r"\ballerg\w*", r"\binjur\w*",
        r"\bdisab\w*", r"\brehab\w*", r"\baddict\w*", r"\balcoholi\w*", r"\bsober\w*",
        r"\boverdos\w*", r"\bsuicid\w*", r"\bself[- ]harm\w*", r"\bheart\s+attack\b",
        r"\bstrokes?\b", r"\bmigraines?\b", r"\barthritis\b", r"\bdementia\b",
        r"\balzheimer\w*", r"\bparkinson\w*", r"\bcovid\w*", r"\bsick\w*",
        r"\bhealth\w*", r"\bmedical\w*", r"\bvaccin\w*", r"\bperiods?\b",
        r"\bmenopaus\w*", r"\bweight\s+loss\b",
    ]), re.I)),
    ("money", re.compile("|".join([
        r"\bsalar\w*", r"\bearn(?:s|ed|ing|ings)?\b", r"\bincome\w*", r"\bwages?\b",
        r"\bpaychecks?\b", r"\bpay\s*slips?\b", r"\bbonus\w*", r"\bowe[sd]?\b",
        r"\bowing\b", r"\bdebts?\b", r"\bloans?\b", r"\bmortgage\w*", r"\brent\b",
        r"\boverdra\w*", r"\bbankrupt\w*", r"\bcredit\s+(?:score|card|rating|report)s?\b",
        r"\bsavings?\b", r"\binvest\w*", r"\bstocks?\b", r"\bshares\b", r"\bcrypto\w*",
        r"\bbitcoin\w*", r"\bpension\w*", r"\b401\s?k\b", r"\bisas?\b", r"\btax\w*",
        r"\bnet\s+worth\b", r"\bbudget\w*", r"\bbills?\b", r"\bfinanc\w*", r"\bbank\w*",
        r"\bbroke\b", r"\bbehind\s+on\b", r"\bin\s+the\s+red\b", r"\bgrand\b",
        r"\b\d+(?:[.,]\d+)?\s?(?:k|m|bn|grand|quid|bucks|dollars?|pounds?|euros?|usd"
        r"|gbp|eur)\b",
        r"[£$€¥₹]\s?\d", r"\d\s?[£$€¥₹]", r"\bper\s+(?:year|annum|month|hour|week)\b",
        r"\b(?:make|makes|made|paid|pays|earn|earns)\b[^.\n]{0,30}\ba\s+(?:year|month|week)\b",
        r"\bmoney\b", r"\bcash\b", r"\bpaid\b", r"\bprice\w*\b", r"\bcosts?\b",
    ]), re.I)),
    ("private details about someone else", re.compile("|".join([
        r"\baffairs?\b", r"\bcheat(?:ing|ed|s)?\b", r"\barrest\w*", r"\bjail\w*",
        r"\bprison\w*", r"\bconvict\w*", r"\bcriminal\w*", r"\bpolice\b",
        r"\bcourt\s+case\b", r"\bdivorc\w*", r"\bsepara\w*", r"\bbr(?:eak|oke)(?:ing)?\s+up\b",
        r"\bha(?:s|ve)n'?t\s+told\b", r"\bha(?:s|ve)\s+not\s+told\b", r"\btold\s+no\s*one\b",
        r"\bnot\s+told\s+anyone\b", r"\bdon'?t\s+tell\b", r"\bdo\s+not\s+tell\b",
        r"\bsecrets?\b", r"\bconfidential\w*", r"\bbetween\s+us\b", r"\bprivate\w*",
        r"\bgay\b", r"\blesbian\b", r"\bbisexual\b", r"\btrans(?:gender)?\b",
        r"\bcom(?:e|ing)\s+out\b", r"\bcame\s+out\b", r"\breligio\w*",
        r"\bimmigra\w*", r"\bvisa\b", r"\bundocumented\b", r"\bdeport\w*",
        r"\baddress\w*", r"\bphone\s+numbers?\b", r"\bmobile\s+numbers?\b",
        r"\b\d+\s+[a-z]+(?:\s+[a-z]+)?\s+(?:street|st|lane|ln|road|rd|avenue|ave|drive|dr"
        r"|close|court|ct|way|place|pl|crescent|terrace|square|boulevard|blvd)\b",
        r"(?<![\d-])(?!\d{4}-\d{2}-\d{2}\b)\+?\d[\d\s().-]{7,}\d",
        r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
        r"\bfired\b", r"\blaid\s+off\b", r"\bsacked\b", r"\bdied\b", r"\bdeath\b",
        r"\bfuneral\b", r"\babus\w*", r"\bviolen\w*", r"\bassault\w*",
    ]), re.I)),
]

#: Someone else is being talked about: a family or other relation, or a
#: capitalised name that is not the first word.
_OTHER_PERSON = re.compile(
    r"\b(?:sister|brother|mum|mom|mother|dad|father|parent|son|daughter|kid|child"
    r"|children|wife|husband|partner|girlfriend|boyfriend|fianc\w*|friend|neighbou?r"
    r"|boss|colleague|coworker|co-worker|manager|cousin|aunt|uncle|niece|nephew"
    r"|grand\w+|in-law|flatmate|roommate|ex)s?\b", re.I)
_NAME = re.compile(r"\b[A-Z][a-z]+'s\b")          # "Dana's", "Mario's"


def sensitivity(text: str) -> str:
    """"" or the topic found, in words: "health", "money", "passwords and
    account details", "private details about someone else" - with "someone
    else's" in front of health or money said about another person."""
    if not isinstance(text, str) or not text.strip():
        return ""
    for topic, rx in _SENSITIVE:
        if rx.search(text):
            if topic in ("health", "money") and (
                    _OTHER_PERSON.search(text) or _NAME.search(text)):
                return f"someone else's {topic}"
            return topic
    try:
        import jarvis_router
        if jarvis_router.looks_like_a_secret(text):
            return "passwords and account details"
    except Exception:
        pass
    return ""


def check_sensitive(fact: str, turns: list, allowed: bool) -> str:
    if allowed:
        return ""
    for t in [fact] + list(turns):
        topic = sensitivity(t)
        if topic:
            return "sensitive: " + topic
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
              " proposal_id INTEGER PRIMARY KEY, reason TEXT, provenance TEXT, at REAL)")


def _note_card(c, pid: int, reason: str, provenance: Optional[str] = None) -> None:
    _init_notes(c)
    c.execute("INSERT OR REPLACE INTO auto_learn_notes (proposal_id, reason, provenance, at)"
              " VALUES (?,?,?,?)", (int(pid), reason, provenance, time.time()))


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
            for pid in pids:
                row = rows.get(pid)
                if row is None or row.get("state") != "pending":
                    continue
                fact = str(row.get("text") or "")
                why = batch or check_source(row.get("source"))
                if not why and row.get("source") != "conversation":
                    why = "not from something you said"
                src = source_turns(fact, texts) if not why else []
                why = (why or check_not_correction(row) or check_instruction(fact)
                       or check_sensitive(fact, src, allowed)
                       or check_grounded(fact, texts))
                decisions[pid] = why
                if why and not off:
                    # No reason is noted while automatic learning is off:
                    # then every proposal is a card, as it always was.
                    _note_card(c, pid, why)
        for pid, why in decisions.items():
            if why:
                result["cards"][pid] = why
                continue
            try:
                fid = _save_fact(pid, _meta("conversation", entries, conversation_id), extract)
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
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


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
    sql = ("SELECT id, text, created, meta FROM facts WHERE source='auto'"
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
    for fid, text, created, meta in rows:
        try:
            m = json.loads(meta or "{}")
            m = m if isinstance(m, dict) else {}
        except Exception:
            m = {}
        prov = m.get("provenance") if m.get("provenance") in ("typed", "voice") else "typed"
        out["facts"].append({"id": int(fid), "text": text, "saved_at": int(created or 0),
                             "provenance": prov, "device": str(m.get("device") or "unknown")})
    return out


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
