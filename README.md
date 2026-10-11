# Jarvis

A personal assistant that runs on **your own Windows 11 PC**, with a desktop
app on that PC and a companion app on an Android phone. The AI model runs on
the PC's own graphics card, so your email, files and memories stay on your own
machine instead of being sent to a company's servers — with **three named
exceptions**, each one approved by you, listed in
[What it is, and what it is not](#what-it-is-and-what-it-is-not).

Version 0.2.0 ([what changed](CHANGELOG.md)) — the last *numbered* release. The
newest work sits above it under "Not in a numbered version yet". Made by
**darknight11ish**. Free and non-commercial: installed by hand, never sold,
never on Google Play.

**New here?** [What it is, and what it is not](#what-it-is-and-what-it-is-not) ·
[The five rules](#the-five-rules-that-are-not-negotiable) ·
[What it can do](#what-it-can-do) ·
[What asks first](#what-asks-first) ·
[Install it](#install-it) (two commands) ·
[Honest limits](#honest-limits).

## What it is, and what it is not

**What it is.** Three pieces working together:

- **The backend** — a Python program on your PC. It holds the model, the
  memory, the timers, and every connection to the outside world. This is the
  part that actually does things.
- **The desktop app** — the window you look at on the PC. It is built with
  Tauri (a tool that wraps a web page into a normal desktop program).
- **The phone app** — an Android companion called `jarvis-client`. It reaches
  the PC over a private network, never over the open internet.

The "AI" is a model of about **8 billion parameters** running in
[Ollama](https://ollama.com) (the free program that runs AI models on your own
PC) on the same machine. That is small enough to fit on a home graphics card,
which is the whole point: it is not ChatGPT, there is no account to sign up to,
and nothing runs in a data centre.

**What it is not.** Said plainly:

- **Not a cloud service.** Nothing about you goes to a company's servers of its
  own accord. There are a few named exceptions, each behind an approval card.
  Two of them deserve spelling out: **one approval lasts for a whole chatbot
  conversation**, not a single message; and **the locked backup file can be
  saved into a folder your cloud service syncs**. See
  [What asks first](#what-asks-first).
- **Not a company product.** It is one person's project, built for one owner,
  and published so somebody else can run it.
- **Not on Google Play.** The phone app is installed by hand (`adb` — the PC
  tool that installs apps onto an Android phone), and is never sold.
- **Not finished.** Some parts are off until they have been measured, and
  some things were deliberately left out. [Honest limits](#honest-limits)
  says which.

## The five rules that are not negotiable

These are not features. They are the promises the whole program is built
around, and every change is checked against them.

1. Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.
2. The app never opens a public tunnel. No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. API keys are allowed in the app - the owner reversed the old blanket ban
   on 2026-09-17, to unblock things like a GitHub API integration. Any key
   still gets the same care the pairing token already gets: never logged,
   sent only to the one service it authenticates against, and kept out of
   anything the app writes to disk in plain text.
4. The app never auto-approves anything, and blocks acting when the event
   stream is stale.
5. Non-commercial build. Sideloaded via adb, never listed on Play.
   The owner said on 2026-09-28 that EpicJarvis **will never be
   commercialized**. So a non-commercial licence (CC BY-NC, CC BY-NC-SA) is
   no reason to avoid or replace a part - don't raise "it blocks selling
   Jarvis" as a concern. Everything else those licences ask still applies:
   credit in THIRD-PARTY-NOTICES.txt, share-alike, no redistribution
   against their terms.

> **Three approved exceptions exist, and each is named and bounded.** Rule 1 is
> bent for exactly two things in what ships today.
>
> - A project's **"Shareable"** switch — **off by default**, approved by you
>   each time it is used, and it never carries health or money numbers, memory,
>   email or credentials — may send a short piece of that project's files,
>   shown word for word on its card first, to a web search or a chatbot. See
>   [Projects, goals and jobs](#projects-goals-and-jobs).
> - The **locked backup file** may be saved into a folder your cloud service
>   syncs. It is a locked copy of what Jarvis knows — which is exactly why its
>   recovery code matters so much. See [Models, hardware and
>   settings](#models-hardware-and-settings).
>
> Rule 4 is bent for exactly one thing: one approval covers a whole chatbot
> conversation, and Jarvis may then keep asking questions on its own, inside the
> limits you set (see [Other AIs](#other-ais) and
> [What asks first](#what-asks-first)). Nothing else in these five rules is
> loosened anywhere.

## What it can do

Everything below is real and in the app. Each area says what you get, and
marks anything that is **off by default**, anything that **asks first**, and
anything that **needs the second graphics card**. Both apps carry the same
list, on their own **Settings → What asks first** page.

### Talk to it

- **Type a question and read the answer as it is written.** Press `Alt+Space`
  for the Jarvis bar (the small chat window), type in the box, press Enter.
  Talking costs no approval card.
- **The whole conversation is one scrollable thread**, and an earlier chat can
  be picked up again from History with "Continue this chat". A new
  conversation starts after 30 quiet minutes (changeable to 10 minutes, 1
  hour, 4 hours or never), and the old one stays in History.
- **"Coach this"** — turn it on in Settings and a button beside the box reads
  what you wrote and says what is missing: a score, up to four gaps with the
  smallest fix for each, and one rewritten version of your request. It never
  sends anything by itself, and a low score never stops you sending your own
  words. **Off by default.**
- **Temporary chat** — nothing is kept and none of your saved facts are used.
- **Search your own past chats**, on screen only; the words are never handed
  to the AI.
- **Tag chats yourself**, and let Jarvis suggest tags overnight. A suggested
  tag is filed only if you tap it.
- **How Jarvis talks** — warm and brief (the default) or plain. Humour is a
  switch, **off to start**, and never appears on a card, an error or a serious
  topic.

### Voice

- **The talk button.** Hold it, speak, let go. Your voice is checked on the PC
  first, before the words are turned into text.
- **Say "Hey Jarvis"** to start talking without touching anything. **Off until
  you turn it on** (one card). The app says plainly that the check cannot tell
  a recording or a copy of your voice from the real one.
- **Teach Jarvis your voice** — one card before it learns. The recordings are
  deleted either way.
- **How strict the voice check is** — a stricter choice is instant; a looser
  one raises a card.
- **Jarvis reads its answers aloud**, and a question asked by voice gets an
  answer written to be heard: a short first sentence, no lists. An answer that
  used a sensitive saved fact stays on screen instead, unless you allow it.
- **Pick the voice Jarvis speaks with, and hear a sample of it.** The voice
  pack is a 350 MB download on the PC, checksum-pinned. Adding a voice of your
  own raises a card.
- **Interrupt by talking**, instead of waiting for the answer to finish. About
  two seconds of what you say is checked for your voice only, and never
  written down.
- **Jarvis Live** — a back-and-forth voice conversation you start and stop,
  with no wake word between turns. It is not full-duplex (that would skip the
  voice check), so a turn takes a couple of seconds. Cards are still decided
  by tapping, never by voice, and side remarks meant for someone else are
  ignored and not kept. Live pauses itself during a phone or video call, where
  the phone can tell one is happening.
- **Around Live:** a phone Quick Settings tile, a headset button (press stops
  the talking, long press mutes the microphone, and it never approves
  anything), and a "Live ended – Resume" note.
- **Talk-to-type (PC only).** Hold `Alt+Shift+T` (changeable in Settings),
  speak, and Jarvis types what you said into the program in front. One card to
  switch it on; nothing after that. It never types into a password box, and it
  waits while Jarvis Live is on. The phone never turns speech into words.

### Memory and learning

- **Everything Jarvis knows lives on the Brain screen** (the Memory tab on the
  PC), with its own lists, topics and switches.
- **Chat history is kept on the PC, encrypted, by default**, with a switch to
  turn keeping it off. The phone keeps none of it.
- **Everyday facts save by themselves**, learned from **your own words only** —
  never from a web page, an email, a document or tool output.
- **Health, money, passwords and other sensitive topics wait for your yes.**
  "Also remember sensitive topics automatically" is **off by default**;
  passwords, PINs, account numbers and ID numbers always wait, even with it
  on.
- **Every fact is listed**, with **Forget** (it asks "are you sure?" first)
  and **Erase the words** (it asks too, and cannot be undone — only the dates
  stay). Erasing can also offer to delete the chat the fact came from.
- **Facts waiting for your yes** — one card per fact, or one card covering
  several. Nothing is saved until you answer. This is the one list that is
  never hidden.
- **Always keep in mind** — facts put into every answer. It holds a fixed
  number of characters, and the card says how many are used.
- **Between us** — inside jokes and shared references, from your own words
  only.
- **Topics** — a mode for each topic Jarvis learns about.
- **The learning switches** — whether Jarvis learns by itself and how much it
  remembers. Turning automatic learning on raises a card; turning it off is
  instant.
- **A wiki Jarvis builds** from documents you give it. Adding a document
  raises one card.
- **Deep questions** — slow, deeper answers, with the questions and answers
  kept so you can look back.
- **What did I believe on this date?** (phone) — ask what a fact said on a
  past day. It needs the connection live.
- **Bring in old chats** (PC) — import an export from ChatGPT, Claude, Gemini
  or DeepSeek. It only proposes: every fact it finds waits for its own yes,
  and imported text is never learned from.
- **People and things** (phone) — the people and things your facts are linked
  to.
- **Forget a time frame** — "forget what you learned last week". Both apps
  show the exact facts and chats from that time, each ticked, and **one card
  decides all of it by tapping, never by voice**. Then 10 minutes to Undo.
  After that the chats are gone for good.
- **Galaxy** (PC) — a map of what Jarvis knows, drawn from your own facts.

### Notes, files and study

- **Jarvis writes a note into Obsidian, Logseq or Joplin.** Normally no card —
  but in a turn where Jarvis has read an email, a page or a file, writing a
  note **raises one card**.
- **Folders Jarvis may read**, chosen through the Windows folder picker, plus
  the Notion export. Adding a folder raises one card; removing one is instant.
  Imported notes are "outside text": never learned as facts.
- **Ask about a PDF, a Word file or a Notion page.** Reading needs no card;
  writing a note back after reading it does.
- **My study decks** — questions you keep, asked again on a schedule the PC
  works out.
- **Quiz me on a text**, or on a YouTube video. Nothing is saved. A YouTube
  quiz sends the link once (one card).
- **Tutorials and the FAQ** — step-by-step guides with your place kept, and
  the usual questions answered. Reading works even while the connection is
  catching up.
- **PC help** (phone) — five plain answers about this PC: what is slow, what
  is full, what is hot. Nothing is read until you press the button.

### Email and calendar

- **Jarvis reads your email** so it can answer questions about it, and "tell
  me when" a named sender writes. Reading needs no card; setting up the alert
  takes one. Text from an email is outside text: it never makes Jarvis act on
  its own, and is never learned as a fact.
- **Send an email for you.** One card per email, showing the exact
  recipients, subject and full text, decided by tapping. There is no "always
  allow". The card says plainly when the conversation has read outside text.
- **Save a draft to your Drafts folder** (PC). One card every time, showing
  the full draft, before any text goes near the folder.
- **Tidy the inbox by voice** — archive, star, mark read, or move to Trash.
  One card lists every email it will touch, approved on screen and never by
  voice, then 10 minutes of Undo. "Delete" only ever moves to Trash. It has
  been tried against a stand-in mail server, never a real mailbox.
- **Read your own calendar** (read-only) so Jarvis can say what is coming up.
  The private calendar link is kept as safely as a password: never logged,
  never shown, and sent nowhere but Google.
- **Weather in the briefing, and the real sun, moon and weather drawn behind a
  character face.** Your own Home Assistant needs no card; Open-Meteo online
  receives your rough location, so turning it on raises one card. **Off by
  default.**

### Web search and the internet

- **Web search with five providers to choose from:** SearXNG (the default,
  self-hosted in Docker on this PC only), DuckDuckGo, Exa, Tavily and Brave.
  Each has a short line saying why you might pick it. **Brave can cost money**
  past its monthly credit; the others are free. If the provider you chose is
  down, Jarvis says so and offers to switch — it never silently uses another.
- **When a search asks first.** A search that comes straight from your own
  question goes without asking. After outside text, or when the search words
  would repeat something private, one card shows the exact words. A setting
  makes it ask every time.
- **A browser without a window** — Jarvis reads a page with a hidden browser,
  so nothing pops up on your screen. Turning it on raises one card.
  **PC only**; the phone can only read what the PC sends back.
- **What's new on GitHub** — name a topic and Jarvis searches for it on a
  schedule, then tells you what is new and what moved. Adding a topic raises
  one card. A repository page is text from a stranger: it is scanned first,
  and a flagged one is listed with the reason rather than handed to a model.
- **News headlines, and pages that change** — headlines from feeds you name
  (up to ten, five headlines each), and a note when a page you are watching
  changes its text. One card each to set up; removing one is instant. A watch
  keeps only a short fingerprint, so it knows *that* something changed but
  never keeps or shows you the page's words, and it runs for up to 90 days.
  Neither one follows a link or acts on what it reads.

### Other AIs

- **Talk to a chatbot for me.** Jarvis holds a conversation with another AI —
  Gemini, ChatGPT, Claude, Copilot, Perplexity, DeepSeek, Grok, Le Chat, Meta
  AI, and services reached by API key — and brings back what it said. One card
  lists every chatbot it will ask; that card covers **the whole conversation**,
  so after you approve it Jarvis may keep asking questions on its own inside
  the limits you set. That is the one approved exception to rule 4 — not a
  loophole, and nothing private goes with it. Jarvis can also ask several the
  same question and compare their answers (up to 3 at a time on one graphics
  card, 4 on two). **Nothing private** — email, files, credentials or memory —
  goes into those chats, and each card names that company's terms risk.
- **Deal with customer support for me.** One card before the chat lists
  exactly which personal details Jarvis may give (an order number, an email
  address — never passwords or card numbers). **Every offer gets its own
  card.** Jarvis writes in your name at human speed; if the agent asks whether
  they are talking to a bot, Jarvis never claims to be human — it hands that
  question to you. Identity checks (card digits, security questions, codes)
  are always handed to you. The transcript can be exported as a file, and that
  file is not encrypted.
- **Keys and a monthly money limit** (PC). API keys are written straight into
  Windows Credential Manager, never over the network and never shown again.
  A monthly amount per service stops a paid service when it is reached;
  raising a limit costs one card plus Windows Hello. The amount is an estimate
  from a price list you can see and correct, and the card says "about".
- **Hand a captcha to your phone ("Solve it here").** When Jarvis is driving a
  browser and hits a captcha or a sign-in page, it stops there and your phone
  can show a live picture of that one window for you to solve. **Jarvis itself
  never solves a captcha.** The picture is never saved and goes only to your
  own phone. Some captchas refuse taps passed this way, so the window on the
  PC stays the fallback.

### Your home

- **Ask how the house is** — sensors and devices: whether something is on,
  open or warm. No card to read.
- **Lights, plugs and fans.** A setting, **off by default**, lets Jarvis
  switch the devices you name without a card each time. Turning it on raises
  one card; turning it off is instant. It never applies in a turn that has
  read outside text.
- **Locks, doors, alarms and covers always get their own card** — never a
  standing permission, and never bundled with anything else.

### Your screen and pictures

- **"Look at this"** — Jarvis looks at the window in front of you, once, and
  answers about it. It also hands you the cleaned picture of that look, so you
  can ask about a chart or an error message. Passwords, keys and card numbers
  are painted solid black first, and if the cleaner cannot check the picture,
  none is attached and Jarvis says why. The picture is never saved; the
  question and the answer are kept like any other chat.
- **"Watch with me"** — a live look at your screen that you start and stop. A
  visible "Jarvis is watching" sign shows the whole time. It pauses on
  password fields and on the apps you exclude (banking), and nothing is
  saved. **Not** always-on watching with a history — that was declined.
- **Picture mode** — lets the PC read the *picture* of your screen, not only
  its words. **Off by default**, slow, and it runs on the processor rather
  than the graphics card. With one graphics card, Jarvis reads the screen's
  words only.
- **Photo to reminder** — show Jarvis a photo of a letter or an appointment
  card and it offers the dates it can read. It only proposes; your tap adds
  one reminder.
- **Show Jarvis the camera in Live** (phone) — **off until the 12 GB card is
  installed and a photo test passes.** There is no words-only camera on one
  card.

### Time, reminders and briefings

- **Timers, alarms, reminders, to-do lists and the standby schedule.** A plain
  timer, a one-time reminder, a repeating reminder, an alarm and the standby
  schedule **need no card**. The morning briefing and "tell me when" raise
  one, because they read email or the calendar. Simple commands like timers
  are answered without the AI model, so they keep working when the model is
  slow, unloaded or asleep.
- **A late alarm rings only if it is at most 10 minutes late.** After that you
  get a quiet note saying it was missed, instead of a ring as if it were
  happening now.
- **The morning briefing** — your calendar, your new email and the weather. It
  shows the senders of new email as well as the count, with a setting in both
  apps to show the count only. "Brief me now" raises no card.
- **Today** — your own cards for the day, in one place.
- **Widgets you describe** — small tiles you asked for, drawn on the desktop
  widget. A widget's tile actions are a fixed set, and nothing a widget shows
  is ever turned into an instruction.
- **Also on my phone** — hand an alarm to the phone's own Clock app, or a
  reminder to its calendar, by your tap only. The copy in the phone's own apps
  rings even when the PC is off or out of reach.
- **Ring my phone** — to help you find it. Your own words only, answered
  without the AI model, and it rings on the alarm channel even when the phone
  is on silent.

### Focus, and how much it interrupts

- **Focus session (PC)** — a timer plus Quiet, with Jarvis naming a
  distraction out loud ("Instagram can wait") and a short report at the end.
  It watches which app is in front **on the PC only**, and keeps counts, never
  what it saw. **Off unless you start it.** There is no streak line.
- **How much Jarvis may interrupt you** — an interruption budget, and a short
  brief of what needs you today. Muting is instant and approves nothing.

### Projects, goals and jobs

- **Projects** — each with its own instructions, files, chats, goals and
  numbers to track. **One card per change.** A "Shareable" switch per project
  is **off by default**; when it is on, a short piece of the project's files
  may go to a web search or the chatbot driver, shown word for word on its
  card first. Never health or money numbers, and never memory, email or
  credentials. **Jarvis writing code waits for the 12 GB card.**
- **Goals** — plans you edit, with a weekly check-in. Accepting a drafted goal
  raises one card; marking a step done does not.
- **Progress** — an activity heatmap and a balance chart of where your time
  went. The picture is taken out while the private lists are hidden or App
  lock is on.
- **Jobs that keep going after the chat ends.** A job is a named set of steps
  on your PC; it runs one step at a time, remembers where it got to, and
  carries on after a restart instead of starting over. **Every step still
  raises its own approval card before it acts.** Pause and Cancel are instant.
  The list shows how far each job got and which tools it will use, never what
  the job is about. Nothing runs while Jarvis is switched off, and the plan
  card that would start a job from a chat is **still switched off**.
- **"Now"** — what Jarvis is doing right now: its state, each step it is
  taking, and anything it noticed by itself.

### Money and health

- **Spending summaries** — drop a bank export into a folder and plain code on
  the PC adds it up into a small table in the chat. **No model sees the
  numbers**, and the phone only shows what the PC sends.
- **Retirement what-if** — a simple what-if from numbers you type in yourself.
  Nothing is saved, and nothing is asked or sent while the private lists are
  hidden or App lock is on.
- **Crisis help** — if a message sounds like a crisis, Jarvis answers plainly
  with the help lines (United States: **988**, the Suicide & Crisis Lifeline,
  and **911**) instead of carrying on. A crisis question and its answer are
  never learned from, never counted, and do not stay in the thread. The chat
  is still kept in History, called "A difficult moment".

### How it looks: faces, themes and menus

- **25 faces to choose from** — twenty drawn designs, plus four animals (a red
  panda, a pygmy owl, a sea otter and a monkey) and a robot. They breathe,
  look around, sleep when Jarvis is on standby, and move their mouths in time
  with the real voice. The animals and the robot are drawn live, from shapes
  rather than a downloaded 3D model.
- **Animal options** (PC) — every face option in one place: Still, the sun and
  moon, weather and its source, sharpness and frame rate. Cosmetic options
  change at once; anything that opens a way out of the PC still raises its
  card.
- **Appearance** — the theme, the face, and the colour for each state. Look
  and behaviour choices are shared between the PC and the phone; sharpness and
  frame rate stay per device.
- **Show or hide menus** — hide a menu you do not use and bring it back. A few
  things always stay visible: approvals, security, "What asks first", and the
  connection status.
- **Keyboard shortcuts** (PC) — every shortcut in one list, and a key of your
  own for each. A key another program already owns is refused, with the
  reason.

### Models, hardware and settings

- **Models** — switch the everyday model, install another by typing its name,
  or roll back. Switching or installing raises one card, and nothing downloads
  until you approve it. There is **no catalogue to scroll or search** — you
  type the name by hand, the same as at a terminal (`ollama pull <name>`).
- **Hardware and models** — your graphics cards and the three setups Jarvis
  can run in. Choosing a setup changes nothing by itself; each step it needs
  is its own card.
- **The second graphics card** — the switches that put extra work on the
  second card, and which card everyday chat runs on. **The card is installed,
  but its features are not measured — every switch stays off until you turn it
  on.**
- **The big model (slow)** — one bigger model split across both cards, for the
  hardest questions. Only worth it with both cards installed.
- **Compute, Skills and "What this backend supports"** — which model runs
  where, extra abilities installed for Jarvis (each with a scan verdict), and
  the list of abilities the app checks before it offers you a button.
- **The settings file, the logs and starting with Windows** (PC) — start
  Jarvis with Windows, open the log folder, read the crash notes.
- **Backups** — one locked backup file into a folder you pick. Setting the
  folder raises one card; restoring always needs Windows Hello. It is locked
  with a recovery code only you have, **shown once** — lose the code and the
  backup is useless. **The folder may be one your cloud service syncs** (a
  NordLocker folder, for example): that is one of the two deliberate bendings
  of rule 1, and it covers that one locked file and nothing else. Erased facts
  stay in older backups until they age out, and Jarvis keeps only the last few.
- **Accounts and keys** (PC) — the mail password, the private calendar link
  and the Home Assistant token. Saving a secret writes it straight into
  Windows Credential Manager, never over the network and never shown again.
  The phone is never asked for an account secret.
- **What Jarvis can reach** — every way Jarvis can reach something outside
  itself, and whether it is on right now. Loosening a reading tool from the PC
  costs one card plus Windows Hello.
- **Limits and frequency** — the numbers Jarvis keeps to: how long you can
  undo, how much it gets on with at once, how many cards a study run shows,
  and more. Turning a number down changes at once; turning one up that lets
  Jarvis do more is a loosening, so the PC asks first.
- **Undo** (PC) — the changes you can still undo. Undo itself never asks.
- **Activity** (PC) — a read-only list of past approvals: the title,
  Approved / Denied / Timed out, when, and which device.
- **Updates and "Check for tool updates"** (PC). Nothing installs by itself.
  "Check for tool updates" looks up whether the Python packages Jarvis is
  built from have newer versions out and shows you a command for each — **it
  never installs anything**, and you do not need it to update Jarvis. See
  [Update it](#update-it).
- **About Jarvis** (PC) — the version, the licences and the credits.

### The phone app

- **Pairing and the connection.** Pair with a QR code, or a short typed code
  as the backup; **one card on the PC confirms it before any key is handed
  over**. Only your own networks are accepted. The desktop app may point at
  this PC, your home network (private addresses such as `192.168.…` and names
  ending in `.local`), Tailscale or NordVPN Meshnet; **the phone reaches the PC
  only through Tailscale or NordVPN Meshnet — at home too** — because a home
  address would let the pairing key travel unscrambled. A public tunnel is
  refused, with a plain message saying why.
- **Devices** — every paired device, each with its own key. Removing a lost
  phone is instant, and so is retiring the old shared key. This list can never
  be hidden, so a lost phone can always be removed.
- **Let Jarvis read phone notifications** — so you can ask what came in.
  **Off by default**; turning it on raises one card, turning it off is
  instant. Only the apps you choose (never banking), one-time codes are hidden
  before anything reaches the model, and it never makes Jarvis act. Never text
  messages, and Jarvis never replies or sends.
- **Smartwatch notifications** — every notification stays on the phone by
  default. Letting them all show on a compatible watch raises a card.
- **Floating Jarvis** — a small floating face, or a bubble, over your other
  apps. Bubble mode may need more than this setting before Android shows it at
  all — try it on the real phone.
- **Quick Settings tiles** — a tile starts or ends Jarvis Live. It never
  approves anything.
- **Screen refresh rate** — the rate Jarvis asks the phone's screen to run at
  while Jarvis is on screen. It only asks, so it cannot change the phone's own
  display setting; if the screen does not take the rate, the row says so. A
  higher rate uses more battery.

### Keeping you in control

- **Approval cards.** One card for each thing Jarvis wants to do that is not
  completely safe. Nothing runs until you decide, and **there is no
  "approve all" anywhere**. Approving a risky card asks for Windows Hello on
  the PC or your screen lock on the phone. On a PC with no Windows Hello, or a
  phone with no screen lock, a risky approval is refused until one is set up,
  with a plain message saying how. (This narrows a real gap without closing it
  — see [Honest limits](#honest-limits).)
- **"What asks first"** — a page in both apps listing every action and whether
  it asks you, in plain words. A "make stricter" switch is instant. Loosening
  one of a short safe list is PC-only and costs one card plus Windows Hello.
- **Lock Jarvis, and hide what it remembers.** Opening Jarvis needs your
  fingerprint or PIN, and the memory lists and chat history can be hidden.
  Turning a lock on is instant; turning it off or loosening it asks first.
  With App lock on, the phone blocks screenshots, and the PC's approval widget
  shows only a short title.
- **When the connection is catching up, Jarvis stops acting and says so**
  rather than guessing. This is deliberate: acting on a stale picture of the
  world is how the wrong thing gets approved.
- **Stop everything** — `Alt+Shift+X` on the PC. On the phone it is **Home's
  "Stop everything" button, whenever Jarvis is busy**; Jarvis Live has its own
  Stop button for the voice session. It asks nothing first and approves
  nothing.
- **Jarvis marks what it read from outside.** Once it has read an email, a
  page, a file or other outside text, it says so, and the turn is treated as
  tainted — which is what makes the next risky step ask. Outside text is never
  learned as a fact.
- **A warning when text tried to rush you** (phone) — a banner saying outside
  text tried to hurry you into approving something. It is a warning only;
  nothing can clear it, and it is never hidden.
- **Trust** (PC) — outside text that looked risky, and the chain that records
  what Jarvis decided. It holds what is waiting on you, so it can never be
  hidden.
- **A live check of the whole setup** — "N pass, N fail, N warn", testing
  every real chain end to end, with one new check added per real incident.
  Run this one line in PowerShell from this repository's folder, with your own
  backend folder (the one holding `jarvis_hud.py`) between the first quotes;
  the result is also saved as `preflight.txt` on your Desktop:

  ```powershell
  $env:JARVIS_BACKEND = "C:\path\to\your\backend"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"
  ```

## What asks first

**Jarvis never acts without a card for anything that leaves the PC or touches
private things.** It asks, you decide — on the PC or on the phone. Rule 4
above is the short version. One qualification, said plainly: **a card can cover
a whole job, not just a single message.** When you approve a chatbot
conversation, Jarvis may then follow up with that AI *on its own*, inside the
limits you set — that is the one place rule 4 is deliberately loosened.

- Every action that is not completely safe raises **one approval card**.
  Nothing runs until you answer, and there is no "approve all" control
  anywhere.
- **Risky** cards need Windows Hello on the PC, or your screen lock on the
  phone. With no lock set up, the card is refused until you set one up. This
  narrows a real gap without closing it — see [Honest limits](#honest-limits).
- **Stopping is never held back.** Stop everything, Cancel on a job, muting
  and Undo all happen at once, with no card.
- **Outside text raises the bar.** In a turn that has read an email, a page, a
  file or other outside text, note writes, web searches and smart-home
  switches ask first.
- The named ways out of the PC — sending email, the chatbot driver,
  Open-Meteo weather, a web search that could repeat something private — each
  get their own card, and each card says what will leave the PC.

The full list, in plain words, is **Settings → What asks first** in both apps.
It also has "make stricter" switches, and a short safe list the PC may loosen
— each change costing one card plus Windows Hello. Nothing outside that list
can be loosened from an app.

## Install it

**You can install this now.** The Python program that does the work
(`jarvis_hud.py` and the files beside it) is published in this repository, in
[`jarvis-backend/`](jarvis-backend/README.md), as plain source. Until
2026-10-06 it existed only on the author's PC, so nobody else could run Jarvis
at all, however carefully they followed the install page.

Every command is one line. Copy the whole line into **PowerShell** (Start
menu → type `PowerShell` → Enter) and press Enter.

### The quick way: two commands

From the folder you downloaded this into. **First time on this PC:**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-jarvis.ps1
```

It copies `jarvis-backend\` into a folder of your own, runs both install
scripts, says whether Ollama and Jarvis's model are ready, installs the
desktop app, starts the backend and runs the live check. It **never downloads
the model** — that is about 5 GB, so the one command that does it is printed
for you to run yourself. `-Print` ("show me the plan, change nothing") prints
every command it would run, with your paths already in them, and changes
nothing. `-SkipDesktop` leaves the app alone; `-NoStart` prints the start line
instead of starting the backend.

**Every time after that**, one command updates **both halves** — the backend
and the desktop app:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-jarvis.ps1
```

It is described in full under [Update it](#update-it).

Both commands are safe to run again, and both stop and say plainly what they
did and did not change when something is wrong.

**Still by hand:** the phone app (below), and two switches in the desktop
app's own Settings — **Let Jarvis Desktop start and stop Jarvis**, and
**Start Jarvis Desktop when Windows starts**.

### Or step by step

Follow [`docs/INSTALL.md`](docs/INSTALL.md), in order. It has three parts, and
this is what each one does:

1. **The backend on the PC** — the Python program that does the work, plus the
   model in Ollama. Install Git, Python 3.12 and Ollama, clone this repository,
   then copy `jarvis-backend\` to a folder of your own (INSTALL.md step 1.3).
   One script, `scripts/install-backend.ps1`, writes down where that folder is
   (one line; the live check and the test suites read it from then on); then
   `scripts/apply-patches.ps1` installs the Python packages, puts the settings
   file in place and runs the tests. On the published folder it changes no
   code, because that folder is already the state after the patches (INSTALL.md
   part 1 has both exact commands, and the model command too).
2. **The desktop app** — built from this folder today: `npm install` and
   `npm run tauri build` in `jarvis-desktop/`, then run the installer it
   produces (INSTALL.md part 2). The update command above does this for you.
   **There is no published desktop installer yet** — the app's own
   Settings → Updates says "Not set up yet" until somebody makes the update
   signing key, which is about ten minutes and is written out in
   [`docs/INSTALL.md`](docs/INSTALL.md).
3. **The phone app** — download the `.apk` from the
   [`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest)
   and open it on the phone, or run
   `adb install -r jarvis-client-<commit>.apk` from the PC. Then pair it with
   the PC (INSTALL.md part 3) — the QR code, with a short typed code as
   backup, confirmed by an approval card on the PC. The phone reaches the PC
   only through Tailscale or NordVPN Meshnet, at home too.

> **Install only `jarvis-client`.** The `jarvis-android` folder is an older app
> kept for reference: it speaks a connection method the backend never had, so
> it cannot talk to Jarvis at all. It no longer publishes a download, so the
> two cannot be mixed up — installing the wrong one would look like "my phone
> is broken" rather than "wrong app".

If you are the first to take a fresh clone through the whole page, the page is
the place to report what it got wrong. Its **"Known rough edges"** section at
the end is the live list of what you will hit that is already known, rather
than your fault.

## Update it

**The backend and the desktop app together: one command.** Run it from the
folder you downloaded this into:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-jarvis.ps1
```

That is the whole update for those two. It works out which folder is the
backend, gets the newest code, closes Jarvis, patches the backend (through
`apply-patches.ps1`, unchanged), updates the desktop app, starts Jarvis again
and runs the live check. It is described under
[the quick way](#the-quick-way-two-commands) too. What it does **not** do: it
never approves anything for you, never installs an update on its own, and
never prints a token or a key.

- **You do not have to close Jarvis first.** It waits up to 90 seconds for you
  to close it (and says what to click), or closes it for you if you add
  `-Force` — which cuts off whatever Jarvis was doing at that moment.
- **`-Print`** prints exactly what it would do and changes nothing.
- **`-FromSource`** builds the desktop app from this folder instead of using a
  published installer.
- **`-SkipDesktop`** leaves the app alone; **`-SkipPatches`** leaves the
  backend alone; **`-SkipTests`** skips the test suites (quicker, and less
  proven — the patcher says so when it finishes); **`-NoCheck`** skips the
  live check at the end.
- Its own log lands in `_jarvis-logs` inside your backend folder, and
  `apply-patches.ps1` keeps its own log of what it changed. The patch script
  **keeps your settings file** and backs up everything it replaces.

**The phone app is separate.** Download the newest `.apk` from the
[`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest)
and install it over the old one. It stays paired: an update signed with the
same key keeps the app's data.

**Updating by hand instead:** stop Jarvis, then
`cd "$env:USERPROFILE\Epic-Jarvis"; git pull; powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "C:\path\to\your\backend"`,
then rebuild or reinstall the desktop app. INSTALL.md → "Updating everything"
has all four steps.

> **Not the same thing:** **Settings → Check for tool updates** looks up whether
> the Python packages Jarvis is built from have newer versions out, and shows
> you a command for each. It never installs anything. You do not need it to
> update Jarvis — the steps above *are* the update. A command it shows is a
> version nobody has tested with Jarvis yet, so leave it alone unless you know
> why you want it.

## Where things are

| Folder | What is in it |
|---|---|
| `jarvis-desktop/` | The Windows app (Tauri). Rust in `src-tauri/`, the windows in `src/`. |
| `jarvis-client/` | The Android app. **This is the one to install.** |
| `jarvis-backend/` | **The backend itself**, as plain source: a checked copy of the author's, 198 files, 190 of them Python. [`jarvis-backend/README.md`](jarvis-backend/README.md) says where it came from and what it is not. |
| `backend/` | Changes (patches) for the backend, the modules it needs, and a test for each. The patches are written against the author's own backend folder. [`backend/README.md`](backend/README.md) has the table. |
| `features/` | `features.json` — the one list of every feature both apps show, including what asks first and each feature's own limit. Its three copies are kept byte-identical by a checker. |
| `plugins/` | Drop-in modules: a feature whose only wiring was one startup call is a folder you add or take out, with no patch. [`docs/PLUG-AND-PLAY.md`](docs/PLUG-AND-PLAY.md) explains it. |
| `docs/` | How it all works. [`docs/README.md`](docs/README.md) says which documents are current. |
| `scripts/` | The install, update and patch scripts described above. |
| `tools/` | Generators for the test fixtures and the third-party notices, and the checkers CI runs. |
| `docker/` | The self-hosted SearXNG container — the default web-search provider, on this PC only. |
| `keystore/` | How the phone app's signing key is restored on GitHub's build machines. The key itself is never committed. |
| `contract/`, `tokens/` | The pairing word list, and the theme colour tokens both apps build from. |
| `videos/` | The launch videos' project files, so any version can be rendered again. |
| `scratchpad/` | Scratch measurements and research, not part of the app. |
| `jarvis-android/` | The older phone app, kept as source only. See the note in [Install it](#install-it). |
| `server/` | An old server, not used by Jarvis (its README says so). |

The documents to read first: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
(how the pieces fit, and the rules), [`docs/INSTALL.md`](docs/INSTALL.md)
(installing and updating), [`docs/JARVIS-API.md`](docs/JARVIS-API.md) (what the
apps ask the PC), [`CLAUDE.md`](CLAUDE.md) (the owner's decision log, including
the five rules), and [`backend/README.md`](backend/README.md) (what each
backend change fixes). For the graphics cards:
[`docs/MODEL-TOPOLOGY.md`](docs/MODEL-TOPOLOGY.md). For the faces:
[`docs/CRITTERS.md`](docs/CRITTERS.md).

## Honest limits

This project's habit is to say what is not done. One of its own architecture
rules is that **nothing is claimed that is not true**. The short list:

- **The desktop installer is not published yet.** Settings → Updates says
  "Not set up yet", and the desktop app has to be built from source until
  somebody makes the update signing key (about ten minutes, in
  [`docs/INSTALL.md`](docs/INSTALL.md)). The update command falls back to
  building it.
- **The second graphics card is installed and measured, but its features are
  not.** It offers seven switches (longer conversations, pictures, background
  learning, browser control, the wiki builder, the study helper, referee
  suggestions); **every one is off, and each needs its own approval card**.
  That includes the camera in Jarvis Live, which stays off until the card is
  in and a photo test passes.
- **Everyday chat has a small memory: about 4,096 tokens** of conversation.
  Longer talks get strange before they get long, and the bigger figures for
  what fits on each card are still worked out on paper — none of them is
  measured.
- **The wake word has not been tried on a real voice.** It was tested against
  made-up (synthesised) speech, 44 of 44 heard; what it does with a real
  person, a television or a phone's battery is unmeasured.
- **Some things are deliberately absent.** No always-on screen watching with a
  history (Recall-style). No phone calls for urgent alerts — a call would send
  private text to an outside voice company. No approve-all anywhere, and no
  control that clears the "text tried to rush you" warning. The phone does no
  speech-to-text, has no model catalogue to browse, and no deep config
  editing. Jarvis does not change Windows settings (Night light, dark mode,
  Focus Assist) — PC help only reads. The model's private reasoning is not
  shown, on purpose: it can quote your email and files.
- **Built, but never tried for real.** The chatbot website conversations, the
  chatbot API conversations, the comparison of several AIs, the
  customer-support chat and the hidden browser are each labelled "not yet
  tried for real" in the project's own notes. The job list says "nothing here
  has run on the owner's PC". The inbox tidy has been tried against a stand-in
  mail server, never a real mailbox. Nobody has listened to a v1.0 voice yet.
  The prompt coach and other newer pieces say in their own notes that nobody
  has measured how good their advice is.
- **The approval gap is narrowed, not closed.** The PC's own backend now asks
  Windows Hello for risky approvals, and stamps each real approval so a row
  written straight into the database does not count. A program written
  specifically to attack Jarvis can still get around it.
- **The updater's own log is not scrubbed.** `backend.log` is (passwords,
  keys and the pairing key are taken out), but `jarvis-desktop.log` is not, and
  neither catches everything — read one before sending it anywhere.
- **A token in Windows Credential Manager can still be read by any program
  running as you.** What changed is that it no longer sits on disk as readable
  text.
- **`Alt+Space` can lose the race at startup.** Every startup program asks for
  its shortcuts at once, so being present after a reboot is not the same as
  owning the key. The tray icon's "Show or hide the Jarvis bar" is the way in
  when that happens.
- **Do not run a downloaded OpenJarvis copy.** It writes into the same
  `%USERPROFILE%\.openjarvis\` folder as Jarvis.
- **`docs/INSTALL.md` → "Known rough edges"** is the fuller, live list. Read
  it before reporting a problem.

## Launch video

[![Jarvis launch video v6: your AI](videos/v6/jarvis-launch-v6.jpg)](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v6.mp4)

**Tap the picture to watch v6** (25.6 seconds, sound on; every line is on
screen). On a phone held upright, watch
[the upright cut](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v6-vertical.mp4)
(13.6 seconds).

A real AI model on your own PC, at work: it looks things up and shows its
sources, checks it is your voice first, stops when you say stop, lets you swap
its brain from your phone, and still asks first. Every desktop screen is the
real app, with made-up examples.

The ten rendered video files are kept in the
[**launch-videos release**](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/launch-videos)
rather than in the repository — the six numbered versions are the ones linked
below. Together they were 184 MB, and `videos/` was 67% of the repository
*then*. Git also keeps a whole new copy on every re-render, so the cost only
grows. Nothing was lost — each version's plan, composition brief and project
files stay in [`videos/`](videos/), so any of them can be rendered again:
[v1](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v1.mp4),
[v2](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v2.mp4),
[v3](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v3.mp4),
[v4](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v4.mp4),
[v5](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v5.mp4),
[v6](https://github.com/darknight11ish/Epic-Jarvis/releases/download/launch-videos/jarvis-launch-v6.mp4).

## How it is built

- **Phone app:** GitHub builds it. A build is published to `client-latest`
  only from `main`, and only after the tests passed **and** that exact file was
  installed on an Android emulator and started.
- **Desktop app:** built on Windows with `npm install` and `npm run tauri build`
  in `jarvis-desktop/`; GitHub also builds the installer once the update
  signing key exists.
- **Every change** runs the tests on GitHub: the backend suites (on Windows as
  well as Linux), every desktop page test, the Rust checks, the
  credential-manager checks, and PowerShell 5.1 running the patch script.

## Licence

Jarvis is MIT-licensed ([`LICENSE`](LICENSE)), copyright 2026 darknight11ish.
It is built with parts made by other people that keep their own licences,
including wake-word models that are for non-commercial use only: see
[`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt), and in the phone app,
FAQ → About → Third-party notices.
