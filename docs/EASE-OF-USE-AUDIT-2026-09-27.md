# Ease-of-use audit - 2026-09-27

**Question (the owner's words):** "How easy is it to set up Jarvis the first
time or customize later, how easy is it to use and understand Jarvis as
someone new to the program? How customizable is everything and how do I
review past changes or chats and so forth?"

**How it was done.** Seven reviewers, each looking at one area: setup,
customizing, everyday use, reviewing the past, recovery, a newcomer's walk
through, and a critic who re-checked the other six and compared Jarvis with
other assistants. Their reports are in `docs/ease-audit-2026-09-27/` (`setup.md`,
`customize.md`, `everyday.md`, `history.md`, `recovery.md`, `newcomer.md`,
`critic.md`); the screenshots they took were not kept in the repository.
Everything was read-only, from the repository at commit
`ad44732`. The chair (me) re-checked the claims this report leans on
against the files. The windows were drawn in a browser on a copy, with test
data, **not** on Windows and **not** on a phone.

---

## 1. Summary, with scores

1. **First-time setup: 2/10.** For anyone but you it cannot be done: the main backend files have no download (`docs/INSTALL.md:85-97`). For you it is about 24 steps, 6 programs, a build from source and a 43-character key typed by hand.
2. **Customizing: 5/10.** Almost every setting has a plain sentence under it, and "stricter is instant, looser asks with a card" works the same everywhere. But settings are spread over about 11 places, and tools, the built-in voices and email can only be changed by editing a file.
3. **Everyday understanding: 5/10.** Approval cards, "Offline" messages and Stop are clear. But nothing tells you what you can say, the phone hides its own menu row, and about 60 words on everyday screens are jargon.
4. **Reviewing the past: 4/10.** Memory is the best in its class (dated facts, Forget, "what did you know on this date?"). But chats cannot be searched, and there is **nowhere** to see past approvals or settings changes.
5. **Recovery: 4/10.** Both apps share good plain error messages. But after a PC restart Jarvis is off and the advice points at a button that does not exist under that name. The best check tool is hidden, and there is no backup.
6. **Three things are wrong today and you should hear them plainly.** (a) "What asks first" says web search "Asks you first, every time", but a search from your own question runs with no card. (b) The phone suggests your home Wi-Fi address, but it can only connect over Tailscale or Meshnet. (c) Web search looks set up in Settings, but the AI cannot use it until you edit a file.
7. **Biggest single win:** a short "Things you can say" list (already approved as I116, not built) in place of the 10 shortcut rows in the empty Jarvis bar.
8. **Biggest missing piece:** a read-only list of past approval cards (approved, denied, timed out). The PC already sends it, and both apps ignore it.
9. **The reviewers proposed about 94 fixes.** After merging duplicates, **9 "do first" items** remain. Together they add 0 new settings, 0 new card kinds and 1 already-approved list, and the Jarvis bar ends up with *fewer* rows.
10. **Four questions for you** (section 5). Nothing else here needs your decision before it is built.

---

## 2. The newcomer's journey, in short

A smart non-developer gets the GitHub link and follows only what the README
and the apps say (`newcomer.md`, walk 1).

| Step | What happens | Stops? |
|---|---|---|
| 1-2 | README: clear, plain, honest. "Follow docs/INSTALL.md" (`README.md:71-87`) | No |
| 3-5 | Installs Git, Python and Ollama with one line; clones the repository | No |
| **6** | **INSTALL 1.3: "there is no download link" for the backend** (`INSTALL.md:85-97`). The README never warned them | **Everyone but you stops here**, after installing 3 programs |
| 7 | A command with *your* folder in it (`C:\Users\pcadmin\...`), 6 times in INSTALL.md | Guesses |
| 9 | "Tools are off until you name them": edit a 1,290-line settings file | Guesses at names |
| 10 | 5 GB model. Voice is 7 more commands in a 10,434-line README | Long |
| 11 | Start Jarvis in PowerShell. **After every reboot, do it again** (nothing says so) | Daily friction |
| **12** | **Build the desktop app from source**: Visual Studio build tools, Rust, Node.js, then `npm run tauri build`. There is no installer, because the update signing key is empty (`tauri.conf.json:118`) | **Hours; the scariest part** |
| 14-15 | First launch opens 4 things at once. The big HUD shows "CLOUD", "escalate" and "FREE-TIER BUDGET" (browser preview). The walkthrough says the icon is "next to the clock", but Windows 11 hides it under `^` | Confused |
| 16 | Presses Alt+Space: 10 shortcut rows, **0 example sentences** | "What can I ask?" |
| **19-21** | Phone: needs Tailscale (**no install steps anywhere**). "Let my phone reach this" **does nothing** unless the desktop starts Jarvis, and the setting does not say so. Also needs an **administrator** firewall line | **Most likely place to give up** |
| **23** | Type a 43-character random key on a phone keyboard, in a hidden field. The key is shown on the PC for 60 seconds with no Copy button. One typo gives "refused", with no hint which character | **Second most likely** |

**Worst stopping points, in order:**
1. The backend cannot be downloaded (step 6). Only a decision about what goes public fixes it; no app change can.
2. Building the desktop app (step 12). Your 10 minutes making the signing key fixes it (professionalism #2, still open).
3. Getting the phone to reach the PC (steps 19-21). Docs plus two sentences in Settings.
4. The 43-character key (step 23). QR pairing (I102, already decided) fixes it.
5. After install: nothing says what to say, and no tools are switched on, so Jarvis looks like it can do little.

**A month later** (walk 2):
- **Change how Jarvis talks:** tray → Settings → scroll about 9 screen-heights to card 8 of 21. There are 2 choices.
- **See what it learned last week:** 2 clicks, and it works well.
- **Find Tuesday's chat:** no search and no weekday on the dates, so you work out the date and scroll.
- **See what you approved:** impossible.

---

## 3. Ranked fixes

Sizes: **S** = under a day, **M** = a few days, **L** = a week or more.
"Joins" names the plan it belongs to, so nothing is built twice. Every item
keeps the five rules: nothing new leaves the PC, nothing approves by itself,
and nothing is loosened without a card. Items marked **feature** need their
own follow-up audit under CLAUDE.md's standing rule.

### Do first (small, big effect)

| # | Fix | App(s) | Size | Joins |
|---|---|---|---|---|
| 1 | **Fix what is untrue.** (a) The web search row in "What asks first" (`backend/jarvis_asks_first.py:135,144` vs `backend/rebuilt/jarvis-framework.toml:185-193`), and merge its two "Read your calendar" rows. (b) About says every action "stops and asks first" (`settings.html:1277-1278`); the FAQ says the same about the internet (`:1011-1013`). (c) The deep-question note says "the answer is kept" (`brain.html:381-382`), but answers last only until a restart. (d) Show "The answer came from the cloud model, so it was not kept" where `answer_kept` is false (neither app reads it today). (e) The phone's refusal message suggests 192.168.x.x and `.local` (`OwnNetwork.kt:39-43`), but the phone can only connect to `ts.net`/`nord` names (`network_security_config.xml`). (f) The phone FAQ (`FaqScreen.kt:203`) and INSTALL 3.4 quote messages that no longer exist. (g) "Settings → Startup and logs" is now under "More options". (h) "backend.log" exists only when the desktop starts Jarvis; the logs are scrubbed, not "nothing hidden" | backend, both, docs | S | New. Same kind of error as the approvals audit's wording fixes |
| 2 | **Starting Jarvis, in true words.** The `jarvis_not_running` message sends you to "Settings, Start Jarvis" (`plain-errors.js:39-42`). The real button is "Start" inside the closed "More options" box, and it is greyed out unless supervision is on. Name that place and open it. Rename "Start Jarvis when Windows starts" (`settings.html:1245`, which starts only the desktop app) to "Start Jarvis Desktop when Windows starts", with one line under it. Under "Let my phone reach this", say it works only when the desktop starts Jarvis (`sidecar.rs:482-485`) | both (one shared word list, `tools/gen_plain_error_cases.py`), desktop | S | The shared plain-errors list |
| 3 | **Phone: show the way around.** Show the menu row by default (`AppearanceStore.kt:644`, `navAlwaysShown = false` today; keep "hide" as an Appearance option). Rename "Platform checks" to "Checks and setup". On empty Home, add **one** quiet line: "Talk: teach Jarvis your voice first →" until your voice is trained, then "What can I say?" | phone | S | UI audit #15 (Home's *one* new line; this is that line) and the cheap first half of UI #14 |
| 4 | **"Things you can say"**: about 5-8 real sentences Jarvis already understands without the AI model ("set a timer for 10 minutes", "what did I miss?", "tell me when an email from Alex arrives", "focus for 30 minutes"). They **replace** the 10 shortcut rows in the empty Jarvis bar, with one line "More: right-click the Jarvis icon by the clock". Also one "what can you do?" command answered from the same list, 3 examples on walkthrough screen 2, and a Help answer in both apps. Tapping a line fills the box and never sends | backend, both | M | Feasibility **I116** (approved "Now"), UI audit **#19** (shorter shortcut list). **Feature** |
| 5 | **One wording pass.** Linked → Connected; "Stale — reconnecting" → "Catching up…"; Faculties → Model; Long Fuse jobs → Background jobs; drop "State of mind" and "route badge"; "Stop learning" → "Pause background learning". One name for the bar, "Jarvis bar" (today also "Spotlight", "Quickbar" and "Summon Jarvis"). Retitle Faces from "Jarvis Reactor Kit" to "Choose Jarvis's face" and fix its false sentence "nothing on this desktop draws one yet" (`faces.html:152-153`; the widget does). Tray "Settings…" → "Settings and help…" | both | S | UI audit **#20** (Faces details); the shared-words tests |
| 6 | **Make error details selectable.** The details under an error are the thing to send with a bug report, but they cannot be selected (desktop: `user-select: none`, `style.css:75`; phone: no `SelectionContainer` anywhere). One CSS line, plus one wrapper on the phone. No Copy button, because the clipboard can sync off the PC | both | S | New |
| 7 | **History: small, true, useful.** Add the weekday to dates ("Tue 22 Sept", `history-view.js:216-227`). Next to Delete, say "Deleting a chat does not forget facts learned from it". Add a filter box on "What Jarvis knows about you" (filters the loaded list; no new route) | both / desktop | S | New |
| 8 | **Docs and the check tool.** (a) README line 65 gives `python backend\selftest.py --preflight`. It uses the word INSTALL says never to use, and it checks the wrong folder (18 FAIL when run here). Give the real line. (b) `selftest.py` checks first that the folder holds `jarvis_hud.py`, instead of printing 76 FAILs. (c) INSTALL: Tailscale install steps for both devices, "needed even at home". (d) "Keep the PC awake" (alarms ring on the PC, `backend/README.md:8133-8139`), plus a preflight WARN when Windows sleeps on mains power. (e) An "Updating everything" section, plus one FAQ answer "How do I update Jarvis?" that the ~78 "run apply-patches.ps1" messages can point to. (f) A README warning that the backend is not public. (g) Uninstall lists all 7 Credential Manager entries, not 2. (h) A lost-phone answer. (i) The patch script keeps a log file | docs, backend, desktop | S | Professionalism **#13** and **#22** (still open); feasibility guardrail 9 (a preflight line, not a switch) |
| 9 | **Your 10 minutes: make the update signing key.** CI then publishes a ready installer, and step 12 of the journey becomes "download, then click past SmartScreen" | you | S | Professionalism **#2** (still open) |

### Then

| # | Fix | App(s) | Size | Joins |
|---|---|---|---|---|
| 10 | **Desktop Settings: jump list at the top**, with cards reordered: everyday first, rare in the middle, read-only last, FAQ near the top, and a "Chat history and learning → Brain" line. Today it is 21 cards, about 15 screens tall, with no map | desktop | S-M | UI audit **#13** |
| 11 | **Past approvals list ("Activity")**, read-only. One row per card: its title (already safe for a lock screen), Approved / Denied / Timed out, when, and which device. It sits next to the Undo shelf (desktop Brain → Work; phone Inbox) and never shares a list with waiting cards (keep `JarvisApi.kt:121`'s guard). Built from the `history` the PC already sends (`JARVIS-API.md:208`). Every loosening already raises a card, so this also answers "did I turn that on?". **First, check on your PC what the gate's `history` rows hold** (`jarvis_gate.py` is not in this repo) | backend check, both | M | Question 2. Reuses the existing list, not a new ledger (the feasibility audit warns against one). **Feature** |
| 12 | **"What did I miss?" covers more**: cards that timed out, facts saved automatically, "tell me when" matches (today skipped, `jarvis_schedule.py:1322-1328`), and finished jobs. No new button, because saying it already works | backend | M | The one shared scheduler/digest (2026-09-25 decision) |
| 13 | **Speaking speed and a built-in voice choice** in both apps (today file-only, `tts_speed`, `tts_speaker_id`) | backend, both | M | Feasibility **I28** ("Now"), step 3 voice upgrades. 2 new settings, which is exactly guardrail 13's limit |
| 14 | **Reading tools switched on from the PC**: calendar, email, notes and home status, each with the existing loosen card plus Windows Hello. Every other tool's line says in plain words that it is file-only | backend, desktop | M | The 2026-09-26 "What asks first" PC-only list. Question 3 |
| 15 | **Email, calendar and Home Assistant secrets into Credential Manager**, entered in a PC-only box like the web search keys. Today they are Windows user environment variables, which Windows stores as plain text | backend, desktop | M-L | Feasibility step 5, **Security G3** (already queued) |
| 16 | **Phone Settings screen**: move voice, security, look and settings out of Brain and "Checks". Ship it alone, because it is the biggest CI risk | phone | L | UI audit **#14**, professionalism **#15** |
| 17 | **Phone welcome** (one still picture and one sentence above pairing), and a line in ARCHITECTURE §8 saying why the phone has no 3-step tour. Also a §8 line for "Findings" being phone-only. Both are needed for CLAUDE.md's parity rule | phone, docs | S | UI audit **#16** |
| 18 | Show the pairing key in groups of 4 (display only) until QR pairing lands | desktop | S | Feasibility **I102** (QR, decided) |
| 19 | "Find it for me" for the Python path when turning on "Let Jarvis Desktop start and stop Jarvis". Supervision stays off by default | desktop | M | Recovery fix; no plan yet |
| 20 | Search your own old chats, **if you say yes** (question 4) | backend, both | M | CLAUDE.md 2026-09-26 "searching past chat words waits". **Feature** |
| 21 | Add 4 missing steps to the guided-setup design: "can your phone reach this PC?", tools, email/calendar, "Jarvis starts by itself". It stays "Later", after QR pairing | design doc | S | Feasibility **I119** |

### Not worth it (now)

Each of these was proposed by at least one reviewer and dropped by the
critic. Most add a button or screen that a "do first" item makes unneeded.

- **A gear, History or "What did I miss?" button in the Jarvis bar.** Item 4's footer line and "Things you can say" cover it, and the bar already has 4 icon-only buttons.
- **A 4th walkthrough screen, or a "screen 0".** Put 3 examples on screen 2 instead; the walkthrough stays 3 screens.
- **A search box in Settings.** The jump list does the job.
- **A "show" eye on the phone's key field.** QR pairing replaces it, and a visible key is a new way to leak it.
- **A zip of `.openjarvis` or a "Back up now" button.** These would put every memory unscrambled on a USB stick. Wait for the encrypted backup (I96; your open question 3 in `OWNER-QUESTIONS-2026-09-27.md`). A zip of the backend *program* folder in the docs is fine.
- **The desktop writing Jarvis's listening address into the settings file.** That is a new write path to a safety setting; the words in item 2 fix the trap.
- **A reader for the audit log to list settings changes.** About 26 modules write free-form entries to it, not redacted. Item 11 covers loosenings.
- **"Carry on this chat", "Save a problem report", past-focus-session lists, a reset button per card, merging the learning controls.** Later, or unasked for.
- **Exporting a chat to a file.** It would break ARCHITECTURE §5's "encrypted or not kept … no plain-text path". Only you can change that rule, and nobody has asked.
- **Moving guided setup (I119) earlier.** It would build pairing twice, and it cannot fix the three worst blockers, which all happen before the app exists.
- **Pointing INSTALL to the CI "Actions" download.** Those files vanish after 14 days. The signing key (item 9) is the real fix.

**Budget check** (feasibility guardrail 13): do-first plus "then" add 2 new
settings (#13), 0 new card kinds, 0 new notifications, 1 new list (#11) and
1 already-approved list (#4).

### Earlier audits: still open (re-checked)

| Item | Status |
|---|---|
| Professionalism #2: no desktop installer (`tauri.conf.json:118` `"pubkey": ""`) | **Open** → do first #9 |
| Professionalism #13: your folder built into the scripts; no patch log | **Open** → #8 |
| Professionalism #15: phone has no Settings | **Open** → #16 |
| Professionalism #21: no `jarvis-client/README.md` | **Open** (not ranked; S, docs) |
| Professionalism #22: no single "what to send" page | **Open** → #8 |
| UI #13 (Settings jump list), #14 (phone Settings), #16 (phone welcome), #18 (Core/Ollama/LiteLLM dots), #19 (shortcut rows), #20 (Faces numbers) | **All open** → #10, #16, #17, #4, #5 |
| UI #9: Mind → Brain | Rename **done**; grouping **open** (already in your open question 5) |
| UI #4a: walkthrough colours | **Fixed** |
| Continuity #1 ("Hide memory lists" wording), #2 (Stop everything on the PC) | **Fixed** (tray row; still no bar button) |
| Feasibility I116 "Things you can say", I28 speaking speed (both "Now") | **Not built** → #4, #13 |
| Changelog | **Fixed** in the repo; not shown in either app |

---

## 4. How to look back at the past, today

"Brain" on the PC opens from the tray icon → "Open the Brain". On the phone,
open the menu row first by swiping down on the status line (it is hidden by
default), then Brain.

| What you want | Where on the PC | Where on the phone | What is missing |
|---|---|---|---|
| **Past chats** | Brain → **History** tab (2nd tab) → click a chat. 30 at a time, "Load older" | Brain → scroll to about the 25th section, "Chat history" → Open History | No search, no weekday, can't continue a chat, can't copy it out, no link from the Jarvis bar. A cloud answer shows as a blank reply with no reason |
| **Facts Jarvis saved by itself** | Brain → Memory → "Saved automatically" (date, device, "said again N times") | Brain → "Saved automatically" | No "this week" filter |
| **Every fact, forgotten ones too** | Brain → Memory → "What Jarvis knows about you" (greyed "no longer recalled", "Erased on …") | Not shown, on purpose (ARCHITECTURE §8) | No filter box |
| **What Jarvis believed on a date** | Brain → Memory → "What did you know on…" (type YYYY-MM-DD) | Brain → "What did I believe on this date?" | Works |
| **Save your memory to a file** | Brain → Memory → "Export everything" (JSON) | None, on purpose | No import; chats have no export |
| **Cards you approved or denied** | **Nowhere** | **Nowhere** | The PC sends the list; both apps skip it → fix #11 |
| **Cards that timed out while you were away** | **Nowhere** (a card waits 180 seconds, then vanishes) | **Nowhere** | → fixes #11, #12 |
| **Settings you changed** | **Nowhere** in the app. The PC's audit log in `%USERPROFILE%\.openjarvis\logs\` (one file a day, kept 90 days, raw text) | Nowhere | → fix #11 covers every loosening |
| **Timers, alarms and reminders that went off** | Brain → Work → Coming up → "Just went off" | Brain → Coming up | Shown for 1 hour only |
| **"What did I miss?"** | Say it, or Brain → Work → Morning briefing | Say it, or Brain → Morning briefing | Up to 1 day. Leaves out timed-out cards, auto-saved facts, "tell me when" matches and finished jobs → fix #12 |
| **"Tell me when" alerts** | The notification, then the job's row | Same | Readable for 1 day |
| **Background jobs** | Brain → Work → "Long Fuse jobs" | Inbox → Running | How long they are kept: not checked |
| **Undo something** | Brain → Work → Undo shelf | Inbox → Undo shelf | How long it keeps things: not checked (in your `jarvis_undo.py`) |
| **Deep questions** | Brain → Memory → Deep questions | Brain → Deep questions | Lost when Jarvis restarts, although the PC note says "kept" → fix #1 |
| **Focus sessions** | Last report card only | Same | The PC keeps 200 and shows 1 |
| **"Findings" (what Jarvis noticed)** | Only the HUD window | Brain → Findings | Parity note missing → fix #17 |
| **What changed in Jarvis itself** | `CHANGELOG.md` in the repository | Not in the app | No "What's new" in either app |

**In numbers:**
- Clicks to open one past chat: PC 4 from the tray; phone 3, plus a scroll past up to 24 sections.
- Places to check for "while I was away": 8 on the PC, with 5 different names.
- Search boxes for past things: 0 for chats, 0 for the fact list.
- Places that show past approvals or settings changes: **0**.

---

## 5. Questions for you

Four questions, none repeating the 2026-09-27 list. The first option is the
recommendation.

**1. Web search out of the box.** Jarvis ships with every tool switched off,
so the AI cannot search the web until you edit a file, even though you chose
SearXNG as the default.
- **a. Ship it with web search on** (recommended). Searches from your own question still need no card; after outside text they still ask.
- b. Leave it off, and make the app say how to turn it on.

**2. A list of past approvals.** A read-only list: each card's title,
Approved / Denied / Timed out, when, and from which device. It sits next to
the Undo shelf and has no buttons that decide anything.
- **a. Build it** (recommended). First I would need a look at what your PC's `jarvis_gate.py` keeps.
- b. Not now.

**3. Turning on reading tools from the PC app.** Calendar, email, notes and
home status would get an "On" switch on the PC. Each switch raises a card
plus Windows Hello, like "What asks first". Other tools stay file-only.
- **a. Yes, PC only, those four** (recommended)
- b. Keep all tools in the settings file.

**4. Searching your own old chats.** A search box in History, just for you.
The PC unscrambles your chats in memory to look and shows the matches on
screen. Nothing is saved, and nothing is handed to the AI.
- **a. Allow it now** (recommended). The 2026-09-26 "wait" was about Jarvis itself searching your words.
- b. Wait until memory ideas 1-4 are measured.

---

## 6. What nobody could check

- **Anything on a real Windows PC or a real phone.** There is no Windows host, and the phone app has no Android build here. How long downloads take, the size of the Visual Studio build tools, whether Windows' `tar` unpacks the voice files, and how the phone screens look and scroll were all not checked.
- **What the HUD shows with Jarvis really running.** Only the browser preview (sample data) was drawn, so the "CLOUD" and "escalate" rows may differ live. Nobody checked whether INSTALL's "demo · not connected" sentence is still right.
- **What your gate's `history` list holds and how long it keeps it.** `jarvis_gate.py` is only on your PC, and fix #11 depends on it. The same goes for the Undo shelf and background jobs (`jarvis_undo.py`, `jarvis_jobs`).
- **Whether the AI answers "what can you do?" or "talk more plainly" sensibly.**
- **Whether a hand edit of `jarvis-framework.toml` takes effect without a restart.**
- **Whether the phone shows that the PC's `one_moment_enabled = false` overrides its own switch.**
- **Whether Ollama starts itself at login on your PC.**
- **Whether the GitHub repository is public.** If it is private, a phone's browser cannot download the app without signing in.
- **Some counts are approximate.** The "run apply-patches.ps1" count (±5) and the jargon count (text drawn at run time is partly missed) are rough. Settings height came from test data (13,400-14,500 px). The critic corrected small counting slips in the reviewer reports: the tray has 18 rows, the HUD opens at 1280×820, the settings file has 38 sections and the phone Brain 38 items. This report uses the corrected numbers.
- **Some competitor facts are search summaries only**, because two help sites are blocked here (`critic.md` section 2).
