"""test_pooled_preload.py - F2: a COLD pooled turn is warmed at 49,152 first.

    py -3 backend/test_pooled_preload.py

WHAT THIS IS FOR. The pooled Coding lane is measured at 49,152 tokens, 0 spill,
and `jarvis_agent.chat_body()` names that window on a pooled request
(`options.num_ctx`). But Ollama's OpenAI-compatible `/v1/chat/completions`
IGNORES a top-level `options` field when it spawns a runner, so a COLD pooled
turn reloaded the 30B at Ollama's own default - measured live on the 0.2.441
install, 2026-11-09 04:00 PT: `context_length` 8192 - and stayed there. The
acceptance row passed only because the Q8 warm's 49,152 load was still
resident (`docs/POOLED-WINDOW-PRELOAD-DESIGN-2026-11-09.md`; the second finding
in DEF-034's open row).

Ollama's NATIVE `/api/generate` DOES honour `options.num_ctx` and keeps that
runner resident, and it is exactly the call the Q8 warm measured at 49,152 / 0
spill on this PC. So `jarvis_agent.pooled_preload()` reads the lane's own
`/api/ps` and, only when the model is not resident or is resident below the
configured window, sends that native load BEFORE the `/v1` turn.

WHAT IT PROVES, against a fake Ollama lane on 127.0.0.1 (real sockets, real
JSON, nothing from the owner's PC, no model, no card, no live lane):

  (a) a COLD pooled turn sends the native preload with `num_ctx` 49,152 BEFORE
      the `/v1/chat/completions` turn, and the turn itself still names the
      window and streams (no streaming regression);
  (b) when `/api/ps` already reports the model at 49,152, no duplicate preload
      is sent - and at 8,192 (the measured defect) it IS sent;
  (c) a preload that fails is recorded in `POOLED_PRELOAD_LAST`, said in one
      plain line, and the real turn still dispatches and answers;
  (d) a non-pooled (everyday/coding) lane is untouched: no preload call, state
      "off", and its `/v1` request gains no `options` field.

The lane the seam acts on is the REAL predicate (`jarvis_presets.lane_num_ctx`,
port 11450), checked first; because the fake lane must not bind the owner's
11450, the pooled port constant is pointed at the fake's random port for the
turn checks and put back afterwards. `require_shipped` runs this against the
repository's own `jarvis_agent.py`, never the owner's live backend.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_TMP = Path(tempfile.mkdtemp(prefix="pooled-preload-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OLLAMA_URL"] = "http://127.0.0.1:11436"

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py")
import _ollama_wire as W  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_model_lanes as LANES  # noqa: E402

MODEL = "qwen3-coder-30b-a3b-ud-q3-k-xl"
POOLED = "http://127.0.0.1:11450"
EVERYDAY = "http://127.0.0.1:11436"
CTX = 49152
FAILED, PASSED = [], []

AG._publish_step = lambda step: None      # no event bus write in a test run


def check(name: str, ok, detail=None) -> None:
    (PASSED if ok else FAILED).append(name)
    print(f"ok    {name}" if ok else
          f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


# ---------------------------------------------------------------------------
#   A fake Ollama lane on 127.0.0.1: every request it receives, in order
# ---------------------------------------------------------------------------

class FakeLane:
    """One Ollama lane, real sockets and real JSON. `requests` is what arrived,
    in arrival order: ("GET"|"POST", path, body-or-None). `loaded` is what
    /api/ps reports, and a successful native load makes it report that model at
    the window asked for - as Ollama keeps the runner resident."""

    def __init__(self) -> None:
        self.requests: list = []
        self.loaded: list = []
        self.fail_load = False
        self.lock = threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj, status: int = 200):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _record(self, method: str, body=None):
                with fake.lock:
                    fake.requests.append((method, self.path, body))

            def do_GET(self):
                self._record("GET")
                if self.path == "/api/ps":
                    with fake.lock:
                        return self._json({"models": [dict(r) for r in fake.loaded]})
                self.send_error(404)

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = json.loads(raw or b"{}")
                self._record("POST", body)
                if self.path == "/api/show":
                    return self._json({"capabilities": ["completion", "tools"],
                                       "parameters": "num_ctx                        49152"})
                if self.path == "/api/generate":
                    if fake.fail_load:
                        return self._json({"error": "the lane refused the load"},
                                          status=500)
                    with fake.lock:
                        fake.loaded = [{
                            "name": f"{body.get('model')}:latest",
                            "context_length": int((body.get("options") or {})
                                                  .get("num_ctx") or 0)}]
                    return self._json({"model": body.get("model"), "response": "",
                                       "done": True, "done_reason": "load"})
                if self.path == "/v1/chat/completions":
                    data = W.stream([("content", "ok"), ("done", "stop")],
                                    model=str(body.get("model") or MODEL))
                    self.send_response(200)
                    self.send_header("Content-Type", W.CONTENT_TYPE_STREAM)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_error(404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.port = int(self.server.server_address[1])
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def paths(self, method: str = "POST") -> list:
        with self.lock:
            return [path for m, path, _b in self.requests if m == method]

    def bodies(self, path: str) -> list:
        with self.lock:
            return [b for m, p, b in self.requests if m == "POST" and p == path]

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class pooled_port:
    """Point the pooled port constant at the fake lane, and put it back."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.real = int(LANES.POOLED_PORT)

    def __enter__(self):
        LANES.POOLED_PORT = self.port
        return self

    def __exit__(self, *exc):
        LANES.POOLED_PORT = self.real
        return False


def last_preload() -> dict:
    """POOLED_PRELOAD_LAST as the module holds it ({} when the seam is absent,
    so a build without it reports a failure instead of crashing)."""
    return dict(getattr(AG, "POOLED_PRELOAD_LAST", {}) or {})


def a_turn(lane: FakeLane, *, announce=None) -> dict:
    """One REAL `run_local_turn` against the fake lane, no tools."""
    AG._CTX_CACHE.clear()
    AG._TOOLS_CACHE.clear()
    lock = getattr(AG, "_POOLED_PRELOAD_LOCK", None)
    if lock is not None:
        with lock:
            AG.POOLED_PRELOAD_LAST.clear()
    return AG.run_local_turn(
        [{"role": "user", "content": "hi"}], MODEL,
        ollama_url=lane.url, stream_out=lambda b: None,
        enabled_tools=set(), announce=announce, lane_choice=None,
        request={"conversation_id": "conv-f2", "stream": True,
                 "messages": [{"role": "user", "content": "hi"}]})


def first_index(paths: list, want: str) -> int:
    return paths.index(want) if want in paths else -1


# ---------------------------------------------------------------------------
#   The lane the seam acts on is the REAL pooled predicate
# ---------------------------------------------------------------------------

def the_seam_only_targets_the_pooled_lane() -> None:
    check("F2: the one lane this touches is 11450, the pooled lane",
          AG._pooled_num_ctx(POOLED) == CTX, AG._pooled_num_ctx(POOLED))
    check("F2: the everyday lane asks for no preload",
          AG._pooled_num_ctx(EVERYDAY) is None, AG._pooled_num_ctx(EVERYDAY))
    check("F2: a request with no address asks for no preload",
          AG._pooled_num_ctx("") is None and AG._pooled_num_ctx(None) is None,
          (AG._pooled_num_ctx(""), AG._pooled_num_ctx(None)))


# ---------------------------------------------------------------------------
#   (a) a COLD pooled turn preloads the native call BEFORE the /v1 turn
# ---------------------------------------------------------------------------

def a_cold_pooled_turn_preloads_before_it_asks() -> None:
    lane = FakeLane()
    try:
        with pooled_port(lane.port):
            out = a_turn(lane)
        posts = lane.paths("POST")
        check("F2a: a cold pooled turn sends the native preload",
              first_index(posts, "/api/generate") >= 0, posts)
        check("F2a: ... BEFORE the /v1/chat/completions turn",
              -1 < first_index(posts, "/api/generate")
              < first_index(posts, "/v1/chat/completions"), posts)
        bodies = lane.bodies("/api/generate")
        check("F2a: ... with the same model and options.num_ctx = 49,152",
              bodies == [{"model": MODEL, "options": {"num_ctx": CTX}}], bodies)
        check("F2a: the preload is the only one this turn sends",
              len(bodies) == 1, bodies)
        v1 = lane.bodies("/v1/chat/completions")
        check("F2a: the real turn still names its window and still streams",
              len(v1) == 1 and v1[0].get("options") == {"num_ctx": CTX}
              and v1[0].get("stream") is True, v1)
        check("F2a: ... and it is the answer that was asked for",
              out.get("finish_reason") == "stop" and out.get("answer") == "ok",
              out)
        check("F2a: the record says the lane was warmed, at which window",
              last_preload().get("state") == "warmed"
              and last_preload().get("ctx") == CTX,
              last_preload())
    finally:
        lane.stop()


# ---------------------------------------------------------------------------
#   (b) no duplicate preload when the lane already holds the window
# ---------------------------------------------------------------------------

def a_warm_pooled_turn_sends_no_duplicate_preload() -> None:
    lane = FakeLane()
    try:
        lane.loaded = [{"name": MODEL + ":latest", "context_length": CTX}]
        with pooled_port(lane.port):
            out = a_turn(lane)
        posts = lane.paths("POST")
        check("F2b: a lane already loaded at 49,152 sends NO preload",
              first_index(posts, "/api/generate") < 0, posts)
        check("F2b: ... and the real turn still goes, once, naming its window",
              len(lane.bodies("/v1/chat/completions")) == 1
              and lane.bodies("/v1/chat/completions")[0].get("options")
              == {"num_ctx": CTX}, lane.paths("POST"))
        check("F2b: the record says it was already there (no call was made)",
              last_preload().get("state") == "already",
              last_preload())
        check("F2b: ... and the answer still came",
              out.get("finish_reason") == "stop" and out.get("answer") == "ok", out)
    finally:
        lane.stop()


def a_lane_loaded_below_the_window_is_reloaded_at_it() -> None:
    # 8,192 is not a guess: it is what the live 0.2.441 install measured a cold
    # /v1 turn loading the 30B at (2026-11-09 04:00 PT, DEF-034's 2nd finding).
    lane = FakeLane()
    try:
        lane.loaded = [{"name": MODEL + ":latest", "context_length": 8192}]
        with pooled_port(lane.port):
            a_turn(lane)
        posts = lane.paths("POST")
        check("F2b2: a lane loaded at 8,192 IS preloaded, before the /v1 turn",
              -1 < first_index(posts, "/api/generate")
              < first_index(posts, "/v1/chat/completions"), posts)
        check("F2b2: ... at 49,152, so the reload carries the measured window",
              lane.bodies("/api/generate")
              == [{"model": MODEL, "options": {"num_ctx": CTX}}],
              lane.bodies("/api/generate"))
        check("F2b2: the record names the old size as the reason",
              last_preload().get("state") == "warmed"
              and "8,192" in str(last_preload().get("why")),
              last_preload())
    finally:
        lane.stop()


# ---------------------------------------------------------------------------
#   (c) a failed preload is recorded, said, and loses nothing
# ---------------------------------------------------------------------------

def a_failed_preload_still_runs_the_real_turn() -> None:
    lane = FakeLane()
    noted: list = []
    try:
        lane.fail_load = True
        with pooled_port(lane.port):
            out = a_turn(lane, announce=noted.append)
        posts = lane.paths("POST")
        check("F2c: the preload was tried, and failed",
              first_index(posts, "/api/generate") >= 0, posts)
        check("F2c: the real turn still dispatched AFTER the failed preload",
              -1 < first_index(posts, "/api/generate")
              < first_index(posts, "/v1/chat/completions"), posts)
        check("F2c: ... and the owner still got the answer",
              out.get("finish_reason") == "stop" and out.get("answer") == "ok",
              out)
        check("F2c: the failure is recorded, not swallowed",
              last_preload().get("state") == "failed"
              and "HTTP 500" in str(last_preload().get("why")),
              last_preload())
        said = [line for line in noted if "49,152-token window" in str(line)]
        check("F2c: ... and said in one plain line that the answer still ran",
              len(said) == 1 and "still ran" in said[0], noted)
    finally:
        lane.stop()


# ---------------------------------------------------------------------------
#   (d) the everyday and coding lanes keep exactly today's behaviour
# ---------------------------------------------------------------------------

def an_everyday_lane_is_untouched() -> None:
    lane = FakeLane()
    try:
        lane.loaded = [{"name": "qwen3.5:9b", "context_length": 196608}]
        # The REAL pooled port (11450), so this fake lane is not the pooled one.
        out = a_turn(lane)
        posts = lane.paths("POST")
        check("F2d: an everyday/coding lane sends no preload at all",
              first_index(posts, "/api/generate") < 0, posts)
        check("F2d: ... its /v1 request gains no options field, as before",
              len(lane.bodies("/v1/chat/completions")) == 1
              and "options" not in lane.bodies("/v1/chat/completions")[0],
              lane.bodies("/v1/chat/completions"))
        check("F2d: ... the record says it was not the pooled lane",
              last_preload().get("state") == "off",
              last_preload())
        check("F2d: ... and it still answers",
              out.get("finish_reason") == "stop" and out.get("answer") == "ok", out)
    finally:
        lane.stop()


def main() -> int:
    print("-- the pooled predicate --")
    the_seam_only_targets_the_pooled_lane()
    print("\n-- (a) a cold pooled turn --")
    a_cold_pooled_turn_preloads_before_it_asks()
    print("\n-- (b) no duplicate preload --")
    a_warm_pooled_turn_sends_no_duplicate_preload()
    a_lane_loaded_below_the_window_is_reloaded_at_it()
    print("\n-- (c) a failed preload --")
    a_failed_preload_still_runs_the_real_turn()
    print("\n-- (d) the everyday lane --")
    an_everyday_lane_is_untouched()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    code = main()
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
