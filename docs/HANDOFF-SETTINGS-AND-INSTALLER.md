# HANDOFF — settings generator (+ the installer thread)

Written 2026-10-09 for the next session. Working dir:
`C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`
Repo conventions live in `CLAUDE.md` (read the version at repo root, not an old
copy on a branch). This file is a working handoff, **not a feature doc — do not
commit it as-is.**

Owner preferences that matter: plain words (they are a beginner developer), lead
with the answer, short multiple choice (1-2 questions, 2-3 options, recommended
option first), say plainly what is broken or uncertain, own mistakes early.

---

## 0. THE ONE THING IN FLIGHT RIGHT NOW

A **subagent is running** (id `4755aa1f-5368-4566-8ad2-1957ec2c1001` at time of
writing) building the generator foundation. It CANNOT be messaged mid-run
(`send_message` fails; only `spawn_teammate` targets are addressable). It was
given a brief containing **a wrong number from me**:

> "add records for the remaining desktop toggles so that **all 19** desktop
> `<label class="toggle">` switches are described"

**The real count is 26.** So:

1. When its work lands, **count the toggles yourself** with a regex over
   `jarvis-desktop/src/settings.html` before trusting its catalogue.
2. Expect to add the 7 it was told did not exist.
3. Its test will probably assert 19. Fix it to 26.

This is the exact failure mode worth internalising: three times on 2026-10-09 a
number I asserted was wrong, and each time something else caught it. **Do not
take any count in this document on trust either — verify it.**

---

## 1. WHAT THE OWNER ASKED FOR

Choices already made by the owner (do not re-litigate):

- **"One source for the settings screens"** — a generator so the desktop and
  phone settings can no longer drift, mirroring what `gen_menu_cases.py`
  already does for menus.
- **Scope: "Generate the toggle rows"** — NOT the whole screens. The bespoke
  sections (chooses, buttons, lists, custom widgets) stay hand-written and only
  get *checked* against the registry.

---

## 2. THE INVENTORY (verified 2026-10-09, HEAD 62265666)

### 2.1 The existing source of truth is NOT a screen description

`backend/jarvis_settings_registry.py` — 755 lines. It is a **voice/chat**
registry ("open that screen", "adjust that switch"). It carries **no label, no
detail and no DOM id per switch.**

- `Section` (frozen dataclass, ~144-149): `id`, `names`, `app`, `where`.
  `SECTIONS` (~158-279) = **41** records. `where` is dead (0 uses of `where=`);
  `sections_for()` (~289) is never called.
- `BoolSetting` (~623-641): `key`, `names`, `section`, `set`, `on_word`,
  `off_word`. `BOOL_SETTINGS` (~643-689) = **11** records.
- Imports only `re`/`dataclasses`/`typing` at module level; every backend module
  is imported lazily inside functions. **Keep it standalone-importable.**
- **Check for a byte-identical twin under `jarvis-backend/` before editing** —
  `backend/test_base_matches_repo.py` fails if the two diverge.

**Design decision already made:** extend `BoolSetting` with the UI fields
(desktop DOM id, label, detail, order, app) rather than creating a new backend
module. A new module would drag in `backend/_where.py`'s SHIPPED list, a
`jarvis-backend/` copy and the patch machinery for no benefit.

### 2.2 Desktop surface

`jarvis-desktop/src/settings.html` **2542 lines**; `settings.js` **3498**;
`settings.css` **1314**. **28 script tags** at `settings.html:2513-2540`
(`sky.js` classic + **27** `type="module"`) — the earlier "26 modules" was wrong.

Structure: **37** `<section class="card" id>` + one `<details id="more-options">`
(2231); **3** heading bands (Everyday 184 / Rare 1102 / What Jarvis does 2358);
a **static** `<nav class="settings-jump">` with **35** links; **26**
`<label class="toggle">` rows and **20** `class="toggle-detail"` spans.

**The 26 toggles** (label line, then the `<input>` id on the next line):

| line | input id | label id | wiring | words |
|---|---|---|---|---|
| 437 | `follow-system` | — | `settings.js:495` | inline; `:496` rewrites detail |
| 476 | `floating-enabled` | — | `settings.js:789` | inline, never rewritten |
| 546 | `sky-show` | — | `sky-settings.js:44` | **from PC** (`:45-46`) |
| 601 | `face-auto` | — | `settings.js:666` | inline |
| 816 | `voice-one-moment` | — | `settings.js:3364` | label inline, **detail from PC** |
| 823 | `voice-heard-sound` | — | `settings.js:3391` | label inline, **detail from PC** |
| 854 | `mn-humor` | — | `manner-settings.js:38` | label inline, **detail from PC** |
| 910 | `coach-enabled` | span `coach-enabled-label` | `prompt-coach-settings.js:69` | **label+detail from PC** |
| 958 | `br-senders` | `br-senders-row` | `briefing-settings.js:62` | inline |
| 980 | `notif-alarms` | `notif-alarms-row` | `notifications-settings.js:28` | inline |
| 988 | `notif-reminders` | `notif-reminders-row` | `:29` | inline |
| 996 | `notif-briefing` | `notif-briefing-row` | `:30` | inline |
| 1004 | `notif-handoff` | `notif-handoff-row` | `:31` | inline |
| 1016 | `notif-quiet-enabled` | `notif-quiet-row` | `:32` | label inline, **no detail** |
| 1087 | `hud-open-bar-show` | — | `hud-window-settings.js:39,46` | inline, never rewritten |
| 1145 | `sec-app-lock` | — | `settings.js:1358` | label inline, **detail from PC** |
| 1165 | `sec-private` | — | `settings.js:1364` | label inline, **detail from PC** |
| 1242 | `cv-face-switch` | span `cv-face-title` | `voice-panel.js:1785` | **label+detail from PC** |
| 1327 | `cv-better-switch` | — | `voice-panel.js:1784` | inline; carries `data-live="true"` (855) |
| 1361 | `ws-enabled` | span `ws-enabled-label` | `web-search-settings.js:70` | **label+detail from PC** |
| 1380 | `ws-ask` | span `ws-ask-label` | `:74` | **label+detail from PC** |
| 1937 | `spd-accept` | `spd-accept-wrap` | `spending-settings.js:75` | **from PC**. Label also has `hidden` |
| 2012 | `sp-switch` | span `sp-switch-label` | `look-settings.js:46` | inline, **no detail** |
| 2043 | `be-switch` | span `be-switch-label` | `browser-engine.js:40` | inline, **no detail** |
| 2255 | `supervise` | — | `settings.js:131` | inline, **no detail** |
| 2320 | `autostart` | — | `settings.js:146` | inline, **no detail** |

Notes that will bite a generator:

- **`spd-accept` (1937) is NOT a settings toggle.** It is the spending
  accept-all control and its label carries `hidden`. Decide deliberately.
- **12 rows get their visible words from the PC at read time**; the HTML text is
  a **fallback only** (546, 816, 823, 854, 910, 1145, 1165, 1242, 1361, 1380,
  1937). Do not make the catalogue a competing source of truth for those.
- **7 rows have an id on the `<label>`** (the modules hide/relabel the whole
  row through it): `br-senders-row`, `notif-alarms-row`, `notif-reminders-row`,
  `notif-briefing-row`, `notif-handoff-row`, `notif-quiet-row`,
  `spd-accept-wrap`.
- **6 spans have ids**: `coach-enabled-label`, `cv-face-title`,
  `ws-enabled-label`, `ws-ask-label`, `sp-switch-label`, `be-switch-label`.
- **No toggle is the first child of its card** — all 37 cards open with `<h2>`.
  Depth varies from a direct child (`#hud-window` 1087) to three levels deep
  (`#more-options` 2231 → `#start-jarvis` 2237 → 2255).
- Some inputs are `checked` in the HTML (981/989/997/1005).
- Two detail spans are written by **nothing**: `floating-detail` (480) and
  `hud-open-bar-detail` (1091) — hand-written words with no other copy.

### 2.3 Phone surface

`jarvis-client/app/src/main/java/com/jarvis/client/`: `SettingsScreen.kt` **502
lines** (**22** `item(key = "…")` at 259-474; `SETTINGS_ITEM_INDEX` at 96-125
with 20 keys), plus ~**7.9k lines** of `*Plate.kt` composables and `net/*.kt`
words. Shared widget: `Toggle` at `ui/parts/Parts.kt:823-874`; plain rows use
`SwitchRow` at `AppearanceScreen.kt:1037`.

**Only 3 of the 22 rows are plain toggles:**
`prompt-coach` (410), `watch-notify` (416), `screen-look` (429).
**18 are bespoke**, 1 is a spacer (`tail` 474).

Where each plain row's words live:

- `watch-notify` — **hardcoded** at `WatchNotifyPlate.kt:88-90`. This is the one
  clean win. (No `TITLE`/`DETAIL` const in `net/WatchNotify.kt`.)
- `screen-look` — `net/ScreenPicture.kt:40-52`, contract-tested against the PC's
  own words at `ScreenPictureTest.kt:42-44`.
- `prompt-coach` — **from the PC** at read time (`PromptCoachPlate.kt:101-103`,
  parsed in `net/PromptCoach.kt:185-193`). **Do not replace with a static
  string**: `tools/check_parity.py:103` classifies `/api/prompt/coach` as
  `ported`, and rule 2 (`check_parity.py:45`) fails if the phone stops calling a
  ported route.

`SETTINGS_ITEM_INDEX` needs **no** regeneration for a words-only catalogue. It is
already held by `SettingsJumpTest.kt:54-60,72-82,95-148`,
`backend/test_settings_registry.py:338-366` (aliases `appearance-card` and
`animal-options` → `appearance`), and `OpenPlaceTest.kt:76-87`.

**So the phone half of this feature is small: two rows genuinely benefit.**

### 2.4 What a new setting touches today

A recent real setting (commit `69820585`) touched **63 files, +5037/−139**.
The 19-point hand-edit checklist is reproduced in the recon report; the items
that are **already checked**: registry ids vs both apps
(`test_settings_registry.py:156-220`), the desktop jump list (`:223-335`),
`SETTINGS_ITEM_INDEX` (`:338-366`), the feature list (`check_feature_list.py`),
`_where.py` SHIPPED + base copies (`test_base_matches_repo.py`), Tauri command
ACLs (`check_command_acl.py`), invoke grants (`check_invoke_grants.py`), phone
place decisions (`OpenPlaceTest.kt:64-72`), menu places
(`MenuVisibilityTest.kt:289-335`).
**Not checked:** the per-section JS, the `*Plate.kt` composables, and — the gap
this work closes — **any comparison of the registry against either app's
switch-level labels, details or ids. No such test exists today.**

---

## 3. THE DESIGN (settled — build this)

### 3.1 The generator

`tools/gen_settings_cases.py`, mirroring **`tools/gen_menu_cases.py` (418
lines)** — read it first. Its shape:

- injects `sys.path` (~37-42) to import its source;
- builds everything in memory;
- writes **four** files (~399): two **byte-identical** JSON fixtures
  (`jarvis-desktop/tests/fixtures/…` and
  `jarvis-client/app/src/test/resources/contract/…`), a Kotlin file
  (`net/MenuCatalog.kt` via a hand-written skeleton + f-string, ~310-366) and a
  JS file (`jarvis-desktop/src/menu-catalog.js`, ~369-387);
- every output opens with `GENERATED by … do not edit by hand` (~314-316, ~371);
- `--check` (~400-407) rebuilds in memory and **byte-compares**, printing
  `STALE <path> - run python3 tools/gen_menu_cases.py` and exiting 1;
- writes with `p.write_text(..., encoding="utf-8", newline="\n")` (~412) so
  Windows keeps LF.

Outputs for settings, same four-way shape:
`jarvis-desktop/tests/fixtures/settings-cases.json`,
`jarvis-client/.../test/resources/contract/settings-cases.json` (byte-identical),
`jarvis-client/.../net/SettingsCatalog.kt`, `jarvis-desktop/src/settings-catalog.js`.

Test to mirror: `backend/test_menu_visibility.py:405-412` (runs `--check` via
subprocess and asserts the two JSON copies are byte-identical). House test style:
plain Python, **no pytest**, a `check(name, cond, detail)` helper, `t_*`
functions, its own `main()`.

### 3.2 Desktop wiring — splice in place between markers

**Splice the generated rows back into `settings.html` between two HTML-comment
markers.** No partial, no include step, nothing changes at runtime — every id,
word, attribute and element nesting stays byte-identical.

Precedent to copy exactly: **`tools/gen_hardware_cases.py`** splices a generated
table into `docs/HARDWARE-PROFILES.md` between
`<!-- hardware-cases:begin … -->` / `<!-- hardware-cases:end -->` (constants
~47-48, splice ~233-238), and `SystemExit`s if the marker is gone.

**Why not render from JS at startup:** **19 desktop test files read
`src/settings.html` as text** and assert ids and wording —
`notifications-settings.mjs:73-93`, `browser-engine.mjs:166`,
`look-rules.mjs:327`, `hud-window.mjs:380`, `briefing.mjs:141-143`,
`asks-first.mjs:89`, `chatbot-api-keys.mjs:208`, `chatbot-money.mjs:267`,
`continuity.mjs:214`, `features.mjs:241`, `handoff-mode.mjs:147`,
`hotkeys.mjs:93`, `jarvis-live.mjs:271`, `menu-visibility.mjs:286`,
`pairing.mjs:189-190`, `reach.mjs:54`, `spending.mjs:531`, `updates.mjs:171`.
Also **`voice-panel.js:1784-1787` calls `.addEventListener` UNGUARDED** inside
`startVoicePanel` (called from `settings.js:3319`) — a missing row throws and
aborts that initialiser.

Requirements for the splice:

- Markers must be **bare comments at the same indent**; wrapping the rows in an
  extra element breaks `settings.css:1264`
  (`.card.card-collapsed > :not(h2):not(.card-collapse-toggle)`) and `:890-895`.
- Reproduce per-row extras **verbatim**: `hidden` (1937), `checked`
  (981/989/997/1005), `data-live="true"` (855), all 7 label ids, all 6 span ids,
  and the two hand-written-only details (480, 1091).
- Add a Node test `jarvis-desktop/tests/settings-catalogue.mjs` mirroring
  `menu-visibility.mjs:16,35-38`, holding the catalogue to the fixture **and** to
  the ids/words in `settings.html`. **Row-level order is currently unprotected** —
  this test must check it.
- Add `--check` to CI beside `ci.yml:263` (`gen_animal_cases.py --check`).
  Note `gen_menu_cases.py --check` is **not** in any workflow today; the phone's
  fixture check lives in `MenuVisibilityTest.kt:57-74` instead.

Desktop risk list (each with the test that catches it) is in the recon report;
the sharp ones: a row moving between cards (row order unprotected), a renamed
toggle id (string-level tests catch the id, but a **guarded** module silently
no-ops — e.g. `briefing-settings.js:113`), and `voice-panel.js:1784` throwing.

### 3.3 Phone wiring — words only, and only where the phone owns them

Read **words** from the generated Kotlin catalogue for the rows whose words the
app already owns (`watch-notify`, `phone-notify`). **Keep reading the PC** for
rows the PC owns. Use the catalogue for `key`/`section`/`order`/`apps` in a unit
test. **Do not drive the `LazyColumn` from it.**

Consuming precedent: `MenuVisibilityPlate.kt:22,90,125` reads the generated
`MenuCatalog`; `MenuVisibilityTest.kt:57-74` holds it to
`contract/menu-cases.json`.

Pattern:

```kotlin
val row = SettingsCatalog.row("watch-notify")
SwitchRow(title = row?.label ?: "Show notifications on a compatible watch",
          detail = row?.detail, …)
```

All enable/approve/stale-link logic stays untouched.

---

## 4. THE TOOLCHAIN — what works on this machine now (2026-10-09)

**Java 17** (`openjdk 17.0.20.1`) ✓ · **Android SDK** at
`C:\Users\pcadmin\AppData\Local\Android\Sdk` with **platforms: android-36**,
**build-tools: 36.0.0** ✓ · `gradlew` present in `jarvis-client` (Gradle 9.6.0)
✓ · **node v22.23.2** ✓ · **python 3.12.10** via `py -3` ✓.

Gaps: **`ANDROID_HOME`/`ANDROID_SDK_ROOT` are NOT set** and `adb`/`sdkmanager`
are **not on PATH**; `pnpm` is not on PATH (the harness bundles it —
`load_workspace_dependencies` returns its path).

**The phone compiles locally.** Verified with a forced, non-cached build:

```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_HOME = $sdk; $env:ANDROID_SDK_ROOT = $sdk
cd 'C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\jarvis-client'
.\gradlew.bat :app:compileDebugKotlin --rerun-tasks --console=plain --no-daemon
```

→ `7 actionable tasks: 7 executed`, **BUILD SUCCESSFUL in 57s**. (13 pre-existing
warnings, none fatal: deprecated `LocalClipboardManager`, unnecessary `!!`,
always-true conditions in `HistoryScreen`/`VoiceTrainingScreen`/`ChatbotPlate`.)

**This is the single biggest process improvement available**: before this, every
Kotlin change was a blind CI push. The prompt coach burned three ~1-hour
round-trips on Kotlin errors that were invisible locally. **Compile before you
push.**

Because the next session is debugging a **USB-connected phone**: `adb` is not on
PATH here — find it under the SDK's `platform-tools`. The five non-negotiable
rules still apply (see `CLAUDE.md`): sideload only, never Play, non-commercial,
no client-side speech-to-text, phone connects via Tailscale/NordVPN Meshnet only
(never a public tunnel).

---

## 5. GOTCHAS THAT COST REAL TIME (read these before touching the repo)

1. **CI only triggers on pull requests.** A bare branch push runs nothing. A
   **draft PR** is enough to start checks.
2. **Auto-merge is NOT allowed** on this repo
   (`GraphQL: Auto merge is not allowed for this repository`). Merge manually;
   do not promise auto-merge.
3. **`gh pr checks` rows are tab-separated** `name<TAB>status<TAB>duration<TAB>url`.
   The one-line "no checks reported on the branch" is **not a check**. A watcher
   that counts it as "all good" will merge nothing and report success. Filter:
   `$_ -match "`t(pass|fail|pending|skipping)`t"`, and keep looping while the
   list is empty (a push empties it).
4. **Main moves fast — several merges an hour.** A branch that passes every check
   can become un-mergeable before anyone presses the button; `frontend` alone
   takes ~57 minutes. Re-check mergeability immediately before merging.
5. **Editing any patch obliges storing its old version** in
   `backend/patch-history/<patch>/<commit>.patch` — run
   `py -3 tools/build_patch_history.py`, then `backend/test_patch_history.py`.
6. **`backend/_stack.py`'s RATCHET** pins how many hunks needed an invented
   pre-image, per file. `test_retrieve_count.py` asserts the pin **equals** what
   the walk measures — so the value is a **measurement**, never arithmetic.
7. **`backend/_where.py`'s SHIPPED list, `jarvis-backend/` copies and
   `scripts/apply-patches.ps1`'s `$PATCHES`** must agree with each other;
   `test_base_matches_repo.py`, `test_shipped_modules.py` and
   `test_screen_attach.py` enforce parts of it.
8. **Generated files are never hand-edited** (`menu-catalog.js`,
   `MenuCatalog.kt`, both `menu-cases.json`, `*-cases.json`). Regenerate.
9. **`screen-attach.patch` must stay last** in `$PATCHES`, bar an explicit
   allow-list declared in `test_screen_attach.py`, `test_referee.py`,
   `test_devices.py`, `test_gate_risk_rows.py`.
10. `py -3` (not `python`); `$env:PYTHONIOENCODING="utf-8"`; every generated or
    written file uses `encoding="utf-8", newline="\n"`.
11. **PowerShell heredocs (`<<'MSG'`) do not work**; write the message to a file
    and use `git commit -F`, or a single-quoted here-string `@'…'@`.
12. **Fixed temp folder names are a trap.** `Copy-Item -Recurse X <existing dir>`
    nests instead of replacing, silently producing garbage results. Always use a
    fresh GUID-suffixed directory. This produced a confident, completely wrong
    failure report on 2026-10-09.

---

## 6. THE OTHER THREAD — the installer (do not duplicate another session)

**My PRs, all merged:** #109 job list `165e8f2d`; #126 prompt coach `451c3ab0`;
#147 the anchor write-up `62265666`.

**The problem** (fully written up in `docs/PATCH-ANCHOR-FRAGILITY-2026-10-09.md`,
merged): **41 patches insert a block immediately before the same line** in
`jarvis_hud.py` (`# Before the main socket, so the banner lists every address
together.`), each naming the block above it as its leading context.
`screen-attach.patch` named `tutorials.patch`'s print lines, which
`chatbot-limits-hud.patch` has since pushed up — so it **fails on the repair
pass**, which is the pass the owner's PC takes (their backend carries 7 older
patch versions). Re-anchoring is a treadmill: proved correct for 128 patches,
stale again within the hour when main reached 131.

**Status of that thread:**

- **Another session owns it.** `origin/fix/tutorials-patch-superseded` (1 commit
  ahead, unmerged): *"tutorials.patch is superseded by the published base, and
  saying so unblocks every update"* — it touches `apply-patches.ps1`.
  Also `origin/next-patcher-race` (installer concurrency).
  **Do not race that branch.** I attempted to verify it and my rehearsal was
  **invalid** (fixed temp path, see gotcha 12) — that output is not evidence.
- A **proposed** durable fix (one sentinel line, anchored as trailing context
  only, so patch order stops mattering) is in the merged write-up but is marked
  **NOT VERIFIED**: my test of the load-bearing claim failed in every case
  **including the control**, which points at the harness rather than the claim.
  Nobody should change 41 patches on it until that test passes. The longer cure
  noted there: **generate the banner blocks** from one list.
- `handoff-mode.patch` was malformed and **is already fixed** on current main
  (`cb294e04`, PR #142). The git error named line 12; the real defect was one
  integer on **line 3**. Worth knowing because the error misleads.
- My proven-but-stale re-anchor is on the **local, unpushed** branch
  `fix/screen-attach-context`.
- **The installer rehearsal was run** (owner-approved, long outstanding): it
  found the anchor failure. Run it with
  `scripts\apply-patches.ps1 -BackendPath <copy>`; **it dry-runs on a copy
  itself**, so it is safe. Without `-SkipTests` it runs the suites and takes
  **over an hour**; with it, ~5 minutes. It refuses if a patch file exists that
  is not in `$PATCHES`, and vice versa.

---

## 7. OTHER OPEN ITEMS (mine, unresolved)

- **The plan card safety test.** `jarvis_plan.enabled()` reads
  `~/.openjarvis/tool_eval_results.json`, produced by
  `py -3 tools/tool_eval/ollama_tool_eval.py` (`MULTI_PASS_RATE = 0.9`). It has
  **never been run on the owner's PC** — the app says so plainly. **Worth
  checking first:** another session's commit *"plan card: the gate can be
  satisfied when the run happens in the repository"* may mean it can be run here
  instead of by the owner. Unverified.
- **`waiting_input` has no producer** (documented in the job-list audit);
  ownership unknown.
- **promptfoo-style offline prompt regression tests** — deferred by the owner.
- **The installer's own rehearsal against the owner's REAL backend** has still
  never been run (only against copies).

---

## 8. WHAT "DONE" MEANS FOR THE SETTINGS WORK

1. Row metadata in `backend/jarvis_settings_registry.py` covering **all 26**
   desktop toggles (minus a deliberate decision on `spd-accept`), with words
   copied from the existing markup, plus the `jarvis-backend/` twin kept
   byte-identical.
2. `tools/gen_settings_cases.py` + its four generated outputs + `--check`.
3. `backend/test_settings_rows.py` in house style, failing when a hand-added
   toggle has no registry row.
4. The desktop splice between markers, with a Node test holding the catalogue to
   the fixture and to `settings.html`, checking row-level **order**.
5. The phone reading words from the catalogue for `watch-notify` (and
   `phone-notify`), PC-owned words left alone.
6. `--check` wired into CI.
7. Claimed honestly: the desktop gains drift protection for 26 switches; the
   phone for two. **The bespoke sections remain hand-written.**

Run before every push: the guards named in §2.4, `py -3 tools/gen_menu_cases.py
--check`, and the local Kotlin compile from §4.
