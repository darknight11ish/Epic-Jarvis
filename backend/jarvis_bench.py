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

    NO APPROVAL CARD, and that is a RECORDED decision with a precedent rather
    than a shortcut: `decisions.d/2026-11-04-self-benchmark-no-approval-card.md`
    (rolled into `docs/DECISIONS.md`) records it and its reasoning. The
    precedent is `POST /api/hardware/measure`, which already runs with no card
    because it "runs one short prompt per model on this PC and changes no
    setting", and here the owner is the actor. What a card would have bought is
    bought explicitly instead: the request must carry
    `confirm: {model, lane, may_evict: true}`. (This docstring used to cite
    "DESIGN.md section 7", and DESIGN.md lives only under `.dsh-scratch/`, so
    the claim that it was recorded pointed at nothing a reader could check.)

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
import sys
import tempfile
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
#:
#: `lane` is deliberately NOT here: it is a closed vocabulary, and a field in
#: both tables used to be a real defect - `lane` sat in both, `_clean()` tested
#: this one first, and `_ENUM_FIELDS`' own promise ("a value outside its list
#: is dropped") was unreachable for it, so "everyday lane" was cut to 12
#: characters and stored as a fourth lane. Keep the two tables disjoint.
_NAME_FIELDS = {
    "run": 60, "model": 120, "card": 40,
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

    A CLOSED VOCABULARY IS CHECKED BEFORE A TEXT FIELD. The two tables are
    disjoint (`lane` used to be in both, and the name branch won, which is how
    its enum check became dead code), and the enum branch goes first anyway so
    a future field added to both cannot bypass its own list.
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
        elif k in _ENUM_FIELDS:
            if isinstance(v, str) and v in _ENUM_FIELDS[k]:
                out[k] = v
        elif k in _NAME_FIELDS:
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()[:_NAME_FIELDS[k]]
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


def _child_env() -> dict:
    """The environment the `nvidia-smi` child gets: `jarvis_child_env`'s
    allowlist, so no token and no key of the owner's goes with it.

    THE RULE IS NOT DECORATION. A child that inherits the parent's environment
    inherits `HUD_TOKEN` and `JARVIS_TOKEN` with it, and every spawn in this
    repository either passes an environment or sits on
    `backend/test_child_env_spawns.py`'s small reviewed list. `nvidia-smi` needs
    only PATH, so this is the same shape `jarvis_docker._env()` uses: the
    allowlist when that module is there, and almost nothing when it is not,
    rather than everything.
    """
    try:
        import jarvis_child_env as CE  # type: ignore
        env = CE.inherited()
    except Exception:
        env = {}
    env.setdefault("PATH", "")
    return env


def smi_text() -> str:
    """One `nvidia-smi` query. "" when the tool is missing or refuses.

    ONE process for one call, which is why a run samples before, after every
    repeat, and at the end - rather than on a timer that would leave a process
    running for the whole benchmark. No shell, and no inherited environment.
    """
    exe = shutil.which("nvidia-smi") or "nvidia-smi"
    try:
        r = subprocess.run([exe, "--query-gpu=" + ",".join(SMI_FIELDS),
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8,
                           env=_child_env(), shell=False)
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


def _bare(name) -> str:
    """A model name without the `:latest` Ollama adds for itself. The same
    rule `jarvis_big_coder._bare` uses, kept here so a scorecard written one
    day is found the next."""
    x = str(name or "").strip()
    return x[:-7] if x.endswith(":latest") else x


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
# A FRESH PROMPT FOR EVERY REPEAT (RESEARCH.md section 6, rule 4), AND THE PART
# THAT MAKES IT FRESH COMES FIRST. Ollama serves the LONGEST COMMON PREFIX of a
# prompt from its cache, so a per-repeat tag at the TAIL leaves the entire word
# body cacheable: every repeat after the first is served from the cache, the
# honest `(count - cached)` formula divides the few uncached tail tokens, and
# the median is a measurement of the tail rather than of the depth. The tag is
# therefore the FIRST thing on the prompt, and what a cache can still serve is
# only the tag's own opening characters - a handful of tokens, not `depth`.
# (The shipped shape until 2026-11-04 put it at the tail, and
# `backend/test_bench.py` now pins the front.) The prompt is generated from a
# fixed word list with no owner text in it. It is never stored: what is stored
# is how many tokens Ollama said it really counted.

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

    THE TAG LEADS, because Ollama's cache is a PREFIX cache. Two repeats of one
    run share their run id, so a tail tag would leave every word of the body
    shared and cacheable - the honest formula would then time the tail. With
    the tag at the front the two prompts diverge within the tag (a few tokens
    at most), and `depth` tokens of body are genuinely read on every repeat.
    """
    n = max(0, int(depth or 0))
    if n <= 0:
        return "Reply with one short sentence about a thermometer."
    out = [_WORDS[i % len(_WORDS)] for i in range(n)]
    # The head is what makes this prompt different from every other one, and it
    # is counted too, so the depth stays as asked.
    head = f"[{tag}] " if tag else ""
    return head + " ".join(out) + "\n\nReply with one short sentence."


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
    # "ALL OF THEM" IS block_count + 1, NOT block_count. Ollama's num_gpu
    # counts the layers kept on the graphics card, and the OUTPUT layer is
    # offloadable too. Measured on this PC, 2026-11-06, on the live 11436
    # lane with qwen3.5:9b (block_count 32): num_gpu=32 loaded size 6.13 GB
    # of which size_vram 5.12 GB - 83.6% on card - while num_gpu=33, 34, 40
    # and 99 all loaded 5.49 of 5.49 GB, i.e. 100%. So a run that asks for
    # "all layers" has to ask for block_count + 1, or the 100% baseline this
    # benchmark exists to compare against is unreachable by design. An
    # explicit larger value is clamped to that same number: the control
    # cannot usefully go past every layer, but it must be able to reach them.
    # The slider the owner sees keeps its range - this is the RESOLVED
    # request, not the control.
    want = raw.get("num_gpu", out["num_gpu"])
    every = block_count + 1 if block_count else None
    if want is None:
        want = every
    n = _int(want)
    if n is None:
        n = every
    if n is not None:
        if every is not None and n > every:
            notes.append(f"num_gpu {n} is more layers than the model has "
                         f"({block_count}) plus its output layer: requesting "
                         f"all {every} layers (every layer on the card)")
            n = every
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


#: How many /api/chat requests in THIS process are streaming an answer right
#: now. A COUNT, not a flag: two clients can ask at once (the desktop and the
#: phone), and the answer is only over when the last one ends. Set and cleared
#: by jarvis_hud's turn guard (`activity-turn-guard.patch`) on every way out of
#: the handler, so a turn that ends down any path - answered, quick-answered,
#: raised, client gone - cannot leave it stuck.
_IN_CHAT = {"depth": 0, "since": 0.0}
_IN_CHAT_LOCK = threading.Lock()

#: The words `jarvis_power.in_flight()` uses for its activity branch. They are
#: the only busy words it can return, which is how this module knows which of
#: its reasons came from the HUD's activity mark.
_ACTIVITY_BUSY = ("thinking", "speaking", "working")

#: Fallback only: the lease itself lives in jarvis_events, so power, bench and
#: the status route share one definition. Used when the installed
#: jarvis_events predates clear_if_stale() - and the safe answer then is the
#: old refusal, never a guessed unlock.
ACTIVITY_STALE_SECONDS = 300.0


def note_answer_start() -> None:
    """Record that an answer is streaming RIGHT NOW (DESIGN.md section 2's
    signal (a)).

    It is exact and costs nothing, and it is set by the one place every
    /api/chat request passes through (jarvis_hud's turn guard), so it covers
    the quick answers and the failed turns too - not only the ones that reach
    the answer path's own `finally`. Counted, so a second client asking at the
    same time cannot clear it early. `answer_streaming()` refuses on this alone
    while the activity mark is fresh; the stale-mark lease is the second
    opinion, and the owner's ruling of 2026-11-06 says a mark with no progress
    for five minutes must be cleared rather than block the benchmark all day.
    """
    with _IN_CHAT_LOCK:
        if int(_IN_CHAT["depth"]) <= 0:
            _IN_CHAT["since"] = time.time()
        _IN_CHAT["depth"] = int(_IN_CHAT["depth"]) + 1


def note_answer_end() -> None:
    """One answer finished, or failed. Idempotent: never below zero."""
    with _IN_CHAT_LOCK:
        _IN_CHAT["depth"] = max(0, int(_IN_CHAT["depth"]) - 1)
        if _IN_CHAT["depth"] == 0:
            _IN_CHAT["since"] = 0.0


def _busy_activity() -> dict:
    """(state, age in seconds, was just cleared) for the HUD's activity mark.

    The clear is `jarvis_events.clear_if_stale()` - the owner's 2026-11-06
    ruling: a busy mark with no progress for ACTIVITY_STALE_SECONDS is a
    leftover, so it is auto-cleared (once, with a structured warning) and the
    benchmark may proceed. The OTHER reasons in_flight can return - a Live
    conversation, another conversation, a waiting approval card, a running
    task - are untouched: only the activity lease is cleared here.
    """
    try:
        import jarvis_events  # type: ignore
        try:
            marked = jarvis_events.clear_if_stale()
        except AttributeError:
            marked = None
        mark = jarvis_events.activity() or {}
        state = str(mark.get("state") or "").strip().lower()
        try:
            age = jarvis_events.activity_age()
        except AttributeError:
            at = float(mark.get("at") or 0.0)
            age = max(0.0, time.time() - at) if at > 0 else None
    except Exception:
        return {"state": "", "age_s": None, "cleared": None}
    return {"state": state,
            "age_s": None if age is None else round(float(age), 1),
            "cleared": marked if marked else None}


def _answer_hold() -> dict:
    """The one 409 row's answer, with the two facts a stuck turn is read by.

    Returns {"sentence", "busy_reason", "activity_age_s"}; `sentence` is None
    when nothing is answering. This is what `answer_streaming()` keeps for
    existing callers and what `check_job()` puts in the refusal BODY, so a
    refused benchmark can be read without any source: the reason the model was
    held, and how old that claim is (the ruling's diagnosability half).
    """
    out = {"sentence": None, "busy_reason": None, "activity_age_s": None}
    mark = _busy_activity()
    out["activity_age_s"] = mark["age_s"]
    with _IN_CHAT_LOCK:
        on = int(_IN_CHAT.get("depth") or 0) > 0
    if mark["cleared"] is not None:
        # A leftover mark was just cleared; the bus logged one warning for it,
        # and a refusal must not be invented from something no longer true.
        return out
    if on:
        out["sentence"] = ANSWER_STREAMING
        out["busy_reason"] = (f"Jarvis is {mark['state']} right now"
                              if mark["state"] else "a chat turn is in flight")
        return out
    try:
        import jarvis_power_switch  # type: ignore
        held = jarvis_power_switch._busy_reason()
    except Exception:
        return out
    if not held:
        return out
    out["busy_reason"] = str(held)
    low = str(held).lower()
    out["sentence"] = (ANSWER_STREAMING if any(w in low for w in _ACTIVITY_BUSY)
                       else f"Jarvis is busy ({held}). Measuring now would "
                            "time the queue, not the model.")
    return out


def answer_streaming() -> Optional[str]:
    """The 409 sentence when something is answering right now, or None.

    Three sources, most exact first:
      1. `_IN_CHAT` - a /api/chat request in THIS process is in flight. Exact,
         and every way out of the handler clears it (the HUD's turn guard).
      2. the HUD's activity mark, through
         `jarvis_power_switch._busy_reason()`. It auto-clears a busy mark with
         no progress for `jarvis_events.ACTIVITY_STALE_SECONDS` - measured
         2026-11-06: a quick-answered chat turn left "thinking" behind and the
         benchmark refused for over four hours until the backend restarted.
      3. any other busy reason (a Live conversation, a waiting approval card)
         is named in the refusal as it always was.
    A guard that cannot tell must not invent a refusal, so anything that
    raises answers None. `check_job()` uses `_answer_hold()`, which is this
    answer plus the reason and age carried in the 409 body.
    """
    return _answer_hold()["sentence"]


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

    # 2. an answer is streaming right now - and the refusal carries the reason
    #    and the age of the claim, so a stuck mark is visible in the 409 body
    #    itself (the owner's ruling of 2026-11-06: the benchmark must be able
    #    to say why it is refusing without anyone reading this file).
    if busy is not None:
        sentence, details = busy(), {}
    else:
        hold = _answer_hold()
        sentence = hold["sentence"]
        details = ({"busy_reason": hold["busy_reason"],
                    "activity_age_s": hold["activity_age_s"]}
                   if sentence else {})
    if sentence:
        raise Refusal(409, sentence, **details)

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
    # A fresh prompt every time, with its per-repeat tag at the FRONT: Ollama
    # caches the longest common prefix, so a tag at the tail would leave the
    # whole body cached and every repeat after the first would time the tail,
    # not the depth (the shape until 2026-11-04). See `prefill_prompt`.
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
# ONE function, two entry points PLANNED (the read-only chat tool
# `benchmark_results` and the "Explain this result" button), so the sentence is
# identical wherever it is read. It reads `bench.jsonl` and nothing else: it
# cannot run a benchmark, delete a row, or reach the network.
#
# NOT ROUTED, AND NOT CALLED BY ANYTHING YET - the honest state of this code on
# 2026-11-04. There is NO `/api/bench/advice` route: `backend/bench.patch` wires
# exactly five routes (`GET /api/bench`, `GET /api/bench/run/{id}`,
# `GET /api/bench/history`, `POST /api/bench/run`, `POST /api/bench/cancel`),
# the `benchmark_results` chat tool does not exist, and no app draws an
# "Explain this result" button. The only caller in this repository is
# `backend/test_bench.py`. It is here because the sentence and its refusals are
# arithmetic over stored numbers, which is exactly what a test can prove, and
# DESIGN.md's phase plan puts the route and the tool in phase 4. A later reader
# must not report it as reachable until one of those callers exists - and
# `tools/check_parity.py`'s bench block says the same thing beside the five
# routes that DO exist.

def advice(*, model: str = "", lane: str = "", preset: str = "",
           run_id: str = "", log: Optional[BenchLog] = None) -> dict:
    """{note, numbers, enough} - one sentence built only from stored rows.

    NOT ROUTED AND NOT CALLED BY A SCREEN OR A TOOL YET (2026-11-04): there is
    no `/api/bench/advice` route and no `benchmark_results` chat tool, so the
    only caller is `backend/test_bench.py`. DESIGN.md phase 4 wires it. See the
    comment block above; do not describe this sentence as reachable until one
    of those callers exists.

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
    """Forget the in-memory run map and the answer count. Tests only."""
    with _RUNS_LOCK:
        _RUNS.clear()
    with _IN_CHAT_LOCK:
        _IN_CHAT.update(depth=0, since=0.0)


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


# ==========================================================================
#   THE FIVE BENCHMARK SUITES (2026-11-07, Wave-9 Lane 3)
# ==========================================================================
#
# WHAT THIS SECTION IS. The owner's ruling Q2 (2026-11-07 17:40 PT) made one
# fixed 6-task quality rubric per domain plus a 3-repeat speed/VRAM gate the
# official bar for changing a preset default. This section is that bar as code:
# the five suites the owner chose, each scored by a check that cannot be talked
# into a pass, each run on a THROWAWAY Ollama on port 11451+ so the number is
# the model's own and never the live lane's queue.
#
# WHY A THROWAWAY SERVER AND NOT THE LIVE LANE. Measured on this PC (2026-11-06):
# a model benchmarked beside a resident model on the same card spilled 16% to
# system RAM and measured the spill, not the model. The shipped speed bench
# (`start()` above) measures a LIVE lane and is right to: it times the setup the
# owner actually runs. A suite run is a different question - "what can this
# model do on this card" - so it gets its own server, its own card pin, and a
# zero-spill requirement before a speed row is promotion-grade.
#
# WHAT THE OWNER RULED ABOUT THE LIVE LANES (Q3):
#   * an OWNER-INITIATED run may unload the resident model on the target card,
#     say so on the screen, and MUST warm the active preset back afterwards;
#   * a SCHEDULED/BACKGROUND run is idle-only and never evicts anything;
#   * the only 409 that is about being busy is a chat/voice turn that is
#     STREAMING right now (plus the two safety rows this benchmark already had:
#     standby, and a multi-step task running).
#
# WHAT IS NEVER STORED. Prompts and answers do not reach the store: the score
# row's allowlist is an allowlist, like `_clean()`, and it has no field that
# could hold a prompt or a model's answer. Only the task ID, a pass/fail and the
# numbers are written. The one exception a reader might expect - the answer to
# an exact-answer question - is judged in memory and discarded.
#
# THE CODING RUBRIC RUNS MODEL-WRITTEN CODE. That is what "automated objective
# test" means for six small Python tasks: the answer's fenced block is executed
# by a SEPARATE interpreter (`-I`, a temporary folder, a 20 s timeout, and an
# allowlisted environment with no token, key or Jarvis variable in it). It is a
# guard against a runaway or broken answer, NOT a sandbox against hostile code;
# the code comes from the owner's own local model on the owner's own PC, and the
# alternative - eyeballing six answers - is exactly what the ruling replaced.

#: The suite IDs, in the order a screen should show them. Written into a score
#: row as a closed vocabulary, so a typo is a dropped field and not a new suite.
SUITE_KEYS = ("speed", "coding", "general", "tool_calling", "vision_ocr")

#: The owner's five suites, with what each one is for and what it needs. The
#: desktop Brain panel and any later route read this table rather than keeping
#: a second copy of the names.
SUITES = (
    {"id": "speed", "label": "Speed",
     "words": ("decode and prompt tokens a second, cold load, video memory and "
               "spill, three repeats; only a 100%-on-card, zero-spill run is "
               "promotion-grade"),
     "needs_image": False, "needs_tools": False},
    {"id": "coding", "label": "Coding",
     "words": ("six fixed coding tasks, each checked by running its own test"),
     "needs_image": False, "needs_tools": False},
    {"id": "general", "label": "General",
     "words": "six questions with one exact answer",
     "needs_image": False, "needs_tools": False},
    {"id": "tool_calling", "label": "Tool-calling",
     "words": "fixed tasks, scored on the right tool and its arguments",
     "needs_image": False, "needs_tools": True},
    {"id": "vision_ocr", "label": "Vision / OCR",
     "words": ("reads the text in one image; only a model that reports vision "
               "is asked"),
     "needs_image": True, "needs_tools": False},
)

#: The throwaway server's port range. NEVER a live lane's port: `LANE_PORTS`
#: above holds 11436/11435/11450, and the 11451 convention (2026-11-07) is the
#: first free number above the block. `_pick_port()` refuses anything inside
#: `LANE_PORTS` even if a caller passes it.
BENCH_PORT_FIRST, BENCH_PORT_LAST = 11451, 11460

#: Which model a run must unload when the owner allowed it to evict, per target
#: arrangement. "pooled" means all three cards are wanted, so the two lane
#: models AND the pooled lane's own model are in the way. The pooled SERVER on
#: 11450 is not stopped (it holds no model once its model is unloaded, and the
#: throwaway server uses another port).
EVICT_PORTS = {
    "everyday": (11436,),
    "coding": (11435,),
    "pooled": (11436, 11435, 11450),
}

#: The context a suite run uses when the caller does not name one: the window
#: that arrangement really serves. `everyday` is the user's own
#: OLLAMA_CONTEXT_LENGTH (16,384); `coding` is that lane's task window;
#: `pooled` is the measured three-card rung (49,152, `jarvis_big_coder.NUM_CTX`).
DEFAULT_SUITE_CTX = {"everyday": 16384, "coding": 16384, "pooled": 49152}

#: The decode floor each preset must clear before a candidate may replace it.
#: Provenance, because a floor is a measurement and not taste:
#:   * coding 75.0 - the owner's own 2026-11-07 bar for the Coding preset
#:     (`jarvis_big_coder`'s NUM_CTX comment records it);
#:   * general 40.0 - the everyday 9B's measured band on this PC is 38-43 tok/s
#:     (docs/MODEL-TOPOLOGY.md, 2026-10-30), so 40 is the bottom of the measured
#:     band rather than a wish;
#:   * tool_calling 40.0 - the routing half runs on the same lane and model as
#:     general, so it keeps the same floor;
#:   * vision_ocr 20.0 - the measured vision model read 63.35 tok/s on the
#:     headless card (docs/MEASURED-2026-11-07-THREE-GPU.md), so 20 is a floor
#:     that admits a slower vision model without admitting a crawl.
PROMOTION_DECODE_FLOOR = {"coding": 75.0, "general": 40.0,
                          "tool_calling": 40.0, "vision_ocr": 20.0}

#: The measure-first pairs the packet names. `suites` is what a promotion
#: verdict must have measured for BOTH models: the speed row is the zero-spill
#: and speed evidence, the domain suite is the quality evidence, and General
#: additionally needs tool-calling (Q2: it must pass both).
#:
#: THE CODING PAIR IS RETIRED (2026-11-09), and the receipt is why. `coding_q4`
#: named `qwen3-coder:30b-a3b-q4_K_M` as its candidate until that tag was
#: deleted on 2026-11-09 11:09 PT, and its last completed measurement is the
#: honest verdict: the shipped `qwen3-coder-30b-a3b-ud-q3-k-xl` answered at
#: 64.6-76.8 tok/s with 0 B spilled, the q4 build at 65.3 tok/s with 231.5 MiB
#: spilled (both 6/6 on the coding rubric), and the other installed challenger,
#: `gemma4:26b-a4b-it-qat` at 32,768, measured 49.26 tok/s with 4.4% (0.68 GiB)
#: spilled. So the incumbent STAYS the Coding preset's speed default - KEEP
#: CURRENT, measured rather than assumed - and a pair whose candidate cannot be
#: installed is a dead row in the packet, not a pending promotion. The models
#: stay in `docs/MEASURED-2026-11-07-THREE-GPU.md` as measured; only the pair is
#: gone. `pair_verdict("coding_q4")` now refuses it by name.
PROMOTION_PAIRS = (
    {"id": "general_12b", "preset": "general",
     "incumbent": "qwen3.5:9b",
     "candidate": "gemma4:12b-it-qat",
     "ctx": 196608, "suites": ("speed", "general", "tool_calling"),
     "why": "the 12B is a newer build than the everyday 9B; the preset's own "
            "196,608-token window is the hard part, and routing/OCR must not "
            "regress (Q2)"},
)

#: The sentences a screen shows. One constant each, so the desktop, the phone
#: and the card cannot word the same refusal three ways.
SUITE_STREAMING = ANSWER_STREAMING
SUITE_ALREADY_RUNNING = ("a benchmark is already running; it takes a minute or two")
SUITE_STANDBY = STANDBY
SUITE_TASK_RUNNING = TASK_RUNNING
SUITE_NOT_IDLE = ("a scheduled benchmark only runs while no model is loaded; "
                  "start it yourself to let it pause the lane it needs")
SUITE_LANE_DOWN = "nothing answers on port {port}, so that lane cannot be paused"
SUITE_MODEL_MISSING = "{model} is not installed on this PC. It has: {has}"
SUITE_NO_CARD = ("the graphics cards could not be read, so this run cannot pick "
                 "one to measure on")
SUITE_NOT_CONFIRMED = "nothing was measured: the run was not confirmed"
SUITE_BAD_SUITE = "{suite!r} is not one of {keys}"
SUITE_NO_PORT = ("no spare port between {first} and {last} is free, so a "
                 "throwaway server cannot be started")
SUITE_NOTHING = "nothing was measured: the run stopped before any suite ran"

#: The fixture the vision suite reads, as a PNG embedded in this file rather
#: than a file beside it: this module is shipped WHOLE to the owner's backend,
#: and a `fixtures/` folder is not. 448x112, black-on-white block capitals,
#: 791 bytes. `test_bench_suites.py` proves the base64 decodes to a real PNG
#: and that the text it was rendered from is the text the suite expects.
VISION_IMAGE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAcAAAABwAQAAAACh450fAAAC3klEQVR42u2YMW7bMBSGP9IaNASN"
    "hg7dLPQEOUCBsDfxEXqC9nXr2AN1YLYcoaMCdPCoFBnkQBY7UCKpmJbbTkUhLrJp/nz/+/m/R8HK"
    "8XdDswJX4ApcgStwBf4zwIO6AHQKUAKflSo4aEDdKvhCHZffVcsRj6YAwIAT9n7yocaZpwtUm/Bp"
    "gOcw98wxD3RY/2GPAwfQj0+w0IFZjtj7eYHOP/xoI5c5cEg4xrXjkDSDcxEHEIbpm/VpgI0bnQE6"
    "BaCAZtPPaHRZYE8L3LoWsPQAXG0CCeRalqlexR9tNWrTA9zs8sBuZKKRsHWNaQNHU/UXvdqEdJJj"
    "Pqtq6R/KH3QxxQznImUe2NIvMPjNsmppSw/YTmenzhqgeT1ETV5YxxrY/kkh/4yOW6D6NsrX0VSA"
    "cSZFBqWLGc4GxeUxTN4nJowAfc7j9N7bNQcBGPS8WOZAee8J/ZgJ9DU4LhlFJt6dQk1WoIKnZGVT"
    "LquqYUCM99IRoCtjaZ4AHSI2Q0liclItRyxm6tmRM7hgjBlwUBjvqjfgHDK26AZo6knuxYi7+MMH"
    "T9OO1bzcHjcytZzQDcR440gO2Gvq2A4/jptY7zMBaNUS1Vs7TOEA3iWOa3QW2B1V3QE3DuCbnnj3"
    "QRVbLIpTzmto50OaBznbOsIp2rT+qsQhJ/fj4+SOHtA0wPcC4CF0MGCIjUGf7AqoWD2unnf6vFeb"
    "yRsCmDFSmm6nLjjHdLMLLnY+fQq0Q7Kg7qcqVth8+eo0M7t1g4sZVy9utuzFKs2smQ5p4m0BG+fs"
    "Vmx5GrHtRx1kvEIqv43s0ziP6qTLdXvAjBYtknvp2ZmS06Y8Ac2hngkclhinL77LudCONFCGmg0q"
    "5e7HGgqQMVRyCHWqWQZYQTkkkjdpNLMALCdCZkqx8MGvkoSHDLCAXVL1Jr0j1JI4G5A+uVY6tF+v"
    "hFf5d6hxNNcuPzo+5abV+kfQClyBK3AFrsD/F/gLXX0Ysrb+K1kAAAAASUVORK5CYII="
)

#: The two tokens the image contains, lower-cased. Both must appear in the
#: model's answer (normalised) for the vision task to pass - a model that reads
#: only one of them has not read the image.
VISION_EXPECTED = ("jarvis", "42")

#: What each suite needs from the model, by name, so a run can say "not a
#: vision model" instead of scoring it zero and calling that a result. Ollama
#: reports these in `/api/show`'s `capabilities` list ("completion", "tools",
#: "vision", "thinking", "embedding").
SUITE_NEEDS_CAPABILITY = {"tool_calling": "tools", "vision_ocr": "vision"}

# ==========================================================================
#   The 6-task rubrics
# ==========================================================================
#
# EACH TASK IS FIXED. The prompt is one short sentence, the check is a machine
# check, and the check is the only thing that decides a pass - never the
# harness's opinion of the prose. The tasks are deliberately small: this rubric
# ranks two local models against each other, it is not a coding exam.

#: Six coding tasks. `tests` are (expression, expected) pairs appended to the
#: model's own code and run by a separate interpreter. The function names are
#: part of the prompt so a check is unambiguous.
CODING_TASKS = (
    {"id": "add_two",
     "prompt": ("Write a Python function called add_two(a, b) that returns the "
                "sum of a and b. Reply with only the code in one ```python "
                "block."),
     "tests": (("add_two(2, 3)", 5), ("add_two(-4, 1)", -3),
               ("add_two(0, 0)", 0))},
    {"id": "is_even",
     "prompt": ("Write a Python function called is_even(n) that returns True "
                "when n is even and False otherwise. Reply with only the code "
                "in one ```python block."),
     "tests": (("is_even(4)", True), ("is_even(7)", False),
               ("is_even(0)", True))},
    {"id": "reverse_words",
     "prompt": ("Write a Python function called reverse_words(text) that "
                "returns the words of text in reverse order, separated by "
                "single spaces. Reply with only the code in one ```python "
                "block."),
     "tests": (("reverse_words('one two three')", "three two one"),
               ("reverse_words('hello')", "hello"))},
    {"id": "max_of_three",
     "prompt": ("Write a Python function called max_of_three(a, b, c) that "
                "returns the largest of three numbers. Reply with only the "
                "code in one ```python block."),
     "tests": (("max_of_three(1, 5, 3)", 5), ("max_of_three(-2, -9, -4)", -2),
               ("max_of_three(7, 7, 2)", 7))},
    {"id": "count_vowels",
     "prompt": ("Write a Python function called count_vowels(text) that "
                "returns how many vowels (aeiou, either case) are in text. "
                "Reply with only the code in one ```python block."),
     "tests": (("count_vowels('Jarvis')", 2), ("count_vowels('xyz')", 0),
               ("count_vowels('AEIOU')", 5))},
    {"id": "factorial",
     "prompt": ("Write a Python function called factorial(n) that returns n "
                "factorial for a non-negative integer, with factorial(0) == 1. "
                "Reply with only the code in one ```python block."),
     "tests": (("factorial(0)", 1), ("factorial(5)", 120),
               ("factorial(7)", 5040))},
)

#: Six questions with one exact answer. `expected` is compared to the WHOLE
#: answer (normalised: lower-cased, surrounding punctuation and markdown
#: stripped) and to its last non-empty line, because a model that answers
#: "391" and a model that answers "The answer is\n391" have both answered the
#: question; a model that writes a paragraph has not followed "only".
GENERAL_TASKS = (
    {"id": "multiply", "prompt": "What is 17 multiplied by 23? Reply with only the number.",
     "expected": "391"},
    {"id": "leap_year", "prompt": "How many days are in a leap year? Reply with only the number.",
     "expected": "366"},
    {"id": "gold", "prompt": "What is the chemical symbol for gold? Reply with only the symbol.",
     "expected": "au"},
    {"id": "canberra", "prompt": "What is the capital city of Australia? Reply with only the city name.",
     "expected": "canberra"},
    {"id": "power", "prompt": "What is 2 to the power of 10? Reply with only the number.",
     "expected": "1024"},
    {"id": "hexagon", "prompt": "How many sides does a hexagon have? Reply with only the number.",
     "expected": "6"},
)

#: The tools the tool-calling suite offers. Small, fixed, local in meaning (the
#: model only has to CALL them; nothing here executes).
TOOL_SCHEMAS = (
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "The city name."}},
            "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "set_timer",
        "description": "Set a countdown timer.",
        "parameters": {"type": "object", "properties": {
            "minutes": {"type": "integer", "description": "How many minutes."},
            "label": {"type": "string", "description": "What the timer is for."}},
            "required": ["minutes", "label"]}}},
    {"type": "function", "function": {
        "name": "search_web",
        "description": "Search the web for a query.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for."}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file on this PC.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "The file path."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "create_note",
        "description": "Create a note with a title and a body.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"}},
            "required": ["title", "body"]}}},
)

#: Five routing tasks. `args` are exact (numbers, booleans); `args_contain` are
#: case-insensitive substrings (free text a model may word differently).
#: `forbid` is an argument the model must NOT put in: asking `search_web` for
#: "Paris" instead of `get_weather` is the failure this half exists to catch.
TOOL_TASKS = (
    {"id": "weather_paris", "prompt": "What is the weather in Paris right now?",
     "tool": "get_weather", "args": {}, "args_contain": {"city": "paris"}},
    {"id": "timer_pasta",
     "prompt": "Set a timer for 10 minutes and call it pasta.",
     "tool": "set_timer", "args": {"minutes": 10},
     "args_contain": {"label": "pasta"}},
    {"id": "search_ollama",
     "prompt": "Search the web for the latest Ollama release.",
     "tool": "search_web", "args": {}, "args_contain": {"query": "ollama"}},
    {"id": "read_notes", "prompt": "Read the file notes.txt on this PC.",
     "tool": "read_file", "args": {}, "args_contain": {"path": "notes.txt"}},
    {"id": "make_note",
     "prompt": "Create a note titled Shopping with the body Milk and eggs.",
     "tool": "create_note", "args": {},
     "args_contain": {"title": "shopping", "body": "milk"}},
)

# ==========================================================================
#   The scorecard store - its own file, its own allowlist
# ==========================================================================
#
# WHY NOT REUSE `BenchLog`. That store's rows are speed measurements of a live
# lane; its allowlist, its run ring and its tests are shaped for those. A
# suite row carries a score and a rubric ID and belongs in its own file, so an
# old bench row can never be read as a scorecard and a scorecard can never be
# read as a 300-field speed row. The privacy rule is the same and is the point:
# an ALLOWLIST, and there is deliberately no field for a prompt or an answer.

SCORE_FILE = "bench-scores.jsonl"
SCORE_SCHEMA = 1
SCORE_MAX_ROWS = 2000
SCORE_MAX_BYTES = 2 * 1024 * 1024

_SCORE_NUMBER = {
    "v", "at", "ctx", "size", "size_vram", "spill_bytes", "on_card_percent",
    "decode_tps", "prompt_tps", "cold_load_ms", "score_pct", "items",
    "items_passed", "repeats", "seconds",
}
_SCORE_BOOL = {"ok", "passed", "skipped", "promotion_grade", "spilled"}
_SCORE_NAME = {
    "run": 60, "model": 120, "digest": 80, "quant": 40, "family": 40,
    "parameter_size": 40, "cards_used": 80, "ollama_version": 40,
    "driver_version": 40, "why": MAX_REASON, "words": MAX_WORDS,
}
_SCORE_ENUM = {"kind": ("bench-suite",), "measured_on": ("this_pc",),
               "suite": SUITE_KEYS}


def _clean_score(row: dict) -> dict:
    """`_clean()`'s rule for a score row: allowed fields only, allowed shapes
    only. A prompt or an answer handed in by mistake is dropped here, not
    written and read back later."""
    out: dict = {}
    for k, v in (row or {}).items():
        if k in _SCORE_NUMBER:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if isinstance(v, float) and (v != v or v in (float("inf"),
                                                         float("-inf"))):
                continue
            out[k] = round(float(v), 2) if isinstance(v, float) else v
        elif k in _SCORE_BOOL:
            if isinstance(v, bool):
                out[k] = v
        elif k in _SCORE_ENUM:
            if isinstance(v, str) and v in _SCORE_ENUM[k]:
                out[k] = v
        elif k in _SCORE_NAME:
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()[:_SCORE_NAME[k]]
    return out


def scores_path() -> Path:
    """`~/.openjarvis/bench-scores.jsonl`, beside the speed history."""
    return _config_dir() / SCORE_FILE


class ScoreLog:
    """Append-only JSON lines for suite scorecards. Never raises.

    The store is small (a scorecard is ~15 fields) and a run writes one row per
    suite, so the row cap is a history cap, not a performance guard. A row that
    fails to parse is skipped on read rather than killing the history; a write
    that fails returns False and the run says the scorecard was not saved.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path else scores_path()

    def rows(self) -> list:
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out

    def append(self, row: dict) -> bool:
        try:
            stamped = dict(row or {})
            stamped.setdefault("kind", "bench-suite")
            stamped.setdefault("measured_on", "this_pc")
            stamped.setdefault("v", SCORE_SCHEMA)
            stamped.setdefault("at", int(time.time()))
            clean = _clean_score(stamped)
            rows = self.rows()
            rows.append(clean)
            while len(rows) > SCORE_MAX_ROWS:
                rows.pop(0)
            text = "\n".join(json.dumps(r, sort_keys=True,
                                        separators=(",", ":")) for r in rows) + "\n"
            while len(text.encode("utf-8")) > SCORE_MAX_BYTES and len(rows) > 1:
                rows.pop(0)
                text = "\n".join(json.dumps(r, sort_keys=True,
                                            separators=(",", ":"))
                                 for r in rows) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding="utf-8")
            return True
        except Exception:
            return False

    def by_run(self, run_id: str) -> list:
        return [r for r in self.rows() if str(r.get("run") or "") == run_id]

    def clear(self) -> bool:
        try:
            self.path.write_text("", encoding="utf-8")
            return True
        except OSError:
            return False


def score_history(*, limit: int = 50, model: str = "", suite: str = "",
                  store: Optional[ScoreLog] = None) -> list:
    """The scorecards, newest first, optionally filtered. Read-only."""
    rows = (store or ScoreLog()).rows()
    if model:
        rows = [r for r in rows if _same(str(r.get("model") or ""), model)]
    if suite:
        rows = [r for r in rows if r.get("suite") == suite]
    rows.sort(key=lambda r: (int(r.get("at") or 0), str(r.get("run") or "")),
              reverse=True)
    return rows[:max(1, int(limit))]


def latest_scorecards(*, store: Optional[ScoreLog] = None) -> dict:
    """The newest scorecard per (model, suite), as a dict.

    Keyed `(model, suite)`. A model name is compared case-insensitively and
    without a `:latest` suffix, so a store written on one day is not invisible
    on the next because Ollama added the suffix.
    """
    out: dict = {}
    for row in score_history(limit=100000, store=store):
        key = (_bare(str(row.get("model") or "")), str(row.get("suite") or ""))
        if key[0] and key[1] and key not in out:
            out[key] = row
    return out


def model_identity(base: str, model: str, *,
                   get: Optional[Callable[[str], dict]] = None,
                   show: Optional[Callable[[str, dict], dict]] = None) -> dict:
    """What a scorecard must carry about a model, read from Ollama itself.

    The digest and the quantisation come from `/api/tags` (the same list a
    screen shows); `/api/show` fills anything missing and is the one place that
    reports `capabilities` ("completion", "tools", "vision", ...), which the
    suite runner uses to SKIP a suite the model cannot do instead of scoring it
    zero. Every field is capped, and an unreadable field is absent rather than
    guessed - a scorecard with no digest is honest, one with a made-up digest
    is not.
    """
    out = {"model": str(model or "")[:120], "digest": "", "quant": "",
           "family": "", "parameter_size": "", "capabilities": []}
    try:
        body = (get or http_get)(f"{base}/api/tags")
        for m in (body or {}).get("models") or []:
            if not isinstance(m, dict):
                continue
            if not _same(str(m.get("name") or m.get("model") or ""), model):
                continue
            out["digest"] = str(m.get("digest") or "")[:80]
            details = m.get("details") or {}
            if isinstance(details, dict):
                out["quant"] = str(details.get("quantization_level") or "")[:40]
                out["family"] = str(details.get("family") or "")[:40]
                out["parameter_size"] = str(
                    details.get("parameter_size") or "")[:40]
            break
    except Exception:
        pass
    try:
        body = (show or http_post_json)(f"{base}/api/show", {"model": model})
        if isinstance(body, dict):
            details = body.get("details") or {}
            if isinstance(details, dict):
                out["quant"] = out["quant"] or str(
                    details.get("quantization_level") or "")[:40]
                out["family"] = out["family"] or str(
                    details.get("family") or "")[:40]
                out["parameter_size"] = out["parameter_size"] or str(
                    details.get("parameter_size") or "")[:40]
            caps = body.get("capabilities")
            if isinstance(caps, list):
                out["capabilities"] = [str(c)[:30] for c in caps
                                       if isinstance(c, str)][:8]
    except Exception:
        pass
    return out


def scorecard_row(*, run_id: str, identity: dict, lane: str, suite: dict,
                  model: str, ctx: int, result: dict, ollama_version: str = "",
                  driver: str = "", cards_used: str = "") -> dict:
    """One stored row for one suite result. The ONLY place a result becomes a
    row, so the allowlist in `_clean_score()` is exercised on one shape."""
    return {
        "kind": "bench-suite", "run": run_id,
        "model": model, "digest": identity.get("digest", ""),
        "quant": identity.get("quant", ""), "family": identity.get("family", ""),
        "parameter_size": identity.get("parameter_size", ""),
        "ctx": int(ctx), "cards_used": cards_used,
        "suite": suite["id"],
        "size": result.get("size"), "size_vram": result.get("size_vram"),
        "spill_bytes": result.get("spill_bytes"),
        "on_card_percent": result.get("on_card_percent"),
        "decode_tps": result.get("decode_tps"),
        "prompt_tps": result.get("prompt_tps"),
        "cold_load_ms": result.get("cold_load_ms"),
        "score_pct": result.get("score_pct"),
        "items": result.get("items"), "items_passed": result.get("items_passed"),
        "repeats": result.get("repeats"),
        "seconds": result.get("seconds"),
        "ok": bool(result.get("ok")), "passed": bool(result.get("passed")),
        "skipped": bool(result.get("skipped")),
        "promotion_grade": bool(result.get("promotion_grade")),
        "spilled": bool(result.get("spilled")),
        "why": str(result.get("why") or "")[:MAX_REASON],
        "words": str(result.get("words") or "")[:MAX_WORDS],
        "ollama_version": ollama_version, "driver_version": driver,
        "measured_on": "this_pc",
    }


# ==========================================================================
#   The throwaway server: this PC's Ollama, on a spare port, pinned by UUID
# ==========================================================================
#
# WHY BY UUID. Ollama's own device numbering is the reverse of nvidia-smi's on
# this PC (`start-lane.ps1` records the trap), so an index is a coin flip
# between two cards. Every pin here is the `uuid` nvidia-smi printed.

def _cards_now(smi: Optional[Callable[[], str]] = None) -> list:
    """The card rows, or []. Never raises - a benchmark that dies because
    nvidia-smi hiccuped once is worse than one with a missing number."""
    return read_cards(smi).get("cards") or []


def _is_monitor(card: dict) -> bool:
    return str(card.get("display_active") or "").strip().lower().startswith("en")


def card_choice(lane: str, *, smi: Optional[Callable[[], str]] = None) -> dict:
    """Which card set a suite run measures on, from nvidia-smi, never from a
    hard-coded index.

    Options in plain words:
      * "everyday" - the card WITHOUT the monitor, because measuring there does
        not stutter the desktop (the shipped speed bench's own reason);
      * "coding"   - the card WITH the monitor, which is the fast card this
        PC's second lane already uses;
      * "pooled"   - every card, no `CUDA_VISIBLE_DEVICES` at all, because the
        pooled lane's whole point is the sum of the cards.

    Returns {"ok", "why", "kind", "uuid", "name", "indexes"}. A PC that cannot
    be read gets ok False and ONE sentence, never a guessed card.
    """
    cards = [c for c in _cards_now(smi)
             if isinstance(c.get("total_mb"), (int, float))
             and c.get("total_mb") and c.get("uuid")]
    if not cards:
        return {"ok": False, "why": SUITE_NO_CARD, "kind": "", "uuid": "",
                "name": "", "indexes": []}
    if lane == "pooled":
        return {"ok": True, "why": "", "kind": "pool", "uuid": "",
                "name": "all cards",
                "indexes": [int(c["index"]) for c in cards]}
    monitors = [c for c in cards if _is_monitor(c)]
    if lane == "coding":
        chosen = (monitors or sorted(cards, key=lambda c: c["total_mb"],
                                     reverse=True))[0]
    else:
        plain = [c for c in cards if not _is_monitor(c)] or cards
        chosen = sorted(plain, key=lambda c: c["total_mb"], reverse=True)[0]
    return {"ok": True, "why": "", "kind": "one", "uuid": str(chosen["uuid"]),
            "name": str(chosen.get("name") or "a graphics card"),
            "indexes": [int(chosen["index"])]}


def throwaway_env(port: int, choice: dict, ctx: Optional[int]) -> dict:
    """The environment the throwaway `ollama serve` gets.

    Same discipline as `jarvis_big_coder._child_env()`: `jarvis_child_env`'s
    allowlist when it is beside this module (so no token or key of the owner's
    is inherited), the model folder, loopback only, one model, one request at a
    time, kv cache q8_0 (the format every measurement and live lane uses), and
    `OLLAMA_VULKAN=0` - without it a CUDA_VISIBLE_DEVICES pin silently falls back
    to Vulkan on another card (measured 2026-10-10, `start-lane.ps1`'s header).
    """
    try:
        import jarvis_child_env  # type: ignore
        env = jarvis_child_env.inherited(names=("OLLAMA_MODELS",))
    except Exception:
        # The same narrow fallback shape `_child_env()` uses: never the parent's
        # whole environment, so a token or key of the owner's cannot ride along.
        env = {}
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME",
                     "USERPROFILE", "LOCALAPPDATA", "OLLAMA_MODELS"):
            if os.environ.get(name):
                env[name] = os.environ[name]
    for name in ("CUDA_VISIBLE_DEVICES", "GGML_VK_VISIBLE_DEVICES"):
        env.pop(name, None)
    if choice.get("kind") == "one" and choice.get("uuid"):
        env["CUDA_VISIBLE_DEVICES"] = str(choice["uuid"])
    env["OLLAMA_VULKAN"] = "0"
    env["OLLAMA_NO_CLOUD"] = "1"
    env["OLLAMA_HOST"] = f"127.0.0.1:{int(port)}"
    env["OLLAMA_KEEP_ALIVE"] = "-1"
    env["OLLAMA_NUM_PARALLEL"] = "1"
    env["OLLAMA_MAX_LOADED_MODELS"] = "1"
    env["OLLAMA_KV_CACHE_TYPE"] = "q8_0"
    if ctx:
        env["OLLAMA_CONTEXT_LENGTH"] = str(int(ctx))
    return env


def _port_busy(port: int, *, get: Optional[Callable[[str], dict]] = None) -> bool:
    """Is something already answering on this port? One loopback GET."""
    try:
        (get or http_get)(f"http://127.0.0.1:{int(port)}/api/version")
        return True
    except Exception:
        return False


def pick_port(*, get: Optional[Callable[[str], dict]] = None,
              first: int = BENCH_PORT_FIRST,
              last: int = BENCH_PORT_LAST) -> Optional[int]:
    """The first free port in the throwaway range. Never a lane port:
    `LANE_PORTS` is checked both ways, so a caller that edits the range cannot
    hand a suite the server a live lane is using."""
    live = set(int(p) for p in LANE_PORTS.values())
    for port in range(int(first), int(last) + 1):
        if port in live or port in (11434, 11439):
            continue
        if not _port_busy(port, get=get):
            return port
    return None


def _kill_tree(proc) -> None:
    """Take the whole process tree down. On Windows a plain terminate can leave
    `llama-server.exe` behind holding the cards; `taskkill /T` is the shipped,
    documented way to end it. Never raises."""
    pid = getattr(proc, "pid", None)
    try:
        if os.name == "nt" and pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True, timeout=20,
                           shell=False, env=_child_env())
    except Exception:
        pass
    for method in ("terminate", "kill"):
        try:
            getattr(proc, method)()
            break
        except Exception:
            continue
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def start_throwaway(*, choice: dict, ctx: Optional[int] = None,
                    port: Optional[int] = None,
                    spawn: Optional[Callable] = None,
                    get: Optional[Callable[[str], dict]] = None,
                    clock: Optional[Callable[[], float]] = None,
                    wait_s: float = 45.0) -> dict:
    """Start ONE `ollama serve` for this run. {"ok","why","url","port","proc","owned"}.

    It is started on a port the caller never had to choose, with the card pin
    in its environment, and it is the only Ollama a suite run talks to. If a
    server is already answering on the chosen port it is REUSED and `owned` is
    False - the same rule `jarvis_big_coder.server_start` follows - so a
    previous run's leftover is not doubled.
    """
    chosen_port = int(port) if port else pick_port(get=get)
    if not chosen_port:
        return {"ok": False, "why": SUITE_NO_PORT.format(first=BENCH_PORT_FIRST,
                                                         last=BENCH_PORT_LAST),
                "url": "", "port": None, "proc": None, "owned": False}
    if chosen_port in set(int(p) for p in LANE_PORTS.values()):
        return {"ok": False, "why": (f"port {chosen_port} is a live lane's, and a "
                                     "suite run never measures a live lane"),
                "url": "", "port": None, "proc": None, "owned": False}
    url = f"http://127.0.0.1:{chosen_port}"
    try:
        (get or http_get)(f"{url}/api/version")
        return {"ok": True, "why": "", "url": url, "port": chosen_port,
                "proc": None, "owned": False}
    except Exception:
        pass
    env = throwaway_env(chosen_port, choice, ctx)
    runner = spawn or (lambda environment: subprocess.Popen(
        ["ollama", "serve"], env=environment, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
    try:
        proc = runner(env)
    except Exception as exc:
        return {"ok": False,
                "why": f"could not start the throwaway Ollama ({type(exc).__name__})",
                "url": "", "port": None, "proc": None, "owned": False}
    now = clock or time.monotonic
    deadline = now() + float(wait_s)
    while now() < deadline:
        try:
            (get or http_get)(f"{url}/api/tags")
            return {"ok": True, "why": "", "url": url, "port": chosen_port,
                    "proc": proc, "owned": True}
        except Exception:
            if getattr(proc, "poll", lambda: None)() is not None:
                return {"ok": False,
                        "why": "the throwaway Ollama stopped as soon as it started",
                        "url": "", "port": None, "proc": None, "owned": False}
            time.sleep(0.25)
    _kill_tree(proc)
    return {"ok": False,
            "why": "the throwaway Ollama did not answer within 45 seconds",
            "url": "", "port": None, "proc": None, "owned": False}


def stop_throwaway(handle: dict, *, kill: Optional[Callable] = None) -> dict:
    """Stop the server this run started. A server it did not start is left
    alone; a suite run must never kill a lane."""
    proc = (handle or {}).get("proc")
    if proc is None:
        return {"stopped": False, "why": ""}
    try:
        (kill or _kill_tree)(proc)
    except Exception as exc:
        return {"stopped": False,
                "why": f"the throwaway Ollama could not be stopped ({type(exc).__name__})"}
    return {"stopped": True, "why": ""}


# ==========================================================================
#   Pausing the live lane (owner-initiated only) and warming it back
# ==========================================================================
#
# Q3's two halves, in code. The pause is only ever entered by an OWNER run: a
# scheduled run is refused before this is reached. The warm-back is in a
# `finally`, so a suite that raises still puts the owner's model back.

def _ps_row(rows: Optional[list], model: str) -> Optional[dict]:
    for m in rows or ():
        if _same(str(m.get("name") or m.get("model") or ""), model):
            return m
    return None


def pause_for_run(lane: str, *, get: Optional[Callable[[str], dict]] = None,
                  post: Optional[Callable] = None,
                  clock: Optional[Callable[[], float]] = None) -> dict:
    """Unload whatever is resident on the ports this run's cards are behind.

    Returns {"paused": [{"port","model","ctx","note"}], "words"}. A lane that
    does not answer is not a refusal here: the throwaway server has its own
    model store and does not need the lane up. What matters is that no OTHER
    model is left holding the cards.
    """
    paused: list = []
    post = post or http_post_json
    for port in EVICT_PORTS.get(lane, ()):
        base = f"http://127.0.0.1:{int(port)}"
        held = ps_models(base, get=get) or []
        for m in held:
            name = str(m.get("name") or m.get("model") or "")
            if not name:
                continue
            ctx = _int(m.get("context_length"))
            note = _unload(name, base, post=post)
            paused.append({"port": int(port), "model": name, "ctx": ctx,
                           "note": note})
    words = ""
    if paused:
        words = ("Paused for the run: "
                 + "; ".join(f"{p['model']} on port {p['port']}" for p in paused)
                 + ". It is warmed back when the run ends.")
    return {"paused": paused, "words": words}


def warm_back(paused: list, *, get: Optional[Callable[[str], dict]] = None,
              post: Optional[Callable] = None,
              clock: Optional[Callable[[], float]] = None,
              wait_s: float = 120.0) -> dict:
    """Load each paused model back at its own window and PROVE it from
    /api/ps. {"ok","restored","wrong","proof"}.

    A model that does not come back is named, and `ok` is False - a run that
    claims to have restored a lane it did not is worse than one that admits it.
    """
    post = post or http_post_json
    now = clock or time.monotonic
    restored, wrong, proof = [], [], []
    for item in paused or ():
        base = f"http://127.0.0.1:{int(item.get('port') or 0)}"
        model = str(item.get("model") or "")
        ctx = _int(item.get("ctx"))
        if not model:
            continue
        payload = {"model": model, "prompt": "", "stream": False,
                   "keep_alive": -1,
                   "options": {"num_ctx": int(ctx)} if ctx else {}}
        try:
            post(f"{base}/api/generate", payload)
        except Exception as exc:
            wrong.append(f"{model} could not be loaded back ({type(exc).__name__})")
            proof.append(f"port {item.get('port')}: {model} was NOT reloaded")
            continue
        seen = None
        deadline = now() + float(wait_s)
        while now() < deadline:
            rows = ps_models(base, get=get)
            seen = _ps_row(rows, model)
            if seen is not None:
                break
            time.sleep(0.25)
        if seen is None:
            wrong.append(f"{model} is not loaded again on port {item.get('port')}")
            proof.append(f"port {item.get('port')}: {model} did NOT come back")
            continue
        got_ctx = _int(seen.get("context_length"))
        proof.append(f"port {item.get('port')}: {model} ctx={got_ctx} "
                     f"(intended {ctx}) size={seen.get('size')} "
                     f"size_vram={seen.get('size_vram')}")
        if ctx and got_ctx and int(got_ctx) != int(ctx):
            wrong.append(f"{model} came back at {got_ctx}, not {ctx}, on port "
                         f"{item.get('port')}")
        restored.append(f"{model} @{item.get('port')}")
    why = ""
    if wrong:
        why = ("the paused model was not put back exactly as it was: "
               + "; ".join(wrong))
    return {"ok": not wrong, "restored": restored, "wrong": wrong, "why": why,
            "proof": proof}


# ==========================================================================
#   One request, and the five suite runners
# ==========================================================================

def _generate(base: str, model: str, prompt: str, *, ctx: Optional[int],
              num_predict: int = 128, post: Optional[Callable] = None,
              tools: Optional[list] = None, image_b64: str = "",
              timeout: float = 300.0) -> dict:
    """ONE question to the throwaway server, answered whole.

    A tool-calling or vision task goes to `/api/chat` (the only endpoint that
    takes `tools` and `messages[].images`); everything else goes to
    `/api/generate`. `stream: False` on purpose: a suite needs the text AND the
    counters, and the shipped speed bench already owns the streaming
    time-to-first-token path.
    """
    options = {"temperature": 0, "num_predict": int(num_predict)}
    if ctx:
        options["num_ctx"] = int(ctx)
    if tools or image_b64:
        message = {"role": "user", "content": prompt}
        if image_b64:
            message["images"] = [image_b64]
        payload = {"model": model, "messages": [message], "stream": False,
                   "options": options}
        if tools:
            payload["tools"] = tools
        return (post or http_post_json)(f"{base}/api/chat", payload, timeout)
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": options}
    return (post or http_post_json)(f"{base}/api/generate", payload, timeout)


def _answer_text(reply: dict) -> str:
    """The answer text out of either endpoint's reply. "" when absent."""
    if not isinstance(reply, dict):
        return ""
    text = reply.get("response")
    if not isinstance(text, str):
        msg = reply.get("message")
        text = (msg or {}).get("content") if isinstance(msg, dict) else ""
    return text if isinstance(text, str) else ""


def _rate(count, duration_ns) -> Optional[float]:
    """tokens a second from one reply, or None - absent is never zero."""
    c, d = _int(count), _int(duration_ns)
    if not c or not d or d <= 0:
        return None
    return round(c * 1e9 / d, 2)


def _sentence(parts: list) -> str:
    return "; ".join(p for p in parts if p)


def run_speed_suite(base: str, model: str, ctx: Optional[int], *,
                    post: Optional[Callable] = None,
                    get: Optional[Callable[[str], dict]] = None,
                    smi: Optional[Callable[[], str]] = None,
                    clock: Optional[Callable[[], float]] = None,
                    repeats: int = 3, prefill_tokens: int = 512,
                    num_predict: int = 128) -> dict:
    """The Speed suite: what the model does on ONE card at ONE window.

    Three repeats, a FRESH prompt each time (so prompt speed is measured, not
    read from Ollama's cache - the prefill trap this module's docstring is
    largely about), and a zero-spill requirement: a run is only
    `promotion_grade` when `/api/ps` says `size == size_vram` (100% on the
    card). `ollama ps`'s own `PROCESSOR 100% GPU` is NOT used as that proof.
    """
    started = (clock or time.monotonic)()
    cards_before = _cards_now(smi)
    samples = [cards_before]
    replies, gen_rates, prefill_rates = [], [], []
    first_load_ms = None
    last_ps = None
    for i in range(max(1, int(repeats))):
        prompt = prefill_prompt(int(prefill_tokens), tag=f"suite-{i}")
        try:
            reply = _generate(base, model, prompt, ctx=ctx,
                              num_predict=num_predict, post=post)
        except Exception as exc:
            if i == 0:
                return {"ok": False, "passed": False, "skipped": False,
                        "why": f"the model did not answer ({type(exc).__name__})",
                        "words": (f"Nothing was measured: {model} did not answer "
                                  f"({type(exc).__name__}).")}
            break
        replies.append(reply)
        gen = _rate(reply.get("eval_count"), reply.get("eval_duration"))
        if gen is not None:
            gen_rates.append(gen)
        pre = prefill_rate(reply.get("prompt_eval_count"),
                           reply.get("prompt_eval_cached_count"),
                           reply.get("prompt_eval_duration"))
        rate = pre[0] if isinstance(pre, tuple) else pre
        if rate is not None:
            prefill_rates.append(float(rate))
        if i == 0:
            first_load_ms = round(float(reply.get("load_duration") or 0) / 1e6, 1)
        samples.append(_cards_now(smi))
        last_ps = _ps_row(ps_models(base, get=get), model)
    seconds = round((clock or time.monotonic)() - started, 1)
    peaks = peak_cards(samples)
    peak0 = max((c.get("used_mb") or 0) for c in peaks) if peaks else None
    size = _int((last_ps or {}).get("size"))
    size_vram = _int((last_ps or {}).get("size_vram"))
    spill = (size - size_vram) if (size is not None and size_vram is not None) else None
    pct = on_card_percent(model, [last_ps] if last_ps else [])
    decode = _median(gen_rates[1:] or gen_rates)
    prompt_tps = _median(prefill_rates[1:] or prefill_rates)
    if last_ps is None:
        ok = False
        why = ("the model was not in /api/ps after the repeats, so its video "
               "memory could not be measured")
    else:
        ok = decode is not None
        why = "" if ok else "the replies carried no generation timings"
    # A grade requires the whole chain: a measured decode, a measured load, and
    # that /api/ps says 100% of it is on the card. A run whose timings are
    # missing is NOT "promotion-grade at 0 B spilled" just because the memory
    # line was readable.
    grade = bool(ok and spill == 0 and pct == 100)
    words = _sentence([
        f"{model} at {int(ctx):,} tokens" if ctx else model,
        f"{decode:.1f} tokens a second decode" if decode is not None else "",
        f"{prompt_tps:.0f} tokens a second prompt" if prompt_tps else "",
        f"cold load {first_load_ms / 1000:.1f} s" if first_load_ms else
        f"cold load {first_load_ms:.0f} ms" if first_load_ms else "",
        (f"{size / 1024 ** 3:.2f} GiB loaded, "
         f"{spill / 1024 ** 2:.0f} MiB not on the card"
         if size is not None and spill else
         f"{size / 1024 ** 3:.2f} GiB loaded, all of it on the card"
         if size is not None else ""),
        "promotion-grade" if grade else ("SPILLED - not promotion-grade"
                                         if spill else "not proved on-card"),
    ]) + "."
    return {"ok": bool(ok), "passed": bool(ok and grade), "skipped": False,
            "why": why, "words": words, "decode_tps": decode,
            "prompt_tps": prompt_tps, "cold_load_ms": first_load_ms,
            "size": size, "size_vram": size_vram, "spill_bytes": spill,
            "on_card_percent": pct, "repeats": len(replies),
            "seconds": seconds, "vram_peak_mb": peak0,
            "promotion_grade": grade, "spilled": bool(spill)}


#: A fenced python block, with or without the language tag.
_CODE_FENCE = None


def extract_python(answer: str) -> str:
    """The code out of a model's answer: the first ```python block, or the
    first ``` block, or a bare `def ...` run. "" when there is no code - and an
    empty string is a failed task, never a crash."""
    global _CODE_FENCE
    import re
    if _CODE_FENCE is None:
        _CODE_FENCE = re.compile(
            r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)
    text = str(answer or "")
    m = _CODE_FENCE.search(text)
    if m:
        return m.group(1).strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("def ", "class ")):
            return "\n".join(lines[i:]).strip()
    return ""


def coding_test_script(code: str, tests) -> str:
    """The model's code plus its asserts, as one script for a separate
    interpreter. `print()` at the end is the only pass signal."""
    asserts = "\n".join(f"assert ({expr}) == ({expected!r})"
                        for expr, expected in tests or ())
    return (str(code or "") + "\n\n" + asserts +
            "\nprint('JARVIS-BENCH-OK')\n")


def run_coding_answer(answer: str, task: dict, *,
                      code_runner: Optional[Callable] = None) -> tuple:
    """(passed, why) for one coding task. The code runs in a separate `-I`
    interpreter with a timeout and an allowlisted environment - a guard
    against a runaway answer, not a sandbox against hostile code (see the
    section comment)."""
    code = extract_python(answer)
    if not code.strip():
        return False, "the answer contained no code"
    script = coding_test_script(code, task.get("tests"))
    if code_runner is not None:
        return code_runner(script)
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
    for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
                 "LOCALAPPDATA"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-bench-") as tmp:
            proc = subprocess.run([sys.executable, "-I", "-c", script],
                                  cwd=tmp, env=env, capture_output=True,
                                  text=True, timeout=20, shell=False)
    except subprocess.TimeoutExpired:
        return False, "the test did not finish within 20 seconds"
    except OSError as exc:
        return False, f"the test could not be run ({type(exc).__name__})"
    if proc.returncode == 0 and "JARVIS-BENCH-OK" in (proc.stdout or ""):
        return True, ""
    tail = ((proc.stderr or proc.stdout or "").strip().splitlines() or [""])[-1]
    return False, tail[:MAX_REASON] or "the test failed"


def run_coding_suite(base: str, model: str, ctx: Optional[int], *,
                     post: Optional[Callable] = None,
                     code_runner: Optional[Callable] = None) -> dict:
    """Six fixed coding tasks, each checked by running its own test."""
    passed, per_item, failures = 0, [], []
    answered = 0
    for task in CODING_TASKS:
        try:
            reply = _generate(base, model, task["prompt"], ctx=ctx,
                              num_predict=400, post=post)
            answered += 1
            ok, why = run_coding_answer(_answer_text(reply), task,
                                        code_runner=code_runner)
        except Exception as exc:
            ok, why = False, f"the model did not answer ({type(exc).__name__})"
        per_item.append({"id": task["id"], "pass": bool(ok), "why": why})
        if ok:
            passed += 1
        else:
            failures.append(f"{task['id']}: {why}")
    if not answered:
        return {"ok": False, "passed": False, "skipped": False,
                "why": "the model did not answer any coding task",
                "words": (f"Nothing was measured: {model} did not answer any of "
                          "the six coding tasks.")}
    score = round(100.0 * passed / len(CODING_TASKS), 1)
    return {"ok": True, "passed": passed == len(CODING_TASKS), "skipped": False,
            "why": ("Every coding task passed." if not failures else
                    "Failed: " + "; ".join(failures))[:MAX_REASON],
            "words": (f"{passed} of {len(CODING_TASKS)} coding tasks passed "
                      f"({score:.0f}%)."),
            "items": len(CODING_TASKS), "items_passed": passed,
            "score_pct": score, "per_item": per_item}


def _normalised_answer(text: str) -> str:
    """Lower case, no markdown, no surrounding punctuation, one line."""
    import re
    t = str(text or "").strip().lower()
    t = t.replace("**", "").replace("`", "")
    t = re.sub(r"\s+", " ", t)
    return t.strip(" \t\r\n.,;:!?\"'()[]{}")


def general_answer_passes(answer: str, expected: str) -> bool:
    """Exact-answer check: the WHOLE answer, or its last non-empty line.

    The last-line rule is not leniency: "The answer is\\n391" HAS answered the
    question, while a paragraph of reasoning has not followed "reply with only".
    Both are judged against the same normalisation.
    """
    want = _normalised_answer(expected)
    whole = _normalised_answer(answer)
    if whole == want:
        return True
    lines = [ln for ln in str(answer or "").splitlines() if ln.strip()]
    return bool(lines) and _normalised_answer(lines[-1]) == want


def run_general_suite(base: str, model: str, ctx: Optional[int], *,
                      post: Optional[Callable] = None) -> dict:
    """Six questions with one exact answer."""
    passed, per_item, failures = 0, [], []
    answered = 0
    for task in GENERAL_TASKS:
        try:
            reply = _generate(base, model, task["prompt"], ctx=ctx,
                              num_predict=64, post=post)
            answered += 1
            text = _answer_text(reply)
            ok = general_answer_passes(text, task["expected"])
            why = "" if ok else f"answered {_normalised_answer(text)[:60]!r}"
        except Exception as exc:
            ok, why = False, f"the model did not answer ({type(exc).__name__})"
        per_item.append({"id": task["id"], "pass": bool(ok), "why": why})
        if ok:
            passed += 1
        else:
            failures.append(f"{task['id']}: {why}")
    if not answered:
        return {"ok": False, "passed": False, "skipped": False,
                "why": "the model did not answer any general question",
                "words": (f"Nothing was measured: {model} did not answer any of "
                          "the six general questions.")}
    score = round(100.0 * passed / len(GENERAL_TASKS), 1)
    return {"ok": True, "passed": passed == len(GENERAL_TASKS), "skipped": False,
            "why": ("Every general question was answered exactly." if not failures
                    else "Failed: " + "; ".join(failures))[:MAX_REASON],
            "words": f"{passed} of {len(GENERAL_TASKS)} exact-answer questions "
                     f"passed ({score:.0f}%).",
            "items": len(GENERAL_TASKS), "items_passed": passed,
            "score_pct": score, "per_item": per_item}


def _tool_calls(reply: dict) -> list:
    msg = (reply or {}).get("message") if isinstance(reply, dict) else None
    calls = (msg or {}).get("tool_calls") if isinstance(msg, dict) else None
    if calls is None and isinstance(reply, dict):
        calls = reply.get("tool_calls")
    return [c for c in (calls or []) if isinstance(c, dict)]


def _call_arguments(call: dict) -> dict:
    fn = call.get("function") if isinstance(call, dict) else None
    args = (fn or {}).get("arguments") if isinstance(fn, dict) else None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return {}
    return args if isinstance(args, dict) else {}


def tool_call_passes(reply: dict, task: dict) -> tuple:
    """(passed, why): a call to the RIGHT tool whose arguments match.

    Exact arguments (numbers, booleans) must be equal; free text is a
    case-insensitive substring, because "Paris" and "paris, France" are the
    same intent and the rubric is about routing, not wording.
    """
    name_wanted = task.get("tool")
    for call in _tool_calls(reply):
        fn = call.get("function") if isinstance(call, dict) else {}
        if not isinstance(fn, dict) or fn.get("name") != name_wanted:
            continue
        args = _call_arguments(call)
        bad = []
        for key, want in (task.get("args") or {}).items():
            if args.get(key) != want:
                bad.append(f"{key}={args.get(key)!r} (wanted {want!r})")
        for key, want in (task.get("args_contain") or {}).items():
            got = args.get(key)
            if not isinstance(got, str) or str(want).lower() not in got.lower():
                bad.append(f"{key}={got!r} (wanted it to mention {want!r})")
        if not bad:
            return True, ""
        return False, f"called {name_wanted} with " + ", ".join(bad)
    names = [((c.get("function") or {}).get("name")) for c in _tool_calls(reply)]
    return False, (f"called {names!r}, not {name_wanted}" if names
                   else f"did not call {name_wanted}")


def run_tool_calling_suite(base: str, model: str, ctx: Optional[int], *,
                           post: Optional[Callable] = None) -> dict:
    """Five fixed routing tasks, scored on the right tool and its arguments."""
    passed, per_item, failures = 0, [], []
    answered = 0
    for task in TOOL_TASKS:
        try:
            reply = _generate(base, model, task["prompt"], ctx=ctx,
                              num_predict=64, post=post, tools=list(TOOL_SCHEMAS))
            answered += 1
            ok, why = tool_call_passes(reply, task)
        except Exception as exc:
            ok, why = False, f"the model did not answer ({type(exc).__name__})"
        per_item.append({"id": task["id"], "pass": bool(ok), "why": why})
        if ok:
            passed += 1
        else:
            failures.append(f"{task['id']}: {why}")
    if not answered:
        return {"ok": False, "passed": False, "skipped": False,
                "why": "the model did not answer any tool-calling task",
                "words": (f"Nothing was measured: {model} did not answer any of "
                          "the five tool-calling tasks.")}
    score = round(100.0 * passed / len(TOOL_TASKS), 1)
    return {"ok": True, "passed": passed == len(TOOL_TASKS), "skipped": False,
            "why": ("Every tool task called the right tool with the right "
                    "arguments." if not failures else
                    "Failed: " + "; ".join(failures))[:MAX_REASON],
            "words": (f"{passed} of {len(TOOL_TASKS)} tool-calling tasks passed "
                      f"({score:.0f}%)."),
            "items": len(TOOL_TASKS), "items_passed": passed,
            "score_pct": score, "per_item": per_item}


def vision_answer_passes(answer: str, expected=VISION_EXPECTED) -> bool:
    """Both tokens the image contains must appear in the answer. One token
    means the model read a word and guessed the rest - not OCR."""
    norm = _normalised_answer(answer)
    return all(str(want).lower() in norm for want in (expected or ()))


def run_vision_suite(base: str, model: str, ctx: Optional[int], *,
                     post: Optional[Callable] = None) -> dict:
    """Read ONE image and check both words in it. The image is embedded in
    this file as base64 (this module is shipped whole; a `fixtures/` folder is
    not shipped with it) and decodes to a 448x112 PNG reading "JARVIS 42"."""
    prompt = ("Read the text in this image. Reply with only the text you can "
              "see, nothing else.")
    try:
        reply = _generate(base, model, prompt, ctx=ctx, num_predict=48,
                          post=post, image_b64=VISION_IMAGE_PNG_B64)
    except Exception as exc:
        return {"ok": False, "passed": False, "skipped": False,
                "why": f"the model did not answer ({type(exc).__name__})",
                "words": (f"Nothing was measured: {model} did not answer the "
                          f"image question ({type(exc).__name__}).")}
    text = _answer_text(reply)
    ok = vision_answer_passes(text)
    return {"ok": True, "passed": ok, "skipped": False,
            "why": "" if ok else f"read {_normalised_answer(text)[:80]!r}",
            "words": ("The image text was read correctly."
                      if ok else "The image text was NOT read correctly."),
            "items": 1, "items_passed": 1 if ok else 0,
            "score_pct": 100.0 if ok else 0.0,
            "per_item": [{"id": "ocr", "pass": bool(ok),
                          "why": "" if ok else "wrong text"}]}


#: Which runner answers which suite ID. One table, so a suite can never be
#: added to `SUITES` and silently never run.
SUITE_RUNNERS = {
    "speed": run_speed_suite,
    "coding": run_coding_suite,
    "general": run_general_suite,
    "tool_calling": run_tool_calling_suite,
    "vision_ocr": run_vision_suite,
}


def run_one_suite(suite_id: str, base: str, model: str, ctx: Optional[int], *,
                  identity: Optional[dict] = None,
                  post: Optional[Callable] = None,
                  get: Optional[Callable[[str], dict]] = None,
                  smi: Optional[Callable[[], str]] = None,
                  clock: Optional[Callable[[], float]] = None,
                  code_runner: Optional[Callable] = None) -> dict:
    """Run one suite, with the capability gate and one never-a-fake-score rule.

    A suite whose capability the model does NOT report is `skipped`, with the
    reason in words, and `passed` is False: BLOCKED is never a pass in this
    project. A suite that raises is `ok: False` with the exception named - never
    a zero that would look like a measured result.
    """
    suite = next((s for s in SUITES if s["id"] == suite_id), None)
    if suite is None:
        return {"suite": suite_id, "ok": False, "passed": False,
                "skipped": False,
                "why": SUITE_BAD_SUITE.format(suite=suite_id, keys=SUITE_KEYS),
                "words": "Nothing was measured: that is not one of the suites."}
    needed = SUITE_NEEDS_CAPABILITY.get(suite_id)
    caps = [str(c).lower() for c in ((identity or {}).get("capabilities") or [])]
    if needed and caps and needed not in caps:
        return {"suite": suite_id, "ok": True, "passed": False, "skipped": True,
                "why": (f"{model} does not report {needed} support, so the "
                        f"{suite['label']} suite was NOT attempted"),
                "words": (f"{suite['label']}: not run - the model does not "
                          f"report {needed} support.")}
    runner = SUITE_RUNNERS[suite_id]
    kwargs = {"post": post}
    if suite_id == "speed":
        kwargs.update({"get": get, "smi": smi, "clock": clock})
    if suite_id == "coding":
        kwargs.update({"code_runner": code_runner})
    try:
        result = runner(base, model, ctx, **kwargs)
    except Exception as exc:
        result = {"ok": False, "passed": False, "skipped": False,
                  "why": f"the {suite['label']} suite raised "
                         f"{type(exc).__name__}",
                  "words": (f"The {suite['label']} suite stopped with "
                            f"{type(exc).__name__}; nothing is claimed.")}
    result.setdefault("skipped", False)
    result["suite"] = suite_id
    return result


# ==========================================================================
#   Starting a suite run: refusals in order, then the work
# ==========================================================================
#
# THE ORDER IS THE RULING'S (Q3), then this module's existing safety rows:
#   1. a run is already going;
#   2. an owner run refuses for ONE busy reason only - a chat/voice turn that is
#      STREAMING right now (a scheduled run also refuses while anything at all
#      is using the model, because it may not evict);
#   3. standby, which exists to keep the cards free (both modes);
#   4. a multi-step task running (both modes: pausing lanes under a task breaks
#      it);
#   5. a scheduled run needs the PC idle: no model loaded on any lane;
#   6. the POST must carry `confirm`, so a stale screen cannot start a run
#      nobody agreed to.

def suite_choices(body: dict) -> tuple:
    """(lane, suites, ctx, mode, notes) from a POST body - validated, never
    guessed. Raises nothing; the caller refuses on an empty suites list."""
    body = body if isinstance(body, dict) else {}
    lane = str(body.get("lane") or "everyday").strip().lower()
    if lane not in LANE_KEYS:
        lane = "everyday"
    wanted = body.get("suites")
    if not isinstance(wanted, (list, tuple)) or not wanted:
        suites = list(SUITE_KEYS)
    else:
        suites = [str(s).strip().lower() for s in wanted]
    mode = str(body.get("mode") or "owner").strip().lower()
    if mode not in ("owner", "scheduled"):
        mode = "owner"
    ctx = _int(body.get("num_ctx")) or DEFAULT_SUITE_CTX.get(lane, 16384)
    notes = []
    if ctx < 2048:
        ctx = 2048
        notes.append("num_ctx below 2,048 was raised to 2,048")
    return lane, suites, int(ctx), mode, notes


def _any_model_loaded(*, get: Optional[Callable[[str], dict]] = None) -> list:
    """Every model resident on any lane, with its port. Read-only."""
    found = []
    for lane, port in LANE_PORTS.items():
        rows = ps_models(f"http://127.0.0.1:{int(port)}", get=get)
        for row in rows or []:
            name = str(row.get("name") or row.get("model") or "")
            if name:
                found.append((lane, int(port), name))
    return found


def check_suite_job(body: dict, *, mode: str = "owner",
                    get: Optional[Callable[[str], dict]] = None,
                    busy: Optional[Callable[[], Optional[str]]] = None,
                    standby: Optional[Callable[[], bool]] = None,
                    tasks: Optional[Callable[[], list]] = None,
                    running: Optional[Callable[[], Optional[str]]] = None) -> None:
    """Raise `Refusal` when this POST must not start a suite run."""
    body = body if isinstance(body, dict) else {}

    # 1. the same one-benchmark-at-a-time lock the speed bench uses.
    if (running or _current_run)() is not None:
        raise Refusal(409, SUITE_ALREADY_RUNNING)

    # 2. the ruling's ONE busy refusal for an owner run: a turn streaming now.
    if busy is not None:
        sentence = busy()
    elif mode == "owner":
        sentence = answer_streaming()
    else:
        sentence = (_answer_hold() or {}).get("sentence")
    if sentence:
        raise Refusal(409, sentence)

    # 3. standby keeps the cards free on purpose.
    if (standby or read_standby)():
        raise Refusal(409, SUITE_STANDBY)

    # 4. a multi-step task continues between turns and would lose its model.
    if (tasks or running_tasks)():
        raise Refusal(409, SUITE_TASK_RUNNING)

    # 5. a scheduled run may not evict, so it only runs when nothing is loaded.
    if mode == "scheduled":
        held = _any_model_loaded(get=get)
        if held:
            raise Refusal(409, SUITE_NOT_IDLE)

    # 6. explicit, machine-checkable consent. An owner run may pause the live
    #    lane, so it must say so; a scheduled run may not, and must not claim it.
    confirm = body.get("confirm")
    if not isinstance(confirm, dict):
        raise Refusal(400, SUITE_NOT_CONFIRMED)
    model = str(body.get("model") or "").strip()
    if model and str(confirm.get("model") or "") not in ("", model):
        raise Refusal(400, SUITE_NOT_CONFIRMED)
    wants_evict = bool(confirm.get("may_evict"))
    if mode == "owner" and not wants_evict:
        raise Refusal(400, SUITE_NOT_CONFIRMED)
    if mode == "scheduled" and wants_evict:
        raise Refusal(400, "a scheduled run may not pause a lane; run it yourself")
    for suite in suite_choices(body)[1]:
        if suite not in SUITE_KEYS:
            raise Refusal(400, SUITE_BAD_SUITE.format(suite=suite,
                                                      keys=SUITE_KEYS))


def start_suites(body: dict, *, spawn: Optional[Callable] = None,
                 post: Optional[Callable] = None,
                 get: Optional[Callable[[str], dict]] = None,
                 show: Optional[Callable[[str, dict], dict]] = None,
                 smi: Optional[Callable[[], str]] = None,
                 clock: Optional[Callable[[], float]] = None,
                 store: Optional[ScoreLog] = None,
                 busy: Optional[Callable[[], Optional[str]]] = None,
                 standby: Optional[Callable[[], bool]] = None,
                 tasks: Optional[Callable[[], list]] = None,
                 running: Optional[Callable[[], Optional[str]]] = None,
                 code_runner: Optional[Callable] = None,
                 spawn_thread: bool = True) -> tuple:
    """Start ONE five-suite run in the background. (http_status, body).

    Asynchronous, like the speed bench: the work happens on a thread and a
    screen polls `suite_view(run_id)`. `spawn_thread=False` runs it in place and
    is for the tests, which want the numbers before the call returns.
    """
    body = body if isinstance(body, dict) else {}
    model = str(body.get("model") or "").strip()
    if not model:
        return 400, {"error": "nothing was measured: no model was named"}
    lane, suites, ctx, mode, notes = suite_choices(body)
    try:
        check_suite_job(body, mode=mode, get=get, busy=busy, standby=standby,
                        tasks=tasks, running=running)
    except Refusal as exc:
        return exc.code, exc.body
    run_id = _new_run_id()
    with _RUNS_LOCK:
        _RUNS[run_id] = {
            "state": "running", "step": 0, "of": len(suites), "partial": False,
            "notes": notes, "run_id": run_id, "at": int(time.time()),
            "kind": "suites", "model": model, "lane": lane,
            "suites": list(suites), "ctx": int(ctx), "mode": mode,
            "notice": "",
        }

    def work() -> None:
        try:
            _suites_work(run_id, model=model, lane=lane, ctx=ctx, suites=suites,
                         mode=mode, spawn=spawn, post=post, get=get, show=show,
                         smi=smi, clock=clock, store=store or ScoreLog(),
                         code_runner=code_runner)
        except Exception as exc:                       # never leaves a gap
            _set_state(run_id, state="failed", partial=True,
                       why=f"the run stopped ({type(exc).__name__})")

    if not spawn_thread:
        work()
        return 200, {"ok": True, "run_id": run_id, "notes": notes,
                     "message": "Measured."}
    try:
        (spawn or _spawn)(work)
    except Exception:
        _set_state(run_id, state="failed")
        return 503, {"error": "could not start the benchmark"}
    message = ("Measuring now on a throwaway Ollama. "
               + ("The lane this run needs is paused first and warmed back "
                  "afterwards." if mode == "owner" else
                  "It only runs while nothing else is using the model."))
    return 200, {"ok": True, "run_id": run_id, "notes": notes,
                 "message": message}


def _suites_work(run_id: str, *, model: str, lane: str, ctx: int, suites: list,
                 mode: str, spawn, post, get, show, smi, clock,
                 store: ScoreLog, code_runner) -> None:
    """Start the throwaway server, pause if allowed, run the suites, stop the
    server and warm the lane back - each step in the only safe order."""
    notes = list((_state(run_id) or {}).get("notes") or [])
    choice = card_choice(lane, smi=smi)
    if not choice["ok"]:
        _fail_suite_run(run_id, model, lane, pattern=[] ,
                        why=choice["why"])
        return
    chosen_cards = ",".join(str(i) for i in choice["indexes"])
    paused: list = []
    results: list = []
    server: dict = {}
    identity: dict = {}
    ollama_v, driver = "", ""
    try:
        if mode == "owner":
            p = pause_for_run(lane, get=get, post=post, clock=clock)
            paused = p.get("paused") or []
            if p.get("words"):
                notes.append(p["words"])
                _set_state(run_id, notice=p["words"])
        server = start_throwaway(choice=choice, ctx=ctx, spawn=spawn, get=get,
                                 clock=clock)
        if not server.get("ok"):
            _set_state(run_id, notes=notes)
            _fail_suite_run(run_id, model, lane, pattern=[],
                            why=server.get("why") or "the server would not start")
            return
        identity = model_identity(server["url"], model, get=get, show=show)
        names = installed_models(server["url"], get=get)
        if names is None:
            _fail_suite_run(run_id, model, lane, pattern=[],
                            why="the throwaway Ollama did not list its models")
            return
        if not any(_same(n, model) for n in names):
            _fail_suite_run(
                run_id, model, lane, pattern=[],
                why=SUITE_MODEL_MISSING.format(
                    model=model, has=", ".join(sorted(names)[:12]) or "nothing"))
            return
        ollama_v = ollama_version(server["url"], get=get) or ""
        driver = read_cards(smi).get("driver") or ""
        cancelled = False
        for i, suite_id in enumerate(suites):
            st = _state(run_id)
            if st is None or st.get("cancelled"):
                cancelled = True
                break
            _set_state(run_id, step=i + 1)
            result = run_one_suite(
                suite_id, server["url"], model, ctx, identity=identity,
                post=post, get=get, smi=smi, clock=clock,
                code_runner=code_runner)
            results.append(result)
            suite = next(s for s in SUITES if s["id"] == suite_id)
            row = scorecard_row(
                run_id=run_id, identity=identity, lane=lane, suite=suite,
                model=model, ctx=ctx, result=result, ollama_version=ollama_v,
                driver=driver, cards_used=chosen_cards)
            if not store.append(row):
                notes.append("the scorecard could not be saved to disk")
        _set_state(run_id, notes=notes, partial=bool(cancelled))
    except Exception as exc:
        _fail_suite_run(run_id, model, lane, pattern=[],
                        why=f"the run stopped ({type(exc).__name__})")
        return
    finally:
        stopped = stop_throwaway(server or {})
        if stopped.get("why"):
            notes.append(stopped["why"])
        if paused:
            warm = warm_back(paused, get=get, post=post, clock=clock)
            notes.append("Warmed back: " + "; ".join(warm.get("restored") or [])
                         if warm.get("ok") else warm.get("why") or "")
            if not warm.get("ok"):
                notes.append("THE LANE WAS NOT PUT BACK: " + str(warm.get("why")))
    result = _suite_run_result(run_id=run_id, model=model, lane=lane, ctx=ctx,
                               mode=mode, choice=choice, suites=suites,
                               results=results, paused=paused,
                               cancelled=bool(cancelled),
                               notes=notes)
    _set_state(run_id, state="done" if results and not cancelled else "failed",
               step=len(results), of=len(suites), partial=bool(cancelled),
               result=result, notes=notes)


def _suite_run_result(*, run_id: str, model: str, lane: str, ctx: int,
                      mode: str, choice: dict, suites: list, results: list,
                      paused: list, cancelled: bool, notes: list) -> dict:
    """The one sentence a screen shows, and the per-suite results behind it."""
    skipped = [r for r in results if r.get("skipped")]
    failed = [r for r in results if not r.get("skipped") and not r.get("passed")]
    passed_all = (bool(results) and not cancelled and not skipped and not failed
                  and all(r.get("ok") for r in results))
    parts = []
    for r in results:
        label = next((s["label"] for s in SUITES if s["id"] == r.get("suite")),
                     r.get("suite"))
        if r.get("skipped"):
            parts.append(f"{label} NOT RUN")
        elif not r.get("ok"):
            parts.append(f"{label} failed")
        elif r.get("suite") == "speed":
            tps = r.get("decode_tps")
            parts.append(f"{label} {'promotion-grade' if r.get('promotion_grade') else 'SPILLED'}"
                         + (f" at {tps:.1f} tok/s" if tps else ""))
        else:
            parts.append(f"{label} {r.get('items_passed')}/{r.get('items')}")
    words = (f"{model} on the {choice.get('name') or 'card'} at {int(ctx):,} tokens: "
             + _sentence(parts) + "." if results else
             "Nothing was measured.")
    return {"kind": "suites", "run": run_id, "model": model, "lane": lane,
            "card": choice.get("name") or "", "cards_used": choice.get("indexes"),
            "ctx": int(ctx), "mode": mode, "requested": list(suites),
            "results": results, "passed": passed_all, "cancelled": bool(cancelled),
            "paused": paused, "notes": notes, "words": words,
            "measured_on": "this_pc"}


def _fail_suite_run(run_id: str, model: str, lane: str, *, pattern: list,
                    why: str) -> None:
    """A suite run that died writes NOTHING to the scorecard store - a fake row
    with zeros would be read as a measurement. The failure is in the run state,
    in one sentence."""
    _set_state(run_id, state="failed", partial=True,
               why=str(why)[:MAX_REASON],
               result={"kind": "suites", "run": run_id, "model": model,
                       "lane": lane, "passed": False, "results": pattern,
                       "words": f"Nothing was measured: {str(why)[:MAX_WORDS]}"},
               notes=list((_state(run_id) or {}).get("notes") or [])
               + [str(why)[:MAX_REASON]])


def suite_view(run_id: str, *, store: Optional[ScoreLog] = None) -> tuple:
    """(status, body) for one suite run - live from memory, then the store."""
    st = _state(run_id)
    if st is not None:
        out = {"state": st.get("state"), "step": st.get("step"),
               "of": st.get("of"), "partial": bool(st.get("partial")),
               "kind": "suites", "model": st.get("model"),
               "lane": st.get("lane"), "ctx": st.get("ctx")}
        if st.get("notice"):
            out["notice"] = st["notice"]
        if st.get("notes"):
            out["notes"] = list(st["notes"])
        if st.get("state") in ("done", "failed") and st.get("result"):
            out["result"] = st["result"]
        if st.get("why"):
            out["why"] = st["why"]
        return 200, out
    rows = (store or ScoreLog()).by_run(run_id)
    if not rows:
        return 404, {"error": "no suite run with that id"}
    model = str(rows[0].get("model") or "")
    notes = [f"{len(rows)} scorecard row(s) on file for this run"]
    results = [{"suite": r.get("suite"), "ok": bool(r.get("ok")),
                "passed": bool(r.get("passed")),
                "skipped": bool(r.get("skipped")),
                "why": r.get("why") or "", "words": r.get("words") or "",
                "score_pct": r.get("score_pct"),
                "decode_tps": r.get("decode_tps")} for r in rows]
    return 200, {"state": "done", "step": len(rows), "of": len(rows),
                 "partial": False, "kind": "suites", "model": model,
                 "notes": notes,
                 "result": {"kind": "suites", "run": run_id, "model": model,
                            "passed": all(r.get("passed") for r in results),
                            "results": results,
                            "words": "Read from the scorecard history."}}


def cancel_suite(run_id: str) -> tuple:
    """Ask a suite run to stop after the suite in flight. The request already
    sent is never cut off; what has been measured stays measured."""
    st = _state(run_id)
    if st is None:
        return 404, {"error": "no suite run with that id"}
    if st.get("state") != "running":
        return 409, {"error": "that run has already finished"}
    _set_state(run_id, cancelled=True)
    return 200, {"ok": True, "cancelled": True}


# ==========================================================================
#   The measure-first promotion harness (Q2, as code)
# ==========================================================================
#
# WHAT THIS IS. The owner's ruling: a preset default may change only when a
# measured run shows (1) zero spill at the preset's own window, (2) quality not
# worse on the domain rubric, and (3) the preset's speed floor. This turns two
# scorecards into those three checks and a verdict - and the verdict can say
# "keep the current default" perfectly well. It NEVER changes a preset; the
# `applied` key is always False and the words say which existing card would be
# the only way to apply one.

def promotion_plan(pair_id: str) -> dict:
    """What to measure for one pair, so a screen can offer the run."""
    pair = next((p for p in PROMOTION_PAIRS if p["id"] == pair_id), None)
    if pair is None:
        return {"ok": False,
                "why": f"no promotion pair called {pair_id!r}; there are: "
                       + ", ".join(p["id"] for p in PROMOTION_PAIRS)}
    return {"ok": True, "pair": dict(pair),
            "message": (f"Measure {pair['candidate']} and {pair['incumbent']} on "
                        f"a throwaway server at {pair['ctx']:,} tokens, then "
                        f"compare: zero spill, the {pair['preset']} rubric not "
                        f"worse, and the speed floor. Nothing is applied."),
            "suites": list(pair["suites"]), "ctx": pair["ctx"]}


def _rows_for(scorecards: dict, model: str) -> dict:
    """{suite: row} for one model out of `latest_scorecards()`."""
    bare = _bare(model)
    return {suite: row for (name, suite), row in (scorecards or {}).items()
            if name == bare}


def promotion_checks(pair: dict, incumbent: dict, candidate: dict) -> list:
    """The three Q2 checks, each with a plain sentence. Every check must pass
    for the verdict to promote; a missing measurement fails its own check
    rather than being skipped."""
    checks: list = []
    suites = list(pair.get("suites") or ())
    missing = []
    for name, rows in ((pair.get("incumbent"), incumbent),
                       (pair.get("candidate"), candidate)):
        for suite in suites:
            if suite not in rows:
                missing.append(f"{name} {suite}")
    checks.append({
        "check": "both models measured at the preset's window",
        "pass": not missing,
        "detail": ("both have a scorecard" if not missing else
                   "no scorecard yet for: " + ", ".join(missing)),
    })
    speed = candidate.get("speed") or {}
    spill = speed.get("spill_bytes")
    pct = speed.get("on_card_percent")
    spill_pass = (spill == 0 and pct == 100)
    checks.append({
        "check": "zero spill at the preset's target context",
        "pass": bool(spill_pass),
        "detail": (f"candidate spilled {spill} B, {pct}% on card"
                   if spill is not None else
                   "the candidate has no speed scorecard showing its spill"),
    })
    for suite in [s for s in suites if s != "speed"]:
        inc = (incumbent.get(suite) or {}).get("score_pct")
        cand = (candidate.get(suite) or {}).get("score_pct")
        worse = inc is not None and cand is not None and float(cand) < float(inc)
        checks.append({
            "check": f"quality not worse on the {suite} rubric",
            "pass": bool(inc is not None and cand is not None and not worse),
            "detail": (f"candidate {cand}%, current default {inc}%"
                       if inc is not None and cand is not None else
                       f"missing a {suite} score for "
                       + ("the candidate" if cand is None else "the current default")),
        })
    floor = PROMOTION_DECODE_FLOOR.get(str(pair.get("preset") or ""))
    tps = speed.get("decode_tps")
    if floor is None:
        checks.append({"check": "speed floor", "pass": False,
                       "detail": f"no floor is defined for preset "
                                 f"{pair.get('preset')!r}"})
    else:
        checks.append({
            "check": f"speed floor of {floor:g} tokens a second",
            "pass": bool(isinstance(tps, (int, float)) and not isinstance(tps, bool)
                         and float(tps) >= float(floor)),
            "detail": (f"candidate {float(tps):.1f} tok/s" if isinstance(tps, (int, float))
                       and not isinstance(tps, bool) else
                       "the candidate has no measured decode speed"),
        })
    return checks


def promotion_verdict(pair: dict, incumbent: dict, candidate: dict) -> dict:
    """The verdict for ONE pair, as a dict a screen can render. Never applies."""
    checks = promotion_checks(pair, incumbent, candidate)
    promote = all(c["pass"] for c in checks)
    failed = [c for c in checks if not c["pass"]]
    if promote:
        words = (f"Measured evidence supports {pair['candidate']} over "
                 f"{pair['incumbent']} for the {pair['preset']} preset: zero "
                 f"spill, no worse on its rubric, above the speed floor. "
                 f"Nothing has been changed.")
    else:
        words = (f"Keep {pair['incumbent']} as the {pair['preset']} default: "
                 + "; ".join(f"{c['check']} - {c['detail']}" for c in failed)
                 + ". Nothing has been changed.")
    return {"pair": pair.get("id"), "preset": pair.get("preset"),
            "incumbent": pair.get("incumbent"),
            "candidate": pair.get("candidate"), "ctx": pair.get("ctx"),
            "suites": list(pair.get("suites") or ()),
            "promote": promote, "checks": checks, "applied": False,
            "words": words,
            "note": ("a preset default only changes through the existing "
                     "approval card; this verdict does not touch one")}


def pair_verdict(pair_id: str, *, scores: Optional[dict] = None,
                 store: Optional[ScoreLog] = None) -> dict:
    """The verdict for one named pair, from the newest stored scorecards.

    `scores` is `latest_scorecards()`'s shape ({(model, suite): row}); a test
    hands a fake one, a route hands none and the store is read. Read-only.
    """
    pair = next((p for p in PROMOTION_PAIRS if p["id"] == pair_id), None)
    if pair is None:
        return {"ok": False, "applied": False,
                "why": f"no promotion pair called {pair_id!r}; there are: "
                       + ", ".join(p["id"] for p in PROMOTION_PAIRS)}
    cards = scores if scores is not None else latest_scorecards(store=store)
    out = promotion_verdict(pair, _rows_for(cards, pair["incumbent"]),
                            _rows_for(cards, pair["candidate"]))
    out["ok"] = True
    return out


def promotion_pairs_view(*, store: Optional[ScoreLog] = None) -> dict:
    """Every pair and its verdict - the read shape a screen offers.

    Deterministic and read-only: no model is called, no card is raised and no
    preset is applied.
    """
    cards = latest_scorecards(store=store)
    verdicts = [pair_verdict(p["id"], scores=cards) for p in PROMOTION_PAIRS]
    return {"pairs": verdicts, "measured_on": "this_pc",
            "note": ("scorecards come from the five suites run on a throwaway "
                     "Ollama; a missing pair reads as 'keep the current default' "
                     "because there is no measurement to promote on")}
