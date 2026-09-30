# Report 32 (outside-suggestion-check), agent aa7a9c51, 2026-09-30T06:32Z

> **What it was asked** (first 600 characters of the task): Check this outside (Gemini) suggestion list against /home/user/Epic-Jarvis's code and past decisions (read CLAUDE.md, docs/AUDIT-2026-09-28-REPO-REFS.md first - its disproven findings stay closed - then grep docs/ and backend/ for each name before judging). Items: (1) screenpipe/screenpipe: 24/7 screen+audio capture into SQLite, 'passive visual memory' answering 'what was that flag 45 minutes ago'. CLAUDE.md records that the owner DECLINED always-on watching with history (Recall-style) on 2026-09-28; check exactly what was decided (Look at this / Watch with me, nothing saved, screen safety, ru

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

All five items checked against the repo. I could not reach GitHub, so every licence and project claim about the outside repos is "not checked". Nothing was edited.

**Wrong facts in Gemini's text**
- "AMD Ryzen 9 3900X" is correct. `docs/MODEL-TOPOLOGY.md:3` says "Ryzen 9 3900X" and `.claude/agents/JARVIS-TODAY.md:25` says 12 cores.
- `%USERPROFILE%\.openjarvis` is real. It is Jarvis's own settings folder (`docs/INSTALL.md:1134`, `ARCHITECTURE.md:424`). It does not come from Gemini's project. `docs/INSTALL.md:1255` says not to run the separate "OpenJarvis" download because it writes into the same folder. Only the claim that STORM would run from there is unfounded.
- `backend/jarvis_coding.py` does not exist. I searched the whole repo and found nothing. The real file is `backend/jarvis_app_workspace.py`.

**1. screenpipe: SKIP (already rejected)**
- `ARCHITECTURE.md:2536` rejects it: "relicensed, captures keystrokes and the a11y tree, telemetry on by default". `docs/RESEARCH-AUDIT-2026-09-28.md:334` says it is under a commercial licence. `studio-2026-09-27/integrate-desktop.md:8` says "never copy". `COMPETITORS-COMMERCIAL:159` says it "would capture passwords and email".
- CLAUDE.md says the owner declined "always-on watching with a history (Recall-style)" on 2026-09-28. `SCREEN-DESIGN.md` says Jarvis "keeps no history".
- The allowed versions are "Look at this" (one look, nothing saved) and "Watch with me" (owner starts and stops it, a visible "Jarvis is watching" sign, pauses on password fields and banking apps, nothing saved).
- Only the owner's question and Jarvis's answer are kept in chat history. The picture and the screen's words never are.
- Screen safety (`jarvis_secrets.py`) blacks out keys and card numbers before any model sees them.
- I found no design for a saved "session summary" and no audio recording. Audio capture would also clash with the voice design, and 24/7 capture cannot be made to fit the "nothing saved" decision.
- A narrower version would be an opt-in session summary that is saved. That would be a new decision for the owner. I am not proposing it.
- The licence claim of "source-available" is not checked, but the repo already records it as commercial.

**2. Outlines: SKIP (decided against, and the premise is wrong)**
- `ARCHITECTURE.md:2532`: "Ollama's native `format: <schema>` — GBNF at the sampler. **Not** `outlines`, which cannot constrain Ollama." Outlines needs logit access to a local model, and Jarvis talks to Ollama over HTTP.
- `format` schemas are already used at `jarvis_support.py:1418` (`MOVE_SCHEMA`) and `:2040` (`SUMMARY_SCHEMA`). I did not open `jarvis_wiki.py`, `jarvis_tidy.py` or `_ollama_wire.py` in detail.
- Tool calls are a different path. `jarvis_agent.py:3126` explains that Ollama does not hold the model to a tool's schema and only reads the call afterwards. So `check_call` (`:3215-3235`) validates first. A bad call never reaches `prepare()` or a card. The model gets one plain sentence saying what was wrong and can try once more.
- Wrapping gate proposals is the wrong place. `jarvis_gate.py` decides approval and does not produce tool JSON.
- BORROW IDEA: none needed.

**3. STORM: SKIP for now**
- `CUTTING-EDGE-2026-09-26-round3-routines.md:277,342` already lists STORM (MIT) in the same "deep research" family as local-deep-researcher, GPT Researcher and open_deep_research. It is not adopted, and no code uses it.
- Jarvis already has web search (`jarvis_search.py`, five providers, with asks-first rules). There is also a wiki builder and the chatbot "compare" feature.
- A second research agent framework would break "one permission model, one scheduler" (audit round 7 refuses agent-framework and agno for the same reason).
- Searches read outside text, so they would need the asks-first card. Many searches means many cards, or one plan card. The plan card is still switched off until the tool tests pass.
- If it ever comes back, the round-3 doc's loop would be the design to use, on the existing search and the second lane, with no new framework.
- I did not read STORM itself. The "on a second GPU lane" claim is unverified, and the second card is not installed yet.

**4. agent-zero snapshots: BORROW IDEA only, and it is partly already there**
- `PROJECTS-DESIGN.md:178-180` already designs Undo: each approved change becomes a git save point, and Undo adds a new save point on top.
- `jarvis_app_workspace.py` uses one git worktree per task and a merge card, and `discard()` drops a task's copy.
- `APPS-IN-PROJECTS-DESIGN.md:152,171` states that the app-merge action has no Undo button yet, and that the older version stays in git history.
- So the gap is a "restore to before" button for an app merge. That is a small addition on top of git, and the owner would need to decide whether to add it.
- Other Undos already exist: inbox tidy (10 minutes) and "Forget a time frame" (10 minutes).
- I did not check Agent Zero's licence, so "fully open source" is not checked. Nothing needs copying.

**5. MCP servers: BORROW IDEA, mostly redundant**
- `backend/jarvis_mcp.py` is built, with tests in `test_mcp.py` and `test_mcp_wiring.py`. It does not use the `mcp` SDK.
- It follows the decisions:
  - local programs only;
  - read-only first (`:29`);
  - a card to start each server (`:1203`);
  - every call is checked against the gate, and its floor is "ask" (`:78`).
- The design draft (`docs/designs/mcp-draft-2026-09-23/DESIGN.md:8`) refuses anything that downloads code at start, such as `npx` or `uvx`. It expects a full path to `node.exe` (`:240`). This would matter to a beginner on PowerShell 5.1 who has no Node installed.
- Filesystem and git servers overlap the existing file and shell tools. They would also need a path jail to satisfy rule 1, and the bridge does not sandbox the program (`:70`).
- I searched the repo for `sequential-thinking` and found no mention. I found no record of the per-model thinking levels (Off/Quick/Deep/Auto) the task described. That is not verified, so I cannot say whether it overlaps. It would likely duplicate any built-in thinking control anyway.
- Nothing more needs deciding unless the owner wants a specific server added.

**Verdicts:** 1 SKIP, 2 SKIP, 3 SKIP (later idea only), 4 BORROW IDEA (Undo for app merges), 5 SKIP (already built, and the Node/npx part clashes with the setup rules).
