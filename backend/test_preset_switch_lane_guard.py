"""DEF-088: a preset switch may not load the wrong model on the wrong lane.

    python3 test_preset_switch_lane_guard.py

No pytest, no Ollama, no network beyond a fake lane this suite starts on its
own ephemeral 127.0.0.1 port. Nothing is read from or written to 11436, 11435
or 11450, and no state file outside a temporary folder is touched.

THE DEFECT THIS PINS (measured on the live install 2026-11-17, the A2 field
test, docs/defect-register.tsv DEF-088). Applying `coding` then `general`
reported success, and afterwards port 11436 - the everyday lane, ONE 12 GB card
- was holding the pooled 14.44 GB coder at Ollama's 8,192 default, 3.76 GB of
it spilled to the CPU, while `model-state.json` said `current: qwen3.5:9b` and
`presets-choice.json` said `general`. Three code faults made that happen, and
each one is checked here BY CAPTURING THE REQUESTS, never by reading source
text:

  1. `jarvis_presets._switch_for_the_owner` ran the tripwire on the OUTGOING
     model - after a heavy preset, the pooled coder - against
     `jarvis_models.OLLAMA`, the everyday lane. Sixteen `/api/generate`
     requests naming the coder were measured on the unfixed code.
  2. `jarvis_models._probe_asker` sent no `num_ctx`, so even a model that CAN
     run on the lane was re-loaded at Ollama's own default and threw away the
     window the lane serves (196,608 on 11436).
  3. `apply_preset` answered `ok` on the strength of file writes, without ever
     reading the lane back.

WHAT IS DRIVEN, and by whom:

  * the app-click road through the REAL `apply_preset` and the REAL
    `_switch_for_the_owner` - only the lane, the clock and the receipt book are
    fakes;
  * the carded model road through the REAL `jarvis_models.switch_to`;
  * `_default_verify_lane` against the same fake lane, for the wrong model, the
    spilled model, the too-small window and the empty lane.

WHICH COPIES. `jarvis_presets.py` is shipped whole, so the copy under test is
`backend/jarvis_presets.py`. `jarvis_models.py` lives only on the owner's PC
and in the published base (`backend/_base.py`'s OWNER_ONLY rule), so the copy
under test is `jarvis-backend/jarvis_models.py`, and this suite prints which
one it read.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# --- a fake lane first, so OLLAMA_URL can name it before anything imports ----
CODER = "qwen3-coder-30b-a3b-ud-q3-k-xl"
EVERYDAY = "gemma4:26b-a4b-it-qat"   # the General preset's model since 2026-11-18
SECOND = "qwen3:8b"        # the retired coding lane's model, still in the fake's /api/tags
LANE_CTX = 196608          # the everyday lane's window (jarvis_big_coder.LANES)
LIVE_PORTS = (11434, 11435, 11436, 11450)

TMP = Path(tempfile.mkdtemp(prefix="def088-guard-"))


def _row(model, ctx, spill=0):
    size = 6_100_000_000 + int(spill)
    return {"name": model, "context_length": int(ctx),
            "size": size, "size_vram": size - int(spill)}


class FakeLane:
    """One Ollama-shaped lane: records every request, answers three routes."""

    def __init__(self):
        self.posts = []
        self.ps_rows = []
        self.tags = [{"name": CODER}, {"name": EVERYDAY}, {"name": SECOND},
                     {"name": "qwen3.5:4b"}]
        self.requests = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):        # keep the suite's output clean
                pass

            def _json(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                outer.requests += 1
                if self.path.endswith("/api/tags"):
                    return self._json({"models": outer.tags})
                if self.path.endswith("/api/ps"):
                    return self._json({"models": outer.ps_rows})
                return self._json({})

            def do_POST(self):
                outer.requests += 1
                size = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(size).decode("utf-8", "replace")
                try:
                    body = json.loads(raw)
                except Exception:
                    body = {"_raw": raw}
                outer.posts.append({"path": self.path, "body": body})
                return self._json({"response": "Paris", "done": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = int(self.server.server_address[1])
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def generate_posts(self):
        return [p["body"] for p in self.posts if p["path"].endswith("/api/generate")]

    def stop(self):
        self.server.shutdown()


LANE = FakeLane()
assert LANE.port not in LIVE_PORTS, f"the fake lane took a LIVE port: {LANE.port}"

# --- isolation BEFORE the backend modules are imported ----------------------
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_MODEL_STATE"] = str(TMP / "model-state.json")
os.environ["JARVIS_TRIPWIRE_STATE"] = str(TMP / "tripwire.json")
os.environ["OLLAMA_URL"] = LANE.url          # every default lane address is the fake

from _where import REPO, explain             # noqa: E402
import _base                                  # noqa: E402

BASE = _base.folder("jarvis_models.py", "jarvis_hud.py")
if BASE is not None:
    _base.put_on_path(BASE)


def _stub_receipts():
    """A receipt book that records nothing: the live one is the owner's own DB."""
    import types
    fake = types.ModuleType("jarvis_receipts")
    fake.register_restorer = lambda *a, **k: True
    fake.record = lambda *a, **k: "def088-suite"
    fake.discard = lambda *a, **k: True
    sys.modules["jarvis_receipts"] = fake


_stub_receipts()

import jarvis_presets as P                    # noqa: E402  (backend/, shipped whole)
import jarvis_models as M                     # noqa: E402  (the base's copy)
import jarvis_big_coder as BIG                # noqa: E402

# --- the seams: everything the apply touches, pointed at the fake -----------
M.OLLAMA = LANE.url
M.STATE = TMP / "model-state.json"
P._config_dir = lambda: TMP
P._lane_url = lambda key: LANE.url

_PASSED: list = []
_FAILED: list = []


def check(name, cond, detail=""):
    (_PASSED if cond else _FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _Allowed:
    allowed = True
    outcome = "approved"
    reason = "the suite's own yes"


M._gate = lambda *a, **k: _Allowed()


def _seed(current=CODER, previous=EVERYDAY):
    M.STATE.write_text(json.dumps({"current": current, "previous": previous,
                                   "switches": []}), "utf-8")
    for name in ("presets-choice.json", "presets-active-lane.json"):
        try:
            (TMP / name).unlink()
        except FileNotFoundError:
            pass


def _apply_general(ps_rows, current=CODER):
    """Drive the real app-click road for `general` against the fake lane."""
    LANE.ps_rows = list(ps_rows)
    LANE.posts = []
    _seed(current=current)
    return P.apply_preset(
        "general", owner_ui=True,
        start_lane=lambda key, mode="": (200, {"ok": True, "changed": False}),
        stop_pooled=lambda: {"ok": True, "ran": False},
        verify_lane=P._default_verify_lane)


# --------------------------------------------------------------------------
#   The four things the owner must never see again
# --------------------------------------------------------------------------

def t_a_pooled_outgoing_model_is_never_probed_on_the_everyday_lane():
    code, out = _apply_general([_row(EVERYDAY, LANE_CTX)])
    bodies = LANE.generate_posts()
    asked = [b.get("model") for b in bodies]
    check("the apply succeeds on the ordinary road", code == 200 and out.get("ok") is True,
          (code, out.get("error")))
    check("NO probe asks the everyday lane for the pooled coder",
          not [b for b in bodies if b.get("model") == CODER], asked)
    check("the smoke test is about the model that was switched IN",
          (out.get("switched") or {}).get("tripwire", {}).get("model") == EVERYDAY,
          (out.get("switched") or {}).get("tripwire"))
    check("every probe names the lane's own window",
          bool(bodies) and all((b.get("options") or {}).get("num_ctx") == LANE_CTX
                               for b in bodies),
          [(b.get("model"), (b.get("options") or {}).get("num_ctx")) for b in bodies])
    check("the lane was read back BEFORE ok",
          (out.get("lane_check") or {}).get("checked") is True
          and (out.get("lane_check") or {}).get("ok") is True,
          out.get("lane_check"))


def t_the_window_comes_from_the_lane_not_from_a_default():
    """The reader answers a KNOWN lane's configured window, and None otherwise.

    Until 2026-11-18 this read a SECOND lane's window (11435 = 16,384), and it
    read it from the owner's LIVE lane: the check passed at the desk only
    because this PC still ran `qwen3:8b` there, and CI - where nothing answers
    on 11435 - failed it. That lane is now retired ("i dont need a separate
    coding lane on any preset. each preset should be dedicated to one preset
    local ai model"), so there is no second configured window to read and no
    live port to read it from. What replaces it is the retirement itself plus
    the rule that made the reader worth testing: it answers a lane's CONFIGURED
    window when it knows the lane, and None - never Ollama's own default, never
    a guessed number - when it does not.
    """
    LANE.ps_rows = [_row(EVERYDAY, LANE_CTX)]
    check("the program configures exactly ONE lane, the everyday one on 11436",
          [int(getattr(lane, "port", 0) or 0) for lane in BIG.LANES] == [11436],
          [getattr(lane, "port", None) for lane in BIG.LANES])
    check("11436's configured window is 196608",
          M.lane_num_ctx("http://127.0.0.1:11436") == LANE_CTX,
          M.lane_num_ctx("http://127.0.0.1:11436"))
    check("nothing configures the retired coding lane on 11435",
          not [lane for lane in BIG.LANES
               if int(getattr(lane, "port", 0) or 0) == 11435],
          [(getattr(lane, "port", None), getattr(lane, "model", None))
           for lane in BIG.LANES])
    check("a lane this repo has never seen answers its own served window",
          M.lane_num_ctx(LANE.url) == LANE_CTX, M.lane_num_ctx(LANE.url))
    LANE.ps_rows = []
    check("...and a lane holding nothing answers None, never a default window",
          M.lane_num_ctx(LANE.url) is None, M.lane_num_ctx(LANE.url))


def t_a_lane_holding_the_wrong_model_fails_the_apply():
    code, out = _apply_general([_row(CODER, 8192, spill=3_762_835_946)])
    error = str(out.get("error") or "")
    check("a lane holding the wrong model is a FAILURE, not ok",
          code >= 400 and out.get("ok") is False and out.get("changed") is False,
          (code, error))
    check("the failure names what the lane really held", CODER in error, error)
    check("the model record is rolled back, not left saying success",
          M._read_state().get("current") == CODER, M._read_state())
    check("the chosen preset is not left at general", P.choice() != "general", P.choice())


def t_the_right_model_with_spill_or_a_smaller_window_fails_too():
    LANE.ps_rows = [_row(EVERYDAY, LANE_CTX, spill=1_048_576)]
    spilled = P._default_verify_lane(LANE.url, EVERYDAY, LANE_CTX)
    check("the right model with CPU spill is a failure",
          spilled.get("ok") is False and "spill" in str(spilled.get("why")), spilled)
    LANE.ps_rows = [_row(EVERYDAY, 8192)]
    small = P._default_verify_lane(LANE.url, EVERYDAY, LANE_CTX)
    check("the right model at 8192 when the preset names 196608 is a failure",
          small.get("ok") is False and "8192" in str(small.get("why")), small)


def t_an_empty_lane_is_not_a_failure():
    code, out = _apply_general([])
    lane_check = out.get("lane_check") or {}
    check("a lane holding nothing is a successful apply",
          code == 200 and out.get("ok") is True, (code, out.get("error")))
    check("...and it says nothing was left on the lane",
          lane_check.get("ok") is True and lane_check.get("loaded") == [], lane_check)


def t_an_unknown_window_does_not_silently_switch_the_tripwire_off():
    """A guard must never disable the smoke test where it cannot know better.

    A lane whose window cannot be established is NOT refused: the request goes
    out WITHOUT `num_ctx` - exactly what `main` sent - rather than not going out
    at all. Refusing here would stop the tripwire on every install whose chat
    lane is not one of the two named lane ports (`OLLAMA_URL` unset means
    11434), and a check disabled by a guard is worse than the gap it closes.
    Naming a guessed window would be worse still, so the field is simply absent.
    """
    LANE.ps_rows = []
    check("an unknown window is NOT a refusal",
          M.probe_refusal(EVERYDAY, LANE.url) == "", M.probe_refusal(EVERYDAY, LANE.url))
    LANE.posts = []
    ask = M._probe_asker(EVERYDAY, url=LANE.url)
    answer = ask("What is the capital of France?")
    bodies = LANE.generate_posts()
    check("...the probe still runs, so the check is not silently gone",
          answer == "Paris" and len(bodies) == 1, (answer, len(bodies)))
    check("...and it names no window rather than a guessed one",
          "num_ctx" not in ((bodies[0].get("options") or {}) if bodies else {}),
          bodies[0].get("options") if bodies else None)


def t_the_pooled_model_is_refused_by_name_and_the_everyday_one_is_not():
    refusal = M.probe_refusal(CODER, "http://127.0.0.1:11436")
    check("the guard is the pooled-model rule, in plain words", "pooled" in refusal,
          refusal)
    check("the everyday model is still allowed on the everyday lane",
          M.probe_refusal(EVERYDAY, "http://127.0.0.1:11436") == "",
          M.probe_refusal(EVERYDAY, "http://127.0.0.1:11436"))


def t_the_carded_model_road_has_the_same_guard():
    LANE.ps_rows = [_row(EVERYDAY, LANE_CTX)]
    LANE.posts = []
    _seed(current=CODER, previous=EVERYDAY)
    out = M.switch_to(EVERYDAY)
    bodies = LANE.generate_posts()
    asked = [b.get("model") for b in bodies]
    check("the carded switch still succeeds", out.get("ok") is True, out)
    check("it does not probe the pooled model on the everyday lane",
          not [b for b in bodies if b.get("model") == CODER], asked)
    check("its probes name the lane's window too",
          bool(bodies) and all((b.get("options") or {}).get("num_ctx") == LANE_CTX
                               for b in bodies),
          [(b.get("model"), (b.get("options") or {}).get("num_ctx")) for b in bodies])


def t_the_default_reader_is_real_on_the_pc_and_an_honest_skip_in_a_suite():
    """The seam `apply_preset` uses when nobody injects one."""
    reader = P._verify_lane_for_this_process()
    skipped = reader(LANE.url, EVERYDAY, LANE_CTX)
    check("a suite's default reader says it did NOT check",
          skipped.get("checked") is False and "NOT a pass" in str(skipped.get("proof")),
          skipped)
    LANE.ps_rows = [_row(EVERYDAY, LANE_CTX)]
    real = P._default_verify_lane(LANE.url, EVERYDAY, LANE_CTX)
    check("the real reader does check, and passes a lane that is right",
          real.get("checked") is True and real.get("ok") is True, real)


TESTS = (t_a_pooled_outgoing_model_is_never_probed_on_the_everyday_lane,
         t_the_window_comes_from_the_lane_not_from_a_default,
         t_a_lane_holding_the_wrong_model_fails_the_apply,
         t_the_right_model_with_spill_or_a_smaller_window_fails_too,
         t_an_empty_lane_is_not_a_failure,
         t_an_unknown_window_does_not_silently_switch_the_tripwire_off,
         t_the_pooled_model_is_refused_by_name_and_the_everyday_one_is_not,
         t_the_carded_model_road_has_the_same_guard,
         t_the_default_reader_is_real_on_the_pc_and_an_honest_skip_in_a_suite)


def main() -> int:
    print(f"  file  {_base.which(BASE, 'jarvis_models.py')}")
    print(f"  file  {Path(P.__file__)}")
    print(f"  lane  the fake lane is {LANE.url} (live ports are never opened)")
    try:
        for fn in TESTS:
            try:
                fn()
            except Exception:
                traceback.print_exc()
                _FAILED.append(f"{fn.__name__} raised")
    finally:
        LANE.stop()
    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        print("failed: " + ", ".join(_FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
