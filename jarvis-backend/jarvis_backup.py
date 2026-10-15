"""jarvis_backup.py - one locked backup file, a recovery code, restore with a
card (the owner's decision of 2026-09-27, CLAUDE.md; the design in
docs/CUTTING-EDGE-2026-09-26-round2-trust.md, "2. Encrypted backup and plain
restore"). docs/JARVIS-API.md section 45.

NEW MODULE, shipped whole. backup.patch adds one call at start-up,
`install(Handler, ...)`, which answers the nine routes below (the same shape
as jarvis_documents.py).

THE PHONE'S HALF (2026-10-13, the owner asked for a "Back up now" button on
the phone on 2026-10-10 and was told why not - this is the answer built for
real). Three routes: `STATUS_ROUTE` (read-only, any paired device) says what
the folder holds; `PREPARE_ROUTE` (any paired device) mints this run's one-time
recovery code and writes NOTHING; `COMMIT_ROUTE` (this PC only) writes the file
when the owner says he has kept the code - with that same code, so the code he
kept is the code that opens it. See PREPARE_ROUTE's own comment for why it is
two calls rather than one: an unfinished run must leave the folder exactly as
it was, because a new backup DELETES the oldest of the KEEP, and a file nobody
can open is worse than no new file at all.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-27, answering
docs/OWNER-QUESTIONS-2026-09-27.md): "one locked backup file into a folder
the owner picks, a NordLocker (or other cloud-synced) folder included.
Locked with a recovery code only the owner has (shown once); Jarvis keeps
only the last few. This bends rule 1 for that one locked file only, and the
app must say plainly that a lost code means a useless backup and that
erased facts stay in older backups until they age out."

THIS BENDS RULE 1 (docs/ARCHITECTURE.md invariant 1), on purpose, for this
one file only: a folder the owner picks can be one a cloud-sync program
(NordLocker, OneDrive, ...) uploads. Jarvis itself sends nothing anywhere -
it only writes one encrypted file to a folder on this PC, exactly as
"Folders Jarvis may look in" does - but if that folder is synced, the sync
program uploads it, the same as anything else the owner puts there. That is
the whole exception: one named file, encrypted before it is written, never
readable without a recovery code only the owner ever holds.

THE FOLDER - reused exactly, "Folders Jarvis may look in"'s own picker
  * Setting it: only from this PC (jarvis_owner_check.from_this_pc), ONE
    approval card (action `change_own_config`, tier "ask" only - the same
    action jarvis_documents.py uses for adding a folder). Refused for the
    same places `jarvis_documents.check_folder` refuses (a drive's top, the
    whole user folder, Windows' folders, protected places): imported from
    there, not copied, so the two lists of refusals can never drift apart.
    A NordLocker-synced folder is an ordinary folder to Windows, so nothing
    special is needed for it.
  * "Back up now": no card. The owner already approved the folder, and
    pressing the button on the PC is the same shape as the Notion import
    (jarvis_documents.py) - an explicit action the owner started, writing
    only into a folder already on the list.

WHAT IS BACKED UP - verified against this repository's real file names,
2026-09-27 (the design doc's names had drifted: it said "history.db"; the
real file, made by jarvis_chat_log.py, is "chat-history.db")
  * The SQLite databases in SOURCE_DBS, snapshotted with the online backup API
    (`sqlite3.Connection.backup`, safe while Jarvis keeps them open):
    memory.db, chat-history.db, schedule.db, feedback.db, projects.db, goals.db,
    and (2026-09-30) study.db, the review decks; and (2026-10-07) arbiter.db,
    jobs.db, ledger.db and watch.db, the files of the arbiter, jobs, ledger and
    watch modules; and (2026-10-08) tasks.db, the job list; and (2026-10-14)
    receipts.db, the action receipts and their Undo snapshots
    (jarvis_receipts.py). A receipt holds the owner's own words - what changed,
    and what the thing looked like before - and a restore that put goals.db or
    projects.db back while dropping the receipts for those rows would leave
    Undo pointing at changes the archive had already replaced. The whole
    archive is encrypted, so the words are never in the clear.
  * Every `*.json` file directly in the Jarvis settings folder (folders.
    json, asks_first.json, manner.json, and so on) - never a subfolder, so
    this glob can never reach into "voice" or "notes" by accident.
  * TWO named settings files the `*.json` glob above cannot match, because
    their extensions are not `.json` (`SETTINGS_NAMES`, 2026-10-13):
      - `config.toml` - the HUD's OWN settings, 10.9 KB, and until this
        change it was in NO backup of any kind: this module's only `.toml`
        was jarvis-framework.toml, which lives in the program folder, so
        every setting the owner changes in Jarvis's own window lived in
        exactly one place on Earth. Its real contents were read and checked
        on 2026-10-13 before it was added: **it holds no secret of any
        kind** - see "WHAT `config.toml` ACTUALLY HOLDS" below, and
        `t_config_toml_holds_no_secret` in test_backup.py, which fails if
        that ever stops being true.
      - `speed.jsonl` - one JSON object per line, the response-speed
        measurements the desktop HUD draws its own graph from. 24 KB. A
        `.jsonl` is not a `.json`, so the glob above never matched it; the
        format is deliberately one line per sample, so it cannot be renamed
        into the glob's reach either.
    Both are written under the same `settings/` prefix as the JSON files, so
    a restore puts them back the same way; `_apply_restore` routes that whole
    prefix to the settings folder already.
  * jarvis-framework.toml, wherever `jarvis_framework.config_path()` finds
    the owner's real copy.
  * The notes folder (`notes/`) and the voice enrolment folder (`voice/` -
    the owner's own voice-print, NOT `voice-models/`, which holds
    downloaded engine files, or `voices/`, the custom-voice bank), both
    copied whole, recursively.
  * The chat-history encryption key, read from Windows Credential Manager
    (jarvis_chat_log.CredentialKey, KEY_TARGET) and kept, base64, as ONE
    small file INSIDE the archive - which is encrypted before it ever
    touches a disk, so the key is never written out in the clear.
  * The review decks' own key (jarvis_decks.KEY_TARGET, "Jarvis Backend/study
    decks key"), carried the same way as secrets/study-decks-key.b64, and only
    when study.db exists AND the key can be read: the deck words are sealed
    under it, so a study.db without it is left out rather than carried
    unopenable. A restore writes the file and the key back together and makes
    the running store reopen (jarvis_decks.forget_key). Same recovery code, same
    lock; the deck words are never in the archive in the clear.
  * **The backend's own program files** - every `*.py` directly in the folder
    this module is running from (`_source_dir()`), kept as `source/<name>.py`.
    Added 2026-10-05, after an audit found FIVE files that existed in exactly
    one place on Earth - the live backend folder - and were read by no backup
    of any kind: not this module (nothing in it read a `.py` file), not
    apply-patches.ps1, not git (`backend/.gitignore` keeps the live sources
    out on purpose, with a written exception only for the ten under
    `backend/rebuilt/`). The five were `jarvis_hud.py` (the whole control
    plane), `jarvis_gate.py` (the approval gate), `jarvis_extract.py`,
    `jarvis_models.py` and `jarvis_skills.py`; a bad patch or a deleted folder
    would have taken them with it. TOP LEVEL ONLY, never the tree: the folder
    also holds `__pycache__/` (9.6 MB of bytecode that is rebuilt from the
    sources anyway) and the patcher's own `_jarvis-backup-*` folders, which
    already hold older copies of the same sources - archiving those would nest
    a copy of the whole source inside every new backup and grow each
    generation. Top level is 188 files, 10.1 MB, about 3.6 MB once deflated: a
    bounded, one-off cost beside data that grows on its own. The source rides
    inside the same encrypted archive, so the code is never in the clear
    either. A restore writes these back into the folder this module runs from,
    so the CODE comes back with the data - and therefore a restore also
    replaces the current program files with that day's, which the restore card
    now says in plain words.

EXPLICITLY NOT BACKED UP (CLAUDE.md rule 3; the owner's own words)
  * The pairing token and every API key (Exa, Tavily, Brave, GitHub, ...):
    all of them live in Windows Credential Manager under their OWN target
    names (jarvis_token_store.py, jarvis_search.py) - never in a `*.json`
    settings file - and this module reads exactly one Credential Manager
    entry, the chat-history key, and the review decks' key, and no other. A key that is re-entered
    once, on the PC that needs it, is safer than one that can be dug out of
    a backup file years later.
  * Model files (large, and Ollama already keeps its own copy) and logs
    (`*.log` in the settings folder - the `*.json` glob above never matches
    them).
  * Any backend file that is NOT a top-level `*.py`: the subfolders
    (`__pycache__/`, `_jarvis-logs/`, the patcher's `_jarvis-backup-*`
    folders - see the source bullet above), other file types beside the
    sources, and `*.py` nested deeper than one level.
  * approvals.db and holds.db (pending-approval state, not memory - restoring
    a stale "waiting" row would be misleading, never a security hole: the
    in-memory approval stamp, jarvis_owner_check.stamp, is gone the moment
    the backend restarts, so nothing written into approvals.db by a restore
    can forge an approval).
  * FIVE more databases that were measured on 2026-10-13 and left out on
    purpose - agents.db, audit.db, digest.db, sync_state.db and telemetry.db,
    the five of the nineteen in the settings folder that are neither in
    SOURCE_DBS nor approvals.db. Each one's reason is written beside it in
    `NOT_BACKED_UP` above, so the decision is recorded rather than inferred
    from its absence. In one line each: agents.db and digest.db are empty
    template tables the modules recreate, audit.db is a security trail rather
    than memory, sync_state.db holds sync cursors whose staleness loses data,
    and telemetry.db is measurements of the machine with its writer switched
    off by design.
  * The `-wal`, `-shm` and `-journal` files beside a database: never copied,
    and never needed. The online backup API above reads one consistent view
    and folds the log into the snapshot, so the rows that live only in the log
    arrive inside the snapshot and a second file is not merely redundant but
    dangerous - a stale log landing beside a fresh database is a way to corrupt
    a restore, not to complete one. `t_a_database_whose_rows_live_in_the_wal_
    is_captured_whole` in test_backup.py proves the rows arrive, and
    `_apply_restore` moves any leftover `-wal`/`-shm` aside for the same
    reason.
  * The settings folder's own `.md` files (USER.md, SOUL.md, MEMORY.md) and
    the file with no extension that marks a first chat (first_chat_sent):
    measured 2026-10-13 at 18, 69, 18 and 0 bytes, unedited template stubs.
    Nothing is lost with them, and the `*.json` glob plus SETTINGS_NAMES is
    the whole of what this module claims to carry.
  * The `devices/` folder, which holds the list of devices allowed to talk to
    Jarvis and a SHA-256 of each one's pairing token. It is NOT backed up, and
    this is the one exclusion here that is a privacy decision as much as a
    correctness one: that list is authorization state, so a restore of an old
    copy would re-authorize a phone the owner had since removed - and the
    tokens' hashes have no business being copied off the machine that checks
    them. (Rule 3: a key re-entered once on the PC that needs it is safer than
    one that can be dug out of a backup years later.) The `*.json` glob cannot
    reach a subfolder, so this was already true; it is written down because it
    was checked rather than assumed. `chatbot/api-money.json` - the spending
    limits the owner set - is in that same subfolder and is therefore also not
    carried, which is a genuine, stated gap rather than a decision: it is
    three numbers, and adding subfolder support is a change to what the archive
    layout may hold, not a name added to a list.

WHAT `config.toml` ACTUALLY HOLDS (read on 2026-10-13, before it was added)

The setting that carries a secret in this project is the pairing token, and
rule 3 says it is never written to disk in plain text. `config.toml` was
checked line by line rather than taken on faith, because it is the HUD's own
settings file and a token in it would have been swept into the archive by this
change:

  * **Every** token, password, app_secret and api_key line in the file is
    COMMENTED OUT and holds the empty string - `# bot_token = ""`, for
    Telegram, Discord, Slack, WhatsApp, Teams, Matrix, Mattermost and Feishu,
    each followed by "Or set <SERVICE>_TOKEN env var". Measured: 14 such lines,
    0 of them live.
  * The one place the file mentions how a real key arrives says it arrives from
    the ENVIRONMENT, not from the file: the vLLM slot's comment reads "Auth
    comes from the VLLM_API_KEY environment variable, which must hold the
    proxy's LITELLM_MASTER_KEY".
  * The weather credentials are not here either, in the file's own words:
    "Weather API credentials belong in credentials.toml or the environment, not
    here." There is no `credentials.toml`, and no `*.env` file, anywhere in the
    settings folder (checked).
  * `[server]` is `host = "127.0.0.1"` with the file's own comment "Loopback is
    safe for local use and works without API authentication", and the
    `host = "0.0.0.0"` line below it is commented out.
  * The only matches that are NOT comments are ordinary settings whose names
    merely contain the words: `max_tokens = 1024` and `secret_scanner = true`.

So adding it puts no secret into the archive, and the archive is AES-256-GCM
under a recovery code only the owner holds in any case. What the owner should
still know is the other half: if a token is ever pasted into this file instead
of into Windows Credential Manager or the environment, then that token starts
travelling in every backup from then on. The test suite pins the state that was
measured - `t_config_toml_holds_no_secret` reads the real file and fails on a
live token-shaped line - so the day that changes, a test goes red rather than
the change going unnoticed.

THE LOCK - AES-256-GCM with a key stretched from the recovery code by
Argon2id (`cryptography`, already a dependency here for chat history and
already pinned in requirements.lock at 50.0.1, which has had Argon2id since
44.0.0). NOT the `pyrage`/age route the design doc offered as its other
option: this repository pins every dependency with hashes
(requirements.lock, tools/check_python_advisories.py) and a brand-new
package needs that lock remade and re-checked before it can ship. (Said
plainly, security/privacy audit 2026-09-27: apply-patches.ps1 still
installs from requirements.txt, not the lock, and leaves an installed
package alone - so the PC's `cryptography` is whatever was there first. One
older than 44.0.0 has no Argon2id; the import below then fails and backing
up refuses in words, never writing anything unencrypted.) A package
already here, already reviewed and already the exact tool this job needs,
is the lower-friction and no less honest choice. The cost, said plainly:
`age -d` cannot open this file - only Jarvis, or someone who reads this
docstring and reimplements the format below, can.

    b"JBAK1" | argon2 lanes (1 byte) | argon2 memory KiB (4 bytes) |
    argon2 iterations (4 bytes) | salt (16 bytes) | nonce (12 bytes) |
    AES-256-GCM(zip bytes), AAD = every byte before the ciphertext

The recovery code (`generate_code`) is 20 characters from a 32-symbol
alphabet with no 0/O/1/I/L (about 100 bits) - typed once, shown once, in
four groups of five. It is NEVER written to a file, a log, or the audit
trail, and this module has no code path that could recover it: the only
way to open a backup is to have kept the code that made it. Said plainly,
in every place the code is shown and on the restore card: A LOST CODE MEANS
A USELESS BACKUP - there is no way in without it. And: "Erase the words"
cannot reach into an OLDER backup that still holds an erased fact's
original text; it only stops mattering once every backup kept from before
the erase has aged out (KEEP, below).

RETENTION - the newest KEEP (5) backup files in the folder are kept; making
a new one deletes the rest. Five, not three, because a card is shown for
each restore anyway (so keeping more costs disk, not safety), and not more
than five because a folder that is also synced to the cloud should not grow
without bound. Named `jarvis-backup-<UTC time>.jbak`, sorted by that name.

RESTORE - pick a file, type its code, see COUNTS and a DATE only (read from
the archive's own manifest.json, never any content) as a preview
(`preview_restore`); then ONE approval card that ALWAYS needs Windows Hello
and ALWAYS comes from this PC (action `restore_backup`, in
jarvis_owner_check.PC_ONLY_ACTIONS - the same mechanism
`loosen_what_asks_first` and `enable_reading_tool` already use), whatever
the gate's own risk table would say on its own: replacing everything Jarvis
knows is exactly the kind of action that must never go through on a stolen
token from another device. Before the restore itself, Jarvis backs up the
CURRENT state first, automatically, with a FRESH recovery code shown once
in the same response - so the restore itself can be undone, and the owner
is told the one code they need to undo it.

Restore only ADDS AND OVERWRITES; it never deletes a file that is not in
the backup. Said plainly on the restore card: this can bring back an erased
fact's original words, if an older backup still has them - the same limit
CLAUDE.md itself states.

TWO THINGS THE ROUTE MUST NOT DO (both fixed 2026-10-10, after a restore
that could never be approved). It must not promise a card to a caller that
can never approve one: a restore request from anything but this PC is
refused up front, in RESTORE_PC_ONLY's words, before the body is read. And
the card it raises must not NAME a file jarvis_gate.py protects
(jarvis_hud.py among them): the gate reads the card's own text for those
names and refuses at tier "never" if it finds one, so a card that names
them is never shown to anybody - and no Windows Hello prompt ever comes.
The refusal the owner reads is plain words with the next step in them
(RESTORE_LAST_WORDS); the technical reason is kept in the record's `why`,
for a bug report.

Standard library plus `cryptography` (already required by chat history;
without it, backing up and restoring both refuse, in words, rather than
ever writing anything unencrypted).
"""
from __future__ import annotations

import base64
import calendar
import shutil
import io
import json
import os
import secrets
import sqlite3
import struct
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
except Exception:  # pragma: no cover - cryptography not installed
    AESGCM = None  # type: ignore
    Argon2id = None  # type: ignore
    InvalidTag = Exception  # type: ignore

PATH = "/api/backup"
FOLDER_ROUTE = "/api/backup/folder"
NOW_ROUTE = "/api/backup/now"
LIST_ROUTE = "/api/backup/list"
PREVIEW_ROUTE = "/api/backup/restore/preview"
RESTORE_ROUTE = "/api/backup/restore"

#: The PHONE's half of Backups (2026-10-13, the owner's question of 2026-10-10
#: answered for real). Two routes, both about ONE thing: the phone may ask for
#: a backup and may see what the folder holds - and the PC does the writing.
#:
#:   * `STATUS_ROUTE` (GET, any paired device): what the FOLDER holds - when
#:     the last backup was made, which folder it went to (its last path
#:     segment), how many are kept and how many are there, and whether the
#:     newest file is complete and well formed. It NEVER carries a recovery
#:     code and never can: `status_view` reads the settings file and the
#:     folder, and neither has a code in it (`_load_settings` keeps "folder"
#:     and nothing else; `_audit` refuses to record one).
#:
#:   * `PREPARE_ROUTE` (POST, any paired device) and `COMMIT_ROUTE` (POST,
#:     THIS PC ONLY): the phone asks, the PC writes. This pair replaces the
#:     old plain "no, a phone may never ask" with a rule that cannot lose a
#:     backup - see "WHY THE PHONE'S RUN IS TWO CALLS" below.
#:
#: WHY THE PHONE'S RUN IS TWO CALLS, AND WHY THAT IS THE WHOLE SAFETY OF IT.
#: Each backup file is locked with its OWN one-time recovery code and the code
#: is never stored anywhere (`generate_code`; the module docstring). A backup
#: whose code was never written down is a file nobody can ever open - and
#: because making a new one deletes the oldest of the KEEP (5), a run whose
#: code never reached the owner does not just add a dud: it PUSHES OUT an
#: older backup that its own code could still open. That is the one outcome
#: this feature may never produce.
#:
#: So the phone's run does not write a file when it is asked. `prepare` mints
#: the code and holds it - in memory, for PENDING_TTL_S, never on disk - and
#: hands it back to the phone. The phone shows it, in the owner's face, and
#: asks him to keep it. Only his "I have saved it", carrying that same code
#: back (`commit`), writes anything. A phone that is put down, a link that
#: drops, a run nobody finishes: each of those writes NO FILE AT ALL, so the
#: five backups already in the folder are untouched. The old file is never
#: replaced by one nobody can open.
#:
#: The code does therefore travel to the phone, once, in the reply to
#: `prepare`, and lives on the phone's screen until the run is finished - the
#: change `docs/ARCHITECTURE.md` section 8 records for this one screen. Its
#: cost is the same as the code's cost on the PC, and it is said on the screen
#: in so many words: a code that is not kept is a backup that can never be
#: opened, and Jarvis cannot recover it.
#:
#: `commit` is THIS PC ONLY (`_from_this_pc`): the phone asks, and the PC -
#: the machine that holds the folder - is what writes into it. That keeps the
#: standing rule that a phone never writes to the PC's disk by itself, and it
#: is what makes a stolen token useless here: a thief can ask all day and
#: nothing is ever written, because the write is refused from anywhere but the
#: PC. The PC's own "Back up now" (`NOW_ROUTE`) is untouched: still one call,
#: still no card, still this PC only.
STATUS_ROUTE = "/api/backup/status"
PREPARE_ROUTE = "/api/backup/prepare"
COMMIT_ROUTE = "/api/backup/commit"

#: How long a prepared run stays open. Long enough to read a code out and put
#: it in a password manager or a notes app, short enough that a forgotten run
#: cannot be committed hours later out of a stale screen. The same 15 minutes
#: approval cards wait (the owner's decision of 2026-10-13, #378).
PENDING_TTL_S = 15 * 60

#: Setting the folder - jarvis_documents.py's own action for "let Jarvis see
#: (or write into) one more place".
CARD_ACTION = "change_own_config"

#: Restoring from a backup. jarvis_owner_check.PC_ONLY_ACTIONS holds the
#: same name.
RESTORE_ACTION = "restore_backup"

#: How many backup files are kept in the folder. Chosen, not measured: a
#: card is shown per restore either way, so more costs disk, not safety; a
#: synced folder should not grow without bound. See the module docstring.
KEEP = 5
#: A file name dated more than this far ahead of the PC's clock cannot be
#: trusted (the clock was wrong when it was made, or the name was edited): it is
#: ranked by the file's own modified time instead (see `list_backups`).
FUTURE_SLACK_S = 300

FILE_SUFFIX = ".jbak"
MAGIC = b"JBAK1"

#: Argon2id, OWASP's 2026 minimum for a low-value key doubled: about
#: 0.5-1.5s on an ordinary PC, cheap once, expensive at scale for an
#: attacker who has already stolen the file.
ARGON_LANES = 4
ARGON_MEMORY_KIB = 64 * 1024      # 64 MiB
ARGON_ITERATIONS = 3
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16                       # AES-GCM's check bytes at the end
_HEADER_STRUCT = struct.Struct(">B I I")   # lanes, memory_kib, iterations

#: No 0/O, 1/I/L: nothing that can be misread out loud or by eye.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_GROUPS, CODE_GROUP_LEN = 4, 5

#: The real databases this backend has today (verified against the modules
#: that make them, 2026-09-27 - see the module docstring). projects.db
#: (jarvis_projects.py: projects, their benchmarks and every number the
#: owner logged) joined on 2026-09-28, found by the Projects feature audit.
#: goals.db (jarvis_goals.py) joined on 2026-09-29, found by the cohesiveness
#: audit: schedule.db WAS backed up, and it holds each goal's weekly check-in
#: job, so a restore brought back check-ins whose goals were gone - and Stop
#: tracking (the only way to remove one) needs the goal.
#: study.db (jarvis_decks.py, review decks) joined on 2026-09-30, the owner's
#: decision after the decks audit: same recovery code, same lock. Its words are
#: sealed under a Credential Manager key of their own, so that key travels the
#: way the chat-history key does (secrets/study-decks-key.b64) - and a study.db
#: is only written into an archive together with its key, never without.
#: arbiter.db (jarvis_arbiter.py), jobs.db (jarvis_jobs.py), ledger.db
#: (jarvis_ledger.py) and watch.db (jarvis_watch.py) joined on 2026-10-07: those
#: four modules began being shipped that day, each keeps its own SQLite file in
#: the settings folder, and test_backup.py refuses to let a database a module
#: names go unbacked. A name whose file is not there is skipped, as for the rest.
#: tasks.db (jarvis_tasks.py, the job list) joined on 2026-10-08: it is where a
#: job remembers which step it got to, so a restore without it would leave the
#: owner's unfinished work as a row nothing can pick up again. It holds ids,
#: states, tool names, step counts and the same words a step was approved with -
#: no more than the other working databases here - and it travels only inside
#: this one locked file, like every name below.
#: knowledge.db (6 tables) and traces.db (7 tables) joined on 2026-10-13, after
#: the coverage gap was measured against the owner's own install: 19 databases
#: live in ~/.openjarvis and this list named 12 of them. These two are the ones
#: of the remaining seven that hold the OWNER'S OWN CONTENT - things he pastes
#: and imports into the knowledge store, and the words he typed and the answer
#: he was given. The other five are written down as deliberate exclusions, with
#: their reasons, in `NOT_BACKED_UP` below; test_backup.py fails if a database
#: stops being in one list or the other.
#:
#:
#: voiceprint.db (2026-10-14) is the "Write Like Me" exemplars: what the owner
#: wrote, kept so Jarvis can draft in his own voice. It is the owner's own words
#: about his own life, so it belongs in the locked backup for the same reason
#: memory.db does - and test_backup.py's own rule catches a module that names a
#: database and does not get it in here, which is how this was found.
SOURCE_DBS = ("memory.db", "chat-history.db", "schedule.db", "feedback.db", "projects.db",
              "goals.db", "study.db", "arbiter.db", "jobs.db", "ledger.db", "watch.db",
              "tasks.db", "knowledge.db", "traces.db",
              "receipts.db", "voiceprint.db")

#: Databases in the settings folder this module leaves out ON PURPOSE
#: (2026-10-13). Named here, with the reason, so an exclusion is a decision
#: written down rather than a name somebody forgot - the same rule
#: `SETTINGS_NAMES` keeps for the files that ARE added. `approvals.db` and
#: `holds.db` are not in this mapping because the module docstring's longer
#: explanation owns them already ("pending-approval state, not memory"), and
#: test_backup.py's own NOT_BACKED_UP set covers all of them.
#:
#: agents.db   6 empty template tables (managed_agents, agent_tasks, ...). The
#:             whole schema lives in the 115,392-byte `-wal` file beside a
#:             4,096-byte main file, so a plain copy takes an empty shell -
#:             which is exactly what SQLite's online backup API fixes, and why
#:             the WAL regression test uses this shape. But there is nothing in
#:             it to restore: measured 2026-10-13, 6 tables and 0 rows, and the
#:             modules recreate it if the feature is ever switched on.
#: audit.db    an empty hash-chained security-event trail (1 table, 0 rows).
#:             Left out for the reason approvals.db is: it is a trail, not
#:             memory. A stale trail restored beside a current hash chain would
#:             mislead, and showing what really happened is its whole purpose.
#: digest.db   an empty generated-digest store (1 table, 0 rows). Digests are
#:             re-generated from data that IS backed up, so nothing is lost
#:             that cannot be made again.
#: sync_state.db  sync cursors (1 table, 0 rows). An old cursor tells a
#:             connector it has already fetched items it has not, which loses
#:             data rather than saving it - the same "stale state is worse than
#:             absent state" call as approvals.db.
#: telemetry.db   GPU and power measurements (2 tables, 1 row): operability data
#:             about the machine, not the owner's data, and the code that would
#:             write it is switched off on purpose (jarvis_child_env.py,
#:             test_telemetry_off.py; docs/FEATURE-REVIEW-2026-10-04.md calls it
#:             a "Template telemetry store ... no writer found").
NOT_BACKED_UP = {
    "agents.db": "template tables the modules recreate; empty today (0 rows)",
    "audit.db": "a security trail, not memory; restoring a stale one misleads",
    "digest.db": "generated digests, re-made from data that is backed up",
    "sync_state.db": "sync cursors; a restored old cursor loses un-fetched items",
    "telemetry.db": "machine measurements, not the owner's data; writer off",
}

#: The settings files the `*.json` glob cannot reach, because their extension is
#: not `.json`, added 2026-10-13 (see the module docstring's "WHAT IS BACKED
#: UP"). Written under the `settings/` prefix exactly like the JSON files, and
#: restored BY that prefix, so a restore needs no rule of its own for them.
#:
#: config.toml  the HUD's own settings. Checked for secrets before it was
#:              added: it holds none (see the module docstring).
#: speed.jsonl  one JSON object per line - the response-speed samples the
#:              desktop graph is drawn from. Never renamed into the glob's
#:              reach: the format is one line per sample by design.
SETTINGS_NAMES = ("config.toml", "speed.jsonl")

STUDY_DB = "study.db"

#: The backend's own program files, inside the archive (2026-10-05). Added
#: after an audit found five sources - jarvis_hud.py, jarvis_gate.py,
#: jarvis_extract.py, jarvis_models.py, jarvis_skills.py - that existed in
#: exactly one place on Earth (the live backend folder) and that no backup of
#: any kind read. See the module docstring's "WHAT IS BACKED UP".
#: TOP LEVEL ONLY: `*.py` directly in the folder this module runs from, never
#: a subfolder - `__pycache__/` is bytecode that rebuilds itself, and the
#: patcher's `_jarvis-backup-*` folders already hold older copies of these same
#: sources, so recursing would nest the whole source inside every new backup.
SOURCE_PREFIX = "source/"
SOURCE_GLOB = "*.py"

MISSING = "backup.py could not be reached - run apply-patches.ps1 on this PC"
NO_CRYPTO = ("Backing up needs the `cryptography` package, which is not installed on this "
             "PC - without it nothing is ever written unencrypted, so backups are off "
             "until it is installed")
NO_FOLDER = "Choose a folder for backups first (Settings, Backups)."
PC_ONLY = "Backups are set up on the PC only (Settings, Backups)."
#: The two RESTORE routes' own refusal, said before anything is read
#: (2026-10-10). `PC_ONLY` above is the backups-PANEL line: it tells a caller
#: where the setting lives, which for a restore reads as advice to go and set
#: backups up. What a caller trying to RESTORE needs to hear is that
#: restoring happens at the PC, and that this attempt changed nothing.
#: Measured that night: an API caller was answered 202 "Waiting for your
#: approval, with Windows Hello" and the restore was refused a millisecond
#: later, with no card and no prompt - the route had promised a card that
#: could never appear. A caller that is not this PC is now refused BEFORE the
#: body is looked at, in these words, and is never told to wait: the action is
#: in jarvis_owner_check.PC_ONLY_ACTIONS, so such a caller can never approve
#: it, and the route already knows that (the same `_from_this_pc` the folder
#: route uses). No address and no port is named here.
RESTORE_PC_ONLY = ("Restoring has to be done in Jarvis on your PC, so nothing was restored. "
                   "Open Jarvis there, then Settings, Backups.")
LOST_CODE = ("Write this down or save it somewhere safe now - Jarvis will not show it "
             "again, and cannot recover it. If it is lost, this backup can never be "
             "opened again; there is no other way in.")
ERASE_LIMIT = ("\"Erase the words\" cannot reach into an older backup: an erased fact's "
               "original words may still be readable in a backup kept from before it was "
               "erased, until that backup ages out of the last {keep} kept. A chat you "
               "delete is the same, and so is a review deck or card: it can still be in an "
               "older backup until that backup ages out.").format(keep=KEEP)

#: The phone's run, said before it starts (2026-10-13). What a caller about to
#: ask for a backup has to know first: where the file goes, that the code is
#: the only way in, and that nothing is written until the code is kept.
PREPARE_LEAD = ("Your PC will make one locked backup into the folder you chose there, and show "
                "you a recovery code for it. Nothing is written until you say you have saved "
                "that code - so a run you do not finish leaves your PC exactly as it was.")
#: Said when the prepared run exists but the folder does not. `NO_FOLDER` is the
#: PC's own sentence and is reused, never a second wording of the same thing.
COMMIT_NO_RUN = ("That backup run has expired or was never started, so nothing was written. "
                 "Ask for a backup again from your phone.")
COMMIT_WRONG_CODE = ("That is not the code for the backup waiting to be written, so nothing "
                     "was written and your folder is unchanged. Ask for a backup again.")
#: A caller that is not this PC asking to COMMIT. `PC_ONLY` (the backups panel)
#: is not this: it reads as advice to go and set backups up. This says what
#: actually happened to the ask.
COMMIT_PC_ONLY = ("The backup is written on your PC, so nothing was written from here. Ask "
                  "for a backup in Jarvis on your phone, then keep the code it shows: your "
                  "PC writes the file when you tap that you have saved it. If you cannot "
                  "reach your phone, make one at the PC - Settings, Backups, \"Back up "
                  "now\".")
#: `verify.why` values, in the phone's own words. Each says what was ACTUALLY
#: checked: the file's own bytes, never that it can be opened.
CHECK_WORDS = {
    "complete": "Jarvis checked this file just now: it is a complete, well-formed backup, "
                "and nothing about it has changed since it was written.",
    "missing": "Jarvis cannot find that backup file in the folder any more. Look in the "
               "folder on your PC.",
    "too_small": "That backup file is smaller than a real backup can be, so it is not "
                 "usable. Something may have cut the copy short - make a new backup on "
                 "your PC.",
    "not_a_backup": "That file is not one of Jarvis's own backup files. Something else has "
                    "taken its name in the folder - look at the folder on your PC.",
    "unreadable": "Jarvis could not read that backup file just now. It may be locked by "
                  "another program (a sync program, or an antivirus scan). More backups are "
                  "still kept; look at the folder on your PC.",
    "no_folder": "No folder has been chosen on your PC yet, so there is nothing to check.",
    "empty": "There is no backup in the folder on your PC yet.",
}
#: Always drawn beside the check line. The one thing a check CANNOT prove, said
#: rather than left to be inferred: only the code opens a backup, and only the
#: PC can try a code.
CHECK_LIMIT = ("Jarvis cannot prove from your phone that a backup OPENS - that needs the "
               "recovery code, and codes are only ever typed on your PC. To prove one "
               "opens, open Jarvis there, Settings, Backups, and check it with its code.")


class WrongCode(Exception):
    """The recovery code does not open this file (or it is not one of ours)."""


class BackupUnavailable(Exception):
    """Backing up or restoring cannot go ahead; the message is plain words."""


# ---------------------------------------------------------------------------
#   Settings, the gate, the clock - replaceable, so the tests open nothing
# ---------------------------------------------------------------------------


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


def _source_dir() -> Path:
    """The folder this module is RUNNING FROM - the live backend folder, the
    one holding jarvis_hud.py, jarvis_gate.py and the rest. There is exactly
    one honest answer and this is it: the copy of this module that is executing
    is in that folder by definition, so `__file__` always names it, with no
    setting to keep in step and nothing to get wrong on the owner's PC (the
    path is different on every machine, and a setting would only be a second
    thing to fix).

    Replaceable in tests, exactly like `_config_dir()`, so a test never writes
    into the folder the test itself is running from."""
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


def settings_path() -> Path:
    """backup.json in the Jarvis settings folder: {"folder": str|None}. The
    LAST backup's own outcome is kept in memory only (_B_STATE), never here -
    it can carry a one-time recovery code, which must never touch disk."""
    return _config_dir() / "backup.json"


def _load_settings() -> dict:
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"folder": None}
    except (OSError, ValueError):
        return {"folder": None}
    if not isinstance(raw, dict):
        return {"folder": None}
    folder = raw.get("folder")
    return {"folder": folder if isinstance(folder, str) and folder else None}


def _save_settings(data: dict) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-backup-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only. Never a folder's path, a file name that
    # could hint at its date, or (obviously) a recovery code.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False  # cannot tell: fail closed, nothing runs


def _owner_check_armed() -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.armed())
    except Exception:
        return False


def check_folder(path) -> str:
    """The folder, as it would be kept, or ValueError with a sentence.

    Reused from jarvis_documents.py - not copied - so backups are refused
    the same places "Folders Jarvis may look in" is (a drive's top, the
    whole user folder, Windows' own folders, anywhere file_read refuses):
    one list of unsafe places, never two that can drift apart.
    """
    import jarvis_documents
    return jarvis_documents.check_folder(path)


# ---------------------------------------------------------------------------
#   The lock: AES-256-GCM, a key stretched from the code by Argon2id
# ---------------------------------------------------------------------------


def generate_code() -> str:
    """A fresh recovery code: 20 characters, 4 groups of 5, from an
    alphabet with no 0/O/1/I/L. Never logged, never written to a file,
    never kept by this module past the response that shows it once."""
    chars = [secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUPS * CODE_GROUP_LEN)]
    groups = ["".join(chars[i:i + CODE_GROUP_LEN])
              for i in range(0, len(chars), CODE_GROUP_LEN)]
    return "-".join(groups)


def _clean_code(code) -> str:
    """As the owner would type it back: upper-cased, hyphens and spaces
    dropped, so "abcd-efghj" and "ABCDEFGHJ" and "abcd efgh j" all match."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def _require_crypto() -> None:
    if AESGCM is None or Argon2id is None:
        raise BackupUnavailable(NO_CRYPTO)


def _derive_key(salt: bytes, code: str) -> bytes:
    kdf = Argon2id(salt=salt, length=KEY_LEN, iterations=ARGON_ITERATIONS,
                   lanes=ARGON_LANES, memory_cost=ARGON_MEMORY_KIB)
    return kdf.derive(_clean_code(code).encode("utf-8"))


def encrypt_blob(data: bytes, code: str) -> bytes:
    """The on-disk format - see the module docstring's diagram. `data` is
    the whole zip archive's bytes, held in memory only until this returns."""
    _require_crypto()
    salt = secrets.token_bytes(SALT_LEN)
    nonce = secrets.token_bytes(NONCE_LEN)
    header = MAGIC + _HEADER_STRUCT.pack(ARGON_LANES, ARGON_MEMORY_KIB, ARGON_ITERATIONS)
    header += salt + nonce
    key = _derive_key(salt, code)
    aes = AESGCM(key)
    return header + aes.encrypt(nonce, data, header)


def decrypt_blob(blob: bytes, code: str) -> bytes:
    """The zip bytes back, or WrongCode - never AESGCM's own exception, so a
    caller never has to know cryptography's exception types to handle it."""
    _require_crypto()
    head_len = len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN + NONCE_LEN
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < head_len or \
            bytes(blob[:len(MAGIC)]) != MAGIC:
        raise WrongCode("that is not a Jarvis backup file")
    header = bytes(blob[:head_len])
    lanes, memory_kib, iterations = _HEADER_STRUCT.unpack(
        header[len(MAGIC):len(MAGIC) + _HEADER_STRUCT.size])
    salt = header[len(MAGIC) + _HEADER_STRUCT.size: len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN]
    nonce = header[len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN:head_len]
    ciphertext = bytes(blob[head_len:])
    if len(ciphertext) < TAG_LEN:
        raise WrongCode("that backup file is damaged - it is cut short (a copy or a sync "
                        "that did not finish?)")
    try:
        kdf = Argon2id(salt=salt, length=KEY_LEN, iterations=iterations,
                       lanes=lanes, memory_cost=memory_kib)
        key = kdf.derive(_clean_code(code).encode("utf-8"))
        aes = AESGCM(key)
        return aes.decrypt(nonce, ciphertext, header)
    except InvalidTag:
        raise WrongCode("that recovery code does not open this backup (or the file is "
                        "damaged, for instance a copy that did not finish)") from None
    except (ValueError, TypeError) as exc:
        raise WrongCode(f"that backup file is damaged ({type(exc).__name__})") from None


# ---------------------------------------------------------------------------
#   Gathering what gets backed up
# ---------------------------------------------------------------------------


def _table_counts(db_path: Path) -> dict:
    """{table: row count} for every real table in `db_path` - a manifest
    number, never a row's content. {} for a missing or unreadable file."""
    if not db_path.is_file():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return {}
    try:
        conn.execute("PRAGMA query_only = 1")
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = {}
        for name in names:
            try:
                out[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.DatabaseError:
                continue
        return out
    except sqlite3.DatabaseError:
        return {}
    finally:
        conn.close()


def _snapshot_db(src: Path, dest: Path) -> bool:
    """A safe-while-running copy of `src` at `dest`, via SQLite's own online
    backup API. False (never raises) when `src` does not exist or cannot be
    read - that database is simply left out of the archive."""
    if not src.is_file():
        return False
    try:
        source = sqlite3.connect(str(src))
    except sqlite3.DatabaseError:
        return False
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    except sqlite3.DatabaseError:
        return False
    finally:
        source.close()
    return dest.is_file()


def _chat_history_key_b64() -> Optional[str]:
    """The chat-history encryption key, base64, or None if it is not there
    or Credential Manager cannot be reached. Read the SAME way
    jarvis_chat_log.py reads it - not copied."""
    try:
        import jarvis_chat_log
        key = jarvis_chat_log.CredentialKey()()
        return base64.b64encode(key).decode("ascii")
    except Exception:
        return None


def _study_decks_key_b64() -> Optional[str]:
    """The review decks' own encryption key, base64, or None when it cannot
    be read. Read the SAME way jarvis_decks.py reads it (its own Credential
    Manager entry, "Jarvis Backend/study decks key"), and only called when
    study.db exists, so a backup never makes a key for decks nobody has."""
    try:
        import jarvis_chat_log
        import jarvis_decks
        key = jarvis_chat_log.CredentialKey(jarvis_decks.KEY_TARGET)()
        return base64.b64encode(key).decode("ascii")
    except Exception:
        return None


def _toml_source() -> Optional[Path]:
    try:
        if fw is not None:
            p = fw.config_path()
            return Path(p) if p else None
    except Exception:
        pass
    return None


def _walk_files(root: Path):
    if not root.is_dir():
        return
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p


def _archive_settings_names(zf: zipfile.ZipFile, conf: Path, manifest: dict) -> None:
    """The settings files the `*.json` glob cannot match, because their
    extension is not `.json`: `SETTINGS_NAMES` (2026-10-13 - config.toml, the
    HUD's own settings, was in no backup of any kind until this). Written
    under the same `settings/` prefix as the JSON files, so a restore routes
    them home through the rule that already exists. A name whose file is not
    there is skipped, exactly as for a database; one that cannot be read is
    skipped too and the count says how many really went in, because a file
    that will not open is never a reason to fail the whole backup.
    """
    for name in SETTINGS_NAMES:
        src = conf / name
        if not src.is_file():
            continue
        try:
            zf.write(src, arcname=f"settings/{name}")
            manifest["settings_files"] += 1
            manifest["named_settings"][name] = True
        except OSError:
            continue


def _named_settings_entries(names) -> list:
    """The archive entries that belong in the settings folder: the JSON files
    (`settings/*.json`, the long-standing rule) and `SETTINGS_NAMES`
    (`settings/config.toml`, `settings/speed.jsonl`). One list, so the rule for
    what may land in the owner's settings folder is stated once and
    `_apply_restore` cannot drift away from `build_archive`.
    """
    out = []
    for name in names:
        if not name.startswith("settings/"):
            continue
        rest = name[len("settings/"):]
        if rest.endswith(".json") or rest in SETTINGS_NAMES:
            out.append(name)
    return out


def build_archive() -> tuple:
    """(zip_bytes, manifest). The manifest is also written INSIDE the zip
    as manifest.json, so a restore preview can read counts and a date
    without touching anything else in the archive."""
    conf = _config_dir()
    manifest = {"created_at": time.time(), "databases": {}, "settings_files": 0,
                "notes_files": 0, "voice_files": 0, "chat_history_key": False,
                "study_decks_key": False, "framework_toml": False,
                "source_files": 0, "named_settings": {}}
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="jarvis-backup-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            study_key_b64 = None
            for name in SOURCE_DBS:
                src = conf / name
                dest = tmp_path / name
                if name == STUDY_DB:
                    # Sealed words are useless (and a restore of them would
                    # replace a working file) without their key: no key, no file.
                    if not src.is_file():
                        continue
                    study_key_b64 = _study_decks_key_b64()
                    if not study_key_b64:
                        continue
                if _snapshot_db(src, dest):
                    manifest["databases"][name] = _table_counts(dest)
                    zf.write(dest, arcname=f"db/{name}")
                    if name == STUDY_DB:
                        zf.writestr("secrets/study-decks-key.b64", study_key_b64)
                        manifest["study_decks_key"] = True
            for jf in sorted(conf.glob("*.json")):
                if jf.name == settings_path().name:
                    continue  # backup.json names only a folder - never useful inside itself
                try:
                    zf.write(jf, arcname=f"settings/{jf.name}")
                    manifest["settings_files"] += 1
                except OSError:
                    continue
            # The settings files whose extension the glob above cannot match
            # (2026-10-13). See SETTINGS_NAMES.
            _archive_settings_names(zf, conf, manifest)
            toml_src = _toml_source()
            if toml_src is not None and toml_src.is_file():
                try:
                    zf.write(toml_src, arcname="jarvis-framework.toml")
                    manifest["framework_toml"] = True
                except OSError:
                    pass
            notes_root = conf / "notes"
            for f in _walk_files(notes_root):
                zf.write(f, arcname=f"notes/{f.relative_to(notes_root)}")
                manifest["notes_files"] += 1
            voice_root = conf / "voice"
            for f in _walk_files(voice_root):
                zf.write(f, arcname=f"voice/{f.relative_to(voice_root)}")
                manifest["voice_files"] += 1
            # The backend's own program files, so a backup brings the CODE back
            # with the data (2026-10-05). Top level only: `glob`, not
            # `_walk_files` - see SOURCE_GLOB above for why recursing here is
            # wrong, not merely expensive. A file that cannot be read is left
            # out and the count says how many really went in; this is never a
            # reason to fail the whole backup.
            source_root = _source_dir()
            for sf in sorted(source_root.glob(SOURCE_GLOB)):
                if not sf.is_file():
                    continue
                try:
                    zf.write(sf, arcname=f"{SOURCE_PREFIX}{sf.name}")
                    manifest["source_files"] += 1
                except OSError:
                    continue
            key_b64 = _chat_history_key_b64()
            if key_b64:
                zf.writestr("secrets/chat-history-key.b64", key_b64)
                manifest["chat_history_key"] = True
            zf.writestr("manifest.json", json.dumps(manifest))
    return buf.getvalue(), manifest


# ---------------------------------------------------------------------------
#   Making one backup file, and keeping only the last few
# ---------------------------------------------------------------------------


def _file_name(at: float) -> str:
    return time.strftime("jarvis-backup-%Y%m%d-%H%M%S", time.gmtime(at)) + FILE_SUFFIX


def _stamp_of(name: str) -> Optional[str]:
    """The "jarvis-backup-YYYYmmdd-HHMMSS" part of a name that may carry a
    "-N" disambiguator before the extension (two backups made in the same
    second), or None if `name` is not shaped like one of ours."""
    if not (name.startswith("jarvis-backup-") and name.endswith(FILE_SUFFIX)):
        return None
    body = name[:-len(FILE_SUFFIX)]
    parts = body.split("-")
    # "jarvis-backup-YYYYmmdd-HHMMSS" is 4 parts; a 5th, all-digit part is
    # the disambiguator added below for two backups made in the same second.
    if len(parts) == 5 and parts[-1].isdigit():
        return "-".join(parts[:-1])
    return body


#: Smallest a real backup can be: the header, then at least the check bytes.
MIN_FILE_BYTES = len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN + NONCE_LEN + TAG_LEN


def _suffix_of(name: str) -> int:
    """The "-N" a same-second backup carries (1 when it has none)."""
    body = name[:-len(FILE_SUFFIX)] if name.endswith(FILE_SUFFIX) else name
    parts = body.split("-")
    if len(parts) == 5 and parts[-1].isdigit():
        return int(parts[-1])
    return 1


def list_backups(folder, *, now: Optional[float] = None) -> list:
    """[{"name", "at", "size", "complete"}], newest first. `at` is read from
    the file's own name (UTC) - a copy or a sync program can change a file's
    modified time, so the name is trusted - EXCEPT a name dated in the future
    (more than FUTURE_SLACK_S ahead of `now`: the PC's clock was wrong, or the
    name was edited): that one is dated by the file's real modified time
    instead, so it can neither sit at the top for ever nor push the newest
    real backup out. Same second: the "-N" number breaks the tie, so a
    same-second backup is newer than the one it did not overwrite.
    `complete` is False for a file too small to be a backup at all (a copy
    that was cut short): it is listed but never counts as one of the kept."""
    p = Path(folder)
    if not p.is_dir():
        return []
    now = time.time() if now is None else now
    out = []
    for f in p.iterdir():
        if not f.is_file():
            continue
        stamp = _stamp_of(f.name)
        if stamp is None:
            continue
        try:
            at = calendar.timegm(time.strptime(stamp, "jarvis-backup-%Y%m%d-%H%M%S"))
        except ValueError:
            continue
        try:
            st = f.stat()
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size, mtime = 0, None
        if at > now + FUTURE_SLACK_S and mtime is not None:
            at = min(at, mtime)
        out.append({"name": f.name, "at": at, "size": size, "complete": size >= MIN_FILE_BYTES})
    out.sort(key=lambda r: (r["at"], _suffix_of(r["name"]), r["name"]), reverse=True)
    return out


def check_file(path) -> dict:
    """{"ok", "why", "size"} for one backup file, read from the file itself.

    What this CAN prove, and it is worth saying exactly: the file starts with
    our own magic bytes, its length is a whole one (a header, a salt, a nonce,
    at least the check bytes, and no trailing rubbish), and the Argon2id
    parameters in that header are the ones `encrypt_blob` writes. That is the
    difference between a backup and a copy that was cut short, and it is the
    check `list_backups` alone cannot make - `complete` there is a length, not
    a shape.

    What it CANNOT prove, and never claims to: that the file OPENS. That needs
    the recovery code, which is not on disk anywhere and by design cannot be
    (`generate_code`; `t_a_lost_code_truly_cannot_be_recovered`). So the words
    the phone draws beside a pass are `CHECK_WORDS["complete"]`, and
    `CHECK_LIMIT` says the rest - never "this backup works"."""
    p = Path(path)
    try:
        st = p.stat()
    except FileNotFoundError:
        return {"ok": False, "why": "missing", "size": 0}
    except OSError:
        return {"ok": False, "why": "unreadable", "size": 0}
    size = st.st_size
    if size < MIN_FILE_BYTES:
        return {"ok": False, "why": "too_small", "size": size}
    try:
        with p.open("rb") as fh:
            head = fh.read(len(MAGIC) + _HEADER_STRUCT.size)
    except OSError:
        return {"ok": False, "why": "unreadable", "size": size}
    if not head.startswith(MAGIC):
        return {"ok": False, "why": "not_a_backup", "size": size}
    try:
        lanes, memory_kib, iterations = _HEADER_STRUCT.unpack_from(head, len(MAGIC))
    except struct.error:                       # pragma: no cover - size checked above
        return {"ok": False, "why": "not_a_backup", "size": size}
    if (lanes, memory_kib, iterations) != (ARGON_LANES, ARGON_MEMORY_KIB, ARGON_ITERATIONS):
        return {"ok": False, "why": "not_a_backup", "size": size}
    # No trailing rubbish: our own file is exactly its header, its salt, its
    # nonce and its ciphertext (which carries the tag). A file LONGER than the
    # minimum by anything is still fine - what would not be is a file whose
    # declared shape cannot fit inside it, and `MIN_FILE_BYTES` is that shape's
    # floor. Everything past the floor is ciphertext, which only the code can
    # read.
    return {"ok": True, "why": "complete", "size": size}


def _folder_name(folder: Optional[str]) -> Optional[str]:
    """The LAST segment of the backup folder, for a phone.

    Deliberately not the whole path: `C:\\Users\\<name>\\Documents\\Jarvis
    Backups` names the owner's Windows account and his folder tree, and
    `docs/ARCHITECTURE.md` section 8 already keeps the memory store's own path
    off the phone for exactly that reason. "Jarvis Backups" answers "where did
    it go?" - which is the question - and the whole path is one tap away on the
    PC that has it."""
    if not folder:
        return None
    try:
        name = Path(folder).name
    except Exception:                          # pragma: no cover - Path is forgiving
        return None
    return name or folder


def status_view() -> dict:
    """GET /api/backup/status - what the FOLDER holds, for the phone.

    Read-only, on any paired device, and it carries no recovery code and no
    full path (see `_folder_name`). Everything in it is read from the folder
    and the settings file at the moment it is asked, so it is TRUE after the
    backend restarts - which the older `last_backup_at` (the PC's memory only,
    cleared on start-up) was not. `net/Backup.kt` draws it; the desktop may
    read the same keys out of `GET /api/backup` and does not need to.

    `verify` is about the NEWEST kept file, read now. `last_attempt` is the
    last run THIS backend made, remembered in memory - it is the only place a
    refusal can be seen, so a failed backup is never reported as a success."""
    with _B_LOCK:
        last_attempt = dict(_B_STATE["last"]) if _B_STATE["last"] else None
    with _P_LOCK:
        prepared = dict(_P_STATE["pending"]) if _P_STATE["pending"] else None
    st = _load_settings()
    folder = st["folder"]
    rows = list_backups(folder) if folder else []
    complete = [r for r in rows if r["complete"]]
    newest = complete[0] if complete else None
    if not folder:
        check = {"ok": False, "why": "no_folder"}
    elif newest is None:
        check = {"ok": False, "why": "empty"}
    else:
        check = check_file(Path(folder) / newest["name"])
        check.pop("size", None)
    # The time the phone shows: the newest kept file's own date, which is true
    # after a restart. Falling back to the last ATTEMPT's time only when the
    # folder holds nothing (a run whose file was deleted since, or one that
    # failed after the folder was set).
    at = newest["at"] if newest else (last_attempt or {}).get("at")
    return {
        "available": True,
        "folder": _folder_name(folder),
        "keep": KEEP,
        "kept": len(complete),
        "last_backup_at": at or None,
        "last_backup_name": newest["name"] if newest else None,
        "verify": {"ok": bool(check["ok"]), "why": check["why"],
                   "words": CHECK_WORDS.get(check["why"], ""), "proves_open": False,
                   "limit": CHECK_LIMIT},
        "last_attempt": ({"ok": bool(last_attempt.get("ok")),
                          "at": last_attempt.get("at"),
                          "error": last_attempt.get("error") or ""} if last_attempt else None),
        "prepared": ({"at": prepared.get("at"), "expires_at": prepared.get("expires_at")}
                     if prepared else None),
    }


def _retain(folder, keep_name: Optional[str] = None) -> None:
    """Keeps the newest KEEP complete backups and deletes the rest. The file
    just written (`keep_name`) is NEVER deleted, whatever its rank, and counts
    as one of the KEEP. A file that is too small to be a backup is not counted
    and not deleted (it may be a sync still in progress)."""
    rows = [r for r in list_backups(folder) if r["complete"]]
    others = [r for r in rows if r["name"] != keep_name]
    room = KEEP - (1 if keep_name and any(r["name"] == keep_name for r in rows) else 0)
    for row in others[max(room, 0):]:
        try:
            (Path(folder) / row["name"]).unlink()
        except OSError:
            pass


def backup_now(folder, *, code: Optional[str] = None) -> dict:
    """Makes one encrypted backup file in `folder`. `code` lets a caller
    (the restore flow's safety backup) supply its own fresh code; a plain
    "Back up now" leaves it None and gets one made here. Returns
    {"name", "at", "counts", "recovery_code"} - the code is in the return
    value ONLY, never written anywhere by this function."""
    real = check_folder(folder)
    made_code = code or generate_code()
    zip_bytes, manifest = build_archive()
    blob = encrypt_blob(zip_bytes, made_code)
    at = time.time()
    base = _file_name(at)
    name, dest, n = base, Path(real) / base, 1
    # Two backups in the same second (e.g. "Back up now" right before a
    # restore's automatic safety backup) must never share a name - that
    # would silently overwrite the first with the second's content.
    while dest.exists():
        n += 1
        name = base[:-len(FILE_SUFFIX)] + f"-{n}" + FILE_SUFFIX
        dest = Path(real) / name
    tmp = Path(real) / f".{name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        tmp.write_bytes(blob)
        os.replace(tmp, dest)
    except BaseException:
        # A full disk (or a folder that went away) must not leave a half-written
        # hidden file behind in the owner's backup folder.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    _retain(real, keep_name=name)
    return {"name": name, "at": at, "counts": manifest, "recovery_code": made_code,
            "size": dest.stat().st_size}


# ---------------------------------------------------------------------------
#   Setting the folder - the folder-add card, jarvis_documents.py's own shape
# ---------------------------------------------------------------------------

_F_LOCK = threading.Lock()
_F_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_F_SWITCH = threading.Lock()

LAST_WORDS = {
    "set": "Set. Jarvis will back up into that folder.",
    "denied": "You said no, so the folder was not changed.",
    "timed_out": "Nobody answered the card in time, so the folder was not changed.",
    "withdrawn": "You changed your mind before the card was answered, so nothing changed.",
    "refused": "The card could not be answered, so the folder was not changed.",
    "failed": "It was approved, but the setting could not be saved, so the folder was not "
              "changed.",
}


def folder_card(path: str) -> str:
    return "\n".join([
        "Back up into this folder?",
        "",
        f"Folder: {path}",
        "",
        "From now on, \"Back up now\" writes one locked file here - your memory, chat "
        "history, settings and notes, encrypted, with a recovery code shown once that "
        "only you will have. Jarvis keeps the newest "
        f"{KEEP} backups here and deletes older ones.",
        "",
        "If this folder is synced by NordLocker, OneDrive or a similar program, that "
        "program uploads the file, as it does anything else you put there - the file "
        "itself stays locked either way.",
        "",
        f"A lost recovery code means a useless backup: {LOST_CODE}",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _folder_finish(pid: str, outcome: str, why: str = "") -> None:
    with _F_LOCK:
        if _F_STATE["pending"].get("id") == pid:
            _F_STATE["pending"].clear()
        _F_STATE["withdrawn"].discard(pid)
        if _F_STATE["latest"].get("id") not in (None, pid):
            return
        _F_STATE["last"].clear()
        _F_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=LAST_WORDS.get(outcome, ""))
    _audit("backup.folder.card", {"outcome": outcome})


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _decide_folder(pid: str, path: str, gate: Callable, tier_of: Callable,
                   write: Callable[[str], None]) -> None:
    text = folder_card(path)
    detail = {"text": text, "what": "back up into one more folder",
              "setting": "backup folder", "to": path, "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _folder_finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _folder_finish(pid, "refused",
                              f"the gate answered at tier {vtier!r}, which is not a person "
                              f"saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _folder_finish(pid, outcome)
        return _folder_finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _F_SWITCH:
        with _F_LOCK:
            withdrawn = pid in _F_STATE["withdrawn"]
        if withdrawn:
            return _folder_finish(pid, "withdrawn")
        try:
            write(path)
        except Exception as exc:
            return _folder_finish(pid, "failed", type(exc).__name__)
    _audit("backup.folder.set", {})
    _folder_finish(pid, "set")


def _set_folder_now(path: str) -> None:
    _save_settings({"folder": path})


def request_set_folder(body, *, peer=None, local=None, here: Optional[bool] = None,
                       gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                       spawn: Optional[Callable] = None,
                       write: Optional[Callable[[str], None]] = None) -> tuple:
    """POST /api/backup/folder {"path"}. (code, body). 202 and ONE card."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    write = write or _set_folder_now
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"path": "<a folder on this PC>"}'}
    try:
        real = check_folder(body.get("path"))
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except BackupUnavailable as exc:
        return 503, {"ok": False, "error": str(exc)}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; setting the backup "
            f"folder needs a person to say yes, so it must be 'ask'")}
    with _F_LOCK:
        if _F_STATE["pending"]:
            return 409, {"ok": False, "error": "A card to set the backup folder is already "
                                               "waiting - answer it first."}
        pid = uuid.uuid4().hex
        _F_STATE["pending"].update(id=pid, path=real, since=time.time())
        _F_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide_folder(pid, real, gate, tier_of, write))
    except Exception:
        with _F_LOCK:
            _F_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "message": "Waiting for your approval. Nothing "
                                                          "changes unless you approve the "
                                                          "card."}


# ---------------------------------------------------------------------------
#   "Back up now" - no card
# ---------------------------------------------------------------------------

_B_LOCK = threading.Lock()
_B_STATE: dict = {"last": {}}   # {"name","at","counts","ok","error"} - never the code


def _record_backup_outcome(ok: bool, *, name: str = "", at: float = 0.0, counts=None,
                           error: str = "") -> None:
    with _B_LOCK:
        _B_STATE["last"] = {"ok": ok, "name": name, "at": at or time.time(),
                            "counts": counts or {}, "error": error}


def request_backup_now(body=None, *, peer=None, local=None, here: Optional[bool] = None,
                       run: Optional[Callable[[str], dict]] = None) -> tuple:
    """POST /api/backup/now {}. PC only, no card - the folder was already
    approved. Runs synchronously: a backup is small enough (settings,
    notes, a few SQLite files) that there is nothing to poll for."""
    run = run or backup_now
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    try:
        out = run(st["folder"])
    except (BackupUnavailable, ValueError) as exc:
        _record_backup_outcome(False, error=str(exc))
        return 503, {"ok": False, "error": str(exc)}
    except OSError as exc:
        _record_backup_outcome(False, error=f"could not write the backup ({type(exc).__name__})")
        return 500, {"ok": False, "error": f"could not write the backup file "
                                           f"({type(exc).__name__})"}
    _record_backup_outcome(True, name=out["name"], at=out["at"], counts=out["counts"])
    _audit("backup.made", {"ok": True})
    return 200, {"ok": True, "name": out["name"], "at": out["at"], "counts": out["counts"],
                "recovery_code": out["recovery_code"],
                "message": f"Backed up. {LOST_CODE}"}


def request_list(*, peer=None, local=None, here: Optional[bool] = None) -> tuple:
    """GET /api/backup/list. PC only."""
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    st = _load_settings()
    if not st["folder"]:
        return 200, {"ok": True, "backups": []}
    return 200, {"ok": True, "backups": list_backups(st["folder"])}


# ---------------------------------------------------------------------------
#   The phone's run: ask, then keep the code - the file is written on the ask
#   that comes back (2026-10-13; the routes and the reasoning are at
#   PREPARE_ROUTE, near the top)
# ---------------------------------------------------------------------------

_P_LOCK = threading.Lock()
#: ONE run at a time: {"id", "code", "at", "expires_at"}. `code` is held here
#: for at most PENDING_TTL_S and is never written to disk, logged or audited -
#: `_audit` refuses to carry one. Cleared by a commit, by the next prepare, and
#: by a failed code check on an expired run.
_P_STATE: dict = {"pending": {}}


def _clear_pending() -> None:
    with _P_LOCK:
        _P_STATE["pending"].clear()


def _is_expired(row: dict) -> bool:
    try:
        return float(row.get("expires_at") or 0) <= time.time()
    except (TypeError, ValueError):            # pragma: no cover - we write floats
        return True


def request_prepare(body=None, *, peer=None, local=None, here: Optional[bool] = None) -> tuple:
    """POST /api/backup/prepare {} - the phone asks for a backup.

    Answers 200 with the recovery code, which the caller must show the owner
    and send back to `COMMIT_ROUTE` before ANYTHING is written. This PC only
    is not required (the phone is the point); the folder is, because a code
    minted with nowhere to write is a code the owner would be told to keep for
    nothing."""
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    code = generate_code()
    now = time.time()
    pid = uuid.uuid4().hex
    with _P_LOCK:
        _P_STATE["pending"].clear()          # one run at a time; the older code is dropped
        _P_STATE["pending"].update(id=pid, code=code, at=now, expires_at=now + PENDING_TTL_S)
    return 200, {"ok": True, "pending": True, "id": pid, "recovery_code": code,
                 "at": now, "expires_at": now + PENDING_TTL_S,
                 "folder": _folder_name(st["folder"]), "keep": KEEP,
                 "message": PREPARE_LEAD + " " + LOST_CODE}


def request_commit(body=None, *, peer=None, local=None, here: Optional[bool] = None,
                   run: Optional[Callable[[str, str], dict]] = None) -> tuple:
    """POST /api/backup/commit {"id","code"} - the owner says the code is kept.

    THIS PC ONLY. This is the call that writes the file, and a phone never
    writes to the PC's disk by itself: the write is what the PC does. A caller
    that is not this PC is refused BEFORE the body is read, in
    `COMMIT_PC_ONLY`, and nothing is ever written for it.

    The code must be the one `prepare` minted and must still be inside
    PENDING_TTL_S. A wrong or missing code, and an expired or never-started
    run, both write NOTHING - the whole point of the two calls. The file is
    made with that same code (`backup_now(code=...)`), so the code the owner
    kept is the code that opens what lands. Returns the same shape the PC's own
    "Back up now" does, plus the file's byte size, which is what the phone
    shows him next to the code."""
    run = run or (lambda folder, code: backup_now(folder, code=code))
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": COMMIT_PC_ONLY, "pc_only": True}
    want = body.get("code") if isinstance(body, dict) else None
    # Cleaned the way the owner would type it (`_clean_code`: uppercased, and
    # hyphens and spaces dropped), because the phone shows him the code in four
    # groups of five and may hand it back with or without the hyphens. Both
    # sides are cleaned, so either shape matches - and a code that is not this
    # run's still matches nothing.
    want = _clean_code(want)
    with _P_LOCK:
        row = dict(_P_STATE["pending"]) if _P_STATE["pending"] else {}
        if not row or _is_expired(row):
            _P_STATE["pending"].clear()
            return 409, {"ok": False, "error": COMMIT_NO_RUN}
        if not want or want != _clean_code(row["code"]):
            # The run stays open, so a mistyped code can be corrected. Nothing
            # is written either way - that is the guarantee, not the message.
            return 400, {"ok": False, "error": COMMIT_WRONG_CODE}
    st = _load_settings()
    if not st["folder"]:
        _clear_pending()
        return 409, {"ok": False, "error": NO_FOLDER}
    try:
        out = run(st["folder"], row["code"])
    except (BackupUnavailable, ValueError) as exc:
        _record_backup_outcome(False, error=str(exc))
        _clear_pending()
        return 503, {"ok": False, "error": str(exc)}
    except OSError as exc:
        _record_backup_outcome(False, error=f"could not write the backup ({type(exc).__name__})")
        _clear_pending()
        return 500, {"ok": False, "error": f"could not write the backup file "
                                           f"({type(exc).__name__})"}
    size = out.get("size")
    if size is None:
        try:
            size = (Path(st["folder"]) / out["name"]).stat().st_size
        except OSError:                        # pragma: no cover - a write we just made
            size = 0
    _record_backup_outcome(True, name=out["name"], at=out["at"], counts=out["counts"])
    _audit("backup.made", {"ok": True, "from": "phone"})
    _clear_pending()
    return 200, {"ok": True, "name": out["name"], "at": out["at"], "counts": out["counts"],
                 "size": size, "folder": _folder_name(st["folder"]), "keep": KEEP,
                 "recovery_code": out["recovery_code"],
                 "message": f"Backed up. {LOST_CODE}"}


# ---------------------------------------------------------------------------
#   "Delete older backups now" - offered after an "Erase the words"
# ---------------------------------------------------------------------------
# The owner's choice (2026-09-30 audit): erased words can still be readable in
# a backup made before the erase, until it ages out. After an Erase the apps
# offer a button that makes ONE fresh backup (so the newest one is from after
# the erase) and deletes every other backup file. It is a real deletion, so it
# asks: ONE card (change_own_config, the folder card's own action), this PC
# only, listing exactly how many files go. The fresh backup's recovery code is
# shown once, like any other.

_D_LOCK = threading.Lock()
_D_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_D_SWITCH = threading.Lock()
DELETE_ROUTE = "/api/backup/delete-older"

DELETE_LAST_WORDS = {
    "deleted": "Done. Jarvis made one fresh backup and deleted the older ones. Write down the "
               "new backup's recovery code now - it is shown once.",
    "denied": "You said no, so no backup was deleted.",
    "timed_out": "Nobody answered the card in time, so no backup was deleted.",
    "withdrawn": "You changed your mind before the card was answered, so nothing changed.",
    "refused": "The card could not be answered, so no backup was deleted.",
    "failed": "It was approved, but the fresh backup could not be made, so NO backup was "
              "deleted.",
}


def delete_older_card(names: list) -> str:
    return "\n".join([
        "Delete your older backups?",
        "",
        f"Jarvis will make one fresh, locked backup now, then delete {len(names)} older "
        f"backup file{'s' if len(names) != 1 else ''} from your backup folder.",
        "",
        "Why: words you erased can still be readable in a backup made before you erased "
        "them. The fresh one is made after, so it does not have them.",
        "",
        "This cannot be undone: a deleted backup is gone, and so is anything only it held. "
        "The fresh backup gets a NEW recovery code, shown once; the old codes then open "
        "nothing.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _delete_finish(pid: str, outcome: str, why: str = "", *, fresh=None, deleted: int = 0) -> None:
    with _D_LOCK:
        if _D_STATE["pending"].get("id") == pid:
            _D_STATE["pending"].clear()
        _D_STATE["withdrawn"].discard(pid)
        if _D_STATE["latest"].get("id") not in (None, pid):
            return
        _D_STATE["last"].clear()
        _D_STATE["last"].update(outcome=outcome, why=why, at=time.time(), deleted=deleted,
                                message=DELETE_LAST_WORDS.get(outcome, ""), fresh_backup=fresh)
    _audit("backup.delete_older.card", {"outcome": outcome, "deleted": deleted})


def take_delete_older_result() -> Optional[dict]:
    """The last "Delete older backups" outcome, the fresh backup's one-time
    recovery code included - read ONCE, like `take_restore_result`."""
    with _D_LOCK:
        last = dict(_D_STATE["last"])
        if last:
            fresh = last.get("fresh_backup")
            if isinstance(fresh, dict) and "recovery_code" in fresh:
                _D_STATE["last"]["fresh_backup"] = {k: v for k, v in fresh.items()
                                                    if k != "recovery_code"}
    return last or None


def _delete_older_now(folder: str) -> dict:
    """One fresh backup, then every other backup file in the folder deleted
    (only ones shaped like ours). If the fresh one cannot be made, nothing is
    deleted. {"fresh": backup_now's answer, "deleted": n}."""
    fresh = backup_now(folder)
    deleted = 0
    for row in list_backups(folder):
        if row["name"] == fresh["name"]:
            continue
        try:
            (Path(folder) / row["name"]).unlink()
            deleted += 1
        except OSError:
            pass
    return {"fresh": fresh, "deleted": deleted}


def _decide_delete(pid: str, names: list, folder: str, gate: Callable, tier_of: Callable,
                   do: Callable[[str], dict]) -> None:
    text = delete_older_card(names)
    detail = {"text": text, "what": f"delete {len(names)} older backup file(s) after making "
                                    "a fresh one", "setting": "older backups", "to": folder,
              "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _delete_finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _delete_finish(pid, "refused", f"the gate answered at tier {vtier!r}, which is "
                                              f"not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _delete_finish(pid, outcome)
        return _delete_finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _D_SWITCH:
        with _D_LOCK:
            withdrawn = pid in _D_STATE["withdrawn"]
        if withdrawn:
            return _delete_finish(pid, "withdrawn")
        try:
            done = do(folder)
        except Exception as exc:
            return _delete_finish(pid, "failed", type(exc).__name__)
    fresh = done["fresh"]
    _record_backup_outcome(True, name=fresh["name"], at=fresh["at"], counts=fresh["counts"])
    _audit("backup.older_deleted", {"deleted": done["deleted"]})
    _delete_finish(pid, "deleted", deleted=done["deleted"],
                   fresh={"name": fresh["name"], "at": fresh["at"],
                          "recovery_code": fresh["recovery_code"]})


def request_delete_older(body=None, *, peer=None, local=None, here: Optional[bool] = None,
                         gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                         spawn: Optional[Callable] = None,
                         do: Optional[Callable[[str], dict]] = None) -> tuple:
    """POST /api/backup/delete-older {}. PC only. 202 and ONE card (the same
    `change_own_config` action the folder card uses). 409 when there is nothing
    older to delete."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    do = do or _delete_older_now
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    names = [r["name"] for r in list_backups(st["folder"])]
    if not names:
        return 409, {"ok": False, "error": "There are no backups in the folder to delete."}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; deleting backups needs a "
            f"person to say yes, so it must be 'ask'")}
    with _D_LOCK:
        if _D_STATE["pending"]:
            return 409, {"ok": False, "error": "A card to delete older backups is already "
                                               "waiting - answer it first."}
        pid = uuid.uuid4().hex
        _D_STATE["pending"].update(id=pid, since=time.time())
        _D_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide_delete(pid, names, st["folder"], gate, tier_of, do))
    except Exception:
        with _D_LOCK:
            _D_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "count": len(names),
                 "message": "Waiting for your approval. Nothing is deleted unless you approve "
                            "the card."}


# ---------------------------------------------------------------------------
#   Restore preview - counts and a date only, never content
# ---------------------------------------------------------------------------


def _read_manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        try:
            return json.loads(zf.read("manifest.json"))
        except (KeyError, ValueError):
            return {}


def preview_restore(body, *, peer=None, local=None, here: Optional[bool] = None) -> tuple:
    """POST /api/backup/restore/preview {"name","code"}. PC only. Decrypts
    to read manifest.json ONLY - counts and the backup's own date - never
    any other file inside. Nothing is changed."""
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": RESTORE_PC_ONLY, "pc_only": True}
    if not isinstance(body, dict) or not isinstance(body.get("name"), str) or \
            not isinstance(body.get("code"), str):
        return 400, {"ok": False, "error": 'need {"name": "<backup file>", "code": '
                                           '"<recovery code>"}'}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    path = Path(st["folder"]) / body["name"]
    if ".." in body["name"] or "/" in body["name"] or "\\" in body["name"] or not path.is_file():
        return 404, {"ok": False, "error": "That backup file could not be found."}
    try:
        blob = path.read_bytes()
        zip_bytes = decrypt_blob(blob, body["code"])
        manifest = _read_manifest(zip_bytes)
    except WrongCode as exc:
        return 400, {"ok": False, "error": str(exc), "wrong_code": True}
    except (OSError, zipfile.BadZipFile, BackupUnavailable) as exc:
        return 500, {"ok": False, "error": f"that backup could not be read ({type(exc).__name__})"}
    return 200, {"ok": True, "name": body["name"], "created_at": manifest.get("created_at"),
                "counts": manifest, "erase_limit": ERASE_LIMIT}


# ---------------------------------------------------------------------------
#   Restore - one card, always Windows Hello, always this PC
# ---------------------------------------------------------------------------

_R_LOCK = threading.Lock()
_R_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_R_SWITCH = threading.Lock()

RESTORE_LAST_WORDS = {
    # The tray has no "Restart" row, and closing a window only hides it
    # (setup/recovery audit, 2026-09-27): these are the real steps. The
    # safety backup's code is shown once, in this same panel, and lives only
    # in this process's memory - so it comes before the restart.
    "restored": "Restored. First write down the safety backup's recovery code (\"Your data "
               "just before the restore\", in Settings, Backups). Then restart Jarvis so every part of it uses the restored data - "
               "some of it was already open while the files underneath it changed: tray "
               "icon, Stop the backend, then Start the backend (or, if you started Jarvis "
               "yourself in PowerShell, close that window and start it again).",
    "denied": "You said no, so nothing was restored.",
    "timed_out": "Nobody answered the card in time, so nothing was restored.",
    "withdrawn": "You changed your mind before the card was answered, so nothing was "
                "restored.",
    # WHAT THE OWNER READS WHEN A RESTORE IS REFUSED (2026-10-10). It used to
    # be "The card could not be answered, so nothing was restored." - true and
    # useless: it did not say the one thing that helps, which is where a
    # restore can be approved at all. This is the sentence the desktop shows
    # (`last_restore.message`, jarvis-desktop/src/backup-settings.js), so it is
    # plain words with the next step in it. The technical reason for the
    # refusal stays in the record's own `why` (GET /api/backup), for a bug
    # report: it is never what the owner is shown.
    "refused": "Nothing was restored. Restoring has to be done in Jarvis on your PC - open "
               "Jarvis there, then Settings, Backups, and start the restore again.",
    "failed": "It was approved, but the restore itself failed. Everything it had already "
              "changed was put back, so your data is as it was - the safety backup made just "
              "before it is still there.",
    "failed_before": "It was approved, but the safety backup could not be made first, so "
                     "nothing was restored and your data was not changed.",
    "failed_partial": "It was approved, but the restore failed part-way AND putting things "
                      "back did not fully work, so some of your files may now be the backup's "
                      "and some may be as they were. Do not carry on as normal: your data as "
                      "it was just before the restore is in the safety backup (its recovery "
                      "code is shown once in this panel) - restore that one to get back to "
                      "where you were.",
}
#: Added to "restored" when one thing could not be put back.
KEY_WARNING = ("WARNING: the key that opens your restored chat history could not be put back "
               "in Windows Credential Manager, so restored chats may not open. Restore again "
               "after Windows Credential Manager works, or keep the chat-history key from "
               "the PC the backup came from.")


def restore_card(name: str, manifest: dict) -> str:
    when = manifest.get("created_at")
    when_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(when)) if when else "an unknown time"
    # IT MUST NOT NAME A FILE THE GATE PROTECTS. This text is handed to
    # jarvis_gate.check() as the card's `prompt`, and the gate reads that
    # prompt for the names in its own `_PROTECTED` list (jarvis-framework.toml,
    # jarvis_gate.py, jarvis_hud.py, ...) before it raises anything: a prompt
    # that names one is refused at tier "never", and NO CARD IS EVER SHOWN.
    # Measured on the owner's PC, 2026-10-10: this card said "(the .py files
    # beside jarvis_hud.py)" and the audit log reads
    # `gate.refused_protected / restore_backup / <redacted 13 chars>` followed
    # by `backup.restore.card / outcome "refused"` - so a restore could never
    # be approved by anyone, at the PC or anywhere else. The folder is named
    # instead of the file, which is also plainer; test_backup.py keeps it that
    # way by checking this text against the gate's own list.
    return "\n".join([
        "Restore Jarvis from this backup?",
        "",
        f"Backup: {name}",
        f"Made: {when_text}",
        "",
        "This REPLACES your memory and chat files, your knowledge and trace stores, review "
        "decks, settings and notes with that day's "
        "copies, and puts that day's copy of Jarvis's own program files (the .py files in the "
        "folder Jarvis runs from) back into it. Anything you added or changed in "
        "them since is lost - unless it is in the safety backup Jarvis makes first. Only files "
        "the backup does not have at all are left as they are.",
        "",
        "Because the program files are included from 2026-10-05 on, restoring an OLDER backup "
        "also puts back the older program and undoes any updates applied to the code since. "
        "Run apply-patches.ps1 again afterwards if you want those back.",
        "",
        "Before doing this, Jarvis will back up your CURRENT data first, with a fresh "
        "recovery code shown once, so this restore itself can be undone.",
        "",
        ERASE_LIMIT,
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _restore_finish(pid: str, outcome: str, *, why: str = "", safety=None,
                    message: Optional[str] = None, warning: str = "") -> None:
    with _R_LOCK:
        if _R_STATE["pending"].get("id") == pid:
            _R_STATE["pending"].clear()
        _R_STATE["withdrawn"].discard(pid)
        if _R_STATE["latest"].get("id") not in (None, pid):
            return
        _R_STATE["last"].clear()
        _R_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=(message if message is not None
                                         else RESTORE_LAST_WORDS.get(outcome, "")),
                                safety_backup=safety, warning=warning)
    _audit("backup.restore.card", {"outcome": outcome})


def take_restore_result() -> Optional[dict]:
    """The last restore's outcome, INCLUDING the safety backup's one-time
    recovery code if there is one - read ONCE. A second call never sees the
    code again, so it can never be re-read off a stale poll, logged by a
    later request, or left sitting in memory for longer than one answer
    needs it."""
    with _R_LOCK:
        last = dict(_R_STATE["last"])
        if last:
            safety = last.get("safety_backup")
            if isinstance(safety, dict) and "recovery_code" in safety:
                _R_STATE["last"]["safety_backup"] = {k: v for k, v in safety.items()
                                                     if k != "recovery_code"}
    return last or None


def _inside(root: Path, rel: str, *, flat: bool = False) -> Optional[Path]:
    """`root` joined with the archive path `rel`, or None when `rel` could
    land anywhere but inside `root`: a "..", an empty or "." part, a
    leading "/", a backslash, or a drive letter (on Windows, `root /
    "C:/x"` IS "C:/x"). `flat`: one name only, no folder (db/ and
    settings/ hold top-level files only - build_archive never writes
    deeper). Security/privacy audit, 2026-09-27: restore used to join
    whatever name the archive held, so "db/../../x" wrote outside the
    settings folder. build_archive never writes such a name, and a file
    needs its recovery code to open, so this is a second lock, not a
    reported attack."""
    if not rel or "\\" in rel or rel.startswith("/") or ":" in rel:
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts) or (flat and len(parts) != 1):
        return None
    return root.joinpath(*parts)


class RestoreError(Exception):
    """A restore that stopped. `state`: "unchanged" (nothing had been replaced
    yet, or everything replaced was put back) or "partial" (putting back failed
    too - some files may be the backup's and some the old ones)."""

    def __init__(self, message: str, state: str = "unchanged"):
        super().__init__(message)
        self.state = state


def _apply_restore(zip_bytes: bytes) -> dict:
    """Writes the archive's files back. Only adds and overwrites: a file that
    is present now but absent from the backup is left alone. Returns a short
    summary for the audit log (counts only). A name that would land outside
    its own folder is skipped and counted (`_inside`).

    All-or-nothing, as far as a plain file system allows (2026-09-30 audit):
      1. every file is read from the archive and written beside its place as a
         hidden temp file first - a bad or full disk fails here, before
         anything real is touched;
      2. each real file is copied aside, then replaced in one step
         (os.replace); a database's leftover -wal/-shm files (which belong to
         the OLD database and would corrupt the restored one) are moved aside
         too;
      3. on ANY failure everything already replaced is put back and every temp
         file removed (RestoreError.state says whether that worked).
    Nothing here can pause the programs that have these files open: the
    backend has no hook for that, so a restore should be followed by a restart
    (the restore message says so)."""
    conf = _config_dir()
    conf.mkdir(parents=True, exist_ok=True)
    applied = {"databases": 0, "settings_files": 0, "notes_files": 0, "voice_files": 0,
               "framework_toml": False, "chat_history_key": False, "study_decks_key": False,
               "source_files": 0,
               "skipped": 0, "chat_history_key_failed": False, "study_decks_key_failed": False}
    plan: list = []              # (dest, data, is_database)
    key_data = None
    study_key_data = None
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Read ONCE, outside the loop: the one list of what may land in the
        # settings folder (see `_named_settings_entries`).
        allowed_settings = set(_named_settings_entries(zf.namelist()))
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/") or name == "manifest.json":
                continue
            where = None
            if name.startswith("db/"):
                where = ("databases", _inside(conf, name[len("db/"):], flat=True))
            elif name.startswith("settings/"):
                # The JSON files, plus the named ones whose extension is not
                # `.json` (config.toml, speed.jsonl - 2026-10-13). Both land in
                # the settings folder; `_named_settings_entries` is the single
                # statement of what may, so this cannot drift from
                # build_archive. A name that is neither is counted as skipped,
                # not written anywhere.
                if name not in allowed_settings:
                    applied["skipped"] += 1
                    continue
                where = ("settings_files", _inside(conf, name[len("settings/"):], flat=True))
            elif name.startswith("notes/"):
                where = ("notes_files", _inside(conf / "notes", name[len("notes/"):]))
            elif name.startswith("voice/"):
                where = ("voice_files", _inside(conf / "voice", name[len("voice/"):]))
            elif name.startswith(SOURCE_PREFIX):
                # The backend's own program files go back into the folder this
                # module runs from (2026-10-05) - `_source_dir()`, read HERE and
                # not before the chain, so an archive with no `source/` entry
                # (every backup made before this change) never even asks where
                # the sources live. `flat=True`: build_archive writes one name
                # per file, so a nested name is a tampered archive, not a
                # layout to honour - `_inside` refuses it and it is counted
                # under "skipped" like any other bad name.
                where = ("source_files",
                         _inside(_source_dir(), name[len(SOURCE_PREFIX):], flat=True))
            if where is not None and where[1] is None:
                applied["skipped"] += 1
                continue
            data = zf.read(info)
            if where is not None:
                plan.append((where[1], data, where[0] == "databases"))
                applied[where[0]] += 1
            elif name == "jarvis-framework.toml":
                toml_dest = _toml_source()
                plan.append((toml_dest if toml_dest is not None else (conf / name), data, False))
                applied["framework_toml"] = True
            elif name == "secrets/chat-history-key.b64":
                key_data = data
            elif name == "secrets/study-decks-key.b64":
                study_key_data = data
    tag = uuid.uuid4().hex[:8]
    staged: list = []            # (dest, temp, is_database)
    swapped: list = []           # (dest, copy of the old file or None)
    aside: list = []             # (path, where it was moved to) - wal/shm
    try:
        for dest, data, is_db in plan:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / f".{dest.name}.{tag}.tmp"
            staged.append((dest, tmp, is_db))       # listed first: cleaned up even if half-written
            tmp.write_bytes(data)
    except BaseException as exc:
        _remove_all([t for _d, t, _i in staged])
        raise RestoreError(f"could not prepare the files ({type(exc).__name__})") from exc
    try:
        for dest, tmp, is_db in staged:
            old = None
            if dest.exists():
                old = dest.parent / f".{dest.name}.{tag}.old"
                shutil.copyfile(dest, old)
            swapped.append((dest, old))
            os.replace(tmp, dest)
            if is_db:
                for suffix in ("-wal", "-shm"):
                    side = dest.parent / (dest.name + suffix)
                    if side.exists():
                        moved = dest.parent / f".{side.name}.{tag}.old"
                        shutil.copyfile(side, moved)
                        aside.append((side, moved))
                        side.unlink()
    except BaseException as exc:
        problems = _put_back(swapped, aside)
        _remove_all([t for _d, t, _i in staged])
        raise RestoreError(f"could not replace a file ({type(exc).__name__})",
                           "partial" if problems else "unchanged") from exc
    _remove_all([old for _d, old in swapped if old] + [m for _p, m in aside])
    if key_data is not None:
        try:
            import jarvis_token_store as ts
            import jarvis_chat_log
            ts.WindowsStore(target=jarvis_chat_log.KEY_TARGET).write(key_data.decode("ascii"))
            applied["chat_history_key"] = True
        except Exception:
            # Not swallowed: the files ARE restored, but chats written with the
            # backup's key will not open without it. The outcome says so.
            applied["chat_history_key_failed"] = True
    if study_key_data is not None:
        try:
            import jarvis_token_store as ts
            import jarvis_decks
            ts.WindowsStore(target=jarvis_decks.KEY_TARGET).write(study_key_data.decode("ascii"))
            applied["study_decks_key"] = True
            jarvis_decks.forget_key()   # the running store must reopen with this key
        except Exception:
            applied["study_decks_key_failed"] = True
    return applied


def _remove_all(paths) -> None:
    for pth in paths:
        try:
            Path(pth).unlink()
        except OSError:
            pass


def _put_back(swapped: list, aside: list) -> list:
    """Undoes a half-finished swap. Returns what could NOT be put back."""
    problems = []
    for dest, old in reversed(swapped):
        try:
            if old is not None:
                os.replace(old, dest)
            elif Path(dest).exists():
                Path(dest).unlink()
        except OSError as exc:
            problems.append((str(dest), type(exc).__name__))
    for side, moved in aside:
        try:
            os.replace(moved, side)
        except OSError as exc:
            problems.append((str(side), type(exc).__name__))
    return problems


def _decide_restore(pid: str, name: str, code: str, manifest: dict, zip_bytes: bytes,
                    gate: Callable, tier_of: Callable, apply_fn: Callable,
                    safety_fn: Callable) -> None:
    text = restore_card(name, manifest)
    detail = {"text": text, "what": "replace memory, chat history, review decks, settings and notes with "
                                    f"the backup {name}", "setting": "restore from backup",
              "to": name, "leaves_this_pc": False}
    try:
        v = gate(RESTORE_ACTION, detail, text)
    except Exception as exc:
        return _restore_finish(pid, "refused", why=f"the approval gate failed "
                                                   f"({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(RESTORE_ACTION) != "ask":
        # The gate answered WITHOUT asking anybody: it refused before any card
        # existed (its own protected-file rule sees a name it protects in the
        # card's text, the tier is "never", or the policy cannot be read).
        # The owner is told what happened and what to do next, in the plain
        # words the app shows (RESTORE_LAST_WORDS["refused"]); the diagnosis -
        # which tier, and the gate's own sentence - goes in `why`, which only
        # GET /api/backup returns, for a bug report. This line used to be the
        # other way round: the record kept `the gate answered at tier 'never',
        # which is not a person saying yes` - accurate, and no use at all to
        # the owner, who read it as the answer to a restore that never
        # happened (2026-10-10).
        return _restore_finish(pid, "refused",
                               why=f"the gate answered at tier {vtier!r} without asking anyone: "
                                   f"{str(getattr(v, 'reason', '') or 'no reason given')[:300]}")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _restore_finish(pid, outcome)
        return _restore_finish(pid, "refused", why=str(getattr(v, "reason", "refused"))[:200])
    with _R_SWITCH:
        with _R_LOCK:
            withdrawn = pid in _R_STATE["withdrawn"]
        if withdrawn:
            return _restore_finish(pid, "withdrawn")
        try:
            safety = safety_fn()
        except Exception as exc:
            return _restore_finish(pid, "failed", why=f"the safety backup failed "
                                                       f"({type(exc).__name__})",
                                   message=RESTORE_LAST_WORDS["failed_before"])
        safety_out = {"name": safety["name"], "at": safety["at"],
                      "recovery_code": safety["recovery_code"]}
        try:
            applied = apply_fn(zip_bytes)
        except Exception as exc:
            # "Your data was not changed" is only said when that is true.
            partial = getattr(exc, "state", "unchanged") == "partial"
            return _restore_finish(
                pid, "failed", why=type(exc).__name__, safety=safety_out,
                message=RESTORE_LAST_WORDS["failed_partial" if partial else "failed"])
    _audit("backup.restored", {"applied": applied})
    key_failed = bool(isinstance(applied, dict) and applied.get("chat_history_key_failed"))
    _restore_finish(pid, "restored", safety=safety_out,
                    warning=KEY_WARNING if key_failed else "",
                    message=RESTORE_LAST_WORDS["restored"] + (" " + KEY_WARNING if key_failed
                                                              else ""))


def request_restore(body, *, peer=None, local=None, here: Optional[bool] = None,
                    gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                    spawn: Optional[Callable] = None, apply_fn: Optional[Callable] = None,
                    safety_fn: Optional[Callable] = None,
                    armed: Optional[Callable[[], bool]] = None) -> tuple:
    """POST /api/backup/restore {"name","code"}. (code, body). 202 and ONE
    card that always needs Windows Hello and always comes from this PC -
    jarvis_owner_check.PC_ONLY_ACTIONS refuses its approval from anywhere
    else, whatever the gate's own risk table says about `restore_backup`.

    A caller that is not this PC can never approve that card, so it is
    refused here, in plain words and before the body is read - never with a
    202 that promises a card which cannot appear (2026-10-10)."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    apply_fn = apply_fn or _apply_restore
    armed = armed or _owner_check_armed
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": RESTORE_PC_ONLY, "pc_only": True}
    if not isinstance(body, dict) or not isinstance(body.get("name"), str) or \
            not isinstance(body.get("code"), str):
        return 400, {"ok": False, "error": 'need {"name": "<backup file>", "code": '
                                           '"<recovery code>"}'}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    if not armed():
        return 503, {"ok": False, "error": "Jarvis cannot check it is you on this PC yet "
                                           "(Windows Hello), so a restore is refused until "
                                           "it can - restart Jarvis after setting up Windows "
                                           "Hello."}
    path = Path(st["folder"]) / body["name"]
    if ".." in body["name"] or "/" in body["name"] or "\\" in body["name"] or not path.is_file():
        return 404, {"ok": False, "error": "That backup file could not be found."}
    try:
        blob = path.read_bytes()
        zip_bytes = decrypt_blob(blob, body["code"])
        manifest = _read_manifest(zip_bytes)
    except WrongCode as exc:
        return 400, {"ok": False, "error": str(exc), "wrong_code": True}
    except (OSError, zipfile.BadZipFile, BackupUnavailable) as exc:
        return 500, {"ok": False, "error": f"that backup could not be read ({type(exc).__name__})"}
    t = tier_of(RESTORE_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{RESTORE_ACTION} is tier {t!r} in jarvis-framework.toml; restoring needs a "
            f"person to say yes, so it must be 'ask'")}
    safety_fn = safety_fn or (lambda: backup_now(st["folder"]))
    with _R_LOCK:
        if _R_STATE["pending"]:
            return 409, {"ok": False, "error": "A restore card is already waiting - answer "
                                               "it first."}
        pid = uuid.uuid4().hex
        _R_STATE["pending"].update(id=pid, name=body["name"], since=time.time())
        _R_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide_restore(pid, body["name"], body["code"], manifest, zip_bytes,
                                      gate, tier_of, apply_fn, safety_fn))
    except Exception:
        with _R_LOCK:
            _R_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "message": "Waiting for your approval, with "
                                                          "Windows Hello. Nothing changes "
                                                          "unless you approve."}


# ---------------------------------------------------------------------------
#   GET /api/backup
# ---------------------------------------------------------------------------


def view(*, here: bool = False) -> dict:
    """GET /api/backup. From this PC: the folder, whether a card is
    waiting, how the last folder-card and the last backup/restore went, and
    the retention count. From anywhere else (the phone): only whether a
    backup has ever been made and when the last one was - "last backup: 3
    days ago" and nothing more (the design's own words; the full flow is
    desktop-only, docs/ARCHITECTURE.md section 8)."""
    with _B_LOCK:
        last_backup = dict(_B_STATE["last"]) if _B_STATE["last"] else None
    if not here:
        return {"available": True,
                "last_backup_at": last_backup["at"] if last_backup else None}
    st = _load_settings()
    with _F_LOCK:
        pending = dict(_F_STATE["pending"]) if _F_STATE["pending"] else None
        last_folder_card = dict(_F_STATE["last"]) if _F_STATE["last"] else None
    with _R_LOCK:
        restore_pending = dict(_R_STATE["pending"]) if _R_STATE["pending"] else None
    # take_restore_result() takes _R_LOCK itself - called after releasing it
    # above, never from inside it (that would deadlock: _R_LOCK is a plain
    # Lock, not reentrant).
    last_restore = take_restore_result()
    with _D_LOCK:
        delete_pending = dict(_D_STATE["pending"]) if _D_STATE["pending"] else None
    last_delete = take_delete_older_result()
    return {"available": True, "folder": st["folder"], "keep": KEEP,
           "pending_delete_older_card": delete_pending, "last_delete_older": last_delete,
           "last_backup": last_backup, "pending_folder_card": pending,
           "last_folder_card": last_folder_card, "pending_restore_card": restore_pending,
           "last_restore": last_restore, "erase_limit": ERASE_LIMIT}


# ---------------------------------------------------------------------------
#   Wiring into jarvis_hud.py's server (backup.patch)
# ---------------------------------------------------------------------------

_ARMED = False


def armed() -> bool:
    return _ARMED


def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def handle_get(route: str, *, peer=None, local=None) -> tuple:
    here = _from_this_pc(peer, local)
    if route == PATH:
        return 200, view(here=here)
    if route == LIST_ROUTE:
        return request_list(peer=peer, local=local, here=here)
    if route == STATUS_ROUTE:
        return 200, status_view()
    return 404, {"ok": False, "error": "not found"}


def handle_post(route: str, body, *, peer=None, local=None) -> tuple:
    here = _from_this_pc(peer, local)
    if route == FOLDER_ROUTE:
        return request_set_folder(body, peer=peer, local=local, here=here)
    if route == NOW_ROUTE:
        return request_backup_now(body, peer=peer, local=local, here=here)
    if route == PREPARE_ROUTE:
        return request_prepare(body, peer=peer, local=local, here=here)
    if route == COMMIT_ROUTE:
        return request_commit(body, peer=peer, local=local, here=here)
    if route == PREVIEW_ROUTE:
        return preview_restore(body, peer=peer, local=local, here=here)
    if route == RESTORE_ROUTE:
        return request_restore(body, peer=peer, local=local, here=here)
    if route == DELETE_ROUTE:
        return request_delete_older(body, peer=peer, local=local, here=here)
    return 404, {"ok": False, "error": "not found"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the nine routes above are
    answered here, after the server's own origin and token checks; every
    other request goes straight to the original - the same shape as
    jarvis_documents.py's `install`."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_backup", False):
        _ARMED = True
        return ("  backups    /api/backup, folder, now, list, status, prepare, commit, "
                "restore (already on)")

    from urllib.parse import urlsplit

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
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/") or "/"
        if route not in (PATH, LIST_ROUTE, STATUS_ROUTE):
            return get0(self)
        if not _allowed(self):
            return None
        peer, local = _peer_local(self)
        try:
            code, out = handle_get(route, peer=peer, local=local)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in (FOLDER_ROUTE, NOW_ROUTE, PREPARE_ROUTE, COMMIT_ROUTE,
                         PREVIEW_ROUTE, RESTORE_ROUTE, DELETE_ROUTE):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "error": "bad JSON"})
        peer, local = _peer_local(self)
        try:
            code, out = handle_post(route, body, peer=peer, local=local)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_backup = True
    do_POST._jarvis_backup = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  backups    /api/backup, folder, now, list, status, prepare, commit, restore"


def _reset_for_tests() -> None:
    global _ARMED
    _ARMED = False
    with _F_LOCK:
        _F_STATE.update(pending={}, withdrawn=set(), last={}, latest={})
    with _R_LOCK:
        _R_STATE.update(pending={}, withdrawn=set(), last={}, latest={})
    with _B_LOCK:
        _B_STATE["last"] = {}
    with _P_LOCK:
        _P_STATE["pending"].clear()
    with _D_LOCK:
        _D_STATE.update(pending={}, withdrawn=set(), last={}, latest={})


if __name__ == "__main__":
    print(f"  config dir  {_config_dir()}")
    print(f"  settings    {_load_settings()}")
    print(f"  crypto      {'ready' if AESGCM is not None and Argon2id is not None else NO_CRYPTO}")
