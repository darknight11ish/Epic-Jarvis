"""The pooled three-card lane can carry deep_think and creative too.

    python3 backend/test_pooled_modes.py

WHAT THIS SUITE OWNS (Wave-9 Lane 3, 2026-11-07):
  1. `pooled_profile` reads the modes from `jarvis_big_coder.MODES` when it is
     beside this backend, and falls back to the lane's own coding constants
     when it is not - with the coding lane byte-identical either way.
  2. `start_pooled_lane(mode=...)` announces, pauses, loads and reports THAT
     mode's model, window and measured words; the coding default (no mode) is
     exactly the message it always had.
  3. `stop_pooled_lane()` unloads WHATEVER mode is loaded, read from /api/ps
     once - so stopping after a deep-think or creative session leaves no model
     resident.
  4. A misspelled mode is a 400, not a silent coding lane.
  5. No shipped preset default is changed.

No pytest. Run it directly; the exit code is the verdict.
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_model_lanes.py")
require_shipped("jarvis_big_coder.py")

import jarvis_big_coder as B  # noqa: E402
import jarvis_model_lanes as L  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Allow:
    allowed = True
    outcome = "allowed"


class Engine:
    """A stand-in for `jarvis_big_coder` that records the calls it is given."""

    MODES = B.MODES
    LANES = B.LANES

    def __init__(self, rows=None, load_ok=True):
        self.rows = list(rows or [])
        self.load_ok = load_ok
        self.calls = []
        self.card_kw = {}
        self.loaded = {}

    def ps(self, url):
        self.calls.append(("ps", url))
        return [dict(r) for r in self.rows]

    def loaded_row(self, rows, model):
        for row in rows or ():
            if row.get("name") == model:
                return row
        return None

    def spill_bytes(self, row):
        return int((row or {}).get("size") or 0) - int(
            (row or {}).get("size_vram") or 0)

    def card_text_start(self, **kw):
        self.card_kw = dict(kw)
        return f"Use the {kw.get('mode')} model at {kw.get('num_ctx')}."

    def announce_pause(self, words):
        self.calls.append(("announce", words))

    def server_start(self):
        self.calls.append(("server_start",))
        return {"ok": True, "url": "http://127.0.0.1:11450", "owned": True}

    def pause_lanes(self):
        self.calls.append(("pause",))
        return {"ok": True, "why": "", "proof": ["paused"]}

    def restore_lanes(self):
        self.calls.append(("restore",))
        return {"ok": True, "why": "", "wrong": [], "proof": ["restored"]}

    def load_coder(self, **kw):
        self.loaded = dict(kw)
        self.calls.append(("load", kw.get("mode"), kw.get("num_ctx")))
        if not self.load_ok:
            return {"ok": False, "why": "it did not fit", "proof": []}
        row = {"name": B.mode_profile(kw.get("mode") or "coding").model,
               "size": 100, "size_vram": 100,
               "context_length": kw.get("num_ctx")}
        self.rows = [row]
        return {"ok": True, "why": "", "proof": ["loaded"], "row": row}

    def unload_coder(self, **kw):
        self.calls.append(("unload", kw.get("mode"), kw.get("model")))
        self.rows = []
        return {"ok": True, "why": "", "proof": ["nothing is resident"]}

    def server_stop(self):
        self.calls.append(("server_stop",))
        return {"stopped": True, "why": ""}

    def lane_lines(self):
        return ["qwen3.5:9b at 196,608 tokens on the RTX 2060 (port 11436)",
                "qwen3:8b at 16,384 tokens on the RTX 2080 SUPER (port 11435)"]


# ==========================================================================
#   1. pooled_profile
# ==========================================================================

def t_pooled_profile_reads_the_modes_and_keeps_the_coding_default():
    eng = Engine()
    coding = L.pooled_profile("coding", engine=eng)
    check("coding is the lane's own model", coding["model"] == L.POOLED_MODEL)
    check("coding is the lane's own window",
          coding["num_ctx"] == L.POOLED_CTX == 49152)
    check("coding keeps the lane's own measured words",
          coding["measured_words"] == L.POOLED_MEASURED_WORDS)
    deep = L.pooled_profile("deep_think", engine=eng)
    check("deep_think is gemma4:31b-it-qat",
          deep["model"] == "gemma4:31b-it-qat")
    check("deep_think's window is its measured 32,768",
          deep["num_ctx"] == 32768)
    creative = L.pooled_profile("creative", engine=eng)
    check("creative is the 27B uncensored build",
          "27B-Uncensored" in creative["model"])
    check("creative's window is its measured 32,768",
          creative["num_ctx"] == 32768)
    check("the default profile is coding",
          L.pooled_profile(engine=eng)["key"] == "coding")
    try:
        L.pooled_profile("vibes", engine=eng)
        raised = False
    except ValueError as exc:
        raised = "not one of the pooled modes" in str(exc)
    check("a misspelled mode raises", raised)
    class Bare:
        LANES = B.LANES
    fallback = L.pooled_profile("coding", engine=Bare())
    check("a backend without the big-coder modes still describes coding",
          fallback["model"] == L.POOLED_MODEL and fallback["num_ctx"] == 49152)
    try:
        L.pooled_profile("deep_think", engine=Bare())
        raised2 = False
    except ValueError as exc:
        raised2 = "coding lane only" in str(exc) or "not one of" in str(exc)
    check("and honestly refuses the modes it cannot describe", raised2)

    # wave-14: the preset layer's own row reaches the lane profile, with its
    # measured spill allowance (0 B for Medical), even without a big-coder
    # engine - and the big-coder module can resolve the same row by name.
    medical = L.pooled_profile("medical", engine=eng)
    check("medical is the preset layer's medgemma:27b",
          medical["model"] == "medgemma:27b")
    check("medical's window is its measured 32,768",
          medical["num_ctx"] == 32768)
    check("medical's measured spill allowance is 0 bytes",
          medical["spill_allowance"] == 0)
    bare_medical = L.pooled_profile("medical", engine=Bare())
    check("... and the preset row needs no big-coder engine",
          bare_medical["model"] == "medgemma:27b"
          and bare_medical["num_ctx"] == 32768)
    check("the big-coder module resolves medical too",
          B.mode_profile("medical").key == "medical"
          and B.mode_profile("medical").num_ctx == 32768)
    check("... without widening MODE_KEYS",
          B.MODE_KEYS == ("coding", "deep_think", "creative"))


# ==========================================================================
#   2. start_pooled_lane
# ==========================================================================

def t_starting_deep_think_announces_and_loads_its_own_window():
    eng = Engine()
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Allow(),
                                     tasks=lambda: [], mode="deep_think",
                                     by="test")
    m = B.mode_profile("deep_think")
    check("a deep-think start is accepted", code == 200, (code, body))
    check("the announcement used the deep-think card text",
          eng.card_kw.get("mode") == "deep_think"
          and eng.card_kw.get("num_ctx") == m.num_ctx, eng.card_kw)
    check("the load asked for the deep-think mode",
          eng.loaded.get("mode") == "deep_think"
          and eng.loaded.get("num_ctx") == m.num_ctx
          and eng.loaded.get("allow_spill") == 0, eng.loaded)
    check("the answer names the mode, model and window",
          body.get("mode") == "deep_think" and body.get("model") == m.model
          and body.get("num_ctx") == m.num_ctx, body)
    check("the message says deep think, not coding",
          "deep think" in body["message"] and "coding" not in body["message"])


def t_starting_medical_loads_the_preset_rows_own_window_and_mode():
    eng = Engine()
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Allow(),
                                     tasks=lambda: [], mode="medical", by="test")
    check("a Medical start is accepted", code == 200, (code, body))
    check("the load asked for the preset row's own mode, 32,768 window and its "
          "measured 0 B spill allowance",
          eng.loaded.get("mode") == "medical"
          and eng.loaded.get("num_ctx") == 32768
          and eng.loaded.get("allow_spill") == 0, eng.loaded)
    check("the announcement is the preset row's own card",
          eng.card_kw.get("mode") == "medical"
          and eng.card_kw.get("num_ctx") == 32768, eng.card_kw)
    check("the answer names medgemma, the mode and the window",
          body.get("mode") == "medical" and body.get("model") == "medgemma:27b"
          and body.get("num_ctx") == 32768, body)
    check("the message says medical, never coding",
          "medical" in body["message"].lower()
          and "coding" not in body["message"])


def t_the_coding_start_is_still_the_exact_shipped_message():
    eng = Engine()
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Allow(),
                                     tasks=lambda: [])
    check("the coding start is accepted", code == 200, (code, body))
    check("the load asked for the coding mode at its window",
          eng.loaded.get("mode") == "coding"
          and eng.loaded.get("num_ctx") == 49152, eng.loaded)
    check("the shipped coding message is byte-identical",
          body.get("message") ==
          "The coding model is running across all three cards at 49,152 "
          "tokens. The two lane models are paused and come back when you stop "
          "it or apply another preset.", body.get("message"))


def t_a_loaded_mode_is_reported_as_already_holding_the_lane():
    gemma = B.mode_profile("deep_think")
    eng = Engine(rows=[{"name": gemma.model, "size": 1, "size_vram": 1,
                        "context_length": gemma.num_ctx}])
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Allow(),
                                     tasks=lambda: [], mode="deep_think")
    check("starting the loaded mode changes nothing",
          code == 200 and body.get("changed") is False, body)
    check("and says which mode it is already holding",
          "deep think model" in body.get("message", ""), body.get("message"))
    check("no second load happened", eng.loaded == {})
    code2, body2 = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Allow(),
                                       tasks=lambda: [], mode="coding")
    check("a different mode is NOT reported as the one already running",
          code2 == 200 and "changed" in body2)


def t_a_bad_mode_is_a_400_and_a_refused_card_loads_nothing():
    eng = Engine()
    code, body = L.start_pooled_lane(engine=eng, mode="vibes")
    check("a misspelled mode is a 400", code == 400, (code, body))
    check("and nothing was announced, paused or loaded",
          not any(c[0] in ("announce", "pause", "load") for c in eng.calls))
    code2, body2 = L.start_pooled_lane(
        engine=Engine(load_ok=False), gate=lambda *a, **k: Allow(),
        tasks=lambda: [], mode="creative")
    check("a load that does not fit is a 503 with the reason",
          code2 == 503 and body2.get("error") == "it did not fit", (code2, body2))


# ==========================================================================
#   3. stop_pooled_lane unloads whatever mode is loaded
# ==========================================================================

def t_stopping_unloads_the_loaded_mode_not_always_coding():
    gemma = B.mode_profile("deep_think")
    eng = Engine(rows=[{"name": gemma.model, "size": 1, "size_vram": 1,
                        "context_length": gemma.num_ctx}])
    code, body = L.stop_pooled_lane(engine=eng)
    check("a stop with no mode is accepted", code == 200, (code, body))
    check("it unloads the model that is really loaded, by name",
          eng.calls[1][0] == "unload"
          and eng.calls[1][1] == "deep_think"
          and eng.calls[1][2] == gemma.model, eng.calls)
    check("the message names deep think, not coding",
          "deep think model is stopped" in body["message"], body["message"])
    check("one /api/ps read decides the whole stop",
          len([c for c in eng.calls if c[0] == "ps"]) == 1, eng.calls)


def t_stopping_the_coding_lane_keeps_the_shipped_message():
    eng = Engine(rows=[{"name": L.POOLED_MODEL, "size": 1, "size_vram": 1,
                        "context_length": 49152}])
    code, body = L.stop_pooled_lane(engine=eng)
    check("the coding stop is accepted", code == 200, (code, body))
    check("it unloads the coding model",
          eng.calls[1][1] == "coding" and eng.calls[1][2] == L.POOLED_MODEL,
          eng.calls)
    check("and the shipped coding stop message is byte-identical",
          body["message"].startswith(
              "The coding model is stopped, the three-card server this app "
              "started is stopped, and both lane models are back: "),
          body["message"])


# ==========================================================================
#   4. No shipped preset default moved
# ==========================================================================

def t_no_preset_default_is_changed():
    import jarvis_presets as P  # noqa: E402
    presets = {p.id: p for p in P.PRESETS}
    check("the Coding preset still runs the shipped q3 coder",
          presets["coding"].model == "qwen3-coder-30b-a3b-ud-q3-k-xl")
    check("the Coding preset still uses the pooled lane",
          presets["coding"].lane == "pooled")
    check("the Coding preset's window is unchanged",
          int(presets["coding"].context) == 49152)
    check("deep_think and creative are not offered as presets yet",
          all(m.model not in {p.model for p in P.PRESETS}
              for m in B.MODES if m.key != "coding"))


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
