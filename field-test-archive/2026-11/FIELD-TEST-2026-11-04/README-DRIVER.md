# The field-test driver for the 2026-11-04 deploy

**Written 2026-11-04, before the deploy. It has never been run against the live stack** - the
build it is meant to judge does not exist yet. Two files, nothing else:

| file | what it is |
|---|---|
| `agent_drive.py` | the driver: seven subcommands, standard library only, Python 3.12 |
| `README-DRIVER.md` | this page |

The 18 rows and the five probes it automates are in
[`../FIELD-TEST-RUNBOOK-2026-11-04.md`](../FIELD-TEST-RUNBOOK-2026-11-04.md). This driver does not
replace that runbook: it replaces the **typing** in it, so the field-test session spends its time on
the things only a person can do - a card, a screen, a voice, the clock.

## The one rule it cannot bend

**A probe PASS is not a field PASS.** `docs/FIELD-TEST-MATRIX-2026-10-11.md` says so, and it says
BLOCKED, PARTIAL and NOT-TESTABLE are never counted as passes. An agent is not the owner. So the
driver prints evidence and the honest **ceiling** for each row, and `rows` lists every row whose
whole point is a person's decision as PARTIAL or BLOCKED - never PASS.

## Run these, one line each

From the repository root. Everything below is one line, ready to paste.

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py rows
```

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py preflight --feature-sha <a row's merge commit> --backend-sha <the commit the update log names>
```

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py probe-a
```

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py probe-b
```

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py probe-c
```

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py probe-d
```

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 .dsh-scratch\FIELD-TEST-2026-11-04\agent_drive.py probe-e --allow-live-turns
```

`--help` works on the driver and on every subcommand, and every subcommand accepts the same five
switches (`--repo`, `--backend-url`, `--live-backend`, `--adb`, `--serial`) after its own name.

## What each subcommand does

| subcommand | reads | writes |
|---|---|---|
| `preflight` | the Step-0 gate (`tools/check_field_test_binaries.py`, imported in-process), the token, `/api/self/version`, `/api/pending`, the live backend folder's file count, the installed desktop build, the phone's `versionName`/`versionCode`/`firstInstallTime`/`lastUpdateTime` | `preflight-<stamp>.json` |
| `probe-a` | nine HUD routes with `X-Jarvis-Token` and `X-Jarvis-Client: hud`, plus the same GET under three client names (`hud` 200 / other 403 / none 403) | `probe-a-<stamp>.json`, and each body under `probe-a/<stamp>/` (redacted where it is private) |
| `probe-b` | `GET /api/ps` on 11435, 11436, 11450 - no token | `probe-b-<stamp>.json`, `probe-b/<stamp>/lane-<port>.json` |
| `probe-c` | `adb devices`, `dumpsys package com.jarvis.client`, `wm density`, `uiautomator dump` + pull, `dumpsys notification --noredact` | `probe-c-<stamp>.json`, `probe-c/<stamp>/ui.xml`, `probe-c/<stamp>/notifications-jarvis.txt` |
| `probe-d` | `scripts/fieldtest-desktop.ps1` with `-Windows`, then `-Text` on the HUD and on the Settings window | `probe-d-<stamp>.json`, `probe-d/<stamp>/windows.txt`, `probe-d/<stamp>/text-hud.txt`, `probe-d/<stamp>/text-settings.txt` |
| `probe-e` | one ordinary chat turn, streamed the way the HUD streams it, and the `X-Jarvis-Route` header | `probe-e-<stamp>.json` (nothing at all unless `--allow-live-turns`) |
| `rows` | nothing - it is a printed matrix | nothing |

Every receipt lands in this folder. Nothing is written anywhere else on this PC.

The preflight table prints **PASS / FAIL / WARN / BLOCKED**, and **WAITING** where the gate honestly
answers `WAITING_FOR_RELEASE_BUILD` - the runbook's own vocabulary, so a build that is still
building is never dressed up as a failure or as a pass.

## The rules, in code rather than in a sentence

- **GET only.** There is no POST path in the file except probe-e's one chat turn, and that one
  refuses to run without `--allow-live-turns`. No card is approved or denied, no setting is changed,
  no preset or model switched, nothing installed.
- **The token is never printed, logged, saved, or put on a command line.** It is read at run time
  from the live backend's own `jarvis_token_store`, kept in one variable, and every printed and
  written character passes through `scrub()`. The Step-0 gate is **imported in-process** and handed
  the token through an injected HTTP function - that is why it never appears in a child process's
  argv either. If the import cannot be done, the gate runs as a subprocess **without** the token and
  says so.
- **Memory fact text and chat titles are never saved.** `/api/memory/facts` and
  `/api/conversations` are written through an allow-list that keeps ids, counts and flags; every
  other value becomes `{"_redacted": "text", "_chars": N}`. The other seven routes are saved whole,
  minus credential-shaped keys.
- **Writes are refused outside this folder.** `out_path()` resolves every path and exits if it
  would escape; a test in development confirmed it refuses `..\escaped.txt`.
- **Nothing is hardcoded that can be discovered.** The desktop version comes from the installed
  `.exe`'s own `FileVersion`/`ProductVersion`, cross-checked against the uninstall registry (the
  HKCU row is the witness; older HKLM rows are listed as stale). The phone version comes from
  `dumpsys package`. The Settings window's real title comes from `-Windows`, because the dash in it
  is not dependable - see "What I could not verify" below.
- **No network except the local machine and one public read.** Requests go to `127.0.0.1:4719`, to
  the three Ollama ports, and (only when the gate asks) to `api.github.com` for the two rolling
  releases' public metadata. No token ever goes to GitHub.

## What it can prove after the deploy - and what it cannot

**Mechanically provable** (a probe PASS, which is still not a field PASS): that the Step-0 gate
answers and which build is installed; that the nine routes answer and with what shape; the three
Ollama lanes, their size, VRAM and spill; the phone package, its notification record and the
on-screen text with bounds; the desktop's window list and its words; and the `X-Jarvis-Route`
header for one benign turn.

**Not mechanically provable, at all**: any card decision; any setting, model or preset change; the
owner's voice, facts or history; pixels (the phone sets `FLAG_SECURE`, so screenshots come back
black); the clock (a routine's next occurrence); DEF-029's reproduction (it needs a real cloud
reply); and the phone half of every desktop-only row.

## The F1-F18 matrix, compact

`py -3 ... agent_drive.py rows` prints the authoritative version with the checks and the human step
for each row. The ceiling column is the **best honest verdict** a machine-assisted session can
reach; it is never PASS.

| row | ceiling | what the driver adds | what a person still must do |
|---|---|---|---|
| F1 | PARTIAL | window list (a second `Jarvis` window), HUD text, versions | ask each "open ..." phrase, ask twice for a window, read Settings -> Updates |
| F2 | PARTIAL | `/api/self` counts, `/api/conversations` ids | ask for the portrait, open a conversation, deny a clear card |
| F3 | PARTIAL | `X-Jarvis-Route` for one turn | save the DeepSeek key, choose Cloud, judge a blank reply |
| F4 | PARTIAL | the three lanes, spill vs the 352 MiB cap | apply Coding, approve the card, restore the preset |
| F5 | PARTIAL | fact count and ids, pending count | say the facts, turn on the reworded switch |
| F6 | PARTIAL | the Settings text search, the phone dump | open the feature row on both apps |
| F7 | **BLOCKED** | the before-values only | any change and its undo - the driver may not write |
| F8 | PARTIAL | `/api/storage/scan` bytes | read the plan, deny once, approve only if wanted |
| F9 | **BLOCKED** | nothing | the reminder in your words, the card at fire time |
| F10 | PARTIAL | the Settings -> Voice row from the dump | open that screen, then the four voice cases with your voice |
| F11 | PARTIAL | `/api/limits`, lanes before/at/after, `/api/status` | set the window, approve the cards, wake it |
| F12 | **BLOCKED** | the pending count | the six tool names, the PAT card, every ask |
| F13 | PARTIAL | `jarvis_alarm` records, first-install continuity | create a routine, press a part's button |
| F14 | PARTIAL | the bar's bounds and dp height | look at Home in Full screen |
| F15 | PARTIAL | `/api/setup`, `/api/setup/progress`, `/api/setup/plan` | answer, skip, reopen, apply and read the card |
| F16 | PARTIAL | the sync sentence, both versions | press Install, read the log order, repeat with the box empty |
| F17 | PARTIAL | the words "Ask Jarvis" and the box's bounds | the focused/typing states and the pixels |
| F18 | **BLOCKED** | nothing | create a repeating routine and wait for the next occurrence |

18 rows: **0** can reach PASS mechanically, **14** have a PARTIAL ceiling, **4** are BLOCKED for a
driver (F7, F9, F12, F18).

## The order for the session

1. `rows` - plan, offline, touches nothing.
2. Deploy the backend, restart Jarvis, install the desktop build and the CI-signed APK (runbook
   section 2, steps 1-4). **Do not run the driver before this.**
3. `preflight` with the FINAL MAIN commit and the commit the update log names. Read the table. A
   `WAITING` gate is not a failure - install the named build and run the row later.
4. `probe-a`, then `probe-b` (that is the "before" lane picture).
5. `probe-c` and `probe-d` - the phone and the desktop must be showing something for these to read.
6. The human rows from the runbook. Run `preflight` again with each row's own merge commit when that
   row needs its own gate.
7. After a preset change, run `probe-b` again; after the phone install, run `probe-c` again - its
   continuity line compares `firstInstallTime` with the previous receipt in this folder.
8. `probe-e --allow-live-turns` last, once the Cloud preset and key are what F3 needs.

## Deliberate omissions, so nobody thinks they were forgotten

- **`/api/storage/cleanup/plan` is never called.** A GET may create a single-use plan, and the
  runbook says a plan is single-use. `probe-a` reads `/api/storage/scan` only.
- **No screenshot is taken.** The phone refuses capture (`FLAG_SECURE`), and a black PNG is not
  evidence.
- **`/api/schedule` is not read.** F9 and F18 need a reminder created in the owner's words and then
  time to pass; nothing read-only can prove them.
- **No settings, presets or tools are switched on.** That is the whole reason F7, F9, F12 and F18
  are BLOCKED rather than PARTIAL.
- **`/api/memory/facts` text is never read out**, even though the response contains it - the ids,
  the count and the item *key names* are kept, so the schema is visible without the content.

## The two writes outside this folder, and why they are not a breach

1. **One chat turn** in `probe-e`, only with `--allow-live-turns`. It is appended to this PC's
   History like any typed turn. No card is answered or denied.
2. **One temporary file on the phone**, `/sdcard/jarvis-fieldtest-ui.xml`, because
   `uiautomator dump` can only write to a path - that is how the runbook's method 1 reads a screen.
   The driver changes nothing else on the phone and never deletes anything.

Everything else it writes lands in this folder.

## What I could not verify while writing this, stated plainly

- **`preflight`, `probe-c` and `probe-d` have not been run against the live stack**, because the
  instruction was not to touch it before the deploy. Their code is compiled and their parsers are
  unit-tested against synthetic data (a fake `dumpsys package`, a fake `uiautomator` dump, a fake
  window list), but the real `adb` and PowerShell calls are unexercised until the session.
- **`probe-a`, `probe-b` and `probe-e` were run only against a local stub server** on a random
  loopback port - never against `127.0.0.1:4719`. That proved the redaction, the receipts, the
  spill arithmetic, the SSE parser and the route-header read, and nothing about the real backend.
- **The Settings window's name is not dependable.** The runbook says "the em-dash matters", but in
  this checkout both the runbook line and `scripts/fieldtest-desktop.ps1` spell it with **U+002D, a
  plain hyphen** (`Jarvis Desktop - Settings`). The driver therefore reads the real title out of
  `-Windows` first and only then falls back to the hyphen and the em-dash spellings.
- **`/api/ps` does not always report a context length.** Where it does not, probe-b prints `n/a` and
  says to read the preset's context from `/api/work` and the runbook's preset table. It never
  guesses a number.
- **The Step-0 gate needs each installed build's commit** to say PASS. `--github` supplies it only
  when the installed version *is* the published one; otherwise pass `--desktop-sha` / `--apk-sha`.
  Without them the gate honestly answers `WAITING_FOR_RELEASE_BUILD`. A gate that only checked the
  desktop is reported as **WARN**, not PASS, because the tool only checks the surfaces it was given.
- **The desktop registry holds three "Jarvis Desktop" rows on this PC** (an HKCU row and two older
  HKLM rows). That is why the exe's own metadata is the witness and the stale rows are only listed.
- **`--feature-sha` is repeatable but each SHA is a separate gate run.** With `--github` each run
  reads the public releases; the driver caches those two responses for the length of one preflight,
  so eighteen SHAs still cost two GitHub calls, not thirty-six.

## Exit codes

`0` clean; `1` a FAIL or BLOCKED check; `2` refused by policy or bad input (nothing was sent);
`3` honest "not yet" - the gate says `WAITING_FOR_RELEASE_BUILD`, a surface was not gated, or a
probe could not reach what it asks about. **A `3` is not a failure of the feature.**
