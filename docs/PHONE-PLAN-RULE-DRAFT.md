# DRAFT rule entry 004 - NOT APPLIED, awaiting the owner's word-for-word approval

**Nothing in this file has been applied.** `docs/RULE-FLEXIBILITY.md` has not
been edited, no code has been changed, no setting exists to turn on, and no
switch has been added anywhere. This is the exact text proposed for that file,
put here so the owner can read the words and change them before anything is
built. `docs/RULE-FLEXIBILITY.md`'s own first step says the entry names **who
decided - "the owner, or nothing - an agent may not do this"**
(`docs/RULE-FLEXIBILITY.md:22-23`), which is exactly why an agent has written it
here instead of adding it there.

If he approves these words, they are copied into `docs/RULE-FLEXIBILITY.md` as
entry 004, in the same change that builds anything.

The design that needs it is `docs/PHONE-PLAN-DESIGN.md`.

---

## ### 004 - A phone session may keep tapping while the event stream is stale

- **The rule that was relaxed - and this is a FLOOR change, not a normal one.**
  `docs/RULE-FLEXIBILITY.md:45-46`, from "What may never be relaxed, under any
  feature":

  > **Never auto-approve anything**, and acting stays blocked while the event
  > stream is stale.

  That file also says, two lines under the list
  (`docs/RULE-FLEXIBILITY.md:53-54`):

  > If a feature appears to need one of these, that is a finding to report -
  > **not a reason to edit this list.**

  **This entry is the owner overruling that sentence knowingly.** It should be
  read that way, and it is the first entry in that file to touch the floor
  rather than a rule beside it. Two halves are at stake and they are not the
  same half:

  - **What is relaxed: the second half.** A phone session taps over `adb` on
    the owner's own phone. Those taps are local commands, not the event stream,
    so when the stream to the apps drops the runner does **not** stop tapping.
    Today's floor says acting is blocked while the stream is stale; this feature
    acts anyway, and the design says so plainly instead of implying a block it
    does not deliver (`docs/PHONE-PLAN-DESIGN.md` §6 and §17).
  - **What is kept: the first half, as written.** Nothing is approved without
    the owner: every command in a session comes from a card he approved, with
    Windows Hello on the PC or the screen lock on the phone. **Said exactly:**
    one approved card covers the listed commands, and they then run with no
    further card - the shape he already allowed for a plan
    (`CLAUDE.md`, 2026-09-27: *"The plan card is allowed later, only after the
    multi-step safety tests pass; risky steps still get their own card."*). It
    is not a session-level "always allow".
- **The feature that needs it.** **The phone agent**
  (`docs/PHONE-PLAN-DESIGN.md`): the owner asked for Jarvis to drive his
  Android phone the way an agentic assistant drives a phone (2026-10-11), and
  then chose **"Still change the floor, with only enforceable promises"** - that
  is, go ahead, but promise only what the code can actually hold.
- **Decided by.** **The owner.** The floor change above is his call and nobody
  else's; this entry is a draft until he approves these exact words.
- **What is kept - all of it, unchanged.**
  - **No public tunnel.** No ngrok, no Cloudflare Tunnel, no Tailscale Funnel,
    nothing new: the session reaches the phone over the owner's own Meshnet.
  - **The pairing token and every API key are never logged**, and never written
    to disk in plain text. The session uses `adb` only, and `adb` inherits
    nothing of Jarvis's own environment
    (`backend/jarvis_android_control.py:223-229`).
  - **A client never does speech-to-text.** Untouched: nothing here listens.
  - **Non-commercial, sideloaded, never on Play.** Untouched.
  - **No bulk approval, and nothing that clears a rush latch.** Untouched, and
    a session cannot approve anything at all - it has no approval path.
  - **The phone's own rules are untouched**: its own "Never look at" list
    (`jarvis-client/.../data/ScreenNever.kt:9-17`), its app lock, and its
    Security switches stay exactly as they are. This feature does not read the
    phone's notifications, its messages or its screen history.
  - **Nothing about the owner's memory, email, files or credentials is
    involved**, so rule 1 is untouched: the phone agent reads a screen over adb
    on the PC, and no model that is not local sees anything
    (`docs/PHONE-PLAN-DESIGN.md` §15).
- **What is NOT kept, plainly.** This entry does **not** claim any of the
  following, because the code cannot hold them. The mechanism that fails is
  named for each, with the line the review gave:

  | Claim | What actually happens |
  |---|---|
  | A **password box** is never typed into | Recognised only from the accessibility dump's `password` attribute - which **has never once appeared set** in this project's own capture (49 nodes, all `password="false"`, `docs/phone-checks-2026-10-09/dump-checks.xml`) |
  | A **2FA / one-time code** box is never typed into | **Not enforceable**: an OTP box is an ordinary numeric field, nothing marks it, there is no accessibility service, and `_SAFE_TEXT` permits digits (`backend/jarvis_android_control.py:76`), so `input text 123456` is built and sent |
  | A **bank** app is never opened | A **documented heuristic, not a promise** (`jarvis-client/.../data/ScreenNever.kt:9-17`; `NotificationAllowList.kt`, whose own test asserts the false negative at `NotificationAllowListTest.kt:55-61`). Worse here: that heuristic runs **on the phone**, and needs the app's store category, which the PC runner driving `adb` does not have |
  | A **spending or sending** button is never pressed | **Wishful**: the only reader of a button's meaning is the model's own self-report, and this module already records it failing to flag a Send click (`backend/jarvis_android_control.py:180-192`) |

  It also does not promise that a step stays inside one app in any useful
  sense: the check is **package-only**, so a browser is one package and every
  website is inside it, and a spend-or-send sheet drawn inside an allowed app
  passes by construction (`docs/PHONE-PLAN-DESIGN.md` §17).
- **The staleness point, corrected.** The design's first draft claimed acting
  stops when the stream is stale. It does not. What is true mid-run:
  - **refused to start**: a session does not begin while the link is stale
    (the 12-second grace, `docs/ARCHITECTURE.md:1874-1875`);
  - **checked every step**: the device is still the same serial in `adb`'s own
    list, or the run stops (`backend/jarvis_android_control.py:381-385`);
  - **not blocked while running**: a dropped stream does not stop the taps, and
    the live line goes quiet. The result says the report was incomplete.
- **The alert (step 2).** Gate action `phone_agent_session`, tier **`ask`**:
  one card, in plain words, saying which floor half is relaxed and what it lets
  happen - and **carrying the card's own sentence** (below). On the PC that
  means **Windows Hello**; on the phone, **the screen lock**.
- **It is not a setting that can be flipped, and that has to change in code.**
  `control_phone` and `run_plan` are both in the code's own `HARD_LIMITS`
  (`backend/jarvis_asks_first.py:402-431`, the two names at `:405` and `:419`),
  whose comment reads *"Never loosened from an app, whatever else changes"*
  (`:398-401`), and `run_plan` is in `MUST_ASK` as well
  (`:436-456`, name at `:446`). So **until those sets change in code, there is
  no switch to turn on and nothing can run.** Building this feature therefore
  *includes* changing those sets - which is precisely the floor change this
  entry records. A reviewer should read the diff for that, not a settings file.
- **The setting, and "What asks first" (step 3).** One row on the "What asks
  first" page (`backend/jarvis_asks_first.py:210-211` and its mirrors), beside
  the other loosening switches, with the design's own two switches: **the phone
  agent** and **"Let Jarvis delete things"** - both **off by default**, the
  second doing nothing unless the first is on. **Turning either off is
  immediate, with no card.** `docs/RULE-FLEXIBILITY.md:36-37`.
- **The card's own words (the sentence, exactly as it would appear).**

  > **Jarvis recognises a password box, a bank, and a spending or sending
  > button only by guesses its own code documents as unreliable. With this on,
  > a tap Jarvis has misread can send a message, spend money, or delete
  > something, and stopping it lands between taps.**

- **What is promised instead, with the mechanism that holds each one** - this
  is the list the owner asked for, "only enforceable promises", and the design
  carries it as §17:

  | Promise | What holds it |
  |---|---|
  | Never taps inside the Jarvis app itself | Real code, per step: `backend/jarvis_android_control.py:236-286` |
  | The app in front stays the same package | The same per-step check, compared with the plan's own recorded package |
  | A step runs only after its target is found again on the current screen | The plan's per-step guard; it stops rather than tapping stale coordinates (`docs/PHONE-PLAN-DESIGN.md` §2) |
  | Stop lands between taps, and both the phone's Stop and the PC's hotkey reach it | `jarvis_task_control.checkpoint()` consumes the signal (`backend/jarvis_task_control.py:91-124`), read first at each step (`backend/jarvis_android_control.py:355-380`) - **and only if the run registered as a task with an id** (`:121-122`) |
  | A hard time and step limit | Steps capped at 8 (`backend/jarvis_plan.py:84`); the time limit is a fixed number, not "about" |
  | A visible marker while it runs | The badge (§13) and the content-free live line (`backend/jarvis_android_control.py:390-397`) |
  | Never touches hidden memory lists or app lock | Not on this path at all: the agent has no route to either |
  | Everything local | `adb` to the owner's own phone; a local model; nothing sent anywhere (§15) |
- **The build gates - all six, nothing runs until each is met.**
  1. The plan card's own `tools/tool_eval` bar (`backend/jarvis_plan.py:453-492`).
  2. The tiers stay "ask" (`backend/rebuilt/jarvis-framework.toml:248,250`).
  3. The three unverified facts in the design's §3/§11 measured on the owner's
     phone.
  4. The first test (§11) run by the owner, watching.
  5. **The driving model's grounding measured** (§15) - the research has landed
     and names AutoGLM-Phone-9B plus a 2-4B grounding specialist; the numbers
     are still to be measured.
  6. **The delete toggle's limits accepted as written** (§16), with the card
     sentence above on the switch that turns it on.
- **The owner questions still open**: who names the steps; whether a send may
  live inside a plan at all; the cap; stop-the-plan versus pause-and-ask; saved
  recipes; the delete verdicts; and whether a second specialist model may take
  the 12 GB card (`docs/PHONE-PLAN-DESIGN.md`, the closing list).

---

**Not applied. Nothing in `docs/RULE-FLEXIBILITY.md` has changed, no code has
changed, and no setting exists.** If the owner approves these words, the text
between the two `---` lines is copied into `docs/RULE-FLEXIBILITY.md` as entry
004, and the code changes named in "It is not a setting that can be flipped"
are the ones that make the switch exist.
