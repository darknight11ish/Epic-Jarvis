#!/usr/bin/env python3
"""test_model_conversation.py - talking about the local models, measured.

    python -B backend/test_model_conversation.py

THE OWNER'S ASK (2026-11-08): *"I'd also like to be able to talk about the local
AI models. what has been measured, start Benchmarks, what a better models for
the current Presets, what are the current models for the current Presets and
more in chat and in jarvis live."* Chat and Jarvis Live share `/api/chat`, so
this suite drives the SAME `jarvis_quick.answer_turn` the handler calls, typed
(`provenance:"voice"` only) and Live-marked (`provenance:"voice"` + `live:true`),
and requires the words to be byte-identical.

WHAT IT PROVES, each check one of the claims:

  1. The owner's own sentences are all answered deterministically - what was
     measured, start a benchmark (current model, all five suites, or a named
     preset's model), which model each preset uses, which model is better for a
     preset, and what model ran before - and every answer takes the `quick:`
     route (never the model: `jarvis_agent.run_local_turn`/`_post`/
     `_open_stream` are patched to RAISE for the whole run).
  2. MEASURED MEANS STORED: every number in the measured answer appears in the
     `jarvis_bench` stores this PC actually wrote (speed rows + suite
     scorecards), or is a count/date derived from them. Nothing is invented; an
     empty store says so.
  3. STARTING USES THE REAL RUNNER, NEVER A SECOND ONE: the chat door calls
     `jarvis_bench.start` / `start_suites` with the model and lane read from the
     preset row, owner mode and the explicit `may_evict` consent; a refusal is
     relayed in the runner's own words and nothing is claimed measured. The
     tests REPLACE those two functions - no benchmark is started here, and no
     live lane/port is contacted (sockets and `jarvis_bench.http_post_json` are
     patched to raise).
  4. A STREAMING TURN IS REFUSED: the runner's own ANSWER_STREAMING sentence,
     with no state file written.
  5. PRESET FACTS match `jarvis_model_knowledge`; better-model advice carries
     the recommender's own MEASURED ON THIS PC / ESTIMATED FIT labels and never
     calls a model better without a measurement for that preset; model history
     reads the change journal and says plainly when nothing is recorded.
  6. THE FEATURE GUIDE CANNOT CONTRADICT IT: `model_benchmarks` is one of the
     bounded SELF_FACT_IDS the model's `self_portrait` carries, and the feature
     list's row names the new sentences.

Hermetic: temp config/HOME, temp bench stores, a fake recommender panel, fake
`jarvis_bench.start`/`start_suites`, no network, no model, no card.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import time
import traceback
import types
from contextlib import contextmanager
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-model-conversation-"))
for _d in ("config", "home", "logs"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
os.environ.setdefault("JARVIS_NO_EMBED", "1")
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP / "config"
fw.LOG_DIR = _TMP / "logs"
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.pop("JARVIS_BACKEND", None)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_bench.py",
                "jarvis_model_knowledge.py", "jarvis_model_recommender.py",
                "jarvis_feature_guide.py")

import jarvis_agent as A  # noqa: E402
import jarvis_bench as B  # noqa: E402
import jarvis_feature_catalogue as FC  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_model_knowledge as K  # noqa: E402
import jarvis_model_recommender as MR  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: The owner's phrasings, exactly what he asked for (and the natural variants
#: this code claims), each with the intent it must reach.
OWNER_SENTENCES = {
    # 1. what has been measured
    "what have you measured": "bench_history",
    "what has been measured": "bench_history",
    "what's been measured on this pc": "bench_history",
    "what did the last benchmark measure": "bench_history",
    "what are the benchmark results": "bench_history",
    "what benchmarks have you run": "bench_history",
    "what were the benchmark results": "bench_history",
    "tell me what you measured": "bench_history",
    # 2. start a benchmark
    "start a benchmark": "bench_run",
    "start benchmarks": "bench_suites",
    "start the benchmarks": "bench_suites",
    "run the benchmarks": "bench_suites",
    "run the full benchmark": "bench_suites",
    "start the benchmark suites": "bench_suites",
    "benchmark the coding model": "bench_run",
    "run the coding benchmark": "bench_run",
    "start a benchmark on the fast model": "bench_run",
    "how do i start a benchmark": "bench_how",
    "what does a benchmark measure": "bench_how",
    # 3. current models for the presets
    "what models do the current presets use": "preset_models",
    "what are the current models for the current presets": "preset_models",
    "what models do the presets use": "preset_models",
    "which model is each preset using": "preset_models",
    "what are the preset models": "preset_models",
    "which preset uses which model": "preset_models",
    "what model does the coding preset use": "preset_model",
    "what model does fast use": "preset_model",
    # 4. better models for the presets
    "what are the best models for the current presets": "preset_best_all",
    "what better models are there for my presets": "preset_best_all",
    "what is a better model for the coding preset": "preset_best",
    "which model is better for coding": "preset_best",
    "which model is best for coding": "preset_best",
    "what should i use for coding": "preset_best",
    "what is the best model for the fast preset": "preset_best",
    "is there a better model for general": "preset_best",
    # 5. current / previous model
    "what is the current model": "model_current",
    "what model are you using": "model_current",
    "what did you use before": "model_before",
    "what model did you use before": "model_before",
    "which model did you use previously": "model_before",
}

#: The rows this suite writes into the two REAL stores, and the panel the fake
#: recommender returns - fixed numbers, fixed dates, no hardware detection.
AT_SPEED = 1_800_000_000
AT_SCORE = 1_800_000_100
SPEED_ROWS = (
    {"kind": "bench-run", "model": "qwen3.5:9b", "lane": "everyday",
     "gen_median": 44.9, "ok": True, "at": AT_SPEED},
    {"kind": "bench-run", "model": "qwen3-coder-30b-a3b-ud-q3-k-xl",
     "lane": "coding", "gen_median": 83.8, "ok": True, "at": AT_SPEED + 10},
)
SCORE_ROWS = (
    {"model": "qwen3.5:9b", "suite": "coding", "score_pct": 83.3,
     "items": 6, "items_passed": 5, "passed": True, "ok": True,
     "at": AT_SCORE, "decode_tps": 44.9, "ctx": 16384},
    {"model": "qwen3-coder-30b-a3b-ud-q3-k-xl", "suite": "speed",
     "score_pct": 91.7, "items": 12, "items_passed": 11, "passed": True,
     "ok": True, "at": AT_SCORE + 10, "decode_tps": 83.8, "ctx": 49152},
    {"model": "qwen3.5:4b", "suite": "vision_ocr", "skipped": True,
     "ok": True, "at": AT_SCORE + 20},
)
PANEL_ROWS = (
    {"model": "gemma4:12b-it-qat", "label": "Gemma 4 12B",
     "provenance": "measured_this_pc", "measured": {"decode_tps": 61.2}},
    {"model": "qwen3.5:4b", "label": "Qwen 3.5 4B",
     "provenance": "estimated_fit",
     "provenance_label": "ESTIMATED FIT (run benchmark to verify)",
     "measured": {}},
)


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def body(sentence, *, live=False, private=False):
    msg = {"role": "user", "content": sentence, "provenance": "voice"}
    if live:
        msg["live"] = True
    out = {"messages": [msg], "model": "m", "stream": False}
    if private:
        out["private"] = True
    return out


# --------------------------------------------------------------------------
#  Hermetic guards: no model, no socket, no bench internals
# --------------------------------------------------------------------------

@contextmanager
def no_model():
    names = ("run_local_turn", "_post", "_open_stream")
    saved = {n: getattr(A, n, None) for n in names}

    def boom(*a, **k):
        raise AssertionError("the model entry point was called")

    for n in names:
        if saved[n] is not None:
            setattr(A, n, boom)
    try:
        yield
    finally:
        for n in names:
            if saved[n] is not None:
                setattr(A, n, saved[n])


@contextmanager
def no_socket():
    real = socket.socket.connect

    def boom(*a, **k):
        raise AssertionError("a socket was opened by a deterministic answer")

    socket.socket.connect = boom
    save_http, save_url = B.http_post_json, B._urlopen
    B.http_post_json = boom
    B._urlopen = boom
    try:
        yield
    finally:
        socket.socket.connect = real
        B.http_post_json, B._urlopen = save_http, save_url


class BenchDouble:
    """The two real-runner entry points, replaced by recording fakes."""

    def __init__(self, code=200, run_id="fake-run-1", out=None):
        self.code, self.run_id, self.out = code, run_id, out or {}
        self.calls = []

    def start(self, body):
        self.calls.append(("start", dict(body or {})))
        out = dict(self.out)
        out.setdefault("ok", self.code == 200)
        out.setdefault("run_id", self.run_id)
        return self.code, out

    def start_suites(self, body):
        self.calls.append(("start_suites", dict(body or {})))
        out = dict(self.out)
        out.setdefault("ok", self.code == 200)
        out.setdefault("run_id", self.run_id)
        return self.code, out


@contextmanager
def bench_double(double):
    saved = B.start, B.start_suites
    B.start, B.start_suites = double.start, double.start_suites
    try:
        yield double
    finally:
        B.start, B.start_suites = saved


@contextmanager
def fake_recommender():
    saved = MR.recommend

    def fake(**_k):
        return {"hardware": {"words": "this PC", "detected": True},
                "rows": [dict(r) for r in PANEL_ROWS], "notes": []}

    MR.recommend = fake
    try:
        yield
    finally:
        MR.recommend = saved


# --------------------------------------------------------------------------
#  Data setup / teardown
# --------------------------------------------------------------------------

def _stores_path() -> tuple:
    return Path(B.default_path()), Path(B.scores_path())


def seed_stores():
    for path in _stores_path():
        try:
            path.unlink()
        except OSError:
            pass
    for row in SPEED_ROWS:
        B.BenchLog().append(dict(row))
    for row in SCORE_ROWS:
        B.ScoreLog().append(dict(row))


def clear_stores():
    for path in _stores_path():
        try:
            path.unlink()
        except OSError:
            pass


JOURNAL = _TMP / "home" / "self-awareness" / "changes.jsonl"


def write_journal(rows):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    if rows is None:
        try:
            JOURNAL.unlink()
        except OSError:
            pass
        return
    JOURNAL.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                       encoding="utf-8")


# --------------------------------------------------------------------------
# 1. Every owner sentence, deterministic and on the quick route
# --------------------------------------------------------------------------

def t_the_owner_sentences_are_all_answered_without_the_model():
    seed_stores()
    P._write_choice("coding")
    with no_model(), no_socket():
        for sentence, expected in OWNER_SENTENCES.items():
            got = Q.match(sentence)
            check(f"{sentence!r} is claimed as {expected}",
                  got is not None and got.name == expected,
                  None if got is None else got.name)
            if got is None:
                continue
            with bench_double(BenchDouble()):
                res = Q.answer_turn(body(sentence))
            check(f"{sentence!r} answers without the model", res is not None)
            if res is not None:
                check(f"{sentence!r} takes the quick: route",
                      Q.route_fields(res).get("quick") == res.intent,
                      Q.route_fields(res))


def t_typed_and_live_are_byte_identical():
    seed_stores()
    P._write_choice("coding")
    with no_model(), no_socket():
        for sentence in OWNER_SENTENCES:
            with bench_double(BenchDouble()):
                typed = Q.answer_turn(body(sentence))
            with bench_double(BenchDouble()):
                live = Q.answer_turn(body(sentence, live=True))
            check(f"{sentence!r}: Live words are the typed words",
                  typed is not None and live is not None
                  and typed.intent == live.intent
                  and typed.reply == live.reply,
                  (None if typed is None else typed.reply[:120],
                   None if live is None else live.reply[:120]))


# --------------------------------------------------------------------------
# 2. Measured means stored; no invented number
# --------------------------------------------------------------------------

def _numbers(text: str) -> set:
    out = set()
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", str(text or "")):
        out.add(token.replace(",", ""))
    return out


def _store_numbers(rows) -> set:
    allowed = set()
    for row in rows:
        raw = json.dumps(row)
        for token in re.findall(r"\d[\d,]*(?:\.\d+)?", raw):
            allowed.add(token.replace(",", ""))
        at = row.get("at")
        try:
            when = time.localtime(float(at))
            allowed.update({time.strftime("%d", when).lstrip("0") or "0",
                            time.strftime("%Y", when)})
        except (TypeError, ValueError, OSError):
            pass
    return allowed


def t_the_measured_answer_uses_only_stored_numbers():
    seed_stores()
    with no_model(), no_socket():
        res = Q.answer_turn(body("what has been measured"))
    check("the measured answer exists", res is not None)
    if res is None:
        return
    reply = res.reply
    check("... it says the numbers were measured on this PC",
          "measured on this pc" in reply.lower())
    check("... it names both stores' records",
          "benchmark runs" in reply.lower() and "suite scorecards" in reply.lower())
    check("... a speed row's number is stated", "44.9" in reply)
    check("... a suite scorecard's score is stated", "83.3" in reply)
    check("... and a suite's own label", "Coding" in reply)
    allowed = _store_numbers(SPEED_ROWS + SCORE_ROWS)
    allowed.update({str(len(SPEED_ROWS)), str(len(SCORE_ROWS))})
    invented = _numbers(reply) - allowed
    check("every number in the measured answer is in the store (or its count/date)",
          not invented, invented)


def t_an_empty_store_says_so_and_invents_nothing():
    clear_stores()
    with no_model(), no_socket(), fake_recommender():
        res = Q.answer_turn(body("what have you measured"))
    check("an empty store says nothing has been measured",
          res is not None and "not measured anything" in res.reply.lower()
          and "will not invent" in res.reply.lower())
    if res is not None:
        check("... and it names the door that starts a run",
              "start a benchmark" in res.reply.lower()
              and "benchmark suites" in res.reply.lower())


# --------------------------------------------------------------------------
# 3. Starting a benchmark: the real runner, with consent, and its refusals
# --------------------------------------------------------------------------

def t_starting_uses_the_real_runner_with_consent():
    seed_stores()
    P._write_choice("coding")
    coding = K.preset_by_name("coding") or {}
    fast = K.preset_by_name("fast") or {}
    state = _TMP / "bench-run.json"
    saved_path = Q._bench_state_path
    Q._bench_state_path = lambda: str(state)
    try:
        with no_model(), no_socket():
            double = BenchDouble(run_id="speed-run-9")
            with bench_double(double):
                res = Q.answer_turn(body("benchmark the coding model"))
            calls = double.calls
            check("a named benchmark calls jarvis_bench.start once",
                  len(calls) == 1 and calls[0][0] == "start", calls)
            sent = calls[0][1] if calls else {}
            check("... with the named preset's own model",
                  sent.get("model") == coding.get("model"), sent)
            check("... on that preset's lane",
                  sent.get("lane") == "coding", sent)
            check("... with the explicit may_evict consent",
                  isinstance(sent.get("confirm"), dict)
                  and sent["confirm"].get("may_evict") is True
                  and sent["confirm"].get("model") == coding.get("model"), sent)
            check("... and the answer names the model, lane and result place",
                  res is not None and str(coding.get("model")) in res.reply
                  and "coding lane" in res.reply.lower()
                  and "Brain, Model, Models" in res.reply,
                  None if res is None else res.reply[:240])
            written = json.loads(state.read_text(encoding="utf-8"))
            check("... the run id and the speed kind are written for progress",
                  written.get("run_id") == "speed-run-9"
                  and written.get("kind") == "speed", written)

            state.unlink(missing_ok=True)
            double = BenchDouble(run_id="suite-run-3")
            with bench_double(double):
                res = Q.answer_turn(body("start benchmarks"))
            calls = double.calls
            check("'start benchmarks' is the five-suite run through start_suites",
                  len(calls) == 1 and calls[0][0] == "start_suites", calls)
            sent = calls[0][1] if calls else {}
            check("... in owner mode, with the may_evict consent",
                  sent.get("mode") == "owner"
                  and (sent.get("confirm") or {}).get("may_evict") is True, sent)
            check("... and the answer says the five suites and the pause rule",
                  res is not None and "five-suite" in res.reply.lower()
                  and "may pause" in res.reply.lower()
                  and "Brain, Model, Models" in res.reply,
                  None if res is None else res.reply[:240])
            written = json.loads(state.read_text(encoding="utf-8"))
            check("... the suite kind is written for progress",
                  written.get("kind") == "suites" and written.get("run_id") == "suite-run-3",
                  written)

            double = BenchDouble(run_id="fast-run-4")
            with bench_double(double):
                res = Q.answer_turn(body("start a benchmark on the fast model"))
            sent = double.calls[0][1] if double.calls else {}
            check("a fast-model benchmark uses the fast preset's model and the "
                  "everyday lane",
                  sent.get("model") == fast.get("model") and sent.get("lane") == "everyday",
                  sent)
    finally:
        Q._bench_state_path = saved_path


def t_an_unknown_named_target_is_refused_and_nothing_runs():
    with no_model(), no_socket():
        double = BenchDouble()
        with bench_double(double):
            res = Q._run_bench_run({"target": "travel model"})
    check("an unknown benchmark target is refused in words, not measured",
          res is not None and "nothing was measured" in res.reply.lower()
          and "do not know" in res.reply.lower(), None if res is None else res.reply[:200])
    check("... and the runner was never called", not double.calls, double.calls)


def t_a_streaming_turn_is_refused_and_nothing_is_written():
    state = _TMP / "bench-run-refused.json"
    saved_path = Q._bench_state_path
    Q._bench_state_path = lambda: str(state)
    state.unlink(missing_ok=True)
    try:
        with no_model(), no_socket():
            refused = BenchDouble(code=409, out={"error": B.ANSWER_STREAMING})
            with bench_double(refused):
                res = Q.answer_turn(body("start a benchmark"))
            check("a streaming turn refuses the speed benchmark in the runner's words",
                  res is not None and "nothing was measured" in res.reply.lower()
                  and "answering" in res.reply.lower(),
                  None if res is None else res.reply[:220])
            check("... and no state file was written", not state.exists())

            refused = BenchDouble(code=409, out={"error": B.SUITE_STREAMING})
            with bench_double(refused):
                res = Q.answer_turn(body("start the benchmark suites"))
            check("a streaming turn refuses the suite run the same way",
                  res is not None and "nothing was measured" in res.reply.lower(),
                  None if res is None else res.reply[:220])
            check("... and no state file was written", not state.exists())
    finally:
        Q._bench_state_path = saved_path


# --------------------------------------------------------------------------
# 4. Preset facts and candidate advice
# --------------------------------------------------------------------------

def t_the_current_models_come_from_the_preset_store():
    P._write_choice("coding")
    chosen = P.choice()
    with no_model(), no_socket():
        res = Q.answer_turn(body("what models do the current presets use"))
    check("the current-models answer exists", res is not None)
    if res is None:
        return
    missing = []
    for row in K.presets():
        if str(row.get("title")) not in res.reply:
            missing.append(("title", row.get("title")))
        if str(row.get("model") or "no local model") not in res.reply:
            missing.append(("model", row.get("model")))
        context = row.get("context")
        if context and f"{int(context):,}" not in res.reply:
            missing.append(("context", context))
    check("every preset row's title, model and context window is in the answer",
          not missing, missing[:8])
    check("the active preset is marked once",
          res.reply.count("(active)") == 1 and '"Coding"' in res.reply,
          res.reply[:200])


def t_better_model_advice_carries_the_right_labels():
    seed_stores()
    P._write_choice("coding")
    coding = K.preset_by_name("coding") or {}
    with no_model(), no_socket(), fake_recommender():
        one = Q.answer_turn(body("what is a better model for the coding preset"))
        allp = Q.answer_turn(body("what are the best models for the current presets"))
    check("the per-preset advice answer exists", one is not None)
    check("the all-presets advice answer exists", allp is not None)
    if one is None or allp is None:
        return
    check("it names the preset's current model",
          str(coding.get("model")) in one.reply, one.reply[:200])
    check("a measured candidate is labelled MEASURED ON THIS PC",
          "MEASURED ON THIS PC" in one.reply, one.reply[:400])
    check("an unmeasured candidate keeps ESTIMATED FIT (run benchmark to verify)",
          "ESTIMATED FIT (run benchmark to verify)" in one.reply, one.reply[:400])
    check("it never calls one better without a measurement for that preset",
          "will not claim one is better" in one.reply.lower(),
          one.reply[-260:])
    check("... and points at the measurement that would settle it",
          "benchmark the coding model" in one.reply.lower(), one.reply[-260:])
    check("... and says nothing was switched",
          "nothing was switched" in one.reply.lower())
    check("the all-presets advice carries the same labels and the same limit",
          "MEASURED ON THIS PC" in allp.reply
          and "ESTIMATED FIT (run benchmark to verify)" in allp.reply
          and "will not call one better" in allp.reply.lower()
          and "nothing was switched" in allp.reply.lower(),
          allp.reply[-300:])
    check("the current preset's model is never offered as its own alternative",
          one.reply.count(str(coding.get("model"))) == 1,
          one.reply[:300])


def t_model_history_reads_the_change_journal_or_says_it_cannot():
    write_journal([{"at": AT_SPEED + 50,
                    "changed": [{"key": "model", "from": "qwen3.5:4b",
                                 "to": "qwen3-coder-30b-a3b-ud-q3-k-xl"}]}])
    with no_model(), no_socket():
        res = Q.answer_turn(body("what did you use before"))
    check("a recorded model change is read back with both names",
          res is not None and "qwen3.5:4b" in res.reply
          and "qwen3-coder-30b-a3b-ud-q3-k-xl" in res.reply,
          None if res is None else res.reply[:240])
    write_journal(None)
    with no_model(), no_socket():
        res = Q.answer_turn(body("what did you use before"))
    check("with nothing recorded it says so instead of guessing",
          res is not None and "no model change is recorded" in res.reply.lower(),
          None if res is None else res.reply[:240])


# --------------------------------------------------------------------------
# 5. The feature guide cannot contradict any of it
# --------------------------------------------------------------------------

def t_the_feature_guide_carries_the_same_facts():
    check("model_benchmarks is one of the bounded SELF_FACT_IDS",
          "model_benchmarks" in FG.SELF_FACT_IDS, FG.SELF_FACT_IDS)
    fact = FG.self_fact("model_benchmarks") or {}
    digest = str(fact.get("digest") or "")
    sentence = str(fact.get("sentence") or "")
    check("the digest says the measured/estimated labels a model turn would need",
          "MEASURED ON THIS PC" in digest
          and "ESTIMATED FIT (run benchmark to verify)" in digest, digest[:200])
    check("the digest says a benchmark is owner-started on a throwaway server",
          "throwaway model server" in digest and "asking" in digest, digest[:300])
    check("the digest says no number may be invented and none is called better "
          "without a measurement",
          "invented" in digest and "never called better" in digest, digest[:300])
    check("the sentence names where the results go and the streaming refusal",
          "Brain, Model, Models" in sentence and "while an answer is streaming"
          in sentence.replace("while I am answering a turn", "while an answer is streaming"),
          sentence[:200])
    row = next((r for r in FC.FEATURES if r.get("id") == "model-knowledge"), None)
    check("the feature list's model row names the benchmark/measured sentences",
          row is not None and "start a benchmark" in (row.get("where") or "")
          and "what have you measured" in (row.get("where") or "")
          and "suite scorecards" in (row.get("what") or ""),
          None if row is None else (row.get("where") or "")[:200])
    check("... and its own limit keeps an estimate from being called a measurement",
          row is not None and "ESTIMATED FIT (run benchmark to verify)"
          in (row.get("limit") or ""),
          None if row is None else (row.get("limit") or "")[:240])


# --------------------------------------------------------------------------
# 6. Private chat and the read-only marks
# --------------------------------------------------------------------------

def t_the_new_reads_answer_the_same_in_a_private_chat():
    seed_stores()
    P._write_choice("coding")
    reads = ("what has been measured", "what models do the current presets use",
             "what is a better model for the coding preset",
             "what did you use before", "how do i start a benchmark")
    with no_model(), no_socket(), fake_recommender():
        for sentence in reads:
            typed = Q.answer_turn(body(sentence))
            private = Q.answer_turn(body(sentence, private=True))
            check(f"private chat answers {sentence!r} with the same words",
                  typed is not None and private is not None
                  and typed.reply == private.reply,
                  (None if typed is None else typed.reply[:100],
                   None if private is None else private.reply[:100]))


def t_the_reads_change_nothing_and_the_starts_are_not_read_only():
    for name in ("bench_history", "bench_how", "preset_models", "preset_best",
                 "preset_best_all", "model_before"):
        check(f"{name} is marked read-only and private-answerable",
              name in Q.READ_ONLY_INTENTS
              and name in Q._PRIVATE_DETERMINISTIC_READS, name)
    for name in ("bench_run", "bench_suites"):
        check(f"{name} is NOT marked read-only (it acts on the PC)",
              name not in Q.READ_ONLY_INTENTS, name)


def t_this_suite_is_hermetic():
    check("the suite's OPENJARVIS_HOME is its own temp folder",
          Path(os.environ.get("OPENJARVIS_HOME") or "/nonexistent").resolve()
          == (_TMP / "home").resolve())
    check("the stores this suite writes are its own temp files",
          all(str(path).startswith(str(_TMP)) for path in _stores_path()),
          _stores_path())


def t_the_answers_are_the_same_on_every_preset():
    seed_stores()
    replies = {}
    with no_model(), no_socket(), fake_recommender():
        for preset in ("general", "coding", "fast", "general_uncensored"):
            P._write_choice(preset)
            replies[preset] = {
                sentence: (Q.answer_turn(body(sentence)) or None)
                for sentence in ("what has been measured",
                                 "what is a better model for the coding preset",
                                 "what did you use before")
            }
    P._write_choice("coding")
    # The history answer legitimately names the model running NOW, which the
    # preset really changes; mask only that fact, exactly as the ruling's other
    # preset test does for its two preset-reporting rows.
    preset_models = {str(r.get("id")): str(r.get("model") or "")
                     for r in K.presets()}
    differing = []
    for sentence in replies["general"]:
        words = {}
        for preset in replies:
            res = replies[preset][sentence]
            text = None if res is None else res.reply
            if text is not None and sentence == "what did you use before":
                model = preset_models.get(preset, "")
                if model:
                    text = text.replace(model, "<MODEL>")
            words[preset] = text
        if len(set(words.values())) > 1:
            differing.append((sentence, words))
    check("the measured, better-model and history answers are byte-identical on "
          "all four presets (the history's current-model fact masked)",
          not differing, differing)


if __name__ == "__main__":
    if not str(_TMP) in str(os.environ.get("OPENJARVIS_HOME") or ""):
        print("FAIL  the suite does not own its temp HOME")
        sys.exit(1)
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
                print(f"\n--- {name} ---")
                try:
                    fn()
                except Exception:
                    FAILED.append(name)
                    traceback.print_exc()
    finally:
        P._write_choice("coding")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
