"""jarvis_projects.py - Projects, steps 1 and 2 (the owner's decision of
2026-09-28, CLAUDE.md "Projects, like Claude's Projects and more"; the
design is docs/PROJECTS-DESIGN.md, and its "Build notes" say what this
first piece is and is not).

NEW MODULE, shipped whole (projects.patch adds the routes).

WHAT IT IS FOR, IN PLAIN WORDS
A project is one place for one thing the owner is working on: an app
("Jarvis Desktop", a coding project) or "run a half marathon" (a life
project). This module keeps each project's name, kind, instructions ("how
Jarvis should work on this", in the owner's words), a few pinned project
notes, its one folder (coding only), a Shareable switch (off by default),
its work list (a named list on the one scheduler), the ids of the goals it
is linked to - and its benchmarks: named measurements with dated results,
"better or worse than last time", and the points for a chart.

WHAT IS BUILT HERE, AND WHAT IS NOT (build steps 1 and 2 only)
  * Built: the projects themselves, life benchmarks (logging a number,
    results over time, better/worse, sensitive marking), the quick command
    "log 5 km run" / "I ran 5 km" (jarvis_quick.py calls quick_match() and
    quick_log() below), and coding benchmarks AS WORDS ONLY: the command's
    text is kept, marked "not runnable yet". Nothing in this file runs a
    command, opens a socket, calls a model or writes a file outside
    projects.db.
  * APPS (2026-09-29, docs/APPS-IN-PROJECTS-DESIGN.md): a coding project
    may be a Jarvis-built app - `app` names its folder under
    `<settings folder>/apps/` (jarvis_app_workspace.py), never together with
    a `folder`. Its tasks, the merge card and the routes are in
    jarvis_apps.py; this file keeps the link (the `app` column), makes or
    adopts the folder when the project is made, and never deletes it.
  * Not built: running benchmarks (the fence, build step 6), Jarvis
    changing code (`project_edit`, build steps 5 and 7 - after the 12 GB
    card is installed and measured, the owner's answer of 2026-09-28), the
    project chat CONTEXT (the `project` column on conversations, below),
    both apps' screens (step 3), and anything the Shareable switch would
    one day let go out (it is only a switch here; nothing is ever sent).
  * BUILT (2026-10-15), and it is the LABEL half of project-labelled facts
    (build step 4): a project's labelled facts - see below. The owner's
    side decided the label lives in `projects.db`, owned by this module,
    and NOT as `meta.project` on jarvis_memory.py's own row: that module is
    the application target of THREE patches (memory-safety, embedding-guard,
    bitemporal), and a fourth would fight them. What is still NOT built is
    the other half of step 4 - a fact learned in a project chat being
    labelled automatically, which cannot happen until /api/chat carries a
    project id.
  * GOALS: jarvis_goals.py is on main now, and the link is HALF built
    (corrected 2026-10-13; this note started as the cohesiveness audit's
    finding of 2026-09-29). A project lists goal ids (`goals`) on THIS side,
    and no screen sets or shows them. **A goal step's `measure`
    ({"project", "bench"}) is built**: jarvis_goals.py parses and validates it
    (`clean_plan`, ~line 349), and reads the named benchmark through
    `jarvis_projects.get().results(project, bench, 1)` (`_read_bench`,
    ~line 461); a goal that is stopped or removed drops its own spoke from the
    balance chart (`jarvis_projects.axes_drop_goal`, called from
    jarvis_goals.py ~line 474). Still to come: the goals.db `project` column
    and `GET /api/goals?project=<id>`, which is why a goal id written on a
    project here is still not checked against goals.db. The design's "one
    extra field, no second goals system" is unchanged. **This block said the
    measure was "still to come" until 2026-10-13; that had stopped being
    true.**
  * CHATS: the chat-history `project` column waits for step 4 - nothing
    can set it until /api/chat carries a project id.

WHO MAY DO WHAT, AND WHICH NEED A CARD (ARCHITECTURE section 3)
  * Creating, editing and deleting a project, its notes and its
    benchmarks, and logging a number: NO card. The owner is writing down
    their own things, like a to-do item (docs/PROJECTS-DESIGN.md section 3,
    "Life projects"). Only from the apps (the owner's tap) or, for logging,
    from the owner's own typed or spoken words through jarvis_quick.py -
    which already refuses pasted, shared and untagged messages.
  * A project's folder: it must ALREADY be on "Folders Jarvis may look in"
    (jarvis_documents.folders()), or inside one of them. Adding a folder to
    that list stays where it is - PC only, one change_own_config card
    (jarvis_documents.request_add); there is no second folder list.
    Choosing a project's folder, and writing or changing a coding
    benchmark's command, are PC-only (jarvis_owner_check.from_this_pc,
    the same check "Folders Jarvis may look in" uses): folders already are,
    and a command's words decide what would run on the PC
    (docs/PROJECTS-DESIGN.md section 6; ARCHITECTURE section 8).
  * The Shareable switch: OFF by default. Turning it ON is ONE approval
    card (change_own_config, the same action "Folders Jarvis may look in"
    uses, so jarvis_gate needs no new line); turning it OFF is instant -
    the shape of every switch that loosens a rule (CLAUDE.md, 2026-09-24).
    Even on, nothing here sends anything; each future send gets its own
    card showing the words, and never a sensitive number.
  * Sensitive numbers: a benchmark about health or money is marked
    sensitive, from its name and unit (jarvis_sensitive.topic() plus a
    short benchmark word list below, because topic() alone does not see
    "weight" or "resting heart rate"), or because the owner marked it. Its
    numbers are flagged `keep_on_screen`: never read aloud (the quick
    command's answer is `private`, so the apps keep it on screen), and
    never to be sent anywhere. The owner can mark more, and take their own
    mark off at once. A mark Jarvis made by itself from the name can come
    off too, but only with ONE card first (change_own_config, like
    Shareable ON) - because afterwards the numbers may be read aloud (the
    owner's answer of 2026-09-28: `jarvis_sensitive` reads "5k" as money).
    Renaming the benchmark or changing its unit checks the name again.

WHAT IS KEPT, AND WHERE
`projects.db` in the Jarvis settings folder, beside schedule.db and
memory.db (JARVIS_PROJECTS_DB overrides it, for the tests). The audit log
gets ids and counts only - never a name, an instruction, a note or a
number.

A PROJECT'S LABELLED FACTS (2026-10-15)
One project can label the owner's own remembered facts - "this is why I
know that" - and Brain lists them under the project with Forget: the owner's
answer of 2026-09-24, which every such list follows. The LABEL is one row in
`project_facts` here: the memory fact's id, and when it was labelled.
**The fact's words are never copied here.** They stay in memory.db, and an
app reads them from jarvis_memory's own existing read,
`GET /api/memory/used?ids=<id>,<id>,...` - which already knows how to say
"no longer in use" for a fact that was forgotten, and to leave an Off topic
out. `MAX_FACTS` is that read's own cap (100), so one project's whole list is
one call. Forget calls the memory module's OWN Forget - `MemoryStore.retire()`,
the same call `POST /api/memory/forget` makes - so the fact stops being
recalled everywhere, not only under this project. **This file removes no fact
and wipes no words**: "Erase the words" stays the separate button the owner
chose (2026-09-24). The "are you sure?" question before a Forget is the APP's
and stays - forgetting cannot be undone. There is NO approval card: the
owner's own tap on a fact they can see, the same shape as /api/memory/forget
and /api/memory/shared.

PM3 (2026-11-20): THE EXECUTION AND BRIEF BRIDGES
The plan store now meets the surfaces that already exist (the architecture
review's "PM3 - Execution Bridge"; docs/PROJECTS-DESIGN.md's build note):
  * a linked GitHub pull request's own state and CI, read through
    jarvis_github.py and stored as a PROJECTION (no card, no GitHub write);
    a merged PR is an OFFER to move the item to done, never an automatic
    write, and the move stays the existing status path with its receipt/Undo;
  * a linked jarvis_tasks.py durable job's own state, projected onto the item
    through the SAME status path (in_review, never straight to done). The Run
    Step DISPATCH itself is deliberately deferred - no production executor
    exists to hand jarvis_tasks.tick(), and a stand-in runner would move rows
    while nothing ran (docs/ARCHITECTURE.md section 8, and the decision
    fragment);
  * a morning brief (due within 48h, top 3 ready, stalled in_progress >7d,
    offers) read by jarvis_arbiter.digest();
  * a read-only daily to-do projection read by jarvis_schedule.status().
No model tool, no card class and no due date is added by any of it: the
bridges are reached by one route (POST <PATH>/<id>/sync) and by those two
reads. See docs/JARVIS-API.md section 88.9.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

import jarvis_sqlite

try:
    import jarvis_forecast as _forecast
except Exception:  # pragma: no cover - shipped beside it on the PC
    _forecast = None  # type: ignore

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

MAX_PROJECTS = 30
MAX_NAME = 60
#: "How Jarvis should work on this" - the design's ~1,500 characters. Every
#: part of a project chat's SYSTEM line has a hard limit (8K tokens on the
#: 8 GB card, docs/PROJECTS-DESIGN.md section 1).
MAX_INSTRUCTIONS = 1500
#: Project notes: the owner's own pinned lines ("the server uses port
#: 8080"), like "Always keep in mind" but per project. Small on purpose.
MAX_NOTES = 10
MAX_NOTE = 200
MAX_GOALS_LINKED = 20
MAX_BENCHMARKS = 12
MAX_BENCH_NAME = 40
MAX_UNIT = 16
MAX_COMMAND = 300
MAX_RESULTS = 5000
CHART_POINTS = 365
CHART_POINTS_MAX = 1000
#: How many of the owner's own facts one project may label. Deliberately
#: jarvis_memory.USED_MAX (100): the WORDS for a project's whole list come
#: from that module's existing read, GET /api/memory/used?ids=<id>,<id>,...
#: which takes at most that many ids - so one project is one call, and this
#: cap is checked against it by the suite (test_projects.py).
MAX_FACTS = 100
#: A number bigger than this is a typo, not a measurement.
MAX_ABS_VALUE = 1e12

KINDS = ("coding", "life")
BENCH_KINDS = ("number", "command")
BETTER = ("higher", "lower")

#: The plan store (2026-11-19, PM1): milestones, work items, typed links and
#: an append-only event log, kept in this SAME projects.db. It is additive -
#: four `CREATE TABLE IF NOT EXISTS` and seven nullable columns added through
#: the guarded ALTER block below - and it replaces nothing this file already
#: keeps (docs/JARVIS-API.md section 88.7). Nothing in this step adds a route,
#: an app screen, a card or a model tool: the three deterministic answers in
#: jarvis_quick.py are its first readers.
MAX_MILESTONE_TITLE = 120
MAX_WORK_TITLE = 120
MAX_WORK_DETAIL = 2000
MAX_PRIORITY = 9
MAX_EVENT_SUBJECT = 80
#: The states one work item may be in. A step is READY when it has not been
#: started or finished and nothing open blocks it (`ready_next()`).
#: PM3 (2026-11-20) added the two states a linked durable job passes through:
#: `waiting_approval` (the job is waiting on its own card) and `in_review` (the
#: job finished and the owner decides). Neither is READY and neither is CLOSED,
#: so an item in one of them still counts as work and still blocks what it
#: blocks - only `done`/`cancelled` close anything.
WORK_STATUSES = ("backlog", "ready", "in_progress", "waiting_approval",
                 "in_review", "done", "cancelled")
READY_STATUSES = ("backlog", "ready")
#: A work item in one of these states is never started again, and a blocker in
#: one of them no longer blocks (it is met, not waiting).
CLOSED_STATUSES = ("done", "cancelled")
#: A project in one of these states offers no ready work.
CLOSED_PROJECT_STATUSES = ("done", "archived")
MILESTONE_STATUSES = ("planned", "active", "done")
PROJECT_STATUSES = ("planned", "active", "paused", "done", "archived")
#: The typed links. `blocks` and `parent_child` order work, so they get the
#: DFS circle guard; `related` and `discovered_from` record a link only.
EDGE_KINDS = ("blocks", "parent_child", "related", "discovered_from")
ORDERING_EDGES = ("blocks", "parent_child")
#: The project columns the plan adds, in the order the ALTER block adds them.
#: All nullable on purpose: a NOT NULL column with no default is an ALTER that
#: fails, and a failed ALTER is an availability failure (docs/JARVIS-API.md
#: 88.7) - the one shape this migration must never take.
PLAN_COLUMNS = ("objective", "success_criteria", "status", "target_date",
                "linked_repo", "linked_note_path", "slug")
#: The one file the three answers name. There is no second store.
PLAN_DB = "projects.db"
#: A plan write's own refusals, in plain words (the tests quote them).
WORK_NOT_FOUND = "There is no work item with that id."
SELF_EDGE = "A work item cannot block or contain itself."
CROSS_PROJECT_EDGE = "A blocking link joins two work items in the same project."
CYCLE_EDGE = "That link would make a circle of work, so it was not saved."
EDGE_EXISTS = "That link is already recorded."

#: ---- PM2 (2026-11-20): the import/seed, checkpoints and the hub note ------
#: The import/seed reads the two stores that ALREADY hold the owner's work - a
#: goal's plan steps (`goals.db`) and a project's work list on the one scheduler
#: - and proposes rows for this store's `milestones`/`work_items`. It is
#: IDEMPOTENT: every created row's source key ("goal:<id>",
#: "goal_step:<goal>:<step>", "todo:<id>") is written into the append-only
#: `project_events` log, so a second run finds it and creates nothing new. It
#: INVENTS NOTHING: a goal step's `by` is the owner's rough label ("before
#: winter"), never a calendar date, so the imported item stays undated; a
#: scheduler to-do that really has its own due date imports that date unchanged.
SEED_EVENT = "plan_seeded"
MAX_SEED_ITEMS = 200
#: A decomposed plan is kept as short as a goal's own plan: a card the owner
#: reads must stay readable, and a long plan was the measured failure mode.
MAX_PLAN_MILESTONES = 9
MAX_PLAN_ITEMS = 30
#: A checkpoint/reflection line is the owner's (or Jarvis's) own short lesson.
MAX_CHECKPOINT = 500
CHECKPOINT_KINDS = ("checkpoint", "reflection")
#: The one folder a hub note is written into when the project names no path.
HUB_FOLDER = "Projects"
HUB_NOTE_WORDS = ("This is a one-way copy of the project. Jarvis keeps the project "
                  "in its own store on this PC; edit it there, not here.")
HUB_MAX_BYTES = 64 * 1024
SEED_NOTHING = ("Nothing to import: no goal's step or work-list item can be "
                "attached to a project yet.")
SEED_ALL_DONE = "Everything from your goals and work lists is already in the plan."

#: ---- PM3 (2026-11-20): the execution and brief bridges -------------------
#: The owner-approved PM3 spec (the architecture review's "PM3 - Execution
#: Bridge"; docs/PROJECTS-DESIGN.md's build notes): the plan store now meets
#: the surfaces that already exist - the read-only GitHub reader, the durable
#: `jarvis_tasks.py` job list, the morning digest, the daily to-do list and the
#: one-way hub note. **This file still RUNS nothing.** The Run Step dispatch
#: ("start this work item as a durable job") is deliberately deferred: the
#: only real step executor in this product belongs to a chat turn, and
#: `jarvis_tasks.tick()` has no production caller by its own audit - building
#: a background runner here would be the half-built runner the owner's brief
#: forbids. What IS built is the LINK, and the status projection below.
#: The executor values a work item can carry (the review's `executor` column):
#: the owner does it, or one of the three ways Jarvis may. Nothing here starts
#: any of them.
EXECUTORS = ("owner", "jarvis_local", "jarvis_cloud", "jarvis_job")
#: A linked GitHub PR's read-only projection. `merged` is the state whose
#: OFFER is surfaced - never an automatic status write.
PR_STATES = ("open", "merged", "closed")
CI_STATES = ("green", "running", "failed", "unknown")
#: The numbers the owner-approved brief names: the top THREE ready items (the
#: same cap the spoken/phone answer already keeps, `jarvis_quick.
#: _MAX_NEXT_ITEMS`), work due within 48 hours, and an in_progress item
#: untouched for more than seven days.
BRIEF_READY_MAX = 3
DUE_SOON_HOURS = 48
STALLED_DAYS = 7
#: Caps so the morning brief and the daily projection stay small reads, never
#: a second listing of the whole store.
BRIEF_DUE_MAX = 12
BRIEF_STALLED_MAX = 12
DAILY_MAX = 60
#: A work item's own refusals for the two links, in plain words.
LINK_NO_TASK = "There is no job with that id in the task list."
LINK_NO_PR = "A pull request number is a whole number from 1."
#: What the merged-PR offer says. It is an offer: the move to done is the
#: owner's own status change and keeps its normal receipt and Undo.
PR_MERGED_OFFER_WORDS = ("Pull request #{pr} was merged. Move \"{title}\" to done? "
                         "Nothing has changed yet - say done, or tap it, and the "
                         "usual Undo is in your receipts.")
#: What a durable job's own state means for the work item linked to it. A
#: finished job goes to `in_review`, NEVER to `done`: the owner decides.
TASK_STATE_TO_WORK = {"queued": "in_progress", "running": "in_progress",
                      "waiting_approval": "waiting_approval",
                      "waiting_input": "waiting_approval",
                      "succeeded": "in_review"}
#: The columns PM3 adds to `work_items` and the SQLite type each needs on an
#: older projects.db. All NULLABLE on purpose - the same migration rule the
#: plan's project columns keep: `ALTER TABLE ... ADD COLUMN x TEXT NOT NULL`
#: with no default raises, and a failed ALTER is an availability failure.
_WORK_COLUMNS = (
    ("executor", "TEXT"),
    ("linked_task_id", "TEXT"),
    ("linked_pr_number", "INTEGER"),
    ("linked_pr_state", "TEXT"),
    ("linked_ci_status", "TEXT"),
)
#: The names only, for `_missing_schema()` and the guarded ALTER below.
WORK_COLUMNS = tuple(name for name, _type in _WORK_COLUMNS)

#: The card this module raises: turning Shareable ON, and taking an
#: automatic private mark off a benchmark. The same action "Folders Jarvis
#: may look in" raises, so the gate needs no new line.
CARD_ACTION = "change_own_config"

TITLE = "Projects"
EMPTY = "No projects yet."
NOT_RUNNABLE = ("Running a benchmark's command comes in a later step - nothing runs yet. "
                "The command is kept, word for word.")
PC_ONLY_FOLDER = ("A project's folder is chosen on the PC only, from \"Folders Jarvis may "
                  "look in\".")
PC_ONLY_COMMAND = "A benchmark's command is written on the PC only."
SHARE_WAITING = "Waiting for your yes on the approval card."
KEEP_ON_SCREEN = "Health or money: kept on screen, never read aloud or sent anywhere."
#: A project's labelled facts (2026-10-15). The list shows IDS only; the
#: words come from jarvis_memory's own GET /api/memory/used.
EMPTY_FACTS = "No facts are labelled with this project yet."
NO_SUCH_FACT = "There is no remembered fact with that id."
FACT_NOT_CURRENT = ("That fact has been forgotten or had its words erased, so a project "
                    "cannot label it.")
FACT_NOT_LABELLED = "This project does not label that fact."
MEMORY_UNAVAILABLE = ("The memory layer is not importable here, so a project's facts "
                      "cannot be worked out.")

_ID = re.compile(r"[0-9a-f]{32}")
#: A durable job's id, as `jarvis_tasks.py` writes it: `uuid4().hex` for a job
#: the owner started, or a sha256 hex for one built from a plan key (64). Both
#: are lowercase hex and nothing else, so a raw string is never put in SQL.
_TASK_ID = re.compile(r"[0-9a-f]{32}|[0-9a-f]{64}")
#: A memory fact id as it arrives: a number in a body, the same digits as
#: text in a path (`.../facts/7/forget`). At most 18 digits, so an id cannot
#: be a number SQLite would have to round.
_FACT_ID = re.compile(r"[0-9]{1,18}")
APP_ONLY_WORDS = "This project's files are its app."
APP_CHOSEN_WORDS = "An app is chosen when the project is made."
APP_AND_FOLDER_WORDS = "A project has a folder or an app, not both."


class NoSuchApp(LookupError):
    """An app folder that does not exist (a 404 with its own sentence)."""


class Unavailable(Exception):
    """git is missing or stuck: a 503 with the sentence (nothing typed was wrong)."""


class FactGone(LookupError):
    """A labelled fact that cannot be labelled, or a fact a project does not
    label. `status` is 404 (no such fact, or this project does not label it)
    or 409 (the fact is there but no longer current - already forgotten, or
    its words were erased), so the app can say which in plain words."""
    def __init__(self, message: str, status: int = 404):
        super().__init__(message)
        self.status = int(status)


_GOAL_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# --------------------------------------------------------------------------
#   Where, the gate, the clock - replaceable, so the tests open nothing
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def db_path() -> Path:
    env = os.environ.get("JARVIS_PROJECTS_DB")
    return Path(env) if env else _config_dir() / "projects.db"


def _audit(event: str, detail: dict) -> None:
    # Ids and counts only. Never a name, an instruction, a note or a number.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-projects-card", daemon=True).start()


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        # Cannot tell: not this PC, so a PC-only change is refused (fail
        # closed), exactly as jarvis_documents._from_this_pc does.
        return False


def _allowed_folders() -> list:
    """"Folders Jarvis may look in" - the ONE list (jarvis_documents.py).
    Without that module, none: a project folder cannot be chosen."""
    try:
        import jarvis_documents
        return list(jarvis_documents.folders())
    except Exception:
        return []


def _protected(path: str) -> bool:
    try:
        import jarvis_documents
        return bool(jarvis_documents.protected(path))
    except Exception:
        return True


# --------------------------------------------------------------------------
#   Checking what the owner typed
# --------------------------------------------------------------------------


def _text(value, limit: int, what: str, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{what} must be text")
    t = " ".join(value.split()) if "\n" not in value else value.strip()
    if required and not t:
        raise ValueError(f"{what} cannot be empty")
    if len(t) > limit:
        raise ValueError(f"{what} is {len(t)} characters - at most {limit}")
    return t


def _one_line(value, limit: int, what: str, *, required: bool = False) -> str:
    if value is not None and isinstance(value, str) and ("\n" in value or "\r" in value):
        raise ValueError(f"{what} is one line")
    return _text(value, limit, what, required=required)


def clean_notes(notes) -> list:
    if notes is None:
        return []
    if not isinstance(notes, list):
        raise ValueError("notes are a list of short lines")
    out = []
    for n in notes:
        line = _one_line(n, MAX_NOTE, "a project note")
        if line:
            out.append(line)
    if len(out) > MAX_NOTES:
        raise ValueError(f"a project keeps at most {MAX_NOTES} notes")
    return out


def clean_goals(goals) -> list:
    """Goal ids from jarvis_goals.py. Kept as given; not yet checked against
    goals.db (the goals.db `project` column and the `GET /api/goals?project=`
    filter are still to come; see the module note)."""
    if goals is None:
        return []
    if not isinstance(goals, list):
        raise ValueError("goals are a list of goal ids")
    out = []
    for g in goals:
        if not isinstance(g, str) or not _GOAL_ID.fullmatch(g):
            raise ValueError("a goal id is 1 to 64 letters, digits, - or _")
        if g not in out:
            out.append(g)
    if len(out) > MAX_GOALS_LINKED:
        raise ValueError(f"a project links at most {MAX_GOALS_LINKED} goals")
    return out


def clean_work_list(name) -> Optional[str]:
    """A named list on the one scheduler (jarvis_schedule.list_key), or None
    for no work list. The to-do list itself cannot be a project's list."""
    if name is None or (isinstance(name, str) and not name.strip()):
        return None
    if not isinstance(name, str):
        raise ValueError("a work list's name is text")
    import jarvis_schedule
    key = jarvis_schedule.list_key(name)
    if key is None:
        raise ValueError("the to-do list itself cannot be a project's work list - "
                         "give it a name, like \"garden\"")
    return key


def _default_work_list(name: str) -> Optional[str]:
    try:
        return clean_work_list(name)
    except Exception:
        return None


def _clean_date(value) -> Optional[str]:
    """A day written YYYY-MM-DD, or None. A made-up day is refused, never
    guessed into one (the plan store has no business inventing a date)."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        time.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("a date is a day written YYYY-MM-DD") from None
    return text


def _clean_priority(value) -> Optional[int]:
    """0 to 9, or None. Lower runs first (`ready_next()` orders by it)."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"a priority is a whole number from 0 to {MAX_PRIORITY}")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"a priority is a whole number from 0 to {MAX_PRIORITY}") from None
    if not 0 <= number <= MAX_PRIORITY:
        raise ValueError(f"a priority is a whole number from 0 to {MAX_PRIORITY}")
    return number


def _clip(text, limit: int) -> str:
    """The source's own words, shortened to fit one line. Truncation is marked
    with "...", so a shortened import can never pass for the owner's whole
    sentence."""
    line = " ".join(str(text or "").split())
    if len(line) <= limit:
        return line
    return line[: max(0, limit - 3)].rstrip() + "..."


def _safe_note_name(name: str) -> str:
    """A file name safe inside an Obsidian vault, from a project's name."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(name or "")).strip(" .")
    return clean or "project"


#: The ONE ready-work condition, shared by `ready_next()` and the counts in
#: `plan_counts()` so the two cannot disagree about what is ready. A work item
#: is ready when it has not been started or finished, its project is not
#: closed, and no OPEN `blocks` link points at it.
_READY_WHERE = (
    "w.status IN ('backlog', 'ready') "
    "AND (p.status IS NULL OR p.status NOT IN ('done', 'archived')) "
    "AND NOT EXISTS (SELECT 1 FROM work_edges e JOIN work_items b ON b.id = e.src "
    "                WHERE e.kind = 'blocks' AND e.dst = w.id "
    "                  AND b.status NOT IN ('done', 'cancelled'))")

#: The ONE blocked condition: an open work item with at least one open
#: `blocks` link pointing at it. Used by the reads that name blockers.
_BLOCKED_WHERE = (
    "w.status NOT IN ('done', 'cancelled') "
    "AND EXISTS (SELECT 1 FROM work_edges e JOIN work_items b ON b.id = e.src "
    "            WHERE e.kind = 'blocks' AND e.dst = w.id "
    "              AND b.status NOT IN ('done', 'cancelled'))")

#: How `ready_next()` orders: lower priority first, then the earlier day, then
#: the one written first. NULLS LAST both ways - an item with no priority or
#: no date is not "priority zero" and not "due at the epoch".
_READY_ORDER = ("w.priority IS NULL, w.priority, w.due_date IS NULL, w.due_date, "
                "w.created, w.id")


def _real(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def _inside(root: str, path: str) -> bool:
    try:
        return (os.path.commonpath([os.path.normcase(root), os.path.normcase(path)])
                == os.path.normcase(root))
    except ValueError:
        return False


def check_folder(path, allowed: Optional[list] = None) -> str:
    """The real place of `path` when it is one of "Folders Jarvis may look
    in", or a folder inside one of them. ValueError, in words, otherwise."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("choose a folder from \"Folders Jarvis may look in\"")
    real = _real(path.strip())
    listed = _allowed_folders() if allowed is None else list(allowed)
    if not any(_inside(_real(f), real) for f in listed):
        raise ValueError("that folder is not on \"Folders Jarvis may look in\" - add it "
                         "there first, on the PC (Settings)")
    if not os.path.isdir(real):
        raise ValueError("that folder does not exist on this PC")
    if _protected(real):
        raise ValueError("that folder is one Jarvis never looks in")
    return real


def _value(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError("a number, like 5 or 72.5")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError("a number, like 5 or 72.5")
    if not math.isfinite(f) or abs(f) > MAX_ABS_VALUE:
        raise ValueError("that number is too big to be a measurement")
    return f


def _opt_value(v) -> Optional[float]:
    return None if v is None else _value(v)


# --------------------------------------------------------------------------
#   Sensitive: health or money
# --------------------------------------------------------------------------

#: What jarvis_sensitive.topic() does not see in a benchmark's short name
#: (checked 2026-09-28: "weight", "body weight", "resting heart rate",
#: "calories", "monthly spending" all came back ""). Whole words only.
_HEALTH_WORDS = re.compile(
    r"(?<![a-z])(?:weight|weigh|weighed|bmi|body ?fat|fat ?%|waist|heart ?rate|pulse|hrv|bpm"
    r"|blood|glucose|sugar|cholesterol|calories|calorie|kcal|sleep|slept|mood|anxiety|pain"
    r"|medication|meds|dose|insulin|symptoms?|alcohol|drinks|cigarettes|smoking|mmhg"
    r"|mg/dl|mmol|period|fertility|pregnan\w*)(?![a-z])")
_MONEY_WORDS = re.compile(
    r"(?<![a-z])(?:money|savings?|saved|spend|spending|spent|budget|income|salary|wages?|pay"
    r"|debts?|loans?|balance|net ?worth|rent|bills|expenses|investments?|portfolio|pension"
    r"|dollars?|usd|gbp|eur|euros?|quid|bucks|pounds sterling)(?![a-z])|[$£€]")


def auto_sensitive(name: str, unit: str = "") -> str:
    """"health", "money", another topic jarvis_sensitive names, or "" - from
    the benchmark's own name and unit, never the numbers. No model."""
    words = f"{name or ''} {unit or ''}".strip()
    if not words:
        return ""
    low = words.lower()
    if _HEALTH_WORDS.search(low):
        return "health"
    if _MONEY_WORDS.search(low):
        return "money"
    try:
        import jarvis_sensitive
        t = jarvis_sensitive.topic(words)
    except Exception:
        t = ""
    return t or ""


def marks(name: str, unit: str, owner, cleared) -> dict:
    """Both private marks of one benchmark, worked out the same way
    everywhere (the view, the quick command): {"auto": the topic the name
    looks like, "auto_holds": that topic unless the owner took it off with
    a card, "owner": the owner's own mark, "sensitive": either holds}.
    `cleared` is the topic the owner's yes took off; a different topic
    (after a rename) holds again."""
    auto = auto_sensitive(name, unit)
    holds = auto if auto and (cleared or "") != auto else ""
    own = bool(owner)
    return {"auto": auto, "auto_holds": holds, "owner": own,
            "sensitive": bool(holds) or own}


# --------------------------------------------------------------------------
#   A project's labelled facts (2026-10-15) - the bridge to jarvis_memory
# --------------------------------------------------------------------------
#
# WHAT IS HERE, AND WHAT IS DELIBERATELY NOT
#
# The label (a fact id, and when) lives in `project_facts`, in THIS module's
# own projects.db. The fact itself lives in memory.db, which jarvis_memory.py
# owns - and that module is the application target of three patches
# (memory-safety, embedding-guard, bitemporal), which is why the label is not
# a fourth column on it.
#
# So this module does exactly two things with the memory layer, and neither
# of them is reading a fact's words:
#
#   * `_fact_state()` asks whether one fact is THERE and still CURRENT, so a
#     label never points at something that can no longer be recalled, and the
#     project's Forget can tell "forgot it" from "there was nothing left".
#   * `_forget_fact()` calls the memory module's OWN Forget -
#     `MemoryStore.retire()`, the same call `POST /api/memory/forget` makes.
#
# The WORDS are never read here: the apps ask jarvis_memory's own existing
# read, `GET /api/memory/used?ids=...`, which is the route that already knows
# how to show a forgotten fact as "no longer in use" and to leave an Off topic
# out. `test_topics_leaks.py`'s list of every module that reads facts still
# says of this file "reads no fact", and a check in test_projects.py holds
# that line: no SQL on the facts table, and no `store().search(` anywhere here.

def _fact_id(value) -> int:
    """The whole number above 0 a memory fact id is.

    A string of digits is accepted too, because the project's Forget carries
    its id in the PATH (`.../facts/7/forget`), where it is always text - the
    body's `{"id": 7}` is a number the other way. A `True` is refused even
    though bool is an int in Python, and `"id": true` is never a fact.
    ValueError, in words, otherwise - the refusal jarvis_memory's `shared()`
    makes for a non-integer id, in this file's words."""
    if isinstance(value, bool):
        raise ValueError("a fact id is a whole number, like 12")
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, int):
        text = str(value)
    else:
        raise ValueError("a fact id is a whole number, like 12")
    if not _FACT_ID.fullmatch(text):
        raise ValueError("a fact id is a whole number, like 12")
    fid = int(text)
    if fid <= 0:
        raise ValueError("a fact id is a whole number above 0")
    return fid


def _memory_store():
    """jarvis_memory's one open store, or None when that module is not here
    (the feature is then switched off, never broken - the shape every other
    optional module in this file has, like jarvis_forecast).

    This is the module's own `store()`: it caches the one store, so this is
    not a fresh MemoryStore per request, and it reads memory.db where it
    lives. Nothing here is a second memory database and nothing here writes
    a fact."""
    try:
        import jarvis_memory
        return jarvis_memory.store()
    except Exception:
        return None


def _fact_state(fid: int) -> dict:
    """{"found", "current"} for ONE fact, from jarvis_memory's own store.

    `current` is the rule every reader uses (`valid_to` empty or still ahead,
    and the words not erased) - the same test `shared()` and `used_view()`
    make. **No words are read here**: only the two columns that decide it.

    Unavailable, with the sentence, when the memory layer is not importable
    or will not answer: there is nothing to label then, and a label that
    pointed at nothing would be a list the owner cannot act on. Asking the
    memory layer is the point - the owner's own fact is the thing being
    labelled, and this module does not guess at another module's data."""
    store = _memory_store()
    if store is None:
        raise Unavailable(MEMORY_UNAVAILABLE)
    try:
        row = store.get(int(fid))
    except Exception as exc:
        raise Unavailable(f"the memory layer could not be read "
                          f"({type(exc).__name__})") from exc
    if row is None:
        return {"found": False, "current": False}
    erased = row.get("erased_at")
    valid_to = row.get("valid_to")
    current = erased is None and (valid_to is None or float(valid_to) > time.time())
    return {"found": True, "current": bool(current)}


def _forget_fact(fid: int) -> bool:
    """The memory module's OWN Forget for one fact: `MemoryStore.retire()`,
    exactly the call `POST /api/memory/forget` makes, and the only removal
    this file causes.

    Never a delete and never a word wiped: `retire()` keeps the row and marks
    it, which is what every "Forget" in Jarvis means (CLAUDE.md, 2026-09-24);
    "Erase the words" is `erase()` and stays its own button. False when there
    was nothing left to forget - an already-forgotten fact, or one whose id
    is not there at all, which `retire()` reports as "no row matched".

    Unavailable, in words, when the memory layer will not answer: the caller
    has already taken one label off, and it must be able to say plainly that
    the fact itself was NOT forgotten, rather than reporting a success the
    rest of Jarvis would contradict."""
    store = _memory_store()
    if store is None:
        raise Unavailable(MEMORY_UNAVAILABLE)
    try:
        return bool(store.retire(int(fid)))
    except Exception as exc:
        raise Unavailable(f"the memory layer refused to forget it "
                          f"({type(exc).__name__})") from exc


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
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
CREATE TABLE IF NOT EXISTS benchmarks (
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
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    bench TEXT NOT NULL,
    value REAL NOT NULL,
    at REAL NOT NULL,
    source TEXT NOT NULL,
    logged REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS results_by_bench ON results (bench, at);
CREATE INDEX IF NOT EXISTS results_by_at ON results (at);
-- The owner's balance chart (JARVIS-API section 105):
-- 3 to 8 rows, in the order drawn. kind "bench" (ref = benchmark id) or
-- "goal" (ref = goal id). `label` is the owner's own name for the spoke, or
-- '' for the default. No numbers and no words of a benchmark live here.
CREATE TABLE IF NOT EXISTS balance_axes (
    position INTEGER NOT NULL,
    kind TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS bench_by_project ON benchmarks (project);
-- A project's labelled facts (2026-10-15): the LABEL, and nothing else -
-- the memory fact's id and when it was labelled. A fact's words are never
-- copied here (they stay in memory.db, read through jarvis_memory's own
-- GET /api/memory/used), nothing here is a second way to save a fact, and
-- no reader of this table ever touches a fact's text. The pair is the key:
-- labelling the same fact twice is one row.
CREATE TABLE IF NOT EXISTS project_facts (
    project TEXT NOT NULL,
    fact INTEGER NOT NULL,
    created REAL NOT NULL,
    PRIMARY KEY (project, fact)
);
CREATE INDEX IF NOT EXISTS project_facts_by_fact ON project_facts (fact);
-- The plan store (2026-11-19, PM1; docs/JARVIS-API.md section 88.7). Four NEW
-- tables appended after the five this file already had: a milestone a project
-- works towards, a work item that can be started, a typed link between two
-- items, and an append-only log of what changed. Additive only: every table is
-- `CREATE TABLE IF NOT EXISTS`, no existing table is rebuilt, no column of an
-- existing table is dropped or renamed, and no foreign key is declared (this
-- file keeps that shape everywhere - `PRAGMA foreign_keys` is never turned on
-- here). Ids are 32-hex, exactly like a project's or a benchmark's.
CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    due_date TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    changed REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS milestones_by_project ON milestones (project, position);
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    milestone TEXT,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'backlog',
    priority INTEGER,
    due_date TEXT,
    created REAL NOT NULL,
    changed REAL NOT NULL,
    -- PM3 (2026-11-20), appended so a migrated file and a new file have the
    -- same column order. All NULLABLE: an older projects.db gains them with
    -- the guarded ALTER below and nothing it already holds changes.
    executor TEXT,
    linked_task_id TEXT,
    linked_pr_number INTEGER,
    linked_pr_state TEXT,
    linked_ci_status TEXT
);
CREATE INDEX IF NOT EXISTS work_items_by_project ON work_items (project, status, priority);
CREATE TABLE IF NOT EXISTS work_edges (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    kind TEXT NOT NULL,
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS work_edges_once ON work_edges (kind, src, dst);
CREATE INDEX IF NOT EXISTS work_edges_by_dst ON work_edges (kind, dst);
CREATE INDEX IF NOT EXISTS work_edges_by_src ON work_edges (kind, src);
-- Append-only: an event is only ever INSERTed. The trigger refuses an UPDATE
-- outright, and this file exposes no way to rewrite or remove one event. A
-- project's own delete takes its history with it, exactly as it already takes
-- its benchmarks (2026-11-19). Ids and transitions only - a title, a name or a
-- number is never copied into this table.
CREATE TABLE IF NOT EXISTS project_events (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    at REAL NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS project_events_by_project ON project_events (project, at);
CREATE TRIGGER IF NOT EXISTS project_events_append_only
BEFORE UPDATE ON project_events
BEGIN
    SELECT RAISE(ABORT, 'project_events is append-only');
END;
"""

#: Every table, index and trigger `_db()` ensures. Kept beside `_SCHEMA` so
#: `_missing_schema()` can answer "would opening this file change it at all?"
#: BEFORE one schema statement runs. That answer is what decides whether the
#: pre-migration backup is written, so an up-to-date database never grows a
#: trail of backup copies.
_SCHEMA_TABLES = ("projects", "benchmarks", "results", "balance_axes",
                  "project_facts", "milestones", "work_items", "work_edges",
                  "project_events")
_SCHEMA_INDEXES = ("results_by_bench", "results_by_at", "bench_by_project",
                   "project_facts_by_fact", "milestones_by_project",
                   "work_items_by_project", "work_edges_once", "work_edges_by_dst",
                   "work_edges_by_src", "project_events_by_project",
                   "projects_by_app")
_SCHEMA_TRIGGERS = ("project_events_append_only",)
#: The columns `_db()` adds to the two tables an older build could have made.
_SCHEMA_OLD_COLUMNS = {
    "projects": ("app", "auto_route_cloud") + PLAN_COLUMNS,
    "benchmarks": ("auto_cleared",),
    # PM3 (2026-11-20): the work-item link/projection columns. An old file
    # that already has `work_items` (a PM1/PM2 install) gains them, and the
    # pre-migration backup runs first exactly as it does for the plan columns.
    "work_items": WORK_COLUMNS,
}


def _migration_backup(source, path: Path) -> None:
    """Copy the open database to `path` through SQLite's own backup API.

    Module-level on purpose: a test can replace it with one that fails, and
    prove that the migration then does not run at all."""
    dest = sqlite3.connect(str(path))
    try:
        source.backup(dest)
    finally:
        dest.close()


def _missing_schema(c: sqlite3.Connection) -> list:
    """What this file does not have yet, asked WITHOUT changing anything.

    An empty list means the migration has nothing to do - so no backup is
    written and no earlier copy is left behind. It reads `sqlite_master` and
    `PRAGMA table_info` only: no CREATE, no ALTER, no write."""
    have = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type IN ('table', 'index', 'trigger')").fetchall()}
    missing = [name for name in _SCHEMA_TABLES + _SCHEMA_INDEXES + _SCHEMA_TRIGGERS
               if name not in have]
    for table, columns in _SCHEMA_OLD_COLUMNS.items():
        if table not in have:
            continue
        present = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        missing.extend(f"{table}.{column}" for column in columns
                       if column not in present)
    return missing


def _new_id() -> str:
    return uuid.uuid4().hex


def _folder_name(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] or path


def _num_words(v: float) -> str:
    """72.5 -> "72.5", 5.0 -> "5", 10000 -> "10000"."""
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _with_unit(v: float, unit: str) -> str:
    n = _num_words(v)
    if not unit:
        return n
    if unit in ("$", "£", "€"):
        return f"{unit}{n}"
    if unit == "%":
        return f"{n}%"
    return f"{n} {unit}"


def _workspace():
    import jarvis_app_workspace
    return jarvis_app_workspace


def _app_view(app: str, *, full: bool) -> dict:
    """The `app` object of a project view (jarvis_apps builds it: the list
    gets the short form, one project the whole)."""
    try:
        import jarvis_apps
        return jarvis_apps.full(app) if full else jarvis_apps.summary(app)
    except Exception:
        return {"name": app, "type": "", "tasks": 0, "merge_waiting": False}


class Projects:
    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time):
        self.path = Path(path) if path is not None else db_path()
        self.clock = clock
        self._lock = threading.RLock()
        self._ready = False

    # ---- plumbing -----------------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # jarvis_sqlite.connect, not sqlite3.connect: the connection is CLOSED
        # when its `with` block ends, not left to the collector - a leaked
        # handle is what made projects.db undeletable on the Windows runner
        # (2026-10-08, the same bug jarvis_schedule.py fixed the day before).
        # One shared copy of the class now, in jarvis_sqlite.py.
        c = jarvis_sqlite.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        if not self._ready:
            # THE PRE-MIGRATION BACKUP COMES FIRST (2026-11-19, ruling 5.2).
            # The guarded schema below is additive and was proved on a copy of
            # the owner's real file, but "additive" is not the same promise as
            # "a copy of the file before this program touched it exists". So an
            # EXISTING database that really is about to gain something gets one
            # `projects.db.before-migrate-<stamp>` copy through SQLite's own
            # backup API, before the first CREATE/ALTER. An up-to-date database
            # needs nothing, so it writes nothing; a brand-new file has no rows
            # to protect, so it writes nothing either. A backup that cannot be
            # written REFUSES the migration (it raises here, before any schema
            # statement) rather than proceeding unprotected.
            missing = _missing_schema(c)
            if missing:
                self._backup_before_migration(c, missing)
            c.executescript(_SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(benchmarks)").fetchall()}
            if "auto_cleared" not in cols:
                # A projects.db from build steps 1 and 2, before an automatic
                # mark could be taken off.
                c.execute("ALTER TABLE benchmarks ADD COLUMN auto_cleared TEXT")
            pcols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
            if "app" not in pcols:
                # A projects.db from before apps joined Projects (2026-09-29).
                c.execute("ALTER TABLE projects ADD COLUMN app TEXT")
            if "auto_route_cloud" not in pcols:
                # A projects.db from before Project Mode (step 4). OFF is the
                # default here for the same reason it is the default everywhere:
                # a database written by an older build must not come back with a
                # loosening already on.
                c.execute("ALTER TABLE projects ADD COLUMN auto_route_cloud "
                          "INTEGER NOT NULL DEFAULT 0")
            # The plan store's project fields (2026-11-19, PM1). Each one is
            # NULLABLE, and that is the rule this migration keeps rather than a
            # style: `ALTER TABLE ... ADD COLUMN x TEXT NOT NULL` with no
            # default raises OperationalError and changes nothing, so an older
            # projects.db would fail to open rather than gain a column. A
            # nullable column always applies. If an ALTER does raise, the
            # exception leaves `_ready` False and every later call retries -
            # "cannot read projects" is the honest answer, never a wrong one.
            for column in PLAN_COLUMNS:
                if column not in pcols:
                    c.execute(f"ALTER TABLE projects ADD COLUMN {column} TEXT")
            # PM3 (2026-11-20): the work-item bridge columns. The table itself
            # either was just created with them (a new or PM1 file) or came
            # from a build that had it without them; either way each missing
            # one is a NULLABLE ALTER, and a file that already has them gets
            # nothing - so a second open leaves no schema churn at all.
            wcols = {r[1] for r in c.execute("PRAGMA table_info(work_items)").fetchall()}
            for column, kind in _WORK_COLUMNS:
                if column not in wcols:
                    c.execute(f"ALTER TABLE work_items ADD COLUMN {column} {kind}")
            # One project per app folder. After the column exists, so an old
            # file gets the column first.
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS projects_by_app ON projects (app) "
                      "WHERE app IS NOT NULL")
            c.commit()
            self._ready = True
        return c

    def _backup_before_migration(self, c, missing: list) -> Optional[Path]:
        """Copy the database to `projects.db.before-migrate-<stamp>` before the
        first schema statement (2026-11-19, ruling 5.2).

        Called only when `_missing_schema()` said the file would really change.
        A brand-new file (no tables at all) has nothing to protect and gets no
        copy. A copy that cannot be written raises `sqlite3.OperationalError`
        BEFORE anything is altered, so the migration refuses rather than
        running without a way back; any half-written copy is removed first.
        The name never ends in `.db`, so `jarvis_backup.py`'s list of source
        databases is unchanged and the file is not mistaken for a store."""
        try:
            tables = int(c.execute("SELECT COUNT(*) FROM sqlite_master "
                                   "WHERE type = 'table'").fetchone()[0])
        except sqlite3.Error:
            tables = 0
        if not tables:
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.clock()))
        backup = self.path.with_name(self.path.name + ".before-migrate-" + stamp)
        n = 1
        while backup.exists():
            n += 1
            backup = self.path.with_name(self.path.name + ".before-migrate-"
                                         + stamp + "-" + str(n))
        try:
            _migration_backup(c, backup)
        except Exception as exc:           # noqa: BLE001 - refuse, do not proceed
            try:
                backup.unlink()
            except OSError:
                pass
            raise sqlite3.OperationalError(
                f"cannot write the pre-migration backup {backup.name} "
                f"({type(exc).__name__}: {exc}); nothing was changed") from exc
        _audit("projects.migrate.backup", {"missing": len(missing)})
        return backup

    def exists(self) -> bool:
        """Is there a projects.db at all? The quick command asks this first,
        so an ordinary chat message never creates one."""
        return self.path.is_file()

    def _project_row(self, c, pid: str):
        if not isinstance(pid, str) or not _ID.fullmatch(pid):
            raise KeyError(pid)
        r = c.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if r is None:
            raise KeyError(pid)
        return r

    def _bench_row(self, c, pid: str, bid: str):
        if not isinstance(bid, str) or not _ID.fullmatch(bid):
            raise KeyError(bid)
        r = c.execute("SELECT * FROM benchmarks WHERE id = ? AND project = ?",
                      (bid, pid)).fetchone()
        if r is None:
            raise KeyError(bid)
        return r

    # ---- views --------------------------------------------------------------------

    def _bench_view(self, c, b, *, points: int = 0) -> dict:
        m = marks(b["name"], b["unit"], b["owner_sensitive"], b["auto_cleared"])
        auto, owner, sensitive = m["auto_holds"], m["owner"], m["sensitive"]
        rows = c.execute("SELECT id, value, at, source FROM results WHERE bench = ? "
                         "ORDER BY at DESC, logged DESC LIMIT 2", (b["id"],)).fetchall()
        count = c.execute("SELECT COUNT(*) FROM results WHERE bench = ?",
                          (b["id"],)).fetchone()[0]
        latest = rows[0] if rows else None
        previous = rows[1] if len(rows) > 1 else None
        v = {
            "id": b["id"], "name": b["name"], "kind": b["kind"], "unit": b["unit"],
            "better": b["better"], "target": b["target"],
            "sensitive": sensitive,
            "sensitive_why": (auto or ("you marked it" if owner else "")),
            "marked_by_you": owner,
            # The automatic mark: what the name looks like ("money"), and
            # whether the owner took it off with a card.
            "mark_auto": m["auto"],
            "mark_auto_removed": bool(m["auto"]) and not auto,
            # How the private mark comes off: "instant" (only the owner's
            # own mark holds it), "card" (Jarvis's own mark holds it), or
            # "" (not marked).
            "unmark": ("card" if auto else "instant" if owner else ""),
            "keep_on_screen": sensitive,
            "keep_on_screen_words": KEEP_ON_SCREEN if sensitive else "",
            "results": int(count),
            "latest": ({"id": latest["id"], "value": latest["value"], "at": latest["at"]}
                       if latest else None),
            "change": compare(latest["value"] if latest else None,
                              previous["value"] if previous else None,
                              b["better"], target=b["target"]),
            "created": b["created"], "changed": b["changed"],
        }
        with _P_LOCK:
            waiting = _M_STATE["pending"].get(b["id"])
            last = _M_STATE["last"].get(b["id"])
        v["unmark_waiting"] = bool(waiting)
        v["unmark_last"] = dict(last) if last else None
        if b["kind"] == "command":
            v["command"] = b["command"] or ""
            v["runnable"] = False
            v["not_runnable_why"] = NOT_RUNNABLE
        if points:
            pts = c.execute("SELECT id, value, at FROM results WHERE bench = ? "
                            "ORDER BY at DESC, logged DESC LIMIT ?",
                            (b["id"], int(points))).fetchall()
            v["points"] = [{"id": p["id"], "at": p["at"], "value": p["value"]}
                           for p in reversed(pts)]
            v["points_shown"] = len(pts)
            if _forecast is not None:
                try:
                    v["forecast"] = self._forecast(c, b)
                except Exception:
                    pass          # no range is better than a broken benchmark read
        return v

    def _forecast(self, c, b) -> dict:
        """"About N to M weeks" (jarvis_forecast.py, JARVIS-API section 101).
        Read from the benchmark's own recent numbers - never from the
        `points` count a chart asked for - so every reader gets the same
        answer. The benchmark's own `keep_on_screen` covers it: a health or
        money benchmark's range is for its screen only."""
        rows = c.execute("SELECT value, at FROM results WHERE bench = ? "
                         "ORDER BY at DESC, logged DESC LIMIT 200", (b["id"],)).fetchall()
        return _forecast.forecast([(r["at"], r["value"]) for r in rows], b["target"],
                                  b["better"], self.clock())

    def _view(self, c, r, *, full: bool = False) -> dict:
        folder = r["folder"]
        folder_ok = None
        if folder:
            try:
                check_folder(folder)
                folder_ok = True
            except ValueError:
                folder_ok = False
        wl = r["work_list"]
        benches = c.execute("SELECT * FROM benchmarks WHERE project = ? ORDER BY created",
                            (r["id"],)).fetchall()
        with _P_LOCK:
            waiting = _P_STATE["pending"].get(r["id"])
            last = _P_STATE["last"].get(r["id"])
        with _A_LOCK:
            auto_waiting = _A_STATE["pending"].get(r["id"])
            auto_last = _A_STATE["last"].get(r["id"])
        v = {
            "id": r["id"], "name": r["name"], "kind": r["kind"],
            "shareable": bool(r["shareable"]),
            "shareable_waiting": bool(waiting),
            "shareable_waiting_words": SHARE_WAITING if waiting else "",
            "shareable_last": dict(last) if last else None,
            "auto_route_cloud": bool(r["auto_route_cloud"]),
            "auto_route_waiting": bool(auto_waiting),
            "auto_route_waiting_words": AUTO_ROUTE_WAITING if auto_waiting else "",
            "auto_route_last": dict(auto_last) if auto_last else None,
            # The pill the workspace draws. Both switches are the owner's own,
            # and BOTH have to be on before a cloud lane is even considered:
            # Shareable alone is not enough, and Auto-Route alone is not either.
            "routing": ("Local / Auto-Route to Cloud"
                        if (r["shareable"] and r["auto_route_cloud"])
                        else "Local-Only"),
            "routing_why": ("This project is Shareable and Auto-Route is on: a hard "
                            "question in it may be offered to a cloud lane, and only "
                            "after a card showing the exact words."
                            if (r["shareable"] and r["auto_route_cloud"])
                            else ("Not Shareable, so nothing from this project is ever "
                                  "offered to a cloud lane."
                                  if not r["shareable"] else
                                  "Shareable, but Auto-Route is off, so every turn "
                                  "stays on this PC.")),
            "active": active_project_id() == r["id"],
            "folder": ({"path": folder, "name": _folder_name(folder),
                        "listed": bool(folder_ok),
                        "said": "" if folder_ok else
                        "This folder is no longer on \"Folders Jarvis may look in\" (or is "
                        "gone), so Jarvis does not look in it."} if folder else None),
            "work_list": ({"name": wl, "title": _list_title(wl)} if wl else None),
            "goals": json.loads(r["goals"] or "[]"),
            "benchmarks": len(benches),
            "created": r["created"], "changed": r["changed"],
            "app": _app_view(r["app"], full=full) if r["app"] else None,
        }
        if full:
            # The labelled facts are NOT here. Their own route is
            # GET /api/projects/<pid>/facts, and this view's exact keys are
            # the two apps' frozen contract (projects-cases.json), which the
            # screens' own piece owns (piece 6) - the count a screen wants
            # comes from that route's `count`, so this file changes nothing
            # the apps already read.
            v["instructions"] = r["instructions"]
            v["notes"] = json.loads(r["notes"] or "[]")
            v["benchmark_list"] = [self._bench_view(c, b) for b in benches]
            v["max"] = {"instructions": MAX_INSTRUCTIONS, "notes": MAX_NOTES,
                        "note": MAX_NOTE, "benchmarks": MAX_BENCHMARKS}
        return v

    def unlinked_apps(self) -> list:
        """App folders in Jarvis's apps folder that no project uses: an offer
        inside Projects (adopt one with POST /api/projects {"app": {"adopt":
        ...}}). There is no separate list of apps."""
        try:
            import jarvis_app_workspace as W
            found = W.list_projects()
        except Exception:
            return []
        linked = set()
        if self.exists():
            with self._lock, self._db() as c:
                linked = {r[0] for r in c.execute(
                    "SELECT app FROM projects WHERE app IS NOT NULL").fetchall()}
        return [{"name": a["name"], "type": a["kind"], "title": a["title"]}
                for a in found if a["name"] not in linked]

    def list(self) -> list:
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM projects ORDER BY created").fetchall()
            return [self._view(c, r) for r in rows]

    def get(self, pid: str) -> dict:
        with self._lock, self._db() as c:
            return self._view(c, self._project_row(c, pid), full=True)

    def app_of(self, pid: str) -> dict:
        """{"name": the project's name, "app": its app folder name or None} -
        a light read for jarvis_apps (no git, no benchmarks)."""
        with self._lock, self._db() as c:
            r = self._project_row(c, pid)
            return {"name": r["name"], "app": r["app"]}

    # ---- projects -----------------------------------------------------------------

    def create(self, body: dict, *, here: bool) -> dict:
        if not isinstance(body, dict):
            raise ValueError('need {"name": ..., "kind": "coding" or "life"}')
        kind = body.get("kind")
        if kind not in KINDS:
            raise ValueError('a project is "coding" or "life"')
        app_type, adopt = None, None
        if body.get("app") is not None:
            # An app Jarvis builds: new (`type`) or an existing folder with no
            # project (`adopt`). Coding only, and never with a folder.
            req = body.get("app")
            if not isinstance(req, dict):
                raise ValueError('"app" is {"type": "web"} or {"adopt": "<folder name>"}')
            if kind != "coding":
                raise ValueError("only a coding project can be an app")
            if body.get("folder") not in (None, ""):
                raise ValueError(APP_AND_FOLDER_WORDS)
            if req.get("adopt") is not None:
                adopt = req.get("adopt")
                if not isinstance(adopt, str):
                    raise ValueError("the app to add is named by its folder name")
            else:
                app_type = req.get("type")
                if app_type not in ("web", "android"):
                    raise ValueError('an app is "web" or "android"')
        if adopt is not None and body.get("name") in (None, ""):
            found = {a["name"]: a for a in _workspace().list_projects()}
            name = _one_line((found.get(adopt) or {}).get("title") or adopt, MAX_NAME,
                             "a project's name", required=True)
        else:
            name = _one_line(body.get("name"), MAX_NAME, "a project's name", required=True)
        instructions = _text(body.get("instructions"), MAX_INSTRUCTIONS, "the instructions")
        notes = clean_notes(body.get("notes"))
        goals = clean_goals(body.get("goals"))
        folder = None
        if body.get("folder") not in (None, ""):
            if kind != "coding":
                raise ValueError("a life project has no folder")
            if not here:
                raise PermissionError(PC_ONLY_FOLDER)
            folder = check_folder(body.get("folder"))
        if body.get("shareable") is True:
            raise ValueError("a project starts with Shareable off - turn it on afterwards "
                             "(that asks you with a card)")
        if "work_list" in body:
            work_list = clean_work_list(body.get("work_list"))
        else:
            work_list = _default_work_list(name)
        now = self.clock()
        pid = _new_id()
        with self._lock, self._db() as c:
            n = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if n >= MAX_PROJECTS:
                raise OverflowError(f"there are already {MAX_PROJECTS} projects - delete one "
                                    f"first")
            if c.execute("SELECT 1 FROM projects WHERE lower(name) = lower(?)",
                         (name,)).fetchone():
                raise OverflowError("there is already a project with that name")
            self._list_free(c, work_list, None)
            app, made = None, False
            if adopt is not None:
                app = self._check_adopt(c, adopt)
            elif app_type is not None:
                app = self._make_app(c, name, app_type)
                made = True
            try:
                c.execute("INSERT INTO projects (id, name, kind, instructions, notes, folder, "
                          "shareable, work_list, goals, created, changed, app) "
                          "VALUES (?,?,?,?,?,?,0,?,?,?,?,?)",
                          (pid, name, kind, instructions, json.dumps(notes), folder, work_list,
                           json.dumps(goals), now, now, app))
            except Exception as exc:
                if made:
                    # Only the folder THIS call just made: never another.
                    _workspace().remove_new_project(app)
                if isinstance(exc, sqlite3.IntegrityError) and app:
                    raise OverflowError("that app already has a project") from exc
                raise
        _audit("projects.create", {"id": pid, "kind": kind, "app": bool(app)})
        return self.get(pid)

    def _check_adopt(self, c, adopt: str) -> str:
        W = _workspace()
        try:
            W.check_name(adopt)
        except W.WorkspaceError as exc:
            raise ValueError(str(exc)) from exc
        if adopt not in {a["name"] for a in W.list_projects()}:
            raise NoSuchApp("There is no app folder with that name.")
        if c.execute("SELECT 1 FROM projects WHERE app = ?", (adopt,)).fetchone():
            raise OverflowError("that app already has a project")
        return adopt

    def _make_app(self, c, name: str, app_type: str) -> str:
        """A new, empty app folder for this project (no card: an empty folder
        in Jarvis's own folder, nothing runs)."""
        W = _workspace()
        import jarvis_apps
        taken = {a["name"] for a in W.list_projects()}
        taken |= {r[0] for r in c.execute("SELECT app FROM projects WHERE app IS NOT NULL")}
        try:
            root = W.root()
            if root.is_dir():
                taken |= {d.name for d in root.iterdir()}
        except OSError:
            pass
        slug = jarvis_apps.slug(name, taken)
        try:
            W.create_project(slug, app_type, name)
        except W.GitUnavailable as exc:
            raise Unavailable(str(exc)) from exc
        except W.WorkspaceError as exc:
            raise ValueError(str(exc)) from exc
        return slug

    def _list_free(self, c, work_list: Optional[str], pid: Optional[str]) -> None:
        if not work_list:
            return
        r = c.execute("SELECT id, name FROM projects WHERE work_list = ? AND id != ?",
                      (work_list, pid or "")).fetchone()
        if r is not None:
            raise OverflowError(f"the {_list_title(work_list)} already belongs to the "
                                f"project \"{r['name']}\"")

    def update(self, pid: str, body: dict, *, here: bool) -> dict:
        """Edit what the owner typed. No card: name, instructions, notes,
        goals, work list, folder (PC only), and Shareable OFF. Shareable ON
        is not here - request_shareable() raises its card."""
        if not isinstance(body, dict):
            raise ValueError("send the fields to change")
        # Shareable OFF and a late yes on its card never interleave: the
        # card's write takes the same switch lock (_decide).
        switch = _P_SWITCH if body.get("shareable") is False else contextlib.nullcontext()
        with switch:
            return self._update(pid, body, here=here)

    def _update(self, pid: str, body: dict, *, here: bool) -> dict:
        before, name = {}, ""
        with self._lock, self._db() as c:
            r = self._project_row(c, pid)
            before, name = _snapshot(r), r["name"]
            sets, args = [], []
            if "name" in body:
                name = _one_line(body.get("name"), MAX_NAME, "a project's name", required=True)
                if c.execute("SELECT 1 FROM projects WHERE lower(name) = lower(?) AND id != ?",
                             (name, pid)).fetchone():
                    raise OverflowError("there is already a project with that name")
                sets.append("name = ?")
                args.append(name)
            if "kind" in body and body.get("kind") != r["kind"]:
                raise ValueError("a project's kind cannot change - make a new project")
            if "app" in body:
                raise ValueError(APP_CHOSEN_WORDS)
            if r["app"] and body.get("folder") not in (None, ""):
                raise ValueError(APP_ONLY_WORDS)
            if "instructions" in body:
                sets.append("instructions = ?")
                args.append(_text(body.get("instructions"), MAX_INSTRUCTIONS,
                                  "the instructions"))
            if "notes" in body:
                sets.append("notes = ?")
                args.append(json.dumps(clean_notes(body.get("notes"))))
            if "goals" in body:
                sets.append("goals = ?")
                args.append(json.dumps(clean_goals(body.get("goals"))))
            if "work_list" in body:
                wl = clean_work_list(body.get("work_list"))
                self._list_free(c, wl, pid)
                sets.append("work_list = ?")
                args.append(wl)
            if "folder" in body:
                f = body.get("folder")
                if f in (None, ""):
                    # Clearing it only lets Jarvis see less: either app.
                    new = None
                else:
                    if r["kind"] != "coding":
                        raise ValueError("a life project has no folder")
                    if not here:
                        raise PermissionError(PC_ONLY_FOLDER)
                    new = check_folder(f)
                sets.append("folder = ?")
                args.append(new)
            if "shareable" in body:
                s = body.get("shareable")
                if s is True and not r["shareable"]:
                    raise ValueError("turning Shareable on asks you first - use "
                                     "/api/projects/<id>/shareable")
                if s is False:
                    sets.append("shareable = 0")
                elif s is not True:
                    raise ValueError("shareable is true or false")
            if "auto_route_cloud" in body:
                a = body.get("auto_route_cloud")
                if a is True and not r["auto_route_cloud"]:
                    # The same shape as Shareable, and for the same reason: this
                    # is the switch that lets a turn reach a cloud lane, so ONE
                    # card, and the route is the only door.
                    raise ValueError("turning Auto-Route on asks you first - use "
                                     "/api/projects/<id>/auto-route")
                if a is False:
                    sets.append("auto_route_cloud = 0")
                elif a is not True:
                    raise ValueError("auto_route_cloud is true or false")
            if sets:
                sets.append("changed = ?")
                args.append(self.clock())
                c.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", (*args, pid))
        if "shareable" in body and body.get("shareable") is False:
            _withdraw_share(pid)
        if "auto_route_cloud" in body and body.get("auto_route_cloud") is False:
            _withdraw_auto(pid)
        if sets:
            # One receipt per edit, so the edit has a one-click Undo. Written
            # AFTER the change here (unlike an action that can half-fail), and
            # never able to fail the edit it records.
            _record_project_receipt(
                pid, before,
                {k: body.get(k) for k in UNDOABLE_FIELDS if k in body}, name)
        _audit("projects.update", {"id": pid, "fields": len(sets)})
        return self.get(pid)

    def delete(self, pid: str) -> bool:
        self.delete_full(pid)
        return True

    def delete_full(self, pid: str) -> dict:
        """Deletes the project; answers {"app": <folder name or None>}. An app
        project's FOLDER is never deleted - only the record and its
        benchmarks - and a merge card waiting for it is withdrawn."""
        with _P_SWITCH:
            return self._delete(pid)

    def _delete(self, pid: str) -> dict:
        with self._lock, self._db() as c:
            app = self._project_row(c, pid)["app"]
            benches = [b["id"] for b in c.execute("SELECT id FROM benchmarks WHERE project = ?",
                                                  (pid,)).fetchall()]
            for bid in benches:
                c.execute("DELETE FROM results WHERE bench = ?", (bid,))
            c.execute("DELETE FROM benchmarks WHERE project = ?", (pid,))
            # The LABELS go with the project. Nothing in memory.db is touched:
            # the facts are the owner's, and deleting a project never forgets
            # one - only the memory module's own Forget does that.
            c.execute("DELETE FROM project_facts WHERE project = ?", (pid,))
            # The PLAN rows go with the project too (2026-11-19, PM1). The
            # event log is the project's own history, so it leaves with the
            # project exactly as its benchmarks do: the table stays append-only
            # (no per-event edit or delete exists), and nothing is left behind
            # for `project_doctor()` to report as an orphan.
            c.execute("DELETE FROM work_edges WHERE project = ?", (pid,))
            c.execute("DELETE FROM work_items WHERE project = ?", (pid,))
            c.execute("DELETE FROM milestones WHERE project = ?", (pid,))
            c.execute("DELETE FROM project_events WHERE project = ?", (pid,))
            c.execute("DELETE FROM projects WHERE id = ?", (pid,))
            self._drop_axes(c, "bench", benches)
        # The row is gone as of that commit. If it was the ACTIVE project the
        # mode file must stop naming it: otherwise active_project_id() keeps
        # answering a dead id, and every reader of it is handed a project that
        # is not there. The chat path's own lane gate in
        # backend/cloud-say-yes.patch is one such reader - for EVERY turn - and
        # a KeyError out of Projects.get there is a 500 on every chat turn
        # until the owner leaves Project Mode by hand. Leaving Project Mode is
        # the honest outcome: this never enters another project, and it never
        # makes a turn cloud-eligible. Done here, right after the commit and
        # BEFORE the withdrawals below, so a withdrawal that raises cannot
        # leave the dead id behind. `set_active_project(None)` is the one
        # audited door for leaving, the same call the route uses. A mode file
        # that cannot be written raises out of here on purpose: a delete that
        # cannot clear the dead id must not report success while the 500 stays.
        if active_project_id() == pid:
            set_active_project(None, store=self)
        _withdraw_share(pid)
        for bid in benches:
            _withdraw_unmark(bid)
            _forget_log_state(bid)
        if app:
            try:
                import jarvis_apps
                jarvis_apps.withdraw_card(app)
            except ImportError:
                pass
        _audit("projects.delete", {"id": pid, "benchmarks": len(benches), "app": bool(app)})
        return {"app": app}

    def set_shareable_on(self, pid: str) -> None:
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            c.execute("UPDATE projects SET shareable = 1, changed = ? WHERE id = ?",
                      (self.clock(), pid))
        _audit("projects.shareable_on", {"id": pid})

    def set_auto_route_cloud_on(self, pid: str) -> None:
        """The card's own write, and the ONLY way this column is ever set to 1.
        `_update` refuses it, so there is one door and a card behind it."""
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            c.execute("UPDATE projects SET auto_route_cloud = 1, changed = ? WHERE id = ?",
                      (self.clock(), pid))
        _audit("projects.auto_route_on", {"id": pid})

    # ---- benchmarks ---------------------------------------------------------------

    def add_benchmark(self, pid: str, body: dict, *, here: bool) -> dict:
        if not isinstance(body, dict):
            raise ValueError('need {"name": ..., "kind": "number" or "command"}')
        name = _one_line(body.get("name"), MAX_BENCH_NAME, "a benchmark's name", required=True)
        kind = body.get("kind", "number")
        if kind not in BENCH_KINDS:
            raise ValueError('a benchmark is "number" (you log it) or "command" (a test '
                             'or a script on the PC)')
        unit = _one_line(body.get("unit"), MAX_UNIT, "the unit")
        better = body.get("better")
        if better not in (None,) + BETTER:
            raise ValueError('"better" is "higher", "lower" or left out')
        target = _opt_value(body.get("target"))
        owner = body.get("sensitive") is True
        command = None
        now = self.clock()
        bid = _new_id()
        with self._lock, self._db() as c:
            r = self._project_row(c, pid)
            if kind == "command":
                if r["kind"] != "coding":
                    raise ValueError("a life project's benchmarks are numbers you log")
                if not here:
                    raise PermissionError(PC_ONLY_COMMAND)
                command = _one_line(body.get("command"), MAX_COMMAND, "the command",
                                    required=True)
            elif body.get("command") not in (None, ""):
                raise ValueError("a number you log has no command")
            n = c.execute("SELECT COUNT(*) FROM benchmarks WHERE project = ?",
                          (pid,)).fetchone()[0]
            if n >= MAX_BENCHMARKS:
                raise OverflowError(f"a project has at most {MAX_BENCHMARKS} benchmarks")
            if c.execute("SELECT 1 FROM benchmarks WHERE project = ? AND lower(name) = lower(?)",
                         (pid, name)).fetchone():
                raise OverflowError("this project already has a benchmark with that name")
            c.execute("INSERT INTO benchmarks (id, project, name, kind, unit, better, target, "
                      "command, owner_sensitive, created, changed) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (bid, pid, name, kind, unit, better, target, command, int(owner),
                       now, now))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?", (now, pid))
            v = self._bench_view(c, self._bench_row(c, pid, bid))
        _audit("projects.benchmark.add", {"project": pid, "id": bid, "kind": kind})
        return v

    def update_benchmark(self, pid: str, bid: str, body: dict, *, here: bool) -> dict:
        if not isinstance(body, dict):
            raise ValueError("send the fields to change")
        # A late yes on an "unmark" card and a rename or a new mark of the
        # owner's never interleave: the card's write takes this lock too.
        with _P_SWITCH:
            return self._update_benchmark(pid, bid, body, here=here)

    def _update_benchmark(self, pid: str, bid: str, body: dict, *, here: bool) -> dict:
        recheck = False
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            sets, args = [], []
            if "name" in body:
                name = _one_line(body.get("name"), MAX_BENCH_NAME, "a benchmark's name",
                                 required=True)
                if c.execute("SELECT 1 FROM benchmarks WHERE project = ? AND lower(name) = "
                             "lower(?) AND id != ?", (pid, name, bid)).fetchone():
                    raise OverflowError("this project already has a benchmark with that name")
                sets.append("name = ?")
                args.append(name)
                recheck = recheck or name != b["name"]
            if "kind" in body and body.get("kind") != b["kind"]:
                raise ValueError("a benchmark's kind cannot change - make a new one")
            if "unit" in body:
                unit = _one_line(body.get("unit"), MAX_UNIT, "the unit")
                sets.append("unit = ?")
                args.append(unit)
                recheck = recheck or unit != b["unit"]
            if "better" in body:
                if body.get("better") not in (None,) + BETTER:
                    raise ValueError('"better" is "higher", "lower" or null')
                sets.append("better = ?")
                args.append(body.get("better"))
            if "target" in body:
                sets.append("target = ?")
                args.append(_opt_value(body.get("target")))
            if "sensitive" in body:
                if not isinstance(body.get("sensitive"), bool):
                    raise ValueError("sensitive is true or false")
                # Only YOUR mark changes; a mark made from the name stays
                # (it comes off only through request_unmark(), with a card).
                sets.append("owner_sensitive = ?")
                args.append(int(body["sensitive"]))
            if "command" in body:
                if b["kind"] != "command":
                    raise ValueError("a number you log has no command")
                if not here:
                    raise PermissionError(PC_ONLY_COMMAND)
                sets.append("command = ?")
                args.append(_one_line(body.get("command"), MAX_COMMAND, "the command",
                                      required=True))
            if recheck:
                # A new name or unit is checked again: an automatic mark the
                # owner took off comes back if the new words still look like
                # health or money.
                sets.append("auto_cleared = NULL")
            if sets:
                now = self.clock()
                sets.append("changed = ?")
                args.append(now)
                c.execute(f"UPDATE benchmarks SET {', '.join(sets)} WHERE id = ?", (*args, bid))
        if recheck or body.get("sensitive") is True:
            # The card showed the old words, or the owner marked it again:
            # a waiting "unmark" card no longer counts.
            _withdraw_unmark(bid)
        with self._lock, self._db() as c:
            v = self._bench_view(c, self._bench_row(c, pid, bid))
        _audit("projects.benchmark.update", {"project": pid, "id": bid, "fields": len(sets)})
        return v

    def unmark_owner(self, pid: str, bid: str) -> bool:
        """Take the owner's own private mark off at once. True when it was on."""
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            if not b["owner_sensitive"]:
                return False
            c.execute("UPDATE benchmarks SET owner_sensitive = 0, changed = ? WHERE id = ?",
                      (self.clock(), bid))
        _audit("projects.benchmark.unmark", {"project": pid, "id": bid, "whose": "owner"})
        return True

    def clear_auto_mark(self, pid: str, bid: str, name: str, unit: str, topic: str) -> None:
        """After a person's yes on the card: take off the automatic mark -
        only if the benchmark still has the words the card showed."""
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            if (b["name"], b["unit"]) != (name, unit) or auto_sensitive(name, unit) != topic:
                raise LookupError("the benchmark changed while the card waited")
            c.execute("UPDATE benchmarks SET auto_cleared = ?, changed = ? WHERE id = ?",
                      (topic, self.clock(), bid))
        _audit("projects.benchmark.unmark", {"project": pid, "id": bid, "whose": "auto"})

    def delete_benchmark(self, pid: str, bid: str) -> bool:
        with _P_SWITCH, self._lock, self._db() as c:
            self._project_row(c, pid)
            self._bench_row(c, pid, bid)
            c.execute("DELETE FROM results WHERE bench = ?", (bid,))
            c.execute("DELETE FROM benchmarks WHERE id = ?", (bid,))
            self._drop_axes(c, "bench", [bid])
        _withdraw_unmark(bid)
        # A card waiting to write into it must never write into a benchmark
        # that is gone (nor into a new one the id could not name twice).
        _forget_log_state(bid)
        _audit("projects.benchmark.delete", {"project": pid, "id": bid})
        return True

    def log(self, pid: str, bid: str, value, *, at=None, source: str = "app") -> dict:
        """One number the owner logged - their own tap or their own words.
        No card. A command benchmark's results come from running it, which
        is a later step, so logging one by hand is refused."""
        v = _value(value)
        now = self.clock()
        if at is None:
            when = now
        else:
            when = _value(at)
            if when > now + 86400 or when < now - 20 * 365 * 86400:
                raise ValueError("that date is too far from today")
        if source not in ("app", "words"):
            source = "app"
        rid = _new_id()
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            b = self._bench_row(c, pid, bid)
            if b["kind"] != "number":
                raise ValueError("a command's results come from running it, which comes in a "
                                 "later step")
            n = c.execute("SELECT COUNT(*) FROM results WHERE bench = ?", (bid,)).fetchone()[0]
            if n >= MAX_RESULTS:
                raise OverflowError(f"this benchmark already has {MAX_RESULTS} numbers - "
                                    f"remove some old ones first")
            c.execute("INSERT INTO results (id, bench, value, at, source, logged) "
                      "VALUES (?,?,?,?,?,?)", (rid, bid, v, when, source, now))
            out = self._bench_view(c, self._bench_row(c, pid, bid))
        _audit("projects.log", {"project": pid, "bench": bid, "source": source})
        out["logged"] = {"id": rid, "value": v, "at": when}
        return out

    def delete_result(self, pid: str, bid: str, rid: str) -> bool:
        if not isinstance(rid, str) or not _ID.fullmatch(rid):
            raise KeyError(rid)
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            self._bench_row(c, pid, bid)
            cur = c.execute("DELETE FROM results WHERE id = ? AND bench = ?", (rid, bid))
            if cur.rowcount == 0:
                raise KeyError(rid)
        _audit("projects.result.delete", {"project": pid, "bench": bid})
        return True

    def results(self, pid: str, bid: str, points: int = CHART_POINTS) -> dict:
        """For a chart: dated points (oldest first, at most `points`), the
        target line when there is one, and better/worse than last time."""
        try:
            points = int(points)
        except (TypeError, ValueError):
            points = CHART_POINTS
        points = max(1, min(points, CHART_POINTS_MAX))
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            return self._bench_view(c, self._bench_row(c, pid, bid), points=points)

    # ---- a project's labelled facts (2026-10-15) ------------------------------------
    #
    # See the "A project's labelled facts" note at the top of this file. In one
    # line: the LABEL is here, the fact is jarvis_memory's, and no fact's words
    # pass through this module.

    def facts(self, pid: str) -> list:
        """A project's labelled facts, oldest label first:
        [{"fact": <memory fact id>, "created": <when it was labelled>}].

        The LABEL only - never a fact's words. An app shows them by handing
        these ids to jarvis_memory's own existing read,
        `GET /api/memory/used?ids=...`, which already says "no longer in use"
        for a forgotten fact and leaves an Off topic out. Empty when there is
        no projects.db."""
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            rows = c.execute("SELECT fact, created FROM project_facts WHERE project = ? "
                             "ORDER BY created, fact", (pid,)).fetchall()
        return [{"fact": int(r["fact"]), "created": r["created"]} for r in rows]

    def fact_labels(self, pid: str) -> dict:
        """The IDS of the facts this project labels, and the ids OTHER
        projects label: {"own": [...], "others": [...]}.

        The labels only, never a fact's words - the same rule `facts()` keeps.
        A project-scoped chat uses this to keep one project's facts out of
        another project's turn (`jarvis_hud.py` asks, `jarvis_quick.py` says
        what to keep) and to let this project's own labelled facts in."""
        own = [f["fact"] for f in self.facts(pid)]
        if not self.exists():
            return {"own": own, "others": []}
        with self._lock, self._db() as c:
            rows = c.execute("SELECT DISTINCT fact FROM project_facts "
                             "WHERE project != ?", (pid,)).fetchall()
        return {"own": own, "others": [int(r["fact"]) for r in rows]}

    def label_fact(self, pid: str, fact) -> dict:
        """Label ONE of the owner's own remembered facts with this project.

        No card and no PC-only: the owner's own tap on a fact they can see,
        the same shape as jarvis_memory's "Between us". Refused when the fact
        is not there (404), or is no longer current - forgotten, or its words
        erased (409) - so a label never points at something that cannot be
        recalled. Labelling the same fact twice changes nothing (`changed` is
        false); a project labels at most MAX_FACTS.

        Reads no fact's words: the memory layer is asked whether one id is
        there and still current, and nothing else.

        The PROJECT is checked first - it is the route's own subject, so a
        route under a project that is gone is a 404 whatever the fact is -
        and the memory layer is asked with no lock held, because opening it
        the first time is slow and this is the owner's tap on a phone."""
        fid = _fact_id(fact)
        with self._lock, self._db() as c:
            self._project_row(c, pid)
        state = _fact_state(fid)
        if not state["found"]:
            raise FactGone(NO_SUCH_FACT)
        if not state["current"]:
            raise FactGone(FACT_NOT_CURRENT, status=409)
        now = self.clock()
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            n = c.execute("SELECT COUNT(*) FROM project_facts WHERE project = ?",
                          (pid,)).fetchone()[0]
            already = c.execute("SELECT 1 FROM project_facts WHERE project = ? AND fact = ?",
                                (pid, fid)).fetchone() is not None
            if not already and n >= MAX_FACTS:
                raise OverflowError(f"a project labels at most {MAX_FACTS} facts")
            cur = c.execute("INSERT OR IGNORE INTO project_facts (project, fact, created) "
                            "VALUES (?,?,?)", (pid, fid, now))
            changed = bool(cur.rowcount)
            if changed:
                c.execute("UPDATE projects SET changed = ? WHERE id = ?", (now, pid))
            total = n + 1 if changed else n
        _audit("projects.fact.label", {"project": pid, "fact": fid, "changed": changed})
        return {"ok": True, "fact": fid, "changed": changed, "facts": int(total),
                "max": MAX_FACTS}

    def forget_fact(self, pid: str, fact) -> dict:
        """The owner forgets ONE fact from this project.

        The FACT goes first, through the memory module's own Forget
        (`MemoryStore.retire()`, the same call `POST /api/memory/forget`
        makes), and the label comes off only once that has answered: a memory
        layer that refuses leaves the label in place, so the list still shows
        the fact and the owner can try again - never a list that has taken a
        fact off while the rest of Jarvis still recalls it.

        No card, and no words wiped (that is "Erase the words", its own
        button). Answers {"ok", "fact", "unlabelled", "forgot"} - `forgot` is
        false when there was nothing left to forget, which is an already
        forgotten fact, or an id with no fact at all.

        A fact this project does not label is a 404: there is nothing here to
        forget. The label comes off even when the fact is already gone."""
        fid = _fact_id(fact)
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            if c.execute("SELECT 1 FROM project_facts WHERE project = ? AND fact = ?",
                         (pid, fid)).fetchone() is None:
                raise FactGone(FACT_NOT_LABELLED)
        forgot = _forget_fact(fid)
        now = self.clock()
        with self._lock, self._db() as c:
            self._project_row(c, pid)
            c.execute("DELETE FROM project_facts WHERE project = ? AND fact = ?", (pid, fid))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?", (now, pid))
        _audit("projects.fact.forget", {"project": pid, "fact": fid, "forgot": forgot})
        return {"ok": True, "fact": fid, "unlabelled": True, "forgot": forgot}

    # ---- the quick command's side ---------------------------------------------------

    def life_benchmarks(self) -> list:
        """Every number benchmark, with its project's name - for matching
        "I ran 5 km". Empty when there is no projects.db (nothing created)."""
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            rows = c.execute("SELECT b.id, b.project, b.name, b.unit, b.owner_sensitive, "
                             "b.auto_cleared, p.name AS project_name FROM benchmarks b "
                             "JOIN projects p ON p.id = b.project WHERE b.kind = 'number' "
                             "ORDER BY b.created").fetchall()
        return [{"id": r["id"], "project": r["project"], "name": r["name"], "unit": r["unit"],
                 "project_name": r["project_name"],
                 "sensitive": marks(r["name"], r["unit"], r["owner_sensitive"],
                                    r["auto_cleared"])["sensitive"]}
                for r in rows]

    # ---- the plan store: milestones, work items, links and events (2026-11-19) ----
    # Additive to THIS projects.db (docs/JARVIS-API.md section 88.7). These are
    # the store's own reads and writes; no route, no card and no model tool
    # calls them in this step. A write here is the owner's own row - like a
    # benchmark or a note - and it appends ONE event in the same transaction.
    # Nothing here changes a column this store had before 2026-11-19.

    def _work_row(self, c, item_id: str):
        """One work item row, or KeyError. A raw string is never put in SQL."""
        if not isinstance(item_id, str) or not _ID.fullmatch(item_id):
            raise KeyError(item_id)
        r = c.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
        if r is None:
            raise KeyError(item_id)
        return r

    def _milestone_row(self, c, milestone_id: str):
        if not isinstance(milestone_id, str) or not _ID.fullmatch(milestone_id):
            raise KeyError(milestone_id)
        r = c.execute("SELECT * FROM milestones WHERE id = ?", (milestone_id,)).fetchone()
        if r is None:
            raise KeyError(milestone_id)
        return r

    def _direct_open_blockers(self, c, item_id: str) -> list:
        """The OPEN `blocks` links pointing at one item: the direct blockers,
        not the whole chain (that is `blocking_chain()`)."""
        rows = c.execute(
            "SELECT e.src AS id, b.title AS title, b.status AS status "
            "FROM work_edges e JOIN work_items b ON b.id = e.src "
            "WHERE e.kind = 'blocks' AND e.dst = ? "
            "AND b.status NOT IN ('done', 'cancelled') ORDER BY e.created, e.id",
            (item_id,)).fetchall()
        return [{"id": r["id"], "title": r["title"], "status": r["status"]} for r in rows]

    def _work_view(self, c, r) -> dict:
        project = c.execute("SELECT name, status FROM projects WHERE id = ?",
                            (r["project"],)).fetchone()
        blockers = self._direct_open_blockers(c, r["id"])
        project_open = bool(project is not None
                            and (project["status"] is None
                                 or project["status"] not in CLOSED_PROJECT_STATUSES))
        return {
            "id": r["id"], "project": r["project"],
            "project_name": project["name"] if project is not None else "",
            "milestone": r["milestone"], "title": r["title"], "detail": r["detail"],
            "status": r["status"], "priority": r["priority"], "due_date": r["due_date"],
            "created": r["created"], "changed": r["changed"],
            "blocked_by": blockers,
            "ready": bool(r["status"] in READY_STATUSES and not blockers and project_open),
            # PM3 (2026-11-20): who would do it, and what it is linked to.
            # Read-only facts: nothing in this module acts on any of them.
            "executor": (r["executor"] or "owner"),
            "linked_task_id": r["linked_task_id"],
            "linked_pr_number": r["linked_pr_number"],
            "linked_pr_state": (r["linked_pr_state"] or ""),
            "linked_ci_status": (r["linked_ci_status"] or ""),
        }

    def _milestone_view(self, r) -> dict:
        return {"id": r["id"], "project": r["project"], "title": r["title"],
                "status": r["status"], "due_date": r["due_date"],
                "position": r["position"], "created": r["created"],
                "changed": r["changed"]}

    def _event(self, c, project_id: str, kind: str, subject: str,
               detail: Optional[dict] = None) -> None:
        """Append ONE event row. The table is append-only: there is no update
        and no delete for it here, and a trigger refuses an UPDATE outright.
        Ids and transitions only - a title, a name or a number is never
        copied here (the same rule this file's audit log keeps)."""
        c.execute("INSERT INTO project_events (id, project, at, kind, subject, detail) "
                  "VALUES (?,?,?,?,?,?)",
                  (_new_id(), project_id, self.clock(),
                   kind, str(subject)[:MAX_EVENT_SUBJECT],
                   json.dumps(detail or {}, sort_keys=True)))

    # ---- writing a plan (the store's own door; no route calls it yet) ----

    def add_milestone(self, project_id: str, body: dict) -> dict:
        """A milestone a project works towards. No card: it is the owner's own
        row, like a project note. Nothing of the project's current columns
        changes except `changed`."""
        if not isinstance(body, dict):
            raise ValueError("a milestone needs a title, and may have a status and "
                             "a due date")
        title = _one_line(body.get("title"), MAX_MILESTONE_TITLE, "a milestone's title",
                          required=True)
        status = str(body.get("status") or "planned")
        if status not in MILESTONE_STATUSES:
            raise ValueError("a milestone is " + ", ".join(MILESTONE_STATUSES))
        due_date = _clean_date(body.get("due_date"))
        position = body.get("position")
        if position in (None, ""):
            position = None
        else:
            try:
                position = int(position)
            except (TypeError, ValueError):
                raise ValueError("a milestone's position is a whole number") from None
            if position < 0:
                raise ValueError("a milestone's position is a whole number")
        now = self.clock()
        mid = _new_id()
        with self._lock, self._db() as c:
            self._project_row(c, project_id)
            if position is None:
                position = int(c.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM milestones WHERE project = ?",
                    (project_id,)).fetchone()[0])
            c.execute("INSERT INTO milestones (id, project, title, status, due_date, position, "
                      "created, changed) VALUES (?,?,?,?,?,?,?,?)",
                      (mid, project_id, title, status, due_date, position, now, now))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?", (now, project_id))
            self._event(c, project_id, "milestone_added", mid, {"status": status})
            view = self._milestone_view(self._milestone_row(c, mid))
        _audit("projects.milestone.add", {"project": project_id, "id": mid,
                                          "status": status})
        return view

    def add_work_item(self, project_id: str, body: dict) -> dict:
        """One step that can be started. No card: the owner's own row."""
        if not isinstance(body, dict):
            raise ValueError("a work item needs a title, and may have a status, a "
                             "priority and a due date")
        title = _one_line(body.get("title"), MAX_WORK_TITLE, "a work item's title",
                          required=True)
        detail = _text(body.get("detail"), MAX_WORK_DETAIL, "a work item's detail")
        status = str(body.get("status") or "backlog")
        if status not in WORK_STATUSES:
            raise ValueError("a work item is " + ", ".join(WORK_STATUSES))
        # WHO WOULD DO IT (PM3): a value from the review's own column, default
        # "owner". It is a label, never a trigger: nothing here starts a job.
        executor = str(body.get("executor") or "owner").strip().lower()
        if executor not in EXECUTORS:
            raise ValueError("an executor is " + ", ".join(EXECUTORS))
        priority = _clean_priority(body.get("priority"))
        due_date = _clean_date(body.get("due_date"))
        milestone = body.get("milestone")
        now = self.clock()
        wid = _new_id()
        with self._lock, self._db() as c:
            self._project_row(c, project_id)
            if milestone in (None, ""):
                milestone = None
            else:
                milestone = str(milestone)
                if not c.execute("SELECT 1 FROM milestones WHERE id = ? AND project = ?",
                                 (milestone, project_id)).fetchone():
                    raise ValueError("that milestone is not in this project")
            c.execute("INSERT INTO work_items (id, project, milestone, title, detail, status, "
                      "priority, due_date, executor, created, changed) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (wid, project_id, milestone, title, detail, status, priority,
                       due_date, executor, now, now))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?", (now, project_id))
            self._event(c, project_id, "work_item_added", wid, {"status": status})
            view = self._work_view(c, self._work_row(c, wid))
        _audit("projects.work.add", {"project": project_id, "id": wid, "status": status})
        return view

    def set_work_item_status(self, item_id: str, status: str, *,
                             receipt: bool = True) -> dict:
        """Move one item between the five states. No card and no second write:
        the status change is one row plus one event, and - unless `receipt` is
        off, which only an Undo itself uses - one `jarvis_receipts` entry so the
        change has a one-click Undo. Returns the item."""
        status = str(status or "")
        if status not in WORK_STATUSES:
            raise ValueError("a work item is " + ", ".join(WORK_STATUSES))
        now = self.clock()
        changed = False
        with self._lock, self._db() as c:
            row = self._work_row(c, item_id)
            old = row["status"]
            if old != status:
                c.execute("UPDATE work_items SET status = ?, changed = ? WHERE id = ?",
                          (status, now, item_id))
                c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                          (now, row["project"]))
                self._event(c, row["project"], "work_item_status", item_id,
                            {"from": old, "to": status})
                changed = True
            view = self._work_view(c, self._work_row(c, item_id))
        _audit("projects.work.status", {"id": item_id, "status": status})
        if changed and receipt:
            _record_work_status_receipt(row["project"], item_id, view["title"],
                                        old, status)
        return view

    def set_plan_fields(self, project_id: str, body: dict) -> dict:
        """The plan's own project fields: objective, success criteria, status,
        target date and the two links. No card and no route in this step; the
        guarded ALTER above is what makes them exist on an older file. Only
        the fields actually sent change, and `slug` is never a key (A2)."""
        if not isinstance(body, dict):
            raise ValueError('need {"objective": ..., "status": ...}')
        allowed = ("objective", "success_criteria", "status", "target_date",
                   "linked_repo", "linked_note_path")
        unknown = sorted(set(body) - set(allowed))
        if unknown:
            raise ValueError("a plan field is " + ", ".join(allowed))
        sets = {}
        if "objective" in body:
            sets["objective"] = _text(body.get("objective"), MAX_WORK_DETAIL,
                                      "the objective")
        if "success_criteria" in body:
            sets["success_criteria"] = _text(body.get("success_criteria"), MAX_WORK_DETAIL,
                                             "the success criteria")
        if "status" in body:
            status = str(body.get("status") or "planned")
            if status not in PROJECT_STATUSES:
                raise ValueError("a project's plan status is "
                                 + ", ".join(PROJECT_STATUSES))
            sets["status"] = status
        if "target_date" in body:
            sets["target_date"] = _clean_date(body.get("target_date"))
        if "linked_repo" in body:
            sets["linked_repo"] = _one_line(body.get("linked_repo"), 300,
                                            "the linked repository")
        if "linked_note_path" in body:
            sets["linked_note_path"] = _one_line(body.get("linked_note_path"), 500,
                                                "the linked note's path")
        now = self.clock()
        with self._lock, self._db() as c:
            self._project_row(c, project_id)
            if sets:
                columns = ", ".join(f"{name} = ?" for name in sets)
                c.execute(f"UPDATE projects SET {columns}, changed = ? WHERE id = ?",
                          tuple(sets.values()) + (now, project_id))
                self._event(c, project_id, "project_plan_changed", project_id,
                            {"fields": sorted(sets)})
        _audit("projects.plan.update", {"project": project_id, "fields": len(sets)})
        return self.plan_state(project_id)

    def add_edge(self, kind: str, src: str, dst: str) -> dict:
        """A typed link `src -> kind -> dst`. For the two ordering kinds this
        runs a DFS first and REFUSES a link that would make a circle - the
        refusal writes nothing at all (no edge, no event). `blocks` and
        `parent_child` join two items of one project; `related` and
        `discovered_from` may cross projects."""
        kind = str(kind or "")
        if kind not in EDGE_KINDS:
            raise ValueError("a link is " + ", ".join(EDGE_KINDS))
        now = self.clock()
        with self._lock, self._db() as c:
            source = self._work_row(c, src)
            target = self._work_row(c, dst)
            if src == dst:
                raise ValueError(SELF_EDGE)
            if kind in ORDERING_EDGES and source["project"] != target["project"]:
                raise ValueError(CROSS_PROJECT_EDGE)
            if c.execute("SELECT 1 FROM work_edges WHERE kind = ? AND src = ? AND dst = ?",
                         (kind, src, dst)).fetchone():
                raise OverflowError(EDGE_EXISTS)
            if kind in ORDERING_EDGES and self._would_cycle(c, kind, src, dst):
                raise ValueError(CYCLE_EDGE)
            eid = _new_id()
            c.execute("INSERT INTO work_edges (id, project, kind, src, dst, created) "
                      "VALUES (?,?,?,?,?,?)",
                      (eid, source["project"], kind, src, dst, now))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                      (now, source["project"]))
            self._event(c, source["project"], "edge_added", eid,
                        {"kind": kind, "src": src, "dst": dst})
        _audit("projects.edge.add", {"kind": kind, "id": eid})
        return {"id": eid, "project": source["project"], "kind": kind,
                "src": src, "dst": dst, "created": now}

    def _would_cycle(self, c, kind: str, src: str, dst: str) -> bool:
        """Would `src -> dst` close a circle? Walk forward from `dst` along the
        same kind of link; reaching `src` means yes. Seen nodes are walked
        once, so a circle already in the rows cannot hang the walk."""
        if kind not in ORDERING_EDGES:
            return False
        seen, stack = {dst}, [dst]
        while stack:
            at = stack.pop()
            for row in c.execute("SELECT dst FROM work_edges WHERE kind = ? AND src = ?",
                                 (kind, at)).fetchall():
                nxt = row["dst"]
                if nxt == src:
                    return True
                if nxt in seen:
                    continue
                seen.add(nxt)
                stack.append(nxt)
        return False

    def would_cycle(self, kind: str, src: str, dst: str) -> bool:
        """Read-only: would this link be refused as a circle?"""
        if kind not in EDGE_KINDS:
            raise ValueError("a link is " + ", ".join(EDGE_KINDS))
        if not self.exists():
            return False
        with self._lock, self._db() as c:
            return self._would_cycle(c, kind, src, dst)

    # ---- reading a plan (the three answers' only sources) ----

    def work_items(self, project_id: Optional[str] = None,
                   status: Optional[str] = None) -> list:
        """Every work item, oldest first, as `_work_view` shapes. Read-only."""
        if not self.exists():
            return []
        sql = ("SELECT w.* FROM work_items w JOIN projects p ON p.id = w.project "
               "WHERE 1 = 1")
        args = []
        if project_id is not None:
            if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
                raise KeyError(project_id)
            sql += " AND w.project = ?"
            args.append(project_id)
        if status is not None:
            if status not in WORK_STATUSES:
                raise ValueError("a work item is " + ", ".join(WORK_STATUSES))
            sql += " AND w.status = ?"
            args.append(status)
        sql += " ORDER BY w.created, w.id"
        with self._lock, self._db() as c:
            return [self._work_view(c, r) for r in c.execute(sql, args).fetchall()]

    def milestones(self, project_id: Optional[str] = None) -> list:
        if not self.exists():
            return []
        sql = "SELECT * FROM milestones"
        args = []
        if project_id is not None:
            if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
                raise KeyError(project_id)
            sql += " WHERE project = ?"
            args.append(project_id)
        sql += " ORDER BY position, created, id"
        with self._lock, self._db() as c:
            return [self._milestone_view(r) for r in c.execute(sql, args).fetchall()]

    def events(self, project_id: Optional[str] = None, limit: int = 50) -> list:
        """The append-only log, oldest first. Read-only; there is no setter."""
        if not self.exists():
            return []
        sql = "SELECT * FROM project_events"
        args = []
        if project_id is not None:
            if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
                raise KeyError(project_id)
            sql += " WHERE project = ?"
            args.append(project_id)
        sql += " ORDER BY rowid LIMIT ?"
        args.append(max(1, int(limit)))
        with self._lock, self._db() as c:
            rows = c.execute(sql, args).fetchall()
        return [{"id": r["id"], "project": r["project"], "at": r["at"],
                 "kind": r["kind"], "subject": r["subject"],
                 "detail": json.loads(r["detail"] or "{}")} for r in rows]

    def edge_count(self, *, project_id: Optional[str] = None,
                   kind: Optional[str] = None) -> int:
        """How many typed links are recorded (0 means none at all)."""
        if not self.exists():
            return 0
        sql = "SELECT COUNT(*) FROM work_edges WHERE 1 = 1"
        args = []
        if project_id is not None:
            if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
                raise KeyError(project_id)
            sql += " AND project = ?"
            args.append(project_id)
        if kind is not None:
            if kind not in EDGE_KINDS:
                raise ValueError("a link is " + ", ".join(EDGE_KINDS))
            sql += " AND kind = ?"
            args.append(kind)
        with self._lock, self._db() as c:
            return int(c.execute(sql, args).fetchone()[0])

    def ready_next(self, project_id: Optional[str] = None, limit: int = 20) -> list:
        """The work items that can be started now: not started or finished,
        their project not closed, and nothing open blocking them. Ordered by
        priority (lower first), then due date (earlier first), then the order
        they were written; NULLS LAST both ways. Read-only."""
        if not self.exists():
            return []
        if project_id is not None and (not isinstance(project_id, str)
                                       or not _ID.fullmatch(project_id)):
            raise KeyError(project_id)
        sql = ("SELECT w.* FROM work_items w JOIN projects p ON p.id = w.project "
               f"WHERE {_READY_WHERE}")
        args = []
        if project_id is not None:
            sql += " AND w.project = ?"
            args.append(project_id)
        sql += f" ORDER BY {_READY_ORDER} LIMIT ?"
        args.append(max(1, int(limit)))
        with self._lock, self._db() as c:
            rows = c.execute(sql, args).fetchall()
            return [self._work_view(c, r) for r in rows]

    def blocked_items(self, project_id: Optional[str] = None) -> list:
        """Every OPEN work item with at least one open blocker, each with the
        blockers named. Read-only: nothing is ticked or changed."""
        if not self.exists():
            return []
        if project_id is not None and (not isinstance(project_id, str)
                                       or not _ID.fullmatch(project_id)):
            raise KeyError(project_id)
        sql = ("SELECT w.* FROM work_items w JOIN projects p ON p.id = w.project "
               f"WHERE {_BLOCKED_WHERE}")
        args = []
        if project_id is not None:
            sql += " AND w.project = ?"
            args.append(project_id)
        sql += (" ORDER BY w.priority IS NULL, w.priority, w.due_date IS NULL, "
                "w.due_date, w.created, w.id")
        with self._lock, self._db() as c:
            return [{"item": self._work_view(c, r),
                     "blockers": self._direct_open_blockers(c, r["id"])}
                    for r in c.execute(sql, args).fetchall()]

    def blocking_chain(self, item_id: str) -> dict:
        """The OPEN items that block one work item, directly or through other
        `blocks` links. A walk that visits each item once, so a circle already
        in the rows is walked once, never forever.

        Returns {"item": item view, "blockers": [{id, title, status, depth}],
        "edges": N}. `edges` is how many `blocks` links point at the item AT
        ALL - 0 means no blocker has been recorded, which is a different
        answer from "every recorded blocker is done" (blockers is then empty
        but `edges` is not)."""
        with self._lock, self._db() as c:
            item = self._work_view(c, self._work_row(c, item_id))
            edges = int(c.execute("SELECT COUNT(*) FROM work_edges "
                                  "WHERE kind = 'blocks' AND dst = ?",
                                  (item_id,)).fetchone()[0])
            blockers, seen = [], {item_id}
            queue = [(item_id, 0)]
            while queue:
                current, depth = queue.pop(0)
                for src in self._direct_open_blockers(c, current):
                    if src["id"] in seen:
                        continue
                    seen.add(src["id"])
                    blockers.append({"id": src["id"], "title": src["title"],
                                     "status": src["status"], "depth": depth + 1})
                    queue.append((src["id"], depth + 1))
        blockers.sort(key=lambda b: (b["depth"], b["id"]))
        return {"item": item, "blockers": blockers, "edges": edges}

    def plan_counts(self) -> dict:
        """project id -> {"milestones", "work_items", "ready", "blocked",
        "edges", "events"} counts, from one read. `ready` uses the SAME
        condition `ready_next()` does (`_READY_WHERE`). Projects with no plan
        rows are absent. Read-only; nothing is created."""
        if not self.exists():
            return {}
        with self._lock, self._db() as c:
            counts = {}

            def bump(project_id):
                return counts.setdefault(str(project_id),
                                         {"milestones": 0, "work_items": 0, "ready": 0,
                                          "blocked": 0, "edges": 0, "events": 0})

            for table, key in (("milestones", "milestones"), ("work_items", "work_items"),
                               ("work_edges", "edges"), ("project_events", "events")):
                for row in c.execute(f"SELECT project, COUNT(*) AS n FROM {table} "
                                     "GROUP BY project").fetchall():
                    bump(row["project"])[key] = int(row["n"])
            for row in c.execute("SELECT w.project AS project, COUNT(*) AS n "
                                 "FROM work_items w JOIN projects p ON p.id = w.project "
                                 f"WHERE {_READY_WHERE} GROUP BY w.project").fetchall():
                bump(row["project"])["ready"] = int(row["n"])
            for row in c.execute("SELECT w.project AS project, COUNT(*) AS n "
                                 "FROM work_items w JOIN projects p ON p.id = w.project "
                                 f"WHERE {_BLOCKED_WHERE} GROUP BY w.project").fetchall():
                bump(row["project"])["blocked"] = int(row["n"])
            return counts

    def plan_state(self, project_id: str) -> dict:
        """One project's appended plan fields plus its plan counts, from one
        read. The route views are deliberately NOT changed by this PR: the two
        apps' frozen contract keeps its exact keys."""
        with self._lock, self._db() as c:
            r = self._project_row(c, project_id)
            values = {column: (r[column] if column in r.keys() else None)
                      for column in PLAN_COLUMNS}
            values.update({"id": r["id"], "name": r["name"]})
            values.update(self.plan_counts().get(project_id)
                          or {"milestones": 0, "work_items": 0, "ready": 0,
                              "blocked": 0, "edges": 0, "events": 0})
            return values

    def project_next(self, limit: int = 3, *, sched=None,
                     project_id: Optional[str] = None) -> dict:
        """THE one "what should I work on next" answer, unioning the sources
        that already hold next-work so chat does not grow a fourth:
          * this store's ready work items (priority, then due date);
          * every active goal's next open step (jarvis_goals, read only);
          * each project's first open work-list item (the one scheduler).
        With `project_id`, only that project's own sources are read (a goal
        has no project link, so goals are then not a source).

        Returns {"items": [{"kind", "project_id", "project", "text", "by",
        "priority", ...}], "sources": {"ready": N, "goals": N|None,
        "work_lists": N|None}}. A None source means it could not be read, and
        the answer says so rather than claiming it is empty. Nothing is
        created: a goals.db that does not exist yet is not opened."""
        limit = max(1, int(limit))
        if project_id is not None and (not isinstance(project_id, str)
                                       or not _ID.fullmatch(project_id)):
            raise KeyError(project_id)
        items = []
        ready = self.ready_next(project_id=project_id, limit=1000) \
            if self.exists() else []
        for row in ready:
            items.append({"kind": "work_item", "project_id": row["project"],
                          "project": row["project_name"], "text": row["title"],
                          "by": row["due_date"] or "", "priority": row["priority"],
                          "status": row["status"], "id": row["id"]})
        sources = {"ready": len(ready), "goals": None, "work_lists": None,
                   "scope": project_id or ""}
        # ---- the goals store: an active goal's next open step ----
        try:
            import jarvis_goals as G
            goal_count = 0
            if G.db_path().is_file():
                store = G.get()
                active = [g for g in store.list()
                          if isinstance(g, dict) and g.get("status") == "active"]
                goal_count = len(active)
                if project_id is None:
                    for goal in active:
                        step = store.next_open_step(goal.get("id"))
                        if isinstance(step, dict) and str(step.get("step") or "").strip():
                            items.append({"kind": "goal", "project_id": "",
                                          "project": "", "priority": None,
                                          "text": str(step.get("step")).strip(),
                                          "by": str(step.get("by") or ""),
                                          "goal": str(goal.get("text") or ""),
                                          "status": "active"})
            sources["goals"] = goal_count
        except Exception:                       # noqa: BLE001 - unreadable, said so
            sources["goals"] = None
        # ---- the one scheduler: each project's first open work-list item ----
        try:
            todos = sched.todos() if sched is not None else None
            if todos is not None:
                lists = {}
                for project in (self.list() if self.exists() else []):
                    if project_id is not None and project.get("id") != project_id:
                        continue
                    work = project.get("work_list") or {}
                    if work.get("name"):
                        lists[project["id"]] = (work["name"], project.get("name") or "")
                picked = set()
                for todo in todos:
                    if not isinstance(todo, dict) or todo.get("kind") != "todo":
                        continue
                    if todo.get("state") not in ("active", "paused"):
                        continue
                    text = str(todo.get("text") or "").strip()
                    name = todo.get("list")
                    if not text:
                        continue
                    for pid, (list_name, project_name) in lists.items():
                        if list_name == name and pid not in picked:
                            picked.add(pid)
                            items.append({"kind": "work_list", "project_id": pid,
                                          "project": project_name, "text": text,
                                          "by": "", "priority": None,
                                          "status": ""})
                            break
                sources["work_lists"] = len(picked)
        except Exception:                       # noqa: BLE001 - unreadable, said so
            sources["work_lists"] = None
        # ONE answer: no text twice (a ready item and a work-list item the
        # owner wrote twice is one next thing, not two), ready items first.
        out, seen = [], set()
        for item in items:
            key = (item["project_id"], item["text"].casefold())
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return {"items": out[:limit], "sources": sources}

    def project_doctor(self) -> dict:
        """Contradictory plan rows, REPORTED and never fixed. Read-only: no
        row is repaired, no event is written. Returns {"ok", "problems",
        "count"}; each problem names a kind and the ids involved. It checks
        the things a row can say that cannot all be true: a row whose project
        is gone, a link to a missing item, a link across projects, a link from
        an item or project to itself, a closed item still blocked by an open
        one, an unknown status or link kind, and a circle of `blocks` or
        `parent_child` (a circle means nothing in it can ever be ready)."""
        if not self.exists():
            return {"ok": True, "problems": [], "count": 0}
        problems = []

        def problem(kind, **detail):
            problems.append(dict({"kind": kind}, **detail))

        with self._lock, self._db() as c:
            project_ids = {r[0] for r in c.execute("SELECT id FROM projects").fetchall()}
            item_ids = {r[0] for r in c.execute("SELECT id FROM work_items").fetchall()}
            for table in ("milestones", "work_items", "work_edges", "project_events"):
                for row in c.execute(f"SELECT id, project FROM {table}").fetchall():
                    if row["project"] not in project_ids:
                        problem("orphan-row", table=table, id=row["id"],
                                project=row["project"])
            for row in c.execute("SELECT id, status FROM milestones").fetchall():
                if row["status"] not in MILESTONE_STATUSES:
                    problem("unknown-milestone-status", id=row["id"],
                            status=row["status"])
            for row in c.execute("SELECT id, status, executor FROM work_items").fetchall():
                if row["status"] not in WORK_STATUSES:
                    problem("unknown-work-status", id=row["id"], status=row["status"])
                # PM3 (2026-11-20): the executor is a label, and an unknown one
                # would make the app draw a "Jarvis does it" it cannot run.
                if row["executor"] is not None and row["executor"] not in EXECUTORS:
                    problem("unknown-executor", id=row["id"],
                            executor=row["executor"])
            for row in c.execute("SELECT id, status FROM projects "
                                 "WHERE status IS NOT NULL").fetchall():
                if row["status"] not in PROJECT_STATUSES:
                    problem("unknown-project-status", id=row["id"], status=row["status"])
            for row in c.execute("SELECT id, project, kind, src, dst "
                                 "FROM work_edges").fetchall():
                if row["kind"] not in EDGE_KINDS:
                    problem("unknown-edge-kind", id=row["id"], edge_kind=row["kind"])
                if row["src"] == row["dst"]:
                    problem("self-link", id=row["id"], src=row["src"])
                if row["src"] not in item_ids or row["dst"] not in item_ids:
                    problem("orphan-link", id=row["id"], src=row["src"], dst=row["dst"])
            for row in c.execute(
                    "SELECT e.id AS id, e.project AS project FROM work_edges e "
                    "JOIN work_items s ON s.id = e.src "
                    "JOIN work_items d ON d.id = e.dst "
                    "WHERE e.project != s.project OR e.project != d.project").fetchall():
                problem("link-project-mismatch", id=row["id"], project=row["project"])
            for row in c.execute(
                    "SELECT DISTINCT e.dst AS id FROM work_edges e "
                    "JOIN work_items b ON b.id = e.src "
                    "JOIN work_items w ON w.id = e.dst "
                    "WHERE e.kind = 'blocks' "
                    "AND b.status NOT IN ('done', 'cancelled') "
                    "AND w.status IN ('done', 'cancelled')").fetchall():
                problem("closed-item-blocked", id=row["id"])
            for kind in ORDERING_EDGES:
                for circle in self._find_cycles(c, kind):
                    problem("link-circle", edge_kind=kind, ids=circle)
        return {"ok": not problems, "problems": problems, "count": len(problems)}

    def _find_cycles(self, c, kind: str) -> list:
        """Every circle in one kind's links, each as the ids walked (the
        closing id appears twice). Iterative, so a long chain cannot hit
        Python's recursion limit."""
        edges = {}
        for row in c.execute("SELECT src, dst FROM work_edges WHERE kind = ?",
                             (kind,)).fetchall():
            edges.setdefault(row["src"], []).append(row["dst"])
        colour, circles = {}, []
        for start in list(edges) + [n for ns in edges.values() for n in ns]:
            if colour.get(start):
                continue
            colour[start] = 1
            path = [start]
            stack = [(start, iter(edges.get(start, ())))]
            while stack:
                node, children = stack[-1]
                advanced = False
                for child in children:
                    state = colour.get(child, 0)
                    if state == 1:
                        circles.append(path[path.index(child):] + [child])
                    elif state == 0:
                        colour[child] = 1
                        path.append(child)
                        stack.append((child, iter(edges.get(child, ()))))
                        advanced = True
                        break
                if not advanced:
                    colour[node] = 2
                    stack.pop()
                    path.pop()
        return circles

    # ---- PM2 (2026-11-20): the import/seed, checkpoints and the hub note ----
    # The store's own door for "put the plan the owner already has into this
    # plan store". Like the PM1 writes above it raises no card itself: the
    # TOOL is the carded door (jarvis_agent), and this file only ever writes
    # once a yes was given. Everything here reads the sources READ-ONLY and
    # writes the source's own words - never a date, a name or a priority the
    # source did not carry.

    def _seeded(self, c) -> dict:
        """{source key: {"kind", "id"}} already imported, from the append-only
        log. One read; the import's whole idempotence rests on this."""
        found = {}
        for row in c.execute("SELECT detail FROM project_events WHERE kind = ?",
                             (SEED_EVENT,)).fetchall():
            try:
                detail = json.loads(row["detail"] or "{}")
            except (TypeError, ValueError):
                continue
            source = str(detail.get("source") or "")
            if not source or source in found:
                continue
            found[source] = {"kind": str(detail.get("kind") or ""),
                             "id": str(detail.get("item") or detail.get("milestone") or "")}
        return found

    def _seed_items(self) -> tuple:
        """(items, edges, skipped, sources) - a pure read of the two stores that
        already hold the owner's work. Nothing is created: a store that is not
        there is not opened."""
        items, edges, skipped = [], [], []
        sources = {"goals": 0, "goal_steps": 0, "work_lists": 0,
                   "work_list_items": 0}
        projects = self.list() if self.exists() else []
        by_goal: dict = {}
        for project in projects:
            for goal_id in project.get("goals") or []:
                by_goal.setdefault(str(goal_id), []).append(project)
        # ---- a goal's own steps (goals.db, read only) ----
        try:
            import jarvis_goals as G
            goal_rows = list(G.get().list()) if G.db_path().is_file() else []
            goals_ok = True
        except Exception:                    # noqa: BLE001 - unreadable, said so
            goal_rows, goals_ok = [], False
        if not goals_ok:
            skipped.append({"source": "goals", "kind": "goal",
                            "why": "the goals store could not be read here"})
        sources["goals"] = len(goal_rows)
        for goal in goal_rows:
            gid = str(goal.get("id") or "")
            words = str(goal.get("text") or "").strip()
            if not gid or not words:
                continue
            owners = by_goal.get(gid) or []
            if len(owners) != 1:
                skipped.append({
                    "source": f"goal:{gid}", "kind": "goal",
                    "title": _clip(words, MAX_WORK_TITLE),
                    "why": ("no project links this goal" if not owners else
                            "more than one project links this goal")})
                continue
            status = str(goal.get("status") or "")
            if status == "draft":
                skipped.append({"source": f"goal:{gid}", "kind": "goal",
                                "title": _clip(words, MAX_WORK_TITLE),
                                "why": "this goal is still a draft"})
                continue
            project = owners[0]
            mkey = f"goal:{gid}"
            items.append({
                "source": mkey, "kind": "milestone",
                "project": project["id"], "project_name": project["name"],
                "milestone": "", "title": _clip(words, MAX_MILESTONE_TITLE),
                "status": {"done": "done", "active": "active"}.get(status, "planned"),
                "priority": None, "due_date": None, "detail": ""})
            step_keys = {}
            for step in goal.get("plan") or []:
                sid = str(step.get("id") or "")
                step_words = str(step.get("step") or "").strip()
                if not sid or not step_words:
                    continue
                key = f"goal_step:{gid}:{sid}"
                step_keys[sid] = key
                state = str(step.get("state") or "")
                done = state in ("done", "met_by_number")
                detail = f'From the goal "{_clip(words, MAX_WORK_TITLE)}".'
                by = str(step.get("by") or "").strip()
                if by:
                    # The goal's own rule (jarvis_goals.py:71-76): `by` is a
                    # rough label, never a calendar date. It is kept as the
                    # owner's words and the item stays UNDATED.
                    detail += f' Their own rough date: "{_clip(by, 40)}" - not a calendar date.'
                items.append({
                    "source": key, "kind": "work_item",
                    "project": project["id"], "project_name": project["name"],
                    "milestone": mkey,
                    "title": _clip(step_words, MAX_WORK_TITLE),
                    "status": "done" if done else "backlog",
                    "priority": None, "due_date": None, "detail": detail})
                sources["goal_steps"] += 1
            for step in goal.get("plan") or []:
                sid = str(step.get("id") or "")
                for need in step.get("needs") or []:
                    need = str(need)
                    if sid in step_keys and need in step_keys and need != sid:
                        edges.append({"kind": "blocks", "from": step_keys[need],
                                      "to": step_keys[sid]})
        # ---- each project's work list (the one scheduler, read only) ----
        with_lists = [(p, (p.get("work_list") or {}).get("name") or "")
                      for p in projects if (p.get("work_list") or {}).get("name")]
        sources["work_lists"] = len(with_lists)
        try:
            todos = _schedule_store().todos() if with_lists else []
            sched_ok = True
        except Exception:                    # noqa: BLE001 - unreadable, said so
            todos, sched_ok = [], False
        if not sched_ok:
            skipped.append({"source": "work_lists", "kind": "work_list",
                            "why": "the scheduler could not be read here"})
        for project, list_name in with_lists:
            for todo in todos:
                if not isinstance(todo, dict):
                    continue
                if todo.get("kind") != "todo" or todo.get("list") != list_name:
                    continue
                if todo.get("state") not in ("active", "paused"):
                    continue
                text = str(todo.get("text") or "").strip()
                todo_id = str(todo.get("id") or "")
                if not text or not todo_id:
                    continue
                # The scheduler's own due date, when it really has one: the
                # owner typed it there, so importing it invents nothing.
                due_date = None
                due = todo.get("due")
                if isinstance(due, (int, float)) and not isinstance(due, bool):
                    due_date = time.strftime("%Y-%m-%d", time.localtime(float(due)))
                items.append({
                    "source": f"todo:{todo_id}", "kind": "work_item",
                    "project": project["id"], "project_name": project["name"],
                    "milestone": "", "title": _clip(text, MAX_WORK_TITLE),
                    "status": "backlog", "priority": None, "due_date": due_date,
                    "detail": f'From the "{_list_title(list_name)}" work list.'})
                sources["work_list_items"] += 1
        if len(items) > MAX_SEED_ITEMS:
            skipped.append({"source": "cap", "kind": "cap",
                            "why": f"only the first {MAX_SEED_ITEMS} rows are "
                                   f"imported in one run"})
            keep = {item["source"] for item in items[:MAX_SEED_ITEMS]}
            items = items[:MAX_SEED_ITEMS]
            edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
        return items, edges, skipped, sources

    def seed_sources(self) -> dict:
        """The proposal the import card shows: what WOULD be saved, what is
        already saved, and what was skipped and why. Reads only - a dry run is
        this function."""
        items, edges, skipped, sources = self._seed_items()
        already = {}
        if self.exists():
            with self._lock, self._db() as c:
                already = self._seeded(c)
        pending = [item for item in items if item["source"] not in already]
        for item in items:
            if item["source"] in already:
                item["already"] = True
        return {"items": items, "pending": pending, "edges": edges,
                "skipped": skipped, "sources": sources,
                "already": len(items) - len(pending)}

    def seed_plan(self, dry_run: bool = True) -> dict:
        """Import the source's own plan rows into this store. `dry_run=True`
        reads and proposes and writes NOTHING (the default); `dry_run=False`
        is only ever called after an approval card, and writes in ONE
        transaction: the milestones, the work items, the `blocks` links and one
        event per created row. A second run creates nothing new."""
        proposal = self.seed_sources()
        pending = proposal["pending"]
        known = {}
        if self.exists():
            with self._lock, self._db() as c:
                known = self._seeded(c)
        result = {"dry_run": bool(dry_run), "items": pending,
                  "edges": proposal["edges"], "skipped": proposal["skipped"],
                  "sources": proposal["sources"],
                  "already": proposal["already"], "wrote": False,
                  "created": {"milestones": 0, "work_items": 0, "edges": 0},
                  "events": 0}
        if dry_run or not pending:
            result["message"] = (SEED_NOTHING if dry_run and not pending
                                 and not proposal["items"] else
                                 SEED_ALL_DONE if not pending else "")
            return result
        ids = {source: row["id"] for source, row in known.items()
               if row.get("id")}
        by_source = {item["source"]: item for item in pending}
        created = result["created"]
        now = self.clock()
        skipped = list(result["skipped"])
        with self._lock, self._db() as c:
            # Positions continue after any milestone already there.
            positions: dict = {}
            for project_id in {item["project"] for item in pending}:
                row = c.execute("SELECT COALESCE(MAX(position), -1) + 1 "
                                "FROM milestones WHERE project = ?",
                                (project_id,)).fetchone()
                positions[project_id] = int(row[0])
            for item in pending:
                if item["kind"] != "milestone":
                    continue
                mid = _new_id()
                position = positions[item["project"]]
                positions[item["project"]] = position + 1
                c.execute("INSERT INTO milestones (id, project, title, status, "
                          "due_date, position, created, changed) "
                          "VALUES (?,?,?,?,?,?,?,?)",
                          (mid, item["project"], item["title"], item["status"],
                           None, position, now, now))
                ids[item["source"]] = mid
                self._event(c, item["project"], SEED_EVENT, mid,
                            {"source": item["source"], "kind": "milestone",
                             "item": mid})
                created["milestones"] += 1
                result["events"] += 1
            for item in pending:
                if item["kind"] != "work_item":
                    continue
                wid = _new_id()
                milestone = ids.get(item["milestone"] or "") or None
                c.execute("INSERT INTO work_items (id, project, milestone, title, "
                          "detail, status, priority, due_date, created, changed) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (wid, item["project"], milestone, item["title"],
                           item["detail"], item["status"], item["priority"],
                           item["due_date"], now, now))
                ids[item["source"]] = wid
                self._event(c, item["project"], SEED_EVENT, wid,
                            {"source": item["source"], "kind": "work_item",
                             "item": wid})
                created["work_items"] += 1
                result["events"] += 1
            for edge in proposal["edges"]:
                src, dst = ids.get(edge["from"] or ""), ids.get(edge["to"] or "")
                if not src or not dst:
                    continue
                if c.execute("SELECT 1 FROM work_edges WHERE kind = ? AND src = ? "
                             "AND dst = ?", (edge["kind"], src, dst)).fetchone():
                    continue
                if self._would_cycle(c, edge["kind"], src, dst):
                    skipped.append({"source": edge["from"], "kind": "edge",
                                    "why": "that link would make a circle, so "
                                           "it was not imported"})
                    continue
                project_id = str(by_source.get(edge["from"], {}).get("project")
                                 or c.execute("SELECT project FROM work_items "
                                              "WHERE id = ?", (src,)).fetchone()[0])
                eid = _new_id()
                c.execute("INSERT INTO work_edges (id, project, kind, src, dst, "
                          "created) VALUES (?,?,?,?,?,?)",
                          (eid, project_id, edge["kind"], src, dst, now))
                self._event(c, project_id, SEED_EVENT, eid,
                            {"source": f"edge:{edge['from']}:{edge['to']}",
                             "kind": "edge", "item": eid})
                created["edges"] += 1
                result["events"] += 1
            for project_id in {item["project"] for item in pending}:
                c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                          (now, project_id))
        result["wrote"] = True
        result["skipped"] = skipped
        _audit("projects.plan.seed", {"milestones": created["milestones"],
                                      "work_items": created["work_items"],
                                      "edges": created["edges"]})
        return result

    def apply_plan(self, project_id: str, milestones: list, items: list,
                   blocks: list) -> dict:
        """Write ONE proposed plan - the milestones, the work items and the
        `blocks` links between them - on the strength of the one approval card
        that showed it. NOTHING RUNS: no command, no job, no other store is
        touched; this is rows, exactly like the owner typing them in.

        The plan is validated BEFORE the first write, and a circular `blocks`
        set is refused with the whole plan untouched (the same rule
        `add_edge()` keeps for one link). No date is accepted here at all: a
        plan the model wrote may never carry a date the owner did not give."""
        if not isinstance(milestones, list) or not isinstance(items, list):
            raise ValueError("a plan is a list of milestones and a list of items")
        if len(milestones) > MAX_PLAN_MILESTONES:
            raise ValueError(f"a plan keeps at most {MAX_PLAN_MILESTONES} milestones")
        if len(items) > MAX_PLAN_ITEMS:
            raise ValueError(f"a plan keeps at most {MAX_PLAN_ITEMS} work items")
        clean_milestones = []
        for m in milestones:
            if not isinstance(m, dict):
                raise ValueError("a milestone is an object with a title")
            title = _one_line(m.get("title"), MAX_MILESTONE_TITLE,
                              "a milestone's title", required=True)
            status = str(m.get("status") or "planned")
            if status not in MILESTONE_STATUSES:
                raise ValueError("a milestone is " + ", ".join(MILESTONE_STATUSES))
            clean_milestones.append({"title": title, "status": status})
        clean_items = []
        for i in items:
            if not isinstance(i, dict):
                raise ValueError("a work item is an object with a title")
            body = i
            title = _one_line(body.get("title"), MAX_WORK_TITLE,
                              "a work item's title", required=True)
            status = str(body.get("status") or "backlog")
            if status not in WORK_STATUSES:
                raise ValueError("a work item is " + ", ".join(WORK_STATUSES))
            priority = _clean_priority(body.get("priority"))
            milestone = body.get("milestone")
            if milestone in (None, ""):
                milestone = None
            else:
                try:
                    milestone = int(milestone)
                except (TypeError, ValueError):
                    raise ValueError("an item's milestone is its number in the "
                                     "plan's milestone list") from None
                if not 0 <= milestone < len(clean_milestones):
                    raise ValueError("that item names a milestone the plan does not have")
            clean_items.append({
                "title": title,
                "detail": _text(body.get("detail"), MAX_WORK_DETAIL, "a work item's detail"),
                "status": status, "priority": priority, "milestone": milestone})
        clean_blocks = []
        adjacency: dict = {}
        for pair in blocks or []:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("a blocking pair is [the item that must finish "
                                 "first, the item it blocks]")
            try:
                src, dst = int(pair[0]), int(pair[1])
            except (TypeError, ValueError):
                raise ValueError("a blocking pair names two items by their "
                                 "number in the plan's item list") from None
            if not (0 <= src < len(clean_items) and 0 <= dst < len(clean_items)):
                raise ValueError("a blocking pair names an item the plan does not have")
            if src == dst:
                raise ValueError(SELF_EDGE)
            clean_blocks.append((src, dst))
            adjacency.setdefault(src, []).append(dst)
        # A circle in the PROPOSED plan is refused whole: one edge written would
        # already block work silently, and the owner approved one picture.
        for start in adjacency:
            seen, stack = set(), [start]
            while stack:
                at = stack.pop()
                for nxt in adjacency.get(at, ()):
                    if nxt == start:
                        raise ValueError(CYCLE_EDGE)
                    if nxt in seen:
                        continue
                    seen.add(nxt)
                    stack.append(nxt)
        now = self.clock()
        result = {"milestones": 0, "work_items": 0, "edges": 0,
                  "project": project_id}
        with self._lock, self._db() as c:
            self._project_row(c, project_id)
            position = int(c.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM milestones "
                "WHERE project = ?", (project_id,)).fetchone()[0])
            milestone_ids = []
            for m in clean_milestones:
                mid = _new_id()
                c.execute("INSERT INTO milestones (id, project, title, status, "
                          "due_date, position, created, changed) "
                          "VALUES (?,?,?,?,?,?,?,?)",
                          (mid, project_id, m["title"], m["status"], None,
                           position, now, now))
                position += 1
                milestone_ids.append(mid)
                self._event(c, project_id, "milestone_added", mid,
                            {"status": m["status"]})
                result["milestones"] += 1
            item_ids = []
            for item in clean_items:
                wid = _new_id()
                milestone = (milestone_ids[item["milestone"]]
                             if item["milestone"] is not None else None)
                c.execute("INSERT INTO work_items (id, project, milestone, title, "
                          "detail, status, priority, due_date, created, changed) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (wid, project_id, milestone, item["title"],
                           item["detail"], item["status"], item["priority"],
                           None, now, now))
                item_ids.append(wid)
                self._event(c, project_id, "work_item_added", wid,
                            {"status": item["status"]})
                result["work_items"] += 1
            for src, dst in clean_blocks:
                eid = _new_id()
                c.execute("INSERT INTO work_edges (id, project, kind, src, dst, "
                          "created) VALUES (?,?,?,?,?,?)",
                          (eid, project_id, "blocks", item_ids[src],
                           item_ids[dst], now))
                self._event(c, project_id, "edge_added", eid,
                            {"kind": "blocks", "src": item_ids[src],
                             "dst": item_ids[dst]})
                result["edges"] += 1
            c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                      (now, project_id))
        _audit("projects.plan.apply", {"project": project_id,
                                       "milestones": result["milestones"],
                                       "work_items": result["work_items"],
                                       "edges": result["edges"]})
        return result

    def resolve_project(self, words) -> dict:
        """One project from what the model was given: its id, or enough of its
        name. Ambiguity is refused with the candidates named - never guessed."""
        text = str(words or "").strip()
        if not text:
            raise ValueError("say which project")
        if _ID.fullmatch(text):
            try:
                return self.get(text)
            except KeyError:
                raise ValueError("there is no project with that id") from None
        projects = self.list() if self.exists() else []
        exact = [p for p in projects if p["name"].casefold() == text.casefold()]
        if len(exact) == 1:
            return exact[0]
        hits = [p for p in projects if text.casefold() in p["name"].casefold()]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise ValueError(f'there is no project called "{_clip(text, 60)}"')
        names = ", ".join(f'"{p["name"]}"' for p in hits[:4])
        raise ValueError(f'more than one project matches "{_clip(text, 60)}": '
                         f'{names} - say which one')

    def find_work_item(self, words) -> dict:
        """One work item from what the model was given: its id, or enough of its
        title. Ambiguity is refused with the candidates named."""
        text = str(words or "").strip()
        if not text:
            raise ValueError("say which work item")
        if not self.exists():
            raise ValueError("there are no work items yet")
        items = self.work_items()
        if _ID.fullmatch(text):
            for item in items:
                if item["id"] == text:
                    return item
            raise ValueError("there is no work item with that id")
        exact = [i for i in items if i["title"].casefold() == text.casefold()]
        if len(exact) == 1:
            return exact[0]
        hits = [i for i in items if text.casefold() in i["title"].casefold()]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise ValueError(f'there is no work item called "{_clip(text, 60)}"')
        names = ", ".join(f'"{i["title"]}"' for i in hits[:4])
        raise ValueError(f'more than one work item matches "{_clip(text, 60)}": '
                         f'{names} - say which one')

    # ---- PM3 (2026-11-20): the execution and brief bridges --------------------
    # The store's own reads and writes for the bridges. A bridge write is ONE
    # row plus ONE append-only event, exactly like the plan writes above; a
    # bridge READ creates nothing. Nothing in this section runs a command,
    # opens a socket or raises a card: the GitHub read arrives through the
    # caller's injected `fetch` (jarvis_github.py's own seam), the job state
    # comes from jarvis_tasks.py's own store read, and the brief and the daily
    # list are projections over rows the owner already has.

    def _open_project_ids(self) -> set:
        """The ids of projects that still offer work (not done/archived)."""
        if not self.exists():
            return set()
        with self._lock, self._db() as c:
            return {r["id"] for r in c.execute("SELECT id, status FROM projects")
                    if r["status"] is None or r["status"] not in CLOSED_PROJECT_STATUSES}

    def link_task(self, item_id: str, task_id=None, *, task_store=None) -> dict:
        """Attach (or clear) the durable `jarvis_tasks.py` job this item follows.

        NO RUN HAPPENS HERE. This is the link the deferred Run Step dispatch
        would write (docs/ARCHITECTURE.md section 8); what this PR proves is
        that once such a link exists, the job's own state is projected onto the
        work item by `sync_task_status()` below, through the existing status
        path and its receipt. A task id that is not in the task list is refused
        in words when the list is readable; when the task list is not shipped
        here the id is kept as given (the store never depends on it)."""
        tid = None if task_id in (None, "") else str(task_id).strip()
        if tid is not None:
            if not _TASK_ID.fullmatch(tid):
                raise ValueError("a job id is 32 or 64 lowercase hex characters.")
            tasks = task_store if task_store is not None else _tasks_store()
            if tasks is not None and tasks.get_task(tid) is None:
                raise ValueError(LINK_NO_TASK)
        now = self.clock()
        with self._lock, self._db() as c:
            row = self._work_row(c, item_id)
            c.execute("UPDATE work_items SET linked_task_id = ?, changed = ? WHERE id = ?",
                      (tid, now, item_id))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                      (now, row["project"]))
            self._event(c, row["project"], "work_item_link", item_id,
                        {"task": tid or ""})
            view = self._work_view(c, self._work_row(c, item_id))
        _audit("projects.work.link_task", {"item": item_id, "linked": bool(tid)})
        return view

    def link_pr(self, item_id: str, number=None) -> dict:
        """Attach (or clear) the GitHub pull request this item follows.

        A NUMBER ONLY: the state and the CI status are never typed in, they
        are read later by `sync_prs()` and stored as a projection. Clearing the
        link clears the projection with it, so a stale "merged" can never
        outlive the link that justified it."""
        pr = None
        if number not in (None, ""):
            if isinstance(number, bool):
                raise ValueError(LINK_NO_PR)
            text = str(number).strip().lstrip("#").strip()
            if not text.isdigit() or int(text) < 1 or int(text) > 10 ** 12:
                raise ValueError(LINK_NO_PR)
            pr = int(text)
        now = self.clock()
        with self._lock, self._db() as c:
            row = self._work_row(c, item_id)
            c.execute("UPDATE work_items SET linked_pr_number = ?, "
                      "linked_pr_state = NULL, linked_ci_status = NULL, "
                      "changed = ? WHERE id = ?", (pr, now, item_id))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                      (now, row["project"]))
            self._event(c, row["project"], "work_item_link", item_id,
                        {"pr": pr or 0})
            view = self._work_view(c, self._work_row(c, item_id))
        _audit("projects.work.link_pr", {"item": item_id, "linked": pr is not None})
        return view

    def sync_task_status(self, project_id: Optional[str] = None, *,
                         task_store=None) -> dict:
        """Project every linked durable job's own state onto its work item.

        READ-ONLY toward the task list, and read-only toward GitHub; the only
        write is the work item's own status through `set_work_item_status()`,
        which is the EXISTING path: one `project_events` row and one Undo
        receipt per real change. A job's state maps as
        `TASK_STATE_TO_WORK` says - a finished job goes to `in_review`, never
        to `done` - and a job that failed, was cancelled or went blocked is
        REPORTED, never given a made-up status. A closed work item is never
        pulled back open. Nothing runs."""
        out: dict = {"read": 0, "linked": 0, "changed": [], "unchanged": 0,
                     "skipped": []}
        if not self.exists():
            return out
        if project_id is not None and (not isinstance(project_id, str)
                                       or not _ID.fullmatch(project_id)):
            raise KeyError(project_id)
        items = [i for i in self.work_items(project_id) if i.get("linked_task_id")]
        out["linked"] = len(items)
        if not items:
            return out
        tasks = task_store if task_store is not None else _tasks_store()
        if tasks is None:
            out["skipped"].append({"why": "the task list is not available here"})
            return out
        for item in items:
            task = tasks.get_task(item["linked_task_id"])
            if task is None:
                out["skipped"].append({"item": item["id"], "task": item["linked_task_id"],
                                       "why": "the linked job is not in the task list"})
                continue
            out["read"] += 1
            target = TASK_STATE_TO_WORK.get(str(task.status))
            if target is None:
                out["skipped"].append({
                    "item": item["id"], "task": task.id, "state": str(task.status),
                    "why": f"a {task.status} job does not move the work item - "
                           f"it stays {item['status']}"})
                continue
            if item["status"] in CLOSED_STATUSES:
                out["skipped"].append({"item": item["id"], "task": task.id,
                                       "state": str(task.status),
                                       "why": "the work item is already closed"})
                continue
            if item["status"] == target:
                out["unchanged"] += 1
                continue
            try:
                view = self.set_work_item_status(item["id"], target)
            except (KeyError, ValueError) as exc:
                out["skipped"].append({"item": item["id"], "task": task.id,
                                       "why": str(exc)[:200]})
                continue
            out["changed"].append({"item": item["id"], "task": task.id,
                                   "from": item["status"], "to": view["status"]})
        _audit("projects.work.sync_task", {"linked": out["linked"],
                                           "read": out["read"],
                                           "changed": len(out["changed"])})
        return out

    def _record_pr_state(self, item: dict, repo: str, got: dict) -> tuple:
        """Store ONE read PR state as a projection, and offer a merge once.

        Returns (changed, offer). An OFFER is appended to the append-only log
        the FIRST time a linked, still-open work item's PR is seen merged; the
        work item's STATUS is never written here. The same merged PR seen again
        writes nothing."""
        state = str(got.get("state") or "")
        ci = str(got.get("ci") or "unknown")
        if state not in PR_STATES:
            return False, None
        if ci not in CI_STATES:
            ci = "unknown"
        offer = None
        changed = False
        now = self.clock()
        with self._lock, self._db() as c:
            row = self._work_row(c, item["id"])
            if (row["linked_pr_state"], row["linked_ci_status"]) != (state, ci):
                c.execute("UPDATE work_items SET linked_pr_state = ?, "
                          "linked_ci_status = ?, changed = ? WHERE id = ?",
                          (state, ci, now, item["id"]))
                self._event(c, row["project"], "pr_synced", item["id"],
                            {"pr": int(row["linked_pr_number"] or 0),
                             "state": state, "ci": ci})
                changed = True
            if state == "merged" and row["status"] not in CLOSED_STATUSES:
                detail = json.dumps({"pr": int(row["linked_pr_number"] or 0)},
                                    sort_keys=True)
                already = c.execute(
                    "SELECT 1 FROM project_events WHERE kind = 'pr_merged_offer' "
                    "AND subject = ? AND detail = ?",
                    (item["id"], detail)).fetchone()
                if not already:
                    self._event(c, row["project"], "pr_merged_offer", item["id"],
                                {"pr": int(row["linked_pr_number"] or 0)})
                offer = {"item": item["id"], "project": row["project"],
                         "project_name": item.get("project_name") or "",
                         "title": row["title"],
                         "pr": int(row["linked_pr_number"] or 0), "ci": ci,
                         "repo": repo,
                         "message": PR_MERGED_OFFER_WORDS.format(
                             pr=int(row["linked_pr_number"] or 0), title=row["title"])}
        return changed, offer

    def sync_prs(self, project_id: Optional[str] = None, *, fetch=None,
                 github=None) -> dict:
        """Read each linked pull request's own state and CI, and store the
        projection. NO CARD, NO GITHUB WRITE, NO STATUS CHANGE.

        The read is `jarvis_github.pull_request_state()` (README only: every
        request it makes is a GET on api.github.com through the module's own
        token and transport), and the offer a merged PR creates is surfaced by
        `pr_merged_offers()` - the move to done stays the owner's own status
        change with its normal receipt and Undo. A project with no
        `linked_repo` is named in `errors` and skipped; a read that fails
        changes nothing and is returned in plain words."""
        out: dict = {"read": 0, "linked": 0, "synced": [], "offers": [],
                     "errors": []}
        if not self.exists():
            return out
        if project_id is not None and (not isinstance(project_id, str)
                                       or not _ID.fullmatch(project_id)):
            raise KeyError(project_id)
        items = [i for i in self.work_items(project_id) if i.get("linked_pr_number")]
        out["linked"] = len(items)
        if not items:
            return out
        reader = github if github is not None else _github_module()
        if reader is None:
            out["errors"].append({"why": "the GitHub reader is not available here"})
            return out
        repos: dict = {}
        for item in items:
            if item["project"] not in repos:
                try:
                    repos[item["project"]] = str(
                        (self.plan_state(item["project"]) or {}).get("linked_repo")
                        or "").strip()
                except Exception:                       # noqa: BLE001
                    repos[item["project"]] = ""
            repo = repos[item["project"]]
            if not repo:
                out["errors"].append({
                    "item": item["id"],
                    "why": "this project has no linked repository, so its PR "
                           "cannot be read"})
                continue
            try:
                got = reader.pull_request_state(repo, item["linked_pr_number"],
                                                fetch=fetch)
            except Exception as exc:                    # noqa: BLE001
                got = {"ok": False, "error": f"the GitHub reader raised "
                                             f"{type(exc).__name__}"}
            if not got.get("ok"):
                out["errors"].append({"item": item["id"], "repo": repo,
                                      "why": str(got.get("error")
                                                 or "GitHub could not be read")})
                continue
            out["read"] += 1
            changed, offer = self._record_pr_state(item, repo, got)
            if changed:
                out["synced"].append({"item": item["id"],
                                      "pr": int(item["linked_pr_number"]),
                                      "state": str(got.get("state") or ""),
                                      "ci": str(got.get("ci") or "unknown")})
            if offer is not None:
                out["offers"].append(offer)
        _audit("projects.work.sync_pr", {"linked": out["linked"],
                                         "read": out["read"],
                                         "synced": len(out["synced"]),
                                         "offers": len(out["offers"])})
        return out

    def pr_merged_offers(self) -> list:
        """Every OPEN work item whose linked PR is known to be merged.

        Read-only: this is the OFFER the digest and the hub note surface. The
        move to done is the existing status path and its Undo receipt."""
        if not self.exists():
            return []
        open_projects = self._open_project_ids()
        out = []
        for item in self.work_items():
            if (item.get("linked_pr_state") != "merged"
                    or item["status"] in CLOSED_STATUSES
                    or item["project"] not in open_projects):
                continue
            out.append({"item": item["id"], "project": item["project"],
                        "project_name": item["project_name"],
                        "title": item["title"],
                        "pr": item.get("linked_pr_number"),
                        "ci": item.get("linked_ci_status") or "",
                        "executor": item.get("executor") or "owner",
                        "message": PR_MERGED_OFFER_WORDS.format(
                            pr=item.get("linked_pr_number"),
                            title=item["title"])})
        return out

    def morning_brief(self, now: Optional[float] = None) -> dict:
        """The project half of the morning digest: (a) work due within 48
        hours, (b) the top 3 ready items across ACTIVE projects, (c) stalled
        `in_progress` items untouched for more than seven days - and any
        merged-PR OFFER. Read-only: nothing is written, nothing is spoken and
        nothing is created; `available` is False only when the store cannot be
        read at all. The digest itself decides what to do with it."""
        now = float(now if now is not None else self.clock())
        read = time.strftime("%Y-%m-%d", time.localtime(now))
        out: dict = {"available": True, "read": read, "due_48h": [], "ready": [],
                     "stalled": [], "offers": [],
                     "counts": {"due_48h": 0, "ready": 0, "stalled": 0,
                                "offers": 0}}
        if not self.exists():
            return out
        open_projects = self._open_project_ids()
        horizon = time.strftime("%Y-%m-%d",
                                time.localtime(now + DUE_SOON_HOURS * 3600))
        items = [i for i in self.work_items() if i["project"] in open_projects]
        due, stalled = [], []
        for item in items:
            if item["status"] in CLOSED_STATUSES:
                continue
            if item["due_date"] and item["due_date"] <= horizon:
                due.append({"item": item["id"], "project": item["project"],
                            "project_name": item["project_name"],
                            "title": item["title"],
                            "due_date": item["due_date"],
                            "overdue": item["due_date"] < read,
                            "status": item["status"],
                            "created": item["created"]})
            if (item["status"] == "in_progress"
                    and float(item["changed"]) < now - STALLED_DAYS * 86400):
                stalled.append({"item": item["id"], "project": item["project"],
                                "project_name": item["project_name"],
                                "title": item["title"],
                                "changed": item["changed"],
                                "untouched_days": int(max(0.0, now
                                                          - float(item["changed"]))
                                                      // 86400)})
        due.sort(key=lambda row: (row["due_date"], row["created"], row["item"]))
        stalled.sort(key=lambda row: (row["changed"], row["item"]))
        ready = []
        for row in self.ready_next(limit=BRIEF_READY_MAX):
            ready.append({"item": row["id"], "title": row["title"],
                          "project": row["project"],
                          "project_name": row["project_name"],
                          "priority": row["priority"],
                          "due_date": row["due_date"],
                          "executor": row.get("executor") or "owner",
                          "status": row["status"]})
        offers = self.pr_merged_offers()
        out["due_48h"], out["stalled"] = due[:BRIEF_DUE_MAX], stalled[:BRIEF_STALLED_MAX]
        out["ready"], out["offers"] = ready, offers
        out["counts"] = {"due_48h": len(due), "ready": len(ready),
                         "stalled": len(stalled), "offers": len(offers),
                         "stalled_shown": len(out["stalled"])}
        return out

    def daily_projection(self, now: Optional[float] = None) -> list:
        """Work items that belong on TODAY's to-do list: due today or earlier,
        still open, in a project that still offers work.

        Read-only: this returns rows; it writes nothing and creates no
        scheduler row. `jarvis_schedule.py` adds them to the daily list it
        already serves, with the SAME carry-over tag it gives its own rows -
        so a work item is never typed into the scheduler twice."""
        now = float(now if now is not None else self.clock())
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if not self.exists():
            return []
        open_projects = self._open_project_ids()
        rows = []
        for item in self.work_items():
            if (not item["due_date"] or item["due_date"] > today
                    or item["status"] in CLOSED_STATUSES
                    or item["project"] not in open_projects):
                continue
            rows.append({"id": daily_row_id(item["project"], item["id"]),
                         "work_item": item["id"],
                         "project_id": item["project"],
                         "project_name": item["project_name"],
                         "title": item["title"],
                         "due_date": item["due_date"],
                         "status": item["status"],
                         "priority": item["priority"],
                         "executor": item.get("executor") or "owner",
                         "created": item["created"]})
        rows.sort(key=lambda row: (row["due_date"],
                                   row["priority"] is None,
                                   row["priority"] if row["priority"] is not None else 0,
                                   row["created"], row["work_item"]))
        return rows[:DAILY_MAX]

    def record_checkpoint(self, project_id: str, text, *,
                          kind: str = "checkpoint",
                          item_id: Optional[str] = None) -> dict:
        """One checkpoint or lesson, in the append-only event log. No card: a
        reflection is the owner's own note about their own project, like a
        project note. Returns the event."""
        kind = str(kind or "checkpoint")
        if kind not in CHECKPOINT_KINDS:
            raise ValueError("a checkpoint is " + " or ".join(CHECKPOINT_KINDS))
        words = _text(text, MAX_CHECKPOINT, "a checkpoint", required=True)
        now = self.clock()
        with self._lock, self._db() as c:
            self._project_row(c, project_id)
            item = None
            if item_id not in (None, ""):
                item = str(item_id)
                row = self._work_row(c, item)
                if row["project"] != project_id:
                    raise ValueError("that work item is not in this project")
            evid = _new_id()
            c.execute("INSERT INTO project_events (id, project, at, kind, subject, "
                      "detail) VALUES (?,?,?,?,?,?)",
                      (evid, project_id, now, kind, item or project_id,
                       json.dumps({"text": words, "item": item or ""},
                                  sort_keys=True)))
            c.execute("UPDATE projects SET changed = ? WHERE id = ?",
                      (now, project_id))
        _audit("projects.plan." + kind, {"project": project_id, "item": bool(item)})
        return {"id": evid, "project": project_id, "kind": kind,
                "at": now, "item": item or "", "text": words}

    def hub_note(self, project_id: str) -> dict:
        """The Markdown the export writes: a one-way, read-only picture of the
        project. Built from SQL only, and NO benchmark number appears - a
        private number must never leave the store, even into a note (A3)."""
        state = self.plan_state(project_id)
        milestones = self.milestones(project_id)
        items = self.work_items(project_id)
        events = self.events(project_id, limit=10)
        name = str(state.get("name") or "Project")
        path = str(state.get("linked_note_path") or "").strip()
        if path:
            path = path.replace("\\", "/")
            while path.startswith("/"):
                path = path[1:]
            if not path.lower().endswith((".md", ".txt")):
                path += ".md"
        else:
            path = f"{HUB_FOLDER}/{_safe_note_name(name)}.md"
        lines = [f"# {_clip(name, MAX_NAME)}", "", f"> {HUB_NOTE_WORDS}", ""]
        objective = str(state.get("objective") or "").strip()
        criteria = str(state.get("success_criteria") or "").strip()
        if objective:
            lines += [f"**Objective:** {_clip(objective, 300)}", ""]
        if criteria:
            lines += [f"**Success criteria:** {_clip(criteria, 300)}", ""]
        status = str(state.get("status") or "").strip()
        if status:
            lines.append(f"**Status:** {status}")
        if state.get("target_date"):
            # Only a date the owner himself gave; the export never adds one.
            lines.append(f"**Target date:** {state['target_date']}")
        repo = str(state.get("linked_repo") or "").strip()
        if repo:
            # PM3 (2026-11-20): the one repository this project is linked to.
            # Nothing is written on GitHub by an export; the note only says
            # what the store already holds.
            lines.append(f"**Repository:** {_clip(repo, 300)}")
        if status or state.get("target_date") or repo:
            lines.append("")
        # The merged-PR OFFER (PM3): shown, never acted on by the export. The
        # move to done is the owner's own status change and its Undo receipt.
        offers = self.pr_merged_offers() if self.exists() else []
        offers = [o for o in offers if o["project"] == project_id]
        if offers:
            lines += ["## Offered", "",
                      "These pull requests were merged; the note does not move the "
                      "work - say done (or leave it), and Undo is in the receipts.", ""]
            for offer in offers[:10]:
                lines.append(f"- PR #{offer['pr']} merged - move "
                             f"\"{_clip(offer['title'], MAX_WORK_TITLE)}\" to done?")
            lines.append("")
        if milestones:
            lines += ["## Milestones", ""]
            for m in milestones:
                mark = "x" if m["status"] == "done" else " "
                lines.append(f"- [{mark}] {_clip(m['title'], MAX_MILESTONE_TITLE)}")
            lines.append("")
        ready = [i for i in items if i.get("ready")]
        if ready:
            lines += ["## Ready now", ""]
            for item in ready[:10]:
                lines.append(f"- {_clip(item['title'], MAX_WORK_TITLE)}")
            lines.append("")
        if items:
            lines += ["## Work items", ""]
            for item in items:
                tail = ""
                if item["due_date"]:
                    tail = f" (due {item['due_date']})"
                # PM3 (2026-11-20): who would do it, and the READ-ONLY link
                # state. No number is ever copied from a benchmark; a PR's
                # number and checks are GitHub's own facts, read once.
                if item.get("executor") and item["executor"] != "owner":
                    tail += f" [{item['executor']}]"
                if item.get("linked_pr_number"):
                    pr_state = item.get("linked_pr_state") or "not synced"
                    ci = (f"; checks {item['linked_ci_status']}"
                          if item.get("linked_ci_status") else "")
                    tail += f" (PR #{item['linked_pr_number']}: {pr_state}{ci})"
                blockers = item.get("blocked_by") or []
                blocked = ""
                if blockers:
                    blocked = (" - blocked by "
                               + ", ".join(f'"{_clip(b["title"], 60)}"'
                                           for b in blockers[:3]))
                lines.append(f"- [{item['status']}] "
                             f"{_clip(item['title'], MAX_WORK_TITLE)}{tail}{blocked}")
            lines.append("")
        if events:
            lines += ["## Recent activity", ""]
            for ev in events:
                when = time.strftime("%Y-%m-%d", time.localtime(float(ev["at"])))
                lines.append(f"- {when} {ev['kind']}")
            lines.append("")
        text = "\n".join(lines)
        raw = text.encode("utf-8")
        if len(raw) > HUB_MAX_BYTES:
            text = _clip(text, HUB_MAX_BYTES // 2 - 3) + "\n"
        return {"project": project_id, "name": name, "path": path, "text": text}

    # ---- the progress side (the heatmap and balance chart; JARVIS-API section 105) ----
    # Read-only for the heatmap and the balance chart, plus the owner's own
    # choice of axes. Nothing here is ever put in a chat answer or sent.

    def _drop_axes(self, c, kind: str, refs) -> None:
        """Take deleted things off the balance chart and close the gaps in
        the order. Inside the caller's transaction."""
        refs = [r for r in refs if isinstance(r, str)]
        if not refs:
            return
        c.executemany("DELETE FROM balance_axes WHERE kind = ? AND ref = ?",
                      [(kind, r) for r in refs])
        rows = c.execute("SELECT rowid AS rid FROM balance_axes ORDER BY position, rowid").fetchall()
        for i, r in enumerate(rows):
            c.execute("UPDATE balance_axes SET position = ? WHERE rowid = ?", (i, r["rid"]))

    def activity_results(self, lo: float, hi: float) -> list:
        """[(at, sensitive)] for every logged number dated between `lo` and
        `hi` (seconds), oldest first - only the date and whether the
        benchmark is private, never a name or a value. Nothing is created."""
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            rows = c.execute(
                "SELECT r.at AS at, b.name AS name, b.unit AS unit, b.owner_sensitive AS own, "
                "b.auto_cleared AS cleared FROM results r JOIN benchmarks b ON b.id = r.bench "
                "WHERE r.at >= ? AND r.at < ? ORDER BY r.at", (float(lo), float(hi))).fetchall()
        cache: dict = {}
        out = []
        for r in rows:
            key = (r["name"], r["unit"], r["own"], r["cleared"])
            if key not in cache:
                cache[key] = marks(*key)["sensitive"]
            out.append((r["at"], cache[key]))
        return out

    def progress_bench(self, bid) -> Optional[dict]:
        """One number benchmark for the balance chart: its name, unit, target,
        which way is better, whether it is private, how many numbers it has,
        and the first and the latest (by date). None when it is gone."""
        if not isinstance(bid, str) or not _ID.fullmatch(bid) or not self.exists():
            return None
        with self._lock, self._db() as c:
            b = c.execute("SELECT b.*, p.name AS project_name FROM benchmarks b JOIN projects p "
                          "ON p.id = b.project WHERE b.id = ?", (bid,)).fetchone()
            if b is None or b["kind"] != "number":
                return None
            n = c.execute("SELECT COUNT(*) FROM results WHERE bench = ?", (bid,)).fetchone()[0]
            first = c.execute("SELECT value FROM results WHERE bench = ? "
                              "ORDER BY at ASC, logged ASC LIMIT 1", (bid,)).fetchone()
            last = c.execute("SELECT value FROM results WHERE bench = ? "
                             "ORDER BY at DESC, logged DESC LIMIT 1", (bid,)).fetchone()
        return {"id": b["id"], "project": b["project"], "project_name": b["project_name"],
                "name": b["name"], "unit": b["unit"], "better": b["better"],
                "target": b["target"], "count": int(n),
                "first": first["value"] if first else None,
                "latest": last["value"] if last else None,
                "sensitive": marks(b["name"], b["unit"], b["owner_sensitive"],
                                   b["auto_cleared"])["sensitive"]}

    def progress_benchmarks(self) -> list:
        """Every number benchmark that has a target and a direction (the
        ones a balance axis can follow), in creation order."""
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            ids = [r["id"] for r in c.execute(
                "SELECT id FROM benchmarks WHERE kind = 'number' AND target IS NOT NULL "
                "AND better IN ('higher','lower') ORDER BY created, id").fetchall()]
        return [b for b in (self.progress_bench(i) for i in ids) if b]

    def axes_read(self) -> list:
        if not self.exists():
            return []
        with self._lock, self._db() as c:
            rows = c.execute("SELECT kind, project, ref, label FROM balance_axes "
                             "ORDER BY position, rowid").fetchall()
        return [{"kind": r["kind"], "project": r["project"], "ref": r["ref"],
                 "label": r["label"]} for r in rows]

    def axes_write(self, axes: list) -> None:
        """Replace the whole chart (already checked by the caller)."""
        with self._lock, self._db() as c:
            c.execute("DELETE FROM balance_axes")
            for i, a in enumerate(axes):
                c.execute("INSERT INTO balance_axes (position, kind, project, ref, label) "
                          "VALUES (?,?,?,?,?)",
                          (i, a["kind"], a.get("project", ""), a["ref"], a.get("label", "")))
        _audit("projects.balance.set", {"axes": len(axes)})

    def axes_drop_goal(self, goal_ref: str) -> None:
        """A goal that was stopped or removed leaves the balance chart, the
        order closes up. Nothing is created when there is no projects.db."""
        if not self.exists():
            return
        with self._lock, self._db() as c:
            self._drop_axes(c, "goal", [goal_ref])


# --------------------------------------------------------------------------
#   PM3 (2026-11-20): the bridges' own helpers, and the app's one sync door
# --------------------------------------------------------------------------


def daily_row_id(project_id: str, item_id: str) -> str:
    """The id a projected work item carries on the daily to-do list.

    A stable, prefixed id - `project:<project>:work:<item>` - so a projection
    can never collide with a scheduler row's own id, and a client can tell a
    projected row from a real one without a second field to trust."""
    return f"project:{project_id}:work:{item_id}"


def _tasks_store():
    """The durable job list, or None when jarvis_tasks.py is not shipped here."""
    try:
        import jarvis_tasks
        return jarvis_tasks.Store()
    except Exception:                        # noqa: BLE001 - module absent
        return None


def _github_module():
    """The read-only GitHub reader, or None when jarvis_github.py is not here."""
    try:
        import jarvis_github
        return jarvis_github
    except Exception:                        # noqa: BLE001 - module absent
        return None


def sync_project(project_id: str, body=None, *, store: Optional[Projects] = None,
                 fetch=None, github=None, task_store=None) -> dict:
    """`POST /api/projects/<pid>/sync`: the app's one read-only bridge door.

    The body may attach a link first - `{"work_item": <id or title>, "task":
    <job id>}` or `{"work_item": ..., "pr": <number>}` - and then the project's
    linked durable jobs and linked pull requests are read and projected.

    NO CARD and NO model turn: this is the owner's own app asking his own PC to
    catch up with the job list and with GitHub. Nothing is changed on GitHub
    (every request the reader makes is a GET), nothing is run, and a work
    item's STATUS is never changed here: the job's own state moves it through
    the existing status path (with its receipt), and a merged PR only produces
    an OFFER."""
    store = store or get()
    project = store.get(project_id)          # KeyError -> the route's 404
    body = body if isinstance(body, dict) else {}
    linked = None
    target = body.get("work_item")
    if target not in (None, ""):
        item = store.find_work_item(target)
        if item["project"] != project_id:
            raise ValueError("that work item is not in this project")
        if "task" in body:
            linked = store.link_task(item["id"], body.get("task"),
                                     task_store=task_store)
        if "pr" in body:
            linked = store.link_pr(item["id"], body.get("pr"))
    try:
        task_out = store.sync_task_status(project_id, task_store=task_store)
    except Exception as exc:                 # noqa: BLE001 - the turn survives
        task_out = {"read": 0, "linked": 0, "changed": [],
                    "skipped": [{"why": f"the task list could not be read "
                                        f"({type(exc).__name__})"}]}
    repo = str((store.plan_state(project_id) or {}).get("linked_repo") or "").strip()
    if repo:
        pr_out = store.sync_prs(project_id, fetch=fetch, github=github)
    else:
        pr_out = {"read": 0, "linked": 0, "synced": [], "offers": [],
                  "errors": [], "project": project_id,
                  "message": "No linked repository, so no GitHub read was made."}
    return {"ok": True, "project": project["name"], "linked": linked,
            "task": task_out, "pr": pr_out,
            "offers": pr_out.get("offers") or [],
            "message": ("Read-only sync: the linked job's state and the linked "
                        "pull request's own state. Nothing was changed on "
                        "GitHub and nothing ran.")}


def _list_title(key: Optional[str]) -> str:
    try:
        import jarvis_schedule
        return jarvis_schedule.list_title(key)
    except Exception:
        return (key[0].upper() + key[1:] + " list") if key else "To-do list"


# --------------------------------------------------------------------------
#   Better or worse than last time
# --------------------------------------------------------------------------


def compare(latest: Optional[float], previous: Optional[float], better: Optional[str],
            *, target: Optional[float] = None) -> Optional[dict]:
    """{"direction": "up"|"down"|"same", "by", "verdict": "better"|"worse"|
    "same"|None, "said", "target_reached"} - or None with no number yet.
    Without `better` there is no verdict: up is not always good (a weight,
    a 5k time), so Jarvis does not guess."""
    if latest is None:
        return None
    reached = None
    if target is not None and better in BETTER:
        reached = latest >= target if better == "higher" else latest <= target
    if previous is None:
        return {"direction": None, "by": None, "verdict": None,
                "said": "The first number.", "target_reached": reached}
    diff = latest - previous
    if abs(diff) < 1e-9:
        direction = "same"
    else:
        direction = "up" if diff > 0 else "down"
    if direction == "same":
        verdict = "same"
    elif better == "higher":
        verdict = "better" if direction == "up" else "worse"
    elif better == "lower":
        verdict = "better" if direction == "down" else "worse"
    else:
        verdict = None
    by = _num_words(abs(diff))
    if direction == "same":
        said = "The same as last time."
    elif verdict:
        said = f"{verdict.capitalize()} than last time ({direction} {by})."
    else:
        said = f"{'Higher' if direction == 'up' else 'Lower'} than last time (by {by})."
    return {"direction": direction, "by": abs(diff), "verdict": verdict, "said": said,
            "target_reached": reached}


# --------------------------------------------------------------------------
#   The quick command: "log 5 km run", "I ran 5 km"
# --------------------------------------------------------------------------

#: What a said unit may mean. A benchmark's own unit decides between them
#: ("pounds" is a weight on one and money on another).
_UNIT_ALIASES = {
    "km": {"km"}, "kms": {"km"}, "k": {"km"}, "kilometre": {"km"}, "kilometres": {"km"},
    "kilometer": {"km"}, "kilometers": {"km"},
    "mi": {"mi"}, "mile": {"mi"}, "miles": {"mi"},
    "m": {"m"}, "metre": {"m"}, "metres": {"m"}, "meter": {"m"}, "meters": {"m"},
    "kg": {"kg"}, "kgs": {"kg"}, "kilo": {"kg"}, "kilos": {"kg"}, "kilogram": {"kg"},
    "kilograms": {"kg"},
    "lb": {"lb"}, "lbs": {"lb"}, "pound": {"lb", "gbp"}, "pounds": {"lb", "gbp"},
    "st": {"st"}, "stone": {"st"},
    "£": {"gbp"}, "gbp": {"gbp"}, "quid": {"gbp"},
    "$": {"usd"}, "usd": {"usd"}, "dollar": {"usd"}, "dollars": {"usd"}, "bucks": {"usd"},
    "€": {"eur"}, "eur": {"eur"}, "euro": {"eur"}, "euros": {"eur"},
    "min": {"min"}, "mins": {"min"}, "minute": {"min"}, "minutes": {"min"},
    "h": {"h"}, "hr": {"h"}, "hrs": {"h"}, "hour": {"h"}, "hours": {"h"},
    "s": {"s"}, "sec": {"s"}, "secs": {"s"}, "second": {"s"}, "seconds": {"s"},
    "kcal": {"kcal"}, "cal": {"kcal"}, "cals": {"kcal"}, "calorie": {"kcal"},
    "calories": {"kcal"},
    "%": {"%"}, "percent": {"%"}, "per cent": {"%"},
}

#: A verb said in the past ("I ran") and the word a benchmark's name uses.
_VERBS = {
    "ran": "run", "run": "run", "jogged": "run", "jog": "run",
    "walked": "walk", "walk": "walk", "hiked": "hike", "hike": "hike",
    "swam": "swim", "swim": "swim", "cycled": "cycle", "biked": "bike", "rode": "ride",
    "rowed": "row", "read": "read", "slept": "sleep", "weigh": "weight", "weighed": "weight",
    "saved": "save", "meditated": "meditate", "studied": "study", "practised": "practice",
    "practiced": "practice", "wrote": "write", "lifted": "lift", "did": "",
    "spent": "spend", "drank": "drink",
}

_WORD_NUMBERS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
_WORD_NUMBERS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                      "eighty": 80, "ninety": 90, "hundred": 100})

_NUM = (r"(?P<cur>[$£€])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?"
        r"|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")")
_UNIT = r"(?:(?:\s+|(?<=\d))(?P<unit>%|per cent|[a-z]+(?:/[a-z]+)?))?"
_WHEN_TAIL = re.compile(r"\s+(today|this morning|this afternoon|this evening|tonight"
                        r"|just now|yesterday)$")
_NAME = r"(?P<name>[a-z][a-z' -]{0,38}[a-z]|[a-z])"
_OWN = r"(?:(?:my|the|our)\s+)?"
_LEAD = re.compile(r"^(?:(?:hey|hi|ok|okay)\s+jarvis\b[\s,]*|jarvis\b[\s,]*|please\s+)+")

_LOG_PATTERNS = [
    # 0: "log 5 km run", "log 5 km for my run", "log 72.5 kg weight", "log 30 pages"
    re.compile(r"(?:log|record)\s+" + _NUM + _UNIT
               + r"(?:\s+(?:(?:of|for|on|as)\s+)?" + _OWN + _NAME + r")?"),
    # 1: "log my weight as 72.5 kg", "log weight 72.5 kg", "log my savings at $200"
    re.compile(r"(?:log|record)\s+" + _OWN + _NAME + r"(?:\s+(?:as|at|of|is))?:?\s+"
               + _NUM + _UNIT),
    # 2: "my weight is 72.5 kg", "my weight was 72.5 kg"
    re.compile(r"(?:my|our)\s+" + _NAME + r"\s+(?:is|was)\s+(?:now\s+)?" + _NUM + _UNIT),
    # 3: "i ran 5 km", "i walked 10000 steps", "i did 20 push ups"
    re.compile(r"i(?:'ve| have)?\s+(?:just\s+)?(?P<verb>[a-z]+)\s+" + _NUM + _UNIT
               + r"(?P<rest>(?:\s+[a-z]+){0,2})"),
]

#: Units that only measure; they never name what was done.
_MEASURE_ONLY = frozenset({"km", "mi", "m", "kg", "lb", "st", "min", "h", "s", "gbp", "usd",
                           "eur", "kcal", "%"})


def _tidy(text) -> str:
    t = str(text or "").replace("’", "'").replace("‘", "'").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = _LEAD.sub("", t).strip()
    t = re.sub(r"[\s.!?,]+$", "", t)
    t = re.sub(r"(?:[\s,]+(?:please|thanks|thank you|jarvis))+$", "", t).strip()
    return t


def _parse_num(raw: str) -> Optional[float]:
    if raw in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[raw])
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if math.isfinite(v) and abs(v) <= MAX_ABS_VALUE else None


_STOP = frozenset("my the a an our of for on in at to log and as is was".split())
#: Words (as stems) that describe a measurement but never say what was
#: done: "morning run" and "Long run" share "run", not these.
_WEAK = frozenset("up down out long short daily weekly monthly morning evening night total "
                  "new best".split())
_IRREGULAR = {"running": "run", "swimming": "swim", "savings": "save", "saving": "save",
              "pushups": "push", "situps": "sit", "ups": "up", "weight": "weight",
              "cycling": "cycle", "biking": "bike", "hiking": "hike", "riding": "ride",
              "writing": "write", "meditation": "meditate", "meditating": "meditate",
              "practising": "practice", "practicing": "practice", "studying": "study",
              "spending": "spend", "drinking": "drink", "morning": "morning",
              "evening": "evening"}


def _stem(word: str) -> str:
    """A word's plain root, the same way on both sides ("steps" and "step",
    "pages" and "page", "I cycled" and "Cycling")."""
    w = word.lower().strip("'")
    if w.endswith("'s"):
        w = w[:-2]
    if _VERBS.get(w):
        return _VERBS[w]
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "shes", "ches", "xes", "zes")):
        return w[:-2]
    for suffix in ("ing", "ed"):
        if len(w) > len(suffix) + 2 and w.endswith(suffix):
            return w[: -len(suffix)]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _stems(words: str) -> set:
    return {_stem(w) for w in re.findall(r"[a-z][a-z']*", (words or "").lower())
            if w not in _STOP}


def unit_keys(unit: str) -> set:
    """What a unit may mean: "kilometres" -> {"km"}, "pounds" -> {"lb",
    "gbp"}, "pages" -> {"page"}. Empty for no unit."""
    u = (unit or "").strip().lower()
    if not u:
        return set()
    if u in _UNIT_ALIASES:
        return set(_UNIT_ALIASES[u])
    return {_stem(u)}


def _known_unit(unit: str) -> bool:
    return (unit or "").strip().lower() in _UNIT_ALIASES


def parse_log(text) -> Optional[dict]:
    """Pure: does this sentence log a number? {"value", "unit", "words",
    "when"} or None. Reads nothing, acts on nothing - which benchmark it
    means (if any) is match_log()'s question. `words` are the stems that
    name what was measured ("run" for "I ran", "weight" for "log my
    weight ...", "push" and "up" for "I did 20 push ups")."""
    s = _tidy(text)
    if not s or len(s) > 120 or "\n" in s:
        return None
    when = ""
    m = _WHEN_TAIL.search(s)
    if m:
        when, s = m.group(1), s[:m.start()].strip()
    for i, rx in enumerate(_LOG_PATTERNS):
        m = rx.fullmatch(s)
        if not m:
            continue
        g = m.groupdict()
        value = _parse_num(g["num"])
        if value is None:
            return None
        unit = g.get("unit") or ""
        if unit in _STOP:
            return None
        if g.get("cur"):
            if unit and not unit_keys(unit) & unit_keys(g["cur"]):
                return None        # "$200 km" is not a measurement
            unit = g["cur"]
        words = set()
        if i == 3:
            verb = g.get("verb") or ""
            if verb not in _VERBS or not unit:
                return None        # "I have 3 kids"; "I ran 5" - five what?
            if _VERBS[verb]:
                words.add(_VERBS[verb])
            words |= _stems(g.get("rest") or "")
        else:
            words |= _stems(g.get("name") or "")
        if unit and not _known_unit(unit):
            # "30 pages", "20 push ups": an unknown unit word also names it.
            words |= unit_keys(unit)
        words -= _MEASURE_ONLY
        if not words and not unit:
            return None
        return {"value": value, "unit": unit, "words": sorted(words), "when": when}
    return None


def match_log(parsed: Optional[dict], benchmarks: list) -> dict:
    """Pure: which of `benchmarks` (life_benchmarks()'s shape) the parsed
    sentence means. {"match": bench} for exactly one, {"ambiguous": [..]}
    for several, {} for none.

    A benchmark matches when the said unit fits its unit (a known unit
    must be the same one - no converting miles to km), and its name and
    the said words share a word that says WHAT was done ("run" in "I ran"
    and "Long run"; "morning" and "long" do not count) - or, with only a
    unit said, when that unit is its unit. "I did 20 sit ups" never
    matches "Push ups": sharing "up" is not enough."""
    if not parsed or not benchmarks:
        return {}
    words = set(parsed.get("words") or [])
    unit = parsed.get("unit") or ""
    said = unit_keys(unit)
    known = _known_unit(unit)
    hits = []
    for b in benchmarks:
        bunit = unit_keys(b.get("unit") or "")
        names = _stems(b.get("name") or "")
        if said and bunit and not (said & bunit) and known:
            continue                    # 5 km is never a number of miles
        if said and not known and not (said & bunit) and not (said & names):
            continue                    # "I ran 5 errands" is not a run
        if (words - _WEAK) & (names - _WEAK):
            hits.append(b)
        elif said and bunit and (said & bunit) and (not words or not known):
            hits.append(b)
    if len(hits) == 1:
        return {"match": hits[0]}
    if len(hits) > 1:
        return {"ambiguous": hits}
    return {}


def _when_at(when: str, now: float) -> float:
    return now - 86400 if when == "yesterday" else now


def quick_match(text, store: Optional[Projects] = None) -> Optional[dict]:
    """For jarvis_quick.py: None unless the sentence logs a number AND a
    life benchmark matches it (or several do - then the answer asks which).
    Reads projects.db only after the sentence already parsed, and never
    creates it."""
    parsed = parse_log(text)
    if parsed is None:
        return None
    try:
        store = store or get()
        benches = store.life_benchmarks()
    except Exception:
        return None
    got = match_log(parsed, benches)
    if not got:
        return None
    return dict(parsed, **got)


def quick_match_project(text, pid: str, *, store: Optional[Projects] = None,
                        now: Optional[float] = None) -> Optional[dict]:
    """`quick_match`, restricted to ONE project's number benchmarks.

    For a chat that belongs to a project (2026-11-19): the same sentences
    ("I ran 5 km", "log 5 km run") are matched only against THAT project's
    own benchmarks, so one project's words can never land in another
    project's numbers by accident. None when the sentence is not that shape,
    the project is gone, or nothing in it fits."""
    parsed = parse_log(text)
    if parsed is None:
        return None
    try:
        store = store or get()
        project = store.get(pid)
    except Exception:
        return None
    benches = []
    for b in (project.get("benchmark_list") or []):
        if b.get("kind") != "number":
            continue
        benches.append({"id": b.get("id"), "project": pid,
                        "name": b.get("name"), "unit": b.get("unit") or "",
                        "project_name": project.get("name") or "",
                        "sensitive": bool(b.get("sensitive"))})
    got = match_log(parsed, benches)
    if not got:
        return None
    return dict(parsed, **got)


def quick_log(found: dict, *, store: Optional[Projects] = None,
              now: Optional[float] = None) -> dict:
    """For jarvis_quick.py: log what quick_match() found. {"said",
    "private"} - private when the benchmark is sensitive, so the apps keep
    the answer on screen and never read it aloud."""
    store = store or get()
    if found.get("ambiguous"):
        names = [f"\"{b['name']}\" in \"{b['project_name']}\"" for b in found["ambiguous"][:4]]
        return {"said": "Which one: " + " or ".join(names) + "? Nothing was logged - say it "
                        "with a word only one of them has, or log it in the app.",
                "private": any(b.get("sensitive") for b in found["ambiguous"])}
    b = found["match"]
    now = store.clock() if now is None else now
    out = store.log(b["project"], b["id"], found["value"],
                    at=_when_at(found.get("when") or "", now), source="words")
    unit = out.get("unit") or found.get("unit") or ""
    said = (f"Logged {_with_unit(found['value'], unit)} for \"{out['name']}\" in "
            f"\"{b['project_name']}\".")
    ch = out.get("change") or {}
    if ch.get("said") and ch.get("direction") is not None:
        said += " " + ch["said"]
    if ch.get("target_reached"):
        said += " Target reached."
    return {"said": said, "private": bool(out.get("sensitive"))}


# --------------------------------------------------------------------------
#   A chat that belongs to a project (2026-11-19, design step 4)
#
#   `/api/chat` may carry an optional `project`: the project's id, or the
#   project's own name, resolved HERE by the store's own lookup - never
#   guessed, never a prefix, never a partial match. The absent key is every
#   caller that existed before this: no scope, no change, byte for byte.
#
#   A reference that names nothing, or names more than one thing, is REFUSED
#   with a plain sentence and nothing is written. The chat turn answers the
#   refusal directly (jarvis_quick.py) and the HUD refuses it with a 400
#   before any model or quick answer (jarvis_hud.py) - two doors, one rule.
# --------------------------------------------------------------------------

#: How long a project reference from a request body may be. A name is at most
#: MAX_NAME characters and an id 32, so this only keeps nonsense out.
MAX_REF = 120

#: A benchmark is "due a new measurement" when its newest number is older
#: than this many days, or when it has none yet. Fixed on purpose: "what's
#: next" must answer the same thing twice in a row.
DUE_DAYS = 7

#: How much of a project the two chat answers may read out, so an answer on
#: the 8 GB card's context stays short (docs/PROJECTS-DESIGN.md section 1).
NEXT_MAX_GOALS = 5
NEXT_MAX_STEPS = 6
NEXT_MAX_BENCHES = 5
NEXT_MAX_TODOS = 8

#: The project prompt's own hard cap, in characters. The recalled-facts block
#: and the project block share the 8 GB card's context with the conversation;
#: a project whose instructions are long enough to crowd it is CUT, and the
#: block says so in its own line instead of failing.
MAX_PROMPT_CHARS = 2400


def _clean_ref(value) -> Optional[str]:
    """A project reference from a request body: one line, or None for none.

    None and "" mean "no project" - exactly the absent key, so a client that
    sends an empty string is the same as an older client. ValueError, in
    words, for anything that is not a piece of text."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('"project" is the project\'s id or its name, as one line of text')
    ref = " ".join(value.split())
    if not ref:
        return None
    if len(ref) > MAX_REF:
        raise ValueError(f"the project's id or name is longer than {MAX_REF} characters")
    return ref


def resolve_ref(ref, *, store: Optional[Projects] = None) -> dict:
    """The project a reference names: the id first, then the name.

    The STORE's own lookup does the answering - this never guesses at a
    prefix, a first match or a "closest" name. ValueError with a plain
    sentence for an id that is not a project, a name nothing is called, and a
    name more than one project is called (which the store refuses to create,
    but an edited database could still hold); nothing is written either way."""
    store = store or get()
    fix = _clean_ref(ref)
    if fix is None:
        raise ValueError("name a project by its id or its own name")
    if _ID.fullmatch(fix):
        try:
            return store.get(fix)
        except KeyError:
            raise ValueError(f'There is no project with the id "{fix}". '
                             f"Nothing was changed.") from None
    want = fix.casefold()
    hits = [p for p in store.list()
            if " ".join(str(p.get("name") or "").split()).casefold() == want]
    if not hits:
        raise ValueError(f'There is no project called "{fix}". Nothing was changed.')
    if len(hits) > 1:
        names = ", ".join(f'"{p.get("name")}" (id {p.get("id")})' for p in hits)
        raise ValueError(f'More than one project is called "{fix}" ({names}), so nothing '
                         f"was changed - say which one by its id.")
    return store.get(hits[0]["id"])


def chat_scope(body, *, store: Optional[Projects] = None) -> dict:
    """What a /api/chat body's `project` says: no project, a project, or a
    refusal - and never an exception.

    The answer every caller reads:
        {"given": bool, "ok": bool, "project": <full view>|None,
         "id": str|None, "name": str, "error": str, "why": str}
    `given` False is every request before this existed. `ok` False is a
    refusal with `error` already a plain sentence - the turn must refuse and
    write nothing. A store that cannot be read is `ok` False too (fail
    closed: an unscoped turn must never be turned into a guessed one)."""
    out = {"given": False, "ok": True, "project": None, "id": None, "name": "",
           "error": "", "why": "No project was named, so this turn is an ordinary one."}
    if not isinstance(body, dict):
        return out
    try:
        ref = _clean_ref(body.get("project"))
    except ValueError as exc:
        out.update({"given": True, "ok": False, "error": _sentence(exc)})
        return out
    if ref is None:
        return out
    out["given"] = True
    try:
        project = resolve_ref(ref, store=store)
    except ValueError as exc:
        out.update({"ok": False, "error": _sentence(exc)})
        return out
    except Exception as exc:                       # noqa: BLE001 - fail closed
        out.update({"ok": False, "error": (
            f"The projects store could not be read ({type(exc).__name__}), so nothing "
            f"was scoped and nothing was changed.")})
        return out
    out.update({"ok": True, "project": project, "id": project["id"],
                "name": project.get("name") or "",
                "why": (f"This turn belongs to the project "
                        f"\"{project.get('name')}\" - its own instructions, notes, goals "
                        f"and benchmarks.")})
    return out


def fact_scope(pid: str, *, store: Optional[Projects] = None) -> dict:
    """Which remembered facts a project-scoped turn may see: this project's
    own labelled ids, and the ids OTHER projects label.

    IDS ONLY - no fact's words are read here (the module's own rule: the
    words come from jarvis_memory's read, and jarvis_hud.py makes it). `ok`
    False means the labels could not be proved, and the caller must then use
    NO remembered facts for the turn: a project scope that cannot be checked
    must not guess that a fact is unlabelled."""
    store = store or get()
    try:
        labels = store.fact_labels(pid)
        return {"ok": True, "own": list(labels["own"]), "others": list(labels["others"]),
                "why": ""}
    except Exception as exc:                       # noqa: BLE001 - fail closed
        return {"ok": False, "own": [], "others": [],
                "why": (f"The project's fact labels could not be read "
                        f"({type(exc).__name__}), so no remembered facts were used.")}


def _due_words(view: dict, now: float) -> str:
    """Why this benchmark is due, in the owner's words, or "" when it is not."""
    latest = view.get("latest") or {}
    at = latest.get("at")
    if at is None:
        return "no numbers yet"
    try:
        age = max(0.0, float(now) - float(at))
    except (TypeError, ValueError):
        return ""
    if age > DUE_DAYS * 86400:
        return "last number on " + time.strftime("%Y-%m-%d", time.localtime(float(at)))
    return ""


def next_on_project(pid: str, *, store: Optional[Projects] = None,
                    now: Optional[float] = None, sched=None, goals=None) -> dict:
    """The read behind "what's next on this project" - and nothing else.

    Reads three of the owner's stores, never a model, never a socket, and
    writes nothing:
      * projects.db - the project's own work list name, linked goal ids and
        benchmarks;
      * schedule.db - the open items on that named work list, when it has one;
      * goals.db - the linked goals still open, with their own steps (a step
        already met by its benchmark number is shown as met, not as to do).

    Private (health or money) benchmarks are COUNTED, never named and never
    given a number: the answer to this question can be read aloud, and the
    project's own rule is that those numbers stay on their screen. The result
    carries `read` - which stores were opened - so the answer can say what it
    read, like the defect-register answer does."""
    store = store or get()
    now = time.time() if now is None else float(now)
    p = store.get(pid)
    out = {
        "ok": True, "id": pid, "name": p.get("name") or "",
        "date": time.strftime("%Y-%m-%d", time.localtime(now)),
        "work_list": None, "goals": [], "goals_missing": [],
        "benchmarks_due": [], "benchmarks_private": 0,
        "read": ["projects.db"], "why": "",
    }
    wl = p.get("work_list") or None
    if wl:
        try:
            sched = sched or _schedule_store()
            items = [t for t in sched.todos() if (t.get("list") or "") == wl["name"]]
        except Exception:
            items = None
        if items is None:
            out["work_list"] = {"name": wl["name"], "title": wl.get("title") or "",
                                "open": [], "count": 0, "read": False}
        else:
            out["work_list"] = {"name": wl["name"], "title": wl.get("title") or "",
                                "open": [str(t.get("text") or "") for t in items
                                         if t.get("state") in ("active", "paused")],
                                "count": len(items), "read": True}
            out["read"].append("schedule.db")
    ids = [g for g in (p.get("goals") or []) if isinstance(g, str)]
    if ids:
        try:
            goals = goals or _goals_store()
        except Exception:
            goals = None
        if goals is None:
            out["goals_missing"] = ids[:MAX_GOALS_LINKED]
        else:
            out["read"].append("goals.db")
            for gid in ids[:MAX_GOALS_LINKED]:
                try:
                    g = goals.get(gid)
                except Exception:
                    g = None
                if not isinstance(g, dict):
                    out["goals_missing"].append(gid)
                    continue
                if g.get("status") not in ("draft", "active"):
                    continue
                steps = []
                for st in (g.get("plan") or []):
                    if len(steps) >= NEXT_MAX_STEPS:
                        break
                    if st.get("state") not in ("open", "met_by_number", "locked"):
                        continue
                    steps.append({
                        "step": str(st.get("step") or ""),
                        "state": st.get("state") or "",
                        "measure_name": str(st.get("measure_name") or ""),
                        "reached_words": str(st.get("reached_words") or ""),
                        "lock_words": str(st.get("lock_words") or ""),
                    })
                if len(out["goals"]) >= NEXT_MAX_GOALS:
                    break
                out["goals"].append({"id": gid, "text": str(g.get("text") or ""),
                                     "status": g.get("status") or "", "steps": steps})
    due, private = [], 0
    for b in (p.get("benchmark_list") or []):
        if b.get("sensitive"):
            private += 1
            continue
        why = _due_words(b, now)
        if not why:
            continue
        if len(due) >= NEXT_MAX_BENCHES:
            continue
        latest = b.get("latest") or {}
        due.append({"id": b.get("id"), "name": str(b.get("name") or ""),
                    "unit": str(b.get("unit") or ""), "why": why,
                    "latest": latest.get("value")})
    out["benchmarks_due"] = due
    out["benchmarks_private"] = private
    return out


def _schedule_store():
    import jarvis_schedule
    return jarvis_schedule.get()


def _goals_store():
    import jarvis_goals
    return jarvis_goals.get()


# ---- "log this number against <benchmark>", with ONE card ---------------------
#
# By the owner's 2026-09-28 decision a number the owner writes down needs NO
# card (docs/PROJECTS-DESIGN.md section 3, "Life projects"). This sentence is
# the owner's 2026-11-19 ruling on TOP of that rule: a number said in chat
# against a NAMED project benchmark must be CARDED if it is written, because
# it is a write made from words and rule 4 means nothing is auto-approved.
# The card shows the project, the benchmark, the number and the date, and
# nothing is written until it is approved. A yes writes through the SAME
# `Projects.log` the log route calls - never raw SQL.

LOG_ACTION = CARD_ACTION
LOG_WAITING = "Waiting for your approval. Nothing is logged until you approve the card."
LOG_LAST_WORDS = {
    "logged": "Logged it. You can remove the number in the project's own screen.",
    "denied": "Nothing was logged - you said no.",
    "timed_out": "Nothing was logged - the card timed out.",
    "refused": "Nothing was logged.",
    "withdrawn": "Nothing was logged - the benchmark was deleted while the card waited.",
    "failed": "Nothing was logged - it could not be saved.",
}

_LOG_LOCK = threading.Lock()
#: Held while a waiting card's benchmark is removed, and while a card's yes is
#: written, so the two never interleave (the shape _P_SWITCH has).
_LOG_SWITCH = threading.RLock()
_LOG_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}


def log_card(project_name: str, benchmark_name: str, value_words: str,
             when_words: str) -> str:
    """The card's own words: one number, one benchmark, one project, said
    plainly, with what a yes does and what a no leaves alone."""
    return "\n".join([
        f"Log this number in the project \"{project_name}\"?",
        "",
        f"Benchmark: \"{benchmark_name}\"",
        f"Number: {value_words}",
        f"When: {when_words}",
        "",
        "Saving a number changes nothing else: no command runs, no test starts, and "
        "nothing is sent anywhere. It is kept with this project's own benchmark, where "
        "you can remove it at once.",
        "",
        "If you say no: nothing is logged.",
    ])


def _when_words(at: Optional[float], now: float) -> str:
    if at is None:
        return "today"
    day = time.strftime("%Y-%m-%d", time.localtime(float(at)))
    today = time.strftime("%Y-%m-%d", time.localtime(float(now)))
    yday = time.strftime("%Y-%m-%d", time.localtime(float(now) - 86400))
    if day == today:
        return "today"
    if day == yday:
        return "yesterday"
    return day


def _finish_log(bid: str, token: str, outcome: str, why: str = "") -> None:
    with _LOG_LOCK:
        p = _LOG_STATE["pending"].get(bid)
        if p and p.get("token") == token:
            _LOG_STATE["pending"].pop(bid, None)
        _LOG_STATE["withdrawn"].discard(token)
        _LOG_STATE["last"][bid] = {"outcome": outcome, "why": why, "at": time.time(),
                                   "message": LOG_LAST_WORDS.get(outcome, "")}
    _audit("projects.log.card", {"bench": bid, "outcome": outcome})


def _decide_log(pid: str, bid: str, token: str, value: float, at: Optional[float],
                name: str, bench_name: str, value_words: str, when_words: str,
                store: Projects, gate: Callable, tier_of: Callable) -> None:
    text = log_card(name, bench_name, value_words, when_words)
    detail = {"text": text,
              "what": "save one number you said into one of this project's benchmarks",
              "project": name, "benchmark": bench_name,
              "value": value_words, "when": when_words}
    try:
        v = gate(LOG_ACTION, detail, text)
    except Exception as exc:                       # noqa: BLE001 - said, never swallowed
        return _finish_log(bid, token, "refused",
                           f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(LOG_ACTION) != "ask":
        return _finish_log(bid, token, "refused",
                           f"the gate answered at tier {vtier!r}, which is not a person "
                           f"saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish_log(bid, token, outcome)
        return _finish_log(bid, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _LOG_SWITCH:
        with _LOG_LOCK:
            withdrawn = token in _LOG_STATE["withdrawn"]
        if withdrawn:
            return _finish_log(bid, token, "withdrawn")
        try:
            store.log(pid, bid, value, at=at, source="words")
        except KeyError:
            return _finish_log(bid, token, "withdrawn", "the benchmark is gone")
        except Exception as exc:                   # noqa: BLE001 - said, never swallowed
            return _finish_log(bid, token, "failed", type(exc).__name__)
    _finish_log(bid, token, "logged")


def _withdraw_log(bid: str) -> None:
    with _LOG_LOCK:
        p = _LOG_STATE["pending"].pop(bid, None)
        if p:
            _LOG_STATE["withdrawn"].add(p["token"])


def _bench_in_project(project: dict, bid: str) -> dict:
    for b in (project.get("benchmark_list") or []):
        if b.get("id") == bid:
            return b
    raise KeyError(bid)


def match_benchmark(benchmarks: list, ref: str) -> dict:
    """Which benchmark a spoken reference names: exactly one, several, or none.

    Whole-name first (case and spacing ignored), then by words: a benchmark
    whose every name-word the reference says, or whose name contains every
    word of a one/two-word reference. NEVER a guess: two matches are
    `ambiguous` and the caller refuses in words, the same shape
    `match_log()` already uses for "I ran 5 km"."""
    want = " ".join(str(ref or "").split()).casefold()
    if not want:
        return {}
    named = [b for b in benchmarks
             if " ".join(str(b.get("name") or "").split()).casefold() == want]
    if len(named) == 1:
        return {"match": named[0]}
    if len(named) > 1:
        return {"ambiguous": named}
    want_words = _stems(want)
    hits = []
    for b in benchmarks:
        name_words = _stems(str(b.get("name") or ""))
        if name_words and want_words and (name_words <= want_words
                                          or (len(want_words) <= 2
                                              and want_words <= name_words)):
            hits.append(b)
    if len(hits) == 1:
        return {"match": hits[0]}
    if len(hits) > 1:
        return {"ambiguous": hits}
    return {}


def log_by_words(pid: str, ref: str, value, *, at: Optional[float] = None,
                 store: Optional[Projects] = None, now: Optional[float] = None,
                 gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                 spawn: Optional[Callable] = None) -> dict:
    """One number said against one NAMED benchmark of ONE project - carded.

    {"ok", "waiting", "said", "private", "benchmark"}.
    Refuses, writing nothing, when: the benchmark does not exist in THIS
    project, two benchmarks match the words, the benchmark is a coding
    command (its numbers come from running it, not from saying them), the
    number is not a number, the card cannot be raised, or its tier is not
    `ask` (rule 4: no card, no write). Never looks at another project's
    benchmarks - the scope is the project's own `benchmark_list`."""
    store = store or get()
    now = store.clock() if now is None else float(now)
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    project = store.get(pid)
    name = project.get("name") or ""
    benches = [b for b in (project.get("benchmark_list") or []) if b.get("kind") == "number"]
    got = match_benchmark(benches, ref)
    if got.get("ambiguous"):
        names = ", ".join(f'"{b.get("name")}"' for b in got["ambiguous"][:4])
        return {"ok": False, "waiting": False, "private": False, "benchmark": "",
                "said": (f"More than one benchmark in \"{name}\" fits that: {names}. "
                         f"Nothing was logged - name one exactly.")}
    b = got.get("match")
    if b is None:
        if not benches:
            return {"ok": False, "waiting": False, "private": False, "benchmark": "",
                    "said": (f"The project \"{name}\" has no number benchmark yet, so "
                             f"there is nothing to log against. Nothing was logged.")}
        names = ", ".join(f'"{x.get("name")}"' for x in benches[:6])
        return {"ok": False, "waiting": False, "private": False, "benchmark": "",
                "said": (f"There is no benchmark called \"{str(ref).strip()}\" in "
                         f"\"{name}\". Nothing was logged. This project has: {names}.")}
    try:
        v = _value(value)
    except ValueError as exc:
        return {"ok": False, "waiting": False,
                "private": bool(b.get("sensitive")), "benchmark": str(b.get("name") or ""),
                "said": f"That is not a number I can log: {_sentence(exc)} Nothing was logged."}
    try:
        when = _value(at) if at is not None else None
        if when is not None and (when > now + 86400 or when < now - 20 * 365 * 86400):
            raise ValueError("that date is too far from today")
    except ValueError as exc:
        return {"ok": False, "waiting": False,
                "private": bool(b.get("sensitive")), "benchmark": str(b.get("name") or ""),
                "said": f"Nothing was logged: {_sentence(exc)}"}
    bid = b["id"]
    unit = str(b.get("unit") or "")
    value_words = _with_unit(v, unit)
    when_words = _when_words(at, now)
    if tier_of(LOG_ACTION) != "ask":
        t = tier_of(LOG_ACTION)
        return {"ok": False, "waiting": False, "private": bool(b.get("sensitive")),
                "benchmark": str(b.get("name") or ""),
                "said": (f"Logging a number said in chat needs a person to say yes, and "
                         f"{LOG_ACTION} is set to {t!r} here, so I did not raise a card. "
                         f"Nothing was logged.")}
    with _LOG_LOCK:
        if bid in _LOG_STATE["pending"]:
            return {"ok": False, "waiting": False, "private": bool(b.get("sensitive")),
                    "benchmark": str(b.get("name") or ""),
                    "said": (f"A card for \"{b.get('name')}\" is already waiting - answer "
                             f"it first. Nothing was logged.")}
        token = uuid.uuid4().hex
        _LOG_STATE["pending"][bid] = {"token": token, "since": time.time()}
    try:
        spawn(lambda: _decide_log(pid, bid, token, v, at, name, str(b.get("name") or ""),
                                  value_words, when_words, store, gate, tier_of))
    except Exception:                              # noqa: BLE001 - refuse, never claim
        with _LOG_LOCK:
            _LOG_STATE["pending"].pop(bid, None)
        return {"ok": False, "waiting": False, "private": bool(b.get("sensitive")),
                "benchmark": str(b.get("name") or ""),
                "said": "I could not raise the approval card, so nothing was logged."}
    return {"ok": True, "waiting": True, "private": bool(b.get("sensitive")),
            "benchmark": str(b.get("name") or ""), "said": LOG_WAITING,
            "card": {"project": name, "benchmark": b.get("name"),
                     "value": value_words, "when": when_words}}


def log_last(bid: str) -> dict:
    """The last card for one benchmark: {"outcome", "why", "at", "message"} or {}."""
    with _LOG_LOCK:
        return dict(_LOG_STATE["last"].get(str(bid)) or {})


def _forget_log_state(bid: str) -> None:
    """A benchmark is gone: a waiting card must not write into it."""
    _withdraw_log(bid)
    with _LOG_LOCK:
        _LOG_STATE["last"].pop(str(bid), None)


# --------------------------------------------------------------------------
#   Shareable ON - ONE card (change_own_config); OFF at once
# --------------------------------------------------------------------------

_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}
#: Held while Shareable is switched off (or a project deleted) and while a
#: card's yes is written, so the two never interleave.
_P_SWITCH = threading.RLock()

LAST_WORDS = {
    "on": "Shareable is on.",
    "denied": "Shareable stays off - you said no.",
    "timed_out": "Shareable stays off - the card timed out.",
    "refused": "Shareable stays off.",
    "withdrawn": "Shareable stays off - you turned it off before answering.",
    "failed": "Shareable stays off - it could not be saved.",
}


def share_card(name: str) -> str:
    return "\n".join([
        f"Make the project \"{name}\" Shareable?",
        "",
        "When a project is Shareable, a short piece of its files may one day go to a web "
        "search or to an AI chatbot you use - but only after a card that shows you those "
        "exact words, every time. Nothing is sent by turning this on, and nothing can be "
        "sent today: that part is not built yet.",
        "",
        "Never shared, whatever this says: health or money numbers, anything Jarvis "
        "remembers about you, your email, and passwords or keys.",
        "",
        "Turning it off again is instant, from either app.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _finish(pid: str, token: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        p = _P_STATE["pending"].get(pid)
        if p and p.get("token") == token:
            _P_STATE["pending"].pop(pid, None)
        _P_STATE["withdrawn"].discard(token)
        _P_STATE["last"][pid] = {"outcome": outcome, "why": why, "at": time.time(),
                                 "message": LAST_WORDS.get(outcome, "")}
    _audit("projects.shareable.card", {"id": pid, "outcome": outcome})


def _withdraw_share(pid: str) -> None:
    with _P_LOCK:
        p = _P_STATE["pending"].pop(pid, None)
        if p:
            _P_STATE["withdrawn"].add(p["token"])


def _decide(pid: str, token: str, name: str, store: Projects, gate: Callable,
            tier_of: Callable) -> None:
    text = share_card(name)
    detail = {"text": text, "what": "make one project Shareable",
              "setting": "Shareable", "to": name, "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, token, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish(pid, token, "refused", f"the gate answered at tier {vtier!r}, which "
                                              f"is not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, token, outcome)
        return _finish(pid, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _P_SWITCH:
        with _P_LOCK:
            withdrawn = token in _P_STATE["withdrawn"]
        if withdrawn:
            return _finish(pid, token, "withdrawn")
        try:
            store.set_shareable_on(pid)
        except Exception as exc:
            return _finish(pid, token, "failed", type(exc).__name__)
    _finish(pid, token, "on")


def request_shareable(pid: str, body, *, store: Optional[Projects] = None,
                      gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                      spawn: Optional[Callable] = None) -> tuple:
    """POST /api/projects/<id>/shareable {"on": true|false}. OFF: at once,
    no card (and a waiting card is withdrawn). ON: 202 and ONE card."""
    store = store or get()
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
        return 400, {"ok": False, "error": 'need {"on": true} or {"on": false}'}
    try:
        project = store.get(pid)
    except KeyError:
        return 404, {"ok": False, "error": "no such project"}
    if body["on"] is False:
        out = store.update(pid, {"shareable": False}, here=False)
        return 200, {"ok": True, "changed": project["shareable"], "project": out,
                     "message": "Shareable is off. Nothing from this project can be shared."}
    if project["shareable"]:
        return 200, {"ok": True, "changed": False, "project": project,
                     "message": "Shareable is already on."}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; making a project "
            f"Shareable needs a person to say yes, so it must be 'ask'")}
    with _P_LOCK:
        if pid in _P_STATE["pending"]:
            return 409, {"ok": False, "error": "A card for this is already waiting - answer "
                                               "it first."}
        token = uuid.uuid4().hex
        _P_STATE["pending"][pid] = {"token": token, "since": time.time()}
    try:
        spawn(lambda: _decide(pid, token, project["name"], store, gate, tier_of))
    except Exception:
        with _P_LOCK:
            _P_STATE["pending"].pop(pid, None)
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "project": store.get(pid),
                 "message": "Waiting for your approval. Shareable stays off unless you "
                            "approve the card."}


# --------------------------------------------------------------------------
#   Project Mode (design step 4): which project is ACTIVE, and the two switches
#
#   `active_project_id` is not a field of a project: it is which project the
#   next turn belongs to, so it lives in its own small file beside projects.db
#   rather than in a row. Entering and leaving Project Mode loosens nothing -
#   it chooses whose context is assembled and whose rows get labelled - so it
#   takes no card. `auto_route_cloud` DOES loosen something, and it takes ONE
#   card, exactly as Shareable does. Rule 4: nothing here is ever
#   auto-approved, and OFF is instant.
# --------------------------------------------------------------------------

MODE_FILE = "project-mode.json"

#: The Auto-Route card's own waiting answer. Kept apart from Shareable's so
#: one card can never answer the other's question.
_A_LOCK = threading.Lock()
#: Held while Auto-Route is switched off (or a project deleted) and while a
#: card's yes is written, so the two never interleave - the same shape, and the
#: same reason, as _P_SWITCH.
_A_SWITCH = threading.RLock()
_A_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}

AUTO_ROUTE_WAITING = "Waiting for your yes on the approval card."

AUTO_ROUTE_LAST_WORDS = {
    "on": "Auto-Route is on.",
    "denied": "Auto-Route stays off - you said no.",
    "timed_out": "Auto-Route stays off - the card timed out.",
    "refused": "Auto-Route stays off.",
    "withdrawn": "Auto-Route stays off - you turned it off before answering.",
    "failed": "Auto-Route stays off - it could not be saved.",
}


def mode_path() -> Path:
    return _config_dir() / MODE_FILE


def _read_mode() -> dict:
    try:
        with open(mode_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except Exception:
        # No file, or one that will not read: NO active project. Failing here
        # is failing to "an ordinary turn", which is what every turn recorded
        # before this step was.
        return {}


def _snapshot_mode_file(path: Path) -> dict:
    """Best-effort guardian copy of `project-mode.json` before it is replaced.

    This file is Jarvis's own small pointer (which project the next turn
    belongs to), not the owner's data, so a broken time-machine store must
    never block Project Mode: the answer is recorded honestly in the audit
    row either way. The guardian's own rules still apply - a link is refused,
    and the config folder is the explicit root this one caller allows it to
    look in - because the guardian's default list is the owner's folders.
    Never raises.
    """
    try:
        import jarvis_file_guardian as guardian
        return guardian.snapshot_before_write(
            str(path), reason="before Project Mode's pointer file is replaced",
            roots=[str(path.parent)])
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False,
                "error": f"guardian_unavailable ({type(exc).__name__})",
                "words": "The time machine could not save a copy of the Project "
                         "Mode file."}


def _snapshot_detail(snapshot) -> dict:
    """The ids an audit row may carry for a guardian copy - never a path or words.

    `snapshot_ok`/`snapshot_error` say truthfully whether a copy happened: a
    failed or refused snapshot is never reported as one that worked.
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return {"snapshot_ok": False, "snapshot_reason": "no file was there to copy"}
    if snapshot.get("ok") is True:
        return {"snapshot_ok": True,
                "snapshot_id": str(snapshot.get("snapshot_id") or ""),
                "receipt_id": str(snapshot.get("receipt_id") or ""),
                "before_sha256": str(snapshot.get("before_sha256") or "")}
    return {"snapshot_ok": False,
            "snapshot_error": str(snapshot.get("error") or "the copy failed")}


def _write_mode(doc: dict, *, reason: str = "") -> dict:
    """Replace the file whole, through a temporary name, so a reader never
    sees half a file (the shape jarvis_limits.py uses for the settings file).

    The file that is there now is copied by the guardian BEFORE the replace
    (when one is there to copy), and its answer is returned so the caller can
    link the saved version's ids. Never raises for a failed copy: Project
    Mode is Jarvis's own pointer, and a time-machine problem must not make
    switching impossible - the audit row says plainly whether a copy happened.
    """
    path = mode_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_mode_file(path) if path.is_file() else {}
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    tmp.replace(path)
    return snapshot


def active_project_id() -> Optional[str]:
    """The project the next turn belongs to, or None - and NEVER raises.

    A missing file, a broken file, an id that is not an id, or no
    jarvis_projects at all all answer None, and None is the safe answer: no
    context is assembled and no row is labelled."""
    pid = _read_mode().get("active_project_id")
    return pid if isinstance(pid, str) and _ID.fullmatch(pid) else None


def set_active_project(pid: Optional[str], *,
                       store: Optional[Projects] = None) -> Optional[str]:
    """Enter Project Mode for one project; None leaves it. Leaving is instant."""
    store = store or get()
    if pid in (None, ""):
        snapshot = _write_mode({}, reason="leaving Project Mode")
        _audit("projects.mode", {"active": False, **_snapshot_detail(snapshot)})
        return None
    if not isinstance(pid, str) or not _ID.fullmatch(pid):
        raise ValueError("no such project")
    store.get(pid)                      # KeyError when it is not there at all
    snapshot = _write_mode({"active_project_id": pid},
                           reason="entering Project Mode")
    _audit("projects.mode", {"active": True, **_snapshot_detail(snapshot)})
    return pid


def _bench_summary(benches: list) -> tuple:
    """(the numbers a turn may see, a plain sentence about what was held back).

    A benchmark carrying the private mark (health or money) is NOT put in front
    of a model: jarvis_projects keeps those "on screen, never read aloud or
    sent anywhere", and a prompt is somewhere. Its NAME is left out too - the
    name is what says "therapy" or "savings"."""
    shown, held = [], 0
    for b in benches or []:
        if b.get("sensitive"):
            held += 1
            continue
        shown.append({"name": b.get("name"), "unit": b.get("unit") or "",
                      "latest": (b.get("latest") or {}).get("value"),
                      "target": b.get("target")})
    if not held:
        words = f"{len(shown)} benchmark(s), none private."
    else:
        words = (f"{len(shown)} benchmark(s) shown; {held} kept off this list "
                 f"because they are marked private (health or money).")
    return shown, words


def project_context(pid: Optional[str] = None, *,
                    store: Optional[Projects] = None) -> dict:
    """Everything a turn inside a project should be given, and nothing else:
    the owner's own instructions, the notes he pinned, the work list, the
    goals, and a summary of the benchmarks that are NOT privately marked.

    Reads only. It changes nothing and needs no card."""
    store = store or get()
    pid = pid or active_project_id()
    if not pid:
        return {"active": False, "project_id": None, "instructions": "",
                "pinned_notes": [], "work_list": None, "goals": [],
                "benchmarks": [], "benchmarks_words": "", "held_back": 0,
                "routing": "Local-Only",
                "why": "No project is active, so no project context is added."}
    p = store.get(pid)
    shown, words = _bench_summary(p.get("benchmark_list") or [])
    folder = p.get("folder") or {}
    return {
        "active": True,
        "project_id": pid,
        "name": p.get("name"), "kind": p.get("kind"),
        "folder": folder.get("path") if folder else None,
        "instructions": p.get("instructions") or "",
        "pinned_notes": p.get("notes") or [],
        "work_list": p.get("work_list"),
        "goals": p.get("goals") or [],
        "benchmarks": shown,
        "benchmarks_words": words,
        "held_back": len(p.get("benchmark_list") or []) - len(shown),
        "routing": p.get("routing"),
        "why": ("The active project's own instructions, pinned notes, work list, "
                "goals and its non-private benchmark summary."),
    }


def route_for_turn(prompt: str, *, context_tokens: int = 0,
                   store: Optional[Projects] = None) -> dict:
    """Advise a lane for one turn - or say local.

    THREE switches must all be on, and all three are the owner's own: a project
    must be ACTIVE, that project must be SHAREABLE, and its AUTO-ROUTE must be
    on. Anything less is "local", and so is every failure - the router not
    being installed, a router that raises, advice this cannot read. THE
    ABSENCE OF THE ROUTER MEANS LOCAL: never a crash, never an escalation.

    Nothing here decides anything by itself either: jarvis_auto_router's own
    contract says it ADVISES, and its `recommended` is the only thing read as
    a yes. A dict with no `recommended` is a no."""
    store = store or get()
    pid = active_project_id()
    out = {"lane": "local", "recommended": False, "active": bool(pid),
           "routing": "Local-Only", "why": ""}
    if not pid:
        out["why"] = "No project is active, so this turn is an ordinary one."
        return out
    try:
        p = store.get(pid)
    except Exception:
        out["why"] = "The active project is no longer there."
        return out
    if not p.get("shareable"):
        out["why"] = "This project is not Shareable, so nothing may leave this PC."
        return out
    if not p.get("auto_route_cloud"):
        out["routing"] = "Local-Only"
        out["why"] = "Auto-Route is off for this project, so every turn stays local."
        return out
    try:
        import jarvis_auto_router
        advice = jarvis_auto_router.evaluate_route(
            prompt, context_tokens=context_tokens, active_project=p)
    except Exception as exc:
        out["why"] = (f"Auto-Route is on, but the router is not available here "
                      f"({type(exc).__name__}), so this turn stays on this PC.")
        return out
    if not isinstance(advice, dict):
        out["why"] = ("Auto-Route answered something this cannot read, so this "
                      "turn stays on this PC.")
        return out
    out["routing"] = "Local / Auto-Route to Cloud"
    out["advice"] = advice
    lane = advice.get("lane")
    if advice.get("recommended") is not True or lane not in CLOUD_LANES:
        out["why"] = advice.get("why") or "Auto-Route found no reason to leave this PC."
        return out
    return {"lane": lane, "recommended": True, "active": True,
            "routing": "Local / Auto-Route to Cloud",
            "why": advice.get("why") or "",
            "would_send": advice.get("would_send") or "",
            "advice": advice}


#: The only cloud lane a turn may be advised onto. Anything else - including
#: whatever a future router might invent - reads as local. It was two names
#: until 2026-10-27 (`jarvis-critic` went with the owner's decision to keep ONE
#: cloud lane), and the tuple is kept rather than replaced by a bare string so
#: the membership test above reads exactly as it did.
CLOUD_LANES = ("jarvis-escalate",)


def auto_route_card(name: str) -> str:
    return "\n".join([
        f"Let a hard question in the project \"{name}\" go to a cloud lane?",
        "",
        "When Auto-Route is on AND the project is Shareable, a genuinely hard "
        "question in that project may be estimated as too slow for this PC, and "
        "offered to one of the cloud lanes you have already set up.",
        "",
        "It is never automatic. The advice is advice: the words that would leave "
        "are scrubbed first, they are shown to you on the card that asks, and "
        "nothing goes anywhere until you say yes to that card - every time.",
        "",
        "Never sent, whatever this says: health or money numbers, anything "
        "Jarvis remembers about you, your email, and passwords or keys.",
        "",
        "Turning it off again is instant, from either app.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _finish_auto(pid: str, token: str, outcome: str, why: str = "") -> None:
    with _A_LOCK:
        p = _A_STATE["pending"].get(pid)
        if p and p.get("token") == token:
            _A_STATE["pending"].pop(pid, None)
        _A_STATE["withdrawn"].discard(token)
        _A_STATE["last"][pid] = {"outcome": outcome, "why": why, "at": time.time(),
                                 "message": AUTO_ROUTE_LAST_WORDS.get(outcome, "")}
    _audit("projects.auto_route.card", {"id": pid, "outcome": outcome})


def _withdraw_auto(pid: str) -> None:
    with _A_LOCK:
        p = _A_STATE["pending"].pop(pid, None)
        if p:
            _A_STATE["withdrawn"].add(p["token"])


def _decide_auto(pid: str, token: str, name: str, store: Projects, gate: Callable,
                 tier_of: Callable) -> None:
    text = auto_route_card(name)
    detail = {"text": text, "what": "let a hard question in one project be offered "
                                     "to a cloud lane",
              "setting": "Auto-Route to Cloud", "to": name,
              "leaves_this_pc": True}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish_auto(pid, token, "refused",
                            f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish_auto(pid, token, "refused",
                            f"the gate answered at tier {vtier!r}, which is not a "
                            f"person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish_auto(pid, token, outcome)
        return _finish_auto(pid, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _A_SWITCH:
        with _A_LOCK:
            withdrawn = token in _A_STATE["withdrawn"]
        if withdrawn:
            return _finish_auto(pid, token, "withdrawn")
        try:
            store.set_auto_route_cloud_on(pid)
        except Exception as exc:
            return _finish_auto(pid, token, "failed", type(exc).__name__)
    _finish_auto(pid, token, "on")


def request_auto_route(pid: str, body, *, store: Optional[Projects] = None,
                       gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                       spawn: Optional[Callable] = None) -> tuple:
    """POST /api/projects/<id>/auto-route {"on": true|false}. OFF: at once, no
    card (and a waiting card is withdrawn). ON: 202 and ONE card - the same
    shape as Shareable, because it is the same kind of thing: a switch that
    lets more of the owner's own work leave this PC."""
    store = store or get()
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
        return 400, {"ok": False, "error": 'need {"on": true} or {"on": false}'}
    try:
        project = store.get(pid)
    except KeyError:
        return 404, {"ok": False, "error": "no such project"}
    if body["on"] is False:
        out = store.update(pid, {"auto_route_cloud": False}, here=False)
        return 200, {"ok": True, "changed": project["auto_route_cloud"], "project": out,
                     "message": "Auto-Route is off. Every turn in this project stays "
                                "on this PC."}
    if project["auto_route_cloud"]:
        return 200, {"ok": True, "changed": False, "project": project,
                     "message": "Auto-Route is already on."}
    if not project["shareable"]:
        # Both switches are the owner's, and this one is only meaningful with
        # the other: said plainly rather than raising a card that cannot do
        # anything yet.
        return 409, {"ok": False, "error": (
            "Make the project Shareable first - Auto-Route only decides where a "
            "question may be offered, and nothing may leave a project that is "
            "not Shareable.")}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; turning "
            f"Auto-Route on needs a person to say yes, so it must be 'ask'")}
    with _A_LOCK:
        if pid in _A_STATE["pending"]:
            return 409, {"ok": False, "error": "A card for this is already waiting - "
                                               "answer it first."}
        token = uuid.uuid4().hex
        _A_STATE["pending"][pid] = {"token": token, "since": time.time()}
    try:
        spawn(lambda: _decide_auto(pid, token, project["name"], store, gate, tier_of))
    except Exception:
        with _A_LOCK:
            _A_STATE["pending"].pop(pid, None)
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "project": store.get(pid),
                 "message": "Waiting for your approval. Auto-Route stays off unless "
                            "you approve the card."}


# --------------------------------------------------------------------------
#   One receipt for a project edit, so an edit has a one-click Undo
# --------------------------------------------------------------------------

#: The fields an edit may put back. DELIBERATELY NOT `shareable` or
#: `auto_route_cloud`: those are the two switches, each with its own card and
#: its own instant-OFF, and an Undo button that silently turned one of them
#: back ON would be a loosening nobody approved - the exact thing rule 4
#: forbids. Putting the words back is not a loosening.
UNDOABLE_FIELDS = ("name", "instructions", "notes", "goals", "work_list", "folder")


def _snapshot(r) -> dict:
    """The part of a project row an edit may put back."""
    return {"name": r["name"], "instructions": r["instructions"],
            "notes": json.loads(r["notes"] or "[]"),
            "goals": json.loads(r["goals"] or "[]"),
            "work_list": r["work_list"], "folder": r["folder"]}


def restore_project(pid: str, before: dict, *, store: Optional[Projects] = None) -> bool:
    """Put an edit back. Only the fields in UNDOABLE_FIELDS are ever written."""
    store = store or get()
    if not isinstance(before, dict):
        return False
    body = {k: before.get(k) for k in UNDOABLE_FIELDS if k in before}
    if not body:
        return False
    store.update(pid, body, here=False)
    return True


def restore_work_status(item_id: str, before: str, *,
                        store: Optional[Projects] = None) -> bool:
    """Put a work item's status back (the one-click Undo for a status change).

    Writes through the store's own `set_work_item_status` with `receipt=False`,
    so the Undo itself raises no second receipt; the change still appends its
    own `project_events` row, which is the honest record of what happened."""
    store = store or get()
    if not isinstance(item_id, str) or not _ID.fullmatch(item_id):
        return False
    if before not in WORK_STATUSES:
        return False
    try:
        store.set_work_item_status(item_id, before, receipt=False)
    except (KeyError, ValueError):
        return False
    return True


def _record_work_status_receipt(pid: str, item_id: str, title: str,
                                before: str, after: str) -> str:
    """One receipt for one status change, or "" - never an exception into the
    change. The same shape as `_record_project_receipt`."""
    try:
        import jarvis_receipts
    except Exception:
        return ""
    try:
        summary = f'Moved "{_clip(title, 60)}" to {after}'
        return jarvis_receipts.record(
            "work_item_status", summary,
            before={"item": item_id, "before": before},
            after={"item": item_id, "after": after},
            undo=lambda: restore_work_status(item_id, before))
    except Exception:
        return ""


def _register_receipts() -> bool:
    try:
        import jarvis_receipts
        ok = bool(jarvis_receipts.register_restorer("project_edit",
                                                    lambda payload: restore_project(
                                                        (payload or {}).get("id", ""),
                                                        (payload or {}).get("before") or {})))
        ok = bool(jarvis_receipts.register_restorer(
            "work_item_status",
            lambda payload: restore_work_status((payload or {}).get("item", ""),
                                                (payload or {}).get("before") or ""))) and ok
        return ok
    except Exception:
        return False


def _record_project_receipt(pid: str, before: dict, after: dict, what: str) -> str:
    """One receipt for one project edit, or "" - never an exception into the
    edit. The same shape as jarvis_goals.py's own `_record_step_receipt`."""
    try:
        import jarvis_receipts
    except Exception:
        return ""
    try:
        summary = f'Edited the project "{what}"'
        return jarvis_receipts.record("project_edit", summary,
                                      before={"id": pid, "before": before},
                                      after={"id": pid, "after": after},
                                      undo=lambda: restore_project(pid, before))
    except Exception:
        return ""


_register_receipts()


# --------------------------------------------------------------------------
#   The Obsidian hub note (PM2, 2026-11-20): ONE projection, written through
#   the notes editor's own door
# --------------------------------------------------------------------------
# SQLite stays the write master. The note is a one-way picture: it is built
# from SQL, it says so in its own text, and a later export replaces it. Every
# write goes through jarvis_notes_edit's own paths, so it keeps the product's
# one way of touching a vault file: ONE `edit_vault_note` card, the File
# Guardian copy first when an existing note is replaced, the undo receipt for a
# brand-new one, and the note path checks (inside the vault, no hidden folder).
# No second writer is added here.

def export_hub(project_id: str, *, gate_check=None, wait_s=None,
               store: Optional[Projects] = None) -> dict:
    """Write one project's hub note into the owner's Obsidian vault.

    `gate_check` is the gate callable the notes editor raises its ONE
    `edit_vault_note` card through (the agent passes the turn's own checker).
    Returns the module's own words plus the note and path; nothing in the
    project store is changed by an export. A brand-new note is created (the
    undo receipt comes first); an existing hub note is replaced whole (the
    File Guardian copies the old bytes first, and the receipt makes the change
    undoable)."""
    store = store or get()
    note = store.hub_note(project_id)
    try:
        import jarvis_notes_edit as N
    except Exception as exc:                 # noqa: BLE001 - module absent
        return {"ok": False, "created": False, "replaced": False,
                "path": note["path"],
                "error": f"the notes editor is not available here "
                         f"({type(exc).__name__})"}
    kwargs: dict = {}
    if gate_check is not None:
        kwargs["gate_check"] = gate_check
    if wait_s is not None:
        kwargs["wait_s"] = wait_s
    try:
        full, _rel, why = N._resolve_note(note["path"])
    except Exception as exc:                 # noqa: BLE001 - bad path, said so
        return {"ok": False, "created": False, "replaced": False,
                "path": note["path"], "error": f"{type(exc).__name__}: {exc}"}
    if why:
        return {"ok": False, "created": False, "replaced": False,
                "path": note["path"], "error": str(why)}
    if full.is_file():
        try:
            sha = N._sha256(N._read_bytes(full))
        except OSError as exc:
            return {"ok": False, "created": False, "replaced": False,
                    "path": note["path"],
                    "error": f"the note could not be read ({type(exc).__name__})"}
        code, out = N.handle_save({"path": note["path"], "text": note["text"],
                                   "expected_sha256": sha}, **kwargs)
        verb = "replaced"
    else:
        code, out = N.handle_create({"path": note["path"], "text": note["text"]},
                                    provenance="model", client="agent", **kwargs)
        verb = "created"
    state = str(out.get("state") or "")
    ok = code in (200, 202) and state in ("saved", "waiting")
    result = {"ok": ok, "created": ok and verb == "created",
              "replaced": ok and verb == "replaced", "path": note["path"],
              "state": state, "note": note["text"],
              "message": str(out.get("message") or "")}
    if not ok:
        result["error"] = (str(out.get("error") or out.get("message")
                               or "the note was not written"))
    return result


# --------------------------------------------------------------------------
#   Taking a private mark off a benchmark: the owner's own mark at once;
#   Jarvis's automatic mark with ONE card (the owner, 2026-09-28)
# --------------------------------------------------------------------------

_M_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}}

UNMARK_WORDS = {
    "off": "The private mark is off. Jarvis may read these numbers aloud now.",
    "denied": "The numbers stay private - you said no.",
    "timed_out": "The numbers stay private - the card timed out.",
    "refused": "The numbers stay private.",
    "withdrawn": "The numbers stay private - the benchmark changed, or you marked it "
                 "again, before you answered.",
    "failed": "The numbers stay private - the benchmark changed while the card waited.",
}

TOPIC_WORDS = {"health": "health", "money": "money"}


def unmark_card(name: str, project: str, topic: str, unit: str = "") -> str:
    looks = TOPIC_WORDS.get(topic, f"a private topic ({topic})")
    words = f"\"{name}\"" + (f" (in {unit})" if unit else "")
    return "\n".join([
        f"Take the private mark off \"{name}\" in the project \"{project}\"?",
        "",
        f"Jarvis marked this benchmark private by itself, because its name {words} "
        f"looked like {looks}. While it is marked, its numbers stay on screen: never read "
        "aloud, and never sent anywhere.",
        "",
        "If you take the mark off, Jarvis may read these numbers aloud, like any other "
        "answer.",
        "",
        "Renaming the benchmark or changing its unit checks it again. You can mark it "
        "private yourself at any time, instantly.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes. The numbers stay private.",
    ])


def _finish_unmark(bid: str, token: str, outcome: str, why: str = "") -> None:
    with _P_LOCK:
        p = _M_STATE["pending"].get(bid)
        if p and p.get("token") == token:
            _M_STATE["pending"].pop(bid, None)
        _M_STATE["withdrawn"].discard(token)
        _M_STATE["last"][bid] = {"outcome": outcome, "why": why, "at": time.time(),
                                 "message": UNMARK_WORDS.get(outcome, "")}
    _audit("projects.unmark.card", {"id": bid, "outcome": outcome})


def _withdraw_unmark(bid: str) -> None:
    with _P_LOCK:
        p = _M_STATE["pending"].pop(bid, None)
        if p:
            _M_STATE["withdrawn"].add(p["token"])


def _decide_unmark(pid: str, bid: str, token: str, bench: dict, project: str,
                   store: Projects, gate: Callable, tier_of: Callable) -> None:
    text = unmark_card(bench["name"], project, bench["topic"], bench["unit"])
    detail = {"text": text, "what": "take the private mark off one benchmark",
              "setting": "Private mark", "to": bench["name"], "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _finish_unmark(bid, token, "refused",
                              f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _finish_unmark(bid, token, "refused", f"the gate answered at tier {vtier!r}, "
                                                     f"which is not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish_unmark(bid, token, outcome)
        return _finish_unmark(bid, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _P_SWITCH:
        with _P_LOCK:
            withdrawn = token in _M_STATE["withdrawn"]
        if withdrawn:
            return _finish_unmark(bid, token, "withdrawn")
        try:
            store.clear_auto_mark(pid, bid, bench["name"], bench["unit"], bench["topic"])
        except Exception as exc:
            return _finish_unmark(bid, token, "failed", type(exc).__name__)
    _finish_unmark(bid, token, "off")


def _bench_only(store: Projects, pid: str, bid: str) -> dict:
    out = store.results(pid, bid, 1)
    out.pop("points", None)
    out.pop("points_shown", None)
    return out


def request_unmark(pid: str, bid: str, body=None, *, store: Optional[Projects] = None,
                   gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                   spawn: Optional[Callable] = None) -> tuple:
    """POST /api/projects/<id>/benchmarks/<bid>/unmark {}. The owner's own
    mark comes off at once, no card. A mark Jarvis made from the name: 202
    and ONE card; it comes off only on a person's yes."""
    store = store or get()
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if body is not None and not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    try:
        with store._lock, store._db() as c:
            p = store._project_row(c, pid)
            b = store._bench_row(c, pid, bid)
            m = marks(b["name"], b["unit"], b["owner_sensitive"], b["auto_cleared"])
            project = p["name"]
            bench = {"name": b["name"], "unit": b["unit"], "topic": m["auto_holds"]}
    except KeyError:
        return 404, {"ok": False, "error": "no such project, benchmark or number"}
    if m["auto_holds"]:
        t = tier_of(CARD_ACTION)
        if t != "ask":
            return 503, {"ok": False, "error": (
                f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; taking Jarvis's own "
                f"private mark off needs a person to say yes, so it must be 'ask'")}
        with _P_LOCK:
            if bid in _M_STATE["pending"]:
                return 409, {"ok": False, "error": "A card for this is already waiting - "
                                                   "answer it first."}
    with _P_SWITCH:
        mine = store.unmark_owner(pid, bid) if m["owner"] else False
    if not m["auto_holds"]:
        return 200, {"ok": True, "changed": mine, "benchmark": _bench_only(store, pid, bid),
                     "message": ("Your private mark is off." if mine
                                 else "This benchmark has no private mark.")}
    with _P_LOCK:
        if bid in _M_STATE["pending"]:
            return 409, {"ok": False, "error": "A card for this is already waiting - answer "
                                               "it first."}
        token = uuid.uuid4().hex
        _M_STATE["pending"][bid] = {"token": token, "since": time.time()}
    try:
        spawn(lambda: _decide_unmark(pid, bid, token, bench, project, store, gate, tier_of))
    except Exception:
        with _P_LOCK:
            _M_STATE["pending"].pop(bid, None)
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "changed": mine,
                 "benchmark": _bench_only(store, pid, bid),
                 "message": ("Your own mark is off. " if mine else "")
                 + "Waiting for your approval. The numbers stay private unless you approve "
                   "the card."}


# --------------------------------------------------------------------------
#   The one store this backend uses
# --------------------------------------------------------------------------

_ONE: Optional[Projects] = None
_ONE_LOCK = threading.Lock()


def get() -> Projects:
    global _ONE
    with _ONE_LOCK:
        if _ONE is None:
            _ONE = Projects()
        return _ONE


# --------------------------------------------------------------------------
#   The routes (docs/JARVIS-API.md section 88)
# --------------------------------------------------------------------------

PATH = "/api/projects"


def parse_route(route: str) -> Optional[tuple]:
    """None, or a tuple naming the route:
        ("list",)                                   /api/projects
        ("project", pid)                            /api/projects/<pid>
        ("project_delete", pid)                     /api/projects/<pid>/delete
        ("shareable", pid)                          /api/projects/<pid>/shareable
        ("benchmarks", pid)                         /api/projects/<pid>/benchmarks
        ("bench", pid, bid)                         .../benchmarks/<bid>
        ("bench_delete", pid, bid)                  .../benchmarks/<bid>/delete
        ("log", pid, bid)                           .../benchmarks/<bid>/log
        ("unmark", pid, bid)                        .../benchmarks/<bid>/unmark
        ("result_delete", pid, bid, rid)            .../benchmarks/<bid>/results/<rid>/delete
        ("facts", pid)                              /api/projects/<pid>/facts
        ("fact_forget", pid, fid)                   .../facts/<fid>/forget
    """
    if not isinstance(route, str):
        return None
    if route == PATH:
        return ("list",)
    if route == PATH + "/mode":
        # Project Mode itself: which project is active. Not a project id, and
        # it must be read before anything treats the first segment as one.
        return ("mode",)
    if not route.startswith(PATH + "/"):
        return None
    p = route[len(PATH) + 1:].split("/")
    if not p[0]:
        return None
    pid = p[0]
    if len(p) == 1:
        return ("project", pid)
    if len(p) == 2 and p[1] in ("delete", "shareable", "benchmarks", "facts",
                                "sync"):
        return ({"delete": "project_delete", "shareable": "shareable",
                 "benchmarks": "benchmarks", "facts": "facts",
                 # PM3 (2026-11-20): the read-only bridge sync - POST only.
                 "sync": "sync"}[p[1]], pid)
    if len(p) == 4 and p[1] == "facts" and p[2] and p[3] == "forget":
        # One fact per request, exactly as the memory routes are: there is no
        # list form of Forget (jarvis_memory's own "used" note says the same).
        return ("fact_forget", pid, p[2])
    if len(p) == 2 and p[1] in ("delete", "shareable", "benchmarks", "context",
                                "auto-route", "map"):
        return ({"delete": "project_delete", "shareable": "shareable",
                 "benchmarks": "benchmarks", "context": "context",
                 "auto-route": "auto_route", "map": "map"}[p[1]], pid)
    if len(p) >= 3 and p[1] == "benchmarks" and p[2]:
        bid = p[2]
        if len(p) == 3:
            return ("bench", pid, bid)
        if len(p) == 4 and p[3] in ("delete", "log", "unmark"):
            return ({"delete": "bench_delete", "log": "log", "unmark": "unmark"}[p[3]],
                    pid, bid)
        if len(p) == 6 and p[3] == "results" and p[4] and p[5] == "delete":
            return ("result_delete", pid, bid, p[4])
    return None


def _err(exc) -> tuple:
    """(status, body) for the plain exceptions the store raises - never a
    stack trace reaching an app."""
    if isinstance(exc, NoSuchApp):
        return 404, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, FactGone):
        # 404 for a fact that is not there (or that this project does not
        # label); 409 for one that is there but no longer current.
        return exc.status, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, Unavailable):
        return 503, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, KeyError):
        return 404, {"ok": False, "error": "no such project, benchmark or number"}
    if isinstance(exc, PermissionError):
        return 403, {"ok": False, "error": str(exc), "pc_only": True}
    if isinstance(exc, ValueError):
        return 400, {"ok": False, "error": _sentence(exc)}
    if isinstance(exc, OverflowError):
        return 409, {"ok": False, "error": _sentence(exc)}
    return 503, {"ok": False, "error": type(exc).__name__}


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


def handle_get(route: str, query: str = "", *, store: Optional[Projects] = None) -> tuple:
    store = store or get()
    hit = parse_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "no such route"}
    try:
        if hit[0] == "list":
            items = store.list()
            return 200, {"ok": True, "available": True, "title": TITLE, "projects": items,
                         "empty": EMPTY if not items else "", "max": MAX_PROJECTS,
                         "unlinked_apps": store.unlinked_apps()}
        if hit[0] == "project":
            return 200, {"ok": True, "project": store.get(hit[1])}
        if hit[0] == "facts":
            # The LABELS only. `words_route` is where the words come from -
            # jarvis_memory's own existing read, which is the one place that
            # knows how to show a forgotten fact as "no longer in use" and to
            # leave an Off topic out - and `ids` is ready to hand to it.
            # MAX_FACTS == that route's own cap, so this is one more call.
            items = store.facts(hit[1])
            return 200, {"ok": True, "available": True,
                         "facts": items, "count": len(items), "max": MAX_FACTS,
                         "empty": EMPTY_FACTS if not items else "",
                         "ids": [f["fact"] for f in items],
                         "words_route": "/api/memory/used"}
        if hit[0] == "mode":
            pid = active_project_id()
            return 200, {"ok": True, "active_project_id": pid,
                         "context": project_context(pid, store=store),
                         "routing": route_for_turn("", store=store)}
        if hit[0] == "context":
            return 200, {"ok": True, "context": project_context(hit[1], store=store)}
        if hit[0] == "bench":
            q = parse_qs(query or "")
            n = (q.get("points") or [CHART_POINTS])[0]
            return 200, {"ok": True, "benchmark": store.results(hit[1], hit[2], n)}
        if hit[0] == "map":
            # A READ-ONLY repository map of this project's own folder
            # (jarvis_repomap.py, 2026-11-05): names and signatures only,
            # ranked for the question, packed to a token budget. It adds no
            # gate action and no card - it is a read under the same
            # read_files_readonly line file_read uses - and the module itself
            # writes nothing. Imported here so a backend that does not ship
            # the module still answers every other project route.
            try:
                import jarvis_repomap as RM
            except Exception:                            # noqa: BLE001
                return 503, {"ok": False, "available": False,
                             "error": "The repository map is not installed on this backend."}
            return RM.handle_get(hit[1], query, store=store)
    except Exception as exc:
        return _err(exc)
    return 405, {"ok": False, "error": "use POST for this"}


def handle_post(route: str, body, *, here: bool = False,
                store: Optional[Projects] = None, **card) -> tuple:
    store = store or get()
    hit = parse_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "no such route"}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    kind = hit[0]
    try:
        if kind == "list":
            return 200, {"ok": True, "project": store.create(body, here=here)}
        if kind == "project":
            return 200, {"ok": True, "project": store.update(hit[1], body, here=here)}
        if kind == "project_delete":
            gone = store.delete_full(hit[1])
            out = {"ok": True, "deleted": True}
            if gone.get("app"):
                out["app_kept"] = gone["app"]
            return 200, out
        if kind == "sync":
            # PM3 (2026-11-20): read the linked job's state and the linked
            # PR's own state. No card: a read-only catch-up of the owner's own
            # PC, exactly like the projects reads around it.
            extra = {name: card.get(name) for name in
                     ("fetch", "github", "task_store") if name in card}
            return 200, sync_project(hit[1], body, store=store, **extra)
        if kind == "shareable":
            return request_shareable(hit[1], body, store=store, **card)
        if kind == "auto_route":
            return request_auto_route(hit[1], body, store=store, **card)
        if kind == "mode":
            was = active_project_id()
            now = set_active_project(body.get("project_id"), store=store)
            return 200, {"ok": True, "changed": was != now, "active_project_id": now,
                         "context": project_context(now, store=store),
                         "message": ("Project Mode is on for that project."
                                     if now else
                                     "Project Mode is off - turns are ordinary "
                                     "again.")}
        if kind == "benchmarks":
            return 200, {"ok": True, "benchmark": store.add_benchmark(hit[1], body, here=here)}
        if kind == "facts":
            # Label ONE of the owner's own facts with this project. No card:
            # the owner's own tap on a fact they can see.
            return 200, store.label_fact(hit[1], body.get("id"))
        if kind == "fact_forget":
            return 200, store.forget_fact(hit[1], hit[2])
        if kind == "bench":
            return 200, {"ok": True,
                         "benchmark": store.update_benchmark(hit[1], hit[2], body, here=here)}
        if kind == "bench_delete":
            store.delete_benchmark(hit[1], hit[2])
            return 200, {"ok": True, "deleted": True}
        if kind == "log":
            return 200, {"ok": True, "benchmark": store.log(hit[1], hit[2], body.get("value"),
                                                            at=body.get("at"), source="app")}
        if kind == "result_delete":
            store.delete_result(hit[1], hit[2], hit[3])
            return 200, {"ok": True, "deleted": True}
        if kind == "unmark":
            return request_unmark(hit[1], hit[2], body, store=store, **card)
    except Exception as exc:
        return _err(exc)
    return 404, {"ok": False, "error": "no such route"}


def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the projects routes are
    answered here, after the server's own origin and token checks. Every
    other request goes straight to the original. Returns the banner line."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_projects", False):
        _ARMED = True
        return "  projects   Projects (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if parse_route(route) is None:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if parse_route(route) is None:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, here=_from_this_pc(*_peer_local(self)))
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_projects = True
    do_POST._jarvis_projects = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    try:
        n = len(get().list())
    except Exception:
        n = 0
    return f"  projects   Projects: {n} kept"


_ARMED = False


def _reset_for_tests() -> None:
    global _ARMED, _ONE
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["withdrawn"].clear()
        _P_STATE["last"].clear()
        _M_STATE["pending"].clear()
        _M_STATE["withdrawn"].clear()
        _M_STATE["last"].clear()
    with _LOG_LOCK:
        _LOG_STATE["pending"].clear()
        _LOG_STATE["withdrawn"].clear()
        _LOG_STATE["last"].clear()
    with _ONE_LOCK:
        _ONE = None
    _ARMED = False
