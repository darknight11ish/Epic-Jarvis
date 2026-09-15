# Jarvis next to the others, file by file

[`PEERS.md`](PEERS.md) is what other projects built. **This** is what changes
when you put their code beside ours and read both.

Their side is quoted from files fetched on 2026-09-15 and named below. Our
side is quoted from this repo. Where the two disagree with what PEERS.md
recommended, the code wins and it is called out — a research report that never
opened our config can only compare us to its idea of us.

Sources pulled for this comparison:

```
janhq/jan          src-tauri/tauri.conf.json
                   extensions/llamacpp-extension/src/readiness.ts
getzep/graphiti    graphiti_core/edges.py
open-webui         backend/open_webui/models/memories.py
mem0ai/mem0        README.md
home-assistant     developers.home-assistant  docs/voice/pipelines/index.md
                   core  homeassistant/components/homeassistant/exposed_entities.py
openai/codex       codex-rs/core/src/tools/approvals.rs
```

---

## The scorecard

| | Jarvis | best peer | who is ahead |
|---|---|---|---|
| memory reviewed before writing | **yes**, one fact one decision | nobody | **us** |
| memory deleted | never | Khoj and Open WebUI hard-delete | **us** |
| time axes on a fact | 4 (since this week) | 4 (graphiti) | level |
| retrieval | FTS5 + vector, RRF | same (mem0) | level |
| approval gate | 4 tiers, no approve-all | codex's structured key | **codex, on repeats** |
| gate decided by the model | no | 3 of 5 peers do it | **us** |
| voice pipeline | **nothing** | Home Assistant Assist | **them, by a mile** |
| GPU offload check | **nothing** | Jan | **them** |
| embedding validation | **nothing** | Jan | **them** |
| webview CSP | fixed loopback allowlist | Jan allows `https: http:` | **us** |
| asset protocol | disabled | Jan allows `**/*` | **us** |
| telemetry in CSP | none | Jan allows posthog | **us** |
| updater | **no signing key** | Jan: minisign + 2 endpoints | **them** |
| phone pairing | shared token | Syncthing: cert-derived ID | **them** |

---

## 1. Memory — where we are genuinely alone

**Open WebUI, `models/memories.py`, read today.** Its `apply_memory_operations`
takes what the model proposed and applies it, and `remove` is a real delete:

```python
await db.delete(memory)
results.append({'action': action, 'status': 'deleted', 'id': memory_id})
```

The table it deletes from has no validity interval and no tombstone:

```python
id, user_id, type, path, content, meta, created_at, updated_at
```

**Ours, `jarvis_memory.py` after `bitemporal.patch`:**

```
id, text, source, created, valid_from, valid_to, retired_at,
retired_by, embedded, meta
```

and there is no `DELETE FROM facts` anywhere in the module. `retire()` is an
`UPDATE`.

**What to take from them anyway:** their `type` column is `'user'` or
`'context'` — who said it, you or the extractor. We have that already as
`source` (`user` / `extracted` / `edited` / `legacy`) and the pane renders it
as "from extracted". Nothing to build. Their `path` column gives memories a
folder-like namespace, which we do not have and do not yet need.

### mem0 reached our conclusion from the other direction

Quoted from their README, section "New Memory Algorithm (April 2026)":

> **Single-pass ADD-only extraction** — one LLM call, no UPDATE/DELETE.
> Memories accumulate; nothing is overwritten.
>
> **Multi-signal retrieval** — semantic, BM25 keyword, and entity matching
> scored in parallel and fused.

LoCoMo 71.4 → 92.5, LongMemEval 67.8 → 94.4. **Their own caveat, quoted
verbatim so nobody repeats the number as ours:** *"Scores reflect Mem0's
managed platform, which includes proprietary optimizations not available in
the open-source SDK; open-source users should expect directionally similar
gains but not identical numbers."*

The most-benchmarked memory layer in the field tried letting an LLM update and
delete, threw both away, and went append-only with ranking at retrieval time.
That is our design, arrived at independently, and the retrieval half —
semantic plus keyword, fused — is what `facts_vec` + `facts_fts` + RRF already
does.

### graphiti — the gap we just closed

`graphiti_core/edges.py`, the four fields, read today:

```python
created_at: datetime            # line 54
expired_at: datetime | None     # line 271
valid_at:   datetime | None     # line 274
invalid_at: datetime | None     # line 277
```

We had two of the four. As of `bitemporal.patch` we have all four, under our
own names (`created` / `retired_at` / `valid_from` / `valid_to`), and
`MemoryStore.known_at()` is the query they buy.

**Do not adopt graphiti itself.** Its `pyproject.toml` requires
`neo4j>=5.26.0`; the embedded alternative carries a comment saying upstream is
unmaintained and the extra will be removed. We copied the schema and left the
database server.

---

## 2. Packaging — where the earlier report was wrong about us

PEERS.md recommendation 11 said "copy Jan's packaging decisions". Putting the
two config files side by side, **most of it we already do, and on two counts
we are considerably stricter than Jan.**

### What Jan's webview may reach

```json
"connect-src": "'self' asset: ipc: data: ... https: http:",
"script-src":  "'self' 'unsafe-eval' ... https://eu-assets.i.posthog.com https://posthog.com",
"assetProtocol": { "enable": true, "scope": { "allow": ["**/*"] } }
```

`https: http:` in `connect-src` is every host on the internet. `assetProtocol`
with `**/*` is every file on disk. And there is telemetry in the script
allowlist.

### What ours may reach

```json
"connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:4719
             http://localhost:4719 http://127.0.0.1:11434 http://127.0.0.1:4000"
"assetProtocol": { "enable": false, "scope": [] }
```

Four loopback ports, no wildcard, no file access, no telemetry host, plus
`frame-src 'none'`, `object-src 'none'`, `form-action 'none'` and
`freezePrototype`, none of which Jan sets. **For a project whose first
invariant is "nothing leaves the machine", this is the config doing the
enforcing, and it is already right.**

### What they do better

| | Jan | us |
|---|---|---|
| model or engine in the installer | no — `resources: ["resources/LICENSE"]` | no — notices file only |
| updater signing key | a minisign pubkey | **`"pubkey": ""` — the updater is inert** |
| updater endpoints | 2: their own, then GitHub `latest.json` | 1: GitHub `latest.json` |
| Windows install mode | `passive` | `passive` |
| `createUpdaterArtifacts` | false, CI makes them | false |

So: one real gap, the empty `pubkey`, which `INSTALL.md` already lists as a
known rough edge. The second endpoint is a non-issue — Jan's *fallback* is the
free GitHub one, which is the only one we have.

**Corrected verdict:** copy nothing from Jan's packaging except a signing key
when there is one. Do not copy their CSP; ours is better.

---

## 3. GPU offload and embeddings — two real gaps, and Jan's code fits

`readiness.ts`, quoted:

> A GPU present in hardware but absent from the engine's device list means
> layers silently run on the host: llama.cpp's layer fit puts everything on
> the CPU and the engine still reports healthy. **Comparing the two counts is
> the only signal that offload never happened.**

We have nothing like this. On a 6.9 GB budget it is the difference between
"Jarvis is slow today" and "Jarvis is on the CPU and nobody told you", and
Ollama gives no warning either. Their version only catches *zero* GPU; ours
should also report partial spill. → task #22.

The second half of that file is more immediately relevant, and it found
something in our code:

```ts
// Cosine similarity divides by the vector norm, so an all-zero embedding
// makes every score NaN rather than merely inaccurate.
if (vector.every((value) => value === 0)) {
  return { ok: false, dimension, problem: 'degenerate' }
}
```

**Ours, `jarvis_memory.FastEmbedder.embed`, in full:**

```python
def embed(self, texts):
    return [list(map(float, v)) for v in self._m.embed(list(texts))]
```

No finite check, no zero check. `_pack` will `struct.pack` a NaN into `vec0`
without complaint. `HashEmbedder` is safe — it normalises with
`or 1.0` and always sets at least one bucket — but the real embedder is
unvalidated. See `embedding-guard.patch`.

---

## 4. Voice — we have nothing and they have a specification

Home Assistant runs one WebSocket call, `assist_pipeline/run`, with
`start_stage` and `end_stage` each drawn from a four-value enum, so text-only,
STT-only and TTS-only are the same API. Quoted from their docs source:

> `start_stage` — Required. The first stage to run. One of `wake_word`, `stt`,
> `intent`, `tts`.

Twelve named error codes, including ones we would certainly have invented
badly:

```
wake-engine-missing        stt-provider-missing        intent-not-supported
wake-provider-missing      stt-provider-unsupported-metadata   intent-failed
wake-stream-failed         stt-stream-failed           tts-not-supported
wake-word-timeout          stt-no-text-recognized      tts-failed
```

Plus the detail that saves battery on a phone:

> Clients should avoid unnecessary audio streaming by using a local voice
> activity detector (VAD) to only start streaming when human speech is
> detected.

and `wake_word_phrase` passed back "to avoid multiple device wake-ups", which
is the desktop-and-phone-both-listening problem we will have on day one.

**Take this contract before writing any voice code.** → task #27.

---

## 5. The approval gate

codex's key, from `approvals.rs`: a struct of environment, executable,
canonicalised argv, cwd, tty and sandbox permissions — so an identical repeat
stops asking and anything different still asks, and `apply_patch` gets one key
per file path.

Ours asks every time. That is not wrong; it is a different point on the curve,
and no peer has evidence that ours is unliveable — see PEERS.md for why (all
five shipped a blanket grant without ever turning their gate on).

**Where we are clearly ahead:** three of the five let the model decide its own
gate. `jarvis_gate.action_for_tool` is a static table, `_classify_prompt` is a
regex, unknown resolves to `ask`, an invalid tier coerces to `never`, and
arguments can only make the answer stricter.

**Where Home Assistant is ahead, and it is not about approvals at all:**
`DEFAULT_EXPOSED_DOMAINS` omits `lock` and `alarm_control_panel` entirely
while exposing lock *state* as a read-only sensor. A curated shipped default
the owner opts out of, rather than a list each install assembles.

---

## What this comparison actually changed

1. `bitemporal.patch` — the two missing time axes, from graphiti. **Done.**
2. `embedding-guard.patch` — validate a vector before it is stored, from Jan's
   `evaluateEmbeddingVector`. **Done.**
3. Packaging: **do not** copy Jan's CSP. Corrected in PEERS.md.
4. GPU offload readiness, folded into task #22.
5. The Assist pipeline contract, folded into task #27.
