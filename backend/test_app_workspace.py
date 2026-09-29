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
        empty = W.plan_merge("notes", W.start_task("notes", "Nothing")["task"])
        check("an empty task has nothing to approve", bool(empty.refused) and
              "Nothing to approve" in W.describe(empty))
    except Exception:
        check("no unexpected error", False, traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
