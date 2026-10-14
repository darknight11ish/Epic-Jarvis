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
