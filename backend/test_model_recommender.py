"""The hardware-aware model recommender, proved without a card or a model.

    python3 backend/test_model_recommender.py

WHAT THIS SUITE OWNS (Q6, 2026-11-07):
  1. The five hardware tiers, their boundaries, and the honest fallback for a
     PC that is none of them (one 24 GB card must not be forced into a tier).
  2. The provenance rule: a row is `MEASURED ON THIS PC` only when a local
     scorecard matches the cards this PC reports; otherwise it is
     `ESTIMATED FIT (run benchmark to verify)`, in those words.
  3. The downgrade warning: a stored run that spilled is warned about, and a
     scorecard from a different card set is not offered as measured here.
  4. The panel's JSON shape, exactly - the seam Lane 2 builds against.
  5. The deterministic chat hook: its exact signature, the questions it owns,
     `None` for everything else, and byte-identical answers for one PC.
  6. Read-only: no network, no subprocess, no file writes, no model call, no
     card, no preset - by reading this module's own source.
  7. A PC with no card reported gets the processor-only tier and says so.

No pytest. Run it directly; the exit code is the verdict.
"""
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_model_recommender.py")

import jarvis_model_recommender as R  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


THREE_CARDS = [
    {"name": "NVIDIA GeForce RTX 2060", "total_gib": 12.0, "monitor": False,
     "uuid": "GPU-2060", "index": 0},
    {"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8.0,
     "monitor": False, "uuid": "GPU-2080a", "index": 1},
    {"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8.0,
     "monitor": True, "uuid": "GPU-2080b", "index": 2},
]
EIGHT = [{"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8.0,
          "monitor": True, "uuid": "GPU-2080b", "index": 0}]
TWELVE = [{"name": "NVIDIA GeForce RTX 3060", "total_gib": 12.0,
           "monitor": False, "uuid": "GPU-3060", "index": 0}]
SIXTEEN = [{"name": "NVIDIA GeForce RTX 4070 Ti SUPER", "total_gib": 16.0,
            "monitor": False, "uuid": "GPU-4070", "index": 0}]
FORTY = [{"name": "NVIDIA RTX 6000 Ada", "total_gib": 48.0, "monitor": False,
          "uuid": "GPU-6000", "index": 0}]
TWENTY_FOUR = [{"name": "NVIDIA GeForce RTX 4090", "total_gib": 24.0,
                "monitor": False, "uuid": "GPU-4090", "index": 0}]

MEASURED_9B = {
    "kind": "bench-suite", "suite": "speed", "measured_on": "this_pc",
    "model": "qwen3.5:9b", "digest": "sha256:feedface", "quant": "Q4_K_M",
    "ctx": 196608, "cards_used": "0, 1, 2", "decode_tps": 42.01,
    "spill_bytes": 0, "on_card_percent": 100,
    "size": 9_857_400_830, "size_vram": 9_857_400_830,
    "passed": True, "promotion_grade": True, "at": 1762560000,
}


def _scores(*rows):
    out = {}
    for row in rows:
        bare = R._measured_for
        model = str(row.get("model") or "").replace(":latest", "")
        out[(model, row.get("suite", "speed"))] = row
    return out


# ==========================================================================
#   1. The tiers
# ==========================================================================

def t_the_five_tiers_and_the_honest_fallback():
    def tier(cards):
        return R.tier_for(cards)["id"]

    check("no card reported is the processor-only tier",
          tier([]) == R.TIER_CPU_ONLY, tier([]))
    check("one 8 GB card is the 8 GB tier", tier(EIGHT) == R.TIER_SINGLE_8)
    check("one 12 GB card is the 12-16 GB tier",
          tier(TWELVE) == R.TIER_SINGLE_12_16)
    check("one 16 GB card is the 12-16 GB tier",
          tier(SIXTEEN) == R.TIER_SINGLE_12_16)
    check("a 12 + 8 GB pair is the 20-28 GB pool tier",
          tier(THREE_CARDS[:2]) == R.TIER_MULTI_20_28)
    check("this PC's three cards (28 GiB) are the pool tier",
          tier(THREE_CARDS) == R.TIER_MULTI_20_28)
    check("32 GB or more is the workstation tier",
          tier(FORTY) == R.TIER_WORKSTATION)
    check("one 24 GB card is NONE of the five, and says so instead of being "
          "forced into a tier", tier(TWENTY_FOUR) == R.TIER_OTHER)
    check("every tier has a label and plain words",
          all(t.get("label") and t.get("words") for t in R.TIERS))
    check("the five named tiers are all present",
          {t["id"] for t in R.TIERS} >= {
              R.TIER_CPU_ONLY, R.TIER_SINGLE_8, R.TIER_SINGLE_12_16,
              R.TIER_MULTI_20_28, R.TIER_WORKSTATION})


def t_the_hardware_profile_is_one_sentence_and_no_guesses():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9,
                                 cpu="AMD Ryzen 9 3900X")
    check("the profile counts the cards", profile["card_count"] == 3)
    check("the profile totals the video memory",
          profile["vram_total_gib"] == 28.0, profile["vram_total_gib"])
    check("the profile keeps the largest card",
          profile["largest_card_gib"] == 12.0)
    check("the profile carries the tier", profile["tier"]["id"]
          == R.TIER_MULTI_20_28)
    check("the words name the cards and the RAM",
          "3 NVIDIA cards" in profile["words"]
          and "28 GiB" in profile["words"] and "31.9 GiB of RAM"
          in profile["words"], profile["words"])
    check("an explicitly reported no-card PC is detected, not unknown",
          R.hardware_profile(cards=[], ram_gb=16.0)["detected"] is True)
    check("RAM that cannot be read is None, never 0",
          R.hardware_words(THREE_CARDS, R.tier_for(THREE_CARDS), None)
          .count("RAM") == 0)


def t_no_card_means_processor_only_and_no_invented_hardware():
    profile = R.hardware_profile(cards=[], ram_gb=8.0, cpu="4 cores")
    check("no card reported is the processor-only tier",
          profile["tier"]["id"] == R.TIER_CPU_ONLY)
    check("its sentence says processor only",
          "no usable graphics card" in profile["words"].lower(), profile["words"])
    panel = R.recommend(hardware=profile, scores={})
    small = [row for row in panel["rows"] if row["model"] == "minicpm-v4.6"]
    check("a CPU-only PC is still offered the smallest model, labelled "
          "estimated", len(small) == 1
          and small[0]["provenance"] == R.PROVENANCE_ESTIMATED)
    check("a CPU-only PC is NOT offered the 30B coder",
          not any("30B" in row["params"] for row in panel["rows"]))
    check("the rows it cannot run are counted, not hidden silently",
          panel["not_shown"] > 0, panel["not_shown"])


# ==========================================================================
#   2. Provenance: measured here vs estimated
# ==========================================================================

ROW_KEYS = {"model", "label", "params", "quant", "capabilities", "fit",
            "vram_needed_gib", "context_gib", "provenance", "provenance_label",
            "measured", "downgrade_warning", "why", "measured_note"}


def t_every_row_is_labelled_measured_or_estimated():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    none_measured = R.recommend(hardware=profile, scores={})
    check("with an empty store every row is an ESTIMATED FIT",
          all(row["provenance"] == R.PROVENANCE_ESTIMATED
              for row in none_measured["rows"]))
    check("the estimated label is the owner's exact words",
          all(row["provenance_label"]
              == "ESTIMATED FIT (run benchmark to verify)"
              for row in none_measured["rows"]))
    check("the notes say nothing has been benchmarked yet",
          any("nothing has been benchmarked" in n
              for n in none_measured["notes"]))

    measured = _scores(MEASURED_9B)
    panel = R.recommend(hardware=profile, scores=measured)
    row = next(r for r in panel["rows"] if r["model"] == "qwen3.5:9b")
    check("a matching scorecard is MEASURED ON THIS PC",
          row["provenance"] == R.PROVENANCE_MEASURED)
    want_date = time.strftime("%Y-%m-%d", time.localtime(1762560000))
    check("its label names the speed, the spill and the date",
          row["provenance_label"].startswith("MEASURED ON THIS PC")
          and "42.0 tok/s" in row["provenance_label"]
          and "0% spill" in row["provenance_label"]
          and want_date in row["provenance_label"], row["provenance_label"])
    check("the measured numbers travel with the row",
          row["measured"]["decode_tps"] == 42.01
          and row["measured"]["digest"] == "sha256:feedface"
          and row["measured"]["ctx"] == 196608)
    check("measured rows sort before estimated rows",
          panel["rows"][0]["provenance"] == R.PROVENANCE_MEASURED)
    check("every row carries exactly the documented keys",
          all(set(r) == ROW_KEYS for r in panel["rows"]),
          [set(r) ^ ROW_KEYS for r in panel["rows"]][:2])
    check("every row's reason is scoped to its fit, with the requirement said "
          "once (the row's own needs line), not repeated",
          all(r["why"].startswith("At that window it ")
              and "needs about" not in r["why"] for r in panel["rows"]),
          [r["why"] for r in panel["rows"]][:1])


def t_a_scorecard_from_other_cards_is_not_measured_here():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    other = dict(MEASURED_9B, cards_used="0")
    panel = R.recommend(hardware=profile, scores=_scores(other))
    row = next(r for r in panel["rows"] if r["model"] == "qwen3.5:9b")
    check("a one-card run is not offered as measured on a three-card PC",
          row["provenance"] == R.PROVENANCE_OTHER_PC)
    check("and the row says to re-run the benchmark here",
          "different card" in row["downgrade_warning"]
          and "run the benchmark" in row["why"])


def t_a_spilled_run_raises_a_downgrade_warning():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    spilled = dict(MEASURED_9B, spill_bytes=300 * 1024 * 1024,
                   on_card_percent=96)
    panel = R.recommend(hardware=profile, scores=_scores(spilled))
    row = next(r for r in panel["rows"] if r["model"] == "qwen3.5:9b")
    check("a stored run that spilled is warned about",
          "300 MiB" in row["downgrade_warning"]
          and row["downgrade_warning"])
    check("the label says it spilled, not 0%",
          "spilled" in row["provenance_label"], row["provenance_label"])
    check("the warning is in words an owner reads",
          "too optimistic" in row["why"])


# ==========================================================================
#   3. The panel's JSON shape (Lane 2's seam)
# ==========================================================================

def t_the_panel_shape_is_exactly_what_the_brain_reads():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    panel = R.panel(hardware=profile, scores={}, now=1762560000)
    check("the top-level keys are the documented ones",
          set(panel) == {"hardware", "tier", "rows", "not_shown", "notes",
                         "generated_at", "words"}, set(panel))
    check("hardware carries the documented fields",
          {"cards", "card_count", "vram_total_gib", "largest_card_gib",
           "ram_gib", "cpu", "detected", "tier", "words"} <= set(panel["hardware"]))
    check("tier is id/label/words", set(panel["tier"]) == {"id", "label",
                                                           "words"})
    check("generated_at is the caller's clock, so a test can pin it",
          panel["generated_at"] == 1762560000)
    check("the panel is JSON-serialisable", json.dumps(panel) is not None)
    check("the words mention the hardware and a model",
          panel["hardware"]["words"] in panel["words"]
          and any(row["label"] in panel["words"] for row in panel["rows"]),
          panel["words"])


# ==========================================================================
#   4. The deterministic chat hook
# ==========================================================================

def t_the_chat_hook_owns_its_question_and_returns_none_for_others():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    scores = _scores(MEASURED_9B)
    for question in ("What model should this PC run?",
                     "which model should I run?",
                     "what models fit this PC?",
                     "recommend a model for this PC"):
        answer = R.chat_hook(question, hardware=profile, scores=scores)
        check(f"it answers {question!r}", isinstance(answer, str)
              and len(answer) > 40, answer)
    for question in ("what is the weather in Paris",
                     "switch to the coding model",
                     "how much RAM do I have",
                     "what changed recently"):
        check(f"it leaves {question!r} to the other matchers",
              R.chat_hook(question, hardware=profile, scores=scores) is None)
    check("the exact signature is documented beside the code",
          R.CHAT_HOOK_SIGNATURE.startswith(
              "jarvis_model_recommender.chat_hook(question"))


def t_the_chat_answer_is_deterministic_and_measured_aware():
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    scores = _scores(MEASURED_9B)
    first = R.chat_hook("what model should this PC run?", hardware=profile,
                        scores=scores)
    second = R.chat_hook("what model should this PC run?", hardware=profile,
                         scores=scores)
    check("the same PC answers the same way" + " twice",
          first == second, (first, second))
    check("the answer names the hardware tier",
          "20-28 GB" in first or "pool" in first, first)
    check("the answer separates measured from estimated",
          "measured on this pc" in first.lower()
          and "estimated" in first.lower(), first)
    check("the measured model's real speed is in the answer",
          "42.0" in first, first)


# ==========================================================================
#   5. Read-only: its own source
# ==========================================================================

def t_it_is_read_only_and_touches_nothing():
    import ast
    path = Path(R.__file__)
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"urllib", "http", "socket", "requests", "subprocess", "shutil",
              "jarvis_hud", "jarvis_quick", "jarvis_models", "jarvis_presets",
              "jarvis_gate", "jarvis_asks_first"}
    check("it imports none of the network, process or owner-only modules",
          not (imported & banned), imported & banned)
    writers = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "open":
            writers.append("open")
        elif isinstance(fn, ast.Attribute) and fn.attr in (
                "write_text", "write_bytes", "unlink", "mkdir",
                "rename", "rmdir"):
            writers.append(fn.attr)
    check("it writes no file and opens none for writing", not writers, writers)
    check("it raises no card and touches no preset",
          "jarvis_gate" not in text and "apply_preset" not in text
          and "switch_model" not in text)
    check("it defines no route handler", "@route" not in text
          and "do_POST" not in text and "do_GET" not in text)
    check("it is stdlib only", imported <= {
        "os", "platform", "time", "typing", "jarvis_hardware", "jarvis_bench",
        "jarvis_child_env", "ctypes", "__future__"}, imported)


def t_the_catalogue_has_no_duplicates_and_says_where_its_numbers_come_from():
    models = [row["model"] for row in R.CATALOGUE]
    check("every model appears once", len(models) == len(set(models)))
    check("the catalogue names no DELETED model tag",
          all(row["model"] != "qwen3-coder:30b-a3b-q4_K_M"
              for row in R.CATALOGUE),
          [row["model"] for row in R.CATALOGUE
           if row["model"] == "qwen3-coder:30b-a3b-q4_K_M"])
    check("every row has a positive size estimate",
          all(float(row["min_vram_gib"]) > 0 for row in R.CATALOGUE))
    check("every catalogue row says where its number comes from",
          all(row.get("measured_note") for row in R.CATALOGUE))




# ==========================================================================
#   8. The PC's hardware, not one running Ollama's usage (Wave 11)
# ==========================================================================

def t_the_three_card_pc_is_described_by_its_hardware_not_by_ollama():
    """The owner's PC on 2026-11-08: three cards, and live `jarvis_hardware`
    marks two of them `used: false` because Ollama's log lists only one.
    `detect_cards()` must count every CUDA card; the tier and words describe
    the hardware, and Ollama's current usage stays out of them."""
    probe = {
        "found": "Found 3 graphics cards; Ollama can use 1: the 2080 SUPER",
        "cards": [
            {"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8.0,
             "route": "CUDA", "used": True, "index": 0},
            {"name": "NVIDIA GeForce RTX 2060", "total_gib": 12.0,
             "route": "CUDA", "used": False, "index": 1,
             "why_unused": "Ollama's log does not list it, so Ollama does not use it"},
            {"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8.0,
             "route": "CUDA", "used": False, "index": 2,
             "why_unused": "Ollama's log does not list it, so Ollama does not use it"},
            {"name": "llvmpipe", "total_gib": 4.0, "route": "VULKAN",
             "used": False, "index": 3},
        ],
    }
    cards = R.detect_cards(detect=lambda: probe)
    check("all three CUDA cards are counted, whether or not Ollama lists them",
          len(cards) == 3
          and sorted(c["total_gib"] for c in cards) == [8.0, 8.0, 12.0],
          cards)
    check("a non-CUDA probe row is still not a graphics card", len(cards) == 3)
    profile = R.hardware_profile(detect=lambda: probe, ram_gb=31.9)
    check("...so the profile is three cards and 28 GiB, not one 8 GB card",
          profile["card_count"] == 3
          and profile["vram_total_gib"] == 28.0
          and profile["tier"]["id"] == R.TIER_MULTI_20_28,
          (profile["card_count"], profile["vram_total_gib"],
           profile["tier"]["id"]))
    words = profile["words"]
    check("the hardware sentence says three cards and 28 GiB",
          "3 NVIDIA cards with 28 GiB" in words, words)
    check("the tier words appear exactly once in the sentence",
          words.count(profile["tier"]["label"]) == 1, words)
    check("which cards one Ollama session lists is not in the hardware words",
          "Ollama" not in words and "used" not in words.lower(), words)
    panel = R.recommend(hardware=profile, scores={})
    check("the panel's own hardware block is the three-card PC, not one card",
          panel["hardware"]["card_count"] == 3
          and panel["hardware"]["vram_total_gib"] == 28.0,
          panel["hardware"].get("words"))


def t_every_row_separates_its_estimate_from_the_2026_11_07_measurement():
    """An estimate and a measurement are different claims. Every row says its
    fit in an estimate-scoped sentence, and every catalogue measurement is
    prefixed as the separate 2026-11-07 measurement; neither is dressed up as
    the other, and no number is invented."""
    profile = R.hardware_profile(cards=THREE_CARDS, ram_gb=31.9)
    panel = R.recommend(hardware=profile, scores={})
    rows = panel["rows"]
    check("every fit sentence is the estimate-scoped line",
          all(r["why"].startswith("At that window it ") for r in rows),
          [r["why"] for r in rows if not r["why"].startswith("At that window it ")][:1])
    check("every measurement note is labelled as the separate 2026-11-07 one",
          all(r["measured_note"].startswith(
              "Separately measured on 2026-11-07: ") for r in rows),
          [r["measured_note"] for r in rows
           if not r["measured_note"].startswith("Separately measured on 2026-11-07: ")][:1])
    check("no measurement note is left unprefixed in the catalogue",
          all("2026-11-07 sweep" not in row["measured_note"]
              and "2026-11-07, this PC" not in row["measured_note"]
              for row in R.CATALOGUE))
    mini = next(r for r in rows if r["model"] == "minicpm-v4.6")
    check("MiniCPM-V's one-card fit and its three-card run are scoped "
          "separately, so the two lines cannot be read as one claim",
          "fits on one card" in mini["why"]
          and "across three cards" in mini["measured_note"]
          and "1.33 GiB" in mini["measured_note"],
          (mini["why"], mini["measured_note"]))
    for row in rows:
        check(f"{row['label']}: the requirement is said by its needs line, "
              "not mixed into the fit sentence",
              "needs about" not in row["why"])


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("t_") and callable(f) and f.__module__ == "__main__"]
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
