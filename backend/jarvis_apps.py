"""jarvis_apps.py - an app's tasks and its merge card, inside a project
(docs/APPS-IN-PROJECTS-DESIGN.md, the first slice; JARVIS-API section 92).

NEW MODULE, shipped whole (apps-in-projects.patch installs its routes and adds
the gate lines).

WHAT IT IS FOR, IN PLAIN WORDS
The owner decided (CLAUDE.md, 2026-09-28) that an app Jarvis builds is a
coding project whose tests are its benchmarks: one list, not two. Its files
live in Jarvis's own `apps/<name>/` git folder (jarvis_app_workspace.py); the
project (jarvis_projects.py) is the record the owner sees. This module is the
part between them: an app's open TASKS (one separate copy of the app per piece
of work), reading a task's whole change, and the ONE approval card that lets a
change into the app.

WHAT IS BUILT, AND WHAT IS NOT (the owner's answers of 2026-09-29)
  * Built: the app and its tasks in the project views, starting a task,
    pasting a change into a task (on the PC only), reading a task's whole
    change, Merge (ONE risky card) and Discard.
  * NOT built: a model tool that writes code (B2 - waits for the 12 GB card),
    and running any command (npm, Gradle: milestone C). Nothing here runs a
    program; git is the only program started, by jarvis_app_workspace, with
    the owner's own git settings switched off.

WHO MAY DO WHAT, AND WHICH NEED A CARD
  * Start a task, discard one: no card (an empty copy; a thrown-away
    proposal), either app.
  * Paste a change in: no card, THIS PC ONLY (403 pc_only): a paste of code
    is deep editing, which stays off the phone. It lands only in the task's
    own copy; the merge card decides.
  * Merge: ONE card, `app_merge_change`, every time, approved on either
    device. The card is RISKY (jarvis_gate's risk table says reversible "no"),
    so Windows Hello on the PC and the screen lock on the phone are asked. It
    carries the exact words of jarvis_app_workspace.describe(): every file,
    then the whole change. What lands is exactly what was shown - the
    workspace refuses if the task or `main` moved after the card was built.
    A denial is never a standing rule (jarvis_gate _NO_RULE_FROM_DENIAL).
  * Nothing here approves anything, and nothing here can be approved by
    voice or from a widget: it only raises the card the gate already knows.

WHAT IS KEPT
Nothing new on disk: a task is the workspace's own note and git branch. The
"card waiting" and "how the last card ended" state is in memory only, like
Shareable's: a backend restart drops a waiting card and the task simply stays,
so it can be merged again with a new card. The audit log gets counts only,
never a file's name or contents.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from typing import Callable, Optional
from urllib.parse import urlsplit

import jarvis_app_workspace as W
import jarvis_projects as P

ACTION = W.MERGE_ACTION

MAX_TITLE = 120
MAX_BLOCKS_CHARS = 2_000_000

#: How a merge card ended, word for word (docs/APPS-IN-PROJECTS-DESIGN.md
#: 7.1; tools/gen_projects_cases.py carries the same list to both apps).
OUTCOME_WORDS = {
    "merged": "Added to your app.",
    "denied": "Not added - you said no. The change is kept aside.",
    "timed_out": "Not added - the card timed out. The change is kept aside.",
    "stale": "Not added - the app or the change moved after the card was shown. "
             "Look at the new card.",
    "unsaved": "Not added - the app's own folder has changes that are not saved in git.",
    "conflict": "Not added - the change did not fit the app's newer version. "
                "Nothing was changed; discard it and ask again.",
    "withdrawn": "Not added - the change was thrown away before you answered.",
    "refused": "Not added.",
    "failed": "Not added - something went wrong. Nothing was changed.",
}

CARD_WAITING = "A card for this app is already waiting - answer it first."
TASK_CARD_WAITING = "A card for this change is waiting - answer it first."
NO_BLOCKS = "No <<<FILE>>> blocks were found."
NOTHING_CHANGED = ("Nothing in that paste would change the app: files git keeps out (such as "
                   ".env) and files that are already the same are left out.")
PC_ONLY_PASTE = "A change is pasted in on the PC only."
NOT_AN_APP = "This project is not an app."
NO_TASK = "No such task."
NO_PROJECT = "No such project."
PASTE_SUMMARY = "Change pasted in by the owner"

# --------------------------------------------------------------------------
#   Small helpers
# --------------------------------------------------------------------------


def slug(name: str, taken=()) -> str:
    """A folder name for a new app project: lower-case, every run of other
    characters becomes one dash, at most 40 characters, `app` if nothing is
    left, then `-2`, `-3` ... while the name is taken."""
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:40].strip("-")
    base = base or "app"
    taken = set(taken)
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        cand = base[:40 - len(suffix)].rstrip("-") + suffix
        if cand not in taken:
            return cand
        n += 1


def _git_present() -> bool:
    return shutil.which("git") is not None


def _sentence(text) -> str:
    s = str(text or "").strip() or "Something went wrong"
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!", ">")) else s + "."


def _fail(code: int, error: str, **extra) -> tuple:
    return code, {"ok": False, "error": error, **extra}


def _audit(event: str, detail: dict) -> None:
    P._audit(event, detail)


# --------------------------------------------------------------------------
#   The card's state (in memory, like Shareable's)
# --------------------------------------------------------------------------

_A_LOCK = threading.Lock()
_A_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}
#: Held while a card's yes is written (the merge itself) and while a task is
#: discarded or a project deleted, so the two never interleave.
_A_SWITCH = threading.RLock()


def _waiting_task(app: str) -> Optional[str]:
    with _A_LOCK:
        p = _A_STATE["pending"].get(app)
        return p["task"] if p else None


def _last(app: str) -> Optional[dict]:
    with _A_LOCK:
        last = _A_STATE["last"].get(app)
        return dict(last) if last else None


def withdraw_card(app: str, *, forget_last: bool = True) -> None:
    """A card waiting for this app is withdrawn: its yes will do nothing. Used
    when its task is discarded or its project deleted."""
    with _A_LOCK:
        p = _A_STATE["pending"].pop(app, None)
        if p:
            _A_STATE["withdrawn"].add(p["token"])
        if forget_last:
            _A_STATE["last"].pop(app, None)


def _finish(app: str, token: str, task: str, outcome: str, why: str = "") -> None:
    message = OUTCOME_WORDS.get(outcome, "")
    if outcome == "refused" and why:
        message = f"{message} {_sentence(why[:200])}"
    with _A_LOCK:
        p = _A_STATE["pending"].get(app)
        if p and p.get("token") == token:
            _A_STATE["pending"].pop(app, None)
        _A_STATE["withdrawn"].discard(token)
        _A_STATE["last"][app] = {"task": task, "outcome": outcome, "message": message,
                                 "at": time.time()}
    _audit("apps.merge.card", {"outcome": outcome})


# --------------------------------------------------------------------------
#   Views
# --------------------------------------------------------------------------


def summary(app: str) -> dict:
    """The short `app` object in the project list: no git, cheap."""
    try:
        meta = W.app_meta(app)
        n = len(W.list_tasks(app))
    except Exception:
        meta, n = {"kind": ""}, 0
    return {"name": app, "type": meta["kind"], "tasks": n,
            "merge_waiting": _waiting_task(app) is not None}


def _stats(files: list) -> tuple:
    added = removed = 0
    for f in files:
        for key in ("added", "removed"):
            try:
                n = int(f.get(key, 0))
            except (TypeError, ValueError):
                n = 0  # "-": a file git cannot count
            if key == "added":
                added += n
            else:
                removed += n
    return len(files), added, removed


def _task_summary(item: dict, files: list, main_head: str, waiting: Optional[str]) -> dict:
    n, added, removed = _stats(files)
    base = item.get("base") or ""
    return {"task": item["task"], "title": item.get("title", ""), "started": item.get("started"),
            "source": item.get("source", "jarvis"), "files": n, "added": added,
            "removed": removed, "older_main": bool(base) and bool(main_head) and base != main_head,
            "waiting": waiting == item["task"]}


def _order(tasks: list) -> list:
    return sorted(tasks, key=lambda t: (t.get("started") is None, t.get("started") or 0.0,
                                        t.get("task", "")))


def full(app: str) -> dict:
    """The whole `app` object of one project (design section 7.1)."""
    waiting = _waiting_task(app)
    try:
        meta = W.app_meta(app)
        folder = W.project_dir(app).is_dir()
    except Exception:
        meta, folder = {"kind": "", "title": app}, False
    out = {"name": app, "type": meta["kind"], "title": meta["title"], "git_ok": True,
           "said": "", "main": None, "tasks": [],
           "merge": {"waiting": waiting, "last": _last(app)}}
    if not folder:
        out.update(git_ok=False, said="This app's folder is missing from Jarvis's apps "
                                      "folder, so its versions cannot be shown.")
        return out
    if not _git_present():
        out.update(git_ok=False, said=_sentence(W.GitUnavailable(
            "git is not installed on this PC (https://git-scm.com), so Jarvis cannot keep "
            "app projects yet")))
        return out
    try:
        out["main"] = W.main_info(app)
        head = W.main_head(app)
        tasks = [_task_summary(item, W.diff_stat(app, item["task"]), head, waiting)
                 for item in _order(W.list_tasks(app))]
        out["tasks"] = tasks
    except W.WorkspaceError as exc:
        out.update(git_ok=False, said=_sentence(exc), main=None, tasks=[])
    return out


def _detail(app: str, task: str) -> dict:
    """One task, whole: its summary, its files and the whole comparison (the
    text the card would show; "" when it is too big to show)."""
    plan = W.plan_merge(app, task)
    item = next((t for t in W.list_tasks(app) if t["task"] == task), None)
    if item is None:
        raise W.WorkspaceError("that task is gone - it was merged or thrown away")
    too_big = len(plan.diff) > W.MAX_CARD_DIFF_CHARS
    out = _task_summary(item, plan.files, plan.main, _waiting_task(app))
    out["list"] = [{"path": f["path"], "added": f["added"], "removed": f["removed"]}
                   for f in plan.files]
    out["diff"] = "" if too_big else plan.diff
    out["too_big"] = too_big
    out["refused"] = _sentence(plan.refused) if plan.refused else ""
    return out


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------


def _decide(app: str, token: str, plan, project_name: str, gate: Callable,
            tier_of: Callable) -> None:
    text = W.describe(plan)
    detail = {"text": text, "what": "add one change to your app", "project": project_name,
              "app": app, "files": len(plan.files), "leaves_this_pc": False}
    task = plan.task
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(app, token, task, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(app, token, task, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person "
                       f"saying yes")
    if not P._person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(app, token, task, outcome)
        return _finish(app, token, task, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _A_SWITCH:
        with _A_LOCK:
            withdrawn = token in _A_STATE["withdrawn"]
        if withdrawn:
            return _finish(app, token, task, "withdrawn")
        try:
            r = W.run_merge(plan, approved=True)
        except Exception as exc:
            return _finish(app, token, task, "failed", type(exc).__name__)
    if r.get("ok"):
        return _finish(app, token, task, "merged")
    why = r.get("why")
    if why in ("stale", "unsaved", "conflict"):
        return _finish(app, token, task, why)
    if why == "gone":
        return _finish(app, token, task, "withdrawn")
    if why == "refused":
        return _finish(app, token, task, "refused", str(r.get("error", ""))[:200])
    _finish(app, token, task, "failed")


def request_merge(pid: str, task: str, *, store=None, gate: Optional[Callable] = None,
                  tier_of: Optional[Callable] = None, spawn: Optional[Callable] = None) -> tuple:
    """POST .../app/tasks/<task>/merge. 202 and ONE card, or 400/409/503 and
    no card."""
    store = store or P.get()
    gate = gate or P._gate
    tier_of = tier_of or P._tier
    spawn = spawn or P._spawn
    got = _resolve(store, pid)
    if isinstance(got[0], int):
        return got
    app, project_name = got
    if not _git_present():
        return _fail(503, _sentence(W.GitUnavailable(
            "git is not installed on this PC (https://git-scm.com), so Jarvis cannot keep "
            "app projects yet")))
    try:
        if not _task_dir_ok(app, task):
            return _fail(404, NO_TASK)
        if _waiting_task(app) is not None:
            return _fail(409, CARD_WAITING)
        plan = W.plan_merge(app, task)
    except W.GitUnavailable as exc:
        return _fail(503, _sentence(exc))
    except W.WorkspaceError as exc:
        return _fail(400, _sentence(exc))
    if plan.refused:
        return _fail(400, _sentence(plan.refused))
    t = tier_of(ACTION)
    if t != "ask":
        return _fail(503, f"{ACTION} is tier {t!r} in jarvis-framework.toml; adding a change "
                          f"to an app needs a person to say yes, so it must be 'ask'")
    with _A_LOCK:
        if app in _A_STATE["pending"]:
            return _fail(409, CARD_WAITING)
        token = uuid.uuid4().hex
        _A_STATE["pending"][app] = {"token": token, "task": task, "since": time.time()}
    try:
        spawn(lambda: _decide(app, token, plan, project_name, gate, tier_of))
    except Exception:
        with _A_LOCK:
            _A_STATE["pending"].pop(app, None)
        return _fail(503, "Could not raise the approval card.")
    return 202, {"ok": True, "waiting": True,
                 "message": "Waiting for your approval. Your app stays as it is unless you "
                            "approve the card."}


# --------------------------------------------------------------------------
#   The other routes
# --------------------------------------------------------------------------

PATH = "/api/projects"


def parse_route(route: str) -> Optional[tuple]:
    """None, or a tuple naming the route:
        ("tasks", pid)               /api/projects/<pid>/app/tasks
        ("task", pid, task)          /api/projects/<pid>/app/tasks/<task>
        ("files", pid, task)         .../<task>/files
        ("merge", pid, task)         .../<task>/merge
        ("discard", pid, task)       .../<task>/discard
    """
    if not isinstance(route, str) or not route.startswith(PATH + "/"):
        return None
    p = route[len(PATH) + 1:].split("/")
    if len(p) < 3 or not p[0] or p[1] != "app" or p[2] != "tasks":
        return None
    if len(p) == 3:
        return ("tasks", p[0])
    if len(p) == 4 and p[3]:
        return ("task", p[0], p[3])
    if len(p) == 5 and p[3] and p[4] in ("files", "merge", "discard"):
        return (p[4], p[0], p[3])
    return None


def _resolve(store, pid: str):
    """(app folder name, project name), or a (status, body) refusal."""
    try:
        info = store.app_of(pid)
    except KeyError:
        return _fail(404, NO_PROJECT)
    if not info["app"]:
        return _fail(404, NOT_AN_APP)
    return info["app"], info["name"]


def _task_dir_ok(app: str, task: str) -> bool:
    try:
        return W.task_dir(app, task).is_dir()
    except W.WorkspaceError:
        return False


def _need_git() -> Optional[tuple]:
    if _git_present():
        return None
    return _fail(503, _sentence(W.GitUnavailable(
        "git is not installed on this PC (https://git-scm.com), so Jarvis cannot keep app "
        "projects yet")))


def _start_task(app: str, body: dict) -> tuple:
    if (r := _need_git()) is not None:
        return r
    try:
        title = P._one_line(body.get("title"), MAX_TITLE, "the title", required=True)
    except ValueError as exc:
        return _fail(400, _sentence(exc))
    try:
        with _A_SWITCH:
            if len(W.list_tasks(app)) >= W.MAX_OPEN_TASKS:
                return _fail(409, f"This app already has {W.MAX_OPEN_TASKS} open tasks - add "
                                  "or throw one away first.")
            made = W.start_task(app, title, source="empty")
            item = next((t for t in W.list_tasks(app) if t["task"] == made["task"]), None)
            head = W.main_head(app)
    except W.GitUnavailable as exc:
        return _fail(503, _sentence(exc))
    except W.WorkspaceError as exc:
        return _fail(400, _sentence(exc))
    item = item or {"task": made["task"], "title": made["title"], "source": "empty",
                    "base": head, "started": time.time()}
    return 200, {"ok": True, "task": _task_summary(item, [], head, _waiting_task(app))}


def _paste(app: str, task: str, body: dict, here: bool) -> tuple:
    if not here:
        return _fail(403, PC_ONLY_PASTE, pc_only=True)
    if (r := _need_git()) is not None:
        return r
    blocks = body.get("blocks")
    if not isinstance(blocks, str):
        return _fail(400, "Send the change as text in \"blocks\".")
    if len(blocks) > MAX_BLOCKS_CHARS:
        return _fail(400, f"That paste is longer than {MAX_BLOCKS_CHARS:,} characters.")
    if not _task_dir_ok(app, task):
        return _fail(404, NO_TASK)
    changes = W.parse_file_blocks(blocks)
    if not changes:
        return _fail(400, NO_BLOCKS)
    if _waiting_task(app) == task:
        return _fail(409, TASK_CARD_WAITING)
    try:
        with _A_SWITCH:
            # Re-check under the lock the card's yes takes: a card raised
            # while the paste waited must not see its task change under it.
            if _waiting_task(app) == task:
                return _fail(409, TASK_CARD_WAITING)
            done = W.apply_change(app, task, changes, PASTE_SUMMARY)
            if done.get("changed", 0) > 0:
                # Whatever was already in the task, the card now says the
                # owner pasted it: it never claims Jarvis wrote what was typed.
                W.set_source(app, task, "pasted")
    except W.GitUnavailable as exc:
        return _fail(503, _sentence(exc))
    except W.WorkspaceError as exc:
        return _fail(400, _sentence(exc))
    if done.get("changed", 0) == 0:
        return _fail(400, NOTHING_CHANGED)
    _audit("apps.paste", {"files": done["changed"]})
    return 200, {"ok": True, "task": _detail(app, task)}


def _discard(app: str, task: str) -> tuple:
    if (r := _need_git()) is not None:
        return r
    try:
        if not W.task_known(app, task):
            return _fail(404, NO_TASK)
        with _A_SWITCH:
            # A card waiting for THIS task is withdrawn (its yes will do
            # nothing); a card for another task of the app is left alone.
            if _waiting_task(app) == task:
                with _A_LOCK:
                    p = _A_STATE["pending"].pop(app, None)
                    if p:
                        _A_STATE["withdrawn"].add(p["token"])
                        _A_STATE["last"][app] = {"task": task, "outcome": "withdrawn",
                                                 "message": OUTCOME_WORDS["withdrawn"],
                                                 "at": time.time()}
            W.discard(app, task)
    except W.GitUnavailable as exc:
        return _fail(503, _sentence(exc))
    except W.WorkspaceError as exc:
        return _fail(400, _sentence(exc))
    return 200, {"ok": True, "discarded": True}


def handle_get(route: str, query: str = "", *, store=None) -> tuple:
    store = store or P.get()
    hit = parse_route(route)
    if hit is None:
        return _fail(404, "No such route.")
    if hit[0] != "task":
        return _fail(405, "Use POST for this.")
    got = _resolve(store, hit[1])
    if isinstance(got[0], int):
        return got
    app = got[0]
    if (r := _need_git()) is not None:
        return r
    try:
        if not _task_dir_ok(app, hit[2]):
            return _fail(404, NO_TASK)
        return 200, {"ok": True, "task": _detail(app, hit[2])}
    except W.GitUnavailable as exc:
        return _fail(503, _sentence(exc))
    except W.WorkspaceError as exc:
        return _fail(404, _sentence(exc))


def handle_post(route: str, body, *, here: bool = False, store=None, **card) -> tuple:
    store = store or P.get()
    hit = parse_route(route)
    if hit is None:
        return _fail(404, "No such route.")
    if not isinstance(body, dict):
        return _fail(400, "Send a JSON object.")
    kind = hit[0]
    if kind == "task":
        return _fail(405, "Use GET for this.")
    if kind == "files" and not here:
        # PC only, whatever else is wrong with the request.
        return _fail(403, PC_ONLY_PASTE, pc_only=True)
    got = _resolve(store, hit[1])
    if isinstance(got[0], int):
        return got
    app = got[0]
    try:
        if kind == "tasks":
            return _start_task(app, body)
        if kind == "files":
            return _paste(app, hit[2], body, here)
        if kind == "merge":
            return request_merge(hit[1], hit[2], store=store, **card)
        if kind == "discard":
            return _discard(app, hit[2])
    except Exception as exc:
        return _fail(503, type(exc).__name__)
    return _fail(404, "No such route.")


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the app-task routes are
    answered here, after the server's own origin and token checks. Every
    other request goes to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_apps", False):
        _ARMED = True
        return "  apps       App projects (already on)"

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
            code, out = 503, {"ok": False, "error": type(exc).__name__}
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
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, here=P._from_this_pc(*P._peer_local(self)))
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_apps = True
    do_POST._jarvis_apps = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    try:
        n = len(W.list_projects())
    except Exception:
        n = 0
    return f"  apps       App projects: {n} app folder(s)"


_ARMED = False


def _reset_for_tests() -> None:
    global _ARMED
    with _A_LOCK:
        _A_STATE["pending"].clear()
        _A_STATE["withdrawn"].clear()
        _A_STATE["last"].clear()
    _ARMED = False
