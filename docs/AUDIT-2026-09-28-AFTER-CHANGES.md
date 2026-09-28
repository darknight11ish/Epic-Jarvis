# The audits after the 2026-09-28 changes

Twelve audits, run together on 2026-09-28 (13:30-16:00 UTC) over **everything
the Jarvis sessions built since 2026-09-27**, as if it were all merged:
`main` plus the five branches still waiting to be merged. The detailed
reports, one per audit, are in [`docs/audit-2026-09-28/`](audit-2026-09-28/).

**The answer first:** nothing breaks one of the five rules today. The work
is in good shape feature by feature, but **the five branches clash with each
other**, a few owner decisions are not in the code yet, and one privacy
filter on the phone lets some one-time codes through. None of the five
branches has a pull request yet, so nothing below has reached `main` or
your devices.

How each finding was checked is marked in the detailed reports: **checked in
code** (read in the file), **seen in the browser** (the desktop windows
driven for real, against a pretend backend), or **needs a real try on
device** (only your PC or phone can show it). No audit used the real AI
model.

## What was audited

| Branch | Session | Commits not on `main` | What it adds |
|---|---|---|---|
| `claude/jarvis-ai-assistant-research-ff37vy` | research | 136 | chatbot compare, Jarvis Live, Projects, money limit, many fixes |
| `claude/jarvis-audit-competitors-vyqpt1` | competitor audit | 68 | about 15 features: Lockdown, Watches, talk-to-type, Today, widgets you describe, quick-settings tiles, history import, ... |
| `claude/jarvis-continuation-03kls1` | continuation | 21 | Goals, the plan card (off), "Try the cloud model", 3rd graphics card, reading phone notifications |
| `claude/jarvis-github-repos-b56v1f` | GitHub repos | 19 | memory milestones 7, 12, 13 |
| `claude/jarvis-3d-animal-mascot-8dr0tb` | mascot | 17 | the monkey, sun/moon/weather scenes, calmer movement, mouths |

Also on `main` since the last audit: the three animal faces (PR #20) and the
"rules stay first" fix (PR #21).

## The most important findings

### 1. The five branches clash (merge audit, [05](audit-2026-09-28/05-merge.md))

Each branch merges into `main` on its own, but not with each other. Putting
all five together needed about 75 files resolved by hand. Three clashes would have
broken Jarvis if merged carelessly:

- **Every "Jarvis Live" message would have been sent as a "yes" to the cloud
  model.** Two branches changed the desktop's `send()` in different ways.
- **Five backend patches all aim at the same spot** in `jarvis_hud.py`, so
  in any order after the first, the later ones do not apply (`projects.patch`
  did not apply at all). Four tests that each insist their patch is "last"
  can never all pass together.
- **Three pairs of features share a section number** in `docs/JARVIS-API.md`
  (§59, §60, §61), and two share settings index 12 on the phone.

A combined copy with all of this resolved exists (it passes: 172 of 176
backend suites (the 4 failures are the "last" tests), 103 of 104 desktop
test files, the Rust check, the parity check). It
was **never pushed**: this session may only push to its own branch. See
"What you need to decide", below.

### 2. One-time codes can reach the AI (security, high; [04](audit-2026-09-28/04-security.md), [01-android](audit-2026-09-28/01-bugs-android.md))

Two audits found it separately, and it was confirmed by reading the file.
The phone's filter that hides one-time codes before a notification reaches
Jarvis (`NotificationRedactor.kt`, continuation branch) checks the title and
the text **separately**, and only knows English words like "code" and
"verification". These get through untouched: "Use 482913 to log in to
Instagram", "Your Microsoft PIN is 4821", "Tu código es 482913", a code in
the text when "code" is only in the title. This breaks your own condition
for this feature (codes hidden before anything reaches the model). It stays
on your own devices, and the feature is off by default. **Fix before it
merges**: check title and text together, add "PIN", "log in", "sign in",
"login" and other languages, and always hide "123 456"-style codes.

### 3. Your animal-voice decision is not in the code (decisions, [06](audit-2026-09-28/06-decisions.md))

`backend/jarvis_voices.py`, on `main` and every branch: "Voice follows the
face" still starts **on** (`FACE_VOICE_DEFAULT = True`), the sea otter still
uses speaker "4" ("American (female) - Sky"), and neither app asks the
one-time "Use it / Keep my voice" question. A test (`test_voice_upgrades.py`)
checks that it starts on, so it protects the wrong behaviour. The mascot
session owns this code and is expected to do it; it was not changed here so
the two would not clash.

### 4. The memory "entity layer" makes finding facts worse, and it is on (effectiveness, [03](audit-2026-09-28/03-effectiveness.md))

On the long-conversation memory test, "found all @5" (the right facts in
Jarvis's top 5) drops from 9.5% to 3.6% with it on, and it is on in every
chat. The cause: it adds every fact linked to a person you name, newest
first, so a person you mention often (in the test, one person is linked to
291 of 419 lines) floods the top 5. A tried fix (skip very common names)
brought it back to 8.3% with the main memory test unchanged. Your rule
says a change that makes a number worse is not kept, but this one was added
the day before that rule. **Decide it with the test on your PC** (the
update guide has the line).

### 5. Two sessions' "finished" is not quite finished (sessions, [10](audit-2026-09-28/10-threads.md))

- The continuation session says "completed", but **its 21 commits have no
  pull request** and are on no other branch: Goals, the plan card, "Try the
  cloud model", the 3rd graphics card and phone notifications would be lost
  if that branch were deleted.
- The GitHub-repos session says "completed", but its own CI failed: a web
  address in a code comment in `faces.html` trips the "nothing loads from
  the internet" test.
- Two sessions fixed the same crisis thumbs-down problem; `main`'s CLAUDE.md
  still says it is not fixed.
- The competitor-audit session built about 15 features but never wrote your
  choices into CLAUDE.md and ran no follow-up audit of them (your standing
  rule). Its features are covered by the audits here.

### 6. Smaller things worth fixing

- **Lockdown does not stop everything it says it stops** (security): a
  chatbot conversation already running and the weather keep going. Three
  branches built these without knowing about each other.
- **The PC's "private topic" check misses common health words** (diabetes,
  pregnant, HIV, blood pressure, a medicine name). You still see the exact
  words on the card before anything goes to a chatbot or the cloud, but the
  card's "nothing private is sent" promises more than the check does.
- **Turning phone-notification reading off on the PC does not reach the
  phone at once** (decisions): the phone only re-reads the switch when its
  own settings page opens. Nothing leaves the phone meanwhile.
- **Captured phone notifications are never deleted** (up to 200, 7 days),
  even after the switch goes off.
- **"Call my mum's phone" rings your own phone** (competitor branch), loudly
  and without a card, because the phone-finder accepts any name.
- **Talk-to-type and Jarvis Live can both try to take the microphone**, and
  the message blames "Hey Jarvis" instead.
- **Jarvis Live warms the wrong model** after you switch models, and can put
  a second 8B model on the 8 GB card.
- **The plan card is not ready to switch on** (it is off, correctly): its
  card does not show each step's details, some steps that should ask again
  would not, and a step never receives the previous step's result.
- **Choosing a face on the PC is hard** (play tests): 85 Tab presses to the
  first face, and "Use this face" saves nothing until you find a small Save
  chip. On the phone it is one tap.
- **The home-screen widget keeps showing its text for up to 30 minutes**
  after App lock is turned on (one missing line).

## What was fixed on this branch

This session may only push to `claude/jarvis-post-change-audits-olihzo`, so
it fixed only what is already on `main`:

- `backend/README.md`: a lost code fence made GitHub show about 9,000 lines
  of the patch guide as code and the commands as prose. Fixed, and the
  whole file now pairs its fences correctly.
- Stale facts in the docs: patch count (83, not 51), "all but two apply",
  face count, desktop test count, seven hotkeys, tool-test count, the API
  page's opening, and a two-line PowerShell block made one line.
- Desktop: the CPU/memory sampler no longer loads every process, disk and
  network adapter at start-up.
- The Gemini package tool (`tools/gen_gemini_bundles.py`): splits into
  files Gemini reads well, and covers the new areas.

Every other finding is on a branch this session cannot push to. Each one is
listed, with the file, line and a proposed fix, in the detailed report it
came from, for the session that owns it.

## What you need to decide

1. **How the five branches reach `main`.** Decided (owner, 2026-09-28): ONE
   combined pull request from this audit's branch, with the clashes
   resolved and the blocking fixes in it (the one-time-code filter, the
   animal voice starting off and the otter not on "Sky", the four "is
   last" tests, the `faces.html` address). The one-time "Use it / Keep my
   voice" question is not in it yet.
2. **The entity layer**: keep it, fix it, or turn it off, after the memory
   test on your PC.
3. Questions the audits raised for you, each in its report: whether builds
   should publish from `main` only (they still also publish from an old
   branch); whether pairing by QR code should still wait for "more devices";
   whether widget buttons should work under App lock; whether a goal's
   weekly check-in should stop asking, like reminders; whether the app
   builder's project list should join Projects.

## What only your PC or phone can check

The memory tests with the real model, the tool test that could unlock the
plan card, the voice timings for Jarvis Live, the graphics-card memory the
faces really use, whether Jarvis Live keeps running with the phone's screen
off, and the phone app built from the combined code. The update guide
(`docs/UPDATE-AND-CHECK-2026-09-28.md`) has a one-line command for each that
can be run.
