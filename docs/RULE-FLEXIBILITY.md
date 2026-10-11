# Changing a rule to enable a feature

Written 2026-10-09, at the owner's request: *"change this rule with flexibility and
alerts if it is going to be changed to enable a feature."*

## Why this file exists

Rules in this project have, until now, only ever been **tightened** in one
direction: a decision was written down, and later work had to fit around it. That
is safe, but it makes the project unable to grow - a feature that needs a rule
loosened either never gets built, or gets built by someone quietly editing the
note that stood in its way. **The second outcome is the dangerous one**, because
the rule stops matching what the app does and nobody finds out until it matters.

So: **a rule may be relaxed to enable a feature, and it must never happen
silently.** Every relaxation gets an entry below, and every relaxation raises an
alert before anything can use it.

## The three steps, all required

1. **A written entry in this file**, added in the same change that needs it:
   the rule, the feature that needs it, the date, **who decided** (the owner, or
   nothing - an agent may not do this), and **exactly which protections are
   kept**. An entry that does not name what is kept is not complete.
2. **An alert, before the feature may use it.** The relaxation is a gate action
   at tier `ask`, so it raises an approval card the first time it would be used
   (and whenever the setting is turned on): on the PC that means **Windows Hello**,
   on the phone **the screen lock** - the same shape as every other loosening.
   The card says, in plain words, **which rule is being relaxed and what the
   relaxation lets happen** - not "allow feature X", but "Jarvis may read your
   text messages aloud while car mode is on".
3. **A line on the "What asks first" page** (`jarvis_asks_first.py` and its
   mirrors), so the owner can find every relaxation in one place rather than
   having to remember them.

**Turning a relaxation back off is always immediate, with no card.** Strict now,
ask later - the same rule the rest of the project uses.

## What may never be relaxed, under any feature

These are not "hard to relax": they are the floor, and a feature that needs one of
them is not built.

- **No public tunnel.** No ngrok, no Cloudflare Tunnel, no Tailscale Funnel.
- **Never auto-approve anything**, and acting stays blocked while the event
  stream is stale.
- **The pairing token and every API key are never logged**, and never written to
  disk in plain text.
- **A client never does speech-to-text.** The words are worked out on the PC.
- **Non-commercial, sideloaded, never on Play.**
- **No bulk approval, and nothing that clears a rush latch.**

If a feature appears to need one of these, that is a finding to report - **not a
reason to edit this list.**

## Entries

### 001 - Text messages (SMS) may be read aloud in car mode

- **The rule that was relaxed.** `CLAUDE.md`, 2026-09-26: notification reading is
  *"never text messages (SMS), and Jarvis never replies or sends."*
- **The feature that needs it.** **Car mode** on the phone (owner, 2026-10-09):
  *"read texts outloud proactively, and more. like android auto but a better more
  private jarvis driven one."* Reading a text aloud while driving is the whole
  point of that feature; without this, car mode could not be built as asked.
- **Decided by.** The owner, 2026-10-09, in answer to a direct question that named
  the rule and what changing it would allow.
- **What is kept - all of it, unchanged.**
  - **Jarvis never replies and never sends.** Not in car mode, not anywhere. A
    message that needs an answer is **drafted and read back only**; sending stays
    a thing the owner does.
  - **One-time codes are hidden** before anything reaches the model - and before
    anything is spoken aloud.
  - **Every message is outside text**: never learned from, never saved as a fact,
    never makes Jarvis act.
  - **Nothing leaves the owner's own devices.** The message text goes to the
    owner's own PC and nowhere else.
  - **Default off.** Car mode is turned on by asking, and the reading only
    happens while it is on.
- **The alert.** The first time car mode would read a message aloud, the card
  says which rule is relaxed and what it allows, in those words; approving it is
  a Windows Hello or screen-lock check, and it can be turned off at once.
- **The setting.** What car mode speaks up about is a **setting**, not a fixed
  choice. The owner chose the default **"everything Jarvis would normally notify
  about"** (2026-10-09), with the quieter options available: *messages, alarms and
  urgent alerts*; and *alarms and reminders only*.

### 002 - Jarvis may draft a reply, and the owner sends it

**This is not a relaxation. Nothing in entry 001 changes**, and this entry exists
because the owner asked for something (2026-10-09) that sounds like it needs one
and does not:

> *"enable jarvis to reply with something that it automatically wrote in response
> to a text that it received and analyzed, or let me reply with a voice to text
> message, both with settings i can turn on and off."*

**The owner was asked what "replies automatically" should mean, and chose:**
*"Draft it, read it back, you say send."* And for a spoken reply: *"Speak it, then
confirm before sending."* Both choices keep a person in the loop, so the rule
that matters - **Jarvis never replies and never sends** - stands exactly as
written. Drafting is not sending.

**What is therefore allowed:** Jarvis may **compose** a suggested reply to a
message it has read, and may **say it aloud** for the owner to hear. The owner
may also **speak** a reply, which is worked out on the PC (a client never does
speech-to-text) and shown back.

**What is forbidden, and a future agent must not "helpfully" add it:**

- **Jarvis never sends a message by itself.** Not in car mode, not when the
  owner is driving, not for a contact the owner has named, not ever. Auto-send is
  not a setting that is off by default - **it is not built at all.** If a future
  request wants it, that request needs its own entry here and the owner's own
  decision, because it is the first thing in this project that would act toward
  another person with nobody checking.
- **The reply is shown or spoken in full before it is sent** - never a summary,
  never "sent your usual".
- **A never-reply list is not enough on its own.** One-time codes, banking,
  anything about money or health, and anything that commits the owner to a plan
  are messages Jarvis does not answer at all - the composer says so instead of
  guessing.
- **The send is the owner's action, on the owner's phone**, after hearing or
  reading it. A misheard word can never leave by itself.

**The settings** (owner, 2026-10-09): two switches, either can be on alone -
*"Jarvis can suggest replies"* and *"I can reply by voice"*. Both follow the
house rule: turning one **off** is immediate with no card; turning one **on**
raises a card, because it widens what Jarvis may do with the owner's messages.

### 003 - A "Reject" click may be written down as a suggestion, in Jarvis's words, marked as a guess

- **The rule that was relaxed.** `CLAUDE.md`, 2026-09-24: facts about the owner
  and their projects are *"learned from the owner's own words only (never from
  web pages, emails, documents, notes or tool output)"*. A **Reject click is not
  the owner's words** - it is a button, and it carries only an action name, a
  time and who pressed it: `jarvis_hud.py`'s Reject sends `{id, by}` and
  `jarvis_gate.decide()` NULLs the card's own `prompt` and `detail`. Any words
  written down from one have to be supplied by Jarvis.
- **The feature that needs it.** Learning from the owner's rejections at all
  (owner, 2026-10-09): *"hook every Reject click into learning."* Without this
  there is nothing to learn from, because the click carries no reason and no
  corrected value.
- **Decided by.** The owner, 2026-10-10, in answer to a direct question that
  named the rule and what changing it would allow. The decision was to **write
  it down, but marked as a guess** - a suggestion the owner Keeps or Discards -
  *"replacing today's version that puts words in his mouth"*.
- **What was wrong before, and is fixed.** The gate did not merely record a
  rejection: it **manufactured an owner-voice sentence** - *"Remember this: I do
  not want Jarvis to `<action>` without asking me first. I just said no when it
  asked."* - and handed it to the learner as if it were the owner's own turn,
  with "I just said no when it asked" inventing a reason for a click that
  carries none. That was a rule bend shipping **unlabelled**. The proposal now
  says, in its own words, that it is **Jarvis's guess**, that it is *not a
  record of the owner's words*, and that no reason was given nor made up to fill
  the gap, and that keeping or discarding it is the owner's call.
- **What is kept - all of it, unchanged.**
  - **It is a suggestion, never a fact, and never a second door into memory.**
    It goes through `jarvis_extract.propose()`, the one review queue every
    learned fact already passes - the path `memory-safety.patch` cleared of the
    single auto-accept branch. Nothing reaches `memory.db` until the owner
    presses Keep, and **nothing is ever applied by the click itself**: the
    rejection still refuses, and the action still asks again next time.
  - **It is labelled as guessed, everywhere the owner can meet it.** The
    proposal's own text says so; the review card's own line says so
    (`guessed`, plus the words in the reason line both the PC's Brain window and
    the phone's Memory tab already read); and `source="gate_denial"` stays on
    the row, which `check_source()` has always read as *"made from an action you
    turned down, not from something you said"*.
  - **No reason is invented.** The function deliberately does not read `detail`
    at all - this click carries no reason, so there is nothing in it that could
    honestly become one. The proposal says that outright.
  - **Nothing else feeds it.** Never a timeout - the absence of an answer, so
    the expired path calls this from neither branch (`jarvis_gate.py`,
    `outcome="timed_out"`). Never the actions in `_NO_RULE_FROM_DENIAL` (51 of
    them), whose "no" answers one card rather than a standing wish. Never a
    crisis turn, and never a tool result, web page, email, document or note.
  - **Best-effort.** A failed or unimportable proposal is swallowed, so a
    completed denial can never become an error the owner has to clear.
  - **No approval is ever auto-granted** (rule 4). `Verdict`'s default stays
    `refused`, and no "never ask again" list is written by any of this.
  - **Nothing leaves the PC.** The proposal is made, stored and reviewed on the
    owner's own machine (rule 1).
  - **Forget works on it.** A kept rule is an ordinary saved fact: it can be
    forgotten, and its words erased, exactly like any other.
- **The alert.** **No new gate action and no new approval card** - and that is
  the decision, not an omission. The relaxation's own alert is the review card
  itself: nothing at all is learned or applied until the owner reads the guessed
  rule and presses **Keep**, and pressing **Discard** leaves memory untouched.
  A second, gating card over the same decision would ask the same question
  twice. The row below is therefore the *third* required step, not the second:
  it puts this relaxation on the "What asks first" page where every other one
  can be found.
- **What asks first.** One line on the "What asks first" page
  (`jarvis_asks_first.py`), as the fixed row `fixed:playbook_rejection`, mirrored
  into the case files both apps read
  (`tools/gen_asks_first_cases.py`):

  > **Learn a rule from a Reject click** - *Writes a guessed rule for you to Keep
  > or Discard.* A Reject click carries none of your words, so the rule is worked
  > out from the action's name and says so. It is a suggestion in Brain, never a
  > saved fact, and it never changes what Jarvis is allowed to do until you Keep
  > it. Never from a card that timed out.
- **Not built here, and not claimed.** The wider experiential-learning design
  (`docs/EXPERIENTIAL-LEARNING-DESIGN.md`) proposes a separate `playbook.db`, a
  Keep/Discard surface of its own, and new measurement (about 20 playbook cases,
  10 run-pair cases; bars 18/20, 8/10, 0 wrong rules). **None of that is in this
  entry's change.** What ships here is the naming and marking of a proposal that
  was already being made - and, because a playbook entry comes from the same
  click, that design must carry this entry's marking wherever it goes.
