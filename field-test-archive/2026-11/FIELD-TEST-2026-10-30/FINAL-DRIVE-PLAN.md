# FINAL DRIVE PLAN — after Final-1's desktop build and client-latest APK are installed

**Written 2026-10-30 ~19:25 PDT by the field-test subagent** (read-only prep; nothing driven while
writing this). Purpose: make the last field-test pass fast, complete and honest. Every item below
says **precondition → exact steps → evidence → PASS criteria → honest fallback → who can do it**.

**Authority.** Gemini's F1–F6 rulings
(`C:\Users\pcadmin\Downloads\gemini_rulings_f1_to_f6_field_test_gaps_2026_10_30.md`) authorize
agent-driven, state-restoring UI work (widget re-pick, reversible archive, To-Do add/delete, the 93
SCREEN rows) and owner-gated work (Show/fingerprint, F1 app-control approvals, F2 card Deny, F6
update run). This plan only arranges that work.

**Hard rules for the whole run.** Never print the pairing token (read it into `$t` only; the runbook
pattern is `$t = & $bpy -B jarvis_token_store.py show` then `$h=@{'X-Jarvis-Token'=$t;'X-Jarvis-Client'='hud'}`);
never answer an approval card (the owner does; "Deny" on a harmless test card is the one allowed
exception, F2); restore every state touched; no installs beyond the planned APK + desktop update; no
push/merge. **The live audit log is UTC-dated** — `jarvis_framework.py:650-658` names it
`jarvis-<UTC date>.jsonl`, so after **17:00 PDT** it is the *next day's* file (e.g.
`jarvis-2026-10-31.jsonl`); always resolve the file by UTC date at run time.

**Baselines measured while writing this plan (2026-10-30 18:44–19:25 PDT):**

| fact | value |
|---|---|
| `origin/main` | `0f37fd93e` |
| Final-1 branch | `feat/phone-jobs-and-final-repairs-2026-10-30`, head **`65473fdba`** (already merges `fix/widget-repaint-2026-10-30` `b3bf81530`) |
| Desktop installed | **0.2.368** (`FileVersion`/registry), exe mtime 10/30 11:42:52 — **owner must launch it; this agent session cannot host a GUI app** (pass5 evidence) |
| `desktop-latest` | 0.2.368, targetCommitish `bd302311…` (expected next: **0.2.≥369**, exact number from the release title — never assume) |
| `client-latest` | 0.2.3285 / main `263ea0d` (expected next: the Final-1 build, **≥0.2.3286**) |
| Live backend | running, python pid 48324, listening `127.0.0.1:4719` + `100.75.21.228:4719`; live `jarvis_gate.py` repair state read-only via `tools/repair_live_backend_gaps.py` (dry run) |
| Phone | `f0a5b32b` connected, `com.jarvis.client` 0.2.3261 / versionCode 1000003261, paired 10 Oct |
| Launcher card now | `Jarvis widget 2` reads **"No widget chosen"** |

**Evidence convention for this pass:** `.dsh-scratch/FIELD-TEST-2026-10-30/pass6/` for every dump,
JSON snippet and hash; then append a dated section to
`.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md` with PASS/PARTIAL/BLOCKED stated as measured.

---

## 0. Owner time vs agent time — the order that minimises owner minutes

**Agent-only (do before the owner session; no owner needed):**
1. Verify the releases exist and record versions/commits (read-only `gh release view`).
2. Install the new `client-latest` APK with `adb install -r` (pairing survives; record
   versionName/versionCode/firstInstallTime). If `INSTALL_FAILED_UPDATE_INCOMPATIBLE` → **stop**, the
   owner must decide (release notes say do not uninstall without telling the session).
3. **Item 1 (widget repaint)** — re-pick + launcher dump; no owner, no biometric.
4. Pre-flight A/B/C for the update run (release assets, pinned worktree, fallback cache) per
   `UPDATE-RUNBOOK.md` §1–§3.
5. Prepare the phone for the owner's one Show: open the app, know the exact taps for items 6 and 4;
   keep the screen awake (do not lock).

**Owner-present session, single sitting (~12–15 min):**
1. **Launch Jarvis Desktop** and leave it open (1 min) — required for the F6 PRE baseline (Jarvis
   must be running) and everything desktop-side.
2. **Item 7 (update round trip)** first: agent takes PRE-FLIGHT D, owner runs the one-line updater
   from the pinned worktree (~4 min, SmartScreen if it appears), agent takes POST (§5 F6) — the app
   reopens itself at **0.2.≥369**, which the later items need.
3. **Item 8 (desktop Calendar)** with the new build open — agent runs the one-command harness
   (1 min, no owner if UIA attaches); otherwise the owner reads the panel and the agent records it as
   OWNER-VISUAL.
4. **Item 2 (card timer)** on the new desktop build: agent raises the harmless card and reads the API
   twice; owner glances at the desktop bar's countdown twice and says it is counting (~2 min), then
   the card is DENIED (agent can do it; owner may tap Deny on the phone instead).
5. **One Show + fingerprint** (~20 s) — agent immediately drives **item 6** (archive round trip,
   Galaxy picture, the 10 hidden rows) **and item 4's History half** in that same unlocked window.
6. **Item 5 (app control, F1 five guards)** — owner toggles Android Accessibility + allow-list Clock,
   then approves once and denies once; agent raises the requests and reads evidence (~5 min).

---

## 1. Widget repaint — matrix row 21 (`widgets`) → PASS

**Precondition.** Final-1 merged; `client-latest` APK built from it (contains
`b3bf81530 fix(widgets): keep the seven home-screen widget classes distinct in the release APK`,
merged at Final-1 head); APK installed on `f0a5b32b`; the saved widget `w7dbe0ba0ae` ("Next
Reminders") still on the PC (`C:\Users\pcadmin\.openjarvis\widgets.json`).

**Why it should work now.** R8 had merged the seven `GlanceAppWidget` subclasses into two classes
(`Ljd2;` for the three board slots, `Lvo;` for approval/quick-link/calendar) in the released APK;
Glance finds a widget's ids by the widget class **canonical name**, so the merged classes made every
board card repaint with the last slot's widget — the measured cause of "Jarvis widget 2 still says
No widget chosen". The fix adds **8 `-keep` rules** in `jarvis-client/app/proguard-rules.pro`;
`R8SourcePinTest` fails if any rule is removed.

**Steps.**
1. PRE dumps: `adb -s f0a5b32b shell uiautomator dump /sdcard/w0.xml` + `adb pull` → launcher
   (`adb shell input keyevent 3` first) showing `No widget chosen`; `adb shell dumpsys appwidget`
   saved whole.
2. Launch app → **Brain** → `Money and time` → `WIDGETS` → Open → slot **"Jarvis widget 2"**.
   While the lists are hidden the saved widget's name shows as `Widget 1`; select it (if already
   selected: select `Nothing`, then `Widget 1`, to force a real write), then tap **"Put it on my home
   screen"** once. Record every tap coordinate + the plate dump.
3. HOME, wait 5–10 s, dump the launcher again.
4. If it still says "No widget chosen", capture the fallback bundle (below) and stop — do not repeat
   blindly.

**Evidence.** `pass6/widget-before.xml`, `widget-plate.xml`, `widget-after.xml`,
`appwidget-before.txt`, `appwidget-after.txt`, app version lines, `client-latest` release
title + commit, and `git merge-base --is-ancestor b3bf81530 <apk commit>` = 0 (the fix is in the
installed binary).

**PASS.** The launcher card inside `content-desc="Jarvis widget 2"` shows **"Next Reminders"** /
**"Coming up"** (hidden-words state may replace the reminder lines with "Hidden - open Jarvis to see
it." — the title is the PASS evidence), not "No widget chosen". → Row 21 **PASS**.

**Honest fallback.** If it still shows "No widget chosen": record **PARTIAL** with (a) whether the
plate shows slot 2 mapped and the PIN button present (proves the app-side preference), (b) `dumpsys
appwidget` bindings, (c) installed version/commit + ancestry result, (d) a bounded
`adb logcat -d | grep -i 'glance\|appwidget\|jarvis'`, and (e) the APK's own classes if
`dexdump`/`apkanalyzer` is available (`adb shell pm path com.jarvis.client` → pull → dexdump; the fix
commit did exactly this and showed the merged `Ljd2;`/`Lvo;` names). That bundle names the next bug
precisely instead of a vague retry.

**Who.** Agent — no owner, no biometric (F3 authorized).

---

## 2. Card timer — F2/Q5 (harmless card, countdown, DENY)

**Precondition.** Final-1 merged; the live backend repair for the timer is applied (the SELECT must
read `created,raised,waited_until` — `jarvis_gate.pending()`; dry-run
`python -B tools/repair_live_backend_gaps.py --backend-path "<live>"` says `ok timer: already
present`); desktop updated to **0.2.≥369** and **running** (owner launched it; this agent session
cannot host GUI); phone on the new APK; the live check (`/api/version`) answers.

**Steps.**
1. PRE: record desktop `FileVersion`/`ProductVersion`/HKCU `DisplayVersion`, phone
   `versionName`, and `GET /api/pending` (token into `$t`, never printed) — expect no waiting card.
2. Raise ONE harmless card: type in the phone chat **"turn on remembering sensitive topics
   automatically"** (the documented settings-turn route: it raises a loosening card and changes
   nothing until answered; measured precedent `.dsh-scratch/settings-turn-test-report.md` §2.1).
   Alternative if the model path is needed: the desktop's Settings → Security switch — owner's click.
3. Immediately `GET /api/pending` twice ~5 s apart; quote each row's **`expires_in`** (measured
   precedent: 599 → decreasing). Save the two JSON snippets (id + expires_in only — they contain no
   private text).
4. Desktop bar (owner looks, or agent UIA if it can attach): read the countdown words **twice ~10 s
   apart**, quote verbatim and check the second is smaller. The 0.2.368 source's wording is
   `"M:SS left to decide, then Jarvis refuses it by itself."` (`jarvis-desktop/src/jarvis-link.js:334-341`);
   the runbook's newer-build expectation is `14m 59s left` / last minute
   `42s left — under a minute to decide.` — **record what the build actually shows; do not
   transcribe the expectation**.
5. Phone: `uiautomator dump` of the approval card; expect **`EXPIRES IN`** + `mm:ss`
   (`jarvis-client/.../ui/approval/ApprovalCard.kt:941-965`).
6. DENY it: `POST /api/deny` `{"id":"<id>","by":"hud"}` with `$h` headers, or tap **Deny** on the
   phone (then the body carries `"by":"phone"`). Quote the response (`{"ok":true,...}`) and the next
   `GET /api/pending` (card gone).
7. Audit: read the UTC-dated `C:\Users\pcadmin\.openjarvis\logs\jarvis-<UTC-date>.jsonl` for the
   decision event (`gate.decided` / `gate.denied`) and quote it.

**Evidence.** `pass6/card-pending-1.json`, `card-pending-2.json`, `card-deny.json`,
`card-phone-expires.xml`, desktop version triple, quoted desktop countdown words (owner or UIA),
audit line.

**PASS (Gemini F2).** All six: one harmless card raised; `expires_in` present in `/api/pending`; two
monotonically decreasing desktop countdown reads; phone shows `EXPIRES IN`; DENY answered; the card
is gone afterwards. Any missing element → **PARTIAL** (say which one and why).

**Honest fallback.** If `/api/pending` rows have no `expires_in` → timer repair not live → PARTIAL
(deploy gap). If the desktop bar cannot be observed → PARTIAL; do not infer the words from source.
**Who.** Agent: raise/read/deny (token in a variable). Owner: launch the desktop and read the bar
(or authorise the agent's UIA attempt).

---

## 3. Phone jobs half (Long Fuse) — start / park / No / Allow once

**Precondition.** Final-1 merged (phone half `d7d41c3e3`, branch
`feat/phone-jobs-2026-10-30`); the **live backend carries the jobs routes** from #1000
(`POST /api/jobs`, `POST /api/jobs/answer`, `GET /api/jobs` with `grants`, `ticking`,
`status.handlers`); new APK installed; `ticking: true`; the one production handler is
**`watch_github`**. (If the PC is older, the phone deliberately says which patch it needs — record
that sentence, do not call it an empty queue.)

**Steps.**
1. `GET /api/jobs` → save the body; quote `ticking`, `status.handlers` (expect `watch_github`) and
   `grants` (empty).
2. Phone: **Brain → Work → Background jobs** → "Start a background job" → choose **`watch_github`**,
   type `watch the jarvis repo`, tap **Start**. Dump; the job row appears.
3. Watch it park: `GET /api/jobs` until the row is `waiting_approval` (audit `jobs.created` then
   `jobs.waiting {id, action}`); the phone shows the action's own words, **"One answer, and it counts
   for this job only"**, and exactly two buttons: **`No`** (left) and **`Allow once: <action>`**
   (right). Dump the parked row + buttons.
4. Answer **No** → dump; `GET /api/jobs` → the grant is decided (`state: denied`), the job is
   stopped/failed, no capability written (audit `jobs.grant_decided`, `jobs.finished` with its
   state). Nothing runs.
5. Start the SAME job again → it parks again with the same grant (a refusal left no standing rule).
6. Answer **`Allow once`** → `GET /api/jobs` → grant `state: granted` and spent; at the next tick the
   job proceeds (audit `jobs.capability_granted`, `jobs.tick`, and `jobs.finished` when it ends);
   **one grant / one job / one use** — no second grant appears for the same action, and the action is
   not offered twice.
7. Optional (cheap): confirm a second, different job cannot see the first job's grant (grants are
   joined by `job_id`).

**Evidence.** `pass6/jobs-before.json`, `jobs-parked.json`, `jobs-after-no.json`,
`jobs-allow-granted.json`; phone dumps `jobs-start.xml`, `jobs-parked.xml`, `jobs-after-no.xml`,
`jobs-after-allow.xml`; audit lines quoted from the UTC-dated JSONL: `jobs.created`, `jobs.waiting`,
`jobs.grant_decided`, `jobs.capability_granted`, `jobs.tick`, `jobs.finished`.

**PASS.** Both paths observed end-to-end with the API bodies and the audit lines: **No** stops the
parked job with nothing run and no rule left; **Allow once** grants exactly one use and the job
proceeds. Any missing half → PARTIAL with the missing half named.

**Honest fallback.** Older backend → the phone's own "which patch this PC needs" sentence → record it
and mark **BLOCKED (server side)**. `watch_github` is wired but historically unproven against GitHub
(`.dsh-scratch/JOBS-2026-10-30/REPORT.md` §6) — if the grant or the job's own run errors, that is a
finding, not a pass. **Who.** Agent (phone taps + reads); the grant answer *is* the permission
decision and is explicitly pre-authorized for this pass.

---

## 4. Phone History / More simplification walk-through

**Precondition.** New APK installed (Final-1 commit `d8c4c1608`, branch
`feat/phone-simplify-2026-10-30`). The History **list content** needs the Show-unlocked window (item
6); the More sheet, Modes, Quick note and the History chrome (headers/buttons) do not.

**Steps and exact expectations** (`PHONE-SIMPLIFY-2026-10-30/REPORT.md`; PR-body §2):

A. **More sheet** — Home → **More**: expect at most five doors + Close:
   `New chat`, `Photo`, `Attach a file`, `Modes`, `Quick note`, `Close` (a conditional
   `Notifications` row makes six only when captured phone notifications exist — record which state
   was seen). Verify **`Earlier chats` is gone**, **`Pinned messages` is gone from More**, **`Jarvis
   Presets` is gone from More**. Tap **Modes** → sub-sheet `Think` / `Coach this` / `Incognito` +
   `Back`/`Close` (same words, gates and flags; three taps now, by design). Back; tap **Quick note**
   → its entry opens (unchanged, last row before Close) — **dismiss without writing**.
B. **History chrome** — Home → **History**: header shows the title + **`Pinned`**, `New chat`,
   `Refresh`; **ONE filter row** = the owner's tags as sideways-scrolling chips + a **`Filters`**
   button (a dot / TalkBack count when a filter is on); the old three chip rows are gone. Tap
   **Filters** → sheet holds: conversation kinds (`All chats`, `Just chats`, `Live only`, `Support
   chats`, `Chats with other AIs`, `Comparisons`), **`Archived`**, the full tag list incl.
   **`Untagged`**, the **Tags** editor, and **`Forget a time frame…`**. Pick one kind + one tag and a
   tag chip to prove they still combine; confirm the Filters dot/count reflects it; then clear all
   filters (restore the pre-test view). Tap **`Pinned`** → the same `PinnedScreen` opens; back.
C. **Large-text crowding check** (the one thing the branch report flags as unseen): temporarily set
   the phone's font size to the largest (Settings → Display → Font size; preview it via
   `settings get system font_scale` → record BEFORE, set Largest, AFTER, then restore the exact
   BEFORE value). Open History and More; dump/screenshot; check the History header's three quiet
   actions (Pinned/New chat/Refresh) beside the title, the single filter row, and the five More rows
   for clipping/overlap. Record any crowding precisely (the report says moving Pinned to the filter
   row is a one-line fix if it crowds).

**Evidence.** uiautomator dumps per screen (`pass6/history-*.xml`, `more-*.xml`, `modes.xml`,
`quicknote.xml`), quoted labels, the before/after font-scale values, filter-combination dump, the
pre/post restore proof.

**PASS.** Every moved control is found where designed, opens exactly its old destination with the
old words/gates; the three retired More rows are absent; More ≤5 doors (+conditional
Notifications); Modes one tap deeper; Quick note unchanged; and at the largest font nothing clips or
overlaps (or the exact crowded element is named as a finding).

**Honest fallback.** Any missing/misplaced control → PARTIAL/FAIL with the exact dump, never
"looks fine". The History tag/filters sheet cannot be read while the lists are hidden — if the Show
window was missed, do A only and mark B/C as **BLOCKED (needs Show)**.
**Who.** Agent (all of A/B; font-size change needs the restore step, so agent if authorised, else
owner).

---

## 5. App control — F1's five guards (owner-gated)

**Precondition.** Live backend `[app_control] enabled = true` (the already-executed (b) live edit on
pid 48324) and Jarvis restarted; **Android Accessibility ON for Jarvis**; **allow-list exactly ONE
harmless app — Clock** (or Android Settings; never a browser, email/chat, password or finance app);
desktop open (owner) so the card can be approved with Windows Hello; phone on the new APK.

**Steps (F1's five guards, in order).**
1. **Allow-list one app only**: Settings → **App control** → `Apps Jarvis may act in` → add
   **Clock**. Dump proof: exactly one app; the bank/password/SMS refusals still refuse.
2. **1-step positive proof**: ask (phone chat, typed) *"open Clock and tap Timer"*. Expect: masked
   snapshot → ONE-step local plan → ONE **`change_own_config`** card naming the step and the model →
   **owner approves** (fingerprint/Windows Hello) → exactly ONE step executes → screen re-checked.
   Dump the card and the result; quote the audit rows.
3. **Deny proof**: second request (*"open Clock and tap Stopwatch"*) → **owner taps Deny** → verify
   **zero phone action** (no step event, screen unchanged).
4. **Pre-card refusal proof**: request a non-allow-listed app (*"open Chrome and search for cats"*) or
   a forbidden verb/field (password/delete/send) → the PC must refuse **before any card is raised**.
   Record the refusal sentence and the absence of a card in `/api/pending`.
5. **Stop proof**: start a request that would run a step; while it is running, tap **Stop** on the
   phone plate (`AppControlPlate.kt:268`, contentDescription **"Stop Jarvis"**) → the run halts
   immediately; no further step events.

**Evidence.** Phone dumps of the plate/card/step result (`pass6/appcontrol-*.xml`); the card's exact
step words; audit rows from the UTC-dated JSONL: `app_control.requested`, `app_control.planned`,
`app_control.step` — each carrying **`app` + `verb` only** (`audit_detail()` in
`jarvis_app_control.py:735`: *"The owner's typed text and the screen's words never go in the audit
log"*); grep the audit file for the typed sentence and the screen words to prove they are **absent**;
the deny refusal row; absence of a card for guard 4; the stop event.

**PASS.** All five guards observed with their evidence, and the audit log contains only
`app`/`verb` (no typed text, no screen words). Any guard missing → PARTIAL with the guard named;
accessibility/allow-list not set → **BLOCKED (owner)**.
**Who.** Owner: enables Accessibility, adds Clock, approves once, denies once, watches Stop.
Agent: raises every request and reads all evidence.

---

## 6. History archive + Galaxy picture + the 10 hidden-memory rows — after ONE owner Show

**Precondition.** New APK installed; the phone's hidden-memory gate is up
(`Hidden. Tap Show and confirm it is you.` visible in History / Brain → People and things); the owner
is present for the one Show.

**Steps (all in ONE unlocked window — do not let the screen lock or the app be backgrounded).**
1. **Owner taps `Show` + fingerprint/PIN once** (History or Brain → People and things).
2. **Row 39 archive round trip**: History → pick ONE existing chat (prefer the `hello` test chat;
   record its id/name from the row) → its overflow menu → **`Archive`**; the audit must record
   `history.archive {"archived": true}`. Open the **Archived** view (now inside the Filters sheet,
   item 4) → dump the chat present there. Then overflow → **`Unarchive`**; audit
   `history.archive {"archived": false}`; dump the chat back in the ordinary list. Restore = no chat
   left archived; verify `Archived` is empty again.
3. **Row 130 Galaxy picture** (read-only): Home → **`The Galaxy →`** → the PEOPLE AND THINGS plate now
   draws the picture. Dump and record: the dot nodes (`content-desc` = `Entities.galaxyNameLine`),
   the band/list, the `Showing {n} of {total}` cap line at 48 names. **Tap one dot** → that name's
   read-only facts/connections view → `Back to the list`. Nothing is created/edited/merged/dragged.
4. **The 10 hidden-memory rows, if quick** (open each, read its content, dump): matrix rows
   **27** `memory-saved`, **29** `memory-known`, **30** `memory-people`, **31** `pinned-facts`,
   **32** `between-us`, **34** `memory-learning`, **37** `memory-as-of`, **40** `chat-tags`,
   **41** `forget-range`, **66** `sensitive-facts`. PASS per row only if its content is visible and
   read; row visible but not exercised = PARTIAL.

**Evidence.** `pass6/archive-before.xml`, `archive-menu.xml`, `archived-view.xml`,
`archive-restored.xml`, `galaxy-picture.xml`, `galaxy-facts.xml`; the audit lines quoted from the
**UTC-dated** JSONL (tonight that is `jarvis-2026-10-31.jsonl`): `history.archive` **true → false**
with the same id; the `Showing N of M` line; each hidden-row dump.

**PASS.** `history.archive` `true → false` recorded in the UTC-named audit file **with** the Archived
view showing the chat and the restored list; Galaxy picture drawn and a dot opened its existing
facts view (row 130 PASS); each hidden row PASS/PARTIAL as read.

**Honest fallback.** No Show → **BLOCKED** (say exactly which gate text was on screen). Audit lines
missing → PARTIAL (record the dumps; check whether audit logging is enabled — `[logging] enabled`
in the live framework config — never invent the line). **Who.** Owner: one Show (~20 s). Agent:
everything else, fast, in the same window.

---

## 7. Update round trip — F6 (owner runs the updater; agent measures)

**Precondition.** Final-1 merged; desktop release **0.2.≥369** published with all assets; a **pinned
detached worktree at exactly the release `targetCommitish`** (this is what proves #1010's ancestry
fix); fallback installers cached (§3 C1/C2); Jarvis **running**; owner told Jarvis will close for
~1 minute and reopen. Reference: `.dsh-scratch/RELEASE-READY-2026-10-30/UPDATE-RUNBOOK.md` §3D/§4/§5.

**Steps.**
1. Agent runs **PRE-FLIGHT D (§3D)**: SHA-256 + size of `jarvis-framework.toml`; token store
   `where` + `cmdkey /list` target names (**never the token**); SHA-256 of
   `.openjarvis/devices/registry.json`; `pair=N` + device ids/`last_seen`; SHA-256 of live
   `jarvis_gate.py`; `GET /api/version` fields with `$h` (token into `$t`). Re-run F6-1/F6-4
   **seconds before** the launch and abort/redo if either changed (concurrent live edits happened
   today).
2. **Owner runs the one line from the pinned worktree** (`UPDATE-RUNBOOK.md` §4) — the installer
   closes/reopens Jarvis; owner clicks SmartScreen only if it appears.
3. Agent runs **POST (§5 + F6 block)**: installed `FileVersion` = `ProductVersion` = HKCU
   `DisplayVersion` = the release title; `Get-Process jarvis-desktop` running + shortcuts intact;
   port 4719 + `/api/version` (`server=jarvis-hud`, `api=1`, fresh `started`); updater log lines
   (`the download's signature is verified`, `this folder is at the released commit`, `the desktop app
   was replaced with version 0.2.<n>`, and **not** `building instead`/`has moved past`/`no published
   desktop installer was found`); F6-1..F6-6 table (hashes identical; same token store, no token file
   exists; registry hash identical; gate hash identical; phone `versionName`/`firstInstallTime`
   unchanged, paired ids same, `last_seen` advanced, no re-pair prompt; owner sees **Connected**).

**Evidence.** `pass6/update-pre.txt` and `update-post.txt` (**hashes and store names only**),
release title + `targetCommitish`, updater log quoted lines, the six-row F6 table with PRE/POST
values, phone version dump.

**PASS.** All six F6 checks PASS → the update row is a **measured PASS**. Any missing → PARTIAL; a
stopped/failed run → UNPROVEN (say which line stopped it).
**Who.** Owner: the one updater line + possible SmartScreen (~4 min). Agent: every measurement,
pre-flight A/B/C, fallback cache.

---

## 8. Desktop Calendar UI — matrix row 71 (one command once the owner has Jarvis open)

**Precondition.** Desktop updated to **0.2.≥369** and **running** (owner launched it — this agent
session cannot host a GUI app; pass5 evidence: notepad itself fails 0xC0000409 here). The documented
harness is pre-extracted at `.dsh-scratch/FIELD-TEST-2026-10-30/pass5/fieldtest-desktop.ps1` (from
`scripts/fieldtest-desktop.ps1`).

**Steps (read-only).**
1. `pwsh -File pass5\fieldtest-desktop.ps1 -Windows` → expect the top-level window **`Jarvis`** (the
   HUD; the app can also have a second window called `Jarvis` — the quickbar; use `-Nth`).
2. `-List` (or `-Text`) → save the full tree; find the rail door by name
   **"Calendar: your own events, kept on this PC"** (DOM id `#rail-calendar-open`; the rail card's
   own button is `#cal-open` / "Open calendar").
3. Click it: `-Click 'Calendar: your own events, kept on this PC'` (or `-Click -Id 'rail-calendar-open'`).
4. Dump again (`-List > pass6/desktop-calendar.txt`; `-Text` too). Read and quote: panel title
   **`Calendar`**, the period line (month/year, e.g. "October 2026"), the **Month / Week / Day** tabs,
   the weekday row Sun…Sat, the side heading **`Today`**, and the day's events or the empty state
   (**today is expected empty** — the phone-created "Field test" event was deleted). Optionally click
   `Today`/`Month`/`Week`/`Day` (view-only) and re-read; close with the panel's **`Close`** (✕,
   aria-label "Close the calendar") or Escape.

**Evidence.** `pass6/desktop-windows.txt`, `pass6/desktop-calendar-list.txt`,
`pass6/desktop-calendar-text.txt`, desktop `FileVersion`, the quoted labels, and the harness output.

**PASS.** The desktop Calendar panel was actually opened and read: title + month/year + the view
tabs + today's list/empty state. → Row 71 desktop half driven; with today's phone + PC-API evidence
row 71 → **PASS**.

**Honest fallback.** If the harness answers **`jarvis-desktop is not running`** or UIA cannot
enumerate (window not exposed to this session), record **PARTIAL** with the exact exception text and
the proof the owner has the app open — never claim the screen was read. If UIA cannot attach from
this session, the owner can read the same labels aloud and the agent records them as
**OWNER-VISUAL**, which is evidence but not an agent-driven PASS.
**Who.** Owner: launches/keeps Jarvis open. Agent: runs the harness if UIA can attach (1 min).

---

## Reference index (paths used above)

| what | where |
|---|---|
| Gemini F1–F6 rulings | `C:\Users\pcadmin\Downloads\gemini_rulings_f1_to_f6_field_test_gaps_2026_10_30.md` |
| Final-1 PR body (all change-sets) | `.dsh-scratch/FINAL-1-2026-10-30/PR-BODY.md` |
| Update runbook (§3D/§4/§5) | `.dsh-scratch/RELEASE-READY-2026-10-30/UPDATE-RUNBOOK.md` |
| Jobs backend contract | `.dsh-scratch/JOBS-2026-10-30/REPORT.md` |
| Phone jobs half | `.dsh-scratch/PHONE-JOBS-2026-10-30/REPORT.md` |
| Phone History/More simplify | `.dsh-scratch/PHONE-SIMPLIFY-2026-10-30/REPORT.md` |
| Widget repaint fix | branch `fix/widget-repaint-2026-10-30` commit `b3bf81530`; `jarvis-client/app/proguard-rules.pro`; `R8SourcePinTest.kt` |
| Current field-test report (append this pass) | `.dsh-scratch/FIELD-TEST-2026-10-30/REPORT.md` |
| Desktop UIA harness | `scripts/fieldtest-desktop.ps1`; copy in `pass5/fieldtest-desktop.ps1` |
| Matrix rows | `docs/FIELD-TEST-MATRIX-2026-10-11.md` (19, 21, 39, 71, 130 + the hidden rows) |
| How-to-read-the-apps (methods + binary gate) | `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md` |
| Approve/deny bodies | `docs/JARVIS-API.md` §3 (lines 289–308) |
| Card countdown words | `jarvis-desktop/src/jarvis-link.js:334-341`; phone `ApprovalCard.kt:941-965` |
| Locked-state words | `HistoryScreen.kt` / `SecurityScreen.kt:330`; backend 423s in `jarvis_chat_log.py:4124-4151` |
