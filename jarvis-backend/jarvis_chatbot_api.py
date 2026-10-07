"""jarvis_chatbot_api.py - the chatbot driver's API adapters: Jarvis talks to
ChatGPT, DeepSeek, Mistral, Grok, OpenRouter or Groq through each company's
official API, with a key the owner saved on this PC.

NEW MODULE, shipped whole (like jarvis_chatbot.py, which it plugs into, and
jarvis_chatbot_gemini.py beside it). Reachable from both apps through
/api/chatbot/* (jarvis_chatbot_routes.py, docs/JARVIS-API.md section 87)
once that service's key is saved on the PC. NOT yet tried against any
real service.

THE OWNER'S DECISION (CLAUDE.md, "The chatbot driver becomes versatile",
2026-09-28): "an API adapter - one adapter speaking the common OpenAI-style
API, so a key reaches ChatGPT, DeepSeek, Mistral, Grok, OpenRouter and
similar (keys under rule 3; each host a named way out)".

ONE ADAPTER FAMILY, SIX PRESETS
Every preset speaks the same "Chat Completions" shape: POST
<base>/chat/completions with {"model", "messages"}, one answer back (not
streamed). Each preset registers as ITS OWN chatbot id (openai_api,
deepseek_api, ...), so the one approval card names the exact service, its
host and its model. Where each address comes from (checked 2026-09-28; the
providers' documentation sites were blocked from the container this was
written in, so each was read from the provider's OWN code on GitHub where
that was possible):

    openai_api      https://api.openai.com/v1         VERIFIED: openai/openai-python
                                                      (_client.py; /chat/completions)
    deepseek_api    https://api.deepseek.com          UNVERIFIED: from memory of
                                                      DeepSeek's API docs; its GitHub
                                                      READMEs only name platform.deepseek.com
    mistral_api     https://api.mistral.ai/v1         VERIFIED: mistralai/client-python
                                                      (README "global" server;
                                                      chat.py path /v1/chat/completions)
    xai_api         https://api.x.ai/v1               HOST VERIFIED (xai-org/xai-sdk-python:
                                                      "The API is hosted on api.x.ai");
                                                      the /v1/chat/completions path is
                                                      not in that SDK (it speaks gRPC);
                                                      seen 2026-09-28 in xAI's own
                                                      client, xai-org/grok-build (base
                                                      https://api.x.ai/v1, then
                                                      "chat/completions"), not in the
                                                      API reference (blocked)
    openrouter_api  https://openrouter.ai/api/v1      VERIFIED: OpenRouterTeam/typescript-sdk
                                                      (lib/config.ts; chatSend.ts
                                                      /chat/completions)
    groq_api        https://api.groq.com/openai/v1    VERIFIED: groq/groq-python
                                                      (_client.py base; completions.py
                                                      /openai/v1/chat/completions)

The default models are a cheap first choice, NOT checked against any price
list (the price pages were blocked too); the owner changes one with a line
under [chatbot] in jarvis-framework.toml (MODEL_KEY below), read once when
Jarvis starts.

THE KEYS (rule 3: never logged, sent only to the one service they
authenticate against, never in plain text on disk)
  * Kept in Windows Credential Manager - the SAME store and the SAME code as
    the web-search keys (jarvis_token_store.default_store, which tests swap
    through its _STORE_FACTORY), one entry per service (KEY_TARGETS). No
    environment variable, no file, no new store.
  * Added on the PC only, like the web-search keys: one line in PowerShell
    in Jarvis's folder, `py -3 jarvis_chatbot_api.py key openai` (the key is
    pasted at a hidden prompt). The phone never sends one.
  * A preset with no key is `ready=False` with that one line as its note,
    BEFORE any card (jarvis_chatbot.plan() asks ready()).
  * The key is read when a conversation opens, handed to jarvis_scrub (so a
    log line holding it is hidden by value), attached ONLY to a request
    whose host is that preset's own pinned host, over https, and dropped
    when the conversation closes. A redirect is REFUSED, never followed
    (urllib would copy the Authorization header onto it). Nothing here logs;
    the audit gets counts only. An error never quotes the provider's own
    error text (some echo part of the key).

WHAT IS SENT, AND WHEN
Exactly the messages the driver hands to send() - each already passed
jarvis_chatbot.last_check() - plus this conversation's earlier messages and
replies (the API has no memory of its own; that IS the conversation). No
system message, no Jarvis instructions, nothing else. The history lives in
this adapter, in memory, for this one conversation, and is dropped at close.

MONEY: A MONTHLY LIMIT PER SERVICE (the owner's decision, CLAUDE.md,
2026-09-28, "A money limit comes before API chatbots are used for real")
"A monthly amount per service, set on the PC; Jarvis stops that service when
it is reached, and the approval card shows how much is left. Prices change,
so the amount is an estimate from a price list the owner can see and
correct, and the card says 'about'."
  * The price list: DEFAULT_PRICES below, dollars per million word-pieces
    (tokens) in and out, per service AND model. EVERY DEFAULT IS UNVERIFIED -
    written from memory on PRICES_WRITTEN with no price page reachable - and
    every place that shows one says so. The owner corrects one on the PC:
    `py -3 jarvis_chatbot_api.py price openai 0.25 2.00`. A model with no
    price (a model line the list does not know) cannot be used until the
    owner sets one: without a price there is no way to keep to the limit.
  * The limit: `py -3 jarvis_chatbot_api.py limit openai 5` ($5 a calendar
    month). NO LIMIT, NO CONVERSATION: a service with a key but no limit is
    not ready, and says so. Setting, raising and lowering a limit, and
    correcting a price, are done on the PC's command line only - the same
    place a key is added - because raising a limit is a loosening. There is
    no route for any of it; both apps only read it.
  * What is counted: every answer's `usage` (tokens in and out) times the
    price, per calendar month (this PC's local time), kept in a small file
    on the PC (money_path(): numbers only - never the key, never a word of a
    message). OpenRouter can report a real cost (`usage.cost`, in dollars);
    when it does, that is counted instead of the estimate. An answer with no
    `usage` is estimated from its length. `py -3 jarvis_chatbot_api.py spent`
    shows the month, the limits and the price list.
  * When it stops: ready_for() refuses a conversation once the month's
    estimate has reached the limit (so the card is never shown); and before
    EVERY message (before_send, which jarvis_chatbot.run() asks, and send()
    again) that message must fit in what is left, or the conversation ends
    there with plain words. In a comparison that chatbot drops out and the
    others carry on (jarvis_chatbot_compare's own rule).

A HARD STOP: EACH ANSWER'S LENGTH IS CAPPED (the owner's decision, CLAUDE.md,
2026-09-28: "Jarvis also asks each service to cap how long an answer can be,
so one long answer cannot carry a month past the limit. Each service names
that setting differently, so each one's own documentation is checked before
it is used.")
  * Every request to a service whose field is confirmed carries a cap on
    the answer's length (Preset.cap_field). The cap is the SMALLER of
    MOST_REPLY_TOKENS (8,000 word-pieces, a sensible most for one message)
    and what is left of the month's limit, less the worst case of what the
    message sends, turned into answer word-pieces at that model's price
    (reply_cap). So the service itself will not write - and bill - an answer
    past the limit, as far as its own counting goes. When what is left
    cannot pay for even LEAST_REPLY_TOKENS (256), the message is refused
    with the same plain words as before.
  * An answer cut short by the cap (finish_reason "length") is kept and
    shown with CUT_OFF under it in both apps (the transcript's `cut_off`).
  * Where each field was confirmed (2026-09-28; every provider's
    documentation site was blocked from the container this was written in,
    so each was read in the provider's OWN code on GitHub):
      openai_api      max_completion_tokens  openai/openai-python, types/chat/
                      completion_create_params.py: "An upper bound for the
                      number of tokens that can be generated for a completion,
                      including visible output tokens and reasoning tokens"
                      (max_tokens there: "deprecated in favor of
                      max_completion_tokens", "not compatible with o-series")
      groq_api        max_completion_tokens  groq/groq-python, the same file
                      name (max_tokens: "Deprecated in favor of
                      max_completion_tokens")
      mistral_api     max_tokens             mistralai/client-python, client/
                      models/chatcompletionrequest.py: "The maximum number of
                      tokens to generate in the completion"
      openrouter_api  max_completion_tokens  OpenRouterTeam/typescript-sdk,
                      models/chatrequest.ts: "Maximum tokens in completion"
                      (max_tokens: "deprecated, use max_completion_tokens")
      xai_api         max_tokens             xAI's own code, not its API
                      reference: xai-org/grok-build sends `max_tokens` in its
                      Chat Completions request to <base>/chat/completions, base
                      https://api.x.ai/v1; xai-org/xai-sdk-python's chat.py
                      names the same (gRPC)
      deepseek_api    UNVERIFIED - NO CAP IS SENT. DeepSeek's API reference was
                      blocked and it has no SDK for this API on GitHub (its own
                      deepseek-harness speaks the Anthropic-style endpoint, a
                      different API). The worst-case check below stays its only
                      guard.
  * Hidden reasoning ("thinking"): OpenAI's own words put reasoning INSIDE
    max_completion_tokens, so for openai_api the cap bounds the whole bill
    (Preset.reasoning "inside"). For every other service its own code does
    not say whether the cap also covers hidden reasoning ("not_stated"), so
    the check keeps REASONING_ROOM word-pieces of room for it on top of the
    cap: the cap bounds the visible answer, and the room is a guess for the
    rest.
  * A service with no confirmed field (DeepSeek) keeps the old worst-case
    check only: everything resent plus MOST_REPLY_TOKENS of answer plus
    REASONING_ROOM must fit in what is left.
  * Honest limits: it is still an ESTIMATE. A price may be wrong until the
    owner corrects it; for the "not_stated" services and DeepSeek, hidden
    reasoning longer than REASONING_ROOM, or an answer longer than the most
    (DeepSeek, uncapped), can carry a month a little over the limit.

ERRORS, IN PLAIN WORDS (raised from read_reply as ApiUnavailable, whose
`owner_words` jarvis_chatbot.run() shows): the key refused (401/403), no
credit (402), an unknown model (404), too many requests (429), a problem on
the service's side (5xx), no answer in time, no connection, a redirect.
NEVER A RETRY STORM: a 429 is retried AT MOST ONCE, and only when its
Retry-After is at most RETRY_CAP seconds (else it ends at once, saying how
long the service asked to wait). Nothing else is ever retried.

    python3 test_chatbot_api.py

Standard library only. No I/O at import.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import jarvis_chatbot as CB

KIND = "api"


@dataclass(frozen=True)
class Preset:
    id: str            # the chatbot id: "<short>_api"
    short: str         # what the owner types: py -3 jarvis_chatbot_api.py key <short>
    name: str          # the card's and the apps' name
    company: str       # whose account the key belongs to
    base_url: str      # <base>/chat/completions
    model: str         # the default model; [chatbot] <id>_model changes it
    key_where: str     # where the owner makes a key
    verified: str      # where the base URL was checked, or "unverified"
    note: str = ""     # anything the card must say about this one
    #: Where the owner checks the price (UNVERIFIED addresses, from memory).
    price_page: str = ""
    #: The request field that caps how long an answer can be, as this
    #: service's own code names it; "" when it could not be confirmed - then
    #: no cap is sent and the worst-case check is the only guard.
    cap_field: str = ""
    #: Where cap_field was confirmed, or why it is unverified.
    cap_source: str = ""
    #: Whether hidden reasoning counts inside the cap: "inside" (the
    #: service's own words say so) or "not_stated".
    reasoning: str = "not_stated"

    @property
    def host(self) -> str:
        return (urllib.parse.urlsplit(self.base_url).hostname or "").lower()

    @property
    def port(self) -> int:
        return _port_of(self.base_url)


PRESETS: dict = {p.id: p for p in (
    Preset("openai_api", "openai", "ChatGPT (OpenAI API)", "OpenAI",
           "https://api.openai.com/v1", "gpt-5-mini",
           "https://platform.openai.com/api-keys",
           "openai/openai-python _client.py",
           price_page="https://openai.com/api/pricing",
           cap_field="max_completion_tokens",
           cap_source=("openai/openai-python src/openai/types/chat/"
                       "completion_create_params.py (checked 2026-09-28)"),
           reasoning="inside"),
    Preset("deepseek_api", "deepseek", "DeepSeek (API)", "DeepSeek",
           "https://api.deepseek.com", "deepseek-chat",
           "https://platform.deepseek.com/api_keys",
           "unverified",
           price_page="https://api-docs.deepseek.com/quick_start/pricing",
           cap_field="",
           cap_source=("unverified: DeepSeek's API reference could not be opened and it has "
                       "no SDK for this API on GitHub")),
    Preset("mistral_api", "mistral", "Mistral (API)", "Mistral AI",
           "https://api.mistral.ai/v1", "mistral-small-latest",
           "https://console.mistral.ai/api-keys",
           "mistralai/client-python README and chat.py",
           price_page="https://mistral.ai/pricing",
           cap_field="max_tokens",
           cap_source=("mistralai/client-python src/mistralai/client/models/"
                       "chatcompletionrequest.py (checked 2026-09-28)")),
    Preset("xai_api", "xai", "Grok (xAI API)", "xAI",
           "https://api.x.ai/v1", "grok-4.6",
           "https://console.x.ai",
           ("host from xai-org/xai-sdk-python; the /v1/chat/completions path from xAI's own "
            "client xai-org/grok-build, not its API reference"),
           price_page="https://docs.x.ai/docs/models",
           cap_field="max_tokens",
           cap_source=("xAI's own client code, xai-org/grok-build (xai-grok-sampling-types "
                       "types.rs and xai-grok-sampler client.rs), not xAI's API reference, "
                       "which could not be opened (checked 2026-09-28)")),
    Preset("openrouter_api", "openrouter", "OpenRouter (API)", "OpenRouter",
           "https://openrouter.ai/api/v1", "openai/gpt-5-mini",
           "https://openrouter.ai/keys",
           "OpenRouterTeam/typescript-sdk lib/config.ts",
           note=("OpenRouter passes each message on to the company that runs the model "
                 "you chose (for the default, OpenAI), under that company's terms too."),
           price_page="https://openrouter.ai/models",
           cap_field="max_completion_tokens",
           cap_source=("OpenRouterTeam/typescript-sdk src/models/chatrequest.ts "
                       "(checked 2026-09-28)")),
    Preset("groq_api", "groq", "Groq (API)", "Groq",
           "https://api.groq.com/openai/v1", "openai/gpt-oss-20b",
           "https://console.groq.com/keys",
           "groq/groq-python _client.py and completions.py",
           price_page="https://groq.com/pricing",
           cap_field="max_completion_tokens",
           cap_source=("groq/groq-python src/groq/types/chat/completion_create_params.py "
                       "(checked 2026-09-28)")),
)}

BY_SHORT = {p.short: p.id for p in PRESETS.values()}

#: The Credential Manager entry each key is kept under - one per service,
#: named like jarvis_search.KEY_TARGETS ("Jarvis Backend/<name> key").
KEY_TARGETS = {pid: f"Jarvis Backend/{PRESETS[pid].company} API key" for pid in PRESETS}

#: The line under [chatbot] in jarvis-framework.toml that changes a model.
def MODEL_KEY(pid: str) -> str:
    return f"{pid}_model"


KEY_LINE = "py -3 jarvis_chatbot_api.py key {short}"
KEY_ENTRY = ("Keys are added on the PC only, like the web-search keys: the phone never "
             "sends one, because sending a key to the PC would send it somewhere other "
             "than its own service.")

#: One request's longest wait. Two of them plus the longest 429 wait stay
#: inside the driver's own reply timeout (jarvis_chatbot.REPLY_TIMEOUT).
HTTP_TIMEOUT = 75.0
#: A 429 is retried once, and only when it asks for at most this many seconds.
RETRY_CAP = 20.0
#: A 429 with no Retry-After waits this long before its one retry.
RETRY_DEFAULT = 5.0
#: The most bytes read from one answer.
MAX_BODY = 2_000_000
#: The most earlier messages kept and resent (the driver's own caps keep
#: a conversation far below this; it is a backstop).
MAX_HISTORY = 60

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}$")
_KEY_RE = re.compile(r"^[\x21-\x7e]{8,300}$")

#: Tests only: allow plain http:// to 127.0.0.1 (a fake provider on this
#: PC). Always False on the owner's PC - every preset is https.
_TEST_LOOPBACK_OK = False


class ApiUnavailable(RuntimeError):
    """The conversation cannot go on. `owner_words` is the plain-words reason;
    jarvis_chatbot.run() shows it. Never holds the key or the provider's
    own error text."""

    def __init__(self, owner_words: str, code: str = ""):
        super().__init__(owner_words)
        self.owner_words = owner_words
        self.code = code


# ============================================================================
#   The keys - Windows Credential Manager, through jarvis_token_store
# ============================================================================

def _store(pid: str):
    """The store for one key, or a StoreError instance when there is none."""
    import jarvis_token_store as T
    return T.default_store(KEY_TARGETS[pid])


def key_problem(value) -> str:
    """"" for something that can be a key, else why not. Never quotes it."""
    if not isinstance(value, str):
        return "the key must be text"
    v = value.strip()
    if not v:
        return "the key is empty"
    if not _KEY_RE.match(v):
        return ("the key must be 8 to 300 plain characters with no spaces - check that the "
                "whole key was copied, and nothing else")
    return ""


def _read_key(pid: str) -> Optional[str]:
    """The saved key, "" when none is saved, None when the store cannot be
    asked. Never logged, never returned to an app."""
    st = _store(pid)
    if isinstance(st, Exception):
        return None
    try:
        value = (st.read() or "").strip()
    except Exception:
        return None
    return "" if key_problem(value) else value


def key_saved(pid: str) -> Optional[bool]:
    """True / False, or None when Credential Manager cannot be asked."""
    if pid not in PRESETS:
        return None
    got = _read_key(pid)
    return None if got is None else bool(got)


def save_key(pid: str, value: str) -> dict:
    """Save a key in Credential Manager. For the owner's own command line;
    there is NO route for it."""
    if pid not in PRESETS:
        return {"ok": False, "error": "there is no such chatbot"}
    why = key_problem(value)
    if why:
        return {"ok": False, "error": why}
    st = _store(pid)
    if isinstance(st, Exception):
        return {"ok": False, "error": "Windows Credential Manager cannot be opened here"}
    try:
        st.write(value.strip())
        back = (st.read() or "").strip()
    except Exception as exc:
        # The exception's name only: some carry the value they were given.
        return {"ok": False, "error": f"Credential Manager refused ({type(exc).__name__})"}
    if back != value.strip():
        return {"ok": False, "error": "the key read back from Credential Manager did not match"}
    return {"ok": True, "said": f"Saved your {PRESETS[pid].company} key in Windows Credential "
                                f"Manager, as \"{KEY_TARGETS[pid]}\". It is sent only to "
                                f"{PRESETS[pid].host}."}


def forget_key(pid: str) -> dict:
    if pid not in PRESETS:
        return {"ok": False, "error": "there is no such chatbot"}
    st = _store(pid)
    if isinstance(st, Exception):
        return {"ok": False, "error": "Windows Credential Manager cannot be opened here"}
    try:
        st.delete()
    except Exception as exc:
        return {"ok": False, "error": f"Credential Manager refused ({type(exc).__name__})"}
    return {"ok": True, "said": f"Removed your {PRESETS[pid].company} key from this PC."}


# ============================================================================
#   The model, read once
# ============================================================================

_MODELS: dict = {}
_MODELS_LOCK = threading.Lock()


def model_for(pid: str) -> tuple:
    """(model, problem). The [chatbot] <id>_model line when there is one,
    else the preset's default. Read ONCE per process, so the card and the
    conversation it approved always name the same model: a change takes
    effect when Jarvis restarts."""
    with _MODELS_LOCK:
        if pid not in _MODELS:
            raw = CB._cfg().get(MODEL_KEY(pid))
            if raw is None:
                _MODELS[pid] = (PRESETS[pid].model, "")
            elif not isinstance(raw, str) or not _MODEL_RE.match(raw.strip()):
                _MODELS[pid] = ("", f"the {MODEL_KEY(pid)} line under [chatbot] in "
                                    f"jarvis-framework.toml is not a model name")
            else:
                _MODELS[pid] = (raw.strip(), "")
            _register(pid)
        return _MODELS[pid]


def _reset_models_for_tests() -> None:
    with _MODELS_LOCK:
        _MODELS.clear()
    for pid in PRESETS:
        _register(pid)


# ============================================================================
#   Pinning: the one host a preset's key may go to
# ============================================================================

_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _port_of(url: str) -> int:
    parts = urllib.parse.urlsplit(str(url or ""))
    return parts.port or (443 if parts.scheme == "https" else 80)


def endpoint_problem(url: str, preset: Preset) -> str:
    """"" when `url` is this preset's own https endpoint, else why not."""
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
        host = (parts.hostname or "").lower()
    except ValueError:
        return "the address is not a web address"
    try:
        port = _port_of(url)
    except ValueError:
        return "the address has a bad port"
    if host != preset.host or port != preset.port:
        return f"the address is not {preset.host}"
    if parts.username or parts.password:
        return "the address carries a user name"
    if parts.scheme == "https":
        return ""
    if parts.scheme == "http" and _TEST_LOOPBACK_OK and host in _LOOPBACK:
        return ""
    return "the address is not https"


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is refused, never followed: urllib copies every header -
    the key included - onto the redirect target, cross-host too."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Redirected(code)


class _Redirected(Exception):
    def __init__(self, code):
        super().__init__(f"redirect {code}")
        self.code = code


def _opener(url: str):
    import jarvis_local_http as LH
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host in _LOOPBACK:
        return LH.opener(_RefuseRedirect)            # this PC: never through a proxy
    return LH.opener_for(url, _RefuseRedirect)       # https: a proxy sees only scrambled bytes


#: Tests may replace this: (Request, timeout) -> (status, headers, body).
_HTTP = None


def _http(req: urllib.request.Request, timeout: float) -> tuple:
    if _HTTP is not None:
        return _HTTP(req, timeout)
    try:
        with _opener(req.full_url).open(req, timeout=timeout) as r:
            body = r.read(MAX_BODY + 1)
            return r.status, dict(r.headers.items()), body
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096) if exc.fp is not None else b""
        except Exception:
            body = b""
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, body


def _retry_after(headers: dict) -> Optional[float]:
    for k, v in (headers or {}).items():
        if str(k).lower() == "retry-after":
            try:
                return max(0.0, float(str(v).strip()))
            except ValueError:
                return None           # an HTTP date: not worth parsing to wait on
    return None


# ============================================================================
#   The money limit: a monthly amount per service, an estimate
# ============================================================================

#: The day the default prices below were written. NOT checked against any
#: price page (none could be reached from where this was written).
PRICES_WRITTEN = "2026-09-28"

#: (service id, model) -> (dollars per million word-pieces IN, per million
#: OUT). EVERY ONE IS UNVERIFIED: written from memory on PRICES_WRITTEN,
#: with no price page reachable. Check each against the company's price page
#: (Preset.price_page) and correct it on the PC:
#:     py -3 jarvis_chatbot_api.py price openai <in> <out>
#: A model this list does not know has NO price: it cannot be used until
#: the owner sets one (without a price there is no way to keep to a limit).
DEFAULT_PRICES = {
    ("openai_api", "gpt-5-mini"): (0.25, 2.00),             # UNVERIFIED
    ("deepseek_api", "deepseek-chat"): (0.28, 0.42),        # UNVERIFIED
    ("mistral_api", "mistral-small-latest"): (0.10, 0.30),  # UNVERIFIED
    # No price is remembered for this model name at all: Grok 4's (the
    # highest here) is used as a cautious guess. UNVERIFIED.
    ("xai_api", "grok-4.6"): (3.00, 15.00),
    ("openrouter_api", "openai/gpt-5-mini"): (0.25, 2.00),  # UNVERIFIED
    ("groq_api", "openai/gpt-oss-20b"): (0.10, 0.50),       # UNVERIFIED
}

#: The most one answer may be, in word-pieces: the cap sent with every
#: message (smaller when less of the month is left - reply_cap), and the
#: worst case assumed for a service whose cap field is unverified.
MOST_REPLY_TOKENS = 8000
#: The old name, kept for anything that still reads it.
WORST_REPLY_TOKENS = MOST_REPLY_TOKENS
#: Below this, an answer is too short to be worth asking for: the message is
#: refused instead (the month's limit is as good as reached).
LEAST_REPLY_TOKENS = 256
#: Room kept for hidden reasoning where the service does not say its cap
#: covers it (Preset.reasoning "not_stated"), and for DeepSeek (no cap). A
#: guess: a longer hidden reasoning can still carry a month a little over.
REASONING_ROOM = 8000
#: For the worst case of what is sent: fewer characters per word-piece than
#: the usual four, so the guess errs high; plus a few per message.
WORST_CHARS_PER_TOKEN = 3
WORST_TOKENS_PER_MESSAGE = 20
#: For an answer that came back with no `usage`: the usual four characters
#: per word-piece.
CHARS_PER_TOKEN = 4
#: The most a limit, or a price, may be set to.
MOST_LIMIT = 10_000.0
MOST_PRICE = 1_000.0
#: How many months of spending the file keeps.
KEEP_MONTHS = 13
MONEY_FILE = "api-money.json"

LIMIT_LINE = "py -3 jarvis_chatbot_api.py limit {short} {amount}"
PRICE_LINE = "py -3 jarvis_chatbot_api.py price {short} <in> <out>"

#: Tests may replace this (the month is this PC's local time).
_now = time.time
_MONEY_LOCK = threading.RLock()

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

#: The sentence both apps and both cards show (jarvis_chatbot_routes.WORDS
#: "money_left" is this, word for word).
MONEY_LEFT = ("About {left} of {limit} left this month for {company} (prices are estimates "
              "you can correct on the PC).")
#: Added on the card when what is left may not cover one more message.
MONEY_THIN = (" That may not be enough for one more message; if so, Jarvis stops before "
              "sending it.")
#: Shown under an answer the cap cut short (jarvis_chatbot_routes.WORDS
#: "cut_off" is this, word for word; both apps show it).
CUT_OFF = ("Jarvis asked for a short answer so it stays within your limit; the rest was "
           "cut off.")
#: An answer the cap cut short before any of it was written (a "thinking"
#: model can spend the whole cap on hidden reasoning).
CUT_OFF_EMPTY = ("{name} used up the answer length Jarvis asked for, to stay within your "
                 "money limit, before writing any answer. Nothing more was sent.")


class MoneyFileError(RuntimeError):
    """The money file is there but cannot be read: nothing is used until
    it is fixed (failing closed - an unreadable file must not read as
    "nothing spent")."""


def money_path() -> Path:
    """<Jarvis's settings folder>/chatbot/api-money.json - numbers only."""
    try:
        import jarvis_framework as fw
        base = Path(fw.CONFIG_DIR)
    except Exception:
        env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
        base = Path(os.path.expanduser(env)) if env else (
            Path(os.path.expanduser("~")) / ".openjarvis")
    return base / "chatbot" / MONEY_FILE


def _empty() -> dict:
    return {"version": 1, "limits": {}, "prices": {}, "months": {}}


def _load() -> dict:
    p = money_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty()
    except OSError as exc:
        raise MoneyFileError(f"it could not be opened ({type(exc).__name__})") from None
    try:
        got = json.loads(raw)
    except ValueError:
        raise MoneyFileError("it is not readable JSON") from None
    if not isinstance(got, dict):
        raise MoneyFileError("it is not in the expected shape")
    out = _empty()
    for k in ("limits", "prices", "months"):
        v = got.get(k, {})
        if not isinstance(v, dict):
            raise MoneyFileError("it is not in the expected shape")
        out[k] = v
    return out


def _save(data: dict) -> None:
    p = money_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    for old in sorted(data.get("months", {}))[:-KEEP_MONTHS]:
        data["months"].pop(old, None)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def _num(v) -> Optional[float]:
    """A finite number at or above nothing, else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) and f >= 0 else None


def month_key(t: Optional[float] = None) -> str:
    lt = time.localtime(_now() if t is None else t)
    return f"{lt.tm_year:04d}-{lt.tm_mon:02d}"


def next_month_words(t: Optional[float] = None) -> str:
    """"October 1": the day the month's count starts again."""
    lt = time.localtime(_now() if t is None else t)
    return f"{MONTHS[lt.tm_mon % 12]} 1"


def dollars(x) -> str:
    """"$0.03". An amount above nothing but under a cent shows as "$0.01":
    an estimate is never shown as free."""
    x = max(0.0, float(x or 0.0))
    if 0 < x < 0.01:
        x = 0.01
    return f"${x:,.2f}"


def limit_of(pid: str, data: Optional[dict] = None) -> Optional[float]:
    d = data if data is not None else _load()
    return _num((d.get("limits") or {}).get(pid))


def price_of(pid: str, model: str, data: Optional[dict] = None) -> Optional[tuple]:
    """(in, out, where): the owner's correction for this service and model
    when there is one, else the default, else None. `where` is "yours" or
    "default"."""
    d = data if data is not None else _load()
    mine = (d.get("prices") or {}).get(pid)
    got = mine.get(model) if isinstance(mine, dict) else None
    if isinstance(got, dict):
        pin, pout = _num(got.get("in")), _num(got.get("out"))
        if pin is not None and pout is not None:
            return pin, pout, "yours"
    dflt = DEFAULT_PRICES.get((pid, model))
    return (dflt[0], dflt[1], "default") if dflt else None


def spent_of(pid: str, data: Optional[dict] = None, month: Optional[str] = None) -> float:
    """This month's count for one service, in dollars (an estimate)."""
    d = data if data is not None else _load()
    row = ((d.get("months") or {}).get(month or month_key()) or {}).get(pid)
    if not isinstance(row, dict):
        return 0.0
    return _num(row.get("dollars")) or 0.0


def cost_of(pid: str, model: str, prompt_tokens: int, completion_tokens: int,
            data: Optional[dict] = None) -> Optional[float]:
    """The estimate for these counts, in dollars, or None with no price."""
    pr = price_of(pid, model, data)
    if pr is None:
        return None
    return (max(0, prompt_tokens) * pr[0] + max(0, completion_tokens) * pr[1]) / 1_000_000


def worst_tokens(chars: int, messages: int) -> int:
    """The most word-pieces `chars` characters in `messages` messages could
    be (errs high)."""
    return int(math.ceil(max(0, chars) / WORST_CHARS_PER_TOKEN)) + (
        WORST_TOKENS_PER_MESSAGE * max(1, messages))


def record_spend(pid: str, model: str, prompt_tokens: int, completion_tokens: int, *,
                 real_dollars: Optional[float] = None, guessed: bool = False) -> float:
    """Add one answer to this month's count; returns the dollars counted.
    `real_dollars`: what the service itself reported (OpenRouter), counted
    in place of the estimate. Numbers only: never the key, never a word."""
    with _MONEY_LOCK:
        data = _load()
        est = cost_of(pid, model, prompt_tokens, completion_tokens, data)
        used = real_dollars if real_dollars is not None else (est or 0.0)
        row = data["months"].setdefault(month_key(), {}).setdefault(pid, {})
        row["dollars"] = round((_num(row.get("dollars")) or 0.0) + used, 8)
        for k, v in (("prompt_tokens", prompt_tokens), ("completion_tokens", completion_tokens),
                     ("requests", 1),
                     ("reported_by_service", 1 if real_dollars is not None else 0),
                     ("guessed_from_length", 1 if guessed else 0),
                     ("unpriced", 1 if est is None and real_dollars is None else 0)):
            if v or k in ("prompt_tokens", "completion_tokens", "requests"):
                row[k] = int((_num(row.get(k)) or 0) + v)
        _save(data)
        return used


def _file_words(why: str) -> str:
    """Said in both apps too, so the folder is named, not the full path
    (which holds the Windows user name); `spent` on the PC prints the path."""
    return (f"Jarvis's record of API spending (chatbot\\{MONEY_FILE} in Jarvis's settings "
            f"folder) cannot be read: {why}. No API chatbot is used until it is fixed; "
            f"deleting the file forgets this month's spending and every limit")


def set_limit(pid: str, amount: Optional[float]) -> dict:
    """The owner's command line only (there is NO route): `amount` dollars a
    month, or None to remove the limit (the service then cannot be used)."""
    if pid not in PRESETS:
        return {"ok": False, "error": "there is no such chatbot"}
    if amount is not None:
        a = _num(amount)
        if a is None or a > MOST_LIMIT:
            return {"ok": False, "error": f"the limit must be a number of dollars from 0 to "
                                          f"{MOST_LIMIT:,.0f}"}
    p = PRESETS[pid]
    with _MONEY_LOCK:
        try:
            data = _load()
        except MoneyFileError as exc:
            return {"ok": False, "error": _file_words(str(exc))}
        old = limit_of(pid, data)
        if amount is None:
            data["limits"].pop(pid, None)
        else:
            data["limits"][pid] = round(float(amount), 2)
        _save(data)
        spent = spent_of(pid, data)
    if amount is None:
        return {"ok": True, "said": f"Removed the monthly money limit for {p.company}. Jarvis "
                                    f"will not use {p.name} until a limit is set again."}
    was = f" (it was {dollars(old)})" if old is not None else ""
    return {"ok": True, "said": f"{p.company}: at most {dollars(amount)} a month{was}. About "
                                f"{dollars(spent)} is used so far this month (an estimate)."}


def set_price(pid: str, model: str, pin, pout) -> dict:
    """Correct one price, for this service and model. The command line only."""
    if pid not in PRESETS:
        return {"ok": False, "error": "there is no such chatbot"}
    a, b = _num(pin), _num(pout)
    if a is None or b is None or a > MOST_PRICE or b > MOST_PRICE:
        return {"ok": False, "error": f"each price must be dollars per million word-pieces, "
                                      f"from 0 to {MOST_PRICE:,.0f}"}
    with _MONEY_LOCK:
        try:
            data = _load()
        except MoneyFileError as exc:
            return {"ok": False, "error": _file_words(str(exc))}
        data["prices"].setdefault(pid, {})[model] = {
            "in": a, "out": b, "set": time.strftime("%Y-%m-%d", time.localtime(_now()))}
        _save(data)
    return {"ok": True, "said": f"{PRESETS[pid].company}, model {model}: ${a:g} per million "
                                f"word-pieces in, ${b:g} out. Jarvis uses this price from the "
                                f"next answer; what is already counted stays as it was."}


def reset_price(pid: str, model: str) -> dict:
    """Forget the owner's correction: back to the (unverified) default."""
    if pid not in PRESETS:
        return {"ok": False, "error": "there is no such chatbot"}
    with _MONEY_LOCK:
        try:
            data = _load()
        except MoneyFileError as exc:
            return {"ok": False, "error": _file_words(str(exc))}
        mine = data["prices"].get(pid)
        if isinstance(mine, dict):
            mine.pop(model, None)
            if not mine:
                data["prices"].pop(pid, None)
        _save(data)
        back = price_of(pid, model, data)
    return {"ok": True, "said": f"{PRESETS[pid].company}, model {model}: back to "
                                + (f"the default price (${back[0]:g} in, ${back[1]:g} out, "
                                   f"UNVERIFIED)." if back else
                                   "no price, so it cannot be used until you set one.")}


def no_limit_words(p: Preset) -> str:
    return (f"No monthly money limit is set for {p.company}, so Jarvis will not use {p.name} "
            f"yet. Set one on the PC, in PowerShell in Jarvis's folder - for example $5 a "
            f"month: " + LIMIT_LINE.format(short=p.short, amount=5))


def no_price_words(p: Preset, model: str) -> str:
    return (f"Jarvis has no price for the model \"{model}\" on {p.company}, so it cannot keep "
            f"to your money limit. Look up the price at {p.price_page or 'its price page'} and "
            f"set it on the PC (dollars per million word-pieces in, then out): "
            + PRICE_LINE.format(short=p.short))


def reached_words(p: Preset, limit: float, spent: float) -> str:
    return (f"You set {dollars(limit)} a month for {p.company}; about {dollars(spent)} is used "
            f"this month. Raise the limit on the PC or wait until {next_month_words()}.")


def would_pass_words(p: Preset, limit: float, spent: float, worst: float) -> str:
    return (f"The next message to {p.name} could cost up to about {dollars(worst)}, which "
            f"would pass the {dollars(limit)} a month you set for {p.company} (about "
            f"{dollars(spent)} is used this month). Nothing more was sent. Raise the limit on "
            f"the PC or wait until {next_month_words()}.")


def reasoning_room(p: Preset) -> int:
    """The word-pieces kept for hidden reasoning on top of the cap: none
    where the service's own words put reasoning inside its cap."""
    return 0 if (p.cap_field and p.reasoning == "inside") else REASONING_ROOM


def reply_cap(pid: str, model: str, left: float, next_chars: int, next_messages: int,
              data: Optional[dict] = None) -> tuple:
    """(cap, worst, fits) for the next message, with `left` dollars left
    this month.
      cap    the answer-length cap to send (0: none - the service's field is
             unverified, or the message does not fit)
      worst  the most that message can cost, in dollars, as far as the
             service's own counting goes (with the smallest cap, when it
             does not fit)
      fits   whether it may be sent
    The cap is the SMALLER of MOST_REPLY_TOKENS and what is left after the
    worst case of what is sent, turned into answer word-pieces at this
    model's price, less the room kept for hidden reasoning; below
    LEAST_REPLY_TOKENS the message does not fit."""
    p = PRESETS[pid]
    pr = price_of(pid, model, data)
    if pr is None:
        return 0, 0.0, False
    pin, pout = pr[0], pr[1]
    tin = worst_tokens(next_chars, next_messages)
    room = reasoning_room(p)
    if not p.cap_field:
        worst = (tin * pin + (MOST_REPLY_TOKENS + room) * pout) / 1_000_000
        return 0, worst, worst <= left
    spare = left - tin * pin / 1_000_000
    if pout <= 0:
        cap = MOST_REPLY_TOKENS if spare >= 0 else 0
    else:
        cap = min(MOST_REPLY_TOKENS, int(math.floor(spare * 1_000_000 / pout)) - room)
    if cap < LEAST_REPLY_TOKENS:
        return 0, (tin * pin + (LEAST_REPLY_TOKENS + room) * pout) / 1_000_000, False
    return cap, (tin * pin + (cap + room) * pout) / 1_000_000, True


def money_check(pid: str, model: str, *, next_chars: int = 0,
                next_messages: int = 0) -> tuple:
    """("", cap) when the limit allows; else (why not, in plain words, 0).
    With `next_messages` (the next request: everything it resends), that
    request must fit in what is left too, and `cap` is the answer-length
    cap to send with it (0 for none: reply_cap)."""
    p = PRESETS[pid]
    try:
        data = _load()
    except MoneyFileError as exc:
        return _file_words(str(exc)) + ".", 0
    limit = limit_of(pid, data)
    if limit is None:
        return no_limit_words(p), 0
    if price_of(pid, model, data) is None:
        return no_price_words(p, model), 0
    spent = spent_of(pid, data)
    if spent >= limit:
        return reached_words(p, limit, spent), 0
    if not next_messages:
        return "", 0
    cap, worst, fits = reply_cap(pid, model, limit - spent, next_chars, next_messages, data)
    if not fits:
        return would_pass_words(p, limit, spent, worst), 0
    return "", cap


def money_problem(pid: str, model: str, *, next_chars: int = 0, next_messages: int = 0) -> str:
    """"" when the limit allows; else why not, in plain words (money_check)."""
    return money_check(pid, model, next_chars=next_chars, next_messages=next_messages)[0]


def money_view(pid: str) -> Optional[dict]:
    """What both apps and the card show for one service - the amounts as
    the PC writes them ("$4.02") - or None when there is no limit to show."""
    p = PRESETS.get(pid)
    if p is None:
        return None
    try:
        data = _load()
    except MoneyFileError:
        return None
    limit = limit_of(pid, data)
    if limit is None:
        return None
    model = model_for(pid)[0]
    spent = spent_of(pid, data)
    left = max(0.0, limit - spent)
    pr = price_of(pid, model, data) if model else None
    left_words = dollars(left) if left >= 0.005 else "$0.00"
    line = MONEY_LEFT.format(left=left_words, limit=dollars(limit), company=p.company)
    if pr is not None and left > 0:
        # The longest goal, as the first message: can it be sent at all
        # (with the smallest cap, for a service that caps)?
        if not reply_cap(pid, model, left, CB.MAX_GOAL_CHARS, 1, data)[2]:
            line += MONEY_THIN
    return {"company": p.company, "limit": dollars(limit), "left": left_words,
            "spent": dollars(spent), "until": next_month_words(), "reached": spent >= limit,
            "line": line}


def _card_money(pid: str) -> str:
    """The card's line (jarvis_chatbot.describe and the comparison's card)."""
    got = money_view(pid)
    return got["line"] if got else ""


# ============================================================================
#   The adapter
# ============================================================================

class ApiChatbot(CB.Adapter):
    """One conversation with one preset's API. send() starts the request on
    a thread of its own; read_reply() waits for it in the driver's short
    slices, so Stop lands while a slow answer is on its way."""

    def __init__(self, preset: Preset, model: str, *, http_timeout: float = HTTP_TIMEOUT,
                 sleep=None):
        self.preset = preset
        self.id, self.name, self.host = preset.id, preset.name, preset.host
        self.model = model
        self.http_timeout = float(http_timeout)
        self._key: Optional[str] = None
        self._history: list = []
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._cancel = threading.Event()
        self._busy = False
        self._reply: Optional[str] = None
        self._error: Optional[ApiUnavailable] = None
        self._opened = False
        self._closed = False
        self._sleep = sleep
        self._usage = {"model": model, "requests": 0, "prompt_tokens": 0,
                       "completion_tokens": 0, "total_tokens": 0, "retries": 0,
                       "dollars": 0.0, "cost": dollars(0)}
        #: Set when an answer's cost could not be written down: the next
        #: message is refused (a count that is not kept must not read as
        #: nothing spent).
        self._money_broken = ""
        #: The answer-length cap sent with the request on its way (0: none).
        self._cap = 0
        #: Whether the last answer was cut short by that cap.
        self._cut_off = False

    # ---- the interface ----------------------------------------------------

    def open(self) -> None:
        why = endpoint_problem(self._url(), self.preset)
        if why:
            raise ApiUnavailable(f"Jarvis will not send your {self.preset.company} key "
                                 f"there: {why}.", "pinned")
        key = _read_key(self.preset.id)
        if key is None:
            raise ApiUnavailable(CANNOT_READ.format(name=self.preset.company), "store")
        if not key:
            raise ApiUnavailable(no_key_words(self.preset), "no_key")
        try:
            import jarvis_scrub
            jarvis_scrub.register_secret(key)
        except Exception:
            pass
        self._key = key
        self._opened = True

    def send(self, text: str) -> None:
        with self._lock:
            if self._closed or not self._opened:
                raise ApiUnavailable(f"The conversation with {self.name} is closed.", "closed")
            if self._busy:
                raise ApiUnavailable(f"{self.name} is still answering the last message.",
                                     "busy")
        # The money check again, right here, because it also gives the cap
        # this very request carries (the driver asked before_send already;
        # anything else that calls send() gets the same check).
        why, cap = self._money(text)
        if why:
            raise ApiUnavailable(why, "money_limit")
        with self._lock:
            self._history.append({"role": "user", "content": str(text)})
            self._history = self._history[-MAX_HISTORY:]
            messages = [dict(m) for m in self._history]
            self._busy, self._reply, self._error = True, None, None
            self._cap, self._cut_off = cap, False
            self._done.clear()
        threading.Thread(target=self._work, args=(messages,), name="jarvis-chatbot-api",
                         daemon=True).start()

    def read_reply(self, timeout: float) -> Optional[str]:
        if not self._done.wait(max(0.0, float(timeout))):
            return None
        with self._lock:
            if not self._busy:
                return None
            self._busy = False
            err, reply = self._error, self._reply
            if err is None and reply is not None:
                self._history.append({"role": "assistant", "content": reply})
        if err is not None:
            raise err
        return reply

    def status(self) -> CB.Status:
        return CB.Status("gone", "closed") if self._closed else CB.OK

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._key = None
            self._history = []
        self._cancel.set()

    def usage(self) -> dict:
        """What the service reported, for the session view. Counts only;
        `cost` is this conversation's estimate as the apps show it."""
        with self._lock:
            return dict(self._usage)

    def before_send(self, text: str) -> str:
        """jarvis_chatbot.run() asks this right before every message: "" to
        send it, else why not (the conversation then ends with these words).
        This request must fit in this month's limit: with a cap on the
        answer, at least LEAST_REPLY_TOKENS of it; with none (DeepSeek), its
        worst case (reply_cap)."""
        return self._money(text)[0]

    def cut_off(self) -> bool:
        """Whether the last answer was cut short by the cap Jarvis sent
        (jarvis_chatbot marks it `cut_off` in the transcript)."""
        with self._lock:
            return self._cut_off

    def _money(self, text: str) -> tuple:
        """(why not, "" to send; the cap to send with it)."""
        if self._money_broken:
            return self._money_broken, 0
        with self._lock:
            texts = [str(m.get("content") or "") for m in self._history]
        texts = (texts + [str(text)])[-MAX_HISTORY:]
        return money_check(self.preset.id, self.model,
                           next_chars=sum(len(t) for t in texts), next_messages=len(texts))

    # ---- the request ------------------------------------------------------

    def _url(self) -> str:
        return self.preset.base_url.rstrip("/") + "/chat/completions"

    def _request(self, messages: list) -> urllib.request.Request:
        url = self._url()
        why = endpoint_problem(url, self.preset)
        if why or not self._key:
            # Checked again on every request: the key is attached to the
            # pinned host or to nothing.
            raise ApiUnavailable(f"Jarvis will not send your {self.preset.company} key "
                                 f"there: {why or 'no key'}.", "pinned")
        payload = {"model": self.model, "messages": messages, "stream": False}
        if self.preset.cap_field and self._cap > 0:
            # The hard stop: the service itself will not write past this.
            payload[self.preset.cap_field] = int(self._cap)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Authorization": "Bearer " + self._key})

    def _wait(self, seconds: float) -> bool:
        """False when the conversation was closed while waiting."""
        if self._sleep is not None:
            self._sleep(seconds)
            return not self._cancel.is_set()
        return not self._cancel.wait(seconds)

    def _work(self, messages: list) -> None:
        reply, err = None, None
        try:
            reply = self._post(messages)
        except ApiUnavailable as exc:
            err = exc
        except Exception as exc:  # pragma: no cover - a bug here must not hang the driver
            err = ApiUnavailable(f"Talking to {self.name} failed ({type(exc).__name__}).",
                                 "failed")
        with self._lock:
            self._reply, self._error = reply, err
        self._done.set()

    def _post(self, messages: list) -> str:
        retried = False
        while True:
            if self._cancel.is_set():
                raise ApiUnavailable(f"The conversation with {self.name} was closed.", "closed")
            req = self._request(messages)
            try:
                status, headers, body = _http(req, self.http_timeout)
            except _Redirected as exc:
                raise ApiUnavailable(REDIRECT.format(name=self.name, code=exc.code,
                                                     host=self.host), "redirect") from None
            except urllib.error.URLError as exc:
                if isinstance(getattr(exc, "reason", None), TimeoutError):
                    raise ApiUnavailable(TIMEOUT.format(name=self.name,
                                                        seconds=int(self.http_timeout)),
                                         "timeout") from None
                raise ApiUnavailable(NO_CONNECTION.format(host=self.host, error=type(
                    getattr(exc, "reason", exc)).__name__), "connection") from None
            except TimeoutError:
                raise ApiUnavailable(TIMEOUT.format(name=self.name,
                                                    seconds=int(self.http_timeout)),
                                     "timeout") from None
            except OSError as exc:
                raise ApiUnavailable(NO_CONNECTION.format(host=self.host,
                                                          error=type(exc).__name__),
                                     "connection") from None
            with self._lock:
                self._usage["requests"] += 1
            if status == 429 and not retried:
                wait = _retry_after(headers)
                wait = RETRY_DEFAULT if wait is None else wait
                if wait <= RETRY_CAP:
                    retried = True
                    with self._lock:
                        self._usage["retries"] += 1
                    if not self._wait(wait):
                        raise ApiUnavailable(f"The conversation with {self.name} was closed.",
                                             "closed")
                    continue
                raise ApiUnavailable(RATE_LIMITED_LONG.format(name=self.name,
                                                              seconds=int(wait)),
                                     "rate_limited")
            if status != 200:
                raise ApiUnavailable(status_words(status, self.preset, self.model),
                                     f"http_{status}")
            return self._parse(body, messages)

    def _parse(self, body: bytes, messages: Optional[list] = None) -> str:
        if len(body) > MAX_BODY:
            raise ApiUnavailable(f"{self.name}'s answer was larger than Jarvis reads "
                                 f"({MAX_BODY // 1_000_000} MB), so it was not used.", "too_big")
        try:
            got = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            got = None
        if not isinstance(got, dict):
            raise ApiUnavailable(UNREADABLE.format(name=self.name), "unreadable")
        use = got.get("usage")
        counts = {}
        if isinstance(use, dict):
            with self._lock:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    v = use.get(k)
                    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                        self._usage[k] += v
                        counts[k] = v
        text = _content(got)
        self._count_money(use, counts, messages or [], text)
        # Cut short by the cap Jarvis sent: "length" is the finish reason
        # OpenAI's, Groq's, Mistral's and OpenRouter's own code name for it
        # (xAI's grok-build has a Length reason too). Without a cap sent, a
        # "length" is not Jarvis's doing and gets no note.
        cut = bool(self.preset.cap_field and self._cap > 0
                   and _finish_reason(got) == "length")
        with self._lock:
            self._cut_off = cut
        if cut and (text is None or not text.strip()):
            raise ApiUnavailable(CUT_OFF_EMPTY.format(name=self.name), "cut_off")
        if text is None:
            raise ApiUnavailable(UNREADABLE.format(name=self.name), "unreadable")
        if not text.strip():
            raise ApiUnavailable(f"{self.name} sent back an empty answer.", "empty")
        return text


    def _count_money(self, use, counts: dict, messages: list, text: Optional[str]) -> None:
        """Add this answer to the month's count (record_spend) and to this
        conversation's `cost`. Counted even when the answer turns out
        unreadable or empty: the service charges for it all the same."""
        guessed = "prompt_tokens" not in counts or "completion_tokens" not in counts
        pt = counts.get("prompt_tokens")
        if pt is None:
            pt = int(math.ceil(sum(len(str(m.get("content") or "")) for m in messages
                                   if isinstance(m, dict)) / CHARS_PER_TOKEN))
        ct = counts.get("completion_tokens")
        if ct is None:
            ct = int(math.ceil(len(text or "") / CHARS_PER_TOKEN))
        real = None
        if self.preset.id == "openrouter_api" and isinstance(use, dict):
            # OpenRouter's own figure for this answer, in dollars, when it
            # sends one (its "usage accounting"); else the estimate.
            real = _num(use.get("cost"))
        try:
            got = record_spend(self.preset.id, self.model, pt, ct, real_dollars=real,
                               guessed=guessed)
        except Exception as exc:
            try:
                got = cost_of(self.preset.id, self.model, pt, ct) if real is None else real
            except Exception:       # the file cannot be read either
                got = None
            self._money_broken = (f"Jarvis could not write down what {self.name}'s last answer "
                                  f"cost ({type(exc).__name__}), so it cannot keep to your "
                                  f"money limit. Nothing more was sent.")
        with self._lock:
            self._usage["dollars"] = round(self._usage["dollars"] + float(got or 0.0), 8)
            self._usage["cost"] = dollars(self._usage["dollars"])


def _finish_reason(got: dict) -> str:
    """choices[0].finish_reason, or ""."""
    choices = got.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    fr = choices[0].get("finish_reason")
    return fr if isinstance(fr, str) else ""


def _content(got: dict) -> Optional[str]:
    """choices[0].message.content: a string, or a list of text parts."""
    choices = got.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        return None
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = [str(p.get("text") or "") for p in c
                 if isinstance(p, dict) and p.get("type") in ("text", "output_text")]
        return "".join(parts) if parts else None
    return None


# ============================================================================
#   Plain words
# ============================================================================

CANNOT_READ = ("Jarvis cannot read Windows Credential Manager on this computer, where the "
               "{name} key is kept.")
REDIRECT = ("{name} answered with a redirect (error {code}) to somewhere else. Jarvis never "
            "follows one, so your key stays with {host} only. Nothing more was sent.")
TIMEOUT = "{name} did not answer within {seconds} seconds. Nothing more was sent."
NO_CONNECTION = ("Jarvis could not reach {host} ({error}). Check this PC's internet "
                 "connection. Nothing more was sent.")
UNREADABLE = "{name} answered, but not in a shape Jarvis can read."
RATE_LIMITED = ("{name} says Jarvis is asking too often, or the account's limit is used up "
                "(error 429), even after waiting once. Nothing more was sent; try again later.")
RATE_LIMITED_LONG = ("{name} says Jarvis is asking too often (error 429) and asked it to "
                     "wait {seconds} seconds, which is longer than Jarvis waits. Nothing more "
                     "was sent; try again later.")


def no_key_words(p: Preset) -> str:
    return (f"No {p.company} API key is saved on this PC. To add one, run this one line in "
            f"PowerShell in Jarvis's folder, then paste the key (it will not show): "
            + KEY_LINE.format(short=p.short) + f" - keys are made at {p.key_where}. Then set "
            f"a monthly money limit, for example $5: "
            + LIMIT_LINE.format(short=p.short, amount=5))


def status_words(status: int, p: Preset, model: str) -> str:
    name = p.name
    if status in (401, 403):
        return (f"{name} did not accept the key saved on this PC (error {status}). Check it "
                f"at {p.key_where} and save it again: " + KEY_LINE.format(short=p.short))
    if status == 402:
        return f"{name} says the account has no credit left (error 402). Nothing more was sent."
    if status == 404:
        return (f"{name} does not know the model \"{model}\" (error 404). Change it with the "
                f"{MODEL_KEY(p.id)} line under [chatbot] in jarvis-framework.toml, then "
                f"restart Jarvis.")
    if status == 429:
        return RATE_LIMITED.format(name=name)
    if 500 <= status <= 599:
        return (f"{name} had a problem on its side (error {status}). Nothing more was sent; "
                f"try again later.")
    return f"{name} refused the message (error {status}). Nothing more was sent."


# ============================================================================
#   The registry
# ============================================================================

def ready_for(pid: str) -> str:
    """"" when a conversation can start; else why not, in plain words, with
    the one line that fixes it. Opens no socket."""
    p = PRESETS[pid]
    model, problem = model_for(pid)
    if problem:
        return f"{p.name} cannot be used: {problem}."
    saved = key_saved(pid)
    if saved is None:
        return CANNOT_READ.format(name=p.company)
    if not saved:
        return no_key_words(p)
    # No limit, no price, or this month's limit reached: not before a card.
    return money_problem(pid, model)


def _how(p: Preset, model: str) -> str:
    return (f"through its official API, model {model or '(not set)'}, with the "
            f"{p.company} key saved on this PC")


def _card_note(p: Preset) -> str:
    out = (f"Each message goes to {p.host} only, with your {p.company} key; the key is never "
           f"sent anywhere else, and a redirect is refused. Each message costs a little on "
           f"your {p.company} account: Jarvis estimates the cost from the word-pieces "
           f"(tokens) {p.company} reports and its price list, and stops before a message "
           f"that could pass the monthly money limit you set on the PC. "
           + (f"It also asks {p.company} to keep each answer short enough to stay within "
              f"that limit. " if p.cap_field else
              f"Jarvis cannot yet ask {p.company} to keep answers short (that setting could "
              f"not be checked), so it stops earlier instead. ")
           + f"What you send is kept under {p.company}'s own API terms.")
    if p.note:
        out += " " + p.note
    return out


def _factory_for(pid: str):
    def make() -> CB.Adapter:
        model, problem = model_for(pid)
        if problem:
            raise ApiUnavailable(f"{PRESETS[pid].name} cannot be used: {problem}.", "model")
        return ApiChatbot(PRESETS[pid], model)
    return make


def _register(pid: str) -> None:
    p = PRESETS[pid]
    model = (_MODELS.get(pid) or ("", ""))[0] or p.model
    CB.register_adapter(CB.AdapterInfo(
        p.id, p.name, p.host, _factory_for(pid), built=True, kind=KIND,
        how=_how(p, model), card_note=_card_note(p),
        ready=lambda pid=pid: ready_for(pid), money=lambda pid=pid: money_view(pid)))


for _pid in PRESETS:
    _register(_pid)


def point_at(pid: str, base_url: str) -> Preset:
    """Tests only: the same preset, pointed at a fake provider."""
    PRESETS[pid] = replace(PRESETS[pid], base_url=base_url)
    _register(pid)
    return PRESETS[pid]


# ============================================================================
#   The owner's command line
# ============================================================================

USAGE = ("Jarvis's chatbot API keys and money limits. Run in Jarvis's folder, in "
         "PowerShell:\n"
         "  py -3 jarvis_chatbot_api.py key <service>          save a key (pasted at a "
         "hidden prompt)\n"
         "  py -3 jarvis_chatbot_api.py forget-key <service>   remove it\n"
         "  py -3 jarvis_chatbot_api.py status                 which keys and limits are set\n"
         "  py -3 jarvis_chatbot_api.py limit <service> <dollars>   at most this much a month "
         "(\"none\" removes it, and the service is then not used)\n"
         "  py -3 jarvis_chatbot_api.py price <service> <in> <out>  correct a price: dollars "
         "per million word-pieces (tokens) in, then out (\"default\" goes back)\n"
         "  py -3 jarvis_chatbot_api.py spent                  this month's spending, the "
         "limits and the price list\n"
         "Services: " + ", ".join(sorted(BY_SHORT)))


def _amount(raw: str) -> Optional[float]:
    """"5", "5.50" or "$5" as dollars; None when it is not a number."""
    t = str(raw or "").strip().lstrip("$").replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def spent_lines() -> list:
    """What `spent` prints: per service, this month's estimate, the limit,
    and the price in use - each default price marked UNVERIFIED."""
    try:
        data = _load()
    except MoneyFileError as exc:
        return [_file_words(str(exc)) + ".", f"The file: {money_path()}"]
    lt = time.localtime(_now())
    out = [f"API spending in {MONTHS[lt.tm_mon - 1]} {lt.tm_year} (an estimate; the count "
           f"starts again on {next_month_words()}). Kept in {money_path()}."]
    for pid, p in PRESETS.items():
        model, problem = model_for(pid)
        limit = limit_of(pid, data)
        spent = spent_of(pid, data)
        pr = price_of(pid, model, data) if model else None
        if limit is None:
            lim = f"about {dollars(spent)} used, no limit set - so it is not used"
        else:
            lim = (f"about {dollars(spent)} of {dollars(limit)} used, about "
                   f"{dollars(max(0.0, limit - spent))} left")
        if pr is None:
            price = "none - set one before it can be used"
        elif pr[2] == "yours":
            price = f"${pr[0]:g} in, ${pr[1]:g} out per million word-pieces (your price)"
        else:
            price = (f"${pr[0]:g} in, ${pr[1]:g} out per million word-pieces (default written "
                     f"{PRICES_WRITTEN}, UNVERIFIED - check {p.price_page})")
        out.append(f"{p.short}: {p.name}, model {model or problem}: {lim}. Price: {price}. "
                   f"{cap_words(p)}")
    out.append("Prices change: check each against the company's price page and correct it "
               "with: " + PRICE_LINE.format(short="<service>"))
    return out


def cap_words(p: Preset) -> str:
    """How the limit is kept for one service, for `spent`: the answer-length
    cap and where its name was checked, and what hidden reasoning does."""
    if not p.cap_field:
        return (f"Answer length: NO CAP IS SENT - the name of that setting could not be "
                f"checked in {p.company}'s own documentation ({p.cap_source}). The only guard "
                f"is the check before each message, which assumes the longest answer "
                f"({MOST_REPLY_TOKENS:,} word-pieces) plus {REASONING_ROOM:,} for hidden "
                f"reasoning; a longer answer can still carry a month a little over.")
    out = (f"Answer length: capped with {p.cap_field} (at most {MOST_REPLY_TOKENS:,} "
           f"word-pieces, fewer as the month's limit nears; the name checked in "
           f"{p.cap_source}). ")
    if p.reasoning == "inside":
        return out + (f"{p.company}'s own words count hidden reasoning inside that cap, so the "
                      f"cap bounds the whole answer.")
    return out + (f"{p.company}'s own code does not say whether hidden reasoning counts inside "
                  f"that cap, so the check also keeps room for {REASONING_ROOM:,} word-pieces "
                  f"of it; longer hidden reasoning can still carry a month a little over.")


def _main(argv, *, ask_secret=None, out=print) -> int:
    if not argv:
        out(USAGE)
        return 2
    cmd = argv[0]
    if cmd in ("key", "forget-key"):
        if len(argv) != 2 or argv[1] not in BY_SHORT:
            out("Say which: " + ", ".join(sorted(BY_SHORT)) + ".")
            return 2
        pid = BY_SHORT[argv[1]]
        if cmd == "forget-key":
            r = forget_key(pid)
        else:
            if ask_secret is None:
                import getpass
                ask_secret = getpass.getpass
            value = ask_secret(f"Paste your {PRESETS[pid].company} API key (it will not "
                               f"show), then press Enter: ")
            r = save_key(pid, value or "")
        out(r.get("said") or f"Not saved: {r.get('error')}.")
        return 0 if r.get("ok") else 1
    if cmd == "status":
        for pid, p in PRESETS.items():
            k = key_saved(pid)
            model, problem = model_for(pid)
            try:
                limit = limit_of(pid)
            except MoneyFileError:
                limit = None
            out(f"{p.name} ({p.host}, model {model or problem}): "
                + ("key saved" if k else "no key" if k is False else "cannot be checked here")
                + (f", at most {dollars(limit)} a month" if limit is not None
                   else ", no money limit set"))
        return 0
    if cmd == "limit":
        if len(argv) != 3 or argv[1] not in BY_SHORT:
            out("Say which service and how many dollars a month, for example: "
                + LIMIT_LINE.format(short="openai", amount=5))
            return 2
        pid = BY_SHORT[argv[1]]
        if argv[2].strip().lower() == "none":
            r = set_limit(pid, None)
        else:
            amount = _amount(argv[2])
            if amount is None:
                out("Not set: the limit must be a number of dollars, for example 5 or 2.50.")
                return 1
            r = set_limit(pid, amount)
        out(r.get("said") or f"Not set: {r.get('error')}.")
        return 0 if r.get("ok") else 1
    if cmd == "price":
        if len(argv) not in (3, 4) or argv[1] not in BY_SHORT:
            out("Say which service and the two prices, for example: "
                "py -3 jarvis_chatbot_api.py price openai 0.25 2.00")
            return 2
        pid = BY_SHORT[argv[1]]
        model, problem = model_for(pid)
        if problem:
            out(f"Not set: {problem}.")
            return 1
        if len(argv) == 3 and argv[2].strip().lower() == "default":
            r = reset_price(pid, model)
        elif len(argv) == 4:
            pin, pout = _amount(argv[2]), _amount(argv[3])
            if pin is None or pout is None:
                out("Not set: each price must be a number of dollars per million "
                    "word-pieces, for example 0.25 and 2.00.")
                return 1
            r = set_price(pid, model, pin, pout)
        else:
            out("Say both prices (in, then out), or \"default\".")
            return 2
        out(r.get("said") or f"Not set: {r.get('error')}.")
        return 0 if r.get("ok") else 1
    if cmd == "spent":
        for line in spent_lines():
            out(line)
        return 0
    out(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
