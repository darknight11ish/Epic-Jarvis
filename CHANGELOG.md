# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **The core of the chatbot driver - not usable yet.** The part of Jarvis
  that will hold a conversation with an AI chatbot for you (Gemini first)
  is written and tested on the PC side: one approval card per
  conversation, a check before every message so nothing private leaves,
  and stops at any captcha or sign-in page. There is no button for it in
  either app yet, and the Gemini part is not built.
- **Fixed: marking a crisis answer "wrong" counted toward "suggest the
  bigger model".** Crisis messages are never learned from and never
  counted; the thumbs-down on a crisis answer was the one place that still
  counted. It no longer does. A thumbs-down on any other answer counts as
  before.
- **Fixed (phone): "Use" on a model that cannot chat.** Brain › Model on the
  phone offered "Use" on memory-search models such as nomic-embed-text,
  which would leave Jarvis unable to answer. Like the desktop, their row now
  has no "Use" and says "for memory search only - it cannot chat". Both
  apps follow one shared table of cases, so they cannot drift apart.
- **New (phone): reconnects as soon as the network changes.** Walking out
  of Wi-Fi, or switching Tailscale on, used to leave the phone on a dead
  connection for up to about a minute and a half. Now it reconnects within
  a couple of seconds. Approving still waits until the link is trusted.
- **New (phone): "Tailscale (or Meshnet) is off on this phone".** When the
  link is down and the phone has no VPN running at all, Home and Checks
  say so under the link.
- **New (phone): Show token on the pairing screen.** The 43-character token no
  longer has to be typed blind. It starts hidden, is never saved anywhere
  new, and screenshots and screen recording are blocked while it is shown.
- **New (phone): "Background restart" is offered once after pairing.** A
  line on Home, in the same words as the Checks card, with "Keep link
  alive" and "Not now". It never comes back after either.
- **New (PC): the live check asks "Can your phone reach Jarvis?"**
  (`selftest.py --preflight`): is a phone address set, is it a Tailscale or
  Meshnet one, is Tailscale or Meshnet on this PC, is Jarvis listening
  there, and is there a Windows Firewall rule - each with the one line or
  the one setting that fixes it.
- **Docs: a Quick start at the top of `docs/INSTALL.md`** - the shortest
  way to a first typed chat, with the desktop app starting Jarvis, then
  pairing the phone.
- **Fixed (phone): "open help", "connection", "the morning briefing",
  "about" and "Jarvis's voices" opened Settings at the top.** Each now opens
  the phone's own place for it - Help, Checks, Brain or "Jarvis's voice" -
  and scrolls to it. A setting that only the PC app has (keyboard shortcuts,
  accounts and a few more) now says so in one line instead.
- **Fixed (phone): "Catching up…" explained properly.** An approval card
  said "Not connected to the desktop" even while the phone was connected and
  only catching up. It now says Jarvis is catching up with your PC and the
  decision waits until then. Checks calls this state "Catching up…" like
  Home (it said "Stale"), Home shows Retry next to it, and coming back to the
  app reconnects on its own. Approving still waits until the link is
  trusted again.
- **Fixed (phone): the "Brief me now" and "What did I miss?" app-icon
  shortcuts** opened Brain at the top. Each now asks its question on Home,
  as if you had typed it.
- **Fixed (phone): an answer made without the AI model** said "answered on
  this PC" on the phone. It now says "on your PC".
- **Answers from web search and home status are read aloud again when you
  ask by voice.** Before, any answer where Jarvis used a tool was kept on
  screen ("It's on your screen."), so a spoken question answered from the
  web was never spoken. Now only web search and home status (which is
  where the weather comes from) are read aloud. Email, calendar, notes,
  files, memory and any other tool still keep the answer on screen, and so
  does Jarvis not being sure which tool ran. Both apps follow one shared
  table of cases, so they cannot drift apart.
- **Fixed: one "Hey Jarvis" heard by both the phone and the PC.** Both
  used to answer, so you got two answers - and a timer or "next song" could
  happen twice. Or, after a plain "Hey Jarvis.", the second device used up
  the listening moment and your real question was thrown away. Now only the
  first copy is answered, the other device stays quiet, and each device
  listens for its own follow-up question. Your voice is still checked
  before any words are written down.
- **Fixed (desktop): Forget's "when did this stop being true?" box.** "Sept
  20" was saved as the year 2001; now a date with no year means the most
  recent one that has passed, a date in the future is refused, and a date it
  cannot read asks again instead of quietly dropping the Forget you said yes
  to.
- **Fixed (desktop): "Use" on a model that cannot chat.** Memory-search
  models such as nomic-embed-text say "for memory search only" instead.
- **Fixed (desktop): raw underscores in answers** - `_words_` now show in
  italics.
- **Fixed (desktop): putting one of two approval cards aside hid both.** The
  next card now shows, and the count of waiting cards is right.
- **Clearer (desktop): Erase's second question** says what OK and Cancel
  each do. Two small wording slips fixed in Hardware and Voices.
- **Fixed: typing the phone's pairing key exactly as the PC shows it.** The
  PC shows the key in groups of four with spaces, to make it easier to read.
  The phone kept those spaces, so the key was refused. The phone now drops
  them as you type, and the PC says to leave them out.
- **Fixed: "Tell me when this page changes" alerting when nothing visible
  changed.** It compared the whole page, including hidden codes that change
  on every visit. It now compares only the words you can see. Watches set up
  before this record the new kind once, quietly, instead of alerting.
- **Fixed: "Start with Windows" said on when Task Manager had it off.**
  Settings now reads Task Manager's Startup switch too, and turning it on in
  Jarvis turns that switch back on.
- **Clearer message** when the patch script is pointed at the wrong folder:
  it no longer sends you looking for "OpenJarvis", an unrelated project.

## 0.2.0 - 26 September 2026

The first numbered version. It gathers the work of the last few days.

**New things Jarvis can do**

- **Timers, alarms, reminders and to-do lists**, set by saying or typing
  them, answered without the AI model so they work even when it is busy or
  asleep. Plain repeating reminders and alarms need no approval card.
  "What did I miss?" sums up what went off while you were away.
- **Morning briefing**: today's calendar, new emails (how many, and from
  whom - or only how many, if you prefer), and what is coming up.
- **"Tell me when ..."**: an email from a named sender, or a device at home
  changing (the washing machine finishing). One approval card to set it up;
  a match only notifies you - urgent ones keep ringing on the phone until
  you look.
- **"Folders Jarvis may look in"**: add a folder on the PC (one approval
  card) and ask about the files in it - find them by name, search your notes,
  read PDF, Word, Excel and PowerPoint files a part at a time. "Bring in a
  Notion export" unzips your Notion export into one of those folders. What
  Jarvis reads there is never saved as a fact about you.
- **Instant "tell me when" for email**, and **"tell me if Alex hasn't
  replied by Friday"**.
- **Sending email**: one approval card per email, showing the exact
  recipients, subject and whole text. Never an "always allow".
- **Web search** with five providers to choose from (SearXNG on your own PC
  by default, DuckDuckGo, Exa, Tavily, Brave).
- **Google Calendar**, read-only, through its private link, set on the PC.
- **Focus sessions** on the PC: a timer plus Quiet, a spoken nudge when a
  distraction comes to the front, and a report at the end. Nothing leaves
  the PC, and what was on screen is never stored.
- **Stop everything**: Alt+Shift+X on the desktop, or the button on the
  phone, halts whatever Jarvis is doing at once.
- **A live check of the whole setup** (`selftest.py --preflight`): every
  real connection tested end to end, "N pass, N fail, N warn".
- **"What asks first"**, a page in both apps listing every action and
  whether it asks you, with switches to make things stricter.
- **Lights, plugs and fans without a card** - a setting, off by default.
  Locks, doors, alarms and covers always ask.
- **Memory**: Jarvis learns facts from your own words automatically, lists
  each one with Forget and "Erase the words", and still asks about
  sensitive topics. Chat history is kept on the PC, encrypted, with a switch
  to turn it off. "Who is my sister?" now works.
- **Voice**: "Hey Jarvis" on the PC and the phone, spoken-style answers that
  start at the first comma, interrupting by saying "stop", and a switch for
  the "I heard you" sound (off by default).
- **Warm or plain manner**, a setting in both apps.

**Safer**

- Both apps accept a Jarvis address on your own networks only (this PC, the
  home network, Tailscale, NordVPN Meshnet). A public tunnel is refused.
- The PC itself asks Windows Hello before a risky approval from the PC, and
  a risky approval needs a screen lock on the phone or Windows Hello on the
  PC.
- Plain `http://` to Home Assistant or the calendar only inside your own
  networks.
- Writing notes after Jarvis has read outside text (an email, a web page)
  asks first.
- App lock hides the approval widget's details on the PC, and blocks
  screenshots on the phone.
- Reading email now checks the mail server's certificate, as sending
  always did (it encrypted, but to whoever answered).

**Fixed**

- "What did I miss?" no longer lists every routine "tell me when" look as
  something that went off.
- A "tell me when" whose end date passed while the PC was asleep (or while
  it was paused) now simply ends, instead of looking one more time.
- On the two days a year the clocks change, the briefing's calendar covers
  the whole day, midnight to midnight.
- The "tell me when" approval card no longer ends by saying it sends
  nothing anywhere, which contradicted its own "How" line.
- Many smaller fixes from the bug audits of 19, 24 and 26 September
  (`docs/BUG-AUDIT-2026-09-26-*.md`).

**Packaging**

- One version number (0.2.0) for the desktop app, the phone app and the
  backend. Both About boxes show it, the maker (darknight11ish), the licence
  and a way to read the third-party notices.
- Complete third-party notices for the desktop (`THIRD-PARTY-NOTICES.txt`,
  regenerated by `tools/gen_notices.py`) and a new list inside the phone app.
- Phone and desktop downloads are published only from `main` and the
  working branch; shorter, plainer release notes with a checksum.
