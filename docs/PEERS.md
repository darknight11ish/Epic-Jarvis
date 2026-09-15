# What other people built, and what Jarvis should do about it

Two research passes, September 2026. The first asked how comparable projects
gate an agent's actions; the second asked how local-first assistants handle
memory, voice, packaging and phone pairing. Both were told to read source
rather than marketing pages, and both did.

**How to read the confidence labels.** `CONFIRMED` means the claim was read in
the project's own source or in a committed test snapshot. `REPORTED` means it
came from a search summary or a secondary source because the primary page was
unreachable. Nothing here is "I remember reading". Where a page was blocked,
that is said out loud.

Everything below is either a fact about someone else's code or a judgement
about ours. The judgements are marked as such.

**Read [`COMPARISON.md`](COMPARISON.md) next.** This document says what other
people built; that one puts their files beside ours and quotes both. Two of
the recommendations here did not survive that, and they are struck through
below rather than quietly deleted.

---

## Part 1 — Approval gates

Jarvis's central claim is a human approval gate: four tiers
(`auto` / `notify` / `ask` / `never`), `ask` blocks until a person answers one
action with one decision, and **there is no approve-all anywhere**. The
obvious worry is approval fatigue — that the rule is unliveable and every
serious project has already discovered this and backed off.

### The projects

| project | unit of approval | blanket grant? | default |
|---|---|---|---|
| `block/goose` | the tool **name**, arguments not in the key | Always Allow, global, forever | **`Auto` — the gate is off** |
| `cline/cline` | a **category** of tool, global, forever | five toggles, plus YOLO Mode, plus CLI "zen" | five categories auto-approved |
| `openai/codex` | a **structured key** (see below) | only narrow, named ones | `OnRequest` |
| Home Assistant | the **entity**, per assistant | `expose_new` per assistant | curated allowlist |
| OpenHands SDK | typed policy objects | `NeverConfirm` | **`NeverConfirm` — the gate is off** |

### The headline

**All five ship a blanket grant. Not one shipped it because a strict gate
failed — they shipped it because the gate was never on.** goose defaults to
`Auto`. OpenHands defaults to `NeverConfirm`. cline defaults five categories
to auto-approve. There is no post-mortem anywhere in this sample walking back
a no-approve-all rule, because nobody in the sample tried one.

The one real capitulation datum cuts the other way. On 2026-06-25 cline
enabled command auto-approval by default (`923ee3e1`, 15:03) and disabled it
again (`9abd7ae8`, 20:56). **Under six hours.** CONFIRMED from git history.
That is a project discovering that blanket command approval is indefensible
even to itself.

So the rule is unusual but not contradicted. What *is* contradicted is the
implicit assumption that one-action-one-decision is the only safe point on the
curve. Codex shows a defensible middle.

### codex is the best-designed gate of the five

**Its approval key is a structure, not a name.** For running a command the key
is `environment_id + executable + canonicalised argv + cwd + tty +
sandbox_permissions + additional_permissions`. Change the directory, change
the sandbox, change one argument — it asks again. Patching produces **one key
per file path**, so approving a change to `a.rs` approves nothing about
`b.rs`. CONFIRMED, `codex-rs/core/src/tools/approvals.rs`.

**Every escape hatch names its object.** The verbatim option labels:

- `Yes, proceed`
- ``Yes, and don't ask again for commands that start with `git status` ``
- `Yes, and don't ask again for these files`
- `Yes, and allow this host for this conversation`
- `No, and tell Codex what to do differently`

CONFIRMED, `codex-rs/tui/src/bottom_pane/approval_overlay.rs` and a committed
render snapshot. **None of these is an approve-all.** Each is a narrower
`ask` → `auto` reclassification of one named thing. This is the highest-value
idea in the whole report, because it relieves fatigue without touching the
rule.

**It fails closed at the type level.** `impl Default for ReviewDecision`
returns `Denied`. CONFIRMED. And it has a distinct `TimedOut` variant, so
"nobody answered" is its own outcome rather than a hang or a generic refusal.

**It redacts the decision record.** `to_opaque_string()` maps every decision
to a fixed string, dropping the rejection text. Its doc comment admits why a
second serializer was needed: the normal one has to stay lossless for other
consumers. That is the same problem Jarvis's NULL-on-decision solves, solved
at the serializer instead of at the store — and the serializer is the better
place, because it covers every egress and not just the database.

### The one to refuse: the model decides its own gate

- cline's `execute_command` takes a `<requires_approval>` flag **emitted by
  the LLM**. Their docs: *"Cline does not use a fixed allowlist."* CONFIRMED.
- goose's SmartApprove asks a model whether a call is read-only, and trusts
  MCP `read_only_hint` annotations — which the MCP spec itself says clients
  **MUST** treat as untrusted. CONFIRMED on both halves.
- codex's default `OnRequest` is "the model decides when to ask", with the
  sandbox as the real boundary underneath.

**Jarvis does not do this, and it was checked rather than assumed.**
`jarvis_gate.action_for_tool` looks the tool name up in a static table;
`_classify_prompt` is a regex over the prompt text; an unlisted tool becomes
`unclassified_tool` and an unlisted action resolves to `UNKNOWN_TIER`, which
is `ask`; a tier value that is not one of the four valid strings is coerced to
`never`, not to something permissive. Arguments can only make the answer
*stricter* — a shell blob matching `_SHELL_NEVER` is re-pointed at
`open_public_tunnel` or `post_to_external_service` regardless of the tool's
own tier. No model output reaches any of it.

### Home Assistant gates nouns, not verbs

HA has **no per-action approval at all**. It gates which entities an assistant
can see, then lets it act on them freely. That is the mature, widely-deployed
design, and it is the opposite axis from Jarvis's.

The interesting part is the default list. `DEFAULT_EXPOSED_DOMAINS` contains
climate, cover, fan, humidifier, light, media_player, scene, switch, todo,
vacuum, water_heater. **`lock` and `alarm_control_panel` are absent.** Lock
*state* is readable as a sensor; lock *control* is not exposed. CONFIRMED.
That is Jarvis's `never` tier implemented as a shipped default the owner opts
out of individually, rather than a list each deployment assembles.

Their generic exclusion rule is worth copying too: anything with an
`entity_category` or `hidden_by` — anything the UI already treats as plumbing
— is not assistant-reachable.

**One hazard to refuse.** `async_should_expose` writes its computed answer
back into the registry, so the first evaluation freezes into a persisted
grant and a later policy change never reaches entities already evaluated.
CONFIRMED. If Jarvis caches anything, cache the *decision*, never the
*policy evaluation*.

### Two smaller finds

- **goose built the record Jarvis describes and never wired it up.**
  `ToolPermissionStore` keys on `tool_name:blake3(arguments)`, carries an
  `expiry`, and runs `cleanup_expired()` on load. It is dead code — the only
  reference outside its own file is a `pub use`. CONFIRMED by grep. It also
  persists `readable_context` — the full human-readable request, cleartext,
  on disk, unredacted. Jarvis's NULL-on-decision is the opposite choice, and
  goose's unused implementation is what the other choice looks like.
- **goose suppresses "Always Allow" when the request carries free text.**
  `{!prompt && <Button …always_allow>}`. CONFIRMED. Someone decided a
  standing grant is unsafe when the request is prose. Good instinct.

### A real incident caused by a standing grant

Between 2025-12-21 and 2026-02-09 cline's own repository ran a GitHub Action
on every new issue with a broad tool allowlist and the attacker-controlled
issue **title** interpolated into the prompt. Result: cache poisoning and an
unauthorised `cline@2.3.0` published for about eight hours. REPORTED (three
independent write-ups; the primary incident report was reachable, the vendor
post-mortem was not). The mechanism is exactly a standing grant plus no
interactive human.

### On approval fatigue as evidence

"Approval fatigue" is a named trap in the literature, but **the paper is
egress-blocked and every circulating statistic traces back to blog summaries
that could not be checked against a primary source. Do not cite numbers from
it.** The load-bearing evidence in this report is cline's six-hour walk-back,
the defaults in goose and OpenHands, and cline Discussion #1056 ("Allow
auto-approve: everything"), whose stated reason is latency.

---

## Part 2 — Local-first assistants

### Activity, verified 2026-09-15

| project | licence | last release | state |
|---|---|---|---|
| khoj-ai/khoj | AGPL-3.0 | stable **1.42.10, 2025-07-15** | **dying**; cloud shut down Apr 2026 |
| janhq/jan | Apache-2.0 | v0.8.4, 2026-07-23 | healthy |
| home-assistant/core | Apache-2.0 | 2026.9.2, 2026-09-11 | healthy |
| OpenVoiceOS/ovos-core | Apache-2.0 | 3.5.6a1, 2026-09-13 | alive, **alpha tags only**, 288 stars |
| MycroftAI/mycroft-core | — | — | **archived 2024-09-08** |
| rhasspy/rhasspy, rhasspy3 | MIT | — | **both archived 2025-10-06** |
| open-webui/open-webui | BSD-3 **+ branding clause** | 0.11.3, 2026-08-31 | healthy, **not OSI open source** |
| letta-ai/letta (Python) | Apache-2.0 | 0.16.8, **2026-05-14** | **retired to an `archive` branch** |
| letta-ai/letta-code (TS) | Apache-2.0 | 0.32.10, 2026-09-14 | healthy |
| mem0ai/mem0 | Apache-2.0 | 2.0.20, 2026-09-02 | healthy |
| getzep/graphiti | Apache-2.0 | 0.30.2, 2026-09-08 | healthy |
| k2-fsa/sherpa-onnx | Apache-2.0 | 1.13.8, 2026-09-10 | healthy |

Three of the projects most often recommended for this space are effectively
dead for our purposes. **The "mature local voice loop" no longer exists as an
independent thing** — Mycroft and both Rhasspy repos are archived and the
effort went into Home Assistant's Wyoming/Assist stack. Study Assist.

### Nobody else reviews memory before writing it

This was the thing to check, and the answer is clear.

- **Khoj** asks the model for `create` and `delete` lists and applies them
  straight to the database in a background call with no user in the loop.
  `delete_memory` is a hard row delete; `UserMemory` has no validity
  interval and no tombstone. Its own prompt says: *"You cannot update
  existing facts directly, instead create new facts and delete related
  existing ones."* CONFIRMED from source. So Khoj's "supersede" is literally
  "a model decided that was no longer true, so the row is gone."
- **Open WebUI** `apply_memory_operations` takes LLM-proposed add / replace /
  move / remove and applies them immediately; `remove` is a real delete.
  CONFIRMED.
- **mem0** `add()` writes directly. CONFIRMED.
- **Letta** memory blocks are rewritten by the agent itself.

The only counter-example is supermemory's *hosted* review API, which is not in
its open-source repo and could not be verified. REPORTED only.

And the cost of going without shows up in their issue trackers. Open WebUI
#18603 asks for memory to be disableable per agent because *"some agents are
indiscriminately using information stored in memory without being asked to do
so"*. CONFIRMED the issue exists and says that. Meanwhile Open WebUI v0.11.1
(2026-08-25) shipped a per-call human approval queue **for tools** — one call
at a time, decision remembered per conversation — and left memory unguarded.

**Judgement: Jarvis is early here, not wrong.**

### mem0 threw away UPDATE and DELETE, and gained twenty-one points

This is the most useful single finding in Part 2. From mem0's README, "New
Memory Algorithm (April 2026)":

> **Single-pass ADD-only extraction — one LLM call, no UPDATE/DELETE.
> Memories accumulate; nothing is overwritten.**

Plus time-aware retrieval that ranks the right dated instance, and multi-signal
retrieval fusing semantic, BM25 keyword and entity matching. They report
LoCoMo 71.4 → 92.5 and LongMemEval 67.8 → 94.4. **Their own caveat, quoted:**
scores reflect the managed platform, which includes proprietary optimisations
not in the open-source SDK — so treat the numbers as directional.

The most-benchmarked memory layer in the field tried LLM-driven update and
delete, and replaced both with append-only accumulation plus ranking at
retrieval time. That is a different route to the same destination as Jarvis's
retire-don't-delete, and it independently validates the hybrid FTS5 + vector +
RRF design.

What mem0 keeps is an *audit log* (`history` table: `old_memory, new_memory,
event, is_deleted`), not bi-temporal storage. You can see that a fact changed;
you cannot ask what the store believed on a given date.

### getzep/graphiti: Jarvis is only half bi-temporal

This is the project that answers "is bi-temporal over-engineering?" — no, and
here is someone shipping it. `EntityEdge` carries four datetimes, CONFIRMED
from `graphiti_core/edges.py`:

```
created_at    when we wrote it down          (transaction time)
expired_at    when we stopped believing it   (transaction time)
valid_at      when the fact became true      (valid time)
invalid_at    when the fact stopped being true (valid time)
```

**Jarvis has `valid_from` / `valid_to` — valid time only.** The missing axis
matters for exactly the case Jarvis is built for: *"I told it in March that I
moved in January."* One axis cannot represent a late-accepted review-queue
item or a retroactive correction.

**Do not adopt Graphiti itself.** `neo4j>=5.26.0` is a required dependency;
the backends are Neo4j, FalkorDB, Neptune and OpenSearch; the embedded Kuzu
option carries a comment saying upstream is unmaintained and the extra will be
removed. CONFIRMED from `pyproject.toml`. Copy the schema, not the dependency
tree.

### Home Assistant's voice pipeline is a specification, not a feature

Four stages — wake word → speech to text → intent → text to speech — driven by
**one** WebSocket call, `assist_pipeline/run`, with `start_stage` and
`end_stage` parameters. Text-only, STT-only and TTS-only are the same API with
different endpoints. Fourteen named events including `stt-vad-start` /
`stt-vad-end` and an `intent-progress` carrying a streaming delta. A **closed
error-code vocabulary** of twelve: `wake-engine-missing`,
`wake-provider-missing`, `wake-stream-failed`, `wake-word-timeout`,
`stt-provider-missing`, `stt-provider-unsupported-metadata`,
`stt-stream-failed`, `stt-no-text-recognized`, `intent-not-supported`,
`intent-failed`, `tts-not-supported`, `tts-failed`. Audio rides the same
socket as binary frames. CONFIRMED from the docs repo source.

Writing our own stage machine for task #27 is pure cost. Take this contract
first.

Their consent surface is worth copying too — a dedicated Settings → Voice
assistants → Expose tab, per entity, per assistant, with the reason stated in
the docs: *"to avoid that sensitive devices, such as locks and garage doors,
can inadvertently be controlled by voice commands."* A curated default-deny
list, not a stream of prompts.

**Not found in HA core: any speaker verification or voice-print
identification.** Searched and found only community add-ons. Marked as a
weak negative — absence of evidence. If it holds, the sherpa-onnx speaker
verification planned for #27 puts Jarvis ahead of the most widely deployed
local voice assistant there is, and for a single-owner assistant that gates
memory writes, "is this actually the owner speaking" is load-bearing rather
than a gimmick.

### janhq/jan: the same shell, three rewrites ahead of us

Jan is Tauri 2 + llama.cpp, which is our stack. It has already made the
mistakes.

- **Electron → Tauri**, issue #4485, closed Done. Stated reason: app size, and
  Electron "not suitable for scaling to mobile platforms."
- **Nitro → Cortex.cpp → plain llama.cpp**, issue #4941. The benefit that
  matters here, quoted: *"Smaller app size + faster cold start (inference
  engine is not ship with the app anymore)."*
- **localStorage → backend store + OS keyring**, v0.8.4. Provider credentials
  used to live in the webview's `localStorage`; they now go to the OS keyring.

**The small-GPU walk-back, quoted from their source:**

> `/// The GPU-layers value the old UI shipped as its default. v1 of the`
> `/// backfill copied it into every model.yml, which pins offload to 100`
> `/// layers and defeats llama.cpp's own -1 (auto, VRAM-aware) -- an OOM on`
> `/// a small GPU. v2 removes it again.`

They shipped a hardcoded `n_gpu_layers: 100`, OOM'd small GPUs, and had to
write a migration sweeping every config file to delete it. **Lesson: do not
pre-compute a layer count. Let the engine auto-fit, store nothing unless the
owner deliberately overrode it, and make the override removable.**

**Silent CPU-spill detection**, from `readiness.ts`:

> `/* A GPU present in hardware but absent from the engine's device list means`
> ` * layers silently run on the host: llama.cpp's layer fit puts everything`
> ` * on the CPU and the engine still reports healthy. Comparing the two`
> ` * counts is the only signal that offload never happened. */`

It compares hardware GPU count against engine device count and emits a
warning. Coarse — it catches "zero GPU", not partial spill. On a 6.9 GB
budget this is the difference between "Jarvis is slow today" and "Jarvis is on
the CPU and nobody told you", and we do not have it. Ollama has the same
silent failure and gives no warning either (REPORTED: ollama#7629, #3837 —
not opened, search summaries only).

**Packaging decisions, all CONFIRMED from `tauri.conf.json`:** `bundle.resources`
contains only the licence file — no model, no engine, in the installer; a
minisign updater pubkey with **two** endpoints, the second being GitHub
releases `latest.json` as a free fallback if your own server dies;
`windows.installMode: "passive"`; `createUpdaterArtifacts: false` (CI makes
them); and an explicit first-run download consent key.

**Not verified:** what Jan's "Auto Optimize" actually tunes. Their site is
blocked and the release notes say only "add label experimental". Do not cite
it as a design.

### open-webui: take the screen, refuse the model, mind the licence

**Licence first.** MIT (2023) → BSD-3 (2025) → current BSD-3 **plus a clause
prohibiting altering or removing "Open WebUI" branding**, except where total
end users stay under 50 in any rolling 30 days, or with written permission, or
under an enterprise licence. Contributions require a CLA. CONFIRMED by reading
the files. **This is not OSI open source.** Fine to run; you cannot lift its
UI code into a rebranded app.

**The screen is the reference implementation of what we just built.**
`Personalization.svelte`: list, live text filter over content and namespace,
per-row edit in a modal, delete one, delete all, and an explicit
"experimental" badge. Two ideas we should take: their `type` field
distinguishes `'user'` (you wrote it) from `'context'` (extracted) — a
provenance flag every Jarvis fact should carry — and `path` gives memories a
folder-like namespace.

### Pair the phone the way Syncthing does

Syncthing generates an Ed25519 keypair and a self-signed cert at first start;
the device ID is the **base32-encoded SHA-256 of the certificate in DER form**,
so the ID *is* the key. Both ends must add each other's ID explicitly. No
server, no account, and a human-comparable string. CONFIRMED from their docs
source. LocalSend adds the right first-contact UX on top: multicast discovery,
device fingerprint = SHA-256 of the TLS cert, and an optional short PIN.

The recommendation for task #20: do this **inside** Tailscale, not instead of
it. Tailscale authorises the network path; a pinned device cert authorises the
peer. Tailnet membership should not be the only thing between a device and the
memory store.

---

## What Jarvis is already ahead on

Stated as judgements, with the evidence above.

1. **The human-reviewed memory queue appears to be unique** among comparable
   projects. Every peer whose source was read writes what the model proposes,
   immediately.
2. **Nothing is deleted.** mem0 independently arrived at "memories accumulate;
   nothing is overwritten" in April 2026. Graphiti invalidates rather than
   deletes. Khoj hard-deletes and the row is gone forever.
3. **Tier assignment is deterministic code.** Three of the five gate projects
   let a model decide, in whole or in part. Jarvis does not, and this was
   verified in `jarvis_gate.py` rather than assumed.
4. **No approve-all, and the research did not find a reason to add one.**
5. **Speaker verification**, if #27 ships it, would be ahead of Home Assistant.
6. **The whole-stack local posture.** Letta's active codebase wants API keys.
   Khoj's cloud is gone. Open WebUI restricts rebranding. None of these
   projects could meet Jarvis's no-keys / no-tunnel / one-owner constraints.

## What Jarvis is probably getting wrong

1. **The gate is enforced in more places than have been audited, and two have
   already been found.** The webview-vs-Rust staleness split, and
   `gate-push.patch` — where `_redact`'s own docstring stated the rule, the
   local audit log honoured it, and `_push` sent the identical dict to an
   unauthenticated ntfy.sh topic, on the `notify` tier where by construction
   no human is watching. That is three copies of "what may leave the machine"
   and they disagreed. **Enumerate every site the gate is consulted and add a
   test per site.** The Android companion is the one to look at first: a
   second UI, on a second device, over a network, and nothing in this research
   suggests anyone has solved a two-client approval queue well.
2. **`notify` is a tier nobody else has.** goose has three levels, OpenHands
   three policies, HA a boolean, codex a policy enum. That is either a genuine
   innovation or an under-tested tier — and the first real bug found in
   Jarvis's gate was on the notify path. `ask` fails loudly; `notify` fails
   silently. Spend audit effort there.
3. **Redaction belongs at the serializer, not the store.** NULLing the
   database column does nothing for the copy already in the SSE buffer, the
   Tauri IPC log, or on the phone. codex needed a second, deliberately lossy
   serializer for exactly this reason.
4. **Timeout is not a distinct outcome.** `jarvis_gate` returns
   `Verdict(False, tier, action, "nobody answered in time, so it was
   refused")` — the reason string differs but the decision does not. codex has
   a `TimedOut` variant. "The human said no" and "the human was asleep" need
   different retry, notification and audit treatment.
5. **These docs will become the next copy that is wrong.** cline's
   `auto-approve.mdx` still documents three toggles the UI stopped rendering
   in June — same repo, both shipped. "No approve-all anywhere" is prose about
   code. **Make it a test:** assert that no path can take an `ask` action to
   executed without a matching single decision record.
6. **The volume is measurable and has not been measured.** None of these
   projects can say what Jarvis's approval load actually is. We can: count
   `ask` prompts per day and group repeats by (action, canonicalised detail).
   If the tail is a handful of identical repeats, the structured key below
   removes most of the fatigue without touching the rule. If it is a long tail
   of genuinely distinct actions, the fatigue argument does not apply to us.
   Right now the absolute is being defended against a hypothetical, and the
   answer is a `GROUP BY` away.

---

## What to do, ranked

Ordered by value per unit of work. Each names the task it belongs to where one
exists.

1. ~~**Add the second time axis**~~ — `retired_at` alongside `valid_from` /
   `valid_to`, as graphiti does. **Done**: `bitemporal.patch`, with
   `known_at()`, a `?known_at=` route and a "What did you know on…" button.
2. **Take Home Assistant's pipeline contract before writing voice code** — one
   call with `start_stage` / `end_stage`, the named event sequence, the twelve
   closed error codes. (task #27)
3. **Build Jan's GPU-offload readiness check**, and go one better by reporting
   partial spill, not just "no GPU at all". (task #22)
   The *other* half of that same file — `evaluateEmbeddingVector` — turned out
   to apply to code we already have, and is now `embedding-guard.patch`. Our
   `FastEmbedder.embed` had no finite check and no zero check, and `_pack`
   takes NaN without complaint. **Done.**
4. **Never compute `n_gpu_layers` ourselves.** Let the engine auto-fit; store
   nothing unless the owner overrode it; make the override removable.
   (task #25, already decided — this confirms it)
5. **Enumerate the gate's enforcement sites and add a test per site**, plus
   the invariant test that no path reaches executed without a decision record.
   The invariant test exists now
   (`test_gate_outcome.t_there_is_still_no_approve_all`) **and it found a real
   approve-all on its first run** — `confirm_auto()` granted every `ask`
   action with nobody asked. See `no-auto-approve.patch`. The per-site
   enumeration is still open.
6. **Move redaction to the serializer** for every egress.
7. ~~**Add a distinct `TimedOut` decision**~~ — **done**, `gate-outcome.patch`.
   `Verdict.outcome` now distinguishes six endings and defaults to `refused`,
   codex-style, so a forgotten field fails closed.
8. ~~**Add a provenance flag to every fact**~~ — Open WebUI's
   `type: 'user' | 'context'`. **Already there**: `source` is one of `user`,
   `extracted`, `edited` or `legacy`, and the Memory pane renders it as
   "from extracted". Verified in the code, not assumed.
9. **Measure the approval volume** before arguing about fatigue again.
10. **Syncthing-style device identity inside Tailscale** for phone pairing.
    (task #20)
11. ~~**Copy Jan's packaging decisions.**~~ **Withdrawn after actually
    comparing the two config files** — see [`COMPARISON.md`](COMPARISON.md)
    §2. We already ship no model and no engine, already use
    `installMode: "passive"`, and already point the updater at the GitHub
    `latest.json` that is Jan's *fallback*. And our CSP is considerably
    stricter than theirs: Jan allows `https: http:` in `connect-src` (every
    host), `assetProtocol` `**/*` (every file on disk) and two telemetry hosts
    in `script-src`; we allow four loopback ports, no file access and no
    telemetry. The one real gap is our empty updater `pubkey`, which
    `INSTALL.md` already lists. This entry is left in place rather than
    deleted because "the research said copy it, the code said we already had
    it" is the kind of thing worth remembering about research.
12. **If the no-approve-all rule ever bends, bend it codex's way**: a
    structured key where anything different still asks, every option naming
    its object, an expiry from day one, and no caching at all when the request
    carries free text (goose's rule). **This is not currently planned and the
    research gives no reason to do it.** It is written down so that if the
    owner ever asks, the answer is a design rather than a capitulation.
13. **Two small correct decisions from Khoj**: stamp each memory with its date
    when injecting it into the prompt, and never run extraction on scheduled
    or automated turns.

## What to refuse

1. **The model deciding its own gate.** Tier assignment stays deterministic
   code over the action's structure, on the Python side of the boundary.
2. **A YOLO mode, including a hidden one.** cline needed an enterprise kill
   switch to undo theirs, and the Clinejection incident is what a standing
   grant plus untrusted input costs.
3. **HA's write-back memoization.** Cache the decision, never the policy
   evaluation.
4. **Adopting Graphiti, Letta's Python server, or Khoj as dependencies.**
   Graphiti needs Neo4j; Letta's Python server is retired to an `archive`
   branch; Khoj's last stable release is fourteen months old and its cloud is
   shut down. Anyone proposing "use Letta's memory server" is proposing
   archived software.
5. **Lifting Open WebUI's UI code.** Its licence prohibits removing the
   branding above 50 end users. The screen's *design* is free to copy.

---

## Things neither pass could verify

Listed so nobody later mistakes a gap for a finding.

- The *AI Agent Traps* paper's actual contents — SSRN and arXiv both blocked.
  Every circulating approval-fatigue statistic traces back to blog summaries.
- OpenHands' user-facing approval UX and documented default (docs blocked);
  only the SDK's typed policies and `NeverConfirm` default are from source.
- Whether goose's `ToolPermissionStore` was ever wired up historically — the
  clone is shallow, so it is confirmed dead at HEAD but not when it died.
- What Jan's "Auto Optimize" tunes.
- Khoj's shutdown reasoning in primary form; the shutdown itself is
  corroborated by the deprecated app page and release notes.
- Supermemory's review / approve / decline / undo API — secondhand only, and
  it appears to be a hosted-platform feature rather than open source.
- Letta's core-memory block semantics from primary docs.
- Home Assistant's companion-app pairing and token flow from primary docs.
- Whether Home Assistant has *any* speaker identification. Searched, found
  none in core; this is a weaker claim than the others.
- The Ollama VRAM-estimation issues (#7629, #3837) — search summaries only.

### Licences, for anything borrowable

goose, cline, codex, home-assistant/core, jan, ovos-core, mem0, graphiti,
sherpa-onnx: Apache-2.0. Rhasspy, LocalSend protocol, supermemory: MIT. Khoj
and superlocalmemory: AGPL-3.0. Open WebUI: BSD-3 plus a branding clause —
**not OSI open source**. OpenHands SDK: **not verified** — ideas only until
someone checks.
