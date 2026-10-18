# The app's own backup: what it covers now

Written 2026-10-13, the day the coverage gap was measured and closed. Every
number here was read off the owner's own PC, not estimated.

This page is about **`backend/jarvis_backup.py`** - the backup feature Jarvis
already had, the one behind the Backups panel and the **Back up now** button.
It writes one locked `.jbak` file into a folder you choose, under a recovery
code shown once. Four of them sat in `C:\Users\pcadmin\Documents\Jarvis
Backups`, the newest from **2026-10-10 09:49**.

## The gap, measured

Your personal data lives in `C:\Users\pcadmin\.openjarvis\`, and **19 SQLite
databases** are in it. The feature named **12** of them:

```
memory.db  chat-history.db  schedule.db  feedback.db  projects.db  goals.db
study.db   arbiter.db       jobs.db      ledger.db   watch.db     tasks.db
```

Seven were not on the list. One of the seven is left out **on purpose** and
that decision was checked rather than changed: **`approvals.db`** (51 rows) is
pending-approval state, not memory, and restoring a stale "waiting" row would
mislead. It stays out, and the module now says so in one place with its
reason.

Two more files were missing for a plainer reason still. The feature carried
every `*.json` file in the settings folder - and **`config.toml` is not a
`.json`**, so the HUD's own settings file, the one holding every choice you
made in Jarvis's window, was in **no backup of any kind**. `speed.jsonl` (the
speed samples the desktop graph is drawn from) was missed by the same rule.

## What was added

**Two databases.** Of the seven, these are the two that hold your own content:

| database | what is in it | why it is carried |
|---|---|---|
| `knowledge.db` | 6 tables - things you paste and import into the knowledge store | it is your own material, and it is one of the stores CLAUDE.md rule 1 names |
| `traces.db` | 7 tables, 9 rows - the words you typed and the answer you were given | the same class of thing as chat history, which is already carried |

**Two settings files**, under the same `settings/` prefix the JSON files use,
so a restore puts them back with no new rule: `config.toml` and `speed.jsonl`.

## What was deliberately left out, and why

The other five databases are now written down in the module itself, in a
mapping called `NOT_BACKED_UP`, each with its reason. A name is either backed
up or excluded **with a reason written beside it**, and a test fails if one is
in neither list:

| database | measured 2026-10-13 | why it stays out |
|---|---|---|
| `agents.db` | 6 tables, **0 rows** | empty template tables; the modules recreate them |
| `audit.db` | 1 table, **0 rows** | a security trail, not memory - a stale one restored misleads |
| `digest.db` | 1 table, **0 rows** | generated digests, re-made from data that is carried |
| `sync_state.db` | 1 table, **0 rows** | sync cursors: an old one says items are fetched that are not |
| `telemetry.db` | 2 tables, 1 row | measurements of the machine, not of you; its writer is off by design |

Also left out, each with a reason that is now written down rather than
inferred:

* **The `-wal`, `-shm` and `-journal` files.** Never copied, and never needed -
  see the next section.
* **`USER.md`, `SOUL.md`, `MEMORY.md`** and `first_chat_sent`: 18, 69, 18 and 0
  bytes of unedited template.
* **The `devices/` folder.** It holds a SHA-256 of each paired device's token
  and the list of devices allowed to talk to Jarvis. That is authorization
  state - restoring an old copy would re-authorize a phone you had removed -
  and it is credential material that belongs on the PC that checks it. This
  was already true (the `*.json` rule cannot reach into a subfolder); it is
  written down because it was checked.
* **`chatbot/api-money.json`** (your spending limits) is in that same
  subfolder and is therefore also not carried. This one is a **stated gap, not
  a decision**: it is three numbers, and adding subfolder support changes what
  the archive layout may hold rather than adding a name to a list.

## The `-wal` trap, and why the log files are not needed

A SQLite database keeps recent writes in a *write-ahead log* - the `-wal` file
beside it - and folds them back into the main file later, or never while a
program holds the database open, which Jarvis always does. So the `-wal` file
can hold more than the database does.

**That is why a plain copy is not a backup.** Measured on your PC: `agents.db`
is 4,096 bytes with a **115,392-byte** log beside it, `traces.db` 4,096 with
**78,312**, `telemetry.db` 4,096 with **28,872**. Copy the main file alone and
you get an empty shell - **0 tables** where the live database reads 6, 7 and 2.

**This feature never does that.** It asks SQLite to copy itself, with the
online backup API, which reads one consistent view and folds the log into the
result. Measured, with a database built to keep its rows *only* in the log:

| how the copy was taken | rows that arrived |
|---|---|
| a plain copy of the main file | **none** - the table cannot even be read |
| the online backup API, which this feature uses | **all 40, and the schema** |

The snapshot is self-contained: every row survives with **no `-wal` beside it
at all**, which is checked by deleting the sidecar files and reading it cold.
`test_backup.py` proves this on every run, so the next person who changes how a
database is copied has to keep it true.

## `config.toml` holds no secret - checked, not assumed

`config.toml` was read line by line before it was added, because rule 3 says a
pairing token or an API key is never written to disk in plain text:

* **every** token, password, `app_secret` and `api_key` line in it is
  **commented out** and empty - 14 of them, for Telegram, Discord, Slack,
  WhatsApp, Teams, Matrix, Mattermost and Feishu, each followed by "Or set
  `<SERVICE>_TOKEN` env var";
* the one place it says how a real key arrives names the **environment**:
  "Auth comes from the `VLLM_API_KEY` environment variable";
* the weather credentials are not there either, in the file's own words:
  "Weather API credentials belong in `credentials.toml` or the environment,
  not here" - and there is no `credentials.toml` and no `*.env` in the folder;
* `[server]` is `host = "127.0.0.1"`, with the `0.0.0.0` line commented out;
* the only matches that are not comments are ordinary settings whose *names*
  contain the words: `max_tokens = 1024` and `secret_scanner = true`.

So carrying it puts no secret into the archive, and the archive is
AES-256-GCM under a recovery code only you hold in any case. **The half worth
knowing:** if a token is ever pasted into that file instead of into Windows
Credential Manager, it starts travelling in every backup from then on. A test
now reads the real file and fails on a live secret-shaped line, so that day
announces itself instead of passing quietly.

## What did not change

The lock, the folder, the retention (**5** kept), the routes and the approval
cards are all exactly as they were - this change only widens what goes inside
the archive. A restore still asks once, still always needs Windows Hello, still
comes only from this PC, and still backs up your current data first with a
fresh recovery code so the restore itself can be undone. Its card now also
names the knowledge and trace stores, because it replaces those too.

The archive's layout gained nothing new: the two databases travel under the
same `db/` prefix as the other twelve, and the two settings files under the
same `settings/` prefix as the JSON. One list in the module,
`_named_settings_entries`, is what may land in your settings folder, so a
tampered archive cannot write an arbitrary file there.

## If something looks wrong

* `python backend/test_backup.py` runs the whole feature's suite (206 checks,
  all of which pass without a model, a network or your real Credential
  Manager).
* A backup's own `manifest.json` lists every database it holds with its table
  and row counts, which is what the restore preview shows you before you
  approve anything.
* The module's own docstring, at the top of `backend/jarvis_backup.py`, is the
  full record: every name it carries, every name it refuses, and the reason.

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
| locked? | yes, AES-256-GCM, code shown once | **yes since 2026-10-18**: sealed by default, key in Windows Credential Manager (`--plaintext` is a debugging exception) |
| how many kept | 5 | 4 |
| can it be scheduled? | no - the code would be lost | yes, that is what it is for |

The weekly snapshots are sealed by default since **2026-10-18** (audit HIGH-4):
one `.jba` file per run, AES-256-GCM/Argon2id, with the key kept in Windows
Credential Manager under `Jarvis Backend/data backup key`. The key is never
printed or written to a file, so a sealed snapshot opens only on this Windows
account on this PC - the `.jbak` archives, whose recovery code you hold, remain
the disaster-recovery path. Plaintext snapshots written before that date are
**not deleted automatically**: the tool names them and prints the exact
`Remove-Item -LiteralPath @(...) -Recurse -Force` line once a sealed snapshot
exists. The full at-rest picture, including what is still plaintext, is
`docs/AT-REST-2026-10-18.md`.

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

**And not inside the NordLocker locker itself.** That is not a preference: it
was measured, it does not encrypt anything with the app closed, and the tool now
refuses a locker destination in code rather than warning about it. The section
below has the numbers.

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
make. Sealing is for the runs you start by hand.

## NordLocker cannot encrypt these snapshots, and this was measured

You asked for the weekly snapshots to be encrypted at rest with NordLocker,
which is installed on your PC. **It cannot do that job**, so nothing was wired
to it - a weekly task that appeared to be encrypted and was not would be worse
than no encryption at all. This is what was actually measured on your machine
on 2026-10-13. A small probe file was written and then deleted; nothing else
was changed.

**How NordLocker holds your files.** Its vault,
`C:\Users\pcadmin\NordLocker_9019064`, is **not** a locked disk. It is a folder
of placeholders - the file names are visible, and the contents are fetched on
demand. The proof is the filesystem's own record: `fsutil reparsepoint query`
on that folder reports reparse tag `0x9000201a` (fetch the contents when the
file is opened) and `0x9000301a` (fetch them when it is closed) - the same
mechanism OneDrive uses, and the reason `NordLocker.CloudFilter.dll` ships
inside the program folder. NordLocker also has no Windows service and no
driver of its own, so there is nothing left running to do any encrypting when
the app is closed.

**The test that decides it.** NordLocker was closed, and a 40 MB file was
written into `NordLocker_9019064\My Files\`:

* **it consumed 42.03 MB of free space on `C:`** (131,066,798,080 bytes free
  before, 131,022,725,120 after) - the data really did land on the disk;
* `fsutil` said of that file, *"The file or directory is not a reparse point"*
  - it was not a placeholder, it was an ordinary local file;
* **starting NordLocker and waiting did not encrypt it.** It stayed an
  ordinary readable file.

A real database written the same way behaved the same: a `SQLite format 3`
file in the locker still began `53 51 4c 69 74 65 20 66 6f 72 6d 61 74 20 33 00`
and still contained its plaintext marker, word for word.

**And it would have looked like a success.** The locker folder is writable
whether or not NordLocker is running, so a task pointed there would report
"OK", write your data in the clear, and nobody would know. **That is why
`jarvis_data_backup.py` refuses a locker folder as its destination outright**,
with a message saying so, instead of warning about it - and why the refusal sits
in the one function *every* destination goes through, so `--dest`, the folder
you picked in the app and the built-in default are all covered by it.

**Why it cannot be made to work unattended:** unlocking a locker is something a
person does, in a window, with a password. At 03:00 on a Sunday there is
nobody there to do it.

**NordLocker's own files are not the problem.** Its `node_system_cache.db`
(48 MB) and `crypto_identity_cache.db` begin `4b f3 31 d0...` and `de b1 23 9d...`
- high-entropy blobs with no `SQLite format 3` header, so NordLocker's own
cache really is encrypted. That is its cache, not the vault folder.

## If you want the weekly snapshots encrypted - what is already on, and what is left

**Already on: Windows EFS** (Encrypting File System - Windows' own file
encryption, tied to your Windows account), switched on 2026-10-14. Measured on
your PC: `cipher.exe` is present, `DisableEncryption = 0` and the EFS service is
installed, and once a folder is encrypted **new files written into it are
encrypted automatically, with no prompt** - a file created after `cipher /e` on
a folder came out with the Encrypted attribute set, and read back normally. It is
transparent: the weekly task needs no password and was not changed at all.
`tools/check_snapshots_encrypted.py` reads the EFS attribute of the folder and of
every file beneath it, fails naming the plain ones, and proves its own reader
with `--self-test`; it currently reports **230 paths encrypted, 0 plain** in
`C:\Users\pcadmin\jarvis-data-snapshots` and **177 paths encrypted, 0 plain** in
`C:\Users\pcadmin\Documents\Jarvis Backups`. **The catch is that the key is the
backup:** the files are tied to your Windows account (a self-signed `CN=pcadmin`
certificate, valid to 2126, private key present), so **export that certificate
and keep the file somewhere else**, or a lost Windows profile means the snapshots
can never be read again. What it does **not** protect against: anyone using your
Windows account.

**Still yours to choose: `--seal` with a passphrase (works today, no new
setup).** The snapshot is written as one `.jba` file, locked with AES-256-GCM
under a key stretched from your passphrase. The catch: the weekly task cannot
type a passphrase, so this only protects runs **you** start - and if you leave
the passphrase in a file on this PC for the task to read, it sits on the same
disk as the backup it protects.

**Still yours to choose: BitLocker**, which encrypts the whole drive. What it
does **not** protect against: anyone using your PC once Windows is running - it
defends a stolen or removed disk, not a logged-in stranger. It also covers
everything on the drive, not just the snapshots. (Its state on your PC is **not
checked** here: reading BitLocker status needs an administrator, and nothing in
this work ran elevated.)

**Or add nothing else.** What you have today is EFS at rest on the drive the
snapshots live on, and a weekly run that needs no password. That is a deliberate
choice rather than an oversight.

If you want one of the first three, say which and it can be set up - but none
of them is this tool deciding for you.

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
* **It refuses a NordLocker locker as its destination** - measured on this PC,
  and explained above. The alternative is a backup that says it is protected
  and is not.
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
  checked by `backend/test_data_backup.py` (123 checks, plus 1 skipped on a PC with one drive) on every push.
