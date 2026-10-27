"""POST /api/work/apply: one ask card, on-demand lane, rollback, refusals."""
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_presets as P  # noqa: E402

FAILED, PASSED = [], []
TMP = tempfile.mkdtemp(prefix="presets-apply-")
os.environ["OPENJARVIS_CONFIG_DIR"] = TMP


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name + (f"\n        {detail}" if detail and not cond else ""))


class Deps:
    def __init__(self, start_ok=True, switch_ok=True, set_ok=True):
        self.calls = []
        self.start_ok, self.switch_ok, self.set_ok = start_ok, switch_ok, set_ok
        self.lane = "http://127.0.0.1:11436"
        self.choice = None

    def start(self, key):
        self.calls.append(("start", key))
        return (200, {"ok": True}) if self.start_ok else (503, {"ok": False, "reason": "task missing"})

    def switch(self, ref):
        self.calls.append(("switch", ref))
        return ({"ok": True, "ref": ref} if self.switch_ok
                else {"ok": False, "reason": "no such model"})

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
        self.choice = preset
        return True


def apply(body, d):
    return P.apply_from_body(body) if d is None else P.apply_preset(
        body.get("preset"), start_lane=d.start, switch_model=d.switch,
        active_url=d.get_url, set_active_url=d.set_url,
        read_choice=d.read_choice, write_choice=d.write_choice)


def t_default_unchanged_without_a_call():
    d = Deps()
    check("no preset applied: no files, no calls", d.calls == [] and not (Path(TMP) / "presets-choice.json").exists())


def t_general_success_one_card_and_order():
    d = Deps()
    code, out = apply({"preset": "general"}, d)
    check("general applies through one start, one switch, one lane write, one choice",
          code == 200 and out["changed"] is True
          and [c[0] for c in d.calls] == ["start", "switch", "set_url", "choice"], d.calls)
    check("the one switch is the preset's model on the main lane",
          d.calls[1] == ("switch", "qwen3.5:9b")
          and d.calls[2] == ("set_url", "http://127.0.0.1:11436"), d.calls)
    check("the chosen preset is persisted", d.choice == "general")


def t_fast_starts_the_coding_lane_on_demand():
    d = Deps()
    code, out = apply({"preset": "fast"}, d)
    check("Fast asks for exactly the coding lane, never both",
          code == 200 and d.calls[0] == ("start", "coding")
          and sum(1 for c in d.calls if c[0] == "start") == 1, d.calls)
    check("... and the chat lane is pointed at :11435",
          d.calls[2] == ("set_url", "http://127.0.0.1:11435"), d.calls)


def t_refusals_change_nothing():
    d = Deps()
    code, out = apply({"preset": "nope"}, d)
    check("an unknown preset is refused, no calls", code == 400 and d.calls == [])
    pending = replace(P.by_id("general"), pending=True)
    old = dict(P._BY_ID); P._BY_ID["fake_pending"] = pending
    try:
        code, out = apply({"preset": "fake_pending"}, d)
    finally:
        P._BY_ID.clear(); P._BY_ID.update(old)
    check("a pending preset refuses in plain words, no calls",
          code == 409 and "waiting for the model" in out["error"] and d.calls == [], out)
    code, out = apply({"preset": "coding"}, d)
    check("heavy-mode Coding refuses and says the both-card lane is arriving",
          code == 409 and "heavy mode needs the both-card lane, arriving later" in out["error"]
          and d.calls == [], out)


def t_lane_start_failure_stops_before_the_switch():
    d = Deps(start_ok=False)
    code, out = apply({"preset": "fast"}, d)
    check("a lane that will not start refuses before the switch card exists",
          code == 503 and not any(c[0] == "switch" for c in d.calls)
          and d.lane == "http://127.0.0.1:11436" and d.choice is None, d.calls)


def t_switch_failure_rolls_back_lane_and_choice():
    d = Deps(switch_ok=False)
    d.choice = "general"
    d.lane = "http://127.0.0.1:11436"
    code, out = apply({"preset": "fast"}, d)
    check("a failed switch rolls the chat lane back to where it was",
          code == 409 and d.lane == "http://127.0.0.1:11436", (code, out, d.calls))
    check("... and the chosen preset is unchanged", d.choice == "general")
    check("... and one plain reason is returned", "roiled back" in out["error"] or "rolled back" in out["error"], out)


def t_install_wires_only_the_apply_route():
    seen = []

    class H:
        def do_POST(self):
            return "original"

        def _send(self, code, body):
            seen.append((code, body))
            return code

    P.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: json.dumps({"preset": "coding"}).encode())
    h = H(); h.path = "/api/work/apply"
    got = h.do_POST()
    check("the install wraps POST /api/work/apply", got == 409 and seen, seen)
    h2 = H(); h2.path = "/api/other"
    check("... and leaves every other POST alone", h2.do_POST() == "original")



def t_get_work_serves_the_new_contract():
    seen = []

    class H:
        def do_GET(self):
            return "old-do_get"

        def _send(self, code, body):
            seen.append((code, body))
            return code

    P.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: b"{}")
    h = H(); h.path = "/api/work"
    code = h.do_GET()
    check("GET /api/work is the new contract, not the old work setups",
          code == 200 and "presets" in seen[-1][1]
          and "setup_ids" not in seen[-1][1], seen[-1][1] if seen else None)
    body = seen[-1][1]
    check("... it carries nine presets with the apply contract",
          [p["id"] for p in body["presets"]] == list(P.PRESET_IDS)
          and body["presets"][0]["apply"]["apply_route"] == "/api/work/apply")
    check("... and the hardware/questionnaire/recommendations blocks",
          body["hardware"]["detected"]["source"] == "jarvis_hardware.detect()"
          and body["hardware"]["questionnaire"]["focus_choices"] == list(P.PRESET_IDS)
          and sorted(body["recommendations"]["by_gpu_count"]) == ["1", "2", "3"]
          and "questionnaire" not in body, body.keys())
    check("... and a top-level lane/lane_status beside active_lane",
          "lane" in body and "lane_status" in body and "active_lane" in body
          and body["lane"]["key"] == "main"
          and "RTX 2060" in body["lane"]["label"])
    check("... the hardware shape is the fixture's nested shape",
          sorted(body["hardware"]) == ["detected", "questionnaire"]
          and sorted(body["hardware"]["detected"]) == ["cards", "count", "source"],
          body["hardware"])
    check("... and chosen/active-lane fields, never a token",
          "chosen" in body and "chosen_preset" in body and "active_lane" in body
          and "X-Jarvis-Token" not in json.dumps(body))

    seen.clear()
    h = H(); h.path = "/api/presets"
    check("GET /api/presets is the same contract (alias)", h.do_GET() == 200)
    seen.clear()
    h = H(); h.path = "/api/other"
    check("... and every other GET is left alone", h.do_GET() == "old-do_get")

    seen.clear()
    P.install(H, origin_ok=lambda h: False, token_ok=lambda h: True,
              read_body=lambda h: b"{}")
    h = H(); h.path = "/api/work"
    check("GET /api/work enforces the origin check", h.do_GET() == 403, seen)
    seen.clear()
    P.install(H, origin_ok=lambda h: True, token_ok=lambda h: False,
              read_body=lambda h: b"{}")
    h = H(); h.path = "/api/work"
    check("... and the token check", h.do_GET() == 401, seen)


def t_a_later_failure_rolls_the_model_back_too():
    d = Deps(set_ok=False)      # switch succeeds, pointing the lane fails
    rolled = []
    code, out = P.apply_preset("fast", start_lane=d.start, switch_model=d.switch,
                               active_url=d.get_url, set_active_url=d.set_url,
                               read_choice=d.read_choice, write_choice=d.write_choice,
                               rollback_model=lambda: (rolled.append(True), {"ok": True})[1])
    check("a failure AFTER the switch rolls the switched model back (auto tier)",
          code == 409 and rolled == [True] and "model were rolled back" in out["error"],
          (code, rolled, out))
    check("... and the lane pointer is back where it was", d.lane == "http://127.0.0.1:11436")

def main() -> int:
    for fn in (t_default_unchanged_without_a_call, t_general_success_one_card_and_order,
               t_fast_starts_the_coding_lane_on_demand, t_refusals_change_nothing,
               t_lane_start_failure_stops_before_the_switch,
               t_switch_failure_rolls_back_lane_and_choice, t_install_wires_only_the_apply_route,
               t_a_later_failure_rolls_the_model_back_too,
               t_get_work_serves_the_new_contract):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED)); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
