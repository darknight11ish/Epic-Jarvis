# Richer proposals, live progress, and a stop switch

What the owner asked for, in their own words:

> "I want Jarvis to have more autonomy on tasks than just asking me for
> permission for everything, when it does want more autonomy or I ask it to
> act with more autonomy, it should come up with a straightforward proposal
> with the details and limits of what it plans to do, along with update me
> with progress reports as it works. And I want to be able to have multiple
> choice options around this, and the ability to type in extra things before
> hitting the first accept. Along with an ability to type in through the
> android app or desktop program extra things or pause or stop the current
> task."

This is a real design, not a quick patch - it touches the backend (not in
this repo), the desktop UI (in this repo), and the Android UI (a different
session's branch). This document is the contract those three build against,
the same role `docs/UFO-SAFETY-DESIGN.md` and the cross-client contract docs
already play for the tools that exist today.

---

## 1. The one thing that does not move

`docs/ARCHITECTURE.md` invariant 3, word for word:

> "No auto-approve anywhere, and no approve-all control anywhere. One
> action, one decision. Do not build one."

This is not a style preference. `backend/README.md`'s `no-auto-approve.patch`
section is the receipt: `confirm_auto()` once granted every `ask`-tier action
for the life of the process on the strength of one flag, with zero callers,
sitting inside the module whose entire job is refusing exactly that. It was
found, ripped out, and the flag was turned into a no-op that says so on
stderr rather than silently keep bypassing anything.

Reading the request above against that rule: nothing in it actually asks for
the rule to bend. "More autonomy than asking for permission for everything"
reads as *fewer, bigger, better-described decisions* - one approval that
covers a whole bounded task instead of nagging for every click inside it -
not *zero* decisions. That is already this project's own pattern (see
Section 2). Everything genuinely new below (Section 3) is asked to make that
pattern richer and give the owner a live off switch, never to remove the
decision itself.

**So the frame for everything that follows:** a task never runs, and never
keeps running, past what was explicitly shown and approved, without a new
human decision. Pause and stop are exceptions that make in-progress work
*stop* sooner, never grants that make it start or continue without being
asked.

---

## 2. What already does this, today, verified against the real files

`jarvis_ui_control.py`, `jarvis_android_control.py`, and
`jarvis_browser_control.py` already implement "a straightforward proposal
with details and limits" for their three domains:

- `plan(goal, ..., requests)` reads current state once and returns a `Plan`:
  a **bounded, fully enumerated list of `Step`s** decided now, never
  improvised later. `Plan.weight` and each `Step.heavy` flag already carry
  the "limits" the owner is asking for - a heavy step is one that is
  irreversible or leaves the machine, called out explicitly.
- `describe(plan)` renders that into the card text a human actually reads
  before deciding - every step, in order, with its own `why`, and a plain
  "if you say no" line.
- `run(plan, approved=True)` executes **only** those enumerated steps, and
  (`browser_control`'s `navigate` excepted) re-verifies each target is still
  what was planned immediately before running it - a mid-task surprise stops
  the run rather than pushing through.
- `announce(text)`, threaded through all three, fires once per step -
  `jarvis_agent.py`'s own comment: "wires `announce` to the same
  `_activity()` doorbell everything else in this project already uses."

So "one decision for a bounded, fully-printed set of steps, not an
approve-all" is already built, in three places, and already tested
(`test_ui_control.py`, `test_android_control.py`, `test_browser_control.py`).
**What's below is what is genuinely missing**, checked directly against the
real desktop source rather than assumed:

- `jarvis-desktop/src/jarvis-link.js`'s event payload today carries exactly
  `activity` (one of a small fixed set - `idle`/`working`/`error`/...),
  `approvals`, `attention`, `connected`, `stale`, `power`. **No free-text
  field exists at all.** `announce()`'s actual sentences
  ("Step 2/3: click 'Send' in Support Chat") are called on the backend but
  have nowhere to land on the wire today - the owner sees a generic
  "thinking" face, not what Jarvis is actually doing.
- `jarvis-desktop/src/widget.js`'s approval card (`openApproval`) renders
  exactly `action`, `detail`, `risk`, and `raised` - and offers exactly two
  buttons, Yes and No (`decide(approved)` takes a bare boolean). **No
  options list, no free-text field, exists on the card at all.**
- Nothing anywhere - backend module, gate, or either client - checks for a
  pause/stop/inject signal *while a plan is running*. Once `run()` starts,
  the only way it stops early is a step failing its own re-verification.

Four real gaps, precisely bounded. The rest of this document designs those
four, not a rewrite of what already works.

---

## 3. The design

### 3a. Multiple-choice options on a proposal

A card gains an `options` list. Each option is a **complete, independently
bounded plan** - not a checkbox that mutates one plan, because a plan whose
shape can change after being shown is exactly what "fully enumerated ahead
of time" was written to prevent.

```json
{
  "id": "appr_...",
  "action": "control_browser",
  "detail": "...",
  "risk": {...},
  "raised": null,
  "options": [
    {"id": "opt_a", "label": "Reply and wait for their answer",
     "summary": "1 step: send the drafted message.", "weight": "heavy"},
    {"id": "opt_b", "label": "Reply and also ask for a refund",
     "summary": "2 steps: send the message, then ...", "weight": "heavy"}
  ]
}
```

When `options` has exactly one entry (or is absent), the card behaves exactly
as it does today - this is additive, not a breaking change to the existing
shape. `decide()` on the client becomes `decide(optionId, approved, note)`;
picking "No" needs no option id.

### 3b. A free-text field before the first accept

The owner can type something into the card **before** approving or denying.
Submitting text with no decision does not approve anything - it sends the
note back and asks the model to produce a **new** set of options that
account for it, which replace the ones shown. This is the same rule as
Section 1: a note is never spliced into an already-approved plan; it always
produces a fresh plan, fresh `describe()` text, and a fresh decision.

Practically: `POST /api/pending/<id>/amend` with `{"note": "..."}`, distinct
from `POST /api/pending/<id>/decide` with `{"option_id": ..., "approved": ...}`
- confirm both names against the owner's real `jarvis_hud.py` before writing
a patch; `backend/README.md`'s own ui-control-wiring section already learned
the lesson about guessing route names blind.

### 3c. Live progress while it runs

The fix is small precisely because `announce()` already exists and already
fires once per step. What's missing is a wire field and a place to show it:

- Backend: the event payload's existing `activity` enum gains a sibling,
  `activity_detail` - the exact string `announce()` was already given,
  capped (`_MAX_TOOL_CONTENT_CHARS`-style bound, not open-ended) and
  ephemeral - never persisted, never fed back into any model context, purely
  a status line. `activity` stays the coarse state the face animation
  already keys off; `activity_detail` is new and additive.
- Desktop: `jarvis-link.js`'s state object gains `activityDetail`; the
  widget shows it under the existing "thinking" face state, same place a
  spinner already implies work is happening, now saying what work.
- Android: same field, surfaced the way `FaceView`/the activity indicator
  already shows state today - a line under it, not a new screen.

### 3d. Pause, stop, and inject-while-running - from either client

The run loop already has a checkpoint: `jarvis_ui_control.run()`,
`jarvis_android_control.run()`, and `jarvis_browser_control.run()` all
re-verify the live target **before every step**. That is exactly where a
control signal is checked too - no new architecture, one more read at a
point that already exists in all three loops.

- **Stop**: takes effect at the very next checkpoint. Steps already done stay
  done (a step, once run, cannot be un-run); everything from the current
  step onward is reported `not_run`, the same shape a failed re-verification
  already produces. Resuming anything after a stop is a brand new `plan()`
  and a brand new decision - never automatic, per Section 1.
- **Pause**: same checkpoint, but `not_run` steps stay live rather than
  closed out - the card stays open, showing exactly how far it got. Resuming
  a pause is one explicit "continue" decision, not a timer and not implied
  by anything else happening.
- **Inject a note mid-run**: does **not** alter the steps currently
  approved and running - those finish exactly as shown. The note is queued
  for the *next* proposal, the same amend flow as 3b, so an in-flight plan's
  bounds are never touched live.
- **Reachable from either client**: stop/pause/inject are just another
  action against the running task's id, broadcast the same way
  `approval-resolved` already is today - so a pause hit from the phone is
  visible on the desktop widget within one event-stream frame, and vice
  versa. No new transport, the existing fan-out `GET /api/events` already
  does this for approvals.
- **A client must never show "paused" on its own say-so.** Sending the
  pause request and having the request succeed are two different facts;
  only the second is true the instant `invoke()`/the HTTP call resolves.
  The desktop widget's draft UI (`jarvis-desktop/src/widget.js`) learned
  this the hard way while being built: its first pass flipped the button
  from Pause to Resume the moment the click handler's own call did not
  throw, which is a guess dressed as a confirmation. The fix needs no new
  route to be correct today - `link.activity` already carries whatever
  string the server reports, unvalidated, so the button now swaps only
  when a real event reports `activity: "paused"`, exactly the same
  `approval-resolved`-style trust boundary Stop and Pause/Resume above are
  specified to use. Until `jarvis_gate.py` actually emits that value,
  Resume simply never appears - which is the honest state of a feature
  whose backend half does not exist yet, not a bug to work around.

---

## 4. What this document is not

It is not a patch. `jarvis_gate.py` and `jarvis_hud.py` - the files that
would actually need the new routes, the new `options`/`amend`/`control`
shapes, and the `activity_detail` field - are not in this repository, the
same standing note every backend section in `backend/README.md` already
carries. Route names, exact JSON keys, and where in `jarvis_hud.py` the
event payload is actually built all need confirming against the real files
before anything here becomes a real patch - guessing that blind is exactly
the mistake `ui-control-wiring.patch`'s own section in `backend/README.md`
already made once and rewrote.

**What can be built now, against this contract, without those files:**
the desktop UI additions (options list, note field, live progress line,
pause/stop controls) can be written and tested against a mocked event
stream today, the same way `jarvis_ui_control.py` is tested against an
injected `read`/`act` with no real Windows desktop. That is the concrete
next step on this branch.

**What needs the Android session:** the same UI additions, on their branch.
This document is the thing to hand them, the same way
`docs/ANDROID-FEATURE-AUDIT.md` already hands over the backend audit -
cross-branch, read before acted on, not duplicated.

---

## 5. Where this connects to the browser-control work already shipped

The three "make it more comprehensive" directions from the same
conversation - handling a full back-and-forth in one chat, working across
several chat-widget shapes, and proactively telling the owner when someone
replies - all become straightforward **once this exists**, rather than
needing their own separate approval UI each:

- A multi-turn conversation is naturally several proposals in sequence, each
  one a small, bounded `Plan` (read the new messages, draft a reply) -
  Section 3a's options are exactly "send this" vs. "send this instead" vs.
  "wait, don't reply yet."
- A proactive "someone replied" notice - the piece Section 5 of the earlier
  answer named as needing backend infrastructure this repo doesn't have -
  is exactly a card that raises itself rather than waiting to be asked, using
  the same `raised` field `widget.js` already renders (`A3` in the task
  list). The stop/pause control in 3d is what makes leaving such a watcher
  running trustworthy at all.

Build order recommendation: this document's desktop slice (options + note +
progress + pause/stop UI, against a mock) first, since it is the foundation
everything else in the browser-comprehensiveness direction sits on top of -
not a parallel, unrelated piece of work.
