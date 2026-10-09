"""jarvis_gate.py - the part that makes [autonomy.tiers] mean something.

Until now the framework was a description. jarvis-framework.toml listed
send_email, delete_file, run_shell_on_host and spend_money as "ask", and
OpenJarvis approved every one of them without asking, because its tool
dispatch is constructed with `confirm_callback=lambda _prompt: True`. Every
other protection in this project - the privacy router, the origin check, the
inbound token - is there to stop something from reaching that callback. Once
something does reach it, there was nothing left.

This module is the missing half. It answers one question, "may this action
proceed", and it blocks until a human says so when the tier calls for it.

THE CROSS-PROCESS PROBLEM
OpenJarvis (port 8000) and the HUD proxy (port 4719) are separate processes.
The code that needs to WAIT lives in OpenJarvis; the endpoints a human
answers through live in the proxy. An in-memory queue cannot span the two, so
the queue is a SQLite table in the config directory - atomic across
processes, no daemon to keep alive, no extra dependency, and it behaves on
Windows. The waiting side polls it; the deciding side writes one row.

FAIL CLOSED, EVERYWHERE
Every path that is not an explicit approval denies:
  - an action not listed in [autonomy.tiers]     -> treated as "ask"
  - a prompt this module cannot map to an action -> treated as "ask"
  - nobody answers before the timeout            -> denied, logged "expired"
  - the database cannot be opened at all         -> denied
That last one matters. A gate that opens when it breaks is not a gate, so if
this module cannot do its job it refuses rather than waving things through.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

import jarvis_framework as fw

DB_PATH = Path(os.environ.get(
    "JARVIS_APPROVALS_DB", fw.CONFIG_DIR / "approvals.db"))

def _cfg(section: str, key: str, default):
    """Read one config value. `section` may be dotted for a nested table."""
    try:
        node = fw.load_framework()
        for part in section.split("."):
            node = node.get(part, {})
        return node.get(key, default)
    except Exception:
        return default


# How long a request waits for a human before it gives up and denies.
# The config owns this; the environment variable is an override for testing.
APPROVAL_TIMEOUT = float(os.environ.get(
    "JARVIS_APPROVAL_TIMEOUT",
    _cfg("autonomy", "approval_timeout_seconds", 180)))
POLL_SECONDS = 0.25

# An action nobody thought to classify is not thereby safe. Configurable, but
# only downward-unsafe by explicit choice - the default stays "ask".
UNKNOWN_TIER = str(_cfg("autonomy", "unknown_action_tier", "ask"))

_INIT_LOCK = threading.Lock()
_inited = False


# --------------------------------------------------------------------------
#   Storage
# --------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Always use this inside `with closing(_connect()) as c:`.

    `with sqlite3.connect(...) as c:` does NOT close the connection - it only
    commits or rolls back the transaction. That distinction cost real handles
    here: the approval wait polled every 250ms inside a bare `with _connect()`,
    so a 180-second wait opened 720 connections and closed none of them
    deterministically. CPython's refcounting papers over most of it, which is
    exactly what makes it a bad thing to rely on: on Windows the unclosed
    handles hold locks on approvals.db-wal, and the last one stays open until
    the function returns. The wait loop now opens ONE connection and reuses it.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    global _inited
    with _INIT_LOCK:
        if _inited:
            return
        with closing(_connect()) as c:
            # WAL so the waiting process can read while the deciding process
            # writes, instead of the two blocking each other.
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id         TEXT PRIMARY KEY,
                    action     TEXT NOT NULL,
                    tier       TEXT NOT NULL,
                    detail     TEXT,
                    prompt     TEXT,
                    state      TEXT NOT NULL,     -- pending|approved|denied|expired
                    created    REAL NOT NULL,
                    decided    REAL,
                    decided_by TEXT
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_state ON approvals(state, created)")
            # A process that died mid-wait leaves its row 'pending' forever,
            # and the HUD keeps offering it. Anything older than the timeout
            # plus a grace period cannot still have a waiter.
            c.execute("UPDATE approvals SET state='expired', decided=? "
                      "WHERE state='pending' AND created < ?",
                      (time.time(), time.time() - APPROVAL_TIMEOUT - 60))
            c.execute("""
                CREATE TABLE IF NOT EXISTS taint (
                    key   TEXT PRIMARY KEY,
                    until REAL NOT NULL,
                    why   TEXT
                )""")
            # Why an item was queued at a higher tier than the table says.
            # Added after the fact, so tolerate a database from before it
            # existed rather than refusing to start against one.
            try:
                c.execute("ALTER TABLE approvals ADD COLUMN raised TEXT")
            except sqlite3.OperationalError:
                pass                          # already there
        _inited = True


# --------------------------------------------------------------------------
#   Mapping a free-text prompt onto an action name
# --------------------------------------------------------------------------
# OpenJarvis hands its confirm callback a human-readable prompt, not a tool
# name, so when we are wired in at that point this is the best we can do.
# It is a heuristic and it is allowed to fail - failing means "ask", which is
# the same answer it would give for an unlisted action.

_ACTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("open_public_tunnel",       re.compile(r"\btunnel|ngrok|expose (?:the )?port|public url\b", re.I)),
    ("post_to_external_service", re.compile(r"\bpost (?:to|on)\b|\btweet\b|\bpublish\b|\bupload\b|"
                                            r"\bpush\b[\s\S]{0,30}?\b(?:repo|remote|branch|origin|github)\b|"
                                            r"\bship (?:it |this )?to\b|\bdeploy\b", re.I)),
    ("spend_money",              re.compile(r"\bpurchase|buy\b|\bcheckout\b|\bpayment\b|\bpay\b|\bsubscribe\b|\bcharge\b|\binvoice\b|"
                                            r"\bsettle\b|\btop up\b|\btransfer\b[\s\S]{0,30}?\b(?:to|account|\d)|"
                                            r"\bmove\b\s+\$?\d+|\brefund\b|\bwire\b[\s\S]{0,20}?\d", re.I)),
    ("run_shell_on_host",        re.compile(r"\bshell\b|\bcommand\b|\bpowershell\b|\bbash\b|\bexecute\b|\bsubprocess\b|\brun\b[\s\S]{0,40}?\b(?:script|exe|cmd)\b", re.I)),
    # Euphemism is the normal register for destruction. Nobody says "delete";
    # they say get rid of it, clear it out, make it disappear.
    # Notes. These sit ahead of the generic delete/send patterns so the audit
    # trail names the specific action; strictest-wins means the ORDER is not
    # what keeps them safe (a joplin deletion matches delete_file too, and
    # "never" beats "ask" either way) - it is what makes the log readable.
    ("delete_joplin_note",       re.compile(r"\b(?:delete|remove|purge|trash|erase|drop)\b[\s\S]{0,40}?"
                                            r"\b(?:joplin|personal note|vault note)\b|"
                                            r"\bjoplin\b[\s\S]{0,30}?\b(?:delete|remove|purge|trash)\b", re.I)),
    ("edit_joplin_note",         re.compile(r"\b(?:edit|update|modify|change|rewrite|overwrite|append to|amend)\b"
                                            r"[\s\S]{0,40}?\b(?:joplin|personal note|vault note)\b", re.I)),
    ("create_joplin_note",       re.compile(r"\b(?:create|new|draft|add|save|write|file)\b[\s\S]{0,40}?"
                                            r"\b(?:joplin|personal note|vault note)\b", re.I)),
    ("read_joplin_note",         re.compile(r"\b(?:read|search|find|show|view|check|look up|open|list)\b"
                                            r"[\s\S]{0,40}?\b(?:joplin|personal note|vault note)\b", re.I)),

    ("delete_logseq_page",       re.compile(r"\b(?:delete|remove|unlink|purge|erase)\b[\s\S]{0,40}?"
                                            r"\b(?:logseq|journal page|graph page)\b", re.I)),
    ("edit_logseq_page",         re.compile(r"\b(?:overwrite|rewrite|replace|clobber|reset)\b[\s\S]{0,40}?"
                                            r"\b(?:logseq|page|journal)\b", re.I)),
    ("create_logseq_page",       re.compile(r"\b(?:create|new|start|make)\b[\s\S]{0,40}?"
                                            r"\b(?:logseq page|page in logseq|graph page)\b", re.I)),
    ("append_logseq_journal",    re.compile(r"\b(?:log|append|record|note down|jot|add)\b[\s\S]{0,40}?"
                                            r"\b(?:logseq|journal|progress|scratchpad|daily note)\b", re.I)),
    ("read_logseq_page",         re.compile(r"\b(?:read|check|show|view|open|list)\b[\s\S]{0,40}?"
                                            r"\b(?:logseq|journal|scratchpad|graph page)\b", re.I)),

    ("delete_file",              re.compile(r"\bdelete\b|\bremove\b|\brm -|\bunlink\b|\btrash\b|\berase\b|\bwipe\b|"
                                            r"\bpurge\b|\btruncate\b|\bdrop\b[\s\S]{0,20}?\b(?:table|database|schema)\b|"
                                            r"\bclean(?:\s*up)?\b|\bclear (?:out|down)?\b|\bempty\b|"
                                            r"\bget rid of\b|\bmake\b[\s\S]{0,25}?\bdisappear\b|"
                                            r"\bnuke\b|\bscrub\b|\bflush\b|\bprune\b|\bshred\b", re.I)),
    ("send_email",               re.compile(r"\b(?:shoot|ping|fire off|drop)\b[\s\S]{0,30}?\b(?:note|email|mail|message|line)\b|"
                                            r"\blet\b[\s\S]{0,25}?\bknow\b[\s\S]{0,25}?\b(?:by |via )?(?:mail|email|message)\b|"
                                            r"\b(?:send|dispatch|transmit|deliver|forward|email|mail|reply|respond)\b"
                                            r"[\s\S]{0,60}?\b(?:email|e-mail|mail|message|recipient|inbox|to\s+\S+@)\b"
                                            r"|\b(?:send|dispatch|transmit|forward)\b[\s\S]{0,40}?@", re.I)),
    ("delete_calendar_event",    re.compile(r"\b(?:delete|cancel)\b[\s\S]{0,40}?\b(?:event|meeting|invite)\b", re.I)),
    ("edit_calendar_event",      re.compile(r"\b(?:edit|move|reschedule|update)\b[\s\S]{0,40}?\b(?:event|meeting|invite)\b", re.I)),
    ("control_computer",         re.compile(r"\bclick\b|\bkeystroke\b|\btype into\b|\bmouse\b|\bkeyboard\b", re.I)),
    ("modify_own_code",          re.compile(r"\bmodify\b[\s\S]{0,40}?\b(?:own|its own|source|code)\b|\bself[- ]modif", re.I)),
    ("change_own_config",        re.compile(r"\b(?:change|edit|update|write)\b[\s\S]{0,40}?\bconfig", re.I)),
    ("draft_email",              re.compile(r"\bdraft\b[\s\S]{0,40}?\b(?:email|reply)\b", re.I)),
    ("read_calendar",            re.compile(r"\b(?:read|check|look at|what.s on)\b[\s\S]{0,30}?\bcalendar\b", re.I)),
    ("web_research",             re.compile(r"\bsearch the web\b|\bweb search\b|\bbrowse\b|\bfetch\b[\s\S]{0,30}?\burl\b", re.I)),
]

# Verbs that mean something leaves this machine or stops existing. If one of
# these is present, no prompt-derived classification is allowed to land on a
# tier weaker than "ask", whatever else it matched.
_SIDE_EFFECT = re.compile(
    r"\b(send|sent|sending|dispatch\w*|transmit\w*|deliver\w*|forward\w*|"
    r"publish\w*|upload\w*|post(?:ed|ing)?|submit\w*|push\w*|deploy\w*|ship\w*|"
    r"delete\w*|remove\w*|erase\w*|wipe\w*|overwrit\w*|"
    # The euphemisms, which is how anyone actually talks about destroying
    # something. A verb list built only from the blunt words is a list of the
    # phrasings least likely to be used.
    r"purg\w*|truncat\w*|nuk\w*|scrub\w*|shred\w*|prun\w*|flush\w*|"
    r"clean\w*|clear\w*|empt\w*|discard\w*|drop\w*|disappear\w*|"
    r"purchase\w*|buy|bought|pay\w*|charge\w*|transfer\w*|settl\w*|refund\w*|"
    r"execut\w*|invoke\w*|launch\w*|install\w*|uninstall\w*|"
    r"revok\w*|disabl\w*|terminat\w*|kill\w*|stop\w*|restart\w*|reboot\w*)\b",
    re.I)

# --------------------------------------------------------------------------
#   CONSEQUENCE, which is a different question from PERMISSION
#
#   The tier says whether Jarvis may do a thing without asking. It says
#   nothing about what happens if the answer is wrong, and those are not the
#   same question. "Switch to the other model" and "send this email" are both
#   tier `ask`, and to every client so far they arrived looking identical -
#   same shape of card, same two buttons.
#
#   That is exactly why swipe-to-approve was forbidden on the phone. A swipe
#   is a gesture people make without reading. That is fine for dismissing a
#   notification and not fine for sending mail, and with no way to tell the
#   two apart the only safe rule was "no swiping, ever".
#
#   So: two axes, deliberately few.
#
#     reversible  yes   undoing it is one step and costs nothing
#                 hard  undoable, but it costs time, money or a re-download
#                 no    cannot be undone from here
#
#     reach       local     nothing leaves this machine
#                 outbound  someone or something else sees it
#
#   swipe_ok is the AND of both being benign, and nothing else is allowed to
#   set it. An action absent from this table is treated as irreversible and
#   outbound - the same fail-closed direction as unknown_action_tier.
#
#   Deliberately DERIVED at read time rather than stored on the row: the
#   classification is code, it will be refined, and a stored copy would mean
#   old approvals carried an old judgement and every refinement needed a
#   schema migration.
# --------------------------------------------------------------------------
_RISK: dict[str, tuple[str, str, str]] = {
    # reading anything
    "web_research":        ("yes", "outbound", "a public query leaves the machine; nothing changes"),
    "read_calendar":       ("yes", "local", "reads the calendar; changes nothing in it"),
    "read_files_readonly": ("yes", "local", "opens the file; writes nothing back"),
    "read_joplin_note":    ("yes", "local", "opens the note; the vault is unchanged"),
    "read_logseq_page":    ("yes", "local", "opens the page; the graph is unchanged"),
    "browse_model_catalog":("yes", "outbound", "a fixed public query; downloads nothing"),

    # additive writes to things you own
    "create_logseq_page":     ("yes", "local", "delete it and it is gone"),

    # the ones that are reversible in one step, on purpose
    "switch_model":  ("yes", "local", "rollback is one tap, which is why rollback is tier auto"),
    "rollback_model":("yes", "local", "this IS the undo for a switch, so it never waits"),
    "power_manage":  ("yes", "local", "waking it is one tap; quieting it is the safe direction"),

    # undoable, but it costs something real
    "edit_joplin_note":   ("hard", "local", "the previous text is gone unless you version that vault"),
    "edit_logseq_page":   ("hard", "local", "the previous text is gone unless you version that graph"),
    "change_own_config":  ("hard", "local", "revertible by editing back, if you know what it was"),
    "modify_own_code":    ("hard", "local", "revertible from a backup, not from here"),
    "download_model":     ("hard", "outbound", "deletable afterwards, but you have already paid for the bytes"),

    # no undo
    "edit_calendar_event":    ("no", "outbound", "attendees are notified the moment it changes"),
    "delete_calendar_event":  ("no", "outbound", "attendees are notified, and the invite is gone"),
    "delete_file":            ("no", "local", "not recoverable from here"),
    "delete_joplin_note":     ("no", "local", "not recoverable from here"),
    "delete_logseq_page":     ("no", "local", "not recoverable from here"),
    "spend_money":            ("no", "outbound", "money has left"),
    "post_to_external_service":("no", "outbound", "published; assume it is cached somewhere"),
    "open_public_tunnel":     ("no", "outbound", "exposes this machine; permanently forbidden"),
    # A shell or a mouse can do anything, including sending something. They
    # are classified by their worst case, not their usual one.
    "run_shell_on_host": ("no", "outbound", "a shell can do anything, including reach the network"),
    "control_computer":  ("no", "outbound", "driving the desktop can click send"),
    # Same worst-case reasoning as control_computer, for the paired phone
    # instead of this machine: tapping around in an arbitrary app can send a
    # message or complete a purchase just as easily as driving the desktop
    # can. "outbound" even though the commands stay on the local network to
    # your own device - the PHONE'S apps can still reach the outside world,
    # which is the thing being classified by its worst case.
    "control_phone":     ("no", "outbound", "tapping the phone can send a message or complete a purchase"),
    # A GitHub search that carries your token is not "nothing changes" the
    # way an anonymous one is - it identifies you to GitHub, even though it
    # writes nothing there. Kept separate from web_research (which defaults
    # to auto in jarvis-framework.toml) so authenticating is its own
    # decision rather than inheriting a tier set for anonymous search.
    "research_authenticated": ("yes", "outbound", "identifies you to GitHub via your token; nothing is written"),
    # plan.patch (jarvis_plan.py, "one card, several steps", the owner's
    # "build it now", 2026-09-28; feasibility audit I61). Classified by its
    # own worst case even though every risky or result-filled step inside
    # an approved plan still asks again on ITS OWN action's own risk entry
    # (this one only covers the safe steps that run without asking a
    # second time) - "outbound" because a step the model did not flag as
    # risky could still be wrong about that.
    "run_plan": ("no", "outbound", "runs every step of an approved plan the model did not flag as risky, at once; a risky or result-filled step always asks again on its own separate card first"),
    # phone-notifications.patch (jarvis_phone_notifications.py, the owner's
    # decision of 2026-09-26; built 2026-09-28). Lets the phone start
    # reading notifications from apps the OWNER chooses (an empty list by
    # default; banking apps are blocked on the phone). Nothing here reaches
    # this PC by itself - a captured notification is read into a chat only
    # when the owner explicitly attaches it, the same "shared text" door
    # every other outside-text source already uses. Turning it off again is
    # instant.
    "phone_notifications_read": ("yes", "local", "lets your phone start reading notifications from apps you choose (none, until you add one); banking apps are blocked on the phone; a notification only reaches Jarvis when you attach it to a chat yourself; turning it off again is instant"),
    # devices.patch (jarvis_devices.py, docs/PAIRING-DESIGN.md; the owner's
    # decisions of 2026-09-24 and 2026-09-28). Pairing a phone gives it a
    # key of its own; only the key's SHA-256 is kept on this PC, and the
    # device can be removed at any time (Settings, Devices), which cuts it
    # off at once - so "yes" and "local". Both cards are also in
    # jarvis_owner_check.PC_ONLY_ACTIONS: approved on this PC only, always
    # with Windows Hello, whatever this line says.
    "pair_device": ("yes", "local", "gives the phone named on the card its own key to talk to Jarvis, after you check it shows the same four words; you can remove it any time in Settings, Devices, and that cuts it off at once"),
    # Bringing the old shared key back for other devices (a loosening):
    # retiring it again is instant, so "yes"; it only decides who may talk
    # to this PC, so "local".
    "unretire_shared_key": ("yes", "local", "lets any device that still has the old shared key reach Jarvis again, not only this PC; you can retire it again any time, and that is instant"),
    # Phase 2 (docs/PAIRING-DESIGN.md section 11): a paired phone's signing
    # key, so its risky approvals need a fresh fingerprint or PIN on the
    # phone. Removing the device drops it again, so "yes" and "local";
    # also PC only, always with Windows Hello (PC_ONLY_ACTIONS).
    "register_approval_key": ("yes", "local", "lets the phone named on the card approve risky actions with its own fingerprint or PIN, checked here on this PC; you can remove the device any time in Settings, Devices, and that drops the key again"),
    # apps-in-projects.patch (jarvis_apps.py, docs/APPS-IN-PROJECTS-DESIGN.md
    # section 2.2; the owner's answers of 2026-09-29). Adding a task's change
    # to an app's files: nothing leaves this PC ("local") and nothing is run,
    # but Jarvis has no Undo button for a merge yet - git keeps the old version,
    # and the merged files are the code a later step will build - so "no": this
    # card is RISKY (Windows Hello on the PC, the screen lock on the phone) and
    # heavy (a widget's Approve opens the full card). Not PC-only: the owner
    # reads the whole change first, on either device.
    "app_merge_change": ("no", "local", "adds the change shown on the card to your app's files, exactly as shown; nothing is run; the older version stays in the app's git history, but there is no Undo button for it yet"),
    # note-capture.patch (jarvis_note_capture.py). All three stay on this PC:
    # the Logseq journal and the Obsidian daily note are files here, and
    # Joplin's service must be at 127.0.0.1 or the plan refuses. All only ADD
    # - an entry at the end of a day's page, or a new note - so each can be
    # undone by deleting what was added.
    # A note Jarvis wants to write in a chat turn shaped by outside text is
    # asked under write_notes_after_outside_text instead (jarvis_agent.py
    # NOTE_WRITES, the owner's decision of 2026-09-24): the same three
    # writes, so the same "stays on this PC".
    "write_notes_after_outside_text": ("yes", "local", "adds one entry to your notes on this PC (today's Logseq journal, today's Obsidian daily note, or a new Joplin note); nothing already there is changed; asked because Jarvis read outside text in this conversation, or your message was not typed"),
    "append_logseq_journal": ("yes", "local", "adds one entry to the end of today's Logseq journal on this PC; nothing already there is changed"),
    "create_joplin_note":    ("yes", "local", "creates one new note in Joplin on this PC; no existing note is changed"),
    "append_obsidian_daily": ("yes", "local", "adds one entry to the end of today's Obsidian daily note on this PC; nothing already there is changed"),
    # second-card.patch: "Browser control" (jarvis_second_card.BROWSER_ACTION).
    # Turning it on starts the same second Ollama on this PC AND lets Jarvis
    # offer its browser tool, which works real web pages on the internet -
    # so "outbound", not "local", and the notice interrupts. Each plan of
    # browser steps is still its own approval card.
    "second_card_browser_enable": ("yes", "outbound", "lets Jarvis offer its browser tool, which works real web pages on the internet; each plan of steps there is its own card; turning the switch off takes the tool away"),
    # second-card.patch (jarvis_second_card.py): "One bigger model on both
    # cards" (COMBINED_ACTION). A THIRD copy of Ollama on THIS PC, on
    # 127.0.0.1 only, able to see both graphics cards at once - never at the
    # same time as any switch here (it needs both cards to itself).
    "second_card_combined_enable": ("yes", "local", "starts a third copy of Ollama on this PC that only this PC can reach (127.0.0.1), able to see both graphics cards at once; it stops when the switch is turned off"),
    # second-card.patch (jarvis_second_card.py). Turning on a second-card
    # switch starts a second copy of Ollama on THIS PC, on 127.0.0.1 only,
    # sending nothing anywhere. It runs while ANY switch using it is on, and
    # stops when the last is off. Without this line the action would be read as
    # "unknown", and the notice would say it might leave the machine.
    "second_card_enable": ("yes", "local", "starts a second copy of Ollama on this PC that only this PC can reach (127.0.0.1); it keeps running while any second-card switch that uses it is on, and stops when the last one is turned off"),
    # second-card.patch (jarvis_second_card.py): "Everyday chat runs on",
    # the owner's decision of 2026-10-05. Pinning chat to ONE card sets two
    # settings for the owner's own Windows user (CUDA_VISIBLE_DEVICES to that
    # card's id, OLLAMA_VULKAN to 0), so the everyday Ollama uses that card
    # and cannot fall back to the other one. Its own action, not
    # second_card_enable: it names a SPECIFIC physical card, and it changes
    # where EVERY answer runs, not only the second card's own features.
    # Nothing leaves this PC and no file is written.
    "chat_card_pin": ("yes", "local", "changes which graphics card your everyday Ollama uses, by setting CUDA_VISIBLE_DEVICES and OLLAMA_VULKAN for your own Windows user; nothing leaves this PC and no file is written"),
    # second-card.patch (jarvis_second_card.py): moving one of the second
    # card's own features onto a THIRD graphics card, alongside the second
    # card's own lane - never instead of it. A fourth copy of Ollama on THIS
    # PC, on 127.0.0.1 only, pinned to that one card. Its own action (not
    # second_card_enable) because it names a SPECIFIC physical card, which
    # docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3 says must always be
    # a real, named choice - never a default.
    "second_card_third_assign": ("yes", "local", "starts a fourth copy of Ollama on this PC that only this PC can reach (127.0.0.1), pinned to a third graphics card; it runs alongside the second card's own copy, and stops when the assignment is changed or the feature is turned off"),
    # wiki.patch (jarvis_wiki.py). Adding a document writes pages in
    # <vault>/Jarvis Wiki/ on this PC with a model on this PC (127.0.0.1).
    # A changed page's earlier copy is kept in Jarvis Wiki/.versions/;
    # index.md and log.md are appended to, with no copy. Without this line the
    # action would be read as "unknown", and the notice would say it might
    # leave the machine.
    "wiki_update": ("yes", "local", "writes pages in the Jarvis Wiki folder of your vault on this PC; the earlier copy of any page it changes is kept in .versions, and index.md and log.md are added to, with no copy kept"),
    # big-model.patch (jarvis_big_model.py). Turning on a big-model switch
    # lets Jarvis start colibri on THIS PC, only when a background job
    # needs it, listening on 127.0.0.1 only, and nothing is sent anywhere.
    # It stops once no job switch that uses it is on. Without this line
    # the action would be read as "unknown", and the notice would say it
    # might leave the machine.
    "big_model_enable": ("yes", "local", "lets Jarvis start colibri on this PC for background jobs, reachable from this PC only (127.0.0.1); it keeps running while any big-model job switch is on, and stops when the last one, or the main switch, is turned off"),
    # voices.patch (jarvis_voices.py). Adding a custom voice keeps a
    # recording on THIS PC, and switching Jarvis to one makes it speak in
    # that voice; nothing is sent anywhere, and switching back or deleting
    # the voice never asks. Without these lines the actions would be read as
    # "unknown", and the notice would say they might leave the machine.
    "custom_voice": ("yes", "local", "keeps a voice recording on this PC, or makes Jarvis speak in a voice kept there; nothing is sent anywhere, and switching back to the built-in voice or deleting the voice is immediate"),
    # The better voice: F5-TTS on the second graphics card, in its own
    # program that Jarvis talks to through pipes (no port), only while it
    # speaks in a custom voice; it stops when idle, in standby, and when
    # the switch is turned off.
    "better_voice_enable": ("yes", "local", "lets Jarvis start F5-TTS on the second graphics card on this PC when it speaks in a custom voice, reachable by no network; it stops after idle minutes, in standby, and when the switch is turned off"),
    # chat-history.patch (jarvis_chat_log.py). Turning chat history back on
    # keeps your chats with Jarvis, voice included, encrypted in a file on
    # THIS PC; nothing is sent anywhere, and turning it off never asks.
    # Without this line the action would be read as "unknown", and the
    # notice would say it might leave the machine.
    "history_enable": ("yes", "local", "keeps your chats with Jarvis, including what you say by voice, encrypted on this PC; nothing is sent anywhere, turning it off is immediate, and each kept conversation can be deleted"),
    # auto-learn.patch (jarvis_auto_learn.py). Automatic learning saves facts
    # about you from what you type or say, on THIS PC, without a card per
    # fact; every one can be forgotten, and turning it off never asks.
    "learning_auto_enable": ("yes", "local", "lets Jarvis save facts about you and your projects from what you type or say to it, without asking about each one; nothing is sent anywhere, every saved fact is listed with Forget, and turning it off is immediate"),
    "learning_sensitive_enable": ("yes", "local", "lets Jarvis also save facts about health, money and other people's private details without asking first; passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses still wait for your yes; nothing is sent anywhere, every saved fact is listed with Forget, and turning it off is immediate"),
    # hardware.patch (jarvis_hardware.py). Making a tuned model (jarvis-chat,
    # jarvis-long, jarvis-vision) for a preset: Ollama on THIS PC makes it
    # from a model already downloaded. Nothing is downloaded and nothing is
    # sent anywhere. Without this line the action would be read as
    # "unknown", and the notice would say it might leave the machine.
    "models_create": ("yes", "local", "makes a tuned copy of a model you already downloaded, with Ollama on this PC; nothing is downloaded or sent anywhere, and jarvis-primary is not changed"),
    # web-search.patch (jarvis_search.py, jarvis_agent.py). One web search,
    # asked about because private things could slip into its words (or the
    # owner chose "Ask before every web search"): the words shown on the card
    # go to the search the owner chose - SearXNG on this PC, which asks other
    # engines, DuckDuckGo, Exa, Tavily or Brave. Outbound, so the notice is heavy.
    "search_the_web": ("yes", "outbound", "sends the search words shown on the card to the web search you chose; what comes back is read as outside text, and nothing else of yours is sent"),
    # Turning "Ask before every web search" off: a setting on this PC. It
    # sends nothing; searches straight from the owner's own question then run
    # without a card again.
    "stop_asking_before_every_web_search": ("yes", "local", "stops asking before every web search - a search straight from your own question runs without a card again, and a search after Jarvis has read email, files, notes or other outside text, one whose words repeat a saved fact, and one after a sensitive saved fact was used still ask; nothing is sent by this change"),
    # email-send.patch (jarvis_email_send.py, jarvis_agent.py; the owner's
    # decision of 2026-09-25). ONE email, from the owner's own account, to
    # exactly the people on the card - who, the subject and every word are
    # on the card, never here: this line is what a lock screen may show.
    # It leaves the machine and cannot be taken back, so the notice is heavy.
    "send_email": ("no", "outbound", "sends the email shown on the card from your own account, to exactly the people it lists; once sent it cannot be taken back"),
    # draft-email.patch (jarvis_email_draft.py, jarvis_agent.py; the owner's
    # decision of 2026-09-27). ONE draft, saved to the owner's own Drafts
    # folder by IMAP APPEND only - never sent, and the owner can change or
    # delete it themselves afterward, so it is reversible; it still leaves
    # the machine, to the owner's own mail server, so the notice is heavy.
    "draft_email": ("yes", "outbound", "saves the draft shown on the card to your own Drafts folder; nothing is sent, and you can change or delete the draft yourself afterward"),
    # schedule.patch (jarvis_schedule.py). Setting up something that repeats
    # (a morning briefing or a "tell me when" - since 2026-09-26 a plain
    # repeating reminder, alarm or standby schedule has no card, asks-first.
    # patch). Setting it up sends nothing, but each run then reads the owner's
    # OWN calendar, mail server or Home Assistant, or one web page they named
    # (a page watch), through that read's own gate action; deleting is immediate.
    "schedule_repeat": ("yes", "local", "sets up a morning briefing, which reads your calendar and email if they are set up, or a \"tell me when\", which looks at your own mail server or Home Assistant, or at one web page you named, each time; the card says exactly what each run reads, what it finds goes only to your own apps, and deleting it is immediate"),
    # asks-first.patch (jarvis_asks_first.py, the owner's decision of
    # 2026-09-26). Loosening one line of [autonomy.tiers] from the desktop's
    # "What asks first" page, from a short safe list: it changes one line of
    # the settings file on this PC and sends nothing. Making it ask again is
    # instant, from either app. jarvis_owner_check.PC_ONLY_ACTIONS makes its
    # approval need Windows Hello on this PC whatever this line says.
    "loosen_what_asks_first": ("yes", "local", "lets one action from a short list - reading your own calendar, email, notes or home status, or adding to your notes - go ahead without asking you first, by changing one line of your settings file on this PC; making it ask again is instant"),
    # watch-notifications.patch (jarvis_watch_notify.py, the owner's decision
    # of 2026-09-25; reconfirmed 2026-09-27, Q17). Lets the phone's own,
    # already-built-in notification bridging copy Jarvis's notifications to a
    # paired smartwatch too - not a Jarvis watch app, and nothing about it
    # reaches this PC. Turning it off again is instant.
    "watch_notifications_enable": ("yes", "local", "lets your phone's own notification bridging copy Jarvis's notifications to a paired smartwatch too, instead of keeping them on the phone only; nothing about this reaches this PC, and turning it off again is instant"),
    # tools-enable.patch (jarvis_asks_first.py, the owner's answer of
    # 2026-09-27). A DIFFERENT thing from loosen_what_asks_first, above: this
    # offers a reading tool to the AI model at all, by changing one line of
    # [tools].enabled on this PC, and sends nothing. Turning it back off is
    # instant, from either app. jarvis_owner_check.PC_ONLY_ACTIONS makes its
    # approval need Windows Hello on this PC whatever this line says.
    "enable_reading_tool": ("yes", "local", "offers one reading tool - your calendar, email, notes or home status - to the AI model at all, by changing one line of your settings file on this PC ([tools].enabled); this is separate from whether it asks you first, and turning it back off is instant"),
    # backup.patch (jarvis_backup.py, the owner's decision of 2026-09-27).
    # Replaces memory, chat history, settings and notes with an older
    # backup, and puts the chat-history key back in Windows Credential
    # Manager. Reversible: Jarvis backs up your CURRENT data first, with a
    # fresh recovery code shown once, so this restore can itself be undone.
    # jarvis_owner_check.PC_ONLY_ACTIONS makes its approval need Windows
    # Hello on this PC whatever this line says.
    "restore_backup": ("yes", "local", "replaces your memory, chat history, settings and notes with an older backup, and puts back the key that unlocks your kept chat history; Jarvis backs up your CURRENT data first, with a fresh recovery code, so this restore can itself be undone"),
    # chatbot.patch (jarvis_chatbot.py and jarvis_chatbot_gemini.py, the
    # owner's decisions of 2026-09-27 and 2026-09-28). ONE card per
    # conversation with an AI chatbot website (Gemini first): the goal, word
    # for word, then Jarvis's own follow-up questions, typed into a browser
    # window the owner can see, within the messages and minutes on the card.
    # It leaves this PC and what is sent cannot be taken back, so "no" and
    # "outbound": a risky approval (Windows Hello on the PC, a screen lock
    # on the phone). It was already treated as risky before this line, as
    # an action the gate had not classified; this line gives it its words.
    "chatbot_session": ("no", "outbound", "holds a conversation with an AI chatbot website for you - Gemini first - sending the goal you approved word for word and then its own follow-up questions, typed into a browser window you can see, within the messages and minutes on the card; nothing private is sent, and what is sent cannot be taken back"),
    # forget-range.patch (jarvis_forget_range.py, the owner's decision of
    # 2026-09-28, "Forget a time frame"). ONE card listing every fact and
    # every chat from the days the owner chose, each one they left ticked:
    # the facts are forgotten (retired, as Forget does) and the chats
    # deleted from this PC. Nothing is sent anywhere, so "local". Undo puts
    # everything back for 10 minutes; after that the chats are gone for
    # good, so "no": a risky approval (Windows Hello on the PC, a screen
    # lock on the phone). Without this line the action would be read as
    # "unknown", and the notice would say it might leave the machine.
    "memory_forget_range": ("no", "local", "forgets the facts and deletes the chats listed on the card, on this PC; nothing is sent anywhere; for 10 minutes one tap on Undo puts them all back, and after that the chats are gone for good and the facts stay forgotten"),
    # support-chat.patch (jarvis_support.py and jarvis_support_widget.py,
    # the owner's decisions of 2026-09-28, "Customer-support chats"). ONE
    # card per support chat: Jarvis chats with a company's customer support
    # in the owner's name, on the owner's REAL account, in a browser window
    # the owner can see, giving only the details listed on the card. And
    # ONE card per offer (a refund, a credit, a cancellation, a change):
    # nothing is accepted without it, and what is accepted binds the owner.
    # Both leave this PC and cannot be taken back, so "no" and "outbound":
    # risky approvals (Windows Hello on the PC, a screen lock on the phone).
    # They were already treated as risky before these lines, as actions the
    # gate had not classified; these lines give them their words.
    "support_chat": ("no", "outbound", "chats with a company's customer support for you, in your name, on your own account there, in a browser window you can see - giving only the details listed on the card; every offer gets its own card, identity checks and \"are you a bot?\" are handed to you, and what is sent cannot be taken back"),
    "support_offer": ("no", "outbound", "accepts the offer shown on the card, in your name, by sending exactly the reply shown; what you agree to binds you, like any message you send yourself, and cannot be taken back"),
    # inbox-tidy.patch (jarvis_inbox_tidy.py, jarvis_agent.py; the owner's
    # decision of 2026-09-28, "inbox tidy by voice"). ONE card listing every
    # email that will be archived, starred, marked as read or moved to Trash
    # in the owner's own mailbox - the senders and subjects are on the card,
    # never here: this line is what a lock screen may show. It changes the
    # mailbox on the mail provider's server, so "outbound" (a risky approval:
    # Windows Hello on the PC, a screen lock on the phone) - but nothing is
    # deleted for good and one tap on Undo puts it all back for 10 minutes.
    "tidy_inbox": ("yes", "outbound", "archives, stars, marks as read or moves to Trash exactly the emails listed on the card, in your own mailbox on your mail provider's server; nothing is deleted for good, and for 10 minutes one tap on Undo puts every one back"),
    # screen-picture.patch (jarvis_screen_picture.py, the owner's decision of
    # 2026-09-29: "add it as a feature that can be enabled or disabled"). ONE
    # card to let "Look at this" and "Watch with me" also look at the PICTURE
    # of the screen, slowly, with a small model that runs on the processor
    # (never the graphics card; a running Pictures card lane goes first, 2026-09-30) in its own copy of Ollama that only this PC can
    # reach. The picture is blacked out for secrets first and is never saved;
    # nothing leaves this PC; the model itself is downloaded by the owner's own
    # pasted line, never by this card. Turning it off again is instant.
    "screen_picture_enable": ("yes", "local", "lets \"Look at this\" and \"Watch with me\" also look at the picture of your screen, slowly, using a small model in a separate copy of Ollama that runs on this PC's processor - or, when you have turned on Pictures on an extra graphics card and it is running, that card's picture model is used instead - and only this PC can reach (127.0.0.1); secrets in the picture are blacked out first, nothing is saved or sent anywhere, the model is downloaded by you, not by this card, and turning it off again is instant"),
    # browser-engine.patch (jarvis_browser_engine.py, jarvis_obscura.py; the
    # owner's decision of 2026-09-29). ONE card to let Jarvis choose a
    # headless browser - Obscura, a program with no window, started by Jarvis
    # on this PC and driven over standard input and output (no port) - for
    # plain web reading, instead of the visible browser. A new program and a
    # new way onto the web, so "outbound" (a risky approval): the pages are on
    # the internet, and every page, click and box it fills is still its own
    # plan card first. Stealth is on. Turning it off is instant and stops it.
    "obscura_enable": ("yes", "outbound", "lets Jarvis choose a browser with no window (Obscura, a program on this PC that Jarvis starts and stops) for plain web reading; the pages are on the internet and it looks like an ordinary Chrome, but every page, click and box it fills is still its own card first, it never types a password or solves a captcha and stops at a captcha or sign-in page it recognises, it cannot open your own network, and turning it off is instant"),
    # form-review.patch (jarvis_form_review.py, jarvis_agent.py; the owner's
    # decision of 2026-09-30: "fill out forms and book appointments for me
    # ... send me a screenshot of all the details it filled in for me to
    # check and approve"). The SECOND card of a browser plan that ends in a
    # form-sending click: Jarvis has filled the form and stopped; this card
    # shows the site, every word typed and a picture of the page exactly as
    # it looks. What is typed goes to the site named on the card, and once
    # sent it cannot be taken back, so a risky approval.
    "browser_form_submit": ("no", "outbound", "sends the form you were shown to the website named on the card, with every word typed into it; Jarvis clicks only after you approve this card and only if the page is still exactly as it looked in the picture, and once sent it cannot be taken back; the picture goes to your own devices only and is not saved"),
    # web-search-switch.patch (jarvis_search.py; the settings audit of 2026-09-30).
    # Web search ships ON. The owner may switch it off at any time (instant, no
    # card); turning it back ON is this one card. The change itself sends nothing:
    # a search still follows every rule it had (its own card when private things
    # could slip in, never a password or key), so this is a setting on this PC.
    "web_search_enable": ("yes", "local", "lets Jarvis search the web again, with the search you chose; the change itself sends nothing, every search keeps the rules it already had, and you can turn web search off again at any time, at once"),
    # topics.patch (jarvis_topics.py, JARVIS-API section 107; the owner's decision of
    # 2026-09-30). ONE card when a private topic (Health, Money, or one the owner marked
    # private) is turned back on for learning or for answers, when its private mark is
    # cleared, when a batch of its facts is moved out to a looser topic, or when any
    # loosening is asked from outside text. It only changes which saved facts Jarvis may
    # learn about or use; nothing is sent anywhere. Turning a topic OFF is instant.
    "topic_loosen": ("yes", "local", "lets Jarvis learn about or use a private topic again (health, money, or one you marked private), or move its facts to a more open topic; the facts stay on this PC, sensitive ones are still kept on screen and never read aloud, and new sensitive ones still wait for your yes; switching a topic off again is instant"),
    # referee.patch (jarvis_referee.py, JARVIS-API section 108; the owner's decision of
    # 2026-09-30). ONE card per goal step whose benchmark number reached its target: "This
    # looks done - tick it?", with the numbers on it. Yes ticks that one step, exactly as the
    # owner's own tick would (and it can be unticked at once); the model never writes a tick and
    # no test is run. Nothing leaves this PC. At most a few cards a day.
    "referee_tick": ("yes", "local", "ticks one step of one of your goals whose number reached its target, exactly as if you had ticked it yourself; you can untick it at once, and it never runs a test or ticks anything on its own"),
    # tag-suggest.patch (jarvis_tag_suggest.py, JARVIS-API section 104; the owner's decision of
    # 2026-09-30). Two cards, both on this PC only: one to let the local model read a few old
    # chats at night (never ones that read email or web pages, difficult moments, or Live,
    # support and AI-chat records), and one per suggested tag, which files ONE chat under a tag
    # that already exists when you tap Approve. Turning it off is instant; the tag can be moved
    # or removed at once, and no chat words are kept or logged.
    "chat_tags_suggest_on": ("yes", "local", "lets Jarvis's model on this PC read the first few messages you wrote in a few old chats each night to suggest a tag; it never reads chats that read email or web pages, difficult moments, or Live, support and AI-chat records, it can only pick a tag you already made, nothing is filed without your Approve, and turning it off is instant"),
    "chat_tag_suggest": ("yes", "local", "files one chat under a tag you already made, exactly as if you had filed it yourself; you can move or remove the tag at once, and nothing else about the chat changes"),
    # youtube.patch (jarvis_youtube.py, JARVIS-API section 112; the owner's
    # decision of 2026-09-30, docs/STUDY-FROM-TEXT-DESIGN.md section 5). ONE
    # card per YouTube link: the exact link is on the card, which says this
    # breaks YouTube's terms and may be blocked. Your PC contacts YouTube and
    # the link tells it which video you are studying - a named way out of the
    # PC (ARCHITECTURE section 4) that cannot be taken back, so "no" and
    # "outbound": a risky approval (Windows Hello on the PC, a screen lock on
    # the phone). Only the caption text comes back, never video or sound.
    "youtube_captions_read": ("no", "outbound", "makes this PC contact YouTube to fetch the caption text of the one video named on the card, for a quiz; this breaks YouTube's terms and YouTube may block it, only the caption text comes back (never the video or its sound), the link tells YouTube which video you are studying, and it cannot be taken back"),
    # quiz-cloud.patch (jarvis_quiz_cloud.py, JARVIS-API section 113; the owner's
    # decision of 2026-09-30, docs/STUDY-FROM-TEXT-DESIGN.md section 7). ONE card per
    # "grade this better" request: it shows the whole message word for word (the
    # quiz's questions, your answers and the passages) and the service that would
    # get it. Your study words leave this PC for that one quiz - a named way out
    # (ARCHITECTURE section 4) that cannot be taken back, so "no" and "outbound": a
    # risky approval (Windows Hello on the PC, a screen lock on the phone).
    "quiz_cloud_grade": ("no", "outbound", "sends the questions, your answers and the passages of one quiz, word for word as the card shows them, to the cloud AI service named on the card to be marked; it bends the rule that your study words stay on this PC for that one quiz only, it costs a little on your account, and it cannot be taken back"),
    # readpage.patch (jarvis_readpage.py, JARVIS-API section 115; the owner's
    # request of 2026-10-05: "post a webpage into jarvis and it can read the
    # content out loud"). ONE card per address the owner hands over, showing
    # it in full, raised BEFORE any fetch. Your PC contacts that one website
    # and the site sees this PC's address - a named way out of the PC
    # (ARCHITECTURE section 4) that cannot be taken back, so "no" and
    # "outbound": a risky approval (Windows Hello on the PC, a screen lock on
    # the phone). Only that one page's words come back, never a link on it.
    "read_web_page": ("no", "outbound", "makes this PC fetch the one web page named on the card, so it can read its words out loud to you; that website will see this PC's address and the request cannot be taken back, only that one page is fetched (never a link on it), and its words are outside text - never learned, never acted on"),
}

_UNKNOWN_RISK = ("no", "outbound",
                 "not classified, so treated as irreversible and outbound")


def risk_for(action: str) -> dict:
    """What happens if this approval is answered wrongly.

    swipe_ok is the only field a client should branch on for gesture
    decisions. The rest is there so a UI can EXPLAIN the decision rather than
    just enforce it - a card that says "no undo: there is no unsend" teaches
    the rule, and a card that silently refuses a swipe does not.
    """
    rev, reach, why = _RISK.get(action or "", _UNKNOWN_RISK)
    return {
        "reversible": rev,
        "reach": reach,
        "swipe_ok": rev == "yes" and reach == "local",
        "why": why,
        "classified": (action or "") in _RISK,
    }


def notice_for(item: dict) -> dict:
    """What a notification is allowed to say about a waiting approval.

    THE WHOLE POINT: this reads `action` and whether `raised` is set. It does
    NOT read `detail`, `prompt`, or anything inside `raised`. Every word it
    returns comes from _RISK and from the action name - tables in this file,
    written by us. **It is therefore safe by construction on a lock screen**,
    not safe by a reviewer having remembered to redact something.

    That distinction is the reason this function exists rather than a caller
    assembling a string. Three separate leaks have been found in this project
    where the rule was stated in one place and not enforced at the next: the
    audit log honoured _redact while the ntfy push sent the same dict verbatim;
    the SSE event carried the whole approval row; the doorbell's denylist
    shipped `raised` - the field that quotes hostile text - once it was added.
    A function that never touches the payload cannot join that list.

    The owner asked for the summary on the phone as well as the desktop,
    having been told the phone shows it on a lock screen. That is their call
    and it is answered here - but `raised.quote` is not "the summary". It is
    text an attacker wrote to make a reader hurry, and putting it on a lock
    screen defeats the feature it belongs to, whose entire purpose is to slow
    the reader down inside the app where it appears in quotation marks next to
    its source. `raised` travels as a BOOLEAN. See docs/ARCHITECTURE.md.

    Returns:
        title    one line: what Jarvis wants to do
        body     why it matters, and that nothing has happened yet
        weight   "heavy" | "normal" - whether to interrupt or wait to be found
        deny_ok  whether refusing WITHOUT reading the detail is safe (it is)
    """
    action = str(item.get("action") or "an action")
    r = risk_for(action)
    raised = bool(item.get("raised"))

    # The title from jarvis_card_words.TITLES: a plain phrase for every action
    # the gate knows ("Jarvis wants to switch to a different AI model"). It
    # used to be the identifier with its underscores taken out, on the theory
    # that the names were written to be read - and it read "Jarvis wants to
    # learning enable" (creativity audit, 2026-09-25). The table is ours and
    # reads only the action NAME, so the notice stays safe by construction;
    # backend/test_card_words.py keeps it in step with _RISK. Without the
    # module (an older copy), the name is still quoted as a name, never
    # dropped into a sentence it cannot finish.
    try:
        import jarvis_card_words
        title = jarvis_card_words.title_for(item.get("action"))
    except Exception:
        _words = " ".join("".join(c if c.isascii() and c.isalnum() else " "
                                  for c in str(item.get("action") or "")).split())[:60].strip()
        title = (f'Jarvis wants your OK for "{_words}"' if _words
                 else "Jarvis is asking for your approval")

    # Heavy means "interrupt them". Any one of three things earns it: it cannot
    # be undone, it leaves the machine, or outside text pushed the tier up.
    # Deliberately not a score - three named reasons a person can argue with
    # beat a number nobody can.
    heavy = (r["reversible"] == "no") or (r["reach"] != "local") or raised

    bits = [r["why"]]
    if raised:
        # Said, never quoted. That something tried to rush you is the fact that
        # changes your decision; its actual words are not needed to convey it,
        # and are the one thing that must not travel.
        bits.append("something in the text it read tried to hurry you, so this "
                    "was raised for a closer look")
    bits.append("nothing has happened yet")

    return {
        "title": title,
        "body": ". ".join(b.strip(". ") for b in bits if b).strip() + ".",
        "weight": "heavy" if heavy else "normal",
        # Refusing something you have not read costs you a retry. Approving
        # something you have not read is the failure this whole module exists
        # to prevent. The two are not symmetric and the clients are told so
        # here rather than each deciding for itself.
        "deny_ok": True,
        "approve_ok": False,
    }


# Strictness order. A prompt that matches several patterns is judged by the
# strongest one, never the weakest.
_RANK = {"auto": 0, "notify": 1, "ask": 2, "never": 3}
_VALID_TIERS = frozenset(_RANK)

# Classification by TOOL NAME. This is the primary mechanism now; the prose
# regexes above are the fallback for a free-text prompt with no tool name in
# it. An audit against the real OpenJarvis package showed why: every one of
# its confirmation prompts is
#     "Allow execution of tool 'shell_exec' with args {...}?"
# so the tool name is right there, and judging by English verbs in the
# ARGUMENTS - which the model writes - meant `ssh -R 80:localhost:8000` was a
# plain "ask" while `tail -f tunnel.log` was hard-refused as a tunnel. The
# name is chosen by the tool author; the arguments are chosen by the model.
# Trust the former.
#
# Every OpenJarvis tool is listed. An unlisted tool resolves to UNKNOWN_TIER.
_TOOL_ACTIONS: dict[str, str] = {
    # read-only / harmless
    "calculator": "auto", "think": "auto", "llm": "auto", "retrieval": "auto",
    "knowledge_search": "auto", "memory_search": "auto", "memory_retrieve": "auto",
    "kg_query": "auto", "kg_neighbors": "auto", "scan_chunks": "auto",
    "git_status": "auto", "git_diff": "auto", "git_log": "auto",
    "file_read": "read_files_readonly", "pdf_extract": "read_files_readonly",
    "web_search": "web_research", "browser_axtree": "web_research",
    "browser_extract": "web_research", "browser_screenshot": "web_research",
    "browser_navigate": "web_research",
    "audio_transcribe": "auto", "text_to_speech": "auto", "image_generate": "auto",
    "agent_list": "auto", "channel_list": "auto", "channel_status": "auto",
    "get_pending_actions": "auto", "check_permission": "auto",
    "digest_collect": "auto",
    # writes to the agent's own stores: additive, low blast radius
    "memory_store": "notify", "memory_index": "notify",
    "kg_add_entity": "notify", "kg_add_relation": "notify",
    "queue_action": "notify", "record_decision": "notify",
    # side effects that need a human
    "shell_exec": "run_shell_on_host", "docker_shell_exec": "run_shell_on_host",
    "code_interpreter": "run_shell_on_host", "code_interpreter_docker": "run_shell_on_host",
    "repl": "run_shell_on_host",
    "file_write": "delete_file", "apply_patch": "delete_file",   # both can destroy content
    "channel_send": "send_email", "agent_send": "send_email",
    "http_request": "post_to_external_service",
    "git_commit": "ask", "db_query": "ask", "knowledge_sql": "ask",
    "memory_manage": "ask", "user_profile_manage": "ask", "skill_manage": "modify_own_code",
    "execute_pending_actions": "ask", "agent_spawn": "ask", "agent_kill": "ask",
    "browser_click": "control_computer", "browser_type": "control_computer",
    # jarvis_ui_control.py: reads the OWN accessibility tree, sends no input.
    # control_computer already covers native UI actions same as it covers a
    # browser's, so run() needs no new action name - only plan() needs one,
    # and it is auto for the same reason browser_axtree etc. are read-only
    # and harmless. See backend/jarvis_ui_control.py's own docstring.
    "jarvis_ui_control_plan": "auto", "jarvis_ui_control_run": "control_computer",
    # jarvis_android_control.py: literal, individual adb commands against
    # the owner's own paired phone - never a live scrcpy mirror session (see
    # that module's docstring for why). plan() only builds command lines and
    # optionally checks which device is connected; run() is what actually
    # taps, so only run() carries the real risk.
    "jarvis_android_control_plan": "auto", "jarvis_android_control_run": "control_phone",
    # jarvis_research.py: unauthenticated search is unchanged web_research.
    # An authenticated run is its own action so it gets its own tier rather
    # than inheriting whatever the owner set web_research to for anonymous
    # search - see JARVIS_GITHUB_TOKEN in that module's own docstring.
    "jarvis_research_plan": "auto", "jarvis_research_run": "web_research",
    "jarvis_research_run_authenticated": "research_authenticated",
    # note-capture.patch: jarvis_agent.py's three note tools, each under the
    # action name jarvis-framework.toml gives a tier.
    "append_logseq_journal": "append_logseq_journal",
    "create_joplin_note": "create_joplin_note",
    "append_obsidian_daily": "append_obsidian_daily",
    # email-send.patch: jarvis_agent.py's send_email tool, under the action
    # name jarvis-framework.toml gives a tier ("ask", and it must stay so).
    "send_email": "send_email",
    # draft-email.patch: jarvis_agent.py's draft_email tool, under the action
    # name jarvis-framework.toml gives a tier ("ask", and it must stay so).
    "draft_email": "draft_email",
    # inbox-tidy.patch: jarvis_agent.py's tidy_inbox tool, under the action
    # name jarvis-framework.toml gives a tier ("ask", and it must stay so).
    "tidy_inbox": "tidy_inbox",
    # readpage.patch: jarvis_agent.py's read_web_page tool, under the action
    # name jarvis-framework.toml gives a tier ("ask", and it must stay so).
    # The tool's own name IS the action name - jarvis_agent.Tool's own
    # default when gate_lookup_name is omitted - so without this line
    # action_for_tool() fell through to "unclassified_tool" and the card the
    # owner was shown was never the one this tool raises.
    "read_web_page": "read_web_page",
    # plan.patch (jarvis_plan.py): propose_plan builds and describes a Plan
    # only - it reads nothing, sends nothing, and is auto for the same
    # reason browser_axtree and jarvis_ui_control_plan are: nothing has
    # happened yet. run_plan is the one card that lets the SAFE steps go
    # ahead; it needs its own line, not the tier a risky step's own tool
    # already has.
    "propose_plan": "auto", "run_plan": "run_plan",
    # model steward: looking is free, downloading and switching are not, and
    # they are separate decisions. Reverting is the one that must never wait.
    "model_list": "auto", "model_recommend": "auto",
    "model_browse": "browse_model_catalog",
    "model_install": "download_model",
    "model_switch": "switch_model",
    "model_rollback": "rollback_model",
    # offline personal-data connectors: reading your own mail/calendar/
    # browsing/documents is allowed (auto), but every one of them taints the
    # turn local - the taint is enforced inside the connector, not here.
    # Syncing mail opens the one network connection (to your own server).
    "connector_mail_read": "read_files_readonly",
    "connector_mail_sync": "read_files_readonly",
    "connector_mail_body": "read_files_readonly",
    "connector_calendar": "read_calendar",
    "connector_browser_history": "read_files_readonly",
    "connector_document": "read_files_readonly",
    # skills: a skill is instructions the agent will follow, so installing
    # or writing one is a change to how it behaves. Loading and listing are
    # free; removing a capability never needs approval.
    "skill_list": "auto", "skill_load": "auto", "skill_scan": "auto",
    "skill_uninstall": "auto",
    "skill_install": "modify_own_code",
    "skill_write": "modify_own_code",
    # voice gate: verifying and enrolling are local and harmless; widening
    # WHO may command the assistant is a real exposure change.
    "voice_status": "auto", "voice_verify": "auto", "voice_enroll": "auto",
    "voice_set_mode": "change_own_config",
    # power/sleep: putting the assistant under, or waking it, is the safe
    # direction either way (auto). Changing the schedule/idle rules that put
    # it under on their own is a config change (ask).
    "power_status": "auto", "power_sleep": "power_manage",
    "power_wake": "power_manage", "power_configure": "change_own_config",
    # personality modes: switching how Jarvis TALKS is free. Note there is
    # no tool here that could change what it may DO - jarvis_persona has no
    # field for that, by construction.
    "persona_status": "auto", "persona_list": "auto", "persona_set": "auto",
    "persona_write": "change_own_config",
    # ------------------------------------------------ the tool->action gaps
    #
    # 2026-10-03. Ten tools jarvis_agent.py has always offered the model had
    # no entry in this table at all, so action_for_tool() fell through to
    # "unclassified_tool" and every single call asked the owner. That name is
    # in no [autonomy.tiers] line, so it takes this module's own
    # UNKNOWN_TIER ("unknown_action_tier", "ask" in the shipped config): the
    # fallback is fail-safe by design - nothing ran unattended, and this was
    # never a safety hole. It was still wrong: the prompt was never what
    # these tools were meant to do, and a card nobody can act on is how a
    # real card gets ignored. Also here: browser_control, the same gap one
    # tool over - its gate_lookup_name has named jarvis_browser_control_run
    # since browser-control-wiring, and backend/README.md's own section for
    # it says this line belongs in this table.
    #
    # The four keyless integrations (five tools; home is split in two).
    # The four READS are "auto" on exactly the reasoning README.md's
    # browser-control-wiring section records for them: reading the owner's
    # own calendar, inbox, notes or Home Assistant entity state changes
    # nothing, sends nothing to anyone, and reaches only infrastructure the
    # owner runs for themselves - the same "nothing is sent, nothing acts"
    # line every `_plan` entry above is "auto" on. NOT "notify": that is the
    # tier for a write to the agent's own store, and none of these four
    # writes anything. Each still taints the turn as outside text, but that
    # is enforced inside jarvis_agent.py, not by this tier.
    "jarvis_calendar_read_run": "calendar_read",
    "jarvis_email_read_run": "email_read",
    "jarvis_notes_search_run": "notes_search",
    "jarvis_home_read_run": "home_read",
    # home_control is the one of the five that acts on the real world, so it
    # is "ask" and never "auto" - the same line control_browser and
    # control_computer are held to. One entry covers lights, locks, doors,
    # alarms and covers alike; jarvis_home.py's own _is_heavy_service marks
    # the heavy ones heavy inside the plan. A light that should not ask at
    # all is the off-by-default "Lights, plugs and fans without a card"
    # setting, which this tier deliberately does not pre-empt.
    "jarvis_home_control_run": "home_control",
    # browser_control: every step either sends something to a real person or
    # lands on a page nobody has read yet, so control_browser is "ask" and
    # never "auto", exactly as README.md's section says.
    "jarvis_browser_control_run": "control_browser",
    # The scheduler tools (jarvis_schedule.py, reached through
    # jarvis_agent._schedule_call). _one_call intercepts these by name
    # BEFORE the gate, so these lines are never what decides whether a timer
    # asks, and test_agent.py's own outbound loop skips them by name for
    # that reason. They are here so the table is complete and
    # t_every_tool_resolves_to_a_real_jarvis_gate_action stops reporting
    # them; "auto" states what jarvis_agent.py's own SCHEDULE_TOOLS
    # docstring already records as the owner's decision (2026-09-25, and
    # 2026-09-26 for a plain repeating one): a timer, alarm or reminder
    # needs no card, and coming_up only reads the owner's own list back.
    # The stricter case stays where it already lives - _schedule_call
    # refuses to set or change anything in a turn shaped by outside text,
    # whatever this table says.
    "set_timer": "auto", "set_reminder": "auto", "todo_add": "auto",
    "todo_done": "auto", "coming_up": "auto",
}

# Arguments that ESCALATE a shell-class tool. Regex on model-written text is
# allowed to make things stricter, never looser.
_SHELL_NEVER = re.compile(
    r"\bngrok\b|\bcloudflared\b|\blocaltunnel\b|\blt\s+--port|\bbore\b.*\b(?:local|--to)\b|"
    r"\btailscale\s+(?:funnel|serve)\b|\bserveo\b|\bssh\s+-[a-zA-Z]*R\b|\bsocat\b.*\bLISTEN\b|"
    r"\bcurl\b.*\b-X\s*POST\b.*\bhttps?://(?!(?:127\.0\.0\.1|localhost))|"
    r"\bgh\s+release\s+create\b|\bnpm\s+publish\b|\btwine\s+upload\b|\bdocker\s+push\b|"
    r"\bgit\s+push\b", re.I)

# Files the agent must never be able to touch through any tool. If the policy
# and the gate are writable by an action the gate itself approves, there is
# no gate - just a longer path to the off switch.
_PROTECTED = (
    "jarvis-framework.toml", "jarvis_gate.py", "jarvis_framework.py",
    "patch_openjarvis.py", "jarvis_hud.py", "jarvis_router.py",
    "approvals.db", "hud-budget.json", ".openjarvis-patch.json",
)
_PROTECTED_RE = re.compile("|".join(re.escape(x) for x in _PROTECTED), re.I)


def _touches_protected(*blobs) -> Optional[str]:
    for b in blobs:
        if not b:
            continue
        m = _PROTECTED_RE.search(b if isinstance(b, str) else json.dumps(b, default=str))
        if m:
            return m.group(0)
    return None


def action_for_tool(name: str, params: Any = None) -> tuple[str, bool]:
    """Tool name -> action. Arguments can only make the answer stricter."""
    name = (name or "").strip()
    base = _TOOL_ACTIONS.get(name)
    if base is None:
        return "unclassified_tool", False
    if base in _VALID_TIERS:
        # A tier literal rather than an action name. Keep the entry in
        # _SYNTH_TIERS - that is what makes the tier lookup below find it,
        # since a bare name like "calculator" is NOT a key of
        # [autonomy.tiers] and would otherwise fall to UNKNOWN_TIER ("ask",
        # stricter than the "auto" this entry means). Only the NAME RETURNED
        # changes: 2026-10-03.
        #
        # It used to return f"tool:{name}" as well, which renamed the action
        # on its way OUT - the string handed to the checker, written to the
        # audit log, and shown by jarvis_reach.action_of() on "What can Jarvis
        # reach". No config file has ever used that name; three suites
        # expected "calculator" and got "tool:calculator", and the Reach page
        # showed one string when the gate was importable and "calculator"
        # when it was not.
        _SYNTH_TIERS[name] = base
        action = name
    else:
        action = base
    if action in ("run_shell_on_host",) or name in ("code_interpreter", "repl",
                                                    "code_interpreter_docker"):
        blob = params if isinstance(params, str) else json.dumps(params, default=str)
        if _SHELL_NEVER.search(blob):
            return "open_public_tunnel" if re.search(
                r"ngrok|cloudflared|localtunnel|lt\s+--port|bore|funnel|serveo|ssh\s+-\w*R|socat",
                blob, re.I) else "post_to_external_service", True
    return action, True


# Tiers for synthesised tool:<name> actions, filled by action_for_tool.
_SYNTH_TIERS: dict[str, str] = {}

_TOOL_PROMPT = re.compile(
    r"Allow execution of tool '([A-Za-z0-9_\-\.]+)' with args (.*)\?\s*$", re.S)


def _tiers(framework: Optional[dict] = None) -> dict:
    """The tier table, validated. An unrecognised tier string - "Never" with a
    capital, "aks", anything not in _VALID_TIERS - is treated as "never",
    because a typo in a security policy should lock, not unlock."""
    try:
        f = framework if framework is not None else fw.load_framework()
        raw = f.get("autonomy", {}).get("tiers", {}) or {}
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        v = str(v).strip().lower()
        out[k] = v if v in _VALID_TIERS else "never"
    out.update(_SYNTH_TIERS)
    return out


def action_for_prompt(prompt: str,
                      framework: Optional[dict] = None) -> tuple[str, bool]:
    """Map a confirmation prompt onto an action name, choosing the STRICTEST
    interpretation rather than the first one that happens to match.

    The first version walked the list and returned on first hit. That is a
    bypass, and a clean one. draft_email is tier "auto"; send_email is "ask".
    Given

        "Draft reply finalized. Dispatching email to client@example.com."

    the send_email pattern of the day wanted the literal word "send", did not
    find it, and the draft_email pattern matched "draft ... reply" - so an
    outbound email resolved to "auto" and went out with nobody asked. Any
    scheme where a prompt can select a WEAKER tier than something else it also
    matches is broken by construction, no matter how good the individual
    regexes are.

    Two rules fix the class of bug rather than that one instance:
      1. Test every pattern, collect every match, and return the one whose
         tier is strictest.
      2. If the text contains a side-effect verb at all, refuse to return
         anything weaker than "ask", even if no dangerous pattern matched.
         "Dispatching" and "transmit" are not in anyone's synonym list until
         they are, and the point is not to need them to be.
    """
    text = prompt or ""
    tiers = _tiers(framework)
    matched = [name for name, pat in _ACTION_PATTERNS if pat.search(text)]

    if matched:
        strictest = max(matched, key=lambda n: _RANK.get(tiers.get(n, UNKNOWN_TIER), 2))
        rank = _RANK.get(tiers.get(strictest, UNKNOWN_TIER), 2)
        if rank < _RANK["ask"] and _SIDE_EFFECT.search(text):
            # Landed on auto/notify, but the sentence describes doing
            # something irreversible. Do not take the weak reading.
            return "unclassified_side_effect", False
        return strictest, True

    if _SIDE_EFFECT.search(text):
        return "unclassified_side_effect", False
    return "unclassified_action", False


# --------------------------------------------------------------------------
#   The decision
# --------------------------------------------------------------------------

# Every way a gate decision can end. The DB already distinguished these -
# approvals.state is pending|approved|denied|expired - but Verdict did not, so
# by the time a caller saw the answer the only difference between "a person
# said no" and "nobody was there" was the wording of a sentence.
#
# They are not the same and they want different handling. A denial is an
# answer: do not retry, do not ask again, the person decided. A timeout is the
# absence of an answer: it is worth retrying when the owner is back, it is
# worth counting (a run of them means notifications are broken, not that the
# owner is refusing things), and it should read differently on a screen.
# Matching a reason string to tell them apart is what this replaces.
OUTCOMES = frozenset({
    "auto",        # tier auto: ran, no human involved, none required
    "notify",      # tier notify: ran, the human was told afterwards
    "approved",    # a human said yes
    "denied",      # a human said no
    "timed_out",   # NOBODY ANSWERED. Not a refusal. Refused anyway.
    "refused",     # the gate itself refused: never-tier, protected file,
                   # unreadable policy, no queue. No human was ever asked.
})


# Actions whose "no" answers one card, not a standing wish, so a denial
# proposes nothing for them. The proposal reads "I do not want Jarvis to X
# without asking me first" - and each of these ALWAYS asks, and the owner
# started it with a button, so for them every "no" put a sentence in the
# Memory tab that says nothing. How each one comes to ask:
_NO_RULE_FROM_DENIAL = frozenset({
    "pair_device",  # jarvis_devices.py acts only on tier "ask": ONE card per phone paired (devices.patch)
    "unretire_shared_key",  # jarvis_devices.py acts only on tier "ask": bringing the old shared key back (devices.patch)
    "register_approval_key",  # jarvis_devices.py acts only on tier "ask": ONE card per phone that turns on signed approvals (devices.patch)
    "second_card_enable",     # jarvis_second_card.py acts only on tier "ask"
    "second_card_browser_enable",  # jarvis_second_card.py: the same (Browser control)
    "second_card_combined_enable",  # jarvis_second_card.py: the same (both cards, one model)
    "second_card_third_assign",  # jarvis_second_card.py: the same (moves a feature to a third card)
    "chat_card_pin",          # jarvis_second_card.py: the same (pins everyday chat to one card, 2026-10-05)
    "big_model_enable",       # jarvis_big_model.py: the same
    "learning_enable",        # jarvis_learning_switch.py: the same (learning-asks.patch)
    "history_enable",         # jarvis_chat_log.py: the same (chat-history.patch)
    "learning_auto_enable",   # jarvis_auto_learn.py: the same (auto-learn.patch)
    "learning_sensitive_enable",  # jarvis_auto_learn.py: the same
    "custom_voice",           # jarvis_voices.py: the same (add a voice, switch to one)
    "better_voice_enable",    # jarvis_voices.py: the same (the better voice)
    "change_own_config",      # jarvis_voice_enroll.py, jarvis_speech.py: the same
    "modify_own_code",        # jarvis_skill_discovery.py: the same
    "wiki_update",            # shipped "ask"; the owner pressed Add in the wiki
    "download_model",         # shipped "ask"; the owner typed the model's name
    "switch_model",           # shipped "ask"; the owner picked the model
    "models_create",          # jarvis_hardware.py acts only on tier "ask" (hardware.patch)
    "schedule_repeat",        # jarvis_schedule.py acts only on tier "ask" (schedule.patch)
    "search_the_web",         # jarvis_agent.py: this card asks about ONE search's words (web-search.patch)
    "stop_asking_before_every_web_search",    # jarvis_search.py acts only on tier "ask" (web-search.patch)
    "send_email",             # jarvis_agent.py / jarvis_email_send.py: ONE card per email, sent only on tier "ask" (email-send.patch)
    "draft_email",            # jarvis_agent.py / jarvis_email_draft.py: ONE card per draft, saved only on tier "ask" (draft-email.patch)
    "write_notes_after_outside_text",  # jarvis_agent.py: a note after outside text asks every time
    "power_manage",           # shipped "auto": a card means the owner chose "ask"
    "append_obsidian_daily",  # shipped "auto": the same
    "loosen_what_asks_first",  # jarvis_asks_first.py acts only on tier "ask" (asks-first.patch)
    "watch_notifications_enable",  # jarvis_watch_notify.py acts only on tier "ask" (watch-notifications.patch)
    "enable_reading_tool",  # jarvis_asks_first.py acts only on tier "ask" (tools-enable.patch)
    "restore_backup",  # jarvis_backup.py acts only on tier "ask" (backup.patch)
    "phone_notifications_read",  # jarvis_phone_notifications.py acts only on tier "ask" (phone-notifications.patch)
    "chatbot_session",  # jarvis_chatbot.py acts only on tier "ask": ONE card per conversation (chatbot.patch)
    "memory_forget_range",  # jarvis_forget_range.py acts only on tier "ask": ONE card per time frame (forget-range.patch)
    "support_chat",  # jarvis_support.py acts only on tier "ask": ONE card per support chat, listing every detail it may give (support-chat.patch)
    "support_offer",  # jarvis_support.py acts only on tier "ask": ONE card per offer; nothing is accepted without it (support-chat.patch)
    "app_merge_change",  # jarvis_apps.py acts only on tier "ask": ONE card per change added to an app (apps-in-projects.patch)
    "tidy_inbox",  # jarvis_inbox_tidy.py / jarvis_agent.py acts only on tier "ask": ONE card per tidy, listing every email (inbox-tidy.patch)
    "screen_picture_enable",  # jarvis_screen_picture.py acts only on tier "ask": ONE card to turn on slow picture reading (screen-picture.patch)
    "obscura_enable",  # jarvis_browser_engine.py acts only on tier "ask": ONE card to turn on the headless browser, Obscura (browser-engine.patch)
    "browser_form_submit",  # jarvis_form_review.py / jarvis_agent.py acts only on tier "ask": ONE card, before the click that sends a filled-in form, showing the site, every word typed and a picture of the page (form-review.patch)
    "web_search_enable",  # jarvis_search.py acts only on tier "ask": ONE card to turn web search back on after the owner switched it off (web-search-switch.patch)
    "topic_loosen",  # jarvis_topics.py acts only on tier "ask": ONE card to turn a private topic back on (topics.patch)
    "referee_tick",  # jarvis_referee.py acts only on tier "ask": ONE card per goal step whose number reached its target; only the owner's tap ticks it (referee.patch)
    "chat_tags_suggest_on",  # jarvis_tag_suggest.py acts only on tier "ask": ONE card to let the local model read a few old chats at night to suggest tags (tag-suggest.patch)
    "chat_tag_suggest",  # jarvis_tag_suggest.py acts only on tier "ask": ONE card per suggested tag for one chat; only the owner's tap files it (tag-suggest.patch)
    "youtube_captions_read",  # jarvis_youtube.py acts only on tier "ask": ONE card per YouTube link; caption text only, and it breaks YouTube's terms (youtube.patch)
    "quiz_cloud_grade",  # jarvis_quiz_cloud.py acts only on tier "ask": ONE card per "grade this better" request; it lists exactly what leaves the PC and bends rule 1 for that one quiz (quiz-cloud.patch)
    "read_web_page",  # jarvis_readpage.py acts only on tier "ask": ONE card per address the owner hands over; one GET of that one page, its words read out as outside text (readpage.patch)
})


def _propose_constraint_from_denial(action: str, detail: dict) -> None:
    """Turns a "no" into a candidate standing rule - never an applied one.

    Called from the two DENIED branches below, never from timed_out: a
    timeout is the absence of an answer, and proposing a rule from silence
    would teach Jarvis something nobody actually decided.

    Goes through propose(), the one choke point this project already has
    for every fact it ever learns - memory-safety.patch removed the single
    auto-accept path that used to exist inside it, for exactly this reason.
    A denial writing straight to memory would be a second, parallel door
    into the same room: the shape of bug no-auto-approve.patch found and
    fixed for tier confirmation, one module over. So this only ever
    PROPOSES - the same review queue that already holds every extracted
    fact, "Keep" or "Discard" in the Brain window's Memory tab, one at a
    time, same as always.

    Best-effort by design: a failed or skipped proposal must never turn a
    completed denial into an error the owner has to do something about.
    """
    if action in _NO_RULE_FROM_DENIAL:
        return  # see _NO_RULE_FROM_DENIAL: this "no" was about one card
    try:
        import jarvis_extract
    except Exception:
        return  # memory layer not importable - nothing to propose into
    readable = str(action or "an action").replace("_", " ").strip() or "an action"
    turns = [{"role": "user", "content":
              f"Remember this: I do not want Jarvis to {readable} without "
              f"asking me first. I just said no when it asked."}]
    try:
        jarvis_extract.propose(turns, source="gate_denial")
    except Exception:
        pass


# owner-check.patch (docs/APPROVAL-GAP-DESIGN.md step 1, the owner's decision
# of 2026-09-25). An "approved" row counts only when THIS running backend
# accepted the approval through its own POST /api/approve - after Windows
# Hello, for a risky card from this PC - and stamped it there
# (jarvis_owner_check.py). The stamp's secret is made fresh at every start
# and lives only in this process's memory. So "approved" written straight
# into approvals.db by another program has no stamp, and is refused.
def _approval_stamped(rid, action) -> bool:
    """True, once, when this process stamped the approval of `rid`. Fails
    closed: without jarvis_owner_check.py nothing is stamped, so nothing
    that waits here is approved - apply-patches.ps1 copies it in."""
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.take_stamp(rid, action))
    except Exception:
        return False


def _unstamped_approval(rid, tier, action, row):
    """The Verdict for an "approved" row this process never stamped. Refused,
    not denied: no person said no, and a denial would propose a rule."""
    try:
        by = row["decided_by"]
    except Exception:
        by = None
    _audit("gate.unstamped_approval", {"id": rid, "action": action, "by": by})
    return Verdict(False, tier, action,
                   "it was marked approved, but not through Jarvis's own approval "
                   "check (POST /api/approve on this PC), so it was refused", rid,
                   outcome="refused")


@dataclass
class Verdict:
    allowed: bool
    tier: str
    action: str
    reason: str
    request_id: Optional[str] = None
    # Defaults to "refused", never to anything permissive. codex does the same
    # thing at the type level - `impl Default for ReviewDecision` returns
    # Denied - and the reasoning carries: a field that is forgotten at a new
    # construction site must fail closed, and a default of "approved" would
    # make forgetting it silently grant. See docs/PEERS.md.
    outcome: str = "refused"

    def __post_init__(self) -> None:
        # A typo in an outcome must not become a new, unhandled state that
        # every `if outcome == ...` silently falls through. Coerced rather
        # than raised: this runs on the path that decides whether a tool may
        # act, and an exception here would fail the action in a way that looks
        # like a crash rather than a refusal.
        if self.outcome not in OUTCOMES:
            self.outcome = "refused"
        # The invariant that matters more than any of the above: only two
        # outcomes may carry allowed=True, and "timed_out" is not one of them.
        if self.allowed and self.outcome not in ("auto", "notify", "approved"):
            self.allowed = False

    @property
    def timed_out(self) -> bool:
        """Nobody answered. Distinct from being told no."""
        return self.outcome == "timed_out"

    def as_dict(self) -> dict:
        return asdict(self)


_SAFE_KEYS = {"id", "action", "tier", "classified", "error", "by", "state"}


def _redact(detail: dict) -> dict:
    """[logging].redact_private_content_in_logs says to record that a gate
    fired, never the private text that tripped it. The gate is handed exactly
    the sensitive part - the recipient of the email, the path of the file, the
    body of the shell command - so writing `detail` verbatim would turn the
    audit trail into the leak it exists to detect. Keep the shape, drop the
    values."""
    try:
        if not fw.load_framework().get("logging", {}).get(
                "redact_private_content_in_logs", True):
            return detail
    except Exception:
        pass                                  # unreadable config -> redact
    out = {}
    for k, v in (detail or {}).items():
        if k in _SAFE_KEYS or isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = {"<redacted keys>": sorted(v.keys())[:12]}
        elif isinstance(v, str):
            out[k] = f"<redacted {len(v)} chars>"
        else:
            out[k] = f"<redacted {type(v).__name__}>"
    return out


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, _redact(detail))
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Content risk: outside text can raise a tier, never lower one
# --------------------------------------------------------------------------
# The approval-fatigue literature is blunt about this: attackers engineer
# fatigue deliberately, and the phrasing that does it is cheap to detect and
# needs no model. "Just approve these", "no need to check each one", "quick,
# before it expires" are not neutral words in a tool result - they are an
# attempt to make the reader decide faster than they would have. So they cost
# the sender something: while a rush latch holds, an auto-tier action stops
# and asks.
#
# Failing open is correct here and only here. If the content-risk module is
# missing or its state file is unreadable, the tier falls back to the table -
# never below it. A rule that can only raise cannot be made unsafe by being
# unavailable.

def _content_raise(tier: str, action: str) -> tuple[str, Optional[dict]]:
    try:
        import jarvis_content_risk as cr
        new_tier, latch = cr.raise_tier(tier)
    except Exception:
        return tier, None
    if not latch:
        return tier, None
    chip = cr.chip_from(latch)
    chip["from_tier"], chip["to_tier"] = tier, new_tier
    if new_tier != tier:
        _audit("gate.tier_raised", {"action": action, "from": tier,
                                    "to": new_tier, "why": "rushed",
                                    "source": chip["source"]})
    return new_tier, chip


def filter_tool_result(name: str, content: Any) -> Any:
    """Every tool result, before the model reads it.

    A tool result is outside text: a web page, a mail body, a file someone
    else wrote. It is data, so it is never refused - but it is normalised, so
    invisible instructions never reach the model's context at all, and it is
    scanned, so a rushing phrase inside it latches the gate before the next
    action is proposed rather than after it has run.

    Returns the content to use. Any failure returns the content unchanged:
    breaking a tool call to enforce a hygiene rule is the wrong trade.
    """
    if not isinstance(content, str) or not content:
        return content
    try:
        import jarvis_content_risk as cr
        out = cr.vet_tool_result(name, content)
    except Exception:
        return content
    if out.get("rushed"):
        _audit("gate.result_rushed", {"tool": name,
                                      "phrase": (out.get("reason") or {}).get("quote", "")})
    return out.get("text", content)


def check(action: str,
          detail: Optional[dict] = None,
          prompt: str = "",
          timeout: Optional[float] = None,
          framework: Optional[dict] = None) -> Verdict:
    """The single entry point. Blocks only for the "ask" tier."""
    detail = detail or {}
    try:
        tiers = _tiers(framework)
        if not tiers:
            # Either the file is gone or every tier failed validation. There
            # is no reading of "no policy" under which a tool call is safe.
            raise RuntimeError("autonomy tier table is empty")
        tier = tiers.get(action, UNKNOWN_TIER)
    except Exception as exc:
        # Cannot read the policy -> cannot claim the action is permitted.
        _audit("gate.policy_unreadable", {"action": action, "error": str(exc)})
        return Verdict(False, "unknown", action,
                       f"autonomy policy could not be read ({exc})",
                       outcome="refused")

    # The one rule above the tier table: nothing gets to edit the tier table.
    hit = _touches_protected(prompt, detail)
    if hit:
        _audit("gate.refused_protected", {"action": action, "file": hit})
        return Verdict(False, "never", action,
                       f"this touches {hit}, which no tool may modify; "
                       f"edit it by hand", outcome="refused")

    # Outside text that tried to rush the reader raises the effective tier of
    # whatever comes next. One direction only: this can turn auto into ask, it
    # can never turn ask into auto. Applied after the protected-file check so
    # "never" stays never, and before the tier branches so an auto-tier action
    # that would have run silently stops and asks instead.
    raised = None
    if tier != "never":
        tier, raised = _content_raise(tier, action)

    if tier == "never":
        _audit("gate.refused", {"action": action, "tier": tier, "detail": detail})
        return Verdict(False, tier, action,
                       "this action is set to 'never' in jarvis-framework.toml; "
                       "changing it means editing that file, not asking here",
                       outcome="refused")

    # Any joplin action at all - including a read on the "auto" tier - pins
    # the conversation local. Done before the tier branches so it happens even
    # on the paths that return immediately.
    if "joplin" in action:
        latch_taint(why=action)

    if tier == "auto":
        _audit("gate.auto", {"action": action, "detail": detail})
        return Verdict(True, tier, action, "tier is auto", outcome="auto")

    if tier == "notify":
        _audit("gate.notify", {"action": action, "detail": detail})
        # _redact, not the raw detail. This module's own _redact docstring says
        # the gate "is handed exactly the sensitive part - the recipient of the
        # email, the path of the file, the body of the shell command - so
        # writing `detail` verbatim would turn the audit trail into the leak it
        # exists to detect". That was true of the local audit log and the code
        # honoured it; the push sent the identical dict, verbatim, to a public
        # broker. An ntfy.sh topic is a URL with no authentication: anyone who
        # knows or guesses the string reads every message. On this tier there
        # is no human in the loop at all, so nothing else was going to catch it.
        _push(f"Jarvis did: {action}", risk_for(action)["why"])
        return Verdict(True, tier, action, "tier is notify; you were told after",
                       outcome="notify")

    # ---- "ask", and anything unrecognised, waits for a human ----
    try:
        _init()
        rid = uuid.uuid4().hex[:12]
        now = time.time()
        with closing(_connect()) as c:
            c.execute(
                "INSERT INTO approvals (id,action,tier,detail,prompt,state,created,raised)"
                " VALUES (?,?,?,?,?,'pending',?,?)",
                (rid, action, tier, json.dumps(detail)[:4000], (prompt or "")[:2000], now,
                 json.dumps(raised)[:1000] if raised else None))
    except Exception as exc:
        _audit("gate.queue_unavailable", {"action": action, "error": str(exc)})
        return Verdict(False, tier, action,
                       f"approval queue unavailable, so the action is refused ({exc})",
                       outcome="refused")

    _audit("gate.asked", {"id": rid, "action": action, "tier": tier, "detail": detail})
    # An unclassified action is safe (it became "ask") but opaque: you cannot
    # improve the pattern table without knowing what phrasing missed. Recording
    # the prompt is opt-in because it is prompt text, which redaction otherwise
    # keeps off disk entirely.
    if action.startswith("unclassified") and prompt:
        try:
            if fw.load_framework().get("logging", {}).get(
                    "log_unclassified_prompts", False):
                fw.audit_log("gate.unclassified_prompt",
                             {"id": rid, "action": action, "prompt": prompt[:500]})
        except Exception:
            pass
    # The notification is a doorbell, not the content - the same rule the SSE
    # approval event follows. `prompt` is the human-readable request text and
    # can quote an email body or a file path; the fallback to it was the wider
    # of the two leaks, because it is prose rather than a dict of keys.
    # _safe_detail printed the field NAMES and nothing else - "fields: args,
    # tool" - which is safe and tells a person nothing they can act on. The
    # notice says what and why in a sentence, and is safe for the stronger
    # reason: it is built from this module's own tables and never reads the
    # payload at all. _safe_detail stays for callers that have no action name.
    _note = notice_for({"action": action, "raised": bool(raised)})
    _push(_note["title"],
          _note["body"] + f"\n(id {rid}) - open Jarvis to decide")

    deadline = time.time() + (APPROVAL_TIMEOUT if timeout is None else timeout)
    # One connection for the whole wait rather than one per poll.
    watch = None
    try:
        try:
            watch = _connect()
        except Exception:
            watch = None
        while time.time() < deadline:
            time.sleep(POLL_SECONDS)
            try:
                if watch is None:
                    watch = _connect()
                row = watch.execute(
                    "SELECT state,decided_by FROM approvals WHERE id=?",
                    (rid,)).fetchone()
            except Exception:
                # Drop a connection that has gone bad and try a fresh one next
                # time round, rather than spinning on a dead handle.
                try:
                    if watch is not None:
                        watch.close()
                except Exception:
                    pass
                watch = None
                continue
            if row is None:
                break
            if row["state"] == "approved":
                # owner-check.patch: only an approval this process stamped.
                # Deny needs no stamp - refusing is always the safe direction.
                if not _approval_stamped(rid, action):
                    return _unstamped_approval(rid, tier, action, row)
                _audit("gate.approved", {"id": rid, "action": action,
                                         "by": row["decided_by"]})
                return Verdict(True, tier, action, "approved by a human", rid,
                               outcome="approved")
            if row["state"] == "denied":
                _audit("gate.denied", {"id": rid, "action": action,
                                       "by": row["decided_by"]})
                _propose_constraint_from_denial(action, detail)
                return Verdict(False, tier, action, "denied by a human", rid,
                               outcome="denied")
    finally:
        if watch is not None:
            try:
                watch.close()
            except Exception:
                pass

    # A human can answer in the gap between the last poll and this UPDATE.
    # The WHERE guard means their row is not overwritten - but the old code
    # then returned "expired" anyway, so the DB said approved, the HUD said
    # approved, the audit said expired, and the action did not run. Honour a
    # decision that landed late rather than pretending it did not.
    try:
        with closing(_connect()) as c:
            cur = c.execute("UPDATE approvals SET state='expired', decided=?"
                            " WHERE id=? AND state='pending'", (time.time(), rid))
            if cur.rowcount == 0:
                row = c.execute("SELECT state,decided_by FROM approvals WHERE id=?",
                                (rid,)).fetchone()
                if row and row["state"] == "approved":
                    if not _approval_stamped(rid, action):
                        return _unstamped_approval(rid, tier, action, row)
                    _audit("gate.approved", {"id": rid, "action": action,
                                             "by": row["decided_by"], "late": True})
                    return Verdict(True, tier, action, "approved by a human", rid,
                                   outcome="approved")
                if row and row["state"] == "denied":
                    _audit("gate.denied", {"id": rid, "action": action,
                                           "by": row["decided_by"], "late": True})
                    _propose_constraint_from_denial(action, detail)
                    return Verdict(False, tier, action, "denied by a human", rid,
                                   outcome="denied")
    except Exception:
        pass
    _audit("gate.expired", {"id": rid, "action": action})
    # Refused, because an unanswered request must not run. But recorded as
    # timed_out rather than denied: nobody decided anything here, and a caller
    # that retries on the owner's return is behaving correctly where retrying
    # a denial would not be.
    return Verdict(False, tier, action,
                   "nobody answered in time, so it was refused", rid,
                   outcome="timed_out")


def confirm(prompt: str) -> bool:
    """Drop-in for OpenJarvis's `confirm_callback=lambda _prompt: True`.

    Same signature, same return type, but it consults the policy and waits
    for a human when the policy says to. An unrecognised prompt maps to
    "unclassified_action", which is not in [autonomy.tiers] and therefore
    resolves to UNKNOWN_TIER - "ask". So the worst case of a bad guess is an
    extra confirmation, never a silent execution.
    """
    action, confident, detail = _classify_prompt(prompt)
    v = check(action, detail, prompt=prompt)
    if not v.allowed:
        print(f"  [gate] refused {action}: {v.reason}", file=sys.stderr, flush=True)
    return v.allowed


def _classify_prompt(prompt: str) -> tuple[str, bool, dict]:
    """Turn OpenJarvis's confirmation prompt into (action, confident, detail).

    The detail dict is what the human sees on the approval card. The first
    version passed {"classified": true} - which the HUD then rendered INSTEAD
    of the prompt, so a person approving `rm -rf ~/Documents` was shown a
    boolean. What they need is the tool and its arguments.
    """
    m = _TOOL_PROMPT.search(prompt or "")
    if m:
        name, raw_args = m.group(1), m.group(2).strip()
        action, confident = action_for_tool(name, raw_args)
        return action, confident, {"tool": name, "args": raw_args[:1500]}
    action, confident = action_for_prompt(prompt)
    return action, confident, {"prompt": (prompt or "")[:1500]}


def gate_tool(name: str, params: Any) -> Optional[str]:
    """The hook for ToolExecutor.execute: every tool, by name, before it runs.

    Returns None to allow, or a refusal message to hand back as the tool's
    result. This is the entry point that closes the two structural gaps the
    audit found: OpenJarvis only asked for confirmation on three of its ~50
    tools, and the agent the HUD talks to was built with no confirmation
    callback at all - so the tier table governed almost nothing on the path
    that mattered. Called from inside execute(), it sees every call.
    """
    action, _ = action_for_tool(name, params)
    detail = {"tool": name, "args": (params if isinstance(params, str)
                                     else json.dumps(params, default=str))[:1500]}
    v = check(action, detail, prompt=f"tool {name} {detail['args']}")
    if v.allowed:
        return None
    if v.timed_out:
        # Said differently from a denial ON PURPOSE. This string goes back to
        # the model as the tool result, and "denied" tells it to find another
        # way - which, for a tool the owner would have approved, means working
        # around a gate that was never actually answered. "Nobody was there"
        # tells it the truth and tells it what to do instead.
        return (f"Not run: {name} needed your approval and nobody answered in "
                f"time, so it was refused. Nothing was decided - ask again "
                f"when the owner is at the machine.")
    return (f"Refused by the autonomy gate: {name} is tier '{v.tier}' "
            f"({v.action}) - {v.reason}")


# --------------------------------------------------------------------------
#   Taint latch
# --------------------------------------------------------------------------
# The privacy rule says a turn that touched personal material stays on the
# local model. The proxy enforces that by scanning the message payload - but
# the proxy only sees what the client sends it, and a tool result that
# OpenJarvis keeps in its own context never arrives. The gate DOES see the
# tool call, so this is where the fact gets recorded.
#
# It is deliberately a GLOBAL latch rather than a per-conversation one: there
# is no conversation id in the payload to key on, and for a single-user local
# assistant the over-approximation is the right way to be wrong. After a
# Joplin read, everything stays local for taint_latch_minutes. The cost is
# some public questions answered by the local model; the alternative cost is
# personal material reaching a cloud lane.

def latch_taint(minutes: Optional[float] = None, why: str = "") -> bool:
    if minutes is None:
        minutes = float(_cfg("notes.joplin", "taint_latch_minutes", 30) or 30)
    try:
        _init()
        until = time.time() + max(0.0, float(minutes)) * 60.0
        with closing(_connect()) as c:
            row = c.execute("SELECT until FROM taint WHERE key='conversation'").fetchone()
            if row and row["until"] > until:
                return True                   # never shorten an existing latch
            c.execute("INSERT INTO taint (key, until, why) VALUES ('conversation',?,?) "
                      "ON CONFLICT(key) DO UPDATE SET until=excluded.until, why=excluded.why",
                      (until, why[:200]))
        _audit("gate.taint_latched", {"minutes": minutes, "why": why})
        return True
    except Exception:
        return False


def taint_active() -> bool:
    """True while the latch holds. A failure to read it returns True, because
    the safe answer to "is this conversation private?" when you cannot tell is
    yes."""
    try:
        _init()
        with closing(_connect()) as c:
            row = c.execute("SELECT until FROM taint WHERE key='conversation'").fetchone()
        return bool(row and row["until"] > time.time())
    except Exception:
        return True


def clear_taint() -> bool:
    try:
        _init()
        with closing(_connect()) as c:
            c.execute("DELETE FROM taint WHERE key='conversation'")
        _audit("gate.taint_cleared", {})
        return True
    except Exception:
        return False


def confirm_auto(prompt: str) -> bool:
    """THIS NO LONGER BYPASSES ANYTHING. It is `confirm` with a warning.

    What it used to be, and why that was wrong
    ------------------------------------------
    It existed for OpenJarvis call sites like

        if auto_approve:
            executor._confirm_callback = lambda _prompt: True

    behind a `--auto-approve` CLI flag, and its own docstring argued that
    routing those through the gate "would silently redefine a documented
    flag". So it returned True for tiers auto, notify AND **ask**, refusing
    only `never`.

    That is an approve-all. Not by analogy - by definition. `ask` means a
    human decides one action at a time, and this granted every future,
    unnamed `ask` action for the life of the process on the strength of one
    flag typed once. docs/ARCHITECTURE.md invariant 3 is "No auto-approve
    anywhere, and no approve-all control anywhere. One action, one decision.
    Do not build one." This was one, and it shipped inside the module that
    enforces the rule.

    It had zero callers, which is the only reason it never granted anything.
    A blanket grant with no caller is still a blanket grant: the next person
    to wire up `--auto-approve` would have found it sitting here looking
    intended, with a docstring explaining why it was fine.

    Found by `test_gate_outcome.t_there_is_still_no_approve_all`, on that
    test's first run. docs/PEERS.md is the reason that test exists: every
    comparable project ships a blanket grant, and cline's docs still describe
    auto-approve toggles their UI removed months earlier. A prose claim about
    code goes stale, or is wrong from the start. This one was wrong from the
    start.

    What it is now
    --------------
    A delegation to `confirm`, so the symbol still resolves - anything on the
    owner's machine that wired it up keeps working, it just asks. The flag
    becomes a no-op rather than a bypass, and says so on stderr once, because
    a flag that silently stopped working is its own kind of lie.

    The old docstring's objection stands and is answered rather than ignored:
    yes, this redefines a documented flag. The flag's documentation is not the
    authority here; the invariant is. A tool that asks when you told it not to
    is a nuisance. A tool that acts when you would have said no is the thing
    the gate exists to prevent.
    """
    global _AUTO_FLAG_WARNED
    if not _AUTO_FLAG_WARNED:
        _AUTO_FLAG_WARNED = True
        print("  [gate] --auto-approve does not skip approvals in Jarvis. "
              "Every 'ask' action still waits for you, one at a time. "
              "See docs/ARCHITECTURE.md invariant 3.",
              file=sys.stderr, flush=True)
    _audit("gate.auto_flag_ignored", {"prompt_len": len(prompt or "")})
    return confirm(prompt)


# Printed once per process, not once per call: a flag that is set stays set,
# and a warning on every tool call would train the reader to ignore it.
_AUTO_FLAG_WARNED = False


# --------------------------------------------------------------------------
#   The other side: what the HUD endpoints call
# --------------------------------------------------------------------------

def pending() -> list[dict]:
    """Every waiting approval, each carrying what it costs to get wrong.

    risk is attached here rather than stored on the row so that refining the
    classification improves every pending item at once, including ones queued
    before the refinement existed.
    """
    _init()
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"
            " WHERE state='pending' ORDER BY created").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["risk"] = risk_for(d.get("action", ""))
        # Computed here rather than in each client, so the phone and the
        # desktop cannot word the same warning two different ways - and so
        # there is one place to audit what a notification may contain.
        d["notice"] = notice_for(d)
        # approval-expiry.patch: how many seconds this card has left before
        # check() stops waiting and refuses it. check() waits APPROVAL_TIMEOUT
        # from just after the row is written, so `created` plus that is the
        # deadline. Sent as seconds LEFT, not a clock time, so a phone whose
        # clock disagrees with this PC still counts down correctly. A row
        # whose `created` is not a number gets no field, and the clients then
        # show no countdown rather than a wrong one.
        try:
            d["expires_in"] = max(0, int(float(d.get("created"))
                                         + float(APPROVAL_TIMEOUT)
                                         - time.time()))
        except (TypeError, ValueError):
            pass
        # Why this is being asked about at all, when the table said otherwise.
        # A card shows this instead of a coloured dot: the reason is the thing
        # that changes the decision.
        raw = d.pop("raised", None)
        d["raised"] = None
        if raw:
            try:
                d["raised"] = json.loads(raw)
            except Exception:
                d["raised"] = None
        out.append(d)
    return out


def decide(request_id: str, approved: bool, by: str = "hud") -> bool:
    """Returns False if the id is unknown or already decided, so a double tap
    on Approve cannot resurrect something that already timed out."""
    _init()
    with closing(_connect()) as c:
        # Once decided, the prompt and detail have done their job. Keeping a
        # verbatim shell command or recipient list in this table for ever
        # would make it the unredacted twin of the audit log.
        cur = c.execute(
            "UPDATE approvals SET state=?, decided=?, decided_by=?,"
            " prompt=NULL, detail=NULL"
            " WHERE id=? AND state='pending'",
            ("approved" if approved else "denied", time.time(),
             str(by or "hud")[:64], request_id))
        return cur.rowcount > 0


def history(limit: int = 50) -> list[dict]:
    _init()
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT id,action,tier,state,created,decided,decided_by FROM approvals"
            " ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
#   Push (optional)
# --------------------------------------------------------------------------

NTFY_TOPIC = os.environ.get("JARVIS_NTFY_TOPIC", "").strip()
# No default destination. "https://ntfy.sh" used to be the fallback, so an
# owner who set only a topic - which is all the setup notes ever asked for -
# had every card title posted to a public broker they never chose. Rule 1
# says private things stay on this PC, and a place the owner did not pick is
# not one they agreed to. Empty means NOWHERE: set this to your own ntfy (or
# whichever service you chose) to have phone alerts again.
NTFY_SERVER = os.environ.get("JARVIS_NTFY_SERVER", "").rstrip("/")


def _safe_detail(detail: dict, limit: int) -> str:
    """What may be written into a push body. Never the values.

    This is NOT `json.dumps(_redact(detail))`, and the difference is the whole
    point. `_redact` opens with

        if not fw.load_framework().get("logging", {}).get(
                "redact_private_content_in_logs", True):
            return detail

    so a key named for LOGS - which someone might plausibly switch off while
    debugging something on their own machine - would also switch off redaction
    on a path that posts to a public, unauthenticated broker. Those are not the
    same decision and must not share a switch: an on-disk log is behind the
    file system, an ntfy.sh topic is behind a guess.

    So this redacts unconditionally, and it keeps only the KEYS. _redact keeps
    the shape, which is right for an audit trail you can read later; a push
    body needs less than that. It also avoids json.dumps, so a value that will
    not serialise cannot raise on a path whose whole promise is that it cannot
    break the gate.
    """
    try:
        keys = sorted(str(k) for k in (detail or {}))
    except Exception:
        return "(details withheld)"
    if not keys:
        return "(no details)"
    return ("fields: " + ", ".join(keys))[:limit]


def _push(title: str, body: str) -> None:
    """Best effort, and deliberately not on the critical path: a phone that
    cannot be reached must not stop the desktop HUD from asking.

    Callers must pass an ALREADY REDACTED body - use _safe_detail above. This
    function cannot redact for itself: it takes a string, by which point the
    shape is gone. The rule lives at the two call sites and this docstring
    exists to keep it there.

    WHERE IT GOES: NOWHERE, unless the owner set BOTH JARVIS_NTFY_TOPIC (which
    channel) and JARVIS_NTFY_SERVER (where that channel lives). The server
    used to default to ntfy.sh - a public broker whose topic name is the only
    secret, travelling in a URL, so anyone who guesses it subscribes. That is
    fine for "something is waiting" and wrong as the default, because it means
    the owner never chose a destination at all.
    """
    # Both, or nothing. A topic with no server is a channel with no
    # destination, and the old default quietly supplied one.
    if not NTFY_TOPIC or not NTFY_SERVER:
        return
    # Never while the conversation is latched local. The latch exists because
    # private content is in play; a push is egress to a third party, which is
    # the exact thing the latch is refusing. Fails closed: taint_active()
    # returns True when it cannot read its own database.
    try:
        if taint_active():
            return
    except Exception:
        return

    def send():
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{NTFY_SERVER}/{NTFY_TOPIC}",
                data=body.encode("utf-8"),
                headers={"Title": title[:120], "Priority": "high"},
                method="POST")
            urllib.request.urlopen(req, timeout=5).close()
        except Exception:
            pass

    threading.Thread(target=send, daemon=True).start()


# --------------------------------------------------------------------------
#   python jarvis_gate.py --review
# --------------------------------------------------------------------------

def review(days: int = 7) -> int:
    """What the gate has been doing, and where its classifier is guessing.

    The classifier failing is not a security problem - an unclassified action
    becomes "ask". It is a NUISANCE problem, and nuisance is how approval
    systems die: asked about everything, you stop reading and start clicking.
    So this reports which phrasings it could not place, to be turned into
    patterns.
    """
    import collections
    import datetime as _dt
    try:
        cfg = fw.load_framework().get("logging", {})
        log_dir = Path(os.path.expanduser(cfg.get("log_directory", str(fw.LOG_DIR))))
    except Exception:
        log_dir = Path(fw.LOG_DIR)
    if not log_dir.is_dir():
        print(f"  No log directory at {log_dir}")
        return 1

    cutoff = _dt.date.today() - _dt.timedelta(days=days)
    events, actions, unclassified = collections.Counter(), collections.Counter(), []
    for f in sorted(log_dir.glob("*.jsonl")):
        try:
            if _dt.date.fromisoformat(f.stem) < cutoff:
                continue
        except ValueError:
            pass
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ev = rec.get("event", "")
            if not ev.startswith("gate."):
                continue
            events[ev] += 1
            d = rec.get("detail") or {}
            if d.get("action"):
                actions[(d["action"], ev.split(".", 1)[1])] += 1
            if ev == "gate.unclassified_prompt" and d.get("prompt"):
                unclassified.append(d["prompt"])

    if not events:
        print(f"  No gate activity in the last {days} days.")
        return 0
    print(f"\n  Gate activity, last {days} days ({log_dir})\n")
    for ev, n in events.most_common():
        print(f"    {n:5}  {ev}")
    print("\n  By action:\n")
    for (act, outcome), n in actions.most_common(20):
        print(f"    {n:5}  {act:28} {outcome}")

    asked = sum(n for (a, o), n in actions.items() if o == "asked")
    unk = sum(n for (a, o), n in actions.items()
              if o == "asked" and a.startswith("unclassified"))
    if asked:
        print(f"\n  {unk}/{asked} of the prompts you were asked about could not be "
              f"classified ({unk * 100 // asked}%).")
        if unk and not unclassified:
            print("  Set log_unclassified_prompts = true in [logging] to see which")
            print("  phrasings, then come back here. Turn it off again afterwards.")
    if unclassified:
        print("\n  Prompts the classifier could not place - add patterns for the")
        print("  recurring ones to _ACTION_PATTERNS in this file:\n")
        for p, n in collections.Counter(unclassified).most_common(25):
            print(f"    {n:3}x  {p[:96]}")
    print()
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Approval gate: status and tuning.")
    ap.add_argument("--review", action="store_true",
                    help="summarise gate activity and unclassified prompts")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--pending", action="store_true", help="list waiting actions")
    a = ap.parse_args()
    if a.pending:
        for r in pending():
            print(f"  {r['id']}  {r['tier']:6} {r['action']}")
        sys.exit(0)
    sys.exit(review(a.days))
