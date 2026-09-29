"""jarvis_brain_reads.py - the Brain's read-only routes (the Brain upgrades, and a chat's facts).

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

    GET /api/memory/conversation-facts?conversation_id=<id>
        (2026-09-28; JARVIS-API section 79) "Facts this chat taught": the
        facts still in use whose meta says they were learned in that
        conversation, for History's "delete this chat" to offer forgetting
        them. jarvis_memory.conversation_facts_view() does the work. It
        forgets nothing: each ticked fact is then forgotten through the
        ordinary Forget route, one at a time.

    GET /api/memory/fact-chat?id=<fact id>
        (the chat audit, 2026-09-28) "Which chat did this fact come from?":
        for "Erase the words"'s "Also delete the chat it came from", which
        now names that chat - its title and when - before asking, and does
        not offer to delete a chat that is not on record. The fact's own
        meta names the conversation; jarvis_chat_log.brief() gives its
        title without opening a message. It deletes nothing.

    GET /api/pc/help
        (2026-09-28; JARVIS-API section 84) "PC help": five plain answers
        about this PC - why it is slow, how full the drives are, what is using
        the graphics card, how hot it is, when it last restarted.
        jarvis_pc_help.read() does the work, on this PC only; the program
        names in it are never logged or kept. It changes nothing.

All four are READS for the apps' Brain screens, behind the pairing token and
the origin check like every memory and history read. Neither is a tool: no
model and no chat turn can call them (jarvis_agent.py offers nothing that
reaches here), so what they return never reaches the AI model. Neither
writes anything.

"Widgets you describe" (2026-09-28; JARVIS-API section 86) rides on this
module's install() too, so it needs no patch of its own: install() also
calls jarvis_widgets.install(), which wraps do_GET and do_POST for the
/api/widgets routes (the list, one widget filled in, and the draft, add,
discard and delete POSTs) behind the same token and origin checks. Without
jarvis_widgets.py the banner says so and those routes are simply not there.

Wired the same way as jarvis_news.py and jarvis_sources.py: install() wraps
the server's Handler.do_GET before anything listens, answers these two
paths, and passes every other request to the original, untouched
(brain-reads.patch is that one call). Without this module, or with an older
jarvis_chat_log.py / jarvis_memory.py that lacks the functions, each route
answers 501 with a sentence saying to update, and nothing else changes.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlsplit

SEARCH_PATH = "/api/history/search"
FACT_HISTORY_PATH = "/api/memory/fact-history"
CONVERSATION_FACTS_PATH = "/api/memory/conversation-facts"
PC_HELP_PATH = "/api/pc/help"
FACT_CHAT_PATH = "/api/memory/fact-chat"
PATHS = (SEARCH_PATH, FACT_HISTORY_PATH, CONVERSATION_FACTS_PATH, PC_HELP_PATH, FACT_CHAT_PATH)

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
    if path == CONVERSATION_FACTS_PATH:
        try:
            import jarvis_memory
        except Exception:
            return 503, {"error": "memory layer not importable"}
        handler = getattr(jarvis_memory, "handle_conversation_facts_get", None)
        if handler is None:
            return 501, {"error": UPDATE}
        try:
            return handler(query)
        except Exception as exc:
            return 500, {"error": type(exc).__name__}
    if path == PC_HELP_PATH:
        try:
            import jarvis_pc_help
        except Exception:
            return 503, {"available": False, "error": UPDATE}
        return jarvis_pc_help.handle_get(query)
    if path == FACT_CHAT_PATH:
        return fact_chat(query)
    return 404, {"error": "no such route"}


_CID = re.compile(r"[A-Za-z0-9_-]{8,64}")


def fact_chat(query: str) -> tuple:
    """GET /api/memory/fact-chat?id=<fact id>: {"id", "conversation": null |
    {"id", "title", "updated", "kind"}}. `conversation` is null when the
    fact records no conversation (a card the owner accepted by hand, an
    older fact) or that conversation is no longer kept. 400 for anything but
    one whole-number id; 404 for no such fact. A read."""
    try:
        raw = (parse_qs(query or "", keep_blank_values=True).get("id") or [""])[0]
        fid = int(raw)
        if fid <= 0 or str(fid) != raw.strip():
            raise ValueError
    except (TypeError, ValueError):
        return 400, {"error": "need ?id=<one fact id>"}
    try:
        import jarvis_memory
        row = jarvis_memory.store().get(fid)
    except Exception as exc:
        return 503, {"error": f"memory layer not readable ({type(exc).__name__})"}
    if row is None:
        return 404, {"error": "no fact with that id"}
    meta = row.get("meta")
    try:
        meta = json.loads(meta) if isinstance(meta, str) else meta
    except (TypeError, ValueError):
        meta = None
    cid = meta.get("conversation_id") if isinstance(meta, dict) else None
    out = {"id": fid, "conversation": None}
    if not (isinstance(cid, str) and _CID.fullmatch(cid)):
        return 200, out
    try:
        import jarvis_chat_log
        brief = getattr(jarvis_chat_log, "brief", None)
        got = brief(cid) if brief is not None else None
    except Exception:
        got = None
    if got:
        out["conversation"] = {k: got.get(k) for k in ("id", "title", "updated", "kind")}
    return 200, out


def install(handler_cls, *, origin_ok, token_ok, read_body=None) -> str:
    """Wrap `handler_cls.do_GET` so PATHS are answered here, after the
    server's own origin and token checks; every other request goes straight
    to the original `do_GET`. `read_body` is handed on to
    jarvis_widgets.install() (its POSTs); every route of this module's own
    is GET-only."""
    widgets = _install_widgets(handler_cls, origin_ok, token_ok, read_body)
    if getattr(handler_cls.do_GET, "_jarvis_brain_reads", False):
        return ("  brain      Search old chats, fact history, a chat's facts and PC help "
                "(already on)" + widgets)
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
    return "  brain      Search old chats, fact history, a chat's facts and PC help: on" + widgets


def _install_widgets(handler_cls, origin_ok, token_ok, read_body) -> str:
    """"Widgets you describe" (jarvis_widgets.py): its own routes, wrapped
    round the same Handler. Never raises; the banner line says what
    happened, on a line of its own."""
    if read_body is None:
        return "\n  widgets    NOT ON (no request reader) - Widgets you describe is off"
    try:
        import jarvis_widgets
        return "\n" + jarvis_widgets.install(handler_cls, origin_ok=origin_ok,
                                              token_ok=token_ok, read_body=read_body)
    except Exception as exc:
        return (f"\n  widgets    NOT ON ({type(exc).__name__}) - Widgets you describe is off "
                "until jarvis_widgets.py is back: run apply-patches.ps1 again")
