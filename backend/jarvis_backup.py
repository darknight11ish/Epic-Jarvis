"""jarvis_backup.py - one locked backup file, a recovery code, restore with a
card (the owner's decision of 2026-09-27, CLAUDE.md; the design in
docs/CUTTING-EDGE-2026-09-26-round2-trust.md, "2. Encrypted backup and plain
restore"). docs/JARVIS-API.md section 45.

NEW MODULE, shipped whole. backup.patch adds one call at start-up,
`install(Handler, ...)`, which answers the ten routes below (the same shape
as jarvis_documents.py). The tenth is `DISMISS_ROUTE` (2026-10-20): the last
restore's outcome is now PERSISTED in `last-restore.json` so a poll can never
swallow it, and dismissing it is an explicit POST rather than a side effect of
reading it.

THE 2026-10-21 AUDIT FIXES (independent audit of the 2026-10-20 slice;
`.dsh-scratch/AUDIT-678-BACKUP-FAIL-CLOSED-2026-10-21.md`, finding ids in the
code and the suite): `last-restore.json` never rides into a backup (M1); a
paired device cannot dismiss the notice while this PC still holds the safety
backup's unread one-time code, because that would destroy the only way to open
it (M2); a failed record write leaves an honest fallback marker, or removes the
stale record, so a restart never reports an older restore as the current one
(M3); the record is written under the same lock that publishes it (LOW-1); a
partial restore failure names what it had replaced (LOW-2); an exception in
verification is a clean refusal rather than a dead card thread (LOW-3); a
verification-failed safety backup is removed, or named if it cannot be (LOW-4);
and a successful apply re-checks the safety backup's presence/size and says so
if it has gone (LOW-5). The fail-closed order and the one-time-code rule are
UNCHANGED by all of that.

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
    (jarvis_receipts.py); and (2026-10-21) price-radar.db, the flight price
    history (jarvis_price_radar.py) - a fare observed yesterday cannot be
    re-fetched, so the history is carried like the owner's other data. A receipt holds the owner's own words - what changed,
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
  * The notes folder (`notes/`), copied whole, recursively.
  * **NOT the voice enrolment folder (`voice/`)** (2026-10-23, Backup-Gap 1):
    the owner's own voice-print is sealed with a key in Windows Credential
    Manager on THIS PC, so after a bare-metal restore it could not be opened on
    the new PC. Carrying it would restore files that look present and are dead.
    This module leaves it out, records `voice_profile_backed_up: false` and its
    plain-words note in the manifest, and the restore path never writes a voice
    file it cannot open on this PC (older archives that carried sealed voice
    files are skipped with `voice_needs_re_enrolment` rather than copied).
    `voice-models/` (downloaded engine files) and `voices/` (the custom-voice
    bank) were never carried either.
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
  * SEVEN more databases that were measured on 2026-10-13 (five of them) and
    2026-10-16 (the search index) and left out on purpose - agents.db,
    audit.db, digest.db, sync_state.db and telemetry.db, plus
    documents-index.db, plus media-index.db (F5 S2, 2026-10-19). Each one's
    reason is written beside it in `NOT_BACKED_UP` above, so the decision is
    recorded rather than inferred from its absence. In one line each:
    agents.db and digest.db are empty template tables the modules recreate,
    audit.db is a security trail rather than memory, sync_state.db holds sync
    cursors whose staleness loses data, telemetry.db is measurements of the
    machine with its writer switched off by design, documents-index.db is a
    derived ranking rebuilt from the files it describes, holding no document
    text, and media-index.db is the readable words kept from recordings on the
    owner's decision - excluded so a Delete cannot be undone from a backup
    made before it.
  * The File Guardian's store, `$OPENJARVIS_HOME/guardian/`: its
    `guardian.jsonl` journal, `pins.json` and `blobs/<sha256>.gz` (capped at
    250 MiB, jarvis_file_guardian.py) are device-local file history, not
    memory - the journal names paths on this PC, and the blob store must never
    bloat an archive or carry one off it. `energy.jsonl` (machine measurements,
    writer off by default, 500-row cap) and `ledger-anchors.jsonl` (anchors the
    owner copies elsewhere, and an old anchor beside a restored ledger.db could
    wrongly flag it) are the other non-SQLite stores left out. Each is recorded
    with its reason in `NOT_BACKED_UP_PATHS`, and the coverage check in
    test_backup.py fails if a module names a `.jsonl` store that is neither
    carried nor written down there.
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
import stat
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
#: Dismissing the last restore's outcome (Gemini ruling 8.1, 2026-10-20).
#: The outcome is persisted and readable by both apps until the owner clears
#: it; this route is the ONLY thing that clears it, so no poll can swallow it.
#: Any paired device may ask, BUT while this PC still holds the safety
#: backup's one-time recovery code (the PC has not read it out yet) a device's
#: dismiss is refused with DISMISS_CODE_PENDING: clearing the record would
#: destroy the only copy of the code and leave the safety backup unopenable
#: (audit 2026-10-21, M2). The PC itself may always clear it - the owner is
#: sitting there and can read the code in the same panel first. The restore
#: itself stays THIS PC ONLY.
DISMISS_ROUTE = "/api/backup/restore/dismiss"
#: Said to a paired device that asks to dismiss while the PC has not shown
#: this restore's one-time recovery code yet. Plain words: what to do instead.
DISMISS_CODE_PENDING = ("Read it on the PC first: this restore made a safety backup whose "
                        "recovery code is shown only once, on the PC (Settings, Backups), "
                        "and clearing the notice from here would throw that code away. "
                        "Nothing was cleared - open Jarvis on the PC and read the code, "
                        "then dismiss the notice from wherever you like.")
#: A safety backup that could not be verified before the restore would touch
#: anything. The audit record of such a refusal carries this exact reason.
SAFETY_UNVERIFIED = "safety_unverified"

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
#: price-radar.db (2026-10-21) is the flight price history (jarvis_price_radar.py):
#: whole-cent fare snapshots per tracked route. A fare observed yesterday cannot
#: be re-fetched -- the page only shows today's price -- so losing it loses the
#: history itself, which is the same "the owner's own data, not a cache" reason
#: receipts.db and voiceprint.db are carried. It is read-only in the module that
#: writes it until the owner turns [price_radar] on.
SOURCE_DBS = ("memory.db", "chat-history.db", "schedule.db", "feedback.db", "projects.db",
              "goals.db", "study.db", "arbiter.db", "jobs.db", "ledger.db", "watch.db",
              "tasks.db", "knowledge.db", "traces.db",
              "receipts.db", "voiceprint.db", "price-radar.db")

#: How long a snapshot/table-count connection waits for a lock before giving
#: up. `sqlite3.connect(timeout=...)` IS SQLite's busy handler (it passes the
#: seconds to `sqlite3_busy_timeout` in milliseconds), so this is the same
#: 10-second wait the rest of the backend asks for - `jarvis_receipts.py`,
#: `jarvis_ledger.py`, `jarvis_tasks.py` and the rest. A backup runs while
#: Jarvis is live and writing; the connect default is 5 seconds, which is
#: short enough for a busy writer to lose a whole database out of the archive
#: instead of waiting for it.
DB_BUSY_TIMEOUT_S = 10.0

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
#: documents-index.db  the search index behind `search` in jarvis_documents.py
#:             (2026-10-16). There is nothing in it to restore: it is rebuilt
#:             from the folders the owner listed on the next search, and it
#:             holds no document text at all (its FTS5 table is contentless -
#:             the words are indexed, the text is not stored). A restored copy
#:             could only be a stale ranking of files that have moved on, which
#:             is the same call digest.db gets below. The files themselves are
#:             the source of truth, and those are the owner's own folders,
#:             backed up by whatever he keeps them in - not by this.
#:
#:             `notes-index.db` was here for a day and is NOT: the Obsidian
#:             vault search it would have served (jarvis_notes.py) keeps its
#:             documented "every word must match" contract, and `bm25` ranks by
#:             ANY matching word, so an index there would have changed what a
#:             vault search returns. That change was made and reverted; see
#:             backend/test_obsidian_notes.py, which caught it.
#:
#: media-index.db  the readable words kept from recordings and videos
#:             (jarvis_media_index.py; F5 S2, owner decision 2026-10-19).
#:             This is the one exclusion that is NOT derived: it holds a
#:             readable copy of what was said, because the owner chose that
#:             over a word list. It must never be in a backup: a backup made
#:             before a Delete would still hold the words afterwards, and
#:             "Delete really deletes" is the promise the Settings card makes.
#:             The recording itself stays in the owner's own folder, backed up
#:             by whatever he keeps them in - never by this.
NOT_BACKED_UP = {
    "agents.db": "template tables the modules recreate; empty today (0 rows)",
    "audit.db": "a security trail, not memory; restoring a stale one misleads",
    "digest.db": "generated digests, re-made from data that is backed up",
    "sync_state.db": "sync cursors; a restored old cursor loses un-fetched items",
    "telemetry.db": "machine measurements, not the owner's data; writer off",
    "documents-index.db": "derived word index; rebuilt from the folders on the next search",
    "media-index.db": "kept readable speech; excluded so Delete cannot be undone from an older backup",
}

#: Non-SQLite stores under the settings folder that are deliberately NOT
#: carried, with a reason each (2026-10-18, the Frontier 2 backup audit). Kept
#: beside NOT_BACKED_UP rather than in it: the values here are relative paths
#: (a file, or a directory ending in "/"), so the coverage check in
#: test_backup.py can see the `.jsonl` and blob stores its older `.db`-only
#: scan could not. A path is a decision somebody wrote, not an omission.
NOT_BACKED_UP_PATHS = {
    "guardian/guardian.jsonl": "device-local file history; its path rows name this PC, not memory",
    "guardian/pins.json": "the guardian pins which saved versions to keep; useful only with its blobs",
    "guardian/blobs/": "saved file bytes, up to 250 MiB, device-local; must never bloat an archive",
    "energy.jsonl": "energy measurements: GPU power draw, machine data; writer off by default, 500-row cap",
    "ledger-anchors.jsonl": "tamper anchors the owner copies off the PC; stale ones would flag a restore",
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

#: Plain words for the one thing a backup deliberately does NOT carry
#: (2026-10-23, Backup-Gap 1 of Gemini's security work order). The voice
#: profile is sealed with a key in Windows Credential Manager on THIS PC; after
#: a bare-metal restore that key is gone, so the sealed files could not be
#: opened on the new PC. Carrying them would restore files the owner believes
#: are back while they are dead - so they are left out, the manifest says so in
#: these exact words, and a restore never writes a voice file it cannot open.
VOICE_REENROL_NOTE = (
    "Your voice profile is not carried in a backup: it is locked to this PC, "
    "so it would not work on a new one. After a bare-metal restore, enrol your "
    "voice again in Settings, Voice.")


def not_backed_up_reason(path) -> str:
    """The recorded reason the settings-folder `path` is deliberately not
    carried, or "" when this module has no record of it.

    `path` may be an absolute path, a relative path (`guardian/blobs/x.gz`) or
    just the name a module uses (`guardian.jsonl`, `agents.db`). This is what
    makes an exclusion checkable instead of inferred from absence: the tests
    ask it about every store a backend module names, and about the guardian
    store laid out for real. Backslashes are compared as forward slashes;
    a directory entry (one ending in "/") covers everything below it.
    """
    raw = str(path or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    raw = raw.strip("/")
    if not raw:
        return ""
    base = raw.rsplit("/", 1)[-1]
    if base in NOT_BACKED_UP:
        return NOT_BACKED_UP[base]
    for entry, why in NOT_BACKED_UP_PATHS.items():
        e = entry.strip().replace("\\", "/").strip("/")
        if not e:
            continue
        if raw == e or raw.endswith("/" + e) or base == e or e.endswith("/" + base):
            return why
        if raw.startswith(e + "/") or ("/" + e + "/") in ("/" + raw):
            return why
    return ""


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


#: The LAST restore's outcome, PERSISTED (Gemini ruling 8.1, 2026-10-20). It
#: used to live only in this process's memory: any later GET /api/backup - the
#: desktop's own panel poll, or the phone asking for the folder - handed the
#: outcome (and once, the safety backup's recovery code) to whoever read first,
#: and a restart lost it entirely. Now the record is written here and read
#: until the owner DISMISSES it (`DISMISS_ROUTE`), not until someone polls.
LAST_RESTORE_FILE = "last-restore.json"

#: Said IN the persisted record, because the recovery code itself is
#: deliberately absent: the code is one-time and never touches disk
#: (`settings_path`, `take_restore_result`). Persisting the code would turn a
#: theft of one small file into "open every older backup", which is exactly the
#: rule the design refuses - so the durable record keeps everything EXCEPT the
#: code, and says so rather than looking silently incomplete.
RECOVERY_CODE_HINT = ("The safety backup's recovery code was shown once, in the panel, when "
                      "the restore finished. It is deliberately NOT stored on disk by "
                      "Jarvis (a stored code would open the safety backup for anyone who "
                      "read the file), so write it down when you see it.")

#: The short record left when the FULL `last-restore.json` could not be written
#: (a full disk, a folder that went away). The previous restore's record would
#: otherwise stay there and be reported as the current one after a restart
#: (audit 2026-10-21, M3), so the fallback says plainly what happened and keeps
#: only the outcome it knows; the names of restored files are what is lost.
PERSIST_FAILED_WORDS = ("The restore finished, but Jarvis could not save its full record to "
                        "disk (a full disk, or the settings folder could not be written). "
                        "What is known is shown here; after a restart only this short notice "
                        "remains, without the list of restored files. The safety backup's "
                        "recovery code was shown once, in the panel.")

#: The most a `last-restore.json` may be before it is refused as damaged. The
#: record is a handful of short fields; anything bigger is not one of ours (a
#: corrupt or hand-edited file must not be read into memory without a bound).
MAX_RESTORE_RESULT_BYTES = 256 * 1024

#: Added when the safety backup that made the restore undoable is not there any
#: more after the apply finished (audit 2026-10-21, LOW-5).
SAFETY_LOST_WARNING = ("WARNING: the safety backup made just before this restore is no longer "
                       "in the backup folder, so the one-time recovery code can no longer "
                       "open it. Your data was restored, but the step back is gone - check "
                       "the backup folder before relying on it.")


def last_restore_path() -> Path:
    """last-restore.json in the Jarvis settings folder.

    Everything a reader needs to show the last restore - outcome, when, the
    safety backup's NAME, and the exact filenames replaced - EXCEPT the
    one-time recovery code, which is never written here (see
    `RECOVERY_CODE_HINT`)."""
    return _config_dir() / LAST_RESTORE_FILE


def _own_settings_files() -> tuple:
    """The settings-folder JSON files that are JARVIS'S OWN BOOKKEEPING.

    `backup.json` names the backup folder; `last-restore.json` is the last
    restore's record. Neither is owner data, so neither belongs inside a
    backup - and the restore's own settings allow-list must refuse them too:
    a `last-restore.json` riding in an archive would be restored as if it were
    a settings file and could put an OLD record over the current one (audit
    2026-10-21, M1). One tuple, so the archive rule and the restore rule
    cannot drift apart."""
    return (settings_path().name, last_restore_path().name)


def _write_json_durable(path: Path, data: dict) -> None:
    """Write one small JSON state file, flushed and fsynced before the rename.

    `last-restore.json` is the owner's only record of what a restore replaced
    once the process has restarted, so it must be on disk when this returns,
    not merely in the page cache. The temp file goes beside it (same folder,
    same volume, so the rename is atomic) and is removed if anything fails.

    FSYNC DECISION (audit 2026-10-21, NIT): the FILE is fsynced, the containing
    DIRECTORY is not. On this project's platform (Windows/NTFS) a rename is
    journaled, so the directory fsync POSIX would want is not needed here; and
    on POSIX a lost rename after a crash costs one restore notice (the code it
    could carry was never on disk anyway, `RECOVERY_CODE_HINT`), never data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


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
    # Counts and outcomes only: never a folder's path, never a recovery code,
    # and never the CONTENT of a file. THE ONE EXCEPTION (2026-10-20 ruling
    # 8.1, accepted; audit 2026-10-21 LOW-6): `backup.restored` carries the
    # exact NAMES of the files put back, because the owner asked for that
    # receipt - names are metadata, not the files' words.
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
        conn = sqlite3.connect(str(db_path), timeout=DB_BUSY_TIMEOUT_S)
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
        source = sqlite3.connect(str(src), timeout=DB_BUSY_TIMEOUT_S)
    except sqlite3.DatabaseError:
        return False
    try:
        target = sqlite3.connect(str(dest), timeout=DB_BUSY_TIMEOUT_S)
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

    Jarvis's OWN bookkeeping JSON files are refused here even when an archive
    carries them (an older backup, or a crafted one): `_own_settings_files`
    (audit 2026-10-21, M1) - restoring `last-restore.json` from a backup would
    report an OLD restore as the current one, and `backup.json` would silently
    change the backup folder from an archive. Compared CASEFOLDED: NTFS is
    case-insensitive, so `settings/Last-restore.json` would otherwise land on
    the real `last-restore.json` (audit addendum 2026-10-21, V1).
    """
    own = {name.casefold() for name in _own_settings_files()}
    out = []
    for name in names:
        if not name.startswith("settings/"):
            continue
        rest = name[len("settings/"):]
        if rest.casefold() in own:
            continue
        if rest.endswith(".json") or rest in SETTINGS_NAMES:
            out.append(name)
    return out


def build_archive() -> tuple:
    """(zip_bytes, manifest). The manifest is also written INSIDE the zip
    as manifest.json, so a restore preview can read counts and a date
    without touching anything else in the archive."""
    conf = _config_dir()
    manifest = {"created_at": time.time(), "databases": {}, "settings_files": 0,
                "notes_files": 0, "voice_files": 0,
                # Backup-Gap 1 (2026-10-23): the voice profile is NOT carried,
                # and the manifest says so in the owner's words. `voice_files`
                # stays as 0 for older readers.
                "voice_profile_backed_up": False,
                "voice_note": VOICE_REENROL_NOTE,
                "chat_history_key": False,
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
            own = {name.casefold() for name in _own_settings_files()}
            for jf in sorted(conf.glob("*.json")):
                if jf.name.casefold() in own:
                    # backup.json names only a folder - never useful inside
                    # itself; last-restore.json is the LAST restore's record -
                    # inside a backup it would ride into every later archive,
                    # be restored as if it were owner data, and could report an
                    # OLD restore as current (audit 2026-10-21, M1). Casefolded
                    # because NTFS is case-insensitive (V1 of the addendum).
                    continue
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
            # The voice enrolment folder is deliberately NOT walked (2026-10-23,
            # Backup-Gap 1): the files are sealed with a Windows Credential
            # Manager key on THIS PC, which a bare-metal restore does not have,
            # so they would come back as dead files the owner believes are
            # usable. The manifest carries the plain-words note instead, and
            # restore refuses to write any voice file it cannot open here.
            # Deliberately NOT walked: the guardian store (guardian/) and the
            # two other non-SQLite files in NOT_BACKED_UP_PATHS. This module
            # never recurses an arbitrary settings subfolder - the notes walk
            # above is the only recursive one left - so a 250 MiB blob store
            # cannot bloat an archive. The recorded reasons are the decision.
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
        # FLUSHED TO DISK BEFORE THE RENAME (Gemini ruling 8.1, 2026-10-20). The
        # restore's fail-closed check reads this file straight back and refuses
        # to touch live data unless it is whole; a write sitting in the page
        # cache would pass that read and then be lost in a crash between the
        # rename and the restore. The rename itself is the atomic step.
        try:
            with tmp.open("rb+") as fh:
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            # The write itself is already done and checked below by the caller;
            # a file system that refuses fsync (some network shares) must not
            # turn a usable backup into a crash here - but the restore's own
            # read-back verification is what decides whether it may proceed.
            pass
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
    # "could not be made OR VERIFIED" (audit 2026-10-21, LOW-6): the safety
    # backup may have been written and then failed its on-disk check, which is
    # not the same as never made - the sentence stays plain and true for both.
    "failed_before": "It was approved, but the safety backup could not be made or verified "
                     "first, so nothing was restored and your data was not changed.",
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


def _restored_names(applied) -> dict:
    """The EXACT filenames a restore put back, grouped by the archive's own
    folders (2026-10-20, Gemini ruling 8.1). Empty groups are left out.

    `_apply_restore` builds this; `_restore_finish` puts it in the audit record
    and in `last_restore`, so neither the owner's receipt nor a bug report has
    to guess from "1 database" which database it was."""
    out = {}
    restored = applied.get("restored") if isinstance(applied, dict) else None
    if not isinstance(restored, dict):
        return out
    for group in ("databases", "settings_files", "notes_files", "voice_files",
                  "source_files", "framework_toml", "keys"):
        names = [str(n) for n in (restored.get(group) or []) if n]
        if names:
            out[group] = sorted(names)
    return out


def _without_code(record: dict) -> dict:
    """The record as it may be written to disk: no recovery code anywhere."""
    safe = {k: v for k, v in record.items() if k != "recovery_code"}
    safety = safe.get("safety_backup")
    if isinstance(safety, dict):
        safe["safety_backup"] = {k: v for k, v in safety.items() if k != "recovery_code"}
    safe["recovery_code_hint"] = RECOVERY_CODE_HINT
    return safe


def _persist_restore_result(record: dict) -> bool:
    """Write the last restore's record to `last-restore.json`, WITHOUT the code.

    Returns True when the full record is on disk. Never raises: the restore has
    already happened (or its refusal is already in memory) when this is called,
    and a full disk must not turn a finished restore into an exception the
    card's thread drops. The one-time recovery code is stripped here - it was
    never on disk and this file must not be the first place it is - and a hint
    says where it was shown instead.

    A FAILED WRITE MUST NOT LEAVE THE OLDER RESTORE LOOKING CURRENT (audit
    2026-10-21, M3): the file still holds the PREVIOUS restore's record, which a
    restart would then report as the latest. So on failure this writes a short
    fallback record saying the full one could not be saved (and which outcome
    this run knew), and if even that cannot be written it removes the stale
    file - "no record" is honest, an older restore reported as current is not.
    """
    try:
        _write_json_durable(last_restore_path(), _without_code(record))
        return True
    except Exception:                                          # noqa: BLE001
        _audit("backup.restore.persist_failed", {"why": "could not write last-restore.json"})
    fallback = {"outcome": record.get("outcome") or "unknown",
                "persist_failed": True,
                "at": record.get("at") or time.time(),
                "message": PERSIST_FAILED_WORDS,
                "warning": "", "restored": {},
                "safety_backup": None,
                "recovery_code_hint": RECOVERY_CODE_HINT}
    try:
        _write_json_durable(last_restore_path(), fallback)
        _audit("backup.restore.persist_fallback", {"how": "marker"})
        return False
    except Exception:                                          # noqa: BLE001
        pass
    try:
        last_restore_path().unlink()
        _audit("backup.restore.persist_fallback", {"how": "removed stale"})
    except FileNotFoundError:
        _audit("backup.restore.persist_fallback", {"how": "none"})
    except OSError:
        # Nothing can be written and the old file cannot even be removed: the
        # reader may still see the older record, but the audit line above says
        # so and the in-memory record carries `persist_failed`.
        _audit("backup.restore.persist_fallback", {"how": "failed"})
    return False


def _load_restore_result() -> dict:
    """The persisted last restore, or {} when there is none (or it is damaged).

    Never raises and can never contain a recovery code: the file it reads has
    never had one (`_persist_restore_result` strips it). A file bigger than
    `MAX_RESTORE_RESULT_BYTES` is not one of ours (or is damaged) and is
    ignored instead of being read into memory unbounded."""
    try:
        path = last_restore_path()
        if path.stat().st_size > MAX_RESTORE_RESULT_BYTES:
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _restore_finish(pid: str, outcome: str, *, why: str = "", safety=None,
                    message: Optional[str] = None, warning: str = "",
                    applied=None, reason: str = "", partial: bool = False) -> None:
    record = {
        "outcome": outcome, "why": why, "at": time.time(),
        "message": (message if message is not None
                    else RESTORE_LAST_WORDS.get(outcome, "")),
        "safety_backup": safety, "warning": warning,
        # EXACT filenames, not counts (2026-10-20, ruling 8.1): "1 database" is
        # useless both in the owner's receipt and in a bug report. `applied` is
        # `_apply_restore`'s own dict; a failure before any write passes none,
        # and the record then says so by having no `restored` groups at all.
        # A partial failure passes the names it HAD replaced before it stopped
        # (audit 2026-10-21, LOW-2) with `partial` set, so the reader knows the
        # list is "what may now be the backup's", not "everything went in".
        "restored": _restored_names(applied),
    }
    if reason:
        record["reason"] = reason
    if partial:
        record["partial"] = True
    with _R_LOCK:
        if _R_STATE["pending"].get("id") == pid:
            _R_STATE["pending"].clear()
        _R_STATE["withdrawn"].discard(pid)
        if _R_STATE["latest"].get("id") not in (None, pid):
            return
        _R_STATE["last"].clear()
        _R_STATE["last"].update(record)
        # DURABLE, so a restart and any number of polls keep the outcome
        # (ruling 8.1); the record in memory additionally holds the one-time
        # code for exactly one read.
        #
        # THE DISK WRITE IS INSIDE THE LOCK (audit 2026-10-21, LOW-1): a dismiss
        # can then only run BEFORE the new record is visible or AFTER it is on
        # disk - never in the window between, where it would report success and
        # the write would put the record back. A dismiss that runs after this
        # release clears both copies; a dismiss that ran before it saw the old
        # state, which is the truth it acted on.
        persisted = _persist_restore_result(record)
        if not persisted:
            # The full record is not on disk. In memory the outcome is still
            # true, and the flag says the durable copy is the fallback marker
            # (or gone), so a reader never mistakes it for the full receipt.
            _R_STATE["last"]["persist_failed"] = True
    _audit("backup.restore.card", {"outcome": outcome, "reason": reason,
                                   "partial": bool(partial)})


def take_restore_result() -> Optional[dict]:
    """The last restore's outcome, WITH the safety backup's one-time recovery
    code if this process still holds it - the code is readable exactly once.

    Two things changed on 2026-10-20 (Gemini ruling 8.1), and only one of them
    relaxes:
      * the RECORD persists now. It is written to `last-restore.json` and is
        read here (and by both apps through GET /api/backup) until the owner
        dismisses it - a poll can no longer swallow the outcome;
      * the CODE keeps its old rule. The first read here hands it over and
        removes it from memory, and it was NEVER on disk, so a persisted file
        can never open the safety backup. The record says so in
        `recovery_code_hint`."""
    with _R_LOCK:
        last = dict(_R_STATE["last"])
        if last:
            safety = last.get("safety_backup")
            if isinstance(safety, dict) and "recovery_code" in safety:
                _R_STATE["last"]["safety_backup"] = {k: v for k, v in safety.items()
                                                     if k != "recovery_code"}
    if not last:
        last = _load_restore_result()
    return last or None


def restore_result_for_reader(*, here: bool) -> Optional[dict]:
    """What GET /api/backup's `last_restore` shows.

    `here` (this PC): the record, and once only the in-memory recovery code.
    Any other paired device: the persisted summary and NEVER the code - and
    reading it consumes nothing, so a phone poll cannot swallow the recovery
    information the owner still needs. (The technical `why` is left out of the
    phone's copy: it is for a bug report, and it is the one field that can name
    an engine-room cause.)"""
    if here:
        return take_restore_result()
    stored = _load_restore_result()
    if not stored:
        return None
    return {k: v for k, v in stored.items() if k != "why"}


def _code_unread_locked() -> bool:
    """Is the safety backup's one-time recovery code still held, unread?

    Called with `_R_LOCK` held. The code is the only copy anywhere - it was
    never written to disk - so clearing the record before the PC has read it
    would leave the safety backup permanently unopenable (audit 2026-10-21,
    M2)."""
    safety = _R_STATE["last"].get("safety_backup")
    return bool(isinstance(safety, dict) and safety.get("recovery_code"))


def recovery_code_pending() -> bool:
    """True while this process holds a safety-backup code no PC read has shown.

    Both app views carry it, so a dismiss button can say why a device's clear
    was refused; it reveals nothing (the record itself is already visible to a
    paired device)."""
    with _R_LOCK:
        return _code_unread_locked()


def dismiss_restore_result(*, remote: bool = False) -> tuple:
    """Clear the last restore's outcome everywhere.

    Returns `(cleared, refused)`: `cleared` is True when there was something to
    clear and it is gone; `refused` is "" normally, or the plain sentence a
    REMOTE caller is given when the PC has not yet shown this restore's
    one-time recovery code (`DISMISS_CODE_PENDING`). That refusal is the M2
    rule (audit 2026-10-21): the code exists only in this process's memory, so
    a device clearing the notice first would destroy the one way back to the
    safety backup. The PC itself never hits it - the owner is sitting there
    and can read the code in the same panel first.

    The ONLY thing that clears the record (ruling 8.1): a read never does. A
    notice that cannot be removed from disk is not reported as dismissed."""
    with _R_LOCK:
        if remote and _code_unread_locked():
            return False, DISMISS_CODE_PENDING
        had = last_restore_path().is_file() or bool(_R_STATE["last"])
        _R_STATE["last"].clear()
        try:
            last_restore_path().unlink()
        except FileNotFoundError:
            pass
        except OSError:
            _audit("backup.restore.dismiss_failed", {"remote": bool(remote)})
            return False, ""
    return had, ""


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
    too - some files may be the backup's and some the old ones).

    `applied` (audit 2026-10-21, LOW-2): the `_apply_restore` summary of what
    had really been put in place before the failure, so a PARTIAL restore can
    still name the files that may now be the backup's. None when nothing was
    written, or when everything was put back."""

    def __init__(self, message: str, state: str = "unchanged", applied=None):
        super().__init__(message)
        self.state = state
        self.applied = applied


class BackupRestoreRefusedError(ValueError):
    """A restore archive was refused before any live file was touched.

    Raised for an unsafe member (a name that would leave its own folder, a
    symbolic or hard link, an absolute or drive-qualified name, or a name
    outside the folders a backup may carry) and for a staged database that
    fails its SQLite header or its own quick_check/integrity_check. The
    message is plain words; the restore card never proceeds past it."""


#: The 16 bytes every real SQLite database starts with.
SQLITE_MAGIC_HEADER = b"SQLite format 3\x00"

#: The only top-level names a .jbak may carry. The five folders are the ones
#: `build_archive` writes; the two bare files are the framework's settings file
#: and the archive's own manifest.
_ARCHIVE_ALLOWED_EXACT = ("manifest.json", "jarvis-framework.toml")
_ARCHIVE_ALLOWED_PREFIXES = ("db/", "settings/", "notes/", "voice/",
                             SOURCE_PREFIX, "secrets/")


def _member_is_link(info: zipfile.ZipInfo) -> bool:
    """True for a ZipInfo whose Unix mode says it is a symbolic link.

    ZIP has no portable link flag; a zip made by a Unix tool puts the mode in
    the high 16 bits of `external_attr` (0o120000 there is a symlink). Jarvis's
    own archives never contain one, so a member that carries it is a crafted or
    foreign archive and is refused before anything is read."""
    try:
        mode = int(getattr(info, "external_attr", 0)) >> 16
    except (TypeError, ValueError):
        return False
    return stat.S_ISLNK(mode)


def validate_archive_member_path(
    member_name: str,
    *,
    is_symlink: bool = False,
    is_hardlink: bool = False,
) -> str:
    """The safe archive-relative name, or raise `BackupRestoreRefusedError`.

    One place for the archive-reader's path rules so they cannot drift: no
    link, no empty or NUL name, no absolute path, no drive letter or colon, no
    `.`/empty-segment trick, no `..` in any position, and nothing outside the
    six folders a backup carries. `is_hardlink` is here for a caller that knows
    a link's kind from another format; ZIP is always asked about symlinks.
    """
    if is_symlink or is_hardlink:
        raise BackupRestoreRefusedError(
            f"the backup contains a link ({member_name}); nothing on this PC was changed")
    if not isinstance(member_name, str) or not member_name or "\x00" in member_name:
        raise BackupRestoreRefusedError(
            "the backup contains a file with an empty or invalid name; "
            "nothing on this PC was changed")
    normalized = member_name.replace("\\", "/").strip()
    if normalized.startswith("/") or ":" in normalized:
        raise BackupRestoreRefusedError(
            f"the backup contains an absolute path ({member_name}); "
            "nothing on this PC was changed")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        raise BackupRestoreRefusedError(
            f"the backup contains a path that could escape its folder ({member_name}); "
            "nothing on this PC was changed")
    clean = "/".join(parts)
    if not (clean in _ARCHIVE_ALLOWED_EXACT
            or any(clean.startswith(prefix) for prefix in _ARCHIVE_ALLOWED_PREFIXES)):
        raise BackupRestoreRefusedError(
            f"the backup contains a file outside the backed-up folders ({clean}); "
            "nothing on this PC was changed")
    return clean


def _voice_file_usable(data) -> bool:
    """True only when THIS PC can actually open a voice file from an archive.

    The voice profile is sealed with a Windows Credential Manager key created on
    the PC that enrolled it; after a bare-metal restore that key is gone. A
    restore must not write such a file and count it as restored - the owner
    would believe their voice is back when it is dead. So each `voice/` member
    of an OLDER archive is opened in RAM here first (no write, no plaintext on
    disk); only an openable one is staged. Anything else is skipped and the
    restore says re-enrolment is needed. Never raises: an unreadable file is
    simply not usable."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, (bytes, bytearray))
                         else str(data))
    except Exception:
        return False
    try:
        import jarvis_voice
        if jarvis_voice.is_sealed_doc(doc):
            jarvis_voice.unseal_envelope(doc, what="the backup's voice file")
            return True
    except Exception:
        return False
    # A plain JSON voice file is not one this module writes; the sealed form is
    # the only production shape. Fail closed rather than restore an unsealed
    # print to disk (the #600 invariant).
    return False


def verify_staged_sqlite_db(db_path) -> tuple:
    """(True, "ok") or (False, plain why) for a staged database file.

    Read-only: the 16-byte header, then SQLite's own `quick_check` and
    `integrity_check`. The archive carries SQLite snapshots, so a live `-wal`
    holding rows never reaches here. Any failure is the plain reason the
    restore is refused, and the live file is never touched."""
    path = Path(db_path)
    try:
        if not path.is_file():
            return False, f"the backup's database {path.name} is missing after unpacking"
        size = path.stat().st_size
        if size < 100:
            return False, f"the backup's database {path.name} is cut short ({size} bytes)"
        with path.open("rb") as fh:
            header = fh.read(16)
        if header != SQLITE_MAGIC_HEADER:
            return False, f"the backup's database {path.name} is not a SQLite database"
        conn = None
        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True,
                                   timeout=10.0)
            quick = conn.execute("PRAGMA quick_check;").fetchall()
            if quick != [("ok",)]:
                return False, (f"the backup's database {path.name} did not pass its "
                               f"quick check")
            integ = conn.execute("PRAGMA integrity_check;").fetchall()
            if integ != [("ok",)]:
                return False, (f"the backup's database {path.name} did not pass its "
                               f"full integrity check")
        finally:
            if conn is not None:
                conn.close()
    except BackupRestoreRefusedError:
        raise
    except Exception as exc:
        return False, (f"the backup's database {path.name} could not be checked "
                       f"({type(exc).__name__})")
    return True, "ok"


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
               # Backup-Gap 1 (2026-10-23): an OLDER archive may still carry
               # sealed voice files. They are counted here only when they could
               # NOT be opened on this PC, and the note says re-enrol.
               "voice_files_skipped": 0, "voice_needs_re_enrolment": False,
               "voice_note": "",
               "skipped": 0, "chat_history_key_failed": False, "study_decks_key_failed": False,
               # The EXACT names behind those counts (2026-10-20, ruling 8.1).
               # Filled below and handed to the audit record and the receipt.
               "restored": {"databases": [], "settings_files": [], "notes_files": [],
                            "voice_files": [], "source_files": [], "framework_toml": [],
                            "keys": []}}
    plan: list = []              # (dest, data, is_database)
    key_data = None
    study_key_data = None
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # REFUSE an unsafe archive BEFORE a single byte is read or written
        # (Backup-Gap 2, 2026-10-23). The `_inside` guard below still runs per
        # destination, but this is the whole-archive gate: it also refuses a
        # symbolic link, an absolute or drive-qualified name, a `..` anywhere,
        # and any member outside the six folders a backup may carry. Raising
        # here has touched nothing, so every live file is exactly as it was.
        for info in zf.infolist():
            if info.filename.endswith("/"):
                continue
            validate_archive_member_path(info.filename,
                                         is_symlink=_member_is_link(info))
        # Read ONCE, outside the loop: the one list of what may land in the
        # settings folder (see `_named_settings_entries`), and the manifest's
        # own claim about the voice profile (Backup-Gap 1, 2026-10-23).
        allowed_settings = set(_named_settings_entries(zf.namelist()))
        archive_manifest: dict = {}
        try:
            if "manifest.json" in zf.namelist():
                archive_manifest = json.loads(zf.read("manifest.json") or b"{}")
        except Exception:
            archive_manifest = {}
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/") or name == "manifest.json":
                continue
            where = None
            #: The archive-relative name as the RECEIPT says it (2026-10-20,
            #: ruling 8.1): "db/memory.db" is shown as "memory.db" under the
            #: databases group, a nested note keeps its folders.
            shown = ""
            if name.startswith("db/"):
                shown = name[len("db/"):]
                where = ("databases", _inside(conf, shown, flat=True))
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
                shown = name[len("settings/"):]
                where = ("settings_files", _inside(conf, shown, flat=True))
            elif name.startswith("notes/"):
                shown = name[len("notes/"):]
                where = ("notes_files", _inside(conf / "notes", shown))
            elif name.startswith("voice/"):
                # Backup-Gap 1 (2026-10-23): an OLDER archive may still carry
                # sealed voice files. Open each one in RAM first; only a file
                # this PC can really use is staged. An unopenable one is never
                # written (it would be dead data counted as restored) - it is
                # skipped and the outcome says re-enrolment is needed.
                shown = name[len("voice/"):]
                dest = _inside(conf / "voice", shown)
                voice_data = zf.read(info)
                if dest is None or not _voice_file_usable(voice_data):
                    applied["voice_files_skipped"] += 1
                    applied["voice_needs_re_enrolment"] = True
                    applied["skipped"] += 1
                    continue
                plan.append((dest, voice_data, False, "voice_files", shown))
                applied["voice_files"] += 1
                continue
            elif name.startswith(SOURCE_PREFIX):
                # The backend's own program files go back into the folder this
                # module runs from (2026-10-05) - `_source_dir()`, read HERE and
                # not before the chain, so an archive with no `source/` entry
                # (every backup made before this change) never even asks where
                # the sources live. `flat=True`: build_archive writes one name
                # per file, so a nested name is a tampered archive, not a
                # layout to honour - `_inside` refuses it and it is counted
                # under "skipped" like any other bad name.
                shown = name[len(SOURCE_PREFIX):]
                where = ("source_files", _inside(_source_dir(), shown, flat=True))
            if where is not None and where[1] is None:
                applied["skipped"] += 1
                continue
            data = zf.read(info)
            if where is not None:
                plan.append((where[1], data, where[0] == "databases", where[0], shown))
                applied[where[0]] += 1
            elif name == "jarvis-framework.toml":
                toml_dest = _toml_source()
                plan.append((toml_dest if toml_dest is not None else (conf / name),
                             data, False, "framework_toml", name))
                applied["framework_toml"] = True
            elif name == "secrets/chat-history-key.b64":
                key_data = data
            elif name == "secrets/study-decks-key.b64":
                study_key_data = data
    tag = uuid.uuid4().hex[:8]
    staged: list = []            # (dest, temp, is_database, group, shown name)
    swapped: list = []           # (dest, copy of the old file or None)
    aside: list = []             # (path, where it was moved to) - wal/shm
    #: group -> the names really replaced (a swap that succeeded). Built while
    #: swapping, not while planning: a PARTIAL failure must not claim a file it
    #: never got to (audit 2026-10-21, LOW-2).
    done: dict = {}
    for group in applied["restored"]:
        done[group] = []
    try:
        for dest, data, is_db, group, shown in plan:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / f".{dest.name}.{tag}.tmp"
            # listed first: cleaned up even if half-written
            staged.append((dest, tmp, is_db, group, shown))
            tmp.write_bytes(data)
    except BaseException as exc:
        _remove_all([t for _d, t, _i, _g, _s in staged])
        raise RestoreError(f"could not prepare the files ({type(exc).__name__})") from exc
    # VERIFY the staged databases BEFORE the first live file is replaced
    # (Backup-Gap 2, 2026-10-23): a cut-short or corrupted .db must refuse the
    # whole restore while every live database is still the old one. The check
    # reads the temp file only; nothing live has been touched yet.
    bad = []
    for _dest, tmp, is_db, _group, _shown in staged:
        if is_db:
            ok, why = verify_staged_sqlite_db(tmp)
            if not ok:
                bad.append(why)
    if bad:
        _remove_all([t for _d, t, _i, _g, _s in staged])
        raise BackupRestoreRefusedError(
            "the backup was refused, and nothing on this PC was changed: "
            + "; ".join(bad[:3]) + ".")
    try:
        for dest, tmp, is_db, group, shown in staged:
            old = None
            if dest.exists():
                old = dest.parent / f".{dest.name}.{tag}.old"
                shutil.copyfile(dest, old)
            swapped.append((dest, old))
            os.replace(tmp, dest)
            if shown:
                done[group].append(shown)
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
        _remove_all([t for _d, t, _i, _g, _s in staged])
        # When putting back failed too, the names replaced before the stop are
        # exactly what may now be the backup's - handed to the record.
        applied["restored"].update({g: sorted(v) for g, v in done.items()})
        raise RestoreError(f"could not replace a file ({type(exc).__name__})",
                           "partial" if problems else "unchanged",
                           applied=applied if problems else None) from exc
    _remove_all([old for _d, old in swapped if old] + [m for _p, m in aside])
    if key_data is not None:
        try:
            import jarvis_token_store as ts
            import jarvis_chat_log
            ts.WindowsStore(target=jarvis_chat_log.KEY_TARGET).write(key_data.decode("ascii"))
            applied["chat_history_key"] = True
            applied["restored"]["keys"].append("chat-history-key")
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
            applied["restored"]["keys"].append("study-decks-key")
            jarvis_decks.forget_key()   # the running store must reopen with this key
        except Exception:
            applied["study_decks_key_failed"] = True
    for group, names in done.items():
        applied["restored"][group] = sorted(names)
    applied["restored"]["keys"] = sorted(applied["restored"]["keys"])
    # Backup-Gap 1 (2026-10-23): say plainly what happened to the voice
    # profile. A NEW archive says it was never carried; an OLDER one that
    # carried sealed files this PC could not open says re-enrolment is needed.
    if archive_manifest.get("voice_profile_backed_up") is False:
        note = str(archive_manifest.get("voice_note") or VOICE_REENROL_NOTE).strip()
        if note:
            applied["voice_note"] = note
    elif applied["voice_needs_re_enrolment"]:
        applied["voice_note"] = VOICE_REENROL_NOTE
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


class SafetyBackupUnverified(Exception):
    """The safety backup made just before a restore is not on disk as a whole,
    verifiable backup. A restore NEVER proceeds past this (Gemini ruling 8.1,
    2026-10-20, accepted by the owner).

    Audit 2026-10-21 (NIT): `backup_now` never raises this, so with the real
    safety backup the refusal is the `_verify_safety_backup` return below; the
    class stays for a caller that supplies its own `safety_fn` and wants to
    refuse in the same words. No branch here depends on it alone: an
    unexpected exception from a caller's safety_fn is caught by the same
    plain-words refusal."""


def _verify_safety_backup(safety, folder) -> str:
    """'' when the safety backup on disk is verifiably whole, else why not.

    FAIL-CLOSED, CHECKED BEFORE ANY LIVE FILE IS TOUCHED. Presence alone is not
    enough - a crash, a full disk or a synchronising program can leave an empty,
    cut-short or not-ours file with the right name, and a restore that trusts
    it destroys the only copy of the "before" state. So the checks are, in
    order: the record itself; a plain filename inside the backup folder; the
    file's own JBAK1 header and minimum shape (`check_file`); its size is the
    size that was written; it OPENS with the code it was written with; and its
    manifest reads back whole. Any failure is a plain reason, and nothing is
    restored.

    The recovery code is used here (in memory) and is still never written to
    disk. `folder` is the backup folder from the settings the restore was
    started against; None means the folder went away, which is also a refusal."""
    if not isinstance(safety, dict):
        return "no safety backup was recorded"
    name = safety.get("name")
    code = safety.get("recovery_code")
    if not isinstance(name, str) or not name:
        return "the safety backup has no file name"
    if not isinstance(code, str) or not code:
        return "the safety backup has no recovery code to verify it with"
    if not folder:
        return "the backup folder is not set, so the safety backup cannot be found"
    path = _inside(Path(folder), name, flat=True)
    if path is None:
        return "the safety backup's name is not a plain file name in the backup folder"
    shape = check_file(path)
    if not shape.get("ok"):
        return f"the safety backup is not on disk as a whole backup ({shape.get('why')})"
    size = int(shape.get("size") or 0)
    if size <= 0:
        return "the safety backup file is empty"
    claimed = safety.get("size")
    if isinstance(claimed, int) and not isinstance(claimed, bool) and claimed != size:
        return f"the safety backup is {size} bytes, not the {claimed} just written"
    try:
        zip_bytes = decrypt_blob(path.read_bytes(), code)
    except WrongCode:
        return "the safety backup will not open with the code it was written with"
    except (OSError, BackupUnavailable) as exc:
        return f"the safety backup could not be read back ({type(exc).__name__})"
    try:
        manifest = _read_manifest(zip_bytes)
    except Exception as exc:                                   # noqa: BLE001
        return f"the safety backup's manifest could not be read back ({type(exc).__name__})"
    if not isinstance(manifest, dict) or not manifest.get("created_at"):
        return "the safety backup's manifest could not be read back"
    return ""


def _discard_unverified_safety(safety, folder) -> str:
    """Remove a safety backup that FAILED verification; name it if it stays.

    Audit 2026-10-21 (LOW-4): such a file's one-time code was never shown, so
    nobody can ever open it - left on disk it is an unopenable orphan that
    still counts as one of the KEEP backups. Best effort: when it cannot be
    removed the returned sentence names it so the refusal record says so.
    """
    if not isinstance(safety, dict) or not folder:
        return ""
    name = safety.get("name")
    if not isinstance(name, str) or not name:
        return ""
    path = _inside(Path(folder), name, flat=True)
    if path is None:
        return ""
    try:
        path.unlink()
    except FileNotFoundError:
        _audit("backup.restore.safety_orphan", {"removed": True})
        return ""
    except OSError:
        _audit("backup.restore.safety_orphan", {"removed": False})
        return (f"A safety backup was written but failed verification and could not be "
                f"removed (\"{name}\"); it cannot be opened because its one-time code was "
                f"never shown, so it should be deleted from the backup folder by hand.")
    _audit("backup.restore.safety_orphan", {"removed": True})
    return ""


def _safety_after_restore_problem(safety, folder) -> str:
    """A cheap post-apply re-check of the safety backup: "" when it is there.

    Audit 2026-10-21 (LOW-5): the file was verified BEFORE the apply, and the
    apply can take a while - a sync client or a cleaning program can remove or
    replace it meanwhile, which would make the record's "the safety backup
    made just before it is still there" false. This checks presence and size
    only (never decrypts again); the caller reports what it finds honestly.
    """
    if not isinstance(safety, dict) or not folder:
        return ""
    name = safety.get("name")
    if not isinstance(name, str) or not name:
        return ""
    path = _inside(Path(folder), name, flat=True)
    if path is None or not path.is_file():
        return "the safety backup is no longer in the backup folder"
    try:
        size = path.stat().st_size
    except OSError:
        return "the safety backup could not be read after the restore"
    claimed = safety.get("size")
    if isinstance(claimed, int) and not isinstance(claimed, bool) and claimed != size:
        return (f"the safety backup changed size after the restore "
                f"({size} bytes now, {claimed} when written)")
    return ""


def _decide_restore(pid: str, name: str, code: str, manifest: dict, zip_bytes: bytes,
                    gate: Callable, tier_of: Callable, apply_fn: Callable,
                    safety_fn: Callable, folder: Optional[str] = None) -> None:
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
        except SafetyBackupUnverified as exc:
            return _restore_finish(pid, "failed",
                                   why=f"the safety backup was not verified ({exc})",
                                   message=RESTORE_LAST_WORDS["failed_before"],
                                   reason=SAFETY_UNVERIFIED)
        except Exception as exc:
            return _restore_finish(pid, "failed", why=f"the safety backup failed "
                                                       f"({type(exc).__name__})",
                                   message=RESTORE_LAST_WORDS["failed_before"])
        # FAIL CLOSED (Gemini ruling 8.1, 2026-10-20, accepted): the safety
        # backup must be provably ON DISK and whole BEFORE one live file is
        # touched. The write above only tells us it thinks it wrote something;
        # this reads the bytes back. Anything but a clean '' refuses the
        # restore with nothing changed, records why in the audit, and keeps the
        # outcome visible to the owner (persisted, ruling 8.1 part 2).
        #
        # AN UNEXPECTED EXCEPTION IN THE CHECK IS A REFUSAL, NOT A DEAD CARD
        # (audit 2026-10-21, LOW-3): before this, a raise from inside the
        # verifier escaped this thread before _restore_finish, leaving the
        # restore card "waiting" for ever and every later restore a 409.
        try:
            problem = _verify_safety_backup(safety, folder)
        except Exception as exc:                               # noqa: BLE001
            problem = f"the safety backup could not be checked ({type(exc).__name__})"
        if problem:
            orphan_left = _discard_unverified_safety(safety, folder)
            return _restore_finish(
                pid, "failed",
                why=f"nothing was restored: the safety backup could not be verified "
                    f"before the restore ({problem})",
                message=RESTORE_LAST_WORDS["failed_before"],
                reason=SAFETY_UNVERIFIED, warning=orphan_left or "")
        safety_out = {"name": safety["name"], "at": safety["at"],
                      "recovery_code": safety["recovery_code"],
                      # Kept so the post-apply re-check can compare the size
                      # it was written with (LOW-5); the persisted copy carries
                      # it too (no code, of course).
                      "size": safety.get("size")}
        try:
            applied = apply_fn(zip_bytes)
        except Exception as exc:
            # "Your data was not changed" is only said when that is true.
            partial = getattr(exc, "state", "unchanged") == "partial"
            return _restore_finish(
                pid, "failed", why=type(exc).__name__, safety=safety_out,
                message=RESTORE_LAST_WORDS["failed_partial" if partial else "failed"],
                # A partial failure still names what it had replaced before it
                # stopped (audit 2026-10-21, LOW-2).
                applied=getattr(exc, "applied", None), partial=partial)
    _audit("backup.restored", {"applied": applied})
    key_failed = bool(isinstance(applied, dict) and applied.get("chat_history_key_failed"))
    # POST-APPLY RE-CHECK (audit 2026-10-21, LOW-5): the safety backup was
    # verified before the apply; say plainly if it is not there any more.
    lost = _safety_after_restore_problem(safety_out, folder)
    warning = KEY_WARNING if key_failed else ""
    message = RESTORE_LAST_WORDS["restored"] + (" " + KEY_WARNING if key_failed else "")
    if lost:
        _audit("backup.restore.safety_lost", {"why": lost})
        warning = (warning + " " + SAFETY_LOST_WARNING).strip()
        message = message + " " + SAFETY_LOST_WARNING
    _restore_finish(pid, "restored", safety=safety_out, warning=warning,
                    applied=applied, message=message)


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
                                      gate, tier_of, apply_fn, safety_fn,
                                      folder=st["folder"]))
    except Exception:
        with _R_LOCK:
            _R_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "message": "Waiting for your approval, with "
                                                          "Windows Hello. Nothing changes "
                                                          "unless you approve."}


def request_dismiss_restore(body=None, *, peer=None, local=None,
                            here: Optional[bool] = None) -> tuple:
    """POST /api/backup/restore/dismiss {"": nothing needed}. (code, body).

    The ONLY way the last restore's outcome is cleared (Gemini ruling 8.1,
    2026-10-20). Any paired device may ask - EXCEPT while this PC has not yet
    shown the restore's one-time recovery code: the code exists only in the
    PC's memory, so a device clearing the notice first would destroy the only
    way to open the safety backup (audit 2026-10-21, M2). That request is
    refused with **409** `{"ok": false, "code_pending": true, "error": ...}`
    and nothing is cleared; the PC itself may always clear it (the owner can
    read the code in the same panel first), and once the PC has read it any
    paired device can. The restore itself stays THIS PC ONLY
    (`request_restore`). Reading is never what clears it, so a phone poll can
    no longer swallow the outcome or the recovery hint.

    200 {"ok": True, "dismissed": <true when there was something to clear>}.
    Idempotent: dismissing an already-empty record is a 200, not an error."""
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    had, refused = dismiss_restore_result(remote=not is_here)
    if refused:
        _audit("backup.restore.dismiss_refused", {"why": "code_pending",
                                                  "from": "device"})
        return 409, {"ok": False, "code_pending": True, "error": refused}
    _audit("backup.restore.dismissed", {"had": had, "from": "pc" if is_here else "device"})
    return 200, {"ok": True, "dismissed": had}


# ---------------------------------------------------------------------------
#   GET /api/backup
# ---------------------------------------------------------------------------


def view(*, here: bool = False) -> dict:
    """GET /api/backup. From this PC: the folder, whether a card is
    waiting, how the last folder-card and the last backup/restore went, and
    the retention count. From anywhere else (the phone): whether a backup has
    ever been made and when the last one was, plus the LAST RESTORE's outcome
    - read-only, with no recovery code and no `why` - so both apps can show
    it. From 2026-10-20 (ruling 8.1) that outcome is PERSISTED and reading it
    never consumes it; only `POST /api/backup/restore/dismiss` clears it, and
    from a paired device only after this PC has shown the one-time code
    (`recovery_code_pending` says whether that is still owed - audit
    2026-10-21, M2)."""
    with _B_LOCK:
        last_backup = dict(_B_STATE["last"]) if _B_STATE["last"] else None
    if not here:
        return {"available": True,
                "last_backup_at": last_backup["at"] if last_backup else None,
                "last_restore": restore_result_for_reader(here=False),
                "recovery_code_pending": recovery_code_pending()}
    st = _load_settings()
    with _F_LOCK:
        pending = dict(_F_STATE["pending"]) if _F_STATE["pending"] else None
        last_folder_card = dict(_F_STATE["last"]) if _F_STATE["last"] else None
    with _R_LOCK:
        restore_pending = dict(_R_STATE["pending"]) if _R_STATE["pending"] else None
    # `restore_result_for_reader`/`take_restore_result` take _R_LOCK themselves
    # - called after releasing it above, never from inside it (that would
    # deadlock: _R_LOCK is a plain Lock, not reentrant).
    last_restore = restore_result_for_reader(here=True)
    with _D_LOCK:
        delete_pending = dict(_D_STATE["pending"]) if _D_STATE["pending"] else None
    last_delete = take_delete_older_result()
    return {"available": True, "folder": st["folder"], "keep": KEEP,
           "pending_delete_older_card": delete_pending, "last_delete_older": last_delete,
           "last_backup": last_backup, "pending_folder_card": pending,
           "last_folder_card": last_folder_card, "pending_restore_card": restore_pending,
           "last_restore": last_restore, "recovery_code_pending": recovery_code_pending(),
           "erase_limit": ERASE_LIMIT}


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
    if route == DISMISS_ROUTE:
        return request_dismiss_restore(body, peer=peer, local=local, here=here)
    if route == DELETE_ROUTE:
        return request_delete_older(body, peer=peer, local=local, here=here)
    return 404, {"ok": False, "error": "not found"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the ten routes above are
    answered here, after the server's own origin and token checks; every
    other request goes straight to the original - the same shape as
    jarvis_documents.py's `install`."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_backup", False):
        _ARMED = True
        return ("  backups    /api/backup, folder, now, list, status, prepare, commit, "
                "restore, dismiss (already on)")

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
                         PREVIEW_ROUTE, RESTORE_ROUTE, DISMISS_ROUTE, DELETE_ROUTE):
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
    return ("  backups    /api/backup, folder, now, list, status, prepare, commit, "
            "restore, dismiss")


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
    try:
        last_restore_path().unlink()
    except OSError:
        pass


if __name__ == "__main__":
    print(f"  config dir  {_config_dir()}")
    print(f"  settings    {_load_settings()}")
    print(f"  crypto      {'ready' if AESGCM is not None and Argon2id is not None else NO_CRYPTO}")
