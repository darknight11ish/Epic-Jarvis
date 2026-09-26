# Ease-of-use audit, lens: reviewing the past

Date: 2026-09-26. Read-only look at the repo at `/home/user/Epic-Jarvis`.
Question: how does the owner look back at what happened - past chats, what
Jarvis learned, past approvals, settings changes, what ran in the
background, undo, exports, and "what did Jarvis do while I was away"?

Method: read the source and the docs, and cite file:line for each claim.
I did **not** render any window and did not run either app, so what is
said about how things look comes from the code, not from screenshots.
Anything marked "not checked" was not checked.

---

## The answer in five lines

1. **Past chats: you can read them, but you cannot search them, continue
   them, copy them out, or reach them from the Jarvis bar.** Both apps have
   a read-only History list. It has 0 search, 0 export and 0 "carry on"
   buttons.
2. **Past approvals: there is nowhere to see them.** The PC sends a list of
   decided cards, but both apps throw it away on purpose. A card that timed
   out while you were away (3 minutes) leaves no trace in either app.
3. **Settings changes: there is no change log.** The PC writes an audit log
   file that records many of these, for 90 days, but no app reads it.
4. **What Jarvis learned is the best-covered part.** The desktop shows every
   fact with dates, greyed forgotten ones, "Erased on", and "what did Jarvis
   know on this date?". The phone shows less, on purpose.
5. **"While I was away" is spread over about 8 places with 5 different
   names**, and each keeps a different length of time (1 hour, 1 day, until
   a restart, 200 sessions but only 1 shown).

---

## What exists today, and where

| What you want to look back at | Desktop (PC) | Phone | Kept how long | Search? |
|---|---|---|---|---|
| Past chats | Brain -> History tab (`brain.html:61-66`, `:403-425`) | Brain -> scroll to "Chat history" -> Open History (`BrainScreen.kt:585-592`, `HistoryScreen.kt:510-519`) | Until deleted, or 30/90/365 days (`history-view.js:40-45`) | No (neither app, no route: `JARVIS-API.md:2740-2795`) |
| Facts Jarvis saved by itself | Brain -> Memory -> "Saved automatically", with date, where said, "said again N times" (`auto-learn.js:306-323`) | Brain -> "Saved automatically" (`AutoLearn.kt:396-424`) | Until forgotten | No |
| Every fact, forgotten ones too | Brain -> Memory -> "What Jarvis knows about you": greyed "no longer recalled", "replaced by #id", dates (`brain.js:2153-2172`) | Not shown - one-sided on purpose (`ARCHITECTURE.md:1119-1122`) | Forever (Forget keeps history) | No filter or search box on the list (`brain.html:348-358`); the only search is the graph's, under Advanced (`brain.js:5532`) |
| What Jarvis believed on a date | "What did you know on..." button, typed as YYYY-MM-DD in a prompt box (`brain.js:1755-1770`) | "What did I believe on this date?" (`BrainScreen.kt:634-641`) | - | - |
| Memory export | "Export everything" -> a JSON file you pick (`brain.js:1735-1753`, `brain.rs:538`) | None, on purpose (`ARCHITECTURE.md:1123`) | - | - |
| Past approvals and denials | **Nowhere.** Desktop reads only `pending` (`stream.rs:993`) | **Nowhere.** `history` is refused by name (`JarvisApi.kt:121`) | Not known (the gate is in the owner's `jarvis_gate.py`, not in this repo) | - |
| Cards that timed out while away | **Nowhere.** "What did I miss?" says so itself (`JARVIS-API.md:4148`) | Same | Cards wait 180 s (`JARVIS-API.md:309`) | - |
| Settings changes | **No change log** in either app | Same | Audit log: `~/.openjarvis/logs/jarvis-YYYY-MM-DD.jsonl`, 90 days (`jarvis-framework.toml:348-351`, `jarvis_framework.py:444-450`), read by no app | - |
| What went off (timers, alarms, reminders) | Brain -> Work -> Coming up -> "Just went off", **last hour only** (`brain.html:447-451`) | Coming up | 1 hour on screen | - |
| "What did I miss?" | Brain -> Work -> Morning briefing (`brain.html:476-486`) | Brain -> Morning briefing | Up to 1 day back, since your last message (`JARVIS-API.md:4126-4146`) | - |
| "Tell me when" matches | A notification, then the job row | Same | The alert is readable for 1 day (`JARVIS-API.md:4966`) | - |
| Focus sessions | The last report card only (`JARVIS-API.md:5166`) | Same | PC keeps the last 200 sessions in `focus_ledger.json` (`JARVIS-API.md:5241-5245`) - **no app lists them** | - |
| Deep questions | Brain -> Memory -> Deep questions | Brain -> Deep questions | **Until the backend restarts** (`JARVIS-API.md:1705-1709`) | - |
| Background jobs | Brain -> Work -> Long Fuse jobs | Inbox -> Running | Not checked (owner's `jarvis_jobs`) | - |
| Undo shelf | Brain -> Work -> Undo shelf (`brain.html:496-503`) | Inbox -> Undo shelf (`InboxScreen.kt:167-205`) | Not checked (owner's `jarvis_undo`, unverified: `ARCHITECTURE.md:1513-1520`) | - |
| The daily brief (digest) | Jarvis bar, "Mark the brief read" (`index.html:258-282`) | Inbox -> Today's brief | Not checked | - |
| "Findings" (what Jarvis noticed on its own) | **Not in the Brain**; only the HUD page reads it (`jarvis_hud.html:2151`) | Brain -> Findings (`BrainScreen.kt:643-651`) | Not checked | - |
| The ledger | Brain -> Advanced -> Trust -> Ledger: "chain status only ... never the payloads" (`brain.html:523-528`) | Brain -> "Audit chain" | Payloads 30 days (`jarvis-framework.toml:412-419`) | - |
| What changed in Jarvis itself | `CHANGELOG.md` in the repo (83 lines); in the app only as update "Release notes", and updates are not set up (`settings.html:250-256`, `:283-286`) | Not in the app | - | - |

---

## What works well

- **History is honest about where words came from.** Each turn that was
  not typed or said by you is labelled "pasted", "shared from another app",
  "from clipboard" (`history-view.js:69-78`), and a chat that read outside
  text says so (`history-view.js:84-86`). Both apps use the same words.
- **History is private by design.** Encrypted on the PC, and nothing is
  written in plain text if encryption fails (`JARVIS-API.md:2711-2716`).
  "Why is nothing being kept?" gets a plain answer (`history-view.js:243-246`).
- **Memory has real history.** Forgotten facts stay visible, greyed, with
  the date and what replaced them. Erased facts show "Erased on <date>"
  instead of words. "What did Jarvis know on this date?" works on both
  apps. "Said again N times" is on both apps.
- **"Used in this answer" and "Jarvis remembered N things"** show, at the
  moment it happens, which facts were used or saved (`ARCHITECTURE.md:1120`).
  That is the best "why did it say that?" tool in the project.
- **Delete is careful.** One conversation at a time, with a confirm, and a
  keep-for choice that asks before it deletes anything
  (`history-view.js:106-114`). Both apps word it the same way.
- **The phone FAQ answers "Are my chats kept anywhere?"** in plain words and
  says where to find them (`FaqScreen.kt:157-165`).

---

## What is hard, ranked by how much it hurts a newcomer

### 1. "What did Jarvis do while I was away?" has no single answer (hurts most)

Numbers: on the desktop there are **8 places** to check - the Jarvis bar's
brief, Brain -> Work's "What did I miss?", "Just went off", Long Fuse jobs,
the Undo shelf, Memory's "Saved automatically", History, and Windows
notifications. They use **5 names** for overlapping things: "the brief",
"Today's brief", "What did I miss?", "Just went off", "Findings". They keep
things for **5 different lengths of time**: 1 hour, 1 day, until restart,
30 days, until deleted.

"What did I miss?" is the closest thing. But it leaves out, by its own
description (`JARVIS-API.md:4140-4148`):
- cards that timed out while you were away,
- facts Jarvis saved automatically,
- "tell me when" matches: the scheduler skips the whole "tell me when" kind
  because it is `silent` ("A match has its own event and alert",
  `backend/jarvis_schedule.py:1322-1328`), so a match that happened while you
  were away is not in "What did I miss?" - only in a notification, if you
  saw it,
- finished background jobs and deep questions,
- focus sessions.

And it is buried: Brain -> Work -> scroll to Morning briefing. It is not in
the Jarvis bar, where you would look first. (Saying "what did I miss" to
Jarvis does work from either app, `JARVIS-API.md:4152-4155` - but a newcomer
does not know to say it.)

### 2. Past approvals are invisible

This is the biggest gap for trust. A newcomer's first "wait, what did I
just approve?" or "did that card I missed do anything?" has no answer on
screen.
- The PC's `/api/pending` answers with `pending` **and** `history`
  (`JARVIS-API.md:208`). The desktop reads only `pending` (`stream.rs:993`).
  The phone refuses a list named `history` by design (`JarvisApi.kt:113-121`)
  - rightly, so that decided cards can never show as waiting. But nothing
  then shows them anywhere else, as decided.
- A card times out after **180 seconds** (`JARVIS-API.md:309`). Raised while
  you are away, it just disappears. The spoken line "That card timed out,
  so nothing was done" is said only in a spoken turn (`JARVIS-API.md:495-505`).
- The Trust tab, where a newcomer would look, is hidden under "Advanced"
  (`brain.html:83-118`, `brain.js:228`) and shows "chain status only - entry
  count, the last verified point, the anchors. Never the payloads"
  (`brain.html:523-528`). That sentence has 4 jargon words for a beginner.
- What the `history` list carries is **not checked**: `jarvis_gate.py` is on
  the owner's PC only. ARCHITECTURE says prompt and detail are blanked on
  decision (`ARCHITECTURE.md:167-171`), so it may hold only the action name,
  the result and the time.

### 3. Past chats cannot be searched, continued or copied out

- **No search** in either app, and no route for it (`JARVIS-API.md:2740-2795`;
  a search of `history-view.js`, `HistoryScreen.kt` and `ChatLog.kt` for
  "search" finds nothing). With 30 rows a page and "Load older", finding
  "that recipe from last month" means opening conversations one by one.
  Titles are the first line cut to 80 characters (`JARVIS-API.md:2706-2707`),
  so many will look alike ("hey jarvis", "what's the weather").
- **No "carry on from here".** Opening a chat "only reads it"
  (`brain.html:414-420`). On the desktop, pressing Esc clears the Jarvis
  bar's conversation (`chat-history.js:36-37`) - the only way back is a
  read-only transcript. A newcomer who presses Esc by habit loses the thread.
- **No export or copy of a chat.** Memory has "Export everything"; chats do
  not. On the phone, the transcript's text is drawn with plain `Text`, and I
  found no `SelectionContainer` in `HistoryScreen.kt`, so it is probably not
  even selectable to copy (not tested on a device).
- **No delete-all** (on purpose, `JARVIS-API.md:2766-2768`). Clearing 100
  chats by hand is 100 deletes and 100 confirms, 200 clicks. The way out is
  "Delete conversations older than", which the note does point to
  (`brain.html:415-419`). This is a rule, not a bug; it just needs to be
  obvious.
- Note on the rules: CLAUDE.md says "Searching the owner's own past chat
  words waits" (`CLAUDE.md:329-331`). That line is about **Jarvis recalling**
  past chats into answers (ARCHITECTURE §5: "nothing in it is recalled into a
  chat", `ARCHITECTURE.md:841`). A search box that only **you** use, on your
  own screen, is a different thing - but it is close enough that it should
  be the owner's call, not assumed.

### 4. History is hard to find

- **Desktop: 4 clicks, and never from the Jarvis bar.** Tray icon -> "Open
  the Brain" (`tray.rs:253`) -> History tab -> a conversation. The Brain has
  no hotkey and no button in the Jarvis bar (a search of `index.html` and
  `main.js` finds no link to it except an error's fix button, `main.js:815`).
  If Windows hides the tray icon under the "^" arrow, add one more click.
- **Phone: History is item ~25 of one long Brain list.** Before it come up
  to 24 sections - web search, hardware, second card, big model, attention,
  compute and so on (`BrainScreen.kt:278-585`). Then "Open History" opens a
  separate screen.
- **The switches that decide what is kept live in the Brain, not Settings.**
  "Keep chat history on this PC" and "Learn automatically" are in the Brain
  (`brain.html:303-315`, `:409-411`). The desktop Settings window has 21
  sections and none is about chat history (`settings.html:51-1321`; the only
  hits for "history" are the clipboard and the Windows Hello line at
  `:355`). A newcomer looking for "privacy" or "history" in Settings will not
  find it.
- **First run does not mention it.** The desktop's 3 onboarding screens cover
  the tray, approvals and memory (`onboarding.html:131-176`) - nothing says
  chats are kept on the PC by default, or where to read them. The desktop FAQ
  has 11 questions and none about chats (`settings.html:1007-1150`); the
  phone's FAQ does have one (`FaqScreen.kt:157`).

### 5. Some history quietly is not there, and the screen does not say why

- **Cloud answers are not kept** - only the question (`JARVIS-API.md:2825-2827`).
  The PC marks such turns `answer_kept: false` (`JARVIS-API.md:2759-2761`),
  but **neither app reads that field** (a search for `answer_kept` /
  `answerKept` in both apps finds nothing). So a transcript shows a question
  with no reply and no explanation. It looks like a bug.
- **Deep question answers vanish on restart** (`JARVIS-API.md:1705-1709`), but
  the desktop says "the answer is kept on it for you to read here"
  (`brain.html:381-382`). A newcomer will reasonably expect to find it next
  week. Wording bug, S.
- **Temporary chats are never kept** (`ARCHITECTURE.md:863-865`) - correct,
  and the mode says so; just worth listing in the History note too.
- **Deleting a chat does not forget facts learned from it** - the desktop
  says so in the Memory tab (`brain.html:321`), but not in the History tab
  where you actually press Delete.

### 6. No record of settings changes

There is no "what changed and when" anywhere in either app. Some settings
remember only the outcome of their **last** card (e.g. voice settings'
`last.outcome`, `JARVIS-API.md:2099`; learning's `auto_last`,
`JARVIS-API.md:1061`). The PC's audit log (`jarvis_framework.py:406-460`,
one file a day, 90 days) records tool calls, routing and some settings
(e.g. `memory.pinned`, `memory.rerank_off`, `JARVIS-API.md:1217`, `:5508`),
but reading it means opening JSON-lines files in `~/.openjarvis/logs/` by
hand. For a beginner: "Why is Jarvis suddenly asking before every web
search? Did I turn that on?" has no on-screen answer.

### 7. Background history is kept but not shown

- **Focus sessions**: the PC keeps the last 200 (numbers only), both apps
  show only the latest report card. "Am I getting better?" needs a list.
- **"Just went off"** disappears after an hour.
- **"Tell me when" alerts** are readable for a day, then only the phone's
  notification shade has them.
- **"Findings"** are on the phone's Brain but not on the desktop's Brain
  (a search of `brain.js`, `main.js`, `widget.js` for `initiative` finds
  nothing; only the HUD page reads it, `jarvis_hud.html:2151`). A small
  parity gap, not listed in ARCHITECTURE §8.

### 8. The words on the Work and Trust tabs are for developers

Counted in the notes under those cards (`brain.html:488-528`): "capability
set", "frozen", "digest", "notch", "stored bytes", "before-images", "chain
status", "last verified point", "anchors", "payloads", "rush latch" - **11
jargon terms in 4 short notes**, plus the card name "Long Fuse jobs". The
Undo shelf's note tells you what it does *not* show before what it does.

---

## Concrete fixes

Sizes: S = an afternoon, M = a few days, L = a week or more.
All fit the five rules: read-only views, nothing leaves the PC, no bulk
approve, no new way to act.

| # | Fix | App | Size | Owner's call? |
|---|---|---|---|---|
| 1 | **"While you were away" in one place.** Grow "What did I miss?" to also list: cards that came up and how they ended (approved / denied / timed out), facts saved automatically (count, "see them"), "tell me when" matches, finished jobs and deep questions, and focus sessions. Put a "What did I miss?" button in the Jarvis bar and on phone Home, not only in Brain -> Work. Same builder, no model. | Both, backend first | M | No - it extends an existing feature |
| 2 | **"Recent decisions" list**: title, Approved / Denied / Timed out, when, from which app. Read-only, no buttons that decide anything, and never mixed into the pending list (keep `JarvisApi.kt:121`'s guard). First check what the gate's `history` rows actually carry on the owner's PC. Put it in the Brain on the PC and the Inbox on the phone. | Both | M | Yes, where it lives (it touches the approvals screens) |
| 3 | **Show why an answer is missing**: read `answer_kept: false` and write "The answer came from the cloud model, so it was not kept." under that turn. | Both | S | No |
| 4 | **Fix the deep-question wording**: "kept on this PC until Jarvis restarts" (`brain.html:381-382`). | Desktop | S | No |
| 5 | **A way to History from the Jarvis bar** (a "History" link beside "New conversation"), and move the phone's "Chat history" entry up near the top of Brain, or into Home's menu. | Both | S | No |
| 6 | **Search your own chats**: a PC route that decrypts on the PC and returns matching conversation ids and a short snippet; a search box above the History list. Used only by the owner, never by Jarvis's recall. | Both, backend first | M | **Yes** - near the CLAUDE.md line "searching the owner's own past chat words waits" |
| 7 | **"Carry on from here"** on a past conversation: loads its turns back into the bar (with their original provenance, same conversation id, so its "read outside text" mark stays). | Both | M | No, but check with the owner that it is wanted |
| 8 | **Save one conversation to a file** (desktop, Windows save dialog, the same shape as memory export). Phone left out for the same reason as memory export; write it in ARCHITECTURE §8. Make phone transcripts selectable (`SelectionContainer`). | Desktop (+ phone copy) | S-M | No |
| 9 | **"Recent changes to settings"**: a short list built from the audit log's settings events, in plain words ("Ask before every web search: turned on, Tue 14:05, on the phone"). PC-only read route; ids and names only, never content. | Both | M | Yes (new read of the audit log) |
| 10 | **Past focus sessions**: a small list or streak line from `focus_ledger.json` (numbers only, already stored). | Both | S-M | No |
| 11 | **Tell newcomers**: onboarding screen 3 gets one line "Your chats are kept on this PC, encrypted - read or turn this off in the Brain, History". Add the phone's "Are my chats kept anywhere?" to the desktop FAQ. Put a "Chat history and learning" pointer in desktop Settings that opens the Brain there. | Desktop | S | No |
| 12 | **Plain words on Work and Trust**: rewrite the four notes (`brain.html:488-528`) without the 11 jargon terms; rename "Long Fuse jobs" to "Background jobs"; say what the Undo shelf DOES first. | Desktop | S | No |
| 13 | **Say in History what deleting does not do**: repeat "Deleting a conversation does not forget facts learned from it - use Forget in Memory" in the History tab, next to Delete. | Both | S | No |
| 14 | **Show "Findings" in the desktop Brain**, or write down in ARCHITECTURE §8 why it is phone-only. | Desktop | S | No |
| 15 | **A search box on "What Jarvis knows about you"** (filter the list already loaded - no new route). | Desktop | S | No |

---

## Earlier audits: what is still open in this area

- PROFESSIONALISM #7 "No changelog" - **fixed in the repo** (`CHANGELOG.md`,
  0.2.0, 26 Sep). Still not visible inside either app except as update
  release notes, and updates are not set up (`settings.html:250-256`).
- CONTINUITY #1 ("Hide memory lists and chat history" described wrongly) -
  **fixed**: both apps now share one sentence (`security-settings.js:147-155`).
- FEASIBILITY: encrypted backup (I96) was "build now" (`FEASIBILITY-AUDIT-2026-09-26.md:71`)
  but is still an open owner question (`OWNER-QUESTIONS-2026-09-27.md:31-41`),
  and I found no backup code (a search of `backend/*.py` and `*.patch` for
  "backup" finds only unrelated hits). So today: no backup of memory or
  chats, and chat history has no export at all.
- FEASIBILITY warns against a *new* ledger/undo (`FEASIBILITY-AUDIT-2026-09-26.md:23`,
  `:100`). Fixes 2 and 9 above reuse the gate's existing `history` and the
  existing audit log rather than adding a new store - consistent with that.

---

## Numbers in one place

- Clicks to open one past chat: desktop **4** (from the tray), phone **3**
  plus a scroll past up to **24** sections.
- Places to check for "while I was away": desktop **8**, phone **7**; **5**
  different names.
- Time windows: 1 hour (Just went off), 180 seconds (a card), 1 day (What did
  I miss? and tell-me-when alerts), until restart (deep questions), 30 days
  (ledger payloads), 90 days (audit log), until deleted (chats, facts).
- Search boxes for past things: **0** for chats, **0** for the full fact
  list, **1** for the memory graph (under Advanced).
- Exports: **1** (memory, desktop, JSON). Chats: **0**. Backup: **0**.
- Places showing past approvals: **0**. Places showing settings changes: **0**.
- Focus sessions stored vs shown: **200** vs **1**.
- Jargon terms in the Work and Trust notes: **11**.
- Desktop Settings sections mentioning chat history: **0 of 21**.
  Desktop FAQ questions on chats: **0 of 11** (phone: 1).
