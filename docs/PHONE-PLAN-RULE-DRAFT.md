# Considered and NOT needed - the design keeps the floor

**This is a record, not a proposal. Nothing here is pending, and nothing is
waiting for a signature.** `docs/RULE-FLEXIBILITY.md` is **not** to be edited,
and no entry 004 is needed, for the reason below.

## What happened

The design in `docs/PHONE-PLAN-DESIGN.md` needed the floor's second half
relaxed: the floor says *"acting stays blocked while the event stream is
stale"* (`docs/RULE-FLEXIBILITY.md:45-46`), and the first draft of that design
had a session that kept tapping over `adb` when the stream dropped, because the
taps are local commands and not events.

The owner was offered that floor change and **declined it**. His answer
(2026-10-11):

> **"Approve, but make it stop when the link drops"**

That is the safer third path: **add the guarantee and keep the floor.** The
design now requires the session to **stop dead when the phone's link to the PC
drops** (`docs/PHONE-PLAN-DESIGN.md` §6 and §17), which keeps the floor's
second half true for a session - **and the floor item is left exactly as
written.**

This file is kept because the reasoning below is worth having for whoever looks
next: it says precisely what a floor change would have involved, why the
project's own words call that *"a finding to report - **not** a reason to edit
this list"* (`:53-54`), and what the code would have had to change. **It is not
a draft awaiting approval, and it should not read as one.**

## What a floor change would have involved (kept for the record)

Had the owner chosen the floor change, this is the entry that would have been
copied into `docs/RULE-FLEXIBILITY.md`, following that file's own three steps
(`:19-37`) and entry shape (`:58-`):

- **The rule that would have been relaxed.** `docs/RULE-FLEXIBILITY.md:45-46`:

  > **Never auto-approve anything**, and acting stays blocked while the event
  > stream is stale.

  Only its **second half**: the session's taps are local `adb` commands, so a
  dropped event stream would not have stopped them.
- **What would have been kept.** The first half as written - nothing approved
  without the owner, one card plus Windows Hello on the PC and the screen lock
  on the phone - and every other floor item untouched (no public tunnel; keys
  never logged; no client speech-to-text; non-commercial and sideloaded; no
  bulk approval; the phone's own "Never look at" list, app lock and Security
  switches).
- **What would NOT have been kept.** The list in `docs/PHONE-PLAN-DESIGN.md`
  §17: a password box, a 2FA box, a bank app, and a spending or sending button
  are recognised only by unreliable means, each with the mechanism that fails.
- **The alert, and the switch.** A gate action at tier `ask`, one card, and a
  row on the "What asks first" page with **off immediate and no card**.
- **Why it was not a setting that could simply be flipped.** `control_phone`
  and `run_plan` are **both** in the code's own `HARD_LIMITS`
  (`backend/jarvis_asks_first.py:402-431`; the two names at `:405` and `:419`) -
  *"Never loosened from an app, whatever else changes"* (`:398-401`) - **and
  both are in `MUST_ASK` too** (`:436-456`; `control_phone` at `:437`,
  `run_plan` at `:446`). Those sets govern the **switch**, not the gate: the
  loosening path refuses (`:1174`) and the page renders such a row as *"Always
  asks. This cannot be changed from an app."* (`:799`, `:82`). So a switch
  could not have been *created* without a code change; while the gate itself
  would not have refused a `control_phone` call - it would have **asked**
  (tier `"ask"`, `backend/rebuilt/jarvis-framework.toml:248`).
- **The staleness point.** Even with the entry approved, the honest sentence
  mid-run would have been: refused to start while the link is stale; a per-step
  device check; and **not** blocked while running.

## Why it turned out not to be needed

The owner's "make it stop when the link drops" removes the only thing the entry
was for. A session that stops dead the moment the phone's link to the PC drops
**keeps** the floor: acting no longer continues while the stream is stale.
`docs/PHONE-PLAN-DESIGN.md` now carries that as an enforced promise in its
promised list (§17), not as an aspiration.

**And keeping the floor removes the switch as well**: nothing is loosened, so
no gate action, no "What asks first" row, and no code change to `HARD_LIMITS`
or `MUST_ASK` are needed. `docs/PHONE-PLAN-DESIGN.md` §18 states that, names
which build gate falls away with it, and flags the one question that remains
open (the delete toggle, which was never a rule relaxation in the first place).

**Status: closed. No entry, no approval, nothing pending.**
