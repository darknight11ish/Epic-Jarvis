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

    GET /api/guardian/snapshots?limit=<n>
    GET /api/guardian/diff?path=<file>&sha_before=<sha256>
        (2026-10-18, LM-2A; JARVIS-API section 140) "What did Jarvis change,
        and what did this file look like before?": the file guardian's own
        journal (newest first, one bounded page) and the bounded unified diff
        jarvis_file_guardian.diff_versions() already works out. They READ the
        store only - no restore, no write, no file contents and no blob bytes
        beyond the diff itself, which the module already bounds to
        MAX_DIFF_BYTES. A request from another device is refused BEFORE
        anything is read. The backend cannot see App lock or "Hide memory
        lists" (both are desktop-side state), so the desktop's own drawer must
        hide while either is on; JARVIS-API section 140 says that gap plainly.

    GET /api/pc/help
        (2026-09-28; JARVIS-API section 84) "PC help": five plain answers
        about this PC - why it is slow, how full the drives are, what is using
        the graphics card, how hot it is, when it last restarted.
        jarvis_pc_help.read() does the work, on this PC only; the program
        names in it are never logged or kept. It changes nothing.

    GET /api/today/cockpit
        (GTD-2, 2026-10-18) the Today board: due reminders from the one
        scheduler, the first open step of each active goal and project work
        list, and the owner-words-only "you said you would" proposals.
        jarvis_today.handle_cockpit() does the work; it creates nothing.
        `?hidden=1` withholds every word (an app whose private lists are
        hidden or App lock is on asks for it that way), and the desktop ALSO
        blanks the same sections in Rust. Read-only.

All of them are READS for the apps' Brain screens, behind the pairing token
and the origin check like every memory and history read. None is a tool: nomodel and no chat turn can call them (jarvis_agent.py offers nothing that
reaches here), so what they return never reaches the AI model. None writes
anything.

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
import time
from urllib.parse import parse_qs, urlsplit

SEARCH_PATH = "/api/history/search"
FACT_HISTORY_PATH = "/api/memory/fact-history"
CONVERSATION_FACTS_PATH = "/api/memory/conversation-facts"
PC_HELP_PATH = "/api/pc/help"
FACT_CHAT_PATH = "/api/memory/fact-chat"
#: The file guardian's history, read-only (LM-2A): the journal page and the
#: bounded diff. Restore is NOT here - it overwrites a file and waits for its
#: own gated slice.
GUARDIAN_SNAPSHOTS_PATH = "/api/guardian/snapshots"
GUARDIAN_DIFF_PATH = "/api/guardian/diff"
#: GTD-2 (2026-10-18): the Today board. The route lives in jarvis_today.py;
#: this module is only the door the server already wraps, so it needs no
#: patch of its own.
COCKPIT_PATH = "/api/today/cockpit"
PATHS = (SEARCH_PATH, FACT_HISTORY_PATH, CONVERSATION_FACTS_PATH, PC_HELP_PATH,
         FACT_CHAT_PATH, COCKPIT_PATH, GUARDIAN_SNAPSHOTS_PATH, GUARDIAN_DIFF_PATH)

#: The one POST this module answers (GTD-2, 2026-10-18): the said-I'd-do
#: switch's own toggle. OFF is immediate; ON raises ONE approval card. It is
#: not a second way to change any other setting.
POST_PATHS = (COCKPIT_PATH,)

UPDATE = ("This PC's Jarvis is missing part of this feature. Run apply-patches.ps1 on the PC "
          "to update it.")

#: One page of guardian history: newest first, 50 by default, 200 at most. The
#: answer never carries the whole journal, however long it has grown.
DEFAULT_SNAPSHOTS = 50
MAX_SNAPSHOTS = 200
MAX_PATH_CHARS = 4096
MAX_RECEIPT_CHARS = 120
MAX_REASON_CHARS = 200

NOT_THIS_PC = ("The file guardian's history is on this PC, so a request from another "
               "device is refused before anything is read.")


def _from_this_pc(peer, local) -> bool:
    """Is this request from this PC? Fails CLOSED: no helper, no answer.

    `jarvis_owner_check.from_this_pc` is the project's one answer to this
    question, and it treats loopback and this PC's own addresses as here - so
    a program on the PC can ask, and a phone on the same private network
    cannot.
    """
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False


def _guardian_refusal(why: str, words: str, path: str) -> dict:
    """A refusal in the SAME shape that route's success answer has."""
    if path == GUARDIAN_SNAPSHOTS_PATH:
        return {"ok": False, "refused": True, "why": why, "snapshots": [],
                "count": 0, "total": 0, "limit": 0, "more": False, "usage": {},
                "words": words}
    return {"ok": False, "refused": True, "why": why, "path": "", "diff": "",
            "truncated": False, "binary": False, "same": False,
            "before_sha256": "", "after_sha256": "", "words": words}


def _param(params, name: str) -> str:
    try:
        return str((params.get(name) or [""])[0])
    except Exception:
        return ""


def _safe_text(value, limit: int) -> str:
    """One line of a value from the journal, cut to a bound. Never raises."""
    try:
        text = str(value or "")
    except Exception:
        return ""
    return " ".join(text.split())[:limit]


def _safe_usage(usage) -> dict:
    """Only the numbers and words usage() already answers - never its blob map."""
    if not isinstance(usage, dict):
        return {}
    out = {}
    for key in ("blob_bytes", "blobs", "quota_bytes", "pinned", "over_quota", "words"):
        value = usage.get(key)
        if isinstance(value, str) or isinstance(value, (int, float)) or isinstance(value, bool):
            out[key] = value
    return out


def _label(path: str) -> str:
    """The short name a drawer shows; the full path is carried beside it."""
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or path


def _snapshot_page(query: str, read_rows, read_usage) -> tuple:
    """(status, answer) for GET /api/guardian/snapshots?limit=<n>.

    Newest first, one bounded page, every field read from the module's own
    journal. A row this route cannot mean (no path, no sha256) is skipped
    rather than guessed at. It never opens a blob and never touches a file.
    """
    params = parse_qs(query or "", keep_blank_values=True)
    raw = _param(params, "limit").strip()
    if raw:
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            limit = 0
        if limit < 1 or limit > MAX_SNAPSHOTS:
            return 400, _guardian_refusal(
                "bad_limit",
                f"The page size must be a whole number from 1 to {MAX_SNAPSHOTS}.",
                GUARDIAN_SNAPSHOTS_PATH)
    else:
        limit = DEFAULT_SNAPSHOTS
    try:
        found = read_rows()
    except Exception as exc:
        return 500, _guardian_refusal(
            "unreadable",
            f"The file guardian's history could not be read ({type(exc).__name__}).",
            GUARDIAN_SNAPSHOTS_PATH)
    entries = []
    for order, row in enumerate(found if isinstance(found, list) else []):
        if not isinstance(row, dict):
            continue
        shown = _safe_text(row.get("path"), MAX_PATH_CHARS)
        sha = _safe_text(row.get("before_sha256"), 64).lower()
        if not shown or not sha:
            continue
        stamp = row.get("timestamp")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            stamp = 0.0
        size = row.get("size")
        size = (int(size) if isinstance(size, int) and not isinstance(size, bool)
                and size >= 0 else 0)
        entries.append((float(stamp), order, {
            "path": shown,
            "label": _label(shown),
            "before_sha256": sha,
            "size": size,
            "timestamp": float(stamp),
            "when": (time.strftime("%Y-%m-%d %H:%M", time.localtime(float(stamp)))
                     if stamp > 0 else ""),
            "reason": _safe_text(row.get("reason"), MAX_REASON_CHARS),
            "receipt_id": _safe_text(row.get("receipt_id"), MAX_RECEIPT_CHARS),
        }))
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    total = len(entries)
    page = [entry for _stamp, _order, entry in entries[:limit]]
    try:
        usage = _safe_usage(read_usage())
    except Exception:
        usage = {}
    if not total:
        words = "No saved versions yet: Jarvis has not overwritten a file it keeps a copy of."
    else:
        words = (f"Showing the {len(page)} most recent of {total} saved version(s). "
                 "Only this PC's own guardian store is read.")
    return 200, {"ok": True, "refused": False, "why": "", "count": len(page),
                 "total": total, "limit": limit, "more": total > limit,
                 "snapshots": page, "usage": usage, "words": words}


def _diff_answer(query: str, differ) -> tuple:
    """(status, answer) for GET /api/guardian/diff?path=<file>&sha_before=<sha>.

    The module's own answer is passed back UNCHANGED: its own allowed-folder
    rules, its own sha check, its own MAX_DIFF_BYTES bound and its own plain
    refusals. This route only refuses a missing/oversized pair of inputs.
    """
    params = parse_qs(query or "", keep_blank_values=True)
    path = _param(params, "path").strip()
    sha = _param(params, "sha_before").strip()
    if not path or not sha:
        return 400, _guardian_refusal(
            "bad_request",
            "Say which file and which saved version (path and sha_before).",
            GUARDIAN_DIFF_PATH)
    if len(path) > MAX_PATH_CHARS or len(sha) > 64:
        return 400, _guardian_refusal(
            "bad_request", "That path or saved version is too long to be one.",
            GUARDIAN_DIFF_PATH)
    answer = differ(path, sha)
    if not isinstance(answer, dict):
        return 500, _guardian_refusal(
            "unreadable", "The difference could not be worked out.", GUARDIAN_DIFF_PATH)
    return 200, dict(answer)          # the module's own answer, unchanged


def handle_get(path: str, query: str = "", *, peer=None, local=None) -> tuple:
    """(http status, reply) for one of PATHS. Never raises.

    `peer` and `local` are the request's own socket addresses, handed in by
    `install()`; the guardian history uses them to refuse another device
    BEFORE it reads anything. A direct in-process call omits them (there is no
    network request to place), and `jarvis_owner_check.from_this_pc` answers
    for a request with no peer the way it always has.
    """
    if path in (GUARDIAN_SNAPSHOTS_PATH, GUARDIAN_DIFF_PATH):
        if not _from_this_pc(peer, local):
            return 403, _guardian_refusal("not_this_pc", NOT_THIS_PC, path)
        try:
            import jarvis_file_guardian as engine
        except Exception:
            return 501, _guardian_refusal("update", UPDATE, path)
        if path == GUARDIAN_SNAPSHOTS_PATH:
            read_rows = getattr(engine, "rows", None)
            if not callable(read_rows):
                return 501, _guardian_refusal("update", UPDATE, path)
            try:
                return _snapshot_page(query, read_rows, getattr(engine, "usage", None))
            except Exception:
                return 500, _guardian_refusal(
                    "unreadable", "The file guardian's history could not be read.", path)
        differ = getattr(engine, "diff_versions", None)
        if not callable(differ):
            return 501, _guardian_refusal("update", UPDATE, path)
        try:
            return _diff_answer(query, differ)
        except Exception:
            return 500, _guardian_refusal(
                "unreadable", "The difference could not be worked out.", path)
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
    if path == COCKPIT_PATH:
        try:
            import jarvis_today
        except Exception:
            return 503, {"available": False, "why": UPDATE}
        handler = getattr(jarvis_today, "handle_cockpit", None)
        if handler is None:
            return 501, {"error": UPDATE}
        try:
            return handler(query)
        except Exception as exc:
            # The exception's NAME only, as for /api/schedule.
            return 500, {"error": type(exc).__name__}
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
        return ("  brain      Search old chats, fact history, a chat's facts, PC help and "
                "the file guardian's history (already on)" + widgets)
    get0 = handler_cls.do_GET

    def _peer_local(self) -> tuple:
        """(peer, local) for this request, best effort. The guardian routes
        fail CLOSED when they cannot be had (jarvis_owner_check's own rule)."""
        peer = local = None
        try:
            peer = self.client_address[0]
        except Exception:
            pass
        try:
            local = self.connection.getsockname()[0]
        except Exception:
            pass
        return peer, local

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
        peer, local = _peer_local(self)
        code, out = handle_get(route, parsed.query, peer=peer, local=local)
        return self._send(code, out)

    do_GET._jarvis_brain_reads = True
    handler_cls.do_GET = do_GET
    if read_body is not None:
        post0 = handler_cls.do_POST

        def do_POST(self):
            try:
                from urllib.parse import urlsplit
                route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
            except Exception:
                route = ""
            if route not in POST_PATHS:
                return post0(self)
            if not _allowed(self):
                return None
            try:
                raw = read_body(self) or b"{}"
                if len(raw) > 16 * 1024:
                    return self._send(413, {"ok": False, "error": "too big"})
                body = json.loads(raw)
            except Exception as exc:
                return self._send(400, {"ok": False, "error": type(exc).__name__})
            try:
                import jarvis_today
                handler = getattr(jarvis_today, "handle_cockpit_post", None)
                code, out = ((501, {"ok": False, "error": UPDATE}) if handler is None
                             else handler(body))
            except Exception as exc:
                code, out = 500, {"ok": False, "error": type(exc).__name__}
            return self._send(code, out)

        handler_cls.do_POST = do_POST
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
