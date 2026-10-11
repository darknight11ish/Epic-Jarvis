# Jarvis vs OpenMuse (2026-10-08)

> The owner asked for a full, thorough comparison of Jarvis and
> [CopilotKit/openmuse](https://github.com/CopilotKit/openmuse): what Jarvis
> does better, what OpenMuse does better, what Jarvis is missing, and how to
> copy parts of OpenMuse into Jarvis to improve it.
>
> This supersedes nothing. It sits beside
> [COMPETITORS-2026-10-05.md](COMPETITORS-2026-10-05.md) (Muse, Dots and the
> rest), [COMPETITORS-MUSE-2026-09-25.md](COMPETITORS-MUSE-2026-09-25.md),
> [COMPETITORS-COMMERCIAL-2026-09-25.md](COMPETITORS-COMMERCIAL-2026-09-25.md),
> [COMPETITORS-OPEN-SOURCE-2026-09-25.md](COMPETITORS-OPEN-SOURCE-2026-09-25.md)
> and [PEERS.md](PEERS.md). **OpenMuse appears in none of them** - a search
> for `openmuse` over the whole repository returns nothing, so nothing here
> duplicates an earlier report.

## How far to trust this

- **OpenMuse's claims are read from its own files on GitHub**, not from a
  summary of them. The OpenMuse side was read on 2026-10-08 from `main`: the
  whole git tree; `README.md`, `ROADMAP.md`, `SECURITY.md`, `CONTRIBUTING.md`,
  `.env.example`, `LICENSE`; `docs/{FEATURES,VERIFICATION,COMPUTER,
  RICH-THREADS,OPENBOT-INTEGRATION,TELEMETRY,DEMO}.md`;
  `apps/worker/README.md`; and the source of
  `apps/server/src/{actions,db,auth,config,app,computer,computer-tools,files,
  search,google-auth,rate-limit}`,
  `apps/server/src/engine/{worker,model,conversation,routes,service,finance,
  page-diff,tanstack-agent}`, `apps/worker/src/network.ts`,
  `packages/domain/src/agent.ts`,
  `packages/integrations/src/{google,pdf,vault}.ts` and
  `packages/backends/src/openbot.ts`. **Every OpenMuse quotation below is
  verbatim from one of those**, with its path.
- **Jarvis's claims are checked against this repository.** Where the
  repository's own audits of 2026-10-04 to 2026-10-06 say a feature is dead,
  silent or unmeasured, this report says so instead of repeating the feature
  list's version.
- **Not measured:** no speed, cost, quality or win-rate figure here was
  measured. Nothing was run, built, installed or attacked. This is a reading
  of two codebases.
- **One thing said plainly up front, because it decides how the rest is
  read:** **OpenMuse is an alpha template** ("Alpha, for self-hosting and
  building on", `README.md`) whose own `docs/VERIFICATION.md` says no live
  Google account, no live CopilotKit Intelligence connection and no live model
  acceptance run has been done; and **Jarvis's own audit says about fourteen
  of its features silently do nothing** and that the live memory store on the
  owner's PC holds **0 facts**
  ([AUDIT-PASS-2026-10-05.md](AUDIT-PASS-2026-10-05.md),
  [SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md](SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md)).
  Neither project is what its feature list says. This is a pattern-by-pattern
  comparison, not marketing-by-marketing.
- **Still not read, and therefore not claimed:** OpenMuse's `apps/mobile`
  source, its test suite under `tests/`, `apps/computer`'s `files.py` and
  `Dockerfile`, and the `pdf.ts` internals beyond the size and page limits
  quoted below. For OpenMuse, one thing its own audit could not confirm: the
  literal `/api/agent` mount prefix in `app.ts`.

## How to read this

- **Section 1** is what OpenMuse is. **Section 2** is Jarvis in the same
  shape. **Section 3** is the one-page scorecard.
- **Section 4** is where Jarvis is ahead, **Section 5** where OpenMuse is
  ahead, **Section 6** what Jarvis is missing, ranked.
- **Section 7** is what to copy, with the exact OpenMuse file and a cost.
  **Section 8** is what never to copy, each with the rule it breaks or the
  incident that proves it.
- **Section 9** is where the two projects independently agree - the most
  useful part, because agreement from an unrelated codebase is evidence.
- **Section 11** is the decisions only the owner can make.
- Vocabulary, as in the earlier competitor reports: **A** = Jarvis ahead,
  **E** = even, **B** = Jarvis behind, **NfJ** = "not for Jarvis" - copying
  it breaks one of the [five rules](../README.md).

---

## 0. The short answer

**OpenMuse is the first rival read by this project that is ahead of Jarvis at
the thing Jarvis is worst at: finishing a job that takes a while.** It has a
durable task worker - a queue that survives a restart, leases so a crashed
worker's job is picked up again, checkpoints, retries, pause, resume, cancel,
and a plain record of what happened. Jarvis's own capability audit says of
Jarvis: *"No persistent queue, no retries, no self-verification, no
self-critique, no multi-agent work"*, and *"a single-turn, tool-using
assistant with a hard 7-request ceiling"*
([SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md](SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md):20).
That is the gap, and it is the reason four things the owner already asked for
cannot work.

**The design lesson is sharper than the feature list.** OpenMuse's chat agent
**has no tool that writes anything.** It can read mail, calendar, files and
pages, and it can do exactly one acting thing: `delegate_task`. Every write
happens inside the durable task engine, which gets **16 steps** (the chat
loop gets 6) and which survives a restart. Jarvis does the opposite: its chat
turn both talks and acts, inside a 6-round ceiling, in a process where
nothing is resumed. That single choice is the bottom half of Jarvis that is
missing.

**Jarvis is ahead on everything before and after the work.** OpenMuse
requires a **paid hosted service (CopilotKit Intelligence) in every mode**
just to keep a conversation (`config.ts` calls
`required("CPK_INTELLIGENCE_API_KEY", ...)`), sends telemetry to PostHog
**with full capture on by default**, and its default search hands the
model-generated query, the conversation's context and a session id to a third
party. Its model is a cloud model. Its one MCP client is hardcoded to that
same search service - **there is no user-configurable MCP registry**, which
Jarvis has. And its approval binding is a **content hash, not a signature**:
it proves *what* was reviewed, never *who* reviewed it. Jarvis proves both.

**The practical conclusion.** Copy five mechanisms from OpenMuse's back end -
the lease-and-checkpoint task worker, `outcome_unknown` for an interrupted
write, idempotency keys, hash-bound approval, and memoized tool results - and
refuse the rest, because the rest is what makes OpenMuse a hosted product.
All five are local, all five strengthen rules Jarvis already has, and the
whole set is roughly a few hundred lines of Python, three new SQLite tables
and five tests. **OpenMuse does not change Jarvis's plan; it supplies the
missing bottom half of it.**

**One correction, made later the same day (2026-10-08 16:00 PDT), because it
is the error this project keeps warning itself about.** This report first
listed a sixth borrow - OpenMuse's IP-pinned egress validation - with the
note that Jarvis's rule 2 was "enforced in Python by `jarvis_reach.py`" and
that OpenMuse's version was the hardening to copy. **That was wrong.**
Jarvis's [`jarvis_local_http.py`](../backend/jarvis_local_http.py) already
does the whole thing, and in one respect does more: `_connect_public`
resolves the name ONCE at connect time, refuses if **any** answer is private,
and then connects to the address it checked - never to the name - while
`https` still checks the certificate against the name. That is the same
mechanism OpenMuse's `validatePublicUrl()` uses, arrived at independently
after the 2026-09-27 security audit, and `test_local_http.py` already had a
rebinding control test for it. `PEERS.md` records this happening twice
before; it is now three times, and the file that would have caught it was two
directories away. **What the comparison did earn is small and real:**
OpenMuse's allowlist named ranges Jarvis's did not, and it named an
IPv4-embedding IPv6 form Jarvis did not unwrap. Both are now closed (see
Section 4, last two rows).

---

## 1. What OpenMuse actually is

### 1.1 The shape

A TypeScript monorepo (Node 24, pnpm), **MIT licensed**, built by CopilotKit.
`README.md`'s own table, corrected against the tree:

| Directory | What it is |
|---|---|
| `apps/mobile` | One Expo / React Native UI for **iOS, Android and web**, using CopilotKit's headless hooks |
| `apps/server` | Hono API + CopilotKit runtime + the task engine, agent loop, approvals, files, persistence |
| `apps/worker` | A separate Playwright Chromium service, `Authorization: Bearer <WORKER_TOKEN>` on every route but `/health` |
| `apps/computer` | A Dockerfile and a Python file helper for the optional nonroot Linux container |
| `packages/domain` | Shared types and **zod** request validation - the whole data model |
| `packages/integrations` | Google, PDF and credential-vault adapters |
| `packages/backends` | A disabled OpenBot HTTP adapter with an injected transport seam and 13 contract tests |
| `tests` | Workflow, runtime, persistence, provider-contract and authorization tests |

Processes: the API (which hosts the task worker in-process), an optional
separate task worker (needs real PostgreSQL - *"PGlite cannot be opened by
separate processes"*, `README.md`), and the browser worker. Storage is
**one schemaless table**: `records(owner, kind, id, data jsonb, updated_at)`
over embedded PGlite or PostgreSQL (`apps/server/src/db.ts`). Streaming is
**AG-UI**; the agent is a CopilotKit `BuiltInAgent` over `@tanstack/ai`
adapters for OpenAI, Anthropic and Google.

### 1.2 The mechanisms worth knowing about

These are the load-bearing files, read directly.

**`apps/server/src/db.ts` - a tiny store with real concurrency control.**
The interesting part is not the table, it is five operations on it:

- `compareAndSwap(owner, kind, id, expected, patch)` - `UPDATE ... WHERE data
  @> $expected ... RETURNING data`. A compare-and-set, used everywhere.
- `insertIfAbsent(...)` - `ON CONFLICT DO NOTHING RETURNING data`.
- `claim(...)` - **one SQL UPDATE** that moves an action from
  `awaiting_review` to `executing`, carrying the expiry check and, for a
  task-bound action, an `EXISTS` subquery requiring the task to still be
  `running` or `waiting_approval`. Two devices approving at once cannot both
  win.
- `recoverInterruptedActions()` - on startup, every action left in
  `executing` becomes `outcome_unknown`, with the words: *"Server restarted
  during execution. Check the provider before creating another action."*
- `setMilestoneDone(...)` - updates **one checkbox** with `jsonb_set` +
  `jsonb_agg`, so a concurrent rename or reorder is not clobbered.

**`apps/server/src/engine/worker.ts` - a durable task worker in about 200
lines.** Every second it scans tasks and picks up anything `queued`,
anything `scheduled` whose `nextRunAt` has passed, anything `running` whose
**lease has expired** (a crashed worker), and anything `waiting_approval`.
For each it:

- claims it with `compareAndSwap{status, leaseId}`, writing a fresh `leaseId`
  and `leaseUntil` (60 s) and incrementing `attempts`;
- heartbeats every `leaseMs / 3`, and **a failed heartbeat compare-and-set
  aborts the run** - the run fences itself off rather than writing over
  someone else's work;
- hands the handler a `checkpoint(patch)` (a CAS merge under
  `{leaseId, status:'running'}`, so a zombie's writes are discarded), a
  `guard()` that throws `LostLeaseError` if the lease or status changed, and
  `event(kind, title, detail)` writing to a `run-events` feed;
- caps itself at **3 tasks at once**, so long runs do not block the tick;
- classifies failure: `LostLeaseError` puts the task back to `queued` (someone
  else's turn); any other error marks it `failed` with the message kept;
- writes a `runs` row per attempt with `startedAt`, `finishedAt` and status -
  the receipts.

Manual control is real: `POST /api/agent/tasks/:id/control` with
`{action: pause | resume | cancel | retry}`, and `POST /tasks/:id/input` to
answer a `waiting_input` task.

**`apps/server/src/actions.ts` - the approval gate.** A single
`ActionService` with `propose` and `decide`:

- `propose` computes a **sha256 hash over the input, the connection, the
  target and the target's version**, sets `status: "awaiting_review"` and
  `expiresAt: now + 30 minutes`. Given an `idempotencyKey`, the row's **id is
  that key's sha256** and `insertIfAbsent` is used, so a retried request
  returns the first proposal instead of making a second.
- `decide(owner, id, hash, decision)` **requires the caller to send back the
  hash it displayed**. A mismatch is refused: *"This proposal changed. Open
  its latest review before deciding."* It also refuses if the task was
  cancelled (*"Resume the task before approving this action"*), if the
  proposal expired, if Google was disconnected, or if the **account or
  connection id changed** since it was prepared. Only then does `claim()` run.
- A failure that might have reached the provider becomes **`outcome_unknown`**,
  never `failed`. `MODEL_MAX_RETRIES = 2`, and *"a stream that fails after it
  starts is not retried. External writes never re-fire here"* (`config.ts`).
- Every transition writes an `activity` row - the receipt the owner reads.

**Integrity, not identity, and the report should say so.** The binding is a
content hash. There is **no signature and no WebAuthn**, so OpenMuse has no
cryptographic proof of *who* approved - only of *what*. Jarvis has the
opposite half (`owner-check.patch`: a row saying "approved" counts only if
this running process stamped it, and risky approvals need Windows Hello).
**The two halves are complementary, which is exactly why this is the best
thing in the report to copy.**

**`packages/domain/src/agent.ts` - the whole data model in one file.**
`AgentTask` (with `plan: TaskStep[]`, `evidence: Evidence[]`, `input`,
`state`, `attempts`, `leaseId`, `leaseUntil`, `actionId`, `artifactIds`, and
a `question` for `waiting_input`), `RunEvent`, `Goal`, `Monitor`, `Idea`,
`AgentMemory`, `AgentArtifact`, `AgentNotification`, `AgentIdentity`. Task
statuses: `queued`, `running`, `waiting_approval`, `waiting_input`,
`scheduled`, `paused`, `succeeded`, `failed`, `cancelled`. A `Monitor` is a
typed watch: `condition: "change" | "contains" | "price_below"`, a `value`,
an `intervalMinutes` (1 to 10,080), `lastHash`, `checks`, `error`.

**What the agent can actually do** - a complete list from the source, because
the split matters:

- **Chat** (`engine/conversation.ts`): `read_calendar`, `search_mail`,
  `read_mail_thread`, `search_web`, `browse_web`, `delegate_task`,
  `agent_status`, `create_goal`, `watch_page`, `remember_fact`,
  `present_choices`, plus the computer tools. **There is no chat tool that
  sends an email or writes a calendar event.**
- **Task worker** (`engine/model.ts`): `set_plan`, `read_workspace`,
  `read_mail_thread`, `import_pdf`, `inspect_pdf`, `fill_pdf`, `search_web`,
  `read_web`, `save_artifact`, `prepare_email`, `prepare_event`, `ask_user`,
  `finish_task`, plus the computer tools.
- **Computer**: `computer_status`, `start_computer`, `stop_computer`,
  `run_computer_command`, `list_computer_files`, `read_computer_file`,
  `write_computer_file`, `mkdir_computer`, `import_computer_pdf`,
  `export_computer_pdf`.

**The hard limits are stated in code**, which is worth noting because Jarvis
is trying to do the same thing in its own docs: `set_plan` 1-12 steps;
`finish_task` summary ≤ 8,000 chars; `search_web` objective ≤ 2,000, 1-5
queries, **45-second deadline**; `browse_web` ≤ 30,000 chars of text;
`search_mail` ≤ 20 matches with 240-char snippets; `read_mail_thread` ≤ 20
messages at 12,000 chars each; `read_calendar` ≤ 366 days and ≤ 20 events;
`watch_page` interval 1-10,080 minutes; Gmail MIME depth ≤ 30 and text ≤ 1
MiB; **PDF ≤ 10 MiB, 1-500 pages, AcroForms only, no OCR**; **finance CSV
≤ 500 KB, 1-5,000 rows, requires date/description/amount/category, exact
cents**; terminal **30-second timeout**, 128 KB output cap, `/workspace`
only, symlink rejection, a required namespaced `operationId` for at-most-once;
API rate limit 120 requests per 60 seconds per socket.

### 1.3 What it costs to run

- `CPK_INTELLIGENCE_API_KEY` is **required in every mode**, and
  *"Intelligence is a separate service and is not included in this
  repository's MIT license"* (`README.md`). Thread persistence and replay do
  not work without it, and `/api/conversation` is only local sample history
  (`docs/RICH-THREADS.md`). **Conversations are remote.**
- A model key (OpenAI, Anthropic or Google) - `openai/gpt-5` by default. Or
  `AGENT_BACKEND=sample`, a **scripted agent needing no model at all**, or
  `AGENT_BACKEND=agui`, an external AG-UI endpoint.
- `OPENMUSE_ACCESS_KEY` - **one shared key for one owner.** `SECURITY.md`:
  *"OpenMuse currently supports one owner per deployment. Live mode uses a
  shared access key; it is not multi-tenant account authentication."*
  `auth.ts` hardcodes `owner: "local-user"`.
- `TOKEN_ENCRYPTION_KEY` - 32 random bytes, base64. Google tokens are
  **AES-256-GCM in a versioned envelope** (`v1.nonce.tag.ciphertext`) with
  AAD `openmuse:credential:v1`, and a strict base64 round-trip check so
  malformed ciphertext fails closed (`packages/integrations/src/vault.ts`).
- Telemetry: **on by default.** `config.ts` sets
  `COPILOTKIT_TELEMETRY_SAMPLE_RATE ??= "1"` and events go to
  telemetry.copilotkit.ai into PostHog, tagged `OpenMuse`. Opt out with
  `COPILOTKIT_TELEMETRY_DISABLED=true` or `DO_NOT_TRACK=1`.
- Deployment is a Render blueprint (three services, one 1 GB disk) or
  `docker compose`. Standard plan is the smallest that stays up, because
  PGlite needs the memory.
- Search is on by default through Parallel's free keyless Search MCP; the
  README says it *"sends model-generated queries and context, which may
  include information from your conversation or task, plus a random
  per-chat/task session identifier to Parallel."*

### 1.4 The limits its own docs admit

- `docs/VERIFICATION.md`: no live Google credentials were supplied; the
  Intelligence boundary is mocked in tests; live model quality is pending.
- `docs/FEATURES.md`: *"Live providers and optional infrastructure require
  separate configuration and validation."* The Gmail/Calendar row says
  **"Live credentials required."**
- `ROADMAP.md`'s "Integration acceptance next" is entirely unchecked: live
  Google acceptance, Intelligence persistence and replay, live model
  acceptance, Android emulator smoke tests, the OpenBot bridge.
- Demo is scripted: *"The model responses use CopilotKit AI Mock ... it is not
  an evaluation of a live model's reasoning"* (`docs/DEMO.md`).
- Voice, device push, image generation, health/bank/social connectors,
  reservations and payments: **roadmap only**.
- The Linux computer is **disabled until configured**, has `network none`, and
  is *"not a graphical desktop or a full OS VM"*. The E2B desktop path is
  materially weaker and `SECURITY.md` says so itself (see Section 8).
- The browser worker is optional; without it, page reads, screenshots and
  "Take control" do not work.

---

## 2. What Jarvis is, in the same shape

Read from this repository. Numbers first, because they are the thing OpenMuse
makes look small.

| | |
|---|---|
| **Stack** | Python backend on the owner's Windows PC (**outside this repository** - patches only), Tauri 2 desktop (99 `.rs`, 127 `.js`, 149 browser-test suites, 10 window capability files), Android Jetpack Compose client (488 Kotlin files: 311 in the app's main source set, 171 unit-test files, 6 instrumented tests) |
| **Model** | Ollama, local, on the owner's own GPU. `jarvis-primary` is Qwen 3 8B; a 12 GB second card is **installed and its hardware measured**, but its seven feature switches are **all off and unmeasured** |
| **Storage** | SQLite (`memory.db`, `schedule.db`, approvals, encrypted chat history) under `~/.openjarvis`, plus the Obsidian vault for notes |
| **Reach** | Tailscale or NordVPN Meshnet only. Never a public tunnel. A non-loopback bind with no token refuses to start |
| **Gate** | One permission model; every acting tool is `plan` / `describe` / gate / `run`; one card per action; no approve-all |
| **Size** | `backend/` holds **124 `.patch` files in the folder itself (257 including every subfolder), 151 shipped `jarvis_*.py` modules (8.6 MB) and 260 test suites**; `plugins/README.md` describes **18 drop-in modules and 104 core patches**. Its own review counts 147 modules and **121 patches that edit `jarvis_hud.py` about 100 times** ([FEATURE-REVIEW-2026-10-04.md](FEATURE-REVIEW-2026-10-04.md):145)<br>`docs/JARVIS-API.md` is **17,427 lines: 112 sections, 449 subsections, over 250 distinct `/api` paths**; `docs/` holds 296 markdown files out of 332 files in total, counting this report |
| **Agentic state today** | **29 tools built, 3 offered to the model** - `calculator`, `web_search`, `memory_search` - because the enabled list comes from an inherited template file with 27 names, 24 of which do not exist. A **7-request ceiling** (6 rounds). The plan card is **dead (a path bug)**; the initiative engine is **a provably empty shell**; Projects writing/running code is **not built**. `jarvis_plan.py` is 492 lines and unreachable |
| **Learning today** | On the owner's PC the live memory store holds **0 facts, 0 proposals, 0 pinned facts, 0 people, 0 "said again" counts** |
| **Its own honesty count** | `docs/JARVIS-API.md` says "not built" 30 times, "off by default" 15 times, "unmeasured / unverified" 27 times, and flags 21 switches OFF. Repeated line: *"Nothing has reached a real mail server / provider / Home Assistant"*; *"every test uses a stand-in."* `docs/README.md` calls Live "design only" while `docs/LIVE-DESIGN.md` says built - an unresolved contradiction |
| **Install** | **The backend is not public.** "there is no such file to publish, so a second person cannot install Jarvis today" ([README.md](../README.md)). The desktop updater is switched off (`pubkey = ""`), so no update is published; ~20 test suites are skipped in CI because seven patched files exist only on the owner's PC |

Those last rows are why this comparison is not a victory lap. Jarvis's feature
list is far longer than OpenMuse's; **Jarvis's working feature list on the
owner's PC is not.**

---

## 3. The scorecard

**A** = Jarvis ahead. **E** = even. **B** = Jarvis behind. **NfJ** = copying
OpenMuse's version breaks one of the five rules.

| Area | Jarvis | OpenMuse | Verdict |
|---|---|---|---|
| Where the private data lives | PC only; chat history encrypted | `.openmuse/` locally, but **threads need the hosted Intelligence service** | **A** |
| Model | Local Ollama on own GPU; cloud lanes opt-in per question | Cloud (OpenAI/Anthropic/Google), or a scripted sample with no model | **A** |
| Does it work offline | Yes, fully | No - model, threads and search are all remote | **A** |
| Voice end to end | Wake word, voice-print gate, STT/TTS, Live, barge-in, lip sync | **Roadmap only** | **A** |
| Screen understanding | "Look at this", "Watch with me", secret blackout | Screenshots of the agent's own browser only | **A** |
| Memory | Reviewed, two dates per fact, Forget, Erase-the-words, Forget-a-time-frame, bi-temporal | "Editable/forgettable memories" (`{id, text, source, createdAt}`) | **A** |
| Approval: depth of states | `auto`/`notify`/`approved`/`denied`/`timed_out`/`refused`; a denial is not a timeout; the verdict **defaults to `refused`**; protected files; rush latch | `awaiting_review` → approved/denied/expired, plus `outcome_unknown` | **A** |
| Approval: proof of **who** approved | Windows Hello + a per-process stamp; risky approvals need a real presence check | **None** - a content hash cannot prove identity | **A** |
| Approval: proof of **what** was approved | Not present | **sha256 hash echoed back at decide time** | **B** - copy it |
| Approval: bound to the account/key it was prepared under | Not present (no changeable connectors yet) | Yes - `connectionId` + `account` must still match | **B** - copy it |
| Duplicate-write protection | Approval side only (`decide-once.patch`, a `state='accepting'` CAS) | **Idempotency key → deterministic id**, `insertIfAbsent`, and a required `operationId` on terminal commands | **B** - copy it |
| An interrupted outbound write | No equivalent state | **`outcome_unknown`** + `recoverInterruptedActions()` on startup | **B** - copy it |
| A retried step repeating a side effect | No protection | **`cached()`**: sha256(name+args) memoisation of tool results into task state | **B** - copy it |
| Long-running work | No persistent queue; no retries; a **6-round** chat ceiling | **Durable worker, leases, checkpoints, retries, resume**, and a **16-step** task loop | **B** - the big one |
| Where work happens | The chat turn talks and acts | **The chat turn cannot write; it delegates to a durable task** | **B** - the design lesson |
| Progress the owner can watch | Brain → "Now" shows steps; past approvals are sent by `/api/ledger` and **both apps ignore them** | **Activity + `run-events` + `runs` receipts + `waiting_input`** | **B** |
| Asking for a missing value mid-job | `waiting_input` has no task to hang on | **`waiting_input` + `question`, a real state** | **B** |
| Secrets at rest | Windows Credential Manager; encrypted history | **Versioned AES-256-GCM envelope with AAD**, failing closed | **E** |
| Egress filtering (rule 2) | `jarvis_local_http.py`: one DNS lookup at connect time, **every** answer checked, then a connection to the checked address itself, never the name (https still checks the certificate against the name); no proxy, ever. Since 2026-10-08 it also refuses the ranges that are not a destination at all, and unwraps NAT64 | Public-IP allowlist, ports 80/443 only, rejects `localhost`/`.local`/`.internal`, 5 s DNS timeout, then the resolved IP is pinned through a loopback proxy | **A** - Jarvis already had it, and checks *every* answer where OpenMuse checks the resolved one; its allowlist taught two small gaps, now closed |
| Running commands on the machine | `shell_exec` with the owner's full permissions, one card per exact command | Nonroot, read-only rootfs, all caps dropped, **no network**, 512 MB / 1 CPU, 30 s limit, saved receipts | **A** on honesty, **B** on isolation |
| Browser: read a page | Visible Playwright + headless Obscura, per-step cards | Playwright worker, page reads, screenshots | **E** |
| Browser: take the session over | Visible window on the owner's PC; "Solve it here" hand-off to the phone | **Live console takeover** of the same session via a 15-minute HMAC-signed URL | **E** (different shapes, both real) |
| PDF form filling, end to end | Designed + `form-review.patch`; **untried** | Import → typed input request → filled copy → reviewed reply → receipt (AcroForms, no OCR) | **E** |
| Money features | Spending summaries, retirement what-if, progress charts | CSV import → categorised summary + savings-goal action (no bank link) | **E** |
| Goals | Goals with per-step cards; **never calls the model** | Goals + milestones as typed records tied to tasks | **E** |
| Watches ("tell me when") | Email, devices, web pages; one scheduler; a missed-while-off rule | `Monitor` with **typed conditions**, `lastHash` dedup, relative-time normalisation, failure back-off | **E** (copy the typed conditions and the normalisation) |
| Suggestions / ideas | Tag, skill and referee suggestions with a back-off rule | Ideas **with source evidence**; sent replies and completed matching work excluded | **E** |
| Chat history and threads | Encrypted, kinds, Continue, Forget-a-time-frame; **rename/pin/archive/branching are "proposals only"** | Rich Threads: side chats, rename, archive, restore, replay - **and remote** | **E** (the idea is B, the implementation is NfJ) |
| Extensibility | Local-only MCP bridge (`jarvis_mcp.py`, 92 KB), drop-in plugin folders, per-server card | **One hardcoded MCP client** (Parallel search). No user-configurable MCP registry; tools are added in source | **A** |
| Personality and clients | 23 face designs, animals among them, plus a robot; one shared visual spec across both clients | `AgentIdentity {name, tone, avatar}` with three avatar choices; no i18n found | **A** |
| "What is switched on" | A 1,616-line TOML to hand-edit; the model is offered 3 of 29 tools | Searchable capability/status catalogue | **B** |
| Phone and desktop | Two codebases (Tauri + Kotlin), both real and specific | One React Native codebase for iOS + Android + web | **E** (reach/polish) |
| Installability | Backend not published; the updater is off | `pnpm install`, one blueprint, `docker compose`, one `.env.example`, `/api/health` | **B** |
| Telemetry | None | PostgreSQL-backed PostHog, **full capture by default** | **NfJ** |
| Search default | Five providers, SearXNG local default | Parallel's free keyless MCP, sending query + context + session id | **NfJ** |
| Thread storage | Encrypted SQLite on the PC | CopilotKit Intelligence (hosted, not MIT) | **NfJ** |
| Hosting | One PC, own networks only | Binds `0.0.0.0`, one shared access key, owner hardcoded to `local-user` | **NfJ** |
| The E2B desktop path | Not applicable - no cloud desktop | Internet on, passwordless sudo, every port public | **NfJ** |

**Score: A on 12 rows, B on 12, E on 10 and NfJ on 5** (one row, running
commands on the machine, is A on honesty and B on isolation). Much closer than the
earlier competitor reports, and the reason is simple: **OpenMuse is the first
rival read here whose authors also treat approvals, receipts and recovery as
the product** - and the first whose chat agent is deliberately unable to
write.

---

## 4. Where Jarvis is genuinely ahead

Not asserted - each row is a place where OpenMuse's own documentation puts
the capability on its roadmap, needs a hosted service, or is absent from the
source.

1. **Nothing private leaves the PC, at all.** OpenMuse cannot keep a
   conversation without a hosted project key. Jarvis's four private
   categories - email, files, credentials, memory - are handled only by the
   local model. This is a category difference, not a feature difference.
2. **It works with the internet off.** OpenMuse's model, thread store and
   default search are all remote, and its roadmap still lists live model
   acceptance as to be done.
3. **Voice is finished, and voice is where the safety is.** Jarvis checks the
   owner's voice print *before* any words exist, keeps speech-to-text on the
   PC, and forbids a client from doing it. OpenMuse has no voice.
4. **The approval model is deeper.** Jarvis distinguishes *"a person said
   no"* from *"nobody was there"* (`backend/gate-outcome.patch`); a denial can
   propose a standing rule; an unreadable policy refuses; unknown outcomes
   are coerced to `refused`; and `Verdict.outcome` **defaults to `refused`**,
   so a forgotten field at a new call site fails closed. It also has a
   `notify` tier, a protected-file rule that no tool may touch, and a rush
   latch that raises the tier of whatever follows a suspicious instruction.
   OpenMuse has fewer states and no equivalent of any of those.
5. **Real proof of human presence on a risky approval.** Windows Hello plus a
   per-process stamp, the phone's Keystore half, App lock. OpenMuse binds a
   decision to a content hash and nothing else, and its own docs confirm
   there is no signature or WebAuthn anywhere.
6. **Memory is a system, not a list.** Two dates per fact (valid time and
   transaction time, so "what did you believe then?" is answerable),
   retirement instead of deletion, "Erase the words", Forget-a-time-frame
   with a 10-minute Undo, a review queue, and sensitive topics gated
   separately. OpenMuse's memory is three fields.
7. **Extensibility is real.** `jarvis_mcp.py` runs local MCP servers, behind
   a card, per server, read-only first. OpenMuse hardcodes exactly one MCP
   client - its own search provider - and adds tools by editing source.
8. **The breadth of local tools** - IMAP read/draft/send/tidy, Obsidian,
   Logseq, Joplin, Home Assistant, five search providers with a local default,
   PDF/Word/Excel/PowerPoint/Notion, calendars over a private iCal link,
   music and video control, quizzes, review decks, tutorials, custom voices,
   five faces plus animals. OpenMuse's connector list is Google plus a
   browser.
9. **Personality and two real clients** - 23 face designs, themes, a widget, a
   floating face, a Quick Settings tile, the Android assistant role, a
   smartwatch setting. OpenMuse offers three avatar colours and has no i18n.
10. **The five rules are enforced by construction**, not by policy: a
    non-loopback bind with no token refuses to start; "What Jarvis can reach"
    lists every way out; that list is written from settings, never by the
    model; approval wording is generated centrally rather than composed by a
    client.
11. **Non-commercial and sideloaded by conviction.** No signup, no seat
    price, no terms of service. OpenMuse's own README points at a "Talk to an
    engineer" link.
12. **Egress filtering that defeats DNS rebinding - and checks every answer.**
    [`jarvis_local_http.py`](../backend/jarvis_local_http.py)'s
    `_connect_public` resolves the name once at connect time, refuses if
    **any** answer is private, and then connects to the address it checked
    rather than to the name, so a second DNS answer cannot be won by an
    attacker; `https` still checks the certificate against the name, so
    pinning costs no TLS safety, and no proxy is ever used. OpenMuse's
    [`apps/worker/src/network.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/worker/src/network.ts)
    does the same thing - which is why this report first mistook it for a
    gap. **This comparison did earn two small closings, both done
    2026-10-08:** ranges a real allowlist names and Jarvis's did not (`192.0.0.0/24`,
    the three TEST-NET blocks, `198.18.0.0/15`, multicast `224.0.0.0/4`,
    reserved `240.0.0.0/4`, IPv6 `ff00::/8` and `2001:db8::/32`) and
    **NAT64**, where `127.0.0.1` is spelled `64:ff9b::7f00:1` and
    `ipaddress` reports no `.ipv4_mapped` for it. `backend/test_local_http.py`
    gained 16 checks for both, including that a NAT64 address carrying a
    genuinely public IPv4 is still allowed.

---

## 5. Where OpenMuse is genuinely ahead

Each of these is a place where Jarvis's own audits already admit the gap.

1. **Durable, resumable work with retries.** The single biggest one. See
   `apps/server/src/engine/worker.ts`.
2. **Leases and recovery.** A task orphaned by a crash is reclaimed when its
   lease expires, and a run that has lost its lease fences itself off rather
   than writing over the new owner's work. Jarvis has no queue to lose, so it
   has nothing to recover - and cannot do a job that outlives one turn.
3. **Checkpoints and receipts.** Every attempt writes a `runs` row; every
   transition writes an `activity` row. The owner can see what happened
   afterwards. Jarvis's own review lists exactly this as missing (A3 #1:
   *"A way to see what Jarvis did and what it is doing"*), and both of its
   apps already receive past approvals from `/api/ledger` and ignore them.
4. **`waiting_input` as a real state.** A job stops, asks for one missing
   value, and continues. That is the state a form-filling or setup job needs,
   and it is the difference between "ask, don't guess" as a prompt line and
   as a guarantee.
5. **Five small protection mechanisms Jarvis lacks:** the hash-bound review,
   the idempotency key, the connection/account binding, `outcome_unknown`
   with startup recovery, and memoised tool results so a retried step cannot
   repeat a side effect.
6. **Optimistic concurrency on an external object.** `targetVersion` means an
   edit is applied only to the version that was reviewed.
7. **A typed watch model** with `lastHash` dedup and *relative-time
   normalisation* - `withoutRelativeTimes()` rewrites "3 hours ago" before
   hashing, so a clock ticking on the page does not fire a false "it
   changed".
8. **Evidence as a first-class object** on tasks and ideas, with `kind`,
   `title`, `excerpt` and `url`, plus a rule worth stealing: a suggestion
   whose matching work is already done is not shown.
9. **Artifacts as first-class results** (`plan`, `comparison`, `finance`,
   `report`) that a thread links back to, instead of text in a chat.
10. **A capability/status catalogue**, so what is connected and what is not
    is in one searchable place.
11. ~~**Egress filtering that defeats DNS rebinding.**~~ **Withdrawn
    2026-10-08 - this was wrong, and it was the third time this project has
    "found" something it already had.** Jarvis's
    [`jarvis_local_http.py`](../backend/jarvis_local_http.py) already pins the
    address it checks at connect time. It is now recorded in Section 4 as a
    place Jarvis is **ahead**, with the two small ranges OpenMuse's allowlist
    did teach this project (closed the same day).
12. **Install and deploy that a second human could survive:** one
    `pnpm install`, one `.env.example` listing every setting, one
    `/api/health`, one `docker compose`, one Render blueprint. Jarvis's own
    ease audit calls the missing installer the point where *"everyone but you
    stops"* ([EASE-OF-USE-AUDIT-2026-09-27.md](EASE-OF-USE-AUDIT-2026-09-27.md)).
13. **Truthful failure at the ceiling.** `reportStepLimit()` writes a plain
    message saying the *iteration cap*, not the model, ended the run. Jarvis's
    own invariant is "nothing is claimed that is not true"; this is that
    invariant applied to a loop limit, and Jarvis does not do it.
14. **One client codebase for three platforms.** Jarvis maintains Tauri and
    Kotlin separately, and the two-client drift is a recurring audit theme.

---

## 6. What Jarvis is missing that OpenMuse has, ranked

Ranked by how much it costs Jarvis not to have it.

| # | Missing | What it costs Jarvis today | Where OpenMuse has it |
|---|---|---|---|
| 1 | **A queue for work that outlives one turn** | The plan card is dead, Projects cannot run tests, the overnight tidy runs nothing, and any job longer than one chat turn is impossible. Also why the model cannot reach most of its own tools | `apps/server/src/engine/worker.ts` |
| 2 | **Recovery from a crash mid-job** | Nothing to recover - and no way to say "I do not know whether that went out" | `db.ts: recoverInterruptedActions()` |
| 3 | **A visible record of what ran** | Past approvals are already sent and ignored; there is no run log at all | `run-events`, `runs`, `activity` |
| 4 | **An idempotency key on outbound actions** | A retried send-email, tidy-inbox or home-control request has nothing stopping a second one | `actions.ts`; `computer-tools.ts`'s required `operationId` |
| 5 | **A decision bound to the exact proposal shown** | The signed stamp proves who approved, not what | `actions.ts: decide(owner, id, hash, decision)` |
| 6 | **Memoised tool results across a retry** | A retried step can repeat a side effect | `engine/model.ts: cached()` |
| 7 | **A job that stops to ask for one missing value** | Form review is designed but has no state machine to sit in | `waiting_input` + `question` |
| 8 | **Typed watches** (`contains`, `price_below`) and relative-time normalisation | Watches are free-text; "tell me when this is under £200" is not a first-class thing, and a clock on the page can fire a false change | `Monitor.condition`; `page-diff.ts` |
| 9 | **Evidence attached to a suggestion** | Leaning on `answer-sources.patch` alone | `Evidence` on `Idea` and `AgentTask` |
| 10 | **One place that says what is switched on** | The model is offered 3 of its 29 tools because of a two-file settings split (`~/.openjarvis/config.toml` vs `jarvis-framework.toml`) | The connector/status catalogue |
| 11 | **Artifacts that outlive the chat** | A plan, comparison or money summary lives as text in a conversation | `AgentArtifact` |
| 12 | **Side threads and chat organisation** (rename, pin, archive, restore) | Explicitly "proposals only" in [`JARVIS-TODAY.md`](../.claude/agents/JARVIS-TODAY.md):63 | Rich Threads (the implementation is NfJ) |
| 13 | **An install a second person could do** | Already Jarvis's worst problem, and unrelated to OpenMuse - but OpenMuse is a working example of the answer | `README.md`, `render.yaml`, `.env.example` |

**Not on this list, and it was on an earlier draft of it:** DNS-rebinding-proof
egress checking. Jarvis has it
([`jarvis_local_http.py`](../backend/jarvis_local_http.py)), it checks **every**
resolved answer rather than the first, and it already had a rebinding control
test. See Section 0's correction.

---

## 7. Copy this: the ranked borrow list

**Licence: MIT** ([LICENSE](https://github.com/CopilotKit/openmuse/blob/main/LICENSE)).
MIT permits reuse with attribution, so a port gets one line in
[THIRD-PARTY-NOTICES.txt](../THIRD-PARTY-NOTICES.txt) naming OpenMuse and
CopilotKit. **But almost nothing here is copy-paste:** OpenMuse is TypeScript
on Postgres, Jarvis is Python on SQLite. These are **re-implementations of
mechanisms**, which is the honest description - and for most of them the
OpenMuse file is best read as a specification.

Cost: **S** = under a day, **M** = a few days, **L** = a week or more.

### 7.1 Tier 1 - do these first

| # | Borrow | From | Why, and how it fits | Cost |
|---|---|---|---|---|
| 1 | **A durable task worker: `tasks`, `runs` and `run-events` tables, a lease claim, a self-fencing heartbeat, `checkpoint()`, `guard()` and an event feed** | `apps/server/src/engine/worker.ts`, `packages/domain/src/agent.ts` | The missing bottom half of Jarvis. It replaces no existing mechanism - Jarvis has no queue - and it unblocks the plan card, Projects' "run my tests", the overnight tidy, and the read-only sub-agent fan-out the 2026-10-06 audit asks for. Reuse Jarvis's existing rules rather than inventing new ones: every step is still its own gate action, `Pause`/`Stop` (`jarvis_task_control`) become the lease-cancel path, and the feed is a new **kind on the one scheduler** (`jarvis_schedule.register_kind`), never a second clock. Rule check: nothing leaves the PC; stopping stays ungated; no step is auto-approved | **M** |
| 2 | **`outcome_unknown` for an interrupted outbound write, with startup recovery** | `apps/server/src/db.ts: recoverInterruptedActions()` | About 30 lines, and it closes a real hole: if the PC crashes or is killed between "the gate said yes" and "the provider answered", Jarvis currently cannot tell the owner that it does not know. Applies to `send_email`, `draft_email`, `tidy_inbox`, `home_control`, `shell_exec`. Copy the refusal text nearly verbatim - *"check the provider before creating another action"* - because a silent retry after an uncertain send is exactly the failure the one-card-per-email rule exists to prevent | **S** |
| 3 | **An idempotency key on every outbound action** | `apps/server/src/actions.ts`; `computer-tools.ts`'s required namespaced `operationId` | The action's id becomes a hash of the caller's key, and insertion is `ON CONFLICT DO NOTHING`, so the same request twice returns the first proposal instead of making a second. Jarvis already has the approval-side half (`decide-once.patch` claims the row with a CAS); this is the **write**-side half. Cheapest possible protection against a double send | **S** |
| 4 | **Hash-bound approval: the card carries a hash of exactly what was shown, and the decision must send it back** | `apps/server/src/actions.ts: decide(owner, id, hash, decision)` | Jarvis's `owner-check.patch` proves **who** approved; this proves **what**. A card whose detail changed between being drawn and being decided is refused with *"This proposal changed."* It composes with the Windows Hello stamp rather than replacing it - the two together are strictly stronger than either project has alone. Also copy the **30-minute expiry with a compare-and-set to `expired`**, which pairs with the countdown `approval-expiry.patch` already sends | **S-M** |
| 5 | **Memoise tool results so a retried step cannot repeat a side effect** | `apps/server/src/engine/model.ts: cached()` | A sha256 of the tool name plus its arguments, keyed into task state. With a durable worker this is what makes a retry safe: a step whose result is already known is served from the record instead of being run again. Small, and it is the difference between "retries" and "safe retries" | **S** |
| 6 | **A "what Jarvis did and is doing" screen**, fed by `run-events` and `runs` | `engine/worker.ts: event()`, `actions.ts: record()` | Jarvis's own review makes this capability gap #1, and both apps already receive past approvals from `/api/ledger` and ignore them. Build it as one screen over data the new worker produces: task, step, kind, when, outcome, which device. **Titles and statuses only - no content** - so rule 1 is untouched | **M** |
| 7 | **One settings file, then a "what is switched on" page** | Concept from `engine/service.ts` and the connector catalogue in `docs/FEATURES.md` | Jarvis does not need OpenMuse's catalogue; it needs the **bug fixed first**: `~/.openjarvis/config.toml [tools] enabled` (27 names, 24 nonexistent) is what the chat path reads, while the "offer a reading tool" switch writes `jarvis-framework.toml`. Until that split is gone, no catalogue tells the truth. Fix the split (**S**), then list what is on with the card that turns each thing on (**M**) | **S-M** |

### 7.2 Tier 2 - worth having

| # | Borrow | From | Why, and how it fits | Cost |
|---|---|---|---|---|
| 8 | **The architecture itself: the chat turn cannot write; it delegates** | `engine/conversation.ts` (`delegate_task` and nothing else that writes) | The deepest lesson in this report, and it is free. Today Jarvis's chat turn both talks and acts inside a 6-round ceiling. Splitting "converse" (a short loop, immediate answers) from "do the job" (a longer, durable, resumable loop) is what lets OpenMuse give the task 16 steps and survive a restart - and it means an interrupted job never leaves a half-finished conversation. It also matches what Jarvis already believes: a plan card is one decision about a bounded set of steps | **M** (design, then follows #1) |
| 9 | ~~**DNS-rebinding-proof egress validation**~~ **Already built, and this entry was wrong - kept here so the mistake stays visible.** Jarvis's [`jarvis_local_http.py`](../backend/jarvis_local_http.py) has pinned the checked address at connect time since the 2026-09-27 security audit | `apps/worker/src/network.ts` - read, then discarded as a borrow | **What it DID earn, and it is done (2026-10-08):** OpenMuse's allowlist named ranges Jarvis's did not - `192.0.0.0/24`, the three TEST-NET blocks, `198.18.0.0/15`, multicast `224.0.0.0/4`, reserved `240.0.0.0/4`, IPv6 `ff00::/8` and `2001:db8::/32` - and named an IPv4-embedding form Jarvis did not unwrap, **NAT64** (`64:ff9b::/96`), where `127.0.0.1` is spelled `64:ff9b::7f00:1` and `ipaddress` does not report it as `.ipv4_mapped`. Both are now in `_PRIVATE_NETS` and `_address_carries`; the NAT64 range itself is deliberately NOT refused, because a NAT64 address carrying a public IPv4 is how an IPv6-only machine reaches the open internet | **Done** |
| 10 | **`waiting_input`: a job that stops to ask for one missing value** | `packages/domain/src/agent.ts: TaskStatus`, `AgentTask.question` | The state `docs/FORM-REVIEW-DESIGN.md` is missing. Cheap once Tier 1 exists: one more status, one more field, one route (`POST /tasks/:id/input`). It is how "ask, don't guess" stops being a prompt line | **M** |
| 11 | **Typed watch conditions, dedup and relative-time normalisation** | `Monitor` in `packages/domain/src/agent.ts`; `engine/page-diff.ts: withoutRelativeTimes()` | Jarvis already has page watches, "tell me when", its own hourly floor and end dates. New here: the **typed condition** (`change`, `contains`, `price_below` with a validated positive number), per-watch `lastHash` dedup so one change is not reported five times, and rewriting relative timestamps before hashing so a page that says "3 hours ago" does not look changed every hour | **M** |
| 12 | **Evidence as an object on tasks, suggestions and ideas** | `packages/domain/src/agent.ts: Evidence` | `{id, kind: mail\|file\|web\|user, title, excerpt, url}`. Jarvis's suggestions carry a reason but not a checkable source. It also gives both apps one shape to draw, and a rule worth adopting: **a suggestion whose matching work is already done is not shown** | **S-M** |
| 13 | **Artifacts as first-class results** | `AgentArtifact` (`plan`, `comparison`, `finance`, `report`) | A plan, a comparison of several AIs, a spending summary and a report currently live as chat text. Making them records lets History link to them, lets them survive "Continue this chat", and gives Projects something to attach benchmarks to | **M** |
| 14 | **Binding a pending approval to the account or key it was prepared under** | `actions.ts: connectionId`, `account`, `targetVersion` | Only matters once Jarvis has connectors with changeable credentials - but the check is a few lines each, and it closes "approved under the old account, ran under the new one" | **S** |
| 15 | **The test shapes, which are the most directly portable part of all this** | `tests/` (described in `README.md` as workflow, runtime, persistence, provider-contract and authorization tests) | Five Python tests that each fail today: (a) kill the backend mid-task and prove the lease is reclaimed; (b) crash between gate-yes and provider-answer and prove the action reads `outcome_unknown`, never `succeeded`; (c) call the same outbound action twice with one idempotency key and prove one write; (d) decide a card with a stale hash and prove it is refused; (e) double-tap Approve and prove one effect. Jarvis's house rule is already "every patch here has a test that fails on the unpatched tree" | **S** |
| 16 | **A truthful message when a loop limit ends the run** | `engine/tanstack-agent.ts: reportStepLimit()` | Jarvis's own invariant is "nothing is claimed that is not true", and a silent stop at round 6 currently looks like a finished answer. Small, and it protects the one thing this project cares most about | **S** |

### 7.3 Tier 3 - read, and probably do not port

| # | Thing | Why not |
|---|---|---|
| 17 | **The live browser console with 15-minute HMAC-signed URLs** | Jarvis already has a visible Playwright window on the owner's own PC, plus "Solve it here" passing taps from the phone. The signed-URL console exists because OpenMuse's browser is a *remote service*; Jarvis's is not. Read `apps/server/src/browser-console.ts` and `auth.sign` for the takeover **idea** (pause the agent, hand the same session over), which Jarvis mostly has |
| 18 | **The AG-UI protocol / "compatible with any agent harness"** | Would mean a second, general client protocol. Jarvis is one-sided **on purpose** ([ARCHITECTURE.md](ARCHITECTURE.md) §8). Not recommended unless the owner asks |
| 19 | **The Docker computer, as a package** | OpenMuse's own docs say it is not a full VM, and Jarvis has already refused Docker/WSL2 packaging. The useful lesson is the opposite of a borrow: OpenMuse **bounds** what the agent may run (nonroot uid 1000, read-only rootfs, all capabilities dropped, `no-new-privileges`, `network none`, 512 MB, 128 pids, `/workspace` only) while Jarvis's `shell_exec` runs with the owner's full permissions. The borrow is the bounding, and Jarvis's own A2 #7 (AppContainer) is already the right answer |
| 20 | **A single schemaless `records` table with JSONB CAS** | Elegant for a greenfield TypeScript service. Jarvis has real, typed, long-lived SQLite schemas with 260 test suites depending on them; converting to JSON blobs would trade its strongest asset for tidiness. **Read `compareAndSwap` and `setMilestoneDone` and steal the ideas, not the storage model** |
| 21 | **Goals and milestones as records** | Jarvis already has both (`jarvis_goals.py`, 989 lines, with per-step cards). One good idea remains: `setMilestoneDone` updates a single checkbox, so a concurrent rename or reorder is not clobbered |

### 7.4 The bottom line on copying

**Roughly 400-600 lines of Python, three new SQLite tables, one screen and
five tests buy Jarvis the whole of what OpenMuse is better at.** Everything
else OpenMuse does better is either something Jarvis has already decided
against, or something that only makes sense for a hosted product. And the
single most valuable item on the list - "the chat turn delegates work to a
durable job" - costs no code at all to decide.

---

## 8. Never copy this - and the rule it breaks

| Do not copy | Rule, or the incident that proves it | Why, in one line |
|---|---|---|
| **CopilotKit Intelligence as the thread store** | 1 - private things stay on the PC | It is required in *every* mode; a conversation would live on someone else's server, and it is explicitly not covered by the repository's MIT licence |
| **Parallel's Search MCP** | 1 and 3 | Its own README says it sends model-generated queries **and conversation context** plus a session id to a third party. Jarvis already has five providers with a local SearXNG default; there is nothing to gain |
| **Telemetry, and the sentence about it** | 1 and 3 | Events leave the PC by default. Worse is `docs/TELEMETRY.md`'s own advice: *"Remove old deployment settings that disable telemetry if tracking is desired."* A tool should not talk the person out of their own opt-out. Jarvis has no telemetry, and its review already flagged an unused third-party telemetry package sitting in the tree |
| **A cloud model as the agent** | 1 | `openai/gpt-5` by default. Jarvis may use a cloud lane one question at a time after a yes - as a *lane*, never as the brain |
| **`0.0.0.0` binds and one shared access key** | 2 and 4 | The opposite of Jarvis's own-networks-only rule and its per-device keys with a signed approval. `auth.ts` hardcodes the owner to `local-user`; `SECURITY.md` says it is not multi-tenant authentication |
| **A hosted browser or computer service** | 2 | Reaching a browser or a shell over a network is a public endpoint by another name. Jarvis's browser is a window on the owner's own PC |
| **The E2B desktop path, in any form** | 1, 2, 4 | OpenMuse's own `SECURITY.md` is damning: internet on, passwordless sudo, every listening port publicly reachable, an 8-character effective VNC password, the stream URL itself a bearer secret, and *"approval gating covers only the app's own email and calendar tools, so a prompt-injected agent could send data from the computer or submit forms in its browser."* That is the exact failure Jarvis's gate exists to prevent |
| **`--auto-approve`-shaped shortcuts** | 4 | OpenMuse has none, but its direct reads and its scripted sample mode are the kind of thing that becomes one. Jarvis's `no-auto-approve.patch` exists because this pattern keeps arriving - and the blanket grant it removed had a docstring explaining why it was fine |
| **Treating "shipped" as "works"** | - | Both projects are honest about this (an "Alpha" banner and a `VERIFICATION.md`; 30 "not built" lines and a preflight). But 14 silent failures is the failure mode they share. Copy the *discipline*, not the claim |
| **A second agent protocol, or a second automation engine** | - | Already refused in [ARCHITECTURE.md](ARCHITECTURE.md) §11 and the earlier reports: A2A, n8n/Node-RED, NeMo Guardrails, MCP Apps. OpenMuse's AG-UI is a good design for a project that wants many clients; Jarvis does not |

---

## 9. Where the two projects independently agree

The most valuable section, because two unrelated codebases arriving at the
same rule is evidence for the rule.

| Rule | OpenMuse | Jarvis |
|---|---|---|
| Reads need no approval; **writes do** | Mail, calendar, files and browser reads are ungated; every send or calendar change goes through `propose` → review | The gate's `auto` tier covers reads; every acting tool is `ask` or `notify` |
| **One card per action, nothing auto-approved** | `propose` always lands in `awaiting_review`; no auto-approval path was found in `actions.ts` | `no-auto-approve.patch`: the blanket grant was removed, and a test fails if it comes back |
| **A denial is an answer; be careful about retrying** | *"No hidden retry occurs after an uncertain external write"* (`README.md`); `MODEL_MAX_RETRIES = 2` and "a stream that fails after it starts is not retried" | `timed_out` is deliberately not `denied`, and the model is told which - so it does not work around a gate nobody answered |
| **A decision must not outlive the thing it was about** | 30-minute expiry with a CAS to `expired`; `targetVersion` on an edit | `approval-expiry.patch` sends seconds-left, so a phone with a wrong clock still counts down correctly |
| **One owner, no standing grant** | One shared `OPENMUSE_ACCESS_KEY`; the owner is a hardcoded local user | One owner, per-device keys, no standing grants, and an offer may never ask for more access |
| **A model-free path, so simple things keep working** | `AGENT_BACKEND=sample` needs no model at all | `jarvis_quick.py` answers 93 intents without the model, so a timer works while the model is asleep |
| **Local by default** | Defaults to loopback and `.openmuse/`; sample mode forces a loopback host | This PC, the home network, Tailscale or NordVPN Meshnet - and a non-loopback bind with no token refuses to start |
| **Do not claim what is not verified** | `docs/VERIFICATION.md` lists what is mocked, and the roadmap lists what is unchecked | `docs/CLAIMS.tsv` + `tools/check_claims.py`, a live preflight, and audit passes that publish their own failures |
| **The agent's private reasoning is not shown to a client** | The UI shows work and results, not the model's scratchpad; images are stripped from replaying tool results (`textOnlyToolResult()`) | `ARCHITECTURE.md` §10: the reasoning is deliberately not published, because the event bus reaches a phone's lock screen |
| **Nothing acts on what it read** | `CONTRIBUTING.md`: *"Treat website, mail, and PDF text as data. It cannot grant tool permissions or approve a write."* | The taint rule: after outside text a write asks again, and the rush latch raises the tier of whatever comes next |
| **A step that might have gone out is not repeated** | `outcome_unknown` is kept, not retried | One card per email, and the card says plainly when the conversation has read outside text |

**A note on the tenth row.** OpenMuse's `CONTRIBUTING.md` line and Jarvis's
own outside-text fence ([ARCHITECTURE.md](ARCHITECTURE.md) §4, "These lanes
leave the machine. Nothing else may") are the same rule, arrived at
independently, in different languages, for different reasons. That is the
strongest signal in this report that the rule is right - and a reminder that
it is easy to lose: the fence went back out of this tree on 2026-10-08
(commit `096719a8`) because it broke suites that asserted the older output.

---

## 10. What this changes about the current build queue

Not much, and that is the finding.

- The queue the owner set on 2026-09-30 and the seven steps of
  [FEATURE-REVIEW-2026-10-04.md](FEATURE-REVIEW-2026-10-04.md) both begin with
  **"tell the truth about the hardware"**, **"fix what is broken or lying"**
  and **"make use visible"**. OpenMuse changes none of that. If anything it
  sharpens step 3: *"fix what is broken or lying"* should include the
  tool-offering split, which is the cheapest fix in this whole report.
- **One new item deserves a place in the queue:** the durable task worker
  (Tier 1 #1), plus the design decision behind it (Tier 2 #8). It is the only
  borrow here that unblocks work the owner has **already decided to have** -
  the plan card, Projects running tests, the overnight tidy, and the read-only
  sub-agent fan-out the 2026-10-06 audit asks for. Everything else on the list
  is a refinement.
- **Two items should be dropped from consideration**, since OpenMuse shows no
  advantage: a browser "take control" console, and an AG-UI-style open
  protocol.
- **One item gets better evidence for waiting:** *"an install a second human
  could survive"*. OpenMuse is a working, if alpha, example - one
  `.env.example`, one health route, one compose file - and Jarvis's backend
  still has no download at all.

---

## 11. Decisions this comparison needs from the owner

Following the standing rule: short questions, recommendation first, plain
words.

**Q1. OpenMuse is better than Jarvis at one big thing: work that takes a
while. It keeps a list of jobs, remembers where it got to, picks a job up
again after a crash, and shows what it did. It also splits "chat" from "do
the job" - its chat helper is not allowed to send or change anything; it
hands the job to the list. Jarvis has none of that, which is also why "one
card, several steps" and Projects' "run my tests" cannot work. What should
happen next?**

- **A. Build the job list, and split chat from jobs - recommended.** A few
  days. It is all local, every step still asks you exactly as today, and it
  makes four things you already asked for possible.
- **B. Fix the two-settings-file bug first, so the model can actually use its
  tools.** Under a day. Thirty tools are built and the model is offered
  three.
- **C. Neither yet - keep this report and finish the current queue.** Nothing
  changes today.

**Q2. There are five small safety mechanisms in OpenMuse that Jarvis does not
have: a card that cannot be approved if it changed underneath you, a "don't
send this twice" stamp, a clear "I don't know whether that went out" state
after a crash, a remembered result so a retried step cannot act twice, and an
address check that cannot be fooled by a name that answers twice. Each is
small. How should they be handled?**

- **A. Build all five with the job list, each with its own test -
  recommended.** They are much easier to add while that part of the code is
  open.
- **B. Only the two about sending things** (the "don't send twice" stamp and
  the "I don't know whether it went out" state). They prevent a real double
  email.
- **C. Write each one up as a design first**, and build nothing yet.

---

## Sources

**OpenMuse** - read 2026-10-08 from `main`:

- [README.md](https://github.com/CopilotKit/openmuse/blob/main/README.md) -
  shape, services, cost, telemetry, search, Rich Threads, licence
- [docs/FEATURES.md](https://github.com/CopilotKit/openmuse/blob/main/docs/FEATURES.md),
  [ROADMAP.md](https://github.com/CopilotKit/openmuse/blob/main/ROADMAP.md),
  [SECURITY.md](https://github.com/CopilotKit/openmuse/blob/main/SECURITY.md),
  [CONTRIBUTING.md](https://github.com/CopilotKit/openmuse/blob/main/CONTRIBUTING.md),
  [.env.example](https://github.com/CopilotKit/openmuse/blob/main/.env.example),
  [LICENSE](https://github.com/CopilotKit/openmuse/blob/main/LICENSE)
- [docs/VERIFICATION.md](https://github.com/CopilotKit/openmuse/blob/main/docs/VERIFICATION.md),
  [docs/TELEMETRY.md](https://github.com/CopilotKit/openmuse/blob/main/docs/TELEMETRY.md),
  [docs/RICH-THREADS.md](https://github.com/CopilotKit/openmuse/blob/main/docs/RICH-THREADS.md),
  [docs/COMPUTER.md](https://github.com/CopilotKit/openmuse/blob/main/docs/COMPUTER.md),
  [docs/DEMO.md](https://github.com/CopilotKit/openmuse/blob/main/docs/DEMO.md),
  [docs/OPENBOT-INTEGRATION.md](https://github.com/CopilotKit/openmuse/blob/main/docs/OPENBOT-INTEGRATION.md)
- Source: [`apps/server/src/actions.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/actions.ts),
  [`db.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/db.ts),
  [`auth.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/auth.ts),
  [`config.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/config.ts),
  [`agent.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/agent.ts),
  [`computer-tools.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/computer-tools.ts),
  [`search.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/search.ts),
  [`engine/worker.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/engine/worker.ts),
  [`engine/model.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/engine/model.ts),
  [`engine/conversation.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/engine/conversation.ts),
  [`engine/page-diff.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/engine/page-diff.ts),
  [`engine/finance.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/engine/finance.ts),
  [`engine/tanstack-agent.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/server/src/engine/tanstack-agent.ts),
  [`apps/worker/src/network.ts`](https://github.com/CopilotKit/openmuse/blob/main/apps/worker/src/network.ts),
  [`packages/domain/src/agent.ts`](https://github.com/CopilotKit/openmuse/blob/main/packages/domain/src/agent.ts),
  [`packages/integrations/src/vault.ts`](https://github.com/CopilotKit/openmuse/blob/main/packages/integrations/src/vault.ts),
  [`packages/backends/src/openbot.ts`](https://github.com/CopilotKit/openmuse/blob/main/packages/backends/src/openbot.ts)
- The repository tree, via the GitHub contents API for `apps/server/src` and
  `apps/server/src/engine`

**Jarvis** - read in this repository: [README.md](../README.md),
[CLAUDE.md](../CLAUDE.md), [CHANGELOG.md](../CHANGELOG.md),
[docs/ARCHITECTURE.md](ARCHITECTURE.md) (§3, §4, §8, §9, §10, §11, §12),
[docs/JARVIS-API.md](JARVIS-API.md),
[docs/FEATURE-REVIEW-2026-10-04.md](FEATURE-REVIEW-2026-10-04.md),
[docs/AUDIT-PASS-2026-10-05.md](AUDIT-PASS-2026-10-05.md),
[docs/BUG-AUDIT-2026-10-05.md](BUG-AUDIT-2026-10-05.md),
[docs/DEEP-AUDITS-2026-10-05.md](DEEP-AUDITS-2026-10-05.md),
[docs/SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md](SELF-IMPROVEMENT-AND-CAPABILITY-AUDIT-2026-10-06.md),
[docs/HANDOFF-2026-10-06-self-improvement-audit-and-openjarvis-borrows.md](HANDOFF-2026-10-06-self-improvement-audit-and-openjarvis-borrows.md),
[docs/BUILD-QUEUE-2026-09-30.md](BUILD-QUEUE-2026-09-30.md),
[docs/COMPETITORS-2026-10-05.md](COMPETITORS-2026-10-05.md),
[docs/PEERS.md](PEERS.md), [plugins/README.md](../plugins/README.md),
[.claude/agents/JARVIS-TODAY.md](../.claude/agents/JARVIS-TODAY.md),
`backend/gate-outcome.patch`, `backend/decide-once.patch`,
`backend/approval-expiry.patch`, `backend/no-auto-approve.patch`,
`backend/task-control.patch`, and the file listings of `backend/`, `docs/`,
`plugins/`, `server/`, `tools/` and `scripts/`.

**Still not read, and therefore not claimed:** OpenMuse's `apps/mobile`
source, its `tests/` suite, `apps/computer/files.py` and `Dockerfile`, and
`packages/integrations/src/pdf.ts` beyond the size and page limits quoted
above. Nothing in this report was run, built or attacked.
