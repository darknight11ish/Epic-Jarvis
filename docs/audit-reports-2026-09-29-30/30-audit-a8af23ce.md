# Report 30 (audit), agent a8af23ce, 2026-09-30T06:28Z

> **What it was asked** (first 600 characters of the task): Read-only audit + short design proposal for the owner of /home/user/Epic-Jarvis (read CLAUDE.md fully, docs/ARCHITECTURE.md, docs/MODEL-TOPOLOGY.md, docs/CHATBOT-DRIVER-DESIGN.md, docs/APP-BUILDER-DESIGN.md, docs/PROJECTS-DESIGN.md). Owner: "Make sure Jarvis can drive multiple AI models so that they all work together properly on different or the same task. I want versatility without compromising effectiveness or efficiency." Models here means: the everyday local model (primary card), models on the second/third-card lanes (jarvis_second_card.py lanes: long_context, vision, learning, browser_con

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

MULTI-MODEL AUDIT (read-only; nothing run, no files changed). Everything below is read from source, not executed. "Not checked" is marked.

**1. CURRENT STATE**

| Model / lane | Where it runs | Who decides | Notes |
|---|---|---|---|
| Everyday `jarvis-primary` (Qwen3 8B, 16K) | 2080 Super | default | swap on 8 GB costs ~6-10 s (MODEL-TOPOLOGY.md:249-266) |
| vision, long_context | second-card Ollama (own port, `OLLAMA_MAX_LOADED_MODELS=1`, `NUM_PARALLEL=1`, jarvis_second_card.py:1386-87) | `jarvis_agent.choose_lane` (jarvis_agent.py:4830): picture, then over-long conversation, then "combined", else main | rule-based, per turn |
| learning | same lane | `lane_for("learning")`; on failure it is skipped for 600 s and the pass runs on the main card (second_card.py:2161) | only lane with a fallback |
| browser_control | second-card lane | switches to the lane mid-turn when the tool is called (jarvis_agent.py:6488) | needs long_context on |
| wiki | second-card lane (or big-model lane) | `lane_for("wiki")` | background job |
| third card | 3rd Ollama copy (`_THIRD_LANE`), runs beside the second, one feature moved by an owner card | owner names it (`second_card_third_assign`) | never auto |
| "combined" 14B | both cards | owner switch; excludes every per-card feature | two-card only |
| second local AI | `jarvis_chatbot_local.py`: 2 cards = second lane (swaps models per message if not the lane's own); 1 card = the everyday model itself ("a fresh look, not a different AI") | owner picks `local_model` | loopback, no "-cloud" models |
| Web / API chatbots, compare | `jarvis_chatbot*.py`, `jarvis_chatbot_compare.py` | owner's card | compare runs one after another, "chatbots never see each other's answers"; up to 3 (1 card) or 4 (2 cards); merged by `summarise()`, written by the local model |
| Cloud lane in router | `rebuilt/jarvis_router.py:choose` | 9 ordered gates, cloud only with `owner_said_yes` per question | no lane configured on the owner's PC today |
| Plan card | `jarvis_plan.py` / `propose_plan` | switched off until `tool_eval_results.json` clears 90% multi-step and 0 injections | any tool, one model |

Two models at once: yes, on different cards (separate Ollama processes and ports, pinned by GPU id). On the same card: not designed for. The topology doc says two runners do not fit in 8 GB, and one lane holds one model at a time.

The owner mentioned "planned per-model thinking levels". I found no design for this. The only thinking handling is "off" for `jarvis-primary` (jarvis_agent.py:2636-2650). Not checked beyond grep.

**2. GAPS, worst first**

1. **No "model roles" table or single decider.** Routing is spread over `choose_lane` (picture and length only), the router (cloud), the driver's `choose_tier`, and per-feature `lane_for` calls. Nothing says "code goes to X, checking goes to Y". There is no per-task specialist choice beyond vision and long context.
2. **No mid-turn failover for chat lanes.** `choose_lane` returns a lane and `run_local_turn` streams to it (timeout 300 s, jarvis_agent.py:2384). I found no path back to the main card if the second lane dies mid-answer. Only the learner has a fallback. Not exhaustively checked.
3. **Nobody owns queueing or back-pressure.** The lanes are single-slot. The local-AI driver on 2 cards swaps the lane's model per message, which starves long-context chat on that lane. The limited version "waits while the owner is chatting" only for the driver.
4. **Same-question fan-out, judge and planner/checker do not exist for local models.** Compare is web/API chatbots only, sequential, and its summary is the same local model that would answer alone. There is no small-drafts, big-checks pattern and no local-only compare.
5. **Observability is thin.** The route header carries `lane` and `second_card` (second-card.patch:~2931). There is no per-step "which model did what and how long" view for multi-model work. Chatbot transcripts are shown, but not for local lanes.
6. **"Local" is defined by URL, not by role.** `local_model_refusal` and `is_loopback` guard lane URLs. No single rule states which roles may ever see private data. Today it holds by construction: the cloud gates refuse tainted, private, picture and screen turns; compare sends only the goal; the plan card refuses on taint. A future multi-model plan needs it as one written check.
7. **Stop everything** reaches compare (`_stop_everything`, compare.py:938). Not checked: whether it aborts an in-flight request on the second or third lane.
8. **Cost limits** exist for API services (monthly cap plus answer-length cap). There is no cost or time budget across a multi-model plan.

**3. WHEN MULTI-MODEL IS NOT WORTH IT**

- One card: a second resident model does not fit, so every "helper" is a 6-10 s swap. Never do this per request.
- Fan-out to several local models on the same question re-sends the whole context and doubles or triples latency. The 2060 is about two thirds the speed of the 2080 Super (MODEL-TOPOLOGY.md), so it is the bigger-context lane, not the fast one.
- Local models drawing on the same base weights (a fresh look by the same model) add cost and little diversity.
- Short, simple turns are already answered without any model (`jarvis_quick.py`).

**4. FIT WITH THE RULES**

Nothing new needs to leave the PC. A local-only design passes rules 1 and 2. Rule 4 holds if every step still goes through `check_call` and the gate. It must reuse the one scheduler and jarvis_task_control (Pause/Stop), and must not add a second agent framework. The plan card's `enabled()` measurement must gate any multi-step multi-model plan. A cloud model must never be a role in any plan that touches email, files, credentials or memory.

**5. PROPOSAL: smallest safe design**

**Roles table (one read-only page, no new engine; the defaults are the routing that already exists):**
- Everyday chat, tools: main card
- Long or over-budget context: long_context lane (2 cards)
- Pictures: vision lane (2 cards; 1-card picture mode is CPU and off)
- Learning, wiki: background lane, waits for chat
- Browser: long_context lane
- Second opinion: local second AI on the 12 GB lane (2 cards) or cloud/API (owner card, public question only)
- Aider/app builder: its own task copy, local only for now

**Patterns worth building first (all default OFF, both need the second card):**
- **A. Checker, not fan-out.** Main model answers. The 12 GB model reviews it only for tool-call plans and code, never for chat.
  - Measure: tool_eval multi-step pass rate and injection carry-through, with and without the checker.
  - Where: `tools/tool_eval/ollama_tool_eval.py`, and extra latency logged per turn.
  - Keep it only if the pass rate gains at least 3 points for under 3 s.
- **B. Local compare.** Reuse `jarvis_chatbot_compare.py` with two local roles (main model vs 12 GB model), no browser window, no card leaving the PC.
  - Measure: agreement with a labelled set, and total time.
  - Only for questions the owner asks. Never for private turns, unless both models are local, which they are.
- **C. Failover and health.** If the chat lane errors or times out, retry once on the main card and say so in words. This is a fix, not a feature.
  - Measure: kill the lane mid-turn and check the owner still gets an answer.
  - Where: a test beside `test_second_card.py`.

**Before any switch is turned on (owner's PC, measured):**
- 2060 installed, and speed and memory per role measured.
- Lane swap time on the 12 GB card.
- Whether Stop everything reaches the lanes.
- Latency of A and B.
- The `tool_eval_results.json` numbers.

**Settings, both apps:** one section, "Working together", inside the existing Second graphics card page (phone Brain plate, desktop Settings). It has the roles list and one switch per pattern. Turning one on raises an approval card. Off is instant. The phone shows the same rows through `/api/second-card`. `tools/check_parity.py` should then stay clean.

**6. OWNER DECISIONS**

1. Build first:
   - **(recommended)** C failover, then A the checker
   - B local compare first
   - Nothing yet, wait for the 12 GB card
2. Local model checking another local model's tool plan:
   - **(recommended)** only for plans and code
   - for every answer (slower, no measured gain)
3. Per-model thinking levels: the repo has no design. Should I write one?
   - **(recommended)** Yes, after measuring the 12 GB card
   - No, keep thinking off everywhere
