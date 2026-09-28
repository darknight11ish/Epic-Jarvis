"""jarvis_brain_reads.py - the Brain upgrades' two read-only routes.

The owner's choice of 2026-09-28 (docs/RESEARCH-AUDIT-2026-09-28.md section
8, "Brain upgrades"); docs/JARVIS-API.md section 71 is the contract.

    GET /api/history/search?q=<words>&limit=<n>
        "Search what was said in old chats": the kept conversations whose
        messages hold every search word, newest first, each with a short
        snippet. jarvis_chat_log.ChatLog.search() does the work - it opens
        each kept turn IN MEMORY for this one search and keeps no index, no
        copy and no record of the words searched for.

    GET /api/memory/fact-history?id=<fact id>
        "History of this fact": every earlier (and later) version of one
        fact, oldest first. jarvis_memory.fact_history_view() does the work;
        an erased version never comes with its words.

Both are READS for the apps' Brain screens, behind the pairing token and
the origin check like every memory and history read. Neither is a tool: no
model and no chat turn can call them (jarvis_agent.py offers nothing that
reaches here), so what they return never reaches the AI model. Neither
writes anything.

Wired the same way as jarvis_news.py and jarvis_sources.py: install() wraps
the server's Handler.do_GET before anything listens, answers these two
paths, and passes every other request to the original, untouched
(brain-reads.patch is that one call). Without this module, or with an older
jarvis_chat_log.py / jarvis_memory.py that lacks the functions, each route
answers 501 with a sentence saying to update, and nothing else changes.
"""
from __future__ import annotations

from urllib.parse import urlsplit

SEARCH_PATH = "/api/history/search"
FACT_HISTORY_PATH = "/api/memory/fact-history"
PATHS = (SEARCH_PATH, FACT_HISTORY_PATH)

UPDATE = ("This PC's Jarvis is missing part of this feature. Run apply-patches.ps1 on the PC "
          "to update it.")


def handle_get(path: str, query: str = "") -> tuple:
    """(http status, reply) for one of PATHS. Never raises."""
    if path == SEARCH_PATH:
        try:
            import jarvis_chat_log
        except Exception:
            return 503, {"error": "chat history is not installed on this PC, so there is "
                                  "nothing to search"}
        if not hasattr(jarvis_chat_log, "search"):
            return 501, {"error": UPDATE}
        try:
            return jarvis_chat_log.handle_get(SEARCH_PATH, query)
        except Exception as exc:
            return 500, {"error": type(exc).__name__}
    if path == FACT_HISTORY_PATH:
        try:
            import jarvis_memory
        except Exception:
            return 503, {"error": "memory layer not importable"}
        handler = getattr(jarvis_memory, "handle_fact_history_get", None)
        if handler is None:
            return 501, {"error": UPDATE}
        try:
            return handler(query)
        except Exception as exc:
            return 500, {"error": type(exc).__name__}
    return 404, {"error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body=None) -> str:
    """Wrap `handler_cls.do_GET` so PATHS are answered here, after the
    server's own origin and token checks; every other request goes straight
    to the original `do_GET`. `read_body` is taken only for the signature
    the other install() functions share (both routes are GET-only)."""
    if getattr(handler_cls.do_GET, "_jarvis_brain_reads", False):
        return "  brain      Search old chats and fact history (already on)"
    get0 = handler_cls.do_GET

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
        parsed = urlsplit(str(getattr(self, "path", "") or ""))
        route = parsed.path.rstrip("/")
        if route not in PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        code, out = handle_get(route, parsed.query)
        return self._send(code, out)

    do_GET._jarvis_brain_reads = True
    handler_cls.do_GET = do_GET
    return "  brain      Search old chats and fact history: on"
