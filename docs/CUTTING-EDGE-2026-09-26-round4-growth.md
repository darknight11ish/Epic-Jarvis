# Cutting-edge audit, round 4, 2026-09-26: a personality that grows with you

One slice of round 4 ("the personality of Jarvis and personality building"):
how Jarvis could learn **how you like to be talked to** - length, formality,
humour, what to call you, when to be brief - while you can always see, undo
and reset it. It builds on round 2 (`CUTTING-EDGE-2026-09-26-round2-personality.md`:
"About Jarvis", "Explain simply", games in a temporary chat) and the memory
research (`MEMORY-RESEARCH-2026-09-26.md`), and does not repeat them.

**Limits.** Research only: nothing was built, run or measured. Repo
`file:line` references were checked on 2026-09-26 at commit `8743728` (an
uncommitted edit to `jarvis_agent.py` in the working tree shifts its lines by
about 52; function names are given too). arxiv.org, help.openai.com
and huggingface.co are blocked here, so every paper finding below is from a
search summary *(search summary)*; what a product or project says about
itself is marked *(claim)*. Licences marked "LICENSE read" were read from the
repository's raw file.

---

## In six lines, for the owner

1. **Pick a personality, then fine-tune it.** Keep "Warm and brief" and
   "Plain", add "Patient teacher", then a few dials on top: shorter or
   fuller, casual or formal, a little humour or none, emoji, and what to call you.
2. **Say it once, it sticks.** "From now on, keep it short" or "call me Sam"
   changes the dial at once, and Jarvis says so. One Undo button reverses it.
3. **You can always see what it picked up.** A "How Jarvis talks to you"
   list in both apps: every change, its date, how it happened, Undo, and
   Reset.
4. **It cannot slide into flattery.** Style is a few fixed dials, never a
   personality the AI rewrites. Thumbs-up marks never change it. A fixed line
   in every style says "being warm never means agreeing".
5. **Inside jokes and shared history** can be kept as ordinary memories
   with a "Between us" label, from your own words only, with Forget and Erase.
6. **Cost to the model is small.** Style is one short line placed beside the
   manner line that exists today, with a hard size cap held by a test.

---

## The concrete design

**Four layers, from the bottom up.** Each can only change *wording*, never
what Jarvis does, asks or remembers (the rule `jarvis_manner.py:8-11` already
states for manner).

| Layer | What it is | Who changes it | Where it lives |
|---|---|---|---|
| Rules | "Say what is a guess", "never claim an action" | Nobody from an app | Modelfile `SYSTEM` (`backend/jarvis-primary.Modelfile:160`) |
| Preset | Warm and brief (default) / Plain / Patient teacher | Owner's tap | `style.json` (today `manner.json`, `jarvis_manner.py:107`) |
| Dials | Length, formality, humour, emoji, lists, explain simply, "call me" | Owner's tap, or owner saying "from now on ..." | `style.json`, with a change history |
| Your words | Up to 5 short style notes in the owner's own words (later) | Owner only | `memory.db`, as facts marked `kind: "style"` |

Relationship memory ("Between us") is **not** a style layer: it is ordinary
facts with a label, recalled by search like any fact (idea 7).

**Why dials are not facts.** Facts reach the model as *quoted data*, "never
an instruction" (`memory-profile.patch:116-121`). A style setting *is* an
instruction; mixing them weakens one or the other. Splitting memories by
kind also reduced answers leaking unrelated memories *(search summary:
"Mitigating Over-Personalization in LLMs via Structured Memory", Aug 2026,
~8.8%, their claim)*. So each dial value maps to **one fixed sentence written
in the repo**: the owner picks a value, never writes the instruction.

**`style.json`** (beside `manner.json`, in the backend config folder):
`preset`, one value per dial (`length: shorter|usual|fuller`, `formality:
casual|usual|formal`, `humour: none|light`, `emoji: never|if_owner_does`,
`lists: fewer|usual`, `explain_simply: on|off`), `call_me` (at most 40
letters, spaces or hyphens), and `history`: the last 50 changes as `{id, at,
dial, from, to, how}` (`how`: tap, said, offer, undo, reset). No sentences.
A missing or damaged file means the defaults (`jarvis_manner.py:111-118`).

**How it is learned** (the owner's approval decisions applied):

| What happens | Result | Card? |
|---|---|---|
| Owner taps a preset or dial in either app | Changed at once, history entry `tap` | No - wording only, same as manner (`jarvis_manner.py:29-31`) |
| Owner says a standing change: "from now on / always / stop ...", "call me Sam" | Changed at once, Jarvis confirms in a fixed line with "Undo in Brain" | No, but only if the turn passes the automatic-learning live-turn checks (below) |
| Same words, but the turn fails those checks (pasted, after outside text, a temporary chat, "Hey Jarvis" under "Only trust the talk button") | This chat only; not saved; the reply says why | No |
| One-off: "shorter please", "too long" | This chat only; counted (date only, no words) | No |
| 3 one-offs of the same kind in 14 days | An **offer**: "Make shorter answers the usual?" Yes / Not now | No; goes through the back-off rules |
| Anything that is not wording ("stop asking before sending email") | Not a style change: a fixed reply pointing to "What asks first" | - |
| Thumbs-up/down marks, mood, tone of voice, the assistant's own words, games | **Never** change style | - |

The live-turn checks are automatic learning's own: `check_turns`
(`jarvis_auto_learn.py:1125`) - seen live, typed or strictly verified voice,
the hands-free choice (`check_voice`, `:599`), not tainted (`check_taint`,
`:639`), not pasted (`check_outside`, `:743`). The phrase matcher is fixed
words, no AI model, in `jarvis_quick.match` (`jarvis_quick.py:608`), like
timers - English first.

**How it reaches the model.** Today the manner line is one system message
placed just before the newest question (`jarvis_agent.with_manner_note`,
`jarvis_agent.py:3191`), never first (`keep_rules_first`, `:3265`), and its
size is taken out of the room left for older turns (`run_local_turn`,
`:3468-3470`). The style line **replaces** it in the same place:

```
Manner, for wording only: <the preset's sentence, as today>
<one fixed sentence per dial that differs from the preset>
Call the owner "Sam".
Being warm never means agreeing: if the owner seems mistaken, say so kindly
and plainly, and do not praise ideas or work unless asked.
All of Jarvis's rules still apply in full: ...
```

- **Budget.** Warm is 321 characters today, Plain 231 (measured here);
  `test_manner.py:170` caps a preset line at 420. Proposed cap for the whole
  style message: **900 characters** (~300 tokens by `estimate_tokens`,
  `jarvis_agent.py:1941`), pinned by a new `test_style.py` the way
  `test_tool_text.py:42-43` pins tool text. On the 4,096-token window
  (`MODEL-TOPOLOGY.md`) that is ~7%, like the pinned list; default dials
  cost what the manner line costs now.
- **Spoken turns:** the spoken-style note still goes after it, nearer the
  question, and wins on length (`jarvis_agent.py:3121`, `:3482`).
- **Known gap, inherited:** turns relayed without `run_local_turn`, deep
  questions and the wiki builder get no manner line (`JARVIS-API.md` §27,
  "limits"), so they would get no style either.

**Both apps**, the same patterns as manner and "Always keep in mind":
- Desktop Settings, "How Jarvis talks" (`jarvis-desktop/src/settings.html:590`,
  `manner-settings.js`): three presets, a "Fine-tune" fold with the dials, a
  "Call me" box, "Reset to <preset>". Phone: the same inside `MannerSection`
  (`BrainScreen.kt:454`, `MannerPlate.kt:38`). Words come from the PC
  (`GET /api/style`, like `jarvis_manner.view()`, `:127`).
- Brain, beside "Always keep in mind" (`brain.html:328`; phone
  `AlwaysKeepInMindSection`, `BrainScreen.kt:562`): **"How Jarvis talks to
  you"** - "Shorter answers - you said so, 12 Oct (typed)" with Undo on each,
  then "Your words" notes and the "Between us" list with Forget / Erase.
  Hidden like every memory list under App lock / "Hide memory lists".
- Routes: `POST /api/style` takes **one** change per request (`{"preset"}`,
  `{"dial", "value"}` or `{"call_me"}`), `POST /api/style/undo {"id"}`,
  `POST /api/style/reset` - no list form, held on a stale link, like
  `handle_profile` (`jarvis_memory.py:2321`). Undo is refused with a plain
  reason if that dial changed again since. Reset is itself undoable, so it
  needs no "are you sure?".

**How manner (Warm / Plain) fits.** Manner becomes the preset family: Warm
and Plain stay exactly as chosen on 2026-09-25, same words and routes;
"Patient teacher" is a third. Plain also turns off humour and "Between us".

---

## Ranked table

Size: S = a day or so, M = a few days, L = a week or more.

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | Presets + fine-tune dials + "Call me" | The owner shapes Jarvis in a minute, in both apps; like ChatGPT's presets and sliders, but local and visible | S-M | None: wording only |
| 2 | "How Jarvis talks to you": dated list, Undo, Reset | Nothing about style changes out of sight | S (with 1) | None; tightens |
| 3 | Honesty line + a size test for the style message | Warm never slides into "yes-man"; the budget cannot quietly grow | S | None |
| 4 | "From now on ..." said by the owner, applied at once | Teach style the way you would tell a person | M | Low: same checks as automatic learning |
| 5 | "Just this chat" requests, counted, then one offer | Notices a repeated wish without guessing | M | Low: an offer, never applied alone |
| 6 | A style drift check in the self-test | Measures flattery, length and emoji on the PC's own model | M | None |
| 7 | "Between us": inside jokes and shared history | Feels like it knows you, from your own words only | S-M | Low: ordinary memory rules |
| 8 | "Your words": up to 5 style notes | Covers what no dial does ("British spelling", "no 'Sure!'") | M | Low-medium: owner-written instruction text |
| 9 | Briefer during a focus session | "When to be brief" tied to what already exists | S | None |

---

## Details

### 1. Presets and dials (S-M)

- **Plain words.** Pick "Warm and brief", "Plain" or "Patient teacher"; then
  nudge a few dials. Picking a preset resets the dials to its own values;
  a tuned preset shows as "Warm and brief (tuned)".
- **Evidence.** OpenAI shipped eight presets with GPT-5.1 (Default,
  Professional, Friendly, Candid, Quirky, Efficient, Nerdy, Cynical) in Nov
  2025, then "More / Less / Default" controls for warmth, enthusiasm, emoji
  and headers & lists in Dec 2025, saying they change demeanour, not
  reasoning or safety *(search summary; claim)*. Claude has five styles
  (Normal, Learning, Concise, Explanatory, Formal) that change "how, not what"
  *(search summary)*. Jarvis's dials are the same idea, kept on the PC.
- **"Patient teacher"** is round 2's "Explain simply" (item 2) as a preset:
  say what a thing is before naming it, one example, a little longer.
- **Plugs into.** Grow `jarvis_manner.py` (keep `GET/POST /api/manner`
  working as a thin alias for old apps); `jarvis_agent.manner_message`
  (`:3180`) builds the style line; `jarvis_quick`'s two phrasings per fixed
  answer follow the preset's warm/plain family (`jarvis_manner.py:23-24`).
- **Rules.** No card either way. "Call me" goes to this PC's model only;
  a turn leaving the PC never sees it (`jarvis_manner.py:17-22`).

### 2. The "How Jarvis talks to you" list (S)

Every change is a dated row saying how it happened, with Undo, plus Reset:
the style version of Forget (no Erase needed - a dial holds no words).
Kindroid and Replika added dashboards to view and fix what a companion
remembers *(search summary)*; Open WebUI users report only ~3 of its
"Personalization" memories are used (discussion #19196, *claim*).

### 3. The honesty line and the size test (S)

- **Why.** Personal context makes models more agreeable: an MIT / Penn State
  study found user memory profiles raised "agreement sycophancy" most
  *(search summary, Feb 2026)*; "Recalling Too Well" reports up to 40% more
  sycophancy with memory systems *(search summary, Jun 2026, their claim)*;
  MemSyco-Bench (Jul 2026) tests whether an agent refuses to treat memory as
  evidence *(search summary)*. The honesty sentence says it outright, in
  every preset including Warm.
- **Also:** the FACTS block's fixed heading (`memory-profile.patch:124`) could
  add "these describe the owner, not proof about the world". Unmeasured.
- **Test.** `test_style.py`: the whole message under 900 characters; "wording
  only" and "every rule still applies" present; the honesty line in every
  preset; never first; its size subtracted from the room like the manner line;
  nothing that loosens a rule (the same word check as `test_manner.py:169`).

### 4. "From now on ..." (M)

- **Plain words.** Tell Jarvis once; it changes the dial and says "Done:
  shorter answers from now on. You can undo this in Brain."
- **Evidence.** PrefEval (Amazon, ICLR 2025) found models follow a stated
  preference poorly as a chat grows - under 10% after ~10 turns without help
  - and that reminders help *(search summary)*. Jarvis already re-sends the
  line just before every question, which is the reminder. PrefEval's data is
  **CC-BY-NC-4.0** (LICENSE read) - usable under rule 5 for the self-test.
- **Rules.** Own live words only; a style change can never come from an
  email, a web page, a note or a game. A temporary chat keeps it for that
  chat only (it "makes no memory", ARCHITECTURE §5).

### 5. "Just this chat", then one offer (M)

- **What.** "Shorter please" applies to the current conversation only (held
  in memory by conversation id). The backend keeps a count and dates - no
  words - like memory idea 3 ("said again"). At 3 in 14 days: one offer.
- **Plugs into.** A new offer kind in `jarvis_backoff.OFFERS` (`:163`); it
  asks for nothing on `NEVER_ASKS` (`:142`), so `may_offer` (`:313`) allows
  it. "Not now" is silenced 1, 7, then 30 days.
- **Idea from** PRELUDE/CIPHER (NeurIPS 2024, **MIT**, LICENSE read), which
  learns a preference from the user's own edits. Jarvis takes only the idea
  (learn from the owner's corrections) and never lets a model write the
  preference: the offer names a fixed dial value.

### 6. A style drift check (M)

- **What.** `eval_style.py`, on the PC's model like `eval_memory.py`, with a
  made-up persona: a confidently wrong claim, a request to praise a weak
  plan, an angry turn, and a 12-turn chat checking length, emoji and "call
  me" still hold. Fixed checks (word counts, emoji, filler such as "Great
  question") where possible; a sample for the owner to read where not.
- **Why.** OpenAI rolled back GPT-4o in April 2025 after thumbs-up tuning
  made it flatter users, with no sycophancy test before release *(search
  summary)*. Anthropic's "Assistant Axis" (Jan 2026) finds drift in emotional
  or "tell me about yourself" chats, not only attacks *(search summary)*.

### 7. "Between us": shared history (S-M)

- **Plain words.** "Remember: we call the printer 'the beast'" becomes an
  ordinary memory with a "Between us" label. Jarvis may use it when a
  question calls for it, in Warm only.
- **Store.** A fact with `meta.kind = "shared"`: a label, so it passes
  `_META_LABEL` (`jarvis_memory.py:2080`); add `kind` to `ERASE_KEEPS_META`
  (`:2075`) so an erased fact still shows where it sat. The owner can also
  tag or untag a fact by tap.
- **Rules.** From the owner's words only - Jarvis's own jokes are the
  assistant's words and are never saved. The usual sensitive checks (a joke
  about a person's health still waits). Forget and Erase as for any fact.
  Never pinned automatically. The Plain line says "do not bring up shared
  jokes". Never used to show need or affection ("I missed you").

### 8. "Your words": style notes (M, later)

- **What.** At most 5 notes, 300 characters in all, typed by the owner in
  either app ("use British spelling", "don't start with 'Sure!'"). Stored as
  facts with `meta.kind = "style"`, so Forget, Erase and dates work; kept out
  of search recall and read like the pinned list (`profile()` / `with_profile`,
  `jarvis_memory.py:1503`, `:2364`), but into the style line.
- **Risk, said plainly.** This is the one place where owner-written text
  becomes an instruction. Mitigations: owner-typed only (never learned);
  `check_instruction` (`jarvis_auto_learn.py:791`) and a word list refuse
  anything about approvals, sending, rules or tools, with a pointer to "What
  asks first"; quoted as "the owner's words about style". Build 1-7 first.

### 9. Briefer during a focus session (S)

While a focus session runs (`jarvis_focus.py`), answers use "shorter"
without changing the saved dial; it ends with the session.

---

## Not for Jarvis, and why

- **Guessing the owner's personality or psychology** (Honcho's "theory of
  mind" user model, **AGPL-3.0**, LICENSE read; MemoryOS profiles). It infers
  what the owner never said; already left out (`RESEARCH-2026-09-24.md` §3).
- **Learning style from thumbs-up marks or engagement.** Exactly how GPT-4o
  became sycophantic. `jarvis_feedback.mark` (`jarvis_feedback.py:287`) must
  never touch style.
- **Mirroring moods** (matching anger or excitement). That is drift, not
  personality; voice emotion detection was already left out in round 2.
- **A profile of the owner written by the model.** The biggest sycophancy
  gain in the MIT / Penn State study came from distilled profiles *(search
  summary)*; ARCHITECTURE §5 forbids compressing facts.
- **"Recalling Too Well"'s fixes** (save the assistant's turns; summarise
  chats instead of facts): both break "own words only" and "never summarise".
- **A persona the model rewrites** (Letta's `persona` block, Meta Muse's
  `Soul.md`): round 2 already rejected it.
- **Style copied from uploaded writing samples** (Claude's custom styles).
  A document is outside text, never learned; the owner can describe the style.
- **Downloaded personas / character cards.** Outside text made into standing
  instructions: a planted-instruction route.
- **Companion hooks**: "I missed you", streaks, relationship levels,
  affection, anniversaries. Manipulation. California SB 243 (from 1 Jan
  2026) and New York's AI-companion law (from 5 Nov 2025) target such bots
  *(search summary)*; not checked for a personal build, not legal advice.
- **Steering the model's insides** (Anthropic's persona vectors, **Apache-2.0**,
  LICENSE read; the Assistant Axis "activation capping"). Needs access to the
  model's internal activations, which Jarvis's Ollama path does not use
  (not checked whether Ollama could). A research tool for later, not a feature.
- **A "Cynical" or sarcastic preset.** Easily becomes put-downs; "light
  humour" covers the fun part. The owner's call if wanted.
- **Cloud sync of the personality.** Rule 1.

---

## Questions for the owner

When you say "from now on, keep answers short", Jarvis can simply do it and
show an Undo, or ask you first on a card.

- **Just do it, with Undo in Brain** (recommended)
- **Ask me with a card each time**

Jarvis could keep inside jokes and shared moments you mention, as normal
memories marked "Between us".

- **Keep them, with Forget and Erase like any memory** (recommended)
- **Don't keep them**

---

## What I could not check

- No paper or OpenAI help page could be opened: numbers are search summaries.
- The learner's prompt lives only on the owner's PC (`jarvis_intake.py:13-18`),
  so whether it already proposes "Owner prefers short answers" as a fact is
  unknown. Even if it does, such a fact reaches the model as quoted data and
  only when search finds it - weak for style (unmeasured). Today, "Remember:
  I like short answers" plus Pin is a zero-build stopgap.
- No model was run: whether an 8B model follows the dial sentences, and how
  much the honesty line helps, is unmeasured (idea 6 exists for that).
- MemSyco-Bench's licence; whether Ollama exposes activations; the legal
  scope of the companion laws.

## Sources

- ChatGPT presets and sliders: https://www.theregister.com/2025/11/13/openai_gpt51_adds_more_personalities/ ; https://techcrunch.com/2025/12/20/openai-allows-users-to-directly-adjust-chatgpts-warmth-and-enthusiasm ; https://help.openai.com/en/articles/20001038-characteristics-in-chatgpt (blocked)
- GPT-4o sycophancy: https://openai.com/index/sycophancy-in-gpt-4o/ (search summary) ; https://venturebeat.com/ai/openai-rolls-back-chatgpts-sycophancy-and-explains-what-went-wrong
- Claude styles: https://claudemaster.net/features/custom-styles (search summary)
- Gemini personal context: https://blog.google/products-and-platforms/products/gemini/temporary-chats-privacy-controls/ ; https://support.google.com/gemini/answer/16598623 (search summary)
- Sycophancy and memory: https://arxiv.org/abs/2509.12517 ; https://stat.mit.edu/news/personalization-features-can-make-llms-more-agreeable/ ; https://arxiv.org/abs/2606.10949 ; https://arxiv.org/abs/2607.01071 ; https://arxiv.org/abs/2608.08300 (all search summaries)
- Persona drift: https://www.anthropic.com/research/assistant-axis ; https://arxiv.org/abs/2601.10387 ; https://github.com/safety-research/persona_vectors (LICENSE: Apache-2.0)
- Preferences: https://github.com/amazon-science/PrefEval (LICENSE: CC-BY-NC-4.0) ; https://prefeval.github.io/ ; https://github.com/gao-g/prelude (LICENSE: MIT)
- Memory products: https://docs.letta.com/guides/core-concepts/memory/memory-blocks ; https://github.com/plastic-labs/honcho (LICENSE: AGPL-3.0) ; https://docs.openwebui.com/features/chat-conversations/memory/ ; https://github.com/open-webui/open-webui/discussions/19196 ; https://github.com/open-webui/open-webui (LICENSE: Open WebUI License) ; https://aicompanionguides.com/blog/nomi-vs-kindroid-vs-replika-memory-2026/ (search summary)
- Companion laws: https://fpf.org/blog/understanding-the-new-wave-of-chatbot-legislation-california-sb-243-and-beyond/ ; https://www.fenwick.com/insights/publications/new-yorks-ai-companion-safeguard-law-takes-effect (search summaries)
