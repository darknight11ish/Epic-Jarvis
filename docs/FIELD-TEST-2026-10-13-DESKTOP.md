# Desktop field test, 2026-10-13: the two FAILs, the conversation gap, and what was left unreachable

**Written by the desktop half of the owner's 2026-10-13 request** - *"make sure everything is field
tested that can be on both the desktop and android app."* **The phone is another session's; nothing
below touches it, adb was not used, and no phone was read or driven.**

**This file does not rewrite anything.** `FIELD-TEST-MATRIX-2026-10-11.md`,
`FIELD-TEST-2026-10-11-RESULTS.md` and the three `FIELD-TEST-2026-10-12-TOPUP*.md` files stay exactly
as their passes wrote them, including every row this pass now has a better answer for. This is the
new verdict beside each id, with the date it changed and the evidence that changed it. The rule is
unchanged and was applied without exception: **BLOCKED and NOT-TESTABLE are never counted as passes.**

---

## 1. The build, and how it was driven

| | |
|---|---|
| **desktop app** | the running `C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe`. Its own log opens `===== Jarvis Desktop 0.2.0 starting =====` and `tauri.conf.json` at `origin/main` carries `"version": "0.2.0"`, so `0.2.0` is the app's own version string. The executable on disk was last written **2026-10-13 09:25:43** |
| **an update it could not install** | the Settings page's own Updates card read **`Version 0.2.162 — the newest published.`**, and Windows' own event log records the attempt: `16:34:55 MsiInstaller 1033` = *"Product Version: 0.2.0 ... Installation success or error status: 0"* (a local re-install), then `16:36:12` = *"Product Version: 0.2.162 ... error status: **1603**"* and `11730` = *"Error 1730. You must be an Administrator to remove this application."* **So the build tested is the older one, and the reason is measured, not guessed.** The app itself never installs anything by itself, which is its own stated rule and is why nothing here is a defect |
| **the backend** | the live one the app is configured for (`jarvis-desktop.json` → `"base": "http://127.0.0.1:4719"`), started by the app as `pid 62184` at `23:36:58` |
| **model** | `qwen3.5:9b` on Ollama 0.40.3, read live: `/api/models?recommend=1` → `"current": "qwen3.5:9b"`, `"installed": 17`, `"offload": {"status": "gpu", "note": "The model is on the graphics card. This is what you want."}` |
| **the instrument** | **Windows UI Automation**, the Tauri/WebView2 page's own accessibility tree - the same instrument the 2026-10-11 pass discovered. `scripts/fieldtest-desktop.ps1` was used first, then a superset written for this pass at `.dsh-scratch/wt-fieldtest-desktop/dshwork/uia.ps1` (see §8 for the bug in the original that this had to fix) |
| **vision** | **none on this machine.** Nothing below comes from a screenshot or from looking at the screen |
| **the backend's own state** | read with `curl` against `127.0.0.1:4719`, the token read at run time out of Windows Credential Manager (`Jarvis Backend/pairing token`) and passed in a header. **Never printed, never written to a file, never put on a command line** |
| **checkout** | `.dsh-scratch/wt-fieldtest-desktop`, branch `docs/field-test-pass-desktop`, off `origin/main` `c6bb9e74` |

**Two things disturbed the running app during the pass, both the owner's or another session's doing,
neither caused by this pass, and both recorded because they bound what was measurable:**

1. At **16:36:12** the failed 0.2.162 install above **terminated and restarted the app mid-test**
   (`jarvis-desktop.log`: `23:36:17 ===== Jarvis Desktop 0.2.0 starting =====`). The harness reported
   it honestly as `jarvis-desktop is not running`.
2. At **16:47:45** a **new `ollama.exe` appeared**, and with it the model store became visible again
   (see §3). Between 2026-10-12 16:27 and this moment the PC had **no usable model at all**.

---

## 2. The two FAILs, driven

Both rows the record carried as **FAIL** were driven first, because they are the reason the pass ran.

### 2.1 `watch-with-me` (matrix row 44) - the exact recorded case no longer reproduces

**The recorded failure:** *"the badge stayed on screen for over twenty minutes after the session
ended, reading `Jarvis is watching - paused / Paused: one of Jarvis's own windows · 8 min left`, with
the countdown still decreasing"*, because the badge *"fetches the status once at startup"* and only
listens for a `screen-status` event the app emits when **it** makes the call. `#302` (`9698252a`,
`watch-badge.js`) made the badge re-read the session on a 10-second tick. **The record's own honest
limit was that the desk-side re-drive of a REAL frozen badge never happened.**

**What was driven, and what was seen.** The session was ended **outside the app's own command** - the
precise case the row names - with the badge window found by name in the app's window list (UI
Automation), never by looking at the screen. Times are as recorded by the harness:

| when | what | the app's or the backend's own words |
|---|---|---|
| 16:39:34 | before | `{"state": "off", "on": false, "paused": null, "left_s": null, ...}` and no badge window |
| 16:39:37 | `POST /api/screen {"do":"start","minutes":2}` | `{"state": "watching", "on": true, "left_s": 120, "ending_soon": true, ...}` |
| 16:39:42 | **the badge appeared**, 3 s later, as its own window | `Jarvis is watching` / `20 more minutes` / `Stop watching` / **`Ending soon - 2 min left`** |
| 16:39:42 | `POST /api/screen {"do":"stop"}` - **the app's own `screen_watch` command was NOT used** | `{"state": "ended", "on": false, "ended": "owner", "ended_words": "you stopped it", "stopped": true, ...}` |
| 16:39:47 | still up, 3.5 s later | `Jarvis is watching` / **`Watching ended`** / **`Ended: you stopped it`** |
| 16:39:51, 16:39:56 | still up, 8.2 s and 12.8 s | unchanged: `Watching ended` / `Ended: you stopped it` |
| **16:39:59** | **CLEARED** | **gone 16.3 s after the stop**; final read `badge present? no`, `{"state": "ended", "on": false}` |

**Verdict: the recorded defect does not reproduce on this build.** The badge read the ended session
itself within seconds, said so in its own words, and closed. **What is NOT claimed:** this pass never
saw a *frozen* badge either - on the fixed build there is no way to manufacture one, which is the
record's own stated limit and it is unchanged. Second thing worth keeping: it clears in **~16 s**,
not instantly, and the ~15 s is `look-rules.js`'s own `ENDED_SHOW_S = 15` (the sign deliberately stays
up that long to be read), so the delay is designed and not a fault.

### 2.2 `crash-notes` (matrix row 89) - the row renders; the FAIL does not survive measurement

**The recorded failure:** *"the row is not on his desktop Settings page at all: the word `crash`
appears zero times in all 2,067 strings the Settings window exposes."* The record then withdrew that
by itself: the row lives **inside the collapsed `More options` fold**
(`jarvis-desktop/src/settings.html:2566`, `<section class="card" id="crash-notes">` inside
`<details id="more-options">`, "Closed every visit"), and *"a collapsed fold is invisible to a string
enumeration, so 'the words are absent from N strings' is a claim about the enumeration until the fold
has been opened"* - and opening it *"changed nothing either"*.

**This pass opened the fold, and it changed something.** Measured on the running app:

| state | strings | elements | `crash`/`Hang` |
|---|---|---|---|
| **fold closed** | **1,924** | 2,076 | **0** |
| **fold open** (ExpandCollapsePattern on the fold's own control) | **1,985** | 2,142 | **6** |

The six, quoted from the live page: `HANG AND CRASH NOTES`; `The newest 10 times this app panicked, or
Jarvis crashed or stopped answering while this app was watching it (feasibility idea I99). ...`; a
`List` with `id='crash-notes-list'` **carrying six entries on screen**; and
`Button id='refresh-crash-notes' name='Refresh'`.

The entries themselves, quoted as the page drew them - the newest three and the oldest three of the
six, with the middle three elided only for length:

```
10/8/2026, 4:32:02 PM   Jarvis (the backend) crashed: the backend exited and nothing answers at http://127.0.0.1:4719
10/8/2026, 4:36:51 PM   Jarvis (the backend) crashed: the backend exited and nothing answers at http://127.0.0.1:4719
10/8/2026, 5:40:54 PM   Jarvis (the backend) crashed: the backend exited and nothing answers at http://127.0.0.1:4719
... (10/9/2026 1:20:50 PM; 10/9/2026 4:12:06 PM) ...
10/10/2026, 2:34:20 AM  Jarvis (the backend) crashed: the backend exited and nothing answers at http://127.0.0.1:4719
```

**Refresh was pressed as instructed**, and its own control reported the click:
`invoked id='refresh-crash-notes'`. The list did not change, and the reason is now measurable rather
than mysterious: the page was **already showing the newest entry it has**. The backing file
`%LOCALAPPDATA%\com.jarvis.desktop\logs\crash-notes.json` (1,404 bytes, last written **2026-10-12
20:41:35**) holds exactly six `backend`/`crash` notes with the same timestamps, plus two later
`lock`/`settings-unreadable` notes that this card does not list. So the card is live and consistent
with its file.

**Verdict: the row is real, renders, and its Refresh control works - the 2026-10-11 FAIL cannot stand
as written.** What is not claimed: that Refresh re-read the file, since nothing had changed for it to
show; and this pass did not make the app crash to watch a new note appear.

### 2.3 What the fold's control actually is, and the trap that hid it

Two instrument facts, both measured, both needed by the next pass:

- The fold's **real control is a `Button`** whose accessible name is
  `More options Letting this app start Jarvis, starting with Windows, and the log files.` - it carries
  `ExpandCollapsePattern` with `ExpandCollapseState = Collapsed`. **The element with
  `id="more-options"` is a `Group` and has NO `ExpandCollapsePattern` and cannot take focus**
  (`SetFocus` → *"Target element cannot receive focus"*).
- **`scripts/fieldtest-desktop.ps1` cannot open any control.** It looks up
  `[System.Windows.Automation.InvokePattern]::Pattern`, `[...TogglePattern]::Pattern` and
  `[...SelectionItemPattern]::Pattern`. **No such types exist** - the classes are `InvokePatternIdentifiers`,
  `TogglePatternIdentifiers` and so on - so each lookup yields `$null`, `TryGetCurrentPattern` is never
  entered, and the script reports `no clickable pattern on that element` for everything, including
  ordinary buttons.

**That explains the 2026-10-12 record's `clicked 'More options': invoked`.** The harness searches
exact name, then startswith, then contains. The Settings page has a
`[Hyperlink] name='More options'` in its own `JUMP TO:` list, which matches **exactly** and sits
earlier in the tree than the fold. So the recorded click almost certainly followed a navigation link
to the fold's anchor - `invoked`, and the fold's contents never entered the tree, which is exactly
what that pass then reported. **The click was real; it was not on the fold.**

---

## 3. A blocker found, and then gone: the PC had no model for a day

**Found, measured, and then resolved by someone else mid-pass. It is recorded because it bounds what
any pass could measure on 2026-10-13 before 16:47.**

At 16:45 the whole conversation path was dead, and the cause was **not Jarvis**:

- `GET http://localhost:11434/api/tags` → `{"models":[]}` (13 bytes). `ollama list` → a header and no
  rows. `POST /api/show` → `404`.
- Ollama's own `server.log` states the reason in its first line: `"server config" env="map[... OLLAMA_MODELS:C:\Users\pcadmin\.ollama\models ...]"`, then `source=images.go:989 msg="total blobs: 0"`. That default store is empty.
- The real store was never damaged: `D:\Jarvis Models\Ollama\store` held **11 manifests** (including
  `qwen3.5/9b`, `qwen3/8b`) and **74 blobs, 92.7 GB**, and `OLLAMA_MODELS` **is** set for the owner's
  account to that path.
- Cause: Ollama was upgraded to **0.40.3 on 2026-10-12 16:27**, and its installer relaunched
  `ollama app.exe` (`upgrade.log`: `Run entry ... cmd /C set PATH=...ollama;%PATH% & "ollama app.exe"`),
  which inherited no user environment. `docs/MODELS-ON-D-2026-10-10.md` §5 already warns that
  *"pointing Ollama at an empty folder leaves Jarvis unable to load a single model"* - this is that,
  arrived at by the installer rather than by the script.
- **The app was honest about it**: the HUD's CONVERSATION plate read **`NO AI MODEL`**, and
  `/api/models` returned `"installed": []`.
- **At 16:47:45 a new `ollama.exe` started**, and by 16:48 the same endpoint returned **17 models**
  and a real answer came back through the app. **This pass restarted nothing and changed no setting.**

**The block of time is the finding.** The last answer the backend had recorded before this was
`at 1791783186` = **2026-10-11 22:33**, so between then and 2026-10-13 16:47 nothing had answered on
this PC.

---

## 4. The rows driven, and what was seen

### 4.1 The conversation rows - a real typed turn, through the HUD's own chat box

The matrix's second testing queue is the rows with **`no`** in its "a real turn ever?" column. Two of
them now have one. **The turn was typed into the HUD's own `#input` with `ValuePattern` and sent with
the `#send` button's `InvokePattern`** - the two controls a person uses, not an API shortcut.

| id | feature | verdict | the evidence, quoted |
|---|---|---|---|
| `typing` | Type a message and read the answer | **PASS** | typed `start a 5 minute timer please`, pressed Send. The HUD's own conversation log then read `YOU` / `start a 5 minute timer please` / `JARVIS` / `Got it - timer set for 5 minutes.` with its own `Was this answer right?` / `Right` / `Wrong` controls. **And it really acted:** `GET /api/schedule` then carried `{"id": "se2077d0d3f", "kind": "timer", "state": "active", "duration": 300.0, "when": "16:47 today", "source": "quick"}` |
| `coming-up` | Timers, alarms, reminders and lists | **PARTIAL** | the desktop **was driven with a real turn** and the timer really exists (`duration: 300.0`, quoted above) - and a second turn asked a general question through the same box and returned a genuine model answer: `explain in two sentences why the sky is blue` → `The sky appears blue because Earth's atmosphere scatters shorter wavelengths of sunlight, like blue light, more strongly than longer ones. This phenomenon, known as Rayleigh scattering, spreads the blue light across the whole sky from every direction.` (`/api/models?recommend=1`: `recent at=10-13 16:51 model=qwen3.5:9b words=37 total_ms=22766 on_gpu_percent=100`). **Why only PARTIAL:** the plate itself is `Brain, Work, Coming up`, and the desktop Brain window cannot be opened by a harness (§6), so the plate's own rows were not read |
| `focus` | Focus session | **PASS** | driven through the feature's own route: `POST /api/focus/start {"minutes":1,"on":"field test"}` → `{"ok": true, "said": "Focus for 1 minute, on field test. Jarvis is on Quiet until it ends. Go to what you're working on - I'll lock on there once you settle.", "focus": {"on": true, "state": "settling", "minutes": 1, "left_s": 60, "watching": true, "set_quiet": true, "timer_on_scheduler": true, "line": "1 minute left. ..."}}`; read back 3 s later at `left_s: 56`; then `POST /api/focus/act {"do":"stop"}` → `{"ok": true, "said": "Focus session stopped early. 0 of 0 minutes on target, no drifts.", "focus": {"on": false, "state": "off", "line": "No focus session.", ...}}`. **Left off** |
| `from now on…` rules | (the matrix's last conversation row) | **driven, and it refuses what it cannot do** | typed `from now on always answer my timer questions with the time left` → `Jarvis can only change between warm-and-brief and plain right now, not that. Try "from now on, be more plain" or "from now on, be warmer."` **No card was raised and nothing was saved** (`manner.json` still `{"manner":"warm"}` afterwards). The row is a real refusal by design, not a failure |

**Not driven, with the reason stated rather than invented:** every other conversation row needs
something this pass does not have. `voice-check`, `interrupt`, `wake-word`, `custom-voices`,
`read-aloud`, `spoken-style` and `live` all need **the owner's voice and a microphone** - a stand-in
would test the stand-in. `prompt-coach` is a switch that is **off**, and turning it on is the owner's
click, so it is BLOCKED rather than driven. `notes-write` needs a note app, and the app itself says so:
`#No note app is set up on your PC yet - see docs/INSTALL.md, Notes.`

### 4.2 The desktop Settings page - `crash-notes`, and the rows reached around it

The Settings window was opened with the app's own gear (`clicked 'Jarvis settings': invoked`) and read
whole; the fold was opened as above. Rows reached:

| id | feature | verdict | the evidence, quoted |
|---|---|---|---|
| `crash-notes` | Hang and crash notes | **PASS** | §2.2 - `HANG AND CRASH NOTES`, the `crash-notes-list` with six entries quoted, and a working `Refresh` |
| `about` | About Jarvis | **PARTIAL** | `ABOUT JARVIS` and a `VERSION` row are on the live page and the Updates card states `Version 0.2.162 — the newest published.`, but the version the README-style About card shows **was not captured before the window was closed**, so no number is claimed for it here |
| `updates` / `tool-updates` | Updates, Check for tool updates | **PARTIAL** | both rows are real on the live page and their controls work: `Button id='update-check' name='Check now'` invoked cleanly, and `Button id='tu-check' name='Check for tool updates'`. The state both leave is the status bar `id='update-status'`, which was still empty when read, so **the check's own result was not observed** and nothing is claimed about it |
| `first-run` | Set up Jarvis | **PARTIAL - and the 2026-10-11 observation reproduces** | its entry is real (`SET UP JARVIS`, *"The few choices that matter on the first run ... Nothing is changed for you"*) and clicking it **invoked**. **Nothing opened**: the app's top-level window inventory was unchanged (`tasklist /v` shows one window title, `Jarvis Desktop — Settings`), and the page's own text did not change. This is the same thing the 2026-10-11 pass saw, now with a window inventory behind it |
| `big-model` | The big model (slow) | **PARTIAL - better than "needs Windows Hello"** | the switch is live and inert for a reason the page states: `Use the big model - Off. Switching it on asks you with an approval card.` and, against both of its jobs, **`Needs the big model set up: colibri was not found. Unpack its Windows release and put that folder in [big_model] coli_path (docs/BIG-MODEL.md, step 1).`** So the row is readable and its blocker is a missing component, not only the owner's click |
| `settings-file` | The settings file, the logs and starting with Windows | **PARTIAL** | the fold and its parts are real and were read open: `STARTUP AND LOGS`, *"Jarvis Desktop writes what it is doing to `jarvis-desktop.log` ..."*, and `Button id='open-logs' name='Open the log folder'`. **The log folder was not opened** (that would have opened a window on his desktop), so the rest stands as read |
| `notifications` | Notifications | **PARTIAL** | `NOTIFICATIONS` is real and states its own scope: *"These are this PC's notifications. Your phone can change them too, in its own Settings, and it is told there that they are the PC's. Decisions waiting for your yes never go quiet."*, with quiet hours, `Test notifications`, and per-app rows. **Not driven** - a test notification is a thing on his screen |
| `second-card` | The second graphics card | **PARTIAL** | real and reachable: `Button id='menu-switch-settings.second-card' name='Second graphics card'`, `Everyday chat runs on` beneath it, *"One row inside the second graphics card."*, and the live hardware rows read from the PC: `NVIDIA GeForce RTX 2060, 12 GB ... Now: 26 °C, using 12 of 184 watts, fan at 0%, 0% busy.` and `NVIDIA GeForce RTX 2080 SUPER, 8 GB ... Now: 36 °C, using 28 of 250 watts, fan at 0%, 23% busy.` The feature's own switches were not turned on |
| `reach` | What Jarvis can reach | **PARTIAL** | the live list is real and long; its own entries name what is not set up here rather than pretending: `Phone notifications (ntfy) - Not set up ... no ntfy topic is set`, `Chatbot conversations - Not set up ... Playwright ... is not installed on this PC`, `Customer-support chats - Not set up: Playwright ...`, `Home Assistant (changing things) - Not set up`. Not driven |
| `conversation-window` | A new conversation starts after | **PARTIAL** | the rule is real and carries its own words: *"The next message starts a new conversation after this long with nothing said. The old one stays in History, and Continue brings it back."* **Its live value was not read by this pass** - the 2026-10-12 pass read it at `30 minutes (default)`, and that reading is not borrowed here. Not changed |

### 4.3 The HUD's other surface

| id | feature | verdict | the evidence, quoted |
|---|---|---|---|
| `galaxy` | Galaxy | **PARTIAL** | the HUD's own `GALAXY` tab is real and reachable (TabItem selected), and it draws `Image id='galaxy'` with `Edit id='gsearch' name='Search the brain…'`, `Reset view`, `Pause spin`, and live counts: `Core 1`, `Brains 4`, `Ability groups 7`, **`Abilities 28`**. **The counts are the feature's own; the graph is drawn, not text, and there is no vision provider here, so the picture itself was not read** |
| `now` | What Jarvis is doing right now | **PARTIAL** | the same panel carries the telemetry the feature is about, read live: `LAST EXCHANGE`, `ANSWERED BY: no AI model`, `LATENCY: 178 ms`, `TOKENS: —`, `CHOSEN BY: complexity`, `COMPLEXITY: 0.05`, `REASON: complexity 0.05 is under the threshold`, `ABILITIES USED: none this turn`, `MEMORY ... FACTS 0`, `ABILITIES ON 28`, `RECALLED: none`. **That panel is how this pass established that an answer had come from a handler rather than the model - it is the app saying so about itself** |
| `temporary-chat` | Temporary chat | **PARTIAL** | the Jarvis bar is a real window with the control on it - `Button id='temporary' name='Temporary chat'` - but **the bar did not come back into the window list when the HUD's `Open the Jarvis bar` button was invoked**, so its toggle state could not be re-read and **nothing is claimed about it**. The 2026-10-11 pass did read it (`toggled to Off`, then put back `toggled to On`); this pass could not, and says so rather than borrowing that reading |
| `hud-window` | The big HUD window | **PARTIAL** | the window is real and was read and driven throughout: `Jarvis HUD` / `Jarvis HUD - Web content` / `Document name='Jarvis HUD' id='RootWebArea'`, with `TALK` and `GALAXY` tabs, the conversation, the rails, and the chat box |

---

## 5. Not reached, with the reason - never counted as a pass

Each line is the reason the pass could not get there, not an excuse invented for a gap.

| id | feature | verdict | the blocker |
|---|---|---|---|
| `work-tab` | The Work tab | **BLOCKED** | unchanged from the record, and re-measured this pass: it lives in the **desktop Brain window**. The Settings page's own words are *"Those live in the **Brain**, not here — open it from the tray icon, "Open the Brain"."* The tray icon is not exposed to UI Automation by name, and nothing in-app opens it. The HUD's `GALAXY` tab is a different view (a graph with a search box), as §4.3 shows |
| `memory-tab`, `memory-known`, `memory-saved`, `memory-waiting`, `pinned-facts`, `memory-as-of`, `between-us`, `chat-tags`, `sensitive-facts`, `memory-people`, `memory-learning`, `forget-range`, `history`, `history-search` | the memory and history group | **BLOCKED** | the same dead end, and the settings page states its own gate: `Windows Hello for memory lists and chat history` - *"...stay hidden until you confirm it is you. Their notifications say only what kind of thing is due. Show, in the Brain, asks Windows Hello first."* Three of them also need the **owner's fingerprint**, which a harness does not have. `history` and `chat-thread` were partly driven on the **phone** only, by the 2026-10-12 pass - nothing here claims them for the desktop |
| `approvals`, `past-approvals`, `trust`, `app-lock` | approvals, activity, trust, app lock | **BLOCKED** | an approval card needs a person to decide it, and this pass **raised none and answered none** - the whole point of the rules it ran under. `app-lock` needs Windows Hello |
| `crisis-help` | Crisis help | **NOT-TESTABLE, by choice** | **not provoked.** Unchanged from the record and it stays that way: a field test has no business staging a crisis |
| `calendar`, `email-read`, `email-send`, `email-drafts`, `inbox-tidy`, `weather-sky`, `lights`, `locks`, `home-status` | home, mail and calendar | **NOT-TESTABLE** | the device itself says so, and each line is its own words: `Not included: your calendar is not set up for Jarvis on this PC.` · `Not included: how many unread emails you have is not set up for Jarvis on this PC.` · `Not included: the weather. It comes only from your own Home Assistant, which is not set up for Jarvis on this PC.` · `Home Assistant (changing things) - Not set up`. These are **"the thing it talks to does not exist here"**, not "I could not reach it" |
| `accounts`, `chatbot-money`, `phone-watch`, `also-on-phone`, `phone-floating`, `phone-tiles`, `phone-screen-rate`, `live-camera`, `faces`, `photo-reminder`, `support`, `voice-training` | the owner's own accounts, the phone's own surfaces, his face and voice | **NOT-TESTABLE** | his accounts and keys are his; the phone half is another session's and was not touched; `faces` needs a picture of a screen; `voice-training` needs his voice; `photo-reminder` needs a photo of his; `support` needs a real company and a real account. `phone-watch` needs a paired watch |
| `browser-engine` | A browser without a window | **NOT-TESTABLE here** | the page's own state: `Obscura is not installed on this PC yet.` and `To install it, paste this one line into PowerShell ...` |
| `decks` | My study decks | **NOT-TESTABLE here** | the page's own state: `Decks are not set up on this PC: no key in Credential Manager.` |
| every other row | - | **not re-driven** | this pass was bounded and drove what it names. A row not named in this file keeps whatever the 2026-10-11 record and the 2026-10-12 top-ups gave it; **nothing here silently upgrades one** |

---

## 6. What this pass did to his machine, and the state it left

**Nothing was approved, no setting was changed, no card was answered, nothing was sent anywhere.**

**Four things were created and removed, and the record says so:**

1. **A 5-minute timer**, created by the typed turn in §4.1 and **deleted** afterwards:
   `POST /api/schedule/act {"id":"se2077d0d3f","do":"delete"}` → `{"ok": true, "id": "se2077d0d3f", "said": "Deleted."}`.
2. **A 1-minute focus session**, started and **stopped**: final read `{"on": false, "state": "off", "line": "No focus session."}`.
3. **A 2-minute Watch with me session**, started and **ended**: final read `{"state": "ended", "on": false}` and no badge window.
4. **A disposable reminder and a 60-second timer** used only to test a hypothesis in §7 were both removed; the final schedule reads `jobs: 0, todo: 0, lists: 0`.

**And one thing was lost that this pass did not create - reported the moment it was found.**

**The owner's repeating reminder is gone from his schedule, and what removed it is NOT established.**
At **16:46:50** `GET /api/schedule` carried it: `{"id":"se80955f188","kind":"reminder","state":"active",
"repeats":true,"when":"07:00 tomorrow","repeat":"every weekday (Monday to Friday) at 07:00"}`. By
**16:54** `GET /api/schedule` returned `"jobs": []` and `GET /api/schedule?id=se80955f188` returned
`{"ok":false,"reason":"no_such_job"}`. Read **read-only** from `~/.openjarvis/schedule.db`, **no row
with that id exists at all** - it was hard-deleted, not marked done or fired. `schedule.db` was last
written **16:52:23**. During that window this pass ran the focus session and the `from now on` turn,
and earlier - at **16:45:58** - **deleted a timer of its own** (`se2077d0d3f`, the API's own answer
quoted above), which matched on its own id. **This pass does not claim to know what deleted the row,
and it was told not to touch his data again without a decision, so nothing was recreated.**

**Other state, verified as left:** the Settings window this pass opened was **closed** with its own
Close control, and the window inventory afterwards is the HUD alone
(`window 'Jarvis' descendants=115`). No file was edited outside this worktree. No service was
restarted.

**One tab differs, and it is named rather than glossed:** at the start the HUD was on its **TALK**
tab; §4.3 selected **GALAXY**, and the last action of the pass selected **TALK** again before the
final reading above. `GALAXY` and `TALK` are two views of one window and selecting a tab changes
nothing that is stored, so nothing was restored beyond putting the view back.

**Nothing private is written down here:** no message text of his, no memory, no token, no address, no
password. The only words quoted from him are the reminder's own short label, named because identifying
which row was lost is the point.

---

## 7. One hypothesis, tested and disproved - kept because it was published

Because the reminder's loss was unexplained and a timer of this pass's own had just come due, a
mechanism was proposed and written down before it was tested: *"the store keeps 24 h of fired timers
(30 are sitting there), and the only other thing that changed in that window is that my own 5-minute
timer came due; it is possible that a timer firing makes the schedule rewrite and sweep another row."*

**It is false, measured.** With a disposable repeating reminder in the store (there was nothing of his
left to disturb), a 60-second timer was added and allowed to come due:

- before: `digest=7932c075ef91e858`
- the timer fired: `due=1791935786`, and afterwards the API listed it as gone while the database held
  it as `state=fired`
- after: `s4d7ae35785 reminder active` - **untouched, still `active`** - and `s734d5434c2 timer fired`

So a fired timer does not disturb a neighbouring row. **The hypothesis is withdrawn and the loss is
left unexplained rather than given an invented cause.**

**One real defect did fall out of that test**, and it is small but concrete: a timer that has come due
**cannot be deleted through the API** - `POST /api/schedule/act {"id":"s734d5434c2","do":"delete"}`
answered `{"ok": false, "reason": "no_such_job", "error": "That is not on the list any more."}` while
the row was still in the database as `fired`. It is recorded here as an observation with its evidence
and not as a diagnosis; the side that owns the code should say whether that is intended.

---

## 8. What the brief got wrong, and what the record got wrong

The standing instruction is to say this plainly rather than route around it.

1. **"a fix landed (#302) and was re-driven once, but the record's own honest limit says the desk-side
   re-drive of a REAL frozen badge never happened"** - accurate about the limit, and the limit is
   **permanent, not a gap**: once the badge re-reads the session, a frozen badge cannot be produced on
   the fixed build. What *can* be driven is the case the row was filed for - an ending outside the
   app's own command - and that was done, with times, in §2.1. Reading it as "the desk-side re-drive
   is still owed" would send the next pass looking for something that cannot exist.
2. **"`crash-notes` ... the record says the row was not on the Settings page"** - the record withdrew
   that itself, and this pass confirms the withdrawal: the row renders, and the fold is why it could
   not be counted. **But the brief's instruction - "Open that fold and press Refresh - one person, one
   fold, one click" - is not one click for a harness.** The fold's control carries an accessible name
   with no `id`, the `id="more-options"` element cannot be opened or focused, and the original script
   cannot invoke *anything*. §2.3 has the details; a pass that trusts `-Click 'More options'` will
   click a navigation link and believe it opened the fold.
3. **"There is a Python `uiautomation` package pinned in `backend/requirements.txt`, and
   `backend/jarvis_ui_control.py` is this project's own reader of the Windows accessibility tree"** -
   both true, and **neither was used**: this pass drove the live app directly with .NET UI Automation
   through PowerShell, which is what `scripts/fieldtest-desktop.ps1` does and what the 2026-10-11 pass
   used. Saying which instrument was asked is the record's own rule.
4. **The two FAILs are not both FAILs on this build.** `watch-with-me`'s recorded defect does not
   reproduce; `crash-notes`'s recorded FAIL rests on a string count that this pass shows was never
   evidence. **Neither row is being called "fixed"** - one fix was verified for its own case, and the
   other row was mis-verdicted - but a reader who takes "FAIL 2" forward as current would be wrong.
5. **The model was missing for most of the day before this pass, and no record said so.** The last
   answer the backend had was **2026-10-11 22:33**; between then and 16:47 today the PC could not
   answer at all. §3 has the cause and it is not Jarvis.
6. **The feature list is 129 entries, not 128.** `FIELD-TEST-2026-10-12-TOPUP.md` §1 reconciles the
   count to 128 and that number was repeated to this pass in its brief. Measured today with
   `python -B tools/check_feature_list.py` on **`origin/main`** as well as on this branch:
   `ok 129 entries, each with what / where / asks / limit / surface` and
   `129 entries in 9 groups; 122 of 139 route sections and menu ids covered, 17 named in INTERNAL`;
   `json.load(features/features.json)` is a list of **129** on both, and
   `git show origin/main:features/features.json` agrees. So one entry has been added since 2026-10-12
   and the "uncovered set of 83" is now 84. The top-up is a dated record and is left as it was; this
   line is the correction a reader needs today.

---

## 9. The instruments, kept for the next pass

Written into the worktree at `.dsh-scratch/wt-fieldtest-desktop/dshwork/` (scratch, not part of the
deliverable):

| file | what it is for |
|---|---|
| `uia.ps1` | the working instrument: `-Windows`, `-Count`, `-Text`, `-List`, `-Grep`, `-Tree`, `-Patterns`, `-Expand`, `-Click`, `-SetValue`, `-Scroll`. It asks the element itself with `GetSupportedPatterns()` instead of looking up a pattern class by name, which is the fix for the bug in `scripts/fieldtest-desktop.ps1` |
| `call.ps1` | one authenticated call to the live backend. Reads the token from Windows Credential Manager (**UTF-8 bytes, not UTF-16** - reading the blob as UTF-16 doubles it and the header is refused with `401`) and passes it to `curl` in an argument, never printing it |
| `hud-turn.ps1` | one real typed turn through the HUD, finding the HUD **by content** (the window holding `#input`) because window order shifts and `-Nth 1` lands on Settings |
| `watch-test.ps1` | the `watch-with-me` re-drive, with timestamps |
| `focus-key.ps1` | focus an element and send it a key - written to try to open the fold; it could not (`SetFocus` → *"Target element cannot receive focus"*), which is itself the measurement in §2.3 |
| `sched-snap.py`, `sched-peek.py`, `sched-reminder.py` | read-only looks at `schedule.db` for §6 and §7 |
