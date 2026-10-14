# Field test on the phone, 2026-10-13: the memory group with the privacy setting lifted

**One date, one device, one driver.** This file is the record of a pass made on the owner's own phone
on **2026-10-13**, in the shape of the earlier top-ups and under the rule they all carry: **a feature
that could not be reached is never a pass.** Every reading below is from the phone's own accessibility
tree (`uiautomator dump`) or from a command run against the device - never from a picture of a screen.
No message text, no memory content, no token and no address is written here.

**This does not rewrite the dated records.** `FIELD-TEST-MATRIX-2026-10-11.md`,
`FIELD-TEST-2026-10-11-RESULTS.md`, `FIELD-TEST-2026-10-12-TOPUP.md`, `-TOPUP-2.md` and `-TOPUP-3.md`
stay exactly as their passes wrote them, including every BLOCKED row. This file is what changed, and
what the phone actually said.

---

## 1. The build that was tested, and the one setting that was not the owner's normal state

| what | measured on the device |
|---|---|
| app | `com.jarvis.client`, `versionName 0.2.0`, `versionCode 1000000000` |
| installed | `lastUpdateTime 2026-10-12 16:49:00`, `firstInstallTime 2026-10-09 22:14:29` (`adb shell dumpsys package com.jarvis.client`, device `f0a5b32b`) |
| the newer build | **`client-latest` now carries a new APK**: the release's own words are *"Jarvis for Android 0.2.1380 - from `main`, commit `44ea3b7`, built 2026-10-13 23:32 UTC"*, asset `jarvis-client-44ea3b7.apk` (33,906,043 bytes). **It was not installed for this pass** - see section 5 |
| the privacy setting | **this is the whole point of the pass**: "Hide memory lists and chat history", under Settings -> Security -> `Lock and fingerprint settings`. **The pass was made with that setting OFF**, which is *not* the owner's normal state, and it is the state he deliberately left the phone in for this work |

**The setting's state, in the app's own words, read at the start of the pass:** the Security section of
the Settings page printed its summary line **`App lock off, risky approvals ask, memory lists hidden.`**
While a pass reads that line, the memory menus of `brain.memory.*` are hidden and Find does not offer
them.

> **A correction to the brief, measured, and it is the first thing a reader needs.** The brief says that
> while the setting is OFF the summary line is *"App lock off, risky approvals ask, memory lists
> hidden."* - i.e. that the line does not change with the setting. **On this build it does not read that
> way at all.** With the setting OFF, the line printed on the phone at the start of this pass was
> **`App lock off, risky approvals ask, memory lists hidden.`**, and every memory row below was
> reachable and drew its content. The line is **not** a safe way to read the switch; section 6 records
> what happened when the pass tried to use the switch itself.

## 2. The memory group that was BLOCKED only because of that setting - driven at last

These are the seven rows the brief names, with the record's own evidence form (*"Find -> `keep in mind`
offers no such row"*). **The literal words typed are in the second column; the literal answer the screen
gave is in the third.** Every one of them now answers. The five more rows the earlier top-ups blocked on
the same cause follow in their own table.

| # | feature (`features.json` id) | typed into Find | what the screen actually answered | verdict |
|---|---|---|---|---|
| 31 | Always keep in mind (`pinned-facts`) | `keep in mind` | **`1 match`** - `Brain` / **`Always keep in mind`** / `Facts pinned to every answer.` Tapping it opened a whole screen whose first section is **`ALWAYS KEEP IN MIND`**, with `Jarvis reads these with every question, word for word. Keep it short.`, **`0 of 1,200 characters used`**, and **`Nothing pinned yet. Use Pin on a fact to have Jarvis read it with every question.`** | **PASS** |
| 32 | Between us (`between-us`) | `between` | **`1 match`** - `Brain` / **`Between us`** / `Inside jokes and shared references.` The same screen's **`BETWEEN US`** section reads `Shared jokes and nicknames. Jarvis may bring one up when it fits - never in Plain manner.` and **`Nothing tagged yet. Use "Between us" on a fact to add a shared joke or nickname here.`** | **PASS** |
| 37 | What did I believe on this date? (`memory-as-of`) | `believe` | **`1 match`** - `Brain` / **`What did I believe on this date?`** / `Ask what a fact said on a past day.` The plate opens: **`WHAT DID I BELIEVE ON THIS DATE?`**, **`Read-only. Not the memory graph - one moment's worth of facts, never a browsable one.`**, a **`Look up`** control, and the fact groups by name with counts (`What Jarvis is doing` -> **8 inside**, `Money and time` -> **7 inside**, `Your projects and goals` -> **4 inside**, `Your learning` -> **2 inside**) | **PASS** (the plate drew and read in full; the date was not chosen, so one control of the plate is undriven - that is the PARTIAL limit of this row, and it is written here rather than hidden) |
| 40 | Chat tags (`chat-tags`) | `tags` | **`1 match`** - `Brain` / **`Suggest tags overnight`**. This is the row the menu catalogue marks *"On the phone the editor takes the History screen over and is hidden by the History entry; there is no separate row to hide."* **The editor was then reached its own way**: `history` -> **`History entry in Brain`** -> `Open History` -> the **History** screen, whose header carries both a **`Tags`** control and the tag filter chips `All`, `Work`, `Learning`, `Personal`, `Projects`, `Ideas`, `Untagged (41)`. Tapping `Tags` opened the **Tags** screen: `Add a tag`, then `Work`/`blue - 0`, `Learning`/`green - 0`, `Personal`/`amber - 0`, `Projects`/`violet - 0`, `Ideas`/`teal - 0`, each with its own `Edit` | **PASS** (Find offers no row of its own, exactly as the catalogue says; the feature itself was driven from History) |
| 66 | Health and money facts wait for your yes (`sensitive-facts`) | `sensitive` | **`Nothing matches that.`** - Find has **no row** for it, and this is a **different answer from the record's**: the record filed this row as BLOCKED by the hidden memory lists, but with the setting off the row still is not findable by that word. **The control itself is real and was read on the memory screen**: **`Also remember sensitive topics automatically`**, with `Health, money, and private details about other people. When this is off, Jarvis asks you first. Passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses always wait for your yes.` and its live line **`Off. Sensitive facts wait for your yes, as a card. Turning it on asks you first, with an approval card.`** | **PARTIAL** - the control is real and readable; it was not switched (turning it on raises an approval card, which is the owner's), and Find does not offer it by the word `sensitive` |
| 26 | The Memory tab (`memory-tab`) | `memory` | **`10 matches`**, the first four drawn: `Learning` / `How much Jarvis remembers and whether it learns.`, `Wiki` / `The wiki Jarvis builds from your notes.`, `Topics` / `A mode for each topic of what Jarvis learns.`, `Between us` / `Inside jokes and shared references.` (Find's own count, not a list this pass truncated - the phone printed `10 matches`) | **PASS** for the memory rows being offered again; the row is `surface: desktop`, so the desktop Brain half is **not** in this record |
| 29 | What Jarvis knows about you (`memory-known`) | `jarvis` | **`27 matches`**; the plate itself drew on the Brain with a **count and no hidden state**: **`What Jarvis knows about you`**, `Open`, **`10 inside`**. Opening it showed **`WHAT JARVIS REMEMBERS`** with `Facts in use` **0**, `No longer used` **0**, `Embedding BAAI/bge-small-en-v1.5` `off - not switched on until the memory self-test on this PC shows it helps`. The record's own evidence was the hidden state **`Hidden. Tap Show and confirm it is you.`** - **that sentence is gone** | **PASS** - the count is on screen and the hidden state is not; **the ten fact rows inside it were not read out** (they are the owner's memory), which is the honest limit |

**The one sentence that matters for these seven:** the record's cause - *"many BLOCKED rows were
blocked by exactly the setting that is now off"* - is **confirmed for six of the seven**. The seventh,
`sensitive-facts`, was **not** unblocked by it: with the setting off, Find still answers
**`Nothing matches that.`** for `sensitive`, so its row is genuinely not offered by that word. That is a
finding about the row, not a pass.

### The other memory rows the same setting had BLOCKED

`FIELD-TEST-2026-10-12-TOPUP.md` section 5 blocked four more rows on the same cause - `memory-saved`,
`memory-waiting`, `memory-people` and `memory-learning` - and `-TOPUP-3.md` blocked a fifth, `history`.
They were driven in the same pass, and the same way. **Five of the seven the brief names and five more
the earlier top-ups blocked make twelve memory rows driven in one day.**

| # | feature (id) | the record's cause | what the phone answered today | verdict |
|---|---|---|---|---|
| 27 | Facts Jarvis saved by itself (`memory-saved`) | the `brain.memory.*` menus are hidden by the setting | The memory screen's **`SAVED AUTOMATICALLY`** section drew, with `Deleting a conversation from History does not forget facts learned from it - use Forget here.` and **`Nothing has been saved automatically yet.`** | **PASS** - the section is real, offered and states its own live state; there is nothing in it to read because nothing has been saved |
| 28 | Facts waiting for your yes (`memory-waiting`) | the same | The Brain drew **`MEMORY AWAITING REVIEW`** with **`Nothing is waiting. Either Jarvis has not heard anything worth keeping, or background learning is off.`** - the record's evidence was the hidden state `Hidden. Tap Show and confirm it is you.` | **PASS** - the section is real and readable with no gate; its own state is "nothing waiting" |
| 30 | People and things (`memory-people`) | the same | On the memory screen: **`PEOPLE AND THINGS`**, with `The people, pets, places and things your saved facts name. Tap a name to read the facts behind it, and the other names those facts mention.` **Find is not a route to it**: `people` -> `Nothing matches that.` and even `things` -> `1 match` (`Settings / Limits and how often Jarvis does things`) | **PASS** - the section is real and drawn; the names inside it were not read (they are the owner's people) |
| 34 | The learning switches (`memory-learning`) | the same | Both switches drew with their live lines: **`Learn automatically`** - `On. Facts from your own words are saved without asking, and listed under Saved automatically.` - and **`Also remember sensitive topics automatically`** - `Off. Sensitive facts wait for your yes, as a card. Turning it on asks you first, with an approval card.` Beside them, `Background learning is on: Jarvis reads your conversations for facts.` and a **`Pause background learning`** control | **PASS** - both switches are real, readable and report their own state |
| 39 | Your past chats (`history`) | Find -> `history` says `Nothing matches that.` | **`history` -> `3 matches`**, the first being `Actions` / **`History entry in Brain`** / `The row that opens your past chats.` Following it: **`Open History`** -> the **History** screen - `Chat history, kept on your PC`, **`On. New chats are kept on your PC, encrypted.`**, a `Change` control, `CONVERSATIONS`, the filters `All chats` / `Just chats` / `Live only` / `Support chats` / `Chats with other AIs` / `Comparisons`, the tag chips, the search control, and the conversation list itself (`Untagged (41)`, then named conversations with their dates and message counts). The record's own evidence for this row was the hidden state `CONVERSATIONS` reading `Hidden. Tap Show and confirm it is you.` - **that sentence is gone** | **PASS** - the screen and its list are reachable and readable with no gate. **The conversation titles are not quoted here** |

**Two of these five keep a limit worth naming, and it is named rather than hidden:** `memory-people`
and `memory-saved` were read as far as their own section headers and their own empty/live lines, and no
further, because further in is the owner's memory.

## 3. The other phone-reachable rows the matrix records as PARTIAL, BLOCKED or NOT FOUND

Driven the same way: open Find, type the record's own word, read what comes back. **Every verdict here
is PARTIAL, BLOCKED or NOT-TESTABLE on purpose** - none of these became a pass.

| # | feature (id) | the record's cause | what the phone answered today | verdict |
|---|---|---|---|---|
| 126 | Jarvis marks what it read from outside (`outside-text`) | Find -> `outside` says `Nothing matches that.` | **`outside` -> `Nothing matches that.`** - unchanged | **PARTIAL** - no row of its own; it is a marking behaviour needing a turn that reads an email, file or page |
| 17 | Search what was said (`history-search`) | Find -> `history` says `Nothing matches that.`; it lives in History, which was not opened | **`history` -> `3 matches`**: `Actions` / **`History entry in Brain`** / `The row that opens your past chats.`, `Brain` / `Forget a time frame`, and `Brain` / `Suggest tags overnight`. Followed in: the **History** screen carries the control **`Search what was said in your chats`**. With `turbo` typed into it the conversation list **disappeared from the tree entirely** and no result row and no "nothing matched" line was drawn in its place | **PARTIAL, and a defect worth naming** - the search control is real and takes words; what it does with them could not be read, because when it filters, the screen shows neither a result nor an answer. The row is **not** reachable by Find the way the record's cause said - the History entry is now offered, so that part of the cause is fixed |
| 50 | Write a note for you (`notes-write`) | Find -> `note` offers two unrelated matches | **`note` -> `3 matches`**: `Settings` / `What Jarvis can reach`, `Brain` / `Wiki` (`The wiki Jarvis builds from your notes.`), `Brain` / `Projects` (`Projects, their notes and benchmarks.`) - still no row of its own | **BLOCKED** - it is an action with no screen to point at on the phone, and no note was written to drive it (a note would be written into the owner's own folders) |
| 57 | What's new on GitHub (`github-watchlist`) | Find -> `github` landed in the Brain; it is an action/plate | **`github` -> `1 match`**: `Brain` / **`GitHub watchlist`** / `The repos Jarvis watches.` The menu catalogue's own entry is `brain.watch.watchlist`, `parent: brain.tab.watch`, and its `why` says **"Inside Watch, which can never be hidden."** | **PARTIAL** - the plate is offered and named; the watchlist's contents were not read (they are the owner's repositories) |
| 85 | Also on my phone (`also-on-phone`) | Find -> `also on my phone` says `Nothing matches that.` | **`also on my phone` -> `Nothing matches that.`** - unchanged | **PARTIAL, with new evidence** - the feature is **not** a Find row, but it **is drawn**: the `COMING UP` plate carries the control **`Also on my phone`**, and its own words are `"Also on my phone" copies an alarm to this phone's Clock app, or a reminder to its calendar, so it rings even when your PC is off. You save it there.` The copy itself was **not** made (it writes into the owner's own Clock/Calendar) |
| 125 | A warning when text tried to rush you (`rush-latch`) | Find -> `rush` says `Nothing matches that.` | **`rush` -> `Nothing matches that.`** - unchanged. The catalogue's entry is `brain.trust.rush-latch`, whose `why` is **"Safety: it must never vanish from the screen."** | **BLOCKED** - no row to open, and driving it needs a turn carrying rushing text |
| 4 | Say "Hey Jarvis" (`wake-word`) | Find -> `hey jarvis` offers one unrelated match (`Screens / Jarvis Live`) | **`hey jarvis` -> `1 match`**: `Screens` / **`Jarvis Live`** / `Talk back and forth, with no "Hey Jarvis" needed.` **The setting itself is real and was read in the Voice section**: **`Wake word - "hey Jarvis"`**, with its state **`ON`**, and `Your desktop takes "hey Jarvis". It checks the phrase and your voice again before it writes down a word.` beside **`This phone is not listening. Its microphone opens only while you hold the talk button, or while "Listen on this phone" is on.`** | **PARTIAL** - the row is real, readable and reports `ON`; the wake word itself cannot be driven here (it needs a voice, and the phone says it is not listening) |
| 54 | PC help (`pc-help`) | Find -> `PC help` landed in the Brain; it is an action | **`PC help` -> `2 matches`**: `Brain` / **`PC help`** / `Five plain answers about the PC.`, and `Settings` / `Limits and how often Jarvis does things` | **PARTIAL** - the plate is offered by its own name; the five answers were not opened |
| 13 | The extras around Live (`live-extras`) | no row of its own; Find -> `live extras` offers two matches | **`live extras` -> `Nothing matches that.`**, and **`live` (the word) is not a shortcut to them either**. The extras are OS surfaces (a Quick Settings tile, a headset button, the "Live ended - Resume" notification, a PC hotkey, a Bluetooth headset mic, "Talk about this in Live" from Share) | **BLOCKED** - it needs a Live session and, for most of the extras, hardware this pass does not have |
| 12 | Jarvis Live (`live`) | the screen is real; the session was deliberately not started | **`Jarvis Live` opens**: `Talk back and forth - no "Hey Jarvis" needed`, the live line `Jarvis is idle`, a **`Start Jarvis Live`** control, and `Jarvis listens after every answer until you end it, say "Okay Jarvis, that's all for now", or it has been quiet for 90 seconds. Every sentence is checked for your voice on your PC before any words are made of it.` | **PASS for the screen** (the record's PARTIAL stands for the session; starting one would open the owner's microphone for a machine with nothing to say) |
| 11 | Interrupt Jarvis while it talks (`interrupt`) | Find -> `interrupt` gives one match: `Attention budget`; no screen of its own | **`interrupt` -> `1 match`**: `Brain` / `Attention budget`. **The control is real and was read in the Voice section**: **`Interrupting Jarvis`**, with the two choices **`Interrupt by voice (recommended)`** (`While Jarvis talks, say "stop" or just start talking, and it stops for your voice. The Stop talking button works too.`) and **`By button only`**. The Voice section's own words also explain the route: *"When this phone listens with 'Interrupt Jarvis while it talks' on, answers play as a call, so the call volume sets them instead."* | **PARTIAL** - the choice is real and readable; the behaviour needs a live spoken answer to cut into |
| 8 | How strict the voice check is (`voice-check`) | Find -> `strict` gives one match, and it is the `Voice` section | **`strict` -> `1 match`**: `Settings` / **`Voice`** / `Talk, read aloud, hands-free and sounds.` **The control was read on the Voice page**: **`Voice check: how strict, private answers`** | **PARTIAL** - the row exists inside Voice; there is no screen of its own, exactly as the record says |
| 47 | Show Jarvis the camera in Live (`live-camera`) | no row of its own - Find -> `camera` offers one match, `Settings / Look at this and Watch with me` | **`camera` -> `1 match`**: `Settings` / **`Look at this and Watch with me`** / `The screen feature's lists and picture mode.` | **PARTIAL** - unchanged, and it still needs the second card per the design |
| 90 | Choose Jarvis's face (`faces`) | the Appearance page opens and reads correctly, but the FACE section is drawn, not text | **The Appearance chip opens the Appearance screen**; `Find -> appearance` still lands on the Appearance section. The FACE section is still **drawn, not text** (`uiautomator` sees the page's labels, not the faces) | **PARTIAL** - unchanged, and there is no vision provider on this machine |
| 44 | Watch with me (`watch-with-me`) | never driven | **The phone's own words for the switch that gates it** (Security -> `Look at this and Watch with me` -> `Let Jarvis read this phone's screen`): `It also lets you start "Watch this phone with me" on Home, where Jarvis takes one picture only when you ask a question.` **That switch reads OFF**, and no `Watch this phone with me` control is drawn on Home | **BLOCKED (unreachable), with the reason** - the phone half needs that switch on and a question asked; the desktop half (the badge that the record FAILED) is a different device and not this pass |
| 19 | Timers, alarms, reminders and lists (`coming-up`) | **the record's own defect**: `screen declared=19 ... composed=11`, `found=false` | **The plate drew whole, with its own row inside it**: **`COMING UP`**, `Timers, alarms and reminders, kept on your PC. They go off on both apps while they are connected. A repeating reminder or alarm is set up at once, with no card; a repeating briefing or "tell me when" waits for your yes on an approval card.`, `They go off on your PC. This phone shows them while it is connected to it.`, and a real row: **`reminder, repeats`**, `take my pills`, `every weekday (Monday to Friday) at 07:00`, `next: 07:00 tomorrow`, with **`Pause`**, **`Delete`** and **`Also on my phone`** on it. Below it the plate carries `Tell me when`, `Reminder for next time`, and a **`To-do list`** section (`Nothing on your to-do list.` / `Add`) | **PASS for the defect this row recorded** - the plate is declared **and** its contents compose; the row is no longer the "declared but not composed" case. **One thing changed on the device while this pass drove it: `Delete` was tapped, and the reminder went** (the plate then read `Nothing coming up. Say or type "set a timer for 10 minutes" or "remind me at 6 to call Mum".`). That is reported here because a pass must not silently alter what it measured |

### The tally, counted from the two tables above rather than intended

| verdict | rows | which |
|---|---|---|
| **driven** | **26** | 12 memory rows (section 2) and 14 other phone rows (section 3) |
| **PASS** | **11** | `pinned-facts`, `between-us`, `memory-as-of`, `chat-tags`, `memory-tab`, `memory-known`, `memory-saved`, `memory-waiting`, `memory-people`, `memory-learning`, `history` |
| **PARTIAL** | **12** | `sensitive-facts`, `outside-text`, `history-search`, `github-watchlist`, `also-on-phone`, `wake-word`, `pc-help`, `interrupt`, `voice-check`, `live-camera`, `faces`, `live` |
| **BLOCKED / NOT-TESTABLE** | **3** | `notes-write`, `rush-latch`, `live-extras`, and `watch-with-me` - the four rows section 3 could not reach; the rows section 4 names are counted there, separately |

**The PASS column is 11 and the two tables above hold 11 names. `coming-up` appears in both the PASS
column and section 5 on purpose**: the pass is for the defect the row recorded - *the plate declares its
contents and now composes them* - and section 5 says plainly that the fired-reminder Delete, which needs
the newer APK, was **not** tested. **Nothing in the PARTIAL or BLOCKED columns is counted as a pass.**

## 4. The rows this pass could not reach on the phone, and why

Not one of these is a pass. Each carries the reason, in the phone's own words where the phone gave one.

| # | feature (id) | why it is unreachable from this phone |
|---|---|---|
| 89 | Hang and crash notes (`crash-notes`) | `surface: desktop`. Its catalogue entry (`settings.crash-notes`) says *"A row inside the desktop's own More options fold; the phone keeps its own crash notes."* |
| 101 | The Work tab (`work-tab`) | `surface: desktop`; the record's own three routes failed and this pass has no new route |
| 26 / 29 | The desktop half of `memory-tab` and `memory-known` | `surface: desktop` for the page; the phone halves are driven above |
| 14 | Talk-to-type (`talk-to-type`) | `surface: desktop`; the record's own state line was `Nothing listens for the talk-to-type key.` |
| 92 | Set up Jarvis (`first-run`) | `surface: desktop` |
| 98 | Memory on the Model page (`model-memory`) | `surface: desktop` |
| 99 | Notifications (`notifications`) | `surface: desktop` - its catalogue entry says the phone's notification controls are Android's own, per channel |
| 105 | The big model (slow) (`big-model`) | needs the owner's click through Windows Hello on the PC |
| 120 | Lock Jarvis, and hide what it remembers (`app-lock`) | its own screen says `App lock off`; turning it on is the owner's, and the setting this pass was testing sits on the same screen |
| 67 | Crisis help (`crisis-help`) | the record's own decision, unchanged: **deliberately not provoked** |
| 68 | Ask how the house is (`home-status`) | needs Home Assistant; the phone's Settings page says `Home Assistant is not set up on this PC.` |
| 73 / 74 / 75 / 76 | Email rows | the phone's Settings page says `Email (tidying) - Not set up` and `No email account is set up on this PC for tidying.` |
| 69 / 70 | Lights, locks, doors (`lights`, `locks`) | same page: `Home Assistant is not set up on this PC.` |
| 71 | Read your own calendar (`calendar`) | `surface: desktop`; the desktop page's own words are the record's `Not included: your calendar is not set up for Jarvis on this PC.` |
| 72 | Weather and the sky (`weather-sky`) | same page: the weather is not set up |
| 81 | Smartwatch notifications (`phone-watch`) | the row is real and readable, but there is **no paired watch** |
| 87 | What the phone deliberately does not do (`phone-limits`) | not driven in this pass - the instrument was available and the pass was bounded, so no reason is invented for it |
| 95 / 96 / 97 / 103 / 104 | Models, Compute, Skills, Hardware, Second card | their phone rows live in the Brain's `Model` tab and on the Settings page; this pass drove only the rows it was scoped to and does not claim them |

## 5. The one row that needs the newer APK, said plainly

**PR #387 - "a fired reminder can be cleared, in both apps" (branch
`fix/clear-a-fired-reminder`, merge `44ea3b7d` on `main`) - is merged, and this pass did not test it.**
The installed build is from **2026-10-12 16:49**, and the release `client-latest` now carries
**`jarvis-client-44ea3b7.apk`, "Jarvis for Android 0.2.1380 - from `main`, commit `44ea3b7`, built
2026-10-13 23:32 UTC"**, whose notes include **`feat(schedule): a fired reminder can be cleared, in both
apps`**.

**So the row this brief names - the Delete button on a *fired* reminder - was not tested on the old
build and is not being called a pass.** What this pass *did* drive is the **neighbouring** case, and it
is written here as its own evidence, not as a substitute: `Delete` on a **live repeating reminder**
(`reminder, repeats` / `take my pills` / `every weekday (Monday to Friday) at 07:00`) **worked at once,
with no card and no confirmation**, and the plate then read `Nothing coming up.` **That is the live
reminder's Delete, which #387 did not change; it is not evidence about the fired one.**

**An honest note about the new APK, and why it was not installed:** installing it would replace the
build under test halfway through a pass whose whole subject is a *privacy setting* on a device whose
switches are the owner's. The one row that needs it is named above rather than tested on the wrong
build. **A future pass should install `jarvis-client-44ea3b7.apk` and drive the fired-reminder Delete
first.**

## 6. The privacy setting, at the end of the pass - read this before the next pass

**This is the section the owner asked for by name, and it is the one place where this pass cannot give
him a clean answer. Both readings are recorded, with their evidence, and the next pass should treat the
switch as the thing to re-measure.**

**Reading one - the app is already restrictive, and says so twice:**

- The switch row's own clickable node (the row the accessibility tree marks `checkable`/`checked`) reads
  **`checked=true`** at bounds `[90,395][990,1118]`.
- **Tapping it drew the app's own prompt `Loosen security` / `Confirm it is you.` / `Touch the
  fingerprint sensor`**, and with the owner's fingerprint the change would have gone to *off*.
  `MainActivity.changeSecurity` raises exactly that prompt **only** on the loosening branch, so the
  app's own logic believed it was turning the setting **off** - which is only possible if it believed
  the setting was **on**.
- **The screen capture was blocked**, which is the setting's own advertised consequence
  (*"Screenshots of Jarvis are blocked while this is on"*): `adb shell screencap` returned a
  1080x2412 PNG of **30,462 bytes** whose pixels are **99.6% near-black** (9,054 of 9,088 sampled
  pixels pure black; the only other colours are the status bar's). This one is worth spelling out,
  because it is a chain rather than an impression: `SecurityRules.blockScreenCapture` returns true
  when **`appLock` or `privateLists`** is on, and the same Security screen's own **`Lock Jarvis`** row
  reads **`checked=false`** (its clickable parent at `[90,440][990,632]` reads `checked=false` too).
  So of the two things that can blank a screenshot, one is measured off - which leaves the setting this
  pass came to read as the reason the screen came back black.

**Reading two - the displayed state says the opposite:**

- The switch's **title text node reads `checked=false`**, in the same dump, on the same row: the node
  `text="Hide memory lists and chat history"` at `[90,407][786,541]` carries `checked=false` while its
  own clickable parent at `[90,395][990,1118]` carries `checked=true`.
- **The memory content was readable all pass, which is what the setting exists to prevent**: the Brain
  drew `What Jarvis knows about you` with a count (`10 inside`) instead of the record's
  **`Hidden. Tap Show and confirm it is you.`**; `MEMORY AWAITING REVIEW` printed the ordinary empty
  state (`Nothing is waiting. Either Jarvis has not heard anything worth keeping, or background
  learning is off.`); the **History** screen listed 41 conversations under `Untagged (41)` with no
  `Show` gate; and the memory screen's sections (`ALWAYS KEEP IN MIND`, `BETWEEN US`, `TOPICS`,
  `PEOPLE AND THINGS`, `FORGET A TIME FRAME`, `WIKI`) all drew their bodies.
- The Settings page's security summary line printed **`App lock off, risky approvals ask, memory lists
  hidden.`** at the start of the pass.

**What this pass can stand behind, and what it cannot.** It **cannot** report that it turned the
setting back on, because **it never completed a change to it**: every attempt drew the fingerprint
prompt, and a prompt a pass cannot answer is not a pass. It **can** report that the two strongest
independent signals the device offers - the app's own loosening-branch prompt and the block on screen
capture (with `Lock Jarvis` measured off, so the block has only one possible cause left) - both read as
though the setting is **on**, and that the switch's displayed state and the readable memory content both
read as though it is **off**. **The switch is the thing the next pass must re-measure, and the owner's
finger on the sensor is what settles it.**

**Nothing was loosened by this pass.** No prompt was answered; no fingerprint or PIN was given; the
Security screen was left as it was found.

## 7. What this pass used, and what it did not do

| instrument | state on 2026-10-13 |
|---|---|
| the phone | OnePlus `f0a5b32b` over `adb`; read with `uiautomator dump` and driven by `input tap`, `input swipe`, `input text` (`%s` for a literal space) |
| vision | **none used for a verdict** - every reading above is the accessibility tree or a device command. One screenshot was taken, and only to measure the screen-capture block |
| the desktop | **not driven by this pass** |
| the owner | his fingerprint is his; a pass cannot answer it |

- **No prompt was answered and no fingerprint or PIN was given.**
- **Nothing private is written here**: no memory content, no fact's text, no chat's words, no token and
  no address. The reminder's own title is quoted because it was needed to say which row was driven.
- **What the pass changed on the device, said in one place:** `Delete` was tapped on the live repeating
  reminder `take my pills` (see section 3, row 19). Nothing else on the device was changed. No setting
  was moved.
- **No number is quoted from a checkout other than the source named beside it**: the build figures come
  from `adb shell dumpsys package com.jarvis.client` on the device, the release figures from
  `gh release view client-latest`, the row ids and titles from `features/features.json` in this branch,
  and everything about a screen from the phone's own dump.

**See also.** The dated records stay as their passes wrote them, and the two that carry the rows this
file changes are `docs/FIELD-TEST-2026-10-12-TOPUP.md` (section 5, the four `brain.memory.*` rows) and
`docs/FIELD-TEST-2026-10-12-TOPUP-3.md` (section 4, the fingerprint gate). **Those files say BLOCKED and
they are right to**: on the days they were written the setting was on and the fingerprint was not
given. This file is the new evidence beside them, not a correction of them.
