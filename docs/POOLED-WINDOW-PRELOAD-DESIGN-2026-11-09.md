# The pooled lane's measured window after a cold chat turn — design (recorded OPEN, 2026-11-09)

**Status: recorded defect, not fixed and not claimed.** This page is the design item Gemini's Q1 order put
first in Wave 13; it exists so the next session starts from the measured evidence instead of re-deriving it.
Nothing here changes any code, card or tier.

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

## Where the code would live (when it is built)

`backend/jarvis_agent.py`'s pooled-lane request path (`chat_body`'s own `options` block) plus its shipped twin;
`jarvis-backend/jarvis_agent.py`. Tests in `backend/test_lane_integrity.py` (which already owns the Q5/Q6
window evidence) with a fake native endpoint, plus the live acceptance row above. The `jarvis-self-code.json`
map is regenerated LAST, as always.
