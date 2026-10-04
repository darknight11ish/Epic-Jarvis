# Handoff: the 2026-10-03/04 test-suite fix pass

> **Superseded in part, same day.** The 2026-10-04 audit pass finished
> everything this document leaves open: section 4.1 (the erase hole), 4.2,
> 4.3 and 4.4 are all fixed and green, and all six audits in section 7 were
> run with their fixes applied. Three of the four items in section 4 turned
> out to be **product** bugs, not just stale tests. Read
> [`HANDOFF-2026-10-04-audit-pass.md`](HANDOFF-2026-10-04-audit-pass.md) for
> what was found and what was changed; the sections below are kept as the
> record of that pass.

Everything a fresh conversation needs to pick this up. Written 2026-10-04, at the
end of a long session, by the agent that did the work.

---

## 1. What this was

The owner's run of `apply-patches.ps1` reported **37 failing backend suites**
(181 passed). At the end of this pass: **43 of 47 suites green**, with 4 problem
areas left, each diagnosed below.

Two handoffs are in play:

- `docs/HANDOFF-GATE-ENTRIES-2026-10-03.md` — the original job (ten tools had no
  `_TOOL_ACTIONS` entry, so `action_for_tool()` fell through to
  `"unclassified_tool"`). **Done and deployed**: `gate-entries.patch` and
  `gate-action-name.patch` are on, the config is synced (79 tiers,
  `draft_email = "ask"`), and `test_agent.py` is 214/0.
- This file — the follow-on pass over every other failing suite.

---

## 2. The machine and how to run things

| Thing | Value |
|---|---|
| Repository | `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main` (a downloaded ZIP — **not** a git clone) |
| Live backend | `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program` |
| Owner's shell | **PowerShell 5.1** (`pwsh` 7 is not installed). `git 2.55.0` is on PATH. |
| Python | `py -3` → `C:\Users\pcadmin\AppData\Local\Programs\Python\Python312\python.exe` |

### Running the suites

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
$env:PYTHONIOENCODING = "utf-8"          # the console is cp1252; suites print non-ASCII
py -3 backend\run_suites.py               # or: py -3 backend\test_<name>.py
```

`run_suites.py <suite.py> ...` runs a subset — much faster than the full sweep
(~25 minutes).

### The patcher

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -FixLineEndings
```

`-SkipTests` skips its own suite run. It rehearses every patch on a copy first,
backs up every file it touches into `_jarvis-backup-<stamp>` inside the backend
folder, and never overwrites `jarvis-framework.toml`.

### Three traps that cost real time

1. **The sandbox blocks child processes from writing anywhere.** Python cannot
   create a nested temp directory unless the session is running with
   `danger-full-access`. Without it, suites and generators fail in ways that look
   like product bugs. Pointing `TEMP` at the workspace does **not** help —
   `New-Item`/Python writes are refused even inside the workspace. If you see
   `PermissionError: [WinError 5] ... Temp\dsh-*\tmp...`, it is the sandbox, not
   Jarvis.
2. **`require_shipped()` refuses to run a suite when the PC's copy of a shipped
   module differs from the repository's.** So after editing a *shipped* module
   (`jarvis_wiki.py`, `jarvis_app_workspace.py`, `jarvis_mcp.py`, ...) the suites
   refuse until either (a) you run the patcher, or (b) you copy the repo file over
   the PC's copy, or (c) you unset `JARVIS_BACKEND` and run in repo mode (which
   skips everything needing owner-only files). **Staging is a real change to the
   owner's PC** — say so plainly when you do it.
3. **Never trust a suite's result without real filesystem access.** Suites that
   create nested temp folders produce false failures under the sandbox.

---

## 3. Changes made by this pass

### Product bugs found and fixed (these matter most)

- **`backend/jarvis_wiki.py` — two hashing sites disagreed about `\r\n`.** A file
  saved by Notepad/Word hashed one way when read and another when checked against
  the cache, so it read as "changed" forever (re-reading the whole file and
  spending a model call on every visit) and a card made from it was refused the
  moment it was approved. Both sites now go through one helper, `_content_sha()`,
  which normalises line endings before hashing.
- **`tools/gen_wiki_cases.py` — the same bug in the generator.** It seeded its
  cache from the raw bytes, so the committed fixture had quietly **lost its
  `in_wiki` case entirely**. Fixed and the fixture regenerated.
- **`backend/jarvis_app_workspace.py` — a failed "add this app" left the folder
  behind.** Git marks its object files read-only and Windows refuses to unlink a
  read-only file; with `ignore_errors=True` the cleanup did nothing, so an orphan
  folder survived and showed up in the apps list as an unlinked app. Added
  `_rmtree_forced()`.
- **`backend/jarvis_mcp.py` — the plug-in approval card printed a fake command.**
  It rendered each argument with `json.dumps`, so on Windows the card showed
  `"C:\\Users\\pcadmin\\..."`. That is not the command that would run, and the
  command is exactly what the owner is asked to check. Added `_shown()`.

### Fixtures and generators

- Regenerated stale fixtures: focus, hardware, memory-words, voice-status,
  voice-training, phone-voice, wiki, projects.
- Pinned the three voice generators to the settings file this repository ships
  (`backend/rebuilt/jarvis-framework.toml`), so a fixture shared with both apps
  can no longer bake in the machine's `[voice] stt_engine`.
- `tools/gen_projects_cases.py` used to `unlink()` a sqlite file it still held
  open (WinError 32 on Windows); it now uses a fresh file per store.

### Test-harness fixes (not Jarvis bugs)

| Cause | Suites |
|---|---|
| Asserted a Linux-only fact with no platform guard | `test_screen`, `test_screen_win`, `test_screen_picture`, `test_screen_turn`, `test_picture_text`, `test_ocr_words` |
| `time.tzset()` does not exist on Windows (now honest SKIPs) | `test_decks`, `test_research`, `test_briefing` |
| Could not delete git's read-only object files | `test_apps`, `test_projects`, `test_patch_history` |
| Could not delete `schedule.json` still held open (now stop + `gc.collect()`) | `test_identity`, `test_manner`, `test_open_chat`, `test_sayable` |
| Used the OS temp folder as the folder the owner "picks" — which Jarvis refuses on purpose, because on Windows that is under AppData | `test_backup`, `test_documents` |
| The gate is called with the **resolved action**, not the tool's lookup name | `test_injection_cases`, `test_task_control` |
| Denied an action that later moved into `_NO_RULE_FROM_DENIAL` | `test_gate_outcome` |
| Waiting too little for work that loads the embedding model (~20s cold) | `test_memory_honesty` |
| Let the machine decide which embedder to use | `test_memory_safety` |
| Source-shape assertions that had drifted (`range(len(lanes) + 2)`, a 1100-char window, a bare literal, `len(calls) == 4`) | `test_degrade_filter`, `test_memory_pane`, `test_memory_noise`, `test_voice_503` |
| Windows `CreateProcess` searches beyond `PATH`, so emptying the env did not hide git | `test_app_workspace` |
| Only one news add is pending at a time | `test_news` |
| The first briefing pass downloads the embedding model inside the measured "no socket" window | `test_quick_wins` |
| A read that got no default encoding (cp1252 crash) / a missing NOT NULL column in a test's own insert | `test_voices`, `test_memory_intake` |
| Platform-aware wildcard resolution (14 honest SKIPs) | `test_bind_wildcard`, `test_installed_stand_in` |

### Staged onto the owner's PC

Three shipped modules were copied over the live copies so the suites could run
(backups left in `%TEMP%\jarvis-stage-010620`): `jarvis_wiki.py`,
`jarvis_app_workspace.py`, `jarvis_mcp.py`. The owner's later patcher run reported
*"All 158 modules ... are there and up to date"* and *"None of your backend files
were changed"*, so the patcher has adopted them as its own.

---

## 4. What is left — four problem areas

### 4.1 The erase hole — `test_memory_erase` (3), `test_memory_entities` (1)

**This is the only remaining item that breaks a promise the owner made**:
*"Erase the words" wipes the fact's text for good.* The test finds the erased
word **still in `memory.db` twice**, and its porter stem in the word index.

What is known:

- `erase()` (`backend/rebuilt/jarvis_memory.py:2054`) sets
  `PRAGMA secure_delete=ON` on **its own connection** (line 2155), updates
  `facts.text` to `[erased]`, deletes the FTS row and the vector, calls
  `_erase_copies()` and `_unlink_fact()`, commits, then `_scrub_file()`.
- `_erase_copies()` (line 3948) clears `proposals.text` by `fact_id` **and**
  `proposals.replaces` / `proposals.replaces_text` by `replaces_id`. It looked
  thorough, which is why the hunt moved on.
- **Not reproducible in isolation.** Erasing a short fact leaves **0**
  occurrences and reports `file_clean: True`. Reading `PRAGMA secure_delete` on an
  ordinary connection returns 0 — expected, it is per-connection and only set
  inside erase's transaction, so that is a red herring.
- A short-fact repro shows `before=0` in the raw file: SQLite holds recent writes
  in the WAL, so the words only become visible once enough has been written to
  force a checkpoint. **That is why only the test sees it.**

The test's fixture (`backend/test_memory_erase.py:358`) has four ingredients:
40 filler facts, an **accepted** proposal holding the words with `fact_id=fid`, a
**pending** proposal holding them in `replaces`/`replaces_text` with
`replaces_id=fid`, and a long fact (`SECRET + "a long note about the drawer " * 200`)
that spills onto overflow pages — *"the case secure_delete is for"*.

**Next step:** run that exact fixture and drop one ingredient at a time. The two
hypotheses worth testing first are (a) the long fact's **overflow pages** are not
zeroed the way ordinary freed pages are, and (b) the pending proposal's
`replaces_text` survives a path `_erase_copies` does not reach. Do not change
deletion code on a guess — an incomplete erase fix is worse than a failing test.

### 4.2 `test_memory_intake` (5) — stale assertions, product correct

Measured against the live backend:

```
queued now:
  "Started the new job yesterday (2026-09-22)"       replaces: null
  "Mario is a vegetarian (as of 2026-09-23)"         replaces: null   ← the correction
  "Mario is not a vegetarian (as of 2026-09-23)"     replaces: null

setup_status(): near_duplicate_check: 'on'
  keys: auto_accept, enabled, near_duplicate_check, note, pending, queue_full, setup_complete
```

- **The near-duplicate drop works.** Only one entry carries those words, and it is
  the correction. The assertion fails only because every fact now queues with a
  ` (as of YYYY-MM-DD)` suffix, so `texts.count("Mario is a vegetarian")` is 0.
  Assert on the text *before* the suffix.
- Same suffix problem for `"the one with a 'not' was"`.
- `pending()` no longer returns a non-null `replaces`; the correction is linked to
  the fact it supersedes some other way. **One probe of `pending()`'s full key list
  decides this** — print `sorted(X.pending()[0])` and look for `replaces_id` /
  `replaces_text`.
- `setup_status()` no longer has `near_duplicates_dropped`, only
  `near_duplicate_check`.
- The fifth check ("a number off the list queues a plain fact that retires
  nothing") needs the same look at its own scenario's inputs.

### 4.3 `test_extraction_wiring` (1) — environmental

`a burst of turns produces one pass, not one per turn` fails with
`! learning pass failed: RuntimeError: the local model is not up`. Everything else
in the suite passes. Check whether the test stubs the model; if it does not, this
is the Ollama model not being loaded rather than a product fault.

### 4.4 `test_voice_contract` (1) — one fixture still leaks the machine

`voice-status-cases.json` and `phone-voice-cases.json` pass;
`voice-training-cases.json` is out of date. The difference is the **graphics
card**: the committed contract says `NVIDIA GeForce RTX 2060` (a stand-in) and the
suite-env run produces the owner's real `NVIDIA GeForce RTX 2080 SUPER` (plus a
`why` string naming it).

`tools/gen_voice_training_cases.py` never sets `card` itself — it comes from a
module's status output. Three blocks use the stand-in
`SCG.World(SCG.SMI["2080s_2060"], windows=True)` (lines 549, 731, 738); the leak
is in the stand-in not taking effect under the suite runner, or in a case that
never installs one. Regenerate under the suite env and diff to see which cases
leak, then either fix the stand-in or extend the generator's `scrub()` to the card
name. **Do not simply regenerate** — that writes the owner's real GPU into a
contract shared with both apps.

---

## 5. Two open product findings (not test bugs)

### 5.1 The relevance floor cannot separate unrelated text with the real model

Measured with the owner's real `bge-small-en-v1.5` embedder against the 8-fact
corpus in `test_memory_safety.py`, with `_MAX_VEC_DISTANCE = 1.0`:

```
'zzzz qqqq'                     distances = [0.87, 0.96, 0.99, 1.00]
'write me a haiku about rain'   distances = [0.98, 0.98, 1.02, 1.08]
'am I allergic to anything'     distances = [0.90, 0.96, 1.07, 1.09]   ← on-topic, barely better
```

So on this machine an off-topic question pulls in the owner's bank, medication and
car. The test was pinned to the deterministic `HashEmbedder` so it measures the
floor's *logic* reproducibly; the floor itself is a tuning decision. The project's
own rule is that memory changes must beat `backend/eval_memory.py` before they are
kept — **measure first, do not retune on judgement.**

### 5.2 `_db()` handle lifetime — reviewed, not changed

`backend/jarvis_schedule.py` has 29 call sites of `with self._lock, self._db() as c:`,
and `_db()` returns a raw `sqlite3.Connection`. A connection's context manager
commits but does **not** close. This is plausibly why Windows refused to delete
`schedule.json` in several suites. It was left alone deliberately: converting
`_db()` to a real context manager touches every scheduler path and needs its own
pass with `test_schedule.py` green.

---

## 6. How to verify where things stand

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -FixLineEndings
```

Expect the suite list to show the four problem areas above and nothing else.
Some suites now report *"passed, but N part(s) were SKIPPED (not proven)"* — that
is deliberate: parts that simulate other timezones, resolve IPv6 wildcards, or
parse PowerShell cannot be proven on Windows, and CI proves them on Linux. It is
an honest SKIP, not a hidden failure.

### Facts that help when reading the output

- `test_bind_wildcard` skips 14 parts, `test_past_time_zones` 7, `test_wiki` 4,
  `test_decks` 2, `test_research` 2, `test_schedule` 2, and a few 1s.
- `test_agent.py` at 214/0 is the proof the gate work landed.
- The owner's live `jarvis-framework.toml` keeps its own `[voice] stt_engine =
  "faster-whisper"` and five `[security] sandbox_*` lines. That is intentional;
  the patcher reports the difference and changes nothing.

---

## 7. Audits worth running next (suggested, not started)

1. **Promises vs tests.** For every promise in `CLAUDE.md` / `ARCHITECTURE.md`,
   find the test that would go red if it broke — then break it on purpose and
   confirm. This is what would have caught the erase hole.
2. **Fixture hermeticity.** Run each `tools/gen_*_cases.py` with the owner's
   config, with an empty config, and under `run_suites.py`'s env; require
   byte-identical output. Two leaks were found here by accident.
3. **Windows-vs-CI gap.** CI runs the backend suites on Ubuntu only, which is why
   ~15 of them assumed Linux. Add a Windows CI job for the subset that needs no
   owner files.
4. **"Test reads the source as text."** Six tests assert literal source strings or
   fixed character windows; they rot silently on refactor. Move them to AST or
   marker-based checks.
5. **Gate-name consistency.** One cross-check test — every tool's lookup name
   resolves to an action present in the live tier table, and every action a test
   names still exists — would have caught four of this pass's failures.
6. **Memory quality measurement** with the real embedder (finding 5.1).

---

## 8. Repo hygiene at the end of this pass

- `final-run.txt` and `final-run2.txt` in the repo root are the agent's suite-run
  evidence; safe to delete.
- `yt-out.txt` in the repo root is the owner's own leftover from YouTube
  debugging; safe to delete.
- `__pycache__` folders exist under `backend/`, `backend/rebuilt/`, `tools/`.
- Every file this pass touched parses cleanly (checked with `ast.parse`).

---

## 9. Verified result of the whole pass (added at the end)

A full `py -3 backend/run_suites.py` against the live backend finished with:

```
238 passed, 6 failed, 0 skipped
failed: test_extraction_wiring.py, test_memory_entities.py, test_memory_erase.py,
        test_memory_intake.py, test_second_card.py, test_suite_state.py
```

Read that with three corrections, because the run started before the last two
edits landed:

1. **`test_second_card` is fixed** and now reads **503 passed, 0 failed**. The
   check was updated for the owner's decision: an attached picture whose words
   cannot be read is *replaced by a note* saying the model cannot see pictures,
   never sent blind. Its old assertion demanded the picture be passed through
   unchanged.
2. **`test_voice_contract` is `ok`** in this run. My earlier reports of it failing
   came from running the suite *directly* (`py -3 backend/test_voice_contract.py`),
   which does not set the suite-runner environment. Through `run_suites.py` it
   passes, including the training fixture. **If you see it fail, check which of the
   two invocations you used before changing anything.**
3. **`test_suite_state` is newly failing, and it is a side-effect of the
   `test_task_control` fix.** That suite runs `run_suites.py test_task_control.py`
   as a subprocess and requires it to pass; under *its* invocation the inner run
   reports `110 passed, 1 failed`, while running the same suite normally gives
   `111 passed, 0 failed`. So the inner invocation must differ in environment —
   most likely it does not set `JARVIS_BACKEND` the way the patcher does, so the
   card is raised through a stand-in whose resolved action differs.

   **Start here:** read how `backend/test_suite_state.py` builds the environment
   for its child run, then reproduce the inner `110/1` with that exact environment
   and look at which check fails. The likely answer is that the expected action
   name in `t_resume_asks_first_and_runs_only_the_rest` needs to accept both the
   live resolved name (`control_computer`) and what the stand-in stack produces —
   or that the suite-state child needs `JARVIS_BACKEND` passed through like the
   patcher passes it.

   It is worth doing properly rather than loosening the assertion: this suite is
   the guard that the runner isolates state, so a failure in it is information.

**Net effect of the pass: 37 failing suites → 4 problem areas**
(`test_memory_erase` + `test_memory_entities`, `test_memory_intake`,
`test_extraction_wiring`, and the `test_suite_state`/`test_task_control`
interaction above).
