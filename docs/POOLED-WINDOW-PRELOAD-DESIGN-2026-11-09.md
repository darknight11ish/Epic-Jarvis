# The pooled lane's measured window after a cold chat turn — design (recorded OPEN, 2026-11-09)

**Status: implemented and desk-tested; the live field-test row is still to be added.** The page began as a
recorded defect so the next session would start from the measured evidence instead of re-deriving it; it now
also records the fix shape and its proof. The change is internal to the existing chat path: no new route,
card, tier or permission, and the everyday/coding lanes are untouched.

## The defect, as the wave-11 deploy field test measured it

The pooled Coding lane is measured at **49,152 tokens, 0 spill** (Q8 warm: `/api/ps` on 11450, model
`qwen3-coder-30b-a3b-ud-q3-k-xl:latest`, `context_length` 49,152, `size` == `size_vram` == 17,366,494,735 B,
spread over all three cards; `.dsh-scratch/WAVE11-INTEGRATION-2026-11-08/q8-run-20261109-035353/warm-result.json`).

But the **chat path asks for that window in a way Ollama's OpenAI-compatible endpoint ignores.** The deployed
`jarvis_agent.chat_body()` adds `options: {"num_ctx": 49152}` for the pooled lane, and that is what the code
and its pinned test say - yet `/v1/chat/completions` ignores a top-level `options` field. Measured live on the
0.2.441 install, 2026-11-09 04:00 PT: with the 30B unloaded, a `POST /v1/chat/completions` carrying
`options.num_ctx=49152` came back having loaded the model at **`context_length` 8192**. The acceptance's
`lane_spill` row passed only because the Q8 warm's 49,152 load was still resident.

Evidence: `.dsh-scratch/WAVE9-DEPLOY-2026-11-08/run-20261109-033413/WAVE11-RESULT-2026-11-09.md` and
`.dsh-scratch/WAVE11-INTEGRATION-2026-11-08/q8-run-20261109-035353/warm-result.json`. In the register it is
the second finding in **DEF-034**'s open row (the register allows one open defect per file, and that row
already owns `jarvis_agent.py`).

## Why it matters, in plain words

A chat turn that reloads the model (after standby, after a stop, after the lane was unloaded) silently runs at
8,192 tokens instead of the 49,152 the preset documents. It does not crash and does not warn; the answer is
just working from a much smaller window than the settings say. Nothing here was hidden from the measurement:
the acceptance row is scoped to the warmed state, and no row claims the window survives a reload.

## Two shapes, and which one to build first

**(A) Native preload before the turn (recommended first).** Before a pooled-lane chat turn, call Ollama's
native `POST /api/generate` (or `/api/chat`) naming `options.num_ctx = 49152` for the pooled model with no
prompt, exactly the call the Q8 warm and the Q6 harness already proved on this PC (49,152 / 0 spill). The chat
turn then reuses that resident instance. Small, one call, reuses a shape that is measured here; failure must be
said and must not block the turn (the turn still goes, at whatever window Ollama chose, and the page says so).

**(B) Route pooled turns to the native endpoint (bigger).** Send pooled-lane turns to `/api/chat` instead of
`/v1/chat/completions`. Correct by construction, but it touches streaming/tool-call plumbing and every existing
pinned request, so it is not a first slice.

**Do not** simply change the constant: the number is already right in the request; the endpoint is what does
not honour it.

## What the fix must prove (and what the acceptance row must assert)

- After a **cold** pooled chat turn (the model unloaded first), `/api/ps` on the pooled lane reports
  `context_length == 49152`; the acceptance row must assert that, not the warmed state.
- The Q6 measurement's promotion-grade numbers stay unchanged (76.8 tok/s, 0 spill, 6/6) after the change.
- A preload that fails is said in one plain line and the turn still runs.
- Nothing switches, starts, pauses or loads on its own beyond that one warm-up call on the lane the chat is
  already pointed at; the phased lane start and its one card are untouched.
- No new route, card, permission or tier: this is internal to the existing chat path.

## Where the code lives

`backend/jarvis_agent.py` (shipped twin `jarvis-backend/jarvis_agent.py`): `pooled_preload(url, model)` reads
the lane's own `/api/ps` and, only when the pooled model is absent or resident below the lane's configured
window, sends the native `POST /api/generate` with `options.num_ctx` = that window (49,152) and keeps nothing.
`run_local_turn` calls it inside `one_round`, immediately before either `/v1/chat/completions` dispatch, on
every round: once the runner is resident the lane's own `/api/ps` answer makes the next check a read, and
every non-pooled lane returns without a request. `POOLED_PRELOAD_LAST` records the last answer
(`warmed` / `already` / `off` / `failed`), and a failure is said in one plain progress line while the real
turn still goes.

**The proof is `backend/test_pooled_preload.py`** (26 checks, standard library only, a fake Ollama lane on a
random loopback port): a cold pooled turn sends the preload BEFORE the `/v1` turn, with exactly
`{"model": ..., "options": {"num_ctx": 49152}}`; a lane already at 49,152 sends none; a lane at 8,192 - the
cold default the live install measured - is reloaded at 49,152; a preload refused with HTTP 500 is recorded
and said while the real turn still dispatches and answers; and an everyday/coding lane sends nothing and gains
no `options` field. With the seam reverted, 14 of its checks fail. The `jarvis-self-code.json` map is
regenerated with its twin in the same run, as always, because the new suite is a new tracked file.

## The field-test row this acceptance needs

Add ONE row to the field-test register, in the register's own words: **after a COLD pooled turn, `/api/ps`
`context_length` == 49152** - the pooled model unloaded first, then one chat turn, then the lane's own
`/api/ps`; the answer must still have streamed, with 0 spill. The row passes only when driven on this PC with
the model unloaded first; the warmed Q8 run is not this row. `jarvis_agent.POOLED_PRELOAD_LAST` says what the
seam did on that turn (`warmed` / `already` / `failed`), so the field test can report the seam's answer beside
the lane's own.

