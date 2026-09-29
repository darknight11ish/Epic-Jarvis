"""jarvis_app_workspace.py - where Jarvis builds apps, and the one card that
lets its work in.

WHAT IT IS FOR
The owner decided on 2026-09-28 that Jarvis may build apps: web apps (React +
Vite, wrapped for Android with Capacitor) and native Android apps (Kotlin).
docs/APP-BUILDER-DESIGN.md is the whole plan. This module is its first
milestone, the workspace, and it RUNS NOTHING: no npm, no Gradle, no build.
It only keeps files, and keeps Jarvis's changes apart until the owner has
seen them.

HOW IT WORKS, IN PLAIN WORDS
  * Every app is a folder under `<settings folder>/apps/<name>/`, a git
    repository whose `main` branch is the owner's accepted version.
  * Jarvis never writes to `main`. Each piece of work is a TASK: a separate
    working copy (a git "worktree") on its own branch, under
    `apps/.tasks/<name>-<task id>/`. Jarvis writes its files there.
  * When the task is ready, plan_merge() builds a Plan: every file changed,
    and the full before/after comparison (the diff). That is the approval
    card. run_merge() then brings exactly that into `main` - and refuses if
    anything changed after the card was built, so what was approved is what
    lands.
  * discard() throws a task away. Nothing reached `main`, so nothing is lost.

WHY WRITING A TASK'S FILES NEEDS NO CARD
The files land only in the task's own copy, inside Jarvis's own apps folder,
and nothing runs them. The owner's decision point is the merge, where every
change is shown in full. Running anything (npm, Gradle) is a later milestone
with a card per command - see the design doc for why a git worktree is NOT a
sandbox for running code.

WHAT GIT IS ALLOWED TO SEE
git runs with the allowlisted environment every child program gets
(jarvis_child_env.inherited: never a token, key or password), with the
owner's own git settings switched off (GIT_CONFIG_GLOBAL and
GIT_CONFIG_NOSYSTEM - a global setting could name a credential helper, a
hook folder or a program to run), and with hooks pointed at an empty folder.
Nothing here talks to a network: there is no remote, no fetch, no push.

WHAT JARVIS MAY WRITE
parse_file_blocks() reads the model's answer in one strict format:

    <<<FILE src/App.tsx>>>
    ...the whole file...
    <<<END>>>
    <<<DELETE src/old.css>>>

Paths are checked before anything is written (safe_path): relative, forward
slashes, no `..`, nothing inside `.git`, no Windows device names, no
trailing dots or spaces, and the real location must stay inside the task's
copy. Files are text, at most MAX_FILE_BYTES each, at most MAX_CHANGE_FILES
per change.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:  # the tests, and a PC without the framework
    fw = None

#: The approval card's action (jarvis_gate). A later milestone adds its line
#: to jarvis_gate.py's risk table; until then the gate's unknown-action rule
#: asks, which is the safe answer.
MERGE_ACTION = "app_merge_change"

KINDS = {"web": "a web app (React + Vite; Android through Capacitor)",
         "android": "a native Android app (Kotlin)"}

MAX_FILE_BYTES = 512 * 1024
MAX_CHANGE_FILES = 200
#: A diff longer than this is not put on one card: the owner is asked to
#: split the work instead, because a card nobody can read is not a decision.
MAX_CARD_DIFF_CHARS = 60_000
#: Tasks that may be open at once for one app. Each is a whole separate copy
#: of the app on disk, so the number is small on purpose.
MAX_OPEN_TASKS = 10
GIT_SECONDS = 60.0
#: Who wrote a task's files: Jarvis (a model tool, a later slice), the owner
#: (a change pasted in on the PC), or nobody yet (a task just started).
SOURCES = ("jarvis", "pasted", "empty")
PASTED_LINE = "You pasted this change in on your PC."

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_TASK = re.compile(r"^[0-9a-f]{12}$")
_WINDOWS_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                    *(f"lpt{i}" for i in range(1, 10))}
_BLOCK = re.compile(r"<<<FILE ([^\n>]+)>>>\n(.*?)\n?<<<END>>>|<<<DELETE ([^\n>]+)>>>", re.S)

GITIGNORE = """# Jarvis app workspace: never kept
node_modules/
dist/
build/
.gradle/
local.properties
*.keystore
*.jks
.env
.env.*
"""

_LOCK = threading.RLock()


class WorkspaceError(Exception):
    """A plain-words reason something was refused or failed."""


class GitUnavailable(WorkspaceError):
    """git is not installed, or did not answer in time: the caller answers 503
    (not 400), because nothing the owner typed was wrong."""


# --------------------------------------------------------------------------
#   Where things live
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


def root() -> Path:
    """`<settings folder>/apps` - every project, and the tasks' copies."""
    return _config_dir() / "apps"


def _tasks_dir() -> Path:
    return root() / ".tasks"


def project_dir(name: str) -> Path:
    return root() / check_name(name)


def check_name(name: str) -> str:
    """A project name: lower-case letters, digits and dashes, 1-40 of them,
    not starting with a dash. Returned as given; raises otherwise."""
    if not isinstance(name, str) or not _NAME.match(name):
        raise WorkspaceError("an app's name may use only small letters, digits and "
                             "dashes (up to 40), and must start with a letter or digit")
    return name


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only - never a file's name or its contents.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   git, with nothing of the owner's leaking in
# --------------------------------------------------------------------------

def git_env() -> dict:
    """The environment git runs with. The same allowlist as every program
    Jarvis starts (never a secret), plus switches that keep the owner's own
    git settings, prompts and pagers out of it."""
    import jarvis_child_env
    env = jarvis_child_env.inherited()
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "GIT_AUTHOR_NAME": "Jarvis", "GIT_AUTHOR_EMAIL": "jarvis@localhost",
        "GIT_COMMITTER_NAME": "Jarvis", "GIT_COMMITTER_EMAIL": "jarvis@localhost",
    })
    return env


def _no_hooks() -> Path:
    d = root() / ".no-hooks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _git(args: list, cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    try:
        env = git_env()
    except ImportError:
        raise WorkspaceError("jarvis_child_env.py is missing from the backend folder, so "
                             "git is not started: without it git would get your passwords")
    cmd = ["git", "-c", f"core.hooksPath={_no_hooks()}", "-c", "commit.gpgsign=false",
           "-c", "core.autocrlf=false", "-c", "core.quotepath=false", *args]
    try:
        out = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=GIT_SECONDS)
    except FileNotFoundError:
        raise GitUnavailable("git is not installed on this PC (https://git-scm.com), so "
                             "Jarvis cannot keep app projects yet")
    except subprocess.TimeoutExpired:
        raise GitUnavailable("git took too long and was stopped")
    if check and out.returncode != 0:
        raise WorkspaceError(f"git {args[0]} failed: {(out.stderr or out.stdout).strip()[:300]}")
    return out


# --------------------------------------------------------------------------
#   Projects
# --------------------------------------------------------------------------

def list_projects() -> list:
    out = []
    base = root()
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if d.is_dir() and _NAME.match(d.name) and (d / ".git").exists():
            meta = _read_json(d / ".jarvis-app.json")
            out.append({"name": d.name, "kind": meta.get("kind", "?"),
                        "title": meta.get("title", d.name)})
    return out


def create_project(name: str, kind: str, title: str = "") -> dict:
    """A new, empty app project: a git repository with a README, a
    .gitignore that keeps build output and signing keys out, and
    `.jarvis-app.json` saying what kind of app it is. No card: it is an empty
    folder inside Jarvis's own apps folder, and nothing runs."""
    check_name(name)
    if kind not in KINDS:
        raise WorkspaceError("the kind of app must be 'web' or 'android'")
    title = (title or name).strip()[:80]
    with _LOCK:
        d = root() / name
        if d.exists():
            raise WorkspaceError(f"there is already an app called {name}")
        d.mkdir(parents=True)
        try:
            _git(["init", "-q", "-b", "main"], d)
            (d / "README.md").write_text(f"# {title}\n\n{KINDS[kind].capitalize()}, "
                                         "built with Jarvis.\n", encoding="utf-8")
            (d / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
            (d / ".jarvis-app.json").write_text(
                json.dumps({"kind": kind, "title": title}, indent=2) + "\n", encoding="utf-8")
            _git(["add", "-A"], d)
            _git(["commit", "-q", "-m", f"Start {title}"], d)
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise
    _audit("app_project_created", {"kind": kind})
    return {"name": name, "kind": kind, "title": title}


def remove_new_project(name: str) -> None:
    """Removes an app folder the caller has JUST created and nothing else has
    used yet (Projects, when saving the project fails afterwards). Only ever
    called with the name create_project() returned a moment ago."""
    with _LOCK:
        shutil.rmtree(project_dir(name), ignore_errors=True)


# --------------------------------------------------------------------------
#   Tasks: a separate copy per piece of work
# --------------------------------------------------------------------------

def _task_meta_path(name: str, task: str) -> Path:
    return _tasks_dir() / f"{name}-{task}.json"


def task_dir(name: str, task: str) -> Path:
    check_name(name)
    if not isinstance(task, str) or not _TASK.match(task):
        raise WorkspaceError("that is not a task id")
    return _tasks_dir() / f"{name}-{task}"


def _branch(task: str) -> str:
    return f"jarvis/task-{task}"


def start_task(name: str, title: str, source: str = "jarvis") -> dict:
    """A new task: its own copy of `main`, on its own branch. Returns its id.
    `source` says who will write its files (SOURCES); at most MAX_OPEN_TASKS
    tasks are open for one app."""
    proj = project_dir(name)
    if not (proj / ".git").exists():
        raise WorkspaceError(f"there is no app called {name}")
    if source not in SOURCES:
        raise WorkspaceError("a task's source is 'jarvis', 'pasted' or 'empty'")
    title = " ".join(str(title or "").split())[:120] or "Untitled change"
    task = uuid.uuid4().hex[:12]
    with _LOCK:
        if len(list_tasks(name)) >= MAX_OPEN_TASKS:
            raise WorkspaceError(f"this app already has {MAX_OPEN_TASKS} open tasks - add or "
                                 "throw one away first")
        _tasks_dir().mkdir(parents=True, exist_ok=True)
        _git(["worktree", "add", "-q", "-b", _branch(task), str(task_dir(name, task)), "main"],
             proj)
        base = _git(["rev-parse", "main"], proj).stdout.strip()
        _write_json(_task_meta_path(name, task),
                    {"project": name, "task": task, "title": title, "base": base,
                     "source": source, "started": time.time()})
    _audit("app_task_started", {})
    return {"project": name, "task": task, "title": title, "source": source}


def list_tasks(name: str) -> list:
    check_name(name)
    out = []
    d = _tasks_dir()
    if d.is_dir():
        for f in sorted(d.glob(f"{name}-*.json")):
            meta = _read_json(f)
            if meta.get("project") == name and task_dir(name, meta.get("task", "")).is_dir():
                src = meta.get("source")
                out.append({"task": meta["task"], "title": meta.get("title", ""),
                            "source": src if src in SOURCES else "jarvis",
                            "base": meta.get("base", ""),
                            "started": meta.get("started")})
    return out


def task_known(name: str, task: str) -> bool:
    """Is there anything of this task left - its copy or its note? A task
    whose copy was deleted by hand is not listed (list_tasks), but discard()
    can still clean up its branch and note."""
    try:
        return task_dir(name, task).is_dir() or _task_meta_path(name, task).is_file()
    except WorkspaceError:
        return False


def set_source(name: str, task: str, source: str) -> None:
    """Records who wrote the task's files. A change pasted into a task always
    makes the whole task "pasted", so its card never claims Jarvis wrote what
    the owner typed."""
    if source not in SOURCES:
        raise WorkspaceError("a task's source is 'jarvis', 'pasted' or 'empty'")
    path = _task_meta_path(name, task)
    with _LOCK:
        meta = _read_json(path)
        if not meta:
            raise WorkspaceError("that task is gone - it was merged or thrown away")
        meta["source"] = source
        _write_json(path, meta)


def main_info(name: str) -> dict:
    """The app's latest saved version, read from git on `main`: short commit,
    the subject line, when, and how many versions (commits) there are."""
    proj = project_dir(name)
    if not (proj / ".git").exists():
        raise WorkspaceError(f"there is no app called {name}")
    with _LOCK:
        head = _git(["rev-parse", "main"], proj).stdout.strip()
        line = _git(["log", "-1", "--format=%ct%x09%s", "main"], proj).stdout.strip()
        count = _git(["rev-list", "--count", "main"], proj).stdout.strip()
    at, _, subject = line.partition("\t")
    try:
        when = float(at)
    except ValueError:
        when = None
    try:
        versions = int(count)
    except ValueError:
        versions = 0
    return {"head": head[:7], "subject": subject.strip(), "at": when, "versions": versions}


def main_head(name: str) -> str:
    """The full commit `main` is at now."""
    return _git(["rev-parse", "main"], project_dir(name)).stdout.strip()


def safe_path(tdir: Path, rel: str) -> Path:
    """Where `rel` really is inside the task copy `tdir`, or a refusal."""
    if not isinstance(rel, str):
        raise WorkspaceError("a file name must be text")
    rel = rel.strip()
    if not rel or len(rel) > 240 or "\\" in rel or "\x00" in rel or ":" in rel \
            or rel.startswith("/"):
        raise WorkspaceError(f"refused the file name {rel[:80]!r}: use a plain relative "
                             "path with forward slashes")
    parts = rel.split("/")
    for p in parts:
        low = p.lower()
        if p in ("", ".", "..") or low == ".git" or p != p.rstrip(". ") \
                or low.split(".")[0] in _WINDOWS_DEVICES:
            raise WorkspaceError(f"refused the file name {rel[:80]!r}")
    if parts[0] == ".jarvis-app.json" and len(parts) == 1:
        raise WorkspaceError("Jarvis's own note about the app is not changed this way")
    target = (tdir / rel)
    real_root = os.path.realpath(tdir)
    real = os.path.realpath(target)
    try:
        inside = os.path.commonpath([real_root, real]) == real_root
    except ValueError:  # another drive, on Windows
        inside = False
    if not inside:
        raise WorkspaceError(f"refused {rel[:80]!r}: it points outside the app")
    return target


def parse_file_blocks(text: str) -> list:
    """The model's answer -> [("write", path, content) | ("delete", path, None)].
    Only the strict block format counts; anything between blocks is ignored."""
    out = []
    for m in _BLOCK.finditer(text or ""):
        if m.group(3) is not None:
            out.append(("delete", m.group(3).strip(), None))
        else:
            out.append(("write", m.group(1).strip(), m.group(2) + "\n"))
    return out


def apply_change(name: str, task: str, changes: list, summary: str) -> dict:
    """Writes (or deletes) files in the task's copy and records them as one
    step on the task's branch. Every path is checked BEFORE anything is
    written, so a bad path leaves the copy untouched."""
    tdir = task_dir(name, task)
    if not tdir.is_dir():
        raise WorkspaceError("that task is gone - it was merged or thrown away")
    if not changes:
        raise WorkspaceError("there were no files in that change")
    if len(changes) > MAX_CHANGE_FILES:
        raise WorkspaceError(f"that change has {len(changes)} files; at most "
                             f"{MAX_CHANGE_FILES} are taken at once")
    checked = []
    for op, rel, content in changes:
        target = safe_path(tdir, rel)
        if op == "write":
            if not isinstance(content, str):
                raise WorkspaceError(f"{rel}: only text files are written")
            if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                raise WorkspaceError(f"{rel} is larger than {MAX_FILE_BYTES // 1024} KB")
        elif op == "delete":
            if not target.is_file():
                raise WorkspaceError(f"{rel} is not there to delete")
        else:
            raise WorkspaceError("unknown change")
        checked.append((op, rel, target, content))
    with _LOCK:
        for op, rel, target, content in checked:
            if op == "write":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="")
            else:
                target.unlink()
        _git(["add", "-A"], tdir)
        if not _git(["status", "--porcelain"], tdir).stdout.strip():
            return {"ok": True, "changed": 0}
        msg = " ".join(str(summary or "").split())[:200] or "Change by Jarvis"
        _git(["commit", "-q", "-m", msg], tdir)
        # What git really kept: a file its .gitignore drops (.env, dist/, a
        # signing key) is written but never part of the change, so counting
        # the blocks would promise a file the merge card will not show.
        kept = [f for f in _git(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                                tdir).stdout.splitlines() if f.strip()]
    _audit("app_change_applied", {"files": len(kept)})
    return {"ok": True, "changed": len(kept)}


def diff_stat(name: str, task: str) -> list:
    """What the task would change in `main`, file by file, without the text
    of the change: [{"path", "added", "removed"}] (counts as strings; "-" for
    a file git cannot count)."""
    proj, tdir = project_dir(name), task_dir(name, task)
    if not tdir.is_dir():
        raise WorkspaceError("that task is gone - it was merged or thrown away")
    stat = _git(["diff", "--numstat", f"main...{_branch(task)}"], proj).stdout
    files = []
    for line in stat.splitlines():
        a, d, path = (line.split("\t", 2) + ["", "", ""])[:3]
        files.append({"path": path, "added": a, "removed": d})
    return files


def app_meta(name: str) -> dict:
    """What `.jarvis-app.json` says about an app: {"kind", "title"} - empty
    strings when the folder or the note is missing."""
    meta = _read_json(project_dir(name) / ".jarvis-app.json")
    return {"kind": str(meta.get("kind", "")), "title": str(meta.get("title", name))}


def diff(name: str, task: str) -> dict:
    """What the task would change in `main`: the files and the full diff."""
    proj, tdir = project_dir(name), task_dir(name, task)
    if not tdir.is_dir():
        raise WorkspaceError("that task is gone - it was merged or thrown away")
    rng = f"main...{_branch(task)}"
    files = diff_stat(name, task)
    text = _git(["diff", "--no-color", "--no-ext-diff", rng], proj).stdout
    return {"files": files, "diff": text}


def discard(name: str, task: str) -> dict:
    """Throws the task away: its copy and its branch. `main` is untouched."""
    proj, tdir = project_dir(name), task_dir(name, task)
    with _LOCK:
        if tdir.is_dir():
            _git(["worktree", "remove", "--force", str(tdir)], proj)
        # Prune FIRST: a copy deleted by hand still counts as "checked out"
        # until then, and git will not delete a branch that is.
        _git(["worktree", "prune"], proj, check=False)
        _git(["branch", "-D", _branch(task)], proj, check=False)
        try:
            _task_meta_path(name, task).unlink()
        except FileNotFoundError:
            pass
    _audit("app_task_discarded", {})
    return {"ok": True}


# --------------------------------------------------------------------------
#   The merge: plan (the card), describe (its words), run (only as approved)
# --------------------------------------------------------------------------

@dataclass
class MergePlan:
    project: str
    task: str
    title: str
    files: list = field(default_factory=list)
    diff: str = ""
    #: Both captured when the card is built. run_merge() refuses if either
    #: moved: the owner approves the diff that was SHOWN.
    head: str = ""
    main: str = ""
    refused: str = ""
    #: "jarvis", "pasted" or "empty" - the card says so for a pasted change.
    source: str = "jarvis"

    def detail(self) -> dict:
        """What the gate records - no file contents."""
        return {"project": self.project, "files": len(self.files)}


def plan_merge(name: str, task: str) -> MergePlan:
    tdir = task_dir(name, task)
    meta = _read_json(_task_meta_path(name, task))
    plan = MergePlan(project=name, task=task, title=meta.get("title", ""),
                     source=meta.get("source") if meta.get("source") in SOURCES else "jarvis")
    if not tdir.is_dir():
        plan.refused = "that task is gone - it was merged or thrown away"
        return plan
    proj = project_dir(name)
    d = diff(name, task)
    plan.files, plan.diff = d["files"], d["diff"]
    plan.head = _git(["rev-parse", _branch(task)], proj).stdout.strip()
    plan.main = _git(["rev-parse", "main"], proj).stdout.strip()
    if not plan.files:
        plan.refused = "this task has not changed anything yet"
    elif len(plan.diff) > MAX_CARD_DIFF_CHARS:
        n = len(plan.files)
        plan.refused = (f"this change is too big to show on one card ({n} "
                        f"file{'s' if n != 1 else ''}) - ask Jarvis to split it into "
                        "smaller steps")
    return plan


def describe(plan: MergePlan) -> str:
    """The approval card's words: every file, then the whole comparison."""
    if plan.refused:
        return f"Nothing to approve for {plan.project}: {plan.refused}."
    lines = [f"Add Jarvis's change to your app \"{plan.project}\": {plan.title}", ""]
    if plan.source == "pasted":
        # The owner typed this, not Jarvis: the card must never say otherwise.
        lines += [PASTED_LINE, ""]
    lines.append(f"{len(plan.files)} file(s):")
    for f in plan.files:
        lines.append(f"  {f['path']}  (+{f['added']} -{f['removed']})")
    lines += ["", "Nothing is run: this only changes the app's files. "
              "Saying no keeps the change aside, and your app stays as it is.",
              "", "The full change:", "", plan.diff]
    return "\n".join(lines)


def run_merge(plan: MergePlan, approved: bool = False) -> dict:
    if not approved:
        return {"ok": False, "error": "not approved"}
    if plan.refused:
        return {"ok": False, "error": plan.refused, "why": "refused"}
    proj, tdir = project_dir(plan.project), task_dir(plan.project, plan.task)
    with _LOCK:
        if not tdir.is_dir():
            return {"ok": False, "error": "that task is gone - it was merged or thrown away",
                    "why": "gone"}
        head = _git(["rev-parse", _branch(plan.task)], proj).stdout.strip()
        main = _git(["rev-parse", "main"], proj).stdout.strip()
        if head != plan.head or main != plan.main:
            return {"ok": False, "error": "the app changed after the card was shown, so "
                                          "nothing was merged - look at the new card",
                    "why": "stale"}
        if _git(["status", "--porcelain"], proj).stdout.strip():
            return {"ok": False, "error": "the app's own folder has changes that are not "
                                          "saved in git, so nothing was merged",
                    "why": "unsaved"}
        out = _git(["merge", "--no-ff", "--no-edit", "-m",
                    f"Jarvis: {plan.title}"[:200], _branch(plan.task)], proj, check=False)
        if out.returncode != 0:
            _git(["merge", "--abort"], proj, check=False)
            return {"ok": False, "error": "the change could not be merged cleanly; "
                                          "nothing was changed", "why": "conflict"}
    discard(plan.project, plan.task)
    _audit("app_change_merged", {"files": len(plan.files)})
    return {"ok": True, "files": len(plan.files)}


# --------------------------------------------------------------------------
#   Small helpers
# --------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
