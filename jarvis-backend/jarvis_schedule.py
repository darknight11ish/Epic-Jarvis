"""jarvis_schedule.py - the one scheduler: timers, alarms, one-time and
repeating reminders, and the to-do list.

NEW MODULE, shipped whole (schedule.patch adds the routes and starts it).

THE OWNER'S DECISIONS (2026-09-25, CLAUDE.md)
  * Timers, reminders and ONE shared scheduler come first. Briefings, sleep
    mode and the overnight tidy will be new KINDS of job on this scheduler,
    not a scheduler each (register_kind below is how they plug in). The
    morning briefing is the first (jarvis_briefing.py, loaded by get()
    through KIND_MODULES): a kind may repeat through the same one card
    (`repeatable`) and put its own lines on it (`card_note`).
  * A plain timer or a one-time reminder needs no approval card. Anything
    that repeats asks once, with a card that lists the next run times -
    REPLACED on 2026-09-26 (below) for plain repeats.
  * 2026-09-26, after the approvals audit (docs/APPROVALS-AUDIT-2026-09-26.
    md): plain repeating alarms and reminders, and the standby schedule,
    need NO card (Kind.plain_repeat). Only the owner's own words or taps can
    set one, and deleting is instant. The next times are in the answer
    (repeat_set_words) and under the job in Coming up. The morning briefing
    and "tell me when" keep their ONE card: they read email or the calendar.
  * Simple commands like timers are answered without the AI model
    (jarvis_quick.py), so they work when the model is slow, unloaded or
    asleep. Nothing in this file talks to a model or opens a socket.

WHY NOT THE INITIATIVE ENGINE (rebuilt/jarvis_initiative.py)
It was the first place to look, and it cannot host this cleanly, for four
reasons that are facts about that file, not taste:
  1. Its clock is a heartbeat of 30 minutes, with a floor of one minute. A
     ten-minute timer needs to go off within a second or two.
  2. Its findings live in memory only and are gone on a restart. A reminder
     for next Tuesday has to survive the PC restarting.
  3. It only runs when `[initiative] enabled` is true. The owner asked for
     timers; they must not stop because background checks were switched off.
  4. A finding carries its text in the payload of /api/initiative. A
     reminder's words are private and are read by id, one at a time.
So there is still ONE scheduler - this one. The initiative engine's
heartbeat can move onto it later as one more kind ("check"); until then the
engine is left as it is. The daily digest ([arbiter] in the toml) lives in
jarvis_arbiter.py on the owner's PC, which this repository does not hold, so
nothing here writes to it. The toml's own rule covers timers anyway:
"Anything you ASKED for is exempt and is not counted" - every job here was
asked for.

WHAT IS KEPT, AND WHERE
`schedule.db` in the Jarvis settings folder, beside memory.db and
feedback.db (JARVIS_SCHEDULE_DB overrides it, for the tests). One row per
job. A reminder's or a to-do's words are kept in that file as the owner
said them - plain SQLite on this PC, like memory.db. They are never written
to a log (the audit log gets the id and the kind), never put on the event
bus, and never sent anywhere: this file opens no socket.

A job that went off is kept for FIRED_KEEP (a day), so an app that was
asleep can still read what it was by its id; a to-do marked done is kept for
DONE_KEEP (a week). Then they are gone.

THE CLOCK AND THE TIME ZONE
The PC's own local time, read through the C library (time.mktime and
time.localtime), which follows Windows' own time-zone and daylight-saving
settings - no time-zone database is needed on the PC. A daily 07:00 stays
07:00 across a clock change. Two edge cases, decided rather than left to the
library:
  * a time that does not exist (the hour the clocks go forward - 01:30 on
    that night in the UK) goes off the moment the clocks jump (02:00);
  * a time that happens twice (the hour the clocks go back) goes off the
    FIRST time, once.
A timer is a length of time, not a clock time: ten minutes is 600 seconds
whatever the clocks do.

MISSED WHILE THE PC WAS OFF OR ASLEEP
A job found overdue by more than LATE_AFTER goes off ONCE, late, and says
"missed at 07:00". A repeating job then moves straight to its next time
after now - it never goes off once for every time it missed. Never a burst.

THE EVENT
`schedule` on the bus: `{"id", "kind", "state"}` and, for a job going off,
`"late": true|false`. Ids and the kind only - never the words (ARCHITECTURE
section 6: every event is a doorbell). `state` is "fired" when a job goes
off and "changed" when the list changed (added, paused, deleted, a card
decided). The apps read the words by id: `GET /api/schedule?id=<id>`.

REPEATING JOBS AND THE CARD
A plain alarm, reminder or standby schedule (Kind.plain_repeat, 2026-09-26)
is on the list at once, with no card: the answer says its next three times.
Any other kind that repeats (the briefing, "tell me when") has one approval
card, action `schedule_repeat`, tier "ask" (anything else is refused: a
config line must not become the owner's yes). The card says what it is,
when, and the next three times it will go off, in plain words. The job
waits, doing nothing, until the card is approved. Denied, timed out or
refused: the job is removed. Deleting it while the card waits withdraws it.
Stopping or deleting any job is immediate - it only makes things quieter.

KINDS THAT PLUG IN (register_kind)
The first is the standby schedule (jarvis_standby_schedule.py, 2026-09-25):
a WINDOW - {"every": "day", "at": "01:00", "until": "07:00"} - that goes
off at both ends, one of its kind at a time, and notifies nobody (its event
says "notify": false, so neither app shows a toast or a notification at
01:00). Since 2026-09-26 it is set up at once with no card (plain_repeat),
and deleted like any job. KIND_MODULES below imports it before the loop
first starts.

"Tell me when" (jarvis_tellme.py, 2026-09-25) is a kind that LOOKS every
few minutes and tells the owner only when something happened. It brings
its own rule check (every N minutes, with an end date - the shared
check_rule still refuses minutes, so every other repeat keeps the hourly
floor), its own card, and is `silent`: a look rings no doorbell. See
Kind's hooks below.

NO BULK
Every change names ONE job. There is no "delete all", no "mark everything
done" - here, in the routes, or in either app. The one exception, asked for
by the owner's plan of 2026-09-25 (docs/CREATIVITY-AUDIT-2026-09-25.md, item
6): a NAMED list ("shopping") can be cleared in one go from the apps, after
an "are you sure?" there, and only when the app names how many items it saw
(clear_list below) - so nothing added since the owner looked is lost. The
to-do list itself is never cleared at once, and nothing is cleared by voice.

SNOOZE, "CANCEL THAT" AND NAMED LISTS (2026-09-25, the creativity audit's
everyday quick wins)
  * Snooze: a timer, alarm or reminder that went off can be snoozed. It
    makes a NEW one-off copy of the job, due after the snooze (10 minutes
    unless said otherwise); a repeating job's own times are not touched, so
    only that one occurrence moves. No card - a one-off needs none.
  * "Cancel that": the fast path (jarvis_quick.py) notes what it just set,
    per conversation, in memory (note_set / take_set). Only that, only for
    UNDO_WINDOW seconds, and only once.
  * Named lists: a to-do item may carry a list name ("shopping"); none is
    the to-do list. One limit (MAX_TODO) for every list together.

CONTEXT-RICH REMINDERS, AND WHAT IS KEPT WHEN THEY CANNOT BE SCRUBBED
(GTD-1 follow-up, Gemini's Q2 ruling, 2026-10-18)
A reminder may carry a context packet - a short summary, names, opaque file
labels, a suggested prompt - and every word of it goes through `jarvis_scrub`
before it is stored. When the scrubber is missing or raises, the packet is
dropped WHOLE rather than stored half-scrubbed (privacy review F1/F2). What
remains is ONE plain boolean on the reminder view,
`context_dropped_unscrubbed: True`, and nothing else: no summary, no names, no
ids, and deliberately NO HASH of the dropped words. A hash of a guessable name
or sentence is a secret oracle (try a candidate, compare the hash) and tells
the owner nothing useful; the boolean says only "this reminder had context
that could not be checked, so none of it was kept". It is absent on an
ordinary reminder, on an old row written before the flag existed, and when
the scrubber worked.
"""
from __future__ import annotations

import atexit
import datetime
import hashlib
import importlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import jarvis_sqlite

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

#: Overdue by more than this and a job says it was missed. The tick loop
#: wakes at least every TICK_MAX seconds, so on a PC that is awake nothing
#: is ever this late; a PC that slept or was off is.
LATE_AFTER = 120.0

#: The longest the loop sleeps between looks, in seconds. It also wakes at
#: once when a job is added or changed (poke()).
TICK_MAX = 30.0

#: How long a job that went off stays readable by id, and a done to-do.
FIRED_KEEP = 24 * 3600.0
DONE_KEEP = 7 * 24 * 3600.0

#: Limits. Each is said plainly when it is reached.
MAX_TEXT = 300
MAX_JOBS = 100               # timers, alarms, reminders and repeating jobs
MAX_TODO = 300               # open to-do items
MAX_TIMER = 24 * 3600.0      # a timer is for today; later is a reminder
MIN_TIMER = 1.0
MAX_AHEAD = 366 * 24 * 3600.0
#: "every N hours": never more often than this. Anything more frequent is a
#: nag, not a reminder.
MIN_EVERY_HOURS = 1
MAX_EVERY_HOURS = 24 * 7

#: Snooze: how long, unless the owner says (10 minutes), and the shortest
#: and longest. A snooze is a one-off, so it needs no card.
SNOOZE_DEFAULT = 600.0
SNOOZE_MIN = 60.0
SNOOZE_MAX = MAX_TIMER
#: The kinds that can be snoozed once they went off.
SNOOZABLE = ("timer", "alarm", "reminder")
#: Something that went off is shown under "Just went off" in both apps, and
#: is what a spoken "snooze" means, for this long.
WENT_OFF_SHOWN = 3600.0

#: "Cancel that": how long after the fast path set something it may be
#: taken back by saying so, and how long the note is kept to say "that was
#: too long ago" instead of handing the sentence to the model.
UNDO_WINDOW = 120.0
UNDO_REMEMBER = 30 * 60.0

#: Named lists ("shopping", "packing"). None is the to-do list itself.
MAX_LISTS = 20
MAX_LIST_NAME = 30
DEFAULT_LIST_TITLE = "To-do list"

#: The approval action for anything that repeats.
ACTION = "schedule_repeat"

#: The approval action for a reminder that asks to RUN something (2026-10-27).
#: ONE name for the whole feature, so there is one title, one risk line and one
#: tier: a reminder's `run-task` action is the only kind that acts, and it acts
#: only after this card is approved, once per time it goes off.
ACTION_SCHEDULE = "schedule_action"

# ---- a reminder's action (2026-10-27, the owner's request) -----------------
#
# "id likee to set custom reminders that open something or do an action if i
# ask jarvos to make a specific remonder" - so ONE reminder may carry ONE
# action, and the whole design is built on one line:
#
#   Showing the owner something is not acting. Doing something is.
#
# A kind that only SHOWS (`show-note`, `open-webpage`, `open-file`) fires with
# a notice and an Open button, and nothing happens until a person presses it -
# no card, because nothing is opened by itself and opening writes nothing.
# A kind that DOES something (`run-task`) raises ONE `schedule_action` card at
# fire time and runs nothing without a yes (see `Scheduler._fire_action`).
#
# The block is additive: a reminder written before this has `action` NULL, no
# payload key appears for it, and every old client ignores the field. There is
# deliberately NO "run a command" kind and no free text (DESIGN section 2.3):
# the target is a URL, a file on the allow-list, a note, or a name from the
# closed list below.

#: The kinds this slice knows, exactly. Lower-case hyphenated words, never
#: free text, so a client can switch on them.
#:
#: `ask` (2026-11-02, the owner's "maximum flexibility" round) is the fifth and
#: the only one that is a QUESTION rather than a target: see the ASK block
#: below. It is additive like every other kind - a reminder written before it
#: has `action` NULL and grows no key at all.
ACTION_KINDS = ("show-note", "open-webpage", "open-file", "run-task", "ask")

#: The ONE payload key each kind carries, and no other. `app` (open-app) is
#: reserved by the design and deliberately NOT shipped: the only resolver for a
#: program is the desktop's Start-menu index (`open_app.rs`), so shipping it
#: would mean duplicating that index in Python or adding a general exec path.
#:
#: `ask` carries THREE keys (`question`, `buttons`, `record`), so it is the one
#: kind whose block is not "a kind plus one key"; `ASK_BLOCK_KEYS` below is its
#: own shape and `_clean_ask` is its own check. `question` is named here because
#: it is the one word both apps show first.
ACTION_PAYLOAD = {"show-note": "note", "open-webpage": "url", "open-file": "path",
                  "run-task": "task", "ask": "question"}

#: The kinds that ACT, and therefore raise the one card at fire time.
ACTING_ACTION_KINDS = ("run-task",)

#: The closed list of tasks a reminder may ask to run. Two names, both already
#: one callable on this PC; adding a third is a code change with a test that
#: pins the list. Nothing here is a program, a command or a path.
#:
#: `backup` is named by the design as the second target and is REFUSED when the
#: action is saved - see `_task_problem`. A backup is encrypted with a fresh
#: random recovery code (`jarvis_backup.generate_code`, "never logged, never
#: written to a file, never kept by this module past the response that shows it
#: once"), and a reminder that fired at 07:00 has nobody to show it to, so it
#: would write an archive nobody could ever open. A backup that cannot be
#: opened is worse than no backup at all, and putting the code in the card
#: would write a credential to `approvals.db` in plain text. `briefing` has no
#: such secret: it is built, kept and announced "ready" exactly as a briefing
#: job's own on_fire does.
ACTION_TASKS = ("briefing", "backup")

#: Limits, each said in a sentence when it is reached.
MAX_ACTION_BYTES = 4096
MAX_ACTION_URL = 1024
MAX_ACTION_PATH = 1024
MAX_ACTION_NOTE = 500
MAX_ACTION_LINES = 10

#: What "open a file" may open. "Open a file" means "run whatever is registered
#: for it", so the extension is the security boundary: `.lnk`, `.exe`, `.bat`,
#: `.cmd`, `.ps1`, `.msi`, `.scr`, `.html` and `.svg` are never openable this
#: way. The same list is checked again at the moment of opening.
ACTION_FILE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf",
                    ".txt", ".md", ".docx", ".doc", ".xlsx", ".pptx", ".csv")

#: The sentences. Each one is a whole sentence with no code in it, because
#: every one of them is shown to the owner as it is.
NOT_IN_FOLDERS = ("That file is not in a folder Jarvis may look in. Add its folder "
                  "in Settings, Folders.")
NOT_A_FILE = ("Jarvis can open pictures, PDFs, text and Office files. It will not "
              "start a program from a file.")
NOT_HTTPS = ("A web address starts with https:// - copy it from your browser's "
             "address bar.")
#: The one sentence a file that has gone gets, at save time and at the tap.
FILE_GONE = "That file is not there any more."
_NO_ACTION_KIND = ("An action is one of: show a note, open a web page, open a file, "
                   "do a task, or ask a question with buttons.")

# ---- a reminder that ASKS, and the owner's own buttons (2026-11-02) ----------
#
# The owner's second request of 2026-11-02, verbatim in substance: *"I would like
# to tell Jarvis exactly how I want the reminder to appear and what interactive
# elements there are - e.g. 'hey Jarvis remind me to take a medication at 10:00
# a.m.' -> at 10:00 a.m. a notification on my Android phone saying 'Did you take
# your medication?' with a Yes or No button"*, and then *"as much flexibility or
# options as I want"*.
#
# So ONE reminder may now carry a QUESTION and up to three buttons the owner
# wrote himself, instead of one target. The line the whole block is built on is
# the same one the other kinds use:
#
#   Showing the owner something is not acting. Doing something is.
#   Answering a question is neither: it is a log line, like ticking a to-do.
#
# Nothing here can run a program, a command, a script or a webhook, and no answer
# raises an approval card - an answer is cardless, exactly as `act("done")` is.
# The design is `DESIGN.md` ("Reminder actions v2"), and the tests are
# `backend/test_schedule_ask.py`.
#
# WHAT A BUTTON MAY DO. Exactly one of these three verbs, per button:
#
#   record   write the answer to the destinations below (the log line itself,
#            the journal, a goal's progress, a habit tick)
#   done     mark the reminder done (a one-off leaves "Just went off"; a
#            repeating one stops repeating - it only ever makes Jarvis quieter)
#   snooze   the same one-off copy every other Snooze makes, N minutes later
#
# `open-file` / `open-webpage` are deliberately NOT here in this build, and the
# refusal says why in one sentence: the desktop's ONE opener
# (`open_reminder_target`, reminder_open.rs) opens a reminder's own single
# action and takes the job id only, so a per-button target would need a SECOND
# opener in Rust. That is a security surface (a page that can name a path is an
# exec primitive) and belongs to whoever owns that command, not to this lane.
# The sentence the owner gets says "for now" and names the two kinds that do
# open things, so the limit is visible instead of looking like a bug.
#
# Deliberately NOT named `ACTION_*`: `backend/test_card_words.py` scans this
# folder for module-level `ACTION...` constants, because each of those is a GATE
# ACTION and needs a plain-title row in `jarvis_card_words` (`ACTION` is
# `schedule_repeat`, `ACTION_SCHEDULE` is `schedule_action`). `ask` is a KIND of
# reminder action and raises no card at all, so it must not look like one.
ASK_KIND = "ask"

#: The three keys an `ask` block has, and no others - the shape `_clean_ask`
#: checks and `_decode_ask` checks again.
ASK_BLOCK_KEYS = frozenset({"kind", "question", "buttons", "record"})

#: What ONE button may do. Never a program, a command, a script or a webhook:
#: this tuple IS that rail, and `_ASK_FORBIDDEN` names the words that get their
#: own sentence so the owner is told why rather than "not a kind".
ASK_DOES = ("record", "done", "snooze")

#: The words someone may reach for that this build refuses BY NAME, so the
#: refusal is about what they asked for instead of a generic one. Their message
#: is `ASK_NO_ACT`.
_ASK_FORBIDDEN = ("open-file", "open-webpage", "open", "run", "run-task", "shell",
                  "command", "script", "webhook", "program", "exec")

#: Limits, each said in one sentence when it is reached. A button label is
#: bounded because Android cuts a notification action's label at about 20
#: characters and a label the owner cannot read is worse than a refused one.
MAX_ASK_QUESTION = 200
MAX_ASK_QUESTION_LINES = 3
MAX_ASK_BUTTONS = 3
MAX_ASK_LABEL = 24
ASK_SNOOZE_MIN = 1
ASK_SNOOZE_MAX = 1440            # a day - the same ceiling a timer has
#: How many answers a reminder keeps. A log, not a history of everything: the
#: newest 40 taps is enough to see "I said Taken at 10:00 every day this month",
#: and the row itself is deleted FIRED_KEEP after it last went off.
MAX_ANSWERS = 40

#: The four recording DESTINATIONS an `ask` block may switch on, in the order
#: the answer writes them. `history` is the reminder's own log; `obsidian_daily`
#: appends one plain line to that day's Obsidian note; `goal` and `habit` write
#: progress / a tick through the other module, when this PC has it.
ASK_DESTINATIONS = ("history", "obsidian_daily", "goal", "habit")

#: What the owner reads when a destination is chosen but this PC cannot do it
#: yet. One plain sentence each, never a code, and never a promise: the goal
#: progress log and the habit record are other lanes' modules, and a tree
#: without them says so instead of failing quietly.
GOAL_NOT_SET_UP = ("Goal progress is not set up on this PC yet, so that part was not "
                   "written. The answer itself was kept.")
HABIT_NOT_SET_UP = ("Habit ticks are not set up on this PC yet, so that part was not "
                    "written. The answer itself was kept.")
JOURNAL_NOT_SET_UP = ("Today's Obsidian note was not written: your Obsidian vault is not "
                      "set up on this PC, so only the answer was kept.")
#: A destination that exists but refused or raised. The exception's own words are
#: never shown (they could quote a path), so these are the fixed sentences.
_GOAL_FAILED = "Goal progress could not be written this time."
_HABIT_FAILED = "The habit tick could not be written this time."
_JOURNAL_FAILED = "Today's Obsidian note could not be written this time."

#: Refusals, each ONE sentence shown as it is.
ASK_NO_ACT = ("A button can record the answer, mark the reminder done, or snooze it. "
              "This build has no button that opens a file or a page: the desktop's one "
              "opener opens a reminder's single own action, and a second one has to be "
              "built on the PC first.")
ASK_NOT_FIRED = "That reminder has not gone off yet, so there is nothing to answer."
ASK_WRONG_KIND = "That reminder does not ask a question."
ASK_GONE = "That reminder has gone - the answer was not kept."

#: How many future times the card and the list show for a repeating job.
NEXT_SHOWN = 3

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

# --------------------------------------------------------------------------
#   Kinds
# --------------------------------------------------------------------------
#
# `kind` is free text in the database, checked against this table. A later
# feature (a morning briefing, the overnight tidy, sleep mode) adds its own
# with register_kind() - no change to the table, the loop, the routes or the
# event. What each kind's job does when it goes off beyond ringing the
# doorbell is its `on_fire` (None: the doorbell and the apps' notification
# are the whole of it).

class Kind:
    def __init__(self, name: str, noun: str, lock_screen: str, *, has_text: bool,
                 on_fire: Optional[Callable[[str], None]] = None,
                 owner_listed: bool = True, notify: bool = True, window: bool = False,
                 single: bool = False, edges: tuple = ("", ""), about: tuple = (),
                 note: Optional[Callable[[str], str]] = None, repeatable: bool = False,
                 card_note: tuple = (), check: Optional[Callable] = None,
                 card: Optional[Callable] = None, silent: bool = False,
                 add: Optional[Callable] = None, first_now: bool = False,
                 fields: Optional[Callable[[str], dict]] = None, what: str = "",
                 leaves: bool = False, plain_repeat: bool = False, ends: bool = False):
        self.name = name
        self.noun = noun                 # "timer", "reminder"
        self.lock_screen = lock_screen   # what a locked phone may show
        self.has_text = has_text
        self.on_fire = on_fire
        self.owner_listed = owner_listed
        # False: going off is not something to tell the owner about (the
        # standby schedule, at 01:00). The event then carries
        # "notify": false and neither app shows a notification or a toast.
        self.notify = notify
        # True: a job of this kind is a WINDOW - {"every": "day", "at":
        # "01:00", "until": "07:00"} - and goes off at both ends. on_fire
        # reads in_window() to know which end it is, so a late start and a
        # late end found together (the PC was off all night) agree.
        self.window = window
        # True: at most one job of this kind on the list at a time.
        self.single = single
        # The words for a window's two ends in the list: ("on standby",
        # "awake") -> "next: awake at 07:00 tomorrow". An optional third
        # word is said after the END's time: the standby schedule's
        # ", if the schedule put it on standby" -> "awake at 07:00 today, if
        # the schedule put it on standby" (the owner's decision of
        # 2026-09-25: it wakes only what it put on standby).
        self.edges = edges
        # Extra lines for the approval card, saying what it does.
        self.about = tuple(about)
        # note(job_id) -> one sentence about how it last went ("" for none),
        # shown under the job in both apps. Never raises into the list.
        self.note = note
        # A later kind that may repeat (the morning briefing) - through the
        # same ONE schedule_repeat card as an alarm or a reminder.
        self.repeatable = repeatable
        # Its card's own lines about what each run does and what it reads,
        # in place of the plain "nothing is sent anywhere" paragraph.
        self.card_note = tuple(card_note)
        # "Tell me when" (jarvis_tellme.py, 2026-09-25) - a kind that LOOKS
        # at something every few minutes and tells the owner only when it
        # matches. These let a kind do that without a scheduler of its own:
        #   check(rule, now) -> rule   its own rule check, used instead of
        #                              check_rule (which keeps the hourly
        #                              floor for every other kind);
        #   card(rule, text, now)      the whole approval card, in its words;
        #   silent                     going off rings NO doorbell - a look
        #                              is not news; the kind publishes its
        #                              own event when there is something;
        #   add(body) -> (code, body)  POST /api/schedule/add for this kind;
        #   first_now                  once approved, the first run is now,
        #                              not one interval later;
        #   fields(job_id) -> dict     extra fields for the job's view;
        #   what                       the card's short "what" line;
        #   leaves                     each run asks a server outside this
        #                              PC (the owner's own), said on the card.
        self.check = check
        self.card = card
        self.silent = silent
        self.add = add
        self.first_now = first_now
        self.fields = fields
        self.what = what
        self.leaves = leaves
        # True: a repeating job of this kind is set up at once, with NO
        # card (the owner's decision of 2026-09-26, after the approvals
        # audit): plain alarms and reminders, and the standby schedule.
        # Only the owner's own words or taps can set one, it acts only on
        # this PC, and deleting it is immediate. False (the default, so a
        # kind added later asks): ONE schedule_repeat card, as before - the
        # morning briefing and "tell me when", which read email or the
        # calendar.
        self.plain_repeat = plain_repeat
        # True: a job of this kind has no time of its own - its `due` is the
        # day it ENDS, quietly ("remind me next time I talk about X",
        # jarvis_next_time.py, 2026-09-28: gone after 90 days). The list
        # says "until <day>" instead of a time it goes off; going off at the
        # end rings no doorbell (such a kind is also `silent`).
        self.ends = ends


KINDS: dict = {}

#: Modules that add a kind of their own (register_kind, on import). get()
#: imports each one before the loop first runs, so a job of that kind that
#: is already due - missed while the PC was off - finds its on_fire there.
#: A module that is missing is skipped: its jobs still go off, as a doorbell.
#: jarvis_focus (2026-09-25): the end of a focus session - not listed in
#: Coming up (the focus panel counts down), and it tells nobody.
#: jarvis_next_time (2026-09-28): "remind me next time I talk about X" - no
#: time of its own; its due is the day it ends, quietly (Kind.ends).
#: jarvis_tidy (2026-09-28): the overnight tidy's hourly look - not listed in
#: Coming up, tells nobody, and runs at most once a day, only while the
#: owner's "Overnight memory tidying" switch is on; it only raises cards.
#: jarvis_today (2026-09-28): Today cards - the owner's own words shown on
#: the Today part of both apps at a time, on chosen days; no card (like a
#: plain repeat), and going off only tells the apps the list changed.
#: jarvis_decks (2026-09-30): the quiet `review` job - "N cards ready" under
#: Coming up while the owner has a deck; no card, no notification.
#: jarvis_topics (2026-09-30): the quiet hourly `topic_sort` step that labels the
#: facts already saved (rules only, labels only) and, if the owner switched it
#: on, asks the local model to suggest a topic for a few Unsorted facts a night.
#: Not listed in Coming up, tells nobody, changes no fact.
#: jarvis_referee (2026-09-30): the quiet hourly look for "This looks done - tick
#: it?" (Referee suggestions, a second-card switch). Not listed in Coming up, tells
#: nobody; it only ever raises a card and ticks nothing by itself.
#: jarvis_tag_suggest (2026-09-30): the quiet hourly `tag_suggest` step behind
#: "Suggest tags overnight" (once a night, 01:00-06:00 local, only while the owner's
#: switch is on). Not listed in Coming up, tells nobody; it only raises cards and
#: files nothing by itself.
KIND_MODULES = ("jarvis_standby_schedule", "jarvis_briefing", "jarvis_tellme", "jarvis_focus",
                "jarvis_next_time", "jarvis_tidy", "jarvis_today", "jarvis_decks",
                "jarvis_topics", "jarvis_referee", "jarvis_tag_suggest")


def register_kind(name: str, noun: str, lock_screen: str, *, has_text: bool = False,
                  on_fire: Optional[Callable[[str], None]] = None,
                  owner_listed: bool = True, notify: bool = True, window: bool = False,
                  single: bool = False, edges: tuple = ("", ""), about: tuple = (),
                  note: Optional[Callable[[str], str]] = None, repeatable: bool = False,
                  card_note: tuple = (), check: Optional[Callable] = None,
                  card: Optional[Callable] = None, silent: bool = False,
                  add: Optional[Callable] = None, first_now: bool = False,
                  fields: Optional[Callable[[str], dict]] = None, what: str = "",
                  leaves: bool = False, plain_repeat: bool = False,
                  ends: bool = False) -> Kind:
    """Add a kind of job. For the features still to come (briefing, tidy,
    sleep): their job goes off through the same loop, the same missed-while-
    off rule and the same event; `on_fire(job_id)` is called after the event,
    on its own thread, and nothing it raises stops the loop.

    The standby schedule (jarvis_standby_schedule.py) is a window kind,
    single, that notifies nobody. `repeatable` (the morning briefing): it may
    be set up to repeat, which asks ONCE with the schedule_repeat card, like
    a repeating reminder."""
    if not re.fullmatch(r"[a-z][a-z_]{1,23}", str(name or "")):
        raise ValueError("a kind is a short lower-case word")
    k = Kind(name, noun, lock_screen, has_text=has_text, on_fire=on_fire,
             owner_listed=owner_listed, notify=notify, window=window, single=single,
             edges=edges, about=about, note=note, repeatable=repeatable,
             card_note=card_note, check=check, card=card, silent=silent, add=add,
             first_now=first_now, fields=fields, what=what, leaves=leaves,
             plain_repeat=plain_repeat, ends=ends)
    KINDS[name] = k
    return k


def _repeatable(kind: str) -> bool:
    k = KINDS.get(kind)
    return kind in ("alarm", "reminder") or bool(k is not None and k.repeatable)


register_kind("timer", "timer", "Jarvis: your timer is done.", has_text=True)
register_kind("alarm", "alarm", "Jarvis: alarm.", has_text=True, plain_repeat=True)
register_kind("reminder", "reminder", "Jarvis: a reminder is due.", has_text=True,
              plain_repeat=True)
register_kind("todo", "to-do", "Jarvis: a to-do item is due.", has_text=True)

# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    # The same folder memory.db and feedback.db are in.
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
    env = os.environ.get("JARVIS_SCHEDULE_DB")
    return Path(env) if env else _config_dir() / "schedule.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id        TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    text      TEXT NOT NULL DEFAULT '',
    state     TEXT NOT NULL,
    due       REAL,
    rule      TEXT,
    duration  REAL,
    left_s    REAL,
    created   REAL NOT NULL,
    changed   REAL NOT NULL,
    fired_at  REAL,
    fired_due REAL,
    late      INTEGER NOT NULL DEFAULT 0,
    source    TEXT NOT NULL DEFAULT 'app'
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state, due);
CREATE TABLE IF NOT EXISTS commands (
    digest TEXT PRIMARY KEY,
    at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

#: Columns added after the first release (2026-09-25): a file made before
#: them gets them on open, empty. `list_name`: a to-do item's named list
#: (NULL: the to-do list). `snooze_of`: a snoozed copy's original job.
#: `snoozed_to`: the copy made from a job that went off (cleared when a
#: repeating job goes off again). `extra` (2026-09-28): a kind's own small
#: JSON state, written and read only by that kind's module through
#: Scheduler.extra()/set_extra() - "remind me next time I talk about X"
#: keeps its trigger words and how often it was brought up there. Never
#: handed out by _view: a kind shows what it wants through `fields`.
_ADDED_COLUMNS = (("list_name", "TEXT"), ("snooze_of", "TEXT"), ("snoozed_to", "TEXT"),
                  ("extra", "TEXT"),
                  # GTD-1 (2026-10-18): a reminder's context packet, its
                  # trigger kind, how often it has been snoozed, when it was
                  # resolved, and the optional read-only condition it watches.
                  # All nullable/empty for every row written before this, so
                  # an old schedule.db reads exactly as it did.
                  ("context_bundle", "TEXT"), ("trigger", "TEXT"),
                  ("snooze_count", "INTEGER"), ("resolved_at", "REAL"),
                  ("condition_kind", "TEXT"), ("condition_target", "TEXT"),
                  # Wave D-1 (2026-10-22): "Ready for your review" - a time
                  # Jarvis finished its part and is waiting for the OWNER. It
                  # is never a done state; only act("done") moves a to-do to
                  # done, exactly as before.
                  ("ready_for_review", "REAL"),
                  # HUD Reminders Phase 2 (2026-10-22): a to-do item's position
                  # WITHIN its list (0-based). NULL for every row written before
                  # this and for done/fired rows; the open path below backfills
                  # each list 0..n-1 once, deterministically, and old code
                  # ignores the column, so a code rollback stays safe.
                  ("rank", "INTEGER"),
                  # Schedule-source taint (2026-10-26): "read_outside" on a job
                  # written while jarvis_gate's private latch was on, so the
                  # taint outlives the latch's own minutes instead of dying
                  # with it. A row written BEFORE this column exists reads as
                  # NULL and is treated as trusted - deliberate: there is no
                  # way to know, and marking every old reminder tainted would
                  # latch on a job nobody read anything for. The latch is
                  # replayed once when the job fires (see `tick`).
                  ("source_taint", "TEXT"),
                  # A reminder's ONE action (2026-10-27): JSON, NULL for every
                  # row that has none - which is every row written before this
                  # and every job that is not a reminder. `_view` hands it out
                  # only when it decodes to a known kind, and old code ignores
                  # the column, so a code rollback stays safe: the same contract
                  # `rank` was added under.
                  ("action", "TEXT"),
                  # The day a to-do item was written (2026-11-02, the owner's
                  # choice; Gemini's ruling 8): a calendar day as YYYY-MM-DD in
                  # THIS PC's own local time. It is written once, when the row
                  # is created, and never rewritten - not at midnight, not by an
                  # edit, not by the mode switch. It is what "carry over with a
                  # tag saying how old it is" is measured from, so a rollover
                  # that moved it to today would erase the very thing being
                  # shown. Every row written before this column exists is
                  # backfilled from its own `created` stamp (or today, for a
                  # legacy row with no usable stamp) the first time this code
                  # opens the file; see `_backfill_created_dates`. Old code
                  # ignores the column, so a code rollback stays safe.
                  ("created_date", "TEXT"),
                  # A reminder's answer log (2026-11-02): the newest MAX_ANSWERS
                  # taps on an `ask` reminder's own buttons, as JSON - when, the
                  # label, what that button did, and what was written. NULL for
                  # every row that has never been answered, which is every row
                  # written before this and every job that is not an `ask`
                  # reminder. It is the ONLY new stored thing the feature adds,
                  # and the row itself is deleted FIRED_KEEP after it last went
                  # off, so the log goes with it. Old code ignores the column, so
                  # a code rollback stays safe - the contract `action` came in on.
                  ("answers", "TEXT"))

#: The one value `jobs.source_taint` holds. It is a value, not a boolean, so
#: a later reason (a pasted-text job, say) can be added without a rewrite.
#:
#: MEASURED 2026-10-26, against every `register_kind(on_fire=...)` callback in
#: this checkout (twelve: briefing, decks, focus, goals, next_time, referee,
#: standby_schedule, tag_suggest, tellme, tidy, today, topics): NONE of them
#: starts an agent turn or runs a tool. They do local work or read a mailbox's
#: metadata, and three ask a loopback model directly (topics, tag_suggest,
#: tidy) - never through jarvis_agent's tool loop. So replaying the mark on
#: fire is DEFENCE IN DEPTH for a future on_fire that can start a turn, not a
#: fix for a live exploit. It does have a live effect for any module that asks
#: the latch after a firing: the latch's own 30 minutes no longer decide.
SOURCE_TAINT = "read_outside"


def _taint_mark() -> Optional[str]:
    """The mark a row written or edited RIGHT NOW must carry.

    None when jarvis_gate cannot be imported: with no latch module there is
    nothing to replay when the job fires either, and failing closed here
    would tag every row on an install that simply does not ship the gate.
    """
    try:
        import jarvis_gate
        return SOURCE_TAINT if jarvis_gate.taint_active() else None
    except Exception:
        return None


def _row_taint(row) -> str:
    """One row's stored mark, "" for none - including a DB opened by a build
    before the column existed (the migration adds it on open, but a row read
    by a caller that never constructed a Scheduler must not raise)."""
    try:
        return str(row["source_taint"] or "")
    except (IndexError, KeyError):
        return ""


def _row_action(row) -> str:
    """One row's stored action JSON, "" for none - the same guard `_row_taint`
    makes, for the same reason (a row read before the migration ran)."""
    try:
        return str(row["action"] or "")
    except (IndexError, KeyError):
        return ""


def _latch_fired_taint(tag: str) -> bool:
    """Replay a fired row's mark through the one process-wide latch."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why="scheduled_task:" + str(tag)))
    except Exception:
        return False


#: States. `active` and `paused` are on the list; `waiting` is a repeating
#: job whose card has not been answered; `fired` is a one-off that went off
#: (kept FIRED_KEEP, readable by id); `done` is a to-do ticked off.
LISTED = ("active", "paused", "waiting")

#: Wave D-1 (Upgrade D6): Jarvis can finish its part, but only the OWNER marks
#: a task done. This is the one sentence both apps show for that state.
READY_SAID = "Ready for your review - only you can mark it done."

# --------------------------------------------------------------------------
#   Local time, and daylight saving
# --------------------------------------------------------------------------

def _wall(t: float) -> tuple:
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)


def wall_to_epoch(y: int, mo: int, d: int, hh: int, mm: int) -> float:
    """The moment this PC's clock reads y-mo-d hh:mm.

    Both daylight-saving readings are tried and only one that really shows
    that time on the clock is kept. Twice (the clocks went back): the
    earlier. Never (the clocks went forward): the moment of the jump."""
    want = (y, mo, d, hh, mm)
    found = []
    for dst in (0, 1):
        try:
            t = time.mktime((y, mo, d, hh, mm, 0, 0, 0, dst))
        except (OverflowError, ValueError):
            continue
        if _wall(t) == want:
            found.append(t)
    if found:
        return min(found)
    # In the gap. The first second whose wall time is at or after the
    # wanted one, found between the two readings (at most two hours apart).
    try:
        a = time.mktime((y, mo, d, hh, mm, 0, 0, 0, 1))
        b = time.mktime((y, mo, d, hh, mm, 0, 0, 0, 0))
    except (OverflowError, ValueError):
        return time.mktime((y, mo, d, hh, mm, 0, 0, 0, -1))
    lo, hi = min(a, b) - 3600, max(a, b) + 3600
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _wall(mid) >= want:
            hi = mid
        else:
            lo = mid
    return float(hi)


def _add_days(y: int, mo: int, d: int, n: int) -> tuple:
    # Noon avoids every clock change; the date is all that is read.
    t = time.mktime((y, mo, d, 12, 0, 0, 0, 0, -1)) + n * 86400
    lt = time.localtime(t)
    # A clock change can move noon by an hour, never by a day.
    return lt.tm_year, lt.tm_mon, lt.tm_mday


def _weekday(y: int, mo: int, d: int) -> int:
    return time.localtime(time.mktime((y, mo, d, 12, 0, 0, 0, 0, -1))).tm_wday


def next_at(hh: int, mm: int, after: float, days: Optional[set] = None) -> float:
    """The next time the clock reads hh:mm after `after`, on one of `days`
    (0 = Monday; None: any day)."""
    lt = time.localtime(after)
    y, mo, d = lt.tm_year, lt.tm_mon, lt.tm_mday
    for n in range(0, 9):
        yy, mmo, dd = _add_days(y, mo, d, n) if n else (y, mo, d)
        if days is not None and _weekday(yy, mmo, dd) not in days:
            continue
        t = wall_to_epoch(yy, mmo, dd, hh, mm)
        if t > after:
            return t
    raise ValueError("no such time in the next week")


# --------------------------------------------------------------------------
#   Repeating rules
# --------------------------------------------------------------------------
#
# A small, fixed set - RRULE-like, not RRULE. Each is a JSON object:
#   {"every": "day",     "at": "07:00"}
#   {"every": "weekday", "at": "07:00"}                   Monday to Friday
#   {"every": "week",    "at": "09:00", "days": [0, 3]}   0 = Monday
#   {"every": "hours",   "hours": 2, "start": <epoch>}    every N hours from start
# and, for a WINDOW kind only (Kind.window - the standby schedule):
#   {"every": "day", "at": "01:00", "until": "07:00"}     goes off at both ends
# Anything else is refused with the reason.

def _hhmm(s) -> tuple:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(s or ""))
    if not m:
        raise ValueError("a time is written HH:MM, like 07:30")
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        raise ValueError("that is not a time of day")
    return hh, mm


#: How many different times of day ONE rule may go off at ("several times in
#: one day", 2026-11-02). Eight is a day's worth of prompts; more is a nag.
MAX_TIMES_A_DAY = 8
#: "Every N days" and "every N weeks": the shortest and the longest. One day is
#: "every day" and belongs to that rule; a year is where a repeat should be a
#: date instead.
MAX_REPEAT_DAYS = 365
MAX_REPEAT_WEEKS = 52
#: How far ahead a rule's optional end date may be.
MAX_RULE_YEARS = 10

#: The sentence every reader gets when a rule names a kind this build does not
#: know. Said as a list of what DOES work, so it is a refusal the owner can act
#: on rather than a code.
_RULE_KINDS = ("a repeat is every day, every weekday, every week on some days, every "
               "N days, every N weeks, every month, or every N hours")


def _rule_times(rule: dict) -> list:
    """The times of day a rule goes off, as (hh, mm), earliest first.

    `at` is ALWAYS the earliest one, so every reader that knows only `at` (an
    older app, the phone's own rule parser) still reads the first time it goes
    off. `times` carries them all and is present only when there is more than
    one, so an ordinary rule's block is byte for byte what it always was."""
    many = rule.get("times")
    if isinstance(many, list) and many:
        return sorted({_hhmm(t) for t in many})
    return [_hhmm(rule.get("at"))]


def _times_checked(rule: dict) -> tuple:
    """(at, times) - the earliest time as "HH:MM", and every time in order.
    ValueError, in one sentence, for no time, a bad one, or too many."""
    times = _rule_times(rule)
    if len(times) > MAX_TIMES_A_DAY:
        raise ValueError(f"a rule goes off at up to {MAX_TIMES_A_DAY} times in one day")
    at = f"{times[0][0]:02d}:{times[0][1]:02d}"
    return at, [f"{hh:02d}:{mm:02d}" for hh, mm in times]


def _whole(value, why: str) -> int:
    """A whole number from a body, or ValueError with `why`."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(why)
    return value


def _rule_anchor(rule: dict, now: float) -> float:
    """The first day a "every N days/weeks/month" rule counts from, as this
    PC's own midnight - the owner's "first occurrence". Accepts a date
    ("2026-11-09") or an epoch, and defaults to today."""
    raw = rule.get("start")
    if raw is None or raw == "":
        lt = time.localtime(now)
        return wall_to_epoch(lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0)
    if isinstance(raw, str):
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw.strip())
        if not m:
            raise ValueError("the first one looks like a date, 2026-11-09")
        y, mo, d = (int(g) for g in m.groups())
        try:
            datetime.date(y, mo, d)
        except ValueError:
            raise ValueError("that first date is not on the calendar")
        return wall_to_epoch(y, mo, d, 0, 0)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("the first one looks like a date, 2026-11-09")
    t = float(raw)
    lt = time.localtime(t)
    return wall_to_epoch(lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0)


def _rule_ends(rule: dict, now: float) -> Optional[float]:
    """The last day a rule may go off, as this PC's own 23:59 - or None.

    An optional end date ("stop this at the end of the month", 2026-11-02).
    Accepts a date ("2026-12-31") or an epoch, and is stored as an epoch float
    under `ends` - the key `jarvis_tellme.py` already writes and `tick` already
    honours, so one code path stops every rule, not a second one for these.
    """
    raw = rule.get("ends")
    if raw is None or raw == "":
        return None
    t: Optional[float] = None
    if isinstance(raw, str):
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw.strip())
        if not m:
            raise ValueError("an end date looks like 2026-12-31")
        y, mo, d = (int(g) for g in m.groups())
        try:
            datetime.date(y, mo, d)
        except ValueError:
            raise ValueError("that end date is not on the calendar")
        t = wall_to_epoch(y, mo, d, 23, 59)
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        t = float(raw)
    if t is None:
        raise ValueError("an end date looks like 2026-12-31")
    if t <= now:
        raise ValueError("that end date has already passed")
    if t > now + MAX_RULE_YEARS * 366 * 86400:
        raise ValueError(f"an end date is up to {MAX_RULE_YEARS} years away")
    return t


def _with_ends(rule: dict, ends: Optional[float]) -> dict:
    """The rule with its optional end date added - and unchanged when it has
    none, so a rule written before this feature is byte for byte what it was."""
    if ends is not None:
        rule = dict(rule)
        rule["ends"] = float(ends)
    return rule


def check_rule(rule, now: Optional[float] = None, *, window: bool = False) -> dict:
    """The rule, tidied, or ValueError with a sentence. `window`: the rule
    is for a window kind, and must be every day from one time to another."""
    if not isinstance(rule, dict):
        raise ValueError("a repeat is an object like {\"every\": \"day\", \"at\": \"07:00\"}")
    every = str(rule.get("every") or "").strip().lower()
    if window:
        # Every day only, for now: it is what the owner asked for ("sleep at
        # 01:00, wake at 07:00, every day"), and the one both apps offer.
        if every != "day":
            raise ValueError("a standby schedule is every day, from one time to another")
        hh, mm = _hhmm(rule.get("at"))
        uh, um = _hhmm(rule.get("until"))
        if (hh, mm) == (uh, um):
            raise ValueError("the start and the end are the same time - pick two different times")
        return {"every": "day", "at": f"{hh:02d}:{mm:02d}", "until": f"{uh:02d}:{um:02d}"}
    if rule.get("until") is not None:
        raise ValueError("only a standby schedule has an end time")
    clock_now = float(now if now is not None else time.time())
    ends = _rule_ends(rule, clock_now)
    if every in ("day", "weekday"):
        at, times = _times_checked(rule)
        out = {"every": every, "at": at}
        if len(times) > 1:
            out["times"] = times
        return _with_ends(out, ends)
    if every == "week":
        at, times = _times_checked(rule)
        days = rule.get("days")
        if (not isinstance(days, list) or not days
                or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 6
                           for x in days)):
            raise ValueError("a weekly repeat needs its days, 0 (Monday) to 6 (Sunday)")
        out = {"every": "week", "at": at, "days": sorted(set(days))}
        if len(times) > 1:
            out["times"] = times
        return _with_ends(out, ends)
    if every == "hours":
        n = rule.get("hours")
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError("\"every N hours\" needs a whole number of hours")
        if n < MIN_EVERY_HOURS:
            raise ValueError(f"the shortest repeat is every {MIN_EVERY_HOURS} hour")
        if n > MAX_EVERY_HOURS:
            raise ValueError("the longest \"every N hours\" is a week; use a weekly repeat")
        if rule.get("times") is not None:
            raise ValueError("an hourly repeat has no times of day - it counts from its start")
        start = rule.get("start")
        if not isinstance(start, (int, float)) or isinstance(start, bool):
            start = float(clock_now)
        return _with_ends({"every": "hours", "hours": n, "start": float(start)}, ends)
    if every == "days":
        n = _whole(rule.get("days"), "\"every N days\" needs a whole number of days")
        if n < 1:
            raise ValueError("every N days starts at every day")
        if n > MAX_REPEAT_DAYS:
            raise ValueError(f"the longest \"every N days\" is {MAX_REPEAT_DAYS}; "
                             f"pick a date instead")
        at, times = _times_checked(rule)
        out = {"every": "days", "days": n, "at": at, "start": _rule_anchor(rule, clock_now)}
        if len(times) > 1:
            out["times"] = times
        return _with_ends(out, ends)
    if every == "weeks":
        n = _whole(rule.get("weeks"), "\"every N weeks\" needs a whole number of weeks")
        if n < 1:
            raise ValueError("every N weeks starts at every week")
        if n > MAX_REPEAT_WEEKS:
            raise ValueError(f"the longest \"every N weeks\" is {MAX_REPEAT_WEEKS}")
        at, times = _times_checked(rule)
        days = rule.get("days")
        if (not isinstance(days, list) or not days
                or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 6
                           for x in days)):
            raise ValueError("a repeat every N weeks needs its days, 0 (Monday) to 6 (Sunday)")
        out = {"every": "weeks", "weeks": n, "at": at, "days": sorted(set(days)),
               "start": _rule_anchor(rule, clock_now)}
        if len(times) > 1:
            out["times"] = times
        return _with_ends(out, ends)
    if every == "month":
        d = _whole(rule.get("day"), "\"every month\" needs its day of the month")
        if d < 1 or d > 31:
            raise ValueError("a monthly repeat is on a day 1 to 31")
        at, times = _times_checked(rule)
        out = {"every": "month", "at": at, "day": d}
        if len(times) > 1:
            out["times"] = times
        return _with_ends(out, ends)
    raise ValueError(_RULE_KINDS)


def _day_ord(y: int, mo: int, d: int) -> int:
    """A date as a plain day count. Calendar arithmetic only - no clock, no
    daylight saving, nothing a time zone can move."""
    return datetime.date(y, mo, d).toordinal()


def _ord_date(n: int) -> tuple:
    """The (year, month, day) a day count means."""
    got = datetime.date.fromordinal(int(n))
    return got.year, got.month, got.day


def _days_in_month(y: int, mo: int) -> int:
    first = datetime.date(y, mo, 1)
    nxt = datetime.date(y + 1, 1, 1) if mo == 12 else datetime.date(y, mo + 1, 1)
    return (nxt - first).days


def _today_ord(at: float) -> int:
    lt = time.localtime(at)
    return _day_ord(lt.tm_year, lt.tm_mon, lt.tm_mday)


def _at_times(y: int, mo: int, d: int, times: list, after: float) -> Optional[float]:
    """The first of `times` on this date that is strictly after `after`."""
    for hh, mm in times:
        t = wall_to_epoch(y, mo, d, hh, mm)
        if t > after:
            return t
    return None


def _next_daily(times: list, after: float, days: Optional[set] = None) -> float:
    """The first of `times` after `after`, on one of `days` (0 = Monday;
    None: any day). Two days is always far enough back for a time still to
    come today."""
    lt = time.localtime(after)
    y, mo, d = lt.tm_year, lt.tm_mon, lt.tm_mday
    for n in range(0, 9):
        yy, mmo, dd = _add_days(y, mo, d, n) if n else (y, mo, d)
        if days is not None and _weekday(yy, mmo, dd) not in days:
            continue
        t = _at_times(yy, mmo, dd, times, after)
        if t is not None:
            return t
    raise ValueError("no such time in the next week")


def _next_n_days(times: list, after: float, start_ord: int, step: int) -> float:
    """Every `step` days from the anchor day, the first one after `after`."""
    today = _today_ord(after)
    k = 0 if today <= start_ord else (today - start_ord) // step
    for _ in range(0, 400):
        y, mo, d = _ord_date(start_ord + k * step)
        t = _at_times(y, mo, d, times, after)
        if t is not None:
            return t
        k += 1
    raise ValueError("no such day")


def _next_n_weeks(times: list, after: float, monday_ord: int, step: int,
                  weekdays: set) -> float:
    """Every `step` weeks from the anchor week (which starts on `monday_ord`),
    on one of `weekdays` (0 = Monday), the first one after `after`."""
    today = _today_ord(after)
    span = 7 * step
    k = 0 if today <= monday_ord else (today - monday_ord) // span
    for _ in range(0, 400):
        week = monday_ord + k * span
        for wd in sorted(weekdays):
            y, mo, d = _ord_date(week + wd)
            t = _at_times(y, mo, d, times, after)
            if t is not None:
                return t
        k += 1
    raise ValueError("no such day")


def _next_monthly(times: list, after: float, day_of_month: int) -> float:
    """Every month on `day_of_month` (clamped to the month's last day, so the
    31st is the 28th in February), the first one after `after`."""
    lt = time.localtime(after)
    y, mo = lt.tm_year, lt.tm_mon
    for _ in range(0, 12 * MAX_RULE_YEARS):
        d = min(day_of_month, _days_in_month(y, mo))
        t = _at_times(y, mo, d, times, after)
        if t is not None:
            return t
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    raise ValueError("no such day")


def next_run(rule: dict, after: float) -> float:
    """The first time the rule goes off strictly after `after`. A window
    goes off at both ends: whichever comes first."""
    if rule.get("until"):
        hh, mm = _hhmm(rule["at"])
        uh, um = _hhmm(rule["until"])
        return min(next_at(hh, mm, after), next_at(uh, um, after))
    every = rule["every"]
    if every == "minutes":
        # Only a kind with its own check() may have this ("tell me when",
        # jarvis_tellme.py): check_rule() refuses it, so every other repeat
        # keeps the hourly floor.
        step = rule["minutes"] * 60.0
        start = float(rule["start"])
        if after < start:
            return start
        k = int((after - start) // step) + 1
        return start + k * step
    if every == "hours":
        step = rule["hours"] * 3600.0
        start = float(rule["start"])
        if after < start:
            return start
        k = int((after - start) // step) + 1
        return start + k * step
    times = _rule_times(rule)
    if every == "days":
        return _next_n_days(times, after, _today_ord(float(rule["start"])),
                            int(rule["days"]))
    if every == "weeks":
        start = float(rule["start"])
        lt = time.localtime(start)
        monday = _day_ord(lt.tm_year, lt.tm_mon, lt.tm_mday) - _weekday(
            lt.tm_year, lt.tm_mon, lt.tm_mday)
        return _next_n_weeks(times, after, monday, int(rule["weeks"]), set(rule["days"]))
    if every == "month":
        return _next_monthly(times, after, int(rule["day"]))
    days = None
    if every == "weekday":
        days = {0, 1, 2, 3, 4}
    elif every == "week":
        days = set(rule["days"])
    return _next_daily(times, after, days)


def next_runs(rule: dict, after: float, n: int = NEXT_SHOWN) -> list:
    out, t = [], after
    for _ in range(n):
        t = next_run(rule, t)
        out.append(t)
    return out


def last_at(hh: int, mm: int, at_or_before: float) -> float:
    """The last time the clock read hh:mm at or before `at_or_before`.
    Two days back is always far enough: every day has an hh:mm (a time the
    clocks skip counts as the moment they jump - next_at)."""
    t = next_at(hh, mm, at_or_before - 2 * 86400 - 7200)
    prev = t
    while t <= at_or_before:
        prev = t
        t = next_at(hh, mm, t)
    return prev


def in_window(rule: dict, now: float) -> bool:
    """Is `now` inside a window rule - after its latest start, before the
    end that follows it? False for a rule that is not a window.

    Worked out from the clock, not from which end last went off, so two
    ends found overdue together (the PC was off all night: 01:00 and 07:00
    both missed) come to the same answer - awake - whichever runs first."""
    if not rule or not rule.get("until"):
        return False
    hh, mm = _hhmm(rule["at"])
    uh, um = _hhmm(rule["until"])
    return last_at(hh, mm, now) > last_at(uh, um, now)


def next_windows(rule: dict, after: float, n: int = NEXT_SHOWN) -> list:
    """The next `n` windows that START after `after`: [(start, end), ...]."""
    hh, mm = _hhmm(rule["at"])
    uh, um = _hhmm(rule["until"])
    out, t = [], after
    for _ in range(n):
        start = next_at(hh, mm, t)
        out.append((start, next_at(uh, um, start)))
        t = start
    return out


# --------------------------------------------------------------------------
#   Plain words
# --------------------------------------------------------------------------

def clock(t: float) -> str:
    """07:30 - the PC's local time, 24-hour, the same in both apps."""
    lt = time.localtime(t)
    return f"{lt.tm_hour:02d}:{lt.tm_min:02d}"


def day_words(t: float, now: float) -> str:
    """'today', 'tomorrow', 'Friday', or 'Friday 2 October'."""
    a, b = time.localtime(now), time.localtime(t)
    da = (a.tm_year, a.tm_mon, a.tm_mday)
    db = (b.tm_year, b.tm_mon, b.tm_mday)
    if da == db:
        return "today"
    if _add_days(*da, 1) == db:
        return "tomorrow"
    if t - now < 6 * 86400 and t > now:
        return WEEKDAYS[b.tm_wday]
    return f"{WEEKDAYS[b.tm_wday]} {b.tm_mday} {MONTHS[b.tm_mon - 1]}"


def when_words(t: float, now: float) -> str:
    """'07:00 today', '07:00 tomorrow', '09:00 on Friday 2 October'."""
    d = day_words(t, now)
    if d in ("today", "tomorrow"):
        return f"{clock(t)} {d}"
    return f"{clock(t)} on {d}"


def long_date(t: float) -> str:
    """'Monday 28 September at 07:00' - for the card, where every run is
    named in full."""
    lt = time.localtime(t)
    return f"{WEEKDAYS[lt.tm_wday]} {lt.tm_mday} {MONTHS[lt.tm_mon - 1]} at {clock(t)}"


def until_words(t: float) -> str:
    """'until Sunday 27 December' - a job with no time of its own (Kind.ends)
    that quietly ends that day."""
    lt = time.localtime(t)
    return f"until {WEEKDAYS[lt.tm_wday]} {lt.tm_mday} {MONTHS[lt.tm_mon - 1]}"


def window_words(start: float, end: float) -> str:
    """'Saturday 26 September, 01:00 to 07:00', or across midnight 'Friday
    25 September at 23:00 to Saturday at 07:00' - for the card."""
    a, b = time.localtime(start), time.localtime(end)
    day = f"{WEEKDAYS[a.tm_wday]} {a.tm_mday} {MONTHS[a.tm_mon - 1]}"
    if (a.tm_year, a.tm_mon, a.tm_mday) == (b.tm_year, b.tm_mon, b.tm_mday):
        return f"{day}, {clock(start)} to {clock(end)}"
    return f"{day} at {clock(start)} to {WEEKDAYS[b.tm_wday]} at {clock(end)}"


def length_words(seconds: float) -> str:
    """'10 minutes', '1 hour 30 minutes', '45 seconds'."""
    s = int(round(max(0.0, float(seconds))))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} hour" + ("s" if h != 1 else ""))
    if m:
        parts.append(f"{m} minute" + ("s" if m != 1 else ""))
    if sec and not h:
        parts.append(f"{sec} second" + ("s" if sec != 1 else ""))
    return " ".join(parts) if parts else "0 seconds"


def _times_words(rule: Optional[dict]) -> str:
    """"at 08:00" or "at 08:00, 13:00 and 20:00" - the times a rule goes off."""
    times = _rule_times(rule or {})
    said = [f"{hh:02d}:{mm:02d}" for hh, mm in times]
    if len(said) <= 1:
        return f"at {said[0]}" if said else ""
    return "at " + ", ".join(said[:-1]) + " and " + said[-1]


def _day_month(t: float) -> str:
    """"Monday 2 November" - a date without the year, for a rule's anchor."""
    lt = time.localtime(t)
    return f"{WEEKDAYS[lt.tm_wday]} {lt.tm_mday} {MONTHS[lt.tm_mon - 1]}"


_ORDINAL_TAILS = {1: "st", 2: "nd", 3: "rd"}


def _ordinal_words(n: int) -> str:
    """1st, 2nd, 3rd, 4th ... 21st, 22nd, 31st."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{_ORDINAL_TAILS.get(n % 10, 'th')}"


def rule_words(rule: Optional[dict]) -> str:
    """The rule as ONE readable sentence's worth of words, never a code. An
    optional end date is said last, so the whole stays sayable in one breath
    ("every 2 weeks on Monday and Thursday at 09:00, until Sunday 27 December")."""
    if not rule:
        return ""
    every = rule.get("every")
    ends = rule.get("ends")
    if rule.get("until"):
        said = f"every day from {rule['at']} to {rule['until']}"
    elif every == "day":
        said = f"every day {_times_words(rule)}"
    elif every == "weekday":
        said = f"every weekday (Monday to Friday) {_times_words(rule)}"
    elif every == "week":
        names = [WEEKDAYS[i] for i in rule.get("days", [])]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        said = f"every {joined} {_times_words(rule)}"
    elif every == "days":
        n = rule.get("days")
        said = (f"every day {_times_words(rule)}" if n == 1
                else f"every {n} days {_times_words(rule)}")
    elif every == "weeks":
        n = rule.get("weeks")
        names = [WEEKDAYS[i] for i in rule.get("days", [])]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        said = (f"every week on {joined} {_times_words(rule)}" if n == 1
                else f"every {n} weeks on {joined} {_times_words(rule)}")
    elif every == "month":
        d = rule.get("day")
        said = (f"every month on the {_ordinal_words(int(d))} {_times_words(rule)}"
                if isinstance(d, int) else f"every month {_times_words(rule)}")
    elif every == "hours":
        n = rule.get("hours")
        said = "every hour" if n == 1 else f"every {n} hours"
    elif every == "minutes":
        n = rule.get("minutes")
        # Whole days and hours said as such (2026-09-28: a "tell me when" on
        # a search looks once a day - "every 1440 minutes" is no way to say it).
        if isinstance(n, int) and not isinstance(n, bool) and n >= 60:
            if n % 1440 == 0:
                return "every day" if n == 1440 else f"every {n // 1440} days"
            if n % 60 == 0:
                return "every hour" if n == 60 else f"every {n // 60} hours"
        return "every minute" if n == 1 else f"every {n} minutes"
    else:
        return ""
    if every in ("days", "weeks") and isinstance(rule.get("start"), (int, float)):
        # The owner's "first occurrence": without it "every 3 days" has no
        # visible anchor, and two rules that read the same would start on
        # different days.
        said += f", starting {_day_month(float(rule['start']))}"
    if ends is not None:
        said += f", until {_day_month(float(ends))}"
    return said


def next_words(rule: Optional[dict], after: float, n: int = NEXT_SHOWN) -> str:
    """A repeating rule's next times in words, where the card used to list
    them (2026-09-26: plain repeats have no card): "07:00 tomorrow, 07:00 on
    Tuesday and 07:00 on Wednesday"; for a window, the next one in full,
    "Saturday 26 September, 01:00 to 07:00". "" when it cannot be worked out."""
    if not rule:
        return ""
    try:
        if rule.get("until"):
            a, b = next_windows(rule, after, 1)[0]
            return window_words(a, b)
        said = [when_words(t, after) for t in next_runs(rule, after, n)]
    except Exception:
        return ""
    if len(said) <= 1:
        return "".join(said)
    return ", ".join(said[:-1]) + " and " + said[-1]


#: What the answer says when a plain repeat is set up (no card): the apps'
#: route and the fast path (jarvis_quick.py) both use it.
REPEAT_SET = "{noun} set up, {rule}. Next: {next}. Delete it under Coming up to stop it."


def repeat_set_words(job: dict, now: float) -> str:
    """"Reminder set up, every weekday (Monday to Friday) at 07:00. Next:
    07:00 on Monday, 07:00 on Tuesday and 07:00 on Wednesday. Delete it
    under Coming up to stop it." - for a job add_repeat set up at once."""
    k = KINDS.get(str(job.get("kind") or ""))
    noun = (k.noun if k is not None else "repeat")
    rule = job.get("rule") if isinstance(job.get("rule"), dict) else None
    nxt = next_words(rule, now) or "see Coming up"
    return REPEAT_SET.format(noun=noun[:1].upper() + noun[1:], rule=rule_words(rule) or "repeating",
                             next=nxt)


def _digest(text: str) -> str:
    norm = " ".join(str(text or "").lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
#   A to-do item's own day, and the two ways of showing it (2026-11-02)
# --------------------------------------------------------------------------
# THE OWNER'S CHOICE (2026-11-02 ~00:41 PT, after measuring the gap: yesterday's
# unfinished items DID appear tomorrow but nothing said they were yesterday's).
# He asked for BOTH, with full daily rollover as the DEFAULT:
#
#   * every to-do item keeps the day it was written, for good. It is
#     `created_date`, a calendar day in THIS PC's local time, written once when
#     the row is created and never rewritten. There is deliberately no code
#     path that moves it: a rollover that stamped everything with today would
#     erase the age it is supposed to show (Gemini's ruling 8, 2026-11-02);
#   * ROLLOVER (the default): today's list is every open item written today or
#     earlier, and each older one carries a tag saying how old it is:
#         1 day      "from yesterday"
#         2-6 days   "from <Weekday> (<N>d ago)"     e.g. "from Friday (3d ago)"
#         7+ days    "from <MMM D>"                  e.g. "from Oct 26"
#     A 3-day-old item therefore never says "from yesterday" - the wording is
#     measured from `created_date`, never from "is it still on the list";
#   * DAY BY DAY: each item stays on its own day instead, grouped under that
#     day's own heading. NOTHING is moved, copied or deleted by the switch - the
#     rows and their `created_date` are identical in both modes, which is what
#     makes toggling 100% lossless. The mode is ONE value in this file
#     (`meta['todo_mode']`), changed from either app's Settings, or by asking
#     Jarvis in chat (`jarvis_settings_registry.py`'s `todo_carryover` setting
#     is the one door, so a tap and a sentence cannot disagree).
#
# The tag words are built HERE, on the PC, and handed to both apps - the same
# rule `age_s` follows. A phone whose clock is a day behind must never decide
# for itself that yesterday's item is today's.
TODO_MODE_ROLLOVER = "rollover"
TODO_MODE_DAY = "day"
TODO_MODE_DEFAULT = TODO_MODE_ROLLOVER
TODO_MODES = (TODO_MODE_ROLLOVER, TODO_MODE_DAY)

#: The two modes in the owner's words, for the Settings switch on both apps and
#: for the answer a spoken sentence gets. Handed out by `status()`.
TODO_MODE_WORDS = (
    {"value": TODO_MODE_ROLLOVER, "label": "Daily rollover",
     "detail": "Today's list is everything still open, and each older item says how "
               "old it is: from yesterday, from Friday (3d ago), from Oct 26."},
    {"value": TODO_MODE_DAY, "label": "Day by day",
     "detail": "Each day keeps its own list. An item stays on the day it was written, "
               "and yesterday's unfinished ones are not moved to today."},
)


def _day_of(ts) -> str:
    """The local calendar day a moment falls on, YYYY-MM-DD ("" for junk)."""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(float(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _day_date(day) -> Optional[datetime.date]:
    """A stored YYYY-MM-DD as a date, or None when it is not one."""
    try:
        parts = [int(x) for x in str(day or "").split("-")]
        if len(parts) != 3:
            return None
        return datetime.date(parts[0], parts[1], parts[2])
    except (TypeError, ValueError):
        return None


def _day_gap(day, today) -> int:
    """How many days `day` is BEFORE `today` (0 today, 1 yesterday, -1 future).
    0 when either is not a real day, which reads as "today" everywhere below -
    a damaged value never becomes a claim about how old an item is."""
    a, b = _day_date(day), _day_date(today)
    if a is None or b is None:
        return 0
    return (b - a).days


def _weekday_name(day) -> str:
    d = _day_date(day)
    return d.strftime("%A") if d is not None else ""


def _short_day(day) -> str:
    d = _day_date(day)
    return f"{d.strftime('%b')} {d.day}" if d is not None else ""


def carry_words(created_date, now: float) -> str:
    """"from yesterday" / "from Friday (3d ago)" / "from Oct 26", or "" for an
    item written today (or one with no usable day). ONE function, so the two
    apps and the spoken read-out can never say it differently."""
    today = _day_of(now)
    n = _day_gap(created_date, today)
    if n <= 0:
        return ""
    if n == 1:
        return "from yesterday"
    if n < 7:
        return f"from {_weekday_name(created_date)} ({n}d ago)"
    return f"from {_short_day(created_date)}"


def day_label(created_date, now: float) -> str:
    """The heading a day-labelled list puts above one day's items: "Today",
    "Yesterday", "Friday (3d ago)", "Oct 26"."""
    today = _day_of(now)
    n = _day_gap(created_date, today)
    if n <= 0:
        return "Today"
    if n == 1:
        return "Yesterday"
    if n < 7:
        return f"{_weekday_name(created_date)} ({n}d ago)"
    return _short_day(created_date)


def _todo_days(items: list, now: float) -> list:
    """A day-labelled view of the same items: [{date, label, count, items}],
    today's day first, then each earlier one. `items` are the ids of the rows
    in the flat `todo` list, so a client never receives one twice."""
    groups: dict = {}
    for j in items:
        day = str(j.get("created_date") or _day_of(now))
        groups.setdefault(day, []).append(str(j.get("id")))
    out = []
    for day in sorted(groups, reverse=True):
        out.append({"date": day, "label": day_label(day, now),
                    "count": len(groups[day]), "items": groups[day]})
    return out


# --------------------------------------------------------------------------
#   Named lists
# --------------------------------------------------------------------------

_LIST_WORD = re.compile(r"[a-z][a-z'-]*")
_NOT_A_LIST = frozenset("my the a an our to for of and or on in it this that these those all "
                        "every any list lists todo todos timer timers alarm alarms reminder "
                        "reminders".split())
_THE_TODO_LIST = ("", "todo", "to-do", "to do", "todos", "to-dos", "to dos")


def list_key(name) -> Optional[str]:
    """A list's name as it is kept: lower case, with "list" taken off
    ("Shopping list" -> "shopping"). None for the to-do list itself (no
    name, "to-do", "todo"). ValueError, with a sentence, for a name that
    cannot be one: one to three plain words."""
    if name is None:
        return None
    t = " ".join(str(name).lower().replace("\u2019", "'").split())
    t = re.sub(r"\s*\blist$", "", t).strip()
    if t in _THE_TODO_LIST:
        return None
    words = t.split()
    if (len(t) > MAX_LIST_NAME or not 1 <= len(words) <= 3
            or not all(_LIST_WORD.fullmatch(w) for w in words)
            or any(w in _NOT_A_LIST for w in words)):
        raise ValueError("a list's name is one to three plain words, like \"shopping\"")
    return t


def list_title(key: Optional[str]) -> str:
    """"Shopping list", or "To-do list" for the to-do list - both apps' words."""
    if not key:
        return DEFAULT_LIST_TITLE
    return key[0].upper() + key[1:] + " list"


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


# --------------------------------------------------------------------------
#   The gate (repeating jobs only)
# --------------------------------------------------------------------------

def _default_gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _default_tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-schedule-card", daemon=True).start()


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _audit(event: str, detail: dict) -> None:
    # Ids, kinds and outcomes. Never a job's words.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


CARD_REFUSED_WORDS = ("Your PC's settings do not let this repeat be approved, "
                      "so it was not set up.")
LAST_WORDS = {
    "approved": "You approved the card, so it is set up.",
    "denied": "The card was turned down, so nothing was set up.",
    "timed_out": "Nobody answered the card in time, so nothing was set up.",
    "refused": CARD_REFUSED_WORDS,
    "withdrawn": "It was deleted while the card waited, so nothing was set up.",
    # PA-6: the repeat card is bound to the rule and words it was raised for.
    # If either changed while the card waited, the card would overwrite a newer
    # edit - so it refuses, says so, and the owner can ask again.
    "stale": ("That reminder changed while the card waited, so nothing was "
              "overwritten. Ask me again to change it."),
}


# --------------------------------------------------------------------------
#   The scheduler
# --------------------------------------------------------------------------

class Scheduler:
    """One loop, one database. `clock`, `gate`, `tier_of`, `spawn` and
    `publish` are replaceable so the tests run without waiting, without a
    gate and without a bus."""

    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time,
                 gate: Callable = _default_gate, tier_of: Callable[[str], str] = _default_tier,
                 spawn: Callable[[Callable[[], None]], None] = _spawn,
                 publish: Callable[[str, dict], None] = _publish):
        self.path = Path(path) if path else db_path()
        self.now = clock
        self._gate = gate
        self._tier_of = tier_of
        self._spawn = spawn
        self._publish = publish
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_card: dict = {}      # job id -> outcome, for the list
        # (job id, due) pairs a fire-time action has already asked about, so a
        # retry inside this process can never ask or run twice. In memory only:
        # a restart cannot re-fire anyway - the row is no longer 'active'.
        self._acted: set = set()
        self.errors = 0
        self.fired = 0
        # The clock reading at the last tick, in memory only: a reading EARLIER
        # than it means the PC's clock was set back (a time sync, a manual
        # change), and running timers are moved back with it (see `tick`).
        self._last_tick_now: Optional[float] = None
        # "Cancel that" (jarvis_quick.py): conversation id -> what the fast
        # path last set there. In memory only - a restart forgets it.
        self._recent: dict = {}
        with self._db() as c:
            c.executescript(_SCHEMA)
            have = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
            missing = [(name, typ) for name, typ in _ADDED_COLUMNS if name not in have]
            # Phase 2 (2026-10-22): the ALTERs and the one-time rank backfill
            # run in ONE explicit transaction, so a crash can leave neither half
            # behind - probe-proven on this PC that SQLite rolls the added
            # column back with the rows. Missing columns are what an older
            # schedule.db needs; a rank NULL left by an older build (or by a
            # to-do written before this code) is topped up on the next open.
            needs_backfill = False
            if "rank" in have and not missing:
                needs_backfill = c.execute(
                    "SELECT 1 FROM jobs WHERE kind = 'todo' AND state IN ('active','paused') "
                    "AND rank IS NULL LIMIT 1").fetchone() is not None
            # The to-do day carry-over (2026-11-02): a row written before
            # `created_date` existed has none, and is stamped from its own
            # `created` on this first open. A row that already has one is never
            # touched - the column is immutable by design (see the day section
            # above), and re-stamping it here would be exactly the midnight
            # rewrite the owner ruled out.
            needs_days = False
            if "created_date" in have and not missing:
                needs_days = c.execute(
                    "SELECT 1 FROM jobs WHERE created_date IS NULL LIMIT 1").fetchone() is not None
            if missing or needs_backfill or needs_days:
                c.execute("BEGIN IMMEDIATE")
                for name, typ in missing:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")
                self._backfill_ranks(c)
                self._backfill_created_dates(c)

    def _backfill_ranks(self, c) -> None:
        """One-time rank backfill (HUD Reminders Phase 2, 2026-10-22).

        Every OPEN to-do that has no rank gets the next free number IN ITS OWN
        LIST, in (created, rowid) order - so the first run on an old DB gives
        each list exactly 0..n-1 deterministically, while a row that already
        has a rank keeps it (a new item appended by a later version sorts after
        the ranked ones). Done and fired rows are never ranked: they are not on
        a list. Idempotent by construction: with no NULL remaining it writes
        nothing. Runs inside the same explicit transaction as the ALTERs."""
        rows = c.execute(
            "SELECT id, list_name FROM jobs WHERE kind = 'todo' "
            "AND state IN ('active','paused') AND rank IS NULL "
            "ORDER BY (list_name IS NOT NULL), list_name, created, rowid").fetchall()
        if not rows:
            return
        nxt: dict = {}
        for key, top in c.execute(
                "SELECT ifnull(list_name, ''), COALESCE(MAX(rank), -1) FROM jobs "
                "WHERE kind = 'todo' AND state IN ('active','paused') "
                "AND rank IS NOT NULL GROUP BY ifnull(list_name, '')").fetchall():
            nxt[str(key)] = int(top) + 1
        for r in rows:
            key = str(r["list_name"] or "")
            value = nxt.get(key, 0)
            c.execute("UPDATE jobs SET rank = ? WHERE id = ?", (value, r["id"]))
            nxt[key] = value + 1

    def _backfill_created_dates(self, c) -> None:
        """One-time backfill of `created_date` (2026-11-02).

        Every row with no day of its own is stamped from its own `created`
        stamp, in local time; a legacy row whose stamp is missing or unusable is
        stamped TODAY, as the owner's brief says - there is no honest way to know
        when it was written, and today is the one answer that never claims an age
        the data cannot support.

        Idempotent by construction: it reads only rows where the column is NULL
        and writes only those (`AND created_date IS NULL` in the UPDATE too, so
        two writers cannot fight). Never runs on the hot path: after the first
        open there is nothing NULL left to stamp."""
        rows = c.execute("SELECT id, created FROM jobs WHERE created_date IS NULL").fetchall()
        if not rows:
            return
        today = _day_of(self.now())
        for r in rows:
            try:
                stamp = float(r["created"])
            except (TypeError, ValueError):
                stamp = 0.0
            # A zero (or negative) `created` is the legacy row the brief names:
            # there is no timestamp to read, and 1970 is not an honest age.
            day = (_day_of(stamp) if stamp > 0 else "") or today
            c.execute("UPDATE jobs SET created_date = ? WHERE id = ? AND created_date IS NULL",
                      (day, r["id"]))

    # ---- storage ------------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # jarvis_sqlite.connect, not sqlite3.connect: the connection is CLOSED
        # when its `with` block ends, not left to the collector - a leaked
        # handle is what made schedule.json undeletable on the Windows runner
        # (2026-10-07). It used to be a private _ClosingConnection here; now one
        # shared copy, so a fourth module cannot reinvent the bug.
        c = jarvis_sqlite.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def _row(self, c, job_id: str):
        return c.execute("SELECT * FROM jobs WHERE id = ?", (str(job_id),)).fetchone()

    def _count(self, c, *, todo: bool) -> int:
        if todo:
            q = "SELECT COUNT(*) FROM jobs WHERE kind = 'todo' AND state IN ('active','paused')"
        else:
            q = ("SELECT COUNT(*) FROM jobs WHERE kind != 'todo' "
                 "AND state IN ('active','paused','waiting')")
        return int(c.execute(q).fetchone()[0])

    def _insert(self, kind: str, *, text: str, state: str, due, rule, duration,
                source: str, list_name: Optional[str] = None,
                snooze_of: Optional[str] = None, extra: Optional[dict] = None,
                context_bundle: Optional[dict] = None, trigger: Optional[str] = None,
                condition_kind: Optional[str] = None,
                condition_target: Optional[str] = None,
                rank: Optional[int] = None,
                source_taint: Optional[str] = None,
                action: Optional[dict] = None) -> str:
        """The ONE insert. Every creation path (timer, alarm, reminder, to-do,
        repeat, both snooze copies) comes through here, so the creation-time
        taint mark is recorded in exactly one place.

        `source_taint`: an explicit mark to carry over (a snooze copy of a
        tainted row). When it is None the row is marked iff the private latch
        is on at this moment."""
        jid = "s" + uuid.uuid4().hex[:10]
        now = self.now()
        taint = source_taint or _taint_mark()
        with self._lock, self._db() as c:
            if kind == "todo" and rank is None:
                # Phase 2: a new to-do appends to the end of its list, so the
                # column is never NULL for a row this code writes.
                top = c.execute(
                    "SELECT COALESCE(MAX(rank), -1) FROM jobs WHERE kind = 'todo' "
                    "AND state IN ('active','paused') AND ifnull(list_name, '') = ?",
                    (str(list_name or ""),)).fetchone()[0]
                rank = int(top) + 1
            c.execute("INSERT INTO jobs (id, kind, text, state, due, rule, duration, created, "
                      "changed, source, list_name, snooze_of, extra, context_bundle, trigger, "
                      "condition_kind, condition_target, rank, source_taint, action, created_date) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (jid, kind, text, state, due,
                       json.dumps(rule) if rule else None, duration, now, now, source,
                       list_name, snooze_of, json.dumps(extra) if extra else None,
                       json.dumps(context_bundle) if context_bundle else None,
                       trigger or "time", condition_kind, condition_target, rank, taint,
                       json.dumps(action) if action else None,
                       # The day this row was written, set ONCE here and never
                       # written again by any path (2026-11-02). An item's age is
                       # measured from it for as long as it stays open.
                       _day_of(now)))
        _audit("schedule.add", {"id": jid, "kind": kind, "repeats": bool(rule)})
        self._changed(jid, kind)
        return jid

    def _changed(self, jid: str, kind: str) -> None:
        self._publish("schedule", {"id": jid, "kind": kind, "state": "changed"})
        self.poke()

    # ---- checks shared by every way in ---------------------------------------

    @staticmethod
    def _clean_text(text, kind: str) -> str:
        t = " ".join(str(text or "").split())
        if len(t) > MAX_TEXT:
            raise ValueError(f"that is longer than {MAX_TEXT} characters - say it more briefly")
        if kind in ("reminder", "todo") and not t:
            raise ValueError("a reminder needs some words: what should Jarvis remind you of?")
        return t

    def _room(self, c, kind: str) -> None:
        if kind == "todo":
            if self._count(c, todo=True) >= MAX_TODO:
                raise OverflowError(f"the to-do list is full ({MAX_TODO} items) - mark some done")
        elif self._count(c, todo=False) >= MAX_JOBS:
            raise OverflowError(f"there are already {MAX_JOBS} timers and reminders - "
                                f"delete some first")

    # ---- adding ---------------------------------------------------------------

    def add_timer(self, seconds: float, label: str = "", source: str = "app") -> dict:
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            raise ValueError("a timer needs a length")
        if seconds != seconds or seconds < MIN_TIMER:
            raise ValueError("a timer needs a length of at least a second")
        if seconds > MAX_TIMER:
            raise ValueError("a timer can be up to 24 hours - for later than that, "
                             "set a reminder")
        label = self._clean_text(label, "timer")
        with self._lock, self._db() as c:
            self._room(c, "timer")
        jid = self._insert("timer", text=label, state="active", due=self.now() + seconds,
                           rule=None, duration=seconds, source=source)
        return self.job(jid)

    def add_at(self, kind: str, at: float, text: str = "", source: str = "app",
               extra: Optional[dict] = None, *, context_bundle: Optional[dict] = None,
               trigger: Optional[str] = None, condition_kind: Optional[str] = None,
               condition_target: Optional[str] = None,
               action: Optional[dict] = None) -> dict:
        """A one-off alarm, reminder or to-do with a time. No card. `extra`: a
        kind's own small state (the `extra` column), for a kind whose module
        keeps one (jarvis_next_time.py).

        GTD-1 (2026-10-18), REMINDERS ONLY: `context_bundle` is the scrubbed
        packet this reminder is about ("the details" a bare title loses),
        `trigger` is "time" (default), "on_pc_active" or "after_focus", and
        `condition_kind`/`condition_target` are the optional read-only check
        ("no_email_reply_from": who should have replied; "decks_due"). The
        bundle is normalised by `scrub_context_bundle` before it is stored -
        no raw path and no secret ever enters the database through here.

        REMINDERS ONLY, 2026-10-27: `action` is what this reminder opens, or
        the one task it may ask to run (see `_clean_action`). It is checked
        HERE, once, so a bad target is refused before a row exists; it is
        checked again at the moment it is used (`_action_problem`, and the
        desktop's own re-check before it opens anything)."""
        if kind not in KINDS or kind == "timer":
            raise ValueError("that kind of job needs a time: alarm, reminder or to-do")
        try:
            at = float(at)
        except (TypeError, ValueError):
            raise ValueError("a time is needed")
        now = self.now()
        if at <= now:
            raise ValueError("that time has already passed")
        if at - now > MAX_AHEAD:
            raise ValueError("that is more than a year away")
        text = self._clean_text(text, kind) if KINDS[kind].has_text else ""
        if kind != "reminder" and (context_bundle or trigger not in (None, "time")
                                   or condition_kind or condition_target):
            raise ValueError("only a reminder can carry context, a trigger or a condition")
        if kind != "reminder" and action:
            # The same one-line guard the context packet has: an action belongs
            # to a reminder, and a timer or a to-do that carried one would be a
            # target nothing can show, open or ask about.
            raise ValueError("only a reminder can carry an action")
        action = _clean_action(action)
        if trigger is not None and trigger not in TRIGGERS:
            raise ValueError("trigger is one of: " + ", ".join(TRIGGERS))
        with self._lock, self._db() as c:
            self._room(c, kind)
        jid = self._insert(kind, text=text, state="active", due=at, rule=None,
                           duration=None, source=source, extra=extra,
                           context_bundle=scrub_context_bundle(context_bundle)
                           if context_bundle else None,
                           trigger=trigger or "time",
                           condition_kind=str(condition_kind) if condition_kind else None,
                           condition_target=_clean_condition_target(condition_target)
                           if condition_target else None,
                           action=action)
        return self.job(jid)

    # ---- a kind's own small state (the `extra` column) --------------------------

    def extra(self, jid: str) -> dict:
        """ONE job's own state, {} for none (or a damaged value)."""
        with self._lock, self._db() as c:
            row = c.execute("SELECT extra FROM jobs WHERE id = ?", (str(jid),)).fetchone()
        try:
            got = json.loads(row["extra"]) if row is not None and row["extra"] else {}
        except Exception:
            return {}
        return got if isinstance(got, dict) else {}

    def set_extra(self, jid: str, extra: dict) -> bool:
        """Replace ONE listed job's own state. False when it is not on the
        list any more (deleted meanwhile). Rings no doorbell: nothing the
        list shows about a job's words changed."""
        with self._lock, self._db() as c:
            cur = c.execute("UPDATE jobs SET extra = ?, changed = ? WHERE id = ? AND state IN "
                            "('active','paused','waiting')",
                            (json.dumps(extra or {}), self.now(), str(jid)))
            return cur.rowcount > 0

    # ---- the to-do list's one mode (2026-11-02) ----------------------------

    def todo_mode(self) -> str:
        """Which way the to-do list is shown, "rollover" (the default) or "day".

        ONE value in this file, kept in `meta`, so the Settings switch on either
        app, a spoken sentence and a fact test all read the same answer. An
        unknown or damaged value reads as the default rather than raising: a
        schedule.db edited by hand must not stop the to-do list from opening."""
        with self._lock, self._db() as c:
            row = c.execute("SELECT value FROM meta WHERE key = ?", ("todo_mode",)).fetchone()
        mode = str(row["value"]) if row is not None else ""
        return mode if mode in TODO_MODES else TODO_MODE_DEFAULT

    def set_todo_mode(self, mode) -> str:
        """Change the mode and return the one now in force. ValueError, with the
        owner's own wording, for anything that is not one of the two.

        It moves NO item and rewrites NO `created_date`: the very same rows are
        handed out in the other shape, which is what makes the switch lossless
        in both directions."""
        want = " ".join(str(mode or "").split()).lower()
        if want not in TODO_MODES:
            raise ValueError("the to-do list is either \"rollover\" (today's list carries "
                             "yesterday's open items) or \"day\" (each day keeps its own)")
        with self._lock, self._db() as c:
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                      ("todo_mode", want))
        _audit("schedule.todo_mode", {"mode": want})
        return want

    def todo_days(self) -> list:
        """The open to-do items grouped by the day they were written, for the
        day-labelled mode: [{date, label, count, items}], today first. Each
        entry's `items` are ids into the same flat `todos()` list."""
        now = self.now()
        return _todo_days(self.todos(), now)

    def listed_of(self, kind: str) -> list:
        """The ACTIVE jobs of one kind, oldest first, as raw fields - {"id",
        "text", "created", "due", "extra"} - for that kind's own module."""
        with self._lock, self._db() as c:
            rows = c.execute("SELECT id, text, created, due, extra FROM jobs WHERE kind = ? "
                             "AND state = 'active' ORDER BY created, rowid",
                             (str(kind),)).fetchall()
        out = []
        for r in rows:
            try:
                extra = json.loads(r["extra"]) if r["extra"] else {}
            except Exception:
                extra = {}
            out.append({"id": r["id"], "text": r["text"], "created": r["created"],
                        "due": r["due"], "extra": extra if isinstance(extra, dict) else {}})
        return out

    def add_todo(self, text: str, source: str = "app", list_name=None) -> dict:
        """One to-do item - on the to-do list, or on a named list ("shopping").
        The same words twice on one list are one item."""
        key = list_key(list_name)
        text = self._clean_text(text, "todo")
        with self._lock, self._db() as c:
            self._room(c, "todo")
            dup = c.execute("SELECT id FROM jobs WHERE kind = 'todo' AND state = 'active' "
                            "AND lower(text) = lower(?) AND ifnull(list_name, '') = ?",
                            (text, key or "")).fetchone()
            if dup is None and key is not None:
                names = {r[0] for r in c.execute(
                    "SELECT DISTINCT list_name FROM jobs WHERE kind = 'todo' AND state IN "
                    "('active','paused') AND list_name IS NOT NULL").fetchall()}
                if key not in names and len(names) >= MAX_LISTS:
                    raise OverflowError(f"there are already {MAX_LISTS} lists - finish one first")
        if dup is not None:
            return dict(self.job(dup["id"]), already=True)
        jid = self._insert("todo", text=text, state="active", due=None, rule=None,
                           duration=None, source=source, list_name=key)
        return self.job(jid)

    def add_repeat(self, kind: str, rule, text: str = "", source: str = "app",
                   action: Optional[dict] = None) -> dict:
        """A repeating job. A plain alarm, reminder or standby schedule
        (Kind.plain_repeat) is set up at once, with no card; any other kind
        WAITS until one approval card is approved.

        `action` (2026-10-27): a repeating REMINDER may carry one action, and
        then it goes off - and acts, or offers its Open button - EVERY time.
        A repeating action reminder asks again at every occurrence, never once
        and then silent: "never auto-approved" means every time is a decision."""
        k = KINDS.get(kind)
        window = bool(k is not None and k.window)
        if not _repeatable(kind) and not window:
            raise ValueError("only alarms, reminders and briefings can repeat")
        now = self.now()
        if k is not None and k.check is not None:
            rule = k.check(rule, now)
        else:
            rule = check_rule(rule, now, window=window)
        text = self._clean_text(text, kind) if (k is None or k.has_text) else ""
        if kind != "reminder" and action:
            raise ValueError("only a reminder can carry an action")
        action = _clean_action(action)
        with self._lock, self._db() as c:
            self._room(c, kind)
            if k.single and c.execute(
                    "SELECT 1 FROM jobs WHERE kind = ? AND state IN ('active','paused','waiting')",
                    (kind,)).fetchone() is not None:
                raise OverflowError(f"there is already a {k.noun} - delete it first to set "
                                    f"a different one")
            if not k.has_text and not window and rule["every"] != "hours":
                # A kind with no words of its own (a briefing): the same
                # repeat twice would only go off twice, so it is refused.
                for r in c.execute("SELECT rule FROM jobs WHERE kind = ? AND rule IS NOT NULL "
                                   "AND state IN ('active','paused','waiting')",
                                   (kind,)).fetchall():
                    try:
                        same = check_rule(json.loads(r["rule"]), now) == rule
                    except Exception:
                        same = False
                    if same:
                        raise ValueError(f"a {k.noun} {rule_words(rule)} is already set up")
        if k.plain_repeat:
            # No card (Kind.plain_repeat): on the list at once, due at its
            # first time. The next times are in the answer (repeat_set_words)
            # and under the job in Coming up, where the card used to list them.
            due = now if k.first_now else next_run(rule, now)
            jid = self._insert(kind, text=text, state="active", due=due, rule=rule,
                               duration=None, source=source, action=action)
            return self.job(jid)
        jid = self._insert(kind, text=text, state="waiting", due=None, rule=rule,
                           duration=None, source=source, action=action)
        # Read BEFORE the card is raised: a card answered at once (or a
        # refusal) removes the row, and the caller still needs to say what
        # was asked for.
        view = self.job(jid)
        self._spawn(lambda: self._ask(jid))
        return view

    # ---- the card ---------------------------------------------------------------

    def card_text(self, kind: str, rule: dict, text: str, now: float) -> str:
        k = KINDS[kind]
        if k.card is not None:
            return k.card(rule, text, now)
        if rule.get("until"):
            return self._window_card(k, rule, now)
        runs = next_runs(rule, now)
        what = k.noun
        lines = [f"Set up a repeating {what}.", ""]
        if text:
            lines.append(f"What: {text}")
        lines.append(f"When: {rule_words(rule)}.")
        lines.append("")
        lines.append("The next three times it will go off:")
        lines.extend(f"  - {long_date(t)}" for t in runs)
        note = KINDS[kind].card_note
        if note:
            lines.append("")
            lines.extend(note)
        else:
            lines.extend([
                "",
                "It runs on this PC, by this PC's clock. It goes off on both apps while "
                "they are connected. Nothing is sent anywhere.",
            ])
        lines.extend([
            "Stopping or deleting it is immediate, from either app.",
            "",
            "If you say no: nothing is set up.",
        ])
        return "\n".join(lines)

    @staticmethod
    def _window_card(k: Kind, rule: dict, now: float) -> str:
        """The card for a window kind (the standby schedule): what, when,
        what it does at each end (the kind's own `about`), and the next
        three windows in full."""
        lines = [f"Set up a {k.noun}.", "", f"When: {rule_words(rule)}.", ""]
        if k.about:
            lines.extend(k.about)
            lines.append("")
        lines.append("The next three times:")
        lines.extend(f"  - {window_words(a, b)}" for a, b in next_windows(rule, now))
        lines.extend([
            "",
            "It runs on this PC, by this PC's clock. Nothing is sent anywhere.",
            "Stopping or deleting it is immediate, from either app.",
            "",
            "If you say no: nothing is set up.",
        ])
        return "\n".join(lines)

    def _edit_card_text(self, kind: str, rule: dict, text: str, now: float) -> str:
        """The ONE card a repeat change raises (Phase 2), in the same shape as
        the "set up" card: what will change, the new rule, the next three
        times, and the honest line that the CURRENT schedule stays in force
        until the owner says yes. Never logged, and the audit line that goes
        with the request carries field names only."""
        k = KINDS[kind]
        runs = next_runs(rule, now)
        lines = [f"Change a repeating {k.noun}.", ""]
        if text:
            lines.extend([f"What: {text}", ""])
        lines.append(f"When: {rule_words(rule)}.")
        lines.extend(["", "The next three times it will go off:"])
        lines.extend(f"  - {long_date(t)}" for t in runs)
        lines.extend([
            "",
            "Until you say yes, the current schedule stays exactly as it is.",
            "",
            "If you say no: nothing changes.",
        ])
        return "\n".join(lines)

    def _ask(self, jid: str) -> None:
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        if row is None or row["state"] != "waiting":
            return
        rule = json.loads(row["rule"])
        text = self.card_text(row["kind"], rule, row["text"], self.now())

        def finish(outcome: str) -> None:
            self.last_card[jid] = outcome
            _audit("schedule.card", {"id": jid, "outcome": outcome})
            if outcome == "approved":
                return
            with self._lock, self._db() as c:
                c.execute("DELETE FROM jobs WHERE id = ? AND state = 'waiting'", (jid,))
            self._changed(jid, row["kind"])

        if self._tier_of(ACTION) != "ask":
            return finish("refused")
        try:
            k = KINDS[row["kind"]]
            v = self._gate(ACTION, {"text": text,
                                    "what": k.what or ("set up a repeating " + k.noun),
                                    "leaves_this_pc": bool(k.leaves), "job": jid}, text)
        except Exception:
            return finish("refused")
        vtier = getattr(v, "tier", "unknown")
        allowed = getattr(v, "allowed", False) is True
        outcome = getattr(v, "outcome", None)
        if outcome is None:
            outcome = "approved" if (allowed and vtier == "ask") else "refused"
        if vtier != "ask" or self._tier_of(ACTION) != "ask":
            # allowed on "auto" or "notify" is not a person saying yes (§3).
            return finish("refused")
        if not (allowed and outcome == "approved"):
            return finish(outcome if outcome in ("denied", "timed_out") else "refused")
        with self._lock, self._db() as c:
            cur = self._row(c, jid)
            if cur is None or cur["state"] != "waiting":
                # Deleted while the card waited: approving it sets up nothing.
                self.last_card[jid] = "withdrawn"
                return
            kk = KINDS.get(row["kind"])
            if kk is not None and kk.first_now:
                due = self.now()
            else:
                due = next_run(rule, self.now())
            c.execute("UPDATE jobs SET state = 'active', due = ?, changed = ? WHERE id = ?",
                      (due, self.now(), jid))
        finish("approved")
        self._changed(jid, row["kind"])

    def _ask_edit(self, jid: str, plan: dict) -> None:
        """The ONE `schedule_repeat` card a Phase 2 repeat change raises.

        The job itself is NOT touched before the answer: its old rule keeps
        running exactly as it did. Approved: the new rule (and the edit's own
        new words, when it had any) are applied in one transaction and the next
        run is recomputed from the new rule. Denied/timed-out/refused: nothing
        changes at all. The audit lines carry ids and outcomes only.

        PA-6: the card is bound to the rule and words it was raised for. If a
        newer edit changed either while the card waited, approving the older
        card would silently overwrite that newer edit, so the card is STALE:
        it applies nothing, says so, and the owner can ask again."""
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        if row is None or row["state"] not in ("active", "paused"):
            return
        kind, rule = row["kind"], plan["rule"]
        text = row["text"] if plan.get("text") is None else plan["text"]
        prompt = self._edit_card_text(kind, rule, text, self.now())

        def finish(outcome: str) -> None:
            if outcome == "approved":
                with self._lock, self._db() as c:
                    cur = self._row(c, jid)
                    if cur is None or cur["state"] not in ("active", "paused"):
                        # Deleted, fired or otherwise left the list while the
                        # card waited: applying it would overwrite something
                        # else, so it withdraws.
                        outcome = "withdrawn"
                    elif (cur["rule"] != plan.get("base_rule")
                          or cur["text"] != plan.get("base_text")):
                        # A newer edit (its own words or its repeat rule) landed
                        # while this card waited. Do not overwrite it.
                        outcome = "stale"
                    else:
                        now = self.now()
                        sets, args = ["rule = ?", "changed = ?"], [json.dumps(rule), now]
                        if plan.get("text") is not None:
                            sets.insert(0, "text = ?")
                            args.insert(0, plan["text"])
                        if cur["state"] == "active":
                            sets.append("due = ?")
                            args.append(next_run(rule, now))
                        # Edited while private material was in the turn: the
                        # row is marked too, not only the ones created then.
                        mark = _taint_mark()
                        if mark:
                            sets.append("source_taint = ?")
                            args.append(mark)
                        c.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?",
                                  (*args, jid))
            _audit("schedule.card", {"id": jid, "outcome": outcome})
            if outcome != "approved":
                self.last_card[jid] = outcome
                return
            self.last_card[jid] = "approved"
            self._changed(jid, kind)

        if self._tier_of(ACTION) != "ask":
            return finish("refused")
        try:
            k = KINDS[kind]
            verdict = self._gate(ACTION, {"text": prompt,
                                          "what": "change a repeating " + k.noun,
                                          "leaves_this_pc": bool(k.leaves), "job": jid},
                                 prompt)
        except Exception:
            return finish("refused")
        vtier = getattr(verdict, "tier", "unknown")
        allowed = getattr(verdict, "allowed", False) is True
        outcome = getattr(verdict, "outcome", None)
        if outcome is None:
            outcome = "approved" if (allowed and vtier == "ask") else "refused"
        if vtier != "ask" or self._tier_of(ACTION) != "ask":
            # allowed on "auto" or "notify" is not a person saying yes.
            return finish("refused")
        if not (allowed and outcome == "approved"):
            return finish(outcome if outcome in ("denied", "timed_out") else "refused")
        finish("approved")

    # ---- a reminder's action, at the moment it goes off (2026-10-27) ------------

    def _action_card_text(self, row, action: dict, now: float) -> str:
        """The ONE card's words, in the shape of the repeat card: what the
        reminder is, when it went off, and exactly what will happen.

        The reminder's own words are in HERE (the owner reads them on screen,
        and `decide()` NULLs the prompt the moment the card is answered); the
        TARGET never is, and neither the URL nor the path is in `detail` - see
        `_fire_action`. A repeating reminder also says it will ask again."""
        words = str(row["text"] or "").strip()
        due = row["fired_due"] if row["fired_due"] is not None else row["due"]
        when = clock(float(due)) if due is not None else "now"
        what = str(action.get("task") or "")
        lines = ["A reminder you set wants to do something.", ""]
        if words:
            lines.append(f"Reminder: {words}")
        lines.append(f"When: {when} today")
        lines.append(f"What it will do: {_task_words(what)}")
        lines.append("")
        if row["rule"]:
            lines.append("It repeats, so it will ask again next time.")
        lines.append("It happens once, only if you say yes. Nothing happens before that.")
        lines.append("If you say no, or nobody answers, nothing happens and the reminder "
                     "stays in your list as it was.")
        return "\n".join(lines)

    def _fire_action(self, jid: str, due: float) -> None:
        """ONE reminder's `run-task` action, raised as ONE card, on its own
        thread (so a fifteen-minute wait never blocks the tick loop).

        The shape is `_ask`'s, deliberately, and it refuses in the same order:
        the tier must be "ask" (a config line is never the owner's yes), the
        card must come back tier "ask" with outcome "approved", and anything
        else - denied, timed out, refused, a gate that raised - runs NOTHING.

        `detail` carries ids, the closed-list name, `due` and one boolean:
        NEVER the reminder's words, the URL, the path or the note. Two reasons
        that are facts about the gate: `_redact` returns `detail` VERBATIM when
        `[logging].redact_private_content_in_logs` is off (jarvis_gate.py's own
        `_redact`), so a target there would land in the audit log in the clear
        the day someone turns redaction off to debug something; and `detail` is
        handed to BOTH apps on `/api/pending`. The target that the owner needs
        is in `prompt`, which is the card's own text."""
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        if row is None:
            return
        action = _decode_action(_row_action(row))
        if not action or action["kind"] not in ACTING_ACTION_KINDS:
            return
        task = str(action.get("task") or "")
        pair = (jid, float(due))
        if pair in self._acted:
            # A retry inside this process cannot run or ask twice. A restart
            # cannot re-fire: the row is no longer 'active'.
            return
        self._acted.add(pair)
        if self._tier_of(ACTION_SCHEDULE) != "ask":
            # A config line is never the owner's yes.
            _audit("schedule.action_refused", {"id": jid, "outcome": "refused"})
            return
        if _task_problem(task):
            # Nothing can run for it (a task this build refuses). Never a card
            # for something that would do nothing.
            _audit("schedule.action_refused", {"id": jid, "outcome": "unknown"})
            return
        prompt = self._action_card_text(row, action, self.now())
        detail = {"job": jid, "due": float(due), "what": "run-task", "task": task,
                  "leaves_this_pc": False}
        _audit("schedule.action_asked", {"id": jid, "kind": action["kind"], "what": task})
        try:
            verdict = self._gate(ACTION_SCHEDULE, detail, prompt)
        except Exception:
            _audit("schedule.action_refused", {"id": jid, "outcome": "refused"})
            return
        vtier = getattr(verdict, "tier", "unknown")
        allowed = getattr(verdict, "allowed", False) is True
        outcome = getattr(verdict, "outcome", None)
        if outcome is None:
            outcome = "approved" if (allowed and vtier == "ask") else "refused"
        if vtier != "ask" or self._tier_of(ACTION_SCHEDULE) != "ask":
            # allowed on "auto" or "notify" is not a person saying yes.
            _audit("schedule.action_refused", {"id": jid, "outcome": "refused"})
            return
        if not (allowed and outcome == "approved"):
            _audit("schedule.action_refused",
                   {"id": jid, "outcome": outcome if outcome in ("denied", "timed_out")
                    else "refused"})
            return
        # PA-6: the card named this row as it was. If it was changed or
        # deleted while the card waited, the thing the owner approved is not
        # the thing that would run, so nothing runs.
        with self._lock, self._db() as c:
            cur = self._row(c, jid)
            if cur is None or _row_action(cur) != _row_action(row) \
                    or float(cur["changed"]) != float(row["changed"]):
                _audit("schedule.action_refused", {"id": jid, "outcome": "withdrawn"})
                return
        try:
            self._run_task(task, jid)
        except Exception as exc:
            # The exception's NAME only: its message could quote a path.
            _audit("schedule.action_failed",
                   {"id": jid, "what": task, "error": type(exc).__name__})
            return
        _audit("schedule.action_ran", {"id": jid, "what": task})

    def _run_task(self, task: str, jid: str) -> None:
        """Run ONE name from `ACTION_TASKS`, through the callable that already
        exists on this PC. Nothing else is reachable from here: no shell, no
        command, no path and no free text.

        `briefing` uses `jarvis_briefing.make` - NOT `build`, which the design
        named: `build` returns one briefing and keeps it nowhere, so a reminder
        that ran it would put a briefing together that neither app could ever
        show. `make` is the half that keeps it as the latest, and the "ready"
        ring is the same one `jarvis_briefing._on_fire` sends (that file's own
        scheduled-briefing path), carrying this reminder's id so both apps can
        read it and the briefing's own toast says it is ready."""
        if task == "briefing":
            import jarvis_briefing
            jarvis_briefing.make(sched=self, source="schedule", job=jid)
            self._publish("schedule", {"id": jid, "kind": "briefing", "state": "ready"})
            return
        raise ValueError("unknown task")

    # ---- answering an `ask` reminder (2026-11-02) ---------------------------
    #
    # ONE button of ONE question, pressed. An answer is a LOG LINE, not an
    # approval: it opens no card, decides nothing about anything else on this
    # PC, and is as reversible as a line in a notebook (which is what it is).
    # That is the design's own sentence - "answering is a log, cardless like
    # ticking a to-do" - and it is why nothing here touches the gate.
    #
    # Answering the same question twice is two answers ("Taken" and then
    # "Taken again"), because a question is not a card and does not close.

    def answers(self, jid: str) -> list:
        """ONE reminder's answers, oldest first; [] for none."""
        with self._lock, self._db() as c:
            row = c.execute("SELECT answers FROM jobs WHERE id = ?", (str(jid),)).fetchone()
        return _decode_answers(row["answers"] if row is not None else None)

    def answer(self, jid: str, index, *, source: str = "app") -> tuple:
        """Press ONE button of an `ask` reminder: (code, answer).

        `index` is the button's position in the stored block, 0-based - never
        its label, so a re-worded button cannot be answered by accident.
        Nothing is written unless the whole thing is valid and the reminder has
        actually gone off: the same order `_fire_action` refuses in.

        What is written, in order:
          1. the reminder's own history, when `record.history` is on - EVERY
             button logs there, because that is the log of the question;
          2. today's Obsidian note, a goal's progress and a habit tick - only
             from a `record` button, and each one that cannot be written is
             reported in ONE sentence while the rest still happens;
          3. what the button itself does: `done` (it stops), or `snooze`.
        """
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        if row is None:
            return 404, {"ok": False, "reason": "no_such_job", "error": ASK_GONE}
        action = _decode_action(_row_action(row))
        if not action or action.get("kind") != ASK_KIND:
            return 409, {"ok": False, "error": ASK_WRONG_KIND}
        fired = row["fired_at"]
        if (fired is None or row["state"] not in ("fired", "active", "paused")
                or now - float(fired) > FIRED_KEEP):
            # Not due yet, or so long ago that the row is about to be deleted
            # (FIRED_KEEP) - an answer written now would go with it unseen.
            return 409, {"ok": False, "error": ASK_NOT_FIRED}
        buttons = action.get("buttons") or []
        if isinstance(index, bool) or not isinstance(index, int) \
                or not 0 <= index < len(buttons):
            return 400, {"ok": False,
                         "error": f"Which button? Say its number, from 0 to {len(buttons) - 1}."}
        button = buttons[index]
        does = str(button.get("does") or "")
        record = action.get("record") if isinstance(action.get("record"), dict) else {}
        wrote: list = []
        problems: list = []
        if record.get("history"):
            wrote.append("its own history")
        # A `record` button writes the chosen destinations. A `done` or
        # `snooze` button does its own one thing and writes no note: that is
        # what "each button does ONE thing" means, and it keeps the journal
        # free of "Snoozed 30 minutes" lines the owner never asked for.
        if does == "record":
            line = _answer_line(row["text"], button["label"], now)
            if record.get("obsidian_daily"):
                why = _write_daily_note(line, now)
                (problems if why else wrote).append(
                    why if why else "today's Obsidian note")
            if record.get("goal"):
                why = _write_goal(str(record["goal"]), line, now)
                (problems if why else wrote).append(why if why else "goal progress")
            if record.get("habit"):
                why = _write_habit(str(record["habit"]), line, now)
                (problems if why else wrote).append(why if why else "a habit tick")
        said = _wrote_words(wrote, problems)
        if does == "done":
            said = self._answer_done(jid, row, now)
        elif does == "snooze":
            code, out = self.snooze(jid, float(button["minutes"]) * 60.0)
            if code != 200:
                return code, out
            said = str(out.get("said") or "") or said
            # A snoozed QUESTION asks again when it comes back: its own copy
            # carries the same block. Without this the copy would come back as
            # a plain reminder with the words and no buttons - the owner would
            # have snoozed a question into a statement.
            copy_id = (out.get("job") or {}).get("id")
            if copy_id:
                self._copy_question(jid, str(copy_id))
        entry = {"at": float(now), "clock": clock(now), "button": button["label"],
                 "does": does, "wrote": wrote}
        if problems:
            entry["problems"] = problems
        self._append_answer(jid, entry)
        _audit("schedule.answered", {"id": jid, "button": index, "does": does,
                                     "wrote": list(wrote), "problems": len(problems),
                                     "source": str(source)[:20]})
        if does != "done":
            # Every app hears that this job changed, so the other one takes its
            # notification away and the row redraws with the new answer on it.
            # `done` already did this inside `end`/the UPDATE.
            self._changed(jid, row["kind"])
        return 200, {"ok": True, "id": jid, "button": button["label"], "does": does,
                     "wrote": wrote, "problems": problems, "said": said,
                     "answers": self.answers(jid)}

    def _copy_question(self, from_jid: str, to_jid: str) -> None:
        """Give a snoozed copy the question it came from.

        Only `snooze` makes a copy, so this is the one place a second row can
        hold an `ask` block. Nothing else about the copy changes, and a job that
        is not a question is left exactly as `snooze` made it."""
        with self._lock, self._db() as c:
            row = self._row(c, from_jid)
            if row is None:
                return
            raw = _row_action(row)
            if not _decode_action(raw):
                return
            c.execute("UPDATE jobs SET action = ? WHERE id = ?", (raw, str(to_jid)))

    def _answer_done(self, jid: str, row, now: float) -> str:
        """The "Done" button: this occurrence is dealt with.

        A repeating reminder STOPS repeating (`end`), which is exactly what
        deleting it would do and only ever makes Jarvis quieter. A one-off
        leaves "Just went off" and is kept DONE_KEEP, like a to-do item ticked
        off. Neither asks a card: an answer that quiets something needs none."""
        if row["rule"]:
            self.end(jid)
            return "Marked done - it will not repeat again."
        with self._lock, self._db() as c:
            c.execute("UPDATE jobs SET state = 'done', due = NULL, changed = ?, "
                      "fired_at = COALESCE(fired_at, ?) WHERE id = ?", (now, now, jid))
        self._changed(jid, row["kind"])
        return "Marked done."

    def _append_answer(self, jid: str, entry: dict) -> None:
        """ONE answer onto the end of the reminder's own log, keeping the newest
        MAX_ANSWERS. A log that grows without a bound is a leak on a PC that is
        never rebooted, and 40 taps is more than a month of a daily question."""
        with self._lock, self._db() as c:
            row = c.execute("SELECT answers FROM jobs WHERE id = ?", (str(jid),)).fetchone()
            if row is None:
                return
            kept = _decode_answers(row["answers"])
            kept.append(entry)
            kept = kept[-MAX_ANSWERS:]
            c.execute("UPDATE jobs SET answers = ? WHERE id = ?",
                      (json.dumps(kept), str(jid)))

    # ---- changing one job ---------------------------------------------------------

    #: Waves of work finish; the owner decides when a TASK finished.
    #: "Ready for your review" is therefore its own marker, never `done`.
    def propose_ready(self, jid: str, *, review_note: str = "") -> tuple:
        """Jarvis has done its part: mark a to-do READY FOR THE OWNER.

        Nothing is completed here (`done` stays False), and there is no route
        that marks a task done except the owner's own `act("done")`.
        Idempotent: proposing again only refreshes the time. Only a to-do item
        can wait for review (a reminder or alarm is not the owner's task
        list). The audit line carries the id, the kind and the outcome ONLY -
        a `review_note` is accepted for callers to pass words along but is
        deliberately NOT logged (Wave D-1, Upgrades D6; D-1.4 gate)."""
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None:
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            if row["state"] not in ("active", "paused"):
                return 409, {"ok": False,
                             "error": "That item is not waiting on you."}
            if row["kind"] != "todo":
                return 409, {"ok": False,
                             "error": "Only a to-do item can be ready for your review."}
            c.execute("UPDATE jobs SET ready_for_review = ?, changed = ? WHERE id = ?",
                      (now, now, jid))
        _audit("schedule.ready", {"id": jid, "kind": "todo",
                                  "outcome": "ready_for_review"})
        self._changed(jid, "todo")
        return 200, {"ok": True, "ready_for_review": True,
                     "said": READY_SAID}

    def suggest_done(self, jid: str, *, review_note: str = "") -> tuple:
        """The name the Wave D-1 gate uses for the same proposal: "this looks
        finished - you decide". It NEVER sets done; it only marks the item
        ready for the owner's review, and any `review_note` words are not
        logged. `propose_ready` is the older spelling of the one method."""
        return self.propose_ready(jid, review_note=review_note)

    #: Phase 2: the field names an edit may carry. `list` is a move made inside
    #: an edit (to-dos only); `seconds` is a timer's new length; the rest are
    #: a one-off job's own time.
    EDIT_KEYS = ("text", "when", "date", "time", "at", "repeat", "list", "seconds")

    def act(self, jid: str, do: str, seconds: Optional[float] = None,
            fields: Optional[dict] = None) -> tuple:
        """ONE job: pause, resume, delete, done, add_time, snooze, edit, move,
        reorder. (code, answer). `fields` is the request body for the three
        Phase 2 verbs; every older verb ignores it, so existing callers are
        unchanged."""
        do = str(do or "").strip().lower()
        if do == "snooze":
            return self.snooze(jid, seconds)
        if do == "delete":
            # Routed before this method's own list gate, exactly as snooze is
            # (2026-10-13). A job that went off is no longer on the live list
            # but is still SHOWN under "Just went off", and the owner decided
            # that an entry the apps list must be one they can clear. Every
            # other verb still refuses a fired job - see delete()'s docstring.
            return self.delete(jid)
        if do in ("edit", "move", "reorder"):
            body = {key: value for key, value in (fields or {}).items()
                    if key not in ("id", "do")}
            return self._act_phase2(jid, do, body)
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None:
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            if row["state"] == "fired":
                # It has already gone off. Saying "not on the list any more"
                # would be false - both apps show it under "Just went off" -
                # and pausing, resuming, ticking off or adding time to
                # something that has already gone off means nothing. Snooze
                # and Delete are routed above and do act on one.
                return 409, {"ok": False, "error": "It has already gone off."}
            if row["state"] not in ("active", "paused", "waiting"):
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            kind, state = row["kind"], row["state"]
            if do == "done":
                if kind != "todo":
                    return 409, {"ok": False, "error": "Only a to-do item can be marked done."}
                c.execute("UPDATE jobs SET state = 'done', changed = ?, fired_at = ?, "
                          "ready_for_review = NULL WHERE id = ?", (now, now, jid))
                said = "Marked done."
            elif do == "pause":
                k = KINDS.get(kind)
                if state != "active" or kind == "todo" or (k is not None and k.ends):
                    # A kind with no time of its own ("remind me next time
                    # ...") has nothing to pause: delete it instead.
                    return 409, {"ok": False, "error": "That cannot be paused now."}
                left = max(0.0, (row["due"] or now) - now) if kind == "timer" else None
                c.execute("UPDATE jobs SET state = 'paused', left_s = ?, changed = ? "
                          "WHERE id = ?", (left, now, jid))
                said = "Paused."
            elif do == "resume":
                if state != "paused":
                    return 409, {"ok": False, "error": "That is not paused."}
                over = False
                if kind == "timer":
                    due = now + float(row["left_s"] or 0.0)
                elif row["rule"]:
                    rule = json.loads(row["rule"])
                    due = next_run(rule, now)
                    # A rule with an end date ("tell me when") whose end
                    # passed while it was paused, or comes before its next
                    # run: it is over, not resumed for one more look.
                    over = rule.get("ends") is not None and due > float(rule["ends"])
                else:
                    # A one-off whose time passed while it was paused goes
                    # off now, once, as missed - not silently dropped.
                    due = row["due"]
                if over:
                    c.execute("UPDATE jobs SET state = 'fired', due = NULL, left_s = NULL, "
                              "fired_at = ?, fired_due = NULL, late = 0, changed = ? "
                              "WHERE id = ?", (now, now, jid))
                    said = "Its end date has passed, so it has ended."
                else:
                    c.execute("UPDATE jobs SET state = 'active', due = ?, left_s = NULL, "
                              "changed = ? WHERE id = ?", (due, now, jid))
                    said = "Resumed."
            elif do == "add_time":
                if kind != "timer":
                    return 409, {"ok": False, "error": "Time can only be added to a timer."}
                try:
                    extra = float(seconds)
                except (TypeError, ValueError):
                    return 400, {"ok": False, "error": "How much time? (seconds)"}
                if extra == 0 or extra != extra:
                    return 400, {"ok": False, "error": "How much time? (seconds)"}
                if state == "paused":
                    left = float(row["left_s"] or 0.0) + extra
                else:
                    left = float(row["due"] or now) - now + extra
                if left < MIN_TIMER:
                    return 409, {"ok": False, "error": "That would leave no time on the timer."}
                if left > MAX_TIMER:
                    return 409, {"ok": False, "error": "A timer can be up to 24 hours."}
                dur = float(row["duration"] or 0.0) + extra
                if state == "paused":
                    c.execute("UPDATE jobs SET left_s = ?, duration = ?, changed = ? "
                              "WHERE id = ?", (left, dur, now, jid))
                else:
                    c.execute("UPDATE jobs SET due = ?, duration = ?, changed = ? "
                              "WHERE id = ?", (now + left, dur, now, jid))
                said = f"{length_words(left)} left."
            else:
                return 400, {"ok": False, "error": "do is one of: pause, resume, delete, done, "
                                                   "add_time, snooze, edit, move, reorder"}
        _audit("schedule.act", {"id": jid, "kind": kind, "do": do})
        self._changed(jid, kind)
        return 200, {"ok": True, "id": jid, "said": said}

    # ---- Phase 2: edit / move / reorder (2026-10-22) --------------------------------
    #
    # ONE job per call, no card except a repeat change (which raises the SAME
    # `schedule_repeat` card a new repeating job does, with the OLD rule still
    # running until the owner says yes), and never a list form. The order is
    # act()'s: clear_list is routed earlier in handle_act(), snooze/delete are
    # routed before the row gate, and these three run after it - so a fired,
    # waiting or done job gets that refusal first.

    def _act_phase2(self, jid: str, do: str, fields: dict) -> tuple:
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None:
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            if row["state"] == "fired":
                return 409, {"ok": False, "error": "It has already gone off."}
            if row["state"] not in ("active", "paused", "waiting"):
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            if row["state"] == "waiting":
                return 409, {"ok": False,
                             "error": "That job is waiting for its card - answer it first."}
            kind = row["kind"]
            if do == "edit":
                result = self._edit(c, row, now, fields)
            elif do == "move":
                result = self._move(c, row, now, fields)
            else:
                result = self._reorder(c, row, now, fields)
            if isinstance(result, tuple):
                return result
        if "card" in result:
            plan = result["card"]
            # Audited now, ids and field NAMES only - never a value, a list's
            # words or the rule. The OLD schedule keeps running until the card
            # is answered; the card's own line is audited by `_ask_edit`.
            _audit("schedule.act", {"id": jid, "kind": kind, "do": "edit",
                                    "fields": plan["fields"]})
            self._spawn(lambda: self._ask_edit(jid, plan))
            return 202, {"ok": True, "waiting": True, "job": self.job(jid)}
        detail = {"id": jid, "kind": kind, "do": do}
        detail.update(result.get("audit") or {})
        _audit("schedule.act", detail)
        if result.get("changed", True):
            self._changed(jid, kind)
        return 200, {"ok": True, "id": jid,
                    "said": result.get("said") or result.get("ok")}

    def _edit(self, c, row, now: float, fields: dict):
        """Validate ONE edit, then either write it (cardless) or return the
        pending plan for the ONE repeat card. Never writes before every given
        field has been checked: all-or-nothing."""
        kind, state = row["kind"], row["state"]
        k = KINDS.get(kind)
        if k is not None and k.add is not None:
            # tellme/standby/briefing/today...: their module owns the body.
            return 409, {"ok": False, "error": "That is changed where it was set up."}
        unknown = sorted(set(fields) - set(self.EDIT_KEYS))
        if unknown:
            return 400, {"ok": False,
                         "error": "edit changes only text, when, date/time, at, "
                                  "repeat, list and seconds"}
        if not fields:
            return 400, {"ok": False, "error": "an edit needs at least one field to change"}
        has_text = "text" in fields
        has_repeat = "repeat" in fields
        has_list = "list" in fields
        timed = [key for key in ("when", "at", "date", "time", "seconds") if key in fields]
        if len(timed) > 1 and set(timed) != {"date", "time"}:
            return 400, {"ok": False,
                         "error": "give one time: when, at, date+time or seconds"}
        if timed and kind == "todo":
            return 409, {"ok": False, "error": "A to-do item has no time of its own."}
        if "seconds" in timed and kind != "timer":
            return 409, {"ok": False, "error": "Only a timer is set in seconds."}
        if timed and kind == "timer" and "seconds" not in timed:
            return 409, {"ok": False,
                         "error": "A timer's length is changed in seconds, not a time."}
        if has_list and kind != "todo":
            return 409, {"ok": False, "error": "Only a to-do item can move between lists."}
        if has_repeat:
            if not _repeatable(kind):
                return 409, {"ok": False,
                             "error": "Only alarms, reminders and briefings can repeat."}
            if timed:
                return 400, {"ok": False,
                             "error": "a repeat change sets its own times - give either a "
                                      "repeat or a time, not both"}
        if timed and kind != "timer" and row["rule"]:
            # A repeating rule is changed by editing its repeat, never by moving
            # its next run - so this is a plain refusal, not a silent move.
            return 409, {"ok": False,
                         "error": "That job repeats - change its repeat, not its next time."}
        new_text = None
        if has_text:
            if not isinstance(fields.get("text"), str):
                return 400, {"ok": False, "error": "text is words"}
            try:
                new_text = self._clean_text(fields["text"], kind)
            except ValueError as exc:
                return 400, {"ok": False, "error": _sentence(exc)}
        new_rule = None
        if has_repeat:
            try:
                raw = fields.get("repeat")
                new_rule = k.check(raw, now) if (k is not None and k.check is not None) \
                    else check_rule(raw, now)
            except ValueError as exc:
                return 400, {"ok": False, "error": _sentence(exc)}
        new_due = new_left = new_duration = None
        if "seconds" in timed:
            if isinstance(fields.get("seconds"), bool):
                return 400, {"ok": False, "error": "a timer needs a length"}
            try:
                seconds = float(fields["seconds"])
            except (TypeError, ValueError):
                return 400, {"ok": False, "error": "a timer needs a length"}
            if seconds != seconds or seconds < MIN_TIMER:
                return 400, {"ok": False,
                             "error": "a timer needs a length of at least a second"}
            if seconds > MAX_TIMER:
                return 400, {"ok": False,
                             "error": "a timer can be up to 24 hours - for later than "
                                      "that, set a reminder"}
            new_duration = seconds
            if state == "paused":
                new_left = seconds
            else:
                new_due = now + seconds
        elif timed:
            try:
                if "when" in fields:
                    when = fields["when"]
                    if isinstance(when, dict):
                        at = wall_at(when.get("date"), when.get("time"))
                    elif isinstance(when, bool) or not isinstance(when, (int, float)):
                        raise ValueError("when is a timestamp, or an object with date and time")
                    else:
                        at = float(when)
                elif "at" in fields:
                    at = _num(fields["at"])
                    if at is None:
                        raise ValueError("at is a timestamp")
                else:
                    at = wall_at(fields.get("date"), fields.get("time"))
            except ValueError as exc:
                return 400, {"ok": False, "error": _sentence(exc)}
            if at <= now:
                return 400, {"ok": False, "error": "that time has already passed"}
            if at - now > MAX_AHEAD:
                return 400, {"ok": False, "error": "that is more than a year away"}
            new_due = at
        if has_repeat:
            # ONE card, old rule still active until it is answered. Only the
            # field NAMES go in the audit line, in a fixed order. The card is
            # ALSO bound to the rule and words it was raised for (PA-6): a
            # newer edit that lands while it waits makes it stale, never
            # overwritten by the older card.
            named = [name for name, present in
                     (("repeat", True), ("text", has_text), ("when", False)) if present]
            return {"card": {"rule": new_rule, "text": new_text, "fields": named,
                             "base_rule": row["rule"], "base_text": row["text"]}}
        target_key = None
        if has_list:
            target = self._list_target(c, fields.get("list"))
            if isinstance(target, tuple):
                return target
            target_key = target
        sets, args = ["changed = ?"], [now]
        if has_text:
            sets.append("text = ?")
            args.append(new_text)
        if new_due is not None:
            sets.append("due = ?")
            args.append(new_due)
        if new_left is not None:
            sets.append("left_s = ?")
            args.append(new_left)
        if new_duration is not None:
            sets.append("duration = ?")
            args.append(new_duration)
        # The same rule as creation: an edit made while the private latch is
        # on marks the row, so the next firing replays it.
        mark = _taint_mark()
        if mark:
            sets.append("source_taint = ?")
            args.append(mark)
        c.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", (*args, row["id"]))
        if has_list:
            self._move_in_tx(c, row, target_key, now)
        named = [name for name, present in
                 (("repeat", False), ("text", has_text), ("when", bool(timed)))
                 if present]
        audit = {"fields": named}
        if has_list:
            # A list change inside an edit is a move; the boolean says it was
            # a NAMED list without ever logging its words.
            audit["named_list"] = target_key is not None
        return {"ok": "Changed.", "audit": audit, "changed": True}

    def _list_target(self, c, raw):
        """A move target: None is the to-do list itself; a new name counts
        against MAX_LISTS. The key, or a (code, body) error tuple."""
        if raw is None:
            return None
        if isinstance(raw, str) and raw.strip().lower() in ("", "todo", "to-do"):
            return None
        if not isinstance(raw, str):
            return 400, {"ok": False, "error": "a list's name is words"}
        try:
            key = list_key(raw)
        except ValueError as exc:
            return 400, {"ok": False, "error": _sentence(exc)}
        names = {str(r[0]) for r in c.execute(
            "SELECT DISTINCT list_name FROM jobs WHERE kind = 'todo' AND state IN "
            "('active','paused') AND list_name IS NOT NULL").fetchall()}
        if key not in names and len(names) >= MAX_LISTS:
            return 409, {"ok": False,
                         "error": f"there are already {MAX_LISTS} lists - finish one first"}
        return key

    def _move_in_tx(self, c, row, target_key, now: float) -> bool:
        """Move ONE to-do to the END of its target list and renumber both lists
        0..n-1 inside the caller's transaction. False when it is already there."""
        jid = row["id"]
        old_key = row["list_name"] or ""
        new_key = target_key or ""
        if new_key == old_key:
            return False
        c.execute("UPDATE jobs SET list_name = ? WHERE id = ?", (target_key, jid))
        count = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE kind = 'todo' AND state IN ('active','paused') "
            "AND ifnull(list_name, '') = ? AND id != ?", (new_key, jid)).fetchone()[0]
        c.execute("UPDATE jobs SET rank = ? WHERE id = ?", (int(count), jid))
        self._renumber_list(c, new_key)
        self._renumber_list(c, old_key)
        return True

    def _renumber_list(self, c, key: str) -> None:
        """Rewrite ONE list's open to-dos to ranks 0..n-1, in the order they
        already read, so ordering never depends on gaps or insertion order."""
        rows = c.execute(
            "SELECT id, rank FROM jobs WHERE kind = 'todo' AND state IN ('active','paused') "
            "AND ifnull(list_name, '') = ? ORDER BY (rank IS NULL), rank, created, rowid",
            (key,)).fetchall()
        for i, r in enumerate(rows):
            if r["rank"] != i:
                c.execute("UPDATE jobs SET rank = ? WHERE id = ?", (i, r["id"]))

    def _move(self, c, row, now: float, fields: dict):
        if row["kind"] != "todo":
            return 409, {"ok": False, "error": "Only a to-do item can move between lists."}
        if set(fields) - {"list"}:
            return 400, {"ok": False, "error": "move changes only the list"}
        if "list" not in fields:
            return 400, {"ok": False,
                         "error": "move needs a list (null for the to-do list)"}
        target = self._list_target(c, fields.get("list"))
        if isinstance(target, tuple):
            return target
        said = "Moved to the to-do list." if target is None else "Moved to that list."
        if (target or "") == (row["list_name"] or ""):
            return {"ok": said, "audit": {"named_list": target is not None},
                    "changed": False}
        self._move_in_tx(c, row, target, now)
        c.execute("UPDATE jobs SET changed = ? WHERE id = ?", (now, row["id"]))
        return {"ok": said, "audit": {"named_list": target is not None}, "changed": True}

    def _reorder(self, c, row, now: float, fields: dict):
        if row["kind"] != "todo":
            return 409, {"ok": False, "error": "Only a to-do item can be reordered."}
        if set(fields) - {"rank", "before", "after"}:
            return 400, {"ok": False,
                         "error": "reorder changes only rank (or before/after)"}
        key = row["list_name"] or ""
        rows = c.execute(
            "SELECT id FROM jobs WHERE kind = 'todo' AND state IN ('active','paused') "
            "AND ifnull(list_name, '') = ? ORDER BY (rank IS NULL), rank, created, rowid",
            (key,)).fetchall()
        ids = [r["id"] for r in rows]
        n = len(ids)
        if n == 0:
            return 409, {"ok": False, "error": "There is nothing on that list to reorder."}
        if "rank" in fields:
            if "before" in fields or "after" in fields:
                return 400, {"ok": False,
                             "error": "give rank, or before, or after - one of them"}
            value = fields["rank"]
            if isinstance(value, bool) or not isinstance(value, int):
                return 400, {"ok": False,
                             "error": f"rank is a whole position, 0 to {n - 1}"}
            target = value
        elif "before" in fields or "after" in fields:
            anchor = fields.get("before") if "before" in fields else fields.get("after")
            rest = [jid for jid in ids if jid != row["id"]]
            if not isinstance(anchor, str) or anchor not in rest:
                return 400, {"ok": False,
                             "error": "before/after is another item on that list"}
            target = rest.index(anchor) + (1 if "after" in fields else 0)
        else:
            return 400, {"ok": False, "error": "reorder needs rank, before or after"}
        if target < 0 or target > n - 1:
            return 400, {"ok": False, "error": f"rank is a whole position, 0 to {n - 1}"}
        current = ids.index(row["id"])
        if target == current:
            # Idempotent: the second identical request writes nothing at all.
            return {"ok": "Reordered.", "audit": {"rank": target}, "changed": False}
        rest = [jid for i, jid in enumerate(ids) if i != current]
        order = rest[:target] + [row["id"]] + rest[target:]
        for i, other in enumerate(order):
            c.execute("UPDATE jobs SET rank = ? WHERE id = ?", (i, other))
        c.execute("UPDATE jobs SET changed = ? WHERE id = ?", (now, row["id"]))
        return {"ok": "Reordered.", "audit": {"rank": target}, "changed": True}

    # ---- delete -----------------------------------------------------------------------

    def delete(self, jid: str) -> tuple:
        """ONE job, gone - no card (stopping only makes things quieter).

        Routed before act()'s own list gate, the same way snooze() is. A job
        that WENT OFF is not on the live list any more, but it is still
        SHOWN under "Just went off" for WENT_OFF_SHOWN (an hour) and stays
        readable by id for FIRED_KEEP (a day), and the owner decided on
        2026-10-13 that an entry the apps list must be one they can clear.
        So 'fired' is the one extra state this accepts; the rest of the set
        (active, paused, waiting) is exactly act()'s, and a 'waiting' job
        still says its card will set nothing up. 'done' is still refused: a
        to-do ticked off is on no list at all, so "not on the list any more"
        is the honest answer for it."""
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None or row["state"] not in ("active", "paused", "waiting", "fired"):
                return 404, {"ok": False, "reason": "no_such_job",
                             "error": "That is not on the list any more."}
            kind, state = row["kind"], row["state"]
            c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
        said = "Deleted. The card for it will set nothing up." if state == "waiting" else "Deleted."
        _audit("schedule.act", {"id": jid, "kind": kind, "do": "delete"})
        self._changed(jid, kind)
        return 200, {"ok": True, "id": jid, "said": said}

    # ---- snooze -----------------------------------------------------------------------

    def snooze(self, jid: str, seconds: Optional[float] = None) -> tuple:
        """A timer, alarm or reminder that WENT OFF, again after `seconds`
        (SNOOZE_DEFAULT when not said). A new one-off copy: a repeating
        job's own times are not touched, so only that one occurrence moves.
        No card - a one-off needs none. Snoozing the same one twice while
        its copy waits changes nothing ("already")."""
        now = self.now()
        try:
            length = SNOOZE_DEFAULT if seconds is None else float(seconds)
        except (TypeError, ValueError):
            length = float("nan")
        if length != length or length < SNOOZE_MIN or length > SNOOZE_MAX:
            return 400, {"ok": False, "error": "A snooze is from 1 minute to 24 hours."}
        with self._lock:
            with self._db() as c:
                row = self._row(c, jid)
                if row is None:
                    return 404, {"ok": False, "reason": "no_such_job",
                                 "error": "That is not on the list any more."}
                if row["kind"] not in SNOOZABLE:
                    return 409, {"ok": False,
                                 "error": "Only a timer, an alarm or a reminder can be snoozed."}
                fired = row["fired_at"]
                if (fired is None or row["state"] not in ("fired", "active", "paused")
                        or now - float(fired) > FIRED_KEEP):
                    return 409, {"ok": False, "error": "It has not gone off, so there is nothing "
                                                       "to snooze."}
                if row["snoozed_to"]:
                    copy = self._row(c, row["snoozed_to"])
                    if copy is not None and copy["state"] in ("active", "paused") \
                            and copy["due"] is not None:
                        return 200, {"ok": True, "id": jid, "already": True,
                                     "job": self._view(copy, now),
                                     "said": f"Already snoozed until {clock(float(copy['due']))}."}
                try:
                    self._room(c, row["kind"])
                except OverflowError as exc:
                    return 409, {"ok": False, "error": _sentence(exc)}
                kind, text = row["kind"], row["text"]
            copy_id = self._insert(kind, text=text, state="active", due=now + length, rule=None,
                                   duration=length if kind == "timer" else None,
                                   source="snooze", snooze_of=jid,
                                   # A snooze copy of a tainted row inherits
                                   # the mark even after the latch expired.
                                   source_taint=_row_taint(row) or None)
            with self._db() as c:
                c.execute("UPDATE jobs SET snoozed_to = ?, changed = ? WHERE id = ?",
                          (copy_id, now, jid))
        _audit("schedule.snooze", {"id": jid, "kind": kind, "copy": copy_id})
        self._changed(jid, kind)
        return 200, {"ok": True, "id": jid, "job": self.job(copy_id),
                     "said": f"Snoozed for {length_words(length)} - until {clock(now + length)}."}

    def went_off(self, now: Optional[float] = None) -> list:
        """What went off in the last WENT_OFF_SHOWN seconds and could be
        snoozed - newest first, at most five. One already snoozed is left
        out: its copy is on the list."""
        now = self.now() if now is None else now
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE fired_at IS NOT NULL AND fired_at >= ? "
                             "AND kind IN ('timer','alarm','reminder') "
                             "AND state IN ('fired','active','paused') AND snoozed_to IS NULL "
                             "ORDER BY fired_at DESC LIMIT 5",
                             (now - WENT_OFF_SHOWN,)).fetchall()
        return [self._view(r, now) for r in rows]

    def fired_since(self, since: float, now: Optional[float] = None) -> list:
        """Everything that went off at or after `since`, oldest first, that
        the owner is told about ("What did I miss?"). A repeating job shows
        its latest time only; a one-off is kept FIRED_KEEP."""
        now = self.now() if now is None else now
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE fired_at IS NOT NULL AND fired_at >= ? "
                             "AND fired_at <= ? ORDER BY fired_at", (since, now)).fetchall()
        out = []
        for r in rows:
            k = KINDS.get(r["kind"])
            if k is not None and (not k.notify or not k.owner_listed or k.silent):
                # A silent kind going off is a look, not news ("tell me
                # when" checking the inbox): it did not "go off" for the
                # owner. A match has its own event and alert.
                continue
            if r["kind"] == "todo" and r["fired_due"] is None:
                continue       # a to-do ticked off, not one that went off
            out.append(self._view(r, now))
        return out

    # ---- named lists ------------------------------------------------------------------

    def lists(self) -> list:
        """The named lists with open items, oldest first:
        [{"name": "shopping", "title": "Shopping list", "open": 3}]."""
        with self._lock, self._db() as c:
            rows = c.execute("SELECT list_name, COUNT(*) AS n, MIN(created) AS first FROM jobs "
                             "WHERE kind = 'todo' AND state IN ('active','paused') "
                             "AND list_name IS NOT NULL GROUP BY list_name "
                             "ORDER BY first").fetchall()
        return [{"name": r["list_name"], "title": list_title(r["list_name"]), "open": int(r["n"])}
                for r in rows]

    def clear_list(self, name, count) -> tuple:
        """Every open item on ONE named list, deleted - only from the apps,
        after their "are you sure?", and only when `count` is how many items
        the app showed (so nothing added since is lost). Never the to-do
        list itself."""
        try:
            key = list_key(name)
        except ValueError as exc:
            return 400, {"ok": False, "error": _sentence(exc)}
        if key is None:
            return 409, {"ok": False, "error": "The to-do list is not cleared all at once - mark "
                                               "items done or delete them one at a time."}
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return 400, {"ok": False, "error": "Say how many items you saw on the list."}
        title = _lower_first(list_title(key))
        with self._lock:
            with self._db() as c:
                ids = [r["id"] for r in c.execute(
                    "SELECT id FROM jobs WHERE kind = 'todo' AND state IN ('active','paused') "
                    "AND list_name = ?", (key,)).fetchall()]
                if not ids:
                    # 409, like a count that no longer fits: the list changed
                    # since the app looked (a 404 would read as an older PC).
                    return 409, {"ok": False, "error": f"There is nothing on the {title} any more."}
                if len(ids) != count:
                    return 409, {"ok": False, "error": (
                        f"The {title} changed since you looked - it has {len(ids)} "
                        f"item{'s' if len(ids) != 1 else ''} now. Look again before clearing it.")}
                for jid in ids:
                    c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
        _audit("schedule.clear_list", {"count": len(ids)})
        self._changed(ids[0], "todo")
        n = len(ids)
        return 200, {"ok": True, "cleared": n,
                     "said": f"Cleared your {title} ({n} item{'s' if n != 1 else ''})."}

    # ---- "cancel that" ------------------------------------------------------------------

    def note_set(self, conversation, ids, what: str, intent: str, nouns=()) -> None:
        """The fast path just SET these jobs in this conversation (in memory
        only). The next note replaces it: only the last thing can be taken
        back."""
        if not conversation or not ids:
            return
        with self._lock:
            if len(self._recent) > 200:
                oldest = min(self._recent, key=lambda k: self._recent[k]["at"])
                self._recent.pop(oldest, None)
            self._recent[str(conversation)] = {"ids": list(ids), "what": str(what),
                                               "intent": str(intent), "nouns": list(nouns),
                                               "at": self.now()}

    def last_set(self, conversation, now: Optional[float] = None) -> Optional[dict]:
        """What the fast path last set in this conversation, with its `age`
        in seconds - or None (nothing, or more than UNDO_REMEMBER ago)."""
        if not conversation:
            return None
        now = self.now() if now is None else now
        with self._lock:
            rec = self._recent.get(str(conversation))
            if rec is None:
                return None
            if now - rec["at"] > UNDO_REMEMBER:
                self._recent.pop(str(conversation), None)
                return None
            return dict(rec, ids=list(rec["ids"]), age=max(0.0, now - rec["at"]))

    def forget_set(self, conversation) -> None:
        with self._lock:
            self._recent.pop(str(conversation or ""), None)

    def take_back(self, ids) -> int:
        """Delete the jobs the fast path just set ("cancel that"). Only jobs
        still on the list; a snoozed copy also frees its original, so it can
        be snoozed again. Returns how many were taken back."""
        n = 0
        with self._lock:
            for jid in ids:
                with self._db() as c:
                    row = self._row(c, jid)
                    if row is None or row["state"] not in ("active", "paused", "waiting"):
                        continue
                    c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
                    if row["snooze_of"]:
                        c.execute("UPDATE jobs SET snoozed_to = NULL WHERE id = ? "
                                  "AND snoozed_to = ?", (row["snooze_of"], jid))
                n += 1
                _audit("schedule.act", {"id": jid, "kind": row["kind"], "do": "take_back"})
                self._changed(jid, row["kind"])
        return n

    # ---- the loop -------------------------------------------------------------------

    def tick(self, now: Optional[float] = None) -> list:
        """One look at the list: everything due goes off, ONCE. Returns the
        ids that went off. Public, so the tests drive it with their own clock."""
        now = self.now() if now is None else now
        went = []
        with self._lock, self._db() as c:
            last, self._last_tick_now = self._last_tick_now, now
            if last is not None and now < last:
                # The clock went BACKWARDS between two ticks. A timer is a
                # length of time ("10 minutes"), not a time on the clock: it must
                # keep the time it had left, not wait an extra hour. Only timers
                # - an alarm or a reminder is a time on the clock, and stays.
                c.execute("UPDATE jobs SET due = due - ? WHERE kind = 'timer' "
                          "AND state = 'active' AND due IS NOT NULL", (last - now,))
            rows = c.execute("SELECT * FROM jobs WHERE state = 'active' AND due IS NOT NULL "
                             "AND due <= ? AND (trigger IS NULL OR trigger = 'time') "
                             "ORDER BY due", (now,)).fetchall()
            for row in rows:
                late = (now - float(row["due"])) > LATE_AFTER
                ended = False
                past_end = False
                if row["rule"]:
                    try:
                        rule = json.loads(row["rule"])
                        nxt = next_run(rule, now)
                        # A rule with an end date ("tell me when",
                        # jarvis_tellme.py): this is its last run when the
                        # next one would come after the end.
                        if rule.get("ends") is not None:
                            ends = float(rule["ends"])
                            if nxt > ends:
                                nxt = None
                            # Found only after its end date (the PC slept
                            # through it, or it was resumed with its next
                            # time past the end): it is finished, and does
                            # NOT run one more time - a look now could tell
                            # the owner about something that happened after
                            # the date the card promised.
                            past_end = (float(row["due"]) > ends
                                        or now > ends + LATE_AFTER)
                    except Exception:
                        nxt = None
                    ended = nxt is None
                    # Straight to the next time after NOW: a week of missed
                    # dailies goes off once, not seven times.
                    # Going off again: an earlier snooze of it is its own job
                    # now, so this time can be snoozed afresh.
                    c.execute("UPDATE jobs SET due = ?, fired_at = ?, fired_due = ?, late = ?, "
                              "changed = ?, state = ?, snoozed_to = NULL WHERE id = ?",
                              (nxt, now, row["due"], int(late), now,
                               "active" if nxt is not None else "fired", row["id"]))
                elif row["kind"] == "todo":
                    # A to-do with a time stays on the list until it is
                    # done; going off only takes its time away.
                    c.execute("UPDATE jobs SET due = NULL, fired_at = ?, fired_due = ?, "
                              "late = ?, changed = ? WHERE id = ?",
                              (now, row["due"], int(late), now, row["id"]))
                else:
                    c.execute("UPDATE jobs SET state = 'fired', fired_at = ?, fired_due = ?, "
                              "late = ?, changed = ?, resolved_at = COALESCE(resolved_at, ?) "
                              "WHERE id = ?",
                              (now, row["due"], int(late), now, now, row["id"]))
                went.append((row["id"], row["kind"], late, ended, past_end,
                             _row_taint(row), _row_action(row), float(row["due"])))
            # Housekeeping: what went off a day ago, and done to-dos a week old.
            c.execute("DELETE FROM jobs WHERE state = 'fired' AND fired_at < ?",
                      (now - FIRED_KEEP,))
            c.execute("DELETE FROM jobs WHERE state = 'done' AND fired_at < ?",
                      (now - DONE_KEEP,))
            c.execute("DELETE FROM commands WHERE at < ?", (now - 30 * 86400,))
            # GTD-1: a resolved reminder's context packet is dropped after
            # BUNDLE_RETENTION_DAYS days - the bare reminder row stays, the
            # details that were only there to help do it do not.
            _expire_bundles(c, now)
        for jid, kind, late, ended, past_end, taint, action_raw, due in went:
            self.fired += 1
            k = KINDS.get(kind)
            if past_end:
                # Over before it could run again: the list is told it
                # changed, and nothing goes off.
                _audit("schedule.ended", {"id": jid, "kind": kind, "past_end": True})
                self._changed(jid, kind)
                continue
            if taint:
                # Schedule-source taint: the row was written while the private
                # latch was on, and that latch's own minutes have long passed.
                # Replay it ONCE, here, before the fired event, before the
                # kind's own on_fire and before anything this row can
                # influence runs. Nothing in jarvis_schedule reads the latch
                # itself afterwards; it is there for whatever does.
                _latch_fired_taint(taint)
            if k is not None and k.silent:
                # A look, not news ("tell me when" checking the inbox every
                # five minutes): no doorbell, and no audit line per look -
                # the kind's own on_fire says when something matched. Only
                # the list changing (its last look, at its end) is told.
                if ended:
                    self._changed(jid, kind)
            else:
                _audit("schedule.fired", {"id": jid, "kind": kind, "late": late})
                data = {"id": jid, "kind": kind, "state": "fired", "late": bool(late)}
                if k is not None and not k.notify:
                    # Nothing to tell the owner (the standby schedule at
                    # 01:00): both apps show no notification or toast for it.
                    data["notify"] = False
                self._publish("schedule", data)
            if k is not None and k.on_fire is not None:
                fn = k.on_fire
                self._spawn(lambda fn=fn, jid=jid: _safe(fn, jid))
            # A reminder's action (2026-10-27), LAST: after the taint replay,
            # after the fired event and after the kind's own on_fire, so nothing
            # this row can influence has already run. ONLY an acting kind does
            # anything here: a display kind needs nothing, because both apps
            # draw the notice from the job's own `action`, which they read by
            # id. One occurrence spawns one card, and `_fire_action` keeps the
            # (id, due) pair it has asked about, so a retry inside this process
            # can never ask or run twice.
            if action_raw:
                fired_action = _decode_action(action_raw)
                if fired_action and fired_action["kind"] in ACTING_ACTION_KINDS:
                    self._spawn(lambda jid=jid, due=due: _safe_action(self, jid, due))
                elif not fired_action:
                    _audit("schedule.action_unreadable", {"id": jid})
        return [w[0] for w in went]

    def end(self, jid: str) -> bool:
        """ONE job with a rule is over before its end date - a "tell me
        when" that matched and was to tell only once. It is kept readable by
        id for FIRED_KEEP, like a job that went off, so an app can still read
        what it was. False when it is not on the list (deleted meanwhile)."""
        now = self.now()
        with self._lock, self._db() as c:
            row = self._row(c, jid)
            if row is None or row["state"] not in ("active", "paused"):
                return False
            c.execute("UPDATE jobs SET state = 'fired', due = NULL, fired_at = ?, "
                      "fired_due = NULL, late = 0, changed = ?, "
                      "resolved_at = COALESCE(resolved_at, ?) WHERE id = ?",
                      (now, now, now, jid))
        _audit("schedule.ended", {"id": jid, "kind": row["kind"]})
        self._changed(jid, row["kind"])
        return True

    def jobs_of(self, kind: str) -> list:
        """The ids of the jobs of one kind still on the list (active, paused
        or waiting for a card) - for a kind that manages its own one job
        (jarvis_tidy.py). Reads only."""
        with self._lock, self._db() as c:
            return [r["id"] for r in c.execute(
                "SELECT id FROM jobs WHERE kind = ? AND state IN ('active','paused','waiting')"
                " ORDER BY created", (str(kind),)).fetchall()]

    def next_due(self) -> Optional[float]:
        with self._lock, self._db() as c:
            r = c.execute("SELECT MIN(due) FROM jobs WHERE state = 'active' "
                          "AND due IS NOT NULL").fetchone()
        return float(r[0]) if r and r[0] is not None else None

    def poke(self) -> None:
        self._wake.set()

    def start(self) -> "Scheduler":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jarvis-schedule", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
                nxt = self.next_due()
            except Exception:
                # A bad row must not stop every other timer. Counted, so it
                # shows in status() rather than going silent.
                self.errors += 1
                nxt = None
            wait = TICK_MAX
            if nxt is not None:
                wait = max(0.2, min(TICK_MAX, nxt - self.now() + 0.05))
            self._wake.wait(wait)
            self._wake.clear()

    # ---- reading ----------------------------------------------------------------------

    def _view(self, row, now: float) -> dict:
        kind = row["kind"]
        rule = json.loads(row["rule"]) if row["rule"] else None
        v = {"id": row["id"], "kind": kind, "text": row["text"], "state": row["state"],
             "due": row["due"], "created": row["created"], "source": row["source"],
             "repeats": bool(rule)}
        k = KINDS.get(kind)
        if row["state"] == "active" and row["due"] is not None:
            if k is not None and k.ends:
                # No time of its own: `due` is the day it ends, quietly.
                v["when"] = until_words(float(row["due"]))
            else:
                v["left"] = max(0.0, float(row["due"]) - now)
                v["when"] = when_words(float(row["due"]), now)
        if kind == "timer":
            v["duration"] = row["duration"]
            if row["state"] == "paused":
                v["left"] = float(row["left_s"] or 0.0)
        if rule and rule.get("until") and "when" in v and k is not None:
            # A window's next end, said as which end it is: "awake at 07:00
            # tomorrow", "on standby at 01:00 today".
            inside = in_window(rule, now)
            edge = k.edges[1] if inside else k.edges[0]
            if edge:
                tail = k.edges[2] if inside and len(k.edges) > 2 else ""
                v["when"] = f"{edge} at {v['when']}{tail}"
        if rule:
            # What a "tell me when" watches (a sender's name, a device) is in
            # the rule's `watch`, for the card and the checks. It is the
            # owner's own words, like `text`, which is what an app shows -
            # so it is not handed out a second time here, where the desktop's
            # hiding of the private lists (it blanks `text`) would miss it.
            watch = rule.get("watch") if isinstance(rule.get("watch"), dict) else None
            v["rule"] = {key: x for key, x in rule.items() if key != "watch"}
            if watch is not None:
                v["urgent"] = watch.get("urgent") is True
            v["repeat"] = rule_words(rule)
            base = now if row["state"] != "active" or row["due"] is None else float(row["due"]) - 1
            try:
                v["next"] = next_runs(rule, base)
            except Exception:
                v["next"] = []
        if row["state"] == "waiting":
            v["card"] = "Waiting for your yes on the approval card."
        if row["fired_at"] is not None and row["state"] in ("fired", "active") and (
                kind != "todo" or row["fired_due"] is not None):
            v["fired_at"] = row["fired_at"]
            # How long ago it went off, by the PC's own clock: an app that
            # only has to show "went off 3 minutes ago" needs no clock of its
            # own (the phone's and the PC's can disagree).
            v["age_s"] = max(0.0, now - float(row["fired_at"]))
            v["late"] = bool(row["late"])
            v["went_off_at"] = clock(float(row["fired_at"]))
            if row["late"] and row["fired_due"] is not None and not (k is not None and k.silent):
                # A silent kind's late look (the PC slept) is just a look
                # made later - there is nothing the owner missed.
                v["missed"] = f"missed at {clock(float(row['fired_due']))}"
        if kind == "todo":
            # "" is the to-do list itself; a name is a named list ("shopping").
            v["list"] = row["list_name"] or ""
            # The day it was written, and how old that is in the owner's own
            # words (2026-11-02). `carry` is absent for an item written today
            # and for one with no usable day - so old payloads grow no keys they
            # did not have, and today's item never says "from today".
            try:
                created_date = str(row["created_date"] or "")
            except (IndexError, KeyError):
                created_date = ""
            if not _day_date(created_date):
                try:
                    stamp = float(row["created"])
                except (TypeError, ValueError):
                    stamp = 0.0
                created_date = (_day_of(stamp) if stamp > 0 else "") or _day_of(now)
            v["created_date"] = created_date
            carry = carry_words(created_date, now)
            if carry:
                v["carry"] = carry
        if row["snooze_of"]:
            v["snoozed"] = True
        # Phase 2: a to-do's position within its list, a number (None for an
        # item written by an old build before the backfill ran, and for every
        # kind that is not on a list). Apps can draw Up/Down from it.
        try:
            rank = row["rank"]
        except (IndexError, KeyError):
            rank = None
        v["rank"] = int(rank) if rank is not None else None
        try:
            ready_at = row["ready_for_review"]
        except (IndexError, KeyError):
            ready_at = None
        if ready_at:
            v["ready_for_review"] = True
            v["ready_at"] = float(ready_at)
            v["ready_said"] = READY_SAID
            # D-1.4 gate: the marker never means done. Said as a field too, so
            # an app/test can assert the owner-only rule without reading state.
            v["done"] = False
        v["lock_screen"] = k.lock_screen if k else "Jarvis: something is due."
        # A reminder's ONE action (2026-10-27). Handed out only when it decodes
        # to a known kind and exactly its one payload key, so a row without one
        # grows NO key at all and an old payload is byte for byte what it was.
        # `action_problem` is the second check (DESIGN section 3.4), and only on
        # a row that has already gone off: the file may have moved, or its
        # folder been removed from Settings since. One plain sentence, and the
        # Open button is then not drawn - the owner is never invited to press
        # something that cannot work. A damaged action is never handed out;
        # `action_unreadable` says so in one boolean, so a client can say one
        # line instead of pretending there was nothing there.
        try:
            raw_action = row["action"]
        except (IndexError, KeyError):
            raw_action = None
        if raw_action:
            action_here = _decode_action(raw_action)
            if action_here:
                v["action"] = action_here
                if row["fired_at"] is not None:
                    problem = _action_problem(action_here)
                    if problem:
                        v["action_problem"] = problem
            else:
                v["action_unreadable"] = True
        # An `ask` reminder's own answer log (2026-11-02), oldest first. Handed
        # out only when there is one, so every other row - and every row written
        # before this - grows NO key at all: the same additive contract `action`
        # keeps. Each entry is one tap: when (by the PC's clock), the owner's
        # label, what that button did and what was written.
        try:
            raw_answers = row["answers"]
        except (IndexError, KeyError):
            raw_answers = None
        kept_answers = _decode_answers(raw_answers)
        if kept_answers:
            v["answers"] = kept_answers
        if v.get("action", {}).get("kind") == ASK_KIND:
            # A question is worth being asked and answered: both apps draw its
            # buttons, and `answers` may be absent (nothing pressed yet) - so
            # the marker says the PC can take an answer, which is the one thing
            # an older backend cannot do. The same reason `actions`/`phase2`
            # exist: an older PC would silently drop the route's verb.
            v["asks"] = True
        # GTD-1 (2026-10-18): additive, and only when there is something to
        # say - an old row (or a plain timer/alarm) grows no keys, so every
        # payload and every old test is byte-for-byte what it was. The bundle's
        # WORDS are deliberately NOT handed out here: `has_context` says one
        # exists, and `enrich_and_check_condition()` is the one read path,
        # because that is where hide-memory-lists and App lock are honoured.
        try:
            trigger = row["trigger"]
        except (IndexError, KeyError):
            trigger = None
        if trigger and trigger != "time":
            v["trigger"] = trigger
        try:
            count = int(row["snooze_count"] or 0)
        except (TypeError, ValueError, IndexError, KeyError):
            count = 0
        if count:
            v["snooze_count"] = count
        try:
            kind_of_condition = row["condition_kind"]
        except (IndexError, KeyError):
            kind_of_condition = None
        # Only the two known conditions are ever handed out, and the target
        # only when it is a clean NAME: never a raw path or web address (F4 -
        # the same rule that keeps `rule["watch"]` out of this payload,
        # because the desktop's hiding of private lists only blanks `text`).
        if kind_of_condition in CONDITION_KINDS:
            v["condition_kind"] = str(kind_of_condition)
            target = _safe_condition_target(row["condition_target"])
            if target:
                v["condition_target"] = target
        # GTD-1: the bundle's WORDS are deliberately not handed out here.
        # `has_context` says a real packet exists, and
        # `enrich_and_check_condition()` is the one read path, because that is
        # where hide-memory-lists and App lock are honoured. GTD-1 follow-up
        # (2026-10-18): when the packet was dropped rather than stored because
        # it could not be scrubbed, the ONE additive key is the plain boolean
        # `context_dropped_unscrubbed` - never a word, an id or a hash of it
        # (Gemini's Q2 ruling: a hash would be a secret oracle). `has_context`
        # is NOT set in that case: there is no context to hand out.
        try:
            raw_bundle = row["context_bundle"]
        except (IndexError, KeyError):
            raw_bundle = None
        bundle_here = _decode_bundle(raw_bundle) if raw_bundle else {}
        if bundle_here.get(CONTEXT_DROPPED) is True:
            v[CONTEXT_DROPPED] = True
        if any(bundle_here.get(key) for key in BUNDLE_CONTENT_KEYS):
            v["has_context"] = True
        if k is not None and not k.notify:
            v["notify"] = False
        if k is not None and k.note is not None:
            try:
                said = str(k.note(row["id"]) or "")
            except Exception:
                said = ""
            if said:
                v["note"] = said
        if k is not None and k.fields is not None:
            try:
                extra = k.fields(row["id"]) or {}
            except Exception:
                extra = {}
            for key, x in extra.items():
                # A kind adds fields; it never replaces the scheduler's own.
                if key not in v:
                    v[key] = x
        return v

    def job(self, jid: str) -> Optional[dict]:
        with self._lock, self._db() as c:
            row = self._row(c, jid)
        return None if row is None else self._view(row, self.now())

    def bundle(self, jid: str) -> dict:
        """GTD-1: ONE reminder's stored context packet, {} for none.

        The scheduler's own read path hands out no bundle words (see `_view`);
        this is the backend door a caller that has already checked its own
        hide-memory-lists / App lock flags uses, one row at a time.

        GTD-1 follow-up (2026-10-18): a packet dropped because the scrubber
        was missing or raising reads as `{CONTEXT_DROPPED: True}` - the plain
        boolean and nothing else. There is no hash of the dropped words, on
        purpose: it would be a secret oracle and useless to the owner."""
        with self._lock, self._db() as c:
            row = c.execute("SELECT context_bundle FROM jobs WHERE id = ?",
                            (str(jid),)).fetchone()
        return _decode_bundle(row["context_bundle"]) if row is not None else {}

    def set_bundle(self, jid: str, bundle: Optional[dict]) -> bool:
        """Replace ONE reminder's context packet (None/{} clears it). False
        when the job is gone. Scrubbed on the way in, like `add_at`."""
        clean = scrub_context_bundle(bundle) if bundle else {}
        with self._lock, self._db() as c:
            cur = c.execute("UPDATE jobs SET context_bundle = ?, changed = ? WHERE id = ?",
                            (json.dumps(clean) if clean else None, self.now(), str(jid)))
            return cur.rowcount > 0

    def listed(self) -> list:
        now = self.now()
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE kind != 'todo' AND state IN "
                             "('active','paused','waiting')").fetchall()
        out = [self._view(r, now) for r in rows if KINDS.get(r["kind"], None) is None
               or KINDS[r["kind"]].owner_listed]

        def key(v):
            if v["state"] == "active" and v.get("due") is not None:
                return (0, v["due"])
            if v["state"] == "paused":
                return (1, v.get("left") or 0)
            return (2, v["created"])
        return sorted(out, key=key)

    def todos(self) -> list:
        now = self.now()
        with self._lock, self._db() as c:
            rows = c.execute("SELECT * FROM jobs WHERE kind = 'todo' AND state IN "
                             "('active','paused') ORDER BY (rank IS NULL), rank, "
                             "created, rowid").fetchall()
        return [self._view(r, now) for r in rows]

    def timers(self) -> list:
        return [j for j in self.listed() if j["kind"] == "timer"]

    def status(self) -> dict:
        now = self.now()
        todo = self.todos()
        return {# Phase 2 (2026-10-22): ONE additive boolean capability marker -
                # a newer UI hides edit/move/reorder controls when it is absent
                # (an older backend), and every old client ignores it.
                "available": True, "phase2": True,
                # A reminder's action (2026-10-27): the same kind of marker, for
                # the same reason. `handle_add` pulls only the keys it knows, so
                # an older backend would SILENTLY DROP an `action` and the owner
                # would get a reminder that opens nothing - the one dangerous
                # direction. A newer UI therefore hides the whole "Then" block
                # when this is absent and says why, and every old client ignores
                # the key. The same contract `phase2` has.
                "actions": True,
                # A reminder that ASKS (2026-11-02): the same kind of marker, for
                # the same reason. An older backend refuses an `ask` block at save
                # time (so the owner is told, rather than getting a reminder with
                # a question nothing can draw), but an older backend ALSO has no
                # `answer` verb - so a newer UI hides the buttons unless the PC
                # says `asks: true`, and every old client ignores the key.
                "asks": True, "now": now, "tz": _tz_name(now),
                "jobs": self.listed(), "todo": todo,
                # The to-do list's own day (2026-11-02): which mode is in
                # force, the two modes in the owner's words for the Settings
                # switch, and - for the day-labelled one - the same open items
                # grouped by the day they were written. `todo` itself is
                # UNCHANGED in both modes: the flat list, in the PC's order, with
                # `created_date` and (when it is older than today) `carry` on
                # each item. An app from before this ignores all three keys.
                "todo_mode": self.todo_mode(),
                "todo_modes": [dict(m) for m in TODO_MODE_WORDS],
                "todo_days": _todo_days(todo, now),
                # 2026-09-25: what went off in the last hour (Snooze), and
                # the named lists. An app from before them ignores both.
                "went_off": self.went_off(now), "lists": self.lists(),
                "running": self.running, "limits": {
                    "text": MAX_TEXT, "jobs": MAX_JOBS, "todo": MAX_TODO,
                    "timer_seconds": MAX_TIMER, "min_every_hours": MIN_EVERY_HOURS,
                    "lists": MAX_LISTS, "snooze_seconds": SNOOZE_DEFAULT}}

    # ---- "this sentence set a reminder" (for the learner) ------------------------------

    def mark_command(self, text: str) -> None:
        """Remember THAT this sentence was a command to the scheduler - its
        digest, never its words - so the learner does not read it for facts."""
        if not str(text or "").strip():
            return
        with self._lock, self._db() as c:
            c.execute("INSERT OR REPLACE INTO commands (digest, at) VALUES (?, ?)",
                      (_digest(text), self.now()))

    def was_command(self, text: str) -> bool:
        with self._lock, self._db() as c:
            return c.execute("SELECT 1 FROM commands WHERE digest = ?",
                             (_digest(text),)).fetchone() is not None


def _safe(fn: Callable[[str], None], jid: str) -> None:
    try:
        fn(jid)
    except Exception:
        pass


def _safe_action(sched, jid: str, due: float) -> None:
    """A reminder's fire-time action card, on its own thread. Nothing it raises
    reaches the tick loop - the same rule a kind's `on_fire` has, and for the
    same reason: a card that waits fifteen minutes must never stop the clock."""
    try:
        sched._fire_action(jid, due)
    except Exception:
        pass


def _tz_name(now: float) -> str:
    try:
        lt = time.localtime(now)
        return str(time.tzname[1 if lt.tm_isdst > 0 else 0])
    except Exception:
        return ""


# --------------------------------------------------------------------------
#   The one scheduler this backend runs
# --------------------------------------------------------------------------

_SCHED: Optional[Scheduler] = None
_SCHED_LOCK = threading.Lock()

#: How long, at exit, to wait for the scheduler's loop and its after-start
#: jobs to notice and stop. Bounded on purpose: an after-start job can be
#: waiting on something this PC has switched off (a plug-in program, a
#: window), and a process that will not exit is worse than the risk below.
EXIT_JOIN_SECONDS = 2.0

#: The after-start jobs that are running right now, so exit can wait for them
#: (see `_on_exit`). Nothing else reads it.
_AFTER_START_RUNNING: list = []


def _on_exit() -> None:
    """Stop this process's own threads before the interpreter tears itself
    down, and wait - briefly - for them to finish.

    WHY. The scheduler's loop and an after-start job are daemon threads: the
    interpreter exits without waiting for them, so one can be inside a
    `sqlite3` call (or anywhere else in a C extension) when the process is
    already going away. A test suite that starts the scheduler and simply
    ends - `test_find_phone.py` does, through `jarvis_quick.answer()` - then
    dies at teardown with the C++ runtime's "terminate called without an
    active exception" and SIGABRT, after every one of its checks has already
    printed "ok". That is the unexplained one-in-four flake recorded in
    docs/HANDOFF-2026-10-05-tutorials-and-ci.md section 2.2, and it is a
    property of this module: it is the part that starts threads and never
    stopped them.

    This is not a way of hiding an error: nothing is caught and nothing is
    suppressed. It stops the loop the way `Scheduler.stop()` and
    `test_briefing.py` already do, it runs after the interpreter's own
    `threading._shutdown()` (which only waits for non-daemon threads), and it
    does nothing at all when the scheduler was never started (the usual case
    in a suite).

    Safe at exit: `Scheduler.stop()` only sets an Event, wakes the loop and
    joins it. Nothing here calls into sqlite or prints.
    """
    sched = _SCHED
    if sched is not None:
        try:
            sched.stop(EXIT_JOIN_SECONDS)
        except Exception:
            pass
    with _SCHED_LOCK:
        running = list(_AFTER_START_RUNNING)
    for t in running:
        if t.is_alive():
            try:
                t.join(EXIT_JOIN_SECONDS)
            except Exception:
                pass


atexit.register(_on_exit)


#: Called once, on their own thread, after the scheduler first starts in
#: this process (after_start). For a kind that keeps ONE job of its own in
#: step with a setting (jarvis_tidy.py: the overnight tidy's look, only
#: while its switch is on) - it cannot add that job while get() is still
#: importing it.
_AFTER_START: list = []


def after_start(fn: Callable[[], None]) -> None:
    """Run `fn()` once the scheduler has started (at once, on its own
    thread, when it already has). Nothing it raises reaches anyone."""
    _AFTER_START.append(fn)
    if _SCHED is not None and _SCHED.running:
        _start_after_start(fn)


def _start_after_start(fn: Callable[[], None]) -> None:
    """One after-start job on its own thread, remembered until it has
    finished so exit can wait for it (`_on_exit`)."""
    def run() -> None:
        try:
            _safe(lambda _j: fn(), "")
        finally:
            with _SCHED_LOCK:
                if t in _AFTER_START_RUNNING:
                    _AFTER_START_RUNNING.remove(t)

    t = threading.Thread(target=run, daemon=True, name="jarvis-schedule-after-start")
    with _SCHED_LOCK:
        _AFTER_START_RUNNING.append(t)
    t.start()


def get() -> Scheduler:
    """The scheduler, started. Every way in comes through here - the boot
    line in jarvis_hud.py, the routes, the fast path, the model's tools - so
    whichever is first starts the loop, once."""
    global _SCHED
    first = False
    with _SCHED_LOCK:
        if _SCHED is None:
            _load_kind_modules()
            _SCHED = Scheduler()
            first = True
        s = _SCHED
    s.start()
    if first:
        for fn in list(_AFTER_START):
            _start_after_start(fn)
    return s


def _load_kind_modules() -> None:
    import importlib
    for name in KIND_MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            pass


def start() -> Scheduler:
    return get()


def set_todo_mode_here(mode) -> str:
    """Change the to-do list's mode from THIS process, and return the one now in
    force (2026-11-02).

    This is the ONE door the settings registry calls
    (`jarvis_settings_registry.set_todo_carryover`), so a sentence typed or
    spoken at Jarvis, the Settings switch on either app and
    POST /api/schedule/act {"do": "todo_mode"} all end at the same method - they
    cannot disagree about the state. ValueError for anything that is not one of
    the two modes."""
    return get().set_todo_mode(mode)


def was_command(text: str) -> bool:
    """For jarvis_intake.owner_turns: did this sentence set a job? False on
    any failure - the other checks there still run."""
    try:
        s = _SCHED
        if s is None:
            # Not started in this process (a test, a tool): read the file if
            # there is one, and start nothing.
            if not db_path().is_file():
                return False
            s = Scheduler()
        return s.was_command(text)
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Routes (schedule.patch hands the request here)
# --------------------------------------------------------------------------

def handle_get(query="") -> tuple:
    """GET /api/schedule - the list; ?id=<id> - one job, even one that went
    off in the last day (the apps read a notification's words this way).
    `query` is the raw query string, or a dict already parsed."""
    if isinstance(query, str):
        from urllib.parse import parse_qs
        query = {k: v[0] for k, v in parse_qs(query).items() if v}
    s = get()
    jid = (query or {}).get("id")
    if isinstance(jid, list):
        jid = jid[0] if jid else None
    if jid:
        v = s.job(str(jid))
        if v is None:
            return 404, {"ok": False, "reason": "no_such_job",
                         "error": "That is not on the list any more."}
        return 200, {"available": True, "job": v}
    return 200, s.status()


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def handle_mode(body: dict) -> tuple:
    """The to-do list's ONE mode (2026-11-02), through POST /api/schedule/act.

    Body: {"do": "todo_mode", "mode": "rollover" | "day"}. Nothing else is
    taken: one value, no items, no times. No approval card either way - it
    changes how the owner's own list is DRAWN and touches no item: no row is
    moved, copied, deleted or re-stamped, so there is nothing to ask about and
    nothing to undo.

    It rides `/api/schedule/act` rather than a route of its own on purpose: the
    one scheduler keeps ONE write door for changes that need no card (the same
    choice `clear_list` made), and adding a route to `jarvis_hud.py` here would
    have re-anchored two later patches' invented pre-images in the patch-stack
    audit (`tools/check_patch_original_text.py`) for no gain to the owner."""
    body = body if isinstance(body, dict) else {}
    try:
        mode = get().set_todo_mode(body.get("mode"))
    except ValueError as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    except Exception as exc:                       # noqa: BLE001 - code only
        return 503, {"ok": False, "error": type(exc).__name__}
    said = ("Today's list is everything still open, and each item says how old it is."
            if mode == TODO_MODE_ROLLOVER else
            "Each day keeps its own list now. Nothing was moved and nothing was lost.")
    return 200, {"ok": True, "mode": mode, "said": said,
                 "todo_modes": [dict(m) for m in TODO_MODE_WORDS]}


def wall_at(date, hhmm) -> float:
    """The moment this PC's clock reads `date` ("2026-10-12") at `hhmm`
    ("14:00"). ValueError, in words, for anything else."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(date or "").strip())
    if not m:
        raise ValueError("a date looks like 2026-10-12")
    y, mo, d = (int(g) for g in m.groups())
    try:
        import datetime
        datetime.date(y, mo, d)
    except ValueError:
        raise ValueError("that date is not on the calendar")
    t = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(hhmm or "").strip())
    if not t:
        raise ValueError("a time looks like 14:00")
    return wall_to_epoch(y, mo, d, int(t.group(1)), int(t.group(2)))


def handle_add(body: dict) -> tuple:
    """POST /api/schedule/add - one job.
      {"kind": "todo", "text", "list"?}            a to-do item (on a named list)
      {"kind": "timer", "seconds", "text"?}        a timer
      {"kind": "alarm"|"reminder", "at", "text"?}  once, at an epoch time
      {"kind": "alarm"|"reminder", "date": "YYYY-MM-DD", "time": "HH:MM", "text"?}
                                                   once, on this PC's clock ("said")
      {"kind": "alarm"|"reminder", "repeat": {...}, "text"?}   repeating: no card
      {"kind": "standby", "repeat": {"every", "at", "until"}}  no card
      {"kind": "briefing", "repeat": {...}}        repeating: ONE card
      {"kind": "reminder", ..., "action": {"kind": "open-webpage", "url": "https://..."}}
                                                   a reminder that opens something,
                                                   or asks to run one task at its time
    200 {"ok", "job"} (a plain repeat also has `said`, with its next times),
    202 {"ok", "waiting": true, "job"} for a repeat that waits for its card."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    kind = str(body.get("kind") or "").strip().lower()
    s = get()
    if kind in KINDS and KINDS[kind].add is not None:
        # A kind with its own way in ("tell me when", jarvis_tellme.add_route):
        # it checks its own body and ends in add_repeat - ONE card.
        return KINDS[kind].add(body)
    try:
        if kind == "todo":
            job = s.add_todo(body.get("text"), source="app", list_name=body.get("list"))
        elif kind == "timer":
            job = s.add_timer(_num(body.get("seconds")), body.get("text") or "", source="app")
        elif _repeatable(kind):
            # An alarm, a reminder, or a later kind that may repeat (the
            # morning briefing, from its settings in either app).
            if body.get("repeat") is not None:
                job = s.add_repeat(kind, body.get("repeat"), body.get("text") or "",
                                   source="app",
                                   action=body.get("action") if kind == "reminder" else None)
                return _repeat_answer(job, s.now())
            if kind in ("alarm", "reminder") and ("date" in body or "time" in body):
                # "Photo to reminder" (2026-09-28, JARVIS-API section 83):
                # the owner's edited date and time, read as THIS PC's clock
                # - the PC is Jarvis's only clock - and set by the owner's
                # tap, with no card, like any one-off reminder.
                at = wall_at(body.get("date"), body.get("time"))
                now = s.now()
                if at <= now:
                    raise ValueError(f"{when_words(at, now)} has already passed - "
                                     f"change the date or time")
                job = s.add_at(kind, at, body.get("text") or "", source="app",
                               **(_reminder_extras(body) if kind == "reminder" else {}))
                noun = "Alarm" if kind == "alarm" else "Reminder"
                return 200, {"ok": True, "job": job,
                             "said": f"{noun} set for {when_words(at, now)}."}
            job = s.add_at(kind, _num(body.get("at")), body.get("text") or "", source="app",
                           **(_reminder_extras(body) if kind == "reminder" else {}))
        elif kind in KINDS and KINDS[kind].window:
            # The standby schedule: {"kind": "standby", "repeat": {"every":
            # "day", "at": "01:00", "until": "07:00"}}. Since 2026-09-26 it is
            # set up at once, with no card (Kind.plain_repeat).
            if not isinstance(body.get("repeat"), dict):
                return 400, {"ok": False, "error": f"A {KINDS[kind].noun} needs its two times."}
            job = s.add_repeat(kind, body.get("repeat"), "", source="app")
            return _repeat_answer(job, s.now())
        else:
            names = ["todo", "timer", "alarm", "reminder"] + sorted(
                n for n, k in KINDS.items() if k.window or k.repeatable)
            return 400, {"ok": False, "error": "kind is one of: " + ", ".join(names)}
    except OverflowError as exc:
        return 409, {"ok": False, "error": _sentence(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    return 200, {"ok": True, "job": job}


#: A repeat that waits for its card (the briefing): the apps' words.
WAITS_FOR_CARD = "It repeats, so it waits for your yes on the card."


def _repeat_answer(job: dict, now: float) -> tuple:
    """(code, body) for a repeat just added: 202 {"waiting": true} while its
    card is up (the briefing), 200 with the next times in `said` for a plain
    repeat set up at once (2026-09-26, no card)."""
    if job.get("state") == "waiting":
        return 202, {"ok": True, "waiting": True, "job": job, "said": WAITS_FOR_CARD}
    return 200, {"ok": True, "waiting": False, "job": job, "said": repeat_set_words(job, now)}


def handle_act(body: dict) -> tuple:
    """POST /api/schedule/act - ONE job.

    {"id", "do", "seconds"?}: pause, resume, delete, done, add_time, snooze.
    Phase 2 (2026-10-22) adds three verbs, each ONE job with the same checks:
    {"id", "do": "edit", "text"?, "when"?, "date"?+"time"?, "at"?,
     "repeat"?, "list"?, "seconds"?} - change the words / a one-off's own time
     (cardless) / repeat (ONE card, old rule active until approved) / a to-do's
    list; {"id", "do": "move", "list"?} - a to-do to a named list or null for
    the to-do list; {"id", "do": "reorder", "rank"?|"before"?|"after"?} - a
    to-do's position within its list. Two forms are not one job:
    {"do": "clear_list", "list", "count"} - one NAMED list, cleared after the
    app's "are you sure?" - and, since 2026-11-02,
    {"do": "todo_mode", "mode": "rollover"|"day"} - which way the to-do list is
    shown (see `handle_mode`). A third is not a change at all: since 2026-11-02
    {"do": "answer", "id", "button": <index>, "source"?} presses ONE button of
    ONE `ask` reminder and logs the answer (see `Scheduler.answer`). It needs no
    card and decides nothing - an answer is a log line, like ticking a to-do -
    so the token and origin checks this route already makes are the whole gate.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    verb = str(body.get("do") or "").strip().lower()
    if verb == "todo_mode":
        # The second form that is not one job (2026-11-02, the owner's choice):
        # the to-do list's own mode. It moves no item, deletes nothing and
        # re-stamps no day, so it rides this route rather than opening a second
        # write door to the one scheduler - the same reason `clear_list` is the
        # first such form.
        return handle_mode(body)
    if verb == "clear_list":
        # The one form that is not one job: every item on ONE named list,
        # after the app's "are you sure?", and only when `count` matches what
        # the app showed (Scheduler.clear_list). Never the to-do list.
        return get().clear_list(body.get("list"), body.get("count"))
    if verb == "answer":
        # The third form that is not one job, and the only one that is not a
        # CHANGE: one button of one `ask` reminder, pressed (2026-11-02).
        #
        # It rides this route for the same reason `clear_list` and `todo_mode`
        # do - one scheduler, ONE write door - and because a route of its own
        # in jarvis_hud.py would re-anchor two later patches' invented
        # pre-images in the patch-stack audit for no gain. Nothing here acts:
        # an answer is a log line, cardless like ticking a to-do, so the token
        # and origin checks this route already makes are the whole gate.
        jid = body.get("id")
        if not isinstance(jid, str) or not re.fullmatch(r"s[0-9a-f]{10}", jid):
            return 400, {"ok": False, "error": "need one job id"}
        return get().answer(jid, body.get("button"), source=str(body.get("source") or "app"))
    jid = body.get("id")
    if not isinstance(jid, str) or not re.fullmatch(r"s[0-9a-f]{10}", jid):
        return 400, {"ok": False, "error": "need one job id"}
    return get().act(jid, body.get("do"), _num(body.get("seconds")), fields=body)


def _sentence(exc: BaseException) -> str:
    t = str(exc).strip() or type(exc).__name__
    return t[0].upper() + t[1:] + ("" if t.endswith(".") else ".")


# --------------------------------------------------------------------------
#   A reminder's action (2026-10-27)
# --------------------------------------------------------------------------
# One reminder, one action; the target is a URL, a file on the allow-list, a
# note, or a name from the closed list. Validation happens HERE, when the
# reminder is saved, and again when the target is used: the row is plain
# SQLite on the owner's own disk, and anything on that PC can edit it. The
# rules are DESIGN section 3.2 and 3.4; the tests are
# `backend/test_schedule_actions.py`.

def _documents():
    """`jarvis_documents` - the module that owns "a folder Jarvis may look in" -
    or None when it is not beside this file.

    Missing is refused rather than guessed at: the allow-list is a security
    boundary, and a boundary this module cannot read is one it must not invent.
    On the owner's PC it is SHIPPED beside `jarvis_hud.py`, and `_path_problem`
    fails closed without it."""
    try:
        import jarvis_documents
        return jarvis_documents
    except Exception:
        return None


def _url_problem(url) -> str:
    """'' when this is a web address a reminder may open, else one sentence.

    https ONLY, though the desktop's own opener also allows http
    (`validate_external_url`): an address written once and opened for months is
    not the same risk as a link the owner just clicked in an answer, and a
    plain-http page is the one an attacker on the same cafe Wi-Fi can rewrite.
    The same checks are made again by the desktop at the moment of opening."""
    if not isinstance(url, str) or not url.strip():
        return "Pick a web address first, or choose Nothing."
    url = url.strip()
    if len(url) > MAX_ACTION_URL:
        return f"A web address can be up to {MAX_ACTION_URL} characters."
    if not url.lower().startswith("https://"):
        return NOT_HTTPS
    # Whitespace and control characters are how an argument becomes two, and
    # how a URL stops being the one that was shown on the row.
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return NOT_HTTPS
    host = url.split("//", 1)[1].split("/")[0].split("?")[0].split("#")[0] \
        if "//" in url else ""
    # `https://github.com@evil.example/` has a host of `evil.example`; the part
    # before the `@` is userinfo and every resolver ignores it. A backslash is
    # folded to `/` by the URL parser, so it could hide the real host.
    if not host or "@" in host or "\\" in url:
        return NOT_HTTPS
    return ""




def _protection():
    """jarvis_protection, or None when a half-deployed install lacks it.

    The protection list is a shipped module, so on a normal backend this is
    always the real one. A missing copy means the feature is not installed at
    all (an older install): the caller then behaves exactly as it did before,
    which is the same direction every other optional module here takes.
    """
    try:
        import jarvis_protection
        return jarvis_protection
    except Exception:                                       # noqa: BLE001
        return None


def _path_problem(path) -> str:
    """'' when this file may be opened by a reminder, else one sentence.

    Two boundaries, in this order: the EXTENSION (so "open a file" can never
    become "start a program" - `.lnk`, `.exe`, a script or an `.html` page is
    never on `ACTION_FILE_EXTS`), then `jarvis_documents.allowed_path`, which
    resolves links and junctions and refuses a path outside every listed
    folder, a hidden folder on the way, a reserved Windows name and a
    protected place."""
    if not isinstance(path, str) or not path.strip():
        return "Pick a file first, or choose Nothing."
    path = path.strip()
    if len(path) > MAX_ACTION_PATH:
        return f"A file's path can be up to {MAX_ACTION_PATH} characters."
    if any(ord(c) < 32 for c in path):
        return NOT_IN_FOLDERS
    ext = os.path.splitext(path)[1].lower()
    if ext not in ACTION_FILE_EXTS:
        return NOT_A_FILE
    # Protected from Jarvis (2026-10-31): opening a blocked file is a read
    # and is refused; a read-only file may still be opened.
    _P = _protection()
    if _P is not None:
        _said = _P.path_refusal(path)
        if _said:
            return _said
    docs = _documents()
    if docs is None:
        return NOT_IN_FOLDERS
    got = docs.allowed_path(path)
    if not got:
        return NOT_IN_FOLDERS
    real = got[0] if isinstance(got, tuple) else path
    if not os.path.exists(real):
        return FILE_GONE
    return ""


def _note_problem(note) -> str:
    """'' when this is a note a reminder may show, else one sentence. Plain
    text, never parsed as HTML: the notice and the row set it with
    `textContent`, and the toast escapes it."""
    if not isinstance(note, str) or not note.strip():
        return "Write the note first, or choose Nothing."
    if len(note) > MAX_ACTION_NOTE:
        return f"A note is up to {MAX_ACTION_NOTE} characters."
    if note.count("\n") + 1 > MAX_ACTION_LINES:
        return f"A note is up to {MAX_ACTION_LINES} lines."
    if any(ord(c) < 32 and c not in "\n\t" for c in note):
        return "A note is plain words - that one has a character a note cannot hold."
    return ""


def _task_problem(task) -> str:
    """'' when a reminder may ask for this task, else one sentence.

    The closed list is two names and nothing else - never a program, a command
    or a path. `backup` is on the list and refused HERE, with the reason: a
    backup is locked with a fresh random recovery code that
    `jarvis_backup.generate_code` never writes to a file ("never kept by this
    module past the response that shows it once"), and a reminder that fired at
    07:00 has nobody to show it to. An archive nobody can open is worse than no
    archive, and putting the code in the card would write a credential to
    `approvals.db` in plain text. `briefing` has no such secret.
    """
    if not isinstance(task, str) or not task.strip():
        return "Pick what the reminder should do, or choose Nothing."
    task = task.strip()
    if task not in ACTION_TASKS:
        return ("Jarvis can put your briefing together. That is all a reminder can do "
                "on its own.")
    if task == "backup":
        return ("A reminder cannot make a backup: the file would be locked with a new "
                "recovery code and nothing would show it to you. Run Back up now from "
                "the Brain, and let the reminder remind you instead.")
    return ""


#: The one key each kind must carry, and the check that key must pass.
_ACTION_CHECKS = {"show-note": ("note", _note_problem),
                  "open-webpage": ("url", _url_problem),
                  "open-file": ("path", _path_problem),
                  "run-task": ("task", _task_problem)}


# ---- the `ask` block: checked when it is saved, and again when it is read -----
#
# The second door is the SAME function, on purpose: `_decode_ask` calls
# `_clean_ask` inside a try/except, so the rules the PC saves a question under
# and the rules it reads one back under can never drift apart - the two-check
# pattern section 21.11 already keeps for the other kinds.

#: The sentences, each ONE whole sentence, shown to the owner as it is.
ASK_NEEDS_BUTTONS = ("A question needs at least one button - that is what you press "
                     "when it goes off.")
ASK_NEEDS_DESTINATION = ("That button records the answer, so pick where: the reminder's "
                         "own history, today's Obsidian note, a goal or a habit.")
ASK_NO_LABEL = "Every button needs its words - write what it should say."
ASK_SAME_LABELS = ("Two buttons say the same thing, so there would be no way to tell which "
                   "one you pressed.")
_ASK_BAD_ID = ("A goal or a habit is named by its own id, like the one the Goals screen "
               "shows.")


def _ask_id(value, which: str) -> str:
    """A goal's or a habit's own id, checked as a NAME and nothing else.

    The id is handed to the module that owns the record (`jarvis_goals`,
    `jarvis_habits`); it is never a path and never a command. Its shape is
    checked here so a row edited by hand cannot smuggle free text into that
    call. Existence is deliberately NOT checked: a goal may be created after the
    reminder, and the write degrades with one sentence instead of refusing."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(_ASK_BAD_ID)
    text = str(value).strip()
    if not text or len(text) > 64 or not re.fullmatch(r"[A-Za-z0-9._:-]+", text):
        raise ValueError(_ASK_BAD_ID)
    return text


def _question_problem(q) -> str:
    """'' when this is a question a reminder may ask, else one sentence. Plain
    text, never parsed as HTML: the notice and the row set it with `textContent`
    and the phone puts it in a notification body."""
    if not isinstance(q, str) or not q.strip():
        return "Write the question first - it is what you will read when it goes off."
    if len(q) > MAX_ASK_QUESTION:
        return f"A question is up to {MAX_ASK_QUESTION} characters."
    if q.count("\n") + 1 > MAX_ASK_QUESTION_LINES:
        return f"A question is up to {MAX_ASK_QUESTION_LINES} lines."
    if any(ord(c) < 32 and c not in "\n\t" for c in q):
        return "A question is plain words - that one has a character it cannot hold."
    return ""


def _ask_label_problem(label) -> str:
    """'' when this is a button's label, else one sentence. A label is ONE line
    of the owner's own words: Android cuts a notification action's label at
    about twenty characters, so a longer one is refused rather than shown
    half-finished."""
    if not isinstance(label, str) or not label.strip():
        return ASK_NO_LABEL
    text = label.strip()
    if len(text) > MAX_ASK_LABEL:
        return f"A button's words are up to {MAX_ASK_LABEL} characters."
    if any(c in text for c in "\n\r\t"):
        return "A button's words are one line."
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return "A button's words are plain words - that one has a character it cannot hold."
    return ""


def _clean_button(raw) -> dict:
    """ONE button: its label and the one thing it does. ValueError, in one
    sentence, for anything else - never a program, a command or a webhook."""
    if not isinstance(raw, dict):
        raise ValueError(ASK_NO_ACT)
    problem = _ask_label_problem(raw.get("label"))
    if problem:
        raise ValueError(problem)
    does = raw.get("does")
    if not isinstance(does, str) or not does.strip():
        raise ValueError(ASK_NO_ACT)
    does = does.strip().lower()
    if does not in ASK_DOES:
        # Every refused verb gets the same sentence, and it names the three that
        # work. `open-file` / `open-webpage` are what the design asked for and
        # this build does not ship (see the ASK block above): the sentence says
        # so in plain words rather than pretending the request was understood.
        raise ValueError(ASK_NO_ACT)
    out = {"label": " ".join(str(raw["label"]).split()), "does": does}
    if does == "snooze":
        minutes = raw.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise ValueError("\"snooze\" needs how many minutes, as a whole number.")
        if minutes < ASK_SNOOZE_MIN or minutes > ASK_SNOOZE_MAX:
            raise ValueError(f"A snooze button is {ASK_SNOOZE_MIN} to {ASK_SNOOZE_MAX} "
                             f"minutes.")
        out["minutes"] = int(minutes)
    elif "minutes" in raw:
        # A button that does not snooze carries no time: a block that said both
        # would be one the app could not draw honestly.
        raise ValueError("Only a snooze button has minutes on it.")
    if set(raw) - {"label", "does", "minutes"}:
        raise ValueError(ASK_NO_ACT)
    return out


def _clean_record(raw, needed: bool) -> dict:
    """Where a `record` button writes: any combination of the four destinations,
    and never an id this build cannot pass to the module that owns the record."""
    if raw is None or raw == {}:
        if needed:
            raise ValueError(ASK_NEEDS_DESTINATION)
        return {}
    if not isinstance(raw, dict):
        raise ValueError(ASK_NEEDS_DESTINATION)
    if set(raw) - set(ASK_DESTINATIONS):
        raise ValueError(ASK_NEEDS_DESTINATION)
    out: dict = {}
    for key in ("history", "obsidian_daily"):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise ValueError(ASK_NEEDS_DESTINATION)
            if raw[key]:
                out[key] = True
    # `goal` and `habit` carry an id; false, "" and None all mean "not this one".
    for key in ("goal", "habit"):
        if key in raw and raw[key] not in (None, "", False):
            out[key] = _ask_id(raw[key], key)
    if needed and not out:
        raise ValueError(ASK_NEEDS_DESTINATION)
    return out


def _clean_ask(raw) -> dict:
    """A reminder's `ask` block, checked and normalised. ValueError in one plain
    sentence for anything else. Called when the reminder is SAVED (`add_at` /
    `add_repeat`) and again when it is READ (`_decode_ask`)."""
    if set(raw) - ASK_BLOCK_KEYS:
        raise ValueError(_NO_ACTION_KIND)
    problem = _question_problem(raw.get("question"))
    if problem:
        raise ValueError(problem)
    buttons = raw.get("buttons")
    if not isinstance(buttons, list) or not buttons:
        raise ValueError(ASK_NEEDS_BUTTONS)
    if len(buttons) > MAX_ASK_BUTTONS:
        raise ValueError(f"A question has up to {MAX_ASK_BUTTONS} buttons - Android shows "
                         f"three, and your PC draws the same three.")
    clean = [_clean_button(b) for b in buttons]
    labels = [b["label"].lower() for b in clean]
    if len(set(labels)) != len(labels):
        raise ValueError(ASK_SAME_LABELS)
    record = _clean_record(raw.get("record"), any(b["does"] == "record" for b in clean))
    action = {"kind": ASK_KIND,
              # The owner's own words, with Windows line endings folded, and no
              # outer blank lines: the same tidy a `show-note` gets.
              "question": raw["question"].replace("\r\n", "\n").replace("\r", "\n").strip(),
              "buttons": clean}
    if record:
        action["record"] = record
    if len(json.dumps(action)) > MAX_ACTION_BYTES:
        raise ValueError("That is too much to keep with one reminder.")
    return action


def _decode_ask(got: dict) -> dict:
    """The stored `ask` block, or {} when anything about it is wrong.

    Never raises, and it is the SAME check the save door uses - so a row edited
    on the owner's own disk reads as "that reminder's action could not be read",
    fires as an ordinary reminder and offers no buttons, rather than handing an
    app a half-valid block."""
    try:
        return _clean_ask(got)
    except (ValueError, TypeError, KeyError):
        return {}


def _clean_action(raw) -> Optional[dict]:
    """A reminder's action, checked and normalised - None when there is none.

    ValueError, in one plain sentence, for anything that is not exactly one
    kind and its own keys: no extra keys, no free text, no unknown kind.
    Called from `add_at` and `add_repeat` (the two ways a reminder is made), so
    a bad target is refused before a row exists."""
    if raw is None or raw == "" or raw == {}:
        return None
    if not isinstance(raw, dict):
        raise ValueError(_NO_ACTION_KIND)
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in ACTION_KINDS:
        raise ValueError(_NO_ACTION_KIND)
    if kind == ASK_KIND:
        return _clean_ask(raw)
    key, check = _ACTION_CHECKS[kind]
    extra = set(raw) - {"kind", key}
    if extra:
        # Exactly one payload key per kind, and no other keys at all: a block
        # that carried two targets would be one the client could not draw and
        # this code would have to guess which one to use.
        raise ValueError(_NO_ACTION_KIND)
    if key not in raw:
        raise ValueError(_NO_ACTION_KIND)
    value = raw.get(key)
    problem = check(value)
    if problem:
        raise ValueError(problem)
    value = value if key == "note" else value.strip()
    if key == "note":
        value = value.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    action = {"kind": kind, key: value}
    if len(json.dumps(action)) > MAX_ACTION_BYTES:
        raise ValueError("That is too much to keep with one reminder.")
    return action


def _decode_action(raw) -> dict:
    """The stored action, or {} for anything that is not a JSON object with a
    known kind and exactly its own keys.

    Never raises: a row is plain SQLite on the owner's own disk and anything on
    that PC can edit it, so a damaged action must fire as an ordinary reminder
    (its words, its notice, its toast) and open nothing (`_view` adds
    `action_unreadable` and `tick` audits the id only)."""
    if not raw:
        return {}
    try:
        got = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}
    if not isinstance(got, dict):
        return {}
    kind = got.get("kind")
    if not isinstance(kind, str) or kind not in ACTION_KINDS:
        return {}
    if kind == ASK_KIND:
        return _decode_ask(got)
    key = ACTION_PAYLOAD[kind]
    if set(got) != {"kind", key}:
        return {}
    if not isinstance(got[key], str) or not got[key].strip():
        return {}
    return {"kind": kind, key: got[key]}


#: The plain words for each task, for the card and the HUD's help line.
_TASK_WORDS = {"briefing": "put your morning briefing together now",
               "backup": "run one backup"}


def _task_words(task: str) -> str:
    return _TASK_WORDS.get(str(task or ""), "do that")


def _action_problem(action: dict) -> str:
    """'' when a STORED action may still be used, else one plain sentence.

    The second of the two checks (DESIGN section 3.4): the file may have moved,
    been replaced by a shortcut, or the folder may have been removed from
    Settings since the reminder was saved. Reported on fired rows as
    `action_problem`, and the Open button is then not drawn - the owner is
    never invited to press something that cannot work.

    An `ask` block is deliberately always "" here. Its question and its buttons
    are its own words, and there is nothing outside the row for them to lose;
    the one thing that CAN go away is a destination another module owns (a goal
    deleted, a habit list that was never set up), and refusing the whole answer
    over that would throw away the log line the owner did press. So a
    destination that cannot be written is reported in the ANSWER's own sentence
    instead, after the tap - never by hiding the question."""
    if not action:
        return ""
    kind = action.get("kind")
    if kind == "open-webpage":
        return _url_problem(action.get("url"))
    if kind == "open-file":
        return _path_problem(action.get("path"))
    if kind == "show-note":
        return _note_problem(action.get("note"))
    if kind == "run-task":
        return _task_problem(action.get("task"))
    if kind == ASK_KIND:
        return ""
    return _NO_ACTION_KIND


# ---- what answering WRITES (2026-11-02) -------------------------------------
#
# Four destinations and one log line, and every way one of them can fail is ONE
# plain sentence rather than an exception. The two that belong to another module
# (`jarvis_goals`' progress log, `jarvis_habits`' tick) are called through a
# small, explicit interface and said to be "not set up" when this PC does not
# have them - a tree without those modules must never crash an answer, and must
# never quietly pretend it wrote something.


def _decode_answers(raw) -> list:
    """The stored answer log, oldest first, or [] for anything that is not a
    list of plain records. Never raises: a row edited by hand reads as no
    answers, which is the same direction every other read of that row takes."""
    if not raw:
        return []
    try:
        got = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(got, list):
        return []
    out = []
    for entry in got:
        if not isinstance(entry, dict):
            continue
        try:
            at = float(entry.get("at") or 0.0)
        except (TypeError, ValueError):
            continue
        if at <= 0:
            continue
        wrote = [str(x)[:40] for x in (entry.get("wrote") or [])
                 if isinstance(x, (str, int, float)) and not isinstance(x, bool)][:6]
        problems = [str(x)[:160] for x in (entry.get("problems") or [])
                    if isinstance(x, str)][:4]
        kept = {"at": at, "clock": str(entry.get("clock") or clock(at))[:8],
                "button": str(entry.get("button") or "")[:MAX_ASK_LABEL],
                "does": str(entry.get("does") or "")[:20], "wrote": wrote}
        if problems:
            kept["problems"] = problems
        out.append(kept)
    return out[-MAX_ANSWERS:]


def _join_words(items: list) -> str:
    """'a', 'a and b', 'a, b and c' - the same joining the rules use."""
    words = [str(x) for x in items if str(x)]
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def _answer_line(text: str, label: str, at: float) -> str:
    """The one plain line an answer writes: "10:00 — medication: Taken".

    The reminder's own words, a colon, and the owner's own button label - never
    an id, a code or the module's private state. Bounded so one long reminder
    cannot write a paragraph into a journal that Jarvis then has to read back."""
    subject = " ".join(str(text or "").split())[:80] or "reminder"
    return f"{clock(at)} — {subject}: {' '.join(str(label or '').split())[:MAX_ASK_LABEL]}"


def _wrote_words(wrote: list, problems: list) -> str:
    """What the owner reads after an answer: what was written, then every
    destination that could not be, each in its own sentence."""
    said = (f"Saved to {_join_words(wrote)}." if wrote else "Answered.")
    if problems:
        said = (said + " " + " ".join(problems)).strip()
    return said


def _write_daily_note(line: str, at: float) -> str:
    """'' when the line was appended to TODAY's Obsidian note, else one sentence.

    `jarvis_note_capture` is the module that already owns "add this to today's
    daily note": its own plan is worked out first (the vault, the daily-note
    path, the folder the note lives in, the protection list), and only then is
    it written with `approved=True` - because the tap IS the person. No card:
    an answer is a log line, and this is the same reasoning that lets an Open
    button open something with no card. Nothing leaves this PC."""
    try:
        import jarvis_note_capture as note_capture
    except Exception:
        return JOURNAL_NOT_SET_UP
    try:
        plan = note_capture.plan("obsidian", line,
                                 now=datetime.datetime.fromtimestamp(at))
        why = str(getattr(plan, "reason_empty", "") or "")
        if why:
            return why
        got = note_capture.run(plan, approved=True)
    except Exception:
        return _JOURNAL_FAILED
    if isinstance(got, dict) and got.get("ok") is True:
        return ""
    said = str(got.get("reason") or "") if isinstance(got, dict) else ""
    return said or _JOURNAL_FAILED


def _optional_module(name: str):
    """Another module of this PC's backend, or None when it is not there.

    `jarvis_habits` ships with the life-coach lane and is not in this tree yet,
    and `backend/test_base_matches_repo.py` holds the published base to importing
    ONLY what it ships ("the base's own imports close") - a plain `import
    jarvis_habits` there, even inside a try, would claim the base carries a file
    it does not. So the lookup is by name, at the moment an answer is written,
    which is the same thing `jarvis_notes_edit._protection()` and several other
    modules here do for the same reason. Nothing is guessed at: an absent module
    is None, and every caller turns that into one plain sentence."""
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _write_goal(goal_id: str, line: str, at: float) -> str:
    """'' when the line went on that goal's progress log, else one sentence.

    THE INTERFACE a later lane implements (PR #1105, "a goal keeps a progress
    log"): ``jarvis_goals.progress(goal_id, text, *, at)``, returning a mapping
    whose ``{"ok": False, "error": "..."}`` is shown as it is, or nothing. This
    tree's `jarvis_goals.py` has no progress log yet, so a reminder that names a
    goal says GOAL_NOT_SET_UP and keeps the answer: it never crashes and never
    pretends to have written what it did not."""
    goals = _optional_module("jarvis_goals")
    if goals is None:
        return GOAL_NOT_SET_UP
    fn = getattr(goals, "progress", None) or getattr(goals, "add_progress", None)
    if not callable(fn):
        return GOAL_NOT_SET_UP
    try:
        got = fn(goal_id, line, at=at)
    except KeyError:
        return "That goal is not on this PC any more."
    except Exception:
        return _GOAL_FAILED
    if isinstance(got, dict) and got.get("ok") is False:
        return str(got.get("error") or "") or _GOAL_FAILED
    return ""


def _write_habit(habit_id: str, line: str, at: float) -> str:
    """'' when a tick was recorded, else one sentence.

    Wired by the life-coach lane, and deliberately left as a clean seam rather
    than half-built here: it calls ``jarvis_habits.tick(habit_id, *, at, text)``
    when that module is beside this file. It is not in this tree, so the honest
    answer is HABIT_NOT_SET_UP - the same shape `_write_goal` takes, so one lane
    cannot accidentally look more finished than the other."""
    habits = _optional_module("jarvis_habits")
    if habits is None:
        return HABIT_NOT_SET_UP
    fn = getattr(habits, "tick", None)
    if not callable(fn):
        return HABIT_NOT_SET_UP
    try:
        got = fn(habit_id, at=float(at), text=line)
    except KeyError:
        return "That habit is not on this PC any more."
    except Exception:
        return _HABIT_FAILED
    if isinstance(got, dict) and got.get("ok") is False:
        return str(got.get("error") or "") or _HABIT_FAILED
    return ""


# --------------------------------------------------------------------------
#   GTD-1 - context-rich reminders, read-only conditions, smart snooze and
#   "the owner is at the PC" (2026-10-18)
# --------------------------------------------------------------------------
# Additive throughout. A reminder written before today has no context, no
# trigger and no condition, so every read path returns exactly what it did
# (see `_view`: new keys appear only when there is something to say). Nothing
# here raises a card, opens a socket, calls a model or writes to a client:
# the readers are INJECTED (so this module stays pure and testable), and the
# one call out is the privacy taint latch - and only when private context was
# actually attached, never on a bare tick.

#: A resolved reminder's context packet is dropped this many days later.
#: The bare reminder row is already cleaned up by FIRED_KEEP/DONE_KEEP; this
#: only bounds the extra detail (a summary, a name, a suggested prompt).
BUNDLE_RETENTION_DAYS = 7

#: Limits on what a context packet may hold. A summary is at most the length
#: of a paragraph; a path is NEVER stored (see `scrub_context_bundle`).
BUNDLE_SUMMARY_MAX = 280
BUNDLE_ENTITIES_MAX = 8
BUNDLE_FILES_MAX = 8
BUNDLE_PROMPT_MAX = 400

#: GTD-1 follow-up (Gemini's Q2 ruling, 2026-10-18): the ONLY breadcrumb kept
#: when a context packet's words must be dropped because the scrubber is
#: missing or raising. A plain true flag, never a hash - a hash of a guessable
#: name or sentence is a secret oracle, and it would tell the owner nothing.
#: No words, no ids: just "there was context that could not be checked".
CONTEXT_DROPPED = "context_dropped_unscrubbed"

#: The packet's own content keys. Used to tell "a packet with real content"
#: from "the dropped breadcrumb only", so the view never says `has_context`
#: for a reminder whose context was in fact thrown away.
BUNDLE_CONTENT_KEYS = ("source_conv_id", "source_summary", "linked_entities",
                       "linked_files", "suggested_prompt")

#: "At the PC" means unlocked AND no more than this many idle seconds AND no
#: focus session running. Two minutes is the ruling's own number.
IDLE_ACTIVE_MAX_S = 120.0

#: After this many snoozes a reminder is "stuck" and its card may offer to be
#: broken into three small steps. The option is OPT-IN (the caller has to say
#: yes) and never for a sensitive reminder.
STUCK_SNOOZE_THRESHOLD = 3

#: How a reminder may become due. "time" is every reminder before today.
TRIGGERS = ("time", "on_pc_active", "after_focus")

#: The read-only conditions a reminder may watch. Neither ever sends anything.
CONDITION_KINDS = ("no_email_reply_from", "decks_due")

#: The five snooze presets. "next_pc_active" sets a trigger, not a time.
SNOOZE_PRESETS = ("15m", "1h", "tonight", "tomorrow_morning", "next_pc_active")

#: A path-shaped string, in the three shapes a Windows PC writes one. A file
#: is stored in a context packet as an OPAQUE id/label only, never as a path.
_PATHLIKE = re.compile(r"(?:^[A-Za-z]:[\\/]|^[\\/]|\\\\|(?:^|[\s:])[^/\s:]+[/\\][^/\s:]+)")


def _scrubber():
    """jarvis_scrub.scrub_text, or None on a backend without it."""
    try:
        import jarvis_scrub
        fn = getattr(jarvis_scrub, "scrub_text", None)
        return fn if callable(fn) else None
    except Exception:
        return None


def _scrub_line(text, limit: int) -> str:
    """One line of the owner's/reader's words, secrets hidden, cut to `limit`.

    FAIL CLOSED (2026-10-18 privacy review, F1/F2): a missing scrubber, or a
    scrubber that raises, means the line is DROPPED (""), never stored raw.
    Anything that becomes a storable packet goes through
    `scrub_context_bundle`, which drops the WHOLE packet on the same failure
    rather than storing it half-scrubbed."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    fn = _scrubber()
    if fn is None:
        return ""
    try:
        t = str(fn(t) or "")
    except Exception:
        return ""
    return t[:limit].strip()


#: An address rather than a person's name (privacy review F3/F4): a
#: condition's target may be a name, never a path or a URL. `_PATHLIKE`
#: covers paths; this covers every `scheme://` form and a bare `www.` host.
_ADDRESSLIKE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|\bwww\.)", re.I)


def _clean_condition_target(value):
    """A condition target as it may be persisted, or raise ValueError.

    The target is a PERSON'S NAME (whose reply is being watched); it is never
    a path or a web address (privacy review F3/F4: it is persisted and handed
    to every client by `_view`). It is scrubbed for secrets on the way in; if
    the scrubber is missing or fails, the target is refused rather than
    stored raw - the same fail-closed rule as a context packet."""
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if len(text) > 80:
        raise ValueError("a condition's name must be 80 characters or fewer")
    if _PATHLIKE.search(text) or _ADDRESSLIKE.search(text):
        raise ValueError("a condition's name must be a name, not a path or a web address")
    if _scrubber() is None:
        raise ValueError("the condition's name cannot be checked for secrets here")
    safe = _scrub_line(text, 80)
    if not safe:
        raise ValueError("the condition's name cannot be checked for secrets")
    return safe


def _safe_condition_target(value) -> str:
    """The target as `_view` may hand to clients: "" unless it is a clean name.

    Old rows (or a damaged database) may hold a path/address because an
    earlier build stored it raw; `_view` must never pass one on (privacy
    review F4 - the same reason `rule["watch"]` is withheld from `_view`)."""
    try:
        return _clean_condition_target(value) or ""
    except Exception:
        return ""


def _decode_bundle(raw) -> dict:
    """A stored context packet as a dict; {} for absent or damaged."""
    if isinstance(raw, dict):
        got = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            got = json.loads(raw)
        except Exception:
            return {}
    else:
        return {}
    return got if isinstance(got, dict) else {}


def _bundle_has_content(bundle: dict) -> bool:
    """Whether a packet dict carries anything besides the dropped breadcrumb."""
    return any(bundle.get(key) for key in BUNDLE_CONTENT_KEYS)


def scrub_context_bundle(bundle) -> dict:
    """The ONLY way a context packet becomes storable.

    Scrubbed through the real `jarvis_scrub.scrub_text` (so a secret cannot
    ride along in a summary, a name or a suggested prompt), bounded, and with
    any path-shaped entry in every field DROPPED: a file is remembered by an
    opaque id/label, never by its path (the blueprint's ruling, Q3/Q4).

    FAIL CLOSED (privacy review F1/F2): when the scrubber is missing, or
    raises on any word in the packet, the result is {CONTEXT_DROPPED: True} -
    the packet's words are gone and the reminder keeps ONLY the plain boolean
    saying they were dropped (GTD-1 follow-up, Gemini's Q2 ruling 2026-10-18).
    No words, no ids, and no hash: a hash of the dropped text would be a
    secret oracle. A packet already carrying the breadcrumb keeps it, so a
    snoozed copy does not lose the fact."""
    if not isinstance(bundle, dict):
        return {}
    prior = bundle.get(CONTEXT_DROPPED) is True
    lost = prior or _bundle_has_content(bundle)
    scrubber = _scrubber()
    if scrubber is None:
        return {CONTEXT_DROPPED: True} if lost else {}

    def clean(text, limit: int) -> str:
        t = " ".join(str(text or "").split())
        if not t:
            return ""
        return str(scrubber(t) or "")[:limit].strip()

    try:
        summary = clean(bundle.get("source_summary"), BUNDLE_SUMMARY_MAX)
        if summary and _PATHLIKE.search(summary):
            summary = ""                  # never a path, even inside a summary
        conv = bundle.get("source_conv_id")
        conv = str(conv).strip()[:200] if isinstance(conv, (str, int)) \
            and not isinstance(conv, bool) else ""
        if conv and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", conv):
            conv = ""
        entities = []
        for item in list(bundle.get("linked_entities") or [])[:BUNDLE_ENTITIES_MAX]:
            if isinstance(item, dict):
                item = item.get("name") or item.get("label") or ""
            name = clean(item, 80)
            if name and not _PATHLIKE.search(name):
                entities.append(name)
        files = []
        for item in list(bundle.get("linked_files") or []):
            if isinstance(item, dict):
                label = clean(item.get("label") or item.get("id"), 80)
            else:
                label = clean(item, 80)
            if not label or _PATHLIKE.search(label) or _ADDRESSLIKE.search(label):
                continue                 # NEVER a path or address, in any shape
            files.append(label)
            if len(files) >= BUNDLE_FILES_MAX:
                break
        prompt = clean(bundle.get("suggested_prompt"), BUNDLE_PROMPT_MAX)
        if prompt and (_PATHLIKE.search(prompt) or _ADDRESSLIKE.search(prompt)):
            prompt = ""                   # and never one in a suggested prompt
    except Exception:
        # A scrubber that cannot handle these words must not let ANY of them
        # through: no half-scrubbed packet, no raw survivors. The breadcrumb is
        # the only thing kept, so the owner can see the packet was dropped
        # rather than think there never was one.
        return {CONTEXT_DROPPED: True} if lost else {}
    out = {"source_conv_id": conv or None,
           "source_summary": summary,
           "linked_entities": entities,
           "linked_files": files,
           "suggested_prompt": prompt}
    if prior:
        # Re-scrubbing an already-dropped packet (a snooze copies it, an app
        # sends it back): keep the breadcrumb, and keep ONLY the breadcrumb
        # when there are no words - so reading it again cannot grow empty
        # fields that look like content.
        if not _bundle_has_content(out):
            return {CONTEXT_DROPPED: True}
        out[CONTEXT_DROPPED] = True
    return out


def _reminder_extras(body) -> dict:
    """The GTD-1 fields a POST /api/schedule/add body may carry, if present.

    Only passed to `Scheduler.add_at` for a reminder. An app that does not
    know about them sends none, and a reminder is created exactly as before."""
    if not isinstance(body, dict):
        return {}
    out = {}
    if isinstance(body.get("context_bundle"), dict):
        out["context_bundle"] = body["context_bundle"]
    if body.get("trigger"):
        out["trigger"] = str(body.get("trigger")).strip().lower()
    if body.get("condition_kind"):
        out["condition_kind"] = str(body.get("condition_kind")).strip().lower()
    if body.get("condition_target"):
        out["condition_target"] = str(body.get("condition_target"))
    # 2026-10-27: what this reminder opens, or the one task it may ask to run.
    # Checked by `_clean_action` in `add_at`, which refuses anything that is not
    # one known kind and its one payload key.
    if body.get("action") is not None:
        out["action"] = body.get("action")
    return out


def _expire_bundles(c, now: float) -> int:
    """Drop context packets of reminders resolved long enough ago (one conn)."""
    cutoff = float(now) - BUNDLE_RETENTION_DAYS * 86400.0
    cur = c.execute("UPDATE jobs SET context_bundle = NULL WHERE context_bundle IS NOT NULL "
                    "AND state IN ('fired', 'done') "
                    "AND COALESCE(resolved_at, fired_at, changed) <= ?", (cutoff,))
    return int(cur.rowcount)


def expire_context_bundles(*, now=None, scheduler=None) -> int:
    """The same sweep `tick()` runs, for a caller that wants it plainly."""
    s = scheduler or get()
    with s._lock, s._db() as c:
        return _expire_bundles(c, s.now() if now is None else float(now))


# ---- who is at the PC -----------------------------------------------------

def _reader(readers, name):
    """One injected reader as a zero-argument callable, or None."""
    if readers is None:
        return None
    got = readers.get(name) if isinstance(readers, dict) else getattr(readers, name, None)
    if callable(got):
        return got
    if got is None:
        return None
    return lambda: got


def pc_active(readers=None) -> dict:
    """Whether the owner is really AT this PC right now, from injected readers.

    {"active": bool, "reason": "active" | "session_locked" | "app_locked" |
     "user_idle" | "in_focus_session", "idle_seconds": float | None}

    Active requires ALL THREE, in plain terms: the Windows session is unlocked,
    the owner has touched the keyboard/mouse within `IDLE_ACTIVE_MAX_S` (two
    minutes), and no focus session is running.

    FAIL CLOSED (privacy review F12): a missing or raising reader for ANY of
    the three lock/focus signals means "cannot tell", which means NOT active -
    never "assume unlocked". Only an explicitly injected reader may say the
    session is unlocked, the App lock is off, or no focus session is running.
    A missing/raising idle reading is also NOT active. Reasons name the signal
    that failed, so a caller can wire it:

        session_unlocked() -> bool   missing/raises -> "session_locked"
        app_locked()       -> bool   missing/raises -> "app_locked"
        focus_active()     -> bool   missing/raises -> "in_focus_session"
        idle_seconds()     -> float|None  None/raises -> "user_idle"

    Pure: reads nothing itself, starts nothing, and is safe to call from a
    render or a test."""
    idle = None
    get_idle = _reader(readers, "idle_seconds")
    if get_idle is not None:
        try:
            raw = get_idle()
            idle = float(raw) if raw is not None else None
        except Exception:
            idle = None

    def signal(name: str, when_unknown: bool) -> bool:
        fn = _reader(readers, name)
        if fn is None:
            return when_unknown
        try:
            return bool(fn())
        except Exception:
            return when_unknown

    unlocked = signal("session_unlocked", False)     # unknown -> treat as locked
    app_locked = signal("app_locked", True)          # unknown -> treat as locked
    in_focus = signal("focus_active", True)          # unknown -> treat as focused
    if not unlocked:
        return {"active": False, "reason": "session_locked", "idle_seconds": idle}
    if app_locked:
        return {"active": False, "reason": "app_locked", "idle_seconds": idle}
    if idle is None or idle > IDLE_ACTIVE_MAX_S:
        return {"active": False, "reason": "user_idle", "idle_seconds": idle}
    if in_focus:
        # A focus session is work already under way: a reminder must HOLD here,
        # not interrupt it. This is the ruling's "holds during focus".
        return {"active": False, "reason": "in_focus_session", "idle_seconds": idle}
    return {"active": True, "reason": "active", "idle_seconds": idle}


def reminder_ready(reminder, *, now=None, readers=None):
    """(can become due now, reason) for ONE reminder - pure, reads nothing.

    A "time" reminder is due when its own `due` has passed (the scheduler's
    ordinary tick, unchanged). An "on_pc_active" or "after_focus" reminder is
    due only when `pc_active()` says the owner is at the PC - which is false
    DURING a focus session, so both triggers hold until it ends - AND, when it
    has a real `due`, not before that time (privacy review F13: a future-due
    PC-triggered reminder must not be surfaced early). A `next_pc_active`
    snooze copy has due None and is eligible at the next activity."""
    if not isinstance(reminder, dict):
        return False, "not_a_reminder"
    trigger = str(reminder.get("trigger") or "time")
    if trigger == "time":
        due = reminder.get("due")
        if due is None:
            return False, "no_time"
        at = time.time() if now is None else float(now)
        return (float(due) <= at), ("due" if float(due) <= at else "not_due")
    if trigger not in ("on_pc_active", "after_focus"):
        return False, "unknown_trigger"
    due = reminder.get("due")
    at = time.time() if now is None else float(now)
    if due is not None and float(due) > at:
        return False, "not_due"
    state = pc_active(readers)
    return bool(state["active"]), str(state["reason"])


def due_active_reminders(*, now=None, readers=None, scheduler=None) -> list:
    """The reminders whose trigger is satisfied by the owner being at the PC.

    READ ONLY: it returns the reminders that could go off now, and marks
    nothing. A caller with a notification path fires them itself; this slice
    deliberately adds no second firing loop (the scheduler's own tick only
    runs "time" triggers, so these can never fire at an idle PC by accident).
    """
    s = scheduler or get()
    at = s.now() if now is None else float(now)
    with s._lock, s._db() as c:
        rows = c.execute("SELECT * FROM jobs WHERE kind = 'reminder' AND state = 'active' "
                         "AND trigger IN ('on_pc_active', 'after_focus')").fetchall()
    out = []
    for row in rows:
        view = s._view(row, at)
        # The row's own stored mark goes out with the reminder (2026-10-26,
        # Ruling 2.3 residual): the caller that ACTS on it latches from this
        # value at that moment. This getter is read-only and may be polled, so
        # it never latches here itself - see the docstring above.
        view["source_taint"] = _row_taint(row)
        ready, _why = reminder_ready(view, now=at, readers=readers)
        if ready:
            out.append(view)
    return out


# ---- read-only enrichment and early satisfaction ---------------------------

def _latch_reminder_context() -> bool:
    """Keep the turn on the local model once private context was attached."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why="reminder_context"))
    except Exception:
        return False


def enrich_and_check_condition(reminder, *, readers=None, hide_memory_lists=False,
                               app_locked=False) -> dict:
    """The details a reminder is ABOUT, plus its read-only condition.

    Returns {"withheld", "context", "facts", "condition_satisfied_early",
    "condition_note", "toast", "context_attached"} - plus, ONLY when the stored
    packet had to be dropped unscrubbed, `context_dropped_unscrubbed: True`
    beside them: a plain flag about the reminder, never a word or a hash of
    one. READ-ONLY: it starts nothing, sends nothing, changes no reminder.

    WITHHELD ENTIRELY under `hide_memory_lists` or `app_locked`: no reader is
    called, no bundle is read, no taint is latched, and every words field comes
    back empty - the caller shows the bare reminder and that is all.

    `readers` (all optional; a missing one means "nothing to add"):
        memory_facts(name) -> list[str]        what Jarvis learned about a name
        email_reply_since(target, since) -> {"at": epoch} | None
                                               METADATA ONLY - the reader is
                                               never given or asked for a body
        decks_due() -> int                     cards due from jarvis_decks

    Conditions:
        no_email_reply_from  target already replied after the reminder was
                             created -> early satisfaction; the note names the
                             sender and the time ONLY, never an email body
        decks_due            0 cards due -> early satisfaction

    The one side effect is the privacy latch (`jarvis_gate.latch_taint`,
    why="reminder_context") and it happens ONLY when private context was
    actually attached or read - never on a bare reminder, never when withheld.
    """
    out = {"withheld": bool(hide_memory_lists or app_locked),
           "context": {}, "facts": [], "condition_satisfied_early": False,
           "condition_note": "", "toast": "", "context_attached": False}
    if out["withheld"]:
        # NOTHING is read: not the bundle, not a reader, not a latch.
        return out
    if not isinstance(reminder, dict):
        return out
    title = str(reminder.get("text") or "")
    context = scrub_context_bundle(reminder.get("context_bundle")) \
        if isinstance(reminder.get("context_bundle"), dict) else {}
    # Only fetch from the store when the reminder carried no packet at all: a
    # packet that scrubbed to the dropped breadcrumb is already an answer, and
    # must not send this caller to the singleton scheduler for a second look.
    if not context and reminder.get("id"):
        try:
            context = scrub_context_bundle(get().bundle(str(reminder.get("id"))))
        except Exception:
            context = {}
    context = dict(context or {})
    # The dropped-packet breadcrumb is NOT context and must never be handed to
    # a caller as if it were: it is a flag about the reminder, not a fact about
    # the owner's words. It is exposed additively beside the details, no words.
    dropped = context.pop(CONTEXT_DROPPED, None) is True
    out["context"] = context
    if dropped:
        out[CONTEXT_DROPPED] = True

    facts = []
    get_facts = _reader(readers, "memory_facts")
    names = list(context.get("linked_entities") or [])
    if not names:
        # No stored names: the capitalised words of the reminder itself are
        # the only names it could be about. Nothing is guessed beyond that.
        names = re.findall(r"\b[A-Z][a-z]{2,}\b", title)[:3]
    if get_facts is not None:
        for name in names[:3]:
            if len(facts) >= 3:
                break
            try:
                got = get_facts(name) or []
            except Exception:
                got = []
            for fact in list(got)[: max(0, 3 - len(facts))]:
                said = _scrub_line(fact, 200)
                if said:
                    facts.append(said)
    out["facts"] = facts

    condition = str(reminder.get("condition_kind") or "")
    target = str(reminder.get("condition_target") or "")
    note = ""
    satisfied = False
    if condition == "no_email_reply_from" and target:
        get_reply = _reader(readers, "email_reply_since")
        if get_reply is not None:
            try:
                got = get_reply(target, reminder.get("created"))
            except Exception:
                got = None
            if isinstance(got, dict) and got.get("at"):
                satisfied = True
                # The sender and the clock, NEVER the body: the note is what a
                # toast may show, and a message body must not be in it.
                note = f"{target} already replied at {clock(float(got['at']))}"
    elif condition == "decks_due":
        get_due = _reader(readers, "decks_due")
        if get_due is not None:
            try:
                due = get_due()
            except Exception:
                due = None
            if due == 0:
                satisfied = True
                note = "No cards are due right now"
    out["condition_satisfied_early"] = satisfied
    out["condition_note"] = note

    attached = (bool(facts) or bool(note)
                or bool(context.get("source_summary"))
                or bool(context.get("linked_entities"))
                or bool(context.get("linked_files"))
                or bool(context.get("suggested_prompt")))
    out["context_attached"] = attached
    if attached and not _latch_reminder_context():
        # The privacy latch could not be set (F7): fail CLOSED. No private
        # words go back - not even the facts already read - and the caller is
        # told in plain words why. A latch-free "success" would be the one
        # answer worse than a refusal.
        out.update({"withheld": True, "context": {}, "facts": [],
                    "condition_satisfied_early": False, "condition_note": "",
                    "toast": "", "context_attached": False,
                    "error": ("The privacy latch could not be set, so the private "
                              "details were withheld. Nothing private was shown.")})
        return out
    toast = title
    if note:
        toast = f"{title} - {note}" if title else note
    out["toast"] = toast[:300]
    return out


# ---- snooze presets, the stuck threshold and the opt-in micro-steps --------

_MICRO_STEPS = {
    "email": ["Open the last message", "Draft a two-sentence reply with Jarvis "
              "in chat", "Read it once, then send"],
    "call": ["Open the contact's details", "Write the two things to say in chat "
             "with Jarvis", "Make the call"],
    "file": ["Open the document", "Ask Jarvis to sum up what needs doing in it",
             "Do the first small edit"],
    "default": ["Open what this reminder is about", "Write the first small step "
                "in chat with Jarvis", "Do it for five minutes"],
}


def _micro_steps(title, condition_kind="") -> list:
    """Three small first steps for a reminder that has been snoozed a lot."""
    text = f"{title} {condition_kind}".lower()
    if "email" in text or "reply" in text or "inbox" in text:
        return list(_MICRO_STEPS["email"])
    if "call" in text or "phone" in text:
        return list(_MICRO_STEPS["call"])
    if any(word in text for word in ("file", "document", "read", "pdf", "report")):
        return list(_MICRO_STEPS["file"])
    return list(_MICRO_STEPS["default"])


def _is_sensitive(text, bundle=None) -> bool:
    """Whether the classifier calls this reminder's words or packet sensitive.

    The WHOLE bundle is considered, not only the title (privacy review F10):
    a bland reminder ("Buy milk") with a private summary/name/file/prompt must
    never be offered the three-step breaker just because its title is plain.

    Pattern layer only (`use_model=False`): snoozing must be instant and must
    never call a model. A classifier that is missing or raises is treated as
    SENSITIVE - the conservative direction, so a broken classifier can never
    offer the breaker for private material."""
    parts = [str(text or "")]
    if isinstance(bundle, dict):
        for key in ("source_summary", "suggested_prompt"):
            value = bundle.get(key)
            if value:
                parts.append(str(value))
        for key in ("linked_entities", "linked_files"):
            for value in list(bundle.get(key) or []):
                if value:
                    parts.append(str(value))
    try:
        import jarvis_sensitive
        verdict = jarvis_sensitive.classify("\n".join(parts), use_model=False)
        return bool(verdict.get("sensitive"))
    except Exception:
        return True


def _preset_due(preset: str, now: float):
    """(due epoch or None, trigger) for one preset. Raises ValueError."""
    if preset == "15m":
        return now + 15 * 60.0, "time"
    if preset == "1h":
        return now + 3600.0, "time"
    if preset == "tonight":
        return next_at(19, 0, now), "time"
    if preset == "tomorrow_morning":
        y, mo, d = _add_days(*_wall(now)[:3], 1)
        return wall_to_epoch(y, mo, d, 9, 0), "time"
    if preset == "next_pc_active":
        return None, "on_pc_active"
    raise ValueError("preset is one of: " + ", ".join(SNOOZE_PRESETS))


def snooze_reminder(reminder_id, preset: str = "15m", *, now=None,
                    micro_steps_opt_in: bool = False, scheduler=None) -> dict:
    """Snooze ONE reminder with a named preset, and remember how often.

    `preset`: "15m", "1h", "tonight" (the next 19:00 on this PC's clock),
    "tomorrow_morning" (tomorrow 09:00), "next_pc_active" (no time: it waits
    for `pc_active()`). A new snoozed copy becomes due - the same shape the
    scheduler already uses for Snooze - and the ORIGINAL one-off reminder is
    resolved/replaced so it cannot fire at its old time as well (privacy
    review F17). Its context packet is resolved with it (the sweep then drops
    it after `BUNDLE_RETENTION_DAYS`), and the copy carries the packet.

    The return carries `snooze_count` and:
      * `stuck_hint`: True once the reminder has been snoozed
        `STUCK_SNOOZE_THRESHOLD` (3) times - the boundary is "< 3 is not
        stuck" - and NEVER for a sensitive reminder (the title AND the whole
        packet are classified, F10);
      * `micro_steps`: the three small steps, and ONLY when the caller opted
        in (`micro_steps_opt_in=True`) and the reminder is not sensitive.

    Raises ValueError for an unknown preset (plain words); a missing/not-a-
    reminder id is a plain {"ok": False, ...} answer.
    """
    preset = str(preset or "").strip().lower()
    if preset not in SNOOZE_PRESETS:
        raise ValueError("preset is one of: " + ", ".join(SNOOZE_PRESETS))
    s = scheduler or get()
    at = s.now() if now is None else float(now)
    with s._lock, s._db() as c:
        row = s._row(c, str(reminder_id))
        if row is None or row["kind"] != "reminder":
            return {"ok": False, "reason": "no_such_reminder",
                    "error": "That reminder is not on the list any more."}
        due, trigger = _preset_due(preset, at)
        count = int(row["snooze_count"] or 0) + 1
        # A one-off that was still waiting is finished by its snooze: mark it
        # resolved (not "fired" - nobody should see a second "went off"), so
        # only the new copy carries the reminder forward. A repeating rule or
        # an already-resolved row is left alone.
        resolve = row["rule"] is None and row["state"] in ("active", "paused")
        if resolve:
            c.execute("UPDATE jobs SET snooze_count = ?, changed = ?, state = 'fired', "
                      "due = NULL, fired_at = NULL, fired_due = NULL, late = 0, "
                      "resolved_at = COALESCE(resolved_at, ?) WHERE id = ?",
                      (count, at, at, str(reminder_id)))
        else:
            c.execute("UPDATE jobs SET snooze_count = ?, changed = ? WHERE id = ?",
                      (count, at, str(reminder_id)))
    context = _decode_bundle(row["context_bundle"])
    new_id = s._insert("reminder", text=row["text"], state="active", due=due,
                       rule=None, duration=None, source=row["source"] or "app",
                       snooze_of=str(reminder_id), context_bundle=context or None,
                       trigger=trigger,
                       condition_kind=row["condition_kind"],
                       condition_target=_safe_condition_target(row["condition_target"])
                       or None,
                       # The copy carries the original's creation-time mark
                       # too, so a snooze cannot launder a tainted reminder.
                       source_taint=_row_taint(row) or None)
    with s._lock, s._db() as c:
        c.execute("UPDATE jobs SET snoozed_to = ?, changed = ? WHERE id = ?",
                  (new_id, at, str(reminder_id)))
    sensitive = _is_sensitive(row["text"], context)
    stuck = count >= STUCK_SNOOZE_THRESHOLD and not sensitive
    steps = _micro_steps(row["text"], row["condition_kind"] or "") \
        if stuck and micro_steps_opt_in else []
    return {"ok": True, "id": str(reminder_id), "snoozed_id": new_id,
            "preset": preset, "due": due, "trigger": trigger,
            "snooze_count": count, "stuck_hint": stuck,
            "micro_steps": steps, "micro_steps_opt_in": True,
            "sensitive": sensitive}
