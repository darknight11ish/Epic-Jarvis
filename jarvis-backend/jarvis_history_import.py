"""jarvis_history_import.py - "Bring in chats from ChatGPT, Claude, Gemini or DeepSeek".

The owner's choice of 2026-09-28 (docs/RESEARCH-AUDIT-2026-09-28.md section 3,
idea 13); docs/JARVIS-API.md section 85 is the contract.

NEW MODULE, shipped whole, beside import_history.py (also shipped now).
history-import.patch adds one call at start-up, `install(Handler, ...)`,
which answers three routes (the same shape as jarvis_photo_remind.py):

    GET  /api/memory/import_chats          where a run is: counts, in words
    POST /api/memory/import_chats/start    {"path": "<the export file>"}
    POST /api/memory/import_chats/cancel   stop after the chat being read

WHAT IT DOES
The Brain's Memory page on the PC lets the owner pick a ChatGPT, Claude or
Gemini export (.zip or .json). This runs import_history.run() - the SAME
function the command line uses - on a background thread: which export it is
is worked out from the file, each conversation's OWNER'S OWN messages are
handed to jarvis_extract.propose() (never the other assistant's replies),
and every possible fact it finds lands in the review queue, "Waiting for
you", as one card. NOTHING IS SAVED BY ITSELF: an imported card is never
saved automatically (jarvis_auto_learn.check_source refuses every "import"
source), there is no approve-all, and when the queue is full the run pauses
and says so - the owner says yes or no to some cards and presses the button
again to carry on. The progress file (import_history.PROGRESS_FILE) means a
chat already read is never read twice.

WHO MAY START IT: this PC only (jarvis_owner_check.from_this_pc) - the file
is on this PC, and a path from any other device names nothing there. No
approval card: the owner picked the file here, and a run only PROPOSES; each
fact still gets its own card and its own yes. Cancel is allowed from either
app: it only makes Jarvis do less.

WHAT LEAVES THIS PC: nothing. The file is read from disk; the only model
asked is the one on this PC (run() refuses to start otherwise, and so does
propose() itself). So Lockdown (section 75) has nothing to stop here.

WHAT IS KEPT: counts only, in memory, until the backend restarts - never the
file's name or path, never a word of a chat. Nothing about a run is printed
to backend.log except counts; the audit log gets counts and the outcome.
The chats themselves are NOT put into the owner's own chat History (the
command line never did either).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    import jarvis_framework as fw  # type: ignore
except Exception:  # pragma: no cover - the tests stand one in
    fw = None

PATH = "/api/memory/import_chats"
START_ROUTE = "/api/memory/import_chats/start"
CANCEL_ROUTE = "/api/memory/import_chats/cancel"

#: The file must be one of these. The Windows picker offers only these too.
SUFFIXES = (".zip", ".json")
#: A bigger file than this is refused before anything is read (ChatGPT's own
#: exports run to a few hundred megabytes for years of chats).
MAX_BYTES = 8 * 1024 * 1024 * 1024

ABOUT = ("Jarvis reads only what you wrote in those chats - never the other "
         "assistant's replies - on this PC, with the AI model on this PC. Every "
         "possible fact waits under “Waiting for you” for your yes, one at a "
         "time; nothing is saved by itself. The chats are not added to your History. "
         "It can take hours for a big export, and Jarvis may answer more slowly "
         "while it runs.")

PC_ONLY = ("Old chats are brought in on the PC only: the export file is on the PC "
           "(Brain, Memory).")

LABELS = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini",
          "deepseek": "DeepSeek"}

_LOCK = threading.Lock()
_CANCEL = threading.Event()
_STATE: dict = {}


def _fresh() -> dict:
    return {"state": "idle", "outcome": None, "kind": None, "read": 0, "before": 0,
            "offered": 0, "nothing": 0, "waiting": 0, "started": None,
            "finished": None, "why": ""}


_STATE.update(_fresh())


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _counts(st: dict) -> str:
    return (f"{_plural(st['read'], 'chat', 'chats')} read, "
            f"{_plural(st['waiting'], 'possible fact', 'possible facts')} waiting for "
            f"your yes")


def words(st: dict) -> str:
    """One plain sentence (or two) for where a run is. Counts only."""
    src = LABELS.get(st.get("kind") or "", "")
    state, outcome = st.get("state"), st.get("outcome")
    before = int(st.get("before") or 0)
    again = (f" {_plural(before, 'chat was', 'chats were')} read before and skipped."
             if before else "")
    if state == "idle":
        return ("Bring in your old chats from ChatGPT, Claude, Gemini or DeepSeek: choose the "
                "export file on this PC.")
    if state == "running":
        if not st.get("kind"):
            return "Looking at the file…"
        return (f"Reading your {src} chats… {_plural(st['read'], 'chat', 'chats')} "
                f"read so far, {_plural(st['waiting'], 'possible fact', 'possible facts')} "
                f"waiting for your yes.")
    if state == "stopping":
        return (f"Stopping after the chat Jarvis is reading now… {_counts(st)}.")
    if outcome == "done":
        return f"Done: {_counts(st)}.{again}"
    if outcome == "queue_full":
        return (f"Paused, because “Waiting for you” is full: {_counts(st)}. "
                f"Say yes or no to some of the cards there, then press the button again "
                f"to carry on.")
    if outcome == "cancelled":
        return (f"Stopped: {_counts(st)}. Press the button again with the same file "
                f"to carry on where it stopped.")
    if outcome == "empty":
        return ("Nothing was brought in: no chats were found in that file. Choose the "
                ".zip file ChatGPT, Claude, DeepSeek or Google sent you (for Gemini, "
                "Google Takeout set to JSON, not HTML).")
    if outcome == "not_export":
        return ("Nothing was brought in: that file is not a ChatGPT, Claude, Gemini or DeepSeek "
                "export Jarvis can read. Choose the .zip file they sent you.")
    if outcome == "no_model":
        return (f"Paused, because Jarvis's AI model on this PC did not answer: {_counts(st)}. "
                f"The chat it was reading is not marked as read. Once Jarvis answers "
                f"again, press the button again with the same file to carry on.")
    why = st.get("why") or "something went wrong while reading the file"
    if not st.get("read"):
        return f"Nothing was brought in: {why}."
    return f"Stopped early: {why}. {_counts(st)[0].upper()}{_counts(st)[1:]}."


def view(*, here: bool = False) -> dict:
    with _LOCK:
        st = dict(_STATE)
    return {"ok": True, "available": True, "state": st["state"],
            "outcome": st["outcome"], "kind": st["kind"],
            "source": LABELS.get(st["kind"] or "", None),
            "read": st["read"], "before": st["before"], "offered": st["offered"],
            "nothing": st["nothing"], "waiting": st["waiting"],
            "started": st["started"], "finished": st["finished"],
            "words": words(st), "about": ABOUT, "here": bool(here)}


# --------------------------------------------------------------------------
#   The run
# --------------------------------------------------------------------------

def _audit(detail: dict) -> None:
    # Counts and the outcome. Never the file, never a word of a chat.
    try:
        if fw is not None:
            fw.audit_log("history_import", detail)
    except Exception:
        pass


def _quiet(_line: str) -> None:
    """run()'s lines name the file and its path: kept out of backend.log."""
    return None


def _set(**kw) -> None:
    with _LOCK:
        _STATE.update(kw)


def _run(path: Path, importer) -> None:
    outcome, why = "failed", ""
    try:
        kind = importer.detect_kind(path)
        if not kind:
            outcome = "not_export"
            return
        _set(kind=kind)

        def step(summary: dict) -> None:
            _set(read=int(summary.get("read") or 0),
                 before=int(summary.get("before") or 0),
                 offered=int(summary.get("offered") or 0),
                 nothing=int(summary.get("nothing") or 0),
                 waiting=int(summary.get("waiting") or 0))

        code = importer.run([(kind, path)], say=_quiet, on_step=step,
                            cancelled=_CANCEL.is_set)
        summary = dict(getattr(importer, "SUMMARY", {}) or {})
        step(summary)
        stopped = summary.get("stopped") or "done"
        if code == 2 or stopped == "refused":
            outcome = "failed"
            why = "Jarvis's learning model is not on this PC, so nothing was sent to it"
        elif stopped in ("done", "queue_full", "cancelled", "empty", "no_model"):
            outcome = stopped
        else:
            outcome = "failed"
    except Exception as exc:
        outcome, why = "failed", f"the file could not be read ({type(exc).__name__})"
    finally:
        _set(state="finished", outcome=outcome, why=why, finished=time.time())
        with _LOCK:
            st = dict(_STATE)
        _audit({"kind": st["kind"], "outcome": outcome, "read": st["read"],
                "offered": st["offered"], "waiting": st["waiting"]})
        _CANCEL.clear()


def _importer():
    import import_history
    return import_history


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False     # cannot tell: not this PC (fail closed)


def _check_file(raw) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("choose the export file first")
    p = Path(raw.strip())
    if not p.is_absolute():
        raise ValueError("that is not a full path to a file on this PC")
    if p.suffix.lower() not in SUFFIXES:
        raise ValueError("choose the .zip (or .json) file the export came as")
    try:
        if not p.is_file():
            raise ValueError("that file is not there any more")
        if p.stat().st_size > MAX_BYTES:
            raise ValueError("that file is too big to be a chat export")
    except OSError:
        raise ValueError("that file cannot be opened")
    return p


def start(body, *, here: bool, importer=None, spawn=None) -> tuple:
    """POST /api/memory/import_chats/start {"path"}. This PC only; no card."""
    if not here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"path": "<the export file>"}'}
    try:
        path = _check_file(body.get("path"))
    except ValueError as exc:
        return 400, {"ok": False, "error": f"Nothing was brought in: {exc}."}
    try:
        importer = importer or _importer()
        import jarvis_extract as X  # the owner's learning queue
    except Exception:
        return 503, {"available": False,
                     "error": "Bringing in old chats needs Jarvis's learning on this PC. "
                              "Run apply-patches.ps1 on the PC."}
    if not importer.local_model_ok(X):
        return 409, {"ok": False,
                     "error": "Nothing was brought in: Jarvis's learning model is not on "
                              "this PC (OLLAMA_URL points somewhere else), and your chats "
                              "would have been sent there."}
    with _LOCK:
        if _STATE["state"] in ("running", "stopping"):
            return 409, {"ok": False, "error": "Jarvis is already bringing in chats. "
                                               "Stop it first, or let it finish."}
        _STATE.clear()
        _STATE.update(_fresh())
        _STATE.update(state="running", started=time.time())
    _CANCEL.clear()
    job = (lambda: _run(path, importer))
    (spawn or _spawn)(job)
    return 202, dict(view(here=True), started_now=True)


def _spawn(fn) -> None:
    threading.Thread(target=fn, name="jarvis-history-import", daemon=True).start()


def cancel() -> tuple:
    """POST /api/memory/import_chats/cancel. Either app; it only does less."""
    with _LOCK:
        running = _STATE["state"] == "running"
        if running:
            _STATE["state"] = "stopping"
    if running:
        _CANCEL.set()
    return 200, dict(view(), cancelling=running)


# --------------------------------------------------------------------------
#   The routes - wrapped round the server's handler (history-import.patch)
# --------------------------------------------------------------------------

def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the three routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_history_import", False):
        return "  old chats  Bring in chats from ChatGPT, Claude, Gemini or DeepSeek (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = 200, view(here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in (START_ROUTE, CANCEL_ROUTE):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            if route == CANCEL_ROUTE:
                code, out = cancel()
            else:
                code, out = start(body, here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_history_import = True
    do_POST._jarvis_history_import = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  old chats  Bring in chats from ChatGPT, Claude, Gemini or DeepSeek: every fact "
            "waits for your yes")


def _reset_for_tests() -> None:
    with _LOCK:
        _STATE.clear()
        _STATE.update(_fresh())
    _CANCEL.clear()
