"""jarvis_projects.py - Projects, steps 1 and 2 (the owner's decision of
2026-09-28, CLAUDE.md "Projects, like Claude's Projects and more"; the
design is docs/PROJECTS-DESIGN.md, and its "Build notes" say what this
first piece is and is not).

NEW MODULE, shipped whole (projects.patch adds the routes).

WHAT IT IS FOR, IN PLAIN WORDS
A project is one place for one thing the owner is working on: an app
("Jarvis Desktop", a coding project) or "run a half marathon" (a life
project). This module keeps each project's name, kind, instructions ("how
Jarvis should work on this", in the owner's words), a few pinned project
notes, its one folder (coding only), a Shareable switch (off by default),
its work list (a named list on the one scheduler), the ids of the goals it
is linked to - and its benchmarks: named measurements with dated results,
"better or worse than last time", and the points for a chart.

WHAT IS BUILT HERE, AND WHAT IS NOT (build steps 1 and 2 only)
  * Built: the projects themselves, life benchmarks (logging a number,
    results over time, better/worse, sensitive marking), the quick command
    "log 5 km run" / "I ran 5 km" (jarvis_quick.py calls quick_match() and
    quick_log() below), and coding benchmarks AS WORDS ONLY: the command's
    text is kept, marked "not runnable yet". Nothing in this file runs a
    command, opens a socket, calls a model or writes a file outside
    projects.db.
  * APPS (2026-09-29, docs/APPS-IN-PROJECTS-DESIGN.md): a coding project
    may be a Jarvis-built app - `app` names its folder under
    `<settings folder>/apps/` (jarvis_app_workspace.py), never together with
    a `folder`. Its tasks, the merge card and the routes are in
    jarvis_apps.py; this file keeps the link (the `app` column), makes or
    adopts the folder when the project is made, and never deletes it.
  * Not built: running benchmarks (the fence, build step 6), Jarvis
    changing code (`project_edit`, build steps 5 and 7 - after the 12 GB
    card is installed and measured, the owner's answer of 2026-09-28), the
    project chat context and project-labelled facts (step 4), both apps'
    screens (step 3), and anything the Shareable switch would one day let
    go out (it is only a switch here; nothing is ever sent).
  * GOALS: jarvis_goals.py is on main now, but the link is not built yet
    (cohesiveness audit, 2026-09-29): a project lists goal ids (`goals`) on
    THIS side, and no screen sets or shows them. The goals.db `project`
    column, `GET /api/goals?project=<id>`, and a goal step's measure
    ({"bench": ..., "target": ...}) are still to come - the design's "one
    extra field, no second goals system" is unchanged. Until then a goal id
    here is not checked against goals.db.
  * CHATS: the chat-history `project` column waits for step 4 - nothing
    can set it until /api/chat carries a project id.

WHO MAY DO WHAT, AND WHICH NEED A CARD (ARCHITECTURE section 3)
  * Creating, editing and deleting a project, its notes and its
    benchmarks, and logging a number: NO card. The owner is writing down
    their own things, like a to-do item (docs/PROJECTS-DESIGN.md section 3,
    "Life projects"). Only from the apps (the owner's tap) or, for logging,
    from the owner's own typed or spoken words through jarvis_quick.py -
    which already refuses pasted, shared and untagged messages.
  * A project's folder: it must ALREADY be on "Folders Jarvis may look in"
    (jarvis_documents.folders()), or inside one of them. Adding a folder to
    that list stays where it is - PC only, one change_own_config card
    (jarvis_documents.request_add); there is no second folder list.
    Choosing a project's folder, and writing or changing a coding
    benchmark's command, are PC-only (jarvis_owner_check.from_this_pc,
    the same check "Folders Jarvis may look in" uses): folders already are,
    and a command's words decide what would run on the PC
    (docs/PROJECTS-DESIGN.md section 6; ARCHITECTURE section 8).
  * The Shareable switch: OFF by default. Turning it ON is ONE approval
    card (change_own_config, the same action "Folders Jarvis may look in"
    uses, so jarvis_gate needs no new line); turning it OFF is instant -
    the shape of every switch that loosens a rule (CLAUDE.md, 2026-09-24).
    Even on, nothing here sends anything; each future send gets its own
    card showing the words, and never a sensitive number.
  * Sensitive numbers: a benchmark about health or money is marked
    sensitive, from its name and unit (jarvis_sensitive.topic() plus a
    short benchmark word list below, because topic() alone does not see
    "weight" or "resting heart rate"), or because the owner marked it. Its
    numbers are flagged `keep_on_screen`: never read aloud (the quick
    command's answer is `private`, so the apps keep it on screen), and
    never to be sent anywhere. The owner can mark more, and take their own
    mark off at once. A mark Jarvis made by itself from the name can come
    off too, but only with ONE card first (change_own_config, like
    Shareable ON) - because afterwards the numbers may be read aloud (the
    owner's answer of 2026-09-28: `jarvis_sensitive` reads "5k" as money).
    Renaming the benchmark or changing its unit checks the name again.

WHAT IS KEPT, AND WHERE
`projects.db` in the Jarvis settings folder, beside schedule.db and
memory.db (JARVIS_PROJECTS_DB overrides it, for the tests). The audit log
gets ids and counts only - never a name, an instruction, a note or a
number.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

MAX_PROJECTS = 30
MAX_NAME = 60
#: "How Jarvis should work on this" - the design's ~1,500 characters. Every
#: part of a project chat's SYSTEM line has a hard limit (8K tokens on the
#: 8 GB card, docs/PROJECTS-DESIGN.md section 1).
MAX_INSTRUCTIONS = 1500
#: Project notes: the owner's own pinned lines ("the server uses port
#: 8080"), like "Always keep in mind" but per project. Small on purpose.
MAX_NOTES = 10
MAX_NOTE = 200
MAX_GOALS_LINKED = 20
MAX_BENCHMARKS = 12
MAX_BENCH_NAME = 40
MAX_UNIT = 16
MAX_COMMAND = 300
MAX_RESULTS = 5000
CHART_POINTS = 365
CHART_POINTS_MAX = 1000
#: A number bigger than this is a typo, not a measurement.
MAX_ABS_VALUE = 1e12

KINDS = ("coding", "life")
BENCH_KINDS = ("number", "command")
BETTER = ("higher", "lower")

#: The card this module raises: turning Shareable ON, and taking an
#: automatic private mark off a benchmark. The same action "Folders Jarvis
#: may look in" raises, so the gate needs no new line.
CARD_ACTION = "change_own_config"

TITLE = "Projects"
EMPTY = "No projects yet."
NOT_RUNNABLE = ("Running a benchmark's command comes in a later step - nothing runs yet. "
                "The command is kept, word for word.")
PC_ONLY_FOLDER = ("A project's folder is chosen on the PC only, from \"Folders Jarvis may "
                  "look in\".")
PC_ONLY_COMMAND = "A benchmark's command is written on the PC only."
SHARE_WAITING = "Waiting for your yes on the approval card."
KEEP_ON_SCREEN = "Health or money: kept on screen, never read aloud or sent anywhere."

_ID = re.compile(r"[0-9a-f]{32}")
APP_ONLY_WORDS = "This project's files are its app."
APP_CHOSEN_WORDS = "An app is chosen when the project is made."
APP_AND_FOLDER_WORDS = "A project has a folder or an app, not both."


class NoSuchApp(LookupError):
    """An app folder that does not exist (a 404 with its own sentence)."""


class Unavailable(Exception):
    """git is missing or stuck: a 503 with the sentence (nothing typed was wrong)."""


_GOAL_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# --------------------------------------------------------------------------
#   Where, the gate, the clock - replaceable, so the tests open nothing
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def db_path() -> Path:
    env = os.environ.get("JARVIS_PROJECTS_DB")
    return Path(env) if env else _config_dir() / "projects.db"


def _audit(event: str, detail: dict) -> None:
    # Ids and counts only. Never a name, an instruction, a note or a number.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-projects-card", daemon=True).start()


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        # Cannot tell: not this PC, so a PC-only change is refused (fail
        # closed), exactly as jarvis_documents._from_this_pc does.
        return False


def _allowed_folders() -> list:
    """"Folders Jarvis may look in" - the ONE list (jarvis_documents.py).
    Without that module, none: a project folder cannot be chosen."""
    try:
        import jarvis_documents
        return list(jarvis_documents.folders())
    except Exception:
        return []


def _protected(path: str) -> bool:
    try:
        import jarvis_documents
        return bool(jarvis_documents.protected(path))
    except Exception:
        return True


# --------------------------------------------------------------------------
#   Checking what the owner typed
# --------------------------------------------------------------------------


def _text(value, limit: int, what: str, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{what} must be text")
    t = " ".join(value.split()) if "\n" not in value else value.strip()
    if required and not t:
        raise ValueError(f"{what} cannot be empty")
    if len(t) > limit:
        raise ValueError(f"{what} is {len(t)} characters - at most {limit}")
    return t


def _one_line(value, limit: int, what: str, *, required: bool = False) -> str:
    if value is not None and isinstance(value, str) and ("\n" in value or "\r" in value):
        raise ValueError(f"{what} is one line")
    return _text(value, limit, what, required=required)


def clean_notes(notes) -> list:
    if notes is None:
        return []
    if not isinstance(notes, list):
        raise ValueError("notes are a list of short lines")
    out = []
    for n in notes:
        line = _one_line(n, MAX_NOTE, "a project note")
        if line:
            out.append(line)
    if len(out) > MAX_NOTES:
        raise ValueError(f"a project keeps at most {MAX_NOTES} notes")
    return out


def clean_goals(goals) -> list:
    """Goal ids from jarvis_goals.py. Kept as given; not yet checked against
    goals.db (the project <-> goal link is not built; see the module note)."""
    if goals is None:
        return []
    if not isinstance(goals, list):
        raise ValueError("goals are a list of goal ids")
    out = []
    for g in goals:
        if not isinstance(g, str) or not _GOAL_ID.fullmatch(g):
            raise ValueError("a goal id is 1 to 64 letters, digits, - or _")
        if g not in out:
            out.append(g)
    if len(out) > MAX_GOALS_LINKED:
        raise ValueError(f"a project links at most {MAX_GOALS_LINKED} goals")
    return out


def clean_work_list(name) -> Optional[str]:
    """A named list on the one scheduler (jarvis_schedule.list_key), or None
    for no work list. The to-do list itself cannot be a project's list."""
    if name is None or (isinstance(name, str) and not name.strip()):
        return None
    if not isinstance(name, str):
        raise ValueError("a work list's name is text")
    import jarvis_schedule
    key = jarvis_schedule.list_key(name)
    if key is None:
        raise ValueError("the to-do list itself cannot be a project's work list - "
                         "give it a name, like \"garden\"")
    return key


def _default_work_list(name: str) -> Optional[str]:
    try:
        return clean_work_list(name)
    except Exception:
        return None


def _real(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def _inside(root: str, path: str) -> bool:
    try:
        return (os.path.commonpath([os.path.normcase(root), os.path.normcase(path)])
                == os.path.normcase(root))
    except ValueError:
        return False


def check_folder(path, allowed: Optional[list] = None) -> str:
    """The real place of `path` when it is one of "Folders Jarvis may look
    in", or a folder inside one of them. ValueError, in words, otherwise."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("choose a folder from \"Folders Jarvis may look in\"")
    real = _real(path.strip())
    listed = _allowed_folders() if allowed is None else list(allowed)
    if not any(_inside(_real(f), real) for f in listed):
        raise ValueError("that folder is not on \"Folders Jarvis may look in\" - add it "
                         "there first, on the PC (Settings)")
    if not os.path.isdir(real):
        raise ValueError("that folder does not exist on this PC")
    if _protected(real):
        raise ValueError("that folder is one Jarvis never looks in")
    return real


def _value(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError("a number, like 5 or 72.5")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError("a number, like 5 or 72.5")
    if not math.isfinite(f) or abs(f) > MAX_ABS_VALUE:
        raise ValueError("that number is too big to be a measurement")
    return f


def _opt_value(v) -> Optional[float]:
    return None if v is None else _value(v)


# --------------------------------------------------------------------------
#   Sensitive: health or money
# --------------------------------------------------------------------------

#: What jarvis_sensitive.topic() does not see in a benchmark's short name
#: (checked 2026-09-28: "weight", "body weight", "resting heart rate",
#: "calories", "monthly spending" all came back ""). Whole words only.
_HEALTH_WORDS = re.compile(
    r"(?<![a-z])(?:weight|weigh|weighed|bmi|body ?fat|fat ?%|waist|heart ?rate|pulse|hrv|bpm"
    r"|blood|glucose|sugar|cholesterol|calories|calorie|kcal|sleep|slept|mood|anxiety|pain"
    r"|medication|meds|dose|insulin|symptoms?|alcohol|drinks|cigarettes|smoking|mmhg"
    r"|mg/dl|mmol|period|fertility|pregnan\w*)(?![a-z])")
_MONEY_WORDS = re.compile(
    r"(?<![a-z])(?:money|savings?|saved|spend|spending|spent|budget|income|salary|wages?|pay"
    r"|debts?|loans?|balance|net ?worth|rent|bills|expenses|investments?|portfolio|pension"
    r"|dollars?|usd|gbp|eur|euros?|quid|bucks|pounds sterling)(?![a-z])|[$£€]")


def auto_sensitive(name: str, unit: str = "") -> str:
    """"health", "money", another topic jarvis_sensitive names, or "" - from
    the benchmark's own name and unit, never the numbers. No model."""
    words = f"{name or ''} {unit or ''}".strip()
    if not words:
        return ""
    low = words.lower()
    if _HEALTH_WORDS.search(low):
        return "health"
    if _MONEY_WORDS.search(low):
        return "money"
    try:
        import jarvis_sensitive
        t = jarvis_sensitive.topic(words)
    except Exception:
        t = ""
    return t or ""


def marks(name: str, unit: str, owner, cleared) -> dict:
    """Both private marks of one benchmark, worked out the same way
    everywhere (the view, the quick command): {"auto": the topic the name
    looks like, "auto_holds": that topic unless the owner took it off with
    a card, "owner": the owner's own mark, "sensitive": either holds}.
    `cleared` is the topic the owner's yes took off; a different topic
    (after a rename) holds again."""
    auto = auto_sensitive(name, unit)
    holds = auto if auto and (cleared or "") != auto else ""
    own = bool(owner)
    return {"auto": auto, "auto_holds": holds, "owner": own,
            "sensitive": bool(holds) or own}


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '[]',
    folder TEXT,
    shareable INTEGER NOT NULL DEFAULT 0,
    work_list TEXT,
    goals TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL,
    changed REAL NOT NULL,
    app TEXT
);
CREATE TABLE IF NOT EXISTS benchmarks (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    better TEXT,
    target REAL,
    command TEXT,
    owner_sensitive INTEGER NOT NULL DEFAULT 0,
    auto_cleared TEXT,
    created REAL NOT NULL,
    changed REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    bench TEXT NOT NULL,
    value REAL NOT NULL,
    at REAL NOT NULL,
    source TEXT NOT NULL,
    logged REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS results_by_bench ON results (bench, at);
CREATE INDEX IF NOT EXISTS bench_by_project ON benchmarks (project);
"""


def _new_id() -> str:
    return uuid.uuid4().hex


def _folder_name(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] or path


def _num_words(v: float) -> str:
    """72.5 -> "72.5", 5.0 -> "5", 10000 -> "10000"."""
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _with_unit(v: float, unit: str) -> str:
    n = _num_words(v)
    if not unit:
        return n
    if unit in ("$", "£", "€"):
        return f"{unit}{n}"
    if unit == "%":
        return f"{n}%"
    return f"{n} {unit}"


def _workspace():
    import jarvis_app_workspace
    return jarvis_app_workspace


def _app_view(app: str, *, full: bool) -> dict:
    """The `app` object of a project view (jarvis_apps builds it: the list
    gets the short form, one project the whole)."""
    try:
        import jarvis_apps
        return jarvis_apps.full(app) if full else jarvis_apps.summary(app)
    except Exception:
        return {"name": app, "type": "", "tasks": 0, "merge_waiting": False}


class Projects:
    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time):
        self.path = Path(path) if path is not None else db_path()
        self.clock = clock
        self._lock = threading.RLock()
        self._ready = False

    # ---- plumbing -----------------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.path), timeout=30)
        c.row_factory = sqlite3.Row
        if not self._ready:
            c.executescript(_SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(benchmarks)").fetchall()}
            if "auto_cleared" not in cols:
                # A projects.db from build steps 1 and 2, before an automatic
                # mark could be taken off.
                c.execute("ALTER TABLE benchmarks ADD COLUMN auto_cleared TEXT")
            pcols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
            if "app" not in pcols:
                # A projects.db from before apps joined Projects (2026-09-29).
                c.execute("ALTER TABLE projects ADD COLUMN app TEXT")
            # One project per app folder. After the column exists, so an old
            # file gets the column first.
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS projects_by_app ON projects (app) "
                      "WHERE app IS NOT NULL")
            c.commit()
            self._ready = True
        return c

    def exists(self) -> bool:
        """Is there a projects.db at all? The quick command asks this first,
        so an ordinary chat message never creates one."""
        return self.path.is_file()

    def _project_row(self, c, pid: str):
        if not isinstance(pid, str) or not _ID.fullmatch(pid):
            raise KeyError(pid)
        r = c.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if r is None:
            raise KeyError(pid)
        return r

    def _bench_row(self, c, pid: str, bid: str):
        if not isinstance(bid, str) or not _ID.fullmatch(bid):
            raise KeyError(bid)
        r = c.execute("SELECT * FROM benchmarks WHERE id = ? AND project = ?",
                      (bid, pid)).fetchone()
        if r is None:
            raise KeyError(bid)
        return r

    # ---- views --------------------------------------------------------------------

    def _bench_view(self, c, b, *, points: int = 0) -> dict:
        m = marks(b["name"], b["unit"], b["owner_sensitive"], b["auto_cleared"])
        auto, owner, sensitive = m["auto_holds"], m["owner"], m["sensitive"]
        rows = c.execute("SELECT id, value, at, source FROM results WHERE bench = ? "
                         "ORDER BY at DESC, logged DESC LIMIT 2", (b["id"],)).fetchall()
        count = c.execute("SELECT COUNT(*) FROM results WHERE bench = ?",
                          (b["id"],)).fetchone()[0]
        latest = rows[0] if rows else None
        previous = rows[1] if len(rows) > 1 else None
        v = {
            "id": b["id"], "name": b["name"], "kind": b["kind"], "unit": b["unit"],
            "better": b["better"], "target": b["target"],
            "sensitive": sensitive,
            "sensitive_why": (auto or ("you marked it" if owner else "")),
            "marked_by_you": owner,
            # The automatic mark: what the name looks like ("money"), and
            # whether the owner took it off with a card.
            "mark_auto": m["auto"],
            "mark_auto_removed": bool(m["auto"]) and not auto,
            # How the private mark comes off: "instant" (only the owner's
            # own mark holds it), "card" (Jarvis's own mark holds it), or
            # "" (not marked).
            "unmark": ("card" if auto else "instant" if owner else ""),
            "keep_on_screen": sensitive,
            "keep_on_screen_words": KEEP_ON_SCREEN if sensitive else "",
            "results": int(count),
            "latest": ({"id": latest["id"], "value": latest["value"], "at": latest["at"]}
                       if latest else None),
            "change": compare(latest["value"] if latest else None,
                              previous["value"] if previous else None,
                              b["better"], target=b["target"]),
            "created": b["created"], "changed": b["changed"],
        }
        with _P_LOCK:
            waiting = _M_STATE["pending"].get(b["id"])
            last = _M_STATE["last"].get(b["id"])
        v["unmark_waiting"] = bool(waiting)
        v["unmark_last"] = dict(last) if last else None
        if b["kind"] == "command":
            v["command"] = b["command"] or ""
            v["runnable"] = False
            v["not_runnable_why"] = NOT_RUNNABLE
        if points:
            pts = c.execute("SELECT id, value, at FROM results WHERE bench = ? "
                            "ORDER BY at DESC, logged DESC LIMIT ?",
                            (b["id"], int(points))).fetchall()
            v["points"] = [{"id": p["id"], "at": p["at"], "value": p["value"]}
                           for p in reversed(pts)]
            v["points_shown"] = len(pts)
        return v

    def _view(self, c, r, *, full: bool = False) -> dict:
        folder = r["folder"]
        folder_ok = None
        if folder:
            try:
                check_folder(folder)
                folder_ok = True
            except ValueError:
                folder_ok = False
        wl = r["work_list"]
        benches = c.execute("SELECT * FROM benchmarks WHERE project = ? ORDER BY created",
                            (r["id"],)).fetchall()
        with _P_LOCK:
            waiting = _P_STATE["pending"].get(r["id"])
            last = _P_STATE["last"].get(r["id"])
        v = {
            "id": r["id"], "name": r["name"], "kind": r["kind"],
            "shareable": bool(r["shareable"]),
            "shareable_waiting": bool(waiting),
            "shareable_waiting_words": SHARE_WAITING if waiting else "",
            "shareable_last": dict(last) if last else None,
            "folder": ({"path": folder, "name": _folder_name(folder),
                        "listed": bool(folder_ok),
                        "said": "" if folder_ok else
                        "This folder is no longer on \"Folders Jarvis may look in\" (or is "
                        "gone), so Jarvis does not look in it."} if folder else None),
            "work_list": ({"name": wl, "title": _list_title(wl)} if wl else None),
            "goals": json.loads(r["goals"] or "[]"),
            "benchmarks": len(benches),
            "created": r["created"], "changed": r["changed"],
            "app": _app_view(r["app"], full=full) if r["app"] else None,
        }
        if full:
            v["instructions"] = r["instructions"]
            v["notes"] = json.loads(r["notes"] or "[]")
            v["benchmark_list"] = [self._bench_view(c, b) for b in benches]
            v["max"] = {"instructions": MAX_INSTRUCTIONS, "notes": MAX_NOTES,
                        "note": MAX_NOTE, "benchmarks": MAX_BENCHMARKS}
        return v

    def unlinked_apps(self) -> list:
        """App folders in Jarvis's apps folder that no project uses: an offer
        inside Projects (adopt one with POST /api/projects {"app": {"adopt":
        ...}}). There is no separate list of apps."""
        try:
            import jarvis_app_workspace as W
            found = W.list_projects()
        except Exception:
            return []
        linked = set()
        if self.exists():
            with self._lock, self._db() as c:
                linked = {r[0] for r in c.execute(
                    "SELECT app FROM projects WHERE app IS NOT NULL").fetchall()}
        return [{"name": a["name"], "type": a["kind"], "title": a["title"]}
                for a in found if a["name"] not in linked]

    def list(self) -> list:
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM projects ORDER BY created").fetchall()
            return [self._view(c, r) for r in rows]

    def get(self, pid: str) -> dict:
        with self._lock, self._db() as c:
            return self._view(c, self._project_row(c, pid), full=True)

    def app_of(self, pid: str) -> dict:
        """{"name": the project's name, "app": its app folder name or None} -
        a light read for jarvis_apps (no git, no benchmarks)."""
        with self._lock, self._db() as c:
            r = self._project_row(c, pid)
            return {"name": r["name"], "app": r["app"]}

    # ---- projects -----------------------------------------------------------------

    def create(self, body: dict, *, here: bool) -> dict:
        if not isinstance(body, dict):
            raise ValueError('need {"name": ..., "kind": "coding" or "life"}')
        kind = body.get("kind")
        if kind not in KINDS:
            raise ValueError('a project is "coding" or "life"')
        app_type, adopt = None, None
        if body.get("app") is not None:
            # An app Jarvis builds: new (`type`) or an existing folder with no
            # project (`adopt`). Coding only, and never with a folder.
            req = body.get("app")
            if not isinstance(req, dict):
                raise ValueError('"app" is {"type": "web"} or {"adopt": "<folder name>"}')
            if kind != "coding":
                raise ValueError("only a coding project can be an app")
            if body.get("folder") not in (None, ""):
                raise ValueError(APP_AND_FOLDER_WORDS)
            if req.get("adopt") is not None:
                adopt = req.get("adopt")
                if not isinstance(adopt, str):
                    raise ValueError("the app to add is named by its folder name")
            else:
                app_type = req.get("type")
                if app_type not in ("web", "android"):
                    raise ValueError('an app is "web" or "android"')
        if adopt is not None and body.get("name") in (None, ""):
            found = {a["name"]: a for a in _workspace().list_projects()}
            name = _one_line((found.get(adopt) or {}).get("title") or adopt, MAX_NAME,
                             "a project's name", required=True)
        else:
            name = _one_line(body.get("name"), MAX_NAME, "a project's name", required=True)
        instructions = _text(body.get("instructions"), MAX_INSTRUCTIONS, "the instructions")
        notes = clean_notes(body.get("notes"))
        goals = clean_goals(body.get("goals"))
        folder = None
        if body.get("folder") not in (None, ""):
            if kind != "coding":
                raise ValueError("a life project has no folder")
            if not here:
                raise PermissionError(PC_ONLY_FOLDER)
            folder = check_folder(body.get("folder"))
        if body.get("shareable") is True:
            raise ValueError("a project starts with Shareable off - turn it on afterwards "
                             "(that asks you with a card)")
        if "work_list" in body:
            work_list = clean_work_list(body.get("work_list"))
        else:
            work_list = _default_work_list(name)
        now = self.clock()
        pid = _new_id()
        with self._lock, self._db() as c:
            n = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if n >= MAX_PROJECTS:
                raise OverflowError(f"there are already {MAX_PROJECTS} projects - delete one "
                                    f"first")
            if c.execute("SELECT 1 FROM projects WHERE lower(name) = lower(?)",
                         (name,)).fetchone():
                raise OverflowError("there is already a project with that name")
            self._list_free(c, work_list, None)
            app, made = None, False
            if adopt is not None:
                app = self._check_adopt(c, adopt)
            elif app_type is not None:
                app = self._make_app(c, name, app_type)
                made = True
            try:
                c.execute("INSERT INTO projects (id, name, kind, instructions, notes, folder, "
                          "shareable, work_list, goals, created, changed, app) "
                          "VALUES (?,?,?,?,?,?,0,?,?,?,?,?)",
                          (pid, name, kind, instructions, json.dumps(notes), folder, work_list,
                           json.dumps(goals), now, now, app))
            except Exception as exc:
                if made:
                    # Only the folder THIS call just made: never another.
                    _workspace().remove_new_project(app)
                if isinstance(exc, sqlite3.IntegrityError) and app:
                    raise OverflowError("that app already has a project") from exc
                raise
        _audit("projects.create", {"id": pid, "kind": kind, "app": bool(app)})
        return self.get(pid)

    def _check_adopt(self, c, adopt: str) -> str:
        W = _workspace()
        try:
            W.check_name(adopt)
        except W.WorkspaceError as exc:
            raise ValueError(str(exc)) from exc
        if adopt not in {a["name"] for a in W.list_projects()}:
            raise NoSuchApp("There is no app folder with that name.")
        if c.execute("SELECT 1 FROM projects WHERE app = ?", (adopt,)).fetchone():
            raise OverflowError("that app already has a project")
        return adopt

    def _make_app(self, c, name: str, app_type: str) -> str:
        """A new, empty app folder for this project (no card: an empty folder
        in Jarvis's own folder, nothing runs)."""
        W = _workspace()
        import jarvis_apps
        taken = {a["name"] for a in W.list_projects()}
        taken |= {r[0] for r in c.execute("SELECT app FROM projects WHERE app IS NOT NULL")}
        try:
            root = W.root()
            if root.is_dir():
                taken |= {d.name for d in root.iterdir()}
        except OSError:
            pass
        slug = jarvis_apps.slug(name, taken)
        try:
            W.create_project(slug, app_type, name)
        except W.GitUnavailable as exc:
            raise Unavailable(str(exc)) from exc
        except W.WorkspaceError as exc:
            raise ValueError(str(exc)) from exc
        return slug

    def _list_free(self, c, work_list: Optional[str], pid: Optional[str]) -> None:
        if not work_list:
            return
        r = c.execute("SELECT id, name FROM projects WHERE work_list = ? AND id != ?",
                      (work_list, pid or "")).fetchone()
        if r is not None:
            raise OverflowError(f"the {_list_title(work_list)} already belongs to the "
                                f"project \"{r['name']}\"")

    def update(self, pid: str, body: dict, *, here: bool) -> dict:
        """Edit what the owner typed. No card: name, instructions, notes,
        goals, work list, folder (PC only), and Shareable OFF. Shareable ON
        is not here - request_shareable() raises its card."""
        if not isinstance(body, dict):
            raise ValueError("send the fields to change")
        # Shareable OFF and a late yes on its card never interleave: the
        # card's write takes the same switch lock (_decide).
        switch = _P_SWITCH if body.get("shareable") is False else contextlib.nullcontext()
        with switch:
            return self._update(pid, body, here=here)

    def _update(self, pid: str, body: dict, *, here: bool) -> dict:
        with self._lock, self._db() as c:
            r = self._project_row(c, pid)
            sets, args = [], []
            if "name" in body:
                name = _one_line(body.get("name"), MAX_NAME, "a project's name", required=True)
                if c.execute("SELECT 1 FROM projects WHERE lower(name) = lower(?) AND id != ?",
                             (name, pid)).fetchone():
                    raise OverflowError("there is already a project with that name")
                sets.append("name = ?")
                args.append(name)
            if "kind" in body and body.get("kind") != r["kind"]:
                raise ValueError("a project's kind cannot change - make a new project")
            if "app" in body:
                raise ValueError(APP_CHOSEN_WORDS)
            if r["app"] and body.get("folder") not in (None, ""):
                raise ValueError(APP_ONLY_WORDS)
            if "instructions" in body:
                sets.append("instructions = ?")
                args.append(_text(body.get("instructions"), MAX_INSTRUCTIONS,
                                  "the instructions"))
            if "notes" in body:
                sets.append("notes = ?")
                args.append(json.dumps(clean_notes(body.get("notes"))))
            if "goals" in body:
                sets.append("goals = ?")
                args.append(json.dumps(clean_goals(body.get("goals"))))
            if "work_list" in body:
                wl = clean_work_list(body.get("work_list"))
                self._list_free(c, wl, pid)
                sets.append("work_list = ?")
                args.append(wl)
            if "folder" in body:
                f = body.get("folder")
                if f in (None, ""):
                    # Clearing it only lets Jarvis see less: either app.
                    new = None
                else:
                    if r["kind"] != "coding":
                        raise ValueError("a life project has no folder")
                    if not here:
                        raise PermissionError(PC_ONLY_FOLDER)
                    new = check_folder(f)
                sets.append("folder = ?")
                args.append(new)
            if "shareable" in body:
                s = body.get("shareable")
                if s is True and not r["shareable"]:
                    raise ValueError("turning Shareable on asks you first - use "
                                     "/api/projects/<id>/shareable")
                if s is False:
                    sets.append("shareable = 0")
                elif s is not True:
                    raise ValueError("shareable is true or false")
            if sets:
                sets.append("changed = ?")
                args.append(self.clock())
                c.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", (*args, pid))
        if "shareable" in body and body.get("shareable") is False:
            _withdraw_share(pid)
        _audit("projects.update", {"id": pid, "fields": len(sets)})
        return self.get(pid)

    def delete(self, pid: str) -> bool:
        self.delete_full(pid)
        return True

    def delete_full(self, pid: str) -> dict:
        """Deletes the project; answers {"app": <folder name or None>}. An app
        project's FOLDER is never deleted - only the record and its
        benchmarks - and a merge card waiting for it is withdrawn."""
        with _P_SWITCH:
            return self._delete(pid)

    def _delete(self, pid: str) -> dict:
        with self._lock, self._db() as c:
            app = self._project_row(c, pid)["app"]
            benches = [b["id"] for b in c.execute("SELECT id FROM benchmarks WHERE project = ?",
                                                  (pid,)).fetchall()]
            for bid in benches:
                c.execute("DELETE FROM results WHERE bench = ?", (bid,))
            c.execute("DELETE FROM benchmarks WHERE project = ?", (pid,))
            c.execute("DELETE FROM projects WHERE id = ?", (pid,))
        _withdraw_share(pid)
        for bid in benches:
            _withdraw_unmark(bid)
        if app:
            try:
                import jarvis_apps
                jarvis_apps.withdraw_card(app)
            except ImportError:
                pass
        _audit("projects.delete", {"id": pid, "benchmarks": len(benches), "app": bool(app)})
        return {"app": app}

    def set_shareable_on(self, pid: str) -> None:
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            c.execute("UPDATE projects SET shareable = 1, changed = ? WHERE id = ?",
                      (self.clock(), pid))
        _audit("projects.shareable_on", {"id": pid})

    # ---- benchmarks ---------------------------------------------------------------

    def add_benchmark(self, pid: str, body: dict, *, here: bool) -> dict:
        if not isinstance(body, dict):
            raise ValueError('need {"name": ..., "kind": "number" or "command"}')
        name = _one_line(body.get("name"), MAX_BENCH_NAME, "a benchmark's name", required=True)
        kind = body.get("kind", "number")
        if kind not in BENCH_KINDS:
            raise ValueError('a benchmark is "number" (you log it) or "command" (a test '
                             'or a script on the PC)')
        unit = _one_line(body.get("unit"), MAX_UNIT, "the unit")
        better = body.get("better")
        if better not in (None,) + BETTER:
            raise ValueError('"better" is "higher", "lower" or left out')
        target = _opt_value(body.get("target"))
        owner = body.get("sensitive") is True
        command = None
        now = self.clock()
        bid = _new_id()
        with self._lock, self._db() as c:
            r = self._project_row(c, pid)
            if kind == "command":
                if r["kind"] != "coding":
                    raise ValueError("a life project's benchmarks are numbers you log")
                if not here:
                    raise PermissionError(PC_ONLY_COMMAND)
                command = _one_line(body.get("command"), MAX_COMMAND, "the command",
                                    required=True)
            elif body.get("command") not in (None, ""):
                raise ValueError("a number you log has no command")
            n = c.execute("SELECT COUNT(*) FROM benchmarks WHERE project = ?",
                          (pid,)).fetchone()[0]
            if n >= MAX_BENCHMARKS:
                raise OverflowError(f"a project has at most {MAX_BENCHMARKS} benchmarks")
            if c.execute("SELECT 1 FROM benchmarks WHERE project = ? AND lower(name) = lower(?)",
                         (pid, name)).fetchone():
                raise OverflowError("this project already has a benchmark with that name")
            c.execute("INSERT INTO benchmarks (id, project, name, kind, unit, better, target, "
                      "command, owner_sensitive, created, changed) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (bid, pid, name, kind, unit, better, target, command, int(owner),
                       now, now))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?", (now, pid))
            v = self._bench_view(c, self._bench_row(c, pid, bid))
        _audit("projects.benchmark.add", {"project": pid, "id": bid, "kind": kind})
        return v

    def update_benchmark(self, pid: str, bid: str, body: dict, *, here: bool) -> dict:
        if not isinstance(body, dict):
            raise ValueError("send the fields to change")
        # A late yes on an "unmark" card and a rename or a new mark of the
        # owner's never interleave: the card's write takes this lock too.
        with _P_SWITCH:
            return self._update_benchmark(pid, bid, body, here=here)

    def _update_benchmark(self, pid: str, bid: str, body: dict, *, here: bool) -> dict:
        recheck = False
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            sets, args = [], []
            if "name" in body:
                name = _one_line(body.get("name"), MAX_BENCH_NAME, "a benchmark's name",
                                 required=True)
                if c.execute("SELECT 1 FROM benchmarks WHERE project = ? AND lower(name) = "
                             "lower(?) AND id != ?", (pid, name, bid)).fetchone():
                    raise OverflowError("this project already has a benchmark with that name")
                sets.append("name = ?")
                args.append(name)
                recheck = recheck or name != b["name"]
            if "kind" in body and body.get("kind") != b["kind"]:
                raise ValueError("a benchmark's kind cannot change - make a new one")
            if "unit" in body:
                unit = _one_line(body.get("unit"), MAX_UNIT, "the unit")
                sets.append("unit = ?")
                args.append(unit)
                recheck = recheck or unit != b["unit"]
            if "better" in body:
                if body.get("better") not in (None,) + BETTER:
                    raise ValueError('"better" is "higher", "lower" or null')
                sets.append("better = ?")
                args.append(body.get("better"))
            if "target" in body:
                sets.append("target = ?")
                args.append(_opt_value(body.get("target")))
            if "sensitive" in body:
                if not isinstance(body.get("sensitive"), bool):
                    raise ValueError("sensitive is true or false")
                # Only YOUR mark changes; a mark made from the name stays
                # (it comes off only through request_unmark(), with a card).
                sets.append("owner_sensitive = ?")
                args.append(int(body["sensitive"]))
            if "command" in body:
                if b["kind"] != "command":
                    raise ValueError("a number you log has no command")
                if not here:
                    raise PermissionError(PC_ONLY_COMMAND)
                sets.append("command = ?")
                args.append(_one_line(body.get("command"), MAX_COMMAND, "the command",
                                      required=True))
            if recheck:
                # A new name or unit is checked again: an automatic mark the
                # owner took off comes back if the new words still look like
                # health or money.
                sets.append("auto_cleared = NULL")
            if sets:
                now = self.clock()
                sets.append("changed = ?")
                args.append(now)
                c.execute(f"UPDATE benchmarks SET {', '.join(sets)} WHERE id = ?", (*args, bid))
        if recheck or body.get("sensitive") is True:
            # The card showed the old words, or the owner marked it again:
            # a waiting "unmark" card no longer counts.
            _withdraw_unmark(bid)
        with self._lock, self._db() as c:
            v = self._bench_view(c, self._bench_row(c, pid, bid))
        _audit("projects.benchmark.update", {"project": pid, "id": bid, "fields": len(sets)})
        return v

    def unmark_owner(self, pid: str, bid: str) -> bool:
        """Take the owner's own private mark off at once. True when it was on."""
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            if not b["owner_sensitive"]:
                return False
            c.execute("UPDATE benchmarks SET owner_sensitive = 0, changed = ? WHERE id = ?",
                      (self.clock(), bid))
        _audit("projects.benchmark.unmark", {"project": pid, "id": bid, "whose": "owner"})
        return True

    def clear_auto_mark(self, pid: str, bid: str, name: str, unit: str, topic: str) -> None:
        """After a person's yes on the card: take off the automatic mark -
        only if the benchmark still has the words the card showed."""
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            if (b["name"], b["unit"]) != (name, unit) or auto_sensitive(name, unit) != topic:
                raise LookupError("the benchmark changed while the card waited")
            c.execute("UPDATE benchmarks SET auto_cleared = ?, changed = ? WHERE id = ?",
                      (topic, self.clock(), bid))
        _audit("projects.benchmark.unmark", {"project": pid, "id": bid, "whose": "auto"})

    def delete_benchmark(self, pid: str, bid: str) -> bool:
        with _P_SWITCH, self._lock, self._db() as c:
            self._project_row(c, pid)
            self._bench_row(c, pid, bid)
            c.execute("DELETE FROM results WHERE bench = ?", (bid,))
            c.execute("DELETE FROM benchmarks WHERE id = ?", (bid,))
        _withdraw_unmark(bid)
        _audit("projects.benchmark.delete", {"project": pid, "id": bid})
        return True

    def log(self, pid: str, bid: str, value, *, at=None, source: str = "app") -> dict:
        """One number the owner logged - their own tap or their own words.
        No card. A command benchmark's results come from running it, which
        is a later step, so logging one by hand is refused."""
        v = _value(value)
        now = self.clock()
        if at is None:
            when = now
        else:
            when = _value(at)
            if when > now + 86400 or when < now - 20 * 365 * 86400:
                raise ValueError("that date is too far from today")
        if source not in ("app", "words"):
            source = "app"
        rid = _new_id()
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            if b["kind"] != "number":
                raise ValueError("a command's results come from running it, which comes in a "
                                 "later step")
            n = c.execute("SELECT COUNT(*) FROM results WHERE bench = ?", (bid,)).fetchone()[0]
            if n >= MAX_RESULTS:
                raise OverflowError(f"this benchmark already has {MAX_RESULTS} numbers - "
                                    f"remove some old ones first")
            c.execute("INSERT INTO results (id, bench, value, at, source, logged) "
                      "VALUES (?,?,?,?,?,?)", (rid, bid, v, when, source, now))
            out = self._bench_view(c, self._bench_row(c, pid, bid))
        _audit("projects.log", {"project": pid, "bench": bid, "source": source})
        out["logged"] = {"id": rid, "value": v, "at": when}
        return out

    def delete_result(self, pid: str, bid: str, rid: str) -> bool:
        if not isinstance(rid, str) or not _ID.fullmatch(rid):
            raise KeyError(rid)
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            self._bench_row(c, pid, bid)
            cur = c.execute("DELETE FROM results WHERE id = ? AND bench = ?", (rid, bid))
            if cur.rowcount == 0:
                raise KeyError(rid)
        _audit("projects.result.delete", {"project": pid, "bench": bid})
        return True

    def results(self, pid: str, bid: str, points: int = CHART_POINTS) -> dict:
        """For a chart: dated points (oldest first, at most `points`), the
        target line when there is one, and better/worse than last time."""
        try:
            points = int(points)
        except (TypeError, ValueError):
            points = CHART_POINTS
        points = max(1, min(points, CHART_POINTS_MAX))
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            return self._bench_view(c, self._bench_row(c, pid, bid), points=points)

    # ---- the quick command's side ---------------------------------------------------

    def life_benchmarks(self) -> list:
        """Every number benchmark, with its project's name - for matching
        "I ran 5 km". Empty when there is no projects.db (nothing created)."""
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            rows = c.execute("SELECT b.id, b.project, b.name, b.unit, b.owner_sensitive, "
                             "b.auto_cleared, p.name AS project_name FROM benchmarks b "
                             "JOIN projects p ON p.id = b.project WHERE b.kind = 'number' "
                             "ORDER BY b.created").fetchall()
        return [{"id": r["id"], "project": r["project"], "name": r["name"], "unit": r["unit"],
                 "project_name": r["project_name"],
                 "sensitive": marks(r["name"], r["unit"], r["owner_sensitive"],
                                    r["auto_cleared"])["sensitive"]}
                for r in rows]


def _list_title(key: Optional[str]) -> str:
    try:
        import jarvis_schedule
        return jarvis_schedule.list_title(key)
    except Exception:
        return (key[0].upper() + key[1:] + " list") if key else "To-do list"


# --------------------------------------------------------------------------
#   Better or worse than last time
# --------------------------------------------------------------------------


def compare(latest: Optional[float], previous: Optional[float], better: Optional[str],
            *, target: Optional[float] = None) -> Optional[dict]:
    """{"direction": "up"|"down"|"same", "by", "verdict": "better"|"worse"|
    "same"|None, "said", "target_reached"} - or None with no number yet.
    Without `better` there is no verdict: up is not always good (a weight,
    a 5k time), so Jarvis does not guess."""
    if latest is None:
        return None
    reached = None
    if target is not None and better in BETTER:
        reached = latest >= target if better == "higher" else latest <= target
    if previous is None:
        return {"direction": None, "by": None, "verdict": None,
                "said": "The first number.", "target_reached": reached}
    diff = latest - previous
    if abs(diff) < 1e-9:
        direction = "same"
    else:
        direction = "up" if diff > 0 else "down"
    if direction == "same":
        verdict = "same"
    elif better == "higher":
        verdict = "better" if direction == "up" else "worse"
    elif better == "lower":
        verdict = "better" if direction == "down" else "worse"
    else:
        verdict = None
    by = _num_words(abs(diff))
    if direction == "same":
        said = "The same as last time."
    elif verdict:
        said = f"{verdict.capitalize()} than last time ({direction} {by})."
    else:
        said = f"{'Higher' if direction == 'up' else 'Lower'} than last time (by {by})."
    return {"direction": direction, "by": abs(diff), "verdict": verdict, "said": said,
            "target_reached": reached}


# --------------------------------------------------------------------------
#   The quick command: "log 5 km run", "I ran 5 km"
# --------------------------------------------------------------------------

#: What a said unit may mean. A benchmark's own unit decides between them
#: ("pounds" is a weight on one and money on another).
_UNIT_ALIASES = {
    "km": {"km"}, "kms": {"km"}, "k": {"km"}, "kilometre": {"km"}, "kilometres": {"km"},
    "kilometer": {"km"}, "kilometers": {"km"},
    "mi": {"mi"}, "mile": {"mi"}, "miles": {"mi"},
    "m": {"m"}, "metre": {"m"}, "metres": {"m"}, "meter": {"m"}, "meters": {"m"},
    "kg": {"kg"}, "kgs": {"kg"}, "kilo": {"kg"}, "kilos": {"kg"}, "kilogram": {"kg"},
    "kilograms": {"kg"},
    "lb": {"lb"}, "lbs": {"lb"}, "pound": {"lb", "gbp"}, "pounds": {"lb", "gbp"},
    "st": {"st"}, "stone": {"st"},
    "£": {"gbp"}, "gbp": {"gbp"}, "quid": {"gbp"},
    "$": {"usd"}, "usd": {"usd"}, "dollar": {"usd"}, "dollars": {"usd"}, "bucks": {"usd"},
    "€": {"eur"}, "eur": {"eur"}, "euro": {"eur"}, "euros": {"eur"},
    "min": {"min"}, "mins": {"min"}, "minute": {"min"}, "minutes": {"min"},
    "h": {"h"}, "hr": {"h"}, "hrs": {"h"}, "hour": {"h"}, "hours": {"h"},
    "s": {"s"}, "sec": {"s"}, "secs": {"s"}, "second": {"s"}, "seconds": {"s"},
    "kcal": {"kcal"}, "cal": {"kcal"}, "cals": {"kcal"}, "calorie": {"kcal"},
    "calories": {"kcal"},
    "%": {"%"}, "percent": {"%"}, "per cent": {"%"},
}

#: A verb said in the past ("I ran") and the word a benchmark's name uses.
_VERBS = {
    "ran": "run", "run": "run", "jogged": "run", "jog": "run",
    "walked": "walk", "walk": "walk", "hiked": "hike", "hike": "hike",
    "swam": "swim", "swim": "swim", "cycled": "cycle", "biked": "bike", "rode": "ride",
    "rowed": "row", "read": "read", "slept": "sleep", "weigh": "weight", "weighed": "weight",
    "saved": "save", "meditated": "meditate", "studied": "study", "practised": "practice",
    "practiced": "practice", "wrote": "write", "lifted": "lift", "did": "",
    "spent": "spend", "drank": "drink",
}

_WORD_NUMBERS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
_WORD_NUMBERS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                      "eighty": 80, "ninety": 90, "hundred": 100})

_NUM = (r"(?P<cur>[$£€])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?"
        r"|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")")
_UNIT = r"(?:(?:\s+|(?<=\d))(?P<unit>%|per cent|[a-z]+(?:/[a-z]+)?))?"
_WHEN_TAIL = re.compile(r"\s+(today|this morning|this afternoon|this evening|tonight"
                        r"|just now|yesterday)$")
_NAME = r"(?P<name>[a-z][a-z' -]{0,38}[a-z]|[a-z])"
_OWN = r"(?:(?:my|the|our)\s+)?"
_LEAD = re.compile(r"^(?:(?:hey|hi|ok|okay)\s+jarvis\b[\s,]*|jarvis\b[\s,]*|please\s+)+")

_LOG_PATTERNS = [
    # 0: "log 5 km run", "log 5 km for my run", "log 72.5 kg weight", "log 30 pages"
    re.compile(r"(?:log|record)\s+" + _NUM + _UNIT
               + r"(?:\s+(?:(?:of|for|on|as)\s+)?" + _OWN + _NAME + r")?"),
    # 1: "log my weight as 72.5 kg", "log weight 72.5 kg", "log my savings at $200"
    re.compile(r"(?:log|record)\s+" + _OWN + _NAME + r"(?:\s+(?:as|at|of|is))?:?\s+"
               + _NUM + _UNIT),
    # 2: "my weight is 72.5 kg", "my weight was 72.5 kg"
    re.compile(r"(?:my|our)\s+" + _NAME + r"\s+(?:is|was)\s+(?:now\s+)?" + _NUM + _UNIT),
    # 3: "i ran 5 km", "i walked 10000 steps", "i did 20 push ups"
    re.compile(r"i(?:'ve| have)?\s+(?:just\s+)?(?P<verb>[a-z]+)\s+" + _NUM + _UNIT
               + r"(?P<rest>(?:\s+[a-z]+){0,2})"),
]

#: Units that only measure; they never name what was done.
_MEASURE_ONLY = frozenset({"km", "mi", "m", "kg", "lb", "st", "min", "h", "s", "gbp", "usd",
                           "eur", "kcal", "%"})


def _tidy(text) -> str:
    t = str(text or "").replace("’", "'").replace("‘", "'").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = _LEAD.sub("", t).strip()
    t = re.sub(r"[\s.!?,]+$", "", t)
    t = re.sub(r"(?:[\s,]+(?:please|thanks|thank you|jarvis))+$", "", t).strip()
    return t


def _parse_num(raw: str) -> Optional[float]:
    if raw in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[raw])
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if math.isfinite(v) and abs(v) <= MAX_ABS_VALUE else None


_STOP = frozenset("my the a an our of for on in at to log and as is was".split())
#: Words (as stems) that describe a measurement but never say what was
#: done: "morning run" and "Long run" share "run", not these.
_WEAK = frozenset("up down out long short daily weekly monthly morning evening night total "
                  "new best".split())
_IRREGULAR = {"running": "run", "swimming": "swim", "savings": "save", "saving": "save",
              "pushups": "push", "situps": "sit", "ups": "up", "weight": "weight",
              "cycling": "cycle", "biking": "bike", "hiking": "hike", "riding": "ride",
              "writing": "write", "meditation": "meditate", "meditating": "meditate",
              "practising": "practice", "practicing": "practice", "studying": "study",
              "spending": "spend", "drinking": "drink", "morning": "morning",
              "evening": "evening"}


def _stem(word: str) -> str:
    """A word's plain root, the same way on both sides ("steps" and "step",
    "pages" and "page", "I cycled" and "Cycling")."""
    w = word.lower().strip("'")
    if w.endswith("'s"):
        w = w[:-2]
    if _VERBS.get(w):
        return _VERBS[w]
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "shes", "ches", "xes", "zes")):
        return w[:-2]
    for suffix in ("ing", "ed"):
        if len(w) > len(suffix) + 2 and w.endswith(suffix):
            return w[: -len(suffix)]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _stems(words: str) -> set:
    return {_stem(w) for w in re.findall(r"[a-z][a-z']*", (words or "").lower())
            if w not in _STOP}


def unit_keys(unit: str) -> set:
    """What a unit may mean: "kilometres" -> {"km"}, "pounds" -> {"lb",
    "gbp"}, "pages" -> {"page"}. Empty for no unit."""
    u = (unit or "").strip().lower()
    if not u:
        return set()
    if u in _UNIT_ALIASES:
        return set(_UNIT_ALIASES[u])
    return {_stem(u)}


def _known_unit(unit: str) -> bool:
    return (unit or "").strip().lower() in _UNIT_ALIASES


def parse_log(text) -> Optional[dict]:
    """Pure: does this sentence log a number? {"value", "unit", "words",
    "when"} or None. Reads nothing, acts on nothing - which benchmark it
    means (if any) is match_log()'s question. `words` are the stems that
    name what was measured ("run" for "I ran", "weight" for "log my
    weight ...", "push" and "up" for "I did 20 push ups")."""
    s = _tidy(text)
    if not s or len(s) > 120 or "\n" in s:
        return None
    when = ""
    m = _WHEN_TAIL.search(s)
    if m:
        when, s = m.group(1), s[:m.start()].strip()
    for i, rx in enumerate(_LOG_PATTERNS):
        m = rx.fullmatch(s)
        if not m:
            continue
        g = m.groupdict()
        value = _parse_num(g["num"])
        if value is None:
            return None
        unit = g.get("unit") or ""
        if unit in _STOP:
            return None
        if g.get("cur"):
            if unit and not unit_keys(unit) & unit_keys(g["cur"]):
                return None        # "$200 km" is not a measurement
            unit = g["cur"]
        words = set()
        if i == 3:
            verb = g.get("verb") or ""
            if verb not in _VERBS or not unit:
                return None        # "I have 3 kids"; "I ran 5" - five what?
            if _VERBS[verb]:
                words.add(_VERBS[verb])
            words |= _stems(g.get("rest") or "")
        else:
            words |= _stems(g.get("name") or "")
        if unit and not _known_unit(unit):
            # "30 pages", "20 push ups": an unknown unit word also names it.
            words |= unit_keys(unit)
        words -= _MEASURE_ONLY
        if not words and not unit:
            return None
        return {"value": value, "unit": unit, "words": sorted(words), "when": when}
    return None


def match_log(parsed: Optional[dict], benchmarks: list) -> dict:
    """Pure: which of `benchmarks` (life_benchmarks()'s shape) the parsed
    sentence means. {"match": bench} for exactly one, {"ambiguous": [..]}
    for several, {} for none.

    A benchmark matches when the said unit fits its unit (a known unit
    must be the same one - no converting miles to km), and its name and
    the said words share a word that says WHAT was done ("run" in "I ran"
    and "Long run"; "morning" and "long" do not count) - or, with only a
    unit said, when that unit is its unit. "I did 20 sit ups" never
    matches "Push ups": sharing "up" is not enough."""
    if not parsed or not benchmarks:
        return {}
    words = set(parsed.get("words") or [])
    unit = parsed.get("unit") or ""
    said = unit_keys(unit)
    known = _known_unit(unit)
    hits = []
    for b in benchmarks:
        bunit = unit_keys(b.get("unit") or "")
        names = _stems(b.get("name") or "")
        if said and bunit and not (said & bunit) and known:
            continue                    # 5 km is never a number of miles
        if said and not known and not (said & bunit) and not (said & names):
            continue                    # "I ran 5 errands" is not a run
        if (words - _WEAK) & (names - _WEAK):
            hits.append(b)
        elif said and bunit and (said & bunit) and (not words or not known):
            hits.append(b)
    if len(hits) == 1:
        return {"match": hits[0]}
    if len(hits) > 1:
        return {"ambiguous": hits}
    return {}


def _when_at(when: str, now: float) -> float:
    return now - 86400 if when == "yesterday" else now


def quick_match(text, store: Optional[Projects] = None) -> Optional[dict]:
    """For jarvis_quick.py: None unless the sentence logs a number AND a
    life benchmark matches it (or several do - then the answer asks which).
    Reads projects.db only after the sentence already parsed, and never
    creates it."""
    parsed = parse_log(text)
    if parsed is None:
        return None
    try:
        store = store or get()
        benches = store.life_benchmarks()
    except Exception:
        return None
    got = match_log(parsed, benches)
    if not got:
        return None
    return dict(parsed, **got)


def quick_log(found: dict, *, store: Optional[Projects] = None,
              now: Optional[float] = None) -> dict:
    """For jarvis_quick.py: log what quick_match() found. {"said",
    "private"} - private when the benchmark is sensitive, so the apps keep
    the answer on screen and never read it aloud."""
    store = store or get()
    if found.get("ambiguous"):
        names = [f"\"{b['name']}\" in \"{b['project_name']}\"" for b in found["ambiguous"][:4]]
        return {"said": "Which one: " + " or ".join(names) + "? Nothing was logged - say it "
                        "with a word only one of them has, or log it in the app.",
                "private": any(b.get("sensitive") for b in found["ambiguous"])}
    b = found["match"]
    now = store.clock() if now is None else now
    out = store.log(b["project"], b["id"], found["value"],
                    at=_when_at(found.get("when") or "", now), source="words")
    unit = out.get("unit") or found.get("unit") or ""
    said = (f"Logged {_with_unit(found['value'], unit)} for \"{out['name']}\" in "
            f"\"{b['project_name']}\".")
    ch = out.get("change") or {}
    if ch.get("said") and ch.get("direction") is not None:
        said += " " + ch["said"]
    if ch.get("target_reached"):
        said += " Target reached."
    return {"said": said, "private": bool(out.get("sensitive"))}


# --------------------------------------------------------------------------
#   Shareable ON - ONE card (change_own_config); OFF at once
# --------------------------------------------------------------------------

_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}
#: Held while Shareable is switched off (or a project deleted) and while a
#: card's yes is written, so the two never interleave.
_P_SWITCH = threading.RLock()

LAST_WORDS = {
    "on": "Shareable is on.",
    "denied": "Shareable stays off - you said no.",
    "timed_out": "Shareable stays off - the card timed out.",
    "refused": "Shareable stays off.",
    "withdrawn": "Shareable stays off - you turned it off before answering.",
    "failed": "Shareable stays off - it could not be saved.",
}


def share_card(name: str) -> str:
    return "\n".join([
        f"Make the project \"{name}\" Shareable?",
        "",
        "When a project is Shareable, a short piece of its files may one day go to a web "
        "search or to an AI chatbot you use - but only after a card that shows you those "
        "exact words, every time. Nothing is sent by turning this on, and nothing can be "
        "sent today: that part is not built yet.",
        "",
        "Never shared, whatever this says: health or money numbers, anything Jarvis "
        "remembers about you, your email, and passwords or keys.",
        "",
        "Turning it off again is instant, from either app.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _finish(pid: str, token: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        p = _P_STATE["pending"].get(pid)
        if p and p.get("token") == token:
            _P_STATE["pending"].pop(pid, None)
        _P_STATE["withdrawn"].discard(token)
        _P_STATE["last"][pid] = {"outcome": outcome, "why": why, "at": time.time(),
                                 "message": LAST_WORDS.get(outcome, "")}
    _audit("projects.shareable.card", {"id": pid, "outcome": outcome})


def _withdraw_share(pid: str) -> None:
    with _P_LOCK:
        p = _P_STATE["pending"].pop(pid, None)
        if p:
            _P_STATE["withdrawn"].add(p["token"])


def _decide(pid: str, token: str, name: str, store: Projects, gate: Callable,
            tier_of: Callable) -> None:
    text = share_card(name)
    detail = {"text": text, "what": "make one project Shareable",
              "setting": "Shareable", "to": name, "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, token, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish(pid, token, "refused", f"the gate answered at tier {vtier!r}, which "
                                              f"is not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, token, outcome)
        return _finish(pid, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _P_SWITCH:
        with _P_LOCK:
            withdrawn = token in _P_STATE["withdrawn"]
        if withdrawn:
            return _finish(pid, token, "withdrawn")
        try:
            store.set_shareable_on(pid)
        except Exception as exc:
            return _finish(pid, token, "failed", type(exc).__name__)
    _finish(pid, token, "on")


def request_shareable(pid: str, body, *, store: Optional[Projects] = None,
                      gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                      spawn: Optional[Callable] = None) -> tuple:
    """POST /api/projects/<id>/shareable {"on": true|false}. OFF: at once,
    no card (and a waiting card is withdrawn). ON: 202 and ONE card."""
    store = store or get()
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
        return 400, {"ok": False, "error": 'need {"on": true} or {"on": false}'}
    try:
        project = store.get(pid)
    except KeyError:
        return 404, {"ok": False, "error": "no such project"}
    if body["on"] is False:
        out = store.update(pid, {"shareable": False}, here=False)
        return 200, {"ok": True, "changed": project["shareable"], "project": out,
                     "message": "Shareable is off. Nothing from this project can be shared."}
    if project["shareable"]:
        return 200, {"ok": True, "changed": False, "project": project,
                     "message": "Shareable is already on."}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; making a project "
            f"Shareable needs a person to say yes, so it must be 'ask'")}
    with _P_LOCK:
        if pid in _P_STATE["pending"]:
            return 409, {"ok": False, "error": "A card for this is already waiting - answer "
                                               "it first."}
        token = uuid.uuid4().hex
        _P_STATE["pending"][pid] = {"token": token, "since": time.time()}
    try:
        spawn(lambda: _decide(pid, token, project["name"], store, gate, tier_of))
    except Exception:
        with _P_LOCK:
            _P_STATE["pending"].pop(pid, None)
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "project": store.get(pid),
                 "message": "Waiting for your approval. Shareable stays off unless you "
                            "approve the card."}


# --------------------------------------------------------------------------
#   Taking a private mark off a benchmark: the owner's own mark at once;
#   Jarvis's automatic mark with ONE card (the owner, 2026-09-28)
# --------------------------------------------------------------------------

_M_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}

UNMARK_WORDS = {
    "off": "The private mark is off. Jarvis may read these numbers aloud now.",
    "denied": "The numbers stay private - you said no.",
    "timed_out": "The numbers stay private - the card timed out.",
    "refused": "The numbers stay private.",
    "withdrawn": "The numbers stay private - the benchmark changed, or you marked it "
                 "again, before you answered.",
    "failed": "The numbers stay private - the benchmark changed while the card waited.",
}

TOPIC_WORDS = {"health": "health", "money": "money"}


def unmark_card(name: str, project: str, topic: str, unit: str = "") -> str:
    looks = TOPIC_WORDS.get(topic, f"a private topic ({topic})")
    words = f"\"{name}\"" + (f" (in {unit})" if unit else "")
    return "\n".join([
        f"Take the private mark off \"{name}\" in the project \"{project}\"?",
        "",
        f"Jarvis marked this benchmark private by itself, because its name {words} "
        f"looked like {looks}. While it is marked, its numbers stay on screen: never read "
        "aloud, and never sent anywhere.",
        "",
        "If you take the mark off, Jarvis may read these numbers aloud, like any other "
        "answer.",
        "",
        "Renaming the benchmark or changing its unit checks it again. You can mark it "
        "private yourself at any time, instantly.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes. The numbers stay private.",
    ])


def _finish_unmark(bid: str, token: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        p = _M_STATE["pending"].get(bid)
        if p and p.get("token") == token:
            _M_STATE["pending"].pop(bid, None)
        _M_STATE["withdrawn"].discard(token)
        _M_STATE["last"][bid] = {"outcome": outcome, "why": why, "at": time.time(),
                                 "message": UNMARK_WORDS.get(outcome, "")}
    _audit("projects.unmark.card", {"id": bid, "outcome": outcome})


def _withdraw_unmark(bid: str) -> None:
    with _P_LOCK:
        p = _M_STATE["pending"].pop(bid, None)
        if p:
            _M_STATE["withdrawn"].add(p["token"])


def _decide_unmark(pid: str, bid: str, token: str, bench: dict, project: str,
                   store: Projects, gate: Callable, tier_of: Callable) -> None:
    text = unmark_card(bench["name"], project, bench["topic"], bench["unit"])
    detail = {"text": text, "what": "take the private mark off one benchmark",
              "setting": "Private mark", "to": bench["name"], "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish_unmark(bid, token, "refused",
                              f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish_unmark(bid, token, "refused", f"the gate answered at tier {vtier!r}, "
                                                     f"which is not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish_unmark(bid, token, outcome)
        return _finish_unmark(bid, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _P_SWITCH:
        with _P_LOCK:
            withdrawn = token in _M_STATE["withdrawn"]
        if withdrawn:
            return _finish_unmark(bid, token, "withdrawn")
        try:
            store.clear_auto_mark(pid, bid, bench["name"], bench["unit"], bench["topic"])
        except Exception as exc:
            return _finish_unmark(bid, token, "failed", type(exc).__name__)
    _finish_unmark(bid, token, "off")


def _bench_only(store: Projects, pid: str, bid: str) -> dict:
    out = store.results(pid, bid, 1)
    out.pop("points", None)
    out.pop("points_shown", None)
    return out


def request_unmark(pid: str, bid: str, body=None, *, store: Optional[Projects] = None,
                   gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                   spawn: Optional[Callable] = None) -> tuple:
    """POST /api/projects/<id>/benchmarks/<bid>/unmark {}. The owner's own
    mark comes off at once, no card. A mark Jarvis made from the name: 202
    and ONE card; it comes off only on a person's yes."""
    store = store or get()
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if body is not None and not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    try:
        with store._lock, store._db() as c:
            p = store._project_row(c, pid)
            b = store._bench_row(c, pid, bid)
            m = marks(b["name"], b["unit"], b["owner_sensitive"], b["auto_cleared"])
            project = p["name"]
            bench = {"name": b["name"], "unit": b["unit"], "topic": m["auto_holds"]}
    except KeyError:
        return 404, {"ok": False, "error": "no such project, benchmark or number"}
    if m["auto_holds"]:
        t = tier_of(CARD_ACTION)
        if t != "ask":
            return 503, {"ok": False, "error": (
                f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; taking Jarvis's own "
                f"private mark off needs a person to say yes, so it must be 'ask'")}
        with _P_LOCK:
            if bid in _M_STATE["pending"]:
                return 409, {"ok": False, "error": "A card for this is already waiting - "
                                                   "answer it first."}
    with _P_SWITCH:
        mine = store.unmark_owner(pid, bid) if m["owner"] else False
    if not m["auto_holds"]:
        return 200, {"ok": True, "changed": mine, "benchmark": _bench_only(store, pid, bid),
                     "message": ("Your private mark is off." if mine
                                 else "This benchmark has no private mark.")}
    with _P_LOCK:
        if bid in _M_STATE["pending"]:
            return 409, {"ok": False, "error": "A card for this is already waiting - answer "
                                               "it first."}
        token = uuid.uuid4().hex
        _M_STATE["pending"][bid] = {"token": token, "since": time.time()}
    try:
        spawn(lambda: _decide_unmark(pid, bid, token, bench, project, store, gate, tier_of))
    except Exception:
        with _P_LOCK:
            _M_STATE["pending"].pop(bid, None)
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "changed": mine,
                 "benchmark": _bench_only(store, pid, bid),
                 "message": ("Your own mark is off. " if mine else "")
                 + "Waiting for your approval. The numbers stay private unless you approve "
                   "the card."}


# --------------------------------------------------------------------------
#   The one store this backend uses
# --------------------------------------------------------------------------

_ONE: Optional[Projects] = None
_ONE_LOCK = threading.Lock()


def get() -> Projects:
    global _ONE
    with _ONE_LOCK:
        if _ONE is None:
            _ONE = Projects()
        return _ONE


# --------------------------------------------------------------------------
#   The routes (docs/JARVIS-API.md section 88)
# --------------------------------------------------------------------------

PATH = "/api/projects"


def parse_route(route: str) -> Optional[tuple]:
    """None, or a tuple naming the route:
        ("list",)                                   /api/projects
        ("project", pid)                            /api/projects/<pid>
        ("project_delete", pid)                     /api/projects/<pid>/delete
        ("shareable", pid)                          /api/projects/<pid>/shareable
        ("benchmarks", pid)                         /api/projects/<pid>/benchmarks
        ("bench", pid, bid)                         .../benchmarks/<bid>
        ("bench_delete", pid, bid)                  .../benchmarks/<bid>/delete
        ("log", pid, bid)                           .../benchmarks/<bid>/log
        ("unmark", pid, bid)                        .../benchmarks/<bid>/unmark
        ("result_delete", pid, bid, rid)            .../benchmarks/<bid>/results/<rid>/delete
    """
    if not isinstance(route, str):
        return None
    if route == PATH:
        return ("list",)
    if not route.startswith(PATH + "/"):
        return None
    p = route[len(PATH) + 1:].split("/")
    if not p[0]:
        return None
    pid = p[0]
    if len(p) == 1:
        return ("project", pid)
    if len(p) == 2 and p[1] in ("delete", "shareable", "benchmarks"):
        return ({"delete": "project_delete", "shareable": "shareable",
                 "benchmarks": "benchmarks"}[p[1]], pid)
    if len(p) >= 3 and p[1] == "benchmarks" and p[2]:
        bid = p[2]
        if len(p) == 3:
            return ("bench", pid, bid)
        if len(p) == 4 and p[3] in ("delete", "log", "unmark"):
            return ({"delete": "bench_delete", "log": "log", "unmark": "unmark"}[p[3]],
                    pid, bid)
        if len(p) == 6 and p[3] == "results" and p[4] and p[5] == "delete":
            return ("result_delete", pid, bid, p[4])
    return None


def _err(exc) -> tuple:
    """(status, body) for the plain exceptions the store raises - never a
    stack trace reaching an app."""
    if isinstance(exc, NoSuchApp):
        return 404, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, Unavailable):
        return 503, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, KeyError):
        return 404, {"ok": False, "error": "no such project, benchmark or number"}
    if isinstance(exc, PermissionError):
        return 403, {"ok": False, "error": str(exc), "pc_only": True}
    if isinstance(exc, ValueError):
        return 400, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, OverflowError):
        return 409, {"ok": False, "error": _sentence(exc)}
    return 503, {"ok": False, "error": type(exc).__name__}


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


def handle_get(route: str, query: str = "", *, store: Optional[Projects] = None) -> tuple:
    store = store or get()
    hit = parse_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "no such route"}
    try:
        if hit[0] == "list":
            items = store.list()
            return 200, {"ok": True, "available": True, "title": TITLE, "projects": items,
                         "empty": EMPTY if not items else "", "max": MAX_PROJECTS,
                         "unlinked_apps": store.unlinked_apps()}
        if hit[0] == "project":
            return 200, {"ok": True, "project": store.get(hit[1])}
        if hit[0] == "bench":
            q = parse_qs(query or "")
            n = (q.get("points") or [CHART_POINTS])[0]
            return 200, {"ok": True, "benchmark": store.results(hit[1], hit[2], n)}
    except Exception as exc:
        return _err(exc)
    return 405, {"ok": False, "error": "use POST for this"}


def handle_post(route: str, body, *, here: bool = False,
                store: Optional[Projects] = None, **card) -> tuple:
    store = store or get()
    hit = parse_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "no such route"}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    kind = hit[0]
    try:
        if kind == "list":
            return 200, {"ok": True, "project": store.create(body, here=here)}
        if kind == "project":
            return 200, {"ok": True, "project": store.update(hit[1], body, here=here)}
        if kind == "project_delete":
            gone = store.delete_full(hit[1])
            out = {"ok": True, "deleted": True}
            if gone.get("app"):
                out["app_kept"] = gone["app"]
            return 200, out
        if kind == "shareable":
            return request_shareable(hit[1], body, store=store, **card)
        if kind == "benchmarks":
            return 200, {"ok": True, "benchmark": store.add_benchmark(hit[1], body, here=here)}
        if kind == "bench":
            return 200, {"ok": True,
                         "benchmark": store.update_benchmark(hit[1], hit[2], body, here=here)}
        if kind == "bench_delete":
            store.delete_benchmark(hit[1], hit[2])
            return 200, {"ok": True, "deleted": True}
        if kind == "log":
            return 200, {"ok": True, "benchmark": store.log(hit[1], hit[2], body.get("value"),
                                                            at=body.get("at"), source="app")}
        if kind == "result_delete":
            store.delete_result(hit[1], hit[2], hit[3])
            return 200, {"ok": True, "deleted": True}
        if kind == "unmark":
            return request_unmark(hit[1], hit[2], body, store=store, **card)
    except Exception as exc:
        return _err(exc)
    return 404, {"ok": False, "error": "no such route"}


def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the projects routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_projects", False):
        _ARMED = True
        return "  projects   Projects (already on)"

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
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if parse_route(route) is None:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if parse_route(route) is None:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_projects = True
    do_POST._jarvis_projects = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    try:
        n = len(get().list())
    except Exception:
        n = 0
    return f"  projects   Projects: {n} kept"


_ARMED = False


def _reset_for_tests() -> None:
    global _ARMED, _ONE
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].clear()
        _P_STATE["last"].clear()
        _M_STATE["pending"].clear()
        _M_STATE["withdrawn"].clear()
        _M_STATE["last"].clear()
    with _ONE_LOCK:
        _ONE = None
    _ARMED = False
