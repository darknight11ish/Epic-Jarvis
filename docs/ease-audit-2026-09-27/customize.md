# Ease-of-use audit: customizing Jarvis

Lens: every setting in both apps and in the PC's settings file. How many
there are, where they live, which can only be changed by editing a file,
which differ between the apps, which need an approval card or a restart, and
whether someone new can find them. Read-only audit, 2026-09-26. Every claim
below was checked in the file named; "not checked" is said where I did not.

## The short answer

There is a lot you can change, and almost every setting has a plain sentence
under it saying what it does. That part is good. The problem is **finding**
things. Settings are spread over **about 11 places** across the two apps,
plus a settings file and about 20 Windows "environment variables" (settings
Windows keeps for your user account) that only a PowerShell line can set.
The desktop Settings window is one page about **15 screens tall** with no
table of contents and no search. The phone has **no screen called Settings
at all**: its voice settings sit on a screen called "Platform checks", and
most of the rest are mixed into the Brain's 38-section scroll. Some things a
newcomer will want early - Jarvis's built-in voice, how fast it talks,
letting the AI use tools like web search, connecting email or the calendar -
can **only** be done by editing a file or pasting a command, then restarting.
And there is **no list of past changes or past approvals** anywhere: you can
read old chats, but not "what did I approve last week?".

## Numbers

| What | Count | Where I got it |
|---|---|---|
| Sections in the desktop Settings window | 21 cards (2 of them folded under "More options") | `jarvis-desktop/src/settings.html`, 21 × `<section class="card"`; fold at `:1173` |
| Height of desktop Settings | 13,392 px at the design size of 680×900 ≈ **15 screens** | Rendered in a throw-away copy with the test kit's sample data |
| Words on desktop Settings | about 4,400 (3,670 before the live parts load) | Same render; static count from the HTML |
| Visible controls on desktop Settings | 62 (13 switches, 35 choice buttons, 9 text boxes, 4 radio buttons, 1 text area) | Same render |
| Settings cards you can change nothing in | 5 of 21 (What Jarvis can reach, Sending email, FAQ, About, What this backend supports) | `settings.html:964-995`, `:997-1167`, `:1269-1344` |
| "Reset to default" buttons | 1 on the desktop (Shortcuts) | `settings.html:310`, `settings.js:1014`; phone has Reset + Undo only for the face and colours (`AppearanceScreen.kt:516-518`) |
| Search boxes for settings | 0 in either app | grep of `settings.html`, `settings.js`, `BrainScreen.kt`, `ReadinessScreen.kt` |
| Sections in the phone's Brain screen | 38 list items (status, tools, settings and memory mixed) | `BrainScreen.kt`, 38 × `item(key` |
| Rows on "What asks first" | 63, in 10 groups: 7 with an "Ask me first" switch (the PC may loosen them), 1 lights setting, 2 fixed "no card" rows, 26 "always asks", 27 "only your settings file changes this one" | `backend/jarvis_asks_first.py:208-235`, `:320-345`; counted by importing the module |
| Lines in the PC settings file | 1,290 lines, 39 sections, 227 settings | `backend/rebuilt/jarvis-framework.toml` |
| Settings in that file marked "not read" (do nothing) | 6 | `jarvis-framework.toml:671-676`, `:916-917` |
| Windows environment variables Jarvis reads for accounts | 23 names (email, sending, calendar, Home Assistant, notes, GitHub) | `backend/jarvis_*.py`, every `*_ENV = "JARVIS_..."` |
| Places a desktop setting can live | 4: Settings window, Brain window, Faces window, tray menu (power mode) | `tray.rs:302-333` |
| Places a phone setting can live | 7: Platform checks, Security, Voice check, Jarvis's voice, Appearance, Brain, History | `ui/Nav.kt:72` |

## Where every setting lives today

### Desktop (reached from the tray icon only)

The Jarvis bar has no Settings button. The only way in is right-click the
tray icon → "Settings…" (`tray.rs:292`; it is the 16th of 18 rows in the menu,
`tray.rs:302-335`). The bar says so only when Jarvis is offline: "Settings live in
the tray menu" (`index.html:378`). An error's "fix" button can also open it
(`plain_errors.rs:206-211`).

**Settings window, top to bottom** (`settings.html`):

| # | Card | What you can change | Needs a card? |
|---|---|---|---|
| 1 | Connection `:50` | address, token, "let my phone reach this" address | no |
| 2 | Appearance `:148` | match Windows light/dark, theme (3), text size, face quality / frame rate / speed / auto; "Open Faces" for face and state colours | no |
| 3 | Updates `:244` | look for updates at start | no |
| 4 | Shortcuts `:291` | 6 shortcuts (`hotkeys.rs:55`), Reset to defaults | no |
| 5 | Security `:321` | App lock, lock again after, Windows Hello for approvals, Windows Hello for memory lists and chat history | loosening asks Windows Hello |
| 6 | Voice `:370` | train voice, how strict, private answers by voice, memory answers by voice, sensitive answers by voice, hands-free trust, "Hey Jarvis" on/off, interrupt while talking, "One moment", "I heard you" sound | loosening = card |
| 7 | Jarvis's voice `:499` | add / pick / delete a recorded voice, "better voice" on second card | adding, switching, better voice = card |
| 8 | How Jarvis talks `:591` | Warm and brief / Plain | no |
| 9 | Morning briefing `:615` | time and days, show senders | set-up and senders on = card |
| 10 | Hardware and models `:655` | three setups; PowerShell lines to copy | each step = card |
| 11 | Second graphics card `:756` | 5 feature switches (`jarvis_second_card.py:216-240`) | on = card |
| 12 | Big model (slow) `:819` | master + wiki + deep questions (`jarvis_big_model.py:167-168`) | on = card |
| 13 | Web search `:884` | provider (5), ask before every search, SearXNG address, 3 keys | "ask" off = card |
| 14 | What asks first `:946` | 63 rows to read; 7 "Ask me first" switches (loosening them is PC only) and the lights setting | loosen = card + Windows Hello |
| 15 | What Jarvis can reach `:964` | nothing (read only) | - |
| 16 | Sending email `:990` | nothing (read only) | - |
| 17 | FAQ `:997` | nothing | - |
| 18 | Starting Jarvis for you `:1179` (folded) | let the app start Jarvis, program, arguments, folder | no |
| 19 | Startup and logs `:1234` (folded) | start with Windows; open logs | no |
| 20 | About `:1269` | nothing | - |
| 21 | What this backend supports `:1317` | nothing | - |

**Brain window** also holds settings, not only information
(`brain.html`): automatic learning and "also remember sensitive topics"
(Memory tab, `:305-318`), "Always keep in mind" (`:332`), chat history on/off
and how long to keep it (History tab, `:409-410`), the standby schedule and
focus sessions (Work tab, `:464-475`, `:430-441`), **switching and installing
the AI model** (the "Faculties" tab, `:277`; `brain.js:852`, `:943-969`), a
second theme picker (`:129-133`), and the GitHub watchlist (hidden under
"Advanced", `:82-85`, `:539`).

### Phone

There is no Settings screen (`ui/Nav.kt:72` lists every screen; none is
Settings). The row with Brain, Inbox, Appearance and Help is **hidden by
default** (`HomeScreen.kt:598-600`; `navAlwaysShown = false` at
`AppearanceStore.kt:644`); you swipe the status line or tap a small chevron
to see it. Tapping the status line itself opens "Platform checks"
(`HomeScreen.kt:1161`).

| Screen | Settings in it |
|---|---|
| Platform checks (`ReadinessScreen.kt:197`, subtitle "What this phone will and will not allow") | "Hey Jarvis" on/off, listen on this phone, interrupt while talking, "One moment", "I heard you" sound (`:218-236`); buttons to Voice check, Jarvis's voice (`:466-480`) and Security (`:906`); update checks |
| Security | App lock, fingerprint for approvals, "Hide memory lists and chat history", what counts as you (`SecurityScreen.kt:99-173`) |
| Voice check | how strict, private answers, hands-free |
| Jarvis's voice | recorded voices |
| Appearance | theme, follow system, 13 layout and look settings (`AppearanceStore.kt:640`), face, state colours |
| Brain (38 items) | briefing, web search, what asks first, how Jarvis talks, model, hardware, second card, big model, learning, always keep in mind, entry to History (`BrainScreen.kt:383-729`) |
| History | chat history on/off, keep for |

### Only in a file, a command, or nowhere

These are things a newcomer is likely to want, that **no app can change**:

| What you want | How it is done today | Restart? |
|---|---|---|
| Let the AI use a tool (web search, calendar, email check, calculator…) | add `[tools] enabled = [...]` to `jarvis-framework.toml`; the shipped file has no `[tools]`, so **every tool starts off** (`docs/INSTALL.md:170-197`) | backend |
| Pick one of the built-in voices (e.g. British male) | add `tts_speaker_id = 9` under `[voice]` (`backend/README.md:4840-4843`) | backend |
| How fast Jarvis talks | `tts_speed` in the file (`backend/jarvis_voices.py:252`); no app shows it (feasibility audit I28, `FEASIBILITY-AUDIT-2026-09-26.md:149`, marked "Now", not built) | not checked |
| Connect email, sending, calendar, Home Assistant, Joplin/Obsidian, GitHub | Windows environment variables set by pasting a PowerShell line, e.g. `backend/README.md:8871` (email address **and password**) | "Quit Jarvis … and start it again" |
| Obsidian vault folder | `[notes.obsidian] vault_directory` (`docs/INSTALL.md:407-412`) | backend |
| How often Jarvis may speak up unasked (3 a day) and when the digest comes (6 pm) | `[arbiter] spoken_per_day`, `digest_hour` (`jarvis-framework.toml:1187`, `:1192`); the Brain shows the count but cannot change it (`brain.js:4520-4523`) | backend |
| Quiet hours and idle standby | `[power] schedule_enabled`, `quiet_start`, `idle_enabled` (`jarvis-framework.toml:920-927`) - a **second** schedule, next to the app's standby schedule (`brain.html:464-475`) | backend |
| Personality modes (work, tutor, night…) | `[persona] default_mode` (`jarvis-framework.toml:953-965`); no app shows them; separate from "How Jarvis talks" | backend |
| Turn-taking, and "One moment"/interrupt for every app | `[voice] turn_enabled`, `barge_in_enabled`, `one_moment_enabled`; "The apps cannot change them" (`backend/README.md:6994-6998`) | backend |
| 27 of the 63 "What asks first" rows (26 more are fixed at "always asks" on purpose) | the file only: "Only your settings file (jarvis-framework.toml) changes this one." (`jarvis_asks_first.py:145`) - on purpose for the risky ones | reloads by itself when the app writes it (`jarvis_asks_first.py:_reload`); a hand edit: not checked |
| Ollama settings (which card, memory format) | copy a PowerShell line from Hardware (`settings.html:691-719`) | quit and restart Ollama |

## Can a newcomer find it?

Clicks counted from "Jarvis is running", desktop from the tray icon, phone
from Home.

| Task | Desktop | Phone | Verdict |
|---|---|---|---|
| Change the theme | tray → Settings… → Appearance (2nd card): 3 clicks. Also Brain's corner menu | reveal the nav row → Appearance: 2 taps | Easy on both |
| Change Jarvis's voice | Settings → 7th card: only **recorded** voices. The 50-odd built-in voices: file only | Platform checks → Your voice → "Jarvis's voice": 3 taps, same limit | **Hard**: the obvious choice is missing |
| Turn on "Hey Jarvis" | Settings → Voice (6th card) → button → approve the card → then switch listening on in the bar (`settings.html:445-449`) | tap status line → Platform checks → Wake word | Findable on desktop; on phone it is under a name nobody would guess |
| Change the wake word itself | not possible (`wake_phrase = "hey_jarvis"`, file only, `jarvis-framework.toml:824`) | same | Not offered; not said anywhere in the apps |
| Change the manner | Settings → 8th card | Brain → about the 13th item | OK on desktop, buried on phone |
| See or change what asks first | Settings → 14th of 21 cards, 63 rows | Brain → about the 10th item | Findable if you scroll; long |
| Change the AI model | Brain → "Faculties" tab → Models → Use. Settings → Hardware and models is a different thing (setups) | Brain → "Model" | Two homes on desktop; "Faculties" is jargon |
| Set a schedule | standby: Brain → Work; briefing time: **Settings** → Morning briefing (Brain's Work tab says so, `brain.html:485`); quiet hours: file | Brain (both) | Split three ways |
| Let Jarvis search the web | Settings → Web search lets you pick a provider, but the AI can use it only after a file edit; "What Jarvis can reach" then says `Off: "web_search" is not in [tools].enabled in jarvis-framework.toml.` (`backend/jarvis_reach.py:345-349`) | same, and nothing to type on the phone | **Hardest**: looks set up, is not |
| Review past chats | Brain → History (2nd tab) | Brain → scroll to "Chat history" → History | OK, but no search |
| Review past approvals or setting changes | nowhere | nowhere | **Missing** |

## What works

1. **Every setting explains itself.** Almost every switch has a sentence
   under it in plain words, including what it costs ("Turning it on shows
   you an approval card first; turning it off happens at once",
   `settings.html:564`).
2. **One rule for safety, used everywhere.** Making Jarvis stricter is
   instant; making it looser raises one approval card (and sometimes Windows
   Hello). It is the same in Voice, Security, History, Learning, Web search,
   Second card and Big model. Once learned, it predicts every switch.
3. **The same words in both apps.** Titles and sentences are shared and
   tested (for example `history-view.js:29-37`, `reach.js`,
   `security-settings.js:147-154`, which fixed the continuity audit's #1).
4. **"What asks first" and "What Jarvis can reach"** are written by the PC
   from its real settings, not by the AI, and grouped in plain words
   (`jarvis_asks_first.py:208-235`). Few assistants show this at all.
5. **Chat history is easy to reach on both apps**, says where each message
   came from (typed, pasted, shared…) and marks chats that read outside
   text (`history-view.js:52-84`).
6. **The phone's Appearance screen has Reset and Undo**, and the desktop's
   Shortcuts has "Reset to defaults".
7. **Some settings can be said out loud**: "use DuckDuckGo for web search",
   "brief me every weekday at 7", "focus for 30 minutes"
   (`backend/jarvis_quick.py:25-30`).

## What is hard, worst first

1. **Tools are off, and only a file turns them on.** The apps let you pick a
   search provider, test it, and save keys - and then the AI still cannot
   search, because `[tools] enabled` is missing from the shipped file
   (`docs/INSTALL.md:184-197`). The only hint is a sentence with file jargon
   on the Reach card (`jarvis_reach.py:349`). A newcomer will think search
   is broken.
2. **Accounts are connected by pasting PowerShell, with passwords kept as
   Windows environment variables.** Email, sending, calendar and Home
   Assistant each need several variables and a restart
   (`backend/README.md:8871`). Web search keys, by contrast, go into
   Credential Manager from a box in Settings (`settings.html:926-928`). Two
   different ways to store a secret. Rule 3 says a key must be kept "out of
   anything the app writes to disk in plain text"; here the app does not
   write it (the owner's PowerShell does), but Windows keeps user
   environment variables unscrambled in the registry. I have not checked
   whether that has been discussed before; it is worth the owner knowing.
3. **The phone has no Settings, and its voice settings are under "Platform
   checks".** A name for diagnostics holds the wake word, interrupting,
   "One moment", the "I heard you" sound, and the doors to voice strictness,
   Jarvis's voice and Security (`ReadinessScreen.kt:197-236`, `:466-480`,
   `:906`). The nav row that leads anywhere else is hidden by default
   (`HomeScreen.kt:598-600`). Already found by the UI audit (#14) and the
   professionalism audit (#15); **still not fixed**.
4. **Desktop Settings is one 15-screen page with no map and no search.**
   21 cards in an order that mixes daily things (theme, voice) with rare
   ones (big model, second card) and read-only pages (FAQ, About, backend
   parts) - "What asks first" is 14th. UI audit #13 asked for a jump list;
   **still not done** (no navigation code in `settings.js` or
   `settings.html`). Settings also only opens from the tray menu.
5. **Everyday wishes are file-only.** Built-in voice, speaking speed, how
   often Jarvis speaks up, when the digest comes, quiet hours, the wake
   word, personality modes. None is said anywhere in the apps as "change
   this in the file".
6. **One kind of thing, several homes.** Theme: two pickers on the desktop.
   Model: Brain "Faculties" and Settings "Hardware and models". Schedules:
   standby in Brain, briefing time in Settings, quiet hours in the file.
   This breaks the feasibility audit's own guardrail "One home per kind of
   thing" (`FEASIBILITY-AUDIT-2026-09-26.md:363`).
7. **No record of past changes or approvals.** Chats can be reviewed; facts
   can be reviewed; but there is no list of cards you approved or denied,
   or of settings that changed and when. The Ledger shows "Chain status
   only … Never the payloads" and is hidden under Advanced
   (`brain.html:523-528`). The Undo shelf covers 24 hours
   (`jarvis-framework.toml:1058`). The PC does write an audit trail
   (`jarvis_asks_first.py:_audit`, `jarvis_second_card.py:1778`), but only
   the log folder shows it, as raw text.
8. **Chat history has no search, filter or export.** 30 at a time,
   "Load older", delete one at a time (`history-view.js:47-48`,
   `brain.html:414-418`). Finding "that chat about the boiler last month"
   means scrolling. (Note: the owner decided that *Jarvis* searching past
   chat words waits, CLAUDE.md 2026-09-26. A find box for the owner's own
   eyes is a different thing, but it is the owner's call whether that
   decision covers it.)
9. **"What asks first" says something untrue about web search.** Its "Search
   the web" row says "Asks you first, every time" and "Always asks. This
   cannot be changed from an app." (`jarvis_asks_first.py:135`, `:144`,
   `:196-200`). But a search that comes straight from your own question runs
   with **no** card (`jarvis-framework.toml:185-193`). It also lists "Read
   your calendar" **twice** (`calendar_read` and `read_calendar`, both titled
   the same, `jarvis_card_words.py:57-58`, both in one group at
   `jarvis_asks_first.py:209-211`).
10. **Some help words are out of date.** About: "every action Jarvis wants
    to take stops and asks first, one action at a time"
    (`settings.html:1277-1278`) - timers, repeating reminders, automatic
    learning, plain web searches and (if switched on) lights no longer ask.
    FAQ: Jarvis reaches the internet "only after it explains what it needs
    and you say yes" (`settings.html:1011-1013`) - not true for a plain web
    search. A stale code comment says there is no "More options" section
    (`settings.html:36-38`) above the one at `:1173`.
11. **No reset to default** except shortcuts and the phone's face/colours.
    If you change ten voice and security settings and it goes wrong, you
    undo them one by one.
12. **Six settings in the file do nothing** ("not read",
    `jarvis-framework.toml:671-676`, `:916-917`). Anyone reading the file to
    customize will try them.
13. **Jargon in section names**: "Faculties", "Galaxy", "Long Fuse jobs",
    "Ledger", "Content risk", "colibri", "What this backend supports". In
    Settings' static text: "token" 17 times, "Ollama" 7, "colibri" 6,
    "Meshnet" 6.

## Concrete fixes

No new switches in any of these (the UI audit's "Settings get 0 new
switches" budget, `UI-AUDIT-2026-09-26.md:62`); they move, group, name and
explain what exists.

| # | Fix | App | Size |
|---|---|---|---|
| 1 | **"Let the AI use tools" in the apps.** A row per tool on "What Jarvis can reach" with the same pattern as everything else: turning a tool on raises one approval card and writes `[tools] enabled` for you, like "What asks first" already writes its own tier lines (`jarvis_asks_first.py`, "Writing one tier line"); turning off is instant. Until then, change the Reach line to plain words: "Off. To let the AI use this, see Settings → Help → Turning on tools." | Both (backend + desktop + phone) | M |
| 2 | **A Settings screen on the phone**, entered from a gear on Home that is always visible. Move there: voice things out of "Platform checks", Security, Appearance, and the settings parts of Brain. Brain keeps status, memory, history and work. (UI audit #14.) Ship it alone - it is the biggest CI risk. | Phone | L |
| 3 | **A jump list and a search box at the top of desktop Settings**, plus a gear button in the Jarvis bar. The search only filters the cards by the words already on them. Put daily cards first (Appearance, Voice, How Jarvis talks, What asks first), rare ones after, read-only ones last. | Desktop | M |
| 4 | **Say where file-only settings are.** Under Jarvis's voice: "Built-in voices and speaking speed are in the settings file for now - here is the line." The same for wake word, quiet hours, speaking-up budget. Better, for the two most wanted: a built-in voice list and a speed choice, served by the PC (feasibility I28 already says "Now"). | Both | S (words) / M (the two choices) |
| 5 | **One home per kind.** Model switching and hardware setups on one card ("Model and graphics card"); one standby/quiet-hours schedule (retire `[power]` quiet hours or show it in the app); briefing time next to the briefing. Remove Brain's second theme picker. | Both + backend | M |
| 6 | **A "Recent changes" list** (read only): approvals and denials, and settings changed, newest first, in plain words ("Tue 9:14 - you approved: turn on 'Hey Jarvis'"). The PC already writes these events to its audit log; this reads them. Must show titles only, never private text (rule 1). | Both + backend | M |
| 7 | **Fix "What asks first" words**: the web search row should say "Asks only after outside text, or when 'Ask before every web search' is on"; merge the two "Read your calendar" rows. | Backend (both apps show it) | S |
| 8 | **Put secrets in one place.** Offer "Connect email / calendar / Home Assistant" boxes on the PC that save to Credential Manager, the way web search keys already do, instead of PowerShell and environment variables. | Desktop + backend | L |
| 9 | **A find box in chat history** (the owner's eyes only, on the PC's copy). Owner's call, because of the 2026-09-26 decision about searching past chats. | Both | M |
| 10 | Correct About and FAQ wording (`settings.html:1011-1013`, `:1277-1278`); delete the six "not read" lines or mark them "does nothing"; fix the stale comment at `:36-38`. | Desktop, file | S |
| 11 | Rename "Faculties" to "Model", "Long Fuse jobs" to "Background jobs"; keep the rest under Advanced. | Desktop | S |
| 12 | "Put back how it came" per card (voice, security, appearance) - tightening is instant, so a reset that only tightens needs no card. | Both | M |

## A clearer structure (proposal)

Seven groups, the same names and order in both apps. Settings that exist on
only one app keep their place and say so.

1. **Talking to Jarvis** - how Jarvis talks, Jarvis's voice (built-in and
   recorded, speed), "Hey Jarvis", interrupting, "One moment", "I heard you".
2. **Your voice** - train, how strict, private answers by voice, hands-free.
3. **What Jarvis may do** - What asks first, tools the AI may use, web
   search, lights without a card, sending email.
4. **Memory and history** - learn automatically, sensitive topics, always
   keep in mind, keep chat history, keep for.
5. **Schedules** - standby hours, morning briefing, how often Jarvis speaks
   up unasked.
6. **Look** - theme, text size, face, state colours, layout (phone).
7. **This PC / this phone** - connection and pairing, security and lock,
   model and graphics cards, starting with Windows, updates, logs, about.

Then **Help** (FAQ) and **Recent changes** as their own screens, not inside
Settings.

## Earlier audits: still unfixed (checked today)

| Audit item | Status |
|---|---|
| UI audit #13, desktop Settings jump list (`UI-AUDIT-2026-09-26.md:100`) | Not done |
| UI audit #14, a real phone Settings screen (`:101`) | Not done (`Nav.kt:72`) |
| UI audit #9, rename Mind → Brain and group its sections (`:91`) | Rename done (`BrainScreen.kt:244-246`); grouping not done |
| UI audit #19, shorter shortcut list on the bar (`:106`) | Not done: 9 `<kbd>` in `index.html` |
| Professionalism #15, phone has no "Settings" (`PROFESSIONALISM-AUDIT-2026-09-26.md:53`) | Not done |
| Professionalism #21, no README for `jarvis-client` saying where settings are (`:59`) | Not done (no `jarvis-client/README*`) |
| Continuity #1, "Hide memory lists…" describes itself wrongly | Fixed (`security-settings.js:147-154`) |
| Feasibility I28, speaking-speed setting in the apps (`FEASIBILITY-AUDIT-2026-09-26.md:149`) | Not built |

## Not checked

- How the phone screens actually look and scroll (no Android build here).
- Whether a hand edit of `jarvis-framework.toml` is picked up without a
  restart (INSTALL.md says restart; I did not test the reload path).
- Whether the running backend on the owner's PC uses `[persona]` at all -
  that code is not in this repo.
- Whether the apps show that the PC's `one_moment_enabled = false` overrides
  their own "One moment" switch. The desktop's words do not mention it
  (`voice-flow.js:253-258`).
- The desktop render used the test kit's sample data, so some live parts
  (for example all 63 "What asks first" rows) may be taller on a real PC.
