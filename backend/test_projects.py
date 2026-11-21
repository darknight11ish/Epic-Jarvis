"""test_projects.py - Projects, build steps 1 and 2 (jarvis_projects.py,
projects.patch, docs/JARVIS-API.md section 88, docs/PROJECTS-DESIGN.md), plus
step 4's label half (`project_facts`, 2026-10-15).

    python3 backend/test_projects.py

The owner's decision (CLAUDE.md, 2026-09-28): "Projects, like Claude's
Projects and more" - both coding and life projects; the owner's answers:
a Shareable switch per project, off by default; projects, goals,
benchmarks and charts first. What this proves, with real SQLite files in a
temporary folder, the REAL jarvis_documents.py folder list,
jarvis_schedule.list_key, jarvis_sensitive.topic and jarvis_quick.py (the
approval gate is a fake; no socket opens - a guard below fails the suite if
anything tries):

  - projects: create, list, get, update, delete; a name, a kind ("coding"
    or "life") that never changes, instructions capped at 1,500
    characters, at most 10 project notes of 200 characters, a limit on how
    many projects;
  - the folder: only one of "Folders Jarvis may look in" or a folder
    inside one; never for a life project; chosen on the PC only (cleared
    from anywhere); a folder later taken off the list shows as not listed;
  - Shareable: off by default, cannot be created on or edited on; ON is
    ONE change_own_config card at tier "ask" (no, timed out, the wrong
    tier, or turning it off while the card waits all leave it off); OFF
    is instant;
  - the work list is a named list on the one scheduler (jarvis_schedule.
    list_key's rules), never the to-do list itself, one project per list;
  - goal ids are kept on the project side (jarvis_goals.py is not on this
    branch);
  - benchmarks: a number the owner logs, or a coding command kept as words
    and marked not runnable (PC only, coding projects only, never logged
    by hand); dated results for a chart, oldest first; better or worse
    than last time, only when the owner said which way is better; a
    target; removing one number; limits;
  - sensitive: health and money names are marked from the name and unit
    ("Weight", "Savings", "Resting heart rate"), or by the owner; they are
    `keep_on_screen`; the owner's mark comes off at once, the name's only
    with ONE change_own_config card (the owner, 2026-09-28) - and comes
    back when the name or unit changes;
  - the quick command: "log 5 km run", "I ran 5 km", "my weight is 72 kg"
    and friends parse (and near misses do not); a sentence is ours only
    when a life benchmark fits it; the answer is private for a sensitive
    benchmark; with no projects.db nothing is created;
  - apps (docs/APPS-IN-PROJECTS-DESIGN.md, real git): a coding project may
    be a Jarvis-built app - new or adopted - never with a folder and never
    changed afterwards; an older projects.db gains the `app` column; the
    projects limit counts them; deleting one keeps the folder and lists it
    again as an unlinked app; a save that fails removes only the folder that
    call just made;
  - a project's LABELLED FACTS (2026-10-15, the label half of build step 4):
    the `project_facts` table in projects.db holds a fact ID and when it was
    labelled - never a fact's words; an older projects.db gains the table;
    labelling twice is one row; the cap; a fact that is not there (404) or is
    no longer current, forgotten or erased (409) cannot be labelled; Forget
    takes the label off AND calls the memory module's OWN Forget
    (`MemoryStore.retire()`, the call /api/memory/forget makes) so the fact
    stops being recalled everywhere, while the row and its words stay (Erase
    is a separate button); a memory layer that breaks leaves the LABEL in
    place rather than reporting a half-success; deleting a project takes only
    its labels; and a label really survives a projects.db whose rows are in
    the `-wal` side file (the owner's own agents.db reads 0 tables without
    its log). jarvis_projects.py reads no fact's words: the words come from
    jarvis_memory's own GET /api/memory/used, which MAX_FACTS is capped to
    match so a project's list is one call. The label's own half is driven
    with a FAKE memory layer (nothing here opens the owner's real memory.db);
    the bridge to the REAL jarvis_memory.py is proved in its own test;
  - the PLAN STORE (2026-11-19, PM1, docs/JARVIS-API.md section 88.7):
    milestones, work items, typed links and an append-only event log, added
    to the SAME projects.db by four new tables and seven nullable columns. The
    migration writes its own timestamped `projects.db.before-migrate-<stamp>`
    copy before the first schema statement and writes none on an up-to-date
    file; a backup that cannot be written refuses the migration and alters
    nothing. A 13-column database from before this opens, keeps every row, and
    gains the columns and tables without any table being rebuilt; a refused
    NOT NULL ALTER leaves the file byte-for-byte unchanged; a store shaped
    like the owner's own (2 coding projects, 1 app, 1 work list, 0 benchmarks,
    0 linked goals, 0 goals, 0 to-dos) migrates and answers honestly; ready
    work (priority then due date, and nothing open blocking it); an open
    blocker named by blocking_chain(); the DFS circle guard refusing a
    blocks/parent_child circle and writing nothing; the one project_next()
    union over ready items, active goals' next step and each project's first
    open work-list item; project_doctor() reporting contradictory rows without
    fixing one; and the three deterministic answers - "what am I working on",
    "what should I work on next", "what's blocking X" - answered from the
    store, naming projects.db and the date they read, with honest empty
    answers, ahead of the model, and as record reads an untagged request may
    use;
  - the PLAN STORE'S IMPORT AND TOOLS (2026-11-20, PM2): the import/seed
    reads goals.db's plan steps and the one scheduler's work-list items
    READ-ONLY and proposes them as milestones and work items behind ONE
    change_own_config card; a dry run writes nothing, a second run creates
    nothing new (every source row has one stable key in the append-only log),
    the source's own rough date label stays words and an imported item is
    undated unless the source row really had a date. The eight typed tools are
    driven through the REAL `_one_call`: the five owner-direct writes are
    cardless on a clean owner turn (the shipped "auto" `todo_add` line through
    the REAL published gate) and ONE card after outside text; the decomposed
    plan is ONE card that writes zero rows on a deny and runs nothing; the
    circle guards refuse with nothing written and no card; a status change
    leaves one project event and one Undo receipt that really puts the old
    status back; the hub note is ONE notes-editor card with the File Guardian
    copy first; and the acceptance case answers "what should I work on next?"
    from a REAL plan row after the import, not the empty answer;
  - THE EXECUTION AND BRIEF BRIDGES (2026-11-20, PM3): a work item due today
    or earlier appears in the one scheduler's daily to-do list with the same
    carry-over tag a to-do row gets ("from yesterday"), read-only - no
    schedule.db row is written and a second read is identical; the morning
    digest (jarvis_arbiter.digest()) lists work due within 48 hours, the top
    3 ready items and in_progress items untouched for more than seven days,
    without writing anything; a work item linked to a REAL durable job in
    jarvis_tasks.py follows the job's own state through the existing status
    path (queued/running -> in_progress, waiting_approval -> waiting_approval,
    succeeded -> in_review, a failed job reported and never given a made-up
    status, a done item never pulled back); a linked PR's state and CI are
    read through the REAL jarvis_github.py on a fake transport with NO card
    and no GitHub write, and a merged PR is an OFFER only; the ready read-out
    the phone and the voice path read is capped at 3; jarvis_undo restores a
    reverted status; a turn shaped by outside text still forces every
    owner-direct write to ONE ask card; the bridges add no model tool and no
    date is ever invented; and the hub note is refreshed from the store, never
    read back, with the bridge state in it. The Run Step DISPATCH is
    deliberately deferred - see the decisions fragment and ARCHITECTURE §8;
  - the routes, install() and the patch on the stack of earlier patches;
  - the audit log never carries a name, a note or a number.

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
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_projects.py", "jarvis_quick.py", "jarvis_schedule.py",
                "jarvis_documents.py", "jarvis_sensitive.py",
                # PM2 (2026-11-20): the tests below drive the REAL model tools
                # through jarvis_agent, and the import/seed reads goals.db and
                # the scheduler read-only.
                "jarvis_agent.py", "jarvis_goals.py", "jarvis_receipts.py",
                "jarvis_notes_edit.py", "jarvis_file_guardian.py",
                "jarvis_claims.py", "jarvis_reach.py",
                "jarvis_tool_profiles.py",
                # PM3 (2026-11-20): the execution and brief bridges drive the
                # REAL GitHub reader (with a fake transport), the REAL durable
                # task list and the REAL morning digest.
                "jarvis_github.py", "jarvis_tasks.py", "jarvis_arbiter.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-projects-"))
#: Every project edit in this suite now leaves a receipt. Pointed at this
#: suite's own temporary folder BEFORE jarvis_receipts is imported, so a test
#: run can never write into the owner's real one (the same shape as
#: test_receipts.py's own SCRATCH).
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
#: Project Mode now snapshots its pointer file through the guardian first, so
#: this suite's copy of the time-machine store lives in its temp folder too.
os.environ["OPENJARVIS_HOME"] = str(_TMP / "guardian-home")
#: PM3 (2026-11-20): the durable task list is read by the work-item bridge, so
#: point its default store at this suite's temporary folder BEFORE anything can
#: open it - a test run must never touch the owner's real tasks.db.
os.environ["JARVIS_TASKS_DB"] = str(_TMP / "tasks-default.db")
_AUDIT = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: _AUDIT.append((event, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw


# No network, anywhere in this suite: any socket that tries to connect fails
# the check below.
_NET = []
_real_connect = socket.socket.connect


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_projects.py: no network")


socket.socket.connect = _no_connect

import jarvis_projects as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def raises(fn, exc=Exception) -> str:
    try:
        fn()
    except exc as e:
        return str(e) or type(e).__name__
    return ""


_N = [0]


def fresh(clock=None) -> P.Projects:
    _N[0] += 1
    return P.Projects(_TMP / f"projects-{_N[0]}.db", clock=clock or time.time)


# Folders Jarvis may look in: one real folder, listed the way
# jarvis_documents.py keeps it (folders.json in the settings folder).
LISTED = _TMP / "Code"
(LISTED / "jarvis-desktop").mkdir(parents=True)
OUTSIDE = _TMP / "Elsewhere"
OUTSIDE.mkdir()
(_TMP / "folders.json").write_text(json.dumps(
    {"folders": [{"path": str(LISTED.resolve()), "added": 1.0}]}), encoding="utf-8")


# --------------------------------------------------------------------------
#   Projects
# --------------------------------------------------------------------------


def t_create_list_get_update_delete():
    s = fresh()
    check("no projects.db until something is created", s.list() == [] and not s.exists())
    p = s.create({"name": "Half marathon", "kind": "life",
                  "instructions": "Keep me honest about rest days.",
                  "notes": ["Race is 12 April", "Left knee: easy on hills"],
                  "goals": ["g1", "g2", "g1"]}, here=False)
    check("a life project is created from either app, no card",
          p["name"] == "Half marathon" and p["kind"] == "life" and p["folder"] is None)
    check("instructions and notes are kept as typed",
          p["instructions"] == "Keep me honest about rest days."
          and p["notes"] == ["Race is 12 April", "Left knee: easy on hills"])
    check("goal ids are kept on the project side, once each", p["goals"] == ["g1", "g2"])
    check("Shareable is off by default", p["shareable"] is False)
    check("the work list defaults to a named list from the project's name",
          p["work_list"] == {"name": "half marathon", "title": "Half marathon list"})
    lst = s.list()
    check("list shows it, without the long fields",
          len(lst) == 1 and lst[0]["id"] == p["id"] and "instructions" not in lst[0])
    got = s.get(p["id"])
    check("get shows the long fields and the benchmarks",
          got["instructions"] and got["benchmark_list"] == [] and got["max"]["instructions"] == 1500)
    up = s.update(p["id"], {"name": "Spring half marathon", "notes": ["Race is 12 April"],
                            "instructions": ""}, here=False)
    check("update changes only what was sent",
          up["name"] == "Spring half marathon" and up["notes"] == ["Race is 12 April"]
          and up["instructions"] == "" and up["goals"] == ["g1", "g2"])
    check("a kind never changes",
          "kind cannot change" in raises(lambda: s.update(p["id"], {"kind": "coding"},
                                                          here=True)))
    check("a second project with the same name is refused",
          "already a project" in raises(lambda: s.create(
              {"name": "spring HALF marathon", "kind": "life"}, here=False)))
    check("a kind other than coding or life is refused",
          "coding" in raises(lambda: s.create({"name": "X", "kind": "work"}, here=False)))
    check("a name is required", "empty" in raises(lambda: s.create(
        {"name": "  ", "kind": "life"}, here=False)))
    s.delete(p["id"])
    check("delete removes it", s.list() == [])
    check("a missing project is a KeyError (404)", bool(raises(lambda: s.get(p["id"]),
                                                               KeyError)))
    check("an id that is not ours is a KeyError, never a query",
          bool(raises(lambda: s.get("'; DROP TABLE projects; --"), KeyError)))


def t_caps():
    s = fresh()
    check("instructions over 1,500 characters are refused",
          "at most 1500" in raises(lambda: s.create(
              {"name": "A", "kind": "life", "instructions": "x" * 1501}, here=False)))
    ok = s.create({"name": "A", "kind": "life", "instructions": "x" * 1500}, here=False)
    check("exactly 1,500 is fine", len(ok["instructions"]) == 1500)
    check("more than 10 notes are refused", "at most 10" in raises(lambda: s.update(
        ok["id"], {"notes": [f"n{i}" for i in range(11)]}, here=False)))
    check("a note over 200 characters is refused", "at most 200" in raises(lambda: s.update(
        ok["id"], {"notes": ["y" * 201]}, here=False)))
    check("a note is one line", "one line" in raises(lambda: s.update(
        ok["id"], {"notes": ["a\nb"]}, here=False)))
    check("a name over 60 characters is refused", "at most 60" in raises(lambda: s.create(
        {"name": "n" * 61, "kind": "life"}, here=False)))
    check("a bad goal id is refused", "goal id" in raises(lambda: s.update(
        ok["id"], {"goals": ["no spaces please"]}, here=False)))
    old = P.MAX_PROJECTS
    P.MAX_PROJECTS = 2
    try:
        s.create({"name": "B", "kind": "life"}, here=False)
        check("the project limit is kept", "already 2" in raises(lambda: s.create(
            {"name": "C", "kind": "life"}, here=False), OverflowError))
    finally:
        P.MAX_PROJECTS = old


def t_folder_must_be_an_allowed_folder():
    s = fresh()
    sub = LISTED / "jarvis-desktop"
    p = s.create({"name": "Jarvis Desktop", "kind": "coding", "folder": str(sub)}, here=True)
    check("a folder inside one of \"Folders Jarvis may look in\" is fine (on the PC)",
          p["folder"]["path"] == os.path.realpath(sub) and p["folder"]["listed"] is True
          and p["folder"]["name"] == "jarvis-desktop")
    q = s.create({"name": "Code", "kind": "coding", "folder": str(LISTED)}, here=True)
    check("the listed folder itself is fine", q["folder"]["listed"] is True)
    check("a folder not on the list is refused, and says where to add it",
          "not on \"Folders Jarvis may look in\"" in raises(lambda: s.create(
              {"name": "Other", "kind": "coding", "folder": str(OUTSIDE)}, here=True)))
    check("a folder that does not exist is refused",
          "does not exist" in raises(lambda: s.create(
              {"name": "Gone", "kind": "coding", "folder": str(LISTED / "nope")}, here=True)))
    check("a life project has no folder", "no folder" in raises(lambda: s.create(
        {"name": "Run", "kind": "life", "folder": str(LISTED)}, here=True)))
    check("choosing a folder from the phone is refused (PC only)",
          "PC only" in raises(lambda: s.create(
              {"name": "Phone", "kind": "coding", "folder": str(LISTED)}, here=False),
              PermissionError))
    check("... and so is changing it", "PC only" in raises(lambda: s.update(
        p["id"], {"folder": str(LISTED)}, here=False), PermissionError))
    c = s.update(q["id"], {"folder": None}, here=False)
    check("clearing a folder works from either app (Jarvis sees less)", c["folder"] is None)
    # The folder is taken off "Folders Jarvis may look in" later.
    real = (_TMP / "folders.json").read_text(encoding="utf-8")
    try:
        (_TMP / "folders.json").write_text(json.dumps({"folders": []}), encoding="utf-8")
        got = s.get(p["id"])
        check("a folder no longer on the list shows as not listed, in words",
              got["folder"]["listed"] is False and "no longer" in got["folder"]["said"])
    finally:
        (_TMP / "folders.json").write_text(real, encoding="utf-8")
    code, out = P.handle_post("/api/projects", {"name": "Phone2", "kind": "coding",
                                                "folder": str(LISTED)}, here=False, store=s)
    check("the route answers 403 with pc_only for a folder from the phone",
          code == 403 and out.get("pc_only") is True)


def t_shareable_off_by_default_and_one_card_to_turn_on():
    s = fresh()
    p = s.create({"name": "App", "kind": "coding"}, here=True)
    check("Shareable starts off", p["shareable"] is False)
    check("a project cannot be created Shareable",
          "starts with Shareable off" in raises(lambda: s.create(
              {"name": "B", "kind": "coding", "shareable": True}, here=True)))
    check("an ordinary edit cannot turn it on",
          "asks you first" in raises(lambda: s.update(p["id"], {"shareable": True},
                                                      here=True)))
    cards = []

    class V:
        def __init__(self, allowed, outcome, tier="ask"):
            self.allowed, self.outcome, self.tier = allowed, outcome, tier

    def gate_says(v):
        def g(action, detail, prompt):
            cards.append((action, detail, prompt))
            return v
        return g

    now = lambda fn: fn()  # noqa: E731 - run the card at once
    code, out = P.request_shareable(p["id"], {"on": True}, store=s,
                                    gate=gate_says(V(False, "denied")),
                                    tier_of=lambda a: "ask", spawn=now)
    check("ON raises ONE card, change_own_config", code == 202 and len(cards) == 1
          and cards[0][0] == "change_own_config")
    check("the card says nothing is sent, and what is never shared",
          "Nothing is sent" in cards[0][2] and "health or money" in cards[0][2]
          and "nothing changes" in cards[0][2])
    check("a no leaves it off, and says so", s.get(p["id"])["shareable"] is False
          and s.get(p["id"])["shareable_last"]["outcome"] == "denied")
    P.request_shareable(p["id"], {"on": True}, store=s, gate=gate_says(V(False, "timed_out")),
                        tier_of=lambda a: "ask", spawn=now)
    check("a timed-out card leaves it off", s.get(p["id"])["shareable"] is False)
    P.request_shareable(p["id"], {"on": True}, store=s,
                        gate=gate_says(V(True, "approved", tier="auto")),
                        tier_of=lambda a: "ask", spawn=now)
    check("an 'allowed' at a tier that is not a person's yes leaves it off",
          s.get(p["id"])["shareable"] is False)
    code, _ = P.request_shareable(p["id"], {"on": True}, store=s,
                                  gate=gate_says(V(True, "approved")),
                                  tier_of=lambda a: "auto", spawn=now)
    check("change_own_config not at tier ask: refused before any card", code == 503)
    code, out = P.request_shareable(p["id"], {"on": True}, store=s,
                                    gate=gate_says(V(True, "approved")),
                                    tier_of=lambda a: "ask", spawn=now)
    check("a real yes turns it on", code == 202 and s.get(p["id"])["shareable"] is True)
    code, out = P.request_shareable(p["id"], {"on": False}, store=s)
    check("OFF is instant, no card", code == 200 and out["project"]["shareable"] is False)
    # Turned off while the card waits: the late yes changes nothing.
    held = []
    code, _ = P.request_shareable(p["id"], {"on": True}, store=s,
                                  gate=gate_says(V(True, "approved")),
                                  tier_of=lambda a: "ask", spawn=held.append)
    check("while a card waits, the project says so",
          code == 202 and s.get(p["id"])["shareable_waiting"] is True)
    code2, _ = P.request_shareable(p["id"], {"on": True}, store=s,
                                   gate=gate_says(V(True, "approved")),
                                   tier_of=lambda a: "ask", spawn=held.append)
    check("a second card for the same project is refused while one waits", code2 == 409)
    P.request_shareable(p["id"], {"on": False}, store=s)
    held[0]()
    got = s.get(p["id"])
    check("turning it off while the card waits wins over a late yes",
          got["shareable"] is False and got["shareable_last"]["outcome"] == "withdrawn")
    code, _ = P.request_shareable(p["id"], {"on": "yes"}, store=s)
    check("{\"on\"} must be true or false", code == 400)
    code, _ = P.handle_post(f"/api/projects/{p['id']}/shareable", {"on": False}, store=s)
    check("the shareable route is reachable through handle_post", code == 200)


def t_work_list_is_a_named_scheduler_list():
    s = fresh()
    a = s.create({"name": "Garden", "kind": "life", "work_list": "garden jobs"}, here=False)
    check("a named list, kept the scheduler's way", a["work_list"]["name"] == "garden jobs")
    check("the to-do list itself cannot be a project's list",
          "to-do list" in raises(lambda: s.create(
              {"name": "B", "kind": "life", "work_list": "to-do"}, here=False)))
    check("a list name the scheduler would refuse is refused",
          "one to three plain words" in raises(lambda: s.create(
              {"name": "C", "kind": "life", "work_list": "my 2026 plans!"}, here=False)))
    check("one list belongs to one project",
          "already belongs" in raises(lambda: s.create(
              {"name": "D", "kind": "life", "work_list": "garden jobs"}, here=False),
              OverflowError))
    e = s.create({"name": "App 2.0!", "kind": "coding"}, here=True)
    check("a name that cannot be a list's name just gets no work list",
          e["work_list"] is None)
    f = s.update(a["id"], {"work_list": None}, here=False)
    check("the work list can be taken off", f["work_list"] is None)


# --------------------------------------------------------------------------
#   Benchmarks
# --------------------------------------------------------------------------


def t_benchmarks_number_and_command():
    t = [1_000_000.0]
    s = fresh(clock=lambda: t[0])
    life = s.create({"name": "Half marathon", "kind": "life"}, here=False)
    code = s.create({"name": "Jarvis Desktop", "kind": "coding"}, here=True)
    b = s.add_benchmark(life["id"], {"name": "Long run", "unit": "km", "better": "higher",
                                     "target": 21.1}, here=False)
    check("a number benchmark, from either app", b["kind"] == "number" and b["unit"] == "km"
          and b["results"] == 0 and b["latest"] is None and b["change"] is None)
    check("a life project's benchmark cannot be a command",
          "numbers you log" in raises(lambda: s.add_benchmark(
              life["id"], {"name": "Tests", "kind": "command", "command": "pytest"},
              here=True)))
    check("a command is written on the PC only",
          "PC only" in raises(lambda: s.add_benchmark(
              code["id"], {"name": "Tests", "kind": "command", "command": "pytest -q"},
              here=False), PermissionError))
    cb = s.add_benchmark(code["id"], {"name": "Tests", "kind": "command",
                                      "command": "pytest -q", "better": "higher"}, here=True)
    check("a coding command is kept word for word and marked not runnable yet",
          cb["command"] == "pytest -q" and cb["runnable"] is False
          and "later step" in cb["not_runnable_why"])
    check("a command's results are never logged by hand",
          "later step" in raises(lambda: s.log(code["id"], cb["id"], 41)))
    check("changing a command's words is PC only",
          "PC only" in raises(lambda: s.update_benchmark(
              code["id"], cb["id"], {"command": "rm -rf /"}, here=False), PermissionError))
    check("a command over 300 characters is refused",
          "at most 300" in raises(lambda: s.update_benchmark(
              code["id"], cb["id"], {"command": "x" * 301}, here=True)))
    check("a number benchmark has no command",
          "no command" in raises(lambda: s.add_benchmark(
              life["id"], {"name": "Pace", "command": "echo"}, here=True)))
    check("the same name twice in one project is refused",
          "already has a benchmark" in raises(lambda: s.add_benchmark(
              life["id"], {"name": "long RUN"}, here=False), OverflowError))
    check("better is higher, lower or left out",
          "higher" in raises(lambda: s.add_benchmark(
              life["id"], {"name": "Pace", "better": "up"}, here=False)))
    # Logging: no card, dated, oldest first for the chart.
    t[0] += 86400
    s.log(life["id"], b["id"], 8)
    t[0] += 86400
    out = s.log(life["id"], b["id"], "10.5")
    check("logging returns the new number and the change",
          out["logged"]["value"] == 10.5 and out["latest"]["value"] == 10.5
          and out["change"]["verdict"] == "better" and out["change"]["direction"] == "up")
    t[0] += 86400
    out = s.log(life["id"], b["id"], 9)
    check("worse than last time, when higher is better",
          out["change"]["verdict"] == "worse" and "Worse than last time" in out["change"]["said"])
    t[0] += 86400
    out = s.log(life["id"], b["id"], 21.1)
    check("the target is reached", out["change"]["target_reached"] is True)
    res = s.results(life["id"], b["id"])
    check("results for a chart: dated points, oldest first, the target alongside",
          [p["value"] for p in res["points"]] == [8, 10.5, 9, 21.1]
          and res["points"][0]["at"] < res["points"][-1]["at"] and res["target"] == 21.1)
    check("the chart can ask for fewer points (the newest)",
          [p["value"] for p in s.results(life["id"], b["id"], 2)["points"]] == [9, 21.1])
    back = s.log(life["id"], b["id"], 5, at=t[0] - 10 * 86400)
    check("a number can be logged for an earlier day, and sits in date order",
          s.results(life["id"], b["id"])["points"][0]["value"] == 5
          and back["latest"]["value"] == 21.1)
    check("a date far in the future is refused",
          "too far" in raises(lambda: s.log(life["id"], b["id"], 1, at=t[0] + 3 * 86400)))
    for bad in (float("nan"), float("inf"), True, "ten", None, 1e13):
        check(f"not a number: {bad!r} is refused", bool(raises(
            lambda bad=bad: s.log(life["id"], b["id"], bad))))
    s.delete_result(life["id"], b["id"], back["logged"]["id"])
    check("one logged number can be removed (a typo)",
          s.results(life["id"], b["id"])["results"] == 4)
    check("removing a number that is not there is a KeyError",
          bool(raises(lambda: s.delete_result(life["id"], b["id"], back["logged"]["id"]),
                      KeyError)))
    check("another project's benchmark is not reachable through this one",
          bool(raises(lambda: s.log(code["id"], b["id"], 1), KeyError)))
    old = P.MAX_BENCHMARKS
    P.MAX_BENCHMARKS = 2
    try:
        s.add_benchmark(life["id"], {"name": "Weekly km", "unit": "km"}, here=False)
        check("the benchmark limit is kept", "at most 2" in raises(
            lambda: s.add_benchmark(life["id"], {"name": "Third"}, here=False), OverflowError))
    finally:
        P.MAX_BENCHMARKS = old
    s.delete_benchmark(life["id"], b["id"])
    check("deleting a benchmark removes it and its numbers",
          len(s.get(life["id"])["benchmark_list"]) == 1)
    s.delete(life["id"])
    check("deleting a project removes its benchmarks", s.life_benchmarks() == [])


def t_better_or_worse():
    c = P.compare
    check("no number yet: nothing to say", c(None, None, "higher") is None)
    check("the first number says so", c(5, None, "higher")["said"] == "The first number.")
    check("lower is better: down is better", c(71, 72, "lower")["verdict"] == "better")
    check("lower is better: up is worse", c(73, 72, "lower")["verdict"] == "worse")
    check("the same is the same", c(5, 5, "higher")["verdict"] == "same")
    n = c(6, 5, None)
    check("without 'better', Jarvis does not guess - it only says higher",
          n["verdict"] is None and n["said"] == "Higher than last time (by 1).")
    check("target reached, lower is better", c(70, 72, "lower", target=70)["target_reached"])
    check("target not yet", c(71, 72, "lower", target=70)["target_reached"] is False)
    check("no target line without a direction", c(71, 72, None, target=70)["target_reached"]
          is None)


def t_sensitive_marking():
    s = fresh()
    p = s.create({"name": "Health", "kind": "life"}, here=False)
    cases = {"Weight": ("kg", "health"), "Body weight": ("", "health"),
             "Resting heart rate": ("bpm", "health"), "Calories": ("", "health"),
             "Blood pressure": ("mmHg", "health"), "Savings": ("", "money"),
             "Monthly spending": ("£", "money"), "Money saved": ("$", "money")}
    for name, (unit, why) in cases.items():
        b = s.add_benchmark(p["id"], {"name": name, "unit": unit}, here=False)
        check(f"{name!r} is sensitive ({why}), kept on screen",
              b["sensitive"] is True and b["sensitive_why"] == why and b["keep_on_screen"]
              and "never read aloud" in b["keep_on_screen_words"])
    q = s.create({"name": "Reading", "kind": "life"}, here=False)
    for name, unit in (("Pages read", "pages"), ("Long run", "km"), ("Steps", "steps"),
                       ("Push ups", "")):
        b = s.add_benchmark(q["id"], {"name": name, "unit": unit}, here=False)
        check(f"{name!r} is not sensitive", b["sensitive"] is False and not b["keep_on_screen"])
    m = s.add_benchmark(q["id"], {"name": "Guitar practice", "unit": "min",
                                  "sensitive": True}, here=False)
    check("the owner can mark any benchmark sensitive",
          m["sensitive"] and m["sensitive_why"] == "you marked it" and m["marked_by_you"])
    m2 = s.update_benchmark(q["id"], m["id"], {"sensitive": False}, here=False)
    check("... and take their own mark off", m2["sensitive"] is False)
    w = [b for b in s.get(p["id"])["benchmark_list"] if b["name"] == "Weight"][0]
    w2 = s.update_benchmark(p["id"], w["id"], {"sensitive": False}, here=False)
    check("a mark from the name stays (health stays health)",
          w2["sensitive"] is True and w2["sensitive_why"] == "health")
    # Written down in docs/PROJECTS-DESIGN.md "Build notes" as the owner's
    # call: jarvis_sensitive reads "5k" as money. Pinned here so a change to
    # that shows up, instead of the note quietly going stale.
    check("KNOWN false alarm: \"5k time\" is marked money (the owner can take it off "
          "with a card)", P.auto_sensitive("5k time", "min") == "money")


def t_unmark_automatic_mark_with_a_card():
    """The owner's answer of 2026-09-28: an automatic private mark can be
    removed by the owner, with a card first; the owner's own mark comes
    off with no card."""
    s = fresh()
    p = s.create({"name": "Half marathon", "kind": "life"}, here=False)
    b = s.add_benchmark(p["id"], {"name": "5k time", "unit": "min", "better": "lower"},
                        here=False)
    check("\"5k time\" starts marked (money), and says a card takes it off",
          b["sensitive"] and b["sensitive_why"] == "money" and b["mark_auto"] == "money"
          and b["unmark"] == "card" and b["mark_auto_removed"] is False
          and b["unmark_waiting"] is False)
    cards = []

    class V:
        def __init__(self, allowed, outcome, tier="ask"):
            self.allowed, self.outcome, self.tier = allowed, outcome, tier

    def gate_says(v):
        def g(action, detail, prompt):
            cards.append((action, detail, prompt))
            return v
        return g

    now = lambda fn: fn()  # noqa: E731
    pid, bid = p["id"], b["id"]

    def view():
        return s.results(pid, bid, 5)

    code, out = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(False, "denied")),
                                 tier_of=lambda a: "ask", spawn=now)
    check("removing an automatic mark raises ONE change_own_config card", code == 202
          and out["waiting"] is True and len(cards) == 1
          and cards[0][0] == "change_own_config")
    text = cards[0][2]
    check("the card names the benchmark, the project and why, in plain words",
          "\"5k time\"" in text and "\"Half marathon\"" in text and "looked like money" in text
          and "read these numbers aloud" in text and "If you say no: nothing changes" in text
          and "If you did not just do this, say no." in text)
    check("the card detail never leaves the PC", cards[0][1]["leaves_this_pc"] is False)
    check("a no keeps it private, and says so", view()["sensitive"] is True
          and view()["unmark_last"]["outcome"] == "denied"
          and "stay private" in view()["unmark_last"]["message"])
    P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(False, "timed_out")),
                     tier_of=lambda a: "ask", spawn=now)
    check("a timed-out card keeps it private", view()["sensitive"] is True)
    P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved", tier="auto")),
                     tier_of=lambda a: "ask", spawn=now)
    check("an 'allowed' at a tier that is not a person's yes keeps it private",
          view()["sensitive"] is True and view()["unmark_last"]["outcome"] == "refused")
    code, _ = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                               tier_of=lambda a: "auto", spawn=now)
    check("change_own_config not at tier ask: refused before any card", code == 503)
    n = len(cards)
    code, _ = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                               tier_of=lambda a: "ask", spawn=now)
    got = view()
    check("a real yes takes the automatic mark off", code == 202 and len(cards) == n + 1
          and got["sensitive"] is False and got["keep_on_screen"] is False
          and got["mark_auto"] == "money" and got["mark_auto_removed"] is True
          and got["unmark"] == "" and got["unmark_last"]["outcome"] == "off")
    lb = [x for x in s.life_benchmarks() if x["id"] == bid][0]
    check("the quick command sees it as not private any more", lb["sensitive"] is False)
    said = P.quick_log({"match": lb, "value": 24, "unit": "min"}, store=s)
    check("... so logging it by voice is no longer a private answer",
          said["private"] is False and "Logged 24 min" in said["said"])
    # The owner marks it again, then takes their OWN mark off: no card.
    m = s.update_benchmark(pid, bid, {"sensitive": True}, here=False)
    check("the owner can mark it private again, at once", m["sensitive"] is True
          and m["unmark"] == "instant" and m["sensitive_why"] == "you marked it")
    n = len(cards)
    code, out = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                                 tier_of=lambda a: "ask", spawn=now)
    check("the owner's own mark comes off with no card", code == 200 and len(cards) == n
          and out["changed"] is True and out["benchmark"]["sensitive"] is False)
    code, out = P.request_unmark(pid, bid, {}, store=s, tier_of=lambda a: "ask", spawn=now)
    check("unmarking an unmarked benchmark changes nothing", code == 200
          and out["changed"] is False)
    # A rename checks the name again.
    r = s.update_benchmark(pid, bid, {"name": "Best 5k time"}, here=False)
    check("renaming it checks the name again: the automatic mark is back",
          r["sensitive"] is True and r["unmark"] == "card" and r["mark_auto_removed"] is False)
    r = s.update_benchmark(pid, bid, {"better": "lower"}, here=False)
    check("an edit that is not the name or unit keeps it as it is", r["sensitive"] is True)
    # Renamed while the card waits: the late yes changes nothing.
    held = []
    code, _ = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                               tier_of=lambda a: "ask", spawn=held.append)
    check("while a card waits, the benchmark says so",
          code == 202 and view()["unmark_waiting"] is True)
    code2, _ = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                                tier_of=lambda a: "ask", spawn=held.append)
    check("a second card for the same benchmark is refused while one waits", code2 == 409)
    s.update_benchmark(pid, bid, {"name": "My 5k time"}, here=False)
    held[0]()
    got = view()
    check("renamed while the card waits: the late yes keeps it private",
          got["sensitive"] is True and got["unmark_last"]["outcome"] == "withdrawn"
          and got["unmark_waiting"] is False)
    # The owner marks it while the card waits: the late yes changes nothing.
    held = []
    P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                     tier_of=lambda a: "ask", spawn=held.append)
    s.update_benchmark(pid, bid, {"sensitive": True}, here=False)
    held[0]()
    got = view()
    check("marked again by the owner while the card waits: stays private",
          got["sensitive"] is True and got["mark_auto_removed"] is False
          and got["unmark_last"]["outcome"] == "withdrawn")
    # Both marks: the owner's comes off at once, Jarvis's asks.
    n = len(cards)
    code, out = P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(False, "denied")),
                                 tier_of=lambda a: "ask", spawn=now)
    got = view()
    check("both marks: the owner's comes off at once, Jarvis's waits for the card",
          code == 202 and out["changed"] is True and len(cards) == n + 1
          and got["marked_by_you"] is False and got["sensitive"] is True)
    # A card whose benchmark is deleted while it waits.
    held = []
    P.request_unmark(pid, bid, {}, store=s, gate=gate_says(V(True, "approved")),
                     tier_of=lambda a: "ask", spawn=held.append)
    s.delete_benchmark(pid, bid)
    held[0]()
    check("a benchmark deleted while its card waits: nothing is written",
          P._M_STATE["last"][bid]["outcome"] == "withdrawn")
    # The route.
    b2 = s.add_benchmark(pid, {"name": "Savings", "unit": "$"}, here=False)
    code, out = P.handle_post(f"/api/projects/{pid}/benchmarks/{b2['id']}/unmark", {},
                              store=s, gate=gate_says(V(False, "denied")),
                              tier_of=lambda a: "ask", spawn=now)
    check("the unmark route is reachable through handle_post", code == 202)
    code, _ = P.handle_post(f"/api/projects/{pid}/benchmarks/{'9' * 32}/unmark", {}, store=s)
    check("unmarking an unknown benchmark is a 404", code == 404)


def t_an_older_projects_db_gains_the_new_column():
    import sqlite3
    path = _TMP / "old-projects.db"
    c = sqlite3.connect(str(path))
    c.executescript(P._SCHEMA.replace("    auto_cleared TEXT,\n", ""))
    c.commit()
    c.close()
    s = P.Projects(path)
    p = s.create({"name": "Old", "kind": "life"}, here=False)
    b = s.add_benchmark(p["id"], {"name": "Weight", "unit": "kg"}, here=False)
    check("a projects.db from steps 1 and 2 opens and gains auto_cleared",
          b["sensitive"] is True and b["unmark"] == "card")


def _rmtree(path):
    """shutil.rmtree that can also delete what git wrote. Git marks its object
    files READ-ONLY, and Windows refuses to unlink a read-only file - POSIX does
    not care, so a plain rmtree works in CI and quietly left every earlier
    test's app folders behind on the owner's PC. That is why the names checked
    below came back with "doomed", "notes-app" and the rest (2026-10-03).

    THE MODE MUST KEEP READ AND EXECUTE. `stat.S_IWRITE` alone is 0o200: on
    Windows that is "not read-only", which is what this needs, but on POSIX it
    strips a DIRECTORY's read and execute bits - so the walk that clears the
    flag left an undeletable tree behind, and CI failed on the leftover folders
    instead of on this suite's own subject (2026-10-04). 0o700 is right on
    both: writable on Windows, still listable and traversable on POSIX.
    """
    for dirpath, dirnames, filenames in os.walk(path):
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            try:
                os.chmod(full, stat.S_IRWXU
                         if os.path.isdir(full) else stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


def _git_here() -> bool:
    if shutil.which("git") is None:
        print("SKIP  git is not installed here - the app tests below need it")
        return False
    # Every app test starts with no app folders at all.
    import jarvis_app_workspace as W
    _rmtree(W.root())
    return True


def t_an_older_projects_db_gains_the_app_column():
    import sqlite3
    path = _TMP / "older-projects.db"
    c = sqlite3.connect(str(path))
    c.executescript(P._SCHEMA.replace("    changed REAL NOT NULL,\n    app TEXT\n",
                                      "    changed REAL NOT NULL\n"))
    cols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    check("the test's old file really has no app column", "app" not in cols)
    c.execute("INSERT INTO projects (id, name, kind, created, changed) VALUES "
              "('" + "a" * 32 + "', 'Before apps', 'coding', 1, 1)")
    c.commit()
    c.close()
    s = P.Projects(path)
    old = s.get("a" * 32)
    check("a projects.db from before apps opens; its project has no app", old["app"] is None)
    c = sqlite3.connect(str(path))
    cols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    idx = [r[1] for r in c.execute("PRAGMA index_list(projects)").fetchall()]
    c.close()
    check("... and gains the app column and the one-project-per-app index",
          "app" in cols and "projects_by_app" in idx, (cols, idx))


def t_apps_new_and_adopted():
    if not _git_here():
        return
    import jarvis_app_workspace as W
    s = fresh()
    code, body = P.handle_post("/api/projects", {"name": "Notes app!", "kind": "coding",
                                                 "app": {"type": "web"}}, store=s)
    p = body.get("project") or {}
    check("a new app project: 200, a coding project with an app and no folder",
          code == 200 and p.get("kind") == "coding" and p.get("folder") is None
          and (p.get("app") or {}).get("name") == "notes-app"
          and (p["app"]["type"], p["app"]["title"]) == ("web", "Notes app!"), body)
    check("its folder is a real app under apps/, made by the workspace",
          [a["name"] for a in W.list_projects()] == ["notes-app"])
    check("the list shows the short form: no git, a task count, no card waiting",
          s.list()[0]["app"] == {"name": "notes-app", "type": "web", "tasks": 0,
                                 "merge_waiting": False}, s.list())
    code, body = P.handle_post("/api/projects", {"name": "Notes app?", "kind": "coding",
                                                 "app": {"type": "android"}}, store=s)
    check("a second project whose name makes the same folder name gets -2",
          code == 200 and body["project"]["app"]["name"] == "notes-app-2", body)
    code, body = P.handle_post("/api/projects", {"name": "???", "kind": "coding",
                                                 "app": {"type": "web"}}, store=s)
    check("a name with nothing to make a folder name from gives `app`",
          code == 200 and body["project"]["app"]["name"] == "app", body)
    check("no app is unlinked while every one has a project", s.unlinked_apps() == [])

    # Adopt
    W.create_project("old-notes", "android", "Old notes")
    check("an app folder with no project is offered as unlinked",
          s.unlinked_apps() == [{"name": "old-notes", "type": "android", "title": "Old notes"}])
    code, body = P.handle_post("/api/projects", {"kind": "coding",
                                                 "app": {"adopt": "old-notes"}}, store=s)
    check("adopting: the project takes the app's own title as its name",
          code == 200 and body["project"]["name"] == "Old notes"
          and body["project"]["app"]["name"] == "old-notes"
          and body["project"]["app"]["type"] == "android", body)
    check("... and it is no longer offered", s.unlinked_apps() == [])
    code, body = P.handle_post("/api/projects", {"name": "Twice", "kind": "coding",
                                                 "app": {"adopt": "old-notes"}}, store=s)
    check("an app that already has a project cannot be adopted again: 409",
          code == 409 and "already has a project" in body["error"], body)
    code, body = P.handle_post("/api/projects", {"name": "Ghost", "kind": "coding",
                                                 "app": {"adopt": "ghost"}}, store=s)
    check("a name that is not an app folder: 404, in its own words",
          code == 404 and body["error"] == "There is no app folder with that name.", body)
    code, body = P.handle_post("/api/projects", {"name": "Bad", "kind": "coding",
                                                 "app": {"adopt": "../x"}}, store=s)
    check("a path is not a folder name: 400", code == 400, body)
    (W.root() / "not-git").mkdir()
    code, body = P.handle_post("/api/projects", {"name": "Plain", "kind": "coding",
                                                 "app": {"adopt": "not-git"}}, store=s)
    check("a folder that is not a git app cannot be adopted: 404", code == 404, body)


def t_apps_never_with_a_folder():
    if not _git_here():
        return
    s = fresh()
    code, body = P.handle_post("/api/projects", {"name": "Both", "kind": "coding",
                                                 "folder": "C:\\x", "app": {"type": "web"}},
                               store=s, here=True)
    check("an app and a folder together: 400, said plainly",
          code == 400 and body["error"] == "A project has a folder or an app, not both.", body)
    code, body = P.handle_post("/api/projects", {"name": "Life", "kind": "life",
                                                 "app": {"type": "web"}}, store=s)
    check("a life project cannot be an app: 400", code == 400, body)
    for bad in ({"type": "ios"}, {}, "web", {"adopt": 5}):
        code, body = P.handle_post("/api/projects", {"name": "Odd", "kind": "coding",
                                                     "app": bad}, store=s)
        check(f"a bad app request {bad!r} is a 400, not a folder", code == 400, body)
    check("none of those left a project or a folder behind",
          s.list() == [] and not (P._workspace().root().is_dir()
                                  and [a for a in P._workspace().list_projects()
                                       if a["name"] in ("both", "life", "odd")]))
    made = P.handle_post("/api/projects", {"name": "Mine", "kind": "coding",
                                           "app": {"type": "web"}}, store=s)[1]["project"]
    code, body = P.handle_post(f"/api/projects/{made['id']}", {"app": {"type": "android"}},
                               store=s)
    check("`app` cannot be edited afterwards: 400",
          code == 400 and body["error"] == "An app is chosen when the project is made.", body)
    code, body = P.handle_post(f"/api/projects/{made['id']}", {"folder": "C:\\x"}, store=s,
                               here=True)
    check("a folder cannot be given to an app project, even on the PC: 400",
          code == 400 and body["error"] == "This project's files are its app.", body)
    code, body = P.handle_post(f"/api/projects/{made['id']}", {"folder": ""}, store=s)
    check("clearing a folder an app project never had is harmless", code == 200, body)
    code, body = P.handle_post(f"/api/projects/{made['id']}", {"name": "Renamed"}, store=s)
    check("an app project can still be renamed; its app stays",
          code == 200 and body["project"]["app"]["name"] == "mine", body)
    life = P.handle_post("/api/projects", {"name": "Run", "kind": "life"}, store=s)[1]["project"]
    code, body = P.handle_post(f"/api/projects/{life['id']}", {"app": {"type": "web"}}, store=s)
    check("a project that is not an app cannot become one: 400", code == 400, body)


def t_apps_count_toward_the_limit_and_failed_saves_clean_up():
    if not _git_here():
        return
    import jarvis_app_workspace as W
    s = fresh()
    keep = P.MAX_PROJECTS
    P.MAX_PROJECTS = 1
    try:
        P.handle_post("/api/projects", {"name": "First", "kind": "coding",
                                        "app": {"type": "web"}}, store=s)
        code, body = P.handle_post("/api/projects", {"name": "Second", "kind": "coding",
                                                     "app": {"type": "web"}}, store=s)
        check("an app project counts toward the projects limit: 409, and no folder made",
              code == 409 and [a["name"] for a in W.list_projects()] == ["first"], body)
    finally:
        P.MAX_PROJECTS = keep
    code, body = P.handle_post("/api/projects", {"name": "first", "kind": "coding",
                                                 "app": {"type": "web"}}, store=s)
    check("a name used twice: 409, and no second folder is made",
          code == 409 and [a["name"] for a in W.list_projects()] == ["first"], body)

    # A save that fails AFTER the folder was made removes that folder, and
    # only that one. The id already in use makes the insert fail.
    s2 = fresh()
    W.create_project("precious", "web", "Precious")
    (W.project_dir("precious") / "keep.txt").write_text("mine\n")
    first_id = P.handle_post("/api/projects", {"name": "Existing", "kind": "coding",
                                               "app": {"adopt": "precious"}},
                             store=s2)[1]["project"]["id"]
    real_id = P._new_id
    P._new_id = lambda: first_id
    try:
        code, body = P.handle_post("/api/projects", {"name": "Doomed", "kind": "coding",
                                                     "app": {"type": "web"}}, store=s2)
    finally:
        P._new_id = real_id
    names = [a["name"] for a in W.list_projects()]
    check("a failed save answers with an error, not a stack trace", code >= 400
          and body.get("ok") is False, (code, body))
    check("... removes the folder that call just made", "doomed" not in names, names)
    check("... and never another: the earlier app and its files survive",
          "precious" in names and (W.project_dir("precious") / "keep.txt").is_file(), names)


def t_apps_delete_keeps_the_folder():
    if not _git_here():
        return
    import jarvis_app_workspace as W
    s = fresh()
    pid = P.handle_post("/api/projects", {"name": "Keeper", "kind": "coding",
                                          "app": {"type": "web"}}, store=s)[1]["project"]["id"]
    s.add_benchmark(pid, {"name": "Bundle size", "unit": "KB"}, here=False)
    (W.project_dir("keeper") / "extra.txt").write_text("still here\n")
    code, body = P.handle_post(f"/api/projects/{pid}/delete", {}, store=s)
    check("deleting an app project answers app_kept with the folder's name",
          code == 200 and body == {"ok": True, "deleted": True, "app_kept": "keeper"}, body)
    check("... the folder and its files are still there",
          (W.project_dir("keeper") / "extra.txt").is_file())
    check("... and it is offered again as an unlinked app",
          s.unlinked_apps() == [{"name": "keeper", "type": "web", "title": "Keeper"}])
    life = P.handle_post("/api/projects", {"name": "Run", "kind": "life"}, store=s)[1]["project"]
    code, body = P.handle_post(f"/api/projects/{life['id']}/delete", {}, store=s)
    check("a project that is not an app: no app_kept in the answer",
          body == {"ok": True, "deleted": True}, body)
    other = P.handle_post("/api/projects", {"name": "Walk", "kind": "life"},
                          store=s)[1]["project"]["id"]
    check("the store's own delete() still answers True", s.delete(other) is True)


# --------------------------------------------------------------------------
#   The quick command
# --------------------------------------------------------------------------


def t_quick_parser():
    yes = {
        "log 5 km run": (5, "km", {"run"}),
        "Log 5 km run.": (5, "km", {"run"}),
        "Jarvis, log 5 km for my morning run please": (5, "km", {"morning", "run"}),
        "log 5k run": (5, "k", {"run"}),
        "log my weight as 72.5 kg": (72.5, "kg", {"weight"}),
        "log weight 72.5 kg": (72.5, "kg", {"weight"}),
        "record my savings at $200": (200, "$", {"save"}),
        "I ran 5 km": (5, "km", {"run"}),
        "I ran 5.2 km today": (5.2, "km", {"run"}),
        "I ran five kilometres": (5, "kilometres", {"run"}),
        "I weighed 72,5 kg this morning": (72.5, "kg", {"weight"}),
        "I walked 10,000 steps today": (10000, "steps", {"walk", "step"}),
        "I did 20 push ups": (20, "push", {"push", "up"}),
        "I read 30 pages yesterday": (30, "pages", {"read", "page"}),
        "I saved $50": (50, "$", {"save"}),
        "I cycled 20 miles": (20, "miles", {"cycle"}),
        "my weight is 72 kg": (72, "kg", {"weight"}),
        "log 30 pages": (30, "pages", {"page"}),
    }
    for text, (v, unit, words) in yes.items():
        got = P.parse_log(text)
        check(f"parses: {text!r}", got is not None and got["value"] == v and got["unit"] == unit
              and set(got["words"]) == words, got)
    check("'yesterday' is kept for the date", P.parse_log("I ran 5 km yesterday")["when"]
          == "yesterday")
    no = ["log out", "log in to my email", "I ran 5", "I have 3 kids", "remind me to run 5 km",
          "run 5 km", "how far is 5 km", "set a timer for 5 minutes", "I ran",
          "log the error", "what did I log", "I ran $5 km", "my name is Sam",
          "I think 5 km is far", "x" * 200]
    for text in no:
        check(f"not a log: {text!r}", P.parse_log(text) is None, P.parse_log(text))


def _benches():
    return [
        {"id": "a" * 32, "project": "p1", "name": "Long run", "unit": "km",
         "project_name": "Half marathon", "sensitive": False},
        {"id": "b" * 32, "project": "p2", "name": "Weight", "unit": "kg",
         "project_name": "Health", "sensitive": True},
        {"id": "c" * 32, "project": "p3", "name": "Push ups", "unit": "",
         "project_name": "Strength", "sensitive": False},
        {"id": "d" * 32, "project": "p4", "name": "Pages read", "unit": "pages",
         "project_name": "Reading", "sensitive": False},
        {"id": "e" * 32, "project": "p5", "name": "Daily steps", "unit": "steps",
         "project_name": "Walking", "sensitive": False},
    ]


def t_quick_matching():
    B = _benches()

    def which(text):
        got = P.match_log(P.parse_log(text), B)
        if got.get("match"):
            return got["match"]["name"]
        if got.get("ambiguous"):
            return "ambiguous"
        return None

    for text, want in (("I ran 5 km", "Long run"), ("log 5 km run", "Long run"),
                       ("log 5 km for my morning run", "Long run"),
                       ("log 5k run", "Long run"),
                       ("my weight is 72 kg", "Weight"), ("I weighed 72 kg", "Weight"),
                       ("log my weight as 72.5", "Weight"),
                       ("I did 20 push ups", "Push ups"), ("I read 30 pages", "Pages read"),
                       ("log 30 pages", "Pages read"),
                       ("I walked 10000 steps", "Daily steps")):
        check(f"{text!r} -> {want}", which(text) == want, which(text))
    for text in ("I ran 5 miles", "I weighed 160 lb", "I did 20 sit ups", "I ran 5 errands",
                 "my flight is 5 hours", "log 5 km swim", "I ran 30 minutes"):
        check(f"no benchmark fits: {text!r}", which(text) is None, which(text))
    two = B + [{"id": "f" * 32, "project": "p6", "name": "Run", "unit": "km",
                "project_name": "Fitness", "sensitive": False}]
    got = P.match_log(P.parse_log("I ran 5 km"), two)
    check("two benchmarks fit: ambiguous, never a guess", len(got.get("ambiguous", [])) == 2)
    check("no benchmarks at all: nothing", P.match_log(P.parse_log("I ran 5 km"), []) == {})


class _Sched:
    """jarvis_quick.answer() tells the scheduler a sentence was a command;
    nothing else here touches it."""
    def __init__(self):
        self.marked = []

    def mark_command(self, text):
        self.marked.append(text)

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass


def t_quick_command_end_to_end():
    old_one = P._ONE
    try:
        s = fresh()
        P._ONE = s
        now = time.time()
        check("with no projects.db, a log-shaped sentence is not ours",
              Q.match("I ran 5 km", now) is None and not s.exists())
        check("... and nothing was created by asking", not s.path.exists())
        life = s.create({"name": "Half marathon", "kind": "life"}, here=False)
        check("with a project but no benchmark, still not ours", Q.match("I ran 5 km", now)
              is None)
        run = s.add_benchmark(life["id"], {"name": "Long run", "unit": "km",
                                           "better": "higher"}, here=False)
        health = s.create({"name": "Health", "kind": "life"}, here=False)
        wt = s.add_benchmark(health["id"], {"name": "Weight", "unit": "kg",
                                            "better": "lower"}, here=False)
        it = Q.match("I ran 5 km", now)
        check("now it is ours: a project_log intent", it is not None and it.name == "project_log")
        sched = _Sched()
        res = Q.answer("I ran 5 km", sched=sched, now=now)
        check("answered without the model, and logged",
              res is not None and res.intent == "project_log"
              and "Logged 5 km for \"Long run\" in \"Half marathon\"." == res.reply
              and s.results(life["id"], run["id"])["results"] == 1, res and res.reply)
        check("the scheduler is told it was a command (so it is not learned as a fact)",
              sched.marked == ["I ran 5 km"])
        check("a run is not private: it may be read aloud",
              res.private is False and "gate" not in Q.route_fields(res))
        res = Q.answer("log 7 km run", sched=_Sched(), now=now + 60)
        check("the second one says better or worse", "Better than last time (up 2)." in res.reply,
              res.reply)
        res = Q.answer("my weight is 72.5 kg", sched=_Sched(), now=now)
        check("a weight is logged, and its answer is private (kept on screen)",
              res is not None and res.private is True
              and Q.route_fields(res).get("gate") == "private"
              and s.results(health["id"], wt["id"])["latest"]["value"] == 72.5)
        res = Q.answer("I ran 5 km yesterday", sched=_Sched(), now=now)
        pts = s.results(life["id"], run["id"])["points"]
        check("'yesterday' is logged a day back", res is not None
              and abs(pts[0]["at"] - (now - 86400)) < 5)
        check("\"I ran 5 miles\" goes to the model (no miles benchmark)",
              Q.match("I ran 5 miles", now) is None)
        check("\"is_command\" is true only when a benchmark fits",
              Q.is_command("I ran 5 km") and not Q.is_command("I swam 5 km"))
        other = s.create({"name": "Fitness", "kind": "life"}, here=False)
        s.add_benchmark(other["id"], {"name": "Run", "unit": "km"}, here=False)
        res = Q.answer("I ran 5 km", sched=_Sched(), now=now)
        check("two runs fit: Jarvis asks which, and logs nothing",
              res is not None and res.reply.startswith("Which one:")
              and s.results(life["id"], run["id"])["results"] == 3)
        # Only the owner's own words: a pasted message never reaches the grammar.
        body = {"messages": [{"role": "user", "content": "I ran 5 km", "source": "paste"}]}
        check("a pasted \"I ran 5 km\" is not the owner's own words: not logged",
              Q.newest_own_words(body) is None)
    finally:
        P._ONE = old_one


# --------------------------------------------------------------------------
#   A project's labelled facts (2026-10-15)
# --------------------------------------------------------------------------
#
# The owner's side decided the LABEL lives in projects.db, owned by
# jarvis_projects.py, and not as `meta.project` on jarvis_memory.py's own row
# (that module is the application target of three patches: memory-safety,
# embedding-guard, bitemporal). So the tests below are careful about the
# boundary, and each one says which side of it it is proving:
#
#   * jarvis_projects.py's half - the label table, the routes, the refusals -
#     is driven with a FAKE memory layer, so nothing here opens the owner's
#     real memory.db and no model is ever built;
#   * the bridge itself (that this file really calls the memory module's own
#     Forget, and really reads no fact's words) is proved against the REAL
#     jarvis_memory.py in its own test, and by reading this file's own source.

_FACT_WORDS = "a fact's own words, which jarvis_projects.py must never read"


class FakeMemory:
    """The little of jarvis_memory's API jarvis_projects.py is allowed to use:
    `get()` for one fact's STATE (is it there, is it still current) and
    `retire()` for its own Forget. It hands out no words and offers no
    `search`/`current_facts` at all, so a future edit that started reading
    fact text here would fail rather than pass quietly."""

    def __init__(self, rows=None):
        self.rows = {int(k): dict(v) for k, v in (rows or {}).items()}
        self.retired = []
        self.asked = []
        self.broke = None

    def get(self, fid):
        self.asked.append(int(fid))
        if self.broke is not None:
            raise self.broke
        return self.rows.get(int(fid))

    def retire(self, fid):
        if self.broke is not None:
            raise self.broke
        row = self.rows.get(int(fid))
        if row is None or row.get("valid_to") is not None or row.get("erased_at") is not None:
            # The real retire() reports "no row matched" as False: an
            # already-forgotten fact, an erased one, or an id that is not
            # there at all. Keeps the row - a Forget never deletes.
            return False
        self.retired.append(int(fid))
        row["valid_to"] = time.time()
        return True

    def search(self, *a, **k):        # pragma: no cover - it must never be called
        raise AssertionError("jarvis_projects.py must never search facts")

    def __getattr__(self, name):
        """Anything else jarvis_projects.py reaches for is a boundary it must
        not cross - a fact's words, a search, a list of every fact - so it
        fails HERE, loudly, instead of passing quietly."""
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise AssertionError(f"jarvis_projects.py must not use memory.{name}: it "
                             f"reads no fact's text (see the module's own note)")


def current_fact(fid: int, **kw) -> dict:
    """One current fact, the shape MemoryStore.get() returns (the text is a
    marker: if it ever turns up in an answer, a check below says so)."""
    row = {"id": int(fid), "text": _FACT_WORDS, "valid_to": None, "erased_at": None,
           "created": 1.0, "meta": "{}"}
    row.update(kw)
    return row


class fake_memory:
    """`with fake_memory(store):` - point jarvis_projects at a fake memory
    layer for the block, and put the real one back however the block ends."""

    def __init__(self, store):
        self.store = store
        self.was = None

    def __enter__(self):
        self.was = P._memory_store
        P._memory_store = lambda: self.store
        return self.store

    def __exit__(self, *exc):
        P._memory_store = self.was
        return False


def _fact_refusal(call):
    """(status, sentence) for a call that must be refused, or (None, "") when
    it was not refused at all."""
    try:
        call()
    except P.FactGone as exc:
        return exc.status, str(exc)
    return None, ""


def t_project_facts_are_labelled_listed_and_forgotten():
    ticks = [1000.0]

    def clock():
        ticks[0] += 1.0
        return ticks[0]

    s = fresh(clock=clock)
    pid = s.create({"name": "Half marathon", "kind": "life"}, here=False)["id"]
    check("a new project labels no facts", s.facts(pid) == [])
    mem = FakeMemory({7: current_fact(7), 8: current_fact(8)})
    with fake_memory(mem):
        before = s.get(pid)["changed"]
        out = s.label_fact(pid, 7)
        check("labelling ONE fact is one row, and the answer says so",
              out["ok"] is True and out["changed"] is True and out["fact"] == 7
              and out["facts"] == 1 and out["max"] == P.MAX_FACTS, out)
        check("... and the project itself is marked changed (the clock is the store's "
              "own, so this is the label that moved it)",
              s.get(pid)["changed"] > before, (before, s.get(pid)["changed"]))
        listed = s.facts(pid)
        check("it is listed by id, oldest label first, and carries NO words "
              "(the words come from /api/memory/used)",
              [f["fact"] for f in listed] == [7]
              and all(set(f) == {"fact", "created"} for f in listed), listed)
        check("the answer never carries the fact's text either",
              _FACT_WORDS not in json.dumps(out) and _FACT_WORDS not in json.dumps(listed))
        again = s.label_fact(pid, 7)
        check("labelling the same fact twice changes nothing (one row)",
              again["changed"] is False and again["facts"] == 1 and len(s.facts(pid)) == 1)
        s.label_fact(pid, 8)
        check("a second fact is listed beside the first",
              [f["fact"] for f in s.facts(pid)] == [7, 8], s.facts(pid))
        gone = s.forget_fact(pid, 7)
        check("Forget takes the label off AND calls the memory module's own Forget "
              "(retire(), the call /api/memory/forget makes)",
              gone["unlabelled"] is True and gone["forgot"] is True
              and mem.retired == [7], (gone, mem.retired))
        check("... and only that one is gone from the list",
              [f["fact"] for f in s.facts(pid)] == [8], s.facts(pid))
        check("... and the fact is MARKED, not deleted (Forget keeps the row, and "
              "no words were wiped - that is Erase, its own button)",
              mem.rows[7]["text"] == _FACT_WORDS
              and mem.rows[7]["valid_to"] is not None and 8 not in mem.retired)
        status, why = _fact_refusal(lambda: s.forget_fact(pid, 7))
        check("forgetting a fact this project does not label: 404, in words",
              status == 404 and "does not label" in why, (status, why))
        status, why = _fact_refusal(lambda: s.label_fact(pid, 99))
        check("labelling a fact id that is not there: 404, in words",
              status == 404 and "no remembered fact" in why, (status, why))
        check("... and nothing was stored for it", len(s.facts(pid)) == 1)
    # A string id is what the PATH carries (`.../facts/7/forget`); both
    # spellings are the same id, and neither is a guess.
    mem2 = FakeMemory({7: current_fact(7)})
    with fake_memory(mem2):
        pid2 = s.create({"name": "Garden", "kind": "life"}, here=False)["id"]
        check("a fact id may arrive as the digits a path carries",
              s.label_fact(pid2, "7")["fact"] == 7
              and s.forget_fact(pid2, "7")["forgot"] is True and mem2.retired == [7])
    for bad in (True, 0, -1, "abc", "-3", 1.5, None, "7x", 10 ** 19, ""):
        check(f"{bad!r} is not a fact id (400, in words), and nothing is stored",
              "fact id" in raises(lambda: s.label_fact(pid, bad), ValueError)
              and len(s.facts(pid)) == 1)


def t_project_facts_refuse_a_fact_that_can_no_longer_be_recalled():
    """A label that points at a fact the rest of Jarvis will never recall
    again is a list the owner cannot act on, so both spellings of "not
    current" are refused: forgotten (valid_to in the past) and erased
    (erased_at set). A lease that ends LATER is still current - the rule
    retire()'s own docstring forbids breaking."""
    s = fresh()
    pid = s.create({"name": "Run", "kind": "life"}, here=False)["id"]
    mem = FakeMemory({1: current_fact(1, valid_to=time.time() - 60),
                      2: current_fact(2, erased_at=time.time()),
                      3: current_fact(3, valid_to=time.time() + 86400)})
    with fake_memory(mem):
        status, why = _fact_refusal(lambda: s.label_fact(pid, 1))
        check("a forgotten fact cannot be labelled: 409, in words",
              status == 409 and "forgotten" in why, (status, why))
        status, why = _fact_refusal(lambda: s.label_fact(pid, 2))
        check("a fact whose words were erased cannot be labelled either: 409",
              status == 409 and "erased" in why, (status, why))
        check("a fact whose lease ends later IS current (nothing reads "
              "valid_to as 'not current')",
              s.label_fact(pid, 3)["changed"] is True and len(s.facts(pid)) == 1)
        check("... and neither refusal stored anything",
              [f["fact"] for f in s.facts(pid)] == [3], s.facts(pid))


def t_project_facts_keep_the_label_when_the_memory_layer_refuses():
    """The fact goes first and the label second, on purpose: a memory layer
    that breaks must leave the label in place, so the owner still sees the
    fact listed and can try again - never a list that has taken a fact off
    while the rest of Jarvis still recalls it."""
    s = fresh()
    pid = s.create({"name": "Run", "kind": "life"}, here=False)["id"]
    mem = FakeMemory({7: current_fact(7)})
    with fake_memory(mem):
        s.label_fact(pid, 7)
        mem.broke = RuntimeError("the memory layer fell over")
        try:
            s.forget_fact(pid, 7)
            check("a memory layer that raises is not a silent success", False,
                  "forget_fact returned instead of raising")
        except P.Unavailable as exc:
            check("a memory layer that raises: Unavailable (503) in words, and the "
                  "LABEL STAYS so the owner can try again",
                  "refused to forget" in str(exc)
                  and [f["fact"] for f in s.facts(pid)] == [7],
                  (str(exc), s.facts(pid)))
        mem.broke = None
        check("... and once it answers again the Forget goes through",
              s.forget_fact(pid, 7)["forgot"] is True and s.facts(pid) == [])
    # No memory layer at all is the same refusal, never a false success.
    s2 = fresh()
    pid2 = s2.create({"name": "Run", "kind": "life"}, here=False)["id"]
    with fake_memory(FakeMemory({7: current_fact(7)})):
        s2.label_fact(pid2, 7)
    with fake_memory(None):
        try:
            s2.forget_fact(pid2, 7)
            check("no memory layer at all: nothing is reported as forgotten", False,
                  "forget_fact returned instead of raising")
        except P.Unavailable as exc:
            check("no memory layer at all: the label stays and the answer says why",
                  "not importable" in str(exc)
                  and [f["fact"] for f in s2.facts(pid2)] == [7], str(exc))
    # A fact that was already forgotten elsewhere is a legitimate no-op: the
    # label comes off (the owner asked), and `forgot` is false because there
    # was nothing left for this call to do.
    mem2 = FakeMemory({9: current_fact(9)})
    s3 = fresh()
    pid3 = s3.create({"name": "Walk", "kind": "life"}, here=False)["id"]
    with fake_memory(mem2):
        s3.label_fact(pid3, 9)
        # Forgotten somewhere else - another screen, another day - while the
        # label is still there. The label is still the owner's to take off.
        mem2.rows[9]["valid_to"] = time.time() - 60
        out = s3.forget_fact(pid3, 9)
        check("a fact that was already forgotten elsewhere: the label comes off, "
              "`forgot` is false, and no second Forget is claimed",
              out["unlabelled"] is True and out["forgot"] is False
              and mem2.retired == [] and s3.facts(pid3) == [], (out, mem2.retired))


def _memory_used_max():
    """jarvis_memory.USED_MAX when that module can be imported here, else
    None - the cap on GET /api/memory/used?ids=, which MAX_FACTS must equal so
    one project's words are ONE call. Reading one constant opens no store and
    builds no model."""
    try:
        import jarvis_memory
        return int(jarvis_memory.USED_MAX)
    except Exception:
        return None


def t_project_facts_are_a_capped_list_of_ids():
    s = fresh()
    pid = s.create({"name": "Run", "kind": "life"}, here=False)["id"]
    old = P.MAX_FACTS
    P.MAX_FACTS = 2
    mem = FakeMemory({1: current_fact(1), 2: current_fact(2), 3: current_fact(3)})
    try:
        with fake_memory(mem):
            s.label_fact(pid, 1)
            s.label_fact(pid, 2)
            check("the cap is kept: a third fact is refused in words",
                  "at most 2" in raises(lambda: s.label_fact(pid, 3), OverflowError))
            check("... and it really was not stored", len(s.facts(pid)) == 2)
            check("the cap counts LABELS, so a fact already labelled is still fine",
                  s.label_fact(pid, 1)["changed"] is False)
    finally:
        P.MAX_FACTS = old
    check("MAX_FACTS is jarvis_memory's own USED_MAX, so a project's words are ONE "
          "call to /api/memory/used, never two",
          _memory_used_max() == P.MAX_FACTS, (P.MAX_FACTS, _memory_used_max()))


def t_project_facts_a_project_delete_takes_only_the_labels():
    """Deleting a project takes its labels with it - and NOTHING from
    memory.db: the facts are the owner's, and only the memory module's own
    Forget ever removes one."""
    s = fresh()
    pid = s.create({"name": "Run", "kind": "life"}, here=False)["id"]
    other = s.create({"name": "Garden", "kind": "life"}, here=False)["id"]
    mem = FakeMemory({1: current_fact(1), 2: current_fact(2)})
    with fake_memory(mem):
        s.label_fact(pid, 1)
        s.label_fact(other, 2)
        s.delete(pid)
        check("a label for a project that is gone reads as no such project",
              bool(raises(lambda: s.facts(pid), KeyError)))
        with s._lock, s._db() as c:
            left = c.execute("SELECT COUNT(*) FROM project_facts").fetchone()[0]
        check("... and its label row really went with it (the other project's is left)",
              left == 1, left)
        check("... and the OTHER project's label is untouched",
              [f["fact"] for f in s.facts(other)] == [2], s.facts(other))
        check("... and no fact was forgotten by deleting a project",
              mem.retired == [] and mem.rows[1]["valid_to"] is None, mem.retired)


def t_project_facts_in_a_column_that_an_older_projects_db_gains():
    """An existing projects.db - the owner's own, made by build steps 1 and 2 -
    gains `project_facts` the first time this module opens it (CREATE TABLE IF
    NOT EXISTS, in the same one-time schema pass every other table uses)."""
    import sqlite3
    path = _TMP / "older-projects-facts.db"
    c = sqlite3.connect(str(path))
    c.executescript(P._SCHEMA)
    c.execute("DROP TABLE project_facts")
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check("the test's old file really has no project_facts table",
          "project_facts" not in names, sorted(names))
    c.execute("INSERT INTO projects (id, name, kind, created, changed) VALUES "
              "('" + "b" * 32 + "', 'Before facts', 'life', 1, 1)")
    c.commit()
    c.close()
    s = P.Projects(path)
    s.get("b" * 32)
    c = sqlite3.connect(str(path))
    try:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        idx = [r[1] for r in c.execute("PRAGMA index_list(project_facts)").fetchall()]
        cols = [r[1] for r in c.execute("PRAGMA table_info(project_facts)").fetchall()]
    finally:
        c.close()
    check("... and gains the table, its columns and its index",
          "project_facts" in names and cols == ["project", "fact", "created"]
          and "project_facts_by_fact" in idx, (sorted(names), cols, idx))
    mem = FakeMemory({5: current_fact(5)})
    with fake_memory(mem):
        check("... and it takes a label at once",
              s.label_fact("b" * 32, 5)["fact"] == 5
              and [f["fact"] for f in s.facts("b" * 32)] == [5])


def t_project_facts_survive_a_database_whose_rows_are_in_the_wal_log():
    """THE SQLITE TRAP.

    The owner's own agents.db is 4,096 bytes beside a 115,392-byte `-wal` log
    and reads 0 tables without it. In WAL mode a just-written row lives in the
    SIDE FILE, not in `projects.db`, so anything that reads the main file
    alone - a copy of it, an `immutable=1` opener - sees nothing. backend/
    jarvis_backup.py documents the same care for the same reason.

    So this checks the label through SQLite's own reader (a FRESH Projects
    object on the same path, which has never seen the first), and then proves
    the row really was in the side file: a copy of `projects.db` ALONE (no
    -wal, no -shm) does not have it, and after an explicit checkpoint the same
    copy DOES. That second half is what makes the first half worth anything -
    the instrument is shown to detect presence as well as absence."""
    import sqlite3
    path = _TMP / "wal-projects.db"
    s = P.Projects(path)
    pid = s.create({"name": "WAL", "kind": "life"}, here=False)["id"]
    with s._lock, s._db() as c:
        c.execute("PRAGMA journal_mode=WAL")
    check("the database really is in WAL mode (or this check would prove nothing)",
          _journal_mode(path) == "wal", _journal_mode(path))
    # A WAL log is checkpointed away and DELETED when the LAST connection to
    # the file closes, so one connection is held open for the whole test -
    # which is also what the owner's own machine looks like (agents.db reads 0
    # tables beside its log because a process is still holding it).
    #
    # `sqlite3.connect` is LAZY: it opens no file until the connection is
    # first used, so a bare connect() here held nothing and the label was
    # checkpointed into the main file - the trap this test is about, sprung on
    # the test itself. One statement is what actually opens it.
    keeper = sqlite3.connect(str(path))
    keeper.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    mem = FakeMemory({7: current_fact(7)})

    def main_file_only() -> tuple:
        """(tables, project_facts rows) read from a copy of the MAIN FILE
        alone - no -wal, no -shm."""
        copy = _TMP / f"wal-main-only-{len(_WAL_READS)}.db"
        _WAL_READS.append(copy)
        shutil.copyfile(path, copy)
        c = sqlite3.connect(str(copy))
        try:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master "
                                            "WHERE type='table'")}
            rows = (c.execute("SELECT COUNT(*) FROM project_facts").fetchone()[0]
                    if "project_facts" in names else 0)
            return sorted(names), int(rows)
        finally:
            c.close()

    try:
        with fake_memory(mem):
            s.label_fact(pid, 7)
        wal = Path(str(path) + "-wal")
        check("the label went into the -wal side file, as a WAL database does",
              wal.is_file() and wal.stat().st_size > 0, wal)
        names, rows = main_file_only()
        check("... so a read of projects.db ALONE really does not have it "
              "(the trap is live, not theoretical)",
              rows == 0, (names, rows))
        s2 = P.Projects(path)                 # never saw the first object
        check("... and a FRESH Projects on the same file reads the label back, because "
              "SQLite reads the -wal itself - two SQLite readers, one file",
              [f["fact"] for f in s2.facts(pid)] == [7], s2.facts(pid))
    finally:
        keeper.close()
    with s2._lock, s2._db() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    names, rows = main_file_only()
    check("... and after a checkpoint the same main file DOES have it, so the "
          "check above is a real instrument and not a check that cannot fail",
          rows == 1 and "project_facts" in names, (names, rows))


_WAL_READS = []


def _journal_mode(path) -> str:
    import sqlite3
    c = sqlite3.connect(str(path))
    try:
        return str(c.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    finally:
        c.close()


def t_project_facts_routes():
    pr = P.parse_route
    pid, bid = "1" * 32, "2" * 32
    check("the fact routes are in the table, and only these shapes",
          pr(f"/api/projects/{pid}/facts") == ("facts", pid)
          and pr(f"/api/projects/{pid}/facts/7/forget") == ("fact_forget", pid, "7")
          and pr(f"/api/projects/{pid}/facts/7") is None
          and pr(f"/api/projects/{pid}/facts/7/delete") is None
          and pr(f"/api/projects/{pid}/facts//forget") is None
          and pr(f"/api/projects/{pid}/facts/7/forget/more") is None
          and pr(f"/api/projects/{pid}/benchmarks/{bid}") == ("bench", pid, bid))
    s = fresh()
    pid = s.create({"name": "Run", "kind": "life"}, here=False)["id"]
    mem = FakeMemory({7: current_fact(7), 8: current_fact(8)})
    with fake_memory(mem):
        code, out = P.handle_get(f"/api/projects/{pid}/facts", store=s)
        check("GET .../facts on a project with no labels: 200, the empty sentence",
              code == 200 and out["facts"] == [] and out["count"] == 0
              and out["empty"] == P.EMPTY_FACTS and out["ids"] == []
              and out["max"] == P.MAX_FACTS, out)
        code, out = P.handle_post(f"/api/projects/{pid}/facts", {"id": 7}, store=s)
        check("POST .../facts labels one fact, no card", code == 200 and out["ok"]
              and out["changed"] is True and out["fact"] == 7, out)
        code, out = P.handle_post(f"/api/projects/{pid}/facts", {"id": 8}, store=s)
        code, out = P.handle_get(f"/api/projects/{pid}/facts", store=s)
        check("GET .../facts lists both ids oldest first, and NAMES where the words "
              "come from (jarvis_memory's own route, one call for the whole list)",
              [f["fact"] for f in out["facts"]] == [7, 8] and out["ids"] == [7, 8]
              and out["words_route"] == "/api/memory/used"
              and out["empty"] == "", out)
        check("... and the answer carries no fact's words",
              _FACT_WORDS not in json.dumps(out))
        code, out = P.handle_post(f"/api/projects/{pid}/facts/7/forget", {}, store=s)
        check("POST .../facts/<id>/forget takes the label off and forgets the fact",
              code == 200 and out["unlabelled"] is True and out["forgot"] is True
              and mem.retired == [7], (code, out))
        code, out = P.handle_post(f"/api/projects/{pid}/facts/7/forget", {}, store=s)
        check("forgetting it twice: 404 with its own sentence (nothing left to take off)",
              code == 404 and "does not label" in out["error"], (code, out))
        code, out = P.handle_post(f"/api/projects/{pid}/facts", {"id": 99}, store=s)
        check("labelling a fact that is not there is a 404 in words",
              code == 404 and "no remembered fact" in out["error"], (code, out))
        code, out = P.handle_post(f"/api/projects/{pid}/facts", {}, store=s)
        check("a missing id is a 400 in words, not a 404 or a crash",
              code == 400 and "fact id" in out["error"], (code, out))
        code, out = P.handle_post(f"/api/projects/{pid}/facts", {"id": "7x"}, store=s)
        check("an id that is not a whole number is a 400 in words",
              code == 400 and "fact id" in out["error"], (code, out))
        code, out = P.handle_get(f"/api/projects/{pid}/facts/7/forget", store=s)
        check("GET on the forget route is a 405 (it is a POST)", code == 405, code)
        code, out = P.handle_post(f"/api/projects/{'9' * 32}/facts", {"id": 7}, store=s)
        check("a route under a project that is not there is a 404 - the PROJECT is "
              "checked first, so this is a 404 even though fact 7 is no longer "
              "current", code == 404, code)
        code, out = P.handle_post(f"/api/projects/{pid}/facts", ["not", "a", "dict"],
                                  store=s)
        check("a body that is not an object is a 400", code == 400)
    # No card, and no PC-only: the owner's own tap on a fact they can see, and
    # `here` is never consulted.
    mem2 = FakeMemory({7: current_fact(7)})
    with fake_memory(mem2):
        pid2 = s.create({"name": "Garden", "kind": "life"}, here=False)["id"]
        check("labelling asks for no card and is not PC-only (it works from "
              "anywhere, as /api/memory/forget and /api/memory/shared do)",
              P.handle_post(f"/api/projects/{pid2}/facts", {"id": 7},
                            here=False, store=s)[0] == 200
              and mem2.retired == [])


def t_project_facts_call_the_memory_modules_own_forget_and_read_no_words():
    """The BRIDGE, proved against the real jarvis_memory.py and against this
    file's own source.

    Two things must stay true, and both are checkable:
      1. the Forget this file causes is the memory module's OWN Forget -
         `MemoryStore.retire()`, the call `POST /api/memory/forget` makes -
         and never `erase()` (the separate "Erase the words" button) and
         never a DELETE;
      2. this file reads no fact's WORDS: no SQL against the facts table, and
         no `store().search(` anywhere - which is what lets
         test_topics_leaks.py's own list keep saying "reads no fact"."""
    src = (HERE / "jarvis_projects.py").read_text(encoding="utf-8")
    # test_topics_leaks.py's own instrument, not a second definition of
    # "reads facts" written here: `touches` is why this file is on that list,
    # `sql` would mean it queried the facts table itself, and `searches` would
    # mean it ranked facts. Only the first is allowed.
    #
    # Loaded from THIS file's own folder by path, never by `import
    # test_topics_leaks`: a run against a real install has BACKEND first on
    # sys.path, and a stale copy of that module there would answer for the
    # wrong tree - the mistake CLAUDE.md records twice over.
    tl_path = HERE / "test_topics_leaks.py"
    if not tl_path.is_file():
        skip(f"test_topics_leaks.py is not beside this suite ({HERE}), so its own "
             f"analysis of what reads facts cannot be used here")
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_s2_topics_leaks", tl_path)
        TL = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(TL)
        a = TL.analyse(src)
        check("jarvis_projects.py reads no words: no SQL of its own against the facts "
              "table (test_topics_leaks.py's own analysis)", a["sql"] is False, a)
        check("... and no store.search() on a memory store anywhere in it",
              a["searches"] == [], a["searches"])
        check("... and it does name jarvis_memory, which is why it is on that list",
              a["touches"] is True, a)
    check("... and it causes no delete and wipes no words: no erase() call",
          ".erase(" not in src and "DELETE FROM facts" not in src.upper())
    check("... and its one act on a fact is the memory module's own Forget",
          ".retire(" in src and "MemoryStore" in src)
    check("... and it names the route the memory module already owns for "
          "showing one fact's words", "/api/memory/used" in src)
    # Against the REAL module, when it is importable here (its own USED_MAX is
    # read by a check above): the method this file calls must exist with the
    # same name, and the real Forget route must be the same call.
    try:
        import jarvis_memory as M
    except Exception as exc:                                  # pragma: no cover
        skip(f"jarvis_memory.py is not importable here, so the bridge cannot be "
             f"checked against it ({type(exc).__name__})")
        return
    check("the real MemoryStore has the retire() this file calls, and no "
          "`forget()` that this file should have used instead",
          hasattr(M.MemoryStore, "retire") and not hasattr(M.MemoryStore, "forget"))
    check("the real MemoryStore.retire takes one fact id and returns whether a row "
          "matched (the shape this file's answer is built on)",
          list(M.MemoryStore.retire.__code__.co_varnames)[1:4] == ["fact_id",
                                                                   "replaced_by",
                                                                   "valid_to"])
    check("... and the real module's own cap on showing a list of facts is the one "
          "MAX_FACTS equals", int(M.USED_MAX) == P.MAX_FACTS, M.USED_MAX)
    # End to end, on a throwaway memory.db and the cheapest embedder there is:
    # a real fact, really labelled, really forgotten - and its words really
    # still there afterwards.
    try:
        st = M.MemoryStore(_TMP / "facts-bridge-memory.db", embedder=M.HashEmbedder())
    except Exception as exc:                                  # pragma: no cover
        skip(f"a MemoryStore cannot be built here, so the bridge cannot be driven "
             f"({type(exc).__name__})")
        return
    added = st.add(_FACT_WORDS, source="test")
    fid = int(added["id"] if isinstance(added, dict) else added)
    s = fresh()
    pid = s.create({"name": "Bridge", "kind": "life"}, here=False)["id"]
    with fake_memory(st):
        check("a REAL fact is labelled through the project",
              s.label_fact(pid, fid)["changed"] is True
              and [f["fact"] for f in s.facts(pid)] == [fid])
        out = s.forget_fact(pid, fid)
        check("... and forgotten through the project: the memory module's own "
              "retire() ran (the fact is no longer current)",
              out["forgot"] is True and st.get(fid)["valid_to"] is not None, out)
        check("... and its WORDS are still there (Forget is not Erase)",
              st.get(fid)["text"] == _FACT_WORDS and st.get(fid)["erased_at"] is None)
        check("... and the label is gone", s.facts(pid) == [])
        check("... and a fact that is no longer current cannot be re-labelled "
              "(409)", _fact_refusal(lambda: s.label_fact(pid, fid))[0] == 409)


# --------------------------------------------------------------------------
#   Routes, install, the patch, and what is never written down
# --------------------------------------------------------------------------


def t_routes():
    pr = P.parse_route
    pid, bid, rid = "1" * 32, "2" * 32, "3" * 32
    check("the route table", pr("/api/projects") == ("list",)
          and pr(f"/api/projects/{pid}") == ("project", pid)
          and pr(f"/api/projects/{pid}/delete") == ("project_delete", pid)
          and pr(f"/api/projects/{pid}/shareable") == ("shareable", pid)
          and pr(f"/api/projects/{pid}/benchmarks") == ("benchmarks", pid)
          and pr(f"/api/projects/{pid}/benchmarks/{bid}") == ("bench", pid, bid)
          and pr(f"/api/projects/{pid}/benchmarks/{bid}/log") == ("log", pid, bid)
          and pr(f"/api/projects/{pid}/benchmarks/{bid}/unmark") == ("unmark", pid, bid)
          and pr(f"/api/projects/{pid}/benchmarks/{bid}/delete") == ("bench_delete", pid, bid)
          and pr(f"/api/projects/{pid}/benchmarks/{bid}/results/{rid}/delete")
          == ("result_delete", pid, bid, rid)
          and pr(f"/api/projects/{pid}/facts") == ("facts", pid)
          and pr(f"/api/projects/{pid}/facts/7/forget") == ("fact_forget", pid, "7")
          and pr(f"/api/projects/{pid}/facts/7") is None)
    check("anything else is not ours", pr("/api/projectsX") is None
          and pr("/api/projects/") is None and pr(f"/api/projects/{pid}/run") is None
          and pr("/api/goals") is None)
    s = fresh()
    code, out = P.handle_get("/api/projects", store=s)
    check("GET /api/projects on an empty store", code == 200 and out["projects"] == []
          and out["empty"] == P.EMPTY)
    code, out = P.handle_post("/api/projects", {"name": "Run", "kind": "life"}, store=s)
    pid = out["project"]["id"]
    check("POST /api/projects creates", code == 200 and out["ok"])
    code, out = P.handle_post(f"/api/projects/{pid}/benchmarks",
                              {"name": "Distance", "unit": "km"}, store=s)
    bid = out["benchmark"]["id"]
    code, out = P.handle_post(f"/api/projects/{pid}/benchmarks/{bid}/log", {"value": 5},
                              store=s)
    check("POST .../log logs, no card", code == 200 and out["benchmark"]["latest"]["value"] == 5)
    code, out = P.handle_get(f"/api/projects/{pid}/benchmarks/{bid}", "points=10", store=s)
    check("GET a benchmark gives the chart points", code == 200
          and len(out["benchmark"]["points"]) == 1)
    code, out = P.handle_post(f"/api/projects/{pid}", {"instructions": "x" * 1501}, store=s)
    check("a cap is a 400 in words", code == 400 and "1500" in out["error"])
    code, out = P.handle_get(f"/api/projects/{'9' * 32}", store=s)
    check("an unknown project is a 404", code == 404)
    code, out = P.handle_post(f"/api/projects/{pid}", ["not", "a", "dict"], store=s)
    check("a body that is not an object is a 400", code == 400)
    code, out = P.handle_get(f"/api/projects/{pid}/delete", store=s)
    check("GET on a POST route is a 405", code == 405)
    code, out = P.handle_post(f"/api/projects/{pid}/delete", {}, store=s)
    check("POST .../delete deletes", code == 200 and s.list() == [])


def t_install_wraps_the_routes():
    hits = []

    class H:
        path = "/"
        client_address = ("127.0.0.1", 5)

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            hits.append((code, out))

    old_one = P._ONE
    try:
        P._ONE = fresh()
        line = P.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                         read_body=lambda self: json.dumps(
                             {"name": "Garden", "kind": "life"}).encode())
        check("install returns a banner line", "Projects" in line)
        check("installing twice does not wrap twice", "already on" in P.install(
            H, origin_ok=lambda self: True, token_ok=lambda self: True, read_body=None))
        h = H()
        h.path = "/api/projects"
        h.do_POST()
        check("POST /api/projects is answered here",
              isinstance(hits[-1], tuple) and hits[-1][0] == 200)
        h.path = "/api/projects?x=1"
        h.do_GET()
        check("GET /api/projects (with a query) is answered here",
              hits[-1][0] == 200 and len(hits[-1][1]["projects"]) == 1)
        h.path = "/api/other"
        h.do_GET()
        h.do_POST()
        check("anything else passes through", hits[-2:] == ["get0", "post0"])

        class H2(H):
            pass
        H2.do_GET = lambda self: hits.append("g")
        H2.do_POST = lambda self: hits.append("p")
        P.install(H2, origin_ok=lambda self: True, token_ok=lambda self: False,
                  read_body=lambda self: b"{}")
        h2 = H2()
        h2.path = "/api/projects"
        h2.do_GET()
        check("without the token: 401, nothing read", hits[-1][0] == 401)
    finally:
        P._ONE = old_one


def t_the_patch():
    if not shutil.which("git"):
        return skip("git is not installed")
    import _stack
    order = _stack.order()
    def touches_hud(name):
        try:
            text = (Path(__file__).resolve().parent / name).read_text(encoding="utf-8")
        except OSError:
            return True
        return "+++ b/jarvis_hud.py" in text
    hud_order = [n for n in order if touches_hud(n)]
    # After answer-sources.patch, whose install block it anchors on.
    # chatbot-routes.patch anchors on THIS patch's block, so it follows it.
    check("projects.patch is in apply-patches.ps1's list, after answer-sources.patch",
          "projects.patch" in order and "answer-sources.patch" in order
          and order.index("projects.patch") > order.index("answer-sources.patch"), hud_order[-3:])
    if "projects.patch" not in order:
        return
    text, log = _stack.stand_in("jarvis_hud.py", order[:order.index("projects.patch")])
    check("a stand-in jarvis_hud.py could be built", text is not None, log)
    if text is None:
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-projects-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_bytes((HERE / "projects.patch").read_bytes()
                                    .replace(b"\r\n", b"\n"))
        r = subprocess.run(["git", "apply", "--include", "jarvis_hud.py", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        check("projects.patch applies to what the earlier patches wrote", r.returncode == 0,
              r.stderr)
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run(["git", "apply", "-R", "--include", "jarvis_hud.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        check("... and reverses to the same text", r.returncode == 0
              and (d / "jarvis_hud.py").read_text(encoding="utf-8") == text, r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    i = after.index("# projects.patch")
    j = after.index("# Before the main socket", i)
    blk = after[i:j]
    check("the block passes origin_ok/token_ok/read_body into jarvis_projects.install",
          "import jarvis_projects" in blk and "origin_ok=_origin_ok" in blk
          and "token_ok=_token_ok" in blk and "read_body=_read_body" in blk)
    try:
        compile("def f(self, bind, Handler):\n" + blk, "<patched block>", "exec")
        check("the patched block compiles", True)
    except SyntaxError as exc:
        check("the patched block compiles", False, str(exc))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_projects.py is shipped by apply-patches.ps1", "'jarvis_projects.py'" in ps1)


def t_a_benchmark_read_carries_the_finish_time_range():
    """JARVIS-API section 101: GET .../benchmarks/<id>?points=N gains
    `forecast` (jarvis_forecast.py; its own edge cases are test_forecast.py)."""
    DAY = 86400.0
    NOW = 1_790_000_000.0
    s = fresh(clock=lambda: NOW)
    pid = s.create({"name": "Race", "kind": "life"}, here=False)["id"]
    five = s.add_benchmark(pid, {"name": "5k time", "unit": "min", "better": "lower",
                                 "target": 25}, here=True)["id"]
    plain = s.add_benchmark(pid, {"name": "Score", "unit": "pts"}, here=True)["id"]
    weight = s.add_benchmark(pid, {"name": "Weight", "unit": "kg", "better": "lower",
                                   "target": 70}, here=True)["id"]
    with s._lock, s._db() as c:
        check("...the plain benchmark view (no points asked) carries none",
              "forecast" not in s._bench_view(c, s._bench_row(c, pid, five)))
    r = s.results(pid, five, 365)
    check("no numbers yet: 'not enough', 5 more needed",
          r["forecast"]["state"] == "not_enough" and r["forecast"]["needed"] == 5
          and r["forecast"]["words"] == "Not enough numbers yet - 5 more needed.", r["forecast"])
    # 31, 30, 29, 28, 27 min a week apart, the last an hour ago: 2 min to go = 2 weeks.
    for i, v in enumerate((31, 30, 29, 28, 27)):
        s.log(pid, five, v, at=NOW - 3600 - (4 - i) * 7 * DAY)
    f = s.results(pid, five, 365)["forecast"]
    check("five weekly numbers falling 1 a week to 27, target 25: 'About 2 weeks'",
          f["state"] == "range" and (f["low_weeks"], f["high_weeks"]) == (2, 2)
          and f["words"] == "About 2 weeks at this pace." and f["used"] == 5, f)
    check("the forecast does not depend on how many chart points were asked for",
          s.results(pid, five, 2)["forecast"] == f and s.results(pid, five, 1)["forecast"] == f)
    s.log(pid, five, 24.5, at=NOW - 60)
    check("a number at the target: 'reached', nothing drawn",
          s.results(pid, five, 365)["forecast"]["state"] == "reached"
          and s.results(pid, five, 365)["forecast"]["line"] is None)
    check("no target: 'Set a target to see a pace.'",
          s.results(pid, plain, 365)["forecast"]["state"] == "no_target")
    for i, v in enumerate((80, 79, 78, 77, 76)):
        s.log(pid, weight, v, at=NOW - 3600 - (4 - i) * 7 * DAY)
    w = s.results(pid, weight, 365)
    check("a health number gets the range too, and the benchmark stays keep_on_screen",
          w["forecast"]["state"] == "range" and w["keep_on_screen"] is True
          and w["sensitive"] is True, w["forecast"]["state"])
    check("the answer is plain data (no NaN, no infinity)",
          "NaN" not in json.dumps(w) and "Infinity" not in json.dumps(w))
    code, body = P.handle_get(f"/api/projects/{pid}/benchmarks/{weight}", "points=365", store=s)
    check("GET .../benchmarks/<id> sends `forecast` with state, words and the week numbers",
          code == 200 and {"state", "words", "low_weeks", "high_weeks"} <= set(body["benchmark"]["forecast"]),
          body["benchmark"].get("forecast"))
    # a forecast that blows up must not break the benchmark read
    real = P.Projects._forecast

    def boom(self, c, b):
        raise RuntimeError("the forecast broke")
    P.Projects._forecast = boom
    try:
        broken = s.results(pid, five, 365)
    except Exception as exc:
        broken = None
        check("a forecast that raises does not break the benchmark read", False, repr(exc))
    finally:
        P.Projects._forecast = real
    if broken is not None:
        check("a forecast that raises does not break the benchmark read: the read is whole, "
              "with no forecast", "forecast" not in broken and broken.get("points")
              and broken.get("name") == "5k time", sorted(broken))
    src = (HERE / "jarvis_forecast.py").read_text(encoding="utf-8")
    check("jarvis_forecast.py is shipped beside it (apply-patches.ps1 and _where.SHIPPED)",
          "'jarvis_forecast.py'" in (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
          and "jarvis_forecast.py" in __import__("_where").SHIPPED and "import numpy" not in src)


def t_both_apps_read_the_current_contract():
    if shutil.which("git") is None:
        print("SKIP  git is not installed here - the contract file's app answers come from "
              "a real run of it")
        return
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_projects_cases.py"), "--check"],
                       capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check("projects-cases.json (desktop and phone) is what the backend says today "
          "(python3 tools/gen_projects_cases.py)", r.returncode == 0, r.stdout + r.stderr)


def t_audit_never_carries_words_or_numbers():
    words = ("Half marathon", "Keep me honest", "Race is 12 April", "Long run", "Weight",
             "72.5", "21.1", "pytest")
    leaked = [(e, d) for e, d in _AUDIT
              if any(w in json.dumps(d, default=str) for w in words)]
    check("the audit log has lines, and none carries a name, a note or a number",
          len(_AUDIT) > 10 and not leaked, leaked[:3])


def t_no_network_no_model():
    check("nothing in this suite tried to open a network connection", _NET == [], _NET[:3])
    src = (HERE / "jarvis_projects.py").read_text(encoding="utf-8")
    check("jarvis_projects.py imports no network library and runs nothing",
          not any(w in src for w in ("import urllib.request", "import http", "import requests",
                                     "import subprocess", "os.system", "Popen(",
                                     "ask_model", "ollama")))


def t_a_project_call_does_not_leave_its_database_file_open():
    """Every connection the Projects store opens is CLOSED when its block ends.

    WHY (2026-10-07, the intermittent backend-windows CI failure; still failing
    a different suite on 2026-10-08). sqlite3's context manager commits on the
    way out and never closes the connection, so a bare
    `with self._lock, self._db() as c:` left an OPEN HANDLE on projects.db
    behind until CPython happened to collect it - immediate on a quiet line,
    and NOT immediate when a caught exception's traceback, a generator frame
    or a temp-folder object still held a reference. On Windows an open handle
    makes the file undeletable, the exact failure the runner logged for
    schedule.json (jarvis_schedule.py's own _ClosingConnection), and
    projects.db is opened by that same shape - 24 times in this module.

    This is the deterministic half of that, and it holds on every platform:
    every connection is KEPT (so no refcount can be what closes it) and then
    asked to do something. On the old code each one answers and the check is
    red; with _ClosingConnection they are all closed and it is green."""
    import sqlite3
    made = []
    real = P.sqlite3.connect

    def spy(*a, **kw):
        c = real(*a, **kw)
        made.append(c)          # held on purpose: the collector must not close it
        return c

    P.sqlite3.connect = spy
    try:
        s = fresh()
        p = s.create({"name": "Half marathon", "kind": "life"}, here=False)
        s.list()
        s.get(p["id"])
        s.update(p["id"], {"notes": ["Race is 12 April"]}, here=False)
        b = s.add_benchmark(p["id"], {"name": "Weight", "unit": "kg"}, here=False)
        s.log(p["id"], b["id"], 72.5)
        s.results(p["id"], b["id"])
        with fake_memory(FakeMemory({7: current_fact(7)})):
            q = s.create({"name": "Garden", "kind": "life"}, here=False)
            s.label_fact(q["id"], 7)
            s.facts(q["id"])
            s.forget_fact(q["id"], 7)
        s.delete(p["id"])
    finally:
        P.sqlite3.connect = real

    def still_readable(c):
        try:
            c.execute("SELECT 1")
            return True
        except sqlite3.ProgrammingError:
            return False

    open_ones = [c for c in made if still_readable(c)]
    check("every connection the Projects store opens is closed when its `with` block "
          "ends (a leaked handle is what made projects.db undeletable on the "
          "Windows runner, 2026-10-07)",
          bool(made) and not open_ones, f"{len(open_ones)} of {len(made)} still open")
    # The factory must not change what a caller does with the connection:
    # test_progress.py reads one OUTSIDE a `with`, and that must still answer.
    # Checked on its own live store, before the folder below is removed.
    s3 = P.Projects(_TMP / "projects-outside-with.db", clock=time.time)
    s3.create({"name": "Tea shop", "kind": "life"}, here=False)
    held = s3._db()
    try:
        check("a connection read outside a `with` block still answers (the shape "
              "test_progress.py and test_tellme.py use, kept working)",
              held.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1)
    finally:
        held.close()
    # And the thing the runner actually saw: a folder holding the store's own
    # file, removed the way a suite's temporary folder is. On POSIX an open
    # handle does not refuse the unlink, so this half is Windows-only
    # evidence - the check above is the half that holds everywhere.
    d = Path(tempfile.mkdtemp(prefix="jarvis-projects-del-"))
    s2 = P.Projects(d / "projects.db", clock=time.time)
    s2.create({"name": "Tea shop", "kind": "life"}, here=False)
    try:
        shutil.rmtree(str(d))
        removed, why = True, ""
    except OSError as exc:
        removed, why = False, f"{type(exc).__name__}: {exc}"
    check("... so the folder holding it can be removed at once, the way a suite's "
          "temporary folder is removed (on Windows an open handle refuses this)",
          removed, why)


# --------------------------------------------------------------------------
#   Project Mode (design step 4): the active project, the Auto-Route card, the
#   context a turn is given, the routing gate, and the writer that was missing
# --------------------------------------------------------------------------

def _no_mode_file():
    """Every one of these starts with no project active."""
    try:
        P.mode_path().unlink()
    except FileNotFoundError:
        pass


class _Card:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


def _gate_says(cards, verdict):
    def g(action, detail, prompt):
        cards.append((action, detail, prompt))
        return verdict
    return g


def t_the_active_project_is_never_a_guess():
    s = fresh()
    p = s.create({"name": "Tea shop", "kind": "life"}, here=False)
    _no_mode_file()
    check("no project is active to begin with", P.active_project_id() is None)
    check("entering Project Mode answers the id",
          P.set_active_project(p["id"], store=s) == p["id"])
    check("... the file says so", P.active_project_id() == p["id"])
    check("... and the project's own view says it is the active one",
          s.get(p["id"])["active"] is True)
    check("leaving is instant", P.set_active_project(None, store=s) is None
          and P.active_project_id() is None)
    check("an id that is not an id is refused, not written",
          raises(lambda: P.set_active_project("../../etc/passwd", store=s)) != ""
          and P.active_project_id() is None)
    check("a project that does not exist is refused",
          raises(lambda: P.set_active_project("0" * 32, store=s)) != ""
          and P.active_project_id() is None)
    P.mode_path().write_text("{ this is not json at all", encoding="utf-8")
    check("a state file that will not parse answers None, never raises",
          P.active_project_id() is None)
    P.mode_path().write_text('{"active_project_id": "not-an-id"}', encoding="utf-8")
    check("an id-shaped check is applied to what is read back",
          P.active_project_id() is None)
    _no_mode_file()


def t_auto_route_off_is_instant_and_on_is_one_card():
    s = fresh()
    p = s.create({"name": "App", "kind": "coding"}, here=True)
    check("Auto-Route starts off", s.get(p["id"])["auto_route_cloud"] is False)
    check("an ordinary edit cannot turn it on",
          "asks you first" in raises(lambda: s.update(
              p["id"], {"auto_route_cloud": True}, here=True)))
    cards = []
    def _no_card(*a):
        raise AssertionError("OFF raised a card")
    code, _ = P.request_auto_route(p["id"], {"on": False}, store=s,
                                   gate=_no_card, tier_of=lambda a: "ask",
                                   spawn=lambda fn: fn())
    check("OFF is instant and raises NO card", code == 200 and cards == [], code)
    check("... and it is off", s.get(p["id"])["auto_route_cloud"] is False)
    code, out = P.request_auto_route(p["id"], {"on": True}, store=s,
                                     gate=_gate_says(cards, _Card(True, "approved")),
                                     tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("ON while the project is NOT Shareable is refused, and no card is raised",
          code == 409 and cards == [] and "Shareable first" in out["error"], out)
    s.set_shareable_on(p["id"])
    code, _ = P.request_auto_route(p["id"], {"on": True}, store=s,
                                   gate=_gate_says(cards, _Card(False, "denied")),
                                   tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("ON raises exactly ONE change_own_config card",
          code == 202 and len(cards) == 1 and cards[0][0] == "change_own_config",
          (code, cards))
    check("the card names the question, and says every send is carded too",
          "cloud lane" in cards[0][2] and "never automatic" in cards[0][2]
          and "health or money" in cards[0][2] and "nothing changes" in cards[0][2],
          cards[0][2])
    check("a NO leaves it off, and says so",
          s.get(p["id"])["auto_route_cloud"] is False
          and s.get(p["id"])["auto_route_last"]["outcome"] == "denied")
    P.request_auto_route(p["id"], {"on": True}, store=s,
                         gate=_gate_says(cards, _Card(False, "timed_out")),
                         tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("a timed-out card leaves it off", s.get(p["id"])["auto_route_cloud"] is False)
    P.request_auto_route(p["id"], {"on": True}, store=s,
                         gate=_gate_says(cards, _Card(True, "approved", tier="auto")),
                         tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("CONTROL: a yes at the WRONG tier is not a person saying yes - rule 4",
          s.get(p["id"])["auto_route_cloud"] is False
          and s.get(p["id"])["auto_route_last"]["outcome"] == "refused")
    P.request_auto_route(p["id"], {"on": True}, store=s,
                         gate=_gate_says(cards, _Card(True, "approved")),
                         tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("a real yes turns it on", s.get(p["id"])["auto_route_cloud"] is True)
    check("a second ON says it is already on, and raises no card",
          P.request_auto_route(p["id"], {"on": True}, store=s, gate=_no_card,
                               tier_of=lambda a: "ask",
                               spawn=lambda fn: fn())[0] == 200)
    check("the gate's own tier must be 'ask', or it refuses rather than carding",
          P.request_auto_route(p["id"], {"on": False}, store=s, gate=_no_card,
                               tier_of=lambda a: "ask",
                               spawn=lambda fn: fn())[0] == 200
          and P.request_auto_route(p["id"], {"on": True}, store=s, gate=_no_card,
                                   tier_of=lambda a: "auto",
                                   spawn=lambda fn: fn())[0] == 503)
    P.request_auto_route(p["id"], {"on": False}, store=s, gate=_no_card,
                         tier_of=lambda a: "ask", spawn=lambda fn: fn())
    check("... and OFF after all that is instant again",
          s.get(p["id"])["auto_route_cloud"] is False)
    check("a body that is not true/false is refused",
          P.request_auto_route(p["id"], {"on": "yes"}, store=s, gate=_no_card,
                               tier_of=lambda a: "ask", spawn=lambda fn: fn())[0] == 400)


def t_the_routing_gate_needs_all_three_and_absence_means_local():
    s = fresh()
    p = s.create({"name": "App", "kind": "coding"}, here=True)
    _no_mode_file()
    check("no active project: local, and it says so",
          P.route_for_turn("hello", store=s)["lane"] == "local"
          and "No project" in P.route_for_turn("hello", store=s)["why"])
    P.set_active_project(p["id"], store=s)
    check("active but NOT Shareable: local",
          P.route_for_turn("hello", store=s)["lane"] == "local")
    check("... and it names Shareable as the reason",
          "not Shareable" in P.route_for_turn("hello", store=s)["why"])
    s.set_shareable_on(p["id"])
    got = P.route_for_turn("hello", store=s)
    check("Shareable but Auto-Route OFF: local", got["lane"] == "local", got)
    check("... and the pill is still Local-Only", got["routing"] == "Local-Only", got)
    s.set_auto_route_cloud_on(p["id"])

    real = sys.modules.get("jarvis_auto_router", "<missing>")
    sys.modules["jarvis_auto_router"] = None      # `import` now raises
    try:
        got = P.route_for_turn("hello", store=s)
    finally:
        if real == "<missing>":
            del sys.modules["jarvis_auto_router"]
        else:
            sys.modules["jarvis_auto_router"] = real
    check("ALL THREE on but the router is not installed: LOCAL, not a crash",
          got["lane"] == "local" and got["recommended"] is False, got)
    check("... and it says the router is not available",
          "not available" in got["why"], got.get("why"))

    mod = types.ModuleType("jarvis_auto_router")
    calls = {}

    def advises(prompt, context_tokens=0, active_project=None, **kw):
        calls.update(prompt=prompt, tokens=context_tokens, project=active_project)
        return {"lane": "jarvis-escalate", "recommended": True,
                "would_send": "[scrubbed words]", "why": "worth leaving the PC"}
    mod.evaluate_route = advises
    sys.modules["jarvis_auto_router"] = mod
    try:
        got = P.route_for_turn("a hard question", context_tokens=1234, store=s)
    finally:
        if real == "<missing":
            del sys.modules["jarvis_auto_router"]
        else:
            sys.modules["jarvis_auto_router"] = real
    check("all three on and the router advises: the lane it named",
          got["lane"] == "jarvis-escalate" and got["recommended"] is True, got)
    check("... called exactly the frozen contract",
          calls.get("prompt") == "a hard question" and calls.get("tokens") == 1234
          and isinstance(calls.get("project"), dict), calls)
    check("... and the pill says Auto-Route to Cloud",
          got["routing"] == "Local / Auto-Route to Cloud", got)

    mod.evaluate_route = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    sys.modules["jarvis_auto_router"] = mod
    try:
        got = P.route_for_turn("hello", store=s)
    finally:
        if real == "<missing":
            del sys.modules["jarvis_auto_router"]
        else:
            sys.modules["jarvis_auto_router"] = real
    check("a router that RAISES still means local", got["lane"] == "local", got)

    mod.evaluate_route = lambda *a, **k: "not a dict"
    sys.modules["jarvis_auto_router"] = mod
    try:
        got = P.route_for_turn("hello", store=s)
    finally:
        if real == "<missing":
            del sys.modules["jarvis_auto_router"]
        else:
            sys.modules["jarvis_auto_router"] = real
    check("advice this cannot read still means local", got["lane"] == "local", got)

    mod.evaluate_route = lambda *a, **k: {"lane": "jarvis-escalate",
                                          "recommended": False, "why": "too easy"}
    sys.modules["jarvis_auto_router"] = mod
    try:
        got = P.route_for_turn("hello", store=s)
    finally:
        if real == "<missing":
            del sys.modules["jarvis_auto_router"]
        else:
            sys.modules["jarvis_auto_router"] = real
    check("a lane named without `recommended` is advice, not permission",
          got["lane"] == "local", got)
    P.set_active_project(None, store=s)


def t_the_project_context_is_the_project_and_never_a_private_number():
    s = fresh()
    p = s.create({"name": "App", "kind": "coding", "instructions": "Use pytest."},
                 here=True)
    s.update(p["id"], {"notes": ["Pinned one"], "goals": ["step-1"]}, here=True)
    s.add_benchmark(p["id"], {"name": "Tests passing", "kind": "number",
                              "unit": "", "better": "higher"}, here=True)
    s.add_benchmark(p["id"], {"name": "Weight", "kind": "number", "unit": "kg"},
                    here=True)
    first = s.get(p["id"])["benchmark_list"][0]["id"]
    s.log(p["id"], first, 12)
    P.set_active_project(p["id"], store=s)
    ctx = P.project_context(store=s)
    check("the active project's own instructions are in it",
          ctx["active"] is True and ctx["instructions"] == "Use pytest.", ctx)
    check("... its pinned notes and goals too",
          ctx["pinned_notes"] == ["Pinned one"] and ctx["goals"] == ["step-1"], ctx)
    names = [b["name"] for b in ctx["benchmarks"]]
    check("... and its benchmarks, by name", "Tests passing" in names, names)
    check("a PRIVATELY marked benchmark is NOT put in front of a model",
          "Weight" not in names and ctx["held_back"] == 1, ctx)
    check("... and the sentence says one was held back",
          "private" in ctx["benchmarks_words"], ctx["benchmarks_words"])
    check("the pill is Local-Only while Shareable is off",
          ctx["routing"] == "Local-Only", ctx["routing"])
    s.set_shareable_on(p["id"])
    check("... still Local-Only with Auto-Route off",
          P.project_context(store=s)["routing"] == "Local-Only")
    s.set_auto_route_cloud_on(p["id"])
    check("... and Auto-Route to Cloud only when BOTH switches are on",
          P.project_context(store=s)["routing"] == "Local / Auto-Route to Cloud")
    P.set_active_project(None, store=s)
    off = P.project_context(store=s)
    check("no active project: no context at all, and it says why",
          off["active"] is False and off["instructions"] == ""
          and "No project" in off["why"], off)


def t_a_project_edit_leaves_a_receipt_and_undo_cannot_flip_a_switch():
    s = fresh()
    p = s.create({"name": "App", "kind": "coding"}, here=True)
    s.set_shareable_on(p["id"])
    s.set_auto_route_cloud_on(p["id"])
    s.update(p["id"], {"instructions": "First"}, here=True)
    try:
        import jarvis_receipts as R
    except Exception as exc:                    # pragma: no cover
        skip(f"jarvis_receipts is not importable here ({type(exc).__name__})")
        return
    row = next((r for r in (R.recent(limit=40) or [])
                if r.get("tool_name") == "project_edit"), None)
    check("an edit leaves a project_edit receipt", row is not None, row)
    if row is None:
        return
    check("... naming the project edited", "App" in json.dumps(row), json.dumps(row)[:200])
    s.update(p["id"], {"instructions": "Second"}, here=True)
    P.restore_project(p["id"], {"name": "App", "instructions": "First", "notes": [],
                                "goals": [], "work_list": None, "folder": None}, store=s)
    now = s.get(p["id"])
    check("Undo puts the words back", now["instructions"] == "First", now["instructions"])
    check("... and CANNOT turn Shareable back on through Undo (rule 4)",
          now["shareable"] is True)
    check("... nor Auto-Route", now["auto_route_cloud"] is True)
    check("... because neither switch is an undoable field",
          "shareable" not in P.UNDOABLE_FIELDS
          and "auto_route_cloud" not in P.UNDOABLE_FIELDS, P.UNDOABLE_FIELDS)


def t_the_writer_that_was_missing_is_in_the_conversation_insert():
    """Step 4's own bug: the `project` column has existed since step 1 with
    nothing filling it. This is the source check that the writer is there, and
    that it reads the ACTIVE project rather than a value passed down from a
    caller this repository does not own (jarvis_hud.py is the owner's)."""
    import jarvis_chat_log as C
    _no_mode_file()
    check("with no project active the writer's own reader answers None",
          C._active_project_id() is None)
    s = fresh()
    p = s.create({"name": "App", "kind": "coding"}, here=True)
    P.set_active_project(p["id"], store=s)
    check("with one active it reads that project",
          C._active_project_id() == p["id"])
    P.mode_path().write_text("{oops", encoding="utf-8")
    check("a broken state file means NO project, never a raise",
          C._active_project_id() is None)
    _no_mode_file()
    flat = " ".join((HERE / "jarvis_chat_log.py").read_text(
        encoding="utf-8").replace('"', " ").split())
    check("the conversation INSERT carries `project`",
          "INSERT INTO conversations (id, title, started, updated, device,"
          " kind, project) VALUES" in flat)
    check("... and fills it from the active project",
          "_active_project_id()))" in flat)
    check("... and an older chat joins the project once, never overwritten",
          "project IS NULL" in flat and "_fill_project(c, cid)" in flat)


def t_the_guardian_store_is_this_suites_own():
    """Project Mode's pre-write hook must not touch the owner's real store."""
    import jarvis_file_guardian as GF
    home = os.path.realpath(str(GF.home_dir()))
    check("the guardian store Project Mode copies the pointer into is under this "
          "suite's temp folder", home.startswith(os.path.realpath(str(_TMP))),
          (home, str(_TMP)))
    receipts = os.path.realpath(str(os.environ.get("JARVIS_RECEIPTS_DB", "")))
    check("... and the receipts DB it links is under the same temp folder",
          receipts.startswith(os.path.realpath(str(_TMP))), receipts)


# --------------------------------------------------------------------------
#   The plan store (2026-11-19, PM1; docs/JARVIS-API.md section 88.7)
# --------------------------------------------------------------------------

#: The projects.db shape exactly as it was BEFORE the plan store: thirteen
#: project columns and the five original tables. Hand-written here on purpose:
#: building it from `P._SCHEMA` would prove nothing, because that schema is the
#: thing the extension is added to.
_OLD_PROJECTS_DB = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '[]',
    folder TEXT,
    shareable INTEGER NOT NULL DEFAULT 0,
    auto_route_cloud INTEGER NOT NULL DEFAULT 0,
    work_list TEXT,
    goals TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL,
    changed REAL NOT NULL,
    app TEXT
);
CREATE TABLE benchmarks (
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
CREATE TABLE results (
    id TEXT PRIMARY KEY,
    bench TEXT NOT NULL,
    value REAL NOT NULL,
    at REAL NOT NULL,
    source TEXT NOT NULL,
    logged REAL NOT NULL
);
CREATE TABLE balance_axes (
    position INTEGER NOT NULL,
    kind TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT ''
);
CREATE TABLE project_facts (
    project TEXT NOT NULL,
    fact INTEGER NOT NULL,
    created REAL NOT NULL,
    PRIMARY KEY (project, fact)
);
"""

#: The exact thirteen project columns an older (pre-plan) projects.db has.
_SCHEMA_COLS_13 = ("id", "name", "kind", "instructions", "notes", "folder",
                   "shareable", "auto_route_cloud", "work_list", "goals",
                   "created", "changed", "app")

_DATE = "2026-11-19"
_NOW = time.mktime(time.strptime("2026-11-19 09:30:00", "%Y-%m-%d %H:%M:%S"))


class _AnswerSched:
    """A made-up scheduler for the three read answers. `todos` is what the
    work-list source sees; a card raised by a read answer is a failure."""

    def __init__(self, todos=()):
        self._todos = list(todos)
        self.commands = []

    def todos(self):
        return self._todos

    def listed(self):
        return []

    def mark_command(self, text):
        self.commands.append(text)

    def act(self, *args, **kwargs):
        raise AssertionError("a card was raised by a read-only answer")


class _FakeGoals:
    def __init__(self, goals):
        self._goals = list(goals)

    def list(self):
        return list(self._goals)

    def next_open_step(self, goal_id):
        return {"step": "Write the plan", "by": "Friday"}


def _ticking_clock():
    ticks = [1_790_000_000.0]

    def tick():
        ticks[0] += 1.0
        return ticks[0]

    return tick


def _old_projects_db(path):
    """Write the pre-plan 13-column database and one row of each kind."""
    import sqlite3
    c = sqlite3.connect(str(path))
    c.executescript(_OLD_PROJECTS_DB)
    c.execute("INSERT INTO projects (id, name, kind, instructions, notes, work_list, "
              "goals, created, changed) VALUES (?,?,?,?,?,?,?,?,?)",
              ("a" * 32, "Before plan", "coding", "Keep it", '["a note"]', "garden",
               '["g1"]', 5.0, 5.0))
    c.execute("INSERT INTO benchmarks (id, project, name, kind, unit, created, changed) "
              "VALUES (?,?,?,?,?,?,?)",
              ("b" * 32, "a" * 32, "Pushups", "number", "reps", 5.0, 5.0))
    c.execute("INSERT INTO results (id, bench, value, at, source, logged) "
              "VALUES (?,?,?,?,?,?)", ("c" * 32, "b" * 32, 20.0, 5.0, "app", 5.0))
    c.commit()
    c.close()


def t_the_plan_store_extends_an_old_database():
    """PM1 is an EXTENSION of the shipped projects.db, not a migration and not
    a second store. A current-shape (13 columns, 5 tables) database opens,
    keeps every row, and `list()`/`get()` answer exactly what they answered;
    the seven plan columns are appended nullable and the four plan tables are
    created. A refused NOT NULL ALTER is an availability failure only - the
    file is unchanged."""
    import sqlite3
    path = _TMP / "before-plan.db"
    bad = _TMP / "before-plan-bad-alter.db"
    _old_projects_db(path)
    shutil.copyfile(path, bad)
    c = sqlite3.connect(str(path))
    cols_before = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
    tables_before = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    raw = dict(zip([r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()],
                   c.execute("SELECT * FROM projects").fetchone()))
    c.close()
    check("the fixture really is the old shape: 13 columns and no plan tables",
          len(cols_before) == 13 and "app" in cols_before
          and not ({"milestones", "work_items", "work_edges", "project_events"}
                   & tables_before), (cols_before, sorted(tables_before)))

    s = P.Projects(path)
    got = s.get("a" * 32)
    check("a 13-column projects.db opens and its project is still there",
          got["name"] == "Before plan" and got["kind"] == "coding", got.get("name"))
    check("... get() returns the same values for the fields it had before",
          got["instructions"] == "Keep it" and got["notes"] == ["a note"]
          and got["goals"] == ["g1"] and got["work_list"]["name"] == "garden")
    check("... and its benchmark and number are still readable",
          len(got["benchmark_list"]) == 1
          and got["benchmark_list"][0]["name"] == "Pushups"
          and got["benchmark_list"][0]["latest"]["value"] == 20.0)
    lst = s.list()
    check("list() returns the same project",
          len(lst) == 1 and lst[0]["name"] == "Before plan"
          and lst[0]["kind"] == "coding", lst)
    state = s.plan_state("a" * 32)
    check("the seven plan fields are there on the old row and are NULL/default",
          all(state.get(column) is None for column in P.PLAN_COLUMNS)
          and state["work_items"] == 0 and state["milestones"] == 0, state)

    c = sqlite3.connect(str(path))
    cols_after = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
    info = {r[1]: r for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    tables_after = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    counts = {name: c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
              for name in ("projects", "benchmarks", "results")}
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    c.close()
    check("the 13 original columns are byte-for-byte in the same order",
          cols_after[:13] == cols_before, cols_after[:13])
    check("... and the seven plan columns are appended after them",
          cols_after == cols_before + list(P.PLAN_COLUMNS), cols_after[13:])
    check("... every one of them is NULLABLE (never a NOT NULL ALTER)",
          all(info[column][3] == 0 for column in P.PLAN_COLUMNS
              if column in info) and len(P.PLAN_COLUMNS) == 7,
          {column: info.get(column) for column in P.PLAN_COLUMNS})
    check("the four plan tables were created and no original table was rebuilt",
          {"milestones", "work_items", "work_edges", "project_events"} <= tables_after
          and {"projects", "benchmarks", "results", "balance_axes",
               "project_facts"} <= tables_after, sorted(tables_after))
    check("row counts are unchanged by the extension", counts ==
          {"projects": 1, "benchmarks": 1, "results": 1}, counts)
    check("... and the file's own integrity check still says ok",
          integrity == "ok", integrity)
    # Opening the same extended file again is idempotent: no column twice.
    s2 = P.Projects(path)
    c = sqlite3.connect(str(path))
    cols_again = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
    c.close()
    check("a second open adds nothing (the guard is idempotent)",
          cols_again == cols_after and s2.get("a" * 32)["name"] == "Before plan")

    # THE PRE-MIGRATION BACKUP (2026-11-19, ruling 5.2): an existing database
    # about to change gets its own timestamped copy BEFORE the first schema
    # statement, and a second run writes none.
    backups = sorted(_TMP.glob("before-plan.db.before-migrate-*"))
    check("the migration wrote exactly one pre-migration backup", len(backups) == 1,
          [b.name for b in backups])
    if backups:
        c = sqlite3.connect(str(backups[0]))
        backup_cols = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
        backup_tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        backup_row = c.execute("SELECT name FROM projects").fetchone()
        c.close()
        check("... made BEFORE the migration: it has the OLD 13-column schema",
              backup_cols == cols_before and not (
                  {"milestones", "work_items", "work_edges", "project_events"}
                  & backup_tables), (backup_cols, sorted(backup_tables)))
        check("... and it holds the row the migration was about to change",
              backup_row is not None and backup_row[0] == "Before plan", backup_row)
        check("... and the migrated file is still the one this test reads",
              path.is_file() and backups[0] != path)
    s3 = P.Projects(path)
    check("a second open of the migrated file adds nothing", s3.get("a" * 32)["name"]
          == "Before plan")
    check("... and leaves no trail of backups behind",
          len(sorted(_TMP.glob("before-plan.db.before-migrate-*"))) == 1)

    # THE BAD ALTER RULE, on a copy that is still the old shape: a NOT NULL
    # column with no default raises, changes nothing and returns the file
    # byte-for-byte. That is an availability failure, never data loss.
    before = bad.read_bytes()
    c = sqlite3.connect(str(bad))
    refused = raises(lambda: c.execute("ALTER TABLE projects ADD COLUMN broken "
                                       "TEXT NOT NULL"), sqlite3.OperationalError)
    c.close()
    after = bad.read_bytes()
    c = sqlite3.connect(str(bad))
    bad_cols = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
    bad_counts = {name: c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("projects", "benchmarks", "results")}
    bad_integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    c.close()
    check("a refused NOT NULL ALTER says why",
          "NOT NULL" in refused or "not null" in refused.lower(), refused)
    check("... and leaves the file byte-for-byte unchanged", before == after)
    check("... and leaves the rows, the columns and the integrity check as they were",
          bad_cols == cols_before and bad_counts ==
          {"projects": 1, "benchmarks": 1, "results": 1}
          and bad_integrity == "ok",
          (bad_counts, bad_integrity))

    # A BACKUP THAT CANNOT BE WRITTEN REFUSES THE MIGRATION: nothing is
    # altered, nothing is left behind, and the error says so in plain words.
    refuse = _TMP / "refused-migration.db"
    shutil.copyfile(bad, refuse)
    real_backup = P._migration_backup

    def _no_room(source, target):
        raise OSError("no space left on this test's disk")

    P._migration_backup = _no_room
    try:
        said = raises(lambda: P.Projects(refuse).get("a" * 32),
                      sqlite3.OperationalError)
    finally:
        P._migration_backup = real_backup
    check("a pre-migration backup that cannot be written refuses the migration",
          "pre-migration backup" in said and "nothing was changed" in said, said)
    c = sqlite3.connect(str(refuse))
    refuse_cols = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
    refuse_tables = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    refuse_rows = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    c.close()
    check("... so the file is still the old schema, with its row and no plan tables",
          refuse_cols == cols_before and refuse_rows == 1
          and not ({"milestones", "work_items", "work_edges", "project_events"}
                   & refuse_tables), (refuse_cols, sorted(refuse_tables)))
    check("... and no half-written backup was left behind",
          list(_TMP.glob("refused-migration.db.before-migrate-*")) == [])


def t_the_owner_shaped_store_migrates_and_answers_honestly():
    """The audit measured the owner's live store: 2 projects (both coding), 1
    app project, 1 work list, 0 benchmarks, 0 linked goals; goals.db has 0
    goals and schedule.db has 0 to-dos. A store shaped like THAT must migrate
    and answer - not look broken because a relation is empty. Nothing here
    assumes a benchmark, a goal or a to-do exists."""
    import sqlite3
    path = _TMP / "owner-shaped.db"
    c = sqlite3.connect(str(path))
    c.executescript(_OLD_PROJECTS_DB)
    c.execute("INSERT INTO projects (id, name, kind, instructions, notes, work_list, "
              "goals, created, changed) VALUES (?,?,?,?,?,?,?,?,?)",
              ("1" * 32, "Jarvis", "coding", "", "[]", "jarvis", "[]", 10.0, 10.0))
    c.execute("INSERT INTO projects (id, name, kind, instructions, notes, work_list, "
              "goals, created, changed, app) VALUES (?,?,?,?,?,?,?,?,?,?)",
              ("2" * 32, "Notes app", "coding", "", "[]", None, "[]",
               11.0, 11.0, "notes-app"))
    c.commit()
    c.close()
    old = _point_env("JARVIS_PROJECTS_DB", str(path))
    old_goals = _point_env("JARVIS_GOALS_DB", str(_TMP / "owner-shaped-goals.db"))
    P._reset_for_tests()
    try:
        store = P.get()
        projects = store.list()
        check("the owner-shaped store migrates and keeps both coding projects",
              len(projects) == 2 and {p["name"] for p in projects}
              == {"Jarvis", "Notes app"}
              and all(p["kind"] == "coding" for p in projects), projects)
        check("... one app project and one work list, exactly as measured",
              sum(1 for p in projects if p["app"]) == 1
              and sum(1 for p in projects if p["work_list"]) == 1,
              [(p["name"], p["app"], p["work_list"]) for p in projects])
        check("... with 0 benchmarks and 0 linked goals (not a broken read)",
              all(p["benchmarks"] == 0 and p["goals"] == [] for p in projects))
        check("the migration wrote its pre-migration backup for this file",
              len(list(_TMP.glob("owner-shaped.db.before-migrate-*"))) == 1,
              list(_TMP.glob("owner-shaped.db.before-migrate-*")))
        c = sqlite3.connect(str(path))
        cols = [r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()]
        rows = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        c.close()
        check("... and the migrated file has the 20 columns and both rows",
              cols == list(_SCHEMA_COLS_13) + list(P.PLAN_COLUMNS) and rows == 2,
              (len(cols), rows))
        P._reset_for_tests()
        res = Q.answer("what am I working on?", sched=_AnswerSched(), now=_NOW)
        said = str(res.reply)
        check("the working answer names both real projects, from projects.db",
              "projects.db" in said and _DATE in said and "2 projects" in said
              and '"Jarvis"' in said and '"Notes app"' in said, said[:400])
        check("... and says the empty relations are empty, not broken",
              "0 benchmarks" in said
              and "No milestones, work items or events are recorded" in said,
              said[:500])
        res = Q.answer("what should I work on next?", sched=_AnswerSched(todos=[]),
                       now=_NOW)
        check("the next answer is the EXACT honest empty one on this store",
              str(res.reply) == (f"Nothing is ready to work on right now (read "
                                 f"{_DATE}): projects.db has no ready work item; "
                                 f"goals.db has no active goal step; the scheduler has "
                                 f"no open work-list item."), str(res.reply))
        res = Q.answer("what's blocking the Jarvis project?", sched=_AnswerSched(),
                       now=_NOW)
        check("... and the blocking answer records no blocker, naming the project",
              str(res.reply) == (f'No blockers are recorded for the "Jarvis" project '
                                 f'in projects.db (read {_DATE}).'), str(res.reply))
    finally:
        _restore_env("JARVIS_PROJECTS_DB", old)
        _restore_env("JARVIS_GOALS_DB", old_goals)
        P._reset_for_tests()


def t_ready_work_blocking_and_the_circle_guard():
    """Ready means startable: not blocked by an open item, ordered by priority
    then due date; completing the blocker promotes the blocked item; an open
    blocker is named by blocking_chain(); a circle is refused and NOTHING is
    written (no edge, no event)."""
    s = fresh(clock=_ticking_clock())
    p = s.create({"name": "Jarvis", "kind": "coding"}, here=True)
    first = s.add_work_item(p["id"], {"title": "First by date", "status": "ready",
                                      "priority": 0, "due_date": "2026-11-20"})
    second = s.add_work_item(p["id"], {"title": "Second by date", "status": "ready",
                                       "priority": 0, "due_date": "2026-11-25"})
    later = s.add_work_item(p["id"], {"title": "Lower priority", "priority": 2})
    no_priority = s.add_work_item(p["id"], {"title": "No priority or date",
                                            "status": "ready"})
    blocker = s.add_work_item(p["id"], {"title": "The blocker", "priority": 1,
                                        "status": "backlog"})
    blocked = s.add_work_item(p["id"], {"title": "The blocked one",
                                        "status": "ready", "priority": 0})
    s.add_edge("blocks", blocker["id"], blocked["id"])
    ready = [row["title"] for row in s.ready_next()]
    check("ready order is priority first, then due date, then the earlier row",
          ready == ["First by date", "Second by date", "The blocker",
                    "Lower priority", "No priority or date"], ready)
    check("a work item with an OPEN blocker is not ready",
          "The blocked one" not in ready and
          next(row for row in s.work_items() if row["id"] == blocked["id"])["ready"]
          is False)
    direct = next(row for row in s.work_items()
                  if row["id"] == blocked["id"])["blocked_by"]
    check("... and its direct blocker is named on it",
          [b["title"] for b in direct] == ["The blocker"], direct)
    chain = s.blocking_chain(blocked["id"])
    check("blocking_chain names the open blocker",
          [b["title"] for b in chain["blockers"]] == ["The blocker"]
          and chain["blockers"][0]["depth"] == 1, chain)
    check("... and counts the link that points at it", chain["edges"] == 1)
    s.set_work_item_status(blocker["id"], "done")
    check("completing the blocker promotes the blocked item",
          any(row["id"] == blocked["id"] for row in s.ready_next()))
    chain = s.blocking_chain(blocked["id"])
    check("... the recorded link stays, but names no open blocker",
          chain["edges"] == 1 and chain["blockers"] == [], chain)
    # A project whose plan is closed offers no ready work.
    s.set_plan_fields(p["id"], {"status": "done"})
    check("a closed project offers no ready work", s.ready_next() == [])
    s.set_plan_fields(p["id"], {"status": "active"})
    check("... and it offers its work again when it is open", bool(s.ready_next()))

    # The DFS circle guard: refused, and it writes nothing at all.
    edges_before = s.edge_count()
    events_before = len(s.events())
    said = raises(lambda: s.add_edge("blocks", blocked["id"], blocker["id"]),
                  ValueError)
    check("a blocks circle is refused in words", "circle" in said, said)
    check("... and nothing was written: no edge and no event",
          s.edge_count() == edges_before and len(s.events()) == events_before,
          (s.edge_count(), len(s.events())))
    check("would_cycle() says so before the write is attempted",
          s.would_cycle("blocks", blocked["id"], blocker["id"]) is True)
    # A second ordering kind gets the same guard: one allowed link, then the
    # link that would close the circle is refused and writes nothing.
    s.add_edge("parent_child", blocker["id"], blocked["id"])
    edges_before = s.edge_count()
    events_before = len(s.events())
    said = raises(lambda: s.add_edge("parent_child", blocked["id"], blocker["id"]),
                  ValueError)
    check("... a parent_child circle is refused the same way", "circle" in said, said)
    check("... and it wrote nothing either",
          s.edge_count() == edges_before and len(s.events()) == events_before)
    said = raises(lambda: s.add_edge("blocks", blocked["id"], blocked["id"]),
                  ValueError)
    check("an item cannot link to itself", "itself" in said, said)
    said = raises(lambda: s.add_edge("blocks", blocker["id"], blocked["id"]),
                  OverflowError)
    check("the same link cannot be recorded twice", "already" in said, said)
    said = raises(lambda: s.add_edge("unknown_kind", blocker["id"], blocked["id"]),
                  ValueError)
    check("an unknown link kind is refused", "blocks" in said, said)


def t_project_next_is_one_union_of_ready_goals_and_work_lists():
    """The one canonical next answer unions the plan store's ready work with
    the two sources that already hold next-work: an active goal's first open
    step (jarvis_goals) and each project's first open work-list item (the one
    scheduler). One answer, ready items first, never the same text twice."""
    s = fresh(clock=_ticking_clock())
    p = s.create({"name": "Jarvis", "kind": "coding"}, here=True)
    ready = s.add_work_item(p["id"], {"title": "Ready first", "status": "ready",
                                      "priority": 0})
    work_list = (p.get("work_list") or {}).get("name")
    check("the project has a named work list from its name", work_list == "jarvis",
          work_list)
    fake_goals_file = _TMP / "fake-goals-used.db"
    fake_goals_file.write_text("", encoding="utf-8")
    fake = types.ModuleType("jarvis_goals")
    fake.db_path = lambda: fake_goals_file
    fake.get = lambda: _FakeGoals([{"id": "g1", "text": "Ship PM1",
                                    "status": "active"}])
    saved = sys.modules.get("jarvis_goals")
    sys.modules["jarvis_goals"] = fake
    try:
        sched = _AnswerSched([{"kind": "todo", "state": "active", "list": work_list,
                               "text": "Water the plants"}])
        out = s.project_next(3, sched=sched)
    finally:
        if saved is None:
            sys.modules.pop("jarvis_goals", None)
        else:
            sys.modules["jarvis_goals"] = saved
    check('project_next returns ONE answer: {"items", "sources"}',
          isinstance(out, dict) and set(out) == {"items", "sources"}, out)
    check("... the ready work item comes first",
          out["items"] and out["items"][0]["kind"] == "work_item"
          and out["items"][0]["text"] == "Ready first"
          and out["items"][0]["id"] == ready["id"], out["items"][:1])
    check("... then the active goal's next open step",
          [item["kind"] for item in out["items"]][:3] ==
          ["work_item", "goal", "work_list"]
          and out["items"][1]["text"] == "Write the plan"
          and out["items"][1]["goal"] == "Ship PM1", out["items"])
    check("... then the project's first open work-list item",
          out["items"][2]["kind"] == "work_list"
          and out["items"][2]["text"] == "Water the plants"
          and out["items"][2]["project_id"] == p["id"], out["items"][2])
    check("... and the sources are counted honestly",
          out["sources"]["ready"] == 1 and out["sources"]["goals"] == 1
          and out["sources"]["work_lists"] == 1, out["sources"])
    check("the cap is 3 items", len(out["items"]) <= 3)
    saved = sys.modules.get("jarvis_goals")
    sys.modules["jarvis_goals"] = fake
    try:
        scoped = s.project_next(3, sched=_AnswerSched(
            [{"kind": "todo", "state": "active", "list": work_list,
              "text": "Water the plants"}]), project_id=p["id"])
    finally:
        if saved is None:
            sys.modules.pop("jarvis_goals", None)
        else:
            sys.modules["jarvis_goals"] = saved
    check("a project-scoped next reads that project's sources only (no goal link)",
          [item["kind"] for item in scoped["items"]] == ["work_item", "work_list"],
          scoped["items"])
    no_sched = s.project_next(3)
    check("with no scheduler the work-list source is unread, not invented empty",
          no_sched["sources"]["work_lists"] is None, no_sched["sources"])


def t_project_doctor_reports_contradictions_and_fixes_nothing():
    """The doctor is a READ: it names the rows that cannot all be true, and
    it repairs none of them."""
    import sqlite3
    s = fresh(clock=_ticking_clock())
    p = s.create({"name": "Jarvis", "kind": "coding"}, here=True)
    s.add_work_item(p["id"], {"title": "Clean one", "status": "ready"})
    check("a clean plan store is ok", s.project_doctor()["ok"] is True,
          s.project_doctor())
    blocker = s.add_work_item(p["id"], {"title": "Open blocker", "status": "ready"})
    finished = s.add_work_item(p["id"], {"title": "Finished", "status": "ready"})
    s.add_edge("blocks", blocker["id"], finished["id"])
    s.set_work_item_status(finished["id"], "done")
    # Deliberately contradictory rows a real store refuses to write.
    clean = s.add_work_item(p["id"], {"title": "Clean one"})
    clean2 = s.add_work_item(p["id"], {"title": "Clean two"})
    with sqlite3.connect(str(s.path)) as c:
        c.execute("INSERT INTO milestones (id, project, title, status, created, changed) "
                  "VALUES (?,?,?,?,?,?)",
                  ("b" * 32, "c" * 32, "Orphan milestone", "planned", 1, 1))
        c.execute("INSERT INTO work_items (id, project, title, status, created, changed) "
                  "VALUES (?,?,?,?,?,?)",
                  ("d" * 32, "c" * 32, "Orphan item", "backlog", 1, 1))
        c.execute("INSERT INTO work_items (id, project, title, status, created, changed) "
                  "VALUES (?,?,?,?,?,?)",
                  ("e" * 32, p["id"], "Unknown state", "someday", 1, 1))
        c.execute("INSERT INTO project_events (id, project, at, kind) "
                  "VALUES (?,?,?,?)", ("f" * 32, "c" * 32, 1, "x"))
        c.execute("INSERT INTO work_edges (id, project, kind, src, dst, created) "
                  "VALUES (?,?,?,?,?,?)",
                  ("1" * 32, p["id"], "related", clean["id"], clean["id"], 1))
        c.execute("INSERT INTO work_edges (id, project, kind, src, dst, created) "
                  "VALUES (?,?,?,?,?,?)",
                  ("2" * 32, p["id"], "wat", clean["id"], clean2["id"], 1))
        c.execute("INSERT INTO work_edges (id, project, kind, src, dst, created) "
                  "VALUES (?,?,?,?,?,?)",
                  ("3" * 32, p["id"], "related", "9" * 32, clean["id"], 1))
        c.execute("INSERT INTO work_edges (id, project, kind, src, dst, created) "
                  "VALUES (?,?,?,?,?,?)",
                  ("4" * 32, p["id"], "blocks", clean["id"], clean2["id"], 1))
        c.execute("INSERT INTO work_edges (id, project, kind, src, dst, created) "
                  "VALUES (?,?,?,?,?,?)",
                  ("5" * 32, p["id"], "blocks", clean2["id"], clean["id"], 1))
    counts_before = {name: len(getattr(s, name)()) if name != "project_events" else
                     len(s.events()) for name in ("work_items", "milestones",
                                                  "project_events")}
    counts_before["edges"] = s.edge_count()
    doctor = s.project_doctor()
    kinds = {problem["kind"] for problem in doctor["problems"]}
    check("the doctor says the plan store is not ok", doctor["ok"] is False, doctor)
    check("... count matches the problems it lists",
          doctor["count"] == len(doctor["problems"]) > 0, doctor["count"])
    for expected in ("orphan-row", "orphan-link", "unknown-work-status",
                     "unknown-edge-kind", "self-link", "link-circle",
                     "closed-item-blocked"):
        check(f"the doctor catches {expected}", expected in kinds, sorted(kinds))
    check("... naming the ids it found",
          any("ids" in problem for problem in doctor["problems"]
              if problem["kind"] == "link-circle"),
          [p_ for p_ in doctor["problems"] if p_["kind"] == "link-circle"])
    counts_after = {name: len(getattr(s, name)()) if name != "project_events" else
                    len(s.events()) for name in ("work_items", "milestones",
                                                 "project_events")}
    counts_after["edges"] = s.edge_count()
    check("the doctor is read-only: every row is still there and none was repaired",
          counts_after == counts_before, (counts_before, counts_after))
    check("... and a second run reports exactly the same problems",
          s.project_doctor()["count"] == doctor["count"])
    # Deleting a project takes its plan rows and its event history with it,
    # so the doctor does not inherit orphans from the existing delete route.
    s.delete(p["id"])
    with sqlite3.connect(str(s.path)) as c:
        left = {name: c.execute(f"SELECT COUNT(*) FROM {name} WHERE project = ?",
                                (p["id"],)).fetchone()[0]
                for name in ("milestones", "work_items", "work_edges",
                             "project_events")}
    check("deleting a project takes its plan rows and its event history with it",
          left == {"milestones": 0, "work_items": 0, "work_edges": 0,
                   "project_events": 0}, left)
    s2 = fresh(clock=_ticking_clock())
    check("an empty store has a clean bill of health", s2.project_doctor() ==
          {"ok": True, "problems": [], "count": 0}, s2.project_doctor())


def _point_env(name, value):
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    return old


def _restore_env(name, old):
    if old is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old


def t_the_three_project_answers_answer_from_the_store():
    """The three deterministic answers: from projects.db, naming the file and
    the date they read, with EXACT honest-empty answers - and ahead of the
    model (they match in the fast path, at zero model calls)."""
    path = _TMP / "answers-projects.db"
    s = P.Projects(path)
    coding = s.create({"name": "Jarvis", "kind": "coding"}, here=True)
    trip = s.create({"name": "Trip", "kind": "life"}, here=True)
    s.add_milestone(coding["id"], {"title": "Ship PM1", "due_date": "2026-12-01"})
    first = s.add_work_item(coding["id"], {"title": "Fix the parser",
                                           "status": "ready", "priority": 0,
                                           "due_date": "2026-11-25"})
    s.add_work_item(coding["id"], {"title": "Write the tests", "status": "backlog",
                                   "priority": 1})
    s.set_plan_fields(coding["id"], {"status": "active", "target_date": "2026-12-31",
                                     "objective": "Ship the plan store"})
    old = _point_env("JARVIS_PROJECTS_DB", str(path))
    P._reset_for_tests()
    try:
        res = Q.answer("what am I working on?", sched=_AnswerSched(), now=_NOW)
        said = str(res.reply)
        check("'what am I working on' is answered by the project store",
              res is not None and res.intent == "project_working", repr(res))
        check("... from projects.db, naming the file and the date it read",
              "projects.db" in said and _DATE in said, said[:240])
        check("... with both real projects and their kinds",
              "2 projects" in said and '"Jarvis"' in said and '"Trip"' in said
              and "1 coding, 1 life" in said, said[:400])
        check("... and the plan store's real counts",
              "1 milestone" in said and "2 work items" in said and "ready" in said,
              said[:400])
        check("... and the status/target the plan fields hold",
              "status active" in said and "target 2026-12-31" in said, said[:400])

        res = Q.answer("what should I work on next?", sched=_AnswerSched(todos=[]),
                       now=_NOW)
        said = str(res.reply)
        check("'what should I work on next' is answered by project_next()",
              res is not None and res.intent == "project_next", repr(res))
        check("... naming the file and the date", "projects.db" in said
              and _DATE in said, said[:240])
        check("... with the higher-priority item first and its due date",
              said.find("Fix the parser") < said.find("Write the tests")
              and "priority 0" in said and "due 2026-11-25" in said, said[:400])

        # HONEST EMPTY: an item with no link pointing at it says exactly that.
        res = Q.answer("what's blocking Fix the parser?", sched=_AnswerSched(),
                       now=_NOW)
        said = str(res.reply)
        check("'what's blocking X' answers with no recorded blocker, naming the item",
              res is not None and res.intent == "project_blocking"
              and said == (f'No blockers are recorded for "Fix the parser" in '
                           f'projects.db (read {_DATE}).'), said)
        res = Q.answer("what's blocking the Trip project?", sched=_AnswerSched(),
                       now=_NOW)
        said = str(res.reply)
        check("... and for a project with no link rows at all",
              said == (f'No blockers are recorded for the "Trip" project in '
                       f'projects.db (read {_DATE}).'), said)
        res = Q.answer("what's blocking the Jervis project?", sched=_AnswerSched(),
                       now=_NOW)
        check("a name the store does not hold is honestly not found, never guessed",
              str(res.reply) == (f'I don\'t see a project or work item called '
                                 f'"Jervis" in projects.db (read {_DATE}), so I '
                                 f'won\'t guess.'), str(res.reply))

        # A recorded, OPEN blocker is named - for the item and for its project.
        blocker = s.add_work_item(coding["id"], {"title": "Open blocker",
                                                 "status": "ready", "priority": 1})
        s.add_edge("blocks", blocker["id"], first["id"])
        said = str(Q.answer("what's blocking Fix the parser?", sched=_AnswerSched(),
                            now=_NOW).reply)
        check("an open blocker is named for the work item",
              said == (f'"Fix the parser" is blocked by "Open blocker" (ready) '
                       f'(projects.db, read {_DATE}).'), said)
        said = str(Q.answer("what's blocking the Jarvis project?",
                            sched=_AnswerSched(), now=_NOW).reply)
        check("... and for the project, naming the blocked item and its blocker",
              said == (f'In the "Jarvis" project, 1 item is blocked (read {_DATE}): '
                       f'"Fix the parser" is waiting on "Open blocker" (ready).'), said)
        s.set_work_item_status(blocker["id"], "done")
        said = str(Q.answer("what's blocking the Jarvis project?",
                            sched=_AnswerSched(), now=_NOW).reply)
        check("a recorded blocker that is done means nothing is blocking it now",
              said == (f'Nothing is blocking the "Jarvis" project right now - every '
                       f'blocker recorded in projects.db is already done '
                       f'(read {_DATE}).'), said)

        # HONEST EMPTY: no projects.db at all - said, and nothing created.
        empty_dir = _TMP / "answers-empty"
        empty_dir.mkdir()
        empty_path = empty_dir / "projects.db"
        _restore_env("JARVIS_PROJECTS_DB", old)
        old = _point_env("JARVIS_PROJECTS_DB", str(empty_path))
        P._reset_for_tests()
        res = Q.answer("what am I working on?", sched=_AnswerSched(), now=_NOW)
        check("with no projects.db the working answer is exactly the empty one",
              str(res.reply) == (f"You have no projects on this PC yet - projects.db "
                                 f"does not exist (read {_DATE})."), str(res.reply))
        res = Q.answer("what should I work on next?", sched=_AnswerSched(), now=_NOW)
        check("... the next answer too",
              str(res.reply) == (f"Nothing is ready to work on right now - projects.db "
                                 f"does not exist on this PC yet (read {_DATE})."),
              str(res.reply))
        res = Q.answer("what's blocking the Jarvis project?", sched=_AnswerSched(),
                       now=_NOW)
        check("... and the blocking answer",
              str(res.reply) == (f'There is no projects.db on this PC yet, so no '
                                 f'blocker is recorded for "Jarvis" (read {_DATE}).'),
              str(res.reply))
        check("... and nothing created a projects.db for a read", not empty_path.exists())

        # A projects.db that exists and is empty is a DIFFERENT honest answer.
        import sqlite3
        sqlite3.connect(str(empty_path)).close()
        P._reset_for_tests()
        res = Q.answer("what am I working on?", sched=_AnswerSched(), now=_NOW)
        check("an existing but empty projects.db is said in its own words",
              str(res.reply) == (f"You have no projects on this PC - projects.db has "
                                 f"no project rows (read {_DATE})."), str(res.reply))
        res = Q.answer("what should I work on next?", sched=_AnswerSched(), now=_NOW)
        check("... and the next answer says nothing is ready",
              str(res.reply) == (f"Nothing is ready to work on right now (read "
                                 f"{_DATE}): projects.db has no ready work item; "
                                 f"goals.db has no active goal step; the scheduler has "
                                 f"no open work-list item."), str(res.reply))
        res = Q.answer("what's blocking the Jarvis project?", sched=_AnswerSched(),
                       now=_NOW)
        check("... and a project name in an empty store is honestly not found",
              str(res.reply) == (f'I don\'t see a project or work item called '
                                 f'"Jarvis" in projects.db (read {_DATE}), so I '
                                 f'won\'t guess.'), str(res.reply))
    finally:
        _restore_env("JARVIS_PROJECTS_DB", old)
        P._reset_for_tests()


def t_the_three_project_answers_are_read_only_and_the_widening_is_narrow():
    """They are RECORD READS: nothing filed, written or carded by the answer,
    and the untagged widening (UNTAGGED_RECORD_READS) still refuses an action,
    a chat-filing intent and a file write. An ordinary question still reaches
    the model."""
    folder = _TMP / "answers-purity"
    folder.mkdir(exist_ok=True)
    path = folder / "projects.db"
    s = P.Projects(path)
    p = s.create({"name": "Jarvis", "kind": "coding"}, here=True)
    s.add_work_item(p["id"], {"title": "Fix the parser", "status": "ready",
                              "priority": 0})
    old = _point_env("JARVIS_PROJECTS_DB", str(path))
    old_config = _point_env("OPENJARVIS_CONFIG_DIR", str(_TMP / "answers-config"))
    P._reset_for_tests()
    sentences = ("what am I working on?", "what should I work on next?",
                 "what's blocking the Trip project?")
    files_before = {item.name: item.read_bytes() for item in folder.iterdir()
                    if item.is_file()}
    counts_before = s.plan_counts()
    statuses_before = [(row["id"], row["status"]) for row in s.work_items()]
    try:
        for sentence in sentences:
            sched = _AnswerSched()
            res = Q.answer(sentence, sched=sched, now=_NOW)
            check(f"a read-only answer for {sentence[:32]!r}",
                  res is not None and res.made == [] and res.ids == []
                  and res.open_settings is None and res.open_brain is None, repr(res))
            check("... in READ_ONLY_INTENTS and the untagged gate",
                  res is not None and res.intent in Q.READ_ONLY_INTENTS
                  and res.intent in Q.UNTAGGED_RECORD_READS, repr(res))
            check("... and the only scheduler call is the pre-existing command "
                  "note (no card, no todo written)",
                  sched.commands == [sentence], sched.commands)
        files_after = {item.name: item.read_bytes() for item in folder.iterdir()
                       if item.is_file()}
        check("the project store is byte-for-byte unchanged by the reads",
              files_before.get("projects.db") == files_after.get("projects.db")
              and not (set(files_after) - set(files_before)),
              (sorted(files_before), sorted(files_after)))
        check("... every plan row is unchanged", s.plan_counts() == counts_before)
        check("... and so is every work item's state",
              [(row["id"], row["status"]) for row in s.work_items()] == statuses_before)

        # The explicit gate: a SUBSET of READ_ONLY_INTENTS, never the other way
        # round - `chat_tag` is read-only for "cancel that" but it FILES a chat.
        check("the untagged gate is a subset of READ_ONLY_INTENTS",
              Q.UNTAGGED_RECORD_READS <= Q.READ_ONLY_INTENTS,
              sorted(Q.UNTAGGED_RECORD_READS - Q.READ_ONLY_INTENTS))
        check("... and holds the three project reads",
              {"project_working", "project_next", "project_blocking"}
              <= Q.UNTAGGED_RECORD_READS)
        check("... but not the chat-filing intent nor a timer",
              "chat_tag" not in Q.UNTAGGED_RECORD_READS
              and "timer_set" not in Q.UNTAGGED_RECORD_READS)
        check("... nor a file write", "note_create" not in Q.UNTAGGED_RECORD_READS)

        def turn(sentence, **extra):
            body = {"messages": [{"role": "user", "content": sentence}], **extra}
            return Q.answer_turn(body, sched=_AnswerSched(), now=_NOW)

        got = turn("what should I work on next?")
        check("an UNTAGGED request (the script shape) answers the bare sentence",
              got is not None and got.intent == "project_next", repr(got))
        check("... with the same words the owner's own tagged request gets",
              got is not None
              and str(got.reply) == str(Q.answer("what should I work on next?",
                                                 sched=_AnswerSched(), now=_NOW).reply))
        tagged = Q.answer_turn({"messages": [{"role": "user",
                                              "content": "what should I work on next?",
                                              "provenance": "typed"}]},
                               sched=_AnswerSched(), now=_NOW)
        check("... and a tagged request answers the same words",
              tagged is not None and str(tagged.reply) == str(got.reply), repr(tagged))
        # CONTROLS: the widening is THREE record reads, not "everything".
        check("an ordinary untagged question still goes to the model",
              turn("tell me a joke about cats") is None)
        check("an untagged ACTION still goes to the model",
              turn("set a timer for 10 minutes") is None
              and Q.match("set a timer for 10 minutes", now=_NOW).name == "timer_set")
        check("an untagged CHAT-filing intent still goes to the model",
              turn("label this chat Work") is None
              and Q.match("label this chat Work", now=_NOW).name == "chat_tag")
        check("an untagged FILE/WRITE intent still goes to the model",
              turn("write a note called Groceries") is None
              and Q.match("write a note called Groceries", now=_NOW).name
              == "note_create")
        check("a deterministic read OUTSIDE the gate keeps the old rule",
              turn("how many models are installed") is None)
        check("a pasted project question keeps its old rule (a tag was given)",
              Q.answer_turn({"messages": [{"role": "user",
                                           "content": "what should I work on next?",
                                           "provenance": "pasted"}]},
                            sched=_AnswerSched(), now=_NOW) is None)
        check("a private chat keeps its own stricter rule",
              turn("what should I work on next?", private=True) is None)
        check("the old reader is untouched: untagged is still NOT the owner's own",
              Q.newest_own_words({"messages": [{"role": "user",
                                                "content": "what am I working on?"}]})
              is None)
        check("... while a tagged one still is",
              Q.newest_own_words({"messages": [
                  {"role": "user", "content": "what am I working on?",
                   "provenance": "typed"}]}) == "what am I working on?")
    finally:
        _restore_env("JARVIS_PROJECTS_DB", old)
        _restore_env("OPENJARVIS_CONFIG_DIR", old_config)
        P._reset_for_tests()


# ==========================================================================
#   PM2 (2026-11-20): the import/seed and the plan store's typed tools
# ==========================================================================
# The store (jarvis_projects.py, PM1) has the rows; these prove the import
# that fills it from the two stores that already hold the owner's work
# (goals.db, read-only; the one scheduler's work lists, read-only) and the
# typed model tools that are now the only doors into writing them. Everything
# here drives the REAL jarvis_agent.TOOLS entries through the REAL `_one_call`,
# with a fake approval gate where a card is expected - so "one card", "zero
# rows on deny" and "nothing runs" are read off the same contract an install
# runs, and the clean-turn tier is the REAL published jarvis_gate.py with the
# SHIPPED [autonomy.tiers].

_PM2 = _TMP / "pm2"
_PM2.mkdir(exist_ok=True)
_PM2_VAULT = _PM2 / "vault"
(_PM2_VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)

_AGENT = None
_REAL_TIERS: dict = {}
_GATE = None


def _pm2_agent():
    """jarvis_agent, imported once - no model, no socket."""
    global _AGENT
    if _AGENT is None:
        import jarvis_agent
        _AGENT = jarvis_agent
    return _AGENT


def _pm2_tiers() -> dict:
    """The SHIPPED [autonomy.tiers], read from the template an install gets."""
    if _REAL_TIERS:
        return dict(_REAL_TIERS)
    import tomllib
    cfg = tomllib.loads((HERE / "rebuilt" / "jarvis-framework.toml")
                        .read_text(encoding="utf-8"))
    _REAL_TIERS.update(dict(cfg.get("autonomy", {}).get("tiers") or {}))
    return dict(_REAL_TIERS)


def _pm2_gate():
    """The REAL published jarvis_gate.py (jarvis-backend/), or None here.

    A gate is one of the files that live only on the owner's PC, so this
    repository keeps the published base and that is what is loaded - with the
    SHIPPED tier table, so the tier proved is the tier an install gets.
    """
    global _GATE
    if _GATE is not None:
        return _GATE
    try:
        import _base
        base = _base.folder("jarvis_gate.py")
    except Exception:                                     # noqa: BLE001
        return None
    if base is None:
        return None
    tiers = _pm2_tiers()
    if not tiers:
        return None
    fw.load_framework = lambda: {
        "autonomy": {"unknown_action_tier": "ask", "tiers": tiers},
        "logging": {"redact_private_content_in_logs": True},
    }
    _base.put_on_path(base)
    import jarvis_gate
    _GATE = jarvis_gate
    return _GATE


class _PmVerdict:
    def __init__(self, allowed=True, outcome="approved", tier="ask"):
        self.allowed = bool(allowed)
        self.outcome = outcome
        self.tier = tier
        self.request_id = "pm2-card"
        self.reason = ""


class _PmChecker:
    """A fake approval gate: records every card, answers with one verdict."""

    def __init__(self, allowed=True, outcome="approved", tier="ask"):
        self.calls = []
        self.verdict = _PmVerdict(allowed, outcome, tier)

    def __call__(self, action, detail, prompt):
        self.calls.append((action, dict(detail or {}), str(prompt or "")))
        return self.verdict


def _pm2_call(name, args, checker, watch=None):
    """Drive ONE real `_one_call` and read the tool result and the step."""
    AG = _pm2_agent()
    call = {"id": "pm2-" + name,
            "function": {"name": name, "arguments": json.dumps(args)}}
    convo, steps = [], []

    class _Out:
        status = None
        gone = False

        def set_status(self, word):
            self.status = word

        def card_answered(self, verdict):
            pass

    AG._one_call(call, [name], convo, steps, checker,
                 lambda *a, **k: None, _Out(), lambda *a, **k: None,
                 watch=watch)
    return (json.loads(convo[-1]["content"]) if convo else {}), steps


def _pm2_use(store):
    """Point the tools' own store door at `store`; return the old env value."""
    old = os.environ.get("JARVIS_PROJECTS_DB")
    os.environ["JARVIS_PROJECTS_DB"] = str(store.path)
    P._reset_for_tests()
    return old


def _pm2_unuse(old):
    if old is None:
        os.environ.pop("JARVIS_PROJECTS_DB", None)
    else:
        os.environ["JARVIS_PROJECTS_DB"] = old
    P._reset_for_tests()


class _PmGoals:
    """The two calls the seed and the next answer make on the goals store."""

    def __init__(self, goals):
        self._goals = [dict(g) for g in goals]

    def list(self):
        return [dict(g) for g in self._goals]

    def next_open_step(self, goal_id):
        for goal in self._goals:
            if goal["id"] != goal_id:
                continue
            for step in goal.get("plan") or []:
                if step.get("state") == "open":
                    return dict(step)
        return None


def _pm2_goals(goals, path):
    fake = types.ModuleType("jarvis_goals")
    fake.db_path = lambda: Path(path)
    fake.get = lambda: _PmGoals(goals)
    saved = sys.modules.get("jarvis_goals")
    sys.modules["jarvis_goals"] = fake
    return saved


def _pm2_sched(sched):
    fake = types.ModuleType("jarvis_schedule")
    fake.get = lambda: sched
    fake.list_title = (lambda key: (key[0].upper() + key[1:] + " list")
                       if key else "To-do list")
    saved = sys.modules.get("jarvis_schedule")
    sys.modules["jarvis_schedule"] = fake
    return saved


def _pm2_restore_module(name, saved):
    if saved is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = saved


class _PmSched:
    """Enough of the one scheduler for the import and the next answer."""

    def __init__(self, todos=()):
        self._todos = [dict(t) for t in todos]
        self.commands = []

    def todos(self):
        return [dict(t) for t in self._todos]

    def listed(self):
        return []

    def mark_command(self, text):
        self.commands.append(text)


def _pm2_owner_store():
    """A store shaped like the owner's: two coding projects, no plan rows."""
    s = fresh(clock=_ticking_clock())
    coding = s.create({"name": "Site", "kind": "coding"}, here=True)
    other = s.create({"name": "Tool", "kind": "coding"}, here=True)
    return s, coding, other


def _pm2_link_goal(store, project_id, goal_id):
    import sqlite3
    with sqlite3.connect(str(store.path)) as c:
        c.execute("UPDATE projects SET goals = ? WHERE id = ?",
                  (json.dumps([goal_id]), project_id))


_PM2_GOALS = [{
    "id": "g1", "text": "Ship the plan", "status": "active",
    "plan": [
        {"id": "s1", "step": "Write the plan", "by": "before winter",
         "state": "open", "needs": []},
        {"id": "s2", "step": "Test the plan", "by": "",
         "state": "open", "needs": ["s1"]},
        {"id": "s3", "step": "Agree the plan", "by": "",
         "state": "done", "needs": []},
    ],
}]
_PM2_DUE = time.mktime(time.strptime("2026-12-01", "%Y-%m-%d"))
_PM2_DUE_DATE = time.strftime("%Y-%m-%d", time.localtime(_PM2_DUE))


def _pm2_sources(store, project):
    """A linked goal with steps, and one scheduler item on the project's list."""
    _pm2_link_goal(store, project["id"], "g1")
    work_list = (project.get("work_list") or {}).get("name") or ""
    sched = _PmSched([{"id": "t1", "kind": "todo", "state": "active",
                       "list": work_list, "text": "Buy the domain",
                       "due": _PM2_DUE}])
    goals_file = _PM2 / "goals.db"
    goals_file.write_text("", encoding="utf-8")
    return sched, goals_file


def t_pm2_the_seed_imports_once_and_invents_no_date():
    """The import/seed: reads goals.db and the scheduler READ-ONLY, proposes
    the source's own words on ONE card, writes on a yes, keeps the source's
    dates and invents none, and a second run creates nothing new."""
    s, project, _other = _pm2_owner_store()
    sched, goals_file = _pm2_sources(s, project)
    old_goals = _pm2_goals(_PM2_GOALS, goals_file)
    old_sched = _pm2_sched(sched)
    old_env = _pm2_use(s)
    try:
        # ---- the DRY RUN: the whole proposal, and not one byte written ----
        before_bytes = s.path.read_bytes()
        counts_before = s.plan_counts()
        dry = _PmChecker()
        res, _steps = _pm2_call("project_seed_plan", {"dry_run": True}, dry)
        check("the seed's dry run answers with the source's own rows",
              res.get("ok") is True and res.get("dry_run") is True
              and [item["title"] for item in res.get("items") or []]
              == ["Ship the plan", "Write the plan", "Test the plan",
                  "Agree the plan", "Buy the domain"], res)
        check("... and raises NO card at all", dry.calls == [], dry.calls)
        check("... and writes nothing: not one plan row, not one byte",
              s.plan_counts() == counts_before
              and s.path.read_bytes() == before_bytes, s.plan_counts())
        check("... and reports how many rows WOULD be imported",
              "5 row(s) would be imported" in str(res.get("message")),
              res.get("message"))

        # ---- the WRITE: ONE card, the picture the owner approved ----
        yes = _PmChecker()
        res, _steps = _pm2_call("project_seed_plan", {}, yes)
        check("the import asks exactly ONE card", len(yes.calls) == 1, yes.calls)
        check("... under the existing change_own_config action",
              bool(yes.calls) and yes.calls[0][0] == "change_own_config", yes.calls[:1])
        prompt = yes.calls[0][2] if yes.calls else ""
        check("... showing every row it would save, in the source's words",
              '"Ship the plan"' in prompt and '"Write the plan"' in prompt
              and '"Buy the domain"' in prompt and "Nothing will run" in prompt, prompt)
        check("... and the store's own read built the picture it showed",
              "milestone" in prompt and "due " + _PM2_DUE_DATE in prompt, prompt)
        check("the approved card writes the plan rows",
              res.get("ok") is True and res.get("wrote") is True
              and res.get("created") == {"milestones": 1, "work_items": 4,
                                         "edges": 1}, res)
        items = {row["title"]: row for row in s.work_items()}
        check("... the goal's steps, its milestone and the work-list item",
              set(items) == {"Write the plan", "Test the plan", "Agree the plan",
                             "Buy the domain"}, sorted(items))
        check("... with the source's own statuses (a done step imports done)",
              items["Agree the plan"]["status"] == "done"
              and items["Write the plan"]["status"] == "backlog", items)
        check("... and the goal step's rough label kept as words, NEVER as a date",
              items["Write the plan"]["due_date"] is None
              and "before winter" in items["Write the plan"]["detail"],
              items["Write the plan"])
        check("... every imported work item that had no date stays undated",
              all(row["due_date"] is None for name, row in items.items()
                  if name != "Buy the domain"))
        check("... and a source row that REALLY had a due date imports it unchanged",
              items["Buy the domain"]["due_date"] == _PM2_DUE_DATE,
              items["Buy the domain"]["due_date"])
        check("... the milestone is undated too",
              all(row["due_date"] is None for row in s.milestones()))
        check("... the step that needs another is imported as ONE blocking link",
              s.edge_count() == 1, s.edge_count())
        check("... every created row is in the append-only log, one event each",
              len([e for e in s.events() if e["kind"] == P.SEED_EVENT]) == 6,
              [e["kind"] for e in s.events()])
        check("... and the goals store itself was never written to",
              goals_file.read_text(encoding="utf-8") == "")

        # ---- the SECOND run: nothing new, and no card to answer ----
        counts = s.plan_counts()
        events = len(s.events())
        again = _PmChecker()
        res2, _steps = _pm2_call("project_seed_plan", {}, again)
        check("a second run creates nothing new",
              res2.get("ok") is True and res2.get("wrote") is False
              and s.plan_counts() == counts and len(s.events()) == events,
              (res2, s.plan_counts(), counts))
        check("... and says so in the owner's words",
              res2.get("message") == P.SEED_ALL_DONE, res2.get("message"))
        check("... and asks no card at all: there is nothing to approve",
              again.calls == [], again.calls)

        # ---- the sources are READ-ONLY: a goals store that is not there ----
        missing = _PM2 / "no-goals-here.db"
        _pm2_goals(_PM2_GOALS, missing)
        res3, _st = _pm2_call("project_seed_plan", {"dry_run": True}, _PmChecker())
        check("a goals.db that does not exist is not created by the import",
              res3.get("ok") is True and not missing.exists(), res3)
    finally:
        _pm2_restore_module("jarvis_goals", old_goals)
        _pm2_restore_module("jarvis_schedule", old_sched)
        _pm2_unuse(old_env)


def t_pm2_the_plan_card_is_one_card_and_runs_nothing():
    """project_decompose_plan: ONE card; a refused card writes ZERO rows; a yes
    writes the plan and NOTHING runs. A proposed circle is refused before the
    card, so nothing is written and no card asks about a plan that cannot be
    saved."""
    s, project, _other = _pm2_owner_store()
    old_env = _pm2_use(s)
    try:
        yes = _PmChecker()
        res, _steps = _pm2_call("project_decompose_plan", {
            "project": "Site",
            "milestones": [{"title": "Stage one"}],
            "items": [{"title": "Draft it"},
                      {"title": "Ship it", "milestone": 1, "priority": 0}],
            "blocks": [[1, 2]],
        }, yes)
        check("the plan is written on ONE card", len(yes.calls) == 1, yes.calls)
        check("... under the existing change_own_config action",
              bool(yes.calls) and yes.calls[0][0] == "change_own_config",
              yes.calls[:1])
        prompt = yes.calls[0][2] if yes.calls else ""
        check("... showing the whole plan: milestones, items and the blocking pair",
              "Stage one" in prompt and "Draft it" in prompt and "Ship it" in prompt
              and "must finish before" in prompt, prompt)
        check("... and saying plainly that nothing runs and no date is set",
              "Nothing runs" in prompt and "no date is set" in prompt, prompt)
        check("the yes writes the rows",
              res.get("ok") is True and res.get("created") == {
                  "milestones": 1, "work_items": 2, "edges": 1}, res)
        check("... and the answer says NOTHING RAN",
              "Nothing ran." in str(res.get("message")), res.get("message"))
        check("... exactly one milestone, two items and one edge exist",
              s.plan_counts()[project["id"]]["milestones"] == 1
              and s.plan_counts()[project["id"]]["work_items"] == 2
              and s.edge_count() == 1, s.plan_counts())
        check("... the blocker really makes the second item not ready",
              [row["title"] for row in s.ready_next()] == ["Draft it"],
              [(row["title"], row["ready"]) for row in s.work_items()])
        check("... no date was set by the plan card",
              all(row["due_date"] is None for row in s.work_items())
              and all(row["due_date"] is None for row in s.milestones()))
        check("... and only plan rows and their own events changed",
              {e["kind"] for e in s.events()} ==
              {"milestone_added", "work_item_added", "edge_added"},
              [e["kind"] for e in s.events()])

        # ---- a DENIED card writes nothing at all ----
        before_rows = s.plan_counts()
        before_events = len(s.events())
        no = _PmChecker(allowed=False, outcome="denied")
        res, _steps = _pm2_call("project_decompose_plan", {
            "project": "Site", "milestones": [], "items": [{"title": "Never"}],
            "blocks": []}, no)
        check("a refused plan card writes ZERO rows",
              s.plan_counts() == before_rows and len(s.events()) == before_events,
              (s.plan_counts(), before_rows))
        check("... and the model is told the card said no",
              res.get("ok") is False and "refused" in str(res.get("error")), res)
        check("... one card, no second write", len(no.calls) == 1, no.calls)

        # ---- a CIRCLE is refused BEFORE any card ----
        rows = s.plan_counts()
        events = len(s.events())
        circle = _PmChecker()
        res, _steps = _pm2_call("project_decompose_plan", {
            "project": "Site", "milestones": [],
            "items": [{"title": "One"}, {"title": "Two"}],
            "blocks": [[1, 2], [2, 1]]}, circle)
        check("a proposed circle of blockers is refused",
              res.get("ok") is False and "circle" in str(res.get("error")), res)
        check("... BEFORE any card is raised", circle.calls == [], circle.calls)
        check("... and it writes nothing: no milestone, item, edge or event",
              s.plan_counts() == rows and len(s.events()) == events,
              (s.plan_counts(), rows))
    finally:
        _pm2_unuse(old_env)


def t_pm2_a_link_circle_is_refused_by_the_tool_and_writes_nothing():
    """work_item_link_dependency keeps the store's existing DFS circle guard:
    the link that would close a circle is refused before a card, and NOTHING
    is written - no edge, no event."""
    s, project, _other = _pm2_owner_store()
    first = s.add_work_item(project["id"], {"title": "First step"})
    second = s.add_work_item(project["id"], {"title": "Second step"})
    s.add_edge("blocks", first["id"], second["id"])
    old_env = _pm2_use(s)
    try:
        edges = s.edge_count()
        events = len(s.events())
        cards = _PmChecker()
        res, _steps = _pm2_call("work_item_link_dependency",
                                {"from": "Second step", "to": "First step",
                                 "kind": "blocks"}, cards)
        check("a link that would close a circle is refused",
              res.get("ok") is False and "circle" in str(res.get("error")), res)
        check("... before a card is raised", cards.calls == [], cards.calls)
        check("... and it writes nothing: no edge, no event",
              s.edge_count() == edges and len(s.events()) == events,
              (s.edge_count(), edges, len(s.events()), events))
        # A legal link still runs cardless on a clean owner turn through the
        # real gate, and it writes the one row plus its event.
        gate = _pm2_gate()
        if gate is None:
            skip("the real gate is not in this tree, so the cardless link was not run")
        else:
            res, steps = _pm2_call("work_item_link_dependency",
                                   {"from": "First step", "to": "Second step",
                                    "kind": "related"}, _pm2_agent()._gate_check)
            check("a legal link runs with no card through the real gate",
                  res.get("ok") is True and bool(steps)
                  and steps[-1].get("outcome") == "auto", (res, steps[-1:]))
            check("... and adds exactly one edge",
                  s.edge_count() == edges + 1, s.edge_count())
    finally:
        _pm2_unuse(old_env)


def t_pm2_a_tainted_turn_asks_and_a_clean_one_does_not():
    """The owner-direct plan writes are cardless on a clean owner turn (the
    shipped "auto" todo_add line) and are swapped to ONE change_own_config card
    when the conversation is tainted - and a refused card writes nothing."""
    AG = _pm2_agent()
    s, project, _other = _pm2_owner_store()
    old_env = _pm2_use(s)
    try:
        gate = _pm2_gate()
        if gate is None:
            skip("the real gate is not in this tree, so the clean-turn tier was not run")
        else:
            before = len(gate.pending())
            res, steps = _pm2_call("work_item_add",
                                   {"project": "Site", "title": "Clean step"},
                                   AG._gate_check)
            check("a CLEAN owner turn adds the item with no card",
                  res.get("ok") is True
                  and bool(steps) and steps[-1].get("outcome") == "auto",
                  (res, steps[-1:]))
            check("... and nothing was left waiting for approval",
                  len(gate.pending()) == before, gate.pending())
            clean = [row for row in s.work_items() if row["title"] == "Clean step"]
            check("... the row is really there", len(clean) == 1, clean)

        # ---- TAINTED: every plan write raises ONE change_own_config card ----
        no = _PmChecker(allowed=False, outcome="denied")
        res, _steps = _pm2_call("work_item_add",
                                {"project": "Site", "title": "Tainted step"},
                                no, watch=AG._TurnWatch(tainted=True))
        check("a TAINTED turn forces the write to ONE change_own_config card",
              len(no.calls) == 1 and no.calls[0][0] == "change_own_config", no.calls)
        prompt = no.calls[0][2] if no.calls else ""
        check("... whose card says outside text shaped this request",
              "outside text" in prompt.lower(), prompt)
        check("... a NO writes nothing",
              res.get("ok") is False
              and not [row for row in s.work_items()
                       if row["title"] == "Tainted step"], res)

        yes = _PmChecker()
        res, _steps = _pm2_call("work_item_add",
                                {"project": "Site", "title": "Tainted step"},
                                yes, watch=AG._TurnWatch(tainted=True))
        check("... a YES writes the row the card named",
              res.get("ok") is True
              and [row["title"] for row in s.work_items()
                   if row["title"] == "Tainted step"] == ["Tainted step"], res)
        check("... still exactly one card", len(yes.calls) == 1, yes.calls)

        # A pasted (not typed) newest message is the same rule.
        no2 = _PmChecker(allowed=False, outcome="denied")
        watch2 = AG._TurnWatch(messages=[{"role": "user", "content": "pasted words",
                                          "provenance": "pasted"}])
        res, _steps = _pm2_call("work_item_update_status",
                                {"item": "Clean step", "status": "in_progress"},
                                no2, watch=watch2)
        check("a turn whose newest message was PASTED also asks one card",
              len(no2.calls) == 1 and no2.calls[0][0] == "change_own_config",
              no2.calls)
        check("... and a no leaves the status alone",
              [row["status"] for row in s.work_items()
               if row["title"] == "Clean step"] == ["backlog"],
              [row["status"] for row in s.work_items()
               if row["title"] == "Clean step"])
    finally:
        _pm2_unuse(old_env)


def t_pm2_the_hub_export_is_one_notes_card_and_a_guardian_copy():
    """project_export_obsidian_hub: ONE edit_vault_note card raised by the
    notes editor, a one-way Markdown copy of the project in the vault, the File
    Guardian copy first when an existing note is replaced, and no write to the
    project store."""
    s, project, _other = _pm2_owner_store()
    s.add_milestone(project["id"], {"title": "Stage one"})
    s.add_work_item(project["id"], {"title": "Draft it"})
    old_env = _pm2_use(s)
    old_vault = os.environ.get("JARVIS_OBSIDIAN_VAULT")
    os.environ["JARVIS_OBSIDIAN_VAULT"] = str(_PM2_VAULT)
    try:
        events_before = len(s.events())
        counts_before = s.plan_counts()
        cards = _PmChecker()
        res, _steps = _pm2_call("project_export_obsidian_hub",
                                {"project": "Site"}, cards)
        note_path = _PM2_VAULT / "Projects" / "Site.md"
        check("the export raises exactly ONE notes-editor card",
              len(cards.calls) == 1
              and cards.calls[0][0] == "edit_vault_note", cards.calls[:1])
        card_prompt = cards.calls[0][2] if cards.calls else ""
        check("... showing the note's path and its own words",
              "Projects/Site.md" in card_prompt and "# Site" in card_prompt,
              cards.calls[:1])
        check("the export writes the hub note into the vault",
              res.get("ok") is True and note_path.is_file(), res)
        text = note_path.read_text(encoding="utf-8") if note_path.is_file() else ""
        check("... a one-way picture of the project",
              "# Site" in text and P.HUB_NOTE_WORDS in text
              and "Stage one" in text and "Draft it" in text, text[:300])
        check("... and the project store is NOT changed by an export",
              s.plan_counts() == counts_before
              and len(s.events()) == events_before, (s.plan_counts(), counts_before))

        # ---- replacing an existing note: the File Guardian copy comes first ----
        try:
            import jarvis_file_guardian as GU
            before_rows = len(GU.rows())
        except Exception:                                 # noqa: BLE001
            GU = None
            before_rows = 0
        old_bytes = note_path.read_bytes() if note_path.is_file() else b""
        cards2 = _PmChecker()
        res2, _steps2 = _pm2_call("project_export_obsidian_hub",
                                  {"project": "Site"}, cards2)
        check("a second export asks its ONE card again",
              len(cards2.calls) == 1
              and cards2.calls[0][0] == "edit_vault_note", cards2.calls[:1])
        check("... and replaces the note",
              res2.get("ok") is True and res2.get("replaced") is True, res2)
        if GU is not None:
            import hashlib
            rows = GU.rows()
            check("... the File Guardian copied the old note BEFORE the write",
                  len(rows) == before_rows + 1
                  and str(rows[-1].get("path", "")).endswith("Site.md")
                  and rows[-1].get("before_sha256")
                  == hashlib.sha256(old_bytes).hexdigest(),
                  (len(rows), before_rows, rows[-1:]))
        else:
            skip("the File Guardian is not in this tree, so its copy was not proved")
    finally:
        if old_vault is None:
            os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
        else:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = old_vault
        _pm2_unuse(old_env)


def t_pm2_a_status_change_leaves_an_undo_receipt():
    """work_item_update_status: one project_event row and ONE receipt, and the
    receipt's Undo really puts the old status back (exactly once)."""
    import jarvis_receipts as R
    s, project, _other = _pm2_owner_store()
    item = s.add_work_item(project["id"], {"title": "Move me"})
    old_env = _pm2_use(s)
    try:
        before = {row["receipt_id"] for row in R.recent()}
        out = s.set_work_item_status(item["id"], "in_progress")
        check("a status change still moves the item", out["status"] == "in_progress")
        new = [row for row in R.recent() if row["receipt_id"] not in before]
        check("... and leaves exactly ONE receipt", len(new) == 1, new)
        rid = new[0]["receipt_id"] if new else ""
        check("... whose tool name is the status change itself",
              bool(new) and new[0].get("tool_name") == "work_item_status", new[:1])
        check("... and whose summary names the new state",
              bool(new) and "in_progress" in str(new[0].get("summary", "")), new[:1])
        if rid:
            status_rows = [row for row in R.recent()
                           if row.get("tool_name") == "work_item_status"]
            got = R.undo(rid)
            check("the receipt's Undo really puts the old status back",
                  got.get("ok") is True, got)
            rows = [row for row in P.get().work_items() if row["id"] == item["id"]]
            check("... in the store itself",
                  bool(rows) and rows[0]["status"] == "backlog", rows)
            check("... and the Undo itself leaves no second receipt",
                  len([row for row in R.recent()
                       if row.get("tool_name") == "work_item_status"])
                  == len(status_rows),
                  [row.get("summary") for row in R.recent()][:3])
            again = R.undo(rid)
            check("... and a second Undo refuses, applying nothing",
                  again.get("ok") is False, again)
        check("... the change ALSO left one project event, and the Undo its own",
              [e["kind"] for e in s.events()] == ["work_item_added",
                                                  "work_item_status",
                                                  "work_item_status"],
              [e["kind"] for e in s.events()])
    finally:
        _pm2_unuse(old_env)


def t_pm2_the_tools_are_registered_and_tiered():
    """The registry and the tiers: every one of the eight is a real tool with a
    real prepare/execute, in exactly one short-list home, offered by the
    shipped settings, mapped to an existing gate action, and the one new risk
    row is a local reversible write. No new card class and no new action."""
    AG = _pm2_agent()
    expect = {
        "project_create": "todo_add",
        "work_item_add": "todo_add",
        "work_item_update_status": "todo_add",
        "work_item_link_dependency": "todo_add",
        "project_checkpoint_reflect": "todo_add",
        "project_seed_plan": "change_own_config",
        "project_decompose_plan": "change_own_config",
        "project_export_obsidian_hub": "edit_vault_note",
    }
    check("all eight tools are in jarvis_agent.TOOLS",
          set(expect) <= set(AG.TOOLS), sorted(set(expect) - set(AG.TOOLS)))
    check("... and each carries a real prepare() and execute()",
          all(callable(AG.TOOLS[n].prepare) and callable(AG.TOOLS[n].execute)
              and getattr(AG.TOOLS[n].prepare, "__name__", "").startswith("_prepare_")
              for n in expect),
          {n: getattr(AG.TOOLS[n].prepare, "__name__", "") for n in expect})
    check("... exactly one home each in the short list's core/groups",
          all((1 if n in AG.CORE_TOOLS else 0)
              + sum(1 for _g, _w, members in AG.TOOL_GROUPS if n in members) == 1
              for n in expect),
          {n: [g for g, _w, members in AG.TOOL_GROUPS if n in members]
           for n in expect})
    import tomllib
    shipped = set(tomllib.loads((HERE / "rebuilt" / "jarvis-framework.toml")
                                .read_text(encoding="utf-8"))["tools"]["enabled"])
    check("the shipped settings file offers all eight", set(expect) <= shipped,
          sorted(set(expect) - shipped))
    tiers = _pm2_tiers()
    check("both carded actions ship their own 'ask' tier line, and the "
          "owner-direct one is the gate's own per-tool 'auto' literal (proved "
          "by the real gate check below)",
          tiers.get("change_own_config") == "ask"
          and tiers.get("edit_vault_note") == "ask"
          and "todo_add" not in tiers,
          {a: tiers.get(a) for a in set(expect.values())})
    check("the two proposal tools are in NEEDS_A_PERSON, so a loosened line "
          "cannot run them with nobody asked",
          {"project_seed_plan", "project_decompose_plan"} <= set(AG.NEEDS_A_PERSON))
    check("the five owner-direct writes are NOT a standing card",
          not (set(AG.PROJECT_OWNER_DIRECT_TOOLS) & set(AG.NEEDS_A_PERSON)))
    check("a plan tool's own result is not recorded as outside text",
          AG.PROJECT_TOOLS <= AG._NOT_READING)
    try:
        import jarvis_reach as REACH
        import jarvis_tool_profiles as PROFILES
        import jarvis_claims as CLAIMS
        check("every plan tool has a Reach-page name",
              set(expect) <= set(REACH.TOOL_NAMES),
              sorted(set(expect) - set(REACH.TOOL_NAMES)))
        check("... and a tool dossier",
              set(expect) <= set(PROFILES.PROFILES),
              sorted(set(expect) - set(PROFILES.PROFILES)))
        check("... and a claim classification (an action, never a read)",
              set(expect) <= set(CLAIMS.ACTING_TOOLS)
              and not (set(expect) & set(CLAIMS.READ_ONLY_TOOLS)),
              sorted(set(expect) - set(CLAIMS.ACTING_TOOLS)))
    except Exception as exc:                              # noqa: BLE001
        check("the Reach page, dossiers and claims are importable here",
              False, repr(exc))

    gate = _pm2_gate()
    if gate is None:
        skip("the real gate is not in this tree, so the registry rows were not run")
        return
    want = dict(expect)
    resolved = {name: gate.action_for_tool(name, {}) for name in want}
    check("every plan tool resolves to its action in the published gate",
          {name: resolved[name][0] for name in want} == want, resolved)
    check("... so no tool answers 'unclassified_tool'",
          all(resolved[name][1] and resolved[name][0] != "unclassified_tool"
              for name in want), resolved)
    gate.action_for_tool("todo_add", {})     # the gate's own per-tool tier warm
    verdict = gate.check("todo_add", {})
    check("the owner-direct action really ships 'auto', so a clean turn is cardless",
          verdict.tier == "auto" and verdict.allowed is True,
          (verdict.tier, verdict.allowed))
    risk = gate.risk_for("todo_add")
    check("... and the one new risk row says a local, reversible row",
          risk["classified"] is True and risk["reversible"] == "yes"
          and risk["reach"] == "local" and risk["swipe_ok"] is True, risk)
    check("... while both carded actions stay 'ask' in the shipped tiers",
          tiers.get("change_own_config") == "ask"
          and tiers.get("edit_vault_note") == "ask",
          (tiers.get("change_own_config"), tiers.get("edit_vault_note")))


def t_pm2_the_seeded_plan_is_a_real_next_item():
    """THE ACCEPTANCE TEST. On the owner-shaped store (two coding projects, no
    plan rows) plus a goal with steps and a work-list item that really exist,
    the answer before the import is the honest empty one; AFTER the import the
    answer comes from the plan rows in projects.db alone - a real item, not the
    empty answer - even when goals.db and the scheduler read nothing."""
    s, project, _other = _pm2_owner_store()
    old_env = _pm2_use(s)
    old_goals = sys.modules.get("jarvis_goals")
    old_sched = sys.modules.get("jarvis_schedule")
    try:
        before = Q.answer("what should I work on next?",
                          sched=_PmSched([]), now=_NOW)
        check("before the import, the owner-shaped store answers honestly empty",
              before is not None and before.intent == "project_next"
              and "Nothing is ready to work on right now" in str(before.reply),
              before and before.reply)
        check("... and the plan store really has no rows yet",
              s.plan_counts() == {}, s.plan_counts())

        sched, goals_file = _pm2_sources(s, project)
        _pm2_sched(sched)
        _pm2_goals(_PM2_GOALS, goals_file)
        yes = _PmChecker()
        res, _steps = _pm2_call("project_seed_plan", {}, yes)
        check("the import writes the owner's own rows after ONE card",
              res.get("ok") is True and res.get("wrote") is True
              and len(yes.calls) == 1, (res, yes.calls))
        check("... so the goal step and the work-list item now EXIST as plan rows",
              s.plan_counts()[project["id"]]["work_items"] == 4,
              s.plan_counts())

        # The sources are put back the way the owner's real PC has them (no
        # readable goal, no scheduler item): the answer must now come from the
        # plan rows the import wrote.
        _pm2_restore_module("jarvis_goals", old_goals)
        _pm2_restore_module("jarvis_schedule", old_sched)
        answered = Q.answer("what should I work on next?",
                            sched=_PmSched([]), now=_NOW)
        said = str(answered.reply) if answered is not None else ""
        check("after the import, 'what should I work on next?' answers from "
              "projects.db - a REAL plan item, not the empty answer",
              answered is not None and answered.intent == "project_next"
              and "Nothing is ready to work on right now" not in said
              and "Write the plan" in said, said[:400])
        plan_items = {row["title"]: row for row in s.work_items()}
        check("... the named item is a real work item row the store can act on",
              "Write the plan" in plan_items
              and plan_items["Write the plan"]["id"]
              in [row["id"] for row in s.ready_next()],
              plan_items.get("Write the plan"))
        check("... and it is the plan store's own ready count",
              s.plan_counts()[project["id"]]["ready"] >= 1,
              s.plan_counts())
        moved = s.set_work_item_status(plan_items["Write the plan"]["id"], "done")
        check("... and it can be moved like any other plan row",
              moved["status"] == "done")
    finally:
        _pm2_restore_module("jarvis_goals", old_goals)
        _pm2_restore_module("jarvis_schedule", old_sched)
        _pm2_unuse(old_env)


# ==========================================================================
#   PM3 (2026-11-20): the execution and brief bridges
# ==========================================================================
# The owner-approved PM3 spec (the architecture review's "PM3 - Execution
# Bridge", and this repository's docs/PROJECTS-DESIGN.md build notes): the
# plan store now meets the stores and surfaces that already exist -
#   * the read-only GitHub reader (`jarvis_github.py`) for a linked PR's own
#     state and CI, with NO write card;
#   * the durable task list (`jarvis_tasks.py`), whose job state updates the
#     linked work item - the link and its projection only, see the deferral
#     note on `t_pm3_the_task_link_updates_the_work_item_status`;
#   * the morning digest (`jarvis_arbiter.digest()`): due within 48h, the top
#     3 ready items, and in_progress items untouched for more than 7 days;
#   * the daily to-do list (`jarvis_schedule.status()`): a read-only copy of
#     every work item due today or earlier, with the same carry-over tags;
#   * the one-way Obsidian hub note (`project_export_obsidian_hub`), now
#     carrying the link state and the merged-PR offer.
# Nothing here runs anything: no dispatcher, no runner, no executor.
# Every check below was written BEFORE the bridge code and failed on the tree
# it was written against (the new names did not exist yet).

_PM3 = _TMP / "pm3"
_PM3.mkdir(exist_ok=True)
_PM3_N = [0]
#: The fixed moment the PM3 tests live at (a Friday, so "yesterday" and
#: "Friday (3d ago)" both have a word). Tests that need time to pass move the
#: store's own clock; nothing sleeps.
_PM3_NOW = time.mktime(time.strptime("2026-11-20 09:30:00", "%Y-%m-%d %H:%M:%S"))


def _pm3_day(offset_days: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(_PM3_NOW + offset_days * 86400))


def _pm3_store(*, start=None):
    """(store, bump, ticks): a fresh projects.db whose clock a test can move."""
    _PM3_N[0] += 1
    ticks = [float(_PM3_NOW if start is None else start)]

    def clock():
        ticks[0] += 1.0
        return ticks[0]

    def bump(seconds):
        ticks[0] += float(seconds)

    return P.Projects(_PM3 / f"projects-{_PM3_N[0]}.db", clock=clock), bump, ticks


def _pm3_project(store, name="Site", *, repo="darknight11ish/Epic-Jarvis"):
    project = store.create({"name": name, "kind": "coding"}, here=True)
    if repo:
        store.set_plan_fields(project["id"], {"linked_repo": repo})
    return store.get(project["id"])


def _pm3_tasks():
    """The REAL durable task list on a file of this suite's own."""
    import jarvis_tasks as T
    _PM3_N[0] += 1
    return T, T.Store(_PM3 / f"tasks-{_PM3_N[0]}.db")


def _pm3_github_on():
    """The real GitHub module, told to read with a made-up token."""
    import jarvis_github as GH
    old = GH._need_token
    GH._need_token = lambda: "pm3-test-token-not-logged"
    return GH, old


def _pm3_github_off(GH, old):
    GH._need_token = old


def _pm3_fake_github(*, merged=False, checks=None, fail=False):
    """(fetch, calls, state): a fake transport that answers GETs only.

    `state` is mutable, so a test moves the pull request on between reads the
    same way GitHub would. Nothing here can answer a write's response: the
    bridge never makes one."""
    calls = []
    state = {
        "pr": {"number": 1402, "title": "The plan store's bridges",
               "state": "closed" if merged else "open", "merged": bool(merged),
               "head": {"sha": "a" * 40}, "base": {"ref": "main"}},
        "checks": checks if checks is not None else [
            {"name": "backend", "status": "completed", "conclusion": "success"}],
    }

    def fetch(method, url, *, headers=None, body=None, timeout=None):
        calls.append((method, url, body))
        if fail:
            raise OSError("no network in this test")
        if "/check-runs" in url:
            return 200, json.dumps({"check_runs": state["checks"]}), {}
        if "/pulls/" in url:
            return 200, json.dumps(state["pr"]), {}
        return 404, json.dumps({"message": "Not Found"}), {}
    return fetch, calls, state


def t_pm3_a_due_work_item_appears_in_the_daily_list():
    """BRIDGE 4. A work item due today or earlier appears in the Reminders ->
    Daily to-do list with the SAME carry-over tag a to-do row gets ("from
    yesterday"), read-only: no schedule.db row is created, repeated reads are
    identical, and an item with no date, a future date or a closed status
    never appears. The other three work items in the fixture prove the
    selection is the store's own dates and never an invented one."""
    import sqlite3
    import jarvis_schedule as S
    s, _bump, _ticks = _pm3_store()
    project = _pm3_project(s)
    yesterday = s.add_work_item(project["id"], {"title": "Post the letter",
                                                "due_date": _pm3_day(-1)})
    today = s.add_work_item(project["id"], {"title": "File the report",
                                            "due_date": _pm3_day(0)})
    future = s.add_work_item(project["id"], {"title": "Next month's plan",
                                             "due_date": _pm3_day(30)})
    undated = s.add_work_item(project["id"], {"title": "No date at all"})
    done = s.add_work_item(project["id"], {"title": "Already done",
                                           "due_date": _pm3_day(-2),
                                           "status": "done"})
    sched = S.Scheduler(_PM3 / f"daily-{_PM3_N[0]}.db", clock=lambda: _PM3_NOW)
    # The schedule's read door resolves the plan store through jarvis_projects'
    # own singleton, the way the running backend does - so point it at THIS
    # test's store, never the owner's real one.
    old_env = _pm2_use(s)
    try:
        shown = sched.status()
    finally:
        _pm2_unuse(old_env)
    rows = {row["id"]: row for row in shown.get("todo") or []}
    expected = P.daily_row_id(project["id"], yesterday["id"])
    check("a work item due yesterday appears in the daily to-do list",
          expected in rows, sorted(rows))
    if expected in rows:
        row = rows[expected]
        check("... as a READ-ONLY projected row, not a scheduler row",
              row.get("read_only") is True and row.get("source") == "project"
              and row.get("kind") == "todo" and row.get("state") == "active",
              {k: row.get(k) for k in ("read_only", "source", "kind", "state")})
        check("... carrying the SAME carry-over tag a to-do row gets",
              row.get("carry") == "from yesterday", row.get("carry"))
        check("... and naming the project and the work item it came from",
              row.get("project") == "Site"
              and row.get("work_item") == yesterday["id"], row)
        check("... with the item's own due date, never an invented one",
              row.get("due_date") == _pm3_day(-1), row.get("due_date"))
    today_id = P.daily_row_id(project["id"], today["id"])
    check("an item due today is on today's list too",
          today_id in rows and not rows[today_id].get("carry"), rows.get(today_id))
    check("a future item is NOT on the daily list",
          P.daily_row_id(project["id"], future["id"]) not in rows)
    check("an item with no date is never invented onto the list",
          P.daily_row_id(project["id"], undated["id"]) not in rows)
    check("a DONE item is not carried over",
          P.daily_row_id(project["id"], done["id"]) not in rows)
    check("the read says the projection is there (an additive marker)",
          shown.get("project_todos") is True, shown.get("project_todos"))
    # Read-only and no duplicate rows: a second read is identical, and the one
    # scheduler still holds no to-do row of its own.
    old_env = _pm2_use(s)
    try:
        again = sched.status()
    finally:
        _pm2_unuse(old_env)
    ids = [row["id"] for row in again.get("todo") or []]
    check("a second read adds nothing (no duplicate rows, no writes)",
          ids == [row["id"] for row in shown.get("todo") or []]
          and len(ids) == len(set(ids)), ids)
    check("... the one scheduler is untouched by the projection",
          sched.todos() == [])
    with sqlite3.connect(str(sched.path)) as c:
        n = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    check("... and not one schedule.db row was written", n == 0, n)
    # The route an app actually reads is the same status(): prove it.
    old_get = S.get
    S.get = lambda: sched
    old_env = _pm2_use(s)
    try:
        code, out = S.handle_get()
    finally:
        S.get = old_get
        _pm2_unuse(old_env)
    check("GET /api/schedule's own answer carries the projected item",
          code == 200 and any(row["id"] == expected for row in out.get("todo") or []),
          code)
    # The item's own date is exactly what the owner gave: no bridge wrote one.
    stored = {row["id"]: row for row in s.work_items()}
    check("neither the projection nor the read invented a due date",
          stored[yesterday["id"]]["due_date"] == _pm3_day(-1)
          and stored[undated["id"]]["due_date"] is None
          and stored[future["id"]]["due_date"] == _pm3_day(30),
          {k: v["due_date"] for k, v in stored.items()})


def t_pm3_the_digest_lists_top_three_ready_and_stalled_items():
    """BRIDGE 3. jarvis_arbiter.digest() surfaces, without writing anything
    and without a model: (a) work items due within 48 hours, (b) the top 3
    ready items ACROSS active projects, and (c) in_progress items untouched
    for more than seven days. The digest's own existing keys keep their
    meaning - the project brief is one added key."""
    import jarvis_arbiter as AB
    s, bump, ticks = _pm3_store()
    site = _pm3_project(s, "Site")
    tool = _pm3_project(s, "Tool", repo=None)
    made = []
    for n, (project, title) in enumerate([
            (site, "First"), (tool, "Second"), (site, "Third"),
            (tool, "Fourth"), (site, "Fifth")]):
        made.append(s.add_work_item(project["id"], {"title": title,
                                                    "status": "ready",
                                                    "priority": n}))
    stalled = s.add_work_item(site["id"], {"title": "Stuck for a week"})
    s.set_work_item_status(stalled["id"], "in_progress")
    due_tomorrow = s.add_work_item(site["id"], {"title": "Due tomorrow",
                                                "due_date": _pm3_day(1)})
    far_away = s.add_work_item(site["id"], {"title": "Due next month",
                                            "due_date": _pm3_day(30)})
    bump(8 * 86400)               # eight days later: `stalled` is over 7d old
    # ... while this one was started AFTER the clock moved, so it is not stale.
    started = s.add_work_item(site["id"], {"title": "Started today"})
    s.set_work_item_status(started["id"], "in_progress")
    old_env = _pm2_use(s)
    try:
        before = s.path.read_bytes()
        counts = s.plan_counts()
        out = AB.digest(now=ticks[0])
    finally:
        _pm2_unuse(old_env)
    brief = out.get("projects") or {}
    ready = [row["title"] for row in brief.get("ready") or []]
    check("the digest lists the TOP 3 ready items across active projects",
          ready == ["First", "Second", "Third"], ready)
    check("... and no more than three, so a spoken read-out stays short",
          len(ready) <= 3, len(ready))
    stalled_titles = [row["title"] for row in brief.get("stalled") or []]
    check("the digest lists in_progress items untouched for more than 7 days",
          stalled_titles == ["Stuck for a week"], stalled_titles)
    check("... and does NOT call an item started today stalled",
          "Started today" not in stalled_titles, stalled_titles)
    due = [row["title"] for row in brief.get("due_48h") or []]
    check("the digest lists work items due within 48 hours",
          "Due tomorrow" in due and "Due next month" not in due, due)
    check("the digest's own keys did not change meaning",
          isinstance(out.get("items"), list) and "note" in out
          and "budget" in out and out.get("count") is not None, sorted(out))
    check("a digest read writes nothing: same bytes, same plan counts",
          s.path.read_bytes() == before and s.plan_counts() == counts)
    check("the digest says which day it read",
          str(brief.get("read") or "") == time.strftime(
              "%Y-%m-%d", time.localtime(ticks[0])), brief.get("read"))
    # The due list only ever carries dates the store already had.
    check("no date in the brief was invented",
          {row["due_date"] for row in brief.get("due_48h") or []}
          <= {_pm3_day(1)}, brief.get("due_48h"))


def t_pm3_the_task_link_updates_the_work_item_status():
    """BRIDGE 2, the link and its projection. A work item linked to a REAL
    durable job in jarvis_tasks.py follows that job's own state through the
    EXISTING status path (one project_event and one receipt per change):
    queued/running -> in_progress, waiting_approval -> waiting_approval,
    succeeded -> in_review. A failed or cancelled job is REPORTED, never
    given a made-up status, and a done item is never pulled back.

    WHAT IS DELIBERATELY NOT HERE (the owner's "no half-built runner" rule):
    the Run Step DISPATCH that would create such a job is deferred - see the
    decisions fragment and docs/ARCHITECTURE.md section 8. This test drives
    the link directly, because the link is the half that can be built
    honestly today."""
    import jarvis_tasks as T
    import jarvis_receipts as R
    s, _bump, _ticks = _pm3_store()
    project = _pm3_project(s)
    item = s.add_work_item(project["id"], {"title": "Write the plan"})
    T_store, tasks = _pm3_tasks()
    job = T.JobList(store=tasks).enqueue(
        "Write the plan", "the plan's first step",
        [{"tool": "calculator", "args": {"expression": "1 + 1"},
          "why": "a step that does nothing on this PC"}])
    linked = s.link_task(item["id"], job.id, task_store=tasks)
    check("a work item can be linked to a REAL durable job",
          linked.get("linked_task_id") == job.id, linked.get("linked_task_id"))
    check("... and the link is in the append-only log",
          "work_item_link" in [ev["kind"] for ev in s.events()],
          [ev["kind"] for ev in s.events()])
    receipts = lambda: [row for row in R.recent()
                        if row.get("tool_name") == "work_item_status"]
    before = len(receipts())

    def current():
        return [row for row in s.work_items() if row["id"] == item["id"]][0]

    out = s.sync_task_status(task_store=tasks)
    check("a QUEUED jarvis_tasks job moves the linked item to in_progress",
          current()["status"] == "in_progress" and out["changed"],
          (current()["status"], out))
    check("... through the existing status path, so ONE receipt exists",
          len(receipts()) == before + 1, len(receipts()) - before)
    done_now = tasks.get_task(job.id)
    done_now.status = "running"
    tasks.save(done_now)
    n = len(receipts())
    again = s.sync_task_status(task_store=tasks)
    check("a RUNNING job changes nothing further (no second receipt)",
          current()["status"] == "in_progress" and len(receipts()) == n
          and s.sync_task_status(task_store=tasks)["changed"] == [], again)
    done_now = tasks.get_task(job.id)
    done_now.status = "waiting_approval"
    tasks.save(done_now)
    s.sync_task_status(task_store=tasks)
    check("a job waiting on a card shows as waiting_approval",
          current()["status"] == "waiting_approval", current()["status"])
    done_now = tasks.get_task(job.id)
    done_now.status = "succeeded"
    tasks.save(done_now)
    s.sync_task_status(task_store=tasks)
    check("a SUCCEEDED job moves the item to in_review, not to done",
          current()["status"] == "in_review", current()["status"])
    s.set_work_item_status(item["id"], "done")
    done_now = tasks.get_task(job.id)
    done_now.status = "running"
    tasks.save(done_now)
    s.sync_task_status(task_store=tasks)
    check("a DONE work item is never pulled back by the job's state",
          current()["status"] == "done", current()["status"])
    locked = s.add_work_item(project["id"], {"title": "A failed job"})
    failed = T.JobList(store=tasks).enqueue(
        "A failed job", "",
        [{"tool": "calculator", "args": {"expression": "2 + 2"}, "why": "a step"}])
    s.link_task(locked["id"], failed.id, task_store=tasks)
    bad = tasks.get_task(failed.id)
    bad.status = "failed"
    tasks.save(bad)
    out = s.sync_task_status(task_store=tasks)
    rows = [row for row in s.work_items() if row["id"] == locked["id"]]
    check("a FAILED job invents no status: the item is left where it was and "
          "the answer says why",
          rows[0]["status"] == "backlog"
          and any(row.get("item") == locked["id"] and "failed" in str(row.get("why"))
                  for row in out["skipped"]), (rows[0]["status"], out["skipped"]))
    before_links = len(s.work_items())
    said = raises(lambda: s.link_task(locked["id"], "f" * 32, task_store=tasks),
                  ValueError)
    check("linking a job id that does not exist is refused in words",
          "no job" in said.lower(), said)
    check("... and nothing was written for it", len(s.work_items()) == before_links)
    check("no bridge step invented a due date",
          all(row["due_date"] is None for row in s.work_items()))


def t_pm3_a_pr_status_syncs_with_no_write_card():
    """BRIDGE 1. The linked PR's own state and CI are READ from jarvis_github.py
    and written onto the work item's projection columns - no gate card, no
    GitHub write (every request is a GET), and the work item's STATUS is never
    changed by the sync. A merged PR becomes an OFFER, never an automatic
    'done': the offer is listed, and the move stays the owner's own status
    path with its normal receipt and Undo."""
    GH, old_token = _pm3_github_on()
    try:
        s, _bump, _ticks = _pm3_store()
        project = _pm3_project(s)
        item = s.add_work_item(project["id"], {"title": "Ship the bridge",
                                               "status": "in_progress"})
        s.link_pr(item["id"], 1402)
        fetch, calls, state = _pm3_fake_github(checks=[
            {"name": "backend", "status": "completed", "conclusion": "failure"}])
        cards = _PmChecker()

        def gate_if_asked(action, detail, prompt):
            cards(action, detail, prompt)
            raise AssertionError("the read-only PR sync raised a gate card")

        real_gate = P._gate
        P._gate = gate_if_asked
        try:
            out = s.sync_prs(fetch=fetch)
        finally:
            P._gate = real_gate
        row = [r for r in s.work_items() if r["id"] == item["id"]][0]
        check("a linked PR's own state syncs onto the work item",
              row.get("linked_pr_number") == 1402
              and row.get("linked_pr_state") == "open", row.get("linked_pr_state"))
        check("... and its CI status, read from the checks on its head commit",
              row.get("linked_ci_status") == "failed", row.get("linked_ci_status"))
        check("the sync raises NO write card", cards.calls == [], cards.calls)
        check("... and sends no write: every GitHub request was a GET",
              bool(calls) and all(method == "GET" for method, _url, _body in calls),
              [(method, url) for method, url, _body in calls])
        check("... and never changes the item's own status",
              row["status"] == "in_progress" and not out.get("offers"), row)
        events = len(s.events())
        s.sync_prs(fetch=fetch)
        check("a second sync of the same state writes no second event",
              len(s.events()) == events, len(s.events()) - events)
        # GitHub marks the pull request merged: that is an OFFER.
        state["pr"]["state"] = "closed"
        state["pr"]["merged"] = True
        state["checks"] = [{"name": "backend", "status": "completed",
                            "conclusion": "success"}]
        out = s.sync_prs(fetch=fetch)
        row = [r for r in s.work_items() if r["id"] == item["id"]][0]
        check("a MERGED PR is projected as merged, with green checks",
              row.get("linked_pr_state") == "merged"
              and row.get("linked_ci_status") == "green",
              (row.get("linked_pr_state"), row.get("linked_ci_status")))
        check("... and it OFFERS the move to done, without doing it",
              row["status"] == "in_progress"
              and [o["item"] for o in out.get("offers") or []] == [item["id"]],
              (row["status"], out.get("offers")))
        offers = s.pr_merged_offers()
        check("the offer is a read the apps and the brief can list",
              [o["item"] for o in offers] == [item["id"]]
              and offers[0].get("pr") == 1402, offers)
        n = len([ev for ev in s.events() if ev["kind"] == "pr_merged_offer"])
        s.sync_prs(fetch=fetch)
        check("... and the same merged PR offers only once",
              len([ev for ev in s.events()
                   if ev["kind"] == "pr_merged_offer"]) == n == 1, n)
        # A failing transport is a plain sentence and changes nothing.
        before = (row.get("linked_pr_state"), len(s.events()))
        bad_fetch, _calls, _state = _pm3_fake_github(fail=True)
        bad = s.sync_prs(fetch=bad_fetch)
        after_row = [r for r in s.work_items() if r["id"] == item["id"]][0]
        check("a GitHub that cannot answer is SAID, and the projection stays",
              bad.get("errors") and (after_row.get("linked_pr_state"),
                                     len(s.events())) == before,
              (bad.get("errors"), after_row.get("linked_pr_state")))
        # The production door is the project store's own POST route: the same
        # read through the same store, and the same no-card rule.
        code, posted = P.handle_post(
            f"/api/projects/{project['id']}/sync", {}, store=s, fetch=fetch)
        row = [r for r in s.work_items() if r["id"] == item["id"]][0]
        check("GET.. POST /api/projects/<id>/sync is the app's door to the sync",
              code == 200 and posted.get("ok") is True
              and row.get("linked_pr_state") == "merged", (code, posted))
        check("the bridge route is in the project store's route table",
              P.parse_route(f"/api/projects/{project['id']}/sync") ==
              ("sync", project["id"])
              and P.parse_route(f"/api/projects/{project['id']}/sync/more") is None
              and P.parse_route(f"/api/projects/{project['id']}/run") is None)
    finally:
        _pm3_github_off(GH, old_token)


def t_pm3_undo_restores_a_reverted_work_status():
    """BRIDGE acceptance. Moving a merged PR's work item to done - the offer's
    own move, made through the EXISTING status path - leaves one jarvis_undo
    receipt, and that Undo really puts the old status back, exactly once."""
    import jarvis_receipts as R
    s, _bump, _ticks = _pm3_store()
    project = _pm3_project(s)
    item = s.add_work_item(project["id"], {"title": "Merged and ready",
                                           "status": "in_progress"})
    s.link_pr(item["id"], 77)
    # The receipt's Undo runs through jarvis_projects' own singleton (the same
    # store the running backend uses), so point it at this test's store.
    old_env = _pm2_use(s)
    try:
        before = {row["receipt_id"] for row in R.recent()}
        moved = s.set_work_item_status(item["id"], "done")
        new = [row for row in R.recent() if row["receipt_id"] not in before]
        check("the offer's move uses the existing status path and makes a receipt",
              moved["status"] == "done" and len(new) == 1, (moved["status"], new))
    finally:
        _pm2_unuse(old_env)
    rid = new[0]["receipt_id"] if new else ""
    if rid:
        old_env = _pm2_use(s)
        try:
            got = R.undo(rid)
        finally:
            _pm2_unuse(old_env)
        row = [r for r in s.work_items() if r["id"] == item["id"]][0]
        check("jarvis_undo restores the work item's previous status",
              got.get("ok") is True and row["status"] == "in_progress",
              (got, row["status"]))
        check("... and a second Undo refuses, applying nothing",
              R.undo(rid).get("ok") is False)
        check("... the events record both moves and invent no fourth one",
              [ev["detail"].get("to") for ev in s.events()
               if ev["kind"] == "work_item_status"] == ["done", "in_progress"],
              [ev["detail"] for ev in s.events()
               if ev["kind"] == "work_item_status"])


def t_pm3_the_ready_readout_is_capped_at_three():
    """BRIDGE acceptance, the surface rule: "what should I work on next?" - the
    one deterministic answer the phone and the voice path read - names at most
    THREE ready items, however many are ready, and the brief's own ready list
    is capped the same way so the two can never disagree about how long the
    answer is."""
    s, _bump, _ticks = _pm3_store()
    project = _pm3_project(s)
    for n, title in enumerate(["One", "Two", "Three", "Four", "Five"]):
        s.add_work_item(project["id"], {"title": title, "status": "ready",
                                        "priority": n})
    old_env = _pm2_use(s)
    try:
        answer = Q.answer("what should I work on next?", sched=_PmSched([]),
                          now=_PM3_NOW)
        brief = s.morning_brief(now=_PM3_NOW)
    finally:
        _pm2_unuse(old_env)
    said = str(answer.reply) if answer is not None else ""
    shown = [title for title in ("One", "Two", "Three", "Four", "Five")
             if f'"{title}"' in said]
    check("the phone/voice ready answer names at most three items",
          len(shown) == 3, (shown, said[:400]))
    check("... and names the first three by priority, not a random three",
          shown == ["One", "Two", "Three"], shown)
    check("... because the quick path's own cap is three",
          Q._MAX_NEXT_ITEMS == 3, Q._MAX_NEXT_ITEMS)
    check("the morning brief's ready list is capped the same way",
          len(brief.get("ready") or []) == 3,
          [row["title"] for row in brief.get("ready") or []])


def t_pm3_taint_asks_and_no_date_is_ever_invented():
    """The two rules the bridges must not weaken. (1) TAINT: a turn shaped by
    outside text forces EVERY owner-direct project write to ONE
    change_own_config card, and a no writes nothing - the five PM2 writes, on
    the tree that now carries the bridges. (2) NO INVENTED DATE: the bridges
    add no tool, take no date, and the rows they move keep exactly the dates
    the owner gave (often none)."""
    AG = _pm2_agent()
    s, project, _other = _pm2_owner_store()
    old_env = _pm2_use(s)
    try:
        s.add_work_item(project["id"], {"title": "First"})
        s.add_work_item(project["id"], {"title": "Second"})
        cases = [
            ("work_item_add", {"project": "Site", "title": "Tainted add"}),
            ("work_item_update_status", {"item": "First", "status": "in_progress"}),
            ("work_item_link_dependency", {"from": "First", "to": "Second",
                                           "kind": "blocks"}),
            ("project_checkpoint_reflect", {"project": "Site", "text": "a lesson"}),
            ("project_create", {"name": "Tainted project", "kind": "life"}),
        ]
        before = (s.plan_counts(), len(s.events()), len(s.list()))
        for tool, args in cases:
            no = _PmChecker(allowed=False, outcome="denied")
            res, _steps = _pm2_call(tool, args, no,
                                    watch=AG._TurnWatch(tainted=True))
            check(f"an outside-text turn forces {tool} to ONE ask card",
                  len(no.calls) == 1 and no.calls[0][0] == "change_own_config",
                  (tool, no.calls))
            check(f"... and {tool} writes nothing when the card is refused",
                  res.get("ok") is False, res)
        check("... so the whole store is unchanged after the five noes",
              (s.plan_counts(), len(s.events()), len(s.list())) == before,
              (s.plan_counts(), before))
        check("the bridges add NO model tool: the plan tools are still the eight",
              AG.PROJECT_TOOLS == {
                  "project_create", "work_item_add", "work_item_update_status",
                  "work_item_link_dependency", "project_checkpoint_reflect",
                  "project_seed_plan", "project_decompose_plan",
                  "project_export_obsidian_hub"}, sorted(AG.PROJECT_TOOLS))
        check("... and no plan tool accepts a due or target date",
              all("due_date" not in ((AG.TOOLS[name].parameters or {}).get("properties") or {})
                  and "target_date" not in ((AG.TOOLS[name].parameters or {})
                                            .get("properties") or {})
                  for name in AG.PROJECT_TOOLS),
              {name: sorted(((AG.TOOLS[name].parameters or {}).get("properties") or {}))
               for name in AG.PROJECT_TOOLS})
        # NO DATE INVENTED: the owner gave one date; every bridge keeps it and
        # leaves every other row undated.
        dated = s.add_work_item(project["id"], {"title": "Dated by the owner",
                                                "due_date": _pm3_day(1)})
        undated = s.add_work_item(project["id"], {"title": "Undated by design"})
        s.link_pr(undated["id"], 1402)
        fetch, _calls, _state = _pm3_fake_github(merged=True)
        s.sync_prs(fetch=fetch)
        T, tasks = _pm3_tasks()
        job = T.JobList(store=tasks).enqueue(
            "Undated by design", "",
            [{"tool": "calculator", "args": {"expression": "1"}, "why": "a step"}])
        s.link_task(undated["id"], job.id, task_store=tasks)
        s.sync_task_status(task_store=tasks)
        rows = {row["id"]: row for row in s.work_items()}
        check("the owner's one date is exactly what every bridge keeps",
              rows[dated["id"]]["due_date"] == _pm3_day(1), rows[dated["id"]])
        check("no bridge ever adds a date to an undated item",
              rows[undated["id"]]["due_date"] is None, rows[undated["id"]])
        brief = s.morning_brief(now=_PM3_NOW)
        check("the brief lists only dates the store already holds",
              {row["due_date"] for row in brief["due_48h"]}
              <= {_pm3_day(1)}, brief["due_48h"])
        check("... and its due list never gains a date the owner did not give",
              all(row["due_date"] == _pm3_day(1)
                  for row in brief["due_48h"]), brief["due_48h"])
        check("the daily projection never invents a date either",
              all(row["due_date"] <= _pm3_day(0)
                  for row in s.daily_projection(now=_PM3_NOW)),
              [row["due_date"] for row in s.daily_projection(now=_PM3_NOW)])
    finally:
        _pm2_unuse(old_env)


def t_pm3_the_hub_export_stays_one_way_and_carries_the_bridge():
    """BRIDGE 5. The hub note is refreshed FROM the store on every export and
    never read back: a hand edit is replaced, not imported; it carries the
    link state (repository, PR state/CI, executor) and the merged-PR offer.
    Still ONE edit_vault_note card and one File Guardian copy per export."""
    GH, old_token = _pm3_github_on()
    s, _bump, _ticks = _pm3_store()
    project = _pm3_project(s, "Bridge")
    item = s.add_work_item(project["id"], {"title": "Ship the bridge",
                                           "status": "in_progress",
                                           "executor": "jarvis_local"})
    s.link_pr(item["id"], 1402)
    fetch, _calls, _state = _pm3_fake_github(merged=True)
    s.sync_prs(fetch=fetch)
    old_env = _pm2_use(s)
    old_vault = os.environ.get("JARVIS_OBSIDIAN_VAULT")
    os.environ["JARVIS_OBSIDIAN_VAULT"] = str(_PM2_VAULT)
    try:
        events_before = len(s.events())
        counts_before = s.plan_counts()
        cards = _PmChecker()
        res, _steps = _pm2_call("project_export_obsidian_hub",
                                {"project": "Bridge"}, cards)
        note_path = _PM2_VAULT / "Projects" / "Bridge.md"
        check("the export raises exactly ONE notes-editor card",
              len(cards.calls) == 1
              and cards.calls[0][0] == "edit_vault_note", cards.calls[:1])
        text = note_path.read_text(encoding="utf-8") if note_path.is_file() else ""
        check("the hub note says it is a one-way copy", P.HUB_NOTE_WORDS in text,
              text[:200])
        check("... carries the linked repository and PR state",
              "darknight11ish/Epic-Jarvis" in text and "1402" in text
              and "merged" in text, text[:900])
        check("... carries the executor that would run it",
              "jarvis_local" in text, text[:900])
        check("... and lists the merged PR's offer to move it to done",
              "Ship the bridge" in text and "offer" in text.lower(), text[:900])
        check("... while the store itself is NOT changed by an export",
              s.plan_counts() == counts_before
              and len(s.events()) == events_before)
        # One-way, never read back: a hand edit is replaced on the next export.
        note_path.write_text("# Hand edited by the owner\n", encoding="utf-8")
        cards2 = _PmChecker()
        res2, _steps2 = _pm2_call("project_export_obsidian_hub",
                                  {"project": "Bridge"}, cards2)
        text2 = note_path.read_text(encoding="utf-8")
        check("a second export asks its ONE card again and REPLACES the note",
              len(cards2.calls) == 1 and res2.get("replaced") is True
              and "Hand edited" not in text2, (cards2.calls[:1], res2.get("state")))
        check("... and the hand edit was never read back into the store",
              s.plan_counts() == counts_before
              and len(s.events()) == events_before, s.plan_counts())
        try:
            import jarvis_file_guardian as GU
            rows = GU.rows()
            check("... with a File Guardian copy taken of the replaced note",
                  bool(rows) and str(rows[-1].get("path", "")).endswith("Bridge.md"),
                  rows[-1:])
        except Exception:                                 # noqa: BLE001
            skip("the File Guardian is not in this tree, so its copy was not proved")
    finally:
        if old_vault is None:
            os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
        else:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = old_vault
        _pm2_unuse(old_env)
        _pm3_github_off(GH, old_token)


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn) and name != "t_no_network_no_model" \
                    and name != "t_audit_never_carries_words_or_numbers":
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
        for fn in (t_audit_never_carries_words_or_numbers, t_no_network_no_model):
            print(f"--- {fn.__name__} ---")
            fn()
    finally:
        socket.socket.connect = _real_connect
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
