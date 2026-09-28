# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **Solve it here: a captcha handed to your phone.** When a chatbot website
  or a customer-support chat that Jarvis is using stops at a captcha, a
  sign-in page or an "unusual activity" page, your phone now says so ("Gemini
  needs you") and offers **Solve it here**: a live picture of that one
  browser window on your PC, and your taps and typing passed back to it -
  only while Jarvis is paused there, never saved on either side. Jarvis never
  solves it for you. Some captchas refuse taps passed on this way; "Solve it
  on the PC instead" is always there, and the PC's Brain shows the same
  alert. Press Resume when it is done (Resume asks with a card, as always).
  Not yet tried against a real captcha.

- **Jarvis Live extras.** On the PC: a key to start or end Live, off until
  you pick one in Settings -> Shortcuts (Alt+Shift+L is free for it). On the
  phone: a Quick Settings tile (with the minutes left), the headset button
  (press to stop Jarvis talking, hold to turn the microphone off or on - it
  never approves anything), a "Live ended - Resume" notification for ten
  minutes, a Bluetooth headset's microphone used while one is connected (the
  Live screen says which microphone), "Talk about this in Live" in the Share
  sheet (the shared text is outside text and goes when you tap Send), and
  "End Live when" on the Security screen, like the PC's: when App lock would
  ask again (the default), or only when the phone's screen locks (asks for
  your fingerprint or PIN). Not yet tried on a real phone.

- **Chat with customer support for me.** Jarvis can chat with a company's
  customer support for you - Groupon first - in your name, in a browser
  window you can see on the PC. Fill in the company, what you want done and
  the details Jarvis may give (each one exactly as written) on either app's
  Brain; ONE approval card shows all of it and the company's terms risk
  (your real account could be closed). You open the chat on the help page
  yourself; Jarvis writes from there. **Every offer - a refund, a credit, a
  cancellation - gets its own card**, and nothing is accepted before you
  approve it; the app offers Decline, Say something else and Take over,
  never Accept. "Are you a bot?", identity checks (card digits, security
  questions, codes) and a detail not on the card are handed to you - Jarvis
  never claims to be a person and never sends a password, card number or ID
  number. The chat is kept in your encrypted chat history; Export on the PC
  saves a plain text copy. Not yet tried on Groupon's real site: run the
  read-only check first (backend/README.md, "Chat with customer support for
  me").

- **Forget a time frame.** Say or type "forget what you learned last
  week" or "delete my chats from 1 to 15 September", or open it yourself:
  the desktop's Brain -> History, or the phone's Brain. Jarvis lists every
  fact it saved in those days and every chat from them, each ticked; untick
  anything to keep and tap **Forget these**. One approval card lists
  everything, and you approve it by tapping - saying "yes" does nothing.
  The facts are forgotten, exactly like Forget, and the chats deleted; for
  **10 minutes one tap on Undo puts it all back** (the Undo is kept in
  memory only, so it also ends if Jarvis restarts). A chat that also has
  messages from other days is marked, because the whole chat goes. At most
  200 at once. If a date could mean two things ("on Monday" said on a
  Monday, "3/9"), Jarvis asks. Erasing a fact's words for good is still
  "Erase the words", one fact at a time. This is the one place Jarvis
  deletes many things at once. Not yet tried on your PC's real memory.

- **The money limit for chatbots with a key is now a hard stop.** Every
  message asks the service to keep its answer short enough to fit in what
  is left of your monthly limit (at most 8,000 word-pieces, fewer as the
  month is used), so one long answer cannot carry a month past it. An
  answer cut short says so under it in both apps: "Jarvis asked for a
  short answer so it stays within your limit; the rest was cut off." Each
  company calls this setting something different; each name was checked in
  that company's own code (OpenAI, Groq, OpenRouter, Mistral, and xAI from
  its own client program). **DeepSeek's could not be confirmed, so no cap
  is sent to DeepSeek** - it keeps the old check before each message. For
  every service except OpenAI, whether hidden "thinking" counts inside the
  cap is not stated, so Jarvis leaves room for it - a guess, so a month
  can still end slightly over there. See it per service with
  `cd "<your backend folder>"; py -3 jarvis_chatbot_api.py spent`. Not yet
  tried against the real services.

- **A monthly money limit for chatbots with a key.** Each service Jarvis
  reaches with an API key (OpenAI, DeepSeek, Mistral, xAI, OpenRouter,
  Groq) now needs a monthly limit before it is used - set on the PC with
  one line, for example
  `cd "<your backend folder>"; py -3 jarvis_chatbot_api.py limit openai 5`
  for $5 a month. Jarvis estimates each message's cost from the
  word-pieces the company reports and a price list, stops a service when
  its month reaches the limit, and checks before every message that it
  cannot go over. The approval card and both apps show "About $4.55 of
  $5.00 left this month for OpenAI", and "Used so far" adds "about $0.03".
  **The prices Jarvis starts with are not checked** (written from memory,
  no price page could be opened): see them with
  `py -3 jarvis_chatbot_api.py spent` and correct one with
  `py -3 jarvis_chatbot_api.py price openai <in> <out>`. It is an estimate,
  so a month can end slightly over. Limits and prices can only be set on
  the PC; the apps only show them. Not yet tried against the real services.

- **Jarvis Live, fixed after four reviews - and your three answers built.**
  - **After a crisis answer, Live gets more time.** It does not end at its
    time limit until at least 30 minutes after the last such answer, and
    it does not say "minutes left". It is quiet about it. You can still end
    it any time. Both apps.
  - **One "Interrupting Jarvis" setting** instead of two, for Live and
    everyday voice alike: "Interrupt by voice" (recommended), "By button
    only", or "Don't interrupt". On the PC: Settings -> Voice, where the old
    switch was. On the phone: the Readiness screen. Your old choice carries
    over (the old switch off becomes "Don't interrupt"; Live's "tap only"
    becomes "By button only").
  - **Remarks to someone else are not kept in chat history at all** (they
    were kept, marked "(not for Jarvis)"). An old one still in your history
    shows as "(not for Jarvis)".
  - **"End Live when"** (PC, Settings -> Voice): with App lock on, Live ends
    when App lock would ask again (the default), or only when Windows locks
    - the looser choice asks with an approval card. The phone keeps App
    lock's own rule.
  - **Clearer words:** "End Live" (not "Stop"), "Mic off" / "Mic on" (not
    "Mute"), "Listen anyway" during a call; every pause says what to do
    next; "your PC", never "your desktop"; when Live ends it says why, in
    a sentence, and says it aloud when it ended by itself.
  - **Fewer surprises:** "that's it" or "I'm done" in answer to a question
    no longer ends Live; only a card raised during Live pauses it (an old
    waiting card does not); tap buttons no longer come out garbled; typing
    counts as talking for the quiet timer; Esc on the PC hides the bar but
    keeps the conversation; a remark to someone else no longer wipes the
    answer (or the crisis help) off the screen.
  - **Easier to find:** the phone has a strip on Home while Live is on and
    a "Live" shortcut when you long-press the app icon; the PC's tray icon
    gets a red mark; "What asks first" lists "Start Jarvis Live - does it
    without asking" in both apps; Brain's old "Live" tab on the PC is now
    called "Now".
  - Said plainly: none of this has run on your PC or phone yet, and the
    phone's part is only compiled by GitHub.

- **Jarvis Live: talk back and forth, on the PC and the phone.** Press
  Live (the Jarvis bar, the tray, or Home -> Live on the phone) or say "Hey
  Jarvis, let's talk", then just talk - no "Hey Jarvis" before each
  sentence. Every sentence is still checked to be your voice on your PC
  before any words are made of it, and cards still need a tap (Jarvis stops
  listening while one waits). A sign shows the whole time ("Jarvis Live ·
  24 min left"), with Mute and Stop; on the phone a notification with End
  and Mute. It ends when you say "Okay Jarvis, that's all for now", press
  Stop, after 90 quiet seconds, or at 30 minutes ("give me twenty more
  minutes" adds time). After a spoken question, tap buttons ("Yes", "No")
  answer it; you can type too. It pauses itself during a phone or video
  call. Two new voice settings in both apps: "Jarvis Live" (how far it is
  trusted under "Only trust the talk button"; trusted fully by default) and
  "Interrupting Jarvis in Live" (by voice, or by tap only). Said plainly:
  it needs your voice trained first; very short replies ("yes") are still
  too short to check, so use the buttons; nothing has been timed on your
  PC; and **the camera part is built but switched off** until the second
  graphics card is in and passes the photo test.

- **Chatbot driver fixes, and a correction: every chatbot is reachable from
  both apps.** The entries below that say "still not usable from either
  app" are out of date: both apps' chatbot screens can start a
  conversation with any of the chatbots once it is set up (a website signed
  in, a key saved, or the model chosen). None has been tried against the
  real site or service yet. Fixed at the same time: a website window no
  longer reads an answer from a different chat you clicked while the first
  answer was coming; each site's self-check now asks two questions in the
  same chat, so a wrong guess about a site's chat address is caught by the
  check rather than mid-conversation; a site no longer shows "ready" after
  a sign-in window that was closed before you finished signing in (if you
  signed in to Gemini before this change, run
  `py -3 jarvis_chatbot_gemini.py sign-in` once more - it finishes at once
  if it is still signed in); the second AI on your PC no longer ends with a
  wrong "did not answer within 180 seconds" when it was only waiting for
  your own chat, and Stop now cancels its answer so the graphics card is
  freed; and a few words are now right (no "leaves this PC" or "(this PC)
  (this PC)" for the second AI on your PC, and the real reason when a
  key-based chatbot is not set up).

- **A new voice setting in both apps: "Answers about your screen after
  "Hey Jarvis"".** If you choose "Only trust the talk button" for
  hands-free, an answer about your screen to a question that starts with
  "Hey Jarvis" now stays on screen - written, not read aloud. This setting
  lets you allow reading those answers aloud anyway: "Read aloud" shows an
  approval card first; "Keep on screen" (the default) applies at once. With
  "Same as the talk button" it changes nothing, and the settings page says
  so. It is under Settings -> Voice on the PC, and Checks -> Voice check on
  the phone. Said plainly: Jarvis cannot look at your screen from either
  app yet, so for now the setting is stored and waiting.


- **Ask several chatbots and compare** (both apps, Brain -> "Talk to a
  chatbot for me"). Tick "Ask several and compare", pick two or more
  chatbots, type the goal once. One approval card lists every chatbot
  Jarvis would ask. Jarvis then talks to each one in turn, under the same
  limits and checks as a single conversation, and at the end writes one
  summary on your PC: where they agree, where they disagree (and who said
  what), the sources each gave (not checked by Jarvis), and which one
  dropped out and why. If one shows a captcha or a sign-in page, Jarvis
  leaves it out and carries on with the others. Pause, Resume and Stop act
  on the whole comparison. Up to 3 chatbots with one graphics card, 4 with
  two (you confirmed these numbers). Not yet tried against the real
  chatbot websites.
- **The chatbot chooser is a list you can read on a phone.** It used to be
  one row of buttons, and with sixteen chatbots most fell off the screen.
  Both apps now list them one per line under three headings - "Websites (a
  browser window on the PC)", "With a key (each message costs a little)",
  "On this PC" - with the reason under any that is not set up yet.
- **A conversation through a key shows what it used**: "Used so far: 3
  requests, 4,215 word-pieces (tokens), model gpt-5-mini" (per chatbot in a
  comparison). The card already said Jarvis would show this; neither app
  did.
- **"What Jarvis can reach" showed the chatbot ways out as Off** although
  both apps can start conversations: a switch the routes should have set
  was never set. Fixed.
- **The chatbot driver can now work eight more chatbot websites - still not
  usable from either app.** ChatGPT, Claude, Microsoft Copilot and
  Perplexity, plus DeepSeek, Grok, Le Chat (Mistral) and Meta AI (these
  last four picked as "other commonly used" websites - say if you want any
  left out). Each works exactly like Gemini: a browser window you can see,
  a steady typing pace, nothing hidden, and a stop to ask you at any
  captcha, sign-in or "unusual activity" page. Each has its own spare
  account, signed in once by hand, and each company's terms restrict
  automated use, so that account may be blocked or closed. Perplexity's
  listed sources are copied as text under its answer, never opened. How
  Jarvis finds each site's buttons could not be tried against the real
  sites: run each site's one-line self-check on the PC first
  (`backend/README.md`).

- **The rules for letting Jarvis look at your screen - not in the apps
  yet.** "Look at this" (one look when you ask) and "Watch with me" (a
  session you start and stop, 30 minutes unless you say otherwise, 2 hours
  at most) now have their rules written and tested on the PC side: Jarvis
  pauses on password boxes, on anything on your "Never look at" list
  (password managers and Windows sign-in to start with; adding is instant,
  taking something off asks with a card), on protected windows and on pages
  whose site it can't read; it checks just before and just after each
  picture and throws the picture away if either check fails; it keeps
  nothing it saw; and "Stop everything" ends a session. Answers about the
  screen will be read aloud unless a sensitive fact was used, like web
  search answers. There is no key, button or setting for it in either app
  yet, and the parts that read Windows itself are the next step.

- **A switch to turn off swiping on approval cards** (phone, Security).
  Swiping right to approve and left to deny stays on unless you turn it
  off; off, every card is decided with its buttons only. Turning it back on
  asks for your fingerprint or PIN.
- **The chatbot driver can also use a key, or a second AI on your PC -
  still not usable from either app.** With a key saved on the PC, Jarvis
  can hold its one-card conversation with ChatGPT (OpenAI), DeepSeek,
  Mistral, Grok, OpenRouter or Groq through each company's official API.
  The key stays in Windows Credential Manager and goes only to that
  company. Each message costs a little on that account; Jarvis shows the
  word-pieces (tokens) used, but there is no money limit yet. Or it can talk
  to another AI model on your own PC, where nothing leaves the PC: with one
  graphics card that is the same model Jarvis uses, with both cards any
  model you already have. How to save a key: `backend/README.md`.
- **The chatbot driver's Gemini part is written - still not usable from
  either app.** Jarvis can now open its own Gemini window (gemini.google.com,
  in a browser window you can see), type a question at a steady pace, and
  read back only the answer to it. It never hides that it is a program, and
  at a captcha, a sign-in page or an "unusual activity" page it stops and
  asks you instead of trying to get past it. It uses its own browser profile,
  which you sign in to once, by hand, with the spare Google account. Before
  real use, run the one-line self-check on the PC (`backend/README.md`) - it
  sends "What is 2 plus 2?" and says PASS or FAIL for each step, because the
  way it finds Gemini's buttons could not be tested against the real site.
- **"Talk to a chatbot for me" now has its screens in both apps - but no
  chatbot can be reached yet.** On the PC it is a card in Brain -> Work; on
  the phone, a card in Brain. You choose the chatbot, type what Jarvis
  should find out (the card says these words are sent exactly as typed),
  set the most messages and minutes and any words it must never send, and
  Start asks for one approval card - nothing is sent before your yes. While
  it talks you see the conversation, with the chatbot's words marked
  "outside text", plus Pause, Resume and Stop; changing a limit asks a new
  card; the summary stays on screen at the end and is never read aloud. The
  phone also shows "Talking to Gemini, 3 of 5" with a Stop button. Gemini's
  part is still being built, so today Start says so and does nothing.
- **New: Projects in both apps.** Brain now has Projects on the PC and on
  the phone. Make a project, write how Jarvis should help with it and a
  few notes, and track numbers ("benchmarks") - log a number with a tap,
  see a small chart of your numbers over time with your target as a
  dashed line, and whether each one is better or worse than last time.
  Health and money numbers show "private - not read aloud". Deleting asks
  "are you sure?" first. A coding project's folder is chosen on the PC
  (from "Folders Jarvis may look in"); the phone says "Set on your PC" for
  that. The "Shareable" switch asks you with a card to turn on, and turns
  off at once.
- **New: take a wrong private mark off.** Jarvis sometimes marks a number
  private by mistake - it reads "5k time" as money. You can now remove
  that mark; because the numbers may then be read aloud, it asks you with
  one approval card first. A mark you added yourself comes off at once.
  Renaming the benchmark checks its name again.
- **Backups and the data-health check now include your projects**
  (`projects.db`). Before this, a backup would not have kept them.
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
- **Projects, first part (on the PC's side only - not in the apps yet).**
  Jarvis can now keep projects: a coding project (an app) or a life
  project ("run a half marathon"), each with its own instructions, a few
  notes, a to-do list and the goals it belongs to. A coding project's
  folder must already be one of "Folders Jarvis may look in", and is
  chosen on the PC. Each project can track numbers ("benchmarks"): say
  "I ran 5 km" or "log my weight as 72.5 kg" and Jarvis writes it down
  without the AI model and says whether it is better or worse than last
  time - but only when one of your projects tracks that number.
  Weight, heart rate, money and other health or money numbers stay on
  screen and are never read aloud. A "Shareable" switch per project
  starts off, and turning it on asks you with a card; nothing is ever
  sent by it yet. Running tests and Jarvis changing code come later. The
  screens in both apps are next.
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
