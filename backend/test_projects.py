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
                "jarvis_documents.py", "jarvis_sensitive.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-projects-"))
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
