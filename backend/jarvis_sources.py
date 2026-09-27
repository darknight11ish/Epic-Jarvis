"""jarvis_sources.py - "Where this came from", and the quote check.

Feasibility items I42 and I132 (queued, `docs/FEASIBILITY-AUDIT-2026-09-26.md`
section 2), the exact spec being detail 1 of
`docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md`.

WHAT WAS MISSING
Only saved MEMORY facts were ever listed under an answer - "Used in this
answer", built from `injected_ids` (`docs/JARVIS-API.md` section 4/6,
`GET /api/memory/used`). A note, a wiki page, a web result or a file the
model read was not listed anywhere - `docs/JARVIS-API.md` section 4 calls
this plainly "No tool receipt". This module is that receipt, extended to
those four kinds, in the SAME shape the memory one already uses: read-only,
behind the token, built by code from what a tool actually returned.

TWO THINGS, BUILT FROM THE SAME MOMENT
1. **Sources, by reference.** `from_tool_result(name, result)` reads the
   RESULT a reading tool (`notes_search`, `web_search`, `my_files`,
   `file_read`) really returned this turn - never what the model later
   claims it read - and pulls out a reference only: a note's `ref`
   (`jarvis_notes.py`'s own field, reused, not reinvented), a wiki page's
   path (the same `ref`, tagged "wiki" when it is under `Jarvis Wiki/`), a
   web result's `url`, or a file's `path`. Never the note's or file's full
   text, and never a web page's body - only what the tool's own result
   named. `jarvis_agent._TurnWatch.took_in()` calls this for every tool
   result already flowing through it, so nothing here reaches into the tool
   loop a second time.
2. **The quote check.** `unverified_quotes(answer, outside_texts)` looks for
   a quoted phrase (three words or more, inside straight or curly double
   quotes) in the model's finished answer, and checks it - word for word,
   spacing and case folded away - against the raw text every reading tool
   returned this turn (`_TurnWatch.outside`, already collected for the
   planted-instruction check). A quote not found there is reported, never
   corrected: this is a plain word-match, never a model call, and it only
   ever WARNS - it changes nothing about the answer that already streamed,
   and it never makes outside text more trusted than it already is. Run
   only when something was actually read this turn; an ordinary quote in an
   ordinary conversation ("she said 'no way'") is never checked, because
   there is nothing here to check it against.

WHY IN MEMORY, NOT A DATABASE
A source's `ref`/`path`/`url` and a note's TITLE are the by-product of one
answer, not a fact the owner chose to keep - unlike a saved memory (which
the owner asked Jarvis to remember) or a chat-history row (kept because the
owner turned chat history on). So this is a bounded, per-process dict,
keyed by turn_id, the same shape of cache `jarvis_agent.py` already keeps
for other per-process, non-durable things (`_CTX_CACHE`, `_TOOLS_CACHE`): a
backend restart clears it, and nothing here is written to disk. Capped two
ways (MAX_TURNS, MAX_PER_TURN) so a very long session cannot grow it without
bound.

WHY THE SAME turn_id, AND WHY A SEPARATE ROUTE
`feedback.patch` already gives every answer a 32-character `turn_id`,
carried in `X-Jarvis-Route`, so the right/wrong mark and this list are read
back under the one id an app already has. That header is written and SENT
before `run_local_turn` ever runs a tool - streaming means the headers go
out first - so nothing about tool results can ride in it. `GET
/api/chat/sources?turn_id=<id>` (installed by `install()`, below, the same
`jarvis_news.py`/`jarvis_media.py` pattern: wrap `do_GET`, answer this one
path, pass everything else through) is read only once an app wants to show
"Where this came from", the same lazy fetch "Used in this answer" already
does for `/api/memory/used`.

NO NEW WAY OUT OF THE PC
This only reads what a tool ALREADY fetched this turn, by reference. It
opens no socket of its own, follows no link, and fetches no web page to
preview it - an app shows a web source as plain text with its host, and
opens it only when the owner taps it. Note and wiki titles are private, so
the list this module serves is meant to sit behind the exact gate the
existing memory list already uses ("Hide memory lists and chat history" /
App lock) - enforced by the apps, the same way they already hide
`/api/memory/used`'s answer.
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Optional
from urllib.parse import parse_qs, urlsplit

#: The reading tools this module knows how to read a source out of. Kept
#: narrow on purpose: memory has its own list (`/api/memory/used`), and a
#: write tool (send_email, a note write, home_control, ...) changed
#: something rather than reading it back.
KNOWN_TOOLS = ("notes_search", "web_search", "my_files", "file_read")
KNOWN_KINDS = ("note", "wiki", "web", "file")

#: How many answers' worth of sources this process remembers at once - well
#: above anything one owner sends in a session. A restart clears it, like
#: jarvis_agent's own per-process caches; see the module docstring for why
#: this is memory, not a database.
MAX_TURNS = 500
#: One answer's sources, capped the same way jarvis_feedback.MAX_ITEMS_PER_TURN
#: caps the memory ids it counts - a malformed or run-away turn cannot grow
#: this without bound.
MAX_PER_TURN = 40
#: How long a single field (a title, a ref, a path, a url) is kept. Long
#: enough for a real path or title; short enough that nothing here becomes a
#: place to smuggle a whole document through.
_MAX_FIELD = 300

_TURN = re.compile(r"^[0-9a-f]{32}$")
_LOCK = threading.RLock()
#: turn_id -> {"sources": [...], "unverified_quotes": [...]}
_TURNS: "OrderedDict[str, dict]" = OrderedDict()


def _wiki_prefix() -> str:
    try:
        import jarvis_wiki
        d = str(getattr(jarvis_wiki, "WIKI_DIR", "") or "").strip()
    except Exception:
        d = ""
    return (d or "Jarvis Wiki").rstrip("/\\") + "/"


def _cap(v) -> Optional[str]:
    if v is None:
        return None
    s = " ".join(str(v).split())
    if not s:
        return None
    return s if len(s) <= _MAX_FIELD else s[: _MAX_FIELD - 1] + "…"


def _note_source(ref, title) -> Optional[dict]:
    ref = _cap(ref)
    if not ref:
        return None
    kind = "wiki" if ref.replace("\\", "/").startswith(_wiki_prefix()) else "note"
    out = {"kind": kind, "ref": ref}
    title = _cap(title)
    if title:
        out["title"] = title
    return out


def _web_source(url, title) -> Optional[dict]:
    url = _cap(url)
    if not url:
        return None
    out = {"kind": "web", "url": url}
    title = _cap(title)
    if title:
        out["title"] = title
    return out


def _file_source(path, title) -> Optional[dict]:
    path = _cap(path)
    if not path:
        return None
    out = {"kind": "file", "path": path}
    title = _cap(title)
    if title:
        out["title"] = title
    return out


def from_tool_result(name: str, result) -> list:
    """The sources one reading tool's own RESULT names - built from what the
    tool actually returned, never from anything the model says it read.
    `name` is the tool's name as `jarvis_agent.TOOLS` keys it; `result` is
    exactly what that tool's `execute()` returned, before the model reads it
    and before `_TurnWatch` cleans or labels it. Unknown tools, a result
    that is not a dict, or one that says `"ok": False`, return []."""
    if name not in KNOWN_TOOLS or not isinstance(result, dict) or not result.get("ok"):
        return []
    out: list = []
    if name == "notes_search":
        for r in (result.get("results") or [])[:MAX_PER_TURN]:
            if isinstance(r, dict):
                s = _note_source(r.get("ref"), r.get("title"))
                if s:
                    out.append(s)
    elif name == "web_search":
        for r in (result.get("results") or [])[:MAX_PER_TURN]:
            if isinstance(r, dict):
                s = _web_source(r.get("url"), r.get("title"))
                if s:
                    out.append(s)
    elif name == "my_files":
        # jarvis_documents.run_tool: `search` answers {"results": [...]},
        # `find` answers {"found": [...]} (a different key - it lists file
        # NAMES, not text matches), `read` answers one file with "path" at
        # the top level and no list at all.
        rows = (result.get("results") if isinstance(result.get("results"), list) else
                result.get("found") if isinstance(result.get("found"), list) else [result])
        for r in rows[:MAX_PER_TURN]:
            if isinstance(r, dict):
                s = _file_source(r.get("path"), r.get("name"))
                if s:
                    out.append(s)
    elif name == "file_read":
        s = _file_source(result.get("path"), None)
        if s:
            out.append(s)
    return out[:MAX_PER_TURN]


# --------------------------------------------------------------------------
#   The quote check (I132, "You told me")
# --------------------------------------------------------------------------

#: A quoted phrase: straight or curly double quotes, at least a FEW words -
#: one or two quoted words ("the "new" plan") are too common in ordinary
#: writing to mean "this is a claimed excerpt", and checking them would be
#: mostly noise.
_QUOTE_RX = re.compile(r'[“"]([^”"]{4,600})[”"]')
_MIN_QUOTE_WORDS = 3
#: At most this many phrases are reported - a pathological answer with
#: dozens of quotes gets a short, useful list, not a wall of them.
_MAX_REPORTED = 10


def _folded(s: str) -> str:
    return " ".join(str(s or "").split()).casefold()


def unverified_quotes(answer: str, outside_texts) -> list:
    """The quoted phrases in `answer` that do not appear - word for word,
    spacing and case folded away - in `outside_texts` (the raw text every
    reading tool returned THIS turn; `_TurnWatch.outside`). A plain
    word-match, never a model call: it only ever reports, it never changes
    `answer` and never blocks anything. [] when `answer` holds no long
    enough quote, or when `outside_texts` is empty (nothing was read this
    turn, so there is nothing to check a quote against - an everyday quote
    in an ordinary sentence is not flagged)."""
    if not isinstance(answer, str) or not answer.strip():
        return []
    texts = [t for t in (outside_texts or []) if isinstance(t, str) and t.strip()]
    if not texts:
        return []
    corpus = _folded("\n".join(texts))
    out: list = []
    for m in _QUOTE_RX.finditer(answer):
        phrase = m.group(1).strip()
        if len(phrase.split()) < _MIN_QUOTE_WORDS:
            continue
        folded = _folded(phrase)
        if folded and folded not in corpus and phrase not in out:
            out.append(phrase)
            if len(out) >= _MAX_REPORTED:
                break
    return out


# --------------------------------------------------------------------------
#   Keeping one answer's sources - see the module docstring for why memory
# --------------------------------------------------------------------------

def record(turn_id, sources, quotes=()) -> None:
    """Remember `sources` (from_tool_result's own shape) and `quotes`
    (unverified_quotes' own shape) under `turn_id`, so a later
    `GET /api/chat/sources?turn_id=...` can read them back. Capped at
    MAX_PER_TURN each; the oldest turn is dropped once MAX_TURNS is
    exceeded. Never raises: a bad id, or nothing to add, is a no-op - the
    caller (jarvis_hud.py, off a bare try) must never fail an answered turn
    over this."""
    if not isinstance(turn_id, str) or not _TURN.match(turn_id):
        return
    sources = [s for s in (sources or []) if isinstance(s, dict)][:MAX_PER_TURN]
    quotes = [q for q in (quotes or []) if isinstance(q, str)][:MAX_PER_TURN]
    if not sources and not quotes:
        return
    with _LOCK:
        _TURNS[turn_id] = {"sources": sources, "unverified_quotes": quotes}
        _TURNS.move_to_end(turn_id)
        while len(_TURNS) > MAX_TURNS:
            _TURNS.popitem(last=False)


def sources_of(turn_id) -> dict:
    """{"sources": [...], "unverified_quotes": [...]} for `turn_id` - both
    [] for a bad id, one this process never saw, or one with nothing to
    show. Never a 404: "nothing yet" and "gone since a restart" look the
    same from here, and neither is an error."""
    if not isinstance(turn_id, str) or not _TURN.match(turn_id):
        return {"sources": [], "unverified_quotes": []}
    with _LOCK:
        row = _TURNS.get(turn_id)
        return {"sources": list(row["sources"]), "unverified_quotes": list(row["unverified_quotes"])} \
            if row else {"sources": [], "unverified_quotes": []}


def _reset_for_tests() -> None:
    with _LOCK:
        _TURNS.clear()


# --------------------------------------------------------------------------
#   GET /api/chat/sources?turn_id=<32-hex>
# --------------------------------------------------------------------------

def handle_get(query: str) -> tuple:
    """(status, body) for `?turn_id=<32-hex>` - the same style as
    `jarvis_memory.handle_used_get`: a 400 in words for a bad id, else 200
    with `sources_of`'s answer (which is [] both ways, see its own
    docstring)."""
    try:
        turn_id = (parse_qs(query or "", keep_blank_values=True).get("turn_id") or [""])[0]
    except Exception:
        turn_id = ""
    if not _TURN.match(turn_id or ""):
        return 400, {"error": "need ?turn_id= with the 32-character id from this answer's "
                              "X-Jarvis-Route header (the same id right/wrong marks use)"}
    return 200, sources_of(turn_id)


PATH = "/api/chat/sources"


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` so PATH is answered here, after the
    server's own origin and token checks - every other request goes
    straight to the original `do_GET`. `read_body` is taken only for the
    same signature `jarvis_news.install`/`jarvis_media.install` use (this
    route is GET-only, so it is never called)."""
    if getattr(handler_cls.do_GET, "_jarvis_sources", False):
        return "  sources    Where this came from (already on)"
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
        if parsed.path.rstrip("/") != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(parsed.query)
        except Exception as exc:
            code, out = 503, {"error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_sources = True
    handler_cls.do_GET = do_GET
    return "  sources    Where this came from: on"
