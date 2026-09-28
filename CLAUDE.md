# Working with the owner of this repo

The desktop and Android sessions each kept their own copy of this file while
they worked on separate branches. This is the reconciled version, now that
both have merged into `main` — read this one, not an old copy on a deleted
branch.

## Keep multiple-choice questions SHORT

This is the rule that gets broken most. Asking four questions with four
paragraph-length options each is not a question, it is a document with radio
buttons. It makes a decision harder to make, not easier.

- **One or two questions at a time.** Three is a lot. Four is too many.
- **Two or three options each.** Not four.
- **One or two sentences per option.** Not a paragraph.
- **No jargon in the question itself.** If the question cannot be asked in
  plain words, explain the thing first in a sentence, then ask.
- Lead with the recommendation and say it is the recommendation.
- Put the long reasoning in the reply *around* the question, or in a document.
  Not inside the options.

Bad:

> Should the KV cache use q8_0 quantisation given that llama.cpp reaches the
> quantised path only through fused attention, and Ollama's `ml/device.go`
> gate admits compute capability 7.5 while excluding 7.2, which means…

Good:

> Jarvis can squeeze more conversation into the graphics card's memory by
> storing it in a smaller format. Slight risk it is not supported on your
> card, in which case things get much slower and nothing warns you.
>
> - **Do it, and check it worked** (recommended)
> - **Leave it alone**

## Explain things simply

The owner is a **beginner developer**. Write for someone who is smart and is
learning, not for someone who already knows the jargon.

- Say what a thing *is* before using its name. "R8 (the tool that shrinks the
  app)" beats "R8" on first mention.
- Prefer short sentences and plain words. "The app was slow because it was
  built in debug mode" beats "the debuggable variant disables ART AOT
  compilation".
- When something technical is unavoidable, explain it in one line and move on.
- **Say what to actually do**, concretely: which button, which file, which
  command, in order. Do not leave the next step implied.
- Do not assume knowledge of Gradle, Android build variants, CI, git internals,
  Rust, or Kotlin idioms.
- Lead with the answer. Put the reasoning after it, for anyone who wants it.

This is about clarity, not simplification of substance. Do not hide problems,
soften bad news, or skip caveats - explain them in plain words instead. If
something is broken, uncertain, or was my mistake, say so directly and early.

## What this project is

A local-first personal assistant. A Python backend on the owner's Windows 11
desktop, an 8B model in Ollama on the same machine, a Tauri 2 desktop shell
around it, and an Android companion reachable over Tailscale or NordVPN
Meshnet (both private device-to-device networks, never a public tunnel).

Hardware: an RTX 2080 Super (8 GB) today. **The owner is adding an RTX 2060
12 GB as a second card** - plan features with that second, larger-context
lane in mind, but do not switch anything on that depends on it until it is
installed and measured. `docs/MODEL-TOPOLOGY.md` has the numbers.

- `jarvis-desktop/` - the Tauri desktop app. Rust in `src-tauri/`, the windows
  in `src/`.
- `backend/` - patches against the Python backend, which lives outside this
  repo (`docs/ARCHITECTURE.md` §9 says where), plus tests that prove each
  patch works.
- `jarvis-client/` - the Android app (Jetpack Compose) that actually talks to
  the backend, over the real API (`docs/`'s `JARVIS-API.md`).
- `jarvis-android/` - an older Android app, kept for reference. It speaks a
  WebSocket protocol invented before `JARVIS-API.md` existed, and none of its
  endpoints exist on the backend, so it cannot talk to Jarvis at all. Its
  safe, self-contained parts (the approval widget, a quick-link widget) have
  already been adapted into `jarvis-client`; its duplex audio streaming was
  deliberately **not** ported, because `jarvis-client`'s own voice-print gate
  needs a complete recorded clip to check, and streaming would undermine
  that. See the module's own README before assuming anything else in it is
  safe to copy over verbatim.

## The five rules that are not negotiable

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

Also standing: do not build the model catalogue, the memory graph, or deep
config editing on the phone. A client must not do speech-to-text. Never build a
control that clears a rush latch or approves in bulk. Send
`X-Jarvis-Client: hud` on every request. Never log the token.

Amended by the owner on 2026-09-18: **switching the local model from the
phone is allowed** - between models the desktop already has, via
`/api/models/switch`, which raises an approval card like any other change.

Amended by the owner on 2026-09-20: **installing a model from the phone is
allowed too**, the same shape as switching - a typed model reference posted
to `/api/models/install`, tier `ask` on the server, raising an approval
card like any other change; nothing downloads until that card is approved.
What is still off the phone is *browsing*: there is no catalogue to scroll
or search, no list of what could be installed, only of what already is.
The owner types the name by hand, the same as at a terminal
(`ollama pull <ref>`) - see `BrainScreen.kt`'s `ModelsPlate` and
`JarvisRuntime.installModel`.

Amended by the owner on 2026-09-24: **Jarvis learns automatically by
default.** Facts about the owner and their projects, learned from the
owner's own words only (never from web pages, emails, documents, notes or
tool output), are saved without a per-fact yes, and every one is listed in
both apps with a Forget (it asks "are you sure?" first - the owner chose
to keep that question, 2026-09-24, because forgetting cannot be undone).
Sensitive topics (health, money, passwords
and account details, private details about other people) still wait for
the owner's yes, unless the owner turns on "Also remember sensitive topics
automatically", which is off by default. Turning either setting on raises
an approval card; turning it off is immediate. **Chat history, including
voice transcripts, is kept on the PC by default**, encrypted, with a switch
to turn it off. Background learning stays on by default.

Also decided 2026-09-24: an answer that uses a sensitive saved fact is
**kept on screen, not read aloud**, by default - even under "Read aloud"
for answers that use memories. A voice setting lets the owner allow it;
turning that on raises an approval card like the other voice settings.

Also decided 2026-09-24, after the safety research
(`docs/RESEARCH-2026-09-24.md`):
- **Note-writing waits for a yes after outside text.** In a turn where Jarvis
  has read an email, web page, file or other tool output (or the
  conversation is tainted, or the message was pasted or shared), writing to
  Obsidian, Logseq or Joplin raises an approval card. Other turns save notes
  straight away, as before.
- **Passwords, PINs, account numbers and ID numbers always wait for the
  owner's yes**, even with "Also remember sensitive topics automatically"
  on. That setting covers health, money and the other sensitive topics only.
- **"Erase the words" joins Forget.** Forget still hides a fact and keeps its
  history. A second action, "Erase the words", wipes the fact's text for
  good (and its search entry); only the dates stay, so the history shows
  that something was erased. It asks "are you sure?" first, like Forget.
- **Hands-free voice is as trusted as the talk button by default, with a
  setting to make it stricter** (owner, 2026-09-24). A voice setting
  "Hands-free ("Hey Jarvis")" offers: "Same as the talk button" (default)
  and "Only trust the talk button" - under the stricter choice, a turn
  started by "Hey Jarvis" cannot save facts without a card, and its memory,
  sensitive or private answers stay on screen. Choosing the stricter option
  is immediate; going back raises an approval card, like the other voice
  settings. The voice check's wording says plainly that it cannot tell a
  recording or a copy from the real voice.
- **Spoken questions get spoken-style answers, and speech starts at the
  first comma.** A voice turn tells the model its answer will be spoken
  (short first sentence, 1-3 sentences unless asked for more, no lists or
  markdown); typed turns are unchanged. Both apps start speaking at the
  first comma of an answer once the phrase is long enough.
- **Phone pairing by QR code, with a short typed code as the backup**,
  confirmed by an approval card on the PC before any key is handed over.
  Built together with per-device keys (task "more devices"), since both
  change how a device gets its key.

Decided 2026-09-25, after the competitiveness audit
(`docs/RESEARCH-2026-09-24.md` and the audit reports):
- **Timers, reminders and one shared scheduler come first** in the queue.
  The any-GPU presets, Docker, model advice and mouse control wait. Build
  ONE scheduler (the initiative engine and digest) and reuse it for
  briefings, sleep mode and the overnight tidy - not one per feature.
- **A plain timer or a one-time reminder needs no approval card; anything
  that repeats ("every weekday at 7") asks once with a card**, and that
  card lists the next run times. Simple commands like timers are answered
  without the AI model, so they keep working when the model is slow,
  unloaded or asleep.
- On the desktop, while App lock is on, the approval widget shows only a
  short title and its Approve opens the locked app; the HUD is locked too.
  On the phone, screenshots are blocked while App lock or "Hide memory lists
  and chat history" is on.
- **Plain `http://` (unscrambled) to Home Assistant or the calendar is
  allowed only inside the owner's own networks:** this PC, the home network
  (private addresses such as 192.168.x.x and 10.x.x.x, and `.local` names),
  Tailscale and NordVPN Meshnet (both encrypt the traffic themselves). It is
  refused to anything on the open internet.
- **The "I heard you" sound gets a switch in both apps, off by default**,
  next to the "One moment" switch (the owner changed on to off, 2026-09-25).
- **The standby schedule wakes Jarvis only if the schedule put it on
  standby.** Standby switched on by hand stays on at the end of the hours.
- **The morning briefing shows new emails' count AND senders by default**,
  with a setting in both apps to show the count only.
- **Web search with a choice of five providers, SearXNG the default,** in
  this order: SearXNG (self-hosted, in Docker, on this PC only), DuckDuckGo
  (the `ddgs` library, DuckDuckGo backend only), Exa and Tavily (free keys,
  no payment card), and Brave (a key and a payment card that is charged past
  the $5 monthly credit - the owner removed it, then asked for it back the
  same day, 2026-09-25; its line says plainly that it can cost money). Keys
  follow rule 3. Each has a short "why use this one" line in both apps, and
  Jarvis can explain the choice. Left out, and the list says why: Whoogle
  (it stopped returning results in 2025). No silent fallback: if the chosen
  provider is down, Jarvis says so and offers to switch.
- **When a search asks first:** by default only when private things could
  slip in - a card showing the exact search words if the conversation has
  read email, files, notes or saved memories; no card for a search that
  comes straight from the owner's question. A setting makes it ask every
  time.
- **Jarvis may read Google Calendar through its private link** ("Secret
  address in iCal format"): read-only, set on the PC only, and the link
  kept as safely as a password (never logged, shown or sent anywhere but
  Google).

Decided 2026-09-25, after the audit against Meta's Muse
(`docs/COMPETITORS-MUSE-2026-09-25.md`):
- **Jarvis may SEND email, one approval card per email**, the card showing
  the exact recipients, subject and full text; never an "always allow", and
  the card says plainly when the conversation has read outside text. Sending
  is a new named way out of the PC (ARCHITECTURE section 4), like the others.
- **Close the approval gap later:** today the Windows fingerprint/PIN check
  for risky approvals lives in the desktop app, so a program already on the
  PC could approve by calling the backend directly with the pairing token.
  The owner chose to have the backend itself require that check for risky
  approvals - a later piece of work; until then it is written down as a
  known limit (ARCHITECTURE section 3).
- **Build step 1 of the approval-gap design now** (`docs/APPROVAL-GAP-DESIGN.md`,
  owner 2026-09-25): the PC's backend itself asks Windows Hello before
  accepting a risky approval that comes from the PC, stamps each real
  approval so an "approved" written straight into the database does not
  count, and the desktop stops asking separately so the owner is asked once.
  It narrows the gap; a program written specifically to attack Jarvis can
  still get around it, and the docs say so. The phone half (a Keystore key
  that needs a fresh fingerprint per risky approval) comes with "more
  devices".
- **No lock, no risky approval:** on a PC without Windows Hello set up, or a
  phone without a screen lock, a risky approval is refused until one is set
  up, with a plain message saying how (owner, 2026-09-25).

Decided 2026-09-25, after the creativity audit
(`docs/CREATIVITY-AUDIT-2026-09-25.md`):
- **Web search asks first only when the search words would repeat a saved
  fact, or a sensitive fact was used** - no longer whenever any memory
  (a pinned fact, a recalled one) was part of the question. After outside
  text, and with "Ask before every web search" on, it still asks as before.
- **One smart-home card may cover several named devices**, every one listed
  in full on the card (e.g. "turn off the kitchen, hall and bedroom
  lights"). Locks, alarms, doors and covers always get a card of their own.
  It is one decision about a fully listed set - never a standing permission.
- **Jarvis's manner: warm and brief by default, with a "Plain" option** in
  both apps' settings (plain, businesslike answers). Manner never changes
  what Jarvis does, asks or remembers - only how it phrases things.

Decided 2026-09-25, after reviewing the "Build Your Own Jarvis" prompt pack
and video (owner chose: build four ideas now):
- **A live preflight check** on the PC: every real chain tested end to end,
  "N pass, N fail, N warn", one new check per real incident.
- **A "stop everything" hotkey** on the desktop that halts any action Jarvis
  is taking on the screen at once.
- **Urgent alerts without phone calls:** "tell me when ..." (a named sender's
  email, a device change) set up with one card; a match only notifies -
  urgent ones as a phone notification that keeps ringing until seen. No
  telephony service: a call would send private text to an outside voice
  company (rule 1).
- **Focus sessions**, off unless started: a timer plus Quiet; Jarvis watches
  which app/site is in front ON THE PC ONLY, names the distraction out loud
  ("Instagram can wait") but never stores what it saw (only counts), waits
  until the owner settles before locking on, and ends with a report card.
  Snooze, "I'm doing research", pause and stop by voice. Nothing leaves the PC.

Decided 2026-09-26, after checking a Gemini audit finding:
- **The apps accept a server address on the owner's own networks only:**
  this PC, the home network (private addresses and `.local` names),
  Tailscale and NordVPN Meshnet. Anything on the open internet - including
  a public tunnel such as ngrok or Cloudflare - is refused with a plain
  message saying why, so the pairing key never travels through one.
  While a refused address is saved, the desktop does nothing over the
  network - no chat, no reads - until an allowed address is entered; it
  does not quietly fall back to this PC (owner, 2026-09-26).

Decided 2026-09-26, after the approvals audit
(`docs/APPROVALS-AUDIT-2026-09-26.md`) - small, low-risk things stop asking:
- **Plain repeating reminders, alarms and the standby schedule need no
  card.** Only the owner's own words can set one, and deleting is instant.
  The morning briefing and "tell me when" keep their one card (they read
  email or the calendar). This replaces "anything that repeats asks once"
  for those three kinds.
- **Lights, plugs and fans: a setting, off by default,** lets Jarvis switch
  devices the owner names without a card. Turning it on raises a card;
  turning it off is immediate. Never after outside text in the turn. Locks,
  doors, alarms and covers always keep a card of their own.
- **Everyday facts about people the owner mentions save automatically**
  ("my sister likes jazz"). Their health, money, address and contact
  details, and passwords/PINs/account/ID numbers, still wait for a yes.
- **A "What asks first" page in both apps** lists every action and whether
  it asks, in plain words, with "make stricter" switches. On the PC only,
  the owner may also loosen a short safe list (note writes, the wiki,
  reading their own calendar, email, notes and home status) - one card plus
  Windows Hello per change. Nothing outside that list can be loosened from
  an app.

Decided 2026-09-26, after the professionalism audit
(`docs/PROFESSIONALISM-AUDIT-2026-09-26.md`):
- **The maker's name is the owner's GitHub name, "darknight11ish"** - as
  publisher, copyright holder and in the licence - not "Jarvis Labs" (a real
  company uses that name).
- **Bring GitHub's `main` up to date with one pull request, once the bug
  audit's fixes have landed.** The owner presses Merge on GitHub.

Decided 2026-09-26, after the bug audit (`docs/BUG-AUDIT-2026-09-26-*.md`):
- **App lock covers task notes too**, like approval notes: with App lock on,
  adding a note to a running task needs the app unlocked first.
- **A late alarm rings only if it is at most 10 minutes late.** If the phone
  (or the PC app) hears about an alarm or reminder later than that - it was
  out of reach, or restarted - it shows a silent notification saying when
  it was missed, instead of ringing as if it were happening now.

Decided 2026-09-26, after the memory research
(`docs/MEMORY-RESEARCH-2026-09-26.md`):
- **Build memory ideas 1-4 first, each measured by the memory self-test:**
  a re-ranker over the top ~20 facts, a bigger self-test, "said again"
  counts, and real "true from" dates (older news never replaces newer).
  **Then the overnight tidy** - cards only, never changing memory by itself.
- **Searching the owner's own past chat words waits** until 1-4 are built
  and measured; it changes a written rule (ARCHITECTURE section 5).

Decided 2026-09-26, after the approvals build:
- **The screen is called "Brain" in both apps** (the phone's "Mind" is
  renamed to match the PC).
- **Everyday facts about people are treated as normal everywhere**, not
  only when saving: they may be read aloud and do not make a web search ask
  first. Their health, money, address, contact details, debts and secrets
  stay sensitive everywhere.

Decided 2026-09-26, after the cutting-edge research
(`docs/CUTTING-EDGE-2026-09-26-*.md`) - build all four groups, after the
current fix pass, and keep researching:
- **Quick wins:** briefing weather from the owner's own Home Assistant;
  "Also on my phone" (hand an alarm or event to the phone's own apps by the
  owner's tap); reading the text in a screenshot on the PC (marked as
  outside text).
- **Smarter tools:** a short tool list with more on request, "ask, don't
  guess" and multi-step tool tests, then the MCP bridge (local servers only,
  read-only first, a card to start each server, every call through the
  gate).
- **Voice upgrades:** a newer "Hey Jarvis" detector and a fast voice-copying
  voice, each measured before it replaces anything.
- **Documents & email:** asking about PDFs and Word files, instant "tell me
  when" for email, saving drafts to the owner's Drafts folder.
Also fixed without asking: a model that cannot use tools gets a true error
message, and `OLLAMA_NO_CLOUD=1` as a second lock behind rule 1.

Decided 2026-09-26: **reading phone notifications is added as an option**
(queued after the four cutting-edge groups and the security audit). The
safe version only: off by default, turning it on raises an approval card,
turning it off is immediate; only apps the owner chooses (never banking);
one-time codes hidden before anything reaches the model; treated as
outside text - never makes Jarvis act and is never saved as a fact; shown
or summarised only when the owner asks; nothing leaves the owner's own
devices. Never text messages (SMS), and Jarvis never replies or sends.

Decided 2026-09-26, when the owner asked for memory and learning to be
"really refined":
- **Memory and learning run now, alongside the four groups** - not after
  them. Every memory or learning change must beat the memory self-test
  (`backend/eval_memory.py`) and the learner test (`backend/eval_learner.py`)
  before it is kept; a change that makes a number worse is not kept.
  Numbers from the real model come from the owner's PC (one PowerShell
  line), and are written on a memory scoreboard page after each change.
  A dedicated memory review team follows ideas 1-4.
- **"Bring in my Notion export"** joins the Documents & email group: the
  export (Markdown pages and CSV tables) goes into a folder Jarvis searches,
  then the owner can ask about it or have it tidied. Imported notes are
  outside text: they are never learned as facts, and every note Jarvis
  writes back after reading them asks first, as for any note.

Decided 2026-09-27, the owner's answers to `docs/OWNER-QUESTIONS-2026-09-27.md`
(after the feasibility, UI, memory and ease-of-use audits):
- **Email drafts: a card every time**, showing the full draft, before any
  text goes to the owner's Drafts folder.
- **Plug-in programs (MCP): programs on this PC only** (the owner had no
  preference; the built, stricter version stays). A card when a plug-in is
  added and again when its program or version changes; each start is logged.
- **Backups: one locked backup file into a folder the owner picks, a
  NordLocker (or other cloud-synced) folder included.** Locked with a
  recovery code only the owner has (shown once); Jarvis keeps only the last
  few. This bends rule 1 for that one locked file only; the app must say
  plainly that a lost code means a useless backup and that erased facts stay
  in older backups until they age out.
- **The feasibility audit's 31 small items are queued after the four groups.**
- **Build the UI audit's "do first" list.** The HUD window uses the app's
  theme colours; the widget's Approve button matches the Jarvis bar's; the
  phone keeps its own font everywhere.
- **Memory:** "Erase the words" also offers "Also delete the chat it came
  from"; the re-ranker may also drop weak facts, but only if the PC's
  self-test shows it helps.
- **Web search ships switched on** (with the existing asks-first rules).
- **A read-only list of past approvals** (title, Approved / Denied / Timed
  out, when, which device) - after reading the owner's `jarvis_gate.py`.
- **Reading tools (calendar, email, notes, home status) can be switched on
  from the PC app**, each with a card plus Windows Hello; other tools stay in
  the settings file.
- **A search box in History for the owner's own old chats is allowed now**
  (shown on screen only; nothing saved, nothing handed to the AI).
- **Crisis help line: United States - 988 (Suicide & Crisis Lifeline) and
  911.** Crisis messages are never learned from and never counted.
- **The plan card is allowed later**, only after the multi-step safety tests
  pass; risky steps still get their own card.
- **"From now on, ..." style requests apply at once, with Undo, no card.**
- **Phone: allow home-network addresses** (private addresses and `.local`)
  as the 2026-09-26 own-networks decision says; never the open internet.
- **Focus report card: drop the streak line.**
- **12 GB card:** longer conversations with picture understanding first, and
  making pictures too (swapped in when asked, since both cannot sit on the
  card at once) - decided in detail after the card is measured.
- **Music/video control on the PC: no card**, only from the owner's own words.
- **Smartwatch: every notification stays on the phone by default**, with a
  setting to let them all show on a compatible watch (turning it on raises a
  card, turning it off is instant).
- **News headlines and "tell me when this page changes": yes, the safe
  version** - one card per address the owner adds, read-only, never follows
  links elsewhere, never acts on what it reads, outside text; queued with
  the small items.
- **Games and role-play run in a temporary chat automatically.**
- **Inside jokes: yes**, a "between us" list in Brain with Forget, from the
  owner's own words only.
- **Humour: a switch in "How Jarvis talks", off to start**; never on cards,
  errors or serious topics.

Decided 2026-09-27, the owner's answers to the cross-cutting/backend audits'
own "owner's call" findings:
- **A crisis turn is excluded from the "suggest the bigger model" counters
  too** - the same "never counted" rule already covers memory and learning;
  it now covers this in-memory signal as well.
- **The phone and desktop "open a chat" phrase lists are unified** into one
  shared source both sides check, so the two can no longer quietly drift
  apart (`net/OpenChatPhrase.kt` and `jarvis_quick.py`'s `_OPEN_CHAT` used
  to be two separately-maintained lists).
- **"Floating Jarvis"'s Bubble mode gets the Android conversation shortcut
  it needs** - without one, Android 11+ silently never shows it as a
  bubble at all, even with the setting on. **Not the whole fix**, an Opus
  5.5 re-check found (2026-09-27): Android's own conversation requirement
  also needs `NotificationCompat.MessagingStyle`, which this notification
  still does not use - so a bubble may still not appear until that second,
  larger piece (a real redesign of what the notification looks like, on or
  off Bubble mode) is also done. Try it on a real phone before trusting it.
- **App lock matches on both apps for the floating face/avatar**: neither
  is hidden or blanked while locked - matching the desktop's original
  behaviour, which already showed link, approval and error state while
  locked. The phone's avatar used to go neutral instead; it now shows the
  same connectivity/listening state regardless of App lock, same as the
  desktop always did.

Opus 5.5 re-check, 2026-09-27, of the fixes above and the CI-failure fixes
alongside them - six small, real findings, all fixed except two written down
here rather than patched blind:
- Fixed: the Settings hotkey row for a key Jarvis itself blanked (a default
  clash, not another program) said "in use by another app" - the exact wrong
  blame finding #7 already fixed in the startup toast, missed on this row.
- Fixed: a toggle in "Your second graphics card" whose re-read failed left
  its one-shot focus-restore marker set, so a later, unrelated successful
  repaint could yank keyboard focus back to that switch from wherever the
  owner had moved on to.
- Fixed: the correction-phrase check's anchor (finding #9's fix, above)
  only spared a leading "no," - "Jarvis, that's wrong", "nope, that's
  wrong", "hmm, that's not right" and "actually it's wrong" had quietly
  stopped counting as corrections. Widened; the doctor/landlord false
  positives finding #9 was written for stay fixed.
- Fixed: the Bubble-mode shortcut push discarded a real success/failure
  answer behind a hardcoded `true` - an earlier note here that the call
  "returns Unit" was wrong.
- Fixed: the phone/desktop "open a chat" phrase-list test (above) only ever
  checked the fixture against the app, never the app against the fixture -
  a phrase added straight to the phone's list, in neither direction, would
  have passed silently.
- **Written down, not fixed:** marking a crisis answer "wrong" (the thumbs-
  down button) still counts toward "suggest the bigger model" - the crisis
  exclusion above only covers the live phrase-based signal and the
  struggle count. Fixing it needs the turn's crisis flag and its id joined
  across two separate patches (`chat-stream.patch`, which has the flag, and
  `second-card-suggest.patch`, which has the id) - mechanical, but not done
  without the owner's go-ahead given how carefully this project already
  treats crisis handling.

Built 2026-09-27, the owner's "yes, build it now" - the router's cloud-offer
gate (`jarvis_router.choose()`'s `owner_said_yes`, live since 2026-09-24) had
no way for either app to actually say yes:

- **"Try the cloud model", one tap, one question, never a standing choice.**
  An answer whose route says `gate: "offer"` (a cloud lane that could answer
  this, named but not used) now shows that button beside "Not now" in both
  apps' chat screens, in the same fixed wording word for word
  (`jarvis-desktop/src/index.html`/`main.js`, the phone's
  `net/CloudOffer.kt`/`HomeScreen.kt`). Pressing it resends the exact same
  question with `cloud_yes: true` (`backend/cloud-say-yes.patch`,
  `docs/JARVIS-API.md` §18.1) - nothing else from the conversation goes with
  it, and every gate that would have refused escalation outright (private,
  tainted, a picture, no lane, no budget) already ran on this question's own
  merits before the offer was ever made. "Not now" just dismisses it.
- **Left off the desktop's separate widget on purpose**, not by oversight:
  `widget.html`/`widget.js` never render a chat answer's own text or route
  at all today, so there is nothing on that screen for an offer to attach
  to (`docs/ARCHITECTURE.md` §8, "One-sided on purpose").
- Verified: `backend/test_cloud_say_yes.py` (new), the phone's
  `net/CloudOfferTest.kt` (new), the desktop's `tests/cloud-offer.mjs` (new)
  - and, since the router call site had never been touched by any patch
  before, the backend patch was written and checked against the owner's own
  real `jarvis_hud.py` lines rather than guessed, per "Do not claim more
  than the evidence supports" above.
- **Antigravity / Google-account cloud access** (the same request that
  prompted this): researched, not built - the owner chose "not sure yet,
  research it properly first" for its role (a second cloud lane beside
  this one, or a replacement for API-key cloud access). Still an open
  decision for the owner, not a "later" already committed to.

Built 2026-09-27, the owner's "build it now" after the Jarvis evaluation
(`docs/JARVIS-EVALUATION-2026-09-27.md`) surfaced it as the biggest real gap
against Meta's Muse still on the table - **Goals: a plan the owner edits,
one card per acting step** (`docs/creativity-2026-09-25/future.md` idea 3;
the feasibility audit's I63/I64; `docs/JARVIS-API.md` §59).

- The owner says "insulate the garage before winter", writes or asks
  Jarvis (in ordinary chat) to suggest a short plan, edits and accepts it.
  Accepting sets up a weekly, model-free check-in - the same ONE
  `schedule_repeat` card a repeating reminder already raises, approving
  nothing that acts. Ticking a step off, and Stop tracking, need no card
  and are immediate, like a to-do item. Every acting step (search
  installers, draft an email) is asked for in ordinary chat and goes
  through the exact same per-action card chat already uses - Goals adds no
  new way to act, ever.
- **This is NOT "the plan card"** (feasibility I61, gated behind the
  multi-step safety tests that have not run yet) - a mix-up this session's
  own evaluation made once before catching it. The plan card batches
  several safe steps under one yes; Goals never batches anything, so it
  never touched that gate and was not waiting on it. `jarvis_goals.py`'s
  own docstring exists partly so this does not get confused a third time.
- Deliberately calls no model itself: the real way this backend reaches a
  local model is inside `jarvis_hud.py`, which is not in this repository,
  and guessing at that integration rather than verifying it would be
  exactly what "do not claim more than the evidence supports" (above)
  warns against. Drafting a plan happens in ordinary chat instead, already
  built and already safe.
- **Where the weekly check-in shows**: the backend registers it
  `owner_listed=True`, its own default, so it already appears on Coming
  up like any other repeating job (a reminder, the morning briefing).
  Neither app's Goals section carves out a private channel for it - each
  reads that SAME list for the check-in's live state (waiting for the
  card, paused, its next-run note), rather than inventing a second source
  of truth for one job; Coming up itself offers it no Pause/Delete
  (`Schedule.actionsOf` on the phone), since only Stop tracking, on the
  goal, can take the check-in down cleanly. Consistent with how the
  briefing's and the standby schedule's own jobs already work.
- **All three surfaces are built**: backend (`backend/jarvis_goals.py`,
  `goals.patch`, `test_goals.py`, 57 checks), the phone
  (`net/Goals.kt`, `ui/screens/GoalsPlate.kt`, Brain -> Goals), and the
  desktop (`jarvis-desktop/src/goals.js`, `brain.js`,
  `src-tauri/src/brain/goals.rs`, Brain -> Work -> Goals) - each beside its
  own app's "Coming up". `tools/check_parity.py` is clean.

Built 2026-09-28, the owner's own words: "add the ability for jarvis to
request a multi-step process that it does on its own, and it sends me a
detailed approval card that I only give to approve once. Really refine
this" - **"one card, several steps", the plan card itself** (feasibility
I61; `docs/JARVIS-API.md` §60), the mechanism the Goals entry above was
careful to say it was NOT. Asked plainly first whether building this now
conflicted with the owner's own 2026-09-27 decision to gate it behind the
multi-step safety tests - it does not conflict, since those tests have not
run, so **built fully, switched off**, the owner's own recommended choice:

- `backend/jarvis_plan.py` (whole module) + `plan-gate.patch` (two
  append-only hunks against `jarvis_gate.py`, both verified with
  `_stack.py` against real, already-covered context - this call site,
  unlike `cloud-say-yes.patch`'s, had prior patches touching it, so no
  hand-verification against the owner's real file was needed this time).
  `test_plan.py`, 72 checks. Stricter than `jarvis_ui_control.py`'s own
  "one card, several steps": a risky or result-filled step always asks
  again on its own separate card, mid-run, even inside an already-approved
  plan - only the safe steps run on the strength of the one card that
  started things. Refuses outright on outside text.
- `jarvis_plan.enabled()` is the safety gate itself, measured not
  promised: it reads `tools/tool_eval/tool_eval_results.json` and says yes
  only once a real run, for the real model, clears two bars (90% on the
  multi-step suite, zero carried planted instructions on the injection
  suite) - the same "measured before switched on" rule the memory
  re-ranker already follows. No file yet, so nothing is unlocked yet.
- **Not yet wired as a model-callable tool** in `jarvis_agent.py`'s
  `TOOLS` table - found and confirmed the exact three pieces that need it
  (a `Tool` entry, an outright-refusal check reusing `_TurnWatch.tainted`
  at the real, verified call site, and a `run_step` dispatcher reusing
  `Tool.prepare`/`.execute`'s own documented contract), and left the actual
  wiring for a following pass rather than rush it into the one file this
  project is most careful about - the feature is switched off regardless,
  so nothing is lost by finishing it correctly next instead of quickly now.
- No UI in either app yet - once wired in as a tool, its card needs no new
  shape, only the ordinary approval flow both apps already have.

Built 2026-09-28, after `docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` (the
owner asked for a third NVIDIA graphics card, end to end) - **the data-model
reshape only (that research's own recommendation #1), not the third card's
own feature.** What the research found: `jarvis_second_card.py`'s detection
already picked exactly one "second" card out of however many capable extra
cards were actually plugged in, and threw the rest away with "capable, but
the [other] card has more memory" - a real third card sat right there,
detected, and was silently discarded. Building a third card's own lane
(which of the five features runs on it, its own approval card, a UI row in
both apps - none of which exist today) in the SAME pass as reshaping how
cards are detected risked exactly what this module's own tests exist to
catch: a change to the shape `jarvis_agent.choose_lane()` trusts to route
the model's own tool calls, made and checked in one large, hard-to-verify
step. So this pass built the safety-critical half alone, fully tested, and
stopped there on purpose - the conservative choice the research itself
recommended (its "L, do the S-sized reshape first" advice).

- **What changed:** `jarvis_second_card.detect()` now keeps every capable
  non-primary card internally, not just the biggest, as `det["_lanes"]`
  (best memory first - "second" is unchanged, it is still `_lanes[0]`), and
  a new function, `extra_lanes(det)`, turns every card beyond that into
  `det["second"]`'s own plain-dict shape - so a third capable card is now
  visible to Python code as data, not only as a "why" sentence. Both are
  internal (never returned by `status()`, never in the `GET
  /api/second-card` JSON) - **on a PC with any number of cards, the route,
  both apps and every existing test behave exactly as they did before this
  change.** `test_second_card.py` gained tests for 0/1/2/3-card detection
  (including a genuinely incapable third card, correctly excluded and
  explained) and proves the 2-card case's public output is untouched.
- **What is deliberately NOT built:** a third card cannot run anything yet.
  There is no third lane process, no approval action for "which feature
  goes on which card" (docs/GPU-SUPPORT-RESEARCH-2026-09-27.md §1.3 is
  explicit this must be a real, named choice - never a "biggest card wins"
  default, the same "no approve-all" rule every switch here already
  follows), and no UI in either app (each renders exactly one "second card"
  row today). None of `_wanted`, `_reconcile`, `lane_for`, `_LANE` or
  `describe_on` (the approval card's own words) were touched - so nothing
  about how the model's tool calls get routed could have moved. "Combined"
  (one bigger model split across cards) stays two-card-only, for the same
  reason its own real speed is still unmeasured on two cards: the second
  card is not installed yet, so adding a third untested unknown on top of a
  first untested one is not a decision to make silently.
  `jarvis_hardware.py`'s preset system also stays two-slot, unchanged -
  presets were designed and tested for exactly one extra lane card.
- **This is a known, written-down gap, not an oversight:** a real "build
  the third card's own lane, its approval card and both apps' UI" pass is
  still queued, on top of the shape this one now provides. Until then, a
  third capable NVIDIA card in the PC is detected and correctly explained
  ("capable, but the [other] card has more memory") but does nothing.

Built 2026-09-28, closing the queued gap the entry right above this one
left on purpose - **a third graphics card can now actually be used.** A
quick reminder of the two things in a graphics card that matter here:
memory (how much a model can fit) and compute capability (how new its
design is - old cards cannot use the compact conversation format Jarvis
needs). A third card that has enough of both can now be given one of the
five second-card features (Longer conversations, Pictures, Learning in the
background, Browser control, Wiki builder), running there at the same time
as the second card's own feature - never instead of it, and never chosen
by Jarvis on its own.

- **Never a default, always a named choice** - the one rule
  `docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` §1.3 was most insistent about.
  A capable third card sitting in the PC does nothing on its own, exactly
  like the second card did nothing until the owner turned a switch on.
  Moving a switch there raises its own approval card
  (`second_card_third_assign`, tier "ask"), naming the exact card, its
  model and how much memory it uses - never reusing `second_card_enable`'s
  own card, because that one never says WHICH card, and this decision is
  entirely about that. Moving a switch back to "Not used" is immediate,
  like turning any switch off.
- **Built in both apps**: Settings → "Second graphics card" (desktop) and
  Brain (phone) each show a new "Third graphics card" section, the exact
  same visual and wording pattern the five switches and "One bigger model
  on both cards" already use - a list of the switches that are currently
  on, pick one to move it there. `tools/check_parity.py` is clean; no new
  route was needed (`POST /api/second-card` already carried the shape,
  now with `{"feature": "third", "assign": "<switch>" | null}` alongside
  its existing bodies).
- **How it runs, underneath:** a third, separate copy of Ollama
  (`_THIRD_LANE` in `jarvis_second_card.py`), its own port and its own log
  file, because - unlike "One bigger model on both cards", which never
  runs at the same time as a feature switch - the third card's copy runs
  AT THE SAME TIME as the second card's own copy, one feature on each.
  Considered, and decided against on purpose: turning the two existing
  lane-process singletons (`_LANE`, `_COMBINED_LANE`) into a more general
  "however many lanes exist" structure, the more obviously "correct" shape
  for a future fourth card. Chosen instead: a third, plainly-named
  singleton, matching the existing two - explained in
  `jarvis_second_card.py`'s own module docstring, because touching the
  two existing, already-carefully-tested lane singletons in the same pass
  that adds a third was judged the riskier move for a module this
  safety-critical (it decides which physical card the model's own tool
  calls run on), with no real fourth card on the horizon to justify it yet.
  If a fourth card ever becomes a real prospect, that is the moment for
  the more general shape - informed by how the third one's own design
  actually held up, not guessed now.
- **"One bigger model on both cards" stays two-card-only**, on purpose,
  for the same reason the entry above already gives: real speed splitting
  one model across even two cards is still unmeasured, since the second
  card is not installed. A third untested unknown on top of a first is not
  a decision to make silently, so that switch still only ever reads the
  everyday and second cards - a third capable card is automatically left
  out of it, without any code change.
- **Verified**: `backend/test_second_card.py` (new tests: a capable third
  card doing nothing until named; the approval flow's assign/unassign/
  pending/denied/withdrawn/refused paths; the second and third lanes
  running independently, on different ports, at the same time),
  `backend/test_phone_second_card_contract.py`, `backend/test_hardware.py`,
  `backend/test_asks_first.py`, `backend/test_card_words.py`,
  `backend/test_gate_denial_rule.py`, `backend/test_wiki.py` (a knock-on
  patch-context shift), `backend/test_patch_history.py` (after running
  `tools/build_patch_history.py`, which every patch edit needs) - all
  passing. The desktop's Rust (`cargo fmt`/`check`/`clippy` against the
  Windows target, per this file's own "Checking the Rust" section) is
  clean; `cargo test` itself still needs a Windows host, so the new Rust
  unit tests are written and known to compile, not run here.
  `jarvis-desktop/tests/second-card.mjs` gained real checks for the new
  section, but this container cannot download the Chromium build
  Playwright needs (blocked by network policy) - they are unexecuted, and
  need a run on a machine that can reach it before they are trusted.
  The phone's Kotlin (`net/SecondCard.kt`, `ui/screens/SecondCardPlate.kt`,
  `JarvisRuntime.kt`, `net/JarvisApi.kt`, `MainActivity.kt`,
  `SecondCardContractTest.kt`) is read carefully by eye, following this
  file's own "How the Android apps get built" section (no local Android
  build here); it is confirmed only once CI compiles it.

Built 2026-09-28, the owner's "view the models... without having Jarvis up
and running" request - **Brain → Model remembers its last list on both
apps** (`docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`), a client-side cache
only, no new backend route:

- Each app keeps its own last successful `GET /api/models` read on disk -
  the desktop in `localStorage` (`models-cache.js`), the phone in
  `ModelsCacheStore` (`net/ModelsCache.kt`) - holding only what is honestly
  still true once written: the installed list, each model's size and
  family, and the last-known current/previous model. `speed` and `offload`
  are stripped before the write, never merely hidden after, since those are
  facts about what Ollama is doing right now, not about a file on disk.
- When a live read then fails outright, Brain → Model shows that cache
  instead of going blank, with a plain, clearly-labelled banner naming the
  real time it is from and hiding the live-only lines (the model-in-use
  highlight, on/off-card note, recent-speed lines) rather than showing them
  stale. A backend that explicitly has no models module is shown as that
  fact, never as the cache. A device that has never once read successfully,
  with nothing cached either, says plainly there is nothing to show yet.
  Use/Install/Roll back stay visible but dimmed by the same live-link
  greying both apps already had (rule 4) - no new visual state invented.
- **This is not a model catalogue**, on either app: it only ever replays
  what that same device already showed live at some point, never anything
  fetched specially for the offline case, and never anything the phone
  could browse (the standing "no model catalogue on the phone" rule).
- Built as two worktree agents that, like the Goals feature before them,
  each turned out to have branched from `origin/main` rather than this
  branch - caught and reconciled by hand rather than trusting a plain
  `git merge` (which would have pulled in unrelated main-only history).
  Verified: the desktop's `tests/models-cache.mjs` (new) plus the existing
  `.mjs` suite for files it touched; the phone's `ModelsCacheTest.kt`
  (new) - Kotlin compilation itself is unverified here (no local Android
  build; the "How the Android apps get built" section above), so it is
  confirmed only once CI runs. `tools/check_parity.py`: no undecided drift
  (no route changed either way).

Built 2026-09-28, the following pass the 2026-09-28 plan-card entry above
itself asked for: **the plan card is now wired into `jarvis_agent.py`'s
`TOOLS` table**, as `propose_plan` - the three pieces that entry found and
confirmed but deliberately left for next, now actually built. **The
feature is still switched off for everyone, exactly as before**: nothing
about wiring it in unlocks it - `jarvis_plan.enabled()` still has to read a
real, run, passing `tools/tool_eval/tool_eval_results.json` before
`propose_plan` does anything at all, and no such file ships in this
repository or on the owner's PC yet.

- `propose_plan` is one tool (not two): its `gate_lookup_name` resolves to
  the gate action `run_plan` (tier `ask`), the same way `control_computer`'s
  model-facing name already differs from its own gate key. Before
  `Tool.prepare()` - `jarvis_plan.propose()` - ever runs, `_one_call`
  refuses outright, at the same point `send_email`/`draft_email` already
  do: first `jarvis_plan.enabled()`, then the same four signals
  `note_needs_a_person()` already treats as "not really the owner's own
  words right now" (read something this turn, the conversation is
  tainted, the newest message was not typed or said, the app added its
  own context), folded into the one `tainted` flag `propose()` itself
  checks.
- **The real find of this pass**: `jarvis_plan.run()` only asks its given
  `gate_check` for a step the MODEL itself flagged `risky` or gave a
  `from_step` - a step it did not flag goes straight to `run_step`, with
  no separate gate_check call at all. Trusting that self-report alone
  would have let a step the model happened to call "safe" run an
  "ask"-tier tool with nobody really asked. So the wiring's own dispatcher
  (`_plan_step_dispatch`) does the REAL per-tool gate check - the same
  `check_call()`, `Tool.prepare()`, `jarvis_gate.action_for_tool()` lookup
  and `checker()` call a direct model call to that tool already goes
  through - inside BOTH `gate_check` and `run_step`, cached by the step's
  own identity so the two never ask twice for the same step. A step naming
  a tool whose real configured tier needs a person, even when the model
  called it not risky, is refused rather than let through - proven by its
  own test, not merely reasoned about.
- send_email, draft_email, the schedule tools (their own `Tool.execute` is
  a dummy - `_schedule_call` is the real path, not the `Tool` contract at
  all) and `propose_plan` itself cannot be named by a step: each has its
  own bespoke, turn-shaped pre-gate check this dispatcher does not
  reproduce, or would let a plan nest inside itself. A step naming one is
  refused with a plain reason.
- **Deliberately NOT registered with Pause/Resume** (`_TASK_MODULES`):
  that mechanism's generic Resume path calls `module.run(plan,
  approved=True, announce=..., checkpoint=...)`, with no way to supply the
  `run_step`/`gate_check` `jarvis_plan.run()` requires - and
  `jarvis_plan.py`'s own condition 4 ("the plan grants nothing for later")
  already requires no automatic resume regardless, so nothing is lost.
  "Stop everything" still reaches a running plan through the plain
  `watch.stopped()` check every tool already has.
- `propose_plan` joins `NEEDS_A_PERSON` (the belt the other three
  multi-step tools already wear: an `auto`/`notify` tier is never good
  enough for it, whatever a config file says) and the `control` tool
  group for the short tool list - not a new group of its own, since a new
  group's name costs `more_tools`' own description tokens on every turn,
  already near its budget, while a group's *members* cost nothing there.
- Two tool descriptions had to be trimmed to fit `test_tool_text.py`'s
  per-tool token budget (300) once `propose_plan`'s own schema was added,
  and `jarvis_reach.py`'s `TOOL_NAMES` (the "What asks first" page) gained
  a plain-English row for it - the same audit that follows every feature
  here, run this time as it was being built rather than only after.
- Verified: `backend/test_agent_plan_wiring.py` (new, 49 checks) - the
  tool is invisible/refused while `enabled()` says no, and refused before
  `propose()` runs on each of the four taint signals separately; a safe
  step runs with no card of its own; a risky step, and separately a
  `from_step` one, always get their own card, asked exactly once; a step
  the model did NOT flag risky but whose real tier needs a person is
  refused anyway (the gap above, proven, not assumed); a denial anywhere
  stops the whole run, including a later step that was itself safe; each
  excluded tool is refused before it ever reaches its own gate; running a
  step for a real tool goes through that tool's own real `prepare()`.
  `backend/test_plan.py` (72 checks, unchanged - `jarvis_plan.py` itself
  was not touched) and the existing `test_agent.py`, `test_tool_text.py`,
  `test_short_tool_list.py` and `test_reach.py` suites all still pass;
  `tools/gen_reach_cases.py` was re-run for the new row (a small, additive
  fixture diff in both apps).
- **Not yet built either**: a UI in either app - unchanged from the
  2026-09-28 entry above; once the safety test clears the bar, the card
  needs no new shape, only the ordinary approval flow both apps have.

Built 2026-09-28, the owner's decision of 2026-09-26 above ("reading phone
notifications is added as an option") - **the actual build of that
decision**, phone-only end to end, its one PC-decided switch copied
straight from `jarvis_watch_notify.py`'s already-approved shape
(`docs/JARVIS-API.md` §61):

- **Backend**: `backend/jarvis_phone_notifications.py` (shipped whole) +
  `phone-notifications.patch` (one line into `jarvis_gate.py`'s
  "acts only on tier ask" set, one `_RISK` entry) - off by default, ON is
  one approval card (`phone_notifications_read`), OFF is instant. Never
  sees a notification's own text: it is a plain on/off switch, nothing
  more. Given the usual second door too (`jarvis_settings_registry.py`:
  "open/turn on phone notifications" by voice or chat, calling the exact
  same function). `backend/test_phone_notifications.py`, 70 checks - the
  same shape `test_watch_notify.py` already proves.
- **Phone**: `service/PhoneNotificationListenerService.kt` (the real
  `NotificationListenerService`, bound only by the system), gated by the
  PC's switch, the per-app allow list and, defensively, an SMS check a
  second time; `data/NotificationRedactor.kt` (the one-time-code
  heuristic, applied before anything is stored); `data/
  NotificationAllowList.kt` + `.../NotificationAllowListStore.kt` (empty
  by default; a package the OS itself reports as the default SMS handler,
  `Telephony.Sms.getDefaultSmsPackage` (see the CI fix below - not
  `RoleManager.ROLE_SMS` as first built), is refused outright, and so is
  one whose Play Store category or package name looks like a bank,
  brokerage or payment app); `data/CapturedNotifications.kt` (a capped,
  per-device store, never
  synced). `PhoneNotificationsPlate.kt` (Settings → Phone notifications:
  the switch, Android's "Notification access" explained before it is
  opened, and the allow list). Reading one into a chat reuses the Share
  sheet's own "shared text" chip - no new backend plumbing, and the
  existing outside-text rule marks it on its own.
- **Two judgment calls worth a second look, made rather than deferred:**
  - **Banking apps are blocked outright**, not just discouraged in words
    - the task allowed either. Two real signals existed (the app's own
    declared Play Store category, and a curated name-substring list), so
    blocking was the more responsible choice; the card and the allow-list
    screen both say plainly that this is a heuristic, not a guarantee, for
    a bank neither signal catches.
  - **The redaction heuristic deliberately over-redacts.** It catches a
    plain 4-8 digit run near an English trigger word, the common "NNN NNN"
    grouping, and a bare digit-only notification with no trigger word at
    all - and it will occasionally blank a year or a reference number by
    mistake. It does NOT catch a non-digit code, a trigger word in another
    language, or a bare digit run with no trigger word buried in a longer
    sentence - written down in the class's own doc and in `docs/
    JARVIS-API.md` §61.4, not discovered later.
- Verified: `backend/test_phone_notifications.py` (70/70),
  `test_asks_first.py` (174/174), `test_card_words.py` (98/98),
  `test_gate_risk_words.py` (15/15) - all re-run after this feature's own
  entries were added to their tables; `tools/gen_asks_first_cases.py` and
  `tools/gen_card_words_cases.py` re-run so both apps' fixtures match.
  `tools/check_parity.py`: clean, the new route classified `phone-only`
  beside the smartwatch one. **Kotlin is unverified here** (no local
  Android build; "How the Android apps get built" above) - every new file
  was read back by eye instead, and the redaction/allow-list logic was
  additionally checked by hand-simulating the regex in Python first, since
  neither can be compiled in this container.

Fixed 2026-09-28, from the first real CI round on the phone changes above
(GitHub Actions is the only Kotlin compiler this container has - "How the
Android apps get built" above) - two real, unverified-until-now bugs, both
caught by the compiler itself, neither by a review:

- **A missing import broke `onOk` everywhere in `JarvisRuntime.kt`.**
  Merging the offline-models phone half (`Brain -> Model remembers its
  last list...`, above) removed the one call site that removal alone made
  look unused, and dropped `import com.jarvis.client.net.onOk` along with
  it - but `onOk` (an extension function on `ApiResult<T>`, `net
  /JarvisApi.kt`) was still used at several OTHER, unrelated call sites
  (`refreshStatus`, `refreshAttention`, the jobs read in `refreshAll`),
  none of which the merge touched or re-scanned for. Every one of those
  had been silently broken since that merge - re-added the import; nothing
  else needed to change.
- **`RoleManager.getRoleHolders(ROLE_SMS)`, the SMS-exclusion check built
  above, does not exist in the public SDK stub Gradle compiles against**
  (`RoleManager.isRoleAvailable` and `.isRoleHeld` do; this one specific
  method does not - confirmed by the compiler, not guessed). Replaced with
  `Telephony.Sms.getDefaultSmsPackage`, the long-standing public API for
  exactly this question, plus the `<queries>` element it needs for Android
  11+ package visibility (`AndroidManifest.xml`). No change to what the
  feature actually blocks or how strictly - same signal, same static
  fallback list, same "checked twice" design; only the OS call underneath
  changed.
- Both fixes verified by reading the actual compile error text (not by
  reasoning about what "should" work) and cross-checked against public
  documentation before writing the replacement, per "Do not claim more
  than the evidence supports" above. Every existing test still passes;
  none tested the broken code paths directly (the pure `onOk`-adjacent
  logic wasn't unit-tested at that granularity, and the SMS check's
  Android-backed half was already documented as untestable without a
  device) - written down here so that gap is visible, not papered over by
  "tests passed."

## Every new feature gets its own audit, without being asked

Standing instruction from the owner, 2026-09-24. Whenever features are added
to Jarvis, run a follow-up audit scoped to the new feature set as part of
the same piece of work. Do not wait to be asked. It covers three things:

1. **Bugs.** A bug audit of the new code. Findings are verified against the
   source before they are reported, as everywhere else in this file.
2. **Both apps.** Was the feature added to the desktop program AND the
   Android app, wherever it makes sense? If one side is deliberately left
   out, the reason must be written down in `docs/ARCHITECTURE.md` §8
   ("One-sided on purpose"). `tools/check_parity.py` must be clean.
3. **Fit with what is already there.** Does it tie in with the existing
   features? That means:
   - the same permission model and approval cards;
   - the same settings patterns and the same wording;
   - no clash with an existing feature, and no duplicate of one;
   - `docs/JARVIS-API.md` and the other docs updated.

"Features" means abilities the owner can see or use, not bug fixes or doc
edits. When several features land together, one audit covers the batch.
Report the result in plain words. Fix what it finds, or ask when the fix is
the owner's call.

## Tell the owner when something is wrong

Standing instruction from them: "Tell me plainly when something in the brief is
wrong, out of date, or won't work on the platform - I'd much rather hear that
than have you route around it quietly."

## Do not claim more than the evidence supports

This has caused real damage in this project more than once: a stack frame read
as a cause and relayed as "confirmed", and a bug invented by grepping my own
draft and mistaking it for the source file.

- Verify against the actual file before stating anything about it. Especially
  before stating it to the other session.
- Quote the evidence. Let the side that owns the code do the diagnosing.
- "I checked X and it says Y" beats "Y". "I have not checked" beats a guess
  delivered confidently.

## How the Android apps get built

There is no local Android build in this container. `dl.google.com` is blocked
by the network policy, so the Android Gradle plugin cannot resolve and
**GitHub Actions is the only compiler available** for `jarvis-client` and
`jarvis-android`. Expect a CI round trip (~15 min) to find out whether
anything compiles. Check work carefully before pushing.

The `jarvis-client` APK is published to the rolling `client-latest` release,
but only when the emulator smoke job passes. `jarvis-android` no longer
publishes a release at all - see the top-level `README.md` for why.

## Checking the Rust without waiting for CI

`cargo clippy` fails in the dev container: the product is a Windows app, the
Linux dependency graph pulls `gdk-sys`, and GTK is not installed. For a long
time that meant every Rust change was pushed unverified and checked by CI five
minutes later.

**It does not have to be.** The `x86_64-pc-windows-msvc` target is installed,
and checking against it selects the *Windows* dependency graph, which has no
GTK in it. Nothing is linked, so no MSVC toolchain is needed:

```
cd jarvis-desktop/src-tauri
cargo fmt --check
cargo check  --target x86_64-pc-windows-msvc --all-targets
cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings
```

That is two of the three things CI runs, on the same code CI compiles,
including every `#[cfg(windows)]` block — which a Linux check would have
skipped entirely, and which is where the unsafe FFI lives. It takes about
twenty seconds warm.

The third, `cargo test`, still needs a Windows host. Write the Rust tests
anyway; they are compiled by `--all-targets` above, so at least they are known
to build. A "GNU compiler is not supported for this target" warning in the
output is expected and harmless.

## PowerShell: ONE line, ready to copy

The owner runs these by pasting into a terminal. A multi-line block is a
multi-line paste, and a multi-line paste into PowerShell goes wrong in ways
that look like the command is broken rather than like the paste was.

- **One line.** Statements joined with `;`. However long it ends up.
- **No `.ps1` file to run**, unless the point IS the file. A script file means
  being in the right folder, and it means the execution policy, and both of
  those produce errors that read as "your command is wrong".
- Say where any output file lands, in plain words, at the end of the command.

The trap, written down because it has already been shipped once: inside
`catch`, `$_` is the ERROR, not the pipeline item. In
`... | ForEach-Object { try { ... } catch { $o[$_] = ... } }` the catch writes
under an ErrorRecord instead of the name. Capture it first — `$n = $_` — or
use a plain `foreach` loop, where the variable is real.

## Running PowerShell here

There is a PowerShell 7 at `/opt/pwsh/pwsh` — the portable tarball, extracted,
no install. **Use it.** Three bugs shipped to the owner before it existed,
each found by them running the script and pasting an error back, which is the
slowest possible way to test anything:

```
/opt/pwsh/pwsh -NoProfile -File ./scripts/apply-patches.ps1 -BackendPath /tmp/fake -SkipTests
```

If it is gone after a container restart:
`curl -sSL https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/powershell-7.4.6-linux-x64.tar.gz -o /tmp/pwsh.tar.gz && mkdir -p /opt/pwsh && tar -xzf /tmp/pwsh.tar.gz -C /opt/pwsh && chmod +x /opt/pwsh/pwsh`

**It is 7, the owner has 5.1.** It catches syntax errors, logic and the
stderr trap; it does NOT catch 5.1-only problems like `??`, so those still
have to be read for.

The trap that cost the most: `$ErrorActionPreference = 'Stop'` turns **any
stderr output from a native program into a terminating error**, even on
success. `git apply --verbose` writes "Checking patch x..." to stderr every
time, so the script died on the first of nineteen patches. Wrap native calls:
save the preference, set `Continue`, restore in a `finally`.

## Launch videos: every version is kept and numbered

The owner's rule, 2026-09-24: never replace a launch video. Each new one is
the next version, and every version goes on GitHub.

- Finished videos live in `videos/vN/` as `jarvis-launch-vN.mp4` with its
  poster `jarvis-launch-vN.jpg`, the plan, the brief, the share copy and the
  Hyperframes project. v1 to v5 are there (v3, v4 and v5 also have a 15 s
  upright cut, `jarvis-launch-vN-vertical.mp4`); the next one is v6.
- The `/brag` skill renders into `brag-output/`, which is gitignored scratch.
  Copy the finished video into `videos/vN/`, add it to the top of
  `videos/README.md`, point the README's "Launch video" section at it, and
  post it: push and open a pull request.
- Keep each `.mp4` under GitHub's 100 MB file limit (re-encode if a render
  comes out bigger), and check the soundtrack's loudness after rendering:
  once the renderer's mixer made it 11 dB quieter than the score.
- A video says only what the code supports. Mark anything built-but-off as
  "ready" and anything designed-but-not-built as "next".

## Where everything is written down

- `docs/ARCHITECTURE.md` — **read first.** The invariants, the one permission
  model every feature must use, memory, events, and what does not exist yet.
- `docs/MODEL-TOPOLOGY.md` — what runs on the graphics card and why.
- `backend/README.md` — the patches and what each one fixes.

The Python backend lives on the owner's machine, not in this repo. `backend/`
holds patches against it plus tests that prove the patches work.
