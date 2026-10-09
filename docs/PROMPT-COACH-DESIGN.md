# The Prompt Coach: design

The owner asked, 2026-10-08: *"Are there any GitHub repos that would help me
write better prompts and give me feedback? I'd like to integrate this as a
feature I can turn off and on in Jarvis."* This is the design, written before
anything is built, the way `SCREEN-DESIGN.md`, `LIVE-DESIGN.md` and
`PROJECTS-DESIGN.md` were. Two choices at the end are the owner's; everything
else is written down so the build cannot drift.

## What it is, in plain words

You write a question. Before you send it, Jarvis can read it and say what is
missing - no output format, no idea what "it" refers to, three questions
crammed into one - and offer a better version. You look, and either send yours
or send its version. **It never sends anything by itself and it never changes
your words without you saying so.**

## Where it comes from, and what was rejected

The owner's suggestion came with a plan and four libraries
(`promptimal`, `textgrad`, `promptfoo`, `prompt-optimizer`). I checked each
against this repository and against the library itself. **None of them is
used**, for reasons that are all verifiable:

- **`promptimal`** needs `OPENAI_API_KEY` and does not support local models -
  Ollama is item 1 of its own roadmap. Adopting it would send the owner's
  typed words to OpenAI, which is rule 1 broken. It is also a genetic loop
  (`--num_samples=20` per generation), i.e. dozens to hundreds of model calls
  per prompt, which is not a thing that can happen between typing and sending.
- **`textgrad`** is MIT but pre-alpha (`Development Status 2`, 0.1.8) and pulls
  `openai`, `litellm`, `datasets`, `pandas`, `graphviz`, `gdown` and
  `diskcache`. It is built for offline optimisation of prompts, not for
  checking one message. (It does **not** need PyTorch - checked, because it
  would have settled the question on its own.)
- **`prompt-optimizer`** is **AGPL-3.0**, not the MIT the suggestion claimed,
  and it is a Node/TypeScript web app (Vercel, Docker, Chrome extension),
  not a Python library whose schemas can be lifted.
- **`promptfoo`** is genuinely MIT and genuinely good - at a different job:
  regression-testing *Jarvis's own* system prompts offline, in CI. That is a
  separate, much smaller piece of work, noted here so it is not lost.

What was worth taking is the **idea of what a prompt is usually missing**,
which is a list of checks, not a dependency.

## The rules it obeys

1. **Local model only.** The critique runs on the model already on the PC. No
   new way out of the PC, no key, no service. This is rule 1 and it is the
   whole reason none of the four libraries above is usable.
2. **Never logged, never learned.** The prompt being coached is the owner's own
   words, and the critique is not a fact about them. Nothing here is saved to
   memory, written to chat history, or counted.
3. **It approves nothing and acts on nothing.** It reads text and returns text.
   No tool runs, no file is touched, no card is raised, no `jarvis_gate`
   import. Its own test reads its source to keep that true.
4. **Suggestions, never substitution.** The owner sends either their own words
   or the suggested ones, explicitly. There is no "improve and send".
5. **Off by default, and the switch is in Settings.** The owner asked for this
   in those words. Off, nothing is read and no call is made.

## The three choices, and what is chosen

**A. A button, not a per-message interceptor.** The suggestion above wanted the
coach to intercept every message when on. Chosen instead: a **"Coach this"**
button beside the send button, and the switch decides whether the button is
there at all. Reasons: an 8B local model is a *weak judge* and will confidently
"improve" a prompt that was already fine, so it must not be in the path of
every message; and a critique is a full model call (seconds), which between
typing and sending would feel like Jarvis being slow for no reason. A setting
to also check every message can come later if the owner wants it.

**B. Turning it on is immediate - no approval card.** Every other "loosening"
setting in this project raises a card, and this one deliberately does not: it
opens no way out of the PC, reads only words the chat is about to send to the
same local model anyway, and takes no action. Turning it off is immediate too.
This is written down because "no card" must be a decision, never an oversight -
the same reasoning as the plain-timer and music-control decisions of
2026-09-25 and 2026-09-27.

**C. The same model the chat uses.** If the second card is switched on and has
its lane, the coach may use that lane, because it is a one-shot job with no
conversation state. It does **not** get a switch of its own: the second card
already has one, and a feature must not switch on by itself (the hardware page
rule of 2026-10-05).

## What a critique contains

One strict JSON object, with the schema sent as Ollama's `format` so the shape is
constrained while it decodes - the house norm, which every shipped module follows.
(The research is why: `jarvis_structured.ollama_body()` has no shipped caller, so
routing through it would have been a shape nothing else in the tree uses.)

- `score` - 1 to 10, how complete the prompt is. Shown, never used as a gate.
- `issues` - up to four, each with what is missing, why it matters, and the
  smallest fix. **A critique with nothing to say is a valid, expected answer**:
  "this is clear, send it" must be as easy to get as a list of complaints.
- `missing` - questions the coach would have to ask to do the job well.
- `suggestion` - the same request, rewritten. Shown in full, never applied.

Never: invented facts about the owner, a claim to have run anything, or a
rewrite that answers the question instead of asking it better.

## Where the pieces go

- `backend/jarvis_prompt_coach.py` - the module. Standard library plus the
  local model; no network, no subprocess, no eval, no new dependency.
- `prompt-coach.patch` - one hunk wiring `POST /api/prompt/coach` into
  `jarvis_hud.py`, placed **before `screen-attach.patch`** (which must stay
  last) and added to the three "written after me" shortlists
  (test_referee.py, test_devices.py, test_gate_risk_rows.py).
- The setting: `prompt_coach` in `jarvis_settings_registry.py`'s
  `BOOL_SETTINGS`, with its own `SECTIONS` entry (`prompt-coach`), so it
  appears in **Settings on the PC and on the phone** as *"Prompt coach"*, off
  by default. Both apps get it; `tools/check_parity.py` classifies the route.
- The features list (`features.json`, three byte-identical copies) gets an
  entry - `tools/check_feature_list.py` refuses a Brain read nobody listed.
- `docs/JARVIS-API.md` section 120, a `CHANGELOG.md` entry, a `docs/README.md`
  row, and the decision recorded in `CLAUDE.md`.

## What is not claimed

- **An 8B model is a mediocre prompt critic.** It will miss things a strong
  model catches and will sometimes be confidently wrong. The design answer is
  to keep it advisory and to say so in the app's own line under the switch.
- **Nobody has measured how long a critique takes** on the owner's PC. Until
  that measurement exists, the button is the only entry point and there is no
  promise about speed. (One PowerShell line while the coach runs is the
  measurement, the same shape as the other unmeasured features.)
- **The four libraries were rejected on the evidence above**, which is their
  own READMEs and `requirements.txt`, not a benchmark of them.

## The two questions that are the owner's - answered 2026-10-08

1. **Just the button, or also a setting that checks every message?** The owner
   answered: **the button, with a setting to turn the feature off.** So the
   `prompt_coach` switch is the master switch and it is the only switch: off,
   there is no button and nothing is read; on, the "Coach this" button appears
   beside Send. There is no per-message mode, and nothing runs unless the
   button is pressed.
2. **May the coach also read the last few turns of the conversation?** **Yes** -
   the same turns the chat already holds, so "it" and "that" have an
   antecedent, and no further.

