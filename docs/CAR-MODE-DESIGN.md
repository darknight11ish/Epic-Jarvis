# Car mode, and changing any setting by asking

Written 2026-10-09, from the owner's own words:

> *"a phone based car mode with the screen mostly off, voice first, big targets
> when a glance is safe. and also a phone screen on mode that is specifically
> designed for being interactive while im in the car."*

> *"make sure I can ask jarvis to change any and all settings in chat, with an
> additional approval card for more intense settings changes that appears when
> appropriate."*

Car mode is **phone-based only**. A real car head unit needs Play distribution
(Google requires it for the Car App Library), and rule 5 is sideload-only,
never Play - so a Jarvis on a head unit is not reachable by design. This is not
a limitation to work around; it is the shape of the feature.

## 1. Two modes, not one

The owner asked for both, and they are different things:

**"Driving" - the screen mostly off, voice first.** The phone is dark and in a
mount or a pocket. Jarvis listens, answers, and speaks up on its own. Nothing
needs to be looked at or touched. This is the mode for actually driving.

**"Parked" - the screen on, built for a glance.** The screen stays awake, and
everything is drawn for use in a car: few controls, each one large, each one
readable at arm's length in daylight, and nothing that needs precision.

Both are turned on **by asking** ("turn on car mode", "turn on the screen for
the car"), and both need a way **off without the screen** - a spoken phrase, and
the headset/Bluetooth button, which must never approve anything (the existing
Live rule).

## 2. What "voice first" means, precisely

- **No taps are needed to use it.** Every control in the driving mode has a
  spoken equivalent.
- **The screen shows almost nothing** - a single line of state at most (for
  example, that Jarvis is listening), never text to be read while moving.
- **Speech in, speech out.** Answers are kept to something safe to hear: short,
  no lists, no markdown - the spoken-style rule the app already applies to voice
  turns.
- **A long message is shortened before it is spoken.** A wall of text is not
  safe to hear while driving; the summary says plainly when it has shortened
  something.
- **It is built to be interruptible.** Saying stop stops the speaking at once.

## 3. What it may speak up about - a setting, chosen by the owner

The owner chose the default: **everything Jarvis would normally notify about**,
including email and briefings. The quieter options exist and are selectable:
*messages, alarms and urgent alerts*; and *alarms and reminders only*.

**A car mode that talks too much is worse than one that stays quiet**, so the
default must still be rate-limited: one thing at a time, a gap between
interruptions, and never anything during a call or while the owner is mid
sentence.

**Reading text messages aloud is allowed in car mode only**, and is a
deliberate relaxation of an earlier rule - recorded, with everything it keeps,
in `docs/RULE-FLEXIBILITY.md` entry 001. In short, and unchanged from that
entry: **Jarvis never replies and never sends**; **one-time codes are hidden**
before anything reaches the model or the speaker; **every message is outside
text** (never learned from, never a fact, never makes Jarvis act); **nothing
leaves the owner's own devices**.

## 4. What may act without a tap

Rule 4 says nothing is auto-approved and acting stops on a stale event stream.
Car mode is hands-free by nature, so the honest split is:

- **Reading, summarising and speaking proceed without a tap.** They change
  nothing.
- **Anything that acts waits until the owner has stopped** - or until they say
  so at a moment when the car is still, at which point the card shows on the
  phone and is decided the way every card is: **by tapping, never by voice.**
- **A card that needs a decision while driving is never spoken as if it were
  answered.** If one arrives, Jarvis says a card is waiting, and nothing
  happens until it is decided.

## 5. Asking Jarvis to change any setting

Today this is **partly** true and it would be dishonest to call it done. The
backend matches a spoken phrase against the switch table (`jarvis_quick.py`
around `:2788`, dispatching near `:3703`), but **most settings have no setter to
dispatch to**: of the 26 desktop toggle rows, only **6** are backed by a switch
the backend can actually change. Asking for the other 20 matches a phrase and
then fails.

**So the work is:** every row in the settings table (`SETTINGS_ROWS`, added by
the generator in PR #163) gains **the way to change it** - the route and the key
the backend must call - and a row with no setter is a row Jarvis cannot change by
asking, which the table must say rather than pretend.

**The rule for what asks, and this is the owner's "more intense" clause made
concrete:**

| The change | What happens |
|---|---|
| Turning something **off**, or making Jarvis **stricter** | **Immediate, no card.** This is the house rule everywhere else and it applies here. |
| An everyday change - appearance, voice, faces, briefing, quiet hours | **Immediate, no card.** These are the settings the owner changes often, and a card for each would make asking useless. |
| Turning something **on that loosens a rule** - remembering sensitive topics, hands-free trust, reading notifications, lights without a card | **A card, every time.** |
| A change that **opens a way out of the PC**, or touches **security** - a new online service, App lock, a new device, the pairing rules | **A risky card**: Windows Hello on the PC, the screen lock on the phone. |
| Anything in car mode that would **act** | **Waits until stopped** (§4). |

**The card says what will change, in plain words** - "Jarvis will remember
sensitive topics without asking" - never "allow setting X". And the tier comes
from the **gate**, not from the chat code, so both apps and every route agree.

## 6. Questions only the owner can answer

1. **How often may car mode speak up? - ANSWERED 2026-10-10 (owner):**
   *"1 by default, but with this adjustable to 1 2 or 3 in the settings or with
   even more flexibility."* So the gap is **about a minute by default**, and it
   is a **setting** whose choices are **1, 2 or 3 minutes** - with the setting
   built so **more fine-grained control can be added later without redesigning
   anything** (store the interval in seconds or a small list, not as a
   three-way flag). The quietest option from the earlier draft - only urgent
   things, everything else waits until asked - stays available as the loosest
   end of the same setting, since that is the shape the owner asked for: one
   control, adjustable.
2. **During a call:** stay completely silent (recommended) / read nothing but
   say an urgent alert is waiting.
3. **In the parked, screen-on mode:** should the screen stay awake
   indefinitely while charging (recommended) / time out after a few minutes of
   no interaction.

## 7. First slice, and its size

Small, safe and provable, in this order:

1. **The switch and the state**: car mode on/off by asking, with a spoken way
   off, and both modes drawn as their own screen states.
2. **Voice-first behaviour**: spoken-style answers, interruption, and the
   "mostly off" screen.
3. **Speaking up**: the proactivity setting, rate-limited, starting with alarms
   and reminders only (nothing social), so the SMS relaxation is not needed
   until the reading path itself is proved.
4. **Then** messages, and with them entry 001's alert card.
5. **Settings by asking** as its own piece of work: the setters in the table,
   then the tiering above.

## 8. Constraints this design does not escape

- **A client never does speech-to-text.** The words are worked out on the PC, so
  car mode is only as good as the link. **When the link drops mid-sentence, it
  must say so** - not fall silent, and not pretend it heard.
- **Nothing is auto-approved**; acting stops on a stale event stream.
- **No public tunnel**; the phone reaches the PC over Tailscale or Meshnet only.
- **The pairing token and keys are never logged.**
- **Sideload only, never Play** - hence phone-based.

## 9. Known and unproven

- Whether Android will keep a hands-free voice loop alive reliably in the
  background on this phone, and how much battery it costs, is **not measured**.
- Whether the phone can tell it is in a car without asking the owner is **not
  assumed**: car mode is turned on by asking, deliberately.
- Nothing in this document has been built yet. It is a design, and it says so.
