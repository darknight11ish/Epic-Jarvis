# Newcomer walkthrough - ease-of-use audit, 2026-09-26

**Lens:** a smart person who is not a developer gets the repository link.
They follow only what the README and the apps tell them, in order. Then a
second, shorter walk: "a month later, I want to change how Jarvis talks, see
what it learned about me last week, and find a chat from Tuesday."

**How it was checked:** by reading the files on the current branch (HEAD
`ad44732`), and by rendering the desktop windows in a copy
(`/home/user/ease-copy-newcomer`, with the repository's own test harness
`tests/uikit.mjs` and its sample data). Rendered text and pictures are in
`newcomer-shots/` next to this file. Nothing in the repository was changed.
The phone app was read, not run (there is no Android build here). Anything
marked "not checked" was not checked.

---

## The short version

1. **A newcomer cannot install Jarvis at all.** INSTALL step 1.3 says the
   main backend files (`jarvis_hud.py` and others) have no download and exist
   only on the owner's PC (`docs/INSTALL.md:85-97`). The README never says
   this; it says "Follow docs/INSTALL.md, in order" (`README.md:73`). The
   newcomer finds out at step 4 of about 25, after installing three programs.
   For the owner, this is fine. For anyone else, the README should say it on
   line 1 of "Install it".
2. **Setup is long even for the owner:** 13 PowerShell commands in
   INSTALL.md, 7 more for voice (in a 10,434-line `backend/README.md`),
   6 programs installed with `winget` (three of them only to *build* the
   desktop app, because there is still no installer), a 5 GB model, 850 MB
   of voice files, hand-editing a 1,290-line settings file to turn on any
   tool, and an admin PowerShell firewall rule for the phone.
3. **Nothing in either app says what you can ask Jarvis.** The Jarvis bar's
   help lists 10 keyboard shortcuts and note prefixes, and no example
   questions. Jarvis understands about 39 kinds of plain commands (timers,
   lists, "tell me when", focus, briefing...), but the only place that shows
   example phrases is deep in the Brain's Work tab.
4. **The desktop Settings page is one scroll of 21 cards, about 14,500
   pixels tall, with no menu or search.** "How Jarvis talks" is about 9
   window-heights down; the FAQ about 17.
5. **The phone has no "Settings" screen.** Settings are split over Brain (one
   scroll of about 35 sections), Appearance, and "Platform checks" (which is
   where App lock, voice training and updates are, reached by tapping the
   status line at the top of Home).
6. **Finding an old chat is scroll-only:** no search, no weekday, titles are
   the first 80 characters of the first message, 30 per page.
7. **"Review past changes" has no home.** I found no screen in either app that
   lists past approval decisions, or settings you changed. The closest are
   the Undo shelf and the memory's own history.
8. **What works well:** the first-run walkthrough is short (3 screens) and
   honest; the memory screens are clear and each fact has a date; the
   Settings wording is plain and careful; "What did you know on..." is a
   genuinely good way to see the past.

---

## Walk 1: a newcomer, from the repository link

Numbered as they would live it. "Sees / thinks / stops or guesses."

1. **Opens the README.** Sees a clear one-paragraph description, the five
   rules, a feature list in plain words (`README.md:1-69`). Thinks: "Great,
   a private assistant on my PC." No picture of either app (`README.md` has
   0 images). *Works well.*
2. **"Install it" says follow INSTALL.md, three parts** (`README.md:71-87`).
   It says part 2 means building the desktop app yourself. Thinks: "Build?
   I'm not a developer." Carries on.
3. **Opens `docs/INSTALL.md` (810 lines).** Its intro is good: every command
   is one line, open PowerShell like this (`INSTALL.md:7-11`). *Works well.*
4. **Step 1.1:** one line installs Git, Python and Ollama; close and reopen
   PowerShell; check three version numbers (`INSTALL.md:52-60`). Clear.
5. **Step 1.2:** one line clones the repository (`INSTALL.md:75`). Clear.
6. **Step 1.3 - STOP.** "This is the one part no script can do for you,
   because there is no download link ... Those conversations are the only
   copy" (`INSTALL.md:85-97`). The newcomer has no backend folder. **This is
   where every newcomer's journey ends.** Nothing earlier warned them. They
   have now installed three programs for nothing.

   *From here the walk continues as the owner (who has the files) would
   experience it, still following only the written steps.*

7. **Step 1.4:** a check script, with the owner's own folder in the command
   (`C:\Users\pcadmin\...`, `INSTALL.md:109`). Thinks: "Is `pcadmin` me?"
   The text says "change it if yours is elsewhere" (`INSTALL.md:39-41`), once,
   40 lines earlier. The same path is also the script's built-in default
   (`scripts/apply-patches.ps1:73`, `scripts/check-backend.ps1:34`). The
   path appears 6 times in INSTALL.md.
8. **Step 1.5:** the one script. Well explained: it rehearses first, backs
   up, never overwrites your settings file (`INSTALL.md:125-151`). *Works
   well.* Then: "Update the desktop app at the same time (build and install
   it again, Part 2)" (`INSTALL.md:153-157`) - a forward reference to a part
   they have not done.
9. **Step 1.6: "Tools are off until you name them."** To let Jarvis read the
   calendar, email or notes, you add names to a `[tools]` list in
   `jarvis-framework.toml`, taking "the tools' names in
   `backend\jarvis_agent.py`" (`INSTALL.md:181-194`). Guesses: which names?
   The shipped settings file is 1,290 lines with 227 settings in 38 sections
   and no `[tools]` section (`backend/rebuilt/jarvis-framework.toml`). The
   desktop's "What Jarvis can reach" card shows which tools are on but
   cannot turn any on (`settings.html:964-980`, read-only).
10. **Step 1.7: the model.** One line, 5 GB, then quit Ollama from its tray
    and restart it (`INSTALL.md:206-209`). Clear. "Voice (optional)" points
    to `backend/README.md`, section "Voice that works" - which is at line
    4,754 of a 10,434-line file, opens with a history of what used to be
    broken, and is 7 more pasted commands (`backend/README.md:4754-4830`).
11. **Step 1.8: start it** in PowerShell, and read three banner lines. One of
    them "names the wrong file"; another failure "the banner does not say
    so" (`INSTALL.md:245-249`). Leave this window open. Thinks: "Every time
    I reboot, I open PowerShell and type this?" Yes, unless they later find
    "Starting Jarvis for you" in Settings (card 18 of 21, off by default,
    `settings.html:1179-1190`).
12. **Step 2.1: build the desktop app.** One line installs Visual Studio
    build tools, Rust and Node.js; then `npm install; npm run tauri build`
    (`INSTALL.md:270-276`). The reason: no installer is published because
    the updater's signing key is empty (`tauri.conf.json:118`,
    `"pubkey": ""`). This was the professionalism audit's #2; **still open.**
13. **Step 2.2: SmartScreen.** Five clicks, well described (`INSTALL.md:288-294`).
14. **First launch (step 2.3).** Three things appear at once: a 1280x900 HUD
    window (`windows.rs:521`), the widget pill, and a 480x560 **welcome
    walkthrough** (`windows.rs:554`, `lib.rs:1179-1185`). INSTALL.md does not
    mention the walkthrough at all (searched for "walkthrough", "welcome",
    "onboarding": 0 hits). The HUD shows words like `escalate`, `critic`,
    `bulk`, `CLOUD`, `FREE-TIER BUDGET`, `ROUTED` (rendered
    `newcomer-shots/hud.txt`). INSTALL says the HUD will say "demo · not
    connected" and to ignore it (`INSTALL.md:305-308`) - that sentence
    predates the HUD's requests moving into the app (`INSTALL.md:607-610`
    says that happened 2026-09-25), so it is probably out of date now. *Not
    checked on a real PC.*
15. **The walkthrough (3 screens).** Screen 1: "Look in the row of small icons
    at the bottom-right ... next to the clock" (`onboarding.html:132-137`).
    On Windows 11 the icon starts hidden in the `^` overflow
    (`INSTALL.md:302-303`) - the walkthrough does not say so, so the newcomer
    looks and does not find it. Screen 2: approvals, and "Alt+Space opens
    the Jarvis bar" (`onboarding.html:155`) - the key INSTALL calls "the most
    contested key on Windows 11" (`INSTALL.md:312-314`). Screen 3: memory.
    The colours are now correct (the UI audit's bug is fixed,
    `onboarding.html:85-88`). What it does **not** do: check that Jarvis is
    actually running, suggest a first thing to say, or mention the phone.
16. **Presses Alt+Space.** Sees "Ask Jarvis anything..." and a help list: 7
    keyboard shortcuts, 3 note prefixes, text size (`newcomer-shots/bar-idle.png`).
    Thinks: "OK, but what can I *ask*? Can it set a timer?" No example
    questions anywhere in the bar. Searched both apps for "try saying",
    "things to try", "what can you do", "you can ask": 0 hits. There is also
    no "help" or "what can you do" plain command among the ~39 in
    `backend/jarvis_quick.py`. (Whether the model answers "what can you do?"
    accurately: *not checked.*)
17. **If Jarvis is not running**, the bar says "Offline — Jarvis is not
    answering: could not reach the Jarvis server at http://127.0.0.1:4719
    ... Settings live in the tray menu" (`newcomer-shots/bar-offline.txt`).
    Clear enough, but calls it "the Jarvis server" while INSTALL calls it
    "the backend", and does not say "start it with ..." or offer a Start
    button.
18. **Step 2.5: Settings → Backend.** The card is actually called
    "Connection"; there is no "Backend" heading (`settings.html:51`). Minor,
    but a newcomer following words literally looks for "Backend".
19. **Part 3: the phone.** "Read this part before you start it"
    (`INSTALL.md:510`). It says Tailscale or NordVPN Meshnet is needed, but
    has **no step to install either** (searched for "install tailscale",
    "tailscale.com": 0 hits). The phone refuses a home Wi-Fi number
    (`network_security_config.xml`: only `ts.net`, `nord`, `localhost`,
    `127.0.0.1`), so a mesh is mandatory.
20. **The phone-reach setting only works in one mode.** Settings →
    Connection → "Let my phone reach this" (`settings.html:102-122`) is
    applied only when Jarvis Desktop starts the backend itself
    (`INSTALL.md:592-596`). With the default (you start it in PowerShell),
    the field silently does nothing. The Settings card does not say so
    (searched `settings.js` for a link between the bind field and
    supervision: none). The newcomer types their `100.x` address, saves, and
    the phone still cannot connect.
21. **Firewall:** a one-line rule, in PowerShell *opened as administrator*
    (`INSTALL.md:570-576`), plus a check for an old "Block" rule.
22. **Install the APK** (unknown-sources permission, `INSTALL.md:680-689`).
23. **Pair:** type the PC's name plus `:4719`, then the token. On the PC,
    Settings → "Show the token for my phone": there is no Copy button on
    purpose (`settings.html:94-101`), it hides after a minute, and the token
    is 43 random letters, digits, `-` and `_` (`secrets.token_urlsafe(32)`,
    `backend/jarvis_token_store.py:283`). Typed by hand on a phone keyboard.
    The QR-code pairing the owner decided on is not built yet
    (`PairingScreen.kt`: no QR or scan code).
24. **If it fails**, the phone's message "is usually wrong" (`INSTALL.md:703-707`).

**Count for walk 1 (owner path):** about 24 steps; 13 PowerShell commands in
INSTALL.md + 7 for voice + 1 admin; 6 `winget` programs; 2 app installs past
a security warning; 1 hand-edited settings file (1,290 lines) for any tool;
1 hand-typed 43-character token. **For a true newcomer: stops at step 6.**

---

## Walk 2: a month later

### A. "I want to change how Jarvis talks"

- **Desktop:** find the tray icon → Settings… → scroll to card 8 of 21,
  "How Jarvis talks", about 6,600 pixels down (9 window-heights in the
  760-pixel Settings window, measured in the harness,
  `settings.html:591-605`). **Two choices:** "Warm and brief (default)" or
  "Plain" (`manner.js:23-30`). That is 3 clicks plus a long scroll.
- Nothing else about *style* can be changed: not length, not how it
  addresses you, not humour. Voice (which voice speaks) is a separate card,
  "Jarvis's voice", 1 card above. The FAQ has no question about this.
- **Saying it** ("talk more plainly") is not a plain command (no manner
  intent in `jarvis_quick.py`); what the model does with it: *not checked.*
- **Phone:** Home → Brain → scroll to the 13th section, "How Jarvis talks"
  (`BrainScreen.kt:458`). Same two choices.
- **Verdict:** easy once found; hard to find; very little to customise.

### B. "Show me what it learned about me last week"

- **Desktop:** tray → Open the Brain → the Memory tab opens first. "Saved
  automatically" lists facts newest first, each with when it was saved and
  from which device, 30 at a time with "Load older" (`auto-learn.js:19-20`,
  `:323-326`). **This works well: 2 clicks.**
- Rough edges:
  - Facts that waited for your yes and were approved are in a different
    list, "What Jarvis knows about you", further down (`brain.html:349`).
    Whether that list shows dates: *not checked.*
  - There is no "this week" filter. "What did you know on…" shows memory *as
    of* a date (`brain.js:1756`), which answers "what did it know then", not
    "what changed since".
  - The Learning card has **two learning controls with overlapping names**:
    a "Stop learning" button (background learning, `brain.js:1709`) and a
    "Learn automatically" tick box (`newcomer-shots/brain.png`). A newcomer
    cannot tell which to use.
  - Forget shows two dialogs in a row: "are you sure?" (the owner's choice)
    and then a second box, "When did this actually stop being true?"
    (`brain.js:2120-2129`). The second one is extra.
  - The Memory tab can show "A rush latch is active" (`brain.js:723`) -
    jargon on the first screen of the Brain.
- **Phone:** Home → Brain → scroll to "Saved automatically" (about the 22nd
  section, `BrainScreen.kt:561`).

### C. "Find the chat I had on Tuesday"

- **Desktop:** tray → Open the Brain → History (2nd tab). The list is
  newest first, 30 at a time (`history-view.js:48`). Each row: a title, when,
  and turns. The title is the first line of your first message, cut at 80
  characters (`backend/jarvis_chat_log.py:122,682`). Anything older than a
  day shows as a date like "22 Sept 2026" - **no weekday**
  (`history-view.js:216-227`), so "Tuesday" means working out the date first.
- **No search, no date filter** in either app (searched `history-view.js`
  and `HistoryScreen.kt`: none).
- Opening a chat is read-only; there is no "carry on this conversation"
  (none found in either file).
- **Phone:** Home → Brain → scroll to about the 25th section, "Chat
  history" (`BrainScreen.kt:584-593`) → its own screen.
- **Verdict:** fine with 10 chats; painful with 200.

### D. (Asked by the owner too) "How do I review past changes?"

- **Approvals I made:** no list anywhere. The PC sends a `history` list with
  the pending cards (`docs/JARVIS-API.md:208`), but the phone deliberately
  skips it (`JarvisApi.kt:121`) and no desktop window draws it.
- **Settings I changed:** no log.
- **What Jarvis did:** the Undo shelf (Brain → Work, `brain.html:497`) lists
  actions with an undo; the Ledger shows only "chain status"
  (`brain.html:523-530`, behind Advanced).
- **What changed in Jarvis itself:** `CHANGELOG.md` now exists (fixed since
  the professionalism audit), but neither app shows "what's new" (searched
  both apps for "what's new" / "changelog": no screen).

---

## What works (keep it)

- The README is short, plain and honest (`README.md:1-69`).
- INSTALL.md's style: one line per command, "open a NEW window", and it
  admits what does not work (`INSTALL.md:7-11`, `:775-810`).
- The patch script rehearses first and never overwrites your settings
  (`INSTALL.md:131-145`).
- The walkthrough is only 3 screens, in plain words, and now uses the right
  colours (`onboarding.html:128-181`).
- The Brain's everyday rail is just 4 tabs; 4 more hide behind "Advanced"
  (`brain.html:82-120`).
- Memory is transparent: every fact listed with a date, Forget, Erase,
  Reword, Export, and "What did you know on…".
- The Work tab teaches by example: "Or say 'focus for 30 minutes'", "tell me
  when an email from Alex arrives", "add milk to the shopping list"
  (`brain.html:441,454,463`). This is the right idea - it is just in the
  wrong place.
- The Settings text is careful and plain (for example the token note,
  `settings.html:94-101`).

---

## What is hard, ranked by how much it hurts a newcomer

| # | Problem | Evidence | Hurts |
|---|---|---|---|
| 1 | The backend files cannot be downloaded; the README does not warn | `INSTALL.md:85-97`, `README.md:71-87` | Blocks everyone but the owner |
| 2 | No desktop installer: 3 developer tools + a build | `tauri.conf.json:118`, `INSTALL.md:265-279` | Hours, and the scariest part |
| 3 | No "what can I say?" anywhere you type | bar help `newcomer-shots/bar-idle.txt`; 0 hits for example phrases | Features exist but stay invisible |
| 4 | Phone needs Tailscale (no install step), the reach field that only works in one mode, an admin firewall rule, and a 43-character token typed by hand | `INSTALL.md:514-518,570-576,592-596`; `settings.html:102-122`; `jarvis_token_store.py:283` | Most likely place to give up |
| 5 | Turning on any tool (calendar, email, notes, web) means editing a 1,290-line file by hand; web search's default (SearXNG) needs Docker and INSTALL.md never mentions it | `INSTALL.md:181-194`; `jarvis_search.py:121-122`; 0 hits for "SearXNG"/"Docker" in INSTALL.md | After install, Jarvis can do little |
| 6 | Desktop Settings: 21 cards, ~14,500 px, no menu or search; FAQ near the bottom | measured in harness; `settings.html` | Every later change starts with a hunt |
| 7 | Phone settings in 3 places, one called "Platform checks" | `ReadinessScreen.kt:197,205-245`; `BrainScreen.kt` ~35 sections | Security and voice are hard to find |
| 8 | Backend must be started by hand in PowerShell after each reboot unless "Starting Jarvis for you" is found (card 18) | `INSTALL.md:231,331-342`; `settings.html:1179` | Daily friction |
| 9 | Chat history: no search, no weekday, no resume | `history-view.js:216-227`; `jarvis_chat_log.py:682` | Grows worse every week |
| 10 | No list of past approvals or setting changes | `JarvisApi.kt:121`; no desktop view | Cannot answer "what did I say yes to?" |
| 11 | Jargon on first screens: HUD (`escalate`, `critic`, `bulk`, `FREE-TIER BUDGET`), Brain ("rush latch", "Long Fuse jobs", "capability set", "before-images") | `newcomer-shots/hud.txt`; `brain.js:723`; `brain.html:488-503` | Makes a newcomer feel it is not for them |
| 12 | Walkthrough says the tray icon is "next to the clock" (it starts hidden in `^`) and teaches Alt+Space, the key most likely to be taken | `onboarding.html:132-137,155`; `INSTALL.md:302-303,312-314` | First two things tried may fail |
| 13 | Calendar setup says "quit Jarvis from the tray and start it again" - but with the default setup the backend runs in its own PowerShell window and will not see the new setting until that window is restarted; it also names a different default settings-file place than INSTALL | `backend/README.md:8746-8751` vs `INSTALL.md:176-179,251` | A setup that looks done but does not work |
| 14 | Two learning controls with overlapping names; Forget asks twice | `brain.js:1709`, `:2120-2129` | Confusion, small |

---

## Concrete fixes

Size: S = under an hour, M = an afternoon, L = a day or more.

| # | Fix | App | Size | Owner's call? |
|---|---|---|---|---|
| 1 | README, top of "Install it": one plain sentence - "Jarvis needs backend files that are not public; this repository can only be installed on a PC that already has them." | Docs | S | Yes (how public to be) |
| 2 | Make the updater signing key once, so CI publishes a ready `-setup.exe` (professionalism #2, still open). INSTALL Part 2 becomes "download, then SmartScreen". | Desktop | S (owner's 10 min) | Yes |
| 3 | **"Things to try"** in the Jarvis bar's help and on the phone's empty Home: 6-8 real phrases taken from what `jarvis_quick.py` already understands ("set a timer for 10 minutes", "remind me at 5 to call Mum", "what did I miss?", "tell me when an email from Alex arrives", "focus for 30 minutes", "brief me"). Plus a plain "what can you do?" answer from the same list, made without the model. Also add to the walkthrough's last screen. | Both | S-M | No |
| 4 | Walkthrough: say the icon may be under `^` and how to drag it out; check the link to Jarvis and show "Jarvis is running" or "Start Jarvis first: ..." on the last screen; name the key Windows actually gave the bar. (Budget: stays 3 screens, per UI audit.) | Desktop | S | No |
| 5 | Settings: a short contents list at the top (21 links), or group the cards under 5 headings (Connection, Talking & voice, Memory & privacy, Hardware, Help). FAQ near the top. | Desktop | M | No |
| 6 | "Let my phone reach this": say under the field "Only used when Jarvis Desktop starts Jarvis for you (Starting Jarvis for you, below)", and show it in red when supervision is off. | Desktop | S | No |
| 7 | INSTALL Part 3: add "3.0 Install Tailscale on both devices" (one `winget` line on the PC, Play Store on the phone). | Docs | S | No |
| 8 | Build the decided QR pairing (already decided 2026-09-24, waits on "more devices"). Until then, show the token in groups of 4 characters so it can be typed. | Both | S (grouping) / L (QR) | No (already decided) |
| 9 | A "Turn on a tool" helper on the PC: the "What Jarvis can reach" list gets an On button per tool that edits `[tools].enabled` through one approval card - within the rule that loosening happens on the PC with a card. Until then, INSTALL 1.6 lists the tool names inline. | Desktop + backend | M-L / S (docs) | Yes (loosening from an app) |
| 10 | Web search: if SearXNG is not running at first use, the "down" message names the one-line alternative (DuckDuckGo) - it already offers to switch; INSTALL gets one line on SearXNG/Docker. | Docs, backend | S | No |
| 11 | Chat history: search box (titles and words, on the PC - the words are decrypted there anyway), weekday in dates ("Tue 22 Sept"), and "Continue this chat". | Both | M | Search of past words: yes - it touches ARCHITECTURE §5's rule that the owner said waits (2026-09-26). Weekday: no. |
| 12 | A "Decisions" list: the last 50 approval cards with Approved/Denied/Ran out and when - read-only, from the `history` the PC already sends. | Both | M | No |
| 13 | Phone: one "Settings" entry on Home gathering Appearance, How Jarvis talks, Voice, Security, Updates (professionalism #15, still open); rename "Platform checks" to "Phone checks and security" or move security out. | Phone | M | Yes (layout) |
| 14 | Plain words on the first screens: hide the HUD's lane names or label them ("Answered on this PC"), and replace "rush latch" with "Someone's text tried to rush an approval - approvals are paused briefly". | Desktop | S | No |
| 15 | Merge the two learning controls into one clear pair of switches ("Learn in the background" / "Save without asking"); make Forget's date question an optional link inside the confirm. | Desktop (phone to match) | S | No |
| 16 | Fix the calendar step: "restart the PowerShell window running Jarvis (or Quit and restart if Jarvis Desktop starts it for you)", and the settings-file location to match INSTALL. | Docs | S | No |
| 17 | Mention the welcome walkthrough in INSTALL 2.3, and re-check the "demo · not connected" sentence on the real PC. | Docs | S | No |

---

## Earlier audits: still unfixed (re-checked today)

- Professionalism #2, no desktop installer: **open** (`tauri.conf.json:118`).
- Professionalism #13, the owner's own folder built into both scripts:
  **open** (`apply-patches.ps1:73`, `check-backend.ps1:34`).
- Professionalism #15, no phone "Settings" screen: **open** (the rename to
  "Brain" is done, `BrainScreen.kt:246`, `HomeScreen.kt:1269`).
- Professionalism #21, no `jarvis-client/README.md`: **open** (`ls
  jarvis-client` shows none).
- Professionalism #4, README with no picture: feature list **fixed**,
  picture **open** (0 images in README.md).
- UI audit #16, pairing becomes a small welcome: **open**
  (`PairingScreen.kt:124-138` still starts with the form).
- UI audit, phone Brain is one long scroll: **open** (~35 `item(key=...)`
  in `BrainScreen.kt:278-729`).
- Fixed since: changelog (`CHANGELOG.md`), maker's name (`README.md:7`),
  onboarding colours (`onboarding.html:85-88`), docs index
  (`docs/README.md`), "Stop everything" now also in the tray menu
  (`tray.rs:233-239`).

## Numbers at a glance

- Install steps to a working PC + phone: ~24; newcomer blocked at step 6.
- PowerShell commands: 13 (INSTALL) + 7 (voice) = 20, 1 needs admin.
- Programs via winget: 6 (3 only to build the desktop app).
- Downloads: ~5 GB model + ~850 MB voice + build tools (size not measured).
- Settings file: 1,290 lines, 227 settings, 38 sections; 0 tools on by default.
- Desktop Settings: 21 cards, 66 buttons, 19 tick boxes, 4 choice buttons,
  10 text boxes, ~14,500 px tall, 0 menus/search (harness sample data).
- Desktop FAQ: 11 questions; phone FAQ: 16; neither has "what can I ask?",
  "where are my old chats?" is only on the phone ("Are my chats kept
  anywhere?", `FaqScreen.kt:158`).
- Walkthrough: 3 screens, 83-107 words each.
- Example phrases shown where you type: 0 (desktop bar), 0 (phone Home).
- Pairing token typed by hand: 43 characters.
- Clicks, month-later tasks (desktop): change manner 3 + ~9 screens of
  scroll; see recent facts 2; find Tuesday's chat 2 + scrolling and date
  arithmetic.

## Not checked

- Anything on a real Windows PC or phone (no Windows host, no Android build
  here). The walk's times are not measured.
- Whether the model answers "what can you do?" or "talk more plainly"
  usefully.
- Whether "What Jarvis knows about you" shows dates.
- Real sizes of Settings cards with a real backend (the harness sample data
  decides which parts are open).
