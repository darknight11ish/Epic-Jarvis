# Field test — what is live now, and the simple steps only you can do

Written 2026-11-04 after the FINAL MAIN deploy. The live stack is **version 0.2.421 on all three
halves**: backend `resealed.commit 8a4a8e76f`, desktop 0.2.421, phone 0.2.3742 / 1000003742.
Everything below is a check only a person can do; nothing is a PASS until you've done it.

Read the "Expected" line first. If something differs, note the exact words you saw and tell me —
that is the useful part, not a success report.

## A. Desktop — about 5 minutes

1. **Settings → Updates.** Expected: it says both halves are on **0.2.421** (desktop and server).
2. **New chat window.** In chat, type: `open a new chat window`. Expected: a second chat window
   opens and both keep working. Close it afterwards.
3. **Open a named screen.** Type: `open settings`. Expected: the Settings screen opens from chat.
   Then try `open the brain screen`.
4. **Its own portrait.** Type: `what are you made of?` Expected: Jarvis quotes real counts about
   itself (places, settings, abilities, plugins) — not a guess. Then: `which of your switches are on
   right now?`
5. **The Coding preset.** Type: `what is the coding preset?` Expected: the 32,768-token pooled
   window, clearly labelled as ready-but-untested until the big model is loaded. Do **not** start
   it for this test unless you want the 30B model loaded.
6. **Undo receipt.** Change one harmless setting (e.g. persona or a toggle) in Settings, then look
   for the **Undo** row. Expected: it names what changed and offers undo for 24 hours. Undo it.
7. **Attention budget.** Brain → Now → Attention budget. Expected: it reads your current budget and
   the brief line; nothing is changed by looking.
8. **Personalize quiz.** Open "Personalize Jarvis". Expected: 25 questions in 7 sections; answer one
   question and skip another, then leave. (Don't finish it unless you want to.)

### Known-broken thing, do not expect it to work yet

- **"What would you clean safely on my PC?"** — the storage self-scan route is currently a **404 on
  the live build** (a real bug in today's batch; a fix lane is running). Skip this one; it is not
  your mistake.

## B. Phone (the Pixel 9 — the primary phone) — about 5 minutes

Connect the Pixel by USB and enable USB debugging first if you want me to collect evidence, but
these checks are by eye:

1. **The app connects.** Open the Jarvis app. Expected: it says it is connected, not
   "Reconnecting". (The quick-link widget showed "Reconnecting" six minutes after the update — if
   the app itself still says Reconnecting, that is a finding: tell me.)
2. **The face bar.** On the Home screen, the full-screen face bar should **not** take the whole
   screen any more; the typing box in the face bar says **"Ask Jarvis"** and fills its cell.
3. **Voice check on a locked phone.** Lock the phone, then say **"hey Jarvis"** near it. Expected:
   it asks for the owner voice check only when it should (i.e. it does not nag on every phrase).
   Then unlock and try a normal spoken question.
4. **A spoken screen read.** Say: `what's on my screen?` Expected: it answers about the PC screen
   when asked (the Live read), not a refusal.

## C. Voice + reminders + routines — about 10 minutes

1. **A scheduled task in your own words.** Say/type: `at 18:30 tell me to stretch my legs`.
   Expected: ONE card naming exactly what it will do when it fires. Approve it only if you want the
   reminder.
2. **A multi-part routine.** Create a throwaway reminder with two parts (say: "remind me tomorrow
   at 9 to X and at 9:05 to Y"). Expected: one row that holds both steps. Delete it afterwards.
3. **A repeating routine.** Create a throwaway daily routine (e.g. "every day at 8 say good
   morning"). Expected: it repeats on the next day — this one will only be provable tomorrow; tell
   me if today's occurrence does not appear.
4. **Learning.** Say one true fact about yourself in chat. Expected: it appears in the memory review
   queue (not silently saved).
5. **Cloud escalation (only if you want to use the paid Cloud preset).** Choose the Cloud preset,
   ask a hard question, and check the answer header says a cloud lane was used and that it raised
   its normal card first. In the current preset (general) no cloud lane is offered — that is
   expected, not a bug.

## D. Not testable tonight, and why

- **GitHub tools (#1128)** — that PR is not in this build yet; it lands in a later release.
- **Real-call recording** — being built right now; not on the phone yet.
- **The third graphics card** — not installed; the three-card plan stays marked "best effort, not
  tested" until it is.
- **Tool switching from the Tools page (every tool on/off)** — that PR is open, not in this build.
- **Tool dossiers / capability talk** — open PR, not in this build.

## E. What I already checked for you (no action needed)

- Backend restarted on FINAL MAIN, `/api/self/version` says `0.2.421` and `resealed.commit 8a4a8e76f`.
- Desktop 0.2.421 installed and running; VERSION file written (8 bytes, sha256 `8BED31C4…`).
- Phone APK 0.2.3742 installed (pairing survived: firstInstallTime unchanged).
- Live HUD routes: `/api/self`, `/api/work`, `/api/limits`, `/api/conversations`, `/api/setup`,
  `/api/manner`, `/api/memory/facts`, `/api/status` all answer 200; a live chat turn returned in
  4.2 s on the local model; both model lanes loaded with no VRAM spill.
- One genuine bug found so far: the storage self-scan 404 above (fix in progress). The two other
  "ABSENT" routes in the automated probe were GETs against POST-only routes — tooling noise, not
  product bugs.
