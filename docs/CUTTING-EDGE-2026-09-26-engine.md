# Cutting-edge audit, 26 September 2026: the AI engine (local models and tool use)

This is one slice of the owner's cutting-edge audit: the model that answers,
how it uses tools, MCP (a standard way to plug outside tools into an
assistant), and screen-reading agents. **Research only. Nothing was built and
no code was changed.** It builds on `RESEARCH-2026-09-24.md` §6,
`MODEL-TOPOLOGY.md`, `HARDWARE-PROFILES.md`, `EXTRACTION-RESEARCH-2026-09-23.md`
(the MCP bridge design), the three competitor reports and
`CREATIVITY-AUDIT-2026-09-25.md`, and does not repeat them.

**How it was checked.** Jarvis read at commit `c78a04e`. Ollama's source read
at commit `7af3931` (24 Sept 2026, bundles llama.cpp `b11081`) - read, not run.
Other claims come from GitHub pages, release notes and web search. ollama.com,
huggingface.co, and most blogs are blocked from here, so model-card numbers
are **claims** and are marked that way. Nothing was measured on the owner's PC.

---

## Summary for the owner

1. **Two small fixes first.** If you switch to a model that cannot use tools, every question fails with a misleading "restart Ollama" error. And one Ollama setting (`OLLAMA_NO_CLOUD`) makes Ollama itself refuse its cloud models - a second lock behind rule 1.
2. **Measure before changing models.** Ollama now reports how much of each question it reused from memory ("prompt cache"). Jarvis should record it; the newer Qwen 3.5 models have had bugs here.
3. **Qwen 3.5 can answer ~1.5-2x faster with one line in its Modelfile** (a built-in "guess ahead" feature called MTP). That is a claim from other cards; it needs testing on yours, and Ollama has an open bug about it.
4. **Tools: fix wrong calls with a "fill in this form" retry, and teach the tool test to check "did it ask instead of guessing?"** Both are small.
5. **The MCP bridge should wait for a slimmer tool list.** Jarvis's 23 tools already take about 2,700 words' worth of the model's memory; one MCP server can double that. Hide rarely used tools until asked for.
6. **Screen-clicking by picture (not by button name) fits Jarvis only as a "pointer" inside today's one-card plan,** on the 12 GB card, never as a loop that keeps clicking by itself.

---

## Ranked list

Size: S = one module plus tests; M = several files, maybe a line in both apps;
L = a new subsystem. Card: which graphics card it needs.

| # | Idea | Why it matters | Size | Card | Rule risk |
|---|---|---|---|---|---|
| 1 | Ask Ollama what the model can do before offering tools | A model without tool support fails every turn with a wrong "restart Ollama" message | S | none | none |
| 2 | `OLLAMA_NO_CLOUD=1` on both Ollamas | Ollama itself refuses cloud models and its web search - rule 1, twice | S | none | lowers it |
| 3 | Record the prompt-cache hit on every turn | Shows whether long chats re-read everything; needed before any model switch | S | none | none |
| 4 | "Fill in this form" retry for a broken tool call | Turns the second try into a guaranteed-valid call, using a feature Jarvis already trusts | S-M | either | none (still gated) |
| 5 | Tool test: "ask, don't guess" and multi-step cases | Catches the model inventing a time or a recipient - the costly mistake | S-M | either | none |
| 6 | Lean tool list ("more tools" on request) | Frees working memory; must come before MCP | M | either | none |
| 7 | MTP speed-up for Qwen 3.5 | ~1.5-2x faster words (claim), no extra model | S | 12 GB first | none |
| 8 | Model shortlist to test on each card | Newer models may pick tools better; only measurement decides | S (test) | both | none |
| 9 | MCP bridge, updated for the July 2026 spec, two servers first | Opens the long tail of local tools, safely | L | none | medium, handled by the gate |
| 10 | Picture-based "pointer" for Windows control | Clicks things that have no readable name (games, custom apps) | L | 12 GB | medium: screenshots are private |

---

## Details

### 1. Ask Ollama what the model can do before offering tools (S)

- **What:** Ollama's `/api/show` lists each model's abilities (`capabilities`:
  `tools`, `vision`, `thinking`; `api/types.go:755` at `7af3931`). Jarvis
  should read it and not send `tools` to a model that lacks them.
- **The problem today (verified by reading both sides, not run):** a model
  without the ability answers a request with tools with HTTP 400 "`...` does
  not support tools" (Ollama `server/images.go:42-44,529`). Jarvis turns any
  400 into "Try again; if it keeps happening, restart Ollama"
  (`backend/jarvis_agent.py:2038-2040`). Restarting will not fix it. Since the
  owner can now install and switch models from the phone (CLAUDE.md,
  2026-09-18/20), this is reachable.
- **Where it plugs in:** `_lookup_context` already calls `/api/show`
  (`jarvis_agent.py:1909-1928`); cache the `capabilities` beside it and filter
  at `jarvis_agent.py:3404` (`names = ... offered_tools(...)`). Say in plain
  words "this model cannot use tools, so Jarvis answered without them". The
  same list can tell `vision.rs` about pictures and replace the
  `reasoning_effort` trial-and-error at `jarvis_agent.py:3524-3530`
  (Ollama 0.34.3 now advertises thinking controls, release notes).
- **Both apps:** no app change; the model picker could grey out "no tools".
- **Risk:** none; it only offers less.

### 2. `OLLAMA_NO_CLOUD=1` (S)

- **What:** an Ollama setting that "Disable[s] Ollama cloud features (remote
  inference and web search)" (`envconfig/config.go:332`). With it on, a
  cloud model gets 403 "ollama cloud is disabled" (`server/routes.go:335,2606`;
  `internal/cloud/policy.go`).
- **Why:** Jarvis already refuses cloud models by name
  (`jarvis_agent.py:2826-2833`, security audit H1). This adds Ollama's own
  refusal behind it, for every program on the PC that talks to Ollama, not
  just Jarvis.
- **Where:** the second card's environment (`jarvis_second_card.py:776-787`)
  and the one-line PowerShell command the hardware setups generate
  (`jarvis_profiles.py:854-879`); one preflight check in `selftest.py`.
- **Not checked:** whether it also stops `ollama pull` from the registry (it
  should not; pulling is not a "cloud feature" in the code I read, but I did
  not trace every path). Test that installing a model still works.

### 3. Record the prompt-cache hit (S)

- **What:** Ollama's OpenAI-style endpoint now returns
  `usage.prompt_tokens_details.cached_tokens` - how much of the prompt it
  reused instead of re-reading (`openai/openai.go:243-252`), sent in a stream
  when the request asks for `stream_options: {"include_usage": true}`
  (`middleware/openai.go:145,196`).
- **Why:** Jarvis's layout is built to keep that cache warm (facts late,
  rules first, `ARCHITECTURE.md` §7; `fit_messages` drops to three quarters so
  it trims rarely, `jarvis_agent.py:1967`). Nobody has measured it. And the
  Qwen 3.5 family mixes normal attention with a "running summary" layer
  (Gated DeltaNet). llama.cpp had a bug where such models re-read the **whole**
  conversation every turn (issue #22384, closed; the report measured 11 s
  down to 0.1 s after the fix). Ollama bundles a later llama.cpp (`b11081`),
  so it is probably fixed - **probably, not checked**.
- **Where:** add `stream_options` at `jarvis_agent.py:3486-3491`, read `usage`
  in `_read_chunk` (`:2998-3017`), put "prompt N, reused M" into the voice
  flow timings and the preflight.
- **Risk:** none. Numbers only, no text.

### 4. "Fill in this form" retry for a broken tool call (S-M)

- **What:** Ollama does not hold tool calls to a grammar for Qwen models; it
  reads them after they are written (`MODEL-TOPOLOGY.md`, "tool calls are not
  held to a grammar"). But Ollama's `format: <schema>` IS enforced token by
  token (`llm/llama_server.go:8-11`) - the decision Jarvis already took
  (`ARCHITECTURE.md` §11, "Structured output").
- **Idea:** when the model picked a real tool but wrote broken arguments, do
  the one retry as a separate request with `format` = that tool's own
  `parameters` schema ("fill in the arguments for `set_reminder`"). The
  result cannot be malformed. It still goes through `check_call`, `prepare()`
  and the gate as today.
- **Where:** the unreadable-call retry (`jarvis_agent.py:3617-3631`) and the
  wrong-arguments path (`:3730-3745`). Measure first with
  `ollama_tool_eval.py --repair`, which already counts "fixed by retry".
- **Risk:** a valid form can still hold a wrong value (a made-up time). That
  is what idea 5 tests and what the card shows the owner.

### 5. Tool test: "ask, don't guess", and multi-step (S-M)

- **What:** `tools/tool_eval/` scores picking, filling and staying quiet (61
  cases, `jarvis_tool_cases.py`; its "no tool" set is BFCL's irrelevance idea).
  Two gaps, from two public benchmarks:
  - **When2Call** (NVIDIA, Apache-2.0, github.com/NVIDIA/When2Call): the right
    move is sometimes a *question* ("remind me" - when?). Add cases where a
    required value is missing, scored "asked" vs "invented".
  - **tau2-bench** (Sierra, MIT): judge the *end state*, not the wording. For
    Jarvis: feed canned tool results for 2-3 steps and check the final call
    (e.g. read the calendar, then set the reminder at the right time).
- **BFCL V4** (Apache-2.0) is 40% "agentic" and 30% multi-turn by weight
  (Epoch AI's review) - borrow its categories, not its cloud-model tables.
- **Where:** `tools/tool_eval/jarvis_tool_cases.py` (new lists beside
  `HELD_OUT`, line 76) and `ollama_tool_eval.py`. Runs on the owner's PC only.
- **Risk:** none; nothing runs, calls are only scored.

### 6. Lean tool list: "more tools" on request (M)

- **Measured here:** the 23 tool descriptions Jarvis can offer are 10,859
  characters, **about 2,700 tokens** (browser control alone 1,635 characters;
  counted from `jarvis_agent.TOOLS` at `c78a04e`). That is ~16% of the 16K
  window before a word is said.
- **Idea:** always offer a small core (memory, calendar, timers, notes
  search, home); offer the rest through one `more_tools(topic)` tool that
  returns those schemas for the next round. OpenClaw's "lean mode / Tool
  Search" is the model (`COMPETITORS-OPEN-SOURCE-2026-09-25.md:175`, still open). Ollama
  0.34.0 added the same idea as "client tool search" on its Responses API
  (`openai/responses.go:261-283`) - Jarvis uses the chat endpoint, so copy the
  idea, not the endpoint.
- **Different from what failed before:** the 2026-09-24 test was a router
  guessing tools for the model (50-61% right). Here the model asks.
- **Where:** `offered_tools` (`jarvis_agent.py:2765-2784`) and the round loop;
  `Tool.instead` (`:552-583`) already handles "only mention tools that are
  offered". Measure with idea 5 before and after.
- **Risk:** one extra round for rare tools (about a second). Gate unchanged.

### 7. MTP: Qwen 3.5 guesses ahead with its own built-in head (S)

- **What:** some models ship a small extra "predict the next few words" head
  (MTP). The engine accepts the guesses the main model agrees with, so words
  come faster with the same answer. llama.cpp supports it
  (`docs/speculative.md`, `--spec-type draft-mtp`). **Ollama too:** it
  switches it on when the model file carries MTP layers AND
  `draft_num_predict` is set (`llm/llama_server.go:806-845`,
  `server/routes.go:155`; its docs: "embedded MTP tensors require setting this
  parameter", `docs/modelfile.mdx:153`). So one Modelfile line:
  `PARAMETER draft_num_predict 2`.
- **Which models:** Unsloth publishes MTP versions of every Qwen 3.5 size
  including 4B and 9B (claim, from search results; huggingface.co blocked).
  Whether Ollama's own `qwen3.5` downloads keep the MTP layers is **not
  checked**. Today's `qwen3:8b` has none.
- **Speed:** +33% to +120% on RTX 3090/4090/5090 for a 27B (sudoingX/qwen38-mtp,
  Apache-2.0, community numbers); no RTX 20-series figure found. Costs a
  little memory ("+1-2 GB" there, for a 27B).
- **Risks:** an open Ollama bug where the guesses all fail and it gets ~10x
  slower (issue #18541, 0.34.2, RTX 5090); `draft_num_predict 0` switches it
  off. Only helps one conversation at a time - Jarvis runs one anyway.
- **Where:** the second card's model once it is Qwen 3.5
  (`jarvis_second_card.py:196-208`); `jarvis-primary.Modelfile` only if the
  8 GB card also moves to Qwen 3.5. Measure with and without (idea 3's timings).

### 8. Model shortlist to test (S, a test not a switch)

`RESEARCH-2026-09-24.md` §6 already picked **Qwen 3.5 9B for the 12 GB card**
and **Qwen 3.5 4B to test on the 8 GB card**; `jarvis_profiles.py:213-222`
lists them as "test later". New since then, from source and release notes:

- **Qwen 3.5 is still the newest small Qwen.** 3.6 and 3.8 added only 27B and
  bigger open models (QwenLM/Qwen3.8 README; a request for a 3.6 9B is
  unanswered, discussion #156). Qwen3.8-Flash-Next is 125B - not for these cards.
- **Ollama runs Qwen 3.5 one request at a time** (`server/sched.go:510-514`
  forces `num_parallel` to 1). Fine for chat; it means the background learner
  and a chat question wait for each other on the same card.
- **Gemma 4** (Google, Apache-2.0, native tool-call tokens; Ollama reader
  `gemma4`, `model/parsers/parsers.go:90`). Sizes E2B, E4B, 12B, 26B-A4B, 31B.
  Ollama's own tests give `gemma4:12b` a **16 GB** minimum
  (`integration/reg_fast_test.go:9`) - probably too big for the 12 GB card at
  a useful context. `gemma4` (E4B) is given 8 GB. Worth a tool-test run.
- **Ministral 3** (Mistral, Apache-2.0, 3B/8B/14B, vision and tools, Dec
  2025; Ollama reader `ministral`). Another tool-test candidate for 12 GB.
- **Squeezing the 8B:** IQ4_XS instead of Q4_K_M saves ~0.6 GiB on an 8B
  (8.19B x 0.65 bits / 8, calculated), roughly 8,000 more tokens of `q8_0`
  cache at 78,336 bytes a token. `MODEL-TOPOLOGY.md` only considered it for a
  two-model pair. Quality cost unmeasured.
- **How:** one line on the PC, e.g.
  `py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary qwen3.5:4b gemma4:e4b --repair`
  (each model is a download; your call). Tags **not checked** on ollama.com.

### 9. The MCP bridge (L)

**Found while checking:** the bridge draft (`jarvis_mcp.py`, 1,554 lines,
with tests and a design) is **not in the repository**. `EXTRACTION-RESEARCH`
points at `/tmp/claude-0/research/out/`, which is gone; a copy survives only
in this session's scratch folder (`.../scratchpad/extraction-designs/mcp/`)
and would be lost on a container reset. Worth saving into the repo (I was
told not to edit).

**What it should look like** (the draft's shape, which I read, plus the
changes the new spec and this research need):

- **Local only.** Servers are programs on this PC started over stdin/stdout
  ("stdio"). No HTTP servers, no remote servers, no OAuth - that is a network
  service and would break rule 2's spirit. Starting a server is its own card.
- **Every call through the gate**, tier `ask` by default, per-tool pinned
  fingerprints (a changed description hides the tool - the "rug pull" attack),
  results treated as outside text. Fix the three holes `EXTRACTION-RESEARCH`
  found first (taint latch; "says nothing" means "may use the internet";
  never pass `HUD_TOKEN`).
- **Speak the 2026-07-28 spec too.** It removes the `initialize` handshake
  and sessions; servers answer `server/discover` and every request carries
  its version (spec changelog). The draft speaks only 2025-11-25
  (`jarvis_mcp.py:115`). Try `server/discover` first, fall back. "Roots" is
  deprecated, so give folders as start-up arguments. Tools should now come
  in a fixed order, which helps idea 3's cache.
- **Install once, pinned.** Reference servers are started with `uvx`/`npx`,
  which fetch code on every start. Install into a fixed folder with pinned
  versions; the start card names the version.
- **Needs idea 6 first**, or each server's tool text crowds the 8B out.
  `ANDROID-FEATURE-AUDIT.md` notes community advice that ~14B is the floor
  for reliable MCP use; test with idea 5 before trusting an 8B.

**Servers worth offering first** (both read-only to start):

| Server | What | Licence | Fit |
|---|---|---|---|
| `mcp-server-git` (modelcontextprotocol/servers) | status, diff, log, show; also commit, add, reset, checkout | MIT moving to Apache-2.0 | Offer the read tools only at first; write tools each a card |
| An "Everything" file-name search server (e.g. mamertofabian/mcp-everything-search) | instant file-name search via voidtools Everything | MIT (search result, not read) | New ability: "find the PDF from the bank"; names stay local |

Not worth it now: the filesystem, time and Home Assistant servers duplicate
`file_read`, `jarvis_quick.py` and `jarvis_home.py` (which chose REST on
purpose, `jarvis_home.py:6-11`). The reference README itself says these are
"not meant to be production-ready".

### 10. A picture-based "pointer" for Windows control (L)

- **Today:** `jarvis_ui_control.py` reads the accessibility tree (button
  names) - `plan()` lists every step, one card, `run()` re-checks each target
  before each click and stops on any change (`jarvis_ui_control.py:16-33`,
  `:258`, `:344`). Apps that draw their own buttons have no names to read.
- **Idea:** only when the tree has no match, ask a local vision model to point
  at the named thing in a screenshot. The step's card shows a cropped picture
  of the exact target. `run()` takes a new screenshot and refuses to click if
  that spot no longer looks the same. Still one plan, one card, no loop.
- **Candidate pointers** (all run locally; none measured here): Qwen 3.5's
  own vision (the planned 12 GB model - try it first, no extra download);
  Holo1.5 / Holo2 (H Company, 3B-8B, built for pointing; licence per size not
  checked - huggingface.co blocked); GUI-Owl-7B (Alibaba, licence not
  checked); OmniParser v2 (Microsoft; its newer `icon_detect_v3` is MIT, the
  older detector AGPL - use only v3).
- **Rules:** screenshots are private (email, chats) - rule 1: the pointer
  model must be on this PC; never stored, like Focus sessions. Anything read
  off the screen is outside text (it can say "click here to continue"), so it
  latches the taint as other reads do. Clicking by position is riskier than by
  name - the card must say so. Needs the 12 GB card; off until measured.

---

## Things the owner should know (plain words)

- **Switching to a model that cannot use tools breaks every question today,
  with the wrong advice** (idea 1). Found by reading both codebases, not run.
- **The MCP bridge draft is not saved in the repo** (idea 9).
- **`MODEL-TOPOLOGY.md` still holds:** Ollama's default context is 4,096
  below 24 GB of graphics memory, and 8 + 12 GB is 20 (`server/routes.go:2114-2118`,
  `docs/context-length.mdx`). The `num_ctx` pinned in the Modelfile and
  `OLLAMA_CONTEXT_LENGTH` on the second Ollama are still needed.
- **Ollama moves fast:** 0.33 to 0.40 in five weeks (release page). Structured
  output on thinking models is now "single pass" (0.34.4). Re-check this page
  against the version on the PC.

---

## Not for Jarvis

- **Windows-MCP (CursorTouch, MIT) as a whole.** It has PowerShell, Registry
  and file tools, can serve over HTTP, and sends usage data unless turned off
  (its README). It duplicates `jarvis_ui_control.py` with none of its checks.
- **Playwright MCP / browser MCP servers.** Duplicates `jarvis_browser_control.py`,
  which already took browser-use's safe parts and left the loop out.
- **The MCP "memory" server.** The model writes memory with no review - the
  thing `MEMORY-RESEARCH-2026-09-26.md` §7 rules out.
- **The MCP "fetch" server.** A new, unnamed way out of the PC
  (`ARCHITECTURE.md` §4 names each one). Web access stays with `web_search`.
- **Remote MCP servers, OAuth sign-in, HTTP transport.** A network service;
  local stdio only.
- **Computer-use agents that loop: Fara-7B (Microsoft, MIT), UI-TARS-1.5
  (ByteDance, Apache-2.0), OmniTool.** They look, click, look again until
  they decide they are done, and the model decides when to stop and ask -
  the standing grant `UFO-SAFETY-DESIGN.md` refused. Their pointing ability
  could serve idea 10; their loop cannot.
- **Ollama cloud models and Ollama's web search.** Rule 1; idea 2 switches
  them off.
- **TurboQuant (3-4 bit conversation memory).** Only in community forks, not
  merged into llama.cpp (discussion #20969); Turing support unverified.
- **Tool calls written as ReAct text** ("Thought / Action:" in plain words).
  It would bypass Ollama's per-model tool readers and Jarvis's schema check
  for no gain on models trained for native calls.
- **Splitting one model across both cards.** Already decided against
  (`MODEL-TOPOLOGY.md`); new "tensor split" modes do not change that for a
  fast card paired with a slower one.
- **mcp-scan and other scanners that upload your tool list.** Already
  rejected (`RESEARCH-2026-09-24.md` §4); the draft's local pinning does the job.

---

## What I could not check

- Nothing was run: not Ollama, not a model, not Jarvis, not on Windows.
- ollama.com, huggingface.co and most blogs are blocked: model tags, licences
  of Holo/GUI-Owl, MTP layers in Ollama's own Qwen 3.5 downloads, and all
  model-card scores are unverified or second-hand.
- Whether llama.cpp `b11081` has the hybrid-model cache fix (idea 3 measures it).
- Whether `OLLAMA_NO_CLOUD` affects `ollama pull` (idea 2 says test it).
- The owner's real `jarvis_gate.py` is not in the repo (`ARCHITECTURE.md` §9).

---

## Sources

- Ollama source at `7af3931` (files cited inline) and releases: https://github.com/ollama/ollama/releases ; MTP bug https://github.com/ollama/ollama/issues/18541 ; https://github.com/ollama/ollama/issues/18517
- llama.cpp: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md ; hybrid cache bug https://github.com/ggml-org/llama.cpp/issues/22384 ; TurboQuant https://github.com/ggml-org/llama.cpp/discussions/20969
- MTP community numbers: https://github.com/sudoingX/qwen38-mtp
- Qwen: https://github.com/QwenLM/Qwen3.8 ; https://github.com/QwenLM/Qwen3.8/discussions/156 ; https://github.com/QwenLM/Qwen3.8-Flash-Next/ (via search)
- Gemma 4 (via search): https://deepmind.google/models/gemma/gemma-4/ ; Ministral 3 (via search): https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512
- MCP: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx ; https://github.com/modelcontextprotocol/servers ; https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- MCP servers: https://github.com/CursorTouch/Windows-MCP ; https://github.com/mamertofabian/mcp-everything-search
- Tool benchmarks: https://gorilla.cs.berkeley.edu/leaderboard.html ; https://epoch.ai/benchmarks/berkeley-function-calling-leaderboard/review ; https://github.com/sierra-research/tau2-bench ; https://github.com/NVIDIA/When2Call
- Screen agents: https://github.com/microsoft/OmniParser ; https://www.microsoft.com/en-us/research/blog/fara-7b-an-efficient-agentic-model-for-computer-use/ ; https://huggingface.co/Hcompany/Holo1.5-7B , https://huggingface.co/mPLUG/GUI-Owl-7B , https://huggingface.co/Mungert/UI-TARS-1.5-7B-GGUF (all three via search)
