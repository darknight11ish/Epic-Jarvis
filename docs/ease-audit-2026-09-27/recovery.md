# Ease-of-use audit: when things go wrong (recovery lens)

Date: 2026-09-26. Read-only. Repository at commit `ad44732`.
Checked by reading the files named below, and by running
`backend/selftest.py --preflight` here twice (from `/tmp`, with
`PYTHONDONTWRITEBYTECODE=1`, nothing written to the repository;
`git status` was clean afterwards). No desktop windows were rendered for this
lens, so nothing below says how a screen *looks*, only what it *says*.

---

## In short (8 lines)

1. **The error words themselves are good.** Both apps share one list of 20 failures, each with a plain sentence, one thing to do, and usually one button. The words match word for word, checked by tests.
2. **The biggest trap: after a restart of the PC, Jarvis is not running, and the app's advice points at a greyed-out button.** "Start Jarvis when Windows starts" starts only the desktop app. Jarvis itself stays off unless a second, off-by-default setting is on.
3. **Nothing tells a newcomer the PC must stay awake.** If Windows puts the PC to sleep, the phone cannot reach Jarvis and alarms set from the phone do not ring anywhere until the PC wakes.
4. **About 78 messages say "run apply-patches.ps1", and none says where it is or gives the command.** Updating the whole system is three separate manual jobs with no single page.
5. **The best repair tool, the preflight check, is hidden.** It is not in INSTALL.md, the top README gives a command that uses the wrong word (`python`), and with a wrong folder it prints 76 failures.
6. **Sending a problem report is hard.** "Send the Details" is the advice, but the Details text cannot be selected or copied in either app, and with the default setup there is no backend log file at all.
7. **There is no backup and no restore.** The memory export has no import, and chat history cannot move to a new PC (its key stays in Windows Credential Manager).
8. **Some troubleshooting text describes messages that no longer exist** (the phone FAQ, and INSTALL.md section 3.4).

---

## Numbers

| What | Count | Where |
|---|---|---|
| Kinds of failure with shared plain words | 20 (19 with a sentence and a fix, plus "the PC said it in its own words") | `jarvis-desktop/src/plain-errors.js:33-136`, `jarvis-client/.../net/PlainErrors.kt:49-159` |
| ...with a fix button | 16 of 19 | same (3 have `none`: too old, feature off, unreadable) |
| ...whose fix is an action on the PC that neither app explains how to do ("restart Ollama", "restart Jarvis", "run apply-patches.ps1", or the greyed-out Start) | **10 of 19** | timeout, model_not_running, model_stuck, model_stopped, model_error, backend_too_old, feature_off, server_error, unreadable, jarvis_not_running |
| Message lines in the apps that say "run apply-patches.ps1" | ~53 desktop + ~25 phone (counted by grep over string lines, not comments; approximate) | e.g. `net/Briefing.kt:60`, `plain_errors.rs:109` |
| ...of those that give the path or the command | 0 | grep for `ExecutionPolicy Bypass` in both apps' source: no match |
| Preflight output, backend folder set wrong | 201 lines, **76 FAIL**, 0 pass | run here with `JARVIS_BACKEND=/tmp/nonexistent-backend` |
| Preflight output, `JARVIS_BACKEND` not set (as the top README's command does) | 18 FAIL, 1 pass; it checks the repository's `backend\` folder instead of Jarvis's | run here |
| Desktop FAQ questions / about something going wrong | 11 / 2 (Alt+Space, "got slow") | `settings.html:1007-1150` |
| Phone FAQ questions / about something going wrong | 16 / 1, and that one quotes a message the app no longer shows | `FaqScreen.kt:59-253`, `:203` |
| Windows Credential Manager entries Jarvis can create | 7 (2 pairing tokens, chat history key, Brave, Exa, Tavily, big-model key) | `jarvis_token_store.py:75,81`, `jarvis_chat_log.py:112`, `jarvis_search.py:382`, `jarvis_big_model.py:151` |
| ...listed in INSTALL.md's Uninstall section | 2 | `docs/INSTALL.md:722` |
| Separate jobs to update everything | 3 (backend: `git pull` + script + restart; desktop: rebuild + installer + SmartScreen's 2 extra clicks; phone: release page + APK) | INSTALL.md 1.2, 1.5, 2.1-2.2, 3.3 |

---

## What works (keep it)

- **One list of error words for both apps.** `tools/gen_plain_error_cases.py` writes one fixture; both apps are tested against it (`plain-errors.js:7-12`, `PlainErrors.kt:15-19`). Each has "what happened", then "what to do", then one button that goes to the right place (`main.js:803-816`: retry, reconnect, open Settings, open the Brain).
- **Secrets are scrubbed from the Details** before they are shown: token, keys, passwords, email addresses, Windows user name (`plain-errors.js:232-277`, `PlainErrors.kt:339-378`).
- **The backend's own sentences say what to do.** Example: a missing model says its name and the exact `ollama pull <name>` command (`backend/jarvis_agent.py:2116-2118`). A broken chat-history key says why and how to start again (`jarvis_chat_log.py:393-396`).
- **The preflight itself is excellent** once you reach it: every line is PASS/FAIL/WARN with one sentence and what to do, e.g. "Ollama is not answering ... Start the Ollama app from the Start menu, or run: ollama serve". It is read-only and never prints the token (`backend/README.md:9777-9826`, `selftest.py:1677-1692`).
- **The patch script cannot leave you half-done.** It rehearses on a copy, says "NOTHING HAS BEEN CHANGED" when it refuses, backs up every file, recognises older versions of patches, and has `-Revert` (`scripts/apply-patches.ps1:1-58`).
- **The phone keeps its last crash** and shows it on the next start with a Copy button, token removed (`platform/CrashLog.kt`, `ui/screens/CrashScreen.kt:78-102`).
- **The phone tells you when a newer app exists** (at most every 6 hours, nothing about you sent; `net/UpdateCheck.kt`, `platform/UpdateChecker.kt`).
- **Missed alarms are honest.** An alarm heard more than 10 minutes late shows as a silent "missed at 07:00" (both apps; e.g. `net/Schedule.kt:389,470,611`).
- **"Stop everything"** is on the tray now (`tray.rs:236`) and Alt+Shift+X, and on the phone.
- **Waiting words.** "Waking up the model - the first answer after standby takes a little longer." (`plain-errors.js:151`) stops a slow first answer from looking like a failure.
- **"Jarvis got slow"** has a real answer: a yellow line in the Brain when the model spills off the graphics card (`INSTALL.md` "When something goes wrong"; desktop FAQ `settings.html:1094`).

---

## What is hard, ranked by how much it hurts a newcomer

### 1. After the PC restarts, Jarvis is off, and the fix points at a greyed-out button (HIGH)

Evidence:
- The setting reads **"Start Jarvis when Windows starts"** (`settings.html:1245`). It writes a Run key for the *desktop app* only (`src-tauri/src/autostart.rs:13-18`). The backend is started by the app only if **"Let Jarvis Desktop start and stop Jarvis"** is on, and that is off by default (`settings.html:1180-1192`; `sidecar.rs:20-22`, "A setting, default off").
- INSTALL.md's default path starts the backend in a PowerShell window by hand (step 1.8, `INSTALL.md:227-251`), so after any reboot, or after closing that window, Jarvis is off.
- The words both apps then show: "Jarvis isn't running on your PC. The PC is on, but Jarvis is not started. Start it from the desktop app (Settings, Start Jarvis), then try again." (`plain-errors.js:39-42`, `plain_errors.rs:36-38`). There is no button called "Start Jarvis". The real button is **"Start"**, inside the closed **"More options"** box, under "Starting Jarvis for you" (`settings.html:1173-1222`), and it is disabled unless supervision is on and a program path is typed in (`settings.js:338`).
- The error's button is "Try again", which will fail the same way.
- A supervised backend that crashes is not restarted; you press Start again (`sidecar.rs:395-410`, the slot is cleared, nothing respawns).

Fixes:
- **S, desktop:** rename the switch to "Start Jarvis Desktop when Windows starts", and add one line under it: "Jarvis itself starts too only when 'Let Jarvis Desktop start and stop Jarvis' is on (More options)." Show that line in amber when supervision is off.
- **S, both apps (one list):** change the `jarvis_not_running` fix to name the real place: "Start it: on the PC, Jarvis Desktop, Settings, More options, 'Starting Jarvis for you', Start. If Start is greyed out, turn on 'Let Jarvis Desktop start and stop Jarvis' first." Edit `tools/gen_plain_error_cases.py`, regenerate, then both apps.
- **M, desktop:** a "Find it for me" button next to Program/Arguments that fills in the real `python.exe` (the `py -3 -c "import sys; print(sys.executable)"` trick the note already describes, `settings.html:1199-1205`) and asks for the folder holding `jarvis_hud.py`. Then INSTALL.md can recommend supervision on for newcomers. **Owner's call:** supervision being off by default is a deliberate rule (`sidecar.rs:20-22`: a terminal-started backend must not be taken over). The fix keeps it off by default and only makes turning it on easy.

### 2. Nothing says the PC must stay awake (HIGH)

Evidence:
- No mention of sleep, power settings or keeping the PC awake anywhere in INSTALL.md, the desktop README or HARDWARE-PROFILES.md (grep for "asleep", "sleep mode", "power plan": no hits in INSTALL.md). Nothing in the desktop app stops Windows sleeping (grep for `SetThreadExecutionState` or `powercfg`: no hits).
- Alarms and reminders go off **on the PC**: "The phone sets no alarm of its own ... If the PC was off or asleep when something was due, it goes off once when the PC is back, and says 'missed at 07:00'" (`backend/README.md:8133-8139`). The phone says "They go off on your PC. This phone shows them while it is connected to it." (`net/Schedule.kt:143-144`), but never says "if the PC sleeps, nothing rings".
- "Also on my phone" (hand an alarm to the phone's own clock app) is decided but not built (grep for `ACTION_SET_ALARM`: no hits).
- The phone's own FAQ admits the gap: "a desktop that is simply asleep ... currently looks identical to a real error" (`FaqScreen.kt:207-212`).

So a newcomer who says "wake me at 7" to the phone at night can easily get no alarm, then a silent "missed" note later.

Fixes:
- **S, docs:** an INSTALL.md step "Keep the PC awake", one line: `powercfg /change standby-timeout-ac 0` (plus how to undo it, and what it costs in power).
- **S, both apps:** one extra sentence under "Coming up": "If your PC is asleep or off, nothing goes off until it wakes."
- **S-M, backend:** a preflight WARN when Windows is set to sleep on mains power (read with `powercfg`), so the check catches it before an alarm is missed. (Guardrail 9 style: a preflight line, no new setting.)
- Later: "Also on my phone" (already decided, 2026-09-26 "Quick wins") is the real fix for alarms; it should be listed as that.

### 3. "Run apply-patches.ps1" about 78 times, never how; updates are three separate jobs (HIGH)

Evidence:
- The phrase appears in ~53 desktop and ~25 phone message lines (e.g. "Your PC's Jarvis does not have the morning briefing yet - run apply-patches.ps1 on the PC.", `net/Briefing.kt:60`). None gives the folder, the full command, or "then restart Jarvis" consistently (only `backend_too_old` and `feature_off` say restart, `plain-errors.js:79-88`).
- A newcomer does not know that it lives in `scripts\` of the cloned repository, that it needs `-ExecutionPolicy Bypass`, or which `-BackendPath` to give (`INSTALL.md:121-127`).
- Five error kinds say "restart Ollama" or "Open Ollama" and four say "restart Jarvis"; neither app says how (Ollama: quit from its tray icon, start from the Start menu; Jarvis: depends on whether it was started by hand or by the app).
- Updating everything means three separate chains: backend (`git pull`, the script, restart), desktop (rebuild with `npm run tauri build`, installer, SmartScreen "More info" then "Run anyway", `INSTALL.md:263-294`), phone (release page, APK). No section in INSTALL.md is called "Updating" (grep `## Updat`: only in `jarvis-desktop/README.md:168`, which covers the desktop updater alone).
- The desktop updater is still off: `"pubkey": ""` (`tauri.conf.json:118`); Settings says so honestly (`settings.html:250-257`). Even when on, it updates only the desktop app, not the backend files.

Fixes:
- **M, both apps:** one "Update Jarvis on the PC" place: in the desktop's Settings, a short card with the exact one-line command (repository folder and backend folder filled in when known) and a Copy button, ending "then restart Jarvis"; on the phone, one FAQ answer with the same steps. The ~78 messages keep their short words and add "(how: Settings, Update Jarvis on the PC)". One home for the instruction (guardrail 1), not 78.
- **S, both apps (one list):** say how to restart Ollama in the four fixes that ask for it: "Restart Ollama: right-click its icon by the clock, Quit, then open Ollama from the Start menu."
- **S, docs:** an INSTALL.md section "Updating everything", in order: backend, desktop, phone, each one line.
- **S, owner's 10 minutes:** make the updater signing key (still unfixed from the professionalism audit, #2).

### 4. The preflight check is the right tool, and a newcomer will not find it (MEDIUM-HIGH)

Evidence:
- INSTALL.md never mentions it (grep for "preflight" and "selftest" in `docs/INSTALL.md`: no hits). Its instructions are at line ~9777 of the 10,434-line `backend/README.md`.
- The top README gives: "A live check of the whole setup: `python backend\selftest.py --preflight`." (`README.md:65`). INSTALL.md says never to use the word `python` on its own (`INSTALL.md:63-68`), and the line does not set `JARVIS_BACKEND`, so it checks the repository's own `backend\` folder instead of Jarvis's (`selftest.py:80`). Run here that way: 18 FAIL.
- With the folder set wrong (an easy typo in a long path with spaces): 201 lines and 76 FAIL, each module listed separately with "Run apply-patches.ps1", instead of one line saying "this folder has no jarvis_hud.py - check the path". Its verdict line then says "Each FAIL above says what to do", which is not true of 76 lines that all have one cause.
- Neither app can run it. The tray's "Run a status check" (`tray.rs:296`, `tray.rs:1253-1268`) only pings three services and says e.g. "1/2 online — offline: Ollama" (`commands.rs:1586-1592`), with no "what to do".

Fixes:
- **S, docs:** fix `README.md:65` to the real one-line command from `backend/README.md:9797` (with `py -3` and `JARVIS_BACKEND`). Add a step 1 to INSTALL.md's "When something goes wrong": run this line, read the FAILs.
- **S, backend:** in `selftest.py`, check first that `JARVIS_BACKEND` holds `jarvis_hud.py`; if not, print one FAIL ("This is not your backend folder: set JARVIS_BACKEND to the folder that holds jarvis_hud.py") and skip the per-file checks.
- **S, desktop:** make the tray status check's notification add one "what to do" line (reuse the shared words: Jarvis off -> `jarvis_not_running`'s fix; Ollama off -> "Open Ollama from the Start menu").
- **M-L, backend + both apps (owner's call):** a read-only `/api/preflight` route so a "Check everything" button can show the same PASS/FAIL list in the desktop's Settings and the phone's Platform checks. It is the natural "one home" for "is it working?". Owner's call because it adds a route that reads the token path and files.

### 5. Sending a problem report without leaking is harder than it looks (MEDIUM)

Evidence:
- The fix for `server_error` says "send the Details with a bug report" (`plain-errors.js:91`). On the desktop the Details sit in a `<pre>` (`index.html:621-625`) inside a page whose `body` has `user-select: none` (`style.css:73-77`); only `.markdown` turns selection back on (`style.css:980-985`), and the Details are not inside it. The "Copy" button copies the plain words, not the Details (`main.js:3888-3897`, `state.buffer`). On the phone the Details are plain `Text` with no copy and no selection (`ui/parts/Parts.kt:749-758`; no `SelectionContainer` anywhere in the app). So on both, the Details can only be read or photographed. (I did not run the apps; this is from the code.)
- With INSTALL.md's default setup (backend started by hand), there is **no `backend.log`**: the log file is written only for a backend the app started (`sidecar.rs:494-512`), and INSTALL.md says "Everything it prints goes here and nowhere else" (`INSTALL.md:251`). Yet Settings says "If Jarvis refuses to start, the reason is in backend.log" (`settings.html:1237-1239`) without that condition.
- Mixed messages about what is hidden: Settings and INSTALL.md say the logs are plain and "nothing in them is hidden or scrambled" (`settings.html:1238-1240`, `INSTALL.md:743-744`), but `backend.log` passes through `jarvis_scrub.py` (tokens, keys, passwords, emails, user name) once `log-scrub.patch` is applied (`backend/jarvis_scrub.py:1-24`; the script applies it, `apply-patches.ps1:363`). The advice "read it before you send it" is still right; the claim is out of date.
- The patch script keeps no log file ("Send the block above back", professionalism audit #13, still true: no `Start-Transcript` in `apply-patches.ps1`).
- There is still no single "what to send" page (professionalism #22): INSTALL.md's "When something goes wrong" covers the log folder, proxies and slowness only (`INSTALL.md:735-770`), not the phone's crash copy, the preflight, or the patch script output.

Fixes:
- **S, both apps:** a "Copy details" button beside Details (desktop: through `write_clipboard`; phone: Android clipboard). The text is already scrubbed. (The Brain's memory export avoids the clipboard on purpose because Windows can sync it, `brain.js:1738-1743`; the Details are short and scrubbed, so the clipboard is fine here - but say so in the code.)
- **S, desktop:** fix the two log sentences: "backend.log is written only when Jarvis Desktop starts Jarvis for you" and "passwords, keys and the pairing key are taken out; read it before you send it anyway."
- **S, script:** `Start-Transcript` to a file beside the backup folder, and say where it landed on the last line.
- **M, desktop:** "Save a problem report" in Settings: version and build, what the backend supports, the last ~200 lines of both logs, and the preflight summary, all through the same scrubber, to a file the owner picks (never sent anywhere). One home for "what to send".

### 6. No backup, no restore, and a chat-history trap (MEDIUM: rare, but it loses everything)

Evidence:
- The only export is the Brain's "Export everything" (facts only, to a JSON file, `brain.js:1736-1752`, `brain.rs:527-555`). There is no import of that file (no `memory/import` in `docs/JARVIS-API.md`), and no export on the phone (no `memory/export` in the phone's source).
- Jarvis's state is spread over `%USERPROFILE%\.openjarvis\` (memory.db, approvals.db, schedule.db, chat history and about twenty settings files - counted from file names in `backend/jarvis_*.py`), the settings file beside `jarvis_hud.py`, the desktop's `%APPDATA%\com.jarvis.desktop\`, and 7 Credential Manager entries. INSTALL.md's only word on backup is "your memory and facts. Back this up first." (`INSTALL.md:730`), with no how.
- The chat history is encrypted with a key kept **only** in Windows Credential Manager (`jarvis_chat_log.py:43-50,112`). Copying the folder to a new PC, or after reinstalling Windows, leaves a history that cannot be opened, and then "nothing new is kept" until the file is deleted (`jarvis_chat_log.py:393-396`). This is by design (rule 3), but nowhere is a newcomer told that a backup cannot carry chat history.
- The backend's own core files still exist only on the owner's PC ("that chat history the only backup", `docs/ARCHITECTURE.md:1186-1189`); the patch script's backups go inside the same folder (`INSTALL.md:134-136`), so one disk failure loses both.
- Uninstall lists 2 of the 7 Credential Manager entries (`INSTALL.md:722-724`).

Fixes:
- **S, docs:** INSTALL.md "Back up Jarvis": one PowerShell line that zips `.openjarvis`, the backend folder and the settings file to a named place, and a plain sentence: "Chat history cannot be moved to another PC or a fresh Windows; everything else can." List all 7 Credential Manager entries in Uninstall.
- **M, desktop (owner's call):** a "Back up now" button that writes the same zip to a folder the owner picks. Restoring facts from the Brain's export is L and an owner's call (it must not become a way to add facts without the usual rules).

### 7. Troubleshooting text that no longer matches the apps (MEDIUM-LOW)

Evidence:
- Phone FAQ: "It says "Cannot reach the desktop." Now what?" (`FaqScreen.kt:203`). That sentence is shown nowhere any more (grep: only the FAQ itself); the phone now says "Your PC isn't answering." (`PlainErrors.kt:51`).
- INSTALL.md 3.4 quotes two old messages, "Cannot reach the desktop… Check your private network" and "The desktop refused that token" (`INSTALL.md:703-709`); neither is the current wording.
- INSTALL.md says "Settings → Startup and logs" (`INSTALL.md:737,780,784`); that card is now inside the closed "More options" box (`settings.html:1173-1176`).
- On the desktop, which talks to Jarvis on the same PC, `connection_dropped` still says "check the private network is steady at both ends" (`plain-errors.js:56`). And the two sides disagree on a connect timeout: Rust calls it "Jarvis isn't running" (`plain_errors.rs:76-78`), the page's `classify` calls it "Your PC isn't answering ... Tailscale" (`plain-errors.js:171`).
- For a missing model, the model's name and the `ollama pull` line are only in the Details (`plain-errors.js:312-316`, the PC's sentence goes to `details`); the shown words say only "or install this one".
- The HUD window, when Jarvis is off, fills with sample data ("Everything below is sample data", `jarvis_hud.html:1868-1886`); INSTALL.md tells you to ignore its banner (`INSTALL.md:303-306`). I did not check whether that advice is still right now that the HUD goes through the app (`hud_proxy.rs`).

Fixes (all S): re-word the phone FAQ question to the current words and drop "currently looks identical" once item 2's line exists; update INSTALL.md 3.4 and the "Startup and logs" path; for `model_missing`, show the model name in the main words (the PC already sends it); give the desktop its own `connection_dropped` wording or drop "at both ends" there.

### 8. A lost or stolen phone needs the command line (LOW-MEDIUM)

Evidence: making a new pairing key (which unpairs every device) is `py -3 jarvis_token_store.py forget` in the backend folder, after clearing any typed token and any `HUD_TOKEN` first (`INSTALL.md:646-665`). Settings has only "Clear token" for the desktop's own copy (`settings.html:80,128`).

Fix: fold it into the already-decided "more devices" work (per-device keys, QR pairing): a "Remove this device" per phone in the desktop's Settings. Until then, **S, docs:** a phone-FAQ and desktop-FAQ answer "I lost my phone" with the one line. (M-L if built before "more devices"; owner's call on order.)

---

## Earlier audits: what is still open on this lens

| Audit item | Status | Evidence |
|---|---|---|
| Professionalism #2: no desktop download, updater key empty | **Still open** | `tauri.conf.json:118` `"pubkey": ""` |
| Professionalism #13: patch script keeps no log, default path is the owner's own | **Still open** | no `Start-Transcript` in `apply-patches.ps1`; default at `:72` |
| Professionalism #22: no single "what to send" page | **Still open** | `INSTALL.md:735-770` |
| Professionalism 2.3: struck-through "fixed" items in "Known rough edges" | **Still open** | `INSTALL.md:780,784` |
| Professionalism #3: no shared version number | Fixed | `VERSION` = 0.2.0; `tauri.conf.json:4`; phone `buildVersionName()` (`build.gradle.kts:85`); preflight prints it |
| Continuity #2: no "Stop everything" on the PC | Fixed | `tray.rs:236` |
| Continuity #3: "Update notice" row out of date | Fixed | the row is gone from `ARCHITECTURE.md` |

---

## Fit with the rules and guardrails

- No fix above adds a setting or an approval card. Items 3 and 5 each replace many scattered instructions with one place (guardrail 1, "one home per kind of thing").
- "Save a problem report" and "Back up now" write only to a file the owner picks, never send anything (rule 1), and reuse the existing scrubber.
- A preflight WARN for PC sleep follows guardrail 9 (a preflight line, not a switch).
- Nothing here loosens approvals, opens a tunnel or stores a key in plain text.

## Not checked

- How any of this looks on screen (no windows rendered for this lens).
- What the core backend (`jarvis_hud.py`, not in this repository) prints at start-up when Ollama is off, and whether it writes any log of its own when started by hand.
- Whether Ollama for Windows starts itself at login on the owner's PC.
- Whether the HUD window's "not connected" banner is still wrong now that the HUD goes through the desktop app.
- The exact counts of "apply-patches" messages are from a grep over string lines and are approximate (±5).
