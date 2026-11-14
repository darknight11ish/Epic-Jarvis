# F4 field-test matrix - 2026-11-03

**Wave:** the F4 deploy, 2026-11-03. **Repo:** `Epic-Jarvis-main`, `main` at `dba25cc7d`.
**Harness:** [`probe.py`](probe.py) in this folder. **Pre-deploy evidence:**
[`pre-deploy-probe.txt`](pre-deploy-probe.txt), captured 2026-11-03 09:09:43 -08:00 against the
**live F3 build** (the running HUD process says it started 2026-11-02 14:10:10 -08:00).

## How to read a row

Every feature is **two rows**, and they are graded differently on purpose:

- **Sub-Row A - automated live wire/state probe.** A `GET` against the live backend on this PC.
  It can be **PASS**. What it proves is narrow and it is written on the row: the route exists, the
  answer is well-formed, and the value in it is true of this PC. It proves *wiring and state*, not
  that the owner's experience is right.
- **Sub-Row B - needs the owner's voice or thumb.** Asking by voice, approving a card, touching a
  fingerprint, watching the screen. Nobody but the owner can drive it, and he is not at the machine
  today, so every B row is **BLOCKED-owner-away**. **BLOCKED is never counted as a pass.**

Row ids follow the older matrices: one number per feature (`F4-01` ... `F4-12`), the letter for the
sub-row (`A` / `B`). The older matrices' rule - *a row that could not be reached is BLOCKED,
PARTIAL or NOT-TESTABLE, and only a feature driven for real is a PASS* - is unchanged
(`docs/FIELD-TEST-MATRIX-2026-10-11.md`).

**Verdicts here are dated and built-scoped.** "F3" is the build that was live when the harness was
run: its `/api/version` says `server=jarvis-hud api=1`, the F4 routes are absent, and
`/api/asks_first` still carries the pre-fix DEF-028 sentence. The F4 deploy lands later today, so
**every A cell below has to be re-run** after it; nothing in this file is a claim about F4.

## The F4 wave

| Row | Feature (the owner's words) | Sub-Row A: the automated live probe | A verdict on live F3 | Sub-Row B: what only the owner can do | B verdict |
|---|---|---|---|---|---|
| **F4-01** | **Habit check-ins** - "I want to walk three times a week", one tap records it | `GET /api/habits` - the habit list answers `ok:true` with a `habits` array (`probe.py` → `habits-read`) | **BLOCKED** - `404 {"error": "not found"}`: the route is not in F3 | tick a habit by thumb, and say "done" by voice | **BLOCKED-no-UI-in-this-build** (was BLOCKED-owner-away) - build 0.2.3635 has no Habits screen at all, so there is nothing for the owner's thumb to tick; see "Phone lane" below |
| **F4-02** | **Mood log** - one 1-5 tap a day, optional words, a history to look at | `GET /api/mood?days=7` - rows, `latest`, the scale (`mood-read`) | **BLOCKED** - `404 {"error": "not found"}` on F3 | tap a 1-5 value and read the chart | **BLOCKED-no-UI-in-this-build** (was BLOCKED-owner-away) - build 0.2.3635 has no Mood section or chart on Reminders; see "Phone lane" below |
| **F4-03** | **Week in review** - counts of the week that passed, filed as one line | `GET /api/habits/week` - the counts answer `ok:true` with its own keys (`week-in-review`) | **BLOCKED** - `404 {"error": "not found"}` on F3 | let a week pass and read the filed line | **BLOCKED-no-UI-in-this-build** (was BLOCKED-owner-away) - build 0.2.3635 has no Week-in-review screen; weekly filing is off (`on=false`, `job=null`), and the last complete week (10-27..11-02) predates F4 landing on 11-03, so no filed line exists to read; see "Phone lane" below |
| **F4-04** | **Self-explain 1: the phone's app allow-list** - Jarvis can now explain it | `GET /api/phone/apps` - the allow-list read the explanation rests on (`self-explain-apps`) | **BLOCKED** - `404 {"error": "not found"}` on F3 | ask "which apps may you open?" and judge the answer | **BLOCKED-owner-away** |
| **F4-05** | **Self-explain 2: which model is answering** - Jarvis can say which one and why | `GET /api/models` - `current` / `previous` / `installed` (`self-explain-model`) | **PASS (read only)** - `current=qwen3.5:9b previous=qwen3:8b installed=15` | ask "which model is answering, and why?" and judge the words | **BLOCKED-owner-away** |
| **F4-06** | **Self-explain 3: the read-only flight price radar** - Jarvis can explain it | `GET /api/decks` - the `radar` list the explanation rests on (`self-explain-price`) | **PASS (read only)** - `ok=True decks=0 radar=0` (the list is there and honestly empty) | ask about the price radar and judge the answer | **BLOCKED-owner-away** |
| **F4-07** | **Plugins list / toggle by chat** - "list my plugins", "turn that one off", one card per change | **No HTTP probe exists, by design.** `changelog.d/2026-11-02-plugin-switch-by-chat.md` says it in its own words: *"there is no `GET`/`POST` for any of this"* - two model tools only (`plugin_list`, `plugin_switch`) | **BLOCKED** - nothing read-only to call; see "Not probed, and why" | say "list my plugins", then turn one off, then back on (one card) | **BLOCKED-owner-away** |
| **F4-08** | **DEF-028: the Live wording** - stop promising that every sentence is voice-checked | `GET /api/asks_first` - the `fixed:live` row's `note` (`def028-live-words`). PASS bar = the false promise is gone | **FAIL** - the live note still reads *"Every sentence is still checked for your voice..."*. That is DEF-028 itself, on the build, not a harness fault | read the same line on the phone and in the desktop Help | **FAIL (measured, agent-driven)** on the phone - the LIVE screen in build 0.2.3635 still says "Every full sentence is checked for your voice on your PC; once this session is verified, a short reply is trusted without a check." The corrected "checked once per Live session" line is only in Settings > "What asks first", so the two phone screens contradict each other; that is DEF-028's phone half, still unfixed. See "Phone lane" below |
| **F4-09** | **Goals progress log** - record progress on a goal, read the log back | `GET /api/goals/no-such-goal-probe/progress` - answers `no such goal` once the route exists; that is the only read-only proof (`goals-progress`) | **BLOCKED** - `404 {"error": "not found"}`: the route is not in F3 | add a real progress line and read it back | **BLOCKED-owner-away** |
| **F4-10** | **Wake word** - "Hey Jarvis" and whether it is on | `GET /api/version` → `capabilities.voice.wake_phrase` / `wake_word_enabled` (`wake-word`) | **PASS (read only)** - `wake_phrase=hey_jarvis wake_word_enabled=False` | say "Hey Jarvis" and watch it wake | **BLOCKED-owner-away** |
| **F4-11** | **Live voice check** - one check per Live session, not per sentence | `GET /api/voice/live` - the session state the check belongs to (`live-voice-check`) | **PASS (read only)** - `state=ended on=False session=6 ended=owner` | start Live by voice and watch whether it asks again | **BLOCKED-owner-away** |
| **F4-12** | **Approvals / fingerprint** - approve a card with the phone's fingerprint | `GET /api/pending` and `GET /api/devices` - the queue, who decided past cards, and which devices may decide (`approvals-read`, `devices-read`) | **PASS (read only)** - `pending=0 history=20 decided_by=['desktop_spotlight','field-test-2026-11-02','phone']`; devices `This PC, OnePlus, Pixel 9` | approve one card with the thumb on the phone | **BLOCKED-owner-away** |

Supporting reads that are not features of their own but tell you the harness is talking to a healthy
backend (all **PASS** on F3): `build-version`, `build-status`, `data-health` (`checks=6 warn=0`),
`voice-status` (`enrolled=True samples=48 threshold=0.35`), and `goals-read` (`goals=0`, limits
present - this one also carries F4-09's read half).

## Counts on live F3, from `pre-deploy-probe.txt`

| verdict | probes | sub-rows A | sub-rows B |
|---|---|---|---|
| PASS | 11 | 5 (all "read only") | 0 |
| FAIL | 1 | 1 (F4-08, the known DEF-028) | 0 |
| BLOCKED | 5 | 6 | 12 |

The 17 probes are not 1:1 with the 24 sub-rows: several probes are supporting health reads, and
F4-07 has no probe at all.

The B column is the F3 reading and stays as it was. The phone lane later re-graded three B rows without
the owner: F4-01B, F4-02B and F4-03B are **BLOCKED-no-UI-in-this-build**, and F4-08B is a **measured
FAIL** - see "Phone lane" below. The A column is unchanged.

## Where the F4 route names come from (so they can be checked)

The F4 code was **in branches, not on `main`**, when this harness was written - `main` is at
`dba25cc7d`. Each expected route below was read out of the branch that builds the feature, not out of
a guess, and the local copy of `docs/JARVIS-API.md` stops at section 177, so the habits/mood section
is the branch's own text:

| route | read from |
|---|---|
| `GET /api/habits`, `GET /api/habits/week` | `origin/feat/habits-mood-2026-11-02:backend/jarvis_habits.py` (`PATH`, `WEEK_PATH`) and `.dsh-scratch/HABITS-MOOD-2026-11-02/api180.md` §180.1, §180.3 |
| `GET /api/mood?days=N` | `origin/feat/habits-mood-2026-11-02:backend/jarvis_mood.py` (`PATH = "/api/mood"`) and `api180.md` §180.2 |
| `GET /api/goals/<id>/progress` | `origin/feat/goals-progress-2026-11-02:backend/jarvis_goals.py` (`_goal_route`, `handle_get`) and that branch's `docs/JARVIS-API.md` route table |
| `GET /api/phone/apps` | that branch's `docs/JARVIS-API.md` §176.2, on `main` already at `dba25cc7d`; the route is simply not in the deployed F3 build |
| the `fixed:live` note text (DEF-028) | `origin/fix/def-028-live-words-2026-11-02:backend/jarvis_asks_first.py`, and `docs/defect-register.tsv` row **DEF-028** |

If the F4 deploy ships a different path, the harness will report it honestly as **BLOCKED - route not
in this build**, which is exactly the symptom to look for on a re-run.

## What this matrix does NOT say

- **No B row is an owner pass.** The owner is away; every row that needs his voice, his thumb or his
  eyes stays BLOCKED-owner-away until he is at the machine. Two conditions were later measured by an
  agent without the owner and are recorded separately in "Phone lane" below: F4-01B, F4-02B and
  F4-03B are BLOCKED-no-UI-in-this-build, and F4-08B is a measured FAIL.
- **No A row is a claim about F4.** Every A verdict above is dated and was measured on F3. The
  habits, mood, week, phone-apps and goals-progress routes are **absent from F3** - that is the
  expected pre-deploy state, not five defects.
- **A PASS on an A row is the wire, not the feature.** `self-explain-model` passing says
  `/api/models` answers truly; it says nothing about whether the sentence Jarvis speaks about it is
  right. Only a B row can say that, and B is BLOCKED.
- **F4-08's FAIL is the defect, not the harness.** It is the one cell expected to flip to PASS on
  the F4 build; if it is still FAIL after the deploy, the wording branch did not land.

## After the F4 deploy

1. Run the harness again (one line, from the repository root):

   ```powershell
   python .dsh-scratch\FIELD-TEST-2026-11-03\probe.py | Tee-Object .dsh-scratch\FIELD-TEST-2026-11-03\post-deploy-probe.txt
   ```

2. Copy the new verdicts into the A cells, with the new date and build, leaving each `was ...` note
   in place so the earlier reading stays visible (the older matrices' convention).
3. Fill a B row only when the owner has actually driven it. Until then it is
   **BLOCKED-owner-away** - never "probably fine".

## Not probed, and why

- **`/api/plugins` - does not exist and is not meant to.** The plugin feature is two chat tools, not
  a route; see F4-07. Probing a route that the design says will never exist would be inventing
  evidence.
- **`/api/selftest`, `/api/health`, `/api/features`, `/api/settings` - do not exist on this build**
  (all four answered `404 {"error": "not found"}`). They were candidates, they were checked, and
  they were dropped rather than guessed at. `/api/version` is the closest thing to a self-test the
  HUD actually serves, and it is `build-version`.
- **Anything that writes.** No card approved or denied, no setting changed, no plugin toggled, no
  Live session started, no goal or habit or mood row created - those are B rows or they are not
  tested at all. The harness is GET-only by construction.

## AGENT-DRIVEN EVIDENCE — 2026-11-03 evening (never counted as an owner PASS)

**Provenance.** The owner delegated the field-test driving to the paired DeepSeek session. Every row below was driven against the live Jarvis backend on this PC through the same `POST /api/chat` the HUD uses - header `X-Jarvis-Client: hud`, `stream: true`, and the newest user turn carrying `"provenance": "typed"` - on 2026-11-03 evening. The full answers and the raw logs are in `AGENT-DRIVEN-RESULTS.md` and the `agent-drive*.log` / `agent-drive*.json` files in this folder.

**The grading rule, in plain words.** These rows are graded **AGENT-DRIVEN (AGENT-PASS)**. They are evidence, **NOT** owner field PASSes, and they must never be added to any owner-PASS count or tally - every table and count above stays exactly as it is. The project rule says a probe PASS is not a field PASS, and an agent is not the owner (`docs/FIELD-TEST-MATRIX-2026-10-11.md`). The agent typed the sentences and read the answers back; that is not the owner speaking them and judging them by ear or eye. Every owner-only row remains **BLOCKED** exactly as it was.

**Words used here.** A *card* is the approval card Jarvis shows before a change. A *receipt* is the little record that lets `undo` put a change back.

**Live state.** The run put back what it touched. The sun-and-moon switch was turned off and then back on; the final read is `/api/sky` -> `{"show": true}`, which is where it started. Anti-Slop was turned on by an early attempt and turned back off; `/api/antislop` -> `{"enabled": false}`. No approval card was raised by any row (`pending: []` before and after each row), and no card was ever approved or denied. This is as recorded in `AGENT-DRIVEN-RESULTS.md`; this section does not re-read the live backend.

**The F4 B rows recorded in this section.**

| Row | What was driven | Result (AGENT-PASS / AGENT-PARTIAL) | One-line evidence | Owner PASS? |
|---|---|---|---|---|
| **F4-05B** | Asked `which model are you using` in chat - the phrasing the fast path accepts. | **AGENT-PASS** | The answer says "You are running qwen3.5:9b on this PC, under the 'General' preset ..." - it matches `GET /api/models` (`current=qwen3.5:9b`) and `GET /api/presets` (`current=general`). | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F4-04B** | Asked `what can you open on my phone` - the phrasing the fast path accepts. | **AGENT-PASS** | The full allow-list explanation: the list ships empty, it lives under `[phone_apps]`, adding or removing one app raises one card naming its friendly name and package id, `control_phone` is off by default, the phone needs the adb cable, and `com.jarvis` is refused - matches `GET /api/phone/apps` (`count=0, empty=true`). | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F4-06B** | Asked `what is the price radar showing`. | **AGENT-PASS** | The price and flight radar is OFF by default and read-only (it never books or buys), with an honest empty answer - as `decks=0 radar=0` on `GET /api/decks`. | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F4-07B** | Asked `what plugins do you have` - the list half only. | **AGENT-PARTIAL** | The answer names 22 installed plug-ins and a catalogue of 48. The switch-one-off half was **not driven** - it needs a card. | **No** - still BLOCKED-owner-away, because an agent is not the owner. |

**Not recorded here originally.** This appendix was written before the phone lane finished. The phone lane then drove part of it, and those results are in "Phone lane" below: F4-01B, F4-02B and F4-03B are BLOCKED-no-UI-in-this-build; F4-08B is a measured agent-driven FAIL; F4-09B stays BLOCKED (no goal exists, and creating one would write owner data). Nothing in this section changes any count in this file.

**One cross-reference.** The click-through page's own sentence for F4-05 - "which model is answering me, and why that one?" - is **not** accepted by the fast path; it falls through to the local model. That page-sentence problem is written up as open finding 1 in `MATRIX-F5.md`, and every row above used an accepted phrasing instead.

## Phone lane - 2026-11-03 evening (build 0.2.3635, agent-driven)

**What was driven and how.** The paired session drove the installed Android app on the owner's phone: CPH2419 OnePlus, Android 15 / SDK 35, app `com.jarvis.client` 0.2.3635 (versionCode 1000003635, read from `dumpsys`, not guessed). Driver: monkey launch + `uiautomator` dump + tap-by-bounds + `screencap`. No approval card was tapped, no setting was changed, `pending: []` was checked before and after, and the action history stayed at 20. All Jarvis phone screenshots are black by design (`FLAG_SECURE`), so the `uiautomator` XML dumps are the evidence, not the PNGs. Full evidence: [`PHONE-DRIVE.md`](PHONE-DRIVE.md) and the `phone/` folder (171 uiautomator dumps, 13 PNGs, 5 evidence text files).

**Grading rule.** These are **AGENT-DRIVEN** results, not owner field PASSes. "BLOCKED-no-UI-in-this-build" means the screen the row needs is not in this APK - that is a build fact, not the owner having skipped the row. Nothing here is added to any owner count in this file, and every F4 A cell above is unchanged.

| Row | Result | Evidence |
|---|---|---|
| **F4-01B** | **BLOCKED-no-UI-in-this-build** | No Habits section in build 0.2.3635; the backend read-only check answered `GET /api/habits` -> 200 with `habits=[]` |
| **F4-02B** | **BLOCKED-no-UI-in-this-build** | No Mood section or chart on Reminders; `GET /api/mood?days=7` -> 200 with `latest=null` |
| **F4-03B** | **BLOCKED-no-UI-in-this-build** | No Week-in-review screen; weekly filing reads `on=false`, `job=null`; the last complete week (10-27..11-02) predates F4 landing on 11-03, so no filed line exists. Read-only counts recorded (habit 0, goal 0, reminders 7, mood 0/7) and explicitly **not** a pass |
| **F4-08B** | **FAIL, measured** | The corrected "checked once per Live session" line is in Settings > "What asks first", but the LIVE screen still says "Every full sentence is checked for your voice on your PC; once this session is verified, a short reply is trusted without a check." The two phone screens contradict each other; that is DEF-028's phone half, still unfixed. Evidence: `phone/F4-08B-live.xml`, `phone/F4-08B-evidence.txt`, `phone/F4-08B-live.png` (black by design) |
| **F4-09B** | **BLOCKED-owner** | No goal exists on this PC, and creating one writes the owner's data; the agent did not create one |
| **F4-10B** | **BLOCKED-owner** | Wake word switch is ON, but "Listen on this phone" is OFF |
| **F4-11B** | **BLOCKED-owner** | Live is idle, and "Trust Live fully (default)" is the setting the owner must judge |
| **F4-12B** | **BLOCKED-owner** | App lock is off and fingerprint-for-approvals is "Risky only"; the approval queue is empty, so there is no card to approve |

**DEF-028 note.** The defect already exists in the register; its phone half is a likely amendment or reopen rather than a new row, and that decision is deliberately left to the next phone PR. **Not filed here.**

**What does not change.** F4-04B, F4-05B, F4-06B and F4-07B stay as recorded in the AGENT-DRIVEN appendix above (agent-driven, never owner PASS). F4-09B is the one row the owner still closes when a goal exists.
