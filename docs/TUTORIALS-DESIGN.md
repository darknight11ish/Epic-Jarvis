# Tutorials and FAQ — design

Status: **BUILT** (2026-10-05). Everything below is implemented; this section at
the top says where each piece lives, so the design and the code can be read
together.

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
  The existing first-run `onboarding.html` is untouched: it is three screens
  about first setup, and this is the reference the owner comes back to.

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
| 23 tutorials | `backend/jarvis_tutorials.py` | Data: `{id, version, section, title, why, minutes, steps[]}`, each step `{title, body, where}` |
| Sections | same file, `SECTIONS = ("pc", "phone", "both")` | 11 `pc`, 6 `phone`, 6 `both` |
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
