"""The ten focus presets: ids, lanes, honest measurements, one rendered contract."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
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
    """2026-11-04. The 3-GPU rows were placed by BLIND array index and the words
    said "2080 SUPER #1 (card 1)" and "#2 (card 2)" - a number the owner cannot
    see anywhere - while the Coding row still described the 30B coding model as
    "the Coding lane (qwen3.5:4b helper)", wrong since 2026-11-02.

    The fix is the hybrid topology rule: everyday presets keep one lane per GPU
    (the everyday card, the monitor card, the headless card), and only the
    on-demand Coding preset pools the cards. Which card is which must come from
    a measured fact, so this drives a THREE-card answer where the monitor is on
    the THIRD card in the array - the case a blind index cannot get right.
    """
    real = P._detected_cards
    P._detected_cards = lambda: _three_card_block(None, False, True)
    try:
        rec = P.recommendations()
    finally:
        P._detected_cards = real
    three = rec["by_gpu_count"]["3"]
    check("the everyday rows are placed on the card with the most VRAM (the 2060), "
          "not on index 0 by luck",
          three["general"]["card_index"] == 0
          and three["reflect"]["card_index"] == 0
          and three["documents"]["card_index"] == 0,
          {k: v["card_index"] for k, v in three.items()})
    check("Fast goes to the card nvidia-smi says has the MONITOR - index 2 here, "
          "which is not the index the old table used",
          three["fast"]["card_index"] == 2, three["fast"])
    check("Agentic+Vision stays on the 12 GB everyday card - index 0 - because its "
          "9B weights plus the vision projector need about 7.00 GiB and an 8 GB "
          "headless twin has only 6.65 GiB free",
          three["agentic_vision"]["card_index"] == 0, three["agentic_vision"])
    check("the 2080 SUPER that has the monitor is named by its own PCI address and "
          "role, not by '#' and an array position - and the Agentic+Vision row names "
          "the everyday card it really runs on",
          "0000:0a:00.0" in three["fast"]["note"]
          and "card with the monitor" in three["fast"]["note"]
          and "0000:04:00.0" in three["agentic_vision"]["note"]
          and "12 GB" in three["agentic_vision"]["note"]
          and "2080 SUPER #" not in " ".join(r["note"] for r in three.values()),
          (three["fast"]["note"], three["agentic_vision"]["note"]))
    check("the Coding row names the REAL model on the POOLED lane, not the old "
          "'qwen3.5:4b helper' that stopped being true on 2026-11-02",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in three["coding"]["note"]
          and "11450" in three["coding"]["note"]
          and "qwen3.5:4b" not in three["coding"]["note"]
          and three["coding"]["card"] == "all the cards (pooled lane, port 11450)",
          three["coding"])
    plan = rec["three_gpu_plan"]
    check("the layout states BOTH halves of the hybrid rule: everyday is one lane "
          "per GPU, and only heavy Coding pools the cards on port 11450",
          "one lane per GPU" in plan["layout"]
          and "pooled" not in plan["layout"].split("only", 1)[0]
          and "port 11450" in plan["layout"]
          and "never one model split across three cards" not in plan["layout"],
          plan["layout"])
    check("... and the pooled exception is spelled out beside it, because a rule "
          "that leaves it unsaid is the one that went stale",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in plan["heavy_pooled"]
          and "11450" in plan["heavy_pooled"]
          and "too big for one" in plan["heavy_pooled"], plan["heavy_pooled"])
    check("the three plan cards are the three real cards, in role order",
          [c["role"].split(":")[0] for c in plan["cards"]]
          == ["everyday lane", "monitor card's lane", "headless card's lane"]
          and "0000:04:00.0" in plan["cards"][0]["card"]
          and "0000:0a:00.0" in plan["cards"][1]["card"]
          and "0000:07:00.0" in plan["cards"][2]["card"], plan["cards"])
    check("... and the headless row states the arithmetic instead of claiming a lane "
          "it cannot hold: Agentic+Vision needs about 7.00 GiB, the card has 6.65",
          "Agentic+Vision" in plan["cards"][2]["role"]
          and "7.00 GiB" in plan["cards"][2]["role"]
          and "6.65 GiB" in plan["cards"][2]["role"]
          and "Agentic + Vision stays on the everyday card" in plan["layout"],
          (plan["cards"][2]["role"], plan["layout"]))

    # A PC that does not report the display flag must not guess: the role falls
    # back to the first non-everyday card and the words SAY nothing measured it.
    P._detected_cards = lambda: _three_card_block(None, None, None)
    try:
        unknown = P.recommendations()
    finally:
        P._detected_cards = real
    three_unknown = unknown["by_gpu_count"]["3"]
    check("no display flag anywhere: nothing is claimed about which twin has the "
          "monitor, and the words say so",
          "monitor not reported by this PC" in three_unknown["fast"]["note"]
          and "card with the monitor" not in three_unknown["fast"]["note"],
          three_unknown["fast"]["note"])

    # With only the two cards this PC really has, the third role must not be
    # described as an installed card.
    P._detected_cards = lambda: {"count": 2, "source": "jarvis_hardware.detect()",
                                 "cards": _three_card_block(None, False, True)["cards"][:2]}
    try:
        two = P.recommendations()
    finally:
        P._detected_cards = real
    check("two cards installed: the headless role says it is not installed yet, "
          "instead of pretending a third card is there - and Agentic+Vision is not "
          "placed on it",
          "not installed yet" in two["three_gpu_plan"]["cards"][2]["card"]
          and two["by_gpu_count"]["3"]["agentic_vision"]["card_index"] == 0,
          two["three_gpu_plan"]["cards"][2])
    # This check's invariant is "never an invented array position", NOT a
    # particular card: origin/main moved Agentic+Vision to the everyday card
    # (it needs about 7.00 GiB and a headless 8 GB card has 6.65 GiB free), so
    # the role word it must print is the everyday one. The `card` field and the
    # `note`'s opening must still be the same words (2026-11-05).
    check("two cards installed: the Agentic+Vision ROW's own `card` is a role "
          "word too, never the old invented 'card 2' from _row()'s fallback "
          "(fixed 2026-11-05)",
          not re.match(r"^card \d+$",
                       two["by_gpu_count"]["3"]["agentic_vision"]["card"])
          and two["by_gpu_count"]["3"]["agentic_vision"]["note"].startswith(
              two["by_gpu_count"]["3"]["agentic_vision"]["card"]),
          two["by_gpu_count"]["3"]["agentic_vision"])
    check("... and NO 3-GPU row falls back to an array position at all: every "
          "row names a role (the coding row names the pooled lane)",
          all(not re.match(r"^card \d+$", row["card"])
              for row in two["by_gpu_count"]["3"].values()),
          {k: v["card"] for k, v in two["by_gpu_count"]["3"].items()})
    check("... every non-pooled 3-GPU row's card is the same role word its own "
          "note opens with, so the two fields cannot disagree",
          all(row["note"].startswith(row["card"])
              for row in two["by_gpu_count"]["3"].values()
              if row["preset"] not in ("coding", "medical")),
          {k: (v["card"], v["note"]) for k, v in two["by_gpu_count"]["3"].items()})
    check("the pooled lane's port is ONE number, pinned to the two modules that "
          "own it rather than typed three times",
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
    real = P._detected_cards
    P._detected_cards = lambda: {"count": 3,
                                 "source": "jarvis_hardware.detect()",
                                 "cards": cards}
    try:
        rec = P.recommendations()
    finally:
        P._detected_cards = real
    three = rec["by_gpu_count"]["3"]
    fast = three["fast"]
    check("the 3-GPU Fast row says where the monitor is; it is never labelled "
          "the monitor lane on a card with no monitor",
          "the monitor is on the everyday card instead" in fast["note"]
          and "the monitor is on the everyday card instead" in fast["card"]
          and "the card with the monitor" not in fast["note"]
          and "the card with the monitor" not in fast["card"], fast)
    plan = rec["three_gpu_plan"]["cards"]
    check("the plan's display row is not called the monitor card's lane when the "
          "monitor is on the everyday card",
          "the card with the monitor" not in plan[1]["card"]
          and "the monitor is on the everyday card instead" in plan[1]["card"]
          and "monitor card's lane" not in plan[1]["role"], plan[1])
    check("the headless row keeps the third card and names its own PCI address",
          "0000:0a:00.0" in plan[2]["card"], plan[2])
    check("... and Agentic+Vision, which cannot fit that 8 GB card, is on the "
          "everyday card and names ITS PCI address - never the headless one",
          three["agentic_vision"]["card_index"] == 0
          and "0000:04:00.0" in three["agentic_vision"]["card"],
          three["agentic_vision"])

    # The same reported case with only the two cards this PC has: the other
    # card gets the Fast lane and the third role stays honestly not installed.
    P._detected_cards = lambda: {"count": 2,
                                 "source": "jarvis_hardware.detect()",
                                 "cards": _three_card_block(True, False, False)["cards"][:2]}
    try:
        two = P.recommendations()
    finally:
        P._detected_cards = real
    rows = two["by_gpu_count"]["3"]
    check("two cards with the monitor on the everyday one: no 3-GPU row invents "
          "an array position",
          all(not re.match(r"^card \d+$", row["card"]) for row in rows.values()),
          {k: v["card"] for k, v in rows.items()})
    check("... the Fast row is the other card and says where the monitor is",
          "the monitor is on the everyday card instead" in rows["fast"]["card"]
          and "the card with the monitor" not in rows["fast"]["card"], rows["fast"])
    check("... and Agentic+Vision stays on the installed everyday card instead of "
          "claiming a third card it cannot fit",
          rows["agentic_vision"]["card_index"] == 0
          and "not installed yet" not in rows["agentic_vision"]["card"],
          rows["agentic_vision"])


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
    check("General is qwen3.5:9b on the 2060 at 196,608",
          gen.model == "qwen3.5:9b" and gen.context == 196608 and gen.lane == "main")
    cod = P.by_id("coding")
    check("Coding is heavy, on the pooled all-three-card lane",
          cod.model == "qwen3-coder-30b-a3b-ud-q3-k-xl" and cod.heavy_mode is True
          and cod.lane == "pooled"
          and cod.measured["tok_s"] == 83.8 and cod.measured["rubric"] == "6/6 coding rubric"
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
    check("... its words say the other models are PAUSED and name the honest cost, "
          "never that a lane is still arriving",
          "pauses the other lanes' models" in cod.cost
          and "NOT resident" in cod.worse and "come back" in cod.worse
          and "arriving" not in (cod.what + cod.worse + cod.cost)
          and "all three cards" in cod.heavy_words
          and "paused" in cod.heavy_words, (cod.cost, cod.worse, cod.heavy_words))
    check("Fast is qwen3.5:4b on the 2080 SUPER's coding lane at 16,384",
          P.by_id("fast").model == "qwen3.5:4b" and P.by_id("fast").lane == "coding"
          and P.by_id("fast").context == 16384
          and P.by_id("fast").measured["tok_s"] == 77.1
          and P.by_id("fast").measured["context"] == 65536)
    gu = P.by_id("general_uncensored")
    check("General Uncensored now names the measured abliterated Qwen3.5 ref",
          gu.pending is False
          and gu.model == "hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M"
          and gu.measured["tok_s"] == 45.6 and gu.measured["context_max"] == 262144
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
    av = fixture["presets"][3]
    check("Agentic+Vision now uses qwen3.5:9b on the 2060 at 16,384",
          av["id"] == "agentic_vision" and av["model"] == "qwen3.5:9b"
          and av["lane"]["key"] == "main" and av["context"] == 16384, av["model"])
    check("... its measured latency is labelled LATENCY, never tok/s",
          "tok_s" not in av["measured"]
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
    check("the four capability rows are all qwen3.5:9b on the 2060 (the long-context card)",
          [(p.model, p.lane, p.context) for p in caps.values()]
          == [("qwen3.5:9b", "main", 196608), ("qwen3.5:9b", "main", 32768),
              ("qwen3.5:9b", "main", 196608), ("qwen3.5:9b", "main", 196608)])
    check("... only the row whose window was measured carries measured figures",
          caps["pictures"].measured is None
          and caps["reflect"].measured["tok_s"] == 44.9
          and caps["documents"].measured["tok_s"] == 44.9
          and caps["browser"].measured["tok_s"] == 44.9)
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
          med.measured["tok_s"] == 9.27 and med.measured["cold_load_s"] == 46.8
          and med.measured["size_gib"] == 17.31 and med.measured["tools"] == 0
          and med.measured["spill_gib"] == 0.0, med.measured)
    check("... its words say the honest cost and refuse the doctor claim",
          "17.31" in med.cost and "46.8" in med.cost and "9.27" in med.cost
          and "three cards" in med.cost
          and "tool" in med.worse and "not a doctor" in med.worse.lower(), med.worse)
    check("... and it is appended LAST, so the nine older rows keep their order",
          P.PRESET_IDS[-1] == "medical" and len(P.PRESETS) == 10, P.PRESET_IDS)
    modes = P.pooled_modes()
    check("pooled_modes(): three named rows - Medical from its Preset row, and two "
          "measured candidates nothing points at",
          [m["key"] for m in modes] == ["medical", "gemma4-26b-a4b", "qwen3-vl-30b-a3b"]
          and modes[0]["model"] == med.model and modes[0]["num_ctx"] == med.context
          and [m["num_ctx"] for m in modes] == [32768, 32768, 32768]
          and all(m["needs_cards"] == 3 for m in modes), modes)
    check("... no preset points at either candidate: availability, not a default change",
          all(m["model"] not in {p.model for p in P.PRESETS} for m in modes[1:])
          and modes[1]["spill_allowance"] > 0 and modes[2]["spill_allowance"] > 0,
          [m["model"] for m in modes])
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
    check("2-GPU mapping: General/Coding/Agentic on the 2060, Fast on the fast card",
          rec["by_gpu_count"]["2"]["general"]["card_index"] == 0
          and rec["by_gpu_count"]["2"]["coding"]["card_index"] == 0
          and rec["by_gpu_count"]["2"]["agentic_vision"]["card_index"] == 0
          and rec["by_gpu_count"]["2"]["fast"]["card_index"] == 1,
          {k: v["card_index"] for k, v in rec["by_gpu_count"]["2"].items()})
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
    check("3-GPU confirmed layout: Fast on the display card, Agentic+Vision on the "
          "everyday card (it cannot fit an 8 GB card)",
          three["fast"]["card_index"] == 1 and three["agentic_vision"]["card_index"] == 0,
          {k: v["card_index"] for k, v in three.items()})
    check("3-GPU plan is lane-per-GPU on three RTX cards, and says the x4 link",
          rec["three_gpu_plan"]["confirmed"] is True
          and "lane per GPU" in rec["three_gpu_plan"]["layout"]
          and "PCIe 3.0 x4" in rec["three_gpu_plan"]["link_note"]
          and len(rec["three_gpu_plan"]["cards"]) == 3, rec.get("three_gpu_plan"))
    check("3-GPU layout states the HYBRID rule this repo really runs: everyday is "
          "one lane per GPU, heavy Coding is the pooled lane",
          "one lane per GPU" in rec["three_gpu_plan"]["layout"]
          and "pools the cards" in rec["three_gpu_plan"]["layout"]
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
          rec["by_gpu_count"]["2"]["general_uncensored"]["tok_s"] == 45.6
          and rec["by_gpu_count"]["2"]["general_uncensored"]["measured"] is True)

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
