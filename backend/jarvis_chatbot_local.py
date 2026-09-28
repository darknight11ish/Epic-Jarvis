"""jarvis_chatbot_local.py - "a second AI on this PC": the chatbot driver
talks to another Ollama model on THIS PC. Nothing leaves the PC.

NEW MODULE, shipped whole (like jarvis_chatbot.py, which it plugs into).
Reachable from both apps through /api/chatbot/* (jarvis_chatbot_routes.py,
docs/JARVIS-API.md section 60) once a model is chosen (local_model under
[chatbot]). NOT yet tried against a real Ollama on the owner's PC.

THE OWNER'S DECISION (CLAUDE.md, "The chatbot driver becomes versatile",
2026-09-28): "(3) a second AI on the owner's own PC (another local model,
best on the 12 GB card; nothing leaves the PC)".

WHAT IT TALKS TO
  * Ollama on this PC only: the address must be 127.0.0.1 / localhost / ::1
    (checked before every request, and requests never go through a proxy -
    jarvis_local_http.opener). A redirect is refused.
  * Never one of Ollama's cloud models: a name ending "-cloud" or ":cloud"
    is answered on ollama.com, not on this PC (docs/ARCHITECTURE.md section
    4, "The local model is also egress"), so it is refused - by
    jarvis_router.is_remote_model() and, as a second lock, by this file's
    own pattern - before any card and again before every request.
  * A model the PC ALREADY HAS: open() asks Ollama's list (/api/tags) and
    refuses a model that is not in it. Nothing is ever downloaded here.
  * The owner picks the model with one line under [chatbot] in
    jarvis-framework.toml: local_model = "<a name from `ollama list`>".
    Read once when Jarvis starts, so the card and the conversation always
    name the same model.

TWO VERSIONS, THE SAME CHECK THE CORE USES (jarvis_chatbot.choose_tier)
  * Both graphics cards (the core's full version: [chatbot] full_version on
    AND the second card's "Longer conversations" lane running): the other
    AI runs in the second card's Ollama - the lane jarvis_second_card
    starts, pinned to the 12 GB card. That lane holds one model at a time
    (OLLAMA_MAX_LOADED_MODELS=1), so when the chosen model is not the
    lane's own model, the card swaps between the two every message (a few
    seconds each; the card says so). A model bigger than LANE_MAX_BYTES on
    disk is refused: it would not fit the 12 GB card with room for its
    conversation.
  * One graphics card (the limited version): the 8 GB card has no room for
    a second model beside the everyday one (docs/MODEL-TOPOLOGY.md: at 16K
    the everyday model already fills it), and the core's one-card rule is
    "no extra graphics memory". So the ONLY model allowed is the one
    already loaded - the everyday model itself, at chat's own context size
    (no reload) - and it waits while the owner is chatting, like the
    driver. Any other model is `ready=False`: "needs your second graphics
    card". Said plainly on the card: on one card this is the same model
    Jarvis uses, given only the conversation - a fresh look, not a
    different AI.

OUTSIDE TEXT, STILL
Another model's words are not the owner's words: every reply is outside
text like any chatbot's (the core marks it), never learned from, never
read aloud. The core's last check still runs before every message, even
though nothing leaves the PC - the same rules everywhere, and the
transcript is shown to the owner.

    python3 test_chatbot_local.py

Standard library only. No I/O at import.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

import jarvis_chatbot as CB

ID = "local_ai"
NAME = "A second AI on this PC"
HOST = "this PC"
KIND = "local"
MODEL_KEY = "local_model"

#: The context size asked for a model that is not the lane's own (both
#: cards). The lane's own model, and the one-card model, keep their size so
#: Ollama never reloads them at another one.
LOCAL_NUM_CTX = 8192
#: The biggest model file allowed on the 12 GB card (about 9 GiB of weights,
#: leaving room for its conversation and the runtime: MODEL-TOPOLOGY's
#: "Qwen 3 14B Q4_K_M ... 8.42 GiB" is the largest it lists as fitting).
LANE_MAX_BYTES = 9 * 1024 ** 3
#: The longest wait for one answer, once the request is made. Inside the
#: driver's own reply timeout (jarvis_chatbot.REPLY_TIMEOUT), which does not
#: count the time spent first waiting for the owner's own chat
#: (waiting_for_owner() below) - so a slow answer after a long wait ends
#: with this module's own words, not a wrong "did not answer".
HTTP_TIMEOUT = 170.0
TAGS_TIMEOUT = 5.0
MAX_BODY = 4_000_000
MAX_HISTORY = 60
BUSY_POLL = 2.0

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,149}$")
#: A second lock behind jarvis_router.is_remote_model: "-cloud" or ":cloud"
#: anywhere in the tag ("gpt-oss:120b-cloud", "x:cloud", "y:cloud-large").
_CLOUD = re.compile(r"(?:[:-])cloud(?:\b|[-_.:])", re.I)
_THINK = re.compile(r"<think>.*?</think>\s*", re.S | re.I)
_LOOPBACK = ("127.0.0.1", "localhost", "::1")

NO_MODEL = ("Choose which model on this PC Jarvis should talk to: add the line "
            "local_model = \"<name>\" under [chatbot] in jarvis-framework.toml, using a name "
            "that `ollama list` shows, then restart Jarvis.")
CLOUD = ("\"{model}\" is one of Ollama's cloud models - it is answered on ollama.com, not "
         "on this PC - so Jarvis will not use it as the second AI on this PC. Choose a model "
         "that runs here.")
NEEDS_SECOND = ("\"{model}\" needs your second graphics card. On one card, the only model "
                "Jarvis can talk to without pushing its own chat model off the card is that "
                "same model ({main}); your 8 GB card has no room for a second one. The second "
                "card is used once it is installed and measured ([chatbot] full_version).")
NOT_HERE = ("The model Jarvis would talk to is not on this PC (its address is not 127.0.0.1), "
            "so Jarvis will not use it.")


class LocalUnavailable(RuntimeError):
    """The conversation cannot go on; `owner_words` says why, in plain words
    (jarvis_chatbot.run() shows it)."""

    def __init__(self, owner_words: str, code: str = ""):
        super().__init__(owner_words)
        self.owner_words = owner_words
        self.code = code


# ============================================================================
#   The checks
# ============================================================================

def is_cloud_model(name) -> bool:
    n = str(name or "").strip()
    try:
        import jarvis_router
        if jarvis_router.is_remote_model(n):
            return True
    except Exception:
        pass
    return bool(_CLOUD.search(n))


def is_loopback(url) -> bool:
    try:
        host = (urllib.parse.urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOOPBACK


def _same(a: str, b: str) -> bool:
    def n(x):
        x = str(x or "").strip().lower()
        return x[:-len(":latest")] if x.endswith(":latest") else x
    return bool(n(a)) and n(a) == n(b)


_MODEL: dict = {}
_MODEL_LOCK = threading.Lock()


def model_for() -> tuple:
    """(model, problem). Read ONCE per process (a change takes effect when
    Jarvis restarts), so the card and its conversation name the same model."""
    with _MODEL_LOCK:
        if "m" not in _MODEL:
            raw = CB._cfg().get(MODEL_KEY)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                _MODEL["m"] = ("", NO_MODEL)
            elif not isinstance(raw, str) or not _MODEL_RE.match(raw.strip()):
                _MODEL["m"] = ("", "the local_model line under [chatbot] in "
                                   "jarvis-framework.toml is not a model name")
            else:
                _MODEL["m"] = (raw.strip(), "")
            _register()
        return _MODEL["m"]


#: Tests replace these. None: the core's own.
_TIER: Optional[Callable[[], object]] = None
_OWNER_BUSY: Optional[Callable[[], bool]] = None


def _tier():
    return _TIER() if _TIER is not None else CB.choose_tier()


def _owner_busy() -> bool:
    try:
        return bool((_OWNER_BUSY or CB._default_owner_busy)())
    except Exception:
        return True


class Place:
    """Where the other AI runs: `url` (always this PC), `num_ctx`, which
    version, and the words for the card."""

    def __init__(self, url: str, num_ctx: int, tier: str, words: str, swaps: bool = False):
        self.url, self.num_ctx, self.tier, self.words, self.swaps = url, num_ctx, tier, \
            words, swaps


def placement(model: str) -> tuple:
    """(Place or None, problem). The core's own version check decides."""
    if not model:
        return None, NO_MODEL
    if is_cloud_model(model):
        return None, CLOUD.format(model=model)
    try:
        t = _tier()
    except Exception as exc:
        return None, f"Jarvis could not tell which graphics cards it may use ({type(exc).__name__})."
    url = str(getattr(t, "url", "") or "").rstrip("/")
    if not is_loopback(url):
        return None, NOT_HERE
    tid = getattr(t, "id", CB.ONE_CARD)
    lane_model = str(getattr(t, "model", "") or "")
    if tid == CB.TWO_CARDS:
        same = _same(model, lane_model)
        num_ctx = int(getattr(t, "num_ctx", 0) or LOCAL_NUM_CTX) if same else LOCAL_NUM_CTX
        words = (f"{model}, on your second graphics card"
                 + ("" if same else f" (that card holds one model at a time, so it swaps "
                                    f"between {model} and Jarvis's own {lane_model} every "
                                    f"message, a few seconds each)"))
        return Place(url, num_ctx, CB.TWO_CARDS, words, swaps=not same), ""
    if _same(model, lane_model):
        return Place(url, CB.ONE_CARD_NUM_CTX, CB.ONE_CARD,
                     f"{model}, on your graphics card - the same model Jarvis itself uses, "
                     f"given only this conversation: a fresh look, not a different AI. It "
                     f"waits while you chat with Jarvis"), ""
    return None, NEEDS_SECOND.format(model=model, main=lane_model or "the everyday model")


def ready() -> str:
    """"" when a conversation can start; else why not, in plain words. Opens
    no socket and wakes nothing ("What Jarvis can reach" asks this)."""
    model, problem = model_for()
    if problem:
        return problem
    if is_cloud_model(model):
        return CLOUD.format(model=model)
    if _TIER is None and CB._default_full_version_on():
        # With the full version switched on, which card is free is known only
        # by asking the second card's lane - and "What Jarvis can reach"
        # (which asks this) must never probe or wake anything. So say it
        # may run there; the factory decides for real when the conversation
        # opens, and stops in plain words before anything is sent if the
        # lane is not running and the model is not the everyday one.
        _register(f"{model}, on your second graphics card while its lane is running "
                  f"(if it is not, only Jarvis's everyday model can be used, and a "
                  f"conversation with another one stops before anything is sent)")
        return ""
    place, problem = placement(model)
    # The card is written right after this (jarvis_chatbot.plan), so it
    # names where the other AI runs NOW.
    _register(place.words if place else "")
    return problem


# ============================================================================
#   Talking to Ollama on this PC
# ============================================================================

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalUnavailable("Ollama on this PC answered with a redirect, which Jarvis "
                               "never follows.", "redirect")


class _Line:
    """One request's connection, so close() can abandon it from another
    thread: Ollama stops working on a request whose connection is closed,
    which frees the graphics card instead of finishing an answer nobody
    will read."""

    def __init__(self):
        self.aborted = False
        self.conn: Optional[http.client.HTTPConnection] = None

    def abort(self) -> None:
        self.aborted = True
        conn = self.conn
        sock = getattr(conn, "sock", None) if conn is not None else None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


class _LineHandler(urllib.request.HTTPHandler):
    """Plain http:// (loopback only, checked before) whose connection is
    kept in a _Line."""

    def __init__(self, line: _Line):
        super().__init__()
        self._line = line

    def http_open(self, req):
        line = self._line

        class Conn(http.client.HTTPConnection):
            def connect(self):
                super().connect()
                if line.aborted:
                    # close() came first: never send the request.
                    self.close()
                    raise LocalUnavailable("The conversation was closed.", "closed")

        def make(host, **kw):
            conn = Conn(host, **kw)
            line.conn = conn
            return conn
        return self.do_open(make, req)


#: Tests may replace this: (Request, timeout) -> (status, body bytes).
_HTTP = None


def _http(req: urllib.request.Request, timeout: float, line: Optional[_Line] = None) -> tuple:
    if not is_loopback(req.full_url):
        raise LocalUnavailable(NOT_HERE, "not_loopback")
    if _HTTP is not None:
        return _HTTP(req, timeout)
    import jarvis_local_http as LH
    extra = (_LineHandler(line),) if line is not None else ()
    try:
        with LH.opener(_RefuseRedirect, *extra).open(req, timeout=timeout) as r:
            return r.status, r.read(MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096) if exc.fp is not None else b""
        except Exception:
            body = b""
        return exc.code, body


def installed(url: str) -> Optional[dict]:
    """{name: size in bytes} of the models Ollama at `url` has, or None when
    it does not answer. Loopback only."""
    req = urllib.request.Request(str(url).rstrip("/") + "/api/tags", method="GET")
    try:
        status, body = _http(req, TAGS_TIMEOUT)
        got = json.loads(body.decode("utf-8", "replace")) if status == 200 else None
    except LocalUnavailable:
        raise
    except Exception:
        return None
    if not isinstance(got, dict):
        return None
    out = {}
    for m in got.get("models") or []:
        if isinstance(m, dict) and isinstance(m.get("name"), str):
            size = m.get("size")
            out[m["name"]] = size if isinstance(size, int) else 0
    return out


def _find(models: dict, model: str) -> Optional[str]:
    return next((n for n in models if _same(n, model)), None)


class LocalChatbot(CB.Adapter):
    """One conversation with another model on this PC. send() starts the
    request on its own thread; read_reply() waits in the driver's slices."""

    def __init__(self, model: str, place: Place):
        self.id, self.name, self.host = ID, NAME, HOST
        self.model, self.place = model, place
        self._history: list = []
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._cancel = threading.Event()
        self._busy = False
        #: True while the request waits for the owner's own chat (one card).
        self._held = False
        self._line: Optional[_Line] = None
        self._reply: Optional[str] = None
        self._error: Optional[LocalUnavailable] = None
        self._opened = self._closed = False
        self._usage = {"model": model, "requests": 0, "prompt_tokens": 0,
                       "completion_tokens": 0, "total_tokens": 0, "where": place.tier}

    def open(self) -> None:
        if is_cloud_model(self.model):
            raise LocalUnavailable(CLOUD.format(model=self.model), "cloud")
        if not is_loopback(self.place.url):
            raise LocalUnavailable(NOT_HERE, "not_loopback")
        models = installed(self.place.url)
        if models is None:
            raise LocalUnavailable("Ollama on this PC did not answer, so the second AI cannot "
                                   "start. Check that Ollama is running.", "no_ollama")
        name = _find(models, self.model)
        if name is None:
            raise LocalUnavailable(f"\"{self.model}\" is not on this PC (Ollama does not list "
                                   f"it). Jarvis never downloads a model for this - choose one "
                                   f"that `ollama list` shows.", "not_installed")
        if self.place.tier == CB.TWO_CARDS and models.get(name, 0) > LANE_MAX_BYTES:
            raise LocalUnavailable(f"\"{self.model}\" is too big for the second graphics card "
                                   f"with room for a conversation. Choose a smaller model.",
                                   "too_big")
        self._opened = True

    def send(self, text: str) -> None:
        with self._lock:
            if self._closed or not self._opened:
                raise LocalUnavailable("The conversation with the second AI is closed.",
                                       "closed")
            if self._busy:
                raise LocalUnavailable("The second AI is still answering.", "busy")
            self._history.append({"role": "user", "content": str(text)})
            self._history = self._history[-MAX_HISTORY:]
            messages = [dict(m) for m in self._history]
            self._busy, self._reply, self._error = True, None, None
            self._done.clear()
        threading.Thread(target=self._work, args=(messages,), name="jarvis-chatbot-local",
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

    def waiting_for_owner(self) -> bool:
        """True while the message has not been handed to the other AI yet
        because the owner's own chat comes first (one card). The driver
        does not count this time against its reply limit - the other AI
        has not been asked yet - and says it is waiting for the owner."""
        return self._held and not self._closed

    def close(self) -> None:
        """Stop waiting and abandon any request on its way: the connection
        to Ollama is closed, so Ollama stops that answer and the graphics
        card is free again. Safe from any thread, twice."""
        with self._lock:
            self._closed = True
            self._history = []
            line = self._line
        self._cancel.set()
        if line is not None:
            line.abort()

    def usage(self) -> dict:
        with self._lock:
            return dict(self._usage)

    # ---- the request ------------------------------------------------------

    def _work(self, messages: list) -> None:
        reply, err = None, None
        try:
            if self.place.tier == CB.ONE_CARD:
                # The owner's own chat comes first on one card. No limit of
                # its own: the driver does not count this wait against its
                # reply limit (waiting_for_owner), the conversation's minutes
                # still count it (the card says so), and close() ends it.
                self._held = True
                try:
                    while _owner_busy():
                        if self._cancel.wait(BUSY_POLL):
                            raise LocalUnavailable("The conversation was closed.", "closed")
                finally:
                    self._held = False
            reply = self._post(messages)
        except LocalUnavailable as exc:
            err = exc
        except Exception as exc:  # pragma: no cover - must not hang the driver
            err = LocalUnavailable(f"Talking to the second AI failed ({type(exc).__name__}).",
                                   "failed")
        if self._cancel.is_set():
            # Closed while it worked: whatever came back is not handed on.
            reply, err = None, LocalUnavailable("The conversation was closed.", "closed")
        with self._lock:
            self._reply, self._error = reply, err
        self._done.set()

    def _post(self, messages: list) -> str:
        if is_cloud_model(self.model):
            raise LocalUnavailable(CLOUD.format(model=self.model), "cloud")
        body = json.dumps({"model": self.model, "messages": messages, "stream": False,
                           "options": {"num_ctx": int(self.place.num_ctx)}},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.place.url.rstrip("/") + "/api/chat", data=body,
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
        line = _Line()
        with self._lock:
            if self._closed:
                raise LocalUnavailable("The conversation was closed.", "closed")
            self._line = line
        try:
            status, raw = _http(req, HTTP_TIMEOUT, line)
        except LocalUnavailable:
            raise
        except (TimeoutError, urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            if line.aborted:
                raise LocalUnavailable("The conversation was closed.", "closed") from None
            if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None),
                                                          TimeoutError):
                raise LocalUnavailable(f"The second AI did not answer within "
                                       f"{int(HTTP_TIMEOUT)} seconds.", "timeout") from None
            raise LocalUnavailable("Ollama on this PC did not answer. Check that it is "
                                   "running.", "no_ollama") from None
        finally:
            with self._lock:
                if self._line is line:
                    self._line = None
        with self._lock:
            self._usage["requests"] += 1
        if status != 200:
            raise LocalUnavailable(f"Ollama on this PC refused the message (error {status}).",
                                   f"http_{status}")
        try:
            got = json.loads(raw[:MAX_BODY].decode("utf-8", "replace"))
        except ValueError:
            got = None
        msg = got.get("message") if isinstance(got, dict) else None
        text = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(text, str):
            raise LocalUnavailable("The second AI answered, but not in a shape Jarvis can "
                                   "read.", "unreadable")
        with self._lock:
            for src, dst in (("prompt_eval_count", "prompt_tokens"),
                             ("eval_count", "completion_tokens")):
                v = got.get(src)
                if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                    self._usage[dst] += v
                    self._usage["total_tokens"] += v
        text = _THINK.sub("", text).strip()
        if not text:
            raise LocalUnavailable("The second AI sent back an empty answer.", "empty")
        return text


# ============================================================================
#   The registry
# ============================================================================

def _factory() -> CB.Adapter:
    model, problem = model_for()
    if problem:
        raise LocalUnavailable(problem, "model")
    place, problem = placement(model)
    if place is None:
        raise LocalUnavailable(problem, "placement")
    return LocalChatbot(model, place)


def _how(where: str = "") -> str:
    model = (_MODEL.get("m") or ("", ""))[0]
    return ("another AI model through Ollama on this PC: "
            + (where or (model or "not chosen yet")))


CARD_NOTE = ("Nothing leaves this PC: the other AI runs in Ollama here, and never one of "
             "Ollama's cloud models. Its words are still outside text - another model's words "
             "are not yours - so they are shown to you, never learned from and never read "
             "aloud, and every message Jarvis writes is still checked first.")


def _register(where: str = "") -> None:
    CB.register_adapter(CB.AdapterInfo(
        ID, NAME, HOST, _factory, built=True, kind=KIND, how=_how(where),
        card_note=CARD_NOTE, ready=ready))


_register()


def where_words() -> str:
    """Where the other AI would run right now, for the card and the apps."""
    model, problem = model_for()
    if problem:
        return problem
    place, problem = placement(model)
    return place.words if place else problem


def _reset_for_tests() -> None:
    with _MODEL_LOCK:
        _MODEL.clear()
    _register()


def _main(argv, *, out=print) -> int:
    if argv[:1] == ["models"]:
        t = _tier()
        url = str(getattr(t, "url", "") or "")
        got = installed(url) if is_loopback(url) else None
        if got is None:
            out("Ollama on this PC did not answer.")
            return 1
        for n in sorted(got):
            out(n + ("   (a cloud model - not allowed)" if is_cloud_model(n) else ""))
        return 0
    if argv[:1] == ["status"]:
        out(ready() or "Ready: " + where_words())
        return 0
    out("Jarvis's second AI on this PC. Run in Jarvis's folder, in PowerShell:\n"
        "  py -3 jarvis_chatbot_local.py models   the models this PC has\n"
        "  py -3 jarvis_chatbot_local.py status   whether it can be used now, and where\n"
        "Choose one with local_model = \"<name>\" under [chatbot] in jarvis-framework.toml.")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
