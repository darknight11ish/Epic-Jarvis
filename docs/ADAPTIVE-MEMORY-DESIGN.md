# Adaptive memory — design

Status: **DESIGN ONLY. NOT BUILT, AND NOT APPROVED TO BUILD.** The owner
approved this document being produced on 2026-10-06 (`CLAUDE.md`). He has not
approved building the feature, and nothing in this repository was changed to
make it work. Every number below is either quoted from a document that already
exists or was measured while writing this, and each says which.

**The recommendation, in one line: do not build it yet — the honest gain is
small, the one setting that would help more is already in the app and switched
off, and one measurement from your PC decides whether that changes.**

---

## 0. The thing with two names

This came out of a question about squeezing the KV cache, so start by
separating the two things, because their names sound alike and they are not
related.

**The KV cache is the model's working memory on the graphics card.** It is the
conversation the model is holding in mind *right now*, so it does not have to
re-read it on every new question. `HARDWARE-PROFILES.md:181-183` says it in
plain words: *"the 'KV cache' is the model's memory of the conversation so
far"*. It is rebuilt from the prompt on every turn and thrown away with the
model. (`ARCHITECTURE.md:1073` calls the same number *"the 4,096-token context
the primary model runs with today, re-read every turn"*.)

**What Jarvis remembers is a different thing entirely.** Facts, chat history,
Forget and Erase the words live in files on your disk — `memory.db` and the
encrypted `chat-history.db`. `chat-history.patch` and `jarvis_chat_log.py`
keep your chats *"encrypted in a file on THIS PC"*
(`chat-history.patch:175-179`). None of that is the KV cache, and none of it is
touched by anything in this document.

So: **putting a summary in front of the model changes what the model is
holding in mind for one answer. It does not change what Jarvis remembers.** The
two are separate, and this document is about the first one only.

## 1. What problem does this solve — in your words, and honestly

**What you lose today.** When a conversation runs long, Jarvis quietly forgets
the *beginning* of it. It still answers, and it does not say anything. The
earlier question and answer are simply not in front of the model any more.

That is not a suspicion; it is what the code does, in two places:

* **The app drops them.** The Jarvis bar's conversation is capped at ten
  question-and-answer pairs and 18,000 characters (`chat-history.js:66,103-105`;
  the phone's `ChatHistory.kt:113-116` is the same number for number). Past
  that, *"the oldest pairs go"* (`chat-history.js:50-51`).
* **The PC drops more.** Before sending, the backend drops whole earlier turns
  until they fit the budget (`jarvis_agent.py:3220-3253`, `fit_messages`).

**What you would gain.** Instead of *silently* losing those turns, you would
keep a short written note of them: *"Earlier: we settled on the second
plumber; the boiler is a Worcester 8000; you said not to call before 9am."*
Same saving in the model's working memory, but the compression is a *thing you
can look at* rather than a thing that happened behind your back. That is the
whole idea, and it is a good idea on its own terms.

**And the honest part.** Measured while writing this, on this repository's own
code and its own token counter (`jarvis_agent.estimate_tokens`,
`jarvis_agent.py:3198-3217`):

| Context the model really has | Tool list | Conversation that fits before turns are dropped |
|---|---|---|
| 4,096 | all 29 tools (the shipped default) | **1 turn of 10** |
| 4,096 | the short list, 9 tools | **3 turns of 10** |
| 16,384 | all 29 tools | **all 10 turns** |
| 32,768 | all 29 tools | all 10 turns |

(The script and its output are in section 8. The 29-tool list measures
**5,267 tokens** by the project's own counter; the short list measures
**1,398**; `_TEMPLATE_TOKENS` is 574.)

Read that table twice, because it says two different things:

1. **At 16K there is nothing left to win.** The ten turns the app is willing to
   send already fit. A summary would save tokens nobody is short of. If your
   PC runs at 16K, the honest answer to *"what do I lose today?"* is: **little,
   within one conversation.**
2. **At 4,096 — which is what your PC actually runs today
   (`MEASURED-2026-10-05-owner-pc.md:34-36`, `:55-60`) — Jarvis keeps about one
   exchange.** But the thing eating the window is **the tool list, not the
   length of the conversation.** The short list has been built since
   2026-09-27 and **ships off** (`jarvis_agent.py:4400-4403, 4458`), waiting for
   a tool test on your PC. Turning it on buys **~3,900 tokens** — nearly four
   times what summarising the whole conversation could buy, for one setting and
   no new code.

**So the honest framing is this.** Adaptive memory is a real improvement to a
real weakness. But it is not the first thing to reach for, and within one
conversation at 16K it may not be worth reaching for at all. What would have to
be true for it to be worth building is in section 10.

## 2. What gets summarised, when, and by what

**Which turns survive exactly.** The newest **three** exchanges, whole and
verbatim. That number is a proposal, not a measurement — see the open
questions in section 11.

Everything older than that, inside the same conversation, becomes one short
written paragraph.

**By what.** The **local model on this PC, and nothing else.** Rule 1 is not
bent here even slightly: chat words are yours and private, and they stay on the
PC. There is already exactly this pattern in the codebase, twice, and the
design copies it rather than inventing anything:

* `jarvis_chatbot.summarise` (`jarvis_chatbot.py:1988-2026`) writes an end
  summary *"on this PC from the conversation only. It is outside text: shown on
  screen, never learned from, never read aloud."*
* `jarvis_tag_suggest.py` already reads the owner's **own first six typed or
  spoken messages** of a few old chats, up to 1,500 characters per chat, and
  gives them to **this PC's own model** — checked loopback *and* not a cloud
  model by `jarvis_auto_learn.check_local_model`
  (`docs/JARVIS-API.md:16556-16559`; the rule is written down in
  `ARCHITECTURE.md:1556-1583`). Its own design deliberately excludes chats that
  read outside text, crisis chats, Live, support, chatbot and comparison
  records, and anything under a Forget/Erase hush.

**When.** Three candidate moments, and this is the main design choice:

1. **During the turn, just before answering.** Bad. It puts a second model
   call in front of every answer, and it changes the start of the prompt every
   single turn (see the prompt-cache cost in section 6).
2. **After the answer, on the turn's own thread.** The model is already loaded
   (`OLLAMA_KEEP_ALIVE=-1`, `MEASURED-2026-10-05-owner-pc.md:67-69`), the owner
   has moved on, and the background learner already runs about 45 seconds after
   the conversation goes quiet (`docs/research-audit-2026-09-28/report-optimization.md:5`).
   This is the best fit for the codebase, and it is what section 4 builds on.
3. **Overnight, with the tidy.** Cheapest and quietest — the same scheduler
   slot the overnight tidy already uses (`jarvis_tidy.py:70`, kind `tidy`,
   once a day, not while you are chatting, not in Quiet or Standby). But it
   only helps conversations you come back to the *next day*, and the
   compression you need is for the conversation you are *in*.

**What happens while the model is busy or asleep.** Nothing summarises. That is
the whole answer, and it is a good one: every candidate moment above is already
gated on the model being free, and `jarvis_tidy.py` and `jarvis_tag_suggest.py`
both decline to run rather than queue up. The conversation keeps working the
way it does today — the app drops its oldest turns, the backend trims to fit —
and the summary catches up when the PC is idle. **A missing summary must never
be a reason an answer fails or waits.**

**Where it would live in the code — this is the part the design has to be
exact about.**

Today, one turn is built like this:

1. **The app builds the conversation.** `jarvis-desktop/src/chat-history.js`
   `historyMessages(window)` (`:149-156`) turns the window of exchanges into
   `messages`; `jarvis-desktop/src/main.js:3472` splices it in with
   `...historyMessages(state.conversation)`. The phone does the same in
   `ChatHistory.kt`.
2. **The PC adds memory and notes.** `memory-prefix.patch:59-109` inserts the
   recalled-facts system message **just before the newest user message** —
   `messages[:-1] + [recalled, messages[-1]]` — deliberately late, so the start
   of the prompt stays byte-identical and Ollama can reuse what it has already
   read.
3. **The PC trims to fit.** `jarvis_agent.py:6709`:
   `dress_messages(fit_messages(clear_old_tool_results(msgs, room), room), …)`.
   `fit_messages` (`:3220-3253`) drops the oldest earlier turns until the total
   is at or under `budget() * 0.75`, and **never drops a system message**
   (`:3237-3238`).
4. **`budget()`** is `jarvis_agent.py:6667-6670`:
   `max(512, n_ctx - max_tokens - _TEMPLATE_TOKENS - estimate_tokens(offer["schemas"]))`.

**So summarising has two possible slots, and only one of them is any good.**

* **Slot A — the app, in `historyMessages`.** The window is compressed before
  it is ever sent. This is the right place, because the app is the thing that
  decides which turns exist. It needs the summary to be *available to the app*,
  which means the PC has to be keeping it and the app has to be reading it —
  the chat-history routes (`GET /api/history/conversation`,
  `docs/JARVIS-API.md:3563`) already read a kept conversation, and they are the
  natural place to carry it.
* **Slot B — the PC, inside `fit_messages`.** Cheaper to write, and wrong: the
  PC can only *drop* what the app sent, it cannot put older turns back, and
  anything it adds as a system message is **exempt from trimming**
  (`jarvis_agent.py:3224-3225`) so it would eat the window permanently.

## 3. What you see and control

**A card, before anything is kept — and it should follow the overnight tidy's
rule, not the "save it and list it" rule.**

The overnight tidy's own rule is the strictest one in the project:
**"Cards only: nothing in memory changes by itself"** (`jarvis_tidy.py:1-3`,
`docs/JARVIS-API.md:12423-12425`). The owner's words for it, recorded on
2026-09-26, were *"then the overnight tidy - cards only, never changing memory
by itself"* (`CLAUDE.md`).

**Summarising should follow that rule, for a reason that is specific to it.**
Automatic learning already saves facts without a per-fact yes — but a fact is
*something Jarvis remembers about you*, it is listed in both apps, and it has
Forget and Erase the words. A summary is **words the model wrote about your own
conversation**, and if it is wrong there is no Forget button for it: the
conversation it describes is gone from the window and only the summary is
speaking for it. Adding a second kind of derived text that quietly shapes
answers, with no card and no listing, would be a worse trade than the tidy's.
So:

* **Off by default.** Nothing is summarised until you switch it on. Turning it
  on is **one approval card**, the same shape as `chat_tags_suggest_on`
  (`docs/JARVIS-API.md:16568`) and `history_enable`
  (`chat-history.patch:174-179`).
* **Each summary is a card you can read**, in the ordinary review queue both
  apps already show — approve it, or deny it and keep the raw turns.
* **Turning it off is immediate** and leaves everything already kept alone, like
  the tidy's own off switch (`docs/JARVIS-API.md:12470-12474`).
* **The card shows the summary in full**, never a description of it. This is the
  same rule every other card in this project follows — *"Every URL and body in
  full - never a summary"* (`jarvis_home.py:699`), *"The literal, token-free URL
  - never a summary of it"* (`jarvis_notes.py:309`).
* **Where you would see it afterwards:** on the conversation itself, in
  History, with the compressed stretch marked — *"earlier questions here were
  shortened; tap to see them in full"*. **The original turns are never
  deleted.** The summary is an addition, not a replacement.
* **If the switch is off, or a summary was denied,** the app sends the raw turns
  and the oldest of them get dropped exactly as they do today. Denying a
  summary can therefore never make Jarvis remember *less* than it does now.

## 4. What must never happen

These are the guards. Each one is a rule the code has to enforce, not a note to
be careful.

1. **A summary is never learned from as a fact.** The learner reads the owner's
   own words and nothing else. The mechanism already exists:
   `jarvis_intake.owner_turns` skips anything that is not the owner's own typed
   or spoken words (`jarvis_intake.py:228-246`; `CLAUDE.md`, 2026-09-29: *"facts
   ... learned from the owner's own words only (never from web pages, emails,
   documents, notes or tool output)"*). A summary must be registered with the
   same provenance as `chatbot_summary` — outside text — and `jarvis_chat_log`
   already has the vocabulary for it (`jarvis_chat_log.py:175`,
   `CHATBOT_PROVENANCES`), as does `jarvis_tag_suggest`, which stores **no
   model output at all**, only opaque ids, counts and dates
   (`docs/JARVIS-API.md:16562`).
2. **A summary is never read aloud as though it were your own words.** Voice is
   already gated on where the answer's material came from — the owner's
   decision of 2026-09-27 (`CLAUDE.md:525-530`): answers that used web search,
   weather or home status are read aloud, and *"answers that used email,
   calendar, notes, documents, memory, or any tool not on that short list stay
   on screen."* A summary is *about* your words but is not them; an answer that
   leans on one belongs in the "stays on screen" list, and saying so is a
   one-line change to that list rather than a new rule.
3. **You can always tell what was compressed.** The conversation shows where the
   exact turns stop and the summary begins. There is no mode in which Jarvis
   quietly speaks for words it has compressed.
4. **A summary is never a fact, never a memory, never a note.** It does not
   appear in "What Jarvis knows about you", it cannot be pinned, it is not
   searched by `memory_search`, and `POST /api/memory/forget` has nothing to do
   with it. Forget keeps meaning what it means.
5. **A crisis turn is never summarised, and a conversation that held one is
   never summarised.** This is not a new rule invented here — crisis handling is
   the strictest thing in the project, and it is already built:
   * a crisis turn is **never learned from and never counted**
     (`jarvis_intake.wellbeing_skip`, `jarvis_intake.py:279-288`, and the
     crisis exclusion on the correction counter, `jarvis_agent.py:6697-6699`);
   * the chat is kept but titled **"A difficult moment"**, never with your words
     (`jarvis_chat_log.py:195-197, 1568-1578`);
   * it cannot be continued, forked or sectioned
     (`jarvis_chat_log.py:402, 422, 445`);
   * a crisis answer is said in the plain built-in voice, never an animal's
     (`jarvis_speech.py:2608, 2651-2652`);
   * `jarvis_tag_suggest` — the closest existing feature to this one — already
     excludes crisis chats by both the title *and* a fresh `_crisis_turn` check
     on the first messages (`docs/JARVIS-API.md:16558`).
   Summarising must re-use `jarvis_chat_log._crisis_turn` (`:636-654`) rather
   than inventing a second check, and it must exclude the whole conversation,
   not just the crisis turn — a summary of "the rest of it" would still be a
   model's words about a difficult moment.
6. **Nothing already erased or forgotten comes back.** `jarvis_tag_suggest`
   excludes anything under a Forget/Erase hush (`docs/JARVIS-API.md:16558`).
   A summary built from turns whose fact was erased would put those words back
   in front of the model by the side door.
7. **Temporary chats and games are never summarised.** They are not kept at all
   (`docs/JARVIS-API.md:3503-3506`, `jarvis_chat_log.py:1464-1488`). A summary
   kept for one would be the first thing ever kept from a temporary chat.
8. **A summary never acts.** It reaches no tool, sets nothing, and cannot be the
   reason a card is raised. It is text in a prompt and nothing else.
9. **It must never be the reason an answer fails.** No summary, a failed
   summary, a model that is asleep: the turn goes ahead exactly as it does
   today. Every existing caller of this shape is wrapped in `try/except` for
   exactly this reason (`chat-history.patch:124-130`).
10. **It never leaves the PC, and it is never logged in words.** Audit lines
    carry ids, counts and outcomes, never a title and never a summary
    (`docs/JARVIS-API.md:16562`).

## 5. How it is measured, before and after

**The project's rule, and this document does not get an exemption:** *"Every
memory or learning change must beat the memory self-test
(`backend/eval_memory.py`) and the learner test (`backend/eval_learner.py`)
before it is kept; a change that makes a number worse is not kept. Numbers from
the real model come from the owner's PC (one PowerShell line), and are written
on a memory scoreboard page after each change."* (`CLAUDE.md`, 2026-09-26;
restated in `docs/MEMORY-SCORES-2026-10-04.md:3-7`.)

**No claim about tokens or memory saved may appear in this document or in the
build without a measurement.** Everything in section 1 is measured and labelled
as measured; the "three exchanges kept exactly" in section 2 is labelled as a
proposal.

**Before.** Run and record, on the owner's PC:

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
$env:PYTHONIOENCODING = "utf-8"
py -3 backend\eval_memory.py --learner-model qwen3:8b
```

That is `docs/MEMORY-SCOREBOARD.md:22`, and it is the same command that produced
the 2026-10-04 rows. The current known numbers, so a change can be compared
against something:

| What | Number | Where |
|---|---|---|
| Recall@5, 71 facts, word floor on | 94.7% | measured 2026-10-05 (this worktree, `--sizes 0`) |
| Recall@5, entity layer on | 97.9% | same run |
| Two-fact questions: all found | 10/10 | same run |
| Time questions: wrong older version | 0 | same run |
| Learner cases (model-free) | all rows 0 wrong | same run: reads 6/6, remember 4/4, dates 8/8, gate 37/37, said-again 14/14, true-from 12/12, moves 10/10, true-until 12/12, topic 13/13 |
| Overnight tidy finder | precision 1.0, recall 1.0 (stand-in model) | same run |
| Recall@5 at 71 facts, recorded 2026-10-04 | 95.7% → 94.7% | `docs/MEMORY-SCORES-2026-10-04.md:48-55` |

**After.** `eval_memory.py --against <the earlier .json>` — its own comparison,
which exits non-zero when recall@5, a wrong version or a learner case gets
worse (`eval_memory.py:7-9`).

**But `eval_memory` cannot measure this feature, and saying so is the point.**
It measures *memory search* — "does search find the right saved fact?" It has
never measured a conversation's context window. Adaptive memory needs a **new**
test, and until that test exists there is no number and therefore no claim. What
that test has to answer, each with a pass/fail bar decided before it is run:

1. **Does a summary keep an answer right that dropping the turns would break?**
   A scripted long conversation with facts stated early ("the boiler is a
   Worcester 8000") and asked late. Compare: (a) turns dropped, no summary —
   today's behaviour; (b) turns dropped, summary present. Count right answers.
   This is the only test that can justify the feature.
2. **Does the summary ever add something that was not said?** Every claim in a
   summary is checked against the source turns. This project's bar for the tidy
   was **precision 0.8** (`docs/MEMORY-SCOREBOARD.md:70-72`); a summary that
   invents a fact is worse than one that leaves it out, so the bar here should
   be **precision 1.0 and a measured recall**, both reported.
3. **How many tokens does it really save?** `jarvis_agent.estimate_tokens` on
   the same conversation with and without, at each context size. Reported, not
   assumed.
4. **What does it cost in seconds?** The summary call's own wall time, and
   whether the next question is slower because the prompt's start changed
   (see section 6).
5. **Do the memory numbers move at all?** The `--against` comparison above.
   If a summary is leaking into memory, this is where it shows.

**Where the numbers go:** a new page beside `docs/MEMORY-SCOREBOARD.md`, and
rows added to it after each change. Not into this document.

## 6. What it costs

**Graphics memory: nothing extra, if the summariser is the model already
loaded.** `OLLAMA_KEEP_ALIVE=-1` holds `qwen3:8b` at 5.6 GB permanently
(`MEASURED-2026-10-05-owner-pc.md:33-36, 67-69`). A summary using *that* model
adds no weights. What it does add is a **second use of a single-slot model**:
Ollama keeps one conversation in mind at a time, and a summary call evicts the
chat's own working memory. That cost already exists — the background learner
does exactly this today and the audit wrote it down as *"Background learner
evicts chat KV cache"*, estimated *"+1-3 s first word after a pause"*
(`docs/research-audit-2026-09-28/report-optimization.md:5`). Summarising after
the answer, on the same thread, adds to a cost that is already being paid; it
does not invent a new one. **Not measured on the owner's PC** — the 1-3 s figure
is the audit's own estimate, labelled as one.

**Time: roughly one extra model call per conversation that crosses the
threshold.** A summary of a few hundred words with `num_predict` around 600, the
same shape as `jarvis_chatbot.summarise` (`jarvis_chatbot.py:2003-2010`), is a
few seconds on this card. It happens after the answer, so you do not wait for
it — unless it steals the slot from your next question.

**The prompt-cache cost, which is the real technical risk and is easy to miss.**
Ollama reuses what it has already read **only up to the first token that
differs**. The whole reason the recalled-facts block was moved late was this:
*"a changing position 0 means the whole conversation is re-prefilled every turn"*
(`memory-prefix.patch:66-79`), costing about **3.1 s per 6,000 tokens**
(`docs/MODEL-TOPOLOGY.md:256`, `docs/feasibility-2026-09-26/devil.md:36`). A
summary is, by construction, a different text every time it changes — and it
sits *before* the kept turns. **A summary that changes on every turn therefore
costs a full re-read of everything after it, and can be slower than the turns it
replaced.** The answer is to compute it only when it changes materially and to
keep it byte-identical in between, which is a real constraint on the
implementation and is why slot A in section 2 has to hand the app a *stable*
string. Not measured: how often a summary would really change.

**Complexity: the largest cost, and the honest one.** This is not a small
change. It touches:

* both clients — `chat-history.js` + `main.js` (desktop) and `ChatHistory.kt`
  (phone), whose numbers are held equal by contract
  (`tools/gen_history_cases.py`, `history-cases.json`; the phone test asserts
  them, `HistoryContractTest.kt:286-287`);
* the backend — a summary store, the summary call, the card, a gate action, a
  switch, and a route (or an extra field on `GET /api/history/conversation`);
* `tools/check_parity.py` (a new route is either ported to both apps or
  recorded as deliberate);
* `scripts/apply-patches.ps1` and `backend/_where.SHIPPED` if any of it ships
  as a file;
* a new test module and a new eval.

**The cost of being wrong.** A summary that drops the one thing you needed is
worse than the silent trimming it replaces, because it *looks* like memory. The
mitigations in section 4 (cards, originals never deleted, off by default,
never learned from) are what make the worst case *"Jarvis forgot, and told me
so"* rather than *"Jarvis confidently said a wrong thing about my own
conversation."*

## 7. The risks, each with its mitigation

| Risk | Mitigation |
|---|---|
| **A summary drops something you needed.** The boiler model, the name, the number you gave at the start. | The newest N turns stay exact. The card shows the summary and you can deny it. **The original turns are never deleted** — the conversation can always be read back in full in History. And a summary that loses something is only ever a *loss of context*, never a wrong claim (rule 1 and rule 4). |
| **A summary drifts over months.** Each new summary is written *from the previous summary plus the newest turns*, so an early mistake compounds and eventually nothing in it can be traced to anything you said. | **Summarise from the original turns, never from a previous summary.** The originals are in `chat-history.db` (`/api/history/conversation`). If they have aged out under `keep_days` (`chat-history.patch:48-49`), the summary is dropped with them rather than re-summarised. A chain of summaries is the failure mode this rule exists to prevent. |
| **Two summaries compounding.** Two summaries both claiming to describe the same stretch, in the same prompt. | **One summary per conversation, replaced, never appended.** Versioned like the tutorials' progress record (`docs/TUTORIALS-DESIGN.md:112-124`), so a summary written under an older rule is re-offered rather than trusted. |
| **A crisis or sensitive turn being summarised.** | Section 4 rule 5: a crisis turn, and the whole conversation that held one, is never summarised — re-using `jarvis_chat_log._crisis_turn`. Sensitive facts follow the existing rules unchanged (`CLAUDE.md`, 2026-09-24: sensitive facts stay on screen). |
| **A summary being learned from as a fact.** The single worst outcome: the model's paraphrase of your words becomes a saved fact about you. | Section 4 rule 1: outside-text provenance, and `jarvis_intake.owner_turns` already refuses anything that is not your own typed or spoken words. A test must prove a summary cannot produce a card. |
| **A summary read aloud as your own words.** | Section 4 rule 2: any answer leaning on a summary stays on screen. |
| **A summary putting back words you erased.** | Section 4 rule 6: the Forget/Erase hush excludes the conversation, the same rule `jarvis_tag_suggest` follows. |
| **The re-read cost making things slower, not faster.** | Only recompute when the summary materially changes; keep it byte-identical in between (section 6). The speed record already measures reused-vs-read tokens (`jarvis_speed.py:545-566`), so this is checkable on the PC before it is trusted. |
| **The switch being on and the model never free.** | Every candidate moment is already gated on idle, on the one scheduler, and on the back-off (`jarvis_tidy.py:46-49`). A summary that never happens leaves today's behaviour exactly as it is. |
| **This being built and not helping.** | Section 10: the measurement in section 5 test 1 is the gate. If it does not pass, the code is not kept — the project's standing rule. |

## 8. The measurements behind section 1

Run while writing this, on this worktree, with the repository's own code:

```powershell
cd "C:\Users\pcadmin\Documents\jarvis-admem"
py -3 scratchpad\admem\budget_measure.py
```

```
jarvis_agent: C:\Users\pcadmin\Documents\jarvis-admem\backend\jarvis_agent.py
offered_tools(None) = 29 tools
DEFAULT_MAX_TOKENS = 1024
DEFAULT_CONTEXT    = 4096
_TEMPLATE_TOKENS   = 574
the ten exchanges  = 2130 tokens

every tool (the shipped default): schemas = 5267 tokens
  budget() = max(512, n_ctx - max_tokens - _TEMPLATE_TOKENS - schemas):
    n_ctx=  4096 -> budget=   512 -> 1 of 10 turns kept
    n_ctx= 16384 -> budget=  9519 -> 10 of 10 turns kept
    n_ctx= 32768 -> budget= 25903 -> 10 of 10 turns kept

the short list (ships off): schemas = 1398 tokens
  budget() = max(512, n_ctx - max_tokens - _TEMPLATE_TOKENS - schemas):
    n_ctx=  4096 -> budget=  1100 -> 3 of 10 turns kept
    n_ctx= 16384 -> budget= 13388 -> 10 of 10 turns kept
    n_ctx= 32768 -> budget= 29772 -> 10 of 10 turns kept
```

The script is kept (`scratchpad/admem/budget_measure.py`) so the numbers can be
re-run rather than taken on trust. It imports `jarvis_agent`, calls the
project's own `estimate_tokens`, `offered_tools`, `_new_offer`/`_fill_offer`
and `fit_messages`, and prints; it writes no file and asks no model anything.

Two notes on reading it. `estimate_tokens` is deliberately pessimistic — *"3
characters a token (English is nearer 4)"* (`jarvis_agent.py:3198-3200`) — so
the real numbers are somewhat kinder. And `budget=512` is the **floor** in
`budget()`; when the arithmetic goes negative the loop is left with 512 tokens
and *"1 of 10 turns kept"* follows from that, not from the conversation being
too long.

The `--sizes 0` memory self-test was also run (464.3 s, report at
`%TEMP%\admem-eval\memory-eval-20261005-231401.md`) and its numbers are in
section 5.

**The one thing this machine cannot measure:** how long *your* conversations
actually are. That is the number that decides whether any of this is worth
building, and it is on your PC, not here.

## 9. What would have to be built, if it is built

In order, and each step is its own piece of work:

1. **The eval first** (`backend/eval_adaptive_memory.py`), because the project's
   rule is that nothing is kept without a number. Scripted conversations, the
   two comparisons, precision and recall on the summaries, and token counts from
   `estimate_tokens`. **If this cannot be made to show a real gain, stop here.**
2. **The summariser, backend only**, off by default, one model call on the
   scheduler, from the original turns, writing to a sealed store the way
   `jarvis_tag_suggest` writes its `meta` — ids, counts and dates, plus the
   summary itself, which is new. The rule in `ARCHITECTURE.md:1578-1580` —
   *"no index, no summary, nothing kept beside the encrypted file"* — **would
   have to be amended**, exactly as the overnight tags amended the "nothing
   hands past chat words to the model" rule. That amendment is the owner's to
   make, in writing, before any of this is built.
3. **The card and the switch**, in `jarvis_gate.py`'s action list and
   `jarvis_asks_first`, with the words written once and mirrored by both apps
   the way `tools/gen_history_cases.py` does it.
4. **The read path**, so an app can get the summary for a conversation —
   `GET /api/history/conversation` gaining a field is cheaper than a new route,
   and `tools/check_parity.py` already lists that route as ported.
5. **The two clients last**, because they are the part that cannot be verified
   on this machine (no Android SDK; the desktop's DOM is proved by CI and by you
   opening it — `docs/TUTORIALS-DESIGN.md:24-29` says the same about its own
   build).
6. **A row in the memory scoreboard** and a line in `CLAUDE.md`, after.

## 10. The recommendation

**Do not build it yet.** Reasons, in the order they matter:

1. **One measurement decides it, and it is free.** How many exchanges are in
   your *longest* typical conversation? History already shows the turn count for
   every kept chat (`/api/history` returns `turns`, `docs/JARVIS-API.md:1204`).
   If your longest chats are under about ten exchanges, the app's own cap is
   never reached and **there is nothing to summarise** — that is the end of the
   question, honestly.
2. **If the conversations *are* long, the short tool list helps far more, and
   it is already built.** It buys ~3,900 tokens on the very setup shown to keep
   1 turn of 10 — around four times what summarising can buy — for one setting
   and no new code. It ships off only because it is waiting for a tool test on
   your PC (`jarvis_agent.py:4400-4403`). **That test is the next thing to do,
   not this feature.**
3. **At 16K there is nothing to win**, and the measured advice already on the
   page is that 16K fits the 12 GB card with room to spare
   (`MEASURED-2026-10-05-owner-pc.md:61-65`). One environment setting gets you
   there without quantising anything.
4. **It amends a written rule.** *"no index, no summary, nothing kept beside
   the encrypted file"* (`ARCHITECTURE.md:1578-1580`). That is allowed — the
   tags feature did it — but it should be a deliberate trade for a measured
   gain, not a convenience.
5. **It is a large change** across both clients, the backend, the contract
   files and the patch stack, for a benefit that is currently unmeasured.

**What would change this answer**, and each of these is checkable:

* Your longest typical conversation is well over ten exchanges, **and**
* the short tool list is already on, **and**
* the context is already at 16K, **and**
* `eval_adaptive_memory.py` (step 1 above) shows that a summary keeps an answer
  right which dropping the turns breaks.

If all four hold, build it. If any one fails, there is a cheaper answer.

**A second, smaller thing worth doing regardless:** the silent trimming itself.
Today, at 4,096 with the full tool list, Jarvis keeps about one exchange of your
conversation and says nothing (`fit_messages`). Whatever is decided about
adaptive memory, **saying so** — one quiet line, *"I have dropped the start of
this conversation to make room"* — is small, honest, needs no model call and no
new store, and it is the part of this design's value that does not depend on any
of the above. It is offered here as a cheaper alternative, not as a substitute.

## 11. Open questions for the owner

Asked as multiple choice, and short. Two at a time is the rule; these four are
listed together only because they can all be answered at once.

**Q1. The measurement first.** Before deciding anything: roughly how many
questions and answers are in your longest usual chat with Jarvis?

* **I will check History and tell you** (recommended) — History shows the turn
  count on every kept chat; that single number decides this whole document.
* **Under about ten** — then there is nothing to summarise; leave the cap alone.
* **Well over ten, often** — then the three questions below matter.

**Q2. The cheaper fix first.** The short tool list is built and switched off. It
gives back about four times the room that summarising can, for one setting.

* **Run the tool test and turn it on if it passes** (recommended) — it is the
  project's own next step for it, and it is a measurement rather than a guess.
* **Leave it off for now.**

**Q3. If it is built, how much should be automatic?** The overnight tidy's rule
is cards only; automatic learning saves facts without a per-fact yes.

* **A card per summary, off by default** (recommended) — the tidy's rule, and a
  summary has no Forget button to undo a bad one.
* **Write it quietly, and list it afterwards** — like automatic facts, with the
  conversation showing what was compressed.
* **Write it quietly and say nothing** — not recommended: it is the silent
  behaviour this feature exists to replace.

**Q4. The rule.** Building this amends *"no index, no summary, nothing kept
beside the encrypted file"* (`ARCHITECTURE.md:1578`). The overnight tags feature
did the same, deliberately, in writing.

* **Not yet — decide after Q1** (recommended).
* **Yes, amend it, for summaries only** — then step 2 of section 9 can start.
* **No** — then this feature cannot be built as designed, and the quiet-trimming
  line at the end of section 10 is the answer instead.

## 12. Not established

Written down rather than guessed at, because an honest gap is worth more than a
plausible sentence:

* **How long the owner's real conversations are.** Not measurable from this
  repository. History on the PC has the number.
* **What a summary would really cost in seconds**, and how often it would
  change enough to force a re-read. Both are estimates here, labelled as such.
* **Whether a summary helps at all.** This is the point of
  `eval_adaptive_memory.py`, which does not exist yet. **Until it does, the
  feature has no measurement and therefore no claim** — which is the project's
  rule and the reason this document recommends against building first.
* **`jarvis-primary`'s own `num_ctx` as your model really loads it.** The
  Modelfile asks for 16384; the last measurement of the running machine saw
  4096 (`MEASURED-2026-10-05-owner-pc.md:34-36`). Why the deployed model is at
  4096 is explained in `docs/MODEL-TOPOLOGY.md:48-64` (Ollama's own ladder, and
  the OpenAI-compatible endpoint having no field to set it), but **which of the
  two is true right now, on your PC, was not re-measured while writing this.**
  One line settles it: `ollama ps`.
* **How many of the 29 tools are actually enabled in your
  `jarvis-framework.toml`.** The 5,267-token figure is for the shipped default
  set. A smaller enabled list changes the table in section 1, not its shape.
* **Whether the phone should summarise at all.** The design assumes the PC does
  it and both apps read the result, because a client must not do
  speech-to-text and the phone has no model. Not decided.
* **Where exactly the summary is stored.** Section 9 proposes the chat-history
  file's own sealed store. Whether it belongs there or in a third store of its
  own is a build-time decision, not a design one.

## 13. Sources

Every claim about behaviour above is a file and a line in this repository.
The documents leaned on hardest:

* `CLAUDE.md` — the owner's decisions, the five rules, the beginner-facing voice.
* `docs/MODEL-TOPOLOGY.md` — the context ladder, the prompt-cache cost, the
  budget arithmetic.
* `docs/MEASURED-2026-10-05-owner-pc.md` — the only real measurement of the
  owner's machine: 4,096 context, the model on the 12 GB card, `KEEP_ALIVE=-1`.
* `docs/ARCHITECTURE.md` §5 — the memory rules, and the *"no index, no summary"*
  line this design would amend.
* `docs/JARVIS-API.md` §18 (chat history), §78 (the overnight tidy), §104
  (overnight suggested tags — the closest existing feature).
* `docs/MEMORY-SCORES-2026-10-04.md` and `docs/MEMORY-SCOREBOARD.md` — the rule
  that a memory change must beat a number, and the current numbers.
* `backend/jarvis_agent.py` — `estimate_tokens`, `fit_messages`, `budget()`,
  the crisis exclusions.
* `backend/jarvis_wellbeing.py`, `backend/jarvis_intake.py`,
  `backend/jarvis_chat_log.py` — how a crisis turn is treated.
* `backend/memory-prefix.patch`, `backend/chat-history.patch` — where memory
  and the record enter a turn.
* `jarvis-desktop/src/chat-history.js`, `jarvis-client/.../net/ChatHistory.kt` —
  the window an app actually sends, and its own token budget.
