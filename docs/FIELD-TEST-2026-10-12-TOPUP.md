# Field test top-up, 2026-10-12: the uncovered 83, reconciled and read

**Written by a second pass the day after the first**, in the first pass's own shape and under its own
rule: **a feature that could not be reached is never a pass.** Every reading below is from an app's own
structures - the phone's accessibility tree, the desktop page over Windows UI Automation, or the
backend's own state - never from a picture of a screen.

**This does not rewrite the record.** `FIELD-TEST-2026-10-11-RESULTS.md` stays as the pass wrote it; this
file is what the second pass found, and it is the file to read for the 83 entries the first
record never reached.

## 1. The reconciliation, first (three corrections, each with its evidence)

1. **The list is 128 entries in 9 groups, not 122.** `tools/check_feature_list.py` at `origin/main`
   (`9c91e1fb`) prints: `128 entries in 9 groups; 122 of 139 route sections and menu ids covered, 17
   named in INTERNAL` and `5 passed, 0 failed`. **The 122 counts covered route sections and menu ids -
   the number in the checker's own second clause - not feature entries; its denominator is 139.** The
   entry count is 128, on main and on this branch alike (`git show origin/main:features/features.json`,
   128 ids).
2. **The three ids reported as no longer existing all exist.** `crash-notes`
   (`features/features.json:1119`), `first-run` (`:1156`) and `notifications` (`:1250`) are in the list at
   main **and** on this branch, and all three are also in `FIELD-TEST-MATRIX-2026-10-11.md` (lines 69,
   99, 101). **Nothing was renamed or removed: there is no id drift to reconcile.**
3. **The gap, with a validated pattern.** The record's rows carry the id in backticks *inside the feature
   column* (`| 8 | How strict the voice check is (`voice-check`) | both | PARTIAL | ... |`), and read that
   way the record yields **45 rows and 45 distinct ids**, whose verdicts are **12 PASS - 2 FAIL - 19
   PARTIAL - 10 BLOCKED - 2 NOT-TESTABLE**: exactly the tally the record's own audit line states. So the
   pattern is validated against the file rather than assumed. **The record covers 45 of 128; the
   uncovered set is 83.**

## 2. The instruments on the day, and what was not available

| instrument | state on 2026-10-12 |
|---|---|
| the phone | OnePlus `f0a5b32b` over adb, connected; read with `uiautomator dump` and driven through Find |
| the desktop app | running; its Settings window exposed **2,067 strings** over Windows UI Automation |
| the live backend | `127.0.0.1:4719`; the token read from the backend's own store at run time (`GET /api/status` -> HTTP 200). **Never printed, never written into this file** |
| vision | **none on this machine** - nothing below comes from a screenshot |
| the owner | his fingerprint/Windows Hello and his accounts are his; a harness cannot answer either |

## 3. Driven on the phone (20)

| id | feature | surface | verdict | evidence (raw, as the screen said it) |
|---|---|---|---|---|
| `typing` | Type a message and read the answer | both | **PARTIAL** | no row of its own: Find -> `type a message` offered **1 match**, an unrelated Brain row (`Retirement what-if`) |
| `talk-button` | The talk button | both | **PARTIAL** | no screen of its own: Find -> `talk button` landed in the **Brain** (`What Jarvis is doing`) |
| `briefing` | The morning briefing | both | **PARTIAL** | no screen of its own: Find -> `briefing` offered **1 match**, the Brain row `Morning briefing` (`What the morning briefing said.`) |
| `today` | Today | both | **PARTIAL** | no screen of its own: Find -> `today` landed in the **Brain** (`Money and time`) |
| `focus` | Focus session | both | **PARTIAL** | no screen of its own: Find -> `focus` landed in the **Brain** (`What Jarvis is doing`, `Money and time`) |
| `history` | Your past chats | both | **BLOCKED** | Find -> `history` says **`Nothing matches that.`** - the hidden memory menus (see the cause below) |
| `forget-range` | Forget a time frame | both | **BLOCKED** | Find -> `forget a time` says **`Nothing matches that.`** - the hidden memory menus (see the cause below) |
| `pictures` | Ask for a picture, and keep it | both | **PARTIAL** | no screen of its own: Find -> `picture` landed in the **Brain** (`Your projects and goals`, `Jarvis on your PC`) |
| `documents` | Ask about a PDF, a Word file or a Notion page | both | **PARTIAL** | Find -> `PDF` says **`Nothing matches that.`** - asking about a PDF has no row of its own on the phone |
| `connection` | Pairing and the connection | both | **PASS** | Find -> `connection` opened the phone's own **Connection** screen, read whole: `Platform checks \| What this phone will and will not allow \| Connection \| Connected \| Connected, and updates are arriving. \| Desktop \| <the owner's own address - elided, the record's rule> \| Reconnect \| Change desktop or token \| Your current desktop and token stay saved until new ones connect.` |
| `phone-screen-rate` | Screen refresh rate | phone | **PARTIAL** | no row of its own: Find -> `refresh` offered **1 match**, `Settings / Screen refresh rate` (`The rate the screen is asked to run at while Jarvis is on screen.`) - the setting is real, but there is no row to open |
| `appearance` | Appearance | both | **PASS** | Find -> `appearance` opened the **APPEARANCE** screen, read whole: `Settings \| APPEARANCE \| Theme, the reactor's face, the animal options, and how it all looks. \| APPROVAL CARDS \| Cards that ask for your OK. This only changes how much of a card is shown at first - the same card, the same words underneath, the same buttons. \| Start short (default) (in use) \| Always show everything` |
| `animal-options` | Animal options | both | **PARTIAL** | no row of its own: Find -> `animal options` offered **1 match**, and it is the **Appearance** row (`Theme, faces and how it all looks.`). The desktop Settings page does have an `Animal options` section (see below) |
| `models` | Models | both | **PARTIAL** | no screen of its own: Find -> `models` landed in the **Brain** (`Jarvis on your PC`) |
| `compute` | Compute | both | **PARTIAL** | no screen of its own: Find -> `compute` landed in the **Brain** (`Jarvis on your PC`) |
| `job-list` | Jobs that keep going after the chat ends | both | **PARTIAL** | no screen of its own: Find -> `jobs that keep going` offered **2 matches**, both Brain rows (`Background jobs` - `Long jobs Jarvis is running.` - and `Coming up`) |
| `hardware` | Hardware and models | both | **PARTIAL** | no screen of its own: Find -> `hardware` landed in the **Brain**, on the `Jarvis on your PC` plate (`EVERYTHING JARVIS CAN DO`). The desktop Settings page has `Hardware and models` (see below) |
| `updates` | Updates | both | **PARTIAL** | Find -> `updates` says **`Nothing matches that.`** - no row on the phone. The desktop Settings page has `Updates` and `Check for tool updates` (see below) |
| `undo` | Undo | both | **PARTIAL** | no row of its own: Find -> `undo` offered **1 match**, `Settings / Limits and how often Jarvis does things` (`How long an Undo stays possible, how much Jarvis gets on with at once, and the other numbers you can change.`) |
| `stale-link` | When the connection is catching up | both | **BLOCKED** | Find -> `catching up` says **`Nothing matches that.`** - no row on the phone |

## 4. Real on the live desktop Settings page, not driven (34)

**PARTIAL, and PARTIAL is the honest verdict**: the page really carries the row and its own words, and
the *behaviour* behind it was not driven. Each line quotes the live page, with its position in the 2,067
strings the window exposed so a reader can re-check it.

| id | feature | surface | verdict | evidence |
|---|---|---|---|---|
| `manner` | How Jarvis talks | both | PARTIAL | the live Settings page really carries it: **`How Jarvis talks`**, and its own words beside it: "A new conversation starts after" (strings 23 and following, from the 2,067 the window exposed) |
| `prompt-coach` | Check a prompt before you send it | both | PARTIAL | the live Settings page really carries it: **`Prompt coach`** (strings 25 and following, from the 2,067 the window exposed) |
| `read-aloud` | Jarvis reads its answers aloud | both | PARTIAL | the live Settings page really carries it: **`Read aloud`**, and its own words beside it: "Whether answers that use what Jarvis remembers are spoken out loud when you ask by voice, or kept on screen. Health, money, passwords and other people's private details always stay on screen, whichever you pick here." (strings 101 and following, from the 2,067 the window exposed) |
| `custom-voices` | The voice Jarvis speaks with | both | PARTIAL | the live Settings page really carries it: **`Voice`**, and its own words beside it: "A new conversation starts after" (strings 22 and following, from the 2,067 the window exposed) |
| `devices` | Devices | both | PARTIAL | the live Settings page really carries it: **`Devices`** (strings 17 and following, from the 2,067 the window exposed) |
| `folders` | Folders Jarvis may look in | both | PARTIAL | the live Settings page really carries it: **`Folders Jarvis may look in`**, and its own words beside it: "Look at this and Watch with me" (strings 48 and following, from the 2,067 the window exposed) |
| `spending` | Spending summaries | both | PARTIAL | the live Settings page really carries it: **`Spending`**, and its own words beside it: "Look at this and Watch with me" (strings 49 and following, from the 2,067 the window exposed) |
| `backup` | Backups | both | PARTIAL | the live Settings page really carries it: **`Backups`**, and its own words beside it: "Keeping it up to date" (strings 55 and following, from the 2,067 the window exposed) |
| `tool-updates` | Check for tool updates | desktop | PARTIAL | the live Settings page really carries it: **`Check for tool updates`**, and its own words beside it: "What Jarvis can reach" (strings 58 and following, from the 2,067 the window exposed) |
| `reach` | What Jarvis can reach | both | PARTIAL | the live Settings page really carries it: **`What Jarvis can reach`**, and its own words beside it: "What this backend supports" (strings 63 and following, from the 2,067 the window exposed) |
| `limits` | Limits and frequency | both | PARTIAL | the live Settings page really carries it: **`Limits and frequency`**, and its own words beside it: "What this backend supports" (strings 64 and following, from the 2,067 the window exposed) |
| `backend-supports` | What this backend supports | both | PARTIAL | the live Settings page really carries it: **`What this backend supports`**, and its own words beside it: "Looking for chat history, saved facts or background learning? Those live in the" (strings 68 and following, from the 2,067 the window exposed) |
| `widgets` | Widgets you describe | both | PARTIAL | the live Settings page really carries it: **`Widgets you described.`**, and its own words beside it: "What the morning briefing said." (strings 746 and following, from the 2,067 the window exposed) |
| `jobs` | Background jobs | both | PARTIAL | the live Settings page really carries it: **`Background jobs`**, and its own words beside it: "Long jobs Jarvis is running." (strings 750 and following, from the 2,067 the window exposed) |
| `topics` | Topics | both | PARTIAL | the live Settings page really carries it: **`Topics`**, and its own words beside it: "A mode for each topic of what Jarvis learns." (strings 696 and following, from the 2,067 the window exposed) |
| `wiki` | The wiki Jarvis builds | both | PARTIAL | the live Settings page really carries it: **`The wiki Jarvis builds from your notes.`**, and its own words beside it: "Slow questions and their answers." (strings 713 and following, from the 2,067 the window exposed) |
| `deep-questions` | Deep questions | both | PARTIAL | the live Settings page really carries it: **`Deep questions`**, and its own words beside it: "Slow questions and their answers." (strings 714 and following, from the 2,067 the window exposed) |
| `import-chats` | Bring in old chats | desktop | PARTIAL | the live Settings page really carries it: **`Bring in old chats`**, and its own words beside it: "Import chats from another AI." (strings 693 and following, from the 2,067 the window exposed) |
| `galaxy` | Galaxy | desktop | PARTIAL | the live Settings page really carries it: **`Galaxy`**, and its own words beside it: "The map of what Jarvis knows." (strings 684 and following, from the 2,067 the window exposed) |
| `tutorials` | Tutorials and the FAQ | both | PARTIAL | the live Settings page really carries it: **`Tutorials and the FAQ`**, and its own words beside it: "How Jarvis works, step by step, and the answers to the usual questions." (strings 681 and following, from the 2,067 the window exposed) |
| `picture-mode` | Picture mode | both | PARTIAL | the live Settings page really carries it: **`Picture mode`**, and its own words beside it: "By default Jarvis reads only the words on your screen. Picture mode also lets a small picture reader look at the picture itself, so it can tell what a chart, a button or a photo shows. It runs on your PC's main chip (the" (strings 1653 and following, from the 2,067 the window exposed) |
| `quiz` | Quiz me on a text | both | PARTIAL | the live Settings page really carries it: **`Quiz me on a text`**, and its own words beside it: "Questions on a text you paste or a YouTube link." (strings 525 and following, from the 2,067 the window exposed) |
| `decks` | My study decks | both | PARTIAL | the live Settings page really carries it: **`My study decks`**, and its own words beside it: "Questions kept to study again." (strings 531 and following, from the 2,067 the window exposed) |
| `web-search` | Web search | both | PARTIAL | the live Settings page really carries it: **`Web search`** (strings 39 and following, from the 2,067 the window exposed) |
| `chatbot` | Talk to a chatbot for me | both | PARTIAL | the live Settings page really carries it: **`Talk to a chatbot for me`**, and its own words beside it: "Jarvis holds a conversation with another AI for you." (strings 579 and following, from the 2,067 the window exposed) |
| `projects` | Projects | both | PARTIAL | the live Settings page really carries it: **`Projects`**, and its own words beside it: "Projects, their notes and benchmarks." (strings 539 and following, from the 2,067 the window exposed) |
| `goals` | Goals | both | PARTIAL | the live Settings page really carries it: **`Goals`**, and its own words beside it: "Plans you edit, with a weekly check-in." (strings 542 and following, from the 2,067 the window exposed) |
| `progress` | Progress | both | PARTIAL | the live Settings page really carries it: **`Progress`**, and its own words beside it: "The activity heatmap and balance chart." (strings 545 and following, from the 2,067 the window exposed) |
| `retirement` | Retirement what-if | both | PARTIAL | the live Settings page really carries it: **`Retirement what-if`**, and its own words beside it: "A simple what-if from numbers you typed." (strings 593 and following, from the 2,067 the window exposed) |
| `skills` | Skills | both | PARTIAL | the live Settings page really carries it: **`Skills`**, and its own words beside it: "Installed skills with scan verdicts." (strings 732 and following, from the 2,067 the window exposed) |
| `shortcuts` | Keyboard shortcuts | desktop | PARTIAL | the live Settings page really carries it: **`Keyboard shortcuts.`**, and its own words beside it: "Custom voices and the voice pack." (strings 615 and following, from the 2,067 the window exposed) |
| `second-card` | The second graphics card | both | PARTIAL | the live Settings page really carries it: **`Second graphics card`**, and its own words beside it: "Folders Jarvis may look in" (strings 45 and following, from the 2,067 the window exposed) |
| `stop-everything` | Stop everything | both | PARTIAL | the live Settings page really carries it: **`Stop everything`**, and its own words beside it: "Stop everything: Alt + Shift + X. Press to change." (strings 797 and following, from the 2,067 the window exposed) |
| `hud-window` | The big HUD window | desktop | PARTIAL | the live Settings page really carries it: **`The big HUD window`** (strings 31 and following, from the 2,067 the window exposed) |

## 5. BLOCKED or NOT-TESTABLE, with the reason (18)

| id | feature | surface | verdict | why |
|---|---|---|---|---|
| `memory-saved` | Facts Jarvis saved by itself | both | **BLOCKED** | the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (the cause the record pinned for five features) |
| `memory-waiting` | Facts waiting for your yes | both | **BLOCKED** | the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (the cause the record pinned for five features) |
| `memory-people` | People and things | phone | **BLOCKED** | the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (the cause the record pinned for five features) |
| `memory-learning` | The learning switches | both | **BLOCKED** | the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (the cause the record pinned for five features) |
| `calendar` | Read your own calendar | desktop | **NOT-TESTABLE** | the desktop Settings page's own words: **"Not included: your calendar is not set up for Jarvis on this PC."** (the page's live text) |
| `email-read` | Jarvis reads your email | both | **NOT-TESTABLE** | the desktop Settings page's own words: **"Not included: how many unread emails you have is not set up for Jarvis on this PC."** (the page's live text) |
| `inbox-tidy` | Tidy the inbox by voice | both | **NOT-TESTABLE** | needs the mail account the page says is not set up here, and the inbox routes read it |
| `weather-sky` | Weather and the sky behind the animals | both | **NOT-TESTABLE** | the desktop Settings page's own words: **"Not included: the weather is not set up for Jarvis on this PC."** (the page's live text) It comes only from the owner's own Home Assistant |
| `lights` | Lights, plugs and fans | both | **NOT-TESTABLE** | needs the owner's Home Assistant and devices paired to it; the page says Home Assistant **needs Home Assistant set up for Jarvis on the PC** |
| `locks` | Locks, doors, alarms and covers | both | **NOT-TESTABLE** | same as `lights`: Home Assistant, not set up here, and locks always keep a card of their own |
| `email-send` | Send an email for you | both | **NOT-TESTABLE** | needs the owner's mail account (not set up here) and his approval, one card per email |
| `email-drafts` | Save a draft to your Drafts folder | desktop | **NOT-TESTABLE** | needs the owner's mail account (not set up here) |
| `accounts` | Accounts and keys | desktop | **NOT-TESTABLE** | the owner's accounts and keys - they are his, and the page keeps them under `Accounts` |
| `chatbot-money` | Chatbot keys and a monthly money limit | desktop | **NOT-TESTABLE** | needs chatbot API keys and a monthly amount the owner sets on the PC |
| `app-lock` | Lock Jarvis, and hide what it remembers | both | **BLOCKED** | turning it off or on is the owner's own Windows Hello / phone lock; a harness cannot answer a fingerprint prompt |
| `trust` | Trust: content risk and the audit chain | both | **BLOCKED** | the audit chain's own state is set by approvals the owner decides |
| `approvals` | Approval cards | both | **BLOCKED** | an approval card needs a person to decide it; raising one and answering it are both the owner's |
| `past-approvals` | Activity: cards you already decided | both | **BLOCKED** | it lists what the owner already decided; nothing to read until he has |

**The one cause worth naming twice:** the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change, so Find does not offer them (the cause the record pinned for five features).

**Corrected 2026-10-12, by measurement - and this line is left as written above.** The switch itself sits
behind the phone's fingerprint, so these rows are blocked by a **biometric gate, and only the owner can
lift it**: tapping `Hide memory lists and chat history` drew **`Loosen security` / `Confirm it is you.` /
`Touch the fingerprint sensor`**, and the Brain's own `Show` control drew **`Show memory lists` /
`Confirm it is you.`** The prompt was cancelled both times and the switch was re-read still ON. See
`docs/FIELD-TEST-2026-10-12-TOPUP-3.md` - a future pass should read these rows as the owner's to unlock,
not as a harness task.

## 6. Not driven in this pass, and no reason invented (11)

These are named plainly as **UNTESTED**. The instruments above were available; this pass was bounded, and
an invented obstacle is worse than an honest gap.

| id | feature | surface | verdict | why |
|---|---|---|---|---|
| `spoken-style` | Short answers to spoken questions | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `voice-training` | Teach Jarvis your voice | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `chat-thread` | The whole conversation, and carrying it on | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `photo-reminder` | Photo to reminder | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `browser-engine` | A browser without a window | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `support` | Deal with customer support for me | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `news-and-page-watches` | News headlines, and pages that change | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `phone-limits` | What the phone deliberately does not do | phone | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `start-jarvis` | Starting Jarvis for you | desktop | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `settings-file` | The settings file, the logs and starting with Windows | desktop | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |
| `settings-entry` | Settings itself | both | UNTESTED | not driven in this pass; the instruments were available and the pass was bounded - no reason is invented for it |

## 7. Not verified on screen, and not claimed: the grey frames (#324)

**The owner's report:** two flat grey boxes that vanish when Jarvis exits and return when it starts - a
wide band upper-middle **from the bar**, and a large square bottom-right **from notifications** - and
`rgb(84,84,84)` appears nowhere in this repository, so it is a platform/WebView2 default rather than a
colour anybody chose. **#324** (`fix/transparent-windows-set-their-background`) makes the transparent
windows set their own background, so an unpainted frame shows the desktop rather than the platform grey.

**Its status here is plain: NOT YET VERIFIED ON SCREEN.** The mechanism is established and it compiles
clean; **nobody has watched it draw** - and this pass did not either. Two reasons, both stated rather
than glossed: UI Automation reads the page's own structures and says nothing about pixels, and there is
**no vision provider on this machine**. So neither the bar nor the notifications window can be confirmed
fixed by this method, and this record does not claim it.

## 8. What this pass did not do

- **No setting was changed.** On the phone the harness only went Home, opened Find, searched and tapped a
  result row. On the desktop the Settings window was opened with its own gear (and is where it was left).
- **The crisis path was not provoked** - the record's own decision, unchanged.
- **Nothing private is written down**: no message text, no memory, no token, no address. The token was read
  at run time and kept out of this file.
- **No number is quoted from a checkout other than the source named beside it**: the list numbers come from
  `git show origin/main:<path>`, the phone lines from the phone's own dumps, the Settings lines from the
  live window.
