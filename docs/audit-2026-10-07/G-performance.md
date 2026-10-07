# Stream G — Jarvis performance: latency, tokens, memory, loops, DB

**Target:** `.dsh-scratch/audit-main`, detached HEAD `fa2b379f` (merge PR #89, 2026-10-06).
**Source of truth:** `jarvis-backend/**` (the shipped modules) and `jarvis-desktop/src/**`.
`backend/**` is a byte-identical copy of most of the same files (same SHA-256 for
`backend/jarvis_agent.py` and `jarvis-backend/jarvis_agent.py`) — findings are quoted against
`jarvis-backend/` and every `.patch` mentioned is `backend/*.patch`.
**Read-only on product code:** nothing in the worktree was edited. Files written:
this report, plus two re-runnable measurement scripts at `.dsh-scratch/g-kv-measure.py`
and `.dsh-scratch/g-cpu-measure.py` (and their scratch dir `.dsh-scratch/g-cpu-tmp/`).

**Owner's units.** The everyday model is an 8B on an RTX 2060 12 GB; the model and the desktop
app share an RTX 2080 Super 8 GB. Everything below is ranked by what that owner feels: seconds of
pre-fill before the first word, extra GPU round trips, CPU work that runs *while* the model is
answering, and anything that grows with use.

**What I could and could not measure.** No Ollama and no browser in this container, so the
prompt's *rendered* bytes (the model's chat template) and anything WebGL/DOM are out of reach —
those are labelled traced or estimated, never measured. Everything labelled **measured** was run
here, on this machine, against the shipped Python.

---

## Ranked findings

| # | Area | Finding | Cost | Confidence | Fix size | Where |
|---|------|---------|------|------------|----------|-------|
| G1 | Chat turn / re-done work | Every question typed in the **HUD window** fires `/api/retrieve`, which rebuilds the whole brain corpus (all facts + up to 300 documents + **every Logseq page read off disk** + 600 entities) and scores all of it, for a screen decoration. The chat route already searched memory for the same query moments earlier. | **494 ms** to score a corpus at the shipped caps, + **29 ms** reading 300 Logseq pages — per question, on a parallel thread | **measured** | small (cache the corpus + the result) | `jarvis_hud.py:1969-1992` `:1889-1947` `:1838-1886`; caller `jarvis_hud.html:1770` |
| G2 | Chat turn / KV cache | The HUD window sends `S.messages.slice(-12)`. Past the 12th message the window slides by one exchange **every turn**, so the message part of the prompt differs from token 0 on every turn: **0 messages reused, ~680 est. tokens re-read per turn**, forever. The Jarvis bar's own window (chat-history.js) trims in blocks and keeps 10-18 messages reused. | ~680 est. tokens re-read per turn (measured message-level); seconds depend on G3 | **measured** | trivial (re-anchor in blocks) | `jarvis_hud.html:1787`; contrast `chat-history.js:137-139` |
| G3 | Chat turn / KV cache | Whether the **4,200-token tool block** and the rules precede the messages in the rendered prompt is **explicitly unverified in the repo's own comment**. It decides whether G2 costs ~0.7 s or ~5 s per turn — and the warm-up's value is capped by the same unknown. | 0.7 s/turn (tools first) vs ~5 s/turn (tools last) — estimated from the repo's own "3-4 s at 8K" for 3,000-4,000 tokens | **traced** (uncertainty is in the code) | none to fix — one line to settle it | `jarvis_agent.py:6203-6211`, `:6335-6348`; instrument `jarvis_speed.py:345-361` |
| G4 | Chat turn / re-done work | The recalled-facts block (and the manner/spoken/focus notes) is inserted just before the newest question and is **not echoed back by any client**, so a conversation's history is never byte-stable across turns: each turn re-reads the previous exchange as well as the new one. A per-conversation memory of the injected bytes would make the whole history reusable. | ~350 est. tokens/turn today (measured); ~0 after the fix | **measured** | medium | `jarvis_hud.py:4638`, `jarvis_agent.py:5867-5879` `:5805-5822` |
| G5 | Chat turn / round trips | One turn is **1 model call normally, up to 7** on a tool-heavy question (`max_rounds=6` + the forced final round), each re-sending tools + the whole conversation. On top, the background learner asks the same model again 45 s after talking stops — which the code itself says evicts the shared prefix on a one-card PC (the warm-up then re-reads it, ~3-4 s). | 7 round trips worst case; +1 learner call per quiet period | **traced** | by design; the learner already has its own switch | `jarvis_agent.py:6633` `:7206`; `jarvis_hud.py:931,934,1148-1188` |
| G6 | Front end | The HUD page does `node.textContent = full` **and** reads `scrollTop = scrollHeight` **on every streamed delta** — a forced synchronous layout per token. The Jarvis bar already fixed exactly this (100 ms throttle + one `requestAnimationFrame`). | one layout per token (~40/s) on a window that shares the GPU with the face | **traced** | trivial (copy the bar's `paint()`) | `jarvis_hud.html:1898` vs `main.js:877-928` |
| G7 | Warm path | The learner thread wakes **once a second, forever**, doing nothing when nothing has been said (`Event.wait(1.0)` → `continue`). Correct but not free; an untimed wait would be exact. | ~1 wake/s of an idle process — negligible CPU | **traced** | trivial | `jarvis_hud.py:1148-1151` |
| G8 | Databases | `jarvis_chat_log._connect()` runs `PRAGMA` + **4 × `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` on every connection**, and connections are opened per call, not pooled. | **2.0 ms** for four connections (measured) | **measured** | trivial | `jarvis_chat_log.py:860-878` |
| G9 | Memory / caches | `jarvis_memory._connect()` opens a fresh sqlite3 connection and **re-loads the sqlite-vec extension on every call** (36 call sites). | not measurable here (no sqlite-vec in this container); estimated well under 10 ms/turn | **traced** | small (one thread-local connection) | `jarvis_memory.py:1399-1441` |
| G10 | Chat turn | `reasoning_effort` is chosen **per question** (`auto` → none/low/high). If the model's template prints it into the system block (gpt-oss does; some Qwen3 templates do), every level change throws the whole prefix away. | unknown; full re-prefill when it flips | **traced risk, unverified** | none to fix — measure first | `jarvis_thinking.py:214-255`; `jarvis_agent.py:6289-6303` |
| G11 | Front end / face | Small objects are allocated per frame in `critter-pose.js` (`{}`, `new Array(9)`, `Object.assign({}, …)`). At 165 fps that is hundreds of tiny objects a second — **not** a bottleneck, and I would not change it. | negligible | **traced** | none | `critter-pose.js:1724,1759,1794,1842,1914` |

---

### G1. Every HUD question runs a second, whole-brain search — for a picture on screen

**Where.** The HUD page fires it the moment you press send, in parallel with the chat request
(`jarvis_hud.html:1770`, `traceFor` at `:1648-1660` → `GET /api/retrieve?q=…`), and the route
(`jarvis_hud.py:3174-3179`) calls `retrieve()` (`:1969`) which:

1. calls `retrieval_corpus()` (`:1889`) — **no cache anywhere**: `load_facts()` re-reads and
   re-parses `memory_facts.jsonl` (`:1552-1570`), then reads up to `MAX_DOCS = 300` documents from
   `memory.db` (`:1900-1911`), then `_logseq_corpus()` (`:1838-1886`) **globs the Logseq
   `pages/*.md` folder and reads every page file off disk**, then up to `MAX_ENTITIES = 600`
   entities out of `knowledge_graph.db` (`:1928-1944`);
2. runs `jarvis_recall.rank(query, [everything], top_k=len(corpus))` (`:1987-1992`) — every entry
   scored with stemming and an IDF pass, then a one-hop graph spread;
3. and the result is used **only** for the "what the brain reached for" trace, the little trail
   under the answer (`jarvis_hud.html:1653-1673`).

The chat route, moments later, searches the same store for the same question
(`jarvis_hud.py:4508-4510`). So the same question pays for a memory search twice, and the second
one is the expensive, unbounded one.

**Measured (this machine, shipped functions, corpus at the shipped caps):**

```
temp Logseq-like pages: 300 files x 2000 chars
glob + read 300 Logseq pages (jarvis_hud.py:1870-1877)     29.5 ms
                                                           -> 300 corpus entries, 600,000 chars
corpus for rank(): 1,600 entries, 1,255,580 chars
jarvis_recall.rank over the whole brain (jarvis_hud.py:1988) 494.1 ms
                                                           -> 1600 scored entries
load_facts(): parse the 400-row jsonl (jarvis_hud.py:1552) 1.0 ms
```

**Cost in the owner's units.** ~0.5 s of one CPU core per typed question, plus a directory walk
and 300 file reads, while the model is prefilling on the GPU. It is on a parallel thread
(`ThreadingHTTPServer`, `jarvis_hud.py:6511`) so it does not block the chat outright, but it holds
the GIL in bursts and does disk I/O during the exact window where the first token is being
produced. With a smaller Logseq graph and fewer documents it scales down; with a big vault it
scales up — the caps are 300 documents, 600 entities and *every* page.

**Fix (small).** Either (a) memoise `retrieval_corpus()` with a short TTL (it changes only when a
fact, note or document is written — an obvious invalidation point exists), and memoise the ranked
result by `(query, corpus version)`; or (b) better, have the chat route put the facts it *already*
selected into the `X-Jarvis-Route` header (numbers/ids only, up to 7) and draw the trace from that,
so the second pass disappears entirely. (b) also removes the duplicate search.

---

### G2. The HUD's 12-message sliding window throws the message prefix away every single turn

**Where.** `jarvis_hud.html:1787` sends `messages: S.messages.slice(-12)`, and `S.messages` is
never trimmed (`:1766` pushes the user turn, `:1936` the answer). So once a chat passes six
exchanges, every new turn drops one exchange off the front.

**Measured**, with the real assembly path (`jarvis_hud`'s lifted ordering expression +
`jarvis_agent.dress_messages`), 12 turns, `tools_for(None)` = all 30 tools:

```
### HUD page window: S.messages.slice(-12)
turn msgs prompt tok reused msg reused tok re-read tok  first difference
   1    4        724          -          -        6280  (first turn)
   2    5        352          0          0         352  after 0/5 messages (27 chars)
   3    7        424          2         76         348  after 2/7 messages (293 chars)
   4    9        510          4        156         354  after 4/9 messages (571 chars)
   5   11        539          6        217         322  after 6/11 messages (791 chars)
   6   13        652          8        284         368  after 8/13 messages (1029 chars)
   7   14        691          0          0         691  after 0/14 messages (27 chars)
   8   14        670          0          0         670  after 0/14 messages (27 chars)
   9   14        674          0          0         674  after 0/14 messages (27 chars)
  10   14        673          0          0         673  after 0/14 messages (27 chars)
  11   14        699          0          0         699  after 0/14 messages (27 chars)
  12   14        671          0          0         671  after 0/14 messages (27 chars)

### Jarvis bar window: chat-history.js MAX_EXCHANGES=10 -> KEEP=6
   7   15        705         10        353         352  after 10/15 messages
   8   17        765         12        430         335  after 12/17 messages
   9   19        845         14        507         338  after 14/19 messages
  10   21        907         16        573         334  after 16/21 messages
  11   23        998         18        638         360  after 18/23 messages
  12   15        686          0          0         686  after 0/15 messages

### CONTROL (not shipped): same 12-message cap, re-anchored in blocks
   7    9        488          0          0         488
   8   11        548          6        213         335
   9   13        628          8        290         338
  10    9        477          0          0         477
  11   11        568          6        208         360
  12   13        609          8        278         331

HUD page, 12 turns: 5822 re-read tokens of 7279 sent (80%)
```

"reused msg" counts leading messages that are byte-identical to the previous turn's, so it is a
*sound* reuse figure: anything it does not count cannot be reused at all. It is a *lower* bound on
real reuse, because Ollama also puts the Modelfile's SYSTEM block in front of both prompts and
that block is not in the request.

**Cost.** Turns 7-12 re-read the whole message window: 670-699 est. tokens per turn, ~680 average.
Note the first two turns also reuse nothing: turn 1 puts the recalled block at index 0 (nothing
precedes it), so turn 2's prompt starts with a user message where turn 1's started with a system
message. At the repo's own pre-fill figure ("about 3-4 s at 8K" for 3,000-4,000 tokens ≈ 1,000
tok/s) 680 tokens ≈ **0.7 s per turn** — but see G3, because the whole tool block sits on the same
knife edge.

**Fix (trivial, client-side).** Keep the same 12-message cap but **anchor the window start on a
block grid** — grow it, and when it would overflow, drop down to 6 messages (the control above),
which is exactly what `jarvis_agent.fit_messages` already does server-side for the same reason
(`jarvis_agent.py:3325-3327`: "it goes down to three quarters of the budget, so the start of the
prompt then stays the same for a few turns"). The control recovers 6-8 messages of reuse on four
of six turns.

**The HUD page is the odd one out — the other two clients already do it right.** The Jarvis bar
trims in blocks (`chat-history.js:137-139`, measured above: 10-18 messages reused). The phone does
the same (`ChatHistory.kt:178-180`: only when `fits(next, MAX_EXCHANGES, MAX_CHARS)` fails does it
`removeFirst()` down to `KEEP_EXCHANGES`) — and its own comment at `ChatHistory.kt:21` cites
`jarvis_hud.html`'s `S.messages.slice(-12)` as the thing it is modelled on, so the one place that
slides per turn is the one this audit can fix in a single line.

---

### G3. The one measurement that decides how bad the chat lag is: does the tool block come before the messages?

**Where.** `jarvis_agent.py:6203-6211` says it in the repo's own words:

> "NOT VERIFIED on a real Ollama: Ollama gathers every system message into one block
> (`template.go collate()`); if the model's chat template prints that block before the tool list,
> then a question with recalled facts, or a spoken one, starts differently from the warm-up before
> the tools, and on those questions only the rules are saved."

**Why it matters more than anything else here.** Measured sizes of the stable prefix:

```
rules block      : 1400 chars, ~474 tokens (estimate_tokens, 3 chars/token)
tools schema: 30 tools, 16756 chars, ~5556 tokens (estimate_tokens)
```

`estimate_tokens` is deliberately pessimistic (3 chars/token; English is nearer 4), so in real
tokens the tool block is closer to 4,200. The repo's own figure for "the rules and the tool list"
is 3,000-4,000 tokens ≈ 3-4 s of pre-fill on this card.

- If the template renders the tools **before** the messages (the usual shape), the divergence in G2
  costs ~0.7 s per turn and the prefix is doing its job.
- If it renders them **after**, the same divergence invalidates the tool block too, and every turn
  re-reads ~5,000 tokens ≈ 5 s — the difference between "Jarvis answers instantly" and "Jarvis
  thinks for five seconds first".

**How to settle it, on the owner's PC, one line** (already written down in
`docs/RESEARCH-AUDIT-2026-09-28.md:189-193`); `speed.jsonl` already records Ollama's own
`prompt_tokens_details.cached_tokens` per answer (`jarvis_speed.py:345-361`,
`jarvis_agent.py:5553-5607`):

```powershell
$f = Join-Path $env:USERPROFILE ".openjarvis\speed.jsonl"; Get-Content $f -Tail 40 | ForEach-Object { $r = $_ | ConvertFrom-Json; if ($r.prompt_tokens) { "{0}  prompt {1}  reused {2}  first word {3} ms" -f ([DateTimeOffset]::FromUnixTimeSeconds([int64]$r.at).LocalDateTime), $r.prompt_tokens, $r.cached_tokens, $r.first_word_ms } }
```

Ask three questions in a row in the HUD window, then again in the Jarvis bar. If `reused` stays
near `prompt` on the bar and collapses toward the rules-only size (`~500`) on the HUD after six
exchanges, G2/G3 are confirmed together and the fix order is: fix the HUD window first (trivial),
then re-measure.

**Same instrument answers G10** (`reasoning_effort` flipping per question): ask "hi" (level `off`
→ `"none"`) then a long analytical question (level `auto` → `"low"`/`"high"`) and watch whether
`reused` collapses on the second. The capability lookups themselves are already cached
(`_TOOLS_CACHE`/`_CTX_CACHE` 60 s, `jarvis_agent.py:3257-3288`; thinking capabilities 5 min,
`jarvis_thinking.py:53-55`), so they add no per-turn round trip.

---

### G4. The recalled block is in the right place, but the history is still not byte-stable

**What is already right — and I checked it the way the task asked.** The block is inserted
*late*, just before the newest question (`jarvis_hud.py:4587-4638`), not prepended, and its bytes
do not move with the clock: `_dated_fact` stamps a fact with **its own `created` time**, not "now"
(`jarvis_hud.py:362-394`), and the block's text is fixed words plus `recall_line`-sanitised fact
lines (`jarvis_auto_learn.py:2360-2371`). Assembling the same turn twice, 1.2 s apart, through the
shipped functions:

```
same turn, two assemblies 1.2 s apart: 18579 vs 18579 bytes
IDENTICAL: True
rules:    date/id-like tokens in the block: []
recalled: date/id-like tokens in the block: ['2025-09-30']   <- the fact's own created date
manner:   date/id-like tokens in the block: []
```

**Measured clean, and it is the thing that `memory-prefix.patch` was for.** A per-question block
whose bytes *did* move would still be fatal; it does not.

**What is still open.** No client echoes the injected system messages back (`chat-history.js:142-156`
builds history from question/answer pairs only; the HUD page pushes only `role: user`/`assistant`).
So the block that sat before turn N's question is simply **absent** from turn N+1's messages, and
the prompt diverges exactly where turn N put it. The measurement in G2 shows the size of that: at
turn 5, 6 of 11 messages are reused and ~322 est. tokens are re-read — the previous exchange plus
the new block and question. It is a *constant* overhead per turn, not a growing one, because
`fit_messages` trims in blocks. The same applies to the manner, spoken, focus, next-time, cut-off
and crisis notes, all of which are inserted at the same "just before the question" point
(`jarvis_agent.py:6240-6277`, `:5805-5822`, `:5867-5879`).

**Fix worth considering (medium).** The backend already receives a validated `conversation_id` on
every turn (`jarvis_hud.py:3470-3472`). Keep, per conversation (bounded, evicted like `_OPENED`
in `jarvis_agent.py:4651-4654`), the exact block bytes injected for each of the last N turns, and
re-insert them at the same indices when the client sends that conversation again. Then the entire
history is byte-identical turn to turn and only the newest block + question are new. This is a
real change to the hot path, so it needs the measurement in G3 first.

---

### G5. How many times does one turn ask the model? (1 normally, 7 at worst, plus the learner)

**Traced.** `jarvis_agent.py:6633` `max_rounds: int = 6`; the loop at `:7206-7238` runs
`range(max_rounds + 1)`, so **up to 7 requests to Ollama in one turn**, each carrying the tools
array and the whole conversation, each adding its tool result to the tail. Every round is a real
pre-fill + generation round trip on the owner's GPU. Tool-heavy questions ("check my email and
then…") are the ones where the owner waits; that is inherent to a tool loop, and the round count is
the knob.

**Traced, and already mitigated.** The background learner asks the model again 45 s after the owner
stops talking (`jarvis_hud.py:931` `EXTRACT_IDLE = 45`, `:1148-1188`), on the chat's own model on a
one-card PC — which, as the code says, pushes the shared prefix out of Ollama's single slot. The
mitigation is `jarvis_agent.warm_after_learning()` (`jarvis_agent.py:6597+`), which re-reads the
start on its own thread and is cancelled the moment a question arrives (`:6388-6420`). The 300 s
`EXTRACT_MIN_GAP` (`:934`) bounds how often this can happen.

**Nothing else per turn asks the model.** Checked and clean: the "I've done it" claim check is
pure Python (`jarvis_agent.py:7453`, `jarvis_claims.py` — no HTTP), the crisis check is phrase
matching (`jarvis_wellbeing`), the sneaky-instruction check is regex only — `jarvis_injection.py:25`
states "never calls a model, makes no network call, reads no file, writes nothing" (used at
`jarvis_agent.py:4197-4204`, advisory line only), the guess/struggle signals are in-memory, the
tool capability and context-length lookups are cached, and the memory re-ranker is fastembed **on
the CPU** (`jarvis_memory.py:710-762`), not a second Ollama call.

---

### G6. The HUD page lays the chat out once per streamed token

**Where.** `jarvis_hud.html:1898`:

```js
if(d){ full += d; node.textContent = full; $("log").scrollTop = $("log").scrollHeight; }
```

Every SSE delta rewrites the whole answer into one text node and then **reads `scrollHeight`**,
which forces a synchronous style/layout flush of the chat log before it can scroll. The log can
hold `THREAD_MAX = 100` messages (`chat-history.js:261`), so each flush is over the whole thread.

**Traced.** The sibling surface already solved this: the Jarvis bar's `paint()` coalesces to one
`requestAnimationFrame` and throttles to one parse per 100 ms, with a comment recording that
per-token painting was "parsing tens of kilobytes each" (`main.js:877-928`). The HUD page does not
use it.

**Estimated cost:** one forced layout per token at ~40 tokens/s, on a machine whose GPU is also
drawing the animated face. It will not make the answer slow; it is jank the owner can see while the
face animates. **Fix (trivial):** accumulate `d` into `full`, set a dirty flag, and do the
`textContent` write + scroll inside one `requestAnimationFrame`.

**Traced clean around it:** the answer in the Jarvis bar is painted on a 100 ms throttle
(`main.js:877-928`); the quickbar's history window is capped (`chat-history.js:66,103-105`); the
HUD's own trace list is capped at 8 (`jarvis_hud.html:1656`).

---

### G7-G9. Warm path and databases — three small, honest numbers

**G7 — the learner wakes once a second doing nothing.** `jarvis_hud.py:1148-1151`:
`if not self._woken.wait(1.0): continue`. Before anything has ever been said, this thread wakes 1×/s
and immediately waits again. Measured cost: nothing worth measuring (a timed condition wait). The
fix (`self._woken.wait()` untimed, woken by the turn handler) is one line. I list it only so the
owner knows it was looked at and is not the reason anything feels slow.

**G8 — the chat log rebuilds its schema on every connection.** `jarvis_chat_log.py:860-878` runs
`PRAGMA secure_delete = ON` plus four `CREATE TABLE IF NOT EXISTS` and one `CREATE INDEX IF NOT
EXISTS` **per `_connect()`**, and `_connect()` is called per operation. Measured:

```
chat-log _connect() x1 (jarvis_chat_log.py:860-878)        0.5 ms
chat-log _connect() x4 (one turn's writes+reads)           2.0 ms
```

2 ms per turn, once written. Not worth a patch on its own; worth doing if that file is touched.

**G9 — a fresh sqlite connection (and extension load) per memory call.**
`jarvis_memory.py:1399-1441` opens a new connection every time and, by design, re-loads the
sqlite-vec extension on each one (`:1424-1440` — the comment records the real bug that made this
necessary). 36 call sites. I could not measure the extension load here (no sqlite-vec in this
container), so the cost is **estimated** at single-digit milliseconds per chat turn; if a
thread-local connection is ever introduced, the extension still has to be loaded once per
connection, so this is only worth doing alongside G8. The *indexes* are right — see below.

---

### G11. The face's per-frame code: checked, and I would leave it alone

`critter-pose.js` allocates small objects per call (`{}` at `:1759`, `:1794`, `:1914`;
`new Array(9)` at `:1842`; `Object.assign({}, …)` at `:1724`). At 165 fps that is hundreds of tiny
young-generation objects a second — a V8 scavenge every few seconds, sub-millisecond. **Traced, not
worth changing** unless a profile says otherwise. The frame driver itself is already careful:
per-state frame rates (idle 30, standby 15, banked 2), vsync striding, `if(!s.vis) continue` before
any per-surface work, and a GPU-cost budget measured per frame (`faces.html:5800-5857`). The
browser pauses `requestAnimationFrame` when the window is not visible, so a hidden face is not a
background cost.

---

## Measured clean (paths I traced and found efficient — so the owner knows the audit looked)

| Area | Path | What I found |
|---|---|---|
| Prompt stability | `jarvis_hud.py:362-394` `_dated_fact`, `:4561-4586` block build | Bytes identical across two assemblies 1.2 s apart (18,579 = 18,579, measured). Dates come from the fact's own `created`, never "now". No id, no timestamp, no random ordering in the block. |
| Prompt ordering | `jarvis_hud.py:4587-4638` | The recalled block is inserted **late** on purpose, with the reasoning recorded in the code. The `memory-prefix.patch` bug (a changing token 0) is genuinely fixed, and `backend/test_memory_prefix.py` holds it. |
| Rules placement | `jarvis_agent.py:6129-6150` `keep_rules_first` | `LANE_SYSTEM` is byte-for-byte the Modelfile's SYSTEM block (`test_agent.py` holds it), so putting it at index 0 does not change the rendered bytes — it just stops Ollama dropping the rules. |
| Server-side trimming | `jarvis_agent.py:3317-3350` `fit_messages` | Trims down to 75% of the budget in one go so the prompt start "stays the same for a few turns" — the KV-friendly pattern the HUD window (G2) does not follow. |
| Tool-result clearing | `jarvis_agent.py:3543-3585` `clear_old_tool_results` | Rebuilt from the *untrimmed* conversation every round, so a cleared result stays cleared: the start of the prompt changes as little as possible. Deliberate. |
| Tool list order | `jarvis_agent.py:4671-4711` + `:4651-4654` | Fixed `CORE_TOOLS`/`TOOL_GROUPS` order, never the order groups were opened in, so two chats that opened the same groups send the same list; the per-conversation `_OPENED` map is capped at 200. |
| Capability lookups | `jarvis_agent.py:3257-3288`, `jarvis_thinking.py:53-55` | `/api/show` is cached 60 s, thinking capabilities 5 min — no per-turn HTTP round trip for "can this model use tools". |
| Per-turn Python | `jarvis_agent.py:7453`, `jarvis_claims.py` | The "I've done it" / claim check makes **no** model call. |
| Injection check | `jarvis_injection.py:25`, `jarvis_agent.py:4197-4204` | Regex only, advisory — no model call, no network, no file read. |
| Memory DB | `jarvis_memory.py:1552-1553` `:5168-5179` | Singleton store (the embedder and the sqlite-vec probe are built once); indexes `ix_facts_known(created, retired_at)` and `ix_facts_valid` exist; searches are `LIMIT`-bounded (`:2577`, `:2601`). Measured contrast on a 20k-row table: **7.4 ms** for the same query without the index, **0.3 ms** with it — the index the store already has. |
| In-process state | `jarvis_auto_learn.py:1094-1109` `_HUSH_MAX = 500`; `jarvis_agent.py:4651-4654` `_OPENED_MAX = 200`; `jarvis_hud.html:1656` traces capped at 8; `chat-history.js:66` exchanges capped | Every registry I found that is keyed by a conversation id or a growing value has an eviction rule. I found **no unbounded per-turn dict**. |
| Scheduler | `jarvis_schedule.py:1689-1703` | Event-driven: it waits until the next due job, capped at `TICK_MAX = 30 s` — not a per-second poll. |
| Import/startup | measured, this machine | `import jarvis_hud` 169 ms, `jarvis_sensitive` 181 ms, `jarvis_second_card` 97 ms, `jarvis_agent` 85 ms, `jarvis_quick` 84 ms, `jarvis_memory` 69 ms, and the big data modules are cheap (`jarvis_wakebank` 16 ms, `jarvis_stopword` 14 ms, `jarvis_sky_places` 3 ms, `jarvis_voicebank` 3 ms). Python startup is **not** the owner's felt startup — the model load is. |
| Streaming relay | `jarvis_hud.py:5277-5283` | Blocking `read1(1024)` → write → flush. No busy-wait, no re-serialisation. |
| Jarvis bar rendering | `main.js:877-928` | One `requestAnimationFrame` + 100 ms throttle for markdown + `innerHTML`; the correct pattern (G6 asks the HUD page to copy it). |
| Phone chat window | `ChatHistory.kt:113,173-181` | `MAX_EXCHANGES = 10` with a block trim down to `KEEP_EXCHANGES` only when it overflows — the same KV-friendly shape as the Jarvis bar, and unlike the HUD page (G2). |
| Face frame driver | `faces.html:5800-5857`, `:5834-5836` | Per-state frame rates, vsync striding, visibility check before per-surface work, GPU cost budgeted per frame. |

---

## What I could not settle here (and the exact next step)

1. **The rendered prompt's field order** (G3) — needs the owner's Ollama. One PowerShell line on
   `speed.jsonl` (given in G3). This is the highest-value five minutes available on this audit.
2. **`reasoning_effort`'s effect on the prefix** (G10) — same instrument, two questions that flip
   the level.
3. **The real `/api/retrieve` cost on the owner's data** (G1) — the measured 494 ms is at the
   shipped caps (300 documents, 600 entities, 300 Logseq pages); the owner's actual page count
   multiplies the file-reading part. `Get-ChildItem <logseq>\pages -Filter *.md | Measure-Object`
   gives the number in one line.
4. **The sqlite-vec extension load per connection** (G9) — sqlite-vec is not installed in this
   container, so the estimate stands unverified.

---

## Reproduce

```powershell
$py = "C:\Users\pcadmin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch"
& $py g-kv-measure.py      # prompt assembly twice + per-turn prefix reuse, both client windows
& $py g-cpu-measure.py     # Logseq read loop, whole-brain rank, chat-log connect, index contrast
```

Both scripts import the shipped modules unchanged (`jarvis_agent`, `jarvis_hud`,
`jarvis_auto_learn`, `jarvis_recall`) and lift `jarvis_hud`'s own `messages = …recalled…`
expression with `ast`, the way `backend/test_memory_prefix.py` does, so the ordering measured is
the ordering shipped. Nothing in the worktree was modified.
