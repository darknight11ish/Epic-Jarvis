"""jarvis_power_switch.py and power-mode.patch - Active / Quiet / Standby.

    python3 test_power_switch.py

No real gate, no Ollama. Uses the rebuilt jarvis_power.py from this
repository (backend/rebuilt/) unless the backend has its own. Pinned:

1. The mode changes ONLY on an allowed gate verdict, under the owner's own
   action name `power_manage`; denied, timed out or a broken gate change
   nothing and say so.
2. Standby unloads the model (what the desktop FAQ promises) and says which;
   it is refused while a multi-step task is running.
3. Nothing but the three modes is accepted.
4. The patch applies after note-capture.patch, and reverts.
"""
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, require_shipped  # noqa: E402

require_shipped("jarvis_power_switch.py")
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = Path(tempfile.mkdtemp(prefix="jarvis-power-"))
fw.LOG_DIR = fw.CONFIG_DIR
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = fw
if missing("jarvis_power.py"):
    sys.path.append(str(HERE / "rebuilt"))
import jarvis_power as P  # noqa: E402
import jarvis_power_switch as S  # noqa: E402
import jarvis_task_control as TC  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, outcome):
        self.allowed, self.outcome, self.reason = allowed, outcome, outcome


class FakeModels:
    def __init__(self):
        self.unloaded = []

    def resident_models(self):
        return ["jarvis-primary:8b"]

    def unload(self, name):
        self.unloaded.append(name)


def reset():
    P.set_mode("active", "test")


def t_an_allowed_change_goes_through_the_gate():
    reset()
    asked = []

    def gate(action, detail, prompt):
        asked.append((action, detail["text"]))
        return Verdict(True, "auto")
    code, out = S.set_mode("quiet", by="phone", gate_check=gate)
    check("quiet: 200 and changed", code == 200 and out["changed"] and out["mode"] == "quiet",
          repr(out))
    check("asked under the owner's own action name", asked and asked[0][0] == "power_manage")
    check("the card says what the mode means and what refusing costs",
          "starts nothing on its own" in asked[0][1] and "If you say no" in asked[0][1])
    check("the power module really changed", P.current() == "quiet")


def t_refusals_change_nothing():
    for outcome in ("denied", "timed_out", "refused"):
        reset()
        code, out = S.set_mode("standby", gate_check=lambda *a, o=outcome: Verdict(False, o),
                               models=FakeModels())
        check(f"{outcome}: nothing changed, and it says so",
              P.current() == "active" and out["changed"] is False and "stays active" in out["message"],
              repr(out))
    reset()
    gm = types.ModuleType("jarvis_gate")

    def boom(*a, **k):
        raise RuntimeError("gate exploded")
    gm.check = boom
    sys.modules["jarvis_gate"] = gm
    try:
        S.set_mode("standby", models=FakeModels())
    finally:
        sys.modules.pop("jarvis_gate", None)
    check("a gate that raises changes nothing (fails closed)", P.current() == "active")


def t_standby_frees_the_card_and_says_so():
    reset()
    m = FakeModels()
    code, out = S.set_mode("standby", gate_check=lambda *a: Verdict(True, "auto"), models=m)
    check("standby unloads the resident model", m.unloaded == ["jarvis-primary:8b"], repr(m.unloaded))
    check("and reports it", out.get("unloaded") == ["jarvis-primary:8b"], repr(out))
    check("and warns the next answer is slow", "5-15 seconds" in out["message"])
    code, out = S.set_mode("active", gate_check=lambda *a: Verdict(True, "auto"), models=m)
    check("waking works the same way", P.current() == "active" and out["changed"])


def t_standby_refused_while_a_task_runs():
    reset()
    TC.begin("appr_busy", "control_computer")
    try:
        m = FakeModels()
        code, out = S.set_mode("standby", gate_check=lambda *a: Verdict(True, "auto"), models=m)
    finally:
        TC.end("appr_busy")
    check("409 while a task runs, and nothing unloaded", code == 409 and m.unloaded == [], repr(out))


def t_only_the_three_modes():
    reset()
    for bad in ("sleeping", "", None, 3):
        code, out = S.set_mode(bad, gate_check=lambda *a: Verdict(True, "auto"))
        check(f"{bad!r} is refused with a 400", code == 400)
    check("a non-object body is a 400", S.handle_post(["quiet"])[0] == 400)
    code, out = S.set_mode("active", gate_check=lambda *a: Verdict(True, "auto"))
    check("asking for the mode it is already in changes nothing", out["changed"] is False)


def t_a_waiting_card_answers_202():
    import threading
    reset()
    release = threading.Event()

    def slow(*a):
        release.wait(3)
        return Verdict(True, "approved")
    code, out = S.set_mode("quiet", gate_check=slow, wait_s=0.05)
    check("while the card waits: 202, and not changed yet",
          code == 202 and out["changed"] is False and P.current() == "active", repr(out))
    release.set()


def t_the_patch():
    import test_task_control as TT
    ok, out = TT.rehearse(["task-control.patch", "note-capture.patch", "power-mode.patch"],
                          TT.stack_skeleton())
    if ok is None:
        return check("SKIP - " + out, True)
    check("power-mode.patch applies after note-capture.patch, and reverts", ok is True, out)
    if ok:
        i = out.index('if route == "/api/power":')
        w = out[i:i + 1200]
        check("POST /api/power checks origin and token", "_origin_ok(self)" in w and "_token_ok(self)" in w)
        check("and hands it to jarvis_power_switch", "jarvis_power_switch.handle_post" in w)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("the script applies it right after note-capture.patch",
          "power-mode.patch" in names
          and names.index("power-mode.patch") == names.index("note-capture.patch") + 1)
    check("the script copies jarvis_power_switch.py in",
          "'jarvis_power_switch.py'" in ps1[ps1.index("$SHIPPED = @("):])


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has POST /api/power (power-mode.patch applied)",
          'route == "/api/power"' in s)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
