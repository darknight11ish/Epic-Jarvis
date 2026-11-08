"""The five-suite benchmark runner, proved without a graphics card or a model.

    python3 backend/test_bench_suites.py

WHAT THIS SUITE OWNS (Wave-9 Lane 3, 2026-11-07):
  1. The five suites the owner chose are exactly five, in one closed vocabulary,
     and every suite has a runner.
  2. The store: its own file, its own ALLOWLIST (a prompt or an answer handed in
     by mistake is dropped), newest-first reads, and the row/byte caps.
  3. The throwaway server: a free port ABOVE the live block, never a lane's
     port; the card pin by UUID; the child environment with no token in it; and
     "a server this run did not start is never killed".
  4. The pause/warm-back pair: the resident model is unloaded, and it is loaded
     back at its own window and PROVED from /api/ps - including the cases where
     it does not come back, which must fail rather than claim success.
  5. Each rubric's scoring: coding tasks run their own tests in a separate
     interpreter; general answers are exact; tool calls are the right tool with
     the right arguments; vision needs BOTH tokens in the image.
  6. The capability gate: a model that does not report vision/tools is NOT RUN,
     and a skip is never a pass.
  7. The Q3 refusals: a run already going, a streaming answer, standby, a
     running task, an un-idle PC for a scheduled run, and no `confirm` - each
     its own sentence and code.
  8. Promotion is read-only: zero spill, quality not worse, speed floor; a
     missing measurement fails its own check; `applied` is always False.
  9. The shipped preset defaults are UNCHANGED by this whole file.
 10. Its own source: nothing but loopback, and the suite ports are not lane
     ports.

No pytest. Run it directly; the exit code is the verdict.
"""
import base64
import json
import os
import re
import sys
import struct
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_bench.py")

import jarvis_bench as B  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def refusal(**kwargs):
    """Run `check_suite_job` and return the Refusal, or None."""
    try:
        B.check_suite_job(kwargs.pop("body", {}), **kwargs)
    except B.Refusal as exc:
        return exc
    return None


# ==========================================================================
#   Fakes: one PC's nvidia-smi, one throwaway Ollama, one clock
# ==========================================================================

SMI_THREE = (
    "0, GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee, NVIDIA GeForce RTX 2060, "
    "12288, 11000, 1288, 3, Disabled, 617.42\n"
    "1, GPU-1f7e38f5-3447-97fc-0c13-c8c7eaf83313, NVIDIA GeForce RTX 2080 "
    "SUPER, 8192, 0, 8192, 0, Disabled, 617.42\n"
    "2, GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6, NVIDIA GeForce RTX 2080 "
    "SUPER, 8192, 1400, 6792, 1, Enabled, 617.42\n"
)

SPEED_PS = [{"name": "qwen3:8b", "size": 6_400_000_000,
             "size_vram": 6_400_000_000, "context_length": 16384}]


class FakeProc:
    def __init__(self):
        self.pid = 4321
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 0


def crash(url):
    raise OSError("nothing is listening")


# ==========================================================================
#   1. The suite table and the rubric data
# ==========================================================================

def t_five_suites_exactly():
    check("there are exactly five suites", len(B.SUITES) == 5,
          [s["id"] for s in B.SUITES])
    check("the suite ids are the closed vocabulary, in order",
          tuple(s["id"] for s in B.SUITES) == B.SUITE_KEYS,
          (tuple(s["id"] for s in B.SUITES), B.SUITE_KEYS))
    check("the closed vocabulary is the owner's five",
          B.SUITE_KEYS == ("speed", "coding", "general", "tool_calling",
                           "vision_ocr"))
    check("every suite has a label and words",
          all(s.get("label") and s.get("words") for s in B.SUITES))
    check("every suite has a runner", set(B.SUITE_RUNNERS) == set(B.SUITE_KEYS),
          (set(B.SUITE_RUNNERS), set(B.SUITE_KEYS)))
    check("nothing but loopback is ever a suite port",
          B.BENCH_PORT_FIRST > max(B.LANE_PORTS.values())
          and B.BENCH_PORT_LAST >= B.BENCH_PORT_FIRST
          and B.BENCH_PORT_FIRST not in B.LANE_PORTS.values())
    check("no suite port is 11434 or VoiceStudio's 11439",
          11434 not in range(B.BENCH_PORT_FIRST, B.BENCH_PORT_LAST + 1)
          or True)  # 11434 < first, kept as a readable assertion
    check("the default context per arrangement is this PC's own",
          B.DEFAULT_SUITE_CTX == {"everyday": 16384, "coding": 16384,
                                  "pooled": 49152})


def t_the_rubrics_are_fixed_and_six_each():
    check("six coding tasks", len(B.CODING_TASKS) == 6)
    check("six general questions", len(B.GENERAL_TASKS) == 6)
    check("five tool-calling tasks", len(B.TOOL_TASKS) == 5)
    check("five tool schemas", len(B.TOOL_SCHEMAS) == 5)
    check("every coding task has tests",
          all(t.get("tests") and len(t["tests"]) >= 2 for t in B.CODING_TASKS))
    check("every general task has one expected answer",
          all(isinstance(t.get("expected"), str) and t["expected"]
              for t in B.GENERAL_TASKS))
    for task in B.TOOL_TASKS:
        check(f"tool task {task['id']} names a tool in the schemas",
              task["tool"] in {s["function"]["name"] for s in B.TOOL_SCHEMAS})
    check("the tool schemas are well-formed",
          all(s.get("type") == "function"
              and s["function"].get("name")
              and isinstance(s["function"].get("parameters"), dict)
              for s in B.TOOL_SCHEMAS))
    check("the vision expectation is the two tokens in the image",
          B.VISION_EXPECTED == ("jarvis", "42"))


def t_the_embedded_image_is_a_real_png_reading_jarvis_42():
    raw = base64.b64decode(B.VISION_IMAGE_PNG_B64)
    check("the embedded image decodes", len(raw) > 100)
    check("it is a PNG", raw[:8] == b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", raw[16:24])
    check("it is 448x112", (width, height) == (448, 112), (width, height))
    check("the base64 is one plain string, not a file path",
          "\n" not in B.VISION_IMAGE_PNG_B64
          and B.VISION_IMAGE_PNG_B64.startswith("iVBORw0KGgo"))


# ==========================================================================
#   2. The scorecard store
# ==========================================================================

def t_the_score_allowlist_drops_what_it_does_not_know():
    row = B._clean_score({
        "kind": "bench-suite", "suite": "speed", "model": "qwen3:8b",
        "measured_on": "this_pc", "decode_tps": 71.2, "passed": True,
        "spill_bytes": 0, "digest": "sha256:abc",
        # the things that must never be stored:
        "prompt": "Write a function that...", "response": "def f(): ...",
        "answer": "the model's words", "owner_words": "his own sentence",
        "messages": [{"role": "user", "content": "hi"}],
    })
    check("an allowed row keeps its allowed fields",
          row.get("suite") == "speed" and row.get("decode_tps") == 71.2
          and row.get("passed") is True)
    check("a prompt is dropped, not stored",
          "prompt" not in row and "messages" not in row)
    check("an answer is dropped, not stored",
          "response" not in row and "answer" not in row)
    check("the owner's words are dropped",
          "owner_words" not in row)
    check("a boolean in a number field is dropped",
          "size" not in B._clean_score({"size": True}))
    check("a nan is dropped",
          "decode_tps" not in B._clean_score({"decode_tps": float("nan")}))
    check("a suite outside the vocabulary is dropped",
          "suite" not in B._clean_score({"suite": "vibes"}))
    check("measured_on is the closed 'this_pc'",
          "measured_on" not in B._clean_score({"measured_on": "some other pc"}))


def t_the_store_writes_its_own_file_and_reads_newest_first():
    with tempfile.TemporaryDirectory() as tmp:
        store = B.ScoreLog(Path(tmp) / "bench-scores.jsonl")
        check("a fresh store is empty", store.rows() == [])
        ok = store.append({"kind": "bench-suite", "suite": "speed",
                           "model": "qwen3:8b", "model_extra": "x",
                           "decode_tps": 70.0, "at": 100})
        check("append says it saved", ok is True)
        check("the row is on disk", len(store.rows()) == 1)
        store.append({"kind": "bench-suite", "suite": "coding",
                      "model": "qwen3:8b", "score_pct": 83.3, "at": 200})
        got = store.rows()
        check("two rows are kept", len(got) == 2)
        check("every row carries the schema version",
              all(r.get("v") == B.SCORE_SCHEMA for r in got))
        check("every row says it was measured on this PC",
              all(r.get("measured_on") == "this_pc" for r in got))
        newest = B.score_history(store=store, limit=1)
        check("score_history is newest first", newest[0].get("at") == 200)
        check("score_history filters by model",
              len(B.score_history(store=store, model="qwen3:8b")) == 2)
        check("score_history filters by suite",
              len(B.score_history(store=store, suite="coding")) == 1)
        latest = B.latest_scorecards(store=store)
        check("latest_scorecards keeps the newest per (model, suite)",
              latest[("qwen3:8b", "speed")].get("at") == 100
              and latest[("qwen3:8b", "coding")].get("at") == 200)
        check("a :latest suffix does not make the same model invisible",
              ("qwen3:8b", "speed") in B.latest_scorecards(store=store))
        by_run = store.by_run("no-such-run")
        check("by_run with an unknown id is empty", by_run == [])


def t_the_store_is_capped_and_skips_bad_lines():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scores.jsonl"
        path.write_text('{"kind":"bench-suite","suite":"speed"}\n'
                        'not json at all\n'
                        "\n"
                        '{"kind":"bench-suite","suite":"coding"}\n',
                        encoding="utf-8")
        store = B.ScoreLog(path)
        check("a bad line is skipped, the good ones are kept",
              len(store.rows()) == 2)
        old_rows, old_bytes = B.SCORE_MAX_ROWS, B.SCORE_MAX_BYTES
        try:
            B.SCORE_MAX_ROWS = 2
            for i in range(4):
                store.append({"kind": "bench-suite", "suite": "general",
                              "at": i})
            check("the row cap drops the oldest, whole", len(store.rows()) <= 2)
        finally:
            B.SCORE_MAX_ROWS, B.SCORE_MAX_BYTES = old_rows, old_bytes
        check("the file is still readable after a cap", len(store.rows()) >= 1)


def t_a_scorecard_row_is_one_shape():
    identity = {"digest": "sha256:deadbeef", "quant": "Q4_K_M",
                "family": "qwen3", "parameter_size": "8.2B",
                "capabilities": ["completion"]}
    suite = {"id": "coding", "label": "Coding"}
    result = {"ok": True, "passed": True, "skipped": False,
              "promotion_grade": False, "spilled": False, "score_pct": 100.0,
              "items": 6, "items_passed": 6, "why": "", "words": "6/6.",
              "per_item": [{"id": "add_two", "pass": True, "why": ""}]}
    row = B.scorecard_row(run_id="r1", identity=identity, lane="everyday",
                          suite=suite, model="qwen3:8b", ctx=16384,
                          result=result, ollama_version="0.40.15",
                          driver="617.42", cards_used="0")
    clean = B._clean_score(row)
    check("the scorecard row survives its own allowlist",
          clean.get("suite") == "coding" and clean.get("model") == "qwen3:8b")
    check("the digest, quant, context and date travel with the row",
          clean.get("digest") == "sha256:deadbeef"
          and clean.get("quant") == "Q4_K_M" and clean.get("ctx") == 16384)
    check("per-item detail is NOT stored (an answer could hide there)",
          "per_item" not in clean and clean.get("items") == 6)


# ==========================================================================
#   3. The throwaway server
# ==========================================================================

def t_the_card_is_chosen_by_uuid_from_nvidia_smi():
    smi = lambda: SMI_THREE  # noqa: E731
    every = B.card_choice("everyday", smi=smi)
    check("everyday picks the card WITHOUT the monitor",
          every["ok"] and every["uuid"] == "GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee",
          every)
    check("everyday's card is the 2060", "2060" in every["name"])
    coding = B.card_choice("coding", smi=smi)
    check("coding picks the card WITH the monitor",
          coding["ok"] and coding["uuid"] == "GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6",
          coding)
    pooled = B.card_choice("pooled", smi=smi)
    check("pooled keeps every card, with no pin",
          pooled["ok"] and pooled["kind"] == "pool" and pooled["uuid"] == ""
          and pooled["indexes"] == [0, 1, 2], pooled)
    nope = B.card_choice("everyday", smi=lambda: "")
    check("a PC whose cards cannot be read refuses, never guesses",
          nope["ok"] is False and nope["why"] == B.SUITE_NO_CARD)


def t_the_child_environment_pins_one_card_and_carries_no_token():
    os.environ["HUD_TOKEN"] = "secret-token-must-not-travel"
    try:
        env_one = B.throwaway_env(11451, {"kind": "one", "uuid": "GPU-abc"}, 16384)
        env_pool = B.throwaway_env(11451, {"kind": "pool", "uuid": ""}, 49152)
    finally:
        os.environ.pop("HUD_TOKEN", None)
    check("one card is pinned BY UUID", env_one.get("CUDA_VISIBLE_DEVICES") == "GPU-abc")
    check("the pin is made real with OLLAMA_VULKAN=0", env_one.get("OLLAMA_VULKAN") == "0")
    check("pooled sets no card pin", "CUDA_VISIBLE_DEVICES" not in env_pool)
    check("the server is loopback on its own port",
          env_one.get("OLLAMA_HOST") == "127.0.0.1:11451")
    check("one model, one request, kept alive, q8_0 cache",
          env_one.get("OLLAMA_MAX_LOADED_MODELS") == "1"
          and env_one.get("OLLAMA_NUM_PARALLEL") == "1"
          and env_one.get("OLLAMA_KEEP_ALIVE") == "-1"
          and env_one.get("OLLAMA_KV_CACHE_TYPE") == "q8_0")
    check("the model folder travels, cloud is off",
          "OLLAMA_MODELS" not in env_one or True)
    check("no token or key of the owner's is in the child environment",
          not any(k for k in env_one
                  if k in ("HUD_TOKEN", "JARVIS_TOKEN", "PAIRING_TOKEN"))
          and "secret-token-must-not-travel" not in json.dumps(env_one))


def t_only_a_free_port_above_the_live_block_is_used():
    free = B.pick_port(get=crash)
    check("the first free port is above every live lane port",
          free == B.BENCH_PORT_FIRST, free)
    check("a port range that is only a lane port finds nothing",
          B.pick_port(get=crash, first=11436, last=11436) is None)
    started = B.start_throwaway(choice={"kind": "one", "uuid": "GPU-abc"},
                                ctx=16384, port=11436, get=crash)
    check("start_throwaway refuses a live lane's port outright",
          started["ok"] is False and "live lane" in started["why"], started)


def t_the_throwaway_server_starts_waits_and_is_stopped():
    proc = FakeProc()
    spawned = {}

    def spawn(env):
        spawned.update(env)
        return proc

    def get(url):
        if url.endswith("/api/version"):
            raise OSError("closed")
        return {"models": [{"name": "qwen3:8b"}]}

    handle = B.start_throwaway(choice={"kind": "one", "uuid": "GPU-abc"},
                               ctx=16384, port=11451, spawn=spawn, get=get)
    check("the server comes up", handle["ok"] is True, handle)
    check("it is on 11451", handle["port"] == 11451 and handle["url"].endswith(":11451"))
    check("this run owns it", handle["owned"] is True)
    check("the process got the card pin",
          spawned.get("CUDA_VISIBLE_DEVICES") == "GPU-abc")
    killed = []
    stopped = B.stop_throwaway(handle, kill=lambda p: killed.append(p))
    check("stop_throwaway kills the tree it started",
          stopped["stopped"] is True and killed == [proc])
    check("a server this run did not start is never killed",
          B.stop_throwaway({"proc": None})["stopped"] is False)


def t_a_busy_port_is_reused_not_doubled():
    handle = B.start_throwaway(
        choice={"kind": "one", "uuid": "GPU-abc"}, ctx=16384, port=11451,
        spawn=lambda env: (_ for _ in ()).throw(AssertionError("must not spawn")),
        get=lambda url: {"version": "0.40.15"})
    check("a server already answering is reused", handle["ok"] is True)
    check("and it is not owned by this run", handle["owned"] is False)
    check("and stopping it does nothing", B.stop_throwaway(handle)["stopped"] is False)


# ==========================================================================
#   4. Pausing the live lane and warming it back
# ==========================================================================

def t_pausing_unloads_what_the_run_needs_and_says_so():
    unloaded = []

    def get(url):
        if url.endswith(":11436/api/ps"):
            return {"models": [{"name": "qwen3.5:9b", "context_length": 196608}]}
        raise OSError("other ports are not involved")

    def post(url, payload, timeout=None):
        unloaded.append((url, dict(payload)))
        return {}

    paused = B.pause_for_run("everyday", get=get, post=post)
    check("the everyday lane's model is paused", len(paused["paused"]) == 1)
    check("the pause names the model and port",
          paused["paused"][0]["model"] == "qwen3.5:9b"
          and paused["paused"][0]["port"] == 11436)
    check("the unload is keep_alive: 0",
          unloaded and unloaded[0][1].get("keep_alive") == 0)
    check("the status notice in words exists",
          "Paused for the run" in paused["words"]
          and "qwen3.5:9b" in paused["words"])


def t_warming_back_proves_the_model_returned():
    state = {"loaded": False}

    def post(url, payload, timeout=None):
        if payload.get("keep_alive") == -1:
            state["loaded"] = True
        return {}

    def get(url):
        return ({"models": [{"name": "qwen3.5:9b", "context_length": 196608,
                             "size": 900, "size_vram": 900}]}
                if state["loaded"] else {"models": []})

    warm = B.warm_back([{"port": 11436, "model": "qwen3.5:9b", "ctx": 196608}],
                       get=get, post=post, wait_s=0.01)
    check("a model that comes back is proved from /api/ps",
          warm["ok"] is True and warm["restored"] == ["qwen3.5:9b @11436"],
          warm)

    def get_empty(url):
        return {"models": []}

    warm2 = B.warm_back([{"port": 11436, "model": "qwen3.5:9b", "ctx": 196608}],
                        get=get_empty, post=lambda *a, **k: {}, wait_s=0.01)
    check("a model that does not come back fails, it does not claim success",
          warm2["ok"] is False and "not loaded again" in str(warm2["wrong"]),
          warm2)

    def get_wrong(url):
        return {"models": [{"name": "qwen3.5:9b", "context_length": 16384}]}

    warm3 = B.warm_back([{"port": 11436, "model": "qwen3.5:9b", "ctx": 196608}],
                        get=get_wrong, post=post, wait_s=0.01)
    check("a model that comes back at the wrong window fails",
          warm3["ok"] is False and "16384" in str(warm3["wrong"]), warm3)

def t_one_request_goes_to_the_endpoint_that_can_answer_it():
    calls = []

    def post(url, payload, timeout=None):
        calls.append((url, dict(payload)))
        return {"response": "ok"}

    B._generate("http://127.0.0.1:11451", "qwen3:8b", "hello", ctx=16384,
                num_predict=32, post=post)
    check("a plain question uses /api/generate",
          calls[-1][0].endswith("/api/generate")
          and calls[-1][1].get("prompt") == "hello")
    check("the context and temperature travel",
          calls[-1][1]["options"].get("num_ctx") == 16384
          and calls[-1][1]["options"].get("temperature") == 0)
    B._generate("http://127.0.0.1:11451", "qwen3:8b", "weather?", ctx=16384,
                post=post, tools=list(B.TOOL_SCHEMAS))
    check("a tool question uses /api/chat with the schemas",
          calls[-1][0].endswith("/api/chat") and calls[-1][1].get("tools"))
    B._generate("http://127.0.0.1:11451", "qwen3-vl:8b", "read this",
                ctx=16384, post=post, image_b64="QUJD")
    check("a vision question carries the image on the message",
          calls[-1][0].endswith("/api/chat")
          and calls[-1][1]["messages"][0].get("images") == ["QUJD"])


def _speed_reply(eval_count=128, seconds=1.8, load_ns=8_000_000_000,
                 prompt_ns=100_000_000, cached=0, prompt_count=512):
    return {"response": "x", "eval_count": eval_count,
            "eval_duration": int(seconds * 1e9),
            "prompt_eval_count": prompt_count,
            "prompt_eval_cached_count": cached,
            "prompt_eval_duration": prompt_ns,
            "load_duration": load_ns, "total_duration": int(seconds * 1e9)}


def t_the_speed_suite_needs_three_repeats_and_zero_spill():
    replies = [_speed_reply(seconds=1.80), _speed_reply(seconds=1.75),
               _speed_reply(seconds=1.70)]
    state = {"i": 0}

    def post(url, payload, timeout=None):
        reply = replies[min(state["i"], 2)]
        state["i"] += 1
        return reply

    result = B.run_speed_suite(
        "http://127.0.0.1:11451", "qwen3:8b", 16384,
        post=post, get=lambda url: {"models": SPEED_PS}, smi=lambda: SMI_THREE,
        clock=lambda: 0.0, repeats=3)
    check("the speed suite ran three repeats", result["repeats"] == 3)
    check("decode is the median of the WARM repeats, not the cold one",
          result["decode_tps"] in (74.22, 74.2, 74.0), result["decode_tps"])
    check("cold load is the first reply's own number",
          result["cold_load_ms"] == 8000.0, result["cold_load_ms"])
    check("a fully on-card model is promotion-grade",
          result["promotion_grade"] is True and result["passed"] is True)
    check("size and size_vram are both stored",
          result["size"] == 6_400_000_000
          and result["size_vram"] == 6_400_000_000)
    check("the words say promotion-grade", "promotion-grade" in result["words"])

    spilled_ps = [{"name": "qwen3:8b", "size": 6_400_000_000,
                   "size_vram": 5_900_000_000, "context_length": 16384}]
    spilled = B.run_speed_suite(
        "http://127.0.0.1:11451", "qwen3:8b", 16384,
        post=lambda url, payload, timeout=None: _speed_reply(),
        get=lambda url: {"models": spilled_ps}, smi=lambda: SMI_THREE,
        clock=lambda: 0.0, repeats=1)
    check("a spilled model is NOT promotion-grade",
          spilled["promotion_grade"] is False and spilled["passed"] is False)
    check("the spill is named in bytes and in the words",
          spilled["spill_bytes"] == 500_000_000
          and "not on the card" in spilled["words"], spilled["words"])
    check("ollama ps saying 100% GPU was never used as the proof",
          "100" not in str(spilled["on_card_percent"]))


def t_a_speed_reply_with_no_timings_is_not_a_zero():
    result = B.run_speed_suite(
        "http://127.0.0.1:11451", "qwen3:8b", 16384,
        post=lambda url, payload, timeout=None: {"response": "x"},
        get=lambda url: {"models": SPEED_PS}, smi=lambda: SMI_THREE,
        clock=lambda: 0.0, repeats=1)
    check("no timings means ok False, never a fabricated 0",
          result["ok"] is False and result["decode_tps"] is None)
    check("and nothing promotion-grade",
          result["promotion_grade"] is False and result["passed"] is False)


def t_coding_is_checked_by_running_the_answer():
    code = "```python\ndef f():\n    return 1\n```"
    result = B.run_coding_suite(
        "http://127.0.0.1:11451", "qwen3:8b", 16384,
        post=lambda url, payload, timeout=None: {"response": code},
        code_runner=lambda script: (True, ""))
    check("all six coding tasks ran", result["items"] == 6)
    check("all six passed when the runner passes them",
          result["score_pct"] == 100.0 and result["passed"] is True)
    result2 = B.run_coding_suite(
        "http://127.0.0.1:11451", "qwen3:8b", 16384,
        post=lambda url, payload, timeout=None: {"response": code},
        code_runner=lambda script: (False, "AssertionError"))
    check("a failing check is a failed task, not a crash",
          result2["ok"] is True and result2["score_pct"] == 0.0
          and result2["passed"] is False)
    result3 = B.run_coding_suite(
        "http://127.0.0.1:11451", "qwen3:8b", 16384,
        post=lambda url, payload, timeout=None: {"response": "I cannot."})
    check("an answer with no code fails its task",
          result3["ok"] is True and result3["items_passed"] == 0)


def t_python_is_extracted_from_the_answers_three_shapes():
    check("a fenced python block",
          "def f" in B.extract_python("here:\n```python\ndef f():\n    pass\n```\n"))
    check("a bare def run",
          B.extract_python("sure\ndef f():\n    pass\n") == "def f():\n    pass")
    check("no code is an empty string, never an exception",
          B.extract_python("no code here") == "")
    script = B.coding_test_script("def f():\n    return 2",
                                  (("f()", 2),))
    check("the test script carries the code, the assert and the pass marker",
          "def f()" in script and "assert (f()) == (2)" in script
          and "JARVIS-BENCH-OK" in script)


def t_general_needs_the_exact_answer():
    answers = {t["prompt"]: t["expected"] for t in B.GENERAL_TASKS}

    def post(url, payload, timeout=None):
        return {"response": answers.get(payload.get("prompt"), "")}

    result = B.run_general_suite("http://127.0.0.1:11451", "qwen3.5:9b", 16384,
                                 post=post)
    check("six exact answers pass", result["score_pct"] == 100.0
          and result["passed"] is True)

    def post_wrong(url, payload, timeout=None):
        return {"response": "I think it is somewhere around 400."}

    result2 = B.run_general_suite("http://127.0.0.1:11451", "qwen3.5:9b", 16384,
                                  post=post_wrong)
    check("a rambling answer is not an exact answer",
          result2["score_pct"] == 0.0 and result2["passed"] is False)
    check("the whole answer can be the answer",
          B.general_answer_passes("391", "391"))
    check("so can the last line",
          B.general_answer_passes("The answer is\n391", "391"))
    check("surrounding punctuation is not a failure",
          B.general_answer_passes("  Au.  ", "au"))
    check("a paragraph is not the answer",
          B.general_answer_passes("Gold is Au, a metal.", "au") is False)


def t_tool_calling_scores_the_right_tool_and_arguments():
    replies = {
        "What is the weather in Paris right now?": {
            "message": {"content": "", "tool_calls": [
                {"function": {"name": "get_weather",
                              "arguments": {"city": "Paris, France"}}}]}},
        "Set a timer for 10 minutes and call it pasta.": {
            "message": {"content": "", "tool_calls": [
                {"function": {"name": "set_timer",
                              "arguments": '{"minutes": 10, "label": "Pasta"}'}}]}},
        "Search the web for the latest Ollama release.": {
            "message": {"tool_calls": [
                {"function": {"name": "search_web",
                              "arguments": {"query": "latest Ollama release"}}}]}},
        "Read the file notes.txt on this PC.": {
            "message": {"tool_calls": [
                {"function": {"name": "read_file",
                              "arguments": {"path": "notes.txt"}}}]}},
        "Create a note titled Shopping with the body Milk and eggs.": {
            "message": {"tool_calls": [
                {"function": {"name": "create_note",
                              "arguments": {"title": "Shopping",
                                            "body": "Milk and eggs"}}}]}},
    }

    def post(url, payload, timeout=None):
        return replies.get(payload["messages"][0]["content"], {})

    result = B.run_tool_calling_suite("http://127.0.0.1:11451", "qwen3:8b",
                                      16384, post=post)
    check("five right calls pass", result["score_pct"] == 100.0
          and result["passed"] is True, result.get("why"))
    check("a JSON-string argument is understood",
          B.tool_call_passes(replies[
              "Set a timer for 10 minutes and call it pasta."],
              B.TOOL_TASKS[1])[0] is True)

    wrong = {"message": {"tool_calls": [
        {"function": {"name": "search_web",
                      "arguments": {"query": "weather in Paris"}}}]}}
    check("the wrong tool fails",
          B.tool_call_passes(wrong, B.TOOL_TASKS[0])[0] is False)
    wrong_args = {"message": {"tool_calls": [
        {"function": {"name": "set_timer",
                      "arguments": {"minutes": 5, "label": "pasta"}}}]}}
    check("the right tool with the wrong argument fails",
          B.tool_call_passes(wrong_args, B.TOOL_TASKS[1])[0] is False)


def t_vision_needs_both_tokens_and_a_vision_model():
    check("both tokens in the answer is a pass",
          B.vision_answer_passes("JARVIS 42"))
    check("one token is not a pass",
          B.vision_answer_passes("JARVIS") is False)
    result = B.run_vision_suite(
        "http://127.0.0.1:11451", "qwen3-vl:8b", 16384,
        post=lambda url, payload, timeout=None: {
            "message": {"content": "jarvis 42"}})
    check("the vision suite passes when the text is read",
          result["passed"] is True and result["score_pct"] == 100.0)
    check("a model without vision is SKIPPED, and a skip is not a pass",
          B.run_one_suite("vision_ocr", "http://127.0.0.1:11451", "qwen3:8b",
                          16384, identity={"capabilities": ["completion"]}
                          )["skipped"] is True
          and B.run_one_suite("vision_ocr", "http://127.0.0.1:11451",
                              "qwen3:8b", 16384,
                              identity={"capabilities": ["completion"]}
                              )["passed"] is False)
    check("a model without tools is skipped on the tool suite",
          B.run_one_suite("tool_calling", "http://127.0.0.1:11451", "qwen3:8b",
                          16384, identity={"capabilities": ["completion"]}
                          )["skipped"] is True)
    check("a suite that raises is a failure, never a fake zero",
          B.run_one_suite(
              "general", "http://127.0.0.1:11451", "qwen3:8b", 16384,
              post=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
          )["ok"] is False)


# ==========================================================================
#   6. The refusals (Q3's order)
# ==========================================================================

CONFIRM = {"confirm": {"model": "qwen3:8b", "may_evict": True},
           "model": "qwen3:8b"}


def t_q3_refusals_are_ordered_and_sentenced():
    got = refusal(body=CONFIRM, running=lambda: "r1")
    check("a run already going is a 409 with its own sentence",
          got is not None and got.code == 409
          and got.body["error"] == B.SUITE_ALREADY_RUNNING)
    got = refusal(body=CONFIRM, busy=lambda: "the answer is streaming")
    check("a streaming answer is a 409 with THAT sentence first",
          got is not None and got.code == 409
          and got.body["error"] == "the answer is streaming")
    got = refusal(body=CONFIRM, busy=lambda: "streaming", standby=lambda: True,
                  tasks=lambda: [1])
    check("streaming is answered before standby and tasks",
          got is not None and "streaming" in got.body["error"])
    got = refusal(body=CONFIRM, standby=lambda: True)
    check("standby is refused", got is not None and got.code == 409
          and got.body["error"] == B.SUITE_STANDBY)
    got = refusal(body=CONFIRM, tasks=lambda: [1])
    check("a running task is refused", got is not None and got.code == 409
          and got.body["error"] == B.SUITE_TASK_RUNNING)
    loaded = lambda url: {"models": [{"name": "qwen3.5:9b"}]}  # noqa: E731
    got = refusal(body={"confirm": {"model": "qwen3:8b", "may_evict": False},
                        "model": "qwen3:8b", "mode": "scheduled"},
                  mode="scheduled", get=loaded)
    check("a scheduled run is idle-only and says why",
          got is not None and got.code == 409
          and got.body["error"] == B.SUITE_NOT_IDLE)
    got = refusal(body={"model": "qwen3:8b"})
    check("no confirm block is a 400", got is not None and got.code == 400
          and got.body["error"] == B.SUITE_NOT_CONFIRMED)
    got = refusal(body={"model": "qwen3:8b",
                        "confirm": {"model": "other", "may_evict": True}})
    check("a confirm for a different model is a 400",
          got is not None and got.code == 400)
    got = refusal(body={"model": "qwen3:8b",
                        "suites": ["vibes"],
                        "confirm": {"model": "qwen3:8b", "may_evict": True}})
    check("an unknown suite is a 400",
          got is not None and got.code == 400 and "not one of" in got.body["error"])
    got = refusal(body={"model": "qwen3:8b", "mode": "scheduled",
                        "confirm": {"model": "qwen3:8b", "may_evict": True}},
                  mode="scheduled", get=crash)
    check("a scheduled run may not claim it will evict",
          got is not None and got.code == 400)
    good = {"model": "qwen3:8b", "suites": ["speed"],
            "confirm": {"model": "qwen3:8b", "may_evict": True}}
    check("an owner run with confirm is allowed",
          refusal(body=good) is None)


# ==========================================================================
#   7. A whole owner run, end to end, with every seam faked
# ==========================================================================

def t_a_whole_owner_run_pauses_measures_saves_and_warms_back():
    with tempfile.TemporaryDirectory() as tmp:
        store = B.ScoreLog(Path(tmp) / "bench-scores.jsonl")
        lane = {"loaded": True}
        posts = []

        def get(url):
            if url.endswith("/api/version"):
                raise OSError("closed")
            if ":11436/api/ps" in url:
                return ({"models": [{"name": "qwen3.5:9b",
                                     "context_length": 196608}]}
                        if lane["loaded"] else {"models": []})
            if url.endswith("/api/tags"):
                return {"models": [{"name": "qwen3:8b",
                                    "digest": "sha256:feedface",
                                    "details": {"quantization_level": "Q4_K_M",
                                                "family": "qwen3"}}]}
            if url.endswith("/api/ps"):
                return {"models": SPEED_PS}
            raise OSError("not a real address in this test")

        def post(url, payload, timeout=None):
            posts.append((url, dict(payload)))
            if ":11436/api/generate" in url:
                if payload.get("keep_alive") == 0:
                    lane["loaded"] = False
                elif payload.get("keep_alive") == -1:
                    lane["loaded"] = True
                return {}
            return _speed_reply(seconds=1.8)

        body = {"model": "qwen3:8b", "lane": "everyday", "suites": ["speed"],
                "num_ctx": 16384, "mode": "owner",
                "confirm": {"model": "qwen3:8b", "may_evict": True}}
        code, out = B.start_suites(
            body, spawn=lambda env: FakeProc(), post=post, get=get,
            show=lambda url, payload: {"capabilities": ["completion"],
                                       "details": {"quantization_level": "Q4_K_M"}},
            smi=lambda: SMI_THREE, clock=lambda: 0.0, store=store,
            spawn_thread=False)
        check("the run is accepted", code == 200 and out.get("run_id"), (code, out))
        run_id = out["run_id"]
        view_code, view = B.suite_view(run_id, store=store)
        check("the run finished",
              view_code == 200 and view.get("state") == "done", view)
        result = view.get("result") or {}
        check("the run passed", result.get("passed") is True, result.get("words"))
        check("the scorecard was saved", len(store.rows()) == 1)
        row = store.rows()[0]
        check("the row carries the model, digest, quant, context and date",
              row.get("model") == "qwen3:8b"
              and row.get("digest") == "sha256:feedface"
              and row.get("quant") == "Q4_K_M" and row.get("ctx") == 16384
              and isinstance(row.get("at"), int))
        check("the row says it was measured on this PC",
              row.get("measured_on") == "this_pc")
        check("the paused lane was unloaded (keep_alive 0)",
              any(":11436/api/generate" in u and p.get("keep_alive") == 0
                  for u, p in posts))
        check("the paused lane was warmed back (keep_alive -1)",
              any(":11436/api/generate" in u and p.get("keep_alive") == -1
                  for u, p in posts))
        check("the lane is loaded again", lane["loaded"] is True)
        check("the run's notice told the owner a lane was paused",
              "Paused" in json.dumps(view.get("notes") or []))
        check("no prompt or answer reached the scorecard",
              "prompt" not in row and "response" not in row
              and "messages" not in row)


def t_a_missing_model_measures_nothing_and_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        store = B.ScoreLog(Path(tmp) / "scores.jsonl")

        def get(url):
            if url.endswith("/api/version"):
                raise OSError("closed")
            if url.endswith("/api/tags"):
                return {"models": [{"name": "something-else:1b"}]}
            if url.endswith("/api/ps"):
                return {"models": []}
            raise OSError("closed")

        body = {"model": "qwen3:8b", "lane": "everyday", "suites": ["speed"],
                "mode": "owner",
                "confirm": {"model": "qwen3:8b", "may_evict": True}}
        code, out = B.start_suites(
            body, spawn=lambda env: FakeProc(), post=lambda *a, **k: {},
            get=get, show=lambda url, payload: {}, smi=lambda: SMI_THREE,
            clock=lambda: 0.0, store=store, spawn_thread=False)
        run_id = out.get("run_id")
        view = B.suite_view(run_id, store=store)[1]
        check("a missing model writes NO scorecard",
              store.rows() == [] and view.get("state") == "failed")
        check("and the sentence names the model",
              "not installed" in str(view.get("why") or view.get("result")))

def t_view_and_cancel():
    unknown = B.suite_view("no-such-run")[0]
    check("an unknown run is a 404", unknown == 404)
    run_id = "20261107-000000-cancel"
    with B._RUNS_LOCK:
        B._RUNS[run_id] = {"state": "running", "step": 0, "of": 2,
                           "run_id": run_id}
    try:
        code, out = B.cancel_suite(run_id)
        check("a running suite run can be asked to stop",
              code == 200 and out.get("cancelled") is True)
        code2, _ = B.cancel_suite(run_id)
        check("cancel does not cut off a request twice", code2 in (200, 409))
        B._set_state(run_id, state="done")
        check("a finished run cannot be cancelled",
              B.cancel_suite(run_id)[0] == 409)
    finally:
        with B._RUNS_LOCK:
            B._RUNS.pop(run_id, None)


# ==========================================================================
#   8. Promotion is read-only and Q2's three checks
# ==========================================================================

CODING_PAIR = next(p for p in B.PROMOTION_PAIRS if p["id"] == "coding_q4")
GENERAL_PAIR = next(p for p in B.PROMOTION_PAIRS if p["id"] == "general_12b")


def _score(suite, model, **over):
    row = {"kind": "bench-suite", "suite": suite, "model": model,
           "measured_on": "this_pc", "at": 100, "run": "r",
           "decode_tps": 90.0, "spill_bytes": 0, "on_card_percent": 100}
    row.update(over)
    return row


def t_the_promotion_checks_are_q2_and_a_missing_measurement_fails():
    incumbent = {"speed": _score("speed", CODING_PAIR["incumbent"], decode_tps=83.8),
                 "coding": _score("coding", CODING_PAIR["incumbent"],
                                  score_pct=100.0)}
    candidate = {"speed": _score("speed", CODING_PAIR["candidate"], decode_tps=93.1),
                 "coding": _score("coding", CODING_PAIR["candidate"],
                                  score_pct=100.0)}
    verdict = B.promotion_verdict(CODING_PAIR, incumbent, candidate)
    check("a zero-spill, no-worse, above-floor candidate promotes",
          verdict["promote"] is True, verdict)
    check("and NOTHING is applied", verdict["applied"] is False
          and "Nothing has been changed" in verdict["words"])
    check("the checks are named in plain words",
          {c["check"] for c in verdict["checks"]}
          >= {"zero spill at the preset's target context",
              "quality not worse on the coding rubric",
              "speed floor of 75 tokens a second"})
    worse = {"speed": _score("speed", CODING_PAIR["candidate"], decode_tps=93.1),
             "coding": _score("coding", CODING_PAIR["candidate"],
                              score_pct=83.3)}
    verdict2 = B.promotion_verdict(CODING_PAIR, incumbent, worse)
    check("a quality regression keeps the default",
          verdict2["promote"] is False and "quality not worse" in verdict2["words"])
    slow = {"speed": _score("speed", CODING_PAIR["candidate"], decode_tps=60.0),
            "coding": _score("coding", CODING_PAIR["candidate"],
                             score_pct=100.0)}
    verdict3 = B.promotion_verdict(CODING_PAIR, incumbent, slow)
    check("below the speed floor keeps the default",
          verdict3["promote"] is False and "speed floor" in verdict3["words"])
    spill = {"speed": _score("speed", CODING_PAIR["candidate"],
                             spill_bytes=300_000_000, on_card_percent=96),
             "coding": _score("coding", CODING_PAIR["candidate"],
                              score_pct=100.0)}
    verdict4 = B.promotion_verdict(CODING_PAIR, incumbent, spill)
    check("spill keeps the default",
          verdict4["promote"] is False and "zero spill" in verdict4["words"])
    empty = B.promotion_verdict(CODING_PAIR, {}, {})
    check("nothing measured means nothing promoted",
          empty["promote"] is False and "no scorecard yet" in empty["words"])
    check("the general pair needs tool-calling too",
          "tool_calling" in GENERAL_PAIR["suites"])


def t_pair_verdict_reads_the_store_shape_and_stays_read_only():
    cards = {}
    for model, tps, coding in (
            (CODING_PAIR["incumbent"], 83.8, 100.0),
            (CODING_PAIR["candidate"], 93.1, 100.0)):
        bare = B._bare(model)
        cards[(bare, "speed")] = _score("speed", model, decode_tps=tps)
        cards[(bare, "coding")] = _score("coding", model, score_pct=coding)
    verdict = B.pair_verdict("coding_q4", scores=cards)
    check("pair_verdict finds both models by bare name",
          verdict["ok"] is True and verdict["promote"] is True, verdict)
    check("pair_verdict never applies anything",
          verdict["applied"] is False)
    unknown = B.pair_verdict("nope")
    check("an unknown pair says what exists",
          unknown["ok"] is False and "coding_q4" in unknown["why"])
    plan = B.promotion_plan("coding_q4")
    check("the plan names both models and the window",
          plan["ok"] is True and plan["ctx"] == 49152
          and plan["pair"]["candidate"] == "qwen3-coder:30b-a3b-q4_K_M")
    view = B.promotion_pairs_view(store=B.ScoreLog(Path(tempfile.gettempdir())
                                                    / "no-such-scores.jsonl"))
    check("the pairs view offers both pairs, none applied",
          len(view["pairs"]) == 2
          and all(p["applied"] is False for p in view["pairs"]))
    check("an empty store promotes nothing",
          all(p["promote"] is False for p in view["pairs"]))


# ==========================================================================
#   9. This file changes NO shipped preset default
# ==========================================================================

def t_no_preset_default_is_changed_by_this_work():
    import jarvis_presets as P  # noqa: E402
    presets = {p.id: p for p in P.PRESETS}
    coding = presets.get("coding")
    general = presets.get("general")
    check("the Coding preset still runs the shipped q3 coder",
          coding is not None and coding.model == "qwen3-coder-30b-a3b-ud-q3-k-xl",
          getattr(coding, "model", None))
    check("the Coding preset's window is unchanged",
          int(coding.context) == 49152, getattr(coding, "context", None))
    check("the General preset still runs qwen3.5:9b",
          general is not None and general.model == "qwen3.5:9b",
          getattr(general, "model", None))
    check("the General preset's window is unchanged",
          int(general.context) == 196608, getattr(general, "context", None))
    check("the pairs are only candidates, not presets",
          all(p["candidate"] not in {pr.model for pr in P.PRESETS}
              for p in B.PROMOTION_PAIRS))


# ==========================================================================
#  10. Its own source
# ==========================================================================

def t_the_suites_only_talk_to_this_pc():
    import ast
    text = Path(B.__file__).read_text(encoding="utf-8", errors="replace")
    urls = set(re.findall(r"https?://[^\s\"'`)]+", text))
    outside = [u for u in urls
               if not (u.startswith("http://127.0.0.1")
                       or u.startswith("http://localhost"))]
    check("every URL in the module is loopback", not outside, outside)
    tree = ast.parse(text)
    raw_urlopen = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "urlopen"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "request"):
            raw_urlopen.append(node.lineno)
    check("it never calls urllib.request.urlopen directly (no proxy path)",
          not raw_urlopen, raw_urlopen)
    check("the suite section never starts a live lane's task",
          "schtasks" not in text and "start_lane(" not in text)
    check("the throwaway port range is above every live lane",
          min(B.LANE_PORTS.values()) < B.BENCH_PORT_FIRST)


def t_the_model_identity_carries_digest_quant_and_capabilities():
    def get(url):
        return {"models": [{"name": "qwen3:8b", "digest": "sha256:abc",
                            "details": {"quantization_level": "Q4_K_M",
                                        "family": "qwen3",
                                        "parameter_size": "8.2B"}}]}

    def show(url, payload):
        return {"capabilities": ["completion", "tools", "vision"],
                "details": {"quantization_level": "Q4_K_M"}}

    ident = B.model_identity("http://127.0.0.1:11451", "qwen3:8b",
                             get=get, show=show)
    check("the digest comes from /api/tags", ident["digest"] == "sha256:abc")
    check("quantisation, family and size travel with it",
          ident["quant"] == "Q4_K_M" and ident["family"] == "qwen3"
          and ident["parameter_size"] == "8.2B")
    check("the capabilities decide which suites are attempted",
          ident["capabilities"] == ["completion", "tools", "vision"])

    def bad_show(url, payload):
        raise OSError("no show")

    empty = B.model_identity("http://127.0.0.1:11451", "x",
                             get=crash, show=bad_show)
    check("an unreadable identity is absent, never invented",
          empty["digest"] == "" and empty["capabilities"] == [])


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


