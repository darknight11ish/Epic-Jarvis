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
"""
import json
import os
import sys
import tempfile
import types
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
    P._new_id = _Ids()
    P.check_folder = lambda path, allowed=None: str(path)
    path = _CONF / "projects.db"
    if path.exists():
        path.unlink()
    return P.Projects(path, clock=lambda: AT)


def _held(fn):
    """A card that is raised and never answered: the waiting state."""
    return None


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
            "share_card": P.share_card("Half marathon"),
            "unmark_card": P.unmark_card("5k time", "Half marathon", "money", "min"),
            "limits": {"projects": P.MAX_PROJECTS, "name": P.MAX_NAME,
                       "instructions": P.MAX_INSTRUCTIONS, "notes": P.MAX_NOTES,
                       "note": P.MAX_NOTE, "benchmarks": P.MAX_BENCHMARKS,
                       "bench_name": P.MAX_BENCH_NAME, "unit": P.MAX_UNIT}}


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
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
