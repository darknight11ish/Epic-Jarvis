# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **A red panda face** - the first animal among Jarvis's faces, on the
  desktop and the phone. It sleeps when Jarvis is on standby, perks its ears
  and tilts its head when listening, gazes into a glowing orb when thinking,
  talks with Jarvis's voice, waves when an approval is waiting, and scratches
  its head at an error. The orb is your colour for each state. Drawn in 3D
  by the graphics card with no model file; see `docs/CRITTERS.md`.
- **A pygmy owl and a sea otter** join the panda, on both apps. The owl
  perches on a branch, turns its head to follow the room and waves a wing
  when something is waiting on you; the otter floats on its back in a
  little pool, taps a glowing pebble while it thinks and covers its eyes
  with its paws to sleep.
- **Animal faces tidied after their audit:** no more see-through specks
  along the otter's outline against its pool; the owl's thinking orb now
  circles clear of its head, and its glow no longer shows through the face;
  no starburst of streaks on the owl's crown seen from above; the panda's
  tail no longer shades itself with a false shadow band.
- **The animals' mouths follow Jarvis's real voice.** Each spoken answer is
  read up front into a mouth track - how open, how wide ("ee"), how round
  ("oo"), shut in pauses and on m/b/p - and played in step with the sound
  you actually hear, on the PC (every window that shows a face) and the
  phone. When Jarvis answers without speaking (typed, Quiet mode, kept on
  screen), the animals keep their mouths shut. See `docs/LIPSYNC.md`.
- **Voice follows the face.** With the red panda, owl or otter showing,
  Jarvis's built-in voice becomes that animal's - its own voice, pace and a
  slightly higher pitch. A switch in both apps, on to start, right under
  "Jarvis's built-in voice"; it never asks first. A voice you recorded still
  wins.

**New: watches**

- **"Tell me when a search shows something new."** Jarvis runs your search
  once a day (every 6 hours at most) through the search service you chose -
  never another one - and tells you when new results appear.
- **"Tell me when the price on <address> drops below X."** The price is read
  by plain code, not the AI, and shown under the watch so you can check it
  picked the right number. Jarvis never buys anything.
- **GitHub watches:** "tell me when CI fails (or finishes) on owner/repo" and
  "tell me when PR #12 on owner/repo merges". Read-only, using the GitHub key
  you already have. One line to add on the PC: `github_read = "auto"` under
  `[autonomy.tiers]` in `jarvis-framework.toml` (the refusal message names it).
- **A watch that stops working tells you once** (at most every 12 hours)
  instead of failing silently, and clears by itself when it works again.
- **Page watches ignore hidden page bytes**, so a page nobody changed no
  longer counts as changed (a fix ported from another branch).

**New: Brain upgrades**

- **Search what was said in your old chats**, in both apps' History - not
  just titles. Each match shows the words in place, and "Find in this chat"
  steps through them. The search runs on your PC; nothing is saved and
  nothing goes to the AI.
- **"History of this fact"** on the PC's Memory tab: every earlier wording,
  with the changed words marked. Erased words never come back.
- **Galaxy now shows the people and things Jarvis knows about.** Click a name
  to open "About <name>".
- **Fixed: Galaxy could show memory while "Windows Hello for memory lists"
  said it was hidden.** The HUD's copy is covered too. Galaxy's search now
  counts every match and says when nothing matches.

**New: reminders, your phone, and Lockdown**

- **"Remind me next time I talk about X."** When your own words later mention
  it, Jarvis brings it up in the chat. At most 3 times, never out loud if the
  topic is sensitive, gone after 90 days. No card.
- **"Ring my phone."** Said to Jarvis on the PC, your phone rings on its alarm
  sound - even on silent - with a Stop button, for at most 2 minutes. It never
  rings for an old message.
- **"Playing on your PC" on the phone's Home:** previous, play, pause, next.
- **Lockdown.** One tap (or "lockdown") makes everything that would leave the
  PC ask first, and anything that runs by itself stop. Turning it off is on
  the PC only, with a card and Windows Hello. Not yet covered: the ntfy push
  notice, which lives in your own `jarvis_gate.py`.

**New: smarter memory**

- **"Where did I put ...?"** Tell Jarvis "the passport is in the top
  drawer", then ask "where's my passport?" - it answers at once, without the
  AI model, and says when you told it. A newer place replaces the older one.
  ("Where's my phone?" still rings your phone.)
- **Facts keep "until" dates from your words** ("on holiday until 12
  October") and are never hidden by themselves when the date passes: Jarvis
  asks "Still true?" instead.
- **Overnight memory tidying now actually runs, cards only:** at most five
  "Still true?" or "Which is true now?" cards a night, using the AI on this
  PC only, and only while its switch is on. It never changes a fact by itself.
- **Deleting a chat offers to forget the facts it taught you**, with nothing
  ticked to start, and "are you sure?" before anything is forgotten.

**New: phone conveniences**

- **After a restart, a quiet "Hey Jarvis is off - tap to turn it back on"
  notice**, if listening was on before. Nothing opens the microphone by
  itself.
- **Three Quick Settings tiles you choose:** a focus session, a 10-minute
  timer, Brief me, Stop everything, or play/pause on the PC. Never Approve or
  Deny. Held while the connection catches up. Stop everything works even
  while the app is locked, like the PC's hotkey.
- **Notes for Android 17:** Jarvis's voice has its own volume slider, and
  Floating Jarvis may work as an app bubble (touch and hold the icon).
- **Install notes for 2027:** Google will require extra steps to install
  unverified apps by tapping the file; installing from the PC with adb stays
  allowed (docs/INSTALL.md).

**New: better voice (each off until measured on your PC)**

- **An optional second "hey Jarvis" check:** two detectors must agree before
  Jarvis wakes, for fewer false wake-ups. Off until you choose it, in both
  apps.
- **A newer speech detector (Silero VAD v6)** you can switch to after
  measuring it on your PC; today's stays the default.
- **A third voice-ID model (WeSpeaker ResNet221)** is ready but cannot be
  chosen until it is measured on your PC - in a first test it let other
  voices through more often than the one used today.

**New: Today cards**

- **Your own words on a Today section** in both apps (above Coming up), at a
  time and on the days you choose: "show gym bag on my Today page on Mondays
  at 7". Set by saying it or with a small form; no approval card; Delete is
  immediate.
- **The Today section also shows today's briefing** - weather, calendar,
  email and what is still to come - without reading anything new.

**New: photo to reminder**

- **Give Jarvis a screenshot, a picture file or a shared photo** of a flyer or
  ticket, and it suggests a reminder from the date and time it finds. Nothing
  is set up until you tap Add (or "Also on my phone"). The words are read on
  your PC, never by the AI model, and are not kept.
- **You can now say calendar dates:** "remind me on 12 October at 2pm to pay
  the deposit". A slashed date like 5/10 is read month first (May 10).

**New: PC help**

- **Ask "why is my PC slow?", "how full is my disk?", "what's using my graphics
  card?", "how hot is my graphics card?" or "when did my PC last restart?"**
  and get a plain answer at once, without the AI model. Also under Settings ->
  Hardware and models on the PC and Brain -> PC help on the phone. It only
  reads; program names never leave the PC and are not saved. Changing Windows
  settings (Night light, dark mode) is not built yet.

**New: smarter answers**

- **Big tool results (long files, emails, web pages) are shortened to their
  start and end** instead of being dropped, so Jarvis can still answer from
  them. In long answers that use many tools, older tool results are cleared
  to make room; your own words are never cut.
- **If Jarvis says it did something but nothing actually ran,** the answer
  now ends with "(Nothing was actually done - no action ran in this
  answer.)" - and says so aloud on voice.

**New: model tryouts (tools only - nothing switches by itself)**

- **Try other chat models overnight** against Jarvis's own: tools, learning,
  speed and how much fits on the graphics card, with a plain verdict for each
  (`tools/model_tryout/README.md`).
- **Try other memory-search models and re-rankers** with the memory
  self-test. New `JARVIS_MEMORY_EMBED_MODEL` / `JARVIS_MEMORY_RERANK_MODEL`
  switches; the defaults are unchanged.
- **The preflight check warns about a hidden llama.cpp `config.ini`,** and
  docs/MODEL-TOPOLOGY.md has two engine settings to try, with how to measure
  and undo each.

**New: bring in old chats from ChatGPT, Claude or Gemini**

- **Brain -> Memory on the PC: "Bring in chats from ChatGPT, Claude or
  Gemini".** Choose the export file; Jarvis reads it in the background and
  every possible fact waits for your yes, one card at a time. Nothing is
  saved by itself, and nothing leaves the PC.
- **Changed: importing reads only your own messages,** never the other
  assistant's replies - for all three services (Claude and Gemini imports
  used to read both sides).
- **Fixed:** a Google Takeout with Search activity in it no longer treats
  searches as Gemini chats.

**New: desktop polish**

- **Brain, Settings, Faces and the HUD reopen where you left them,** at the
  same size, and maximised if they were. App lock still asks Windows Hello
  before the HUD shows. A window whose screen was unplugged opens centred.
- **While Jarvis is clicking or typing on your screen,** the widget shows
  "Jarvis is working on your screen", a timer and a Stop button - the same
  as the Stop everything key.

**New: talk-to-type on the PC**

- **Hold Alt+Shift+T, speak, let go** - Jarvis types what you said into the
  program in front. Off by default; turning it on shows one approval card,
  turning it off is immediate. The voice check still comes first.
- **It never types into a password box, while Jarvis is locked, or into a
  window you switched to.** Your clipboard is put back afterwards, and the
  words stay out of Windows' clipboard history. The words are not kept.

**Fixed**

- **Desktop security update.** The desktop app's framework (Tauri) goes from
  2.11.5 to 2.11.6, which closes a published hole (GHSA-w28w-mhc8-qvjv) where
  one window of an app could read data queued for another window. Jarvis has
  several windows and streams chat answers that way, so it was affected.
- **Speech and memory-search models no longer report to Microsoft.** The
  library that runs them (ONNX Runtime) has its own usage reports switched on
  by default. Jarvis now switches them off before any model loads. One copy
  inside the speech engine can't be reached this way; Windows' own "Send
  optional diagnostic data" switch covers that one (docs/ARCHITECTURE.md §4).
- **A fact you forget no longer comes back by itself.** Jarvis re-reads the
  whole chat when it learns, so about a minute after you pressed Forget (or
  Erase), the same sentence could be saved again without asking. Now nothing
  is learned again from the lines it had already read in that chat, and if
  you say a forgotten fact again later, it waits for your yes.

**Faster**

- **A faster first answer after waking, and after a pause.** Jarvis now
  reads its rules and tool list into the model ahead of time - a one-word
  warm-up whose answer is thrown away and never recorded. It never loads the
  model by itself, never runs while you are asking something, and gives way
  the moment you do. To switch it off: `warm_prefix = false` under `[power]`
  in `jarvis-framework.toml`.
- **Jarvis speaks sooner.** Speech-to-text and the voice now use 4 processor
  threads instead of 2 on a PC with cores to spare (2 on a small one), which
  measured about 0.3 s sooner to the first sound. Your own `stt_threads` /
  `tts_threads` setting still wins.
- **The model's settings file explains the real memory check.** The notes in
  `backend/jarvis-primary.Modelfile` were out of date about flash attention.
  They now give the one PowerShell line that shows whether the whole model is
  on the graphics card ("offloaded 37/37").

**Smaller fixes**

- **The model tool test is fair to other models.** A model that loads with
  too short a conversation is skipped with a plain message saying how to fix
  it, `--repeat` saves the worst of several runs, and a model maker's own
  settings can be tried (`tools/tool_eval/README.md`).
- **The smartwatch setting says a ringing alarm may stay on the phone.**
  Watches often skip notifications that keep going until you stop them.

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
