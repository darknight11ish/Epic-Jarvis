#!/usr/bin/env python3
"""Writes the Projects contract file for both apps, and checks it.

    python3 tools/gen_projects_cases.py            # write both copies
    python3 tools/gen_projects_cases.py --check    # compare only

What the Projects routes really answer (backend/jarvis_projects.py,
projects.patch; docs/JARVIS-API.md section 88), in named situations - made
by the real code, nothing written by hand:

    jarvis-desktop/tests/fixtures/projects-cases.json
    jarvis-client/app/src/test/resources/contract/projects-cases.json

(byte-identical). The desktop's Rust and JavaScript tests and the phone's
ProjectsTest build against it.

It also carries the two things both apps must agree on that the backend
does not send:

  * `words` - the screens' own sentences (button names, the "are you
    sure?" questions, the private label). Both apps' tests check their
    copy against this list, word for word, so the two cannot drift.
  * `numbers` and `scales` - how a number is written ("72.5 kg", "$200",
    "5") and where the chart's top and bottom are. `numbers` comes from
    the backend's own `_with_unit`; `scales` from `chart_scale()` below,
    the one reference both apps' chart code is tested against.

The ids are counted (not random) and the clock is fixed, so the file only
changes when the backend's answer does. The folder is a made-up Windows
path, accepted here without looking at the disk.

APPS (docs/APPS-IN-PROJECTS-DESIGN.md, JARVIS-API section 92). The file also
carries what a project that is a Jarvis-built app answers - the `app` object,
its tasks, a task's whole change, the merge card, every refusal - from a REAL
run of jarvis_apps.py against real git in a temporary settings folder. git's
dates, the author, the task ids and the clock are fixed, so the commit
hashes in it do not change from run to run. Needs git installed (the same as
the app workspace's own tests). `app_words` holds the sentences both apps
must say the same way and the PC sends (how a merge ended), kept apart from
`words` on purpose: `words` is compared key for key with each app's own list.
"""
import json
import os
import sys
import shutil
import tempfile
import types
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_CONF = Path(tempfile.mkdtemp(prefix="jarvis-projects-cases-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CONF)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _CONF
fw.LOG_DIR = _CONF
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: None
fw.action_tier = lambda action: "ask"
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_app_workspace as W  # noqa: E402
import jarvis_apps as A  # noqa: E402
import jarvis_forecast as F  # noqa: E402
import jarvis_goals as G  # noqa: E402
import jarvis_projects as P  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "projects-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "projects-cases.json")
COPIES = (DESKTOP, PHONE)

AT = 1790000000.0
DAY = 86400.0
FOLDER = "C:\\Users\\owner\\Code\\jarvis-desktop"

#: The screens' own words, the same in both apps (projects.js, Projects.kt).
#: `{name}` is filled in by the app.
WORDS = {
    "title": "Projects",
    "under": ("One place for each thing you are working on - an app, or a goal like a half "
              "marathon: how Jarvis should help, your notes, and numbers you track. Kept on "
              "your PC."),
    "new": "New project",
    "name": "Name",
    "kind_life": "Life - numbers you track",
    "kind_coding": "Coding - a folder on your PC",
    "create": "Create",
    "coding_on_pc": "A coding project's folder is chosen on your PC. Make coding projects there.",
    "set_on_pc": "Set on your PC",
    "instructions": "How Jarvis should work on this",
    "instructions_under": "In your own words. Saved for later: Jarvis does not read this in chats yet.",
    "notes": "Project notes",
    "notes_under": "Short lines to keep in mind for this project, one per line.",
    "save": "Save",
    "folder": "Folder",
    "folder_none": "No folder yet.",
    "folder_choose": "Choose a folder…",
    "folder_clear": "Clear",
    "folder_under": ("Only a folder on \"Folders Jarvis may look in\" (Settings), or one inside "
                     "it."),
    "shareable": "Shareable",
    "shareable_under": ("Off by default: nothing from this project is shared. Turning it on "
                        "asks you with an approval card first; turning it off is instant."),
    "work_list": "Work list",
    "work_list_none": "No work list.",
    "work_list_under": "A named list in Coming up. Add to it there, or say \"add ... to the {name}\".",
    "benchmarks": "Benchmarks",
    "benchmarks_empty": "No benchmarks yet. Add one to track a number over time.",
    "add_benchmark": "Add a benchmark",
    "bench_name": "What you measure",
    "bench_unit": "Unit (optional)",
    "bench_better": "Better is",
    "better_higher": "Higher",
    "better_lower": "Lower",
    "better_either": "Don't say",
    "bench_target": "Target (optional)",
    "add": "Add",
    "log": "Log",
    "log_value": "A number",
    "private_label": "private - not read aloud",
    "mark_private": "Mark private",
    "remove_mark": "Remove the private mark",
    "remove_mark_card": ("Jarvis marked this itself. Removing the mark asks you with an approval "
                         "card first, because afterwards its numbers may be read aloud."),
    "remove_mark_yours": "You marked this. Removing your mark is instant.",
    "waiting_card": "Waiting for your yes on the approval card.",
    "chart_empty": "No numbers yet - log the first one.",
    "chart_target": "Target",
    "chart_summary": "{count} numbers. Latest: {latest}.",
    "latest": "Latest",
    "remove_number": "Remove this number",
    "delete_project": "Delete project",
    "delete_project_q": ("Delete the project \"{name}\"? Its benchmarks and every number logged "
                         "go with it. This cannot be undone."),
    "delete_bench": "Delete benchmark",
    "delete_bench_q": ("Delete the benchmark \"{name}\" and every number logged for it? This "
                       "cannot be undone."),
    "delete_yes": "Delete",
    "delete_no": "Keep it",
    "command_on_pc": "A benchmark's command is written and changed on your PC.",
    "missing": "Your PC's Jarvis does not have Projects yet - run apply-patches.ps1 on the PC.",
    "stale": "The connection to Jarvis is catching up, so nothing can be sent until it does.",
    "back": "All projects",
    "open": "Open",
    "life": "Life",
    "coding": "Coding",
}


def chart_scale(values, target=None):
    """Where the chart's bottom and top are: every value and the target fit,
    with a tenth of the range spare above and below. One value (or all the
    same) gets one unit of room each way - or a tenth of its size, when that
    is bigger. [lo, hi], lo < hi always. Both apps implement exactly this."""
    pool = [float(v) for v in values]
    if target is not None:
        pool.append(float(target))
    if not pool:
        return [0.0, 1.0]
    lo, hi = min(pool), max(pool)
    if hi - lo < 1e-9:
        room = max(1.0, abs(lo) * 0.1)
        return [lo - room, hi + room]
    pad = (hi - lo) * 0.1
    return [lo - pad, hi + pad]


class _Ids:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"{self.n:032x}"


def _store():
    P._reset_for_tests()
    A._reset_for_tests()
    P._new_id = _Ids()
    P.check_folder = lambda path, allowed=None: str(path)
    path = _CONF / "projects.db"
    if path.exists():
        path.unlink()
    return P.Projects(path, clock=lambda: AT)


def _held(fn):
    """A card that is raised and never answered: the waiting state."""
    return None


GIT_DATE = "1790000000 +0000"


class _Uuid:
    """Counted task ids: 000000000001, 000000000002 ..."""

    def __init__(self):
        self.n = 0

    def uuid4(self):
        self.n += 1
        return types.SimpleNamespace(hex=f"{self.n:012x}" + "0" * 20)


def _fixed_git():
    """git's environment with the dates fixed, so a commit hash is the same on
    every run and every machine; the clock and the task ids as well."""
    real = W.git_env

    def env():
        e = real()
        e.update({"GIT_AUTHOR_DATE": GIT_DATE, "GIT_COMMITTER_DATE": GIT_DATE})
        return e

    W.git_env = env
    W.uuid = _Uuid()
    W.time = types.SimpleNamespace(time=lambda: AT)
    return real


def _blocks(*files):
    return "".join(f"<<<FILE {path}>>>\n{body}\n<<<END>>>\n" for path, body in files)


class _Said:
    """What the approval gate hands back after the owner answers."""

    def __init__(self, outcome):
        self.allowed = outcome == "approved"
        self.outcome = outcome
        self.tier = "ask"
        self.reason = outcome


def _app_cases() -> tuple:
    """The `app` part of the contract, from a real run. Returns (cases, posts,
    merge_card)."""
    s = _store()
    shutil.rmtree(W.root(), ignore_errors=True)
    real_env, real_uuid, real_time, real_a_time = W.git_env, W.uuid, W.time, A.time
    _fixed_git()
    A.time = W.time
    out, posts = {}, {}
    try:
        def post(route, body=None, **kw):
            code, answer = A.handle_post(route, body or {}, store=s, **kw) \
                if A.parse_route(route) else P.handle_post(route, body or {}, store=s, **kw)
            return {"status": code, "body": answer}

        def note(name, route, body=None, **kw):
            posts[name] = post(route, body, **kw)
            return posts[name]["body"]

        def yes(gate_outcome="approved"):
            return dict(gate=lambda *a: _Said(gate_outcome), tier_of=lambda a: "ask",
                        spawn=lambda fn: fn())

        held = dict(gate=lambda *a: None, tier_of=lambda a: "ask", spawn=lambda fn: None)

        # An app folder that has no project yet: an offer inside Projects.
        W.create_project("old-notes", "android", "Old notes")
        made = note("create_app", "/api/projects",
                    {"name": "Notes app", "kind": "coding", "app": {"type": "web"}})
        pid = made["project"]["id"]
        out["list_app"] = P.handle_get("/api/projects", store=s)[1]
        out["app_fresh"] = P.handle_get(f"/api/projects/{pid}", store=s)[1]

        base = f"/api/projects/{pid}/app/tasks"
        first = note("task_start", base, {"title": "Add a dark mode"})["task"]["task"]
        second = note("task_start_second", base, {"title": "Try a login page"})["task"]["task"]
        note("task_start_no_title", base, {"title": "  "})
        note("task_start_long_title", base, {"title": "x" * 121})

        note("paste_from_phone", f"{base}/{first}/files",
             {"blocks": _blocks(("a.txt", "x"))}, here=False)
        note("paste_no_blocks", f"{base}/{first}/files", {"blocks": "just words"}, here=True)
        note("paste_bad_path", f"{base}/{first}/files",
             {"blocks": _blocks(("../escape.txt", "x"))}, here=True)
        note("paste_nothing_changed", f"{base}/{first}/files",
             {"blocks": _blocks((".env", "SECRET=1"))}, here=True)
        note("paste", f"{base}/{first}/files", {"blocks": _blocks(
            ("src/App.tsx", "export default function App() {\n  return <h1>Notes</h1>;\n}"),
            ("src/theme.css", ":root { color-scheme: dark; }"))}, here=True)
        out["app_tasks"] = P.handle_get(f"/api/projects/{pid}", store=s)[1]
        out["task_pasted"] = A.handle_get(f"{base}/{first}", store=s)[1]
        out["task_empty"] = A.handle_get(f"{base}/{second}", store=s)[1]
        note("merge_empty", f"{base}/{second}/merge", {}, **held)
        posts["task_no_such"] = {"status": A.handle_get(f"{base}/{'f' * 12}", store=s)[0],
                                 "body": A.handle_get(f"{base}/{'f' * 12}", store=s)[1]}

        # Too big for one card: the whole change is not sent, and no card.
        big = note("task_start_big", base, {"title": "A huge change"})["task"]["task"]
        note("paste_big", f"{base}/{big}/files",
             {"blocks": _blocks(("big.txt", "\n".join("line %d %s" % (i, "y" * 40)
                                                       for i in range(1400))))}, here=True)
        out["task_too_big"] = A.handle_get(f"{base}/{big}", store=s)[1]
        note("merge_too_big", f"{base}/{big}/merge", {}, **held)
        note("discard", f"{base}/{big}/discard", {})
        note("discard_again", f"{base}/{big}/discard", {})

        # A card waiting: one at a time; the task cannot change under it.
        note("merge_card_raised", f"{base}/{first}/merge", {}, **held)
        out["app_waiting"] = P.handle_get(f"/api/projects/{pid}", store=s)[1]
        note("merge_card_twice", f"{base}/{first}/merge", {}, **held)
        note("paste_while_waiting", f"{base}/{first}/files",
             {"blocks": _blocks(("b.txt", "x"))}, here=True)
        merge_card = W.describe(W.plan_merge("notes-app", first))
        A.withdraw_card("notes-app")

        # The card answered yes: exactly what was shown lands.
        note("merge_yes", f"{base}/{first}/merge", {}, **yes())
        out["app_merged"] = P.handle_get(f"/api/projects/{pid}", store=s)[1]

        # ... and no: the change is kept aside.
        note("paste_second", f"{base}/{second}/files",
             {"blocks": _blocks(("login.html", "<form></form>"))}, here=True)
        note("merge_no", f"{base}/{second}/merge", {}, **yes("denied"))
        out["app_denied"] = P.handle_get(f"/api/projects/{pid}", store=s)[1]

        # Adopting a folder that already exists, and the refusals around it.
        note("adopt", "/api/projects", {"kind": "coding", "app": {"adopt": "old-notes"}})
        out["list_adopted"] = P.handle_get("/api/projects", store=s)[1]
        note("adopt_again", "/api/projects",
             {"name": "Again", "kind": "coding", "app": {"adopt": "old-notes"}})
        note("adopt_missing", "/api/projects",
             {"name": "Ghost", "kind": "coding", "app": {"adopt": "ghost"}})
        note("app_and_folder", "/api/projects",
             {"name": "Both", "kind": "coding", "folder": FOLDER, "app": {"type": "web"}},
             here=True)
        note("app_on_life", "/api/projects",
             {"name": "Run", "kind": "life", "app": {"type": "web"}})
        note("app_bad_type", "/api/projects",
             {"name": "Odd", "kind": "coding", "app": {"type": "ios"}})
        note("update_app", f"/api/projects/{pid}", {"app": {"type": "android"}})
        note("update_folder_on_app", f"/api/projects/{pid}", {"folder": FOLDER}, here=True)
        life = note("create_life_for_app", "/api/projects",
                    {"name": "Half marathon", "kind": "life"})["project"]["id"]
        note("task_on_life", f"/api/projects/{life}/app/tasks", {"title": "x"})

        # Deleting the project keeps the folder: it is offered again.
        note("delete_app", f"/api/projects/{pid}/delete", {})
        out["list_after_delete"] = P.handle_get("/api/projects", store=s)[1]

        # No git on this PC.
        keep = A._git_present, W._git
        A._git_present = lambda: False
        again = note("adopt_after_delete", "/api/projects",
                     {"name": "Notes app", "kind": "coding", "app": {"adopt": "notes-app"}})
        out["app_no_git"] = P.handle_get(f"/api/projects/{again['project']['id']}", store=s)[1]
        note("task_start_no_git", f"/api/projects/{again['project']['id']}/app/tasks",
             {"title": "x"})

        def _gone(*a, **k):
            raise W.GitUnavailable("git is not installed on this PC (https://git-scm.com), so "
                                   "Jarvis cannot keep app projects yet")

        A._git_present, W._git = keep[0], _gone
        note("create_app_no_git", "/api/projects",
             {"name": "Second app", "kind": "coding", "app": {"type": "web"}})
        A._git_present, W._git = keep
    finally:
        W.git_env, W.uuid, W.time, A.time = real_env, real_uuid, real_time, real_a_time
        P._reset_for_tests()
        A._reset_for_tests()
    return out, posts, merge_card


# --------------------------------------------------------------------------
#   Goal step locks and the finish-time range (JARVIS-API section 101)
# --------------------------------------------------------------------------

def _weekly(vals, end=AT - 3600, step_days=7.0):
    n = len(vals)
    return [(end - (n - 1 - i) * step_days * DAY, v) for i, v in enumerate(vals)]


def forecast_extent(points, f, target=None):
    """Where the chart's edges are once a forecast is drawn (both apps
    implement exactly this, as they do chart_scale): x runs from the first
    number to the last number or the farthest end of the dashed line and
    band; y is chart_scale over the numbers, the target, and the forecast's
    own values (the line's first value, the band's three corners, the
    line's end). A forecast without a line (anything but range/open_ended)
    changes nothing."""
    xs = [float(a) for a, _ in points]
    ys = [float(v) for _, v in points]
    if f.get("line"):
        xs += [f["line"]["to"]["at"], f["band"]["fast"]["at"], f["band"]["slow"]["at"]]
        ys += [f["line"]["from"]["value"], f["line"]["to"]["value"], f["band"]["from"]["value"],
               f["band"]["fast"]["value"], f["band"]["slow"]["value"]]
    return {"x": [min(xs), max(xs)] if xs else [0.0, 1.0], "y": chart_scale(ys, target)}


def _forecast_cases() -> list:
    """Named, worked answers of the real jarvis_forecast.forecast() - the
    apps' tests compare what they DRAW (extent, dashed line, band corners)
    and SAY (`words`, `summary`) with these, word for word."""
    day = lambda k: AT - 3600 - k * DAY          # noqa: E731
    specs = [
        ("no_numbers", [], 25, "lower"),
        ("two_more_needed", _weekly([31, 30, 29]), 25, "lower"),
        ("one_day_only", [(AT - 7200 + i * 600, 31 - i) for i in range(5)], 25, "lower"),
        ("steady_fall", _weekly([80, 79, 78, 77, 76]), 70, "lower"),
        ("scattered_fall", _weekly([80, 76, 79, 75, 78, 74]), 70, "lower"),
        ("very_scattered", _weekly([80, 84, 79, 83, 77]), 70, "lower"),
        ("slow_end_past_two_years", _weekly([80, 79, 80, 79, 78]), 70, "lower"),
        ("rising_goal_higher", _weekly([10, 10.5, 11, 11.5, 12]), 21.1, "higher"),
        ("less_than_a_week", [(day(7), 80.0), (day(6.75), 79.75), (day(6.5), 79.5),
                              (day(4), 77.0), (day(0), 73.0)], 70, "lower"),
        ("clipped_at_the_edge", _weekly([80, 79.5, 79, 78.5, 78]), 60, "lower"),
        ("more_than_two_years", _weekly([80, 79.99, 79.98, 79.97, 79.96]), 70, "lower"),
        ("flat", _weekly([75] * 5), 70, "lower"),
        ("wrong_way", _weekly([72, 73, 74, 75, 76]), 70, "lower"),
        ("reached", _weekly([75, 74, 72, 71, 69]), 70, "lower"),
        ("no_target", _weekly([80, 79, 78, 77, 76]), None, "lower"),
        ("no_direction", _weekly([80, 79, 78, 77, 76]), 70, None),
    ]
    out = []
    for name, pts, target, better in specs:
        f = F.forecast(pts, target, better, AT, tz=timezone.utc)
        latest = sorted(pts)[-1][1] if pts else None
        summary = (WORDS["chart_empty"] if latest is None else
                   f"{len(pts)} numbers. Latest: {P._with_unit(latest, 'min')}. {f['words']}")
        out.append({"name": name, "unit": "min", "target": target, "better": better,
                    "now": AT, "zone": "UTC",
                    "points": [{"at": a, "value": v} for a, v in sorted(pts)],
                    "forecast": f, "extent": forecast_extent(pts, f, target),
                    "summary": summary})
    return out


class _Counted:
    """uuid4().hex, counted: goal ids that do not change from run to run."""
    def __init__(self):
        self.n = 0

    def uuid4(self):
        self.n += 1
        return types.SimpleNamespace(hex=f"{self.n:032x}")


class _NoSched:
    def __init__(self):
        self.n = 0

    def add_repeat(self, kind, rule, text="", source="app"):
        self.n += 1
        return {"id": f"job{self.n}", "state": "active"}

    def act(self, job, what):
        return None


def _goal_cases() -> dict:
    """What /api/goals really answers for locked, reached, undone and refused
    steps, and what the weekly check-in says - from the real jarvis_goals.py
    with a stand-in for the benchmark read."""
    pj, bn = "a" * 32, "b" * 32
    state = {"latest": 31.0, "sensitive": False, "forecast": None}
    clock = [AT]

    def read(project, bench):
        if (project, bench) != (pj, bn):
            raise KeyError(bench)
        return {"id": bn, "name": "5k time", "unit": "min", "better": "lower", "target": 30.0,
                "sensitive": state["sensitive"], "keep_on_screen": state["sensitive"],
                "latest": {"id": "x", "value": state["latest"], "at": AT},
                "forecast": state["forecast"]}

    real_uuid = G.uuid
    G.uuid = _Counted()
    path = _CONF / "goals-cases.db"
    if path.exists():
        path.unlink()
    g = G.Goals(path, clock=lambda: clock[0], scheduler=_NoSched(), bench_reader=read)
    real_get = G.get
    G.get = lambda: g
    out = {}
    try:
        def post(route, body):
            code, resp = G.handle_post(route, body)
            return {"status": code, "body": resp}

        made = post("/api/goals", {"text": "Run a race", "plan": [
            {"step": "Get the 5k under 30", "by": "March",
             "measure": {"project": pj, "bench": bn}},
            {"step": "Enter the race", "by": "April", "needs": ["s1"]},
            {"step": "Book the train", "by": "April", "needs": ["s2"]}]})
        out["created"] = made
        gid = made["body"]["goal"]["id"]
        out["refuse_tick_locked"] = post(f"/api/goals/{gid}/step", {"id": "s2", "done": True})
        state["latest"] = 29.5
        out["number_reached"] = G.handle_get(f"/api/goals/{gid}")[1]
        clock[0] = AT + 60
        out["ticked_by_hand"] = post(f"/api/goals/{gid}/step", {"id": "s1", "done": True})
        clock[0] = AT + 120
        out["second_ticked"] = post(f"/api/goals/{gid}/step", {"index": 1, "done": True})
        clock[0] = AT + 180
        out["first_undone"] = post(f"/api/goals/{gid}/step", {"id": "s1", "done": False})
        out["refuse_cycle"] = post("/api/goals", {"text": "Loop", "plan": [
            {"id": "s1", "step": "Paint", "needs": ["s2"]},
            {"id": "s2", "step": "Sand", "needs": ["s1"]}]})
        out["refuse_self"] = post("/api/goals", {"text": "Self", "plan": [
            {"id": "s1", "step": "Paint", "needs": ["s1"]}]})
        out["refuse_unknown"] = post("/api/goals", {"text": "Unknown", "plan": [
            {"id": "s1", "step": "Paint", "needs": ["s4"]}]})
        out["refuse_too_many"] = post("/api/goals", {"text": "Many", "plan": [
            {"step": "a"}, {"step": "b"}, {"step": "c"}, {"step": "d"},
            {"step": "e", "needs": ["s1", "s2", "s3", "s4"]}]})
        # the check-in's own words
        notes = {}
        state["latest"] = 31.0
        g.accept(gid)
        clock[0] = AT + 240
        g.mark_step(gid, None, False, step_id="s2")
        g.mark_step(gid, None, False, step_id="s1")
        notes["first_step_open"] = g.checkin_note(gid)
        state["forecast"] = {"state": "range", "words": "About 6 to 9 weeks at this pace."}
        notes["with_pace_line"] = g.checkin_note(gid)
        state["sensitive"] = True
        notes["private_benchmark_no_pace_line"] = g.checkin_note(gid)
        state["sensitive"] = False
        state["forecast"] = None
        state["latest"] = 29.0
        notes["number_reached"] = g.checkin_note(gid)
        g.mark_step(gid, None, True, step_id="s1")
        g.mark_step(gid, None, True, step_id="s2")
        g.mark_step(gid, None, True, step_id="s3")
        notes["all_done"] = g.checkin_note(gid)
        out["checkin_notes"] = notes
        out["list"] = G.handle_get("/api/goals")[1]
    finally:
        G.get = real_get
        G.uuid = real_uuid
    return out


def cases() -> dict:
    s = _store()
    out, posts = {}, {}

    code, body = P.handle_get("/api/projects", store=s)
    out["list_empty"] = body

    code, body = P.handle_post("/api/projects", {
        "name": "Half marathon", "kind": "life",
        "instructions": "Keep me honest about training. Race is 12 April.",
        "notes": ["Long runs on Sundays", "Knee: stop if it hurts"],
    }, store=s)
    posts["create_life"] = {"status": code, "body": body}
    life = body["project"]["id"]

    def bench(pid, b):
        return P.handle_post(f"/api/projects/{pid}/benchmarks", b, store=s, here=True)[1][
            "benchmark"]["id"]

    run = bench(life, {"name": "Long run", "unit": "km", "better": "higher", "target": 21.1})
    weight = bench(life, {"name": "Weight", "unit": "kg", "better": "lower"})
    five = bench(life, {"name": "5k time", "unit": "min", "better": "lower"})
    mine = bench(life, {"name": "Stretching", "unit": "min", "sensitive": True})
    for i, v in enumerate((8, 10.5, 12)):
        s.log(life, run, v, at=AT - (3 - i) * 7 * DAY)
    for i, v in enumerate((74.2, 73.6)):
        s.log(life, weight, v, at=AT - (2 - i) * 7 * DAY)
    s.log(life, five, 27.5, at=AT - 2 * DAY)
    code, body = P.handle_post(f"/api/projects/{life}/benchmarks/{five}/log",
                               {"value": 26.75, "at": AT - DAY}, store=s)
    posts["log"] = {"status": code, "body": body}

    code, body = P.handle_post("/api/projects", {"name": "Jarvis Desktop", "kind": "coding",
                                                 "folder": FOLDER}, store=s, here=True)
    posts["create_coding_pc"] = {"status": code, "body": body}
    coding = body["project"]["id"]
    code, body = P.handle_post(f"/api/projects/{coding}/benchmarks",
                               {"name": "tests", "kind": "command", "command": "pytest -q",
                                "better": "higher"}, store=s, here=True)
    posts["bench_command_pc"] = {"status": code, "body": body}
    bench(coding, {"name": "Startup", "unit": "ms", "better": "lower", "target": 800})

    code, body = P.handle_get("/api/projects", store=s)
    out["list_two"] = body
    out["life"] = P.handle_get(f"/api/projects/{life}", store=s)[1]
    out["coding"] = P.handle_get(f"/api/projects/{coding}", store=s)[1]
    out["bench_run"] = P.handle_get(f"/api/projects/{life}/benchmarks/{run}", "points=365",
                                    store=s)[1]
    out["bench_weight"] = P.handle_get(f"/api/projects/{life}/benchmarks/{weight}", "",
                                       store=s)[1]
    out["bench_empty"] = P.handle_get(
        f"/api/projects/{coding}/benchmarks/{bench(coding, {'name': 'Score'})}", "",
        store=s)[1]

    # The cards: ON, and taking Jarvis's own mark off. Raised, never answered.
    code, body = P.handle_post(f"/api/projects/{life}/shareable", {"on": True}, store=s,
                               gate=lambda *a: None, tier_of=lambda a: "ask", spawn=_held)
    posts["shareable_on"] = {"status": code, "body": body}
    code, body = P.handle_post(f"/api/projects/{life}/benchmarks/{five}/unmark", {}, store=s,
                               gate=lambda *a: None, tier_of=lambda a: "ask", spawn=_held)
    posts["unmark_card"] = {"status": code, "body": body}
    out["life_waiting"] = P.handle_get(f"/api/projects/{life}", store=s)[1]
    code, body = P.handle_post(f"/api/projects/{life}/shareable", {"on": False}, store=s)
    posts["shareable_off"] = {"status": code, "body": body}
    code, body = P.handle_post(f"/api/projects/{life}/benchmarks/{mine}/unmark", {}, store=s)
    posts["unmark_yours"] = {"status": code, "body": body}
    # What the owner sees after answering (the time fixed, as a real one is
    # whenever it happened).
    P._P_STATE["last"][life] = {"outcome": "denied", "why": "", "at": AT,
                                "message": P.LAST_WORDS["denied"]}
    P._M_STATE["pending"].clear()
    P._M_STATE["last"][five] = {"outcome": "off", "why": "", "at": AT,
                                "message": P.UNMARK_WORDS["off"]}
    s.clear_auto_mark(life, five, "5k time", "min", "money")
    out["life_answered"] = P.handle_get(f"/api/projects/{life}", store=s)[1]

    # Refusals, in the PC's own words.
    code, body = P.handle_post("/api/projects", {"name": "Phone app", "kind": "coding",
                                                 "folder": FOLDER}, store=s, here=False)
    posts["folder_from_phone"] = {"status": code, "body": body}
    code, body = P.handle_post(f"/api/projects/{coding}/benchmarks",
                               {"name": "lint", "kind": "command", "command": "ruff ."},
                               store=s, here=False)
    posts["command_from_phone"] = {"status": code, "body": body}
    code, body = P.handle_post("/api/projects", {"name": "Half marathon", "kind": "life"},
                               store=s)
    posts["name_twice"] = {"status": code, "body": body}
    code, body = P.handle_post(f"/api/projects/{life}", {"instructions": "x" * 1501}, store=s)
    posts["too_long"] = {"status": code, "body": body}
    code, body = P.handle_get(f"/api/projects/{'f' * 32}", store=s)
    posts["no_such"] = {"status": code, "body": body}
    code, body = P.handle_post(f"/api/projects/{life}/delete", {}, store=s)
    posts["delete"] = {"status": code, "body": body}
    P._reset_for_tests()

    app_out, app_posts, merge_card = _app_cases()
    out.update(app_out)
    posts.update(app_posts)

    numbers = [{"value": v, "unit": u, "text": P._with_unit(v, u)}
               for v, u in ((5, "km"), (72.5, "kg"), (10000, "steps"), (200, "$"), (12.5, "%"),
                            (0.125, ""), (26.75, "min"), (-3, "°C"), (21.1, "km"), (1e6, ""))]
    scales = [{"values": v, "target": t, "scale": chart_scale(v, t)}
              for v, t in (([], None), ([5], None), ([0], None), ([8, 10.5, 12], 21.1),
                           ([74.2, 73.6], None), ([1000, 1000], None), ([-2, 3], 0),
                           ([27.5, 26.75], None))]
    return {"cases": out, "posts": posts,
            # A backend without jarvis_projects.py / projects.patch.
            "missing": {"status": 404, "body": {"error": "not found"}},
            "words": WORDS, "numbers": numbers, "scales": scales,
            # Section 101: the sentences and worked answers both apps must match.
            "forecast_words": dict(F.WORDS),
            "forecast_cases": _forecast_cases(),
            "forecast_rules": {"min_numbers": F.MIN_USED, "min_days": F.MIN_DAYS,
                               "min_span_days": F.MIN_SPAN_DAYS, "window_days": F.WINDOW_DAYS,
                               "max_used": F.MAX_USED, "max_weeks": F.MAX_WEEKS,
                               "edge_spans": F.EDGE_SPANS},
            "goal_words": dict(G.WORDS),
            "goal_limits": {"steps": G.MAX_STEPS, "needs": G.MAX_NEEDS,
                            "step_ids": list(G.STEP_IDS)},
            "goal_cases": _goal_cases(),
            "share_card": P.share_card("Half marathon"),
            # The apps' shared sentences (JARVIS-API section 92): how a merge
            # ended (the PC sends them in `app.merge.last.message`), and the
            # words both apps say themselves.
            "app_words": {
                "outcomes": dict(A.OUTCOME_WORDS),
                "cant_run": "Jarvis cannot run this yet. Run it yourself and log the number.",
                "pasted_line": W.PASTED_LINE,
                "card_waiting": A.CARD_WAITING,
                "delete_app_project_q": ("Delete the project \"{name}\"? Its benchmarks and "
                                         "every number logged go with it. The app's files stay "
                                         "on this PC and can be added back later. This cannot "
                                         "be undone."),
                "deleted_app_kept": ("Deleted. The app's files stay on this PC and can be "
                                     "added back."),
            },
            "app_limits": {"open_tasks": W.MAX_OPEN_TASKS, "task_title": A.MAX_TITLE,
                           "blocks": A.MAX_BLOCKS_CHARS, "card_diff": W.MAX_CARD_DIFF_CHARS},
            "app_merge_card": merge_card,
            "unmark_card": P.unmark_card("5k time", "Half marathon", "money", "min"),
            "limits": {"projects": P.MAX_PROJECTS, "name": P.MAX_NAME,
                       "instructions": P.MAX_INSTRUCTIONS, "notes": P.MAX_NOTES,
                       "note": P.MAX_NOTE, "benchmarks": P.MAX_BENCHMARKS,
                       "bench_name": P.MAX_BENCH_NAME, "unit": P.MAX_UNIT}}


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    if shutil.which("git") is None:
        print("git is not installed here, and the app answers in this file come from a real "
              "run of it - install git (https://git-scm.com) and run this again.")
        return 1
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_projects_cases.py")
        if stale:
            return 1
        print("projects-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
