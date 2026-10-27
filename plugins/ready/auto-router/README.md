# auto-router

Estimates what a turn will COST on this PC, and advises when a cloud lane
would be quicker.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out. Copy this
folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name auto-router`) and restart Jarvis.

- Module the loader calls: `jarvis_auto_router.install()` - called with **no
  arguments**, because this manifest says `install: "none"`
- The patch this replaces: none
- Position in the loader's order: 148, after the highest folder already there
  (`skill-hub` at 145, `voiceprint` at 146 and `receipts` at 147)

## The one sentence that matters

**This module ADVISES. `jarvis_router.choose()` DECIDES.**
(`backend/rebuilt/jarvis_router.py:590`.)

`choose()` is the single authority on which lane answers a turn, its nine gates
run in a fixed order, and every one of them can only move the answer *downward*,
toward local. `evaluate_route()` is a second opinion about cost and never a
second permission: it asks `choose()` directly (through
`_router_allows()`), and any gate `choose()` refuses on is its answer too. It is
therefore strictly weaker than the authority it advises about, which is what
makes a second entry point safe. A parallel gate stack in this position would
be the exact failure `jarvis_router.py:632-648` describes - a privacy decision
with two sources of truth, and so a gate nobody can see.

## It serves no route, on purpose

`install: "none"` means the loader imports the module, calls `install()` with no
arguments, and prints its one banner line. **No route is added and nothing about
a live turn changes.** That is deliberate:

- nothing new is reachable, so there is no new permission surface to review;
- the module cannot be hooked into a chat turn by accident - adding a caller is
  a separate change with its own review;
- no `docs/JARVIS-API.md` entry, and no `tools/check_parity.py` classification,
  is owed for a route that does not exist.

## What it returns

`evaluate_route(prompt, context_tokens=0, active_project=None, speed_stats=None)`
gives a plain dict. `lane` is `"local"` or `"jarvis-escalate"`; `recommended` is
true only for the second; `advisory` is
always true. A recommendation always carries `would_send` - the **scrubbed**
text, and the only text the advice covers. The raw `prompt` is never handed back
as something to send.

**It was two lanes until 2026-10-27.** `jarvis-critic` was the stronger model a
review task was offered; the owner's decision of that day keeps ONE cloud lane,
so a review is a longer ANSWER (`REVIEW_ANSWER_TOKENS`) and not a second lane.
`is_review()` is still here and still answers "would this answer be a long
one?", which is what it sizes.

## The four gates, each one proved able to fail

Every gate is exercised by `backend/test_auto_router.py`, including the shapes
where it must refuse.

1. **Mode/switch** - OFF by default in general chat. On only when a caller
   enables it explicitly, or inside an active Project Mode workspace whose
   `auto_route_cloud` is exactly `true`. A missing, unreadable or corrupt
   switch file reads as OFF.
2. **Taint latch** - a HARD block, `reason="taint_latched_local_only"`. It
   reads the ONE latch this project has (`jarvis_gate.taint_active()`), plus a
   project whose `shareable` flag is not on. There is no per-topic latch to
   read - `latch_taint()`'s `why` argument is only a label, and nothing reads
   it back - so this gate does not pretend to finer granularity than exists,
   and ANY active taint blocks. Not being able to read the latch also blocks.
3. **Budget** - the on-disk per-minute/per-day cap (`jarvis_router.Budget`) AND
   the monthly money cap (`jarvis_chatbot_api.money_check()`). A cap that is
   exhausted **or unconfigured** is a no.
4. **Scrubber** - the outbound text must pass `jarvis_scrub.scrub_text()`, and
   the scrubber being absent is itself a refusal.

Then, last, the cost question: a wait over 25 seconds, or a complexity score of
0.75 or more. Only if all four gates passed **and** `choose()` agrees is a cloud
lane named - as advice.

## It sends, writes, approves and logs nothing

No network, no file written, no card raised, no model called, nothing logged. It
returns a dict and stops.
