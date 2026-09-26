# Creativity audit, lens 1: making Jarvis more useful day to day (2026-09-25)

Read-only audit. Nothing in the repository was changed.

## The short answer

Jarvis already has most of the parts a useful day needs: one clock (the
scheduler), a morning briefing put together without the AI model, calendar and
email reading, an Obsidian vault it can search and write a daily note in, Home
Assistant, voice, and memory learned from the owner's own words. **The biggest
wins now come from connecting those parts, not from adding new outside
services.** Eight of the twelve ideas below need no new connection to anything
outside the PC. None of them needs the second graphics card. Two of them
benefit from it.

The best value for the effort, in order:

1. **Snooze, and named lists** ("add milk to the shopping list"). Small. Today
   a reminder cannot be snoozed, and the to-do list has no names.
2. **"What did I miss?"**: the briefing's builder, run for "since I last
   looked". Small.
3. **Focus sessions**, and making Quiet mode actually hold offers back.
   Small to medium. Quiet mode does not hold offers today (evidence below).
4. **An evening wrap-up written into the Obsidian daily note.** Small to
   medium.
5. **A nudge before calendar events, plus a "prep me" sheet.** Small to
   medium.
6. **"Tell me when..."**: an email from a named sender, a Home Assistant
   device changing state. Medium.
7. **Home names and scenes**, so "good night" is one card, not five.
   Small to medium.
8. **Obsidian tasks shown in Coming up and the briefing**, so there is one
   to-do list, not two. Small to medium.

### How far to trust this

- Every statement about what Jarvis does was checked against the file cited.
- Nothing here was run. The backend's own docs say most of these parts have
  not run on the owner's PC yet either (for example JARVIS-API §21.7 and §22.7).
- Things I did not check, and guesses about how the owner lives, are marked
  **(guess)**.
- I skipped ideas the three earlier audits already queued: weather, media
  keys, Wake-on-LAN, "what can Jarvis reach?", history search on its own,
  email drafts and sending, goals, ask-my-documents, and the spoken briefing
  on the first "Hey Jarvis". Where one of my ideas overlaps with one of
  those, I say so.

---

## 1. A day in the owner's life

What Jarvis could do at each point of the day, using mostly what it already
has. **(guess)**: the owner's routine is not written down anywhere, so these
are typical days.

| When | Friction today | Using what exists |
|---|---|---|
| **Waking up** | The alarm rings and cannot be snoozed. `jarvis_schedule` accepts `pause`, `resume`, `delete`, `done` and `add_time` (for timers). I searched the scheduler, the quick-command file and JARVIS-API for "snooze" and found nothing. | Snooze from the notification or by voice ("snooze 10 minutes"). |
| **Breakfast** | The briefing is ready, but only shows what is new since midnight. | The same builder answers "what did I miss?" after any gap: overnight, after lunch, after a day away. |
| **Starting work or study** | Offers and nudges can still turn up in Quiet mode (section 5 below). | "Focus for 45 minutes": a timer, Quiet mode for that stretch, and back to Active when it ends. |
| **Before a meeting or class** | The calendar is read in the morning and then nothing happens until the event. | A nudge 10 minutes before, and "prep me for my 3 o'clock": the notes and remembered facts that match the event. |
| **Waiting on something** (an email from the university, the washing machine) | The owner has to keep checking. | "Tell me when an email from Alex arrives." "Tell me when the washing machine is done" reads one Home Assistant device. |
| **Errands** | The to-do list has no names ("shopping", "for Mum"), so "add milk to the shopping list" is not understood without the model. The phone cannot show the list while the PC is off. | Named lists. A read-only copy on the phone for when the PC is off (owner's call, question 2). |
| **Evening** | Nothing records what got done. | A short "Today" block added to the Obsidian daily note: to-dos done, reminders that went off, tomorrow's first alarm. |
| **Bedtime** | "Turn off the kitchen, hall and bedroom lights" is three approval cards (`jarvis_agent.py`, the note above `CARDS_PER_TURN`), and the model has to guess each device's Home Assistant id. | "Good night" runs one Home Assistant scene, which is one card. Tomorrow's first alarm is read out, then standby. |
| **Any time** | "What did I say about the router last week?" means opening History and scrolling. | One Find box across chat history, memory, notes and to-dos. |

---

## 2. Brainstorm: 38 ideas, then the cut

**Kept (the 12, detailed in section 3):** snooze and named lists · "what did I
miss?" · "tell me when..." watches · the nudge before events and the prep
sheet · the evening wrap-up in Obsidian · Obsidian tasks in Coming up · home
names and scenes · focus sessions · yearly reminders from remembered facts
(birthdays) · one Find box · a voice note turned into a to-do, a reminder
and a note line · "Add to Google Calendar" by the owner's own tap.

**Folded into one of the 12:** "Good morning" and "good night" routines
(combo 3) · a weekly review on Sunday (combo 1) · "cancel that" / "delete the
last reminder" (with snooze) · habit check-ins with Done and Skip (a
repeating reminder plus snooze) · "Continue where I left off", which shows
the last conversation (with "what did I miss?") · "When I get home", using
Home Assistant's presence sensor (a "tell me when" source) · a phone
home-screen widget showing the next alarm and how many to-dos are open (with
named lists) · a daily "how was today?" journal prompt (an offer, with the
wrap-up) · a per-project dashboard from an Obsidian folder (Find plus
Obsidian tasks, filtered to one folder).

**Cut, and why:**

- **Watching a web page for changes.** It needs a new way to fetch pages
  from the internet. Web search is not page fetching, and browser control
  is off until the second card. Too big for the value.
- **Parcel tracking and bill reminders taken from emails.** An email would
  be creating reminders, and outside text must never make Jarvis act. Even
  as a suggestion card, the email decides what is suggested. Too risky.
- **A lecture or meeting recorder.** The voice pipeline takes clips of at
  most 30 seconds (`jarvis_speech.py:944`, `max_seconds`). Long recordings
  would need new chunking, and a lot of processor time. Large. Revisit with
  the queued "voice memos to Obsidian".
- **A "screen activity" recap.** It is the Recall pattern, which is rejected
  (ARCHITECTURE §11, screenpipe).
- **Drafting Home Assistant automation code for the owner to paste.** Useful
  for learning, but the chat can already do it. There is nothing to build.
- **An "explain this error simply" hotkey.** Pasting into chat already does
  it. A new hotkey adds little.
- **Planning the day into calendar gaps.** Jarvis cannot write to Google
  Calendar (the private link is read-only), and suggestions only would be
  weak on an 8B model. **(guess)**
- **Pomodoro counts in the daily note.** Part of focus sessions.
- **"What time is it" and "what can you do".** Already in the earlier
  audits' lists.
- **A "read later" inbox from phone shares.** Shared text is outside text,
  so every save would be a card. It works today with `#obs` plus that card.
- **Queueing questions on the phone while the PC is off.** A queued question
  answered hours later is confusing, and rule 4 means nothing that acts may
  be queued. Low value.
- **PC health ("is the disk full?").** Rarely wanted. **(guess)**
- **Weather, media keys, Wake-on-LAN, history search on its own, email
  sending.** Already queued or already asked by the earlier audits.

---

## 3. The best 12

Each block covers: what the owner gets · what it builds on · what is new ·
size · rules and cards · whether it needs the second card · what could go
wrong.

### 1. Snooze, "cancel that", and named lists. Size S.

- **Gets:** "Snooze 10 minutes" from the notification or by voice, and "add
  milk to the shopping list" / "what's on the shopping list?" without the
  model.
- **Builds on:** `POST /api/schedule/act` (JARVIS-API §21.2: pause, resume,
  delete, done, add_time), the quick grammar for to-dos
  (`jarvis_quick.py`, roughly lines 679-700, which only understands "todo"),
  the toast and phone notification for a job going off.
- **New:** a `snooze` verb that makes a new one-off copy of the job (a
  repeating job's rule is not touched). A `list` name on to-do items. Grammar
  for "snooze", "cancel that" and "add X to the <name> list". A notification
  button on the phone. A button on the Windows toast is **(unverified)**: I
  did not check whether the desktop's notification plugin supports buttons
  on Windows.
- **Rules:** a one-off needs no card, and snoozing only makes things
  quieter, like pause. A notification may carry Deny but never Approve
  (ARCHITECTURE §3, `notice`). Snooze is not an approval, so a snooze button
  is allowed. One job per tap, and no "snooze all". Both apps.
- **Second card:** no.
- **Could go wrong:** snoozing a repeating alarm must not move the whole
  series. A snooze button on a lock screen must not show the reminder's words
  (keep the kind's `lock_screen` text).

### 2. "What did I miss?" Size S.

- **Gets:** one answer after any gap. What went off while the owner was
  away, cards waiting, new emails (count and senders), and the briefing if
  it was not opened. Typed or spoken.
- **Builds on:** `jarvis_briefing.py`, which already puts the day together
  in code, with no model. The scheduler keeps jobs that went off for a day
  (`FIRED_KEEP`, `jarvis_schedule.py:128`). The approval count comes from
  `jarvis_gate.pending()`. The GitHub watchlist report (`/api/watch/report`)
  lives only on the owner's PC.
- **New:** a "last seen" time per app, a "since" window for the builder, and
  a quick-grammar line. **No second builder:** the briefing gains a "since"
  setting.
- **Rules:** it only reads. Email senders are outside text, so the answer
  marks the conversation as having read outside text, exactly as the
  briefing does. "Hide memory lists and chat history" and App lock hide the
  lines and keep the counts. Read aloud only under the private-answer rule.
  Both apps.
- **Second card:** no.
- **Could go wrong:** two apps with two "last seen" times give two different
  answers. Keep the time per app and say "since you last opened Jarvis on
  this phone".

### 3. "Tell me when..." Size M.

- **Gets:** "Tell me when an email from the university arrives." "Tell me
  when the washing machine is done." "Tell me when I get home" (using Home
  Assistant's presence sensor). The alert goes off once, then the watch ends.
- **Builds on:** `register_kind` on the one scheduler.
  `jarvis_email.senders()` reads the From line only, with `BODY.PEEK`, so
  nothing is marked read. `jarvis_home.plan_states()` reads one named
  entity. The `schedule_repeat` card.
- **New:**
  - A `tell_me_when` kind.
  - Checks more often than once an hour for this kind only, since
    `MIN_EVERY_HOURS = 1` today (`jarvis_schedule.py:140`). Say every 15
    minutes at the fastest.
  - An end date (for example 7 days), and matching against the owner's typed
    sender name or device state.
  - Later, a GitHub CI source: "tell me when my build finishes". The owner
    waits about 15 minutes per CI run (CLAUDE.md). This needs a GitHub key,
    which rule 3 now allows, and a new line in the egress table.
- **Rules:** checking repeatedly means ONE `schedule_repeat` card. It lists
  what is checked, how often, which server is asked, and when it stops.
  - The match only rings the doorbell. Outside text never makes Jarvis act:
    no action follows the match, ever.
  - The lock screen shows generic words ("Jarvis: something you were
    waiting for happened"). The app reads the rest by id.
  - The watch is set only from the owner's typed or spoken words.
  - If email reading is set to tier `ask`, the watch cannot run and says
    why, the same rule the briefing follows.
  - Both apps.
- **Second card:** no.
- **Could go wrong:**
  - Signing in to the mail server every 15 minutes may trip a provider's
    limits. **(guess)**
  - **Naming clash:** Brain → "Watch" is already the GitHub watchlist
    (`brain.js:196`). Call this "Tell me when", and consider folding the
    GitHub watchlist into it later (section 5).

### 4. A nudge before events, and "prep me". Size S-M.

- **Gets:** a notification N minutes before each calendar event. "Prep me
  for my 3 o'clock" lists the Obsidian notes whose words match the event,
  and the remembered facts about the people it names.
- **Builds on:**
  - `jarvis_calendar.py` keeps SUMMARY, times, LOCATION and UID
    (`jarvis_calendar.py:86`).
  - The briefing's calendar read, which runs without a card at tier `auto`.
  - The vault search: `jarvis_notes._search_vault` reads files on this PC
    and opens no socket.
  - The people layer: rebuilt `jarvis_memory.py` links facts to names.
  - One-off reminders.
- **New:** one setting, "Nudge me before events", which asks with ONE card
  because it repeats. Each morning's calendar read makes that day's nudges.
  The prep sheet is put together in code. A model summary only when the
  owner asks for one.
- **Rules:**
  - Calendar titles are outside text. The nudge's lock-screen words are
    generic, and showing a title marks the conversation as having read
    outside text.
  - Notes and memory reach the local model only (rule 1).
  - After a prep, any web search or note write in that conversation asks
    first, which the current rules already do.
  - Both apps.
- **Second card:** no. A summary of many notes is better with its longer
  memory.
- **Could go wrong:**
  - Events moved after the morning read keep their old nudge time. Re-read
    at midday, or say "as of 07:00".
  - Matching on title words can find the wrong notes. The sheet shows only
    file names and snippets, so a wrong match is visible.

### 5. Evening wrap-up in the Obsidian daily note. Size S-M.

- **Gets:** at a time the owner picks, a short block added to today's daily
  note: to-dos done today, reminders that went off, what is still open, and
  tomorrow's first alarm.
- **Builds on:** `append_obsidian_daily` (tier `auto` in the shipped toml,
  line 117). The scheduler keeps finished to-dos for a week (`DONE_KEEP`) and
  jobs that went off for a day. The briefing's builder. The daily-note path
  rules (ARCHITECTURE §10: formats that cannot be written out exactly are
  refused with a reason).
- **New:** a `wrapup` kind and its block format.
- **Rules:**
  - Setting it up is ONE `schedule_repeat` card.
  - To-do and reminder words are the owner's own, so the note write needs no
    card, under the current tier.
  - **Calendar titles are outside text.** Including them makes this "a note
    write after outside text", which asks (`NOTE_WRITES`,
    `jarvis_agent.py:1013`). So leave them out by default (question 1).
  - Both apps: a setting and a Coming up row.
- **Second card:** no.
- **Could go wrong:**
  - **If the vault syncs** (Obsidian Sync, OneDrive), reminder words leave
    the PC through the owner's sync. Jarvis sends nothing itself, but the
    card should say so. **(guess)**: I do not know whether the owner's vault
    syncs.
  - A health reminder ("take tablets") would be copied into the note. Offer
    "Leave reminders out" as an option.

### 6. Obsidian tasks in Coming up and the briefing. Size S-M.

- **Gets:** one to-do list instead of two. Open `- [ ]` tasks with a due date
  in the vault show in Coming up and in the briefing, under "From your
  notes".
- **Builds on:** the vault folder search (bounded, and never enters hidden
  folders), and the Coming up list in both apps.
- **New:** a read-only task scan. It would follow one due-date format at
  first. Which one the owner uses, for example the Tasks plugin's `📅
  2026-09-30` or Dataview's `[due:: ]`, is a **(guess)**. Tick-off stays in
  Obsidian; writing to the file would be a later step.
- **Rules:** it reads a folder on this PC and opens no socket. A chat answer
  that quotes the tasks counts as having read files (outside text).
  "Hide memory lists" hides them. Both apps.
- **Second card:** no.
- **Could go wrong:** a large vault makes the scan slow. Keep it bounded and
  cached. Duplicates appear if the same item is on both lists.

### 7. Home names and scenes. Size S-M.

- **Gets:** "turn on the kitchen light" and "good night" work without the
  model guessing ids. A scene is one card instead of one card per light.
- **Builds on:** `jarvis_home.plan_service()`, which calls one service on
  one entity. The model today has to invent ids like `light.kitchen`
  (`jarvis_agent.py`, `home_read` and `home_control` schemas). A Home
  Assistant scene is ONE entity (`scene.good_night`).
- **New:** a short list on the PC of name → entity id, at most 20, the same
  as `_MAX_ENTITIES`. Quick grammar for "turn on/off the <name>" and "run
  <scene>". Before the card, a read of the scene's own entity list, so the
  card can show it.
- **Rules:** tier `ask` is unchanged: one action, one card. A scene that
  contains a lock, an alarm or a cover is marked heavy, like
  `_HEAVY_DOMAINS`. No tier changes. The list is edited on the desktop,
  like the web-search keys, and the phone shows it.
- **Second card:** no.
- **Could go wrong:** the scene can change in Home Assistant between the
  card and the run. The card should say "as Home Assistant describes it
  now". This does not replace Home Assistant's own automations, which are
  the right place for timed home routines. A timed Jarvis action would need
  a card every time it fires.

### 8. Focus sessions. Size S-M.

- **Gets:** "Focus for 45 minutes" gives a timer, and Jarvis goes Quiet (no
  offers, no speaking first) until it ends. Alarms and reminders still ring.
- **Builds on:** the power switch's Quiet mode ("answers, but does not start
  things on its own", `jarvis_power_switch.py`), timers, the back-off.
- **New:**
  - A `focus` kind: Quiet at the start, and Active at the end only if focus
    set Quiet. That is the same rule the standby schedule uses.
  - **`jarvis_backoff.may_offer()` reads the power mode.** Today it does not
    (section 5).
  - Optionally, a line in the daily note: "Focused 45 min".
- **Rules:** going quieter is immediate and needs no card. A one-off focus
  needs no card; a repeating one ("every weekday 9-11") is one card. Both
  apps.
- **Second card:** no.
- **Could go wrong:** the owner switches to Active by hand halfway through.
  Their choice must win, as it does for the standby schedule.

### 9. Yearly reminders from remembered facts. Size S-M.

- **Gets:** "Sam's birthday is tomorrow", every year, offered once after the
  owner tells Jarvis the date.
- **Builds on:** birthdays are always-ask facts, so a stored birthday was
  approved by the owner (`jarvis_sensitive.py`, `jarvis_auto_learn.py:131`).
  The people layer. `jarvis_backoff` for the one offer. The
  `schedule_repeat` card.
- **New:** a yearly repeat rule. `check_rule` accepts only day, weekday,
  week and every-N-hours (`jarvis_schedule.py:396-438`). Also a reminder
  that points at a fact by its id.
- **Rules:**
  - The offer goes through `may_offer()`, and a "no" is heard for 1, 7, then
    30 days.
  - The card lists the next three dates.
  - **Forget and "Erase the words" must also remove the reminder.** If the
    reminder kept its own copy of the text in `schedule.db`, an erased fact
    would survive there. So it holds the fact id and reads the words live.
  - Both apps.
- **Second card:** no.
- **Could go wrong:** the erase gap described above, if it is built the easy
  way.

### 10. One Find box. Size M. Overlaps the earlier audits' "history search".

- **Gets:** "Find: router last week" returns matching chats, remembered
  facts, notes and to-dos in one list. Nothing is sent anywhere.
- **Builds on:** the encrypted chat history (`jarvis_chat_log.py`,
  `/api/history/conversation`), `memory_search`, the notes search,
  `jarvis_past.py`'s fixed parser for "last week" / "in June", and the to-do
  list.
- **New:** a `GET /api/find` route and a box in both apps. What is new
  beyond "history search" is **one box over four stores, with dates**.
- **Rules:** only the owner starts a search, and results never go into the
  model unless the owner opens them in a chat. It follows `keep_days`,
  deletions and temporary chats (never kept, so never found). Hidden by App
  lock and "Hide memory lists". Both apps.
- **Second card:** no.
- **Could go wrong:** decrypting a long history on every search could be
  slow. **(guess)**: fine for one person's history.

### 11. A voice note turned into a to-do, a reminder and a note line. Size S-M. Extends the queued "voice memos into Obsidian".

- **Gets:** "Note that the landlord is coming Thursday, and remind me
  Wednesday at 6 to tidy up" gives one daily-note line and one reminder.
- **Builds on:** the quick grammar for reminders and to-dos, `#obs`
  capture, and voice turns tagged `voice`.
- **New:** splitting "X, and remind me..." into its parts, and a single
  reply listing each thing that was done.
- **Rules:** the owner's own voice, so a reminder needs no card and the note
  write follows its tier. Under "Only trust the talk button", a "Hey Jarvis"
  turn cannot save facts without a card. A note line is not a fact, but
  **check** whether that setting should cover note writes too. Both apps.
- **Second card:** no.
- **Could go wrong:** a wrong split files the wrong thing. Show exactly what
  was filed, each part with its own Undo (delete one job, or show the note
  line).

### 12. "Add to Google Calendar" by the owner's own tap. Size S.

- **Gets:** "Put dentist Tuesday at 3 in my calendar" gives a button that
  opens a pre-filled event. The owner presses Save.
- **Builds on:** the reminder grammar's date parsing (`parse_when`).
- **New:**
  - On the phone, Android's standard "insert event" screen
    (`Intent.ACTION_INSERT` with `CalendarContract.Events`). It opens the
    phone's calendar app with the fields filled in and needs no permission.
    I am confident this exists; I did not check it in this repo.
  - On the desktop, Google Calendar's pre-filled "create event" link
    **(unverified format)**.
- **Rules:** no OAuth and no key. Jarvis cannot write to the calendar: the
  private link stays read-only. The event text reaches Google only when the
  owner taps, through their own browser or calendar app. **It is still a way
  out of the PC** on the desktop, so it needs a line in ARCHITECTURE §4 and
  the owner's OK. Both apps.
- **Second card:** no.
- **Could go wrong:** the queued "calendar events" item may be planning real
  calendar writes. Decide which approach it is before building either.

---

## 4. Combos: most new value for the least new code

1. **One builder, four times of day.** The briefing builder
   (`jarvis_briefing.py`) plus a "since" window gives "what did I miss?". An
   evening time and the `append_obsidian_daily` write give the wrap-up. A
   Sunday time with "next 7 days" gives a weekly review. Each is a kind on
   the one scheduler with the same card. Almost no new reading code.
2. **The scheduler plus the existing read-only reads = "tell me when" and
   event nudges.** `email.senders()`, `home.plan_states()` and the calendar
   read already exist, each gated. What is new is one kind, a faster check
   for that kind, and matching.
3. **Quick grammar + scheduler + home scenes + standby = "good night" and
   "good morning".**
   - "Good night" reads tomorrow's first alarm and first event, raises one
     scene card, and puts Jarvis on standby.
   - "Good morning" reads the briefing aloud under the private-answer rule.
   - Every part already exists except the scene names (idea 7).
4. **Timer + Quiet + back-off = focus.** Three existing parts, plus one fix
   to the back-off.
5. **Calendar + people layer + vault search = the prep sheet.** It is all
   local, and the model is optional.
6. **Voice + quick grammar + to-do + `#obs` = the voice-note splitter.** It
   extends the item already queued.
7. **Remembered facts + back-off + the yearly repeat = birthdays.** It uses
   memory Jarvis already has, offered once.

---

## 5. Things to stop or simplify (evidence from the repo)

1. **Quiet mode does not hold offers back.**
   - `jarvis_backoff.may_offer()` (`jarvis_backoff.py:205-224`) checks the
     silence period, recent chat, what is already waiting and the maximum
     number waiting. It never checks the power mode.
   - I searched `jarvis_skill_discovery.py` and `rebuilt/jarvis_sleep.py` and
     found no power-mode check in either.
   - The owner's own `jarvis_hud.py` might check it. I cannot see that file.
   - Quiet is documented as "does not start things on its own". Fix: one
     check in `may_offer`. Small.
2. **Two timetables for quiet time.**
   - The toml has `[power] schedule_enabled`, `quiet_start` and `quiet_end`
     (`rebuilt/jarvis-framework.toml:876-893`, off by default).
   - These are applied by `jarvis_power.in_quiet_hours()`, outside the one
     scheduler.
   - The standby schedule is a second timetable on the scheduler.
   - `schedule_mode` and `idle_mode` are marked "not read" in the file
     itself.
   - Suggest: fold quiet hours into the standby schedule as a "Quiet
     instead of Standby" choice, and delete the dead keys. That makes one
     place for "when is Jarvis quiet", as ARCHITECTURE §12 asks.
3. **Home control in practice.** The model must guess entity ids, and each
   light is its own card. The code itself says three lights make three
   cards (the comment above `CARDS_PER_TURN = 5` in `jarvis_agent.py`).
   Scenes and names (idea 7) fix this without weakening "one action, one
   card".
4. **"Weather and news: not available" every morning.** The line is
   `jarvis_briefing.OUTSIDE_LINE`. After the owner's weather decision,
   either fill it in or move it to the briefing's settings text, so the
   briefing does not start the day with what Jarvis cannot do. Small.
5. **Two "watch" ideas.** Brain → Watch (the GitHub watchlist, behind
   Advanced, `brain.js:196-200`) and a new "tell me when" would be two
   versions of the same thing. Build "tell me when" with the GitHub
   watchlist as one of its sources later, rather than a second tab.
6. **Two to-do lists** (Jarvis's and Obsidian's), **(guess)** about how the
   owner works. Idea 6 reads Obsidian's rather than asking the owner to
   copy tasks across.

---

## 6. Top 8, ranked by value for this owner against size

| # | Idea | Size | Where it fits the current queue |
|---|---|---|---|
| 1 | Snooze, "cancel that", named lists | S | Now: it finishes the timers item, which the owner put first. |
| 2 | "What did I miss?" | S | With it: the same builder as the briefing. |
| 3 | Focus sessions, plus the Quiet fix for offers | S-M | Next. The fix is small and worth doing on its own. |
| 4 | Evening wrap-up in the daily note | S-M | Together with the queued "voice memos into Obsidian" (same write path). |
| 5 | Event nudge and prep sheet | S-M | Before or with the queued "calendar events" item. |
| 6 | "Tell me when..." (email sender, a Home Assistant device) | M | After QR pairing, alongside email sending (both use the email module). |
| 7 | Home names and scenes | S-M | Any time. It makes "good night" (combo 3) possible. |
| 8 | Obsidian tasks in Coming up | S-M | After the wrap-up, once the owner's task format is known. |

**Next after these:** One Find box · yearly reminders (build it with Forget
and Erase covering the reminder) · the voice-note splitter (fold it into the
queued voice-memo item) · "Add to Google Calendar" (settle it together with
the calendar-events item).

Every one of these needs its own feature audit when it lands (CLAUDE.md):
bugs, both apps plus `tools/check_parity.py`, and fit with the rest of
Jarvis.

---

## 7. Two questions for the owner

**1. The evening note.** Jarvis can add a short "what got done today" block
to your Obsidian daily note each evening. Putting your calendar events in it
would mean an approval card every evening, because calendar text counts as
outside text.

- **Leave calendar events out, no card** (recommended)
- **Include them, with a card each evening**

**2. The shopping list when your PC is off.** For the list to work at the
shop while the PC is asleep, the phone would keep a locked, read-only copy.
You could see it but not tick things off until the PC is back.

- **Keep a read-only copy on the phone** (recommended)
- **PC only.** The list works only while the PC is on and reachable.
