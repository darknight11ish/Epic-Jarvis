"""The nine focus presets: ids, lanes, honest measurements, one rendered contract."""
import json
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

def main() -> int:
    fixture = json.loads((HERE / "fixtures" / "work_presets.json").read_text(encoding="utf-8"))
    check("exactly nine presets, in the owner's order",
          [p["id"] for p in fixture["presets"]]
          == ["general", "general_uncensored", "coding", "agentic_vision", "fast",
              "reflect", "pictures", "documents", "browser"],
          [p["id"] for p in fixture["presets"]])
    check("the five old ids are named as replaced",
          fixture["old_ids_replaced"] == ["everyday", "coding", "admin", "long", "specialist"])
    for p in fixture["presets"]:
        check(f"{p[chr(105)+chr(100)]}: lane is main or coding with its real port",
              p["lane"]["key"] in ("main", "coding")
              and p["lane"]["port"] == (11436 if p["lane"]["key"] == "main" else 11435), p["lane"])
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
    check("Coding now uses the 30B coder across both cards (heavy mode)",
          cod.model == "qwen3-coder-30b-a3b-ud-q3-k-xl" and cod.heavy_mode is True
          and cod.measured["tok_s"] == 76.2 and cod.measured["rubric"] == "6/6 coding rubric"
          and cod.measured["size_gib"] == 14.0 and cod.measured["cold_load_s"] == 32.1
          and "BOTH GPUs" in cod.cost, cod.model)
    check("... its words say heavy mode evicts lanes and lane support is arriving",
          "evicts" in cod.cost and "pooled both-GPU lane" in cod.worse
          and "lane support arriving" in cod.worse and "No single-card" in cod.worse)
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
    rec3 = P.recommendations()["by_gpu_count"]["3"]
    check("every preset has a 3-GPU recommendation row (the id-keyed GPU dicts cover the catalogue)",
          set(rec3) == set(P.PRESET_IDS), sorted(rec3))

    hw = fixture["hardware"]
    check("hardware: detected cards come from detect() and carry name/VRAM/index",
          hw["detected"]["source"] == "jarvis_hardware.detect()"
          and isinstance(hw["detected"]["count"], int)
          and all(set(c) == {"index", "name", "vram_gib", "uuid"} for c in hw["detected"]["cards"]),
          hw["detected"])
    check("questionnaire: the nine focus ids and the four priorities",
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
    check("3-GPU confirmed layout: Fast on card 1, Agentic+Vision on card 2",
          three["fast"]["card_index"] == 1 and three["agentic_vision"]["card_index"] == 2,
          {k: v["card_index"] for k, v in three.items()})
    check("3-GPU plan is lane-per-GPU on three RTX cards, and says the x4 link",
          rec["three_gpu_plan"]["confirmed"] is True
          and "lane per GPU" in rec["three_gpu_plan"]["layout"]
          and "PCIe 3.0 x4" in rec["three_gpu_plan"]["link_note"]
          and len(rec["three_gpu_plan"]["cards"]) == 3, rec.get("three_gpu_plan"))
    check("the pooled Qwen3.8-27B 28 GB is named as future-only, not a preset",
          "not a preset" in rec["three_gpu_plan"]["future_not_a_preset"]
          and "28 GB" in rec["three_gpu_plan"]["future_not_a_preset"])
    check("General Uncensored is measured in the 2-GPU rows now",
          rec["by_gpu_count"]["2"]["general_uncensored"]["tok_s"] == 45.6
          and rec["by_gpu_count"]["2"]["general_uncensored"]["measured"] is True)

    t_the_live_route_matches_the_generated_contract()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
