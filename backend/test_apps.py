"""test_apps.py - an app inside a project: its tasks and the merge card
(jarvis_apps.py, apps-in-projects.patch, docs/JARVIS-API.md section 92,
docs/APPS-IN-PROJECTS-DESIGN.md).

    python3 backend/test_apps.py

The owner's decision (CLAUDE.md, 2026-09-28 and 2026-09-29): the app builder's
projects join Projects; the first slice is the screens, the merge card and
pasting a change in on the PC - no model tool, no running commands. What this
proves, with REAL git in a temporary settings folder, real SQLite files, and a
fake approval gate (no socket opens - a guard fails the suite if one does):

  - the routes and every status and sentence of the frozen API (7.1): 400
    (bad field, nothing to merge, too big), 403 pc_only, 404, 409 (limit, a
    card waiting), 503 (git missing, tier not ask); never a stack trace;
  - the views: the short `app` in the list, the whole one in a project, a
    task's summary and whole change, git missing, the folder gone;
  - starting a task (no card, the open-task cap), pasting a change in (THIS
    PC only, safe paths, files git keeps out do not count, the card then says
    the owner pasted it), discarding one (also one whose copy is gone);
  - the merge card: ONE, at tier ask, its words exactly the workspace's
    describe() (every file, the whole change up to the cap, the pasted line),
    its detail keys, one at a time per app, the answer table (merged, denied,
    timed out, stale, unsaved, conflict, withdrawn, refused, failed), what
    lands is exactly what was shown, and nothing changes when anything moved;
  - discarding withdraws a waiting card; deleting a project withdraws it and
    keeps the folder; a restart drops a waiting card and keeps the task;
  - git only ever sees the allowlisted environment; the audit log carries
    counts, never a path or a line of code;
  - the wiring: the patch on the stack of earlier patches, the risk table
    line (risky, so Windows Hello and the screen lock), the tier line, the
    lists it must be in and out of, and the two apps' shared contract file.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_apps.py", "jarvis_projects.py", "jarvis_app_workspace.py",
                "jarvis_child_env.py")

if shutil.which("git") is None:
    print("SKIP  git is not installed here - these tests run real git")
    sys.exit(0)

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-apps-in-projects-"))
_AUDIT = []
_TIER = {"app_merge_change": "ask"}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: _AUDIT.append((event, detail))
fw.action_tier = lambda action: _TIER.get(action, "ask")
sys.modules["jarvis_framework"] = fw
os.environ["JARVIS_TEST_FAKE_TOKEN"] = "must-not-reach-git"

_NET = []
_real_connect = socket.socket.connect


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_apps.py: no network")


socket.socket.connect = _no_connect

import jarvis_app_workspace as W  # noqa: E402
import jarvis_apps as A  # noqa: E402
import jarvis_projects as P  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


_N = [0]


class Said:
    """What the approval gate hands back."""

    def __init__(self, outcome="approved", tier="ask", allowed=None, reason=""):
        self.outcome = outcome
        self.tier = tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = reason


class Gate:
    """A fake approval gate: records every card, answers as told. `before`
    runs while the card is 'up', before the owner 'answers' - where a test
    moves the app under the card."""

    def __init__(self, answer=None, before=None, raises=None):
        self.calls = []
        self.answer = answer if answer is not None else Said()
        self.before = before
        self.raises = raises

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        if self.before:
            self.before()
        if self.raises:
            raise self.raises
        return self.answer


def now_spawn(fn):
    fn()


class Held:
    """A spawn that keeps the card's work to run later - the card is 'up'."""

    def __init__(self):
        self.fns = []

    def __call__(self, fn):
        self.fns.append(fn)


def ask(**kw):
    return dict(tier_of=lambda a: _TIER.get(a, "ask"), **kw)


def _rmtree(path):
    """shutil.rmtree that can also delete what git wrote. Git marks its object
    files READ-ONLY, and Windows refuses to unlink a read-only file - POSIX does
    not care, so a plain rmtree works in CI and raised PermissionError on the
    owner's PC (2026-10-03). Clear the bit first, then remove."""
    for dirpath, dirnames, filenames in os.walk(path):
        for name in list(dirnames) + list(filenames):
            try:
                os.chmod(os.path.join(dirpath, name), stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


def fresh():
    """A new store, no app folders, no card state."""
    _N[0] += 1
    # NOT plain rmtree(ignore_errors=True): git's object files are read-only and
    # Windows refuses to unlink them, so the old app folders survived and the
    # next app of the same name came out as "notes-app-3" (2026-10-03).
    _rmtree(W.root())
    A._reset_for_tests()
    return P.Projects(_TMP / f"projects-{_N[0]}.db")


def make(store=None, name="Notes app", kind="web"):
    s = store or fresh()
    code, body = P.handle_post("/api/projects", {"name": name, "kind": "coding",
                                                 "app": {"type": kind}}, store=s)
    assert code == 200, body
    p = body["project"]
    return s, p["id"], p["app"]["name"]


def route(pid, tail=""):
    return f"/api/projects/{pid}/app/tasks" + tail


def start(s, pid, title="A change"):
    code, body = A.handle_post(route(pid), {"title": title}, store=s)
    assert code == 200, body
    return body["task"]["task"]


def paste(s, pid, task, *files, here=True):
    blocks = "".join(f"<<<FILE {p}>>>\n{c}\n<<<END>>>\n" for p, c in files)
    return A.handle_post(route(pid, f"/{task}/files"), {"blocks": blocks}, here=here, store=s)


def merge(s, pid, task, gate=None, spawn=now_spawn, **kw):
    gate = gate or Gate()
    return A.handle_post(route(pid, f"/{task}/merge"), {}, store=s, gate=gate,
                         spawn=spawn, **ask(**kw)), gate


def last(app):
    return A._last(app)


def main_files(app):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"],
                         cwd=str(W.project_dir(app)), capture_output=True, text=True).stdout
    return sorted(out.split())


def show(app, path):
    return subprocess.run(["git", "show", f"main:{path}"], cwd=str(W.project_dir(app)),
                          capture_output=True, text=True).stdout


def ready(s, pid, files=(("a.txt", "one"),), title="A change"):
    task = start(s, pid, title)
    code, body = paste(s, pid, task, *files)
    assert code == 200, body
    return task


# --------------------------------------------------------------------------
#   Small pieces
# --------------------------------------------------------------------------


def t_slug():
    check("a name becomes a folder name: lower-case, runs of other characters one dash",
          A.slug("Notes App!") == "notes-app" and A.slug("  My  very -- cool_app  ") ==
          "my-very-cool-app")
    check("nothing left gives `app`", A.slug("???") == "app" and A.slug("") == "app"
          and A.slug(None) == "app" and A.slug("日本語") == "app")
    long = A.slug("x" * 80)
    check("at most 40 characters, and it starts and ends with a letter or digit",
          len(long) == 40 and W.check_name(long) == long)
    check("a name that ends in a dash after cutting has it removed",
          not A.slug("a" * 39 + " b").endswith("-"), A.slug("a" * 39 + " b"))
    check("taken names get -2, -3 ...", A.slug("notes", {"notes"}) == "notes-2"
          and A.slug("notes", {"notes", "notes-2"}) == "notes-3")
    check("-2 still fits in 40 characters", len(A.slug("y" * 80, {"y" * 40})) <= 40
          and A.slug("y" * 80, {"y" * 40}).endswith("-2"))
    check("every slug passes the workspace's own name check",
          all(W.check_name(A.slug(n)) for n in ("Notes", "9 lives", "a", "-x-", "A.B.C")))


def t_the_route_table():
    pr = A.parse_route
    pid, task = "1" * 32, "a" * 12
    check("the route table", pr(f"/api/projects/{pid}/app/tasks") == ("tasks", pid)
          and pr(f"/api/projects/{pid}/app/tasks/{task}") == ("task", pid, task)
          and pr(f"/api/projects/{pid}/app/tasks/{task}/files") == ("files", pid, task)
          and pr(f"/api/projects/{pid}/app/tasks/{task}/merge") == ("merge", pid, task)
          and pr(f"/api/projects/{pid}/app/tasks/{task}/discard") == ("discard", pid, task))
    check("the projects module's own routes are not ours (and ours are not its)",
          pr("/api/projects") is None and pr(f"/api/projects/{pid}") is None
          and pr(f"/api/projects/{pid}/delete") is None
          and pr(f"/api/projects/{pid}/benchmarks") is None
          and P.parse_route(f"/api/projects/{pid}/app/tasks") is None
          and P.parse_route(f"/api/projects/{pid}/app/tasks/{task}/merge") is None)
    check("anything else is not ours", pr(f"/api/projects/{pid}/app") is None
          and pr(f"/api/projects/{pid}/app/tasks/{task}/run") is None
          and pr(f"/api/projects/{pid}/app/tasks/{task}/merge/x") is None
          and pr(f"/api/projects/{pid}/apps/tasks") is None and pr("/api/goals") is None
          and pr(f"/api/projects/{pid}/app/tasks/") is None and pr(None) is None)


def t_the_shared_sentences():
    frozen = {
        "merged": "Added to your app.",
        "denied": "Not added - you said no. The change is kept aside.",
        "timed_out": "Not added - the card timed out. The change is kept aside.",
        "stale": "Not added - the app or the change moved after the card was shown. Look at "
                 "the new card.",
        "unsaved": "Not added - the app's own folder has changes that are not saved in git.",
        "conflict": "Not added - the change did not fit the app's newer version. Nothing was "
                    "changed; discard it and ask again.",
        "withdrawn": "Not added - the change was thrown away before you answered.",
        "refused": "Not added.",
        "failed": "Not added - something went wrong. Nothing was changed.",
    }
    check("the nine outcome sentences are the frozen table, word for word",
          A.OUTCOME_WORDS == frozen, A.OUTCOME_WORDS)
    check("a card waiting says it in the frozen words", A.CARD_WAITING ==
          "A card for this app is already waiting - answer it first.")
    check("the pasted line is the frozen sentence",
          W.PASTED_LINE == "You pasted this change in on your PC.")
    check("limits: 120-character title, 2,000,000-character paste, 10 open tasks, 60,000-"
          "character card", (A.MAX_TITLE, A.MAX_BLOCKS_CHARS, W.MAX_OPEN_TASKS,
                             W.MAX_CARD_DIFF_CHARS) == (120, 2_000_000, 10, 60_000))


# --------------------------------------------------------------------------
#   Who is an app, and what a refusal says
# --------------------------------------------------------------------------


def t_only_an_app_project_has_tasks():
    s = fresh()
    life = P.handle_post("/api/projects", {"name": "Run", "kind": "life"},
                         store=s)[1]["project"]["id"]
    folder = P.handle_post("/api/projects", {"name": "Mine", "kind": "coding"},
                           store=s)[1]["project"]["id"]
    for what, pid in (("a life project", life), ("a coding project with no app", folder)):
        code, body = A.handle_post(route(pid), {"title": "x"}, store=s)
        check(f"{what}: starting a task is a 404 in plain words",
              code == 404 and body == {"ok": False, "error": "This project is not an app."},
              body)
        code, body = A.handle_get(route(pid, "/" + "a" * 12), store=s)
        check(f"{what}: reading a task is a 404", code == 404, body)
    code, body = A.handle_post(route("f" * 32), {"title": "x"}, store=s)
    check("no such project: 404", code == 404 and body == {"ok": False, "error":
                                                           "No such project."}, body)
    code, body = A.handle_post(route("not-an-id"), {"title": "x"}, store=s)
    check("a project id that is not an id: 404, not a crash", code == 404, body)
    s, pid, app = make(s)
    code, body = A.handle_post(route(pid), [], store=s)
    check("a body that is not an object: 400", code == 400 and body["ok"] is False, body)
    code, body = A.handle_get("/api/projects/x/nothing", store=s)
    check("a route that is not ours: 404", code == 404, body)
    code, body = A.handle_get(route(pid), store=s)
    check("GET on the list of tasks: 405, use POST", code == 405, body)
    code, body = A.handle_post(route(pid, "/" + "a" * 12), {}, store=s)
    check("POST on one task: 405, use GET", code == 405, body)


# --------------------------------------------------------------------------
#   Starting a task, the views
# --------------------------------------------------------------------------


def t_start_a_task():
    s, pid, app = make()
    code, body = A.handle_post(route(pid), {"title": "Add a dark mode"}, store=s)
    t = body.get("task", {})
    check("starting a task: 200, the frozen summary shape, no card",
          code == 200 and body["ok"] is True and set(t) == {
              "task", "title", "started", "source", "files", "added", "removed",
              "older_main", "waiting"}, body)
    check("a task started here is 'empty' with nothing in it",
          (t["source"], t["files"], t["added"], t["removed"], t["older_main"], t["waiting"])
          == ("empty", 0, 0, 0, False, False) and len(t["task"]) == 12
          and isinstance(t["started"], float), t)
    check("its own copy exists, and main was not touched",
          W.task_dir(app, t["task"]).is_dir() and main_files(app) ==
          [".gitignore", ".jarvis-app.json", "README.md"])
    for bad, why in (({"title": ""}, "empty"), ({"title": "   "}, "blank"), ({}, "missing"),
                     ({"title": "x" * 121}, "too long"), ({"title": 5}, "not text"),
                     ({"title": "a\nb"}, "two lines")):
        code, body = A.handle_post(route(pid), bad, store=s)
        check(f"a title that is {why}: 400 with a sentence",
              code == 400 and body["ok"] is False and body["error"].endswith("."), body)
    code, body = A.handle_post(route(pid), {"title": "x" * 120}, store=s)
    check("a title of exactly 120 characters is taken", code == 200, body)
    s2, pid2, app2 = make(fresh(), "Capped")
    for n in range(W.MAX_OPEN_TASKS):
        start(s2, pid2, f"Task {n}")
    code, body = A.handle_post(route(pid2), {"title": "One too many"}, store=s2)
    check("an eleventh open task: 409, in plain words",
          code == 409 and "already has 10 open tasks" in body["error"], body)
    check("... and no eleventh copy was made", len(W.list_tasks(app2)) == 10)
    old = A._git_present
    A._git_present = lambda: False
    try:
        code, body = A.handle_post(route(pid2), {"title": "x"}, store=s2)
    finally:
        A._git_present = old
    check("git missing: 503 with the sentence, not a stack trace",
          code == 503 and body["error"].startswith("Git is not installed on this PC")
          and "Traceback" not in json.dumps(body), body)


def t_the_app_in_a_project():
    s, pid, app = make(fresh(), "Notes app", "web")
    short = s.list()[0]["app"]
    check("the list carries the short app: name, type, open tasks, card waiting",
          short == {"name": "notes-app", "type": "web", "tasks": 0, "merge_waiting": False},
          short)
    full = s.get(pid)["app"]
    check("a project carries the whole app: exactly the frozen keys",
          set(full) == {"name", "type", "title", "git_ok", "said", "main", "tasks", "merge"}
          and set(full["main"]) == {"head", "subject", "at", "versions"}
          and set(full["merge"]) == {"waiting", "last"}, full)
    check("a new app: its title, git fine, one saved version, no tasks, no card",
          (full["title"], full["git_ok"], full["said"], full["tasks"]) ==
          ("Notes app", True, "", []) and full["main"]["versions"] == 1
          and full["main"]["subject"] == "Start Notes app"
          and len(full["main"]["head"]) == 7 and isinstance(full["main"]["at"], float)
          and full["merge"] == {"waiting": None, "last": None}, full)
    life = P.handle_post("/api/projects", {"name": "Run", "kind": "life"},
                         store=s)[1]["project"]
    check("a project that is not an app has app: null, in the list and whole",
          life["app"] is None and s.get(life["id"])["app"] is None
          and [x["app"] for x in s.list()][1] is None)
    first = ready(s, pid, (("a.txt", "one"),), "First")
    second = start(s, pid, "Second")
    time.sleep(0.02)
    third = start(s, pid, "Third")
    tasks = s.get(pid)["app"]["tasks"]
    check("open tasks, oldest first",
          [t["task"] for t in tasks] == [first, second, third], tasks)
    check("a task's summary counts its files and lines",
          (tasks[0]["files"], tasks[0]["added"], tasks[0]["removed"], tasks[0]["source"])
          == (1, 1, 0, "pasted") and tasks[1]["source"] == "empty", tasks)
    check("the short form counts the open tasks", s.list()[0]["app"]["tasks"] == 3)
    check("no task is older than main yet", not any(t["older_main"] for t in tasks))
    code, body = merge(s, pid, first)[0]
    check("merging the first: 202", code == 202, body)
    tasks = s.get(pid)["app"]["tasks"]
    check("a task made before another change landed says so (older_main); the merged one is gone",
          [(t["task"], t["older_main"]) for t in tasks] == [(second, True), (third, True)],
          tasks)
    check("the app's latest version is the merge, and there is one more version",
          s.get(pid)["app"]["main"]["subject"] == "Jarvis: First"
          and s.get(pid)["app"]["main"]["versions"] == 3)


def t_git_missing_and_the_folder_gone():
    s, pid, app = make(fresh(), "Gitless")
    old = A._git_present
    A._git_present = lambda: False
    try:
        full = s.get(pid)["app"]
        short = s.list()[0]["app"]
        code, body = A.handle_get(route(pid, "/" + "a" * 12), store=s)
        code2, body2 = merge(s, pid, "a" * 12)[0]
    finally:
        A._git_present = old
    check("git missing: git_ok false, the sentence, no tasks, no main",
          full["git_ok"] is False and full["said"].startswith("Git is not installed on this PC")
          and full["tasks"] == [] and full["main"] is None and full["name"] == "gitless", full)
    check("... the list still answers, without git", short["name"] == "gitless")
    check("... reading a task and merging are 503",
          code == 503 and code2 == 503 and "Git is not installed" in body["error"]
          and "Git is not installed" in body2["error"], (body, body2))
    _rmtree(W.project_dir(app))
    full = s.get(pid)["app"]
    check("an app whose folder was deleted by hand: git_ok false and a sentence, no crash",
          full["git_ok"] is False and "folder is missing" in full["said"]
          and full["tasks"] == [] and full["main"] is None, full)
    check("... and the list still answers", s.list()[0]["app"]["name"] == "gitless")


# --------------------------------------------------------------------------
#   A task's whole change
# --------------------------------------------------------------------------


def t_a_tasks_whole_change():
    s, pid, app = make()
    task = ready(s, pid, (("src/App.tsx", "export default 1;"), ("README.md", "# New")),
                 "Two files")
    code, body = A.handle_get(route(pid, f"/{task}"), store=s)
    t = body["task"]
    check("the detail is the summary plus list, diff, too_big, refused",
          code == 200 and set(t) == {"task", "title", "started", "source", "files", "added",
                                     "removed", "older_main", "waiting", "list", "diff",
                                     "too_big", "refused"}, body)
    check("the list names each file with counts as strings, as the workspace gives them",
          sorted(t["list"], key=lambda f: f["path"]) == [
              {"path": "README.md", "added": "1", "removed": "3"},
              {"path": "src/App.tsx", "added": "1", "removed": "0"}], t["list"])
    check("the diff is the whole comparison, verbatim",
          t["diff"] == W.diff(app, task)["diff"] and "+export default 1;" in t["diff"]
          and "-# " in t["diff"] and t["too_big"] is False and t["refused"] == "")
    check("the summary counts add up", (t["files"], t["added"], t["removed"]) == (2, 2, 3))
    empty = start(s, pid, "Empty")
    t = A.handle_get(route(pid, f"/{empty}"), store=s)[1]["task"]
    check("an empty task: no files, no diff, and the sentence that says why no card",
          t["list"] == [] and t["diff"] == "" and t["too_big"] is False
          and t["refused"] == "This task has not changed anything yet.", t)
    big = start(s, pid, "Huge")
    paste(s, pid, big, ("big.txt", "\n".join(f"line {i} " + "y" * 50 for i in range(1300))))
    code, body = A.handle_get(route(pid, f"/{big}"), store=s)
    t = body["task"]
    check("a change over 60,000 characters: too_big, no diff sent, the refusal sentence",
          t["too_big"] is True and t["diff"] == "" and "too big to show on one card" in
          t["refused"] and "split it into smaller steps" in t["refused"] and
          t["list"][0]["path"] == "big.txt", {k: t[k] for k in ("too_big", "refused")})
    for bad in ("f" * 12, "nope", "A" * 12, "a" * 11):
        code, body = A.handle_get(route(pid, f"/{bad}"), store=s)
        check(f"a task id {bad!r} that is not a task: 404", code == 404
              and body == {"ok": False, "error": "No such task."}, body)


# --------------------------------------------------------------------------
#   Pasting a change in: this PC only
# --------------------------------------------------------------------------


def t_paste_is_this_pc_only():
    s, pid, app = make()
    task = start(s, pid)
    code, body = paste(s, pid, task, ("a.txt", "x"), here=False)
    check("from another device: 403 pc_only, and nothing written",
          code == 403 and body["pc_only"] is True and body["ok"] is False and
          body["error"] == "A change is pasted in on the PC only." and
          not (W.task_dir(app, task) / "a.txt").exists(), body)
    for what, request in (("a body with no blocks", {}), ("blocks that are not text",
                                                          {"blocks": 5}),
                          ("a task that is not there", None)):
        target = task if request is not None else "f" * 12
        code, body = A.handle_post(route(pid, f"/{target}/files"), request or {"blocks": "x"},
                                   here=False, store=s)
        check(f"{what}, from another device: still 403 (the PC-only rule comes first)",
              code == 403 and body["pc_only"] is True, body)
    check("a stranger cannot paste by claiming nothing: here defaults to not the PC",
          A.handle_post(route(pid, f"/{task}/files"), {"blocks": "<<<FILE a.txt>>>\nx\n<<<END>>>"},
                        store=s)[0] == 403)
    code, body = paste(s, pid, task, ("a.txt", "x"), here=True)
    check("on the PC: 200", code == 200, body)
    code, body = merge(s, pid, task, Gate(), now_spawn)[0]
    check("merging is NOT PC only: another device may ask for the card",
          code == 202 and body["waiting"] is True, body)


def t_paste_reads_blocks_and_refuses_bad_ones():
    s, pid, app = make()
    task = start(s, pid)
    code, body = paste(s, pid, task, ("src/App.tsx", "export default 1;"),
                       ("docs/notes.md", "# Notes"))
    t = body["task"]
    check("a paste: 200, the whole task back, the owner's files in it",
          code == 200 and t["files"] == 2 and t["source"] == "pasted" and
          [f["path"] for f in t["list"]] == ["docs/notes.md", "src/App.tsx"], body)
    check("the files are in the task's copy only, main is untouched",
          (W.task_dir(app, task) / "src" / "App.tsx").read_text() == "export default 1;\n"
          and "src/App.tsx" not in main_files(app))
    code, body = A.handle_post(route(pid, f"/{task}/files"),
                               {"blocks": "here you go, no blocks"}, here=True, store=s)
    check("no blocks: 400 with the frozen sentence", code == 400 and
          body["error"] == "No <<<FILE>>> blocks were found.", body)
    for bad in ("../escape.txt", "/etc/passwd", "C:/x.txt", "a\\b.txt", ".git/hooks/pre-commit",
                "src/.git/x", "con.txt", "src/NUL", "trailing.", ".jarvis-app.json", "a/../../x"):
        code, body = paste(s, pid, task, (bad, "x"))
        check(f"a path {bad!r}: refused with 400, nothing written",
              code == 400 and body["ok"] is False and body["error"].endswith("."), body)
    check("none of those paths reached the disk",
          not list(_TMP.rglob("escape.txt")) and not list(_TMP.rglob("passwd"))
          and not list(_TMP.rglob("x.txt")) and not list(_TMP.rglob("pre-commit")))
    code, body = paste(s, pid, task, ("ok.txt", "fine"), ("../bad.txt", "x"))
    check("one bad path in a paste refuses the whole paste",
          code == 400 and not (W.task_dir(app, task) / "ok.txt").exists(), body)
    code, body = A.handle_post(route(pid, f"/{task}/files"),
                               {"blocks": "<<<FILE big.txt>>>\n" + "x" * 600_000 + "\n<<<END>>>"},
                               here=True, store=s)
    check("a file over 512 KB: 400", code == 400 and "larger than 512 KB" in body["error"], body)
    code, body = A.handle_post(route(pid, f"/{task}/files"),
                               {"blocks": "x" * (A.MAX_BLOCKS_CHARS + 1)}, here=True, store=s)
    check("a paste over 2,000,000 characters: 400", code == 400
          and "2,000,000" in body["error"], body)
    code, body = A.handle_post(route(pid, f"/{'f' * 12}/files"),
                               {"blocks": "<<<FILE a.txt>>>\nx\n<<<END>>>"}, here=True, store=s)
    check("a task that is not there: 404", code == 404, body)
    code, body = A.handle_post(route(pid, f"/{task}/files"), {"blocks": [1]}, here=True,
                               store=s)
    check("blocks that are not text: 400", code == 400, body)
    blocks = "".join(f"<<<FILE f{i}.txt>>>\nx\n<<<END>>>\n" for i in range(W.MAX_CHANGE_FILES + 1))
    code, body = A.handle_post(route(pid, f"/{task}/files"), {"blocks": blocks}, here=True,
                               store=s)
    check("more than 200 files in one paste: 400", code == 400 and "200" in body["error"], body)
    code, body = A.handle_post(route(pid, f"/{task}/files"),
                               {"blocks": "<<<DELETE nothing-here.txt>>>"}, here=True, store=s)
    check("deleting a file that is not there: 400", code == 400
          and "not there to delete" in body["error"], body)
    code, body = A.handle_post(route(pid, f"/{task}/files"),
                               {"blocks": "<<<DELETE README.md>>>"}, here=True, store=s)
    check("a delete block works (the file is removed in the task only)",
          code == 200 and "README.md" in [f["path"] for f in body["task"]["list"]]
          and "README.md" in main_files(app), body)


def t_files_git_keeps_out_do_not_count():
    s, pid, app = make()
    task = start(s, pid)
    code, body = paste(s, pid, task, (".env", "SECRET=1"))
    check("only a .env: 400, the plain sentence, and the task is still empty",
          code == 400 and body["error"].startswith("Nothing in that paste would change the app")
          and A.handle_get(route(pid, f"/{task}"), store=s)[1]["task"]["source"] == "empty",
          body)
    code, body = paste(s, pid, task, (".env", "SECRET=2"), ("dist/out.js", "x"),
                       ("kept.txt", "kept"))
    check("a .env, a dist/ file and one real file: the change is the one real file",
          code == 200 and [f["path"] for f in body["task"]["list"]] == ["kept.txt"], body)
    code, body = paste(s, pid, task, ("kept.txt", "kept"))
    check("writing a file exactly as it already is: 400, nothing to change",
          code == 400 and "Nothing in that paste" in body["error"], body)


def t_a_paste_makes_the_whole_task_pasted():
    s, pid, app = make()
    made = W.start_task(app, "Jarvis's own", source="jarvis")["task"]
    W.apply_change(app, made, [("write", "j.txt", "by jarvis\n")], "Jarvis wrote it")
    check("a task Jarvis wrote says so", A.handle_get(
        route(pid, f"/{made}"), store=s)[1]["task"]["source"] == "jarvis")
    paste(s, pid, made, ("p.txt", "typed"))
    t = A.handle_get(route(pid, f"/{made}"), store=s)[1]["task"]
    check("after the owner pastes into it, the whole task is 'pasted'", t["source"] == "pasted")
    held = Held()
    (code, body), gate = merge(s, pid, made, Gate(), held)
    held.fns[0]()
    check("... so its card never claims Jarvis wrote what the owner typed",
          W.PASTED_LINE in gate.calls[0][2])


def t_paste_cannot_change_a_task_under_its_card():
    s, pid, app = make()
    first = ready(s, pid, (("a.txt", "one"),), "First")
    other = ready(s, pid, (("b.txt", "two"),), "Other")
    held = Held()
    (code, body), gate = merge(s, pid, first, Gate(), held)
    check("a card is raised for the first", code == 202 and len(held.fns) == 1)
    code, body = paste(s, pid, first, ("c.txt", "three"))
    check("pasting into the task the card waits for: 409, nothing written",
          code == 409 and body["error"] == "A card for this change is waiting - answer it "
          "first." and not (W.task_dir(app, first) / "c.txt").exists(), body)
    code, body = paste(s, pid, other, ("d.txt", "four"))
    check("pasting into another task of the app is fine", code == 200, body)
    t = A.handle_get(route(pid, f"/{first}"), store=s)[1]["task"]
    check("the waiting task says so", t["waiting"] is True and s.get(pid)["app"]["merge"]
          ["waiting"] == first and s.list()[0]["app"]["merge_waiting"] is True)
    check("... and the other does not", A.handle_get(
        route(pid, f"/{other}"), store=s)[1]["task"]["waiting"] is False)


# --------------------------------------------------------------------------
#   The merge card
# --------------------------------------------------------------------------


def t_the_card_is_exactly_the_workspaces_words():
    s, pid, app = make(fresh(), "Notes app")
    task = ready(s, pid, (("src/App.tsx", "export default function App() {}"),
                          ("src/theme.css", "body { color: red; }"),
                          ("README.md", "# Notes")), "Dark mode")
    plan = W.plan_merge(app, task)
    want = W.describe(plan)
    (code, body), gate = merge(s, pid, task, Gate(), now_spawn)
    check("merging: 202 waiting true, and a message that says nothing changes unless approved",
          code == 202 and body["ok"] is True and body["waiting"] is True and
          "stays as it is unless you approve" in body["message"], body)
    check("exactly ONE card was raised, for app_merge_change", len(gate.calls) == 1
          and gate.calls[0][0] == "app_merge_change", gate.calls)
    action, detail, prompt = gate.calls[0]
    check("the card's words are describe(plan), word for word", prompt == want == detail["text"])
    check("the detail has exactly the frozen keys",
          set(detail) == {"text", "what", "project", "app", "files", "leaves_this_pc"}, detail)
    check("... what, the project's name, the app's folder, the file count, nothing leaves the PC",
          detail["what"] == "add one change to your app" and detail["project"] == "Notes app"
          and detail["app"] == "notes-app" and detail["files"] == 3
          and detail["leaves_this_pc"] is False, detail)
    check("the card names every file with its counts",
          all(f"  {f['path']}  (+{f['added']} -{f['removed']})" in prompt
              for f in plan.files) and "3 file(s):" in prompt, prompt)
    check("the card shows the whole change, in full", plan.diff in prompt
          and "export default function App() {}" in prompt and "color: red" in prompt)
    check("the card says nothing is run and no keeps the app as it is",
          "Nothing is run: this only changes the app's files. Saying no keeps the change "
          "aside, and your app stays as it is." in prompt)
    check("the card says the owner pasted it", "You pasted this change in on your PC." in prompt)
    check("the gate's audit detail carries counts, not text",
          plan.detail() == {"project": "notes-app", "files": 3}, plan.detail())


def t_the_card_carries_a_change_up_to_the_cap():
    s, pid, app = make()
    task = start(s, pid, "Nearly too big")
    lines = "\n".join(f"line {i} " + "z" * 40 for i in range(1000))
    paste(s, pid, task, ("big.txt", lines))
    plan = W.plan_merge(app, task)
    check("the test change is big but under the cap", 20_000 < len(plan.diff) <
          W.MAX_CARD_DIFF_CHARS and not plan.refused, len(plan.diff))
    held = Held()
    (code, body), gate = merge(s, pid, task, Gate(), held)
    held.fns[0]()
    card = gate.calls[0][2]
    check("the card is raised (202) and carries the whole change: every line, none cut",
          code == 202 and plan.diff in card and "line 999 " in card and "line 0 " in card
          and card.endswith(plan.diff), body)


def t_no_card_when_there_is_nothing_to_decide():
    s, pid, app = make()
    empty = start(s, pid, "Empty")
    (code, body), gate = merge(s, pid, empty, Gate(), now_spawn)
    check("an empty task: 400 with the sentence, and NO card",
          code == 400 and body == {"ok": False, "error": "This task has not changed anything "
                                                        "yet."} and gate.calls == [], body)
    check("... and nothing waits", A._waiting_task(app) is None and last(app) is None)
    big = start(s, pid, "Huge")
    paste(s, pid, big, ("big.txt", "\n".join(f"line {i} " + "y" * 50 for i in range(1300))))
    (code, body), gate = merge(s, pid, big, Gate(), now_spawn)
    check("a change over the cap: 400 'split it', and NO card",
          code == 400 and "too big to show on one card" in body["error"]
          and "split it into smaller steps" in body["error"] and gate.calls == [], body)
    (code, body), gate = merge(s, pid, "f" * 12, Gate(), now_spawn)
    check("a task that is not there: 404, no card", code == 404 and gate.calls == [], body)
    life = P.handle_post("/api/projects", {"name": "Run", "kind": "life"},
                         store=s)[1]["project"]["id"]
    (code, body), gate = merge(s, life, "a" * 12, Gate(), now_spawn)
    check("a project that is not an app: 404, no card", code == 404 and gate.calls == [])


def t_the_tier_must_be_ask():
    s, pid, app = make()
    task = ready(s, pid)
    for tier in ("auto", "notify", "deny", "confirm"):
        _TIER["app_merge_change"] = tier
        try:
            spawned = Held()
            (code, body), gate = merge(s, pid, task, Gate(), spawned)
        finally:
            _TIER["app_merge_change"] = "ask"
        check(f"tier {tier!r} in the settings file: 503 naming the line, no card, no thread",
              code == 503 and "must be 'ask'" in body["error"] and gate.calls == []
              and spawned.fns == [] and A._waiting_task(app) is None, body)
    check("nothing was merged", "a.txt" not in main_files(app))


def t_one_card_at_a_time():
    s, pid, app = make()
    first = ready(s, pid, (("a.txt", "one"),), "First")
    second = ready(s, pid, (("b.txt", "two"),), "Second")
    held = Held()
    (code, body), gate = merge(s, pid, first, Gate(), held)
    check("the first card is up: 202", code == 202)
    (code, body), gate2 = merge(s, pid, first, Gate(), Held())
    check("the same task again: 409 with the frozen sentence, no second card",
          code == 409 and body == {"ok": False, "error": A.CARD_WAITING} and gate2.calls == [],
          body)
    (code, body), gate3 = merge(s, pid, second, Gate(), Held())
    check("another task of the same app: 409 too", code == 409 and gate3.calls == [], body)
    s2, pid2, app2 = make(s, "Other app")
    other = ready(s, pid2, (("z.txt", "z"),), "Other")
    (code, body), gate4 = merge(s, pid2, other, Gate(), Held())
    check("a card for a DIFFERENT app is not blocked", code == 202, body)
    held.fns[0]()
    check("answering the first card (a yes) frees its app",
          A._waiting_task(app) is None and last(app)["outcome"] == "merged")
    check("... while the other app's card still waits", A._waiting_task(app2) == other)
    (code, body), gate5 = merge(s, pid, second, Gate(), Held())
    check("... and the next merge for the first app is 202", code == 202, body)


def t_a_spawn_that_fails_leaves_nothing_waiting():
    s, pid, app = make()
    task = ready(s, pid)

    def boom(fn):
        raise RuntimeError("no thread")

    (code, body), gate = merge(s, pid, task, Gate(), boom)
    check("a card that could not be raised: 503 in plain words, nothing waiting",
          code == 503 and body["error"] == "Could not raise the approval card."
          and A._waiting_task(app) is None, body)
    (code, body), gate = merge(s, pid, task, Gate(), Held())
    check("... so the next try works", code == 202, body)


def t_a_yes_lands_exactly_what_was_shown():
    s, pid, app = make(fresh(), "Notes app")
    task = ready(s, pid, (("src/App.tsx", "export default 1;"), ("notes.md", "# Hi")),
                 "Dark mode")
    before = main_files(app)
    (code, body), gate = merge(s, pid, task, Gate(Said("approved")), now_spawn)
    check("a yes: merged, with the fixed sentence",
          last(app)["outcome"] == "merged" and last(app)["message"] == "Added to your app."
          and last(app)["task"] == task and isinstance(last(app)["at"], float), last(app))
    check("the files landed, exactly as shown",
          main_files(app) == sorted(before + ["src/App.tsx", "notes.md"])
          and show(app, "src/App.tsx") == "export default 1;\n"
          and show(app, "notes.md") == "# Hi\n")
    check("the merge is one more version, named for the task",
          s.get(pid)["app"]["main"]["subject"] == "Jarvis: Dark mode"
          and s.get(pid)["app"]["main"]["versions"] == 3)
    check("the task is gone and its copy too",
          not W.task_dir(app, task).exists() and s.get(pid)["app"]["tasks"] == [])
    check("nothing waits any more", A._waiting_task(app) is None
          and s.get(pid)["app"]["merge"]["waiting"] is None
          and s.get(pid)["app"]["merge"]["last"]["outcome"] == "merged")
    check("the app's own folder is clean afterwards",
          not subprocess.run(["git", "status", "--porcelain"], cwd=str(W.project_dir(app)),
                             capture_output=True, text=True).stdout.strip())


def t_the_answers_that_are_not_a_yes():
    table = [
        ("denied", Said("denied"), "denied"),
        ("timed out", Said("timed_out"), "timed_out"),
        ("a yes at a tier that is not ask", Said("approved", tier="auto"), "refused"),
        ("allowed but not approved", Said("expired", allowed=True), "refused"),
        ("not allowed", Said("approved", allowed=False), "refused"),
        ("no answer at all", None, "refused"),
    ]
    for what, said, want in table:
        s, pid, app = make(fresh(), f"Case {want}")
        task = ready(s, pid)
        gate = Gate(said if said is not None else types.SimpleNamespace(tier="ask"))
        merge(s, pid, task, gate, now_spawn)
        got = last(app)
        check(f"{what}: outcome {want}, nothing merged, the task kept aside",
              got is not None and got["outcome"] == want and "a.txt" not in main_files(app)
              and W.task_dir(app, task).is_dir(), got)
        check(f"{what}: the words are the fixed sentence",
              got["message"].startswith(A.OUTCOME_WORDS[want]), got)
        check(f"{what}: nothing is waiting afterwards", A._waiting_task(app) is None)
    s, pid, app = make(fresh(), "Gate breaks")
    task = ready(s, pid)
    merge(s, pid, task, Gate(raises=RuntimeError("secret detail")), now_spawn)
    got = last(app)
    check("a gate that raises: refused, with the kind of error and no stack trace",
          got["outcome"] == "refused" and "RuntimeError" in got["message"]
          and "secret detail" not in got["message"] and "Traceback" not in got["message"], got)
    s, pid, app = make(fresh(), "Long reason")
    task = ready(s, pid)
    merge(s, pid, task, Gate(Said("expired", allowed=True, reason="x" * 500)), now_spawn)
    check("a refusal's reason is cut to 200 characters",
          len("Not added. ") + 150 < len(last(app)["message"]) <= len("Not added. ") + 200 + 1,
          len(last(app)["message"]))
    s, pid, app = make(fresh(), "Tier changes")
    task = ready(s, pid)
    tiers = iter(["ask", "auto"])
    A_tier = lambda a: next(tiers, "auto")  # noqa: E731
    code, body = A.handle_post(route(pid, f"/{task}/merge"), {}, store=s,
                               gate=Gate(Said("approved")), spawn=now_spawn, tier_of=A_tier)
    check("a settings file changed to a looser tier while the card was up: refused, "
          "not merged", last(app)["outcome"] == "refused" and "a.txt" not in main_files(app),
          last(app))


def t_a_failed_merge_step_is_failed_not_a_crash():
    s, pid, app = make()
    task = ready(s, pid)
    real = W.run_merge

    def bad(plan, approved=False):
        raise RuntimeError("disk on fire")

    W.run_merge = bad
    try:
        merge(s, pid, task, Gate(), now_spawn)
    finally:
        W.run_merge = real
    check("run_merge raising: outcome failed, the fixed sentence",
          last(app)["outcome"] == "failed" and last(app)["message"] ==
          "Not added - something went wrong. Nothing was changed.", last(app))


def t_stale_unsaved_conflict():
    # stale: the task moved between the card and the yes
    s, pid, app = make(fresh(), "Stale one")
    task = ready(s, pid, (("a.txt", "one"),))
    gate = Gate(before=lambda: W.apply_change(app, task, [("write", "sneaky.txt", "added late\n")],
                                              "Late"))
    merge(s, pid, task, gate, now_spawn)
    check("the task changed after the card: stale, and NOTHING merged (not even a.txt)",
          last(app)["outcome"] == "stale" and "a.txt" not in main_files(app)
          and "sneaky.txt" not in main_files(app) and W.task_dir(app, task).is_dir(), last(app))
    check("... the words tell the owner to look at the new card",
          "Look at the new card." in last(app)["message"])
    (code, body), gate = merge(s, pid, task, Gate(), now_spawn)
    card = gate.calls[0][2]
    check("the new card shows the late file too, and merges it",
          code == 202 and "sneaky.txt" in card and last(app)["outcome"] == "merged"
          and "sneaky.txt" in main_files(app), last(app))

    # stale: main moved (another task merged) between card and yes
    s, pid, app = make(fresh(), "Stale two")
    first = ready(s, pid, (("a.txt", "one"),), "First")
    second = ready(s, pid, (("b.txt", "two"),), "Second")
    gate = Gate(before=lambda: W.run_merge(W.plan_merge(app, second), approved=True))
    merge(s, pid, first, gate, now_spawn)
    check("main moved after the card: stale, and the first task did not land",
          last(app)["outcome"] == "stale" and "a.txt" not in main_files(app)
          and "b.txt" in main_files(app), last(app))

    # unsaved: the owner edited the app's own folder
    s, pid, app = make(fresh(), "Unsaved")
    task = ready(s, pid)
    scratch = W.project_dir(app) / "scratch.txt"
    gate = Gate(before=lambda: scratch.write_text("my own edit\n"))
    merge(s, pid, task, gate, now_spawn)
    check("changes in the app's own folder that are not saved: unsaved, nothing merged",
          last(app)["outcome"] == "unsaved" and "a.txt" not in main_files(app)
          and scratch.read_text() == "my own edit\n", last(app))
    check("... in the frozen words", last(app)["message"] ==
          "Not added - the app's own folder has changes that are not saved in git.")

    # conflict: two tasks changed the same file
    s, pid, app = make(fresh(), "Conflict")
    one = ready(s, pid, (("same.txt", "from one"),), "One")
    two = ready(s, pid, (("same.txt", "from two"),), "Two")
    merge(s, pid, one, Gate(), now_spawn)
    check("the first of two tasks on the same file merges", last(app)["outcome"] == "merged")
    check("the second one is marked as made before another change", any(
        t["task"] == two and t["older_main"] for t in s.get(pid)["app"]["tasks"]))
    merge(s, pid, two, Gate(), now_spawn)
    check("the second: conflict, and main is exactly what the first made it",
          last(app)["outcome"] == "conflict" and show(app, "same.txt") == "from one\n"
          and not subprocess.run(["git", "status", "--porcelain"],
                                 cwd=str(W.project_dir(app)), capture_output=True,
                                 text=True).stdout.strip(), last(app))
    check("... in the frozen words, and the task is kept to discard",
          last(app)["message"] == A.OUTCOME_WORDS["conflict"] and W.task_dir(app, two).is_dir())
    code, body = A.handle_post(route(pid, f"/{two}/discard"), {}, store=s)
    check("... and it can be discarded", code == 200 and not W.task_dir(app, two).exists())


# --------------------------------------------------------------------------
#   Discard, delete, restart
# --------------------------------------------------------------------------


def t_discard():
    s, pid, app = make()
    task = ready(s, pid)
    code, body = A.handle_post(route(pid, f"/{task}/discard"), {}, store=s)
    check("discard: 200, discarded, no card, the copy and the branch gone",
          code == 200 and body == {"ok": True, "discarded": True} and
          not W.task_dir(app, task).exists() and "jarvis/task-" + task not in subprocess.run(
              ["git", "branch", "--list"], cwd=str(W.project_dir(app)), capture_output=True,
              text=True).stdout, body)
    check("main was untouched", "a.txt" not in main_files(app))
    code, body = A.handle_post(route(pid, f"/{task}/discard"), {}, store=s)
    check("discarding it again: 404", code == 404 and body["error"] == "No such task.", body)
    code, body = A.handle_post(route(pid, f"/{'f' * 12}/discard"), {}, store=s)
    check("a task that never was: 404", code == 404)
    code, body = A.handle_post(route(pid, "/nope/discard"), {}, store=s)
    check("a task id that is not an id: 404", code == 404)
    task = ready(s, pid, title="Copy deleted by hand")
    _rmtree(W.task_dir(app, task))
    check("a task whose copy was deleted by hand is not listed",
          task not in [t["task"] for t in s.get(pid)["app"]["tasks"]])
    code, body = A.handle_get(route(pid, f"/{task}"), store=s)
    check("... and cannot be read: 404", code == 404, body)
    code, body = A.handle_post(route(pid, f"/{task}/discard"), {}, store=s)
    check("... but discarding it still cleans up its branch and note",
          code == 200 and not W.task_known(app, task) and "jarvis/task-" + task not in
          subprocess.run(["git", "branch", "--list"], cwd=str(W.project_dir(app)),
                         capture_output=True, text=True).stdout, body)
    old = A._git_present
    A._git_present = lambda: False
    try:
        code, body = A.handle_post(route(pid, f"/{'a' * 12}/discard"), {}, store=s)
    finally:
        A._git_present = old
    check("git missing: discard is 503", code == 503, body)


def t_discard_withdraws_a_waiting_card():
    s, pid, app = make()
    task = ready(s, pid)
    held = Held()
    gate = Gate()
    merge(s, pid, task, gate, held)
    check("the card is up", A._waiting_task(app) == task and len(held.fns) == 1)
    code, body = A.handle_post(route(pid, f"/{task}/discard"), {}, store=s)
    check("discarding the task: 200, and the waiting card is withdrawn at once",
          code == 200 and A._waiting_task(app) is None and
          last(app)["outcome"] == "withdrawn", body)
    held.fns[0]()  # the owner says yes to a card that no longer stands
    check("a yes that comes late does nothing: withdrawn, nothing merged",
          last(app)["outcome"] == "withdrawn" and "a.txt" not in main_files(app)
          and last(app)["message"] == A.OUTCOME_WORDS["withdrawn"], last(app))
    check("the app is free for a new card", A._waiting_task(app) is None and
          not A._A_STATE["withdrawn"])
    # discarding another task leaves the card alone
    a = ready(s, pid, (("a.txt", "one"),), "A")
    b = ready(s, pid, (("b.txt", "two"),), "B")
    held = Held()
    merge(s, pid, a, Gate(), held)
    A.handle_post(route(pid, f"/{b}/discard"), {}, store=s)
    check("discarding a DIFFERENT task leaves the waiting card alone",
          A._waiting_task(app) == a)
    held.fns[0]()
    check("... and its yes still merges", last(app)["outcome"] == "merged")


def t_a_merge_and_a_discard_never_interleave():
    """The card's yes is written while holding the module's lock; a discard
    takes the same lock, so a task cannot vanish half way through a merge."""
    s, pid, app = make()
    task = ready(s, pid)
    order = []
    real = W.run_merge

    def slow(plan, approved=False):
        order.append("merge-start")
        time.sleep(0.3)
        out = real(plan, approved=approved)
        order.append("merge-end")
        return out

    W.run_merge = slow
    try:
        t = threading.Thread(target=lambda: merge(s, pid, task, Gate(), now_spawn))
        t.start()
        while "merge-start" not in order:
            time.sleep(0.01)
        code, body = A.handle_post(route(pid, f"/{task}/discard"), {}, store=s)
        order.append("discard-done")
        t.join(10)
    finally:
        W.run_merge = real
    check("a discard that arrives mid-merge waits until the merge is over",
          order == ["merge-start", "merge-end", "discard-done"], order)
    check("... and the merge landed whole", "a.txt" in main_files(app))


def t_deleting_the_project_withdraws_the_card_and_keeps_the_folder():
    s, pid, app = make(fresh(), "Doomed project")
    task = ready(s, pid, (("keep.txt", "mine"),))
    held = Held()
    merge(s, pid, task, Gate(), held)
    check("a card is up", A._waiting_task(app) == task)
    code, body = P.handle_post(f"/api/projects/{pid}/delete", {}, store=s)
    check("deleting the project: 200 and the folder named in app_kept",
          code == 200 and body == {"ok": True, "deleted": True, "app_kept": app}, body)
    check("the waiting card is withdrawn and the old outcome forgotten",
          A._waiting_task(app) is None and last(app) is None)
    held.fns[0]()
    check("a yes that comes late merges nothing",
          "keep.txt" not in main_files(app) and W.task_dir(app, task).is_dir())
    check("the folder, its history and the task's copy are all still there",
          W.project_dir(app).is_dir() and main_files(app) == [".gitignore", ".jarvis-app.json",
                                                              "README.md"]
          and W.task_dir(app, task).is_dir())
    check("it is offered again as an unlinked app",
          s.unlinked_apps() == [{"name": app, "type": "web", "title": "Doomed project"}])
    code, body = P.handle_post("/api/projects", {"kind": "coding", "app": {"adopt": app}},
                               store=s)
    check("adopting it again: a fresh project with the task still open, and no old outcome",
          code == 200 and body["project"]["app"]["merge"] == {"waiting": None, "last": None}
          and [t["task"] for t in body["project"]["app"]["tasks"]] == [task], body)
    check("the list carries an unlinked_apps field", "unlinked_apps" in P.handle_get(
        "/api/projects", store=s)[1] and P.handle_get("/api/projects", store=s)[1]
        ["unlinked_apps"] == [])


def t_a_restart_drops_the_card_and_keeps_the_task():
    s, pid, app = make()
    task = ready(s, pid)
    merge(s, pid, task, Gate(), Held())
    check("a card is waiting", A._waiting_task(app) == task)
    A._reset_for_tests()  # what a restart of the backend does to memory
    check("after a restart nothing waits", A._waiting_task(app) is None)
    check("... but the task and its change are still there",
          [t["task"] for t in s.get(pid)["app"]["tasks"]] == [task])
    (code, body), gate = merge(s, pid, task, Gate(), now_spawn)
    check("... and can be merged again with a new card",
          code == 202 and len(gate.calls) == 1 and last(app)["outcome"] == "merged", body)


# --------------------------------------------------------------------------
#   What git sees, what the audit log holds
# --------------------------------------------------------------------------


def t_git_sees_only_the_allowlisted_environment():
    seen = []
    real = subprocess.run

    def spy(cmd, *a, **k):
        if cmd and cmd[0] == "git":
            seen.append(dict(k.get("env") or {}))
        return real(cmd, *a, **k)

    W.subprocess.run = spy
    try:
        s, pid, app = make(fresh(), "Env check")
        task = ready(s, pid)
        merge(s, pid, task, Gate(), now_spawn)
        s.get(pid)
    finally:
        W.subprocess.run = real
    check("git ran many times through this module's flow", len(seen) > 10, len(seen))
    check("no run of git ever got the fake token",
          all("JARVIS_TEST_FAKE_TOKEN" not in e for e in seen))
    check("every run had the owner's own git settings switched off",
          all(e.get("GIT_CONFIG_GLOBAL") == os.devnull and e.get("GIT_CONFIG_NOSYSTEM") == "1"
              for e in seen))
    check("the merge really landed while it was being watched",
          last(app)["outcome"] == "merged")


def t_the_audit_log_holds_counts_only():
    _AUDIT.clear()
    s, pid, app = make(fresh(), "Secret plans")
    task = ready(s, pid, (("src/secret_module.py", "SUPER_SECRET = 'hunter2'"),),
                 "Add the secret module")
    merge(s, pid, task, Gate(), now_spawn)
    t2 = ready(s, pid, (("other.txt", "x"),), "Discarded work")
    A.handle_post(route(pid, f"/{t2}/discard"), {}, store=s)
    text = json.dumps(_AUDIT, default=str)
    check("the audit log has lines for the flow", len(_AUDIT) >= 5, len(_AUDIT))
    check("none names a file, a task title, the app or a line of code",
          not any(w in text for w in ("secret_module", "hunter2", "SUPER_SECRET",
                                      "Add the secret module", "Secret plans", "secret-plans",
                                      "Discarded work", "other.txt")), text[:400])
    check("the card's outcome is logged as a word only",
          ("apps.merge.card", {"outcome": "merged"}) in _AUDIT)


# --------------------------------------------------------------------------
#   install(): the routes on the real server's shape
# --------------------------------------------------------------------------


def t_install_wraps_the_routes():
    hits = []

    class H:
        path = "/"
        client_address = ("127.0.0.1", 5)
        connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8080))

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            hits.append((code, out))

    old_one = P._ONE
    try:
        s, pid, app = make(fresh(), "Wired")
        P._ONE = s
        body = {"title": "Over the wire"}
        line = A.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                         read_body=lambda self: json.dumps(body).encode())
        check("install returns a banner line", "App projects" in line)
        check("installing twice does not wrap twice", "already on" in A.install(
            H, origin_ok=lambda self: True, token_ok=lambda self: True, read_body=None))
        h = H()
        h.path = route(pid)
        h.do_POST()
        check("POST .../app/tasks is answered here", isinstance(hits[-1], tuple)
              and hits[-1][0] == 200 and hits[-1][1]["task"]["title"] == "Over the wire",
              hits[-1])
        task = hits[-1][1]["task"]["task"]
        h.path = route(pid, f"/{task}") + "?x=1"
        h.do_GET()
        check("GET one task (with a query) is answered here",
              hits[-1][0] == 200 and hits[-1][1]["task"]["task"] == task)
        h.path = route(pid, f"/{task}/files")
        body["blocks"] = "<<<FILE a.txt>>>\nx\n<<<END>>>"
        h.do_POST()
        check("a paste from the PC itself (peer 127.0.0.1) is accepted", hits[-1][0] == 200,
              hits[-1])
        h.client_address = ("100.64.1.2", 5)
        h.do_POST()
        check("the same paste from another device (a phone on Tailscale) is 403 pc_only",
              hits[-1][0] == 403 and hits[-1][1]["pc_only"] is True, hits[-1])
        h.path = route(pid, f"/{task}/merge")
        body.clear()
        held_cards = Held()
        real_gate, real_spawn = P._gate, P._spawn
        P._gate, P._spawn = Gate(), held_cards
        try:
            h.do_POST()
        finally:
            P._gate, P._spawn = real_gate, real_spawn
        check("Merge from another device (a phone) is accepted, not PC only: 202 and ONE card",
              hits[-1][0] == 202 and hits[-1][1]["waiting"] is True
              and len(held_cards.fns) == 1, hits[-1])
        h.path = "/api/projects"
        h.do_GET()
        h.do_POST()
        check("the projects routes and everything else pass through",
              hits[-2:] == ["get0", "post0"])
        h.path = f"/api/projects/{pid}/benchmarks"
        h.do_POST()
        check("a projects route with more path is still not ours", hits[-1] == "post0")

        class H2(H):
            pass
        H2.do_GET = lambda self: hits.append("g")
        H2.do_POST = lambda self: hits.append("p")
        A.install(H2, origin_ok=lambda self: True, token_ok=lambda self: False,
                  read_body=lambda self: b"{}")
        h2 = H2()
        h2.path = route(pid, "/" + "a" * 12)
        h2.do_GET()
        check("without the token: 401, nothing read", hits[-1][0] == 401)

        class H3(H):
            pass
        H3.do_GET = lambda self: hits.append("g")
        H3.do_POST = lambda self: hits.append("p")
        A.install(H3, origin_ok=lambda self: False, token_ok=lambda self: True,
                  read_body=lambda self: b"{}")
        h3 = H3()
        h3.path = route(pid)
        h3.do_POST()
        check("from another origin: 403, nothing read", hits[-1][0] == 403)

        class H4(H):
            pass
        H4.do_GET = lambda self: hits.append("g")
        H4.do_POST = lambda self: hits.append("p")
        A.install(H4, origin_ok=lambda self: True, token_ok=lambda self: True,
                  read_body=lambda self: b"{not json")
        h4 = H4()
        h4.path = route(pid)
        h4.do_POST()
        check("a body that is not JSON: 400, not a crash", hits[-1][0] == 400, hits[-1])
    finally:
        P._ONE = old_one


# --------------------------------------------------------------------------
#   The wiring: the patch, the tables, the contract
# --------------------------------------------------------------------------


def t_the_patch_and_the_tables():
    sys.path.insert(0, str(HERE))
    import _stack
    order = _stack.order()
    check("apps-in-projects.patch is in apply-patches.ps1's list, after projects.patch and "
          "devices.patch", "apps-in-projects.patch" in order
          and order.index("apps-in-projects.patch") > order.index("projects.patch")
          and order.index("apps-in-projects.patch") > order.index("devices.patch"), order[-4:])
    gate, glog = _stack.stand_in("jarvis_gate.py")
    hud, hlog = _stack.stand_in("jarvis_hud.py")
    check("the stack builds both stand-ins", gate is not None and hud is not None)
    check("the patch's hunks apply to what the patches before it wrote (no line of it "
          "needed materialising)", not [l for l in glog + hlog
                                        if l.startswith("apps-in-projects.patch")],
          [l for l in glog + hlog if l.startswith("apps-in-projects.patch")])
    check("the server installs jarvis_apps right after the projects block, before chatbot's",
          hud.index("jarvis_projects.install") < hud.index("jarvis_apps.install")
          < hud.index("jarvis_chatbot_routes.install"))
    check("the install block wraps its own failure in try/except and says so on the banner",
          'print(f"  apps       NOT ON' in hud)
    check("app_merge_change is in the gate's no-standing-rule list exactly once",
          gate.count('"app_merge_change",  # jarvis_apps.py acts only on tier "ask"') == 1)
    line = [l for l in gate.split("\n") if l.startswith('    "app_merge_change": (')]
    check("the gate's risk table has ONE line for it: cannot be undone (no), stays on this PC",
          len(line) == 1 and line[0].startswith('    "app_merge_change": ("no", "local", "'),
          line)
    check("... and its words say nothing is run and there is no Undo button yet",
          "nothing is run" in line[0] and "no Undo button" in line[0])
    import jarvis_owner_check as OC
    row = {"id": "x", "action": "app_merge_change", "tier": "ask", "risk": {
        "classified": True, "reach": "local", "reversible": "no", "why": "x",
        "swipe_ok": False}}
    check("so the card is RISKY: Windows Hello on the PC, the screen lock on the phone",
          OC.is_risky(row) is True)
    check("... and it is NOT a PC-only card: the phone may approve it, after reading it all",
          "app_merge_change" not in OC.PC_ONLY_ACTIONS)
    import jarvis_asks_first as AF
    check("What asks first: must stay ask, a hard limit, never switchable",
          "app_merge_change" in AF.MUST_ASK and "app_merge_change" in AF.HARD_LIMITS and
          "app_merge_change" not in getattr(AF, "SWITCHABLE", ()))
    check("... and the page lists the new no-card row and the merge card",
          "fixed:app_tasks" in AF.FIXED and "app_merge_change" in [
              a for _t, items in AF.GROUPS for a in items])
    row = AF.FIXED["fixed:app_tasks"]
    check("the new row says it needs no card and where the card is",
          row[1] == AF.SAYS_NO_CARD and "merge card" in row[2] and "PC only" in row[2], row)
    import jarvis_card_words as CW
    check("the card has a plain title (\"add its change to one of your apps\")",
          CW.TITLES.get("app_merge_change") == "add its change to one of your apps")
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped settings file sets it to ask",
          any(l.replace(" ", "") == 'app_merge_change="ask"' for l in toml.split("\n")))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_apps.py is copied in by apply-patches.ps1 and listed in _where.py",
          "'jarvis_apps.py'" in ps1 and "jarvis_apps.py" in (HERE / "_where.py").read_text())
    patch = (HERE / "apps-in-projects.patch").read_text(encoding="utf-8")
    check("the patch touches only jarvis_hud.py and jarvis_gate.py",
          sorted({l[6:] for l in patch.split("\n") if l.startswith("+++ b/")}) ==
          ["jarvis_gate.py", "jarvis_hud.py"] and patch.count("\n@@ ") + patch.startswith(
              "@@") >= 3)


def t_the_contract_file_carries_the_apps_answers():
    for path in (REPO / "jarvis-desktop" / "tests" / "fixtures" / "projects-cases.json",
                 REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
                 / "projects-cases.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        where = "desktop" if "jarvis-desktop" in path.parts else "phone"
        aw = doc.get("app_words", {})
        check(f"{where}: the contract file's outcome sentences are the module's",
              aw.get("outcomes") == A.OUTCOME_WORDS)
        check(f"{where}: ... with the 'cannot run this yet' line and the pasted line",
              aw.get("cant_run") == "Jarvis cannot run this yet. Run it yourself and log the "
                                    "number." and aw.get("pasted_line") == W.PASTED_LINE)
        cases, posts = doc["cases"], doc["posts"]
        check(f"{where}: the app answers are in it",
              {"app_tasks", "app_waiting", "app_merged", "app_no_git", "task_pasted",
               "task_empty", "task_too_big", "list_app", "list_adopted"} <= set(cases)
              and {"create_app", "task_start", "paste", "paste_from_phone", "merge_yes",
                   "merge_card_twice", "delete_app", "adopt"} <= set(posts))
        check(f"{where}: the PC-only refusal is in it, as 403 with pc_only",
              posts["paste_from_phone"]["status"] == 403
              and posts["paste_from_phone"]["body"]["pc_only"] is True)
        check(f"{where}: every app error in it is a plain sentence with ok false",
              all(p["body"].get("ok") is False and p["body"]["error"].endswith(".")
                  for k, p in posts.items() if p["status"] >= 400 and k.startswith((
                      "paste", "merge", "task", "adopt", "app_", "update_app",
                      "update_folder_on_app", "create_app", "discard"))))
        card = doc.get("app_merge_card", "")
        check(f"{where}: the merge card sample is the pasted change's card",
              W.PASTED_LINE in card and "The full change:" in card)


def t_no_network_no_model_no_program_but_git():
    check("nothing in this suite tried to open a network connection", _NET == [], _NET[:3])
    src = (HERE / "jarvis_apps.py").read_text(encoding="utf-8")
    check("jarvis_apps.py imports no network library, starts no program and calls no model",
          not any(w in src for w in ("import urllib", "import http", "import requests",
                                     "import subprocess", "os.system", "Popen(",
                                     "ask_model", "ollama", "import socket")))


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn) and name != \
                    "t_no_network_no_model_no_program_but_git":
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
        print("--- t_no_network_no_model_no_program_but_git ---")
        t_no_network_no_model_no_program_but_git()
    finally:
        socket.socket.connect = _real_connect
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
