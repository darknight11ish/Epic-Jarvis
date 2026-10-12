# Field test top-up, third pass: the memory rows and the fingerprint gate (2026-10-12)

**The owner authorised this pass himself.** Ten rows were BLOCKED, the cause was put to him as a choice,
and he chose "turn the memory menus back on and re-drive those rows". This file records what happened
when that was tried.

**The setting was NOT changed - and it is not a setting a harness can change.** The phone refuses both
the switch and the Brain's own `Show` button without the owner's fingerprint or PIN. **Nothing was
loosened, and nothing needed restoring: after the attempt the switch was re-read `checked="true"`, i.e.
still ON, with the fingerprint prompt cancelled.** The prompt was cancelled twice, and never answered.

**This file does not rewrite the earlier ones.** `FIELD-TEST-2026-10-11-RESULTS.md`,
`FIELD-TEST-2026-10-12-TOPUP.md` and `FIELD-TEST-2026-10-12-TOPUP-2.md` stay exactly as their passes
wrote them, including every row that says BLOCKED. (The second top-up travels in its own PR, #339, open
at the time of writing - so it is not on `main` beside this file yet.) This is the new verdict beside each
id, with the date
it changed.

---

## 1. The desktop first, as instructed - and why nothing was changed there

The instruction was to try the desktop before touching the phone, because the record's cause names the
phone. Done, and here is what the desktop can and cannot give:

* **The desktop Settings page has no memory-menu rows.** Read whole over Windows UI Automation (1,999
  strings on this build), its only mentions of the subject are the phrase *"not while App lock or "Hide
  memory lists" is on"* inside the small-acknowledgements description, and a `Chat history and
  conversations` section. The `brain.memory.*` menus are not there.
* **The desktop Brain window still cannot be opened from a harness.** The HUD's 101 readable elements
  were listed: tabs `TALK` and `GALAXY`, `BRAIN IN USE` as a **text** element (not a control), buttons
  `Jarvis settings` and `Telemetry`, and the rails - **no control that opens the Brain**. That is the
  record's own tray dead end, unchanged.
* So the desktop half changed nothing, which is the correct outcome of trying it first: there was
  nothing there to loosen.

## 2. The phone: where the setting is, what it says, and what it does when asked

Reached by the app's own controls (Home -> Settings -> `Security` -> `Lock and fingerprint settings`),
with every step read before the next tap:

* The Security section's own summary line reads **`App lock off, risky approvals ask, memory lists hidden.`**
* Under it, `FINGERPRINT FOR PRIVATE LISTS`, the row is **`Hide memory lists and chat history`**, and its
  own description reads: *"Your memory lists, chat history and deep questions, the words of your timers,
  reminders and lists, the morning briefing's lines and what a focus session is on stay hidden until you
  confirm it is you. Their notifications say only what kind of thing is due. Show, on the Brain screen,
  asks for your fingerprint or PIN first. Screenshots of Jarvis are blocked while this is on."*
* Its node reads **`checked="true"`** - the setting is ON.
* **Tapping it drew this, and nothing else:** `Loosen security` / `Confirm it is you.` / `Touch the
  fingerprint sensor` / `Enter password` / `Cancel`.

**That is the app's own printed reason, quoted, and it is the answer for every row below.** The setting
is not hidden behind a switch a pass can flip; loosening it is the owner's fingerprint. Cancelled.

## 3. The Brain's own gate says the same thing

With the setting ON, the phone's Brain (its own `Brain` control on Home) draws the memory sections in
their hidden state, and the sight of it is evidence:

| what the Brain drew | the app's own words |
|---|---|
| `MEMORY AWAITING REVIEW` | **`Hidden. Tap Show and confirm it is you.`** with a `Show` control |
| `What Jarvis knows about you` | `Open` and **`3 inside`** - a count, never the content |
| tapping that section's `Show` | `Show memory lists` / `Confirm it is you.` / `Touch the fingerprint sensor` |

Cancelled again. So the gate is the same at the menu, at the section, and at the screen that lists them.

## 4. The rows, with the verdict this pass can stand behind

| id | feature | verdict now | evidence |
|---|---|---|---|
| `memory-waiting` | Facts waiting for your yes | **PARTIAL** | its section is real and reachable on the Brain - `MEMORY AWAITING REVIEW`, reading **`Hidden. Tap Show and confirm it is you.`** with a `Show` control. The row is real; the content behind it is the owner's fingerprint |
| `memory-known` | What Jarvis knows about you | **PARTIAL** | its section is real on the Brain and reports a **count** - `What Jarvis knows about you`, `Open`, **`3 inside`** - and opening it is the same fingerprint gate |
| `history` | Your past chats | **PARTIAL** | **driven**: Home -> `Earlier chats` opened **`History`** - `Chat history, kept on your PC`, **`On. New chats are kept on your PC, encrypted.`**, `Change`, and `CONVERSATIONS` reading **`Hidden. Tap Show and confirm it is you.`** with `Show`. The screen works and states its own setting; the conversation list is the owner's to unlock |
| `chat-thread` | The whole conversation, and carrying it on | **PARTIAL** (evidence added) | the same `History` screen, reached from Home's `Earlier chats`, carries `CONVERSATIONS` under the same hidden state. Its earlier PARTIAL stands, and this is the phone half of it |
| `pinned-facts` | Always keep in mind | **BLOCKED** | the app's own prompt: `Loosen security` / `Confirm it is you.` / `Touch the fingerprint sensor` for the switch, and `Show memory lists` / `Confirm it is you.` for the Brain's own Show |
| `memory-as-of` | What did I believe on this date? | **BLOCKED** | same gate, same two prompts |
| `between-us` | Between us | **BLOCKED** | same gate |
| `chat-tags` | Chat tags | **BLOCKED** | same gate |
| `sensitive-facts` | Health and money facts wait for your yes | **BLOCKED** | same gate |
| `memory-tab` | The Memory tab | **BLOCKED** | the desktop Brain cannot be opened from a harness, and the phone's list is behind the same gate |
| `memory-saved` | Facts Jarvis saved by itself | **BLOCKED** | same gate |
| `memory-people` | People and things | **BLOCKED** | same gate |
| `memory-learning` | The learning switches | **BLOCKED** | same gate |
| `forget-range` | Forget a time frame | **BLOCKED** | it is an action taken by asking, and the phone's own chat history and memory lists are behind the same gate |

**The correction that matters, and it is bigger than these rows:** the earlier pass wrote the cause as
*"the `brain.memory.*` menus are hidden on this phone by 'Hide memory lists and chat history'..."*, which
reads as though flipping a setting would show them. Measured today, with the owner's authority to flip
it: **the setting cannot be flipped without his fingerprint.** These rows are not blocked by a
preference - they are blocked by a **biometric gate**, and no authorisation can substitute for the
finger on the sensor. A future pass should read them as the owner's to unlock, not as a harness task.

## 5. What this pass did and did not do

- **No setting was changed.** The switch was tapped once; the fingerprint prompt appeared; it was
  cancelled. The switch was then re-read: **`checked="true"`**. The Brain's `Show` prompt was raised and
  cancelled too. Nothing was loosened, and nothing needed restoring.
- **No memory content is in this file.** Only ids, the rows' own labels, the screens' own wording, and
  counts - never a fact's text, a chat word, a message, a token or an address.
- The phone was driven only through the app's own controls (Home, Settings, Security, the Brain), and was
  left on the app's own Home screen.
- **Not done, and not claimable by this method:** unlocking the memory lists, the chat history or the
  deep questions - each needs the owner's fingerprint or PIN, which a pass does not have.
