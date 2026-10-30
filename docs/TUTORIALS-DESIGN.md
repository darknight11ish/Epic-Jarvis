# Tutorials and FAQ — design

Status: **BUILT** (2026-10-05), with one part added 2026-10-30 that is text only.
Sections 1-8 below are implemented; the interactive-tutorials part after them is
its first slice, and the `try`/`used` part after that is design only, as its own
heading says. **The part dated 2026-10-30 at the very end is written but NOT yet
in `backend/jarvis_tutorials.py`** — read it as the text to carry into the
catalogue, not as words the app already says.

* `backend/jarvis_tutorials.py` — the catalogue (an intro plus a tutorial per
  major part), the 20-question FAQ, and the owner's progress in
  `tutorials.json`. `backend/test_tutorials.py` is 303 checks.
* `backend/tutorials.patch` — one hunk in `jarvis_hud.py`, after
  `retirement.patch`; `scripts/apply-patches.ps1` has its patch entry and its
  `$SHIPPED` entry; `docs/JARVIS-API.md` section 114 is the API page.
* Desktop: `jarvis-desktop/src-tauri/src/tutorials.rs` (three commands, with the
  generated ACL permission files and `brain-tutorials` in
  `permissions/surfaces.toml` plus `capabilities/brain.json`),
  `jarvis-desktop/src/tutorials.js` (the Brain section) and
  `jarvis-desktop/tests/tutorials.mjs` (17 checks).
* Phone: `net/Tutorials.kt`, `net/JarvisApi.kt`'s three calls,
  `JarvisRuntime`'s wrappers, `ui/screens/TutorialsPlate.kt`, the `MenuCatalog`
  and `MenuPlaces` entries, `BrainScreen.kt`'s item, and
  `test/.../TutorialsTest.kt`.
* `tools/check_parity.py` lists the three routes as ported, and exits 0.

**What is proven where, and what is not.** The backend, the patch stack and the
desktop's JS are proven here. The Rust is proven by `cargo check` (exit 0) and
the Kotlin by CI's own `.github/workflows/jarvis-client.yml` - this machine has
no Android SDK, so every Kotlin commit says that rather than implying otherwise.
The DOM drawing of the desktop panel is proven by CI's browser suites and by
the owner opening it; the phone screen by the same CI build.

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

**Desktop: a Brain section, not its own window** (changed 2026-10-05, after
reading how the PC-help window is built). The design first said a separate
`tutorials.html` window, in the shape of `brain.html`. Reading the code, that
would mean a new window registered in Rust, a tray or menu entry to open it, and
a first-run hook — while `jarvis-desktop/src/pc-help.js` shows the cheaper and
better-fitting pattern: a **Brain section** that is a plain ES module, reached
from the Hardware and models page, with its labels mirrored by the phone. It is
also where this design's own `where` lines already send the owner ("Brain →
Memory"). So:

* `jarvis-desktop/src/tutorials.js` — an ES module like `pc-help.js`: the two
  section lists, the step card with Next / Back / Skip / Quit, the resume
  offer, "Show this one again", and the FAQ (searchable, its own list).
  Labels exported, so the phone's own file can be checked against them word for
  word by a test, exactly as `backend/test_pc_help.py` checks `PC_HELP`.
* The bridge is a Rust command per route (`tutorials.rs`, registered in
  `lib.rs`'s `invoke_handler` beside `hardware::get_pc_help`), because that is
  how every other page reaches the backend.
* The intro is **offered once** from the Brain's own list (a line at the top:
  "New here? Start with What Jarvis is"), never a modal that blocks anything.
  The existing first-run `onboarding.html` is untouched: it is five screens
  about first setup and how to use it, and this is the reference the owner comes back to.

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

**Two walkthroughs written on 2026-10-30** — archive a chat, and attach a file —
are in the part at the end of this file. They extend tutorials 5 and 13, in the
catalogue's own step shape.

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

**Questions 21-31, for the features that landed on 2026-10-30, are in the part
at the end of this file** — the same voice, the same four groups, numbered on
from here so they can be appended to the catalogue without renumbering it.

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


---

# Interactive tutorials — design

Status: **DESIGN + FIRST SLICE** (2026-10-10). Sections 1-4 below are the
design; section 5 is what this change actually built, and what it did not.

**This part of the note reverses one decision in the part above it.** The
shipped design chose *"Step cards that explain and show... Not live
click-along walkthroughs"* (line 41). That is what was built, and it is what
the owner is now asking to move past: his words are *"make sure that there are
effective, interactive tutorials... specific to each platform"*. The step card
stays - it is the right frame - but a step gains the ability to point at the
real control it is talking about. Nothing above is deleted; the record of what
was decided and why still stands.

This note adds to, and does not replace, `docs/ARCHITECTURE.md` §5 (the rules)
and the tutorials API page in `docs/JARVIS-API.md` §114. The catalogue itself
lives in `backend/jarvis_tutorials.py`.

The owner's request, in his words: *"make sure that there are effective,
interactive tutorials that are interactive on both the android app and desktop
program, and that they are specific to each platform."*

## 1. What exists today, and why it is not what he asked for

There is already a lot, and it is already platform-split. What it is not is
interactive.

| Piece | Where | What it is |
|---|---|---|
| 36 tutorials (23 when this part was written) | `backend/jarvis_tutorials.py` | Data: `{id, version, section, title, why, minutes, steps[]}`, each step `{title, body, where}`, and since 2026-10-10 an optional `try` |
| Sections | same file, `SECTIONS = ("pc", "phone", "both")` | 16 `pc`, 8 `phone`, 12 `both` (11 / 6 / 6 when this part was written) |
| Desktop screen | `jarvis-desktop/src/tutorials.js` | Brain panel: Next / Back / Skip / Leave it here |
| Phone screen | `jarvis-client/.../ui/screens/TutorialsPlate.kt` | The same card, the same buttons |
| Delivery | `backend/tutorials.patch` (19 lines) + `jarvis_tutorials.py` via `_where.SHIPPED` | The patch only wires the module into `jarvis_hud.py` |
| Tests | `backend/test_tutorials.py` (13 cases), `jarvis-desktop/tests/tutorials.mjs`, `TutorialsTest.kt` (12), `tools/check_tutorial_places.py` | All of them check the *data* |

So: **platform-specific already; interactive not at all.** Every step is a
paragraph of prose plus a `where` line naming a screen. The note above says so
in as many words at its line 41 — *"Not live click-along walkthroughs"*. The
three suites named above prove the catalogue is well-formed, the progress
round-trips and the labels match word for word; until this change, not one of
them proved a tutorial ever met a real control.

## 2. What "interactive" means here

A tutorial step is **interactive** when all four are true:

1. It names **one real control in the running app** — not a screen, not a
   picture of a screen.
2. It says what to do in **one line**, in the second person.
3. The app notices when the owner has done it.
4. It moves on by itself, or says plainly why it cannot.

Anything short of that is a book with buttons, which is what ships today.

Two things it must never do, because they are this project's rules and not
style choices:

* **It never acts on Jarvis's behalf.** Pointing at a control is not pressing
  it. If a step could perform the action itself, it could approve, send or
  spend — rule 4 and the gate exist to stop exactly that. A tutorial that
  presses a button is a tutorial that can approve, and there will not be one.
* **It never invents a control.** If the owner has already done the thing, or
  the control is not on screen, the step says so and the owner can move on.
  A Next button that only works after a scavenger hunt is worse than prose.

**How a step declares this.** The catalogue grows one optional field on a step,
`point`, holding one target per app — because the whole of this request is that
the two apps teach different things:

```python
{"title": "Open the palette",
 "body": "Press Ctrl+K, then type a few letters of what you want.",
 "where": "Anywhere on the PC",
 "point": {"desktop": "palette", "phone": None}},   # PC-only step
```

* `desktop` names a control in the **declared registry** in `tutorials.js`.
  A registry, not a raw CSS selector, so the catalogue cannot name a `div` that
  happens to exist and the check has something real to look in.
* `phone` names a control in the **declared registry** in `Tutorials.kt`.
* A step with `"phone": None` is **a step the phone never shows**. That is the
  mechanism that stops a phone user being told to press a hotkey.

The registry is the point. It is the one place that says "these are the
controls a tutorial may point at, and here is how each app finds them", and it
is the thing a test can be wrong about.

## 3. What each platform teaches

This is the heart of the request, and the two lists share almost nothing.

**Desktop** — controls the phone does not have and never will:

| Teaches | The real control |
|---|---|
| The prompt field and the palette | `#prompt`, `#palette` |
| The approval card, and that the PC decides it | `#approval`, `#approval-approve` |
| The talk button and "Hey Jarvis" | `#mic`, `#voice-auto` |
| The HUD window and its talk button | `#talk` in `jarvis_hud.html` |
| The faces | the Faces window |
| Hotkeys: stop everything, talk-to-type, Live | Settings → Hotkeys |
| Settings and the second card's switches | `settings.html` |

**Phone** — controls the PC does not have:

| Teaches | The real control |
|---|---|
| Pairing: the QR, then the short typed code | the pairing screen |
| The talk button, tap-to-talk and stopping at a pause | Home |
| Approval cards, decided by tapping or swiping | the card on Home |
| Notifications, and urgent ones that keep ringing | Android's own shade |
| Live: the Quick Settings tile, the headset button | the tile |
| Which features are PC-only — and why | this is a *step*, not a control |

**The failure to design against, in one line each:**

* A phone step saying "press Ctrl+K" — there is no keyboard.
* A desktop step saying "tap the card" — there is no touchscreen.
* A phone step sending the owner to `Brain → What asks first` to *change*
  something — the phone cannot loosen a rule; that is a PC job
  (`docs/ARCHITECTURE.md` §5).
* A shared step pretending to be interactive on both — it can be interactive
  on neither.

## 4. What it costs

* **Content** — the expensive part, and it is writing, not code. Re-pointing
  the 23 existing tutorials at controls is roughly 60-80 steps reviewed one at
  a time, each needing a real control name in both registries. The `where`
  lines already exist and most of them name the right screen, so this is
  editing, not authoring from scratch.
* **Desktop observation** — cheap and contained. `tutorials.js` is an ES module
  in the **same document** as every control it points at: the Brain panel, the
  Jarvis bar (`index.html`) and the HUD (`jarvis_hud.html`) are separate
  windows with no iframes, so `document.querySelector` reaches the real thing.
  Pointing is `scrollIntoView` plus one CSS class; noticing is a listener on
  the named control. No Rust, no new Tauri command, no ACL work.
* **Desktop screenshots** — the pictures the older note deferred. **Largely
  unnecessary now.** A step that highlights the live control does not need a
  picture of last month's version of it, and a stale picture is the thing that
  makes a tutorial lie. Pictures stay for the things that are not on screen —
  the tray menu, Android's notification shade.
* **Phone observation** — **the real work.** `TutorialsPlate.kt` is inside the
  Compose tree, so "watch the real control" means the tutorial holds a
  `Modifier`/semantics key, or the screen observes `JarvisRuntime` state.
  That is a genuine change to the phone's UI, it cannot be driven from here
  (the attached phone belongs to another agent), and it is where the first
  slice deliberately stops.
* **A wrong registry is a silent lie** — the failure mode to test against. A
  `point` naming a control that no longer exists must fail the suite, not the
  owner. That is one new check per app, and both are cheap.

**Reused, not rebuilt:** the catalogue, the three routes, the progress records,
quit/resume, the version-bump re-offer, the label-parity test, the
`where`-line checker, and the Brain panel and plate that already draw a step
card. Nothing about interactivity needs a new screen on either app.

## 5. The first slice, and its honest size

What was built:

1. `point` on a step, parsed and validated by the backend module, and passed to
   both apps by `one()`.
2. A **declared registry of real controls** on each app —
   `CONTROL_POINTS` in `jarvis-desktop/src/tutorials.js`, and the same idea in
   `jarvis-client/.../net/Tutorials.kt`.
3. `Show me` on a step that has a `point`: the desktop highlights the real
   control and scrolls it into view. **Pointing only** — it never presses
   anything.
4. Tests that fail if a `point` names a control the app does not declare, if a
   step is `desktop`-pointed but reaches the phone, or if a PC-only step is
   shown on the phone.
5. The intro and the two platform tutorials re-pointed as the worked example.

What was **not** built, and why:

* **Watching for the owner to press the control, and advancing by itself.**
  This is the part that makes it truly interactive and it is the part that
  needs a decision: whether a tutorial may listen to every control it points
  at, and what happens when the owner does something else first. See §6.
* **The phone's pointing.** Cannot be driven or verified from here, and the
  attached phone is another agent's. The phone declares its registry and is
  checked against it; drawing the highlight is the next piece.

## 6. The questions only the owner can answer

1. **How long should one tutorial be?** Today each is 4-8 steps and about two
   minutes. Interactive steps take longer than reading steps, because the owner
   has to actually do the thing. Recommended: **keep 4-6 steps, and add a
   "just read it" option** for when he only wants the tour.
2. **When does it run?** Today the intro is *offered once* from the Brain list
   and nothing else ever pops up. Recommended: **keep that** — offer the
   platform tutorial once on first launch, never a modal, never twice.
3. **Can it be replayed?** Yes today, through "Show this one again", and that
   should not change.
4. **May a tutorial act on Jarvis's behalf, or only point?** Recommended:
   **only point, always**, for the reason in §2 — a tutorial that can press a
   button can approve. This is the one answer that changes the design rather
   than the content, so it is worth being explicit about.

## 7. What would make this fail

* A registry that drifts from the markup — fixed by the check in §5, which is
  the whole reason `point` names a registry entry and not a selector.
* Interactive steps that are interactive on one platform and prose on the
  other, which is the drift the owner is complaining about in the first place.
* A tutorial that highlights a control while the owner is mid-task. Pointing
  must be something the owner asks for, never something that happens to him.

---

# `try` and the `used` state — DESIGN ONLY, NOT BUILT

Status: **designed, deliberately not built** (2026-10-10). The owner's call on
docs/EDUCATION-TAB-DESIGN.md §13 question 2 was *"design it now, build it
later"*, and this section is that design. **Nothing here is implemented**: no
`try` is observed, no `used` record can be written, and neither app draws a
`used` state. What has been written is the catalogue side of it — the lessons
that could carry a `try` carry one, in the shape below — so that building the
mechanism is a change to two or three files rather than a rewrite of the
curriculum.

The problem it answers, in one line: **"Done" today means the owner pressed
Next to the end of a lesson, not that he can do the thing it taught.**

## 1. `try` — one real action, in the catalogue

A step may gain one optional field, in the same shape `point` already has:

```python
{"title": "Models",
 "body": "...",
 "where": "Brain → Model → Models",
 "point": {"desktop": None, "phone": None},
 "try": {"desktop": "switch-model", "phone": None}},
```

`try` names a **registry key**, never a sentence and never a selector — exactly
like `point`, and for exactly the same reason: a key can be checked against
what the app really declares, and a sentence cannot. Each app declares its own
map, beside `CONTROL_POINTS`:

* desktop — `TRY_ACTIONS` in `jarvis-desktop/src/tutorials.js`;
* phone — `TRY_ACTIONS` in `jarvis-client/.../net/Tutorials.kt`.

**A `try` the app cannot observe must be `None`, and `None` means "this step
never shows a thing to do here".** That is the mechanism `point`'s per-app
`null` already uses, and it is the same failure it prevents: the phone must
never be told to do something it cannot see, because then it would show a
control that never lights up.

**No step is required to have one.** A lesson with no `try` simply cannot reach
`used`; it can only reach `done`. That is deliberate — the state stays honest
instead of universal.

## 2. `used` — one new state, and nothing else changes

`tutorials.json` keeps `state`, `step`, `version` and `at` exactly as they are.
One value is added to `STATES`:

| state | what it means |
|---|---|
| *(no record)* | never opened |
| `in_progress` | opened, part-way through |
| `done` | read to the end |
| `skipped` | met and declined |
| **`used`** | **read to the end AND the `try` action really happened** |

`used` is written by the app that observed the action, through the same
`POST /api/tutorials/progress` route — no new route, so `tools/check_parity.py`
gains nothing and the phone keeps the two routes it already has.

**When a lesson's words change, `used` goes back to `done`, not to `used`.**
`one()` already re-offers a tutorial whose recorded `version` is lower than the
catalogue's; the same comparison clears the stronger half, because the words the
owner demonstrated it against are not the words on screen any more.

## 3. The one number, and the words it is allowed to use

The line both apps now draw from the backend's `counts`
(`jarvis_tutorials.py`'s `read()`) is:

> **You have met 9 of the 23 lessons here. 14 to go.**

It says **met**, and "met" is every lesson with a record of any kind —
`in_progress`, `done`, `skipped` and `used` alike. Skipped is *met and
declined*, which is information and not a failure mark. The line never says
*learned*, and it never says what he can **do**.

When `used` is built, its count is added **beside** that sentence, not folded
into it:

> You have met 12 of the 23 lessons here. 11 to go — and you have used what 4 of
> them taught.

## 4. What is refused, and why

The refusals are docs/EDUCATION-TAB-DESIGN.md §5.4's, and they hold here:

| not built | why |
|---|---|
| a completion percentage | it rewards skipping — the fastest way to raise a percentage is Next through the shortest lessons |
| streaks, "don't lose your streak" | pressure with a deadline, for one person learning his own tool |
| badges for clicking | a badge for opening a page teaches nothing and lies about what he can do |
| a nudge — "you haven't finished Memory" | the intro is offered once and nothing else ever pops up; that stands |
| a leaderboard, or anything that leaves the PC | there is nobody to share with, and rule 1 keeps this on his own machine |
| timing how long a lesson takes | it turns a lesson into a task and measures the wrong thing |
| locking a lesson behind another | §7's order is a suggestion; gating his own documentation is a strange way to say so |

## 5. How it should be built, in the order that keeps it small

1. **The field and the registries.** `try` in the catalogue (already written on
   the lessons that can carry one), `TRY_ACTIONS` in each app, and the same
   shape check `point` has — `backend/test_tutorials.py` for the shape,
   `jarvis-desktop/tests/tutorials.mjs` and `TutorialsTest.kt` against each
   app's own registry. **This step alone is honest and changes no state.**
2. **Observation, desktop first.** One `TRY_ACTIONS` entry per action, wired to
   the place the app already knows the thing happened — the model switch
   returning, a card being decided, a backup finishing. Nothing new listens to
   anything; the app is already doing the thing it would report.
3. **The state.** `used` in `STATES`, written by the app that observed the
   action, and the second half of the sentence above.
4. **The phone last, and only for what it can see.** A `try` the phone cannot
   observe stays `None`, so this step may legitimately be "nothing to do".

**The thing that must not happen first is the state.** A `used` written by
anything other than an observed action is the same lie as a `done` earned by
pressing Next, one level up.

---

# What the 2026-10-30 features add — FAQ answers and two walkthroughs

Status: **WRITTEN HERE, NOT YET IN THE CATALOGUE** (2026-10-30). The questions
and lessons the two apps show come from `backend/jarvis_tutorials.py`, and that
module still holds the 2026-10-05 content — 20 questions, and a catalogue that
has grown from the 23-tutorial outline in §5 to 36 entries (both counted by
importing the module on 2026-10-30). What follows is the text to carry into it:
the same voice, the same four groups, numbered on from question 20, and two
walkthroughs that extend tutorials that already exist. **This is not a claim
that the app already says it.** §6 says of itself "This is the content; the
module will hold it verbatim", and this part is written in that spirit — the
catalogue is the thing that would have to change.

Every answer was checked against `origin/main` at `21add9d53` on 2026-10-30;
§5 below says where. Where something is not measured — the animation on a real
phone, the app builder driven from a button — the answer says so in the sentence
that makes the claim, not in a footnote.

## 1. Eleven more questions for the FAQ

The numbers are the order the flat list takes; the group headings say where each
question reads best.

**Everyday use — after question 10**

21. **Where is my chat history now?**
    On the PC, press **History** on the HUD's main strip — the clock button — or
    open **Brain → History**. On the phone, tap **History** on Home's status
    line, the row no screen size, menu or setting hides; **Brain → History** and
    the More menu's earlier-chats row still work too. Both apps read the same
    list from the PC, so a chat seen on one is on the other. While App lock or
    "Hide memory lists and chat history" is on, the list is hidden until you
    prove it is you: the PC asks for Windows Hello and the phone asks for your
    fingerprint or PIN. *Where to change it:* PC — Settings → Security →
    "Windows Hello for memory lists and chat history"; phone — Settings →
    Fingerprint for private lists.

22. **What does Archive do, and how do I get a chat back?**
    Archive puts one chat away without deleting it, so the everyday list stays
    short. It is reversible: open the **Archived** list and choose
    **Unarchive**, and the chat goes back where it was. It asks nothing first
    and raises no approval card, because it stores no words and sends nothing;
    **Delete** is the one that still asks you to confirm. An archived chat is
    still kept and still searchable — it is simply not in the main list. *Where
    to change it:* the row's menu in History, then Archive or Unarchive; the
    **Archived** list is a chip beside "Your chats" in the HUD's sidebar (the
    Brain's History tab has one **Archived** button that reads "Back to your
    chats" to return) and on the phone it is the **Archived** chip beside the
    Show chips.

23. **How do I add an event to Jarvis's own calendar?**
    On the phone: **Brain → Jarvis Calendar → Open the calendar**, pick the day,
    then **Add**. Type what it is, the date and the times, and press **Save**.
    Tap an event to change it; **Delete** asks "Yes, delete it" first. On the
    PC: the HUD's **Calendar** card, then **+ Add event**; **Open calendar**
    gives the Month, Week and Day views. If the card is not on your main screen,
    press **Edit HUD** and add it. The events live on your PC only and are never
    synced anywhere. *Where to change it:* **Settings → Jarvis Calendar** is the
    one ON/OFF switch in both apps; OFF hides every surface and keeps every
    event. Two honest limits: nothing rings yet — the remind-me box is saved,
    but nothing rings — and asking in chat turns the calendar on or off but does
    not add an event.

24. **How do I put a widget on my home screen?**
    Say what it should show — a heading, numbers, short lists, a bar, and up to
    four one-tap buttons from a fixed menu ("my next 3 reminders, my to-do count
    and a 10-minute timer button") — and Jarvis makes a **preview**. Nothing is
    added until you press **Add**; **Discard** throws the preview away. You can
    ask for an arrangement too ("put my reminders at the top", "make the count
    big"). Then, on the phone, open **Brain → Widgets** and find **On your home
    screen**: choose which saved widget each **Jarvis widget** slot shows, then
    press **Put it on my home screen**. The phone asks your launcher to place
    it; a launcher may show its own confirm or refuse, and Jarvis says which of
    the three things happened instead of claiming it worked. If your home
    screen will not add a widget by itself, touch and hold it, choose
    **Widgets**, then **Jarvis**, then "Jarvis widget 1", "2" or "3".

25. **How do I style my notifications?**
    Say what you want in chat — "make my Jarvis notifications look like a warm
    orange pulse" — and Jarvis answers with a **preview**: a colour from a short
    list (ice, azure, indigo, ember — the warm orange — rose, mono), a figure
    (spark, ring, dot, star, arrow or none), a motion (still, pulse, flip or
    spinner) and a speed (slow, normal, fast). Nothing is applied until you
    press **Add**; **Discard** throws the preview away. You can also make one in
    **Settings → Notifications from Jarvis → Notification styles**. It changes
    only how your own notifications look: it adds no button, no permission and
    no text of its own, and an approval card still offers Deny only. While App
    lock or "Hide memory lists and chat history" is on — or the phone has no
    secure lock screen — the plain notification is used instead.

26. **How do I get a feature onto the main screen?**
    Press **Edit HUD** on the HUD. The editor shows what is on the main screen
    and everything that could be on it; add the one you want, drag it where you
    want it, and press **Done**. Any built-in feature card can be added this
    way, including one a later release adds — a saved layout gets it back at its
    default place instead of hiding it. The approvals queue, Stop everything,
    app lock and the stale-link warning are deliberately not in the list, so no
    layout can hide them. *Where:* the **Edit HUD** button on the HUD. One
    honest limit: this is the PC's editor — the phone's equivalent screen is the
    next slice and is not built yet.

**Privacy and rules — after question 4**

27. **Does my PDF go to the cloud?**
    No. A file attached in a chat is read on your PC by the same reader that
    reads a folder Jarvis may look in: it is never uploaded, never written to a
    temporary file, and never kept with the chat. Only the words it read are
    used, for that one turn, up to 12,000 characters — a longer file says how
    much was left out. PDF, Word, Excel, PowerPoint, text, Markdown and CSV are
    the kinds it reads, one file per turn, up to 2.5 MB; a picture goes in with
    the picture button, and a bigger file belongs in a folder Jarvis may look
    in. The reader used to lose the first 16 KB of every PDF and Office file;
    that was fixed on 2026-10-30, so the whole file is read now.

28. **What does Jarvis send when I ask about parking?**
    It sends a latitude, a longitude and a radius to the public parking data
    (Seattle's own block-by-block prices inside Seattle, OpenStreetMap
    everywhere), and the place name you said to the map lookup that turns it
    into a point. It does not send your chat, your calendar, a memory fact or a
    note. The answer is a cost estimate, not a booking: parking is priced minute
    by minute across the sign's own rates, a place that publishes no price is
    named rather than guessed, and every answer says what it cannot know. The PC
    gets the full breakdown; the phone gets two options with a map link. Say
    "find cheap parking near Pike Place Market from 4:15 pm to 9 pm", or "how
    much is parking near ... from 4 pm to 9 pm". A latitude and longitude you
    give instead skips the map lookup, so no words are sent at all.

29. **Why does my widget hide its words?**
    A widget draws only what Jarvis already shows you — your reminders, timers,
    to-dos, "now playing", a few counts and a free-space bar — and some of those
    are your own words. With "Hide memory lists and chat history" or App lock
    on, the widget keeps its shape and replaces those words with "Hidden - open
    Jarvis to see it." Nothing is missing; it waits until you prove it is you.
    The counts that carry no words (to-dos left, unread mail, disk space) stay
    visible. *Where to change it:* the same setting named in question 21.

**Setup and upkeep — after question 20**

30. **Why is the window 16,384 and not bigger?**
    16,384 tokens — a token is a small piece of text, roughly three quarters of
    a word — is how much of the conversation the local model can hold at once,
    and it is what your PC is set to. It was measured: at 16,384 the model read
    a 15,409-token prompt whole, while 4,096 silently lost the beginning of a
    5,019-token one. 32,768 and 65,536 were measured too, and both work, but
    they are slower: about 33.5 and 27.4 tokens a second against 41.9, a cold
    first token takes most of a minute at 64K, and in the memory conditions
    measured both sizes spread the model over both cards. So 16,384 stays. A
    fresh install that does not set `OLLAMA_CONTEXT_LENGTH=16384` still gets
    4,096. *Where:* the numbers, the check and the undo are in
    `docs/MEASURED-2026-10-30-CONTEXT.md`.

31. **How do I build an app and put it on my phone?**
    Three steps, all on the PC: write a fixed, minimal Android project into one
    app task (no card — the files land in that task's own copy and nothing runs
    them); build it with Gradle; install it on the paired phone over its cable.
    The last two are each meant to raise one approval card that names the exact
    command and folder, and nothing is ever auto-approved — a card is decided
    with Windows Hello on the PC or the screen lock on the phone, and a denial
    never becomes a standing rule. The app it makes declares no permission at
    all — not even internet — and is a debug build, never the Play Store. It
    needs the Android SDK (Google's tools that turn a project into an app) and a
    JDK (the Java kit Gradle needs) on the PC. Three honest limits: **there is
    no button in either app and no chat sentence that starts this yet** — the
    three steps are the PC's own addresses in `docs/JARVIS-API.md` §166; **at
    `21add9d53` the two cards cannot be raised through the installed plugin at
    all** — the build and install addresses answer "503 TypeError" before a card
    exists, and PR #996 is the fix, so treat build-and-install as blocked rather
    than working until it lands; and Jarvis has no uninstall, so what it
    installs stays until you remove it.

## 2. Two walkthroughs

Both extend a tutorial that already exists, and both are driven on screens that
exist today. They are written in the catalogue's own shape: each numbered step
is a step card's `title` and `body`, and its *Where* line is the card's `where`.

### 2.1 Put a chat away, and get it back

*Extends tutorial 5, "Records, history and what is kept". Section: both. Two
minutes.*

1. **Open History where you are.** On the PC, press **History** on the HUD's
   main strip. On the phone, tap **History** on Home's status line.
   *Where:* PC — the HUD's main strip; phone — Home's status line. The Brain's
   History entry opens the same list on both.

2. **Open the chat's menu.** On the PC, press the three-dot **More** button at
   the end of the row. On the phone, press the **⋮** at the end of the row (its
   name is "Chat actions").
   *Where:* the row itself, in History. The Brain's History tab offers the same
   actions from its own row menu.

3. **Choose Archive.** Nothing is deleted, nothing asks "are you sure?", and no
   approval card appears. The chat leaves the list you were in. If it was the
   chat the HUD was showing, the HUD starts a new conversation rather than
   leaving you in a hidden one.
   *Where:* the row's menu.

4. **Look at the archived list.** On the PC, press the **Archived** chip beside
   **Your chats** at the top of the sidebar; in the Brain's History tab the
   control is the **Archived** button beside the search box. On the phone, tap
   the **Archived** chip beside the **Show** chips.
   *Where:* the two chips above the list.

5. **Bring it back.** In the archived list the same menu now reads
   **Unarchive**. Choose it, and the chat returns to the everyday list exactly
   where it was — archiving does not move its "last used" time, so it cannot
   jump to the top.
   *Where:* the archived row's menu.

6. **If the list is hidden, prove it is you.** While "Hide memory lists and
   chat history" or App lock is on, History says it is hidden: the phone shows
   "Hidden. Tap Show and confirm it is you." and the PC shows how many
   conversations are hidden until Windows Hello confirms it is you. Archive and
   Unarchive are refused until then, so nothing can be changed blind.
   *Where:* the History list itself; **Show** on the phone, Windows Hello on the
   PC.

**What it does not do.** Archive is not delete: the words stay in the encrypted
history on the PC, a search still finds the chat, and a backup still carries it
until it ages out. Delete keeps its own confirm, word for word. On the PC an
archived chat says "This chat is archived. Unarchive it to continue it." — take
it out of the archive first if you want to carry on with it. Nothing leaves the
PC, and no card is raised by any of the six steps.

### 2.2 Attach a file and ask about it

*Extends tutorial 13, "Documents, files and search". Section: both. Two
minutes.*

1. **Attach the file before you send.** On the PC, press **Attach a file** under
   the chat box — or drag a file onto the window, or paste one from the
   clipboard. On the phone, open **More** and choose **Attach a file**.
   *Where:* PC — under the composer; phone — the More menu. The phone's row says
   exactly what is allowed: "PDF, Word, Excel, PowerPoint, text, Markdown or
   CSV, up to 2.5 MB. Read on your PC."

2. **Check the chip.** The file's name, its size and **Read on your PC.** appear
   under the box, with a way to remove it before sending. If it is the wrong
   kind or too big, the same line says so in words and nothing is attached.
   *Where:* under the box, on both apps.

3. **Ask your question and send.** The file rides with that one message. Ask
   what you want to know about it — "what does this say about the deposit?" —
   and send.
   *Where:* the chat box.

4. **Answer the card if one appears.** If reading files is set to "Ask me
   first", one approval card appears before a byte is read. Its detail holds the
   file's name and size and never a word of it; a no reads nothing.
   *Where:* the approval card, on either app.

5. **Read the answer, and the amount it left out.** The PC reads up to 12,000
   characters of the file, and the answer says when it showed only part of a
   longer one. The file's words are treated as information, never as
   instructions, and a card raised after the answer says it was proposed after
   Jarvis read the file you attached.
   *Where:* the answer itself.

6. **Attach it again for a second question.** The chip is gone after sending.
   The file is not kept with the chat and is not added to any folder list, so a
   follow-up about the same file needs it attached again. What is kept is your
   question and the answer, as any other turn is.
   *Where:* the same Attach a file control.

**What it does not do.** One file per turn, 2.5 MB at most; a bigger file
belongs in a folder Jarvis may look in. A picture goes in with the picture
button, not this one. The file is never uploaded, never written to a temporary
file, and never inside a backup. Before the 2026-10-30 fix the first 16 KB of
every PDF and Office file was lost in transit — a Windows pipe said it could
rewind and did not — so a PDF could come back with its opening pages missing or
a Word file could fail outright; the reader now copies the pipe into memory
first, still without writing it to disk, and reads the whole file.

## 3. Why there is no app-builder walkthrough

The app builder is the one new feature this week that cannot be written as a
walkthrough without inventing a control, and §2 of the interactive-tutorial
design above forbids exactly that: "It never invents a control."

What exists today is real: `backend/jarvis_android_builder.py` writes the fixed
project, and its two commands were measured on the owner's PC on 2026-10-30 (one
real build of exactly this template, 53.6 s, `BUILD SUCCESSFUL`; the changelog
fragment names the numbers). What does not exist is a way in from either app, or
from chat: a search of `origin/main` for `android/template` finds the module and
its test and nothing else, and `docs/JARVIS-API.md` §166 says plainly "Neither
has a screen for this". The two cards are meant to be the approval step, but at
`21add9d53` the installed wrapper cannot raise them (see question 31); its field
test is the open PR #996. So question 31 answers how it works and says what is
missing, and a step card waits for the button — the same rule the 2026-10-10
part sets out: a step that points at a control that is not there is worse than
prose.

## 4. What was proven, and what was not, on 2026-10-30

A test that passed is not a run on the owner's own machines, and the two are
kept apart here the way the top of this file keeps them apart. **BLOCKED and
NOT-TESTABLE are never passes.**

| Feature | Proven | Not proven — the honest row |
|---|---|---|
| History door, archive and Archived list (PC) | The page was driven in Playwright across all six HUD shells, and the archive route has its own backend tests | The installed WebView2 window and the live Python route end to end were not driven (the change's own note) |
| History door, archive (phone) | The Android app compiles in CI and its JVM tests pass | That change makes no claim about a run on a phone |
| Jarvis Calendar store and routes | 88 backend checks: add/change/delete, the caps, OFF keeping every event, the DST wall clock, recurrence, no bulk form | A real calendar read in a rebuilt desktop, and any run on a phone, are the owner's field checks |
| Calendar card and sheet (PC) | 33 browser-free page checks and the Rust tests | The real WebView2 window — "the geometry of the sheet in the real window is the owner's eye rather than a test" (§168.7) |
| Parking | 140 offline checks, every socket made to fail, and the phone's short answer with its map link | "The real services answer" is NOT-TESTABLE here: no test and no CI makes a live call, so it is the owner's field check |
| Attachments | The reader on a real PDF and a real `.docx` bigger than 16 KB, through both reading paths; the file never written, never in a history row and never in a backup | Not proven on a phone: no APK from that change has been installed (its own note) |
| Widgets and their arrangements | The four arrangements proven as rules by both apps' tests against the shared fixture; the three slots held equal to the manifest | No widget has been seen drawn on a real launcher or an emulator yet |
| "Put it on my home screen" | Every sentence and all three receivers pinned by JVM tests | The pin itself was not driven on a phone: NOT-TESTABLE until the field test |
| Notification styles | 160 backend checks and the JVM decision tests (locked means the plain notification; each motion's frames) | The animation on a screen — there is no phone or emulator at this desk |
| Edit HUD (PC) | 25 page checks: add, remove, reorder, and the folded-away fix | The phone's equivalent editor is not built at all (the next slice) |
| App builder | One real build of exactly this template on the owner's PC, 53.6 s, `BUILD SUCCESSFUL` | The two cards cannot be raised through the installed plugin at `21add9d53` (503 TypeError, fixed by the open PR #996), and no test runs Gradle or adb |
| Context 16,384 | Measured on the owner's PC: the deployed value, the 4K/8K/16K ladder, 32K/64K, and what 4K did to a long prompt | Sustained multi-turn use — and the phone and voice lanes — were not measured at any of those sizes |

## 5. Where each answer was checked

Read in this worktree, whose `HEAD` is `origin/main` at `21add9d53`. A
`path:line` is a place in that tree. §4's rows come from these same files, and
from the `changelog.d/` fragment each change shipped with.

| What this part says | Where it was checked |
|---|---|
| History is on the HUD's main strip and on Home's status line | `jarvis-desktop/src/jarvis_hud.html:3384-3401` (the door, titled "History: every conversation kept on this PC"); `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt:1918-1933`; `jarvis-client/app/src/main/java/com/jarvis/client/net/ChatLog.kt:946-947` ("History", "Chat history, kept on your PC") |
| Archive is one chat, reversible, with no card and no confirm | `docs/JARVIS-API.md:4489-4540` (§18.3); `jarvis-desktop/src/history-actions.js:48-49, 64-81`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt:500-530` |
| Archived is a visible list on both apps | `jarvis-desktop/src/hud-history.js:638-651` ("Your chats" / "Archived"); `jarvis-desktop/src/brain.js:6815-6840`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt:136, 766` |
| Hidden until Show / Windows Hello | `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SecurityScreen.kt:330-341` (the exact words); `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt:581-583, 721`; `jarvis-desktop/src/brain.js:6011-6014`; `docs/JARVIS-API.md:4384-4391` (the route withholds every row, archived included) |
| Where the hide-lists switch lives | `jarvis-desktop/src/settings.html:1662, 1693-1697`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SecurityScreen.kt:201-214` |
| The calendar is Jarvis's own, kept on the PC, with four routes | `docs/JARVIS-API.md:27509-27708` (§164), especially 27532-27555 and 27640-27648 |
| The calendar's one switch, and OFF keeps every event | `jarvis-desktop/src/calendar-settings.js:56-59, 101`; `docs/JARVIS-API.md:27545-27555, 27650-27653, 28354-28364` |
| The phone's calendar screen and its words | `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt:1109-1129`; `jarvis-client/app/src/main/java/com/jarvis/client/net/Calendar.kt:71, 84-94, 127-144`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/CalendarPlate.kt:400, 682, 828, 916` |
| The HUD's calendar card, Add event and three views | `jarvis-desktop/src/jarvis_hud.html:3566-3576` (card and its two buttons), `3779-3797` (tabs), `3869` (the form's submit); `docs/JARVIS-API.md:28259-28287` |
| No reminder rings yet | `docs/JARVIS-API.md:27587` ("stored only - nothing rings in v1") and 27681 |
| Chat turns the calendar on or off but cannot add an event | `backend/jarvis_quick.py:4862-4869` (the switch is in `CHANGE_BY_ASKING`); `docs/JARVIS-API.md:27683-27684` ("no natural-language add through the model") |
| Widgets: preview then Add, three home-screen slots, four arrangements, "Put it on my home screen" | `docs/JARVIS-API.md:16115-16215` (§86); `jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisWidgets.kt:47-73, 93, 128-132, 143` |
| A widget's private words hide under the setting | `docs/JARVIS-API.md:16163-16177`; `jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisWidgets.kt:67` |
| Notification styles: preview/Add, closed menu, look only, plain when locked | `docs/JARVIS-API.md:28139-28240` (§167); `jarvis-client/app/src/main/java/com/jarvis/client/net/NotificationStyle.kt:50-74, 238-249`; `jarvis-client/app/src/main/java/com/jarvis/client/data/Security.kt:243-244` (`notificationsLocked`) |
| Edit HUD adds any feature card, and the phone has no equivalent editor | `jarvis-desktop/src/hud-edit.js:1427, 1669` (the button), `1819` (the panel); `docs/JARVIS-API.md:28340-28353`; `changelog.d/2026-10-29-hud-edit-main-screen-cards.md` ("This slice is the desktop half... The phone's equivalent edit screen is the next slice"); `docs/HUD-MAIN-SCREEN-CARDS-2026-10-29.md` (status line) |
| Parking: public data, minute by minute, phone short answer with a map link | `docs/JARVIS-API.md:27710-27947` (§165), especially 27733-27737 and 27859-27860 |
| Which parking sentences the PC recognises | `backend/jarvis_quick.py:6837-6868` (the leads and the range shapes), 6990-7015. Measured in this checkout: "find cheap parking near ... from 4:15 pm to 9 pm" and "how much is parking near ... from 4 to 9 pm" both match; "what does parking cost near ..." does **not** match and goes to the model |
| Attachments: 2.5 MB, one per turn, seven kinds, read on the PC, nothing written | `docs/JARVIS-API.md:27307-27506` (§163); `jarvis-client/app/src/main/java/com/jarvis/client/net/AttachFile.kt:50, 103, 137`; `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/MoreMenuWords.kt:82, 89`; `jarvis-desktop/src/jarvis_hud.html:3430-3435, 6771` |
| The 16 KB loss and its fix | `backend/jarvis_documents.py:1697-1701` (the comment and the copy); `changelog.d/2026-10-30-attached-files-pipe-rewind.md` |
| The app builder's two cards, no permissions, debug only | `docs/JARVIS-API.md:27949-28138` (§166); `backend/jarvis_android_builder.py:1-115`; the measured build is in `changelog.d/2026-10-30-android-app-builder.md` |
| The two cards cannot be raised through the installed plugin at this commit | `backend/jarvis_android_builder.py:1283-1344` (`install()` calls `handle_post` with no gate, tier or spawn) and `1237-1270` (`handle_post` needs those for the two card routes, so `_raise` raises `TypeError`, caught at 1275-1276 as 503); the field test is the open PR #996's own report |
| No button or chat sentence starts the app builder | `git grep android/template` finds `backend/jarvis_android_builder.py` and `backend/test_android_builder.py` only; `docs/JARVIS-API.md:28115-28118` ("Neither has a screen for this") |
| The deployed window is 16,384; 32K/64K were measured and are slower | `docs/MEASURED-2026-10-30-CONTEXT.md:102-108` (the table), 167-214 (the follow-up and the decision); `docs/MODEL-TOPOLOGY.md:54-58` |
| The catalogue is still the 2026-10-05 content | `backend/jarvis_tutorials.py` (`FAQ` has 20 entries; `CATALOGUE` has 36); `docs/JARVIS-API.md:20152-20182` (§114); `docs/HANDOFF-2026-10-05-tutorials-and-ci.md:24` |
| The proven / not-proven rows in §4 | `changelog.d/2026-10-30-history-one-click-door.md`, `2026-10-30-phone-history-archive-and-one-tap.md`, `2026-10-29-jarvis-calendar.md`, `2026-10-30-calendar-hud-settings-and-fail-closed.md`, `2026-10-30-parking-cost-estimator.md`, `2026-10-29-attached-files-phone.md`, `2026-10-30-widget-layouts.md`, `2026-10-30-widget-put-on-home-screen.md`, `2026-10-30-notification-styles.md`, `2026-10-29-hud-edit-main-screen-cards.md`, `2026-10-30-android-app-builder.md`, `2026-10-30-context-16k-measured.md`; and the `docs/JARVIS-API.md` sections named above |

