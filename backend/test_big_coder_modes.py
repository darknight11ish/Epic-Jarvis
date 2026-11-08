"""The pooled three-card lane carries three modes, and the default did not move.

    python3 backend/test_big_coder_modes.py

WHAT THIS SUITE OWNS (Wave-9 Lane 3, 2026-11-07):
  1. `MODES` is exactly the three the packet names - coding (the shipped
     default), deep_think (`gemma4:31b-it-qat`) and creative
     (`orcarouter/Qwen3.8-27B-Uncensored:q4_K_M`) - each with a measured window.
  2. The DEFAULT is unchanged: `MODEL`, `NUM_CTX`, `card_text_start()` with no
     mode, `load_coder()` with no mode and `handle_post({"action": "start"})`
     all still mean the shipped q3 coding model at 49,152 tokens.
  3. `mode_profile` refuses a typo instead of silently loading the 30B under
     the wrong sentence, and `handle_post` turns that into a 400.
  4. `load_coder(mode=...)` loads THAT mode's model at THAT mode's window with
     THAT mode's zero-spill rule, and proves the window it asked for.
  5. `unload_coder(model=...)` exists so a stop can unload a model this process
     did not start.
  6. `status()` lists the modes and which one is running; `running(mode)` is
     per mode and `running_mode()` answers "which one".
  7. `start(mode=...)` pulls the right model/window and refuses a SECOND mode
     while one is loaded; the shipped coding message is byte-identical.
  8. No shipped preset default is changed by any of this.

No pytest. Run it directly; the exit code is the verdict.
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_big_coder.py")

import jarvis_big_coder as B  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Allow:
    allowed = True
    outcome = "allowed"


class Deny:
    allowed = False
    outcome = "refused"


def _restore(names: dict) -> None:
    for name, value in names.items():
        setattr(B, name, value)


# ==========================================================================
#   1. The modes
# ==========================================================================

def t_the_three_modes_are_the_packets_and_coding_is_the_default():
    keys = tuple(m.key for m in B.MODES)
    check("three modes, coding first", keys == ("coding", "deep_think",
                                                "creative"), keys)
    check("the default is coding", B.DEFAULT_MODE == "coding")
    check("coding is still the shipped q3 coder",
          B.mode_profile("coding").model == "qwen3-coder-30b-a3b-ud-q3-k-xl")
    check("coding is still 49,152 tokens",
          B.mode_profile("coding").num_ctx == 49152)
    check("deep_think is gemma4:31b-it-qat",
          B.mode_profile("deep_think").model == "gemma4:31b-it-qat")
    check("deep_think's measured window is 32,768",
          B.mode_profile("deep_think").num_ctx == 32768)
    check("creative is the 27B uncensored build",
          "27B-Uncensored" in B.mode_profile("creative").model)
    check("creative's measured window is 32,768",
          B.mode_profile("creative").num_ctx == 32768)
    check("every mode has measured words, not a guess",
          all("measured" in m.measured_words for m in B.MODES))
    check("every mode keeps the zero-spill rule",
          all(m.spill_allowance == 0 for m in B.MODES))
    check("every mode needs all three cards",
          all(m.needs_cards == 3 for m in B.MODES))
    check("the coding floor is the owner's own 75 tok/s bar",
          B.mode_profile("coding").decode_floor == 75.0)
    check("the two new modes carry no preset floor (they are not defaults)",
          B.mode_profile("deep_think").decode_floor is None
          and B.mode_profile("creative").decode_floor is None)
    check("the module constants are the coding mode's, unchanged",
          B.MODEL == B.mode_profile("coding").model
          and B.NUM_CTX == B.mode_profile("coding").num_ctx)
    check("modes_view lists all three and marks the default",
          [v["key"] for v in B.modes_view()] == ["coding", "deep_think",
                                                 "creative"]
          and [v["is_default"] for v in B.modes_view()] == [True, False, False])


def t_a_typo_is_refused_not_silently_the_coder():
    try:
        B.mode_profile("deep-think")
        raised = False
    except ValueError as exc:
        raised = "not one of the pooled modes" in str(exc)
    check("a misspelled mode raises with the list", raised)
    code, body = B.handle_post({"action": "start", "mode": "vibes"})
    check("the POST route turns it into a 400",
          code == 400 and "not one of the pooled modes" in body["error"])


# ==========================================================================
#   2. The coding default did not move
# ==========================================================================

def t_the_coding_card_text_and_load_are_unchanged():
    names = {"cards_in_pc": B.cards_in_pc}
    B.cards_in_pc = lambda: [object(), object(), object()]
    try:
        text = B.card_text_start()
        text_named = B.card_text_start(mode="coding")
    finally:
        _restore(names)
    check("the default card text names the shipped coder",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in text)
    check("calling it with no mode and with mode='coding' is the same words",
          text == text_named)
    check("the default window is still 49,152",
          "49,152 tokens" in text)
    check("it still uses the phrase 'big coding model'",
          "big coding model" in text)
    for key in ("deep_think", "creative"):
        names = {"cards_in_pc": B.cards_in_pc}
        B.cards_in_pc = lambda: [object(), object(), object()]
        try:
            other = B.card_text_start(mode=key)
        finally:
            _restore(names)
        m = B.mode_profile(key)
        check(f"the {key} card names its own model",
              m.model in other and "qwen3-coder" not in other)
        check(f"the {key} card names its own window",
              f"{m.num_ctx:,} tokens" in other)


def t_no_preset_default_is_changed():
    import jarvis_presets as P  # noqa: E402
    presets = {p.id: p for p in P.PRESETS}
    check("the Coding preset still runs the shipped q3 coder",
          presets["coding"].model == "qwen3-coder-30b-a3b-ud-q3-k-xl")
    check("the Coding preset's window is still 49,152",
          int(presets["coding"].context) == 49152)
    check("the General preset still runs qwen3.5:9b",
          presets["general"].model == "qwen3.5:9b")
    check("no new mode is offered as a preset row",
          all(m.model not in {p.model for p in P.PRESETS}
              for m in B.MODES if m.key != "coding"))


# ==========================================================================
#   3. load_coder / unload_coder are mode-aware
# ==========================================================================

def t_load_coder_loads_the_modes_own_model_and_window():
    for key in ("coding", "deep_think", "creative"):
        names = {"cards_in_pc": B.cards_in_pc, "load": B.load,
                 "ps": B.ps}
        seen = {}

        def load(url, model, ctx):
            seen["loaded"] = (url, model, ctx)
            return True

        def ps(url):
            m = B.mode_profile(key)
            return [{"name": m.model, "size": 1000, "size_vram": 1000,
                     "context_length": m.num_ctx}]

        B.cards_in_pc = lambda: [object(), object(), object()]
        B.load = load
        B.ps = ps
        try:
            out = B.load_coder(url_for=lambda port: "http://127.0.0.1:11450",
                               mode=key)
        finally:
            _restore(names)
        m = B.mode_profile(key)
        check(f"load_coder({key}) loads that mode's model",
              seen.get("loaded") == ("http://127.0.0.1:11450", m.model,
                                     m.num_ctx), seen)
        check(f"load_coder({key}) succeeds on a fully on-card row", out["ok"],
              out)


def t_unload_coder_can_unload_an_explicit_model():
    names = {"ps": B.ps}
    seen = {}

    def ps(url):
        return seen.get("rows", [])

    def load_none(url, model, ctx):
        return True

    def unload(url, model):
        seen["unloaded"] = model
        seen["rows"] = []
        return True

    B.ps = ps
    B.unload = unload
    try:
        out = B.unload_coder(url_for=lambda port: "http://127.0.0.1:11450",
                             mode="coding",
                             model="orcarouter/Qwen3.8-27B-Uncensored:q4_K_M")
    finally:
        _restore(names)
        _restore({"load": B.load})
    check("the explicit model is the one unloaded, not the mode's model",
          seen.get("unloaded") == "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M",
          seen)
    check("unloading it succeeds", out["ok"], out)


# ==========================================================================
#   4. Running state and the start/stop pair
# ==========================================================================

def t_running_is_per_mode_and_names_which_one():
    names = {"ps": B.ps}
    gemma = B.mode_profile("deep_think")
    B.ps = lambda url: [{"name": gemma.model, "size": 1, "size_vram": 1,
                         "context_length": gemma.num_ctx}]
    try:
        check("running('deep_think') is True when its model is loaded",
              B.running("deep_think") is True)
        check("running('coding') is False when a different mode is loaded",
              B.running("coding") is False)
        check("running_mode names the loaded mode",
              B.running_mode() == "deep_think")
        check("status lists the modes and the running one",
              [m["key"] for m in B.status()["modes"]] ==
              ["coding", "deep_think", "creative"]
              and B.status()["running_mode"] == "deep_think")
    finally:
        _restore(names)


def t_start_carries_the_mode_and_refuses_a_second_one():
    name_list = ("enabled", "running_mode", "card_text_start", "server_start",
                 "pause_lanes", "restore_lanes", "server_stop", "_gate",
                 "_announce", "_publish", "_audit", "_set_state", "state")
    saved = {n: getattr(B, n) for n in name_list}
    loaded = {}
    try:
        B.enabled = lambda: True
        B.running_mode = lambda: None
        B.card_text_start = lambda **kw: "Use the deep think model."
        B.server_start = lambda: {"ok": True, "url": "http://127.0.0.1:11450",
                                  "owned": True}
        B.pause_lanes = lambda **kw: {"ok": True, "why": "", "proof": ["paused"]}
        B.restore_lanes = lambda **kw: {"ok": True, "why": "", "proof": ["back"]}
        B.server_stop = lambda: {"stopped": True}
        B._gate = lambda *a, **k: Allow()
        B._announce = lambda words: None
        B._publish = lambda *a, **k: None
        B._audit = lambda *a, **k: None

        def load_coder(**kw):
            loaded.update(kw)
            return {"ok": True, "proof": ["loaded"], "row": {}}

        B.load_coder = load_coder
        code, body = B.start(gate_check=lambda *a, **k: Allow(), tasks=lambda: [],
                             mode="deep_think")
        m = B.mode_profile("deep_think")
        check("start(mode='deep_think') is accepted", code == 200, (code, body))
        check("it asks load_coder for the deep-think mode (which owns its window)",
              loaded.get("mode") == "deep_think", loaded)
        check("the answer names the mode and model",
              body.get("mode") == "deep_think" and body.get("model") == m.model)
        loaded.clear()
        code2, body2 = B.start(gate_check=lambda *a, **k: Allow(),
                               tasks=lambda: [], by="test")
        check("a start with no mode loads the coding mode",
              loaded.get("mode") == "coding", loaded)
        check("and the shipped coding message is unchanged",
              body2.get("message") == (
                  "The big coding model is running on all three cards at "
                  "49,152 tokens. The two models are paused and come back when "
                  "you stop it."), body2.get("message"))
        B.running_mode = lambda: "creative"
        code3, body3 = B.start(gate_check=lambda *a, **k: Allow(),
                               tasks=lambda: [], mode="deep_think")
        check("a second mode is refused while another is loaded",
              code3 == 409 and "already using the three-card server"
              in body3.get("error", ""), (code3, body3))
    finally:
        for n, v in saved.items():
            setattr(B, n, v)


def t_handle_post_still_runs_the_coding_mode_by_default():
    name_list = ("start", "stop")
    saved = {n: getattr(B, n) for n in name_list}
    called = {}

    def start(**kw):
        called["start"] = kw
        return 200, {"ok": True}

    def stop(**kw):
        called["stop"] = kw
        return 200, {"ok": True}

    B.start = start
    B.stop = stop
    try:
        code, _ = B.handle_post({"action": "start"})
        check("a start POST with no mode still starts coding",
              code == 200 and called["start"].get("mode") == "coding", called)
        code, _ = B.handle_post({"action": "stop", "mode": "deep_think"})
        check("a stop POST can name a mode",
              code == 200 and called["stop"].get("mode") == "deep_think")
        code, body = B.handle_post({"action": "start", "mode": "creative"})
        check("a start POST can name creative",
              code == 200 and called["start"].get("mode") == "creative")
        code, body = B.handle_post({"action": "vibes"})
        check("an unknown action is still a 400",
              code == 400 and "send" in body["error"])
    finally:
        for n, v in saved.items():
            setattr(B, n, v)


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
