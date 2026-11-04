"""jarvis_bench.py - measure how fast THIS PC runs one model in one setup.

WHAT IT IS FOR. The owner asked (2026-11-04) for Jarvis to measure its own
token speed across the local models, the RAM/GPU layer placement and the
context sizes, keep a separate history of those runs, and explain the results
in plain words. This module is phase 1: the measurement engine and its store.
The screens come later and none of them is needed to read a number.

ONE RUN = one model + one setup + N repeats + one target lane. A repeat asks
Ollama one question, reads Ollama's own counters out of the reply, samples the
two graphics cards, and writes ONE row. The run then writes a second row with
the setup and the median/min/max over its repeats.

WHY THIS IS A MODULE OF ITS OWN AND NOT PART OF jarvis_speed.py
    `jarvis_speed` times a CHAT ANSWER: how long the owner waited, how many
    words a second came back, a first-word time. Its file is a closed
    allowlist whose promise is that rows are never deleted or rewritten, and
    its summaries read every row in it. A benchmark row needs about thirty
    fields that mean nothing to those summaries, and the owner asked for a
    DELETE on a history row, which that file must never have. So the numbers
    live in their own file (`bench.jsonl`), with their own allowlist, and the
    existing chat-speed rows are untouched. `speed.jsonl` is never opened here.

THE PREFILL TRAP, WHICH IS THE REASON THIS DOCSTRING IS THIS LONG
    Ollama's `prompt_eval_duration` times only the prompt tokens it actually
    COMPUTED, while `prompt_eval_count` counts the WHOLE prompt including the
    part it read from its cache. Dividing one by the other inflates prompt
    speed by exactly the cache-hit ratio. Measured example (Ollama 0.34.0,
    qwen2.5:7b, RESEARCH.md section 3.1):

        318 prompt tokens, 317 of them cached, 23.00 ms of evaluation
        naive  318 / 0.023 = 13,826 tokens a second
        honest   1 / 0.023 =      43 tokens a second

    A 318x lie, from two numbers that are each individually correct. So
    prefill here is ALWAYS

        (prompt_eval_count - prompt_eval_cached_count) / prompt_eval_duration

    and:
      * when `cached == count` there is nothing left to time, and the row says
        "cached - prefill not measured". Never 0, never infinity.
      * when `prompt_eval_cached_count` is absent (Ollama before 0.33.3) the
        answer is "unknown", never 0 - absent is not zero.

    `jarvis_speed.timing_from_reply()` is deliberately NOT reused for this.
    Its `first_word_ms` is `load_duration + prompt_eval_duration`, i.e. the
    UNCACHED prefill time, which under-reports time-to-first-token whenever
    part of the prompt was cached. Both of this module's first-token numbers
    are stored instead, and the row says so when they disagree.

WHAT IT REFUSES, AND WHY EACH REFUSAL IS A SENTENCE AND NOT A SILENT NO
    every row of DESIGN.md section 2's table is in `check_job()` below, in the
    table's own order, with the status code it uses. A benchmark started while
    something else is using the model measures the QUEUE, not the model, so the
    run is refused rather than quietly wrong.

    NO APPROVAL CARD, and that is a decision with a precedent rather than a
    shortcut (DESIGN.md section 7): `POST /api/hardware/measure` already runs
    with no card because it "runs one short prompt per model on this PC and
    changes no setting", and here the owner is the actor. What a card would
    have bought is bought explicitly instead: the request must carry
    `confirm: {model, lane, may_evict: true}`.

NO NETWORK, NO MODEL AND NO CARD AT IMPORT TIME. Everything that talks to the
world is an injectable callable (`post`, `get`, `show`, `smi`, `clock`,
`spawn`), the same shape `jarvis_speed.measure(post=...)` and
`jarvis_hardware.request_measure(spawn=...)` already use. That is what lets
`backend/test_bench.py` prove every formula and every refusal with fake Ollama
replies and fake `nvidia-smi` text, on a machine with no graphics card and no
model loaded.

Standard library only. Every import of a shipped module beside it is wrapped,
so this file runs - with that part quietly missing - on a backend that does
not have one.
"""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import statistics
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Iterable, Optional

#: Bumped when a row's meaning changes, so an old row is never read as a new
#: one. Written into every row as `v`.
SCHEMA = 1

#: The history file. Deliberately NOT `speed.jsonl`: see the docstring above.
FILE_NAME = "bench.jsonl"

#: How many RUNS the history keeps. A run is 1 + `repeats` rows, so this is
#: about 2,000 rows, roughly 300 KB at ~150 B a row. The oldest run is dropped
#: on write, WHOLE: half a run is worse than no run, because its summary was
#: computed from numbers that are no longer there.
MAX_RUNS = 500

#: And a hard byte ceiling, whichever comes first. 2 MB is about six times the
#: row cap, so it only ever bites if a row grows unexpectedly - which is
#: exactly when a ceiling is worth having.
MAX_BYTES = 2 * 1024 * 1024

#: How long a machine reason may be. A stored reason, not a paragraph.
MAX_REASON = 200

#: And how long the one sentence a screen shows may be. Longer than a reason on
#: purpose: it is prose, and it is the only thing the owner reads.
MAX_WORDS = 500

# ==========================================================================
#   The controls: DESIGN.md section 3, as one plain dict
# ==========================================================================
#
# WHAT IS A SLIDER AND WHAT IS A CHOICE, and the rule behind it: a control is a
# continuous slider only when every value between the ends is a real,
# different, measurable configuration. Otherwise it is a slider that snaps, and
# the app says where it snapped. `num_gpu` is the only genuinely continuous
# one: every step is handed to llama.cpp as `-ngl N` and really changes the
# split. `num_ctx` snaps to a ladder because each distinct value costs a full
# model reload and nothing is learned between rungs.

#: Which Ollama serves which card. THE CARD IS CHOSEN BY WHICH SERVER, because
#: that is the only real per-card control this machine has: Ollama has no
#: per-GPU layer-ratio option, and `main_gpu` forces `--split-mode none`, i.e.
#: "all of it on this one card". These ports are pinned to
#: `jarvis_model_lanes.py` by backend/test_bench.py, so they cannot drift here
#: unnoticed.
LANE_PORTS = {"everyday": 11436, "coding": 11435, "pooled": 11450}

#: What the owner sees. Two lanes are pinned to one card each; the pooled lane
#: is pinned to neither, and saying "the 2060" for it would be a lie.
LANE_CARDS = {"everyday": "RTX 2060", "coding": "RTX 2080 SUPER",
              "pooled": "both cards"}

LANE_KEYS = ("everyday", "coding", "pooled")

#: The context ladder. Every rung is from this PC's own measurements: 16,384
#: zero-spill; 20,480/24,576/28,672 spilling 204-212 MiB; 32,768 spilling
#: 323.5 MiB (jarvis_model_lanes.py's POOLED comment and
#: docs/MEASURED-2026-11-02-POOLED-LANE.md). The last rung is the largest
#: context the local models are trained for.
CTX_LADDER = (2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768,
              49152, 65536, 98304, 131072, 196608)

#: Prompt depth. 512 is llama-bench's own default (`-p 512`), and prefill speed
#: is only comparable at the same depth.
PREFILL_CHOICES = (0, 512, 2048, 8192)

#: Generation length. 64 matches the existing `jarvis_speed.measure()`.
NUM_PREDICT_CHOICES = (32, 64, 128, 256)

#: `llama-bench` warms up by default and offers `--no-warmup`. A cold first
#: pass times the disk, not the model.
WARMUP_CHOICES = (0, 1, 2)

#: 3 is this repo's own minimum for a median (`jarvis_speed.MIN_EACH = 3`):
#: two lists of two can differ by 40% from noise alone.
REPEATS_MIN, REPEATS_MAX = 1, 9

#: How many runs a comparison needs before it is fair. The same floor
#: `jarvis_speed.compare_latency()` refuses under, kept here as its own
#: constant so the advice builder is provable on its own.
MIN_RUNS = 3

#: The defaults, as ONE plain dict - what a screen fills its controls with and
#: what `normalise_controls()` starts from. `everyday` is the default lane
#: because it is the card WITHOUT the monitor: measuring there does not
#: stutter the desktop.
CONTROLS = {
    # nothing is ever downloaded; a benchmark cannot pull a model
    "model": "",
    "lane": "everyday",
    # None means "all of them" - filled in from the model's `block_count`
    "num_gpu": None,
    "num_ctx": 16384,
    "prefill_tokens": 512,
    "num_predict": 64,
    "repeats": 3,
    "warmup": 1,
    # this PC runs OLLAMA_KEEP_ALIVE=-1, so without this the benchmark leaves
    # its model resident and the owner feels it on the next answer
    "unload": True,
}

# ==========================================================================
#   The sentences
# ==========================================================================
#
# DESIGN.md section 2's table, verbatim, one constant each so a test can assert
# the exact words rather than a prefix of them.

ANSWER_STREAMING = ("Jarvis is answering. Measuring now would time the queue, "
                    "not the model.")
ALREADY_RUNNING = "a benchmark is already running; it takes a minute or two"
STANDBY = ("Jarvis is on standby, which keeps the graphics card free; "
           "measuring would load a model onto it. Wake Jarvis first")
TASK_RUNNING = ("a task is running; it uses the model, so the benchmark would "
                "time the queue instead of the model")
LANE_DOWN = "the {lane} lane is not running; start it first"
MODEL_MISSING = "{model} is not installed on the {lane} lane. It has: {has}"
NOT_LOOPBACK = ("Nothing was measured: Ollama's address ({base}) is not this "
                "PC, and a benchmark only talks to this PC.")
NOT_CONFIRMED = "nothing was measured: the run was not confirmed"

#: When a reply arrives with no timings in it at all. Never a zero.
NO_TIMINGS = "Ollama answered, but without timing numbers"

#: The one honest way to say "there was nothing left to time".
CACHED_PREFILL = "cached - prefill not measured"

# ==========================================================================
#   The store
# ==========================================================================

#: The fields a row may carry, and nothing else. Same discipline as
#: `jarvis_speed._clean()`: an ALLOWLIST, not a filter, so a field a caller
#: invents - a prompt, an answer, a word the owner said - is DROPPED rather
#: than written and read back later. There is deliberately no field that could
#: hold text other than a model name, a lane name, and a short machine reason.
_NUMBER_FIELDS = {
    "v", "at",
    # the setup
    "ctx", "ctx_used", "num_gpu", "block_count", "ram_share_percent",
    "num_predict", "prefill_tokens", "repeat", "repeats", "warmup_passes",
    # the measurement
    "prefill_tokens_per_s", "prefill_uncached", "prefill_cached",
    "gen_tokens_per_s", "gen_tokens",
    "ttft_wall_ms", "ttft_ollama_ms", "load_ms", "total_ms", "ollama_total_ms",
    # the cards
    "vram_peak_mb_card0", "vram_peak_mb_card1", "vram_base_mb_card0",
    "vram_base_mb_card1", "gpu_util_peak", "ram_peak_mb",
    # what really loaded
    "on_card_percent", "offloaded_layers", "total_layers",
    # the aggregate over a run's repeats
    "prefill_median", "prefill_min", "prefill_max", "prefill_spread",
    "gen_median", "gen_min", "gen_max", "gen_spread",
    "ttft_wall_median", "ttft_ollama_median", "repeats_ok",
}

_BOOL_FIELDS = {"warmup", "ok", "spilled", "worst_repeat_ok", "unload"}

#: Text fields, each with its own cap. `why`/`prefill_why`/`ttft_note`/
#: `restore_note` are machine reasons; `words` is the one sentence a screen
#: shows; the two versions are what make two runs comparable at all.
_NAME_FIELDS = {
    "run": 60, "model": 120, "lane": 12, "card": 40,
    "why": MAX_REASON, "prefill_why": MAX_REASON, "ttft_note": MAX_REASON,
    "restore_note": MAX_REASON, "unload_note": MAX_REASON,
    "words": MAX_WORDS, "preset": 40,
    "ollama_version": 40, "driver_version": 40, "loaded_before": 160,
}

#: Small closed vocabularies. A value outside its list is dropped.
_ENUM_FIELDS = {"kind": ("bench", "bench-run"),
                "lane": LANE_KEYS}


def _clean(row: dict) -> dict:
    """Keep only the allowed fields, only in the allowed shapes.

    The allowlist IS the privacy guarantee: `{"prompt": "..."}` handed in by a
    caller that made a mistake is dropped here, not written and read back
    later. Booleans are refused in number fields (Python says `True == 1`) and
    a nan or an infinity is dropped, because either one would poison a median.
    """
    out: dict = {}
    for k, v in (row or {}).items():
        if k in _NUMBER_FIELDS:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if isinstance(v, float) and (v != v or v in (float("inf"),
                                                         float("-inf"))):
                continue
            out[k] = round(float(v), 2) if isinstance(v, float) else v
        elif k in _BOOL_FIELDS:
            if isinstance(v, bool):
                out[k] = v
        elif k in _NAME_FIELDS:
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()[:_NAME_FIELDS[k]]
        elif k in _ENUM_FIELDS:
            if isinstance(v, str) and v in _ENUM_FIELDS[k]:
                out[k] = v
    return out


def _median(xs: Iterable) -> Optional[float]:
    """The middle reading, or None. `jarvis_speed._median` when that module is
    there, so the two files round the same way."""
    try:
        import jarvis_speed  # type: ignore
        return jarvis_speed._median(xs)
    except Exception:
        pass
    vals = [x for x in xs if isinstance(x, (int, float))
            and not isinstance(x, bool)]
    if not vals:
        return None
    return round(float(statistics.median(vals)), 1)


def _config_dir() -> Path:
    """Same rule as `jarvis_speed._config_dir()`: the real framework's
    CONFIG_DIR if importable, OPENJARVIS_CONFIG_DIR if set, otherwise
    ~/.openjarvis. Borrowed rather than re-implemented when it is there, so the
    two files can never end up in different folders."""
    try:
        import jarvis_speed  # type: ignore
        return Path(jarvis_speed._config_dir())
    except Exception:
        pass
    try:
        import jarvis_framework as fw  # type: ignore
        if getattr(fw, "CONFIG_DIR", None):
            return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def default_path() -> Path:
    """`~/.openjarvis/bench.jsonl`, beside everything else Jarvis keeps."""
    return _config_dir() / FILE_NAME


class BenchLog:
    """Append-only JSON lines, with a run ring cap and a byte cap.

    Never raises: a history that can break a run is worse than no history.

    DELETING IS A REWRITE, and that is safe HERE and nowhere near
    `speed.jsonl`: this file is a history view the owner asked to be able to
    clear, not evidence. `jarvis_speed`'s own promise - rows are never deleted
    or rewritten - stays exactly as it is.
    """

    _lock = threading.Lock()

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    # -- writing ---------------------------------------------------------
    def append(self, row: dict) -> bool:
        """One row. False if the row names no `kind`, or the disk refused."""
        clean = _clean(row)
        if "kind" not in clean:
            return False
        clean["v"] = SCHEMA
        clean.setdefault("at", int(time.time()))
        line = json.dumps(clean, separators=(",", ":"), sort_keys=True) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
        except OSError:
            return False
        self.trim()
        return True

    def append_run(self, run_row: dict, repeat_rows: list) -> bool:
        """Every row of one run. The run row goes LAST on purpose: a reader
        never sees a run whose repeats have not been written yet, so a
        half-written run reads as "not there" rather than as a run with
        missing numbers."""
        ok = True
        for r in repeat_rows or ():
            ok = self.append(r) and ok
        return self.append(run_row) and ok

    # -- reading ---------------------------------------------------------
    def rows(self, max_bytes: Optional[int] = None) -> list:
        """Every readable row, oldest first. A damaged line is skipped, not
        fatal - the same rule `SpeedLog.tail()` follows.

        `max_bytes` reads only the tail; None reads the whole file, which is
        what trimming needs and what a 500-run file can afford."""
        try:
            with open(self.path, "rb") as f:
                if max_bytes is None:
                    raw = f.read()
                else:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - max_bytes))
                    raw = f.read()
        except OSError:
            return []
        lines = raw.split(b"\n")
        if max_bytes is not None and len(raw) >= max_bytes:
            lines = lines[1:]          # the first line is probably cut in half
        out = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(_clean(r))
        return out

    def tail(self, n: int = 200, kind: Optional[str] = None) -> list:
        rows = [r for r in self.rows() if kind is None or r.get("kind") == kind]
        return rows[-n:] if n and n > 0 else rows

    def runs(self, *, limit: int = 20, model: str = "", lane: str = "",
             preset: str = "") -> list:
        """The run rows, newest first, optionally filtered.

        A filter is an EXACT match on the stored name. A fuzzy match here would
        let a screen say "qwen3.5:9b" and mean "qwen3.5:4b", which is the one
        mistake a benchmark history must never make.
        """
        out = [r for r in self.rows() if r.get("kind") == "bench-run"]
        if model:
            out = [r for r in out if r.get("model") == model]
        if lane:
            out = [r for r in out if r.get("lane") == lane]
        if preset:
            out = [r for r in out if r.get("preset") == preset]
        out.reverse()
        return out[:limit] if limit and limit > 0 else out

    def get(self, run_id: str) -> Optional[dict]:
        """One run and its repeats, or None."""
        if not run_id:
            return None
        run = None
        repeats = []
        for r in self.rows():
            if r.get("run") != run_id:
                continue
            if r.get("kind") == "bench-run":
                run = r
            elif r.get("kind") == "bench":
                repeats.append(r)
        if run is None:
            return None
        repeats.sort(key=lambda r: (bool(r.get("warmup")), r.get("repeat") or 0))
        return {"run": run, "repeats": repeats}

    def count_runs(self) -> int:
        return len({r.get("run") for r in self.rows()
                    if r.get("kind") == "bench-run"})

    # -- trimming and deleting -------------------------------------------
    def trim(self) -> int:
        """Keep the newest `MAX_RUNS` runs whole, and the whole file under
        `MAX_BYTES`. Returns how many ROWS were dropped (0 almost always).

        Whole runs only. Dropping a run's repeat rows but keeping its summary
        would leave a row whose aggregate was computed from numbers that are no
        longer on disk - exactly the kind of quiet lie this feature exists to
        avoid.
        """
        rows = self.rows()
        if not rows:
            return 0
        order: list = []
        seen: set = set()
        for r in rows:
            rid = r.get("run") or ""
            if rid not in seen:
                seen.add(rid)
                order.append(rid)
        over_runs = len(order) > MAX_RUNS
        over_bytes = self._bytes_of(rows) > MAX_BYTES
        if not over_runs and not over_bytes:
            return 0
        keep = list(order[-MAX_RUNS:]) if over_runs else list(order)
        kept = [r for r in rows if (r.get("run") or "") in set(keep)]
        # Then the byte ceiling: drop from the OLDEST end, one run at a time.
        while self._bytes_of(kept) > MAX_BYTES and len(keep) > 1:
            keep.pop(0)
            kept = [r for r in rows if (r.get("run") or "") in set(keep)]
        try:
            with self._lock:
                self._write(kept)
        except OSError:
            return 0
        return len(rows) - len(kept)

    def delete(self, run_id: str) -> int:
        """Take ONE run off the disk, repeats and all. Returns the rows
        removed (0 when the id is not there). A rewrite, deliberately."""
        if not run_id:
            return 0
        rows = self.rows()
        kept = [r for r in rows if r.get("run") != run_id]
        if len(kept) == len(rows):
            return 0
        try:
            with self._lock:
                self._write(kept)
        except OSError:
            return 0
        return len(rows) - len(kept)

    # -- internals -------------------------------------------------------
    @staticmethod
    def _bytes_of(rows: list) -> int:
        return sum(len(json.dumps(r, separators=(",", ":"),
                                  sort_keys=True)) + 1 for r in rows)

    def _write(self, rows: list) -> None:
        text = "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n"
                       for r in rows)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)


# ==========================================================================
#   The formulas: DESIGN.md section 4
# ==========================================================================
#
# Every one of these is a pure function of numbers Ollama (or nvidia-smi)
# reported. None of them touches a file, a socket or a card, so every one is
# provable with a literal in a test - which is the point: the prefill trap is
# an arithmetic mistake, and arithmetic is testable.

def _int(value) -> Optional[int]:
    """An int, or None. `True` is not an int here, and neither is `"318"`."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def prefill_rate(count, cached, duration_ns) -> tuple:
    """(tokens per second, why) for the part of the prompt Ollama REALLY read.

    THE ONLY CORRECT FORMULA IS `(count - cached) / duration`. Dividing `count`
    by `duration` inflates prompt speed by the cache-hit ratio - 318x in the
    measured example this module's docstring quotes.

    Returns (None, a reason) rather than a number in every case where the
    honest answer is "not measured":
      * `count` missing or not positive -> "no prompt_eval_count"
      * `cached` MISSING (not 0) -> the cached count is not reported.
        ABSENT IS NOT ZERO: defaulting it to 0 turns "I do not know" into a
        confident, too-high number, and `prompt_eval_cached_count` is absent
        before Ollama 0.33.3.
      * `duration` missing or not positive -> "no prompt_eval_duration"
      * `cached >= count` -> CACHED_PREFILL: the whole prompt came from the
        cache and there is nothing left to time. Never 0 (which reads as
        "terribly slow") and never infinity (which reads as a broken screen).
    """
    n = _int(count)
    if n is None or n <= 0:
        return None, "no prompt_eval_count"
    if cached is None:
        return None, ("the cached count is not reported, so the uncached "
                      "prefill is unknown")
    c = _int(cached)
    if c is None:
        return None, ("the cached count is not a number, so the uncached "
                      "prefill is unknown")
    d = _int(duration_ns)
    if d is None or d <= 0:
        return None, "no prompt_eval_duration"
    uncached = n - c
    if uncached <= 0:
        return None, CACHED_PREFILL
    return round(uncached / (d / 1e9), 2), ""


def generation_rate(count, duration_ns) -> Optional[float]:
    """`eval_count / eval_duration`, the same formula
    `jarvis_speed.timing_from_reply()` already uses. None when either is
    missing or not positive - a rate from no tokens is not 0, it is unknown."""
    n, d = _int(count), _int(duration_ns)
    if n is None or n <= 0 or d is None or d <= 0:
        return None
    return round(n / (d / 1e9), 2)


#: How far the two time-to-first-token numbers may differ before the row says
#: so out loud. 15%, from DESIGN.md section 4.
TTFT_TOLERANCE = 0.15


def ttft_note(wall_ms, ollama_ms) -> str:
    """The sentence a row carries when the two first-token numbers disagree by
    more than `TTFT_TOLERANCE`. "" when they agree, or when one is missing.

    They legitimately disagree. The wall clock is the whole round trip the
    owner waited - queue, tokenise, load, prefill. Ollama's figure is its own
    `load_duration + prompt_eval_duration`. The wall clock is the one he
    EXPERIENCES, so it is the one a screen leads with, and this note stops the
    other being read as a contradiction.
    """
    try:
        w, o = float(wall_ms), float(ollama_ms)
    except (TypeError, ValueError):
        return ""
    if w <= 0 or o <= 0:
        return ""
    if abs(w - o) / max(w, o) <= TTFT_TOLERANCE:
        return ""
    return (f"first token: {w:.0f} ms waited, {o:.0f} ms on Ollama's own "
            "clock - the prompt was partly cached, or the request queued")


def timings(reply: dict) -> dict:
    """Everything DESIGN.md section 4 reports, out of ONE Ollama reply.

    Ollama's durations are nanoseconds. Every key is always present, so a
    caller never has to guess which of them a reply happened to carry; the ones
    the reply did not report are None and `prefill_why`/`why` say why in one
    short machine reason ("" when the thing WAS measured).

    NOT `jarvis_speed.timing_from_reply()`: that function's `first_word_ms` is
    `load_duration + prompt_eval_duration`, i.e. the uncached prefill time,
    which is not the time the owner waited. Both numbers are kept here instead.
    """
    out = {
        "prefill_tokens_per_s": None, "prefill_uncached": None,
        "prefill_cached": None, "prefill_why": "",
        "gen_tokens_per_s": None, "gen_tokens": None,
        "ttft_wall_ms": None, "ttft_ollama_ms": None, "load_ms": None,
        "total_ms": None, "ollama_total_ms": None, "ttft_note": "",
        "ok": False, "why": "",
    }
    if not isinstance(reply, dict):
        out["why"] = NO_TIMINGS
        return out
    count = _int(reply.get("prompt_eval_count"))
    cached = _int(reply.get("prompt_eval_cached_count"))
    pdur = _int(reply.get("prompt_eval_duration"))
    rate, why = prefill_rate(count, cached, pdur)
    out["prefill_tokens_per_s"] = rate
    out["prefill_why"] = why
    if rate is not None:
        out["prefill_uncached"] = count - cached
        out["prefill_cached"] = cached
    elif cached is not None and count is not None and cached >= count > 0:
        # The counts ARE known: the whole prompt was cached. Stored, because
        # the next reader has to be able to tell that apart from "no numbers".
        out["prefill_uncached"] = 0
        out["prefill_cached"] = cached
    g = generation_rate(reply.get("eval_count"), reply.get("eval_duration"))
    out["gen_tokens_per_s"] = g
    if g is not None:
        out["gen_tokens"] = _int(reply.get("eval_count"))
    ld = _int(reply.get("load_duration")) or 0
    out["load_ms"] = int(round(ld / 1e6))
    if pdur is not None:
        out["ttft_ollama_ms"] = int(round((ld + pdur) / 1e6))
    td = _int(reply.get("total_duration"))
    if td is not None:
        out["ollama_total_ms"] = int(round(td / 1e6))
    out["ok"] = bool(g is not None)
    if not out["ok"]:
        out["why"] = NO_TIMINGS
    return out


def _spread(values: list, prefix: str) -> dict:
    """`{prefix_median/min/max/spread}` from the usable numbers, or all None."""
    vals = [float(v) for v in values if isinstance(v, (int, float))
            and not isinstance(v, bool)]
    if not vals:
        return {f"{prefix}_median": None, f"{prefix}_min": None,
                f"{prefix}_max": None, f"{prefix}_spread": None}
    return {
        f"{prefix}_median": round(float(statistics.median(vals)), 2),
        f"{prefix}_min": round(min(vals), 2),
        f"{prefix}_max": round(max(vals), 2),
        f"{prefix}_spread": round(max(vals) - min(vals), 2),
    }


def summarise(rows: list, *, warmup: int = 0) -> dict:
    """Median, min, max and spread over one run's repeats - warmup dropped.

    MEDIAN, NOT MEAN: one thermal stall or one eviction drags a mean anywhere,
    and a median is what the owner's own screens already show. The spread is
    reported rather than hidden, because a wide spread means "these numbers are
    noisy", which is a fact about the measurement he has to be able to see.

    Only rows with `ok: true` and not a warmup count. A repeat that failed is
    reported through `repeats_ok` and `worst_repeat_ok` instead of pulling a
    median down to nothing.
    """
    usable = [r for r in (rows or []) if r.get("ok") and not r.get("warmup")]
    gen = [r.get("gen_tokens_per_s") for r in usable
           if isinstance(r.get("gen_tokens_per_s"), (int, float))]
    pre = [r.get("prefill_tokens_per_s") for r in usable
           if isinstance(r.get("prefill_tokens_per_s"), (int, float))]
    out: dict = {"repeats_ok": len(usable), "worst_repeat_ok": bool(usable)}
    out.update(_spread(gen, "gen"))
    out.update(_spread(pre, "prefill"))
    out["ttft_wall_median"] = _median(r.get("ttft_wall_ms") for r in usable)
    out["ttft_ollama_median"] = _median(r.get("ttft_ollama_ms") for r in usable)
    # The WARM figure: `steady_state(drop=n)` is jarvis_speed's own answer to
    # "which readings are the model settling in", so the warm number is that
    # module's arithmetic rather than a second opinion about it.
    out["gen_warm"] = _steady_state(gen, drop=max(1, int(warmup or 1)))
    return out


def _steady_state(values: list, *, drop: int = 2) -> Optional[float]:
    """`jarvis_speed.steady_state` when it is there, else the same arithmetic."""
    try:
        import jarvis_speed  # type: ignore
        return jarvis_speed.steady_state(values, drop=drop)
    except Exception:
        pass
    vals = [float(v) for v in values or ()
            if isinstance(v, (int, float)) and not isinstance(v, bool)]
    vals = vals[max(0, int(drop or 0)):]
    if not vals:
        return None
    return round(float(statistics.fmean(vals)), 1)


def ram_share_percent(num_gpu, block_count) -> Optional[int]:
    """The share of layers OFF the card, as a percentage.

    This is the honest number behind DESIGN.md section 3's "system-RAM share"
    slider, and it is NOT a RAM reservation: it is the same `num_gpu` axis seen
    from the other side. Two independent controls would let the owner set a
    contradictory state, which is why the screens move this one when `num_gpu`
    moves and never the other way round.
    """
    n, b = _int(num_gpu), _int(block_count)
    if n is None or b is None or b <= 0:
        return None
    n = max(0, min(n, b))
    return int(round(100 - (n * 100.0 / b)))


def ram_share_for(controls: dict, block_count) -> Optional[int]:
    """The derived "system-RAM share" for a set of controls."""
    return ram_share_percent((controls or {}).get("num_gpu"), block_count)


def spilled(on_card_percent, offloaded, total) -> bool:
    """Was any of the model off the card?

    Two independent sources, and EITHER one saying so is enough: `/api/ps`
    `size` vs `size_vram` (the only spill measurement available over HTTP) and
    `offloaded N/M layers to GPU` from Ollama's own log. DESIGN.md section 13:
    "a spilled run is labelled, never presented as fast", so this is
    deliberately eager to say yes.
    """
    pct = on_card_percent
    if isinstance(pct, (int, float)) and not isinstance(pct, bool) and pct < 100:
        return True
    o, t = _int(offloaded), _int(total)
    return bool(o is not None and t is not None and o < t)


# ==========================================================================
#   Reading the cards
# ==========================================================================

#: The columns `_smi_text()` asks nvidia-smi for, in this order. `display_active`
#: matters: it is how the run knows the coding lane's card is the one holding
#: the monitor, which is a cost the pre-flight has to name. `driver_version`
#: goes on every row because a tok/s number without it is not comparable to
#: anything - it moved once already on this PC (616.56 -> 617.42).
SMI_FIELDS = ("index", "uuid", "name", "memory.total", "memory.used",
              "memory.free", "utilization.gpu", "display_active",
              "driver_version")


def _num(text) -> Optional[float]:
    """A number, or None. `[N/A]`, `[Not Supported]` and "" are None - the
    three shapes this PC's driver really answers with - and never 0."""
    try:
        v = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def cards_from_smi(text: str) -> dict:
    """`nvidia-smi --query-gpu=...` output -> {"cards": [...], "driver": str}.

    A PURE PARSER, so a test proves it against the exact text this PC's driver
    prints. Fields are read by POSITION, in the order `SMI_FIELDS` asks for
    them, because that is what `--format=csv,noheader,nounits` produces.

    `memory.used` PER PROCESS is `[N/A]` on driver 617.42 (RESEARCH.md
    section 1), so this is the only VRAM reading there is: per CARD, at a
    moment in time. "How much VRAM did this model take" is therefore never
    claimed - only "card 0 rose by X MB while this ran".
    """
    cards, driver = [], ""
    for line in str(text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(SMI_FIELDS):
            continue
        idx = _num(parts[SMI_FIELDS.index("index")])
        if idx is None:
            continue
        cards.append({
            "index": int(idx),
            "uuid": parts[SMI_FIELDS.index("uuid")],
            "name": parts[SMI_FIELDS.index("name")],
            "total_mb": _num(parts[SMI_FIELDS.index("memory.total")]),
            "used_mb": _num(parts[SMI_FIELDS.index("memory.used")]),
            "free_mb": _num(parts[SMI_FIELDS.index("memory.free")]),
            "util_percent": _num(parts[SMI_FIELDS.index("utilization.gpu")]),
            "display_active": parts[SMI_FIELDS.index("display_active")],
        })
        # The driver repeats on every row and is the same on all of them, so
        # taking the last is not a choice between two answers.
        driver = parts[SMI_FIELDS.index("driver_version")] or driver
    cards.sort(key=lambda c: c["index"])
    return {"cards": cards, "driver": driver}


def smi_text() -> str:
    """One `nvidia-smi` query. "" when the tool is missing or refuses.

    ONE process for one call, which is why a run samples before, after every
    repeat, and at the end - rather than on a timer that would leave a process
    running for the whole benchmark.
    """
    exe = shutil.which("nvidia-smi") or "nvidia-smi"
    try:
        r = subprocess.run([exe, "--query-gpu=" + ",".join(SMI_FIELDS),
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout or ""


def read_cards(smi: Optional[Callable[[], str]] = None) -> dict:
    """{"cards": [...], "driver": str} - empty when the cards cannot be read.

    Never raises: a benchmark that dies because nvidia-smi hiccuped once is
    worse than a benchmark with one missing VRAM number.
    """
    try:
        return cards_from_smi((smi or smi_text)() or "")
    except Exception:
        return {"cards": [], "driver": ""}


def card_mb(cards, index: int, key: str = "used_mb") -> Optional[int]:
    """One card's number, or None - and None when the card is not there, which
    is a different fact from "the card reported nothing"."""
    for c in cards or ():
        if _int(c.get("index")) == index:
            v = c.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(round(v))
            return None
    return None


def util_peak(cards) -> Optional[int]:
    """The highest `utilization.gpu` seen on any card, as a percentage.

    Also the evidence for "was the card busy before we started": a run that
    begins at 90% is not measuring the model's ceiling.
    """
    vals = [c.get("util_percent") for c in cards or ()
            if isinstance(c.get("util_percent"), (int, float))
            and not isinstance(c.get("util_percent"), bool)]
    return int(round(max(vals))) if vals else None


def peak_cards(samples: list) -> list:
    """The card list with every card's `used_mb` raised to the highest value
    ever sampled. One entry per card index, in index order.

    `samples` is a list of card lists (before, after each repeat, after). This
    is the "peak" half of "before, ~4x during, after": a model that loads,
    fills, and then relaxes is measured at its fullest.
    """
    seen: dict = {}
    for batch in samples or ():
        for c in batch or ():
            idx = _int(c.get("index"))
            if idx is None:
                continue
            cur = seen.get(idx)
            if cur is None:
                seen[idx] = dict(c)
                continue
            used = c.get("used_mb")
            if (isinstance(used, (int, float)) and not isinstance(used, bool)
                    and used > (cur.get("used_mb") or 0)):
                cur["used_mb"] = used
            util = c.get("util_percent")
            if (isinstance(util, (int, float)) and not isinstance(util, bool)
                    and util > (cur.get("util_percent") or 0)):
                cur["util_percent"] = util
    return [seen[k] for k in sorted(seen)]


# ==========================================================================
#   Talking to Ollama
# ==========================================================================

def lane_base(lane: str) -> str:
    """`http://127.0.0.1:<port>` for a lane. Loopback, always: a benchmark on
    another PC's Ollama would be measuring that PC."""
    port = LANE_PORTS.get(str(lane or "").strip().lower(),
                          LANE_PORTS["everyday"])
    return f"http://127.0.0.1:{port}"


def is_loopback(url: str) -> bool:
    """Same rule as `jarvis_speed.is_loopback()` - borrowed when that module is
    there, so the two can never disagree about what "this PC" means."""
    try:
        import jarvis_speed  # type: ignore
        return bool(jarvis_speed.is_loopback(url))
    except Exception:
        pass
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _urlopen(req, timeout: float):
    """Never through a proxy: a set HTTPS_PROXY would otherwise carry the model
    name and the fixed benchmark prompt to the proxy (the same CONN-1 rule
    `jarvis_speed._urlopen` follows). `jarvis_local_http` when it is there."""
    try:
        import jarvis_local_http  # type: ignore
        return jarvis_local_http.urlopen(req, timeout)
    except ImportError:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({})).open(req, timeout=timeout)


def http_get(url: str, timeout: float = 4.0) -> dict:
    """One JSON GET from this PC's own Ollama."""
    req = urllib.request.Request(url, method="GET")
    with _urlopen(req, timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_post_json(url: str, payload: dict, timeout: float = 8.0) -> dict:
    """One JSON POST that answers once, whole. `/api/show` is the only user:
    a GET on it is the wrong verb, and Ollama answers 405."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with _urlopen(req, timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def post_stream(url: str, payload: dict, *,
                clock: Callable[[], float] = None,
                timeout: float = 300.0) -> tuple:
    """POST one generation request, return `(seconds to the first token, reply)`.

    STREAMING ON PURPOSE, and this is the only reason: DESIGN.md section 4
    reports TWO time-to-first-token numbers, and the one the owner experiences
    is the harness's own wall clock from POST to the first chunk carrying text.
    A `stream: false` request cannot report it - it only finds out the answer
    arrived once the whole answer has.

    `reply` is the final NDJSON object (the one with `done: true`), which is
    where Ollama puts its own counters. NOTHING BUT THOSE COUNTERS IS KEPT: the
    generated text is discarded here and is never stored anywhere.
    """
    clock = clock or time.monotonic
    started = clock()
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    first = None
    final: dict = {}
    with _urlopen(req, timeout) as r:
        for raw in r:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            final = obj
            if first is None and (obj.get("response") or obj.get("message")):
                first = clock() - started
            if obj.get("done"):
                break
    return (first if first is not None else clock() - started), final


def ollama_version(base: str, *,
                   get: Optional[Callable[[str], dict]] = None
                   ) -> Optional[str]:
    """Ollama's own version. Stored on every row: a tok/s number without it is
    not comparable to anything, and this PC's Ollama has moved version before."""
    try:
        body = (get or http_get)(f"{base}/api/version")
    except Exception:
        return None
    v = body.get("version") if isinstance(body, dict) else None
    return str(v)[:40] if v else None


def installed_models(base: str, *, get: Optional[Callable[[str], dict]] = None
                     ) -> Optional[set]:
    """`/api/tags`: what is installed on THAT lane. None when it will not
    answer - which is a different fact from "nothing is installed", and the
    refusal that uses this says which one it means."""
    try:
        body = (get or http_get)(f"{base}/api/tags")
    except Exception:
        return None
    names = set()
    for m in (body or {}).get("models") or []:
        for k in ("name", "model"):
            if isinstance(m.get(k), str):
                names.add(m[k])
    return names


def _shape_of(body) -> dict:
    """`block_count` and the trained `context_length`, from an `/api/show` body.

    READ, NOT GUESSED, and found by SUFFIX: `model_info` is keyed
    `<arch>.block_count` and the arch varies by family (qwen35, qwen3,
    qwen3moe, gemma4), so a table of names here would go stale and a wrong
    prefix would silently return None forever.
    """
    out = {"block_count": None, "context_length": None}
    if not isinstance(body, dict):
        return out
    info = body.get("model_info") or {}
    if not isinstance(info, dict):
        return out
    for k, v in info.items():
        if not isinstance(k, str):
            continue
        if k.endswith(".block_count") and _int(v) and not out["block_count"]:
            out["block_count"] = _int(v)
        elif k.endswith(".context_length") and _int(v) and not out["context_length"]:
            out["context_length"] = _int(v)
    return out


def model_shape(base: str, model: str, *,
                show: Optional[Callable[[str, dict], dict]] = None) -> dict:
    """`/api/show` for ONE model: its layer count and its trained context.

    `/api/show` is a POST in Ollama's API, so it gets its own seam rather than
    being dressed up as a GET. None of it is fatal: a model whose shape cannot
    be read still measures, and the row says the layer count is unknown.
    """
    if not model:
        return {"block_count": None, "context_length": None}
    try:
        body = (show or http_post_json)(f"{base}/api/show", {"model": model})
    except Exception:
        return {"block_count": None, "context_length": None}
    return _shape_of(body)


def ps_models(base: str, *, get: Optional[Callable[[str], dict]] = None
              ) -> Optional[list]:
    """`/api/ps`: what is loaded right now, with `size` vs `size_vram` and the
    `context_length` really in use. Loads nothing."""
    try:
        body = (get or http_get)(f"{base}/api/ps")
    except Exception:
        return None
    return [m for m in (body or {}).get("models") or [] if isinstance(m, dict)]


def _same(a: str, b: str) -> bool:
    strip = lambda s: s[:-7] if s.endswith(":latest") else s  # noqa: E731
    return bool(a and b) and strip(a.strip()) == strip(b.strip())


def on_card_percent(model: str, loaded: Optional[list]) -> Optional[int]:
    """`size_vram / size` for ONE loaded model, as a percentage.

    This is the ONLY spill measurement available over HTTP (`/api/ps`), and it
    is kept as a percentage rather than a byte count because the bytes move as
    the context fills. 100 means "all of it in video memory"."""
    for m in loaded or ():
        if not _same(str(m.get("name") or m.get("model") or ""), model):
            continue
        size, vram = m.get("size"), m.get("size_vram")
        if (isinstance(size, (int, float)) and not isinstance(size, bool)
                and size > 0 and isinstance(vram, (int, float))
                and not isinstance(vram, bool)):
            return int(min(100, round(vram * 100 / size)))
    return None


def context_used(model: str, loaded: Optional[list],
                 shape: Optional[dict] = None) -> Optional[int]:
    """The context length the model is REALLY running at, from `/api/ps`.

    Which is not always what was asked for - it is whatever Ollama chose - so
    the row records it, and a number is never attributed to a context that was
    not in force. Falls back to the TRAINED length only when `/api/ps` says
    nothing, and that fallback is the trained length, not a guess at the loaded
    one.
    """
    for m in loaded or ():
        if _same(str(m.get("name") or m.get("model") or ""), model):
            v = _int(m.get("context_length"))
            if v:
                return v
    return _int((shape or {}).get("context_length")) or None


def offloaded_layers(*, log_text: Optional[Callable[[], str]] = None,
                     text: Optional[str] = None) -> list:
    """`offloaded N/M layers to GPU` from Ollama's own log, as [N, M] - or [].

    THE PARSER IS NOT RE-IMPLEMENTED HERE. `jarvis_hardware.parse_ollama_log`
    already reads exactly this line (and the flash-attention note beside it)
    out of the log, and a second parser would be a second thing to drift. This
    is a thin, guarded wrapper: no log, no hardware module, or a log with no
    such line all give [] - never a made-up ratio.
    """
    if text is None:
        if log_text is None:
            return []
        try:
            text = log_text() or ""
        except Exception:
            return []
    if not text:
        return []
    try:
        import jarvis_hardware  # type: ignore
        parsed = jarvis_hardware.parse_ollama_log(text)
    except Exception:
        return []
    got = parsed.get("offloaded") if isinstance(parsed, dict) else None
    if isinstance(got, (list, tuple)) and len(got) == 2:
        return [_int(got[0]) or 0, _int(got[1]) or 0]
    return []


# ==========================================================================
#   The prompt, which is counted and never kept
# ==========================================================================
#
# A FRESH PROMPT FOR EVERY REPEAT (RESEARCH.md section 6, rule 4). If one
# prompt were reused, every repeat after the first would hit Ollama's cache and
# look 300x faster - the exact trap this file exists to avoid. So each prompt
# carries its own tag, and it is generated from a fixed word list with no owner
# text in it. It is never stored: what is stored is how many tokens Ollama said
# it really counted.

#: Neutral, countable words. Nothing about the owner, nothing from a
#: conversation, nothing that could be a secret by accident.
_WORDS = ("quiet river stone window candle forest pocket silver morning "
          "garden ladder copper meadow thimble yellow anchor bridge canvas "
          "distant feather gravel harbour island jacket kettle lantern "
          "marble needle orchard pebble quill ribbon saddle timber").split()


def prefill_prompt(depth: int, tag: str = "") -> str:
    """A prompt of about `depth` word-units, unique for `tag`.

    ABOUT, deliberately. This module cannot know how llama.cpp's tokeniser will
    split a word, so the depth it ASKS for is stored separately from
    `prompt_eval_count`, which is what Ollama really counted. Claiming to hit
    an exact token count would be claiming a measurement this file did not
    make.
    """
    n = max(0, int(depth or 0))
    if n <= 0:
        return "Reply with one short sentence about a thermometer."
    out = [_WORDS[i % len(_WORDS)] for i in range(n)]
    # The tail is what makes this prompt different from every other one, and it
    # is counted too, so the depth stays as asked.
    return " ".join(out) + f"\n\n[{tag}]. Reply with one short sentence."


# ==========================================================================
#   Controls: what was asked for, cleaned up
# ==========================================================================

def normalise_controls(raw: dict, *, block_count=None,
                       context_length=None) -> tuple:
    """(the controls that will really be used, [what was changed and why]).

    Every value is clamped to something this PC can actually do, and EVERY
    clamp is reported. A control that silently snaps is a control that lies:
    the screen has to be able to say "16,384 was the nearest rung" instead of
    showing 20,000 and measuring 16,384.
    """
    raw = raw if isinstance(raw, dict) else {}
    notes: list = []
    out = dict(CONTROLS)

    model = str(raw.get("model") or "").strip()
    if model:
        out["model"] = model[:120]

    lane = str(raw.get("lane") or out["lane"]).strip().lower()
    if lane not in LANE_KEYS:
        notes.append(f"lane {lane!r} is not one of {', '.join(LANE_KEYS)}: "
                     "using everyday")
        lane = "everyday"
    out["lane"] = lane

    # -- num_gpu: the one genuinely continuous control -------------------
    want = raw.get("num_gpu", out["num_gpu"])
    if want is None:
        want = block_count
    n = _int(want)
    if n is None:
        n = _int(block_count)
    if n is not None:
        if block_count and n > block_count:
            notes.append(f"num_gpu {n} is more layers than the model has "
                         f"({block_count}): using {block_count}")
            n = block_count
        if n < 0:
            notes.append("num_gpu cannot be negative: using 0 (processor only)")
            n = 0
    out["num_gpu"] = n

    # -- num_ctx: a slider that snaps to a measured ladder ---------------
    ctx = _int(raw.get("num_ctx")) or out["num_ctx"]
    capped = [c for c in CTX_LADDER
              if not context_length or c <= context_length]
    if not capped:
        capped = [CTX_LADDER[0]]
    snapped = min(capped, key=lambda c: (abs(c - ctx), c))
    if snapped != ctx:
        why = (f" (the model is trained for {context_length})"
               if context_length and ctx > context_length else "")
        notes.append(f"num_ctx {ctx} snapped to {snapped} on the measured "
                     f"ladder{why}")
    out["num_ctx"] = snapped

    # -- the three discrete choices --------------------------------------
    pre = _int(raw.get("prefill_tokens"))
    if pre is None:
        pre = out["prefill_tokens"]
    if pre not in PREFILL_CHOICES:
        near = min(PREFILL_CHOICES, key=lambda c: (abs(c - pre), c))
        notes.append(f"prefill depth {pre} is not one of the measured depths: "
                     f"using {near}")
        pre = near
    out["prefill_tokens"] = pre

    pred = _int(raw.get("num_predict"))
    if pred is None:
        pred = out["num_predict"]
    if pred not in NUM_PREDICT_CHOICES:
        near = min(NUM_PREDICT_CHOICES, key=lambda c: (abs(c - pred), c))
        notes.append(f"generation length {pred} is not one of the measured "
                     f"lengths: using {near}")
        pred = near
    out["num_predict"] = pred

    warm = _int(raw.get("warmup"))
    if warm is None:
        warm = out["warmup"]
    if warm not in WARMUP_CHOICES:
        near = min(WARMUP_CHOICES, key=lambda c: (abs(c - warm), c))
        notes.append(f"warmup {warm} is not one of 0, 1 or 2: using {near}")
        warm = near
    out["warmup"] = warm

    # -- repeats ----------------------------------------------------------
    rep = _int(raw.get("repeats"))
    if rep is None:
        rep = out["repeats"]
    if rep < REPEATS_MIN or rep > REPEATS_MAX:
        near = max(REPEATS_MIN, min(REPEATS_MAX, rep))
        notes.append(f"repeats {rep} is outside {REPEATS_MIN}-{REPEATS_MAX}: "
                     f"using {near}")
        rep = near
    out["repeats"] = rep

    # -- unload -----------------------------------------------------------
    unload = raw.get("unload", out["unload"])
    out["unload"] = unload if isinstance(unload, bool) else out["unload"]
    return out, notes


# ==========================================================================
#   Refusals: DESIGN.md section 2, in the table's own order
# ==========================================================================

class Refusal(Exception):
    """A run that must not start, carrying the status code and the sentence.

    An exception rather than a return value because a refusal is not a result:
    every caller either hands it to the route or lets it out, and neither can
    forget to check it.
    """

    def __init__(self, code: int, error: str, **extra):
        super().__init__(error)
        self.code = code
        self.body = dict({"error": error}, **extra)


#: The flag a caller can set the instant it starts an answer. Exact,
#: in-process, and free.
_IN_CHAT = {"on": False, "since": 0.0}
_IN_CHAT_LOCK = threading.Lock()


def note_answer_start() -> None:
    """Record that an answer is streaming RIGHT NOW (DESIGN.md section 2's
    signal (a)).

    It is exact and costs nothing. What makes it enough rather than merely
    available is that `answer_streaming()` ALSO asks
    `jarvis_power_switch._busy_reason()`, which reads the HUD's own activity
    state - `_activity("speaking")` when the first chunk goes out,
    `_activity("working")` during a tool call, `_activity("idle")` at the end -
    the same signal both apps already show the owner. So this refusal is wired
    to the real chat path without a patch hunk inside the chat handler, which
    is where a second, coarser guard could only disagree with what he sees.
    """
    with _IN_CHAT_LOCK:
        _IN_CHAT.update(on=True, since=time.time())


def note_answer_end() -> None:
    """Record that the answer has finished, or failed. Idempotent."""
    with _IN_CHAT_LOCK:
        _IN_CHAT.update(on=False, since=0.0)


def answer_streaming() -> Optional[str]:
    """The 409 sentence when something is answering right now, or None.

    Two sources, most exact first:
      1. `_IN_CHAT`, set by `note_answer_start()`.
      2. `jarvis_power_switch._busy_reason()` - the shipped signal: the HUD's
         activity state, a Live conversation, or a waiting approval card.
    A guard that cannot tell must not invent a refusal, so anything that
    raises answers None.
    """
    with _IN_CHAT_LOCK:
        on = _IN_CHAT["on"]
    if on:
        return ANSWER_STREAMING
    try:
        import jarvis_power_switch  # type: ignore
        held = jarvis_power_switch._busy_reason()
    except Exception:
        return None
    if not held:
        return None
    low = str(held).lower()
    if any(w in low for w in ("answering", "speaking", "thinking", "working")):
        return ANSWER_STREAMING
    return (f"Jarvis is busy ({held}). Measuring now would time the queue, "
            "not the model.")


def read_standby() -> bool:
    """Is Jarvis on standby?

    `jarvis_power.current()` is where the mode really lives, and
    `jarvis_power_switch` reads it the same way it does here; that module has
    no reader of its own, so asking `jarvis_power` directly is the SAME
    question rather than a second opinion. The module is absent when the
    backend has not had the published base installed over it - the same
    `except` `jarvis_hardware._standby()` already uses, and the safe direction:
    an unknown mode is not a refusal invented from nothing.
    """
    try:
        import jarvis_power  # type: ignore
        return str(jarvis_power.current()) == "standby"
    except Exception:
        return False


def running_tasks() -> list:
    """The multi-step tasks running now, through the module that owns them.

    `jarvis_power_switch._running_tasks()` is the shipped reader, and it exists
    because a task continues between turns and would lose the model under it.
    Borrowed, not re-implemented, so this refusal cannot disagree with the
    standby one about what "a task is running" means.
    """
    try:
        import jarvis_power_switch  # type: ignore
        return list(jarvis_power_switch._running_tasks() or [])
    except Exception:
        return []


def check_job(body: dict, *, model: str = "", lane: str = "",
              base: Optional[str] = None,
              get: Optional[Callable[[str], dict]] = None,
              busy: Optional[Callable[[], Optional[str]]] = None,
              standby: Optional[Callable[[], bool]] = None,
              tasks: Optional[Callable[[], list]] = None,
              running: Optional[Callable[[], Optional[str]]] = None) -> None:
    """Raise `Refusal` if this POST must not start a run.

    THE ORDER IS DESIGN.md SECTION 2'S TABLE, top to bottom, and it is that
    order on purpose: "a run is already going" is answered before anything
    else, so the owner pressing Measure twice is never told his PC is busy in
    some other way. Each seam is injectable, so a test reaches every row of the
    table without a card, a model or a task.
    """
    body = body if isinstance(body, dict) else {}
    lane = lane or "everyday"
    url = base or lane_base(lane)

    # 1. another benchmark run is in flight - the in-process lock, the same
    #    shape as jarvis_hardware._MEASURE_LOCK
    if (running or _current_run)() is not None:
        raise Refusal(409, ALREADY_RUNNING)

    # 2. an answer is streaming right now
    sentence = (busy or answer_streaming)()
    if sentence:
        raise Refusal(409, sentence)

    # 3. Jarvis is on standby
    if (standby or read_standby)():
        raise Refusal(409, STANDBY)

    # 4. a multi-step task is running
    if (tasks or running_tasks)():
        raise Refusal(409, TASK_RUNNING)

    # 5. the target lane's Ollama is not running - NEVER started as a side
    #    effect. The only thing that starts a lane stays a preset apply.
    names = installed_models(url, get=get)
    if names is None:
        raise Refusal(409, LANE_DOWN.format(lane=lane))

    # 6. the model is not installed on that lane - and say what IS, because
    #    "not installed" with no list is a dead end
    if model and model not in names and (model + ":latest") not in names:
        raise Refusal(409, MODEL_MISSING.format(
            model=model, lane=lane,
            has=", ".join(sorted(names)[:12]) or "nothing"))

    # 7. Ollama's address is not loopback - the same rule
    #    jarvis_speed.measure() applies, because a benchmark on another PC's
    #    Ollama measures that PC
    if not is_loopback(url):
        raise Refusal(400, NOT_LOOPBACK.format(base=url))

    # 8. the POST carries no `confirm` block. DESIGN.md section 7: no card,
    #    but consent is explicit and machine-checkable, and a stale screen
    #    cannot start a run nobody agreed to.
    confirm = body.get("confirm")
    if not isinstance(confirm, dict) or not confirm.get("may_evict"):
        raise Refusal(400, NOT_CONFIRMED)
    if model and str(confirm.get("model") or "") not in ("", model):
        raise Refusal(400, NOT_CONFIRMED)
    if str(confirm.get("lane") or "") not in ("", lane):
        raise Refusal(400, NOT_CONFIRMED)


# ==========================================================================
#   The run itself
# ==========================================================================

_RUNS: dict = {}
_RUNS_LOCK = threading.Lock()

#: How many run states are kept in memory for `GET /api/bench/run/{id}` to
#: answer. The STORE is the history; this is only the progress a screen polls
#: while a run is going, so it is deliberately small - and losing one costs a
#: poll, not a number, because `view()` falls back to the store.
KEEP_STATES = 20


def _current_run() -> Optional[str]:
    """The id of a run in flight, or None. The in-process lock."""
    with _RUNS_LOCK:
        for rid, st in _RUNS.items():
            if st.get("state") == "running":
                return rid
    return None


def _new_run_id() -> str:
    """Sortable, unique, and never typed by a person."""
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _state(run_id: str) -> Optional[dict]:
    with _RUNS_LOCK:
        st = _RUNS.get(run_id)
        return dict(st) if st else None


def _set_state(run_id: str, **fields) -> None:
    with _RUNS_LOCK:
        st = _RUNS.get(run_id)
        if st is not None:
            st.update(fields)
        if len(_RUNS) > KEEP_STATES:
            done = [k for k, v in _RUNS.items() if v.get("state") != "running"]
            for k in done[:max(0, len(_RUNS) - KEEP_STATES)]:
                _RUNS.pop(k, None)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def start(body: dict, *, spawn: Optional[Callable] = None,
          post: Optional[Callable] = None,
          get: Optional[Callable[[str], dict]] = None,
          show: Optional[Callable[[str, dict], dict]] = None,
          smi: Optional[Callable[[], str]] = None,
          clock: Optional[Callable[[], float]] = None,
          log_text: Optional[Callable[[], str]] = None,
          log: Optional[BenchLog] = None,
          busy: Optional[Callable[[], Optional[str]]] = None,
          standby: Optional[Callable[[], bool]] = None,
          tasks: Optional[Callable[[], list]] = None,
          running: Optional[Callable[[], Optional[str]]] = None,
          spawn_thread: bool = True) -> tuple:
    """Start ONE benchmark in the background. Returns (http_status, body).

    The run is ASYNCHRONOUS: it spawns and returns, so a two-minute run can
    never hang a request thread. A screen polls `GET /api/bench/run/{id}`.

    `spawn_thread=False` runs it in place and is for the tests, which have no
    threads to spare and want the numbers before the call returns.
    """
    body = body if isinstance(body, dict) else {}
    model = str(body.get("model") or "").strip()
    if not model:
        return 400, {"error": "nothing was measured: no model was named"}
    lane = str(body.get("lane") or CONTROLS["lane"]).strip().lower()
    base = lane_base(lane)
    try:
        check_job(body, model=model, lane=lane, base=base, get=get, busy=busy,
                  standby=standby, tasks=tasks, running=running)
    except Refusal as exc:
        return exc.code, exc.body

    # The model's shape is read BEFORE normalising, so `num_gpu` really
    # defaults to "all the layers it has" rather than to None.
    shape = model_shape(base, model, show=show)
    controls, notes = normalise_controls(body,
                                        block_count=shape.get("block_count"),
                                        context_length=shape.get("context_length"))
    controls["model"] = model
    controls["lane"] = lane if lane in LANE_KEYS else CONTROLS["lane"]

    post = post or (lambda url, payload: post_stream(url, payload, clock=clock))
    smi = smi or smi_text
    log = log or BenchLog()
    run_id = _new_run_id()
    of = controls["warmup"] + controls["repeats"]
    with _RUNS_LOCK:
        _RUNS[run_id] = {"state": "running", "step": 0, "of": of,
                         "partial": False, "notes": notes, "run_id": run_id,
                         "at": int(time.time())}

    def work() -> None:
        try:
            _run(run_id, controls, notes, shape=shape, post=post, get=get,
                 smi=smi, clock=clock or time.monotonic, log_text=log_text,
                 log=log, base=base)
        except Exception as exc:                       # never leaves a gap
            _finish_failed(run_id, controls, log,
                           f"the run stopped ({type(exc).__name__})")
            _set_state(run_id, state="failed", partial=True,
                       why=type(exc).__name__)

    if not spawn_thread:
        work()
        return 200, {"ok": True, "run_id": run_id, "notes": notes,
                     "message": "Measured."}
    try:
        (spawn or _spawn)(work)
    except Exception:
        _set_state(run_id, state="failed")
        return 503, {"error": "could not start the benchmark"}
    return 200, {"ok": True, "run_id": run_id, "notes": notes,
                 "message": ("Measuring now. Nothing else should use the model "
                             "until it finishes.")}


def _run(run_id: str, controls: dict, notes: list, *, shape: dict, post, get,
         smi, clock, log_text, log: BenchLog, base: str) -> None:
    """Every repeat, one at a time, then the run row. Never raises past itself."""
    model = controls["model"]
    block_count = _int(shape.get("block_count"))
    before = read_cards(smi)
    driver = before.get("driver") or ""
    ollama_v = ollama_version(base, get=get) or ""
    loaded_before = [str(m.get("name") or m.get("model") or "")
                     for m in (ps_models(base, get=get) or [])]
    if any(str(c.get("display_active") or "").strip().lower() == "enabled"
           for c in before.get("cards") or ()):
        if controls["lane"] == "coding":
            notes.append("this card runs your screen; the desktop may stutter "
                         "while it measures")

    samples = [before.get("cards") or []]
    repeats: list = []
    total_steps = controls["warmup"] + controls["repeats"]
    step = 0
    cancelled = False
    for warmup in ([True] * controls["warmup"] + [False] * controls["repeats"]):
        st = _state(run_id)
        if st is None or st.get("cancelled"):
            cancelled = True
            break
        step += 1
        _set_state(run_id, step=step)
        row = _one_repeat(
            run_id=run_id, controls=controls, block_count=block_count,
            repeat=(step if warmup else step - controls["warmup"]),
            warmup=warmup, post=post, get=get, smi=smi, clock=clock,
            log_text=log_text, base=base, shape=shape, driver=driver,
            ollama_v=ollama_v)
        repeats.append(row)
        log.append(row)
        # Sample the cards after every repeat: this is the "~4x during" half of
        # "before, during, after", and it costs one nvidia-smi process.
        samples.append(read_cards(smi).get("cards") or [])

    peaks = peak_cards(samples)
    summary = summarise(repeats, warmup=controls["warmup"])
    summary["vram_peak_mb_card0"] = card_mb(peaks, 0)
    summary["vram_peak_mb_card1"] = card_mb(peaks, 1)
    summary["vram_base_mb_card0"] = card_mb(before.get("cards"), 0)
    summary["vram_base_mb_card1"] = card_mb(before.get("cards"), 1)
    summary["gpu_util_peak"] = util_peak(peaks)
    loaded = ps_models(base, get=get)
    summary["on_card_percent"] = on_card_percent(model, loaded)
    summary["ctx_used"] = context_used(model, loaded, shape)
    off = offloaded_layers(log_text=log_text)
    if off:
        summary["offloaded_layers"], summary["total_layers"] = off[0], off[1]
    if not summary["repeats_ok"] and repeats:
        summary["why"] = (repeats[0].get("why") if repeats else "") or \
            "no repeat produced a number"
    # Carry the prefill's own reason up from a repeat, so the run's sentence can
    # say "cached - prefill not measured" rather than the vaguer "not
    # measured". The two are different facts and the owner asked for the first.
    for r in repeats:
        if r.get("prefill_why"):
            summary["prefill_why"] = r["prefill_why"]
            break
    unload_note = _unload(model, base, post=post) if controls["unload"] else ""
    row = run_row(run_id=run_id, controls=controls, block_count=block_count,
                  before=before, loaded_before=loaded_before,
                  summary=summary, ollama_v=ollama_v, driver=driver,
                  unload_note=unload_note)
    log.append(row)
    _set_state(run_id, state="done", partial=bool(cancelled),
               cancelled=cancelled, result=row.get("words", ""),
               ok=bool(row.get("ok")))


def _one_repeat(*, run_id: str, controls: dict, block_count, repeat: int,
                warmup: bool, post, get, smi, clock, log_text, base: str,
                shape: dict, driver: str, ollama_v: str) -> dict:
    """One repeat: one request, one row. A failure writes `ok: false` + `why`
    and NEVER a zero standing in for a measurement."""
    model = controls["model"]
    depth = controls["prefill_tokens"]
    row = {
        "kind": "bench", "run": run_id, "model": model,
        "lane": controls["lane"], "card": LANE_CARDS.get(controls["lane"], ""),
        "ctx": controls["num_ctx"], "num_gpu": controls.get("num_gpu"),
        "block_count": block_count,
        "ram_share_percent": ram_share_for(controls, block_count),
        "num_predict": controls["num_predict"],
        "prefill_tokens": depth, "repeat": max(1, int(repeat)),
        "warmup": bool(warmup),
        "ollama_version": ollama_v or "", "driver_version": driver or "",
    }
    if depth <= 0:
        # No prefill at all: nothing to time on the prompt side, and saying so
        # is better than a 0 that reads as "terribly slow".
        row["prefill_why"] = "no prefill: depth 0"
    # A fresh prompt every time - the cache would otherwise make every repeat
    # after the first look 300x faster. See `prefill_prompt`.
    payload = {
        "model": model,
        "prompt": prefill_prompt(depth, f"{run_id}/r{repeat}/"
                                        f"{'warm' if warmup else 'run'}"),
        "stream": True,
        # The load-time options. A distinct num_ctx or num_gpu reloads the
        # model, which is why the context ladder snaps and why load_ms is
        # reported per repeat instead of being folded into the rate.
        "options": {"num_ctx": controls["num_ctx"],
                    "num_gpu": controls.get("num_gpu"),
                    "num_predict": controls["num_predict"],
                    "temperature": 0, "seed": 7},
    }
    payload["options"] = {k: v for k, v in payload["options"].items()
                          if v is not None}
    started = clock()
    try:
        first_s, reply = post(f"{base}/api/generate", payload)
    except Exception as exc:
        row.update(ok=False, why=f"Ollama stopped answering "
                                 f"({type(exc).__name__})"[:MAX_REASON])
        return row
    row.update(timings(reply))
    if isinstance(first_s, (int, float)) and not isinstance(first_s, bool) \
            and first_s >= 0:
        # The harness's own wall clock, from POST to the first chunk carrying
        # text: the time-to-first-token the owner actually waited.
        row["ttft_wall_ms"] = int(round(float(first_s) * 1000.0))
    row["total_ms"] = int(round((clock() - started) * 1000.0))
    row["ttft_note"] = ttft_note(row.get("ttft_wall_ms"),
                                 row.get("ttft_ollama_ms"))
    loaded = ps_models(base, get=get)
    row["on_card_percent"] = on_card_percent(model, loaded)
    row["ctx_used"] = context_used(model, loaded, shape)
    off = offloaded_layers(log_text=log_text)
    if off:
        row["offloaded_layers"], row["total_layers"] = off[0], off[1]
    cards = read_cards(smi).get("cards") or []
    row["gpu_util_peak"] = util_peak(cards)
    row["vram_peak_mb_card0"] = card_mb(cards, 0)
    row["vram_peak_mb_card1"] = card_mb(cards, 1)
    if not row.get("ok") and not row.get("why"):
        row["why"] = NO_TIMINGS
    return row


def _unload(model: str, base: str, *, post) -> str:
    """Let the model go, because this PC runs OLLAMA_KEEP_ALIVE=-1.

    Without this a benchmark leaves a 6 GB model resident on the everyday card:
    the next answer is fast, but a card the owner did not ask to fill stays
    full until something evicts it. `keep_alive: 0` means "unload when this
    request ends". A failure is a SENTENCE and not a silent success - a row
    that claims to have unloaded and did not is worse than one that admits it.
    """
    try:
        post(f"{base}/api/generate", {"model": model, "keep_alive": 0,
                                      "prompt": ""})
        return ""
    except Exception as exc:
        return (f"the model was left loaded: it could not be unloaded "
                f"({type(exc).__name__})")[:MAX_REASON]


def run_row(*, run_id: str, controls: dict, block_count, before: dict,
            loaded_before: list, summary: dict, ollama_v: str, driver: str,
            unload_note: str = "", preset: str = "") -> dict:
    """`kind: "bench-run"` - ONE row per run: the setup, and the aggregate.

    `spilled` is computed from BOTH sources and ORed, so a run that put some
    layers on the processor can never be presented as fast (DESIGN.md
    section 13). `words` is the one sentence a screen shows, built HERE so the
    desktop and the phone cannot word the same result two different ways.
    """
    lane = controls.get("lane") or "everyday"
    pct = summary.get("on_card_percent")
    off = summary.get("offloaded_layers")
    total = summary.get("total_layers")
    did_spill = spilled(pct, off, total)
    row = {
        "kind": "bench-run", "run": run_id,
        "model": controls.get("model", ""),
        "lane": lane, "card": LANE_CARDS.get(lane, ""),
        "ctx": controls.get("num_ctx"),
        "ctx_used": summary.get("ctx_used"),
        "num_gpu": controls.get("num_gpu"),
        "block_count": _int(block_count),
        "ram_share_percent": ram_share_for(controls, block_count),
        "num_predict": controls.get("num_predict"),
        "prefill_tokens": controls.get("prefill_tokens"),
        "repeats": controls.get("repeats"),
        "warmup_passes": controls.get("warmup"),
        "unload": bool(controls.get("unload")),
        "ok": bool(summary.get("repeats_ok")),
        "worst_repeat_ok": bool(summary.get("worst_repeat_ok")),
        "spilled": did_spill,
        "repeats_ok": summary.get("repeats_ok"),
        "gen_median": summary.get("gen_median"),
        "gen_min": summary.get("gen_min"),
        "gen_max": summary.get("gen_max"),
        "gen_spread": summary.get("gen_spread"),
        "prefill_median": summary.get("prefill_median"),
        "prefill_min": summary.get("prefill_min"),
        "prefill_max": summary.get("prefill_max"),
        "prefill_spread": summary.get("prefill_spread"),
        "prefill_why": summary.get("prefill_why") or "",
        "ttft_wall_median": summary.get("ttft_wall_median"),
        "ttft_ollama_median": summary.get("ttft_ollama_median"),
        "on_card_percent": pct,
        "offloaded_layers": _int(off), "total_layers": _int(total),
        "vram_peak_mb_card0": summary.get("vram_peak_mb_card0"),
        "vram_peak_mb_card1": summary.get("vram_peak_mb_card1"),
        "vram_base_mb_card0": summary.get("vram_base_mb_card0"),
        "vram_base_mb_card1": summary.get("vram_base_mb_card1"),
        "gpu_util_peak": summary.get("gpu_util_peak"),
        "preset": preset,
        "ollama_version": ollama_v or "",
        "driver_version": driver or "",
        "loaded_before": ", ".join(n for n in (loaded_before or []) if n),
        "unload_note": unload_note,
    }
    if loaded_before:
        row["restore_note"] = (
            f"{', '.join(n for n in loaded_before if n)} was loaded before this "
            "run and is not reloaded afterwards: a run puts a different model "
            "on the card, and the next answer pays for the reload")
    if not row["ok"]:
        row["why"] = summary.get("why") or "no repeat produced a number"
    row["words"] = _words(row, did_spill)
    return row


def _words(row: dict, did_spill: bool) -> str:
    """The one sentence. Numbers only, and a spilled run says so FIRST.

    A sentence that leads with "41.2 tokens a second" and mentions the spill
    afterwards is a sentence that will be read as 41.2. So a spilled run opens
    with what it could not do.

    AND IT DOES NOT CLAIM THE LAYERS IT ASKED FOR. "32 of 32 layers on the
    card" beside "only 93% of it was in video memory" is a sentence that
    contradicts itself, and the reader has no way to tell which half is the
    measurement. When the run spilled, the setup is described as what was
    ASKED FOR and the actual placement is the PARTIAL line - which is the only
    one that was measured.
    """
    model = row.get("model") or "this model"
    lane = row.get("lane") or "everyday"
    card = row.get("card") or ""
    ctx = row.get("ctx")
    layers = row.get("num_gpu")
    total = row.get("block_count")
    gen, pre = row.get("gen_median"), row.get("prefill_median")
    n = row.get("repeats_ok") or 0
    spread = row.get("gen_spread")
    lo, hi = row.get("gen_min"), row.get("gen_max")

    bits: list = []
    if did_spill:
        pct = row.get("on_card_percent")
        off, tot = row.get("offloaded_layers"), row.get("total_layers")
        if off is not None and tot:
            detail = f"only {off} of {tot} layers reached"
        elif pct is not None:
            detail = f"only {pct}% of it was in"
        else:
            detail = "not all of it was in"
        bits.append(f"PARTIAL: {detail} the graphics card, so the rest ran on "
                    "the processor - these numbers are NOT comparable with a "
                    "fully-on-card run")
    head = (f"{model} on the {lane} lane ({card})" if card
            else f"{model} on the {lane} lane")
    if ctx:
        head += f" at {int(ctx):,} tokens"
    if layers is not None and total:
        if did_spill:
            # What was ASKED FOR, labelled as such - the placement is the
            # PARTIAL line above, and that is the one that was measured.
            head += f", asking for {layers} of {total} layers on the card"
        else:
            head += f", {layers} of {total} layers on the card"
            if layers >= total:
                head += ", no spill"
    bits.append(head)
    if gen is not None and n:
        tail = ""
        if lo is not None and hi is not None and spread is not None:
            tail = f" (median of {n}, spread {lo}-{hi})"
        bits.append(f"Generation {gen} tokens a second{tail}")
    elif n:
        bits.append("Generation could not be measured")
    else:
        bits.append("Nothing was measured")
    if pre is not None:
        bits.append(f"prefill {pre} tokens a second")
    elif row.get("prefill_why") == CACHED_PREFILL:
        bits.append(f"prefill: {CACHED_PREFILL}")
    else:
        bits.append("prefill was not measured")
    return ". ".join(bits) + "."


def _finish_failed(run_id: str, controls: dict, log: BenchLog, why: str) -> None:
    """A run that died still writes its row: `ok: false`, `why`, never a zero.

    DESIGN.md section 13: "every exit path writes a row". A silent gap is the
    worst outcome, because the next reader cannot tell it from a run that was
    never started at all.
    """
    lane = (controls or {}).get("lane") or ""
    log.append({
        "kind": "bench-run", "run": run_id,
        "model": (controls or {}).get("model", ""),
        "lane": lane, "card": LANE_CARDS.get(lane, ""),
        "ok": False, "worst_repeat_ok": False, "spilled": False,
        "why": str(why)[:MAX_REASON],
        "words": f"Nothing was measured: {why}.",
    })


def view(run_id: str, *, log: Optional[BenchLog] = None) -> tuple:
    """`GET /api/bench/run/{id}`: (status, {state, step, of, partial, result}).

    In memory while it runs, and out of the STORE once it has finished and
    fallen out of the small in-memory map - so a screen that polls a little
    late still gets the numbers instead of a 404.
    """
    st = _state(run_id)
    if st is not None:
        out = {"state": st.get("state"), "step": st.get("step"),
               "of": st.get("of"), "partial": bool(st.get("partial"))}
        if st.get("notes"):
            out["notes"] = list(st["notes"])
        if st.get("state") == "done":
            got = (log or BenchLog()).get(run_id)
            if got:
                out["result"] = got["run"]
        elif st.get("why"):
            out["why"] = st["why"]
        return 200, out
    got = (log or BenchLog()).get(run_id)
    if not got:
        return 404, {"error": "no benchmark run with that id"}
    return 200, {"state": "done" if got["run"].get("ok") else "failed",
                 "step": got["run"].get("repeats"),
                 "of": got["run"].get("repeats"), "partial": False,
                 "result": got["run"]}


def cancel(run_id: str, *, log: Optional[BenchLog] = None) -> tuple:
    """`POST /api/bench/cancel`: stop after the repeat in flight.

    The repeat already running is NOT killed. A request cut off mid-answer
    leaves Ollama's counters unusable, and half a measured repeat is not a
    number. What has been written stays written, and the run row says PARTIAL.
    """
    st = _state(run_id)
    if st is None:
        return 404, {"error": "no benchmark run with that id"}
    if st.get("state") != "running":
        return 409, {"error": "that run has already finished"}
    bench_log = log or BenchLog()
    got = bench_log.get(run_id)
    kept = len(got["repeats"]) if got else 0
    _set_state(run_id, cancelled=True)
    return 200, {"ok": True, "cancelled": True, "kept_rows": kept}


def history(*, limit: int = 20, model: str = "", lane: str = "",
            preset: str = "", log: Optional[BenchLog] = None) -> dict:
    """`GET /api/bench/history`: the run rows, newest first, with a note.

    `note` is always a sentence, because a list that is empty for two different
    reasons - "never run" and "the filter matched nothing" - is a list that
    cannot be read.
    """
    log = log or BenchLog()
    runs = log.runs(limit=limit, model=model, lane=lane, preset=preset)
    if not runs:
        note = ("No benchmark runs on file yet." if not (model or lane or preset)
                else "No benchmark runs match that filter.")
    else:
        note = f"{len(runs)} run(s), newest first."
    return {"runs": runs, "total": len(runs), "note": note}


# ==========================================================================
#   GET /api/bench: the whole of what a Benchmark screen draws
# ==========================================================================

def controls_view(*, model: str = "", lane: str = "everyday",
                  get: Optional[Callable[[str], dict]] = None,
                  show: Optional[Callable[[str, dict], dict]] = None,
                  smi: Optional[Callable[[], str]] = None,
                  log: Optional[BenchLog] = None) -> dict:
    """Everything a Benchmark screen needs to draw itself, and nothing it would
    have to guess.

    Deliberately NOT one `/api/show` per installed model: that is an HTTP round
    trip each, and a screen that opens slowly to show a dropdown is worse than
    one that fills `block_count` when the owner picks a model (`?model=<name>`,
    which is what the `model` argument is for).
    """
    lanes = {}
    for key in LANE_KEYS:
        base = lane_base(key)
        names = installed_models(base, get=get)
        lanes[key] = {
            "port": LANE_PORTS[key],
            "card": LANE_CARDS[key],
            "running": names is not None,
            "models": sorted(names) if names else [],
        }
    lane = lane if lane in LANE_KEYS else "everyday"
    shape = model_shape(lane_base(lane), model, show=show) if model \
        else {"block_count": None, "context_length": None}
    cards = read_cards(smi)
    return {
        "controls": dict(CONTROLS),
        "ladders": {
            "ctx": list(CTX_LADDER),
            "prefill_tokens": list(PREFILL_CHOICES),
            "num_predict": list(NUM_PREDICT_CHOICES),
            "warmup": list(WARMUP_CHOICES),
            "repeats": [REPEATS_MIN, REPEATS_MAX],
        },
        "lanes": lanes,
        "model": model,
        "lane": lane,
        "block_count": shape.get("block_count"),
        "context_length": shape.get("context_length"),
        "cards": cards.get("cards") or [],
        "driver_version": cards.get("driver") or "",
        "standby": read_standby(),
        "running": _current_run(),
        "last_run": (log or BenchLog()).runs(limit=1),
        "note": ("A benchmark loads a model, so anything loaded now may be "
                 "evicted. Nothing is downloaded and nothing is sent off this "
                 "PC."),
    }


# ==========================================================================
#   "How did the last benchmark do?" - DESIGN.md section 9
# ==========================================================================
#
# ONE function, two entry points (the read-only chat tool and the "Explain this
# result" button), so the sentence is identical wherever it is read. It reads
# `bench.jsonl` and nothing else: it cannot run a benchmark, delete a row, or
# reach the network. The ROUTE and the model tool are later phases; the
# sentence and its refusals are here because they are arithmetic over stored
# numbers, which is exactly what a test can prove.

def advice(*, model: str = "", lane: str = "", preset: str = "",
           run_id: str = "", log: Optional[BenchLog] = None) -> dict:
    """{note, numbers, enough} - one sentence built only from stored rows.

    THE FLOOR IS THREE RUNS, this repo's own rule (`jarvis_speed.MIN_EACH = 3`:
    "two lists of two can differ by 40% from noise alone"). Under three usable
    runs it says how many it has and refuses to compare - it never calls one
    setup better from a single sample.

    A VERSION CHANGE IS SAID OUT LOUD. The driver moved once already on this PC
    (616.56 -> 617.42) and Ollama's version is stored on every row, so a
    comparison across either change names it rather than quietly mixing two
    machines into one verdict.
    """
    log = log or BenchLog()
    if run_id:
        got = log.get(run_id)
        if not got:
            return {"note": "There is no run with that id on file.",
                    "numbers": {}, "enough": False}
        return {"note": _describe_one(got["run"]), "numbers": got["run"],
                "enough": False}
    runs = [r for r in log.runs(limit=0, model=model, lane=lane, preset=preset)
            if r.get("ok") and isinstance(r.get("gen_median"), (int, float))]
    if not runs:
        which = f" of {model}" if model else ""
        return {"note": f"There is no usable benchmark run{which} on file yet.",
                "numbers": {}, "enough": False}
    if not model:
        # Without a model the only fair comparison is one model with itself, so
        # name the newest run's model and keep those runs.
        model = str(runs[0].get("model") or "")
        runs = [r for r in runs if r.get("model") == model]
    if len(runs) < MIN_RUNS:
        return {"note": (f"Only {len(runs)} run(s) of {model} are on file; "
                         f"three are needed before I compare them."),
                "numbers": {"runs": len(runs), "model": model},
                "enough": False}
    versions = {(r.get("ollama_version") or "", r.get("driver_version") or "")
                for r in runs}
    fastest = max(runs, key=lambda r: r.get("gen_median") or 0)
    clean = [r for r in runs if not r.get("spilled")]
    cleanest = (max(clean, key=lambda r: r.get("gen_median") or 0)
                if clean else None)
    bits = [f"{len(runs)} runs of {model} are on file, so a comparison is fair"]
    bits.append(f"fastest generation: {fastest.get('gen_median')} tokens a "
                f"second at {_setup_words(fastest)}")
    if fastest.get("spilled"):
        bits.append("but it spilled to system memory, so it is not "
                    "like-for-like with a fully-on-card run")
    if cleanest is not None and cleanest.get("run") != fastest.get("run"):
        bits.append(f"fastest with no spill: {cleanest.get('gen_median')} at "
                    f"{_setup_words(cleanest)}")
    if len(versions) > 1:
        bits.append("careful, these runs span a version change ("
                    + "; ".join(f"Ollama {o or '?'} / driver {d or '?'}"
                                for o, d in sorted(versions))
                    + "), so part of the difference may be the software rather "
                    "than the setup")
    return {"note": ". ".join(bits) + ".",
            "numbers": {"runs": len(runs), "model": model,
                        "fastest": fastest.get("run"),
                        "fastest_gen": fastest.get("gen_median"),
                        "fastest_clean": (cleanest or {}).get("run"),
                        "fastest_clean_gen": (cleanest or {}).get("gen_median"),
                        "versions": sorted(f"{o}/{d}" for o, d in versions)},
            "enough": True}


def _setup_words(run: dict) -> str:
    """ "16,384 tokens on the everyday lane" - the two controls that change a
    number the most, named the way the owner set them."""
    bits = []
    if run.get("ctx"):
        bits.append(f"{int(run['ctx']):,} tokens")
    if run.get("lane"):
        bits.append(f"the {run['lane']} lane")
    return " on ".join(reversed(bits)) if bits else "this setup"


def _describe_one(run: dict) -> str:
    """One run in the words DESIGN.md section 9 quotes, built from the row.

    Only numbers that are ON the row, and only words the row earns: a spilled
    run says so, a prefill that was fully cached says "not measured", and a
    failed run says why instead of showing a zero.
    """
    if not run.get("ok"):
        return (f"That run did not measure anything: "
                f"{run.get('why') or 'no reason was recorded'}.")
    bits = [str(run.get("words") or "").rstrip(".")]
    if run.get("ttft_wall_median"):
        bits.append(f"the first token took "
                    f"{int(run['ttft_wall_median'])} ms")
    if run.get("on_card_percent") is not None:
        bits.append(f"{run['on_card_percent']}% of it was in video memory")
    if run.get("gen_spread") is not None:
        bits.append(f"spread {run.get('gen_min')}-{run.get('gen_max')}")
    return ". ".join(b for b in bits if b) + "."


# ==========================================================================
#   Tests
# ==========================================================================

def _reset_for_tests() -> None:
    """Forget the in-memory run map and the answer flag. Tests only."""
    with _RUNS_LOCK:
        _RUNS.clear()
    note_answer_end()


def lane_pins() -> dict:
    """The lane ports and card labels this module assumes, for the test to
    compare against `jarvis_model_lanes.py`.

    The ports are pinned by TEST rather than imported, for the same reason
    `jarvis_model_lanes.POOLED_PORT` is: a benchmark must be able to say what
    it is talking to even on a backend where that module is missing, and an
    import that quietly fails would silently move every lane to the default
    port. A pinned constant plus a test that compares them is the version that
    fails loudly.
    """
    try:
        import jarvis_model_lanes as lanes  # type: ignore
    except Exception:
        return {}
    return {"lanes": {l.key: l.port for l in lanes.LANES},
            "pooled": getattr(lanes, "POOLED_PORT", None)}
