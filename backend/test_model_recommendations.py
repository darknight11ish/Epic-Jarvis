"""The model/preset recommendation routes: no download, no card, measured only.

    py -3 backend/test_model_recommendations.py

WHAT EACH BLOCK PROVES

  * GET /api/models/recommendations is read-only and NETWORK-FREE: it reads the
    one JSON store and the PC's own card list, and the discovery seam is wired
    to blow up so a network call cannot hide in it.
  * POST /api/models/check caches the catalogue pass and NEVER downloads: the
    module is source-scanned for every download/apply/gate call it must not
    contain, and the check answer holds only the contract's own keys (plus a
    plain error on failure).
  * a candidate carries the licence the catalogue reports (Hugging Face's
    `license:` tag) and `null` where it reports none - never a guess - and no
    candidate carries a SHA-256, because the catalogue has no hash to carry.
  * POST /api/models/benchmark REFUSES an uninstalled model before measuring,
    stores a real measurement when it has one, and stores nothing when it does
    not.
  * the preset recommendations cite only numbers the benchmark store and the
    measured cards produced - a candidate with no measured rate, video memory
    or context is never chosen, and a faster model that would shrink the window
    is not recommended.
  * the owner's opinion is a deterministic rule (keep/lower/raise/quality/note)
    that changes the suggestion without inventing a measurement: same inputs,
    same answer, and "raise" cannot conjure a number that was never measured.
  * ALL five routes are PC-only: a phone's peer is refused 403 before the body
    is read, and origin/token are the server's own checks.
  * the EXISTING carded routes are still the only way to act: the module holds
    no install and no apply handler, and the published base still serves
    `/api/models/install`, while `jarvis_presets.APPLY_PATH` is still
    `/api/work/apply`.
  * a damaged store reads as empty rather than breaking a route.

Runs anywhere: no owner's PC, no model, no network. The discovery, measure,
/api/ps and /api/show seams are all injected.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_model_recommendations as M  # noqa: E402
import jarvis_presets as P  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="model-rec-"))

#: The owner's PC, as `jarvis_hardware.detect()` reports it (measured
#: 2026-10-05): the 12 GB 2060 is the long-context card, the 8 GB 2080 SUPER is
#: the fast/display card.
GPUS = [{"name": "NVIDIA GeForce RTX 2060", "vram_gb": 12.0, "role": "main"},
        {"name": "NVIDIA GeForce RTX 2080 SUPER", "vram_gb": 8.0, "role": "coding"}]
T0 = 1761700000          # 2026-10-28, roughly; only ever compared to itself


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name +
          (f"\n        {detail}" if detail and not cond else ""))


def fresh(name):
    return TMP / f"{name}.json"


def boom(*_a, **_k):
    raise AssertionError("this seam must not be called")


class Row:
    """One `jarvis_presets.Preset` row, in the fields this feature reads."""

    def __init__(self, id, model, lane, context, pending=False, heavy_mode=False):
        self.id, self.model, self.lane = id, model, lane
        self.context, self.pending, self.heavy_mode = context, pending, heavy_mode


def row(**kw):
    base = dict(id="x", model="cur:9b", lane="main", context=16384)
    base.update(kw)
    return Row(**base)


# --------------------------------------------------------------------------
#   measured hardware
# --------------------------------------------------------------------------

def t_the_cards_are_mapped_to_the_preset_lanes_and_intake_is_honest():
    rows = [
        {"name": "NVIDIA GeForce RTX 2060", "total_gib": 12.0, "used": True},
        {"name": "NVIDIA GeForce RTX 2080 SUPER", "total_gib": 8.0, "used": True},
        {"name": "Intel UHD Graphics 770", "total_gib": 1.0, "used": False},
        {"name": "Mystery card", "used": True},          # no size: not measured
    ]
    got = M.measured_gpus(detect=lambda: rows)
    check("the 2060 is the main lane and the 2080 SUPER the coding lane",
          [g["role"] for g in got] == ["main", "coding"], got)
    check("a card Ollama dropped (used false) is not offered as measured",
          all("Intel" not in g["name"] for g in got), got)
    check("a card with no measured size is not offered at all",
          all(g["name"] != "Mystery card" for g in got), got)
    check("the measured size is the card's own total_gib",
          got[0]["vram_gb"] == 12.0 and got[1]["vram_gb"] == 8.0, got)


# --------------------------------------------------------------------------
#   GET: read-only, no network
# --------------------------------------------------------------------------

def t_the_read_answer_is_the_contract_shape_and_touches_no_network():
    real = M.measured_gpus
    M.measured_gpus = boom
    path = fresh("never-written")
    try:
        out = M.recommendations_view(path=path, gpus=GPUS)
    finally:
        M.measured_gpus = real
    check("GET's answer is exactly the five contract keys",
          set(out) == {"checked_at", "gpus", "candidates", "recommendations",
                       "benchmarked"}, sorted(out))
    check("nothing checked yet reads as checked_at null, no candidates, nothing measured",
          out["checked_at"] is None and out["candidates"] == []
          and out["recommendations"] == [] and out["benchmarked"] == {}, out)
    check("the measured cards are reported", out["gpus"] == GPUS)
    check("... and GET wrote no file", not path.exists())


# --------------------------------------------------------------------------
#   POST check: the catalogue pass, cached, never a download
# --------------------------------------------------------------------------

MODELS = [
    {"ref": "acme/NewModel-GGUF", "source": "huggingface",
     "params": 8_000_000_000, "bytes_": 4 * 2 ** 30, "context": 131072,
     "quant": "Q4_K_M", "trending": 10, "bench": {"humaneval+": 0.5},
     "tags": ["text-generation", "gguf", "license:apache-2.0"]},
    {"ref": "tiny:1b", "source": "ollama", "params": 1_000_000_000,
     "size_gb": 1.0, "context": 8192, "trending": 2},
    {"ref": "acme/NoSize-GGUF", "source": "huggingface", "context": 4096},
]


def t_the_check_caches_candidates_and_never_downloads():
    path = fresh("check")
    calls = []

    def discover():
        calls.append(1)
        return list(MODELS)

    code, out = M.check_models(path=path, gpus=GPUS, discover=discover,
                               estimate=lambda m: 6000, clock=lambda: T0)
    check("check answers 200 with the contract's five keys",
          code == 200 and set(out) >= {"checked_at", "gpus", "candidates",
                                       "recommendations", "benchmarked"}, out)
    check("... checked_at is the clock it ran at", out["checked_at"] == T0)
    check("... a candidate with no size in the listing is not judged",
          all(c["ref"] != "acme/NoSize-GGUF" for c in out["candidates"]),
          out["candidates"])
    check("... two judged candidates", len(out["candidates"]) == 2,
          out["candidates"])
    first = out["candidates"][0]
    check("a candidate carries exactly the contract fields",
          set(first) == {"ref", "name", "family", "params_b", "quant", "size_gb",
                         "context_tokens", "licence", "fit", "source_url", "why"},
          sorted(first))
    check("... its fit is one of the three words",
          first["fit"] in ("fits", "tight", "no"), first["fit"])
    check("... the licence the catalogue reports is carried, nothing invented",
          first["licence"] == "apache-2.0", first["licence"])
    check("... a candidate whose catalogue row has no licence says null, not a guess",
          {c["ref"]: c["licence"] for c in out["candidates"]}.get("tiny:1b", "missing")
          is None, out["candidates"])
    check("... no candidate carries a SHA-256 the catalogue cannot report",
          all("sha256" not in c and "sha_256" not in c for c in out["candidates"]),
          out["candidates"])
    check("... its size, parameter count and context came through",
          first["ref"] == "acme/NewModel-GGUF" and first["size_gb"] == 4.0
          and first["params_b"] == 8.0 and first["context_tokens"] == 131072,
          first)
    check("... its source is the public page and its why quotes the estimate",
          first["source_url"] == "https://huggingface.co/acme/NewModel-GGUF"
          and "estimated" in first["why"], first)
    check("the check really ran the catalogue pass once", calls == [1], calls)
    check("... and it cached the answer on disk", path.is_file())
    saved = json.loads(path.read_text(encoding="utf-8"))
    check("... with the same candidate refs in the store",
          [c["ref"] for c in saved["candidates"]] == [c["ref"] for c in out["candidates"]],
          saved.get("candidates"))

    again = M.recommendations_view(path=path, gpus=GPUS)
    check("a later GET reads the cached check without touching the network",
          again["checked_at"] == T0 and len(again["candidates"]) == 2
          and again["candidates"] == out["candidates"], again)


def t_check_refuses_when_no_card_was_measured_and_does_no_lookup():
    path = fresh("no-gpu")
    code, out = M.check_models(path=path, gpus=[], discover=boom)
    check("check with no measured card is 503, not a guess", code == 503)
    check("... the contract's keys are still present",
          set(out) >= {"checked_at", "gpus", "candidates", "recommendations",
                       "benchmarked"}, sorted(out))
    check("... and it says why", "graphics card" in out["error"], out["error"])
    check("... no store was written", not path.exists())


def t_check_refuses_honestly_without_the_catalogue_module():
    missing = fresh("missing")
    code, out = M.check_models(
        path=missing, gpus=GPUS,
        discover=lambda: (_ for _ in ()).throw(
            M.DiscoveryUnavailable("the model catalogue module is not here")))
    check("a missing catalogue module is a plain 503 that names it",
          code == 503 and "model catalogue" in out["error"], out)
    empty = fresh("empty")
    code, out = M.check_models(path=empty, gpus=GPUS, discover=lambda: [])
    check("a catalogue pass that returns nothing is a 503, not a cached empty check",
          code == 503 and "returned no models" in out["error"] and not empty.exists(),
          out)


def t_the_check_answer_has_no_fit_claim_without_an_estimate():
    path = fresh("no-estimate")
    code, out = M.check_models(path=path, gpus=GPUS, discover=lambda: list(MODELS),
                               estimate=lambda m: None, clock=lambda: T0)
    check("with no estimate every measured-size candidate is still listed",
          code == 200 and len(out["candidates"]) == 2, out)
    check("... and none of them is called fitting",
          all(c["fit"] == "no" and "no fit is claimed" in c["why"]
              for c in out["candidates"]), out["candidates"])


# --------------------------------------------------------------------------
#   POST benchmark: installed only, stored, bounded
# --------------------------------------------------------------------------

def t_benchmark_refuses_an_uninstalled_model_before_measuring():
    path = fresh("bench-uninstalled")
    calls = []
    code, out = M.run_benchmark(
        "qwen3.5:9b", store_path_=path,
        installed=lambda: ["other:1b"],
        measure=lambda ref: calls.append(ref) or {"ok": True, "tokens_per_s": 9.9})
    check("an uninstalled ref is 409", code == 409, (code, out))
    check("... the refusal says it is not installed and names the install card",
          "not installed" in out["error"] and "/api/models/install" in out["error"],
          out)
    check("... and nothing was measured", calls == [] and not path.exists())


def t_benchmark_measures_stores_and_returns_the_measurement():
    path = fresh("bench-good")
    code, out = M.run_benchmark(
        "qwen3.5:9b", store_path_=path,
        installed=lambda: ["qwen3.5:9b"],
        measure=lambda ref: {"ok": True, "tokens_per_s": 52.5, "probes": 1},
        ps=lambda: {"models": [{"name": "qwen3.5:9b", "vram_mb": 9216}]},
        geometry=lambda ref: {"train_context": 196608},
        clock=lambda: T0)
    check("an installed model is measured", code == 200 and out["ok"] is True,
          (code, out))
    check("... the answer carries rate, video memory, context and time",
          out["tokens_per_s"] == 52.5 and out["vram_gb"] == 9.0
          and out["context_tokens"] == 196608 and out["measured_at"] == T0, out)
    check("... it says the raw row is in the speed record",
          "speed.jsonl" in out["note"], out["note"])
    saved = json.loads(path.read_text(encoding="utf-8"))
    check("... and the store has exactly the contract's four fields per ref",
          saved["benchmarked"]["qwen3.5:9b"] == {
              "tokens_per_s": 52.5, "vram_gb": 9.0,
              "context_tokens": 196608, "measured_at": T0},
          saved.get("benchmarked"))
    seen = M.recommendations_view(path=path, gpus=GPUS)
    check("a later GET reports the measurement", seen["benchmarked"]["qwen3.5:9b"]
          == saved["benchmarked"]["qwen3.5:9b"])


def t_benchmark_stores_nothing_when_it_cannot_measure():
    path = fresh("bench-fail")
    code, out = M.run_benchmark(
        "qwen3.5:9b", store_path_=path, installed=lambda: ["qwen3.5:9b"],
        measure=lambda ref: {"ok": False, "note": "Ollama answered, but without "
                                                  "timing numbers."})
    check("a model that will not give timings is 503 with its own sentence",
          code == 503 and "without timing numbers" in out["error"], out)
    check("... and nothing was stored", not path.exists())
    code, out = M.run_benchmark(
        "qwen3.5:9b", store_path_=path, installed=lambda: ["qwen3.5:9b"],
        measure=lambda ref: (_ for _ in ()).throw(RuntimeError("boom")))
    check("a measurement that raises is 503 and stores nothing",
          code == 503 and "RuntimeError" in out["error"] and not path.exists(), out)
    code, out = M.run_benchmark("not a ref!", store_path_=path, installed=boom)
    check("a ref that is not a model name is 400 before any Ollama call",
          code == 400 and "model ref" in out["error"], out)
    # The shipped seam answers [] for "Ollama is down" AND "you do not have it";
    # /api/ps says which, so a down Ollama is 503 (cannot tell), not 409.
    code, out = M.run_benchmark(
        "qwen3.5:9b", store_path_=path,
        installed=lambda: [],
        ps=lambda: {"available": False, "status": "unknown"})
    check("with Ollama down the refusal says it cannot tell, and is 503",
          code == 503 and "did not answer" in out["error"], (code, out))


# --------------------------------------------------------------------------
#   Recommendations: measured numbers only
# --------------------------------------------------------------------------

def t_a_recommendation_cites_the_measured_numbers_and_nothing_else():
    bench = {
        "cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                   "context_tokens": 32768, "measured_at": T0},
        "cand:4b": {"tokens_per_s": 60.0, "vram_gb": 5.0,
                    "context_tokens": 32768, "measured_at": T0 + 10},
        "unmeasured:99b": {"vram_gb": 1.0, "context_tokens": 262144,
                           "measured_at": T0},          # no rate
    }
    recs = M.preset_recommendations(presets=[row()], gpus=GPUS, benchmarked=bench)
    check("one preset is recommended", len(recs) == 1, recs)
    rec = recs[0]
    check("... the recommendation names the preset row, its changes and evidence",
          set(rec) == {"preset", "changes", "evidence"} and rec["preset"] == "x",
          rec)
    check("... exactly one change, and it is the model field",
          len(rec["changes"]) == 1 and rec["changes"][0]["row"] == "model",
          rec["changes"])
    change = rec["changes"][0]
    check("... from the current measured model to the faster measured one",
          change["from"] == "cur:9b" and change["to"] == "cand:4b", change)
    why = change["why"]
    check("... and the sentence quotes the measured rate for both models",
          "60.0 tokens/s" in why and "40.0 for cur:9b" in why, why)
    check("... the measured video memory for the candidate and the card",
          "5.0 GB" in why and "12.0 GB" in why, why)
    check("... a model with no measured rate is never chosen, however it looks",
          "unmeasured:99b" not in json.dumps(rec), rec)
    check("... the evidence names the benchmark store and both hardware docs",
          all(s in rec["evidence"] for s in (
              "model-recommendations.json", "speed.jsonl",
              "docs/MEASURED-2026-10-05-owner-pc.md",
              "docs/MODEL-TOPOLOGY.md")), rec["evidence"])
    check("... and says no estimate justifies a preset change",
          "No estimate" in rec["evidence"], rec["evidence"])


def t_no_change_is_recommended_without_both_sides_measured():
    bench = {"cand:4b": {"tokens_per_s": 90.0, "vram_gb": 4.0,
                         "context_tokens": 65536, "measured_at": T0}}
    check("a candidate alone is not a comparison",
          M.preset_recommendations(presets=[row()], gpus=GPUS,
                                   benchmarked=bench) == [])
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 32768, "measured_at": T0},
             "cand:4b": {"tokens_per_s": 90.0, "context_tokens": 65536,
                         "measured_at": T0}}         # no video memory
    check("a candidate with no measured video memory cannot be shown to fit",
          M.preset_recommendations(presets=[row()], gpus=GPUS,
                                   benchmarked=bench) == [])
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 32768, "measured_at": T0},
             "cand:4b": {"tokens_per_s": 90.0, "vram_gb": 4.0,
                         "measured_at": T0}}         # no context
    check("a candidate with no measured context cannot be shown to keep the window",
          M.preset_recommendations(presets=[row()], gpus=GPUS,
                                   benchmarked=bench) == [])


def t_a_faster_model_that_would_shrink_the_window_is_not_recommended():
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 196608, "measured_at": T0},
             "fast:4b": {"tokens_per_s": 90.0, "vram_gb": 4.0,
                         "context_tokens": 32768, "measured_at": T0}}
    check("a 32k model is not offered to a 196k preset",
          M.preset_recommendations(
              presets=[row(context=196608)], gpus=GPUS, benchmarked=bench) == [])
    small = row(id="fast", model="cur:9b", lane="coding", context=16384)
    check("... but the same model IS offered to a 16k preset",
          [r["preset"] for r in M.preset_recommendations(
              presets=[small], gpus=GPUS, benchmarked=bench)] == ["fast"])


def t_a_gain_below_the_bar_is_not_worth_a_download():
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 32768, "measured_at": T0},
             "barely:4b": {"tokens_per_s": 41.0, "vram_gb": 4.0,
                           "context_tokens": 32768, "measured_at": T0}}
    check("a 2.5% gain is under the 5% bar",
          M.preset_recommendations(presets=[row()], gpus=GPUS,
                                   benchmarked=bench) == [])


def t_the_context_a_model_reports_corrects_a_preset_that_asks_for_more():
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 8192, "measured_at": T0}}
    recs = M.preset_recommendations(presets=[row(context=16384)],
                                    gpus=GPUS, benchmarked=bench)
    check("a preset asking for more tokens than the model has is corrected",
          len(recs) == 1 and recs[0]["changes"][0]["row"] == "context", recs)
    change = recs[0]["changes"][0]
    check("... from the preset's claim to the measured maximum",
          change["from"] == 16384 and change["to"] == 8192
          and "8,192" in change["why"], change)


def t_a_model_too_big_for_its_lane_moves_to_the_card_that_can_hold_it():
    # Deliberately the OTHER way round from the owner's PC, so the rule is
    # shown to follow the measured sizes rather than a hard-coded 2060/2080.
    gpus = [{"name": "small card", "vram_gb": 8.0, "role": "main"},
            {"name": "big card", "vram_gb": 12.0, "role": "coding"}]
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 32768, "measured_at": T0}}
    recs = M.preset_recommendations(presets=[row()], gpus=gpus, benchmarked=bench)
    check("a 9.5 GB model does not stay on a measured 8 GB card",
          len(recs) == 1 and recs[0]["changes"][0]["row"] == "lane", recs)
    change = recs[0]["changes"][0]
    check("... it is moved to the measured card that holds it, and the why says why",
          change["to"] == "coding" and "9.5 GB" in change["why"]
          and "8.0 GB" in change["why"] and "12.0 GB" in change["why"], change)


def t_pending_and_heavy_presets_are_never_recommended():
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 32768, "measured_at": T0},
             "cand:4b": {"tokens_per_s": 90.0, "vram_gb": 4.0,
                         "context_tokens": 65536, "measured_at": T0}}
    rows = [row(id="pending", pending=True), row(id="heavy", heavy_mode=True)]
    check("a pending or heavy-mode preset gets no recommendation",
          M.preset_recommendations(presets=rows, gpus=GPUS,
                                   benchmarked=bench) == [])


def t_the_real_preset_rows_are_what_is_read():
    bench = {
        "qwen3.5:9b": {"tokens_per_s": 60.0, "vram_gb": 6.0,
                       "context_tokens": 196608, "measured_at": T0},
        "qwen3.5:4b": {"tokens_per_s": 50.0, "vram_gb": 3.0,
                       "context_tokens": 32768, "measured_at": T0},
    }
    recs = M.preset_recommendations(gpus=GPUS, benchmarked=bench)  # real P.PRESETS
    check("the real table is read, and its ids are what comes back",
          recs and all(r["preset"] in P.PRESET_IDS for r in recs),
          [r["preset"] for r in recs])
    fast = next((r for r in recs if r["preset"] == "fast"), None)
    check("... and it is the only Fast change proposed here",
          fast is not None
          and fast["changes"][0]["row"] == "model"
          and fast["changes"][0]["to"] == "qwen3.5:9b", fast)


# --------------------------------------------------------------------------
#   The owner's opinion: deterministic, no invented data
# --------------------------------------------------------------------------

def t_the_opinion_rules_are_deterministic():
    cases = [("keep these as they are", "keep"),
             ("leave it alone", "keep"),
             ("prefer less video memory", "lower"),
             ("smaller and cheaper please", "lower"),
             ("make it faster", "raise"),
             ("something with more speed", "raise"),
             ("better quality please", "quality"),
             ("the smarter option", "quality"),
             ("hmm, not sure", "note"),
             ("", "note")]
    for text, want in cases:
        check(f"opinion {text!r} reads as {want}",
              M.classify_opinion(text) == want, M.classify_opinion(text))


def t_keep_suppresses_the_model_and_lane_change_but_not_a_context_correction():
    path = fresh("opinion-keep")
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 8192, "measured_at": T0},
             "cand:4b": {"tokens_per_s": 90.0, "vram_gb": 4.0,
                         "context_tokens": 32768, "measured_at": T0}}
    M.save_store({**M._empty_store(), "benchmarked": bench}, path)
    code, out = M.record_opinion("keep them", store_path_=path, gpus=GPUS,
                                 presets=[row()], clock=lambda: T0)
    check("the opinion is recorded and answered", code == 200 and out["stored"], out)
    check("... its rule is keep and the words are kept",
          out["opinion"]["rule"] == "keep" and out["opinion"]["text"] == "keep them",
          out["opinion"])
    rows = out["recommendations"]
    check("... the faster model is NOT recommended any more",
          all(c["row"] != "model" for r in rows for c in r["changes"]), rows)
    check("... the measured context correction survives, because it is a fact",
          any(c["row"] == "context" for r in rows for c in r["changes"]), rows)
    view = M.recommendations_view(path=path, gpus=GPUS, presets=[row()])
    check("... and a later GET applies the same opinion",
          view["recommendations"] == rows, view["recommendations"])


def t_raise_lowers_the_bar_and_lower_prefers_a_smaller_footprint():
    base = {
        "cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                   "context_tokens": 32768, "measured_at": T0},
        "barely:9b": {"tokens_per_s": 41.0, "vram_gb": 5.0,
                      "context_tokens": 32768, "measured_at": T0},
    }
    default = M.preset_recommendations(presets=[row()], gpus=GPUS,
                                       benchmarked=base)
    check("by default a 2.5% gain is not recommended", default == [], default)
    raise_rule = M.preset_recommendations(
        presets=[row()], gpus=GPUS, benchmarked=base,
        opinion={"rule": "raise", "text": "faster", "at": T0})
    check("... 'raise' takes any measured gain",
          len(raise_rule) == 1 and raise_rule[0]["changes"][0]["to"] == "barely:9b",
          raise_rule)

    lower_bench = {
        "cur:9b": {"tokens_per_s": 60.0, "vram_gb": 9.5,
                   "context_tokens": 32768, "measured_at": T0},
        "small:7b": {"tokens_per_s": 58.0, "vram_gb": 4.0,
                     "context_tokens": 32768, "measured_at": T0},
        "big:14b": {"tokens_per_s": 70.0, "vram_gb": 8.0,
                    "context_tokens": 32768, "measured_at": T0},
    }
    default = M.preset_recommendations(presets=[row()], gpus=GPUS,
                                       benchmarked=lower_bench)
    check("by default the fastest candidate wins",
          default and default[0]["changes"][0]["to"] == "big:14b", default)
    lower = M.preset_recommendations(
        presets=[row()], gpus=GPUS, benchmarked=lower_bench,
        opinion={"rule": "lower", "text": "less memory", "at": T0})
    check("... 'lower' prefers the smaller measured footprint",
          lower and lower[0]["changes"][0]["to"] == "small:7b", lower)
    too_slow = {"cur:9b": {"tokens_per_s": 60.0, "vram_gb": 9.5,
                           "context_tokens": 32768, "measured_at": T0},
                "slow:3b": {"tokens_per_s": 20.0, "vram_gb": 2.0,
                            "context_tokens": 32768, "measured_at": T0}}
    check("... but a much slower model is not 'lower', it is worse",
          M.preset_recommendations(
              presets=[row()], gpus=GPUS, benchmarked=too_slow,
              opinion={"rule": "lower", "text": "less memory", "at": T0}) == [])


def t_quality_uses_the_only_measured_capability_figure_and_says_so():
    bench = {
        "cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                   "context_tokens": 32768, "measured_at": T0},
        "fast:4b": {"tokens_per_s": 60.0, "vram_gb": 7.0,
                    "context_tokens": 32768, "measured_at": T0},
        "long:9b": {"tokens_per_s": 50.0, "vram_gb": 9.0,
                    "context_tokens": 131072, "measured_at": T0},
    }
    recs = M.preset_recommendations(
        presets=[row()], gpus=GPUS, benchmarked=bench,
        opinion={"rule": "quality", "text": "better", "at": T0})
    check("... with 'quality' the longest measured context is preferred",
          recs and recs[0]["changes"][0]["to"] == "long:9b", recs)
    check("... and the evidence says the rule was applied, not invented data",
          "the quality rule" in recs[0]["evidence"], recs[0]["evidence"])


def t_an_unknown_opinion_is_recorded_and_changes_nothing():
    path = fresh("opinion-note")
    bench = {"cur:9b": {"tokens_per_s": 40.0, "vram_gb": 9.5,
                        "context_tokens": 32768, "measured_at": T0},
             "cand:4b": {"tokens_per_s": 90.0, "vram_gb": 4.0,
                         "context_tokens": 32768, "measured_at": T0}}
    M.save_store({**M._empty_store(), "benchmarked": bench}, path)
    before = M.preset_recommendations(presets=[row()], gpus=GPUS, benchmarked=bench)
    code, out = M.record_opinion("not sure what to say", store_path_=path,
                                 gpus=GPUS, presets=[row()], clock=lambda: T0)
    check("an unrecognised note is stored, not thrown away",
          code == 200 and out["opinion"]["rule"] == "note", out)
    check("... and the default ranking is unchanged",
          out["recommendations"] == before, out["recommendations"])
    check("... an empty note is a 400 and writes nothing",
          M.record_opinion("   ", store_path_=path)[0] == 400)
    check("... the history keeps the note",
          M.load_store(path)["opinions"][-1]["text"] == "not sure what to say")


# --------------------------------------------------------------------------
#   The wiring: five routes, PC only
# --------------------------------------------------------------------------

class FakeHandler:
    def __init__(self, path, body=b"{}", peer="127.0.0.1", local="127.0.0.1"):
        self.path, self._body = path, body
        self.client_address = (peer, 5555)
        self.connection = SimpleNamespace(getsockname=lambda: (local, 8765))
        self.sent, self.calls, self.body_reads = [], [], 0

    def _send(self, code, payload):
        self.sent.append((code, payload))
        return code  # the routes return it, exactly like the HUD's own _send

    def do_GET(self):
        self.calls.append(("GET", self.path))
        return -1

    def do_POST(self):
        self.calls.append(("POST", self.path))
        return -1


def wired(**kw):
    cls = type("H", (FakeHandler,), {})
    body = kw.pop("body", b"{}")
    reads = {"n": 0}

    def read_body(handler):
        reads["n"] += 1
        return body

    M.install(
        cls, origin_ok=kw.get("origin_ok", lambda h: True),
        token_ok=kw.get("token_ok", lambda h: True),
        read_body=read_body,
        from_this_pc=kw.get("from_this_pc", lambda peer, local: peer == "127.0.0.1"))
    return cls, reads


def t_the_routes_are_pc_only_before_the_body_is_read():
    cls, reads = wired(body=b'{"ref": "cur:9b"}')
    phone = cls("/api/models/benchmark", peer="100.64.0.9")
    phone.do_POST()          # a refusal is SENT, so the wrapper returns None
    check("a phone request is 403 with the PC-only sentence",
          phone.sent == [(403, {"ok": False, "error": M.DESKTOP_ONLY_REFUSAL})],
          phone.sent)
    check("... and the body was never read", reads["n"] == 0, reads)
    phone_get = cls("/api/models/recommendations", peer="100.64.0.9")
    phone_get.do_GET()
    check("... the read route is PC-only too",
          phone_get.sent and phone_get.sent[0][0] == 403, phone_get.sent)

    cls, _ = wired(origin_ok=lambda h: False)
    h = cls("/api/models/recommendations")
    h.do_GET()
    check("the server's own origin check runs first",
          h.sent and h.sent[0][0] == 403
          and "cross-origin" in h.sent[0][1]["error"], h.sent)
    cls, _ = wired(token_ok=lambda h: False)
    h = cls("/api/models/recommendations")
    h.do_GET()
    check("... and its token check", h.sent and h.sent[0][0] == 401, h.sent)


def t_the_routes_dispatch_and_everything_else_is_untouched():
    saved = (M.check_models, M.run_benchmark, M.record_opinion, M.presets_only,
             M.recommendations_view)
    seen = {}

    def fake(name, answer):
        def call(*a, **k):
            seen[name] = (a, k)
            return 200, {"ok": True, "route": name}
        return call

    M.check_models = fake("check", None)
    M.run_benchmark = fake("benchmark", None)
    M.record_opinion = fake("opinion", None)
    M.presets_only = fake("presets", None)
    M.recommendations_view = fake("recommendations", None)
    try:
        cls, _ = wired(body=b'{"ref": "cur:9b"}')
        h = cls("/api/models/benchmark")
        check("POST /api/models/benchmark passes the ref through",
              h.do_POST() == 200 and seen["benchmark"][0] == ("cur:9b",),
              seen.get("benchmark"))
        cls, _ = wired(body=b'{"text": "keep it"}')
        h = cls("/api/presets/recommend/opinion")
        check("POST /api/presets/recommend/opinion passes the words through",
              h.do_POST() == 200 and seen["opinion"][0] == ("keep it",),
              seen.get("opinion"))
        cls, _ = wired()
        h = cls("/api/models/check"); h.do_POST()
        check("POST /api/models/check reaches check_models", "check" in seen)
        h = cls("/api/presets/recommend"); h.do_POST()
        check("POST /api/presets/recommend reaches presets_only", "presets" in seen)
        h = cls("/api/models/recommendations"); h.do_GET()
        check("GET reaches the read answer", "recommendations" in seen)
        h = cls("/api/approve"); h.do_POST()
        check("another POST route still goes to the original handler",
              h.calls == [("POST", "/api/approve")] and "check" not in h.sent,
              h.calls)
        h = cls("/api/work"); h.do_GET()
        check("... and another GET route too",
              h.calls == [("GET", "/api/work")], h.calls)
        cls, _ = wired(body=b"not json")
        h = cls("/api/models/check")
        check("a body that is not JSON is 400", h.do_POST() == 400, h.sent)
        cls, _ = wired(body=b"[]")
        h = cls("/api/presets/recommend")
        check("a body that is not an object is 400", h.do_POST() == 400, h.sent)
    finally:
        (M.check_models, M.run_benchmark, M.record_opinion, M.presets_only,
         M.recommendations_view) = saved
    check("install() advertises itself and is safe to call twice",
          "recommendations" in M.install(FakeHandler,
                                         origin_ok=lambda h: True,
                                         token_ok=lambda h: True,
                                         read_body=lambda h: b"{}")
          and "already on" in M.install(FakeHandler, origin_ok=lambda h: True,
                                        token_ok=lambda h: True,
                                        read_body=lambda h: b"{}"))


# --------------------------------------------------------------------------
#   The acts stay on the EXISTING carded routes
# --------------------------------------------------------------------------

def t_this_module_holds_no_download_and_no_apply():
    import ast
    src = (HERE / "jarvis_model_recommendations.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported, called = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = getattr(node.func.value, "id", "")
            called.add(f"{owner}.{node.func.attr}")
    check("no download, apply, switch or gate call in the module's code",
          not (called & {"jarvis_models.install", "MM.install",
                         "jarvis_presets.apply_preset", "jarvis_models.switch_to",
                         "jarvis_gate.check"}),
          sorted(called))
    check("... and no second HTTP stack or subprocess",
          not any(m.startswith("urllib.request") or m == "subprocess"
                  for m in imported), sorted(imported))
    check("the install route recommendation points at is the existing card",
          M.INSTALL_ROUTE == "/api/models/install", M.INSTALL_ROUTE)
    check("the apply route recommendation points at is the existing card",
          M.APPLY_ROUTE == P.APPLY_PATH == "/api/work/apply", M.APPLY_ROUTE)
    check("neither existing route has a handler in this module",
          M.INSTALL_ROUTE not in M.GET_PATHS + M.POST_PATHS
          and M.APPLY_ROUTE not in M.GET_PATHS + M.POST_PATHS)
    check("the five routes are exactly the contract's",
          M.GET_PATHS == ("/api/models/recommendations",)
          and M.POST_PATHS == ("/api/models/check", "/api/models/benchmark",
                               "/api/presets/recommend",
                               "/api/presets/recommend/opinion"),
          (M.GET_PATHS, M.POST_PATHS))
    def facts(path):
        """A module's string literals and the attribute calls it makes, through
        `ast` - structural facts, not a pin on the text: renaming the code
        around a route cannot make this red, and removing the route cannot
        leave it green."""
        import ast
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        strings = {node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        calls = {f"{getattr(node.func.value, 'id', '?')}.{node.func.attr}"
                 for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        return strings, calls

    hud_strings, hud_calls = facts(HERE.parent / "jarvis-backend" / "jarvis_hud.py")
    check("the published base still names the EXISTING install route and calls it",
          "/api/models/install" in hud_strings
          and bool({"MM.install", "jarvis_models.install"} & hud_calls),
          sorted(c for c in hud_calls if c.endswith(".install")))
    check("the EXISTING preset apply card is untouched",
          P.APPLY_PATH == "/api/work/apply"
          and P.SWITCH_ROUTE == "/api/models/switch"
          and callable(P.apply_preset), (P.APPLY_PATH, P.SWITCH_ROUTE))


# --------------------------------------------------------------------------
#   The store is defensive
# --------------------------------------------------------------------------

def t_a_damaged_store_reads_as_empty():
    path = TMP / "damaged.json"
    path.write_text("{not json", encoding="utf-8")
    doc = M.load_store(path)
    check("unreadable JSON reads as an empty store", doc["checked_at"] is None
          and doc["candidates"] == [] and doc["benchmarked"] == {}, doc)
    path.write_text(json.dumps({
        "checked_at": "yesterday",
        "candidates": [{"ref": "ok:1b", "fit": "sideways"},
                       {"not": "a candidate"}, 7],
        "benchmarked": {"a:1b": {"tokens_per_s": 20, "vram_gb": 3},
                        "b:1b": {"vram_gb": 4},
                        "c:1b": "nonsense"},
        "opinions": [{"text": "keep", "rule": "keep", "at": 1}, {"nope": 1}],
    }), encoding="utf-8")
    doc = M.load_store(path)
    check("a non-numeric checked_at is dropped, not shown", doc["checked_at"] is None)
    check("a bad fit word becomes 'no' and junk candidates are dropped",
          [c["ref"] for c in doc["candidates"]] == ["ok:1b"]
          and doc["candidates"][0]["fit"] == "no", doc["candidates"])
    check("a benchmark with no measured rate is not a benchmark",
          list(doc["benchmarked"]) == ["a:1b"], doc["benchmarked"])
    check("a malformed opinion is dropped",
          [o["text"] for o in doc["opinions"]] == ["keep"], doc["opinions"])
    check("the atomic write leaves no .tmp behind",
          M.save_store(M._empty_store(), path) is None
          and not path.with_suffix(".json.tmp").exists())


# --------------------------------------------------------------------------

def main() -> int:
    for fn in (
        t_the_cards_are_mapped_to_the_preset_lanes_and_intake_is_honest,
        t_the_read_answer_is_the_contract_shape_and_touches_no_network,
        t_the_check_caches_candidates_and_never_downloads,
        t_check_refuses_when_no_card_was_measured_and_does_no_lookup,
        t_check_refuses_honestly_without_the_catalogue_module,
        t_the_check_answer_has_no_fit_claim_without_an_estimate,
        t_benchmark_refuses_an_uninstalled_model_before_measuring,
        t_benchmark_measures_stores_and_returns_the_measurement,
        t_benchmark_stores_nothing_when_it_cannot_measure,
        t_a_recommendation_cites_the_measured_numbers_and_nothing_else,
        t_no_change_is_recommended_without_both_sides_measured,
        t_a_faster_model_that_would_shrink_the_window_is_not_recommended,
        t_a_gain_below_the_bar_is_not_worth_a_download,
        t_the_context_a_model_reports_corrects_a_preset_that_asks_for_more,
        t_a_model_too_big_for_its_lane_moves_to_the_card_that_can_hold_it,
        t_pending_and_heavy_presets_are_never_recommended,
        t_the_real_preset_rows_are_what_is_read,
        t_the_opinion_rules_are_deterministic,
        t_keep_suppresses_the_model_and_lane_change_but_not_a_context_correction,
        t_raise_lowers_the_bar_and_lower_prefers_a_smaller_footprint,
        t_quality_uses_the_only_measured_capability_figure_and_says_so,
        t_an_unknown_opinion_is_recorded_and_changes_nothing,
        t_the_routes_are_pc_only_before_the_body_is_read,
        t_the_routes_dispatch_and_everything_else_is_untouched,
        t_this_module_holds_no_download_and_no_apply,
        t_a_damaged_store_reads_as_empty,
    ):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
