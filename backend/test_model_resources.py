"""The "Loaded now / Resources" read: what is loaded, where, at what context,
and what Jarvis itself is costing - read-only, honest when it cannot know.

    py -3 backend/test_model_resources.py

WHAT EACH BLOCK PROVES

  * the CHAT lane is resolved the product's own way - the loopback
    `presets-active-lane.json` under the config folder, `OLLAMA_URL` only as the
    documented fallback - not `/api/presets`' lane and not a module constant.
  * every known lane answers honestly: a loaded model carries its context size,
    its video-memory size, its percent on the card and the cards carrying it; a
    lane with nothing loaded says "nothing loaded"; a lane that does not answer
    says it is not running. None of them reports 0 as a fact.
  * spill is reported as spill: `size_vram` below `size` becomes a percent and
    a MiB figure in words, and 100% / equal sizes say nothing spilled.
  * cards: per-card total/used/free come from nvidia-smi, and the local model
    servers' `used_memory` is added up per card so "how much of this is Jarvis's
    own models" is a measured number - the rest is left as other programs' use.
  * Jarvis's own process: resident memory, private memory, processor seconds and
    an average percent, handles and uptime come from the OS. An unreadable
    process says so in words, never a fabricated 0.
  * an unreadable graphics-card query says "no graphics card could be asked"
    rather than showing empty numbers as truth.
  * the route: `jarvis_model_recommendations.install()` serves
    `GET /api/models/resources` as a READ, PC-only, with the same origin/token
    checks as its neighbour, and a broken resources read answers
    `available: false` instead of failing the route.
  * the "Measured results" card's read (`GET /api/models/measured`): only the
    stored rows of `jarvis_bench`'s TWO stores are returned - a repeat row is
    not a run, a failed run keeps its own reason, a skipped suite says skipped
    and has no score, a prompt handed in by mistake never reaches the card - and
    an empty store says WHICH file is missing and which door starts a run. The
    real `jarvis_bench` stores are used, so the selection is proved against the
    code that writes them, never against a second copy of the shape.
  * this module cannot write, load, switch or apply anything: it contains no
    write call, no model load, no `/api/pull`, no requests/post and no subprocess
    at import time (the one subprocess call is the read-only nvidia-smi/netstat
    query, run when the route is asked, never on import).
"""
import ast
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_model_recommendations as M  # noqa: E402
import jarvis_model_resources as R  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="model-resources-"))
(TMP / "presets-choice.json").write_text(json.dumps({"preset": "coding"}),
                                         encoding="utf-8")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name +
          (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Fixtures: a small PC, injection only (no live GPU, no network, no model)
# --------------------------------------------------------------------------
GPU_LINES = [
    "0, GPU-aaa, NVIDIA GeForce RTX 2060, 12288, 6064, 6224, Disabled",
    "1, GPU-bbb, NVIDIA GeForce RTX 2080 SUPER, 8192, 4131, 4061, Enabled",
    "2, GPU-ccc, NVIDIA GeForce RTX 2080 SUPER, 8192, 5463, 2729, Disabled",
]
APP_LINES = [
    "GPU-aaa, 4242, ollama.exe, 5700",
    "GPU-bbb, 4242, ollama.exe, 4000",
    "GPU-ccc, 4242, ollama.exe, 5200",
    "GPU-bbb, 7777, game.exe, 60",
]
SMI = {"gpus": GPU_LINES, "apps": APP_LINES, "error": ""}


def preset_rows():
    return [
        {"id": "general", "title": "General", "model": "qwen3.5:9b", "lane": "main"},
        {"id": "fast", "title": "Fast", "model": "qwen3.5:4b", "lane": "coding"},
        {"id": "coding", "title": "Coding",
         "model": "qwen3-coder-30b-a3b-ud-q3-k-xl", "lane": "pooled"},
    ]


LANES = [
    {"key": "main", "port": 11436, "label": "the everyday lane",
     "card": "RTX 2060", "words": "the long-context card"},
    {"key": "coding", "port": 11435, "label": "the Fast preset's lane",
     "card": "RTX 2080 SUPER", "words": "the fast card"},
    {"key": "pooled", "port": 11450, "label": "the Coding preset's lane (all three cards)",
     "card": "all three cards", "words": "one model across all three cards"},
]

PS = {
    "http://127.0.0.1:11450": {"models": [{
        "name": "qwen3-coder-30b-a3b-ud-q3-k-xl:latest",
        "context_length": 8192,
        "size": 14_497_590_799,
        "size_vram": 14_497_590_799,
    }]},
    "http://127.0.0.1:11436": {"models": []},
}


def get_json(url):
    if url.endswith("/api/ps"):
        lane = url[:-len("/api/ps")]
        if lane in PS:
            return 200, PS[lane], ""
        return 0, None, "ConnectionRefusedError: the lane is down"
    return 404, None, "not used"


def listen(ports):
    return {11450: 4242, 11436: 4343}, ""


def process_stats(pid):
    if pid == 4242:
        return {"available": True, "pid": 4242, "rss_mb": 130.5, "private_mb": 120.0,
                "cpu_seconds": 10.0, "cpu_percent": 2.5, "handles": 400, "uptime_s": 400}
    if pid == 4343:
        return {"available": False, "why": "the process could not be opened for a read"}
    return {"available": True, "pid": pid, "rss_mb": 210.5, "private_mb": 195.2,
            "cpu_seconds": 300.0, "cpu_percent": 3.0, "handles": 812,
            "uptime_s": 10_000}


def run_collect(**overrides):
    # THE OWNER'S LIVE PRESET CHOICE MUST NOT DECIDE THIS SUITE'S ANSWER.
    # `collect()` asks `jarvis_presets.choice()` for the last applied preset,
    # and that module reads `OPENJARVIS_CONFIG_DIR` (or ~/.openjarvis) whatever
    # this test passes as `config_dir`. On 2026-11-09 the desk run went red only
    # because the owner's own machine had "general_uncensored" chosen while the
    # fixture says "coding" - a suite that reads the live config is a suite that
    # fails for a reason that has nothing to do with the code. The variable is
    # pointed at this run's temp folder for the call, so the fixture is the
    # only answer and the previous value is put back afterwards.
    kwargs = dict(config_dir=TMP, preset_rows=preset_rows(), lanes=LANES,
                  active_lane={"url": "http://127.0.0.1:11450",
                               "source": "presets-active-lane.json",
                               "file": str(TMP / "presets-active-lane.json"),
                               "fallback": False},
                  get_json=get_json, smi=SMI, listen=listen,
                  process_stats=process_stats, now=1_760_000_000.0,
                  jarvis_pid=999)
    kwargs.update(overrides)
    saved = os.environ.get("OPENJARVIS_CONFIG_DIR")
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
    try:
        return R.collect(**kwargs)
    finally:
        if saved is None:
            os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
        else:
            os.environ["OPENJARVIS_CONFIG_DIR"] = saved


# --------------------------------------------------------------------------
#   Words: the pure helpers
# --------------------------------------------------------------------------
def t_word_helpers_are_honest():
    check("three cards are named as the owner's three cards",
          R.cards_words([2, 1, 0]) == "all three graphics cards (0, 1, 2)",
          R.cards_words([2, 1, 0]))
    check("one card is named as one card",
          R.cards_words([2]) == "graphics card 2", R.cards_words([2]))
    check("two cards are named as two", R.cards_words([0, 1]) ==
          "graphics cards 0 and 1", R.cards_words([0, 1]))
    check("no reported card is a sentence, not 'card 0'",
          "no graphics card" in R.cards_words([])
          and "0" not in R.cards_words([]).replace("(0", ""), R.cards_words([]))
    check("a context size is thousands-separated", R.context_words(8192) ==
          "8,192 tokens of context", R.context_words(8192))
    check("an unreported context size says so",
          R.context_words(None) == "the context size was not reported")
    check("zero spill says nothing spilled",
          R.spill_words(0, 100) == "nothing spilled into system RAM",
          R.spill_words(0, 100))
    check("a real spill names MiB and the percent",
          "3,762,835,946" not in R.spill_words(3_762_835_946, 74)
          and "MiB spilled into system RAM (74% on the cards)"
          in R.spill_words(3_762_835_946, 74), R.spill_words(3_762_835_946, 74))
    check("gigabyte and gibibyte words are not swapped",
          R.gb_words(12288) == "12.0 GB" and R.gib_words(14_497_590_799) == "13.5 GiB",
          (R.gb_words(12288), R.gib_words(14_497_590_799)))


# --------------------------------------------------------------------------
#   The lane answer
# --------------------------------------------------------------------------
def t_the_active_lane_is_the_product_file_not_a_constant():
    answer = run_collect()
    active = answer["active_lane"]
    check("the chat lane is the pooled lane from the product's file",
          active["url"] == "http://127.0.0.1:11450"
          and active["source"] == "presets-active-lane.json"
          and active["fallback"] is False, active)
    check("the chosen preset's title rides along",
          active["preset"] == "coding" and active["preset_title"] == "Coding",
          active)
    check("the words name the preset's lane",
          "pooled" not in active["words"] and "Coding" in active["words"],
          active["words"])


def t_a_loaded_lane_reports_context_size_size_and_cards():
    answer = run_collect()
    pooled = [l for l in answer["lanes"] if l["key"] == "pooled"][0]
    check("the pooled lane is LOADED", pooled["state"] == "loaded"
          and pooled["loaded"] is True, pooled)
    check("its model is named", pooled["model"] ==
          "qwen3-coder-30b-a3b-ud-q3-k-xl:latest", pooled["model"])
    check("its real context size is reported", pooled["context_length"] == 8192,
          pooled["context_length"])
    check("size_vram equal to size is 100% with no spill",
          pooled["on_card_percent"] == 100 and pooled["spill_bytes"] == 0, pooled)
    check("the three cards carrying it are named",
          pooled["gpu_indices"] == [0, 1, 2]
          and "all three graphics cards (0, 1, 2)" in pooled["words"],
          (pooled["gpu_indices"], pooled["words"]))
    check("the loaded words say 0 spill without a fake number",
          "nothing spilled" not in pooled["words"]
          and "100% on all three graphics cards" in pooled["words"], pooled["words"])
    check("nothing is said as 0 for a model that is not loaded",
          all(l["model"] is None or l["state"] == "loaded" for l in answer["lanes"]))


def t_not_loaded_and_unreachable_lanes_say_so():
    answer = run_collect()
    main = [l for l in answer["lanes"] if l["key"] == "main"][0]
    coding = [l for l in answer["lanes"] if l["key"] == "coding"][0]
    check("a lane with an empty /api/ps says 'nothing loaded'",
          main["state"] == "not_loaded" and main["words"] == "nothing loaded"
          and main["size_bytes"] is None, main)
    check("a lane that does not answer says it is not running",
          coding["state"] == "unreachable"
          and "not running" in coding["words"] and "11435" in coding["words"],
          coding)
    check("an unreachable lane is not a pass and not a zero",
          coding["loaded"] is False and coding["on_card_percent"] is None
          and coding["spill_bytes"] is None, coding)


def t_spill_is_reported_as_spill_not_hidden():
    ps = dict(PS)
    ps["http://127.0.0.1:11450"] = {"models": [{
        "name": "qwen3-coder-30b-a3b-ud-q3-k-xl:latest",
        "context_length": 16384, "size": 1000, "size_vram": 740}]}
    answer = run_collect(get_json=lambda url: (
        (200, ps[url[:-len("/api/ps")]], "") if url.endswith("/api/ps")
        and url[:-len("/api/ps")] in ps else (0, None, "down")))
    pooled = [l for l in answer["lanes"] if l["key"] == "pooled"][0]
    check("a partial load reports the percent and the spill",
          pooled["on_card_percent"] == 74 and pooled["spill_bytes"] == 260
          and "74% on the cards" in pooled["words"]
          and "spilled into system RAM" in pooled["words"], pooled)
    check("... and the spill is not rounded away to 'no spill'",
          "nothing spilled" not in pooled["words"])


def t_a_driver_that_reports_no_per_program_memory_is_said_not_guessed():
    smi = {"gpus": GPU_LINES, "apps": [
        "GPU-aaa, 18496, C:\\Ollama\\llama-server.exe, [N/A]",
        "GPU-bbb, 18496, C:\\Ollama\\llama-server.exe, [N/A]",
        "GPU-ccc, 18496, C:\\Ollama\\llama-server.exe, [N/A]",
    ], "error": ""}
    answer = run_collect(smi=smi)
    check("a driver that reports [N/A] leaves the per-card share unknown, not 0",
          answer["gpu_share"]["known"] is False
          and all(g["jarvis_mb"] is None and g["other_mb"] is None
                  for g in answer["gpus"]), answer["gpu_share"])
    check("... the loaded model's total video memory is still a measured fact",
          answer["gpu_share"]["loaded_vram_gib"] == 13.5
          and answer["gpu_share"]["cards"] == [0, 1, 2], answer["gpu_share"])
    check("... and the answer says why the per-card split is missing",
          any("is not reported by this PC's graphics driver" in n
              for n in answer["notes"]), answer["notes"])
    check("the model server's own cards still name the three cards",
          [l for l in answer["lanes"] if l["loaded"]][0]["gpu_indices"] == [0, 1, 2])


def t_cards_and_jarvis_share_are_measured():
    answer = run_collect()
    gpus = {int(g["index"]): g for g in answer["gpus"]}
    check("all three cards are reported", sorted(gpus) == [0, 1, 2], sorted(gpus))
    check("per-card total/used/free come from nvidia-smi",
          gpus[0]["total_mb"] == 12288 and gpus[0]["used_mb"] == 6064
          and gpus[0]["free_mb"] == 6224, gpus[0])
    check("the local models' memory is added up per card",
          gpus[0]["jarvis_mb"] == 5700 and gpus[1]["jarvis_mb"] == 4000
          and gpus[2]["jarvis_mb"] == 5200, [g["jarvis_mb"] for g in answer["gpus"]])
    check("other programs' use is the remainder, never negative",
          gpus[1]["other_mb"] == 131, gpus[1])
    jarvis = answer["jarvis"]
    check("Jarvis's own resident memory is the process's real number",
          jarvis["available"] is True and jarvis["rss_mb"] == 210.5, jarvis)
    check("... and its processor use is an average, labelled in the words",
          jarvis["cpu_percent"] == 3.0 and "3.0% of the processor" in jarvis["words"],
          jarvis)
    check("the model servers' own RAM is carried too",
          jarvis["model_servers_rss_mb"] == 130.5
          and "130 MiB more" in jarvis["words"], jarvis)
    check("a headline says what is loaded and on which cards",
          any("qwen3-coder" in w for w in answer["words"])
          and any("card 0 has" in w for w in answer["words"]), answer["words"])


def t_an_unreadable_process_is_said_not_invented():
    answer = run_collect(process_stats=lambda pid: {
        "available": False, "why": "the process could not be opened for a read"})
    jarvis = answer["jarvis"]
    check("an unreadable Jarvis process says so in words",
          jarvis["available"] is False and "could not be read" in jarvis["words"],
          jarvis)
    check("... and no 0 is shown as its memory use", jarvis.get("rss_mb") is None)


def t_an_unreadable_card_query_is_said_not_zeroes():
    answer = run_collect(smi={"gpus": [], "apps": [], "error": "nvidia-smi: not found"})
    check("no cards means no cards, in a warning",
          answer["gpus"] == [] and any("No graphics card could be asked" in w
                                       for w in answer["warnings"]),
          answer["warnings"])
    check("the lanes still answer honestly without card facts",
          any(l["state"] == "loaded" for l in answer["lanes"])
          and all("no graphics card (or the cards" in l["words"]
                  for l in answer["lanes"] if l["state"] == "loaded"))


def t_the_product_file_fallback_is_used_and_named():
    answer = run_collect(active_lane={"url": "http://127.0.0.1:11434",
                                      "source": "OLLAMA_URL",
                                      "file": str(TMP / "missing.json"),
                                      "fallback": True})
    active = answer["active_lane"]
    check("with no product file the default Ollama lane is named as a fallback",
          active["fallback"] is True and "default Ollama lane" in active["words"],
          active)


def t_the_active_lane_file_rule_is_the_products():
    cfg = TMP / "cfg"
    cfg.mkdir(exist_ok=True)
    (cfg / R.ACTIVE_LANE_FILE).write_text(
        json.dumps({"base_url": "http://192.168.1.9:11450"}), encoding="utf-8")
    out = R._active_lane(cfg, "http://127.0.0.1:11434")
    check("a non-loopback base_url is ignored, exactly like jarvis_hud",
          out["fallback"] is True and out["url"] == "http://127.0.0.1:11434", out)
    (cfg / R.ACTIVE_LANE_FILE).write_text(
        json.dumps({"base_url": "http://127.0.0.1:11450/"}), encoding="utf-8")
    out = R._active_lane(cfg, "http://127.0.0.1:11434")
    check("a loopback base_url is accepted and trailing slashes are dropped",
          out["fallback"] is False and out["url"] == "http://127.0.0.1:11450", out)


# --------------------------------------------------------------------------
#   The route
# --------------------------------------------------------------------------
def t_the_resources_route_is_wired_read_only_and_pc_only():
    check("the route is on the module's GET list and not its POST list",
          M.PATH_RESOURCES == "/api/models/resources"
          and M.PATH_RESOURCES in M.GET_PATHS
          and M.PATH_RESOURCES not in M.POST_PATHS,
          (M.GET_PATHS, M.POST_PATHS))

    class FakeHandler:
        def __init__(self, path, peer="127.0.0.1", local="127.0.0.1"):
            self.path = path
            self.client_address = (peer, 5555)
            from types import SimpleNamespace
            self.connection = SimpleNamespace(getsockname=lambda: (local, 8765))
            self.sent = []

        def _send(self, code, payload):
            self.sent.append((code, payload))
            return code

        def do_GET(self):
            return -4

        def do_POST(self):
            return -5

    cls = type("H", (FakeHandler,), {})
    M.install(cls, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: b"{}", from_this_pc=lambda p, l: p == "127.0.0.1")
    saved = R.collect
    try:
        R.collect = lambda: {"available": True, "read_at_words": "21:52:03",
                             "probe": "called"}
        h = cls("/api/models/resources")
        h.do_GET()
        check("GET /api/models/resources answers from the resources read",
              h.sent and h.sent[0][0] == 200
              and h.sent[0][1].get("probe") == "called", h.sent)
        phone = cls("/api/models/resources", peer="100.64.0.9")
        phone.do_GET()
        check("... and a phone is refused before the read",
              phone.sent and phone.sent[0][0] == 403
              and "pc" in json.dumps(phone.sent[0][1]).lower(), phone.sent)

        def boom():
            raise RuntimeError("nvidia-smi exploded")
        R.collect = boom
        h = cls("/api/models/resources")
        h.do_GET()
        check("a broken resources read answers available:false, not a 500",
              h.sent and h.sent[0][0] == 200
              and h.sent[0][1].get("available") is False
              and "why" in h.sent[0][1], h.sent)
    finally:
        R.collect = saved


# --------------------------------------------------------------------------
#   "Measured results": the two stores jarvis_bench writes, read only
# --------------------------------------------------------------------------
def t_the_measured_route_is_wired_read_only_and_pc_only():
    check("the measured route is on the module's GET list and not its POST list",
          M.PATH_MEASURED == "/api/models/measured"
          and M.PATH_MEASURED in M.GET_PATHS
          and M.PATH_MEASURED not in M.POST_PATHS,
          (M.GET_PATHS, M.POST_PATHS))

    class FakeHandler:
        def __init__(self, path, peer="127.0.0.1", local="127.0.0.1"):
            self.path = path
            self.client_address = (peer, 5555)
            from types import SimpleNamespace
            self.connection = SimpleNamespace(getsockname=lambda: (local, 8765))
            self.sent = []

        def _send(self, code, payload):
            self.sent.append((code, payload))
            return code

        def do_GET(self):
            return -4

        def do_POST(self):
            return -5

    cls = type("H", (FakeHandler,), {})
    M.install(cls, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: b"{}", from_this_pc=lambda p, l: p == "127.0.0.1")
    saved = R.measured
    try:
        R.measured = lambda **kw: {"available": True, "read_at_words": "21:52:03",
                                   "probe": "called"}
        h = cls("/api/models/measured")
        h.do_GET()
        check("GET /api/models/measured answers from the measured read",
              h.sent and h.sent[0][0] == 200
              and h.sent[0][1].get("probe") == "called", h.sent)
        phone = cls("/api/models/measured", peer="100.64.0.9")
        phone.do_GET()
        check("... and a phone is refused before the read",
              phone.sent and phone.sent[0][0] == 403, phone.sent)

        def boom(**kw):
            raise RuntimeError("bench store exploded")
        R.measured = boom
        h = cls("/api/models/measured")
        h.do_GET()
        check("a broken measured read answers available:false, not a 500",
              h.sent and h.sent[0][0] == 200
              and h.sent[0][1].get("available") is False
              and "why" in h.sent[0][1], h.sent)
    finally:
        R.measured = saved


def t_measured_reads_only_stored_rows_and_says_why_it_is_empty():
    import time
    import jarvis_bench as B
    log = B.BenchLog(TMP / "bench.jsonl")
    scores = B.ScoreLog(TMP / "bench-scores.jsonl")

    empty = R.measured(bench_log=log, score_log=scores, now=1_760_000_000)
    check("an empty card is still an answer, not a failure",
          empty["available"] is True, empty)
    check("... with no invented row and both counts at zero",
          empty["runs"] == [] and empty["scorecards"] == []
          and empty["counts"] == {"runs": 0, "scorecards": 0}, empty)
    check("... and the empty state names the missing speed-run file",
          "no speed run is on file yet" in empty["empty"]["runs"].lower()
          and "bench.jsonl" in empty["empty"]["runs"]
          and "benchmark on this pc" in empty["empty"]["runs"].lower(),
          empty["empty"]["runs"])
    check("... and the missing scorecard file, with the door that fills it",
          "no five-suite scorecard is on file yet" in empty["empty"]["scorecards"].lower()
          and "bench-scores.jsonl" in empty["empty"]["scorecards"]
          and "start the benchmark suites" in
          empty["empty"]["scorecards"].lower(),
          empty["empty"]["scorecards"])
    check("... and the stores' own names and presence are reported",
          empty["stores"]["speed"] == {"name": "bench.jsonl", "exists": False}
          and empty["stores"]["scores"] == {"name": "bench-scores.jsonl",
                                            "exists": False},
          empty["stores"])

    check("a real speed run is written by the real store",
          log.append({"kind": "bench-run", "model": "qwen3:8b",
                      "lane": "everyday", "preset": "general", "at": 1000,
                      "gen_median": 41.2, "prefill_median": 900.5, "ok": True,
                      "spilled": False,
                      "words": "qwen3:8b on the everyday lane: 41.2 tokens a second."}))
    # A REPEAT row is not a run: the card must not read one as the other.
    log.append({"kind": "bench", "model": "qwen3:8b", "at": 1500,
                "gen_tokens_per_s": 40.0})
    log.append({"kind": "bench-run", "model": "qwen3:4b", "lane": "main",
                "at": 2000, "ok": False, "why": "no repeat produced a number",
                "words": "Nothing was measured: no repeat produced a number."})
    scores.append({"kind": "bench-suite", "model": "qwen3:8b", "suite": "coding",
                   "at": 3000, "score_pct": 83.33, "items": 6, "items_passed": 5,
                   "decode_tps": 41.2, "ctx": 8192, "passed": True,
                   "skipped": False, "quant": "Q4_K_M",
                   "words": "5 of 6 coding tasks passed."})
    scores.append({"kind": "bench-suite", "model": "qwen3:8b",
                   "suite": "vision_ocr", "at": 4000, "skipped": True,
                   "words": "Vision / OCR: not run - the model does not report vision."})
    # A field no store may carry must never reach the card, even if handed in.
    log.append({"kind": "bench-run", "model": "qwen3:1b", "lane": "coding",
                "at": 5000, "ok": False, "prompt": "the owner's secret words"})

    out = R.measured(bench_log=log, score_log=scores)
    check("only stored RUN rows are read: a repeat row is not a run",
          out["counts"]["runs"] == 3 and len(out["runs"]) == 3, out["counts"])
    check("the newest run is first", out["runs"][0]["model"] == "qwen3:1b",
          [r.get("model") for r in out["runs"]])
    check("a failed run is shown with its own reason, not hidden or scored",
          out["runs"][1].get("ok") is False
          and out["runs"][1].get("why") == "no repeat produced a number"
          and "gen_median" not in out["runs"][1], out["runs"][1])
    good = out["runs"][2]
    check("a measured run carries the stored numbers, never a re-rounding",
          good.get("gen_median") == 41.2 and good.get("prefill_median") == 900.5,
          good)
    check("... and the sentence the benchmark itself wrote",
          good.get("words") == "qwen3:8b on the everyday lane: 41.2 tokens a second.",
          good.get("words"))
    check("... dated on this PC's own clock",
          good.get("day") == time.strftime("%Y-%m-%d", time.localtime(1000)),
          (good.get("at"), good.get("day")))
    check("no prompt or answer text reaches the card",
          "secret" not in json.dumps(out).lower(), json.dumps(out)[:200])
    check("the newest scorecard is first", out["scorecards"][0]["suite"] == "vision_ocr",
          [s.get("suite") for s in out["scorecards"]])
    check("a suite the model could not run says skipped, with no score",
          out["scorecards"][0].get("skipped") is True
          and "score_pct" not in out["scorecards"][0], out["scorecards"][0])
    coding = out["scorecards"][1]
    check("a measured scorecard carries its score, items and the store's sentence",
          coding.get("score_pct") == 83.33 and coding.get("items") == 6
          and coding.get("items_passed") == 5 and coding.get("decode_tps") == 41.2
          and coding.get("ctx") == 8192 and coding.get("quant") == "Q4_K_M"
          and coding.get("words") == "5 of 6 coding tasks passed.", coding)
    check("the suite label comes from jarvis_bench's own SUITES table",
          coding.get("suite_label") == "Coding"
          and out["scorecards"][0].get("suite_label") == "Vision / OCR",
          [s.get("suite_label") for s in out["scorecards"]])
    check("the empty reasons are blank when the rows are there",
          out["empty"] == {"runs": "", "scorecards": ""}, out["empty"])
    check("the headline says the numbers were measured on this PC",
          any("measured on this pc" in w.lower() for w in out["words"]), out["words"])

    limited = R.measured(bench_log=log, score_log=scores, limit_runs=1,
                         limit_scores=1)
    check("the shown rows are limited but the counts are everything stored",
          len(limited["runs"]) == 1 and len(limited["scorecards"]) == 1
          and limited["counts"] == {"runs": 3, "scorecards": 2},
          (limited["counts"], len(limited["runs"]), len(limited["scorecards"])))

    saved = sys.modules.get("jarvis_bench")
    sys.modules["jarvis_bench"] = None
    try:
        gone = R.measured(bench_log=log, score_log=scores)
    finally:
        if saved is not None:
            sys.modules["jarvis_bench"] = saved
        else:
            sys.modules.pop("jarvis_bench", None)
    check("no benchmark module says so and invents nothing",
          gone["available"] is False and gone["runs"] == []
          and gone["scorecards"] == []
          and "will not invent one" in gone["why"], gone)

    src = (HERE / "jarvis_model_resources.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    measured_fn = next((n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == "measured"),
                       None)
    calls = {getattr(n.func, "attr", "") for n in ast.walk(measured_fn or ast.Module(
        body=[], type_ignores=[])) if isinstance(n, ast.Call)}
    check("the read goes through jarvis_bench's own readers, not a file of its own",
          measured_fn is not None and {"runs", "score_history"} <= calls
          and not ({"open", "read_text", "write_text"} & calls), sorted(calls))


# --------------------------------------------------------------------------
#   The module cannot act
# --------------------------------------------------------------------------
def t_the_module_cannot_write_load_or_apply():
    src = (HERE / "jarvis_model_resources.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    loaded = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            loaded.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            loaded.add(node.module)
    check("no HTTP client, requests or model runtime runs at import time",
          not any(m.startswith(("urllib.request", "requests")) or m in
                  ("subprocess", "ollama") for m in loaded), sorted(loaded))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", getattr(func, "id", ""))
            if name:
                called.add(name)
    forbidden = {"write_text", "write_bytes", "unlink", "remove", "rmdir",
                 "switch_to", "apply_preset", "install", "pull", "rm"}
    check("the code calls no write, load, switch or apply function",
          not (called & forbidden), sorted(called & forbidden))
    check("no download or install route appears even in the words",
          "/api/pull" not in src and "/api/models/install" not in src,
          "a forbidden route word")
    check("the one subprocess call is the read-only nvidia-smi/netstat query",
          "capture_output=True" in src and '"nvidia-smi"' in src
          and '"netstat"' in src)


def t_the_route_contract_still_names_the_existing_cards():
    check("install and apply are still the existing carded routes",
          M.INSTALL_ROUTE == "/api/models/install"
          and M.APPLY_ROUTE == "/api/work/apply", (M.INSTALL_ROUTE, M.APPLY_ROUTE))


def t_ps_parsing_keeps_a_missing_context_as_unknown():
    out = R._lane_ps("http://127.0.0.1:11450", get_json=lambda url: (
        200, {"models": [{"name": "m:latest", "size": 100, "size_vram": 50}]}, ""))
    model = out["models"][0]
    check("a lane that does not report its context keeps it unknown",
          model["context_length"] is None, model)
    check("... while still reporting the real percent and spill",
          model["on_card_percent"] == 50 and model["spill_bytes"] == 50, model)
    junk = R._lane_ps("http://127.0.0.1:11450", get_json=lambda url: (
        200, {"models": ["nonsense", {"name": ""}, {"name": "ok:1"}]}, ""))
    check("junk rows are dropped, not crashed on",
          [m["name"] for m in junk["models"]] == ["ok:1"], junk)


# --------------------------------------------------------------------------
def main():
    for fn in (
        t_word_helpers_are_honest,
        t_the_active_lane_is_the_product_file_not_a_constant,
        t_a_loaded_lane_reports_context_size_size_and_cards,
        t_not_loaded_and_unreachable_lanes_say_so,
        t_spill_is_reported_as_spill_not_hidden,
        t_a_driver_that_reports_no_per_program_memory_is_said_not_guessed,
        t_cards_and_jarvis_share_are_measured,
        t_an_unreadable_process_is_said_not_invented,
        t_an_unreadable_card_query_is_said_not_zeroes,
        t_the_product_file_fallback_is_used_and_named,
        t_the_active_lane_file_rule_is_the_products,
        t_the_resources_route_is_wired_read_only_and_pc_only,
        t_the_measured_route_is_wired_read_only_and_pc_only,
        t_measured_reads_only_stored_rows_and_says_why_it_is_empty,
        t_the_module_cannot_write_load_or_apply,
        t_the_route_contract_still_names_the_existing_cards,
        t_ps_parsing_keeps_a_missing_context_as_unknown,
    ):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
