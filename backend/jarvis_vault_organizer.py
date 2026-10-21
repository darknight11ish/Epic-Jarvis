"""An Obsidian vault, planned into a tidier shape - and NOTHING changed yet.

    POST /api/vault/organize-plan      the read-only dry run (this slice)
    GET  /api/vault/organizer          what the organizer is set to do
    POST /api/vault/organizer/enabled  the one-card switch (off by default)

WHY THIS MODULE EXISTS (the owner's decision, 2026-10-20). The mechanical
Notion converter (jarvis_notion_obsidian.py) keeps a workspace's folder tree
1-for-1, so a messy Notion workspace arrives as a messy vault: no Maps of
Content, no shared tags, orphan pages in the root. The owner approved a
Phase-2 batch organizer and could not pick an organization scheme, so the
DEFAULT IS THE SAFEST ONE: `mocs_only`. That scheme moves NO file: it only
enriches YAML frontmatter (`tags` merged, never erasing the owner's own, and an
`up: "[[_MOC - <Topic>]]"` link), builds `_MOC - <Topic>.md` hub notes and one
`00 - Vault Home.md`. `topic_folders` and `para` (which DO move notes) exist
behind the explicit `scheme` parameter for a later run, and this planner
previews their moves the same way.

TWO ROUTES, TWO HALVES. The PLAN half is genuinely read-only: it opens notes
for reading only, writes no file anywhere (not in the vault, not in the settings
folder, not in memory.db), raises no approval card and takes no action. The
WRITER half (`POST /api/vault/organize`) does exactly what a plan previewed,
under ONE approval card for the whole batch: the file guardian snapshots every
file it is about to change or move, a copy of each original is kept under the
settings folder, ONE batch receipt is recorded BEFORE the first write, writes
are atomic, no note is ever deleted, and ONE Undo puts the exact bytes AND paths
back (including moves). Both halves are described in docs/JARVIS-API.md
section 151, which also carries the owner's runbook: the FIRST REAL RUN is on a
COPY of the vault.

PREMISE-VERIFIED APIs (read from the real modules, not from a review's
guesswork), and every one of them is CALLED, never re-implemented:
  * vault resolution and the "is this a vault?" words: `jarvis_notes.obsidian_
    vault()` and `jarvis_notes.vault_problem(vault)` (jarvis_notes.py:173/218).
  * the path rule that a file must stay inside the vault: `jarvis_notes.
    _inside(root, path)` (jarvis_notes.py:504) - the same helper the vault
    search uses, so "inside" means one thing in both modules.
  * the taint latch and the one permission model are the gate's own
    (`jarvis_gate.check`/`latch_taint`, imported lazily like every other
    optional module; the plan does NOT latch - it returns previews to the
    owner's screen and never feeds note text to the model - the apply slice
    latches before it reads note text for real).
  * the switch shape is `jarvis_media_index.py`'s (OFF is immediate; ON is ONE
    `change_own_config` card at tier ask; a gate that cannot be asked, a tier
    that is not "ask", or a setting that cannot be saved changes nothing).

HARD RULES THIS MODULE KEEPS.
  * No model call and no embeddings: the clustering is pure Python (a
    deterministic TF-IDF over headings/tags/folder names, plus the note's own
    folder and database membership). `JARVIS_NO_EMBED=1` changes nothing here
    because nothing here embeds. Determinism is a test: the same vault twice
    gives the same plan_id, digest and every preview line.
  * No note text ever goes into memory: `jarvis_memory` is not imported by
    this module at all, and a plan writes no row anywhere.
  * Never delete anything: duplicates and 0-word stubs are only LISTED (the
    optional `archive_empty_stubs` flag is recorded in the plan and still moves
    nothing in this slice; the apply slice would move, never delete).
  * Path safety: every note is resolved, symlinks are refused, and anything
    outside the vault (or a different drive) is refused and NAMED in warnings.
  * Bounded work: file count, bytes per note and wall-clock time are capped, so
    a huge vault gives a partial plan that says it is partial rather than
    hanging a request.
  * PC-only and OFF BY DEFAULT: the value of `[vault_organizer] enabled` in
    jarvis-framework.toml is `false` in the shipped template. The owner turns
    it on with ONE card (`POST /api/vault/organizer/enabled`), and the routes
    are refused for any caller that is not this PC. No phone route exists and
    none is planned: the vault is a PC folder, and this plan reads its text.
  * No source pins (2026-10-20 style): nothing in the suites reads this file's
    text to prove itself.

WHAT THE PLAN RETURNS. Exactly what the next slice needs and what a person
needs to decide: the vault, the scheme, summary counts, `moves_preview` (empty
for `mocs_only`), `mocs_preview` (name + rendered body of every MOC and the
Home note), per-note tag additions and `up:` link, `duplicates_and_stubs`, a
`plan_id` and a `digest` of everything it would change, plus plain words in
`said`. The digest is what the apply slice will compare before it writes - a
vault that changed between preview and apply must refuse rather than act on a
stale plan.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

#: REUSED, NOT RE-IMPLEMENTED (the Lead's premise check): the vault resolution,
#: the "is this a vault?" words and the inside-the-root path rule live in
#: jarvis_notes.py and this module calls them. Guarded so a checkout without the
#: notes search still imports (the plan then refuses in words).
try:
    import jarvis_notes
except Exception:                                         # noqa: BLE001
    jarvis_notes = None  # type: ignore

#: The 3 schemes this planner understands. The first one is the DEFAULT and
#: moves no file; the other two are previewed only until the apply slice.
SCHEMES = ("mocs_only", "topic_folders", "para")
DEFAULT_SCHEME = "mocs_only"

#: The routes this slice serves. `ORGANIZE_PATH` (the writer) is NOT here on
#: purpose - see the module docstring.
PLAN_PATH = "/api/vault/organize-plan"
ORGANIZE_PATH = "/api/vault/organize"     # the WRITER (second slice)
STATUS_PATH = "/api/vault/organizer"
SWITCH_PATH = "/api/vault/organizer/enabled"
PATHS = (PLAN_PATH, ORGANIZE_PATH, STATUS_PATH, SWITCH_PATH)

MOC_PREFIX = "_MOC - "
HOME_NAME = "00 - Vault Home.md"
DATABASE_PREFIX = "_Database - "

#: Bounds, same shape as jarvis_notes.py's folder search: a vault is the
#: owner's own folder, and a bad one must cost a bounded request, not a hang.
MAX_FILES = 5000
MAX_FILE_BYTES = 256 * 1024
MAX_SECONDS = 10.0
MAX_CLUSTERS = 12
MAX_HEADINGS = 12
MAX_SNIPPET = 160
MAX_PREVIEW_MOVES = 2000

#: Folder buckets each moving scheme uses. Fixed strings, so a second plan on
#: the same vault goes to the same places.
TOPIC_BUCKETS = ("01 - Projects & Active", "02 - Areas & Topics",
                 "03 - Reference & Notes", "04 - Daily & Journal", "99 - Archive")
PARA_BUCKETS = ("1 - Projects", "2 - Areas", "3 - Resources", "4 - Archives")
#: RULING 8.4 (2026-10-21): there is deliberately NO database bucket. A
#: database's child rows and its `_Database - <Name>.md` hub stay in the folder
#: they are in - beside the hub's `.base`, whose `file.inFolder(...)` filter
#: names that folder - and only STANDALONE pages move under a moving scheme.
ARCHIVE_STUBS_DIR = "99 - Archive/Empty Stubs"

#: The one-card switch (jarvis_media_index.py's shape): the EXISTING
#: change_own_config action at tier ask, so the organizer adds no second
#: permission model.
SWITCH_ACTION = "change_own_config"
STATE_NAME = "vault-organizer.json"
SWITCH_CARD = ("Jarvis will organize an Obsidian vault on this PC. It reads "
               "the vault's notes, adds tags and Map-of-Content links to them, "
               "and (later, with your approval) can move notes between folders. "
               "Nothing leaves this PC. Nothing is deleted. You can turn this "
               "off again at any time.")
SWITCH_ON_WORDS = ("The vault organizer is ON. Ask it for a plan; nothing is "
                   "changed until you approve a plan.")
SWITCH_OFF_WORDS = "The vault organizer is OFF. A plan can wait."
SWITCH_ALREADY_WORDS = "The vault organizer is already on."
SWITCH_LAST_WORDS = {"enabled": "the vault organizer is on",
                     "denied": "you said no, so it stays off",
                     "timed_out": "the card timed out, so it stays off",
                     "refused": "the card was refused, so it stays off",
                     "withdrawn": "you turned it off while the card was waiting",
                     "failed": "the setting could not be saved, so it stays off"}

_OFF_WHY = ("The vault organizer is off. Turn it on first; it is off by "
            "default and turning it on is one approval card.")
_ARITY = "the organizer needs a vault folder and a scheme it knows"

#: `_PLANS` keeps the most recent plans in memory for the apply slice to look
#: up by plan_id. Nothing here is written to disk (the plan is not a setting),
#: and it is capped: a plan is useful for minutes, not days.
_PLANS: dict = {}
_PLANS_LOCK = threading.Lock()
_PLAN_KEEP = 8

_P_LOCK = threading.Lock()
_PENDING: dict = {"id": "", "since": 0.0}
_WITHDRAWN: dict = {}
_LAST_CARD: dict = {}
_SWITCH = threading.Lock()

_SHA = re.compile(r"^[0-9a-f]{64}$")
_LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.M)
_TASK = re.compile(r"^\s*[-*]\s+\[ \]\s+", re.M)
_WORD = re.compile(r"[A-Za-z0-9']+")
_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_STOP = frozenset("""
a about after all also am an and any are as at be because been before being
between both but by can could did do does doing done down each even few for
from further had has have having he her here hers him his how i if in into is
it its itself just me more most my no nor not now of off on once only or other
our out over own same she should so some such than that the their them then
there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your
""".split())

#: The reasons a plan can be partial, in words, so a caller prints them.
PARTIAL_WORDS = {
    "files": f"only the first {MAX_FILES} notes were read",
    "time": f"the scan reached its {MAX_SECONDS:g} s limit",
}


# --------------------------------------------------------------------------
#   Where the owner's settings folder is (the project's own rule)
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    for key in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        value = os.environ.get(key)
        if value:
            return Path(os.path.expanduser(value))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def state_path() -> Path:
    """The switch's own small JSON, beside the other modules' settings files."""
    return _config_dir() / STATE_NAME


# --------------------------------------------------------------------------
#   The switch: OFF by default behind [vault_organizer] enabled = false
# --------------------------------------------------------------------------

def _framework_section() -> dict:
    """`[vault_organizer]` from the owner's settings file, or {}.

    Guarded and lazy: this module loads on a PC whose framework module is
    absent (the suites exercise it that way), and an unreadable file means
    OFF - the fail-closed direction for a feature that reads a whole vault.
    """
    try:
        import jarvis_framework as fw
        return (fw.load_framework() or {}).get("vault_organizer", {}) or {}
    except Exception:
        return {}


def _switch_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def enabled() -> bool:
    """The organizer is ON only when someone said so: the override file the
    one-card switch writes wins, and the shipped `[vault_organizer] enabled`
    value (false in the template) is the default."""
    state = _switch_state()
    if isinstance(state, dict) and "enabled" in state:
        return state.get("enabled") is True
    return _framework_section().get("enabled") is True


def set_enabled(on: bool) -> dict:
    """Write the switch. OFF also withdraws a waiting card. Never raises."""
    on = bool(on)
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"enabled": on}), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:                              # noqa: BLE001
        return {"ok": False, "enabled": enabled(),
                "error": f"the organizer's setting could not be saved "
                         f"({type(exc).__name__}), so it did not change"}
    return {"ok": True, "enabled": on,
            "message": SWITCH_ON_WORDS if on else SWITCH_OFF_WORDS}


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only. NEVER a note's name or words.
    try:
        mod = sys.modules.get("jarvis_framework")
        if mod is not None:
            mod.audit_log(event, detail)
    except Exception:
        pass


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        mod = sys.modules.get("jarvis_framework")
        return str(mod.action_tier(action))
    except Exception as exc:                              # noqa: BLE001
        return f"unreadable ({type(exc).__name__})"


def _start_card_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-vault-organizer-card",
                     daemon=True).start()


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.pop(pid, None)
        _LAST_CARD.clear()
        _LAST_CARD.update(outcome=outcome, at=time.time(), why=why,
                          message=SWITCH_LAST_WORDS.get(outcome, ""))
    _audit("vault_organizer.switch.card", {"outcome": outcome})


def _decide(pid: str, gate: Callable, tier_of: Callable) -> None:
    detail = {"text": SWITCH_CARD,
              "what": "organize an Obsidian vault on this PC",
              "setting": "vault_organizer_enabled", "to": True,
              "leaves_this_pc": False}
    try:
        v = gate(SWITCH_ACTION, detail, SWITCH_CARD)
    except Exception as exc:                              # noqa: BLE001
        return _finish(pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(SWITCH_ACTION) != "ask":
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a "
                       f"person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH:
        with _P_LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn",
                           "you turned it off while the card was waiting")
        out = set_enabled(True)
        if out.get("ok") is False:
            return _finish(pid, "failed", str(out.get("error", "")))
        _finish(pid, "enabled")


def request_enabled(on, *, gate: Optional[Callable] = None,
                    tier_of: Optional[Callable[[str], str]] = None,
                    spawn: Optional[Callable] = None) -> tuple:
    """Ask for the switch to change. (http code, body).

    ON is never applied here: it raises ONE normal approval card and answers
    202 {"waiting": true}. OFF is immediate (200), withdraws a waiting card
    and never asks."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _start_card_thread
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
    if not on:
        with _SWITCH:
            with _P_LOCK:
                if _PENDING:
                    _WITHDRAWN[_PENDING.get("id", "")] = True
                    _PENDING.clear()
            out = dict(set_enabled(False) or {})
        out.setdefault("ok", True)
        out.update(enabled=False, waiting=False, message=SWITCH_OFF_WORDS)
        _audit("vault_organizer.switch.off", {})
        return 200, out
    if enabled():
        return 200, {"ok": True, "enabled": True, "waiting": False,
                     "message": SWITCH_ALREADY_WORDS}
    with _SWITCH:
        with _P_LOCK:
            if _PENDING:
                return 202, {"ok": True, "enabled": False, "waiting": True,
                             "pending": dict(_PENDING),
                             "message": "one card is already waiting"}
            pid = "vc" + hashlib.sha256(
                f"{time.time()}:{os.getpid()}".encode("utf-8")).hexdigest()[:12]
            _PENDING.clear()
            _PENDING.update(id=pid, since=time.time())
    try:
        spawn(lambda: _decide(pid, gate, tier_of))
    except Exception as exc:                              # noqa: BLE001
        return _finish_result(pid, 503,
                              f"the approval card could not be shown "
                              f"({type(exc).__name__}), so nothing changed")
    return 202, {"ok": True, "enabled": False, "waiting": True,
                 "pending_id": pid, "message": SWITCH_ON_WORDS}


def _finish_result(pid: str, code: int, why: str) -> tuple:
    _finish(pid, "failed", why)
    return code, {"ok": False, "enabled": enabled(), "waiting": False,
                  "error": why}


def switch_status() -> dict:
    with _P_LOCK:
        pending = dict(_PENDING)
        last = dict(_LAST_CARD)
    return {"enabled": enabled(), "waiting": bool(pending),
            "pending": pending or None, "last_card": last or None,
            "action": SWITCH_ACTION, "tier": _tier(SWITCH_ACTION)}


# --------------------------------------------------------------------------
#   Reading one note (READ ONLY - nothing below opens a file for writing)
# --------------------------------------------------------------------------

@dataclass
class Note:
    """What the planner knows about ONE note. Holds no full body text: only
    the first sentence (already scrubbed) is kept for the MOC preview."""
    rel: str = ""
    folder: str = ""
    name: str = ""
    title: str = ""
    sha: str = ""
    size: int = 0
    words: int = 0
    frontmatter: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    headings: list = field(default_factory=list)
    links: list = field(default_factory=list)
    tasks: int = 0
    snippet: str = ""
    kind: str = "note"          # note | database | moc | home
    topic: str = ""
    moc: str = ""
    tags_added: list = field(default_factory=list)
    tags_after: list = field(default_factory=list)
    up_link: str = ""
    new_rel: str = ""
    duplicate_of: str = ""
    stub: bool = False

    def move_row(self) -> dict:
        return {"title": self.title, "from_path": self.rel,
                "to_path": self.new_rel or self.rel,
                "tags_added": list(self.tags_added),
                "tags_after": list(self.tags_after),
                "up": self.up_link, "moc": self.moc}


def _read(path: Path) -> tuple:
    """(text, raw bytes, size). A file over MAX_FILE_BYTES is NOT read: the
    caller is told it was too big, rather than it looking like an empty note."""
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            return "", b"", size
        raw = path.read_bytes()
        return raw.decode("utf-8", "replace"), raw, len(raw)
    except OSError:
        return "", b"", -1


def _split_frontmatter(text: str) -> tuple:
    """(frontmatter dict, body). A small parser for the YAML this repository
    writes and Obsidian reads: `key: value`, `key: [a, b]`, and `key:` followed
    by `- item` lines. Never raises on odd text - the raw block is kept in
    `frontmatter["_raw"]` so nothing is lost to a preview."""
    fm: dict = {}
    body = text
    if text.startswith("---"):
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end = i
                    break
            if end is not None:
                raw = "\n".join(lines[1:end])
                fm["_raw"] = raw
                key = ""
                for line in lines[1:end]:
                    if not line.strip():
                        continue
                    if line.lstrip().startswith("- ") and key:
                        fm.setdefault(key, [])
                        if isinstance(fm[key], list):
                            fm[key].append(_yaml_scalar(line.lstrip()[2:]))
                        continue
                    m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", line.strip())
                    if not m:
                        continue
                    key = m.group(1)
                    rest = m.group(2).strip()
                    fm[key] = _yaml_value(rest)
                body = "\n".join(lines[end + 1:])
    return fm, body


def _yaml_scalar(text: str):
    text = str(text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    return text


def _yaml_value(text: str):
    text = str(text or "").strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_yaml_scalar(part) for part in inner.split(",")] if inner else []
    return _yaml_scalar(text)


def _as_tags(value) -> list:
    """Existing tags as a clean list: a YAML list or a comma string. The
    OWNER's words are kept exactly as they are (case and order); only empty
    entries and duplicates are dropped."""
    out, seen = [], set()
    items = value if isinstance(value, list) else (
        re.split(r"[,\s]+", str(value or "")) if str(value or "").strip() else [])
    for item in items:
        name = str(item or "").strip().lstrip("#").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _kebab(text: str) -> str:
    words = [w for w in _WORD.findall(str(text or "").lower())
             if len(w) > 1 and w not in _STOP]
    return "-".join(words[:4])


def _clean_title(text: str) -> str:
    text = _BAD_NAME.sub(" ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text[:120] or "Untitled"


def _prose_only(text: str) -> str:
    """The note's own words, without its heading lines or task markers. What
    "empty" means: a note holding only a title is a stub, and a note with a
    sentence is not."""
    keep = []
    for line in str(text or "").splitlines():
        if line.lstrip().startswith("#"):
            continue
        keep.append(re.sub(r"^\s*[-*]\s+\[[ xX]\]\s*", "", line))
    return "\n".join(keep)


def _snippet(text: str) -> str:
    """The first non-heading sentence, with the project's own scrubbers when
    they are beside this module. Never raises, never returns a model marker."""
    for line in str(text or "").splitlines():
        if line.lstrip().startswith("#"):
            continue
        line = re.sub(r"^\s*[-*]\s+\[[ xX]\]\s*", "", line)
        line = re.sub(r"[*_`>#]+", "", line).strip()
        if not line:
            continue
        sentence = re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0].strip()
        if not sentence:
            continue
        try:
            import jarvis_scrub
            sentence = jarvis_scrub.scrub_text(sentence)
        except Exception:                                 # noqa: BLE001
            pass
        try:
            import jarvis_agent
            sentence = jarvis_agent.strip_chat_markers(sentence)
        except Exception:                                 # noqa: BLE001
            pass
        return sentence[:MAX_SNIPPET]
    return ""


def _note_from(path: Path, vault: Path, rel: str) -> tuple:
    """(Note, ""), or (None, why) when the path rules or the read caps refuse
    it. Nothing here changes a file."""
    if os.path.islink(str(path)):
        return None, "it is a link, and links are refused"
    try:
        real = os.path.realpath(str(path))
    except OSError:
        return None, "its real path could not be resolved"
    if not jarvis_notes._inside(os.path.realpath(str(vault)), real):
        return None, "its real path is outside the vault"
    text, raw, size = _read(path)
    if size < 0:
        return None, "it could not be read"
    if size > MAX_FILE_BYTES:
        return None, f"it is bigger than the organizer's {MAX_FILE_BYTES} byte ceiling"
    fm, body = _split_frontmatter(text)
    note = Note(rel=rel, folder=str(Path(rel).parent).replace("\\", "/"),
                name=path.name, title=path.stem, sha=_sha_bytes(raw),
                size=size, words=len(_WORD.findall(_prose_only(body))),
                frontmatter=fm, tags=_as_tags(fm.get("tags")))
    note.headings = [m.group(2).strip() for m in _HEADING.finditer(body)][:MAX_HEADINGS]
    note.links = [m.group(1).strip() for m in _LINK.finditer(body)]
    note.tasks = len(_TASK.findall(body))
    note.snippet = _snippet(body)
    if note.name.startswith(MOC_PREFIX):
        note.kind = "moc"
    elif note.name == HOME_NAME:
        note.kind = "home"
    elif note.name.startswith(DATABASE_PREFIX):
        note.kind = "database"
    note.stub = bool(note.kind == "note" and note.words == 0
                     and not note.links and not note.tasks)
    return note, ""


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
#   The read-only plan
# --------------------------------------------------------------------------

@dataclass
class Plan:
    vault: str = ""
    scheme: str = DEFAULT_SCHEME
    max_clusters: int = MAX_CLUSTERS
    plan_id: str = ""
    digest: str = ""
    notes: list = field(default_factory=list)      # [Note]
    moves: list = field(default_factory=list)      # [dict]
    mocs: list = field(default_factory=list)       # [{name, body, topic, notes}]
    home: dict = field(default_factory=dict)       # {name, body}
    duplicates: list = field(default_factory=list)
    stubs: list = field(default_factory=list)
    tag_plan: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    partial: list = field(default_factory=list)
    archive_stubs: bool = False
    created: float = 0.0

    def summary(self) -> dict:
        notes = [n for n in self.notes if n.kind == "note"]
        return {
            "notes_scanned": len(notes),
            "notes_moved": len(self.moves),
            "notes_tagged": len([n for n in notes if n.tags_added]),
            "mocs_to_create": len(self.mocs),
            "databases_indexed": len([n for n in self.notes if n.kind == "database"]),
            "links_rewritten": _incoming_links_to_moved_notes(self.notes),
            "duplicates_found": len(self.duplicates),
            "empty_stubs_found": len(self.stubs),
        }

    def payload(self) -> dict:
        return {
            "ok": True,
            "plan_id": self.plan_id,
            "digest": self.digest,
            "vault": self.vault,
            "scheme": self.scheme,
            "max_clusters": self.max_clusters,
            "summary": self.summary(),
            "moves_preview": self.moves,
            "mocs_preview": self.mocs,
            "home_preview": self.home,
            "tag_plan": self.tag_plan,
            "duplicates_and_stubs": {"duplicates": self.duplicates,
                                     "empty_stubs": self.stubs,
                                     "archive_empty_stubs": self.archive_stubs},
            "partial": list(self.partial),
            "warnings": list(self.warnings),
            "said": describe(self),
        }


def _incoming_links_to_moved_notes(notes: list) -> int:
    """How many wiki-links, anywhere in the vault, point at a note this plan
    would move. The apply slice rewrites exactly these; a link to a note that
    is not moving is not touched (and a link to something outside the vault is
    not a link the plan can rewrite)."""
    moved = {n.name[:-3] for n in notes
             if n.kind == "note" and n.new_rel and n.new_rel != n.rel}
    if not moved:
        return 0
    total = 0
    for note in notes:
        if note.kind != "note":
            continue
        for target in note.links:
            if target.split("/")[-1] in moved:
                total += 1
    return total


def describe(plan: Plan) -> str:
    s = plan.summary()
    scheme_words = {
        "mocs_only": "without moving a single file",
        "topic_folders": "into topic folders",
        "para": "into Projects / Areas / Resources / Archives",
    }[plan.scheme]
    lines = [f"A plan for \"{Path(plan.vault).name}\", {scheme_words}:",
             f"  {s['notes_scanned']:,} note(s) read, {s['notes_tagged']:,} to "
             f"be tagged, {s['mocs_to_create']:,} Map-of-Content note(s) and "
             f"1 Vault Home to be created."]
    if s["notes_moved"]:
        lines.append(f"  {s['notes_moved']:,} note(s) would move; "
                     f"{s['links_rewritten']:,} link(s) point at them.")
    if s["duplicates_found"] or s["empty_stubs_found"]:
        lines.append(f"  {s['duplicates_found']:,} duplicate(s) and "
                     f"{s['empty_stubs_found']:,} empty stub(s) found - "
                     f"listed, never deleted.")
    if plan.partial:
        lines.append("  Partial: " + "; ".join(plan.partial) + ".")
    lines.append("Nothing has been changed yet.")
    return "\n".join(lines)


def _scan(vault: Path, plan: Plan, deadline: float) -> None:
    """Read every note under `vault` into `plan.notes`; refuses what the path
    rules refuse, and records every refusal in `plan.warnings`."""
    root = os.path.realpath(str(vault))
    counted = 0
    try:
        paths = sorted(p for p in vault.rglob("*.md") if p.is_file())
    except OSError as exc:                                # noqa: BLE001
        plan.warnings.append(f"the vault could not be listed "
                             f"({type(exc).__name__})")
        return
    for path in paths:
        if time.monotonic() > deadline:
            plan.partial.append(PARTIAL_WORDS["time"])
            break
        counted += 1
        if counted > MAX_FILES:
            plan.partial.append(PARTIAL_WORDS["files"])
            break
        try:
            rel = os.path.relpath(str(path), str(vault)).replace("\\", "/")
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.split("/")[:-1]):
            continue                                    # .obsidian, .trash, ...
        note, why = _note_from(path, vault, rel)
        if note is None:
            # Named but never printed with its words: a plan is data about
            # files, and a warning must not copy a note into a log.
            plan.warnings.append(f"a path under the vault was refused ({why})")
            continue
        plan.notes.append(note)
    # A link is "outgoing" only to a note THIS vault holds; anything else is
    # an external address or a note that does not exist, and a plan must not
    # count it as a link it would rewrite.
    names = {n.name[:-3] for n in plan.notes if n.kind == "note"}
    for note in plan.notes:
        note.links = [t for t in note.links if t.split("/")[-1] in names]


def _idf(notes: list) -> dict:
    total = len(notes)
    df: dict = {}
    for note in notes:
        words = {w for w in _WORD.findall(" ".join(
            [note.title] + note.headings).lower())
            if len(w) > 2 and w not in _STOP}
        for w in words:
            df[w] = df.get(w, 0) + 1
    return {w: math.log((total + 1) / (count + 1)) + 1.0 for w, count in df.items()}


def _folder_topic(note: Note) -> str:
    """The note's own folder, cleaned of the numeric prefix a scheme adds."""
    parts = [p for p in note.folder.split("/") if p and not p.startswith(".")]
    if not parts:
        return ""
    return _clean_title(re.sub(r"^\d+\s*[-_. ]\s*", "", parts[0]))


def _note_topic(note: Note, idf: dict) -> str:
    """The single deterministic topic a note belongs to for MOC purposes.

    In order: the database it came from, its own folder, its first heading,
    then the highest-scoring word by TF-IDF (ties broken by the word itself, so
    two runs cannot disagree). "General" is the honest last resort.
    """
    database = str(note.frontmatter.get("database") or "").strip()
    if database:
        return _clean_title(database)
    folder = _folder_topic(note)
    if folder:
        return folder
    for heading in note.headings:
        cleaned = _clean_title(heading)
        if cleaned and cleaned.lower() not in ("untitled", "index", "summary"):
            return cleaned
    scores = sorted(((-round(score, 6), word) for word, score in
                     _tfidf_words(note, idf).items()))
    if scores:
        return _clean_title(scores[0][1].replace("-", " ").title())
    return "General"


def _tfidf_words(note: Note, idf: dict) -> dict:
    counts: dict = {}
    for word in _WORD.findall(" ".join([note.title] + note.headings).lower()):
        if len(word) > 2 and word not in _STOP:
            counts[word] = counts.get(word, 0) + 1
    return {w: count * idf.get(w, 1.0) for w, count in counts.items()}


def _moc_name(topic: str) -> str:
    return MOC_PREFIX + _clean_title(topic) + ".md"


def _assign_topics(plan: Plan) -> None:
    """Give every note a topic and a MOC, and cap the number of clusters.

    Deterministic: notes are sorted by path; a note's topic is a pure function
    of its own frontmatter/headings/TF-IDF, and the cap merges the SMALLEST
    topics into "General" (ties by name), so the same vault always produces the
    same clusters.
    """
    notes = [n for n in plan.notes if n.kind == "note"]
    idf = _idf(notes)
    for note in sorted(notes, key=lambda n: n.rel):
        note.topic = _clean_title(_note_topic(note, idf)) or "General"
    for note in plan.notes:
        if note.kind == "database":
            stem = note.name[len(DATABASE_PREFIX):] if note.name.startswith(
                DATABASE_PREFIX) else note.name
            note.topic = _clean_title(stem[:-3] if stem.lower().endswith(".md")
                                      else stem) or "General"
            note.moc = _moc_name(note.topic)
            note.up_link = "[[{}]]".format(note.moc[:-3])
    groups: dict = {}
    for note in notes:
        groups.setdefault(note.topic, []).append(note)
    keep = max(1, min(int(plan.max_clusters or MAX_CLUSTERS), MAX_CLUSTERS))
    while len(groups) > keep:
        candidates = [name for name in groups if name != "General"]
        if not candidates:
            break
        smallest = sorted((name for name in candidates),
                          key=lambda name: (len(groups[name]), name))[0]
        merged = groups.pop(smallest)
        for note in merged:
            note.topic = "General"
            groups.setdefault("General", []).append(note)
    for note in notes:
        note.moc = _moc_name(note.topic)
        note.up_link = "[[{}]]".format(note.moc[:-3])


def _infer_tags(note: Note) -> list:
    """1-4 clean lowercase kebab-case tags, inferred from what the note already
    is (folder, database, first heading, topic). The owner's existing tags stay
    first and are never replaced - `tags_after` shows the merge."""
    out: list = []
    seen = {t.lower() for t in note.tags}

    def add(text):
        tag = _kebab(text)
        if not tag or tag in seen:
            return
        seen.add(tag)
        out.append(tag)

    add(note.topic)
    database = str(note.frontmatter.get("database") or "")
    if database:
        add(database)
    folder = _folder_topic(note)
    if folder and folder != note.topic:
        add(folder)
    for heading in note.headings[:2]:
        add(heading)
    return out[:4]


def _tags_after(note: Note) -> list:
    """Owner's tags exactly as they were, then the new ones (never a duplicate
    in either case), so an apply slice can merge without erasing."""
    merged = list(note.tags)
    seen = {t.lower() for t in merged}
    for tag in note.tags_added:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            merged.append(tag)
    return merged


def _moc_body(topic: str, members: list, databases: list) -> str:
    """The Map-of-Content note for one topic. Pure function of its inputs:
    counts, the database index notes that belong here, the notes with open
    tasks, and a bullet per note with its one-line preview."""
    open_tasks = [n for n in members if n.tasks]
    lines = [f"# {topic}", "",
             f"{len(members):,} note(s), "
             f"{sum(n.tasks for n in members):,} open task(s) in this topic."]
    if databases:
        lines.append("\n## Databases")
        for db in databases:
            lines.append(f"- [[{db.title}]]")
    lines.append("\n## Notes")
    for note in sorted(members, key=lambda n: (n.title.lower(), n.rel)):
        hint = f" - {note.snippet}" if note.snippet else ""
        lines.append(f"- [[{note.title}]]{hint}")
    if open_tasks:
        lines.append("\n## Open tasks")
        for note in sorted(open_tasks, key=lambda n: (n.title.lower(), n.rel)):
            lines.append(f"- [[{note.title}]] - {note.tasks} open task(s)")
    return "\n".join(lines).rstrip() + "\n"


def _home_body(plan: Plan) -> str:
    notes = [n for n in plan.notes if n.kind == "note"]
    mocs = sorted(m["name"] for m in plan.mocs)
    dbs = sorted(n.name for n in plan.notes if n.kind == "database")
    lines = ["# Vault Home", "",
             f"A map of this vault, organized on the PC by Jarvis. "
             f"{len(notes):,} note(s) in {len(mocs):,} topic(s).", ""]
    lines.append("## Maps of Content")
    for name in mocs:
        lines.append(f"- [[{name[:-3]}]]")
    lines.append("\n## Databases")
    if dbs:
        for name in dbs:
            lines.append(f"- [[{name[:-3]}]]")
    else:
        lines.append("- (none indexed yet)")
    lines.append("\n## Review Queue: Duplicates & Empty Stubs")
    if plan.duplicates:
        lines.append(f"- {len(plan.duplicates):,} duplicate note(s) listed - "
                     f"nothing is deleted")
    if plan.stubs:
        lines.append(f"- {len(plan.stubs):,} empty stub(s) listed - "
                     f"nothing is deleted")
    if not plan.duplicates and not plan.stubs:
        lines.append("- nothing to review")
    return "\n".join(lines).rstrip() + "\n"


def _find_duplicates(plan: Plan) -> None:
    """Exact duplicates by body hash (frontmatter included in the hash, so two
    stubs with different ids are not called duplicates). Listed only."""
    seen: dict = {}
    for note in sorted((n for n in plan.notes if n.kind == "note"),
                       key=lambda n: n.rel):
        if note.stub:
            continue
        if note.sha in seen:
            plan.duplicates.append({"sha": note.sha[:12],
                                    "keep": seen[note.sha],
                                    "duplicate": note.rel})
        else:
            seen[note.sha] = note.rel


def _assign_paths(plan: Plan) -> None:
    """The new path for every note under a moving scheme. `mocs_only` assigns
    none (old == new, no file moves). Deterministic collision handling: two
    notes never get one new path; the second gets " (2)".

    RULING 8.4 (2026-10-21, accepted from the combined overnight rulings): the
    database rows do NOT move. A note whose frontmatter carries `database:` and
    the `_Database - <Name>.md` hub it belongs to stay exactly where they are,
    because the hub's `.base` filter (`file.inFolder(...)`) names the folder
    they are already in - moving the rows would leave that filter pointing at
    an empty folder and break the database view with no warning. Only
    STANDALONE pages are moved by `topic_folders`/`para`; the rows still get
    their tags and up: link in place, exactly as `mocs_only` does."""
    notes = [n for n in plan.notes if n.kind in ("note", "database")]
    if plan.scheme == "mocs_only":
        for note in notes:
            note.new_rel = note.rel
        return
    used: set = set()
    for note in sorted(notes, key=lambda n: n.rel):
        title = _clean_title(note.title) + ".md"
        database = str(note.frontmatter.get("database") or "").strip()
        if note.kind == "database" or database:
            # Ruling 8.4: in place, beside the hub and its .base. No move row,
            # no path collision, and the tag/up: enrichment above still ran.
            note.new_rel = note.rel
            continue
        if plan.scheme == "topic_folders":
            bucket = ("01 - Projects & Active" if note.tasks
                      else "02 - Areas & Topics")
            dest = f"{bucket}/{note.topic}/{title}"
        else:                                            # para
            status = str(note.frontmatter.get("status") or "").lower()
            if note.tasks or note.frontmatter.get("project") or status in (
                    "in progress", "doing", "todo"):
                dest = f"1 - Projects/{title}"
            elif status in ("done", "archived", "complete", "completed"):
                dest = f"4 - Archives/{title}"
            elif note.stub:
                dest = f"4 - Archives/Empty Stubs/{title}"
            elif note.frontmatter.get("area") or note.folder:
                dest = f"2 - Areas/{note.topic}/{title}"
            else:
                dest = f"3 - Resources/{note.topic}/{title}"
        dest = _unique_rel(dest, used)
        used.add(dest)
        note.new_rel = dest
        if dest != note.rel:
            plan.moves.append(note.move_row())


def _unique_rel(dest: str, used: set) -> str:
    if dest not in used:
        return dest
    stem, ext = os.path.splitext(dest)
    n = 2
    while f"{stem} ({n}){ext}" in used:
        n += 1
    return f"{stem} ({n}){ext}"


def _digest(plan: Plan) -> str:
    """A short fingerprint of EVERYTHING the plan would change. The apply
    slice compares it before it writes, so a vault edited between preview and
    approval refuses instead of acting on a stale plan. Pure function of the
    plan's actions, not of times or ids."""
    canonical = {
        "vault": plan.vault,
        "scheme": plan.scheme,
        "moves": sorted((m["from_path"], m["to_path"], tuple(m["tags_added"]),
                         m["up"]) for m in plan.moves),
        "mocs": sorted((m["name"], _sha_bytes(m["body"].encode("utf-8")))
                       for m in plan.mocs),
        "home": _sha_bytes(plan.home.get("body", "").encode("utf-8")),
        "notes": sorted((n.rel, n.new_rel, tuple(n.tags_added), n.up_link,
                         n.sha, n.words)
                        for n in plan.notes if n.kind == "note"),
    }
    raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return _sha_bytes(raw)[:16]


def plan_vault_organization(vault=None, *, scheme: str = DEFAULT_SCHEME,
                            max_clusters: int = MAX_CLUSTERS,
                            archive_empty_stubs: bool = False) -> dict:
    """The 100% read-only dry run: what a tidy-up WOULD do, and nothing else.

    `vault` defaults to the owner's configured vault (`[notes.obsidian]
    vault_directory`, `JARVIS_OBSIDIAN_VAULT` wins) through `jarvis_notes.
    obsidian_vault()`. `scheme` is one of SCHEMES; the default is the least
    destructive one, `mocs_only`, which moves no file. The return value is the
    preview payload described in the module docstring.

    Everything this opens is opened for reading. No file is created, changed,
    moved or deleted, no card is raised, no model is called, and no note text
    is stored anywhere - the snapshot of note bodies lives only in this
    function's local variables, except the one-line scrubbed snippets that the
    preview itself is made of.
    """
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    if jarvis_notes is None:
        return {"ok": False, "error": "the notes module is not on this backend",
                "why": "the organizer reuses jarvis_notes for the vault "
                       "resolution and the inside-the-vault rule"}
    if scheme not in SCHEMES:
        return {"ok": False, "error": f"unknown scheme {scheme!r}",
                "schemes": list(SCHEMES)}
    target = Path(vault) if vault is not None else jarvis_notes.obsidian_vault()
    if target is None:
        return {"ok": False, "error": "no vault folder is set",
                "why": "put its path in [notes.obsidian] vault_directory in "
                       "jarvis-framework.toml, or in JARVIS_OBSIDIAN_VAULT"}
    problem = jarvis_notes.vault_problem(target)
    if problem:
        return {"ok": False, "error": problem}
    plan = Plan(vault=os.path.realpath(str(target)), scheme=scheme,
                max_clusters=max(1, min(int(max_clusters or MAX_CLUSTERS),
                                        MAX_CLUSTERS)),
                archive_stubs=bool(archive_empty_stubs), created=time.time())
    _scan(Path(plan.vault), plan, deadline)
    _assign_topics(plan)
    _find_duplicates(plan)
    plan.stubs = [n.rel for n in plan.notes if n.stub]
    _assign_paths(plan)
    for note in plan.notes:
        if note.kind != "note":
            continue
        note.tags_added = _infer_tags(note)
        note.tags_after = _tags_after(note)
        if note.tags_added or note.up_link:
            plan.tag_plan.append({"path": note.rel, "title": note.title,
                                  "moc": note.moc,
                                  "tags_before": list(note.tags),
                                  "tags_added": list(note.tags_added),
                                  "tags_after": list(note.tags_after),
                                  "up": note.up_link})
    topics: dict = {}
    for note in plan.notes:
        if note.kind == "note":
            topics.setdefault(note.topic, []).append(note)
    databases_by_topic: dict = {}
    for note in plan.notes:
        if note.kind == "database":
            databases_by_topic.setdefault(note.topic, []).append(note)
    for topic in sorted(topics):
        members = sorted(topics[topic], key=lambda n: (n.title.lower(), n.rel))
        body = _moc_body(topic, members, databases_by_topic.get(topic, []))
        plan.mocs.append({"name": _moc_name(topic), "topic": topic,
                          "body": body, "notes": [n.rel for n in members]})
    if plan.notes:
        plan.home = {"name": HOME_NAME, "body": _home_body(plan)}
    plan.digest = _digest(plan)
    plan.plan_id = "vplan_" + plan.digest
    with _PLANS_LOCK:
        _PLANS[plan.plan_id] = plan
        while len(_PLANS) > _PLAN_KEEP:
            _PLANS.pop(next(iter(_PLANS)), None)
    if not plan.notes:
        plan.warnings.append("the vault holds no notes yet, so there is "
                             "nothing to organize")
    _audit("vault_organizer.plan", {
        "scheme": scheme, "notes": len([n for n in plan.notes if n.kind == "note"]),
        "moves": len(plan.moves), "mocs": len(plan.mocs),
        "partial": len(plan.partial)})
    return plan.payload()


def get_plan(plan_id: str) -> Optional[Plan]:
    """The last plan with that id, or None. In memory only, capped: the apply
    slice will use it, and a plan older than the last few requests is refused
    rather than acted on."""
    with _PLANS_LOCK:
        return _PLANS.get(str(plan_id or ""))


def reset_for_tests() -> None:
    """Clear the in-memory plans and the switch's card state. Never touches a
    file (the switch's own JSON is the owner's and is left alone)."""
    with _PLANS_LOCK:
        _PLANS.clear()
    with _P_LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST_CARD.clear()


# --------------------------------------------------------------------------
#   The routes - a plug-in folder calls install()
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
#   THE WRITER: ONE card, a snapshot of every file it touches, ONE batch
#   receipt, and ONE Undo that puts the whole vault back
# --------------------------------------------------------------------------
#
# THIS IS THE SECOND SLICE of the Phase-2 organizer (the plan half is the
# read-only `POST /api/vault/organize-plan` above). Nothing here runs until a
# person has (a) looked at a plan, (b) kept its plan_id and digest, and
# (c) approved ONE card for the whole batch. It moves no file in the default
# `mocs_only` scheme; the moving schemes do exactly the moves the plan
# previewed.
#
# THE ORDER IS THE SAFETY STORY:
#   1. the plan is looked up and its digest is checked against a FRESH plan of
#      the same vault - a vault edited after the preview is refused as stale,
#      never acted on;
#   2. the taint latch fires because this operation reads note text for real;
#   3. ONE `organize_obsidian_vault` card at tier ask - a denied, timed-out or
#      refused card writes NOTHING (the snapshots have not been taken yet);
#   4. `jarvis_file_guardian.snapshot_before_write()` saves the current bytes
#      of EVERY existing file about to be changed, moved or replaced. If any
#      snapshot fails, the whole batch refuses before a byte is written;
#   5. a copy of every original is also written under the settings folder
#      (`vault-organizer-backups/<plan_id>/`) with a manifest, and ONE
#      `jarvis_receipts.py` receipt is recorded BEFORE the first write;
#   6. writes are atomic (`.tmp` + `os.replace`) and NO file is ever deleted:
#      duplicates and empty stubs are listed only;
#   7. one Undo (the receipt's own) restores the exact bytes AND paths, removes
#      only the files this batch created, and removes only the folders it made.

ORGANIZE_PATH = "/api/vault/organize"
GATE_ACTION = "organize_obsidian_vault"
TAINT_WHY = "vault_organize"
RECEIPT_TOOL = "organize_obsidian_vault"
BACKUP_ROOT = "vault-organizer-backups"
MAX_RECEIPT_FILES = 2000

_APPLY_LOCK = threading.Lock()

ORGANIZE_CARD = (
    "Jarvis will organize the Obsidian vault \"{name}\" on this PC.\n"
    "  Plan: {scheme_words}.\n"
    "  {files} file(s) will change: {notes} note(s) get tags and an up: link,"
    "{moves} note(s) move, {creates} note(s) are created (Maps of Content and"
    " Vault Home).\n"
    "  Nothing is deleted - duplicates and empty stubs are only listed.\n"
    "  A copy of every file it changes is saved first, so ONE Undo puts the"
    " whole vault back.\n"
    "  The plan you looked at still matches the vault (digest {digest})."
)
SCHEME_WORDS = {
    "mocs_only": "no file moves; tags, Map-of-Content notes and a Vault Home",
    "topic_folders": "notes grouped into topic folders under fixed numbered buckets",
    "para": "notes grouped into Projects / Areas / Resources / Archives",
}


def _scheme_words(scheme: str) -> str:
    return SCHEME_WORDS.get(scheme, scheme)


def _latch_taint(why: str = TAINT_WHY) -> bool:
    """Mark the conversation private before this operation reads note text.

    The PLAN does not latch (it answers the owner's own screen); the WRITER
    does, because the notes it reads are outside text. False when the gate is
    not beside this module - never raises on a read."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why=why))
    except Exception:                                     # noqa: BLE001
        return False


def _receipts():
    import jarvis_receipts
    return jarvis_receipts


def _guardian():
    import jarvis_file_guardian
    return jarvis_file_guardian


def _snapshot_before_write(path: str, vault: str) -> dict:
    """The REAL file guardian, asked for one file's current bytes. Never a
    second store, never a copy made here: `roots` is this vault, so a path
    outside it is refused there exactly as it would be anywhere else."""
    try:
        return _guardian().snapshot_before_write(
            path, reason="organize_obsidian_vault", roots=[vault])
    except Exception as exc:                              # noqa: BLE001
        return {"ok": False, "resolved": True,
                "error": f"guardian_failed ({type(exc).__name__})",
                "words": "the time machine that saves a copy first could not "
                         "be asked, so nothing was written"}


def _inside_vault(vault: str, path: str) -> Optional[str]:
    """The resolved path when it is inside the vault and not a link, else None.
    One rule for every file this module writes."""
    try:
        if os.path.islink(path):
            return None
        real = os.path.realpath(path)
    except OSError:
        return None
    root = os.path.realpath(vault)
    if jarvis_notes is None or not jarvis_notes._inside(root, real):
        return None
    return real


def _vault_path(vault: str, rel: str) -> Optional[str]:
    rel = str(rel or "").replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return None
    return _inside_vault(vault, os.path.join(vault, *rel.split("/")))


def _yaml_tag(tag: str) -> str:
    tag = str(tag or "").strip()
    if not tag:
        return ""
    if any(ch in tag for ch in ',[]{}:#"'):
        return json.dumps(tag, ensure_ascii=False)
    return tag


def _with_frontmatter(text: str, tags_after: list, up_link: str) -> str:
    """The note's text with `tags` merged and `up:` added.

    The owner's other frontmatter lines are kept EXACTLY as written (comments,
    order and all), and their own tag list keeps its order; only the `tags:`
    block and an existing `up:` line are replaced. This is a preview-consistent,
    deterministic rewrite - the apply slice writes exactly the tags the plan
    showed (`tags_after`) and the `up:` link it showed."""
    lines = str(text or "").splitlines()
    block: list = []
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                block = lines[1:i]
                body_start = i + 1
                break
    kept: list = []
    skipping_tags = False
    for line in block:
        stripped = line.strip()
        if re.match(r"^tags\s*:", stripped):
            skipping_tags = True
            continue
        if skipping_tags:
            if stripped.startswith("- "):
                continue
            skipping_tags = False
        if re.match(r"^up\s*:", stripped):
            continue
        kept.append(line)
    tag_text = ", ".join(t for t in (_yaml_tag(x) for x in tags_after) if t)
    if tag_text:
        kept.append(f"tags: [{tag_text}]")
    if up_link:
        kept.append(f"up: \"{up_link}\"")
    head = ["---"] + kept + ["---"]
    rest = lines[body_start:] if block else lines
    out = "\n".join(head + rest)
    return out if out.endswith("\n") else out + "\n"


def _rewrite_link(text: str, old: str, new: str) -> str:
    """Rewrite every wiki-link that points at `old` to point at `new`, keeping
    an alias (`|`) or a heading (`#`) exactly as the note wrote it."""
    pattern = re.compile(r"\[\[([^\]|#]*?/)?(" + re.escape(old) + r")(?=[\]|#])")
    return pattern.sub(lambda m: "[[" + new, str(text or ""))


def _link_rewrites(plan: "Plan") -> list:
    """[(rel_path, old_title, new_title)] for every note whose link text points
    at a note this plan moves. Computed from the plan's own stored link map, so
    the writer rewrites exactly what the plan's move list implies - no second
    scanner and no guess."""
    candidates: dict = {}
    for move in plan.moves:
        if move["from_path"] == move["to_path"]:
            continue
        old_stem = Path(move["from_path"]).stem
        new_stem = Path(move["to_path"]).stem
        candidates.setdefault(old_stem, set()).add(new_stem)
    # A title two notes share has no single answer, so a link to it is left
    # EXACTLY as the owner wrote it: a wrong guess is worse than no rewrite.
    moved = {old: next(iter(new)) for old, new in candidates.items()
             if len(new) == 1 and next(iter(new)) != old}
    if not moved:
        return []
    out = []
    for note in plan.notes:
        if note.kind != "note":
            continue
        for target in note.links:
            stem = target.split("/")[-1]
            if stem in moved:
                out.append((note.rel, stem, moved[stem]))
    return sorted(set(out))


def _plan_actions(plan: "Plan") -> dict:
    """Exactly what the plan promised, as file actions, with the paths they end
    at. `texts` holds the note's original words (read once, only when the
    writer runs, and only after the card is approved)."""
    vault = plan.vault
    moves = {m["from_path"]: m["to_path"] for m in plan.moves
             if m["from_path"] != m["to_path"]}
    rewrites: dict = {}
    for rel, old, new in _link_rewrites(plan):
        rewrites.setdefault(rel, []).append((old, new))
    tag_rows = {row["path"]: row for row in plan.tag_plan}
    actions = []
    for rel in sorted(set(tag_rows) | set(moves) | set(rewrites)):
        src = _vault_path(vault, rel)
        dst_rel = moves.get(rel, rel)
        dst = _vault_path(vault, dst_rel)
        if src is None or dst is None:
            return {"ok": False, "refused": True,
                    "why": f"a path in the plan is no longer inside the vault "
                           f"({rel}); nothing was written"}
        try:
            with open(src, "rb") as fh:
                raw = fh.read()
        except OSError:
            return {"ok": False, "refused": True,
                    "why": f"a note the plan names could not be read ({rel}); "
                           f"nothing was written"}
        text = raw.decode("utf-8", "replace")
        for old, new in rewrites.get(rel, []):
            text = _rewrite_link(text, old, new)
        row = tag_rows.get(rel)
        if row is not None:
            text = _with_frontmatter(text, row["tags_after"], row["up"])
        actions.append({"rel": rel, "dst_rel": dst_rel, "src": src, "dst": dst,
                        "data": text.encode("utf-8"), "original": raw,
                        "kind": "move" if dst_rel != rel else "modify"})
    creates = []
    for moc in plan.mocs:
        target = _vault_path(vault, moc["name"])
        if target is None:
            return {"ok": False, "refused": True,
                    "why": "a Map-of-Content name left the vault; nothing was written"}
        creates.append({"rel": moc["name"], "dst": target,
                        "data": moc["body"].encode("utf-8"), "kind": "create"})
    if plan.home:
        target = _vault_path(vault, plan.home["name"])
        if target is None:
            return {"ok": False, "refused": True,
                    "why": "the Vault Home name left the vault; nothing was written"}
        creates.append({"rel": plan.home["name"], "dst": target,
                        "data": plan.home["body"].encode("utf-8"),
                        "kind": "create"})
    return {"ok": True, "actions": actions, "creates": creates,
            "moves": len(moves), "rewrites": sum(len(v) for v in rewrites.values())}


def _write_bytes_atomic(path: str, data: bytes) -> None:
    """One atomic write: a `.tmp` beside the target, then `os.replace`."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _backup_dir(plan_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(plan_id or ""))[:80] or "plan"
    path = _config_dir() / BACKUP_ROOT / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_backup(bdir: Path, files: list) -> list:
    """Copy every original into the batch's own folder and answer the manifest
    rows: {rel, sha256, copy, dst_rel, size}. Pure file copying - nothing in
    the vault changes here."""
    out = []
    folder = bdir / "files"
    folder.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(files):
        name = f"{i:04d}.bin"
        target = folder / name
        _write_bytes_atomic(str(target), item["original"])
        out.append({"rel": item["rel"], "dst_rel": item["dst_rel"],
                    "sha256": _sha_bytes(item["original"]),
                    "copy": f"files/{name}", "size": len(item["original"])})
    return out


def record_card_detail(plan: "Plan", actions: dict) -> dict:
    return {"text": ORGANIZE_CARD.format(
                name=Path(plan.vault).name, scheme_words=_scheme_words(plan.scheme),
                files=len(actions["actions"]) + len(actions["creates"]),
                notes=len(actions["actions"]), moves=actions["moves"],
                creates=len(actions["creates"]), digest=plan.digest),
            "vault_name": Path(plan.vault).name, "scheme": plan.scheme,
            "files": len(actions["actions"]) + len(actions["creates"]),
            "moves": actions["moves"], "creates": len(actions["creates"]),
            "undo": True, "deletes": False, "leaves_this_pc": False}


def _verdict_ok(verdict, tier_of: Callable[[str], str]) -> tuple:
    """(allowed, reason). Only an outcome of exactly "approved" AT tier ask is
    a person saying yes; a missing gate, a lower tier or any other outcome
    writes nothing."""
    vtier = getattr(verdict, "tier", "unknown")
    allowed = getattr(verdict, "allowed", False) is True
    outcome = getattr(verdict, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(GATE_ACTION) != "ask":
        return False, f"the gate answered at tier {vtier!r}, which is not a person saying yes"
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return False, f"the card was {outcome}, so nothing changed"
        return False, str(getattr(verdict, "reason", "the card was refused, so nothing changed"))
    return True, ""


def _refresh_documents_index(vault: str) -> str:
    """Best effort: if the vault is one of the folders the owner already let
    Jarvis read, ask `jarvis_documents.py` to re-index it (`the_index().
    reconcile`). It is NEVER required for the organize itself: a vault not on
    that list is simply not indexed, and says so."""
    try:
        import jarvis_documents as documents
    except Exception:                                     # noqa: BLE001
        return "unavailable"
    try:
        if documents.allowed_path(vault) is None:
            return "not_listed"
        documents.the_index().reconcile([str(vault)])
        return "refreshed"
    except Exception as exc:                              # noqa: BLE001
        return f"failed ({type(exc).__name__})"


def _card_refusal(words: str, **extra) -> dict:
    out = {"ok": False, "refused": True, "why": words, "words": words}
    out.update(extra)
    return out


def apply_plan(plan_id, digest, *, gate: Optional[Callable] = None,
               tier_of: Optional[Callable[[str], str]] = None) -> dict:
    """Do exactly what the plan previewed: ONE card, snapshots, one receipt.

    The plan must still be in memory (`plan_id`) and its `digest` must still
    match a FRESH plan of the same vault - a vault edited after the preview is
    refused as stale rather than acted on. Nothing is written before the card
    is approved and every snapshot is saved.
    """
    plan_id = str(plan_id or "").strip()
    digest = str(digest or "").strip().lower()
    if not plan_id or not digest:
        return _card_refusal("the writer needs the plan's plan_id and digest - "
                             "ask for a plan first")
    plan = get_plan(plan_id)
    if plan is None:
        return _card_refusal("that plan is not in memory any more - a backend "
                             "restart forgets plans; make a new plan and use "
                             "its plan_id")
    if digest != plan.digest:
        return _card_refusal("that digest is not this plan's - refusing rather "
                             "than acting on a stale plan")
    if not _APPLY_LOCK.acquire(blocking=False):
        return _card_refusal("another organize is already running on this PC")
    try:
        # The writer reads note text for real, so the turn is private BEFORE
        # the first note is opened (the freshness check below reads them).
        _latch_taint()
        fresh = plan_vault_organization(plan.vault, scheme=plan.scheme,
                                        max_clusters=plan.max_clusters,
                                        archive_empty_stubs=plan.archive_stubs)
        if fresh.get("ok") is not True:
            return _card_refusal(
                f"the vault could not be re-read before writing: "
                f"{fresh.get('error') or fresh.get('why') or 'unknown reason'}")
        if fresh.get("digest") != plan.digest:
            return _card_refusal(
                "the vault changed since that plan was made, so the plan is "
                "stale - make a new plan and look at it before writing",
                stale=True)
        actions = _plan_actions(plan)
        if actions.get("ok") is not True:
            return _card_refusal(str(actions.get("why") or "the plan's paths "
                                                      "are no longer usable"))
        existing = len(actions["actions"]) + sum(
            1 for c in actions["creates"] if os.path.exists(c["dst"]))
        if existing > MAX_RECEIPT_FILES:
            return _card_refusal(
                f"this one batch would touch {existing:,} existing files, and "
                f"the organizer stops at {MAX_RECEIPT_FILES:,} for one receipt - "
                f"organize a smaller vault or folder first")
        detail = record_card_detail(plan, actions)
        tier_of = tier_of or _tier
        try:
            verdict = (gate or _gate)(GATE_ACTION, detail, detail["text"])
        except Exception as exc:                          # noqa: BLE001
            return _card_refusal(f"the approval card could not be shown "
                                 f"({type(exc).__name__}), so nothing changed")
        allowed, why = _verdict_ok(verdict, tier_of)
        if not allowed:
            return _card_refusal(why, gated=True)
        # ---- snapshots: every existing file about to change, move or be
        # replaced. One failure refuses the WHOLE batch, before any write.
        snap_rows = []
        to_snapshot = [dict(a) for a in actions["actions"]]
        replaced = []
        for item in actions["creates"]:
            if os.path.exists(item["dst"]):
                try:
                    with open(item["dst"], "rb") as fh:
                        original = fh.read()
                except OSError:
                    return _card_refusal(
                        f"an existing note this plan would replace could not be "
                        f"read ({item['rel']}), so nothing was written")
                row = {"rel": item["rel"], "dst_rel": item["rel"],
                       "src": item["dst"], "original": original,
                       "data": item["data"], "kind": "replace"}
                to_snapshot.append(row)
                replaced.append(row)
        for item in sorted(to_snapshot, key=lambda a: a["rel"]):
            snap = _snapshot_before_write(item["src"], plan.vault)
            if snap.get("ok") is not True:
                return _card_refusal(
                    f"the copy of {item['rel']} could not be saved first "
                    f"({snap.get('error') or 'the guardian refused'}), so "
                    f"nothing was written", snapshots_failed=True)
            snap_rows.append({"rel": item["rel"], "dst_rel": item["dst_rel"],
                              "before_sha256": snap.get("before_sha256", ""),
                              "snapshot_id": snap.get("snapshot_id", ""),
                              "guardian_receipt": snap.get("receipt_id", "")})
        # ---- our own exact-bytes copy for ONE Undo, then ONE receipt BEFORE
        bdir = _backup_dir(plan.plan_id)
        backup_rows = _write_backup(bdir, actions["actions"] + replaced)
        created = [c["rel"] for c in actions["creates"]
                   if not any(r["rel"] == c["rel"] for r in replaced)]
        moved_to = {a["dst_rel"]: a["rel"] for a in actions["actions"]
                    if a["kind"] == "move"}
        created_dirs = sorted({str(Path(a["dst_rel"]).parent.as_posix())
                               for a in actions["actions"] if a["kind"] == "move"}
                              | {str(Path(c["rel"]).parent.as_posix())
                                 for c in actions["creates"]})
        manifest = {"plan_id": plan.plan_id, "vault": plan.vault,
                    "scheme": plan.scheme, "files": backup_rows,
                    "snapshots": snap_rows, "created": created,
                    "moved_to": moved_to, "created_dirs": created_dirs}
        summary = (f"organized the Obsidian vault \"{Path(plan.vault).name}\" "
                   f"({plan.scheme}): {len(actions['actions'])} note(s), "
                   f"{actions['moves']} moved, {len(actions['creates'])} "
                   f"note(s) created, nothing deleted")
        before = {"plan_id": plan.plan_id, "files": len(backup_rows)}
        after = {"changed": len(actions["actions"]),
                 "moved": actions["moves"], "created": len(created)}
        try:
            receipts = _receipts()
        except Exception:                                 # noqa: BLE001
            return _card_refusal(
                "the receipt store is not beside this module, so no Undo could "
                "be offered - nothing was written")
        rid = receipts.record(
            RECEIPT_TOOL, summary, before=before, after=after,
            undo=lambda: _undo_from_backup(str(bdir)))
        if not rid:
            return _card_refusal(
                "the batch receipt could not be written, so nothing was "
                "written")
        manifest["receipt_id"] = rid
        _write_bytes_atomic(str(bdir / "manifest.json"),
                            json.dumps(manifest, indent=1).encode("utf-8"))
        # ---- the writes, and only the writes the plan promised
        changed = moved = 0
        writes = {}
        try:
            for item in actions["actions"]:
                writes[item["rel"]] = item["data"]
            for item in actions["actions"]:
                if item["kind"] == "move":
                    dest_dir = os.path.dirname(item["dst"])
                    if dest_dir and not os.path.isdir(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)
            for item in actions["actions"]:
                if item["kind"] == "move":
                    os.replace(item["src"], item["dst"])
                    moved += 1
            for item in actions["actions"]:
                _write_bytes_atomic(item["dst"], writes[item["rel"]])
                changed += 1
            for item in actions["creates"]:
                dest_dir = os.path.dirname(item["dst"])
                if dest_dir and not os.path.isdir(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                _write_bytes_atomic(item["dst"], item["data"])
                changed += 1
        except Exception as exc:                          # noqa: BLE001
            _audit("vault_organizer.apply.partial", {
                "changed": changed, "receipt": rid,
                "error": type(exc).__name__})
            return {"ok": False, "partial": True, "plan_id": plan.plan_id,
                    "receipt_id": rid, "backup": str(bdir),
                    "changed": changed, "moved": moved,
                    "why": f"the organize stopped part-way ({type(exc).__name__}): "
                           f"{changed} file(s) were written, {moved} moved. "
                           f"A receipt was saved first, so Undo puts back what "
                           f"changed.",
                    "undo": {"receipt_id": rid, "route": "/api/receipts/undo"}}
        index = _refresh_documents_index(plan.vault)
        _audit("vault_organizer.apply", {
            "scheme": plan.scheme, "changed": changed, "moved": moved,
            "created": len(actions["creates"]),
            "snapshots": len(snap_rows), "index": index})
        s = plan.summary()
        said = (f"Organized \"{Path(plan.vault).name}\": {changed:,} file(s) "
                f"written, {moved:,} note(s) moved, {len(actions['creates']):,} "
                f"note(s) created ({s['mocs_to_create']:,} Map of Content and "
                f"the Vault Home). Nothing was deleted. One click of Undo "
                f"puts the whole vault back.")
        return {"ok": True, "applied": True, "plan_id": plan.plan_id,
                "receipt_id": rid, "backup": str(bdir),
                "changed": changed, "moved": moved,
                "created": len(actions["creates"]),
                "snapshots": len(snap_rows),
                "links_rewritten": actions["rewrites"],
                "index_refresh": index, "said": said,
                "undo": {"receipt_id": rid, "route": "/api/receipts/undo"}}
    finally:
        _APPLY_LOCK.release()


def _undo_from_backup(bdir: str) -> dict:
    """Put the whole batch back from its own copy.

    Restores every original byte at its original path (moved files included),
    then removes ONLY the files this batch created - never a note that was
    already in the vault - and removes only the folders it created, only when
    they are empty. Never raises; answers plain words."""
    try:
        folder = Path(bdir)
        raw = (folder / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(raw)
    except Exception as exc:                              # noqa: BLE001
        return {"ok": False, "error": f"the batch copy could not be read "
                                      f"({type(exc).__name__})",
                "words": "the copy this organize saved first could not be read, "
                         "so nothing was put back"}
    vault = str(manifest.get("vault") or "")
    if not vault or not os.path.isdir(vault):
        return {"ok": False, "error": "the vault folder is not there any more",
                "words": "the vault folder is not there any more, so nothing "
                         "was put back"}
    restored = removed = 0
    problems = []
    for row in manifest.get("files") or []:
        rel = str(row.get("rel") or "")
        dst_rel = str(row.get("dst_rel") or rel)
        target = _vault_path(vault, rel)
        copy = folder / str(row.get("copy") or "")
        if target is None or not copy.is_file():
            problems.append(rel)
            continue
        try:
            data = copy.read_bytes()
            if _sha_bytes(data) != row.get("sha256"):
                problems.append(rel)
                continue
            if dst_rel and dst_rel != rel:
                moved = _vault_path(vault, dst_rel)
                try:
                    if moved and os.path.isfile(moved):
                        os.unlink(moved)             # created by this batch's move
                except OSError:
                    pass
            _write_bytes_atomic(target, data)
            restored += 1
        except Exception:                                 # noqa: BLE001
            problems.append(rel)
    for rel in manifest.get("created") or []:
        target = _vault_path(vault, str(rel))
        if target and os.path.isfile(target):
            try:
                os.unlink(target)
                removed += 1
            except OSError:
                problems.append(str(rel))
    roots_to_check = []
    for rel_dir in manifest.get("created_dirs") or []:
        parts = [str(p) for p in Path(str(rel_dir)).parts if p not in ("", ".")]
        for i in range(1, len(parts) + 1):
            roots_to_check.append("/".join(parts[:i]))
    for rel_dir in sorted(set(roots_to_check),
                          key=lambda p: (len(Path(p).parts), p), reverse=True):
        target = _vault_path(vault, rel_dir)
        if target and os.path.isdir(target):
            try:
                if not os.listdir(target):
                    os.rmdir(target)
            except OSError:
                pass
    _audit("vault_organizer.undo", {"restored": restored, "removed": removed,
                                    "problems": len(problems)})
    if problems:
        return {"ok": False, "restored": restored, "removed": removed,
                "problems": problems[:20],
                "error": f"{len(problems)} file(s) could not be put back",
                "words": f"Put back {restored} file(s) and removed {removed} "
                         f"created note(s); {len(problems)} file(s) need "
                         f"looking at."}
    return {"ok": True, "restored": restored, "removed": removed,
            "words": f"Put back {restored} file(s) and removed {removed} "
                     f"note(s) this organize created."}


#: A new process finds the batch copy by the receipt's own `before` snapshot,
#: so Undo works after a restart too (the in-process callable is faster but is
#: gone by then). Registered once, at import, guarded.
def _restore_from_before(before) -> None:
    """The restorer a NEW process finds by this receipt's tool name. The
    receipt's before snapshot carries no absolute path (the receipt scrubber
    would redact the owner's home folder in it), so the copy is found by
    plan_id under this PC's own settings folder. Raises when it cannot put
    something back, so Undo reports a failure rather than a false success."""
    plan_id = str((before or {}).get("plan_id") or "")
    if not plan_id:
        raise RuntimeError("the receipt does not say which batch to put back")
    out = _undo_from_backup(str(_backup_dir(plan_id)))
    if out.get("ok") is not True:
        raise RuntimeError(str(out.get("error") or out.get("words")
                               or "putting the batch back failed"))


try:
    _receipts().register_restorer(RECEIPT_TOOL, _restore_from_before)
except Exception:                                         # noqa: BLE001
    pass


_ARMED = False


def armed() -> bool:
    return _ARMED


def _pc_only(peer, local) -> bool:
    """Is this request from this PC? FAILS CLOSED, like jarvis_voiceprint's.

    `jarvis_owner_check.from_this_pc` is the project's one answer; when it is
    not beside this module, loopback (and only loopback) is accepted.
    """
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:                                     # noqa: BLE001
        if peer is None:
            return False
        try:
            host = str(peer).strip("[]").lower()
        except Exception:                                 # noqa: BLE001
            return False
        return host in ("127.0.0.1", "::1", "localhost")


def handle_get(route: str, *, peer=None, local=None) -> tuple:
    if route != STATUS_PATH:
        return 404, {"ok": False, "error": "no such route"}
    out = {"ok": True, "title": "Vault organizer",
           "detail": ("Suggests a tidy shape for an Obsidian vault: tags, "
                      "Map-of-Content notes and a Vault Home. The plan is a dry "
                      "run; nothing is changed until a plan is approved."),
           "default_scheme": DEFAULT_SCHEME, "schemes": list(SCHEMES)}
    out.update(switch_status())
    out.update(can_apply=True, apply_action=GATE_ACTION,
               apply_tier=_tier(GATE_ACTION))
    return 200, out


def handle_post(route: str, body, *, peer=None, local=None,
                gate: Optional[Callable] = None,
                tier_of: Optional[Callable[[str], str]] = None,
                spawn: Optional[Callable] = None) -> tuple:
    body = body if isinstance(body, dict) else {}
    if route == SWITCH_PATH:
        return request_enabled(body.get("enabled"), gate=gate, tier_of=tier_of,
                               spawn=spawn)
    if route not in (PLAN_PATH, ORGANIZE_PATH):
        return 404, {"ok": False, "error": "no such route"}
    if not _pc_only(peer, local):
        return 403, {"ok": False, "error": "not_this_pc",
                     "why": "organizing a vault is for this PC only - the plan "
                            "reads the notes on this PC and answers on its screen"}
    if not enabled():
        return 200, {"ok": False, "enabled": False, "why": _OFF_WHY}
    if route == ORGANIZE_PATH:
        if not str(body.get("plan_id") or "").strip() \
                or not str(body.get("digest") or "").strip():
            return 400, {"ok": False,
                         "error": 'need {"plan_id": ..., "digest": ...} from a '
                                  'plan you looked at'}
        return 200, apply_plan(body.get("plan_id"), body.get("digest"))
    scheme = str(body.get("scheme") or DEFAULT_SCHEME)
    try:
        clusters = int(body.get("max_clusters") or MAX_CLUSTERS)
    except (TypeError, ValueError):
        clusters = MAX_CLUSTERS
    out = plan_vault_organization(body.get("vault"), scheme=scheme,
                                  max_clusters=clusters,
                                  archive_empty_stubs=body.get("archive_empty_stubs") is True)
    out.setdefault("enabled", True)
    return 200, out


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the server's GET/POST so the routes above are answered here."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_vault_organizer", False):
        _ARMED = True
        return "  vault      Obsidian vault organizer (already on)"

    def _allowed(self) -> bool:
        try:
            return bool(origin_ok(self)) and bool(token_ok(self))
        except Exception:                                 # noqa: BLE001
            return False

    def _peer_local(self) -> tuple:
        peer = local = None
        try:
            peer = self.client_address[0]
        except Exception:                                 # noqa: BLE001
            pass
        try:
            local = self.connection.getsockname()[0]
        except Exception:                                 # noqa: BLE001
            pass
        return peer, local

    def do_GET(self):
        route = str(getattr(self, "path", "")).split("?")[0]
        if route != STATUS_PATH:
            return get0(self)
        if not _allowed(self):
            return _send(self, 403, {"ok": False, "reason": "not allowed"})
        peer, local = _peer_local(self)
        code, out = handle_get(route, peer=peer, local=local)
        return _send(self, code, out)

    def do_POST(self):
        route = str(getattr(self, "path", "")).split("?")[0]
        if route not in PATHS:
            return post0(self)
        if not _allowed(self):
            return _send(self, 403, {"ok": False, "reason": "not allowed"})
        try:
            body = read_body(self)
            if isinstance(body, bytes):
                body = json.loads(body.decode("utf-8") or "{}")
        except Exception:                                 # noqa: BLE001
            body = {}
        peer, local = _peer_local(self)
        code, out = handle_post(route, body, peer=peer, local=local)
        return _send(self, code, out)

    do_GET._jarvis_vault_organizer = True       # type: ignore[attr-defined]
    do_POST._jarvis_vault_organizer = True      # type: ignore[attr-defined]
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return ("  vault      Obsidian vault organizer: read-only plans, "
            "one-card organize with Undo")


def _send(self, code: int, payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    try:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    except Exception:                                     # noqa: BLE001
        pass


#: `jarvis_notes` is imported at the top, beside the other modules this one
#: borrows from, so a checkout with the organizer but without the notes search
#: still imports and the plan refuses in words.

if __name__ == "__main__":
    print(f"  {handle_get(STATUS_PATH)[1].get('title')}")
