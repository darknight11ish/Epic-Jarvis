"""jarvis_note_capture.py - file a note in Logseq, Joplin or Obsidian, with permission.

WHAT IT IS FOR
The desktop has had `#log` / `#joplin` prefixes, an Alt+Shift+N quick note
and the widget's #log / #jop buttons for a long time. All of them asked the
model to call `append_logseq_journal` or `create_joplin_note` - tools that did
not exist anywhere in `jarvis_agent.py`. So no note was ever filed, and the
widget could only say "Sent" and admit it had no way to know more.

This module is those two writes - and a third, added later: today's Obsidian
daily note (`#obs`, gate action `append_obsidian_daily`; see OBSIDIAN at the
end) - done the project's one way (docs/ARCHITECTURE.md section 3):

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
  - `jarvis_agent.py`'s `append_logseq_journal` / `create_joplin_note` /
    `append_obsidian_daily` tools, for when the owner asks Jarvis in chat.
    Same plan, same gate, same run.

WHICH TARGETS ARE SET UP
`available_targets()` lists the targets this PC is set up for - names only,
never a path or a token: "logseq" when the graph folder is there, "joplin"
when a token is set and the address is this PC, "obsidian" when the vault is
a real vault. It is what `GET /api/notes/capture` with no `id` answers
(`capture_status("")`), so the desktop and the phone show only those. It
opens no socket, so "joplin" means set up, not that Joplin is open right now.

WHAT IT WILL NOT DO
  - Overwrite. Logseq and Obsidian: the file is opened for APPEND only (never
    truncated), created only if missing. Joplin: always a NEW note, never an
    edit; a notebook is looked up by name and never created.
  - Leave this PC. Logseq and Obsidian are files on disk. Joplin is its local Web Clipper
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

OBSIDIAN (added 2026-09-24): APPENDED TO TODAY'S DAILY NOTE
Gate action `append_obsidian_daily`. The vault is a plain folder on this PC -
no Obsidian plugin, no API key, no network. It is `JARVIS_OBSIDIAN_VAULT`, else
`[notes.obsidian] vault_directory` in jarvis-framework.toml (jarvis_notes.py's
obsidian_vault(), shared with the vault search). It must already exist and
contain a `.obsidian` folder; a vault is never created.

Where today's daily note is - what was checked, on 2026-09-24:
  - Obsidian's own help page for the Daily notes core plugin
    (github.com/obsidianmd/obsidian-help, en/Plugins/Daily notes.md): "By
    default, Obsidian creates a new empty note named after today's date in
    the YYYY-MM-DD format"; the "New file location" option changes the
    folder; slashes in the "Date format" make subfolders
    (`YYYY/MMMM/YYYY-MMM-DD` -> `2023/January/2023-Jan-01`); the format is
    moment.js.
  - Obsidian itself is not open source, so its code could not be read. The
    closest real code is liamcain/obsidian-daily-notes-interface (the
    library the Calendar and Periodic Notes plugins use to find the same
    note): settings.ts reads the plugin's `folder`, `format`, `template`
    options with `format || "YYYY-MM-DD"` and `folder` trimmed, "" meaning the
    vault's top folder; vault.ts getNotePath() joins folder + formatted date
    with "/" and adds ".md".
  - The file those options are stored in, `.obsidian/daily-notes.json`, was
    checked against real vaults on GitHub (code search, 874 files): keys
    `folder`, `format`, `template`, `autorun`; a key left at its default can
    be missing or "" (one has `"format":""`); the file itself does not exist
    until the settings are first changed. All three mean the default here.
  - `.obsidian/community-plugins.json` is the list of turned-on community
    plugins. When "periodic-notes" is in it, that plugin can take over
    naming the daily note (the library reads its settings first, when its
    `daily.enabled` is on). Its settings are not followed here, so the plan
    refuses, unless that plugin's own data.json says `daily.enabled: false`.

Only date formats that can be written out exactly are followed: the tokens
YYYY, YY, MM, M, DD and D, "[bracketed]" literal words, digits, and the
characters - _ . space and / (a folder). Anything else - month or weekday
NAMES (their spelling follows Obsidian's language setting), week numbers,
"Do" - is refused, saying which part, rather than guessing a file name.

The note is added at the END of that file, after a blank line, as its own
paragraph; the file is opened for append only and never truncated. If the
file is not there yet it is made, holding just the note - Obsidian's daily
note TEMPLATE is not applied, because only Obsidian applies it, and the card
says so. Missing folders on the way (a new month's folder, say) are made,
the way Obsidian makes them. The resolved path, after `..` and every link,
must stay inside the vault, or nothing is written.
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
#: jarvis-framework.toml [autonomy.tiers]; that file decides the tier. An
#: owner's file from before Obsidian was added has no line for
#: `append_obsidian_daily`, and the gate then uses `unknown_action_tier`
#: ("ask" as shipped) until they add it.
ACTIONS = {"logseq": "append_logseq_journal", "joplin": "create_joplin_note",
           "obsidian": "append_obsidian_daily"}
#: The names people see, in one place.
NAMES = {"logseq": "Logseq", "joplin": "Joplin", "obsidian": "Obsidian"}
_ALIASES = {"log": "logseq", "journal": "logseq", "jop": "joplin",
            # "#vault" meant Joplin until 2026-09-24; the owner moved it to
            # Obsidian, whose own word it is.
            "vault": "obsidian", "obs": "obsidian", "daily": "obsidian"}
_BAD_TARGET = "the target must be Logseq, Joplin or Obsidian"
_EMPTY = "the note is empty"

MAX_NOTE_CHARS = 4000
MAX_TITLE_CHARS = 200
MAX_NOTEBOOK_CHARS = 200
#: A journal file bigger than this is refused rather than appended to: a day's
#: journal that size means something is wrong, and this is not the thing to
#: make it bigger.
MAX_JOURNAL_BYTES = 5 * 1024 * 1024
_MAX_FOLDER_PAGES = 20
_APPEND_FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
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


def _vault():
    """(configured vault or None, why it is not usable or "") - from
    jarvis_notes, so the search and the capture can never disagree."""
    try:
        import jarvis_notes
    except Exception as exc:
        return None, f"jarvis_notes.py is not available here ({type(exc).__name__})"
    v = jarvis_notes.obsidian_vault()
    return v, jarvis_notes.vault_problem(v)


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
    target: str                 # "logseq" | "joplin" | "obsidian"
    text: str                   # the note body, exactly as it will be written
    title: str = ""             # joplin only
    notebook: str = ""          # joplin only; "" means Joplin's default
    file: str = ""              # logseq/obsidian: the file, absolute
    day: str = ""               # logseq/obsidian: the day, YYYY-MM-DD
    url: str = ""               # joplin: the local service base, TOKEN-FREE
    vault: str = ""             # obsidian: the vault folder, links resolved
    new_folder: str = ""        # obsidian: a folder that will be made, if any
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


def _normal_target(target) -> str:
    t = str(target or "").strip().lower().lstrip("#")
    return _ALIASES.get(t, t)


def _setup_problem(target: str) -> str:
    """Why `target` is not set up on this PC, in plain words, or "".

    Setup only - the folder, the token, the vault. Reads the disk and the
    environment; opens no socket. plan() refuses with this same sentence, so
    the list available_targets() gives and what a capture does always agree.
    """
    if target == "logseq":
        graph = logseq_graph()
        if not graph.is_dir():
            return (f"there is no Logseq graph folder at {graph} - set "
                    f"[notes.logseq] graph_directory in jarvis-framework.toml, "
                    f"or {LOGSEQ_GRAPH_ENV}")
        if not (graph / "journals").is_dir() and not (graph / "logseq").is_dir():
            return (f"{graph} does not look like a Logseq graph (it has no "
                    f"journals or logseq folder)")
        return ""
    if target == "joplin":
        if not _is_loopback(_joplin_base()):
            return ("the Joplin address is not this PC, and the token is only "
                    "ever sent to this PC - check " + JOPLIN_URL_ENV)
        if not _joplin_token():
            return ("no Joplin token is set - copy it from Joplin (Tools > "
                    "Options > Web Clipper) into " + JOPLIN_TOKEN_ENV)
        return ""
    if target == "obsidian":
        return _vault()[1]
    return _BAD_TARGET


def available_targets() -> list:
    """The targets this PC is set up for, by name only - never a path or a
    token. See "WHICH TARGETS ARE SET UP" in the module docstring."""
    return [t for t in ACTIONS if not _setup_problem(t)]


# --- Obsidian's daily note ------------------------------------------------

DAILY_DEFAULT_FORMAT = "YYYY-MM-DD"
_MAX_SETTINGS_BYTES = 256 * 1024
#: The only moment.js tokens followed - each has exactly one spelling.
_TOKENS = {"YYYY": "{y:04d}", "YY": "{yy:02d}", "MM": "{m:02d}", "M": "{m}",
           "DD": "{d:02d}", "D": "{d}"}
_PLAIN = set("-_. /0123456789")
_LITERAL_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ")


def _read_json(path: Path):
    """(parsed, error). A missing file is (None, "")."""
    if not path.exists():
        return None, ""
    try:
        if path.stat().st_size > _MAX_SETTINGS_BYTES:
            return None, f"{path.name} is too big to be a settings file"
        return json.loads(path.read_text(encoding="utf-8-sig")), ""
    except (OSError, ValueError) as exc:
        return None, f"{path.name} could not be read ({type(exc).__name__})"


def daily_name(fmt: str, day: _dt.date) -> tuple:
    """(the date written out in Obsidian's `fmt`, "") or ("", why not).

    Only the exact subset in the module docstring. Anything else is refused
    with the part that could not be followed - never a guessed name."""
    out, i = [], 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == "[":
            end = fmt.find("]", i + 1)
            if end < 0:
                return "", f'the date format "{fmt}" has a "[" with no "]"'
            lit = fmt[i + 1:end]
            if not set(lit) <= _LITERAL_OK:
                return "", (f'the date format "{fmt}" has "[{lit}]", and only letters, '
                            f"digits, spaces and - _ . are followed inside brackets")
            out.append(lit)
            i = end + 1
            continue
        if ch.isalpha():
            j = i
            while j < len(fmt) and fmt[j] == ch:
                j += 1
            run = fmt[i:j]
            if run not in _TOKENS:
                return "", (f'the date format "{fmt}" uses "{run}", which Jarvis does not '
                            f"write out (only YYYY, YY, MM, M, DD and D) - so it cannot "
                            f"be sure of the file name")
            out.append(_TOKENS[run].format(y=day.year, yy=day.year % 100,
                                           m=day.month, d=day.day))
            i = j
            continue
        if ch not in _PLAIN:
            return "", (f'the date format "{fmt}" has "{ch}", which Jarvis does not '
                        f"follow in a file name")
        out.append(ch)
        i += 1
    return "".join(out), ""


def _periodic_notes_owns_daily(obs: Path) -> bool:
    """True when the Periodic Notes community plugin may be naming the daily
    note instead of Daily notes (see the module docstring)."""
    enabled, _ = _read_json(obs / "community-plugins.json")
    if not isinstance(enabled, list) or "periodic-notes" not in enabled:
        return False
    data, _ = _read_json(obs / "plugins" / "periodic-notes" / "data.json")
    daily = data.get("daily") if isinstance(data, dict) else None
    return not (isinstance(daily, dict) and daily.get("enabled") is False)


def _inside(root: str, path: str) -> bool:
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def daily_note_path(vault: Path, day: _dt.date) -> tuple:
    """(absolute path of the daily note for `day`, "") or ("", why not).

    Reads `<vault>/.obsidian/daily-notes.json`. Opens no socket, writes
    nothing. The path is checked to stay inside the vault after resolving
    `..` and every link that exists."""
    obs = vault / ".obsidian"
    if _periodic_notes_owns_daily(obs):
        return "", ("the Periodic Notes plugin is turned on in this vault and can "
                    "decide the daily note's name, and Jarvis does not read its "
                    "settings - turn its daily notes off, or that plugin off")
    data, err = _read_json(obs / "daily-notes.json")
    if err:
        return "", f"Obsidian's daily note settings: {err}"
    if data is not None and not isinstance(data, dict):
        return "", "Obsidian's daily note settings file (daily-notes.json) is not in the expected shape"
    data = data or {}
    folder = data.get("folder") if isinstance(data.get("folder"), str) else ""
    fmt = data.get("format") if isinstance(data.get("format"), str) else ""
    fmt = fmt or DAILY_DEFAULT_FORMAT
    if "\\" in folder:
        return "", f'the daily note folder "{folder}" has a "\\" in it, which Obsidian does not use'
    parts = [s for s in folder.strip().split("/") if s not in ("", ".")]
    if ".." in parts:
        return "", f'the daily note folder "{folder}" goes up out of its folder with ".."'
    name, why = daily_name(fmt, day)
    if why:
        return "", why
    name_parts = name.split("/")
    if any(s.strip() in ("", ".", "..") for s in name_parts):
        return "", f'the date format "{fmt}" gives "{name}", which is not a usable file name'
    if not name_parts[-1].endswith(".md"):
        name_parts[-1] += ".md"
    root = os.path.realpath(str(vault))
    path = Path(root).joinpath(*parts, *name_parts)
    if not _inside(root, os.path.realpath(str(path))):
        return "", "today's daily note would be outside the vault (through a link), so nothing is written there"
    return str(path), ""


def obsidian_block(text: str) -> str:
    """The note as it is added: its own paragraph, ending in a newline."""
    return text + "\n"


def plan(target: str, text: str, *, title: str = "", notebook: str = "",
         now: Optional[_dt.datetime] = None) -> Plan:
    """Work out exactly what would be written. Opens no socket, writes nothing."""
    target = _normal_target(target)
    body = _clean(text, MAX_NOTE_CHARS)
    if target not in ACTIONS:
        return Plan(target=target, text=body, reason_empty=_BAD_TARGET)
    if not body:
        return Plan(target=target, text=body, reason_empty=_EMPTY)
    problem = _setup_problem(target)

    if target == "logseq":
        day = (now or _dt.datetime.now()).date()
        graph = logseq_graph()
        path = graph / "journals" / f"{day:%Y_%m_%d}.md"
        return Plan(target="logseq", text=body, file=str(path), day=day.isoformat(),
                    reason_empty=problem)

    if target == "obsidian":
        day = (now or _dt.datetime.now()).date()
        p = Plan(target="obsidian", text=body, day=day.isoformat(), reason_empty=problem)
        if problem:
            return p
        vault = _vault()[0]
        p.vault = os.path.realpath(str(vault))
        p.file, why = daily_note_path(vault, day)
        if why:
            p.reason_empty = why
            return p
        parent = Path(p.file).parent
        if not parent.exists():
            p.new_folder = os.path.relpath(str(parent), p.vault).replace(os.sep, "/")
        return p

    ttl = _clean(title, MAX_TITLE_CHARS).replace("\n", " ")
    if not ttl:
        first = body.split("\n", 1)[0]
        ttl = first[:80] + ("…" if len(first) > 80 else "")
    nb = _clean(notebook, MAX_NOTEBOOK_CHARS).replace("\n", " ")
    return Plan(target="joplin", text=body, title=ttl, notebook=nb, url=_joplin_base(),
                reason_empty=problem)


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
    elif p.target == "obsidian":
        exists = Path(p.file).exists()
        lines = [f"Add this to your Obsidian daily note for {p.day}:", "",
                 obsidian_block(p.text).rstrip("\n"), "",
                 f"File: {p.file}",
                 ("It is added at the end of that file, after a blank line. Nothing "
                  "already in it is changed." if exists else
                  "That file is not there yet, so it is made with just this note in it. "
                  "Your daily note template, if you use one, is not applied - only "
                  "Obsidian applies it.")]
        if p.new_folder:
            lines.append(f'The folder "{p.new_folder}" in your vault is made first, '
                         f"the way Obsidian would make it.")
        lines.append("Nothing leaves this PC.")
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
    # remove anything already in it. O_BINARY (Windows only; 0 elsewhere):
    # without it, os.open gives Windows' text mode, which writes every "\n"
    # as "\r\n" - and the byte-for-byte read-back below would then fail.
    fd = os.open(str(path), _APPEND_FLAGS, 0o644)
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


def _append_obsidian(p: Plan) -> dict:
    """Append to the daily note the card named - checked again, here, since
    the disk can change between the card and the write."""
    path = Path(p.file)
    root = p.vault
    if not root or not _inside(root, os.path.realpath(str(path))):
        return {"ok": False, "reason": "today's daily note is not inside the vault any "
                                       "more; nothing was written"}
    if not path.parent.is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Made through no link out of the vault: check where it really is.
        if not _inside(root, os.path.realpath(str(path.parent))):
            return {"ok": False, "reason": "the daily note's folder is outside the vault; "
                                           "nothing was written"}
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return {"ok": False, "reason": "the daily note is a link or a folder, not a "
                                       "plain file; nothing was written"}
    size = path.stat().st_size if path.exists() else 0
    if size > MAX_JOURNAL_BYTES:
        return {"ok": False, "reason": f"today's daily note is over "
                                       f"{MAX_JOURNAL_BYTES // (1024 * 1024)} MB, which is "
                                       f"not normal; nothing was written"}
    lead = ""
    if size:
        with open(path, "rb") as f:
            f.seek(-min(2, size), os.SEEK_END)
            tail = f.read()
        lead = "" if tail.endswith(b"\n\n") else "\n" if tail.endswith(b"\n") else "\n\n"
    block = (lead + obsidian_block(p.text)).encode("utf-8")
    fd = os.open(str(path), _APPEND_FLAGS, 0o644)     # append only - see _append_logseq
    try:
        os.write(fd, block)
    finally:
        os.close(fd)
    with open(path, "rb") as f:
        f.seek(max(0, path.stat().st_size - len(block)))
        landed = f.read() == block
    if not landed:
        return {"ok": False, "reason": "the note was written but could not be read back; "
                                       "open the daily note to check"}
    rel = os.path.relpath(str(path), root).replace(os.sep, "/")
    return {"ok": True, "target": "obsidian", "file": rel, "day": p.day}


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
        if p.target == "obsidian":
            return _append_obsidian(p)
        call =joplin_call or (lambda m, path, q, b=None: _joplin_call(m, p.url, path, q, b))
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
    return NAMES.get(target, "Joplin")


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
            where = (f"{_where(p.target)}, {out.get('file')}"
                     if p.target in ("logseq", "obsidian")
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
        code = 400 if p.reason_empty in (_EMPTY, _BAD_TARGET) else 503
        said = p.reason_empty
        if code == 503 and said == _setup_problem(p.target):
            said = f"{_where(p.target)} isn't set up on your PC - {said}"
        return code, {"ok": False, "state": "not_filed", "error": p.reason_empty,
                      "message": f"Not filed: {said}."}
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j["state"] == "waiting")
        if waiting >= _MAX_WAITING:
            # "message" too: it is the field the phone shows (NoteCapture.kt
            # describe()), and without it this refusal read "Not filed in
            # Logseq." with no reason.
            why = "several notes are already waiting for approval - answer those first"
            return 429, {"ok": False, "state": "not_filed", "error": why,
                         "message": f"Not filed: {why}."}
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
    """(http_status, job) - never the note's text.

    With no id - `GET /api/notes/capture` on its own - the answer is instead
    which targets this PC is set up for: `{"ok": true, "targets": [...]}`,
    names only (see available_targets). note-capture.patch's GET route hands
    an absent `?id=` over as "", so this needed no new route."""
    if not str(job_id or "").strip():
        return 200, {"ok": True, "targets": available_targets()}
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
        return 400, {"ok": False, "state": "not_filed", "error": "need a JSON object",
                     "message": "Not filed: the request was not a JSON object."}
    return capture(str(body.get("target") or ""), body.get("text"),
                   title=body.get("title") or "", notebook=body.get("notebook") or "")


# --------------------------------------------------------------------------
#   jarvis_agent.py's three tools
# --------------------------------------------------------------------------

def prepare_logseq_tool(args: dict):
    p = plan("logseq", args.get("text"))
    return p, describe(p)


def prepare_obsidian_tool(args: dict):
    p = plan("obsidian", args.get("text"))
    return p, describe(p)


def prepare_joplin_tool(args: dict):
    p = plan("joplin", args.get("body") if args.get("body") is not None else args.get("text"),
             title=args.get("title") or "", notebook=args.get("notebook") or "")
    return p, describe(p)
