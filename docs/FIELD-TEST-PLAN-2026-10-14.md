# The field-test plan for the big pass, 2026-10-14

**What this is.** The owner asked for a final pass: once all of the day's work merges,
all three parts on his machine get updated (the desktop program, the backend, the phone
app) and then **every new feature and every never-tested feature gets field tested on
both the desktop and the phone.**

This file is the **plan** for that pass. It is not a result. **It records no verdicts,
because none have been measured yet.** Everything below is either a citation of
something a dated record already measured, or a fact this plan's author measured on
this PC today and says so.

**The rule this plan runs on, unchanged.** *BLOCKED and NOT-TESTABLE are never counted
as passes* (`CLAUDE.md`, "Decided 2026-10-11"; `docs/FIELD-TEST-MATRIX-2026-10-11.md`
line 21; `docs/DECISIONS.md`). A row that could not be reached is written **BLOCKED**,
**PARTIAL** or **NOT-TESTABLE** and reads as such. Only a feature **driven on real
hardware** is a PASS. And, per the same file, **do not claim more than the evidence
supports**.

**Which tree every citation was read from.** This plan was written in the worktree
`.dsh-scratch/wt-fieldtest-plan`, branch `docs/field-test-plan-2026-10-14`, created
from **`origin/main` at `f80b1138`** (PR #404, merged 2026-10-14 00:22) and rebased onto
**`origin/main` at `bd24066f`** (PR #405, merged 2026-10-14 07:36) while it was being
written. Where a claim is about `main`, it was read with
`git show origin/main:<path>`, and where the record is quoted, the file and line are
named. **The repository root's `CLAUDE.md` is stale and was not used**; the copy read is
the one in this worktree, which is `origin/main`'s.

---

## 1. What is new since the last record

**What "the last record" means.** The most recent verdict-bearing records are
`docs/FIELD-TEST-2026-10-13-DESKTOP.md` (merged as PR #392, `a284f0d0`) and
`docs/FIELD-TEST-2026-10-13-PHONE-PASS.md` (merged as PR #393, `501ec1b6`). Both were
written against `origin/main` at `c6bb9e74`, and both say in their own words that they
did not touch the other device. **So "new" below means: merged into `origin/main`
after `c6bb9e74`, plus the open PRs still to land.**

The merge list is `git log origin/main --since="2026-10-13 00:00" --merges` (37 merge
commits). Not every merge is a testable feature — this plan counts only changes that
produce **behaviour a person can drive**, which is what the project means by a feature
(`CLAUDE.md`, "Every new feature gets its own audit", 2026-09-24).

### 1a. Landed on `main` — these will be in the updated build (10 items)

**Every item below was checked against `gh pr view <n> --json state,mergedAt` and against
`git log origin/main --merges` on 2026-10-14, not taken from the branch names.** Two rows
this plan first listed here were **wrong, and both are now corrected rather than left
standing**: PR **#381** had never merged and moved down to **N14 in §1b**, and PR **#405**
merged while this plan was being written and stays here as **N9** with its merge `bd24066f`
named.

| # | what is new | where it came from | the behaviour to drive, in one sentence |
|---|---|---|---|
| N1 | **One Update control updates both halves** | PR **#394** `feat/one-update-for-both`, merge `adbdb7a4`; `docs/ONE-UPDATE-FOR-BOTH.md` | Open **Settings → Updates → "Update both halves"** and check the dialog that appears names the backend folder by path, says every file it touches is copied into `_jarvis-backup-<date>` there first, and says which half runs first — then press Cancel and confirm nothing changed. |
| N2 | **The interruption budget's raise actually reaches the backend** | PR **#404** `fix/attention-settings-route`, merge `f80b1138`; `backend/attention-settings.patch`, `backend/test_attention_route.py` | Raise the interruption budget from the Brain's own card on either app; the route `POST /api/attention/settings` must answer **200** rather than **404 `{"error": "not found"}`**, and the new number must come back on the next read. |
| N3 | **The bar's far-left face is no longer clipped** | PR **#402** `fix/bar-face-clipped`, merge `1e7d5c2a`; `jarvis-desktop/src/style.css`, `jarvis-desktop/tests/bar-face.mjs` | Look at the Jarvis bar's left-hand mark: it must be the whole miniature face inside its 40 × 40 slot, not a tall narrow sliver running off the top and bottom. |
| N4 | **A switch can be found in Settings and in Find by the words printed on it** | PR **#391** `fix/settings-search-finds-switches`, merge `88f460a8` | On the phone, type **`Hide memory lists and chat history`** into the Settings search box and into Find: each must offer the Security row rather than *"Nothing here matches that."* / *"Nothing matches that."* |
| N5 | **A fired reminder can be deleted, in both apps** | PR **#387** `feat/clear-a-fired-reminder`, merge `44ea3b7d`, on the backend half PR **#383** `fix/def008-delete-a-fired-reminder`, merge `91295187` | Let a reminder come due, find it under *"Just went off"*, and press **Delete**: the row must go and `GET /api/schedule` must stop listing it. |
| N6 | **The two raise actions get classification rows, so their card stops saying UNCLASSIFIED** | PR **#384** `rescue/gate-raise-rows`, merge `3c8bc6ef`; `jarvis_limits.RAISE_ACTION`, `jarvis_arbiter.RAISE_ACTION` | Raise a spending limit or the interruption budget and read the approval card: it must no longer carry `classified: False` / `"not classified, so treated as irreversible and outbound"`, and no red **UNCLASSIFIED** pill. |
| N7 | **A second, measured picture reader (RapidOCR), off by default** | PR **#390** `feat/rapidocr-second-reader`, merge `7ff622e5`; `backend/jarvis_ocr.py` | Turn the second reader on and attach a picture containing a visible secret: the reader must still black the secret out before anything reads the picture — the whole point of the off-by-default switch. |
| N8 | **"What can I change by asking" stopped understating by three times** | PR **#365** `fix/what-can-i-change-honest`, merge `0b66984b` | Ask *"what can I change?"* and read the count: it must say a number derived from the settings tables rather than the old **13**, which named only on/off switches. |
| N9 | **The `change_setting` tool's own description was rewritten, so the model calls it** | PR **#405** `fix/change-setting-gets-called`, merge `bd24066f` (**merged 2026-10-14 07:36, while this plan was being written**) | Ask for a setting in words the fixed phrase grammar does not already match, then read `X-Jarvis-Route`: through the model path it must **not** say `{"lane": "no AI model"}`. |
| N10 | **The settings tool itself — any wording can change a setting** | PR **#368** `feat/settings-by-asking-any-wording`, merge `2930972b` | Same drive as N9, and read the card: a **loosening** must raise one rather than applying, and a name with no setter must be answered in words with **nothing changed and no card raised**. |

### 1b. In flight — the open PRs that bring new testable behaviour (6 items)

**These are not on `main` yet.** `gh pr list --state open` on 2026-10-14 shows six besides
this plan's own PR, every one of them carrying behaviour a person can drive. **Their rows
are already written in §3.2 and in the restore table of §6.2, so nothing has to be invented
when they land.**

| # | what is coming | the PR, and its state | the behaviour to drive |
|---|---|---|---|
| N11 | **The phone can ask the PC for a backup** — and shows the code before anything is written | PR **#408** `feat/phone-can-back-up`, **`MERGEABLE`** | Press **Back up now** on the phone; the code must be drawn **full-screen in four groups of five** and a tick must be set before the run can finish. `POST /api/backup/prepare` mints it and **writes nothing at all**; only `POST /api/backup/commit` (refused from anywhere but the PC) writes the file. |
| N12 | **One destination for both backups, and the owner picks it** | PR **#407** `feat/choose-the-backup-folder`, **`MERGEABLE`** (stacked on **#403**) | Settings → Backups → **"Choose a folder…"**; then run the weekly tool with no `--dest` and check the snapshot lands in the folder just chosen, reading `folder` from `~/.openjarvis/backup.json` **at run time**. |
| N13 | **A dead model lane says so *before* the question** | PR **#409** `feat/a-dead-lane-says-so`, **`MERGEABLE`** | With `/api/status` carrying `"ollama": false`, the bar, the widget and the HUD must draw the amber line *"The local model isn't running on your PC."* and the phone's Home status line must read **"Connected · Model not running"** — before any question is asked. **An absent field must draw nothing.** |
| N14 | **A device says what it is, and a label cannot make two rows read the same** | PR **#381** `fix/device-kind-and-label-collisions`, **`MERGEABLE`** | Open **Devices** on both apps and give a device a label identical to another's: the two rows must stay distinguishable, and each row must name the kind of device it is. |
| N15 | **His personal data gets a second copy, taken by SQLite itself and verified** | PR **#403** `feat/personal-data-backup`, **`CONFLICTING`** | A run must produce a copy in which `agents.db` carries its **6 tables** and `traces.db`, `telemetry.db` and `digest.db` are **present** — against the measured plain-copy result of **0 tables** and three databases **absent**. |
| N16 | **The weekly snapshots are encrypted now, and NordLocker was measured and refused** | PR **#412** `feat/efs-for-snapshots`, **`CONFLICTING`**, and PR **#406** `feat/encrypted-weekly-snapshots`, **`CONFLICTING`** | Every path under both snapshot folders must read encrypted, **zero plain**; and the tool must **refuse a NordLocker destination outright** rather than writing plaintext into it. |

**The honesty note this subsection exists for.** Three of these are **`CONFLICTING`**, and
`CLAUDE.md` records why that matters: *"**a conflicted pull request gets no CI at all**"* —
GitHub builds no `pull_request` run while a conflict is open, and on 2026-10-13 that left
two PRs (#369, #371) that **never had a single workflow run**. So a plan that assumes they
will land on time is a plan that may have nothing to test. **Re-run `gh pr list --state
open` before the pass starts, and treat this table as dated.**


### 1c. What did **not** count as new, and why

- **Docs-only merges** — #386 (the `docs/README.md` count rule), #396, #397, #398,
  #389, #385, #375, #377, #372, #392, #393, #373, #374. They change what is written
  down, not what an app does. #374 is the exception that proves the rule: it corrects
  `docs/GRAPHENEOS.md` about the local-network permission flow, which is Android
  plumbing rather than a behaviour with a control.
- **Bug fixes with no control to drive** — #363 (every card waits ten minutes; the
  ceiling is observable only by waiting), #366/#367 (test temp-folder leaks), #364
  (`tools/clean-worktree-targets.ps1`), #382 (`deny.toml` comments), #380 (SearXNG's
  container DNS).
- **#386's Tauri 2.12 stack move** — not user-visible on its own, but it **does**
  change the desktop binary, so the whole desktop half of this pass is also the first
  field test of a generation bump. That is a reason to drive the desktop first, not a
  feature to drive.

---

## 2. What has never been field tested

### 2.1 The counts, from the records themselves

From `docs/FIELD-TEST-MATRIX-2026-10-11.md`'s own reconciled tally (lines **19** and
**21**), which this plan re-derived mechanically from the 128-row table rather than
by eye, and agrees with:

| verdict | rows | the matrix's own words |
|---|---|---|
| FIELD-TESTED — **really a pass** | **61** | line 21: *"21 of these 82 are not passes, so the field-tested set is 61"* |
| BLOCKED (a later top-up) | **10** | line 21; the top-up's own section 5 lists 10 BLOCKED (`FIELD-TEST-2026-10-12-TOPUP.md:109-130`) |
| NOT-TESTABLE (a later top-up) | **10** | line 21; `-TOPUP.md:117-126` |
| PARTIAL (a later top-up, + `pictures`) | **3** | line 21 gives 2; row 128 (`pictures`) carries the third (line 19) |
| **NEVER TESTED** | **17** | the first pass's own column (rows 8, 11, 13, 19, 31, 37, 43, 44, 47, 66, 82, 83, 90, 101, 119, 121, 126) |
| **NOT FOUND** | **15** | rows 14, 17, 26, 29, 50, 57, 67, 68, 81, 85, 89, 92, 98, 110, 125 |
| **TEST-VERIFIED ONLY** | **13** | rows 4, 12, 16, 23, 24, 32, 40, 54, 80, 86, 93, 99, 105 |
| **total** | **129** | 61 + 10 + 10 + 3 + 17 + 15 + 13 |

**Where the figures come from, exactly.** The `61 / 10 / 10 / 2` split is the matrix's
own correction note (line 21), quoting the top-ups. The `17` and `15` are the first
pass's columns, which **no later record replaced** — the top-ups moved rows *within*
those sets, they did not re-count the sets. The `3` PARTIAL is the matrix's own line
19 (two top-up PARTIALs) **plus** row 128 `pictures`, which line 19 itself adds. And
the denominator is **129**, not 128, because row 128 exists on top of the 128-row
table — 128 rows in the table and the table's own numbering runs 1–128.

### 2.2 What the later records then reached, which removes rows from that queue

Quoted with their source, because this is the half that makes the queue short:

- **The desktop pass, `docs/FIELD-TEST-2026-10-13-DESKTOP.md`**, drove and verdicted:
  `typing` **PASS** (§4.1, line 182); `coming-up` **PARTIAL** (§4.1, line 183);
  `focus` **PASS** (§4.1, line 184); `from now on…` **driven, refuses honestly**
  (§4.1, line 185); `crash-notes` **PASS** (§4.2, line 201); and PARTIALs for `about`,
  `updates`, `tool-updates`, `first-run`, `big-model`, `settings-file`,
  `notifications`, `second-card`, `reach`, `conversation-window`, `galaxy`, `now`,
  `temporary-chat`, `hud-window` (§4.2–§4.3, lines 202–219). Its **§5 (lines 227–237)**
  names the rows it could **not** reach, each with the reason.
- **The phone pass, `docs/FIELD-TEST-2026-10-13-PHONE-PASS.md`**, drove 26 rows and its
  own tally is at **lines 112–117**: **PASS 11**, **PARTIAL 12**, **BLOCKED /
  NOT-TESTABLE 4**. The 11 PASSes are `pinned-facts`, `between-us`, `memory-as-of`,
  `chat-tags`, `memory-tab`, `memory-known`, `memory-saved`, `memory-waiting`,
  `memory-people`, `memory-learning`, `history`. Its **§4 (lines 128–147)** names every
  row it could not reach, with the phone's or the catalogue's own reason.

### 2.3 The honest count of what has still never been driven

**Derived, not opinionated** — each row below is a row the records still show as
never-driven, with the record that says so.

**(a) Never driven on *either* device, and still not — 4 rows.** These are the four
`FIELD-TEST-2026-10-12-TOPUP-2.md:38-47` left UNTESTED and said why, and no later
record moved them:

| feature | the record that leaves it UNTESTED | why, in the record's own words |
|---|---|---|
| `spoken-style` | `-TOPUP-2.md:44` | *"it happens for anything **asked by voice**, and this machine has no one to speak the question"* |
| `voice-training` | `-TOPUP-2.md:45` | *"**It has to be his voice** - a stand-in would test the stand-in, not the feature"* |
| `photo-reminder` | `-TOPUP-2.md:46` | *"it needs a photo of his, and his tap adds the reminder"* |
| `support` | `-TOPUP-2.md:47` | *"a real company, on a real account, with one card before the chat and one per offer"* |

**(b) Never driven on the desktop only — 14 rows.** The phone half of several of these
was driven on 2026-10-13; the desktop half was not, and
`FIELD-TEST-2026-10-13-DESKTOP.md:230` says why (*"The same dead end"*):

`memory-tab` (row 26), `memory-known` (29), `memory-saved` (27), `memory-waiting` (28),
`pinned-facts` (31), `memory-as-of` (37), `between-us` (32), `chat-tags` (40),
`sensitive-facts` (66), `memory-people` (30), `memory-learning` (34) — **plus
`forget-range` (41), `history` (39) and `history-search` (17)**, which the desktop
pass lists in the same BLOCKED group at line 230. That is **14 rows**, and line 230
is the citation.

**(c) The desktop-only rows a harness cannot open, still never driven — 3 rows.**
`work-tab` (101) and the desktop Brain window generally — `FIELD-TEST-2026-10-13-DESKTOP.md:229`,
and `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:45-49` (*"the tray icon… produces **no
readable menu**, so the **desktop Brain window could not be opened from a harness at
all**"*). `talk-to-type` (14) and `model-memory` (98) are the two further
`surface: desktop` rows the phone pass lists at `-PHONE-PASS.md:133` and `:135`.

**(d) Never driven anywhere, still — 4 rows.** `phone-watch` (81, *"there is **no
paired watch**"*, `-PHONE-PASS.md:145`); `rush-latch` (125, *"no row to open, and
driving it needs a turn carrying rushing text"*, `-PHONE-PASS.md:98`); `also-on-phone`
(85, *"the copy itself was **not** made (it writes into the owner's own Clock/Calendar)"*,
`-PHONE-PASS.md:97`); `live-extras` (13, *"it needs a Live session and, for most of the
extras, hardware this pass does not have"*, `-PHONE-PASS.md:101`).

**(e) `NOT-TESTABLE` for a reason that is not going to change — 10 rows.** `crisis-help`
(67), `home-status` (68), `calendar` (71), `weather-sky` (72), `email-read` (73),
`email-send` (74), `email-drafts` (75), `inbox-tidy` (76), `lights` (69), `locks` (70).
Their reasons are the page's own words, quoted at `FIELD-TEST-2026-10-12-TOPUP.md:117-122`
and re-read on 2026-10-13 at `FIELD-TEST-2026-10-13-DESKTOP.md:233`.

**The number to carry into the pass.** **Four items are unreachable and stay that way**
(§2.3a); **the desktop half of the memory and history group is 14 rows that a person
clears in one fingerprint** (§2.3b); **at least three desktop-only rows need a person
at the machine** (§2.3c); **four rows need hardware or a behaviour nobody can stage**
(§2.3d); and **ten are NOT-TESTABLE because the thing they talk to does not exist here**
(§2.3e).

### 2.4 Where the records disagree, said plainly

1. **The BLOCKED/NOT-TESTABLE split of the matrix's 82.** Line 21 says the top-ups left
   **9 BLOCKED and 10 NOT-TESTABLE**; the top-up's own section 5 header says
   **"BLOCKED or NOT-TESTABLE, with the reason (18)"** and its table holds **8 BLOCKED
   and 10 NOT-TESTABLE** (`-TOPUP.md:113-128`). **This plan does not pick a winner.**
   The top-up then blocked 4 more on the memory cause (`-TOPUP.md:113-116`) and
   `-TOPUP-3.md:76-85` blocked 9 more, so the later records have moved the group
   anyway. A pass should read the per-row verdict, not the totals line.
2. **`watch-with-me`: two records both claim to have driven the exact case that was
   owed.** `FIELD-TEST-2026-10-11-RESULTS.md:64-90` says *"Row 44, re-driven on
   2026-10-12… **The badge cleared**… roughly ten seconds after the stop"*; then
   `FIELD-TEST-2026-10-13-DESKTOP.md:50` says *"**The record's own honest limit was that
   the desk-side re-drive of a REAL frozen badge never happened**"* and re-drives it,
   measuring **16.3 s**. **Both passed and they agree on the outcome, but they disagree
   about what had already been done.** The next pass should treat the 2026-10-13
   measurement as the one with timestamps and not spend a third round on it.
3. **The `crash-notes` fold: two measurements, two answers.** `FIELD-TEST-HOW-TO-READ-THE-APPS.md:172-182`
   records *"**0 `crash`, 0 `Hang` in 2,073** after invoking the fold's own control and
   scrolling the page to its end - the fold's contents never entered the tree, opened or
   not."* `FIELD-TEST-2026-10-13-DESKTOP.md:88` records *"**fold open** … **1,985** …
   `crash`/`Hang` **6**"*. **The disagreement is the instrument, and the later record
   names it**: §2.3 (line 127) shows `scripts/fieldtest-desktop.ps1` looks up
   `[System.Windows.Automation.InvokePattern]::Pattern`, *"**No such types exist**"*, so
   *"the script reports `no clickable pattern on that element` for everything"*. **A
   pass must use the working instrument**, and the working one survives at
   `.dsh-scratch/wt-fieldtest-desktop/dshwork/uia.ps1` (verified present today, 9,978
   bytes).
4. **The phone's privacy switch: the brief and the device disagree, and the record does
   not pick a winner.** `FIELD-TEST-2026-10-13-PHONE-PASS.md:30-42` and §6 (lines
   171–237) record **three independent signals reading the switch as ON** (the summary
   line the code only adds when it is on, the row's own `checked=true`, and the app's
   own *"Loosen security"* prompt) against **one reading the other way** (the memory
   content was readable all pass). **The next pass must re-measure the switch first and
   the summary line second, and never treat one as proof of the other** (line 234).
5. **The feature list is 129 entries, not 128, and this plan confirms it.**
   `-TOPUP.md:14` reconciled the count to **128**; `FIELD-TEST-2026-10-13-DESKTOP.md:337-345`
   corrected that to **129** and this plan re-measured it: `python -B tools/check_feature_list.py`
   prints `ok 129 entries` (exit 0) and `git show origin/main:features/features.json`
   parses as a list of **129**.

---

## 3. The driving method for each item

Each row below gives **which app**, **which control or route**, **what to type or tap**,
and then the half that matters: **what a PASS looks like in observable terms** versus
**what would be a PARTIAL**. Where the honest way to drive something is the API, the
literal request is given. The harness is the one the records already proved:
**`uiautomator dump` on the phone, Windows UI Automation on the desktop** (2 methods 1
and 2), **the phone's notification record** (method 3) and **the backend's own state**
(method 4) to confirm the effect (`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:16-104`).

### 3.1 The items landed on `main` (§1a) — N1 to N10

**N1 — one Update control for both halves.** *App:* desktop.
*Route/control:* Settings → Updates → **"Update both halves"**.
*What to do:* press it, read the dialog, press **Cancel**.
*PASS:* the dialog appears and names the backend folder **by path**, says every file it
touches is copied into `_jarvis-backup-<date>` **in that folder**, says Jarvis is stopped
while it works, says which half goes first, and says what happens if the first half
fails; **Cancel changes nothing** — the backend folder's mtime and content list are
identical before and after.
*PARTIAL:* the button and the dialog exist but the run itself was not performed, or the
dialog appeared and any one of those five facts is missing. **A real run is the owner's
call, not a harness's** — it rewrites his live install.
*Cite:* PR #394's body, `docs/ONE-UPDATE-FOR-BOTH.md`.

**N2 — the interruption budget's raise reaches the backend.** *App:* either, then the
backend.
*Route:* `POST http://127.0.0.1:4719/api/attention/settings`, with the headers below.
*Literal request* (shape only — read the current values first with a `GET`, because
this writes a number into his settings file):

```
POST /api/attention/settings
{"per_day": <current+1>}
```

*PASS:* **HTTP 200** with an `ok`-shaped body, and the new number comes back on a
following read. The Brain's own card, raised from either app, must also stop answering
with the desktop's sentence *"Your PC's Jarvis does not have this setting yet - run
apply-patches.ps1 on the PC"*.
*PARTIAL:* the route answers 200 and the value does not change; or the card is read but
the write was not attempted. **Restore: put the number back and name the prior value.**
*Cite:* PR #404's body; `backend/test_attention_route.py` (54 checks, quoted in
`CHANGELOG.md`).

**N3 — the bar's face.** *App:* desktop.
*Control:* the far-left mark of the **Jarvis bar** window (`Jarvis`, the second window
of that name — the quickbar, not the HUD; `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:53`
warns there are **two** windows called `Jarvis`).
*PASS (what a harness can do):* the geometry — `#reactor` the 40 × 40 slot,
`#reactor-face` the frame **40 × 40**, and the face canvas's backing store **360 × 360**
(so the square picture is not squeezed). PR #402's own table gives those numbers before
and after.
*PARTIAL:* the geometry reads correct but **nobody has looked at the pixels** — *"there
is no vision provider on this machine"* (`FIELD-TEST-HOW-TO-READ-THE-APPS.md:24-29`);
or the numbers were not read at all. **Watching the face actually draw is in §4.**
*Cite:* PR #402's body, including its measured table.

**N4 — a switch found by the words on it.** *App:* phone.
*Control:* **Settings' own search box** *and* **Find anything** — two boxes, one index
(PR #391's body).
*What to type:* `Hide memory lists and chat history`.
*PASS:* **both** boxes offer the `Security / Lock and fingerprint settings` row, in the
form the app draws it. The pre-fix measurement is quoted in the PR: `settings=[] find=[]`
for five different wordings.
*PARTIAL:* one box finds it and the other does not — those are two indexes and the
record treats them as one defect, so half a fix is a PARTIAL.
*Cite:* PR #391's body.

**N5 — deleting a reminder that has already gone off.** *App:* phone **and** desktop.
*Control:* the *"Just went off"* row's own actions (drawn from `WENT_OFF_ACTIONS` in
`jarvis-desktop/src/coming-up.js:436` and `jarvis-client/.../net/Schedule.kt:119`).
*What to do:* create a short timer (60 s), let it come due, then press **Delete**.
*PASS:* the row disappears from *"Just went off"*, and
`GET /api/schedule?id=<id>` stops returning it; for the phone, the notification record
(`adb shell dumpsys notification --noredact`) agrees.
*PARTIAL:* Snooze works and Delete does not; or the row was deleted on one app only.
**This is the one row that needs the new APK** — `FIELD-TEST-2026-10-13-PHONE-PASS.md:149-169`
records that the installed build predates it and says *"A future pass should install
`jarvis-client-44ea3b7.apk` and drive the fired-reminder Delete **first**."* **Install
it before this row.**
*Record the observation `FIELD-TEST-2026-10-13-DESKTOP.md:300-304` already made and did
not diagnose:* a fired timer could **not** be deleted through
`POST /api/schedule/act {"id":"…","do":"delete"}`, which answered
`{"ok": false, "reason": "no_such_job"}` while the row was still in `schedule.db`.
**That is a lead for this row, not a diagnosis.**
*Cite:* PR #387's body; `FIELD-TEST-2026-10-13-DESKTOP.md:300-304`.

**N6 — the raise actions' card.** *App:* either.
*Control:* the Brain's **Interruption budget → raise** card, or the spending-limit
**raise_a_limit** card.
*PASS:* the card no longer carries `'classified': False` and no longer says
*"not classified, so treated as irreversible and outbound"*; it does not make the three
untrue claims PR #384's body quotes; there is no red **UNCLASSIFIED** pill and no
disabled swipe.
*PARTIAL:* the card is raised and readable but was not compared against the old
vocabulary. **A harness may read the card; a harness must not decide it**
(`FIELD-TEST-2026-10-13-DESKTOP.md:231`).
*Cite:* PR #384's body, which quotes the exact pre-fix payload.

**N7 — the second picture reader, and the black boxes.** *App:* desktop.
*Control:* the picture-reader switch (off by default), then attach a picture.
*PASS:* with the second reader on, a picture containing a visible secret comes back
with the secret **blacked out**, in the same way the first reader's path does — that is
the property `backend/jarvis_ocr.py`'s own docstring says the fallback could not
guarantee (PR #390's body).
*PARTIAL:* the switch turns on and reports its state, and no picture was attached; or a
picture was attached with nothing secret in it, which proves nothing about the blacking.
**Never attach a picture of his real screen or documents** — use something authored for
the test.
*Cite:* PR #390's body; `backend/jarvis_ocr.py`.

**N8 — "what can I change?"** *App:* either.
*Control:* the chat box. *What to type:* `what can I change?`
*PASS:* the answer's own count is derived from the settings tables and its rows are in
plain words, with a family row standing for several settings — the shape PR #365's body
tables (**`count` 13 → 43**, **rows 13 → 26**).
*PARTIAL:* the sentence is read and the count is not compared against the tables; or a
row in it names a setting the registry does not carry.
*Cite:* PR #365's body.

**N9 — a setting changed by asking, through the *model* path.** *App:* desktop.
*Control:* the HUD's own chat box (`#input`) and Send (`#send`) — the two controls a
person uses, the same way `FIELD-TEST-2026-10-13-DESKTOP.md:178` drove it.
*What to type:* a sentence the fixed grammar does **not** already cover, then read the
answer's own `X-Jarvis-Route`.
*PASS:* the route does **not** read `{"lane": "no AI model"}` — the model was asked and
it called the tool — and the setting really changed, verified against the live store
rather than against the model's own sentence about itself.
*PARTIAL:* the sentence is answered by the fixed phrase grammar
(`{"lane": "no AI model", "quick": "settings_bool"}`) — which is what happened to
every settings turn in the third pass (`FIELD-TEST-MATRIX-2026-10-11.md:190`, T12) and
is exactly the gap PR #405 addresses. **A PARTIAL here is the honest verdict for a
grammar-only answer; do not record it as a pass.**
*Cite:* PR #405's body (its own control: **0 of 21 requests called the tool before, 18
of 21 after** with the temperature pinned); `FIELD-TEST-MATRIX-2026-10-11.md:409`
(conversation-driven table).

**N10 — a loosening through that path still raises a card.** *App:* desktop.
*What to type:* *"turn on remembering sensitive topics automatically"*.
*PASS:* a card is raised (`"expires_in": 599` at the ten-minute ceiling), the setting
stays unchanged, and the card can be **DENIED** — the shape the third pass already proved
for the grammar path (`FIELD-TEST-MATRIX-2026-10-11.md:175`: `{"ok": true,
"id": "9749ddd28b2b", "state": "denied"}`, 0 waiting, the setting still `false`).
*NOT a PARTIAL — a FAIL:* the setting changes **without** a card. It is written here so
nobody writes it up as a partial.
*Cite:* PR #368's body; `FIELD-TEST-MATRIX-2026-10-11.md:175`.

### 3.2 The in-flight items (§1b) — N11 to N16

**None of these is on `main` today.** The rows are written so that when the PRs land, the
plan needs no new thinking — only a re-read of `gh pr list --state open`.

**N11 — the phone can ask the PC for a backup.** *App:* phone, then the PC.
*Control:* the phone's own **Back up now** (the control this PR draws).
*The literal flow, which is the whole point of the design:*

```
POST /api/backup/prepare     <- mints this run's code and WRITES NOTHING AT ALL
                               the code lives in the PC's memory for 15 minutes only
POST /api/backup/commit      <- THIS PC ONLY; refused before the body is read
                               writes the file WITH that same code
```

*PASS:* after **prepare**, the backup folder is **byte-for-byte unchanged** and the phone
draws the code **full-screen in four groups of five**; the run cannot be finished until
the **tick** is set; after **commit**, the file exists, it opens with the code the owner
kept, and `POST /api/backup/commit` **refused** when it was attempted from anywhere but
the PC.
*PARTIAL:* the phone shows the folder's state (last backup, which folder, how many kept,
the PC's own check of the newest file) and **no run was made** — which is a real reading,
and is not the feature. **Also a PARTIAL, deliberately:** *"Prove that a backup opens"* is
something the screen itself says it cannot do, because the code is only ever typed on the
PC. **Do not read that as a defect.**
*Route:* `GET /api/backup/status` names the folder by its **last segment only**
("Jarvis Backups") — *"a full path names his Windows account."* **A test must not print a
full path either.**
*Cite:* PR #408's body.

**N12 — one destination for both backups, and the owner picks it.** *App:* desktop, then
the command line.
*Control:* Settings → Backups → **"Choose a folder…"** (`bk-choose-folder`).
*PASS:* after choosing, a run of the weekly tool **with no `--dest`** lands its snapshot
in the folder just chosen — read from `folder` in `~/.openjarvis/backup.json` **at run
time, every run** — and `backup.json` itself is **not** rewritten by the tool, whose own
rule is that it *"never writes `backup.json` and never writes into `~/.openjarvis`"*.
*PARTIAL:* the picker changes the setting and the tool's destination was not re-read; or
`--dest` was used, which overrides the setting for one hand-run and therefore proves
nothing about the timer.
*Cite:* PR #407's body.

**N13 — a dead lane says so before the question.** *App:* desktop (bar, widget, HUD) and
phone (Home status line).
*How to produce the state honestly, without touching his scheduled lanes:* point the
backend at a port nothing is listening on — `OLLAMA_URL` is read at `jarvis_hud.py:74`
(PR #409's body) and the healthy lane here is **11436**, so a dead address is any closed
port — restart the backend, then read.
*PASS:* `GET /api/status` carries `"ollama": false`; the bar, the widget and the HUD each
draw the standing amber line *"The local model isn't running on your PC."*; the HUD
additionally draws its own host verdict *"The PC is answering - Jarvis' own model server is
not."*; and the phone's Home line reads **"Connected · Model not running"**. **All of it
before any question is asked.**
*PARTIAL:* the line draws but the app also says *"Jarvis isn't connected"* — the PR's body
is explicit that *"The two are never written in each other's words"*, and
`tests/lane-warning.mjs` pins it (*"it never says the link's words"*).
*The `false`-only rule is a second, cheap test:* **an absent field must draw nothing.**
*Restore: put `OLLAMA_URL` back and restart the backend; the lane itself was never
touched.*
*Cite:* PR #409's body (the table of what already existed and who ignored it).

**N14 — a device says what it is, and a label cannot make two rows read the same.**
*App:* both.
*Control:* **Devices**, on the phone's Settings page and the desktop's Settings window.
*What to do:* give two devices the **same label** and read both rows.
*PASS:* each row names the **kind** of device it is, and the two rows stay
distinguishable — the label alone does not decide the row.
*PARTIAL:* the kind is drawn and the collision was not attempted; or a label was set and
the row was not re-read.
*Cite:* PR #381's body.

**N15 — personal data gets a second copy taken by SQLite itself.** *App:* desktop.
*PASS:* a run of the snapshot tool produces a copy in which `agents.db` carries its
**6 tables**, and `traces.db`, `telemetry.db` and `digest.db` are **present** — against
the measured plain-copy result of **0 tables** for `agents.db` and three databases
**absent** (PR #403's own table). *PARTIAL:* the archive exists and its verification
step was not run, or one of the four is still short.
*Cite:* PR #403's body.

**N16 — the weekly snapshots' encryption, and the locker it refuses.** *App:* desktop /
command line.
*Control:* `tools/check_snapshots_encrypted.py` (read-only) and the weekly task's own
folder. *PASS:* every path under both folders reads encrypted, **zero plain**, and the
checker's `--self-test` proves its own reader; **and** the tool **refuses a NordLocker
destination outright** rather than writing plaintext into it (PR #406's measured
conclusion). *PARTIAL:* the folders read encrypted and the refusal was not driven.
*Cite:* PR #406's body; `tools/check_snapshots_encrypted.py`; `docs/SNAPSHOT-ENCRYPTION.md`.

### 3.3 The memory and history group on the **desktop** — the 14 rows of §2.3b

*App:* desktop. *Control:* the **Brain** window, which is the thing a harness cannot
open and a person opens in two clicks: *"open it from the tray icon, 'Open the Brain'"*
(`FIELD-TEST-2026-10-13-DESKTOP.md:229`).
**So this is a human-driven batch with an agent reading over UI Automation beside him.**

*PASS for each row:* the row is **offered in Find** on the desktop's own Settings search
and the Brain's own plate **draws its content** with no `Hidden.` gate — the shape the
phone pass records for its eleven (`-PHONE-PASS.md:112-117`).
*PARTIAL:* the plate draws and reads *"Hidden. Show asks Windows Hello first"*
(`FIELD-TEST-2026-10-13-DESKTOP.md:230`) — that is the gate working, not the feature
failing, and it is a PARTIAL with that reason written beside it.
*One decision the owner owes first:* the phone pass left the phone's switch in a state
the record **could not agree with itself about** (§2.4.4). **Re-measure the switch
before this batch**, or the batch tests the gate instead of the features.
*Cite:* `FIELD-TEST-2026-10-13-DESKTOP.md:230`; `FIELD-TEST-2026-10-12-TOPUP-3.md:68-92`.

### 3.4 The desktop-only rows needing a person at the machine (§2.3c)

`work-tab` — tray icon → **"Open the Brain"** → the Work tab. *PASS:* the tab draws its
own rows. *PARTIAL:* the Brain opens and the tab is not found.
`talk-to-type` — Settings, the row's own live line (*"Nothing listens for the
talk-to-type key."*). Turning it on needs **an approval card plus Windows Hello**.
*PASS:* the key is set, the row reports listening, and a spoken phrase lands as typed
text. *PARTIAL:* the row turns on and nothing was spoken — **the typing itself is his
voice and is therefore in §4.**
`model-memory` — the Model page's memory summary row. *PASS:* the summary draws.
*PARTIAL:* the row is read and the summary is not.
*Cite:* `FIELD-TEST-2026-10-13-DESKTOP.md:229`; `FIELD-TEST-HOW-TO-READ-THE-APPS.md:45-49`.

### 3.5 The rows needing hardware or a behaviour (§2.3d)

`phone-watch` (81) — the row is real and readable; the behaviour needs a **paired
watch**. *PASS is impossible here* → **NOT-TESTABLE**, reason: no paired watch
(`-PHONE-PASS.md:145`).
`rush-latch` (125) — needs a **turn carrying rushing text**. *Driving method if it is
ever driven:* put a text with a rush pattern in front of a turn and watch for the
warning. **A harness must not manufacture a rush at the owner.**
`also-on-phone` (85) — the control is drawn on the `COMING UP` plate; *the copy itself
writes into his Clock or Calendar*, so *PASS:* the copy lands in the phone's own Clock
app and the phone's notification record shows it; *PARTIAL:* the control and its own
words are read and the copy was not made (`-PHONE-PASS.md:97`).
`live-extras` (13) — needs a **Live session** plus OS surfaces. **NOT-TESTABLE** for
most of its parts (`-PHONE-PASS.md:101`).

### 3.6 The NOT-TESTABLE ten (§2.3e)

No driving method is written for these, deliberately. Each needs **a service or an
account this PC does not have**, in the app's own words (`-TOPUP.md:117-122`, re-read
2026-10-13): the calendar, the weather, unread mail, sending mail, drafts, inbox tidy,
Home Assistant lights, Home Assistant locks, and `home-status`. **Write each as
NOT-TESTABLE with its reason. Do not write any of them as a pass, and do not quietly
drop them.**

### 3.7 The `attention-budget` row (24) gets a second, specific pass

Row 24 is `TEST-VERIFIED ONLY` in the matrix and its PASS in the second pass was
*"read in full"* only (`FIELD-TEST-MATRIX-2026-10-11.md:127`). **N2 is the first time
the raise has ever worked from either app** (PR #404's body: *"raising the budget had
never once worked from either app on any install built from this patch set"*). **So
drive the raise itself, on both apps, and record that separately from "the card was
read."**

---

## 4. What no agent can reach

Named honestly, each with its reason and its verdict. **None of these is a pass, and
none may be quietly dropped.**

| what | why no agent can reach it | verdict to write |
|---|---|---|
| **His voice** — `wake-word` (4), `voice-check` (8), `interrupt` (11), `custom-voices` (9), `read-aloud` (5), `spoken-style` (6), `live` (12)'s session, `voice-training` (7) | *"a stand-in would test the stand-in"* — the print holds **his** voice only (a synthetic clip scores **−0.0414** against the **0.50** bar, which is the refusal working) | **NOT-TESTABLE by an agent**; the owner settles it in about two minutes (`FIELD-TEST-MATRIX-2026-10-11.md:184`, T6) |
| **The PC microphone's print** — `voice-training` on the desktop | there is **no `owner-desktop.json`**; the module falls back to the *phone* print, and its own docstring says *"a print trained on one scores the other lower"* | **NOT-TESTABLE** until he trains the PC mic (T7, line 185) |
| **His fingerprint / PIN** — the desktop-and-phone memory group (`memory-tab`, `memory-known`, `memory-saved`, `memory-waiting`, `pinned-facts`, `memory-as-of`, `between-us`, `chat-tags`, `sensitive-facts`, `memory-people`, `memory-learning`, `forget-range`, `history`), and `app-lock` (120) | *"these rows are not blocked by a preference - they are blocked by a **biometric gate**, and no authorisation can substitute for the finger on the sensor"* | **BLOCKED, reason: his fingerprint** (`FIELD-TEST-2026-10-12-TOPUP-3.md:87-92`) |
| **Windows Hello** — `big-model` (105), `talk-to-type` (14), `app-lock`, restoring a backup | turning it on is *"the owner's click through Windows Hello"* | **BLOCKED, reason: Windows Hello** (`FIELD-TEST-2026-10-13-DESKTOP.md:231`) |
| **His accounts** — `accounts` (113), `chatbot-money` (65), the four email rows (73–76), `calendar` (71), `lights`/`locks` (69–70), the cloud lane's round trip | *"the owner's accounts and keys - they are his"*; and for the cloud lane, *"a lane call returns **HTTP 401**, because the upstream key is absent"* | **NOT-TESTABLE / BLOCKED with that reason** (`-TOPUP.md:125-126`; PR #379's body) |
| **A paired watch** — `phone-watch` (81) | *"no paired watch"* | **NOT-TESTABLE** (`-PHONE-PASS.md:145`) |
| **The camera** — `live-camera` (47), `photo-reminder` (46) | the design needs the **12 GB card**, and `photo-reminder` *"needs a photo of his"* | **NOT-TESTABLE** (`FIELD-TEST-MATRIX-2026-10-11.md:98`; `-TOPUP-2.md:46`) |
| **His eyes on a window effect** — the bar's face actually drawing (N3), the Galaxy graph's picture, the **face picker**, the grey rectangles (#324) | **two separate reasons that both land here:** the *pixel* half of N3, and *"there is **no vision provider** on this machine"* for the drawn, not-text surfaces | **PARTIAL with that reason stated**, never a PASS (`FIELD-TEST-HOW-TO-READ-THE-APPS.md:24-29`, `:153-154`; `-TOPUP.md:161-173` for the grey frames) |
| **A real company and a real account** — `support` (59) | *"a real company, on a real account, with one card before the chat and one per offer"* | **NOT-TESTABLE** (`-TOPUP-2.md:47`) |
| **The tray icon and the desktop Brain window** — `work-tab` (101) and the whole desktop memory batch | *"A person at the machine with a mouse reaches it in two clicks; this harness cannot"* | **BLOCKED for a harness; the owner or a person at the PC settles it** (`FIELD-TEST-2026-10-13-DESKTOP.md:229`; `FIELD-TEST-HOW-TO-READ-THE-APPS.md:155-157`) |
| **A crisis** — `crisis-help` (67) | *"**not provoked.** Unchanged from the record and it stays that way: a field test has no business staging a crisis"* | **NOT-TESTABLE by choice** (`FIELD-TEST-2026-10-13-DESKTOP.md:232`) |
| **Anything the decision log gates for the owner's word** — e.g. loosening a privacy rule | the 2026-10-13 decision is recorded *"as a WEAKENING and it is written here as one"* and says what still protects it | **ask first; never loosen to make a test easier** (PR #411's body quoting `docs/DECISIONS.md:1941-2006`) |

---

## 5. The environment facts an agent will need

**Each line says whether this plan's author verified it today (2026-10-14, this PC) or
took it from a record. Verified facts name the command; record facts name the file and
line.**

| fact | verified today, or from the record |
|---|---|
| **The API is on `127.0.0.1:4719`.** | **Verified.** `Test-NetConnection 127.0.0.1:4719` → open. **An unauthenticated `GET /api/status` answers 403** — the address being up is not a licence, and the token is required. |
| **The token is sent as the header `X-Jarvis-Token`, and `X-Jarvis-Client: hud` goes on every request.** | **Verified in the tree** (the brief's other header name was checked): `scripts`/`backend/README.md:8276` uses `@{'X-Jarvis-Token'=$t; 'X-Jarvis-Client'='hud'}`; `backend/jarvis_hud.html:775` builds `{"X-Jarvis-Client": "hud"}`; and the working harness `call.ps1:51` sends both. |
| **The pairing token is in Windows Credential Manager under `Jarvis Backend/pairing token`, and the blob must be read as UTF-8 bytes, not UTF-16.** | **Both halves verified.** `cmdkey /list` lists `LegacyGeneric:target=Jarvis Backend/pairing token` (also `Jarvis Backend/DeepSeek API key` and `Jarvis Backend/chat history key`). The reading rule is written in `call.ps1:36-41`: *"The blob is UTF-8 BYTES, not UTF-16: the desktop's `token_store.rs` writes exactly the token's bytes… Reading it as UTF-16 doubles every byte and the header is refused with 401."* The same rule is in `FIELD-TEST-2026-10-13-DESKTOP.md:357`. **Never print, log or put the token on a command line.** |
| **Jarvis talks to the Ollama lane on port 11436, not 11434.** | **Verified.** `python -B tools/check_lanes.py` (read-only: *"starts nothing, stops nothing"*) printed **`up everyday port 11436 - up at context 196608 (qwen3.5:9b)`**, and the task is named `Jarvis Ollama - Everyday model (RTX 2060)`. **PR #409's body records that an agent got this wrong today and probed 11434**, which is why this line is here. **Note the trap:** `127.0.0.1:11434` also answers, with the same 17 model names — so *"it answered"* is not evidence that the right lane was asked. Ask `check_lanes.py`, not the port. |
| **The coding lane — port 11435 — is DOWN right now.** | **Verified.** The same run printed **`LANE DOWN coding port 11435 … WinError 10061`**, **`NOT HEALTHY - 1 lane(s) DOWN`**, **exit code 1**, and gave the command to fix it: `Start-ScheduledTask -TaskName 'Jarvis Ollama - Coding model (RTX 2080 Super)'`. **So any test that needs the second lane is BLOCKED until someone starts it, and starting it is a change to his machine.** |
| **The phone is reachable over adb, and the app is `com.jarvis.client`.** | **Partly verified, and the brief needs one correction.** `adb` is **not on `PATH`** in this session (`adb devices` → *"The term 'adb' is not recognized"*). The **binary is present**: `C:\Users\pcadmin\AppData\Local\Android\Sdk\platform-tools\adb.exe` (also reachable as `C:\Android\Sdk\...`), with `ANDROID_HOME` and `ANDROID_SDK_ROOT` both set to `C:\Users\pcadmin\AppData\Local\Android\Sdk`. **Call it by full path.** The package name `com.jarvis.client` is from the device itself: `FIELD-TEST-2026-10-13-PHONE-PASS.md:20` (`adb shell dumpsys package com.jarvis.client`). **This plan's author did not attach a phone**, so *"the phone is reachable"* is the record's claim, and the first thing a pass should do is `adb devices` and see a serial. |
| **`jarvis-client` builds locally — `./gradlew testDebugUnitTest --offline`.** | **Verified today, and it is the brief's most useful correction to the stale `CLAUDE.md`.** Run in this worktree with `JARVIS_BACKEND` cleared: **`BUILD SUCCESSFUL in 1m 47s`**, **exit code 0**, 26 actionable tasks. Java is `C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot`. `%USERPROFILE%\.gradle\caches` and `.gradle\wrapper\dists` both exist, and `jarvis-client/gradlew.bat` is present. **The worktree's `CLAUDE.md` (from `origin/main`) still says *"There is no local Android build in this container… GitHub Actions is the only compiler available"*** — that is the stale claim the brief warned about, and it is still on `main` at line 235. |
| **The desktop app's own instrument.** | **From the record, and the files are present.** The *working* reader is `.dsh-scratch/wt-fieldtest-desktop/dshwork/uia.ps1` (**verified present today, 9,978 bytes**) with `-Windows -Count -Text -List -Grep -Tree -Patterns -Expand -Click -SetValue -Scroll`; `call.ps1` (2,852 bytes), `hud-turn.ps1`, `watch-test.ps1` and three read-only `sched-*.py` are beside it. **`scripts/fieldtest-desktop.ps1` cannot invoke anything** — see §2.4.3. `.dsh-scratch/` is **gitignored**, so these are one clean-up away from being lost (`FIELD-TEST-HOW-TO-READ-THE-APPS.md:108`). |
| **The desktop build under test.** | **From the record.** The installed app is `C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe`, whose own log reads `===== Jarvis Desktop 0.2.0 starting =====`; the 2026-10-13 pass measured the exe at **2026-10-13 09:25:43** and its Settings page as *"Version 0.2.162 — the newest published"* while a **0.2.162 install failed with error status 1603 / Error 1730** (not an administrator). **After the updates this pass is about, all of that changes — re-read the version from the app before recording any verdict**, because a verdict without its build is not evidence (`FIELD-TEST-MATRIX-2026-10-11.md:49`). |

---

## 6. Restore-your-state rules

**Anything a test changes on his PC must be named here with its restore step, and
nothing may be loosened.**

### 6.1 The standing rules

1. **Cards are DENIED, never approved.** An approval card needs a person to decide it,
   and *"raising one and answering it are both the owner's"*
   (`FIELD-TEST-2026-10-12-TOPUP.md:129`). Denying is the restore step: it leaves the
   setting at its prior value and takes the card off the queue. The 2026-10-12 pass
   proved the shape: **`{"ok": true, "id": "9749ddd28b2b", "state": "denied"}`, 0
   waiting, the setting still `false`** (`FIELD-TEST-MATRIX-2026-10-11.md:175`).
2. **Every setting a test changes is returned to its prior value, and the prior value is
   written down before it is changed.** The 2026-10-11 pass did exactly this for
   `temporary-chat`: *"toggled to Off (it was On) - and **put back**, re-read as
   `toggled to On`"* (line 125).
3. **Timers, jobs and sessions the test creates are deleted, and the deletion is read
   back.** The 2026-10-13 desktop pass's own list is the template
   (`FIELD-TEST-2026-10-13-DESKTOP.md:241-251`): a 5-minute timer deleted via
   `POST /api/schedule/act {"id":"…","do":"delete"}` → `{"ok": true, …, "said":
   "Deleted."}`; a focus session stopped (`{"on": false, "state": "off"}`); a
   Watch-with-me session ended (`{"state": "ended", "on": false}`); **and the final read
   is `jobs: 0, todo: 0, lists: 0`.**
4. **Nothing is loosened.** No fingerprint prompt is answered, no privacy switch is
   moved, no Windows Hello prompt is completed, no approval is given. The 2026-10-12
   third top-up is the model: *"The switch was tapped once; the fingerprint prompt
   appeared; it was cancelled. The switch was then re-read: `checked="true"`. Nothing
   was loosened, and nothing needed restoring"* (`-TOPUP-3.md:96-98`).
5. **No window is left open that the test opened**, and no service is restarted.
6. **Nothing private is written into any record**: no message text, no memory content,
   no token, no address, no password, no full path that names his Windows account.

### 6.2 The specific changes this plan's items can make

| the item | what it changes on his PC | the restore step |
|---|---|---|
| **N1** (Update both halves) | runs `scripts/apply-patches.ps1` against his live backend and installs a desktop release | **A real run is the owner's call.** It copies every file it touches into `_jarvis-backup-<date>` in the backend folder **itself** — **name that folder in the record before the run**, and name the config file's own snapshot. **Never run `scripts/apply-patches.ps1` from a feature branch to test this**; the control runs the documented invocation, which is not the same thing as a harness invoking it. |
| **N2** (attention budget) | **writes a number into his settings file** | read the prior value first, write it back, re-read it. |
| **N3** (bar face) | nothing stored | none; the window's geometry is read, not changed. |
| **N4** (settings search) | nothing stored | none. |
| **N5** (fired reminder Delete) | a reminder he may care about is deleted | **create a throwaway reminder for this row; never the owner's own.** The 2026-10-13 phone pass tapped Delete on **his** live reminder `take my pills` and reported it (`-PHONE-PASS.md:108`, `:251`) — and the desktop pass recorded that **his repeating reminder `se80955f188` disappeared with no established cause** (`FIELD-TEST-2026-10-13-DESKTOP.md:253-264`). **Do not repeat that. Use disposable rows and name them.** |
| **N6** (raise card) | a card appears | **DENY it**; nothing else was written. |
| **N7** (picture reader) | the second reader is switched on (off by default) | **switch it back off and re-read.** Never attach his screen or documents. |
| **N8** (what can I change?) | nothing stored | none. |
| **N9 / N10** (settings by asking) | a cosmetic setting changes; a loosening raises a card | the value returns to its prior reading; **the card is DENIED and the setting re-read unchanged**. |
| **N11** (phone backup) | on the PC: **the `commit` half writes a file**, and the run needs the code kept | **the `prepare` half writes nothing at all** — read that back and confirm the folder is unchanged. If `commit` runs, **name the file created and the code's fate**; never print the code into the record. |
| **N12** (backup folder) | **moves where his backups land** | read the prior `folder` value from `~/.openjarvis/backup.json` first, and write it back if the test changed it. |
| **N13** (dead lane) | the backend is pointed at a dead address | **put `OLLAMA_URL` back and restart the backend.** Do **not** stop the scheduled lane task unless the owner asks — that is a change to the machine that outlives the test. |
| **N14** (device labels) | a device label is typed | set the label back to its prior text and re-read both rows. |
| **N15 / N16** (backups) | **writes files into his backup folders** and reads the EFS state | the snapshot tool writes **into** the folder he chose; **name every file created**. The EFS state is a machine setting with nothing to restore (`check_snapshots_encrypted.py --self-test` is the verification, not a change). |
| **The phone's privacy switch** | **nothing** | **nothing — no agent may move it.** If a pass needs it off, the owner turns it off and the pass records that he did (`-PHONE-PASS.md:236-237`). |
| **The coding lane (11435)** | starting it is a change to his machine | **BLOCKED, not a test.** If it is started, say who started it, and know that the everyday lane's task is a separate one. |

### 6.3 The one thing that was already lost, and must not be "restored" by guesswork

`FIELD-TEST-2026-10-13-DESKTOP.md:253-264` records that **the owner's repeating reminder
`se80955f188` (`07:00 tomorrow`, `every weekday (Monday to Friday) at 07:00`) vanished
during that pass, that *"what removed it is NOT established"*, that the row was
**hard-deleted** from `schedule.db` rather than marked done, that a **published
hypothesis about it was tested and disproved** (§7, lines 282–298), and that the pass
*"was told not to touch his data again without a decision, so nothing was recreated."*

**This plan inherits that instruction.** The next pass must **not** recreate that row,
must **not** invent a cause for its loss, and must **not** treat "the count is 0" as
evidence about it. If it wants to look, it reads — read-only — and says which file it
read.

---

## 7. The order to drive it in

**The order matters and it is not arbitrary.** Each step is placed where it is because
of something a record measured.

1. **Install the new builds first, all three, and read back each one's own version.**
   `FIELD-TEST-2026-10-13-PHONE-PASS.md:149-169` is the reason: the pass that mattered
   could not drive the one row it was for because **the APK was a day old**, and it says
   *"A future pass should install `jarvis-client-44ea3b7.apk` and drive the
   fired-reminder Delete **first**."* The desktop's own 0.2.162 install failed with
   **1603 / Error 1730** on 2026-10-13 (`-DESKTOP.md:20`), so **check the installer can
   actually replace the app before planning around a new desktop build.**
2. **Re-measure the phone's privacy switch**, before anything in the memory group, for
   the reason in §2.4.4. **This is a one-tap answer for the owner and it decides whether
   §3.3 is a feature test or a gate test.**
3. **The server-side and route-level rows, by `curl`, before any UI** — N2, N6, N8, N9,
   N10, and (once they land) N11 to N16. These are cheap, they are read-and-write on state
   that can be put back, and they tell you whether the backend you just updated actually
   carries the work. **`backend/run_suites.py` must never be run bare** (the standing
   instruction): drive the routes, and let CI run the suites.
4. **The desktop UI half, with the working instrument** (`uia.ps1`, not
   `scripts/fieldtest-desktop.ps1`): N1, N3, N7. **The desktop comes before the phone**
   because a Tauri generation bump rode along with this batch (§1c) and a regression there
   is the one that would make everything else confusing.
5. **The phone half** (`uiautomator dump`, `input tap`, `input swipe`, `input text` with
   `%s` for a space — `-PHONE-PASS.md:243`): N4, N5, N13's phone line, and N11 once it
   lands.
6. **The human batches last**, because they need the owner and they need his consent to
   be asked for: §3.4 (the desktop memory group), §3.5 (the tray and the Brain), and
   the four voice/fingerprint rows of §4.
7. **Write the record as you go, in the shape the existing ones use**: the row's id, the
   verdict word, the build, the raw evidence quoted, and — new since the third pass —
   **a `who can settle it` column** (`FIELD-TEST-MATRIX-2026-10-11.md:159`). A row
   without a "who" is a row nobody can finish.

---

## 8. What a PASS is, and what is never one

Stated once, plainly, because the whole pass stands on it.

- **PASS** — the feature was **driven on real hardware**, in the shape a person would
  drive it, and the expected thing was observed, quoted. *"Suites passing is not field
  testing"* (`FIELD-TEST-MATRIX-2026-10-11.md:32`).
- **PARTIAL** — some of it was driven. **Say exactly which part, and why the rest was
  not.**
- **BLOCKED** — could not be reached because something else stands in the way. **Name
  the blocker and the person who clears it.**
- **NOT-TESTABLE** — needs hardware, a service, an account or an instrument this machine
  does not have. **"The thing it talks to does not exist here" is a different answer
  from "I could not reach it", and the record must say which one it is**
  (`FIELD-TEST-2026-10-11-RESULTS.md:103`).
- **FAIL** — driven and the wrong thing happened, with the evidence.

**And the four traps the records already paid for, so this pass does not pay again:**

1. **A search is not a claim about `main`.** `git grep` answers *"what does my checkout
   say"*; `git show origin/main:<path>` answers about `main`. Two readers once
   *"independently confirmed"* the same wrong thing with the same wrong instrument
   (`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md:158-171`).
2. **A collapsed fold is invisible to a string enumeration.** *"'The words are absent
   from N strings' is a claim about the enumeration until the fold has been opened"*
   (`:172-182`) — and the 2026-10-13 pass showed the fold only opens with the **fixed**
   instrument (`-DESKTOP.md:118-139`).
3. **A screen you cannot read is not a screen you have tested**, and **"drawn, not
   text"** is a finding, not a gap (`FIELD-TEST-HOW-TO-READ-THE-APPS.md:11-14`).
4. **A verdict without its build is not evidence** (`FIELD-TEST-MATRIX-2026-10-11.md:49`).

---

## 9. What this plan could not settle, said plainly

1. **The BLOCKED/NOT-TESTABLE arithmetic of the matrix** — §2.4.1. Two files give
   different splits of the same 82. This plan reports both and does not choose.
2. **Whether the phone's privacy switch is on** — §2.4.4. The record could not make its
   own two readings agree, and neither can this plan.
3. **`features.json` is called "three byte-identical copies" in the brief, and that is
   right about the list and wrong about the files.** There are **four files named
   `features.json`** in the tree — `features/features.json`,
   `jarvis-desktop/src/features.json`,
   `jarvis-client/app/src/main/assets/features.json` and
   `jarvis-desktop/src-tauri/capabilities/features.json` — and the first three share one
   SHA-256 while **the fourth is a different document entirely**: a Tauri capabilities
   file, a JSON **object with 5 keys**, not a feature list. `tools/check_feature_list.py`
   already says so in its own words (`ok the three copies of features.json are
   byte-identical`), so the brief's *"three"* is the checker's number and the fourth file
   is not a copy. **Verified here, today.**
4. **`docs/README.md`'s count is 379, not 378.** The stale root `CLAUDE.md` uses *"377
   to 378"* as its worked example; the rule it illustrates is what matters, and the
   number to bump is whatever `tools/check_docs_map.py` prints. **Measured today on
   `origin/main`: 379 documents.** This plan adds one, so the bump is **379 → 380**.
5. **No verdict is recorded in this file.** Everything in §1 and §2 is a citation;
   everything in §5 is a measurement of the machine, not of a feature. **The pass that
   follows this plan is the one that measures.**
