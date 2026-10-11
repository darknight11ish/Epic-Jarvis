"""Generate backend/tasks.patch against the REAL backend file.

`backend/_skeleton.py` rehearses a patch on a stand-in built from earlier
patches' own text. That is the best a checkout could do while the Python
program lived only on the owner's PC - and on 2026-10-08 it proved too weak:
`tasks.patch` passed the stand-in rehearsal and then did NOT apply to the real
`jarvis_hud.py`, because a later patch (`note-capture.patch`) had inserted a
route between the lines the stand-in laid side by side.

`jarvis-backend/` is now a copy of the real program (see its README), so the
patch is generated from that file directly: the context lines ARE the real
ones, and the line numbers are the real ones. Run this after any change to the
two blocks, then `backend/test_tasks.py` rehearses it against the same real
file.

    python3 tools/gen_tasks_patch.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "jarvis-backend" / "jarvis_hud.py"
OUT = ROOT / "backend" / "tasks.patch"

# --- the GET block: the counted summary ------------------------------------
GET_BLOCK = """\
        if path == "/api/tasks":
            # tasks.patch - the job list: work that outlives one chat turn.
            # Counted only: ids, tool names, states and step counts, never
            # the text of a note - the same rule jarvis_task_control above
            # follows, so this cannot become a new way for private words to
            # reach a lock screen. The readable feed for the PC's own window
            # is jarvis_tasks.JobList().feed().
            if not _origin_ok(self):
                return self._send(403, {"error": "cross-origin request refused"})
            if not _token_ok(self):
                return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            try:
                import jarvis_tasks
                jarvis_tasks.boot_once()
                return self._send(200, jarvis_tasks.JobList().status())
            except Exception as exc:
                return self._send(503, {"available": False,
                                        "error": f"{type(exc).__name__}: {exc}"})

"""

# --- the POST block: pause, resume, cancel, retry, and an answer -----------
POST_BLOCK = """\
        if route in ("/api/tasks/act", "/api/tasks/input"):
            # tasks.patch - Pause, Resume, Cancel and Retry a job, and answer
            # a question it stopped on. The rules are jarvis_tasks.JobList's
            # own (`_move` and `answer`); this only checks who is asking.
            # **Nothing here approves anything**: Resume puts a job back in
            # the queue and every step of it still raises its own card when
            # its turn comes. Cancel and Pause are immediate, because
            # stopping is never gated.
            if not _origin_ok(self):
                return self._send(403, {"error": "cross-origin request refused"})
            if not _token_ok(self):
                return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            try:
                body = json.loads(_read_body(self) or b"{}")
            except (ValueError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": str(exc)})
            try:
                import jarvis_tasks
            except Exception as exc:
                return self._send(503, {"available": False,
                                        "error": f"{type(exc).__name__}: {exc}"})
            jobs = jarvis_tasks.JobList()
            tid = str(body.get("id") or "")
            try:
                if route.endswith("/input"):
                    got = jobs.answer(tid, str(body.get("answer") or ""))
                else:
                    act = str(body.get("act") or "")
                    if act not in ("pause", "resume", "cancel", "retry"):
                        return self._send(400, {"error": "act must be pause, resume, "
                                                         "cancel or retry"})
                    got = getattr(jobs, act)(tid)
            except jarvis_tasks.Refused as exc:
                return self._send(409, {"error": str(exc)})
            except Exception as exc:
                return self._send(503, {"available": False,
                                        "error": f"{type(exc).__name__}: {exc}"})
            return self._send(200, {"id": got.id, "state": got.status})

"""


def hunk(before, add, after, old_start):
    """One unified hunk: context, insertions, context."""
    old_count = len(before) + len(after)
    new_count = old_count + len(add)
    lines = [f"@@ -{old_start},{old_count} +{old_start},{new_count} @@\n"]
    lines += [" " + l for l in before]
    lines += ["+" + l for l in add]
    lines += [" " + l for l in after]
    return "".join(lines)


def build() -> str:
    src = REAL.read_text(encoding="utf-8").splitlines(keepends=True)
    get_add = GET_BLOCK.splitlines(keepends=True)
    post_add = POST_BLOCK.splitlines(keepends=True)

    def find(prefix, start=0):
        for i in range(start, len(src)):
            if src[i].startswith(prefix):
                return i
        raise SystemExit(f"anchor not found in the real file: {prefix!r}")

    # The GET block goes where task-control's own GET route ends: immediately
    # before the route a LATER patch inserted after it. Quoting that later
    # route is the whole reason this script exists.
    i_get = find('        if path == "/api/notes/capture":')
    # The POST block goes immediately before task-control's own POST routes.
    i_post = find('        if route in ("/api/task/pause"')

    return ("--- a/jarvis_hud.py\n+++ b/jarvis_hud.py\n"
            + hunk(src[i_get - 4:i_get], get_add, src[i_get:i_get + 3], i_get - 3)
            + hunk(src[i_post - 4:i_post], post_add, src[i_post:i_post + 3], i_post - 3))


def verify(text: str) -> None:
    """Prove it on a copy of the real file: check, apply, reverse, compare.

    `-c core.autocrlf=false`: the temporary folder has no `.gitattributes`, so
    a machine with the usual Windows `autocrlf=true` would have git rewrite the
    file's endings mid-test and the byte-for-byte comparison below would fail
    for a reason that has nothing to do with the patch. The repository is LF
    everywhere and the real backend file is LF, so the ending is pinned here
    too rather than left to a global setting.
    """
    git = ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf"]
    with tempfile.TemporaryDirectory(prefix="jarvis-tasks-patch-") as tmp:
        d = Path(tmp)
        original = REAL.read_bytes()
        (d / "jarvis_hud.py").write_bytes(original)
        (d / "p.patch").write_bytes(text.encode("utf-8"))
        subprocess.run(git[:1] + ["init", "-q", "."], cwd=d, check=True)
        for args in (["apply", "--check", "p.patch"], ["apply", "p.patch"],
                     ["apply", "--reverse", "p.patch"]):
            r = subprocess.run(git + args, cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        back = (d / "jarvis_hud.py").read_bytes()
        if back != original:
            raise SystemExit(
                "reversing did not give the file back byte for byte "
                f"({len(back)} bytes vs {len(original)})")
    print("rehearsed against the real jarvis_hud.py: applies, and reverses cleanly")


def main() -> int:
    if not REAL.exists():
        print(f"no {REAL.relative_to(ROOT)} - this checkout has no base backend")
        return 1
    text = build()
    if "--check" in sys.argv[1:]:
        # CI's mode: the patch must match what the real file would generate.
        # Without this, a patch can sit in the tree applying cleanly by luck
        # while the file it patches has moved on underneath it.
        have = OUT.read_text(encoding="utf-8") if OUT.exists() else None
        if have != text:
            print(f"OUT OF DATE: {OUT.relative_to(ROOT)} - run "
                  "python3 tools/gen_tasks_patch.py")
            return 1
        print("tasks.patch: up to date with the real jarvis_hud.py")
        return 0
    verify(text)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
