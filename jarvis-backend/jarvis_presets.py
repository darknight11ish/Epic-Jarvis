"""jarvis_presets.py - the focus presets the chat bar and Settings show.

Pure data plus pure helpers; reads nothing except, since 2026-10-27, WHICH
cloud key is saved on this PC (Credential Manager presence only - never a key,
never a fragment) and this month's spend against the owner's own limit, which
is what the Cloud row in the Presets menu shows. It still switches nothing by
itself: a MODEL/chat apply raises the one `switch_model` ask card inside
`jarvis_models.switch_to`, and the cloud provider's apply raises the one
`change_own_config` card and changes NO model and starts NO lane.

ONE exception, 2026-11-09: a local preset clicked in either app's own preset
control applies at once with no card, because it is the owner's own reversible
click. That road is the `POST /api/work/apply` route alone; the model/chat
path keeps its card. The boundary and its reasoning sit above
`apply_preset`.

The ten local presets: the original five (General, General Uncensored, Coding,
Agentic+Vision, Fast), four capability rows added 2026-10-27 at the owner's
request - Reflective Coach, Pictures & Screens, Long Documents, Browser & Forms -
and Medical Expert, appended tenth on 2026-11-09 (medgemma:27b, one of the
pooled rows). They replace the five "work setups" in jarvis_work.py (decision
2026-10-18).

Each `measured` dict keeps the receipt it was taken from. The decode rate
`tok_s` is the live measurement run of 2026-11-17
(`.dsh-scratch/wave21/preset-truth/REPORT.md`, raw rows in rows.jsonl beside
it), with its own `tok_s_on` date and `tok_s_note`; every other key under
`measured` keeps its dated receipt (.dsh-scratch/android-verify/
MODEL-BENCH-2026-10-10.md and STRATEGY beside it). The everyday 26B's figures
are that run measured ON THE POOLED LANE it now names - the same lane, window
and cards - and `measured is None` means NOT measured for that model, never a
guess. Pictures & Screens is the ONE row re-measured after that run: its
2026-11-18 receipt (the row's own `source`) was taken on the real pooled lane,
and it is why that row no longer runs the 30B vision model.

Lanes (this PC, 2026-11-18):
  main    ONE card (the RTX 2060), port 11436 - the everyday lane and the only
          always-on lane. It serves the 9B long-window rows (Documents & Notes
          and Browser & Forms at 196,608 tokens) and the short-window ones
          (Agentic + Vision and Fast at 16,384). A heavy preset pauses it.
  pooled  ALL THREE cards, port 11450 - the heavy presets' own lane, started on
          demand (2026-11-02). Since 2026-11-18 it carries General's 26B, and
          it also carries Coding, Reflective Coach, Pictures & Screens and
          Medical. It loads ONE model at a time and pauses the everyday lane
          first; bringing the everyday 9B back afterwards costs a reload.

General IS A HEAVY ROW (2026-11-18, and this is the decision worth reading).
The owner chose `gemma4:26b-a4b-it-qat` at a 32,768-token window on quality, and
that model needs all three cards. The everyday lane on 11436 is pinned by its
Windows logon task to the single 12 GB RTX 2060, so putting the 26B there would
guarantee a spill into system RAM (measured live on 2026-11-18: 15.8 GB resident
with only 9.1 GB on the card). The pooled lane on 11450 already sees all three
cards, so General names IT - the owner gets the model he chose with no change to
his PC. General is therefore `heavy_mode=True, mode="gemma4-26b-a4b"`, the same
measured pooled mode Reflective Coach uses; that mode's own window is 32,768 and
its own measured spill allowance is 0.68 GiB, which the apply's lane read-back
now uses. Measured on this PC on 2026-11-17 ON THAT LANE at 32,768 tokens:
15.50 GiB loaded with 0.68 GiB (4.4%) spilled into system memory, 25.4 tokens a
second (the LOW end of two runs that read 25.4-36.5) and a 49.9 s cold load. The
196,608-token version of the same model was measured at 2.385 GiB spilled and
21.2 tokens a second, which is why that window is not offered.

The everyday lane is NOT retired, because it is still what serves the two
presets that need the long window: Documents & Notes and Browser & Forms keep
`qwen3.5:9b` at 196,608 tokens on the 2060. The 11435 coding lane is RETIRED
(2026-11-18) - the owner's words are "i dont need a separate coding lane on any
preset. each preset should be dedicated to one preset local ai model." Every
preset below names exactly one model and exactly one lane, the Fast row moved
from the retired coding lane to the everyday lane, and ONE preset's model is
loaded at a time: a preset switch ends the previous one first, and because no
other preset needs the cards reserved, any preset may use all three.

The 32,768-token window and the model are the owner's 2026-11-18 choice, taken
on quality rather than speed: a blind battery of eight tasks scored this model
22/24, the 12B 21/24, the 35B 21/24 and the old everyday 9B last at 19/24 with
the only app-breaking failure in the run
(`.dsh-scratch/wave21/quality-battery/REPORT.md`).

Coding is the FIRST of the heavy rows that predate General, and since 2026-11-02
it has a lane that can really hold it: a 14.8 GB model fits neither card alone,
so its lane is ONE Ollama on its own port with all three cards visible
(`jarvis_model_lanes.start_pooled_lane`), started by the apply and stopped by
the next apply that is not heavy. The cost is stated in each preset's own words
and on the card: the everyday model is paused while it runs and comes back when
it is stopped. 2026-11-18 also added Reflective Coach and Pictures & Screens to
that road, each naming its own measured pooled mode.

PICTURES & SCREENS MOVED AGAIN THE SAME DAY, and the measurement is the reason.
The 30B vision model it first named does not fit: measured on the real pooled
lane on 2026-11-18 (the three named lanes paused, one model resident), it loaded
19.88 GiB with **2.24 GiB in system memory**, and at 16,384 tokens it still
spilled 1.65 GiB while the cards had 8.6 GiB free - the model's own split, not
the window, so no context size fixes it. The row therefore runs
`gemma4:12b-it-qat` at the same 32,768-token window on the same pooled lane:
8.70 GiB resident, **all of it in the cards' memory (0 B spilled)**, a 20.3 s
cold load and 28.1 tokens a second. That model answered the picture test the
same way the 30B did (it read a generated screenshot's Save button, server
address and red banner), and its general quality is the project's own blind
eight-task battery's 21/24. The proof, the raw rows and the test pictures are in
`.dsh-scratch/preset-pictures-2026-11-18/`; the decision is recorded in
`decisions.d/2026-11-18-pictures-preset-zero-spill.md`.

GENERAL UNCENSORED IS THE ONE PLACE UNCENSORED MODELS LIVE (the external review's
ruling, 2026-11-18): General keeps the aligned `gemma4:26b-a4b-it-qat`, and the
uncensored model stays on this separate preset. The row shipped on 2026-11-18
with the measured uncensored 27B, `orcarouter/Qwen3.8-27B-Uncensored:q4_K_M`;
the 2026-11-19 review ruled that if the downloaded MoE beat that 27B on quality,
speed and tool calling it swaps, and the measurement that day says it does: the
row now names `huihui_ai/qwen3-abliterated:30b-a3b-instruct-2507-q4_K_M` (30.5B
parameters, a mixture of experts with 8 of 128 active per token) on the same
pooled three-card lane at the 32,768-token window, where it loaded **19.520 GiB
with 0.000 GiB spilled**. It tied the 27B's blind quality at **20/24**, emitted
**22/22 correct tool calls** against the 27B's 18/19, and decodes **about 21
tokens a second** - the median of three separate loads on a PC with no test load,
published **with its spread** because the three runs disagreed (19.71, 21.04 and
62.55 tok/s; the cards' clock state, not competing load), which is ruling 5.4's
shape - against the 27B's 9.04-13.05. The trade is
running cost: 2.1 GiB more resident memory, a 55.1-66.3 s cold load against
47.4-57.1 s, only a 32,768-token proven zero-spill window (49,152 measured
0.226 GiB spilled, so the 27B's 49,152-token headroom is gone) and no vision.
The 27B itself is NOT deleted: it stays on this PC as the pooled lane's
`creative` mode model and the smaller-footprint alternative, but no preset
names it now. `muse-glimmer-uncensored:30b` (15.77 GiB, already on this PC,
tools + thinking) is still described rather than chosen, because it has NOT
been benchmarked on this PC. The evidence is
`.dsh-scratch/wave21/research/MEASURE-MOE.md` and the decision is recorded in
`decisions.d/2026-11-19-general-uncensored-is-the-moe.md`.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

#: Evidence every measured figure is quoted from.
EVIDENCE = (".dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md",
            ".dsh-scratch/android-verify/MODEL-STRATEGY-2026-10-10.md")

LANES = {
    # The only always-on lane, and it is ONE card: the RTX 2060 at port 11436
    # runs the 9B long-window rows (Documents & Browser at 196,608 tokens) and
    # the short-window rows (Agentic + Vision and Fast at 16,384). General's 26B
    # needs all three cards, so it is NOT here - it names the pooled lane below,
    # which is why a heavy preset pauses this one while it runs. THE CARD WORD
    # IS THE ONE CARD THE TRACKED LOGON TASK PINS: `scripts/start-lane.ps1` with
    # Windows Task Scheduler passes ONE -GpuUuid for 11436, so claiming more
    # cards here would be a table the PC can never honour
    # (`tools/check_lane_launcher.py`, required).
    "main": {"key": "main", "card": "RTX 2060", "port": 11436,
             "words": "the everyday lane"},
    # The heavy presets' own lane: ONE Ollama that sees ALL THREE cards, started
    # on demand by the apply (never by a logon task, which would hold the cards
    # against the everyday lane). `card` says "all three cards" because there is
    # no single card it lives on; its port and words are
    # `jarvis_model_lanes`' own, pinned to agree by test.
    "pooled": {"key": "pooled", "card": "all three cards", "port": 11450,
               "words": "one model across all three cards"},
}

#: What the one action is called. It is a preset application, never a route
#: that runs by itself: a model/chat apply raises the existing switch_model card
#: (tier "ask"), and a lane start is only ever part of that same action. Since
#: 2026-11-09 a LOCAL preset clicked in either app's own control applies at once
#: with no card (it is the owner's own reversible click); see `apply_preset`.
APPLY_ACTION = "Use this preset"
SWITCH_ROUTE = "/api/models/switch"
LANE_START_ROUTE = "/api/model-lanes/start"


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    focus: str              # a few words under the title
    what: str               # one sentence, what it is for
    cost: str               # honest cost
    worse: str              # honest weakness
    model: str
    lane: str               # a key of LANES
    context: int
    helper_model: Optional[str] = None
    helper_lane: Optional[str] = None
    helper_context: int = 0
    prompt: str = "balanced"
    diet: str = "balanced"  # the top-K tool diet's grouping word
    tools: tuple = ()       # extra tool groups that matter for this preset
    measured: Optional[dict] = None
    pending: bool = False
    heavy_mode: bool = False
    #: The plain-words COST of a heavy preset (all three cards, the other models
    #: paused), which both apps show BESIDE an apply that is now allowed. It is
    #: not a refusal: the refusal was "lane support is arriving", and the lane
    #: is here (`jarvis_model_lanes.start_pooled_lane`).
    heavy_words: str = ""
    #: The pooled mode this preset starts (`jarvis_model_lanes.
    #: start_pooled_lane(mode=...)`), "" for a preset on a named lane. Four rows
    #: name one: Coding keeps the lane's own default, Medical names `medical`,
    #: Reflective Coach names `gemma4-26b-a4b`, and Pictures & Screens names
    #: `gemma4-12b` (the 30B vision mode it named first was measured spilling
    #: 2.24 GiB on this PC and was replaced the same day - see the module
    #: docstring).
    mode: str = ""
    words: tuple = ()       # trigger words for /api/work/recommend
    strong: tuple = ()

    @property
    def lane_info(self) -> dict:
        return dict(LANES[self.lane])

    def view(self) -> dict:
        """The one JSON both apps render; also the fixture's shape."""
        return {
            "id": self.id, "title": self.title, "focus": self.focus,
            "what": self.what, "cost": self.cost, "worse": self.worse,
            "model": self.model,
            "lane": dict(self.lane_info),
            "context": self.context,
            "helper": ({"model": self.helper_model,
                        "lane": dict(LANES[self.helper_lane]),
                        "context": self.helper_context}
                       if self.helper_model else None),
            "policy": {"prompt": self.prompt, "diet": self.diet,
                       "tools": list(self.tools)},
            "measured": self.measured,
            "pending": self.pending,
            "heavy_mode": self.heavy_mode,
            "heavy_words": self.heavy_words,
            "apply": {"action": APPLY_ACTION, "switch_route": SWITCH_ROUTE,
                      "apply_route": "/api/work/apply",
                      "lane_start": self.lane != "main",
                      "auto": False},
        }


#: The Medical mode's measured sentence, quoted from the one bench receipt. It is
#: used by the card text and by `pooled_modes()`; no second copy exists.
MEDICAL_MEASURED_WORDS = (
    "measured on this PC: 17.31 GiB loaded entirely in the three cards' memory "
    "with 0 B spilled and a 46.8 s cold load (2026-11-09); the 2026-11-17 "
    "re-measurement read 11.4-11.7 tokens a second, and the LOW end (11.4) is "
    "the figure the row shows")

#: The measured pooled-mode sentences. Each is the ONE copy `pooled_modes()`
#: republishes, so the applied card, the lane row and the preset row cannot
#: drift. Reflective Coach AND General apply `gemma4-26b-a4b` (General is a
#: heavy row on the pooled lane - see the module docstring); the 26B sentence is
#: the 2026-11-17 live re-measurement of that load (same model, 32,768 tokens,
#: all three cards), because that run's 25.4 low end is what the preset rows
#: quote; the 2026-11-09 receipt's 49.26 was a different run of the same row and
#: is kept in `docs/MODEL-TOPOLOGY.md`. Pictures & Screens applies the 12B row,
#: measured fresh on 2026-11-18 after the 30B vision model it first named spilled
#: 2.24 GiB - the old sentence is NOT kept as an allowance anywhere, because the
#: row it described is gone. General Uncensored applies the third row, the
#: uncensored 30B MoE, measured on the real lane on 2026-11-19 (it was the
#: measured 27B from 2026-11-18 until the 2026-11-19 ruling swapped it).
#: `jarvis_big_coder.MODES`' `creative` row keeps the 27B and its own 2026-11-18
#: sentence: only this preset's row moved, because it is the only row the
#: candidate was measured against.
GEMMA4_26B_MEASURED_WORDS = (
    "measured on this PC on 2026-11-17 at 32,768 tokens across all three "
    "cards: 15.50 GiB loaded with 0.68 GiB (4.4%) spilled into system memory, "
    "25.4-36.5 tokens a second (the LOW end is the figure the row shows) and a "
    "49.9 s cold load")
GEMMA4_12B_MEASURED_WORDS = (
    "measured on this PC on 2026-11-18 at 32,768 tokens across all three "
    "cards on the real pooled lane: 8.70 GiB loaded entirely in the cards' "
    "memory with 0 B spilled, a 20.3 s cold load and 28.1 tokens a second")
UNCENSORED_MOE_MEASURED_WORDS = (
    "measured on this PC on 2026-11-19 at 32,768 tokens across all three "
    "cards on the real pooled lane: 19.520 GiB loaded entirely in the cards' "
    "memory with 0.000 GiB spilled, a 55.1-66.3 s cold load and about 21 "
    "tokens a second (three separate loads on a PC with no test load; the three "
    "read 19.71, 21.04 and 62.55 tok/s - spread 203.6% - so the median 21.04 "
    "is published WITH that spread, never as a stable figure)")

PRESETS = (
    Preset(
        id="general", title="General", focus="everyday questions, writing, life admin",
        what="The everyday preset: questions, writing, checking things, your own "
             "paperwork - one balanced setup instead of a separate admin preset. "
             "Since 2026-11-18 it is the 26B model at a 32,768-token window on the "
             "pooled three-card lane: the owner chose it on quality, after a blind "
             "battery of eight tasks scored it 22/24, the best of the four tried.",
        cost="HEAVY MODE: it needs all three cards at once as ONE pooled lane (port "
             "11450) and pauses the everyday 9B model while it loads. Measured on "
             "this PC on 2026-11-17 on that lane at 32,768 tokens: 15.50 GiB "
             "resident, 14.82 GiB in the cards' memory and 0.68 GiB spilled into "
             "system memory, 25.4 tokens a second (two runs read 25.4-36.5, the low "
             "end is shown) and a 49.9 s cold load.",
        worse="It fills all three cards, so a preset that is not heavy stops its lane "
              "and brings the everyday 9B back; returning to General costs its cold "
              "load (about 50 seconds). The everyday lane is paused while it runs, so "
              "a chat arriving then waits for the switch. `ollama show` reports "
              "completion, vision, tools and thinking and a real 573M-parameter image "
              "projector, so pictures and tools are not lost - but its picture quality "
              "and its general, tool-calling and vision rubric results are NOT "
              "measured on this PC, so nothing here claims them. It thinks before it "
              "answers, so a short answer allowance can cut it off before it speaks.",
        model="gemma4:26b-a4b-it-qat", lane="pooled", context=32768,
        heavy_mode=True, mode="gemma4-26b-a4b",
        heavy_words="This preset needs all three cards at once as one pooled lane on "
                    "port 11450. While it runs, the everyday 9B is paused - it comes "
                    "back, proved from the model list, when you apply a preset that "
                    "is not heavy. Loading it takes about 50 seconds.",
        prompt="balanced", diet="balanced",
        measured={"tok_s": 25.4, "tok_s_on": "2026-11-17",
                  "tok_s_note": "15.50 GiB, 0.68 GiB spill, all three cards, "
                                "32,768 context; two runs read 25.4-36.5, the low "
                                "end is shown",
                  "size_gib": 15.501, "vram_gib": 14.820, "spill_gib": 0.681,
                  "cold_load_s": 49.9, "context_measured": 32768,
                  "capabilities": ["completion", "vision", "tools", "thinking"],
                  "vision_projector_params": 573000000,
                  "source": "the 2026-11-17 live run (preset-truth REPORT.md, the "
                            "reflect_pooled rows) measured the same model, window and "
                            "cards this preset asks for: 15.501 GiB resident, 14.820 "
                            "GiB in the cards' memory, 0.681 GiB (4.4%) spilled, "
                            "25.4-36.5 tok/s (the low end is shown) and a 49.9 s cold "
                            "load, on the pooled three-card lane. /api/show reports "
                            "completion, vision, tools and thinking and a real "
                            "573M-parameter image projector (projector_type gemma4v, "
                            "clip.has_vision_encoder true)"},
        words=("everyday", "general", "quick question", "writing", "admin",
               "paperwork", "letter", "statement", "form", "tax", "email", "inbox"),
        strong=("everyday use", "quick questions", "life admin", "my admin"),
    ),
    Preset(
        id="general_uncensored", title="General Uncensored",
        focus="general work with the uncensored model",
        what="General everyday work with the uncensored model, for answers the "
             "ordinary model's safety tuning would refuse or water down. General "
             "stays the aligned 26B; THIS is the separate preset uncensored "
             "models live on, and it names the measured uncensored 30B mixture of "
             "experts (30.5B parameters, 8 of its 128 experts active per token) "
             "rather than a guess.",
        cost="HEAVY MODE: it needs all three cards at once as one pooled lane (port "
             "11450) and pauses the everyday model while it loads. Measured on this "
             "PC on 2026-11-19 on that lane at 32,768 tokens: 19.520 GiB loaded "
             "ENTIRELY in the cards' memory (0.000 GiB spilled), a 55.1-66.3 s cold "
             "load and about 21 tokens a second - the median of three separate "
             "loads on a PC with no test load. The three disagreed (19.71-62.55 "
             "tok/s, spread 203.6%) because of the cards' clock state, not "
             "competing load, so the row publishes the median and that spread; "
             "the PC was running its own assistant and browser (12-17% CPU on the perf counter; no test load), so ~21 is a floor, not a best case. 49,152 tokens measured "
             "0.226 GiB spilled, so 32,768 is the largest proven zero-spill window "
             "and the window this row runs.",
        worse="The speed and the tool actions are measured gains; quality is a TIE, "
              "not a gain. Speed is ONE rounded figure - the median of three "
              "separate loads on a PC with no test load on 2026-11-19 - and the "
              "three runs disagreed widely (19.71, 21.04 and 62.55 tok/s; spread "
              "203.6% of the median), which is the cards' clock state, not "
              "competing load. The PC was running its own assistant and browser "
              "during the measurement (12-17% CPU on the perf counter; no test load), so ~21 is a "
              "floor, not a best case; the row publishes the median plus the "
              "spread, never a stability claim. The earlier ten-sample set on a "
              "busy PC read 16.19-20.22 tok/s. The aligned 26B on General still "
              "scores 22/24 on the "
              "project's blind eight-task battery at 52.3 tokens a second, so a "
              "bigger, uncensored model is NOT automatically better: this row "
              "scores 20/24, exactly the 27B it replaced. The trade for the speed "
              "is running cost: it loads 2.1 GiB heavier than that 27B (19.520 GiB "
              "against 17.379), takes about 10 seconds longer cold (55.1-66.3 s "
              "against 47.4-57.1 s), and its largest proven zero-spill window is "
              "32,768 tokens - 49,152 measured 0.226 GiB spilled - so the 27B's "
              "49,152-token headroom is not offered. It has NO vision: the 27B "
              "reported vision, this model reports completion, tools and thinking "
              "only. It clears the two-effect instruction the 27B dropped - on "
              "'add squats to my workout log and pin it' it emits both the append "
              "and the pin (22/22 tool calls correct against 18/19) - but on the "
              "mood-log sentence it also created one extra note the owner did not "
              "ask for by name. On three deliberately benign probes the uncensored "
              "tag changed nothing observable - what it does on material this "
              "project deliberately never tested is unknown. The 27B it replaced is "
              "NOT deleted: it stays on this PC as the pooled lane's `creative` mode "
              "model and the smaller-footprint alternative. "
              "`muse-glimmer-uncensored:30b` (15.77 GiB, already on this PC, tools "
              "and thinking) is still described rather than chosen, because it has "
              "NOT been benchmarked on this PC. The other downloaded MoE candidate, "
              "`TrevorJS/gemma-4-26B-A4B-it-uncensored`, is NOT measured on this PC "
              "and is not a choice. A window above 32,768 tokens is not offered, so "
              "very long documents are Documents & Notes' job.",
        model="huihui_ai/qwen3-abliterated:30b-a3b-instruct-2507-q4_K_M",
        lane="pooled", context=32768, pending=False,
        heavy_mode=True, mode="general-uncensored",
        heavy_words="This preset needs all three cards at once as one pooled lane. "
                    "While it runs, the everyday model is paused - it comes back, "
                    "proved from the model list, when you apply a preset that is "
                    "not heavy, and a coding model another preset left loaded is "
                    "ended first, because only one preset's model is loaded at a "
                    "time. It loads about 19.5 GiB with nothing spilled into "
                    "system memory, takes 55-66 seconds cold and writes about 21 "
                    "tokens a second.",
        measured={"tok_s": 21, "tok_s_on": "2026-11-19",
                  "tok_s_runs": [62.55, 19.71, 21.04], "tok_s_median": 21.04,
                  "tok_s_spread_pct": 203.6,
                  "tok_s_note": "19.520 GiB, 0.000 GiB spill, all three cards, "
                                "32,768 context; THREE separate loads on a PC with "
                                "no test load, one fixed-prompt decode each at "
                                "temperature 0, read 62.55, 19.71, 21.04 tok/s - median 21.04, "
                                "published as the rounded figure ~21. The three "
                                "disagree by 203.6% of the median: the cards' "
                                "clock state, not competing load (run 1's RTX 2060 "
                                "at 1,995 MHz, runs 2 and 3 near 800 MHz). The PC "
                                "was running its own assistant and browser (12-17% CPU on the perf counter; no test load), so ~21 is a floor, "
                                "not a best case, and the row publishes the median "
                                "plus this spread rather than a stable-looking "
                                "number (ruling 5.4). The earlier ten-sample set "
                                "on a busy PC read 16.19-20.22 tok/s (median 17.16)",
                  "size_gib": 19.520, "vram_gib": 19.520, "spill_gib": 0.0,
                  "cold_load_s": 66.3, "cold_load_range_s": [55.1, 66.3],
                  "context_measured": 32768,
                  "context_zero_spill": 32768,
                  "spill_at_49152_gib": 0.226,
                  "params_b": 30.5,
                  "capabilities": ["completion", "tools", "thinking"],
                  "quality_general": "20/24 on the blind eight-task battery of "
                                     "2026-11-19 - a TIE with the 27B it replaced, "
                                     "which also scored 20/24; one rater, model "
                                     "known while marking, so the mechanical cells "
                                     "are the firm ones",
                  "tool_calls": "22/22 emitted (100%) and 22/22 fully correct "
                                "(15/15 repo bench + 3/3 squats + 4/4 notes "
                                "tasks); the 27B was 18/19 and dropped the pin on "
                                "the squats sentence. Caveat: on the mood-log "
                                "sentence it also made one extra, unrequested note",
                  "alternative": "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M - the "
                                 "model this row replaced on 2026-11-19, still on "
                                 "this PC as the pooled lane's `creative` mode "
                                 "model: 17.379 GiB, 0.000 GiB spilled, a "
                                 "49,152-token zero-spill window, vision, ~10 tok/s",
                  "source": "measured on this PC on 2026-11-19 "
                            "(10:35:23-10:59:58 PST) on the real pooled lane (port "
                            "11450, the two named lanes paused, one model "
                            "resident): 20,959,251,656 B resident and the same "
                            "20,959,251,656 B in the cards' memory at 32,768 "
                            "tokens (0.000 GiB spilled); 49,152 measured 0.226 GiB "
                            "spilled and was disqualified; the speed is the median "
                            "of THREE separate loads on a PC with no test load (the "
                            "three decodes read 62.55, 19.71, 21.04 tok/s; median 21.04, spread "
                            "203.6%, published as ~21), with zero suite "
                            "runners, no LLM call in flight, no model download and "
                            "every GPU idle before each load; the PC's own assistant "
                            "and browser held a 12-17% CPU baseline on the perf counter (no test load), so the "
                            "figure is a floor; the earlier ten-sample busy-PC set "
                            "read 16.19-20.22 (median 17.16), kept as the honest "
                            "limit, never the figure; 20/24 on the "
                            "project's blind eight-task battery at 32,768; 22/22 "
                            "tool calls emitted and 22/22 fully correct; a "
                            "55.1-66.3 s cold load over three cold loads; /api/show "
                            "reports completion, tools and thinking and NO vision. "
                            "Full evidence: "
                            ".dsh-scratch/wave21/research/MEASURE-MOE.md; the "
                            "quiet-machine three-run median and its spread: "
                            ".dsh-scratch/wave21/research/quiet-median-2026-11-19/ "
                            "(median-run.json, SUMMARY.md)"},
        prompt="balanced", diet="balanced",
        words=("uncensored", "no filter", "unfiltered", "general uncensored",
               "uncensored model"),
        strong=("general uncensored", "uncensored"),
    ),
    Preset(
        id="coding", title="Coding", focus="code, files, debugging, multi-step work",
        what="For writing and fixing code, reading a project, and long tool-driven "
             "coding jobs: the 30B coding model on ONE lane that sees all three cards, "
             "started on demand by this apply.",
        cost="HEAVY MODE: it fills ALL THREE GPUs (16.17 GiB of video memory here, with the "
             "same q8_0 cache the everyday lane uses, and nothing pushed into system "
             "RAM) and pauses the everyday model while it works, for about 32 s on "
             "a cold load. Measured 2026-11-07 at 49,152 tokens on all three cards: "
             "83.8 tokens a second after a 900-word prompt, prompt ~1,644 tokens a "
             "second, zero CPU spill. The same-night two-card control (same q8_0 cache) "
             "at 32,768 tokens read 60.6 tokens a second with a 69.6 s cold load; the "
             "2026-11-03 shipped record used the default f16 cache and read 80.4 at a "
             "36.0 s load, so it is not a like-for-like baseline. Against the control "
             "the three-card window is about 38% faster; against the older record the "
             "gain is small - the real change is the 16,384-token wider window with "
             "zero spill and no spill allowance. The older figures (76.2 tok/s at "
             "28,672; 80.4 at 32,768 with 323.5 MiB spilled) are kept in "
             "docs/MEASURED-2026-11-07-THREE-GPU.md.",
        worse="Applying it makes it the model chat uses, so the everyday 26B is NOT "
              "resident while it runs - it comes back when you apply another "
              "preset, and that switch is the everyday lane's own 9B reload, not "
              "an instant swap. It is "
              "not a quick helper: it takes all three cards for as long as it is on, "
              "and nothing else can be loaded beside it. Measured about 59 tokens a "
              "second at 65,536 tokens, so the wider window is not offered.",
        model="qwen3-coder-30b-a3b-ud-q3-k-xl", lane="pooled", context=49152,
        prompt="coding", diet="coding", heavy_mode=True,
        heavy_words="This preset needs all three cards at once as one pooled lane. "
                    "While it runs, the everyday model is paused - it comes "
                    "back, proved from the model list, when you apply a preset that "
                    "is not heavy, and that reload is the everyday lane's own 9B "
                    "load, not an instant swap. Loading it takes about half a "
                    "minute.",
        tools=("code", "files"),
        measured={"tok_s": 40.3, "tok_s_on": "2026-11-17",
                  "tok_s_note": "16.17 GiB, 0 spill, all three cards, 49,152 "
                                "context; two runs read 40.3-51.2 tok/s, the low "
                                "end is shown",
                  "rubric": "6/6 coding rubric", "size_gib": 16.2,
                  "gpu_use": "100% GPU across all three cards", "cold_load_s": 31.6,
                  "spill_gib": 0.0, "context_zero_spill": 49152,
                  "context_measured": 49152,
                  "source": "measurement 2026-11-07 on all three cards with "
                            "OLLAMA_SCHED_SPREAD=1: 49,152 tokens loaded at 16.2 GiB "
                            "entirely in video memory, 83.8 tok/s warm generation "
                            "after a 900-word prompt, prompt ~1,644 tok/s, cold load "
                            "31.6 s, three cards used (nvidia-smi deltas). The same-night "
                            "two-card control (q8_0, 32,768 tokens) measured 60.58 tok/s "
                            "with a 69.611 s cold load and zero spill as well; the "
                            "2026-11-03 shipped record used the default f16 cache and "
                            "read 80.36 tok/s at a 36.0 s load, so the two baselines are "
                            "not comparable. 65,536 tokens measured 59.06 tok/s and "
                            "98,304 measured 88.69 tok/s, both with zero spill; 49,152 "
                            "is the larger of the two windows the Q2 ruling named "
                            "(49,152 and 65,536) that clears the 75 tok/s bar - 98,304 "
                            "was outside those windows and is recorded, not chosen. "
                            "The 6/6 coding rubric was measured "
                            "2026-10-18 on two cards and was not re-run. Evidence: "
                            "docs/MEASURED-2026-11-07-THREE-GPU.md and "
                            ".dsh-scratch/GPU-3WAY-2026-11-06/bench/results3/."},
        words=("code", "coding", "program", "android", "app", "debug", "bug",
               "kotlin", "python", "script", "compile", "repository", "git"),
        strong=("writing code", "fix a bug", "build an app", "app development",
                "coding"),
    ),
    Preset(
        id="agentic_vision", title="Agentic + Vision",
        focus="tools, steps, forms, browser, phone, pictures",
        what="For work that takes several steps with tools - browser, phone, forms, "
             "notes - and pictures: the vision model reads the image, and a "
             "picture-capable model stays off the display card.",
        cost="Measured 2026-10-18: it accepts pictures and answered correctly (minor "
             "mislabels of status indicators). Browser: 4.45 s to first token, 25.6 s "
             "total. Desktop: 0.89 s first token / 46.9 s total warm, 27.6 s / 70.2 s "
             "cold - these are LATENCY, not tokens a second.",
        worse="Slow on the desktop UI (about 47 s warm, 70 s cold for a full answer), "
              "and the faster first-token fallback qwen3-vl:8b-thinking produced NO "
              "answer on the desktop UI (all thinking, done_reason=length), so it is "
              "only a simple-page option.",
        model="qwen3.5:9b", lane="main", context=16384,
        prompt="agentic", diet="agentic",
        tools=("browser", "phone", "forms", "notes"),
        measured={"tok_s": 40.1, "tok_s_on": "2026-11-17",
                  "tok_s_note": "5.49 GiB, 0 spill, one card (RTX 2060), 16,384 "
                                "context",
                  "vision_latency_s": {"browser_first_token": 4.45,
                                       "browser_total": 25.6,
                                       "desktop_warm_first_token": 0.89,
                                       "desktop_warm_total": 46.9,
                                       "desktop_cold_first_token": 27.6,
                                       "desktop_cold_total": 70.2},
                  "source": "vision test 2026-10-18: pictures accepted, answers correct "
                            "(minor status-indicator mislabels); speeds are LATENCY, not tok/s",
                  "fallback": {"model": "qwen3-vl:8b-thinking",
                               "note": "browser 0.39 s first token / 25.9 s total and exact, "
                                       "but on the desktop UI no answer at 3,000 or 700 tokens "
                                       "(all thinking, done_reason=length) - a first-token "
                                       "option for simple pages only, not the default"}},
        words=("agent", "agentic", "multi-step", "browser", "phone", "form",
               "screenshot", "picture", "image", "vision", "steps", "automate"),
        strong=("multi-step work", "use the browser", "read this screenshot",
                "look at this picture", "agentic"),
    ),
    Preset(
        id="fast", title="Fast", focus="the quickest short answers",
        what="The quickest preset: qwen3.5:4b at the 16,384-token window it is for, "
             "on the everyday lane. Since 2026-11-18 there is no separate fast "
             "card: applying it makes qwen3.5:4b the model chat uses, and going "
             "back to General starts the pooled three-card lane for its 26B again.",
        cost="Measured 2026-10-10 on an RTX 2080 SUPER: 77.1 tokens a second and "
             "4.15 GB of video memory at a 65,536-token window (the file is 3.16 GB "
             "on disk). Since 2026-11-18 Fast shares the ONE-card everyday lane "
             "(the RTX 2060), so that 2080 SUPER figure is the model's own "
             "measurement on this PC rather than a fresh one for the lane; this row "
             "keeps the 16,384-token window it is for.",
        worse="The small model: fastest measured writer here, and the bench's three "
              "short prompts were only called broadly correct rather than scored. "
              "Chosen for waiting less, not for care. The 26B does not fit beside it "
              "on the same three cards, so switching back to General costs the "
              "everyday model's cold load (about 50 seconds).",
        model="qwen3.5:4b", lane="main", context=16384,
        prompt="fast", diet="fast",
        measured={"tok_s": 83.2, "tok_s_on": "2026-11-17",
                  "tok_s_note": "3.20 GiB, 0 spill, one card (RTX 2080 SUPER), "
                                "16,384 context",
                  "size_gib": 3.16, "vram_gib": 4.15, "spill_gib": 0.0,
                  "context": 65536,
                  "source": "measured 2026-10-10 at 65,536 tokens on the RTX 2080 "
                            "SUPER (repo restatement: docs/WORK-SETUPS.md:29, "
                            "jarvis_work.py:262); the everyday lane is the one-card "
                            "RTX 2060 and this row keeps 16,384"},
        words=("fast", "quick", "quickly", "short answer", "one-off", "hurry",
               "speed", "asap"),
        strong=("quick answer", "as fast as possible", "fast"),
    ),
    Preset(
        id="reflect", title="Reflective Coach",
        focus="talking a difficult thought through",
        what="For talking something through: a calm listener that reflects what you "
             "said first and asks one gentle question at a time. Since 2026-11-18 it "
             "thinks on all three cards at once, so a difficult thought gets the whole "
             "machine instead of one card.",
        cost="HEAVY MODE: it needs all three cards at once as one pooled lane and "
             "pauses the everyday 9B model while it thinks. Measured on this PC: "
             "15.5 GiB loaded with 0.68 GiB (4.4%) spilled into system memory, 96% "
             "in the cards' memory and a 52.0 s cold load (2026-11-09); the "
             "2026-11-17 re-measurement read 25.4-36.5 tokens a second, and the LOW "
             "end (25.4) is the figure this row shows. No model on this PC has been "
             "measured for empathy or reflective quality, and nothing here claims "
             "it.",
        worse="A model choice only - it changes no wording by itself. It is not a "
              "therapist: it gives no diagnosis, keeps no therapy record and the "
              "crisis help stays exactly where it already is. Applying it pauses the "
              "everyday model while it loads (about a minute), so it is for a session "
              "of thinking, not for a quick question.",
        model="gemma4:26b-a4b-it-qat", lane="pooled", context=32768,
        heavy_mode=True, mode="gemma4-26b-a4b",
        prompt="balanced", diet="balanced",
        measured={"tok_s": 25.4, "tok_s_on": "2026-11-17",
                  "tok_s_note": "15.50 GiB, 0.68 GiB spill, all three cards, "
                                "32,768 context; two runs read 25.4-36.5 tok/s, the "
                                "low end is shown",
                  "size_gib": 15.5, "spill_gib": 0.68,
                  "spill_pct": 4.4, "vram_pct": 96, "cold_load_s": 52.0,
                  "context_measured": 32768,
                  "source": "model matrix 2026-11-09: gemma4:26b-a4b-it-qat at "
                            "32,768 tokens loaded 15.5 GiB with 0.68 GiB (4.4%) "
                            "spilled into system memory (96% in the cards' memory), "
                            "a 52.0 s cold load and 49.26 tok/s; the 2026-11-17 "
                            "re-measurement of the same row read 25.4-36.5 tok/s, "
                            "low end shown. Same row as GEMMA4_26B_MEASURED_WORDS "
                            "above; no empathy or reflective quality was measured."},
        heavy_words="This preset needs all three cards at once as one pooled lane. "
                    "While it runs, the everyday 9B model is paused - it comes back, "
                    "proved from the model list, when you apply a preset that is not "
                    "heavy. It loads about 15.5 GiB, spills 0.68 GiB into system "
                    "memory, takes about 52 s cold and writes about 25 tokens a "
                    "second (the low end of two 2026-11-17 runs).",
        words=("reflect", "talk it through", "thinking out loud", "coach",
               "difficult thought"),
        strong=("talk something through", "reflective coach"),
    ),
    Preset(
        id="pictures", title="Pictures & Screens",
        focus="reading a screenshot or a picture",
        what="For looking at a picture or a screenshot and talking about it: a 12B "
             "vision model on the all-three-card lane that holds the whole model in "
             "the cards' memory. Agentic + Vision is the version that also drives "
             "tools.",
        cost="HEAVY MODE: it needs all three cards at once as one pooled lane and "
             "pauses the everyday 9B model while it works. Measured on this PC on "
             "2026-11-18 on that lane at 32,768 tokens: 8.70 GiB loaded ENTIRELY in "
             "the cards' memory (0 B spilled), a 20.3 s cold load and 28.1 tokens a "
             "second.",
        worse="Picture QUALITY has no scoring battery. The measured check behind this "
              "row is a generated picture and a generated settings screenshot: it read "
              "the picture's words and shapes and named the screenshot's Save button, "
              "server address and red banner exactly as the 30B vision model did - but "
              "that is a reading test, not a score against other models. It is a 12B "
              "model, smaller than the 30B it replaces, so a busy or hard screenshot "
              "can be read less well; its general quality is the project's own blind "
              "eight-task battery's 21/24 (2026-11-17), one below the 26B's 22/24. It "
              "pauses the everyday model for about 20 seconds while it loads. Live "
              "phone-camera frames are explicitly unmeasured.",
        model="gemma4:12b-it-qat", lane="pooled", context=32768,
        heavy_mode=True, mode="gemma4-12b",
        prompt="balanced", diet="balanced",
        tools=("pictures",),
        measured={"tok_s": 28.08, "tok_s_on": "2026-11-18",
                  "tok_s_note": "8.70 GiB, 0 spill, all three cards, 32,768 "
                                "context; one run on the real pooled lane read "
                                "28.08 tok/s",
                  "size_gib": 8.696, "vram_gib": 8.696, "spill_gib": 0.0,
                  "cold_load_s": 20.3, "context_measured": 32768,
                  "picture_test": "read 'ATLAS 42' and the two shapes from a "
                                  "generated picture, then named the Save button, "
                                  "the server address and the red banner from a "
                                  "generated screenshot - the same answers the 30B "
                                  "gave",
                  "quality_general": "21/24 on the blind eight-task battery of "
                                     "2026-11-17",
                  "replaced": "qwen3-vl:30b-a3b-instruct at 32,768 measured 2.24 "
                              "GiB spilled on 2026-11-18 (and 1.65 GiB at 16,384), "
                              "so it was not kept",
                  "source": "measured on this PC 2026-11-18 on the real pooled "
                            "lane (port 11450, the three named lanes paused, one "
                            "model resident, thinking off - the app's ordinary "
                            "turn): 9,336,929,643 B resident and 9,336,929,643 B "
                            "in video memory (0 B spilled), a 20.3 s cold load "
                            "and 28.08 tok/s warm. The supplied picture and "
                            "screenshot tests are in "
                            ".dsh-scratch/preset-pictures-2026-11-18/ (screenshot-test.png, "
                            "rows3.jsonl); the quality battery is "
                            ".dsh-scratch/wave21/quality-battery/REPORT.md."},
        heavy_words="This preset needs all three cards at once as one pooled lane. "
                    "While it runs, the everyday 9B model is paused - it comes back, "
                    "proved from the model list, when you apply a preset that is not "
                    "heavy. It loads about 8.70 GiB with NOTHING spilled into system "
                    "memory, takes about 20 s cold and writes about 28 tokens a "
                    "second.",
        words=("picture", "screenshot", "screen", "image", "photo", "look at"),
        strong=("read this screenshot", "look at this picture"),
    ),
    Preset(
        id="documents", title="Documents & Notes",
        focus="long reading, notes and study",
        what="For long documents, notes and study material: the same measured setup as "
             "General - qwen3.5:9b on the 2060 with the full 196,608-token window - "
             "named so long reading, note synthesis and study guides are one click "
             "instead of remembering which preset has the big window.",
        cost="Same measured setup as General: 44.9 tokens a second, 9.17 of the 12 GB, "
             "no spill. The window is the point - it is what stops a long document "
             "being cut before the model sees it.",
        worse="Not the quickest; fine for reading, not for waiting. Same model as "
              "General, so this row adds a named choice and the full window, not a "
              "different model.",
        model="qwen3.5:9b", lane="main", context=196608,
        prompt="balanced", diet="balanced",
        measured={"tok_s": 38.1, "tok_s_on": "2026-11-17",
                  "tok_s_note": "9.18 GiB, 0 spill, one card (RTX 2060), "
                                "196,608 context; the same measured row as General",
                  "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        words=("document", "documents", "long read", "summarise", "summarize", "pdf",
               "long text", "notes", "wiki", "study"),
        strong=("read this long document", "summarise this"),
    ),
    Preset(
        id="browser", title="Browser & Forms",
        focus="long pages and multi-step web work",
        what="For long web pages and multi-step form work: the long-context model on "
             "the 12 GB card with the full 196,608-token window, so a whole page plus "
             "its steps fit. Agentic + Vision stays the short tool-loop setup.",
        cost="Same measured setup as General: qwen3.5:9b on the 2060 at 196,608 tokens, "
             "44.9 tokens a second, 9.17 of the 12 GB, no spill.",
        worse="Browser and form work has not been measured through this row, and no "
              "tool-success rate is claimed; the model is the same one Agentic + "
              "Vision already uses.",
        model="qwen3.5:9b", lane="main", context=196608,
        prompt="agentic", diet="agentic",
        measured={"tok_s": 38.1, "tok_s_on": "2026-11-17",
                  "tok_s_note": "9.18 GiB, 0 spill, one card (RTX 2060), "
                                "196,608 context; the same measured row as General",
                  "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        tools=("browser", "forms"),
        words=("browser", "web page", "form", "fill in", "website"),
        strong=("use the browser", "fill in this form"),
    ),
    Preset(
        id="medical", title="Medical Expert",
        focus="clinical reading and patient-advocate questions",
        what="For reading clinical material carefully and in calm plain words: lab panels, "
             "letters, medication lists and health questions. It is a purpose-trained "
             "medical model on all three cards at once. It is not a doctor, gives no "
             "diagnosis and replaces no clinician.",
        cost="HEAVY MODE: it needs all three cards at once (17.31 GiB loaded entirely in "
             "video memory, 0 B spilled) and pauses the everyday 9B model while it runs. "
             "It is slow: a 46.8 s cold load, and the 2026-11-17 re-measurement read "
             "11.4-11.7 tokens a second (the low end, 11.4, is the row's figure); the "
             "older 2026-11-09 coding-prompt run read 9.27 (11.1 on the measured "
             "~150-word explanation, 7.89 on the four-token answer). Measured on this PC "
             "(model-bench run 20261109-105956, the medgemma window row).",
        worse="It has NO tool calling - `ollama show` reports no `tools` capability, so it "
              "cannot use Jarvis's tools, browser or files. It reports vision (pictures), "
              "but its picture quality is not measured here. It is not a doctor: no "
              "diagnosis, no prescription and no replacement for your own clinician, and a "
              "model trained on clinical text can still be wrong about your case.",
        model="medgemma:27b", lane="pooled", context=32768, heavy_mode=True, mode="medical",
        prompt="balanced", diet="balanced",
        measured={"tok_s": 11.4, "tok_s_on": "2026-11-17",
                  "tok_s_note": "17.31 GiB, 0 spill, all three cards, 32,768 "
                                "context; two runs read 11.4-11.7 tok/s, the low "
                                "end is shown",
                  "tok_s_long": 11.1, "tok_s_short": 7.89,
                  "size_gib": 17.31, "spill_gib": 0.0, "cold_load_s": 46.8,
                  "context_measured": 32768,
                  "gpu_use": "100% in video memory, 0 B spilled",
                  "tools": 0, "vision": "reported, not measured",
                  "source": "model matrix 2026-11-09 10:59:56, windows[1] medgemma: "
                            "18,588,222,089 B loaded, spill 0, load 46.8 s, summary "
                            "decode 9.27 tok/s (long 11.1, short 7.89); the "
                            "2026-11-17 re-measurement read 11.4-11.7, low end "
                            "shown; no tools"},
        heavy_words="This preset needs all three cards at once as one pooled lane. "
                    "While it runs, the everyday 9B model is paused - it comes back, "
                    "proved from the model list, when you apply a preset that is not "
                    "heavy. It loads about 17.31 GiB, takes about 47 s cold, writes "
                    "slowly (about 11 tokens a second on the row's 2026-11-17 "
                    "re-measurement) and cannot use tools.",
        words=("medical", "medicine", "doctor", "symptom", "symptoms", "lab",
               "lab result", "prescription", "health", "clinical", "patient",
               "diagnosis"),
        strong=("medical question", "read this lab result", "medical",
                "health question"),
    ),
)

PRESET_IDS = tuple(p.id for p in PRESETS)
_BY_ID = {p.id: p for p in PRESETS}


def pooled_modes() -> tuple:
    """The FOUR pooled mode rows the preset layer owns (2026-11-09).

    `jarvis_big_coder.MODES` owns coding/deep_think/creative. This is the preset
    layer's own extra rows: `medical`, derived from the Medical Preset row so its
    model and window are typed once; the two measured candidates
    (`gemma4-26b-a4b`, `gemma4-12b`), which Reflective Coach and Pictures &
    Screens apply; and `general-uncensored` (since 2026-11-18, the measured
    uncensored 30B MoE since 2026-11-19), derived from the
    General Uncensored row the same way `medical` is, so that preset's model and
    32,768-token window are typed once. Each row is the ONE copy the preset and
    the lane both read rather than two numbers that can drift.
    `gemma4:26b-a4b-it-qat` is also the General preset's model since 2026-11-18,
    on this same pooled lane at the same 32,768-token window - `mode
    "gemma4-26b-a4b"` is shared by General and Reflective Coach, and only one
    preset's model is loaded at a time, so no two rows ever share a machine.
    The 2026-11-18 measurements replaced the `qwen3-vl-30b-a3b` row: that 30B
    model spilled 2.24 GiB on the real lane (and 1.65 GiB at 16,384), so its
    allowance is not carried here - the 12B row's allowance is ZERO, which is
    what `load_coder`'s zero-spill rule checks. The uncensored MoE row's
    allowance is ZERO too: it measured 0.000 GiB spilled at 32,768, and the
    49,152 rung measured 0.226 GiB, which is why 32,768 is the window that
    ships (it replaced the uncensored 27B on 2026-11-19 - only this preset's
    row moved; `creative` keeps that 27B).
    Read by `jarvis_model_lanes` and `jarvis_big_coder` through lazy imports.
    Never raises; `()` when the Medical row is absent (a trimmed backend).
    """
    p = _BY_ID.get("medical")
    if p is None or not p.mode:
        return ()
    rows = [
        {"key": p.mode, "label": "Medical", "model": p.model,
         "num_ctx": p.context, "measured_words": MEDICAL_MEASURED_WORDS,
         "spill_allowance": 0, "needs_cards": 3},
        {"key": "gemma4-26b-a4b", "label": "Gemma 4 26B A4B",
         "model": "gemma4:26b-a4b-it-qat", "num_ctx": 32768,
         "measured_words": GEMMA4_26B_MEASURED_WORDS,
         "spill_allowance": round(0.681 * 1024 ** 3), "needs_cards": 3},
        {"key": "gemma4-12b", "label": "Gemma 4 12B",
         "model": "gemma4:12b-it-qat", "num_ctx": 32768,
         "measured_words": GEMMA4_12B_MEASURED_WORDS,
         "spill_allowance": 0, "needs_cards": 3},
    ]
    # The uncensored row, derived from its own Preset row (model and window
    # typed once there). It is listed only when that preset really names a
    # pooled mode, so a future row that moves lane cannot leave a stale mode
    # behind for the lane to load.
    u = _BY_ID.get("general_uncensored")
    if u is not None and u.mode and u.lane == "pooled":
        rows.append({"key": u.mode, "label": "General Uncensored",
                     "model": u.model, "num_ctx": u.context,
                     "measured_words": UNCENSORED_MOE_MEASURED_WORDS,
                     "spill_allowance": 0, "needs_cards": 3})
    return tuple(rows)


OLD_IDS = ("everyday", "coding", "admin", "long", "specialist")
FOCUS_WORDS = ("quick answers", "writing", "coding", "agentic", "pictures",
               "speed")




# --------------------------------------------------------------------------
#   Applying a preset (presets.patch, 2026-10-18)
# --------------------------------------------------------------------------

CHOICE_FILE = "presets-choice.json"
APPLY_PATH = "/api/work/apply"
PENDING_LINE = "waiting for the model; nothing was changed"
#: THE PRESET THAT LOADS WHEN ATLAS ITSELF STARTS (2026-11-22). The owner's
#: ask, verbatim: *"load the general local ai model preset. and have that be the
#: default that loads anytime jarvis is reset. it should be a larger local ai
#: model in that preset compared to qwen 9b. let me set the default presets that
#: load when atlas is restarted through chat or settings"*. This file is the
#: owner's answer to the second half: `{"preset": "<id>"}`, absent means none,
#: and it is DELIBERATELY SEPARATE from `presets-choice.json` - that file records
#: the last apply and is cleared by the restart reconcile when the on-demand
#: lane is gone, while this one is the choice the owner made on purpose and must
#: outlive a restart. Read at start-up and by `/api/work`'s `startup_preset`
#: block; written only twice - after the ONE `change_own_config` card that sets
#: it, and at once when it is CLEARED (a tightening, the asymmetry every switch
#: in this program keeps).
STARTUP_FILE = "startup-preset.json"
STARTUP_PATH = "/api/work/startup-preset"



#: The contract's lane key -> jarvis_model_lanes' own lane key. The contract
#: (and both app fixtures) keep "main" for the 2060 chat lane; ma
#: jarvis_model_lanes calls that SAME lane "everyday". Translating here is the
#: difference between a working apply and a 409 "no lane called 'main'".
LANE_START_KEYS = {"main": "everyday", "coding": "coding"}

def _config_dir() -> "pathlib.Path":
    import os
    from pathlib import Path
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR", Path.home() / ".openjarvis"))


def _choice_path():
    return _config_dir() / CHOICE_FILE


def _startup_path():
    return _config_dir() / STARTUP_FILE


def choice() -> Optional[str]:
    """The preset id the owner last applied, or None. Never raises."""
    try:
        import json
        doc = json.loads(_choice_path().read_text(encoding="utf-8"))
        return str(doc.get("preset") or "") or None
    except Exception:
        return None


def _write_choice(preset_id: str) -> bool:
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _choice_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"preset": preset_id}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(_choice_path())
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   The cloud provider, and the standing escalation (2026-10-27)
# --------------------------------------------------------------------------
#
# THE OWNER'S DECISION, 2026-10-27. The Cloud row sits in the Presets menu
# beside General/Coding/Agentic+Vision/Fast (the owner's "coder, general,
# fast"), and picking one of the API services is an APPLY: ONE
# `change_own_config` card, nothing marked chosen until THIS PC's own file
# says so - the same rule every model preset already keeps
# (hud-presets.js, "a model preset is a loosening: ONE card").
#
# ONE SERVICE AT A TIME, and it is `cloud-choice.json` beside the other
# settings files. `cloud_lanes()` turns that one choice into the ONE lane name
# the whole program uses - `jarvis-escalate` - and turns "no choice" into no
# lane at all, which is `jarvis_router.choose()`'s gate "unavailable". That is
# the replacement, not a hole: before this, the lane list came from
# `litellm-proxy.yaml`, the config of a proxy that is not installed and never
# was, and it named three lanes (escalate, critic, bulk) where this program
# has one service.
#
# THE CHECKBOX UNDER IT IS A STANDING GRANT, and that is a rule the owner
# changed rather than a rule that was never there. `jarvis_router.choose()`
# says in its own words that cloud use is "per use, with permission ... and
# asks. No standing grant." (2026-09-24). On 2026-10-27 the owner asked for
# exactly that grant, and docs/DECISIONS.md records the change. What keeps it
# from being the app doing silently what the record says it never does:
#
#   * turning it ON raises ONE `change_own_config` card (`escalate_switch`'s
#     words below), and nothing is written before that yes. Turning it OFF is
#     immediate - the asymmetry every other switch in this program keeps;
#   * the FILE IS THE ONLY SOURCE of the standing yes. A client flag cannot
#     set it (`jarvis_router.choose()` reads this file, never a request body),
#     so a stale page or a phone cannot make a standing decision the PC has
#     not made;
#   * every privacy gate still runs FIRST and can still only push the turn
#     back to local: Lockdown, a tainted conversation, a picture, the screen's
#     words, a private topic, a pasted secret, the monthly money limit.
#
# WHAT THIS SECTION READS. Which keys are SAVED (Credential Manager presence -
# never a key, never a fragment, never a message) and this month's spending.
# That is the owner's own PC and it is a read; nothing here writes until a card
# has been answered.

CLOUD_CHOICE_FILE = "cloud-choice.json"
CLOUD_ESCALATE_FILE = "escalate-cloud.json"
CLOUD_ESCALATE_PATH = "/api/work/cloud-escalate"
#: The ONE cloud lane name. `jarvis_chatbot_api.CLOUD_LANES` maps it to the
#: service behind it; `jarvis_router.choose()` escalates on it and on nothing
#: else, so a stray name can never become "the cloud".
CLOUD_LANE = "jarvis-escalate"
#: The card action every loosening in this program uses.
CLOUD_ACTION = "change_own_config"
#: The Cloud row's own id - NOT one of PRESET_IDS, so both apps' ten-preset
#: list is unchanged and the phone keeps ignoring a key it does not know.
CLOUD_PRESET_ID = "cloud"


def _cloud_choice_path():
    return _config_dir() / CLOUD_CHOICE_FILE


def _escalate_path():
    return _config_dir() / CLOUD_ESCALATE_FILE


def _provider_ids() -> tuple:
    """The connected services' ids, in `jarvis_chatbot_api.PRESETS`' own order.

    Never raises: without that module (a clone, or a backend missing it) the
    answer is (). The module is imported LAZILY, inside the call, because
    this file is imported by suites that must run with no API module at all -
    the same discipline `jarvis_auto_router._money_module` uses.
    """
    try:
        import jarvis_chatbot_api as API
        return tuple(API.PRESETS)
    except Exception:
        return ()


def cloud_chosen() -> str:
    """The service id the owner last applied in the Presets menu, or "".

    "" is the honest answer for "no file", "an unreadable file", and "a name
    this PC does not know" - and it means NO cloud lane exists at all, which
    is gate "unavailable" rather than a lane nobody chose. Never raises.
    """
    try:
        import json
        doc = json.loads(_cloud_choice_path().read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(doc, dict):
        return ""
    pid = str(doc.get("provider") or "")
    if not pid:
        return ""
    known = _provider_ids()
    return pid if (not known or pid in known) else ""


def _write_cloud_choice(provider: str) -> bool:
    """Save the one provider. Atomic; False (and nothing changed) on any error."""
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _cloud_choice_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"provider": str(provider)}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(_cloud_choice_path())
        return True
    except Exception:
        return False


def cloud_lanes() -> list:
    """The cloud lanes this PC has RIGHT NOW: one name, or none.

    None is not a hole - it is gate "unavailable", the honest answer for a PC
    where the owner has not picked a cloud service. `_lane_names()` in
    jarvis_hud.py is the only caller (through cloud-escalate.patch), and it
    used to read `litellm-proxy.yaml` for three names that no longer exist.
    """
    return [CLOUD_LANE] if cloud_chosen() else []


def escalate_on() -> bool:
    """Is the PC's own standing escalation switch ON?

    ON only when the file says so, literally: absent, unreadable, corrupt or
    holding anything but `"on": true` reads as OFF. That is the same
    fail-closed shape `jarvis_auto_router`'s own switch keeps, and it is the
    direction a privacy switch has to fail in. Never raises.
    """
    try:
        import json
        doc = json.loads(_escalate_path().read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(doc, dict) and doc.get("on") is True


def escalate_why() -> str:
    """The plain sentence for `cloud.escalate.why` - "" when it is ON."""
    if escalate_on():
        return ""
    return ("not turned on for this PC" if not _escalate_path().exists()
            else "the setting on this PC cannot be read, so it stays off")


def _write_cloud_escalate(on: bool) -> bool:
    """Save the switch. Atomic; False (and nothing changed) on any error."""
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _escalate_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"on": bool(on), "on_since": time.time()},
                                  indent=2) + "\n", encoding="utf-8")
        tmp.replace(_escalate_path())
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Full GitHub mode (slice 1, 2026-11-25) - the SECOND standing yes
# --------------------------------------------------------------------------
# ONE FILE, AND IT IS BOTH THE MODE AND THE STANDING YES. The owner's ask:
# "also add a full github mode that gives full parity with less restrictions and
# less cards ... it can be enabled in chat or settings and forwards anything
# necessary to the cloud api"; "activating github mode needs a card". The design
# first wrote the mode as a setting and the standing yes as a second file; that
# is two facts one switch would have to keep in step, and the day they disagree
# is the day "off" is on. So this file IS the mode: `github-mode.json` says
# `{"on": true}` and nothing else is the truth.
#
# WRITTEN ONLY AFTER A CARD. `jarvis_asks_first.set_github_mode` raises ONE
# `github_mode` card (PC-only, Windows Hello - `jarvis_owner_check.
# PC_ONLY_ACTIONS`) and calls `write_github_mode` only when a person approved
# it. Turning it OFF is immediate and cardless, the asymmetry every other
# switch in this program keeps; the caller also clears the conversation grant
# in jarvis_agent.py, and the grant READS this file on every use, so a stale
# in-memory grant cannot outlive an off.
#
# READ WHERE. `jarvis_router.github_mode_escalation()` is the ONLY reader that
# decides anything, and it is consulted at gate 6 and nowhere else - so no
# request body, header or client flag can reach it, and every privacy gate in
# choose() has already had its chance to answer local. `jarvis_asks_first` and
# `jarvis_agent` read it for the status/payload and for the fix-write grant;
# neither can *set* it.
#
# WHY IT IS SEPARATE FROM `escalate-cloud.json` (an owner decision for the lead,
# recorded in the design): reusing the cloud switch would make GitHub mode cover
# every cloud-escalatable turn, which is wider than the owner asked for. This
# one is consulted only for a GitHub-shaped turn (`github_shaped_turn`) and it
# does not choose the service - the Presets menu's own Cloud row does.
GITHUB_MODE_FILE = "github-mode.json"


def _github_mode_path():
    return _config_dir() / GITHUB_MODE_FILE


def github_mode_on() -> bool:
    """Is full GitHub mode ON? Read from THIS PC's file and from nowhere else.

    ON only when the file says so, literally: absent, unreadable, corrupt or
    holding anything but `"on": true` reads as OFF. A privacy switch fails
    closed, the same rule `escalate_on()` above keeps. Never raises.
    """
    try:
        import json
        doc = json.loads(_github_mode_path().read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(doc, dict) and doc.get("on") is True


def github_mode_why() -> str:
    """The plain sentence for why the mode is off - "" when it is ON."""
    if github_mode_on():
        return ""
    return ("not turned on for this PC" if not _github_mode_path().exists()
            else "the setting on this PC cannot be read, so it stays off")


def write_github_mode(on: bool) -> bool:
    """Save the mode. Atomic; False (and nothing changed) on any error.

    Called ONLY from `jarvis_asks_first.set_github_mode`, after the
    `github_mode` card was approved - the same rule
    `_write_cloud_escalate` follows: a denial, a timeout or a refusal writes
    nothing at all. Short of an OS-level failure this cannot be called by a
    request body, a client flag or a tool's own choice.
    """
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _github_mode_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"on": bool(on), "on_since": time.time()},
                                  indent=2) + "\n", encoding="utf-8")
        tmp.replace(_github_mode_path())
        return True
    except Exception:
        return False


def cloud_providers() -> list:
    """One row per connected API service, for the Cloud submenu.

    The row carries the service's NAME, host and model, whether a key is
    SAVED (`True`/`False`, or `None` when Credential Manager cannot be asked),
    the PC's own plain sentence for why it cannot be used (`ready_for`), the
    money line (`money_view`) and the one honest way to add a key from an app:
    the command line to run ON THIS PC. Keys are added on the PC only - there
    is no route for it, and the phone never sends one (rule 3).

    NO KEY, NO FRAGMENT OF ONE AND NO MESSAGE is in this answer, ever.
    `lane_status()`'s own docstring says the same for the same reason.
    """
    try:
        import jarvis_chatbot_api as API
    except Exception:
        return []
    chosen = cloud_chosen()
    rows = []
    for pid, preset in API.PRESETS.items():
        try:
            saved = API.key_saved(pid)
        except Exception:
            saved = None
        try:
            why = API.ready_for(pid)
        except Exception:
            why = "this PC could not say whether that service can be used"
        try:
            model = str(API.model_for(pid)[0] or preset.model)
        except Exception:
            model = preset.model
        try:
            money = API.money_view(pid)
        except Exception:
            money = None
        rows.append({
            "id": pid, "short": preset.short, "name": preset.name,
            "company": preset.company, "host": preset.host, "model": model,
            "key_saved": saved, "ready": not why, "why": why,
            "chosen": pid == chosen,
            "money": money,
            "key_line": API.KEY_LINE.format(short=preset.short),
            "key_where": preset.key_where,
        })
    return rows


def cloud_view() -> dict:
    """The `/api/presets` answer's new `cloud` key.

    `provider` is the service in use ("" when none is), `providers` every
    connected service (see cloud_providers), `escalate` the PC's own standing
    switch. Additive: the ten presets are untouched, `version` stays 1, and
    every reader that does not know this key ignores it.
    """
    return {"provider": cloud_chosen(),
            "providers": cloud_providers(),
            "escalate": {"on": escalate_on(), "why": escalate_why()}}


def cloud_state() -> dict:
    """The cloud facts the chat may state, read fresh and never including a key.

    This is the ONE state read for the quick answers and the model's system
    line (2026-10-31): the chosen provider, whether its key is saved (a bool,
    never a value or a fragment), whether it can be used now and why not, the
    standing escalation switch, and the DeepSeek key's presence separately
    because the owner asks about that service by name. No network, no card and
    no write; a missing module leaves the fields empty rather than guessing.
    """
    out = {"available": False, "provider": "", "provider_name": "",
           "company": "", "host": "", "model": "", "key_saved": None,
           "ready": "", "escalate": False, "escalate_why": "",
           "deepseek_key_saved": None}
    try:
        import jarvis_chatbot_api as API
    except Exception:                                       # noqa: BLE001
        return out
    out["available"] = True
    try:
        out["deepseek_key_saved"] = API.key_saved("deepseek_api")
    except Exception:                                       # noqa: BLE001
        out["deepseek_key_saved"] = None
    pid = cloud_chosen()
    out["provider"] = pid
    try:
        out["escalate"] = bool(escalate_on())
        out["escalate_why"] = escalate_why()
    except Exception:                                       # noqa: BLE001
        pass
    if pid and pid in API.PRESETS:
        preset = API.PRESETS[pid]
        out["provider_name"] = preset.name
        out["company"] = preset.company
        out["host"] = preset.host
        try:
            out["model"] = str(API.model_for(pid)[0] or preset.model)
        except Exception:                                   # noqa: BLE001
            out["model"] = preset.model
        try:
            out["key_saved"] = API.key_saved(pid)
        except Exception:                                   # noqa: BLE001
            out["key_saved"] = None
        try:
            out["ready"] = str(API.ready_for(pid) or "")
        except Exception:                                   # noqa: BLE001
            out["ready"] = "this PC could not say whether that service can be used"
    return out


def cloud_state_line() -> str:
    """ONE redacted system line saying the real cloud state, for the model.

    It names the chosen service, host and model and whether a key is saved; it
    NEVER names a key value, a fragment or a message. It exists because the
    local model was denying that any external API existed even with the Cloud
    preset chosen and a DeepSeek key saved (owner-reported, 2026-10-31). The
    line also carries the real privacy rule, so the model cannot claim either
    that everything always leaves or that nothing can ever leave.
    """
    st = cloud_state()
    if not st["available"]:
        return ("The cloud state on this PC could not be read, so do not claim either that "
                "you are connected to a cloud API or that no external connection exists. "
                "Nothing is sent to a cloud service without the owner's yes.")
    provider = st["provider"]
    if not provider:
        if st["deepseek_key_saved"]:
            return ("No cloud API service is chosen on this PC, so no question can be sent "
                    "to the cloud right now; a DeepSeek API key is saved, but choosing the "
                    "Cloud row and a provider is the step. Every answer is written by the "
                    "model on this PC unless a cloud turn is arranged and allowed.")
        return ("No cloud API service is chosen on this PC, so no question can be sent to "
                "the cloud; every answer is written by the model on this PC. A cloud turn "
                "is possible only after the owner chooses the Cloud row and saves a key.")
    who = f"{st['company']} ({st['host']}, model {st['model']})"
    key = st["key_saved"]
    if key is False:
        return (f"The Cloud preset is set to {who}, but no {st['company']} API key is saved "
                f"on this PC, so no question can be sent to it until one is added in "
                f"Windows Credential Manager; answers stay on this PC.")
    if key is None:
        return (f"The Cloud preset is set to {who}, but this PC cannot read Windows "
                f"Credential Manager, so whether that service can be used is unknown. "
                f"Nothing is sent to it without the owner's yes.")
    if st["ready"]:
        return (f"The Cloud preset is set to {who}; its key is saved on this PC, but it "
                f"cannot be used right now: {st['ready']} Nothing is sent to it.")
    escalate = (" The standing escalation switch is ON, so a hard question may go there "
                "without a per-question yes after every privacy gate; it is off at once."
                if st["escalate"] else
                " The standing escalation switch is OFF, so each cloud turn needs the "
                "owner's yes.")
    return (f"The Cloud preset is set to {who}; its key is saved on this PC and it can be "
            f"used now. A question is sent there only when the owner allows it (the Try "
            f"the cloud model button, a standing switch, or an explicit request), never "
            f"with email, files, credentials, stored memory, a picture, a screen or a "
            f"tainted conversation. Choosing the preset alone sends nothing.{escalate}")


def cloud_preset_view() -> dict:
    """The Cloud row itself, in the SAME shape as a `Preset.view()`.

    Its id is "cloud", it is deliberately absent from `PRESETS`/`PRESET_IDS`
    (both apps' ten-row list stays ten rows), and its `apply` block says the
    two things that make it different: it is a cloud row, and it needs a
    provider before it can be applied.
    """
    return {
        "id": CLOUD_PRESET_ID, "title": "Cloud",
        "focus": "a second opinion from a service you have connected",
        "what": ("Let Jarvis send a hard question to one of the cloud services whose key "
                 "is saved on this PC, instead of answering it here. Choosing this row "
                 "only chooses the service; it switches no answer and sends nothing by "
                 "itself. Each answer costs a little on that account."),
        "cost": ("Every message goes to that company's own servers, under its terms, and "
                 "is billed to your account there. Jarvis stops before a message that "
                 "could pass the monthly money limit you set."),
        "worse": ("Your words leave this PC when a cloud turn is allowed. Anything private, "
                  "tainted, a picture or your screen never goes - those gates run first and "
                  "answer here. The answer is capped, so a thinking model may return its "
                  "working-out instead of an answer."),
        "model": "",
        "lane": {"key": CLOUD_PRESET_ID, "card": "", "port": 0,
                 "words": "the cloud"},
        "context": 0,
        "helper": None,
        "policy": {"prompt": "balanced", "diet": "balanced", "tools": []},
        "measured": None,
        "pending": False,
        "heavy_mode": False,
        "heavy_words": "",
        "apply": {"action": APPLY_ACTION, "switch_route": SWITCH_ROUTE,
                  "apply_route": APPLY_PATH, "lane_start": False, "auto": False,
                  "cloud": True, "needs_provider": True},
    }


def _gate(action: str, detail: dict, prompt: str):
    """`jarvis_gate.check()`, failing CLOSED on any error.

    The same shape `jarvis_big_coder._gate` uses: a gate that cannot be
    reached is a refusal, never an allow. Tests pass their own `gate_check`.
    """
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}")


def _service_words(API, provider: str) -> tuple:
    """(company, host, model, money line) for ONE service, in plain words."""
    preset = API.PRESETS[provider]
    try:
        model = str(API.model_for(provider)[0] or preset.model)
    except Exception:
        model = preset.model
    try:
        money = API.money_view(provider) or {}
    except Exception:
        money = {}
    return preset.company, preset.host, model, str(money.get("line") or "")


def _cloud_card_text(API, provider: str) -> str:
    """What applying this provider changes, in the owner's own words."""
    company, host, model, money = _service_words(API, provider)
    said = (f"Send hard questions to {company} ({host}, model {model}) instead of "
            f"answering them on this PC. Every message then goes to {company}'s own "
            f"servers, under its terms, and is billed to your account there.")
    if money:
        said += " " + money
    said += (" Anything private, a tainted conversation, a picture or your screen still "
             "never leaves this PC, and nothing on this PC changes until you say yes.")
    return said


def _escalate_card_text(API=None) -> str:
    """The ONE card turning the standing switch ON raises.

    In the owner's own words, and naming the provider when one is chosen: he
    is being asked to let Jarvis spend money and send his words without a
    per-question yes, so the sentence has to say both, and say what still
    does NOT go.
    """
    provider = cloud_chosen()
    who = "the cloud service you chose"
    if provider:
        try:
            import jarvis_chatbot_api as _API
            who = _API.PRESETS[provider].company
        except Exception:
            who = "the cloud service you chose"
    return (f"Jarvis may send a hard question to {who} without asking you first. "
            f"Anything private, a tainted conversation, a picture or your screen still "
            f"never leaves this PC, and the monthly money limit still applies.")


def apply_cloud(*, provider="", gate_check=None) -> tuple:
    """Use ONE cloud provider after the owner's single `change_own_config` card.

    ORDER, and it is the contract: refuse a provider that was not named or
    does not exist (400) -> refuse a service this PC cannot use yet, in the
    PC's own words, BEFORE any card (409: no key, no price, no monthly limit)
    -> raise the ONE card -> only after that yes, write `cloud-choice.json`
    and `presets-choice.json`.

    IT STARTS NO LANE AND SWITCHES NO MODEL. This is the one apply branch that
    must not run `start_lane`/`switch_model`: a cloud preset changes nothing
    local, and starting a GPU lane for it would unload the model the owner is
    using. `test_presets_cloud.py` proves both spies were never called.
    """
    pid = str(provider or "").strip()
    try:
        import jarvis_chatbot_api as API
    except Exception:
        return 503, {"ok": False, "changed": False,
                     "error": ("the cloud services are not set up on this PC, so no "
                               "cloud provider can be chosen")}
    ids = tuple(API.PRESETS)
    if not pid:
        return 400, {"ok": False, "changed": False,
                     "error": f"say which cloud service; the services are {', '.join(ids)}"}
    if pid not in API.PRESETS:
        return 400, {"ok": False, "changed": False,
                     "error": (f"there is no cloud service called {pid!r}; the services "
                               f"are {', '.join(ids)}")}
    why = ""
    try:
        why = str(API.ready_for(pid) or "")
    except Exception:
        why = "this PC could not say whether that service can be used"
    if why:
        return 409, {"ok": False, "changed": False, "error": why,
                     "provider": cloud_chosen()}
    words = _cloud_card_text(API, pid)
    company = API.PRESETS[pid].company
    verdict = (gate_check or _gate)(
        CLOUD_ACTION, {"text": words},
        f"send hard questions to {company} instead of answering them on this PC")
    if not getattr(verdict, "allowed", False):
        return 200, {"ok": False, "changed": False, "provider": cloud_chosen(),
                     "preset": cloud_preset_view(),
                     "outcome": str(getattr(verdict, "outcome", "refused")),
                     "message": "Not changed - the cloud provider stays as it was."}
    previous = choice()
    if not _write_cloud_choice(pid):
        return 503, {"ok": False, "changed": False,
                     "error": ("the chosen cloud provider could not be saved on this PC; "
                               "nothing was changed")}
    if not _write_choice(CLOUD_PRESET_ID):
        return 503, {"ok": False, "changed": False,
                     "error": ("the cloud provider was saved but the chosen preset could "
                               "not be; the next read will say which provider is in use")}
    return 200, {"ok": True, "changed": True, "provider": pid,
                 "preset": cloud_preset_view(), "previous_preset": previous,
                 "cloud": cloud_view(),
                 "message": (f"{company} is the cloud service Jarvis will use. Nothing "
                             f"on this PC's models changed, and nothing is sent until a "
                             f"hard question clears every gate and you have said yes.")}


def cloud_escalate(*, on, gate_check=None) -> tuple:
    """Turn the standing escalation switch on (ONE card) or off (at once).

    ON is a LOOSENING - Jarvis may then spend money and send the owner's words
    with no per-question yes - so it raises ONE `change_own_config` card and
    writes nothing before that yes. OFF is a tightening and is instant, the
    same asymmetry every other switch in this program keeps
    (`set_web_search`: "OFF at once; ON raises the one approval card").

    It refuses ON with no provider chosen, BEFORE a card: a standing yes to a
    service that is not chosen cannot do anything, and a card for a setting
    that cannot work would be a lie.

    Returns (http status, body). `card` says whether a card was raised, so an
    app can say "waiting for your click" instead of guessing.
    """
    want = bool(on)
    now = escalate_on()
    if want == now:
        return 200, {"ok": True, "on": now, "changed": False, "card": False,
                     "message": f"Escalation is already {'on' if want else 'off'}.",
                     "escalate": {"on": now, "why": escalate_why()}}
    if want:
        if not cloud_chosen():
            return 409, {"ok": False, "on": False, "changed": False, "card": False,
                         "error": ("no cloud service has been chosen on this PC yet - "
                                   "pick one in the Presets menu first"),
                         "escalate": {"on": False, "why": escalate_why()}}
        words = _escalate_card_text()
        verdict = (gate_check or _gate)(
            # The card's detail carries the two keys the gate's card payload
            # reads for the "what it costs" line (2026-11-06, Hermes borrow
            # #7): this card can spend money on the chosen cloud service, and
            # the service is named so the line can find its ledger. `text` stays
            # the card's own words, unchanged.
            CLOUD_ACTION, {"text": words, "costs_money": "cloud",
                           "pid": cloud_chosen()},
            "let hard questions go to the cloud without asking first")
        if not getattr(verdict, "allowed", False):
            return 200, {"ok": False, "on": now, "changed": False, "card": True,
                         "outcome": str(getattr(verdict, "outcome", "refused")),
                         "message": "Not turned on - Jarvis still asks before every cloud turn.",
                         "escalate": {"on": now, "why": escalate_why()}}
    if not _write_cloud_escalate(want):
        return 503, {"ok": False, "on": now, "changed": False, "card": want,
                     "error": ("the switch could not be saved on this PC; nothing was "
                               "changed"),
                     "escalate": {"on": now, "why": escalate_why()}}
    return 200, {"ok": True, "on": want, "changed": True, "card": want,
                 "message": ("Jarvis may now send a hard question to the cloud without "
                             "asking first. Everything private still stays here."
                             if want else
                             "Jarvis asks before every cloud turn again."),
                 "escalate": {"on": want, "why": escalate_why()}}


def escalate_from_body(body) -> tuple:
    """`POST /api/work/cloud-escalate {"on": true|false}` -> cloud_escalate()."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "expected a JSON object"}
    if "on" not in body:
        return 400, {"ok": False,
                     "error": 'expected {"on": true} or {"on": false}'}
    if not isinstance(body.get("on"), bool):
        return 400, {"ok": False, "error": '"on" must be true or false'}
    return cloud_escalate(on=body["on"])


def _lane_url(key: str) -> str:
    return f"http://127.0.0.1:{LANES[key]['port']}"


def _active_url() -> str:
    import jarvis_models
    return jarvis_models.ollama_url_on_this_pc().rstrip("/")


def _set_active_url(url: str) -> bool:
    import json
    try:
        from pathlib import Path
        d = _config_dir(); d.mkdir(parents=True, exist_ok=True)
        f = d / "presets-active-lane.json"
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"base_url": str(url).rstrip("/")}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(f)
        return True
    except Exception:
        return False



# --------------------------------------------------------------------------
#   After a RESTART: the on-demand pooled lane does not come back (2026-11-08)
# --------------------------------------------------------------------------
#
# THE GAP THIS CLOSES (measured live, 2026-11-08). The Coding preset's lane is
# NOT a Windows logon task - by the owner's 2026-11-04 decision there is no
# third lane task, because a pooled Ollama that starts with Windows would hold
# every card against the everyday model. It is ONE `ollama serve` this process
# starts on demand (`jarvis_model_lanes.start_pooled_lane`, port 11450). Three
# things survive a restart while that server does not:
#   * `presets-choice.json` still says "coding";
#   * `presets-active-lane.json` still says http://127.0.0.1:11450, and the
#     HUD patch's active_ollama_url() points every chat turn there;
#   * `model-state.json` still says the current model is the pooled 30B.
# Tonight's deploy restarted the backend at 18:56 and all three were left as
# they were: coding-routed chats then failed with "The local model is not
# running" (a false sentence - the everyday lane was fine), and the wake-time
# warm-up loaded the pooled 30B on the ONE-card everyday lane at Ollama's 8192
# context, which is the HUD's 74%-on-GPU / 26%-CPU warning. Both are the same
# state inconsistency, so this is where it is repaired.
#
# WHAT IT DOES, and what it deliberately does NOT do:
#   * only when the remembered lane is the POOLED port and nothing answers
#     there - the two logon-task lanes are left alone (their own Windows tasks
#     race the backend at logon, and a briefly-down everyday lane is not this
#     bug);
#   * points the chat lane back at the configured lane (OLLAMA_URL, the
#     everyday model), rolls the model back to the one it replaced, and forgets
#     the preset that cannot be served - so the HUD's Presets screen says
#     plainly that nothing is chosen instead of lying;
#   * it never STARTS the pooled lane and never raises a card: starting the
#     three-card lane is a model switch the owner approves, and a background
#     reconcile must not approve one for him. Re-applying the Coding preset is
#     the one carded action that brings the pooled lane back;
#   * it never touches a lane that answers, never downloads, never leaves this
#     PC, and never raises.

LANE_FILE_NAME = "presets-active-lane.json"
_LAST_RECONCILE: dict = {"changed": False, "why": "not run yet"}


def _persisted_lane_url() -> str:
    """The lane `presets.patch`'s active_ollama_url() reads, or "". Never raises."""
    import json
    try:
        doc = json.loads((_config_dir() / LANE_FILE_NAME).read_text(encoding="utf-8"))
        url = str(doc.get("base_url") or "").strip().rstrip("/")
    except Exception:
        return ""
    if url.startswith(("http://127.0.0.1:", "http://localhost:")):
        return url
    return ""


def _pooled_port() -> int:
    """The pooled lane's own port, from the module that owns it (never typed)."""
    try:
        import jarvis_model_lanes
        return int(jarvis_model_lanes.POOLED_PORT)
    except Exception:
        return 11450


def _lane_answers(url: str, timeout: float = 2.0) -> bool:
    """Does this loopback lane answer /api/version? Read-only; False on any error."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/version",
                                    timeout=float(timeout)) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except Exception:
        return False


#: How long the Q4 probe may take. ONE TCP connect; no HTTP, no model, no card.
_POOLED_PROBE_TIMEOUT_S = 0.35


def _port_of_url(url) -> Optional[int]:
    """The loopback port a lane URL names, or None. Never raises."""
    try:
        import urllib.parse
        parts = urllib.parse.urlsplit(str(url or "").strip())
        if (parts.hostname or "").lower() not in ("127.0.0.1", "localhost", "::1"):
            return None
        port = int(parts.port or 0)
        return port if 0 < port < 65536 else None
    except Exception:
        return None


def _lane_listening(url: str, timeout: float = _POOLED_PROBE_TIMEOUT_S) -> bool:
    """Something is LISTENING on this loopback lane's port - one TCP connect.

    Q4 (2026-11-08): this is the whole probe the chat-lane getter is allowed to
    do. It opens no HTTP request, sends no /api/generate or /api/chat, loads no
    model, pauses no lane and starts nothing; sub-second by construction.
    """
    import socket
    port = _port_of_url(url)
    if not port:
        return False
    try:
        with socket.create_connection(("127.0.0.1", int(port)),
                                      timeout=float(timeout)):
            return True
    except Exception:
        return False


def active_chat_url(default: str = "") -> str:
    """Q4: the chat lane, with a dead POOLED pointer repaired atomically here.

    The HUD patch's `active_ollama_url()` calls this for every chat turn. When
    `presets-active-lane.json` names the on-demand pooled lane (`_pooled_port()`,
    11450) and a fast TCP probe shows nothing is listening there, it puts the
    file back - atomically, through the one setter every lane write uses - to the
    configured lane (`OLLAMA_URL`, normally 11436) and returns it, so a chat turn
    answers instead of failing "The local model is not running".

    What it deliberately does NOT do: never starts/auto-spawns the pooled server
    (a status/HUD poll calls this; starting the three-card lane would pause the
    ordinary lanes and cold-load 13.8 GB inside a poll), never pauses or stops a
    lane, never asks a model anything, never raises.
    """
    fallback = str(default or "").strip().rstrip("/") or _active_url()
    lane = _persisted_lane_url()
    if not lane:
        return fallback                       # no file / not loopback: today's rule
    if _port_of_url(lane) == _pooled_port() and not _lane_listening(lane):
        _set_active_url(fallback)
        return fallback
    return lane


def _applied_pooled_mode() -> str:
    """The pooled mode the APPLIED preset names, from presets-choice.json.

    `choice()` reads that file (`_choice_path`); the file is written last by a
    successful apply (`write_choice(p.id)`). A named-lane preset returns "" and
    the caller falls back to the lane's own evidence. Never raises.
    """
    try:
        p = by_id(choice())
        return str(getattr(p, "mode", "") or "") if p is not None else ""
    except Exception:
        return ""


def pooled_num_ctx() -> Optional[int]:
    """The pooled lane's configured window for the preset that is APPLIED.

    THE DEFECT THIS FIXES: this called `pooled_profile()` with no mode, so it
    answered the coding window (49,152) whatever preset had been applied. A chat
    turn then asked a 32,768-token Medical lane for 49,152 tokens - a window it
    never loaded. The answer now follows the APPLIED preset's `mode` from
    `presets-choice.json`; only when that file does not name a pooled preset
    (a just-restarted server, or the lane started outside the preset road) does
    it ask the lane what it really holds (`pooled_mode_now`, one /api/ps read),
    and it keeps the coding default as the last resort. This is read-only.
    """
    try:
        import jarvis_model_lanes as lanes
        mode = _applied_pooled_mode()
        if not mode:
            mode = str(lanes.pooled_mode_now() or "") or "coding"
        profile = lanes.pooled_profile(mode)
        return int(profile.get("num_ctx") or lanes.POOLED_CTX)
    except Exception:
        try:
            import jarvis_big_coder as big
            return int(big.mode_profile(big.DEFAULT_MODE).num_ctx)
        except Exception:
            return None


def is_pooled_lane(url) -> bool:
    """Is `url` the on-demand pooled lane's own port? Read-only, never raises.

    Split out of `lane_num_ctx` on 2026-11-15 because a caller now has to tell
    "this is not the pooled lane, so it keeps today's request" apart from "this
    IS the pooled lane and nothing can say which window it is set to". The
    second is said to the owner in jarvis_agent; treating it as the first would
    be the silent guess the 2026-11-15 measurement was made of.
    """
    return _port_of_url(url) == _pooled_port()


def lane_num_ctx(url) -> Optional[int]:
    """The configured `num_ctx` a chat request on LANE `url` must carry, or None.

    Q5 (2026-11-08): only the pooled lane has a window the chat request has to
    NAME - its 49,152 measurement - because Ollama otherwise loads at the
    model's own default (8192 here). Every other lane keeps today's behaviour:
    its server carries the window in its environment and the request sends no
    options. The number comes from the lane module's own config, never a second
    copy here.

    THAT NAME GOES ON /api/chat SINCE 2026-11-15, not on the /v1 body: `/v1`
    does not use a top-level `options` field when it picks a runner (measured
    twice - 2026-11-09 and 2026-11-15), so the number was never honoured there.
    This function still answers the number; `jarvis_agent._pooled_turn_window`
    is what decides which request carries it.
    """
    if not is_pooled_lane(url):
        return None
    return pooled_num_ctx()


def _bare_model(model) -> str:
    """A model name without the ":latest" tag Ollama adds for itself.

    Measured on the live install, 2026-11-09 (Q6b defect): `/api/ps` reported the
    pooled 30B as `qwen3-coder-30b-a3b-ud-q3-k-xl:latest`, the exact-name compare
    below did not recognise it, and the everyday lane warmed a second copy of the
    30B (74% on card / 26% on CPU - the copy the owner photographed).
    """
    x = str(model or "").strip()
    return x[:-7] if x.endswith(":latest") else x


def is_pooled_model(model) -> bool:
    """Is `model` a pooled-lane (three-card) model name? Never a 11436 client.

    Q6 (2026-11-08): the everyday lane must never be asked to load one of these
    - the 30B model cannot fit one card, and loading it there is the duplicate
    copy (74% GPU / 26% CPU) the owner photographed. The comparison strips the
    ":latest" tag Ollama reports (Q6b, measured live 2026-11-09).

    NO EXEMPTION, AND THAT IS DELIBERATE (2026-11-18). Earlier that day General
    named `gemma4:26b-a4b-it-qat` on the everyday lane, and this function had to
    exempt a tag that a preset on the everyday lane named. External review then
    ruled the lane wrong: General is a HEAVY row on the pooled lane now (see the
    module docstring), so the 26B is a pooled model like the coder and the
    picture model, and the exemption went with the reason for it. The everyday
    lane must refuse every pooled model again, including General's own.
    """
    name = _bare_model(model)
    if not name:
        return False
    try:
        import jarvis_big_coder as big
        if _bare_model(getattr(big, "MODEL", "")) == name:
            return True
        for key in getattr(big, "MODES", ()) or ():
            profile = big.MODES[key] if isinstance(big.MODES, dict) else key
            if _bare_model(getattr(profile, "model", "")) == name:
                return True
    except Exception:
        pass
    try:
        import jarvis_model_lanes as lanes
        if _bare_model(getattr(lanes, "POOLED_MODEL", "")) == name:
            return True
    except Exception:
        pass
    for row in pooled_modes():
        if _bare_model(row.get("model") or "") == name:
            return True
    return False


def reconcile_after_restart(*, probe=None, set_active_url=None,
                            rollback_model=None) -> dict:
    """Repair the persisted preset state when the on-demand pooled lane is gone.

    Called ONCE by `install()` in the real HUD process (see `_warm_on_startup`);
    every seam is injectable so the suite proves all three outcomes without a
    socket, a model or a card. Returns {"changed", "why", "lane", "preset"}.
    """
    import os as _os
    if _os.environ.get("JARVIS_SUITE_RUNNING") and not _os.environ.get(
            "OPENJARVIS_CONFIG_DIR"):
        # A suite that forgot to point OPENJARVIS_CONFIG_DIR at its own temp
        # folder must NEVER read, let alone rewrite, the owner's live preset
        # files (this happened once in a smoke check, 2026-11-08; content was
        # restored at once). It is a bug in the caller, so it is refused loudly.
        return {"changed": False, "lane": "", "preset": "",
                "why": ("refused: a suite run must point OPENJARVIS_CONFIG_DIR at "
                        "its own temp folder; nothing was touched")}
    lane = _persisted_lane_url()
    if not lane:
        return {"changed": False, "why": "no preset has been applied on this PC yet",
                "lane": "", "preset": ""}
    port = _pooled_port()
    if f"127.0.0.1:{port}" not in lane and f"localhost:{port}" not in lane:
        # A logon-task lane is restarted by its own Windows task at logon; a
        # briefly-down one is NOT this restart gap, so its files stay as they are.
        return {"changed": False,
                "why": (f"the remembered lane is not the on-demand pooled lane "
                        f"(port {port}); it is started by its own Windows task"),
                "lane": lane, "preset": str(choice() or "")}
    probe = probe or _lane_answers
    if probe(lane):
        return {"changed": False, "why": "", "lane": lane,
                "preset": str(choice() or "")}
    target = _active_url()
    lane_ok = bool((set_active_url or _set_active_url)(target))
    rolled = False
    try:
        got = (rollback_model or _default_rollback_model)()
        rolled = isinstance(got, dict) and got.get("ok") is not False
    except Exception:
        rolled = False
    preset = str(choice() or "")
    cleared = False
    try:
        _choice_path().unlink()
        cleared = True
    except FileNotFoundError:
        cleared = True
    except Exception:
        cleared = False
    why = (
        f"the remembered preset ({preset or 'one with no name'}) needed the "
        f"on-demand three-card lane at {lane}, which does not survive a "
        f"restart; chat was pointed back at {target}"
        + (", the previous model was restored" if rolled else
           " (the previous model could not be restored)")
        + (", and the preset was forgotten" if cleared else
           ", but the preset file could not be cleared")
        + ". Apply the preset again to bring the three-card lane back.")
    return {"changed": bool(lane_ok or rolled or cleared), "why": why,
            "lane": target, "preset": preset, "pooled_lane": lane,
            "lane_ok": lane_ok, "model_rolled_back": rolled,
            "preset_cleared": cleared}


# --------------------------------------------------------------------------
#   The preset that loads WHEN ATLAS STARTS (2026-11-22)
# --------------------------------------------------------------------------
#
# THE OWNER'S ASK, and the half that was missing. He asked for the General
# preset to be "the default that loads anytime jarvis is reset", and to be able
# to "set the default presets that load when atlas is restarted through chat or
# settings". The preset table needed nothing: General already exists, it is the
# 26B model on the pooled three-card lane - larger than the everyday 9B - and
# `apply_preset` already starts that lane, switches the model and persists the
# lane. What was missing is a SETTING that survives the restart and a start-up
# step that reads it:
#
#   * the reconcile ABOVE is the opposite case. When the remembered preset's
#     on-demand lane is gone after a restart, it points chat back at the default
#     lane and DELETES `presets-choice.json`, because a choice nobody can serve
#     is a lie. That is right for a choice made by clicking; it must not be how
#     a choice the owner made on purpose is treated, so this setting lives in
#     its own file and the start-up step applies it BEFORE any reconcile runs.
#   * THE APPLY IS THE ROUTE'S OWN ROAD, not a second implementation:
#     `_apply_body({"preset": pid}, owner_ui=True)` is exactly what
#     `POST /api/work/apply` runs, so the lane starts, the model switches, the
#     lane is persisted and the chosen preset is written by the one code path
#     that already does all four. `owner_ui=True` means what it means on that
#     route - the owner's own act - so a start-up load raises no second card:
#     the ONE `change_own_config` card that saved this setting was the yes for
#     it. (The apply still writes its Undo receipt, so a start-up load is
#     reversible like any other owner-clicked apply.)
#   * the owner accepted a slow start (~a minute, ~15 GiB of card memory), but
#     not a late one: `_start_startup_check` runs this in ONE daemon thread, so
#     a 26B cold load never delays the HUD's first request. The outcome lands in
#     `_LAST_RECONCILE`, which `/api/work` already reports as
#     `restart_reconcile`, so a load that failed is never silent.
#   * THE LOAD ASKS TO STAY RESIDENT (`keep_alive: -1`), through the SAME loader
#     the route uses, because an eager preload the idle timer throws away five
#     minutes later is pointless. The pooled lane's own server already runs with
#     `OLLAMA_KEEP_ALIVE=-1` (`jarvis_big_coder._child_env`), so this matters most
#     where that guarantee does not reach: a lane that reuses a server THIS
#     program did not start. It is bounded by two existing rules - one preset's
#     model at a time (a later apply ends the lane first) and the owner's rest
#     hours (`_startup_keep_alive`).
#   * with NO start-up preset this module does exactly what it did before: the
#     reconcile runs, once, synchronously, and every existing sentence is
#     unchanged.

#: The approval action every setting change in this program uses. Reused, never
#: a new row: a start-up preset is a config change like the cloud switch, and
#: `change_own_config` is already `ask`.
STARTUP_ACTION = CLOUD_ACTION


def _startup_doc() -> tuple:
    """(the preset id to load at start, why there is none). Reads only.

    The `why` is "" when there is nothing to explain: no file is "nothing has
    been set", and a valid id is "it is set". It is a plain sentence when the
    file cannot be read or names a preset this PC does not have - the case where
    a saved setting silently stops working, which is exactly what must be said
    rather than hidden.
    """
    import json
    try:
        text = _startup_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", ""
    except Exception:
        return "", ("the start-up preset file on this PC cannot be read, so no "
                    "preset is loaded at start")
    try:
        doc = json.loads(text)
    except Exception:
        return "", ("the start-up preset file on this PC is not readable JSON, so "
                    "no preset is loaded at start")
    if not isinstance(doc, dict):
        return "", ("the start-up preset file on this PC does not hold a setting, "
                    "so no preset is loaded at start")
    raw = str(doc.get("preset") or "").strip()
    if not raw:
        return "", ""
    if by_id(raw) is None:
        return "", (f"this PC has no preset called {raw!r}, so no preset is loaded "
                    f"at start")
    return raw, ""


def startup_preset() -> str:
    """The preset id the owner marked to load every time Atlas starts, or "".

    Never raises, and never guesses: an unreadable file or an id this PC does
    not know is "" - nothing is loaded - and `startup_why()` says which.
    """
    return _startup_doc()[0]


def startup_why() -> str:
    """The plain reason nothing is loaded at start, or "" when all is well."""
    return _startup_doc()[1]


def startup_view() -> dict:
    """The `/api/work` answer's small `startup_preset` block. Read-only."""
    preset, why = _startup_doc()
    return {"preset": preset, "why": why}


def _write_startup_preset(preset_id: str) -> bool:
    """Save the one start-up preset, or remove the setting when it is "".

    Atomic (write beside, replace), and False - with nothing changed - on any
    error. The empty case removes the FILE rather than writing `{"preset": ""}`:
    absent is the shape every other setting file in this folder treats as "not
    set", and a reader must be able to tell the two apart by `exists()`.
    """
    import json
    try:
        if not str(preset_id or "").strip():
            try:
                _startup_path().unlink()
            except FileNotFoundError:
                pass
            return True
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _startup_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"preset": str(preset_id)}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(_startup_path())
        return True
    except Exception:
        return False


def _startup_card_text(p) -> str:
    """The ONE card setting this, in the owner's own words.

    It has to say what will happen at the NEXT start, because that is the thing
    being agreed to and it is invisible at the moment of the click: a model he
    chose will be loaded before he asks anything, and it will cost the time and
    the card memory the preset's own row measures. `heavy_words` is the preset
    table's measured sentence, quoted rather than re-typed.
    """
    cost = (p.heavy_words
            or f"It loads on {p.lane_info['card']} ({p.lane_info['words']}).")
    return (f"Load the {p.title} preset ({p.model}) every time Atlas starts, "
            f"before you ask it anything. {cost} Chat is not ready until it has "
            f"finished loading. Nothing on this PC changes until you say yes.")


def set_startup_preset(*, preset, gate_check=None) -> tuple:
    """Mark ONE preset to load at every start (ONE card), or clear it (at once).

    ORDER, the same contract `cloud_escalate` keeps: refuse an id that is not a
    local preset (400, BEFORE any card - a card for something that cannot work
    would be a lie) -> refuse a preset whose model this PC does not have yet
    (409, also before a card) -> do nothing and raise no second card when it is
    already the setting -> raise ONE `change_own_config` card -> only after that
    yes, write `startup-preset.json`.

    CLEARING IS A TIGHTENING and is instant, the asymmetry every switch here
    keeps: it makes Atlas load nothing at start. Setting it asks because it is a
    standing change to what the program does on its own, every time it starts.

    Returns (http status, body); `card` says whether one was raised, so a client
    can say "waiting for your click" instead of guessing.
    """
    pid = str(preset or "").strip()
    if not pid:
        had = bool(_startup_doc()[0])
        if not _write_startup_preset(""):
            return 503, {"ok": False, "changed": False, "card": False,
                         "error": ("the start-up preset could not be cleared on "
                                   "this PC; nothing was changed"),
                         "startup_preset": startup_view()}
        return 200, {"ok": True, "changed": had, "card": False,
                     "startup_preset": startup_view(),
                     "message": ("No preset will be loaded when Atlas starts."
                                 if had else
                                 "No preset was set to load when Atlas starts.")}
    if pid == CLOUD_PRESET_ID:
        return 400, {"ok": False, "changed": False, "card": False,
                     "error": ("the Cloud row is not a local preset, so there is no "
                               "model on this PC for Atlas to load at start"),
                     "startup_preset": startup_view()}
    p = by_id(pid)
    if p is None:
        return 400, {"ok": False, "changed": False, "card": False,
                     "error": (f"there is no preset called {pid!r}; the presets are "
                               f"{', '.join(PRESET_IDS)}"),
                     "startup_preset": startup_view()}
    if p.pending:
        return 409, {"ok": False, "changed": False, "card": False,
                     "error": (f"the {p.title} preset has no model on this PC yet, so "
                               f"it cannot be loaded when Atlas starts"),
                     "startup_preset": startup_view()}
    if _startup_doc()[0] == pid:
        return 200, {"ok": True, "changed": False, "card": False,
                     "startup_preset": startup_view(),
                     "message": (f"{p.title} is already the preset Atlas loads when "
                                 f"it starts.")}
    words = _startup_card_text(p)
    verdict = (gate_check or _gate)(
        STARTUP_ACTION, {"text": words},
        f"load the {p.title} preset every time Atlas starts")
    if not getattr(verdict, "allowed", False):
        return 200, {"ok": False, "changed": False, "card": True,
                     "outcome": str(getattr(verdict, "outcome", "refused")),
                     "message": ("Not changed - Atlas still starts with no preset "
                                 "loading."),
                     "startup_preset": startup_view()}
    if not _write_startup_preset(pid):
        return 503, {"ok": False, "changed": False, "card": True,
                     "error": ("the start-up preset could not be saved on this PC; "
                               "nothing was changed"),
                     "startup_preset": startup_view()}
    return 200, {"ok": True, "changed": True, "card": True,
                 "startup_preset": startup_view(),
                 "message": (f"Atlas will load the {p.title} preset ({p.model}) every "
                             f"time it starts, before you ask it anything. Nothing "
                             f"on this PC changes until the next start.")}


def startup_from_body(body) -> tuple:
    """`POST /api/work/startup-preset {"preset": "<id>"}` -> set_startup_preset.

    `{"preset": ""}` and `{"clear": true}` both clear it. The body is checked
    exactly, the same way the cloud switch's is: there is no truthiness shortcut
    on a setting that changes what the program does on its own.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "expected a JSON object"}
    if "clear" in body:
        if not isinstance(body.get("clear"), bool):
            return 400, {"ok": False, "error": '"clear" must be true or false'}
        if body["clear"]:
            return set_startup_preset(preset="")
    if "preset" not in body:
        return 400, {"ok": False,
                     "error": 'expected {"preset": "<id>"}, {"preset": ""} or '
                              '{"clear": true}'}
    if not isinstance(body.get("preset"), str):
        return 400, {"ok": False, "error": '"preset" must be text'}
    return set_startup_preset(preset=body["preset"])


#: Ollama's documented "keep it resident until something else evicts it"
#: (`keep_alive: -1`). THE START-UP PRESET ASKS FOR IT (2026-11-22, measured on
#: this PC: the General model was applied at 02:41 and Ollama's default idle
#: timer had unloaded it by 10:30 - `/api/ps` on 11450 reported no model while
#: `/api/work` still said `chosen: "general"`). An eager start-up load the idle
#: timer throws away five minutes later is pointless, so the load asks to stay.
#: WHAT BOUNDS IT, and both are rules this program already keeps: only ONE
#: preset's model is resident at a time, so applying any other preset ends this
#: lane first (`stop_pooled`, `_default_stop_pooled`), and the owner's own rest
#: hours are respected at start-up (see `_startup_keep_alive`).
STARTUP_KEEP_ALIVE = -1


def _startup_keep_alive() -> tuple:
    """(the keep_alive the start-up load may ask for, why it is not -1).

    `(STARTUP_KEEP_ALIVE, "")` when nothing tells the model to go. `(None, why)`
    when the owner's own rest hours are active right now, or cannot be read: the
    model is then loaded by the ordinary road with Ollama's own idle rule, and
    the reason travels in the record.

    THE SETTING IS THE ONE THE PRODUCT HAS: `[power]`'s scheduled window
    (`schedule_enabled`, `quiet_start`, `quiet_end`, `schedule_mode`), read by
    `jarvis_power.schedule_drop()` - the same reader the power rules use, so
    there is no second copy of the clock arithmetic. There is NO `[energy]`
    rest-hours setting: that section is the measured-watts record
    (`jarvis_energy.py`), so nothing here invents one.
    """
    try:
        import jarvis_power as _power
    except Exception:
        return STARTUP_KEEP_ALIVE, ""     # no rest-hours module: nothing to respect
    try:
        drop = _power.schedule_drop()
    except Exception as exc:              # noqa: BLE001 - said, never swallowed
        return None, (f"the rest hours could not be read "
                      f"({type(exc).__name__}), so the model was loaded with "
                      f"Ollama's own idle rule instead of being held resident")
    if drop:
        return None, (f"your rest hours are on now ({drop}), so the model was "
                      f"loaded with Ollama's own idle rule instead of being held "
                      f"resident")
    return STARTUP_KEEP_ALIVE, ""


def apply_startup_preset(*, apply=None, reconcile=None) -> dict:
    """The ONE start-up step: load the marked preset, or repair what it left.

    Called by `install()` in the real HUD process. Returns the dict that becomes
    `/api/work`'s `restart_reconcile` block: `{"changed", "why", "lane",
    "preset"}` and, for this feature, `startup_applied`, `startup_preset` and
    `keep_alive`.

    THREE OUTCOMES, and none is silent:

      * NO start-up preset: today's behaviour, byte for byte - the restart
        reconcile runs and its own dict is returned untouched, so every existing
        sentence and every existing test is unchanged;
      * the preset LOADS: the apply is the route's own road
        (`_apply_body(..., owner_ui=True)`), which starts the lane, switches the
        model, points chat at the lane and saves the chosen preset. No reconcile
        runs, so the owner's choice is never deleted by the step that just
        served it. The load asks to STAY RESIDENT (`keep_alive: -1`) unless the
        owner's own rest hours are active or unreadable, in which case the record
        says why it did not;
      * the preset CANNOT load: the failure is said, and THEN today's reconcile
        runs - chat is pointed back at the default lane and the unservable
        choice is forgotten, exactly as it is today - with both sentences kept
        in `why`. A start that cannot do what the owner set says so; it never
        leaves a stale choice and no word about it.
    """
    import os as _os
    if _os.environ.get("JARVIS_SUITE_RUNNING") and not _os.environ.get(
            "OPENJARVIS_CONFIG_DIR"):
        # The same refusal `reconcile_after_restart` makes, for the same reason
        # (2026-11-08): a suite with no temp config folder must never read, let
        # alone act on, the owner's live setting.
        return {"changed": False, "lane": "", "preset": "",
                "why": ("refused: a suite run must point OPENJARVIS_CONFIG_DIR at "
                        "its own temp folder; nothing was touched")}
    pid = startup_preset()
    if not pid:
        got = (reconcile or reconcile_after_restart)()
        return got if isinstance(got, dict) else {
            "changed": False, "lane": "", "preset": "", "why": ""}
    keep_alive, hold_why = _startup_keep_alive()

    def _apply(want):
        return _apply_body({"preset": want}, owner_ui=True,
                           keep_alive=keep_alive)

    apply = apply or _apply
    try:
        code, body = apply(pid)
    except Exception as exc:                     # noqa: BLE001 - said, never swallowed
        code, body = 503, {"ok": False,
                           "error": f"{type(exc).__name__}: {exc}"}
    body = body if isinstance(body, dict) else {}
    if code in (200, 202) and body.get("ok") is True and not body.get("error"):
        p = by_id(pid)
        title = p.title if p is not None else pid
        lane = str(body.get("base_url") or "")
        return {"changed": True,
                "why": (f"loaded the {title} preset at start, as you set it"
                        + (f" on {lane}" if lane else "")
                        + ("; it stays resident until another preset or your "
                           "rest hours replace it" if keep_alive is not None
                           else "; " + hold_why)
                        + "; it is the preset chat uses now"),
                "lane": lane, "preset": pid, "startup_preset": pid,
                "startup_applied": True, "keep_alive": keep_alive,
                "held_resident": keep_alive is not None,
                "model": str(body.get("model") or "")}
    why = str(body.get("error") or body.get("reason")
              or body.get("message") or "").strip()
    if not why:
        why = f"the apply answered {code} and agreed to nothing"
    try:
        got = (reconcile or reconcile_after_restart)()
    except Exception as exc:                     # noqa: BLE001 - said, never swallowed
        got = {"changed": False, "lane": "", "preset": "",
               "why": f"{type(exc).__name__}: the restart check failed"}
    got = dict(got) if isinstance(got, dict) else {}
    tail = str(got.get("why") or "")
    merged = dict(got)
    merged.update({
        "startup_preset": pid, "startup_applied": False,
        "keep_alive": keep_alive,
        # `preset` is the preset THIS feature was asked to load; the reconcile's
        # own answer about the remembered choice keeps its own key, so a reader
        # can tell the two apart.
        "preset": pid,
        "remembered_preset": str(got.get("preset") or ""),
        "startup_error": why,
        "why": (f"the start-up preset ({pid}) could not be loaded: {why}."
                + (f" {tail}" if tail else
                   " Nothing else on this PC was changed by it.")),
    })
    return merged


#: Set once this process has started its start-up check, so a second `install()`
#: in the same process (the suites call it several times) cannot start a second
#: 26B load.
_STARTUP_CHECK_STARTED = False


def _startup_check_in_background() -> None:
    """Run `apply_startup_preset()` off the serving path and record its outcome.

    The ONE writer of `_LAST_RECONCILE` on this road: `/api/work` reports it as
    `restart_reconcile`, so the answer to "did the start-up preset load?" is a
    read of the normal payload rather than a line in a log nobody opens.
    """
    global _LAST_RECONCILE
    try:
        got = apply_startup_preset()
    except Exception as exc:                     # noqa: BLE001 - never blocks start-up
        got = {"changed": False, "lane": "", "preset": "",
               "why": f"{type(exc).__name__}: the start-up check failed"}
    _LAST_RECONCILE = dict(got) if isinstance(got, dict) else {
        "changed": False, "lane": "", "preset": "",
        "why": "the start-up check answered nothing"}
    try:
        if _LAST_RECONCILE.get("changed"):
            print("  presets    " + str(_LAST_RECONCILE.get("why") or ""))
    except Exception:                            # noqa: BLE001 - printing is not start-up
        pass


def _start_startup_check() -> bool:
    """Start THE start-up thread once. True when it is running (or was).

    A 26B cold load measured about 50 s on this PC (`GEMMA4_26B_MEASURED_WORDS`),
    and the HUD must serve its first request during it - so this work is on its
    own daemon thread and never on `install()`'s. False means the thread could
    not be created, which the caller records rather than hides.
    """
    global _STARTUP_CHECK_STARTED
    if _STARTUP_CHECK_STARTED:
        return True
    thread = threading.Thread(target=_startup_check_in_background,
                              name="jarvis-presets-startup", daemon=True)
    try:
        thread.start()
    except Exception:
        _STARTUP_CHECK_STARTED = False
        return False
    _STARTUP_CHECK_STARTED = True
    return True


def _chat_lane_url() -> str:
    """The lane a chat turn uses: the applied preset's own lane, else the default.

    THE DEFECT THIS FIXES (measured on the owner's phone, 2026-11-21 ~20:24 PT).
    `_active_lane_key()` and the `lane`/`active_lane` blocks read `_active_url()`,
    which is the DEFAULT lane (`OLLAMA_URL`, port 11436 on this PC) - so while
    the General preset was APPLIED and `presets-active-lane.json` pointed every
    chat turn at the pooled lane (11450, its model resident), the contract still
    reported the default lane. The phone compares the chosen preset's lane with
    the reported one, so it drew "General - Chosen - not running now" over a
    lane that was really running.

    The applied lane is exactly what `jarvis_hud.active_ollama_url()` hands a
    chat turn, and it is persisted in the loopback-only file
    `_persisted_lane_url()` already reads. `_active_url()` itself is NOT
    changed: `reconcile_after_restart()` needs the default lane to point chat
    back at it. This is the contract's read only - it starts nothing, pauses
    nothing, writes nothing, and never raises.
    """
    return _persisted_lane_url() or _active_url()


def _active_lane_key(url: str = "") -> Optional[str]:
    """The `LANES` key of the lane chat is on, or None when it is no preset lane.

    `url` defaults to the applied-or-default lane (`_chat_lane_url()`); it is a
    parameter so `live_status()` can pass the one reading it already took. The
    port compare (not a string compare) accepts the same loopback spellings the
    lane file accepts: `localhost` and `::1` name this PC too.
    """
    port = _port_of_url(url or _chat_lane_url())
    for key, lane in LANES.items():
        if port == int(lane["port"]):
            return key
    return None


def live_status() -> dict:
    """GET /api/work's and GET /api/presets' answer: the ten local presets,
    the Cloud row, the cloud provider list and the PC's own escalation switch,
    the detected cards, the questionnaire, the 1/2/3-GPU recommendations, the
    chosen preset and the active lane.

    Reads only, and never switches a model, starts a lane or writes a file -
    the two things it DOES read from the owner's PC are which cloud keys are
    saved (presence only) and this month's spend, both for `cloud`.

    The `lane` block and `active_lane` report the APPLIED preset's lane when one
    is persisted (`presets-active-lane.json`, the same file a chat turn is
    pointed by), falling back to the default lane only when no applied lane
    exists - the reading that makes the phone's chosen/running compare true.
    """
    chosen = choice()
    chosen_preset = by_id(chosen) if chosen else None
    hw = hardware_block()
    applied_lane = _persisted_lane_url()
    lane_url = applied_lane or _active_url()
    lane_key = _active_lane_key(lane_url)
    lane_info = LANES.get(lane_key) if lane_key else None
    lane_label = ""
    if lane_info:
        lane_label = f"{lane_info['card']} · {lane_info['words']}"
    lane = {
        "key": lane_key,
        "base_url": lane_url,
        "card": lane_info["card"] if lane_info else "",
        "words": lane_info["words"] if lane_info else "",
        "label": lane_label,
        "ready": lane_info is not None,
        # Never a guess: with no applied lane this is today's sentence, and with
        # an applied lane that names no preset port it says the address is not
        # one of the presets' lanes instead of pretending nothing was applied.
        "why": "" if lane_info else (
            "the applied preset's lane is not one of the presets' lanes"
            if applied_lane else "no preset has been applied on this PC yet"),
    }
    return {
        "found": f"{len(PRESETS)} focus presets",
        "presets": [p.view() for p in PRESETS],
        # The Cloud row: an ELEVENTH row in the same shape (ten presets + this
        # one), deliberately not in `presets` - both apps' ten-row list stays
        # ten rows (the owner's decision of 2026-10-27: additive keys only, so
        # the phone needs no change at all to keep working).
        "cloud_preset": cloud_preset_view(),
        # The provider in use, the services to choose from, and the PC's own
        # standing escalation switch. See cloud_view().
        "cloud": cloud_view(),
        "old_ids_replaced": list(OLD_IDS),
        # The exact shape the generated contract fixture has (and the one the
        # desktop/Android readers expect): hardware.detected + hardware.questionnaire.
        "hardware": hw,
        "recommendations": recommendations(),
        "chosen": chosen,
        "chosen_preset": chosen,
        "chosen_model": chosen_preset.model if chosen_preset else None,
        "active_lane": {"key": lane_key, "base_url": lane_url},
        # What the startup reconcile did after the last restart (2026-11-08).
        # A read: it changes nothing and is empty on a PC with no pooled preset.
        "restart_reconcile": dict(_LAST_RECONCILE),
        # The preset marked to load at every start (2026-11-22), and the plain
        # reason there is none when one is saved and cannot be used. Read-only:
        # this block changes nothing, starts nothing and raises no card. A PC
        # that never set one reads `{"preset": "", "why": ""}`.
        "startup_preset": startup_view(),
        "lane": lane,
        "lane_status": lane,
        "apply_path": APPLY_PATH,
        "switch_path": SWITCH_ROUTE,
        "auto": False,
        "not_a_catalogue": ("This lists the presets that exist; it is not a download "
                            "catalogue. A pending preset waits for its model."),
    }


# --------------------------------------------------------------------------
#   A preset clicked in an app: the owner's own act (2026-11-09, widened 2026-11-16)
# --------------------------------------------------------------------------
#
# THE OWNER'S ASK, 2026-11-09: *"if i manually click and change the preset for
# jarvis, it shouldnt need a card"* and *"if i manually choose anything in the
# jarvis app or deskstop program, and its something that i can easily click and
# change back right away, it shouldnt need a card"*. He said it again on
# 2026-11-16, about the one row this road still carded: *"when i change the
# model on the jarvis app it still sends me an approval card. that shouldnt
# happen if i manually press the preset change. only if i ask through chat"*.
#
# WHAT CHANGES. A local preset is applied AT ONCE when the request came through
# `POST /api/work/apply` - the route only the two apps' own preset controls
# call, after the server's origin and pairing-token checks. SINCE 2026-11-16
# that includes the heavy presets (Coding and Medical): their pooled lane raises
# ONE `switch_model` card on the carded road, and on this road it is started with
# the press itself as the approval (`_start_lane_for_the_owner`,
# `_OwnerPressed`). The preset it replaced goes into a receipt
# (jarvis_receipts); clicking another preset in the same menu switches straight
# back, and Undo is offered on the receipt for every local preset.
#
# THE MODEL PATH KEEPS ITS CARD, and nothing here is a flag a caller can put in
# a request. The private `_apply_body(..., owner_ui=True)` is called from ONE
# place, this module's own route wrapper (`install()`), and the request body is
# never read for it. Everything else - `jarvis_model_knowledge.apply_preset`
# (the spoken "use the X preset" command), `jarvis_settings_registry.
# set_focus_preset` ("set the focus preset to X") and every direct Python
# caller - goes through the public `apply_from_body`, which is still the carded
# road: `jarvis_models.switch_to` (tier "ask", `switch_model`) on a named lane,
# and the pooled lane's own `switch_model` card for a heavy one.
#
# WHY THE ROUTE IS ENOUGH TO KNOW IT WAS A SCREEN. The model never posts to its
# own HTTP routes: a chat tool call reaches this module in-process. The route
# already demands the server's origin check and the pairing token
# (`presets.patch` passes `_origin_ok`/`_token_ok` in), so a request that gets
# this far came from a paired app. No tier is loosened and no header is
# trusted: the tier table still says `switch_model = "ask"`, and the model path
# still reads it.
#
# THE REVERSIBLE BOUNDARY, and what stays carded:
#   * a local preset clicked in an app -> no card, heavy or not. One click back
#     in the same menu, nothing is downloaded, nothing is deleted, nothing is
#     spent. A heavy one pauses both lane models while its own model loads; the
#     click back is applying another preset, which brings them back - and the
#     card that used to ask *this exact question* is why the owner's press
#     answers it instead of asking it a second time.
#   * the SAME preset asked for in chat or by voice -> STILL a card, both kinds:
#     `jarvis_models.switch_to` on a named lane, and the pooled lane's own
#     `switch_model` card for Coding or Medical.
#   * Cloud -> STILL a card. It chooses where the owner's words go
#     (`apply_cloud`, `change_own_config`).
#   * installs and downloads -> untouched; still `ask`.

#: The receipt name for one preset clicked in an app, so Undo knows how to put
#: the model, the lane and the chosen preset back (jarvis_receipts.py). It is
#: registered at import, the same way jarvis_antislop.py's own receipts are.
OWNER_RECEIPT_TOOL = "preset_apply"


def _current_model() -> str:
    """The model steward's current model, or "" when it cannot be read."""
    try:
        import jarvis_models as M
        return str(M.current_model() or "")
    except Exception:
        return ""


def _restorable_preset(preset_id) -> bool:
    """Can this preset be put back by the same uncarded app click?

    Every LOCAL preset can, the heavy rows included since 2026-11-16: a heavy
    preset clicked in an app is the owner's own click too, so the same click (or
    this receipt's Undo) puts it back with no card. Cloud cannot: it raises
    `change_own_config` on every road, and an Undo that raised a SECOND card
    would be a different action wearing Undo's name. A pending preset has no
    model yet, and an unknown id (a hand-edited file) is not restorable either;
    the receipt is still written.
    """
    if not preset_id:
        return True                      # "no preset was chosen": restorable by hand
    p = by_id(preset_id)
    return bool(p is not None and not p.pending)


def _owner_before(previous_preset, previous_lane) -> Optional[dict]:
    """The before snapshot a receipt keeps, or None when it cannot be undone."""
    if not _restorable_preset(previous_preset):
        return None
    return {"preset": previous_preset or None,
            "model": _current_model(),
            "lane": str(previous_lane or "")}


def restore_from_before(before) -> None:
    """Put the model, the chat lane and the chosen preset back from a receipt.

    This is BOTH the live Undo callable and the snapshot path jarvis_receipts
    uses after a restart. It takes the same uncarded owner path a click takes,
    because the Undo itself was already decided by the receipt's own card.
    Raises on a snapshot it cannot use or a restore that will not happen;
    jarvis_receipts turns that into plain words and changes nothing else.
    """
    if not isinstance(before, dict):
        raise ValueError("this is not a preset receipt snapshot")
    preset_id = str(before.get("preset") or "")
    if preset_id:
        code, out = apply_preset(preset_id, owner_ui=True)
        out = out if isinstance(out, dict) else {}
        if code >= 400 or not out.get("ok"):
            raise RuntimeError(str(out.get("error") or
                                   "the preset could not be put back"))
        return
    model = str(before.get("model") or "")
    if model:
        got = _switch_for_the_owner(model)
        if not got.get("ok"):
            raise RuntimeError(str(got.get("reason") or
                                   "the model could not be put back"))
    lane = str(before.get("lane") or "")
    if lane and not _set_active_url(lane):
        raise RuntimeError("the chat lane could not be put back")
    try:
        _choice_path().unlink()
    except FileNotFoundError:
        pass


def _register_receipt() -> bool:
    """Tell jarvis_receipts.py how a preset click is put back. Never raises."""
    try:
        import jarvis_receipts
        return bool(jarvis_receipts.register_restorer(
            OWNER_RECEIPT_TOOL, restore_from_before))
    except Exception:
        return False


_register_receipt()


def _record_owner_preset(previous_preset, previous_lane, preset) -> str:
    """One receipt for a preset changed by an app click, or "". Never raises.

    Written BEFORE the switch (jarvis_receipts' own rule), so it exists even if
    the switch then fails - `_discard_owner_receipt` removes it in that case.
    Undo is pointed at the before snapshot only when the preset it replaced is
    itself restorable (`_owner_before`): every local preset is, heavy or not,
    since 2026-11-16 - the same uncarded click puts it back. Going back to Cloud
    raises its own card, so the menu row is that way back, not Undo. The receipt
    is written either way, so the change is always visible.
    """
    try:
        import jarvis_receipts
    except Exception:
        return ""
    before = _owner_before(previous_preset, previous_lane)
    if previous_preset:
        was = by_id(previous_preset)
        was_words = was.title if was is not None else str(previous_preset)
        summary = f"Preset: {preset.title}. Before it: {was_words}."
    else:
        summary = f"Preset: {preset.title}. No preset was chosen before."
    after = {"preset": preset.id, "model": preset.model, "lane": preset.lane}
    undo = (lambda: restore_from_before(before)) if before is not None else None
    try:
        return jarvis_receipts.record(OWNER_RECEIPT_TOOL, summary,
                                      before=before, after=after, undo=undo)
    except Exception:
        return ""


def _discard_owner_receipt(receipt_id: str) -> None:
    """Remove a receipt whose change did not happen. Never raises."""
    if not receipt_id:
        return
    try:
        import jarvis_receipts
        jarvis_receipts.discard(receipt_id)
    except Exception:
        pass


def _switch_for_the_owner(ref: str, why: str = "a preset clicked in an app") -> dict:
    """Make `ref` the local lane's model with NO card - the owner's own click.

    The same model record `jarvis_models.switch_to` writes, and the same
    tripwire smoke test it runs afterwards, minus the gate: the request came
    from a paired app's own preset control (see this section's comment), and
    the way back is the same menu. The model must already be installed -
    nothing here downloads, and an install stays carded.

    A missing model steward, an uninstalled model or a state file that will not
    write answers `{"ok": False, "reason": ...}`; nothing is claimed that was
    not seen. A tripwire that is not on this PC is reported as unavailable and
    does not undo the switch.
    """
    try:
        import jarvis_models as M
    except Exception as exc:
        return {"ok": False, "ref": str(ref),
                "reason": f"the model steward is not available ({type(exc).__name__})"}
    try:
        ref = M.safe_ref(ref)
    except ValueError as exc:
        return {"ok": False, "ref": str(ref), "reason": str(exc)}
    try:
        if not M.is_installed(ref):
            return {"ok": False, "ref": ref,
                    "reason": "not installed on this machine; download it first"}
        st = M._read_state()
    except Exception as exc:
        return {"ok": False, "ref": ref,
                "reason": f"the model state could not be read ({type(exc).__name__})"}
    cur = st.get("current")
    if cur == ref:
        return {"ok": True, "ref": ref, "unchanged": True,
                "reason": "already the current model"}
    # The outgoing model's answers, before it stops being the one in use - the
    # same reason `switch_to` records this baseline first. TWO THINGS CAN MAKE
    # THAT REQUEST UNSAFE, and `probe_refusal` checks both before anything is
    # sent (DEF-088, the A2 field test of 2026-11-17):
    #
    #   * the outgoing model may be a POOLED (three-card) model. After a heavy
    #     preset that is exactly what the record says, and `_probe_asker` talks
    #     to `jarvis_models.OLLAMA` - the everyday lane, ONE 12 GB card. Asking
    #     it for a 14.44 GB model is the duplicate copy the owner photographed
    #     (74% on the card / 26% on the CPU): a `general` apply then reported
    #     success while port 11436 served the coder at 8,192 tokens and the
    #     record said `qwen3.5:9b`.
    #   * the lane's window may be unknown. A probe that names no `num_ctx`
    #     loads at Ollama's own default (8,192 here) and throws away the window
    #     the lane was configured for (32,768 for General on 11436), so it is not
    #     sent.
    #
    # SKIPPING is chosen over "probe it on the pooled lane's own address",
    # deliberately. By the time this runs on the app-click road, `apply_preset`
    # has already STOPPED that server, so there is nothing there to ask and
    # nothing left to compare against; and a probe aimed at the pooled address
    # would still load a stale name there, while a skip cannot load the wrong
    # model on the wrong card even when the pooled lane is DOWN. The skip is
    # reported below, so the app shows a reason instead of a smoke test of
    # nothing.
    probe = None
    baseline_skip = ""
    try:
        baseline_skip = (M.probe_refusal(cur) if cur
                         else "there was no previous model to record")
        if not baseline_skip:
            import jarvis_tripwire
            probe = M._probe_asker(cur)
            jarvis_tripwire.baseline(probe, cur)
    except Exception:
        probe = None
    now = time.time()
    st["previous"] = cur
    st["current"] = ref
    st["switched_at"] = now
    st["why"] = str(why or "a preset clicked in an app")[:300]
    log = list(st.get("switches") or [])
    log.append({"from": cur, "to": ref, "at": now})
    st["switches"] = log[-int(getattr(M, "MAX_HISTORY", 20) or 20):]
    try:
        wrote = bool(M._write_state(st))
    except Exception:
        wrote = False
    if not wrote:
        return {"ok": False, "ref": ref,
                "reason": "could not write the model state file; nothing changed"}
    out = {"ok": True, "ref": ref, "previous": cur, "no_card": True,
           "revert_with": "the model's own rollback",
           "reason": f"local lane now uses {ref}"}
    # The smoke test asks the model that was just switched IN - never the one it
    # replaced (DEF-088). `probe or M._probe_asker(ref)` read like a fallback,
    # but `probe` is a function and therefore always truthy, so the "after"
    # screen answered about the OLD model and filed the result under the new
    # model's name. `baseline_skip` is deliberately NOT reused here: that
    # sentence was about the outgoing model, and a pooled outgoing model says
    # nothing about whether `ref` may run on this lane.
    after_skip = M.probe_refusal(ref)
    if after_skip:
        out["tripwire"] = {"available": False, "model": ref,
                           "reason": after_skip}
    else:
        try:
            import jarvis_tripwire
            out["tripwire"] = jarvis_tripwire.after_swap(
                M._probe_asker(ref), ref)
        except Exception as exc:
            out["tripwire"] = {"available": False, "reason": str(exc)}
    return out


class _OwnerPressed:
    """The verdict a heavy preset's pooled lane gets from the owner's own click.

    WHY NO CARD HERE. `jarvis_model_lanes.start_pooled_lane` normally raises ONE
    `switch_model` card before it unloads anything, because it pauses both of the
    owner's lane models for about half a minute. But the owner pressed this
    preset in one of the two apps' own preset controls, and on 2026-11-16 he
    ruled that press to be his own click: *"when i change the model on the
    jarvis app it still sends me an approval card. that shouldnt happen if i
    manually press the preset change. only if i ask through chat"*. So the press
    IS the approval, in the shape a card's verdict has (`allowed`, `outcome`,
    `reason`) - the same fields every caller of the gate reads.

    NOTHING IS LOOSENED: the tier table still says `switch_model = "ask"`, the
    chat and voice roads still raise that card inside the lane, and the only
    route that can reach this verdict is `install()`'s POST wrapper, after its
    origin and token checks. The card was not skipped - it was answered by the
    act it exists to obtain.
    """

    allowed = True
    outcome = "approved"
    reason = "the owner pressed this preset in one of the apps"


def _start_lane_for_the_owner(key: str, mode: str = "", keep_alive=None):
    """Start the preset's lane with NO card - the owner's own click. `(status, body)`.

    The same start `_default_start_lane` performs, with the same `mode`, and the
    same `(status, body)` answer. The ONE difference is the card: a heavy
    preset's pooled lane normally raises its own `switch_model` card before it
    unloads anything, and on this road it gets `_OwnerPressed` instead - the
    press the app's preset control just recorded. The presets on a named lane
    raise no card on either road, so they are started exactly as before, through
    `_lane_starter` (every injected one-argument seam still works).

    `keep_alive` is forwarded only when the start-up path names one (2026-11-22,
    `-1`): the start-up load takes this same road - the owner set it on purpose,
    so it is his own press - and the option reaches the lane's own loader.

    NOTHING HERE DOWNLOADS and nothing here picks a model: a heavy preset's
    model is loaded by the lane and recorded afterwards by `_default_adopt`, on
    this road too - `_switch_for_the_owner` is NOT used for it, because its
    smoke test runs against the one-card everyday lane (see `_default_adopt`).
    A lane that will not start answers the same plain words a carded start does
    ("the three-card Ollama could not be started"), and the apply then rolls
    back and says what it could not restore; a refused card cannot happen here,
    because the press already said yes.
    """
    import jarvis_model_lanes
    if str(key) == jarvis_model_lanes.POOLED_KEY:
        if keep_alive is None:
            return jarvis_model_lanes.start_pooled_lane(
                gate=lambda *a, **k: _OwnerPressed(),
                mode=str(mode or "coding"))
        return jarvis_model_lanes.start_pooled_lane(
            gate=lambda *a, **k: _OwnerPressed(),
            mode=str(mode or "coding"), keep_alive=keep_alive)
    return _lane_starter(key, mode)


def switch_model_for_the_owner(ref: str, why: str = "") -> dict:
    """The uncarded model switch, by the public name `jarvis_reversible_ui` uses.

    Called by `jarvis_reversible_ui.install()` for a model picked in either
    app's own model list - the manual-click rule (Gemini Q2, 2026-11-09). It is
    the same body a preset click uses, so the two owner clicks share ONE
    implementation and one model record; the `why` is the only difference.
    Every model/chat path still reaches `jarvis_models.switch_to`, which asks.
    """
    return _switch_for_the_owner(ref, why=why or "a model picked in an app")


def _lane_not_checked(url: str, model: str, min_ctx=None,
                      allow_spill: int = 0) -> dict:
    """The answer a TEST SUITE gets when it did not inject a lane reader.

    `ok` stays True so an apply that is being driven for some other purpose is
    not turned into a failure by a decision it never made, and `checked` is
    False so nothing can read that line as a lane that was verified. A suite
    that wants to prove the reader passes `verify_lane=_default_verify_lane`
    itself, with a fake lane of its own (backend/test_preset_switch_lane_guard.py).
    """
    return {"ok": True, "checked": False, "loaded": [], "why": "",
            "proof": ("not checked: this process is a test suite, so the lane was "
                      "not read - this is NOT a pass for the lane")}


def _verify_lane_for_this_process():
    """The reader an ordinary apply uses: the REAL one, in the real HUD process.

    Three things decide it, and none of them trusts the caller:

      * `JARVIS_SUITE_RUNNING` - `backend/_where.py` sets it for every suite
        that imports the checkout's helpers;
      * the process is running `jarvis_hud.py` - the same test
        `_warm_on_startup` uses for the same reason, and it is what catches a
        suite that does NOT import `_where` (measured 2026-11-18:
        `backend/test_reversible_ui_choices.py` loads the base's model steward
        directly, never sets the marker, and a lane read there answered with the
        owner's LIVE 11435 - "it is holding qwen3:8b, not qwen3.5:4b" - so the
        apply failed against a lane the suite never meant to touch);
      * anything else is not the backend, and gets the honest "not checked".

    A suite that wants to prove the reader passes `verify_lane=_default_verify_lane`
    itself, with a fake lane of its own (backend/test_preset_switch_lane_guard.py).
    """
    if os.environ.get("JARVIS_SUITE_RUNNING"):
        return _lane_not_checked
    main = sys.modules.get("__main__")
    name = os.path.basename(str(getattr(main, "__file__", "") or "")).lower()
    if name != "jarvis_hud.py":
        return _lane_not_checked
    return _default_verify_lane


def _preset_spill_allowance(p) -> int:
    """Bytes of spill THIS preset's own measurement allows on its lane, or 0.

    A HEAVY preset runs on the pooled lane, and a pooled mode's row carries the
    spill that mode was measured with (`pooled_modes()` -> `spill_allowance`:
    General/Reflective Coach 0.68 GiB; Coding, Medical, Pictures & Screens and
    General Uncensored 0).
    The apply's lane read-back is the only place that number has a say, and it is
    read from the ONE mode row rather than typed again here.
    Every preset that is not heavy keeps the zero-spill rule.
    """
    if not getattr(p, "heavy_mode", False):
        return 0
    mode = str(getattr(p, "mode", "") or "")
    for row in pooled_modes():
        if mode and str(row.get("key") or "") == mode:
            try:
                return max(0, int(row.get("spill_allowance") or 0))
            except (TypeError, ValueError):
                return 0
    return 0


def _default_verify_lane(url: str, model: str, min_ctx=None,
                         allow_spill: int = 0) -> dict:
    """Read the lane's own `/api/ps` and say what it REALLY holds. Never raises.

    {"ok", "checked", "why", "proof", "loaded"} - the shape an app can show, and
    the check `apply_preset` needs before it may answer `ok` (DEF-088: a preset
    apply reported success while port 11436 held the pooled coder at 8,192).

    WHAT COUNTS AS A FAILURE, and why an EMPTY lane is not one:
      * a model that is NOT the one this preset names -> failure. That is the A2
        defect exactly: the record said `qwen3.5:9b`, the lane served the coder.
      * the named model with MORE CPU spill than this preset's own measured
        allowance -> failure: it cannot answer at speed, and the spill was the
        second half of what the owner saw. The allowance is 0 for every
        non-heavy preset (the everyday lane's 9B fits); a heavy preset gets the
        spill its own pooled mode was measured with (`_preset_spill_allowance`),
        so General's measured 0.681 GiB does not fail its own apply while a
        worse load still does.
      * the named model at a window SMALLER than `min_ctx` (the preset's own
        declared context) -> failure. A named lane's chat turns carry no
        `options.num_ctx` (`jarvis_agent.chat_body`), so whatever window the
        last load left behind IS the window chat runs at - 8,192 instead of
        32,768 is the same defect wearing different numbers.
      * the named model PLUS another model on the same lane -> failure. The
        owner's rule is one preset's model at a time (2026-11-18); a second
        model left resident is the previous preset not ended, and the apply
        must not claim success for it.
      * a lane that does not answer at all -> failure: nothing was proved, and
        "could not tell" is never a pass.
      * the lane holding NOTHING -> NOT a failure. The apply records which model
        chat should use; Ollama loads it on the next turn at the lane's own
        window. Red-flagging that would fail the most ordinary apply there is.
    """
    import jarvis_big_coder as big
    where = str(url or "").rstrip("/")
    rows = big.ps(where)
    if rows is None:
        return {"ok": False, "checked": True, "loaded": [],
                "why": f"the lane at {where} did not answer, so what it holds is not known",
                "proof": f"{where}: no answer from /api/ps"}
    names = [str(row.get("name") or "") for row in rows if row.get("name")]
    row = big.loaded_row(rows, model)
    if row is None:
        if not names:
            return {"ok": True, "checked": True, "loaded": [],
                    "why": "",
                    "proof": (f"{where}: nothing is loaded there, so the next turn "
                              f"loads {model} - no other model was left on the lane")}
        return {"ok": False, "checked": True, "loaded": names,
                "why": f"it is holding {', '.join(names)}, not {model}",
                "proof": f"{where}: loaded {', '.join(names)}"}
    # THE OWNER'S RULE, WITH TEETH (2026-11-18): only ONE preset's model may be
    # loaded at a time. The named model being present is not enough - a second
    # model left resident beside it means a preset switch did not end the
    # previous one, and the apply must not answer ok for that. This is the read
    # that can see it: /api/ps is the machine's own list, never a remembered
    # flag. A lane that holds nothing is fine (checked above), so this only
    # fails the real two-model state.
    others = [name for name in names
              if _bare_model(name) != _bare_model(model)]
    if others:
        return {"ok": False, "checked": True, "loaded": names,
                "why": (f"it is holding {', '.join(others)} as well as {model}; "
                        "only one preset's model may be loaded at a time, so the "
                        "previous preset was not ended first"),
                "proof": f"{where}: loaded {', '.join(names)}"}
    spill = big.spill_bytes(row)
    ctx = row.get("context_length")
    proof = (f"{where}: {model} ctx={ctx} size={row.get('size')} "
             f"size_vram={row.get('size_vram')} spill={spill}")
    if spill is None or int(spill) > int(allow_spill or 0):
        allowed = (f", past the {int(allow_spill)} B this preset's own measurement "
                   f"allows" if allow_spill else "")
        return {"ok": False, "checked": True, "loaded": names,
                "why": (f"{model} came back with {spill} B spilled out of video "
                        f"memory{allowed}"),
                "proof": proof}
    try:
        ctx_n = int(ctx) if ctx is not None else None
    except (TypeError, ValueError):
        ctx_n = None
    if min_ctx and ctx_n is not None and ctx_n < int(min_ctx):
        return {"ok": False, "checked": True, "loaded": names,
                "why": (f"{model} is loaded at {ctx_n} tokens, smaller than the "
                        f"{int(min_ctx)} this preset names"),
                "proof": proof}
    return {"ok": True, "checked": True, "loaded": names, "why": "",
            "proof": proof}


def apply_preset(preset_id, *, provider=None, cloud_gate=None, start_lane=None,
                 switch_model=None, switch_for_owner=None, owner_ui=False,
                 active_url=None, set_active_url=None,
                 read_choice=None, write_choice=None, rollback_model=None,
                 stop_pooled=None, verify_lane=None, keep_alive=None) -> tuple:
    """Apply ONE preset: after the owner's card, or at once for an app click.

    `keep_alive` is the load's residency ask in Ollama's own units, and it is
    `None` for every caller but the start-up preset (2026-11-22): `-1` asks the
    lane to keep the model resident until something else evicts it, which is
    what makes an eager start-up load outlive Ollama's idle timer. It reaches
    the SAME loader through the same `start_lane` call - `-1` and nothing else
    changes - and it is passed only when a caller names it, so every existing
    seam, fake and caller keeps the exact call it made before. A LATER preset
    switch still ends this lane first (`stop_pooled`), so no second copy of any
    model becomes resident: the one-preset-at-a-time rule bounds the keep-alive.

    `owner_ui=True` is set by ONE caller - this module's own route wrapper
    (`install()`), the road both apps' preset controls use. It means "the
    owner clicked this", and a local preset applies with no card, writing a
    receipt first - the heavy ones included since 2026-11-16, whose pooled lane
    is started with the press as its approval (`_start_lane_for_the_owner`). It
    is NOT read from a request body, and every model/chat caller leaves it False
    and keeps the `switch_model` card.

    `preset_id == "cloud"` is its own branch (`apply_cloud`): it raises ONE
    `change_own_config` card for the service, writes the choice, and starts no
    lane and switches no model - so `start_lane`, `switch_model`,
    `rollback_model` and `set_active_url` are never touched on it. Cloud is the
    ONE row `owner_ui` cannot make cardless. A heavy preset keeps its card on
    the CARDED road (the pooled lane's own, raised inside `start_lane`).

    Order: start the named lane if it is down -> switch the model (the ask card
    lives inside switch_model on the ordinary path) -> READ THE LANE BACK and
    refuse unless it shows the preset's model at the preset's window with no
    spill BEYOND THAT PRESET'S OWN MEASURED ALLOWANCE (DEF-088; `verify_lane`,
    and `_default_verify_lane` says what counts as proof) -> point chat at it
    -> save the chosen preset.
    The lane start is BEFORE the card on purpose: a lane that is down cannot
    answer the switch's is_installed read, so switch-first is not possible.
    That means a card the owner DENIES leaves the started lane RUNNING (it
    starts no model and switches nothing) - stated here and in JARVIS-API
    section 145 rather than claiming nothing happens before the card.

    THE HEAVY ROWS ARE General, General Uncensored, Coding, Reflective Coach,
    Pictures & Screens and Medical, and since 2026-11-02 their lane exists. General joined them on
    2026-11-18: its model needs all three cards, and the everyday lane is
    pinned to one 12 GB card, so pointing it there was ruled out. A heavy
    preset's model cannot run on either named single-card lane; its lane is
    "pooled" (`jarvis_model_lanes.start_pooled_lane`), ONE Ollama on its own
    port with all three cards visible. That start raises the ONE `switch_model`
    card ITSELF,
    before it unloads anything, because the pause has to be announced before
    the first unload - which is why the heavy path's `switch_model` is
    `_default_adopt` (record the model that is already loaded, no second card,
    no smoke test on a single-card lane) rather than `_default_switch`. See
    `_default_adopt` for the whole argument. A card the owner denies leaves
    NOTHING changed on this path: nothing has been unloaded yet. ON THE APP-CLICK
    ROAD (`owner_ui=True`) that same start is given `_OwnerPressed` instead of
    the card (`_start_lane_for_the_owner`) - the owner's own press is the
    approval - while `switch_model` stays `_default_adopt` on BOTH roads: the
    click changes the card, never the model path.

    Since 2026-11-09 the same road carries the Medical preset: `p.mode` is
    passed to `start_pooled_lane`, which loads `medgemma:27b` at 32,768 with
    the same one card. General joined that road on 2026-11-18 with its own
    measured mode `gemma4-26b-a4b` (the same pooled row Reflective Coach uses),
    and `_preset_spill_allowance(p)` passes that mode's measured spill to the
    lane read-back - so General's 0.681 GiB is allowed by its own measurement
    and a worse load still fails.

    The other direction matters too: a preset that is NOT heavy needs the
    everyday lane back, so applying one ENDS the pooled lane first (it unloads
    the heavy model and puts the everyday 9B back exactly as it was). If it
    cannot end it, the apply refuses in plain words rather than trying to load a
    model on a card the heavy one is still holding.

    The contract lane key is "main" (both apps' fixture says so); the model
    starter calls that same lane "everyday" - `_default_start_lane` translates
    through LANE_START_KEYS. `pending` presets refuse before anything happens.
    Once the model HAS switched, any later failure rolls the model back with
    the auto-tier jarvis_models.rollback() as well as restoring the chat lane
    and the remembered preset - and, on the heavy path, stopping the pooled
    lane it started. **Each of those restores is checked** and the answer names
    only the ones that were seen to work; the ones that were not are listed
    under `not_restored` and said in the error (silent-failure audit
    2026-10-27, row 2).
    """
    if str(preset_id or "") == CLOUD_PRESET_ID:
        return apply_cloud(provider=provider, gate_check=cloud_gate)
    p = by_id(preset_id)
    if p is None:
        return 400, {"ok": False, "changed": False,
                     "error": f"no preset called {preset_id!r}; presets are "
                              f"{', '.join(PRESET_IDS)}"}
    if p.pending:
        return 409, {"ok": False, "changed": False, "error": PENDING_LINE}
    heavy = bool(p.heavy_mode)
    # THE ONE CONDITION THAT MAKES A PRESET CLICK UNCARDED: the request came
    # from the apps' own route (`owner_ui`). Cloud returned above and still
    # cards; every other row is the owner's own click, heavy or not. Since
    # 2026-11-16 a heavy preset's lane is started with the press as its approval
    # (`_start_lane_for_the_owner`), so no `jarvis_gate.check` is reached on this
    # road. The MODEL road is unchanged by the click: a heavy preset still
    # records through `_default_adopt` (the lane already loaded the model; a
    # `switch_to` here would smoke-test a 14.8 GB model against the owner's
    # one-card everyday lane - see its docstring). See the section above
    # `apply_preset`.
    direct_owner = bool(owner_ui)
    start_lane = start_lane or (_start_lane_for_the_owner if direct_owner
                                else _lane_starter)
    if heavy:
        if switch_model is None:
            switch_model = lambda ref: _default_adopt(ref)
    elif direct_owner:
        switch_model = (switch_for_owner or switch_model
                        or (lambda ref: _switch_for_the_owner(ref)))
    elif switch_model is None:
        switch_model = lambda ref: _default_switch(ref)
    active_url = active_url or _active_url
    set_active_url = set_active_url or _set_active_url
    read_choice = read_choice or choice
    write_choice = write_choice or _write_choice
    rollback_model = rollback_model or _default_rollback_model
    stop_pooled = stop_pooled or _default_stop_pooled
    previous_preset = read_choice()
    previous_lane = active_url()
    target_lane = _lane_url(p.lane)
    if not heavy:
        # The cards must be free before another preset's model can be loaded or
        # asked anything. Ending the pooled lane is the ONLY way back, and it
        # restores both lane models itself. A failure here is said in words and
        # nothing else is changed.
        try:
            ended = stop_pooled()
        except Exception as exc:
            ended = {"ok": False, "ran": True,
                     "reason": f"{type(exc).__name__}: {exc}"}
        if isinstance(ended, dict) and ended.get("ran") and not ended.get("ok"):
            why = ended.get("reason") or "the pooled three-card lane did not stop"
            return 503, {"ok": False, "changed": False,
                         "error": ("the big coding model is still holding both "
                                   f"cards, so this preset was not applied: {why}")}
    try:
        mode = str(getattr(p, "mode", "") or "")
        # `keep_alive` is named ONLY when the caller named one: the route, the
        # chat path and every injected seam keep the exact call they made before
        # 2026-11-22.
        keep = ({} if keep_alive is None else {"keep_alive": keep_alive})
        code, start_body = (start_lane(p.lane, mode=mode, **keep) if mode
                            else start_lane(p.lane, **keep))
    except Exception as exc:
        return 503, {"ok": False, "changed": False,
                     "error": f"the {p.lane} lane could not be started "
                              f"({type(exc).__name__}); nothing was changed"}
    if code not in (200, 202) or not start_body.get("ok", True):
        why = (start_body.get("reason") or start_body.get("error")
               or start_body.get("message") or "the lane did not start")
        if code in (200, 202):
            # A card the owner DENIED (the pooled lane asks before it unloads
            # anything). Nothing was touched, and this is a refusal, not a
            # failure of the machine.
            return 409, {"ok": False, "changed": False,
                         "error": f"{why}; nothing was changed",
                         "outcome": start_body.get("outcome", "refused")}
        return 503, {"ok": False, "changed": False,
                     "error": f"the {p.lane} lane did not start: {why}; nothing was changed"}
    # True only when THIS apply started the pooled lane (not when it was
    # already running before it): a rollback must not end a mode the owner had
    # already turned on.
    started_pooled = heavy and bool(start_body.get("changed"))
    # The receipt is written BEFORE the switch, the project's own rule, and
    # removed again if the switch (or anything after it) does not happen. It is
    # written for the app-click path only: the carded paths already have their
    # approval card as the record.
    receipt_id = (_record_owner_preset(previous_preset, previous_lane, p)
                  if direct_owner else "")
    try:
        switched = switch_model(p.model)
    except Exception as exc:
        switched = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    switched_ok = False

    def rollback(reason: str, code=409) -> tuple:
        # The lane start comes first (a down lane cannot answer the switch's
        # is_installed read), so a refused card can leave a lane RUNNING while
        # nothing was switched - said in the docstring and docs. Once the model
        # HAS switched, every later failure undoes it with the auto-tier
        # rollback, not only the lane pointer and the remembered choice.
        #
        # EVERY restore is checked, and the sentence names only what was
        # OBSERVED to happen (silent-failure audit 2026-10-27, row 2). It used
        # to be `except Exception: pass` on the lane pointer, the choice
        # write's return value never read, and then one sentence asserting all
        # three had been rolled back - so `changed: false` could stand beside a
        # model, a lane or a choice that had really moved. Now: a restore that
        # raised, returned a falsey result or reported `ok: false` is named as
        # NOT restored, and nothing is claimed that was not seen.
        restored: list = []
        failed: list = []

        def outcome(name: str, done: bool) -> None:
            (restored if done else failed).append(name)

        if started_pooled:
            # FIRST, because nothing can be loaded on a card the 30B is still
            # holding, and because the stop puts both lane models back itself.
            try:
                ended = stop_pooled()
                outcome("the pooled lane",
                        isinstance(ended, dict) and ended.get("ok") is True)
            except Exception:
                outcome("the pooled lane", False)
        if switched_ok:
            try:
                rb = rollback_model()
                outcome("the model", isinstance(rb, dict) and rb.get("ok") is True)
            except Exception:
                outcome("the model", False)
        # The chat lane pointer. `_set_active_url` answers a bool, so a falsey
        # answer is a real failure, not a "probably fine".
        try:
            outcome("the chat lane", bool(set_active_url(previous_lane)))
        except Exception:
            outcome("the chat lane", False)
        # The remembered preset: a file write, or its removal when nothing was
        # remembered before this apply (a file that is already gone is the
        # state we wanted, so that is success).
        try:
            if previous_preset is None:
                try:
                    _choice_path().unlink()
                except FileNotFoundError:
                    pass
                outcome("the chosen preset", True)
            else:
                outcome("the chosen preset", bool(write_choice(previous_preset)))
        except Exception:
            outcome("the chosen preset", False)

        def spoken(names) -> str:
            if len(names) == 1:
                return names[0]
            return ", ".join(names[:-1]) + " and " + names[-1]

        if failed:
            if restored:
                note = (f"{spoken(restored)} "
                        f"{'was' if len(restored) == 1 else 'were'} rolled back, but "
                        f"{spoken(failed)} could not be restored")
            else:
                note = f"{spoken(failed)} could not be restored"
            note += ". Check that on the PC before relying on the preset."
        else:
            note = (f"{spoken(restored)} "
                    f"{'was' if len(restored) == 1 else 'were'} rolled back")
        # `changed: false` means the preset is NOT the chosen one. It says
        # nothing about the model, the lane or the choice file - `restored` and
        # `not_restored` are the facts about those, and both are always sent.
        _discard_owner_receipt(receipt_id)
        return code, {"ok": False, "changed": False,
                      "error": f"{reason}; {note}",
                      "restored": restored, "not_restored": failed}
    if not isinstance(switched, dict) or not switched.get("ok"):
        return rollback(f"the model switch did not happen: "
                        f"{(switched or {}).get('reason', 'refused')}")
    switched_ok = True
    # THE LANE IS READ BACK BEFORE ANYTHING IS WRITTEN OR CLAIMED. This apply
    # used to answer `ok, changed` on the strength of two FILE writes - the
    # model record and the choice - and on 2026-11-17 that reported success
    # while port 11436 was loading the pooled coder at 8,192 tokens (the A2
    # field test, DEF-088). The lane now has to show the model this preset
    # names, at or above the window it names, within the spill its own
    # measurement allows, or the apply rolls back and says what it saw; see
    # `_default_verify_lane` for exactly what counts as proof and why an EMPTY
    # lane is not a failure. The seam exists so a suite can inject a fake lane
    # instead of a socket: the default is the real reader on the owner's PC and
    # an honest "not checked" inside a suite. `allow_spill` is the preset's own
    # measured allowance (`_preset_spill_allowance`): 0 for everything that is
    # not heavy, the pooled mode's measured spill for a heavy row.
    verify_lane = verify_lane or _verify_lane_for_this_process()
    allow_spill = _preset_spill_allowance(p)
    lane_check: dict = {}
    try:
        lane_check = verify_lane(target_lane, p.model,
                                 int(getattr(p, "context", 0) or 0) or None,
                                 allow_spill=int(allow_spill)) or {}
    except Exception as exc:
        lane_check = {"ok": False,
                      "why": (f"the lane could not be read "
                              f"({type(exc).__name__}: {exc})")}
    if not isinstance(lane_check, dict) or lane_check.get("ok") is not True:
        why = (lane_check or {}).get("why") or "the lane did not show the model"
        return rollback(f"the lane did not come back with {p.model}: {why}")
    # Both forward writes are checked AND held: an exception here used to
    # escape `apply_preset` (a 500 the caller could only show as an opaque
    # failure) instead of rolling back and saying what happened.
    try:
        lane_ok = bool(set_active_url(target_lane))
    except Exception:
        lane_ok = False
    if not lane_ok:
        return rollback("the chat lane could not be pointed at the new lane")
    try:
        choice_ok = bool(write_choice(p.id))
    except Exception:
        choice_ok = False
    if not choice_ok:
        return rollback("the chosen preset could not be saved")
    # Re-picking the preset that is already in force changed nothing, so it must
    # not leave an Undo row that would only "put back" the same thing.
    if (receipt_id and previous_preset == p.id
            and isinstance(switched, dict) and switched.get("unchanged")):
        _discard_owner_receipt(receipt_id)
        receipt_id = ""
    return 200, {"ok": True, "changed": True, "preset": p.view(),
                 "lane": dict(p.lane_info), "base_url": target_lane,
                 "model": p.model, "switched": switched,
                 "previous_preset": previous_preset,
                 # What the lane was seen to hold before this apply answered ok
                 # (DEF-088). `checked: false` is the suite's honest "not read".
                 "lane_check": lane_check,
                 # "" on every carded path; an app click leaves the receipt the
                 # owner can see in GET /api/receipts and undo from there.
                 "receipt_id": receipt_id}


def _default_start_lane(key: str, mode: str = "", keep_alive=None):
    """The preset's own lane, started on demand.

    "pooled" is not one of the PC's logon tasks: it is the ONE Ollama that sees
    all three cards, started here and stopped by the next apply that is not heavy
    (`_default_stop_pooled`). `jarvis_model_lanes.start_pooled_lane` raises the
    ONE card for it, before it unloads anything - on the CARDED road; the
    app-click road passes `_OwnerPressed` instead, because the press is the
    approval (`_start_lane_for_the_owner`). `mode` is the applied preset's pooled
    mode (Medical today); "" keeps the coding lane every pre-wave-14 caller has
    always started. `keep_alive` is forwarded to the lane ONLY when the caller
    named one (the start-up preset, 2026-11-22); a named-lane start loads no
    model at all, so it has nowhere to put it.
    """
    import jarvis_model_lanes
    if str(key) == jarvis_model_lanes.POOLED_KEY:
        if keep_alive is None:
            return jarvis_model_lanes.start_pooled_lane(mode=str(mode or "coding"))
        return jarvis_model_lanes.start_pooled_lane(mode=str(mode or "coding"),
                                                    keep_alive=keep_alive)
    mapped = LANE_START_KEYS.get(str(key))
    if mapped is None or jarvis_model_lanes.lane_by_key(mapped) is None:
        return 409, {"ok": False, "changed": False,
                     "reason": f"the preset lane {key!r} has no model lane on this PC "
                               f"(known lanes: {', '.join(l.key for l in jarvis_model_lanes.LANES)})"}
    return jarvis_model_lanes.start_lane(mapped)


def _lane_starter(key: str, mode: str = "", keep_alive=None):
    """`_default_start_lane` with the mode passed ONLY when a preset names one.

    The nine older presets name no pooled mode, so they call the starter with
    one argument exactly as before: every injected one-argument seam in the
    existing tests, and every caller that replaced `_default_start_lane`, keeps
    working. The two-argument call is reserved for a preset that really does
    name a pooled mode (Medical today), and an injected seam that cannot take
    it says so with a TypeError rather than being silently downgraded. A third
    argument (`keep_alive`) is passed only when the start-up path names one.
    """
    if keep_alive is not None:
        return _default_start_lane(key, mode, keep_alive=keep_alive)
    return _default_start_lane(key, mode) if mode else _default_start_lane(key)


def _default_stop_pooled() -> dict:
    """End the pooled lane if it is running. Never raises.

    `{"ok", "ran", "reason"}`: `ran` says whether it was running at all, so the
    apply can tell "nothing to do" from "it would not stop". A read of
    `/api/ps` decides that, never a remembered flag - the lane's own model is
    the evidence, which is what survives a backend restart.
    """
    import jarvis_model_lanes
    try:
        running = jarvis_model_lanes.pooled_running()
    except Exception:
        running = False
    if not running:
        return {"ok": True, "ran": False, "reason": ""}
    try:
        code, body = jarvis_model_lanes.stop_pooled_lane()
    except Exception as exc:
        return {"ok": False, "ran": True, "reason": f"{type(exc).__name__}: {exc}"}
    ok = code in (200, 202) and isinstance(body, dict) and bool(body.get("ok"))
    reason = ""
    if not ok:
        reason = (body.get("error") or body.get("message")
                  or "the pooled three-card lane did not stop") if isinstance(body, dict) \
            else "the pooled three-card lane did not stop"
    return {"ok": ok, "ran": True, "reason": reason, "body": body}


def _default_rollback_model():
    import jarvis_models
    return jarvis_models.rollback()


def _default_switch(ref: str):
    import jarvis_models
    return jarvis_models.switch_to(ref, why="preset")


def _default_adopt(ref: str):
    """Record the model the POOLED lane has already loaded. No second card.

    WHY THIS EXISTS, and why it is not `_default_switch`. `jarvis_models.
    switch_to` raises the `switch_model` card - which is right for every
    single-card preset - and then runs the tripwire's smoke test AT
    `jarvis_models.OLLAMA`: the address of the owner's own lane, pinned to ONE
    card (12 GB). A 14 GB coding model cannot be loaded there. By the time this
    is called the model is already loaded on the pooled lane, so `switch_to`
    would either ask that card to hold a second copy or evict the model the
    pooled lane just loaded, and its "did the new model work" answer would be
    about the wrong lane. So the ONE card for this change is the pooled lane's
    own (`jarvis_model_lanes.start_pooled_lane`, action `switch_model`, the
    same `from`/`to`/`why` detail `switch_to` sends), and this writes the same
    record `switch_to` writes - through the model steward's own read and write,
    so the format lives in one place and cannot drift.

    NOTHING ELSE CALLS IT, it raises no card, and it is only reached from the
    heavy-mode branch of `apply_preset` - after the pooled lane's ONE card was
    approved, OR after the owner's own preset click answered it on the app route
    - and after the model really loaded (a load that spills past this lane's one
    measured allowance is undone before this runs). If the model steward on
    this PC cannot be read or written, this says so and the apply rolls
    everything back rather than pretending.
    """
    try:
        import time as _time
        import jarvis_models as M
    except Exception as exc:
        return {"ok": False, "ref": ref,
                "reason": f"the model steward is not available ({type(exc).__name__})"}
    read = getattr(M, "_read_state", None)
    write = getattr(M, "_write_state", None)
    if not callable(read) or not callable(write):
        return {"ok": False, "ref": ref,
                "reason": ("this PC's model steward has no recordable model state, "
                           "so the coding model could not be made the one chat uses")}
    try:
        st = read()
        st = dict(st) if isinstance(st, dict) else {}
        cur = st.get("current")
        if cur == ref:
            return {"ok": True, "ref": ref, "unchanged": True,
                    "reason": "already the model in use"}
        at = _time.time()
        st["previous"] = cur
        st["current"] = ref
        st["switched_at"] = at
        st["why"] = "the Coding preset's pooled three-card lane"[:300]
        log = list(st.get("switches") or [])
        log.append({"from": cur, "to": ref, "at": at})
        st["switches"] = log[-int(getattr(M, "MAX_HISTORY", 20) or 20):]
        if not write(st):
            return {"ok": False, "ref": ref,
                    "reason": "could not write the model state file; nothing was recorded"}
    except Exception as exc:
        return {"ok": False, "ref": ref, "reason": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "ref": ref, "previous": cur, "adopted": True,
            "reason": f"the pooled three-card lane now answers as {ref}"}


def apply_from_body(body) -> tuple:
    """`POST /api/work/apply {"preset": "<id>", "provider": "<service>"}`.

    The public entry point, and the one every model/chat path calls
    (`jarvis_model_knowledge.apply_preset`, `jarvis_settings_registry.
    set_focus_preset`): it keeps the `switch_model` ask card. `provider` is
    read only for the `"cloud"` preset and ignored everywhere else, which is
    what keeps every existing call's bytes meaning exactly what they meant
    before (a body with no `provider` is the same request it was).

    It is deliberately NOT the road the apps' own preset controls take: the
    route wrapper below calls `_apply_body(..., owner_ui=True)` itself, and the
    body is never asked for a "no card" field of any kind.
    """
    return _apply_body(body, owner_ui=False)


def _apply_body(body, *, owner_ui: bool, keep_alive=None) -> tuple:
    """`apply_from_body` with the road named; private on purpose.

    `owner_ui=True` is passed by ONE caller in this program - `install()`'s
    POST wrapper, the route both apps' preset controls use - so no Python
    caller can turn a card off by accident, and no request field can ask for
    it. `owner_ui=False` is the carded path, unchanged.

    `keep_alive` is the start-up preload's own residency ask (2026-11-22), and
    it is passed by ONE caller - `apply_startup_preset` - never read from a
    request body, so the route's own bytes are unchanged. It travels to
    `apply_preset`'s `start_lane`, the road the route already takes.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "expected a JSON object"}
    provider = body.get("provider")
    if provider is not None and not isinstance(provider, str):
        return 400, {"ok": False, "error": '"provider" must be text'}
    if keep_alive is None:
        return apply_preset(body.get("preset"), provider=provider,
                            owner_ui=owner_ui)
    return apply_preset(body.get("preset"), provider=provider,
                        owner_ui=owner_ui, keep_alive=keep_alive)


def install(Handler, *, origin_ok, token_ok, read_body):
    """Wire GET /api/work and GET /api/presets (the preset contract),
    POST /api/work/apply, POST /api/work/cloud-escalate and
    POST /api/work/startup-preset onto the HUD's Handler. Returns the status
    line the banner prints. Reads nothing from the owner's PC except what
    live_status() reports; it approves nothing: the cloud apply, the escalation
    switch and setting a start-up preset raise their one change_own_config
    card. A LOCAL preset applied through this route is the owner's own click:
    it applies at once, writes a receipt, and starts a heavy preset's pooled
    lane with that press as its approval - the model path keeps its card, and
    the same preset asked for in chat still raises it."""
    # THE MANUAL-CLICK RULE'S MODEL SWITCH (Gemini Q2, 2026-11-09). A model
    # already on this PC, picked in either app's own model list, takes the same
    # uncarded road a preset click takes. `jarvis_reversible_ui.py` is the
    # allow-list and the route; this installer is already wired into the HUD by
    # presets.patch, so the model picker needs no second patch. It intercepts
    # ONE path, checks the same origin and token as this wrapper, and forwards
    # every other path untouched. It is installed BEFORE `original` below is
    # captured, so `original` is the switch's own forwarder.
    try:
        import jarvis_reversible_ui
        print("  " + jarvis_reversible_ui.install(
            Handler, origin_ok=origin_ok, token_ok=token_ok,
            read_body=read_body))
    except Exception as exc:                     # noqa: BLE001 - never blocks start-up
        print(f"  reversible  not installed ({type(exc).__name__})")
    original_get = getattr(Handler, "do_GET", None)

    def do_GET(self):
        import json
        path = str(getattr(self, "path", "") or "").split("?", 1)[0]
        if path not in ("/api/work", "/api/presets"):
            if original_get is None:
                return self._send(404, {"error": "not found"})
            return original_get(self)
        if not origin_ok(self):
            return self._send(403, {"error": "cross-origin request refused"})
        if not token_ok(self):
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        try:
            out = live_status()
        except Exception as exc:
            return self._send(503, {"available": False,
                                    "error": f"{type(exc).__name__}: {exc}"})
        return self._send(200, out)

    Handler.do_GET = do_GET
    original = getattr(Handler, "do_POST", None)

    def do_POST(self):
        import json
        path = str(getattr(self, "path", "") or "").split("?", 1)[0]
        if path not in (APPLY_PATH, CLOUD_ESCALATE_PATH, STARTUP_PATH):
            if original is None:
                return self._send(404, {"error": "not found"})
            return original(self)
        if not origin_ok(self):
            return self._send(403, {"error": "cross-origin request refused"})
        if not token_ok(self):
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        try:
            body = json.loads(read_body(self) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            return self._send(400, {"error": str(exc)})
        # The standing escalation switch is its OWN route, because it is its
        # own verb: applying a preset says which model answers, and this says
        # whether Jarvis may ask the cloud with no per-question yes. Both raise
        # a card through the same gate.
        #
        # THE START-UP PRESET IS ITS OWN ROUTE for the same reason (2026-11-22):
        # applying a preset says which model answers NOW, and this says which
        # one loads by itself the next time Atlas starts. It raises the same
        # `change_own_config` card and writes nothing before the yes.
        #
        # THIS IS THE ONLY PLACE `owner_ui=True` IS SET, and this route already
        # passed the server's origin and token checks above. It is what makes a
        # local preset click apply at once, the heavy ones included since
        # 2026-11-16; the body cannot ask for it, and every other caller of
        # apply_from_body keeps the card. Cloud still cards here (apply_preset
        # decides), and so does the same preset asked for in chat.
        if path == CLOUD_ESCALATE_PATH:
            code, out = escalate_from_body(body)
        elif path == STARTUP_PATH:
            code, out = startup_from_body(body)
        else:
            code, out = _apply_body(body, owner_ui=True)
        return self._send(code, out)

    Handler.do_POST = do_POST
    # Repair the persisted preset state BEFORE anything reads it: an on-demand
    # pooled lane does not survive a restart, and a chat lane left pointing at
    # its dead port fails every coding-routed turn with a false "not running"
    # (and lets a wake-time warm-up load the pooled 30B on one card). Real HUD
    # process only, the same rule as the card warm below, so a suite's
    # install() stays off the owner's PC.
    #
    # THE START-UP PRESET COMES FIRST, and that order is the feature (2026-11-22):
    # when the owner has marked a preset to load, the start-up step applies it
    # through the route's own road, and the reconcile above only runs if that
    # apply could not happen. Running the reconcile first would delete
    # `presets-choice.json` - the choice the next step was about to serve -
    # before anything had a chance to load it.
    #
    # A start-up load takes about a minute (26B cold load) and the HUD must serve
    # its first request during it, so THAT road runs in its own thread and
    # updates `restart_reconcile` when it finishes. With no start-up preset the
    # reconcile runs here, synchronously, exactly as it always has.
    global _LAST_RECONCILE
    if _warm_on_startup():
        if startup_preset():
            if not _start_startup_check():
                _LAST_RECONCILE = {
                    "changed": False, "lane": "", "preset": startup_preset(),
                    "why": ("the start-up preset could not be loaded because the "
                            "background check would not start; chat was left as it "
                            "was")}
                print("  presets    " + str(_LAST_RECONCILE.get("why") or ""))
        else:
            try:
                _LAST_RECONCILE = reconcile_after_restart()
                if _LAST_RECONCILE.get("changed"):
                    print("  presets    " + str(_LAST_RECONCILE.get("why") or ""))
            except Exception as exc:                 # noqa: BLE001 - never blocks start-up
                _LAST_RECONCILE = {"changed": False,
                                   "why": f"{type(exc).__name__}: the startup check failed"}
    # Warm the card detection while the HUD finishes starting, so the first
    # GET /api/work does not pay the ~10 s `nvidia-smi` + lane-probe cost. The
    # request path never does it again once a snapshot exists (see above).
    if _warm_on_startup():
        _refresh_detect_cache_async()
    return "presets    ready"

# --------------------------------------------------------------------------
#   Hardware, questionnaire and 1/2/3-GPU recommendations (contract extension)
# --------------------------------------------------------------------------

PRIORITIES = ("speed", "quality", "long_context", "vision")

#: How long a card detection is reused. `jarvis_hardware.detect()` is not cheap
#: (measured at ~10 s on the owner PC), and `GET /api/work` is read by both
#: apps through request timeouts of ~20 s; calling it twice inside one contract
#: build made the live endpoint take ~20.6 s and time the clients out. Cards do
#: not appear or disappear between requests, so a short cache is honest; tests
#: clear it when they need a fresh answer.
DETECT_CACHE_SECONDS = 60.0

#: How long a FIRST call may wait for a detection that is already in flight.
#: The startup warm-up (below) runs off the request path; if the very first
#: request arrives while it is still running, waiting for that one detection is
#: better than starting a second `nvidia-smi`. Bounded so a wedged detector
#: cannot hold a request for ever - past it the call detects for itself.
DETECT_COLD_WAIT_SECONDS = 30.0

#: The cached snapshot: "at" is the monotonic time it was stored, "value" the
#: contract dict, "in_flight" that a background refresh is running. ONE lock
#: guards all three (the detection itself runs outside it).
_DETECT_CACHE = {"at": 0.0, "value": None, "in_flight": False}
_DETECT_LOCK = threading.Lock()
#: Set once a snapshot has been stored, so a first call can wait for a
#: detection already in flight instead of starting a second one.
_DETECT_STORED = threading.Event()


def _copy_detection(value: Optional[dict]) -> dict:
    """The snapshot, copied so callers cannot mutate the cache. None reads as
    the no-cards answer, never as an exception."""
    if value is None:
        return {"count": 0, "cards": [], "source": "jarvis_hardware.detect()"}
    return {**value, "cards": [dict(card) for card in value["cards"]]}


def _clear_detect_cache() -> None:
    """Forget the cached card detection (tests and a hardware change).

    The next read detects SYNCHRONOUSLY: clearing means "I need a fresh answer
    now". Only the ordinary TTL expiry has a stale answer to serve, and only
    that path refreshes in the background.
    """
    with _DETECT_LOCK:
        _DETECT_CACHE["value"] = None
        _DETECT_CACHE["at"] = 0.0
    _DETECT_STORED.clear()


def _detect_cards() -> dict:
    """Run `jarvis_hardware.detect()` and shape the result. The slow part;
    touches no cache state. Never raises; count 0 is said plainly."""
    try:
        import jarvis_hardware
        got = jarvis_hardware.detect() or {}
        rows = got.get("cards") or []
    except Exception:
        rows = []
    cards = []
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if isinstance(row, dict):
            name = row.get("name") or row.get("model") or f"card {i}"
            # `total_gib` LAST, not first: it is what jarvis_hardware.detect()
            # actually puts on a card row (jarvis_hardware.py's `rows.append`,
            # "total_gib": s.total_mb / 1024), and it was missing from this
            # tuple until 2026-11-04 - so every card's vram_gib came out None
            # and the hardware screen showed the count with blank sizes. The
            # other three keys are kept first so a caller that already speaks
            # this block's own vocabulary still wins.
            vram = (row.get("vram_gib") or row.get("memory_gib") or row.get("vram")
                    or row.get("total_gib"))
            uuid = row.get("uuid") or row.get("id") or ""
            # The two facts that tell two IDENTICAL cards apart (2026-11-04):
            # `nvidia-smi` reports the PCI address of every card, and whether a
            # monitor is plugged into it. Without them a plan can only say
            # "card 1" and "card 2", which is an array position, not a card.
            # Both stay None/"" when the caller does not know them, so nothing
            # here ever invents a fact.
            pci_id = str(row.get("pci_id") or "")
            monitor = row.get("monitor")
            monitor = monitor if isinstance(monitor, bool) else None
        else:
            name = str(getattr(row, "name", "") or f"card {i}")
            vram = (getattr(row, "vram_gib", None) or getattr(row, "memory_gib", None)
                    or getattr(row, "total_gib", None))
            uuid = str(getattr(row, "uuid", "") or "")
            pci_id = str(getattr(row, "pci_id", "") or "")
            monitor = getattr(row, "monitor", None)
            monitor = monitor if isinstance(monitor, bool) else None
        cards.append({"index": i, "name": str(name),
                      "vram_gib": (round(float(vram), 1) if isinstance(vram, (int, float)) else None),
                      "uuid": uuid, "pci_id": pci_id, "monitor": monitor})
    return {"count": len(cards), "cards": cards,
            "source": "jarvis_hardware.detect()"}


def _store_detection(result: dict) -> None:
    """Remember one detection - the only place the cache is written."""
    with _DETECT_LOCK:
        _DETECT_CACHE["value"] = result
        _DETECT_CACHE["at"] = time.monotonic()
    _DETECT_STORED.set()


def _refresh_detect_cache() -> None:
    """One background refresh: detect off the request thread, then store."""
    try:
        _store_detection(_detect_cards())
    finally:
        with _DETECT_LOCK:
            _DETECT_CACHE["in_flight"] = False


def _refresh_detect_cache_async() -> bool:
    """Start THE background refresh, unless one is already running.

    True when a thread was started, False when a refresh was already in flight
    (or could not start) - so a burst of expired-cache requests starts ONE
    detection, never one per request. Never raises.
    """
    with _DETECT_LOCK:
        if _DETECT_CACHE["in_flight"]:
            return False
        _DETECT_CACHE["in_flight"] = True
    thread = threading.Thread(target=_refresh_detect_cache,
                              name="jarvis-presets-detect", daemon=True)
    try:
        thread.start()
    except Exception:
        with _DETECT_LOCK:
            _DETECT_CACHE["in_flight"] = False
        return False
    return True


def _warm_on_startup() -> bool:
    """Is this the real HUD process? Only the HUD warms the cache at startup: a
    test's `install()` must not run `nvidia-smi` behind the suite that called
    it. `backend/_where.py` sets JARVIS_SUITE_RUNNING for the suites, and the
    HUD is the script named `jarvis_hud.py` (the desktop app starts that file).
    """
    if os.environ.get("JARVIS_SUITE_RUNNING"):
        return False
    main = sys.modules.get("__main__")
    name = os.path.basename(str(getattr(main, "__file__", "") or "")).lower()
    return name == "jarvis_hud.py"


def _detected_cards() -> dict:
    """Every card this PC reports, from jarvis_hardware.detect() - never a
    hardcoded two-card table. Never raises; count 0 is said plainly.

    STALE-WHILE-REVALIDATE. Once a snapshot exists it is served until the TTL
    runs out; when the TTL expires the request STILL gets the old snapshot
    immediately, and one background thread refreshes it. The request thread
    never runs the detection except on the very first call, when there is no
    snapshot to serve - because `detect()` measured ~10 s on the owner PC and
    used to block one `GET /api/work` / `GET /api/presets` every minute.
    """
    with _DETECT_LOCK:
        value = _DETECT_CACHE["value"]
        at = _DETECT_CACHE["at"]
    if value is not None:
        if time.monotonic() - at < DETECT_CACHE_SECONDS:
            return _copy_detection(value)
        _refresh_detect_cache_async()
        return _copy_detection(value)
    # Nothing cached yet, so the first answer has to be a real detection. A
    # startup warm-up may already be running it; wait for that ONE detection
    # rather than starting a second, and detect here if it never lands.
    with _DETECT_LOCK:
        in_flight = _DETECT_CACHE["in_flight"]
    if in_flight:
        _DETECT_STORED.wait(DETECT_COLD_WAIT_SECONDS)
        with _DETECT_LOCK:
            value = _DETECT_CACHE["value"]
        if value is not None:
            return _copy_detection(value)
    result = _detect_cards()
    _store_detection(result)
    return _copy_detection(result)


def hardware_block() -> dict:
    return {"detected": _detected_cards(),
            "questionnaire": {"focus_choices": list(PRESET_IDS),
                              "priority_choices": list(PRIORITIES),
                              "answers": None}}


#: The port the pooled three-cards lane listens on. It is
#: `jarvis_model_lanes.POOLED_PORT` (and `jarvis_big_coder.BIG_PORT`), and it is
#: a literal here on purpose: this module is imported by the backend's start-up
#: banner and by suites that run without the lane module beside them, so it must
#: not pull `jarvis_model_lanes` in at import time. `backend/test_presets.py`
#: pins the three to each other, so the number cannot drift in one place only.
POOLED_PLAN_PORT = 11450


def _card_roles(cards: list) -> dict:
    """Which detected card plays which role in a three-card plan, from the
    PC's own facts - never an array position.

    `main` is the card with the MOST video memory, because the long-context
    everyday model has to fit there (the 12 GB RTX 2060 on this PC). `display`
    is the card `nvidia-smi` says a monitor is plugged into; `headless` is the
    remaining card. Two identical RTX 2080 SUPERs cannot be told apart by
    number, and the plan's own words used to call them "#1" and "#2" as if the
    order in the list were a fact about the machine.

    THE MONITOR IS SEARCHED FOR ON EVERY CARD, not only outside `main`
    (fixed 2026-11-05). It used to search only `rest`, so on a PC whose
    highest-VRAM card has the monitor it fell through to `rest[0]` - a card
    with NO monitor - and `_role_words(..., "display")` then called that row
    "the card with no monitor" while the plan called it the monitor lane. Now
    a monitor found on the everyday card sets `monitor_on_main`, the display
    LANE still gets its own card (the Fast/Live model does not need the
    screen), and `_role_words` says where the monitor really is instead of
    pretending this card has it.

    The three indexes are always integers so every row can be placed even on a
    PC with fewer cards than the plan describes; `display_known` and
    `headless_known` say whether a card was really FOUND for the role, and
    `_role_words` uses them, so a card that is not installed is never described
    as if it were. `display_known` stays False when the display LANE was
    placed on a card the monitor is NOT on (`monitor_on_main`).
    """
    n = len(cards)

    def _vram(card):
        value = card.get("vram_gib")
        return float(value) if isinstance(value, (int, float)) else -1.0

    main = min(range(n), key=lambda i: (-_vram(cards[i]), i)) if n else 0
    rest = [i for i in range(n) if i != main]
    # EVERY card is searched for the monitor, not only `rest` (2026-11-05).
    # A monitor card that is not the everyday card is the display card; if
    # the only monitor card IS the everyday card, `monitor_on_main` says so
    # and the Fast/Live lane gets another card.
    display, display_known = None, False
    for i in range(n):
        if i != main and cards[i].get("monitor") is True:
            display, display_known = i, True
            break
    monitor_on_main = bool(display is None and 0 <= main < n
                           and cards[main].get("monitor") is True)
    if display is None:
        # No display flag anywhere, or the monitor is on the everyday card:
        # the Fast/Live lane still needs a card of its own. `monitor_on_main`
        # makes the words say where the monitor is.
        display = rest[0] if rest else main + 1
    headless, headless_known = None, False
    for i in rest:
        if i != display:
            headless, headless_known = i, True
            break
    if headless is None:
        headless = max(main, display) + 1
    return {"main": int(main), "display": int(display),
            "headless": int(headless),
            "display_known": bool(display_known),
            "headless_known": bool(headless_known),
            "monitor_on_main": bool(monitor_on_main)}


def _role_words(cards: list, roles: dict, role: str) -> str:
    """One role as the owner reads it: the card's own detected name, its PCI
    address when the PC reports one (the only proof of which twin is which),
    and the fact that decided the role - or, when there is no such card, plain
    words that say it is not installed yet."""
    index = roles[role]
    card = cards[index] if 0 <= index < len(cards) else None
    if card is None:
        return {"main": "a card this PC has not detected",
                "display": "the second 2080 SUPER (not installed yet)",
                "headless": "the headless 2080 SUPER (not installed yet)"}[role]
    name = str(card.get("name") or f"card {index}")
    word = f"{name} (PCI {card['pci_id']})" if card.get("pci_id") else name
    vram = card.get("vram_gib")
    if role == "main":
        return f"{word}, {vram:g} GB" if isinstance(vram, (int, float)) else word
    if role == "display":
        # `monitor` is nvidia-smi's display_active: True when a monitor is
        # plugged in, False when it is not, None when this PC could not say.
        # A known flag needs no explanation; only the UNKNOWN case must be
        # said out loud, so the owner is never told which twin has the monitor
        # when nothing measured it.
        if roles.get("monitor_on_main"):
            # The monitor is on the everyday card. This card still runs the
            # Fast/Live lane, and the words say where the screen really is -
            # never that this card has it, and never a bare "card with no
            # monitor" beside a row called the monitor lane (2026-11-05).
            return f"{word}; the monitor is on the everyday card instead"
        if card.get("monitor") is True:
            return f"{word}, the card with the monitor"
        if card.get("monitor") is False:
            return f"{word}, the card with no monitor"
        return f"{word}; monitor not reported by this PC"
    if card.get("monitor") is False:
        return f"{word}, the card with no monitor"
    return word


def _row(p: Preset, index: int, cards: list, measured: bool,
         best_effort: bool, note: str = "", card_text: str = "") -> dict:
    card = cards[index] if index < len(cards) else None
    return {"preset": p.id, "model": p.model,
            "card_index": index,
            "card": card_text or (card or {}).get("name") or f"card {index}",
            "context": p.context,
            "tok_s": (p.measured or {}).get("tok_s") if measured else None,
            "measured": bool(measured),
            "best_effort_not_tested": bool(best_effort),
            "note": note}


def recommendations() -> dict:
    """The 1-, 2- and 3-GPU rows for every preset, and the 3-card plan.

    ONE PRESET'S MODEL AT A TIME (the owner's rule, 2026-11-18). Every preset
    names one model on one lane, and applying a different preset ends the
    previous model first - nothing is left resident "just in case". Because no
    preset has to keep a card free for another preset, any preset may use all
    three cards where its model warrants it: the everyday lane (port 11436) and
    the on-demand pooled lane (port 11450) both see all three. The old
    one-lane-per-GPU layout this screen used to describe is GONE - it is the
    text that kept the retired 11435 lane looking necessary.

    A row's `measured` flag is the preset's own receipt (`p.measured`), never a
    layout claim: the 26B's figures were taken on this PC across all three
    cards, so a one- or two-card row that cannot hold it says
    best_effort_not_tested in words instead. A pending preset is never
    recommended (pending=True comes through and no figure is given).
    """
    cards = _detected_cards()["cards"]
    by = {}
    for n in (1, 2, 3):
        rows = {}
        for p in PRESETS:
            if p.pending:
                rows[p.id] = _row(p, 0, cards, False, True,
                                  "waiting for the model; nothing can be placed yet")
                continue
            if n == 1:
                rows[p.id] = _row(p, 0, cards, False, True,
                                  "one card: reasoned, not measured on this PC")
            elif n == 2:
                if p.lane == "pooled":
                    rows[p.id] = _row(p, 0, cards, p.measured is not None,
                                      p.measured is None,
                                      f"HEAVY MODE: {p.model} on "
                                      f"the pooled lane (port {POOLED_PLAN_PORT}) across "
                                      "ALL THREE cards, started on demand; it pauses "
                                      "the everyday model while it runs",
                                      card_text=(f"all three cards (pooled lane, port "
                                                 f"{POOLED_PLAN_PORT})"))
                else:
                    rows[p.id] = _row(p, 0, cards, p.measured is not None,
                                      p.measured is None,
                                      "the everyday lane: all the cards this PC has, "
                                      "one preset's model at a time")
            else:
                # 2026-11-18: one preset's model loaded at a time. The everyday
                # lane (ONE card on this PC) carries the long-window 9B rows and
                # the short-window ones; the pooled lane (all three cards) carries
                # every heavy row, General's 26B included, and pauses the everyday
                # model while it runs.
                roles = _card_roles(cards)
                everyday = _role_words(cards, roles, "main")
                pooled_card = (f"all the cards (pooled lane, port "
                               f"{POOLED_PLAN_PORT})")
                note = {
                    "general": (f"{p.model} on ONE pooled lane (port "
                                f"{POOLED_PLAN_PORT}) across ALL the cards at "
                                f"{p.context:,} tokens: HEAVY MODE, it pauses the "
                                f"everyday model while it runs"),
                    "general_uncensored": (f"{p.model} on ONE pooled lane (port "
                                           f"{POOLED_PLAN_PORT}) across ALL the "
                                           f"cards at {p.context:,} tokens: HEAVY "
                                           f"MODE, it pauses the everyday model "
                                           f"while it runs"),
                    "coding": (f"{p.model} on ONE pooled lane (port "
                               f"{POOLED_PLAN_PORT}) across ALL the cards: it is "
                               f"too big for one card, so applying this preset "
                               f"pauses the everyday model, starts that lane, and "
                               f"stops it again when another preset is applied"),
                    "fast": f"{everyday}: Fast, qwen3.5:4b, {p.context:,} window",
                    "agentic_vision": (f"{everyday}: Agentic+Vision, qwen3.5:9b "
                                       f"with images, {p.context:,} window"),
                    "reflect": (f"{p.model} on ONE pooled lane (port "
                                f"{POOLED_PLAN_PORT}) across ALL the cards at "
                                f"{p.context:,} tokens: HEAVY MODE, it pauses the "
                                f"everyday model while it runs"),
                    "pictures": (f"{p.model} on ONE pooled lane (port "
                                 f"{POOLED_PLAN_PORT}) across ALL the cards at "
                                 f"{p.context:,} tokens: HEAVY MODE, it pauses the "
                                 f"everyday model while it runs"),
                    "documents": (f"{everyday}: Documents & Notes, qwen3.5:9b, "
                                  f"{p.context:,} window"),
                    "browser": (f"{everyday}: Browser & Forms, qwen3.5:9b, "
                                f"{p.context:,} window"),
                    "medical": (f"medgemma:27b on ONE pooled lane (port "
                                f"{POOLED_PLAN_PORT}) across ALL the cards at "
                                f"{p.context:,} tokens: HEAVY MODE, it pauses the "
                                f"everyday model while it runs"),
                }[p.id]
                role_text = {
                    "general": pooled_card,
                    "general_uncensored": pooled_card,
                    "coding": pooled_card,
                    "fast": everyday,
                    "agentic_vision": everyday,
                    "reflect": pooled_card,
                    "pictures": pooled_card,
                    "documents": everyday,
                    "browser": everyday,
                    "medical": pooled_card,
                }[p.id]
                # `card_index` is the first card of the lane (the everyday
                # card), kept for the apps that sort by position; the `card`
                # TEXT is what names where the model really runs - General's
                # heavy row says the pooled lane on all three cards, and a
                # named-lane row names the one everyday card it is loaded on.
                # `_row()`'s fallback is `f"card {index}"` - an array position
                # the owner cannot see - so no row is left to it.
                rows[p.id] = _row(p, roles["main"], cards, False, True, note,
                                  card_text=role_text)
        by[str(n)] = rows
    roles = _card_roles(cards)
    return {"by_gpu_count": by,
            "basis": ("one preset's model is loaded at a time; every heavy preset, "
                      "General included, needs the pooled lane's three cards, so "
                      "one- and two-card layouts are reasoned and labelled, never "
                      "claimed as measured"),
            "three_gpu_plan": {
                "confirmed": True,
                # The owner's rule, in the order the owner meets it: the one
                # model, then the all-three-cards consequence. The old sentence
                # here said "everyday presets keep one lane per GPU" - it is the
                # text that kept the retired second lane looking necessary, so
                # it is replaced rather than reworded.
                "layout": ("ONE preset's model is loaded at a time: applying "
                           "another preset ends the previous one first, so no "
                           "preset has to keep a card free for another. The "
                           "everyday lane (port 11436) is ONE card on this PC and "
                           "serves the 9B rows - Documents & Notes and Browser & "
                           "Forms at 196,608 tokens, Fast and Agentic + Vision at "
                           f"16,384. The pooled lane (port {POOLED_PLAN_PORT}) "
                           "sees ALL THREE cards and carries every heavy preset - "
                           "General's 26B at 32,768, General Uncensored's measured "
                           "30B MoE at 32,768, Coding, Reflective Coach, Pictures & "
                           "Screens and Medical - and it pauses the everyday model "
                           "while it runs, because no preset has to keep a card free "
                           "for another. So any preset may use all three cards "
                           "where its model warrants it. There is no one-lane-per-GPU "
                           "split any more."),
                "cards": [
                    {"role": ("everyday lane: ONE card (the RTX 2060), port 11436 - "
                              "the 9B long-window rows at 196,608; Fast and "
                              "Agentic + Vision at 16,384"),
                     "card": _role_words(cards, roles, "main"), "context": 196608},
                    {"role": ("pooled lane, started on demand: all three cards, "
                              f"port {POOLED_PLAN_PORT} - General's 26B at 32,768, "
                              "General Uncensored's measured 30B MoE at 32,768, "
                              "Coding, Reflective Coach, Pictures & Screens and "
                              "Medical; it pauses the everyday model while it runs"),
                     "card": f"all three cards (pooled lane, port {POOLED_PLAN_PORT})",
                     "context": 32768},
                ],
                "heavy_pooled": (f"on demand, a heavy preset pauses the everyday "
                                 f"model and loads ONE model on the pooled lane on "
                                 f"port {POOLED_PLAN_PORT} across all the cards: "
                                 f"General (gemma4:26b-a4b-it-qat at 32,768), Coding "
                                 f"(qwen3-coder-30b-a3b-ud-q3-k-xl at 49,152 tokens), "
                                 f"Medical (medgemma:27b at 32,768), Reflective Coach "
                                 f"(gemma4:26b-a4b-it-qat at 32,768), Pictures & "
                                 f"Screens (gemma4:12b-it-qat at 32,768) and "
                                 f"General Uncensored "
                                 f"(huihui_ai/qwen3-abliterated:30b-a3b-instruct-"
                                 f"2507-q4_K_M at 32,768). "
                                 f"Each is too big for one card, which is why a heavy "
                                 f"preset splits one model across the cards; every "
                                 f"preset that is not heavy runs on the one everyday "
                                 f"lane, one model at a time."),
                "link_note": ("the third card likely sits on the B550 chipset through an "
                              "M.2 adapter: PCIe 3.0 x4, maybe x2. A slower link costs "
                              "loading time, not a lane: the everyday model is loaded "
                              "once across all three cards on the pooled lane, so the link is paid at "
                              "load, not per token."),
                "future_not_a_preset": ("The other downloaded uncensored MoE "
                                        "candidate - "
                                        "TrevorJS/gemma-4-26B-A4B-it-uncensored - "
                                        "is not a preset and no figure is claimed "
                                        "for it until it is measured on this PC. "
                                        "The huihui MoE that was a future candidate "
                                        "is General Uncensored's model since "
                                        "2026-11-19, measured at 19.520 GiB with "
                                        "0.000 GiB spilled. The uncensored 27B that "
                                        "row replaced is NOT deleted: it stays on "
                                        "this PC as the pooled lane's `creative` "
                                        "mode model."),            }}


def by_id(preset_id) -> Optional[Preset]:
    return _BY_ID.get(str(preset_id or ""))


def view() -> dict:
    """{"presets": [...], "old_ids_replaced": [...]} - what both apps render."""
    return {"presets": [p.view() for p in PRESETS],
            "old_ids_replaced": list(OLD_IDS),
            "hardware": hardware_block(),
            "recommendations": recommendations()}


def status_view() -> dict:
    """The GET answer without the PC's readiness fields (the HUD adds those)."""
    return {"found": f"{len(PRESETS)} focus presets", "presets": view()["presets"],
            "old_ids_replaced": list(OLD_IDS),
            "switch_path": SWITCH_ROUTE, "auto": False}
