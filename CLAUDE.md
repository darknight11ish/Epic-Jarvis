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
- ~~Phone: allow home-network addresses~~ - **replaced 2026-09-28** (see
  the studio review block below): the phone stays on Tailscale/Meshnet.
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
- **Fixed 2026-09-28 (the owner said fix it; commit 248227a2):** marking a
  crisis answer "wrong" (the thumbs-down button) used to count toward
  "suggest the bigger model" - the crisis exclusion above only covered the
  live phrase-based signal and the struggle count. Now the chat route hands
  a crisis turn's id to `jarvis_agent.note_crisis_turn` when it makes the
  id (`second-card-suggest.patch`, on `wellbeing.patch`'s flag and again on
  `run_local_turn`'s own check), and `note_correction` does not count a
  mark on that id. `test_wellbeing.py` runs the join end to end.

Decided 2026-09-27, the owner's answers after the studio review (play
testers, scouts and integration scouts; `.claude/agents/`):
- **Talk-to-type on the PC: one approval card to switch it on**, then no
  card each time. Hold a key, speak, and Jarvis types what was said into the
  program in front - speech-to-text on the PC only, as always. Switching it
  off is immediate. Not on the phone (a client must not do speech-to-text).
  Built on GitHub's `main` (JARVIS-API §72), merged into the research branch
  2026-09-28; while Jarvis Live is on, talk-to-type waits, like the talk
  button.
- **Answers that used web search, weather or home status are read aloud**
  when read-aloud would otherwise apply. Answers that used email, calendar,
  notes, documents, memory, or any tool not on that short list stay on
  screen, and every earlier rule (sensitive facts, the stricter hands-free
  choice) still comes first. This replaces "any tool keeps the answer on
  screen".
- **Jarvis may hold a conversation with an AI chatbot (such as ChatGPT or
  Gemini) for the owner**, asking it things and following up on its answers
  **on its own, within limits the owner sets**. This loosens rule 4 and the
  "ask each time" cloud rule (ARCHITECTURE §11) for this feature only. How
  the limits work, and whether it uses the chatbot's official API or its
  website, is being designed and comes back to the owner before anything is
  built (`docs/CHATBOT-DRIVER-DESIGN.md`). It may need both graphics cards.
  Rule 1 is unchanged: nothing private (email, files, credentials, memory)
  goes into those chats.
  Owner's answers, 2026-09-28: **Gemini first, through its website
  (gemini.google.com), driven openly** - at human pace, in a visible
  browser window, with nothing that hides it from or dodges Google's bot
  detection, and no captcha-solving. The owner chose this knowing Google's
  terms forbid automated access and that the account could be closed. A
  request to add "tactics that help avoid bans" was declined: getting round
  a site's bot protection is not something this project builds.
  **A spare Google account used only by Jarvis**, not the owner's main
  one (owner, 2026-09-28): a ban cannot touch the owner's Gmail, and the
  owner's email and Gemini's memory of them stay out of these chats.
- **Inbox tidy by voice: yes** (owner, 2026-09-28) - archive, star, mark
  read, or move to Trash. One approval card lists every email it will
  touch, approved on screen (never by voice), then Undo. "Delete" only ever
  moves to Trash. The card says when the choice came from reading email
  (outside text). A new named way out of the PC (ARCHITECTURE §4) and its
  own gate action, like sending email. Not built yet.
- **The phone connects through Tailscale or NordVPN Meshnet only** (owner,
  2026-09-28), replacing "Phone: allow home-network addresses" of
  2026-09-27. Allowing a home address would mean the PC also answering on
  home Wi-Fi, where the pairing key travels unscrambled; the mesh networks
  work at home too and scramble it.
- **A "listening" sound after a bare "Hey Jarvis"** (owner, 2026-09-28):
  only as part of the existing "I heard you" switch, which stays off by
  default.
- **Animal faces offer their own voice once** (owner, 2026-09-28): the
  first time the owner picks an animal face, one line asks "The panda has
  its own voice. Use it?" (Use it / Keep my voice), remembered per face. A
  face never changes the voice by itself. **Confirmed 2026-09-28 over the
  mascot branch's "Voice follows the face" switch, which was built on by
  default:** that switch stays, but starts off, and the one-time question
  turns it on. **The sea otter must not use Kokoro's "Sky" voice** (its name
  matches the voice OpenAI withdrew in 2024 over a likeness complaint);
  give it another Kokoro voice with the same playful pitch. Animal voices are Kokoro voices,
  blends and pitch from Jarvis's own sources only - never a real person's
  voice - and must pass the "not the owner's voice" check.
- **Upgrade the voice pack to Kokoro v1.0** (owner, 2026-09-28): the best
  rated voices, real British pronunciation, and a "Hear it" sample button
  for every voice in both apps. The saved choice moves from a number to the
  voice's name, and the owner's current choice carries over. A 350 MB
  download on the PC, checksum-pinned. Not built yet.
- **A "sneaky instruction" (prompt-injection) detector: test two, keep the
  winner** (owner, 2026-09-28) - Meta's Prompt Guard 2 (Llama 4 Community
  Licence: credit "Built with Llama", licence file, the owner downloads it
  after accepting Meta's terms) and an Apache-licensed one (Horizon Labs
  guard-small). Both run on Jarvis's own attack tests on the owner's PC;
  whichever wins is kept, and it only ever adds a warning - it never removes
  or replaces an approval card.
- **A thumbs-down on a crisis answer stops counting toward "suggest the
  bigger model"** (owner, 2026-09-28) - closes the gap written down in the
  Opus 5.5 re-check above. Done (commit 248227a2).
- **Build the chatbot driver first** (owner, 2026-09-28), ahead of easier
  setup, voice upgrades and the other new abilities. It is **versatile**:
  one driver with a separate "adapter" per chatbot website, Gemini first,
  others added one at a time (each new chatbot is a new named way out of
  the PC and gets the owner's OK first, since each company's terms differ).
  **Two versions by hardware:** with both graphics cards, the full version
  (long, flexible sessions, the driver model on the 12 GB card); with one
  card, a limited version (shorter sessions, sharing the main card, waiting
  while the owner chats). The two-card version is switched on only once
  the second card is installed and measured.
- **Phone: tap to talk, stopping at a pause** (owner, 2026-09-28), instead
  of only hold-to-talk. The phone detects the pause (Smart Turn); the words
  are still worked out on the PC after the voice check. A Stop button and a
  time limit stay.
- **Projects, like Claude's Projects and more** (owner, 2026-09-28): a
  project has a name, its own instructions, files and chats, its goals
  (built on the Goals feature, `jarvis_goals.py` on the continuation
  branch - not a second goals system), benchmarks to measure progress, and
  the work being built. **Both kinds**: coding projects (benchmarks are
  tests, speed and scores) and life projects (benchmarks are numbers the
  owner tracks). **Jarvis does real work**: it writes files and runs code
  and benchmarks on the PC, and **every change asks first with a card**,
  like everything else. Designed in `docs/PROJECTS-DESIGN.md` before
  anything is built; queued after the chatbot driver unless the owner says
  otherwise.
  Owner's answers to the design's questions (2026-09-28):
  **a "Shareable" switch per project, off by default** - when on, a short
  piece of the project's files may go to a web search or the chatbot
  driver, shown word for word on its card first; never health or money
  numbers, and never memory, email or credentials. This bends rule 1 for
  that shown piece only, the way the locked backup bends it for one file.
  **Build order inside Projects:** projects, goals, benchmarks, charts and
  running tests first; Jarvis writing code comes once the 12 GB card is
  installed and measured.
  **A private mark Jarvis added by itself to a benchmark** (a tracked
  number, e.g. "5k time" mistaken for money) **can be removed by the owner,
  with a card first** (owner, 2026-09-28), because afterwards those numbers
  may be read aloud. A mark the owner added comes off with no card, as
  built.
- **Swiping on approval cards is a setting that can be turned off**
  (owner, 2026-09-28): "Swipe to approve or deny" on the phone's Security
  screen, on by default. Off, every card is decided with its buttons only.
  Turning it off is instant; turning it back on asks for the fingerprint or
  PIN, like every other loosening there. The desktop has no swipe.
- **The chatbot driver becomes versatile** (owner, 2026-09-28): (1) **an
  API adapter** - one adapter speaking the common OpenAI-style API, so a key
  reaches ChatGPT, DeepSeek, Mistral, Grok, OpenRouter and similar (keys
  under rule 3; each host a named way out); (2) **more websites, driven
  openly like Gemini**, each with its own spare account - **ChatGPT, Claude,
  Microsoft Copilot, Perplexity, and other commonly used chatbot websites**;
  (3) **a second AI on the owner's own PC** (another local model, best on
  the 12 GB card; nothing leaves the PC); and (4) **compare**: ask several
  AIs the same question, one card listing every AI it will ask, one summary
  of agreements, disagreements and sources.
  **The chatbots the studio picked are confirmed** (owner, 2026-09-28,
  after the feature audit noted they had gone in without a per-company OK):
  DeepSeek, Grok, Le Chat and Meta AI websites and the Groq API stay, next
  to the ChatGPT, Claude, Copilot and Perplexity the owner named. Any
  further chatbot still gets the owner's OK first.
  **A money limit comes before API chatbots are used for real** (owner,
  2026-09-28): a monthly amount per service, set on the PC; Jarvis stops
  that service when it is reached, and the approval card shows how much is
  left. Prices change, so the amount is an estimate from a price list the
  owner can see and correct, and the card says "about".
  **Built 2026-09-28; the owner then chose to make it a hard stop too:**
  Jarvis also asks each service to cap how long an answer can be, so one
  long answer cannot carry a month past the limit. Each service names that
  setting differently, so each one's own documentation is checked before
  it is used. Built 2026-09-28 (field names confirmed from each company's
  own code on GitHub, their documentation sites being blocked); **the owner
  chose (2026-09-28): DeepSeek, whose field could not be confirmed, stays
  usable with the estimate check only, and OpenAI keeps gpt-5-mini** even
  though its hidden thinking can shorten answers near the limit.
  **Compare, as built, is confirmed** (owner, 2026-09-28): up to 3 chatbots
  per comparison on one graphics card and 4 on two, asked one after
  another; a chatbot that shows a captcha or sign-in page is left out and
  the others carry on (the summary says who and why), rather than pausing
  the whole comparison.
- **Customer-support chats** (Groupon's and similar, owner 2026-09-28) are a
  separate mode of the driver, because the other side is a company acting
  on the owner's real account, often a real person: **one card before each
  support chat lists exactly which personal details Jarvis may give** (order
  number, email and so on - never passwords or payment card numbers);
  **every offer (refund, cancellation, change) gets its own card**, and
  nothing is accepted until the owner approves it. ~~Jarvis says at the
  start that it is an AI assistant~~ - **changed 2026-09-28 (owner): no
  opening disclosure line; Jarvis writes in the owner's name**, like any
  message an assistant drafts for someone. **If the agent asks directly
  whether they are talking to a bot, Jarvis never claims to be human: it
  pauses and hands that question to the owner**, who answers in the window. Designed in `docs/CHATBOT-DRIVER-DESIGN.md` before it is built.
  Owner's answers to the design (2026-09-28): **Jarvis sends the messages
  itself**, at human speed (and never hiding from the site's bot detection),
  and **each card names that
  company's terms risk** before the owner approves (the real account could
  be closed); **identity checks** (last digits of a card, security
  questions, codes) **are always handed to the owner** in the window, never
  answered by Jarvis.
- **A captcha can be handed to the owner's phone** (owner, 2026-09-28):
  when a chatbot or support site shows a captcha or sign-in page, the phone
  gets an alert, and offers **"Solve it here"** - a live picture of that one
  browser window only, sent PC to phone over Tailscale/Meshnet, never
  saved, and the owner's taps and typing passed to that window only while
  Jarvis is paused there. Solving it on the PC still works. Jarvis itself
  never solves a captcha. The app says plainly that some captchas may
  reject taps passed on this way. Queued after customer-support chats.
- **The build queue, set by the owner (2026-09-28)**, in this order:
  1. customer-support chats; 2. the captcha hand-off to the phone;
  3. **one pull request to `main`** with everything so far (the owner
  merges); 4. the voice upgrade (Kokoro v1.0, "Hear it" samples);
  5. finishing the screen feature ("Look at this" and "Watch with me"
  working on the PC and phone); 6. inbox tidy by voice, **Undo for 10
  minutes**; 7. talk-to-type on the PC, **held Right Ctrl** by default
  (changeable in Settings); 8. QR pairing with per-device keys; 9. the
  sneaky-instruction detector test.
  **Jarvis Live extras, all yes:** a phone Quick Settings tile (start/end);
  a headset button (press = stop talking, long press = mic off, never
  approves); a 10-minute "Live ended - Resume" notification; a PC hotkey to
  start/end Live, off until the owner picks one (Alt+Shift+L suggested);
  preferring a Bluetooth headset microphone in Live; "Talk about this in
  Live" from the phone's Share (the shared item is outside text). **The
  phone gets the same "End Live when" setting as the PC** (default strict;
  the looser choice asks for the fingerprint or PIN). These extras are
  built alongside the queue where they fit, the phone ones with item 2.
  **History marks Live sessions** (owner, 2026-09-28): each Live session
  is already its own chat (words and times kept, encrypted; never the
  audio, pictures or side remarks); History shows it with a "Live" label
  and its length ("Live · 12 min · 28 Sep, 14:05") in both apps, and can
  be filtered to Live sessions only. Built with item 2.
- **Chats, after the chat audit** (owner, 2026-09-28;
  `docs/studio-2026-09-28/chat-audit-*.md`): **"Continue this chat"** from
  History in both apps (reuses the conversation, its "read outside text"
  mark carried over), an **"Earlier chats"** link on the phone's Home and in
  the Jarvis bar, and **the whole current conversation as a scrollable
  thread**, not just the last answer. **Chats with other AIs and comparisons
  are kept in History**, encrypted, marked as outside text, never learned
  from, never read aloud. **A new conversation starts after 30 quiet
  minutes** (the old one stays in History, and Continue brings it back).
  **Crisis chats are kept but titled "A difficult moment"**, never with the
  owner's words. **Support chats: export stays** (the owner's own record -
  a named exception to "no plain-text path", saying plainly the file is not
  encrypted), and **auto-delete and "Forget a time frame" ask before
  removing a support chat**. **The desktop HUD's own chat box opens the
  Jarvis bar instead**, so the PC has one chat box. History rows carry a
  kind (chat, Live, support, chatbot, comparison).
- **Jarvis may look at the owner's screen, on the PC and the phone**
  (owner, 2026-09-28), two ways: **"Look at this"** - one look when the
  owner asks (a key on the PC; the assistant gesture on the phone), nothing
  saved; and **"Watch with me"** - a live session the owner starts and
  stops, with a visible "Jarvis is watching" sign the whole time, pausing
  on password fields and on apps the owner excludes (banking), nothing
  saved. What Jarvis sees is outside text. Screen images stay on the owner's
  own devices (the phone sends them only to the PC, over Tailscale/Meshnet).
  Full picture understanding needs the 12 GB card; with one card, Jarvis
  reads the screen's text only. **Not** always-on watching with a history
  (Recall-style) - the owner declined it. Designed in
  `docs/SCREEN-DESIGN.md` before it is built.
  Owner's answers to the design (2026-09-28): **the question and Jarvis's
  answer about the screen are kept in chat history like any chat** (the
  picture and the screen's words never are); **screen answers are read
  aloud** unless a sensitive fact was used or the strict hands-free setting
  says otherwise - a named exception to "a reading tool keeps the answer on
  screen".
  **Under "Only trust the talk button", screen answers stay on screen**
  (owner, 2026-09-28): a turn started by "Hey Jarvis" gets a written answer
  about the screen only. **A voice setting lets the owner allow reading them
  aloud** even then; like the other voice settings, turning it on raises an
  approval card and turning it off is immediate.
- **"Jarvis Live": design voice and camera together now** (owner,
  2026-09-28), like Gemini Live: a back-and-forth voice conversation the
  owner starts and stops, with no wake word between turns and interrupting
  at any time, plus showing Jarvis the phone's camera. The voice check still
  runs on every clip, cards are still decided by tapping (never by voice),
  and everything stays on the owner's own devices. Not full-duplex (that
  skips the voice check), so a turn takes about 2-4 seconds (estimated; corrected by the design). The camera
  understands pictures only with the 12 GB card (Qwen 3.5 9B or Qwen3-VL
  8B, unmeasured); with one card there is no camera (see the owner's answers below). The camera part stays
  off until the card is in and a photo test passes. Designed in
  `docs/LIVE-DESIGN.md` and brought back to the owner before anything is
  built.
  Owner's answers to the design (2026-09-28): **under "Only trust the talk
  button", a Live session is trusted like the talk button by default**
  (the owner pressed Start), **with a voice setting to give Live the extra
  "Hey Jarvis" caution instead**; choosing the extra caution is immediate,
  going back raises an approval card, like the other voice settings.
  **Answers about what the camera sees are read aloud, like screen
  answers**, unless a sensitive fact was used or the strict setting says
  otherwise. **The camera stays off until the 12 GB card is in and passes
  the photo test** - no words-only camera on one card.
  After the rules check (owner, 2026-09-28): **a Live session started by
  voice ("Hey Jarvis, let's talk") is trusted the same as one started with
  the button** by default, and **the Live voice setting can change it** -
  its choices are full trust (default), "only when started with the
  button", and the "Hey Jarvis" caution for all of Live; a stricter choice
  is immediate, a looser one raises an approval card. **Live pauses itself
  during a phone or video call** and picks up afterwards (whether Windows
  and Android can always tell a call is happening is to be checked; where
  they cannot, the app says so and the Mute button covers it).
  After the voice play-test (owner, 2026-09-28): **Live keeps the 2-second
  voice check** - no "Balanced" option for Live; tap buttons cover quick
  answers. **Side remarks to someone else are ignored**: when a Live clip is
  clearly not meant for Jarvis, Jarvis stays silent and nothing from it is
  learned.
  After the build (owner, 2026-09-28): **with App lock on, the PC ends Live
  when App lock would ask again** (1 minute after the owner last touched a
  Jarvis window, talking does not count) by default, **with a setting to
  end it only when Windows itself locks**; the looser choice raises an
  approval card, the stricter one is immediate. **The desktop Brain's
  existing "Live" tab is renamed "Now"** (and, after the review track,
  2026-09-28: **after a crisis turn, Live quietly gets more time and skips
  the "minutes left" warning**; **the two interrupt settings become one** -
  interrupt by voice, by tap only, or not at all - for Live and normal use
  alike; **side remarks are not kept in chat history at all**) so it is
  not confused with
  Jarvis Live.
- **After the second chat audit** (owner, 2026-09-28;
  `docs/studio-2026-09-28/chat-audit2-*.md`): **the PC re-registers a
  continued chat's own typed and spoken messages from its encrypted record**,
  so facts learned after "Continue this chat" or a restart save on their own
  again instead of waiting as cards for about 10 questions. This loosens the
  "only messages seen arriving live count" rule for the owner's own typed or
  spoken words in a chat the PC already holds - never for shared, pasted,
  chatbot, support or outside text, and the outside-text mark still decides.
  **The scrollable thread hides under "Hide memory lists and chat history"**
  on both apps, like the "Used" list. Not yet decided by the owner, built
  the careful way meanwhile: the delete dialogs say facts stay and backups
  keep copies; the thread shows a "Jarvis reads from here" line; a chat that
  spills over the days in "Forget a time frame" starts unticked; the bigger
  re-send caps for two cards wait until the second card is measured.
- **"Forget a time frame"** (owner, 2026-09-28): the owner may ask, by
  voice or typing, to forget what Jarvis learned or said in a time frame
  ("forget what you learned last week", "delete my chats from 1 to 15
  September"). Nothing is removed at once: both apps show the exact facts
  and chats from that time, each ticked, the owner can untick any, and ONE
  approval card listing every item is decided by tapping only - never by
  voice. Approved, the facts are **forgotten (retired, as Forget does) and
  the chats deleted, with 10 minutes to Undo**; erasing a fact's words for
  good stays the separate per-fact "Erase the words". This is the one
  exception to "irreversible bulk actions stay off the API" (JARVIS-API
  §18), made safe by the list, the card and the Undo window.
  Built 2026-09-28 (JARVIS-API §64); **the owner kept its card a risky
  approval** (Windows Hello on the PC, the screen lock on the phone),
  because after the 10 minutes the chats are gone for good; Undo stays one
  tap.
- **Jarvis is built for one or two graphics cards.** Research and new
  features say which they need; a feature may need two if a one-card PC
  still works without it. Studio agents read `.claude/agents/JARVIS-TODAY.md`
  first so they do not re-research what Jarvis already has.

Decided 2026-09-27, when the owner asked for a 3D animal face (with
Gemini's notes as input, not instructions):
- **All three animals - red panda, pygmy owl, sea otter - panda first.**
  The owner then said go for the owl and the otter the same day, and all
  three are built. Each is a face like the others (picked in the Faces
  window / Appearance), drawn from shared shader parts plus its own, one
  source for both apps (`docs/CRITTERS.md`), not a downloaded 3D model.

Decided 2026-09-28, the owner's answers after the animal-face audits:
- **Mouths follow Jarvis's real voice**, timed by Kokoro's own phoneme
  durations when the PC is set up for it (`jarvis_mouth.py --prepare`), else
  analysed from the sound (`docs/LIPSYNC.md`). No sound, no mouth movement.
- **Body movement: natural and calm, never busy or sporadic** - small,
  slow, eased motion; rare idle events; asleep is still. Reuse proven open
  motion logic (MIT: Spring-It-On, TalkingHead) rather than invent it.
- **Serious moments are calm and plain:** no wave while asking for an
  approval (an attentive look instead), a still, concerned look at an error,
  and for a crisis-help answer a neutral pose and Jarvis's plain voice (not
  the animal voice).
- **Not connected = asleep with a hollow ring**, on every face surface of
  both apps, matching the tray icon; never an approval pose while acting is
  blocked. The screen reader says "Jarvis isn't connected".
- **Asleep shows rising Zs** above each animal whenever Jarvis is on standby,
  whether the standby schedule or the owner put it there - never while
  merely not connected (that is the hollow ring alone). Drawn over the face,
  not inside the shader, in both apps.
- **A "Still" option for the animals** in both apps' face settings, off by
  default: the animal sits calmly and only breathes - no looking around,
  no gestures or idle events.

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

**A phone face's AGSL shader must stay under Android's size limit.** Android
compiles `RuntimeShader`s in Skia's strict mode, which refuses any shader
whose flattened size is over 100,000 - and the app crashes when that face is
drawn. Every operation counts 1, a call counts the called function's whole
size, and a loop counts its body once per step, so a big distance function
inside a long march loop blows it fast. WebGL and a newer Skia on a PC
(skia-python) accept an over-size shader without a word: the first red panda
went out four times over and only the emulator test caught it. Measure with
`python3 tools/shader_size.py` (CI runs `--check`) before pushing a shader.

The `jarvis-client` APK is published to the rolling `client-latest` release,
but only when the emulator smoke job passes. `jarvis-android` no longer
publishes a release at all - see the top-level `README.md` for why.

## Editing a backend `.patch`: record its old version first

After changing any `backend/*.patch`, run `python3 tools/build_patch_history.py`
before committing (its docstring says why). **This container's clone is
shallow**, and there the tool refuses to run and `test_patch_history.py`
quietly skips the checks that need history - so it passes here and fails in
CI. Run `git fetch --unshallow origin` first. (Shipped once, 2026-09-28:
`voices.patch` changed, CI's backend job went red.)

## Checking the Rust without waiting for CI

`cargo clippy` fails in the dev container: the product is a Windows app, the
Linux dependency graph pulls `gdk-sys`, and GTK is not installed. For a long
time that meant every Rust change was pushed unverified and checked by CI five
minutes later.

**It does not have to be.** Check against the `x86_64-pc-windows-msvc`
target. It is not always installed in a fresh container (it was missing on
2026-09-27): if `rustup target list --installed` does not list it, run
`rustup target add x86_64-pc-windows-msvc` first. Checking against it selects the *Windows* dependency graph, which has no
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
  Hyperframes project. v1 to v6 are there (v3 to v6 also have an upright
  cut, `jarvis-launch-vN-vertical.mp4`); the next one is v7.
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
