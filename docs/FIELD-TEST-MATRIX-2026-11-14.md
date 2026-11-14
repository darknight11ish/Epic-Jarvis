# Field-test matrix — the wave-19 deploy (desktop + phone)

**Opened 2026-11-14.** It records the wave-19 deploy measured that morning,
06:07–06:33 PDT, on the owner's real desktop and real phone: what the shipped
build actually did, not what the code is meant to do.

**Source record:** `C:\Users\pcadmin\Downloads\FIELD-TEST-2026-11-14-wave19.md`,
written the same morning from what was measured on this PC and the real phone.
Every verdict below comes from it: the desktop through Windows UI Automation on
the real windows, the phone through `adb` against the installed APK, and the
backend through its own answers. The record lives outside the repository, so it
is cited by path; it has not yet been copied into `field-test-archive/2026-11/`,
which the archive decision of the same day says is where field-test records
belong, so a later archive pass should take it. Nothing below is inferred from
the code.

**How to read this.** A row becomes **PASS** only when the feature was actually
driven on the real app and the evidence names the build, the date and what was
seen. `BLOCKED`, `PARTIAL` and `NOT TESTABLE` (the earlier matrices spell the
last one `NOT-TESTABLE`) are never a pass - the same rule as
[`FIELD-TEST-MATRIX-2026-10-11.md`](FIELD-TEST-MATRIX-2026-10-11.md) and
[`FIELD-TEST-MATRIX-2026-11-09.md`](FIELD-TEST-MATRIX-2026-11-09.md), whose rows
stay intact and untouched. A row that was not driven says so.

**The ruling's shape.** The Gemini ruling that asked for this page named two
PASSes and three checks that need the owner's hands. The two Atlas rows carry
the PASSes it asked for; rows 4, 5 and 7 are the three checks only the owner can
finish, and none of them is written as a pass. The wave's own record also
measured a third PASS - the chat-storage answer on row 3 - and that is recorded
here rather than left out.

## The build this was tested on

| Half | Version | Where it came from | When (PT) |
|---|---|---|---|
| Backend | **0.2.454** | reconciled to `d9f8cbba9`, the merge of PR #1257 | 06:07–06:23 |
| Desktop | **0.2.454** | rolling `desktop-latest`, minisign-verified against the app's own key `ceb4fae76d70e330` | 06:20 |
| Phone | **0.2.4215** (code 1000004215) | rolling `client-latest`, `jarvis-client-d9f8cbb.apk`, after the emulator smoke job passed | 06:33 |

The live backend folder now holds this repository's bytes exactly: **0 of 338
shipped files differ** after `reconcile_live_backend.py --apply`, and the
previous state is backed up in `_jarvis-deploy-backup-tool-20261114-060835`.

## The rows

| # | feature | wave | desktop | phone | verdict | evidence |
|---|---|---|---|---|---|---|
| 1 | Atlas visible name — desktop (#1232) | 19 | **PASS** | n/a (the phone is row 2) | **PASS** | The real window titles read `Atlas HUD` and `Atlas — Brain` through Windows UI Automation, not a screenshot. The HUD's brand wordmark renders `◈ATLAS`, and its rails say `Atlas settings`, `Atlas Live`, `Atlas faces`. |
| 2 | Atlas visible name — phone (#1232) | 19 | n/a (the desktop is row 1) | **PASS** | **PASS** | The real launcher shows `Atlas`, its widget is `Atlas quick link`, and the installed APK is 0.2.4215. |
| 3 | "Where are my chats kept?" answered from the code (#1251) | 19 | **PASS** (live backend on this PC) | not driven | **PASS** | Asked the live backend, and it answered from the code rather than the model: the reply carried `"model":"no AI model"` and `"system_fingerprint":"fp_jarvis_quick"`, in 0.1 s. It named the file (`chat-history.db` in `.openjarvis`), the encryption (AES-256-GCM with its key in Windows Credential Manager), that voice is kept the same way, and both switches that turn it off. |
| 4 | Send any file type, up to 2 GiB (#1252) | 19 | **BLOCKED ON OWNER** | **BLOCKED ON OWNER** | **BLOCKED ON OWNER** | `begin` accepted 64 MiB of `application/octet-stream` - the old cap was 50 MiB - and returned `max_bytes 2147483648` (2 GiB). The first chunk then stopped at an approval card, `receive_uploaded_document`: the permission model working, which **must not be auto-approved**. The card was denied afterwards so it would not sit in the owner's UI as one that can no longer be pressed, and **nothing landed in the owner's Downloads folder**. |
| 5 | Widget look — Colour / See-through / Contrast (#1255) | 19 | **NOT TESTABLE** | not driven | **NOT TESTABLE** | The three pickers render only under a **draft** widget's preview in the Brain window, and there is no draft widget right now, so the real screen has nothing to press. The controls are in the shipped code (`brain.js`), but the see-through itself still needs the owner's eyes on the composited desktop. |
| 6 | Native Android screens (#1256) | 19 | **BLOCKED** (no entry point) | **BLOCKED** (no entry point) | **BLOCKED** | `DEF-068` is open: the builder and its four routes exist and are tested, but nothing in either app calls them, so there is no button or sentence that starts a native-screen build. It cannot be field-tested until an entry point exists. |
| 7 | Web search | — (not this deploy) | **FAIL** | n/a (PC-side service) | **FAIL** | The preflight reports `web search through searxng does not work`: SearXNG is not running - nothing answers on `http://127.0.0.1:8888`. Start it in Docker Desktop, or switch web search to another provider. Not a regression from this deploy: it is the one preflight failure that is not a record row. |
| 8 | Preflight after the deploy | deploy check | **FAIL** (15 rows, none new) | n/a | **FAIL** — measured, not a pass | `backend\selftest.py --preflight` → **34 pass / 15 fail / 3 warn / 5 skipped**. The 15 are not new, and the module rows improved from 9 failing to 4: **10** are patch-lineage rows (`appearance 216/334`, `attached-file 0/30`, `cloud-honesty 3/80`, `gpu-offload 61/94`, `approval-notice 77/111`, `show-card-timer 10/60`, `tools-enable` on two files, `forget-range` on two files) - the reseal predicted exactly 10 before the deploy too, so the deploy neither added nor removed one; **4** are record rows the reseal refuses to invent (`jarvis_extract.py`, `jarvis_gate.py`, `jarvis_hud.py`, `jarvis_skills.py`) - patched base files this repository does not ship, so their bytes cannot be proved from it; **1** is the SearXNG failure above. The reseal was **not** run with `--rebaseline-unprovable`, which would have recorded the folder's own bytes for those four and made the report look clean at the cost of those rows never detecting a change again. A skipped row is not a pass either. |

**Counts, over the eight rows above: 3 PASS / 2 FAIL / 1 BLOCKED ON OWNER / 1
BLOCKED / 1 NOT TESTABLE.** One FAIL is the preflight (a deploy check, not a
feature); the other is web search, which this deploy did not cause. No blocked
or not-testable row is counted as a pass.

**Reading the non-PASS rows.** Row 4 is not a fail: the approval card is the
permission model doing what it promises, and approving it by machine is not
allowed. Row 5 is not a pass: the controls exist in the shipped build, but the
screen that draws them cannot be reached without a draft widget. Row 6 is not a
pass: the builder exists, and nothing can start it. Row 7 is a real FAIL on the
installed build, and the cause is a service that is not running rather than this
deploy's code.

## The three checks that need your hands

1. **Approve one large file transfer.** Send any file, of any type, from the
   phone and press Approve. That is the only way to finish testing #1252, and
   it is the one thing standing between row 4 and a PASS.
2. **Build a widget, then look at its look pickers.** Ask Atlas for a custom
   widget; while it is a draft, the Brain window shows Colour / See-through /
   Contrast under its preview. Set See-through and check your wallpaper shows
   through on the desktop.
3. **Start SearXNG** if you want web search back. Nothing answers on
   `http://127.0.0.1:8888` today.

The native-screen builder is not a check you can do: it needs code first. `DEF-068`
stays open until an entry point calls the builder.

## What changed since the 2026-11-09 matrix

Six things landed between the 2026-11-09 matrix and this one, and all six are in
this deploy. **Atlas** replaced Jarvis in the places a person
reads - window titles, launcher label, widget name, rails and wordmark (#1232) -
although the wake word and the in-chat wording stay Jarvis on purpose.
**Native Android screens** let Jarvis build a real app with up to eight screens,
but nothing can start the builder yet, which is `DEF-068` (#1256). **Widget look**
adds eight accent colours, three ways of being see-through and a high-contrast
version, reachable only under a draft widget (#1255). The **chat-storage answer**
makes "where are my chats kept?" answer from the code rather than the model
(#1251). The **field-test archive** moved 53 records that existed only in
`.dsh-scratch/` into `field-test-archive/2026-11/` (#1254). The **skip report**
prints a machine skip as a skip, so a suite that did not run can no longer read
as one that passed (#1253).

## What this pass recorded but did not change

- **The rename is visible-only.** The wake word and the in-chat wording stay
  Jarvis, and the README states that limit. Three **HUD chrome** strings still
  say Jarvis in the merged source, so this is not a stale build: `Open the Jarvis
  bar` (the quickbar launcher's label and tooltip, appearing twice),
  `Talk to Jarvis: opens the quickbar - hold its mic button to speak.` (a
  tooltip), and `Let Jarvis Desktop start and stop Jarvis` (a Settings sentence,
  seen in the source; the Settings window was not opened for this test).
  Everything else renamed correctly, including the chat speaker label staying
  `JARVIS`, which is in-chat wording and is supposed to stay.
- **One deploy mistake, kept for the record.** The backend reconcile ran before
  the new desktop was installed, and the reconcile writes the backend's `VERSION`
  from whichever desktop is installed, so the HUD came up saying *"the backend
  0.2.452, but this HUD expects 0.2.454"*. It was fixed at the cause by
  re-running the reconcile once 0.2.454 was installed, and the banner is gone.
  The order that avoids it: install the desktop first, then reconcile, then
  restart.

## What this matrix does not cover

The rows of `docs/FIELD-TEST-MATRIX-2026-10-11.md` and
`docs/FIELD-TEST-MATRIX-2026-11-09.md` keep the verdicts those documents
measured; this page adds no verdict to them and re-opens none. It records only
the wave-19 deploy. A row here that is BLOCKED or NOT TESTABLE stays open until a
later pass drives it on real hardware - it is not quietly retired.
