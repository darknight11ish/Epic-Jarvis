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
5. (2026-09-25, with the standby schedule) Standby unloads EVERY model the
   everyday Ollama holds, not only the ones jarvis_models names, and says
   plainly what is still loaded; this PC's Ollama only. Leaving standby
   loads the chat model again (the warm-up) - never a cloud model, never
   another machine's Ollama, and unloaded again if Jarvis went back on
   standby meanwhile. The answer comes when the mode has changed, not
   after every card is freed.
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


class FakeOllama:
    """The everyday Ollama: what /api/ps lists, and what was asked."""

    def __init__(self, loaded=(), stubborn=(), url="http://127.0.0.1:11434", slow=0.0):
        self.loaded = list(loaded)
        self.stubborn = set(stubborn)   # never let go
        self.url = url
        self.unloads, self.loads = [], []
        self.slow = slow

    def ps(self):
        return list(self.loaded)

    def unload(self, name):
        if self.slow:
            __import__("time").sleep(self.slow)
        self.unloads.append(name)
        if name not in self.stubborn:
            self.loaded = [n for n in self.loaded if n != name]

    def load(self, name):
        self.loads.append(name)
        if name not in self.loaded:
            self.loaded.append(name)


# No test here may reach a real Ollama: the default is an empty fake.
S.everyday_ollama = lambda: FakeOllama()


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
    for _ in range(300):                 # a change still finishing behind its answer
        if not getattr(S, "_PENDING", None):
            break
        __import__("time").sleep(0.02)
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


def t_standby_frees_the_other_cards_too():
    # With two cards, "frees its graphics cards" has to cover the second
    # card's Ollama and the big model as well as the everyday model.
    reset()
    calls = []

    def engine(name, sentence=None, boom=False):
        def sleep(why):
            calls.append((name, why))
            if boom:
                raise RuntimeError("no")
            return {"stopped": bool(sentence), "sentence": sentence or ""}
        return types.SimpleNamespace(__name__=name, sleep=sleep)

    others = [engine("jarvis_second_card", "The second graphics card was freed too."),
              engine("jarvis_big_model"),
              engine("jarvis_other", boom=True)]
    code, out = S.set_mode("standby", gate_check=lambda *a: Verdict(True, "auto"),
                           models=FakeModels(), others=others)
    check("every engine is asked to sleep, once each, because of standby",
          [c[0] for c in calls] == ["jarvis_second_card", "jarvis_big_model", "jarvis_other"]
          and all("standby" in c[1] for c in calls), calls)
    check("what was freed is said, what had nothing to free says nothing",
          out.get("also", [])[:1] == ["The second graphics card was freed too."]
          and "The second graphics card was freed too." in out["message"]
          and len(out.get("also", [])) == 2, out)
    check("an engine that fails says so, and standby still happens",
          "Could not free jarvis_other" in out["also"][1] and P.current() == "standby", out)
    reset()
    calls.clear()
    S.set_mode("quiet", gate_check=lambda *a: Verdict(True, "auto"),
               models=FakeModels(), others=others)
    check("quiet frees nothing", calls == [])


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


def t_one_power_card_at_a_time():
    # AP-8: with power_manage at tier "ask", three changes raised three cards,
    # and the one answered LAST decided the mode, not the one asked for last.
    import threading
    for _ in range(100):                      # the previous test's card ends
        if not getattr(S, "_PENDING", None):
            break
        __import__("time").sleep(0.02)
    reset()
    release, asked = threading.Event(), []

    def slow(action, detail, prompt):
        asked.append(prompt)
        release.wait(3)
        return Verdict(True, "approved")
    code, out = S.set_mode("standby", gate_check=slow, models=FakeModels(), wait_s=0.05)
    check("the first change: 202, a card waits, and it says 'your PC or phone'",
          code == 202 and "on your PC or phone" in out["message"]
          and "desktop" not in out["message"], repr(out))
    code2, out2 = S.set_mode("quiet", gate_check=slow, wait_s=0.05)
    check("a second change while it waits: 409, no second card",
          code2 == 409 and len(asked) == 1 and "already waiting" in out2["error"]
          and "standby" in out2["error"], repr(out2))
    release.set()
    for _ in range(100):
        if not S._PENDING:
            break
        __import__("time").sleep(0.02)
    check("once it is answered, a new change may raise a card", not S._PENDING)
    code3, _ = S.set_mode("active", gate_check=lambda *a: Verdict(True, "auto"))
    check("... and does", code3 == 200 and P.current() == "active")


def t_standby_rechecks_tasks_after_the_card():
    # AP-8: the running-task check ran only BEFORE the card. A task that
    # started while the card waited then had its model unloaded under it.
    import threading
    reset()
    release = threading.Event()
    m = FakeModels()
    done = {}

    def slow(action, detail, prompt):
        release.wait(3)
        return Verdict(True, "approved")
    real = S._running_tasks
    tasks = []
    S._running_tasks = lambda: list(tasks)
    try:
        box = {}
        t = threading.Thread(target=lambda: box.update(r=S.set_mode(
            "standby", gate_check=slow, models=m, wait_s=3)))
        t.start()
        __import__("time").sleep(0.1)
        tasks.append("task-1")                # a task starts while the card waits
        release.set()
        t.join(5)
        code, out = box["r"]
    finally:
        S._running_tasks = real
    check("approved after a task started: nothing unloaded, mode unchanged, 409 with why",
          m.unloaded == [] and P.current() == "active" and code == 409
          and "task started while the card waited" in out["message"], repr((code, out)))


def _auto(*a):
    return Verdict(True, "auto")


def _settled():
    for _ in range(300):
        if not S._PENDING:
            return
        __import__("time").sleep(0.02)


def t_standby_unloads_every_model_ollama_holds():
    reset()
    m = FakeModels()                                  # jarvis_models names only this one
    o = FakeOllama(["jarvis-primary:8b", "qwen2.5vl:7b", "nomic-embed-text:latest"])
    code, out = S.set_mode("standby", gate_check=_auto, models=m, ollama=o, others=[])
    check("every model /api/ps listed is asked to unload, not only jarvis_models' one",
          set(o.unloads) >= {"qwen2.5vl:7b", "nomic-embed-text:latest"} and o.loaded == [],
          repr((o.unloads, o.loaded)))
    check("... and all of them are said as unloaded, once each",
          sorted(out["unloaded"]) == ["jarvis-primary:8b", "nomic-embed-text:latest",
                                      "qwen2.5vl:7b"], repr(out))
    check("nothing still loaded: no 'still' sentence", "still_loaded" not in out
          and "Still loaded" not in out["message"], repr(out))

    reset()
    o = FakeOllama(["jarvis-primary:8b", "stuck:1b"], stubborn={"stuck:1b"})
    code, out = S.set_mode("standby", gate_check=_auto, models=FakeModels(), ollama=o,
                           others=[], wait_s=10)
    check("a model Ollama will not let go of is said plainly, and not claimed as unloaded",
          out.get("still_loaded") == ["stuck:1b"] and "stuck:1b" not in out["unloaded"]
          and "Still loaded after asking Ollama to unload it: stuck:1b." in out["message"],
          repr(out))

    reset()

    class NoUnload:
        def resident_models(self):
            return ["jarvis-primary:8b"]
    o = FakeOllama(["jarvis-primary:8b"])
    code, out = S.set_mode("standby", gate_check=_auto, models=NoUnload(), ollama=o, others=[])
    check("a jarvis_models without unload(): Ollama is asked directly, and it is freed",
          o.loaded == [] and out["unloaded"] == ["jarvis-primary:8b"] and "note" not in out,
          repr(out))


def t_only_this_pcs_ollama():
    for url, ok in (("http://127.0.0.1:11434", True), ("http://localhost:11434", True),
                    ("127.0.0.1:11434", True), ("http://0.0.0.0:11434", True),
                    ("http://10.0.0.5:11434", False), ("http://gpu-box.ts.net:11434", False),
                    ("https://ollama.com", False)):
        check(f"OLLAMA_URL {url}: {'this PC' if ok else 'refused'}",
              (S.EverydayOllama(url).url is not None) is ok)
    reset()
    o = FakeOllama(["jarvis-primary:8b"], url=None)
    code, out = S.set_mode("standby", gate_check=_auto, models=types.SimpleNamespace(),
                           ollama=o, others=[])
    check("another machine's Ollama is asked nothing, and that is said",
          o.unloads == [] and "OLLAMA_URL is not this PC" in out.get("note", ""), repr(out))
    src = (HERE / "jarvis_power_switch.py").read_text(encoding="utf-8")
    body = src[src.index("class EverydayOllama"):src.index("def everyday_ollama")]
    check("every call goes through jarvis_local_http (no proxy), never a bare urlopen",
          body.count("jarvis_local_http.urlopen(") == 2
          and "urllib.request.urlopen(" not in body)


def t_waking_loads_the_chat_model_again():
    import os
    reset()
    S.set_mode("standby", gate_check=_auto, models=FakeModels(), ollama=FakeOllama(), others=[])
    o = FakeOllama()
    os.environ["JARVIS_MODEL"] = "jarvis-primary"
    try:
        code, out = S.set_mode("active", gate_check=_auto, ollama=o, warm=lambda fn: fn())
    finally:
        os.environ.pop("JARVIS_MODEL", None)
    check("waking from standby loads the chat model at once",
          o.loads == ["jarvis-primary"] and S.warm_status()["state"] == "ready", repr(o.loads))
    check("... and says so, naming it", out["warm_up"] == "jarvis-primary"
          and "Loading the chat model (jarvis-primary) again now" in out["message"], repr(out))
    o2 = FakeOllama()
    code, out = S.set_mode("quiet", gate_check=_auto, ollama=o2, warm=lambda fn: fn())
    check("active -> quiet loads nothing (the model was never unloaded)",
          o2.loads == [] and "warm_up" not in out, repr(out))


def t_the_warm_up_refuses_what_it_must():
    reset()
    o = FakeOllama()
    st = S.warm_up(P, o, "gpt-oss:120b-cloud")
    check("a cloud model is never loaded", o.loads == [] and st["state"] == "skipped"
          and "ollama.com" in st["why"], repr(st))
    st = S.warm_up(P, FakeOllama(url=None), "jarvis-primary")
    check("another machine's Ollama is never asked", st["state"] == "skipped"
          and "not this PC" in st["why"], repr(st))
    st = S.warm_up(P, o, None)
    check("no model known: nothing loaded, and the first answer's wait is said",
          st["state"] == "skipped" and "5-15 seconds" in st["why"], repr(st))

    class Boom(FakeOllama):
        def load(self, name):
            raise OSError("refused")
    st = S.warm_up(P, Boom(), "jarvis-primary")
    check("Ollama failing to load it is said, not raised", st["state"] == "failed", repr(st))

    class BackToSleep(FakeOllama):
        def load(self, name):
            super().load(name)
            P.set_mode("standby", "test")      # the owner chose Standby meanwhile
    o = BackToSleep()
    reset()
    st = S.warm_up(P, o, "jarvis-primary")
    check("back on standby while it loaded: unloaded again, standby's promise kept",
          o.loaded == [] and o.unloads == ["jarvis-primary"] and st["state"] == "skipped",
          repr((o.loaded, st)))
    reset()


def t_the_answer_comes_when_the_mode_has_changed():
    # Freeing the cards can take seconds. Waiting for it used to make the
    # answer "Waiting for your approval" when no card was up at all.
    reset()
    o = FakeOllama(["jarvis-primary:8b"], slow=0.5)
    code, out = S.set_mode("standby", gate_check=_auto, models=types.SimpleNamespace(),
                           ollama=o, others=[], wait_s=0.2)
    check("a slow unload: 200, changed, 'freeing the graphics card now' - not 202 waiting",
          code == 200 and out["changed"] is True and out.get("waiting") is None
          and "Freeing the graphics card now." in out["message"]
          and "approval" not in out["message"], repr((code, out)))
    check("... and the mode is already standby", P.current() == "standby")
    for _ in range(100):
        if not S._PENDING:
            break
        __import__("time").sleep(0.02)
    check("... and the unloading finishes behind it", o.loaded == [], repr(o.loaded))
    reset()


def t_why_is_the_callers_own():
    reset()
    S.set_mode("quiet", gate_check=_auto, by="the standby schedule", why="the standby schedule")
    check("the standby schedule is recorded as itself, not as 'the owner' (the tray would "
          "say 'set by hand')", P.status()["why"] == "the standby schedule", P.status())
    reset()
    S.set_mode("quiet", gate_check=_auto, by="phone")
    check("a tap in an app is still 'the owner, from ...'",
          P.status()["why"] == "the owner, from phone", P.status())
    reset()


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
