# Tapping around on the phone: ONE plan card for a short sequence (design)

**Status: designed, nothing built. No patch, no module, no route.**
The owner asked whether Jarvis could control his Android phone "similar to how
Gemini on the Pixel 11 can take agentic control" (2026-10-11). He was told the
ability already exists as the `control_phone` action and is deliberately one
card per tap; he then chose: **design the multi-step version - a short
multi-step action as one plan card listing every tap up front, written down
for him to approve before anything is built.** That decision is the same one
already written in `CLAUDE.md` for the plan card generally (owner,
2026-09-27): *"The plan card is allowed later, only after the multi-step
safety tests pass; risky steps still get their own card."*

Written by the studio's designer against `origin/main` `b2beb60a`
(2026-10-11). **Anything marked unverified has not been tried on the owner's
phone or on any phone by this design.** The phone is in use by another
conversation while this is written: nothing here was run against it, and no
`adb` command was issued while writing.

**In one paragraph.** Today Jarvis can tap his phone, one literal `adb`
command at a time, each one behind its own approval card. This design keeps
every one of those properties and changes only how many cards a short,
already-decided sequence needs: Jarvis works out the literal commands first,
shows **all of them, in order, on one card**, and runs exactly those, checking
before every step that the phone is still the same one and still the app it
was planned against. Nothing new becomes possible - the same commands, decided
once. A step that sends something, touches a lock or a permission, or would
type into a secret field does **not** ride along inside the plan: it keeps its
own card. And a plan is never a session: it has a fixed list of steps, a fixed
end, and it stops dead - it never guesses - the moment the phone is not where
the plan expected it.

## What already exists and is reused (nothing here is a second version of anything)

| What | Where | What it gives this design |
|---|---|---|
| The literal-command plan and its runner | `backend/jarvis_android_control.py:19-29` (the permission model), `:161-177` (`plan()` builds and runs nothing), `:306-429` (`run()`) | The whole execution half. Unchanged. |
| Why a live session is refused | `backend/jarvis_android_control.py:8-11` | The rule this design must not weaken. Quoted below. |
| The card text | `backend/jarvis_android_control.py:195-216` (`describe()`) | The card body, verbatim: every literal command, numbered, with its `why`. |
| The weight line | `backend/jarvis_android_control.py:188-192` (`CARD_WEIGHT_LINE`) | The one line that says the whole plan is heavy, and that an unmarked step is not a promise. |
| The safe-text rule | `backend/jarvis_android_control.py:65-77` | Why `hello; reboot` cannot become two remote commands. |
| Never tapping inside Jarvis's own app | `backend/jarvis_android_control.py:236-286` | An existing per-step guard, already "stop, do not guess". |
| The plan-card machinery | `backend/jarvis_plan.py` - `:84` (`MAX_STEPS`), `:111-139` (the shapes), `:197-245` (`propose()`), `:262-287` (`describe()`), `:294-380` (`run()`) | The in-between case this was built for. Reused as-is, including its 8-step cap and its "a marked step still gets its own card" rule. |
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
which is what §2 exists for.

**The one thing all three share, and the reason this design is safe at all:
reading the phone's screen to VERIFY is fine; reading it to PROPOSE is not, in
this version.** Verification does not shape what will happen - it can only
stop it (§2).

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

## 6. Staleness (rule 4)

Rule 4 says the app **blocks acting when the event stream is stale**, and the
project draws the line precisely: *"never held on a stale event stream or by a
waiting card: rule 4 blocks ACTING on a stale stream, and these only make
Jarvis do less"* (`docs/ARCHITECTURE.md:353-354`). The grace is 12 seconds on
both apps (`docs/ARCHITECTURE.md:1874-1875`), and the staleness decision is
made on the PC side of the app, not in a page
(`docs/ARCHITECTURE.md:1863-1865`).

For a phone plan, "stale" means three separate things, and each has its own
answer:

1. **The PC's own event stream.** A plan is a long-running action the owner
   should be able to watch. **Recommended: the run refuses to START while the
   link is stale** (the same 12-second rule, `docs/ARCHITECTURE.md:1874-1875`),
   and does not begin work it cannot report. Mid-plan, a dropped stream does
   **not** stop the taps (the taps are local `adb`, not the stream) but the
   live line goes quiet, and the result says the report was incomplete - the
   same honesty the runner already applies to a late Stop
   (`backend/jarvis_android_control.py:414-428`).
2. **The phone connection.** Already answered, per step: before **every**
   command, `run()` checks the device is still in `adb devices`'s own list and
   stops otherwise, *"rather than sending a tap intended for one phone toward
   whatever is connected now"* (`backend/jarvis_android_control.py:313-321`,
   `:381-385`). This design adds no second mechanism and removes none. Which
   address that device is reached at - the mesh one, never a home-Wi-Fi one - is
   §12.
3. **The same serial.** Recorded on the card as part of the plan
   (`Plan.device`, `:99-106`), and compared every step by that same check.

**The phone never decides any of this.** No rule, no refusal and no approval
is made on the phone: the phone is the thing being acted on, and its only job
is to be the same phone (see "What this is NOT").

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
(`:211-213`). Re-using that cap means one promise to the owner, not two.

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

One card, drawn by the machinery that already draws plan cards
(`backend/jarvis_plan.py:262-287`) and filled with the existing phone card
text (`backend/jarvis_android_control.py:195-216`), so the two cannot drift:

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
- **Not a weaker live-session ban.** `plan()` still runs nothing
  (`backend/jarvis_android_control.py:161-163`), `run()` still executes only
  the enumerated commands with `approved` having no default
  (`:306-333`), and no new capability is added: the same commands, decided
  once instead of one at a time.
- **Not built.** No code, no patch, no new module, no route.

## What has to be true before any of it is built

1. **The plan card's own gate must be open.** The plan machinery refuses to
   run until a real `tools/tool_eval/ollama_tool_eval.py` run on this model
   clears the bar - 90% of the multi-step suite and **zero** planted
   instructions carried into a tool call
   (`backend/jarvis_plan.py:87-95`, `:453-492`);
   `backend/rebuilt/jarvis-framework.toml:246,250` keeps `run_plan` at "ask"
   until then. The phone plan rides that same switch - it does not get its own
   bypass.
2. **The tiers stay "ask"**: `control_phone` (`jarvis-framework.toml:248`) and
   `run_plan` (`:250`). This design never loosens either.
3. **The three unverified facts in §3 and §11** are measured on the owner's
   phone first.
4. **The first test (§11) is run by the owner, on his phone, watching.**

## Open questions only the owner can answer

1. **Who names the steps?** May Jarvis read the phone's screen to *suggest* a
   sequence (option B in §1), or does the plan always come from the owner's own
   words? Reading it to *check* each step is in this design either way.
2. **Sending inside a plan**: is it enough that a send is the last step and
   always gets its own card, or should a plan refuse to contain a send at all?
3. **The cap**: keep the existing 8 steps, or a smaller number for the phone?
4. **The pause**: when the screen no longer matches the plan, stop the whole
   plan (recommended, §2), or pause and ask?
5. **Saved recipes**: wanted at all, and if so, is a card on every replay
   enough for him?
