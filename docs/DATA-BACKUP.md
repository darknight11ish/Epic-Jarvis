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

The last line it prints says where the snapshot landed:
`C:\Users\pcadmin\jarvis-data-snapshots`.

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
and 607 rows in `jarvis-data-snapshots`.

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

## Where it lands - and why not in the folder you already have

`C:\Users\pcadmin\jarvis-data-snapshots`.

**Deliberately not** `C:\Users\pcadmin\Documents\Jarvis Backups`. That folder
is one your app is allowed to point at a cloud-synced place: its own source
says a NordLocker or OneDrive folder is fine there, because rule 1 is bent "for
that one locked file only" - the file being encrypted before it is written.
These snapshots are plain files. OneDrive is installed on your PC, so putting
unencrypted memory facts in a folder that might become a synced one would bend
rule 1 without you ever deciding to.

**And not inside the NordLocker locker.** That is not a preference: it was
measured, it does not encrypt anything with the app closed, and the tool now
refuses a locker destination in code rather than warning about it. The section
above has the numbers.

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
`jarvis_data_backup.py` now refuses a locker folder as its destination
outright**, with a message saying so, instead of warning about it.

**Why it cannot be made to work unattended:** unlocking a locker is something a
person does, in a window, with a password. At 03:00 on a Sunday there is
nobody there to do it.

**NordLocker's own files are not the problem.** Its `node_system_cache.db`
(48 MB) and `crypto_identity_cache.db` begin `4b f3 31 d0…` and `de b1 23 9d…`
- high-entropy blobs with no `SQLite format 3` header, so NordLocker's own
cache really is encrypted. That is its cache, not the vault folder.

## If you want the weekly snapshots encrypted - your choice, three ways

None of these is switched on, because each is a trade only you can accept.

**1. `--seal` with a passphrase (works today, no new setup).** The snapshot is
written as one `.jba` file, locked with AES-256-GCM under a key stretched from
your passphrase. The catch: the weekly task cannot type a passphrase, so this
only protects runs **you** start - and if you leave the passphrase in a file on
this PC for the task to read, it sits on the same disk as the backup it
protects.

**2. Encrypt the snapshot folder itself with Windows EFS** (Encrypting File
System - Windows' own file encryption, tied to your Windows account). Measured
on your PC: EFS is available (`cipher.exe` is present, `DisableEncryption = 0`,
the EFS service is installed), and once a folder is encrypted **new files
written into it are encrypted automatically, with no prompt** - a file created
after `cipher /e` on a folder came out with the Encrypted attribute set, and
read back normally. Windows made you a self-signed certificate for this
(`CN=pcadmin`, valid to 2126, private key present). It is transparent: the
weekly task needs no password and nothing about it changes. The catch is that
the key is the backup - **export that certificate and keep the file somewhere
else**, or a lost Windows profile means the snapshots can never be read again.
What it does **not** protect against: anyone using your Windows account.

**3. BitLocker**, which encrypts the whole drive. What it does **not** protect
against: anyone using your PC once Windows is running - it defends a stolen or
removed disk, not a logged-in stranger. It also covers everything on the drive,
not just the snapshots. (Its state on your PC is **not checked** here: reading
BitLocker status needs an administrator, and nothing in this work ran
elevated.)

**4. Leave it as it is.** The snapshot folder is plain files on a drive only
you use. That is what you have today, and it is a deliberate choice rather than
an oversight.

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

* `last-run.txt` in `jarvis-data-snapshots` says what the last run did, in
  counts. A run that failed names the database and the reason.
* A snapshot whose name ends `-INCOMPLETE` **is not a backup** - it is kept so
  you can see what went wrong, and the next good run does not count it.
* `verify` opens a snapshot and prints the real row count of every database.
  If it says "every database opens and matches its manifest", the snapshot is
  good.
* The whole thing is one file, `tools/jarvis_data_backup.py`, and it is
  checked by `backend/test_data_backup.py` (82 checks) on every push.
