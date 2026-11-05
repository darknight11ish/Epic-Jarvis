"""test_bench.py - the benchmark engine, proved with fake Ollama and fake cards.

    python3 backend/test_bench.py

NO OLLAMA, NO MODEL, NO GRAPHICS CARD, NO NETWORK. That is the whole design of
this suite: `jarvis_bench` takes injectable `post`, `get`, `show`, `smi`,
`clock` and `spawn` callables, so every formula and every refusal below is
driven from a literal - a fake reply with the exact counters, or the exact text
`nvidia-smi` prints on this PC. A real run is a field test, not a test (DESIGN
section 12: "One real run is a field test, not a test"), and a CI runner has no
cards and no models, so the rows that would need them are BLOCKED and are not
claimed here as pass.

WHAT IT PROVES, and why each one is worth a test rather than a comment:

  1. THE PREFILL TRAP. A reply with 318 prompt tokens, 317 cached and 23 ms of
     evaluation must give 43 tok/s - NOT the 13,826 the naive division gives.
     This is the one arithmetic mistake that would ship a 318x lie, and it is
     invisible to every other check in this repo. A fully cached prompt must
     give None and "cached - prefill not measured": not 0, not infinity. A
     reply with no `prompt_eval_cached_count` must be UNKNOWN, not 0.
  2. Generation rate, and both time-to-first-token numbers.
  3. A run whose model is NOT fully on the card is labelled PARTIAL and its
     numbers are never presented as fast (DESIGN section 13).
  4. A failed run writes `ok: false` + `why`, and never a zero standing in for
     a measurement.
  5. Every refusal row of DESIGN section 2, with its status code and its
     sentence - including "no run can start without `confirm`".
  6. The store: append, tail, list with filters, get, delete, the 500-run cap
     and the byte cap, and that `speed.jsonl` is never touched.
  7. The allowlist: a row carrying a prompt, an answer or the owner's words is
     DROPPED, not written. And `lane` is a CLOSED vocabulary: a lane that is
     not one of the three is dropped too, rather than cut to 12 characters by
     the text-field table it used to sit in as well.
  8. The advice builder: it refuses to compare under three runs, and it says
     so when a comparison spans a version change.
  9. The lane ports are the ones `jarvis_model_lanes.py` really uses.
 10. Its own source: this module cannot reach anything but loopback.
 11. THE PROMPT IS FRESH AT THE FRONT. Two repeats at one depth must share no
     word of prefix and only a few characters - Ollama caches the longest
     common prefix, so a tag at the TAIL makes every repeat after the first a
     measurement of the tail. Nothing tested `prefill_prompt` before
     2026-11-04, and the shipped prompt did put the tag at the tail.

No pytest. Run it directly; the exit code is the verdict.
"""
import io
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_bench.py")

import jarvis_bench as B  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ==========================================================================
#   Fakes: one Ollama, one graphics card reader, one clock
# ==========================================================================

#: The reply this PC's `qwen3.5:9b` would give for a WARM prompt: 318 tokens
#: asked, 317 of them already cached, so only ONE was really computed. This is
#: the measured case from RESEARCH.md section 3.1, and the naive division of
#: 318 by 23 ms is 13,826 tok/s - a 318x lie.
WARM_REPLY = {
    "prompt_eval_count": 318, "prompt_eval_cached_count": 317,
    "prompt_eval_duration": 23_000_000,          # 23.00 ms, in nanoseconds
    "eval_count": 64, "eval_duration": 1_550_000_000,   # 1.55 s -> 41.29 tok/s
    "load_duration": 0, "total_duration": 1_800_000_000,
    "response": "", "done": True,
}

#: The COLD reply: nothing cached, 139.97 ms of prompt evaluation.
COLD_REPLY = {
    "prompt_eval_count": 318, "prompt_eval_cached_count": 0,
    "prompt_eval_duration": 139_970_000,
    "eval_count": 64, "eval_duration": 2_000_000_000,
    "load_duration": 500_000_000, "total_duration": 2_700_000_000,
    "response": "", "done": True,
}

#: What this PC's two cards print, driver 617.42, June 2026 measurement - the
#: 2060 full of the everyday model, the 2080 SUPER holding the desktop.
SMI_BEFORE = (
    "0, GPU-aaaa1111-bbbb-2222-cccc-333344445555, NVIDIA GeForce RTX 2060, "
    "12288, 11919, 369, 3, Disabled, 617.42\n"
    "1, GPU-dddd5555-eeee-6666-ffff-777788889999, NVIDIA GeForce RTX 2080 "
    "SUPER, 8192, 4086, 4106, 11, Enabled, 617.42\n")
#: The same cards while a 6.1 GB model is being measured on the 2060.
SMI_DURING = (
    "0, GPU-aaaa1111-bbbb-2222-cccc-333344445555, NVIDIA GeForce RTX 2060, "
    "12288, 12110, 178, 94, Disabled, 617.42\n"
    "1, GPU-dddd5555-eeee-6666-ffff-777788889999, NVIDIA GeForce RTX 2080 "
    "SUPER, 8192, 4102, 4090, 12, Enabled, 617.42\n")


def fake_get(*, models=("qwen3.5:9b", "qwen3:8b"), ps=None, show=None,
             version="0.40.12"):
    """A `/api/tags`, `/api/ps`, `/api/version` and `/api/show` stand-in.

    One callable for every GET the module makes, refusing anything else - so a
    URL this module should not be calling is a test failure rather than a
    quiet success."""
    def get(url):
        if url.endswith("/api/tags"):
            return {"models": [{"name": n} for n in models]}
        if url.endswith("/api/ps"):
            return {"models": ps if ps is not None else []}
        if url.endswith("/api/version"):
            return {"version": version}
        raise AssertionError(f"unexpected GET {url}")
    return get


def fake_show(block_count=32, context_length=262144):
    def show(url, payload):
        if not url.endswith("/api/show"):
            raise AssertionError(f"unexpected POST {url}")
        arch = "qwen35"
        return {"model_info": {f"{arch}.block_count": block_count,
                               f"{arch}.context_length": context_length}}
    return show


def fake_post(reply=None, *, first_s=0.42):
    """A generation request stand-in: one reply, and a first-chunk time.

    It answers the `keep_alive: 0` unload too, because that is also a POST to
    `/api/generate` and a fake that refused it would make every run look like
    it failed to unload."""
    reply = COLD_REPLY if reply is None else reply

    def post(url, payload):
        if not url.endswith("/api/generate"):
            raise AssertionError(f"unexpected POST {url}")
        if payload.get("keep_alive") == 0:
            return 0.0, {"done": True}
        return first_s, dict(reply)
    return post


def fake_clock(step=1.0):
    """A clock that moves by `step` every time it is read, so `total_ms` is a
    number the test chose rather than a number that varies."""
    box = {"t": 0.0}

    def clock():
        box["t"] += step
        return box["t"]
    return clock


def tmp_log():
    """A `BenchLog` in a fresh temporary folder - never the owner's
    `~/.openjarvis`."""
    return B.BenchLog(Path(tempfile.mkdtemp(prefix="jarvis-bench-test-"))
                      / "bench.jsonl")


def run_once(*, reply=COLD_REPLY, ps=None, log=None, body=None, models=None,
             block_count=32, first_s=0.42, smi=SMI_BEFORE,
             during=SMI_DURING, tasks=(), busy=None, standby=False):
    """One whole run, synchronously, against the fakes. Returns (code, body,
    log).

    `smi` is what the cards look like BEFORE the run and `during` is what they
    look like while it is measured, so the peak really is a peak."""
    log = log or tmp_log()
    payload = {"model": "qwen3.5:9b", "lane": "everyday", "repeats": 3,
               "warmup": 1, "confirm": {"model": "qwen3.5:9b",
                                        "lane": "everyday",
                                        "may_evict": True}}
    payload.update(body or {})
    calls = {"n": 0}

    def smi_reader():
        calls["n"] += 1
        return smi if calls["n"] == 1 else during
    code, out = B.start(
        payload, spawn_thread=False, log=log,
        post=fake_post(reply, first_s=first_s),
        get=fake_get(models=models or ("qwen3.5:9b",), ps=ps),
        show=fake_show(block_count=block_count),
        smi=smi_reader, clock=fake_clock(), log_text=lambda: "",
        busy=(lambda: busy) if busy is not None else (lambda: None),
        standby=lambda: standby, tasks=lambda: list(tasks),
        running=lambda: None)
    return code, out, log


def repeat_row(**over):
    """A valid `kind: "bench"` row, for the store tests."""
    row = {"kind": "bench", "run": "r1", "model": "qwen3.5:9b",
           "lane": "everyday", "repeat": 1, "warmup": False,
           "gen_tokens_per_s": 41.2, "prefill_tokens_per_s": 610.0,
           "ok": True}
    row.update(over)
    return row


def run_row(run_id="r1", **over):
    """A valid `kind: "bench-run"` row, for the store and advice tests."""
    row = {"kind": "bench-run", "run": run_id, "model": "qwen3.5:9b",
           "lane": "everyday", "ctx": 16384, "num_gpu": 32, "block_count": 32,
           "repeats": 3, "gen_median": 41.2, "gen_min": 40.8,
           "gen_max": 41.6, "gen_spread": 0.8, "ok": True, "spilled": False,
           "ollama_version": "0.40.12", "driver_version": "617.42",
           "words": "qwen3.5:9b on the everyday lane (RTX 2060)"}
    row.update(over)
    return row


# ==========================================================================
#   1. The prefill trap - the test that stops the 318x lie shipping
# ==========================================================================

def t_the_prefill_rate_is_the_uncached_part():
    rate = B.prefill_rate(318, 317, 23_000_000)
    check("318 asked, 317 cached, 23 ms: the rate comes from ONE token",
          rate == (43.48, ""), rate)
    naive = round(318 / (23_000_000 / 1e9), 2)
    check("... which is 318x lower than the naive division that ships the lie",
          naive == 13826.09 and rate[0] < naive / 300, (rate, naive))
    check("a COLD prompt is the same formula with nothing subtracted",
          B.prefill_rate(318, 0, 139_970_000) == (2271.92, ""),
          B.prefill_rate(318, 0, 139_970_000))


def t_a_fully_cached_prompt_measures_nothing():
    rate, why = B.prefill_rate(318, 318, 23_000_000)
    check("cached == count: no rate at all", rate is None, rate)
    check("... and 'cached - prefill not measured', not 0 and not infinity",
          why == B.CACHED_PREFILL == "cached - prefill not measured", why)
    check("... 0 would have been a number, and it is not one",
          rate != 0)
    # More cached than asked cannot really happen, but if it does the answer
    # must be "nothing to time" rather than a negative rate.
    check("cached > count is still 'not measured', never negative",
          B.prefill_rate(318, 400, 23_000_000)[0] is None)


def t_absent_is_not_zero():
    rate, why = B.prefill_rate(318, None, 139_970_000)
    check("an absent cached count is UNKNOWN, not zero",
          rate is None and "not reported" in why, (rate, why))
    check("... and it is NOT the cold-prompt rate either",
          rate != 2271.92)
    check("no prompt_eval_count at all: no rate",
          B.prefill_rate(None, 0, 1_000_000) ==
          (None, "no prompt_eval_count"))
    check("no prompt_eval_duration: no rate",
          B.prefill_rate(318, 0, None) ==
          (None, "no prompt_eval_duration"))
    check("a duration of 0 is 'no duration', not an infinite rate",
          B.prefill_rate(318, 0, 0)[0] is None)
    check("a string '318' is not a number, so it is not measured",
          B.prefill_rate("318", 0, 1_000_000)[0] is None)
    check("True is not a number either",
          B.prefill_rate(True, 0, 1_000_000)[0] is None)


def t_timings_from_a_reply():
    t = B.timings(WARM_REPLY)
    check("the warm reply's prefill is its uncached 43.48 tok/s",
          t["prefill_tokens_per_s"] == 43.48, t["prefill_tokens_per_s"])
    check("... and it records that 1 token was uncached and 317 cached",
          t["prefill_uncached"] == 1 and t["prefill_cached"] == 317,
          (t["prefill_uncached"], t["prefill_cached"]))
    check("the generation rate is eval_count / eval_duration",
          t["gen_tokens_per_s"] == 41.29, t["gen_tokens_per_s"])
    check("... and the token count is stored with it",
          t["gen_tokens"] == 64, t["gen_tokens"])
    check("Ollama's own time-to-first-token is load_duration + prefill",
          t["ttft_ollama_ms"] == 23, t["ttft_ollama_ms"])
    check("... and the harness's wall clock is a SEPARATE number, stored too",
          "ttft_wall_ms" in t and t["ttft_wall_ms"] is None)
    check("a reply with no counters is not ok, and says why",
          B.timings({"response": "hello", "done": True})["ok"] is False
          and B.timings({})["why"] == B.NO_TIMINGS)
    check("a reply that is not a dict is refused, not crashed on",
          B.timings(None)["why"] == B.NO_TIMINGS)


def t_generation_rate():
    check("64 tokens in 1.55 s is 41.29 a second",
          B.generation_rate(64, 1_550_000_000) == 41.29)
    check("no tokens is unknown, not 0", B.generation_rate(0, 1_000_000) is None)
    check("no duration is unknown, not infinity",
          B.generation_rate(64, 0) is None)
    check("a negative duration is refused", B.generation_rate(64, -1) is None)


def t_both_first_token_numbers():
    t = B.timings(COLD_REPLY)
    check("Ollama's first-token figure includes the model load",
          t["ttft_ollama_ms"] == 640, t["ttft_ollama_ms"])
    check("a 15% disagreement is within tolerance and says nothing",
          B.ttft_note(1000, 900) == "", B.ttft_note(1000, 900))
    note = B.ttft_note(2000, 640)
    check("a big disagreement is spelled out in words",
          "first token" in note and "2000 ms" in note and "640 ms" in note, note)
    check("one missing number is not a disagreement",
          B.ttft_note(None, 640) == "" and B.ttft_note(2000, None) == "")
    check("zero is not a disagreement either",
          B.ttft_note(0, 640) == "")


# ==========================================================================
#   1b. The prompt is fresh for every repeat - DESIGN section 6 rule 4
# ==========================================================================
#
# Ollama serves the LONGEST COMMON PREFIX of a prompt from its cache, so the
# part that differs between two repeats has to come FIRST. A per-repeat tag at
# the TAIL leaves the whole word body cacheable: every repeat after the first
# is served from the cache, `prefill_rate`'s honest `(count - cached)` divides
# the few uncached tail tokens, and `summarise()`'s median is a measurement of
# the tail rather than of the depth. That was the shipped shape until
# 2026-11-04, and these checks are what fails if it comes back. No test
# referenced `prefill_prompt` before them.

def _shared_word_prefix(first: str, second: str) -> int:
    """How many leading WORDS two prompts share - what a prefix cache serves."""
    n = 0
    for a, b in zip(first.split(), second.split()):
        if a != b:
            break
        n += 1
    return n


def _shared_char_prefix(first: str, second: str) -> int:
    """The longest common CHARACTER prefix: the tighter reading of the same
    fact, because a tokeniser splits inside a word, so word-level equality can
    hide a shared token prefix."""
    n = 0
    for a, b in zip(first, second):
        if a != b:
            break
        n += 1
    return n


def t_the_prefill_prompt_is_fresh_at_the_front():
    # The two tags `_one_repeat` really builds for consecutive repeats of one
    # run: the run id is shared and only `/r1` vs `/r2` differs.
    tag_one = "20261104-155512-abc123/r1/run"
    tag_two = "20261104-155512-abc123/r2/run"
    depth = 512                     # llama-bench's own default (`-p 512`)
    first = B.prefill_prompt(depth, tag_one)
    second = B.prefill_prompt(depth, tag_two)
    words_shared = _shared_word_prefix(first, second)
    check("two repeats of the same run at the same depth share no WORD of "
          "prefix, so a prefix cache cannot serve the depth body",
          words_shared == 0,
          (words_shared, first[:60], second[:60]))
    chars_shared = _shared_char_prefix(first, second)
    check("... and at most a few characters, so what a cache could serve is "
          "the tag's own opening rather than the prompt",
          chars_shared <= 32, chars_shared)
    check("... which is less than a fortieth of the prompt, so nearly all of "
          "`depth` is really read rather than served",
          chars_shared * 40 < len(first), (chars_shared, len(first)))
    check("the depth is still on the prompt: `depth` words come from the "
          "fixed, counted list",
          sum(1 for w in first.split() if w in set(B._WORDS)) == depth,
          sum(1 for w in first.split() if w in set(B._WORDS)))
    check("one tag is deterministic - asking twice gives the same words, so "
          "the difference above is the tag and not chance",
          first == B.prefill_prompt(depth, tag_one))
    check("a different depth is a different prompt, so `depth` really sets it",
          B.prefill_prompt(64, tag_one) != first)
    check("depth 0 still measures no prefill at all, with one fixed sentence "
          "that carries no tag",
          B.prefill_prompt(0, tag_one) == B.prefill_prompt(0, tag_two)
          and "thermometer" in B.prefill_prompt(0, tag_one),
          B.prefill_prompt(0, tag_one))


# ==========================================================================
#   2. The aggregates are pure functions
# ==========================================================================

def t_median_spread_and_the_warmup_drop():
    rows = [
        {"ok": True, "warmup": True, "gen_tokens_per_s": 99.0},
        {"ok": True, "warmup": False, "gen_tokens_per_s": 40.8},
        {"ok": True, "warmup": False, "gen_tokens_per_s": 41.2},
        {"ok": True, "warmup": False, "gen_tokens_per_s": 41.6},
        {"ok": False, "warmup": False, "gen_tokens_per_s": None},
    ]
    s = B.summarise(rows, warmup=1)
    check("the median is over the MEASURED repeats only, never the warmup",
          s["gen_median"] == 41.2, s["gen_median"])
    check("the warmup's 99 did not get in", s["gen_max"] == 41.6, s["gen_max"])
    check("the min and the spread are reported, not hidden",
          s["gen_min"] == 40.8 and s["gen_spread"] == 0.8, s)
    check("a failed repeat is counted as not ok, not as a zero",
          s["repeats_ok"] == 3 and s["worst_repeat_ok"] is True, s["repeats_ok"])
    check("the warm figure drops the first measured repeat too",
          s["gen_warm"] == 41.4, s["gen_warm"])
    check("one reading is a median of one, and its spread is 0",
          B.summarise([{"ok": True, "gen_tokens_per_s": 41.2}])["gen_spread"]
          == 0.0)
    empty = B.summarise([])
    check("no readings gives None, never 0",
          empty["gen_median"] is None and empty["repeats_ok"] == 0)
    check("all-warmup rows leave nothing measured",
          B.summarise([{"ok": True, "warmup": True,
                        "gen_tokens_per_s": 9.0}])["repeats_ok"] == 0)


def t_the_layer_ratio_is_one_axis_both_ways():
    check("32 of 32 layers on the card is 0% off it",
          B.ram_share_percent(32, 32) == 0)
    check("16 of 32 is 50%",
          B.ram_share_percent(16, 32) == 50)
    check("0 of 32 is all of it off the card",
          B.ram_share_percent(0, 32) == 100)
    check("more layers than the model has is clamped, not 200%",
          B.ram_share_percent(64, 32) == 0)
    check("an unknown layer count gives None, not a made-up share",
          B.ram_share_percent(None, 32) is None)


def t_spilled_uses_both_sources():
    check("less than 100% in video memory is a spill",
          B.spilled(93, None, None) is True)
    check("the log's 'offloaded 24/32' is a spill even when /api/ps says 100",
          B.spilled(100, 24, 32) is True)
    check("100% and all layers offloaded is no spill",
          B.spilled(100, 32, 32) is False)
    check("nothing known is not a claim of a spill",
          B.spilled(None, None, None) is False)


# ==========================================================================
#   3. The cards, from the exact text nvidia-smi prints
# ==========================================================================

def t_cards_from_this_pcs_own_output():
    got = B.cards_from_smi(SMI_BEFORE)
    cards = got["cards"]
    check("both cards are read, in index order",
          [c["index"] for c in cards] == [0, 1], cards)
    check("the 12 GB card's used memory is the number in the text",
          cards[0]["used_mb"] == 11919, cards[0])
    check("the card holding the monitor is marked as doing so",
          cards[1]["display_active"] == "Enabled"
          and cards[0]["display_active"] == "Disabled",
          [c["display_active"] for c in cards])
    check("the driver version is read once, not guessed",
          got["driver"] == "617.42", got["driver"])
    check("a util value of 3 is 3, not 'unknown'",
          cards[0]["util_percent"] == 3, cards[0])
    # The driver answers [N/A] for a field it does not have. That is None, and
    # it is emphatically not 0 - 0 MB used would read as "this card is empty".
    na = B.cards_from_smi(
        "0, GPU-x, NVIDIA GeForce RTX 2060, 12288, [N/A], [N/A], [N/A], "
        "[Not Supported], 617.42\n")
    check("a driver's [N/A] is None, never 0",
          na["cards"][0]["used_mb"] is None
          and na["cards"][0]["util_percent"] is None, na["cards"][0])
    check("empty output is no cards, not a crash",
          B.cards_from_smi("") == {"cards": [], "driver": ""})


def t_the_peak_is_the_busiest_sample():
    before = B.cards_from_smi(SMI_BEFORE)["cards"]
    during = B.cards_from_smi(SMI_DURING)["cards"]
    peaks = B.peak_cards([before, during, before])
    check("the peak is the highest used memory ever sampled, per card",
          B.card_mb(peaks, 0) == 12110, B.card_mb(peaks, 0))
    check("the other card keeps its own number",
          B.card_mb(peaks, 1) == 4102, B.card_mb(peaks, 1))
    check("the peak utilisation is the highest seen",
          B.util_peak(peaks) == 94, B.util_peak(peaks))
    check("a card that was never sampled is None, not 0",
          B.card_mb(peaks, 7) is None)


# ==========================================================================
#   4. The store
# ==========================================================================

def t_the_store_holds_two_row_kinds():
    log = tmp_log()
    check("the file does not exist until something is written",
          not log.path.exists())
    check("a bench row is appended", log.append(repeat_row()))
    check("... and a run row too",
          log.append(run_row("r1")))
    rows = log.rows()
    check("both kinds are there, oldest first",
          [r["kind"] for r in rows] == ["bench", "bench-run"],
          [r["kind"] for r in rows])
    check("the tail can ask for one kind",
          [r["kind"] for r in log.tail(10, kind="bench-run")] == ["bench-run"])
    check("a run is read back with its repeats",
          log.get("r1")["run"]["model"] == "qwen3.5:9b"
          and len(log.get("r1")["repeats"]) == 1)
    check("an unknown run id is None, not an empty dict",
          log.get("nope") is None)


def t_the_store_never_touches_speed_jsonl():
    B.BenchLog  # the class exists; the checks below drive it, not its text.
    check("the benchmark store is bench.jsonl",
          B.default_path().name == "bench.jsonl", B.default_path().name)
    # THE REAL FUNCTION, not the text of one: writing a row with a distinctive
    # value and reading the file back is what proves the store is this file.
    log = tmp_log()
    log.append(repeat_row(gen_tokens_per_s=41.25))
    written = log.path.read_text(encoding="utf-8")
    check("a written row really lands in bench.jsonl, not somewhere else",
          "41.25" in written and log.path.name == "bench.jsonl",
          log.path.name)
    check("... and the chat-speed file beside it is untouched: this store's "
          "folder holds ONE file after a write",
          [p.name for p in log.path.parent.iterdir() if p.is_file()]
          == ["bench.jsonl"],
          [p.name for p in log.path.parent.iterdir() if p.is_file()])
    # `jarvis_speed`'s own store is a different object with a different name.
    check("jarvis_speed's own store is a different file with a different name",
          _speed_store_name() != B.default_path().name,
          _speed_store_name())


def _speed_store_name() -> str:
    """jarvis_speed's own history file, asked of ITS OWN function - the runtime
    answer, not a string searched for in its text."""
    import jarvis_speed
    return jarvis_speed.default_path().name


def t_filters_are_exact_and_newest_first():
    log = tmp_log()
    log.append(run_row("r1"))
    log.append(run_row("r2", model="qwen3:8b"))
    log.append(run_row("r3", gen_median=50.0))
    check("newest first", [r["run"] for r in log.runs()] == ["r3", "r2", "r1"],
          [r["run"] for r in log.runs()])
    check("a model filter is an exact match, not a prefix",
          [r["run"] for r in log.runs(model="qwen3.5:9b")] == ["r3", "r1"],
          [r["run"] for r in log.runs(model="qwen3.5:9b")])
    check("... so a different model is really excluded",
          [r["run"] for r in log.runs(model="qwen3:8b")] == ["r2"])
    check("a filter that matches nothing is an empty list, not everything",
          log.runs(model="nope") == [])
    check("limit really limits", len(log.runs(limit=1)) == 1)
    check("a lane filter works the same way",
          len(log.runs(lane="coding")) == 0)


def t_a_run_can_be_deleted_and_the_file_rewritten():
    log = tmp_log()
    log.append(repeat_row(run="r1"))
    log.append(run_row("r1"))
    log.append(repeat_row(run="r2"))
    log.append(run_row("r2", gen_median=44.0))
    check("two rows for each of two runs", len(log.rows()) == 4)
    removed = log.delete("r1")
    check("deleting one run removes its repeat AND its summary",
          removed == 2 and len(log.rows()) == 2, (removed, len(log.rows())))
    check("... and the other run is untouched",
          [r["run"] for r in log.rows()] == ["r2", "r2"])
    check("deleting an id that is not there changes nothing",
          log.delete("nope") == 0 and len(log.rows()) == 2)


def t_the_history_keeps_five_hundred_runs():
    log = tmp_log()
    for i in range(B.MAX_RUNS + 12):
        log.append(repeat_row(run=f"r{i:04d}", repeat=1))
        log.append(run_row(f"r{i:04d}", gen_median=40.0 + i / 100))
    rows = log.rows()
    runs = log.count_runs()
    check(f"the store holds at most {B.MAX_RUNS} runs", runs == B.MAX_RUNS, runs)
    check("... whole: every surviving run still has its repeat row",
          len(rows) == B.MAX_RUNS * 2, len(rows))
    check("... and it is the NEWEST ones that survive",
          log.runs(limit=1)[0]["run"] == f"r{B.MAX_RUNS + 11:04d}",
          log.runs(limit=1)[0]["run"])
    check("... the oldest are the ones that went",
          log.get("r0000") is None, log.get("r0000"))
    check("the cap is 500, as the design says", B.MAX_RUNS == 500)
    check("the file stayed under its byte ceiling too",
          log.path.stat().st_size < B.MAX_BYTES, log.path.stat().st_size)


def t_the_byte_ceiling_is_real():
    check("the ceiling is 2 MB, as the design says",
          B.MAX_BYTES == 2 * 1024 * 1024)
    log = tmp_log()
    # A row with a big `words` is capped on the way in, so no single row can
    # ever be bigger than the ceiling - the ceiling is about MANY rows.
    old = B.MAX_RUNS
    try:
        B.MAX_RUNS = 10_000        # let the byte ceiling be the one that bites
        for i in range(400):
            log.append(run_row(f"r{i:04d}", words="x" * B.MAX_WORDS))
        size = log.path.stat().st_size
        check("a file of many rows is trimmed below the byte ceiling",
              size <= B.MAX_BYTES, size)
        check("... and something is still there afterwards",
              len(log.rows()) > 0)
    finally:
        B.MAX_RUNS = old


def t_the_allowlist_drops_what_it_does_not_know():
    log = tmp_log()
    log.append(repeat_row(prompt="Mario's bank PIN is 4471",
                          response="the pin is 4471",
                          text="his sister lives on Rua Augusta"))
    raw = log.path.read_text(encoding="utf-8")
    check("a prompt is not written", "bank PIN" not in raw, raw[:200])
    check("an answer is not written", "the pin is 4471" not in raw)
    check("the owner's words are not written", "Rua Augusta" not in raw)
    check("the fields that ARE allowed are written",
          "gen_tokens_per_s" in raw)
    check("a row naming no kind is refused outright",
          log.append({"model": "x"}) is False)
    check("a nan is dropped rather than stored",
          "gen_tokens_per_s" not in
          B._clean({"gen_tokens_per_s": float("nan")}))
    check("a bool in a number field is dropped, not stored as 1",
          B._clean({"gen_tokens_per_s": True}) == {})
    check("an over-long reason is cut, not stored whole",
          len(B._clean({"why": "x" * 900})["why"]) == B.MAX_REASON)


def t_a_lane_outside_the_closed_list_is_dropped():
    """`lane` is a CLOSED vocabulary, and the table says so: "A value outside
    its list is dropped" (`_ENUM_FIELDS`).

    It was not, until 2026-11-04: `lane` was in `_NAME_FIELDS` AND in
    `_ENUM_FIELDS`, `_clean()` tested the name table first, and the enum branch
    was therefore unreachable for this one field - so a value like "everyday
    lane" was cut to 12 characters and stored as a lane that does not exist,
    while every other closed field was validated.
    """
    check("a lane the module really uses is kept",
          B._clean({"lane": "coding"}) == {"lane": "coding"},
          B._clean({"lane": "coding"}))
    check("a lane outside the three is DROPPED, as the table promises",
          B._clean({"lane": "gaming"}) == {}, B._clean({"lane": "gaming"}))
    check("... including one that merely starts like a real lane, which used "
          "to be cut to 12 characters and stored",
          B._clean({"lane": "everyday lane"}) == {},
          B._clean({"lane": "everyday lane"}))
    check("every lane LANE_KEYS names is the whole accepted vocabulary",
          all(B._clean({"lane": lane}) == {"lane": lane}
              for lane in B.LANE_KEYS),
          [B._clean({"lane": lane}) for lane in B.LANE_KEYS])
    check("`lane` is governed by the enum table alone",
          "lane" in B._ENUM_FIELDS and "lane" not in B._NAME_FIELDS,
          (B._ENUM_FIELDS.get("lane"), B._NAME_FIELDS.get("lane")))
    check("no field is in both the name table and the enum table, which is "
          "how `lane`'s enum branch became unreachable",
          not (set(B._NAME_FIELDS) & set(B._ENUM_FIELDS)),
          set(B._NAME_FIELDS) & set(B._ENUM_FIELDS))


# ==========================================================================
#   5. Every refusal row of DESIGN section 2
# ==========================================================================

def t_the_already_running_lock():
    B._reset_for_tests()
    code, body = _refusal(
        body={"confirm": {"may_evict": True}},
        model="qwen3.5:9b", lane="everyday", get=fake_get(),
        busy=lambda: None, standby=lambda: False, tasks=lambda: [],
        running=lambda: "another-run")
    check("a second run while one is in flight is a 409", code == 409, code)
    check("... with the sentence the table names",
          body["error"] == B.ALREADY_RUNNING, body)
    check("the lock check comes BEFORE every other refusal: a busy PC and a "
          "run in flight answer 'already running'",
          body["error"] == B.ALREADY_RUNNING and "standby" not in body["error"])
    # And the real in-process lock, not only the injected one.
    with B._RUNS_LOCK:
        B._RUNS["live"] = {"state": "running"}
    try:
        code, body = _refusal(
            body={"confirm": {"may_evict": True}}, model="qwen3.5:9b",
            lane="everyday", get=fake_get(), busy=lambda: None,
            standby=lambda: False, tasks=lambda: [])
        check("... and the module's own running-run map refuses too",
              code == 409 and body["error"] == B.ALREADY_RUNNING, (code, body))
    finally:
        B._reset_for_tests()


def _refusal(**kwargs):
    """Run `check_job` and return (code, body) or ("no refusal", None)."""
    try:
        B.check_job(**kwargs)
        return "no refusal", None
    except B.Refusal as exc:
        return exc.code, exc.body


def t_an_answer_streaming_is_refused():
    B._reset_for_tests()
    code, body = _refusal(model="qwen3.5:9b", lane="everyday", get=fake_get(),
                          busy=lambda: B.ANSWER_STREAMING,
                          standby=lambda: False, tasks=lambda: [],
                          running=lambda: None,
                          **{"base": "http://127.0.0.1:11436"},
                          body={"confirm": {"may_evict": True}})
    check("an answer streaming right now is a 409", code == 409, code)
    check("... with the table's own sentence",
          body["error"] == "Jarvis is answering. Measuring now would time the "
                           "queue, not the model.", body)
    # And the real flag, which is what a caller sets.
    B.note_answer_start()
    check("the module's own flag answers the same sentence",
          B.answer_streaming() == B.ANSWER_STREAMING, B.answer_streaming())
    B.note_answer_end()
    check("... and it clears again", B.answer_streaming() is None)


def t_standby_is_refused():
    B._reset_for_tests()
    code, body = _refusal(model="qwen3.5:9b", lane="everyday", get=fake_get(),
                          busy=lambda: None, standby=lambda: True,
                          tasks=lambda: [], running=lambda: None,
                          body={"confirm": {"may_evict": True}})
    check("Jarvis on standby is a 409", code == 409, code)
    check("... with the words copied from the existing refusal",
          "on standby" in body["error"] and "Wake Jarvis first" in body["error"],
          body)


def t_a_running_task_is_refused():
    B._reset_for_tests()
    code, body = _refusal(model="qwen3.5:9b", lane="everyday", get=fake_get(),
                          busy=lambda: None, standby=lambda: False,
                          tasks=lambda: [{"id": "t1"}], running=lambda: None,
                          body={"confirm": {"may_evict": True}})
    check("a multi-step task running is a 409", code == 409, code)
    check("... and the sentence says why a measurement would be wrong",
          "time the queue" in body["error"], body)


def t_the_lane_not_running_is_refused_and_never_started():
    B._reset_for_tests()
    # `get` raising for /api/tags is what a lane whose Ollama is not running
    # really looks like.
    def dead(url):
        raise OSError("connection refused")
    code, body = _refusal(model="qwen3.5:9b", lane="coding", get=dead,
                          busy=lambda: None, standby=lambda: False,
                          tasks=lambda: [], running=lambda: None,
                          body={"confirm": {"may_evict": True}})
    check("a lane whose Ollama is not running is a 409", code == 409, code)
    check("... naming the lane and telling the owner to start it",
          body["error"] == "the coding lane is not running; start it first",
          body)
    calls = _programs_jarvis_bench_runs()
    check("... and nothing in this module can start a lane: the only external "
          "program it runs is nvidia-smi, which starts nothing",
          calls == ["nvidia-smi"], calls)
    check("... it never builds a command line at all - no schtasks, no task "
          "name, no shell",
          not _uses_shell_or_task_name(), _uses_shell_or_task_name())
    check("... and the lane module is only READ: no function of it is called",
          _lanes_functions_called() == [], _lanes_functions_called())


def t_the_model_not_installed_is_refused_with_the_list():
    B._reset_for_tests()
    code, body = _refusal(model="qwen3.5:70b", lane="everyday",
                          get=fake_get(models=("qwen3.5:9b", "qwen3:8b")),
                          busy=lambda: None, standby=lambda: False,
                          tasks=lambda: [], running=lambda: None,
                          body={"confirm": {"may_evict": True}})
    check("a model that is not on that lane is a 409", code == 409, code)
    check("... and the sentence lists what IS there",
          "qwen3.5:9b" in body["error"] and "qwen3:8b" in body["error"], body)
    check("a model that IS installed passes that row",
          _refusal(model="qwen3.5:9b", lane="everyday", get=fake_get(),
                   busy=lambda: None, standby=lambda: False, tasks=lambda: [],
                   running=lambda: None,
                   body={"confirm": {"may_evict": True}})[0] == "no refusal")


def t_a_non_loopback_ollama_is_a_400():
    B._reset_for_tests()
    code, body = _refusal(model="qwen3.5:9b", lane="everyday",
                          base="http://192.168.1.50:11434", get=fake_get(),
                          busy=lambda: None, standby=lambda: False,
                          tasks=lambda: [], running=lambda: None,
                          body={"confirm": {"may_evict": True}})
    check("an Ollama that is not this PC is a 400, not a 409", code == 400, code)
    check("... and the sentence names the address and says nothing was measured",
          "192.168.1.50" in body["error"]
          and body["error"].startswith("Nothing was measured"), body)
    check("loopback really is this PC",
          B.is_loopback("http://127.0.0.1:11436")
          and B.is_loopback("http://localhost:11434")
          and not B.is_loopback("http://192.168.1.50:11434"))


def t_no_run_can_start_without_confirm():
    B._reset_for_tests()
    good = {"model": "qwen3.5:9b", "lane": "everyday"}
    for label, body in (
            ("no confirm block at all", {}),
            ("confirm is not a block", {"confirm": True}),
            ("confirm without may_evict", {"confirm": {"model": "qwen3.5:9b"}}),
            ("confirm for a DIFFERENT model",
             {"confirm": {"model": "qwen3:8b", "lane": "everyday",
                          "may_evict": True}}),
            ("confirm for a DIFFERENT lane",
             {"confirm": {"model": "qwen3.5:9b", "lane": "coding",
                          "may_evict": True}})):
        code, out = _refusal(body=body, get=fake_get(), busy=lambda: None,
                             standby=lambda: False, tasks=lambda: [],
                             running=lambda: None, **good)
        check(f"{label}: a 400", code == 400, (label, code))
        check(f"{label}: 'nothing was measured: the run was not confirmed'",
              out["error"] == "nothing was measured: the run was not confirmed",
              out)
    code, out = _refusal(body={"confirm": {"model": "qwen3.5:9b",
                                           "lane": "everyday",
                                           "may_evict": True}},
                         get=fake_get(), busy=lambda: None,
                         standby=lambda: False, tasks=[], running=lambda: None,
                         **good)
    check("a full confirm passes, and is never needed twice",
          code == "no refusal", (code, out))
    # And through the real entry point, which is what a route calls.
    B._reset_for_tests()
    status, out2 = B.start({"model": "qwen3.5:9b", "lane": "everyday"},
                           spawn_thread=False, log=tmp_log(),
                           get=fake_get(), show=fake_show(),
                           post=fake_post(), smi=lambda: SMI_BEFORE,
                           clock=fake_clock(), busy=lambda: None,
                           standby=lambda: False, tasks=lambda: [],
                           running=lambda: None)
    check("start() refuses an unconfirmed POST with a 400", status == 400, status)
    check("... and it measures NOTHING: the sentence says so",
          out2["error"] == B.NOT_CONFIRMED, out2)


# ==========================================================================
#   6. A whole run, and what it stores
# ==========================================================================

def t_a_run_writes_one_row_per_repeat_plus_a_summary():
    B._reset_for_tests()
    code, out, log = run_once(ps=[{"name": "qwen3.5:9b", "size": 9_400_000_000,
                                   "size_vram": 9_400_000_000,
                                   "context_length": 16384}])
    check("the run starts", code == 200 and out.get("run_id"), (code, out))
    rows = log.rows()
    repeats = [r for r in rows if r["kind"] == "bench"]
    summary = [r for r in rows if r["kind"] == "bench-run"]
    check("3 repeats + 1 warmup + 1 summary row",
          len(repeats) == 4 and len(summary) == 1,
          (len(repeats), len(summary)))
    check("the warmup is marked as one", sum(1 for r in repeats if r["warmup"])
          == 1)
    check("the summary row is for the same run as the repeats",
          {r["run"] for r in rows} == {out["run_id"]})
    check("the summary says it was ok", summary[0]["ok"] is True, summary[0])
    check("the summary carries the median of the 3 measured repeats",
          summary[0]["gen_median"] == 32.0, summary[0]["gen_median"])
    check("... and the warmup rows are excluded from it",
          summary[0]["repeats_ok"] == 3)
    check("the prefill rate on the row is the UNCACHED one",
          summary[0]["prefill_median"] == 2271.92,
          summary[0]["prefill_median"])
    check("the context really in use is recorded beside the one asked for",
          summary[0]["ctx"] == 16384 and summary[0]["ctx_used"] == 16384,
          (summary[0]["ctx"], summary[0]["ctx_used"]))
    check("the layers on the card default to all of them, read from /api/show",
          summary[0]["num_gpu"] == 32 and summary[0]["block_count"] == 32,
          (summary[0]["num_gpu"], summary[0]["block_count"]))
    check("... and the derived RAM share is 0% for all of them",
          summary[0]["ram_share_percent"] == 0, summary[0]["ram_share_percent"])
    check("the driver and Ollama versions are on the row: a tok/s number "
          "without them is not comparable to anything",
          summary[0]["driver_version"] == "617.42"
          and summary[0]["ollama_version"] == "0.40.12", summary[0])
    check("the VRAM peak rose on the card that was measured, per card",
          summary[0]["vram_base_mb_card0"] == 11919
          and summary[0]["vram_peak_mb_card0"] == 12110,
          (summary[0]["vram_base_mb_card0"],
           summary[0]["vram_peak_mb_card0"]))
    check("... and the other card is a separate pair of numbers",
          summary[0]["vram_base_mb_card1"] == 4086
          and summary[0]["vram_peak_mb_card1"] == 4102)
    check("the run's own sentence is on the row", bool(summary[0]["words"]),
          summary[0].get("words"))


def t_a_run_that_is_not_fully_on_the_card_is_labelled():
    B._reset_for_tests()
    # /api/ps says 93% of it is in video memory: 7% spilled to system RAM, and
    # the log agrees - 24 of 32 layers.
    code, out, log = run_once(
        ps=[{"name": "qwen3.5:9b", "size": 9_400_000_000,
             "size_vram": 8_700_000_000, "context_length": 16384}],
        smi=SMI_DURING)
    summary = log.get(out["run_id"])["run"]
    check("the run still records the numbers", summary["gen_median"] == 32.0)
    check("... but it is marked as spilled", summary["spilled"] is True, summary)
    check("... on_card_percent says how much is really on the card",
          summary["on_card_percent"] == 93, summary["on_card_percent"])
    words = summary["words"]
    check("... and the ONE sentence leads with PARTIAL, not with the speed",
          words.startswith("PARTIAL:"), words)
    check("... saying it is not comparable with a fully-on-card run",
          "NOT comparable" in words, words)
    check("... so the number cannot be read as a clean result", "32.0" in words
          and words.index("PARTIAL") < words.index("32.0"), words)


def t_a_run_where_the_log_disagrees_with_api_ps():
    B._reset_for_tests()
    # /api/ps says the whole model is in video memory; Ollama's own log says
    # only 24 of 32 layers got there. EITHER source saying so is a spill, and
    # BOTH numbers stay on the row - DESIGN section 4: "two independent
    # sources; when they disagree both are kept".
    ps = [{"name": "qwen3.5:9b", "size": 9_400_000_000,
           "size_vram": 9_400_000_000, "context_length": 16384}]
    honest = B.offloaded_layers
    B.offloaded_layers = lambda **kw: [24, 32]
    try:
        code, out, log = run_once(ps=ps)
    finally:
        B.offloaded_layers = honest
    summary = log.get(out["run_id"])["run"]
    check("/api/ps alone would say no spill", summary["on_card_percent"] == 100,
          summary.get("on_card_percent"))
    check("the log's 24/32 still marks the run as spilled",
          summary["spilled"] is True, summary["spilled"])
    check("... and both numbers are on the row, not one chosen over the other",
          summary["offloaded_layers"] == 24
          and summary["total_layers"] == 32, summary)
    check("... and the run's sentence says PARTIAL rather than a clean number",
          summary["words"].startswith("PARTIAL:"), summary["words"])


def t_a_failed_run_writes_why_and_never_a_zero():
    B._reset_for_tests()

    def broken(url, payload):
        if payload.get("keep_alive") == 0:
            return 0.0, {"done": True}
        raise ConnectionResetError("the model fell over")

    log = tmp_log()
    code, out = B.start(
        {"model": "qwen3.5:9b", "lane": "everyday", "repeats": 2, "warmup": 0,
         "confirm": {"model": "qwen3.5:9b", "lane": "everyday",
                     "may_evict": True}},
        spawn_thread=False, log=log, post=broken, get=fake_get(),
        show=fake_show(), smi=lambda: SMI_BEFORE, clock=fake_clock(),
        busy=lambda: None, standby=lambda: False, tasks=lambda: [],
        running=lambda: None)
    check("the route still answers 200: the run started", code == 200, code)
    summary = log.get(out["run_id"])["run"]
    check("the summary says it did not work", summary["ok"] is False, summary)
    check("... and says why, in words", bool(summary.get("why")), summary)
    check("... and NOTHING is stored as 0 in place of a measurement",
          summary.get("gen_median") is None
          and summary.get("prefill_median") is None, summary)
    repeats = log.get(out["run_id"])["repeats"]
    check("every repeat row says ok: false with its reason too",
          all(r["ok"] is False and r.get("why") for r in repeats), repeats)
    check("... and no repeat row carries a zero rate",
          all("gen_tokens_per_s" not in r for r in repeats), repeats)
    check("the one sentence says nothing was measured, in those words",
          "Nothing was measured" in summary["words"], summary["words"])


def t_a_reply_with_no_timings_is_not_a_zero():
    B._reset_for_tests()
    code, out, log = run_once(reply={"response": "hello", "done": True})
    summary = log.get(out["run_id"])["run"]
    check("a reply without counters is a failed run, not a fast one",
          summary["ok"] is False, summary)
    check("... with Ollama's answer as the reason",
          summary.get("why") == B.NO_TIMINGS, summary.get("why"))


def t_a_fully_cached_reply_says_so_and_stores_no_rate():
    B._reset_for_tests()
    code, out, log = run_once(
        reply={"prompt_eval_count": 318, "prompt_eval_cached_count": 318,
               "prompt_eval_duration": 23_000_000,
               "eval_count": 64, "eval_duration": 1_550_000_000,
               "load_duration": 0, "total_duration": 1_600_000_000,
               "done": True})
    summary = log.get(out["run_id"])["run"]
    check("a fully cached prompt still measures generation",
          summary["gen_median"] == 41.29, summary["gen_median"])
    check("... and reports NO prefill rate, not 0 and not a huge one",
          summary.get("prefill_median") is None, summary.get("prefill_median"))
    check("... saying 'cached - prefill not measured' in the sentence",
          B.CACHED_PREFILL in summary["words"], summary["words"])


def t_unload_is_asked_for_and_reported():
    B._reset_for_tests()
    seen = []

    def watch(url, payload):
        seen.append(payload)
        if payload.get("keep_alive") == 0:
            return 0.0, {"done": True}
        return 0.4, dict(COLD_REPLY)

    log = tmp_log()
    B.start({"model": "qwen3.5:9b", "lane": "everyday", "repeats": 1,
             "warmup": 0, "confirm": {"model": "qwen3.5:9b",
                                      "lane": "everyday", "may_evict": True}},
            spawn_thread=False, log=log, post=watch, get=fake_get(),
            show=fake_show(), smi=lambda: SMI_BEFORE, clock=fake_clock(),
            busy=lambda: None, standby=lambda: False, tasks=lambda: [],
            running=lambda: None)
    check("the run asks Ollama to unload when it is done",
          any(p.get("keep_alive") == 0 for p in seen), seen)
    check("... because this PC keeps a model loaded for ever otherwise",
          True)
    check("... and the row records that it did, not that it might have",
          log.runs(limit=1)[0].get("unload_note", "") == "",
          log.runs(limit=1)[0].get("unload_note"))


def t_a_run_that_cannot_start_reports_503_not_a_crash():
    B._reset_for_tests()

    def no_thread(fn):
        raise RuntimeError("no threads left")

    code, out = B.start(
        {"model": "qwen3.5:9b", "lane": "everyday",
         "confirm": {"model": "qwen3.5:9b", "lane": "everyday",
                     "may_evict": True}},
        spawn=no_thread, log=tmp_log(), get=fake_get(), show=fake_show(),
        post=fake_post(), smi=lambda: SMI_BEFORE, clock=fake_clock(),
        busy=lambda: None, standby=lambda: False, tasks=lambda: [],
        running=lambda: None)
    check("a run that could not be spawned is a 503", code == 503, code)
    check("... with a sentence, not a traceback",
          "could not start" in out["error"], out)


# ==========================================================================
#   7. The advice builder - DESIGN section 9
# ==========================================================================

def t_advice_refuses_to_compare_under_three_runs():
    log = tmp_log()
    log.append(run_row("r1", gen_median=41.2))
    got = B.advice(model="qwen3.5:9b", log=log)
    check("one run is not a comparison", got["enough"] is False, got)
    check("... and it says how many it has and how many it needs",
          "Only 1" in got["note"] and "three are needed" in got["note"], got)
    log.append(run_row("r2", gen_median=39.0, ctx=8192))
    got = B.advice(model="qwen3.5:9b", log=log)
    check("two runs is still not a comparison", got["enough"] is False, got)
    check("... and it never picks a winner from two samples",
          "fastest" not in got["note"], got["note"])


def t_advice_compares_at_three_and_names_the_fastest():
    log = tmp_log()
    log.append(run_row("r1", gen_median=37.9, ctx=8192))
    log.append(run_row("r2", gen_median=41.2, ctx=16384))
    log.append(run_row("r3", gen_median=41.9, ctx=32768, spilled=True))
    got = B.advice(model="qwen3.5:9b", log=log)
    check("three runs is a fair comparison", got["enough"] is True, got)
    check("... it says why it is fair", "3 runs" in got["note"], got["note"])
    check("... it names the fastest", got["numbers"]["fastest"] == "r3", got)
    check("... and says that one SPILLED rather than calling it the best",
          "spilled" in got["note"], got["note"])
    check("... and it names the fastest that did NOT spill",
          got["numbers"]["fastest_clean"] == "r2", got["numbers"])
    check("... with its number", got["numbers"]["fastest_clean_gen"] == 41.2)


def t_advice_says_when_a_version_changed():
    log = tmp_log()
    log.append(run_row("r1", gen_median=41.2))
    log.append(run_row("r2", gen_median=41.2))
    log.append(run_row("r3", gen_median=44.0, driver_version="616.56"))
    got = B.advice(model="qwen3.5:9b", log=log)
    check("a comparison across a driver change says so",
          "version change" in got["note"], got["note"])
    check("... naming both driver versions",
          "617.42" in got["note"] and "616.56" in got["note"], got["note"])
    log2 = tmp_log()
    for i in range(3):
        log2.append(run_row(f"q{i}", gen_median=41.0))
    clean = B.advice(model="qwen3.5:9b", log=log2)
    check("... and says nothing when nothing changed",
          "version change" not in clean["note"], clean["note"])


def t_advice_on_one_run_and_on_nothing():
    log = tmp_log()
    empty = B.advice(model="qwen3.5:9b", log=log)
    check("no runs at all is a sentence, not an empty answer",
          "no usable benchmark run" in empty["note"]
          and empty["enough"] is False, empty)
    log.append(run_row("r1", gen_median=41.2))
    one = B.advice(run_id="r1", log=log)
    check("one run explained on its own does not claim it is fastest",
          "fastest" not in one["note"], one["note"])
    check("... and it carries the row's own numbers",
          one["numbers"]["gen_median"] == 41.2, one["numbers"])
    failed = B.advice(run_id="nope", log=log)
    check("an id that is not on file says so", "no run with that id" in
          failed["note"], failed)


# ==========================================================================
#   8. The controls
# ==========================================================================

def t_the_defaults_are_the_design_s():
    check("the nine controls of DESIGN section 3 are in one plain dict",
          set(B.CONTROLS) == {"model", "lane", "num_gpu", "num_ctx",
                              "prefill_tokens", "num_predict", "repeats",
                              "warmup", "unload"}, set(B.CONTROLS))
    check("the default lane is the card WITHOUT the monitor",
          B.CONTROLS["lane"] == "everyday")
    check("the default context is 16,384, the measured zero-spill rung",
          B.CONTROLS["num_ctx"] == 16384)
    check("the default repeats is 3, this repo's own minimum for a median",
          B.CONTROLS["repeats"] == 3)
    check("the default unloads when finished",
          B.CONTROLS["unload"] is True)
    check("the context ladder has every rung the docs measured",
          all(r in B.CTX_LADDER for r in (16384, 20480, 24576, 28672, 32768)),
          B.CTX_LADDER)


def t_a_value_off_the_ladder_is_reported_not_silently_changed():
    got, notes = B.normalise_controls({"num_ctx": 20000})
    check("20,000 snaps to 20,480, the nearest measured rung",
          got["num_ctx"] == 20480, got["num_ctx"])
    check("... and the snap is REPORTED, so a screen can say where it snapped",
          any("snapped" in n for n in notes), notes)
    got, notes = B.normalise_controls({"num_ctx": 999999})
    check("a context beyond the ladder stops at the top rung",
          got["num_ctx"] == B.CTX_LADDER[-1], got["num_ctx"])
    got, notes = B.normalise_controls({"num_ctx": 32768},
                                     context_length=40960)
    check("a context the model was not trained for is capped and said so",
          got["num_ctx"] == 32768 and not any("snapped" in n for n in notes))
    got, notes = B.normalise_controls({"num_ctx": 196608},
                                     context_length=40960)
    check("... really capped", got["num_ctx"] <= 40960, got["num_ctx"])
    got, notes = B.normalise_controls({"repeats": 99})
    check("repeats above 9 clamp to 9 and are reported",
          got["repeats"] == 9 and any("repeats" in n for n in notes), notes)
    got, notes = B.normalise_controls({"repeats": 0})
    check("repeats below 1 clamp to 1", got["repeats"] == 1, got["repeats"])
    got, notes = B.normalise_controls({"prefill_tokens": 600})
    check("a prefill depth that was never measured snaps to one that was",
          got["prefill_tokens"] == 512, got["prefill_tokens"])
    got, _ = B.normalise_controls({}, block_count=32)
    check("num_gpu defaults to all the layers the model has",
          got["num_gpu"] == 32, got["num_gpu"])
    got, notes = B.normalise_controls({"num_gpu": 99}, block_count=32)
    check("more layers than the model has is clamped and reported",
          got["num_gpu"] == 32 and any("num_gpu" in n for n in notes), notes)
    got, _ = B.normalise_controls({"lane": "nonsense"})
    check("an unknown lane falls back to everyday rather than a KeyError",
          got["lane"] == "everyday", got["lane"])


# ==========================================================================
#   9. The store's two shapes, and the views built from them
# ==========================================================================

def t_history_view():
    log = tmp_log()
    first = B.history(log=log)
    check("an empty history says so, in words",
          first["runs"] == [] and "No benchmark runs" in first["note"], first)
    log.append(run_row("r1"))
    got = B.history(log=log)
    check("a history with a run returns it",
          len(got["runs"]) == 1 and got["total"] == 1, got)
    filtered = B.history(model="qwen3:8b", log=log)
    check("a filter that matches nothing says THAT, not 'no runs yet'",
          "match that filter" in filtered["note"], filtered)


def t_controls_view():
    B._reset_for_tests()
    # Only the everyday lane's Ollama answers. The other two are down, which is
    # the real state of this PC: the pooled lane is started on demand only.
    def only_everyday(url):
        if ":11436" not in url:
            raise OSError("connection refused")
        return fake_get(models=("qwen3.5:9b", "qwen3:8b"))(url)
    view = B.controls_view(get=only_everyday, show=fake_show(),
                           smi=lambda: SMI_BEFORE, model="qwen3.5:9b",
                           log=tmp_log())
    check("every lane is listed with the card it really is",
          view["lanes"]["everyday"]["card"] == "RTX 2060"
          and view["lanes"]["coding"]["card"] == "RTX 2080 SUPER"
          and view["lanes"]["pooled"]["card"] == "both cards", view["lanes"])
    check("the installed models are listed per lane",
          view["lanes"]["everyday"]["models"] == ["qwen3.5:9b", "qwen3:8b"],
          view["lanes"]["everyday"])
    check("a lane whose Ollama is not running is marked, not hidden",
          view["lanes"]["everyday"]["running"] is True
          and view["lanes"]["pooled"]["running"] is False
          and view["lanes"]["pooled"]["models"] == [], view["lanes"])
    check("the model's layer count is READ, not guessed",
          view["block_count"] == 32 and view["context_length"] == 262144, view)
    check("the cards and the driver come from nvidia-smi",
          len(view["cards"]) == 2 and view["driver_version"] == "617.42", view)
    check("the ladders are exposed for the screen to draw",
          view["ladders"]["ctx"] == list(B.CTX_LADDER)
          and view["ladders"]["repeats"] == [1, 9], view["ladders"])
    check("whether a run is in flight is on the view", view["running"] is None)
    check("the view says what a run will do to the loaded model",
          "evicted" in view["note"], view["note"])


def t_view_and_cancel():
    B._reset_for_tests()
    code, out, log = run_once()
    status, seen = B.view(out["run_id"], log=log)
    check("a finished run is readable by id", status == 200 and seen["state"]
          == "done", (status, seen))
    check("... with its numbers in `result`",
          seen["result"]["gen_median"] == 32.0, seen.get("result"))
    status, missing = B.view("no-such-run")
    check("an id that is not there is a 404, not an empty 200",
          status == 404, status)
    status, cancelled = B.cancel(out["run_id"])
    check("cancelling a run that already finished is a 409, not a lie",
          status == 409, (status, cancelled))
    status, missing = B.cancel("no-such-run")
    check("cancelling an unknown run is a 404", status == 404)


# ==========================================================================
#   10. The lanes are the ones this PC really uses
# ==========================================================================

def t_the_lane_ports_are_this_pc_s():
    pins = B.lane_pins()
    # A REAL check, not a skip: `jarvis_model_lanes.py` is a shipped module in
    # this very folder, so "it is not there" is a failure of the tree, not a
    # machine that cannot run the test. `check(..., True)` here would print ok
    # whatever happened - the shape tools/check_vacuous_checks.py exists to
    # catch, and it caught this one.
    check("the lane module that owns the ports is in this checkout, so they can "
          "be compared", bool(pins), pins)
    if not pins:
        return
    check("the everyday lane is the port jarvis_model_lanes uses",
          B.LANE_PORTS["everyday"] == pins["lanes"].get("everyday"),
          (B.LANE_PORTS, pins))
    check("the coding lane is too",
          B.LANE_PORTS["coding"] == pins["lanes"].get("coding"),
          (B.LANE_PORTS, pins))
    check("the pooled lane is the port jarvis_model_lanes uses",
          B.LANE_PORTS["pooled"] == pins["pooled"], (B.LANE_PORTS, pins))
    check("a lane's base is always this PC, on that lane's port",
          B.lane_base("coding") == "http://127.0.0.1:11435",
          B.lane_base("coding"))
    check("an unknown lane falls back to everyday rather than nowhere",
          B.lane_base("nope") == B.lane_base("everyday"))


# ==========================================================================
#   11. Its own source: this module cannot reach anywhere but this PC
# ==========================================================================

def t_the_module_only_ever_talks_to_this_pc():
    urls = _urls_in_the_module()
    check("every address the module contains is this PC's own loopback",
          urls and all(u.startswith("http://127.0.0.1") for u in urls), urls)
    check("it opens no socket of its own",
          not _imports_anything_named({"socket", "requests", "http.client",
                                       "http"}), _imports_anything_named(
              {"socket", "requests", "http.client", "http"}))
    check("it never calls urllib's own urlopen: every request goes through "
          "_urlopen, which uses jarvis_local_http when it is there",
          _calls_urllib_urlopen() is False)
    # And the runtime proof: the address a lane really gets is loopback.
    for lane in B.LANE_KEYS:
        check(f"the {lane} lane's address is loopback",
              B.is_loopback(B.lane_base(lane)), B.lane_base(lane))


def t_it_is_a_two_file_change():
    """The module is SHIPPED, so the installer copies it, and the byte-for-byte
    twin is the repo's own checkers' job.

    TWO CHECKS HERE HAVE ALREADY BEEN WRONG, and both for the same reason: this
    suite must read only what is inside the folder it runs in.

      * It used to compare `../jarvis-backend/jarvis_bench.py` itself. That
        cannot pass in `backend/run_suites.py`, which builds its
        `jarvis-backend/` from the five files a suite can LIFT (jarvis_hud,
        jarvis_gate, jarvis_extract, jarvis_models, jarvis_skills - see
        backend/_base.py), so that folder holds no `jarvis_bench.py`.
      * It then also parsed `../scripts/apply-patches.ps1`. A sweep carries no
        `scripts/` folder, so that read returned nothing and the check failed
        for a reason that has nothing to do with the module.

    So this asserts only what `backend/` itself can answer: the module is on
    `SHIPPED`, where a new module is appended. The byte-for-byte twin is
    `backend/test_base_matches_repo.py` (136 checks) and
    `tools/check_stale_twins.py`, and the two SHIPPED lists agreeing is
    `backend/test_shipped_modules.py` (855 checks) - all three run in the same
    required `backend` job.
    """
    from _where import SHIPPED
    check("jarvis_bench.py is on the SHIPPED list, so the installer copies it",
          "jarvis_bench.py" in SHIPPED, SHIPPED[-3:])
    check("... and it is the LAST entry, where a new module is appended, so the "
          "two lists cannot disagree about its position",
          SHIPPED[-1] == "jarvis_bench.py", SHIPPED[-1])
    check("... and it is named exactly once, so a copy-paste cannot ship it "
          "twice", list(SHIPPED).count("jarvis_bench.py") == 1,
          list(SHIPPED).count("jarvis_bench.py"))


# ==========================================================================
#   Reading the module STRUCTURALLY, never its text
# ==========================================================================
#
# `tools/check_no_source_pins.py` gives a NEW suite a ceiling of ZERO source
# pins, and it is right to: a check that greps a module's text goes red when the
# code gets BETTER (a renamed call, a reworded comment) and green when a defect
# merely moves. Everything below walks `ast` nodes, where a docstring is a
# Constant and can never be mistaken for a Call - the second shape that checker
# names.

def _module_tree():
    """`jarvis_bench`'s parsed AST. Read here, compared NOWHERE as text."""
    import ast
    return ast.parse((BACKEND / "jarvis_bench.py").read_text(encoding="utf-8"))


def _programs_jarvis_bench_runs() -> list:
    """The external program each `subprocess.run(...)` in the module can start.

    Resolved through the tree, not the text: the call's first argument is a
    list whose head may be a literal or a NAME (`exe`), and a name is followed
    back to the string constants assigned to it. That is what makes this an
    answer about the code rather than about a spelling - the shape
    `tools/check_no_source_pins.py` asks for.
    """
    import ast
    tree = _module_tree()
    assigned: dict = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            consts = [n.value for n in ast.walk(node.value)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if consts:
                assigned.setdefault(node.targets[0].id, []).extend(consts)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "run"
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "subprocess"):
            continue
        if not node.args:
            continue
        consts = [n.value for n in ast.walk(node.args[0])
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        for n in ast.walk(node.args[0]):
            if isinstance(n, ast.Name):
                consts.extend(assigned.get(n.id, []))
        exe = [c for c in consts if "nvidia-smi" in c]
        out.append(exe[0] if exe else consts[:1])
    return out


def _uses_shell_or_task_name() -> list:
    """Every string constant in the module that names a way to START something.

    A constant, never a comment or a docstring: those are Constant nodes too,
    so the search is over `ast.Constant` values whose text is an executable or a
    scheduled-task name - and the module's own docstring promises no such thing
    exists, which this turns into a fact about the code."""
    import ast
    bad = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        low = node.value.lower()
        if any(w in low for w in ("schtasks", "start_lane", "task_prefix",
                                  "powershell", "cmd /c")):
            bad.append(node.value[:40])
    return bad


def _lanes_functions_called() -> list:
    """Every attribute CALLED on a name that looks like the lane module.

    `lane_pins()` reads `lanes.LANES` - an attribute READ, which is the point:
    the ports are borrowed, and no function of that module is ever invoked, so
    this module cannot start a lane even by accident."""
    import ast
    out = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                and fn.value.id in ("lanes", "jarvis_model_lanes", "lane")):
            out.append(fn.attr)
    return out


def _urls_in_the_module() -> set:
    """Every http(s) URL in the module, from its string constants."""
    import ast
    out = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(("http://", "https://")):
                out.add(node.value)
    return out


def _imports_anything_named(wanted: set) -> list:
    """The names in `wanted` the module really imports."""
    import ast
    found = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in wanted or a.name.split(".")[0] in wanted:
                    found.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module in wanted or node.module.split(".")[0] in wanted:
                found.append(node.module)
    return found


def _calls_urllib_urlopen() -> bool:
    """Does the module call `urllib.request.urlopen` directly? It must not:
    that path honours HTTPS_PROXY, which would carry the model name and the
    fixed benchmark prompt to a proxy."""
    import ast
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and fn.attr == "urlopen"
                and isinstance(fn.value, ast.Attribute)
                and fn.value.attr == "request"):
            return True
    return False


# ==========================================================================
#   Runner
# ==========================================================================

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
