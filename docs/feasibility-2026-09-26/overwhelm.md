# Feasibility audit - the Overwhelm reviewer (2026-09-26)

**My question:** would this set of ideas bury the owner in settings,
approval cards, notifications, screens or Jarvis talking unasked? For each
idea: does it earn its place, can it be off by default or tucked away, is
there already ONE place it belongs, and does it reuse the same words?

Read-only. Paths are from the repo root (`/home/user/Epic-Jarvis`). Every
code claim was checked in the file named; "not checked" where not; report
claims I did not re-check say "(per <report>)".

## How crowded Jarvis already is (the starting point, all checked)

- **Desktop Settings has 21 sections** (21 `<h2>` headings in
  `jarvis-desktop/src/settings.html`, from "Connection" at :51 to "What this
  backend supports" at :1320). The **desktop Brain has 8 tabs** (Memory,
  History, Faculties, Work, Galaxy, Live, Trust, Watch -
  `jarvis-desktop/src/brain.html:53-110`).
- **The phone's Brain is already a long scroll:** the creativity audit
  counted "~14 sections" to scroll past before reaching saved facts
  (`docs/creativity-2026-09-25/experience.md:38`). The phone app has 11
  screens (`Nav.kt:74`) and about 33 switch rows across its screens (grep of
  `Toggle(` / `SwitchRow(` / `ApprovalSwitchRow(` call sites in
  `jarvis-client/.../ui/screens`, a rough count).
- **The phone has 5 notification channels**: link status, approvals (loud),
  approvals (quiet), alarms (`JarvisApp.kt:35-122`) and the wake-word
  service (`service/WakeWordService.kt:718-719`).
- **"What asks first" already lists ~58 actions in 10 groups**
  (`backend/jarvis_asks_first.py:208-233`). It is the one place every
  "does this ask?" answer belongs.
- **The owner has spent two audits cutting cards.** The creativity audit
  estimated "4-9 cards on a normal day, 10-18 if lights are voice-controlled"
  (`docs/CREATIVITY-AUDIT-2026-09-25.md:28-31`); the approvals audit then
  removed cards for repeats, lights and everyday facts (`CLAUDE.md:286-305`).
  **Any idea that adds a daily card works against a decision the owner has
  already made twice.**
- **Good news - the "one place" parts already exist:**
  - one scheduler: every timed thing is a `register_kind(...)`
    (`backend/jarvis_schedule.py:313-353`); a new kind asks by default
    (`docs/ARCHITECTURE.md:1547-1550`);
  - one "tell me when" kind with sources `email` and `home`
    (`backend/jarvis_tellme.py:1-60`, `:249-254`);
  - one offer gate: at most 3 unasked offers waiting
    (`MAX_WAITING = 3`, `backend/jarvis_backoff.py:88`), none in Quiet or
    Standby, "no" backs off 1/7/30 days (`:94`);
  - one digest screen on the phone: Inbox, "the brief, the shelf and the
    running jobs ... One screen rather than three, because none of it is
    urgent" (`ui/screens/InboxScreen.kt:41-49`);
  - "What did I miss?" already exists (`backend/jarvis_quick.py`,
    `jarvis_briefing.py`, both apps' briefing code - grep).

## The count (the headline)

Legend for the table's "Adds" column: **S** = a new setting the owner can
see; **C** = a new KIND of approval card; **N** = a new kind of
notification; **P** = a new page, tab or settings section; **V** = Jarvis
speaking without being asked. "0" = nothing new the owner has to see.

**If every idea I mark "build" (54 ids) were built, the way I recommend:**

| New | Count | Which |
|---|---|---|
| Settings | **6** (8 as the reports propose them) | speaking speed (I28); one folder list shared by files, documents, the library and the Notion import (I39/I40); plug-in servers list, PC only (I07); backup place (I96); devices list (I102); "follow Windows Focus" (I122). The reports' versions add two more: a media "no card" switch (I91) and a help-line country picker (I151) |
| Kinds of approval card | **4** (5 as proposed) | start a plug-in server (I07); restore a backup (I96); pair a new device (I102); the tidy's "are these the same? / still true?" cards (I37, owner-chosen). Proposed I91 adds "turn on media without a card" |
| Kinds of notification | **3** | the weekly goal check (I63); tidy cards (I37); "the backend kept crashing, I stopped restarting it" (I98). Plus more of the EXISTING "tell me when" notification from new sources (I66, I69, I82) |
| Pages / sections | **6** | Today (I117 - must absorb, see point 1); "Things you can say" (I116, a pop-up list, not a nav entry); Backup (I96); Devices (I102, inside Security); plug-in servers (I07, inside "What Jarvis can reach"); folders (I39-41) |
| Unasked speech | **0** | nothing in the build set speaks on its own |

**If EVERY one of the 155 ideas were built as the reports write them:**
about **39 new controls** (my estimate, adding them up row by row: e.g.
I136-I138 alone are 3 presets + 6 dials + "Call me" = 8; I73 is a switch
plus an app list; I79 is a switch plus a room per device), **~12 new kinds
of card**, **~14 new kinds of notification or daily/weekly prompt**
(I19, I37, I49, I57, I63, I67, I70, I71, I74, I82, I85, I98, I109, I118,
I124), **~15 new pages or lists**, and **3 sources of unasked speech**
(I19 household sounds, I85 welcome home, I147/I148 face life is visual
only). That would roughly double the desktop's 21 settings sections. It is
the main reason most of the list is "build later" below.

---

## 1. One line per idea

Verdicts: **build** / **build later** / **don't build** / **no objection**
(= nothing for the owner to see, or already built; I have no say).
For owner-chosen ideas I review HOW, not whether.

### Engine (I01-I13)

| Id | Verdict | Reason (plain words) | Guardrails / cost | Adds |
|---|---|---|---|---|
| I01 | build | Replaces a wrong "restart Ollama" message with a true one. Less confusion, not more. | No setting. One fixed sentence, same wording in both apps. | 0 |
| I02 | build | Invisible second lock. | No setting; a preflight line only if it is missing. | 0 |
| I03 | no objection | Numbers for the owner's measuring, not for daily use. | Put it in the existing Hardware "Details" / preflight, never on the main screen. | 0 |
| I04 | no objection | Invisible; same single retry. | - | 0 |
| I05 | build | PC test tool; nothing in the apps. | One test harness for I05, I95 and I133 (the Fit reviewer says the same). | 0 |
| I06 | build | Invisible to the owner; fewer tools in front of the model. | **No per-tool on/off list in the apps.** Show "offered always / on request" inside the existing "Tools the AI model is offered" (`settings.html:971`), not a new page. | 0 |
| I07 | build | Owner chose it. Risk: a plug-in page and a card every time a server starts. | Set up on the PC only, listed inside "What Jarvis can reach" (`settings.html:964`). **Card when a server is added or its pinned version changes, not at every launch** - "a card to start each server" read as "every start" means a card per server per reboot (question for Rules, below). Start with 2 servers at most. | S1 C1 P1 |
| I08 | build later | Invisible speed switch; measure first. | No setting; a Modelfile line. | 0 |
| I09 | no objection | A test; results go into the existing Hardware "Measure". | No new screen. | 0 |
| I10 | build later | **Removes** a model swap and could merge two second-card switches into one - a simplification. | When built, fold "Longer conversations" and "Pictures" into one switch if one model serves both. | 0 (could be -1) |
| I11 | build later | One card per plan is fine, but it is a big new mode. | After I27 (show, then click). Card shows the cropped picture; never a loop. | 0 new kinds (uses control_computer) |
| I12 | build | Fills a gap in an existing screen (desktop reads only the first card: `commands.rs:2617`). | Same Hardware screen and widget; one line per card; **no new "card is hot" notification**. | 0 |
| I13 | build later | One-off measuring job. | Tuck under Hardware "Details"; the PowerShell line uses the existing Copy pattern. No setting. | 0 |

### Voice & vision (I14-I30)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I14 | build | Owner chose. Automatic when the model cannot see pictures. | **No "OCR on/off" switch.** The existing outside-text marking says what happened. | 0 |
| I15 | build | Owner chose. Replaces a part; fewer false wake-ups means fewer interruptions. | No "which detector" choice. Swap only after the measured test. | 0 |
| I16 | build | Owner chose. Risk: a third voice engine to choose between. | It appears as a voice in the existing Voices list, not an "engine" setting. If it wins, it **replaces** ZipVoice; never three engines on screen. | 0 |
| I17 | build later | Waits for the card. | Inside the existing "Second graphics card" switches (`settings.html:756`), not a new section. | 0 |
| I18 | build later | A switch the owner cannot judge ("name hints") with a known 20% bad-text bug (per VV). | **No switch.** Measure it; ship it on if it helps, not at all if not. | 0 |
| I19 | don't build | Always-on listening, a new card, a new notification kind, and a "not a safety device" warning, for alarms that are already loud. Much for little. | If ever: PC only, off by default, on by one card, inside "tell me when". | (S1 C1 N1) |
| I20 | build later | Invisible model choice. | No setting. | 0 |
| I21 | build later | Invisible; kept only if measured better. | No setting. | 0 |
| I22 | build later | **Reduces** false recordings (a fan or TV starting one). | No setting; replaces the loudness trigger. | 0 |
| I23 | build later | Invisible; only if the numbers say so. | No setting. | 0 |
| I24 | build later | Replaces F5, not adds. | No second "better voice" choice; the existing "The better voice" section (`settings.html:557`) keeps one. | 0 |
| I25 | don't build | No reliable detector exists (per VV). | - | 0 |
| I26 | build later | Adds friction to every hands-free turn. | Only as part of "Only trust the talk button" or a choice beside it - never the default, never a new section. | (S1) |
| I27 | build later | No card; helpful for a beginner. | Needs the second card. | 0 |
| I28 | build | The setting already exists but no app shows it (`tts_speed` read at `backend/jarvis_voices.py:251-252` and `jarvis_speech.py:1818`; no hit in either app's code - grep). | Three choices (Slower / Normal / Faster), inside "Jarvis's voice" (`settings.html:499`) and the phone's Voices screen. No card. | S1 |
| I29 | build later | Big, fun, and it pushes the long-conversation model aside. | One more second-card switch, inside that section. | (S1) |
| I30 | don't build | Fun only; downloads and card time. | - | 0 |

### Memory (I31-I38)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I31 | no objection | Already merged (see section 3); invisible. | - | 0 |
| I32 | no objection | Already merged; a test. | - | 0 |
| I33 | no objection | Already merged; invisible. | - | 0 |
| I34 | no objection | Already merged; invisible. | - | 0 |
| I35 | build later | Invisible; "Erase the words" must wipe the hints too. | Never shown in any list. | 0 |
| I36 | build | Invisible re-ordering. | Reuse `jarvis_past.py`'s date parser, not a second one (Fit agrees). | 0 |
| I37 | build | Owner chose it, cards only. **Biggest new card source in the set:** "at most 5 cards a night" (`docs/MEMORY-RESEARCH-2026-09-26.md:103`) is up to 35 a week. | **Cap at the back-off's 3 waiting** (`jarvis_backoff.py:88`; MEM's 5 does not fit under it - Rules found the same clash). Send them on the **quiet** approval channel (`JarvisApp.kt:86-94`, no sound). Show them as one "Tidy suggestions" list in Brain -> Memory. None in Quiet/Standby. Unanswered = "not now". The switch to turn it on already exists (MEM :103, "already built"; not checked). | C1 N1 |
| I38 | build later | Owner decided it waits. | When built: no setting; answers only when asked. | 0 |

### Knowledge & documents (I39-I60)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I39 | build | Useful and asked by voice. | **One folder list** for I39, I40, I41, I66's folder watch and the owner's new Notion import (`CLAUDE.md:376-381`): "Folders Jarvis may look in", PC only, empty by default. Not four lists. | S1 P1 (shared) |
| I40 | build | Owner chose. | Uses the same folder list; no setting of its own. | 0 |
| I41 | build later | The search half of I40. | Same folder list; no second index screen. | 0 |
| I42 | build | Valuable, but "a list under every answer" is clutter. | **Merge with the existing "Used N memories" line** into ONE collapsed line: "Used: 2 memories, 1 note, 1 web page". Opens on tap. Also carries I132. | 0 |
| I43 | build later | Voice-only; adds nothing to a screen. | Lives in the daily note; no reading-list page. | 0 |
| I44 | build later | Four parts; the wiki builder is not measured yet (per Fit). | The report goes in the existing Wiki section, not a new page. | 0 |
| I45 | build later | On request only. | Show query and answer in the chat, not a new screen. | 0 |
| I46 | build later | On request only; long job. | Uses the existing job list and Stop. | 0 |
| I47 | build later | On request only. | No setting; `file_read` refuses browser folders today (per Fit). | 0 |
| I48 | don't build | A third "read a private stream, off by default, on by card" switch beside notifications (I73) and history; very private, rarely needed. | - | (S1 C1) |
| I49 | build later | Makes the briefing longer; a feeds list plus a card per feed. | Decide with I67 as ONE "outside pages" setting. Headlines capped (e.g. 5). | (S1 C1) |
| I50 | build later | "Open in Obsidian" button only. | **No second galaxy layer** - the Brain already has a Galaxy tab (`brain.html:87`). | 0 |
| I51 | build later | Invisible. | - | 0 |
| I52 | build | "Detect and say so" is one plain sentence. | No setting. | 0 |
| I53 | build | Owner chose. Drafts are rare and owner-asked, so a card each is **not** overwhelm. | `draft_email` already has a row in "What asks first" and is a hard limit (`jarvis_asks_first.py:179`, `:218`): no new row. Overwhelm has no objection to "always a card" - and a draft does leave the PC to Gmail (Rules). | 0 |
| I54 | build later | One extra line on the send card. | The `.vcf` path joins the PC's email settings, not a new section. | 0 |
| I55 | don't build | Not useful with Google's read-only calendar link (per Fit). | - | 0 |
| I56 | build later | Needs I14 and I40. | No new screen; the note card already exists. | 0 |
| I57 | build later | Spaced-repetition review is a **daily nag machine** by nature. | Reviews show in Today, never a ringing notification; nothing due unless the owner made a deck; no streaks. | (N1) |
| I58 | build | A command, no screen. | No setting. | 0 |
| I59 | build later | Typed practice works already in a temporary chat. | No setting. | 0 |
| I60 | build later | Chat-only. | Any edit later = a diff card, which does not exist yet. | 0 |

### Routines & agents (I61-I74)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I61 | build later | **Fewer cards** (one plan card instead of one per step) - a win for overwhelm, if Rules clears it. | At most 8 steps on one card (per R3-ROUT); risky steps still get their own. | 0 new kind |
| I62 | don't build | A second "saved routine" idea beside skills, which already exist (per Fit). Two names for one thing confuses. | Fold "Try it" and "read back" into skills instead. | 0 |
| I63 | build | Small, the owner's own words, and a real gap. Risk: a weekly check per goal. | **One weekly check for all goals together**, shown in Today and the briefing, not one notification per goal. At most ~5 active goals. No card (declare the kind `plain_repeat`). | N1 |
| I64 | build later | After I63. | Re-plan offers through the back-off gate (counts toward the 3). | 0 |
| I65 | build later | One line per card ("can be undone" / "cannot be undone"). | Reuse the existing undo shelf (`/api/undo`, `docs/JARVIS-API.md:1042`); no new undo screen. | 0 |
| I66 | build | Same card, same list, same notification as today's "tell me when". | The folder comes from the one folder list (I39). | 0 |
| I67 | build later | New way out; decide with I49. | Inside "tell me when"; one card per page. | (C0) |
| I68 | build | Owner chose. Faster, invisible. | **No "instant vs every 5 minutes" setting.** | 0 |
| I69 | build | Same card and list. | Same words as today's "tell me when" notification. | 0 |
| I70 | build later | Overlaps the existing Watch tab (`brain.html:110`) and "tell me when". | Put it in ONE of them, not both. | 0 |
| I71 | build later | Second card; "Ready for you" would be yet another inbox. | Results land in Today / the phone's Inbox, not a new page. | 0 |
| I72 | build later | Chat-only; one card. | No "research" page. | 0 |
| I73 | build later | Owner chose; queued. | One switch plus the app list on the phone's Security or Inbox screen; **never notify about notifications**; shown only when asked. | S1 C1 (when built) |
| I74 | build later | A weekly card on top of I63 and I118; also needs the I38 rule change (per Fit). | If built, part of "Close the day" on Sundays, not its own card kind. | 0 |

### Home and the PC (I75-I94)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I75 | build | Owner chose. Fills a "not available" line (`backend/jarvis_briefing.py:117`, `:338`). | No "weather source" setting; HA's forecast entity or the existing "not available" line with one plain reason. | 0 |
| I76 | build later | On request only. | - | 0 |
| I77 | build later | ONE device list, managed in HA, would be simpler than two. But not over HA's HTTP MCP (per Fit). | Via the plain HA connection (I78's client). | 0 |
| I78 | build later | **Fewer cards** ("downstairs lights" = one card). | Q1: one card per room (recommended); the existing 10-device cap applies. | 0 |
| I79 | build later | A switch plus a room per device. | After I102; the room sits on each device's row in the Devices list, no new page. | (S1 C1) |
| I80 | build later | One line on a card. | - | 0 |
| I81 | build | A preflight warning, no screen. | WARN only. | 0 |
| I82 | build | Already possible with the `home` source (per Fit). Risk: "person detected" fires a lot. | Default "tell me once" (already the default, `jarvis_tellme.py:53-55`); suggest a 10-minute quiet gap between repeats. | 0 |
| I83 | build later | Own card; on request. | - | (C1) |
| I84 | build later | A number on the Hardware screen. | No new screen. | 0 |
| I85 | don't build | Unasked summary plus an offered card every time the owner comes home. "What did I miss?" already does it on request. | If ever: off by default, on screen only (never spoken), counts toward the 3 offers. | (S1 N1 V1) |
| I86 | build later | Briefing lines. | Only when notable ("toner low"), never "toner 64%". | 0 |
| I87 | build later | A switch or a card per add. | Mirror the existing named lists; no second shopping list. | (S1 C1) |
| I88 | don't build | Would make standing automations; and a stream of "shall I automate this?" offers. | - | 0 |
| I89 | build later | Useful; one button on the phone. | Q2 as recommended (HA's button). | (S1) |
| I90 | don't build | Admin prompts and a PC that is Jarvis's only clock (per Fit). | - | 0 |
| I91 | build | A card for "pause" would be absurd. | **Overwhelm's view: no card AND no setting** - pausing the PC's own media is instantly reversible and only from the owner's words, like timers. If Rules says a switch is needed, it goes as a row in "What asks first", not a new section. | 0 (S1 C1 as proposed) |
| I92 | build later | On request; one card per package. | Never "update all". | (C1) |
| I93 | build | Owner chose. A button on alarm/event rows. | **No setting.** One button, "Also on my phone", with the two-alarms warning as one line. | 0 |
| I94 | build later | One button. | - | 0 |

### Trust & safety (I95-I115)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I95 | build | PC test; decides whether I104-I108 are needed at all. | Same harness as I05/I133. | 0 |
| I96 | build | Real protection; one section. | One "Backup" section on the PC: where (Q1: this PC or a USB drive), "Back up now", last backup date. Recovery code shown once. Restore on the PC only. **An old backup is a preflight WARN, not a notification.** | S1 C1 P1 |
| I97 | build | Preflight lines only. | WARN, never a notification. | 0 |
| I98 | build | No setting. | One desktop message when it gives up after 3 tries. | N1 |
| I99 | build | Invisible. | - | 0 |
| I100 | build later | Owner's call. | If ever: PC-only setting, off. | (S1) |
| I101 | build later | After I96. | No setting unless needed. | 0 |
| I102 | build | Owner chose. | "Devices" list inside the existing Security section (`settings.html:321`) and the phone's Security screen; one card per new device; no per-device permission matrix. | S1 C1 P1 |
| I103 | build | Owner chose. | Fingerprint only on risky cards, never on every card. | 0 |
| I104 | build later | Adds a warning line on some cards. | **One "outside text" warning slot per card** shared by I104, I106, I108 and today's line (`jarvis_agent.py:2615-2684`, per Fit) - never three warnings stacked. | 0 |
| I105 | build later | Invisible. | - | 0 |
| I106 | build later | Label only. | Same single warning slot. | 0 |
| I107 | build later | Invisible. | - | 0 |
| I108 | build later | Warning only. | Same single warning slot. | 0 |
| I109 | build later | The ledger exists (Brain -> Trust, `brain.html:102`). | The weekly count lives on the Trust tab only; **never a weekly notification**. | 0 |
| I110 | build | Friction where it belongs. | **Risky ("heavy") cards only**, never every card, or every lights card becomes 2 seconds slower. | 0 |
| I111 | build later | Owner-facing complexity (a copy, a switch, a way back). | One command, one plain result. | 0 |
| I112 | build later | After I102. | "Approved on Pixel 8" is one line on the card. | 0 |
| I113 | build | Fewer places private text shows. | **No watch setting** (the unmerged worktree already keeps everything on the phone; the owner's question was answered in code - see section 3). | 0 |
| I114 | build | No setting ("always", the recommended answer). | - | 0 |
| I115 | build | No setting. | One fixed line in the chat. | 0 |

### Experience (I116-I128)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I116 | build | **Anti-overwhelm:** a beginner cannot guess the phrasing. | A pop-up from the text box (`/` or "?"), not a nav entry. Words served from `jarvis_quick` so both apps match (per Fit). | P1 |
| I117 | build | Only as **the one home for "my day"** - it must absorb, not add. | On the phone, grow the existing Inbox screen (`InboxScreen.kt:41-49`) into it, don't add a 12th screen. I63, I57, I71, I74, I85, I118 land INSIDE it. "Waiting on you" = titles + "Open the card", never Approve. | P1 |
| I118 | build later | A box on Today. | No evening notification by default; the owner can set a plain reminder if wanted. | (S1) |
| I119 | build later | **Anti-overwhelm** for first run. | Reuse `onboarding.html` and the preflight, not a new wizard. | 0 |
| I120 | build later | One Windows menu entry. | - | 0 |
| I121 | build later | Phone Share entry. | - | 0 |
| I122 | build | Small. Risk: Jarvis goes Quiet "for no reason" the owner can see. | One switch, **off by default**, inside the existing Focus section; the status line says "Quiet: Windows Focus is on". Phone tile needs no setting. | S1 |
| I123 | build later | Overlaps I122 and asks for a phone permission. | If built: one switch in the same Focus section. | (S1) |
| I124 | build later | Replaces the end-only notification with one live one. | One ongoing notification for all running timers, not one each; only for timers over a minute. | 0 |
| I125 | build | No setting; four shortcuts. | Same App lock. | 0 |
| I126 | build later | A third widget. | Counts only; off the lock screen. | 0 |
| I127 | build | Checks, not UI. | - | 0 |
| I128 | don't build | Large for a beginner-maintained app (per Fit). | - | 0 |

### Personality & character (I129-I150)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I129 | build | Invisible wording. | No "honesty" setting (the reports agree). | 0 |
| I130 | build later | After I133. | - | 0 |
| I131 | build | Fixed answers; no screen. | - | 0 |
| I132 | build | One line on an answer. | Part of the single "Used: ..." line (see I42), not a second line. | 0 |
| I133 | build | PC test. | One harness with I05/I95. | 0 |
| I134 | build | Preflight WARN. | - | 0 |
| I135 | build | A test that keeps cards and errors plain. | - | 0 |
| I136 | build later | **Duplicate inside the report:** "Patient teacher" preset AND an `explain_simply` dial (`CUTTING-EDGE-2026-09-26-round4-growth.md:57`, `:61`). | Keep it as a preset only. | 0 |
| I137 | build later | After I133. | Part of I138's fold, off at first. | 0 |
| I138 | build later | As proposed: 3 presets + 6 dials + "Call me" = 8 controls in both apps. Too many for a wording feature; `formality` overlaps Plain, `explain_simply` duplicates Patient teacher. | **3 presets + "Call me" on screen; at most 3 dials (length, humour, lists) under a closed "Fine-tune" fold;** the rest changed by saying it (I140). After I145. | S2 (after trimming) |
| I139 | build later | With I138. | In Brain beside "Always keep in mind", not a new tab. | 0 |
| I140 | build later | **Reduces** controls: change style by saying it, with Undo. | Same live-turn checks as automatic learning. | 0 |
| I141 | build later | Another kind of offer. | Counts toward the same 3 offers. | 0 |
| I142 | build later | "Between us" as its own list is a third memory-ish list. | Ordinary facts with a label, shown in the existing memory list with a filter, not a new list. | 0 |
| I143 | build later | A third style list. | After I138-I142; within the "How Jarvis talks to you" list. | 0 |
| I144 | build | Invisible. | - | 0 |
| I145 | build | **A simplification:** eight older persona modes sit unseen in the backend's settings (per R4-CHAR; `jarvis_persona.py` not in this repo, per Fit). Settle them before adding ANY style control. | Look first (S). | 0 |
| I146 | build later | Chat only. | - | 0 |
| I147 | build later | Visual only. | Reduced motion respected. | 0 |
| I148 | build later | Visual only. | Never looks like "approval"; reduced motion respected. | 0 |
| I149 | don't build | No face with a mouth. | - | 0 |
| I150 | no objection | Guidance. | - | 0 |

### Wellbeing (I151-I155)

| Id | Verdict | Reason | Guardrails / cost | Adds |
|---|---|---|---|---|
| I151 | build | A floor worth having; shows only on a crisis turn. | **No picker in Settings** if the country can be set once at first run or in the one-time setup; never counts, never follows up. | 0 (S1 as proposed) |
| I152 | build | Invisible. | - | 0 |
| I153 | build later | Invisible wording. | - | 0 |
| I154 | build | Invisible. | No mood log. | 0 |
| I155 | don't build | Duplicates I133 (per Fit). | - | 0 |

Totals of my verdicts: **build 54, build later 81, don't build 12,
no objection 8** (155).

---

## 2. "Keep Jarvis simple" - guardrails for the whole set

1. **One home for "my day": the Today page.** The briefing, "What did I
   miss?", Coming up's next items, goals (I63), quiz reviews (I57), night
   results (I71), close the day (I118), the journal (I74) and any welcome
   home (I85) show THERE. None gets its own screen or its own daily
   notification. On the phone, Today is the existing Inbox screen grown, not
   a new one.
2. **One place per kind of thing.** Every "does it ask?" is a row in "What
   asks first" (no new permission sections). Every watched thing is a
   "tell me when" source. Every timed thing is a scheduler kind. Every folder
   is in one "Folders Jarvis may look in" list. Every unasked suggestion goes
   through the back-off gate and shares its 3 slots.
3. **Invisible by default.** An engine swap, a model, a detector, a
   re-ranker or a speed-up gets **no switch**: measure it, then ship it or
   don't. A switch the owner cannot judge ("name hints", "OCR") is a
   question pushed onto him.
4. **Replace, don't add.** A new voice, voice engine, wake detector or model
   replaces the old one on screen. Never three engines to choose from.
5. **Off by default; loosening is a card; tightening is instant** - the
   existing pattern. No new setting starts "on" if it shows, hears or trusts
   more.
6. **Advanced things fold away.** Fine-tune dials, measuring tables,
   plug-in servers and crash-dump options sit under a closed fold or in
   Hardware "Details", PC first.
7. **No new daily card.** A new card kind must be rare (setup-time) or
   owner-asked. Anything that could come daily (the tidy) is capped at the
   back-off's 3 and uses the quiet channel.
8. **Nothing speaks unasked** that does not speak today. New voice lines
   only in answer to the owner.
9. **One line under an answer**, not a stack: memories, sources and "no
   saved fact was used" share one collapsed "Used: ..." line. One
   "outside text" warning slot per card, however many checks feed it.
10. **The same words.** New features reuse the existing phrases: "Open the
    card", "What asks first", "tell me when", "Coming up", "outside text",
    "Quiet", "Forget" / "Erase the words". A test like the card-words one
    (`jarvis_card_words.py`) should cover new fixed lines (I135).
11. **Say it instead of finding it.** Where a feature can be changed by
    saying it ("from now on shorter", "tell me when ..."), the screen
    control can stay small; I116 teaches the phrases.
12. **Budget check per batch:** before a batch lands, the feature audit
    counts new S/C/N/P/V like the table above. More than 2 new settings or
    1 new card kind per batch needs a line saying why.

---

## 3. Objections for the other reviewers

- **Fit:** you have I117 (Today) as "build later"; I have it as "build",
  but ONLY as the consolidation hub - because five other ideas (I57, I63,
  I71, I74, I118) each need somewhere to land, and without Today each will
  grow its own screen or notification. If Today waits, those must wait too.
  You also have I19 and I85 as "build later"; I say don't build (always-on
  mic for a non-safety alert; an unasked summary that duplicates "What did
  I miss?"). I62: you say build later as a duplicate of skills; I say don't
  build it as a separate idea at all.
- **Rules:** (a) I91 - I propose **no card and no setting** for pause/next
  on the PC's own media, owner's words only, like timers. You propose the
  lights pattern (a switch, on by card). Which rule requires the switch?
  (b) I07 - "a card to start each server" (`CLAUDE.md:349`): is that each
  launch, or each server once (and on a version change)? Per launch is a
  card per server per reboot. (c) I37 - we agree 5 does not fit under the
  back-off's 3; but lowering the owner's "cards only" cap is his call.
  (d) I53 - overwhelm has no objection to a card per draft; I would not use
  "fewer cards" as a reason to skip it.
- **Security:** I merge warnings (one slot per card for I104/I106/I108),
  which you may see as hiding detail. My ask: the slot shows the strongest
  warning first and "and N more" on tap - nothing is dropped. I110's
  2-second delay: I support it on risky cards only; if you want it on every
  card, that adds friction to every lights card and pushes back on the
  approvals audit.
- **Hardware:** no disagreement expected; my only ask is that measuring
  results (I03, I08, I09, I13) live in Hardware "Details", not on the main
  Hardware view.
- **Upkeep:** fewer settings = fewer tests and fewer parity rows. Trimming
  I138 to 3 presets + "Call me" + a fold with 3 dials saves roughly 5
  controls x 2 apps of tests. Where I keep a fold PC-only, it needs a §8
  "one-sided on purpose" row (`docs/ARCHITECTURE.md` §8).
- **Devil's advocate:** my "build" list is still 54 ids. Most are invisible
  (engine, tests, preflight lines); only ~15 add anything the owner sees.
  If you want the list cut further, cut by the "Adds" column, not by size.
- **Everyone:** the owner's newest decision - "Bring in my Notion export"
  (`CLAUDE.md:376-381`) - is **not in the master list** (00-ideas.md). It
  adds "a folder Jarvis searches"; it must use the same folder list as I39,
  I40, I41 and I66, not a fourth.

## 4. Wrong or out of date in the reports (with evidence)

1. **00-ideas.md note 1 is out of date:** memory ideas 1-4 are merged, not
   only in a worktree. `git log` shows `1381e6a Merge branch
   'worktree-agent-a4d69393e5376ccb0'`, and `git merge-base --is-ancestor
   9abdd68 HEAD` succeeds. (The notification commit `e372eb7` is still NOT
   in HEAD - checked the same way - so note 2 still holds.)
2. **00-ideas.md misses an owner decision:** the Notion import
   (`CLAUDE.md:376-381`, commit `e656093`) has no id.
3. **R4-GROW duplicates itself:** the "Patient teacher" preset and the
   `explain_simply` dial are the same thing
   (`docs/CUTTING-EDGE-2026-09-26-round4-growth.md:57`, `:61`, `:170-171`),
   and its `formality` dial overlaps the Plain preset. None of the round
   reports counts how many settings its ideas add.
4. **MEM idea 7 does not fit the existing gate:** "At most 5 cards a night,
   under the existing back-off" (`docs/MEMORY-RESEARCH-2026-09-26.md:103`),
   but the back-off allows at most 3 waiting (`backend/jarvis_backoff.py:88`).
   (Rules found the same.)
5. **Shipped code vs. the reports' "no streaks":** R2-PER lists "Streaks
   and guilt nudges" as not for Jarvis
   (`docs/CUTTING-EDGE-2026-09-26-round2-personality.md:272-273`), and
   R4-GROW lists streaks among companion hooks (`round4-growth.md:303`) -
   but the focus report card already shows a streak and "The streak starts
   again ..." (`backend/jarvis_focus.py:33`, `:702-704`). The owner's
   decision said "ends with a report card" (`CLAUDE.md:273`), not a
   streak. Not a bug; a mismatch for the owner to see. The reports did not
   notice it.
6. **I113's owner question was answered in code without the owner:**
   00-ideas note 2 already says this (commit `e372eb7` makes alarms local
   too). I agree and add: from an overwhelm view "everything stays on the
   phone" is also the simpler answer (no watch setting), but it is still the
   owner's call.
7. **I117 would be the fourth "what's next" view** (briefing, Coming up,
   "What did I miss?") - Fit says the same - and R2-EXP #4 does not mention
   that the phone already has an Inbox screen built as "one screen rather
   than three" digest (`jarvis-client/.../ui/screens/InboxScreen.kt:41-49`).
