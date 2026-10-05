# Epic Jarvis: full feature review (2026-10-04)

A whole-project review, asked for by the owner: what is missing that other
projects have, what should be removed, and what should change. Nothing in this
report was built, removed or edited while it was written - every claim is
evidence from the repository at `fb1433fd` (branch
`fix/2026-10-04-audit-pass`), the owner's own PC, or a source named with a link.

## How to read this

- **Part A** is what is missing. **Part B** is what to remove. **Part C** is what
  to change or fix. **Part D** is the risk register. **Part E** is complexity
  and maintenance. **Part F** is the owner's own side of it.
- Every finding has a file path or a link, and the method is stated when a number
  is given. Where something could not be checked it says **unverified** rather
  than guessing - the project's own rule, and this review keeps to it.
- Findings are marked **[verified]** (seen in code or on the PC during this
  review), **[reported]** (stated by a project document, not re-checked), or
  **[unverified]**.
- Severity is stated as **high / medium / low** for what it costs the owner.

## 0. The short version

Jarvis is not short of features. It is short of **evidence that its features
work, that they are used, and that the owner can find them.** Measured today:

| What | Number | Where it comes from |
|---|---|---|
| Backend modules | 147, 8.8 MB | `backend/jarvis_*.py` |
| Backend tests | 249 files | `backend/test_*.py` |
| Backend patches | 121 (plus 130 history copies) | `backend/*.patch` |
| Things Jarvis can do, per its own spec | 108 numbered API sections (numbered to 114, with 66-69, 76 and 111 never written), 203 routes on the live backend, 249 desktop / 222 phone routes | `docs/JARVIS-API.md`, `tools/check_parity.py` |
| Gate actions ("what asks first") | 70 rows, from 80 tier lines | `backend/jarvis_reach.py`, `rebuilt/jarvis-framework.toml` |
| Commands the owner can say with no model | 93 distinct intents | `backend/jarvis_quick.py` |
| Desktop windows / Tauri commands / global hotkeys | 10 / 339 / 10 | `jarvis-desktop/` |
| Phone screens / API paths | 14 reachable / 224 | `jarvis-client/` - **corrected 2026-10-05**, was 13: see [UI-AUDIT §0](UI-AUDIT-2026-10-05.md) for this and the other recount |
| Settings cards, desktop / phone | 33 (+31 jump links) / 18 rows | `settings.html`, `SettingsScreen.kt` - **corrected**: was 34 / 33 jump links |
| Docs | 277 markdown files, 593,000 lines, 19 MB | `docs/` |
| Commits | 1,978, in about nine days | `git rev-list --count HEAD` |

**The seven findings that matter most:**

1. **The second graphics card is installed, and the project still behaves as if
   it is not.** `nvidia-smi` on this PC reports an **RTX 2060 12 GB** (card 0)
   and the **RTX 2080 SUPER 8 GB** (card 1). [verified] Around a dozen features -
   long conversations, pictures, background learning, browser control, the wiki
   builder, the study helper, the camera in Jarvis Live, a bigger voice - are
   built and switched off "until the second card is installed and measured"
   (`docs/SECOND-CARD.md`, `docs/ARCHITECTURE.md` §10). The card is in, so they
   are now **eligible to be measured** - which is not the same as unblocked: the
   standing rule is "installed *and measured*", and nothing has been measured
   (`docs/JARVIS-API.md:1986` still says "the second card is not installed";
   `~/.openjarvis/config.toml:5` still names only the 2080 SUPER). **No document
   says the facts changed.** This is the single highest-value action in the whole
   review: measure the card, write the numbers down, then turn on what they
   justify - or delete what they do not.
2. **No one can tell which features are used, including the owner.** There is no
   usage counter and no telemetry (correctly - `backend/test_telemetry_off.py`),
   and there is nowhere to see past approvals or settings changes
   (`docs/EASE-OF-USE-AUDIT-2026-09-27.md:27`). The one place that could answer
   it - `~/.openjarvis/approvals.db` - holds **11 rows in total**, of which 3 are
   real (model switches on 21-22 September, one approved from the HUD) and 8 are
   test noise from 3-4 October whose prompts name `https://example.com/...`.
   [verified] Everything below about "probably unused" is derived from gates and
   defaults, never from behaviour, because there is no behaviour data.
3. **A whole class of features is built, documented, offered in the UI, and
   cannot work.** The clearest three: the cloud escalation button (no transport
   exists - the request goes to a port nothing listens on; `litellm` is not even
   a dependency, yet three cloud lanes are advertised from an inherited config
   file); the plan card (`propose_plan` is gated on a measurement file that does
   not exist); and the desktop's "Grade this better" (four registered commands,
   no permission grant, so the button never appears). [verified - see Part C]
4. **The project's own research already found most of the missing features, and
   the queue is where they died.** `docs/CUTTING-EDGE-2026-09-26-*.md` (four
   rounds), `docs/FEASIBILITY-AUDIT-2026-09-26.md` (155 ranked ideas) and
   `docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md` produced a large, ranked backlog.
   A good part of it was built; a good part is still sitting there unbuilt while
   new features were added on top. Part A separates the two.
5. **The repo carries things that have nothing to do with Jarvis and should not
   be in it**: 199 MB of launch videos in `videos/` (232 tracked files), a
   vendored telemetry npm package at `tel/` plus a stray tracked tarball at the
   root, a 13.5 MB stale copy of the phone's source in `docs/`, a "not used by
   Jarvis" WebSocket server at `server/`, two leftover scratch transcripts, a
   nested duplicate directory, and 88 MB of untracked agent scratch in
   `dshwork/`. [verified - see Part B]
6. **The docs have drifted from the code, which is the failure mode this project
   audits for.** `docs/README.md` calls `SOURCE-BUNDLE.md` "720 KB" when it is
   13.5 MB and says "about ninety documents" when there are 277; 31 docs -
   including both 2026-10-04 handoffs - are not in its index; the phone's README
   still promises a connection method that was reversed on 2026-09-28;
   `MENU-VISIBILITY-DESIGN.md` still says "designed, not built" about a built
   feature; `CLAUDE.md` says the owner is *adding* the second card.
   [verified - see Part E]
7. **The most useful thing to build next is not a feature.** It is a way to see
   what Jarvis did: a local, content-free usage counter plus the past-approvals
   list the backend already sends and both apps ignore. Every removal decision
   in Part B, and every future one, becomes answerable instead of argued.

---

## 1. What Jarvis is today [verified]

Written from the repository itself (`docs/JARVIS-API.md` headings,
`backend/*.patch`, `backend/jarvis_*.py`), so the review does not re-propose
what exists. Grouped by area; each item exists as a patch, a module and tests.

- **Voice** - "Hey Jarvis" wake word (two detectors, the second confirms), owner
  voice-ID gate, speech-to-text and text-to-speech on the PC, barge-in, Kokoro
  v1.0 voices, two blended voices, lip sync from Kokoro's own phoneme timings,
  talk-to-type on the PC, enrolment and training screens.
- **Chat** - local-first turn routing, streaming answers, encrypted history,
  forks, tags and sections, temporary chats, imported third-party chats, a
  scrollable thread, opening a chat by phrase.
- **Memory** - extraction from the owner's own words only, a review queue,
  auto-learn with sensitive gating, entities, bitemporal "true from/until",
  Forget and Erase-the-words, forget-a-time-frame, reranker, overnight tidy.
- **Email, notes, documents** - IMAP read, drafts, send, inbox tidy, one-time-code
  masking, Obsidian/Logseq/Joplin writes, PDF and Word folders, Notion import,
  a wiki builder.
- **Time and home** - one shared scheduler for timers, alarms, reminders,
  briefings, standby, "tell me when", page watches; Home Assistant control with
  a multi-device card; Google Calendar read by private iCal link.
- **Search and browsing** - five web-search providers, RSS news, a visible
  Playwright browser, a headless browser (Obscura) with stealth.
- **Screen and vision** - "Look at this", "Watch with me", Windows text reading,
  secret blackout before any model, a slow CPU picture mode.
- **Chatbot driver** - nine chatbot websites, an OpenAI-style API adapter for six
  services with money limits, local compare, customer-support chats, a captcha
  hand-off to the phone.
- **Projects, goals, money** - projects with benchmarks, app-building tasks,
  goals with per-step cards, the plan card (off), spending summaries, retirement
  what-if, progress charts.
- **Learning** - quiz from notes and YouTube captions, cloud grading, FSRS
  review decks, Spanish practice, tutorials.
- **Safety** - the one gate and its tiers, "What asks first", Windows Hello for
  risky approvals, phone signed approvals, lockdown, Stop everything, paste
  guard, log scrub, encrypted backup, crisis help.
- **Devices** - QR pairing with per-device keys, phone notifications, ring-my-phone,
  smartwatch setting, floating HUD, widgets and Quick Settings tiles.
- **Ops** - live preflight, doctor, data health, tool updates, hardware presets,
  second/third-card management, a big slow model, speed records.
- **Personality** - manner (warm/plain), humour, "between us", five 3D faces,
  sky, sun and moon, scene weather.

**What that costs to carry**, stated plainly: 147 modules, 8.8 MB of Python, 249
test files, 121 patches that 100-times edit the same file (`jarvis_hud.py`), a
1.1 MB backend manual, a 1.2 MB API spec and 277 documents - for one owner on
one PC. That is not an argument against any single feature. It is the reason
finding 2 (nobody knows what is used) is the most important one.

---

## Part A - What is missing

Three different things get called "missing", and they need different answers:

- **A1 - Already decided or already researched by this project, still unbuilt.**
  Nothing new to invent; the work is to finish or to cancel.
- **A2 - New, from outside.** What other projects on GitHub do that Jarvis does
  not. Each has a link. Checked against the repository first, so nothing already
  built appears here.
- **A3 - Capability gaps found in this review** that are not a feature in anyone
  else's list: mostly the things that make a big feature set usable.

### A1. Decided or researched, still unbuilt

Found by walking `CLAUDE.md`'s decision log, `docs/BUILD-QUEUE-2026-09-30.md`,
`docs/HANDOFF-AFTER-PR39.md` and the tree, then checking each against the code.
Ranked by how much the owner appears to care (an explicit "build it" ranks
highest). "Not built" means no code, no route and no test found.

| # | Item | Decision | State today | Note |
|---|---|---|---|---|
| 1 | **Prompt-injection detector bake-off** - "test two, keep the winner" (Meta's Prompt Guard 2 and an Apache-licensed one) | 2026-09-28, kept in the 2026-09-30 queue as item 9, milestone 2 | **Nothing built.** No `prompt_guard` / `guard-small` anywhere; only Jarvis's own attack tests (`backend/agentdojo_injections.json`, `test_injection_cases.py`) exist. An audit already recorded it: `docs/audit-reports-2026-09-29-30/25-audit-afc29a09.md:33` | The one safety feature the 2026-10 PR wave skipped. Small, CPU-only, and for a small model reading outside text it is the highest-value safety item left |
| 2 | **GitHub tools: add and update a tool, open a pull request** | 2026-09-30, owner chose "Full: add and update" | **Design only** (`docs/GITHUB-TOOLS-DESIGN.md`, "Status: designed, not built"). JARVIS-API §111 is reserved and empty | Was waiting on the 12 GB card; the card is in |
| 3 | **Multi-model work: failover, then a checker, then local compare, plus a per-lane measured log** | Owner's order, `docs/HANDOFF-AFTER-PR39.md:344-364` | **Nothing built** - `failover` has 0 hits repo-wide | Also waiting on the card, which is now present |
| 4 | **Milestone 4 - one-line lesson from each "wrong" mark, offered on a card** | 2026-09-28 | **Nothing built**; `lesson` appears only in unrelated comments | Silently dropped from every queue after 2026-09-30 |
| 5 | **Milestone 9 - "match my speaking pace" setting, both apps** | 2026-09-28 | **Nothing built**; no registry row | Silently dropped |
| 6 | **Milestone 11 - offline developer docs (Dash/Zeal docsets)** | 2026-09-28 | **Nothing built** | Silently dropped |
| 7 | **Milestone 6 - a skill that fails twice stops being offered and asks "keep or turn off?"** | 2026-09-28 | **Nothing built**; `jarvis_skill_discovery.py` only suggests | Silently dropped |
| 8 | **Milestone 5 - multi-hop memory, kept only if the self-tests improve** | 2026-09-28 | Measurement built (`eval_memory.py --locomo`); the memory change is not - and on LoCoMo the entity layer "made every number worse" (`CLAUDE.md:1027-1029`) | Blocked on an honest measurement, not on effort |
| 9 | **Milestone 14 - PrefEval questions for "From now on..." preferences** | 2026-09-28 | No fixture; the behaviour itself is built (`jarvis_quick.py:2579-2599`) | Test data only |
| 10 | **Queue items 8-10: a per-patch test ratchet; "Restore to before" for an app merge; a stale-area check after every big merge** | 2026-09-30 | Per-suite checks exist; no pinned global ratchet; `restore_to_before` and `stale-area` = 0 hits | Test-quality work, not user-facing |
| 11 | **Memory/storage remainder: "What Jarvis is using", a warning at 50k facts, gzip for the audit log** | `HANDOFF-AFTER-PR39:373-385` | `db_bytes` exists; the rest does not | The audit log on this PC reached 373 KB in a single day during the 2026-10-04 audit pass (`~/.openjarvis/logs/jarvis-2026-10-04.jsonl`), so the gzip item is real |
| 12 | **Milestone 3 - "quiz me on my notes" with FSRS** | 2026-09-28, "deferred until a note-review screen is designed" | **Superseded**: FSRS decks and Spanish practice shipped instead; quiz sources are pasted text and YouTube only, with no notes source | Worth confirming with the owner rather than rebuilding |
| 13 | **The feasibility audit's 31 small items** | 2026-09-27, "queued after the four groups" | **Unverified** - not checked one by one in this review | A candidate for a short, separate pass |

**Still-open decisions the owner never answered** (each is a question, not work):
Antigravity / Google-account cloud access (`CLAUDE.md:1078-1082`); the "Keep"
question for quizzes made from outside text (`HANDOFF-2026-09-30:84-88`); Bubble
mode's `MessagingStyle` redesign (`CLAUDE.md:457-464`); screenshot blocking on
the desktop (`docs/research-audit-2026-09-28/inventory.md:226`); Wake-on-LAN and
Live camera framing hints (`docs/RESEARCH-AUDIT-2026-09-28.md:295-300`).

**And one piece of work already on disk that needs finishing:** the branch this
checkout is on (`fix/2026-10-04-audit-pass`, 46 commits ahead of `origin/main`,
2 behind) carries the tutorials/FAQ feature - API §114, `jarvis_tutorials.py`,
`tutorials.js`, `Tutorials.kt` - with three Rust permission files still modified
in the working tree (`jarvis-desktop/src-tauri/permissions/autogenerated/
{get_faq,get_tutorials,mark_tutorial}.toml`). [verified] Under the project's own
standing rule it needs its feature audit and, when the owner asks, one pull
request.

### A2. New: the strongest candidates from outside

Ranked by value for this project. **Cost** is a rough class: **S** under a day,
**M** a few days, **L** a week or more. Rule notes refer to the five rules in
`README.md`.

**Tier 1 - worth doing**

| # | Feature | Where it comes from | Why it matters here | Cost | Rules |
|---|---|---|---|---|---|
| 1 | **A local usage counter and a visible past-approvals list** | This review (the "findings" pattern is standard; the backend already sends the list) | Nothing else in this review can be decided well without it. `JARVIS-API.md` §41 already sends past approvals and both apps ignore them (`docs/EASE-OF-USE-AUDIT-2026-09-27.md:27`). A counter of *feature → times used* stores no content, so rule 1 is untouched. | S | Strengthens rule 1 |
| 2 | **llama-swap** ([mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap)) | A small local proxy that starts model servers on demand and **stops the previous one so its memory is freed first** | This is exactly the 8 GB + 12 GB co-residency problem Jarvis solves with its own hand-rolled lane logic (`backend/jarvis_second_card.py`, 207 KB). A proven swapper removes hand-rolled unload ordering - and the second card is now installed, so the problem is live. | S | None |
| 3 | **Speculative decoding** ([llama.cpp](https://github.com/ggml-org/llama.cpp)) | A small draft model proposes tokens, the 8B verifies them: roughly 1.5-2x on a card like the 2080 Super | Ollama does not expose a draft model, so this means a second `llama.cpp` lane - which the two-card design already supports. Directly improves the 2.5-4 s wait the voice path suffers. | S-M | None |
| 4 | **A semantic answer cache** ([GPTCache](https://github.com/zilliztech/GPTCache)) | Reuses an answer for a near-identical question, using the embeddings Jarvis already has (`fastembed`, bge-small) | Cuts the wait on repeated questions ("what's on today"). **Must refuse to cache** any turn that used outside text, a sensitive fact or a tool - otherwise it becomes a privacy leak. | S | Tension with rule 1 if careless |
| 5 | **A local trace file in the standard shape** ([OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)) | Standard field names for model, tokens, latency and tool calls, written to a local JSONL | The project already asked for this ("a per-lane measured log", `CLAUDE.md`, queue item 7) and the 2060's numbers are unmeasured. Following the standard costs nothing and makes the numbers comparable with anything else. | S | None |
| 6 | **A Windows Firewall outbound rule per process** ([Windows Firewall](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/)) | Rule 2 ("no public tunnel") is enforced today by Python, in `jarvis_reach.py` | An OS rule enforces it even if a dependency misbehaves. This is the cheapest way to make the project's strongest promise independent of its own code. | S | Strengthens rule 2 |
| 7 | **A low-integrity token for plug-in programs and code steps** ([AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)) | Runs an MCP server or a code step with no read access to `memory.db`, the vault or credentials | An MCP server or a poisoned tool cannot exfiltrate what the gate would have blocked. Rule 4 is only as strong as what the acting process can reach. | M | Supports rules 1 and 4 |
| 8 | **Better local document reading** ([docling](https://github.com/docling-project/docling), [MinerU](https://github.com/opendatalab/MinerU)) | Jarvis converts documents with MarkItDown; these are materially better on tables and multi-column pages | "Ask my documents" loses information exactly where documents are hardest. Local only; docling is heavier because it uses models. | M | None |
| 9 | **Android AppFunctions** ([Android AI platform](https://developer.android.com/ai)) | A typed way for the assistant to call a phone app's own declared functions instead of driving its UI | Replaces fragile screen-tapping on the phone and keeps the phone out of speech-to-text. | M | None |
| 10 | **A duress/decoy lock on the phone** | Idea from [Android-AntiForensic-Tools](https://github.com/bakad3v/Android-AntiForensic-Tools) | Jarvis holds the owner's whole life; App lock alone does not cover "opened under coercion". **Lock-and-hide only** - a wipe would need its own card. | S | Rule 4 if it wiped |

**Tier 2 - worth having later**

| # | Feature | Why / caveat |
|---|---|---|
| 11 | **An in-app command palette** ("/" over Jarvis's own actions) | It was in the original desktop design and appears dropped; the desktop already has 104 menu entries and 10 hotkeys, so finding things is the actual problem. **Build it inside Tauri** - a PowerToys extension would put the pairing token in another process (rule 3). |
| 12 | **Per-turn tool allow-lists** ([LocalAGI](https://github.com/mudler/LocalAGI)) | Cheapest fix for "tool descriptions crowd out the conversation" - the 8B sees a short list, the server enforces it. |
| 13 | **"A named check must pass before answering"** ([LocalAGI](https://github.com/mudler/LocalAGI)) | Enforced on the output side, so a small model cannot skip it. Useful for "did I read outside text this turn?" and quote checks. |
| 14 | **Context compaction** ([Letta](https://github.com/letta-ai/letta)) | Rolls old turns into a summary so long chats fit the window. Any summary must never become memory, and must not turn outside text into a fact. |
| 15 | **A summary tree over documents** ([RAPTOR](https://github.com/parthsarthi03/raptor)) | Answers whole-document questions without a huge window. Fits the 12 GB card, which is now present. |
| 16 | **Streaming speech detection for "stopped talking"** ([Moonshine](https://github.com/moonshine-ai/moonshine), [Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)) | Shortens the wait. **The voice-print check still needs the complete clip**, so streaming may only drive endpointing. |
| 17 | **A standing offline red-team suite** ([Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), [garak](https://github.com/NVIDIA/garak)) | The project has memory/learner/tool evals but no standing injection suite. Dev-only; keep it offline. |
| 18 | **Accessibility work already listed as open** ([Compose a11y testing](https://developer.android.com/develop/ui/compose/accessibility/testing)) | TalkBack custom actions for Approve/Deny, tap-to-talk, High Contrast/Narrator on the frameless windows, a font-scale test. Cheap, and it is already in the project's own notes. |
| 19 | **An energy / tokens-per-answer meter** | Makes the one-card vs two-card trade-off visible in numbers rather than adjectives. |
| 20 | **A far-field microphone** ([Wyoming](https://github.com/rhasspy/wyoming), [Willow](https://github.com/toverainc/willow)) | A cheap ESP32 satellite gives room voice over the LAN. The voice-print gate must run on the PC unchanged. |

**Tier 3 - deliberately not recommended** (so the owner does not have to
re-litigate them): A2A (built for many organisations), autonomous coding agents
(standing grants - the opposite of rule 4), always-on screen capture (owner said
no), pixel-loop GUI agents (a pixel pointer has no name to re-check before
clicking, which is the whole safety property of `jarvis_ui_control.py`), graph
RAG servers (LightRAG's own README calls its default stores unfit for production
and names a 30B model as the local minimum), the `mem0` package (telemetry on by
default), n8n/Node-RED (a second automation engine), launcher plug-ins (the token
again), NeMo Guardrails/Rebuff (a hosted or dialogue-flow-shaped layer in front
of every turn), MCP Apps (a server drawing inside Jarvis's windows is a new
injection surface), Docker/WSL2 packaging, and phone-side speech-to-text - all
already refused in the repo or by a standing rule.

### A3. Capability gaps that are not anybody's feature list

1. **A way to see what Jarvis did and what it is doing.** Past approvals are
   sent and ignored; there is no history of settings changes; the Brain's "Now"
   tab shows only steps, and the model's private reasoning is deliberately not
   published (correctly - `docs/ARCHITECTURE.md` §10). What is missing is a plain
   local record: what ran, when, whether it was approved, and how long it took.
2. **A way to know what is switched on.** The model is offered 2 of its 28 tools
   on this PC, and the list comes from an inherited config file whose four names
   are mostly not Jarvis tools (C2 #3); the repository's own shipped config names
   one (`enabled = ["web_search"]`,
   `backend/rebuilt/jarvis-framework.toml:1615-1616`). Everything else is opt-in
   by hand-editing a 1,616-line TOML file. There is no single screen that says
   "these abilities are on, these are off, and here is the one card to turn each
   on".
3. **Context compaction for long chats** (see A2 #14): the concrete limit of a
   16k window on 8 GB.
4. **A second copy of the backend under version control.** Seven patched files
   (`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_extract.py`, `jarvis_memory.py`,
   `jarvis_events.py`, `jarvis_models.py`, `jarvis_skills.py`) exist only on the
   owner's PC; about twenty suites are skipped in CI because of it
   (`backend/run_suites.py:6-13`, `:51`). This is the project's biggest
   reliability risk and it was already named as such in
   `docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md` (item 7 of "missing things").
5. **An installer.** The desktop updater is wired but publishes nothing until a
   signing key exists; the phone publishes only from `main`; and the backend has
   no download at all, which the project's own ease audit calls the point where
   "everyone but you stops" (`docs/EASE-OF-USE-AUDIT-2026-09-27.md:54-56`).

---

## Part B - What to remove

Ranked by value gained against risk of removal. Nothing here was done - this is
a list for the owner to approve or refuse, item by item.

### B1. Things in the repository that are not Jarvis (low risk, do first)

| # | Remove | Evidence | Why | Risk |
|---|---|---|---|---|
| 1 | `dshwork/` - 88 MB, 3,028 untracked files | `docs/HANDOFF-2026-10-04-audit-pass.md:502-512` says it "can be deleted once its reports have been read" | Agent scratch, not part of the product | Keep `dshwork/audit-2026-10-04/staged-backup/` until the owner is happy with the two staged modules - the handoff says so |
| 2 | `final-run.txt` (133 KB), `final-run2.txt` (58 KB), `yt-out.txt` (33 KB) at the repo root | The same handoff, line 509: "the previous pass's leftovers; still safe to delete" | Old test output pasted to the root | None |
| 3 | `evidence-dev-telemetry-2.1.3.tgz` (**tracked**) and `tel/` | `tel/package/package.json` is `@evidence-dev/telemetry`, a third-party telemetry package; nothing in Jarvis imports it [verified] | An unused telemetry package sitting in a project whose first rule is "nothing leaves the PC" is indefensible, even unused | None. Delete both, or write one line in `THIRD-PARTY-NOTICES.txt` saying why it is kept |
| 4 | `Epic-Jarvis-main/Epic-Jarvis-main/docs/HANDOFF-GATE-ENTRIES-2026-10-03.md` | The same file exists at `docs/HANDOFF-GATE-ENTRIES-2026-10-03.md` [verified] | An accidental nested copy of the repo root | None |
| 5 | `docs/SOURCE-BUNDLE.md` - 13,469,567 bytes | `docs/README.md:93` already calls it stale: "A 720 KB copy of the phone app's source at an old commit... The real source is in `jarvis-client/`" [verified - it is 19x the size the index claims] | 13.5 MB of the 19 MB `docs/` is one dead generated file | It was made for an outside audit. Keep a link to the commit instead if it is ever needed. Removing it does not touch git history, so nothing else breaks |
| 6 | `jarvis-desktop/src-tauri/target/` - 2,010 MB of debug output | `target/` holds only `debug/`, no release build [verified] | Two gigabytes of build cache on the owner's disk | None - it is regenerated by the next build. `cargo clean` |
| 7 | `backend/__pycache__/` (10.2 MB, 168 files) and `backend/rebuilt/__pycache__/` | Both are in `backend/.gitignore`, zero tracked [verified] | Generated bytecode, ~2.3x the size of the source it caches | None |
| 8 | `videos/` - 199 MB, 232 tracked files | [verified] | **Not a removal** - the owner's rule is that every launch video is kept on GitHub (`CLAUDE.md:1998-2015`). Recommendation: move the `.mp4`s to **Git LFS** or attach them to the existing releases, keeping the posters and the plans in the tree | Low, if LFS is set up first. Without LFS, every clone of this repo pays 199 MB |
| 9 | `server/` - 3 files, 41 KB | `server/README.md:3` says it itself: "**Legacy - not used by Jarvis.** Nothing in Jarvis imports or starts `jarvis_mobile_ws.py`... whether to delete it is the owner's call" [verified] | It also carries a real hazard if ever run: without a token, "anything that can reach the port can connect and answer approval requests" (its own README, security audit L6) | Low. The old phone app it served is itself a candidate for removal (item 10) |
| 10 | `jarvis-android/` - 63 files, 5,259 lines | Everything worth having was ported in 2026-09 (`jarvis-client/widget/ApprovalWidget.kt:48-60`, `QuickLinkWidget.kt:39-47`); no legacy artefacts remain in `jarvis-client` (grep for `mobile/ws`, `approval_request`, `audio_stream_start`, `com.jarvis.assistant` = 0 hits) [verified] | It keeps **an HMAC signing secret and a bearer token in plain `SharedPreferences`** (`JarvisSettings.kt:53-64`) and allows cleartext to `.local`, both against the phone rule of 2026-09-28; and it costs a whole CI workflow (`android-apk.yml`) that publishes nothing | Low for the product, medium for the owner's attachment to it. Alternative: move to `legacy/`, fix the two rule problems, cut the workflow to a compile check |
| 11 | Stale backup files in the live backend folder: `jarvis_hud.py.bak`, `jarvis_hud.py.before-loopback`, `jarvis-framework.toml.backup-2026-10-03-210230` | Listed in `Desktop program\` [verified] | Three old copies beside the real files, one dated and two not | None |
| 12 | **Five paths are protected only on this machine** - `dshwork/`, the nested `Epic-Jarvis-main/`, `final-run.txt`, `final-run2.txt`, `yt-out.txt` | They are excluded by `.git/info/exclude:8-12`, which **is never cloned**; `.gitignore` (60 lines) mentions none of them. [verified] Also not ignored anywhere: `*.mp4`, `*.jar`, `*.tgz`, `*.log`, `*.gguf`, `*.onnx`, `.venv/`, and `_jarvis-backup-*` - the timestamped folder `apply-patches.ps1` creates beside the backend it patches | On any other machine, or after a fresh clone here, `git add -A` sweeps **88 MB of agent scratch into the repository**. No tracking is involved, so nothing needs a history rewrite | None - append the patterns to `.gitignore`. The cheapest fix in this whole review |
| 13 | `docs/critters/eyelids-preview/` - 4 files, 2.70 MB | Its own `README.md:3` says "This branch (`eyelids-preview`) is a prototype... **The main branch does not have it**" - and it is in main. Its generator, `render-lids.mjs:4`, imports from `/home/user/Epic-Jarvis/.claude/worktrees/agent-abd7d5ab573657428/...`, a path that does not exist [verified] | Unreproducible images from a deleted worktree, referenced by nothing outside their own folder | None |
| 14 | The nested `Epic-Jarvis-main/Epic-Jarvis-main/docs/HANDOFF-GATE-ENTRIES-2026-10-03.md` | 6,988 bytes, content-identical to `docs/HANDOFF-GATE-ENTRIES-2026-10-03.md` [verified] | An accidental second copy of the repo root | None |
| 15 | **45 byte-identical fixture pairs** across the two clients - 2.34 MB | `jarvis-desktop/tests/fixtures/*.json` and `jarvis-client/app/src/test/resources/contract/*.json` (e.g. `live-cases.json` 494,236 B each, `asks-first-cases.json` 274,855, `menu-cases.json` 195,733 - 38 more). Both copies are written by the same generator (`tools/gen_live_cases.py:58-59`), and **no test or CI step asserts the two agree** | Two copies of the same contract data, refreshed by hand-running a generator, with no guard. This is the shape that drifts | Low - symlink one path, or add one CI step that hashes both. **It has already happened once:** `jarvis-visual-spec.json` exists at 73,121 bytes (desktop) and 75,171 bytes (phone) [verified] |

### B2. Leftovers from the template Jarvis was built on (`~/.openjarvis`)

Jarvis's backend grew out of an older assistant ("OpenJarvis": the state folder
is still `~/.openjarvis`, and `litellm-proxy.yaml` says "OpenJarvis cloud
escalation lanes" in its own header). A set of files in that folder is written by
nothing in the current code - checked by grepping the live backend for each name
[verified]:

| File | What it is | Written by current code? |
|---|---|---|
| `anon_id` (38 bytes, a UUID) | An anonymous identity for telemetry | **No writer found** |
| `telemetry.db` (1 row, plus an empty `mining_stats` table) | Template telemetry store | **No writer found.** The code that would have sent it is switched off on purpose (`jarvis_child_env.py:33`, `test_telemetry_off.py`) |
| `version-check.json` | Reports `latest_version 1.0.3` for a backend whose own version is `0.0.1.dev1` - an upstream update checker | **No writer found** |
| `traces.db` | 1 trace, 1 step | **No writer found** |
| `agents.db`, `digest.db`, `audit.db` | Template tables, all empty | No writer found |
| `MEMORY.md`, `SOUL.md`, `USER.md` | `# Agent Memory`, `# Agent Persona`, `# User Profile` - empty stubs | No writer found |
| `cloud-keys.env` (1 byte) | An empty plain-text key file | **Nothing reads it** - and a plain-text key file would break rule 3 if it ever were used |
| `litellm-proxy.yaml` (4,805 bytes) | Three cloud lanes pinned to free OpenRouter models, dated 2026-09-12 | Read by the HUD's lane discovery, but the proxy it configures is not installed (see C1) |
| `tripwire.json` | A model sanity probe from 2026-09-22; one probe ("english") **failed** | Written by `jarvis_models.py` via `jarvis_tripwire.py` - this one is live |

Recommendation: delete the first seven rows (or move them to an `attic/` folder
inside `~/.openjarvis`), and deal with `litellm-proxy.yaml` as part of C1. Keep
`tripwire.json`. None of this is tracked by git, so nothing in the repository
changes - but "a telemetry database and an anonymous ID sit in my assistant's
state folder" is exactly the kind of thing rule 1 exists to prevent, even when
the writer is gone.

### B3. Things that should have been built, not removed - but should be deleted if the owner does not want them finished

1. **The nine chatbot website adapters** (~164 KB,
   `jarvis_chatbot_{gemini,chatgpt,claude,copilot,perplexity,deepseek,grok,lechat,metaai}.py`).
   Every one was written without ever reaching its site - each file's own header
   says so - and `built=False` on the Gemini adapter
   (`jarvis_chatbot.py:441`). [verified] The owner explicitly asked for all nine
   (2026-09-28), so this is **not** a removal recommendation. It is a "try one
   for real, then keep only what works" recommendation. The second card being
   installed removes the last excuse.
2. **`jarvis_initiative.py` and the `/api/initiative` route.** No module imports
   `jarvis_initiative` (checked across all 172 live modules) and no window calls
   the route (`tools/check_parity.py`: "In an allow-list, asked for by no
   window"). `docs/ARCHITECTURE.md` §10 still describes it as the engine that
   "could not host" the scheduler. [verified] Either delete it or give it its
   original job back (the queue's "stale-area check" and "what is Jarvis doing"
   work would both fit there).
3. **Two more orphans in the live backend**: `jarvis_structured` (used only by
   `jarvis_extract.py`) and `jarvis_style` (used only by a test). [verified]
   Small, but they are the kind of thing that makes a 172-module folder
   unauditable.

### B4. Features that may be useless in practice - measure before removing

This is the honest answer to "which features are useless". **There is no usage
data** (Part 0, finding 2), so every entry below is a *hypothesis with evidence*,
not a verdict. The right order is: build the counter (Step 4 of Part G), wait two
weeks, then decide. Each of these is a candidate because it duplicates something
else, is unreachable, or costs more than it can return.

| Candidate | Evidence for "probably unused" | What I would do |
|---|---|---|
| **The HUD window** (`jarvis_hud.html`, plus `shell.html` 102 KB and `jarvis-reactor-kit.html` 305 KB in the backend folder) | It is a third view of the same data: its Approve/Deny buttons are removed (`hud_bootstrap.js:932-943`) and its chat box is replaced with "Open the Jarvis bar" (`:1019`). It is reachable from one tray row | Measure; if unused, remove the window and the tray row and keep the Brain |
| **The Brain's ability map** | Built from the inherited `~/.openjarvis/config.toml`, so it can only ever show two or three names, two of which are not Jarvis tools (C4 #1) | Repoint it at `jarvis_agent.TOOLS` or delete the map - do not leave it showing wrong names |
| **`jarvis_initiative.py` and `/api/initiative`** | No importer, no caller (B3 #2) | Delete, or give it the "stale-area check" job it was meant for |
| **Two unbound hotkeys** (`toggle_watch`, `toggle_live`) | Ship with no key bound (`hotkeys.rs:59-144`) | Bind them or remove the rows from Settings |
| **The `notify` tier** | One member out of 80 tier lines | Fold it into `auto` with a note, or give the other note-writers the same tier |
| **Single-use phrases in `jarvis_quick.py`** | 93 intents in a 4,679-line module with a 344-line matcher; candidates: `identity_help`, `sayable_help`, `lists_which`, `where_put`, `lockdown_status`, `widget_make` | Remove the ones with no remembered use; each removal shortens the matcher |
| **`website chat` adapters nobody has ever reached** | Nine adapters, none ever run against its site (B3 #1) | Try one for real; keep what works |
| **Third view of the same setting** | Menu visibility is expressed three ways (Settings card, Brain rail row, by voice); faces have four or more entry points; two voice cards | Collapse each to one entry point plus a link |
| **`server/jarvis_mobile_ws.py` + its test** | 894 lines for an app that cannot use it (B1 #9, B1 #10) | Delete with `jarvis-android` |
| **`docs/` history (277 files)** | 19 MB, and 13.5 MB of that is one dead bundle (B1 #5) | Keep the audits but move the 2026-09 one-offs into `docs/archive/` with the index generated from the folder |

---

## Part C - What to change

### C1. Features that are built, offered, and cannot work (fix or delete)

1. **The cloud escalation button has no transport.** [verified]
   - `POST /api/chat` sends a non-local lane to `JARVIS_URL` (default
     `http://127.0.0.1:8000`) or to the LiteLLM proxy on port 4000.
     `backend/ollama-direct.patch:12-18` says it in its own words: "this project
     has no other cloud-lane transport today. That path is therefore
     unimplemented in practice on a machine with no `litellm-proxy.yaml`, which
     is every machine so far", and `backend/test_ollama_direct.py:9` repeats it.
   - On this PC: nothing listens on 4000 or 8000; `litellm` is **not installed**
     and **not in `backend/requirements.txt`**; yet cloud lanes *are* advertised,
     because `~/.openjarvis/litellm-proxy.yaml` exists and `_lane_names()`
     (`jarvis_hud.py:5739-5748`) reads `model_name:` entries out of it -
     `jarvis-escalate`, `jarvis-critic`, `jarvis-bulk`, all pinned to free
     OpenRouter models with model IDs "verified 2026-09-12".
   - The owner has already set `OPENROUTER_KEY_1` (73 characters) and
     `LITELLM_MASTER_KEY` (41) as user environment variables, and
     `~/.openjarvis/cloud-keys.env` sits empty. So the path looks live and is
     not: pressing "Try the cloud model" in either app ends in
     "Jarvis is not answering on http://127.0.0.1:8000."
   - **The fix is already half-built elsewhere**: `jarvis_chatbot_api.py` talks to
     OpenRouter (and five other services) directly over HTTPS, with the key in
     Windows Credential Manager, an endpoint check, no redirect following and a
     money limit. Pointing the router's cloud lane at that adapter removes the
     LiteLLM dependency entirely. The alternative - delete the offer, the LiteLLM
     status dot and the `PROXY_*` plumbing - is smaller and equally honest.
   - Rule note: keys in **user environment variables** are the template's habit,
     not this project's standard (Credential Manager). Whichever way this goes,
     those two variables should be retired.

2. **The plan card can never switch on.** [verified]
   `jarvis_plan.enabled()` requires
   `tools/tool_eval/tool_eval_results.json`; that file does not exist in the
   repository **or** on the owner's PC (`Test-Path` false in both places), so
   `propose_plan` - wired into `jarvis_agent.py`'s tool table, tested with
   `test_agent_plan_wiring.py` (60 checks) - can never run. Either run the
   multi-step tool evaluation once and publish the result, or say plainly in
   `docs/JARVIS-API.md` §60 that the feature is parked.

3. **The desktop's "Grade this better" does nothing, silently.** [verified]
   `brain_quiz_cloud_info/start/get/cancel` are registered in
   `src-tauri/src/lib.rs`, have permission files, and are called from
   `jarvis-desktop/src/brain.js:9504-9578` - but **no capability grants them**:
   `permissions/surfaces.toml` has zero occurrences of `cloud` or `quiz-cloud`,
   and `capabilities/brain.json:32` grants only `brain-quiz`. The front end
   swallows the rejection (`catch (_) { qz.cloudInfo = null }`), so the button
   never appears and nothing is ever reported. Add a `brain-quiz-cloud` set, or
   delete the four commands and the UI path.

4. **The phone tells the owner a feature is missing while showing it.**
   `jarvis-client/.../ui/OpenPlace.kt:113` lists `"spending"` in `PC_ONLY`, so
   saying "open spending" answers "That setting is only in Jarvis on your PC,
   not on this phone" - while the phone has a Spending card
   (`ui/MenuPlaces.kt:47`, `ui/screens/BrainScreen.kt:517`,
   `net/MenuCatalog.kt:64` marks it `phone=true`, and `ui/screens/SpendingPlate.kt`
   exists). [verified] The nuance is real: what is PC-only is *setting up a new
   bank file's columns* (`net/Spending.kt:56`, "Set up on the PC: Settings,
   Spending"). So the sentence is right about the setup and wrong about the
   feature; "open spending" should open the phone's card. One-line fix either
   way.

5. **Two features cannot be switched on honestly because their download is not
   pinned.** `backend/jarvis_obscura.py:146` and
   `backend/jarvis_screen_picture.py:143` both read `PINNED_DIGEST = ""`.
   [verified] The project's own rule is "the model comes from a
   checksum-pinned line the owner pastes, never fetched by the backend"
   (`CLAUDE.md`, 2026-09-29). Until the digest is filled in, turning either on
   is a hand-install with no check.

6. **A desktop-only screen with no "one-sided on purpose" note.** Notification
   settings are marked `app="desktop"` with the comment "(2026-10-01)"
   (`backend/jarvis_settings_registry.py:225-227`), and
   `docs/ARCHITECTURE.md` §8 has no row for it. The project's own rule is that
   a deliberately one-sided feature must be recorded there
   (`CLAUDE.md:1847-1869`). Either build the phone half or write the row.

### C2. Inconsistencies in the safety model (the owner's decision each time)

1. **One action's tier is looser than it looks - and the code, not the config, is
   what saves it.** [verified, corrected 2026-10-05]
   `backend/rebuilt/jarvis-framework.toml:82` sets `web_research = "auto"`
   (never asks) while `:284` sets `search_the_web = "ask"`, and `web_research` is
   what the gate's own phrase matcher assigns to "search the web / browse"
   (`jarvis_gate.py:205`). The project recorded a live incident about it
   (`jarvis_agent.py:2110-2119`): "`github_search`, which resolves to
   `web_research` - 'auto' in the shipped config - sent a model-chosen search
   term to GitHub with nobody asked." **What stops it being a hole:** the code
   compensates where the config does not - `NEEDS_A_PERSON`
   (`jarvis_agent.py:2131-2144`) names `github_search`, `browser_control`,
   `control_computer`, `shell_exec`, `send_email` and others, "must never run
   unless a PERSON said yes on a card, whatever tier ... gives their action".
   So this is a **config/code mismatch that the code already covers**, not live
   exposure - but it is the kind of mismatch that will bite the next action
   nobody adds to that list. Worth fixing in the config rather than relying on
   the belt.
   ~~`rollback_model = "auto"` while `switch_model`/`download_model` must ask~~ -
   withdrawn: the same file reasons it out at `:250-252`, "reverting is 'auto'
   because a revert that waits for permission arrives too late to be a revert".
   That one is deliberate design, not an inconsistency.
2. **The `notify` tier has exactly one member** (`create_joplin_note`, `:217`)
   while `append_obsidian_daily` (`:235`), `append_logseq_journal` (`:226`) and
   `create_logseq_page` (`:227`) never ask at all. [verified] Four note-writers,
   three behaviours, one owner.
3. **The gate is barely exercised in real use, because so few tools are switched
   on.** [verified - corrected 2026-10-05] `jarvis_agent.TOOLS` holds **28**
   tools. The enabled list the live backend reads is
   `~/.openjarvis/config.toml`'s `[tools] enabled` (`jarvis_hud.py:89`, `:5109`,
   `:5128`), and it is the **template's** list, not Jarvis's: 27 names, of which
   **24 do not exist in Jarvis at all** (`think`, `http_request`,
   `browser_navigate`, `browser_extract`, `browser_click`, `browser_type`,
   `browser_screenshot`, `browser_axtree`, `pdf_extract`, `memory_store`,
   `memory_retrieve`, `memory_index`, `memory_manage`, `knowledge_search`,
   `user_profile_manage`, `calendar_search`, `calendar_upcoming`,
   `queue_action`, `get_pending_actions`, `check_permission`,
   `record_decision`, `code_interpreter_docker`, `get_weather`, `llm`). Only
   three names match a real tool - `calculator`, `memory_search`, `web_search` -
   so **the model is offered 3 of its 28 tools on this PC**. The filter is
   deliberate and documented (`offered_tools`' own docstring,
   `jarvis_agent.py:4327-4337`: offering a name that is not here "would mean a
   turn that can only ever be told 'no such tool'"), so this is not a bug in the
   filter - it is a **config file left over from the template**, feeding the
   wrong list to a live machine. Everything else - `send_email`, `tidy_inbox`,
   `control_computer`, `control_phone`, `browser_control`, `my_files`, the
   calendar/notes/home reads, the plan card - cannot be reached without
   hand-editing that inherited file. The repository's own shipped config names
   one tool (`enabled = ["web_search"]`,
   `backend/rebuilt/jarvis-framework.toml:1615-1616`).
   The consequence is not "too many cards" but "the card system has rarely been
   exercised" - which is also why nobody knows what the daily card load would be.
4. **Two `fixed:` rows promise no card for the biggest surfaces**: `fixed:screen`
   ("Look at your screen... or watch with you") and `fixed:projects` ("Make,
   change or delete a project"). [reported] Defensible - the owner's own words,
   on their own machine - but they are the loosest rows on a page whose purpose
   is to show what asks.
5. **The remaining approval hole, unchanged and documented**: a *non-risky* card
   can still be approved by any program holding the pairing token, and an
   unpaired device on the old **shared key** can still approve risky cards
   (`docs/ARCHITECTURE.md:453-478`). [reported] The cheap attack is closed; the
   expensive one is open. **Concrete owner action available today: retire the
   shared key now that per-device keys and phone signed approvals exist.**

### C3. Documentation that is now wrong

This project treats its documents as the contract - `ARCHITECTURE.md` wins
disagreements (`docs/README.md:8-9`) and every feature must update
`JARVIS-API.md`. Drift is therefore a defect, not tidiness.

| # | Where | What it says | What is true |
|---|---|---|---|
| 1 | `CLAUDE.md` (2,028 lines) | The decision log, ending 2026-09-30 | The tree has decisions dated 2026-10-01 (`jarvis_settings_registry.py:225`) and 2026-10-05 (`docs/JARVIS-API.md:17096`, tutorials). Ten owner decisions from 2026-09-28 (§70, §71, §73, §74, §75, §77, §81, §82, §84, §85) exist **only** inside `JARVIS-API.md` - so reading `CLAUDE.md` alone makes shipped features look unapproved |
| 2 | `docs/README.md:3`, `:93` | "about ninety documents"; `SOURCE-BUNDLE.md` is "a 720 KB copy" | 277 markdown files; the file is 13,469,567 bytes |
| 3 | `docs/README.md` index | 97 links, all valid | 31 top-level docs are not in it, and **four whole subdirectories (92 files) are never mentioned**: `audit-reports-2026-09-29-30/` (63 files), `critters/`, `studio-2026-09-27/` (17), `studio-2026-09-28/` (12). The unindexed set includes current, load-bearing files - `AUDIT-2026-09-28-REPO-REFS.md` (which `CLAUDE.md` twice tells a new session to read first), `PAIRING-DESIGN.md`, `CHATBOT-DRIVER-DESIGN.md`, `CRITTERS.md`, `LIPSYNC.md`, `BUILD-QUEUE-2026-09-30.md` and all three 2026-10-04 handoffs - so the index omits current documents and lists historical ones, which is worse than having none |
| 4 | `CLAUDE.md:2019-2021` | "start here: `docs/HANDOFF-2026-09-30.md`" | Two newer handoffs exist (`HANDOFF-2026-10-04-test-suite-fixes.md`, `HANDOFF-2026-10-04-audit-pass.md`) |
| 5 | `CLAUDE.md`, `ARCHITECTURE.md` §10, `SECOND-CARD.md` | The second card "is not installed"; features are off "until it is installed and measured" | `nvidia-smi` reports **RTX 2060 12 GB** as card 0 and **RTX 2080 SUPER 8 GB** as card 1 [verified] |
| 6 | `jarvis-client/README.md:16`, `:73-77` | The phone may reach the backend over "Tailscale, NordVPN Meshnet, **or the home network**" | Two of the three enforcing files allow mesh only (`data/PhoneAddress.kt:44-49`, `:56-60`, and `res/xml/network_security_config.xml`, whose own comment says home names are left off on purpose), and the owner reversed the home-network choice on 2026-09-28. **Correction:** `data/OwnNetwork.kt` is *not* mesh-only - it is the permissive layer (`OWN_SUFFIXES` at `:50` includes `.local`, `.lan`, `.home.arpa`; `:116-131` accepts 10/8, 172.16/12, 192.168/16, `fc00::/7`, `100.64/10`). It is `PhoneAddress.kt:68` that refuses the home address, at the cleartext step |
| 7 | `docs/MENU-VISIBILITY-DESIGN.md:3` | "Status: designed, not built" | It is built: `settings.html:1098-1115`, `menu-visibility-settings.js`, `menu-visibility.js`, `menu-catalog.js`, `tests/menu-visibility.mjs` |
| 8 | `jarvis-client/.../VoiceButton.kt:44-55` | "Hold to talk... that is a privacy decision" | The code 90 lines below implements tap-to-talk at a pause (the owner's 2026-09-28 decision) |
| 9 | `CHANGELOG.md`, `VERSION` | Newest section stops at 2026-09-29; version 0.2.0 (26 September) | No entry for §99-§114: chat tags, spending, retirement, topics, heatmap, quiz/decks, menu visibility, thinking levels, notification settings, tutorials |
| 10 | `docs/JARVIS-API.md` | 108 numbered sections | Numbering holes at §66-69, §76 and §111 (reserved, never written), and §106 is literally titled "New section here" |
| 11 | `docs/BUILD-QUEUE-2026-09-30.md:134`, `HANDOFF-2026-09-30.md:40-41` | Desktop YouTube and cloud-grade screens "not built" | `tools/check_parity.py:354-361` lists all eight routes as ported |
| 12 | `docs/ARCHITECTURE.md:2267-2269` | §10 "last checked against the repository on 2026-09-24" | Two weeks and roughly a thousand commits out of date; it is the section a new session is told to trust |
| 13 | `CLAUDE.md:1897-1909` | `jarvis-android` endpoints "none... exist on the backend" | `server/jarvis_mobile_ws.py:487` serves that exact path - unwired and explicitly dead, so the claim holds in effect but not in wording |

### C4. Simplification (the same thing is built twice, or in three places)

| # | Problem | Evidence | Suggested change |
|---|---|---|---|
| 1 | **Two configuration files, one inherited** | `jarvis_framework.load_framework()` parses `jarvis-framework.toml` (979 lines, the one with the tiers); `jarvis_hud.py` reads `~/.openjarvis/config.toml` (10 KB) for both the "abilities" list (`collect_tools`, `jarvis_hud.py:1512-1549`, which feeds `build_graph()` at `:1756`) and the enabled-tool list for the model (`:5109`, `:5128`). That file holds **four** template tool names - `think`, `calculator`, `web_search`, `http_request` - of which two exist. Jarvis's real tools are 28 in `jarvis_agent.TOOLS` and 70 gate actions | Point both at Jarvis's own tool table, or delete the map |
| 2 | **Five secret/PII matchers that will drift** | `jarvis_sensitive.py`, `jarvis_mail_mask.py`, `jarvis_paste_guard.py`, `jarvis_secrets.py` + `jarvis_secret_rules.py`, and a Rust `scrub()` in `crash_notes.rs`. The API doc defends the split (`JARVIS-API.md:8946-8959`) | One shared pattern module with a per-consumer policy (classify / mask / withhold) |
| 3 | **The patch stack is a hand-ordered pile** | 100 of 121 patches edit `jarvis_hud.py`; `apply-patches.ps1` carries 843 comment lines and 68 "must come after / context is" notes inside a 965-line list | Generate the route table from a manifest instead of appending diffs to one file |
| 4 | **Duplicated front-end helpers** | `node(tag, className, text)` appears **17 times byte-identical**; `canAct()` 5 times; `problemWords()` 20 times; `say()` 25 times | One `settings-row.js` exporting them |
| 5 | **Three settings lists that disagree** | 39 registry sections, 34 desktop cards, 18 phone rows - and `BOOL_SETTINGS` declares only 10 switches while the desktop renders 34 | Generate all three from `jarvis_menus.py`'s 104 entries, which is already the single source |
| 6 | **Two voice cards, four+ face pickers, ten hotkeys (two unbound)** | Desktop Settings `#voice` (`settings.html:764`) and `#voices` (`:1201`); faces settable in Settings → Appearance, Settings → Animal options, the Faces window, the floating face and the widget | One voice card; one face picker |
| 7 | **Three Settings cards outside the menu registry** | `settings.notifications`, `settings.start-jarvis`, `settings.crash-notes` have no `menu-catalog.js` entry and are not in `NEVER_HIDE`, so they cannot be hidden or folded | Add them, and add a build check the other way round too |
| 8 | **A 387 KB monolith and two multi-thousand-line clients** | `jarvis_agent.py` 387 KB (2.5x the next-largest module); `JarvisRuntime.kt` 7,431 lines with **no** `ViewModel` anywhere; `MainActivity.kt` 3,526; `JarvisApi.kt` 3,162 with **56 hand-written request builders** - one missing `.authed()` silently drops `X-Jarvis-Client` | Split tool registration from turn execution; route every phone request through one factory and assert the header once |
| 9 | **Nine `SharedPreferences` stores, nine readers** | `jarvis_client`, `jarvis_appearance`, `jarvis_secure`, `jarvis_menus`, `jarvis_models_cache`, `jarvis_history_view`, `jarvis_captured_notifications`, `jarvis_phone_notifications`, `internal_launch` | Consolidate the readers |
| 10 | **The local test script covers a third of the front-end suites** | `tests/` has 143 suites; `package.json`'s `test:ui` names 56 | Make `npm test` iterate `tests/*.mjs` the way CI does |
| 11 | **Docs outweigh the code they describe** | `backend/README.md` 1.1 MB; `docs/JARVIS-API.md` 1.2 MB / 17,121 lines; `CLAUDE.md` 130 KB; 277 markdown files | Split the README per feature; generate the route index from the patch list |
| 12 | **Seven desktop commands that are registered nowhere** | `capture_screen`, `toggle_widget`, `show_quickbar`, `toggle_hud`, `is_quickbar_pinned`, `read_clipboard` and `quit_app` exist as `#[tauri::command]` bodies (`commands.rs:1516/3197/5256/5262/5282/5313/5569`) with no permission file and no caller. [verified] **This is deliberate, not a defect:** `lib.rs:792-800` names exactly eight unregistered commands and explains why - "registered IPC is reachable from every page - `quit_app` in particular let any script terminate the app - so unused surface is cost without benefit" - and one of the eight (`notify_user`) was later re-registered deliberately at `lib.rs:805` | The only open question is tidiness: keep the bodies with their note, or delete them. Do **not** describe this as dead code to fix |
| 13 | **Permission sets wider than the reason each window has** | `core:app:default` is granted to 10 windows, `core:path:default` / `core:window:default` / `core:webview:default` to 8 each, in a config whose own comment says a command should be reachable "only from the surface that has a reason to call it"; and `core:webview:allow-internal-toggle-devtools` is granted to **brain, faces, quickbar and widget** - inert only while [Cargo.toml:176-178](jarvis-desktop/src-tauri/Cargo.toml) leaves the `devtools` feature off | Replace the whole default sets with the named `core:` commands each page uses; drop the devtools grant from those four capability files and let the feature flag be the only switch |

### C5. Verification gaps (the project's own honesty rules make these the real debt)

1. **Seven patched files exist only on the owner's PC** (`jarvis_hud.py`,
   `jarvis_gate.py`, `jarvis_extract.py`, `jarvis_memory.py`,
   `jarvis_events.py`, `jarvis_models.py`, `jarvis_skills.py`); about twenty
   suites test against them and **19 are skipped by name in CI**
   (`backend/run_suites.py:6-13`, `:51`). [reported] The last full local run was
   "248 passed, 0 failed, 29 skipped" (`docs/HANDOFF-2026-10-04-audit-pass.md`
   §6) - which is 29 checks nobody has seen pass.
2. **Six generated artifacts are committed as source with no drift check at
   all.** `backend/jarvis_wakebank.py` (930 KB, 8,610 lines),
   `backend/jarvis_sky_places.py` (569 KB), `backend/jarvis_voicebank.py`
   (323 KB), `backend/jarvis_stopword.py` (289 KB),
   `backend/jarvis_secret_rules.py` (69 KB) and `docs/SOURCE-BUNDLE.md`
   (13.5 MB) each say in their own header that they are machine-written, and
   each has a generator in `tools/` - but only two of those generators even
   support `--check`, and **none is ever invoked**. [verified] A bad merge into
   a 930 KB data table would ship silently, and `jarvis_wakebank.py` has **no
   test anywhere** (grep across all 249 test files returns nothing; it is read
   by one importer, `jarvis_wakeword.py:794`). The honest guard is not
   regeneration - `gen_sky_places.py` needs a download, the trainers need Piper
   and Kokoro - but a **committed SHA-256 plus a test that recomputes it**.
3. **Two promises have no guard at all**: the phone's Keystore key plus
   fingerprint prompt for a risky approval (reachable only from Android
   instrumentation tests), and "a key goes only to the one service it
   authenticates against" as a general rule (proved for one adapter only).
   `docs/HANDOFF-2026-10-04-audit-pass.md:364-368`, `:494-496`. [reported]
4. **A Windows CI job exists that has never run on GitHub** (§2.3 of the same
   handoff), and `cargo test` still needs a Windows host.
5. **The phone ignores three event kinds** (`finding`, `voice` and `job` -
   `docs/JARVIS-API.md:1491-1495`), so Findings, Live/voice state and job
   progress can be stale on the phone while the PC shows them. [reported] At
   minimum, say so on screen.
6. **Nothing measures whether a merge broke a nearby area** - this is queue item
   10 ("a stale-area check after every big merge"), still unbuilt.

---

## Part D - Risk register (privacy, security, rules)

Condensed from the security pass. Severity is what it costs the owner.

| # | Risk | Severity | Evidence | What to do |
|---|---|---|---|---|
| 1 | **`ntfy.sh` is the default alert broker** for approval notifications | **High** | `backend/gate-push.patch:36` - `JARVIS_NTFY_SERVER` defaults to `https://ntfy.sh`; the patch's own comment: "ntfy.sh topics are unauthenticated by design: the topic name is the only secret, it travels in a URL, and anyone who guesses it subscribes" | The code is careful (unconditional redaction, keys-only body, and it refuses to push while the conversation is latched local). But a public broker receiving card titles is a rule-1 judgement: either self-host ntfy, or make the default "off until the owner sets a broker" |
| 2 | **The shared key still approves risky cards** | High | `docs/ARCHITECTURE.md:453-478` | Retire the shared key now that per-device keys and phone signed approvals exist |
| 3 | **A non-risky card can be approved by any program holding the token** | Medium-High | `jarvis_owner_check.py:662-666` - Windows Hello is required for *risky* cards only | Owner decision: leave as documented, or widen "risky" to anything touching mail, files or memory |
| 4 | **"Stealth on for everything" overstates what was built** | Medium | Only the headless Obscura engine has `--stealth` (`jarvis_obscura.py:149`, `:388`); the visible browser that drives all nine chatbot sites and support chats has none, and a test forbids spoofing code there. Already found internally: `docs/audit-reports-2026-09-29-30/11-audit-adc2842a.md:86` | Reword the record to "for everything Obscura runs", or actually add stealth to the visible windows (which reverses the surviving "it is a real browser" sentence) |
| 5 | **Telemetry leftovers in the state folder** | Medium | `~/.openjarvis/telemetry.db` (1 row + empty `mining_stats`), `anon_id`, `version-check.json`, `traces.db` - none has a writer in the current code [verified] | Delete or attic them (B2) |
| 6 | **Bot-question and identity detection are regex-only** | Medium | `jarvis_support.py:406-449` (`_BOT_Q`, `_IDENTITY`) | An unenumerated phrasing ("just so I know, is this a person?") can slip past a promise the owner made explicit. Add a second check or an "unsure" pause |
| 7 | **Nine chatbot adapters and the support widget hosts have never reached a real site** | Medium | Each adapter's header; `ARCHITECTURE.md:640` says the widget host list is "NOT VERIFIED"; `:643` the DeepSeek address is unverified | Try one site for real, then keep only what passes |
| 8 | **The phone's bank/SMS block is a package-name heuristic** | Medium | `NotificationAllowList.kt:27` says so itself | Keep it, but say in the UI that it is a guess, or switch to an explicit allow-list |
| 9 | **Phone notification access is Android's widest grant** | Low-Medium | `AndroidManifest.xml:305`, `jarvis_phone_notifications.py` is only an on/off switch | Already off by default, already redacts codes, already excludes SMS - no change needed beyond item 8 |
| 10 | **Licence credits are missing for two planned parts** | Low (until built) | `Prompt Guard` / `Built with Llama` are absent from `THIRD-PARTY-NOTICES.txt` (correct today - not built); `Qwen` appears nowhere though Qwen 3.5 9B / Qwen3-VL 8B are the planned camera models | Add "Built with Llama" the day Prompt Guard 2 lands; credit Qwen when the camera ships |
| 11 | **Two documented plain-text paths** | Low | `obscura.log` (`jarvis_obscura.py:86-87`) and the support-chat export | Keep documented; add a scrub pass over `obscura.log` on rotation |
| 12 | **Dependency pinning** | Low | `requirements.txt` has 25 real lines, 13 pinned; `requirements.lock` has ~86 `==` entries, not hash-pinned; `fastembed` downloads its models on first use | Hash-pin the lock; name the model download hosts in the notices |

**Two things the security pass could not verify**, kept here rather than
dropped: whether the running backend's approval-stamp check is wired in
production (the shipped module and its tests were read, not a live install), and
whether any real chatbot site has ever been driven from this PC (every document
says "built, not yet tried for real", and nothing contradicts them).

---

## Part E - Complexity and maintenance

### E1. The numbers that describe the load

| Measure | Value | Why it matters |
|---|---|---|
| Commits | **1,978**, and the first numbered version (0.2.0) is **26 September 2026** | Almost the whole product was written in about nine days. It was not grown, it was erupted - which is why so much of it is "built, not tried for real" |
| Python shipped by patch | 147 modules, 8.8 MB | Larger than many applications; maintained by one person |
| Tests | 249 files; the last full local run reported 248 passed / 29 skipped | The skip rate is the honest measure of what runs on one machine |
| Generated data committed as source | `jarvis_wakebank.py` 908 KB, `jarvis_sky_places.py` 556 KB, `jarvis_voicebank.py` 315 KB, `jarvis_stopword.py` 282 KB, `jarvis_secret_rules.py` 69 KB - about **2.1 MB of the 8.8 MB** | Data that should be a file, loaded lazily, with a `--check` mode. One of them has no test at all |
| Patch fragility | 121 patches; 100 touch `jarvis_hud.py`; 68 ordering assertions in the installer | A single misplaced hunk breaks the install; the ordering is semantic, not cosmetic. `backend/patch-history/` (126 files) exists precisely because this happened often |
| Docs | 277 markdown files, 593,000 lines, 19 MB; `SOURCE-BUNDLE.md` alone is 13.5 MB | More text than code, with no index that covers it |
| CI | 8 jobs; the Ubuntu backend job takes ~15 minutes, the frontend more than 28, the Windows job covers 209 suites | `cancel-in-progress` means the long jobs are cancelled by each new push: two of them "were never seen to fail or pass" during the 2026-10-04 pass (`HANDOFF-2026-10-04-audit-pass.md`, the CI trap note) |

### E2. What a new session costs

`CLAUDE.md` is 130 KB and is the first thing any new conversation reads; it is
now incomplete (C3 #1). `docs/ARCHITECTURE.md` is 276 KB and its §10 is two weeks
stale. `docs/JARVIS-API.md` is 1.2 MB. `backend/README.md` is 1.1 MB. Four
handoff documents overlap. **Reading the project into memory takes longer than
most of the features took to build** - and the drift in Part C is the direct
result: several of those documents now describe a PC that no longer exists.

**And it no longer even fits.** This review's own session opened with the
harness reporting: *"Workspace instruction budget 65536 bytes: truncated
CLAUDE.md from 130728 to 65142 bytes."* [verified - it is in this session's own
system context] Half of `CLAUDE.md` - including the entire tail, which holds
"Every new feature gets its own audit", "Tell the owner when something is
wrong", "Do not claim more than the evidence supports" and the PowerShell and
Rust instructions - **never reached the agent that is required to follow it**.
That is not a style problem. The rules that prevent this project's worst
documented failures are in the half that gets cut. Splitting it (rules in
`CLAUDE.md`, the dated decision log in `docs/DECISIONS.md`) is now a
correctness fix, not tidiness.

### E3. The one structural change worth making

Every problem in Part E has the same shape: **one file that everything appends
to.** `jarvis_hud.py` takes 100 patches; `jarvis_agent.py` is 387 KB;
`brain.js` is 484 KB; `JarvisRuntime.kt` is 7,431 lines with no view models;
`CLAUDE.md` is where 2,028 lines of decisions accumulate. The recommendation is
not a rewrite. It is one rule, applied where it is cheapest:

> **Anything appended to by more than half the changes gets generated or split
> before the next feature lands on it.**

Concretely, in order of value: the route table in `jarvis_hud.py` (generate from
a manifest), the decisions log (one file per month, with `CLAUDE.md` linking to
them), the docs index (generate from the files), and the settings lists (generate
from `jarvis_menus.py`).

---

## Part F - The owner's own side of it

### F1. What the owner faces today [verified]

- **Desktop Settings**: 34 cards, 33 jump links, 626 element ids, 25 checkboxes,
  21 segmented choice groups, 4 dropdowns, 15 text inputs, 69 buttons, three
  groups ("Everyday", "Rare", "What Jarvis does").
- **Phone Settings**: 18 rows. **Brain**: 8 rail tabs, 39 cards.
- **Menu**: 104 entries across both apps, three levels deep, 68 hideable, 64
  collapsible, six feature groups, 24 that can never be hidden.
- **"What asks first"**: 100 rows for 80 tier lines, with 70 hard limits, 51
  must-ask and exactly 7 things the owner may loosen - **on the PC only, each
  with a card and Windows Hello**.
- **Things the owner can say without the model**: 93 distinct intents inside a
  4,679-line module, with a 344-line main matcher.
- **Hotkeys**: 10 (two ship unbound). **Tray**: 22 items. **Windows**: 10.
- **Setup**: `docs/INSTALL.md` is 1,263 lines and 60 numbered steps; the "Quick
  start" is 10 steps and is genuinely the shortest path - but step 3 is "have
  your backend folder ready (there is no download for it)". The project's own
  audit scored first-time setup 2/10 and customising 5/10
  (`docs/EASE-OF-USE-AUDIT-2026-09-27.md:25-26`), and recovery 4/10.
- **Settings are spread over about 11 places** (same audit, line 26).
- **Nothing tells the owner what is switched on.** Only one tool is enabled by
  default; the rest need a hand-edited 1,616-line TOML file.

### F2. What follows from that

1. **The problem is not too many features - it is that no screen answers "what
   does my Jarvis do, and what did it do?"** A single "What's on" page (the 28
   model tools and 70 gate actions, each with its switch, its card cost and a
   one-line "you last used this on...") would do more for daily use than any new
   feature in Part A.
2. **The card load is probably low, and that is a finding, not a relief.** On this
   PC the model is offered two tools (`calculator`, `web_search` out of 28 - see
   C2 #3), so the 57 asking actions are mostly unreachable. The approval design -
   this project's single biggest advantage over every competitor
   (`docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md` §2) - is therefore barely
   exercised, and its real card load is unknown.
3. **Discoverability beats capability.** With 104 menu entries, 93 phrases, 34
   cards and 10 hotkeys, the owner's real problem is finding the thing that
   exists. A command palette ("/" over Jarvis's own actions) and a search box
   over settings would both pay for themselves.
4. **Consolidation candidates for the owner's own eyes**, in the order they would
   reduce daily friction:
   - merge the two voice cards and make the Faces window the only face picker;
   - move the 13 `fixed:` explanation rows on "What asks first" into one line
     ("your own taps and words on this PC never raise a card"), which shortens
     that page by about 40%;
   - drop the ten or so single-use phrases from `jarvis_quick.py`
     (`identity_help`, `sayable_help`, `lists_which`, `where_put`,
     `lockdown_status`, `widget_make`...), keeping the ones with real value;
   - give the tray menu and the 10-hotkey table a "just the essentials" pass -
     the 2026-09-26 UI audit already asked for this.

---

## Part G - What I would do next, in order

The single most important recommendation of this review: **stop adding features
for one fortnight and make what exists true, measured and visible.** Everything
below is ordered so that each step makes the next one cheaper.

**Step 1 - Tell the truth about the hardware (an afternoon).**
The second card is in. Update `CLAUDE.md`, `docs/ARCHITECTURE.md` §10,
`docs/SECOND-CARD.md` and `docs/MODEL-TOPOLOGY.md` to say so; then run the
measurement lines those documents already contain and write the numbers into
`docs/SECOND-CARD.md`. This unblocks around a dozen built-but-off features and
is the only step that makes the rest of the review a different conversation.

**Step 2 - Housekeeping (an afternoon, no risk).**
Everything in B1 and B2. It removes about 2.1 GB from the working copy
(`target/` 2.0 GB, `dshwork/` 88 MB, `__pycache__` 10 MB), 13.5 MB from `docs/`,
a telemetry package from a no-egress project, and an accidental nested copy of
the repo. **Start with B1 #12** - appending five patterns to `.gitignore` is one
line of work and it is the only thing standing between 88 MB of agent scratch
and the repository on any machine but this one.

**Step 3 - Fix what is broken or lying (one to two days).**
C1 items 1-6 and the thirteen documentation rows in C3. Most are one-line fixes;
the cloud lane is the only one needing a decision, and the decision is small
because `jarvis_chatbot_api.py` already does the hard part.

**Step 4 - Make use visible (two to three days).**
The usage counter (feature → times used, no content) plus the past-approvals
list both apps already receive and drop. Then every "should we remove X?"
question in this report - and every future one - has an answer.

**Step 5 - Land what is on disk (one day).**
The tutorials/FAQ branch, with its own feature audit, and the pull request the
owner asks for. Nothing new starts on top of it.

**Step 6 - Then, and only then, build (pick at most two).**
My ranking: (a) the Prompt Guard 2 bake-off, because it is the last unbuilt safety
item and it is small; (b) whatever the second card's measurements justify -
longer conversations, pictures, or the camera in Jarvis Live. Both are already
designed.

**Step 7 - Simplify the load-bearing files (ongoing, one at a time).**
E3's rule, applied in the order given there.

**A standing rule I would add to `CLAUDE.md`, because it would have caught most
of Part C:** every new feature must state, in the pull request that adds it,
(a) which existing feature it makes redundant or replaces, (b) how it will be
shown to be *used* rather than merely working, and (c) the measurement that
would justify deleting it. Three lines per feature, and none of the "built,
offered, cannot work" items in C1 would have survived it.

---

## Part H - Decisions this review needs from the owner

Kept short and multiple-choice, as the project's own rules ask. In the order
they block work.

1. **The second graphics card is in. What now?**
   - **Measure it first, then switch on what the numbers justify** (recommended)
   - Switch on the features first and measure afterwards
   - Leave the second-card features off for now
2. **Cloud escalation ("Try the cloud model") is half-built and cannot work.**
   - **Point it at the chatbot API adapter and delete the LiteLLM path** (recommended)
   - Delete the cloud offer, the LiteLLM dot and the proxy plumbing
   - Leave it as it is
3. **The prompt-injection detector bake-off** (decided 2026-09-28, never built) -
   the last unbuilt safety item.
   - **Build it now, ahead of the other leftovers** (recommended)
   - Keep it where it is, after the current queue
   - Drop it
4. **The old shared pairing key can still approve risky cards.**
   - **Retire it now that per-device keys exist** (recommended)
   - Keep it for compatibility
5. **Approval notifications go to `ntfy.sh`, a public broker, by default.**
   - **Self-host the broker, or make the default "off until I set one"** (recommended)
   - Keep the public default
6. **`jarvis-android` keeps a signing secret and a token in plain text.**
   - **Delete it; git history keeps it** (recommended)
   - Move it to `legacy/`, fix the two rule problems, keep a compile check
   - Keep it exactly as it is

---

## Appendix - how this review was done

Eight read-only passes over the repository, plus direct checks on the owner's PC.
Nothing was built, removed or edited. Each pass returned findings with file paths
and line numbers; the ones that could be re-checked were, and anything that could
not be is marked **unverified** rather than stated as fact.

| Pass | Scope | Result |
|---|---|---|
| External research | GitHub projects, standards and 2025-2026 capabilities, checked against what Jarvis already has | Part A2 (10 tier-1, 10 tier-2, 15 refused) |
| Backend inventory | `backend/*.patch`, `backend/jarvis_*.py`, `backend/test_*.py`, JARVIS-API headings | Part 1, Part E1 |
| Desktop | `jarvis-desktop/` - windows, 339 commands, permissions, dead code, UX | Part C1 #3, C4, C5 |
| Android | `jarvis-client/` and `jarvis-android/` | Part C1 #4, C3 #6, C4 #9 |
| Decision conformance | `CLAUDE.md`'s decision log against the tree | Part A1, C3 #1 |
| Privacy/security/rules | The five rules, egress, secrets, approvals, licences | Part D |
| Repo and code hygiene | Committed artefacts, duplication, generated data, docs | Part B, Part E |
| User-facing sprawl | Settings, menu, cards, phrases, onboarding | Part F |
| Verification | The headline claims re-checked independently | Marked [verified] throughout |

Direct checks made on this PC during the review: `nvidia-smi` (two cards),
listening ports, whether Jarvis and Ollama are running, the Ollama model store,
the live backend folder, `~/.openjarvis` (config, approvals, logs, leftover
files), and `Test-Path` on the two files that gate the plan card and the pinned
digests.

**Known limits of this review.** It could not confirm what the owner actually
uses, because nothing records it (Part 0, finding 2); it did not run the test
suites or any feature end to end; it did not check the feasibility audit's 31
small items one by one; and every performance or memory number is either from a
document or from the hardware inventory, never from a measurement run.
