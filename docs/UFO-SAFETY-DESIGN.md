# Windows UI control: what it would take, and why "add UFO" is not the answer

Written before any code, per the owner's request. This is a design, not a
patch — nothing here has a call site yet.

## What was asked

`microsoft/UFO` was suggested as a way for Jarvis to click around in other
Windows apps — reading their accessibility tree instead of guessing pixel
coordinates. That's a real gap: Jarvis cannot touch any other app's UI today.
The question was how this would go through the same approval gate as
everything else in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## The conflict, stated plainly

UFO is built as a live loop: look at the screen, decide the next click, do it,
look again, decide the next one, repeat until the goal looks done. That loop
is the entire point of the project — it's what "agent" means there.

Jarvis's permission model (`ARCHITECTURE.md` §2–3) is built the opposite way:
**one plan, fully printed, one human decision, then run exactly that plan and
nothing else.** Rule 3 of the five invariants says "no auto-approve anywhere,
and no approve-all control anywhere" — and that rule has already been broken
once by accident, inside the gate itself, which is why it now has a test that
reads the source with comments stripped to check the rule is actually true.

Running UFO's own loop inside Jarvis would mean: Jarvis asks once ("may I try
to do X in this app?"), and then clicks around on its own judgment for as long
as the loop runs, with no card printed for click #2, #3, #47 — a standing
grant for future, unnamed actions. That is the exact shape §2 forbids. It
would not be a bug in an otherwise-fine integration; it would be the
integration.

**So: don't adopt UFO's loop.** What's actually worth taking from it is one
piece — reading the UI Automation (UIA) tree instead of guessing coordinates —
and that piece can be wired into Jarvis's existing shape instead of its own.

## What a compliant version looks like

Same four steps as `jarvis_research.py` — which `ARCHITECTURE.md` §3 calls out
by name as the reference implementation to copy the shape of.

```
plan(goal)      Walk the UIA tree of the relevant window(s) — read-only,
                sends no input, same as jarvis_research reading nothing off
                the network while it plans. Turn what it finds into a
                BOUNDED, FULLY ENUMERATED list of concrete steps: which
                window, which named control (by its accessibility name/ID,
                never bare coordinates), which action (click / type "exact
                text" / select). Every step is decided now. Nothing is
                improvised during run().

describe(plan)  Print every step in full, in the order they'll happen —
                "Click the 'Send' button in Outlook - Compose", not "send the
                email." Say plainly what happens if this is refused: nothing,
                the goal is not attempted.

<human>         jarvis_gate. Tier `ask`, always, for a UFO-driven plan — this
                is new, error-prone, and irreversible action on someone else's
                software, which is exactly what `ask` is for. One decision for
                the whole bounded plan, same as approving one shell command
                with eight arguments is one decision — not one decision per
                click.

run(plan)       Executes ONLY the enumerated steps, in order. Before each
                step, re-reads the UIA tree and checks the target control is
                still there, still enabled, and still means what it meant at
                plan time. If it isn't — the window closed, a dialog popped
                up, the control moved — STOP and report exactly which step
                failed and why, rather than guessing or clicking the nearest
                thing. This is the same staleness rule the app already
                applies to approvals over a dead event stream (invariant/rule
                4): a decision made against a snapshot of the world does not
                get executed against a world that has since changed.
```

**The moment the plan needs to change — a dialog appeared, a step failed, the
goal needs one more click nobody enumerated — that is a NEW plan.** Back to
`plan()`, a new card, a new decision. No loop gets to keep going on its own
say-so. This is slower than real UFO. That's the point: the speed is exactly
the thing this project's own invariants forbid trading away.

## Fitting the rest of the model

- **Weight.** A UI action is `heavy` (interrupts, per the `notice` contract in
  `ARCHITECTURE.md` §3) if it's irreversible (closing a document without
  saving, submitting a form) or if it causes something to leave the machine
  (typing into a browser that posts data, sending through a desktop mail
  client). Anything more like "open this window and look" can be `normal`.
  This is a per-step judgment at `describe()` time, from a risk table the same
  shape as `jarvis_gate._RISK` — not something the plan author eyeballs case
  by case.
- **Egress.** Reading and clicking a local app's UI touches no network by
  itself, so this does not need a new entry in the three-lane egress table
  (§4) — *unless* a planned step is itself a network action (the browser-form
  example above), in which case that step's `describe()` text has to say so
  as plainly as `jarvis_research` says what leaves the machine.
- **Notice / Deny-on-lock-screen.** Same rule as every other approval: Deny
  can be a notification action, Approve cannot. Nothing about this capability
  is a lock-screen decision.
- **No credential of any kind.** UIA reads and synthetic input need no key,
  no token, no network — this capability doesn't touch rule 3 of the five
  non-negotiables (the API-key rule) at all.

## What this does not solve, on purpose

- **It's slow for multi-step goals.** A goal that needs a dialog Jarvis
  couldn't have predicted means stopping and asking again. That's the
  trade for never running an unapproved click.
- **It does not make "have Jarvis use this app for me" into one request.**
  It makes "have Jarvis do this exact enumerated sequence in this app" into
  one request, repeatable when the sequence needs to change.
- **This does not decide whether the capability is worth having at all** —
  only how it would have to be shaped if it is. That's a separate call,
  and a real one: even done exactly like this, letting Jarvis click inside
  other people's software is new territory for this app.

## Recommendation

Don't take a dependency on `microsoft/UFO`. Its value here is one idea — read
the accessibility tree, don't guess coordinates — and that idea is a page of
Windows UI Automation calls (`windows-rs`, from Rust, or `pywinauto`/`uiautomation`
from Python), not a framework.

## Update — built, not wired

The owner asked for this to be built, per the shape above. `backend/jarvis_ui_control.py`
now exists: `plan()`/`describe()`/`run()`, `uiautomation`-based, with `run()`
re-verifying every target against the live accessibility tree right before
acting on it and stopping rather than guessing the moment it does not match.
`backend/test_ui_control.py` (28 checks) proves `plan()` sends no input,
`run()` refuses without `approved=True`, and a control that changes or
vanishes mid-plan stops execution at exactly that step - all against
injected fakes, never a real Windows desktop.

**It is not reachable from the running app.** `jarvis_hud.py` is not in this
repository, so the route that would call this module, queue its plan through
`jarvis_gate`, and wire its `announce` callback to `jarvis_events.set_activity`
cannot be written here. `backend/README.md`'s new section spells out exactly
what that route needs. Until it exists, this module is tested, real code with
no caller - worth stating plainly rather than leaving to be discovered, since
that exact gap is this codebase's own most-repeated defect.
