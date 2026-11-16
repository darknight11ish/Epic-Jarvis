#!/usr/bin/env python3
"""test_awareness_gaps.py - four awareness answers the audit found missing.

    python -B backend/test_awareness_gaps.py

THE MEASURED GAP (2026-11-15). An audit asked the live backend nineteen
awareness questions and checked each answer against the machine. Eleven had NO
deterministic answer at all: they fell through `jarvis_quick` to the 8B model,
which cannot measure any of them, so whatever it said was invention. PR #1292
fixed two. This suite proves the four of the remaining eleven that a real local
read can settle exactly:

  * "what models are loaded" - Ollama's own `/api/ps`, through the reader the
    benchmark already uses (`jarvis_bench.ps_models`);
  * "how many models are installed" (and which) - the installed-model list the
    app already reads (`jarvis_model_knowledge.installed_models`), through the
    existing `models_list` answer, which already led with the count;
  * "what is my disk space" - the same PC-facts disk reader
    (`jarvis_pc_facts`, which reads `jarvis_pc_help`'s own `shutil.disk_usage`
    rows) that "how much disk space is left" already reaches, so the reply
    names EVERY drive: the audit's gap was the phrasing, not a missing fact;
  * "is ollama running" - whether the lane's server answers
    (`jarvis_model_lanes.probe`), the same `/api/tags` probe both apps' lane
    warning already makes.

WHAT IT PROVES, and these are the rules the answers exist to keep:

  1. every audit sentence is reached by `answer_turn` with its intent - on the
     audited tree all four returned None, which is the route handing the
     question to the model;
  2. each answer says WHICH read answered (`/api/ps`, `/api/tags`, the
     installed-model list, the disk read), so the words can be checked;
  3. a read that fails says "I could not read" / "I cannot tell" and NEVER
     invents a number or a name - driven with each reader stubbed to fail;
  4. "nothing is loaded" is said when `/api/ps` returns an empty list, and the
     configured model is "set to use" - never claimed to be loaded or running
     (PR #1292's rule);
  5. the loaded answer quotes the stub's OWN name, memory, card share and
     context - nothing in the answer is typed into the source;
  6. no card, no model call, no socket and no write: with the readers stubbed,
     a socket connection is an assertion failure, a `jarvis_gate` module that
     raises on ANY attribute is installed and every answer still answers, the
     fake readers record the calls the answers really made (`ps_models` at the
     lane's address, `probe` on the lane's port), and no approvals/receipts
     database appears;
  7. the neighbours keep their own answers: "which model are you running" is
     still `model_current`, "what models are installed" is still `models_list`,
     "how much disk space do i have" is still `pc_help`, and the sentences this
     change deliberately does NOT answer stay unclaimed;
  8. the twin `jarvis-backend/jarvis_quick.py` is byte-identical, so the
     deployed copy is the tested one;
  9. THE BITE: with the new matcher removed in memory, the audit sentence falls
     straight back to None - so these checks fail if the registration is lost.

No network, no model, no live install: every reader is a fake injected into
`sys.modules`, the config folder is a throwaway temp directory, and
`JARVIS_BACKEND` is unset.
"""
from __future__ import annotations

import os
import re
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-awareness-gaps-"))
# Before anything imports jarvis_framework or the receipt stores: their paths
# are read once, at import.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
(_TMP / "home").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_bench.py", "jarvis_model_lanes.py",
                "jarvis_pc_facts.py", "jarvis_model_knowledge.py")
os.environ.pop("JARVIS_BACKEND", None)

PASSED, FAILED = [], []

#: The audit's four sentences, and the intent each must reach.
AUDIT = (
    ("what models are loaded", "models_loaded"),
    ("which model is loaded right now", "models_loaded"),
    ("how many models are loaded", "models_loaded"),
    ("what's loaded in ollama", "models_loaded"),
    ("is anything loaded", "models_loaded"),
    ("how many models are installed", "models_list"),
    ("how many models are installed and which", "models_list"),
    ("how many models do i have", "models_list"),
    ("what is my disk space", "pc_facts"),
    ("what's my free disk space", "pc_facts"),
    ("is ollama running", "ollama_running"),
    ("is the ollama server up", "ollama_running"),
    ("is ollama still running", "ollama_running"),
)

#: The eleven-gap questions this change deliberately does NOT answer, because
#: the honest source is not on this PC (the phone's own facts, or a measurement
#: nothing here makes). None of them may be claimed by the four above.
NOT_OURS = (
    "what is my phone model",
    "are you connected to my phone",
    "what is my mailbox",
    "which card runs the model",
    "what are you doing",
    "what can you not do",
    "how many interruptions are left",
    # The phone's own model is not this PC's Ollama, even when the words fit.
    "what models are loaded on my phone",
    "is ollama running on my phone",
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + str(detail)) if detail and not cond else ""))


# --------------------------------------------------------------------------
#  The fakes: every read these answers make, in the shape the real module has
# --------------------------------------------------------------------------

def _fake_lanes(lane="everyday", port=11436, up=True, target_none=False,
                probe_raises=False):
    mod = types.ModuleType("jarvis_model_lanes")
    row = types.SimpleNamespace(
        key=lane, port=port, task_prefix="Jarvis Ollama - Everyday model",
        words="the everyday model (the main one chat uses)")
    mod.PROBED = []

    def target(lanes=None, url=None):
        return None if target_none else row

    def port_of(url):
        m = re.search(r":(\d+)/?$", str(url or ""))
        return int(m.group(1)) if m else None

    def probe(got_port, timeout=3.0):
        mod.PROBED.append(int(got_port))
        if probe_raises:
            raise RuntimeError("the probe failed")
        return bool(up)

    mod.target, mod.port_of, mod.probe = target, port_of, probe
    return mod


def _fake_bench(rows=None, raises=False):
    """`jarvis_bench` with its own `/api/ps` reader.

    `rows=None` is the real reader's own failure value (`ps_models` returns
    None when the read fails), and `rows=[]` is a successful read of nothing.
    """
    mod = types.ModuleType("jarvis_bench")
    mod.CALLED = []

    def ps_models(base, get=None):
        mod.CALLED.append(str(base))
        if raises:
            raise RuntimeError("the ps read failed")
        return rows

    mod.ps_models = ps_models
    mod.is_loopback = lambda url: str(url).startswith(
        ("http://127.0.0.1", "http://localhost", "http://[::1]"))
    return mod


def _fake_models(current="qwen3.5:9b", installed=None, raises=False):
    mod = types.ModuleType("jarvis_models")
    mod.current_model = lambda: current

    def installed_models():
        if raises:
            raise RuntimeError("the installed list failed")
        return list(installed or [])

    mod.installed_models = installed_models
    return mod


def _fake_hardware(main_url=""):
    mod = types.ModuleType("jarvis_hardware")
    mod._current_model = lambda: ""
    mod._main_url = lambda: main_url
    mod._tags = lambda url: None
    return mod


def _fake_pc_facts(reply="", raises=False, calls=None):
    mod = types.ModuleType("jarvis_pc_facts")
    calls = calls if calls is not None else []

    def answer(shape, *, drive="", facts=None):
        calls.append({"shape": str(shape), "drive": str(drive)})
        if raises:
            raise RuntimeError("the disk read failed")
        return reply

    mod.answer = answer
    return mod, calls


def _install(lanes=None, bench=None, models=None, hardware=None, pc_facts=None):
    """Put the fakes in `sys.modules`; returns what must be restored."""
    saved = {}
    for name, mod in (("jarvis_model_lanes", lanes), ("jarvis_bench", bench),
                      ("jarvis_models", models), ("jarvis_hardware", hardware),
                      ("jarvis_pc_facts", pc_facts)):
        saved[name] = sys.modules.get(name)
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    return saved


def _restore(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def main():
    import jarvis_schedule as SCH
    import jarvis_model_knowledge as K
    import jarvis_quick as Q

    sched = SCH.Scheduler(_TMP / "schedule.db")

    def ask(text):
        return Q.answer_turn(
            {"messages": [{"role": "user", "content": text,
                           "provenance": "typed"}],
             "conversation_id": "abcdefgh-awareness-gap"}, sched=sched)

    def say(text):
        got = ask(text)
        return getattr(got, "intent", None), (getattr(got, "reply", "") or "")

    loaded_row = {"name": "qwen3.5:9b", "model": "qwen3.5:9b",
                  "size": 9857400830, "size_vram": 9857400830,
                  "context_length": 196608,
                  "expires_at": "2319-02-25T21:33:11-08:00"}

    # ------------------------------------------------------------------
    #  1. Every audit sentence reaches its own answer (it did not before)
    # ------------------------------------------------------------------
    for sentence, want in AUDIT:
        got = Q.match(sentence)
        check(f"'{sentence}' is {want}, not the model",
              got is not None and got.name == want, got)
        if want == "pc_facts" and got is not None:
            check(f"... '{sentence}' asks the EXISTING whole-PC disk shape",
                  got.f.get("shape") == "space_all", got.f)
    for sentence in NOT_OURS:
        got = Q.match(sentence)
        check(f"not claimed: '{sentence}' is not one of the four",
              got is None or got.name not in
              ("models_loaded", "ollama_running"), got)

    # ------------------------------------------------------------------
    #  2. A LOADED model: the answer quotes the read's own row
    # ------------------------------------------------------------------
    bench = _fake_bench(rows=[dict(loaded_row)])
    saved = _install(lanes=_fake_lanes(), bench=bench,
                     models=_fake_models(), hardware=_fake_hardware(),
                     pc_facts=_fake_pc_facts(""))
    try:
        intent, said = say("what models are loaded")
        check("loaded: the intent is models_loaded", intent == "models_loaded", intent)
        check("loaded: names the model the read returned",
              "qwen3.5:9b" in said, said)
        check("loaded: quotes the read's own memory, card share and context",
              "9.2 GB" in said and "all on the card" in said
              and "196,608-token context" in said, said)
        check("loaded: says which read answered",
              "/api/ps" in said and "http://127.0.0.1:11436" in said, said)
        check("loaded: reads the ONE address the chat uses",
              bench.CALLED == ["http://127.0.0.1:11436"], bench.CALLED)
        check("loaded: never calls the configured model 'running'",
              "running" not in said.lower(), said)
        check("loaded: short enough for a phone", len(said) <= 400, len(said))

        # A second loaded model is listed too, and the card share is computed
        # from THAT row's own bytes.
        half = 1610612736                    # 1.5 GB of a 3 GB model
        bench_rows = [dict(loaded_row, name="qwen3.5:4b",
                           size=3 * 1024 ** 3, size_vram=half,
                           context_length=8192)]
        bench.ps_models = lambda base, get=None: (bench.CALLED.append(base)
                                                  or bench_rows[:])
        intent, said = say("what models are loaded")
        check("loaded: a second model, with its own card share",
              "qwen3.5:4b" in said and "50% on the card" in said
              and "8,192-token context" in said, said)

        # ------------------------------------------------------------------
        #  3. NOTHING loaded: said plainly, and the choice is not a claim
        # ------------------------------------------------------------------
        bench.ps_models = lambda base, get=None: (bench.CALLED.append(base) or [])
        intent, said = say("what models are loaded")
        check("nothing loaded: says nothing is loaded",
              intent == "models_loaded" and "Nothing is loaded right now" in said,
              said)
        check("nothing loaded: names the read",
              "no model in memory" in said and "/api/ps" in said, said)
        check("nothing loaded: the configured model is 'set to use', never loaded",
              "set to use qwen3.5:9b" in said
              and "not proof it is loaded" in said, said)
        check("nothing loaded: says nothing is running",
              "running" not in said.lower(), said)

        # ------------------------------------------------------------------
        #  4. The /api/ps read FAILS: no model name, no number, no guess
        # ------------------------------------------------------------------
        for how, breaker in (
                ("returns no answer", lambda base, get=None: None),
                ("raises", None)):
            if breaker is None:
                bench.ps_models = lambda base, get=None: (_ for _ in ()).throw(
                    RuntimeError("the ps read failed"))
            else:
                bench.ps_models = breaker
            intent, said = say("what models are loaded")
            check(f"read fails ({how}): says it could not read /api/ps",
                  intent == "models_loaded" and "could not read" in said
                  and "/api/ps" in said, said)
            check(f"read fails ({how}): says it cannot tell, and will not guess",
                  "cannot tell" in said and "will not guess" in said, said)
            check(f"read fails ({how}): never offers a model name or a size",
                  "qwen3.5:9b" not in said and "GB" not in said, said)
            check(f"read fails ({how}): nothing was started",
                  "Nothing was started" in said, said)

        # ------------------------------------------------------------------
        #  5. The server cannot be named: say so, and do not read at all
        # ------------------------------------------------------------------
        bench.CALLED.clear()
        saved2 = _install(lanes=_fake_lanes(target_none=True),
                          bench=bench, models=_fake_models(),
                          hardware=_fake_hardware(main_url=""),
                          pc_facts=_fake_pc_facts(""))
        try:
            intent, said = say("what models are loaded")
            check("no address: says it cannot tell which model is loaded",
                  intent == "models_loaded" and "cannot tell" in said
                  and "will not guess" in said, said)
            check("no address: no read was attempted", bench.CALLED == [],
                  bench.CALLED)
        finally:
            _restore(saved2)

        # ------------------------------------------------------------------
        #  6. "Is ollama running": answers, does not answer, cannot probe
        # ------------------------------------------------------------------
        lanes = _fake_lanes(up=True)
        saved2 = _install(lanes=lanes, bench=bench, models=_fake_models(),
                          hardware=_fake_hardware(), pc_facts=_fake_pc_facts(""))
        try:
            intent, said = say("is ollama running")
            check("ollama up: says yes and names the probe",
                  intent == "ollama_running" and said.startswith("Yes")
                  and "/api/tags" in said and "http://127.0.0.1:11436" in said,
                  said)
            check("ollama up: probes the chat lane's own port",
                  lanes.PROBED == [11436], lanes.PROBED)
            lanes.probe = lambda port, timeout=3.0: (
                lanes.PROBED.append(int(port)) or False)
            intent, said = say("is ollama running")
            check("ollama down: says it is not answering, in those words",
                  intent == "ollama_running" and "not answering" in said
                  and "got nothing back" in said, said)
            check("ollama down: says plainly what it did NOT do",
                  "I did not start it" in said, said)
            check("ollama down: no invented version, size or model name",
                  "version" not in said.lower() and "GB" not in said
                  and "qwen3.5" not in said, said)
            lanes.probe = lambda port, timeout=3.0: (
                lanes.PROBED.append(int(port)) or
                (_ for _ in ()).throw(RuntimeError("no probe")))
            intent, said = say("is ollama running")
            check("probe fails: says it cannot tell and will not guess",
                  "cannot tell whether Ollama is running" in said
                  and "will not guess" in said, said)
        finally:
            _restore(saved2)

        saved2 = _install(lanes=_fake_lanes(target_none=True), bench=bench,
                          models=_fake_models(),
                          hardware=_fake_hardware(main_url=""),
                          pc_facts=_fake_pc_facts(""))
        try:
            lanes = sys.modules["jarvis_model_lanes"]
            intent, said = say("is ollama running")
            check("no address: cannot tell whether Ollama is running",
                  intent == "ollama_running" and "cannot tell" in said
                  and "will not guess" in said, said)
            check("no address: no probe was made", lanes.PROBED == [], lanes.PROBED)
        finally:
            _restore(saved2)

        # ------------------------------------------------------------------
        #  7. Installed models: the count and the list, or no guessing
        # ------------------------------------------------------------------
        installed = ["qwen3.5:9b", "qwen3.5:4b", "qwen2.5vl:7b"]
        saved2 = _install(lanes=_fake_lanes(), bench=bench,
                          models=_fake_models(installed=installed),
                          hardware=_fake_hardware(),
                          pc_facts=_fake_pc_facts(""))
        try:
            intent, said = say("how many models are installed")
            check("installed: the existing models_list answer takes it",
                  intent == "models_list", intent)
            check("installed: leads with the count the read returned",
                  "3 local models installed" in said, said)
            check("installed: names the models and the one chat uses",
                  all(name in said for name in installed)
                  and "Chat is using qwen3.5:9b" in said, said)
            for _ in ("installed_models",):
                saved3 = sys.modules.get("jarvis_models")
                sys.modules["jarvis_models"] = _fake_models(raises=True)
                try:
                    intent, said = say("how many models are installed")
                finally:
                    sys.modules["jarvis_models"] = saved3
                check("installed: a read that raises says it cannot tell",
                      intent == "models_list" and "cannot tell how many" in said
                      and "will not guess" in said, said)
                check("installed: ... and never claims zero installed",
                      "0 local models" not in said and "no models" not in said, said)
            sys.modules["jarvis_models"] = _fake_models(installed=[])
            try:
                intent, said = say("how many models are installed")
            finally:
                sys.modules["jarvis_models"] = _fake_models(installed=installed)
            check("installed: an empty list is 'cannot tell', not 'none'",
                  "cannot tell how many" in said and "will not guess" in said, said)
        finally:
            _restore(saved2)

        # ------------------------------------------------------------------
        #  8. Disk space: the audit's PHRASE reaches the WIDE answer that
        #     already names every drive - not a narrower answer of its own
        # ------------------------------------------------------------------
        # "how much disk space is left" already reached `space_all` and
        # answered every drive; only "what is my disk space" fell to the model.
        # So the promise to pin is that the new wording reaches that SAME
        # answer, widened to both drives rather than narrowed to the one the
        # backend sits on - and the reader is asked for `space_all`, once.
        pc, calls = _fake_pc_facts(
            "C: has 100.0 GB free of 200.0 GB (50% free). "
            "D: has 400.0 GB free of 500.0 GB (80% free).")
        saved2 = _install(lanes=_fake_lanes(), bench=bench,
                          models=_fake_models(), hardware=_fake_hardware(),
                          pc_facts=pc)
        try:
            intent, said = say("what is my disk space")
            check("disk: 'what is my disk space' reaches the existing space_all "
                  "answer, and it names both drives",
                  intent == "pc_facts"
                  and calls == [{"shape": "space_all", "drive": ""}]
                  and "C: has 100.0 GB free of 200.0 GB" in said
                  and "D: has 400.0 GB free of 500.0 GB" in said,
                  (intent, calls, said))
        finally:
            _restore(saved2)

        # ------------------------------------------------------------------
        #  9. No card, no model, no socket, no write
        # ------------------------------------------------------------------
        class _NoGate(types.ModuleType):
            def __getattr__(self, name):
                raise AssertionError("an approval card was raised: " + name)

        saved_gate = sys.modules.get("jarvis_gate")
        sys.modules["jarvis_gate"] = _NoGate("jarvis_gate")
        connects = []

        def counted_connect(self, address):
            connects.append(address)
            raise AssertionError("a socket was opened by a deterministic answer")

        real_connect = socket.socket.connect
        socket.socket.connect = counted_connect
        lanes9, bench9 = _fake_lanes(), _fake_bench(rows=[loaded_row])
        saved2 = _install(lanes=lanes9, bench=bench9,
                          models=_fake_models(installed=["qwen3.5:9b"]),
                          hardware=_fake_hardware(),
                          pc_facts=_fake_pc_facts("C: has 100.0 GB free of 200.0 GB."))
        saids = []
        try:
            for sentence, _want in AUDIT:
                saids.append(say(sentence)[1])
        finally:
            socket.socket.connect = real_connect
            _restore(saved2)
            if saved_gate is None:
                sys.modules.pop("jarvis_gate", None)
            else:
                sys.modules["jarvis_gate"] = saved_gate
        check("no socket: with the readers stubbed, no connection was attempted",
              connects == [], connects)
        check("no write: no approvals database was created",
              not (_TMP / "config" / "approvals.db").exists())
        check("no write: no receipts database was created",
              not (_TMP / "config" / "receipts.db").exists())
        # BEHAVIOUR, not the answer's source text: `_NoGate` raises on ANY
        # attribute, so an answer that reached for a card would have crashed the
        # run above, and each one still had to produce words of its own.
        check("no card: every audit answer ran with the gate module raising, "
              "and each one answered",
              len(saids) == len(AUDIT) and all(isinstance(s, str) and s
                                               for s in saids),
              saids)
        # The reader each answer SAYS it used is the one the fake saw called:
        # `/api/ps` at the lane's own address, and the lane's `/api/tags` probe
        # on the lane's own port. (A source-text pin cannot prove this - it only
        # proves a name was typed - which is why the checker forbids one.)
        check("the loaded answer really called the /api/ps reader, at the lane's address",
              bool(bench9.CALLED) and all(u.startswith("http://127.0.0.1:11436")
                                          for u in bench9.CALLED),
              bench9.CALLED)
        check("the running answer really called the lane's /api/tags probe, on its port",
              bool(lanes9.PROBED) and set(lanes9.PROBED) == {11436}, lanes9.PROBED)

        # ------------------------------------------------------------------
        #  10. Neighbours keep their own answers
        # ------------------------------------------------------------------
        for sentence, want in (
                ("which model are you running", "model_current"),
                ("what model are you using", "model_current"),
                ("what models are installed", "models_list"),
                ("how much disk space do i have", "pc_help"),
                ("how much space do i have left", "pc_help"),
                ("is my disk getting full", "pc_facts")):
            got = Q.match(sentence)
            check(f"neighbour: '{sentence}' keeps {want}",
                  got is not None and got.name == want, got)

        # ------------------------------------------------------------------
        #  11. The twin is identical, so the deployed copy is the tested one
        # ------------------------------------------------------------------
        a = (REPO / "backend" / "jarvis_quick.py").read_bytes()
        b = (REPO / "jarvis-backend" / "jarvis_quick.py").read_bytes()
        check("twin: jarvis_quick.py is identical in both copies", a == b)

        # ------------------------------------------------------------------
        #  12. THE BITE: remove the registration in memory and it falls back
        # ------------------------------------------------------------------
        saved_loaded = Q._K_MODELS_LOADED
        Q._K_MODELS_LOADED = re.compile(r"(?!)")
        try:
            check("bite: without the loaded matcher, the audit sentence is the "
                  "model's again",
                  Q.match("what models are loaded") is None,
                  Q.match("what models are loaded"))
        finally:
            Q._K_MODELS_LOADED = saved_loaded
        saved_running = Q._K_OLLAMA_RUNNING
        Q._K_OLLAMA_RUNNING = re.compile(r"(?!)")
        try:
            check("bite: without the ollama matcher, that sentence is the "
                  "model's again",
                  Q.match("is ollama running") is None,
                  Q.match("is ollama running"))
        finally:
            Q._K_OLLAMA_RUNNING = saved_running
        saved_facts = Q._PC_FACTS
        Q._PC_FACTS = tuple((shape, rx) for shape, rx in saved_facts
                            if not rx.fullmatch("what is my disk space"))
        try:
            check("bite: without the widened disk row, 'what is my disk space' "
                  "is the model's again",
                  Q.match("what is my disk space") is None,
                  Q.match("what is my disk space"))
        finally:
            Q._PC_FACTS = saved_facts
        saved_list = Q._K_MODELS_LIST
        Q._K_MODELS_LIST = re.compile(r"(?!)")
        try:
            check("bite: without the widened list matcher, 'how many models are "
                  "installed' is the model's again",
                  Q.match("how many models are installed") is None,
                  Q.match("how many models are installed"))
        finally:
            Q._K_MODELS_LIST = saved_list
        check("bite: the restored matchers answer again",
              (Q.match("what models are loaded") or types.SimpleNamespace(
                  name=None)).name == "models_loaded"
              and (Q.match("is ollama running") or types.SimpleNamespace(
                  name=None)).name == "ollama_running"
              and (Q.match("what is my disk space") or types.SimpleNamespace(
                  name=None)).name == "pc_facts"
              and (Q.match("how many models are installed") or types.SimpleNamespace(
                  name=None)).name == "models_list")

        # The fakes come out of `sys.modules` below; the real readers are what
        # every later suite in this process must see.
        check("the real installed-model reader is the product's own",
              callable(getattr(K, "installed_models", None)))
    finally:
        _restore(saved)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  FAIL {name}")
        sys.exit(1)
    print(f"{len(PASSED)} passed, 0 failed")
