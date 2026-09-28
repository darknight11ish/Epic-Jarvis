"""jarvis_chatbot_api.py - the chatbot driver's API adapters: Jarvis talks to
ChatGPT, DeepSeek, Mistral, Grok, OpenRouter or Groq through each company's
official API, with a key the owner saved on this PC.

NEW MODULE, shipped whole (like jarvis_chatbot.py, which it plugs into, and
jarvis_chatbot_gemini.py beside it). Reachable from both apps through
/api/chatbot/* (jarvis_chatbot_routes.py, docs/JARVIS-API.md section 60)
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
                                                      UNVERIFIED (that SDK speaks gRPC)
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

MONEY
The core has no money cap yet (docs/CHATBOT-DRIVER-DESIGN.md planned one;
it is not built). So this adapter RECORDS what each answer's `usage` says -
word-pieces (tokens) in and out, and requests - for the session view
(usage()), and the card says plainly that the message limit on the card is
what bounds the cost. No price is guessed.

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
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
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
           "openai/openai-python _client.py"),
    Preset("deepseek_api", "deepseek", "DeepSeek (API)", "DeepSeek",
           "https://api.deepseek.com", "deepseek-chat",
           "https://platform.deepseek.com/api_keys",
           "unverified"),
    Preset("mistral_api", "mistral", "Mistral (API)", "Mistral AI",
           "https://api.mistral.ai/v1", "mistral-small-latest",
           "https://console.mistral.ai/api-keys",
           "mistralai/client-python README and chat.py"),
    Preset("xai_api", "xai", "Grok (xAI API)", "xAI",
           "https://api.x.ai/v1", "grok-4.6",
           "https://console.x.ai",
           "host from xai-org/xai-sdk-python; the /v1/chat/completions path unverified"),
    Preset("openrouter_api", "openrouter", "OpenRouter (API)", "OpenRouter",
           "https://openrouter.ai/api/v1", "openai/gpt-5-mini",
           "https://openrouter.ai/keys",
           "OpenRouterTeam/typescript-sdk lib/config.ts",
           note=("OpenRouter passes each message on to the company that runs the model "
                 "you chose (for the default, OpenAI), under that company's terms too.")),
    Preset("groq_api", "groq", "Groq (API)", "Groq",
           "https://api.groq.com/openai/v1", "openai/gpt-oss-20b",
           "https://console.groq.com/keys",
           "groq/groq-python _client.py and completions.py"),
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
                       "completion_tokens": 0, "total_tokens": 0, "retries": 0}

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
            self._history.append({"role": "user", "content": str(text)})
            self._history = self._history[-MAX_HISTORY:]
            messages = [dict(m) for m in self._history]
            self._busy, self._reply, self._error = True, None, None
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
        """What the service reported, for the session view. Counts only."""
        with self._lock:
            return dict(self._usage)

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
        body = json.dumps({"model": self.model, "messages": messages, "stream": False},
                          ensure_ascii=False).encode("utf-8")
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
            return self._parse(body)

    def _parse(self, body: bytes) -> str:
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
        if isinstance(use, dict):
            with self._lock:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    v = use.get(k)
                    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                        self._usage[k] += v
        text = _content(got)
        if text is None:
            raise ApiUnavailable(UNREADABLE.format(name=self.name), "unreadable")
        if not text.strip():
            raise ApiUnavailable(f"{self.name} sent back an empty answer.", "empty")
        return text


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
            + KEY_LINE.format(short=p.short) + f" - keys are made at {p.key_where}.")


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
    return ""


def _how(p: Preset, model: str) -> str:
    return (f"through its official API, model {model or '(not set)'}, with the "
            f"{p.company} key saved on this PC")


def _card_note(p: Preset) -> str:
    out = (f"Each message goes to {p.host} only, with your {p.company} key; the key is never "
           f"sent anywhere else, and a redirect is refused. Each message costs a little on "
           f"your {p.company} account: Jarvis counts the word-pieces (tokens) {p.company} "
           f"reports and shows them, but there is no money limit yet - the message limit on "
           f"this card is what limits the cost. What you send is kept under {p.company}'s own "
           f"API terms.")
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
        ready=lambda pid=pid: ready_for(pid)))


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

USAGE = ("Jarvis's chatbot API keys. Run in Jarvis's folder, in PowerShell:\n"
         "  py -3 jarvis_chatbot_api.py key <service>          save a key (pasted at a "
         "hidden prompt)\n"
         "  py -3 jarvis_chatbot_api.py forget-key <service>   remove it\n"
         "  py -3 jarvis_chatbot_api.py status                 which keys are saved\n"
         "Services: " + ", ".join(sorted(BY_SHORT)))


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
            out(f"{p.name} ({p.host}, model {model or problem}): "
                + ("key saved" if k else "no key" if k is False else "cannot be checked here"))
        return 0
    out(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
