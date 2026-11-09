"""test_lane_integrity.py - Q4/Q5/Q6 lane-integrity guards (owner ruling 2026-11-08).

    python3 backend/test_lane_integrity.py

WHAT THIS IS FOR. The live PC lost its model-backed chat twice on 2026-11-08: a
persisted chat lane named the on-demand three-card server (11450) after that
server was gone, so every chat turn died with "The local model is not running";
and a wake-time warm-up loaded the pooled 30B on the ONE-card everyday lane
(74% GPU / 26% CPU). The owner's Q4/Q5/Q6 ruling of 20:55 PT names three fixes:

  Q4  a dead pooled-lane pointer is repaired atomically inside the chat-lane
      getter: ONE sub-second TCP probe, then the lane file is put back on the
      configured everyday lane (OLLAMA_URL). Nothing is started, paused or
      loaded by that getter.
  Q5  a pooled-lane `/v1/chat/completions` request NAMES its configured window
      (`options.num_ctx`, 49,152) so Ollama cannot default to 8192 and reload /
      truncate the measured context. Non-pooled lanes keep today's request.
  Q6  `warm_everyday()` never warms 11436 while the pooled lane is the active,
      running lane; and it never loads a pooled 30B model onto 11436 at all.

Every check is hermetic: its own temp OPENJARVIS_CONFIG_DIR, fakes for the TCP
probe / HTTP transport, no Ollama, no model, no card, no live lane.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

TMP = Path(tempfile.mkdtemp(prefix="lane-integrity-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["OLLAMA_URL"] = "http://127.0.0.1:11436"

import jarvis_agent as AG  # noqa: E402
import jarvis_presets as P  # noqa: E402

LANE_FILE = TMP / "presets-active-lane.json"
EVERYDAY = "http://127.0.0.1:11436"
POOLED = "http://127.0.0.1:11450"
POOLED_MODEL = "qwen3-coder-30b-a3b-ud-q3-k-xl"
EVERYDAY_MODEL = "qwen3.5:9b"

PASSED, FAILED = [], []


def check(name: str, ok, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


def _lane(url: str) -> None:
    LANE_FILE.write_text(json.dumps({"base_url": url}), encoding="utf-8")


def _lane_url() -> str:
    try:
        return str(json.loads(LANE_FILE.read_text(encoding="utf-8"))["base_url"])
    except Exception:
        return "<absent>"


# ===========================================================================
#   Q4 - the dead pooled pointer is repaired in the getter
# ===========================================================================

def the_dead_pooled_pointer_is_repaired_in_the_getter() -> None:
    real = (P._lane_listening, P._persisted_lane_url)
    calls = []

    def refused(url, timeout=0.35):
        calls.append(("probe", url))
        return False

    # The two things the getter must NEVER do: start the pooled server, pause a
    # lane. Any of those raising is the failure this test is for.
    import jarvis_big_coder as big
    real_start, real_pause = big.server_start, big.pause_lanes
    big.server_start = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the chat-lane getter started the pooled server"))
    big.pause_lanes = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the chat-lane getter paused a lane"))
    try:
        P._lane_listening = refused
        _lane(POOLED)
        got = P.active_chat_url(EVERYDAY)
        check("Q4: a dead pooled pointer returns the configured everyday lane",
              got == EVERYDAY, got)
        check("Q4: ... and the lane file is rewritten atomically to it",
              _lane_url() == EVERYDAY, _lane_url())
        check("Q4: ... the probe was ONE ask on the pooled lane, nothing else",
              calls == [("probe", POOLED)], calls)

        # A LIVE pooled lane keeps the file and is returned unchanged.
        _lane(POOLED)
        P._lane_listening = lambda url, timeout=0.35: True
        got = P.active_chat_url(EVERYDAY)
        check("Q4: a live pooled lane is kept and nothing is rewritten",
              got == POOLED and _lane_url() == POOLED, (got, _lane_url()))

        # No file / a non-loopback file keeps today's rule (the configured lane).
        LANE_FILE.unlink()
        check("Q4: no lane file means OLLAMA_URL, exactly as before",
              P.active_chat_url(EVERYDAY) == EVERYDAY)
        LANE_FILE.write_text(json.dumps({"base_url": "http://10.0.0.9:11450"}),
                             encoding="utf-8")
        check("Q4: a non-loopback lane file is still ignored",
              P.active_chat_url(EVERYDAY) == EVERYDAY)
    finally:
        P._lane_listening, P._persisted_lane_url = real
        big.server_start, big.pause_lanes = real_start, real_pause
    LANE_FILE.unlink(missing_ok=True)


# ===========================================================================
#   Q5 - pooled-lane chat requests name their configured window
# ===========================================================================

def the_pooled_chat_request_names_its_window() -> None:
    body = AG.chat_body("m", [{"role": "user", "content": "hi"}], {},
                        ollama_url=POOLED)
    check("Q5: a pooled-lane chat request carries options.num_ctx = 49,152",
          body.get("options") == {"num_ctx": 49152}, body.get("options"))

    plain = AG.chat_body("m", [{"role": "user", "content": "hi"}], {},
                         ollama_url=EVERYDAY)
    check("Q5: an everyday-lane request gains no options field",
          "options" not in plain, plain.get("options"))

    # The number is READ from lane config, not a second constant here.
    import jarvis_model_lanes as lanes
    real_profile = lanes.pooled_profile
    try:
        lanes.pooled_profile = lambda mode="coding": {"key": "coding",
                                                      "num_ctx": 32768}
        changed = AG.chat_body("m", [{"role": "user", "content": "hi"}], {},
                               ollama_url=POOLED)
        check("Q5: changing the lane config changes the request's window",
              changed.get("options") == {"num_ctx": 32768},
              changed.get("options"))
    finally:
        lanes.pooled_profile = real_profile


# ===========================================================================
#   Q6 - warm_everyday never loads the pooled model onto the everyday lane
# ===========================================================================

def _warm_harness():
    """Fakes for the three places warm_everyday can touch, plus the guards."""
    seen = []
    real = (AG._get_json, AG.warm_prefix, AG._lane_context, AG._chat_model_now,
            AG.local_model_refusal, P._lane_listening)

    def get_json(url, payload=None, timeout=120.0):
        seen.append(("http", str(url), dict(payload or {})))
        return {}

    def warm_prefix(model, *, ollama_url, enabled_tools=None, why="", **kw):
        seen.append(("warm_prefix", str(ollama_url), str(model)))
        return {"state": "warmed"}

    AG._get_json = get_json
    AG.warm_prefix = warm_prefix
    AG._lane_context = lambda url, model: 16384
    AG._chat_model_now = lambda: EVERYDAY_MODEL
    AG.local_model_refusal = lambda url, model: ""
    P._lane_listening = lambda url, timeout=0.35: True
    return seen, real


def _restore(real) -> None:
    (AG._get_json, AG.warm_prefix, AG._lane_context, AG._chat_model_now,
     AG.local_model_refusal, P._lane_listening) = real


def the_warm_never_loads_the_pooled_model_on_the_everyday_lane() -> None:
    # (a) the pooled lane is the active, running chat lane: nothing is warmed.
    seen, real = _warm_harness()
    try:
        _lane(POOLED)
        P._lane_listening = lambda url, timeout=0.35: True
        got = AG.warm_everyday()
        check("Q6a: an active pooled lane means warm_everyday warms NOTHING",
              got is False and seen == [], (got, seen))
        got = AG.warm_everyday(model=POOLED_MODEL)
        check("Q6a: ... not even when a model is named explicitly",
              got is False and seen == [], (got, seen))
    finally:
        _restore(real)

    # (b) on the everyday lane, the pooled 30B name is refused before any request.
    seen, real = _warm_harness()
    try:
        _lane(EVERYDAY)
        got = AG.warm_everyday(model=POOLED_MODEL)
        check("Q6b: the pooled 30B model is never warmed on the everyday lane",
              got is False and seen == [], (got, seen))
    finally:
        _restore(real)

    # (c) the ordinary everyday warm still works, and only on 11436.
    seen, real = _warm_harness()
    try:
        _lane(EVERYDAY)
        got = AG.warm_everyday(model=EVERYDAY_MODEL)
        http = [row for row in seen if row[0] == "http"]
        check("Q6c: the everyday model is warmed on 11436, as before",
              got is True and http and http[0][1] == f"{EVERYDAY}/api/generate"
              and http[0][2].get("options", {}).get("num_ctx") == 16384,
              (got, seen))
        check("Q6c: ... and the prefix is warmed on the same lane",
              [row for row in seen if row[0] == "warm_prefix"]
              and seen[-1][1] == EVERYDAY, seen)
    finally:
        _restore(real)

    # (d) DEF measured on the live install, 2026-11-09: Ollama's own /api/ps
    # reports the model with a ":latest" tag, and the exact-name compare let it
    # past the guard - the 30B really was loaded on 11436 at 74% on card.
    seen, real = _warm_harness()
    try:
        check("Q6d: is_pooled_model knows the :latest tag Ollama reports",
              P.is_pooled_model(POOLED_MODEL + ":latest") is True)
        _lane(EVERYDAY)
        got = AG.warm_everyday(model=POOLED_MODEL + ":latest")
        check("Q6d: the tagged pooled 30B is never warmed on the everyday lane",
              got is False and seen == [], (got, seen))
        got = AG.warm_everyday(model=POOLED_MODEL)
        check("Q6d: ... and the untagged name is still refused too",
              got is False and seen == [], (got, seen))
    finally:
        _restore(real)
    LANE_FILE.unlink(missing_ok=True)


def main() -> int:
    print("-- Q4 --")
    the_dead_pooled_pointer_is_repaired_in_the_getter()
    print("\n-- Q5 --")
    the_pooled_chat_request_names_its_window()
    print("\n-- Q6 --")
    the_warm_never_loads_the_pooled_model_on_the_everyday_lane()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    code = main()
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
