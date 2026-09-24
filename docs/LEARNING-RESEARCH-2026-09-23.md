# Has Jarvis taken everything useful from OpenJarvis for "learning over time"?

Code versions checked: Epic-Jarvis @ `d82f83f`, OpenJarvis @ `e86c582` (both 2026-09-23). "Learning over time" here means anything that makes Jarvis better the more you use it: memory, preferences, skills it builds up, measuring whether a change helped, and tidying memory on a schedule.

## 1. The short answer

- **No, but not because something was missed.** No OpenJarvis learning code is in Epic-Jarvis, and OpenJarvis never actually ran on your PC. Your own README says so: "OpenJarvis was never actually part of this setup" (`backend/README.md:1929`).
- **Most of OpenJarvis's learning features are not connected up inside OpenJarvis itself.** The training loop is never called. Its "learned" model router starts empty every time. Its prompt optimisers score the old answer instead of the new one. Its playbook is written but never read back. Two of its commands just print "not yet fully implemented" (OpenJarvis `cli/optimize_cmd.py:428`, `cli/feedback_cmd.py:155`). There is less there to take than its docs suggest.
- **Several of its biggest learning features break your rules or repeat decisions you already made.** These are fine-tuning, a test set built from your own transcripts, and a cloud "teacher" model. Your config already rules out the first two (`backend/rebuilt/jarvis-framework.toml:924-931`, `:949-951`). The third would send private content to the cloud.
- **15 smaller ideas are worth taking**, from OpenJarvis and from five other projects (mem0, graphiti, zynkbot, Khoj, letta-code). The most important gap is that **you have no way to tell Jarvis an answer was wrong.** Jarvis learns what you say, but never finds out whether its answers were any good.
- **Most of these ideas touch memory, and you parked memory work** "until Jarvis is actually running and he has used it for a while" (`backend/rebuilt/jarvis_sleep.py:17-18`). So treat the memory ideas as a list for later, not work to start now. The non-memory ones (items 10-15) could go ahead now.

## 2. What OpenJarvis is, and how Epic-Jarvis relates to it

OpenJarvis is Stanford's open-source local assistant framework (Apache-2.0, a licence that allows reuse). Epic-Jarvis was designed to sit **in front of** OpenJarvis. Early on, chat was passed through to OpenJarvis's server on port 8000 (`backend/README.md:1921-1927`), and the permission gate knows OpenJarvis's tool names. But the two projects share no code. Epic-Jarvis also keeps its files where OpenJarvis keeps its own: the `~/.openjarvis` folder, `memory.db`, `config.toml`. Since then Epic-Jarvis has replaced each OpenJarvis piece with its own: it talks to Ollama directly (`ollama-direct.patch`), has its own tool loop (`backend/jarvis_agent.py`), and its own memory. What still expects OpenJarvis is the status check on port 8000, the "jarvis" status light, and the route for a future cloud lane.

## 3. Worth taking

Ranked by how much each helps Jarvis learn over time. Approve by number. Effort: S = small, M = medium, L = large.

**1. A "that was wrong" button on each answer (M)**
- **What it is:** one tap on an answer stores a right/wrong mark, plus the list of remembered facts that went into that answer. No words are stored, only the mark and some ID numbers.
- **What changes for you:** Jarvis finally learns whether its answers were any good. Items 7 and 8 need this first.
- **Rules:** it stays on your PC. A mark never changes memory directly; at most it moves a counter or raises a card for you to decide. One answer, one mark, with no "rate all". No AI grades answers for you.
- **Already there:** the fact IDs used in each prompt are already recorded (`backend/memory-noise.patch:93-94`) and sent along in the route header (`backend/degrade-filter.patch:40`). Neither app reads them yet.
- **Source:** OpenJarvis `server/api_routes.py:1049-1070`, `traces/store.py:271-281`.

**2. "Remember: …" (S)**
- **What it is:** start a message (typed or spoken) with "Remember:" and the rest goes into the memory review queue exactly as you said it, without the model rewording it.
- **What changes for you:** a dependable, direct way to teach Jarvis.
- **Rules:** it still becomes a card you accept or reject. By voice it is safe, because the owner-voice check runs before any words exist (`backend/jarvis_speech.py:407-447`). It must only react to text you actually typed or said. The backend already writes "Remember this: …" itself (`backend/gate-outcome.patch:53-55`), so that text must not trigger it; see item 12. Pair it with item 3, otherwise the normal learner may also propose a reworded copy.
- **Licence:** zynkbot's own non-commercial licence, so take the idea only and write the code fresh.
- **Source:** zynkbot @ `906d22b` `commands/chat.rs:2251-2270`.

**3. Filter out near-duplicate proposals before you see them (S)**
- **What it is:** a new proposal is compared by meaning with facts you already kept and with cards still waiting.
- **What changes for you:** fewer repeat cards. Today only exact copies are caught (`backend/memory-safety.patch:334`), and once the queue is full, extra proposals are dropped with no record (`:423-431`).
- **Rules:** it only ever drops proposals, never stored facts. Conditions:
  - Never drop a correction.
  - Never drop anything where a number, a date or a "not" differs. Comparing by meaning cannot see negation, so "allergic to X" and "no longer allergic to X" would look the same.
  - Count every drop so the status screen can show it.
  - Skip the check until the real embedder (the part that turns text into comparable numbers) has downloaded.
- **Licence:** mem0 and graphiti are Apache-2.0; zynkbot is the idea only.
- **Source:** zynkbot `commands/memory.rs:758, 839`; mem0 @ `f8082a7` `mem0/memory/main.py:1004-1023`; graphiti @ `16cdf70` `prompts/dedupe_edges.py:23-32`.

**4. Corrections point to the old fact by number (M)**
- **What it is:** when Jarvis proposes a correction, it is shown the closest stored facts numbered 0, 1, 2… and answers with a number instead of describing the old fact in its own words.
- **What changes for you:** corrections actually retire the fact they replace. Today the model's description is matched on shared words (`backend/rebuilt/jarvis_memory.py:913-943`). When the match is unclear, the correction is added as an extra fact and nothing is retired.
- **Rules:** the card already shows the fact that would be retired (`memory-safety.patch:287-296`), and nothing is retired until you accept. A number outside the list counts as "no match". How often corrections fail today has not been measured.
- **Licence:** Apache-2.0.
- **Source:** graphiti `prompts/dedupe_edges.py:28-32, 81`; mem0 `main.py:933-937`.

**5. A "both are true" answer on correction cards (S-M)**
- **What it is:** a third answer on a correction card: keep the new fact and do not retire the old one.
- **What changes for you:** a true fact is not retired just because two facts looked like they clashed. Today your only choices are yes (which retires the old fact) or no (which throws the new fact away) (`docs/JARVIS-API.md:382`, `memory-safety.patch:376-388`).
- **Rules:** still one card and one decision, so it is not bulk approval. Do not copy zynkbot's "keep new" option: it deletes the old fact outright (`memory.rs:1091-1095`). Both apps need changing, so the phone side needs a CI round trip (~15 minutes on GitHub to find out if it compiles).
- **Source:** zynkbot `commands/memory.rs:1045-1300`, idea only.

**6. Turn "yesterday" into a real date when a fact is learned (S)**
- **What it is:** the learner is told the date of the conversation and must turn "last week" into an actual date.
- **What changes for you:** "went to Paris last week" still means something six months later. This matters more because your chat-history importer feeds in years-old conversations as if they were live (`backend/import_history.py:9-16, 360`).
- **Caveats:** the date will sit inside the fact's text. Facts would need a new field for the real "true from" date to be stored properly (`memory-safety.patch:386`). The learner's prompt is not in this repo, so whether it already does this is not verified.
- **Licence:** Apache-2.0.
- **Source:** mem0 `mem0/configs/prompts.py:522-535`; letta-code @ `f3709eb` `reflection-v2.md:85`.

**7. Suggest a new skill when you keep approving the same chain of actions (M)**
- **What it is:** Jarvis counts tool chains it has run repeatedly (for example: search notes, then read the calendar, then draft an email), using the approval log it already keeps. When a chain repeats often, it offers one skill card.
- **What changes for you:** routine jobs become one step.
- **Rules:** counting only, with nothing sent anywhere. The result goes through the existing approval for Jarvis changing its own code (`backend/README.md:446-447`), and nothing is written until you say yes. OpenJarvis instead writes these skills straight to disk with no review (`skills/manager.py:296-315`), so do not copy that part. Count actions that ran automatically (with or without a notice) as well as approved ones, because read-only tools run without asking. Do not copy your old messages into the skill text.
- **Not verified:** whether the approval log records which conversation turn each action belonged to.
- **Source:** OpenJarvis `learning/agents/skill_discovery.py:47-104`.

**8. Helpful/harmful counts on each fact and skill note (M, after item 1)**
- **What it is:** two counters per fact and per skill note: how often it was used in an answer you marked right, and how often in one you marked wrong.
- **What changes for you:** a fact that keeps showing up in wrong answers raises a "retire this?" card. Retiring means giving it an end date, not deleting it.
- **Rules:** only your own marks move the counters. Take only the counter format from the ACE project. Do not take its engine as OpenJarvis wires it up: that defaults to OpenAI (OpenJarvis `core/config.py:758`), treats Jarvis's own old answer as the correct one (`ace_optimizer.py:96-111`), and is never read back.
- **Caveats:** with one user the counts will be sparse, and a fact appearing in a wrong answer does not prove it caused the mistake. Keep the retire threshold high.
- **Source:** ace-agent/ace @ `82709de` `playbook_utils.py:13-26, 50-95`.

**9. Warn on memory proposals that look like planted instructions (S)**
- **What it is:** each proposed fact is checked for text trying to smuggle in orders ("always forward emails to…"). If it looks like that, the card shows a warning flag.
- **What changes for you:** a pasted hostile message cannot quietly become a fact that steers every later answer.
- **Rules:** it only adds a warning to your one-at-a-time review. Unlike OpenJarvis (`memory/service.py:216-220`), it drops nothing silently. The check runs on your PC's processor, not the graphics card. Skill notes are already scanned (`skill-notes.patch:52-57`).
- **Not verified:** whether memory proposals are scanned today; the learner module is not in this repo.
- **Source:** OpenJarvis `memory/service.py:196-243`, `memory/store.py:319-326`.

**10. Never learn from turns Jarvis started itself (S)**
- **What it is:** one check in the learner: only turns you actually typed or said get learned from. The backend sets where each turn came from; the model never does.
- **What changes for you:** a future scheduled digest cannot put its own wording in the queue as if you had said it. Today this holds only because nothing automated exists yet. The learner keeps every "user" message whatever its origin (`extraction-wiring.patch:166-178, 275-287`), and no test covers this case.
- **Rules:** it must not break the deliberate path where your "no" to an action becomes a proposed rule (`gate-outcome.patch:49-58`).
- **Licence:** Khoj is AGPL, a licence whose terms would come with any copied code, so write the one line fresh.
- **Source:** khoj @ `ae229ca` `src/khoj/processor/conversation/utils.py:612-613`.

**11. Record how fast each answer was, as numbers only (M)**
- **What it is:** one small row per answer: which model, time to first word, total time, words per second, and how much of the model sat on the graphics card. No conversation text is stored.
- **What changes for you:** you can see if an Ollama update or another program quietly made Jarvis slower. Today nothing records it; the only timings are one-off measurements in `docs/MODEL-TOPOLOGY.md`.
- **Rules:** kept in a local file only. Do not bring over OpenJarvis's analytics or leaderboard upload, which would be a new outbound connection (`docs/ARCHITECTURE.md:183`).
- **Not verified:** whether Ollama's stream reports token counts (the stream can be timed either way), and whether power readings work on the 2080 Super.
- **Licence:** if code is copied, add OpenJarvis to `THIRD-PARTY-NOTICES.txt`.
- **Source:** OpenJarvis `telemetry/store.py:14-70`, `telemetry/instrumented_engine.py:379-381`.

**12. Add a speed check when the model is switched (S)**
- **What it is:** Tripwire, the check that already runs when you switch models, also times a few fixed test prompts on the old and new model.
- **What changes for you:** a measured "old: X words/s, new: Y words/s". Speed can be measured reliably; answer quality cannot, which is why you cut that (`jarvis-framework.toml:924-929`).
- **Where the numbers go:** on Tripwire's result screen **after** the switch, next to rollback. They cannot go on the approval card, because the new model is not loaded yet. Ollama's own replies already carry the timing numbers.
- **Not verified:** the Tripwire code itself is not in this repo (only named at `backend/selftest.py:64`).
- **Source:** OpenJarvis `bench/latency.py:17-65`, `bench/_stats.py:20-35`.

**13. A "doctor" step in the self-test (S)**
- **What it is:** `selftest.py` also checks that Ollama answers, that the configured model is downloaded, and that it is fully on the graphics card.
- **What changes for you:** catches the silent slow-down when part of the model spills off the card. Today the self-test never mentions Ollama.
- **Rules:** read-only and local, and it loads nothing. If no model is loaded, it reports "skipped". The cache-size check can only ever warn, never fail.
- **Source:** OpenJarvis `cli/doctor_cmd.py:18-26, 115-222`; Epic `backend/gpu-offload.patch`.

**14. Stop OpenJarvis from writing into Jarvis's memory folder (S)**
- **What it is:** if you ever run the OpenJarvis copy you downloaded, its document indexer creates a `documents` table in `~/.openjarvis/memory.db` (OpenJarvis `rust/crates/openjarvis-tools/src/storage/sqlite.rs:58-67`). Epic-Jarvis reads that exact table into your prompts as soon as it exists (`documents-honesty.patch:42-47`), so content would reach your prompts without you deciding.
- **Fix:** only read that table if Epic-Jarvis recorded creating it, and add a one-line warning in `INSTALL.md`. Nothing is deleted.

**15. Remove the dead check on port 8000 (S)**
- **What it is:** the status check still tries OpenJarvis on port 8000, which nothing listens on. Per a code comment, that costs about 2 seconds per check (`jarvis-desktop/src-tauri/src/commands.rs:26-35`; not measured). Also remove the "jarvis" status light (`jarvis_hud.html:1729-1741`) and replace the "uv run jarvis serve" error text.
- **Caveats:** this is clean-up, not learning. The port 4000 check has the same cost. Keep the cloud-lane address until something replaces it.

## 4. Already in Epic-Jarvis

- Human review before any fact is kept (`propose()` then `decide()`, `docs/ARCHITECTURE.md:219-220`). OpenJarvis keeps facts automatically.
- Nothing is ever deleted: old facts are retired with an end date. OpenJarvis deletes the oldest facts above 1000 (`memory/store.py:334-335`).
- Meaning-based plus keyword search over facts, and recall of relevant facts only. OpenJarvis injects the newest facts first.
- The learner reads your messages only, never Jarvis's replies (`ARCHITECTURE.md:246-252`).
- Where each fact came from: the fact links to its proposal, its source and its time (`memory-safety.patch:386-390`). Only the name of the extraction model is missing.
- Undo for self-changes: rollback settings, an undo shelf and git restore points (`jarvis-framework.toml:131-148, 737-766, 862-869`). Not yet enforced (`:150`).
- The model never picks its own permission tier. Unknown tiers default to "ask" (`skill-notes.patch:39-51`).
- Your "no" to an action becomes a proposed standing rule (`gate-outcome.patch:25-60`). *Since then (2026-09-24):* except for actions that always ask anyway and that you start yourself with a button (turning on the second card or the big model, installing or switching a model, the wiki, Jarvis changing its own settings or code, and a few more). For those a "no" answers that one card and proposes nothing, because "do not do this without asking me" would say nothing new. The list is `_NO_RULE_FROM_DENIAL` in `gate-outcome.patch`.
- A log of every routing decision, tool call and gate outcome, with private details removed (`jarvis-framework.toml:198-214`).
- A privacy-first model router (`backend/rebuilt/jarvis_router.py:328`).

## 5. Left out, and why

- **Full log of every question and answer** (OpenJarvis traces): you already rejected a "frozen second copy of your life" (`toml:924-931`). The rating half is item 1.
- **Personal test set from your conversations, with an AI judge:** you cut it twice. 30-50 tasks is too noisy, and it is a transcript copy (`toml:920-931`). A second version of this idea was left out for the same reason.
- **ACE playbook of lessons written by reflecting on whole conversations:** it would read Jarvis's replies, the hole the learner deliberately avoids. The counter half is item 8.
- **Skill discovery from a new trace log:** a duplicate of item 7, which uses the log you already have.
- **DSPy/GEPA prompt optimiser:** it does not measure anything as written, and its fallback copies your raw past answers into prompts (`skill_optimizer.py:244-253`).
- **Fine-tuning (LoRA/SFT/GRPO):** you ruled it out (`toml:949-951`). It does not fit on 8 GB, and the loop is never run in OpenJarvis.
- **Cloud "teacher" spec search:** breaks rule 1. OpenJarvis's own safety audit flags it (`security/data_boundary_audit.py:928-937`).
- **Learned model routing:** it starts empty every time in OpenJarvis (`agents/executor.py:402-409`), and there is no second lane to learn between yet.
- **Improved-examples side file for skills:** it can only be produced by the broken optimiser, or by copying your private answers.
- **Home Assistant's voice vocabulary:** little learning value, and it would change the voice contract on both apps.
- **Letta reflection rules:** duplicate of items 6 and 7. Its best parts need Jarvis's replies.
- **OpenJarvis proactive agent:** auto-approves, offers "yes all", and lets the model choose its own tier (`agents/proactive_agent.py:467, 489-493, 571`).
- **OpenJarvis end-of-session memory flush and memory/skill tools:** they write and delete with no approval (`tools/skill_manage.py:216-295`).
- **OpenJarvis session "consolidation":** it keeps 100 characters and deletes the originals (`sessions/session.py:237-266`). Your tidy-up-while-idle pass is still a real gap, but OpenJarvis does not fill it.
- **Analytics, leaderboard upload, "mining":** new outbound connections, and out of scope.

## 6. Could not check

- These modules live only on your PC, not in this repo: the learner (`jarvis_extract`, including its prompt text), `jarvis_skills.py`, `jarvis_tripwire.py`, and the status-check code in `jarvis_hud.py`. Anything that depends on them is marked "not verified" above.
- Whether the approval log records which conversation turn each action belonged to (needed for item 7).
- Whether Ollama's stream reports token counts, and whether power readings work on the 2080 Super.
- No timing on your card was measured. Every estimate above is an estimate.
- The OpenJarvis paper (arXiv 2605.17172) was blocked by the network, so its claims come from code comments only.
- DSPy's licence (believed MIT) and how the 2080 Super handles the number format (bfloat16) that OpenJarvis's training code hard-codes.
- NousResearch/hermes-agent, which OpenJarvis imports skills from, was not read.
- mem0's evaluation harness is in a separate repo that was not cloned.
- A small bug, not checked against your PC's original file: the rebuilt importer reads `~/.openjarvis/facts.json` as one JSON list (`backend/rebuilt/jarvis_memory.py:796-813`), but OpenJarvis writes facts as one-per-line JSONL. A real OpenJarvis facts file would import 0 facts. It matters little, since OpenJarvis never ran.

Research clones are read-only, in `/tmp/claude-0/research/` (ace, ha-core, zynkbot, mem0, graphiti, letta-code, langmem, khoj, pypi/gepa_src). OpenJarvis is at `/home/user/open-jarvis/openjarvis`.

## 7. To revisit later (owner's request, 2026-09-23)

**A local "teacher" model.** OpenJarvis's teacher is a cloud model, which breaks
rule 1. The local version would be a larger model on the owner's own PC that
checks and improves the everyday one - for example by suggesting better
wording for a skill note, or by reviewing answers the owner marked wrong. Not
built now because the 8 GB RTX 2080 Super cannot hold a model much larger than
the chat model, and a teacher barely smarter than its student teaches little.

A narrower follow-on, to decide at the same time: training only on facts the
owner has already approved (never on raw chats), kept only if the owner's own
right/wrong marks show it helped. Everything section 5 says against
fine-tuning still applies - what training learns cannot be listed or removed
one fact at a time - so this needs its own decision, not a default yes.

**Revisit when both are true:**
1. The second graphics card (RTX 2060 12 GB) is installed, so a larger teacher
   model can run - most likely overnight, while the chat model is idle.
2. Item 1's "that was wrong" marks have been collecting for a few weeks, so
   there is real evidence of what goes wrong, and a way to tell whether the
   teacher actually helped.
