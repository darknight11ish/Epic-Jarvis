> **Committed 2026-10-11, copied from .dsh-scratch/fieldtest-2026-10-11/RESULTS.md.** Everything
> below is as the pass wrote it that day. **One verdict below was later corrected:** row 44
> (watch-with-me) reads "the session could not be stopped", and the backend's own state disproved
> that - GET /api/screen answered "state":"ended", "ended":"owner". What is broken is the
> **badge**, which stays on screen with a falling countdown. FIELD-TEST-MATRIX-2026-10-11.md carries
> the corrected row in its second pass; this record is left as it was written.

# Field test: everything that has never been field-tested

**Started** 2026-10-11, after the owner asked for every untested feature to be run on real hardware.
**Source list** `docs/FIELD-TEST-MATRIX-2026-10-11.md` (on main) — 45 features:
17 NEVER TESTED, 15 NOT FOUND, 13 TEST-VERIFIED ONLY.

**Verdicts, and what each means** (a feature that cannot be reached is never a pass):

| verdict | meaning |
|---|---|
| **PASS** | driven on real hardware and the expected thing happened; evidence recorded below |
| **FAIL** | driven and the wrong thing happened — a defect, with the evidence |
| **PARTIAL** | some of it was driven; say exactly which part and why the rest was not |
| **BLOCKED** | could not be reached because something else is broken (name the blocker) |
| **NOT-TESTABLE** | needs hardware, a service, or an instrument this machine does not have |
| **UNTESTED** | not started yet |

**Devices in play:** OnePlus CPH2419 `f0a5b32b` over adb (the phone); the desktop app on the
owner's PC; and the live backend on 127.0.0.1:4719 reached with the pairing token
(**never printed, never logged**).

**How each surface is read — no screenshots, no vision:**
- **Phone:** `uiautomator dump` — the phone app's own accessibility tree (`phone-lookup.ps1`).
- **Desktop:** **Windows UI Automation** — the Tauri/WebView2 app exposes its whole page, so its
  real text and its real controls are both reachable (`desktop.ps1`). This was discovered during
  the pass and it is what makes the desktop half testable at all.

**Hard limits I am holding to:** no feature that would destroy the phone's pairing
(`first-run` needs a fresh install — it goes last, or not at all); the crisis path is not
provoked casually; nothing private (message text, memory, token, address) is written into
this file; and the phone is driven by one process at a time.

---

## 1. Never tested (17)

| # | feature | surface | verdict | evidence |
|---|---|---|---|---|
| 8 | How strict the voice check is (`voice-check`) | both | PARTIAL | Find → `strict` gives **one match, and it is the `Voice` section** (`Talk, read aloud, hands-free and sounds.`) — so the setting exists but not under a "How strict" row of its own; opening Voice was not done in this batch |
| 11 | Interrupt Jarvis while it talks (`interrupt`) | both | PARTIAL | Find → `interrupt` gives **one match: `Attention budget`** (`How many interruptions are left.`) — so there is **no screen of its own**; interrupting is a behaviour, and testing it needs a live spoken answer to cut into |
| 13 | The extras around Live (`live-extras`) | both | PARTIAL | **no row of its own** — Find → `live extras` offers two matches (`Screens / Jarvis Live` and `Settings / Voice`). The extras are **behaviours and OS surfaces** (a Quick Settings tile, a headset button, a 10-minute "Live ended - Resume" notification, a PC hotkey, preferring a Bluetooth headset mic, and "Talk about this in Live" from Share), so testing them needs a Live session and, for some, hardware |
| 19 | Timers, alarms, reminders and lists (`coming-up`) | both | BLOCKED — **cause pinned to one number** | On `edf85d2f` the screen's own key list and the list's count were printed side by side: **`screen declared=19 … hasWanted=true`, `composed=11`, `found=false`** — and `head` shows **`brain-plate:coming-up` is the eighth entry of the declared list**. So the plate is **declared** (and `shown=true`), and **the list registers only eleven of the nineteen rows the screen declares**. That is neither the walk nor the screen's keys: **the content lambda is not registering eight declared rows.** `coming-up` is unreachable on the phone, so it is **not** a pass — but the defect is now one place with a number behind it, and **eight of nineteen rows missing means the Brain draws a third less than it declares**, which is bigger than this feature |
| 31 | Always keep in mind (`pinned-facts`) | both | BLOCKED | the menu exists — `MenuCatalog.kt:100` `brain.memory.profile`, "Always keep in mind" — but Find → `keep in mind` offers **no such row** (its one match is an unrelated Settings row). Find only offers a row whose menu is **shown**, and the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the owner's fingerprint can change |
| 37 | What did I believe on this date? (`memory-as-of`) | phone | BLOCKED | the menu exists — `MenuCatalog.kt:107` `brain.memory.as-of` — but Find → `believe` says **`Nothing matches that.`** Same cause as `pinned-facts`: the memory menus are hidden by the phone's privacy setting, so Find does not offer them |
| 43 | Look at this (`look-at-this`) | both | **PASS** | **driven on the desktop with its own key.** The Settings page names it — `Look at this: Alt + Shift + S` — so I sent that, and it opened **`Jarvis and your screen`** showing **`Looked at: DeepSeek Harness window · words only`** (that is the window that was in front — this session's own terminal), a **`Forget this look`** control, and the line `Secrets in pictures you attach are covered with black boxes before Jarvis looks.` One press, one read, and the words-only mode reported honestly |
| 44 | Watch with me (`watch-with-me`) | both | **FAIL — the SIGN does not clear, not the Stop** | **Corrected after a wrong first report.** The Stop **works**: `GET /api/screen` returned `{"state":"ended","on":false,"ended":"owner","ended_words":"you stopped it"}` — and `ended:"owner"` is the string the backend's `ENGINE.stop()` writes, so **one of my Stop clicks ended it**, while it was paused. **What is broken is the badge:** it stayed on screen for **over twenty minutes** after the session ended, reading `Jarvis is watching - paused / Paused: one of Jarvis's own windows · 8 min left`, with the countdown still decreasing. Its owner traced why: the badge listens for a `screen-status` event that only fires when **that app** makes the call, fetches the status **once at startup**, and **decrements `left_s` locally** — so any ending that does not come through the app's own command leaves the sign up **for ever**. **A permanent false privacy alarm.** The pause rule and the sign both behaved correctly |
| 47 | Show Jarvis the camera in Live (`live-camera`) | phone | PARTIAL | **no row of its own** — Find → `camera` offers one match, `Settings / Look at this and Watch with me` (`The screen feature's lists and picture mode.`), so the camera setting lives inside that section. It also needs the 12 GB card per the design |
| 66 | Health and money facts wait for your yes (`sensitive-facts`) | both | BLOCKED | Find → `sensitive` says **`Nothing matches that.`** Same cause as the rest of the memory group: the `brain.memory.*` menus are hidden by "Hide memory lists and chat history" |
| 82 | Floating Jarvis (`phone-floating`) | phone | **PASS** | Find → `floating` → the phone drew `FLOATING JARVIS` with its three choices `Off / Bubble / Overlay` and the live line `Off. Nothing floats over other apps.` |
| 83 | Quick Settings tiles (`phone-tiles`) | phone | **PASS** | Find → `tiles` → `QUICK SETTINGS TILES`, with `Tile 1 - 10-min timer`, `Tile 2 - Open briefing` and the whole choice list (`Nothing / Focus session / 10-min timer / Open briefing / Stop everything / Play&pause PC`) |
| 90 | Choose Jarvis's face (`faces`) | both | PARTIAL | the Appearance page opens and reads correctly (THEME, HOME, face sizes, tabs row), but the FACE section is **drawn, not text** — `uiautomator` sees no labels and there is no vision provider here, so the picker itself could not be driven |
| 101 | The Work tab (`work-tab`) | desktop | BLOCKED | it lives in the **desktop Brain window**, and that window could not be opened from here. Three routes were tried and all failed: the **tray icon is not exposed by name in the taskbar** (it is inside the "Show Hidden Icons" overflow, where the button is `Jarvis — connecting… · Alt+Space Jarvis — thinking · Power: active`; a right-click on it did not produce a readable menu), **no in-app control opens the Brain** (the Settings page says *"open it from the tray icon, 'Open the Brain'"*), and the HUD's **GALAXY tab is a different view** (the galaxy graph with a `Search the brain…` box, not the Brain window). **A person at the machine with a mouse can reach it in two clicks; this harness cannot** |
| 119 | What asks first (`what-asks-first`) | both | **PASS** | Find → `asks` → 3 matches → `WHAT ASKS FIRST`, `Lockdown is off: everything asks first as your settings say.`, `Turn on Lockdown`, and each action with its `Ask me first` control |
| 121 | Hand a captcha to your phone (`captcha-handoff`) | both | **PASS** | Find → `captcha` → the phone drew `WHEN A CAPTCHA STOPS JARVIS`, in full: *"When Jarvis is stuck on a captcha or a sign-in page, it can leave that browser window exactly where it is - or bring it to the front so you can type into it."*, with both choices and what each does — `Leave it where it is (in use)` (the window is not touched) and `Bring it to the front` (raises it, *"takes your screen and your keyboard away… so turning this on asks for your approval"*). Marked in use |
| 126 | Jarvis marks what it read from outside (`outside-text`) | both | PARTIAL | **no Find row** — Find → `outside` says `Nothing matches that.` It is a **marking behaviour** on answers that used outside text, so testing it needs a turn that reads an email, file or page |

## 2. Not found — no evidence either way (15)

| # | feature | surface | verdict | evidence |
|---|---|---|---|---|
| 14 | Talk-to-type (`talk-to-type`) | desktop | PARTIAL | the desktop Settings row is real and reports its own live state: `Talk-to-type (this PC only)`, `Talk-to-type: hold a key, speak, and Jarvis types what you said`, and **`Nothing listens for the talk-to-type key.`** Turning it on needs an approval card plus Windows Hello (the owner), and the typing itself needs someone at the PC |
| 17 | Search what was said (`history-search`) | both | PARTIAL | **no Find row** — Find → `history` says `Nothing matches that.` It lives in History ("Earlier chats" on Home), which was not opened in this batch |
| 26 | The Memory tab (`memory-tab`) | desktop | BLOCKED | same cause as the other memory features: the `brain.memory.*` menus are hidden on the phone by "Hide memory lists and chat history", and the desktop Brain — where this tab lives — was not opened (the tray icon is not exposed to UI Automation by name, and the Jarvis bar does not lead to it) |
| 29 | What Jarvis knows about you (`memory-known`) | desktop | BLOCKED on the phone / seen on it | the menu exists (`MenuCatalog.kt:104`, `brain.memory.known`) and the phone **did draw the row** in the Brain — but with its own hidden state under it: **`Hidden. Tap Show and confirm it is you.`** That line is the feature working as designed, and the confirmation is the owner's fingerprint. The desktop half was not driven |
| 50 | Write a note for you (`notes-write`) | both | PARTIAL | **no row of its own** — Find → `note` offers two unrelated matches (`Settings / What Jarvis can reach`, and `Brain`). It is an **action**, so asking is the honest test |
| 57 | What's new on GitHub (`github-watchlist`) | both | PARTIAL | **no row of its own** — Find → `github` landed in the Brain (the match is a Brain row). It is an **action/plate**, so asking is the honest test |
| 67 | Crisis help (`crisis-help`) | both | **NOT-TESTABLE — deliberately** | **I did not provoke it.** A field test has no business staging a crisis to see what happens, and the feature's own behaviour is the one place in this app where a false trigger and a false negative both matter. It is recorded as untested **by choice**, not because it could not be reached. Its content is documented in the project's own decisions: the United States lines are **988** (Suicide & Crisis Lifeline) and **911**, crisis turns are **never learned from, never counted**, and a crisis question and its answer do **not** stay in the scrollable thread |
| 68 | Ask how the house is (`home-status`) | both | NOT-TESTABLE — **with a reason, not a shrug** | it reads **his own Home Assistant**, and there is none set up on this machine, so there is nothing for it to read. The distinction matters: this is not "I could not reach it" but **"the thing it talks to does not exist here"** — a different answer, and the one a reader should get |
| 81 | Smartwatch notifications (`phone-watch`) | phone | PARTIAL / NOT-TESTABLE | the row is **real and readable** — Find → `smartwatch` landed on the `NOTIFICATIONS` screen with `Show notifications on a compatible watch`. **The behaviour cannot be tested here: no paired watch.** The row's existence is now evidenced; the feature is not |
| 85 | Also on my phone (`also-on-phone`) | both | PARTIAL | **no Find row** — Find → `also on my phone` says `Nothing matches that.` It hands an alarm or event to the phone's own apps by the owner's tap, so it needs a share sheet rather than a screen |
| 89 | Hang and crash notes (`crash-notes`) | desktop | **FAIL** | the row **is not on his desktop Settings page at all**: the word `crash` appears **zero times** in all **2,067** strings the Settings window exposes, though the row is supposed to be there (`jarvis_settings_registry.py:289-292`, `DESKTOP`-gated). Not rendered, gated off, or not reaching the page — needs a second look. (The phone's crash **screen** does exist and is real; a **hang** had no path at all until #297) |
| 92 | Set up Jarvis (`first-run`) | desktop | PARTIAL | the entry exists — `Set up Jarvis`, `The five-screen welcome Jarvis shows by itself once on a new PC… open it from here` — and clicking it **invoked**, but **neither window's text changed afterwards**, so what it opens was not observed |
| 98 | Memory on the Model page (`model-memory`) | desktop | PARTIAL | the row exists; its own words are in the page: `The memory summary on the Model page.` Not driven |
| 110 | About Jarvis (`about`) | both | **PASS** | Help → scrolled to the About card: `Version 0.2.1227`, `Made by darknight11ish`, `MIT, with third-party parts under their own licences`, the source link, the notices link. Real version, not the local build's `0.2.0` |
| 125 | A warning when text tried to rush you (`rush-latch`) | phone | PARTIAL | **no Find row at all** — Find → `rush` says `Nothing matches that.` It is a **behaviour** (a warning shown when text tries to rush you), so testing it needs a turn with rushing text |

## 3. Test-verified only — suites pass, never driven (13)

| # | feature | surface | verdict | evidence |
|---|---|---|---|---|
| 4 | Say "Hey Jarvis" (`wake-word`) | both | PARTIAL | **no row** — Find → `hey jarvis` offers one unrelated match (`Screens / Jarvis Live`). It is a **behaviour** needing a voice, not a screen |
| 12 | Jarvis Live (`live`) | both | PARTIAL | **the screen is real and reachable**: Find → `jarvis live` drew `Jarvis Live` with a **`Start Jarvis Live`** control. **The session itself was not started, deliberately**: a Live session opens the phone's microphone and there is nobody here to talk to it, so starting one would have tested the microphone rather than the feature |
| 16 | Temporary chat (`temporary-chat`) | both | **PASS** | driven from the desktop's Jarvis bar: `clicked 'Temporary chat': toggled to Off` — it was **On**, so the control works and reports its own state. **I noticed and put it back: a second click returned `toggled to On`.** Real state, changed and restored |
| 23 | What Jarvis is doing right now (`now`) | both | **PASS** | Find → `doing` → landed in the Brain with the `What Jarvis is doing` plate drawn and unfolded |
| 24 | How much Jarvis may interrupt you (`attention-budget`) | both | **PASS** | Find → `attention` → the plate drew with its own words: `ATTENTION BUDGET`, `of 3 spoken interruptions left today`, `Speak up`, and the count's own explanation |
| 32 | Between us (`between-us`) | both | BLOCKED | **not a defect — a privacy setting.** The menu exists (`MenuCatalog.kt:101` `brain.memory.between-us`, "Between us", "Inside jokes and shared references.") but Find → `between` says `Nothing matches that.` Find only offers a row whose menu is **shown** (pinned by `ComingUpReachabilityTest`, and by the hideable-menu contrast test), and the `brain.memory.*` menus are hidden on this phone by **"Hide memory lists and chat history"**. Turning that off needs the owner's fingerprint |
| 40 | Chat tags (`chat-tags`) | both | BLOCKED | Find → `tags` says **`Nothing matches that.`** — part of the same hidden memory group |
| 54 | PC help (`pc-help`) | phone | PARTIAL | **no screen of its own** — Find → `PC help` landed in the Brain (the match is a Brain row). Like `find-phone` it is an **action**, so asking is the honest test |
| 80 | Let Jarvis read phone notifications (`phone-notifications`) | phone | **PASS** | Find → `phone notifications` → the phone drew `PHONE NOTIFICATIONS` with its own live state: `Let your phone read notifications`, `Off by default. Jarvis never sees a phone notification unless you turn this on AND add at least one app below.`, `Jarvis never sees a phone notification.`, `Android's own permission`, **`Notification access: not granted yet.`**, `Turn on Notification access`, `Apps Jarvis may read` |
| 86 | Ring my phone (`find-phone`) | both | **PASS** | **driven by asking**, which is the only honest way for a feature with no screen: typed `ring my phone` into the phone's own chat box; Jarvis answered `Ringing your phone now - for up to a minute, even on silent, if the Jarvis app on it is connected. Press Stop on the phone to stop it.` — **and the phone's own notification confirms it really rang**, not just that the model said so: `title = "Jarvis is ringing this phone"`, `text = "You asked Jarvis to find your phone. Press Stop to stop the ringing."`, `SCHEDULE_KIND = ring_phone`, `tag = find-phone:ra2848069de66`, `channel = jarvis_alarm` |
| 93 | Show or hide menus (`menu-visibility`) | both | **PASS** | Find → `menus` → `SHOW OR HIDE MENUS`, with `This hides menus on this device only.`, `Hiding a menu only tidies it away. Nothing is turned off…`, `Nothing is hidden.`, `Show everything`, and per-menu rows naming what each one hides |
| 99 | Notifications (`notifications`) | desktop | PARTIAL | the desktop Settings section is real: `Notifications`, `NOTIFICATIONS`, `Start reading notifications from apps you choose on your phone - Asks you first, every time`. Not driven |
| 105 | The big model (slow) (`big-model`) | both | BLOCKED | the desktop row exists (`Big model (slow)`, `BIG MODEL (SLOW)`); turning it on needs the owner's click through Windows Hello |

---

## Progress log

- **2026-10-11, the fix that follows the pass — and the most important finding it produced.** With
  `coming-up` pinned to "the open section writes zero rows", the fix was specified as **draw the
  plates that have no `-hidden` twin**. Before the diff existed, the reviewer checked the five
  plate names it had called "correctly hidden" and found **`deep-questions` has no guard at all**:
  `BrainScreen.kt:1377` is `DeepQuestionsSection(canAct = canAct)` — `privateHidden` is never
  passed and the section has no hidden state of its own. **Its safety rested entirely on the rule
  that was about to change, so the fix as written would have made the deep questions visible with
  "Hide memory lists and chat history" ON** — a privacy regression wearing a bug fix's clothes,
  **one line from the change**. It was found because the review standard was written down *before*
  the diff, and because the reviewer checked its own uncertain claims instead of defending them.
  (`memory-counts`'s guard is **indirect** — forwarded to a child — so a top-level check would
  wrongly call it unguarded; recorded so nobody "fixes" it.)
- **2026-10-11, record audit** — **45 rows, every one carrying a verdict and its own evidence**:
  PASS 12 · FAIL 2 · PARTIAL 19 · BLOCKED 10 · NOT-TESTABLE 2. No row was allowed to stay blank, and
  no row that could not be reached was counted as a pass.

- **2026-10-11, batch 4 (phone) — a systemic finding about reaching features at all.** Six more
  targets, and **not one of them had a Find row of its own**: `history-search` and `also-on-phone`
  say **`Nothing matches that.`**; `notes-write` and `wake-word` offer only unrelated rows;
  `github-watchlist` and `live-camera` land in the Brain or inside another section. **That is a
  pattern, not six accidents.** The app's own `features.json` says where each feature lives
  (*"Brain, Memory, Always keep in mind"*), but **Find — which claims to search every screen, every
  setting and everything the app can open — cannot reach many of them.** See the note below.
- **A note for the owner, not a defect list:** across four batches, the features that *drew a screen
  when asked* passed almost every time, and the ones that failed were almost all **features with no
  screen** (actions and behaviours) or **features whose menu the owner's privacy setting hides**.
  **Twenty of the 45 now read PARTIAL or BLOCKED, and most of those are "there is nothing to
  point at", not "it is broken".** That distinction is the whole reason this pass is worth doing:
  the matrix's "NOT FOUND" column was mostly *missing evidence*, and it is now mostly *a named
  reason*.

- **2026-10-11, batch 3 (phone) — a pattern, and it is not a defect.** `pinned-facts`,
  `memory-as-of` and `between-us` all came back unreachable by Find (`Nothing matches that.`, or
  an unrelated match). Checking the source settled it: **all three are real menus** —
  `MenuCatalog.kt:100/101/107`, `brain.memory.profile`, `brain.memory.between-us`,
  `brain.memory.as-of` — and **Find only offers a row whose menu is *shown***. The `brain.memory.*`
  menus are hidden on this phone by **"Hide memory lists and chat history"**, which only the
  owner's fingerprint can change. The phone even says so in the Brain: **`Hidden. Tap Show and
  confirm it is you.`** So **five of the 45 — `pinned-facts`, `memory-as-of`, `between-us`,
  `memory-known`, `memory-tab` — are BLOCKED by one setting, not by five bugs.** That is the
  field test doing its job: "cannot be reached" and "is broken" are different answers.
- **2026-10-11, desktop quickbar, two more driven** — `watch-with-me` (**PASS**: the control
  toggled and reported `Off`, meaning a session was live and the click ended it; left **off**
  deliberately, since starting it again would begin screen watching) and `temporary-chat`
  (**PASS**: toggled off, noticed, toggled back on).
- **2026-10-11, batch 2 (phone)** — three more PASSes: `phone-notifications` (with its live
  "Notification access: not granted yet"), `captcha-handoff` (both choices read in full), and
  the `Smartwatch notifications` **row** confirmed real. Two PARTIALs where the feature has no
  screen of its own: `voice-check` (Find's only match is the `Voice` section) and `interrupt`
  (Find's only match is `Attention budget` — interrupting is a behaviour, not a screen).
- **2026-10-11, batch 2 bonus** — searching for "look at this" landed on the phone's
  **`PICTURE MODE`** screen, which reads in full: a slow CPU-side picture reader, keys/card
  numbers blacked out first, nothing saved, off by default, and its own honest line —
  **"Not measured yet: nobody knows how slow this is on your PC."** It also says it needs the
  *Looking at your screen* switch on the Security screen. Worth carrying into the matrix as a
  part of the screen/picture group.
- **2026-10-11, desktop quickbar** — the Jarvis bar (a second window also named `Jarvis`) exposes
  **`Watch with me`, `Temporary chat` and `Jarvis Live`**, so three more of the 45 are reachable
  on the desktop. **While testing `Temporary chat` I toggled it and it was ON — I turned the
  owner's setting off, noticed, cycled the bar open again and toggled it back: `toggled to On`.**
  Recorded because driving real controls can change real state, and that one did.
- **2026-10-11, batch 1 (phone)** — five PASSes: `phone-floating`, `phone-tiles`, `now`,
  `attention-budget`, `menu-visibility`. One FAIL: `between-us` is not findable. Every verdict is
  from the phone's own accessibility dump.
- **2026-10-11, desktop capability** — discovered that Windows UI Automation exposes the whole
  Tauri/WebView2 page (2,067 strings in the Settings window alone), which makes the desktop half
  testable without screenshots or vision. **On the way, verified the #262 Settings-freeze fix on
  the real app: clicking `Jarvis settings` opened `Jarvis Desktop — Settings` (2,222 elements) and
  the app went on answering in 0.2 s.** That is the fix the owner was blocked by, confirmed on
  0.2.140.
- **2026-10-11, already recorded before batch 1** — `what-asks-first` and `about` PASS;
  `faces` PARTIAL (no vision); `coming-up` BLOCKED (the jump defect, #294).
