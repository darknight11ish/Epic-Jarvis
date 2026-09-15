# Jarvis: how the pieces fit

This is the source of truth. Every other document in `docs/` is a detail of
something stated here; where they disagree, this wins and the other is stale.

Read this before adding anything. The characteristic defect of this codebase
has been capability with no call site — `propose()` with zero callers, a Pump
nothing constructed, a `retire()` nobody calls, an event kind no client
handles. Almost every one of those started as a good idea built beside the
system instead of into it.

---

## 1. What it is

A local-first assistant for one person, on one Windows 11 workstation, with an
Android companion reached over Tailscale. A Python HTTP server does the work;
a Tauri 2 shell (Rust + WebView2) is the desktop face; the model runs in Ollama
on the machine's own GPU.

Non-commercial. One owner. That shapes everything: there is no multi-tenancy,
no account system, no scale problem — and correspondingly no excuse for a
control that acts on more than one thing at a time.

---

## 2. The invariants

These are not preferences. Anything that violates one is wrong, however well
it works.

1. **Everything private stays on the local model.** Cloud lanes exist; what
   may reach them is bounded and enforced in code, not by convention.
2. **No public tunnel, ever.** Reachability is Tailscale. A non-loopback bind
   with no `HUD_TOKEN` refuses to start — `SystemExit(2)`, not a warning.
3. **No auto-approve anywhere, and no approve-all control anywhere.** One
   action, one decision. Do not build one.
4. **An item carrying `raised` never belongs in a group that can be actioned
   quickly**, whatever its `risk.swipe_ok` says.
5. **`POST /api/digest/seen` marks read and approves nothing.**
6. **Nothing is claimed that is not true.** A promise the product cannot keep
   is worse than no promise, because the owner stops checking. Several fixes
   in this repo are nothing but a sentence being made true.

### What "no approve-all" actually means

It forbids a control that grants permission for **future, unnamed** actions.

It does not forbid one decision about one bounded set of things, every one of
them shown in full. Approving a shell command with eight arguments is one
decision. Approving eight enumerated, printed search queries for one audit is
one decision. Approving "web access" as a standing setting is not — that is
the thing this rule exists to prevent.

---

## 3. The permission model — one mechanism, no exceptions

**Every capability that acts on the world or leaves the machine uses the same
four steps.** If a new feature needs its own approval flow, the design is
wrong.

```
plan()      Work out what would have to be done. Touch nothing. Open no
            socket. Return a plan object.

describe()  Render the plan for a person: every command, every URL, in FULL.
            No summarising — summarising a request on the card that
            authorises it defeats the card. Plus, always, what refusing
            costs. A permission request that omits that is a nudge, not a
            question.

<human>     jarvis_gate. One decision, recorded, with prompt and detail
            NULLed on decision so the queue does not become an unredacted
            twin of the audit log.

run()       Executes an approved plan. `approved` has no default of True.
            A module that can act must not be one call away from acting by
            accident.
```

`backend/jarvis_research.py` is the reference implementation. Its tests patch
`socket.connect` to raise, so "opens no socket" is a fact rather than a
comment. Copy that shape.

### Two rules that are easy to get wrong

**`allowed` is not "a human decided".** `jarvis_gate.check()` returns
`allowed=True` on tier `notify` — reason: *"tier is notify; you were told
after"* — and on `auto` with nobody in the loop. Anything that needs a person
must assert the tier is `ask` or `never`, not trust the boolean.
`skill-notes.patch` shows the pattern.

**Redaction is per-destination.** `jarvis_gate._redact` obeys
`[logging].redact_private_content_in_logs`, which is correct for an on-disk
log and wrong for anything that leaves. A push to a public broker gets
`_safe_detail` instead: keys only, unconditional. Do not reuse a redactor
across destinations with different threat models.

---

## 4. The egress boundary

Three lanes leave the machine. Nothing else may.

| lane | what may go | enforced by |
|---|---|---|
| **cloud model** | user-role turns only | a role filter, re-derived on **every** hop of the degrade loop |
| **ntfy push** | field names only, never values, never while tainted | `_safe_detail` + `taint_active()` |
| **research** | enumerated search terms, per approved plan | `jarvis_research.plan/run` |

The cloud filter deserves a note because it was broken in the least obvious
way: it ran once, above the degrade loop, and the loop could go cloud → local
→ cloud. It now re-derives from the lane it is **about to call**. The loop's
comment claims "downward only" — that is a contract with `jarvis_router` which
the loop never checked, so the fix does not depend on it holding.

The **local model is also egress** if `OLLAMA_URL` does not point at this
machine. The learner asserts loopback before it runs; anything else that talks
to Ollama in the background must do the same.

---

## 5. Memory — one model

```
facts (bi-temporal)  valid_from / valid_to. Nothing is deleted; a superseded
                     fact is retired and the new one records what it replaced.
                     "What is no longer true" is load-bearing.

facts_fts   FTS5, words
facts_vec   sqlite-vec, meaning
            fused by reciprocal rank fusion, with a vector distance floor

proposals   the review queue. Extraction writes here. NOTHING reaches `facts`
            without decide(id, accept) — one integer id, one decision.
```

**Three tables are welded to one local rowid.** `facts` is
`id INTEGER PRIMARY KEY`, `facts_fts` uses `content_rowid='id'`, and
`facts_vec` is `vec0(fact_id INTEGER PRIMARY KEY)`. Any proposal needing
globally-unique ids — sync, sharding, cross-device dedup — is a three-table
migration plus a full re-embed, and `vec0` is a virtual table most extensions
cannot touch. Cost it honestly or design around it.

**The distance floor is inert on first boot.** It sits behind
`self.embedder.semantic`, and until fastembed finishes downloading the
embedder is `HashEmbedder` with `semantic=False`. On day one the tail *is*
padded to `k` on any shared content word.

**Never compress facts or transcripts** with a keep/drop token dropper
(LLMLingua and relatives). They are negation-blind, and this store is
bi-temporal precisely because negation matters. Retrieve less; do not compress
what you retrieve.

### The learner

Runs on one background thread, 45 s after the conversation goes quiet, then
not again for 5 minutes. It reads **user turns only** — the same cut the cloud
lane makes, for the same reason: the assistant turn is a carrier. It restates
injected memory, it quotes tool output, and a Joplin vault read comes back
through it. The vault is kept out of the retrieval corpus on purpose;
extracting facts out of a vault read would undo that one accepted proposal at
a time.

Consequence worth knowing: a turn whose `content` is a list — which is what
the client sends with a screenshot attached — is skipped whole. Safe
direction, deliberate, and the obvious "fix" of flattening content arrays
would immediately admit `tool_result` blocks.

---

## 6. Events — one bus

`jarvis_events.Pump` runs the pollers on one thread; every client learns state
changes from it and from nowhere else. Kinds: `approval`, `proposal`,
`finding`, `power`, `persona`, `model`, `activity`, `appearance`, `hello`.

**Every event is a doorbell.** Count, ids, and what is needed to route —
never content. This bus reaches a phone that surfaces notifications with the
screen off. Clients fetch the authenticated route for the content.

If you add an event kind, add the client handler in the same change. A
doorbell that rings into an empty room is the defect this codebase keeps
producing.

---

## 7. The model

One 8B, resident, nothing else on the card. Full arithmetic, the Modelfile,
the verification step and the second-card analysis are in
[MODEL-TOPOLOGY.md](MODEL-TOPOLOGY.md). Two things belong here because they
are architectural rather than configuration:

- **`num_ctx` cannot be set from the HUD.** It posts to an OpenAI-compatible
  endpoint, which has no field for it. Context length lives on the model or in
  the environment. Left alone, Ollama picks 4096.
- **The recalled-facts block goes late, never at index 0.** At index 0 it
  invalidates the KV prefix cache for the whole conversation every turn, *and*
  suppresses the Modelfile's `SYSTEM` block — which is where the persona
  invariants live. Both from one line. If delimiters are ever added around
  recalled facts, they go on that message, not around the list.

---

## 8. The clients

**Desktop** (`jarvis-desktop/`): Tauri 2, six windows, per-window ACL
capabilities. The Rust commands are the real API — buttons are a courtesy, and
any window holding the capability can call them, so a check that lives only in
the webview is not a check. `decide_approval` consults link staleness in Rust
for exactly that reason.

**Android** (`claude/android-apk-build-q435fi`): Kotlin, native, over
Tailscale. It is a remote, not a second brain. It renders, it decides one
thing at a time, it does not hold its own copy of state.

`jarvis-android` is retired; capabilities port later.

### Talking to the other branch — do this, it keeps going wrong

The two clients are worked by two sessions that **cannot message each other**.
Communication is a committed document. That much was already understood. What
was not: *each session only ever sees its own branch*, so a document written
as a message sits unread on the branch of whoever wrote it, and **silence
looks exactly like being ignored**.

That has now caused four separate misunderstandings in two days:

- The desktop's reply to `CROSS-CLIENT-CONTRACT.md` was written, committed and
  pushed — and recorded on the other side as never read.
- The Android session's `check_parity.py` was wrong about whether
  `/api/appearance` exists **in both directions inside 24 hours**, because it
  was reasoning about desktop source it had not fetched.
- The desktop told the Android session to fetch `/api/approvals`, a route that
  does not exist, from memory rather than from `jarvis_hud.py`.
- The Android session's `SpecDriftTest` compares against its *own* vendored
  copy of the visual spec, so it is structurally incapable of detecting drift
  from the desktop's copy.

Every one of them is the same mistake: making a claim about the other side's
code without fetching it. So:

```bash
# Before writing anything ABOUT the other client, or replying to it:
git fetch origin claude/android-apk-build-q435fi        # from the desktop
git fetch origin claude/jarvis-desktop-tauri-vey6bc     # from the client
git log --oneline origin/<other-branch> -10
git show origin/<other-branch>:docs/<the-doc>.md
```

**Read the other branch before claiming anything about it, and fetch before
concluding a message went unanswered.** A reply you cannot see is not absence
of a reply.

Current cross-branch documents, both directions:

| on the desktop branch | on the client branch |
|---|---|
| `docs/CROSS-CLIENT-CONTRACT-REPLY.md` | `docs/CROSS-CLIENT-CONTRACT.md` |
| `docs/ANDROID-VOICE-FALLBACK.md` | `docs/ANDROID-REPLY-2026-09-15.md` |
| `docs/ARCHITECTURE.md` (this file) | `docs/HANDOFF.md`, `CLAUDE.md` |

One more thing the desktop session can do cheaply and the Android session
cannot: **read that branch's CI logs**. There is no local Android build, so
every check there costs a ~15 minute round trip, while the GitHub API is a
few seconds from here. Offer it rather than waiting to be asked.

**But relay the evidence, not a reading of it.** Fetching those logs resolved
a compile error whose five reported symptoms were all downstream of one
unclosed comment. It also produced the fifth misunderstanding, and this one
was pure relay damage: the desktop passed back a stack trace with the words
*"a timeout inside runBlocking — confirmed, not guessed"* on it. The frame
could not support that. `EventStreamContractTest.kt:103` is the `runBlocking`
line itself, so a timeout, a failed assertion and a thrown exception all
unwind through it identically — and the real cause turned out to be a
`ConcurrentModificationException`. The other session had written that
hypothesis in its own handoff, the desktop repeated it back with added
confidence, and it briefly became settled fact in two places at once.

A frame inside `runBlocking` says where a coroutine was blocked, not why it
failed. The general rule, which is the reason this is in the architecture
document rather than a commit message: **quote the log, and let the side that
owns the code do the diagnosing.** Fetching the other branch catches a stale
file. It does nothing about a claim that was never verified — and confidence
added in transit is indistinguishable, at the far end, from evidence.

---

## 9. Where the backend lives

**Not in this repo.** The owner keeps `jarvis_hud.py`, `jarvis_memory.py`,
`jarvis_gate.py` and the rest on their machine. `backend/` holds **patches**
against them plus the tests that prove the patches do what they claim.
`backend/.gitignore` refuses the sources, because a stale copy in git is worse
than no copy — the next reader would not know which is real.

Eleven patches. They commute (five touch `jarvis_hud.py`, in separated
regions), but `memory-safety` must land first: without it the first accepted
proposal retires a roughly-matching unrelated fact, permanently, and `retire()`
has no way back. `backend/README.md` has the table and a section per patch.

New capability that is a whole module — `jarvis_research.py` — ships as a
file, not a patch, because there is nothing on the owner's machine to patch.

---

## 10. Things that do not exist

Say so rather than designing around imagined code.

- `jarvis_speech.py` — absent, so all four `/api/voice/*` routes are on their
  failure path on every request.
- `jarvis_framework.py`, `jarvis_router.py`, `jarvis_initiative.py`,
  `jarvis_compute.py`, `jarvis_sleep.py` — imported in places, present
  nowhere in anything handed over. Some may exist on the owner's machine.
- The `documents` table — read by two code paths, created by none. The status
  line now says `documents: false`, which is correct.
- A memory review pane. The queue fills; there is no screen to read it on.
  This is the largest gap.

---

## 11. Decisions already taken

Do not relitigate these without new evidence.

| | |
|---|---|
| Reachability | Tailscale, properly. Never a public tunnel. |
| Face / appearance | Rendered locally on each device; the server is a sync channel only. |
| Voice | sherpa-onnx for everything — STT, speaker verification, wake word, Kokoro TTS, Silero VAD. 0 GB VRAM. First audio is 0.5–1.5 s, not 100 ms; design a "thinking" state that survives a second of silence. |
| Cloud / API keys | Allowed, **per use, with permission**. Jarvis works out what it genuinely needs the internet for, explains it, and asks. No standing grant. |
| Structured output | Ollama's native `format: <schema>` — GBNF at the sampler. **Not** `outlines`, which cannot constrain Ollama. |
| Sandbox | Git worktrees, not Docker. |
| Extraction | `ast-grep` — measured 54,490 → 1,088 bytes, 0 VRAM. |

**Rejected, with reasons, so they stay rejected:** screenpipe (relicensed,
captures keystrokes and the a11y tree, telemetry on by default) · moshi
(upstream says 8 GB cards cannot run it) · cr-sqlite (automatic merge breaks
the consent rule — demonstrated on the real binary) · llm-guard (archived
2026-07-09, models abandoned) · cognee and graphrag (~40 deps / three
mandatory Azure SDKs) · LLMLingua (negation-blind) · browser-use (dies at 8k
context by step 2–3) · Phi-4-mini (8B KV cost at 3.8B capability) · kokoro-onnx
the package, though Kokoro the model is adopted via sherpa-onnx.

---

## 12. Before you add anything

1. Does an existing mechanism already do this? The gate, the proposals queue
   and the event bus each get reinvented by roughly every external proposal
   that arrives. Connect to them.
2. Does it have a call site and a surface? If a person cannot see it happen
   and nothing invokes it, it is not finished.
3. Does it act, or leave the machine? Then it is `plan` / `describe` / gate /
   `run`, with the tier asserted.
4. Can you state, in one sentence, what it sends and where? If not, you do not
   know yet.
5. Does it need a test that fails on the unpatched tree? Yes. Every patch here
   has one, and several caught the fix being wrong.
6. Has someone already built it? [`PEERS.md`](PEERS.md) is what twenty
   comparable projects did about memory, approval gates, voice and packaging,
   read from their source. It says what to copy, what to refuse, and where
   Jarvis is behind. Three of the most-recommended projects in this space are
   archived or retired, so check there before adopting a dependency.
