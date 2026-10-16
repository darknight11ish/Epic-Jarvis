# Jarvis Self-Improvement — Design Document for Review

**Status:** DESIGN FOR REVIEW — nothing built, nothing committed
**Author:** Lead session, 2026-10-15
**Repository:** darknight11ish/Epic-Jarvis (main = 8f55058a)
**Reviewer:** Gemini
**Owner's instruction that prompted this:** "have Jarvis itself adapt to any updates from Ollama by running a
local AI model to do the work? Eventually I would like to get Jarvis to do any work on itself using the local ai
models."

> **Transcribed into the repository on 2026-10-16** by the DeepSeek session, because the document existed only
> in a chat window and the work order that calibrates to it could not be followed without it. The content below
> is the document as given, unedited. **Two things a reader must know:**
>
> 1. It is pinned to `main = 8f55058a`, which is **not** today's `main`. Checked on 2026-10-16 against
>    `origin/main = 2f85d772`: `jarvis_hardware.py:606` and `:912` are **exact**; `modify_own_code` exists at
>    `jarvis_gate.py:278`; but `jarvis_agent.py`'s `_lookup_context` is now **:3619** (not :3578),
>    `_model_can_use_tools` is **:3654** (not :3613) and `_model_can_see_pictures` is **:5730** (not :5670).
> 2. The `modify_own_code` risk tuple is `("hard", "local", "revertible from a backup, not from here")` — three
>    elements, not two. **The third matters to Claim 3**: the gate itself says this class of change is revertible
>    from a backup rather than from here.

## 0. Read this first — the one-sentence shape

Jarvis may read its own source, diagnose problems, and draft changes, using the local model; it may never
apply a change to itself without the owner's explicit yes, and every change it proposes must be reversible
in one click and recorded in the log he already has.

Everything below is detail in service of that sentence. If a reviewer disagrees with anything, this is the claim
to argue with.

## 1. The owner's request, split into three separable features

His sentence contains three asks of very different risk. They must not be built as one thing.

| # | Feature | Risk | Verdict |
|---|---|---|---|
| A | Adapt to Ollama updates — notice when the running Ollama is not the one Jarvis understands, and say so | Low | Build now. Mostly a detection + reporting problem |
| B | Diagnose itself — read its own source and logs, explain what is broken, propose a fix | Moderate | Build now, read-only. This is where the value is |
| C | Change itself — apply a proposed edit to its own code | High | Build last, and only with the boundary in §5. This is the one that can break the owner's machine |

The owner asked for all three. A and B are safe and useful on their own; C is the part that needs a design,
which is what §5 and §6 are for.

## 2. Why this is a real feature and not a novelty

Three facts about this repository make self-diagnosis unusually valuable here:

1. The project's most expensive recurring failure is a wrong premise. On 2026-10-15 alone, eight work
   items were found to be already built, non-existent, or mis-described — and four of the Lead's own
   briefs were wrong. Every one was caught by reading the source. A local model that reads source and
   reports "this already exists at file:line" is exactly the missing tool.
2. Failures here are silent by design in several places. A rehearsal that reported "all patches are on" while
   nothing was applied; a run_due() tested directly while its caller was missing; suites that silently skip
   half their checks under a 0o700 sandbox. A system that reads its own state and notices inconsistency is
   the general fix for a general problem.
3. The local model is already good enough for the reading, not the deciding. qwen3.5:9b reads files and
   answers questions about them. It is not reliable enough to be trusted to edit code un-reviewed —
   which is precisely why §5 draws the line where it does.

## 3. Feature A — adapting to Ollama updates

### 3.1 The current design, and why it is already right

Jarvis is capability-driven, not version-gated (verified in source):

- `jarvis_hardware.py:606` calls `/api/version` and reports it as `ollama_version` at `:1339` — for display
  only. No code branches on it.
- `jarvis_hardware.py:912` states the intent explicitly: card detection works "by the cards alone, so a
  new Ollama version does not forget that a" card exists.
- Capabilities are asked at runtime: `jarvis_agent.py:3613` `_model_can_use_tools()` and `:5670`
  `_model_can_see_pictures()` read `/api/show`'s capabilities; `:3578` `_lookup_context()` reads `/api/ps`
  then `/api/show`.
- The three-state return is deliberate: False → offer no tools; None ("an older Ollama, or no answer") →
  proceed anyway, because an Ollama too old to send capabilities also does not enforce tool support;
  for vision, `keep_picture=sees is None` (`:7621`) keeps the image rather than sending an image-blind
  request.

This means most Ollama updates need nothing. A new model is asked, not assumed.

### 3.2 The actual gap

Unrecognised capability vocabulary degrades silently. If a future Ollama renames "tools", or changes the
shape of `/api/show`, `_model_can_use_tools()` starts returning None and Jarvis quietly stops offering tools.
No error, no failing test, no signal to the owner.

The same applies to response fields the code reads directly, which the module cites against Ollama's own
source (`ollama/server/routes.go`, `ollama/openai/openai.go`, `ollama/server/prompt.go`, `ollama
model/parsers/qwen3.go`).

### 3.3 What to build

1. A static contract guard (already dispatched): pin the exact capability strings and response fields Jarvis
   reads, and fail loudly if the comparison changes. Static, so it needs no running Ollama — the guard is
   about the contract, not the connection.
2. A runtime compatibility probe. On startup and on model change, ask `/api/show` and classify what
   comes back:
   - **Understood** — every capability Jarvis relies on is present and named as expected.
   - **Unknown capabilities present** — the list contains words Jarvis does not recognise. Not an error: log
     them, surface them once in the HUD's diagnostics, and continue.
   - **Expected capability missing that the model plainly has** — e.g. the model file is known to be a tool-
     calling model but capabilities has no tools. This is the case worth telling the owner about, because
     it means Jarvis is about to under-use his model.
3. Report it where he already looks — the existing status/diagnostics surface, not a new window. One
   line, plain words, with the Ollama version and what was not understood.
4. Never a version comparison. A guard that pinned a version number would be worse than none: it
   would make Jarvis refuse a working newer Ollama.

### 3.4 Acceptance criteria for A

- The static guard fails when a capability string Jarvis compares against is changed, and passes
  unchanged.
- A stubbed `/api/show` returning an unknown capability produces a reported condition, not a silent None.
- A stubbed `/api/show` missing `capabilities` entirely keeps today's behaviour exactly (proceed, three-
  state None) — this must not regress.
- No new network call on the hot path; the probe is cached the way `_CTX_CACHE`/`_TOOLS_CACHE` already
  are.

## 4. Feature B — Jarvis diagnoses itself (read-only)

This is the feature with the most value per unit of risk, and it is read-only by construction.

### 4.1 What it does

Given a question from the owner — "why did my last backup fail?", "is the jobs queue actually running?",
"what is broken right now?" — the local model:

1. Reads the relevant subset of Jarvis's own source, logs, and state.
2. Answers with citations: file:line and a quoted line, never a paraphrase presented as fact.
3. Says plainly when it cannot tell, rather than guessing.

### 4.2 Why it must quote rather than summarise

This repository's own rule, and it was earned: "a stack frame read as a cause and relayed as confirmed",
and "a bug invented by grepping my own draft and mistaking it for the source file." Two independent
readers once "confirmed" the same wrong finding with the same wrong command. A self-diagnosis feature
that paraphrases would industrialise that failure. So: quotes with line numbers, or an explicit "I could not
establish this".

### 4.3 What it may read

| Source | Allowed | Why |
|---|---|---|
| `backend/`, `jarvis-backend/`, `tools/`, `scripts/` | Yes | The program itself |
| Its own logs and the event stream | Yes | The state it is being asked about |
| `docs/`, `features/features.json` | Yes | What it is supposed to do |
| `~/.openjarvis` databases | Through existing modules only | Never a raw SQLite handle; the modules already enforce taint and scrub rules |
| The owner's documents, mail, calendar | Only if the question requires it, through the existing local-only paths | Rule 1 — and the taint latch must apply |
| Anything on the network | No | Rule 2 |

### 4.4 The hard part, stated honestly

The model must not be asked to be right about things it cannot verify. A 9B model reading 200,000 lines
will hallucinate. So the design is:

- **Retrieval first, model second.** A deterministic retrieval step selects a small, relevant set of files and
  lines (the repo already has `tools/` checkers and a `CLAIMS.tsv` register to anchor this).
- The model explains and connects; it does not recall. Every claim carries the line it came from.
- **Confidence is not asked for and not reported.** A model's self-reported confidence is not evidence.
  What is reported instead is "here is the line" or "I could not find it".

### 4.5 Acceptance criteria for B

- Every answer contains at least one file:line citation, or states that it could not determine the answer.
- A test feeds it a question whose answer exists and whose answer does not; the second must produce an
  explicit "could not find", not a plausible guess.
- No new route reaches the network. Verified by the existing egress checkers.
- The taint latch applies: a question touching memory, credentials or the owner's documents cannot be
  escalated to a cloud lane.

## 5. Feature C — Jarvis changes itself, with the boundary

This is the part that needs the owner's decision, and the boundary is the design.

### 5.1 The boundary, in one table

| The model MAY | The model MAY NOT |
|---|---|
| Read any file it is allowed to read (§4.3) | Write any file without an approval card |
| Draft a patch, a diff, or a new file | Apply that patch itself |
| Explain what the change does, in plain words | Modify `jarvis_gate.py`, the approval path, or any tier/risk table |
| Propose the test that would prove it | Disable, weaken or delete a test |
| Say "this is beyond what I can do safely" | Touch `jarvis-backend/` (the canonical shipped program) |
| | Change `$PATCHES`, `$SHIPPED`, or the three lists |
| | Reach the network |
| | Approve anything, ever |

The governing rule is rule 4: the app never auto-approves anything. A self-modifying system is, by
construction, modifying the program that enforces that rule — so the change path must be strictly outside
the thing being changed.

### 5.2 The loop, in order

1. **Propose.** The owner asks, or a diagnostic finding raises a proposal. The model drafts a change and
   explains it.
2. **Show.** The owner sees a diff, not a summary — the actual lines, plus what the model says it does and
   where it got that.
3. **Prove.** The proposal must carry the test that would fail without it. No test, no proposal — this
   repository has been burned repeatedly by checks that could not fail.
4. **Approve.** One card, the existing one. Tier `modify_own_code`, which already exists in the risk table as
   `("hard", "local")` — local-only, not swipe-approvable.
5. **Apply, on a branch.** Never on `main`, never in a working tree that is in use.
6. **Verify.** Run the affected suites and the checkers before the owner is told it worked. A green claim from
   an unrun test is the failure mode this whole document exists to avoid.
7. **Receipt.** `jarvis_receipts.record()` — the same one-click undo every other action gets. For a code
   change, undo means revert the commit, and that must be stated on the card.
8. **If verification fails**, it is not offered as done. The failure is reported, the change is left unapplied or
   reverted.

### 5.3 The five things that make this safe rather than dangerous

1. **The gate is outside the model's reach.** The model cannot edit `jarvis_gate.py`, the tier tables, or the
   approval code. Enforced by a checker that fails if a self-improvement diff touches them.
2. **Every change is reversible in one click**, via the receipts mechanism that already exists.
3. **Everything is recorded.** Every proposal, approval, application and verification result, with the model
   that produced it.
4. **A change is a diff the owner can read.** Never "done", never a black box.
5. **Verification is mandatory and precedes the claim of success.** The one rule this project keeps having to
   relearn: a test that did not run is not a pass.

### 5.4 What this explicitly does NOT do

- It does not let Jarvis run unattended. Every change needs the owner present. That is deliberate and is
  not a limitation to be engineered away later.
- It does not create a second permission path. If it needs a new tier, that is a change to `jarvis_gate.py`
  — which the model may not make, so it requires the owner to build it.
- It does not touch the phone. `docs/ARCHITECTURE.md` §8: the phone is a remote, not a second brain.

### 5.5 Acceptance criteria for C

- A self-improvement diff touching `jarvis_gate.py`, a tier table, or a test file is refused by a checker, and
  the refusal is bite-proved.
- A proposal without a test cannot reach the approval card.
- The card shows the diff, the claimed effect, the test, and that undo is a revert.
- Applying runs the affected suites and the checkers, and reports their real output; a failure cannot be
  reported as success.
- `jarvis_receipts` carries the entry, and one click reverses it.
- A test proves a change cannot be applied without an approval, by attempting it.

## 6. The safety argument, stated so it can be attacked

A reviewer should try to break these claims:

**Claim 1 — the model cannot escalate its own privileges.** It cannot edit the gate, the tier tables, or the
approval path. Counter to look for: any route by which a proposed diff reaches those files — including via a
patch file, a plugin folder, `$SHIPPED`, or a generated file that a checker reads.

**Claim 2 — the model cannot act without the owner.** Every application is carded at tier `modify_own_code`.
Counter to look for: an existing autonomous path that already applies changes — the jobs ticker and the
initiative engine are both live loops, and neither may be allowed to apply a self-improvement.

**Claim 3 — every change is reversible.** Receipts exist for actions. Counter to look for: a change that is not
reversible by `git revert` — a database migration, a generated file consumed before the revert, a patch-
history edit.

**Claim 4 — the model cannot exfiltrate.** It reaches no network. Counter to look for: the escalation path,
which does reach a network and is gated by the taint latch; and the patch/diff text itself, which could carry a
secret if the model read one.

**Claim 5 — a wrong diagnosis cannot become a wrong change silently.** Proposals are diffs with tests, and
verification precedes the success claim. Counter to look for: the failure mode where a test silently skips —
measured in this very sandbox today, where `test_base_matches_repo.py` ran 15 of its 30 checks and
reported green.

## 7. Phasing, with what each phase must prove before the next starts

| Phase | Build | Must prove before moving on |
|---|---|---|
| 1 | Ollama contract guard (§3.3.1) | Bites when a capability string changes |
| 2 | Compatibility probe + report (§3.3.2–3) | Unknown capability is reported, not silent; missing `capabilities` does not regress |
| 3 | Read-only self-diagnosis (§4) | Cites lines; says "could not find" when it cannot; no network |
| 4 | Proposal drafting, no application (§5.1–5.2 steps 1–3) | Diff shown; no test, no card; the gate/tier/test refusal checker bites |
| 5 | Application with approval + verification + receipt (§5.2 steps 4–8) | Cannot apply unapproved; failure cannot be reported as success; one-click undo works |

**Phases 1–3 are safe to build now. Phase 4 is safe and useful on its own** — a Jarvis that drafts fixes for the
owner to apply by hand is already valuable. Phase 5 is the one to argue about, and it should not start until
phases 1–4 are real and the claims in §6 have survived review.

## 8. What this design deliberately refuses

- No unattended self-modification. Ever, in any phase.
- No self-reported confidence. The model says where it read it, or says it does not know.
- No new permission path. One gate, one card, one tier table.
- No auto-approval, no bulk approval, no "trust this model" switch. Rule 4 is absolute.
- No version pinning of Ollama — it would make Jarvis refuse a newer, working Ollama.
- No phone involvement.

## 9. Open questions for the reviewer

1. **Is the boundary in §5.1 drawn in the right place?** Specifically: should the model be allowed to draft a
   change to `tools/check_*.py` (the checkers)? It is not the gate, but it is the thing that decides whether a
   change is safe.
2. **Is phase 4 useful enough on its own?** A Jarvis that drafts and explains, for the owner to apply by hand,
   has most of the value and none of the risk. Should phase 5 exist at all?
3. **What is the smallest test that proves "cannot apply unapproved"?** The design says "attempt it and
   fail" — is there a cheaper, stronger proof?
4. **How should a self-improvement interact with the patch stack?** A change to a shipped module is a
   `$SHIPPED` edit; a change to `jarvis_hud.py` needs a patch, and today registering one costs 27 files (§3 of
   the handover). That is a real cost on every self-edit and may deserve its own answer.
5. **Should self-improvement proposals be visible where the owner already looks** — the receipts list — or
   somewhere separate, so they are not confused with actions he asked for?

## 10. The one-paragraph summary for a busy reviewer

Jarvis is already capability-driven rather than version-gated, so it adapts to most Ollama updates for free;
the gap is that unrecognised capabilities degrade silently, and the fix is a contract guard plus a visible
compatibility report. Self-diagnosis is the high-value, low-risk feature — the local model reads its own
source and logs, and answers with file:line citations or an explicit "I could not find it", which directly
addresses this project's most expensive recurring failure (a confident wrong premise). Self-modification is
the one needing care: it is safe only if the model can propose but never apply, if the gate and the tier tables
are outside its reach, if every change is a readable diff with a test that can fail, if verification runs before
success is claimed, and if one click undoes it. Phases 1–4 deliver most of the value with none of the risk;
phase 5 should be argued about on its own.
