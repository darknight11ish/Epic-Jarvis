# Review #1 — the prompt stack, measured (2026-10-23)

**What this page is.** The owner's work order of 2026-10-23, section 1, asked for
a checker that would prove Jarvis's prompt stack fits in a 16,384-token window
under a "3,600 / 4,500 token cap". A first audit (agent scratch,
`.dsh-scratch/REVIEW-1-PROMPT-STACK-2026-10-23/REPORT.md`, not in a clone) read
the real code and found most of those numbers do not exist. This page is the
measured version: every block, where it is built, how big it is, and what is
actually wrong.

**The tool is real.** `tools/measure_prompt_stack.py` imports the shipped
`backend/jarvis_agent.py` and asks the code for its own strings and schemas. It
does not carry a table of numbers. Its tests
(`backend/test_measure_prompt_stack.py`, 43 checks) prove the numbers follow the
catalogue: adding a tool to a fixture changes the reported cost, and a comment
that lies about the tool count fails `--check`.

## The answer in one paragraph

The stack is **bigger** than the work order says, not smaller. A usual local turn
is about **3,520** estimated tokens before the conversation starts; a worst case
with every note that can stack plus the whole tool catalogue is about **10,085**;
a drafting turn can reach about **14,158**. The tool schemas alone are **6,734**
(7,101 with `more_tools`) — the biggest block on every single turn. The number the
work order calls a cap, **3,800**, is the project's own *measured* ordinary prompt
of 2026-10-15 (**3,838** tokens, `docs/MODEL-TOPOLOGY.md:465`), rounded down; a cap
there would have failed the very turn the project measured and called fine. Two of
the six blocks do not exist at all. The one real defect is that **nothing puts a
floor under the tool schemas**, so on a small window a prompt can be built that is
larger than the window (section 3).

Every figure here is an **estimate** from characters in two ways: **E3** is the
repository's own `estimate_tokens` (characters ÷ 3, plus 6 tokens a message,
`backend/jarvis_agent.py:4385-4404`), **E4** is characters ÷ 4. They differ by about
a quarter. No tokenizer ships in this repository; real counts exist only where
Ollama reports them (section 4).

## 1. What the work order got wrong

| The work order says | The tree says | Where |
|---|---|---|
| "six blocks stack to ~5,304 tokens (32.4% of 16,384)" | Four exist, two do not, and the worst is 10,085 E3 | measured table below |
| "Pre-project cap 3,600 / project-mode cap 4,500" | No such cap exists anywhere. 3,838 is a *measured ordinary prompt*, not a ceiling | `docs/MODEL-TOPOLOGY.md:465` |
| "`qwen3.5:9b` runs with 16,384 context" | Three files disagree: the model file asks 16,384, the measurement says 4,096, the code falls back to 4,096 | `backend/jarvis-primary.Modelfile:119`, `docs/HARDWARE-PROFILES.md:7`, `backend/jarvis_agent.py:3944` |
| "Active skill instructions (`SKILL.md`, ~420 tokens)" | No such prompt block. `backend/jarvis_skills.py` does not exist; `jarvis-backend/jarvis_skills.py` installs and vets skill files but nothing in the agent injects one | `jarvis-backend/jarvis_skills.py`, `backend/jarvis_agent.py` (no import) |
| "`<project_workspace>` (~1,200 tokens)" | Absent from the shipped code: outside this review's own test, the one hit in `backend/` is a test function's name | `backend/test_auto_router.py:403` |
| "Sticky + top-K schemas: up to 9 tools, ~720–1,744 tokens" | 9 is right; the band is not. The 9 cheapest cost 737 E3, the 9 dearest 2,814; a chain may show up to 16 | `backend/jarvis_agent.py:6602`, `:6290` |
| "Recalled facts: 8 → 4" | There is no 8. The cap is 5 and it is already a setting | `backend/memory-prefix.patch:41` (`JARVIS_MEMORY_K`, default 5) |
| "Sticky tools `#587`/`#607`" | Sticky order shipped as `#671` (`899115a80`); `#607` is the tool diet (`1f3753778`); no #587 exists | `git log` |
| "Add `allocate_prompt_budget()`" | The allocator exists: `budget()`, `room`, `fit_messages`, the diet and the sticky list. A new one would duplicate it | `backend/jarvis_agent.py:9192`, `:9209`, `:4455`, `:6275`, `:6602` |
| "Tool descriptions overlap; add `Use when:` to each" | 16 of 34 already carry a "use that, not this" line; **0** begin with one. A header on all 34 would **add** ~600–790 E3 to a stack it is trying to shrink | counted on the shipped `TOOLS` dict |

## 2. The measured stack

E3 and E4 are both estimates (see the top). "When" is when the block can be sent.

| Block | Where it is built | chars | E3 | E4 | When |
|---|---|---:|---:|---:|---|
| Base persona + rules | `backend/jarvis_agent.py:7162` (`LANE_SYSTEM`) | 1,400 | 472 | 350 | every local turn |
| Chat-template reserve | `backend/jarvis_agent.py:7192` (`_TEMPLATE_TOKENS` = 574) | — | 102 | 77 | every local turn |
| Pinned facts (ceiling) | `backend/rebuilt/jarvis_memory.py:4779` (`PROFILE_LIMIT` = 1,200) | 1,256 | 424 | 314 | when facts are pinned |
| Recalled facts (top 5) | `backend/memory-prefix.patch:41` (`JARVIS_MEMORY_K` = 5) | 838 | 285 | 210 | when memory recalls |
| Voiceprint block (3 × 400 chars) | `backend/jarvis_voiceprint.py:630`, `:493` | 1,403 | 473 | 351 | drafting turns |
| Voiceprint block (3 × 4,000 chars) | `backend/jarvis_voiceprint.py:804` (`MAX_TEXT`) | 12,203 | **4,073** | 3,051 | drafting turns |
| **Tool schemas — all 34** | `backend/jarvis_agent.py:2053`, `:6977` | 20,234 | **6,734** | 5,059 | every turn with tools |
| Tool schemas + `more_tools` | `backend/jarvis_agent.py:6520` | 21,335 | **7,101** | 5,334 | every turn with tools |
| Tool schemas — the 8 core tools | `backend/jarvis_agent.py:6154` | 3,306 | 1,100 | 827 | a recognised question |
| Tool schemas — 9 cheapest / 9 dearest | `backend/jarvis_agent.py:6602` | — | 737 / 2,814 | — | a 9-tool carried list |
| Manner (warm) / + humour | `backend/jarvis_manner.py:110`, `:103` | 321 / 573 | 113 / 197 | 81 / 144 | almost always |
| Spoken-answer note | `backend/jarvis_agent.py:7745` | 400 | 139 | 100 | spoken turns |
| Jarvis Live note | `backend/jarvis_live.py:576` | 390 | 136 | 98 | Live turns |
| Focus-session note | `backend/jarvis_agent.py:7959` | 167 | 61 | 42 | a focus session |
| Cut-off answer note (longest) | `backend/jarvis_agent.py:8069` (`CUT_OFF_MAX` = 240) | 476 | 164 | 119 | after an interruption |
| Crisis help line | `backend/jarvis_wellbeing.py:174` | 458 | 158 | 115 | a crisis turn |
| Next-time reminder (one) | `backend/jarvis_next_time.py:323` | 396 | 138 | 99 | when one is due |
| Outside-text note | `backend/jarvis_agent.py:5113`, inserted `:9679` | 176 | 64 | 44 | after any tool runs |
| Prompt-dropped notice | `backend/jarvis_agent.py:4202` | 281 | 99 | 71 | after an overflow |
| Skills instructions (`SKILL.md`) | **not in this tree** | — | **ABSENT IN TREE — not measured** | — | never |
| Project workspace (`<project_workspace>`) | **not in this tree** | — | **ABSENT IN TREE — not measured** | — | never |

**Assembled:** a usual turn (rules, manner, memory recalling, 8 core tools, 1,024
tokens of answer) **≈ 3,520**; worst with tools (every note that can stack, all 34
plus `more_tools`) **≈ 10,085**; worst drafting (+ the 4,000-character voiceprint
block) **≈ 14,158**; a crisis turn (no tools are offered at all) **≈ 1,869**.

## 3. The one real risk: nothing puts a floor under the tool schemas

`budget()` computes the room the conversation gets by taking the output length,
the rules and **every schema** off the window, and clamps the answer at **512**
(`backend/jarvis_agent.py:9192-9195`). `fit_messages` then enforces that number,
but it **never drops a system message** (`:4455-4466`), and nothing shrinks the
tool list when the subtraction goes negative. So on a 4,096-token window the worst
stack is **246%** of the window: the model is sent more text than it can read, and
Ollama drops the oldest part of it **without saying so**. The owner then gets a
confident answer about a conversation the model no longer has.

This is arithmetic, not a guess: `budget()` clamp 512, schemas 7,101 E3, measured
above. The fix is a **floor rule**, not a new allocator: when the room left after
the rules, the answer and the schemas is below about 1,500 tokens, force the short
list for that turn. It is written out as an exact patch in
`.dsh-scratch/DOC2-PROPOSALS/prompt-stack-proposals.md` §P2 — **not applied here**,
because Session A owns `backend/jarvis_agent.py`.

## 4. What is NOT-TESTABLE from this repository

| Not testable here | Why | Settles it |
|---|---|---|
| The real worst-case prompt | The pinned facts, the exemplars and `[tools].enabled` are the owner's live data; only Ollama counts tokens | one real turn's `prompt_tokens` (command 2 below) |
| Which context the everyday lane runs | The model file asks 16,384; the measurement says 4,096; the code defaults to 4,096 | `ollama ps` (command 1) |
| Whether all 34 tools are enabled | `[tools].enabled`, `short_list`, `tool_diet` live in the live `jarvis-framework.toml` | `Get-Content "$env:USERPROFILE\.openjarvis\jarvis-framework.toml"` |
| A true per-block token count | No tokenizer ships; `estimate_tokens` is characters ÷ 3 | Ollama's `prompt_eval_count`, i.e. the `speed.jsonl` row |

**The two commands.** Run them in PowerShell on the owner's PC, with Jarvis
running. The first says which window is real; the second says what one turn really
cost.

```powershell
ollama ps
```

```powershell
Get-Content "$env:USERPROFILE\.openjarvis\speed.jsonl" -Tail 1
```

Ask a question that names no tool ("hello, how are you?") so the tool diet falls
back to the full list, then read the last row's `prompt_tokens`. That number is
the measurement every table above is an estimate of. `docs/MODEL-TOPOLOGY.md:465`
records one such measurement already: 3,838 tokens.

## 5. Reconciliation — every claim in the work order's section 1

| §1 claim | Verdict | Evidence |
|---|---|---|
| The six-block stack, ~5,304 tokens | **WRONG** | four exist; two are absent; measured 10,085 E3 worst |
| 3,800 / 3,600 / 4,500-token caps | **WRONG** | 3,838 is a measured ordinary prompt (`MODEL-TOPOLOGY.md:465`); no cap exists |
| `allocate_prompt_budget()` (Cog-1) | **ALREADY DONE**, in a different shape | `budget()` `:9192`, `room` `:9209`, `fit_messages` `:4455`, diet `:6275`, sticky `:6602` |
| The floor under the schemas | **MISSING** | `budget()` clamps at 512 `:9194`; proposal P2 |
| Disambiguate the four file/knowledge tools (Cog-2) | **PARTLY DONE** | 16 of 34 carry `instead=`; 0 start with a cue; proposal P3 |
| Replace stacked negatives (Cog-3) | **MISSING, and the owner's call** | 11 negatives vs 3 positive examples in `LANE_SYSTEM`; changes Jarvis's voice, so not shipped |
| A real `tools/measure_prompt_stack.py` | **MISSING** — the draft printed PASS from its own table; shipped here | `tools/measure_prompt_stack.py`, `backend/test_measure_prompt_stack.py` |
| The stale tool-count comments | **MISSING** — 23 and 31 against 34 | `jarvis_agent.py:6121`, `:6454`; proposal P1 |
| Skills block / `<project_workspace>` | **WRONG** (neither exists) | `jarvis-backend/jarvis_skills.py`; `test_auto_router.py:403` |
| 16,384-token context | **NOT-TESTABLE** | three files disagree (section 4) |

## 6. What shipped with this page

- `tools/measure_prompt_stack.py` — the checker, read-only, with `--json`,
  `--context N` and `--check` (structural drift only; it exits 1 today because
  the two stale comments are still there — that is finding F1, not a broken gate).
- `backend/test_measure_prompt_stack.py` — 43 checks, hermetic, and they bite: a
  fixture's catalogue is what gets measured, a lying comment fails `--check`, a
  broken import falls back and says so, and the two absent blocks are never 0.
- `.dsh-scratch/DOC2-PROPOSALS/prompt-stack-proposals.md` — the three patches for
  Session A to apply to `backend/jarvis_agent.py`, each proved with
  `git apply --check`, none applied here. **That file is agent scratch
  (`.dsh-scratch/` is gitignored), so it is not in a clone**; this page records
  what it proposes and why, and the patch is reproduced in the hand-off.
