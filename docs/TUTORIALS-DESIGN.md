# Tutorials and FAQ — design

Status: **for the owner's read** (2026-10-05). Nothing here is built yet.

The owner's request, in their words: a skippable comprehensive intro tutorial,
tutorials for each of the major parts of Jarvis, on the desktop program and in
the Android app, with the progress of tutorial completion recorded and the
ability to quit a specific tutorial and resume it later. The same tutorials on
both apps, but a different section for the desktop program and a different
section for the Android app. Plus an FAQ section with well-thought-out
questions and answers.

Two decisions the owner made when asked:

* **Step cards that explain and show** — each step is a sentence or two plus a
  picture of the real screen, with Next / Back / Skip / Quit. Not live
  click-along walkthroughs.
* **Progress is recorded on the PC** and shared by both apps, like the rest of
  the owner's settings.

## 1. What exists today

* `jarvis-desktop/src/onboarding.html` — three first-run screens, opened once.
  `jarvis-desktop/src-tauri/src/commands.rs` records completion as a **versioned
  marker** (`ONBOARDING_VERSION`, stored under `onboarding_version`) precisely so
  that a corrected onboarding can be shown again. That is the pattern this
  design extends, one level down: per tutorial instead of one whole window.
* `backend/jarvis_pc_help.py` — the "what can this PC do" answers Jarvis gives
  when asked. Nothing to do with a tutorial, but it is where some of the FAQ's
  facts already live, and the two must not disagree.
* **Nothing on the phone.** `jarvis-client` has no onboarding, no welcome and no
  help screen (zero matches for `onboard`/`Welcome`/`FirstRun`).
* The gaps are already written down in `docs/ease-audit-2026-09-27/` ("First run
  does not mention it", "Setup: about 24 steps, 13 PowerShell lines").

## 2. The content model

One catalogue, in the backend, written by hand in a shipped module
(`backend/jarvis_tutorials.py`) — not in the apps, so the two can never drift
and `tools/check_parity.py` has something to check.

```json
{
  "id": "memory",                       // stable; progress is keyed by this
  "version": 1,                         // bumped when the steps change
  "section": "both",                    // "pc" | "phone" | "both"
  "title": "What Jarvis remembers",
  "why": "One line saying what this is for.",
  "minutes": 2,
  "steps": [
    {"title": "Facts, not transcripts",
     "body": "Two or three plain sentences.",
     "shows": "brain-memory.png",       // a picture of the real screen
     "where": "Brain → Memory"}         // where to find it, in words
  ]
}
```

`where` matters more than the picture: it is what the owner can act on when the
screen has moved on since the picture was taken. Pictures live with the apps
(`jarvis-desktop/src/tutorials/`, `jarvis-client/.../res/drawable/`) and the
catalogue names them; a missing picture is a broken check in the suites, not a
blank card at run time.

**Sections.** `section` splits the catalogue into the two the owner asked for:

* **Desktop** — everything that happens on the PC: the HUD and the Jarvis bar,
  approval cards, Brain, focus sessions, Projects, the wiki and notes,
  documents, screens and "Look at this", Jarvis Live, the animals, backups, the
  stop-everything hotkey.
* **Android** — the phone: pairing by QR, talking on the phone, Live, the
  approval card and swiping, notifications, history, Temporary, what stays on
  the PC.
* **Both** — the intro ("what Jarvis is, and the five rules"), memory and
  learning, what asks first, voice and faces, crisis help, privacy, the FAQ.

A tutorial with `section: "both"` appears in each app's own list, so the owner
sees "the same tutorials" as they asked, while each app's section is its own.

## 3. Progress

One record per tutorial, held by the PC in the shipped module's own state file
(`OPENJARVIS_CONFIG_DIR/tutorials.json`), and served over the API so the phone
reads and writes the same record.

```json
{"memory": {"state": "in_progress", "step": 3, "version": 1, "at": 1790000000.0}}
```

* `state`: `in_progress` | `done` | `skipped`. No record at all means not
  started, which is the honest default — a tutorial nobody opened is not
  "skipped".
* `step`: where to resume. Quitting writes it; opening a tutorial with a record
  offers **Resume** or **Start again**.
* `version`: the catalogue's version when it was completed. A tutorial whose
  steps changed (higher `version`) is offered again rather than being counted
  done on words the owner never saw — the same reason `commands.rs` versioned
  the old onboarding.
* `skipped` is reversible: "Show this one again" clears the record.

Routes (documented in `docs/JARVIS-API.md` like every other route):

| Route | What it does |
|---|---|
| `GET /api/tutorials` | the catalogue, each with its progress and whether it is due |
| `GET /api/tutorials/progress` | just the records |
| `POST /api/tutorials/progress` | `{id, state, step}` — no card: this is the owner marking their own reading, changes nothing else |
| `GET /api/faq` | the questions and answers, with `where` for anything the owner can also do |

`POST` deliberately asks for no approval card: it edits the owner's own reading
progress, cannot act on anything, and a card per "Next" would be absurd. That
is worth one line in the API doc, because it is an exception to the usual rule.

## 4. The screens

**Desktop.** A new window, `tutorials.html`, in the same shape as `brain.html`
and `onboarding.html`: the left side lists the two sections and the tutorials in
them, each row showing done / in progress / not started; the right side is the
step card with Next / Back / Skip / Quit and a "step 3 of 8" line. Opening the
window with `?tutorial=memory&step=3` resumes; closing it at any point writes
the step. A "Show this one again" button per finished tutorial. The FAQ is a
third part of the same window, searchable, with the questions in the owner's
own words rather than the code's.

**Android.** A Tutorials screen reachable from the Brain list (and offered once,
on first run, in place of the desktop's onboarding), with the same two sections,
the same step cards and the same Next / Back / Skip / Quit. Progress goes
through the API, so finishing "Memory" on the phone ticks it on the PC. Offline,
the screen says so plainly rather than pretending to save.

**Skippable, everywhere.** The intro can be dismissed from the first card; every
tutorial can be left mid-way; nothing blocks the app. First run *offers* the
intro once and never nags again.

## 5. The tutorials

The intro, then one per major part. Each is 4–8 steps and two minutes.

| # | Section | Tutorial |
|---|---|---|
| 1 | both | **What Jarvis is** — the intro: what it runs on, where your words go, the five rules |
| 2 | both | **Talking to it** — the talk button, "Hey Jarvis", Live, what a voice check does |
| 3 | both | **What asks first** — approval cards, the tiers, how to make something stricter |
| 4 | both | **Memory and learning** — what is learned, what waits, Forget and Erase the words |
| 5 | both | **Records and history** — chat history, encryption, the read-only approval list, the audit log |
| 6 | both | **When something is wrong** — errors, "Jarvis isn't connected", the stop-everything hotkey, crisis help |
| 7 | pc | **The desktop at a glance** — HUD, the Jarvis bar, the tray, the approval widget |
| 8 | pc | **Brain** — the settings, the "What asks first" page, your memory lists |
| 9 | pc | **Focus sessions** — starting one, what it watches (and what it never stores) |
| 10 | pc | **Timers, reminders and the schedule** — including what needs no card |
| 11 | pc | **Projects** — projects, goals, benchmarks, running tests |
| 12 | pc | **Notes and the wiki** — Obsidian, Logseq, Joplin, the "Jarvis Wiki" folder |
| 13 | pc | **Documents, files and search** — asking about PDFs and Word files, the import |
| 14 | pc | **Screens and pictures** — "Look at this", "Watch with me", what is kept |
| 15 | pc | **Home, calendar and email** — what Jarvis may read, and what always asks |
| 16 | pc | **The faces** — picking an animal, voices, what the expressions mean |
| 17 | pc | **Backups and recovery** — the locked backup, the recovery code, what a lost code means |
| 18 | phone | **Pairing your phone** — QR, the typed code, the card on the PC |
| 19 | phone | **Talking on the phone** — tap to talk, hold to talk, "stopping at a pause" |
| 20 | phone | **Approval cards on the phone** — swiping, the fingerprint, Timeline |
| 21 | phone | **Notifications and alerts** — what rings, what waits, the watch setting |
| 22 | phone | **What stays on the PC** — screenshots, voice prints, nothing on the phone does speech-to-text |
| 23 | phone | **Live on the phone** — the tile, the headset button, ending a session |

Plus **the FAQ** as its own section in both apps (right-hand side of the same
window on the PC; its own list on the phone).

## 6. The FAQ

Written from the app's real behaviour, in the owner's own words, with a "where
to change it" line wherever there is one. This is the content; the module will
hold it verbatim.

**Privacy and rules**

1. **Does Jarvis send my things anywhere?** Email, files, credentials and saved
   memory are only ever read by the model on this PC. Web search, the chatbot
   driver and online weather are the named exceptions, each asks first, and web
   search can be your own SearXNG on this PC.
2. **Will it open a tunnel so I can reach it from anywhere?** No. The phone
   reaches the PC over Tailscale or NordVPN Meshnet, both device-to-device.
   A public address is refused with a message saying why.
3. **Where do my API keys go?** Only to the one service each key belongs to.
   They are never logged and never written in plain text.
4. **Can it act without asking?** Only where you have said so ("What asks
   first"). Risky approvals need Windows Hello on the PC or your screen lock on
   the phone, and it stops acting when the event stream is stale.

**Everyday use**

5. **How do I start talking to it?** The talk button, "Hey Jarvis", or the
   phone's tile. The same setting can make "Hey Jarvis" stricter than the
   button.
6. **Why did it keep an answer on screen instead of reading it out?** It used a
   sensitive fact, or a reading tool (email, files, notes, memory), or your
   hands-free setting is strict. A voice setting lets it read those aloud, and
   turning that on asks first.
7. **What does it remember about me?** Facts learned from your own words, plus
   the chat history you have not turned off. Health, money, passwords and other
   people's private details wait for your yes.
8. **How do I make it forget something?** "Forget" hides a fact and keeps its
   history; "Erase the words" wipes the text for good and keeps only the dates;
   "Forget a time frame" lists everything from a period for you to untick, with
   ten minutes of Undo.
9. **Does deleting a chat delete what it learned?** No. Facts learned earlier
   stay until you Forget or Erase them — the delete dialog says so, and backups
   keep a copy until they age out.
10. **What happens if I lose my backup recovery code?** The backup is useless,
    and nobody can open it — including Jarvis. That is the point of the code.

**When something is wrong**

11. **It says "Jarvis isn't connected".** The PC's backend is not answering —
    usually the app is closed, asleep, or the model is loading. The tray icon
    says the same thing.
12. **How do I stop it mid-action?** The stop-everything hotkey, the phone's
    Stop, or ending a Live session. Nothing is approved by voice.
13. **The model is slow or asleep.** Simple things like timers and reminders are
    answered without the model, so they keep working.
14. **What if I say something about self-harm?** It answers with the crisis
    helplines (988 and 911 in the United States), in a plain voice, and that
    turn is never learned from, never counted and not kept in the thread.
15. **A picture it was sent could not be read.** It says so on screen and does
    not send the picture on blindly; reading the words in a picture needs
    Windows' own text recognition.

**Setup and upkeep**

16. **How do I update Jarvis?** Pull the repository and run
    `scripts/apply-patches.ps1`, then restart. The patcher leaves your
    `jarvis-framework.toml` alone.
17. **Do I need the second graphics card?** No. Picture understanding and the
    long-context lane wait for it; everything else runs on the card you have.
18. **How do I see what it has been doing?** History (read-only, with
    Continued chats marked), the approval list, and the audit log on the PC.
19. **Why does an option say it will ask for Windows Hello?** Anything that
    loosens a rule asks once, on the PC, with Windows Hello — that is the
    guardrail, not a fault.
20. **How do I get a tutorial back?** Tutorials → "Show this one again". A
    tutorial whose steps changed is offered again by itself.

## 7. Build order

1. **Backend** — `backend/jarvis_tutorials.py` (catalogue, progress, routes),
   its patch, `_where.SHIPPED` entry, `scripts/apply-patches.ps1` entry, and
   `backend/test_tutorials.py` (the catalogue is well-formed; every `shows`
   picture exists in both apps; progress round-trips; a version bump re-offers;
   skip is reversible; no card is raised). Plus `docs/JARVIS-API.md` and
   `tools/check_parity.py`.
2. **Desktop** — `tutorials.html` + `tutorials.js` in the shape of
   `onboarding.html`; the window registered in `commands.rs`; first-run offer;
   pictures under `jarvis-desktop/src/tutorials/`.
3. **Android** — the Tutorials screen and the FAQ screen, reachable from the
   Brain list; the same catalogue and progress through the API; the same
   pictures under `res/drawable/`.
4. **Tests** — the desktop's own window test (`jarvis-desktop/tests/*.mjs`), the
   phone's `TutorialsTest`, and one suite that reads the catalogue and proves
   both apps can render every step's `where` and `shows`.

## 8. The owner's calls

Answered 2026-10-05:

* **Thin slice first.** Build the whole system end to end — backend, PC window,
  phone screen, progress, quit and resume, the FAQ — with the intro plus four or
  five tutorials, all real and tested. The remaining tutorials are then content,
  not code. The full list in section 5 stays as the target.
* **Words first, pictures as they come.** Every step says *where* the thing is in
  words ("Brain → Memory"); `shows` is added as screenshots are taken, and the
  suite treats a name in the catalogue with no file as a failure only once that
  tutorial is marked as having pictures.

Still open, and cheap to change later:

* The tutorial list above is 23 tutorials. That is a lot to write well; the thin
  slice proves the machinery on six of them.
* The FAQ answers above are written from how the app behaves today; anything
  that reads wrong is worth correcting before it is shipped as the app's own
  words.
