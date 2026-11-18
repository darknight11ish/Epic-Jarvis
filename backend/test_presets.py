"""The ten focus presets: ids, lanes, honest measurements, one rendered contract."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
#: `jarvis_models.py` is one of the owner's own files; the published base carries
#: it, and the modules under test ask it for the one Ollama address (2026-11-18).
import _base  # noqa: E402
_base.put_on_path(_base.folder("jarvis_models.py"))
import jarvis_presets as P  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name + (f"\n        {detail}" if detail and not cond else ""))



def t_the_live_route_matches_the_generated_contract():
    """The GET route's deterministic blocks must be the committed fixture itself.

    Hardware detection is the one per-PC input: the fixture stores the cards of
    the machine that generated it, while the live route reads THIS PC. The test
    therefore feeds the route the fixture's own detected block, which makes the
    comparison exact and still catches every shape/word drift between the route
    and the contract both UIs read. It does not compare `chosen`: that is the
    owner's local state, deliberately not in the fixture.
    """
    import json
    fixture = json.loads((HERE / "fixtures" / "work_presets.json").read_text(encoding="utf-8"))
    real = P._detected_cards
    P._detected_cards = lambda: fixture["hardware"]["detected"]
    try:
        live = P.live_status()
    finally:
        P._detected_cards = real
    check("live presets are the fixture's presets, word for word",
          live["presets"] == fixture["presets"])
    check("live hardware is the fixture's nested hardware block, word for word",
          live["hardware"] == fixture["hardware"], live["hardware"])
    check("live recommendations are the fixture's recommendations, word for word",
          live["recommendations"] == fixture["recommendations"])
    check("live old_ids_replaced is the fixture's list",
          live["old_ids_replaced"] == fixture["old_ids_replaced"])
    check("there is no second, top-level questionnaire shape",
          "questionnaire" not in live, list(live))
    check("the route adds the live-only fields both readers use",
          live["chosen"] is None or isinstance(live["chosen"], str)
          and live["lane"]["key"] in ("main", "coding", None)
          and live["active_lane"]["key"] == live["lane"]["key"]
          and isinstance(live["auto"], bool) and live["auto"] is False
          and live["apply_path"] == "/api/work/apply")

def t_every_installed_card_reports_its_own_vram():
    """Defect B, measured 2026-11-04 and fixed the same day: the hardware block
    reported the card COUNT and every card's `vram_gib` was null, so the
    owner's preset screen showed two cards with blank sizes.

    The check above it only ever asserted field NAMES, so it passed happily on
    a null: that is the gate this function closes. It runs the REAL producer
    (`jarvis_presets._detect_cards()`) over the shape `jarvis_hardware.detect()`
    really builds a card row in - `"total_gib": s.total_mb / 1024`, and NOT
    `vram_gib` - which is why the reader used to find nothing: the producer
    looked for three keys, none of them the one on the row.

    A SYNTHETIC two-card fixture, never live data: the numbers are the audit's
    saved nvidia-smi sample of 2026-11-04 (2060 = 12,288 MiB, 2080 SUPER =
    8,192 MiB), so this runs the same on CI as on the owner's PC. Fails on the
    base commit (`[None, None]`, total 0) and passes after the fix
    (`[12.0, 8.0]`, total 20.0).
    """
    import jarvis_hardware

    rows = {"cards": [
        # Exactly detect()'s own row keys (jarvis_hardware.py's `rows.append`).
        {"name": "NVIDIA GeForce RTX 2060", "total_gib": 12288 / 1024,
         "vendor": "nvidia", "route": "CUDA", "compute": "7.5",
         "uuid": "GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee",
         "pci_id": "00000000:04:00.0", "monitor": False,
         "free_gib": (12288 - 11919) / 1024, "share_gib": None, "share_how": "",
         "used": True, "why_unused": "", "sources": ["nvidia-smi"], "index": 0,
         "key": "GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee"},
        {"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8192 / 1024,
         "vendor": "nvidia", "route": "CUDA", "compute": "7.5",
         "uuid": "GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6",
         "pci_id": "00000000:07:00.0", "monitor": True,
         "free_gib": (8192 - 6037) / 1024, "share_gib": None, "share_how": "",
         "used": True, "why_unused": "", "sources": ["nvidia-smi"], "index": 1,
         "key": "GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6"},
    ], "planned": [], "sources": {}, "found": "", "log": None}

    real = jarvis_hardware.detect
    jarvis_hardware.detect = lambda fresh=False: rows
    try:
        P._clear_detect_cache()
        block = P.hardware_block()["detected"]
    finally:
        jarvis_hardware.detect = real
        P._clear_detect_cache()

    cards = block["cards"]
    got = [c["vram_gib"] for c in cards]
    check("two cards on this PC: the block reports a count of two",
          block["count"] == 2 and len(cards) == 2, block)
    check("DEFECT B: every installed card reports its MEASURED VRAM in GiB, not null",
          got == [12.0, 8.0], got)
    check("DEFECT B: the two cards' VRAM adds up to a real number (20.0 GiB)",
          all(isinstance(v, (int, float)) for v in got)
          and round(sum(got), 1) == 20.0, got)
    check("... and each card keeps its own identity, so the sizes cannot swap",
          [(c["index"], c["name"], c["uuid"]) for c in cards]
          == [(0, "NVIDIA GeForce RTX 2060", "GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee"),
              (1, "NVIDIA GeForce RTX 2080 SUPER", "GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6")],
          cards)
    check("... and the two facts that tell two identical cards apart are carried "
          "through: the PCI address and nvidia-smi's display flag",
          [(c["pci_id"], c["monitor"]) for c in cards]
          == [("00000000:04:00.0", False), ("00000000:07:00.0", True)], cards)


def _three_card_block(*monitors):
    """A synthetic THREE-card detection in `_detected_cards()`'s own shape: the
    12 GB 2060 plus two identical 8 GB 2080 SUPERs, which is the only way to
    test that a role is picked from a FACT rather than from the array order."""
    names = ["NVIDIA GeForce RTX 2060", "NVIDIA GeForce RTX 2080 SUPER",
             "NVIDIA GeForce RTX 2080 SUPER"]
    pcis = ["0000:04:00.0", "0000:07:00.0", "0000:0a:00.0"]
    vrms = [12.0, 8.0, 8.0]
    return {"count": 3, "source": "jarvis_hardware.detect()",
            "cards": [{"index": i, "name": names[i], "vram_gib": vrms[i],
                       "uuid": f"GPU-{i}", "pci_id": pcis[i],
                       "monitor": monitors[i]} for i in range(3)]}


def t_three_gpu_rows_name_the_cards_by_role_not_by_index():
    """2026-11-18. TWO LANES, BOTH ACROSS ALL THREE CARDS, ONE MODEL AT A TIME.

    This check used to pin the older "hybrid" rule: everyday presets keep one
    lane per GPU and only the coding model pools the cards. That rule - and the
    words in `recommendations()` / `three_gpu_plan.layout` that stated it - is
    what kept the retired 11435 lane looking necessary. The 3-GPU plan now says
    what the code does: every named-lane row runs on the ONE everyday lane
    across all three cards, the heavy rows run on the pooled lane and pause the
    everyday model, and no row invents a per-card slot or an array position.

    The role words are still checked against a real three-card answer, because
    the pool's own words must not number identical cards.
    """
    real = P._detected_cards
    P._detected_cards = lambda: _three_card_block(None, False, True)
    try:
        rec = P.recommendations()
    finally:
        P._detected_cards = real
    three = rec["by_gpu_count"]["3"]
    # The everyday lane is ONE card again, and its role words come from the same
    # detected-card table the recommendations used.
    _cards = _three_card_block(None, False, True)["cards"]
    everyday_words = P._role_words(_cards, P._card_roles(_cards), "main")
    pooled_words = f"all the cards (pooled lane, port {P.POOLED_PLAN_PORT})"
    check("every named-lane 3-GPU row names the ONE everyday card",
          all(three[k]["card"] == everyday_words
              for k in ("general_uncensored", "fast",
                        "agentic_vision", "documents", "browser")),
          {k: three[k]["card"] for k in three})
    check("... and every heavy row - General included - says the pooled lane on "
          "all the cards",
          all(three[k]["card"] == pooled_words
              for k in ("general", "coding", "reflect", "pictures", "medical")),
          {k: three[k]["card"] for k in three})
    check("... General's row names the 32,768 window it really runs, and every "
          "heavy row says it pauses the everyday model (never 'the other lanes')",
          "32,768" in three["general"]["note"]
          and all("pauses the everyday model" in three[k]["note"]
                  for k in ("general", "coding", "reflect", "pictures", "medical")),
          {k: three[k]["note"] for k in three})
    check("... the rows never print an invented array position ('card 2')",
          all(not re.match(r"^card \d+$", row["card"]) for row in three.values()),
          {k: v["card"] for k, v in three.items()})
    check("... and every named-lane row's `card` is the same words its own note "
          "opens with (the heavy rows open with the model's name instead)",
          all(row["note"].startswith(row["card"]) for row in three.values()
              if P.by_id(row["preset"]).lane != "pooled"),
          {k: (v["card"], v["note"]) for k, v in three.items()})
    plan = rec["three_gpu_plan"]
    check("the 3-GPU plan states the ONE-preset-at-a-time rule, not 'one lane per GPU'",
          "one preset's model is loaded at a time" in plan["layout"].lower()
          and "one lane per gpu" not in plan["layout"].lower()
          and str(P.POOLED_PLAN_PORT) in plan["layout"]
          and "all three" in plan["layout"], plan["layout"])
    check("... and it says any preset may use all three cards, and that the heavy "
          "presets pause the everyday model",
          "any preset may use all three" in plan["layout"]
          and "pooled" in plan["layout"]
          and "pauses the everyday model" in plan["layout"], plan["layout"])
    check("... the pooled exception is spelled out beside it, because a rule that "
          "leaves it unsaid is the one that went stale",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in plan["heavy_pooled"]
          and str(P.POOLED_PLAN_PORT) in plan["heavy_pooled"]
          and "too big for one" in plan["heavy_pooled"], plan["heavy_pooled"])
    check("... and the plan's cards are the two real lanes: the one-card "
          "everyday lane and the all-three-card pooled lane",
          [c["role"].split(":")[0] for c in plan["cards"]]
          == ["everyday lane", "pooled lane, started on demand"]
          and plan["cards"][0]["card"].startswith("NVIDIA GeForce RTX 2060")
          and plan["cards"][1]["card"].startswith("all three cards"),
          plan["cards"])
    check("... with no invented headless lane from the old one-card-per-GPU plan",
          "headless" not in json.dumps(plan["cards"]).lower()
          and "one lane per GPU" not in plan["layout"], plan["cards"])

    # A PC that cannot report the display flag: the plan makes no claim about
    # which card has the monitor, so there is nothing to get wrong.
    P._detected_cards = lambda: _three_card_block(None, None, None)
    try:
        unknown = P.recommendations()
    finally:
        P._detected_cards = real
    check("no display flag anywhere: the plan never guesses which card has the "
          "monitor", "monitor" not in json.dumps(unknown["three_gpu_plan"]).lower(),
          unknown["three_gpu_plan"])

    # Only the two cards this PC really has: the plan is about the lanes, so a
    # missing third card must not become an invented one.
    P._detected_cards = lambda: {"count": 2, "source": "jarvis_hardware.detect()",
                                 "cards": _three_card_block(None, False, True)["cards"][:2]}
    try:
        two = P.recommendations()
    finally:
        P._detected_cards = real
    three_two = two["by_gpu_count"]["3"]
    check("two cards installed: no 3-GPU row falls back to an array position, and "
          "the plan names the lanes rather than a card that is not there",
          all(not re.match(r"^card \d+$", row["card"]) for row in three_two.values())
          and all(not re.match(r"^card \d+$", c["card"] or "")
                  for c in two["three_gpu_plan"]["cards"]),
          {k: v["card"] for k, v in three_two.items()})
    check("... and the pooled lane's port is ONE number, pinned to the two modules "
          "that own it rather than typed three times",
          P.POOLED_PLAN_PORT == 11450, P.POOLED_PLAN_PORT)
    import jarvis_big_coder as BC
    import jarvis_model_lanes as L
    check("... and it is the lane module's POOLED_PORT and the big-coder's BIG_PORT",
          P.POOLED_PLAN_PORT == L.POOLED_PORT == BC.BIG_PORT,
          (P.POOLED_PLAN_PORT, L.POOLED_PORT, BC.BIG_PORT))


def t_a_monitor_on_the_everyday_card_is_never_called_a_monitor_lane():
    """2026-11-05. `_card_roles()` took `main` = highest VRAM and then searched
    only `rest` for `monitor is True`. On a PC whose main card HAS the monitor
    that search found nothing, so the display role fell through to `rest[0]` -
    a card with NO monitor - and `_role_words(..., "display")` described that
    card as "the card with no monitor" while the plan called the same row the
    monitor lane. The monitor is now searched for on EVERY card.

    When the monitor is on the everyday card, the Fast/Live lane still gets its
    own card (the model does not need the screen) and the words say where the
    monitor really is. The 12 GB card with `monitor=True` is the reported case.
    """
    cards = _three_card_block(True, False, False)["cards"]
    roles = P._card_roles(cards)
    words = P._role_words(cards, roles, "display")
    check("the monitor on the everyday card is FOUND, not silently missed",
          roles["monitor_on_main"] is True and roles["main"] == 0, roles)
    check("the Fast/Live lane still has a card of its own (the monitor card is "
          "already the everyday card)",
          roles["display"] == 1, roles)
    check("... and its words say where the monitor is instead of claiming this "
          "card has it",
          "the card with the monitor" not in words
          and "the card with no monitor" not in words
          and "the monitor is on the everyday card instead" in words, words)
    # The 3-GPU plan no longer places a model on one physical card, so there is
    # no per-card role for the rows to get wrong: every named-lane row is the
    # everyday lane across all three cards. The helper-level facts above still
    # matter (a lane would have to be drawn on ONE card again for a monitor claim
    # to be needed), and the plan itself makes no monitor claim at all.
    real = P._detected_cards
    P._detected_cards = lambda: {"count": 3,
                                 "source": "jarvis_hardware.detect()",
                                 "cards": cards}
    try:
        rec = P.recommendations()
    finally:
        P._detected_cards = real
    three = rec["by_gpu_count"]["3"]
    check("no 3-GPU row is placed on a single card any more, so no row can be "
          "labelled the monitor lane wrongly",
          all("the monitor" not in row["card"] for row in three.values())
          and all("the monitor" not in row["note"] for row in three.values()),
          {k: v["card"] for k, v in three.items()})
    check("... and the plan's lane rows make no claim about which card has the "
          "monitor", "monitor" not in json.dumps(rec["three_gpu_plan"]).lower(),
          rec["three_gpu_plan"])


def t_every_pooled_preset_carries_a_measured_dict():
    """2026-11-18: a preset that takes all three cards must not be a guess.

    `heavy_mode` is a real cost - the everyday lane is paused while the model
    loads - so every pooled row has to carry the numbers that decision was made
    from: a decode rate, the loaded size, the spill it really measured, its cold
    load and a `source` saying where those came from. The row's own `mode` must
    also be a row `pooled_modes()` publishes, at the same model and window, or
    the lane would load a model the preset never named.
    """
    pooled = [p for p in P.PRESETS if p.lane == "pooled"]
    check("FIVE presets take all three cards today: General (joined 2026-11-18), "
          "Coding, Reflective Coach, Pictures & Screens and Medical",
          [p.id for p in pooled] == ["general", "coding", "reflect",
                                     "pictures", "medical"],
          [p.id for p in pooled])
    check("... every one of them is heavy_mode",
          all(p.heavy_mode for p in pooled),
          [(p.id, p.heavy_mode) for p in pooled])
    check("... and every one carries a measured dict, never an empty guess",
          all(isinstance(p.measured, dict) and p.measured for p in pooled),
          [(p.id, p.measured) for p in pooled])
    required = ("tok_s", "tok_s_on", "tok_s_note", "size_gib", "spill_gib",
                "cold_load_s", "source")
    check("... with the figures a three-card decision needs in EVERY pooled row: "
          + ", ".join(required),
          all(all(k in p.measured for k in required) for p in pooled),
          [(p.id, sorted(p.measured)) for p in pooled])
    check("... and each source names the date it was measured, so no number here is "
          "an unattributable estimate",
          all(re.search(r"20\d\d-\d\d-\d\d", p.measured["source"]) for p in pooled),
          [(p.id, p.measured.get("source")) for p in pooled])
    modes = {m["key"]: m for m in P.pooled_modes()}
    named = [p for p in pooled if p.mode]
    check("four of the five name their own pooled mode (General shares Reflective "
          "Coach's measured row), and Coding keeps the lane's own default",
          [p.id for p in named] == ["general", "reflect", "pictures", "medical"]
          and P.by_id("coding").mode == "", [p.id for p in named])
    check("... every named mode is a row pooled_modes() publishes, at the SAME model "
          "and window the preset row states",
          all(p.mode in modes and modes[p.mode]["model"] == p.model
              and modes[p.mode]["num_ctx"] == p.context for p in named),
          [(p.id, p.mode) for p in named])
    check("... so no preset can point at a mode the lane would refuse to load",
          all(m["needs_cards"] == 3 for m in P.pooled_modes()))
    moved = (P.by_id("reflect"), P.by_id("pictures"))
    check("... and both moved rows quote their own numbers in plain words, not only "
          "in a dict the owner never sees (Reflective Coach's is the 2026-11-17 run; "
          "Pictures & Screens is the 2026-11-18 real-lane run that replaced the "
          "spilling 30B, a single run, so it carries no range)",
          all(p.measured["tok_s_on"] in ("2026-11-17", "2026-11-18") for p in moved)
          and all(str(p.measured["tok_s"]) in p.measured["tok_s_note"] for p in moved)
          and all(str(p.measured["size_gib"]) in p.cost
                  or f"{p.measured['size_gib']:.2f}" in p.cost for p in moved)
          and all("all three cards" in p.heavy_words for p in moved),
          [(p.id, p.measured["tok_s_note"]) for p in moved])


def main() -> int:
    fixture = json.loads((HERE / "fixtures" / "work_presets.json").read_text(encoding="utf-8"))
    check("exactly ten presets, in the owner's order",
          [p["id"] for p in fixture["presets"]]
          == ["general", "general_uncensored", "coding", "agentic_vision", "fast",
              "reflect", "pictures", "documents", "browser", "medical"],
          [p["id"] for p in fixture["presets"]])
    check("the five old ids are named as replaced",
          fixture["old_ids_replaced"] == ["everyday", "coding", "admin", "long", "specialist"])
    for p in fixture["presets"]:
        check(f"{p[chr(105)+chr(100)]}: lane is main, coding or the pooled both-card "
              f"lane, with its real port",
              p["lane"]["key"] in ("main", "coding", "pooled")
              and p["lane"]["port"] == {"main": 11436, "coding": 11435,
                                        "pooled": 11450}[p["lane"]["key"]], p["lane"])
        check(f"{p['id']}: every rendered word is a non-empty string",
              all(isinstance(p[k], str) and p[k] for k in ("title", "focus", "what", "cost", "worse")))
        check(f"{p['id']}: apply is one asked action, never automatic",
              p["apply"]["action"] == "Use this preset" and p["apply"]["auto"] is False
              and p["apply"]["apply_route"] == "/api/work/apply")
        check(f"{p['id']}: model and context are stated", bool(p["model"]) and int(p["context"]) > 0)
    gen = P.by_id("general")
    check("General is the 26B at 32,768 on the POOLED lane - a heavy preset, "
          "because the everyday lane's one 12 GB card cannot hold it",
          gen.model == "gemma4:26b-a4b-it-qat" and gen.context == 32768
          and gen.lane == "pooled" and gen.heavy_mode is True
          and gen.mode == "gemma4-26b-a4b"
          and gen.measured["tok_s"] == 25.4
          and gen.measured["tok_s_on"] == "2026-11-17"
          and gen.measured["size_gib"] == 15.501
          and gen.measured["vram_gib"] == 14.82
          and gen.measured["spill_gib"] == 0.681
          and gen.measured["cold_load_s"] == 49.9
          and gen.measured["context_measured"] == 32768,
          (gen.model, gen.measured))
    check("... its speed is the DATED 2026-11-17 run, and the note says what was "
          "measured and that the LOW end of two runs is the figure",
          gen.measured["tok_s_on"] == "2026-11-17"
          and "0.68 GiB spill" in gen.measured["tok_s_note"]
          and "all three cards" in gen.measured["tok_s_note"]
          and "32,768 context" in gen.measured["tok_s_note"]
          and "25.4-36.5" in gen.measured["tok_s_note"], gen.measured["tok_s_note"])
    check("... and its words say HEAVY MODE on the pooled lane and quote that "
          "measured figure, with no two-card claim",
          "HEAVY MODE" in gen.cost and "pooled lane" in gen.cost.lower()
          and "15.50" in gen.cost and "0.68 GiB" in gen.cost and "25.4" in gen.cost
          and "6.37" not in gen.cost and "46.10" not in gen.cost, gen.cost)
    check("... and it tells the owner the everyday lane is paused while it runs",
          "everyday" in (gen.heavy_words or "")
          and "paused" in gen.heavy_words, gen.heavy_words)
    check("... and its words say plainly what is NOT measured (picture quality, "
          "general/tool-calling/vision rubric)",
          "NOT measured" in gen.worse and "picture quality" in gen.worse
          and "rubric" in gen.worse, gen.worse)
    cod = P.by_id("coding")
    check("Coding is heavy, on the pooled all-three-card lane",
          cod.model == "qwen3-coder-30b-a3b-ud-q3-k-xl" and cod.heavy_mode is True
          and cod.lane == "pooled"
          and cod.measured["tok_s"] == 40.3 and cod.measured["rubric"] == "6/6 coding rubric"
          and cod.measured["size_gib"] == 16.2 and cod.measured["cold_load_s"] == 31.6
          and "ALL THREE GPUs" in cod.cost, cod.model)
    check("Coding asks for the 49,152-token window measured on all three cards, "
          "with zero spill recorded against it",
          cod.context == 49152
          and cod.measured["context_measured"] == 49152
          and cod.measured["context_zero_spill"] == 49152
          and cod.measured["spill_gib"] == 0.0
          and "49,152" in cod.cost and "zero CPU spill" in cod.cost,
          (cod.context, cod.measured))
    check("... its words say the everyday model is PAUSED and name the honest cost, "
          "never that a lane is still arriving",
          "pauses the everyday model" in cod.cost
          and "NOT resident" in cod.worse and "comes back" in cod.worse
          and "arriving" not in (cod.what + cod.worse + cod.cost)
          and "all three cards" in cod.heavy_words
          and "paused" in cod.heavy_words, (cod.cost, cod.worse, cod.heavy_words))
    check("Fast is qwen3.5:4b on the everyday lane at 16,384, never a second card",
          P.by_id("fast").model == "qwen3.5:4b" and P.by_id("fast").lane == "main"
          and P.by_id("fast").context == 16384
          and P.by_id("fast").measured["tok_s"] == 83.2
          and P.by_id("fast").measured["context"] == 65536
          and "no separate fast card" in P.by_id("fast").what,
          (P.by_id("fast").lane, P.by_id("fast").what))
    gu = P.by_id("general_uncensored")
    check("General Uncensored now names the measured abliterated Qwen3.5 ref",
          gu.pending is False
          and gu.model == "hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M"
          and gu.measured["tok_s"] == 42.6 and gu.measured["context_max"] == 262144
          and gu.measured["licence"] == "Apache-2.0", gu.model)
    check("... its words say one-run rubric, not independent, and the Homebrew nit",
          "6/6" in gu.measured["source"] and "not independent" in gu.measured["source"]
          and "Homebrew" in gu.worse)
    check("Agentic+Vision is qwen3.5:9b on the 2060 (never the display card)",
          P.by_id("agentic_vision").model == "qwen3.5:9b"
          and P.by_id("agentic_vision").lane == "main" and P.by_id("agentic_vision").context == 16384)
    text_measured = [p for p in fixture["presets"] if p["measured"]
                     and "tok_s" in p["measured"]]
    check("measured tok/s is present only where that measurement exists",
          all(isinstance(p["measured"]["tok_s"], (int, float)) for p in text_measured),
          [p["id"] for p in text_measured])
    # The owner's one ask (2026-11-17): the speed in the list is DATED. Every
    # measured row names the live-lane run it came from and says in words what
    # was measured; a row repeated twice carries the RANGE and the LOW end is
    # the number the list shows, so the row can never flatter itself.
    check("every measured row dates its speed and says what was measured",
          all(p["measured"].get("tok_s_on") in ("2026-11-17", "2026-11-18")
              and isinstance(p["measured"].get("tok_s_note"), str)
              and p["measured"]["tok_s_note"] for p in text_measured),
          [(p["id"], p["measured"].get("tok_s_on")) for p in text_measured])
    ranged = {p["id"]: p["measured"] for p in text_measured
              if "two runs" in p["measured"].get("tok_s_note", "")}
    check("... the rows run twice carry their range, and tok_s is its LOW end "
          "(General's 26B row is the same twice-measured pooled load as "
          "Reflective Coach's, so it carries the range too; Pictures & Screens was "
          "measured once on 2026-11-18, when its whole model changed, so it is not "
          "one of the ranged rows and says so in its note)",
          set(ranged) == {"general", "coding", "reflect", "medical"}
          and all(re.search(r"read " + re.escape(str(m["tok_s"])) + r"-",
                            m["tok_s_note"]) for m in ranged.values())
          and "one run" in P.by_id("pictures").measured["tok_s_note"],
          {k: v.get("tok_s_note") for k, v in ranged.items()})
    av = fixture["presets"][3]
    check("Agentic+Vision now uses qwen3.5:9b on the 2060 at 16,384",
          av["id"] == "agentic_vision" and av["model"] == "qwen3.5:9b"
          and av["lane"]["key"] == "main" and av["context"] == 16384, av["model"])
    check("... its measured latency is labelled LATENCY in its own receipt, and its "
          "dated 2026-11-17 decode rate sits beside it",
          av["measured"]["tok_s"] == 40.1
          and av["measured"]["tok_s_on"] == "2026-11-17"
          and "LATENCY" in av["measured"]["source"]
          and av["measured"]["vision_latency_s"]["browser_first_token"] == 4.45
          and av["measured"]["vision_latency_s"]["desktop_cold_total"] == 70.2,
          av["measured"])
    check("... the qwen3-vl fallback note says it gave no answer on the desktop UI",
          av["measured"]["fallback"]["model"] == "qwen3-vl:8b-thinking"
          and "no answer" in av["measured"]["fallback"]["note"])
    check("... and both honest words say pictures are accepted",
          "accepts pictures" in av["cost"])

    caps = {pid: P.by_id(pid) for pid in ("reflect", "pictures", "documents", "browser")}
    check("the two capability rows that stayed on one card are still qwen3.5:9b on the "
          "2060 (the long-context card)",
          [(caps[k].model, caps[k].lane, caps[k].context)
           for k in ("documents", "browser")]
          == [("qwen3.5:9b", "main", 196608), ("qwen3.5:9b", "main", 196608)],
          [(caps[k].model, caps[k].lane, caps[k].context)
           for k in ("documents", "browser")])
    check("... and both keep the General setup's measured figures",
          caps["documents"].measured["tok_s"] == 38.1
          and caps["browser"].measured["tok_s"] == 38.1)
    check("2026-11-18: Reflective Coach moved to the measured gemma4-26b-a4b pooled "
          "mode - all three cards, heavy mode, its own 32,768-token window",
          caps["reflect"].model == "gemma4:26b-a4b-it-qat"
          and caps["reflect"].lane == "pooled" and caps["reflect"].heavy_mode is True
          and caps["reflect"].mode == "gemma4-26b-a4b"
          and caps["reflect"].context == 32768,
          (caps["reflect"].model, caps["reflect"].lane, caps["reflect"].mode))
    check("... with the 2026-11-09 bench receipt copied, the measured spill included "
          "and never rounded away",
          caps["reflect"].measured["tok_s"] == 25.4
          and caps["reflect"].measured["tok_s_on"] == "2026-11-17"
          and caps["reflect"].measured["size_gib"] == 15.5
          and caps["reflect"].measured["spill_gib"] == 0.68
          and caps["reflect"].measured["cold_load_s"] == 52.0,
          caps["reflect"].measured)
    check("2026-11-18: Pictures & Screens runs the gemma4-12b pooled mode on all three "
          "cards at a 32,768-token window - because the 30B vision model it named that "
          "same day was measured spilling 2.24 GiB on the real lane and 1.65 GiB even "
          "at 16,384, which no window can fix",
          caps["pictures"].model == "gemma4:12b-it-qat"
          and caps["pictures"].lane == "pooled" and caps["pictures"].heavy_mode is True
          and caps["pictures"].mode == "gemma4-12b"
          and caps["pictures"].context == 32768,
          (caps["pictures"].model, caps["pictures"].lane, caps["pictures"].mode))
    check("... the 30B model the row first named is nowhere in the shipped rows any "
          "more, and no preset names it",
          all(p.model != "qwen3-vl:30b-a3b-instruct" for p in P.PRESETS)
          and all(m["model"] != "qwen3-vl:30b-a3b-instruct"
                  for m in P.pooled_modes()))
    check("... with the 2026-11-18 lane measurement copied: 8.696 GiB resident, all "
          "of it in video memory (0 B spilled), a 20.3 s cold load and 28.08 tok/s",
          caps["pictures"].measured["tok_s"] == 28.08
          and caps["pictures"].measured["tok_s_on"] == "2026-11-18"
          and caps["pictures"].measured["size_gib"] == 8.696
          and caps["pictures"].measured["vram_gib"] == 8.696
          and caps["pictures"].measured["spill_gib"] == 0.0
          and caps["pictures"].measured["cold_load_s"] == 20.3,
          caps["pictures"].measured)
    check("... and the row carries the picture-reading evidence, not a quality claim "
          "it cannot support",
          "picture_test" in caps["pictures"].measured
          and "30B gave" in caps["pictures"].measured["picture_test"]
          and caps["pictures"].measured["quality_general"].startswith("21/24")
          and "not a score" in caps["pictures"].worse
          and "0 B spilled" in caps["pictures"].cost, caps["pictures"].measured)

    check("Reflective Coach is a model choice only, never a therapist claim",
          "not a therapist" in caps["reflect"].worse
          and "no therapy record" in caps["reflect"].worse)
    med = P.by_id("medical")
    check("Medical Expert is the tenth row: medgemma:27b on the pooled all-three-card "
          "lane at its measured 32,768",
          med.model == "medgemma:27b" and med.lane == "pooled"
          and med.context == 32768 and med.heavy_mode is True
          and med.mode == "medical", (med.model, med.lane, med.context))
    check("... its measured figures are the 2026-11-09 receipt, with no tool calling "
          "claimed",
          med.measured["tok_s"] == 11.4
          and med.measured["tok_s_on"] == "2026-11-17"
          and med.measured["cold_load_s"] == 46.8
          and med.measured["size_gib"] == 17.31 and med.measured["tools"] == 0
          and med.measured["spill_gib"] == 0.0, med.measured)
    check("... its words say the honest cost and refuse the doctor claim",
          "17.31" in med.cost and "46.8" in med.cost and "9.27" in med.cost
          and "three cards" in med.cost
          and "tool" in med.worse and "not a doctor" in med.worse.lower(), med.worse)
    check("... and it is appended LAST, so the nine older rows keep their order",
          P.PRESET_IDS[-1] == "medical" and len(P.PRESETS) == 10, P.PRESET_IDS)
    modes = P.pooled_modes()
    check("pooled_modes(): three named rows - Medical from its Preset row, and the two "
          "measured candidates Reflective Coach and Pictures & Screens now apply",
          [m["key"] for m in modes] == ["medical", "gemma4-26b-a4b", "gemma4-12b"]
          and modes[0]["model"] == med.model and modes[0]["num_ctx"] == med.context
          and [m["num_ctx"] for m in modes] == [32768, 32768, 32768]
          and all(m["needs_cards"] == 3 for m in modes), modes)
    check("... the two candidates are exactly the models the two moved presets run, "
          "and the 12B row's measured spill allowance is ZERO (it was measured with "
          "nothing spilled) while the 26B keeps its measured 0.68 GiB",
          modes[1]["model"] == P.by_id("reflect").model
          and modes[2]["model"] == P.by_id("pictures").model
          and modes[1]["spill_allowance"] == round(0.681 * 1024 ** 3)
          and modes[2]["spill_allowance"] == 0,
          [m["model"] for m in modes])
    check("... so the pictures apply is read back with the zero-spill rule, not a "
          "2.24 GiB allowance for a replaced model",
          P._preset_spill_allowance(P.by_id("pictures")) == 0
          and "0 B spilled" in modes[2]["measured_words"],
          (P._preset_spill_allowance(P.by_id("pictures")),
           modes[2]["measured_words"]))
    rec3 = P.recommendations()["by_gpu_count"]["3"]
    check("every preset has a 3-GPU recommendation row (the id-keyed GPU dicts cover the catalogue)",
          set(rec3) == set(P.PRESET_IDS), sorted(rec3))
    check("... Medical's 3-GPU row is heavy-mode and names its model and window",
          "medgemma:27b" in rec3["medical"]["note"]
          and "32768" in rec3["medical"]["note"].replace(",", "")
          and rec3["medical"]["card"] == "all the cards (pooled lane, port 11450)",
          rec3["medical"])

    hw = fixture["hardware"]
    # The exact key set is pinned, not "at least these": the two facts added on
    # 2026-11-04 (`pci_id`, `monitor`) are what let a plan name a card instead of
    # numbering it, and a block that quietly stopped carrying them would make
    # every role choice a guess again. The pin is the whole set, so a removal
    # fails here as loudly as an addition.
    check("hardware: detected cards come from detect() and carry name/VRAM/index, "
          "plus the PCI address and display flag that tell two identical cards apart",
          hw["detected"]["source"] == "jarvis_hardware.detect()"
          and isinstance(hw["detected"]["count"], int)
          and all(set(c) == {"index", "name", "vram_gib", "uuid", "pci_id", "monitor"}
                  for c in hw["detected"]["cards"])
          and all(isinstance(c["pci_id"], str)
                  and (c["monitor"] is None or isinstance(c["monitor"], bool))
                  for c in hw["detected"]["cards"]),
          hw["detected"])
    t_every_installed_card_reports_its_own_vram()
    check("questionnaire: the ten focus ids and the four priorities",
          hw["questionnaire"]["focus_choices"] == [p["id"] for p in fixture["presets"]]
          and hw["questionnaire"]["priority_choices"] == ["speed", "quality", "long_context", "vision"]
          and hw["questionnaire"]["answers"] is None, hw["questionnaire"])
    rec = fixture["recommendations"]
    check("recommendations exist for exactly 1, 2 and 3 GPUs",
          sorted(rec["by_gpu_count"]) == ["1", "2", "3"], sorted(rec["by_gpu_count"]))
    for n in ("1", "2", "3"):
        rows = rec["by_gpu_count"][n]
        check(f"{n} GPU: one row per preset with model/card_index/context",
              sorted(rows) == sorted(p["id"] for p in fixture["presets"])
              and all(r["model"] and isinstance(r["card_index"], int)
                      and isinstance(r["context"], int) for r in rows.values()), rows)
        check(f"{n} GPU: unmeasured rows are labelled",
              all(r["measured"] or r["best_effort_not_tested"] for r in rows.values()),
              {k: (v["measured"], v["best_effort_not_tested"]) for k, v in rows.items()})
    check("2-GPU mapping: General is a heavy pooled-lane row like Coding, so its "
          "row says so; everything else shares the one everyday lane",
          rec["by_gpu_count"]["2"]["general"]["card"].startswith(
              "all three cards (pooled lane")
          and rec["by_gpu_count"]["2"]["general"]["measured"] is True
          and rec["by_gpu_count"]["2"]["documents"]["measured"] is True
          and rec["by_gpu_count"]["2"]["fast"]["measured"] is True
          and {v["card_index"] for v in rec["by_gpu_count"]["2"].values()} == {0},
          {k: (v["card_index"], v["best_effort_not_tested"])
           for k, v in rec["by_gpu_count"]["2"].items()})
    check("1- and 3-GPU rows are best effort, not tested",
          all(r["best_effort_not_tested"] and not r["measured"]
              for n in ("1", "3") for r in rec["by_gpu_count"][n].values()),
          "1/3 GPU rows")
    three = rec["by_gpu_count"]["3"]
    # Both sides rewrote this block, and they disagree about ONE fact: where
    # Agentic+Vision goes on a 3-GPU PC. origin/main moved it to the everyday
    # card with a measured reason - the 9B weights plus the vision projector
    # need about 7.00 GiB and a headless 8 GB card has 6.65 GiB free - after
    # this branch was written against the older headless placement (2026-11-05).
    # main's measured placement wins; this branch's two NEW invariants are kept
    # and pointed at it, so neither side's paragraph is lost.
    check("the fixture's 3-GPU rows never print an invented array position "
          "('card 2'), because every row carries a role word (fixed 2026-11-05)",
          all(not re.match(r"^card \d+$", row["card"]) for row in three.values()),
          {k: v["card"] for k, v in three.items()})
    check("... and the Agentic+Vision row's card words are the same words its own "
          "note opens with, so no row names a card its note contradicts",
          three["agentic_vision"]["note"].startswith(three["agentic_vision"]["card"]),
          three["agentic_vision"])
    check("3-GPU confirmed layout: every named-lane row is the ONE everyday card, "
          "and every heavy row - General included - is the pooled lane",
          three["fast"]["card"] == three["agentic_vision"]["card"]
          == three["documents"]["card"]
          and three["general"]["card"].startswith("all the cards (pooled lane")
          and three["coding"]["card"].startswith("all the cards (pooled lane"),
          {k: v["card"] for k, v in three.items()})
    check("3-GPU plan states the ONE-preset-at-a-time rule on all three cards, and "
          "says the x4 link",
          rec["three_gpu_plan"]["confirmed"] is True
          and "one preset's model is loaded at a time" in rec["three_gpu_plan"]["layout"].lower()
          and "PCIe 3.0 x4" in rec["three_gpu_plan"]["link_note"]
          and len(rec["three_gpu_plan"]["cards"]) == 2, rec.get("three_gpu_plan"))
    check("3-GPU layout says any preset may use all three cards and that only the "
          "heavy ones pool them on the pooled lane",
          "any preset may use all three" in rec["three_gpu_plan"]["layout"]
          and "one lane per GPU" not in rec["three_gpu_plan"]["layout"]
          and str(P.POOLED_PLAN_PORT) in rec["three_gpu_plan"]["layout"],
          rec["three_gpu_plan"]["layout"])
    check("the stale 'never one model split across three cards' claim is gone, and "
          "so is the 'qwen3.5:4b helper' Coding was never since 2026-11-02",
          "never one model split" not in json.dumps(rec)
          and "qwen3.5:4b helper" not in json.dumps(rec), rec["three_gpu_plan"]["layout"])
    check("the Coding preset is described as the 30B pooled model in BOTH the 2- and "
          "3-GPU rows, because it is one preset with one behaviour",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in rec["by_gpu_count"]["3"]["coding"]["note"]
          and str(P.POOLED_PLAN_PORT) in rec["by_gpu_count"]["2"]["coding"]["note"]
          and "main model on the 2060" not in rec["by_gpu_count"]["2"]["coding"]["note"],
          rec["by_gpu_count"]["2"]["coding"]["note"])
    check("the pooled Qwen3.8-27B 28 GB is named as future-only, not a preset",
          "not a preset" in rec["three_gpu_plan"]["future_not_a_preset"]
          and "28 GB" in rec["three_gpu_plan"]["future_not_a_preset"])
    check("General Uncensored is measured in the 2-GPU rows now",
          rec["by_gpu_count"]["2"]["general_uncensored"]["tok_s"] == 42.6
          and rec["by_gpu_count"]["2"]["general_uncensored"]["measured"] is True)

    t_every_pooled_preset_carries_a_measured_dict()
    t_three_gpu_rows_name_the_cards_by_role_not_by_index()
    t_a_monitor_on_the_everyday_card_is_never_called_a_monitor_lane()
    t_the_live_route_matches_the_generated_contract()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
