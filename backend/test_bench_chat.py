"""test_bench_chat.py - the five-suite benchmark through chat (Wave 9).

    python -B backend/test_bench_chat.py

THE OWNER'S ASK (2026-11-07): "jarvis to be able to run its own benchmarks for
both quality and speed", and he chose the full scope (speed, coding, general,
tool-calling, vision). `jarvis_bench.py` grew the five-suite runner in Wave 9,
but a runner with no door is not a feature: this suite holds the CHAT door.

WHAT IT PROVES, with fakes (no model is run, no throwaway server is started):

  - the owner's own sentences for the full run route to `bench_suites`, and the
    older speed-bench sentences keep their own intents (no sentence is stolen);
  - the runner calls the REAL `jarvis_bench.start_suites` once, with the model
    it read from the same record the speed bench uses, the lane, owner mode and
    an explicit `may_evict` consent - a run that may pause a live lane must say
    so, and the code never invents the consent;
  - the run id and its kind are written where progress reads them, so
    "how is the benchmark going?" reads `suite_view` (not the speed view) and
    "stop the benchmark" cancels the suite runner;
  - a refusal from the runner is relayed in its own words, never a claim that
    something was measured.

Hermetic: its own temp config dir and a temp bench-state file; only the
`jarvis_bench` functions are replaced, and every replacement is restored.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-bench-chat-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
_HOME = _TMP / "home"
_HOME.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_HOME)
os.environ["JARVIS_HOME"] = str(_HOME)

import jarvis_bench as B  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name: str, ok: bool, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


def t_the_owner_sentences_route_to_the_full_run():
    for said in ("run the full benchmark",
                 "run all the benchmark suites",
                 "run the benchmark suites",
                 "benchmark your quality and speed",
                 "measure your quality and speed",
                 "start the complete benchmark"):
        m = Q.match(said)
        check(f"{said!r} is the five-suite run",
              m is not None and m.name == "bench_suites", m)
    # The owner's own 2026-11-08 words: "start Benchmarks" is the PLURAL ask and
    # used to be read as "open the benchmarks app" - a door that does not exist.
    for said in ("start a benchmark", "run a benchmark", "benchmark yourself"):
        m = Q.match(said)
        check(f"{said!r} is still the speed bench",
              m is not None and m.name == "bench_run", m)
    for said in ("start benchmarks", "start the benchmarks", "run the benchmarks",
                 "run the benchmark suites", "run the full benchmark"):
        m = Q.match(said)
        check(f"{said!r} is the five-suite run",
              m is not None and m.name == "bench_suites", m)
    # A NAMED benchmark went to the model or to the app launcher before this;
    # it is the speed bench of that preset's model now.
    for said in ("benchmark the coding model", "run the coding benchmark",
                 "start a benchmark on the fast model"):
        m = Q.match(said)
        check(f"{said!r} is a named speed bench",
              m is not None and m.name == "bench_run", m)
    m = Q.match("how do i start a benchmark")
    check("'how do i start a benchmark' is the explanation, not a run",
          m is not None and m.name == "bench_how", m)
    # ... and the older sentences keep their own owner.
    m = Q.match("run a benchmark")
    check("'run a benchmark' is still the speed bench",
          m is not None and m.name == "bench_run", m)
    m = Q.match("how is the benchmark going?")
    check("progress still belongs to bench_progress",
          m is not None and m.name == "bench_progress", m)
    m = Q.match("benchmark history")
    check("history still belongs to bench_history",
          m is not None and m.name == "bench_history", m)


def t_the_run_uses_the_real_suite_runner_with_consent():
    old_model, old_start = Q._model_record, B.start_suites
    old_dir, old_path = Q._awareness_dir, Q._bench_state_path
    seen = {}
    state_file = _TMP / "bench-run.json"

    def fake_start(body):
        seen["body"] = dict(body or {})
        return 200, {"ok": True, "run_id": "suite-run-1"}

    try:
        Q._model_record = lambda: "qwen3.5:9b"
        Q._awareness_dir = lambda: str(_TMP)
        Q._bench_state_path = lambda: str(state_file)
        B.start_suites = fake_start
        r = Q._run_bench_suites()
        body = seen.get("body") or {}
        check("the chat door calls jarvis_bench.start_suites",
              bool(seen) and callable(fake_start), seen)
        check("... with the model it read, never a guessed one",
              body.get("model") == "qwen3.5:9b", body)
        check("... in owner mode with the explicit may_evict consent",
              body.get("mode") == "owner"
              and isinstance(body.get("confirm"), dict)
              and body["confirm"].get("may_evict") is True, body)
        check("... and the answer says the five suites and the pause rule",
              r is not None and r.intent == "bench_suites"
              and "five-suite" in r.reply.lower()
              and "may pause" in r.reply.lower(), None if r is None else r.reply[:240])
        state = json.loads(state_file.read_text(encoding="utf-8"))
        check("the run id and the SUITE kind are written for progress",
              state.get("run_id") == "suite-run-1" and state.get("kind") == "suites",
              state)
        check("... with no measured number invented in the answer",
              r is not None and "tokens a second" not in r.reply.lower(),
              None if r is None else r.reply[:160])
    finally:
        Q._model_record, Q._awareness_dir, Q._bench_state_path = old_model, old_dir, old_path
        B.start_suites = old_start


def t_progress_and_stop_read_the_suite_runner():
    old_view, old_suite, old_cancel, old_cancel_suite = (
        B.view, B.suite_view, B.cancel, B.cancel_suite)
    old_dir, old_path, old_snapshot = Q._awareness_dir, Q._bench_state_path, Q._bench_progress_snapshot
    state_file = _TMP / "bench-run.json"
    asked = {}
    try:
        Q._awareness_dir = lambda: str(_TMP)
        Q._bench_state_path = lambda: str(state_file)
        state_file.write_text(json.dumps({"run_id": "suite-run-1", "model": "qwen3.5:9b",
                                          "kind": "suites"}), encoding="utf-8")

        def fake_view(run_id):
            asked["speed_view"] = run_id
            return 404, {"error": "wrong runner"}

        def fake_suite_view(run_id):
            asked["suite_view"] = run_id
            return 200, {"state": "running", "step": 2, "of": 5, "kind": "suites"}

        B.view = fake_view
        B.suite_view = fake_suite_view
        r = Q._run_bench_progress()
        check("progress reads suite_view, never the speed view",
              asked.get("suite_view") == "suite-run-1" and "speed_view" not in asked,
              asked)
        check("... and names the step and the model",
              r is not None and "step 2 of 5" in r.reply
              and "qwen3.5:9b" in r.reply, None if r is None else r.reply[:200])

        def fake_cancel(run_id):
            asked["cancel"] = run_id
            return 200, {"ok": True}

        def fake_cancel_suite(run_id):
            asked["cancel_suite"] = run_id
            return 200, {"ok": True, "cancelled": True}

        B.cancel = fake_cancel
        B.cancel_suite = fake_cancel_suite
        r = Q._run_bench_stop()
        check("stop cancels the suite runner",
              asked.get("cancel_suite") == "suite-run-1" and "cancel" not in asked,
              asked)
        check("... and says it was asked to stop", r is not None, None if r is None else r.reply[:160])
    finally:
        (B.view, B.suite_view, B.cancel, B.cancel_suite) = (
            old_view, old_suite, old_cancel, old_cancel_suite)
        Q._awareness_dir, Q._bench_state_path, Q._bench_progress_snapshot = (
            old_dir, old_path, old_snapshot)


def t_a_refusal_is_relayed_in_its_own_words():
    old_start, old_model = B.start_suites, Q._model_record
    try:
        Q._model_record = lambda: "qwen3.5:9b"
        B.start_suites = lambda body: (409, {"error": "an answer is streaming right now"})
        r = Q._run_bench_suites()
        check("a refusal is relayed, and nothing is claimed measured",
              r is not None and r.intent == "bench_suites"
              and "nothing was measured" in r.reply.lower()
              and ("answering" in r.reply.lower()
                   or "streaming" in r.reply.lower())
              and "five-suite" not in r.reply.lower(),
              None if r is None else r.reply[:220])
    finally:
        B.start_suites, Q._model_record = old_start, old_model


def main() -> int:
    home = os.environ.get("OPENJARVIS_HOME") or ""
    try:
        same = bool(home) and Path(home).resolve() == _HOME.resolve()
    except OSError:
        same = False
    if not same:
        print("FAIL  the suite's OPENJARVIS_HOME is not its own temp folder")
        return 1
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
