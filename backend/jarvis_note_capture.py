"""jarvis_note_capture.py - file a note in Logseq or Joplin, with permission.

WHAT IT IS FOR
The desktop has had `#log` / `#joplin` prefixes, an Alt+Shift+N quick note
and the widget's #log / #jop buttons for a long time. All of them asked the
model to call `append_logseq_journal` or `create_joplin_note` - tools that did
not exist anywhere in `jarvis_agent.py`. So no note was ever filed, and the
widget could only say "Sent" and admit it had no way to know more.

This module is those two writes, done the project's one way
(docs/ARCHITECTURE.md section 3):

    plan()       Work out exactly what would be written and where. Reads the
                 clock and the config. Opens no socket, writes no file.
    describe()   The card: the exact text, the exact file or notebook, what
                 leaves this PC (nothing), and what saying no costs.
    <the gate>   jarvis_gate.check() with the action names the owner's own
                 jarvis-framework.toml already lists: `append_logseq_journal`
                 and `create_joplin_note`. The TIER is the owner's: whatever
                 that file says (the shipped file says "auto" for the Logseq
                 journal and "notify" for a new Joplin note). Change it there
                 to "ask" to get a card every time.
    run()        Writes. `approved` has no default of True.

Two ways in, one path:
  - `capture()` - what `POST /api/notes/capture` calls (note-capture.patch).
    The owner typed the words; no model is involved at all. It answers with
    a job id, and `capture_status()` says honestly what happened: filed,
    waiting for approval, refused, or failed - and why.
  - `jarvis_agent.py`'s `append_logseq_journal` / `create_joplin_note` tools,
    for when the owner asks Jarvis in chat. Same plan, same gate, same run.

WHAT IT WILL NOT DO
  - Overwrite. Logseq: the journal file is opened for APPEND only (never
    truncated), created only if missing. Joplin: always a NEW note, never an
    edit; a notebook is looked up by name and never created.
  - Leave this PC. Logseq is a file on disk. Joplin is its local Web Clipper
    service, and the address must be this machine (127.0.0.1 / localhost /
    ::1) or the plan refuses - the token is only ever sent there.
  - Show, log or store the Joplin token. It is read fresh from the
    environment inside the one function that sends it, never put in a Plan,
    a card, a result or an error message (every error is scrubbed), and
    never written to disk here.
  - Talk to any model. Nothing here reaches a cloud lane (invariant 1).

LOGSEQ DEFAULTS, CHECKED
Logseq keeps each day's journal as `journals/<yyyy_MM_dd>.md` inside the
graph folder - `:journal/file-name-format` defaults to "yyyy_MM_dd" and
`:journals-directory` to "journals" in Logseq's own config.edn. A graph that
changed either is not followed here (the file would be made under the
default name, which Logseq would not show as that day's journal); set them
back, or ask for this to learn your config.edn. Each note becomes one block:
"- " before the first line, two spaces before every following line.

WHERE THE GRAPH IS
`JARVIS_LOGSEQ_GRAPH` if set, else `[notes.logseq].graph_directory` in
jarvis-framework.toml, else `<config dir>/notes` - that file's own comment
("Leave empty to fall back to <config dir>/notes"). The folder must already
exist; this never creates a graph.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional

LOGSEQ_GRAPH_ENV = "JARVIS_LOGSEQ_GRAPH"
JOPLIN_URL_ENV = "JARVIS_JOPLIN_URL"       # the same names jarvis_notes.py reads
JOPLIN_TOKEN_ENV = "JARVIS_JOPLIN_TOKEN"

#: The gate action for each target. These names are in the owner's
#: jarvis-framework.toml [autonomy.tiers] already; that file decides the tier.
ACTIONS = {"logseq": "append_logseq_journal", "joplin": "create_joplin_note"}

MAX_NOTE_CHARS = 4000
MAX_TITLE_CHARS = 200
MAX_NOTEBOOK_CHARS = 200
#: A journal file bigger than this is refused rather than appended to: a day's
#: journal that size means something is wrong, and this is not the thing to
#: make it bigger.
MAX_JOURNAL_BYTES = 5 * 1024 * 1024
_MAX_FOLDER_PAGES = 20
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _cfg(section: str, key: str, default=None):
    try:
        import jarvis_framework as fw
        return (fw.load_framework().get("notes", {}).get(section, {}) or {}).get(key, default)
    except Exception:
        return default


def _config_dir() -> Path:
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        return Path(os.path.expanduser("~")) / ".openjarvis"


def logseq_graph() -> Path:
    """The Logseq graph folder this machine is set up with (see module doc)."""
    env = os.environ.get(LOGSEQ_GRAPH_ENV, "").strip()
    if env:
        return Path(os.path.expanduser(env))
    cfg = str(_cfg("logseq", "graph_directory", "") or "").strip()
    if cfg:
        return Path(os.path.expanduser(cfg))
    return _config_dir() / "notes"


def _joplin_token() -> str:
    """Read fresh, every time, and only by the functions that send it."""
    tok = os.environ.get(JOPLIN_TOKEN_ENV, "").strip()
    if tok:
        return tok
    name = str(_cfg("joplin", "token_env", "JOPLIN_TOKEN") or "JOPLIN_TOKEN")
    return os.environ.get(name, "").strip()


def _joplin_base() -> str:
    env = os.environ.get(JOPLIN_URL_ENV, "").strip()
    if env:
        return env.rstrip("/")
    try:
        port = int(_cfg("joplin", "port", 41184) or 41184)
    except (TypeError, ValueError):
        port = 41184
    return f"http://127.0.0.1:{port}"


def _is_loopback(url: str) -> bool:
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and (u.hostname or "") in _LOOPBACK


def _clean(text, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch in "\n\t" or ch >= " ")
    return text.strip()[:limit]


# --------------------------------------------------------------------------
#   The plan
# --------------------------------------------------------------------------

@dataclass
class Plan:
    target: str                 # "logseq" | "joplin"
    text: str                   # the note body, exactly as it will be written
    title: str = ""             # joplin only
    notebook: str = ""          # joplin only; "" means Joplin's default
    file: str = ""              # logseq: the journal file, absolute
    day: str = ""               # logseq: the journal day, YYYY-MM-DD
    url: str = ""               # joplin: the local service base, TOKEN-FREE
    reason_empty: str = ""      # set when nothing can be written, and why
    if_refused: str = "nothing is written"

    def as_dict(self) -> dict:
        return asdict(self)


def logseq_block(text: str) -> str:
    """One Logseq block: "- " before the first line, two spaces before the rest."""
    lines = text.split("\n")
    out = ["- " + lines[0]]
    out += [("  " + l) if l.strip() else "  " for l in lines[1:]]
    return "\n".join(out) + "\n"


def plan(target: str, text: str, *, title: str = "", notebook: str = "",
         now: Optional[_dt.datetime] = None) -> Plan:
    """Work out exactly what would be written. Opens no socket, writes nothing."""
    target = str(target or "").strip().lower()
    if target in ("vault", "jop"):
        target = "joplin"
    if target in ("log", "journal"):
        target = "logseq"
    body = _clean(text, MAX_NOTE_CHARS)
    if target not in ACTIONS:
        return Plan(target=target, text=body,
                    reason_empty="the target must be Logseq or Joplin")
    if not body:
        return Plan(target=target, text=body, reason_empty="the note is empty")

    if target == "logseq":
        day = (now or _dt.datetime.now()).date()
        graph = logseq_graph()
        path = graph / "journals" / f"{day:%Y_%m_%d}.md"
        p = Plan(target="logseq", text=body, file=str(path), day=day.isoformat())
        if not graph.is_dir():
            p.reason_empty = (f"there is no Logseq graph folder at {graph} - set "
                              f"[notes.logseq] graph_directory in jarvis-framework.toml, "
                              f"or {LOGSEQ_GRAPH_ENV}")
        elif not (graph / "journals").is_dir() and not (graph / "logseq").is_dir():
            p.reason_empty = (f"{graph} does not look like a Logseq graph (it has no "
                              f"journals or logseq folder)")
        return p

    ttl = _clean(title, MAX_TITLE_CHARS).replace("\n", " ")
    if not ttl:
        first = body.split("\n", 1)[0]
        ttl = first[:80] + ("…" if len(first) > 80 else "")
    nb = _clean(notebook, MAX_NOTEBOOK_CHARS).replace("\n", " ")
    base = _joplin_base()
    p = Plan(target="joplin", text=body, title=ttl, notebook=nb, url=base)
    if not _is_loopback(base):
        p.reason_empty = ("the Joplin address is not this PC, and the token is only "
                          "ever sent to this PC - check " + JOPLIN_URL_ENV)
    elif not _joplin_token():
        p.reason_empty = ("no Joplin token is set - copy it from Joplin (Tools > "
                          "Options > Web Clipper) into " + JOPLIN_TOKEN_ENV)
    return p


def describe(p: Plan) -> str:
    """The card text. The exact words and the exact place - never a summary."""
    if p.reason_empty:
        return f"Jarvis would file a note, but {p.reason_empty}. Nothing would be written."
    if p.target == "logseq":
        lines = [f"Add this to your Logseq journal for {p.day}:", "",
                 logseq_block(p.text).rstrip("\n"), "",
                 f"File: {p.file}",
                 "It is added at the end of that file (the file is made if it is "
                 "not there yet). Nothing already in it is changed.",
                 "Nothing leaves this PC."]
    else:
        where = f'the notebook "{p.notebook}"' if p.notebook else "Joplin's default notebook"
        lines = [f'Create a new Joplin note in {where}, titled "{p.title}":', "",
                 p.text, "",
                 f"Sent to Joplin's own service on this PC ({p.url}), with your "
                 "Joplin token. No existing note is changed"
                 + (", and the notebook is not created if it does not exist." if p.notebook
                    else "."),
                 "Nothing leaves this PC."]
    lines += ["", f"If you say no: {p.if_refused}."]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Writing
# --------------------------------------------------------------------------

def _scrub(message: str) -> str:
    """An error message with the Joplin token taken out, in every form it has.

    urllib puts the whole URL - query string and all - into several of its
    errors (a malformed address is a ValueError that quotes it), and Joplin
    takes its token in the query string. So any message that might carry a
    URL passes through here before it goes anywhere.
    """
    tok = _joplin_token()
    s = str(message)
    if tok:
        for form in {tok, urllib.parse.quote(tok, safe=""), urllib.parse.quote_plus(tok)}:
            if form:
                s = s.replace(form, "[token hidden]")
    return s


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the token (it is in the URL) somewhere else."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            _scrub(req.full_url), code,
            "Joplin's address redirected, and the token is never followed onto a "
            "redirect. Point JARVIS_JOPLIN_URL at the final address.", headers, fp)


def _joplin_call(method: str, base: str, path: str, query: dict, body=None,
                 timeout: float = 10.0):
    """One request to Joplin's local service. The token is added HERE only."""
    if not _is_loopback(base):
        raise ValueError("the Joplin address is not this PC")
    q = dict(query)
    q["token"] = _joplin_token()
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(q)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    opener = urllib.request.build_opener(_RefuseRedirect)
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "null")


def _find_notebook(name: str, call: Callable) -> Optional[str]:
    """The id of the notebook with exactly this title (then case-blind), or None."""
    folders = []
    for page in range(1, _MAX_FOLDER_PAGES + 1):
        got = call("GET", "/folders", {"fields": "id,title", "page": page}) or {}
        folders += [f for f in (got.get("items") or []) if isinstance(f, dict)]
        if not got.get("has_more"):
            break
    for f in folders:
        if str(f.get("title", "")) == name:
            return str(f.get("id"))
    for f in folders:
        if str(f.get("title", "")).casefold() == name.casefold():
            return str(f.get("id"))
    return None


def _append_logseq(p: Plan) -> dict:
    path = Path(p.file)
    journals = path.parent
    if not journals.is_dir():
        journals.mkdir(parents=False, exist_ok=True)   # graph checked in plan()
    # The file must be what the card said: a plain file in this graph's
    # journals folder, not a link pointing somewhere else on the disk.
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return {"ok": False, "reason": "the journal file is a link or a folder, not a "
                                       "plain file; nothing was written"}
    size = path.stat().st_size if path.exists() else 0
    if size > MAX_JOURNAL_BYTES:
        return {"ok": False, "reason": f"today's journal file is over "
                                       f"{MAX_JOURNAL_BYTES // (1024 * 1024)} MB, which is "
                                       f"not normal; nothing was written"}
    lead = ""
    if size:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                lead = "\n"
    block = lead + logseq_block(p.text)
    # O_APPEND without O_TRUNC: the one way to open this file that cannot
    # remove anything already in it.
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, block.encode("utf-8"))
    finally:
        os.close(fd)
    # Read it back rather than trusting the write: "filed" is a claim.
    with open(path, "rb") as f:
        f.seek(max(0, path.stat().st_size - len(block.encode("utf-8"))))
        landed = f.read().decode("utf-8", "replace").endswith(logseq_block(p.text))
    if not landed:
        return {"ok": False, "reason": "the note was written but could not be read back; "
                                       "open the journal to check"}
    return {"ok": True, "target": "logseq", "file": f"journals/{path.name}",
            "day": p.day}


def _create_joplin(p: Plan, call: Callable) -> dict:
    parent = None
    if p.notebook:
        parent = _find_notebook(p.notebook, call)
        if parent is None:
            return {"ok": False, "reason": f'Joplin has no notebook called "{p.notebook}" '
                                           f"- nothing was created (a notebook is never "
                                           f"made on your behalf)"}
    body = {"title": p.title, "body": p.text}
    if parent:
        body["parent_id"] = parent
    got = call("POST", "/notes", {}, body)
    nid = str((got or {}).get("id") or "")
    if not nid:
        return {"ok": False, "reason": "Joplin answered, but without a note id; "
                                       "check Joplin to see whether it was made"}
    return {"ok": True, "target": "joplin", "note_id": nid,
            "notebook": p.notebook or None, "title": p.title}


def run(p: Plan, *, approved: bool = False,
        joplin_call: Optional[Callable] = None) -> dict:
    """Write an approved plan. `approved` has no default of True.

    `joplin_call(method, path, query, body=None)` is injectable so tests need
    no Joplin; the default sends to `p.url` - the address the card showed.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was written"}
    if p.reason_empty:
        return {"ok": False, "reason": p.reason_empty}
    try:
        if p.target == "logseq":
            return _append_logseq(p)
        call = joplin_call or (lambda m, path, q, b=None: _joplin_call(m, p.url, path, q, b))
        return _create_joplin(p, call)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False, "reason": "Joplin refused the token - copy it again "
                                           "from Joplin (Tools > Options > Web Clipper)"}
        return {"ok": False, "reason": _scrub(f"Joplin answered HTTP {exc.code}: {exc.reason}")}
    except urllib.error.URLError as exc:
        return {"ok": False, "reason": _scrub(
            f"could not reach Joplin on this PC ({exc.reason}) - is Joplin open, with "
            f"the Web Clipper service turned on?")}
    except Exception as exc:
        return {"ok": False, "reason": _scrub(f"{type(exc).__name__}: {exc}")}


# --------------------------------------------------------------------------
#   POST /api/notes/capture - the owner's own words, through the gate
# --------------------------------------------------------------------------

_lock = threading.Lock()
_jobs: dict = {}            # id -> public job record
_MAX_JOBS = 50
_MAX_WAITING = 4


def _gate_check(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error."""
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}")


_REFUSED_WORDS = {
    "denied": "You said no, so nothing was written.",
    "timed_out": "Nobody answered the approval card in time, so nothing was written.",
}


def _audit(what: str, detail: dict) -> None:
    try:
        import jarvis_framework
        jarvis_framework.audit_log("notes." + what, detail)
    except Exception:
        pass


def _where(target: str) -> str:
    return "Logseq" if target == "logseq" else "Joplin"


def _finish(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated"] = time.time()


def _worker(job_id: str, p: Plan, gate_check: Callable, joplin_call) -> None:
    try:
        verdict = gate_check(ACTIONS[p.target], {"text": describe(p)},
                             f"file a note in {_where(p.target)} ({len(p.text)} characters, "
                             f"typed by the owner)")
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            _finish(job_id, state="not_filed", outcome=outcome,
                    message=_REFUSED_WORDS.get(outcome, "The approval gate refused it, so "
                                               "nothing was written: "
                                               + str(getattr(verdict, "reason", ""))[:200]))
            _audit("capture_refused", {"job": job_id, "target": p.target, "outcome": outcome})
            return
        out = run(p, approved=True, joplin_call=joplin_call)
        if out.get("ok"):
            where = (f"Logseq, {out.get('file')}" if p.target == "logseq"
                     else f"Joplin{', notebook ' + p.notebook if p.notebook else ''}")
            _finish(job_id, state="filed", outcome=str(getattr(verdict, "outcome", "")),
                    message=f"Filed in {where}.",
                    where=out.get("file") or out.get("note_id"))
            _audit("captured", {"job": job_id, "target": p.target, "chars": len(p.text)})
        else:
            _finish(job_id, state="failed", message="Not filed: " + str(out.get("reason")))
            _audit("capture_failed", {"job": job_id, "target": p.target})
    except Exception as exc:
        _finish(job_id, state="failed", message=_scrub(f"Not filed: {type(exc).__name__}: {exc}"))


def capture(target: str, text: str, *, title: str = "", notebook: str = "",
            by: str = "", gate_check: Optional[Callable] = None,
            joplin_call: Optional[Callable] = None, wait_s: float = 1.5) -> tuple:
    """File the owner's own words. Returns (http_status, json_body).

    Waits up to `wait_s` for the answer, so the common case (a tier that does
    not ask) comes back already "filed". Otherwise 202 with state "waiting":
    an approval card is up, and `capture_status(id)` will say how it ended.
    """
    p = plan(target, text, title=title, notebook=notebook)
    if p.reason_empty:
        code = 400 if p.reason_empty in ("the note is empty",
                                         "the target must be Logseq or Joplin") else 503
        return code, {"ok": False, "state": "not_filed", "error": p.reason_empty,
                      "message": f"Not filed: {p.reason_empty}."}
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j["state"] == "waiting")
        if waiting >= _MAX_WAITING:
            return 429, {"ok": False, "state": "not_filed",
                         "error": "several notes are already waiting for approval - "
                                  "answer those first"}
        job_id = "note_" + secrets.token_hex(8)
        _jobs[job_id] = {"id": job_id, "state": "waiting", "target": p.target,
                         "message": "Waiting for your approval.", "created": time.time(),
                         "updated": time.time(), "by": by}
        while len(_jobs) > _MAX_JOBS:
            oldest = min(_jobs, key=lambda k: _jobs[k]["created"])
            _jobs.pop(oldest)
    t = threading.Thread(target=_worker, args=(job_id, p, gate_check or _gate_check,
                                                joplin_call),
                         name="jarvis-note-capture", daemon=True)
    t.start()
    t.join(max(0.0, float(wait_s)))
    return capture_status(job_id)


def capture_status(job_id: str) -> tuple:
    """(http_status, job) - never the note's text."""
    with _lock:
        job = dict(_jobs.get(str(job_id)) or {})
    if not job:
        return 404, {"ok": False, "error": "no note with that id on this PC"}
    job.pop("by", None)
    job["ok"] = job["state"] in ("filed", "waiting")
    return (202 if job["state"] == "waiting" else 200), job


def handle_post(body) -> tuple:
    """POST /api/notes/capture: {"target", "text", "title"?, "notebook"?}."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    return capture(str(body.get("target") or ""), body.get("text"),
                   title=body.get("title") or "", notebook=body.get("notebook") or "")


# --------------------------------------------------------------------------
#   jarvis_agent.py's two tools
# --------------------------------------------------------------------------

def prepare_logseq_tool(args: dict):
    p = plan("logseq", args.get("text"))
    return p, describe(p)


def prepare_joplin_tool(args: dict):
    p = plan("joplin", args.get("body") if args.get("body") is not None else args.get("text"),
             title=args.get("title") or "", notebook=args.get("notebook") or "")
    return p, describe(p)
