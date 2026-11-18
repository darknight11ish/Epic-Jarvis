#!/usr/bin/env python3
"""check_lane_launcher.py - compare the repository's lane launcher with the one the owner's PC runs.

    py -3 tools/check_lane_launcher.py                 # the whole check, on this machine
    py -3 tools/check_lane_launcher.py --repo-only     # the half CI can prove; reads no machine
    py -3 tools/check_lane_launcher.py --live-dir DIR  # fixtures, or a moved install
    py -3 tools/check_lane_launcher.py --repo-root DIR # another checkout

WHY THIS EXISTS, IN ONE PARAGRAPH

The script that decides which graphics card(s) an Ollama lane may use lives on
the owner's Windows profile, NOT in this repository:

    C:\\Users\\pcadmin\\AppData\\Local\\JarvisOllama\\start-lane.ps1

Two lines in it decide how every model preset behaves on this PC - the
``$env:CUDA_VISIBLE_DEVICES = $GpuUuid`` assignment (one card, because the logon
task passes one ``-GpuUuid``) and ``$env:OLLAMA_MAX_LOADED_MODELS = '1'`` - and
before the tracked copy existed no test could read either. On 2026-11-18 a pull
request changed the repository's lane table (``jarvis_presets.LANES``) to say
the everyday lane at port 11436 runs across ALL THREE cards. CI was green. The
machine could not do it: the everyday task passes one ``-GpuUuid``, measured
loading grew the RTX 2060 by 3,713 MiB and the other two cards by 0 MiB each.
The repository described a machine that does not exist, and nothing said so.

WHAT IT COMPARES (four sections, each PASS / FAIL / NOT CHECKED)

  1. THE REPOSITORY'S LANE TABLE vs THE TRACKED LOGON TASKS. This one reads NO
     machine: it parses ``backend/jarvis_presets.py``'s ``LANES`` table and
     compares each lane's ``card`` claim with the cards the tracked task for
     that lane grants. A lane that asks for "all three cards" while its task
     passes ONE ``-GpuUuid`` is a FAIL here, and the message carries the exact
     ``-GpuUuid`` value the task would have to carry. This is the section CI can
     run, and the one that would have caught 2026-11-18's pull request.

  2. THE TRACKED COPY vs THE LIVE FILE. ``scripts/start-lane.ps1`` is a copy of
     the live file with a header (the header says it is a copy). Everything
     below the header's END marker must equal the live file line for line; the
     only thing ignored is line-ending style. A difference prints BOTH paths,
     the tracked-file line number and the live line number, and both lines.

  3. THE TRACKED LOGON TASKS vs THIS PC'S TASK SCHEDULER. The tracked copy's
     header records the two tasks that run it (name, lane, port, the exact
     ``-GpuUuid`` value, context). This section reads the machine's real tasks
     and reports a renamed task, a changed port, a changed ``-GpuUuid`` (this
     is the one that decides how many cards a lane gets) or a task the repo
     does not record.

  4. THE TRACKED GRAPHICS CARDS vs ``nvidia-smi -L``. Card names and UUIDs must
     match the machine, because the ``-GpuUuid`` values the tasks carry are
     UUIDs.

NOT CHECKED IS NOT A PASS. Sections 2-4 need the live launcher, so on a fresh
machine or a CI runner they print, in these exact words:

    not checked: no live launcher on this machine

and the run exits 3 - never 0. Silence must never read as agreement. Section 1
is hermetic, so CI still gets the lane-table verdict; that is the difference
between "the machine agreed" and "the repository is self-consistent".

READ-ONLY. It opens files, runs ``schtasks /query`` and ``nvidia-smi -L``, and
prints. It starts nothing, stops nothing, changes no task, file, lane or model.

EXIT CODES

    0  everything it checked agrees (or, with --repo-only, the repository half does)
    1  at least one section FAILED - the repository and/or the machine disagree
    3  no failure, but something was NOT CHECKED (no live launcher on this machine)
"""
from __future__ import annotations

import argparse
import ast
import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

PASS = "PASS"
FAIL = "FAIL"
NOT_CHECKED = "NOT CHECKED"

#: The exact sentence a reader must see when the live file is not here. It is
#: also the sentence the deploy preflight prints; tests assert it word for word.
NOT_CHECKED_LIVE = "not checked: no live launcher on this machine"

#: The tracked copy's header ends where the live file starts.
END_MARKER = "# <<< END OF TRACKED-COPY HEADER"

#: A fragment of the header's first line, so a file that is the live copy without
#: the header is refused rather than compared against itself.
HEADER_SENTENCE = "TRACKED COPY - THIS IS NOT THE FILE THE OWNER'S PC RUNS"

#: The live launcher's own folder, relative to the owner's LOCALAPPDATA.
LIVE_SUBFOLDER = ("JarvisOllama", "start-lane.ps1")

#: The repository's lane table. It is the same table the apps render (its own
#: comment says so), and it is what a preset/apply change edits.
LANE_TABLE = ("backend", "jarvis_presets.py")

_UUID = r"GPU-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
_UUID_RE = re.compile(rf"^{_UUID}$")
_GPU_LINE = re.compile(rf"^GPU\s+(\d+):\s+(.+?)\s+\(UUID:\s+({_UUID})\)\s*$")
_ALL_CARDS = re.compile(r"^all\s+(?:(two|three|four)|(\d+))\s+cards?$", re.IGNORECASE)
_ALL_CARDS_ANY = re.compile(r"^all\s+cards$", re.IGNORECASE)

_ARGUMENTS = re.compile(r"<Arguments>(.*?)</Arguments>", re.DOTALL)
_FLAG_UUID = re.compile(r"-GpuUuid\s+(?:\"([^\"]*)\"|(\S+))", re.IGNORECASE)
_FLAG_LANE = re.compile(r"-Lane\s+(?:\"([^\"]*)\"|(\S+))", re.IGNORECASE)
_FLAG_PORT = re.compile(r"-Port\s+(\d+)", re.IGNORECASE)
_FLAG_CONTEXT = re.compile(r"-ContextLength\s+(\d+)", re.IGNORECASE)
_ENTITIES = (("&quot;", '"'), ("&apos;", "'"), ("&lt;", "<"), ("&gt;", ">"),
             ("&amp;", "&"))

#: How many differing lines to print before summarising the rest.
SHOW_DIFFS = 20


class LauncherFormatError(ValueError):
    """The tracked copy is not shaped like a tracked copy (header, TASK/GPU rows)."""


@dataclass(frozen=True)
class LaneTask:
    """One logon task that runs the launcher: the repo's copy of it, or the live one."""

    name: str
    lane: str
    port: int
    uuids: tuple
    context: int


@dataclass(frozen=True)
class Gpu:
    """One graphics card, as ``nvidia-smi -L`` describes it."""

    index: int
    name: str
    uuid: str


@dataclass
class Finding:
    """One lane whose repository claim its tracked logon task cannot honour."""

    lane: str
    task: str
    problem: str
    should_carry: str = ""


@dataclass
class Blocker:
    """Why a one-step deploy is refused, and what the task should carry."""

    task: str
    should_carry: str
    why: str


@dataclass
class Section:
    """One comparison, and its three-way verdict."""

    title: str
    status: str
    lines: list = field(default_factory=list)


@dataclass
class Preflight:
    """The whole check, with the lines and the refusal block the deploy path prints."""

    sections: list
    blockers: list = field(default_factory=list)
    #: The status of the repository-only half (the lane table vs the tracked tasks).
    #: ``--repo-only`` exits on THIS, not on the verdict, because it deliberately
    #: does not read the machine and "the machine was not read" is not a failure.
    repo_status: str = NOT_CHECKED

    @property
    def failed(self) -> bool:
        return any(section.status == FAIL for section in self.sections)

    @property
    def not_checked(self) -> bool:
        return any(section.status == NOT_CHECKED for section in self.sections)

    @property
    def verdict(self) -> str:
        if self.failed:
            return FAIL
        if self.not_checked:
            return NOT_CHECKED
        return PASS

    def lines(self) -> list:
        out = []
        for number, section in enumerate(self.sections, 1):
            out.append(f"{number}. {section.title}: {section.status}")
            for line in section.lines:
                out.append(f"   {line}")
        return out

    def two_step_lines(self) -> list:
        """The explicit words a refused one-step deploy prints."""
        out = ["2-step deploy: update the lane task"]
        seen = set()
        for blocker in self.blockers:
            key = (blocker.task, blocker.should_carry)
            if key in seen:
                continue
            seen.add(key)
            out.append(f"  why: {blocker.why}")
            out.append(f"  task: {blocker.task or '(no logon task named)'}")
            if blocker.should_carry:
                out.append(f"  -GpuUuid it should carry: {blocker.should_carry}")
        if not self.blockers:
            out.append("  why: the repository's tracked copy is not shaped like one - "
                       "no task value can be named until it is fixed (step 1)")
        out.extend([
            "  step 1 - this deploy writes the repository's backend files (the run prints it).",
            "  step 2 - update each task above in Task Scheduler, restart Jarvis, and run",
            "           this deploy again so it can check both halves.",
            "  This check only READ the machine: no file, task, lane or model was changed.",
        ])
        return out


# ---------------------------------------------------------------------------
#   Where the files are
# ---------------------------------------------------------------------------

def repo_root_default() -> Path:
    """This checkout: tools/check_lane_launcher.py is one level under it."""
    return Path(__file__).resolve().parent.parent


def tracked_launcher(repo_root=None) -> Path:
    """The repository's tracked copy of the launcher."""
    root = Path(repo_root) if repo_root else repo_root_default()
    return root / "scripts" / "start-lane.ps1"


def lane_table_path(repo_root=None) -> Path:
    """The repository's lane table (the table the apps and presets share)."""
    root = Path(repo_root) if repo_root else repo_root_default()
    return root.joinpath(*LANE_TABLE)


def live_launcher(live_dir=None) -> Path:
    """The launcher the owner's PC really runs.

    Default: ``%LOCALAPPDATA%\\JarvisOllama\\start-lane.ps1`` (on a machine
    without LOCALAPPDATA, the same path under the home folder - which is absent
    on a CI runner, and absence is reported as NOT CHECKED, never as a pass).
    ``--live-dir`` overrides the folder for fixtures and moved installs.
    """
    if live_dir:
        return Path(live_dir) / "start-lane.ps1"
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base.joinpath(*LIVE_SUBFOLDER)


# ---------------------------------------------------------------------------
#   Reading the tracked copy
# ---------------------------------------------------------------------------

def split_tracked(text: str) -> tuple:
    """(header_lines, body_lines) for the tracked copy. Raises on a wrong shape.

    The header is everything up to and including the END marker; the body is the
    live file. A file without the marker is refused rather than compared, because
    comparing a headerless file against the live one would call the header lines
    drift and hide a missing header.
    """
    lines = text.splitlines()
    if not any(HEADER_SENTENCE in line for line in lines[:6]):
        raise LauncherFormatError(
            f"the first lines are not the tracked-copy header; expected a line "
            f"containing {HEADER_SENTENCE!r}")
    for index, line in enumerate(lines):
        if line.startswith(END_MARKER):
            body = lines[index + 1:]
            if not body:
                raise LauncherFormatError(
                    f"the END marker line ({index + 1}) is the last line - there "
                    f"is no live-file body below it")
            return lines[:index + 1], body
    raise LauncherFormatError(
        f"no END marker line (one starting {END_MARKER!r}) - the tracked copy "
        f"cannot be split into header and live body")


def _task_row(row: str) -> LaneTask:
    """One ``TASK|name|lane|port|-GpuUuid|context`` row, validated."""
    parts = [part.strip() for part in row.split("|")]
    if len(parts) != 5:
        raise LauncherFormatError(
            f"a TASK row must have 5 fields (name|lane|port|-GpuUuid|context), "
            f"not {len(parts)}: {row!r}")
    name, lane, port, uuids, context = parts
    if not name or not lane:
        raise LauncherFormatError(f"a TASK row needs a name and a lane: {row!r}")
    try:
        port_number = int(port)
        context_number = int(context)
    except ValueError:
        raise LauncherFormatError(
            f"a TASK row's port and context must be numbers: {row!r}") from None
    uuid_list = tuple(item.strip() for item in uuids.split(",") if item.strip())
    if not uuid_list:
        raise LauncherFormatError(f"a TASK row needs at least one UUID: {row!r}")
    for value in uuid_list:
        if not _UUID_RE.match(value):
            raise LauncherFormatError(
                f"a TASK row's -GpuUuid is not a card UUID: {value!r} (row {row!r})")
    return LaneTask(name=name, lane=lane, port=port_number, uuids=uuid_list,
                    context=context_number)


def _gpu_row(row: str) -> Gpu:
    """One ``GPU|index|name|uuid`` row, validated."""
    parts = [part.strip() for part in row.split("|")]
    if len(parts) != 3:
        raise LauncherFormatError(
            f"a GPU row must have 3 fields (index|name|UUID), not {len(parts)}: "
            f"{row!r}")
    index, name, uuid = parts
    try:
        index_number = int(index)
    except ValueError:
        raise LauncherFormatError(f"a GPU row's index is not a number: {row!r}") from None
    if not name or not _UUID_RE.match(uuid):
        raise LauncherFormatError(f"a GPU row needs a name and a card UUID: {row!r}")
    return Gpu(index=index_number, name=name, uuid=uuid)


def parse_header(header_lines) -> tuple:
    """(tasks, gpus) from the tracked copy's header. Raises on a wrong shape."""
    tasks, gpus = [], []
    for raw in header_lines:
        line = raw.strip()
        if not line.startswith("#"):
            continue
        row = line.lstrip("#").strip()
        if row.startswith("TASK|"):
            tasks.append(_task_row(row[len("TASK|"):].strip()))
        elif row.startswith("GPU|"):
            gpus.append(_gpu_row(row[len("GPU|"):].strip()))
    if not tasks:
        raise LauncherFormatError(
            "no '# TASK|...' row in the header - the tracked copy records no "
            "logon task, so the repository cannot say how the machine starts a lane")
    if not gpus:
        raise LauncherFormatError(
            "no '# GPU|...' row in the header - the tracked copy records no cards, "
            "so a '-GpuUuid it should carry' value cannot be named")
    names = [task.name for task in tasks]
    if len(set(names)) != len(names):
        raise LauncherFormatError(
            "two '# TASK|...' rows name the same task: "
            + ", ".join(sorted(name for name in set(names) if names.count(name) > 1)))
    uuids = [gpu.uuid for gpu in gpus]
    if len(set(uuids)) != len(uuids):
        raise LauncherFormatError("two '# GPU|...' rows carry the same UUID")
    for task in tasks:
        for value in task.uuids:
            if value not in uuids:
                raise LauncherFormatError(
                    f"task {task.name!r} carries {value}, which is not one of the "
                    f"cards in the GPU block")
    return tuple(tasks), tuple(gpus)


def compare_body(tracked_body, live_lines) -> tuple:
    """(diffs, note) where diffs is [(body_index, tracked_line, live_line)].

    Line endings and a trailing newline are the one thing ignored: git stores the
    tracked copy with LF endings, and a line-ending-only difference is not a
    different decision. A changed character anywhere else is a difference.
    """
    body = list(tracked_body)
    live = list(live_lines)
    diffs = []
    for index in range(max(len(body), len(live))):
        tracked_line = body[index] if index < len(body) else ""
        live_line = live[index] if index < len(live) else ""
        if tracked_line != live_line:
            diffs.append((index, tracked_line, live_line))
    note = ""
    if len(body) != len(live):
        note = (f"the tracked copy has {len(body)} line(s) below its header and the "
                f"live file has {len(live)} - line counts differ")
    return diffs, note


# ---------------------------------------------------------------------------
#   Reading the machine (read-only)
# ---------------------------------------------------------------------------

def _run(args, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout)


def _decode(data: bytes) -> str:
    """Task Scheduler can answer in UTF-16 or the local code page; both decode."""
    if b"\x00" in data[:200]:
        try:
            return data.decode("utf-16-le").lstrip("\ufeff")
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _unescape(text: str) -> str:
    for entity, value in _ENTITIES:
        text = text.replace(entity, value)
    return text


def task_from_xml(name: str, xml: str) -> Optional[LaneTask]:
    """The lane task a task's XML describes, or None when it does not run start-lane.ps1.

    The ``-GpuUuid`` value is the point: it is what decides how many cards the
    lane may use, and it is NOT in the launcher file.
    """
    found = _ARGUMENTS.search(xml or "")
    if not found:
        return None
    arguments = _unescape(found.group(1))
    if "start-lane.ps1" not in arguments.lower():
        return None
    lane_match = _FLAG_LANE.search(arguments)
    port_match = _FLAG_PORT.search(arguments)
    context_match = _FLAG_CONTEXT.search(arguments)
    uuid_match = _FLAG_UUID.search(arguments)
    uuids = ()
    if uuid_match:
        raw = uuid_match.group(1) if uuid_match.group(1) is not None else uuid_match.group(2)
        uuids = tuple(item.strip() for item in raw.split(",") if item.strip())
    return LaneTask(
        name=name,
        lane=(lane_match.group(1) or lane_match.group(2)) if lane_match else "",
        port=int(port_match.group(1)) if port_match else 0,
        uuids=uuids,
        context=int(context_match.group(1)) if context_match else 0,
    )


def read_live_tasks(runner: Optional[Callable] = None) -> tuple:
    """(tasks, reason) for every live logon task that runs start-lane.ps1.

    ``reason`` is non-empty when the machine could not be asked (not Windows,
    ``schtasks`` missing or refusing) - that is NOT CHECKED. An empty tuple AND
    an empty reason means "the machine was asked and has no such task", which the
    caller reports as a failure when a live launcher exists.
    """
    if runner is None and sys.platform != "win32":
        return (), "schtasks exists only on Windows"
    run = runner or _run
    try:
        listed = run(["schtasks", "/query", "/fo", "csv", "/nh"])
    except (OSError, subprocess.SubprocessError) as exc:
        return (), f"schtasks could not be run here ({exc})"
    if listed.returncode != 0:
        return (), f"schtasks refused to list this PC's tasks (exit {listed.returncode})"
    names = []
    for row in csv.reader(_decode(listed.stdout).splitlines()):
        if row and row[0].lstrip("\\").startswith("Jarvis Ollama"):
            names.append(row[0].lstrip("\\"))
    tasks = []
    for name in names:
        try:
            done = run(["schtasks", "/query", "/xml", "/tn", name])
        except (OSError, subprocess.SubprocessError) as exc:
            return (), f"schtasks could not read the task {name!r} ({exc})"
        if done.returncode != 0:
            return (), f"schtasks could not read the task {name!r} (exit {done.returncode})"
        task = task_from_xml(name, _decode(done.stdout))
        if task is not None:
            tasks.append(task)
    return tuple(tasks), ""


def parse_gpu_list(text: str) -> tuple:
    """The card rows in ``nvidia-smi -L`` output, in its own order."""
    gpus = []
    for line in (text or "").splitlines():
        found = _GPU_LINE.match(line.strip())
        if found:
            gpus.append(Gpu(index=int(found.group(1)), name=found.group(2).strip(),
                            uuid=found.group(3)))
    return tuple(gpus)


def read_live_gpus(runner: Optional[Callable] = None) -> tuple:
    """(gpus, reason) for this PC's cards; reason non-empty means NOT CHECKED."""
    run = runner or _run
    try:
        done = run(["nvidia-smi", "-L"])
    except (OSError, subprocess.SubprocessError) as exc:
        return (), f"nvidia-smi is not available here ({exc})"
    if done.returncode != 0:
        return (), f"nvidia-smi exited {done.returncode}"
    gpus = parse_gpu_list(_decode(done.stdout))
    if not gpus:
        return (), "nvidia-smi listed no card"
    return gpus, ""


# ---------------------------------------------------------------------------
#   Reading the repository's lane table (no machine, no import of the backend)
# ---------------------------------------------------------------------------

def read_repo_lanes(repo_root=None) -> Optional[dict]:
    """The ``LANES`` table from ``backend/jarvis_presets.py``, or None.

    Read with ``ast`` rather than imported: this tool must stay standard-library
    only and must not import the backend's modules (which can reach a model, a
    socket or the owner's live folder). The table is the one the apps render and
    the one a preset change edits, so it is the authority on what a lane claims.
    """
    path = lane_table_path(repo_root)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "LANES"
                   for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        lanes = {}
        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            row = {}
            if isinstance(value, ast.Dict):
                for inner_key, inner_value in zip(value.keys, value.values):
                    if (isinstance(inner_key, ast.Constant)
                            and isinstance(inner_key.value, str)
                            and isinstance(inner_value, ast.Constant)):
                        row[inner_key.value] = inner_value.value
            lanes[key.value] = row
        return lanes or None
    return None


# ---------------------------------------------------------------------------
#   The lane-table comparison
# ---------------------------------------------------------------------------

def _card_claim(card, gpus) -> tuple:
    """("all", N) for "all three cards", ("one", name) for a card name.

    ``("unknown", 0)`` when there is no claim at all. "all cards" means every card
    this PC has, which is how many the tracked GPU block lists.
    """
    text = " ".join(str(card or "").split()).strip()
    if not text:
        return "unknown", 0
    found = _ALL_CARDS.match(text)
    if found:
        word = (found.group(1) or "").lower()
        count = {"two": 2, "three": 3, "four": 4}.get(word)
        if count is None:
            count = int(found.group(2))
        return "all", count
    if _ALL_CARDS_ANY.match(text):
        return "all", len(gpus)
    return "one", text


def _uuid_text(uuids) -> str:
    return ",".join(uuids) if uuids else "(none)"


def _uuids_for(count: int, gpus, name: str = "") -> str:
    """The exact ``-GpuUuid`` value a task should carry for this claim."""
    if name:
        named = [gpu for gpu in gpus if _words_in(name, gpu.name)]
        if len(named) == 1:
            return named[0].uuid
        return ""
    if count <= 0:
        return ""
    if count >= len(gpus):
        return _uuid_text(gpu.uuid for gpu in gpus)
    return _uuid_text(gpu.uuid for gpu in gpus[:count])


def _words_in(claim: str, card_name: str) -> bool:
    return " ".join(str(claim).casefold().split()) in " ".join(str(card_name).casefold().split())


def _task_for_lane(lanes_row: dict, key: str, tasks) -> Optional[LaneTask]:
    """The tracked task that runs this lane, by lane name first, then by port."""
    for task in tasks:
        if task.lane == key:
            return task
    port = lanes_row.get("port")
    if isinstance(port, int):
        for task in tasks:
            if task.port == port:
                return task
    return None


def lane_findings(lanes: dict, tasks, gpus) -> tuple:
    """(findings, notes, compared): every lane whose task cannot honour its claim.

    Only lanes that a tracked logon task runs are judged: the on-demand pooled
    lane has no task, and its "all three cards" row is about a server the app
    starts itself (no ``-GpuUuid`` pin at all), so comparing it here would invent
    a task that does not exist.
    """
    findings, notes, compared = [], [], 0
    for key in sorted(lanes):
        row = lanes[key] or {}
        card = str(row.get("card") or "").strip()
        if not card:
            continue
        task = _task_for_lane(row, key, tasks)
        if task is None:
            notes.append(f"note: lane {key!r} (port {row.get('port')}) has no logon "
                         f"task - on-demand lanes have no task grant to compare, so "
                         f"this lane is not judged here")
            continue
        compared += 1
        kind, value = _card_claim(card, gpus)
        granted = tuple(task.uuids)
        if kind == "unknown":
            continue
        if kind == "all":
            count = int(value or len(gpus) or 3)
            if len(granted) < count:
                findings.append(Finding(
                    lane=key, task=task.name,
                    problem=(f"lane {key!r} says its card is {card!r}, but the logon "
                             f"task {task.name!r} passes only {len(granted)} -GpuUuid "
                             f"({_uuid_text(granted)}), so the launcher pins "
                             f"CUDA_VISIBLE_DEVICES to {len(granted)} card(s) and the "
                             f"lane can never spread a model"),
                    should_carry=_uuids_for(count, gpus)))
            elif len(granted) > count:
                findings.append(Finding(
                    lane=key, task=task.name,
                    problem=(f"lane {key!r} says its card is {card!r}, but the logon "
                             f"task passes {len(granted)} -GpuUuid values "
                             f"({_uuid_text(granted)}), so the lane may use more cards "
                             f"than the repository describes"),
                    should_carry=_uuids_for(count, gpus)))
        else:
            name = value
            if not granted:
                findings.append(Finding(
                    lane=key, task=task.name,
                    problem=(f"lane {key!r} names the card {card!r}, but the logon "
                             f"task passes no -GpuUuid at all"),
                    should_carry=_uuids_for(1, gpus, name=card)))
                continue
            if len(granted) > 1:
                findings.append(Finding(
                    lane=key, task=task.name,
                    problem=(f"lane {key!r} names one card ({card!r}), but the logon "
                             f"task passes {len(granted)} -GpuUuid values"),
                    should_carry=_uuids_for(1, gpus, name=card)))
                continue
            pinned = next((gpu for gpu in gpus if gpu.uuid == granted[0]), None)
            if pinned is None:
                findings.append(Finding(
                    lane=key, task=task.name,
                    problem=(f"the logon task carries {granted[0]}, which is not one "
                             f"of the cards in the tracked GPU block"),
                    should_carry=_uuids_for(1, gpus, name=card)))
                continue
            named = [gpu for gpu in gpus if _words_in(card, gpu.name)]
            if not named:
                notes.append(f"note: lane {key!r} names {card!r}, which matches no card "
                             f"in the tracked GPU block - the card-identity check is "
                             f"not judged here (that is NOT a pass)")
            elif pinned.uuid not in {gpu.uuid for gpu in named}:
                findings.append(Finding(
                    lane=key, task=task.name,
                    problem=(f"lane {key!r} names the card {card!r}, but the logon "
                             f"task pins {pinned.uuid} ({pinned.name})"),
                    should_carry=_uuids_for(1, gpus, name=card)))
    return findings, notes, compared


# ---------------------------------------------------------------------------
#   The whole preflight
# ---------------------------------------------------------------------------

def _section_drift(tracked_file: Path, live_file: Path, header, body,
                   live_text: str) -> tuple:
    """(section, blockers) for the tracked-copy-vs-live-file comparison."""
    diffs, count_note = compare_body(body, live_text.splitlines())
    header_len = len(header)
    lines = [f"tracked: {tracked_file}", f"live   : {live_file}"]
    blockers = []
    if not diffs:
        lines.append("the live file matches the tracked copy line for line")
        return Section("the tracked copy vs the live launcher", PASS, lines), blockers
    lines.append(f"the tracked copy and the live file differ in {len(diffs)} line(s)")
    if count_note:
        lines.append(count_note)
    for index, tracked_line, live_line in diffs[:SHOW_DIFFS]:
        lines.append(f"tracked line {header_len + index + 1} / live line {index + 1}:")
        lines.append(f"  tracked: {_clip(tracked_line)}")
        lines.append(f"  live   : {_clip(live_line)}")
    if len(diffs) > SHOW_DIFFS:
        lines.append(f"... and {len(diffs) - SHOW_DIFFS} more differing line(s)")
    return Section("the tracked copy vs the live launcher", FAIL, lines), blockers


def _clip(line: str, width: int = 220) -> str:
    return line if len(line) <= width else line[:width] + " ..."


def _task_differences(tracked: LaneTask, live: LaneTask) -> list:
    """The fields of one task that disagree, in words."""
    diffs = []
    if tracked.lane != live.lane:
        diffs.append(f"lane: repo says {tracked.lane!r}, the PC has {live.lane!r}")
    if tracked.port != live.port:
        diffs.append(f"port: repo says {tracked.port}, the PC has {live.port}")
    if tracked.uuids != live.uuids:
        diffs.append(f"-GpuUuid: repo says {_uuid_text(tracked.uuids)}, "
                     f"the PC has {_uuid_text(live.uuids)}")
    if tracked.context != live.context:
        diffs.append(f"context: repo says {tracked.context}, the PC has {live.context}")
    return diffs


def _section_tasks(tracked_tasks, live_tasks) -> tuple:
    """(section, blockers) for the tracked logon tasks vs the live Task Scheduler."""
    title = "the tracked logon tasks vs this PC's Task Scheduler"
    if not live_tasks:
        lines = [
            "the live launcher is here, but no task whose action runs start-lane.ps1 "
            "was found - the machine does not start a lane at logon",
        ]
        blockers = [Blocker(task=task.name, should_carry=_uuid_text(task.uuids),
                            why="the repo records this logon task, and this PC has no "
                                "task running start-lane.ps1")
                    for task in tracked_tasks]
        return Section(title, FAIL, lines), blockers
    tracked_by_name = {task.name: task for task in tracked_tasks}
    live_by_name = {task.name: task for task in live_tasks}
    lines, blockers = [], []
    for name, tracked in tracked_by_name.items():
        live = live_by_name.get(name)
        if live is None:
            lines.append(f"FAIL: the repo records task {name!r}, and this PC has no "
                         f"task with that name that runs start-lane.ps1")
            blockers.append(Blocker(task=name, should_carry=_uuid_text(tracked.uuids),
                                    why="the repo's task table records a task this PC "
                                        "does not have"))
            continue
        differences = _task_differences(tracked, live)
        if differences:
            lines.append(f"FAIL: task {name!r} disagrees with the repo's record:")
            for difference in differences:
                lines.append(f"  {difference}")
            blockers.append(Blocker(task=name, should_carry=_uuid_text(tracked.uuids),
                                    why=f"the live task {name!r} differs from the repo's "
                                        f"record of it (see the lines above)"))
        else:
            lines.append(f"the repo's record of task {name!r} matches this PC "
                         f"({_uuid_text(tracked.uuids)}, port {tracked.port}, "
                         f"context {tracked.context})")
    for name in live_by_name:
        if name not in tracked_by_name:
            live = live_by_name[name]
            lines.append(f"FAIL: this PC has task {name!r}, which runs start-lane.ps1 "
                         f"and passes {_uuid_text(live.uuids)}, but the repo's task "
                         f"table does not record it")
            blockers.append(Blocker(task=name, should_carry=_uuid_text(live.uuids),
                                    why=f"the task {name!r} is not in the repo's task table"))
    if not lines:
        lines.append("no task to compare")
    return Section(title, FAIL if blockers else PASS, lines), blockers


def _section_gpus(tracked_gpus, live_gpus) -> tuple:
    """(section, blockers) for the tracked card inventory vs nvidia-smi."""
    title = "the tracked graphics cards vs this PC's nvidia-smi"
    tracked_by_uuid = {gpu.uuid: gpu for gpu in tracked_gpus}
    live_by_uuid = {gpu.uuid: gpu for gpu in live_gpus}
    lines, blockers = [], []
    for uuid, gpu in tracked_by_uuid.items():
        live = live_by_uuid.get(uuid)
        if live is None:
            lines.append(f"FAIL: the repo records {uuid} ({gpu.name}, index "
                         f"{gpu.index}) and this PC's nvidia-smi does not list it")
        elif live.index != gpu.index or live.name != gpu.name:
            lines.append(f"FAIL: the repo records {uuid} as ({gpu.name}, index "
                         f"{gpu.index}); this PC lists ({live.name}, index {live.index})")
    for uuid, live in live_by_uuid.items():
        if uuid not in tracked_by_uuid:
            lines.append(f"FAIL: this PC lists {uuid} ({live.name}, index {live.index}) "
                         f"and the repo's GPU block does not record it")
    if not lines:
        lines = [f"the tracked GPU block matches this PC: {len(tracked_gpus)} card(s), "
                 f"{', '.join(gpu.name for gpu in tracked_gpus)}"]
        return Section(title, PASS, lines), blockers
    lines.append("the tracked GPU block is stale: re-copy it from `nvidia-smi -L` and "
                 "re-copy the launcher header, then re-run this check")
    return Section(title, FAIL, lines), blockers


def _section_lanes(repo_root, tracked_tasks, tracked_gpus) -> tuple:
    """(section, findings) for the hermetic check: lane table vs tracked task grants."""
    title = "the repo's lane table vs the tracked logon tasks"
    path = lane_table_path(repo_root)
    lanes = read_repo_lanes(repo_root)
    if lanes is None:
        return Section(title, NOT_CHECKED, [
            f"not checked: no LANES table could be read from {path}",
            "the repository half of this check needs backend/jarvis_presets.py's "
            "LANES table",
        ]), []
    findings, notes, compared = lane_findings(lanes, tracked_tasks, tracked_gpus)
    lines = [f"lane table: {path}"]
    if findings:
        for finding in findings:
            lines.append(f"FAIL: {finding.problem}")
            if finding.should_carry:
                lines.append(f"  the task {finding.task!r} should carry -GpuUuid "
                             f"{finding.should_carry}")
    lines.extend(notes)
    if not findings:
        if compared:
            lines.append(f"every lane a logon task runs agrees with that task's grant "
                         f"({compared} lane(s) compared)")
        else:
            return Section(title, NOT_CHECKED, lines + [
                f"not checked: no lane in {path} names a card a tracked task runs",
            ]), []
    return Section(title, FAIL if findings else PASS, lines), findings


def preflight(repo_root=None, live_dir=None, task_reader: Optional[Callable] = None,
              gpu_reader: Optional[Callable] = None, run_machine: bool = True) -> Preflight:
    """The whole four-section check.

    ``task_reader``/``gpu_reader`` are the injection points for tests (and for a
    fixture machine): each is a no-argument callable returning ``(rows, reason)``
    exactly like ``read_live_tasks``/``read_live_gpus``. ``run_machine=False`` is
    ``--repo-only``: no live file, task or card is read.
    """
    root = Path(repo_root) if repo_root else repo_root_default()
    tracked_file = tracked_launcher(root)
    live_file = live_launcher(live_dir)
    sections, blockers = [], []

    tracked = None
    header = body = tasks = gpus = None
    if not tracked_file.is_file():
        sections.append(Section("the repository's tracked launcher", NOT_CHECKED, [
            f"not checked: no tracked launcher at {tracked_file}",
            "a checkout without the tracked copy cannot say what the machine runs",
        ]))
    else:
        try:
            text = tracked_file.read_text(encoding="utf-8", errors="replace")
            header, body = split_tracked(text)
            tasks, gpus = parse_header(header)
        except (OSError, LauncherFormatError) as exc:
            sections.append(Section("the repository's tracked launcher", FAIL, [
                f"the tracked launcher at {tracked_file} is not shaped like one: {exc}",
            ]))
        else:
            tracked = True

    # The repository-only half always runs when the tracked copy is readable: it is
    # the one section CI can prove, and it is the one that catches a lane table
    # asking for more cards than the tracked task grants.
    lane_section = None
    if tracked:
        lane_section, lane_findings_made = _section_lanes(root, tasks, gpus)
        sections.append(lane_section)
        for finding in lane_findings_made:
            blockers.append(Blocker(task=finding.task,
                                    should_carry=finding.should_carry,
                                    why=finding.problem))

    if not run_machine:
        sections.append(Section("the live launcher checks", NOT_CHECKED, [
            NOT_CHECKED_LIVE + " - --repo-only was passed, so the file, the tasks and "
            "the cards on this machine were NOT READ",
            "this mode proves the repository half only; it is NOT a pass about the "
            "machine",
        ]))
    elif tracked:
        live_text, live_reason = None, NOT_CHECKED_LIVE
        if live_file.is_file():
            try:
                live_text = live_file.read_text(encoding="utf-8", errors="replace")
                live_reason = ""
            except OSError as exc:
                live_reason = f"the live launcher could not be read ({exc})"
        if live_text is None:
            for title in ("the tracked copy vs the live launcher",
                          "the tracked logon tasks vs this PC's Task Scheduler",
                          "the tracked graphics cards vs this PC's nvidia-smi"):
                sections.append(Section(title, NOT_CHECKED, [
                    f"live path: {live_file}",
                    live_reason,
                ]))
        else:
            drift, drift_blockers = _section_drift(tracked_file, live_file, header,
                                                   body, live_text)
            sections.append(drift)
            blockers.extend(drift_blockers or [
                Blocker(task=task.name, should_carry=_uuid_text(task.uuids),
                        why="the repo's tracked launcher and the live file differ "
                            "(the lines above say where)")
                for task in (tasks if drift.status == FAIL else ())
            ])
            live_tasks, tasks_reason = (task_reader or read_live_tasks)()
            if tasks_reason:
                sections.append(Section(
                    "the tracked logon tasks vs this PC's Task Scheduler",
                    NOT_CHECKED, [f"not checked: {tasks_reason}"]))
            else:
                task_section, task_blockers = _section_tasks(tasks, live_tasks)
                sections.append(task_section)
                blockers.extend(task_blockers)
            live_gpus, gpus_reason = (gpu_reader or read_live_gpus)()
            if gpus_reason:
                sections.append(Section(
                    "the tracked graphics cards vs this PC's nvidia-smi",
                    NOT_CHECKED, [f"not checked: {gpus_reason}"]))
            else:
                gpu_section, _gpu_blockers = _section_gpus(gpus, live_gpus)
                sections.append(gpu_section)
                if gpu_section.status == FAIL:
                    blockers.extend([
                        Blocker(task=task.name, should_carry=_uuid_text(task.uuids),
                                why="the tracked GPU block is stale (see the lines above)")
                        for task in tasks
                    ])

    return Preflight(sections=sections, blockers=blockers,
                     repo_status=lane_section.status if lane_section else NOT_CHECKED)


# ---------------------------------------------------------------------------
#   The command line
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the repository's tracked lane launcher with the one "
                    "this PC runs, and the repository's lane table with the tracked "
                    "logon tasks. Read-only; changes nothing.")
    parser.add_argument("--repo-root", default="",
                        help="the repository checkout (default: this tool's parent folder)")
    parser.add_argument("--live-dir", default="",
                        help="the folder holding the live start-lane.ps1 (default: "
                             "%LOCALAPPDATA%\\JarvisOllama)")
    parser.add_argument("--repo-only", action="store_true",
                        help="read no machine at all: prove only the repository's lane "
                             "table against its tracked logon tasks (what CI can check)")
    args = parser.parse_args(argv)

    root = Path(args.repo_root) if args.repo_root else repo_root_default()
    live_dir = Path(args.live_dir) if args.live_dir else None
    verdict = preflight(repo_root=root, live_dir=live_dir,
                        run_machine=not args.repo_only)
    print("Jarvis lane launcher check - read-only: starts, stops and changes nothing")
    print(f"  repository: {root}")
    print(f"  live file : {live_launcher(live_dir)}")
    print("")
    for line in verdict.lines():
        print(line)
    if verdict.failed:
        print("")
        for line in verdict.two_step_lines():
            print(line)
    print("")
    if verdict.failed:
        print("RESULT: FAIL - the repository's launcher/lane table and what this PC "
              "runs do not agree; a one-step deploy would leave one of them wrong.")
        return 1
    if args.repo_only:
        if verdict.repo_status != PASS:
            print("RESULT: NOT CHECKED - the repository half could not be read, and "
                  "that is not a pass.")
            return 3
        print("RESULT: PASS (repository half only) - the lane table agrees with the "
              "tracked logon tasks; the live half was NOT CHECKED, so this says "
              "nothing about the machine.")
        return 0
    if verdict.not_checked:
        print("RESULT: NOT CHECKED - nothing failed, and this is not a pass: the live "
              "launcher was not available on this machine, so nothing was compared "
              "with it.")
        return 3
    print("RESULT: PASS - the tracked copy, the logon tasks, the graphics cards "
          "and the repository's lane table all agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
