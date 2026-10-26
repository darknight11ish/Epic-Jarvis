"""jarvis_personality_creator.py - the owner makes a personality by talking.

NEW MODULE, shipped whole. `jarvis_quick.py` calls `handle()` from the
`/api/chat` fast path, before its own English grammar, so a sentence like

    "make me a personality like a grumpy but caring mechanic"

is answered by THIS PC instead of the general model. The LOCAL model is asked
exactly once to draft the fields, the owner sees the draft in the conversation,
refines it in their own words, and says "save it". The saved row is the same
"My personalities" entry the Settings form writes: `jarvis_manner.py`'s
`save_user_personality()` validates it, caps it, scrubs it and stores it in
`manner.json`, and "switch to <name>" already finds a saved personality by
name. Nothing new is stored on disk beyond the draft file described below: the
one "tell me what it should be like" question is remembered in memory only, for
that conversation's next message.

WHY FIELDS AND NOT A FINISHED PROMPT (the one design decision that matters)

`contract/personalities.json` and the shipped copy it feeds were built so a
personality is a small number of NAMED fields - a line about how to talk, one
example exchange, dials, a base preset - and the PC assembles the prompt from
them (`jarvis_manner.prompt_block()`, 750-character budget). This module keeps
that shape deliberately: the model drafts FIELDS, never a finished system
prompt, and the same caps the Settings form enforces are applied here. A
personality therefore cannot smuggle in an instruction about tools, approval,
permissions, memory or safety: only the four text fields are read, each is
capped, and the row is validated a second time by `save_user_personality()`.
The research for this slice (`.dsh-scratch/PERSONALITY-2026-10-25/
RESEARCH-web.md`) found that the popular character-card formats do the
opposite - the card's own `system_prompt` REPLACES the host's - which is the
one thing this project must never copy.

WHAT IT MAY NOT DO

  * no new route, no approval card, no permission tier: a personality changes
    wording only, exactly like the Settings form and "switch to Classic
    Butler" (all cardless by the owner's 2026-10-22 decision). Saving happens
    through the same function those already use;
  * it never leaves this PC: the address is the chat lane's own, resolved by
    `jarvis_model_lanes._hud_ollama_url()` (never a copy kept here), and
    `_loopback_url()` refuses to use any host that is not loopback, so this
    module cannot be pointed at another machine by an environment variable;
  * the model's reply is data, not instructions. Only a JSON object is read
    from it, field by field; if the model answers with prose, an error, or
    nothing, NOTHING is drafted or saved and the owner is told plainly;
  * a temporary chat is refused: a temporary chat remembers nothing, and a
    saved personality is permanent, so the two do not belong together.

CAPS (the same numbers the Settings form uses)

name 60, the line 240, each half of the example 240, at most 20 saved
personalities, base preset one of the nine built-ins. The draft is asked for
SHORTER than the caps on purpose (line ~150, example ~60/90): the persona block
has a 750-character budget and, measured on this engine, a 240-character line
already pushes a full block over it and silently drops the two cadence
example exchanges (`jarvis_manner.prompt_block()`). A draft that fits keeps its
examples.

STATE

`<config>/personality-drafts.json` (beside `manner.json`): one pending draft per
conversation, at most MAX_DRAFTS at once, each expires after DRAFT_TTL_S. A
draft is written only by the owner's own sentence, contains only the fields the
owner was shown, and is removed the moment it is saved, dropped or expired.
The saved personality itself lives in `manner.json`, not here.

The unanswered "tell me what it should be like" question is MEMORY ONLY: one per
conversation, at most MAX_PENDING_BRIEFS at once, forgotten after BRIEF_TTL_S,
gone on restart, and never written to disk. The next message in that
conversation is read as the brief the owner was asked for - so the sentence the
question invites ("a grumpy mechanic") drafts a personality instead of
dead-ending at the general model - unless it is a question or a new creation
sentence, which clears the question. This is one turn of state, not a draft: it
belongs to a conversation id, and a conversation without a real id never
remembers it.

Standard library only. No module is imported at import time except the
standard library; `jarvis_manner`, `jarvis_model_lanes`, `jarvis_hud`,
`jarvis_models` and `jarvis_chatbot` are imported inside the functions that need
them, wrapped, so a backend without one of them still answers (with the named
fallbacks) rather than failing to load.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

#: The LAST-RESORT loopback address, used only when neither `jarvis_hud` nor the
#: environment can say which lane the chat is on. The lane itself is never
#: copied here: `_hud_lane_url()` asks `jarvis_model_lanes._hud_ollama_url()`,
#: the one resolver that reads `jarvis_hud.OLLAMA_URL`/`OLLAMA_URL` - a separate
#: copy of that address is exactly how the desktop's health probe came to ask
#: the wrong port (jarvis_model_lanes.py:333-348, 2026-10-13).
DEFAULT_URL = "http://127.0.0.1:11434"

#: The context the chat's own model is loaded at, named so asking cannot reload
#: it at Ollama's small default. `jarvis_chatbot.ONE_CARD_NUM_CTX` is this
#: repository's name for the value ("the SAME context size as chat
#: (jarvis-primary.Modelfile's num_ctx), so asking never makes Ollama reload the
#: model at another size", jarvis_chatbot.py:201-204); `jarvis-primary.Modelfile`
#: line 119 sets it, and on this PC `/api/ps` reported jarvis-primary:latest at
#: `context_length: 16384` on 2026-10-25. `_num_ctx()` prefers the module's
#: constant and falls back to this named value when jarvis_chatbot is absent.
CHAT_NUM_CTX = 16384

#: Hosts that mean "this PC". Anything else is not used: this module's whole
#: point is that the owner's own description stays on the machine.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})

#: The model name the draft asks for when NOTHING else can say - the chat's own
#: default (`jarvis_chatbot.MAIN_MODEL_DEFAULT`), kept here as a literal so this
#: module never imports the chatbot just to read a name. qwen3.5:9b used to be
#: this fallback, and that was the wrong answer: it is a DIFFERENT base model
#: (also pulled on this PC), while the CHAT lane runs jarvis-primary:latest -
#: measured 2026-10-25, `GET http://127.0.0.1:11436/api/ps` reported
#: `jarvis-primary:latest` with `context_length: 16384`. Asking qwen3.5:9b
#: loads a second model and evicts the chat's own from the card, which
#: `options.num_ctx` alone cannot prevent; asking the chat's own NAME can.
DEFAULT_MODEL = "jarvis-primary"

#: The draft file, beside manner.json in the config folder.
DRAFT_FILE = "personality-drafts.json"

#: A draft is a suggestion waiting for one answer; it is not a setting. Two
#: hours is long enough to think, short enough that a forgotten one cannot
#: surprise the owner next week.
DRAFT_TTL_S = 2 * 60 * 60

#: At most this many conversations can have a pending draft at once. The owner
#: is one person; this is a bound, not a feature.
MAX_DRAFTS = 6

#: A brief question ("tell me what it should be like") is remembered for this
#: long. Long enough to read the question and type a line, short enough that a
#: forgotten one cannot catch a message sent much later. It is memory only.
BRIEF_TTL_S = 10 * 60

#: At most this many conversations can hold an unanswered brief question at
#: once - the same bound, and the same reason, as MAX_DRAFTS.
MAX_PENDING_BRIEFS = 6

#: The owner's own description of what they want. Long enough for a paragraph,
#: short enough to stay a description rather than a document.
MAX_BRIEF_CHARS = 600

#: How long the LOCAL model may take to answer. A draft is one small object.
ASK_TIMEOUT_S = 90.0

#: What the model is asked for. Shorter than the caps on purpose (see the
#: module docstring): the persona block has room for a short line plus the
#: preset's two cadence examples, and that is the shape that works.
WANT_LINE = 150
WANT_EXAMPLE_USER = 60
WANT_EXAMPLE_JARVIS = 90
WANT_NAME = 40

#: The nine built-ins this module may start from, in the contract's own order.
#: Frozen here as a fallback so the module still runs where jarvis_manner is
#: absent; the suite asserts this list equals the engine's own built-ins, so
#: drift fails a test instead of surprising the owner.
BUILTIN_IDS = (
    "warm_peer", "classic_butler", "tactical_ops", "dry_wit", "friday_partner",
    "socratic_mentor", "devils_advocate", "calm_stoic", "advocate",
)

#: What a follow-up may change a draft to. Same values the Settings form sends.
DIAL_VALUES = {
    "humor": (0, 1, 2, 3),
    "brevity": ("concise", "balanced", "thorough"),
    "formality": ("casual", "warm_peer", "formal_butler", "tactical"),
    "address": ("first_name", "sir", "ma'am", "boss", "captain", "none"),
}

ASK_BRIEF = ("Tell me what it should be like - one line is enough, for example "
             "\"a grumpy but caring mechanic who explains with car analogies\".")

CANNOT_DRAFT = ("I could not draft that just now - the local model did not answer, "
                "or its answer did not fit the personality fields. Nothing was saved. "
                "Try again, or add it by hand in Settings -> How Jarvis talks.")

TEMPORARY_REFUSAL = ("I don't build personalities in a temporary chat - nothing is "
                     "kept there, and a saved personality is kept for good. Ask me "
                     "again in a normal chat.")

# --------------------------------------------------------------------------
#   The sentences this module answers
# --------------------------------------------------------------------------

#: "make me a personality ...", "I want a new personality ...". The words after
#: the verb are the owner's description. Deliberately narrow: the word
#: "personality" must be in the sentence, so "make me a sandwich" is untouched.
_CREATE = (
    re.compile(r"(?i)^(?:please\s+)?(?:can|could|would|will)\s+you\s+"
               r"(?:make|create|build|design|invent|draft)\s+(?:me\s+)?"
               r"(?:a|an|my\s+own|another)?\s*(?:new\s+)?personalit(?:y|ies)\b(?P<brief>.*)$"),
    re.compile(r"(?i)^(?:please\s+)?(?:make|create|build|design|invent|draft)\s+(?:me\s+)?"
               r"(?:a|an|my\s+own|another)?\s*(?:new\s+)?personalit(?:y|ies)\b(?P<brief>.*)$"),
    re.compile(r"(?i)^(?:please\s+)?(?:i\s+want|i'd\s+like|i\s+would\s+like|let's\s+(?:make|create|build|design))\s+"
               r"(?:a|an|my\s+own|another)?\s*(?:new\s+)?personalit(?:y|ies)\b(?P<brief>.*)$"),
)

#: Only tried while a draft is pending for this conversation. Order matters:
#: save/cancel/show are whole-sentence answers; the rest are edits.
_SAVE = re.compile(r"(?i)^(?:please\s+)?(?:save|keep|store)\s+(?:it|that|this)"
                   r"(?:\s+as\s+(?P<name>.+))?$")
_CANCEL = re.compile(r"(?i)^(?:please\s+)?(?:forget|discard|scrap|cancel|drop)\s+"
                     r"(?:it|this\s+personality|that\s+personality|the\s+personality)$")
_SHOW = re.compile(r"(?i)^(?:show|see|read)\s+(?:it|that|the\s+personality)\s+again$"
                   r"|^(?:what|what's)\s+(?:the|my)\s+draft\??$")
_RENAME = re.compile(r"(?i)^(?:call|name)\s+it\s+(?P<name>.+)$")
_REBASE = re.compile(r"(?i)^(?:base|start)\s+(?:it\s+)?(?:on|from)\s+(?P<base>.+)$")
_EDIT_VERB = re.compile(r"(?i)^(?:make|change|adjust|tweak|edit|update|turn|give)\b(?P<rest>.*)$")
_EDIT_SHORT = re.compile(r"(?i)^(?:shorter|longer|plainer|warmer|cooler|funnier|"
                         r"more\s+\w+|less\s+\w+|no\s+humou?r)\b(?P<rest>.*)$")

#: Lead-ins that are not part of the description itself.
_LEAD = re.compile(r"(?i)^(?:it|one|something|a\s+personality|that|which|who)\s+"
                   r"(?:that|which|who|is|should|sounds|sounding)\b\s*", re.I)
_LEAD_SIMPLE = re.compile(r"(?i)^(?:like|such\s+as)\b\s*", re.I)
_TRAILING_PUNCT = " \t\r\n.!?,;:"

#: A message that is a question or another quick command is NOT the brief an
#: unanswered "tell me what it should be like" asked for: it clears the question
#: and falls through, so "what's the weather?" is never drafted as a personality.
#: Deliberately narrow - a description does not have to start with a noun, so
#: "sounds like a tired engineer" and "more formal" are still read as briefs.
_OTHER_REQUEST = re.compile(
    r"(?i)^(?:what(?:'s)?|who(?:'s)?|when|where|why|how|which|"
    r"is|are|am|do|does|did|can|could|would|will|should|may|might|"
    r"remind|schedule|set|switch|turn|open|close|play|stop|start|"
    r"delete|remove|list|search|find|check|email|text|message|call|"
    r"remember|cancel|forget|discard|scrap|drop|save|keep|store|show|tell)\b")


def _is_other_request(text: str) -> bool:
    """Is this plainly about something else, rather than a personality brief?

    Used only for the one message after the brief question. Anything that is
    not caught here is passed to the model as the brief, which is the point of
    remembering the question at all.
    """
    return bool(_OTHER_REQUEST.match(text))


_LOCK = None


def _lock():
    """One process-wide lock for the draft file, made on first use."""
    global _LOCK
    if _LOCK is None:
        import threading
        _LOCK = threading.Lock()
    return _LOCK


#: conversation key -> when the "tell me what it should be like" question was
#: asked. MEMORY ONLY on purpose: it is one turn of state, not a draft. A
#: restart forgets it, and nothing in this module ever writes it to disk.
_PENDING_BRIEFS = {}
_BRIEF_LOCK = threading.Lock()


# --------------------------------------------------------------------------
#   The local model, and the one seam the suite replaces
# --------------------------------------------------------------------------

def _hud_lane_url() -> str:
    """The address the CHAT talks to, from the one resolver that owns it.

    `jarvis_model_lanes._hud_ollama_url()` reads `jarvis_hud.OLLAMA_URL`
    (the backend's own line, 11436 on the owner's PC) and only then the
    environment's `OLLAMA_URL`; it exists precisely because a second copy of
    the address asked the wrong port (jarvis_model_lanes.py:333-348). So this
    module asks it instead of keeping a port of its own.

    The environment fallback is for a backend without that module, and reads
    the SAME variable `_hud_ollama_url()` would - never `OLLAMA_HOST`.
    `OLLAMA_HOST` is Ollama's own variable, it is unset on the owner's PC, and
    reading it here is what made the draft ask 11434 while the chat used 11436
    (2026-10-25). "" when nothing can say; the caller then uses DEFAULT_URL.
    """
    try:
        import jarvis_model_lanes
        lane = jarvis_model_lanes._hud_ollama_url()
        if lane:
            return str(lane)
    except Exception:                                          # noqa: BLE001
        pass
    return os.environ.get("OLLAMA_URL") or ""


def _loopback_url(url: Optional[str] = None) -> str:
    """`url`, or the CHAT lane, or the loopback default - and the default if
    the host is not loopback.

    A remote host is never refused with an exception: it simply is not used.
    Nothing in this module can be pointed at another machine by an environment
    variable. (Same loopback rule as jarvis_self_improve._loopback_url, but the
    candidate list is the chat's own, not Ollama's `OLLAMA_HOST`.)
    """
    for candidate in (url, _hud_lane_url(), DEFAULT_URL):
        text = (candidate or "").strip()
        if not text:
            continue
        host = text.split("://", 1)[-1].split("/", 1)[0]
        if host.startswith("["):
            host = host[1:].split("]", 1)[0]
        else:
            host = host.split(":", 1)[0]
        if host.lower() in LOOPBACK_HOSTS:
            return text.rstrip("/")
    return DEFAULT_URL


def _num_ctx() -> int:
    """The context size the chat's model is loaded at - never Ollama's default.

    `options.num_ctx` is always named. A `POST /api/generate` that names a model
    and no `num_ctx` loads that model at Ollama's OWN default (2,048 when it was
    measured on 2026-10-10/11) rather than the lane's - the accident that
    reloaded a 196,608-token window at `-c 2048` twice and shrank it 96x
    (jarvis_agent.py:7923-7935; the same rule jarvis_self_improve.py:729-735
    names a floor for). Here the number is not a floor: it is EXACTLY the
    context chat runs the model at, so a draft cannot make Ollama reload it at
    another size. On this PC that is 16,384 - `/api/ps` reported
    `jarvis-primary:latest` with `context_length: 16384` on 2026-10-25, and
    jarvis_chatbot.py:201-204 names the same value for the same reason.

    `jarvis_chatbot` is asked at call time (the module imports only the
    standard library at import time); CHAT_NUM_CTX is the named fallback for a
    backend without it, not a second live value.
    """
    try:
        import jarvis_chatbot
        value = int(getattr(jarvis_chatbot, "ONE_CARD_NUM_CTX", 0) or 0)
        if value > 0:
            return value
    except Exception:                                          # noqa: BLE001
        pass
    return CHAT_NUM_CTX


def _model_name(model: Optional[str] = None) -> str:
    """The model NAME the CHAT lane is running - from the resolver that owns it.

    The order, and why it is this order:

      1. an explicit `model` argument (the caller's choice, and the test seam);
      2. `JARVIS_PERSONALITY_MODEL` - a deliberate override for this feature;
      3. `jarvis_hud._extract_model()` - the CHAT's own resolver, asked the same
         way `_hud_lane_url()` asks `jarvis_model_lanes._hud_ollama_url()`: the
         module that owns the answer gives it, and no copy is kept here;
      4. `JARVIS_LOCAL_MODEL`, the variable `_extract_model()` reads first;
      5. `jarvis_models.current_model()` - the model switched from the HUD;
      6. `jarvis_chatbot.MAIN_MODEL_DEFAULT` - the chat's own default;
      7. `JARVIS_MODEL`, kept for an environment that already set it;
      8. `DEFAULT_MODEL`, the named last-resort fallback ("jarvis-primary").

    A SECOND NAME HERE IS NOT HARMLESS. `options.num_ctx` cannot stop a
    `POST /api/generate` that names another model from loading it: the request
    loads the model it names and evicts the chat's own from the card, so the
    next chat turn reloads it (the accident `jarvis_hud._extract_model`'s own
    docstring describes). qwen3.5:9b is a real base model and is pulled on this
    PC, so the old fallback would have won silently - the CHAT lane runs
    jarvis-primary:latest (`/api/ps`, 2026-10-25). Ask the chat's name.
    """
    explicit = str(model or "").strip()
    if explicit:
        return explicit
    override = str(os.environ.get("JARVIS_PERSONALITY_MODEL") or "").strip()
    if override:
        return override
    try:
        import jarvis_hud
        resolver = getattr(jarvis_hud, "_extract_model", None)
        if callable(resolver):
            name = str(resolver() or "").strip()
            if name:
                return name
    except Exception:                                          # noqa: BLE001
        pass
    local = str(os.environ.get("JARVIS_LOCAL_MODEL") or "").strip()
    if local:
        return local
    try:
        import jarvis_models
        name = str(jarvis_models.current_model() or "").strip()
        if name:
            return name
    except Exception:                                          # noqa: BLE001
        pass
    try:
        import jarvis_chatbot
        name = str(getattr(jarvis_chatbot, "MAIN_MODEL_DEFAULT", "") or "").strip()
        if name:
            return name
    except Exception:                                          # noqa: BLE001
        pass
    return str(os.environ.get("JARVIS_MODEL") or "").strip() or DEFAULT_MODEL


def _ask(prompt: str, *, model: Optional[str] = None, url: Optional[str] = None,
         timeout: float = ASK_TIMEOUT_S) -> str:
    """Ask the LOCAL model. The reply, or "" - never raises, never remote.

    THIS IS THE SEAM. The suite passes its own `ask=` to `handle()` (or
    replaces this function), so no test needs a running Ollama.
    """
    where = _loopback_url(url)
    body = json.dumps({
        "model": _model_name(model),
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": _num_ctx(), "temperature": 0.8,
                    "num_predict": 320},
    }).encode("utf-8")
    try:
        request = urllib.request.Request(
            f"{where}/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            payload = json.loads(answer.read().decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("response") or "")


# --------------------------------------------------------------------------
#   Reading the model's answer: fields, never instructions
# --------------------------------------------------------------------------

def _one_line(value, cap: int) -> str:
    """One plain line from whatever the model sent, capped. No newlines: a
    multi-line answer would break the reply the owner reads and the field the
    saved row holds. Whitespace is collapsed, never invented."""
    text = " ".join(str(value or "").replace("\u201c", '"').replace("\u201d", '"').split())
    text = text.strip(_TRAILING_PUNCT)
    return text[:cap].strip(_TRAILING_PUNCT)


def _json_object(reply: str) -> Optional[dict]:
    """The first JSON object in `reply`, or None.

    Models wrap JSON in a fenced block or a sentence despite being asked not
    to, so the braces are found rather than assuming a clean string. A reply
    with no object, or one that does not parse, is None - never guessed.
    """
    if not isinstance(reply, str) or not reply.strip():
        return None
    text = reply.strip()
    fence = text.find("```")
    if fence != -1:
        end = text.find("```", fence + 3)
        block = text[fence + 3:end if end != -1 else len(text)]
        block = re.sub(r"^[A-Za-z]+\s*\n", "", block.strip())
        text = block
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for pos in range(start, len(text)):
            ch = text[pos]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        got = json.loads(text[start:pos + 1])
                    except Exception:                          # noqa: BLE001
                        break
                    return got if isinstance(got, dict) else None
        start = text.find("{", start + 1)
    return None


def _builtin_ids() -> tuple:
    """The engine's own built-in ids, in contract order; the frozen list when
    jarvis_manner is not importable."""
    try:
        import jarvis_manner
        rows = jarvis_manner.all_personalities()
        builtin = [str(r.get("id")) for r in rows
                   if isinstance(r, dict) and r.get("builtin") in (True, None)
                   and r.get("id")]
        if len(builtin) >= len(BUILTIN_IDS):
            return tuple(builtin)
    except Exception:                                          # noqa: BLE001
        pass
    return BUILTIN_IDS


def _normalize_base(value) -> Optional[str]:
    """A built-in preset id from an id, a title or an alias - or None."""
    text = _one_line(value, 60)
    if not text:
        return None
    try:
        import jarvis_manner
        pid = jarvis_manner.normalize_personality_id(text)
        if pid and pid in _builtin_ids():
            return pid
    except Exception:                                          # noqa: BLE001
        pass
    plain = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    for pid in _builtin_ids():
        if plain in (pid.replace("_", " "), pid.replace("_", "-")):
            return pid
    return None


def _clean_draft(raw: dict, *, base_fallback: Optional[str] = None) -> Optional[dict]:
    """The four fields the owner is shown, cleaned and capped - or None when
    the model's answer cannot become a personality at all.

    Only these keys are read from the model's object. Anything else it wrote
    (a whole system prompt, a safety claim, an instruction) is discarded, and
    the saved row is validated again by jarvis_manner.save_user_personality().
    """
    if not isinstance(raw, dict):
        return None
    name = _one_line(raw.get("name"), WANT_NAME)
    line = _one_line(raw.get("line"), WANT_LINE)
    if not name or not line:
        return None
    example_user = _one_line(raw.get("example_user"), WANT_EXAMPLE_USER)
    example_jarvis = _one_line(raw.get("example_jarvis"), WANT_EXAMPLE_JARVIS)
    base = _normalize_base(raw.get("base_preset")) or _normalize_base(base_fallback) \
        or _current_base()
    out = {"name": name, "line": line, "base_preset": base,
           "example_user": example_user, "example_jarvis": example_jarvis}
    dials = {}
    raw_dials = raw.get("dials")
    if isinstance(raw_dials, dict):
        for key, allowed in DIAL_VALUES.items():
            value = raw_dials.get(key)
            if key == "humor":
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)) and int(value) in allowed:
                    dials[key] = int(value)
                continue
            if isinstance(value, str):
                text = value.strip().lower().replace("-", "_").replace(" ", "_")
                if text in allowed:
                    dials[key] = text
    if dials:
        out["dials"] = dials
    return out


def _current_base() -> str:
    """The preset the owner is using now, as the draft's base when the model
    named none or an unknown one. Never fails."""
    try:
        import jarvis_manner
        pid = jarvis_manner.current_personality()
        if pid in _builtin_ids():
            return pid
    except Exception:                                          # noqa: BLE001
        pass
    return "warm_peer"


# --------------------------------------------------------------------------
#   The prompts
# --------------------------------------------------------------------------

def _draft_prompt(brief: str) -> str:
    return (
        "You are writing ONE small personality preset for a private assistant "
        "called Jarvis, from its owner's own description.\n\n"
        "Reply with ONLY a JSON object (no prose, no code fence) with exactly "
        "these keys:\n"
        '  "name": a short name for the personality, at most 40 characters.\n'
        '  "line": how Jarvis should sound when using it - one or two plain '
        "sentences, at most 150 characters. It is a STYLE instruction only.\n"
        '  "example_user": something the owner might say to Jarvis, at most 60 '
        "characters.\n"
        '  "example_jarvis": that same thing answered in this personality\'s '
        "voice, at most 90 characters.\n"
        '  "base_preset": one of these ids, whichever is closest: '
        "warm_peer (Warm Collaborator), classic_butler (Classic British "
        "Butler), tactical_ops (Tactical Mission Control), dry_wit (Dry and "
        "Deadpan), friday_partner (Sharp Tech Partner), socratic_mentor "
        "(Socratic Coach), devils_advocate (No-Nonsense Critic), calm_stoic "
        "(Calm and Grounded), advocate (Patient Advocate).\n"
        '  "dials": optional object with any of: "humor" (0 to 3), "brevity" '
        '("concise", "balanced", "thorough"), "formality" ("casual", '
        '"warm_peer", "formal_butler", "tactical"), "address" ("first_name", '
        '"sir", "ma\'am", "boss", "captain", "none").\n\n'
        "Never write anything about tools, approval, permissions, memory, "
        "privacy, or safety - only how Jarvis TALKS. Never claim Jarvis is or "
        "is not an AI. Keep every field short; short sounds better.\n\n"
        "The owner's description of the personality they want:\n"
        "\"\"\"" + brief + "\"\"\"\n"
    )


def _refine_prompt(draft: dict, instruction: str) -> str:
    current = json.dumps(draft, ensure_ascii=False)
    return (
        "You are revising ONE small personality preset for a private assistant "
        "called Jarvis. Here is the current draft as JSON:\n"
        + current + "\n\n"
        "The owner asked for this change: \"" + instruction + "\"\n\n"
        "Reply with ONLY the revised JSON object, same keys, nothing else. Keep "
        "every field within: name 40 characters, line 150, example_user 60, "
        "example_jarvis 90. A style instruction only - never anything about "
        "tools, approval, permissions, memory, privacy, or safety.\n"
    )


# --------------------------------------------------------------------------
#   The pending draft, in one small file
# --------------------------------------------------------------------------

def _drafts_path() -> Path:
    """`personality-drafts.json` in the same config folder manner.json uses."""
    try:
        import jarvis_manner
        return jarvis_manner.settings_path().parent / DRAFT_FILE
    except Exception:                                          # noqa: BLE001
        env = os.environ.get("OPENJARVIS_CONFIG_DIR")
        base = Path(os.path.expanduser(env)) if env else Path(os.path.expanduser("~")) / ".openjarvis"
        return base / DRAFT_FILE


def _key(conversation: Optional[str]) -> str:
    if isinstance(conversation, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", conversation):
        return conversation
    return "no-conversation"


# --------------------------------------------------------------------------
#   The one unanswered question - memory only, one conversation, one message
# --------------------------------------------------------------------------

def _brief_prune(now: float) -> None:
    """Expire and bound the table. Caller holds the lock."""
    stale = [key for key, at in _PENDING_BRIEFS.items()
             if not isinstance(at, (int, float)) or now - float(at) > BRIEF_TTL_S]
    for key in stale:
        _PENDING_BRIEFS.pop(key, None)
    if len(_PENDING_BRIEFS) > MAX_PENDING_BRIEFS:
        keep = sorted(_PENDING_BRIEFS.items(), key=lambda kv: float(kv[1]))[-MAX_PENDING_BRIEFS:]
        _PENDING_BRIEFS.clear()
        _PENDING_BRIEFS.update(keep)


def _brief_put(key: str, now: float) -> None:
    """Remember that this conversation was just asked for a brief.

    A conversation with no real id is NOT remembered: "the same conversation" is
    exactly the guarantee this makes, and the shared "no-conversation" bucket
    could be a different chat. It simply asks again instead.
    """
    if key == "no-conversation":
        return
    with _BRIEF_LOCK:
        _PENDING_BRIEFS[key] = now
        _brief_prune(now)


def _brief_take(key: str, now: float):
    """The time this conversation's question was asked, and forget it - or None.

    Popping it is the whole usage rule: one question is answered by exactly one
    message, whatever happens to that message.
    """
    with _BRIEF_LOCK:
        _brief_prune(now)
        return _PENDING_BRIEFS.pop(key, None)


def _brief_drop(key: str) -> None:
    """Forget this conversation's question without answering it."""
    with _BRIEF_LOCK:
        _PENDING_BRIEFS.pop(key, None)


def _brief_clear() -> None:
    """Forget every pending question. The suite calls this between tests; a
    restart does the same thing, because the table is memory only."""
    with _BRIEF_LOCK:
        _PENDING_BRIEFS.clear()


def _read_all() -> dict:
    try:
        doc = json.loads(_drafts_path().read_text(encoding="utf-8"))
        drafts = doc.get("drafts") if isinstance(doc, dict) else None
        return drafts if isinstance(drafts, dict) else {}
    except Exception:                                          # noqa: BLE001
        return {}


def _prune(drafts: dict, now: float) -> dict:
    fresh = {}
    for key, entry in drafts.items():
        if not isinstance(entry, dict):
            continue
        at = entry.get("at")
        if not isinstance(at, (int, float)) or now - float(at) > DRAFT_TTL_S:
            continue
        if not isinstance(entry.get("draft"), dict):
            continue
        fresh[str(key)] = entry
    if len(fresh) > MAX_DRAFTS:
        keep = sorted(fresh.items(), key=lambda kv: float(kv[1].get("at") or 0))[-MAX_DRAFTS:]
        fresh = dict(keep)
    return fresh


def _write_all(drafts: dict) -> bool:
    with _lock():
        try:
            path = _drafts_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps({"version": 1, "drafts": drafts},
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
            return True
        except Exception:                                      # noqa: BLE001
            return False


def _get(key: str, now: float) -> Optional[dict]:
    entry = _read_all().get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("draft"), dict):
        return None
    at = entry.get("at")
    if not isinstance(at, (int, float)) or now - float(at) > DRAFT_TTL_S:
        return None
    return entry


def _put(key: str, draft: dict, brief: str, now: float) -> None:
    drafts = _prune(_read_all(), now)
    drafts[key] = {"at": now, "brief": brief, "draft": draft}
    _write_all(_prune(drafts, now))


def _drop(key: str) -> None:
    drafts = _read_all()
    if key in drafts:
        drafts.pop(key, None)
        _write_all(drafts)


def pending(conversation: Optional[str] = None, *, now: Optional[float] = None) -> bool:
    """Is there a draft waiting for this conversation? Cheap: one small read."""
    now = time.time() if now is None else now
    return _get(_key(conversation), now) is not None


# --------------------------------------------------------------------------
#   The replies the owner reads
# --------------------------------------------------------------------------

def _base_title(pid: str) -> str:
    try:
        import jarvis_manner
        row = jarvis_manner.preset(pid)
        if isinstance(row, dict) and row.get("title"):
            return str(row["title"])
    except Exception:                                          # noqa: BLE001
        pass
    return pid.replace("_", " ")


def _render(draft: dict, *, opening: str) -> str:
    """The whole draft on screen, plus the two words that finish it."""
    lines = [opening]
    lines.append(f"- Name: {draft['name']}")
    lines.append(f"- Sounds like: {draft['line']}")
    if draft.get("example_user") or draft.get("example_jarvis"):
        lines.append(f"- Example - you: \"{draft.get('example_user', '')}\"")
        lines.append(f"  Jarvis: \"{draft.get('example_jarvis', '')}\"")
    lines.append(f"- Starts from: {_base_title(str(draft['base_preset']))}")
    lines.append('Say "save it" to keep it, or tell me what to change.')
    return "\n".join(lines)


def _reply(text: str, intent: str) -> dict:
    return {"reply": text, "intent": intent}


# --------------------------------------------------------------------------
#   Creating, refining, saving
# --------------------------------------------------------------------------

def _create_brief(text: str) -> Optional[str]:
    for rx in _CREATE:
        match = rx.match(text)
        if not match:
            continue
        brief = match.group("brief") or ""
        brief = re.sub(r"^[\s,:;\-\u2013\u2014]+", "", brief)
        brief = _LEAD.sub("", brief, count=1)
        brief = _LEAD_SIMPLE.sub("", brief, count=1)
        return brief.strip(_TRAILING_PUNCT).strip()
    return None


def create(brief: str, *, conversation: Optional[str] = None,
           ask: Optional[Callable[[str], str]] = None,
           now: Optional[float] = None) -> dict:
    """Draft a personality from the owner's own description. Never saves it.

    With no description it asks for one AND remembers the question in memory
    for this conversation, so the next line the owner sends is read as the brief
    by `handle()` instead of dead-ending at the general model. Nothing is
    written to disk for that question.
    """
    now = time.time() if now is None else now
    key = _key(conversation)
    brief = " ".join(str(brief or "").split())[:MAX_BRIEF_CHARS]
    if len(brief) < 3:
        _brief_put(key, now)
        return _reply(ASK_BRIEF, "personality_create_help")
    _brief_drop(key)
    ask_fn = ask or _ask
    try:
        raw = ask_fn(_draft_prompt(brief))
    except Exception:                                          # noqa: BLE001
        raw = ""
    draft = _clean_draft(_json_object(raw) or {})
    if draft is None:
        return _reply(CANNOT_DRAFT, "personality_create_failed")
    _put(key, draft, brief, now)
    return _reply(_render(draft, opening="Here's the personality I'd save:"),
                  "personality_create")


def _refine(draft: dict, instruction: str,
            ask: Optional[Callable[[str], str]]) -> Optional[dict]:
    ask_fn = ask or _ask
    try:
        raw = ask_fn(_refine_prompt(draft, instruction[:MAX_BRIEF_CHARS]))
    except Exception:                                          # noqa: BLE001
        return None
    revised = _clean_draft(_json_object(raw) or {}, base_fallback=draft.get("base_preset"))
    return revised


def save(conversation: Optional[str] = None, *, now: Optional[float] = None,
         name: Optional[str] = None) -> dict:
    """Save the pending draft through jarvis_manner's own validation."""
    now = time.time() if now is None else now
    key = _key(conversation)
    entry = _get(key, now)
    if entry is None:
        return _reply("There is no personality draft waiting. Say \"make me a "
                      "personality ...\" to start one.", "personality_save_missing")
    draft = dict(entry["draft"])
    if name:
        clean = _one_line(name, 40)
        if clean:
            draft["name"] = clean
    spec = {"name": draft.get("name"),
            "base_preset": draft.get("base_preset"),
            "custom_trait": draft.get("line"),
            "example_user": draft.get("example_user"),
            "example_jarvis": draft.get("example_jarvis")}
    if isinstance(draft.get("dials"), dict):
        spec["dials"] = draft["dials"]
    try:
        import jarvis_manner
        ok, got = jarvis_manner.save_user_personality(spec)
    except Exception:                                          # noqa: BLE001
        return _reply("I could not save that just now - the personality system is "
                      "not available on this PC. Nothing was changed.",
                      "personality_save_failed")
    if not ok:
        return _reply(str(got), "personality_save_failed")
    saved_name = str((got or {}).get("name") or draft.get("name")) if isinstance(got, dict) \
        else str(draft.get("name"))
    _drop(key)
    return _reply(
        f'Saved "{saved_name}". Say "switch to {saved_name}" when you want it - '
        "or pick it in Settings -> How Jarvis talks under My personalities.",
        "personality_save")


def cancel(conversation: Optional[str] = None, *, now: Optional[float] = None) -> dict:
    _drop(_key(conversation))
    return _reply("Dropped the draft - nothing was saved.", "personality_cancel")


def show(conversation: Optional[str] = None, *, now: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    entry = _get(_key(conversation), now)
    if entry is None:
        return _reply("There is no personality draft waiting. Say \"make me a "
                      "personality ...\" to start one.", "personality_show_missing")
    return _reply(_render(entry["draft"], opening="Here's the draft so far:"),
                  "personality_show")


def _handle_followup(text: str, key: str, now: float,
                     ask: Optional[Callable[[str], str]]) -> Optional[dict]:
    """A whole-sentence answer or an edit, only while a draft is pending."""
    entry = _get(key, now)
    if entry is None:
        return None
    draft = entry["draft"]

    if _SAVE.match(text):
        match = _SAVE.match(text)
        return save(key, now=now, name=(match.group("name") if match else None))
    if _CANCEL.match(text):
        return cancel(key)
    if _SHOW.match(text):
        return show(key)

    rename = _RENAME.match(text)
    if rename:
        clean = _one_line(rename.group("name"), 40)
        if not clean:
            return _reply("Give it a name I can use.", "personality_refine")
        draft = dict(draft, name=clean)
        _put(key, draft, entry.get("brief") or "", now)
        return _reply(_render(draft, opening="Done - here's the draft:"),
                      "personality_refine")

    rebase = _REBASE.match(text)
    if rebase:
        pid = _normalize_base(rebase.group("base"))
        if pid is None:
            titles = ", ".join(_base_title(p) for p in _builtin_ids())
            return _reply(f"I could not tell which preset that is. Pick one of: {titles}.",
                          "personality_refine")
        draft = dict(draft, base_preset=pid)
        note = ""
        if draft.get("dials"):
            note = " I kept your dials; say \"reset the dials\" to clear them."
        _put(key, draft, entry.get("brief") or "", now)
        return _reply(_render(draft, opening="Done" + note + " - here's the draft:"),
                      "personality_refine")

    instruction = None
    match = _EDIT_VERB.match(text)
    if match:
        tail = (match.group("rest") or "").strip()
        # "make it shorter" keeps the verb's meaning; the whole sentence is
        # the instruction either way.
        instruction = text
    elif _EDIT_SHORT.match(text):
        instruction = text
    if instruction is None:
        return None
    revised = _refine(draft, instruction, ask)
    if revised is None:
        return _reply("I could not revise that just now - the local model did not "
                      "answer. The draft is unchanged.", "personality_refine_failed")
    _put(key, revised, entry.get("brief") or "", now)
    return _reply(_render(revised, opening="Updated:"), "personality_refine")


def handle(text, *, conversation: Optional[str] = None, temporary: bool = False,
           ask: Optional[Callable[[str], str]] = None,
           now: Optional[float] = None) -> Optional[dict]:
    """The one entry point jarvis_quick.py calls. None: not this module's turn.

    Returns `{"reply": str, "intent": str}` when it answered. Never raises:
    every failure that reaches the owner becomes a plain sentence, and nothing
    is ever saved by accident.
    """
    if not isinstance(text, str):
        return None
    text = " ".join(text.replace("\u2018", "'").replace("\u2019", "'").split())
    text = text.strip(_TRAILING_PUNCT + " ")
    if not text:
        return None
    now = time.time() if now is None else now
    key = _key(conversation)

    brief = _create_brief(text)
    if brief is not None:
        # A new "make me a personality ..." sentence replaces any question the
        # owner did not answer; create() asks (and remembers) again if empty.
        _brief_drop(key)
        if temporary:
            return _reply(TEMPORARY_REFUSAL, "personality_create_refused")
        return create(brief, conversation=conversation, ask=ask, now=now)

    if _get(key, now) is not None:
        try:
            answered = _handle_followup(text, key, now, ask)
        except Exception:                                      # noqa: BLE001
            _brief_drop(key)
            return _reply("I could not finish that personality change just now. "
                          "The draft is unchanged and nothing was saved.",
                          "personality_refine_failed")
        if answered is not None:
            # A whole-sentence answer or an edit is about the draft; it is not
            # the answer to the brief question, which is now stale.
            _brief_drop(key)
            return answered

    # The message after "tell me what it should be like" is the brief - if this
    # conversation was asked and the line is a description rather than another
    # question or command. Taking it here means it is used exactly once.
    if _brief_take(key, now) is None:
        return None
    if temporary:
        return _reply(TEMPORARY_REFUSAL, "personality_create_refused")
    if _is_other_request(text):
        return None
    return create(text, conversation=conversation, ask=ask, now=now)
