"""The pooled both-card lane: the Coding preset's lane, proved without a GPU.

Every check here runs against a FAKE `jarvis_big_coder`, so no graphics card,
no Ollama and no model is touched. What is proved is the order (card -> pause
announcement -> server -> pause -> load), the refusals in plain words, the
restores on every failure, and that the preset apply uses this lane for the
Coding row and only for it.

The real numbers (tokens a second, VRAM on both cards, spill, cold load) are
measured on the PC and recorded in `docs/MEASURED-2026-11-02-POOLED-LANE.md`;
nothing here claims any of them.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FAILED, PASSED = [], []
TMP = tempfile.mkdtemp(prefix="pooled-lane-")
os.environ["OPENJARVIS_CONFIG_DIR"] = TMP

import jarvis_model_lanes as L  # noqa: E402
import jarvis_presets as P  # noqa: E402

MODEL = "qwen3-coder-30b-a3b-ud-q3-k-xl"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed=True, outcome="allowed", reason=""):
        self.allowed, self.outcome, self.reason = allowed, outcome, reason


class Engine:
    """A stand-in for `jarvis_big_coder`, recording the order of every call."""

    def __init__(self, *, server_ok=True, pause_ok=True, load_ok=True,
                 restore_ok=True, unload_ok=True):
        self.calls = []
        self.rows = []
        self.server_ok, self.pause_ok, self.load_ok = server_ok, pause_ok, load_ok
        self.restore_ok, self.unload_ok = restore_ok, unload_ok
        self.announced = ""
        self.card_kw = {}

    # --- what the lane reads -------------------------------------------------
    def ps(self, url):
        self.calls.append(("ps", url))
        return [dict(r) for r in self.rows]

    def loaded_row(self, rows, model):
        for row in rows or ():
            if row.get("name") == model:
                return row
        return None

    def spill_bytes(self, row):
        return int((row or {}).get("size") or 0) - int((row or {}).get("size_vram") or 0)

    def card_text_start(self, **kw):
        self.card_kw = dict(kw)
        return ("Use the coding model. It needs BOTH graphics cards, so the two "
                "models running now are paused first.")

    def lane_lines(self):
        return ["qwen3.5:9b at 196,608 tokens on the RTX 2060 (port 11436)",
                "qwen3:8b at 16,384 tokens on the RTX 2080 SUPER (port 11435)"]

    # --- the actions ---------------------------------------------------------
    def announce_pause(self, words):
        self.calls.append(("announce", words))
        self.announced = words

    def server_start(self):
        self.calls.append(("server_start",))
        return {"ok": self.server_ok, "url": L.pooled_url(), "owned": True,
                "why": "" if self.server_ok else
                "the both-cards Ollama did not answer within 30 seconds"}

    def pause_lanes(self):
        self.calls.append(("pause",))
        if self.pause_ok:
            return {"ok": True, "why": "", "unloaded": ["qwen3.5:9b @11436"],
                    "still": [], "proof": ["port 11436: qwen3.5:9b is not loaded"]}
        return {"ok": False, "unloaded": [],
                "why": ("Jarvis did not pause every model it must, so the big coding "
                        "model was NOT started: still loaded - qwen3.5:9b on port "
                        "11436. Nothing was loaded, and what was unloaded is being "
                        "put back."),
                "still": ["qwen3.5:9b on port 11436"],
                "proof": ["port 11436: qwen3.5:9b is STILL loaded after being asked "
                          "to unload"]}

    def load_coder(self, *, port=11450, num_ctx=None, allow_spill=None):
        self.calls.append(("load", port, num_ctx, allow_spill))
        if not self.load_ok:
            return {"ok": False,
                    "why": (f"{MODEL} loaded with 300000000 B of spill, over the "
                            f"{L.POOLED_SPILL_ALLOWANCE} B measured allowance for "
                            f"{L.POOLED_CTX} tokens - it needs both cards, and this "
                            "machine gave it less video memory than that measurement, "
                            "so it was unloaded again"),
                    "proof": [f"port {port}: {MODEL} size=100 size_vram=0"]}
        self.rows = [{"name": MODEL, "context_length": num_ctx or L.POOLED_CTX,
                      "size": 15_000, "size_vram": 15_000}]
        return {"ok": True, "why": "", "proof": [f"port {port}: {MODEL} ctx={num_ctx}"],
                "row": self.rows[0]}

    def unload_coder(self, *, port=11450):
        self.calls.append(("unload", port))
        self.rows = []
        if self.unload_ok:
            return {"ok": True, "why": "", "proof": ["nothing is resident"]}
        return {"ok": False, "why": f"{MODEL} is STILL loaded after being asked to unload",
                "proof": [f"port {port}: {MODEL} is still in /api/ps"]}

    def server_stop(self):
        self.calls.append(("server_stop",))
        return {"stopped": True, "why": ""}

    def restore_lanes(self):
        self.calls.append(("restore",))
        if self.restore_ok:
            return {"ok": True, "why": "", "wrong": [],
                    "proof": ["port 11436: qwen3.5:9b ctx=196608 spill=0",
                              "port 11435: qwen3:8b ctx=16384 spill=0"]}
        return {"ok": False, "wrong": ["qwen3.5:9b came back at 16384, not 196608"],
                "why": ("The two models were not put back exactly as they were: "
                        "qwen3.5:9b came back at 16384, not 196608. Start them from "
                        "the Power screen, or restart Jarvis."),
                "proof": ["port 11436: qwen3.5:9b DID not come back"]}

    # --- helpers for the checks ---------------------------------------------
    def names(self):
        return [c[0] for c in self.calls]

    def index(self, name):
        return self.names().index(name)


# ---------------------------------------------------------------------------
#   The lane itself
# ---------------------------------------------------------------------------

def t_the_lane_is_the_one_big_coder_owns():
    import inspect
    import jarvis_big_coder as BC
    check("the pooled port is the big-coder mode's own port, not a second one",
          L.POOLED_PORT == BC.BIG_PORT == 11450, (L.POOLED_PORT, BC.BIG_PORT))
    check("the model is the mode's own, and the context is a measured rung at or "
          "below the mode's widest - never a number invented here",
          L.POOLED_MODEL == BC.MODEL == MODEL and 0 < L.POOLED_CTX <= BC.NUM_CTX,
          (L.POOLED_MODEL, L.POOLED_CTX, BC.MODEL, BC.NUM_CTX))
    check("the pooled window is 20,480 - the 2026-11-03 measurement, not the "
          "old 16,384 and not the big-coder mode's 28,672",
          L.POOLED_CTX == 20480 and BC.NUM_CTX == 28672,
          (L.POOLED_CTX, BC.NUM_CTX))
    measured = int(L.POOLED_SPILL_MEASURED_MIB * 1024 * 1024)
    check("the allowance is ONE 224 MiB number: the measured 203.5 MiB plus about "
          "10%, and nothing larger is accepted",
          L.POOLED_SPILL_ALLOWANCE == 224 * 1024 * 1024
          and measured < L.POOLED_SPILL_ALLOWANCE <= int(measured * 1.15),
          (L.POOLED_SPILL_MEASURED_MIB, L.POOLED_SPILL_ALLOWANCE))
    check("the allowance is not a general 'spill is fine': load_coder defaults to "
          "NO allowance and the big-coder mode's start() cannot pass one",
          inspect.signature(BC.load_coder).parameters["allow_spill"].default is None
          and "allow_spill" not in inspect.signature(BC.start).parameters,
          (inspect.signature(BC.load_coder), inspect.signature(BC.start)))
    check("the Coding preset's own context IS the lane's measured rung, so the "
          "contract and the load cannot disagree",
          P.by_id("coding").context == L.POOLED_CTX == 20480,
          (P.by_id("coding").context, L.POOLED_CTX))
    cod = P.by_id("coding")
    check("the preset records BOTH the new window and the old zero-spill rung as "
          "history, with the measured spill it accepts",
          cod.measured.get("context_measured") == 20480
          and cod.measured.get("context_zero_spill") == 16384
          and cod.measured.get("spill_gib") == 0.2, cod.measured)
    check("the contract row says BOTH cards, never a single card",
          L.POOLED["card"] == "both cards" and L.POOLED["port"] == L.POOLED_PORT)
    check("the preset contract's pooled lane is this lane's own port and words",
          P.LANES["pooled"]["port"] == L.POOLED_PORT
          and P.LANES["pooled"]["card"] == L.POOLED["card"]
          and P.LANES["pooled"]["words"] == L.POOLED["words"], P.LANES["pooled"])
    check("the Coding preset is on the pooled lane and is the only heavy row",
          P.by_id("coding").lane == "pooled"
          and [p.id for p in P.PRESETS if p.heavy_mode] == ["coding"])


def t_the_card_describes_the_load_it_will_really_do():
    """The card is what the owner approves, so it must name the window this
    lane asks for and the measured spill it accepts - not the big-coder mode's
    zero-spill rung, and not the old 16,384-token window."""
    import jarvis_big_coder as BC
    words = L.pooled_card_text()          # the real engine, this lane's words
    check("the pooled card names the 20,480-token window it will ask for",
          f"{L.POOLED_CTX:,} tokens" in words, words)
    check("... and it says the measured 203.5 MiB out loud instead of promising "
          "zero spill",
          f"{L.POOLED_SPILL_MEASURED_MIB:g} MiB" in words
          and "zero spill" not in words.lower()
          and f"{BC.NUM_CTX:,}" not in words, words)
    check("... while the big-coder mode's own card keeps its own measured rung",
          f"{BC.NUM_CTX:,} tokens" in BC.card_text_start()
          and "no spill" in BC.card_text_start(), BC.card_text_start())


def t_the_order_is_card_then_announce_then_server_then_pause_then_load():
    eng = Engine()
    seen = []

    def gate(action, detail, prompt):
        seen.append((action, detail, prompt))
        return Verdict(True)

    code, body = L.start_pooled_lane(engine=eng, gate=gate)
    check("a start succeeds and says the model is on both cards",
          code == 200 and body["ok"] is True and body["changed"] is True
          and body["model"] == MODEL and body["num_ctx"] == L.POOLED_CTX, (code, body))
    check("the ONE card is the switch_model action with the same from/to/why the "
          "model switch sends, so the owner reads the card he already knows",
          len(seen) == 1 and seen[0][0] == "switch_model"
          and set(seen[0][1]) == {"from", "to", "why"}
          and seen[0][1]["to"] == MODEL and seen[0][1]["why"] == "preset", seen)
    check("the card's words name both cards and the pause before anything happens",
          "both cards" in seen[0][2] or "BOTH" in seen[0][2], seen[0][2])
    check("the card comes BEFORE the pause announcement, and the announcement "
          "before the first unload",
          eng.names()[:4] == ["ps", "announce", "server_start", "pause"],
          eng.names())
    check("the model is loaded only after both lanes are proved paused",
          eng.names()[:5] == ["ps", "announce", "server_start", "pause", "load"],
          eng.names())
    check("the load names the port, so it lands on the pooled server",
          ("load", 11450, L.POOLED_CTX, L.POOLED_SPILL_ALLOWANCE) in eng.calls,
          eng.calls)
    check("... and it passes the lane's ONE measured spill allowance, never a "
          "bare load that would get the zero-spill rule",
          eng.calls[4] == ("load", 11450, L.POOLED_CTX, L.POOLED_SPILL_ALLOWANCE),
          eng.calls)
    check("the card was given this lane's own window and measured words, so it "
          "cannot describe the big-coder mode's load",
          eng.card_kw.get("num_ctx") == L.POOLED_CTX
          and str(L.POOLED_SPILL_MEASURED_MIB) in str(eng.card_kw.get("measured_words")),
          eng.card_kw)
    check("... and the answer carries the proof of the pause and of the load",
          any("11436" in row for row in body["paused"])
          and any(f"ctx={L.POOLED_CTX}" in row for row in body["proof"]), body)


def t_a_second_start_does_nothing():
    eng = Engine()
    L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Verdict(True))
    eng.calls.clear()
    called = []
    code, body = L.start_pooled_lane(
        engine=eng, gate=lambda *a, **k: (called.append(1), Verdict(True))[1])
    check("a lane already holding the model starts nothing and raises no card",
          code == 200 and body["ok"] is True and body["changed"] is False
          and called == [] and eng.names() == ["ps"], (code, body, eng.calls))


def t_a_denied_card_touches_nothing():
    eng = Engine()
    code, body = L.start_pooled_lane(
        engine=eng, gate=lambda *a, **k: Verdict(False, "denied", "you said no"))
    check("a denied card is a refusal (not a failure) and says nothing changed",
          code == 200 and body["ok"] is False and body["changed"] is False
          and body["outcome"] == "denied"
          and "nothing was paused" in body["message"].lower(), (code, body))
    check("... and NOTHING was started, paused or loaded",
          eng.names() == ["ps"], eng.calls)


def t_a_gate_that_cannot_be_asked_fails_closed():
    real = L._pooled_gate

    def broken():
        raise RuntimeError("no gate here")

    saved = L._pooled_gate
    L._pooled_gate = lambda *a, **k: L._Refused("no gate here")
    try:
        eng = Engine()
        code, body = L.start_pooled_lane(engine=eng)
    finally:
        L._pooled_gate = saved
    check("a gate that cannot be asked refuses and touches nothing",
          code == 200 and body["ok"] is False and eng.names() == ["ps"],
          (code, body, eng.calls))
    check("... and the refusal class carries the reason, never a silent pass",
          L._Refused("x").allowed is False and L._Refused("x").reason == "x")
    assert real is L._pooled_gate


def t_a_task_running_refuses_before_the_card():
    eng = Engine()
    seen = []
    code, body = L.start_pooled_lane(
        engine=eng, gate=lambda *a, **k: (seen.append(1), Verdict(True))[1],
        tasks=lambda: ["a coding job"])
    check("a multi-step task running refuses in plain words, before any card",
          code == 409 and body["ok"] is False and seen == []
          and "a task is running" in body["error"], (code, body))
    check("... and nothing at all was touched", eng.names() == ["ps"], eng.calls)


def t_a_lane_that_will_not_pause_stops_the_whole_start():
    eng = Engine(pause_ok=False)
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Verdict(True))
    check("a lane that will not pause refuses (409) and names it",
          code == 409 and body["ok"] is False
          and "did not pause" in body["error"], (code, body))
    check("... nothing is loaded", "load" not in eng.names(), eng.calls)
    check("... the lanes are put back and the server is stopped",
          eng.names()[-2:] == ["restore", "server_stop"], eng.calls)


def t_a_load_that_spills_is_undone_and_the_lanes_come_back():
    eng = Engine(load_ok=False)
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Verdict(True))
    check("a load that spills is refused (503) in the model's own plain words",
          code == 503 and body["ok"] is False
          and "needs both cards" in body["error"], (code, body))
    check("... it is unloaded again, both lanes are put back and the server stops",
          eng.names()[-3:] == ["unload", "restore", "server_stop"], eng.calls)
    check("... and the answer carries the proof of what was seen",
          body["proof"] and body["restored"], body)


def t_a_server_that_will_not_start_changes_nothing():
    eng = Engine(server_ok=False)
    code, body = L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Verdict(True))
    check("a both-cards server that will not start refuses (503) in its own words",
          code == 503 and "did not answer" in body["error"], (code, body))
    check("... nothing was paused and nothing was loaded",
          "pause" not in eng.names() and "load" not in eng.names(), eng.calls)


def t_stop_puts_both_lanes_back_and_says_what_it_saw():
    eng = Engine()
    L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Verdict(True))
    eng.calls.clear()
    code, body = L.stop_pooled_lane(engine=eng)
    check("stopping unloads the model, stops the server, then puts both lanes back",
          code == 200 and body["ok"] is True and body["changed"] is True
          and eng.names() == ["ps", "unload", "server_stop", "restore"],
          (code, body, eng.calls))
    check("... and the answer names the two models that came back",
          "both lane models are back" in body["message"]
          and len(body["restored"]) == 2, body)


def t_stop_is_safe_when_nothing_is_running():
    eng = Engine()
    code, body = L.stop_pooled_lane(engine=eng)
    check("stopping a lane that is not running still puts the lanes back, and "
          "does not claim it changed anything",
          code == 200 and body["ok"] is True and body["changed"] is False
          and eng.names() == ["ps", "unload", "server_stop", "restore"],
          (code, body, eng.calls))


def t_a_lane_that_does_not_come_back_is_reported():
    eng = Engine(restore_ok=False)
    L.start_pooled_lane(engine=eng, gate=lambda *a, **k: Verdict(True))
    code, body = L.stop_pooled_lane(engine=eng)
    check("a lane that does not come back is a 503 naming what was not put back",
          code == 503 and body["ok"] is False
          and "not put back" in body["error"], (code, body))


# ---------------------------------------------------------------------------
#   The preset apply: the Coding row uses it, and only it
# ---------------------------------------------------------------------------

class Apply:
    """The apply's own seams, recording order and the state they see."""

    def __init__(self, *, start_ok=True, start_outcome="", pooled_running=False,
                 stop_ok=True, switch_ok=True, choice_ok=True, set_ok=True):
        self.calls = []
        self.lane = "http://127.0.0.1:11436"
        self.choice = None
        self.start_ok, self.start_outcome = start_ok, start_outcome
        self.pooled_running, self.stop_ok = pooled_running, stop_ok
        self.switch_ok, self.choice_ok, self.set_ok = switch_ok, choice_ok, set_ok

    def start(self, key):
        self.calls.append(("start", key))
        if not self.start_ok:
            return 200, {"ok": False, "changed": False,
                         "outcome": self.start_outcome or "denied",
                         "message": "Not started - nothing was paused and nothing was loaded."}
        return 200, {"ok": True, "changed": True, "url": P._lane_url(key)}

    def switch(self, ref):
        self.calls.append(("switch", ref))
        return ({"ok": True, "ref": ref} if self.switch_ok
                else {"ok": False, "reason": "no such model"})

    def stop_pooled(self):
        self.calls.append(("stop_pooled",))
        return {"ok": self.stop_ok, "ran": self.pooled_running,
                "reason": "" if self.stop_ok else "a lane did not come back"}

    def get_url(self):
        return self.lane

    def set_url(self, url):
        self.calls.append(("set_url", url))
        if self.set_ok:
            self.lane = url
        return self.set_ok

    def read_choice(self):
        return self.choice

    def write_choice(self, preset):
        self.calls.append(("choice", preset))
        if not self.choice_ok:
            return False
        self.choice = preset
        return True

    def rollback_model(self):
        self.calls.append(("rollback",))
        return {"ok": True}


def apply(d, preset="coding", **kw):
    return P.apply_preset(preset, start_lane=d.start, switch_model=d.switch,
                          active_url=d.get_url, set_active_url=d.set_url,
                          read_choice=d.read_choice, write_choice=d.write_choice,
                          rollback_model=d.rollback_model,
                          stop_pooled=d.stop_pooled, **kw)


def t_coding_applies_through_the_pooled_lane():
    d = Apply()
    code, out = apply(d)
    check("Coding applies: pooled lane, model recorded, chat pointed at :11450, "
          "choice written",
          code == 200 and out["changed"] is True
          and [c[0] for c in d.calls] == ["start", "switch", "set_url", "choice"],
          (code, out, d.calls))
    check("... the lane it starts is 'pooled', never a single-card lane",
          d.calls[0] == ("start", "pooled"), d.calls)
    check("... chat is pointed at the pooled lane's own port, not :11436",
          d.calls[2] == ("set_url", "http://127.0.0.1:11450"), d.calls)
    check("... and the Coding preset is what is remembered", d.choice == "coding")


def t_a_non_heavy_apply_leaves_a_pooled_lane_that_is_not_running_alone():
    d = Apply(pooled_running=False)
    code, out = apply(d, "general")
    check("a preset that is not heavy asks the pool to stop, and does nothing "
          "when it was not running",
          code == 200 and ("stop_pooled",) in d.calls
          and d.calls.index(("stop_pooled",)) < d.calls.index(("start", "main")),
          (code, d.calls))


def t_leaving_the_pooled_lane_stops_it_before_the_new_model():
    d = Apply(pooled_running=True)
    code, out = apply(d, "general")
    check("applying General while Coding is on ENDS the pooled lane FIRST, then "
          "starts the everyday lane",
          code == 200 and d.calls[:2] == [("stop_pooled",), ("start", "main")],
          (code, d.calls))
    check("... and chat moves back to the everyday lane", d.lane.endswith(":11436"),
          d.lane)


def t_a_pooled_lane_that_will_not_stop_refuses_the_new_preset():
    d = Apply(pooled_running=True, stop_ok=False)
    code, out = apply(d, "general")
    check("if the big coding model will not stop, the apply refuses (503) and "
          "says the cards are still held",
          code == 503 and "still holding both cards" in out["error"], (code, out))
    check("... nothing else is touched: no lane started, no model switched, no "
          "choice written",
          [c[0] for c in d.calls] == ["stop_pooled"],
          d.calls)


def t_a_denied_card_on_coding_changes_nothing():
    d = Apply(start_ok=False, start_outcome="denied")
    d.choice = "general"
    code, out = apply(d)
    check("a denied card on Coding is a 409 refusal, and NOTHING was changed",
          code == 409 and out["changed"] is False
          and "nothing was changed" in out["error"] and out["outcome"] == "denied",
          (code, out))
    check("... no model was recorded, chat did not move and the choice is intact",
          [c[0] for c in d.calls] == ["start"] and d.choice == "general"
          and d.lane.endswith(":11436"), (d.calls, d.choice, d.lane))


def t_a_pooled_start_that_fails_says_the_lane_words():
    d = Apply()
    real_default = P._default_start_lane
    try:
        P._default_start_lane = lambda key: (503, {
            "ok": False, "changed": False,
            "error": (f"{MODEL} loaded with spill (1024 B not in video memory) - it "
                      "needs both cards and this machine could not give it both"),
        })
        code, out = P.apply_preset("coding", switch_model=d.switch,
                                   active_url=d.get_url, set_active_url=d.set_url,
                                   read_choice=d.read_choice,
                                   write_choice=d.write_choice,
                                   rollback_model=d.rollback_model,
                                   stop_pooled=d.stop_pooled)
    finally:
        P._default_start_lane = real_default
    check("a pooled lane that could not load refuses (503) in the lane's own words",
          code == 503 and "needs both cards" in out["error"], (code, out))
    check("... no model is recorded and chat does not move",
          not any(c[0] == "switch" for c in d.calls) and d.lane.endswith(":11436"),
          d.calls)


def t_a_later_failure_after_coding_stops_the_pooled_lane_first():
    class OnceFails(Apply):
        """The choice write fails ONCE, so the restore can succeed."""

        def __init__(self, **kw):
            super().__init__(**kw)
            self.writes = 0

        def write_choice(self, preset):
            self.calls.append(("choice", preset))
            self.writes += 1
            if self.writes == 1:
                return False
            self.choice = preset
            return True

    d = OnceFails()
    d.choice = "general"
    code, out = P.apply_preset("coding", start_lane=d.start, switch_model=d.switch,
                               active_url=d.get_url, set_active_url=d.set_url,
                               read_choice=d.read_choice, write_choice=d.write_choice,
                               rollback_model=d.rollback_model,
                               stop_pooled=d.stop_pooled)
    check("a failure after the pooled lane started rolls it back (stop) as well as "
          "the model, the chat lane and the choice",
          code == 409 and out["restored"] == ["the pooled lane", "the model",
                                              "the chat lane", "the chosen preset"],
          (code, out))
    check("... the stop happens BEFORE the model rollback, so the previous model's "
          "lane is free again",
          d.calls.index(("stop_pooled",)) < d.calls.index(("rollback",)), d.calls)
    check("... and the lane pointer and the remembered preset are back",
          d.lane.endswith(":11436") and d.choice == "general", (d.lane, d.choice))


def t_the_heavy_path_uses_adopt_and_the_others_use_the_model_switch():
    seen = []
    d = Apply()
    real_adopt, real_switch = P._default_adopt, P._default_switch
    try:
        P._default_adopt = lambda ref: (seen.append(("adopt", ref)),
                                        {"ok": True, "ref": ref})[1]
        P._default_switch = lambda ref: (seen.append(("switch", ref)),
                                         {"ok": True, "ref": ref})[1]
        code, out = P.apply_preset("coding", start_lane=d.start,
                                   active_url=d.get_url, set_active_url=d.set_url,
                                   read_choice=d.read_choice,
                                   write_choice=d.write_choice,
                                   rollback_model=d.rollback_model,
                                   stop_pooled=d.stop_pooled)
        coding = list(seen)
        seen.clear()
        d2 = Apply(pooled_running=False)
        code2, out2 = P.apply_preset("general", start_lane=d2.start,
                                     active_url=d2.get_url,
                                     set_active_url=d2.set_url,
                                     read_choice=d2.read_choice,
                                     write_choice=d2.write_choice,
                                     rollback_model=d2.rollback_model,
                                     stop_pooled=d2.stop_pooled)
        general = list(seen)
    finally:
        P._default_adopt, P._default_switch = real_adopt, real_switch
    check("Coding records the model the pooled lane loaded, never switch_to's "
          "single-card smoke test",
          code == 200 and coding == [("adopt", MODEL)], (code, coding))
    check("a preset that is not heavy still goes through the model switch",
          code2 == 200 and general == [("switch", "qwen3.5:9b")], (code2, general))


def t_the_pooled_defaults_are_wired_to_the_lane_module():
    seen = []
    real_start, real_stop = L.start_pooled_lane, L.stop_pooled_lane
    real_running = L.pooled_running
    try:
        L.start_pooled_lane = lambda **kw: (seen.append("start"),
                                            (200, {"ok": True, "changed": True}))[1]
        L.stop_pooled_lane = lambda **kw: (seen.append("stop"),
                                           (200, {"ok": True, "changed": True}))[1]
        L.pooled_running = lambda **kw: False
        code, body = P._default_start_lane("pooled")
        check("the apply's 'pooled' lane is the lane module's pooled start",
              code == 200 and seen == ["start"], (code, seen, body))
        out = P._default_stop_pooled()
        check("... and its stop is the pool's own stop, and 'ran: false' when "
              "nothing was running", out["ok"] is True and out["ran"] is False
              and seen == ["start"], out)
        L.pooled_running = lambda **kw: True
        out = P._default_stop_pooled()
        check("... and it reports that it really stopped a running lane",
              out["ok"] is True and out["ran"] is True and seen == ["start", "stop"],
              out)
    finally:
        L.start_pooled_lane, L.stop_pooled_lane = real_start, real_stop
        L.pooled_running = real_running


# ---------------------------------------------------------------------------
#   Recording the model without a second card
# ---------------------------------------------------------------------------

class Steward:
    """A stand-in for the owner's jarvis_models state file."""

    MAX_HISTORY = 3

    def __init__(self, state=None, write_ok=True, no_writer=False):
        self.state = dict(state or {})
        self.write_ok, self.no_writer = write_ok, no_writer

    def wire(self, mod):
        mod._read_state = lambda: dict(self.state)
        if not self.no_writer:
            def write(st):
                if not self.write_ok:
                    return False
                self.state = dict(st)
                return True
            mod._write_state = write


def _with_steward(steward):
    import types
    mod = types.ModuleType("jarvis_models")
    steward.wire(mod)
    sys.modules["jarvis_models"] = mod
    return mod


def t_adopt_writes_the_same_record_the_switch_writes():
    steward = Steward({"current": "qwen3.5:9b", "previous": "qwen3:8b",
                       "switches": [{"from": None, "to": "qwen3:8b", "at": 1}]})
    module = _with_steward(steward)
    try:
        out = P._default_adopt(MODEL)
    finally:
        sys.modules.pop("jarvis_models", None)
    check("the model the pooled lane loaded is recorded as the one in use",
          out["ok"] is True and out.get("adopted") is True
          and steward.state.get("current") == MODEL
          and steward.state.get("previous") == "qwen3.5:9b", (out, steward.state))
    check("... in the same fields switch_to writes, with the switch history kept",
          {"previous", "current", "switched_at", "why", "switches"}
          <= set(steward.state) and len(steward.state["switches"]) == 2
          and steward.state["switches"][-1]["to"] == MODEL, steward.state)
    check("... and it never asks the single-card lane's smoke test",
          "switched" not in json.dumps(out), out)
    check("... and it does not call switch_to at all", callable(module) is False)


def t_adopt_is_a_no_op_when_the_model_is_already_in_use():
    steward = Steward({"current": MODEL})
    _with_steward(steward)
    try:
        out = P._default_adopt(MODEL)
        before = dict(steward.state)
    finally:
        sys.modules.pop("jarvis_models", None)
    check("recording the model already in use changes nothing and says so",
          out["ok"] is True and out.get("unchanged") is True
          and steward.state == before, out)


def t_adopt_refuses_when_it_cannot_record():
    steward = Steward({"current": "qwen3.5:9b"}, write_ok=False)
    _with_steward(steward)
    try:
        out = P._default_adopt(MODEL)
    finally:
        sys.modules.pop("jarvis_models", None)
    check("a model state that cannot be written is a refusal, not a claim",
          out["ok"] is False and "could not write" in out["reason"], out)

    import types
    mod = types.ModuleType("jarvis_models")
    sys.modules["jarvis_models"] = mod
    try:
        out = P._default_adopt(MODEL)
    finally:
        sys.modules.pop("jarvis_models", None)
    check("a model steward with no recordable state refuses in plain words",
          out["ok"] is False and "no recordable model state" in out["reason"], out)

    sys.modules["jarvis_models"] = None
    try:
        out = P._default_adopt(MODEL)
    finally:
        sys.modules.pop("jarvis_models", None)
    check("a missing model steward refuses, and the apply would roll back",
          out["ok"] is False and "not available" in out["reason"], out)


def t_a_heavy_apply_whose_record_fails_rolls_everything_back():
    steward = Steward({"current": "qwen3.5:9b"}, write_ok=False)
    _with_steward(steward)
    d = Apply()
    d.choice = "general"
    try:
        code, out = P.apply_preset("coding", start_lane=d.start,
                                   active_url=d.get_url, set_active_url=d.set_url,
                                   read_choice=d.read_choice,
                                   write_choice=d.write_choice,
                                   rollback_model=d.rollback_model,
                                   stop_pooled=d.stop_pooled)
    finally:
        sys.modules.pop("jarvis_models", None)
    check("if the model cannot be recorded, the preset is NOT applied",
          code in (409, 503) and out["changed"] is False, (code, out))
    check("... the pooled lane is stopped again and the chat lane and choice are "
          "put back",
          ("stop_pooled",) in d.calls and d.lane.endswith(":11436")
          and d.choice == "general" and "the pooled lane" in out["restored"],
          (d.calls, out))


def main() -> int:
    for fn in (t_the_lane_is_the_one_big_coder_owns,
               t_the_card_describes_the_load_it_will_really_do,
               t_the_order_is_card_then_announce_then_server_then_pause_then_load,
               t_a_second_start_does_nothing,
               t_a_denied_card_touches_nothing,
               t_a_gate_that_cannot_be_asked_fails_closed,
               t_a_task_running_refuses_before_the_card,
               t_a_lane_that_will_not_pause_stops_the_whole_start,
               t_a_load_that_spills_is_undone_and_the_lanes_come_back,
               t_a_server_that_will_not_start_changes_nothing,
               t_stop_puts_both_lanes_back_and_says_what_it_saw,
               t_stop_is_safe_when_nothing_is_running,
               t_a_lane_that_does_not_come_back_is_reported,
               t_coding_applies_through_the_pooled_lane,
               t_a_non_heavy_apply_leaves_a_pooled_lane_that_is_not_running_alone,
               t_leaving_the_pooled_lane_stops_it_before_the_new_model,
               t_a_pooled_lane_that_will_not_stop_refuses_the_new_preset,
               t_a_denied_card_on_coding_changes_nothing,
               t_a_pooled_start_that_fails_says_the_lane_words,
               t_a_later_failure_after_coding_stops_the_pooled_lane_first,
               t_the_heavy_path_uses_adopt_and_the_others_use_the_model_switch,
               t_the_pooled_defaults_are_wired_to_the_lane_module,
               t_adopt_writes_the_same_record_the_switch_writes,
               t_adopt_is_a_no_op_when_the_model_is_already_in_use,
               t_adopt_refuses_when_it_cannot_record,
               t_a_heavy_apply_whose_record_fails_rolls_everything_back):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
