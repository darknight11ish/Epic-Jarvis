"""Write the job list's contract cases for BOTH apps, from the module itself.

    python3 tools/gen_tasks_cases.py            # write them
    python3 tools/gen_tasks_cases.py --check    # fail if they are stale (CI)

WHY A GENERATOR, AND WHY IT IMPORTS THE REAL MODULE

`jarvis_tasks.JobList.status()` is what both apps read, so nothing here is
hand-made: this builds a real job list in a temporary folder (never the
owner's), puts jobs into real states through the module's own calls, and
writes down exactly what `status()` returned. If the payload ever changes
shape, the fixture stops matching, the Kotlin contract test fails, and the
change has to be a decision rather than an accident - the same rule
`gen_menu_cases.py` and `gen_pc_help_cases.py` follow.

THE FOURTH CASE IS THE PRIVACY ONE

`status()` is counted only: ids, states, kinds, step counts and tool names,
never a task title and never a step's text. The `title_is_ignored` case takes
a real payload and ADDS a `title` to a row, so each client's test can prove it
renders nothing from a field it was never sent - a leak that would only ever
be noticed by reading the screen, never by a crash.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "tasks-cases.json"
PHONE = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract" / "tasks-cases.json"


def _job_list(tmp: Path):
    """A real JobList on a throwaway database, never the owner's."""
    os.environ["JARVIS_TASKS_DB"] = str(tmp / "tasks.db")
    import importlib
    import jarvis_tasks
    importlib.reload(jarvis_tasks)          # pick up the temp path
    return jarvis_tasks


def build() -> str:
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-task-cases-"))
    T = _job_list(tmp)
    jl = T.JobList()

    steps = [
        {"tool": "web_search", "args": {"q": "ferry times"}, "why": "find them",
         "acts": False},
        {"tool": "send_email", "args": {"to": "a@b.c"}, "why": "confirm", "risky": True},
        {"tool": "notes_write", "args": {}, "why": "file it", "acts": True},
    ]

    # One job part-way through and RUNNING (the state Pause and Cancel exist
    # for - claimed through the module's own _claim, so the lease is real),
    # one blocked by an interrupted step, one waiting on the owner's answer.
    running = jl.enqueue("Plan the trip", "book the ferry", list(steps), kind="plan")
    jl.tick(lambda step: {"ok": True})                 # step 1 done, checkpointed
    jl._claim(jl.store.get_task(running.id), T._now())  # and now mid-step 2

    blocked = jl.enqueue("Tidy the inbox", "archive a few", [
        {"tool": "tidy_inbox", "args": {}, "why": "clear it", "risky": True},
    ])
    back = jl.store.get_task(blocked.id)
    back.status, back.lease_id, back.lease_until = "running", "crashed", 0.0
    back.inflight = {"index": 0, "tool": "tidy_inbox", "acts": True}
    jl.store.save(back)
    jl.tick(lambda step: {"ok": True})                 # becomes blocked

    waiting = jl.enqueue("Send the note", "one email", [
        {"tool": "send_email", "args": {"to": "a@b.c"}, "why": "send it", "risky": True},
    ])
    jl.tick(lambda step: {"ok": True}, ask=lambda step: None)

    # One that stopped to ASK, so the fixture covers the answer box on both
    # apps and the question the wire has to carry for it.
    asking = jl.enqueue("Chase the order", "find out where it is", [
        {"tool": "email_check", "args": {}, "why": "look for the confirmation",
         "acts": False},
    ])
    got = jl.store.get_task(asking.id)
    got.status, got.question = "waiting_input", "Which order number is it?"
    jl.store.save(got)

    status = jl.status()

    # DETERMINISTIC, so `--check` means something. A job's id is a uuid4 and
    # the list is ordered by "most recently touched", so two runs would never
    # agree and every CI check would fail. The ids are replaced with stable
    # placeholders and the rows are sorted; nothing is lost, because a client
    # treats an id as an opaque string it hands straight back.
    status = json.loads(json.dumps(status))
    status["tasks"].sort(key=lambda t: (str(t.get("state")), t.get("step", 0),
                                        t.get("steps", 0)))
    for n, t in enumerate(status["tasks"], 1):
        t["id"] = f"job-{n}"

    cases = [
        {
            "id": "mixed",
            "why": "one job running mid-step, one blocked by an interrupted step, "
                   "one waiting on a card, one that stopped to ask a question",
            "answer": status,
            "expect": {
                "waiting": status["waiting"],
                "running": status["running"],
                "blocked": status["blocked"],
                "rows": len(status["tasks"]),
                "states": sorted(t["state"] for t in status["tasks"]),
            },
        },
        {
            "id": "empty",
            "why": "a PC with nothing queued - an empty list, not an error",
            "answer": {**status, "counts": {}, "waiting": 0, "running": 0,
                       "blocked": 0, "tasks": []},
            "expect": {"waiting": 0, "running": 0, "blocked": 0, "rows": 0, "states": []},
        },
        {
            "id": "older_backend",
            "why": "a PC that has not had the job list installed: 404 on the route",
            "answer": None,
            "expect": {"read": "OlderBackend"},
        },
        {
            "id": "title_is_ignored",
            "why": "the payload is counted only - a row that carries a `title` the "
                   "client was never sent must render nothing from it",
            "answer": {**status, "tasks": [{**t, "title": "SECRET TITLE"} for t in status["tasks"]]},
            "expect": {"rows": len(status["tasks"]),
                       "must_not_contain": ["SECRET TITLE"]},
        },
    ]
    doc = {
        "about": "GENERATED by tools/gen_tasks_cases.py from backend/jarvis_tasks.py "
                 "- do not edit by hand. run the tool after changing the payload; "
                 "CI runs --check.",
        "source": "jarvis_tasks.JobList().status() with real jobs in real states",
        # Keyed by case name, the same shape contracts/pc-help-cases.json uses,
        # so each client indexes it the same way (`cases["mixed"]`).
        "cases": {c.pop("id"): c for c in cases},
    }
    return json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    text = build()
    check = "--check" in sys.argv[1:]
    bad = []
    for path in (DESKTOP, PHONE):
        have = path.read_text(encoding="utf-8") if path.exists() else None
        if have == text:
            continue
        if check:
            bad.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            # newline="\n": without it a stale file would be rewritten CRLF on
            # Windows and LF elsewhere (the repository is LF everywhere).
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
    if bad:
        for p in bad:
            print(f"OUT OF DATE: {p.relative_to(ROOT)} - run python3 tools/gen_tasks_cases.py")
        return 1
    if check:
        print("tasks cases: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
