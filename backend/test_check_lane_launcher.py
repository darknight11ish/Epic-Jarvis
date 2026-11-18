"""test_check_lane_launcher.py - the lane launcher's tracked copy and its drift check.

    py -3 -B backend/test_check_lane_launcher.py

WHY THIS SUITE EXISTS

The script that decides which graphics card(s) an Ollama lane may use lives on
the owner's Windows profile, outside this repository:

    C:\\Users\\pcadmin\\AppData\\Local\\JarvisOllama\\start-lane.ps1

Two lines in it decide how every model preset behaves - the
``$env:CUDA_VISIBLE_DEVICES = $GpuUuid`` assignment (one card, because the logon
task passes one ``-GpuUuid``) and ``$env:OLLAMA_MAX_LOADED_MODELS = '1'`` - and
before this work no test could read either. On 2026-11-18 a pull request
changed the repository's lane table to say the everyday lane at port 11436 runs
across all three cards; CI was green, and the machine could not do it (measured
that night: loading on 11436 grew the RTX 2060 by 3,713 MiB and the other two
cards by 0 MiB each). ``scripts/start-lane.ps1`` and
``tools/check_lane_launcher.py`` are the answer, and this suite proves the
answer can fail.

WHAT IS PROVED HERE, all on temporary folders and hand-built fixtures - NEVER
by reading the owner's real machine, so it is the same answer on a CI runner:

  * the tracked copy is in the tree, its header says it is a copy, says where
    the live file lives and says editing it alone changes nothing, and its
    machine-readable TASK/GPU rows carry the two logon tasks this PC runs;
  * an identical live file PASSES, with a clean line saying so;
  * ONE CHANGED CHARACTER in ``CUDA_VISIBLE_DEVICES`` FAILS the comparison and
    prints BOTH paths, the tracked-file line number, the live line number and
    both lines - the same for ONE CHANGED CHARACTER in a port;
  * an ABSENT live file prints "not checked: no live launcher on this machine"
    in those exact words, exits 3, and does NOT print a pass - the
    BLOCKED-is-never-a-pass rule;
  * a live logon task whose -GpuUuid differs from the tracked record FAILS, and
    names both values and the task;
  * a live card list that differs from the tracked GPU block FAILS;
  * the lane table rule: when a lane claims "all three cards" but its tracked
    logon task passes ONE -GpuUuid, the check FAILS and prints the exact
    "2-step deploy: update the lane task" block with the exact task and the
    exact comma-separated -GpuUuid value - this is the failure 2026-11-18's green
    CI did not have;
  * the on-demand pooled lane (no logon task) is NOT judged, because there is no
    task grant to compare, and the run says so instead of inventing one;
  * a named card that is not the card the task pins FAILS and names the card the
    task should carry;
  * a tracked copy that is missing its header, or has no END marker, is a
    FAILURE, never a quiet pass;
  * THIS REPOSITORY is honourable: its own lane table passes the repository-half
    check that the required backend job runs (the gate that a future
    "everyday lane on all three cards" pull request would go red on unless it
    also updated the tracked logon-task table);
  * the tool is READ-ONLY: no create/change/delete argument, no file write, no
    Start-ScheduledTask.

BOTH HALVES ARE EXERCISED, and the machine-reading halves are injected:
``preflight`` takes the live file folder and the task/card readers as
arguments, so every section is driven from a fixture. The one CLI run below
that would look at a machine points at a missing live folder, which every
machine answers the same way.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_lane_launcher.py"
TRACKED = REPO / "scripts" / "start-lane.ps1"
LIVE_PATH = r"C:\Users\pcadmin\AppData\Local\JarvisOllama\start-lane.ps1"

PASSED, FAILED = [], []


def load_tool():
    """The tool under test, loaded from its file (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("check_lane_launcher_under_test",
                                                  TOOL)
    module = importlib.util.module_from_spec(spec)
    # Register it before executing: the tool's @dataclass definitions look their
    # own module up in sys.modules, and a module name nobody registered crashes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


L = load_tool()

#: Fixture cards and tasks. The UUIDs are shaped like real ones but belong to
#: no machine: a test must never depend on the owner's PC.
A = "GPU-aaaaaaaa-1111-2222-3333-444444444444"
B = "GPU-bbbbbbbb-1111-2222-3333-444444444444"
C = "GPU-cccccccc-1111-2222-3333-444444444444"
EVERYDAY = "Jarvis Ollama - Everyday model (RTX 2060)"
CODING = "Jarvis Ollama - Coding model (RTX 2080 Super)"
GPU_ROWS = (
    (0, "NVIDIA GeForce RTX 2060", A),
    (1, "NVIDIA GeForce RTX 2080 SUPER", B),
    (2, "NVIDIA GeForce RTX 2080 SUPER", C),
)
TASK_ROWS = (
    (EVERYDAY, "main", 11436, A, 196608),
    (CODING, "coding", 11435, C, 16384),
)

#: The fixture launcher body: a tiny stand-in with the two lines that matter,
#: plus a numeric port so a one-character port change can be proven.
FIXTURE_BODY = """\
[CmdletBinding()]
param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$GpuUuid)
$ErrorActionPreference = 'Stop'
$env:OLLAMA_HOST = "127.0.0.1:11436"
$env:CUDA_VISIBLE_DEVICES = $GpuUuid
$env:OLLAMA_VULKAN = '0'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
"""


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="lane-guard-"))


def write_bytes(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def header_text(tasks=TASK_ROWS, gpus=GPU_ROWS, sentence=True, end_marker=True) -> str:
    """A tracked-copy header shaped like the real one, with fixture rows."""
    lines = ["# ====================================================================="]
    if sentence:
        lines.append("#  TRACKED COPY - THIS IS NOT THE FILE THE OWNER'S PC RUNS.")
    lines.append("#  (fixture: the real file is scripts/start-lane.ps1)")
    lines.append(f"#  live: {LIVE_PATH}")
    lines.append("#")
    for name, lane, port, uuids, context in tasks:
        value = uuids if isinstance(uuids, str) else ",".join(uuids)
        lines.append(f"#  TASK|{name}|{lane}|{port}|{value}|{context}")
    lines.append("#")
    for index, name, uuid in gpus:
        lines.append(f"#  GPU|{index}|{name}|{uuid}")
    if end_marker:
        lines.append("# <<< END OF TRACKED-COPY HEADER - EVERYTHING BELOW IS THE "
                     "LIVE FILE >>>")
    return "\n".join(lines) + "\n"


def presets_text(main_card="RTX 2060", coding_card="RTX 2080 SUPER",
                 include_pooled=True) -> str:
    """A lane table shaped like backend/jarvis_presets.py's LANES."""
    rows = [
        '    "main": {"key": "main", "card": %r, "port": 11436, '
        '"words": "the everyday lane"},' % main_card,
        '    "coding": {"key": "coding", "card": %r, "port": 11435, '
        '"words": "the fast card"},' % coding_card,
    ]
    if include_pooled:
        rows.append('    "pooled": {"key": "pooled", "card": "all three cards", '
                    '"port": 11450, "words": "one model across all three cards"},')
    return ("from __future__ import annotations\n\nLANES = {\n"
            + "\n".join(rows) + "\n}\n")


def make_repo(root: Path, body: str = FIXTURE_BODY, tasks=TASK_ROWS, gpus=GPU_ROWS,
              presets="", sentence=True, end_marker=True) -> Path:
    """A throwaway repository with a tracked launcher and a lane table."""
    repo = root / "repo"
    write_bytes(repo / "scripts" / "start-lane.ps1",
                header_text(tasks=tasks, gpus=gpus, sentence=sentence,
                            end_marker=end_marker) + body)
    write_bytes(repo / "backend" / "jarvis_presets.py",
                presets if presets else presets_text())
    return repo


def make_live(root: Path, body: str = FIXTURE_BODY, folder: str = "live") -> Path:
    """A throwaway 'live' launcher folder."""
    live = root / folder
    write_bytes(live / "start-lane.ps1", body)
    return live


def lane_task(row):
    name, lane, port, uuids, context = row
    values = tuple(uuids) if not isinstance(uuids, str) else (uuids,)
    return L.LaneTask(name=name, lane=lane, port=port, uuids=values, context=context)


def card(row):
    return L.Gpu(index=row[0], name=row[1], uuid=row[2])


def readers(tasks=TASK_ROWS, gpus=GPU_ROWS, task_reason="", gpu_reason=""):
    """(task_reader, gpu_reader) as the preflight takes them - fixtures, no PC."""
    def read_tasks():
        return (tuple(lane_task(row) for row in tasks), task_reason)

    def read_gpus():
        return (tuple(card(row) for row in gpus), gpu_reason)

    return read_tasks, read_gpus


def preflight(repo: Path, live_dir: Path, tasks=TASK_ROWS, gpus=GPU_ROWS,
              run_machine=True, task_reason="", gpu_reason=""):
    read_tasks, read_gpus = readers(tasks=tasks, gpus=gpus,
                                    task_reason=task_reason, gpu_reason=gpu_reason)
    return L.preflight(repo_root=repo, live_dir=live_dir, task_reader=read_tasks,
                       gpu_reader=read_gpus, run_machine=run_machine)


def text_of(verdict) -> str:
    return "\n".join(verdict.lines())


def full_text(verdict) -> str:
    """Everything the tool prints for a verdict, including the 2-step block."""
    return text_of(verdict) + "\n" + "\n".join(verdict.two_step_lines())


def section(verdict, title_fragment: str):
    for item in verdict.sections:
        if title_fragment in item.title:
            return item
    return None


def run_tool(*args) -> tuple:
    done = subprocess.run([sys.executable, "-B", str(TOOL), *args], cwd=str(REPO),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


# ---------------------------------------------------------------------------
#   1. the tracked copy is in the tree and says what it is
# ---------------------------------------------------------------------------

def t_the_tracked_copy_is_in_the_tree_and_says_what_it_is():
    check("scripts/start-lane.ps1 exists in the repository", TRACKED.is_file(),
          str(TRACKED))
    text = TRACKED.read_text(encoding="utf-8", errors="replace")
    check("its header says it is the tracked copy, not the live file",
          "TRACKED COPY" in text and "THIS IS NOT THE FILE THE OWNER'S PC RUNS" in text)
    check("its header says where the live file lives", LIVE_PATH in text, LIVE_PATH)
    check("its header says editing it alone changes nothing on the machine",
          "EDITING THIS FILE ALONE CHANGES NOTHING ON THE MACHINE" in text)
    header, body = L.split_tracked(text)
    tasks, gpus = L.parse_header(header)
    check("it records exactly the two logon tasks this PC runs",
          {task.name for task in tasks} == {EVERYDAY, CODING},
          [task.name for task in tasks])
    check("the everyday task grants ONE card in the tracked table",
          len([t for t in tasks if t.lane == "main"][0].uuids) == 1)
    check("the tracked table records all three installed cards", len(gpus) == 3, gpus)
    check("the live-file body below the header is a real PowerShell launcher",
          any("CUDA_VISIBLE_DEVICES" in line for line in body)
          and any("OLLAMA_MAX_LOADED_MODELS" in line for line in body))


# ---------------------------------------------------------------------------
#   2. a match passes, and ONE changed character fails
# ---------------------------------------------------------------------------

def t_an_identical_live_file_passes():
    root = tmpdir()
    try:
        repo = make_repo(root)
        live = make_live(root)
        verdict = preflight(repo, live)
        drift = section(verdict, "the tracked copy vs the live launcher")
        check("an identical live file passes the drift section",
              drift is not None and drift.status == L.PASS,
              text_of(verdict))
        check("... and the whole run passes", verdict.verdict == L.PASS,
              text_of(verdict))
        check("... with a line saying the files match",
              "matches the tracked copy line for line" in text_of(verdict))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_one_changed_character_in_CUDA_VISIBLE_DEVICES_is_caught():
    root = tmpdir()
    try:
        repo = make_repo(root)
        changed = FIXTURE_BODY.replace("$env:CUDA_VISIBLE_DEVICES = $GpuUuid",
                                       "$env:CUDA_VISIBLE_DEVICES = $GpuUid")
        live = make_live(root, body=changed)
        verdict = preflight(repo, live)
        text = text_of(verdict)
        drift = section(verdict, "the tracked copy vs the live launcher")
        check("one changed character in CUDA_VISIBLE_DEVICES fails the check",
              verdict.failed and drift is not None and drift.status == L.FAIL, text)
        check("... both paths are named",
              str(repo / "scripts" / "start-lane.ps1") in text
              and str(live / "start-lane.ps1") in text, text)
        header, _body = L.split_tracked((repo / "scripts" / "start-lane.ps1")
                                        .read_text(encoding="utf-8"))
        body_lines = FIXTURE_BODY.splitlines()
        index = body_lines.index("$env:CUDA_VISIBLE_DEVICES = $GpuUuid")
        where = f"tracked line {len(header) + index + 1} / live line {index + 1}"
        check(f"... the differing lines are named ({where})", where in text, text)
        check("... and both versions of the changed line are printed",
              "CUDA_VISIBLE_DEVICES = $GpuUuid" in text
              and "CUDA_VISIBLE_DEVICES = $GpuUid" in text, text)
        check("... and the run prints the 2-step deploy block",
              "2-step deploy: update the lane task" in full_text(verdict)
              and EVERYDAY in full_text(verdict) and A in full_text(verdict),
              full_text(verdict))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_one_changed_character_in_a_port_is_caught():
    root = tmpdir()
    try:
        repo = make_repo(root)
        changed = FIXTURE_BODY.replace("127.0.0.1:11436", "127.0.0.1:11435")
        live = make_live(root, body=changed)
        verdict = preflight(repo, live)
        text = text_of(verdict)
        drift = section(verdict, "the tracked copy vs the live launcher")
        check("one changed character in a port fails the comparison",
              verdict.failed and drift is not None and drift.status == L.FAIL, text)
        check("... and the two port values are printed",
              "127.0.0.1:11436" in text and "127.0.0.1:11435" in text, text)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
#   3. absent live file: the exact sentence, and never a pass
# ---------------------------------------------------------------------------

def t_an_absent_live_file_says_not_checked_in_those_words():
    root = tmpdir()
    try:
        repo = make_repo(root)
        missing = root / "no-machine-here"
        verdict = preflight(repo, missing)
        text = text_of(verdict)
        check("an absent live file is NOT a failure",
              not verdict.failed, text)
        check("... and NOT a pass", verdict.verdict == L.NOT_CHECKED, text)
        check("... and the exact sentence is printed",
              "not checked: no live launcher on this machine" in text, text)
        check("... the missing path is named", str(missing / "start-lane.ps1") in text,
              text)
        drift = section(verdict, "the tracked copy vs the live launcher")
        check("... the drift section is NOT CHECKED, not PASS",
              drift is not None and drift.status == L.NOT_CHECKED, text)
        code, cli = run_tool("--repo-root", str(repo), "--live-dir", str(missing))
        check("the CLI exits 3 when it could not read the machine", code == 3,
              (code, cli[-600:]))
        check("... and its output carries the exact sentence",
              "not checked: no live launcher on this machine" in cli, cli[-600:])
        check("... and never says the run passed",
              "RESULT: PASS" not in cli, cli[-600:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
#   4. the live task table and the live card list are compared too
# ---------------------------------------------------------------------------

def t_a_changed_GpuUuid_in_a_logon_task_is_caught():
    root = tmpdir()
    try:
        repo = make_repo(root)
        live = make_live(root)
        changed = ((EVERYDAY, "main", 11436, B, 196608),  # the PC pins the other card
                   (CODING, "coding", 11435, C, 16384))
        verdict = preflight(repo, live, tasks=changed)
        text = text_of(verdict)
        tasks_section = section(verdict, "Task Scheduler")
        check("a changed -GpuUuid in a logon task fails the check",
              verdict.failed and tasks_section is not None
              and tasks_section.status == L.FAIL, text)
        check("... the task is named and both values are printed",
              EVERYDAY in text and f"repo says {A}" in text
              and f"the PC has {B}" in text, text)
        check("... the 2-step block names the exact value the task should carry",
              "2-step deploy: update the lane task" in full_text(verdict)
              and f"-GpuUuid it should carry: {A}" in full_text(verdict),
              full_text(verdict))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_changed_card_list_is_caught():
    root = tmpdir()
    try:
        repo = make_repo(root)
        live = make_live(root)
        swapped = ((0, "NVIDIA GeForce RTX 2060", A),
                   (1, "NVIDIA GeForce RTX 2080 SUPER", C),
                   (2, "NVIDIA GeForce RTX 2080 SUPER", B))
        verdict = preflight(repo, live, gpus=swapped)
        text = text_of(verdict)
        cards_section = section(verdict, "graphics cards")
        check("a card list that differs from the tracked GPU block fails",
              verdict.failed and cards_section is not None
              and cards_section.status == L.FAIL, text)
        check("... the card UUID and both indexes are printed",
              B in text and "index 1" in text and "index 2" in text, text)
        code, cli = run_tool("--repo-root", str(repo), "--live-dir",
                             str(root / "no-machine-here"))
        check("an unreadable card list is NOT CHECKED (exit 3), never a fail",
              code == 3 and "not checked:" in cli, cli[-600:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
#   5. the lane table rule (the one that would have caught 2026-11-18)
# ---------------------------------------------------------------------------

def t_a_lane_that_asks_for_more_cards_than_its_task_grants_fails():
    root = tmpdir()
    try:
        repo = make_repo(root, presets=presets_text(main_card="all three cards"))
        verdict = preflight(repo, root / "no-machine-here", run_machine=False)
        text = full_text(verdict)
        lanes_section = section(verdict, "lane table")
        check("a lane table saying 'all three cards' fails when its task passes ONE",
              verdict.failed and lanes_section is not None
              and lanes_section.status == L.FAIL, text)
        check("... the lane and the single card are named",
              "lane 'main'" in text and "only 1 -GpuUuid" in text and A in text, text)
        check("... the block starts with the exact words of the owner's rule",
              "2-step deploy: update the lane task" in text, text)
        check("... the exact task is named", EVERYDAY in text, text)
        check("... the exact -GpuUuid value the task should carry is named",
              f"-GpuUuid it should carry: {A},{B},{C}" in text, text)
        code, cli = run_tool("--repo-only", "--repo-root", str(repo))
        check("the CLI's repository-only mode exits 1 on that tree", code == 1,
              (code, cli[-800:]))
        check("... and prints the 2-step block", "2-step deploy: update the lane task"
              in cli, cli[-800:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_an_on_demand_lane_with_no_task_is_not_judged():
    root = tmpdir()
    try:
        repo = make_repo(root, presets=presets_text(include_pooled=True))
        # Two tasks, but the pooled lane has no task - and it must not be invented.
        verdict = preflight(repo, root / "no-machine-here", run_machine=False)
        text = text_of(verdict)
        check("a lane with no logon task is not a failure", not verdict.failed, text)
        check("... and the run says the lane was not judged",
              "has no logon task" in text and "not judged" in text, text)
        check("... and it still passes the lanes it could compare",
              verdict.repo_status == L.PASS, text)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_named_card_that_is_not_the_pinned_card_fails():
    root = tmpdir()
    try:
        # The tracked task table pins the 2080 SUPER (C) for the everyday lane,
        # while the lane table names the RTX 2060. The checker must name the RTX
        # 2060's UUID as the value that task should carry.
        repo = make_repo(root, presets=presets_text(main_card="RTX 2060"),
                         tasks=((EVERYDAY, "main", 11436, C, 196608),
                                (CODING, "coding", 11435, C, 16384)))
        verdict = preflight(repo, root / "no-machine-here", run_machine=False)
        text = full_text(verdict)
        check("a card claim that names a different card from the task's pin fails",
              verdict.failed, text)
        check("... the pinned card is named",
              "the logon task pins" in text and C in text, text)
        check("... and the card the task should carry is named",
              f"-GpuUuid it should carry: {A}" in text, text)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
#   6. a broken tracked copy is a failure, never a quiet pass
# ---------------------------------------------------------------------------

def t_a_tracked_copy_without_a_header_is_a_failure():
    root = tmpdir()
    try:
        repo = make_repo(root, sentence=False)
        verdict = preflight(repo, root / "no-machine-here", run_machine=False)
        text = text_of(verdict)
        check("a tracked copy with no header sentence is refused",
              verdict.failed and "not shaped like one" in text, text)
        repo2 = make_repo(root / "second", end_marker=False)
        verdict2 = preflight(repo2, root / "no-machine-here", run_machine=False)
        check("a tracked copy with no END marker is refused",
              verdict2.failed and "END marker" in text_of(verdict2), text_of(verdict2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
#   7. this repository's own half passes - the gate the backend job runs
# ---------------------------------------------------------------------------

def t_this_repository_is_honourable():
    verdict = L.preflight(repo_root=REPO, run_machine=False)
    text = text_of(verdict)
    check("this repository's lane table agrees with its tracked logon tasks",
          verdict.repo_status == L.PASS and not verdict.failed, text)
    check("... and the tracked copy supplies the tasks that judgement needs",
          L.tracked_launcher(REPO).is_file()
          and L.read_repo_lanes(REPO) is not None)
    header, _body = L.split_tracked(TRACKED.read_text(encoding="utf-8",
                                                      errors="replace"))
    tasks, gpus = L.parse_header(header)
    lanes = L.read_repo_lanes(REPO)
    findings, _notes, compared = L.lane_findings(lanes, tasks, gpus)
    check("... every lane a tracked task runs is compared (not vacuously skipped)",
          compared >= 1, compared)
    check("... and none of them asks for more cards than its task grants",
          findings == [], findings)
    check("... the everyday lane is the one this PC's logon task really starts",
          any(task.lane == "main" and task.port == 11436 for task in tasks), tasks)


def t_the_cli_help_works():
    """--help must work on every Python: argparse %-expands help strings.

    This is the failure a CI runner caught on Python 3.14 and a desk run on
    3.12 did not: a help string carrying the literal "%LOCALAPPDATA%" made
    argparse raise "unsupported format character 'O'" at `--help` (and, on
    3.14, at import of the argument parser - so even a bare run crashed). It
    is one line of a test here and a red audit job otherwise."""
    code, output = run_tool("--help")
    check("the CLI's --help exits 0", code == 0, (code, output[-800:]))
    check("... and it names the flags", "--live-dir" in output
          and "--repo-only" in output, output[-800:])
    check("... with no argparse traceback", "Traceback" not in output
          and "unsupported format character" not in output, output[-800:])


# ---------------------------------------------------------------------------
#   8. the tool only reads
# ---------------------------------------------------------------------------

def t_the_tool_only_reads_and_never_changes_a_task():
    text = TOOL.read_text(encoding="utf-8", errors="replace")
    for forbidden in ('"/create"', '"/change"', '"/delete"', '"/run"',
                      "write_text(", "write_bytes(", "open(", "rmtree(",
                      "unlink(", "Start-ScheduledTask", "Stop-Process",
                      "os.remove", "shutil"):
        check(f"the tool never uses {forbidden!r}", forbidden not in text)
    check("its only task query is schtasks /query",
          '"schtasks", "/query"' in text and '"/query", "/xml"' in text)
    check("its only card query is nvidia-smi -L",
          '"nvidia-smi", "-L"' in text)


if __name__ == "__main__":
    for fn in (t_the_tracked_copy_is_in_the_tree_and_says_what_it_is,
               t_an_identical_live_file_passes,
               t_one_changed_character_in_CUDA_VISIBLE_DEVICES_is_caught,
               t_one_changed_character_in_a_port_is_caught,
               t_an_absent_live_file_says_not_checked_in_those_words,
               t_a_changed_GpuUuid_in_a_logon_task_is_caught,
               t_a_changed_card_list_is_caught,
               t_a_lane_that_asks_for_more_cards_than_its_task_grants_fails,
               t_an_on_demand_lane_with_no_task_is_not_judged,
               t_a_named_card_that_is_not_the_pinned_card_fails,
               t_a_tracked_copy_without_a_header_is_a_failure,
               t_this_repository_is_honourable,
               t_the_cli_help_works,
               t_the_tool_only_reads_and_never_changes_a_task):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
