# Audit #2 - Continuity between the desktop program and the Android app

Combined tree `integ` (branch `audit-integration`, HEAD deaca649), new work = `9cdb0567..HEAD`.
Everything below was checked in code unless marked otherwise. No Android build is possible here,
so every phone claim comes from reading Kotlin.

## Short version (plain words)

- **The two apps match well.** Every new feature the owner can see is either on both apps, or
  written down in `docs/ARCHITECTURE.md` §8 ("One-sided on purpose") with a reason. I found **no
  feature that is on one app only without a written reason**.
- `python3 tools/check_parity.py` is **clean** (exit 0: 173 desktop routes, 149 phone routes, 147
  ported, "No undecided drift"). The one "still to port" item, `/api/retrieve`, is older than the new work.
- **All 46 new routes** both apps call are in `docs/JARVIS-API.md` (my own script, below).
- **All 17 shared wording files** (`tests/fixtures/*.json` against the phone's `contract/*.json`) are
  byte-for-byte the same on both sides.
- Things that need fixing (details below): the phone's reading-notifications switch **does not
  hear about "off" from the PC** until its settings page is opened (medium); **Projects and Goals are
  not joined** now that both are in one tree (medium, needs the owner to decide the shape); the app
  builder's "app projects" are a **second project list** beside Projects (medium, owner's call); a
  wrong-blame message when talk-to-type is pressed during Jarvis Live (low); a few small wording
  differences and stale sentences (low).

## What `tools/check_parity.py` checks, and what it misses

It compares the `/api/...` routes each app calls (desktop Rust + JS, phone Kotlin, comments
stripped) against a hand-kept list of decisions (`CLAUDE.md` rule: must be clean). It does **not**
check:
1. features that ride on an existing route (schedule job kinds like Today cards, Watches,
   "remind me next time", Goals' check-in; voice settings inside `/api/voice/enroll`; events such as
   `wellbeing`, `ring_phone`, `live`);
2. that `JARVIS-API.md` documents a route;
3. wording or defaults.

So I checked those by hand (sections below).

## Table: every new owner-visible feature

"Both" = I found the code in `jarvis-desktop/src*` and `jarvis-client/app/src/main` (commit file
lists and greps). §8 = the row in `docs/ARCHITECTURE.md` "One-sided on purpose".

| Feature (branch) | Desktop | Phone | §8 reason if one-sided | Wording / defaults mismatches found |
|---|---|---|---|---|
| Animal faces: red panda, owl, otter, monkey; wake/sleep, Zs, "Keep the animal still", serious pose, hollow offline ring (mascot) | Yes | Yes | Floating face only: §8 says the phone's floating bubble is the app icon, not the animal | None found; "Keep the animal still" same title both |
| Quality levels / frame rate / sharp on capable hardware (mascot) | Yes (Settings "Face on this computer") | Yes (Appearance -> FaceEditor) | - | Per-device settings by design |
| Sun, moon and weather behind the animals (mascot) | Yes | Yes | Typing the town is PC-only (§8, backend refuses other devices) | Shared `sky-cases.json` identical |
| Voice follows the face; each animal's voice, Try it (main/mascot) | Yes | Yes | - | Both show the PC's state. Default is ON on both because the PC says so - see audit #6 |
| Lip-sync (mascot) | Yes | Yes | - | - |
| Chatbot driver + compare (research) | Yes | Yes | Signing in, keys, money limits are PC PowerShell only (§8 rows 70-73); phone has the "Talking to Gemini" notification (§8) | Shared `chatbot-cases.json` identical. Code comment and ARCHITECTURE still call the 3/4 limits "PROPOSED" although the owner confirmed them (low, doc) |
| Jarvis Live (research) | Yes | Yes | Badge, tray, End-Live-when-Windows-locks, mic-in-use = PC (§8 rows 74-76); Live notification, call detection = phone (§8 rows 100-101); camera hidden on both | Shared `live-cases.json` identical |
| Projects (research) | Yes | Yes | Folder and benchmark command PC-only (§8 row 69) | Shared `projects-cases.json` identical. **Not joined to Goals** - see F2 |
| Goals (continuation) | Yes (Brain -> Work -> Goals) | Yes (Brain -> Goals) | - | "Add a step" (desktop `goals.js:62`) vs "Add step" (phone `Goals.kt:89`); "...get done, below." vs "...get done below."; phone's `ACCEPT_DETAIL` says "one approval card, like a repeating reminder" - untrue since 2026-09-26 (repeating reminders ask no card). See F5 |
| Plan card (continuation) | No UI | No UI | Switched off; no UI on either (documented in CLAUDE.md) | - |
| Try the cloud model (main) | Yes (not in the widget) | Yes | Widget left out, in §8 row 68 | - |
| Third graphics card (continuation) | Yes | Yes | - | Shared `second-card-cases.json` identical |
| Reading phone notifications (continuation) | Switch only on PC backend | Yes | Phone-only in §8 row 99 and `check_parity.py` | **Phone does not learn about "off" from the PC** - see F1 |
| Brain -> Model remembers its last list (continuation) | Yes | Yes | - | - |
| Lockdown (competitors) | Turn on + off | Turn on only | Turning off is PC-only (§8 row 66) | Words identical (compared every "Lockdown" string) |
| Watches: search, price, GitHub (competitors) | Yes (Coming up) | Yes (Coming up) | No new route | - |
| "Remind me next time" (competitors) | Yes | Yes | - | - |
| Ring my phone / Playing on your PC (competitors) | Media buttons only in a widget | Yes | §8 rows 89-90 | - |
| Talk-to-type (competitors) | Yes | No | §8 row 29 (a client must not do speech-to-text) | Wrong-blame message during Live - see F4 |
| Today cards (competitors) | Yes | Yes | - | Compared every sentence in `today.js` vs `Today.kt`: identical except one internal line |
| Widgets you describe (competitors) | Yes (in the widget window) | Yes (home-screen slots) | §8 row 92 (where it is drawn) | Shared `widget-cases.json` identical |
| Quick Settings tiles, "Hey Jarvis is off since restart", Android 17 notes (competitors) | - | Yes | §8 rows 91, 93, 94 | - |
| History search, find in chat (competitors) | Yes | Yes | Fact history and Galaxy desktop-only (§8 rows 13-14) | - |
| Bring in chats from ChatGPT/Claude/Gemini (competitors) | Yes | No button | §8 row 56 | - |
| Photo to reminder (competitors) | Yes | Yes | "Also on my phone" on it is phone-only (§8 row 85) | - |
| PC help (competitors) | Yes | Yes | - | Shared `pc-help-cases.json` identical |
| Forget a time frame (research) | Yes | Yes | - | Shared `forget-range-cases.json` identical |
| Deleting a chat offers to forget its facts; overnight tidy switch (github-repos) | Yes | Yes | - | - |
| Prompt-cache share on Brain -> Model (github-repos) | Yes (`brain.js`) | Yes (`ApiModels.kt`) | - | Commit 564c90a6 says "same wording" |
| Better voice settings (competitors) | Yes | Yes (Voice check screen) | microWakeWord and VAD choice PC-only (§8 rows 30-31) | - |
| Screen answers after "Hey Jarvis" setting (research) | Yes | Yes | - | Default `screen_on_screen` on the PC |
| Swipe to approve setting (research) | - | Yes | §8 row 86 (desktop has no swipe) | - |
| Setup helps: Show token, reconnect, keep-alive offer (research) | - | Yes | §8 row 97 | - |
| "Working on your screen - Stop", windows remember size (competitors) | Yes | - | §8 rows 33-34 | - |
| Look at this / Watch with me (research) | Not built | Not built | Backend only, stated in §8 row 26 and JARVIS-API §62 | - |
| App builder workspace (github-repos) | Not wired to any screen | Not wired | Not owner-visible yet | Duplicate risk with Projects - see F3 |

## Findings

### F1 - medium - The phone keeps reading notifications after the owner turns the switch off on the PC
**Checked in code** (continuation branch). The owner's rule is "turning it off is immediate". The
phone's listener checks a cached copy of the PC's switch:
`JarvisRuntime.kt:3545-3546` - `fun phoneNotificationsAllowed(): Boolean = if (::settings.isInitialized) settings.phoneNotifications.value else false`.
That cache is refreshed only by `phoneNotificationsSettings()` (`JarvisRuntime.kt:3561-3566`), whose
only caller is the settings page itself (`ui/screens/PhoneNotificationsPlate.kt:75`). No event on the
bus updates it (grep for `phone_notifications` in the phone finds only constants). So if the owner
turns it off on the PC, or by voice ("turn off phone notifications" goes through
`jarvis_settings_registry.py`), the phone goes on capturing allowed apps' notifications into its local
store until that settings page is opened. Nothing leaves the phone, so no rule-1 break, but "off is
immediate" is not true. The same gap means an approved "on" does not take effect until that page is
re-read.
**Fix (code):** re-read `GET /api/notifications/phone` with the other reads in `refreshAll`, and/or
publish a small event from `jarvis_phone_notifications.set` that the phone's `onEvent` handles; on a
stale link keep the last value but treat a failed read after a known "off" as off.

### F2 - medium - Projects and Goals are not joined, now that both are in the same tree
**Checked in code** (research + continuation branches). The owner's decision says a project's goals
are "built on the Goals feature ... not a second goals system". `backend/jarvis_projects.py:32-38`
still says "jarvis_goals.py exists only on the continuation branch ... not here ... Until then a goal
id here is not checked against goals.db". In the combined tree `jarvis_goals.py` has no `project`
field (grep finds only a docstring use of the word), and neither app's Projects screen shows goals.
Meanwhile Projects' own help line in both apps says "an app, or a goal like a half marathon" - so the
owner now sees two places to put a goal. **Fix (code, after the owner OKs the shape):** the design's
"one extra field" - a `project` column in goals.db, `GET /api/goals?project=`, a Goals list inside a
project in both apps. Until then, remove "or a goal like" from the Projects line so it does not
point at the wrong screen.

### F3 - medium - The app builder starts a second kind of "project"
**Checked in code** (github-repos branch). `backend/jarvis_app_workspace.py` (commit 2e2df224) keeps
"app projects under <settings>/apps", separate from Projects' coding projects
(`jarvis_projects.py`, research branch). `docs/APP-BUILDER-DESIGN.md` never mentions Projects, and its
milestones plan "both apps showing projects, tasks and the merge card" (line 64). Not visible to the
owner yet (not wired to any route or screen), so nothing is broken today - but it is heading for a
duplicate. Also Projects' decision says "Jarvis writing code comes once the 12 GB card is installed
and measured", while the app-builder decision lets Jarvis write code without that condition.
**Owner's call:** should app-builder apps BE coding Projects (one list), and does the 12 GB wait apply?

### F4 - low - Talk-to-type during Jarvis Live blames "hey Jarvis"
**Checked in code** (competitors + research). The two cannot take the microphone at once - good:
Live refuses while talk-to-type holds it (`voice.rs:1852-1853`, `1877-1878`), and talk-to-type
refuses while the listener Live uses is open (`talk_type.rs:300-302` checks `AutoListenState`, which
`open_live_listener` uses, `voice.rs:1353-1356`). But the words shown are `MIC_WAKE`
(`talk_type/rules.rs:66-67`): "Jarvis is listening for "hey Jarvis" ... Turn listening off in the
Jarvis bar" - wrong during Live; the owner should End Live. **Fix (code):** in `mic_free`, check
`crate::live::on_here()` (or `voice::LIVE_MODE`) first and return a Live-specific sentence ("Jarvis
Live is using the microphone. End Live first.").

### F5 - low - Small wording and stale-sentence differences
All **checked in code**:
- Goals: "Add a step" (`jarvis-desktop/src/goals.js:62`) vs "Add step" (`Goals.kt:89`); empty-list
  line with and without a comma.
- Phone `Goals.kt:95-97`: "Sets up a weekly check-in on your PC - one approval card, like a repeating
  reminder." Since 2026-09-26 a plain repeating reminder asks no card, so the comparison is wrong. The
  check-in itself does ask (`jarvis_goals.py:421`, `plain_repeat=False`) - a deliberate choice the
  module explains (lines 57-62). Worth asking the owner whether a check-in that reads nothing and acts
  on nothing should follow the "plain repeat, no card" rule like Today cards (`Kind.plain_repeat`).
- `docs/ARCHITECTURE.md:1409` still says the apps' side of the `wellbeing` event "is not built yet";
  both apps read it now (`jarvis-link.js:586`, `JarvisRuntime.kt:1396`).
- `backend/jarvis_chatbot_compare.py:92` and `docs/ARCHITECTURE.md:584` call the 3/4 limits
  "PROPOSED"; the owner confirmed them (CLAUDE.md, 2026-09-28).
- CLAUDE.md line 511 still says talk-to-type is "Not built yet"; it is built (§72).
- Projects keeps its own pinned "notes" (`jarvis_projects.py:113-115`, up to 10 lines) beside the
  owner's Obsidian/Logseq/Joplin notes and the wiki. Small and project-scoped, so I would not call it a
  duplicate, but the word "notes" may confuse; "Pinned lines" would not.

## How I checked
- `python3 tools/check_parity.py` in `integ` (exit 0, output quoted above).
- A script (`scratchpad/a02/apicheck.py`) listing every route added to `check_parity.py`'s tables
  since 9cdb0567 and looking for it in `docs/JARVIS-API.md`: 46 of 46 found.
- `cmp` of every `jarvis-desktop/tests/fixtures/*.json` against the phone's
  `app/src/test/resources/contract/` copy: none differ.
- Per-commit file lists for desktop vs phone, then reading §8 rows for anything one-sided.
- Not done: running the desktop UI tests or the Kotlin unit tests (no Android build here).
