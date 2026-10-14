# Your Jarvis data, and the copy that now exists

Written 2026-10-13, the day the copy was built. Every number here was measured
on the owner's PC, not estimated.

## What was at stake

Your personal data lives in `C:\Users\pcadmin\.openjarvis\`: **19 SQLite
databases, your settings file, and your voice-print**, 1.26 MB of things that
cannot be re-made. Beside it sit 1.14 GB of `voice-models`, which can be
downloaded again, and a 64 MB model cache, which also can - those are not the
data and are not backed up.

Windows' File History has no backup target set. The `Backup` tasks in Task
Scheduler (`\Microsoft\Windows\AppListBackup\Backup`,
`\Microsoft\Windows\CloudRestore\Backup`) are empty Windows placeholders that
have never run. And the code backups (`_jarvis-backup-*`,
`_jarvis-full-backup-*`) are copies of the **program**, not of your data.

## What a plain file copy loses - measured

There was one attempt at a copy:
`C:\Users\pcadmin\jarvis-data-backups\jarvis-data-2026-10-13-223631`. It was
made with a plain file copy, and comparing it with a real SQLite snapshot of
the same minute shows what that costs:

| database | the plain copy | a real snapshot |
|---|---|---|
| `agents.db` | **0 tables** | **6 tables** |
| `traces.db` | **missing entirely** | 7 tables, 9 rows |
| `telemetry.db` | **missing entirely** | 2 tables, 1 row |
| `digest.db` | **missing entirely** | 1 table |
| the other 15 | same as live | same as live |

**16 tables and 10 rows were lost, and 3 databases were missing outright.**

The `agents.db` row is the interesting one, and it is not a fluke. That file is
4,096 bytes, but the file beside it, `agents.db-wal`, is **115,392 bytes**. A
SQLite database keeps recent writes in a *write-ahead log* (the `-wal` file)
and folds them back into the main file later. A plain copy takes the main file
and leaves the log behind - so it took an empty shell, and the entire database,
schema included, stayed behind in the log. `traces.db` (78,312-byte log) and
`telemetry.db` (28,872-byte log) are the same shape.

The older copy is **left where it is**: something beats nothing. But it is not
a snapshot, and it cannot be verified.

## What already existed, and why this is not a duplicate of it

This is said first because the brief it was built from believed no backup
existed at all, and that is not quite true.

`backend/jarvis_backup.py` is a real, working, encrypted backup feature and you
have used it: **four `.jbak` files** sit in
`C:\Users\pcadmin\Documents\Jarvis Backups`, the newest from **2026-10-10
09:49**. Three of the four were made within twenty seconds of each other, and
nothing has run since.

That feature cannot be put on a timer, and this is the whole reason the tool
below exists. It makes a **fresh recovery code for every backup**, shows it
once, and never writes it anywhere - its own source says "NEVER written to a
file, a log, or the audit trail". A weekly run would therefore produce a locked
file that **nobody could ever open**, which is worse than no backup at all,
because it looks like one.

It also does not cover everything. Its list of databases names 12 of the 19;
`knowledge.db`, `agents.db`, `audit.db`, `sync_state.db`, `telemetry.db`,
`traces.db` and `digest.db` are not on it, `approvals.db` (51 rows) is left out
on purpose, its `*.json` rule does not match `speed.jsonl`, and its only
settings file is `jarvis-framework.toml`, which lives in the program folder -
so **`~/.openjarvis/config.toml`, Jarvis's own settings, is in no backup of any
kind.**

So the two sit side by side, doing different jobs:

| | `jarvis_backup.py` | `jarvis_data_backup.py` (this) |
|---|---|---|
| when it runs | when you press the button | weekly, by itself |
| what it holds | data **and** the program's own source | your personal data only |
| locked? | yes, AES-256-GCM, code shown once | no, unless you ask for `--seal` |
| how many kept | 5 | 4 |
| can it be scheduled? | no - the code would be lost | yes, that is what it is for |

Neither one replaces the other. If you want one thing to do, keep pressing the
button for the locked, code-protected archive, and let the weekly job be the
safety net that runs whether or not you remember.

## How a snapshot is taken, and why that is safe while Jarvis is running

**Nothing is ever copied with `Copy-Item`.** SQLite is asked to copy itself:

1. Each database is opened **read-only**, with a 30-second busy timeout - so a
   database another process is writing to settles instead of failing, and a bug
   in the tool cannot write to your live data even in principle.
2. **`VACUUM INTO`** writes a fresh, compacted, single-file copy. SQLite reads
   one consistent view of the database and folds the write-ahead log into the
   result, so a database caught mid-write still produces a file that opens.
   Measured with Jarvis running: **all 19 databases, `PRAGMA integrity_check`
   "ok" for every one, row counts identical to the live source.**
3. If `VACUUM INTO` refuses (an old SQLite, or a lock that will not clear), the
   same connection falls back to SQLite's **online backup API** - the equivalent
   primitive, and the one the app's own backup feature uses.
4. The `-wal`, `-shm` and `-journal` files are **never copied**. They are
   already inside the snapshot, and a stale log landing beside a fresh database
   is a way to corrupt a restore, not to complete one.
5. Everything that is not a database is copied plainly: `config.toml`,
   `speed.jsonl`, every other file at the top level, and the small folders -
   including `voice/`, which holds your voice-print enrolments.

**Jarvis is never stopped, and is not asked to stop.** The snapshot cannot be
made inconsistent by a running Jarvis, and Jarvis cannot be damaged by the
snapshot: after the copy, the suite that proves this writes another row to the
same live database and confirms it still commits.

## Nothing is trusted: every snapshot is verified

After the copy, every database is **opened again** and checked:

* it opens at all, and `PRAGMA integrity_check` says `ok`;
* its set of tables is the same set the live database had - this is what
  catches the `agents.db` failure above, and nothing else does;
* no table holds fewer rows than the live database did.

A snapshot that fails any of that is retried once against a fresh reading of
the live database, and if it still fails it is kept as
`<name>-INCOMPLETE` so it can be looked at, **never counted as one of your
backups**, and reported as a failure. `last-run.txt` in the backup folder says
what the last run did, which is how an unattended run is told apart from a dead
one.

## The commands

**Back up now - one line, paste it into a terminal:**

```powershell
python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py"
```

The last line it prints says where the snapshot landed - the folder you chose in
Settings, Backups (`C:\Users\pcadmin\Documents\Jarvis Backups` on this PC), or
`C:\Users\pcadmin\jarvis-data-snapshots` if you have never chosen one.

| what you want | one line |
|---|---|
| back up now | `python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py"` |
| what exists, and when the next run is | `python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py" status` |
| is this snapshot good? | `python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py" verify` |
| put one back, into a spare folder | `python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py" restore --to-temp` |
| set it up on another PC | `python "<a checkout>\tools\jarvis_data_backup.py" install --register-task` |

## The weekly timer

One Windows task, named **`Jarvis Personal Data Backup`**:

* **weekly, Sunday 03:00**; next run, as Windows reports it:
  **10/18/2026 3:00:00 AM**;
* it runs **`pythonw.exe`**, which has no console - **no window ever flashes on
  your screen**. The record of each run is written to `last-run.txt` in the
  backup folder instead;
* **per-user and no administrator**: it runs as `pcadmin`, registering it
  needed no elevation, and no password is stored anywhere. The cost of that,
  said plainly: it runs while you are signed in. It is the same shape as the
  two `Jarvis Ollama` tasks already on your PC;
* **`StartWhenAvailable` is set**, which matters more than it looks. At 03:00
  your PC may well be asleep. Without that setting a missed run is simply
  missed, and a backup that never happens is the one failure worse than a late
  one;
* it points at `%LOCALAPPDATA%\JarvisDataBackup\jarvis_data_backup.py`, **not**
  at a folder in this repository. The repository is worked in many parallel
  checkouts on different branches, and a backup that stops happening because a
  branch changed is not a backup.

**Verified end to end**: the task was started through Task Scheduler itself,
and it finished with **Last Result 0** and a verified snapshot of 19 databases
and 607 rows in `jarvis-data-snapshots`. (That was 2026-10-13, before the
destination became the folder you choose - see "Where it lands" below for where
the runs go now and what the task has to be refreshed to.)

## What is kept, and for how long

**The newest 4**, and older ones are deleted as new ones arrive. Weekly, that
is about a month of history: enough to walk back a bad write noticed a
fortnight later, and few enough that this cannot pile up the way the code
backups did (23 of those had to be pruned by hand on 2026-10-13).

Retention only ever deletes things this tool made, named `jarvis-snap-*`.
Your `.jbak` files and the older plain copy are not touched by it - the test
suite proves that by putting both in the folder and keeping six snapshots
beside them.

## Putting it back, and the test that was actually run

A backup nobody can restore is not a backup, so the restore path was driven for
real. Each snapshot was restored **into a spare folder** - never over
`~/.openjarvis`, which the tool refuses in code:

```
$ ... restore --to-temp
Restored into C:\Users\pcadmin\AppData\Local\Temp\jarvis-restore-...
  agents.db                  0 rows in 6 tables
  approvals.db              51 rows in 4 tables
  arbiter.db                 1 rows in 2 tables
  audit.db                   0 rows in 1 tables
  chat-history.db          223 rows in 4 tables
  digest.db                  0 rows in 1 tables
  feedback.db              101 rows in 4 tables
  goals.db                   0 rows in 1 tables
  jobs.db                    0 rows in 2 tables
  knowledge.db               3 rows in 6 tables
  ledger.db                  0 rows in 3 tables
  memory.db                 22 rows in 23 tables
  projects.db                0 rows in 4 tables
  schedule.db              196 rows in 3 tables
  sync_state.db              0 rows in 1 tables
  tasks.db                   0 rows in 6 tables
  telemetry.db               1 rows in 2 tables
  traces.db                  9 rows in 7 tables
  watch.db                   0 rows in 3 tables
  607 rows in total
```

Every database opened, every count matched its manifest, and `agents.db`
arrived with **6 tables** where the plain copy had none. `restore` writes a
short `README.txt` beside the restored data saying how to put it back, because
whoever needs that file will be reading it at the worst possible moment.

## Where it lands - one destination, and you pick it (2026-10-14)

**`folder` in `C:\Users\pcadmin\.openjarvis\backup.json` is the one setting.**
It is the key the locked `.jbak` backups have used since 2026-09-27, and this
tool now reads the same key, at run time, so both halves of Jarvis put their
backups in the same place - the folder **you** chose, not two folders that
disagree.

**What you click:** Jarvis Desktop → Settings → **Backups** → **"Choose a
folder…"**. That opens Windows' own "Select folder" dialog (the same one
"Folders Jarvis may look in" uses), shows the folder's full path back to you,
and raises one approval card on the PC. Until this change this tool ignored that
setting and wrote to `C:\Users\pcadmin\jarvis-data-snapshots` instead.

**Read fresh every run.** The weekly task is registered once and runs for years,
and its command line names no folder at all: it asks `backup.json` each time, so
changing the folder changes where the *next* snapshot lands. `--dest <folder>`
overrides it for a single hand-run. If you have never chosen one, you get
`C:\Users\pcadmin\jarvis-data-snapshots`, which is where the first snapshots
went - a default, not a decision.

**What is checked before a folder is accepted.** The app refuses, in the panel
and before any card is raised:

| rule | what you see |
|---|---|
| it must be a folder that is there | "…is not there any more. Choose the folder again." |
| Jarvis must be able to write into it | one empty probe file, created and deleted at once; "Jarvis cannot write into…" if it is refused |
| never inside `C:\Users\pcadmin\.openjarvis` | "…is inside Jarvis's own data folder - the very thing being backed up. A backup kept inside what it is backing up is not a backup…" |
| never inside a program folder | "…is inside <folder>, where Jarvis's own program lives. A backup kept there is lost with the program…" |
| another drive | not a refusal: a question naming the drive, asked before anything is sent |

The weekly tool applies the same rules and says the same things in its own
words, because it is the half that runs with no window on the screen.

**The one caveat, said plainly.** The `.jbak` files are encrypted before they
are written, so a cloud-synced folder (NordLocker, OneDrive) is fine for *them*.
These snapshots are **plain files** unless you seal them with `--seal`, so if the
folder you pick is one a sync program uploads, your memory and chat history go
up with it. The Backups panel says so in those words now, next to the picker -
it is your decision to make with the folder in front of you, not something this
tool decides for you by writing somewhere else.

### What happens to the backups that are already there

Nothing is moved, nothing is deleted and nothing is silently ignored.

- **Your four `.jbak` files** (`jarvis-backup-20261010-*.jbak`) are already in
  `C:\Users\pcadmin\Documents\Jarvis Backups`, which is the folder you chose.
  They stay exactly where they are, and the weekly run now writes beside them.
  The two retentions cannot eat each other: this tool only ever deletes entries
  named `jarvis-snap-*`, and the app's own retention only ever deletes files
  named `jarvis-backup-*`. Whichever folder holds both, each leaves the other
  alone.
- **The snapshots already in `C:\Users\pcadmin\jarvis-data-snapshots`** stay
  there too. Retention only ever looks in the folder the run itself is writing
  to, so a destination change cannot delete them - and to make sure they are not
  simply forgotten, every run and `status` now print a line naming that folder
  and how many snapshots are still in it. They are older backups of real data;
  they are kept.
- **Nothing was moved automatically**, on purpose: moving somebody's backups
  without asking is how a backup ends up half in one place, and a copy is not
  free on a disk that may be full. If you want them together, delete the old
  folder's contents by hand once you are satisfied the new runs are landing.

**One step is still yours to do on the PC.** The weekly task points at the
installed copy, `%LOCALAPPDATA%\JarvisDataBackup\jarvis_data_backup.py`, which
is the old build until it is refreshed. After this change lands:

```powershell
python "<a checkout>\tools\jarvis_data_backup.py" install --register-task
```

That copies the new tool into place and re-registers the same weekly task, which
then follows the folder above. `status` prints where snapshots go now and where
the task will run from, so you can check rather than trust.

## Encryption - the half that is safe to decide

Encrypting the **live** files is your decision and it has not been made, so
this tool does not touch, encrypt or move them. The archive, however, can be
protected, and that is built:

```powershell
$env:JARVIS_BACKUP_PASSPHRASE="something only you know"; python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py" --seal
```

That writes **one file**, `jarvis-snap-<date>.jba`, instead of a folder: a zip
of the snapshot sealed with AES-256-GCM under a key stretched from your
passphrase by Argon2id. Measured on your real data: one **660,588-byte** file
holding all 19 databases and 607 rows, with no readable folder beside it. With
no passphrase it refuses in plain words; with the wrong one it refuses in plain
words.

**What is on your PC, checked rather than assumed:** `cryptography` 50.0.2 is
installed and its Argon2id works, so this needs nothing downloaded. There is
**no** 7-Zip, GnuPG, OpenSSL, `age` or WinRAR on the machine, NordLocker is
installed but has no command line (it is a window you click, not something a
weekly task can drive), and Windows' own `Compress-Archive` cannot put a
password on a file at all. So `cryptography` is the only safe option already
there, and it is the one used.

**The weekly run is not sealed, on purpose.** An unattended run has no
passphrase, and the only place it could keep one is the same disk as the
backup - which is exactly the trade the app's own backup feature refuses to
make. Sealing is for the runs you start by hand. If you later want the weekly
snapshots encrypted too, the honest answer is not to store a passphrase but to
move `jarvis-data-snapshots` inside a NordLocker locker (or another encrypted
volume) - then the files are protected at rest and no passphrase sits on the
disk. **That is your call, and nothing here does it for you.**

## What this deliberately does not do

* **It makes no network call at all** - no `socket`, no `urllib`, no `http`, no
  `requests`, nothing that could upload. That is not a promise in a comment: the
  test suite reads the tool's own source and refuses those names, so a later
  "send it to the cloud" option cannot be added without a test going red. Rule 1
  is why, and it is also why chat history stays encrypted on this PC.
* **It never writes into `C:\Users\pcadmin\.openjarvis`.** The source is opened
  read-only, and the destination *and* any restore target are refused if they
  resolve inside it - so a typo cannot turn a backup into a write over the live
  data. The suite asks for both, expects both to be refused, and checks that
  the live folder is byte-for-byte as it was.
* **It does not back up the program.** Code is not personal data and this is
  not a code backup; the app's encrypted feature is where the source rides
  along.
* **It does not cover `voice-models` (1.14 GB, re-downloadable), `models`
  (64 MB, a downloaded model cache) or `logs` (13 MB of daily diagnostics).**
  Each is named with its reason in every snapshot's `manifest.json`, so nothing
  is dropped in silence.
* **It does not stop, restart or reconfigure Jarvis**, and it does not touch
  `config.toml` - it copies it, and that is all.

## If something looks wrong

* `last-run.txt` in the backup folder says what the last run did, in counts. A
  run that failed names the database and the reason. When the backup folder
  itself has gone, the note is written to
  `%LOCALAPPDATA%\JarvisDataBackup\last-run.txt` instead, and `status` shows it.
* A snapshot whose name ends `-INCOMPLETE` **is not a backup** - it is kept so
  you can see what went wrong, and the next good run does not count it.
* `verify` opens a snapshot and prints the real row count of every database.
  If it says "every database opens and matches its manifest", the snapshot is
  good.
* The whole thing is one file, `tools/jarvis_data_backup.py`, and it is
  checked by `backend/test_data_backup.py` (110 checks, plus 1 skipped on a PC with one drive) on every push.
