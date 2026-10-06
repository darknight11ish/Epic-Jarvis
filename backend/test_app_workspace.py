"""The app workspace (jarvis_app_workspace.py): projects, tasks, the merge card.

    python3 test_app_workspace.py

Runs real git in a temporary settings folder. Needs nothing from the owner's
PC; skips (and says so) only if git itself is not installed.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def refused(fn, *a, **k):
    import jarvis_app_workspace as W
    try:
        fn(*a, **k)
    except W.WorkspaceError:
        return True
    return False


def main():
    if shutil.which("git") is None:
        print("SKIP  git is not installed here")
        return 0
    tmp = tempfile.mkdtemp(prefix="jarvis-apps-")
    os.environ["OPENJARVIS_CONFIG_DIR"] = tmp
    os.environ["JARVIS_TEST_FAKE_TOKEN"] = "must-not-reach-git"
    try:
        import jarvis_app_workspace as W
        W.fw = None  # the settings folder comes from the environment above

        # --- git's environment ------------------------------------------
        env = W.git_env()
        check("git never gets a token-looking variable",
              "JARVIS_TEST_FAKE_TOKEN" not in env)
        check("the owner's own git settings are switched off",
              env.get("GIT_CONFIG_GLOBAL") == os.devnull and env.get("GIT_CONFIG_NOSYSTEM") == "1")

        # --- projects -----------------------------------------------------
        check("a bad name is refused", refused(W.create_project, "My App", "web"))
        check("an unknown kind is refused", refused(W.create_project, "notes", "ios"))
        p = W.create_project("notes", "web", "Notes app")
        proj = W.project_dir("notes")
        check("a project is a git repository on main",
              (proj / ".git").exists() and
              subprocess.run(["git", "branch", "--show-current"], cwd=proj, capture_output=True,
                             text=True).stdout.strip() == "main")
        check("its .gitignore keeps signing keys and .env out",
              "*.keystore" in (proj / ".gitignore").read_text() and
              ".env" in (proj / ".gitignore").read_text())
        check("the same name twice is refused", refused(W.create_project, "notes", "web"))
        check("it is listed with its kind",
              W.list_projects() == [{"name": "notes", "kind": "web", "title": "Notes app"}])

        # --- a task, and what it may write --------------------------------
        t = W.start_task("notes", "Add a first page")["task"]
        tdir = W.task_dir("notes", t)
        check("a task is its own copy", tdir.is_dir() and (tdir / "README.md").is_file())
        check("the task is listed", [x["task"] for x in W.list_tasks("notes")] == [t])

        for bad in ("../escape.txt", "/etc/passwd", "C:/x.txt", "a\\b.txt", ".git/hooks/pre-commit",
                    "src/.git/x", "con.txt", "src/NUL", "trailing.", "folder./x.txt", "", ".jarvis-app.json"):
            check(f"refused path {bad!r}",
                  refused(W.apply_change, "notes", t, [("write", bad, "x")], "bad"))
        check("a refused path leaves the copy untouched",
              not (Path(tmp) / "escape.txt").exists() and
              not subprocess.run(["git", "status", "--porcelain"], cwd=tdir, capture_output=True,
                                 text=True).stdout.strip())
        big = "x" * (W.MAX_FILE_BYTES + 1)
        check("a too-large file is refused",
              refused(W.apply_change, "notes", t, [("write", "big.txt", big)], "big"))

        answer = ("Here you go.\n<<<FILE src/App.tsx>>>\nexport default function App() {\n"
                  "  return <h1>Notes</h1>;\n}\n<<<END>>>\nand\n<<<DELETE README.md>>>\n")
        blocks = W.parse_file_blocks(answer)
        check("the model's file blocks are read",
              blocks == [("write", "src/App.tsx",
                          "export default function App() {\n  return <h1>Notes</h1>;\n}\n"),
                         ("delete", "README.md", None)], repr(blocks))
        r = W.apply_change("notes", t, blocks, "First page")
        check("a change is written and recorded", r == {"ok": True, "changed": 2}, repr(r))
        check("main is untouched by the task", (proj / "README.md").is_file() and
              not (proj / "src").exists())

        d = W.diff("notes", t)
        check("the diff lists both files",
              sorted(f["path"] for f in d["files"]) == ["README.md", "src/App.tsx"], repr(d["files"]))

        # --- the merge card -----------------------------------------------
        plan = W.plan_merge("notes", t)
        card = W.describe(plan)
        check("the card names every file and shows the full change",
              "src/App.tsx" in card and "README.md" in card and "<h1>Notes</h1>" in card)
        check("the card's gate detail carries no file contents",
              "Notes" not in repr(plan.detail()))
        check("without approval nothing merges",
              W.run_merge(plan) == {"ok": False, "error": "not approved"} and
              not (proj / "src").exists())

        W.apply_change("notes", t, [("write", "src/extra.ts", "export const x = 1;\n")], "More")
        stale = W.run_merge(plan, approved=True)
        check("a change after the card was shown is refused",
              not stale["ok"] and not (proj / "src").exists(), repr(stale))

        plan = W.plan_merge("notes", t)
        done = W.run_merge(plan, approved=True)
        check("an approved, unchanged card merges into main",
              done == {"ok": True, "files": 3} and (proj / "src" / "App.tsx").is_file() and
              not (proj / "README.md").exists(), repr(done))
        check("the merged task's copy is gone", not tdir.exists() and W.list_tasks("notes") == [])

        # --- throwing a task away -----------------------------------------
        t2 = W.start_task("notes", "Try something")["task"]
        W.apply_change("notes", t2, [("write", "idea.md", "maybe\n")], "Idea")
        W.discard("notes", t2)
        check("a discarded task leaves main as it was",
              not W.task_dir("notes", t2).exists() and not (proj / "idea.md").exists())
        empty_id = W.start_task("notes", "Nothing")["task"]
        empty = W.plan_merge("notes", empty_id)
        check("an empty task has nothing to approve", bool(empty.refused) and
              "Nothing to approve" in W.describe(empty))
        W.discard("notes", empty_id)

        # --- apps in Projects: who wrote a task, and what the card says ----
        made = W.start_task("notes", "From Jarvis")
        tj = made["task"]
        check("a task started with no source is Jarvis's", made["source"] == "jarvis" and
              W.list_tasks("notes")[0]["source"] == "jarvis")
        W.apply_change("notes", tj, [("write", "j.txt", "by jarvis\n")], "Jarvis wrote it")
        card = W.describe(W.plan_merge("notes", tj))
        check("a Jarvis-written change's card has no pasted line",
              W.PASTED_LINE not in card and W.plan_merge("notes", tj).source == "jarvis")
        tp = W.start_task("notes", "Typed by the owner", source="empty")["task"]
        listed = {x["task"]: x for x in W.list_tasks("notes")}
        check("a task started 'empty' is listed empty, with the version it began from",
              listed[tp]["source"] == "empty" and listed[tp]["base"] == W.main_head("notes")
              and isinstance(listed[tp]["started"], float), repr(listed[tp]))
        W.apply_change("notes", tp, [("write", "p.txt", "pasted\n")], "Pasted")
        W.set_source("notes", tp, "pasted")
        plan = W.plan_merge("notes", tp)
        card = W.describe(plan)
        check("a pasted change: the plan says so and the card adds the line",
              plan.source == "pasted" and W.PASTED_LINE in card and
              W.PASTED_LINE == "You pasted this change in on your PC.")
        check("... and the line comes before the files, so it cannot be missed",
              card.index(W.PASTED_LINE) < card.index("file(s):"))
        check("a source that is not one of the three is refused",
              refused(W.start_task, "notes", "x", "somebody") and
              refused(W.set_source, "notes", tp, "somebody"))
        check("setting the source of a task that is gone is refused",
              refused(W.set_source, "notes", "0" * 12, "pasted"))
        W.discard("notes", tj)
        W.discard("notes", tp)

        # --- the count is what git kept -----------------------------------
        tg = W.start_task("notes", "Ignored files")["task"]
        r = W.apply_change("notes", tg, [("write", ".env", "SECRET=1\n")], "Only a secret")
        check("a file .gitignore drops is written but is not a change: changed is 0",
              r == {"ok": True, "changed": 0}, repr(r))
        r = W.apply_change("notes", tg, [("write", ".env", "SECRET=2\n"),
                                         ("write", "dist/out.js", "x\n"),
                                         ("write", "kept.txt", "kept\n")], "Mixed")
        check("three blocks, one file git keeps: changed is 1, and the card shows that one",
              r == {"ok": True, "changed": 1} and
              [f["path"] for f in W.plan_merge("notes", tg).files] == ["kept.txt"], repr(r))
        r = W.apply_change("notes", tg, [("write", "kept.txt", "kept\n")], "Same again")
        check("writing a file as it already is changes nothing: changed is 0",
              r == {"ok": True, "changed": 0}, repr(r))
        W.discard("notes", tg)

        # --- git attributes must not hide a change from the card -----------
        # (audit 2026-09-29: with `* -diff` in main, git printed "Binary files
        # differ" for every later change, so the card showed no content.)
        check("Jarvis's own note is protected whatever the letter case (Windows)",
              refused(W.apply_change, "notes", W.start_task("notes", "Case")["task"],
                      [("write", ".Jarvis-App.json", "{}")], "case"))
        for tt in [x["task"] for x in W.list_tasks("notes")]:
            W.discard("notes", tt)
        tw = W.start_task("notes", "Attributes")["task"]
        W.apply_change("notes", tw, [("write", ".gitattributes", "* -diff\n*.js binary\n")], "Attrs")
        W.plan_merge("notes", tw)
        W.run_merge(W.plan_merge("notes", tw), approved=True)
        tb = W.start_task("notes", "Hidden by attributes")["task"]
        W.apply_change("notes", tb, [("write", "app.js", "console.log('secret plan');\n"),
                                     ("write", "note.txt", "plain words\n")], "Two files")
        planb = W.plan_merge("notes", tb)
        cardb = W.describe(planb)
        check("with `* -diff` and `binary` in main, the card still shows the whole text",
              "console.log('secret plan');" in cardb and "plain words" in cardb
              and "Binary files" not in cardb and not planb.refused, cardb[:300])
        check("... and the counts are real numbers, not dashes",
              all(f["added"].isdigit() and f["removed"].isdigit() for f in planb.files),
              repr(planb.files))
        W.discard("notes", tb)

        # --- the latest saved version --------------------------------------
        info = W.main_info("notes")
        check("main_info: a short commit, the subject, a time, a count of versions",
              len(info["head"]) == 7 and info["head"] == W.main_head("notes")[:7] and
              info["subject"].startswith("Jarvis: ") and isinstance(info["at"], float) and
              info["versions"] >= 3, repr(info))
        check("main_info of an app that is not there is refused",
              refused(W.main_info, "ghost"))

        # --- diff_stat and the other small reads ---------------------------
        ts = W.start_task("notes", "Stat")["task"]
        W.apply_change("notes", ts, [("write", "s.txt", "a\nb\n")], "Two lines")
        check("diff_stat lists each file with counts, no text",
              W.diff_stat("notes", ts) == [{"path": "s.txt", "added": "2", "removed": "0"}])
        check("app_meta reads the app's own note",
              W.app_meta("notes") == {"kind": "web", "title": "Notes app"})
        check("task_known: a task with a copy is known, a stranger is not",
              W.task_known("notes", ts) and not W.task_known("notes", "0" * 12) and
              not W.task_known("notes", "nope"))

        # --- a task whose copy was deleted by hand -------------------------
        import shutil as _sh
        _sh.rmtree(W.task_dir("notes", ts))
        check("a task whose copy is gone is no longer listed ...",
              ts not in [x["task"] for x in W.list_tasks("notes")])
        check("... but is still known, so discard can clean up its branch and note",
              W.task_known("notes", ts))
        W.discard("notes", ts)
        check("discard of that task removes the note and the branch",
              not W.task_known("notes", ts) and
              "jarvis/task-" + ts not in subprocess.run(
                  ["git", "branch", "--list"], cwd=proj, capture_output=True,
                  text=True).stdout)

        # --- run_merge says why it refused ---------------------------------
        tm = W.start_task("notes", "Why")["task"]
        W.apply_change("notes", tm, [("write", "why.txt", "w\n")], "Why")
        plan = W.plan_merge("notes", tm)
        W.apply_change("notes", tm, [("write", "why2.txt", "w\n")], "Moved")
        check("a task that moved after the card: why is stale",
              W.run_merge(plan, approved=True).get("why") == "stale")
        plan = W.plan_merge("notes", tm)
        (proj / "scratch.txt").write_text("owner's own edit\n")
        check("an unsaved change in the app's folder: why is unsaved, nothing merged",
              W.run_merge(plan, approved=True).get("why") == "unsaved" and
              not (proj / "why.txt").exists())
        (proj / "scratch.txt").unlink()
        # a conflict: both sides changed the same file differently
        tc1 = W.start_task("notes", "Conflict A")["task"]
        tc2 = W.start_task("notes", "Conflict B")["task"]
        W.apply_change("notes", tc1, [("write", "same.txt", "one\n")], "A")
        W.apply_change("notes", tc2, [("write", "same.txt", "two\n")], "B")
        plan_b = W.plan_merge("notes", tc2)
        first = W.run_merge(W.plan_merge("notes", tc1), approved=True)
        plan_b = W.plan_merge("notes", tc2)
        second = W.run_merge(plan_b, approved=True)
        check("two tasks touching the same file: the first merges, the second is a "
              "conflict, and main is left as the first made it",
              first["ok"] and second.get("why") == "conflict" and
              (proj / "same.txt").read_text() == "one\n" and
              not subprocess.run(["git", "status", "--porcelain"], cwd=proj,
                                 capture_output=True, text=True).stdout.strip(), repr(second))
        check("a task that is gone: why is gone",
              W.run_merge(W.plan_merge("notes", tc1), approved=True).get("ok") is False)
        W.discard("notes", tm)
        W.discard("notes", tc2)

        # --- the open-task cap ---------------------------------------------
        for n in range(W.MAX_OPEN_TASKS - len(W.list_tasks("notes"))):
            W.start_task("notes", f"Filler {n}")
        check("MAX_OPEN_TASKS is 10 and the tenth task is allowed",
              W.MAX_OPEN_TASKS == 10 and len(W.list_tasks("notes")) == 10)
        check("an eleventh open task is refused, in plain words",
              refused(W.start_task, "notes", "One too many"))
        for x in W.list_tasks("notes"):
            W.discard("notes", x["task"])

        # --- git missing is its own kind of error ---------------------------
        check("GitUnavailable is a WorkspaceError, so old callers still catch it",
              issubclass(W.GitUnavailable, W.WorkspaceError))
        # Windows' CreateProcess searches well beyond PATH (the application
        # directory, the current directory, the system directories), so emptying
        # the environment did NOT hide git there: _git ran, raised nothing, and
        # this check read "None". Make the absence explicit instead - the thing
        # under test is the FileNotFoundError -> GitUnavailable mapping, which is
        # the same on every platform (2026-10-03).
        def _no_git(*_a, **_k):
            raise FileNotFoundError("git")
        real_run = W.subprocess.run
        W.subprocess.run = _no_git
        try:
            try:
                W._git(["status"], proj)
                gone = None
            except W.GitUnavailable as exc:
                gone = str(exc)
            except Exception as exc:  # pragma: no cover
                gone = "wrong error: " + type(exc).__name__
        finally:
            W.subprocess.run = real_run
        check("git not on the path: a GitUnavailable naming git.scm",
              gone is not None and "git is not installed" in gone, repr(gone))
    except Exception:
        check("no unexpected error", False, traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
