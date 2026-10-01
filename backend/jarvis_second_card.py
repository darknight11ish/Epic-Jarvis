"""jarvis_second_card.py - what Jarvis may do with a second graphics card.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).

WHAT IT IS FOR. The owner is adding a second card - an RTX 2060 12 GB, or
possibly an RTX 2080 Ti 11 GB - beside the RTX 2080 Super 8 GB that runs the
everyday model. docs/MODEL-TOPOLOGY.md ("The planned second card") works out
what that second card could hold. This module is every feature built for it,
ALL OFF, each behind a switch that can only be turned on once a capable
second card is actually detected. That is how CLAUDE.md's "do not switch
anything on that depends on it until it is installed and measured" is kept:
nothing here does anything on a PC with one card, and nothing does anything
on a PC with two until the owner says yes on an approval card.

CARD SIZES (2026-09-30). An extra card may be 8, 10, 11, 12, 16 or 24 GB (the
floor is 7,680 MiB reported - MIN_TOTAL_MB). What each size can run is
worked out in the comment blocks above LONG_BIG and the small-card plan:
an 8 GB card runs Learning, the Wiki builder and (no monitor on it) Pictures -
work taken off the main card - but not "Longer conversations" or "Browser
control", which need more room than the main card's 16K. 10 GB and up is
the full plan. Every figure is calculated, not measured.

THE FEATURES (the ids are the API contract - both apps build against them):

    long_context     "Longer conversations": when a chat would be trimmed to
                     fit the main card, that answer is written on the second
                     card instead, with the whole history.
    vision           "Pictures": a turn that carries a picture goes to a
                     picture-reading model on the second card.
    learning         "Learning in the background": the memory learner's
                     model calls run on the second card.
    browser_control  "Browser control": the browser tool is offered only
                     while this lane is running, and its turns continue on
                     it. Needs long_context (it uses that lane's model).
    wiki             "Wiki builder": the lane jarvis_wiki.py's builder
                     runs on (lane_for("wiki")); it runs nowhere else.

TWO MORE (2026-09-30, JARVIS-API section 108, both built OFF until the second
card is installed and measured - the same rule as the five above):

    study            "Study helper": quiz questions are written, and answers
                     marked, on the second card's model (jarvis_quiz's model
                     call, handed in by study_call()/wire_study(); the quiz
                     module itself never imports this one). Off, or with the
                     lane down, the quiz runs exactly as before. The bigger
                     local model ("qwen3:14b", "One bigger model on both
                     cards") for marking stays a follow-up, not built here.
    referee          "Referee suggestions": PROPOSE-ONLY. jarvis_referee.py may
                     raise a card "This looks done - tick it?" when a goal
                     step's benchmark number reaches its target. The owner's
                     tap ticks the step (Goals.mark_step, as their own tick
                     would); nothing here ever writes a tick. Today it compares
                     numbers in code and loads NO model ("model_free": True in
                     FEATURES) - so it starts no second Ollama, and does not
                     count against "One bigger model on both cards". The
                     second card is required to switch it on because the later
                     step (reading a project task's change summary) will use
                     the card's model.

A THIRD MODE, alongside these five and alongside a chosen hardware preset's
single-card lanes (docs/HARDWARE-PROFILES.md 4.3): "One bigger model on both
cards" (the switch id is "combined", not one of the five FEATURE_IDS above -
it does not compose with them). Off by default, one approval card
(action second_card_combined_enable) to turn on, same shape as the other
switches here. When on, it starts a THIRD copy of Ollama that can see BOTH
cards (no CUDA_VISIBLE_DEVICES pin to one) and loads a model genuinely
bigger than either card holds alone (COMBINED_MODEL) - Ollama's own
scheduler then splits that model's layers across both cards by itself
(read from source, not inferred: docs/MODEL-TOPOLOGY.md "Running one model
across both cards"). It TIES UP BOTH CARDS, so it cannot run at the same
time as any of the five features above (request_change refuses either
direction while the other is genuinely on: _combined_capable, and the
"master and any feature" checks in _request_change_combined and in the
five features' own request_change path). Real speed is unmeasured until
the second card is physically installed - the approval card and Settings
both say so. combined_lane() is lane_for()'s shape for it; jarvis_agent.
choose_lane() calls it as the ordinary-turn fallback once vision and
long_context have both said no (bug audit 2026-09-27, finding #3 - fixed
the same day it was found; this file's own words had claimed the gap
longer than it was actually still open, caught by re-reading the real
caller list rather than trusting this comment).

SUGGESTING "COMBINED" (2026-09-27, the owner's "Both, with a setting"
answer to being asked directly). jarvis_agent.py notices two signs, each
per conversation
and in memory only, and asks THIS module to OFFER the existing card:

    struggle    Jarvis visibly having to work around a tool call this turn
                (jarvis_agent.note_struggle - an unreadable call, or a
                broken one).
    correction  the owner directly correcting an answer in this conversation
                (jarvis_agent.note_correction - a "wrong" mark, or the
                narrow phrase check, jarvis_agent.looks_like_correction).

`maybe_suggest_combined(conversation_id)`, called once at the end of every
turn, raises NOTHING by itself: once either count crosses its threshold
(STRUGGLE_THRESHOLD, CORRECTION_THRESHOLD - each with its own setting, both
on by default, SUGGEST_SIGNALS), it asks `_combined_capable` for the SAME
hard gate `combined` itself needs - a capable second card, right now, on
this PC, never inferred or assumed - and, only if that says yes, asks
jarvis_backoff whether an offer nobody asked for may be made right now (not
mid-chat, a few at most, a "no" heard). If every gate says yes, it raises
the EXACT SAME approval card `request_change("combined", True)` already
raises from Settings - `second_card_combined_enable`, tier "ask" - with one
short sentence added saying why Jarvis is asking now. There is no separate
"just this once" switch and no second on/off concept: accepting the offer
IS answering that card, so a "yes" turns combined mode on for real and a
"no" only ever means "not now" (jarvis_backoff.declined, the same 1/7/30-day
quiet every other offer gets - never a permanent refusal). The two settings
(`SUGGEST_SIGNALS`, `suggest_settings()`/`handle_suggest_post()`) live on
the same Hardware screen as the switches above, and change only whether
Jarvis OFFERS - never what it may do without a person's yes - so, like
jarvis_manner.py's humour switch, changing either one raises no card either
way.

THE INTERFACE other modules use - kept exactly:

    lane_for(feature) -> Optional[Lane]      Lane(url, model, num_ctx, why)
    combined_lane() -> Optional[Lane]        the third mode's own lane_for
    status() -> dict                         GET /api/second-card
    request_change(feature, enabled, *, gate=...) -> (http code, dict)
                                             POST /api/second-card
                                             (feature may be "combined")
    maybe_suggest_combined(conversation_id)  jarvis_agent.py, end of turn
    suggest_settings() -> dict               GET /api/second-card (folded in)
    handle_suggest_post(body) -> (code, dict) POST /api/second-card/suggest

lane_for() returns None unless the main switch and that feature are on, a
capable second card is detected, the second Ollama is running and the model
is installed. It never raises. Every caller treats None as "do exactly what
you did before this module existed".

THE PERMISSION MODEL (docs/ARCHITECTURE.md section 3). Turning a switch ON
is one approval card through jarvis_gate, action `second_card_enable`, tier
"ask" (the tier is checked before the card and again on the answer; only
tier "ask" with outcome "approved" turns it on - the same shape as the
wake-word card in jarvis_speech.set_wake_enabled). Turning OFF is immediate:
it only narrows what runs. Nothing here auto-approves (rule 4).

THE SECOND OLLAMA. While the main switch and at least one feature are on,
this starts `ollama serve` with:

    OLLAMA_HOST=127.0.0.1:11435      loopback only (rule 2); refused otherwise
    CUDA_VISIBLE_DEVICES=<uuid>      pinned by the card's id, never its number
    OLLAMA_KV_CACHE_TYPE=q8_0        the cache format MODEL-TOPOLOGY budgets
    OLLAMA_MAX_LOADED_MODELS=1       one model there at a time
    OLLAMA_NUM_PARALLEL=1            one conversation's cache, not four
    OLLAMA_CONTEXT_LENGTH=<num_ctx>  the only way to set context for the
                                     /v1 chat endpoint (no field for it)
    OLLAMA_KEEP_ALIVE=30m            (configurable)
    OLLAMA_VULKAN=0                  no Vulkan route (see below)
    OLLAMA_NO_CLOUD=1                Ollama itself refuses cloud models and its
                                     web search - a second lock behind rule 1

and NOT OLLAMA_FLASH_ATTENTION, unless `[second_card] flash_attention` says
"on". "off" is refused with a plain reason (_flash_refusal): with the q8_0
cache, llama.cpp will not load a model with flash attention off. I checked Ollama's source (llm/llama_server.go,
LlamaServerFlashAttention, main branch, 2026-09-24): unset means llama.cpp's
"auto", which falls back per model; set to 1 it passes `--flash-attn on`,
which removes that fallback. MODEL-TOPOLOGY.md already says not to set it, for
that reason.

WHY OLLAMA_VULKAN=0 (bug audit 3; the owner's decision 3 in
docs/HARDWARE-PROFILES.md section 5). Ollama reaches cards through a second
route, Vulkan, which is ON by default (ollama envconfig/config.go:234,
EnableVulkan, default true) and ignores CUDA_VISIBLE_DEVICES. Removing
GGML_VK_VISIBLE_DEVICES, which this module used to do alone, does not turn
that route off, so the second Ollama could still see the main card through
it. OLLAMA_VULKAN=0 does. The second card is always an NVIDIA card (it is
found through nvidia-smi), so CUDA is the route it uses. The owner's
`pin_command` sets the same thing for the everyday Ollama.

WHY THE CARD'S ID, NOT ITS NUMBER. CUDA numbers cards "fastest first" by
default (CUDA_DEVICE_ORDER=FASTEST_FIRST) while nvidia-smi numbers them in
PCI bus order, so "1" can mean different cards to the two - NVIDIA's CUDA
programming guide, "CUDA Environment Variables" (read through a search
result on 2026-09-24; docs.nvidia.com itself is blocked from where this was
written). CUDA_VISIBLE_DEVICES also accepts the id nvidia-smi prints
("GPU-8932f937-..."), and Ollama's own docs/gpu.mdx says "Numeric IDs may be
used, however ordering may vary, so UUIDs are more reliable" (read
2026-09-24). CUDA_DEVICE_ORDER=PCI_BUS_ID is set as well, belt and braces.

WHY TURING IS THE FLOOR (compute capability 7.5). MODEL-TOPOLOGY.md: llama.cpp
reaches the q8_0 cache only through its fused-attention path, and its fast
kernels need the Turing MMA path (GGML_CUDA_CC_TURING is 750). Everything this
module budgets assumes that cache. A Pascal card such as the Tesla P100
(6.0) passes Ollama's own gate and then takes the slow kernel, and has no
DP4A for quantised maths - see "If you are thinking about a second card".

THE EVERYDAY OLLAMA IS PINNED BY THE OWNER, NOT BY THIS MODULE. It must only
see the main card, or it may put the everyday model on the second one. This
module cannot and does not change another program's settings; it detects
(best effort) and hands the owner one PowerShell line (`pin_command`).

A THIRD CARD (2026-09-28, docs/GPU-SUPPORT-RESEARCH-2026-09-27.md). That
research read this file's own _detect() and found it picks exactly ONE
"second" candidate from however many capable extra cards are actually
plugged in, and throws the rest away with "capable, but the {second.name}
has more memory" - a real, capable third card sat right there and was
discarded, not merely untested. Its recommendation #1 was to fix the DATA
MODEL first, on its own, with NO behaviour change on a 1- or 2-card PC,
before building anything a third card could actually run - because every
call site below (_wanted, _feature_active, _reconcile, lane_for,
_combined_rows, status() itself) reads the SINGULAR det["second"] /
det["_second"], and jarvis_agent.choose_lane() trusts lane_for()'s answer to
route the model's own tool calls, so a change here that got the shape wrong
could silently send a turn to the wrong card, or to a card that isn't
running anything. That is exactly the risk this module's own approval-card
discipline exists to avoid on the SWITCH side; the detection side deserves
the same care.

**What is built here (2026-09-28):** _detect() now ALSO keeps every
capable non-primary card, not just the biggest, as det["_lanes"] - a
plain list of jarvis_compute Device objects (its own dataclass name for a
graphics card), best-memory-first (the same
sort _detect() already used to pick "second"; "second" is unchanged,
it is still _lanes[0] when the list is non-empty). extra_lanes(det)
turns _lanes[1:] into the same plain-dict shape status() already uses for
"second" (uuid/index/name/total_mb/compute_cap), so a THIRD capable card
is now visible to Python callers as data, not just as a "why" sentence on
an "unused" row in det["cards"] (which already said, correctly, why it was
not picked - that part of the design was already right and needed no
change). `_lanes` and `extra_lanes()` are internal (leading underscore on
the dict key; the function is not called from status() or any route) - the
GET /api/second-card JSON is BYTE-FOR-BYTE UNCHANGED, so both apps and
every existing test keep working exactly as before, on a PC with any
number of cards, capable or not.

**What is deliberately NOT built here, and why doing it now would be
reckless rather than merely incomplete:** a third card cannot yet run a
lane of its own. _wanted(), _feature_active(), _reconcile(), lane_for(),
_LANE (the one lane-process singleton) and describe_on() (the approval
card's own words) all still read the singular det["_second"] exactly as
they did before this change - none of them was touched, on purpose, so
none of the routing jarvis_agent.choose_lane() depends on could possibly
have moved. Making a third card actually RUN something needs, at minimum:
a second _LaneProcess-shaped singleton (or the two rewritten as a
dict-by-card), a real approval-card decision for "which feature goes on
which card" (docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3 is
explicit that this must be a genuine per-card choice on the card, never a
"biggest card wins" default - the same "no approve-all" rule every other
switch here already follows), and a matching UI in both apps (there is
none today; each app renders exactly one "second card" row). None of that
exists yet. Building it without a real third card to measure against, in
the same pass as this data-model change, risked exactly the kind of
sweeping, hard-to-verify rewrite this module's own tests are built to
catch early - so it is left for a dedicated follow-up pass instead, on top
of the shape _lanes now provides. "Combined" (COMBINED_MODEL, above) stays
two-card-only for the same reason MODEL-TOPOLOGY.md already gives for the
pair itself: real speed for splitting a model across even two cards is
still unmeasured, because the second card is not installed; adding a third
untested unknown on top of a first untested unknown is not a design
decision this module should make silently. _combined_rows() keeps reading
only the "primary" and "second" roles from det["cards"], so a third
capable card is automatically left out of "combined" too, without any new
code - it simply is not one of those two rows.

jarvis_hardware.py's preset system (lane_plan(), "chat_card"/"lane_card")
is a separate two-slot design and is UNCHANGED here for the same reason:
docs/HARDWARE-PROFILES.md's own presets ("Fastest answers"/"Smartest
answers"/"Most features") were designed and tested around exactly one
extra lane card, and generalising presets to three cards is its own,
separate decision this file does not make.

A THIRD CARD'S OWN LANE (2026-09-28). The follow-up pass the section above
promised: a third capable card (det["_third"], the same Device as
extra_lanes(det)'s first entry) can now be given ONE of the five features
above, so it runs alongside the second card's own lane - never instead of
it, and never a default (docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section
1.3: which card runs which feature must always be a real, named choice).

    THE SWITCH. One new field in second-card.json, "third_feature": either
    null (the third card does nothing - the "no default winner" rule holds
    even with a genuinely capable card sitting right there) or one of
    FEATURE_IDS (that feature's model calls go to the third card's own
    lane instead of the second's). Only ONE feature at a time can be
    moved there - there is only one third lane - so this is a single
    pointer, not the per-feature {"lane": ...} dict
    docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3 sketched for an
    arbitrary number of lanes: with exactly two lanes total (second and
    third), a pointer says the same thing with far less wire-format churn,
    and "features": {id: bool} - which both apps and every existing test
    already read - is untouched. If a FOURTH card is ever a real prospect,
    that is the moment to move to the fuller per-feature shape; building it
    now, for a lane nobody can measure yet, would be exactly the kind of
    speculative generality this project's own "measure before you build"
    rule (the memory re-ranker, "combined" itself) already warns against.

    Assigning a feature to the third card does NOT turn that feature on by
    itself - request_change(feature, True) (the existing switch) still
    does that, exactly as before. The assignment only says WHERE an
    already-on feature's calls go; _request_change_third refuses to
    assign a feature that is not on yet, in words, rather than silently
    turning it on as a side effect of a card about something else.

    WHY ITS OWN ACTION (second_card_third_assign, not second_card_enable).
    The task that asked for this named the reason precisely: the research
    doc requires the approval card to NAME the physical card, which means
    its wording (describe_third_assign) and its "what asks first" line
    are genuinely different from second_card_enable's own ("nothing
    leaves this PC" - true, but it does not say WHICH card, which is the
    one thing this decision is actually about). Reusing second_card_enable
    would also mean turning the third card on or off could never be
    loosened or audited separately from the second card's own switch - the
    same reason BROWSER_ACTION and COMBINED_ACTION already have their own
    lines rather than borrowing this one's.

    THE LANE PROCESS: A THIRD, LITERAL _LaneProcess, NOT A DICT. _LANE and
    _COMBINED_LANE are two hardcoded singletons; the tempting "more
    correct" shape is a dict keyed by role (or by card uuid), so a fourth
    card would be "add one more key" instead of "add one more singleton
    and mirror every call site again". That was seriously considered here
    and deliberately NOT done, for a reason specific to this module rather
    than a general dislike of dicts: _LaneProcess itself already carries NO
    assumption about being "the second" or "the combined" one - every
    method (ensure/hold/stop/pids, the card claim/release in _start) is
    already written generically, parameterised by whatever uuid/port/log
    role it is given. The cost of one more literal instance (_THIRD_LANE)
    is therefore exactly the cost of one more dict entry would have been -
    a handful of new orchestration functions (_reconcile_third,
    mirroring _reconcile; a "third" branch in status(), sleep(), shutdown()
    and main_pin()) - MINUS the risk of touching _LANE's and
    _COMBINED_LANE's own already-well-tested call sites to thread a lookup
    through them. Given how safety-critical this module's routing is (the
    task that asked for this said so plainly), the lower-risk, purely
    additive path was chosen on purpose. If a genuine fourth card is ever
    on the table, THAT pass should build the dict - informed by whether
    the third card's own design (one pointer, one action, one lane) turned
    out to generalise cleanly, rather than guessing now for a card nobody
    has ordered.

    THE PORT AND THE LOG, EACH THEIR OWN. _LANE and _COMBINED_LANE already
    share one port (_port(), from [second_card] port) safely, because the
    two are mutually exclusive by design (never running at once - see
    "combined" above) - only one of them is ever actually listening on it.
    The third lane is NOT mutually exclusive with the second's: a feature
    on the third card and a feature on the second card are meant to run at
    the SAME TIME, on different physical cards. It therefore needs its own
    port ([second_card] third_port, default 11436, never MAIN_OLLAMA_PORT
    or _port()'s own value) and its own log file
    (second-card-third-ollama.log) - sharing either would either fail to
    bind, or interleave two processes' output into one unreadable file.

    WHERE THE THIRD CARD'S MEMORY BUDGET COMES FROM. _feature_model() grew
    one optional `card` parameter (default: det["_second"], exactly as
    before - every existing caller is unaffected) so the third lane's own
    memory/model plan is sized from det["_third"]'s OWN total_mb, never
    borrowed from the second card's. A third card of a different size gets
    its own correct answer, the same arithmetic _long_context_plan()
    already does for the second.

    WHAT IS DELIBERATELY UNCHANGED. _detect()'s per-row "cards[]" role and
    "why" text for a third capable card are UNTOUCHED for the case
    test_second_card.py's reshape-pass fixture actually covers (still
    "unused, capable, but the {second.name} has more memory" when the
    chosen card genuinely has more) - without an assignment, a third card
    really is unused. Fixed in this pass, not part of the reshape's own
    promise: the sentence used to say "has more memory" even when the two
    cards TIE, which is false (2026-09-28 hardware-detection audit,
    finding #2) - it now says "has the same amount of memory and was
    already picked" for that case instead. The fuller, up-to-date story
    (capable, assigned to X, or not assigned) lives in status()'s new
    "third" key instead, which is purely additive - every existing key in
    GET /api/second-card is untouched. "Combined" stays exactly as it was:
    _combined_rows() still reads only "primary"/"second" from cards[], so
    a third card is automatically left out of it, without any new code.
    Presets (_detect_preset) stay two-slot: det["_third"] is always None
    under a chosen preset, so third-card assignment simply does nothing
    there, in words, the same way every other third-card check already
    reads "no capable third card".

Standard library only. Never logs or returns a token or key.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

#: Every request here goes straight to the address, never through a proxy
#: (bug audit 3, CONN-1): see jarvis_local_http.py.
import jarvis_local_http

#: What a program Jarvis starts may inherit (bug audit 3, CONN-2).
import jarvis_child_env

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import jarvis_compute as compute
except Exception:
    compute = None  # type: ignore


# --------------------------------------------------------------------------
#   Constants
# --------------------------------------------------------------------------

ACTION = "second_card_enable"
#: "Browser control" has its own action (AP-9). Every other switch only
#: starts a model on this PC; this one also lets Jarvis offer its browser
#: tool, which works real web pages on the internet. Its own action gives
#: it its own tier line in the toml and its own words on the lock-screen
#: notice (second-card.patch's _RISK line: "outbound"), instead of
#: borrowing second_card_enable's "nothing leaves this PC".
BROWSER_ACTION = "second_card_browser_enable"
#: Moving one of the five features onto a THIRD capable card (see the
#: module docstring's "A THIRD CARD'S OWN LANE" section). Its own action,
#: not ACTION: the approval card it raises names a SPECIFIC physical
#: card, which docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3 says
#: must always be a real, named choice, and its "what asks first" wording
#: is genuinely different from ACTION's own ("nothing leaves this PC" -
#: true, but not the point of this particular card).
THIRD_ACTION = "second_card_third_assign"
HOST = "127.0.0.1"
DEFAULT_PORT = 11435
#: The third lane's own port (module docstring: it can run at the SAME
#: TIME as the second card's lane, so it cannot share _port()'s value the
#: way _COMBINED_LANE safely does).
DEFAULT_THIRD_PORT = 11436
MAIN_OLLAMA_PORT = 11434

#: Turing. See the module docstring and MODEL-TOPOLOGY.md.
MIN_COMPUTE = 7.5
#: The capability floor, as nvidia-smi reports memory.total (MiB): 7.5 GiB.
#: CHANGED 2026-09-30 from 10,240 (10 GiB) so an 8 GB extra card can be used
#: (owner: "make sure if the second and/or 3rd GPUs are only 8 GB VRAM each
#: that they are able to be utilized fully"). A card sold as "8 GB" is
#: 8,192 MiB and some drivers report a few MiB less (8,188 was seen), so the
#: floor sits half a GiB under 8,192: every real 8 GB card clears it, and a
#: 6 GB card (6,144 MiB, the RTX 2060 6 GB) does not. A card under 8,192 is
#: still sized honestly from its real memory (see the small-card plan below),
#: never from the label. Turing (compute 7.5) and a card id are still needed.
MIN_TOTAL_MB = 7680
#: The old floor, now the line between the two plans: a card at or above 10 GiB
#: gets the full plan below (LONG_BIG/LONG_SMALL - unchanged), a card between
#: MIN_TOTAL_MB and this gets the small-card plan.
FULL_TOTAL_MB = 10240
#: A card sold as "12 GB". 11.5 GiB rather than exactly 12,288 MiB, because
#: a card can report a little under its label; an 11 GB 2080 Ti (11,264 MiB)
#: stays below it. Since 2026-09-24 both sizes get the same lane (below);
#: the line is kept so a bigger plan for 12 GB can be put back in one place.
BIG_TOTAL_MB = 11776

# What the long-context lane holds, by the second card's memory.
#
# CHANGED 2026-09-24 (bug audit T3). This used to be Qwen 3 14B at 16K on a
# 12 GB card. The everyday model, jarvis-primary, also has 16,384 tokens of
# room (backend/jarvis-primary.Modelfile, num_ctx 16384), so a conversation
# too long for the main card was moved to a lane with NO more room, and was
# trimmed there exactly as it would have been at home. The lane is only
# worth having if it holds more than the main card, so 12 GB now gets what
# docs/HARDWARE-PROFILES.md section 4.4 gives a 12 GB long-context lane
# ("8 + 12 GB, monitor on the 12" and "12 + 12 GB": qwen3:8b, 32K), with
# the owner's 0.75 GB gap (section 5, decision 1):
#
#   KV per token, q8_0 = 2 (K and V) x layers x kv_heads x 128 x 1.0625 bytes
#     Qwen 3 8B : 2 x 36 x 8 x 128 x 1.0625 = 78,336 B   (section 2.8)
#
#   Qwen 3 8B Q4_K_M @ 32K: 4.67 + 2.39 + 0.30 = 7.36 GiB   (section 8.2's "need")
#                           (weights) (cache) (compute)
#   + 0.33 GiB CUDA start-up, which section 4.2 counts on the card's side
#   = 7.69 GiB, the figure the approval card shows.
#
#   room on the card, no monitor: total - 0.60 desktop - 0.33 - 0.75 gap
#     12 GB card (2060 12 GB)  10.32 GiB  -> 8B @ 32K (7.36), 2.96 spare
#     11 GB card (2080 Ti)      9.32 GiB  -> 8B @ 32K, 1.96 spare
#     10 GB card                8.32 GiB  -> 8B @ 32K, 0.96 spare
#
# Qwen 3 14B at 16K (10.10 needed) would fit a 12 GB card, but gives no more
# room than the main card; 14B at 32K (11.43) does not fit. Measure on the
# PC before changing this (HARDWARE-PROFILES section 4.7).
LONG_BIG = ("qwen3:8b", 32768, 7.69)
LONG_SMALL = ("qwen3:8b", 32768, 7.69)

# EVERY SIZE, BY MEMORY BAND (2026-09-30). Extra cards are expected to be 8 to
# 24 GB. nvidia-smi reports MiB, a little under the label on some cards
# (16 GB: 16,376; 24 GB: 24,564), so bands are read from the reported MiB and
# never from the label. CALCULATED, NOT MEASURED - no extra card is installed.
#
#   band            reported MiB          plan (this file's own arithmetic)
#   8 GB            7,680 - 10,239        the small-card plan below: qwen3:8b at the
#                                         largest of 16K / 8K that fits; no
#                                         "Longer conversations" (no more room than
#                                         the main card), no "Browser control"
#   10, 11, 12 GB   10,240 - up           LONG_BIG above, unchanged: qwen3:8b @ 32K
#   16 GB           16,376 (room 14.64)   the same LONG_BIG, spare 6.95 GiB
#   24 GB           24,564 (room 22.64)   the same LONG_BIG, spare 14.95 GiB
#
# (room = total - 0.60 desktop - 0.75 gap, the same terms as the small-card
# plan's table below; spare = room - the 7.69 LONG_BIG needs.)
# WHY 16 AND 24 GB DO NOT GET A BIGGER PLAN. Two larger things were checked
# against this file's own arithmetic and neither is taken:
#  - a longer context on qwen3:8b: 32,768 is the model's own native length. Room
#    for 64K exists (cache 4.78 GiB, need 10.08 GiB) but going past the native
#    length needs rope scaling, which nothing here sets or has tested, so it
#    is not offered.
#  - a bigger model: qwen3:14b @ 32K needs 8.42 + 2.66 + 0.30 + 0.33 = 11.71 GiB
#    (COMBINED_MODEL's own weights and cache, one card's runtime), which fits a
#    16 GB card (14.64) and a 24 GB one. It is NOT switched on, because it would
#    change which model writes the answers and does the learning, and the
#    tool-call tests and the learner test (CLAUDE.md: measure before keeping a
#    memory or learning change) are measured on the 8B. Left as an owner
#    decision; the extra memory on a 16/24 GB card stays spare until then.

# Pictures. NOT CHECKED against ollama.com: the library page could not be
# reached from where this was written (ollama.com and huggingface.co are
# blocked there). From the published Qwen2.5-VL-7B geometry as remembered -
# 28 layers, 4 KV heads, head size 128 - its cache is
#   2 x 28 x 4 x 128 x 1.0625 = 30,464 B a token (0.46 GiB at 16K, 0.93 at 32K),
# and the download is about 6 GB with the picture reader included (~5.59 GiB
# of weights, assumed). Plus 0.63 runtime, plus an unmeasured amount for
# reading an image. Treat VISION_WEIGHTS_GIB as a guess until
# `ollama show qwen2.5vl:7b` has been read on the PC.
VISION_MODEL = "qwen2.5vl:7b"
VISION_WEIGHTS_GIB = 5.59
VISION_KV_BYTES_PER_TOKEN = 30464
RUNTIME_GIB = 0.63

# --------------------------------------------------------------------------
#   The small-card plan: an 8 GB extra card (2026-09-30)
# --------------------------------------------------------------------------
#
# CALCULATED, NOT MEASURED. No extra card is installed in the owner's PC yet;
# every number below comes from the same arithmetic LONG_BIG uses, from
# docs/HARDWARE-PROFILES.md's shapes, and none of it has been run.
#
# THE KEY FACT. The everyday model, jarvis-primary, already has 16,384 tokens
# of room (backend/jarvis-primary.Modelfile, num_ctx 16384). An 8 GB extra card
# can hold no more than that (below), so "Longer conversations" would move a
# conversation to a card with NO more room than the one it left - the exact
# mistake bug audit T3 (above) already removed for 12 GB. So on an 8 GB card
# "Longer conversations" is NOT offered, and "Browser control" (which needs it,
# and needs room for page after page of history - jarvis_browser_control.py)
# is not offered either. What the card is still good for is taking work OFF
# the main card: Learning in the background, the Wiki builder and, when
# nothing is plugged into it, Pictures. That work then never competes with
# chat for the main card.
#
# THE ROOM. Same terms as LONG_BIG's comment - memory total, minus the
# desktop's own share (0.60 GiB with no monitor on the card, 1.10 with one:
# HARDWARE-PROFILES section 4.2), minus the owner's 0.75 GiB empty gap:
#
#   8,192 MiB card, no monitor   8.00 - 0.60 - 0.75  =  6.65 GiB
#   8,192 MiB card, monitor      8.00 - 1.10 - 0.75  =  6.15 GiB
#   8,188 MiB card, no monitor   7.996 - 0.60 - 0.75 =  6.65 GiB (rounded)
#   7,680 MiB card (the floor)   7.50 - 0.60 - 0.75  =  6.15 GiB
#
# WHAT IS PUT IN IT. Qwen 3 8B Q4_K_M (learning, wiki), KV cache q8_0 at
# 2 x 36 x 8 x 128 x 1.0625 = 78,336 B a token (the same 78,336 as LONG_BIG):
#
#   need = weights 4.67 + cache + compute 0.30 + CUDA start-up 0.33
#   @ 16,384 tokens: 4.67 + 1.20 + 0.30 + 0.33 = 6.50 GiB
#                    -> fits the 6.65 of a no-monitor card, 0.15 spare
#                       (tight - the owner's 0.75 gap is already taken out
#                       of the room, so it is kept; only this sliver is
#                       left over, and it is an estimate)
#   @  8,192 tokens: 4.67 + 0.60 + 0.30 + 0.33 = 5.90 GiB
#                    -> fits even with a monitor (6.15), 0.25 spare
#
# so each 8 GB card gets the LARGEST of 16,384 / 8,192 that fits. 16,384 is the
# most an 8 GB card can give and it equals the main card's, which is the
# whole reason "Longer conversations" is off here. Under 8,192 is refused as
# too small to be useful (the wiki's source budget shrinks with it).
#
# PICTURES. qwen2.5vl:7b, the same guessed 5.59 GiB of weights as
# VISION_WEIGHTS_GIB (UNCHECKED - `ollama show qwen2.5vl:7b` has not been read
# on the PC), cache 30,464 B a token, 0.63 runtime:
#   @ 8,192 tokens: 5.59 + 0.23 + 0.63 = 6.45 GiB
#                   -> fits a no-monitor card (6.65), 0.20 spare; does NOT fit
#                      with a monitor (6.15), so Pictures is refused there,
#                      in words. 16,384 would need 6.68 and does not fit either.
# Reading a picture needs an unmeasured extra on top; 0.20 spare is thin, so
# if Pictures is slow on an 8 GB card, that is the first thing to suspect.
#
# Cards between 8 GB and 10 GB (there are none on sale that Jarvis knows of)
# are sized by the same rule from their own memory. From 10,240 MiB up the
# full plan applies, exactly as before.

#: The largest, then the smaller, context an 8 GB card is offered.
SMALL_CTX_STEPS = (16384, 8192)
#: Below this an 8 GB card is refused for the features that need room.
SMALL_MIN_CTX = 8192
#: Qwen 3 8B Q4_K_M (LONG_BIG's own 4.67 + 0.30 compute), KV bytes per token.
QWEN8_WEIGHTS_GIB = 4.67
QWEN8_COMPUTE_GIB = 0.30
QWEN8_KV_BYTES_PER_TOKEN = 78336
CUDA_START_GIB = 0.33
#: The desktop's share on a card with no monitor / with a monitor, and the
#: owner's empty gap (HARDWARE-PROFILES section 4.2 and decision 1).
DESKTOP_GIB = 0.60
DESKTOP_MONITOR_GIB = 1.10
GAP_GIB = 0.75
#: The main card's context (jarvis-primary.Modelfile): what an extra card has
#: to beat for "Longer conversations" to be worth anything.
MAIN_CARD_CTX = 16384

#: The seven features, in the order both apps show them. `model_free`: the
#: feature loads no model today (referee), so it starts no second Ollama, does
#: not tie up the cards (it never blocks "One bigger model on both cards") and
#: cannot be moved to a third card.
FEATURES = (
    {"id": "long_context", "name": "Longer conversations", "needs": [],
     "what": ("When a conversation grows past what the main card has room for, "
              "that answer is written on the second card, which has room for more of it.")},
    {"id": "vision", "name": "Pictures", "needs": [],
     "what": ("A message with a picture goes to a picture-reading model on the "
              "second card, on this PC, so Jarvis can see what you attached.")},
    {"id": "learning", "name": "Learning in the background", "needs": [],
     "what": ("Jarvis learns from your conversations on the second card, so it "
              "never slows the main card down and does not wait long for a pause.")},
    {"id": "browser_control", "name": "Browser control", "needs": ["long_context"],
     "what": ("Jarvis can work a web page for you in your browser, one approved step at a "
              "time, using the second card's extra room for long pages. The pages are on "
              "the internet: what it types or clicks there reaches that website.")},
    {"id": "wiki", "name": "Wiki builder", "needs": [],
     "what": ("Lets the wiki builder use the second card: documents you put in "
              "your vault's Jarvis Wiki/Sources folder become linked pages, each one "
              "after its own approval card.")},
    # 2026-09-30 (JARVIS-API section 108). Built OFF like the rest.
    {"id": "study", "name": "Study helper", "needs": [],
     "what": ("Quiz questions are written, and your answers marked, on the second card, "
              "so a quiz never slows the everyday chat. The text you paste and the "
              "answers you type stay on this PC.")},
    {"id": "referee", "name": "Referee suggestions", "needs": [], "model_free": True,
     "what": ("When a goal step's number reaches your target, Jarvis asks \"This looks "
              "done - tick it?\" on a card that shows the numbers. Only your tap ticks "
              "it: Jarvis never ticks a step by itself and never runs a test. Today it "
              "compares numbers on this PC and loads no model.")},
)
FEATURE_IDS = tuple(f["id"] for f in FEATURES)
_BY_ID = {f["id"]: f for f in FEATURES}


def _model_free(feature: str) -> bool:
    """A feature that loads no model today (see FEATURES): it needs the second
    card to be switched on, but starts no lane and holds no card memory."""
    return bool(_BY_ID.get(feature, {}).get("model_free"))

# --------------------------------------------------------------------------
#   The third mode: one bigger model, split across both cards by Ollama's
#   own scheduler. Off by default; ties up both cards (see module docstring).
# --------------------------------------------------------------------------

COMBINED_ACTION = "second_card_combined_enable"
COMBINED_NAME = "One bigger model on both cards"

# Combined budget, same arithmetic style as LONG_BIG above and
# docs/HARDWARE-PROFILES.md section 4.2's per-card room, added across both
# cards (owner's planned pair: RTX 2080 Super 8 GB with the monitor, RTX
# 2060 12 GB without):
#
#   room, 2080 Super (monitor)   8.00 - 1.10 desktop - 0.33 CUDA - 1.00 fit  =  5.57 GiB
#   room, 2060 (no monitor)     12.00 - 0.60 desktop - 0.33 CUDA - 1.00 fit  = 10.07 GiB
#   combined room                                                            = 15.64 GiB
#
# Qwen 3 14B Q4_K_M, q8_0 KV @ 32K (docs/HARDWARE-PROFILES.md 2.8's shapes):
#   weights                                                        =  8.42 GiB
#   KV     2 x 40 x 8 x 128 x 1.0625 B x 32768                      =  2.66 GiB
#   runtime, TWO CUDA contexts + compute buffers (one per card in the
#     split, not sourced - see docs/MODEL-TOPOLOGY.md's "not sourced
#     anywhere I could find" about this number even for ONE card;
#     doubled here on purpose, to stay on the pessimistic side)      =  1.20 GiB
#                                                                       --------
#                                                                        12.28 GiB, 3.36 spare
#
# 14B is genuinely bigger than every per-card plan in this file (LONG_BIG,
# VISION_MODEL and the everyday jarvis-primary are all 7-8B), and 32K is
# double the everyday model's 16,384 - the same "must beat the main card"
# rule LONG_BIG already follows. Not measured: the second card is not
# installed. Change this once it is (with eval numbers, as CLAUDE.md's
# memory rule already requires for a different kind of change - the same
# discipline applies here).
COMBINED_MODEL = ("qwen3:14b", 32768, 12.28)
#: The floor below which the arithmetic above no longer clears the model's
#: need with any margin (see the comment): 18 GiB combined (e.g. an 8 GB
#: card with a 10 GB one). Below it, "combined" is refused as not capable.
COMBINED_MIN_TOTAL_MB = 18432


# --------------------------------------------------------------------------
#   Suggesting the bigger model (2026-09-27) - see the module docstring's
#   own section for the whole design. The settings here only ever change
#   whether Jarvis OFFERS "combined" on its own; the offer, when made, is
#   the SAME approval card the switch above already raises.
# --------------------------------------------------------------------------

#: How many "struggle" signs (jarvis_agent.note_struggle: an unreadable tool
#: call, or a broken one) in ONE conversation before Jarvis offers the
#: bigger model, IF the setting for it is on. Low, on purpose: one broken
#: call happens even with a perfectly capable model (a stray token, a
#: truncated stream), and asking after every single one would be a nag over
#: nothing; three in the SAME conversation is a pattern the owner can see
#: and decline in a moment if the model was only having an off turn.
STRUGGLE_THRESHOLD = 3

#: How many "correction" signs (jarvis_agent.note_correction: a "wrong"
#: mark, or the narrow phrase check) in ONE conversation, IF that setting is
#: on. Lower than STRUGGLE_THRESHOLD: a correction is a more deliberate
#: signal than a parser hiccup, and correcting Jarvis TWICE in the same
#: conversation is the earliest point at which "repeated correction"
#: (CLAUDE.md's own words for this) genuinely applies - a single correction
#: is just as likely to be the owner catching an ordinary slip.
CORRECTION_THRESHOLD = 2

#: The offer's kind, declared in jarvis_backoff.OFFERS with what it asks for
#: (rule 4: an offer never asks for more). It only ever asks to raise the
#: SAME card the switch already has; nothing here is a second yes.
SUGGEST_OFFER_KIND = "second_card_combined_offer"

#: The words both apps show for the two switches (GET /api/second-card,
#: folded into status() as "suggest" - the same screen the switches above
#: are already on).
SUGGEST_TITLE = "When to suggest the bigger model"
SUGGEST_DETAIL = ("Lets Jarvis OFFER to turn on \"One bigger model on both cards\" when it "
                  "notices one of these - never switches it on by itself. Accepting the offer "
                  "raises the exact same approval card as the switch above; saying no only "
                  "means \"not now\" - Jarvis waits a while before offering again.")
SUGGEST_LABEL = {
    "struggle": "When Jarvis is visibly struggling",
    "correction": "When you correct an answer more than once",
}
SUGGEST_WHY = {
    "struggle": ("Jarvis had to ask the model to try a tool call again more than a couple of "
                "times in one conversation - a sign it is struggling with what you are asking."),
    "correction": ("You have told Jarvis it got something wrong more than once in the same "
                  "conversation."),
}


def suggest_setting(signal: str) -> bool:
    """Is this suggestion signal switched on? SUGGEST_DEFAULT (True) for a
    signal this module does not know, or for a missing or damaged state
    file - see _read_switches for why the two defaults (the switches
    above, and this one) point opposite ways on purpose."""
    if signal not in SUGGEST_SIGNALS:
        return False
    try:
        return bool(_read_switches()["suggest"].get(signal, SUGGEST_DEFAULT))
    except Exception:
        return SUGGEST_DEFAULT


def suggest_settings() -> dict:
    """`status()`'s own "suggest" key (GET /api/second-card) - there is no
    separate GET route for this alone; both apps already poll the one
    route for the Hardware screen, and this rides along in it."""
    sw = _read_switches()
    return {
        "available": True, "title": SUGGEST_TITLE, "detail": SUGGEST_DETAIL,
        "signals": [{"id": s, "label": SUGGEST_LABEL[s], "why": SUGGEST_WHY[s],
                    "enabled": bool(sw["suggest"].get(s, SUGGEST_DEFAULT)),
                    "default": SUGGEST_DEFAULT} for s in SUGGEST_SIGNALS],
    }


def handle_suggest_post(body) -> tuple:
    """POST /api/second-card/suggest {"signal": "struggle"|"correction",
    "enabled": true|false} - NO CARD EITHER WAY (see the section above: this
    only changes whether Jarvis offers, never what it may do without
    asking, the same reasoning jarvis_manner.py's humour switch already
    uses). 200 on success, 400 for a bad body."""
    if not isinstance(body, dict) or set(body) != {"signal", "enabled"}:
        return 400, {"ok": False,
                     "error": 'send {"signal": "struggle" or "correction", "enabled": true '
                              'or false}, and nothing else'}
    sig = body.get("signal")
    en = body.get("enabled")
    if sig not in SUGGEST_SIGNALS:
        return 400, {"ok": False,
                     "error": f"signal must be one of: {', '.join(SUGGEST_SIGNALS)}"}
    if not isinstance(en, bool):
        return 400, {"ok": False, "error": '"enabled" must be true or false'}
    err = _write_suggest(sig, en)
    if err:
        return 500, {"ok": False, "error": err}
    _audit("second_card.suggest_setting", {"signal": sig, "enabled": en})
    return 200, {"ok": True, **suggest_settings()}


@dataclass(frozen=True)
class Lane:
    """Where a feature's model calls go. `url` is always loopback."""
    url: str
    model: str
    num_ctx: int
    why: str


# --------------------------------------------------------------------------
#   Things the tests replace
# --------------------------------------------------------------------------

def _cards(fresh: bool = False) -> list:
    """jarvis_compute's reading of nvidia-smi (cached 30 s there)."""
    if compute is None:
        return []
    try:
        return compute.query_cards(fresh=fresh)
    except Exception:
        return []


def _primary(cards: list) -> tuple:
    if compute is None:
        return (cards[0], "it is the first card") if cards else (None, "no card")
    return compute.primary(cards)


def _smi_apps() -> Optional[str]:
    """nvidia-smi's list of processes using a card, or None."""
    if compute is None:
        return None
    try:
        return compute._run_smi(["--query-compute-apps=pid,process_name,gpu_uuid,used_memory",
                                 "--format=csv,noheader,nounits"])
    except Exception:
        return None


def _user_env(name: str) -> Optional[str]:
    """A variable from the Windows user environment (HKCU\\Environment),
    where `[Environment]::SetEnvironmentVariable(..., 'User')` puts it.
    None when not set or not Windows."""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, _ = winreg.QueryValueEx(k, name)
            return str(val) if val else None
    except Exception:
        return None


def _http_json(url: str, payload: Optional[dict] = None, timeout: float = 2.0):
    """GET (or POST `payload`) a loopback URL and return the JSON body.
    Raises on anything else - callers catch."""
    if not _is_loopback_url(url):
        raise ValueError("not a loopback address")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    # Never through a proxy: jarvis_local_http.py (bug audit 3, CONN-1).
    with jarvis_local_http.urlopen(req, timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _port_taken(port: int) -> bool:
    """Is anything listening on 127.0.0.1:<port>?"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((HOST, int(port))) == 0
    except Exception:
        return False
    finally:
        s.close()


_popen = subprocess.Popen
_which = shutil.which
_ON_WINDOWS = os.name == "nt"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-second-card", daemon=True).start()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _big_model():
    """jarvis_big_model, or None. Imported when asked, never at load."""
    try:
        import jarvis_big_model
        return jarvis_big_model
    except Exception:
        return None


def _claim_card(uuid: str) -> Optional[str]:
    """jarvis_compute.claim_card for this lane: None when the card is ours,
    else who holds it."""
    if compute is None or not hasattr(compute, "claim_card"):
        return None
    try:
        return compute.claim_card(uuid, "second_card")
    except Exception:
        return None


def _release_card(uuid: str) -> None:
    if compute is None or not uuid or not hasattr(compute, "release_card"):
        return
    try:
        compute.release_card(uuid, "second_card")
    except Exception:
        pass


def big_model_holds(uuid: str, name: str) -> Optional[str]:
    """Why the second Ollama must not start on this card because the big
    model (colibri, with [big_model] cuda = "on") is using it, in plain
    words; None when it is not. Reads only."""
    if not uuid:
        return None
    bm = _big_model()
    ec = None
    if bm is not None and hasattr(bm, "engine_card"):
        try:
            ec = bm.engine_card()
        except Exception:
            ec = None
    held = bool(ec and str(ec.get("uuid") or "").lower() == str(uuid).lower())
    if not held and compute is not None and hasattr(compute, "card_holder"):
        try:
            held = compute.card_holder(uuid) == "big_model"
        except Exception:
            held = False
    if not held:
        return None
    mins = (ec or {}).get("idle_minutes")
    after = (f"it stops after {mins} idle minutes" if mins
             else "it stops when it has been idle for a while")
    return f"the big model is using the {name}; {after}"


# --------------------------------------------------------------------------
#   Settings: the toml for how, a small file for the owner's switches
# --------------------------------------------------------------------------

def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return (fw.load_framework().get("second_card") or {}).get(key, default)
    except Exception:
        return default


def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _state_path() -> Path:
    """The switches. Never the owner's toml: no route may write that."""
    return _config_dir() / "second-card.json"


def _log_path(role: str = "second") -> Path:
    """second-card-ollama.log for the feature lane and for "combined" (role
    "second" or "combined") - the two never run at once (module docstring),
    so sharing one file was always safe. A third lane CAN run at the same
    time as the feature lane, so role "third" gets its own file - sharing
    would interleave two processes' output into one unreadable log."""
    name = "second-card-ollama.log" if role in ("second", "combined") \
        else f"second-card-{role}-ollama.log"
    return _config_dir() / name


def _port() -> int:
    try:
        p = int(_cfg("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return p if 1024 <= p <= 65535 and p != MAIN_OLLAMA_PORT else DEFAULT_PORT


def _third_port() -> int:
    """The third lane's own port - never MAIN_OLLAMA_PORT or _port()'s own
    value (module docstring: the two lanes can run at once, so they cannot
    share a port the way _LANE and _COMBINED_LANE safely do)."""
    try:
        p = int(_cfg("third_port", DEFAULT_THIRD_PORT))
    except (TypeError, ValueError):
        return DEFAULT_THIRD_PORT
    taken = (MAIN_OLLAMA_PORT, _port())
    if not (1024 <= p <= 65535) or p in taken:
        p = DEFAULT_THIRD_PORT
    # The default itself can be taken (a second-card `port` set to 11436):
    # step up to the next port that neither of the other two copies uses.
    while p in taken:
        p += 1
    return p


def _keep_alive() -> str:
    v = str(_cfg("keep_alive", "30m") or "30m").strip()
    return v if re.fullmatch(r"-1|\d+[smh]?", v) else "30m"


def _flash_setting() -> str:
    v = str(_cfg("flash_attention", "auto") or "auto").strip().lower()
    return v if v in ("auto", "on", "off") else "auto"


def _flash_refusal() -> Optional[str]:
    """Why the lane must not start with this [second_card] flash_attention,
    or None. "off" cannot work with the lane's q8_0 cache: llama.cpp
    refuses to create the model's context ("quantized V cache requires
    flash_attn to be enabled", src/llama-context.cpp ~3737-3741, b11081 -
    docs/HARDWARE-PROFILES.md 2.2), so every model on the lane would fail
    to load. Refused here, in words, instead."""
    if _flash_setting() != "off":
        return None
    return ("[second_card] flash_attention is \"off\" in jarvis-framework.toml, which cannot "
            "work: the second copy of Ollama keeps the conversation in the compact q8_0 "
            "format, and llama.cpp refuses to load a model that way with flash attention "
            "off. Delete that line (or set it to \"auto\"), and the second card starts")


def _main_ollama_url() -> str:
    return (os.environ.get("OLLAMA_URL") or f"http://{HOST}:{MAIN_OLLAMA_PORT}").rstrip("/")


def _is_loopback_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1")


_STATE_LOCK = threading.RLock()


#: The two independent signs "suggest the bigger model" watches - each its
#: own switch, both on by default (see the "Suggesting the bigger model"
#: section below). Kept in the SAME state file as the switches above (it is
#: the same Hardware screen), but never written by `_write_switch` - see
#: `_write_suggest`.
SUGGEST_SIGNALS = ("struggle", "correction")
SUGGEST_DEFAULT = True


def _read_switches() -> dict:
    """{"master": bool, "combined": bool, "features": {id: bool},
    "suggest": {"struggle": bool, "correction": bool},
    "third_feature": Optional[str], "third_card": Optional[str]}. "combined" is the third mode's own
    switch - a sibling of "master", not one of "features" (it does not
    compose with them: see the module docstring). "suggest" is neither: it
    never starts or stops anything by itself, it only says whether
    jarvis_second_card may OFFER "combined" on its own (see below).
    "third_feature" (2026-09-28) is which of FEATURE_IDS, if any, is moved
    onto a third capable card - None (the default) means the third card
    does nothing, even if one is plugged in (module docstring's "A THIRD
    CARD'S OWN LANE"). "third_card" (2026-09-30) is the id of the card the
    owner APPROVED that move for: the third slot is re-picked from whatever
    cards are plugged in on every read (best memory, then lowest index), so
    a swapped, moved or added card can be the third one tomorrow. The
    assignment only counts while the card in that slot IS this one
    (_third_feature_now). A file from before this field has none, and is
    read as "ask again" - never as "whichever card is third now". A missing or broken file is everything off (and
    third_feature None), and "suggest" both ON - the safe reading either
    way: nothing starts without a person's yes, and a missing file
    offering nothing is the wrong direction to fail an offer in, so the two
    defaults are opposite on purpose."""
    out = {"master": False, "combined": False, "features": {f: False for f in FEATURE_IDS},
           "suggest": {s: SUGGEST_DEFAULT for s in SUGGEST_SIGNALS}, "third_feature": None,
           "third_card": None}
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    out["master"] = raw.get("master") is True
    out["combined"] = raw.get("combined") is True
    feats = raw.get("features")
    if isinstance(feats, dict):
        for f in FEATURE_IDS:
            out["features"][f] = feats.get(f) is True
    sug = raw.get("suggest")
    if isinstance(sug, dict):
        for s in SUGGEST_SIGNALS:
            if s in sug:
                out["suggest"][s] = sug[s] is True
    tf = raw.get("third_feature")
    if isinstance(tf, str) and tf in FEATURE_IDS:
        out["third_feature"] = tf
    tc = raw.get("third_card")
    if out["third_feature"] and isinstance(tc, str) and tc.strip():
        out["third_card"] = tc.strip()
    return out


def _write_state(cur: dict) -> Optional[str]:
    """The one write to second-card.json, called with the whole state
    (master/combined/features/suggest/third_feature) so a write of one
    never drops another - `_write_switch`, `_write_suggest` and
    `_write_third` all build `cur` from `_read_switches()` first. None on
    success, else the error in words."""
    p = _state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"master": cur["master"], "combined": cur["combined"],
                                   "features": cur["features"], "suggest": cur["suggest"],
                                   "third_feature": cur.get("third_feature"),
                                   "third_card": cur.get("third_card"),
                                   "set_at": int(time.time())}, indent=1),
                       encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        return f"could not save the switch ({type(exc).__name__})"
    return None


def _write_switch(feature: str, enabled: bool) -> Optional[str]:
    """Sets one switch. None on success, else the error in words."""
    with _STATE_LOCK:
        cur = _read_switches()
        if feature in ("master", "combined"):
            cur[feature] = bool(enabled)
        else:
            cur["features"][feature] = bool(enabled)
        return _write_state(cur)


def _write_third(feature: Optional[str], card_uuid: Optional[str] = None) -> Optional[str]:
    """Sets which feature (if any) is moved onto the third card, and the id
    of the card the owner approved it for. None on success, else the error in
    words. `feature` outside FEATURE_IDS is written as unassigned (None), and
    an assignment without a card id is written without one - which reads as
    "ask again" (_third_feature_now) - the safe direction both ways."""
    with _STATE_LOCK:
        cur = _read_switches()
        ok = feature in FEATURE_IDS
        cur["third_feature"] = feature if ok else None
        cur["third_card"] = (str(card_uuid) if ok and card_uuid else None)
        return _write_state(cur)


def _write_suggest(signal: str, enabled: bool) -> Optional[str]:
    """Sets one "suggest" switch - no card either way (see the "Suggesting
    the bigger model" section: it only changes whether Jarvis OFFERS to
    switch, never what it is allowed to do without asking)."""
    with _STATE_LOCK:
        cur = _read_switches()
        cur["suggest"][signal] = bool(enabled)
        return _write_state(cur)


# --------------------------------------------------------------------------
#   Detection
# --------------------------------------------------------------------------

def _gb(total_mb: int) -> str:
    g = total_mb / 1024.0
    return f"{g:.0f} GB" if abs(g - round(g)) < 0.05 else f"{g:.1f} GB"


def _not_capable(card) -> Optional[str]:
    """Why this card cannot be the second card, in plain words, or None."""
    name = card.name
    cc = card.compute_cap
    if cc is None:
        return (f"Jarvis could not tell which generation the {name} is (this driver "
                f"does not report it), so it is treated as not capable")
    if cc < MIN_COMPUTE:
        extra = ""
        if "P100" in name.upper():
            extra = (" - the P100 in particular cannot run the compressed models Jarvis "
                     "uses at speed (docs/MODEL-TOPOLOGY.md, 'If you are thinking about "
                     "a second card')")
        return (f"the {name} is older than Turing (the RTX 20 generation, compute "
                f"capability 7.5), which the second-card features need{extra}")
    if card.total_mb < MIN_TOTAL_MB:
        return (f"the {name} has {_gb(card.total_mb)}, which is not enough: the "
                f"extra-card features need at least 8 GB")
    if not card.uuid:
        return (f"nvidia-smi did not give the {name}'s id, and Jarvis only points work "
                f"at a card by its id")
    return None


def _preset_lanes() -> Optional[dict]:
    """jarvis_hardware.lane_plan(): where the lanes go under the preset the
    owner chose (docs/HARDWARE-PROFILES.md 4.3), or None - no preset chosen,
    or the module is missing - which means exactly today's behaviour below.
    Imported when asked, never at load."""
    try:
        import jarvis_hardware
        return jarvis_hardware.lane_plan()
    except Exception:
        return None


def detect(fresh: bool = False) -> dict:
    """`detected` in status(). Never raises."""
    try:
        plan = _preset_lanes()
        if plan is not None:
            return _detect_preset(plan, fresh)
        return _detect(fresh)
    except Exception as exc:
        return {"capable": False, "why": f"the graphics cards could not be read "
                                         f"({type(exc).__name__})",
                "primary": None, "second": None, "cards": [], "_second": None,
                "_lanes": [], "_third": None}


def _card_summary(card) -> dict:
    """The plain-dict shape det["second"] already uses, for one Device - shared
    by _detect() (so "second" is built from the same code as extra_lanes())
    and by extra_lanes() below. Never None: callers only pass a real card."""
    return {"uuid": card.uuid, "index": card.index, "name": card.name,
            "total_mb": card.total_mb, "compute_cap": card.compute_cap}


def extra_lanes(det: dict) -> list:
    """Every capable non-primary card BEYOND the one already running as
    "second" today - a third card, and a fourth, if they are ever plugged
    in - as det["second"]'s own plain-dict shape. [] on a 1- or 2-card PC,
    or under a chosen hardware preset (which is a separate, two-slot design -
    see the module docstring's "A THIRD CARD" section).

    This is READ-ONLY, forward-looking data: nothing here can be turned on
    yet, on this PC or any other - there is no switch, no approval action
    and no lane process for a third card today. Nothing in this module or
    any other calls this function yet; it exists so a later, dedicated pass
    that DOES build a third card's own lane has a real list of candidates to
    start from, instead of redoing _detect()'s own card-reading work. Never
    raises; a bad `det` (missing or malformed "_lanes") reads as []."""
    try:
        lanes = det.get("_lanes") or []
        return [_card_summary(c) for c in lanes[1:]]
    except Exception:
        return []


def _detect(fresh: bool) -> dict:
    cards = list(_cards(fresh))
    if not cards:
        return {"capable": False,
                "why": ("no NVIDIA graphics card could be read (nvidia-smi is missing "
                        "or did not answer)"),
                "primary": None, "second": None, "cards": [], "_second": None,
                "_lanes": [], "_third": None}
    prim, rule = _primary(cards)
    rows, candidates, reasons = [], [], []
    for c in sorted(cards, key=lambda d: d.index):
        if c is prim:
            continue
        r = _not_capable(c)
        if r is None:
            candidates.append(c)
        else:
            reasons.append((c, r))
    # Every capable non-primary card, best memory first - the same sort this
    # line always used to pick "second" alone. "second" is unchanged: it is
    # still lanes[0]. Keeping the WHOLE list (not just [0]) is the one real
    # change docs/GPU-SUPPORT-RESEARCH-2026-09-27.md's recommendation #1
    # asked for - see the module docstring's "A THIRD CARD" section. A
    # second (or third, ...) capable card that is not "second" still gets
    # its row in `rows` below, with the SAME "unused" role and "why" text as
    # before this change - nothing about what is SHOWN today has moved,
    # only what is kept internally for a card beyond the first two.
    lanes = sorted(candidates, key=lambda d: (-d.total_mb, d.index))
    second = lanes[0] if lanes else None
    for c in sorted(cards, key=lambda d: d.index):
        if c is prim:
            role, why = "primary", f"everyday chat runs here: {rule}"
        elif c is second:
            role, why = "second", "the second-card features would run here"
            if c.display_active:
                why += (" (a monitor is plugged into it, which uses some of its memory; "
                        "plug the monitors into the main card)")
        elif c in candidates:
            if c.total_mb < second.total_mb:
                role, why = "unused", f"capable, but the {second.name} has more memory"
            else:
                role, why = ("unused", f"capable, but the {second.name} has the same "
                             f"amount of memory and was already picked")
        else:
            role, why = "unused", next(r for (x, r) in reasons if x is c)
        rows.append({"index": c.index, "uuid": c.uuid or None, "name": c.name,
                     "total_mb": c.total_mb, "free_mb": c.free_mb,
                     "compute_cap": c.compute_cap, "display_active": c.display_active,
                     "role": role, "why": why})
    # The third card's own lane candidate (module docstring: "A THIRD
    # CARD'S OWN LANE") - lanes[1], the same object extra_lanes(det)'s first
    # entry describes, kept here too so _reconcile_third/lane_for never have
    # to re-derive it from _lanes themselves. None whenever there is no
    # second capable extra card (fewer than 3 capable cards total).
    third = lanes[1] if len(lanes) > 1 else None
    p = {"uuid": prim.uuid or None, "index": prim.index, "name": prim.name}
    if second is not None:
        s = _card_summary(second)
        if _is_small(second.total_mb):
            ok = [_BY_ID[f]["name"] for f in FEATURE_IDS
                  if _small_card_refusal(f, second) is None]
            no = [_BY_ID[f]["name"] for f in FEATURE_IDS
                  if _small_card_refusal(f, second) is not None]
            why = (f"the {second.name} ({_gb(second.total_mb)}) can take some of the "
                   f"extra-card features ({', '.join(ok) or 'none right now'}), which keeps "
                   f"that work off the {prim.name}; it holds no more than the {prim.name}, so "
                   f"{', '.join(no) or 'nothing else'} stay"
                   f"{'s' if len(no) == 1 else ''} off; everyday chat stays on the "
                   f"{prim.name}")
        else:
            why = (f"the {second.name} ({_gb(second.total_mb)}) can take the second-card "
                   f"features; everyday chat stays on the {prim.name}")
        return {"capable": True, "why": why, "primary": p, "second": s, "cards": rows,
                "_second": second, "_lanes": lanes, "_third": third}
    if len(cards) == 1:
        why = f"only one graphics card found (the {prim.name})"
    else:
        why = "; ".join(r for (_, r) in reasons)
    return {"capable": False, "why": why, "primary": p, "second": None, "cards": rows,
            "_second": None, "_lanes": lanes, "_third": third}


def _detect_preset(plan: dict, fresh: bool) -> dict:
    """`detected` under a chosen preset. The same shape as _detect's, plus
    `_plan`, `_main` (the lanes run inside the everyday Ollama, beside chat
    on one card) and `unsupported` ({feature: why} for a feature this
    preset has no model for)."""
    cards = list(_cards(fresh))
    chat, lane = plan["chat_card"], plan.get("lane_card")
    preset = {"fast": "Fastest answers", "smart": "Smartest answers",
              "features": "Most features"}.get(plan.get("preset"), "the chosen preset")

    def dev_for(card):
        if card is None or not getattr(card, "uuid", ""):
            return None
        return next((d for d in cards if d.uuid and d.uuid.lower() == card.uuid.lower()), None)

    chat_dev, lane_dev = dev_for(chat), dev_for(lane)
    unsupported = {}
    for f in FEATURE_IDS:
        key = "vision" if f == "vision" else "long_context"
        if key in plan.get("why_none", {}):
            unsupported[f] = plan["why_none"][key]
    main = lane is None
    capable = bool(plan.get("long") or plan.get("pictures"))
    why = ""
    if lane is not None and lane_dev is None:
        capable = False
        why = (f"the preset \"{preset}\" puts the extra features on the {lane.name}, but "
               f"nvidia-smi does not see that card now")
    elif not capable:
        why = f"the preset \"{preset}\" has no extra features on these cards"
    elif main:
        why = (f"the preset \"{preset}\" runs the extra features inside your everyday copy of "
               f"Ollama, beside chat on the {chat.name}")
    else:
        why = (f"the preset \"{preset}\" puts the extra features on the {lane.name}; everyday "
               f"chat stays on the {chat.name}")
    p = {"uuid": chat.uuid or None, "index": chat_dev.index if chat_dev else None,
         "name": chat.name}
    target = chat if main else lane
    tdev = chat_dev if main else lane_dev
    s = {"uuid": target.uuid or None, "index": tdev.index if tdev else None,
         "name": target.name,
         "total_mb": tdev.total_mb if tdev else int(round(target.total_gib * 1024)),
         "compute_cap": tdev.compute_cap if tdev else None}
    rows = []
    for c in sorted(cards, key=lambda d: d.index):
        if chat_dev is not None and c is chat_dev:
            role = "primary"
            why_c = f"everyday chat runs here (the preset \"{preset}\")"
            if main and capable:
                why_c += "; the extra features run beside it, in the same copy of Ollama"
        elif lane_dev is not None and c is lane_dev:
            role, why_c = "second", f"the extra features run here (the preset \"{preset}\")"
        else:
            role, why_c = "unused", f"the preset \"{preset}\" does not use it"
        rows.append({"index": c.index, "uuid": c.uuid or None, "name": c.name,
                     "total_mb": c.total_mb, "free_mb": c.free_mb,
                     "compute_cap": c.compute_cap, "display_active": c.display_active,
                     "role": role, "why": why_c})
    # A preset has exactly one lane slot (lane_card) - see the module
    # docstring's "A THIRD CARD" section for why that stays a separate,
    # two-slot design rather than growing a third slot here. `_lanes`
    # mirrors `_second` for shape-consistency with the non-preset path
    # above: [] when there is no lane card (or the lanes run inside the
    # everyday Ollama, main=True), else the one lane card, so
    # extra_lanes(det) is always safe to call and always answers [] under
    # a chosen preset today.
    lane_active = (not main) and capable and lane_dev is not None
    return {"capable": capable, "why": why, "primary": p, "second": s if capable else None,
            "cards": rows, "_second": None if main else lane_dev, "_main": main and capable,
            "_plan": plan, "unsupported": unsupported,
            "_lanes": [lane_dev] if lane_active else [],
            # A preset has no third slot either - see the comment above.
            "_third": None}


def _is_small(total_mb: int) -> bool:
    """An extra card under the full plan's floor (10 GiB): the 8 GB plan."""
    return int(total_mb) < FULL_TOTAL_MB


def _shows_monitor(card) -> bool:
    """Is a monitor plugged into this card? nvidia-smi not saying (None) reads
    as no, the way the rest of this module already reads it."""
    return bool(getattr(card, "display_active", False))


def _room_gib(total_mb: int, monitor: bool) -> float:
    """What is left of a card for a model, in GiB, after the desktop's share
    and the owner's empty gap (the small-card plan's comment above)."""
    return round(total_mb / 1024.0 - (DESKTOP_MONITOR_GIB if monitor else DESKTOP_GIB)
                 - GAP_GIB, 2)


def _small_8b_need(ctx: int) -> float:
    kv = QWEN8_KV_BYTES_PER_TOKEN * ctx / 1024 ** 3
    return round(QWEN8_WEIGHTS_GIB + kv + QWEN8_COMPUTE_GIB + CUDA_START_GIB, 2)


def _small_8b_plan(total_mb: int, monitor: bool) -> tuple:
    """(model, num_ctx, memory_gib) for an 8 GB card: the largest of
    SMALL_CTX_STEPS whose need fits the room, or (None, None, None)."""
    room = _room_gib(total_mb, monitor)
    for ctx in SMALL_CTX_STEPS:
        need = _small_8b_need(ctx)
        if ctx >= SMALL_MIN_CTX and need <= room:
            return LONG_BIG[0], ctx, need
    return None, None, None


def _small_vision_plan(total_mb: int, monitor: bool) -> tuple:
    """(model, num_ctx, memory_gib) for Pictures on an 8 GB card: 8,192
    tokens if it fits (the picture model's guessed size - see VISION_WEIGHTS_GIB),
    else (None, None, None)."""
    room = _room_gib(total_mb, monitor)
    ctx = SMALL_MIN_CTX
    need = _vision_gib(ctx)
    if need <= room:
        return VISION_MODEL, ctx, need
    return None, None, None


def _small_card_refusal(feature: str, card) -> Optional[str]:
    """Why `feature` cannot run on this card, in words - or None when it can.
    None for every card of 10 GiB and up (the full plan runs everything, as
    before this was written), so nothing about a 10/11/12 GB card moves. For an
    8 GB card: the arithmetic in the small-card plan's comment above."""
    if card is None or not _is_small(card.total_mb):
        return None
    name = getattr(card, "name", "this card")
    gb = _gb(card.total_mb)
    mon = _shows_monitor(card)
    if feature == "long_context":
        return (f"the {name} ({gb}) holds no more conversation than your main card "
                f"already does ({MAIN_CARD_CTX:,} tokens), so moving long "
                f"conversations there would not help. A card with 10 GB or more can hold "
                f"more")
    if feature == "browser_control":
        return (f"Browser control needs room for page after page of history, more than your "
                f"main card has, and the {name} ({gb}) has no more than the main card. A "
                f"card with 10 GB or more can do it")
    if feature == "vision":
        model, _, _ = _small_vision_plan(card.total_mb, mon)
        if model is None:
            room = _room_gib(card.total_mb, mon)
            need = _vision_gib(SMALL_MIN_CTX)
            return (f"the picture model needs about {need:.1f} GB and the {name} has about "
                    f"{room:.1f} GB to spare after the desktop"
                    f"{' and the monitor plugged into it' if mon else ''}"
                    f" and a safety gap"
                    + ("; plug the monitors into the main card and it may fit" if mon else ""))
        return None
    # learning, wiki: the 8B model at the largest context that fits.
    model, _, _ = _small_8b_plan(card.total_mb, mon)
    if model is None:
        return (f"the {name} has too little memory left after the desktop"
                f"{' and the monitor plugged into it' if mon else ''} and a safety gap "
                f"({_room_gib(card.total_mb, mon):.1f} GB) for the 8B model at a useful "
                f"conversation length")
    return None


def _unsupported(feature: str, det: dict, card=None) -> Optional[str]:
    """Why `feature` cannot run on the second card (or on `card`, the third),
    in words, or None. A chosen preset carries its own list (det["unsupported"],
    set by _detect_preset); without one, the card's own size decides."""
    if det.get("_plan") is not None:
        return (det.get("unsupported") or {}).get(feature)
    target = card if card is not None else det.get("_second")
    return _small_card_refusal(feature, target)


def _long_context_plan(total_mb: int, monitor: bool = False) -> tuple:
    """(model, num_ctx, memory_gib) for a second card with this much memory.
    From 10,240 MiB up, LONG_BIG/LONG_SMALL exactly as before; under it, the
    small-card plan (which may be (None, None, None) - nothing fits)."""
    if _is_small(total_mb):
        return _small_8b_plan(total_mb, monitor)
    return LONG_BIG if total_mb >= BIG_TOTAL_MB else LONG_SMALL


def _lane_ctx(card) -> int:
    """The context the lane's own OLLAMA_CONTEXT_LENGTH is set to, from the
    card's size. Each model call also names its own num_ctx (a feature's
    Lane carries it), so on an 8 GB card, where Pictures runs at 8,192 beside
    the 8B model's 16,384, this is only the default."""
    plan = _long_context_plan(card.total_mb, _shows_monitor(card))
    return int(plan[1]) if plan and plan[1] else SMALL_MIN_CTX


def _vision_gib(num_ctx: int) -> float:
    kv = VISION_KV_BYTES_PER_TOKEN * num_ctx / 1024 ** 3
    return round(VISION_WEIGHTS_GIB + kv + RUNTIME_GIB, 2)


def _feature_model(feature: str, det: dict, card=None) -> tuple:
    """(model, num_ctx, memory_gib) - all None without a capable card, or for
    a feature the card cannot run (an 8 GB card and "Longer conversations").

    `card` (2026-09-28): a specific jarvis_compute Device to size the plan
    from, instead of det["_second"] - used by the third card's own lane
    (_reconcile_third, describe_third_assign, status()'s "third" row) so
    its model/context/memory numbers come from THAT card's own total_mb,
    never borrowed from the second card's. Every existing caller omits it
    and gets exactly det["_second"]'s numbers, unchanged. Presets ignore
    it (a preset's own plan already names one lane; there is no third
    slot to size - module docstring)."""
    plan = det.get("_plan")
    if plan is not None:
        if not det.get("capable"):
            return None, None, None
        lane = plan.get("pictures") if feature == "vision" else plan.get("long")
        return tuple(lane) if lane else (None, None, None)
    target = card if card is not None else det.get("_second")
    if target is None:
        return None, None, None
    monitor = _shows_monitor(target)
    if _is_small(target.total_mb):
        if _small_card_refusal(feature, target) is not None:
            return None, None, None
        if feature == "vision":
            return _small_vision_plan(target.total_mb, monitor)
        return _small_8b_plan(target.total_mb, monitor)
    model, ctx, gib = _long_context_plan(target.total_mb)
    if feature == "vision":
        return VISION_MODEL, ctx, _vision_gib(ctx)
    return model, ctx, gib


def _combined_rows(det: dict) -> tuple:
    """(primary row, second row) from det["cards"] - the same rows detect()
    already builds for both the plain and the preset paths, each with
    name/uuid/total_mb/compute_cap. Either may be None."""
    rows = det.get("cards") or []
    prim = next((r for r in rows if r.get("role") == "primary"), None)
    second = next((r for r in rows if r.get("role") == "second"), None)
    return prim, second


def _combined_alone_note(det: dict) -> str:
    """One sentence when the SECOND card alone has room for COMBINED_MODEL (a
    16 or 24 GB card, 2026-09-30): "One bigger model on both cards" is meant
    for a model bigger than either card holds alone, so there splitting it
    across both only adds the slower card's pace. "" otherwise. Not a refusal:
    the owner may still want it, and the switch and its card are unchanged."""
    try:
        _, second = _combined_rows(det)
        total = int((second or {}).get("total_mb") or 0)
        model, ctx, gib = COMBINED_MODEL
        need = round(gib - 0.57, 2)     # one card's runtime, not two (12.28 - 1.20 + 0.63)
        if total and _room_gib(total, False) >= need:
            return (f"The {second.get('name')} ({_gb(total)}) alone has room for {model}, so "
                    f"splitting it across both cards is not needed for size and can only slow "
                    f"it down to the slower card's pace.")
    except Exception:
        pass
    return ""


def _combined_capable(det: dict) -> tuple:
    """(ok, why) for "One bigger model on both cards" - not det["capable"]
    (that only checks the SECOND card; this mode runs on the PRIMARY one
    too, so it must pass the same Turing/q8_0 floor - HARDWARE-PROFILES.md
    2.2: flash attention is "auto" only when EVERY card passes Ollama's
    gate). The combined-memory floor (COMBINED_MODEL's comment) applies to
    the two cards' TOTAL, never to either one alone - the primary card
    (today's 2080 Super, 8 GB) is well under MIN_TOTAL_MB by itself, and
    that is fine: it only has to hold its own share of the split model."""
    prim, second = _combined_rows(det)
    if prim is None or second is None:
        return False, "needs two graphics cards; only one is here"
    for row, which in ((prim, "the everyday card"), (second, "the second card")):
        name = row.get("name") or which
        cc = row.get("compute_cap")
        if cc is None:
            return False, (f"{which} ({name}): this driver does not report which generation "
                           f"it is, so it is treated as not capable")
        if cc < MIN_COMPUTE:
            return False, (f"{which} ({name}) is older than Turing (compute capability {cc}, "
                           f"needs {MIN_COMPUTE}) - it cannot use the compact conversation "
                           f"cache this mode needs on every card it runs on")
        if not row.get("uuid"):
            return False, f"{which} ({name}) has no id from nvidia-smi"
    total = int(prim.get("total_mb") or 0) + int(second.get("total_mb") or 0)
    if total < COMBINED_MIN_TOTAL_MB:
        return False, (f"the two cards together have {_gb(total)}, not the "
                       f"{_gb(COMBINED_MIN_TOTAL_MB)} a genuinely bigger model needs")
    return True, ""


# --------------------------------------------------------------------------
#   Is the model there?
# --------------------------------------------------------------------------

_TAGS: dict = {}          # url -> (names, when)
_TAGS_SECONDS = 30.0


def _installed_names(url: str) -> Optional[set]:
    hit = _TAGS.get(url)
    now = time.monotonic()
    if hit and now - hit[1] < _TAGS_SECONDS:
        return hit[0]
    try:
        body = _http_json(f"{url}/api/tags", timeout=2.0)
        names = set()
        for m in body.get("models") or []:
            for k in ("name", "model"):
                if isinstance(m.get(k), str):
                    names.add(m[k])
    except Exception:
        return None
    _TAGS[url] = (names, now)
    return names


def _model_installed_on(model: Optional[str], url: str) -> Optional[bool]:
    """Is `model` installed, asked at `url`? None: not answered, or `url`
    is not loopback."""
    if not model or not _is_loopback_url(url):
        return None
    names = _installed_names(url)
    if names is None:
        return None
    want = {model, model + ":latest"} if ":" not in model else {model}
    return bool(want & names)


def _model_installed(model: Optional[str]) -> Optional[bool]:
    """Asks the second Ollama when it runs, else the everyday one (both read
    the same model folder). None: neither answered, or the everyday one is
    not on this PC (it is not asked then)."""
    url = _LANE.url() if _LANE.state == "running" else _main_ollama_url()
    return _model_installed_on(model, url)


# --------------------------------------------------------------------------
#   The second Ollama
# --------------------------------------------------------------------------

def lane_env(uuid, *, port: int, num_ctx: int, host: str = HOST,
             base: Optional[dict] = None, flash: str = "auto",
             keep_alive: str = "30m", fit_target: Optional[str] = None,
             spread: bool = False) -> dict:
    """The environment for the second (or combined) `ollama serve`. Raises
    ValueError for a host that is not 127.0.0.1 (rule 2) or an id that is
    not a card id.

    `uuid` is a single card id (str, the classic per-feature lane - one
    CUDA_VISIBLE_DEVICES entry) or a sequence of them ("combined": no pin to
    one card, so Ollama's own scheduler places the model's layers across
    every id listed - MODEL-TOPOLOGY.md). `spread=True` sets
    OLLAMA_SCHED_SPREAD=1, so combined mode always uses every card listed
    rather than trusting Ollama's own (over-counting, for a q8_0 cache -
    HARDWARE-PROFILES.md 2.5) prediction of whether the model fits on one.

    Built from an allowlist (jarvis_child_env.py, bug audit 3 CONN-2): what
    Windows needs to start a program, plus OLLAMA_MODELS if the owner set it
    (so the second Ollama finds the models already downloaded). Nothing else
    of Jarvis's environment - not the pairing token, not any other *_TOKEN,
    *_KEY, *_PASSWORD or *_SECRET - reaches the second Ollama."""
    if host != HOST:
        raise ValueError(f"the second Ollama only ever listens on {HOST}, not {host!r}")
    ids = (uuid,) if isinstance(uuid, str) else tuple(uuid)
    if not ids or not all(re.fullmatch(r"GPU-[0-9A-Fa-f-]{8,64}", str(i or "")) for i in ids):
        raise ValueError("the second Ollama is only pinned by a card id (GPU-...)")
    port = int(port)
    if not (1024 <= port <= 65535) or port == MAIN_OLLAMA_PORT:
        raise ValueError(f"port {port} cannot be used for the second Ollama")
    env = jarvis_child_env.inherited(base, names=("OLLAMA_MODELS",))
    # Inherited settings that would widen or reshape it are removed first.
    # (The allowlist above already leaves them out; kept, so a name added to
    # it later cannot quietly bring one back.)
    for k in ("OLLAMA_HOST", "OLLAMA_ORIGINS", "OLLAMA_SCHED_SPREAD",
              "OLLAMA_FLASH_ATTENTION", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
              "GPU_DEVICE_ORDINAL", "GGML_VK_VISIBLE_DEVICES"):
        env.pop(k, None)
    env.update({
        "OLLAMA_HOST": f"{HOST}:{port}",
        "CUDA_VISIBLE_DEVICES": ",".join(ids),
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_CONTEXT_LENGTH": str(int(num_ctx)),
        "OLLAMA_KEEP_ALIVE": keep_alive,
        # Vulkan is on by default and ignores CUDA_VISIBLE_DEVICES: off, so
        # this Ollama sees the second card only (see the module docstring).
        "OLLAMA_VULKAN": "0",
        # Ollama's own refusal of its cloud models and web search, behind
        # Jarvis's refusal by name (rule 1, twice).
        "OLLAMA_NO_CLOUD": "1",
    })
    if flash == "on":
        env["OLLAMA_FLASH_ATTENTION"] = "1"
    elif flash == "off":
        env["OLLAMA_FLASH_ATTENTION"] = "0"
    if spread:
        # Always give every id in `ids` to llama.cpp's own layer split
        # (server/sched.go's bestSingleGPUFit otherwise tries one card
        # first, using Ollama's own VRAM guess - MODEL-TOPOLOGY.md) - this
        # mode's whole point is running on every card listed, not whichever
        # one Ollama's guess thinks is enough.
        env["OLLAMA_SCHED_SPREAD"] = "1"
    if fit_target is not None:
        # Under a chosen preset only: the empty gap llama.cpp keeps on the
        # card, in MiB (the owner's 0.75 GB, docs/HARDWARE-PROFILES.md
        # decision 1). Without a preset it is llama.cpp's own 1 GB, as today.
        if not re.fullmatch(r"\d{1,5}", str(fit_target)):
            raise ValueError("the empty-gap setting must be a whole number of MiB")
        env["LLAMA_ARG_FIT_TARGET"] = str(fit_target)
    return env


def _version_at(port: int) -> Optional[dict]:
    try:
        v = _http_json(f"http://{HOST}:{port}/api/version", timeout=1.0)
        return v if isinstance(v, dict) and "version" in v else None
    except Exception:
        return None


class _LaneProcess:
    """One `ollama serve` that this module started, or none."""

    START_SECONDS = 30.0
    RETRY_SECONDS = 60.0

    def __init__(self, role: str = "second") -> None:
        self.lock = threading.RLock()
        self.state = "off"
        self.why = "nothing on the second card is switched on"
        self.proc = None
        self.port = DEFAULT_PORT
        self.uuid = ""
        self.card = ""
        self.num_ctx = 0
        self.failed_at = -1e9
        self.gen = 0
        self.claimed = ()          # the card id(s) whose claim this lane holds
        self.fit = None            # LLAMA_ARG_FIT_TARGET under a preset, else None
        self.spread = False        # OLLAMA_SCHED_SPREAD=1 ("combined": every id, not one)
        #: "second", "combined" or "third" - which log file (_log_path)
        #: and, for "third", which port default this instance uses. The
        #: class itself carries no other assumption about which lane it is
        #: (module docstring's "THE LANE PROCESS" section).
        self.role = role

    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def alive(self) -> bool:
        p = self.proc
        try:
            return p is not None and p.poll() is None
        except Exception:
            return False

    def ensure(self, uuid, card: str, num_ctx: int, fit: Optional[str] = None,
               spread: bool = False, port: Optional[int] = None) -> None:
        """`port`: the caller's own port, when it must not share _LANE's/
        _COMBINED_LANE's (the third lane - module docstring's "THE PORT AND
        THE LOG" section). None (every existing caller) means _port(),
        exactly as before this parameter was added."""
        with self.lock:
            port = port if port is not None else _port()
            same = (self.uuid == uuid and self.num_ctx == num_ctx and self.port == port
                    and self.fit == fit and self.spread == spread)
            if self.state in ("running", "starting") and same and self.alive():
                return
            if self.state == "running" and same and not self.alive():
                code = self._exit_code()
                self._clear()
                self._drop_card()
                self._fail(f"the second Ollama stopped by itself (exit code {code}); "
                           f"Jarvis will try again in a minute. Its log: {_log_path(self.role)}")
                return
            if self.state == "failed" and same and \
                    time.monotonic() - self.failed_at < self.RETRY_SECONDS:
                return
            if self.proc is not None:
                self._stop_proc()
            self.fit = fit
            self.spread = spread
            self._start(uuid, card, num_ctx, port)

    def _exit_code(self):
        try:
            return self.proc.poll()
        except Exception:
            return "unknown"

    def _clear(self) -> None:
        self.proc = None

    def _fail(self, why: str) -> None:
        self.state, self.why, self.failed_at = "failed", why, time.monotonic()

    def _drop_card(self) -> None:
        """Gives back every card's claim this lane holds, once no process
        of ours is on it."""
        ids, self.claimed = self.claimed, ()
        for u in ids:
            _release_card(u)

    def hold(self, why: str) -> None:
        """Not started, and not a failure: something else (the big model)
        is using the card. Tried again on the next look."""
        with self.lock:
            if self.proc is not None:
                self._stop_proc()
            self.state, self.why = "off", why

    def _start(self, uuid: str, card: str, num_ctx: int, port: int) -> None:
        self.uuid, self.card, self.num_ctx, self.port = uuid, card, num_ctx, port
        exe = _which("ollama")
        if not exe:
            return self._fail("Ollama was not found on this PC's PATH, so the second "
                              "copy could not be started")
        if _port_taken(port) or _version_at(port) is not None:
            if _version_at(port) is not None:
                return self._fail(
                    f"something that answers like Ollama is already using {HOST}:{port}, "
                    f"and Jarvis did not start it, so Jarvis will neither use it nor stop "
                    f"it. Close it, or set another port under [second_card] in "
                    f"jarvis-framework.toml")
            return self._fail(f"another program is already using {HOST}:{port}; set "
                              f"another port under [second_card] in jarvis-framework.toml")
        refused = _flash_refusal()
        if refused:
            return self._fail(refused)
        try:
            env = lane_env(uuid, port=port, num_ctx=num_ctx, flash=_flash_setting(),
                           keep_alive=_keep_alive(), fit_target=self.fit, spread=self.spread)
        except ValueError as exc:
            return self._fail(str(exc))
        # The card's claim, taken BEFORE the process starts, on EVERY id in
        # `uuid` (a str, or a tuple of ids for the combined lane).
        # jarvis_big_model takes the same claim before it starts colibri on
        # a card, so the two can never both be starting on it, whatever the
        # timing. If a later id in the list is already held, every id
        # claimed so far in this attempt is given back at once - never a
        # partial claim of only some of the cards this lane needs.
        ids = (uuid,) if isinstance(uuid, str) else tuple(uuid)
        got, held_why = [], None
        for u in ids:
            held = _claim_card(u)
            if held is not None:
                held_why = big_model_holds(u, card) or f"the big model is starting on the {card}"
                break
            got.append(u)
        if held_why is not None:
            for u in got:
                _release_card(u)
            self.state = "off"
            self.why = held_why
            return None
        self.claimed = tuple(got)
        kwargs: dict = {"env": env, "stdin": subprocess.DEVNULL}
        log = None
        try:
            _log_path(self.role).parent.mkdir(parents=True, exist_ok=True)
            log = open(_log_path(self.role), "wb")
            kwargs["stdout"] = log
            kwargs["stderr"] = subprocess.STDOUT
        except OSError:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        if os.name == "nt":
            # No console window, and its own group so stopping it is clean.
            kwargs["creationflags"] = 0x08000000 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        try:
            self.proc = _popen([exe, "serve"], **kwargs)
        except Exception as exc:
            self.proc = None
            self._drop_card()
            return self._fail(f"the second Ollama could not be started ({type(exc).__name__})")
        finally:
            if log is not None:
                try:
                    log.close()      # the child has its own handle
                except Exception:
                    pass
        self.gen += 1
        gen = self.gen
        self.state = "starting"
        self.why = (f"starting a second copy of Ollama on {HOST}:{port}, using only "
                    f"the {card}")
        _spawn(lambda: self._wait_healthy(gen))

    def _wait_healthy(self, gen: int) -> None:
        deadline = time.monotonic() + self.START_SECONDS
        while time.monotonic() < deadline:
            with self.lock:
                if gen != self.gen or self.state != "starting":
                    return
                if not self.alive():
                    code = self._exit_code()
                    self._clear()
                    self._drop_card()
                    return self._fail(f"the second Ollama stopped straight away (exit code "
                                      f"{code}). Its log: {_log_path(self.role)}")
            if _version_at(self.port) is not None:
                with self.lock:
                    if gen == self.gen and self.state == "starting":
                        self.state = "running"
                        self.why = (f"running on {HOST}:{self.port} (this PC only), using "
                                    f"only the {self.card}")
                return
            _sleep(0.5)
        with self.lock:
            if gen == self.gen and self.state == "starting":
                self._stop_proc()
                self._fail(f"the second Ollama did not answer within "
                           f"{self.START_SECONDS:.0f} seconds. Its log: {_log_path(self.role)}")

    def _stop_proc(self) -> None:
        p, self.proc = self.proc, None
        self.gen += 1
        self._drop_card()
        if p is None:
            return
        try:
            if p.poll() is not None:
                return
        except Exception:
            return
        _kill_tree(p)

    def stop(self, why: str) -> None:
        with self.lock:
            self._stop_proc()
            self.state, self.why = "off", why

    def pids(self) -> set:
        """Our process and everything it started (for the pin check)."""
        p = self.proc
        if p is None or not self.alive():
            return set()
        return _tree(p.pid)


def _kill_tree(p) -> None:
    """Stops a process THIS module started, and what it started. Never
    called with any other process. Replaced in tests."""
    try:
        if os.name == "nt":
            # The whole tree of this one process: `ollama serve` starts a
            # runner per model, and stopping the parent alone would leave the
            # runner holding the card's memory.
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            import signal
            try:
                # Its own session (start_new_session=True), so this group
                # is exactly it and its children.
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                p.terminate()
        p.wait(timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _tree(root: int) -> set:
    """`root` and its descendants. Best effort; {root} when unreadable."""
    parents: dict = {}
    try:
        if os.name == "nt":
            parents = _win_parents()
        else:
            for d in Path("/proc").iterdir():
                if d.name.isdigit():
                    try:
                        stat = (d / "stat").read_text()
                        ppid = int(stat[stat.rindex(")") + 2:].split()[1])
                        parents[int(d.name)] = ppid
                    except Exception:
                        continue
    except Exception:
        return {root}
    out, frontier = {root}, [root]
    while frontier:
        cur = frontier.pop()
        for pid, ppid in parents.items():
            if ppid == cur and pid not in out:
                out.add(pid)
                frontier.append(pid)
    return out


def _win_parents() -> dict:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {}
    out = {}
    try:
        e = PROCESSENTRY32()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k32.Process32First(snap, ctypes.byref(e))
        while ok:
            out[int(e.th32ProcessID)] = int(e.th32ParentProcessID)
            ok = k32.Process32Next(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


_LANE = _LaneProcess("second")
_COMBINED_LANE = _LaneProcess("combined")
#: The third card's own lane (module docstring's "A THIRD CARD'S OWN LANE").
#: A literal third instance, not a dict - see the docstring's "THE LANE
#: PROCESS" section for why that is the deliberate, documented choice.
_THIRD_LANE = _LaneProcess("third")


def _third_feature_now(sw: dict, det: dict) -> Optional[str]:
    """Which feature runs on the third card RIGHT NOW: the stored assignment,
    but only while the card in the third slot is the very card the owner
    approved it for (2026-09-30). None when there is no third card, under a
    preset, when nothing is assigned, when the card in the slot is a different
    one (swapped, moved to another slot, another added), or when the saved file
    has no card id (it is from before the id was kept: ask again). The choice
    stays SAVED in every one of those cases - it is just not acted on, so a
    lane never starts on a card the owner did not approve."""
    third = det.get("_third")
    feature = sw.get("third_feature")
    if third is None or det.get("_main") or not feature:
        return None
    saved = str(sw.get("third_card") or "").strip().lower()
    if not saved or saved != str(getattr(third, "uuid", "") or "").strip().lower():
        return None
    return feature


def _third_stale_why(sw: dict, det: dict) -> str:
    """In words, why a SAVED third-card assignment is not being acted on, or ""
    when it is being acted on (or nothing is saved / no third card)."""
    third = det.get("_third")
    feature = sw.get("third_feature")
    if third is None or det.get("_main") or not feature or _third_feature_now(sw, det):
        return ""
    name = f"\"{_BY_ID[feature]['name']}\""
    if not str(sw.get("third_card") or "").strip():
        return (f"{name} was moved to the third card before Jarvis kept track of which card you "
                f"approved. Your choice is kept, but to be safe nothing runs on the {third.name} "
                f"until you approve the move again.")
    return (f"{name} was moved to a different graphics card than the one in the third slot now "
            f"(the {third.name}). Your choice is kept, but nothing runs on the {third.name} "
            f"until you approve moving it there.")


def _on_third(feature: str, sw: dict, det: dict) -> bool:
    """Is `feature` moved onto a third card RIGHT NOW (a capable third card
    is here, this is not a preset, the switch points at it, and it is the card
    the owner approved)? Module docstring's "A THIRD CARD'S OWN LANE"."""
    return _third_feature_now(sw, det) == feature


def _wanted(sw: dict, det: dict) -> bool:
    # A feature moved onto the third card does not need the SECOND card's
    # own lane - if every active feature has been moved there, starting
    # the second lane too would hold the second card open for nothing
    # (2026-09-28).
    return bool(not sw.get("combined") and sw["master"] and det.get("capable")
                and any(_feature_active(f, sw, det) and not _on_third(f, sw, det)
                        and not _model_free(f) for f in FEATURE_IDS))


def _feature_active(feature: str, sw: dict, det: dict, card=None) -> bool:
    """`card`: the third card, when asking whether the feature can run THERE
    (its own size decides for an 8 GB card); None means the second card."""
    return bool(det.get("capable") and sw["master"] and sw["features"].get(feature)
                and _unsupported(feature, det, card) is None
                and all(sw["features"].get(d) for d in _BY_ID[feature]["needs"]))


def _idle_why(sw: dict, det: dict) -> str:
    """Why the second lane is off, when nothing wants it - in words. Says
    "moved to the third card" rather than "nothing switched on" when that
    is the real reason (2026-09-28): a feature can be genuinely on and
    still leave the second lane idle."""
    if not det.get("capable"):
        return f"no capable second card: {det.get('why')}"
    if not sw["master"]:
        return "the second-card switch is off"
    moved = [f for f in FEATURE_IDS if _feature_active(f, sw, det) and _on_third(f, sw, det)]
    # (A model-free feature, "Referee suggestions", is on without a lane: the
    # second Ollama has nothing to start for it.)
    if moved:
        names = ", ".join(f"\"{_BY_ID[f]['name']}\"" for f in moved)
        return f"{names} {'is' if len(moved) == 1 else 'are'} moved to the third card"
    return "nothing on the second card is switched on"


def _reconcile(sw: dict, det: dict) -> None:
    """Start the second Ollama if something needs it, stop it if nothing does.
    While Jarvis is on standby (sleep()), it starts nothing."""
    try:
        if _still_asleep():
            if _LANE.state != "off" or _LANE.proc is not None:
                _LANE.stop(_ASLEEP["why"])
            else:
                _LANE.why = _ASLEEP["why"]
            return
        if det.get("_main"):
            # A chosen preset runs the lanes inside the everyday Ollama, on
            # the one card: no second copy is started (HARDWARE-PROFILES 4.3).
            why = "the extra features run inside your everyday copy of Ollama, beside chat"
            if _LANE.state != "off" or _LANE.proc is not None:
                _LANE.stop(why)
            else:
                _LANE.why = why
            return
        if _wanted(sw, det):
            second = det["_second"]
            ctx = _lane_ctx(second)
            plan = det.get("_plan")
            fit = None
            if plan is not None:
                ctx = max([x[1] for x in (plan.get("long"), plan.get("pictures")) if x] or [ctx])
                fit = plan.get("fit_target")
            ours = (_LANE.state in ("starting", "running") and _LANE.uuid == second.uuid
                    and _LANE.alive())
            if not ours:
                # The big model (colibri with [big_model] cuda = "on") may be
                # on this very card. It will not start while this lane runs
                # (jarvis_big_model._cuda_plan); this is the other direction.
                held = big_model_holds(second.uuid, second.name)
                if held:
                    _LANE.hold(held)
                    return
            _LANE.ensure(second.uuid, second.name, ctx, fit)
        elif _LANE.state != "off" or _LANE.proc is not None:
            _LANE.stop(_idle_why(sw, det))
        else:
            _LANE.why = _idle_why(sw, det)
    except Exception as exc:
        _LANE.state, _LANE.why = "failed", f"unexpected error ({type(exc).__name__})"


def _combined_conflict(sw: dict) -> bool:
    """Is a per-card feature genuinely on, so "One bigger model on both
    cards" must not run (it needs both cards to itself)?"""
    return bool(sw["master"] and any(sw["features"].get(f) for f in FEATURE_IDS
                                     if not _model_free(f)))


def _combined_wanted(sw: dict, det: dict) -> bool:
    if not sw.get("combined") or _combined_conflict(sw):
        return False
    ok, _ = _combined_capable(det)
    return ok


def _reconcile_combined(sw: dict, det: dict) -> None:
    """Start the combined Ollama (both cards, no pin) if it is wanted, stop
    it otherwise. The mirror of _reconcile, for the third mode."""
    lane = _COMBINED_LANE
    try:
        if _still_asleep():
            if lane.state != "off" or lane.proc is not None:
                lane.stop(_ASLEEP["why"])
            else:
                lane.why = _ASLEEP["why"]
            return
        if _combined_wanted(sw, det):
            prim, second = _combined_rows(det)
            ids = (prim["uuid"], second["uuid"])
            name = f"the {prim['name']} and the {second['name']}"
            _, ctx, _ = COMBINED_MODEL
            ours = (lane.state in ("starting", "running") and lane.uuid == ids and lane.alive())
            if not ours:
                held = big_model_holds(prim["uuid"], prim["name"]) \
                    or big_model_holds(second["uuid"], second["name"])
                if held:
                    lane.hold(held)
                    return
            lane.ensure(ids, name, ctx, spread=True)
        elif lane.state != "off" or lane.proc is not None:
            if _combined_conflict(sw):
                why = ("a second-card feature is on, and \"One bigger model on both cards\" "
                       "needs both cards to itself")
            elif not sw.get("combined"):
                why = "\"One bigger model on both cards\" is off"
            else:
                ok, why2 = _combined_capable(det)
                why = why2 or "not ready"
            lane.stop(why)
        else:
            if not sw.get("combined"):
                lane.why = "\"One bigger model on both cards\" is off"
            elif _combined_conflict(sw):
                lane.why = ("a second-card feature is on, and \"One bigger model on both cards\" "
                           "needs both cards to itself")
            else:
                ok, why2 = _combined_capable(det)
                lane.why = why2 or "not ready"
    except Exception as exc:
        lane.state, lane.why = "failed", f"unexpected error ({type(exc).__name__})"


def _reconcile_third(sw: dict, det: dict) -> None:
    """Start the third card's own copy of Ollama if a feature is assigned
    to it, stop it otherwise - the mirror of _reconcile, for _THIRD_LANE
    (module docstring's "A THIRD CARD'S OWN LANE" section). Its own
    function, not a loop over _LANE/_THIRD_LANE, for the same reason
    _reconcile_combined is its own function: there is no preset/_main case
    for a third card (presets stay two-slot - det["_third"] is always None
    then), and no "needs" chain beyond the assigned feature's own."""
    try:
        if _still_asleep():
            if _THIRD_LANE.state != "off" or _THIRD_LANE.proc is not None:
                _THIRD_LANE.stop(_ASLEEP["why"])
            else:
                _THIRD_LANE.why = _ASLEEP["why"]
            return
        third = det.get("_third")
        feature = _third_feature_now(sw, det)
        if third is None or not feature or feature not in _BY_ID:
            why = ("no capable third graphics card" if third is None
                   else _third_stale_why(sw, det) or "no feature is assigned to the third card")
            if _THIRD_LANE.state != "off" or _THIRD_LANE.proc is not None:
                _THIRD_LANE.stop(why)
            else:
                _THIRD_LANE.why = why
            return
        if not _feature_active(feature, sw, det, card=third):
            refused = _unsupported(feature, det, third)
            why = (f"\"{_BY_ID[feature]['name']}\" cannot run on this card: {refused}"
                   if refused else f"\"{_BY_ID[feature]['name']}\" is off")
            if _THIRD_LANE.state != "off" or _THIRD_LANE.proc is not None:
                _THIRD_LANE.stop(why)
            else:
                _THIRD_LANE.why = why
            return
        ctx = _lane_ctx(third)
        ours = (_THIRD_LANE.state in ("starting", "running") and _THIRD_LANE.uuid == third.uuid
                and _THIRD_LANE.alive())
        if not ours:
            # The big model may be on this very card too - the same check
            # _reconcile makes for the second card's own lane.
            held = big_model_holds(third.uuid, third.name)
            if held:
                _THIRD_LANE.hold(held)
                return
        _THIRD_LANE.ensure(third.uuid, third.name, ctx, port=_third_port())
    except Exception as exc:
        _THIRD_LANE.state, _THIRD_LANE.why = "failed", f"unexpected error ({type(exc).__name__})"


# --------------------------------------------------------------------------
#   Standby: the second card is freed too
# --------------------------------------------------------------------------
#
# Standby (jarvis_power_switch.py) promises to free the graphics card. With
# two cards that has to mean both: sleep() stops the second Ollama, which
# frees everything it held on that card, CUDA's own share included.
#
# It then has to STAY stopped. Both apps read GET /api/second-card every few
# seconds, and status() reconciles - so without this flag the next poll
# started the lane again, and standby freed the card for a few seconds.
# It wakes the way the main model does, "on demand": the next time the owner
# actually uses a second-card feature (lane_for), or when Jarvis leaves
# standby. Background learning is not the owner using it, so it does not
# wake the card; it waits, like the rest of Jarvis's own background work.

_ASLEEP = {"on": False, "why": ""}
_ASLEEP_LOCK = threading.Lock()
#: Features that run in the background on Jarvis's own schedule. They never
#: wake the card from standby.
_BACKGROUND = frozenset({"learning"})


def sleep(why: str = "Jarvis is on standby") -> dict:
    """Stop the second Ollama (and the third's, and the combined's) and keep
    them stopped until they are really needed or Jarvis leaves standby.
    {"stopped": bool, "sentence": str}. Never raises."""
    try:
        with _ASLEEP_LOCK:
            _ASLEEP.update(on=True, why=f"asleep: {why}")
        running = _LANE.state != "off" or _LANE.proc is not None
        running_combined = _COMBINED_LANE.state != "off" or _COMBINED_LANE.proc is not None
        running_third = _THIRD_LANE.state != "off" or _THIRD_LANE.proc is not None
        if running:
            _LANE.stop(_ASLEEP["why"])
        if running_combined:
            _COMBINED_LANE.stop(_ASLEEP["why"])
        if running_third:
            _THIRD_LANE.stop(_ASLEEP["why"])
        stopped = running or running_combined or running_third
        _audit("second_card.sleep", {"stopped": stopped})
        return {"stopped": stopped,
                "sentence": "The second graphics card was freed too." if stopped else ""}
    except Exception as exc:
        return {"stopped": False,
                "sentence": f"Could not stop the second graphics card ({type(exc).__name__})."}


def wake() -> None:
    """Allow the second Ollama to start again. It starts only when something
    needs it. Never raises."""
    with _ASLEEP_LOCK:
        _ASLEEP.update(on=False, why="")


def asleep() -> bool:
    return bool(_ASLEEP["on"])


def _still_asleep() -> bool:
    """Asleep, unless Jarvis has left standby since - then wake by itself.
    A power module that cannot be read leaves it asleep: the safe direction
    for a promise to keep the card free."""
    if not _ASLEEP["on"]:
        return False
    try:
        import jarvis_power
        if str(jarvis_power.current()) != "standby":
            wake()
            return False
    except Exception:
        pass
    return True


def lane_state() -> str:
    """"off", "starting", "running" or "failed": the second Ollama's state as
    last seen. Reads only; starts and stops nothing. jarvis_big_model.py asks
    this before it would put colibri on the second card (it will not while
    this lane is starting or running)."""
    try:
        return str(_LANE.state)
    except Exception:
        return "unknown"


def combined_lane_state() -> str:
    """"off", "starting", "running" or "failed": the combined Ollama's
    state as last seen. Reads only; starts and stops nothing."""
    try:
        return str(_COMBINED_LANE.state)
    except Exception:
        return "unknown"


def third_lane_state() -> str:
    """"off", "starting", "running" or "failed": the third card's own
    Ollama's state as last seen. Reads only; starts and stops nothing -
    lane_state()'s own shape, for the third lane."""
    try:
        return str(_THIRD_LANE.state)
    except Exception:
        return "unknown"


def shutdown() -> None:
    """Stops the second Ollama(s) if this module started them. At process
    exit."""
    try:
        _LANE.stop("Jarvis is shutting down")
    except Exception:
        pass
    try:
        _COMBINED_LANE.stop("Jarvis is shutting down")
    except Exception:
        pass
    try:
        _THIRD_LANE.stop("Jarvis is shutting down")
    except Exception:
        pass


atexit.register(shutdown)


# --------------------------------------------------------------------------
#   lane_for - the one call the rest of the backend makes
# --------------------------------------------------------------------------

def lane_for(feature: str) -> Optional[Lane]:
    """Where `feature`'s model calls go, or None to carry on exactly as
    before. Never raises."""
    try:
        if feature not in _BY_ID or _model_free(feature):
            return None         # a model-free feature has no lane to route to
        sw = _read_switches()
        # The cheap checks first: with the switches off (the default) this
        # reads one small file and returns, on every chat turn.
        if not sw["master"] or not sw["features"].get(feature):
            return None
        if not all(sw["features"].get(d) for d in _BY_ID[feature]["needs"]):
            return None
        if _ASLEEP["on"]:
            if feature in _BACKGROUND:
                return None     # Jarvis's own background work does not wake the card
            wake()              # the owner is using it: wake on demand
        det = detect()
        _reconcile(sw, det)
        _reconcile_third(sw, det)
        third = det.get("_third")
        on_third = _on_third(feature, sw, det)
        if not det.get("capable") or _unsupported(feature, det, third if on_third else None):
            return None
        model, ctx, _ = _feature_model(feature, det, card=third if on_third else None)
        if on_third:
            # Moved onto the third card (2026-09-28) - runs alongside the
            # second card's own lane, not instead of it.
            if _THIRD_LANE.state != "running":
                return None
            if not model or _model_installed_on(model, _THIRD_LANE.url()) is not True:
                return None
            url = _THIRD_LANE.url()
            if not _is_loopback_url(url):
                return None
            return Lane(url=url, model=model, num_ctx=int(ctx),
                        why=f"{_BY_ID[feature]['name']}: {model} on the {third.name} "
                            f"(your third graphics card)")
        if det.get("_main"):
            # A chosen preset with the lanes inside the everyday Ollama.
            url = _main_ollama_url()
            if not model or not _is_loopback_url(url) or _model_installed(model) is not True:
                return None
            return Lane(url=url, model=model, num_ctx=int(ctx),
                        why=(f"{_BY_ID[feature]['name']}: {model} beside chat on the "
                             f"{det['second']['name']}"))
        if _LANE.state != "running":
            return None
        if not model or _model_installed(model) is not True:
            return None
        url = _LANE.url()
        if not _is_loopback_url(url):
            return None
        return Lane(url=url, model=model, num_ctx=int(ctx),
                    why=f"{_BY_ID[feature]['name']}: {model} on the {det['_second'].name}")
    except Exception:
        return None


def combined_lane() -> Optional[Lane]:
    """Where "One bigger model on both cards" runs, or None. lane_for()'s
    shape, for the third mode: `jarvis_agent.choose_lane()` calls this as
    the fallback for an ordinary (non-picture) turn once vision and
    long_context have both said no - the same contract every other lane
    already has. Never raises."""
    try:
        sw = _read_switches()
        if not sw.get("combined") or _combined_conflict(sw):
            return None
        if _ASLEEP["on"]:
            wake()      # the owner is using it: wake on demand, like a feature lane
        det = detect()
        _reconcile_combined(sw, det)
        ok, _ = _combined_capable(det)
        if not ok:
            return None
        model, ctx, _ = COMBINED_MODEL
        if _COMBINED_LANE.state != "running":
            return None
        if not model or _model_installed_on(model, _COMBINED_LANE.url()) is not True:
            return None
        url = _COMBINED_LANE.url()
        if not _is_loopback_url(url):
            return None
        prim, second = _combined_rows(det)
        return Lane(url=url, model=model, num_ctx=int(ctx),
                    why=f"{COMBINED_NAME}: {model} across the {prim['name']} and {second['name']}")
    except Exception:
        return None


#: After the learning lane fails to answer, how long the learner goes back
#: to exactly what it did before this module: the main card, after the full
#: quiet wait (K13).
LEARN_RETRY_SECONDS = 600.0
_LEARN: dict = {"failed_at": -1e9, "short": False}


def _learning_lane() -> Optional[Lane]:
    """lane_for("learning"), unless it failed to answer in the last
    LEARN_RETRY_SECONDS."""
    if time.monotonic() - _LEARN["failed_at"] < LEARN_RETRY_SECONDS:
        return None
    return lane_for("learning")


def learning_idle_seconds(default: float) -> float:
    """How long the learner waits for a quiet spell. With the learner on the
    second card it no longer competes with chat, so a short pause is enough
    (10 s, never longer than it already was). Not while the lane has lately
    failed to answer: then the pass will run on the main card, which needs
    the full wait."""
    try:
        if _learning_lane() is not None:
            _LEARN["short"] = float(default) > 10.0
            return min(float(default), 10.0)
    except Exception:
        pass
    _LEARN["short"] = False
    return default


def generate(lane: Lane, prompt: str, *, timeout: float = 120.0) -> Optional[str]:
    """One non-streamed answer from the lane's model, or None. Loopback only.
    num_ctx matches the lane's OLLAMA_CONTEXT_LENGTH, so asking never makes
    Ollama reload the model at a different size."""
    if lane is None or not _is_loopback_url(lane.url):
        return None
    body = {"model": lane.model, "prompt": prompt, "stream": False, "think": False,
            "options": {"num_ctx": int(lane.num_ctx), "temperature": 0}}
    for attempt in (1, 2):
        try:
            out = _http_json(f"{lane.url}/api/generate", body, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if attempt == 1 and exc.code == 400 and "think" in body:
                body.pop("think", None)     # an Ollama or model without the field
                continue
            return None
        except Exception:
            return None
        text = out.get("response") if isinstance(out, dict) else None
        if not isinstance(text, str):
            return None
        return re.sub(r"(?s)<think>.*?</think>", "", text).strip()
    return None


def _skip_pass(prompt: str) -> Optional[str]:
    return None


def _say_skipped() -> None:
    print("  ! learning: the second card did not answer, so this pass was skipped rather "
          "than run on the main card after only a short pause. The next passes use the "
          "main card after the full wait; the second card is tried again in "
          f"{LEARN_RETRY_SECONDS / 60:.0f} minutes. What was said is looked at again on the "
          "pass after your next message.", file=sys.stderr)


def learning_llm(llm: Callable[[str], Optional[str]]) -> Callable[[str], Optional[str]]:
    """The learner's model call, moved to the second card when the
    "learning" feature is working there; `llm` itself otherwise.

    If the second card does not answer, and this pass waited only the short
    pause (learning_idle_seconds), the pass is SKIPPED - `llm` is not called
    - because the main card was never given the full quiet it needs (K13:
    it used to fall back to the main card after 10 seconds). For the next
    LEARN_RETRY_SECONDS the learner then does exactly what it did before
    this module existed: the full wait, then `llm`."""
    short, _LEARN["short"] = _LEARN["short"], False
    try:
        lane = _learning_lane()
    except Exception:
        lane = None
    if lane is None:
        if short:
            # The pause was shortened for a lane that is gone now.
            _say_skipped()
            return _skip_pass
        return llm

    def ask(prompt: str) -> Optional[str]:
        out = generate(lane, prompt)
        if out is not None:
            return out
        first = time.monotonic() - _LEARN["failed_at"] >= LEARN_RETRY_SECONDS
        _LEARN["failed_at"] = time.monotonic()
        if short:
            if first:
                _say_skipped()
            return None
        return llm(prompt)
    return ask


# --------------------------------------------------------------------------
#   "Study helper": the quiz module's model call, on the second card
# --------------------------------------------------------------------------
#
# jarvis_quiz.configure(call=...) is the quiz's one injection point, and the
# quiz imports nothing from this module (its import rule). So the wiring is
# done HERE: wire_study() (called once at startup by referee.patch's block,
# after the quiz is installed) hands the quiz study_call(), which asks
# lane_for("study") on every model call. The lane is up: the question or the
# mark is written by the second card's model. Off, or the lane is down or does
# not answer: the quiz's own default call runs, exactly as it did before this
# existed. Loopback only; nothing about the text or the answer is kept here.

class StudyReply(str):
    """The lane's reply text, carrying the model that wrote it (`.model`; ""
    for an everyday-model reply, which is a plain str). The quiz reads it off
    the reply of ITS OWN call, so two quizzes asking at once cannot label each
    other's marks: "Jarvis's guess" stays on the marks until the grader test
    has been run on THIS model too."""
    model: str = ""


#: Only for `call.active_model()` (the eval script and the quiz's fallback
#: probe): the model of the LAST call made on THIS thread. Never shared
#: between threads, so concurrent calls cannot mislabel each other.
_STUDY = threading.local()


def _study_chat(lane: Lane, system: str, user: str, schema: dict,
                num_predict: int) -> Optional[str]:
    """One structured /api/chat answer from the lane, or None. jarvis_quiz's
    default_call, pointed at the lane: same body, num_ctx = the lane's."""
    if lane is None or not _is_loopback_url(lane.url):
        return None
    body = {"model": lane.model, "stream": False, "think": False, "format": schema,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_predict": int(num_predict),
                        "num_ctx": int(lane.num_ctx)}}
    for attempt in (1, 2):
        try:
            out = _http_json(f"{lane.url}/api/chat", body, timeout=120.0)
        except urllib.error.HTTPError as exc:
            if attempt == 1 and exc.code == 400 and "think" in body:
                body.pop("think", None)     # a model that does not know `think`
                continue
            return None
        except Exception:
            return None
        if not isinstance(out, dict) or out.get("done_reason") == "length":
            return None
        msg = out.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        return content if isinstance(content, str) else None
    return None


def study_call(fallback: Optional[Callable] = None) -> Callable:
    """The quiz's model call: `call(system, user, schema, num_predict)` ->
    the reply's JSON text. On the second card while "Study helper" is working
    there; otherwise `fallback` (jarvis_quiz.default_call - the unchanged local
    behaviour), or an error when there is none. It raises on failure, as the
    quiz expects (it turns that into its plain "model_unavailable")."""
    def call(system: str, user: str, schema: dict, num_predict: int):
        lane = None
        try:
            lane = lane_for("study")
        except Exception:
            lane = None
        if lane is not None:
            out = _study_chat(lane, system, user, schema, num_predict)
            if out is not None:
                _STUDY.model = lane.model
                reply = StudyReply(out)
                reply.model = lane.model
                return reply
        _STUDY.model = ""
        if fallback is None:
            raise RuntimeError("the second card did not answer and there is no other model call")
        return fallback(system, user, schema, num_predict)

    call.active_model = lambda: getattr(_STUDY, "model", "")      # type: ignore[attr-defined]
    return call


def wire_study() -> str:
    """Hand jarvis_quiz the study call. Call it AFTER jarvis_quiz.install() (which
    resets the quiz's settings) - referee.patch's startup block does. Touches
    only the quiz's model call; the deck `keep` function is left alone. One
    banner line; never raises."""
    try:
        import jarvis_quiz
        jarvis_quiz.configure(call=study_call(jarvis_quiz.default_call))
        return "  study      Study helper wired (the quiz uses the second card only while that switch is on)"
    except Exception as exc:
        return f"  study      NOT WIRED ({type(exc).__name__}) - the quiz keeps using the everyday model"


def feature_active(feature: str) -> bool:
    """Is this second-card switch genuinely on right now: the main switch and
    the feature on, a capable second card here, and everything it needs on?
    For modules that must be switched on this way (jarvis_referee). Reads the
    state file and the card list; starts and stops nothing. Never raises;
    False when in doubt."""
    try:
        if feature not in _BY_ID:
            return False
        return bool(_feature_active(feature, _read_switches(), detect()))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Is the everyday Ollama kept off the second card?
# --------------------------------------------------------------------------

_UUID_RE = re.compile(r"GPU-[0-9A-Fa-f-]{8,64}")


def pin_command(primary_uuid: Optional[str]) -> Optional[str]:
    """One PowerShell line (5.1-safe) that pins the owner's everyday Ollama
    to the main card. None without a real card id.

    Two settings: CUDA_VISIBLE_DEVICES (only the main card, by its id) and
    OLLAMA_VULKAN=0, because Ollama's Vulkan route is on by default and does
    not read CUDA_VISIBLE_DEVICES - without it the everyday Ollama could still
    reach the second card (docs/HARDWARE-PROFILES.md, decision 3)."""
    if not primary_uuid or not _UUID_RE.fullmatch(primary_uuid):
        return None
    return ("[Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', "
            f"'{primary_uuid}', 'User'); "
            "[Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '0', 'User'); "
            "Write-Host 'Done. Now quit Ollama (right-click "
            "its icon by the clock, then Quit Ollama) and start it again from the Start "
            "menu. Nothing was written to any file.'")


def main_pin(det: dict) -> tuple:
    """(true | false | None, one sentence). Best effort, never raises."""
    try:
        return _main_pin(det)
    except Exception as exc:
        return None, f"Could not check ({type(exc).__name__})."


def _main_pin(det: dict) -> tuple:
    prim = det.get("primary")
    cards = det.get("cards") or []
    if not prim or not cards:
        return None, "No graphics card could be read, so there is nothing to check."
    if len(cards) < 2:
        return None, "Only one graphics card, so there is nothing to keep apart yet."
    prim_uuid = (prim.get("uuid") or "").lower()
    others = {(c.get("uuid") or "").lower(): c.get("name") for c in cards
              if c.get("role") != "primary" and c.get("uuid")}
    # `_COMBINED_LANE`'s own process runs on the second card BY DESIGN, not
    # as the "everyday Ollama" this check is looking for - excluding only
    # `_LANE`'s pids meant a running combined lane was reported as if it
    # were the everyday one crowding the second card (bug audit 2026-09-27,
    # backend finding #7). `_THIRD_LANE`'s own process runs on the third
    # card the SAME way, for the same reason (2026-09-28).
    ours = _LANE.pids() | _COMBINED_LANE.pids() | _THIRD_LANE.pids()
    text = _smi_apps()
    if text:
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            pname = parts[1].lower()
            gpu = parts[2].lower()
            if ("ollama" in pname or "llama" in pname) and gpu in others and pid not in ours:
                return False, (f"The everyday Ollama is using the {others[gpu]} right now, so "
                               f"it can take memory the second-card features need. Run the "
                               f"command below, then restart Ollama.")
    val = _user_env("CUDA_VISIBLE_DEVICES")
    if val is not None:
        if val.strip().lower() == prim_uuid and prim_uuid:
            vulkan = (_user_env("OLLAMA_VULKAN") or "").strip()
            if vulkan != "0":
                # CUDA_VISIBLE_DEVICES hides the second card from Ollama's
                # CUDA route only. Its Vulkan route (on by default, see
                # lane_env) can still put a model there - which is why the
                # command below now sets OLLAMA_VULKAN=0 as well. An owner who
                # ran the older one-setting command must not be told "pinned".
                return False, (f"Ollama's CUDA route is pinned to the {prim.get('name')}, "
                               f"but its Vulkan route is still on and can still use the "
                               f"second card. Run the command below (it now switches "
                               f"Vulkan off too), then restart Ollama.")
            return True, (f"Ollama is set to use only the {prim.get('name')} "
                          f"(CUDA_VISIBLE_DEVICES in your user settings). If you set it "
                          f"just now, quit Ollama and start it again.")
        return False, (f"CUDA_VISIBLE_DEVICES in your user settings is {val.strip()!r}, "
                       f"which is not the {prim.get('name')}'s id. Run the command below.")
    if _ON_WINDOWS:
        return False, ("The everyday Ollama is not pinned: it can see both cards and may put "
                       "models on the second one. Run the command below once, then restart "
                       "Ollama.")
    return None, "Could not tell from here (this check reads Windows' user settings)."


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def _what(f: dict, det: dict) -> str:
    """A feature's "what", said right for where it runs: under a chosen setup
    on one card, beside chat rather than on a second card."""
    if det.get("_main"):
        return f["what"].replace("on the second card", "beside chat, on the same card")
    return f["what"]


def _feature_row(f: dict, sw: dict, det: dict, lane_state: str, lane_why: str,
                 pending: list) -> dict:
    fid = f["id"]
    enabled = bool(sw["features"].get(fid))
    active = _feature_active(fid, sw, det)
    free = _model_free(fid)
    model, ctx, gib = (None, None, None) if free else _feature_model(fid, det)
    installed = _model_installed(model) if model else None
    main = bool(det.get("_main"))
    running = main or lane_state == "running"
    available = bool(active and running and installed is True)
    if free:
        # No model, no lane: nothing else has to be running for it to work.
        available = active
    missing = [d for d in f["needs"] if not sw["features"].get(d)]
    names = ", ".join(_BY_ID[d]["name"] for d in missing)
    unsupported = _unsupported(fid, det)
    if unsupported and det.get("capable"):
        why = (f"{'On' if enabled else 'Off'}, but {unsupported}. "
               + ("Your choice is kept." if enabled else
                  ("It cannot be turned on with this preset." if det.get("_plan") is not None
                   else "It cannot be turned on with this card.")))
    elif not det.get("capable"):
        if enabled:
            why = (f"On, but it cannot run: {det['why']}. Your choice is kept; it works "
                   f"again once a capable second card is back.")
        else:
            why = f"Needs a capable second graphics card: {det['why']}."
    elif not enabled:
        why = "Off."
        if fid in pending:
            why = "Off. A card to turn it on is waiting for your answer."
        elif missing:
            why += f" Needs {names} on first."
    elif not sw["master"]:
        why = "On, but the main second-card switch is off."
    elif missing:
        why = f"On, but it needs {names} to be on as well."
    elif free:
        why = ("Working: it compares the numbers you log with your targets on this PC and "
               "loads no model, so it uses none of the card's memory yet.")
    elif not running:
        why = f"On. The second copy of Ollama is {lane_state}: {lane_why}."
    elif installed is None:
        why = f"On, but Jarvis could not ask Ollama whether {model} is installed."
    elif installed is False:
        why = (f"On, but {model} is not installed yet. Install it (Brain, Models, or "
               f"'ollama pull {model}' in a terminal) and it starts working.")
    elif main:
        why = (f"Working: {model} in your everyday copy of Ollama, beside chat on the "
               f"{det['second']['name']}, with room for {ctx:,} tokens of conversation.")
    else:
        why = (f"Working: {model} on the {det['second']['name']}, with room for "
               f"{ctx:,} tokens of conversation.")
    return {"id": fid, "name": f["name"], "what": _what(f, det), "enabled": enabled,
            "active": active, "available": available, "needs": list(f["needs"]),
            "model": model, "model_installed": installed,
            "memory_gib": gib, "why": why,
            # True for a switch that loads no model at all (Referee suggestions):
            # an app shows no "model" line for it. Optional for a reader.
            "model_free": bool(free)}


def status() -> dict:
    """GET /api/second-card. No token, no key, no secret in it: card ids are
    hardware ids. Never raises."""
    sw = _read_switches()
    det = detect()
    _reconcile(sw, det)
    _reconcile_combined(sw, det)
    _reconcile_third(sw, det)
    lane_state, lane_why = _LANE.state, _LANE.why
    with _PENDING_LOCK:
        pending = [f for f in ("master", "combined", "third") + FEATURE_IDS
                   if f in _PENDING and not _PENDING[f].get("withdrawn")]
        last = dict(_LAST_ANY) or None
    feats = [_feature_row(f, sw, det, lane_state, lane_why, pending) for f in FEATURES]
    pinned, note = main_pin(det)
    prim = det.get("primary") or {}
    cmd = pin_command(prim.get("uuid")) if len(det.get("cards") or []) >= 2 else None
    detected = {k: det[k] for k in ("capable", "why", "primary", "second", "cards")}
    return {
        "detected": detected,
        "enabled": sw["master"],
        "active": bool(sw["master"] and det.get("capable")),
        "pending": pending,
        "lane": {"state": lane_state, "why": lane_why},
        "main_ollama_pinned": pinned,
        "pin_note": note,
        "pin_command": cmd,
        "features": feats,
        # How the last approval card ended (AP-6): {feature, outcome, why,
        # at}, or null when none has ended since Jarvis started.
        "last": last,
        # Whether this PC reads the WORDS in a picture when the model
        # answering cannot see it (jarvis_ocr.py, 2026-09-26): both apps
        # already read this route before a picture is sent.
        "picture_text": _picture_text(),
        # The third mode: "One bigger model on both cards" (2026-09-26). Not
        # one of "features" above - it does not compose with them, so both
        # apps show it as its own row, next to "features", in the same
        # Hardware screen.
        "combined": _combined_status(sw, det, pending),
        # A third capable card, and which of the five features (if any) is
        # moved onto it (2026-09-28) - see the module docstring's "A THIRD
        # CARD'S OWN LANE" section. Purely additive: every key above is
        # unchanged from before this was built.
        "third": _third_status(sw, det, pending),
        # "When to suggest the bigger model" (2026-09-27): the two switches
        # that decide whether Jarvis may OFFER "combined" on its own - never
        # what it may do without asking. Same screen, folded into this same
        # poll rather than a route of its own.
        "suggest": suggest_settings(),
    }


def _combined_status(sw: dict, det: dict, pending: list) -> dict:
    """The "combined" row of status(): the same shape as a features[] row,
    for the one switch that is not in FEATURES."""
    enabled = bool(sw.get("combined"))
    conflict = _combined_conflict(sw)
    ok, capable_why = _combined_capable(det)
    model, ctx, gib = COMBINED_MODEL
    lane = _COMBINED_LANE
    running = lane.state == "running"
    installed = _model_installed_on(model, lane.url() if running else _main_ollama_url())
    active = bool(enabled and ok and not conflict)
    if not ok:
        why = (f"On, but it cannot run: {capable_why}. Your choice is kept; it works again "
               f"once both cards are back." if enabled
               else f"Needs two capable graphics cards: {capable_why}.")
    elif conflict:
        why = ("On, but a second-card feature (Longer conversations, Pictures, Learning in "
               "the background, Browser control, Wiki builder or Study helper) is on too, "
               "and this mode "
               "needs both cards to itself. Turn the other one off first."
               if enabled else "Off.")
    elif not enabled:
        why = "Off. A card to turn it on is waiting for your answer." if "combined" in pending \
            else "Off."
    elif not running:
        why = f"On. The combined copy of Ollama is {lane.state}: {lane.why}"
    elif installed is None:
        why = f"On, but Jarvis could not ask Ollama whether {model} is installed."
    elif installed is False:
        why = (f"On, but {model} is not installed yet. Install it (Brain, Models, or "
               f"'ollama pull {model}' in a terminal) and it starts working.")
    else:
        prim, second = _combined_rows(det)
        why = (f"Working: {model} split across the {prim['name']} and the {second['name']}, "
               f"with room for {ctx:,} tokens. Runs at the slower card's pace - not measured "
               f"on your hardware yet.")
    return {"id": "combined", "name": COMBINED_NAME,
            "what": ("Loads one bigger model than either card holds alone, split across both "
                    "at once by Ollama's own scheduler. Ties up both cards: the second card's "
                    "other features cannot run while this does."),
            "enabled": enabled, "capable": ok, "capable_why": capable_why,
            "conflict": conflict, "active": active,
            "available": bool(active and running and installed is True),
            "model": model, "context": ctx, "memory_gib": gib, "why": why}


def _third_status(sw: dict, det: dict, pending: list) -> dict:
    """status()'s "third" key (2026-09-28): a capable third card, if any,
    and which of the five features (if any) the owner has moved onto it -
    never a default (module docstring's "A THIRD CARD'S OWN LANE" section,
    docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3). Purely additive:
    nothing else in status() reads or depends on this key."""
    third = det.get("_third")
    capable = third is not None and not det.get("_main")
    card = _card_summary(third) if capable else None
    # The SAVED choice, and the one being acted on (2026-09-30: only while the
    # card in the third slot is the one the owner approved it for).
    saved = sw.get("third_feature")
    assigned = _third_feature_now(sw, det)
    stale = _third_stale_why(sw, det) if capable else ""
    lane = _THIRD_LANE
    running = lane.state == "running"
    model = ctx = gib = installed = None
    if not capable:
        why = "No capable third graphics card is plugged in right now."
        if saved:
            why = (f"\"{_BY_ID[saved]['name']}\" was moved here, but there is no capable "
                   f"third card right now: {det.get('why') or 'no capable third card.'} Your "
                   f"choice is kept.")
    elif not assigned:
        why = (f"Not running anything. Assign one of the switches above to the {third.name} "
               f"to use it.")
        if stale:
            why = stale
        if "third" in pending:
            why = "A card to move a feature here is waiting for your answer."
    else:
        f = _BY_ID[assigned]
        active = _feature_active(assigned, sw, det, card=third)
        model, ctx, gib = _feature_model(assigned, det, card=third)
        installed = _model_installed_on(model, lane.url()) if running else None
        refused = _unsupported(assigned, det, third)
        if refused:
            why = f"\"{f['name']}\" is assigned here, but it cannot run on this card: {refused}."
        elif not active:
            why = f"\"{f['name']}\" is assigned here, but it is off. Turn it on above to use it."
        elif not running:
            why = f"On. The third copy of Ollama is {lane.state}: {lane.why}"
        elif installed is None:
            why = f"On, but Jarvis could not ask Ollama whether {model} is installed."
        elif installed is False:
            why = (f"On, but {model} is not installed yet. Install it (Brain, Models, or "
                   f"'ollama pull {model}' in a terminal) and it starts working.")
        else:
            why = (f"Working: {model} on the {third.name}, with room for {ctx:,} tokens - at "
                   f"the same time as the second card's own lane.")
    unavailable = ({f: _small_card_refusal(f, third) for f in FEATURE_IDS
                    if _small_card_refusal(f, third)} if capable and det.get("_plan") is None
                   else {})
    return {"capable": capable, "card": card, "assigned": assigned,
            # Which switches could be moved here right now - already ON,
            # so assigning them never turns anything on as a side effect
            # (module docstring: the assignment card only ever says WHERE).
            # Not one this card cannot run (an 8 GB card and "Longer
            # conversations" - 2026-09-30).
            "assignable": [f for f in FEATURE_IDS
                           if sw["master"] and sw["features"].get(f) and not _model_free(f) and f not in unavailable],
            # Additive (2026-09-30): {feature: why} for a switch this card
            # cannot run. The apps do not need it; it is here to be read.
            "unavailable": unavailable,
            "pending": "third" in pending,
            "lane": {"state": lane.state, "why": lane.why},
            "model": model, "context": ctx, "memory_gib": gib, "model_installed": installed,
            "why": why}


def _picture_text() -> dict:
    """{"available", "engine", "why"} from jarvis_ocr.status(); "not
    available" when that module is not here. Never raises."""
    try:
        import jarvis_ocr
        st = jarvis_ocr.status()
        return {"available": st.get("available") is True, "engine": str(st.get("engine") or ""),
                "why": str(st.get("why") or "")}
    except Exception:
        return {"available": False, "engine": "",
                "why": "The part of Jarvis that reads pictures (jarvis_ocr.py) is not installed."}


# --------------------------------------------------------------------------
#   Changing a switch
# --------------------------------------------------------------------------

_PENDING_LOCK = threading.Lock()
_PENDING: dict = {}        # feature -> {"id", "since", "withdrawn"}
_LAST: dict = {}           # feature -> how its last card ended
#: Every card switched off while it waited and not yet answered, by its id.
#: A SET, not a flag on _PENDING: a new ON replaces _PENDING[feature], and
#: the flag went with it - after two ON/OFF rounds, approving the FIRST
#: card turned the switch on although the owner's last word was OFF.
_WITHDRAWN: set = set()
#: The last card to end, whichever switch it was for: status()["last"].
_LAST_ANY: dict = {}


def _last_words(label: str, outcome: str, reason: str) -> str:
    """How the last card ended, in words the apps can show as they are.
    `outcome` is one of: enabled, denied, timed_out, refused, failed,
    withdrawn (timed_out is jarvis_gate's own word for a card nobody
    answered in time)."""
    reason = str(reason or "").strip().rstrip(".")
    if outcome == "enabled":
        return f"{label} was turned on."
    if outcome == "denied":
        return f"You said no, so {label} stays off."
    if outcome == "timed_out":
        return f"Nobody answered the card in time, so {label} stays off."
    if outcome == "withdrawn":
        return (f"You turned {label} off while its card was waiting, so approving that "
                f"card changed nothing.")
    if outcome == "failed":
        return f"{label} could not be turned on: {reason or 'an unexpected error'}."
    return f"{label} was not turned on: {reason or 'refused'}."


def _tier(action: str) -> str:
    return str(fw.action_tier(action)) if fw is not None else "unknown"


def action_for(feature: str) -> str:
    """The gate action a switch's ON card is raised under."""
    return BROWSER_ACTION if feature == "browser_control" else ACTION


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _shares_with_big_model() -> str:
    """One line for the card when the big model may use this card too, or
    ""."""
    bm = _big_model()
    try:
        on = bm is not None and bm._cuda_setting() == "on"
    except Exception:
        on = False
    if not on:
        return ""
    return ("\n\nThe big model is set to use this card too ([big_model] cuda = \"on\"). "
            "They never share it: while the big model is using the card, this waits "
            "until it stops.")


def _would_work(feature: str, sw: dict, det: Optional[dict] = None) -> list:
    """The features that are working once `feature` is turned on, given the
    owner's other switches as they are - every choice is kept while the
    main switch or a feature it needs is off, so approving one card can
    bring back others. In the apps' order."""
    after = {"master": sw["master"], "features": dict(sw["features"])}
    if feature == "master":
        after["master"] = True
    else:
        after["features"][feature] = True
    ok = det if det is not None else {"capable": True}
    return [f for f in FEATURE_IDS if _feature_active(f, after, ok)]


def _brings_browser(feature: str, sw: dict, det: Optional[dict] = None) -> bool:
    """Does saying yes to `feature`'s card start "Browser control" working
    (it was not before)? Then the card must not say nothing leaves."""
    ok = det if det is not None else {"capable": True}
    return ("browser_control" in _would_work(feature, sw, det)
            and not _feature_active("browser_control", sw, ok))


def _names(ids: list) -> str:
    names = [f"\"{_BY_ID[i]['name']}\"" for i in ids]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def describe_on(feature: str, det: dict, sw: Optional[dict] = None) -> str:
    """The approval card. Every word from here; what refusing costs is on it.
    It says exactly what starts if the owner says yes (AP-4)."""
    sw = sw if sw is not None else _read_switches()
    s = det["second"]
    p = det.get("primary") or {}
    card = f"the {s['name']} ({_gb(s['total_mb'])})"
    lane = (f"Jarvis uses only that card and listens on {HOST}:{_port()} — "
            f"this PC only, not your network or the internet.")
    if det.get("_main"):
        # A chosen preset with one card: the lanes are more models in the
        # everyday Ollama. No second copy starts.
        lane = ("It runs in your everyday copy of Ollama on this PC, beside chat on the same "
                "card - no second copy is started.")
        pics = (det.get("_plan") or {}).get("pictures_mode")
        if pics == "swap" and feature in ("vision", "master"):
            lane += (" There is not room for both at once: a message with a picture unloads "
                     "chat for a moment, and chat loads again on your next message (a few "
                     "seconds each way).")
    if _brings_browser(feature, sw, det):
        # AP-9: not "Nothing leaves this PC". The model stays here; the
        # browser tool it offers works real web pages.
        lane += (" \"Browser control\" also lets Jarvis offer to work web pages in your "
                 "browser: those pages are on the internet, so what it types or clicks "
                 "there reaches that website. Each thing it would do there is shown to you "
                 "on its own card first.")
    else:
        lane += " Nothing leaves this PC."
    lane += _shares_with_big_model()
    head = "Let Jarvis use the second graphics card?"
    if det.get("_main"):
        head = (f"Let Jarvis run extra models beside chat on the {s['name']}, as the setup you "
                f"chose says?")
    if feature == "master":
        back = _would_work("master", sw, det)
        if back:
            yes = (f"If you say yes: {_names(back)} start{'s' if len(back) == 1 else ''} "
                   f"working again at once - you left "
                   f"{'it' if len(back) == 1 else 'them'} switched on. {lane} Every other "
                   "feature stays off; each has its own switch and its own card.")
        else:
            yes = ("If you say yes: nothing starts yet. Each feature (Longer conversations, "
                   "Pictures, Learning in the background, Browser control, Wiki builder, "
                   "Study helper, Referee suggestions) has "
                   f"its own switch and its own card. Once one of them is on, {lane}")
        return (
            f"{head}\n\n"
            f"Which card: {card}.\n\n"
            f"{yes}\n\n"
            "If you did not just ask for this, say no.\n\n"
            f"If you say no: nothing changes. Everything keeps running on the "
            f"{p.get('name', 'main card')}.")
    f = _BY_ID[feature]
    if _model_free(feature):
        return _describe_model_free(f, det, card, p)
    model, ctx, gib = _feature_model(feature, det)
    mem = (f"about {gib:.1f} GB of the card's {_gb(s['total_mb'])}"
           + (" (an estimate: the picture model's size was not checked)"
              if feature == "vision" else ""))
    installed = _model_installed(model)
    inst = ""
    if det.get("_plan") is None and _is_small(s["total_mb"]):
        # An 8 GB card (2026-09-30): the numbers are arithmetic, and thin.
        inst += ("\n\nThis card has 8 GB, so the room is tight. The memory figure above is "
                 "calculated from the model's size, not measured on this card - the second "
                 "card's real use has not been measured yet. If answers get slow, the model "
                 "may not fully fit.")
    if installed is False:
        inst += (f"\n\n{model} is not installed yet. The switch will be on, but the "
                 f"feature waits until it is installed.")
    ok = det
    also = [x for x in _would_work(feature, sw, det)
            if x != feature and not _feature_active(x, sw, ok)]
    if also:
        one = len(also) == 1
        inst += (f"\n\nAlso: {_names(also)} {'is' if one else 'are'} still switched on from "
                 f"before, so {'it starts' if one else 'they start'} working again too, "
                 f"at once.")
    where = ("beside chat, on the same card" if det.get("_main")
             else "on the second graphics card")
    return (
        f"Turn on \"{f['name']}\" {where}?\n\n"
        f"What it does: {_what(f, det)}\n\n"
        f"Which card: {card}.\n"
        f"Which model: {model}, with room for {ctx:,} tokens - {mem}.\n\n"
        f"{lane}{inst}\n\n"
        "If you did not just ask for this, say no.\n\n"
        "If you say no: nothing changes. This keeps working the way it does today, on "
        f"the {p.get('name', 'main card')}.")


def _describe_model_free(f: dict, det: dict, card: str, primary: dict) -> str:
    """The approval card for a switch that loads no model today ("Referee
    suggestions"). It says so plainly: no second copy of Ollama starts, no
    model loads, and what the switch DOES allow - a card that only ever asks
    you to tick a step - is on it word for word."""
    return (
        f"Turn on \"{f['name']}\"?\n\n"
        f"What it does: {_what(f, det)}\n\n"
        f"Which card: {card} - it must be there to switch this on, because the later "
        f"version (reading a project's changes) will use its model.\n"
        f"Which model: none yet. Nothing is loaded and no second copy of Ollama is "
        f"started for this. Nothing leaves this PC.\n\n"
        "How it asks: at most a few cards a day, one at a time, never while you are in a "
        "focus session or Jarvis is in Quiet or Standby. Each card shows the numbers and "
        "says \"a suggestion from a number, not a check\". Your tap ticks the step, the same "
        "as ticking it yourself, and you can untick it at once. It never runs a test, and "
        "it only looks at your own goals.\n\n"
        "If you did not just ask for this, say no.\n\n"
        "If you say no: nothing changes. Goal steps are ticked only by you, as today.")


def describe_third_assign(feature: str, det: dict) -> str:
    """The approval card for moving `feature` onto the third card. Every
    word from here, same as describe_on - what refusing costs is on it
    (AP-4), and which physical card this is about, in words
    (docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3)."""
    f = _BY_ID[feature]
    third = det["_third"]
    tcard = f"the {third.name} ({_gb(third.total_mb)}, id {third.uuid})"
    scard = (det.get("second") or {}).get("name", "the second card")
    model, ctx, gib = _feature_model(feature, det, card=third)
    mem = f"about {gib:.1f} GB of the card's {_gb(third.total_mb)}" if gib else "an unknown amount"
    if _is_small(third.total_mb):
        mem += " (calculated from the model's size, not measured - the card is tight at 8 GB)"
    installed = _model_installed_on(model, _THIRD_LANE.url()) \
        if _THIRD_LANE.state == "running" else _model_installed_on(model, _main_ollama_url())
    inst = ""
    if installed is False:
        inst = (f"\n\n{model} is not installed yet. The move happens, but the feature "
                f"waits until it is installed.")
    return (
        f"Move \"{f['name']}\" to your third graphics card?\n\n"
        f"What it does: {_what(f, det)}\n\n"
        f"Which card: {tcard} - instead of {scard}, where it runs today.\n"
        f"Which model: {model}, with room for {ctx:,} tokens - {mem}.\n\n"
        f"Jarvis starts one more copy of Ollama, separate from your everyday one and from "
        f"the second card's, that uses only that card and listens on "
        f"{HOST}:{_third_port()} - this PC only, not your network or the internet. Nothing "
        f"leaves this PC. It runs AT THE SAME TIME as the second card's own copy: the two "
        f"cards work independently, one feature on each.{inst}\n\n"
        "If you did not just ask for this, say no.\n\n"
        f"If you say no: nothing changes. \"{f['name']}\" keeps working the way it does "
        f"today, on {scard}.")


def _decide_third(feature: str, pid: str, gate: Callable, tier_of: Callable) -> None:
    """_decide's shape, for moving `feature` onto the third card. Its own
    function, not a branch in _decide: there is no "needs" chain to
    re-check (the feature's own switch is checked instead), and the card
    names a different action (THIRD_ACTION) with its own wording."""
    det = detect()
    third = det.get("_third")
    if third is None:
        return _finish("third", pid, "refused", "there is no capable third graphics card")
    cur = _read_switches()
    if not cur["master"] or not cur["features"].get(feature):
        return _finish("third", pid, "refused",
                       f"\"{_BY_ID[feature]['name']}\" is not on")
    refused = _small_card_refusal(feature, third)
    if refused:
        return _finish("third", pid, "refused",
                       f"\"{_BY_ID[feature]['name']}\" cannot run on the {third.name}: {refused}")
    text = describe_third_assign(feature, det)
    model, ctx, gib = _feature_model(feature, det, card=third)
    detail = {"text": text, "what": f"move a second-card feature to the third graphics card: "
                                    f"{feature}",
              "feature": feature, "card": third.name, "card_id": third.uuid, "model": model,
              "memory_gib": gib, "listens_on": f"{HOST}:{_third_port()}", "leaves_this_pc": False}
    try:
        v = gate(THIRD_ACTION, detail, text)
    except Exception as exc:
        return _finish("third", pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish("third", pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes",
                       rid)
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish("third", pid, outcome, "", rid)
        return _finish("third", pid, "refused", str(getattr(v, "reason", "refused")), rid)
    with _PENDING_LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish("third", pid, "withdrawn",
                       "you changed it while the card was waiting", rid)
    cur2 = _read_switches()
    if not cur2["master"] or not cur2["features"].get(feature):
        return _finish("third", pid, "refused",
                       f"\"{_BY_ID[feature]['name']}\" was turned off while the card waited", rid)
    det2 = detect(fresh=True)
    third2 = det2.get("_third")
    if third2 is None:
        return _finish("third", pid, "refused", "the third card is not there any more", rid)
    if str(third2.uuid or "").lower() != str(third.uuid or "").lower():
        # The card in the third slot changed while the card waited: the owner
        # approved the OTHER one (2026-09-30), so nothing is saved.
        return _finish("third", pid, "refused",
                       "the graphics card in the third slot changed while the card waited, "
                       "so what you approved no longer matches - ask again", rid)
    err = _write_third(feature, third.uuid)
    if err:
        return _finish("third", pid, "failed", err, rid)
    _finish("third", pid, "enabled", "", rid)
    _reconcile_third(_read_switches(), detect())


def _request_change_third(assign: Optional[str], gate: Callable, tier_of: Callable,
                          spawn: Callable) -> tuple:
    """request_change's shape, for feature == "third": which of the five
    features (if any) runs on a third capable card, alongside the second
    card's own lane - never instead of it, and never both at once for the
    SAME feature (there is nowhere for it to run twice). UNASSIGNING
    (assign=None) is at once, no card, like every other OFF direction
    here. ASSIGNING is one approval card (THIRD_ACTION) that names the
    physical card - never a default (module docstring's "A THIRD CARD'S
    OWN LANE" section)."""
    if assign is None:
        # Withdraws any pending card FIRST, unconditionally - the same order
        # request_change's own OFF path uses, and for the same reason: a
        # card can be waiting while second-card.json still says None (the
        # state is only written once the card is actually approved), so
        # checking "already unassigned" before withdrawing would miss
        # exactly the case (AP-5) this exists to catch.
        with _PENDING_LOCK:
            if "third" in _PENDING:
                _PENDING["third"]["withdrawn"] = True
                _WITHDRAWN.add(_PENDING["third"]["id"])
        err = _write_third(None)
        if err:
            return 500, {"error": err}
        _audit("second_card.off", {"feature": "third"})
        _reconcile_third(_read_switches(), detect())
        return 200, {"ok": True, "assigned": None, "pending": False,
                     "message": "The third card is not running anything."}
    if assign not in _BY_ID:
        return 400, {"error": f"there is no second-card feature called {str(assign)[:40]!r}"}
    label = f"\"{_BY_ID[assign]['name']}\""
    if _model_free(assign):
        return 400, {"error": f"{label} loads no model, so there is nothing to move to the "
                              f"third card."}
    sw = _read_switches()
    det0 = detect()
    if _third_feature_now(sw, det0) == assign:
        return 200, {"ok": True, "assigned": assign, "pending": False,
                     "message": f"{label} is already on the third card."}
    if not sw["master"] or not sw["features"].get(assign):
        return 400, {"error": f"Turn {label} on first (the switch above), then move it to "
                              f"the third card."}
    with _PENDING_LOCK:
        p = _PENDING.get("third")
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": "a card to change the third card's feature is already "
                                  "waiting - approve or deny that one"}
    det = detect(fresh=True)
    third = det.get("_third")
    if third is None:
        return 503, {"error": "there is no capable third graphics card right now."}
    refused = _small_card_refusal(assign, third)
    if refused:
        return 503, {"error": f"{label} cannot run on the {third.name}: {refused}."}
    held = big_model_holds(third.uuid, third.name)
    if held:
        return 409, {"error": f"Not now: {held}."}
    try:
        tier = tier_of(THIRD_ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 503, {"error": (f"{THIRD_ACTION} is tier {tier!r} in jarvis-framework.toml; "
                               f"moving a feature to the third card needs a person to say "
                               f"yes, so it must be 'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        p = _PENDING.get("third")
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": "a card to change the third card's feature is already waiting"}
        _PENDING["third"] = {"id": pid, "since": time.time(), "withdrawn": False}
    _audit("second_card.asked", {"feature": "third", "assign": assign})

    def work() -> None:
        try:
            _decide_third(assign, pid, gate, tier_of)
        except Exception:
            _finish("third", pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish("third", pid, "failed", "could not start")
        return 503, {"error": "could not raise the approval card"}
    return 200, {"ok": True, "assigned": _third_feature_now(sw, det), "pending": True,
                 "message": ("Approve the card on your PC or phone to move it. "
                             "Nothing changes until you do.")}


#: pid -> (backoff fingerprint, conversation_id) for a "combined" card THIS
#: MODULE raised as a suggestion (maybe_suggest_combined), not one the owner
#: raised from Settings. Set right when the pid is made (before the card is
#: even up - see _request_change_combined's `on_pid`), read once by _finish
#: when that same pid ends, then gone either way. Never touches a card the
#: owner raised themselves: those never appear here.
_SUGGEST_FP: dict = {}


def _settle_suggestion(fp: str, conversation_id, outcome: str) -> None:
    """A suggested "combined" card has ended: tell jarvis_backoff (a real
    "no" is heard, 1/7/30 days, exactly like every other offer; a "yes"
    wipes the count), and reset this conversation's struggle/correction
    counts - "declines the offer once" and "combined mode is already on"
    both end here (item 5 of the brief). Best effort; never raises."""
    try:
        import jarvis_backoff
        bo = jarvis_backoff.get()
        if outcome == "enabled":
            bo.accepted(fp)
        elif outcome == "denied":
            bo.declined(fp)
        else:
            # timed_out / refused / failed / withdrawn: nobody said no, so
            # this is not counted as a decline - only that the offer is not
            # waiting for an answer any more (jarvis_backoff's own "waiting"
            # bookkeeping, same as every other offer's `closed`).
            bo.closed(fp)
    except Exception:
        pass
    if outcome in ("enabled", "denied"):
        try:
            import jarvis_agent
            jarvis_agent.reset_suggest_counts(conversation_id)
        except Exception:
            pass


def _finish(feature: str, pid: str, outcome: str, reason: str = "",
            request_id=None) -> None:
    with _PENDING_LOCK:
        if feature in _PENDING and _PENDING[feature]["id"] == pid:
            del _PENDING[feature]
        _WITHDRAWN.discard(pid)
        suggested = _SUGGEST_FP.pop(pid, None) if feature == "combined" else None
        _LAST[feature] = {"outcome": outcome, "reason": reason[:200]}
        label = ("The second graphics card" if feature == "master"
                 else f"\"{COMBINED_NAME}\"" if feature == "combined"
                 else "the third graphics card's assignment" if feature == "third"
                 else f"\"{_BY_ID[feature]['name']}\"" if feature in _BY_ID else feature)
        _LAST_ANY.clear()
        _LAST_ANY.update(feature=feature, outcome=outcome,
                         why=_last_words(label, outcome, reason[:200]), at=int(time.time()))
    _audit("second_card.decided", {"feature": feature, "outcome": outcome,
                                   **({"request_id": request_id} if request_id else {})})
    if suggested is not None:
        _settle_suggestion(suggested[0], suggested[1], outcome)


def _decide(feature: str, pid: str, gate: Callable, tier_of: Callable) -> None:
    """Raise the card, wait for the answer, act on it. Runs on its own thread."""
    det = detect()
    if not det.get("capable"):
        return _finish(feature, pid, "refused", det.get("why", ""))
    refused = _unsupported(feature, det) if feature != "master" else None
    if refused:
        return _finish(feature, pid, "refused", f"it cannot run on this card: {refused}")
    text = describe_on(feature, det)
    model, ctx, gib = (_feature_model(feature, det)
                       if feature != "master" and not _model_free(feature)
                       else (None, None, None))
    web = _brings_browser(feature, _read_switches(), det)
    detail = {"text": text, "what": f"turn on the second graphics card: {feature}",
              "feature": feature, "card": det["second"]["name"],
              "card_id": det["second"]["uuid"], "model": model, "memory_gib": gib,
              "listens_on": f"{HOST}:{_port()}", "leaves_this_pc": web}
    try:
        v = gate(action_for(feature), detail, text)
    except Exception as exc:
        return _finish(feature, pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish(feature, pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes",
                       rid)
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(feature, pid, outcome, "", rid)
        return _finish(feature, pid, "refused", str(getattr(v, "reason", "refused")), rid)
    with _PENDING_LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish(feature, pid, "withdrawn",
                       "you turned it off while the card was waiting", rid)
    if feature != "master":
        # Checked again now, not only when the card went up: the main switch
        # (or a feature this one needs) may have been turned off meanwhile -
        # and, bug audit 2026-09-27 finding #5, "combined" may have been
        # turned ON meanwhile (a separate card, approved in between): the
        # two cannot share both cards, and this was previously checked only
        # when THIS card was first raised, not again here - so approving
        # "combined" while a feature's own card was still waiting could
        # leave both switches on, and _wanted/_combined_wanted would then
        # each refuse the other, running neither.
        cur = _read_switches()
        if not cur["master"]:
            return _finish(feature, pid, "refused",
                           "the main second-card switch was turned off while the card "
                           "waited", rid)
        if cur.get("combined"):
            return _finish(feature, pid, "refused",
                           "\"One bigger model on both cards\" was turned on while this "
                           "card waited, and the two cannot share both cards", rid)
        gone = [d for d in _BY_ID[feature]["needs"] if not cur["features"].get(d)]
        if gone:
            return _finish(feature, pid, "refused",
                           f"it needs {_names(gone)}, which was turned off while the card "
                           f"waited", rid)
    if not detect(fresh=True).get("capable"):
        return _finish(feature, pid, "refused", "the second card is not there any more", rid)
    err = _write_switch(feature, True)
    if err:
        return _finish(feature, pid, "failed", err, rid)
    _finish(feature, pid, "enabled", "", rid)
    _reconcile(_read_switches(), detect())
    _referee_sync(feature)


def _referee_sync(feature: str) -> None:
    """Referee suggestions (and the main switch) went on or off: the quiet hourly
    look on the one scheduler follows the switch at once, not at the next
    restart. Best effort; never raises. A switch that changes nothing here (any
    other feature) does nothing."""
    if feature not in ("referee", "master"):
        return
    try:
        import jarvis_referee
        jarvis_referee.ensure_job()
    except Exception:
        pass


def _describe_combined(det: dict, why: str = "") -> str:
    """The approval card for "combined". Every word from here, same as
    describe_on - what refusing costs is on it (AP-4). `why`: when this card
    is a SUGGESTION (maybe_suggest_combined), one short plain sentence
    saying what Jarvis noticed - "" for the owner's own request from
    Settings, which needs no such line."""
    prim, second = _combined_rows(det)
    model, ctx, gib = COMBINED_MODEL
    lede = ("Jarvis noticed something and would like to suggest turning on \"One bigger model "
           f"on both cards\".\n\n{why}\n\n" if why else
           "Let Jarvis run one bigger model across BOTH graphics cards at once?\n\n")
    return (
        f"{lede}"
        f"Which cards: the {prim['name']} and the {second['name']}.\n"
        f"Which model: {model}, with room for {ctx:,} tokens - about {gib:.1f} GB, split "
        f"across both cards' memory by Ollama's own scheduler.\n\n"
        f"Jarvis starts a third copy of Ollama that can see both cards - it is not pinned to "
        f"one - and lets Ollama decide how many of the model's layers go on each card. It "
        f"listens on {HOST}:{_port()} - this PC only, not your network or the internet. "
        f"Nothing leaves this PC.\n\n"
        f"Ollama splits the model by how much FREE memory each card has right now, not by "
        f"how fast each card is - so most of the model can land on the bigger, slower card. "
        + (_combined_alone_note(det) + " " if _combined_alone_note(det) else "") +
        f"Every answer then runs at roughly that card's pace. Real speed is not measured yet: "
        f"the extra card is not installed yet.\n\n"
        f"This uses both cards for the one model, so it cannot run at the same time as the "
        f"second card's other features (Longer conversations, Pictures, Learning in the "
        f"background, Browser control, Wiki builder, Study helper) - turn those off first, or "
        f"this stays "
        f"off until you do.\n\n"
        + (f"If this is not something you want right now, say no - Jarvis will wait a while "
           f"before suggesting it again, and \"When to suggest the bigger model\" in Settings "
           f"can turn this kind of suggestion off.\n\n"
           f"If you say no: nothing changes; Jarvis keeps counting, and may ask again later."
           if why else
           f"If you did not just ask for this, say no.\n\n"
           f"If you say no: nothing changes. Everything keeps running the way it does today."))


def _decide_combined(pid: str, gate: Callable, tier_of: Callable, why: str = "") -> None:
    """_decide's shape, for "combined": raise the card, wait, act. Its own
    function rather than a branch in _decide - the checks and the message
    are different enough (two cards, no "needs" chain, always "nothing
    leaves this PC") that folding it in risked the well-tested generic
    path more than it saved. `why`: see _describe_combined."""
    det = detect()
    ok, cap_why = _combined_capable(det)
    if not ok:
        return _finish("combined", pid, "refused", cap_why)
    text = _describe_combined(det, why)
    prim, second = _combined_rows(det)
    model, ctx, gib = COMBINED_MODEL
    detail = {"text": text, "what": "run one bigger model across both graphics cards",
              "feature": "combined", "cards": [prim["name"], second["name"]],
              "card_ids": [prim["uuid"], second["uuid"]], "model": model, "memory_gib": gib,
              "listens_on": f"{HOST}:{_port()}", "leaves_this_pc": False,
              **({"why": why} if why else {})}
    try:
        v = gate(COMBINED_ACTION, detail, text)
    except Exception as exc:
        return _finish("combined", pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish("combined", pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes",
                       rid)
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish("combined", pid, outcome, "", rid)
        return _finish("combined", pid, "refused", str(getattr(v, "reason", "refused")), rid)
    with _PENDING_LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish("combined", pid, "withdrawn",
                       "you turned it off while the card was waiting", rid)
    cur = _read_switches()
    if _combined_conflict(cur):
        return _finish("combined", pid, "refused",
                       "a second-card feature was turned on while the card waited", rid)
    det2 = detect(fresh=True)
    ok2, why2 = _combined_capable(det2)
    if not ok2:
        return _finish("combined", pid, "refused", why2, rid)
    err = _write_switch("combined", True)
    if err:
        return _finish("combined", pid, "failed", err, rid)
    _finish("combined", pid, "enabled", "", rid)
    _reconcile_combined(_read_switches(), detect())


def _request_change_combined(enabled: bool, gate: Callable, tier_of: Callable,
                             spawn: Callable, *, why: str = "",
                             on_pid: Optional[Callable[[str], None]] = None) -> tuple:
    """request_change's shape, for feature == "combined". OFF: at once, no
    card. ON: refused (409) while any of the five features is genuinely on
    (they cannot share both cards with this mode); otherwise one approval
    card, action second_card_combined_enable.

    `why` and `on_pid` exist only for maybe_suggest_combined below - the
    owner's own request from Settings (request_change("combined", ...))
    never passes them, and every check above is exactly the same either
    way. `why`: see _describe_combined - one plain sentence added to the
    card saying what Jarvis noticed. `on_pid`: called with this card's pid
    once it is genuinely the one waiting (never for a pid this function
    returns 409/503/500 for without raising a card), so the caller can
    remember which offer this is BEFORE the answer comes back - _finish
    reads it back by the same pid."""
    label = f"\"{COMBINED_NAME}\""
    if not enabled:
        with _PENDING_LOCK:
            if "combined" in _PENDING:
                _PENDING["combined"]["withdrawn"] = True
                _WITHDRAWN.add(_PENDING["combined"]["id"])
        err = _write_switch("combined", False)
        if err:
            return 500, {"error": err}
        _audit("second_card.off", {"feature": "combined"})
        _reconcile_combined(_read_switches(), detect())
        return 200, {"ok": True, "enabled": False, "pending": False, "message": f"{label} is off."}

    sw = _read_switches()
    if sw.get("combined"):
        return 200, {"ok": True, "enabled": True, "pending": False,
                     "message": f"{label} is already on."}
    with _PENDING_LOCK:
        p = _PENDING.get("combined")
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": f"a card to turn on {label} is already waiting - "
                                  f"approve or deny that one"}
    if _combined_conflict(sw):
        return 409, {"error": (f"{label} needs both cards to itself: turn off the second-card "
                               f"features that are on now first (Brain, Hardware), then ask "
                               f"again.")}
    det = detect(fresh=True)
    ok, why = _combined_capable(det)
    if not ok:
        return 503, {"error": f"{label} cannot be turned on: {why}."}
    prim, second = _combined_rows(det)
    held = big_model_holds(prim["uuid"], prim["name"]) or big_model_holds(second["uuid"],
                                                                          second["name"])
    if held:
        return 409, {"error": f"Not now: {held}."}
    try:
        tier = tier_of(COMBINED_ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 503, {"error": (f"{COMBINED_ACTION} is tier {tier!r} in jarvis-framework.toml; "
                               f"turning this on needs a person to say yes, so it must be "
                               f"'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        p = _PENDING.get("combined")
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": f"a card to turn on {label} is already waiting"}
        _PENDING["combined"] = {"id": pid, "since": time.time(), "withdrawn": False}
    if on_pid is not None:
        try:
            on_pid(pid)
        except Exception:
            pass
    _audit("second_card.asked", {"feature": "combined", **({"suggested": True} if why else {})})

    def work() -> None:
        try:
            _decide_combined(pid, gate, tier_of, why)
        except Exception:
            _finish("combined", pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish("combined", pid, "failed", "could not start")
        return 503, {"error": "could not raise the approval card"}
    return 200, {"ok": True, "enabled": False, "pending": True,
                 "message": ("Approve the card on your PC or phone to turn it on. "
                             "Nothing changes until you do.")}


# --------------------------------------------------------------------------
#   Noticing on its own - the offer (see the module docstring's own section)
# --------------------------------------------------------------------------

def _agent_counts(conversation_id) -> tuple:
    """jarvis_agent.suggest_counts(conversation_id), or (0, 0) without that
    module (or an older one without the function)."""
    try:
        import jarvis_agent
        return jarvis_agent.suggest_counts(conversation_id)
    except Exception:
        return 0, 0


def _reset_agent_counts(conversation_id) -> None:
    try:
        import jarvis_agent
        jarvis_agent.reset_suggest_counts(conversation_id)
    except Exception:
        pass


def _suggestion_reason(struggle: int, correction: int) -> Optional[str]:
    """One or two plain sentences for the card, saying exactly why Jarvis is
    asking now - or None when neither signal has crossed its threshold (or
    its own setting is off). Never invents a reason: only what was actually
    counted, and only for a signal whose own switch is on."""
    bits = []
    if suggest_setting("struggle") and struggle >= STRUGGLE_THRESHOLD:
        bits.append(f"Jarvis had to ask the model to try a tool call again {struggle} times "
                    f"in this conversation.")
    if suggest_setting("correction") and correction >= CORRECTION_THRESHOLD:
        bits.append(f"You have corrected Jarvis's answers {correction} times in this "
                    f"conversation.")
    if not bits:
        return None
    return " ".join(bits) + " A bigger model may do better with this."


def maybe_suggest_combined(conversation_id, *, gate: Optional[Callable] = None,
                           tier_of: Optional[Callable[[str], str]] = None,
                           spawn: Optional[Callable] = None,
                           sleep: Optional[Callable[[float], None]] = None) -> None:
    """Called once, at the end of a chat turn (jarvis_agent.run_local_turn) -
    never mid-answer. Offers "One bigger model on both cards" through the
    SAME approval card the Hardware screen's own switch already raises
    (second_card_combined_enable) when: the owner has been visibly
    struggling, or has corrected Jarvis more than once, in THIS conversation
    (jarvis_agent's own per-conversation counts); the matching setting is
    on; a genuinely capable second card is here RIGHT NOW
    (_combined_capable - the same hard gate "combined" itself needs, never
    a separate or looser one); and jarvis_backoff says this offer may be
    made right now. Never switches anything on by itself: the same
    person's-yes card as always decides that.

    jarvis_backoff's own "never mid-chat" rule (note_conversation, stamped
    at the START of this SAME turn by /api/chat) would otherwise refuse
    every single check this function ever makes, since it always runs at
    the END of a turn that just stamped "chatting now" - bug audit
    2026-09-27, finding #1. When that is the ONLY reason held back, one
    background wait (see _retry_when_quiet) tries this exact same check
    again once the conversation goes quiet, rather than only ever trying
    once and never again.

    `gate`/`tier_of`/`spawn`/`sleep`: request_change()'s own injection
    points, plus the wait itself - for the tests; the real caller never
    passes them. Never raises."""
    try:
        _maybe_suggest_combined(conversation_id, gate, tier_of, spawn, sleep)
    except Exception:
        pass


#: Retry threads already waiting for "the owner is still chatting, try again
#: once quiet" - one per conversation, so a busy back-and-forth turn after
#: turn does not spawn a pile of sleeping threads that would all wake at
#: once. See _retry_when_quiet.
_RETRY_SCHEDULED: set = set()
_RETRY_LOCK = threading.Lock()


def _retry_when_quiet(conversation_id, gate, tier_of, spawn, sleep, bo) -> None:
    """Bug audit 2026-09-27, finding #1: `/api/chat` stamps "the owner is
    chatting now" (jarvis_backoff.note_conversation) at the START of the
    same turn `_maybe_suggest_combined` checks at the END of, so
    `may_offer`'s conversation gate always said "not now" and nothing ever
    checked again - the offer could never actually fire outside a turn
    that happened to take over two minutes to answer. This is that "check
    again": one background wait for exactly as long as `quiet_for()` still
    says, then one more real attempt through `_maybe_suggest_combined`
    itself, so every other gate (the thresholds, `combined`'s own
    capability check, backoff, a card already pending) is re-checked
    fresh rather than trusted from before the wait - if the owner is still
    talking when the wait ends, that call schedules the next wait itself,
    the same way; if any other gate says no, it stops here, same as an
    ordinary turn that never had anything to offer."""
    with _RETRY_LOCK:
        if conversation_id in _RETRY_SCHEDULED:
            return
        _RETRY_SCHEDULED.add(conversation_id)

    def run() -> None:
        try:
            wait = bo.quiet_for()
            if wait > 0:
                sleep(wait)
        finally:
            with _RETRY_LOCK:
                _RETRY_SCHEDULED.discard(conversation_id)
        _maybe_suggest_combined(conversation_id, gate, tier_of, spawn, sleep)

    spawn(run)


def _maybe_suggest_combined(conversation_id, gate=None, tier_of=None, spawn=None,
                            sleep=None) -> None:
    if not isinstance(conversation_id, str) or not conversation_id:
        return
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    sleep = sleep or _sleep
    # Cheapest checks first: most conversations never cross either
    # threshold, and this runs at the end of EVERY turn, so nothing below
    # this line (a config-file read, detect()'s nvidia-smi call) happens
    # unless there is genuinely something to consider offering.
    struggle, correction = _agent_counts(conversation_id)
    reason = _suggestion_reason(struggle, correction)
    if reason is None:
        return
    sw = _read_switches()
    if sw.get("combined"):
        # Already on: item 5 of the brief - nothing left to suggest, and
        # this conversation's counts stop mattering.
        _reset_agent_counts(conversation_id)
        return
    if _combined_conflict(sw):
        return
    with _PENDING_LOCK:
        p = _PENDING.get("combined")
        if p is not None and not p.get("withdrawn"):
            return   # a card - suggested or the owner's own - is already up
    det = detect()
    ok, _why = _combined_capable(det)
    if not ok:
        return
    try:
        import jarvis_backoff
    except Exception:
        return
    fp = jarvis_backoff.fingerprint(SUGGEST_OFFER_KIND)
    bo = jarvis_backoff.get()
    try:
        may, why2 = bo.may_offer(fp, kind=SUGGEST_OFFER_KIND)
    except Exception:
        return
    if not may:
        if why2 == "conversation":
            _retry_when_quiet(conversation_id, gate, tier_of, spawn, sleep, bo)
        return
    try:
        bo.opened(fp)
    except Exception:
        return

    def remember(pid: str) -> None:
        with _PENDING_LOCK:
            _SUGGEST_FP[pid] = (fp, conversation_id)

    code, body = _request_change_combined(True, gate, tier_of, spawn,
                                          why=reason, on_pid=remember)
    if code != 200 or not (isinstance(body, dict) and body.get("pending")):
        # Refused before a card was even raised (not capable any more since
        # the fresh detect() inside _request_change_combined, the big model
        # holds a card, the tier is not "ask", ...): not a "no" from the
        # owner, so this is not counted as a decline.
        try:
            bo.closed(fp)
        except Exception:
            pass


def request_change(feature: str, enabled: bool = False, *, assign: Optional[str] = None,
                   gate: Optional[Callable] = None,
                   tier_of: Optional[Callable[[str], str]] = None,
                   spawn: Optional[Callable] = None) -> tuple:
    """POST /api/second-card. Returns (http code, body). `feature` may be
    "master", "combined" (the third mode, mutually exclusive with the rest
    - see _request_change_combined), "third" (which of FEATURE_IDS, if
    any, runs on a third capable card alongside the second's own lane -
    see _request_change_third; `assign` is read instead of `enabled`) or
    one of FEATURE_IDS.

    OFF: at once, no card. ON: one approval card, and this returns straight
    away - `pending: true` means a card is up, NOT that it is on."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if feature == "third":
        if assign is not None and not isinstance(assign, str):
            return 400, {"error": "\"assign\" must be a feature id or null"}
        return _request_change_third(assign, gate, tier_of, spawn)
    if feature == "combined":
        if not isinstance(enabled, bool):
            return 400, {"error": "\"enabled\" must be true or false"}
        return _request_change_combined(enabled, gate, tier_of, spawn)
    if feature != "master" and feature not in _BY_ID:
        return 400, {"error": f"there is no second-card feature called {str(feature)[:40]!r}"}
    if not isinstance(enabled, bool):
        return 400, {"error": "\"enabled\" must be true or false"}
    label = "The second graphics card" if feature == "master" else f"\"{_BY_ID[feature]['name']}\""
    if enabled and _read_switches().get("combined"):
        return 409, {"error": (f"{label} cannot be turned on: \"{COMBINED_NAME}\" is on, and "
                               f"needs both cards to itself. Turn that off first.")}

    if not enabled:
        with _PENDING_LOCK:
            if feature in _PENDING:
                _PENDING[feature]["withdrawn"] = True
                _WITHDRAWN.add(_PENDING[feature]["id"])
        err = _write_switch(feature, False)
        if err:
            return 500, {"error": err}
        _audit("second_card.off", {"feature": feature})
        _reconcile(_read_switches(), detect())
        _referee_sync(feature)
        return 200, {"ok": True, "enabled": False, "pending": False,
                     "message": f"{label} is off."}

    sw = _read_switches()
    already = sw["master"] if feature == "master" else sw["features"].get(feature)
    if already:
        return 200, {"ok": True, "enabled": True, "pending": False,
                     "message": f"{label} is already on."}
    with _PENDING_LOCK:
        p = _PENDING.get(feature)
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": (f"a card to turn on {label} is already waiting - "
                                   f"approve or deny that one")}
    det = detect(fresh=True)
    if not det.get("capable"):
        return 503, {"error": f"{label} cannot be turned on: {det.get('why')}."}
    refused = _unsupported(feature, det)
    if refused:
        return 503, {"error": f"{label} cannot be turned on: {refused}."}
    if feature != "master":
        if not sw["master"]:
            return 400, {"error": "Turn on the second graphics card itself first "
                                  "(the main switch), then this one."}
        missing = [d for d in _BY_ID[feature]["needs"] if not sw["features"].get(d)]
        if missing:
            names = ", ".join(f"\"{_BY_ID[d]['name']}\"" for d in missing)
            return 400, {"error": f"{label} needs {names} on first."}
    if ((feature != "master" and not _model_free(feature))
            or (feature == "master" and any(v for k, v in sw["features"].items()
                                            if not _model_free(k)))) and not det.get("_main"):
        # This ON would start the second Ollama. Not while the big model is
        # on the card: the approval would turn on something that cannot run.
        held = big_model_holds(det["second"]["uuid"], det["second"]["name"])
        if held:
            return 409, {"error": f"Not now: {held}."}
    action = action_for(feature)
    try:
        tier = tier_of(action)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Checked BEFORE a card is raised: a card that could not end in a
        # person deciding should not be raised at all.
        return 503, {"error": (f"{action} is tier {tier!r} in jarvis-framework.toml; "
                               f"turning this on needs a person to say yes, so it must "
                               f"be 'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        p = _PENDING.get(feature)
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": f"a card to turn on {label} is already waiting"}
        _PENDING[feature] = {"id": pid, "since": time.time(), "withdrawn": False}
    _audit("second_card.asked", {"feature": feature})

    def work() -> None:
        try:
            _decide(feature, pid, gate, tier_of)
        except Exception:
            _finish(feature, pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish(feature, pid, "failed", "could not start")
        return 503, {"error": "could not raise the approval card"}
    return 200, {"ok": True, "enabled": False, "pending": True,
                 "message": ("Approve the card on your PC or phone to turn it on. "
                             "Nothing changes until you do.")}


def handle_post(body) -> tuple:
    """The route's body: {"feature": "...", "enabled": true|false} - or,
    for the third card, {"feature": "third", "assign": "<feature id>" or
    null}."""
    if not isinstance(body, dict):
        return 400, {"error": "send {\"feature\": \"...\", \"enabled\": true or false}"}
    feature = str(body.get("feature") or "")
    if feature == "third":
        return request_change(feature, assign=body.get("assign"))
    return request_change(feature, body.get("enabled"))


def _reset_for_tests() -> None:
    global _LANE, _COMBINED_LANE, _THIRD_LANE
    with _PENDING_LOCK:
        _PENDING.clear()
        _LAST.clear()
        _WITHDRAWN.clear()
        _LAST_ANY.clear()
        _SUGGEST_FP.clear()
    _TAGS.clear()
    _LEARN.update(failed_at=-1e9, short=False)
    _STUDY.model = ""
    wake()
    try:
        _LANE.stop("reset")
    except Exception:
        pass
    _LANE = _LaneProcess("second")
    try:
        _COMBINED_LANE.stop("reset")
    except Exception:
        pass
    _COMBINED_LANE = _LaneProcess("combined")
    try:
        _THIRD_LANE.stop("reset")
    except Exception:
        pass
    _THIRD_LANE = _LaneProcess("third")


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
