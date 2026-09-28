"""test_projects.py - Projects, build steps 1 and 2 (jarvis_projects.py,
projects.patch, docs/JARVIS-API.md section 61, docs/PROJECTS-DESIGN.md).

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
  - the routes, install() and the patch on the stack of earlier patches;
  - the audit log never carries a name, a note or a number.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
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


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


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
          == ("result_delete", pid, bid, rid))
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
        return check("SKIP - git is not installed", True)
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


def t_both_apps_read_the_current_contract():
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
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
