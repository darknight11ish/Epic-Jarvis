# Field test top-up, second half: the seven drivable rows, driven (2026-10-12)

**This file does not rewrite anything.** `FIELD-TEST-2026-10-11-RESULTS.md` and
`FIELD-TEST-2026-10-12-TOPUP.md` stay exactly as their passes wrote them - including the eleven rows that
end "not driven in this pass". This is the **new verdict beside each id**, written the day the seven were
driven, so a reader can see what changed and when rather than a record that quietly improved its own
history.

**Where the eleven came from:** the top-up's section 6 named them UNTESTED. Seven of them are reachable
with the instruments that pass already used; **four need the owner himself**, and they stay UNTESTED
below with the reason stated in the feature list's own words.

**Instruments on 2026-10-12, second pass:** the phone `f0a5b32b` over adb (Find + `uiautomator`); the
desktop app running, read and driven over Windows UI Automation (its Settings window exposed **1,999
strings** this time - 2,067 the previous day, so the build differs and the number is stated as read);
the live backend on 4719 with the token read from its own store at run time. **No vision provider on this
machine**, so nothing below is from a picture of a screen.

---

## The seven, with the verdict this pass can stand behind

| id | feature | how it was reached | verdict | evidence, quoted as it was said |
|---|---|---|---|---|
| `settings-entry` | Settings itself | **driven** - the app's own gear, then the window read whole; the phone's Settings reached through Find in the same pass | **PASS** | `clicked 'Jarvis settings': invoked` -> `Jarvis Desktop — Settings` opened, class `Tauri Window`, **1,999 strings** read in order. The feature's own words say *"The list of every switch and card, in both apps. PC: the tray menu, Settings and help. Phone: Settings."* and *"Always reachable - it can never be hidden."* On the phone, Find landed on `Settings / ...` rows repeatedly (e.g. `Settings / Limits and how often Jarvis does things`, `Settings / Screen refresh rate`), so the phone's own Settings entry is real too |
| `start-jarvis` | Starting Jarvis for you | **read** - Settings, More options | **PARTIAL** | the row is real and reports live state: `Start Jarvis for you` (*"Off unless you turn it on. With it on, opening this app starts Jarvis too - unless Jarvis is already running, in which case this app uses that one ins..."*), and `Let Jarvis Desktop start and stop Jarvis` - *"With it on, opening this app starts Jarvis too. A Jarvis you started yourself is never taken over and never stopped."* - with its own live answer beside it: **`On. Jarvis Desktop started Jarvis and it has been running for 0s.`** The start/stop itself was not driven by this pass |
| `settings-file` | The settings file, the logs and starting with Windows | **read** - Settings, More options | **PARTIAL** | the folded card the feature names is on the page: `More options` - **`Letting this app start Jarvis, starting with Windows, and the log files.`** - which is the feature's own three parts, word for word. The log folder was not opened |
| `browser-engine` | A browser without a window | **read** - Settings, Browser without a window | **PARTIAL** | the row, the section and the live state all read: `Browser without a window` - *"Which browser Jarvis uses for plain reading."*; `BROWSER WITHOUT A WINDOW (OBSCURA)` - *"a browser Jarvis uses without opening a window"*; the switch `Let Jarvis use the windowless browser (Obscura)` with its own state **`Off. Jarvis uses the visible browser only.`** and **`Obscura is not installed on this PC yet.`** followed by `To install it, paste this one line into PowerShell (the Windows command window) on your PC:`. Turning it on raises one card (the feature's own `asks`) and the browser is not installed, so the reading path itself was not driven |
| `chat-thread` | The whole conversation, and carrying it on | **read** - the HUD, and Settings, A new conversation starts after | **PARTIAL** | the HUD really carries the thread's own section - its text reads `CONVERSATION` under `JARVIS HUD` - and the carrying-on rule is a real Settings row with its live value: `A NEW CONVERSATION STARTS AFTER` - *"The next message starts a new conversation after this long with nothing said. The old one stays in History, and Continue brings it back."* - set to **`30 minutes (default) What Jarvis has always done. The same words in both apps.`** The thread itself was empty (no conversation in progress), and the "Earlier chats" route lives in the Jarvis bar / the Brain window, which this harness cannot open (the record's tray dead end) |
| `news-and-page-watches` | News headlines, and pages that change | **driven on the phone** - Find, three terms | **PARTIAL** | **no row of its own on the phone**: Find -> `news` says **`Nothing matches that.`**; `watch` offers **3 matches**, the first `Brain / GitHub watchlist` (*"The repos Jarvis watches."*); `page changes` offers **2 matches**, `Settings / Browser without a window` and `When a captcha stops Jarvis`. The feature's own words say how it is really driven - *"Say 'add this feed:' and the address, or 'tell me when this page changes' and the address"* - and that each addition **raises one card showing the whole address**, which is the owner's to answer |
| `phone-limits` | What the phone deliberately does not do | **driven on the phone** - Find, two terms | **PARTIAL** | **the feature is a limit, not a screen, and its own words say so**: *"where: Nothing to press - this is a limit. asks: Nothing to ask."* On the phone, Find -> `deliberately` says **`Nothing matches that.`**, and `does not do` offers **4 matches**, none of them this feature (the first is `Settings / When the phone does not answer`). So the honest verdict is that the limit exists as a list while the phone offers no row to point at |

**One PASS, six PARTIAL, and no BLOCKED** - which is itself the finding: none of the seven was stopped by
hardware or by the owner; five are rows whose *behaviour* the harness cannot complete (a card, a route it
cannot open, a thread with nothing in it), and one - `news-and-page-watches` - is driven by a phrase that
raises a card.

## The four that need the owner, left exactly as UNTESTED

These stay UNTESTED, and the reason is the feature's own definition rather than this pass's excuse:

| id | feature | why it needs him |
|---|---|---|
| `spoken-style` | Short answers to spoken questions | *"Questions asked by voice get an answer written to be heard"* - it happens for anything **asked by voice**, and this machine has no one to speak the question |
| `voice-training` | Teach Jarvis your voice | *"Jarvis learns what you sound like, so it only listens to you"*; one approval card before it is learned, and *"The recordings are deleted either way."* **It has to be his voice** - a stand-in would test the stand-in, not the feature |
| `photo-reminder` | Photo to reminder | *"Show Jarvis a photo of a letter or an appointment card"* - it needs a photo of his, and his tap adds the reminder |
| `support` | Deal with customer support for me | *"Jarvis runs a customer-support chat on your behalf"* - a real company, on a real account, with one card before the chat and one per offer |

**Four of the eleven require the owner's own voice, a photo, or a real support conversation.** That is a
boundary of the method, not a gap in the work.

## What this pass did and did not do

- **Driven:** the desktop Settings window was opened with the app's own gear and read whole; the phone was
  driven only through Home, Find, and tapping a result row. **No setting was changed** on either app, and
  **no card was answered** - the three cards these features would raise (browser engine, a feed, a page
  watch) are the owner's.
- **Quoted raw:** every line above is what the app said, with the source named - the Settings window's own
  strings (1,999 this time), the HUD's own text, or the phone's Find output.
- **Not done:** the log folder was not opened; the thread was read empty; the four above stay UNTESTED.
- **Nothing private is written down:** no message text, no memory, no token, no address.
