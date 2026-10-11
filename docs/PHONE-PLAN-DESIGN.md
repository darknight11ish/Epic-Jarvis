# Tapping around on the phone: ONE plan card for a short sequence (design)

**Status: designed, nothing built. No patch, no module, no route.**
The owner asked whether Jarvis could control his Android phone "similar to how
Gemini on the Pixel 11 can take agentic control" (2026-10-11). **He was told
the ability already exists as the `control_phone` action and is "one card per
tap" - that was wrong, and this draft repeated it (see the corrections below).**
He then chose: **design the multi-step version - a short
multi-step action as one plan card listing every tap up front, written down
for him to approve before anything is built.** That decision is the same one
already written in `CLAUDE.md` for the plan card generally (owner,
2026-09-27): *"The plan card is allowed later, only after the multi-step
safety tests pass; risky steps still get their own card."*

**Then he settled the one thing that would have needed the floor changed.** He
was offered a `docs/RULE-FLEXIBILITY.md` floor entry (a session that keeps
tapping while the event stream is stale) and chose the safer route instead
(2026-10-11): ***"Approve, but make it stop when the link drops."*** So the
session **stops dead when the phone's link to the PC drops**, `CLAUDE.md` rule 4
stands **exactly as written**, that file is **untouched**, and **no entry is
needed** (§6, §17, §18). The record of what was considered is
`docs/PHONE-PLAN-RULE-DRAFT.md`. **And keeping the floor removed the switch as
well**: nothing is loosened, so the feature rides the card that already exists
(§18).

Written by the studio's designer against `origin/main` `b2beb60a`
(2026-10-11), corrected the same day against an adversarial review and a
model-research pass. **Anything marked unverified has not been tried on the
owner's phone or on any phone by this design.** The phone is in use by another
conversation while this is written: nothing here was run against it, and no
`adb` command was issued while writing.

**In one paragraph.** Jarvis can already tap his phone: `control_phone` takes a
**`requests` array** (`backend/jarvis_agent.py:1545-1561`, the schema at
`:1552`), so one call can carry twenty commands under **one** card
(`backend/jarvis_android_control.py:195-216`, `:306-333`) - **there is no cap
on how many ride a card, and there never was.** This design therefore does not
replace twenty cards with one; a card can already cover twenty. What it adds is
**verification between the commands and a local record of them**: Jarvis works
out the literal commands first, shows all of them in order on one card, and
runs them while checking before every step that the phone is still the same one
and still the app it was planned against. Said honestly, what the owner asked
for - an agent that keeps acting while it looks - is **the card removed for ten
minutes**, and this design does **not** grant that (§1, §17). A step that sends
something, touches a lock or a permission, or would type into a secret field
does **not** ride along inside the plan: it keeps its own card. And a plan is
never a session: it has a fixed list of steps, a fixed
end, and it stops dead - it never guesses - the moment the phone is not where
the plan expected it. A marker on the phone shows which step of how many is
running, one control stops it, and every step it took is written down locally
afterwards. **One switch decides how much of it happens** - he asked for "Let
Jarvis delete things" (§16), off by default, which covers only deletions he can
still undo and never lets an account be deleted. The session itself needs **no
switch at all**, because nothing is loosened (§18): it rides the card
`control_phone` already has.

## Corrections to the first draft (2026-10-11, after an adversarial review)

The first draft rested on a premise that is **false**, and it presented several
exclusions as walls with nothing behind them. Corrected in place below; the
record is kept here rather than quietly rewritten, and nothing in this list is
defended. **One later correction is different in kind and is recorded at the
end of this list:** the owner settled the staleness question himself, in the
safer direction, and that changed what this design asks for (item 7).

1. **"One card per command" was wrong.** `control_phone` takes a `requests`
   array (`backend/jarvis_agent.py:1545-1561`): one call, N commands, ONE card
   describing and running the whole array
   (`backend/jarvis_android_control.py:195-216`, `:306-333`). `MAX_STEPS = 8`
   belongs to `jarvis_plan` (`backend/jarvis_plan.py:84`), not to this tool, so
   nothing caps a phone card's length. **Said honestly: the request is not "one
   card instead of twenty" - a card can already cover twenty. The request is
   that the card be removed for ten minutes.** This design does not grant that;
   what it adds is verification and a record (§2, §13).
2. **A look-then-act session cannot be built on the plan machinery**, so the
   reuse this draft claimed fails on exactly the half that matters (§1):
   `jarvis_plan.propose()` refuses a plan from a tainted turn
   (`backend/jarvis_plan.py:191-194`, `:202-203`), and the plan path refuses
   when `watch.tainted or watch.read or watch.provenance or watch.app_context`
   is set (`backend/jarvis_agent.py:1489-1490`). `control_phone` sets `read`,
   because it is not in `_NOT_READING` (`backend/jarvis_agent.py:3984`,
   `:4295-4296`).
3. **The exclusions are not walls.** §17 states one by one which have real
   enforcement and which do not - and only two do.
4. **"Acting stops when the event stream is stale" was not delivered mid-run** -
   the honest position at the time, corrected in §6. **Then the owner settled it
   in the safer direction** (item 7 below): the design now *delivers* it, by
   stopping the session dead when the link drops.
5. **Stop lands between taps, and only reaches a session that has a task id.**
   Said exactly in §7 and §14.
6. **The delete guard misses two shapes by construction** - a long-press menu
   that shows "Delete" only after the press, and a swipe with no node to read
   (§16).
7. **The owner kept the floor (2026-10-11), and that simplified the design.**
   Offered a `docs/RULE-FLEXIBILITY.md` floor entry, he chose *"Approve, but make
   it stop when the link drops."* So: the floor item stands exactly as written,
   `docs/RULE-FLEXIBILITY.md` is **untouched** and **no entry is needed**, the
   session **stops dead when the link drops** (§6, §17), and - because nothing is
   loosened - **the phone-agent switch has gone entirely** (§18). The earlier
   revision asked for a floor change, a switch, and a code change to
   `HARD_LIMITS` / `MUST_ASK`; **none of those three is needed now.** One switch
   remains (the delete toggle) and it turns out to relax **no** rule - which he
   settled the same day: **keep it**, recorded as a preference rather than a
   loosening (§16, §18).

## What already exists and is reused (nothing here is a second version of anything)

| What | Where | What it gives this design |
|---|---|---|
| The literal-command plan and its runner | `backend/jarvis_android_control.py:19-29` (the permission model), `:161-177` (`plan()` builds and runs nothing), `:306-429` (`run()`) | The whole execution half. Unchanged. |
| Why a live session is refused | `backend/jarvis_android_control.py:8-11` | The rule this design must not weaken. Quoted below. |
| The card text | `backend/jarvis_android_control.py:195-216` (`describe()`) | The card body, verbatim: every literal command, numbered, with its `why`. |
| The weight line | `backend/jarvis_android_control.py:188-192` (`CARD_WEIGHT_LINE`) | The one line that says the whole plan is heavy, and that an unmarked step is not a promise. |
| The safe-text rule | `backend/jarvis_android_control.py:65-77` | Why `hello; reboot` cannot become two remote commands. |
| Never tapping inside Jarvis's own app | `backend/jarvis_android_control.py:236-286` | An existing per-step guard, already "stop, do not guess". |
| The plan-card machinery | `backend/jarvis_plan.py` - `:84` (`MAX_STEPS`), `:111-139` (the shapes), `:197-245` (`propose()`), `:262-287` (`describe()`), `:294-380` (`run()`) | The in-between case this was built for. Reused as-is **only when the turn has not read anything** - its 8-step cap and its "a marked step still gets its own card" rule. **It cannot carry a look-then-act session** (§1): a tainted turn is refused outright (`:191-194`, `:202-203`) |
| Checkpoints and stop | `backend/jarvis_task_control.py:78-88`, `:91-124` (the checkpoint **consumes** the signal) | How a plan is stopped between steps. |
| Stop everything | `backend/jarvis_stop_all.py:108` (`register`), `:188-210` (`_stop_tasks`), `:221-256` (`stop_all`); `docs/JARVIS-API.md:6341-6343` | The hotkey and the phone's Stop already stop "a running multi-step task (computer, browser or phone control)" before its next step. |
| The gate | `jarvis-backend/jarvis_gate.py:300` (`control_phone`: reversible "no", reach "outbound"), `:624-639` (`risk_for`), `:780` (the `_plan`/`_run` pair's tiers); `backend/rebuilt/jarvis-framework.toml:248` (`control_phone = "ask"`), `:250` (`run_plan = "ask"`), `:246` | The tiers stay exactly as they are. |
| The line this design must not cross | `backend/jarvis_android_control.py:8-11` | *"a live session that keeps acting for as long as it runs cannot be the thing one approval card authorises, because 'authorise this session' is a standing grant for whatever happens inside it, unnamed in advance."* |

## 1. How Jarvis knows the taps before the card (the crux)

Three ways were considered.

**A. The owner says the steps, Jarvis turns them into commands - recommended.**
The owner says what he wants in his own words ("open the calculator, put in
one plus two, and show me"), and the model's only job is to turn *those words*
into the literal commands `plan()` already builds
(`backend/jarvis_android_control.py:117-158`). The card then lists every
command. This is what happens today, with the card count changed from N to 1.

**B. Jarvis reads the phone's screen and proposes the sequence.** `adb shell
uiautomator dump` gives an XML tree of what is on screen - the project's own
phone audits already use it (`docs/ANDROID-TOUR-2026-10-09.md:251-255`,
`docs/ANDROID-PAIRED-AUDIT-2026-10-10.md:358`). **Deferred, and the reason is
not cost.** A dump costs about **2.33 s** per look on the owner's device
(three runs: 2.33 / 2.29 / 2.37 s, `docs/ANDROID-TOUR-2026-10-09.md:251-255`),
which is affordable for a handful of steps. The real reason is the project's
own rule about where a plan may come from: `jarvis_plan.propose()` refuses
outright when the turn has read outside text - *"A multi-step plan can only
come from your own words, never from something Jarvis read this turn (an
email, a file, a web page)"* (`backend/jarvis_plan.py:191-194`, enforced at
`:202-203`). **A plan shaped by what a phone's screen says is a plan shaped by
outside text** - the same class of thing, from the same class of source, and
the model would be inventing taps to match a sentence some app wrote. If the
owner wants B, it is a change to that rule and needs his decision in so many
words (see the open questions).

**C. A saved recipe, replayed later.** A named sequence, stored, and re-shown
as a card each time it runs. **Second version, and only after A works** - it
is not a standing grant *provided* the card is shown every run, which is the
only version of it this design would accept. Its cost is the drift: an app
that updates its layout makes a recipe wrong in a way the owner cannot see,
which is what §2 exists for. **DECIDED 2026-10-11: not in v1 - deferred, not
refused.** What would have to be true to revisit it: A in use and measured
first, and a card on **every** replay listing every command.

**The one thing all three share, and the reason this design is safe at all:
reading the phone's screen to VERIFY is fine; reading it to PROPOSE is not, in
this version.** Verification does not shape what will happen - it can only
stop it (§2).

**And the correction the review forced on this section (2026-10-11): a
look-then-act session cannot be built on the plan machinery at all.** The
reuse this document claims is real only for the no-look case. `jarvis_plan`
refuses a plan from a tainted turn (`backend/jarvis_plan.py:191-194`,
`:202-203`), and the plan path refuses when
`watch.tainted or watch.read or watch.provenance or watch.app_context` is set
(`backend/jarvis_agent.py:1489-1490`). **`control_phone` sets `read`**, because
it is not in `_NOT_READING` (`backend/jarvis_agent.py:3984`, `:4295-4296`). So
the moment a session looks at the screen - even for a screenshot - a
`jarvis_plan`-based session is refused by the code as it stands. There are only
two ways forward, and both are owner decisions: **the session is new
machinery** (its own plan/verify loop, built and reviewed on its own terms), or
**it cannot look-then-act** - it runs the owner's words with per-step
verification, which is what this design is. The first draft claimed the second
while implying it had the first; it does not.

**DECIDED by the owner (2026-10-11), and this is the shape of the whole
feature: the steps come from HIS OWN WORDS ONLY.** Jarvis may **not** read the
phone's screen to suggest taps. He was offered the other path - option B above,
read the screen and propose the sequence - and **declined it**. So:

- the taint rule above stays **exactly where it is**: no rule change, nothing to
  loosen, screen-proposed steps still refused;
- **this is the difference between what this feature is and the Gemini-style
  thing he originally asked about** (the status at the top of this document
  quotes his own words, "similar to how Gemini on the Pixel 11 can take agentic
  control"). He asked for that, was shown the two ways it could go, and chose
  **the narrower one**: every tap comes from something he said himself, checked
  against the screen rather than chosen from it. A later reader should not have
  to reconstruct that - **the narrowing was deliberate, not a limitation that
  went unnoticed**, and it is recorded in two places: here, and in the closing
  questions section under "Decided by the OWNER";
- and the one thing that followed from it - whether the taint rule would even
  cover the array path if the screen were ever allowed to propose - is settled
  in the closing section, and is **moot while this decision stands**.

## 2. What if the screen changed between planning and running?

It will happen: a notification lands, an app updates, a keyboard opens. The
plan was approved against a screen that no longer exists.

**Before every step that sends input, the runner checks three things, and any
one of them failing STOPS THE WHOLE PLAN:**

1. **The app in front is the one the plan was made for.** The existing guard
   already reads `adb shell dumpsys window` and stops when it cannot tell
   (`backend/jarvis_android_control.py:255-286`). This design adds "and it is
   still the *same* app as when the plan was built", which is a comparison
   against a value recorded on the card, not a new kind of read.
2. **The element the step is about is still there**, and still says what it
   said: a `uiautomator dump` (§1) of the screen, looking for the node the
   step was planned against - its `resource-id`, its `content-desc` or text,
   and `clickable="true"`. All three appear in the project's own captured
   dumps (`docs/phone-checks-2026-10-09/dump-checks.xml:1` and its siblings
   show `resource-id`, `content-desc`, `clickable` and `password` on every
   node).
3. **The coordinates still point at that element**, within a small tolerance.
   A tap is a pixel pair; the element is the thing the owner approved.
   **The tolerance number is unverified and should be measured** on the
   owner's device before it is fixed.

**A step whose element cannot be found, or whose dump fails, stops the plan -
it does not fall back to tapping the old coordinates.** That is the same
posture as the existing guard's *"I could not tell" is not "it is safe"*
(`backend/jarvis_android_control.py:246-247`, `:278-280`).

**Stopping the whole plan is recommended over asking.** A mid-plan card would
have to show the owner the screen the next tap is about, and the honest thing
to show him is a screen he is not looking at; the project has already refused
exactly that shape once, for the step whose real values are not known when the
plan card is drawn - it is *"ALWAYS asked again individually"* rather than
decided blind (`backend/jarvis_plan.py:117-123`). So: the plan stops at the
step that no longer matches, says **which** step and **what** it saw instead,
and keeps every step it already did. Re-planning is then a fresh card, which
is a decision the owner can actually make.

## 3. Password and secret fields: refused or paused, never typed

**Never typed, and refused before the card is drawn, not at run time.** A
step whose target is a password field must not reach the plan at all, so the
owner never reads a card that offers to type his PIN.

**How it is known without an accessibility service.** The project has already
decided against one for the phone: *"An accessibility service is rejected (far
too powerful; restricted for sideloaded apps)"* (`docs/SCREEN-DESIGN.md:170-172`).
The check that does not need one is the dump itself: every node in
`uiautomator dump` carries a `password` attribute, as the project's own
captured dumps show (`docs/phone-checks-2026-10-09/dump-checks.xml:1`). A
step whose target node has `password="true"`, or whose `resource-id`/text
matches the password-field shapes, is refused. **Unverified: that the
attribute reads `true` on a real password field on this phone** - every
captured dump in this repository has `password="false"` throughout, because
none of them was a password screen. That is the first thing to measure.

Then, at run time, the same check runs again as part of §2's guard: if a
password field is on screen where the plan expected a button, the plan stops.
The PC's own screen feature already uses the identical two-place shape
(check when planning, check again just before acting) for `IsPassword`
(`docs/SCREEN-DESIGN.md:111-112`, `:62-65`).

## 4. Money, messages, and anything that leaves the phone

`backend/jarvis_android_control.py:36-40` already requires it: *"a step whose
own purpose is to make something leave the phone (send a message, post
something) must say so in its own `why`"*, and `_build_step` marks a step
heavy when it is `irreversible` or `leaves_machine` (`:120`).

**Recommendation: such a step may live inside a plan, but it always gets its
own card - it never rides on the plan's approval.** The machinery for exactly
this already exists: `PlanStep.needs_own_card` is true for a `risky` step
(`backend/jarvis_plan.py:124-126`), and the plan card says so on the line
itself (`:270-271`), and the runner raises that card when its turn comes
(`:339-357`). So the plan can end with "send it", the card lists it as a
step that will ask again, and the actual send is decided on its own with the
recipients and the words in front of the owner.

Two hard edges, both reused rather than invented:
- **A send can only ever be the LAST step.** If it were in the middle, the
  steps after it would run on the strength of a decision made about something
  else.
- **The send card is the existing control** - `control_phone` stays tier
  "ask" (`backend/rebuilt/jarvis-framework.toml:248`) and its risk row stays
  as written: irreversible, outbound, *"tapping the phone can send a message
  or complete a purchase"* (`jarvis-backend/jarvis_gate.py:300`).

**DECIDED by the owner (2026-10-11): a send may be the LAST STEP ONLY, on its
own card, showing the exact message and the exact recipient** - and **nothing
before it in the run may run without him seeing that card.** If the card cannot
be raised, the run does not happen (which is what §2 already does when a step
cannot be shown: it stops).

## 5. Locks, doors and alarms

The project's standing rule is that locks, doors, alarms and covers always get
a card of their own, never a place in a batch ("One smart-home card may cover
several named devices... Locks, alarms, doors and covers always get a card of
their own", `CLAUDE.md`, owner 2026-09-25).

**The phone equivalent, recommended: a "never inside a plan" list, checked
before the card is drawn.**
- Any step that changes a **lock, door, alarm or security setting** - the
  same rule, for the same reason: the tap's consequence is not visible in the
  tap.
- Any step inside **Android's own permission dialogs, the lock screen, or
  Settings' security pages**. A tap there grants something, and a granted
  permission outlives the plan.
- Any step inside an app on the owner's **"Never look at" list** (it starts
  with password managers, and the owner is asked to add his bank -
  `docs/SCREEN-DESIGN.md:112-115`). The phone-side screen feature already
  applies that list before anything is sent (`docs/SCREEN-DESIGN.md:141-142`);
  tapping is the same hazard with a worse consequence.
- The Jarvis app itself - already enforced, per step, today
  (`backend/jarvis_android_control.py:236-286`).

Such a step is not "banned" - it gets its own card, and the plan stops before
it if the owner would rather do it by hand. That is the honest shape: the
plan is for the sequence around it, not for the decision itself.

## 6. Staleness (rule 4): the floor, kept and delivered

Rule 4 says the app **blocks acting when the event stream is stale**, and the
project draws the line precisely: *"never held on a stale event stream or by a
waiting card: rule 4 blocks ACTING on a stale stream, and these only make
Jarvis do less"* (`docs/ARCHITECTURE.md:353-354`). The grace is 12 seconds on
both apps (`docs/ARCHITECTURE.md:1874-1875`), and the staleness decision is
made on the PC side of the app, not in a page
(`docs/ARCHITECTURE.md:1863-1865`).

**The owner kept the floor, and this design now delivers it (2026-10-11).** His
answer to the floor question was *"Approve, but make it stop when the link
drops"* - add the guarantee, keep the rule. So a session **stops dead when the
phone's link to the PC drops**, and the floor item *"never auto-approve
anything, and acting stays blocked while the event stream is stale"*
(`docs/RULE-FLEXIBILITY.md:45-46`) is left **exactly as written**. No entry in
that file is needed and none was made; the record of what was considered is
`docs/PHONE-PLAN-RULE-DRAFT.md`. Precisely what that means:

- **What "the link" is.** The phone's own live connection to the PC's API over
  the mesh - the link whose loss is what makes the apps hold their writes
  (`docs/ARCHITECTURE.md:1689`: "the apps hold every write on a stale link
  (rule 4)") and paints the hollow, not-connected icon
  (`docs/ARCHITECTURE.md:1893`). Its staleness is judged **on the PC**, not in a
  page (`docs/ARCHITECTURE.md:1863-1865`), and the grace is the project's own
  **12 seconds** - `OFFLINE_GRACE_MS` in `jarvis-link.js`'s `faceSignal`
  (`docs/ARCHITECTURE.md:1874-1881`).
- **Where the check happens.** At the **same per-step point that already
  re-checks the device serial**, before every command
  (`backend/jarvis_android_control.py:381-385`). One place, one order: the link,
  the device, the app in front, then the tap.
- **What "stops dead" means mid-step.** The step in flight **finishes** - a tap
  already dispatched cannot be recalled (§9) - and the loop **stops before the
  next step**, returning `ok: False` with its reason and the `done` /
  `not_run` lists (`backend/jarvis_android_control.py:340-353`, `:373-380`). The
  report says the link went stale, in those words.
- **A link that drops and comes back: the session is OVER. It does not resume.**
  Reasons, in order: the plan was approved against a screen a dropped link
  invalidates (the phone may have been unlocked, moved, or picked up by hand);
  while the link is down the phone's badge **and its Stop** are both gone, so a
  resumed run would be acting with no marker and no cancel (§13, §14); and
  re-planning is a fresh card the owner can actually decide - the same reason §2
  stops rather than guesses.
- **The honest limit, and it is the one that matters.** This makes the
  **staleness half of rule 4 true for a session**: acting no longer continues
  while the stream is stale. It does **not** make the taps depend on the stream -
  they are still local `adb` commands, and the stop is a **check the runner
  performs**, not a property of the taps. So with the project's 12-second grace,
  "stops dead" is delivered as **"stops before its next step, once the link has
  been stale for up to 12 seconds"** - **up to 12 seconds of taps can still go
  out after the link actually drops.** **DECIDED by the owner (2026-10-11): keep
  the project's own 12 seconds, unchanged, for this path as for the others.** He
  was offered a tighter window just for phone sessions and declined it. **He
  accepted that cost knowingly, and this sentence is not to be softened:** the
  number, the window and the consequence stay written down as he agreed them.

What the runner checks before each step, all at that one point:

1. **The link** (above). Stale, and the session stops dead.
2. **The phone connection.** Before **every** command, `run()` checks the
   device is still in `adb devices`'s own list and stops otherwise, *"rather
   than sending a tap intended for one phone toward whatever is connected
   now"* (`backend/jarvis_android_control.py:313-321`, `:381-385`). This design
   adds no second mechanism and removes none. Which address that device is
   reached at - the mesh one, never a home-Wi-Fi one - is §12.
3. **The same serial.** Recorded on the card as part of the plan
   (`Plan.device`, `:99-106`), and compared every step by that same check.

**The phone never decides any of this.** No rule, no refusal and no approval
is made on the phone: the phone is the thing being acted on, and its only job
is to be the same phone (see "What this is NOT").

**Because the session now stops dead when the link drops, the floor is KEPT and
nothing needs changing.** `docs/RULE-FLEXIBILITY.md` is untouched, `CLAUDE.md`
rule 4 stands as written, and no entry, switch or code change to the never-loosen
sets is needed. The record of what was considered, and why it turned out not to
be needed, is `docs/PHONE-PLAN-RULE-DRAFT.md`.

## 7. Stop everything must halt a running plan mid-sequence

It already can, and the mechanism is the reason it can:
`jarvis_task_control.checkpoint()` **consumes** the signal
(`backend/jarvis_task_control.py:91-124`) - *"Reading it is what acting on it
looks like, and a signal that has been acted on is spent"* - and `run()` reads
it **first, before the device check and before announcing the step**
(`backend/jarvis_android_control.py:355-373`, and the ordering's own reasons
at `:356-372`). One more read after the last step catches a Stop that arrived
too late (`:414-428`).

So a plan halts mid-sequence if:
- the PC's **Stop everything** hotkey is pressed: `stop_all()` asks the task
  layer to stop (`backend/jarvis_stop_all.py:188-210`, `:221-256`), which is
  the same route the task Stop button uses, and `docs/JARVIS-API.md:6341-6343`
  names "computer, browser or phone control" as exactly the kind of task that
  stops before its next step; or
- the phone's own Stop is pressed (the same route, per
  `docs/JARVIS-API.md:6341-6343`).

**What the design must add: nothing, except that the plan runs as a task with
an id.** If the plan is executed outside a task id, `checkpoint(None)` returns
None (`backend/jarvis_task_control.py:121-122`) and Stop everything cannot see
it - so "the plan is a task" is a requirement, not a detail. Registered
stoppers (`jarvis_stop_all.register`, `:108`) cover anything else the runner
holds open.

## 8. How many steps is too many?

**Recommendation: keep the existing 8 - do not introduce a second number.**
`backend/jarvis_plan.py:84` already says `MAX_STEPS = 8`, *"keep plans short"*,
and `propose()` refuses a longer one with a plain sentence
(`:211-213`). Re-using that cap means one promise to the owner, not two. **What
is being capped is the array itself:** `control_phone`'s own card has **no** cap
today (§18), so this 8 is a **new** limit this design imposes on a session -
taken from the project's existing number rather than invented, which is the
point.

Why 8 is the right size here, with this feature's own numbers: eight taps are
about eight seconds of `input` commands, plus up to ~2.33 s of verification per
step on this device (`docs/ANDROID-TOUR-2026-10-09.md:251-255`) - call it
**under half a minute** end to end. That is a sequence. A plan of thirty taps
is a session wearing a card, which is the thing
`backend/jarvis_android_control.py:8-11` refuses; and past a handful of steps
the owner cannot honestly check the list against what he meant, which is the
only protection the single card has.

## 9. Undo

**There is no undo. A real tap has already happened.** The button was pressed,
the message may be sent, the purchase may be made. This design will not imply
otherwise anywhere in the UI, the card or the result text.

What it does instead - all of it making the plan *smaller or later*, never
pretending a tap can be taken back:
- the card lists every command before anything runs (§10), so the decision is
  the whole decision;
- the sequence is capped at 8 (§8);
- a send, a lock, a door, an alarm, a permission or a secret keeps its own
  card (§3-§5), so the irreversible part is never bundled;
- Stop everything stops it between steps (§7);
- the result says exactly which steps ran and which did not - the shape
  `run()` already returns (`done` / `not_run`, `backend/jarvis_android_control.py:340-353`),
  so "what did it actually do to my phone" has an answer;
- the live status line names each step **without content** - the step number
  and a word from a fixed list, *"never the text typed or the device's
  serial"* (`:390-397`).

**Not proposed: an "undo" button that replays the inverse taps.** Half of the
commands in this feature have no inverse, and a button that sometimes works is
worse than a sentence that says it never does.

## 10. What the card literally shows

One card: the **existing** phone card, drawn by `describe()`
(`backend/jarvis_android_control.py:195-216`). Since the feature rides
`control_phone`'s own card rather than a plan (§18), **that** is the drawer - it
takes one idea from the plan machinery's card (`backend/jarvis_plan.py:262-287`):
a marked step says so on its own line. The two cannot drift, because the literal
`adb` line comes from the same place:

```
Jarvis would like to do this, in 4 step(s): open the calculator and add 1 + 2

  1. tap  - open the calculator
     adb -s 100.x.x.x:5555 shell input tap 540 2010
  2. tap  - the 1 key
     adb -s 100.x.x.x:5555 shell input tap 300 1500
  ...
  4. screenshot  - show me the result
     adb -s 100.x.x.x:5555 exec-out screencap -p

weight: heavy - any tap can send something or be impossible to undo, so the
whole plan is treated that way. The steps marked below are the ones Jarvis
flagged itself; an unmarked step is not a promise that it is safe.
Talks to your own paired phone over adb. Nothing goes to a third party.

Steps not marked above run once, right after this card, with no further
asking. Every marked step above still gets its own separate card when its turn
comes - approving this one never approves those.
If you say no: nothing happens on the phone; the goal is not attempted
```

- **One line per command**, the literal `adb` line in full - *"this is an adb
  command line, and summarising it defeats the point of printing one"*
  (`backend/jarvis_android_control.py:196-197`).
- **Its purpose**, the `why` the owner's own turn supplied.
- **What is at risk**: the one weight line, which is deliberately the
  *heavier* of the model's flags and the gate's own risk row
  (`:180-192`) - the gate classifies the whole action as irreversible and
  outbound (`jarvis-backend/jarvis_gate.py:300`).
- **What will ask again**, marked on the step's own line
  (`backend/jarvis_plan.py:270-274`).
- **The requests that were refused**, named, so a step cannot quietly vanish
  (`backend/jarvis_android_control.py:209-214`).
- **What "no" does** (`:215`).

For the owner deciding: this is the same text he sees today for a single
action, with the card count changed.

## 11. What "pass" means on the real phone (the first test)

A harmless task: **open the Calculator, work out 1 + 2, and show me.** It
changes nothing in any account, sends nothing, and types nothing, and it still
exercises every part of this design.

Pass means **all** of these, on the owner's own phone, watched by him:
1. the card appears **before anything runs**, and lists every command,
   including the tap coordinates;
2. **all** the taps land - the calculator shows `3` at the end;
3. the app-in-front check ran before each input step (the live line shows a
   step at a time, with no content) and the screenshot came back;
4. **an interruption test passes**: with the plan waiting at a step, the owner
   opens another app (or presses Stop everything), and the plan **stops
   without tapping**, saying which step and what it saw instead;
5. **a drift test passes**: at a step's guard, the screen is moved on (scroll
   or switch app) and the plan refuses to continue rather than tapping the old
   coordinates;
6. nothing on the phone changed outside the calculator.

Anything less than all six is not a pass. **Unverified until then:** the
`password` attribute reading `true` on a real password field, the coordinate
tolerance in §2, and the real cost of a dump-plus-tap cycle on this phone
(2.33 s per dump is measured, `docs/ANDROID-TOUR-2026-10-09.md:251-255`; the
rest is not).

## 12. How the steps reach the phone (the transport)

Measured on the owner's own phone, 2026-10-11, and the decision it settles.

- **Same Wi-Fi is not required, and it is not the path.** With the phone on Wi-Fi
  and the PC on the same home network, the PC reached the phone's adbd at its
  **NordVPN Meshnet** address on port 5555 and `getprop ro.product.model` came
  back `CPH2419` - a real answer over that path, so the transport works end to
  end. The phone's home-Wi-Fi address answered too; it is not the address this
  design uses.
- **Why the mesh address and not the home one.** It works whatever Wi-Fi either
  end is on, and it is what the owner decided on 2026-09-28: the phone connects
  over Tailscale or Meshnet only, because a home address would carry the pairing
  key unscrambled (`CLAUDE.md`). This document writes the address the way the
  rest of the repository does - `100.x.x.x`, the `100.64.0.0/10` block
  (`docs/ARCHITECTURE.md:67`, `docs/INSTALL.md:913`) - and never the literal
  number: `docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md:249` counts a real
  `100.x` address in this repository as something to have none of.
- **Meshnet, not Tailscale, today.** On this PC Tailscale is logged out (its
  adapter holds a 169.254 link-local placeholder and `tailscale status` says
  "Logged out"), and the phone has only NordVPN installed. The mesh actually
  carrying the traffic is Meshnet; nothing here depends on Tailscale being up.
- **How adbd gets into network mode, and what each way costs.**
  - *USB, once*: `adb tcpip 5555` over a cable puts adbd into network mode with
    no Android "Wireless debugging" toggle and no pairing code. Cost: **one
    cable connection per phone reboot**, because adbd returns to USB mode on
    restart. This is the way measured above.
  - *Android's own "Wireless debugging"*: cable-free, but it needs a **fresh
    6-digit pairing code every time it is enabled** and it picks a **new random
    port** each time, so the PC has to be told the current port.
- **The thing to avoid, said plainly.** While adbd was in TCP mode, port 5555
  was reachable on **both** the mesh address and the home-Wi-Fi address - an
  adbd in TCP mode listens on every interface the phone has. The owner's test
  reverted it immediately (`adb usb`, the Wireless debugging setting still `0`,
  the cable connection back). **So the PC connects to the mesh address only.**
  An adbd left listening on the home network is the specific thing this design
  treats as a fault rather than a convenience.
- **The rule that follows.** The plan builder accepts a device address only from
  the mesh block (`100.64.0.0/10`); a plan aimed at a `192.168.x.x`, `10.x.x.x`
  or `.local` address is refused with a sentence saying why. This is a check on
  the plan - it changes nothing in `run()`, whose per-step serial check
  (`backend/jarvis_android_control.py:381-385`) and "never the Jarvis app" guard
  (`:236-286`) already apply whatever the address.

## 13. Transparency: what is visible while it runs, and what is kept after

The owner asked for this in his own words (2026-10-11): *"i want this really
well refined, including making sure there is a excellent local ai model driving
my android phone, transparency, and the ability to easily cancel it."* This
section is the transparency half; §14 is the cancel half, §15 the model.

### While it runs

- **On the phone: a marker that does not go away while the plan is running.**
  The project already has exactly this shape for watching a screen - *"an eye on
  the tray icon, and a small always-on-top badge: 'Jarvis is watching · 24 min
  left · Stop'"* (`docs/SCREEN-DESIGN.md:106-110`) - and the phone equivalent is
  the same badge over the phone's own screen: **"Jarvis is tapping · step 3 of
  4 · Stop"**. It is drawn over whatever app is in front, so the app being
  driven cannot cover it. It reads `3 of 4`, so the owner can see how far along
  the plan is, and it disappears the moment the plan ends.
- **On the PC: the same state, from the same source.** `run()`'s `announce`
  hook is already wired to `jarvis_events.set_activity("working", text)`
  (`backend/jarvis_android_control.py:323-325`), and the line carries **the step
  number and a word from a fixed list - never the text typed and never the
  serial** (`:390-397`, which cites `ARCHITECTURE.md` section 6: an event
  carries "never content"). So the Brain window, the tray and the face show
  that Jarvis is controlling the phone, without the event stream becoming a
  second copy of anything private.
- **Unverified:** that an always-on-top badge is not hidden by Android over a
  permission dialog, a secure (`FLAG_SECURE`) screen or the lock screen. The
  badge is therefore the primary marker, not the only one - see §14.

### After it runs: the log, in plain words, kept locally

**It already exists and this design reuses it.** A plan runs as a job in the
job list (`backend/jarvis_tasks.py:1373` `from_plan`, `:1336` `plan_steps`),
and that machinery keeps, in local SQLite beside the backend:

- **one `run_events` row per action** - task, date, kind, title, detail
  (`backend/jarvis_tasks.py:324-327`, written at `:473`) - which is the
  plain-words list of what was done, in order; and
- **one `actions` row per card**, carrying **the words that were shown**
  (`shown`) and the hash of them (`shown_hash`), so the record says what the
  owner was asked and how he answered (`:126`, `:328-331`, `:636-689`).

**Where it lives and how it is read:** the rows are read by
`Store.events(task_id, limit)` (`backend/jarvis_tasks.py:478`) through the job
list's own routes - `GET /api/tasks`, `/api/tasks/act`, `/api/tasks/input`
(the route strings are pinned by `backend/test_tasks.py:664-676`) - so the
owner reads it in the job list both apps already have, on the PC and on the
phone. Nothing is sent anywhere: it is the same local store the rest of the
job list uses.

### What transparency cannot promise, said plainly

- **The screen is the private thing, not the log.** A verification look reads
  the phone's screen (an accessibility-tree dump, §2-§3), and the owner's
  question is whether that ends up stored. **Recommended, and stated as a
  rule: no screen contents are kept.** The verification stores only the
  answer - which element was expected, whether it was still there, and the
  app's package name - never the node texts it read. The only picture that
  survives is the one the owner explicitly asked for as a `screenshot` step
  (`backend/jarvis_android_control.py:152-157`), which is already read-only and
  already his.
- **So the log reveals what Jarvis did and why, not what was on the screen.**
  The `why` lines come from the owner's own words (§1). A person reading the
  log afterwards can see "step 2, tap, the Send button" - and cannot see what
  the message said.
- **Transparency is not detection.** The log is how the owner notices that a
  step went wrong; it is not how Jarvis notices. Jarvis notices only what §2's
  guard can compare.

### The failure mode transparency is the mitigation for

**The owner noticing, mid-plan, that the next step is about to do the wrong
thing.** The card was right when he approved it and the screen still matches,
so §2's guard sees nothing wrong - the plan is doing what it said, and what it
said was mistaken (the wrong button, the wrong row). Nothing in the machinery
can catch that: only a person watching can. That is precisely why (a) the
badge shows **which step of how many**, (b) the card lists the literal command
for every step (§10) rather than a summary, and (c) the cancel action in §14 is
one tap away at all times and does not ask a question.

## 14. Easy cancel, designed for the worst moment

The owner asked for *"the ability to easily cancel it"*. The worst moment is
not the tidy one: he is looking at the phone, the app in front is full-screen
or has its own overlay, and Jarvis is one step away from doing the wrong thing.

### The candidates, compared honestly

| Candidate | One action | Without looking | Without unlocking | Over a full-screen app | Already built |
|---|---|---|---|---|---|
| **PC "Stop everything" key** | yes | **yes** | n/a (it is the PC) | n/a | **yes** |
| **Badge on the phone with Stop** | yes | close (fixed place) | no (needs the phone awake) | **yes** | no (new) |
| Ongoing notification with a Stop action | yes | no (open the shade) | yes (lock-screen actions) | n/a (it is in the shade) | no (new) |
| Headset / media button, long press | yes | **yes** | yes | n/a | for Live only |

### The pick

**The PC's Stop everything key is the guaranteed cancel, and the phone's badge
Stop is the phone's own.** Reasons, in order:

1. **It is already built, and it already knows this kind of task.** Stop
   everything stops *"a running multi-step task (computer, browser or phone
   control) ... before its next step"* (`docs/JARVIS-API.md:6341-6343`), and
   it is *"never held on a stale event stream or by a waiting card"* and works
   *"while App lock is on"* (`docs/JARVIS-API.md:6337`). The owner is at the PC
   when a plan starts - the PC decides everything here (§6) - and it needs no
   new permission on the phone. **It reaches the plan only if the plan
   registered as a task with an id**: `checkpoint(None)` is `None`
   (`backend/jarvis_task_control.py:121-122`), so an unregistered run cannot be
   reached by the hotkey or by the phone's Stop. "The plan is a task" is a
   requirement, not a detail (§7).
2. **The badge is the same Stop where his eyes already are** while he watches
   the phone. It is the marker from §13 and the cancel in one control, which is
   the PC's own Watch pattern reused (`docs/SCREEN-DESIGN.md:106-110`), and it
   is drawn over the driven app so a full-screen app cannot cover it.
3. **The other two are fallbacks, not the pick:** the ongoing notification's
   Stop works from the lock screen but needs the shade open (so: not without
   looking), and the headset/media-button long press is genuinely hands-free but
   only exists today for Live (its reachability with no headset connected is
   **unverified**).

**Both the badge and the PC key end at the same place** - the task Stop route
`jarvis_task_control.request(task_id, "stop")` → `checkpoint()`
(`backend/jarvis_task_control.py:78-88`, `:91-124`) - so there is one stop
mechanism and three ways to reach it, not three mechanisms.

**Two honest costs to state before building it.** The badge needs Android's
**"draw over other apps"** permission, which is a real Settings grant the owner
gives once - the honest alternative is the notification, which needs no such
permission and cannot be covered by an app, only missed. And a plan that runs
while the phone is **locked** does not need either: the lock screen is a
different app in front, so §2's existing guard stops the plan by itself.

### What "stopped" means mid-step

- **A tap already dispatched cannot be recalled.** `adb shell input tap` is
  fire-and-forget: once it is on the wire, it lands. This design says so on the
  badge, in the result and in the log, and never implies otherwise (§9).
- **The step in flight is not abandoned - it finishes, and the loop stops
  before the next one.** The checkpoint is read **first, at the top of each
  step** (`backend/jarvis_android_control.py:355-380`), and it **consumes** the
  signal (`backend/jarvis_task_control.py:91-124`), so the stop lands exactly
  between two steps. The runner abandons the remaining steps, not the current
  one.
- **How it confirms it stopped:** `run()` returns `ok: False`,
  `reason: "stopped by request"`, and the `done` / `not_run` lists, so "what did
  it actually do to my phone" has an answer
  (`backend/jarvis_android_control.py:340-353`, `:373-380`); the badge and the
  notification clear; the PC's live line stops; and the run-event row says the
  same thing in plain words (§13). A Stop that arrives after the last step is
  still reported - `late_signal` (`:414-428`) - rather than silently ignored.

### Cancelling is not the same as turning the feature off

- **Turning the feature's own switch off is immediate, with no card** - the
  project's rule for every switch (`CLAUDE.md`, 2026-09-24 onwards), and the
  plan card's own gate stays at tier "ask" (`run_plan`,
  `backend/rebuilt/jarvis-framework.toml:250`).
- **Cancelling a running plan is the Stop action above.** A plan is one shot
  with a fixed end, so there is nothing left running to cancel once it ends;
  the design deliberately has no "session" that could be left on.

## 15. The model that drives it (the part that decides whether this works)

### Local is a constraint, not a preference

Rule 1 is that anything touching email, files, credentials or stored memory
stays on the local model. **A phone screen is as private as anything this
project handles.** So whatever turns the owner's words into `adb` commands
runs on this PC, on loopback, and nothing about the phone's screen goes
anywhere else. The project already expresses this for the phone's own screen
feature: a raw phone screenshot is kept away from any lane that is not the
owner's own - the chat router still refuses to send one to the "vision" lane,
"because a raw picture must never reach any model before `clean_picture` has
run" (`docs/SCREEN-DESIGN.md:29-32`).

### Grounding is the hard part, and it must not be assumed

Turning *"tap Send"* into a coordinate is **grounding**, and it is a different
skill from chatting. The current everyday lane model is an 8B model chosen for
chat; nothing in this repository measures whether it can ground a screen
element, and **this design does not assume it can.** What must be measured
before the feature can be trusted:

| What | How it is measured | "Good enough", recommended |
|---|---|---|
| Right element, first try | a fixed suite of screens captured from the owner's own phone, each with the target named | **>= 90%** of steps - the same bar the plan card already has to clear (`backend/jarvis_plan.py:94`) |
| Dangerous taps | the same suite, with password fields, permission dialogs, the "Never look at" apps and the Jarvis app deliberately present | **0** - zero tolerance, the shape the injection suite already uses (`backend/jarvis_plan.py:488-491`) |
| Honest refusal | screens where the named target is **absent** | **0** invented targets: it says it cannot find it, and the plan stops |
| Cost | seconds per grounded step, dump included | reported, not guessed - the dump alone is **2.33 s** (three runs: 2.33 / 2.29 / 2.37 s, `docs/ANDROID-TOUR-2026-10-09.md:251-255`) |

The machinery to run that suite the project's own way already exists:
`tools/tool_eval/ollama_tool_eval.py` writes the results file that
`jarvis_plan.enabled()` reads, and the plan card stays **off** until a real run
on this model clears its bar (`backend/jarvis_plan.py:87-95`, `:453-492`;
`backend/rebuilt/jarvis-framework.toml:246,250`). A grounding suite belongs in
that same place, with the same "off until measured" rule. **No number in the
table above has been measured yet.**

### What it contends with, and whether it is the chat model or a second one

Both cards are occupied and this is already written down for a different
feature: *"The everyday chat runs on the 12 GB RTX 2060 and fills most of it"*
and *"Two things cannot sit on one card, so something has to give - and there
are exactly three sensible ways to give"*
(`docs/PICTURE-CARDS-DESIGN.md:8-12`). The same three ways apply here:

| | What it does | What it costs |
|---|---|---|
| **A** | the existing lane model grounds as well as it chats | free in memory; unmeasured, and it is a chat model first |
| **B** | a **second, specialist grounding model** on the 12 GB card, with the chat unloaded before a plan and warmed back after | a few seconds of chat reload per plan; the long conversation is kept |
| **C** | a small grounding model on the 8 GB card, chat untouched | the weakest grounder, but the everyday chat never moves |

**Recommended: B, behind its own switch, off until *this feature* is
measured** - the project's own rule (`CLAUDE.md`: a feature that uses the
second card keeps its own switch, off until that feature is measured), and the
same shape picture-card already ships (three ways, each its own switch,
`docs/PICTURE-CARDS-DESIGN.md:16-26`). Two hard constraints carried over from
that work, because they have already produced wrong measurements here: a
model is pinned by the card's **UUID, never a number**, because
`CUDA_VISIBLE_DEVICES` alone falls back to Vulkan and lands on the other card
(`docs/PICTURE-CARDS-DESIGN.md:42-54`); and **one GPU-heavy thing at a time** -
the measurement refuses to run while a model it did not expect is resident
(`:70-71`).

### The research, landed (2026-10-11): size is not the bottleneck, grounding is

Licences below were read from each project's own LICENSE file or its API
metadata, not from a badge.

**The driver: `AutoGLM-Phone-9B`.** Purpose-built for driving Android over
**plain adb**; **MIT**; and converted by the **llama.cpp team itself**
(`ggml-org/AutoGLM-Phone-9B-GGUF`): Q4_K_M **5.74 GB** + mmproj-Q8_0
**0.91 GB** = **6.65 GB**, architecture `glm4` (registered in llama.cpp). It
supports **remote adb** (`--device-id <mesh-ip>:5555`), which is exactly this
project's transport (§12). **Put it on the 12 GB card.**

**Grounding is the hard part, and general models are bad at it.** ScreenSpot-Pro
figures: purpose-built **Holo2-4B 57.2%** and Holo1.5-7B 57.9%; general
**Qwen3-VL-4B-Thinking 41.4%**, **Qwen3-VL-8B 38.5%**, Qwen2.5-VL-7B 29.0%.
So **the everyday lane model must not be assumed capable of grounding**, and
the answer to a weak grounder is not a bigger general model. **Recommended
split: the existing 8B/9B stays the planner, and a 2-4B grounding specialist
sits on the same card** - **Holo2-4B** (Apache-2.0, Q4_K_M + mmproj
**2.95 GB**) or **GUI-Owl-1.5-2B** (MIT, **1.44 GB**).

**Pull the prompt format, not the code.** **Open-AutoGLM is Apache-2.0**, and
its action vocabulary - `Tap`, `Type`, `Swipe`, `Back`, `Home`, `Long Press`,
`Double Tap`, `Launch`, `Take_over` - maps almost 1:1 onto
`jarvis_android_control`'s own actions, while its `confirmation_callback` and
`takeover_callback` hooks map onto approval cards. **OmniParser's
`icon_detect_v3` is MIT** and gives the screenshot-to-numbered-boxes layer; the
older YOLOv8 `icon_detect` is **AGPL-3.0 and must never be used here**.

**Licence traps, named so nobody pulls them later:** `droidrun/mobilerun` is
MIT but its Android app `mobilerun-portal` is **AGPL-3.0**, and the MIT half is
useless without it - **INSPIRE ONLY**; **AutoDroid is GPL-3.0**;
**ADBKeyBoard is GPL-2.0**; **Holo1.5-3B and Qwen2.5-VL-3B are Research
licences** (Holo1.5-7B is Apache-2.0 instead).

**Two traps that would break a standing rule.** Ollama's `qwen3-vl:235b-cloud`
is a **CLOUD** tag: it sends screenshots off this machine and breaks rule 1 -
only the local `2b/4b/8b` tags may be used here. And `mobilerun` ships
**telemetry on by default** (`posthog`, `arize-phoenix`, `--tracing`).

**One measured detail that pushes toward pixels.** This project's own captured
dump has **49 nodes and not one `content-desc`** (`docs/phone-checks-2026-10-09/dump-checks.xml`),
so a text-only node tree can be thin on this phone - which is an argument for
the screenshot-and-numbered-boxes layer (OmniParser's MIT `icon_detect_v3`)
rather than a tree-only grounder, on the terms §2 already sets for reading the
screen.

### Both cards, "so it could be bigger" - the owner's question, answered

Mechanically yes: the existing both-cards mode already does exactly that -
`big-coder.patch`, measured **49/49 layers, zero spill at 28,672 tokens** - at
the cost of **Jarvis going offline while it is loaded**. **But bigger is not
what fixes this.** Grounding, not size, is the bottleneck, and the figures above
show a purpose-built 4B beating a general 8B at it by roughly half again. The
honest use of both cards is a **big planner plus a small grounder**, measured -
not one giant model.

### What is still owed before any model drives this

The grounding suite itself, run on this PC through the project's own gate
(`tools/tool_eval/ollama_tool_eval.py` → `jarvis_plan.enabled()`), against the
bars in the table above: >= 90% right element first try, **zero** dangerous
taps, **zero** invented targets where the target is absent, and the cost per
grounded step reported. Until that exists, the feature's gate stays closed
(§ "What has to be true before any of it is built"), and the honest reading of
the numbers above is that grounding is the thing to measure - the model names
are a starting point, not a result.

### A wrong tap is a real tap, so the plan is what limits the blast radius

There is no undo (§9). What keeps a grounding mistake from being expensive is
the shape of the plan rather than the quality of the model:

- **The model never chooses free-form taps from the screen in v1** - the steps
  come from the owner's own words (§1), so a wrong tap is a wrong translation
  of a *decision he made*, not a decision the model made for him;
- **every literal command is on the card** before anything runs (§10), so a bad
  translation is visible at the moment he can still say no;
- **the cap is 8** (`backend/jarvis_plan.py:84`, and the same 8 again for the
  job list at `backend/jarvis_tasks.py:100`), so there is a small, countable
  number of chances to be wrong;
- **per-step verification** stops the plan the moment the screen is not what it
  was (§2), which is what catches a mis-aimed first tap before the second one
  repeats it;
- **the irreversible things are not in the batch** - a send, a lock, a door, an
  alarm, a permission or a secret keeps its own card (§3-§5), so the blast
  radius of a bad step is a wrong tap on an ordinary screen, not a message sent;
- **the run is recorded** (§13), so what actually happened is answerable
  afterwards;
- **no standing grant**: one plan, one card, one end (§What this is NOT).

## 16. Deleting: its own switch, off by default

The owner asked for this directly (2026-10-11): *"have the delete function be a
toggle in settings for this that is disabled by default."*

### One switch, off by default - and it is not a rule relaxation

**Corrected after the owner kept the floor (§18).** There were two switches in
the earlier revision. One of them no longer exists:

1. ~~**The phone agent itself.**~~ **Gone.** It was only ever there to carry a
   floor change in `docs/RULE-FLEXIBILITY.md`, and the owner kept the floor
   instead. Nothing is loosened by this feature: `control_phone` is already tier
   "ask" (`backend/rebuilt/jarvis-framework.toml:248`) and its card already
   carries a whole list of commands (`backend/jarvis_agent.py:1545-1561`), so
   the feature **rides the card that already exists** and needs no gate action,
   no "What asks first" row and no change to `HARD_LIMITS` / `MUST_ASK` (§18).
2. **"Let Jarvis delete things".** His own request (2026-10-11), and the only
   switch left: its own row in the "What asks first" page
   (`backend/jarvis_asks_first.py:210-211`), **off by default**, with the shape
   the project already uses for "Lights, plugs and fans without a card":
   *"Asks first unless you turn on the switch below (off by default)"* (`:1642`),
   `set_lights()` (`:1712`), `lights_on()` (`:1730`) - off immediate, no card.
   - **Turning it on is NOT a loosening of any rule this repository holds.** It
     relaxes a restriction **this design adds**: with the toggle off, a
     deletion-shaped step keeps its own card; with it on, such a step may ride
     the approved batch. Today, a delete tap inside an approved array already
     rides the same card, so nothing in the project's rulebooks changes - which
     is why **there is no entry for it in `docs/RULE-FLEXIBILITY.md`** and no
     floor change is involved (§18).
   - Because it still *reduces* asking, it keeps the safe **form** of a
     loosening even though it is not one: off by default, one card plus the
     screen lock (phone) or Windows Hello (PC) to turn on, immediate to turn
     off. Its "What asks first" row must not imply a rule entry exists.

The toggle is a preference about **one named class of step**, never a session
permission: switching it on does not make a session "allowed to delete" - it
lets a **recognised** deletion-shaped step be part of an approved batch at all.

**DECIDED by the owner (2026-10-11): keep the toggle, exactly as designed.** He
was offered the stricter alternative - drop the toggle, so that every deletion
always asks - and **chose to keep it**. The rule of this feature, in his words'
terms:

- **Toggle off (the default): a deletion always gets its own card.**
- **Toggle on: a *recoverable* deletion may happen inside the run.**
- **Permanent deletions and anything that closes or erases an account always get
  their own card, whatever the toggle says** - Empty trash, Clear history, Clear
  data, Uninstall, Delete for everyone, Erase, Forget this device, and account
  deletion refused outright (the verdict table above).
- It is recorded **as a preference, not a rule entry**: it relaxes no repository
  rule, so its "What asks first" row must not imply that one exists (§18).

### What counts as "delete": a positive list

The organising question is not "does the word appear" but **could the owner get
it back, and from where**. The verdicts, each with its reason:

| On-screen shape | What it usually does | Get it back? | Verdict |
|---|---|---|---|
| **Delete** (a file, photo, note, message) | usually moves to Trash / Recently Deleted | usually yes | **covered by the toggle** |
| **Remove** | takes it out of a collection; the thing itself usually stays | yes | covered |
| **Remove from album** | untags it from one album | yes | covered |
| **Trash / Move to Trash / Move to Bin** | the recoverable step itself | yes | covered |
| **Archive** | hides it from the main view; the item stays | yes | covered - it changes where he will look for it, so it is worth the switch, but nothing is lost |
| **Clear cache** | regenerable data, rebuilt on demand | yes | covered |
| **Clear history** | gone from the owner's view | mostly no | **own card** |
| **Clear data** | the app's own local state | no | **own card** |
| **Empty trash / bin / recycle bin** | burns the copies | no | **own card** |
| **Uninstall** | the app and its local data | app yes, its data no | **own card** |
| **Delete for everyone** | destroys the copy on the other side | no, and it reaches another person | **own card, and only as the last step** (§4: it is a send) |
| **Erase** (erase all content, erase device) | everything | no | **own card; the device-wiping ones refused outright** |
| **Forget this device** | unpairs a device record | only by re-pairing; can lock him out | **own card** (§5 already keeps security settings out of a plan) |
| **Deleting or closing the ACCOUNT** | ends the account itself | no, often needs support | **refused outright, never covered by the toggle** |

**Where I argue with the Lead's recommendation: I agree with all three limbs**
(recoverable ones under the toggle; a permanent delete keeps its own card even
when the toggle is on; an account deletion refused outright and never covered).
Two refinements I would add, with reasons:

1. **"Delete for everyone" is not merely permanent - it reaches another
   person.** So it is a send as well as a destruction: own card *and*
   last-step-only, which §4 already requires of anything that leaves the phone.
2. **An unclassifiable delete is treated as permanent.** If the runner cannot
   positively place a step in the recoverable list above, the step does **not**
   get the toggle's cover - it keeps its own card. This is what makes the
   honest answer in the next part safe: the failure direction of a missed
   recognition is an extra card, not a silent permanent delete.

### The card's own words when the toggle is turned on

Not "allow deletions". The card says **this sentence**:

> **With this on, an action that cannot be undone may happen inside a session
> without you seeing it first.**

### Is it enforceable? Three layers, and where each one fails

The owner's question, answered honestly: **without an accessibility service,
three layers of evidence exist, and none of them is complete.**

1. **The step's own declared purpose.** The step's `why`, plus a `deletes`
   flag the plan builder must set. `backend/jarvis_android_control.py:36-40`
   already requires a step whose purpose is to leave the phone to say so in its
   own `why`, and `:120` already marks a step heavy from booleans the caller
   supplies - this is the same shape, not a new mechanism.
   **Where it fails:** it is the model's self-report. A model that does not
   recognise a trash-can icon simply does not set the flag. (What limits the
   damage: a plan shaped by outside text is already refused outright, §1, and
   the card shows the `why` the owner's own words produced.)
2. **The screen's own words around the tapped element** - the node's text, its
   `content-desc`, and the text of what is near it or on the dialog
   (`uiautomator dump`, §2).
   **Where it fails:** the word is in another language; the icon has no word at
   all (a bare trash can, `content-desc=""`); the word appears where nothing is
   destroyed ("Remove from favourites", a help article); **a swipe-to-delete
   gesture has no node to read at all**; and **a long-press menu shows "Delete"
   only after the long press**, so the word is not on the screen when the plan
   is checked.
3. **The app's own confirmation dialog**, read by a dump after the step.
   **Where it fails:** many apps never ask; some ask without the word
   ("Are you sure?"); and the ordering problem is the real one - **the tap has
   already happened**. A confirmation dialog is the app offering a way out, and
   Jarvis must never take it, because that would be the machine answering the
   app's own approval. So when an unexpected dialog appears the plan **stops**
   and hands it to the owner.

**So, said exactly: the toggle is a strong guard, not an airtight one.** It
reliably refuses the deletion-shaped steps it can *recognise* - a declared
purpose, a recognised word next to the tap or on the dialog. It cannot promise
that every deletion-shaped action is recognised. **Two shapes are missed by
construction, and the design does not paper over either: a long-press menu that
reveals "Delete" only after the press, and a swipe-to-delete that has no node to
read at all** (layer 2 above). **Residual risk, plainly:**
with the toggle **on**, an unrecognised permanent delete could run inside an
approved plan without its own card. With the toggle **off**, the same
recognition miss produces the opposite outcome - a harmless step is refused -
which costs a card, never data. That asymmetry is why off is the default.

### When the toggle is off and a delete step appears

**Refused, named, in plain words - never silently skipped, and never retried
another way** (not as a swipe, not on a different button, not by long-pressing
where the word did not appear).

- **At plan time**, the step never becomes a command. It appears on the card in
  the existing refused-list shape (`backend/jarvis_android_control.py:161-177`,
  printed at `:209-214`), with the plain reason - so the owner can turn the
  toggle on, or do that step by hand, and either way he is told rather than
  left to notice.
- **At run time** - a delete the plan did not carry, seen by layer 2 or 3 - the
  design **stops the plan** rather than carrying on. The rest of the plan was
  written as a sequence whose later steps may exist to finish that very
  deletion, so continuing would act on a screen that has already diverged from
  what was approved; that is §2's rule, applied again. Steps already done stay
  done, and the result names the refused step.

### Where this sits among the design's other limits

- The toggle is a guard, not a guarantee (§ above), and its own failure
  direction is chosen to cost a card rather than data.
- **No undo** (§9) applies to every deletion the toggle ever covers - a
  "recoverable" delete is recoverable *in the app that did it*, on its terms and
  for as long as it keeps the copy. This design cannot restore anything.
- An unrecognised delete is treated as permanent (§ above).
- The full picture of what the owner can and cannot see afterwards is §13.

## 17. What is promised, and what is not (the owner's decision, 2026-10-11)

The owner's words, after being shown what the code cannot hold: **"Still change
the floor, with only enforceable promises."** That splits this document's
exclusions into two lists, and the second one goes on the card itself.

### PROMISED - each one named with the mechanism that holds it

| Promise | The mechanism that holds it |
|---|---|
| **Never taps inside the Jarvis app itself** | Real code, checked before every input step: `backend/jarvis_android_control.py:236-286` (any package under `com.jarvis.`, and "could not tell" also stops) |
| **The app in front stays the same package** | The same per-step check, compared against the package the plan recorded when it was built (§2) |
| **A step only runs after its target is found again on the current screen** | The per-step dump and comparison in §2; when it does not match, the plan **stops** rather than tapping stale coordinates |
| **Stop lands between taps, and both the phone's Stop and the PC's hotkey reach it** | `jarvis_task_control.checkpoint()` consumes the signal (`backend/jarvis_task_control.py:91-124`), read first at the top of each step (`backend/jarvis_android_control.py:355-380`). **Only if the plan runs as a task with an id** - `checkpoint(None)` returns `None` (`:121-122`), so a plan without a task id cannot be stopped by either |
| **A hard time and step limit, not "about"** | Steps capped at 8, the project's own number (`backend/jarvis_plan.py:84`, and again at `backend/jarvis_tasks.py:100`); the time limit is a fixed number, chosen before anything is built |
| **A visible marker while it runs** | The badge (§13) and the PC's content-free live line (`backend/jarvis_android_control.py:390-397`, `:323-325`) |
| **Never touches hidden memory lists or app lock** | Not on this path: the agent has no route to either, and its log is the job list's own (§13) |
| **Everything local** | `adb` to the owner's own phone over the mesh (§12), and a local model (§15). Nothing leaves the machine |
| **If the phone's link to the PC drops, the session stops dead** | A per-step check at the same point that re-checks the device serial (`backend/jarvis_android_control.py:381-385`), against the PC's own link-staleness signal (judged on the PC, `docs/ARCHITECTURE.md:1863-1865`; the apps' 12-second grace is `OFFLINE_GRACE_MS`, `docs/ARCHITECTURE.md:1874-1881`). The step in flight finishes, the loop stops before the next one, and the report says the link went stale. **A link that comes back does not resume the session.** The floor's own half of rule 4, delivered rather than excused (§6); the window is the project's 12 seconds and is stated, not hidden |

### NOT PROMISED - guesses, whose failures this project already documents

Stated as limitations rather than protections. The owner is accepting these
**with his eyes open**, so this list is deliberately explicit.

| Not promised | The mechanism that fails |
|---|---|
| **A password box is never typed into** | Recognised only from the dump's `password` attribute - which **has never once appeared set** in this project's own capture: 49 nodes, every one `password="false"` (`docs/phone-checks-2026-10-09/dump-checks.xml`) |
| **A 2FA / one-time-code box is never typed into** | **Not enforceable.** An OTP box is an ordinary numeric field, nothing marks it, there is no accessibility service, and `_SAFE_TEXT` permits digits (`backend/jarvis_android_control.py:76`) - so `input text 123456` is a command this module will happily build |
| **A bank app is never opened** | A **documented heuristic, not a promise** (`jarvis-client/app/src/main/java/com/jarvis/client/data/ScreenNever.kt:9-17`), whose false negative is **asserted by its own test** (`jarvis-client/app/src/test/java/com/jarvis/client/NotificationAllowListTest.kt:55-61`). And the heuristic lives **on the phone** and needs the app's store category, which the PC runner driving `adb` does not have |
| **A spending or sending button is never pressed** | **Wishful.** The only reader of a button's meaning is the model's own self-report, and this module already records it failing exactly there: *"a plan whose Send click the model left unflagged read 'weight: normal' while the notice and the risk line said the opposite"* (`backend/jarvis_android_control.py:180-192`) |
| **A step stays inside one app** | Only in the weak sense: the check is **package-only**, so a browser is one package and every website is inside it, and a spend-or-send sheet drawn **inside** an allowed app passes by construction. That is the whole attack, and it needs no attacker |
| **"Delete" is recognised** | Misses two shapes **by construction**: a long-press menu that shows "Delete" only *after* the press, and a swipe-to-delete that has no node to read at all (§16) |

**Of everything on the promise list above, exactly TWO items were ever
enforceable, and these are they** - a reader should be able to name them
without reading anything else:

1. **Never tapping inside the Jarvis app itself** - real per-step code, not a
   guess: `backend/jarvis_android_control.py:236-286` refuses any package under
   `com.jarvis.`, and treats "could not tell" as a stop too.
2. **The step and time caps** - hard numbers, not "about": 8 steps
   (`backend/jarvis_plan.py:84`, `backend/jarvis_tasks.py:100`) and a fixed
   time limit chosen before anything is built.

**Every other exclusion in this design is a guess with a documented failure
mode**, which is why the second list is on the card rather than in a promise:
the password box, the 2FA box, the bank app, the spending-and-sending button,
and "stays inside one app". The first draft listed those as protections; they
are not.

### The card's own words (given to the owner for approval)

> **Jarvis recognises a password box, a bank, and a spending or sending button
> only by guesses its own code documents as unreliable. With this on, a tap
> Jarvis has misread can send a message, spend money, or delete something, and
> stopping it lands between taps.**

Not "allow phone sessions". That sentence is the whole disclosure, and §16's
delete switch carries its own one as well.

### The floor is KEPT - nothing to change, and no entry needed

The owner was offered the floor change and **declined it**: *"Approve, but make
it stop when the link drops."* So:

- The floor item (`docs/RULE-FLEXIBILITY.md:45-46`) stands **exactly as
  written**, `docs/RULE-FLEXIBILITY.md` is untouched, and **no entry 004 is
  needed** - not deferred, *not needed*;
- this design **delivers** the floor's second half rather than asking to be
  excused from it: the session stops dead when the link drops (§6, and the
  promise in the table above);
- the record of what was considered, and why it was not needed, is
  `docs/PHONE-PLAN-RULE-DRAFT.md`, now headed *"considered and NOT needed"*,
  stating that nothing in it is pending.

The code facts that made a switch impossible (`HARD_LIMITS` and `MUST_ASK`
naming `control_phone` and `run_plan`) mattered **only because a switch was
contemplated**. With nothing loosened, no code change to those sets is needed
either - §18.

## 18. What this no longer needs, and the one question left

### No new switch is needed - and that is not a loophole

`control_phone` is **already** tier `ask`
(`backend/rebuilt/jarvis-framework.toml:248`) and its card **already** carries a
whole list of literal commands in one call
(`backend/jarvis_agent.py:1545-1561`). A card listing every tap up front
**already exists**; it is the array card. Nothing in this design loosens
anything - every addition it makes is **stricter** than today's behaviour
(per-step verification, the link stop, the exclusion lists, a hard time limit,
the local record, the badge and Stop).

Therefore:

- **The phone-agent switch collapses into nothing.** It existed only to carry
  the floor change. With the floor kept there is no gate action, no "What asks
  first" row, and **no code change to `HARD_LIMITS` / `MUST_ASK`** - the code
  change the previous revision was about. The feature **rides the card that
  already exists.**
- **No loosening card and no Windows Hello step** are needed for the session
  itself. What the owner still decides is exactly what he decides today: he
  reads the card and says yes or no.
- **What changes is code, not permission**: the per-step checks and the link
  stop are new work inside the runner, and the owner's multi-step-safety
  decision (`CLAUDE.md`, 2026-09-27) is honoured in spirit by gate 5 rather than
  by a gate on the machinery (§ "The six build gates", below).

### The delete toggle was never a rule relaxation - and the owner has now settled it

§16 presented the delete toggle as a loosening (one card plus the fingerprint to
turn it on). That framing is wrong in an important way: **it relaxes no rule in
this repository.** With the toggle **off**, the design's own added caution is
"a deletion-shaped step keeps its own card" - a restriction *this document*
invents, because today a delete tap inside an approved array already rides the
same card. Turning the toggle on therefore relaxes **this design's extra
caution**, not a project rule, so it **cannot have an entry in
`docs/RULE-FLEXIBILITY.md`** (there is nothing there to relax) and needs no
floor change.

**The two ways forward were put to him (2026-10-11), and he chose the first:**

1. **CHOSEN - keep it as a design preference:** off by default, its own card plus
   the screen lock or Windows Hello to turn on (the safe *form*, even though the
   reason is not a rule entry), and off immediate with no card. Its "What asks
   first" row must **not** imply a rule entry exists.
2. **Declined - dropping the toggle** so that every deletion always asks:
   simplest, no setting, nothing to explain, at the cost that a batch containing
   a harmless deletion cannot be approved in one go.

So the switch is kept **knowingly**, as a preference about how much extra
caution this design adds - not as a loosening, and not quietly: nothing in this
document or in the "What asks first" page claims a rule entry for it.

### The steps may still come only from the owner's own words

The owner's choice changed **nothing** about where a step may come from. That is
governed by the plan-taint refusal (`backend/jarvis_plan.py:191-203`, and the
plan route's own check at `backend/jarvis_agent.py:1489-1490`), and
`control_phone` **counts as a reading tool** because it is not in
`_NOT_READING` (`backend/jarvis_agent.py:3984`, `:4295-4296`). So
**screen-proposed steps remain refused exactly where they were**, and this design
does not touch that rule: v1 takes the steps from the owner's own words (§1), and
asking Jarvis to read the phone's screen and *propose* them is a separate
decision he has not made.

**One honest subtlety, stated rather than assumed:** that refusal is enforced on
the **plan** route. v1 here never reads the screen to propose, so the question
does not arise - but if the owner ever wants the screen to *propose* steps
through `control_phone`'s array instead of a plan, whether the taint rule covers
that path has to be settled in code first, not assumed. Flagged here so it is
not discovered later.

### The six build gates, after the owner's choice

- **Gate 1 falls away** - the plan card's own `tools/tool_eval` bar. It existed
  only because this design rode `jarvis_plan`, and it no longer does. What does
  **not** fall away is the reason the owner set it: measure the multi-step
  behaviour before trusting it, which is what gate 5 does for grounding.
- **Gate 2 changes shape**: "the tiers stay ask" is now trivially true rather
  than a prerequisite, because nothing is loosened.
- **Gates 3 and 4 stand**: the three unverified facts measured on his phone, and
  the first test run by him, watching.
- **Gate 5 stands**: the driving model's grounding measured (§15).
- **Gate 6 stands**: the delete toggle's limits accepted as written (§16) - and it
  now carries the open question above.

## What this is NOT

- **Not a live session, and not scrcpy.** No mirror, no stream, no session
  that keeps acting while it runs - the reason is quoted at the top of this
  document from `backend/jarvis_android_control.py:8-11`.
- **Not "always allow this task".** There is no standing permission of any
  kind, for any sequence, at any point. A saved recipe (option C in §1) is
  re-shown as a card on every run or it is not built.
- **Not a screen mirror and not a video feed.** The only picture is the
  existing `screenshot` step, on the existing terms
  (`backend/jarvis_android_control.py:152-157`).
- **Not decided on the phone.** The PC builds the plan, checks it, runs it and
  stops it. The phone is what is acted on. (Unchanged from today.)
- **Not an accessibility service.** Rejected for the same reason the project
  rejected it for the phone's screen feature (`docs/SCREEN-DESIGN.md:170-172`).
- **Not a delete permission folded into the agent's switch.** "Let Jarvis
  delete things" is its own setting, off by default, and a session runs without
  it (§16). With it on it covers only deletions the owner can undo in the app
  that did them; a permanent delete keeps its own card; deleting an account is
  refused outright.
- **Not a cloud model.** Whatever drives this is local, on loopback (§15, rule
  1), and the phone's screen is read on this PC and goes nowhere.
- **Not a weaker live-session ban.** `plan()` still runs nothing
  (`backend/jarvis_android_control.py:161-163`), `run()` still executes only
  the enumerated commands with `approved` having no default
  (`:306-333`), and no new capability is added: the same commands, decided
  once instead of one at a time.
- **Not built.** No code, no patch, no new module, no route.

## What has to be true before any of it is built

**Five stand. One fell away when the owner kept the floor (§18).**

1. ~~The plan card's own gate~~ - **fallen away.** It existed only because this
   design rode `jarvis_plan`, and it no longer does: the feature rides
   `control_phone`'s existing card (§18). **The reason the owner set that gate
   does not fall away** - measure the multi-step behaviour before trusting it -
   and that is what item 5 below does for grounding.
2. **The tiers stay "ask"**: `control_phone` (`jarvis-framework.toml:248`) and,
   if anything still uses it, `run_plan` (`:250`). Now trivially true rather than
   a prerequisite: nothing is loosened, no gate action is added, and
   `HARD_LIMITS` / `MUST_ASK` are not touched.
3. **The three unverified facts in §3 and §11** are measured on the owner's
   phone first.
4. **The first test (§11) is run by the owner, on his phone, watching.**
5. **The driving model is measured, not assumed** (§15): a grounding suite in
   `tools/tool_eval`, clearing the >= 90% bar with **zero** taps on a password
   field, a permission dialog, a "Never look at" app or the Jarvis app, on the
   model that will actually drive this. Until then, nothing here runs. The
   model research has landed (§15) and names a driver and a grounder.
6. **The delete toggle's limits are accepted as written** (§16): it is a strong
   guard, not an airtight one; off is the default; and the card that turns it
   on carries the sentence that says an action that cannot be undone may happen
   inside a session without the owner seeing it first. **The owner has kept the
   toggle itself** (closed question, below), as a preference rather than a
   loosening (§18).

## Questions: what is decided, and what is still open

**Everything below is settled except two items at the end.** Each entry says who
decided it, so a later reader can tell the owner's calls from the design's.

### Decided by the OWNER (2026-10-11)

1. **The steps come from HIS OWN WORDS ONLY.** Jarvis may **not** read the
   phone's screen to suggest taps. He was offered the other path (option B in
   §1: read the screen and propose the sequence) and **declined it**. So the
   taint rule stays **exactly where it is** - no rule change - and
   screen-proposed steps remain refused. **This is the difference between what
   this feature is and the Gemini-style thing he originally asked about:** he
   asked for an agent like the one on the Pixel, and then chose the narrower
   version, where every tap comes from something he said himself. Later readers:
   the narrower choice was deliberate and is recorded here, in §1 and in
   correction item 7.
2. **A send may be the LAST STEP ONLY, on its own card** (§4), showing the exact
   message and the exact recipient - and **nothing before it in the run may run
   without him seeing that card**. If the card is not shown, the run does not
   happen.
5. **Saved recipes are NOT IN v1** (§1, option C) - **deferred, not refused**.
   What would have to be true to revisit it: a stored sequence may be replayed
   **only** with a card shown on **every** replay, listing every command, and
   only once A (his own words) has been in use and measured.
8. **The delete toggle - KEEP IT** (§16, §18). Off by default; with it off a
   deletion always gets its own card; with it on, recoverable deletions may
   happen inside the run; **permanent deletions and anything that closes or
   erases an account always get their own card, whatever the toggle says.**
   Recorded as a **preference, not a rule entry** - it relaxes no repository
   rule, and its "What asks first" row must not imply one exists. He was offered
   the stricter alternative (drop the toggle; every deletion always asks) and
   **chose to keep it**.
9. **The offline window - KEEP 12 SECONDS** (§6). The project's own
   `OFFLINE_GRACE_MS`, unchanged, for this path as for the others. He was offered
   a tighter session-only window and **chose the project's number**, with the
   cost he accepted stated plainly and kept: **up to 12 seconds of taps can
   still go out after the link really drops** (not to be softened).

### Decided by the DESIGN, and accepted by the owner as recommended

3. **The cap stays 8** (§8) - and note it is **newly imposed** on
   `control_phone`'s array, which has no cap today.
4. **When the screen no longer matches, the whole run STOPS** rather than
   pausing to ask (§2). A mid-run card could not show him the screen it was
   about.
6. **The delete verdict list stands as written** (§16): Archive and Clear cache
   sit under the toggle; Clear history, Clear data, Uninstall, Empty trash,
   Delete for everyone, Erase and Forget this device always ask; deleting or
   closing an account is refused outright.

### Settled by the design - and moot while item 1 stands

**Does the taint rule cover `control_phone`'s array path?** Settled here so no
one is left in suspense, and **flagged as the design's question, not his**:
**it does not.** In the code as it stands, the refusal that stops a plan from
being shaped by outside text is enforced on the **plan** route
(`backend/jarvis_agent.py:1489-1490`, with `jarvis_plan.propose()`), and each
other taint-sensitive tool carries its own gate (notes `:4422-4426`, spending
`:972-974`, browser `:586-587`). The phone tool has **no** such gate: its
definition (`:1545-1567`) and its prepare hook (`:403-411`) check nothing about
taint, while calling it still *marks* the turn as reading, because it is not in
`_NOT_READING` (`:3984`, `:4295-4296`).

**Because of item 1, this is moot for now** - the screen is not allowed to
propose anything, so there is no screen-shaped plan to refuse. It is written
down for whoever revisits item 1: **if the screen is ever allowed to propose,
extending that refusal to the array path is required first.** That is a
*stricter* change, so it is a code change to design and test rather than a rule
to loosen, and it would have to land before any such feature is switched on.

### Still open - the owner is being asked now

- **Q7, the driving model's card** (§15): may a second, specialist grounding
  model take the 12 GB card with the chat stepping aside (option B,
  recommended), or must it share whatever is already resident?
- **The badge's "draw over other apps" grant** (§13, §14): Android needs a
  one-time Settings permission for the always-on-top badge. The alternative
  needs no permission at all - the ongoing notification - but it cannot be drawn
  over the app in front and has to be found in the shade.
