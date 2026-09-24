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
  Sensitive   jarvis_sensitive.py on the fact and on the turns it came from:
              word lists in eight languages, number and token shapes, the
              other-person rule, then the learner's own local model. Unless
              "Also remember sensitive topics automatically" is on, a hit is a
              card (L7). When unsure - or when the model does not answer: a hit.

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
NEEDS_LEARNING = ("Learn automatically only works while background learning is on.")


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
                "why": "the automatic learning settings file is damaged, so nothing is "
                       "saved automatically. Turn \"Learn automatically\" off and on "
                       "again to rewrite it"}
    auto = doc.get("auto", True)
    sens = doc.get("auto_sensitive", False)
    why = ""
    if not isinstance(auto, bool):
        auto, why = False, ("the automatic learning setting is damaged, so nothing is "
                            "saved automatically")
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


def _finish(kind: str, pid: str, outcome: str, why: str = "") -> None:
    s = _STATE[kind]
    with _LOCK:
        if s["pending"].get("id") == pid:
            s["pending"].clear()
        s["withdrawn"].discard(pid)
        if s["latest"].get("id") not in (None, pid):
            return
        s["last"].clear()
        s["last"].update(outcome=outcome, why=why, at=time.time())
    _audit(f"learning.{kind}.card", {"outcome": outcome})


def _decide(kind: str, pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    action = action_for(kind)
    text = _card_text(kind)
    try:
        v = gate(action, {"text": text, "what": _what(kind), "leaves_this_pc": False}, text)
    except Exception as exc:
        return _finish(kind, pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
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
        with _LOCK:
            if s["pending"]:
                # Withdrawn AND no longer the waiting card: approving it does
                # nothing, and a later ON raises a fresh card.
                s["withdrawn"].add(s["pending"]["id"])
                s["pending"].clear()
        try:
            apply(False)
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not save the setting ({type(exc).__name__})"}
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
_HIDDEN = re.compile("[\u00ad\u061c\u115f\u1160\u180e\u200b-\u200f\u202a-\u202e"
                     "\u2060-\u2064\u2066-\u206f\u3164\ufeff\ufff9-\ufffb]"
                     "|[\U000e0000-\U000e007f]")
_ENCODED = re.compile(r"[A-Za-z0-9+/=_-]{48,}")
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
    if _LINK.search(text):
        return "it has a link or web-page code in it"
    if _HIDDEN.search(text):
        return "it has hidden characters in it"
    if _ENCODED.search(text):
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


def _injection(text: str) -> bool:
    try:
        import jarvis_intake
        return bool(jarvis_intake.injection_flags(text))
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
    return out


def check_grounded(fact: str, turns: list) -> str:
    """GUARDS L5: every content word and every number of the fact is in
    what the owner said."""
    if not _fact_words(fact):
        return "not in your own words"
    return "not in your own words" if ungrounded(fact, turns) else ""


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
        return jarvis_sensitive.topic(text)
    except Exception:
        return "a topic that could not be checked (jarvis_sensitive.py is missing)"


def check_sensitive(fact: str, turns: list, allowed: bool) -> str:
    """"" when the fact may be saved without a card, else the card's reason:
    "about health, a sensitive topic". `allowed` is the owner's "Also
    remember sensitive topics automatically": on, nothing is checked."""
    if allowed:
        return ""
    try:
        import jarvis_sensitive
    except Exception:
        return "the check for sensitive topics is not installed (jarvis_sensitive.py)"
    return jarvis_sensitive.card_reason(fact, turns)


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
