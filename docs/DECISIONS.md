# Decisions, dated: the owner's decisions from 2026-09-24 onwards

**This is the record, not the rulebook.** Every block below was moved here **verbatim**
from `CLAUDE.md` on 2026-10-12, because that file had grown to about 150 KB and the
harness loads only the first 64 KB of it - silently. The rules themselves stayed in
`CLAUDE.md`; the dated reasoning behind them lives here.

Nothing in this file was reworded while moving. The blocks are in their original order.
Read `CLAUDE.md` to know a rule; read this to know **when** it was decided, what the
owner's own words were, and what it replaced.

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
- **Written down, not fixed:** marking a crisis answer "wrong" (the thumbs-
  down button) still counts toward "suggest the bigger model" - the crisis
  exclusion above only covers the live phrase-based signal and the
  struggle count. Fixing it needs the turn's crisis flag and its id joined
  across two separate patches (`chat-stream.patch`, which has the flag, and
  `second-card-suggest.patch`, which has the id) - mechanical, but not done
  without the owner's go-ahead given how carefully this project already
  treats crisis handling. **Go-ahead given 2026-09-28: queued as milestone 8**
  (`docs/AUDIT-2026-09-28-REPO-REFS.md`).
- **Fixed 2026-09-28 (the owner said fix it; commit 248227a2):** marking a
  crisis answer "wrong" (the thumbs-down button) used to count toward
  "suggest the bigger model" - the crisis exclusion above only covered the
  live phrase-based signal and the struggle count. Now the chat route hands
  a crisis turn's id to `jarvis_agent.note_crisis_turn` when it makes the
  id (`second-card-suggest.patch`, on `wellbeing.patch`'s flag and again on
  `run_local_turn`'s own check), and `note_correction` does not count a
  mark on that id. `test_wellbeing.py` runs the join end to end.
- The crisis thumbs-down gap written down above is closed by the fix
  recorded just above (2026-09-28, `jarvis_agent.note_crisis_turn`); the owner's
  go-ahead of 2026-09-29 confirmed that fix, and nothing else about crisis
  handling changed.

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
  (gemini.google.com)**, ~~driven openly - at human pace, in a visible
  browser window, with nothing that hides it from or dodges Google's bot
  detection, and no captcha-solving. The owner chose this knowing Google's
  terms forbid automated access and that the account could be closed. A
  request to add "tactics that help avoid bans" was declined: getting round
  a site's bot protection is not something this project builds.~~
  **Reversed 2026-09-29 (owner): "driven openly" and the refusal of
  "tactics that help avoid bans" are gone** - see "Stealth on for
  everything" below. What stays: Jarvis never solves a captcha (it hands it
  to the owner), and the owner chose this knowing Google's terms forbid
  automated access and that the account could be closed.
  **A spare Google account used only by Jarvis**, not the owner's main
  one (owner, 2026-09-28): a ban cannot touch the owner's Gmail, and the
  owner's email and Gemini's memory of them stay out of these chats.
- **Inbox tidy by voice: yes** (owner, 2026-09-28) - archive, star, mark
  read, or move to Trash. One approval card lists every email it will
  touch, approved on screen (never by voice), then Undo. "Delete" only ever
  moves to Trash. The card says when the choice came from reading email
  (outside text). A new named way out of the PC (ARCHITECTURE §4) and its
  own gate action, like sending email. Built (JARVIS-API §95; merged in PR #30, 2026-09-29). Tried against a stand-in mail server, never a real mailbox.
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
  download on the PC, checksum-pinned. Built (JARVIS-API §94; merged in PR #30, 2026-09-29). Nobody has listened to a v1.0 voice yet - the "Hear it" buttons are how to try them.
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
  under rule 3; each host a named way out); (2) **more websites, in a
  visible window like Gemini** (~~driven openly~~ - reversed 2026-09-29, see
  "Stealth on for everything"), each with its own spare account - **ChatGPT, Claude,
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
  **Amended by the owner on 2026-10-11: the phone may raise the limit too,
  with its own fingerprint.** His words: "Let the phone raise it too, with its
  own fingerprint" - a change to his own rule above, made after he asked to
  change the amount "in the settings of jarvis on both the desktop and phone
  app". Asked directly, once the limit was open, he chose the same for a
  PRICE: the phone may correct one too. What that means, in plain words:
  raising a limit is still ONE approval card - Windows Hello on the PC, or the
  asking phone's own fingerprint or PIN (signed approvals, a fresh signature
  for every raise) - while lowering a limit, removing one and correcting a
  price change at once, from either app, with no card at all. A price needs no
  fingerprint because it is only an estimate of what a service costs:
  correcting it spends nothing, raises no cap and takes nothing back. **What
  changed is WHERE a raise may be confirmed, never whether a person confirms
  it**: the raise is still a risky approval on its own, so the PC's own path
  still asks Windows Hello, and a phone with no approval key is still refused
  until it turns signed approvals on. The API key itself is still typed on the
  PC (docs/ACCOUNT-KEYS-DESIGN.md).
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
  itself**, at human speed (~~and never hiding from the site's bot
  detection~~ - reversed 2026-09-29, see "Stealth on for everything"),
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
  working on the PC and phone) - **built (PR #34, 2026-09-29)**, with the
  limits in `docs/ARCHITECTURE.md` section 8; 6. inbox tidy by voice, **Undo for 10
  minutes**; 7. talk-to-type on the PC, **held Right Ctrl** by default
  (changeable in Settings); 8. QR pairing with per-device keys; 9. the
  sneaky-instruction detector test.
  **Corrected 2026-10-08, after a feature review measured it:** talk-to-type
  ships on **Alt+Shift+T**, not Right Ctrl, and `docs/JARVIS-API.md` section 72
  says the same. A bare Ctrl key cannot be a global hotkey in this build - the
  hotkey library wants a real key plus a modifier, and the parser refuses an
  accelerator with no modifier at all - so "held Right Ctrl" was never
  buildable as written. The owner chose on 2026-10-08 to keep Alt+Shift+T and
  have this note corrected, rather than add low-level keyboard-hook code for
  one key. It stays rebindable in Settings.
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
  reads the screen's text only (**changed 2026-09-29: "picture mode", a slow
  picture reader on the processor, is built and off by default - see the
  2026-09-29 screen block near the end of this file**). **Not** always-on watching with a history
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
  **The owner then answered the two open items (2026-09-29):** **a crisis
  question and its answer do not stay in the scrollable thread** (the help
  answer shows once; the chat is still kept in History as "A difficult
  moment"); and **two short warnings are built**: "Continue this chat" says
  when chat history is off that new messages will not be kept, and the
  phone's Live screen says when Temporary is on that the session will not be
  kept.
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
- **Wake-up and falling-asleep animations** for every animal: short (about
  2-3 s), calm, no yawn (the mouth moves only with Jarvis's voice); eyes
  only when waking into an approval, under Still, calm motion or a crisis.
- **A fourth animal: a cartoon monkey** (from the owner's picture), in the
  same style as the others and with every improvement they have. It hangs
  from a vine by one arm and swings gently; it sits on the vine to sleep,
  tail curled round it. **The banana is its orb**: it glows in the state
  colour, as the others' orbs do. A male voice, a touch energetic. It is
  a little more lively than the other three - still smooth and never
  sporadic. Its resting motion targets about 1.5x the panda's.
- **Sharp animals on capable hardware:** when Jarvis detects a capable
  graphics chip and the owner has chosen quality over battery saving,
  every animal draws at full resolution (no soft or jagged edges).
- **The otter gets more detail:** visible fur texture, and small gentle
  waves on the water around it.
- **Sun and moon behind the animals, optional (off by default):** the real
  sun and moon for the date and time - sunrise and sunset, the moon's
  phase (full, waxing, waning) and its rising and setting - worked out on
  the owner's own devices from a town the owner types once on the PC (the
  phone gets it from the PC). Nothing goes online for it.
- **Weather in the animals' scene, optional (off by default):** rain, snow
  or wind. Two sources to choose from in settings: the owner's own Home
  Assistant (stays on the home network), or Open-Meteo online (free, no
  key; it receives the rough location, so turning it on raises an
  approval card, like any new way out of the PC; turning it off is
  immediate).
- **Every animal option lives in one place in both apps' settings** (Still,
  sun and moon, weather and its source, resolution, frame rate, and every
  new one), and **Jarvis can change any of them when asked** ("turn weather
  off", "make the animal sharper"). Asking Jarvis follows the same rules as
  the switch: cosmetic options change at once; anything that opens a way
  out of the PC (online weather) still raises its approval card.
  **Look-and-behaviour options are shared between the PC and the phone**
  (one request changes both); sharpness and frame rate stay per device.
- **A picked frame rate rounds UP** when the screen cannot match it exactly
  (120 on a 165 Hz screen draws 165) - never slower than the pick.
- **New animal behaviours, all four chosen** (after the ideas research,
  `scratchpad` report "animal-ideas"): listening nods in the owner's pauses
  and gestures landing on Jarvis's sentence ends; a focus buddy (works
  quietly beside the owner in a focus session, a stretch at the end; never
  sees the screen, never scolds) and small acknowledgements (a nod when a
  fact is saved - not while App lock or "Hide memory lists" is on - and a
  glow when a long answer is ready); petting (stroke it and it leans in;
  a long press on the phone that does not open Brain); seasonal touches
  from the date (off by default). Each is an option in the one animal
  options place and changeable by asking Jarvis. Still and serious moments
  switch every one off; calm makes them smaller. Never: humming, yawning,
  mood-guessing, reacting to email or screen content, guilt or streaks,
  roaming the screen, anything cute during an approval or error.
- **A fifth face: a cute robot**, fully based on the owner's picture (round
  white body, a big glowing blue visor with arc eyes, teal ear fins and a
  teal chest patch), in the same soft 3D style. **Expressive eyes and no
  mouth; no orb** - the eyes carry the state colour and the expression, the
  ear fins and arms show the state, and while Jarvis speaks the eyes pulse
  with the real voice instead of a mouth. Now and then at rest it **zips
  around inside its own space** and settles back (never across the screen;
  not under Still, calm motion or a serious moment). An energetic but not
  annoying voice by default. It gets everything the animals have (sleep and
  wake, Zs, Still, sky, options, quality). No wave at an approval.
- **Two cute idle moments per face, alternating**, for all five: after the
  face has been resting a while, now and then one plays, then it settles
  back. Calm, never during an approval or error, off under Still and in
  serious moments, with a switch in the animal options.
- **Goodbye and hello when switching faces**, both apps: the leaving
  animal or robot plays a short goodbye (about a second - a little wave or
  bow, then out of view), then the incoming one a short hello (pops in, a
  small bounce, a look at the owner). A non-animal face just fades on its
  side. Under Still, calm motion or a serious moment it is a quick gentle
  crossfade.
- **Variety, never over the top:** every face gets several variants of each
  kind of move (listening, thinking, talking gestures, resting moments,
  the reaction as an approval or an error arrives), picked so the same one
  never plays twice running - all within the existing comfort limits
  (small, slow, eased, never busy). Still, calm and serious quieten them
  as before; approval and error stay attentive and still.

Decided 2026-09-29, the owner's answers on the small animal leftovers:
- **Tighter drawing boundaries for the five faces**, for about 20-30% less
  graphics work, provided nothing is cut off: every pose is compared
  pixel for pixel with the old drawing before it is kept.
- **A 60-frame cap while the AI model shares the graphics card waits for a
  measurement from the owner's PC** (a one-line PowerShell check of the
  graphics card while Jarvis talks, with and without a face showing). No cap
  is built until those numbers are in.
- **The owl's beak opens wider on quiet-to-normal speech**; loud words stay
  about where they were, and it must stay cute, never a wide gape.
- **A thumbs-down on a crisis-help answer is no longer counted** toward
  "suggest the bigger model" - the owner's go-ahead for that one gap in the
  2026-09-27 "written down, not fixed" note. Nothing else about crisis
  handling changes; no crisis content is stored, counted or logged.

Decided 2026-09-29, after the skeptical review of all five faces (the
owner kept the ray-marched drawing; the review found expression, motion and
one state bug to fix, not a new approach):
- **An error gets a still mark on every face:** a thin ring with a gap at
  the bottom, drawn by the apps over the face, never moving. It must not be
  mistaken for the waiting-on-you clock or the not-connected ring.
- **Fewer small idle moves when Jarvis is not being used:** breathing and
  looking around stay; the small happenings (a tail flick, an ear turn, a
  stretch) drop to about a quarter unless the owner has talked to Jarvis
  lately or their pointer is on the face.
- **A focus session no longer shows a sleeping animal:** the focus buddy
  shows, not standby (a manual Quiet stays asleep).

Decided 2026-09-29, after seeing the eyelid preview:
- **The animals get painted eyelids** (red panda, pygmy owl, sea otter,
  monkey): a lid of the surrounding fur over the top of each eye, so an
  error looks worried (a sloped lid), waiting on you attentive (a level lid)
  and dozing sleepy (a heavy lid). It is painted in the surface shading, not
  in the shape, so it costs a little per pixel and nothing per march step;
  each animal gets one new pose value on both apps. The robot has no
  eyelids (its eyes carry the state). The lids obey the same rules as every
  other look: nothing cute or new at an approval or error beyond the plain
  worried or attentive lid, calm and Still quieten them, and the phone's
  60,000 shader budget still holds.

Decided 2026-09-28, after checking two Gemini reviews of the outside
projects Jarvis names (`docs/AUDIT-2026-09-28-REPO-REFS.md` - read it
before acting on any outside review; its disproven findings stay closed):
- **Three separate milestones are queued, none started**, in this order:
  (1) Silero speech detection in the apps for "stopped talking" and
  interruptions (wake-up stays with the wake-word model); (2) Prompt Guard 2
  as a warning only, after the owner gets Meta's access and it is measured;
  (3) "quiz me on my notes" with FSRS, deferred until a note-review screen
  is designed. Details and limits are in that audit, section 6.
  Added the same day, as milestones 4-7: (4) a one-line lesson from each
  "wrong" mark, offered on a card and saved only on the owner's yes; (5)
  multi-hop memory, kept only if the memory self-tests improve; (6) a skill
  that fails twice in a row stops being offered and asks "keep or turn
  off?"; (7) record how much of each prompt Ollama reuses from its cache.
- **Milestones 8-11, the same day:** (8) close the crisis "wrong" gap (the 2026-09-27 re-check above) -
  the owner's go-ahead is given; (9) a "match my speaking pace" setting, off
  to start, both apps; (10) microWakeWord joins the wake-word trial; (11)
  offline developer docs. Details in the audit, section 6.
- **Milestone 12, the same day:** "said again" counts become a small
  tie-breaker in recall - never hiding or fading a fact - kept only if the
  memory self-tests improve.
- **Milestones 13-14, the same day:** LoCoMo's multi-hop questions join the
  memory self-test (before milestone 5), and PrefEval's questions test "From
  now on..." preferences. Test data only (CC BY-NC 4.0), never shipped,
  credited when added.
- **Built the same day:** milestones 7 (the prompt-cache share, shown in
  Brain -> Model in both apps), 12 (the tie-breaker, OFF until the PC's
  numbers improve) and 13 (`eval_memory.py --locomo`). On LoCoMo, words only,
  the entity layer made every number worse - not looked into yet
  (`docs/MEMORY-SCOREBOARD.md`).
- **Copying the owner's own voice stays refused** (`jarvis_voices.py`): a
  Jarvis speaking in the owner's voice could pass its own voice check.

Decided 2026-09-28, after the app-builder suggestions
(`docs/APP-BUILDER-DESIGN.md` has the plan):
- **Jarvis may build apps and write code for the owner** - web apps (React +
  Vite, Android through Capacitor) and native Android apps (Kotlin).
- **Local model first; a cloud model only when Jarvis is stuck.** After a
  set number of failed tries on one step, Jarvis may OFFER cloud help on a
  card listing the exact files and error text that would leave the PC. This
  bends rule 1 for app project files only, one card per offer - never email,
  notes, memory, chat history, settings, `.env` files, signing keys or
  anything that looks like a secret. A project can be marked "never cloud".
- **Every merge into an app and every command (npm, Gradle) asks with a
  card**; a git worktree keeps changes apart but is not a sandbox for
  running programs.
- Offline developer docs (Dash/Zeal docsets): queued as milestone 11 (below).
- **aider is trialled as the coding engine**, locked down: only inside a
  task's copy, no shell commands, no "yes to everything", no analytics, no
  cloud model. Kept only if it beats Jarvis's own file blocks (design doc,
  milestone D2). No second agent framework: one permission model, one
  scheduler.

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

Decided 2026-09-28, the owner's answers after the post-change audits
(`docs/AUDIT-2026-09-28-AFTER-CHANGES.md`; all merged in PR #23):
- **The memory entity layer: test the fix.** Build the "skip very common
  names" fix switched off; the owner runs the memory self-test on the PC
  and whichever setting scores best is kept.
- **Next work: fix the audits' open problems** - the seven smaller
  findings (Lockdown gaps, health words in the private-topic check, "call
  my mum's phone", talk-to-type vs Live on the microphone, Live warming the
  wrong model, the plan card's gaps while it stays off, the hard face
  picker, the widget's App lock line) plus the one-time "Use it / Keep my
  voice" question - in one checked pull request, before bringing in the
  other sessions' newer work.
- **Phone builds publish from `main` only**, not from the old branch.
- **Under App lock, the widgets' buttons open the locked app first, in
  both apps** (the desktop widget's Focus/timer/music tiles and the phone's
  home-screen widget buttons); they do not act on their own. The owner was
  first told, wrongly, that the desktop widget already did this - only its
  approval button did.
- **A goal's weekly check-in needs no card**, like plain repeating
  reminders: it only reminds and never acts.
- ~~QR-code pairing keeps waiting~~ - **changed the same day (owner):
  build QR-code pairing now**, together with per-device keys ("more
  devices"), as the 2026-09-24 decision already said: a QR code with a short
  typed code as the backup, an approval card on the PC before any key is
  handed over, a key per device listed in both apps with its own Remove.
  Designed first in `docs/PAIRING-DESIGN.md`, checked against the real code,
  then built.
- **Each animal keeps its own answer to "Use its own voice?"** (owner, the
  same day, after the feature audit found one "Use it" turned every animal's
  voice on): an animal speaks in its own voice only when "Voice follows the
  face" is on AND the owner said "Use it" for that animal; every animal asks
  once, even after another said yes; until answered it keeps the normal
  voice. The switch stays the master (off = no animal voice).
- **The app builder's projects join Projects**: an app is a coding project
  whose tests are its benchmarks - one list, not two.
- **An animal's answer can be changed later** (owner, 2026-09-28, after PR
  #25 merged): in the voice settings of both apps, an animal answered "Keep
  my voice" gets a button "Use its own voice", and one answered "Use it"
  gets "Keep my voice". No card (the switch it can turn on has none); held
  on a stale link. The backend route already took a new answer.
- **The update guide is kept true after each merge** (owner, 2026-09-28): it
  said QR pairing was "for later" after it was built; it now says what is on
  `main`, which of its steps are old, and adds the half-hour pairing test.
- **Build phase 2 of pairing and the app builder joining Projects now**
  (owner, 2026-09-29, "go ahead and build this"). Phase 2 is
  `docs/PAIRING-DESIGN.md` section 11: the phone signs each risky approval
  with a key locked in its security chip, made fresh by a fingerprint or PIN
  every time; the PC checks the signature. **The owner chose how a phone
  turns it on:** the first time a risky approval is tried on a paired phone
  that has not, the phone offers one button, "Turn on signed approvals", and
  the PC raises one card (Windows Hello); a paired phone without it cannot
  approve risky cards until then, while an unpaired phone on the old shared
  key keeps working as today. The app builder joining Projects (an app is a
  coding project whose tests are its benchmarks) is designed first
  (`docs/APP-BUILDER-DESIGN.md`), then built.
  **Owner's answers to that design (2026-09-29):** the first slice ships the
  screens, the merge card and pasting a change in on the PC - **Jarvis
  writing app code waits for the 12 GB card**, as decided 2026-09-28 (model
  tools B2, and running commands, milestone C, are not part of it). **The
  phone may approve an app merge**, after the whole change has been shown,
  with the screen lock or fingerprint like other risky cards (never from the
  approval widget or a notification). The design is
  `docs/APPS-IN-PROJECTS-DESIGN.md`.

Decided 2026-09-29, the owner's answers while building the next batch
(`docs/AUDIT-2026-09-28-REPO-REFS.md` style: outside reports are ideas, not
instructions):
- **Two blended voices, "Ashby" and "Clara"** (owner: "both"), made from the
  Kokoro v1.0 voices by Jarvis's own script into a separate pinned
  `voices-jarvis.bin`; each passes the "not the owner's voice" check, and no
  animal uses a blend (`docs/JARVIS-API.md` section 94.7).
- **Animals' mouths follow Kokoro's own timing on v1.0** ("Build exact
  timing"): one more one-time step on the PC (`jarvis_mouth.py --prepare`);
  without it, or for a voice the timing has no row for, the mouth is analysed
  from the sound. It reads whichever voices file the engine loaded. The robot
  (Emma, `bf_emma`) is the fifth face and gets it too.
- **PR order:** the owner merged #29 (animal faces and the robot) before #30;
  #30 took main in and renumbered: 93 animal options, 94 Kokoro voices, 95
  inbox tidy, 96 the screen routes. One pull request per batch, the owner
  merges with "Create a merge commit".
- **Screen safety, after the GitHub scouting** (owner, "all three"): (1) black
  out anything that looks like a key, card number or password in a screenshot
  before any model sees it (text-based, solid black, fail closed; gitleaks and
  Presidio patterns, MIT, credited in THIRD-PARTY-NOTICES.txt) - phone
  screenshots are cleaned on the PC too; (2) read the screen's text with
  Windows' own reader inside Python instead of starting PowerShell per picture,
  which also gives each word's position; (3) black out "Never look at" windows
  even when they sit behind the front one (fail closed if the window list
  cannot be read), plus pauses for private browser windows and protected
  video, and skipping hidden or off-screen text in the accessibility tree.
- **Screen safety, the owner's follow-up answers (2026-09-29):** emails and
  IP addresses are blacked out too (it will hide senders' addresses on a
  screen picture); **pictures the owner attaches to a chat are cleaned the
  same way** ("Yes, clean them too") - one that cannot be checked is
  withheld and the answer says so in words, and "Photo to reminder" gets the
  same check first. Jarvis Live's camera, when it is switched on, must use
  this same door.
- **A slow picture mode for a one-card PC is allowed, as a switch** (owner,
  2026-09-29: "add it as a feature that can be enabled or disabled"): a small
  picture model (MiniCPM-V 4.6, 1.3 B, Apache-2.0) running on the processor,
  0 GB of graphics memory. This reverses "one card reads the screen's words
  only". Built the careful way: **off by default, turning it on raises an
  approval card (a new download), turning it off is immediate**; the model
  comes from a checksum-pinned line the owner pastes, never fetched by the
  backend; speed is measured on the owner's PC before anything says "works".
  Everything the model sees is outside text, and secrets are blacked out first.
  Camera/Live pictures still wait for the 12 GB card.
- **Screen safety, built 2026-09-29** (branch `feat-screen-safety`; JARVIS-API
  §62.13): anything that looks like a key, token, password or card number is
  hidden (`[hidden]`, and solid black in a picture) before a look's words or a
  picture are used - the PC's screen and the phone's screen text and
  screenshot alike (`jarvis_secrets.py`, `jarvis_secret_rules.py`,
  `jarvis_picture.py`; `jarvis_screen.clean_picture` is the one door; fail
  closed). The text reader runs inside Jarvis through six pywinrt packages,
  with each word's position, PowerShell kept as the fallback. The PC's picture
  is taken with every "Never look at" window painted black (not only the front
  one), private browser windows and Jarvis's own windows too; a private browser
  window in front is a new pause; ten streaming sites joined the built-in list;
  the accessibility-text walk skips off-screen controls and has a quarter-second
  budget. **Said plainly:** a password behind a show-password eye has no shape a
  pattern can see. Emails and IP addresses are hidden too (a list in
  `jarvis_secrets.PII_KINDS`). Nothing ran on Windows yet: the owner's check is
  `tools\check_screen_safety.py`.

Decided 2026-09-29, the owner REVERSED the 2026-09-28 "driven openly" rule
(asked several times, after being told the ban risk each time; "get rid of
the rule blocking it"):
- **Stealth on for everything (owner, 2026-09-29): the ban risk was
  explained and accepted; Obscura (Apache-2.0) is integrated as a headless
  engine with `--stealth` always on; the visible Playwright browser stays the
  default wherever the owner may have to take over (captcha, sign-in) and for
  the chatbot driver; Jarvis writes no fingerprint-spoofing of its own for
  the visible browser (it is a real browser); no proxy service; no captcha
  solving.**
- **What this replaces:** "driven openly - at human pace, in a visible
  browser window, with nothing that hides it from or dodges Google's bot
  detection" and the declined request for "tactics that help avoid bans"
  (2026-09-28, struck through above), and the support chats' "never hiding
  from the site's bot detection". The backend's approval-card notes (both
  apps just show them) no longer promise "never hides that it is a program" or "never changes
  how the browser looks" - a card note that said so would now be untrue.
- **What does NOT change:** Jarvis itself never solves a captcha - it hands
  it to the owner (the PC window, or "Solve it here" on the phone); no proxy
  or residential-proxy service; nothing private (email, files, credentials,
  memory) goes into a web chat or page (rule 1); every card and approval
  rule; identity checks in support chats are handed to the owner; and **if
  the other side asks directly whether it is talking to a bot, Jarvis never
  claims to be human** - it pauses and hands the question to the owner.
- **The ban risk is real and accepted:** an account on Gemini, ChatGPT and
  the others could be blocked or closed, and each card still names the
  company's terms risk. A spare account used only by Jarvis stays as
  **advice** (a ban then cannot touch the owner's own account), not a rule.
- The typing pause in the chatbot driver (a fixed few milliseconds a
  character, and a pause between messages) stays: it is there so a site is
  not flooded, and nothing in the owner's decision asked to change it.
- **Tests:** the checks that used to fail on any "stealth" or user-agent
  word now say what is still true - no proxy code, no captcha-solving code,
  no spoofing code of Jarvis's own in the visible browser's files
  (`backend/test_chatbot_gemini.py`, `test_chatbot_sites.py`,
  `test_support_widget.py`, `test_handoff.py`). The engine that carries the
  stealth lives in its own files (`backend/jarvis_browser_engine*.py`), not
  in the chatbot driver's.

Decided 2026-09-30, after checking an outside list of learning repos
(`docs/STUDY-FROM-TEXT-DESIGN.md`): the owner said **any rule can change if
the change is worth it**, and chose:
- **A quiz on text the owner pastes or opens**, marked by the local model,
  in a temporary chat, first.
- **Reading a YouTube video's captions is allowed, one card per link**
  (caption text only). This reverses the 2026-09-26 "left out" decision; the
  owner accepts that it breaks YouTube's terms and may be blocked.
- **Grading is local first, cloud on request:** a card lists exactly what goes,
  bending rule 1 for that one quiz. Nothing is built yet.

Also decided 2026-09-30: **study features that need the second graphics card
are built switched off until the card is installed and measured** - a "Study
helper" switch (quiz writing and marking on the second card, possibly with the
bigger local model) and, later, multilingual speech-to-text for spoken
practice. Video/audio download from YouTube stays refused; a second card does
not change that (`docs/STUDY-FROM-TEXT-DESIGN.md` section 9).

Decided 2026-09-30: **chat tags** (`docs/CHAT-TAGS-DESIGN.md`) - History gets
collapsible coloured sections for tagged chats (a starter set the owner can
rename and add to; one tag per chat), and the owner can ask Jarvis to label the
current chat (applies at once, no card) or an older one (Jarvis shows matches and
the owner taps the chat; it never guesses). **No automatic tagging**, and no
tree index or clustering of past chats (ChatIndex, BERTopic and the others were
checked and turned down).

Decided 2026-09-30, the owner ticked every item in `docs/BUILD-QUEUE-2026-09-30.md`
and said any rule can be changed if worth it: **spending summaries from bank
CSV/Excel files** (bank connections such as Plaid stay refused; numbers by code,
screen only), **review decks with py-fsrs and typed Spanish practice** as quiz
modes, **goal step locks, a forecast range and step completion dates**, a
**retirement what-if calculator** ("not financial advice"), **overnight suggested
tags on cards only** (off by default; this reverses the earlier "no automatic
tagging" answer to "no tagging without a tap"), an **activity heatmap and
owner-defined balance chart** (no streaks, no wilting), a **Galaxy facts panel**
and a manual **"new section here"** marker. Also decided: the tldraw canvas,
React Flow, Datasette, Evidence, BERTopic and the other chat-clustering repos
stay refused; the Galaxy is not swapped for a library.

Standing instruction, 2026-09-30: **never open a pull request into `main` (or any
branch) unless the owner asks for one.** (The owner then asked for exactly one, at the end of
the 2026-09-30 batch, to be merged once its checks pass: see docs/BUILD-QUEUE-2026-09-30.md,
"Final sequence".) Work is committed and pushed to the
session's own branch only. This overrides the earlier plans in this file to open
"one pull request" per batch: those wait until the owner says so.

Decided 2026-09-30, the owner's answers on filling in forms and booking
appointments (`docs/FORM-REVIEW-DESIGN.md`; Gemini's browser-use, LaVague,
OmniParser, UI-TARS, Midscene, Stagehand, Agent-S and steel-browser suggestions
were checked and none is added - `jarvis_browser_control.py` already does the
job, one permission model, named elements only):
- **Fill a form, show me, then a separate Submit card.** Jarvis fills the
  fields, stops before the one click marked `final`, shows the owner **a
  picture of the filled form exactly as the page shows it** (nothing blacked
  out - the owner must read their own name, phone and email to check them),
  and raises a **second card just for the Submit click**
  (`browser_form_submit`, tier ask, risky). The picture goes only to the
  owner's own PC and phone: kept in memory only, never on disk, never to any
  model, never in a log, event, notification or widget. This is the one screen
  picture shown without `jarvis_screen.clean_picture`, because it never
  reaches a model. Visible browser only; the headless one has no pixels, so
  its Submit card is text only and says so.
- **The picture is also hidden under App lock AND under "Hide memory lists and
  chat history"**, on both apps (owner, 2026-09-30); a plain line says why.
- **Built before the second card is installed** (owner: "build it now"); the
  form driver itself still needs the 2060 and its "Browser control" switch.
  **No pull request to `main` until the owner asks.** Built 2026-09-30
  (JARVIS-API §98, `backend/jarvis_form_review.py`, `form-review.patch`); not
  tried against a real browser or the owner's real gate.
- **The form page Jarvis opened itself does not count as "outside text" for
  the Submit click** (owner, 2026-09-30, "ignore the form page itself"). Email,
  files, notes, web searches, memories and **a different website read earlier
  in the same turn** still refuse it, as does a model that is not on this PC.
  Known limit, said plainly: an earlier TURN of the same conversation that
  used any tool still taints the conversation, so a form must be opened and
  filled in one turn (the normal flow).
- **A form of several pages** (owner, 2026-09-30): one `browser_control` call
  per page, all in one turn; **up to 8 cards in a turn (instead of 5) while ONE
  website's form is being filled** and nothing else has asked - a card for any
  other tool or a second website puts it back to 5 (a loosening of the
  2026-09-25 limit, for the form only, confirmed by the owner); and **the
  Submit card lists every page's typed words** (JARVIS-API §98.1b), the
  picture staying the last page.
- **Pillow is a named requirement** (owner, 2026-09-30) so a very tall form
  still gets a picture; it was already in `requirements.lock`.
- **Model advice stays as it is** (owner, 2026-09-30, "improve what exists"):
  Jarvis already offers the bigger model when it struggles or is corrected
  twice; better signals are added to that, only after the 2060 is measured. No
  llm-checker, llmfit, hf-mem, RouteLLM or UncommonRoute; never a second
  router, and no "delete models" action without its own card.
- **A numbered-boxes screen-parsing fallback** (the OmniParser idea) is only
  a possible later spec, for pages the accessibility tree cannot read; it
  waits for the 12 GB card, a measurement of how often reading a page fails,
  and the owner's decision on mouse control.

Decided and built 2026-09-30, the owner's answers after the multi-GPU, settings,
notification, card, quick-access and coverage audits (one pull request):
- **Extra graphics cards of 8 GB now work** (floor 7,680 MiB reported, was 10
  GB). An 8 GB second or third card runs Learning, the Wiki builder and (no
  monitor on it) Pictures - work moved OFF the main card - but not "Longer
  conversations" or "Browser control", because an 8 GB card holds no more than
  the main card's 16,384 tokens. 10-12 GB behaviour is unchanged; 16 and 24 GB
  cards get the same qwen3:8b at 32K plan (the 14B would fit but stays off until
  it passes the tool tests). **All sizes are calculated, not measured; no extra
  card is installed.** The third card's approval is now tied to the card's id: a
  different card in that slot, or an old file with no id, counts as unassigned
  and asks again. Known, not fixed: the second card's master switch is not tied
  to a card id.
- **"Look at this" and "Watch with me" use the Pictures graphics-card lane first**
  when Pictures is on and its lane runs; the slow processor picture mode is the
  fallback. Picture mode's own switch still decides whether a picture is read at
  all (owner may revisit). The picture is still cleaned first.
- **Settings fixes:** the email switch wrote a name the tool list ignored
  (`email_read` vs `email_check`) - fixed for all four reading switches. **Web
  search has an on/off switch in both apps** (off instant; back on is one card,
  `web_search_enable`, via `web-search-switch.patch`, which goes AFTER
  `form-review.patch` because both anchor on the gate's last lines). Phone
  voice switches moved to Settings > Voice; Settings has a jump list; greyed
  panels say why.
- **Screen safety:** the secret scan is capped at 25,000 characters and 6 s and
  fails closed; more patterns (`DB_PASSWORD=`, Bearer, US SSN, code-before-label,
  `Passwort:`); a Watch started from the desktop ends after 45 s without a
  heartbeat; a look racing Stop is discarded; an unreadable program name is
  painted black; phone Watch ends after 10 s of a lost link and says it cannot
  see password boxes.
- **Phone hardening:** Live and the handoff screen start only from Jarvis's own
  tiles and notifications (an app-private secret); the approval widget and the
  Mute tile obey App lock; stream start is single-file; every notification id
  is in one place; three unlabeled switches and checkboxes are readable by
  TalkBack.
- **Desktop hardening:** App lock reads each field on its own so one bad value
  cannot switch it off; `backend.log` is capped at 4 MB while running; approval
  toasts are withdrawn when the card is decided anywhere; failure toasts use
  plain words and obey App lock; the focus ring is a solid outline with a High
  Contrast fallback. `'unsafe-inline'` stays in the CSP (12 inline scripts) and
  a test pins the count.
- **Backups:** retention never deletes the file just written and ranks by real
  file time; a restore is all-or-nothing with rollback; the restore card says it
  replaces the memory and chat files; `POST /api/backup/delete-older` (one card)
  is built on the backend - and the desktop's "Delete older backups now" button
  after an Erase is **built too**: `jarvis-desktop/src/settings.html:2368` draws
  it, and `jarvis-desktop/src/backup-settings.js` wires it to the
  `delete_older_backups` command (`src-tauri/src/backup.rs:249`, registered in
  `lib.rs:1161`), which raises the one card. **This line said that button was
  *queued* when the decision was recorded (owner, 2026-09-30); it was corrected
  on 2026-10-13, because the button had been built and the sentence had stopped
  being true.** The phone still has no such button **on purpose**: a phone is
  not this PC, the route answers 403 there, so the screen says "PC only" in
  plain words instead (`jarvis-client/.../net/Backup.kt`).
- **Time:** the PC sends `age_s` for a fired job; "12 at night" is midnight and a
  bare 12 is said back; timers survive a clock set back; DST "last week" and a
  leap-day range no longer crash.
- **Update script:** `-FixLineEndings` rehearses on a converted copy and converts
  the real files only afterwards; the end is a green, yellow or red summary with
  an exit code; a half-patched backend gets a one-line restore; a running Jarvis
  stops the run (`-Force` overrides). Not run on real PowerShell 5.1.
- **Owner decisions recorded, not yet built (queue, in this order). A 2026-10-05
  pass marked every item that is now built; the marks are the record, so read
  them before trusting any line below.** (1) a notification settings screen in
  both apps (per kind: on/off, style, Test button, quiet hours that never
  silence urgent alerts or approvals) - **the desktop screen is built 2026-09-30**
  (`settings.html` "Notifications", `notifications.rs`); **the phone's own screen
  is still open**; urgent alerts break through Do Not Disturb / Focus Assist
  where the system allows, with a note - **built 2026-09-30** (`winrt_toast.rs`'s
  `scenario="alarm"`) - and a late urgent alert follows the silent "Missed" rule
  - **built** on the PC (`brain/schedule.rs`) and on the phone
  (`JarvisRuntime.kt`); reminders and briefings get their own phone channel -
  **built** (`strings.xml`'s `channel_schedule_desc`); (2) tap-to-talk on the
  phone - **built 2026-10-01** (`eabca34d`): a tap starts the clip, a second
  tap or the Smart Turn pause sends it, and hold-to-talk still works; (3)
  quick access: "current task with Stop" and "approvals waiting" as widget
  sources, "graphics memory per card" and "tokens per second" as fixed widget
  sources (marked not measured), edit a saved
  widget, per-widget transparency, accent, high contrast and a live preview
  (**the preview is built 2026-09-30**, `widget-board.js`), and "Pin to home
  screen" for any Brain section or chat; (4) card experience: after any approve
  one line says which Undo exists - **built 2026-09-30 in both apps** (`main.js`'s
  `desktopUndoNotice`, `JarvisRuntime.kt`'s `undoNoticeFor`); past approvals show
  one non-sensitive summary line - **built 2026-09-26** (`9d1dddab`); setup cards
  in plain words; pinned Approve/Deny on long phone cards; a quiet reminder when a
  routine card has under 60 s left; (5) a suggestion line in Brain > Model for a
  16-32 GB first card ("your card can hold the 14B at 32K") - **built 2026-09-30**
  (`brain.js`), and a 16 GB or larger first card counts as capable for Pictures,
  Wiki and Browser without a preset (each still off until approved) - **built
  2026-09-30** (`jarvis_second_card.py`); (6) per-model thinking levels - Off,
  Quick, Deep or Auto, set separately for the everyday model and each lane's
  model, only levels the model supports, default Off, voice answers stay fast, no
  card to change - **built 2026-10-01** (Section 5.5, `jarvis_thinking.py`);
  (7) multi-model work: failover to the main card when a lane fails, a checker
  (bigger model reviews tool plans and code only) and local compare (**local
  compare built**, `jarvis_chatbot_compare.py`), each off by default and measured
  first, plus a per-lane measured log; (8) test hardening (a per-patch "reads
  original text" ratchet, skips no longer count as passes - **the skip half is
  built**, `run_suites.py`; **the ratchet half is built 2026-10-16**,
  `tools/check_patch_original_text.py`); (9) "Restore to before" for an app
  merge (with the app builder, after the 12 GB card); (10) a stale-area check
  after every big merge.
- **Rejected this session (ideas only):** Xinference, LocalAI, GPUStack, Triton,
  a llama-server supervisor, screenpipe (stays rejected), Outlines, STORM, MCP
  filesystem/git servers, Zebar, yasb, tauri-plugin-decorum, json-to-compose
  and a free-form widget renderer, and Skill-Anything / QuizScribe / deepeval for
  learning. The owner asked not to work on educational features for now (a
  note-quiz feature stays queued behind everything else).
- **The Undo shelf, Activity list and 10-minute Undo windows are separate today**;
  the Activity list keeps only the title, decision, time and device.

Decided 2026-10-06: **"Let Jarvis Desktop start and stop Jarvis" is deliberately
instant - no approval card.** The owner considered giving the switch a card and
chose to leave it as it is, and this entry is the record that the choice was
deliberate rather than an oversight:
- **It can only run one program he typed in himself.** The desktop starts
  exactly the **Program** and **Arguments** saved in that same Settings box
  and nothing else (`jarvis-desktop/src-tauri/src/sidecar.rs`:
  `Command::new(config.program.trim())` then `command.args(&config.args)`,
  with the whole `BackendConfig` written by the owner's own Save). There is
  no way to make it run a program he did not name.
- **It takes no power over his data.** Starting or stopping the backend does
  not read, move, send or delete a file, and nothing leaves the PC.
- **It opens no way out of the PC.** It is not a new named way out
  (`docs/ARCHITECTURE.md` section 4) and it reaches nothing on the network.
- So the card an approval would raise would ask him to confirm the exact
  thing he just typed and pressed Save on. Switching it **off** is instant,
  like every other narrowing change in this project; switching it **on** is
  the only direction that changes anything, and it still needs his own Save.
- The switch is **off by default** (`read_supervise`, ".unwrap_or(false)",
  "§5, and the reason is a person's terminal"): a Jarvis he started himself
  in PowerShell is never adopted and never stopped.
- The desktop build brief's own section 5 (`DESKTOP-BUILD.md`, "Supervising
  the backend - and the orphan problem") is why it is built carefully rather
  than not at all: ask `POST /api/shutdown` first, kill the process tree (not
  the process) only if that does not go, attach to a backend already
  listening instead of spawning a second one, and keep it a setting, default
  off.

Decided 2026-10-08, after the owner asked for a prompt-writing helper and
offered four open-source projects to build it from: **the Prompt Coach comes
first, and none of the four is used.** `backend/jarvis_prompt_coach.py` reads
ONE prompt the owner is about to send, and the last few turns (the owner's
answer), and returns a short critique with a rewritten version. It runs on the
model already on the PC and **adds no dependency at all** - because
`promptimal` requires an OpenAI API key and has no local-model support (Ollama
is item 1 of its own roadmap), so using it would have sent the owner's own typed
words to OpenAI, which is rule 1. `textgrad` is a pre-alpha research framework,
`prompt-optimizer` is AGPL-3.0 rather than the MIT claimed, and `promptfoo` is
a fine Node CLI for a different job (regression-testing Jarvis's own system
prompts offline, noted for later). The full comparison is
`docs/PROMPT-COACH-DESIGN.md`.

- **A button, not an interceptor.** The owner was offered a mode that checks
  every message and chose the button, with the switch as the master switch: off
  means no button and nothing read. An 8B model is a mediocre prompt critic, so
  it must not be in the path of every message, and a critique is a full model
  call.
- **Turning it on raises no card, and neither does turning it off.** Written
  down as a decision so nobody "fixes" it later: the coach reads words the chat
  is about to send to the same model on the same PC anyway, takes no action, and
  opens no way out of the PC. The reasoning is in the setter's docstring.
- **The score is never a gate.** A 1 out of 10 is still sendable, "this is
  clear, send it" is a correct answer, and the module's own prompt says that
  inventing a complaint is a failure.
- **It never sends anything by itself and never changes the owner's words.**
  Both apps offer Send mine and Send the suggestion, and nothing leaves without
  one of those presses.
- **It never leaves the PC and keeps nothing.** The address is checked with
  `jarvis_auto_learn.check_local_model()` before the request is built, and no
  prompt, critique or score is written to history, memory or a log.
- **Unmeasured, and said so.** Nobody has run it against a real model, so the
  quality of its advice and how long it takes are both unknown; the app's own
  line under the switch says the advice is sometimes wrong.
- **One thing found on the way, for later:** neither app renders its settings
  from `jarvis_settings_registry.py` - every switch is hand-written in three
  places (the backend's words, a desktop copy, a phone copy) and nothing tests
  that the copies agree. The repo's cure for that exists and is used elsewhere
  (`gen_menu_cases.py` generates both apps' menu catalogues from one source,
  with a `--check` in CI). The owner chose to build the Coach the house way and
  queue "one source for the settings screens" as its own task rather than
  block the feature on it.

Decided 2026-10-08, after the comparison against CopilotKit's OpenMuse
(`docs/COMPETITORS-OPENMUSE-2026-10-08.md`): **the job list comes first, and a
turn hands work to it.** Work that outlives one chat turn is built
(`backend/jarvis_tasks.py`, `tasks.patch`, JARVIS-API section 118): a job is a
named list of steps, one step runs per tick, each step still raises its own
approval card, and the list remembers where it got to through a restart. A
chat turn delegates to a job with `jarvis_tasks.from_plan` after the plan card
is approved, and the gate is reached only through `gate_ask`, so nothing
bypasses it. Five protections came with it: a lease so a crashed job is picked
up again and never run twice at once, a checkpoint after every step,
`outcome_unknown` for a send interrupted by a restart (never `failed`, which
invites a retry), an idempotency key so the same request makes one action, and
a card whose decision must carry the hash of the words that were shown. Both
apps show the list on Brain -> Work. Nothing new leaves the PC.
- **The comparison also produced a correction, and the correction is the point.**
  The report first listed OpenMuse's IP-pinned egress check as a gap to copy;
  `backend/jarvis_local_http.py` had already done it since the 2026-09-27
  security audit, and checks every resolved answer rather than the first. That
  was the third time this project has "gone looking for" something it already
  had (`docs/PEERS.md` recorded the first two). The two real things it did
  earn were closed the same day: the ranges that are never a destination, and
  NAT64, where `127.0.0.1` is spelled `64:ff9b::7f00:1`.

Decided 2026-10-10, the owner's two answers after the integration evaluation
(`docs/INTEGRATION-EVAL-2026-10-10.md`, PR #207, which read eight outside
projects and found one idea worth taking): **the floating face passes clicks
through to whatever is behind it, as a setting that is off by default** -
every click goes to the window underneath except on the animal itself, so the
face stops getting in the way over a full-screen app while the animal can
still be dragged (and stroked, wherever stroking reaches it). It is one
cosmetic switch in the desktop's Appearance card, under "Floating face",
declared in the one settings table like every other row; it applies at once
and asks for no approval card, because it changes only how Jarvis's own face
is shown. The hit test is measured off the face's own drawn picture rather
than guessed from the shader's camera (every one of the five faces reaches
the edge of its square in some pose, so no circle round the middle would do),
and every doubt - no measurement yet, a pointer that cannot be read - leaves
the animal clickable. **And the faces stay as they are: no Live2D and no VRM
importer** - Open-LLM-VTuber and amica both draw Jarvis a different way
entirely, which would *replace* the ray-marched shader faces the desktop and
the phone share (`docs/CRITTERS.md`) rather than extend them, and buy a
second renderer, a second face picker and an SDK licence for it. The one idea
worth borrowing was borrowed as an idea: no code, no dependency, no licence
exposure.

Decided 2026-10-10: **the desktop intro still appears once by itself, and the
owner can replay it on demand** - the walkthrough is no longer a one-shot. The
owner asked directly whether it was "interactive (and skippable) and redoable
if accidentally skipped": the first two were true and the third was not.
`jarvis-desktop/src/onboarding.html` is five plain screens with Back/Next and
Escape to leave, and `commands.rs`'s versioned marker carries the rule "shown
once, never again" - `lib.rs` opened the window only while the marker was
missing, and no command and no control anywhere could open it again, so one
accidental Escape and it was gone for good.

What changed, in the owner's terms: one button, **"Show the intro again"**, in
Settings' "Set up Jarvis" card (`settings.html`'s `#first-run`), beside that
card's own "Set up again" and OUTSIDE its checklist rows - those rows fold away
once set-up is done, which is exactly the state the owner is in when he wants
the intro back. It calls one new command, `replay_onboarding`, which reuses
`windows::show_onboarding` (the same fixed-size, non-resizable window, same
label, same narrow capability) and **reads and writes no marker at all**.

What deliberately did NOT change: when the intro appears by itself. `lib.rs`
still opens it unprompted only while `commands::onboarding_seen` is false, and
`finish_onboarding` is still the only writer of the versioned marker. Clearing
the marker from the replay path would have made the intro open by itself on the
next start, which is not what was asked for. This is replay on demand, never
"show it every launch" - and it is not the first-run checklist
(`src/first-run-settings.js`, the owner's option 8A of 2026-10-06), which
gathers settings and is a different thing.

The new command's whole ACL path, because a command missing any one piece
silently does nothing: `build.rs`, `lib.rs`'s `generate_handler!`,
`permissions/autogenerated/replay_onboarding.toml`, `surfaces.toml`'s new
`onboarding-replay` set, and `capabilities/settings.json` - and that set is NOT
given to the walkthrough's own window, which keeps `onboarding-surface` (mark
seen, close) and nothing more. The button is not a settings TOGGLE row, so
`backend/jarvis_settings_registry.py` (PR #163) is untouched and no generated
catalogue needed regenerating. The stale "shown once, never again" comments in
`commands.rs`, `windows.rs` and `onboarding.html` said otherwise and were
corrected with it.
Decided 2026-10-10, after a Reject click was found shipping a rule in the
owner's name: **a Reject click may be written down, but only as Jarvis's
guess, marked as a guess.** The owner's words: a rejection may become *"a
suggestion, marked as a guess"*, which he **Keeps or Discards** - never
something Jarvis puts in his mouth. What was happening before: when the owner
pressed Reject, `jarvis_gate.py` built the sentence *"Remember this: I do not
want Jarvis to `<action>` without asking me first. I just said no when it
asked."* and handed it to the learner as if it were the owner's own turn. It
was not. A Reject click carries none of his words - the HUD's Reject sends only
`{id, by}`, and the gate NULLs the card's own `prompt` and `detail` when it is
decided - so the sentence was Jarvis's invention, and "I just said no when it
asked" invented a reason for a click that carries none. Facts here are learned
from the owner's own words only (2026-09-24), so **that unlabelled behaviour is
fixed**: the proposal now says in its own words that it is Jarvis's guess, that
it is not a record of the owner's words, and that no reason was given nor made
up to fill the gap - and it names the action, so the guess is worth reading.
The same marking reaches the review card itself (`guessed`, plus the words in
the reason line both apps already show), so it is visible where the owner
actually decides, not only inside the backend. **Everything good about the old
behaviour is kept, and must stay kept:** a timeout still proposes nothing ("the
absence of an answer"), it still only ever *proposes* through
`jarvis_extract.propose()` - the one review queue, never a second door into
memory - the one-card list (`_NO_RULE_FROM_DENIAL`) still excludes a denial
that answers a single card, and a failed proposal still never turns a completed
denial into an error. Keeping the guess is what makes it apply: nothing is
applied until the owner says so. Written down as entry **003** of
`docs/RULE-FLEXIBILITY.md`, with the relaxation's own line on the "What asks
first" page (`fixed:playbook_rejection`, "Writes a guessed rule for you to Keep
or Discard").

Decided 2026-10-13, the owner's two answers about changing settings by asking:
**Jarvis may change any setting when the owner asks in chat or in Live, and ONE
approval card - decided from either app - is what authorises it.** His words:
*"jarvis should be able to change all settings if i ask it to in chat or in the
live mode, if its a big settings change that would impact privacy, security, or
significantly change functioning it should send me an approval card"*. Asked
the follow-up that rule implies, he chose: **"Let a card alone authorise it,
from either app"**. Asked what should take the place of the PC-only Windows
Hello step he had required for exactly these changes, he answered: *"yes, i
should be able authorize any card on my phone with my fingerprint on my phone,
just like using windows hello on my desktop"* - so the phone's own fingerprint
or PIN is his intended equal of Windows Hello, for EVERY card, not only the
ones the risk table calls risky.

**What this replaces**, quoted word for word from the 2026-09-26 entry above:
*"On the PC only, the owner may also loosen a short safe list (note writes, the
wiki, reading their own calendar, email, notes and home status) - one card plus
Windows Hello per change. **Nothing outside that list can be loosened from an
app.**"* Both sentences are gone: there is no short safe list any more, and a
change to something privacy- or security-related no longer has to be made at
the PC. That is a WEAKENING and it is written here as one - the extra step that
guarded exactly these changes is removed, and a card, decided from the phone as
readily as from the PC, is now the gate.

**What still protects it, so the whole trade is visible:**
- **The card is the gate, and it must not weaken.** Every one of these changes
  still raises an approval card naming what will change, and nothing happens
  until the owner decides it. With the PC-only step gone the card is the only
  thing between a request and the change, so its wording, what it lists and the
  "What asks first" page matter more than before, not less.
- **A lock is still required to approve, and this half is BUILT** - verified in
  the source on 2026-10-13, not planned: the phone holds a Keystore signing key
  that needs a fresh fingerprint or device credential for every single use
  (`platform/ApprovalKey.kt`: `PURPOSE_SIGN`, `setUserAuthenticationRequired(true)`,
  `setUserAuthenticationParameters(0, AUTH_BIOMETRIC_STRONG or
  AUTH_DEVICE_CREDENTIAL)`, `setInvalidatedByBiometricEnrollment(true)`), the
  real `BiometricPrompt` runs with that signature as its `CryptoObject`
  (`ui/approval/BiometricGate.kt`), and the signature travels with the approval
  to `POST /api/approve` (`net/SignedApproval.kt`, `JarvisApi.approve`). A phone
  with no such key is refused and told so (`SignedApproval.OFFER_WORDS`). On the
  PC, Windows Hello, as before.
- **"No lock, no risky approval"** (2026-09-25) is UNCHANGED: on a PC without
  Windows Hello set up, or a phone without a screen lock, a risky approval is
  refused until one is set up, with a plain message saying how.

**What is in the way, precisely - the remaining work.** The server does not
honour the phone's signature for the actions this decision is about:
`jarvis_owner_check.PC_ONLY_ACTIONS` (its own list: `loosen_what_asks_first`,
`enable_reading_tool`, `restore_backup`, `pair_device`, `unretire_shared_key`,
`register_approval_key`, `handoff_keep_offering`, `handoff_bring_to_front`)
refuses such a card from any peer but the PC - `if action in PC_ONLY_ACTIONS and
not here: 403, "This card can only be approved on the PC, with Windows Hello,
so nothing was approved"` - and `jarvis_asks_first.py` says the same in words:
*"jarvis_owner_check.PC_ONLY_ACTIONS makes its approval need Windows Hello and
refuses it from any other device, so a phone (or anything pretending to be one)
cannot approve it."* So a perfectly valid fingerprint-signed approval from the
phone is still refused for `loosen_what_asks_first` - exactly the change this
entry is about - and until that list is narrowed, **the phone still cannot
loosen anything**: the decision above is not the shipped behaviour for it. That
module is a protected one (`backend/<file>` and `jarvis-backend/<file>` are kept
equal, and it is carried by `backend/asks-first.patch` with its own patch
history), so this is a deliberate, reviewed change rather than a one-line edit.

This entry is the RECORD of his decision. The behaviour - Jarvis changing
settings when asked, and `PC_ONLY_ACTIONS` yielding to the phone's own lock - is
a separate piece of work.

Decided 2026-10-13: **the desktop's whole Tauri stack moves up one generation,
and `rust-version` moves with it.** Every crate of the Tauri 2.12 generation
declares MSRV 1.90 - read from crates.io's own per-version metadata on
2026-10-13, not assumed - so the single line `rust-version = "1.89"` in
`jarvis-desktop/src-tauri/Cargo.toml` was what held the entire stack one
generation back. Raising it to `"1.90"` is the change that lets the rest move;
it is not a separate errand.

**What moved, as ONE coordinated change** (`Cargo.toml`, versions as resolved in
`Cargo.lock`): `tauri` 2.11.6 -> 2.12.3, `tauri-build` 2.6.3 -> 2.7.2,
`tauri-plugin-updater` 2.11.0 -> 2.13.3 (three minors behind on a security
surface, so this one did not wait), `notification` 2.4.0 -> 2.6.0,
`store` 2.4.4 -> 2.5.0, `single-instance` 2.4.4 -> 2.5.3,
`clipboard-manager` 2.3.3 -> 2.4.2, `global-shortcut` 2.3.2 -> 2.4.1,
`window-state` 2.4.1 -> 2.5.0 (the `=` exact pin dropped),
`window-vibrancy` 0.6.0 -> 0.8.1, plus `wry` 0.55.1 -> 0.57.0 and
`tao` 0.35.3 -> 0.37.1 transitively. On the JS side `@tauri-apps/cli`
`^2.1.0` -> `^2.12.0` (2.12.2 in `package-lock.json`), so the CLI and the crate
name the same generation.

**The two pins the file used to call "deliberate" were the same blocker, and
each had a second half that survives.** Both are now resolved, and neither
surviving half was touched:

- **`window-state`.** The `=2.4.1` pin had exactly one reason: 2.5.0 needs Rust
  1.90. That reason is gone with `rust-version`. The OTHER half of the decision
  did not depend on the pin and still stands: the plugin's default restores
  whether a window was VISIBLE, which would put the HUD on screen before Windows
  Hello while App lock is on. Re-checked in 2.5.0's own `src/lib.rs` rather than
  assumed - `StateFlags::VISIBLE` is still `1 << 3`, `Default for StateFlags` is
  still `all()`, and `WindowState::default()` still has `visible: true`.
  `window_memory.rs` still restricts the restore to size, position and
  maximised, and `visibility_is_never_remembered` and
  `only_size_place_and_maximised_are_remembered` are unchanged and still hold.
- **`window-vibrancy`.** The old comment said 0.6 because `tauri 2.11.6` itself
  depends on `^0.6`, so anything else compiles a SECOND copy of the crate. That
  reasoning was right and inverts with the bump: `tauri 2.12.3` depends on
  `window-vibrancy ^0.8.1` (read from its published dependency list, not
  guessed), so after moving Tauri, **staying on 0.6 is what would duplicate it**.
  The two had to move together, and they did: `Cargo.lock` now holds exactly one
  `window-vibrancy`, 0.8.1.

**One coupling nobody had written down, found by the compiler.** Adding
`Win32_System_LibraryLoader` to our own `windows-sys` feature list. Our
`lock.rs` test uses `GetModuleHandleW`, which that feature gates, but this file
never asked for it: it arrived by **feature unification** from
`window-vibrancy 0.6.0`, which depends on `windows-sys 0.59` with
`Win32_System_LibraryLoader` in its list. `window-vibrancy 0.8.1` is on
`windows-sys >= 0.60, <= 0.61` instead, so the feature stopped arriving and the
test target stopped compiling while the library target still did. It is now
declared where it is used, which is the right place for it: a feature of a crate
already in the graph, not a new dependency, and `windows-sys` itself did not
move.

**What deliberately did NOT move, and why** - each has a recorded reason that a
version number alone would violate: `reqwest` stays `0.12` (`native-tls` /
schannel on purpose, to avoid a second TLS stack; re-checking the newer major's
TLS feature story was explicitly left undone), `windows-sys` stays `0.59`,
`windows` stays `0.61` and `windows-future` stays `0.2` (chosen so Tauri's own
copies are not duplicated - still true after the bump: `windows 0.61.3` is still
required by `tauri-winrt-notification 0.7.3` through `notify-rust`, so the pin
adds no new copy), and `image` (0.25.10), `serde` (1.0.229), `xcap` (0.9.8),
`hound` (3.5.1) and `qrcodegen` (`=1.8.0`, exact) are untouched in
`Cargo.lock`. One duplicate DID appear and could not be avoided:
`keyboard-types` is now both 0.7.0 (`global-hotkey 0.8.0`, via
`tauri-plugin-global-shortcut` 2.4.1, the newest release) and 0.8.3
(`muda 0.20.0`, via `tauri` 2.12.3). `reqwest` 0.12 + 0.13 and the four
`windows` / five `windows-sys` copies were already there before this change.

**Still blocked, unchanged by this:** the `sonora` crate needs Rust **1.91**, so
it stays out either way. This move takes the floor to 1.90, not to 1.91.

Decided 2026-10-13: **deleting a reminder that has already gone off must work.**
His answer to the parked question in `docs/defect-register.tsv`'s DEF-008 row -
"if the owner wants a way to clear a fired entry, that is a product decision" -
was to **make `delete` work on a fired entry**, rather than leaving it (the
entry ages out of "Just went off" an hour later on its own) or shortening the
hour it is shown for. The defect it closes: the READ route put a job that went
off under `went_off` for `WENT_OFF_SHOWN` (an hour) while the WRITE route refused
the very same id with 404 `no_such_job`, "That is not on the list any more." -
so the PC listed an entry it would not let anyone clear, and the phone showed
the two answers contradicting each other. `snooze` was already routed before
that state gate; `delete` now is too, and **it is the only verb that gained
this**: `pause`, `resume`, `done` and `add_time` on a job that has already gone
off still refuse, and their answer is now the true one, 409 "It has already gone
off.", instead of a 404 saying it is not on the list while both apps are showing
it. Nothing about the two time windows themselves changed - a fired job is still
shown for an hour and kept for a day (`FIRED_KEEP`) - and snoozing one is
untouched. The change is in `backend/jarvis_schedule.py` and its byte-identical
twin `jarvis-backend/jarvis_schedule.py`, on the branch
`fix/def008-delete-a-fired-reminder`.

## 2026-10-13 - the settings tool ships ON, on the PC and for a fresh install

Asked directly, with the choice in front of him, the owner said: **"yes turn it
on for my pc. it should also be enabled by default."**

What that decided, in plain words:

* **A tool the AI model can call to change a setting** (`change_setting`,
  JARVIS-API section 130) is now named in `[tools].enabled` in the shipped
  `jarvis-framework.toml`, so a fresh install has it from the start. It is the
  **second** tool ever to ship switched on; `web_search` was the first (his
  decision of 2026-09-25, reconfirmed 2026-09-27), and until today the file
  said plainly that nothing else was on.
* The reason it is narrow enough to ship on: it reaches **Jarvis's own
  switches and nothing else** - never a file, a folder, a key, an email or
  anything outside the PC - and it decides no tier of its own. It calls the
  same per-setting function a spoken sentence calls, so a cosmetic setting
  applies at once and anything that **loosens a rule, reads or reaches more, or
  touches privacy or how Jarvis works still raises that setting's own approval
  card**, with its own risk text and its own Windows Hello rule. Turning it on
  cannot weaken rule 4, because the cards it raises are the cards that were
  always there.
* **On his own PC** the name was added to the list actually in force, which is
  `~/.openjarvis/config.toml`'s `[tools] enabled` - not `jarvis-framework.toml`,
  which on his machine has no `[tools]` section at all and so never overrode the
  inherited template's list. His file was backed up first
  (`config.toml.before-change_setting-2026-10-13`) and the result validated as
  TOML.
* **It takes effect only when that PC's backend has the code**, which is an
  `apply-patches.ps1` run. Until then the name is silently ignored - the same
  silent filtering `offered_tools()` has always done for a name that is not a
  tool here. This is recorded because it is the difference between "switched on"
  and "working".

This replaces the earlier position in the same day's work that the tool "ships
OFF, like every tool but `web_search`". That was the safe default while the
choice was still open; it is no longer what the project does.

Decided 2026-10-13, the owner's explicit answer to a question the audits left
open on 2026-09-25 - **idea I-1**, question 1 of
`docs/creativity-2026-09-25/rules.md` section 6:

- **A web search asks first only when private words could actually end up in the
  search.** This is a LOOSENING - fewer cards, less asking - so it was put to him
  as one, and he said yes; the project's rule is that loosening anything
  privacy-related is his call and asks first.
- **It is the same rule as the 2026-09-25 entry above, which landed then, so NO
  CODE CHANGED for this entry.** What this adds is the record of his explicit yes
  to it *as a loosening*, and the proof that the behaviour now shipped is the
  behaviour he chose. It was checked on 2026-10-13 rather than assumed.
- **Where it lives in the code.** `jarvis_agent.web_search_card_lines` builds the
  card's reasons; the memory reason asks `jarvis_search.repeated_facts`, which
  needs the SEARCH WORDS to match a saved fact's own words (words the owner used
  themselves do not count), plus `jarvis_search.fact_topic` for sensitive facts.
  A pinned "Always keep in mind" fact on its own therefore raises no card - it is
  added to every question, which is what made it the most frequent unneeded card
  (`docs/creativity-2026-09-25/experience.md` section 0.4).
- **Verified on 2026-10-13** in `.dsh-scratch/wt-searchask`, `JARVIS_BACKEND`
  unset: a pinned, non-sensitive fact with a plainly public search -> **no card,
  0 lines**; a sensitive saved fact with the same public search -> **a card**,
  whose exact line is *"Jarvis used a saved fact about health for this question,
  so it asks before searching - something private could be in the search words."*;
  search words that repeat the fact -> a card; `backend/test_web_search.py` ->
  343 passed, 0 skipped, 0 failed.
- **What deliberately did not move:** sensitive saved facts (health, money,
  passwords and account details, and private details about other people), search
  words that repeat a saved fact, outside text read in the conversation, pasted or
  shared text, the owner's own "Ask before every web search", and password-looking
  words refused outright, which is never a card. Every card still shows the exact
  search words and says why in plain words.


---

## 2026-10-14 - "Also restart the lane automatically when it dies"

**His words, in full:** *"Also restart the lane automatically when it dies."*

**What it replaces.** PR #409 (2026-10-13) made both apps SAY the local model is
not running, on a standing line, and deliberately made that line **act on
nothing**. PR #418 added one button to it - "Start the local model" - which runs
his own Windows logon task. Neither answers the defect he has actually been
living with: **the lanes die silently and repeatedly**, today at 08:19:11, with
both scheduled tasks still reporting `Result=0 State=Ready` while nothing was
listening. Nobody is at a screen at 08:19 to press a button.

**What he gets.** The BACKEND now watches the lane itself - one daemon thread,
one loopback `/api/tags` probe every 30 s, no model call - and restarts it
through **the same one action as the button**: his own task, found on that PC by
the stable half of its name, `["schtasks", "/run", "/tn", <name>]` as argv, never
a shell. The limits are 2 down beats (about a minute) before the first try, at
most 3 tries in one episode, a 5-minute cooldown that doubles to 10, and an
episode ends only after **10 minutes of the lane really answering** - so a
flapping lane cannot hand itself a fresh three attempts. **At the cap it stops**:
the state goes back to plain `down` and what remains is exactly #409's warning,
with #418's button still there. Both apps say what happened, in the backend's own
words ("Jarvis started the local model again at 08:19, because it was not
running."), and a chat turn never waits on a restart.

**The decisions inside it, recorded because they are his kind of decision:**

- **No approval card, in either direction.** The house rule is the Docker one -
  *"starting a service gives Jarvis more, so it asks"*. This is deliberately not
  that case: what is started is the lane the chat is pointed at, which this PC
  already starts by itself at every logon with no card and nobody asked, and a
  card could not be answered at 08:19 anyway - it would sit for its 900-second
  timeout, expire, and be raised again on the next attempt. That is the defect
  plus a queue of expired cards. It is bounded, reversible and said, it opens no
  socket that was not already open, and **nothing is auto-approved**: this path
  raises no card and answers no card, so rule 4 is untouched. Full argument in
  `docs/ARCHITECTURE.md` §3 and `docs/JARVIS-API.md` §134.4.
- **A deliberate stop cannot be told from a crash, and this does not pretend
  otherwise.** `schtasks` reports the same "Ready" whether the lane crashed or
  was closed on purpose. So there is one switch (`POST /api/model-lanes/auto`,
  off in one immediate press from either app, on by default because that is what
  he asked for), and every automatic restart is announced. **The residual risk is
  stated plainly wherever this is written down: with the switch on, Jarvis will
  start a lane he stopped on purpose, and will tell him it did.** Only he can say
  which it was.
- **Both apps, and nowhere one-sided.** One sentence, written by the backend, is
  drawn verbatim by the Jarvis bar, the widget and the phone. The HUD window
  keeps only the standing line for the reason it already had no button
  (`hud_proxy.rs`'s five-read allow-list).

**Verified at the desk** (nothing below touched his lanes; every check injects
its own probe and its own stand-in for the start): `backend/test_model_lanes.py`
159 passed, 0 failed; `jarvis-desktop/tests/lane-auto.mjs` 16 checks, wired into
`npm run test:ui`; `./gradlew testDebugUnitTest --offline` 2,346 tests, 0
failures; `tools/check_parity.py`, `check_feature_list.py` and
`check_docs_map.py` clean. See the CHANGELOG entry for the full list.

**Seven checks were red on the base branch before this work, and are fixed with
it.** #418 put `model-lanes.patch` at the tail of the patch stack without
carrying it through the checks that pin the tail: five backend suites
(`test_devices.py`, `test_gate_risk_rows.py`, `test_gate_touches.py`,
`test_referee.py`, `test_screen_attach.py`) keep an allow-list of the patches
written after them, and `test_uncensored_optins.py` plus
`jarvis-desktop/tests/pictures.mjs` named the loader's old neighbour and its old
anchor line. Each was run on `feat/start-the-lane` **unmodified** first and
failed there identically, so this is the branch's own state, not something this
work broke. All seven are green now.

Decided 2026-10-13, the owner's three answers after being asked the multi-device
questions as short multiple choice (`docs/MULTI-DEVICE-DESIGN.md` section 4, and
`.dsh-scratch/multi-device-questions.md`; the worked questions were task-51):

- **The laptop / other-PC client: START IT NOW** as the main piece of the
  multi-device work. It is the largest item in that design - a client mode in the
  desktop app, a second credential store on the other machine, its own pairing
  screen - and a client cannot approve risky cards, because Windows Hello on that
  machine proves nothing to this PC. **The client mode itself is NOT built yet**;
  what this change lands is the backend half it needs (below), so a non-phone
  client is no longer recorded as a phone.
- **Who may approve a new device - a LOOSENING, with his explicit yes:** a phone
  that already signs approvals may also approve a *new* device. It is recorded as
  a loosening because it is one: until now `pair_device` is in
  `jarvis_owner_check.PC_ONLY_ACTIONS` and a device can never approve a device.
  **It is NOT built, and must not be built before the phone signing half is
  proved on a real phone** (a fresh fingerprint per risky approval, and the four
  words matched against the card - `docs/MULTI-DEVICE-DESIGN.md` section 1 says
  that last mile has never been proved on hardware). Nothing in this change
  touches that gate; the PC-only rule stands until that proof exists, and the
  proof is a later, separate piece of work.
- **Nothing else per-device, for now** - no per-device notifications and no
  "quiet this device" switch. Only the animal's sharpness and frame rate are
  per-device (`jarvis_animal.py`), and that stays. **Written down for whenever it
  is revisited: quieting one device must never hide an approval card.** A card is
  how Jarvis asks, and a device the owner has quieted is still a device he must
  be able to answer on.

Decided 2026-10-13, after he asked whether a cloud model could "take over
Jarvis's brain": **the cloud lanes are for background work and genuinely hard
questions only - `jarvis-escalate`, `jarvis-critic` and `jarvis-bulk`, the three
he already has configured in `~/.openjarvis/litellm-proxy.yaml` (OpenRouter's
free tier). Ordinary conversation stays on this PC, and rule 1 remains a
guarantee for it.** His question and this decision are deliberately NOT the same
thing: what is being switched on is a lane a hard question may be *offered* to,
not a cloud replacement for the everyday model. The everyday chat, the voice
turns and the approvals are untouched by it.

**What this replaces:** nothing was previously switched on at all. Until this
entry the whole lane was inert - `ARCHITECTURE.md` recorded cloud use as "per
use, with permission ... No standing grant", and the router has always refused to
escalate on its own (its gate 6, the owner's decision of 2026-09-24: *"any long,
non-private question went to the first cloud lane, and the owner saw a Cloud
badge afterwards"* was the old behaviour that was removed). So this narrows
nothing and widens nothing in what may leave the PC; it only makes the existing
offer reachable, which it was not.

Decided 2026-10-13, the precondition the code itself demanded: **Jarvis stops
injecting the owner's saved facts into every request.** His words, asked exactly
that: *"Yes - stop injecting my facts into every request."* He was told plainly
that this changes his everyday chat, and agreed knowing it.

**Why it was required, in the code's own words** (`backend/cloud-say-yes.patch`,
lines 10-12): *"While Jarvis injects memory itself we cannot escalate safely: it
would attach your facts to a free-tier cloud request."* That is why
`jarvis_hud.py` passed `lanes=[]` and every cloud lane was hard-disabled while
`[agent] context_from_memory = true` - and his own routing log said so on every
turn, `gate: "privacy"`, `reason: "escalation off while Jarvis injects memory
itself"`.

**What this replaces, said plainly because it is a real change to his chat:**
the setting he had, `context_from_memory = true`, was **switching the memory
block OFF**. The name reads the other way round and that misled the brief for
this work; the code is `if decision.inject_memory and ROUTING and not
jarvis_side_memory:` (`jarvis_hud.py:4819`), so `true` meant "Jarvis is injecting
it itself" and the block was skipped. Changing it to `false` therefore **turns
his saved facts back on for local answers** - it does not take them away. That is
the opposite of a regression, but it is a behaviour change and it is recorded as
one. **Measured 2026-10-13 on his PC:** the same question returned
`gate: "privacy"` before the change and `gate: "complexity"` after, which is the
gate moving past the memory check.

**One honest limit on that measurement.** His memory store holds **0 facts**
(`~/.openjarvis/memory.db`, `SELECT COUNT(*) FROM facts` -> 0), so
`injected_facts` was 0 both before and after. The change is proven to have
**enabled the path** (the gate moved); it could not be shown to **change an
answer**, because there is nothing saved to recall. When he saves facts, this is
where they will appear.

Decided 2026-10-14, from the field test that measured it
(`docs/FIELD-TEST-CLOUD-ESCALATION-2026-10-14.md`, its section 6, and the same
day's four escalated calls): **when a cloud answer comes back empty and the
reply carries the model's own working-out, Jarvis shows that working-out under
one line that says what it is - rather than raising the answer cap or turning
his thinking off.**

* **The measurement that forced the choice.** Four escalated turns driven
  through the live `/api/chat` (two `stream: false`, two `stream: true`): all
  four `finish_reason: "length"`, `len(content) == 0`, and 2048 of 2048
  completion tokens spent on `reasoning_tokens`. Read back off the live SSE
  stream: *"chunks with visible content: 0, chunks with reasoning only: 2048"*.
  DeepSeek's thinking mode is ON BY DEFAULT, its thinking is billed INSIDE
  `max_tokens`, `max_tokens` defaults to 2048, and nothing in the program read
  `reasoning_content` at all - `git grep -n reasoning_content` matched nothing
  on that day's `main`. So the hardest questions, the only ones that earn an
  offer, bought a blank card: **$0.0099 for four blank answers.**
* **The two changes he did NOT choose, and why that is the point.** Raising the
  cap for a cloud lane and turning thinking off for `deepseek-flash` were both
  on the table, and both change what he is billed for or what the model does.
  He chose to leave the request exactly as it is and show what came back.
* **What it is not.** Not a replacement, and not silent. A reply with any
  visible text is passed through **byte for byte**; a reply whose only text is
  the working-out is shown under one line naming it
  (`REASONING_NOT_ANSWER`), so it cannot be read as a finished answer; a turn
  with neither says so in one plain sentence (`NO_ANSWER_AT_ALL`) instead of
  rendering an empty card; and anything unreadable is passed through untouched,
  because a filter that lost an answer would be worse than the blank it fixes.
* **Where it lives.** The rule is in `jarvis_chatbot_api.py` and its
  byte-identical twin `jarvis-backend/jarvis_chatbot_api.py`: `CloudAnswer`
  rewrites a streamed or whole-JSON cloud reply, and `reasoning_answer()` is the
  same law where a whole reply is parsed (`ApiChatbot._parse`). The wire is
  `jarvis-backend/jarvis_hud.py`'s cloud relay, which now runs the service's
  bytes through it and still hands `jarvis_speed`'s meter the **service's own
  bytes, in the same order** - so what the turn is recorded as spending cannot
  move because of this.
* **Deliberately unchanged:** the request itself (model, cap,
  `reasoning_effort`), the local lane (jarvis_agent has its own `<think>`
  handling), the money (`_count_money` counts the ORIGINAL text, so a guessed
  token count cannot become the working-out's length), and every client - the
  added line is text, so the HUD page, the desktop window and the phone need no
  change. A flag in the reply's headers was the alternative and was turned down:
  on a streamed reply the headers are on the wire before the first byte of the
  body, so the flag could not be known at the moment it would have to be
  written.
* **One thing this does contradict, said plainly:** `jarvis_thinking.py`'s
  docstring says "Thinking text is never shown, saved or learned from." That
  stands for every ordinary turn - thinking is still switched off per model and
  never reaches a client - but a cloud reply that wrote nothing else is now
  shown, marked, because an empty card is not an answer either. The working-out
  is not saved as a fact and never reaches the event bus.

Decided 2026-10-14, found while fixing the above and settled the same day:
**`docs/DATA-BACKUP.md` stays ONE filename carrying BOTH backup pages, each
under its own clear heading, and whoever merges second combines them.**

* **The state this is about, checked rather than assumed.** The path is on no
  branch of `main` (`git cat-file -e origin/main:docs/DATA-BACKUP.md` exits
  128). **Four** open pull requests add it, and they are two different documents:
  #403, #406 and #407 are three versions of ONE page, the weekly SQLite snapshot,
  titled `# Your Jarvis data, and the copy that now exists`; **#414** is a
  different page entirely, the app's own encrypted `.jbak` backup, titled
  `# The app's own backup: what it covers now` (123 lines). Whichever family
  merges second hits an add/add collision on that one path.
* **The headings to use, so the combining is mechanical.** The page that merges
  first keeps its own `# ` title as the page's title. The second one's `# ` title
  becomes a `## ` section heading - `## The app's own backup: what it covers now`
  - with its own `## ` subheadings demoted to `### `. Every fact from both
  documents stays and nothing new is added. (Naming one top title for the pair
  and demoting both halves to `## ` is equally acceptable; what is not is
  dropping either half, or renaming the file.)
* **Why not two filenames.** Both documents are about the same subject - the
  copies of his data - and a reader looking for "the backup page" should find
  both tools and what each one covers. It is also the smaller change: the four
  PRs already carry links to this path.

## 2026-10-06 and 2026-10-07 - six decisions that were only on a branch until now

Six decisions the owner made on 06 and 07 October were written down only on the
branch `next-claude-shortlist`, which never merged. Its 58-line addition was for
the shape `CLAUDE.md` had **before** the 2026-10-12 split moved the dated
decisions into this file, so it could not be merged as it stood - and a search of
the whole tree on 2026-10-16 found **none of the six** anywhere: not in
`CLAUDE.md`, not in `docs/DECISIONS.md`. They are recorded here, in the branch's
own words, so that retiring the branch loses nothing.

**The first of them reverses a decision recorded above**, which is the reason
this is a correction and not only an addition: the 2026-09-28 entry says *"The
desktop HUD's own chat box opens the Jarvis bar instead, so the PC has one chat
box"*. That was replaced on 2026-10-06.

- **2026-10-06 - the big Jarvis window gets its own chat box back.** This
  reverses the 2026-09-28 "the PC has one chat box" decision. Typing there is
  its own conversation, kept in History as HUD, and that window has no
  Temporary chat, no New conversation, no "Used in this answer" and no crisis
  panel. The owner was told those limits and accepted them. The "Open the
  Jarvis bar" button stays in that window, beside the box.
- **2026-10-06 - anything needing a key or a sign-in should be settable in the
  Jarvis app itself**, desktop only, stored under rule 3 (Windows Credential
  Manager for a secret; never a plain-text key file). The phone is never asked
  for an account secret.
- **2026-10-06 - the chatbot API keys and the monthly money limits are one
  piece of work, not two.** A key with no limit leaves the service unusable, so
  the keys box and the limits ship together. Raising a limit is a loosening and
  takes a card plus Windows Hello; lowering one does not.
- **2026-10-06 - the agent runs the patcher; the owner does not.** When the
  owner says "patch Jarvis", the agent does the whole thing: quits Jarvis,
  brings `C:\Users\pcadmin\Documents\jarvis-update` up to `main`, runs
  `scripts/apply-patches.ps1` against the installed backend, reads the verdict,
  restarts Jarvis and re-runs the preflight. He had been pasting that command
  by hand for a long time and was never told it could be delegated; offer it,
  never wait to be asked.
- **2026-10-07 - the agent watches CI, fixes it and re-runs it without being
  asked.** A red job is diagnosed, fixed if the fault is ours, and re-run by the
  agent; a run cancelled by the concurrency setting (`cancel-in-progress: true`,
  which shows its killed jobs as failures) is re-run rather than reported as a
  test failure. The owner should never be the one to notice a red or cancelled
  job, and should never have to ask for the re-run. Say what was done
  afterwards, plainly - the diagnosis, the fix and the new result.
- **2026-10-07 - the agent owns the pull requests, and merges them.** The owner
  asked for the work rather than doing it himself, so the agent keeps the whole
  board: watches every PR, resolves conflicts (every PR appends a CHANGELOG
  bullet at the same spot, so each merge makes the others conflict), refreshes
  the published base when a shipped module changed, re-runs a job killed by the
  concurrency setting or by a runner fault, and presses Merge in the order that
  costs the fewest fix-ups. This replaces the 2026-09-26 note that the owner
  presses Merge; he can still press it himself whenever he wants.

## 2026-10-16 - the card is answered where it is shown

Asked by the owner the same day, in his own words, as his top priority:

> "when i click open the card from the notification, it opens the jarvis bar
> with no additional information. it should open the card itself. i should also
> be able to approve any card from the jarvis hud directly on my desktop and
> not need the jarvis widget or jarvis bar to do so"
>
> "also after i click open the card and type into the jarvis bar that i
> approve, nothing happens. i have no idea what happens"

**Decided: all three are real and all three are fixed, and the HUD answers a
card through the SAME `decide_approval` the Jarvis bar and the widget call -
never through a second permission path.** What that means concretely:

* **The bar grows to the card a notification opened it for.** The quickbar is
  collapsed to its base height every time it is summoned from hidden, and the
  page sizes the window to what it measures; the stylesheet capped that
  measurement at the window's own height, so the loop could never close and the
  card - with Approve and Deny - sat outside an 80px window with no scroller
  height to reach it through. The cap is now the window's own clamp, held to
  `windows.rs`'s `QUICKBAR_MAX_HEIGHT` by a test.
* **The HUD's card has real Approve and Deny**, granted as one command
  (`hud-approvals` -> `allow-decide-approval`). Windows Hello, the stale-link
  refusal, the cut-off refusal and the App-lock rule apply there unchanged, and
  the page's own `fetch` still cannot post a decision: `hud_bootstrap.js`
  refuses `/api/approve` and `/api/deny` whatever the link is doing. This
  supersedes the 2026-09-25 rule that the HUD shows cards and answers none
  (apps security audit M2) - that rule existed because the page's own POST had
  none of those checks, and it still has none, which is why the command is the
  only door.
* **Typing the decision works, and nothing is inferred.** Only a message that
  IS the decision ("approve", "i approve it", "deny") decides, and it goes
  through the same `decideApproval` the two buttons call. A message that only
  sounds like one ("yes", "ok", "go ahead") is answered with words saying which
  button to press, and an APPROVE on a card `quickActionable()` refuses (it
  carries `raised`) is refused with words too. A card that is not on screen -
  Esc puts one aside without deciding it - is never answered from a typed word.

## 2026-10-16 - a sensitive answer stays on screen in the HUD too

Put to him the same day, with the finding that the HUD window - the one
surface that reads a **typed** answer aloud - ran none of the private-answer
rules, and his answer was:

> "Gate it - keep sensitive answers on screen in the HUD too."

**Decided: the HUD stops speaking an answer that used a sensitive saved fact,
and one the PC gated as private, and shows the bar's own line instead.**
What that means, and what it does not:

* **It is the bar's rule, not a second one.** `hud_bootstrap.js` (section 2e)
  wraps the HUD page's own `speechSynthesis.speak` and refuses when the route
  the page already has - the `X-Jarvis-Route` its chat header carries - says
  `injected_sensitive` above 0 or `gate: "private"`. That is step 3 of
  `docs/JARVIS-API.md` §16 read off the same fact, and the missing route
  case gates nothing, exactly as the bar reads it.
* **What he sees is the existing sentence**, `"It's on your screen."` - the
  bar's own `PRIVATE_LINE` (`private-speech.js`), drawn under the answer.
  No new wording was written for this.
* **It removes one exception, in one window.** The documented rule was
  written for a **voice** answer, and a typed question is otherwise allowed
  to be read aloud (`jarvis_voice.may_speak(private, origin="typed")`). The
  HUD is the only window that speaks typed answers, so that exception is
  removed there and nowhere else: the bar, the widget and the phone are
  unchanged. This is a decision, not an oversight, and `tests/hud.mjs`
  drives the real window once per route to hold the gate against
  `usedSensitiveFact` so the two cannot drift.
* **The local-voices-only rule stays.** That wrapper already refused
  Microsoft's "Online (Natural)" voices, which send the text to Microsoft to
  be spoken; this gate stands in front of the same call, it does not replace
  it.

## 2026-10-18 - said-I'd-do suggestions stay opt-in, and speculative decoding is measured and turned down

Put to the owner on 2026-10-18 as a set of multiple-choice questions. The
answers below are his choices; they decide what gets built when each slice
starts.

**Decided:**

* **Said-I'd-do suggestions are OFF by default, and opt-in in Settings.** Jarvis
  may read the owner's OWN words for a promise he made ("I'll send that
  Tuesday") and offer it as a proposal - only when he turns the setting on,
  only tap-to-accept (never auto-created), and **a proposal that is not taken
  lapses after three days** (`PROPOSAL_TTL_DAYS=3`). Temporary and crisis words
  are never scanned, assistant and tool words are never scanned, and everything
  is withheld while memory lists are hidden or the app is locked.
* **Pillar 24 (selection co-pilot): the trigger is reading the highlighted
  selection when the Jarvis bar opens.** No new global hotkey is added -
  Alt+Space already belongs to the bar.
* **Pillar 27 (routines): Option B is the default** - a saved routine may also
  make changes, with everything it did listed in one consolidated receipt.
  Settings offer **Option A** (read-only / low-risk steps, allow-listed when the
  routine is saved; anything riskier raises a normal card) and **Option C** (a
  card every run). **Caveat, still to be confirmed with the owner:** in Option B
  high-risk actions raise a card whatever the setting says - moving money,
  credentials or API keys, sending email or messages to other people, deleting
  data, public posting. That is an assumption he can override explicitly, not
  something he has already agreed to.
* **Pillar 25 (life-log): Option B is the default** - read-only plates, plus a
  local-model tool that may read the timeline to answer "what did I do
  Tuesday". Settings offer **Option A** (plates only; no model sees the
  timeline). Local model only; withheld under hide-memory / App-lock; a
  timeline read taint-latches the answer.
* **Pillar 12 (Scribe): full meeting capture is the default** - all voices,
  transcript kept - and the owner-only / transient-audio mode is available in
  Settings. Scribe is still **OFF by default**: starting a session offers the
  mode choice, a persistent red banner shows while recording, one tap stops it,
  and raw-audio retention is its own switch. (Exact retention length and the
  per-app banner wording are still open, to settle when that pillar starts.)
* **Pillar 13 (speculative decoding): tried, measured, DO NOT BUILD.** The owner
  asked to try the model-switch MTP route anyway; it was measured on this PC on
  2026-10-18. Only `qwen3.5:0.8b/2b/4b` in the local store carry MTP heads;
  `qwen3.5:9b` has none and the engine refuses it ("model doesn't contain MTP
  layers"); every MTP-capable model is smaller than today's `qwen3:8b`. The best
  lossless result was `qwen3.5:4b` MTP at **0.90x** plain decode (n-max 1 was
  0.96x and changed the answer) - below the `N_placeholder` 1.15x gate.
  `jarvis-primary` was never evicted and both cards were restored; no Modelfile
  or model was created. Evidence: `.dsh-scratch/PILLAR29-MEASUREMENT.md` section
  9 and `.dsh-scratch/pillar29-raw/`. **Reopen only if a future MTP-capable
  8-9B model lands.**
* **Priority order until further notice:** GTD end-to-end -> Pillar 24
  (selection chip) -> Pillar 27 (routines) -> Pillar 17 (code visual docs) ->
  the rest of the queued work, as much as can reasonably be done.


* **The chat-to-job plan card is `CLOSED_BY_MEASUREMENT` (2026-10-18).** The
  first real multi-step tool-planning eval on this PC passed **1/8 = 12.5%**
  against the **90%** bar (`tools/tool_eval/ollama_tool_eval.py`, eight
  multi-step cases), so `jarvis_plan.py`'s freeform "one card, several steps"
  card is not merely dark: it is closed by that measurement on the current
  8B/9B local models. `jarvis_plan.enabled()` now also binds a passing result
  to the **current everyday model name** - read the way chat reads it
  (`JARVIS_LOCAL_MODEL`, then `jarvis_models.current_model()`, else chat's own
  `jarvis-primary` default) - on top of #570's **90-day** freshness. A fresh
  pass for another model, or a file whose recorded model does not match the
  model of the day, is refused in plain words naming both. **Reopen only after
  a fresh eval on the everyday model of the day clears `MULTI_PASS_RATE = 90%`
  with `carried == 0`; switching to a future model forces that fresh run by
  construction, because the recorded model no longer matches.** Evidence: the
  2026-10-18 competitive-benchmark review (Part I Q3) and the measured run it
  cites; the wiring tests are in `backend/test_plan.py`
  (`t_enabled_refuses_a_fresh_pass_for_a_different_model`,
  `t_enabled_accepts_only_a_fresh_pass_for_the_current_model`).

## 2026-10-19 - the preset and voice questions, answered as clickable multiple choice

Put to the owner on 2026-10-19, during the preset/voice merge work, as short
multiple-choice questions he could click. The answers below are his choices;
they decide what gets built when each slice starts. Nothing below is a
switch-on by itself: each still needs its own slice, and a feature switch still
has its own separate approval.

**Decided:**

* **Clearing the old voice training is built, with ONE approval card.** Asked
  "is there a way to clear previous voice training with an approval card in
  settings? if not add it". There is none today (only `adapt-reset`, which
  zeroes the live-addition counters and never touches the enrolled print), so
  it is added as a mode on the EXISTING `POST /api/voice/enroll` route, raising
  the same `change_own_config` card enrolling already uses; nothing is deleted
  until the card is approved, and voice checks refuse until he trains again.
  **The two Settings buttons land after the in-flight voice PRs merge** (they
  own those screens); the backend half comes first.
* **F5 S2, the searchable recordings index: keep the transcript text too, and
  build it in the next slice ON by default.** His own words: "built in in the
  next slice on by default." This deliberately overrides the design brief's
  recommended off-by-default: the index will keep a readable copy of what was
  said, on this PC, until he deletes it - so that slice MUST ship the one
  Delete, the backup exclusion (a backup cannot resurrect deleted words), the
  plain-language disclosure, and an instant OFF. S1 stays read-one-file-and-
  forget-it until that slice is built.
* **Coding on both graphics cards: do the measurement run first.** One ~10
  minute run, in a quiet window, measures the zero-spill start through the real
  path; the runbook and a read-only probe are prepared
  (`.dsh-scratch/MEASURE-HEAVY-LANE-RUNBOOK-2026-10-19.md`). **Heavy mode stays
  refused until the measured numbers exist and he approves the switch
  separately.** The probe already found the coding-lane server down and both
  everyday servers holding a model, so the run waits for those to clear.
* **Live audio: measure one real Live turn first, then build the backend-only
  streaming receiver.** Streaming audio to the PC was excluded on purpose in
  `docs/LIVE-DESIGN.md` section 8, so revisiting it is his call; the first step
  is real end-to-end numbers from one owner Live session, then a dark backend
  receiver that still passes the complete clip through the voice-print gate.
  No public tunnel, and the client never does speech-to-text.
* **Voice-training density: the 12 phrases are recorded once across the three
  rounds** (about 15 recordings), not every phrase in every condition (about
  60). The four-condition contract and the free-speech prompts are unchanged.
* **Old worktrees and branches: delete the 43 clean, already-superseded
  worktrees and the 209 local branches proven already merged** - nothing else.
  Origin refs, PR snapshot refs, rescue/backup branches, unproven branches,
  owner files and backups are explicitly NOT in that approval.
* **Android signing-key rotation: later, after the current feature work.** The
  app release stays on the old debug certificate until then (still HIGH-1); a
  two-hour reminder re-asks him rather than letting it drift.
* **Third graphics card: not yet** - the second card's own features are still
  unmeasured, so measuring the two cards comes first.

## 2026-10-20 - the voice latency work: all three, and two were already done

Put to the owner on 2026-10-20, on Gemini's optimization work order
(`gemini_full_jarvis_optimization_review_and_work_order_2026_10_20.md`, Layer
3): he chose **all three** voice-latency changes for this wave - "parallel
CAM++/Parakeet with verify-before-commit", "Smart Turn v3.2 early end-of-turn
cut", "first-clause streaming TTS".

**What the code already had.** The work order's baseline was stale: two of the
three had been on `main` since 2026-09-24. Smart Turn v3.2 already cuts the
turn early on both listeners - `backend/jarvis_turn.py` (the ONNX classifier and
`POST /api/voice/turn`), `jarvis_speech._turn_state()` (`turn.enabled` on by
default, `ask_after_ms` 200, `max_pause_ms`), the desktop
(`voice.rs` `pause_step`, falling back to the old 900 ms silence when the model
is absent) and the phone (`LiveRules.kt` / `SmartTurn.kt` / `OrtTurnModel.kt`,
its own copy of the model, `SmartTurnTest.kt`). And speech already starts at
the first comma - the owner's own 2026-09-24 decision - through
`jarvis-desktop/src/speech-pieces.js` fed by the live token stream in
`main.js` (`checkForSpeakableSentence`, one clip made ahead), the phone's
`SpeechText.kt`/`SpeechAhead.kt`, and the private/tainted-answer gate
(`private-speech.js`, checked before a clip's sound is asked for and again
before it plays). The work order's own numbers for these (0.85 threshold,
400 ms ask, ~450 ms cut, 8-word clause) are **slower** than what shipped.

**Decided:**
* **Build the one that was missing - parallel verify + speech-to-text** (Opt
  3.1), and do **not** retune the two that were working. `hear()` used to run
  the owner check (~140 ms) and then the transcription (~219 ms) one after the
  other; they now run beside each other on the same in-memory audio, so a clip
  the owner speaks is ready ~140 ms sooner.
* **The privacy rule keeps its promise, and its wording moves from "made" to
  "used".** Unverified speech is still never returned, logged, stored, learned
  from or sent to any model: when the check fails, the worker is joined, the
  words are discarded (`text = ""`) and they exist nowhere the request can see.
  Three costs are said plainly: a stranger's clip now costs one local
  transcription that is dropped unread; a refused clip answers a little later,
  not sooner (the discard waits for the worker it started, so a refusal costs
  the longer of the two steps); and the first clip after a restart may load the
  speech-to-text model before the check instead of after it. With no
  engine installed nothing is started at all, and the check-only path of a Live
  voice pause keeps the old serial order.
* **Not measured here, and not claimed:** the ~140 ms is the work order's figure
  for the real CAM++/Parakeet models on his PC. This repository has no weights
  and no microphone, so what was proven is the mechanism (the transcription
  starts before the check ends, every sink stays empty of an unverified clip's
  words) - not the number.

Built in `backend/jarvis_speech.py` (mirrored to `jarvis-backend/`), proven by
the new `backend/test_voice_parallel.py` and the updated
`test_live.py`/`test_talk_type.py`/`test_speech.py`; written up in
`docs/JARVIS-API.md` section 5.

## 2026-10-20 - three HUD looks, chosen in Settings and from the HUD's own header

Asked by the owner on 2026-10-20, in his own words: *"i would also like to
choose from 3 different UIs for the jarvis HUD in the settings. i want them
looking cutting edge while still being intuitive and effective"*. The design
brief is `deepseek_jarvis_hud_3_ui_modes_and_bar_redesign_work_order.md` PART
III+IV (the bar half of that brief is a separate slice and not this one).

**Decided:**
* **Three layouts, one page.** Command Cockpit (the default), Studio
  Split-Workspace and Ambient Voice Core live inside the one
  `jarvis_hud.html`, switched by `document.body.dataset.hudLayout`. No second
  or third HTML file: the page is shipped as a byte-for-byte copy in three
  places (`jarvis-desktop/src`, `backend/`, `jarvis-backend/`), and three files
  would triple that and let the copies drift. Every DOM id the page and its
  tests already use stays in the document in every mode - the layouts are
  CSS Grid/Flexbox, order and visibility only.
* **Built only from what the HUD really has.** The HUD has two views (Talk
  and the Galaxy map), the approval cards, and the telemetry/memory readouts.
  Nothing invents a Today, Memory or Vault screen: the Cockpit's left rail
  keeps the real Talk and Galaxy navigation, and its Bento inspector is the
  real waiting-cards count, the real second-brain counts and the real last-turn
  numbers. The Studio stage's tabs show the real Galaxy view, the real
  approval cards, the real memory readouts and the real telemetry - never a
  copy of them. The Ambient pills carry the same facts the rails carry.
* **Choosable in two places, kept like the theme.** The picker is in Settings
  -> "The big HUD window" (this computer only) and as a pill in the HUD's own
  header. It is cosmetic, like the theme: **no approval card**, no Rust
  command, no backend route - a per-computer `localStorage` key
  (`jarvis.hud.layout`), the same mechanism and the same file as the "Open the
  Jarvis bar" button switch beside it. The HUD obeys a change made in Settings
  at once through the shared `storage` event, and the in-HUD picker writes the
  same key back. The phone has no HUD window, so it has no row for this; its
  own look is its themes, unchanged (`docs/ARCHITECTURE.md` §8).
* **The bar is not this slice.** The Jarvis bar's own redesign (the same work
  order's PART II: `index.html`, `main.js`, `style.css`, `uikit.mjs`) belongs
  to a different slice and is not touched here.

What the owner can see: the HUD opens as Command Cockpit; the header pill and
the Settings card switch it instantly between the three; the choice is
remembered on that computer. What was **not** tested here: how the three look
on his real screen (a colour and spacing judgement needs the window on his
monitor) - said as NOT-TESTABLE in the pull request, while Playwright proves
each mode switches, persists, keeps every id and works (send, tabs, drawer,
badge, tiles).

Built in `jarvis-desktop/src/jarvis_hud.html` (copied byte-identically to
`backend/` and `jarvis-backend/`), `hud-window.js` and
`hud-window-settings.js`, the "The big HUD window" card in
`jarvis-desktop/src/settings.html`, and proven by `tests/hud.mjs` and
`tests/hud-window.mjs`.

## 2026-10-21 - the whole Live & Voice program approved; barge-in starts as a design, off and unwired

  * **The owner's decision.** The whole audited Live & Voice program is approved (2026-10-21) - the slices are built in order, each with its own switch and its own measurement, and each lands as its own pull request. This entry records the biggest and riskiest of them, **Voice Slice F: true barge-in on open speakers with echo cancellation**.
  * **What phase 1 is.** A design plus an off-by-default prototype, not a live feature. `backend/jarvis_barge_in.py` subtracts the PC's own TTS PCM from the microphone signal with a small NLMS filter and answers ONE question - is there 350 ms of speech-shaped residual, and does the owner check say it is the owner's voice - as a decision dict. Nothing acts on it, no live module imports it, and no route calls it, so the current voice path is exactly as it was (`docs/DESIGN-VOICE-BARGE-IN.md`).
  * **Why off, and what turns it on.** The project's rule is that a feature touching the live microphone path is off until that feature is measured on the owner's hardware (the second-card rule, applied to voice). The switch is `[voice] aec_barge_in = false`; turning it on is one `change_own_config` approval card, turning it off is immediate, and enabling a wiring is a later, separately reviewed change. Real open-speaker barge-in is **NOT-MEASURED** until then.
  * **No new dependency, by choice.** The first attempt uses numpy, which the voice modules already need. speexdsp or the WebRTC echo canceller are only candidates if the measured plan (residual echo level, false-cut rate, owner check on the residual, barge-in latency) rejects the no-dep prototype; that would be its own decision with a `requirements.lock` change and the THIRD-PARTY-NOTICES process.
  * **Desktop only, on purpose.** The prototype needs the PC's TTS PCM and the PC's CAM++ check, so the phone cannot run this half; it already keeps Android's `AcousticEchoCanceler` in voice-call mode. Written in `docs/ARCHITECTURE.md` §8 as a one-sided row, not left to look like a missed screen.
## 2026-10-21 - the anti-surveillance price/flight radar approved; F1 is read-only, off, and not a booking tool
  * **The owner's decision.** The full anti-surveillance price/flight stack is approved (2026-10-21): a flight price radar that reads public prices without cookies, saved logins or tracking tags, plus product-page sources and optional configured exits in later slices. This entry records slice F1, the flight engine and price history.
  * **What is built.** `backend/jarvis_price_radar.py`: a pure-Python `tfs` query builder (byte-parity with the MIT `punitarani/fli` reference, goldens in the suite), a tolerant parser that keeps whole integer cents and never invents a price, and a SQLite history with last-known-good/stale semantics and an outside-text diff. No new dependency; the twin is in `jarvis-backend/` and it ships whole.
  * **What it refuses, hard.** No checkout/cart/seat-hold/PNR path exists; no cookies, login or vault credential is used; a 403/429 is stale `blocked_by_site_challenge` and is never retried or challenged; the only host is the public Google Flights page (strict SSRF allowlist, redirects refused); no proxy in F1; checks are at least 300 s apart with +/-30% jitter. The endpoint is **unofficial** and may break - it is a public search page, not an API.
  * **What is off, and how it turns on.** `[price_radar] enabled = false` in both shipped toml copies; nothing runs until the owner turns it on with one `change_own_config` approval card, and turning it off is immediate. No live request is made in the tests; the real payload is NOT-MEASURED until the switch is on. The approved disclosure words are in the module and both toml copies so F2/F3 reuse them.

## 2026-10-21 - the owner check looks at the first window of voice; Smart Turn's picture is built as the audio arrives

Owner approved "the whole audited program" (the Live & Voice audit, 2026-10-21
morning), whose revised Slice B is backend latency plumbing with no new
dependencies. Two decisions were needed inside it:

**1. The owner check may decide on the first ~1.2 s of voice.** The audit's
V1-Path A: a speaker model gets nearly all of its information from one clean
second, and the check costs a fraction of a whole-clip check, so `hear()` now
asks the SAME `jarvis_voice.verify` on the clip's first window
(`[voice] early_verify_window`, default 1.2 s; `early_verify_margin`, default
0.06). It is a **saving, not a different standard**: only a score at least the
margin past the bar (either way) decides on the window; anything inside the
band is re-checked on the FULL clip exactly as before, and if the window's
worker raises the full clip is checked rather than the error being trusted.
`early_verify_window = 0` restores the old single full-clip call. The
verify-first privacy rule does not move: words are still made beside the check
and, on a no, the worker is joined and the words discarded unread - and a
refusal still **costs that transcription**, so the app cannot be fingerprinted
by how fast it refused. The owner's "verified before the words are used"
wording still holds; what changed is how much audio the verdict needed. The
check-only path of a Live voice pause gets the window too (same check).
**Ruling 10.4 (Gemini's sign-off, same day): an early verdict is bound to one
recording.** The single-shot path builds and purges its window worker inside
each `hear()` call and keeps no audio or verdict at module/class level; a
`StreamingVerify` instance ties its check to the current recording, clears
worker, buffer and token in `verdict()`'s `finally:`, and `abort()` covers a
recording abandoned before an answer - so no utterance can inherit the
previous one's early verdict. Three regression tests cover reuse and abort.

**2. Smart Turn gets a raw-PCM, in-process path whose features follow the
audio in.** `predict_pcm()`/`TurnStream` take raw 16 kHz mono int16 PCM with
no WAV/base64/HTTP, and `MelStream` caches the FFT of every frame a future 8 s
window can ask for, correcting cached raw frames for the window's mean and
variance analytically at the end. The old `features()` stays unchanged as the
reference, and every incremental case is tested against it inside a stated
tolerance; the ONNX session was already cached, CPU only, no new dependency.
The wire is unchanged: `voice.rs` sends the WAV it always sent, and the phone
runs its own model. **What is not claimed:** any real-hardware latency - the
audit's 90 ms / 12-18 ms / 140 ms figures are unmeasured here (no CAM++
weights, no Parakeet weights, no Smart Turn ONNX on this machine, no
microphone), the tests record stand-in mechanism numbers only, and the honest
gate for a spoken-sentence before/after remains the owner's retrain plus one
measured Live sentence.

Built in `backend/jarvis_speech.py` and `backend/jarvis_turn.py` (both mirrored
to `jarvis-backend/`), proven by `backend/test_voice_parallel.py`,
`backend/test_live.py` and `backend/test_turn.py`; documented in
`docs/JARVIS-API.md` (the turn route and the owner check) and
`docs/ARCHITECTURE.md` §8's Smart Turn row.


## 2026-10-21 - the Galaxy gets three lenses, as a view over the graph it already reads

Galaxy v2's first slice (G1, approved by the Lead after the premise check). The owner's HUD window had
ONE brain map fed by `GET /api/graph`; it now has a **Memory | Neural | Unified** lens picker over that
same payload. **Neural** is the capability half the PC's own `build_graph()` already computes
(`collect_models` for the brains and cloud lanes, `collect_tools` for the ability groups and the
abilities their config enables); **Memory** is the memory half (facts, documents, knowledge entities,
projects, skills, personas); **Unified** draws both and its counts line names each half. The decision
that matters: **this is a view, not a second source of truth, and it adds no API.** It needs no new
route, no widening of the shell's five-read allow-list in `hud_proxy.rs`, and no Rust change, because
the page already receives that graph; the counts are computed from the nodes, so they cannot drift from
what the PC actually reports. Every dot is also a real focusable HTML `<button>` with an accessible
label (the "nothing drawn only on the canvas" rule), outside the canvas, so keyboard and screen-reader
users get the same inspector the mouse opens. The chosen lens is cosmetic, kept in the HUD origin's
`localStorage` (`jarvis.galaxy.lens`), with no approval card and no Settings entry.

**Honest limits, said rather than glossed:** the Memory lens renders the HUD's REDACTED memory nodes -
the PC's lock rules decide whether the dots are sent at all - and it shows names and counts, not the
per-entity facts list, because `/api/memory/entities` is deliberately not reachable from this window
(Brain keeps that list); and no lens can mark the active lane/preset because `/api/presets` is not
reachable either. It is the desktop HUD's alone: a phone has no HUD window, and the memory graph stays
off the phone. Built in `jarvis-desktop/src/jarvis_hud.html` (copied byte-identically to `backend/` and
`jarvis-backend/`), proven by `jarvis-desktop/tests/hud.mjs`, documented in `docs/ARCHITECTURE.md` §8.


## 2026-10-22 - the HUD becomes editable: one reducer behind drag, click and keyboard

H2 of the owner-approved editable-HUD design (Gemini rulings 23-27). The big
HUD window's header now has **[Edit HUD]**: panel cards move between the left
rail, the stage top and the right rail, resize S/M/L/Tall, fold and (except the
four protected cards) hide; Settings -> "The big HUD window" has the door
("Edit HUD in the window"). The decisions that matter:

1. **ONE pure reducer.** `jarvis-desktop/src/hud-edit.js`'s `applyAction` is
   the only writer; pointer drag, the card's own toolbar buttons, the keyboard
   shortcuts and undo all call it, and every result goes through `normalizeLayout`.
   That makes the WCAG 2.2 SC 2.5.7 equivalence mechanical: each card has
   up/down, a direct `Move to` region selector, four real size buttons, fold and
   hide (with a reason when protected), the handle takes arrow/Alt/Shift keys,
   and a Playwright gate proves a drag, a click-only path and a keyboard-only
   path save the **deep-equal** layout. The drag itself is one delegated
   pointer-events handler inside the ruling's measured 180-line budget; CSS
   Grid does the reflow. No new dependency.
2. **Protected cards stay protected in the editor, not only in the data.** The
   four protected ids keep a visible-but-refused Hide with a sentence naming the
   card, the approvals card's region is locked, and the approvals auto-expand is
   derived (`effectiveCollapsed(card, pendingCount)`) and never written. H4's
   non-hideable safety banners are out of scope and untouched.
3. **One new capability grant, owner-approved 2026-10-21.**
   `capabilities/hud.json` gains `hud-layout-write` (its own layout, the same
   appearance-class store as the theme) and **nothing else**; Rust
   `sanitise` stays the authority for the saved document, the page still holds
   no pairing token, and the capability test now asserts exactly this one grant
   (and that the H1 read grant was not removed).
4. **Saves are honest and bounded.** 400 ms debounced, flushed on Done/Escape,
   the status line paints the store's own answer ("Saved." or the refusal);
   undo is session-only (50 actions); Reset to preset and Discard changes are
   one click each. The layout contains no private data, so no approval card.

**Honest limits, said plainly:** the main stage (conversation, Galaxy, composer,
stage tabs) is fixed in H2 - its rows round-trip, but the live stage is not
reparented; no import/export (copy/paste JSON is H3), no user-preset management
(H3), and touch/pen drag is NOT-TESTABLE on the owner's hardware here. Built in
`jarvis-desktop/src/hud-edit.js`, `jarvis_hud.html` (copied byte-identically to
`backend/` and `jarvis-backend/`), `hud_layout.rs`'s `open_hud_edit`,
`settings.html`/`hud-window-settings.js` and the capability files; proven by
`tests/hud-edit.mjs` and `tests/hud.mjs`; documented in `docs/ARCHITECTURE.md`
§8.

## 2026-10-22 - H3: the HUD renders the preset's own shell, and the owner keeps layouts

H3 of the owner-approved editable-HUD design (Gemini ruling Q5; Rulings 9, 27
and 28). Four fields H2 stored but never drew are now real, four inert things
are gone, and the window keeps the owner's own layouts:

1. **The preset is what you see.** `shell_template` (six shells),
   `density` (three steps) and `default_stage_tab` are rendered: the injected
   bootstrap puts `data-hud-shell`/`data-hud-density` on the page and announces
   `jarvis:hud-shell`; the page opens the mapped view or inspector tab. Every
   shell that hides a rail has a way back - a slide-over drawer (Ambient
   `center-core`, `two-column-right`, `single-stage-bento`) or the stage tabs
   (`split-stage`'s right rail via Telemetry/Memory/Today). Entering Edit HUD
   auto-reveals every hidden rail, so the protected controls the HUD draws stay
   visible/reachable while editing and all four `PROTECTED_IDS` stay forced
   visible in the document. The fixed **Stop everything** control (owner-approved
   2026-10-22) sits in the stage bar outside every card and the layout document:
   `#hud-stop` calls the same `screen_work::stop_everything` command as the
   Alt+Shift+X hotkey, the tray and the widget (stop only, never held on a stale
   link or App lock), and the HUD gains only the least-privilege `hud-stop`
   capability (`allow-stop-everything`). No preset, import or Edit HUD can hide
   it; H4 may later move it into `#hud-safety` without a second control.
   The 4-into-3 `LOOKS` alias map, `LOOK_BY_PRESET`,
   `lookForPreset`, `data-hud-layout` and the stale "until H2" comments are
   **deleted**, pinned by a source test. Only a three-field
   `jarvis.hud.preview` localStorage mirror remains, for the first frame only -
   the saved document is still the one truth.
2. **Inert fields pruned.** Colour `theme` is out of the document and the
   contract (Appearance owns colour; a saved document that still carries it
   loads with the key dropped, and LAYOUT_VERSION stays 1 so nobody's layout is
   discarded), and the seven fixed cards' 68 dead span values are out of
   `contract/hud-presets.json`. The vocabulary -> DOM mapping test is
   closed-world both ways: every shell/density/region/tab/card the model can say
   has a page target, and the page cannot say a token the model does not know.
3. **My layouts, through the ONE write.** The library lives inside the same
   layout document (`user_presets`, <=20, Rust-bounded: ids, names, base
   presets, protected cards forced visible, 64 KB cap) and saves through the
   SAME `set_hud_layout` command - **no new capability, no new command, no
   approval card**, so H2's owner-approved one-write invariant still holds. The
   Layouts menu does duplicate/rename/delete/reset; editing a shipped layout
   starts the owner's copy (Ruling 27); moving a layout between PCs is
   **copy/paste JSON only** (Ruling 9: no file picker, no `blob:`, CSP
   untouched), and Settings lists the same library with a one-click Reset.
4. **Honest limits, said plainly:** the library is per-computer (no sync; the
   JSON is the manual move path); the owner's real monitor look and touch/pen
   are NOT-TESTABLE here; the non-hideable safety rail (rush/outside-text,
   stale-link with Deny enabled, App lock) remains **H4** and H3 makes no new
   promise about it. Built in `hud-layout.js`/`hud-layout-store.js`/`hud-presets.js`,
   `hud_bootstrap.js`, `jarvis_hud.html` (three byte-identical copies),
   `hud_layout.rs`, the contract, `settings.html`/`hud-window-settings.js`;
   proven by `tests/hud-shell.mjs`, `hud-layout.mjs`, `hud-window.mjs`, and the
   H3 checks in `tests/hud.mjs`.


**Decided 2026-10-22, HUD H4 (the safety rail): three safety facts get a fixed home no layout can hide (owner: "fully editable" must never mean "editable into hiding a safety fact").** The HUD now carries one fixed `#hud-safety` strip, owned by the shell and OUTSIDE every editable region: it is not a card, not in `CARD_REGISTRY`, has no layout-document entry, and no preset, import, hand-edited settings file or edit-mode action can hide or move it (tests pin the absence; a hostile saved document naming such cards is dropped by the normaliser, the strip stays visible with it and with a non-default preset, and it is visible in edit mode with the line "Always visible — no layout can hide this"). It shows (a) **App lock is on** (`App lock is on. This window hides when you step away, and approvals wait until you're back.`) or **memory lists are hidden** (`Memory lists are hidden until you unlock.`), read through the ALREADY-GRANTED `get_lock_flags` (two booleans, no token, no new capability); (b) **queue-scoped rush/outside-text evidence** derived from the pending queue's `raised` object the page already polls — the words are "Something Jarvis read tried to rush you on the card that is waiting… Take your time — this can never be hidden.", and the banner disappears when the queue no longer carries such a row. It deliberately does NOT claim the persistent ten-minute rush latch is armed: that latch lives only on the owner's PC and has no read on the HUD's fixed allowlist (a backend read is an approved follow-up for a later deploy wave — H4 adds none). (c) **Catching up with your PC… Approvals wait for the link; Deny still works.** — while the link is stale the card's **Approve is disabled** with the words tied to it (`aria-describedby`) and **Deny stays enabled**, matching Rust's own `stale_answer_refusal` (only an APPROVED decision is held); an offline link shows Rust's own first sentence. The actual App-lock "locked" state still HIDES the HUD window (Rust) and there is deliberately no in-page locked overlay (it could never be seen) — a documented non-goal, not a gap. No new command, permission, capability, inline script (count stays 4), CSP change or deploy: one new external module `hud-safety.js` imported by the page's existing module block, three byte-identical HUD copies, and the strip is silent when linked (the one status row already says it). Tests: `tests/hud-safety.mjs` (words matrix, queue-scoped wording pinned, Approve-held/Deny-enabled, hostile import, no new grant, no file/blob path, un-hideable pins) plus the H4 block in `tests/hud.mjs` (catching up with a pending card, offline, App-lock and hidden-lists chips with no card raised, escaped rush quote with no DOM injection, edit mode cannot hide it, geometry at 1280×820 and 1024×768 at DPR 1 and 900×600 at DPR 1.5, with the strip click-through so the protected bar launcher, quickbar, composer, approvals buttons and the real fixed Stop everything control (#742, `#hud-stop`) are never covered or pointer-blocked, reduced motion, a real Deny click reaching `decide_approval`). Honest limits: `get_lock_flags` is polled (boot, focus, visibility, a 20 s beat) so the chip can lag by that beat; the real lock-screen experience is a field-test row (BLOCKED until driven on the PC, never a pass); the rail's visual weight is the owner's judgement.

## 2026-10-23 - Q1: four approval cards wait for the owner; every other card still expires

**Decided 2026-10-23, Q1 (card expiry). Written into this record on 2026-10-24, because the
decision was carried into the code and the other docs but not into this log; the owner's
original wording is not recoverable from the repository, so this entry records the
decision's shape rather than pretending to quote it.** The earlier rescue work
(`rescue/card-expiry-never-expires`, 2026-10-13) had exempted **23** gate actions from the
expiry clock. Ruling Q1 refused that scope: a stale "yes" on a card that loosens a rule is a
time bomb, so only the interactive ceremonies that need the owner at the PC may wait without
a deadline.

The exempt set is exactly four gate action ids, decided by the gate's own ids in
`backend/no-expiry-cards.patch`:

- `pair_device`, `unretire_shared_key` - pairing a device (its card, and the old shared
  key's "bring back");
- `register_approval_key` - registering a phone's approval key;
- `restore_backup` - restoring a backup.

Every other card keeps `#378`'s window - 900 seconds in the shipped configuration since
2026-10-13, changeable in Settings - including "forget a time frame" and every switch that
loosens a rule (web search, reading tools, notifications, learning, limits, the voice bar).
**Waiting is still not approving:** a never-expiring card runs nothing until a person
answers it, a denial is still a denial, and a cancelled or replaced pairing/key card is
withdrawn and no longer answerable. There is no way for a caller to ask for "no deadline":
`timeout_for(action)` turns `None`, `0`, a negative number, a malformed name or an unknown
value into the ordinary timeout, and a caller's own `timeout=` can only shorten the wait.

**The costs, said plainly.** A card with no clock cannot clean itself up: a pairing or
approval-key card whose session is cancelled or replaced is taken off the list by
`jarvis_gate.withdraw()`, and a restore card whose waiting thread died (an app restart)
stays pending until it is denied or re-raised - the documented cost of no clock. The
implementation and its evidence are in `backend/no-expiry-cards.patch`,
`backend/test_gate_no_expiry.py` (170 checks), `docs/ARCHITECTURE.md` section 2,
`backend/README.md` and `docs/JARVIS-API.md` (`expires_in`), and the rescue pull request is
#773.

## 2026-10-23 - the phone's Galaxy stays a read-only list and gains an "at a glance" band

Offered three choices, the owner picked the light one: the phone keeps the
read-only `PeopleAndThingsSection` list (the signed 2026-10-21 ruling's "zero
canvas" stands) and gains ONE read-only band above it - the number of names and
facts, then the eight names that share facts with the most others, as plain
labels that announce as text and never as buttons. A still picture and the
animated 8 presets were NOT chosen; the animated presets would also need a new
decision and desktop engines that do not exist yet. Slice 1 is planned in
`.dsh-scratch/ANDROID-GALAXY-PHONE-PLAN-2026-10-23.md`; it reads nothing new
(the two reads the plate already makes) and writes nothing.

## 2026-10-23 - the desktop Galaxy is rebuilt as a faithful 3D port with a bundled library

The owner chose the full 3D port of the v2.6 prototype for the desktop Brain
window, and later for the editable HUD: a pinned, MIT-licensed three.js and
OrbitControls vendored into the app (no CDN at runtime), every visible name kept
as real HTML text over the drawing, a visible SVG fallback when WebGL is
missing, the existing pause-when-hidden rule (#777), and no "simulate" control
for any security state - the Sentinel view reads real local/approval/taint state
only. The phone stays excluded. The three simple layouts (Star map, Clean tree,
Zen ring) landing in SVG as #775 stay as the fallback. The plan is in
`.dsh-scratch/GALAXY-WEBGL-PORT-PLAN-2026-10-23.md`; the GPU frame rate and how
it feels on the owner's screen are his field test, not a claim here.

## 2026-10-23 - DeepSeek search is tried for real by the owner, once

The owner will save the DeepSeek Search key in Windows Credential Manager
(`Jarvis Backend/DeepSeek Search key`) and run one real web search with the
provider switched on, then say what happened. Until that call is observed, the
DeepSeek network paths stay NOT-TESTABLE - never a pass. No key is ever placed in
the repository, a log or an agent workspace.

## 2026-10-23 - the new-PC setup script is fixed by rewriting the 13 stale patches

The owner chose the deep fix over a docs stop-gap: `scripts/apply-patches.ps1`
must succeed on a fresh `jarvis-backend` copy, which means rewriting the 13
genuinely stale patches (the G8 bisect: 15 patches already present in the base,
7 sequence casualties, 13 genuine drift). The success test is a real run on a
fresh base with both Windows PowerShell 5.1 and pwsh 7, exit 0, and the docs
updated to the proven command. Until then the documented new-PC step still
exits 1 and that is recorded as a blocker, not worked around.

## 2026-10-23 - the Python lock recipe is fixed before the filelock advisory is bumped

The documented recipe cannot regenerate `requirements.lock`, so `filelock==4.0.0`'s
three advisories (GHSA-v4x8-3wr5-3wq8, GHSA-9vhv-jxww-xfm5, GHSA-567q-5qvw-pf92)
cannot be cleared honestly. The recipe is fixed first; only then is the bump to
4.2.1 made through it. This is also why a new Python dependency (like a WebSocket
library) could not be added for the phone Live stream.

## 2026-10-23 - the phone live-stream transport is the hand-rolled minimal WebSocket

The owner approved the transport design for Slice G/G2: a minimal RFC 6455
WebSocket implemented with the standard library (no new dependency), with token
and origin checked BEFORE the upgrade, 2,048-byte binary frames (one 64 ms frame
at 16 kHz mono), the design's refusal paths, and one whole turn over the
persistent stream. It lands as its own pull request after the cascade; the switch
`[live] stream` ships OFF, and the phone Live 16 kHz stream still answers `501`
on the backend until the phone half is wired and measured.

## 2026-10-23 - dependency policy: Tauri 2.12.5 and the six GitHub Actions majors move now

The safe patch updates already landed as #778. The owner approved the next step:
Tauri 2.12.5 plus the six GitHub Actions major bumps, as their own pull request
on fresh `main`; Android library bumps and the search-engine image tag stay held.
The "one approval card per update" policy remains the chosen self-update shape
and is still unbuilt.

**Decided 2026-10-23, Galaxy Phase G0 (the owner chose A/A: three flat layouts first, the rich 3D presets later).** The Brain window's Galaxy gets **three flat layouts beside the constellation** - **Star map**, **Clean tree** and **Zen ring** - chosen from a chip row in the Galaxy bar or the **6/7/8** keys while the picture has focus; pressing the same key again returns to the constellation. The five rich presets the rework blueprint lists are shown in the same row as disabled "not built yet" chips. The layouts are a **pure, deterministic module** (`jarvis-desktop/src/galaxy-presets.js`) that only moves the nodes the existing renderer already draws: no node, link, label rule, cap, backend route, permission, approval card, dependency or PC write is added, and the choice is remembered on this device (`jarvis.galaxy.preset`, the Brain window's own local storage - no PC copy), with a corrupt value falling back to the constellation. It is the **desktop Brain window's alone**: the phone deliberately has no memory graph, and the editable HUD stage keeps its own renderer until G1 shares the layout maths - recorded in `docs/ARCHITECTURE.md` §8. Two small defects found by the follow-up audit were fixed before the pull request: the Fit button and the `0` key now use the flat layouts' wider margin, and switching away during the constellation's ~1.3 s assembly no longer saves a part-assembled picture for the return. **Also fixed in passing:** the constellation's labels were half a stage to the left of their dots (a shipped bug: `margin-left: -50%` resolved against the stage width), now `translate: -50% 0`. Honest limits: the guide drawing and the label look on the real WebView2 window/monitor are NOT-TESTABLE here (never counted as a pass); the five rich presets, the same layouts in the big HUD window, the icon packs and the phone version are later phases. Built in `brain.js`/`brain.css`/`brain.html`, `galaxy-presets.js`; proved by `jarvis-desktop/tests/galaxy-presets.mjs` plus the existing galaxy suites.

## 2026-10-24 - a backup started on the phone is finished with ONE TAP on the phone

The owner upgraded the 2026-10-13 rule "a phone may ask, only the PC may write",
and replaced the morning's 2026-10-24 decision ("let the PC finish a backup the
phone started", finished from Settings, Backups with the typed code). After the
phone shows the recovery code and the owner ticks "I have written this code down
somewhere safe", pressing the phone's finish button now makes the PC write the
backup - no step on the PC. The one-time code the phone holds IS the
authorisation; the write still physically happens on the PC's disk, by the PC's
backend, and only the trigger comes from the paired phone. `POST
/api/backup/commit` therefore no longer refuses a caller for not being the PC: a
live run minted by `prepare`, its exact one-time code and the 15-minute TTL are
what authorise a write. The PC's typed-code finish stays as the fallback for a
run the phone left waiting, on the same route.

The residual risk, named rather than hidden: the "I saved it" tick is a
client-side promise inside the phone app, not something the PC can check. A
modified or misused paired phone could therefore make the PC write a backup
whose recovery code was never kept - an unopenable file - and because making a
new backup deletes the oldest of the five kept, it also pushes the oldest one
out. The owner accepted that on 2026-10-24 rather than leave a run the phone
could never finish.

What stays PC-only, unchanged: restoring (Windows Hello, `restore_backup`),
choosing the backup folder (the Windows picker), listing the files on the PC's
disk, and deleting older copies. `docs/JARVIS-API.md` §45 and
`docs/ARCHITECTURE.md` §8 carry the rule; the phone's screen says "Nothing has
been written yet" before the press and "Your PC wrote the backup" only after the
PC reports a file.

**Narrowed the same day on Gemini's ruling (Q-A, the asker guard).** The
one-tap decision above left the code as the whole authorisation, so any paired
device that learned the code could finish someone else's run. The finish is now
BOUND: `prepare` records the caller's device identity in the live run - the
same `handler._jarvis_device` identity `jarvis_devices` stamps on every request
("pc", "shared", or a paired device's id), never a new header or token - and
`commit` is accepted only from the device that minted the run or from this PC
(the typed-code fallback). Any other paired device holding the same code gets
403 with plain words: nothing was written, the folder is unchanged, and the run
is NOT spent, so its real finisher can still use it; the device is checked
before the code, so the route is no code oracle. Two limits are stated rather
than hidden: a run minted with NO recorded identity (a backend without
`jarvis_devices`, or a direct in-process call) cannot be bound, so possession
of the live code still decides, exactly as before; and the legacy shared key is
one identity (`shared`) for every holder until the first device is paired. The
guard does not close the token-churn gap - a token holder can prepare and then
commit as the device that minted its own run.

**Also on the same ruling (Q-F).** A commit that has CLAIMED the run and then
cannot write now always records `last_attempt.ok: false`, including the 409
when the folder has gone - that path used to record nothing, so the phone's
status line could still show the PREVIOUS run's success over a run that wrote
nothing; the response shape and status are unchanged. And a partial/truncated
`.jbak` left by a cut-short copy or a failed write is never counted as a valid
backup (`list_backups`' own completeness rule, the same one retention uses),
while a later successful write still produces the right, openable file.
`backend/test_backup.py` proves the failure, the byte-for-byte unchanged
folder, the unchanged kept count, the truncated file not counting, and the
later success - each with the negative-control numbers recorded in the branch's
own report.

## 2026-10-24 - the C3 decision-time bug is fixed in the two apps; `history()` stays exactly as measured

The live read settled the C3 question the 2026-10-24 bug audit had left open:
`GET /api/pending` history rows carry `id, action, tier, state, created,
decided, decided_by` and no `decided_at` (measured 13:52 PT; a decided row's
`decided` was `1792875072.03678`), while the desktop (`brain.js`
`activityWhen`) and the phone (`GateHistory.kt`) both read `decided_at` - so a
decided card showed its raise time, or nothing, as its decision time.

**Decided: fix the readers, not the PC.** Both clients now read
`decided_at ?? decided` for the decision time and `created_at ?? created` for
the raise time, which is the whole fix against the measured row - `decided` is
a real value on a decided row. No alias was added to
`jarvis-backend/jarvis_gate.py` and no patch was written. The base is never
copied over the owner's install (a live change travels only as a
`backend/*.patch` delta), so an alias typed into the base would be a claim
that never reaches the PC; delivering it would need a new patch plus a
`DELTA_TABLE` anchor in the deploy tool, and the only readers of `decided_at`
are the two clients being fixed here. The fallback is what makes the fix land
on the backend as it is. If a later wave wants the alias on the wire, both
readers already prefer it, and the measured shape above is the anchor.

Evidence: `jarvis-desktop/tests/activity-when.mjs` lifts the real
`activityWhen` and pins an old-shape row and a row carrying both names - it
fails against the old reader (2 checks red) and passes against the fix (5 of
5). `jarvis-client/.../PastApprovalsTest.kt` pins the Kotlin reader the same
way; CI is the first compiler for it, since there is no Android build at this
desk.

## 2026-10-24 - the medical record is its own file, and the local medical model is an explainer with no authority

The owner asked for medical records "kept separate from other information",
a health conversation that stays on the PC, and MedGemma 1.5 4B on the second
card as a helper to "verify FHIR records and lab terminology 100% offline".
Tonight's slice built the smallest honest version of that, and wrote down where
the words in the request are stronger than the code. It first shipped with the
record **unencrypted and out of backups**, because that question was still the
owner's to answer; he answered it the same evening, so this entry records both
the first version and the reversal, in that order.

**What was built and why each part.** The record lives in
`~/.openjarvis/medical/health.db` - its own folder and its own file, not one
more name in `memory.db` - in `backend/jarvis_medical_advocate.py`, shipped
whole with no route and no screen. Every read and write sets
`jarvis_gate.latch_taint(why="health_data")` *before* it opens anything and
fails closed with `MedicalStoreUnavailable` when the latch cannot be set; a
medical read therefore pins the chat to local models for the gate's
**30 minutes**, and no longer. `erase_all()` empties only that file (secure
delete, a truncated write-ahead log, then a vacuum), and a test proves a
neighbouring `memory.db` is byte-for-byte untouched and never created. The
local model client is the ONE HTTP path already in `jarvis_second_card`
(`generate()` gained a narrow `model=`/`keep_alive=` override whose default
request is unchanged), so this feature adds no second client and inherits that
module's loopback refusal; it probes `127.0.0.1:11435` in 0.20 s, strips the
`<unused94> ... <unused95>` thinking markers MedGemma leaks, and on any failure
returns a calm fallback that names the main local model on `:11436`.
`validate_bundle()` is a deterministic offline checker of a named subset of FHIR
R4 (32 checks: Bundle rules, required elements and required-bound status
values, id and instant shapes, reference syntax and in-bundle resolution,
Observation value/unit/range/flag/component contradictions, duplicate rows and a
magnitude heuristic, and code SHAPE), with `summarise()`; its verdict is
`no_errors_found`, `errors_found` or `not_checked` - never "valid" - every code
meaning is listed under `unverified`, and the optional model is attributed with
`authority: "none"` and can never move a finding.

**What the request asked for that this slice does NOT do, and why.** The latch
is NOT permanent: the two settings that look like they promise a
whole-conversation latch (`taint_persists_for_conversation`,
`always_taint_conversation`) are read by nobody; a non-expiring latch is a code
change for a later slice. There is no biometric lock screen, no phone or desktop
screen, no backup toggle, no import of a bundle into the store, and no federal
API (RxNav, MedlinePlus, openFDA, DailyMed) and no outbound de-identifier - the
federal-API route is network, so "100% offline" would be false, and a bare LOINC
code already reveals which tests the owner had; `jarvis_scrub.py` is not reused
because its own header says it is not an egress filter. **"Verify lab
terminology" is not achievable offline**: the LOINC, RxNorm/ RxCUI, ICD-10-CM,
SNOMED CT and UCUM tables are not on this PC, so the checker reports code shapes
and lists every meaning as not checked. And the 4B model is not a terminology
authority - measured 2026-10-24, it answered a basic metabolic panel LOINC spot
check with `8141` (and `81416-1`/`81417-1` elsewhere) where the usual code is
`24323-8` - so nothing it says may be written down as "verified". The first
version of this entry also recorded that the record was not encrypted and not in
backups; that half was a pending decision, not a limit, and the next paragraph
records what the owner said.

**The owner's answer, the same day - a deliberate reversal (2026-10-24).** Asked
whether the health database should stay out of the encrypted backups and
unlocked, the owner said: **"I wanted it encrypted as well and part of that
file."** Both halves were built immediately after, and they reverse this
entry's first version on purpose:

- **Encrypted at rest.** Every record field - label, dates, value, unit,
  source, note - is sealed as ONE JSON payload per row with AES-256-GCM, under
  a fresh 12-byte nonce and with the table name and a random per-row label as
  associated data, so a sealed row cannot be moved to another row or kind and
  still open. The 32-byte key is kept in Windows Credential Manager under its
  own target, **`Jarvis Backend/medical key`**, created on first use and read
  back before use, through the SAME `jarvis_chat_log.CredentialKey` helper chat
  history and the review decks use - a second key, not the chats'. It is never
  written to a file by this module and never logged. The module also seals a
  check value into the store, so a replaced or deleted key raises
  `MedicalStoreUnavailable` instead of being read as "an empty record"; a file
  an earlier version wrote unencrypted is refused in plain words rather than
  read or overwritten. The plain columns are the structural minimum: row
  number, random row label, when the row was made, and the audit table's
  action/kind/row-number/count. These say a medical row exists and when, not
  what it says - written down in the module's docstring and in
  `docs/MEDICAL-STORE.md`.
- **In the backup.** `health.db` moved out of `jarvis_backup.NOT_BACKED_UP`
  and into `SOURCE_DBS`; the archive carries it under `db/medical/health.db`
  (its own folder, never flattened beside `memory.db`), and carries this
  store's own key inside the encrypted archive as
  `secrets/medical-key.b64`, exactly as chat history's key already travels.
  A restore writes the database back into `medical/` and the key back into its
  own Credential Manager entry, so a **new PC whose Credential Manager has
  nothing in it** can open the restored record. If the key cannot be read when
  the backup is made, the record is left out rather than carried unopenable -
  the same rule `study.db` already follows. The pinned counts moved from
  `17 + 8` to `18 + 7`.
- **The MedGemma request timeout** was raised from 25 s to **120 s**: measured
  on 2026-10-24, one answer took 28.35 s, so 25 s was cutting the model off and
  returning the fallback instead of the answer.

**What is honestly testable tonight, and what is not.** 93 hermetic tests
(`backend/test_medical_advocate.py`) cover the store round-trip, **encryption
at rest** (a distinctive secret is written, then the raw database bytes and any
journal beside it are scanned for it and the payload is checked to be
unreadable JSON), the plain-metadata list, the latch ordering, fail-closed for
a missing / broken / short / replaced key and for a file from the unencrypted
version, the path separation, the backup pins, the loopback guard, the
120-second timeout reaching the HTTP call, the lane's three states, the
fallback note, the marker strip and the FHIR canaries, each with a positive
control. `backend/test_backup.py` adds two real round-trips: a record is written
with a fake Credential Manager, backed up, the local file is deleted, and a
"new PC" with an EMPTY Credential Manager restores the archive and reads the
record back with the key the restore put there; the second is the harder case -
that new PC had already minted its OWN medical key before restoring, and the
restore replaces it with the backup's so the record still opens, with a stale
`-wal` beside the restored file removed. The pre-push audit also pinned the two
store-side holes: a sealed payload moved between rows is refused (the AAD binds
it to its kind and row label), and `erase_all()` still wipes when no key can be
had - a lost key must never stop the owner erasing their own record - while the
latch still comes first. The lane itself was measured on the owner's PC on
2026-10-24 (100% GPU, 16,384 context, `size_vram` 2,817,953,626 bytes), then
stopped again so the coding lane keeps its port; one line starts it. A real
portal export, a real phone screen and a real medical review remain
NOT-TESTABLE - and NOT-TESTABLE is never a pass.

## 2026-10-24 - the flight price radar's live test: the page is 2.3 MB, and the "hard" 300 s floor wasn't

  * **What the live test found.** The first real read-only GET of Google
    Flights' public page (SEA -> NRT, 2026-12-12, economy, USD) came back
    HTTPS 200 at **2,306,825 bytes identity / 309,768 bytes gzipped**, while
    the module's cap was 2,000,000 bytes and it did not ask for gzip. So
    `fetch_page()` raised `FetchFailed("the page was larger than a search page
    can be")` - with the switch on, every check would have recorded
    `fetch_failed` and never produced a price. The parser itself was right
    against the real page: 11 itineraries, lowest $856.00.
  * **The fix, owner-approved the same night.** The request now sends
    `Accept-Encoding: gzip` (what a browser sends, and roughly 7x fewer bytes
    per check); the page cap is 8,000,000 bytes with a separate
    2,000,000-byte wire cap for compressed answers, and a compressed body is
    inflated only up to the page cap - a gzip bomb is refused, never
    decompressed without a bound. The measurement is written into the module,
    the design and the architecture note.
  * **The poll floor, corrected.** The design and the module both said the
    floor was "at least 300 s", but `next_check_at` applied its +/-30% jitter
    before returning, so a wait could be as short as 210 s (measured live: 257
    s). The jitter now only ADDS time (300-390 s), so "at least 300 s between
    checks" is literally true; a test pins `>= 300`. This does not loosen the
    2026-10-21 ruling - it makes the code match the "hard" part that was
    approved. F2's cadence was already safe: it delegates to
    `jarvis_tellme.next_poll_timestamp`, which clamps with
    `max(POLL_MIN_SECONDS, ...)`.
  * **What is still not measured.** The switch stays off, nothing is
    scheduled, and there is still no route or app surface. The endpoint's
    stability over time is NOT-MEASURED; the suite makes no live request.

## 2026-10-25 - the fast lane may only promise what this PC can do, and a claim no tool backed gets one plain correction

The owner's live campaign of 2026-10-24/25 found chat making claims the
machine could not keep: `"Opening <whole sentence>."` for a shell command or
a two-part ask; `"what time is it?"` answered by the model 9.5 hours wrong
after 82 seconds; a real setting (`"turn on learning in the background"`)
denied; `"cancel that"` silently doing nothing after a read-only turn;
DuckDuckGo reported ready only because `ddgs` imports. The fixes live in the
fast path that already owns those words (`jarvis_quick.py`, `jarvis_open.py`,
`jarvis_search.py`), so no model choice is involved, and the rule they follow
is one sentence: **a fast answer may only promise what this PC can do.** Two
decisions follow from it:

- **`open_app_built=False` does not mean "opening is off".** It means the
  backend did not name the program from its own fixed tables; the desktop
  resolves the name against this PC's Start menu and opens it
  (`jarvis-desktop/src-tauri/src/open_app.rs`), and says in the chat when it
  is not there. The architect relied on the opposite reading when it approved
  the sentence "Opening programs from chat is switched off on this PC —
  nothing was opened." for that case (ruling Q6). That sentence would be false
  for `open notion`, so the shipped wording is **"I have asked this PC to open
  notion."** on this PC; the ruling's exact sentence is kept in
  `jarvis_open.OPEN_OFF` and is used only when opening really is off
  (`can_open=False`, which no caller passes today). This correction is
  recorded for Gemini to review.
- **An answer may not claim a search, a calculation, a feature list or a
  missing setting that no tool backed.** When the words do claim one and no
  matching tool ran in the turn, one plain correction sentence follows the
  answer (`_claim_corrections()` in `jarvis_agent.py`); corrections are
  additive lines before the finish chunk - never a rewrite of the answer - so
  the app shows the model's words and then the correction, and denials,
  questions, "earlier" claims and honestly backed claims are left alone. The
  same day's ruling Q9 approved this shape (deterministic pre-routers plus a
  post-turn search-claim guard).

The fast lane's honest refusal for shell commands and two-part sentences is
`SHELL_REFUSED` / `NOT_ONE_THING` in `jarvis_open.py`; a refused sentence
carries no `open_app` route field, so no client is told to act. Search
readiness now means "the provider's last live test worked" (`at_risk` /
`untested` / last test recorded, and choosing a provider tests it before
switching), not "the library imports".

## 2026-10-25 - the two graphics cards are named by their job, and the approved card keeps its role across a reboot

After the 21:14 reboot the app called the monitor card the everyday card, so
a valid stored switch looked like it had been approved for a different card
and demanded re-approval. The fix keys on the **approved card's UUID**: when
the stored `master_card` UUID is physically present, that card is the spare
card, regardless of which model happens to be loaded or which `nvidia-smi`
row is first (`jarvis_second_card.py`, `_approved_spare()`). The other card is
the chat card. When no card has been approved yet, the old detection still
runs; a deterministic total-VRAM fallback exists (`_chat_card_by_size`) but is
deliberately **not wired**, because it only affects the not-yet-approved state
and wiring it changed 94 of 612 checks when tried - the owner's call. Roles
are named by their job in both apps, not by arrival order, because the
numbers read backwards ("the second card" is the 12 GB RTX 2060): the
everyday card is the **"Chat card (RTX 2060 12 GB)"** and the free card is the
**"Spare card (RTX 2080 SUPER 8 GB)"**; the route name `/api/second-card` is
unchanged. The existing availability sentence about moving the monitor cables
now only appears when the chat card has more than 2,500 MiB free, because
moving the monitors adds roughly 1-2 GB of desktop overhead (ruling Q8). The
background learner stays **off** until the owner deliberately turns it on
again after this fix (owner decision 2026-10-24); it was found on in the live
backend at 23:50 PT and turned off the same night.

## 2026-10-25 - live preload warms the prompt prefix too

`warm_prefix()` already existed on main but the preload path never called it,
so the first real answer still paid ~10.5 s reading the rules and tool list
out of nothing. The call site is now in the preload
(`backend/jarvis_agent.py`); it calls the same helper the waking path already
calls, holds no lock while it waits and loads no model.
## 2026-10-25 — The HUD's three measured cockpit defects, and why the browser draws its own face

  * **What was measured, on the real page at 1440x900 (headless Chromium,
    the HUD sweep of 2026-10-25).** In the ordinary Cockpit view the right
    rail painted three cards on top of each other. `#rail-right` is a flex
    column and its first child, the card region, was a shrinkable flex item
    (`flex:0 1 auto` with `min-height:0`): it was squeezed to 342 px while
    its six cards needed 798 px, so the overlaps are real 2-D
    intersections - `#rail-memory` ∩ `#rail-reminders` 239x119 px,
    `#rail-budget` ∩ `#rail-reminders` 239x108 px (the budget card entirely
    inside the reminders card) and `#rail-voice` ∩ `#rail-reminders`
    239x136 px (also entirely covered) - and `#rail-right` measured
    `scrollHeight 900 = clientHeight 900`, so there was **no scroll range at
    all** to reach the two cards that were not visible.
  * **The preset names were squeezed to nothing.** `.preset-name` had an
    ellipsis but no minimum width, and `.preset-model` was `flex-shrink:0`
    with no ellipsis, so a 60-character GGUF tag held 324 px, made its
    button 272 px wide inside a 220 px rail (66 px of it hanging over the
    conversation pane) and squeezed "General Uncensored" to **0 px** and
    "Coding" to **5 px**.
  * **The browser asked for a face page the web server has never served.**
    `#reactor` was pointed at `faces.html?mode=display&feed=parent`
    unconditionally, but the web server answers a closed list of named
    files (`STATIC_ASSETS` in `jarvis_hud.py`) and `faces.html` is not a key
    in it, so a browser painted `{"error": "not found"}` where the red panda
    belongs and logged that 404 as the page's only console error on every
    load: **1 request and 1 console error before, 0 and 0 after**.
  * **The fix lives in the normal layout, not only in edit mode.** The rule
    that stops the stacking already existed, but only under
    `body[data-hud-edit="on"]` (P0.5 D-UI-3, 2026-10-23) - so a correctly
    laid-out Edit HUD shipped beside a broken ordinary view, which is the
    view that actually ships. The ordinary view now carries it
    (`#rail-right{overflow-y:auto;min-height:0}`,
    `#rail-right .hud-region-right{flex:0 0 auto;min-height:0}`), scoped to
    the right rail, and the edit-mode block is left exactly as it was.
    Measured after: **0 overlapping card pairs and 457 px of scroll range**
    in Cockpit; Edit HUD unchanged at 813 px and 0 overlaps; the preset
    names **97 px and 88 px** visible and the button **191 px**; no element
    outside the rail and the page width still equal to the window.
  * **The browser draws its own face, and that is the decision.** Serving
    `faces.html` would mean 12 static files (the 405,699-byte `faces.html`
    plus the 11 scripts it loads), a 12-key whitelist in `jarvis_hud.py`'s
    `STATIC_ASSETS` and the matching deploy-sync entries - all for a
    fallback of five lines of script. So in a plain browser the frame stays
    at `about:blank` and a built-in CSS orb is drawn in the frame's own
    box; the frame and the orb share one grid cell, so every rule that
    already sizes `#reactor` (220 px in Cockpit, 150 px narrow, 48 px in
    Studio, 320 px in Ambient) sizes the orb too and it cannot drift from
    the face it stands in for. Inside the desktop shell - the same
    `window.__TAURI__ && window.__TAURI__.core` test the page already
    makes - the animated face is untouched and none of this is drawn.
  * **Honest limits.** Everything above was measured in headless Chromium at
    1440x900 in Cockpit only. The other shells were checked to still lay
    out, and Studio's core-plus-label row was corrected so the orb is not
    stretched, but overlap was not re-measured in them, and a real tablet or
    laptop browser remains a field-test row rather than a pass. The page
    ships three times byte-identically (`backend/`, `jarvis-backend/`,
    `jarvis-desktop/src/`) and all three changed together; no backend, Rust,
    API or live-folder file changed.
## 2026-10-24 - the phone may approve the picture swap too (`free_card`)

  * **What the owner asked, in their own words.** "i would like to be able to
    approve this from my phone as well" (2026-10-24). Until then the
    picture-maker's swap was the PC's own act: a confirmed `POST /api/pictures`
    from anything but this PC was refused `403 pc_only`, so the owner had to
    walk to the PC to say yes.
  * **What replaced it.** The refusal is gone for the make route. A paired
    phone that sends the draw again with `"free_card": true` - after the same
    `409 needs: "free_card"` question, the same plain sentence and the same
    minutes - runs the identical swap: the everyday chat lane is unloaded
    (`keep_alive: 0`), the picture is drawn, ComfyUI is asked to let go of its
    models and waited for, and the chat is warmed back in a `finally`. The
    answer keeps its shape, including `card.chat_away_seconds`,
    `card.chat_back_seconds` and the words.
  * **Why this is safe.** The swap is local and reversible: the same PC's own
    model is unloaded for a few minutes and reloads on its own; nothing is
    deleted, nothing leaves the PC, and no new way out of it opens. It is the
    same deliberate-confirm shape the project already uses for the phone
    raising a spending limit with its own fingerprint (2026-10-11): a person
    taps the one confirm, there is still no auto-confirm, and no phone-side
    timer sends it.
  * **Still the PC's alone.** Changing where pictures are kept and which
    drawing program draws them (`POST /api/pictures/settings`, `403 pc_only`)
    is this PC's own configuration, not the in-and-out swap.
  * **One picture at a time.** Because a phone may now confirm, a double tap is
    a real second request: a confirm that arrives while a draw is running is
    refused in one plain sentence (`409 needs: "drawing"`) and starts no second
    draw beside the first. The first draw still warms the chat back in its
    `finally`.
  * **Proved, not assumed.** `backend/test_pictures.py` holds the phone's first
    409, the phone's confirmed 200 with the same card times, the desktop
    confirm unchanged, the settings route still refusing the phone, and the
    one-draw-at-a-time sentence; the twin is byte-identical. The swap was then
    driven for real on this PC (Chroma1-HD, ComfyUI 0.39.0 on the RTX 2060):
    with the everyday chat resident, the fixed release wait saw ComfyUI let go
    (`models_freed: true`), the chat came back WHOLE (`size_vram == size`,
    spill 0) 23.6 s after being away 0.5 s, and the picture was 2,087,566 bytes
    drawn in 381.0 s. The phone path was then driven through the same route,
    with `X-Jarvis-Client: phone` on both requests (the first answered 409 and
    moved nothing; the confirm drew a 1,721,489-byte picture in 382.0 s, saw
    `models_freed: true`, and brought the chat back whole 117.1 s after it
    stepped aside, spill 0).

## 2026-10-25 — The browser HUD serves the real face page (the page half)

  * **What was decided.** The owner chose to serve the real face page to the
    browser HUD (2026-10-25), reversing the "serving it was turned down on
    cost" half of this date's earlier cockpit entry. The server half landed in
    PR #814: `faces.html` and its whole import closure are in the published
    base's closed `STATIC_ASSETS` whitelist. This entry records the page half
    (PR #819): in a plain browser the HUD asks for the same
    `faces.html?mode=display&feed=parent` the desktop shell asks for, shows it
    when it loads, and keeps the built-in CSS orb only while the loaded
    document is not the real page (a 404, an error page or `about:blank`), so
    the server's 404 text is never painted. The desktop shell's face path is
    unchanged.
  * **What replaced what.** The earlier entry's reasoning was that the orb was
    the cheap, honest fallback and serving meant twelve static files and
    whitelist entries. The owner decided the real face is worth the files (it
    is sixteen, not twelve: the page, the eleven scripts it loads, and the four
    modules they import), so the orb is now only the fallback a browser lands
    on when the page is not there.
  * **Not deployed by this record.** The live install still answers
    `/faces.html` with the old 404 and still shows the orb until the page, the
    whitelist and the sixteen files are deployed together with the owner's go.

## 2026-10-25 — The browser HUD's face is live on the owner's install

  * **What was done.** The owner was shown one multiple-choice question and
    answered "Merge it, then deploy to live Jarvis." PR #819 merged as
    `8104e6d01f4e035f882e59f1e6b25834fecfdd3c`, and the deploy followed the
    same day: the page, the sixteen face files and the sixteen
    `STATIC_ASSETS` keys went onto the live folder, the backend was asked to
    stop with `POST /api/shutdown` (200, `model unloaded, server stopping`),
    and the app's own supervisor restarted it (pid 41216 -> 38456, 7.9 s after
    the port was released).
  * **What was measured, after the restart, on the live install.** `GET /`
    serves the merged page byte for byte (314,681 B, sha256 `2d0e6b7f...`);
    all sixteen `/faces.html`-closure paths answer 200 with the merged bytes
    and their declared types, while two of them with no token answer 401 and an
    unlisted path 404 (the whitelist did not become a directory). In a real
    headless Chromium the page asks for
    `/faces.html?mode=display&feed=parent` once, gets 200, and the real
    renderer draws (440 px canvas; 844 lit pixels in a 96x96 sample), with no
    console errors, no page errors and no failed requests. The same harness
    measured the opposite before the deploy: zero face requests, orb on, frame
    hidden - a before/after on his own server, not between branches.
  * **What this supersedes.** The page-half entry above ends "Not deployed by
    this record", and `docs/ARCHITECTURE.md` §8 said "Nothing here is deployed
    yet": both understate the live install now, and §8 is corrected to the
    measured state in the same change as this entry. The orb remains what a
    browser lands on whenever the real page is not the document that loaded.
  * **The one side effect, said plainly.** The app's supervisor saw the
    deliberate restart as a crash, logged `backend crash: the backend exited and
    nothing answers`, and recorded one crash note (the file was already at its
    ten-note cap, so the oldest note was pushed out by the app's own rule). That
    note is this deploy, not a real crash.
  * **Rollback.** The live folder's 337 root files were copied before the
    deploy, and the two replaced files have `*.before-browser-face-2026-10-25`
    copies; restoring them removes the sixteen new files (only while their
    sha256 still matches what was deployed) and needs one backend restart.

## 2026-10-25 — A personality can be made by talking to Jarvis

  * **What was decided.** The owner asked for "make your own personality"
    (2026-10-25): chat co-creation first, the Settings "Draft it for me"
    button as the later slice.
  * **What it costs.** Wording only and cardless, drafted on the loopback
    model so nothing leaves the PC, and saved through
    `jarvis_manner.save_user_personality()` with the same caps and the same
    20-personality limit the form enforces.
  * **Both apps, by construction.** The PC reads the phrase out of the existing
    chat request, so the desktop and the phone both get it; the Settings editor
    stays the desktop's.

## 2026-10-25 — The 2026-10-21 approval of the Python lock floor 3.10 -> 3.11 is on the record

  * **What the owner approved, and where it was written down.** On 2026-10-21
    the owner approved three dependency rulings; the approval is recorded in
    that day's rulings document
    (`deepseek_rulings_split_deploy_notion_voice_2026_10_21.md`, Ruling 11.4,
    Guard 4, lines 75-77 of the copy in the owner's `Downloads` folder). That
    document is outside this repository, so its words are quoted here rather
    than left behind a path: "The owner's 3 dependency rulings for Session B
    (`Pillow 13` one-package exception, Python lock floor `3.10 -> 3.11`, and
    naming `tokenizers` + `huggingface-hub` in `backend/requirements.txt`) are
    recorded and approved." The first two rulings are the 2026-10-21 Pillow
    13.0.0 change and the lock's coverage line moving to 3.11; the third named
    `tokenizers` and `huggingface-hub` in `backend/requirements.txt`. This
    entry closes a gap: `docs/DECISIONS.md` has carried the 2026-10-23
    decision that the lock recipe must be fixed before filelock is bumped, but
    not the approval of the floor move that fix depends on.
  * **What used the ruling, in the same change.** `backend/requirements.txt`
    no longer names `tomli`: it existed only for the Python 3.10 range the
    lock stopped covering on 2026-10-21, and its fallback imports only fire
    below 3.11. Both `requirements.lock` twins were then regenerated with the
    repaired recipe at `--python-version 3.11`, and `filelock` was moved
    4.0.0 -> 4.2.1 through it - exactly the order the 2026-10-23 decision
    requires. Measured: every (name, version) pin the old lock carried for
    Python 3.11 and newer is unchanged with the same PyPI file hashes, and the
    only version that moved is filelock. The lock's own header carries the
    exact command and the one-package exceptions.
  * **What it does not mean.** It does not make the backend's Python code
    3.11-only: the modules still import on 3.10, and `tomli`'s guarded
    fallbacks are still in the code. It makes the hash-locked install say what
    has been true since Pillow 13.0.0 was pinned - it needs Python 3.11 or
    newer.

## 2026-10-25 — A private chat is strictly reads-only (H10 ruling, backend Slice 1)

  * **The ruling.** Gemini's H10 answer to the private-chat question
    (2026-10-25, design A) is recorded here as the decision the code
    implements: `"private": true` on `POST /api/chat` is a temporary chat plus
    a zero-write promise, and the boundary is reads-only - a request to change
    something is refused, not executed with a receipt. The gate is the shipped
    `backend/jarvis_private_chat.py`; the hud half is
    `backend/private-chat.patch`. JARVIS-API section 156 is the contract.
  * **Why reads-only, not "actions with receipts".** A cardless action would
    write both the thing it changed and an undo row in `receipts.db` carrying
    the owner's own words - so the chat would not have been private at all.
    The eight stores a turn can reach (chat history, memory and the learner,
    feedback, speed, the route audit, approvals, receipts, the device's
    last_seen) are each gated, and the gate is fail-closed: a missing or
    broken module still refuses the private turn rather than making it
    ordinary. The test suite carries an explicit eight-store table. The agent
    turn itself enforces the tool half: it is handed `private: true`, empties
    its own tool list (the owner's framework file cannot re-enable one),
    refuses any tool call instead of dispatching it, skips the tool-chain audit
    recorder, the next_time/energy writes and the Write Like Me drafting block
    (no voiceprint.db, no embedding-model download, no stored writing sample in
    the prompt) - so the settings and schedule shortcuts, which bypass the
    approval gate by design, cannot run, and no stored words are read back into
    the answer.
  * **What is NOT built.** Neither app sends the flag and neither has a toggle
    or marker; Slice 2 is the apps' half. Nothing here is a live deploy.
  * **The cost, measured.** One shipped module, one 13-hunk hud patch, four
    shipped-module twins changed besides the module (jarvis_quick, jarvis_devices,
    jarvis_agent, rebuilt/jarvis_events), and two hunks that read the owner's
    own HUD text (the body-parse block and the route-audit line), recorded in
    `backend/_stack.py`'s RATCHET (56 -> 58) and in
    `tools/check_patch_original_text.py`'s pin table (2 hunks / 13 lines). The
    two independent reviews' findings are recorded in the PR: fail-closed gate,
    the wrapper drop-on-failure, the explicit deny-all approval gate, the agent
    turning its own tool list off (the framework file had overridden the config
    the first version emptied), the tool-chain/next_time/energy writes, the
    eight-store table and the corrected wording.

## 2026-10-26 — The visible name is "Incognito"; the internal `temporary` field and capability names stay

  * **What changed, and only that.** Every string the owner sees for this
    feature, in both apps and in the words fixture the two share, now calls it
    **Incognito**: the quickbar button's screen-reader name ("Incognito") and
    its two tooltips ("Start an incognito chat: …", "End the incognito chat and
    start a normal one"), the strip's label and its one line on an empty chat
    ("Incognito: Jarvis won't use or learn from your memory, and this chat isn't
    kept."), "Incognito started. Nothing in it is remembered or kept." /
    "Incognito ended. Your next question starts a normal chat.", the refusal an
    older PC gets ("Incognito isn't available on this PC's version of Jarvis, so
    nothing was sent. …"), the unconfirmed-answer warning, "Remember: is off in
    an incognito chat.", the game line ("This looks like a game or role-play, so
    it's an incognito chat: nothing is kept or learned."), and Settings' Write
    like me detail. The two shared History sentences are `tools/gen_history_cases.py`'s
    (`continued_temporary_off`, `game_temporary`), regenerated into
    `jarvis-desktop/tests/fixtures/history-cases.json` and
    `jarvis-client/app/src/test/resources/contract/history-cases.json`; two
    runs were byte-identical and `--check` is clean.
  * **What deliberately stayed, and why.** The name changed, the machine did
    not: the `temporary` JSON/API field and the `"temporary": true` route flag,
    the `temporary_chat` capability, the Kotlin `TemporaryChat` object and
    `setTemporaryChat`, the desktop `TEMPORARY_*` constant names, the
    `temporary-chat` route/id/permission names and the patch filenames are all
    untouched, so no request, header, capability probe or saved record changed
    meaning - only the words. Comments were edited only where they quote what
    the screen says. The feature catalogue's title stays "Temporary chat" in
    `features/features.json`, `contract/feature-controls.json`, both apps'
    `features.json`, `jarvis_feature_catalogue.py` and its twin, and
    `feature-directory.json`; a later change renames that catalogue row, and
    this entry does not pre-empt it. The Live strip still says "Temporary is on
    - this Live session will not be kept in History.", because that sentence is
    `jarvis_live.SEEN["temporary_on"]` on the PC: both apps copy it
    (`SEEN.temporary_on` in `live-rules.js`, `LiveRules.SEEN` on the phone) and
    are held to the generated table by tests, so renaming it needs the backend
    module and the regenerated `live-cases.json` in the same change.

Decided 2026-10-26: the owner-secret hand-off ships first, with its 15-minute secret-page read taint inside it. This reverses the earlier "2 then 1" order, and the reason is measured in `makecindy/cindy`'s source: its taint is triggered only by `onSecretEntered` during the hand-off, so a standalone taint would guard a flow that does not exist and could not be tested against a real typed secret. The host draws the card, shows the HOST-VERIFIED target (a page's scheme+host+path, or a window's executable+PID+title+IsPassword) separately from the agent's cleaned and explicitly-untrusted purpose note, and aborts with ZERO characters typed if the live target, the control, or the password-field property changed, if the card is older than 180 seconds, if it is answered from another machine, or if the value is empty or over 4096 characters. The 15-minute taint is marked BEFORE the first character is typed, lives in memory only (at most 32 targets, monotonic clock), and its keys are page addresses or pid/hwnd/class - never a secret value. The secret itself is never written to disk, a database, a log, the clipboard, model context or a tool result, and `backend/jarvis_secret_handoff.py` imports no storage or logging library at all. Slice 1 is the rule engine only (module, twin, `backend/test_secret_handoff.py`: 82 checks); the wiring into `jarvis_ui_control.py` / `jarvis_browser_control.py`, the host-only route and the HUD card are the next slice, and the phone is deliberately out for now. `docs/DESIGN-SECRET-HANDOFF.md` records both halves and the honest limit that Python cannot wipe memory.

## 2026-10-26 — The apps' half of the private-chat decision has landed: the desktop Private chip, and Incognito as the phone's private mode

  * **What landed, and when.** The desktop Private chip (`#856`, 2026-10-26)
    sends ONLY `"private": true` on `POST /api/chat` (never `temporary` too -
    the PC implies that half) and starts a new conversation when it is turned
    on or off, so a private chat and a normal one never mix; a PC that does not
    advertise `capabilities.private_chat` leaves the mode off and says why
    instead of quietly sending an ordinary chat. On the phone the private mode
    is Incognito (the 2026-10-26 rename above): a temporary chat that still
    runs tools, so it is not the same guarantee as the desktop's private turn.
    The catalogue's own `private-chat` row (`#862`) and the files it generates
    now say so.
  * **The sentence this supersedes, and the older entry keeps its words.** The
    2026-10-25 entry's "What is NOT built" bullet says "Neither app sends the
    flag and neither has a toggle or marker; Slice 2 is the apps' half." That
    is now out of date, and per the append-only rule it is not edited above:
    the desktop app sends the flag and has a chip and a marker, so Slice 2's
    desktop half is built and live. The phone half is still not built on
    purpose - the phone sends no `private` flag and has no Private toggle or
    marker, because its private mode is Incognito - so "neither app" is the
    part that expired, not the phone's own choice.

## 2026-10-26 — The owner approved a read-only Galaxy picture on the phone

  * **The decision, in the owner's words.** *"i want the android phone to have
    a picture B) also design a phone Galaxy picture"*. He approved breaking the
    old "no map on the phone" rule for this one screen, on 2026-10-26. What he
    got is the desktop's own deterministic zen-ring picture, at most 48 names
    (1 centre + 32 on the halo + 15 on the first outward ring), drawn from the
    same `/api/memory/entities` read the phone's list already makes. No name is
    painted on the canvas; every dot carries a TalkBack line, and a tap opens
    that name's existing facts/connections view.
  * **What it replaces, and only that.** It replaces the "no picture / no
    canvas on the phone" part of the 2026-09-30 rule as widened on 2026-10-11
    and 2026-10-23 (`docs/GALAXY-PANEL-DESIGN.md`), and nothing else.
    `/api/graph` stays off the phone and no new route is added. The desktop
    panel remains the interactive map: the constellation and the three flat
    presets, its hover and drag, the merge card and the names under each fact.
  * **What still stands, unchanged.** The phone's memory graph is still
    read-only: no add, edit, delete, merge, drag, pin, Forget or Erase from the
    picture or the list, no approval card and no write of any kind. The picture
    adds no route, no model call, no animation and no GL/AGSL, and it is hidden
    with the other memory lists and while the list shows a past date.
  * **What is not yet known.** No phone or emulator run has happened, so the
    picture's look and a real tap are NOT-TESTABLE: CI compiled the app and ran
    its JVM unit tests on 2026-10-26 (the `build` and `phone-unit-tests` jobs
    passed on #869's head), and a green build is not a field test.
    `docs/FIELD-TEST-MATRIX-2026-10-11.md` records the row as NOT-TESTABLE. The
    layout itself is pinned to the real desktop JavaScript at 1e-6 by the
    generated fixture and `GalaxyPictureTest.kt`; that is a test, not a run on
    a phone.
## 2026-10-26 — Jarvis can talk about an update in chat, and start one only through ONE card

  * **The owner asked, in their own words:** *"can jarvis talk about an update
    if theres one availabale and the changes? and start the update process for
    me?"* - and then *"if i ask in chat"*. Two questions and one action, in the
    window the owner already talks to Jarvis in.
  * **Who answers, and why it is split.** The Tauri shell is the only party
    that knows which version is running and whether this build can verify a
    download (it owns `update.rs` and the signed release). So both chat paths
    the app owns add an optional top-level `desktop` field -
    `{"version": "0.2.320", "can_update": true}` - to the `/api/chat` body, in
    Rust after the page's field whitelist, so no page can set it. The Python
    fast path (`backend/jarvis_quick.py`, no model) reads it and answers from
    the SAME public manifest the app's updater reads
    (`desktop-latest/latest.json`): no report of the running build, a build
    with no update key, a failed check, the newest version, a development build
    ahead of the release page, or an update available - each with its own
    sentence, and "what changed" quotes the release's own notes, never an
    invented list. An empty notes field says the release does not say; a gap of
    more than one version says the notes cover only that release.
  * **The changes have a machine-readable source now.** The release workflow
    writes `latest.json`'s `notes` (and the release body) from
    `jarvis-desktop/scripts/release-notes.mjs`: the `changelog.d/` fragments,
    one summary sentence each, newest first, capped at 20 - and the rolled
    `CHANGELOG.md` bullets only when a roll has emptied the folder, never both
    at once (mixing them would put six weeks of already-shipped changes into
    one build's notes). Until this, that field was one sentence naming the
    commit, so Settings -> Updates showed nothing worth reading. **Honest
    limit:** the desktop version is `major.minor.<run number>` and moves far
    more often than the changelog's numbered versions, so a bullet that was in
    an earlier desktop build can appear again after a roll. The text says
    "from the changelog" and the chat answer says which release the notes are
    for; it is a list of recorded changes, not a promise of the exact delta
    between two builds.
  * **Starting it is ONE card and nothing else.** "Update Jarvis" raises one
    approval card, action `desktop_update`, through `jarvis_gate.check` - tier
    `ask` written into `jarvis-framework.toml`, added to
    `jarvis_owner_check.PC_ONLY_ACTIONS` (only this PC can approve it, and
    Windows Hello comes first), and listed on the **What asks first** page in
    "Jarvis's own settings, memory and voice" with no switch, so it can never
    be loosened to run without asking. `backend/test_asks_first.py` caught that
    row missing on the first pass - the page promises every action a card can
    name, and that is exactly the kind of gap the feature audit exists for. The card names both halves, the version, the
    restart and the pace, and says nothing is downloaded, installed or changed
    before the yes. The owner's Approve goes through the same
    `decide_approval` every card uses (stale-link refusal, App lock, Windows
    Hello); `commands.rs` reads the answered card's own action from the queue
    it already holds BEFORE sending the decision, and only for that action
    does it call `update.rs` `run_approved_update`: a fresh check, then the
    SAME `update_both` the Settings button runs - backend first, then the
    signed release, then a restart. A deny, a timeout, a stale link, a locked
    PC or an unreadable card starts nothing, and the HUD window gained no
    update command (`capabilities/hud.json` is unchanged): the progress it
    shows arrives pushed from Rust, as system lines in the chat.
  * **Why this improves the gate rather than widening it - and what it does
    NOT close.** The self-improvement audit's finding S3 was that the desktop
    updater was the one self-modification path outside the gate: a plain
    command with no gate call, no Windows Hello and no audit line. The
    CHAT-STARTED path now has all three - a gate card, PC-only means Windows
    Hello, and the approvals row is the audit line - and its card is the only
    thing that starts an install ("do it now" in a chat message changes
    nothing). **The Settings button is untouched and is still a direct
    `update_both` call with only its own in-window question, no gate card, no
    Windows Hello and no approvals row.** S3 is therefore improved for the new
    path and still true for the old one; closing it for the Settings button is
    a separate decision the owner has not been asked for, and this change does
    not pretend otherwise.
  * **Both apps.** The desktop answers and starts. The phone is deliberately
    one-sided (recorded in `docs/ARCHITECTURE.md` §8): a phone message carries
    no `desktop` field, so its reply points at **Platform checks**, the phone's
    own update card, where the owner downloads the APK and Android's installer
    needs the tap. The card is PC-only, so a phone Approve gets the standard
    `pc_only` 403 with nothing changed. No route is added,
    `tools/check_parity.py` has nothing new to classify, and the phone's own
    check-and-install is unchanged.
  * **Proven by:** `backend/test_update_chat.py` (the phrasings and
    near-misses, every state's own sentence, exactly one card and no card in
    every other state, the card's words, PC-only + ask, the twin, and the
    manifest URL equal to `tauri.conf.json`'s),
    `jarvis-desktop/tests/update-chat.mjs` (the HUD draws the shell's words as
    system lines and holds no update command), `jarvis-desktop/tests/
    release-notes.mjs` (the notes quote the record and invent nothing), the
    existing Rust tests including the new `chat_facts`/`is_update_card` ones,
    and the three two-file checks. **Not proven here:** a real signed release
    installed by the card - the updater's own installer path was not run in
    this container, and that is the owner's field test, never a pass.

## 2026-10-27 — The "no standing grant" rule is changed by the owner: cloud escalation becomes a switch

The rule that this replaces, in `jarvis_router.choose()`'s own words, was the
owner's decision of 2026-09-24: cloud use is "per use, with permission ... and
asks. **No standing grant.**" Every gate below gate 6 still runs first and can
still only push a turn back to local; what changed is **who says yes**, and
there is now a third answer besides "the owner clicked for this one question"
and "nobody".

**What the owner asked for, 2026-10-27.** A checkbox in the Presets menu -
"escalate to the cloud when the work is too complex" - which, once on, lets
Jarvis send a hard question to the one cloud provider he has chosen without
asking him first. He also asked for the Cloud row itself to sit in that menu
beside General/Coding/Agentic+Vision/Fast, with the six connected API services
under it, and for the three lane names (`jarvis-escalate`, `jarvis-critic`,
`jarvis-bulk`) to become one.

**Why it is not simply a loosening nobody can see.** Four things bound it, and
each is proved rather than described:

  * **ONE card, at ON, and nothing before it.** `POST /api/work/cloud-escalate`
    raises one `change_own_config` card; a refused card writes nothing. Turning
    it OFF is a tightening and is instant - the same asymmetry every other
    switch in this program keeps.
  * **The PC's own file is the only source of the standing yes.** It is read by
    `jarvis_router.standing_escalation()` at gate 6 and from nowhere else - no
    request body, no header and no client flag. The HUD page's own `cloud_yes`
    counts only while that file says on, so a page that has not refreshed
    cannot defeat the switch. Another client's `cloud_yes` (the phone's "Try
    the cloud model") is the per-question tap it already was and is unchanged.
  * **"Escalate this" typed in the message is a yes for that turn only.**
    A fixed phrase list, evaluated at gate 6, after every privacy gate. Nothing
    is stored; the next message has to ask again.
  * **Every gate is untouched and still first.** Lockdown, a tainted
    conversation, a picture, the words off the screen, a private topic, a
    pasted secret, the monthly money limit: a turn refused by any of them stays
    local, and `backend/test_cloud_escalate_setting.py` drives each one with the
    switch ON and the phrase present.

**What this does NOT authorise, said plainly.** No new route reaches the
cloud. No key can be typed, pasted or sent from either app (rule 3): the
provider list carries the command line to run on the PC, and nothing else. The
phone reads the setting and never writes it - turning it on needs the card, and
the card lives on the PC (`docs/ARCHITECTURE.md` §8). One provider at a time.
The money limit still decides whether a message can be sent at all.

**One honest limitation, measured not assumed.** The questions that escalate
are the ones the cloud most often answers with its working-out instead of an
answer: four of four measured escalated turns came back
`finish_reason: "length"` with empty `content`
(`docs/FIELD-TEST-CLOUD-ESCALATION-2026-10-14.md`). On a turn the owner did not
click for, that working-out is **not** shown; the PC answers it instead, under
one line saying the cloud did not answer. That is a real change in what he
sees on those turns, and it is recorded here because the alternative - a page
of a model's private reasoning offered as an answer to a question nobody asked
to send anywhere - is worse than an honest sentence.

**What this replaces, and only that.** The 2026-09-24 "no standing grant" rule,
in the one place it governs cloud escalation. Nothing else moves: the
per-question yes both apps already had, the offer gate, the taint latch, the
private-topic backstop and the secret scan are all as they were, and
`docs/ARCHITECTURE.md` §11's cloud paragraph is amended to point here.

## 2026-10-27 — F-01: a lane you pick by hand runs the same privacy gates

  * **What was wrong, and how it was found.** Two independent reviews on
    2026-10-27 found the same bypass, and it was re-verified against the
    published base before anything changed. `POST /api/chat` picks a lane in
    `jarvis_hud.py`'s `do_POST`, and it had two paths. The automatic one called
    `jarvis_router.choose()`, which runs every gate in a fixed order. The manual
    one - `"auto": false` with a `"lane"` - called
    `_manual_decision(chosen, local_model)`, which built a `Decision` with
    `gate: "manual"` and ran no gate at all. Any client with the pairing token
    could therefore send `{"lane": "<cloud lane>", "auto": false}` and have that
    turn answered on a cloud model with private memory text, a tainted
    conversation, a picture, or the owner's screen attached. Neither shipping
    client sends `lane` today, which is why it was latent rather than seen - not
    why it was safe.
  * **The rule, decided before the change was written.** A manual pick of the
    local model is exactly what it was. A manual pick of any other lane is used
    ONLY when the decision the automatic path would have made for that same turn
    landed on a cloud lane; the pick stands in for the owner's own yes for that
    one question and answers gate 6, nothing else. A refused pick stays on the
    local model and says why. Nothing may leave this PC "just because the owner
    picked the lane".
  * **How it is built, and why that shape.** There is now ONE
    `jarvis_router.choose(...)` call and both paths reach it
    (`if ROUTING:` plus `manual_pick = not body.get("auto", True)`), so a gate
    added to it can never reach one path only - the drift was the defect. The
    rule itself lives in a pure function, `_manual_lane(decide, chosen,
    local_model, lanes)`, so it can be proved by calling it rather than by
    driving a running HUD; `_manual_decision()` turns its answer into the
    `Decision` the rest of the turn reads, and with no router at all a cloud
    pick fails closed to the local model.
  * **What a refused pick looks like, and what it deliberately does not add.**
    No wire field. `X-Jarvis-Route` carries the router's own `gate`
    ("taint", "image", "screen", "private", "secret", "budget", "complexity",
    "lockdown", "unavailable", "cloud_model"), `where` is "local", `lane` is
    the local model, and `reason` is one plain sentence - the same shape a
    refused automatic decision already has, which both apps already draw as
    local. A lane this PC does not offer and a PC with no `jarvis_router.py`
    also stay local. A local pick is untouched: same lane, same reason, same
    gate, memory riding along as before.
  * **The one place the rule is stricter than the brief's examples, said
    plainly.** The brief listed the privacy and availability refusals. The
    implemented rule also refuses a pick on gate 4 (the complexity threshold)
    and gate 5 (the cloud budget), because "the same decision would have
    permitted a cloud lane" is the only reading that cannot be argued with, and
    the safe direction is to refuse. The product consequence, stated rather than
    discovered later: a cloud lane picked by hand answers a SHORT question on
    the local model, with the reason shown. If the owner would rather a manual
    pick outrank the complexity heuristic, that is a one-line change in
    `_manual_lane()` and a decision to record here - never a quiet edit.
  * **Cost, recorded because a reviewer should see it.** Three of the patch's
    four hunks read the owner's own HUD text: the manual path exists nowhere
    else, and `_manual_decision()` is the function whose gates were missing, so
    none of the three can anchor on text an earlier patch writes. `_stack.py`'s
    `jarvis_hud.py` RATCHET moves 58 -> 61 and
    `tools/check_patch_original_text.py` pins
    `f01-manual-lane-gate.patch` at 3 hunks / 37 lines, both with the reason
    written down. The fourth hunk anchors on the line `cloud-say-yes.patch`
    writes and costs nothing. No install block, no gate tier, no app file.
  * **Proven by:** `backend/test_hud_manual_lane_gate.py` - the patch applies to
    the published base and reverses out of it byte for byte; one
    `jarvis_router.choose()` call is counted as an ast node; `_manual_lane` is
    driven with REAL router decisions for a tainted conversation, a picture,
    the owner's screen, a private question, a pasted secret, Lockdown, a spent
    budget, an Ollama cloud model as the everyday model, a lane this PC does not
    offer, and no router at all; the local pick is shown unchanged; and the
    CONTROL lifts the OLD `_manual_decision()` out of the patch's own removed
    lines and shows it returning the cloud lane for the same tainted turn,
    which is what fails on today's code. **Not proven here:** a real HUD process
    answering a crafted `{"lane": ..., "auto": false}` request - this suite
    drives the functions out of the patched file, not the server, and that
    end-to-end run is a field test, never a pass.


## 2026-10-27 — CI parses every Python file, and a suite that runs no check is not a pass

  * **The problem, measured.** The 2026-10-27 test audit
    (`.dsh-scratch/AUDIT-TESTS-2026-10-27/FINDINGS.md`, F-01/F-02/F-07/F-09)
    found four holes in the checks that gate a merge. Two files that say in
    their own headers that they are not tests - `poll-hygiene-measure.mjs`
    (prints one JSON object) and `make-before-overlay.mjs` (copies `src/` to
    `src-old/`) - were counted as passing `frontend` suites. Fourteen backend
    suites carrying 364 `check()` calls were run by no CI job, and no CI job
    even parsed them, so a syntax error in one was invisible to a pull request
    and surfaced during the owner's update. A suite that skipped every check it
    had was still printed as `ok` by `backend/run_suites.py`, because its exit
    code depended only on failures. And the frontend shard count was typed in
    three places, so a `SHARDS` larger than the matrix silently dropped every
    fifth suite.
  * **What now holds.** (1) The required `backend` job's first working step
    compiles every `.py` file under `backend/`, `jarvis-backend/` and `tools/`
    in memory and fails in seconds on the first syntax error. It is not
    `compileall`/`py_compile`: both were measured writing `__pycache__` even
    under `-B` and `PYTHONDONTWRITEBYTECODE=1` (1,090 `.pyc` files in a copy of
    the three folders), and a job that dirties its checkout is a trap for the
    next step that reads the tree. (2) The frontend loop no longer runs those
    two non-tests; the frontend job's selected suites are 225 of the 229
    top-level `.mjs` files (the other four are `uikit.mjs` and `shots.mjs`, the
    harness and the screenshot writer, plus the two non-tests). (3) The shard
    count has ONE definition - the `matrix.shard` list - and both the job name
    and the shell's `SHARDS` read `strategy.job-total`, so a matrix and a
    `SHARDS` cannot disagree. (4) A suite that exits 0 having run no
    non-skipped check is `NO-CHECKS`, neither a pass nor a skip; it fails the
    sweep unless it is on the named `ZERO_CHECK_ALLOWED` list, which holds the
    three suites whose optional package (playwright, cryptography, Pillow) is
    not installed on a bare machine, each with its one-line reason. In the
    required backend job all three packages are installed, so there they still
    run for real.
  * **The 14 audit suites, and which can run without the owner's PC.** Each was
    run DIRECTLY against a staged backend holding every shipped module and none
    of the owner's files (measured 2026-10-27). Four passed and are now in the
    required backend job, naming as a skip whatever still needs the owner's
    whole file: `test_bitemporal.py` (28 passed, 1 skipped),
    `test_extraction_wiring.py` (13 passed, 10 skipped), `test_gate_push.py`
    (7 passed, 6 skipped) and `test_import_history.py` (13 passed, 6 skipped) -
    61 checks CI did not run before. The other ten stay skipped by name, with
    the files each is waiting for, in `run_suites.py`'s `NEEDS_OWNER`:
    `test_approval_notice.py`, `test_decide_once.py`,
    `test_degrade_filter.py`, `test_events_pump.py`, `test_gate_egress.py`,
    `test_gate_outcome.py`, `test_gpu_offload.py`, `test_memory_noise.py`,
    `test_memory_prefix.py` and `test_memory_safety.py`. Four of those exit 1
    at import with no output at all (they import the owner's module at module
    level), three fail checks that read the owner's real file, and three print
    one whole-suite skip and exit 0 - so all ten need `jarvis_hud.py`,
    `jarvis_gate.py`, `jarvis_extract.py` or `jarvis_models.py`, which only the
    owner's PC has.
  * **What is pinned, and what is not yet run.** `backend/test_suite_report.py`
    gained 31 checks (74 in the file now): a zero-check suite is FAILED with
    "no check ran" and the sweep exits non-zero (proved end to end with the
    real `test_apps.py`, whose git guard skips everything when `git` is not on
    PATH); an allowlisted one is `NO-CHECKS`, neither passed nor failed nor
    skipped (proved end to end with `test_browser_control_live.py` and a
    shadowed `playwright`); and a real suite that passed one check and skipped
    one is still `ok`. `backend/test_suite_state.py` still passes unchanged.
    The workflow itself has been parsed with PyYAML, and `strategy.job-total`
    is documented by GitHub as the matrix length in both `jobs.<job_id>.name`
    and `steps.env`.
  * **The rule's own first CI run found two suites that had been proving
    nothing (run 40468616102, 2026-10-27).** The branch's first run went red on
    the new rule, not on a product change, and both failures were real:
    `test_decks.py` printed one skip and ran NO check because `py-fsrs` was
    never installed by either backend job - 349 checks sat unrun on every push
    while the job read green; `fsrs==6.3.2`, the version `requirements.lock`
    pins for Python 3.12, is now installed by BOTH the Ubuntu and the Windows
    backend jobs, so its 351 checks run on Ubuntu and 349 passed with 2
    legitimately skipped on Windows. `test_tool_calling_wiring.py` lifts
    `do_POST`'s text out of `jarvis_hud.py` in all six checks, and that file is
    the owner's patched entry point which no checkout holds - so no CI runner
    can run it at all: it moved into `NEEDS_OWNER` (skipped by name, saying
    which file it waits for) and out of the Windows job's suite list, where six
    skips and exit 0 would have read as a pass. The owner's PC is still the
    only machine it runs on, for real. **What is not fixed:** the Windows job
    still trusts exit codes alone, so a future suite that skips every check
    there would still read as a pass - the Ubuntu sweep is the one with the
    rule, and widening it to that job is named as remaining work rather than
    claimed here. What has NOT happened is a green run of the amended branch:
    the next CI run is what shows the fix.


## 2026-10-27 - the phone reads a typed answer aloud, behind the same gate as the HUD

**Decided:** the phone gets one Read aloud control beside Copy on a finished
typed answer, in Jarvis's chosen voice, through the existing
`POST /api/voice/say` - no new route and no new setting. It never speaks an
answer that used saved or sensitive facts, an answer the PC gated `private`,
one that read the screen or camera, one whose turn ran a tool, one whose
stream could not say, or on a stale link or a locked phone; those keep their
words on screen with the one fixed sentence "It's on your screen.". The cap
is one named constant, `READ_ALOUD_SENTENCE_CAP = 24`, so the HUD read-aloud
slice adopts the identical number. The phone is deliberately stricter than
the HUD's typed path in two places: it refuses when the route header is
missing (the HUD reads `route || {}` and would speak) and it checks the real
tool/screen facts (the HUD typed path still hardcodes `toolsKnown: true`);
the HUD side is to be aligned, and that is a fix there, not a deviation here.

**Why:** the owner asked on 2026-10-27 that the Android app carry the
read-aloud the desktop HUD already had. The 2026-10-16 owner decision that
put the gate on the HUD said in so many words "the bar, the widget and the
phone are unchanged", so this is a new, narrower parity decision - not that
decision read as if it had covered the phone.

**Proven by:** `ReadAloudTest` (every fail-closed branch, the sentence split
and the cap, the refusal wording) and `ReadAloudWiringTest` (one control
beside Copy, the wrapper on every typed send, the PC's say route reused,
arm-before-play, no new route) - both run off-device; the phone drive is a
field-test row, not a pass.


## 2026-10-27 — A setting can be changed by asking for it on or off, and the answer is a read-back

  * **The owner's ask, already on the record.** *"jarvis should be able to
    change all settings if i ask it to in chat or in the live mode, if its a
    big settings change that would impact privacy, security, or significantly
    change functioning it should send me an approval card"*, and *"Let a card
    alone authorise it, from either app"* (:1945-1947). This is the first
    vertical slice of it, and the measure of it is what makes it a slice rather
    than a promise: ONE setting, changed through its own writer, with the value
    READ BACK before the answer says it moved.
  * **What was missing was the plainest sentence.** "Turn on/off <name>" has
    worked since 2026-09-27 (the settings block, `_settings_adjust`), and "can I
    change <name>" has explained how since #884. But "make the prompt coach
    off", "set web search to off", "I want the prompt coach off", "the prompt
    coach should be off" and "make sure <x> is off" matched NOTHING and went to
    the model, which has no settings tool - measured through `match()` on
    2026-10-27, every one of them returned None. So the sentence a person says
    first was the one that did nothing.
  * **The allow-list, and why each exclusion is there.** 27 of the 31
    `jarvis_settings_registry.BOOL_SETTINGS` rows may be changed by asking
    (`jarvis_quick.CHANGE_BY_ASKING`). It is DERIVED by three rules, not chosen
    by taste: its writer is a table entry, so the change goes through the same
    `BoolSetting.set` the Settings switch, the HUD route and "turn on/off"
    already call, and that setter owns the card, the tier, the PC-only refusal
    and the words; `jarvis_feature_guide.read_state` answers a real bool for it,
    so the receipt is a read and never a claim; and its card is not one only the
    PC may approve. Four are out, each for one of those rules:
    `second_card_combined`, `second_card_suggest_struggle` and
    `second_card_suggest_correction` because `read_state` returns None for all
    three today (the second card's features are not measured - CLAUDE.md says
    they stay off until they are), and `lights_without_card` because its card is
    `loosen_what_asks_first`, which `jarvis_owner_check.PC_ONLY_ACTIONS` refuses
    on any other device - starting it from chat would make this lane depend on
    the phone/PC distinction it deliberately does not make. Every remaining one
    is a stored on/off value, so the same sentence the other way round is the
    undo.
  * **Three intents, one of which can write.** `feature_change` is UNCHANGED and
    stays in `READ_ONLY_INTENTS`: "can I change <x>" is a question, it must not
    write, and in a private chat it must still fall to the model rather than be
    refused. `feature_change_ask` is the ONE question back when no state was
    said ("change the prompt coach" -> "Do you want prompt coach on or off? Say
    ... "), and it changes nothing, so it is read-only too.
    `feature_change_apply` is the only one that can write; it is NOT in
    `READ_ONLY_INTENTS`, so "cancel that" knows something happened, and a
    private chat refuses it before any writer can run. The grammar adds no verb
    that already worked: "turn on/off" and "enable/disable" stay the settings
    block's, and the allow-list applies only to the new phrasings.
  * **Card or immediate, and the receipt.** The lane never decides which: it
    calls the setter and reads `Outcome.waiting`. Immediate settings (prompt
    coach, humour, voice follows the face, pictures, the five PC notification
    switches) are written, then re-read, and the answer names the old and the
    new value ("I checked: web search reads on now - it was off before").
    Carded settings (web search ON, background learning ON, picture mode ON, the
    big coder, chat history, the big model, and the rest) answer with the
    module's OWN waiting sentence and never with "done". Nothing was written
    while a card is up, so no read-back is claimed either.
  * **The refusals, and why they are answers rather than errors.** A switch
    outside the list keeps the guide's own change sentence word for word (that
    is what #884's tests pin, and this change does not touch it). A page-only
    setting ("app lock", "autostart") keeps `NOT_BY_ASKING`'s sentence. A
    password, a key, a token, a credential, deep config or an irreversible ask
    is refused in ONE plain sentence, and that sentence is checked only for
    names NOTHING resolves to - so it can never take a real setting's words
    away. The phone/PC distinction is refused by exclusion rather than by a
    sentence: the one PC-only-card switch is not on the list, so no chat
    sentence can start it.
  * **No patch, and that is not an omission.** `jarvis_quick.py` is in
    `scripts/apply-patches.ps1`'s `$SHIPPED` list, and step 3 copies every
    shipped module over the backend AFTER step 2 applies the patches - so a
    patch against it would be applied and then overwritten by the same run. The
    change ships as `backend/jarvis_quick.py` plus its `jarvis-backend/` twin,
    kept byte-identical; `backend/README.md` says so where it describes the
    patches, so nobody adds the dead patch later.
  * **Both apps.** It is one `/api/chat` turn, so the desktop and the phone get
    it with no app change and no new route: the phone already posts
    `/api/chat`, the card it may see is the module's own, and its fingerprint is
    the same authority `change_own_config` already accepts. The phone gains NO
    write route, and `tools/check_parity.py` has nothing new to classify.
  * **Proven by:** `backend/test_ask_to_change.py` - the allow-list derived
    against the real table, every phrasing and near-miss, the writer called
    exactly once with the wanted bool AND the request's peer/local, zero calls
    when the value is already right, the waiting sentence with no "done", a
    disagreement said plainly, a value that cannot be read never written, the
    guide's own words compared word for word for the four excluded switches,
    source pins that the apply runner contains no direct config write and no
    gate decision, and a REAL end-to-end run in a throwaway config folder where
    the real setter moves the value and the real reader sees it, both ways.
    Also `backend/test_feature_guide.py` (1,820 checks, unregressed),
    `backend/test_settings_help.py`, `test_settings_registry.py`,
    `test_settings_switches.py`, `test_private_chat.py` and
    `test_voice_reflex.py`.
  * **Not proven here, and not claimed:** a setting changed on the owner's live
    backend through a real `/api/chat` request (this session works on a copy
    and starts no server), a card approved or denied on a phone, and any of the
    four excluded switches - they are deliberately outside this lane.
